"""n8n 스타일 워크플로우 에디터 백엔드.

- 단일 JSON 파일(`~/.claude-dashboard-workflows.json`) 에 여러 워크플로우 저장
- 각 워크플로우 = 노드(세션·서브에이전트·취합·분기·결과) + 엣지(DAG)
- Run 엔진: DAG topological sort → 각 노드별 subprocess 로 `claude -p` 실행
- 모든 I/O 는 atomic write (tmp → rename) + 화이트리스트 검증
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Optional

from .config import WORKFLOWS_PATH
from .logger import log
from .utils import _safe_read, _safe_write


# ───────── 상수 ─────────

_NODE_TYPES = {"start", "session", "subagent", "aggregate", "branch", "output"}
_INPUT_MODES = {"concat", "first", "json"}
_ASSIGNEES = {"opus-4.7", "sonnet-4.6", "haiku-4.5"}  # UI 선택지용; 검증 여기서는 free-form

_WF_ID_RE = re.compile(r"^wf-[0-9]{10,14}-[a-z0-9]{3,6}$")
_NODE_ID_RE = re.compile(r"^n-[A-Za-z0-9_-]{1,40}$")
_RUN_ID_RE = re.compile(r"^run-[0-9]{10,14}-[a-z0-9]{3,8}$")

_DEFAULT_NODE_TIMEOUT = int(os.environ.get("WORKFLOW_NODE_TIMEOUT", "300"))
_DEFAULT_TOTAL_TIMEOUT = int(os.environ.get("WORKFLOW_TOTAL_TIMEOUT", "1800"))

# Run 엔진용 동시성 — 서버 프로세스 안에서 run 을 돌려야 하므로 lock 필요
_LOCK = threading.Lock()


# ───────── 영속 ─────────

def _empty_store() -> dict:
    return {"version": 1, "workflows": {}, "runs": {}, "customTemplates": {}}


def _load_all() -> dict:
    """파일 로드. 없거나 파싱 실패 시 빈 store 반환."""
    if not WORKFLOWS_PATH.exists():
        return _empty_store()
    try:
        data = json.loads(_safe_read(WORKFLOWS_PATH) or "{}")
        if not isinstance(data, dict):
            return _empty_store()
        data.setdefault("version", 1)
        data.setdefault("workflows", {})
        data.setdefault("runs", {})
        data.setdefault("customTemplates", {})
        if not isinstance(data["workflows"], dict):
            data["workflows"] = {}
        if not isinstance(data["runs"], dict):
            data["runs"] = {}
        if not isinstance(data["customTemplates"], dict):
            data["customTemplates"] = {}
        return data
    except Exception as e:
        log.warning("workflows load failed: %s — using empty store", e)
        return _empty_store()


def _dump_all(data: dict) -> bool:
    try:
        text = json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("workflows dump json failed: %s", e)
        return False
    return _safe_write(WORKFLOWS_PATH, text)


# ───────── 검증 / sanitize ─────────

def _clamp_str(s: Any, max_len: int) -> str:
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    return s[:max_len]


def _clamp_float(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
        if f != f or f == float("inf") or f == float("-inf"):
            return default
        return f
    except Exception:
        return default


def _under_home(raw_path: str) -> Optional[str]:
    """문자열 경로를 절대화하고 ~/ 하위면 abs path 반환, 아니면 None."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    try:
        expanded = os.path.expanduser(raw_path.strip())
        abs_p = os.path.abspath(expanded)
    except Exception:
        return None
    home = str(Path.home())
    if abs_p == home or abs_p.startswith(home + os.sep):
        return abs_p
    return None


def _sanitize_node(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    nid = raw.get("id")
    if not isinstance(nid, str) or not _NODE_ID_RE.match(nid):
        return None
    ntype = raw.get("type")
    if ntype not in _NODE_TYPES:
        return None
    out: dict = {
        "id": nid,
        "type": ntype,
        "x": _clamp_float(raw.get("x"), 0.0),
        "y": _clamp_float(raw.get("y"), 0.0),
        "title": _clamp_str(raw.get("title"), 120),
        "data": {},
    }
    d = raw.get("data") or {}
    if not isinstance(d, dict):
        d = {}
    if ntype in ("session", "subagent"):
        out["data"] = {
            "subject":     _clamp_str(d.get("subject"), 200),
            "description": _clamp_str(d.get("description"), 4000),
            "assignee":    _clamp_str(d.get("assignee"), 40),
            "agentRole":   _clamp_str(d.get("agentRole"), 80),
            "cwd":         _clamp_str(d.get("cwd"), 500),
            "inputsMode":  d.get("inputsMode") if d.get("inputsMode") in _INPUT_MODES else "concat",
            "tags":        [_clamp_str(t, 40) for t in (d.get("tags") or []) if isinstance(t, str)][:10],
            # 세션 하네스 (persona · CLAUDE.md 스타일 지시 · tools · resume)
            "systemPrompt":       _clamp_str(d.get("systemPrompt"), 8000),
            "appendSystemPrompt": _clamp_str(d.get("appendSystemPrompt"), 4000),
            "allowedTools":       _clamp_str(d.get("allowedTools"), 500),
            "disallowedTools":    _clamp_str(d.get("disallowedTools"), 500),
            "resumeSessionId":    _clamp_str(d.get("resumeSessionId"), 80),
            # 연결 노드의 session_id 를 자동으로 --resume 으로 이어받기
            "continueFromPrev":   bool(d.get("continueFromPrev")),
            "sessionRef":  {
                "mode":      _clamp_str((d.get("sessionRef") or {}).get("mode"), 20) or "spawn",
                "sessionId": _clamp_str((d.get("sessionRef") or {}).get("sessionId"), 80),
                "pid":       (d.get("sessionRef") or {}).get("pid"),
            },
            "lastRun": d.get("lastRun") if isinstance(d.get("lastRun"), dict) else {
                "status": "idle", "output": None, "sessionId": "", "durationMs": 0, "startedAt": 0
            },
        }
    elif ntype == "branch":
        out["data"] = {"condition": _clamp_str(d.get("condition"), 400)}
    elif ntype == "aggregate":
        mode = d.get("mode") if d.get("mode") in ("concat", "json") else "concat"
        out["data"] = {"mode": mode}
    elif ntype == "output":
        exp = d.get("exportTo")
        out["data"] = {"exportTo": _clamp_str(exp, 500)}
    # start 는 data 비움
    return out


def _sanitize_edge(raw: Any, node_ids: set[str]) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    eid = _clamp_str(raw.get("id"), 60) or f"e-{int(time.time()*1000)}-{uuid.uuid4().hex[:4]}"
    frm = raw.get("from"); to = raw.get("to")
    if not (isinstance(frm, str) and isinstance(to, str)):
        return None
    if frm not in node_ids or to not in node_ids or frm == to:
        return None
    from_port = raw.get("fromPort") if raw.get("fromPort") in ("out", "out_y", "out_n") else "out"
    to_port = raw.get("toPort") if raw.get("toPort") == "in" else "in"
    return {
        "id": eid, "from": frm, "to": to,
        "fromPort": from_port, "toPort": to_port,
        "label": _clamp_str(raw.get("label"), 80),
    }


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _sanitize_repeat(raw: Any) -> dict:
    """반복 실행 설정 sanitize. enabled 기본 False."""
    if not isinstance(raw, dict):
        return {"enabled": False}
    def _time_str(s):
        s = _clamp_str(s, 5)
        return s if _TIME_RE.match(s) else ""
    return {
        "enabled":          bool(raw.get("enabled")),
        "maxIterations":    max(1, min(int(raw.get("maxIterations") or 5), 100)),
        "intervalSeconds":  max(0, min(int(raw.get("intervalSeconds") or 0), 86400)),
        "scheduleEnabled":  bool(raw.get("scheduleEnabled")),
        "scheduleStart":    _time_str(raw.get("scheduleStart")),
        "scheduleEnd":      _time_str(raw.get("scheduleEnd")),
        "feedbackNote":     _clamp_str(raw.get("feedbackNote"), 4000),
        "feedbackNodeId":   _clamp_str(raw.get("feedbackNodeId"), 60),
    }


def _sanitize_workflow(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    nodes_raw = raw.get("nodes") or []
    edges_raw = raw.get("edges") or []
    if not isinstance(nodes_raw, list) or not isinstance(edges_raw, list):
        return None
    nodes: list[dict] = []
    seen_ids: set[str] = set()
    for n in nodes_raw:
        cleaned = _sanitize_node(n)
        if cleaned and cleaned["id"] not in seen_ids:
            nodes.append(cleaned); seen_ids.add(cleaned["id"])
    node_ids = {n["id"] for n in nodes}
    edges: list[dict] = []
    seen_pairs: set[tuple] = set()
    for e in edges_raw:
        ce = _sanitize_edge(e, node_ids)
        if ce and (ce["from"], ce["to"], ce["fromPort"]) not in seen_pairs:
            edges.append(ce); seen_pairs.add((ce["from"], ce["to"], ce["fromPort"]))
    vp = raw.get("viewport") or {}
    out = {
        "name":        _clamp_str(raw.get("name"), 120) or "Untitled",
        "description": _clamp_str(raw.get("description"), 2000),
        "nodes":       nodes,
        "edges":       edges,
        "viewport": {
            "panX": _clamp_float(vp.get("panX"), 0.0),
            "panY": _clamp_float(vp.get("panY"), 0.0),
            "zoom": max(0.25, min(3.0, _clamp_float(vp.get("zoom"), 1.0))),
        },
        "repeat":      _sanitize_repeat(raw.get("repeat")),
    }
    return out


def _check_dag(nodes: list[dict], edges: list[dict]) -> list[str]:
    """DAG 검증. cycle 이 있으면 설명 리스트 반환, 없으면 빈 리스트."""
    ids = {n["id"] for n in nodes}
    adj: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = {nid: 0 for nid in ids}
    for e in edges:
        if e["from"] in ids and e["to"] in ids:
            adj[e["from"]].append(e["to"])
            indeg[e["to"]] = indeg.get(e["to"], 0) + 1
    # Kahn's
    q = deque([nid for nid, d in indeg.items() if d == 0])
    visited = 0
    while q:
        u = q.popleft(); visited += 1
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if visited != len(ids):
        # 어떤 노드가 사이클에 있는지 간단 표시
        stuck = [nid for nid, d in indeg.items() if d > 0][:5]
        return [f"cycle: nodes {', '.join(stuck)}"]
    return []


def _topological_order(nodes: list[dict], edges: list[dict]) -> list[str]:
    """사이클 없다고 가정. Kahn's 결과 순서 반환."""
    ids = [n["id"] for n in nodes]
    adj: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = {nid: 0 for nid in ids}
    for e in edges:
        if e["from"] in indeg and e["to"] in indeg:
            adj[e["from"]].append(e["to"])
            indeg[e["to"]] += 1
    q = deque([nid for nid in ids if indeg[nid] == 0])
    order: list[str] = []
    while q:
        u = q.popleft(); order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    return order


# ───────── ID 생성 ─────────

def _new_wf_id() -> str:
    return f"wf-{int(time.time()*1000)}-{uuid.uuid4().hex[:4]}"


def _new_run_id() -> str:
    return f"run-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"


# ───────── API: CRUD ─────────

def api_workflows_list(query: dict | None = None) -> dict:
    store = _load_all()
    out = []
    for wfId, wf in store["workflows"].items():
        out.append({
            "id": wfId,
            "name": wf.get("name", "Untitled"),
            "description": wf.get("description", ""),
            "nodeCount": len(wf.get("nodes", [])),
            "edgeCount": len(wf.get("edges", [])),
            "createdAt": wf.get("createdAt", 0),
            "updatedAt": wf.get("updatedAt", 0),
        })
    out.sort(key=lambda x: x["updatedAt"], reverse=True)
    return {"ok": True, "workflows": out}


def api_workflow_get(wfId: str) -> dict:
    if not isinstance(wfId, str) or not _WF_ID_RE.match(wfId):
        return {"ok": False, "error": "invalid id"}
    store = _load_all()
    wf = store["workflows"].get(wfId)
    if not wf:
        return {"ok": False, "error": "not found"}
    return {"ok": True, "workflow": wf}


def api_workflow_save(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    wf_clean = _sanitize_workflow(body)
    if wf_clean is None:
        return {"ok": False, "error": "invalid workflow"}
    now = int(time.time() * 1000)
    with _LOCK:
        store = _load_all()
        raw_id = body.get("id")
        is_new = not (isinstance(raw_id, str) and _WF_ID_RE.match(raw_id) and raw_id in store["workflows"])
        wfId = raw_id if not is_new else _new_wf_id()
        # staleness 체크 (optional)
        if not is_new:
            expected = body.get("ifUpdatedAt")
            current_updated = store["workflows"][wfId].get("updatedAt", 0)
            if isinstance(expected, int) and expected != current_updated:
                return {"ok": False, "error": "stale", "updatedAt": current_updated}
        wf_clean["id"] = wfId
        wf_clean["createdAt"] = (store["workflows"].get(wfId) or {}).get("createdAt") or now
        wf_clean["updatedAt"] = now
        store["workflows"][wfId] = wf_clean
        _dump_all(store)
    return {"ok": True, "id": wfId, "updatedAt": now, "created": is_new}


def api_workflow_patch(body: dict) -> dict:
    """부분 업데이트 — 노드 좌표 드래그 같은 고빈도 호출용. patch 는 키 단위 덮어쓰기."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    wfId = body.get("id")
    if not (isinstance(wfId, str) and _WF_ID_RE.match(wfId)):
        return {"ok": False, "error": "invalid id"}
    patch = body.get("patch") or {}
    if not isinstance(patch, dict):
        return {"ok": False, "error": "invalid patch"}
    now = int(time.time() * 1000)
    with _LOCK:
        store = _load_all()
        wf = store["workflows"].get(wfId)
        if not wf:
            return {"ok": False, "error": "not found"}
        merged = dict(wf)
        for k in ("name", "description"):
            if k in patch:
                merged[k] = _clamp_str(patch[k], 2000 if k == "description" else 120)
        if "nodes" in patch:
            # 부분 노드 좌표 patch: {nodes:[{id, x, y}]} → 기존 노드에 좌표만 덮어쓰기
            existing = {n["id"]: n for n in merged.get("nodes", [])}
            for pn in patch["nodes"]:
                if not isinstance(pn, dict):
                    continue
                nid = pn.get("id")
                if nid in existing:
                    if "x" in pn: existing[nid]["x"] = _clamp_float(pn["x"], existing[nid].get("x", 0))
                    if "y" in pn: existing[nid]["y"] = _clamp_float(pn["y"], existing[nid].get("y", 0))
        if "viewport" in patch and isinstance(patch["viewport"], dict):
            vp = merged.get("viewport") or {"panX": 0, "panY": 0, "zoom": 1}
            for k in ("panX", "panY"):
                if k in patch["viewport"]:
                    vp[k] = _clamp_float(patch["viewport"][k], vp.get(k, 0))
            if "zoom" in patch["viewport"]:
                vp["zoom"] = max(0.25, min(3.0, _clamp_float(patch["viewport"]["zoom"], 1.0)))
            merged["viewport"] = vp
        merged["updatedAt"] = now
        store["workflows"][wfId] = merged
        _dump_all(store)
    return {"ok": True, "id": wfId, "updatedAt": now}


def api_workflow_delete(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    wfId = body.get("id")
    if not (isinstance(wfId, str) and _WF_ID_RE.match(wfId)):
        return {"ok": False, "error": "invalid id"}
    with _LOCK:
        store = _load_all()
        if wfId not in store["workflows"]:
            return {"ok": False, "error": "not found"}
        del store["workflows"][wfId]
        # 연관 runs purge
        store["runs"] = {rid: r for rid, r in store["runs"].items() if r.get("workflowId") != wfId}
        _dump_all(store)
    return {"ok": True, "id": wfId}


# ───────── Run 엔진 ─────────

def _run_status_snapshot(runId: str) -> dict:
    store = _load_all()
    r = store["runs"].get(runId)
    if not r:
        return {"ok": False, "error": "run not found"}
    return {"ok": True, "run": r}


def _execute_node(node: dict, inputs: list[str], prev_session_ids: list[str] | None = None) -> dict:
    """단일 노드 실행. 동기. (subject/description + inputs) → stdout.

    prev_session_ids: 이 노드로 들어오는 엣지의 from 노드들의 lastRun.sessionId 리스트.
    continueFromPrev 가 켜지면 그 중 첫 번째(있으면)를 --resume 에 넘긴다.

    반환: {status:"ok|err", output:str, sessionId:str, durationMs:int, error?:str}
    """
    ntype = node["type"]
    data = node.get("data") or {}
    prev_session_ids = prev_session_ids or []
    t0 = int(time.time() * 1000)

    def _elapsed() -> int:
        return int(time.time() * 1000) - t0

    if ntype == "start":
        return {"status": "ok", "output": "", "durationMs": _elapsed(), "sessionId": ""}

    if ntype == "aggregate":
        mode = data.get("mode", "concat")
        if mode == "json":
            output = json.dumps(inputs, ensure_ascii=False)
        else:
            output = "\n---\n".join(inputs)
        return {"status": "ok", "output": output, "durationMs": _elapsed(), "sessionId": ""}

    if ntype == "branch":
        cond = (data.get("condition") or "").strip().lower()
        prev = (inputs[0] if inputs else "").lower()
        matched = bool(cond) and cond in prev
        out_port = "out_y" if matched else "out_n"
        return {
            "status": "ok", "output": prev, "durationMs": _elapsed(), "sessionId": "",
            "_branch": out_port,
        }

    if ntype == "output":
        final = inputs[0] if inputs else ""
        exp_raw = data.get("exportTo") or ""
        if exp_raw:
            under = _under_home(exp_raw)
            if under:
                try:
                    Path(under).parent.mkdir(parents=True, exist_ok=True)
                    _safe_write(Path(under), final)
                except Exception as e:
                    return {"status": "err", "output": "", "durationMs": _elapsed(), "error": f"export failed: {e}"}
        return {"status": "ok", "output": final, "durationMs": _elapsed(), "sessionId": ""}

    # ── session / subagent — `claude -p` 호출 ──
    prompt_parts = []
    if data.get("subject"):
        prompt_parts.append(data["subject"])
    if data.get("description"):
        prompt_parts.append(data["description"])
    if data.get("agentRole") and not data.get("systemPrompt"):
        # systemPrompt 가 있으면 거기서 역할을 설명하므로 중복 방지
        prompt_parts.append(f"(역할: {data['agentRole']})")
    if inputs:
        mode = data.get("inputsMode", "concat")
        if mode == "json":
            joined = "\n# 입력(JSON)\n" + json.dumps(inputs, ensure_ascii=False)
        elif mode == "first":
            joined = "\n# 입력\n" + (inputs[0] if inputs else "")
        else:
            joined = "\n# 입력\n" + "\n---\n".join(inputs)
        prompt_parts.append(joined)
    prompt = "\n\n".join(p for p in prompt_parts if p).strip() or "."

    claude_bin = shutil.which("claude")
    if not claude_bin:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": "claude CLI not found in PATH"}

    cwd_raw = data.get("cwd") or str(Path.home())
    cwd_safe = _under_home(cwd_raw) or str(Path.home())

    # resume 대상 session_id 결정:
    # 1) 노드에 명시된 resumeSessionId 최우선
    # 2) continueFromPrev 가 켜졌고 이전 노드 중 session_id 를 가진 것이 있으면 그걸 사용
    resume_id = (data.get("resumeSessionId") or "").strip()
    if not resume_id and data.get("continueFromPrev"):
        for sid in prev_session_ids:
            if sid:
                resume_id = sid
                break

    cmd = [claude_bin, "-p", prompt, "--output-format", "json"]
    sys_prompt = (data.get("systemPrompt") or "").strip()
    if sys_prompt:
        cmd += ["--system-prompt", sys_prompt]
    app_prompt = (data.get("appendSystemPrompt") or "").strip()
    if app_prompt:
        cmd += ["--append-system-prompt", app_prompt]
    allowed = (data.get("allowedTools") or "").strip()
    if allowed:
        cmd += ["--allowed-tools", allowed]
    disallowed = (data.get("disallowedTools") or "").strip()
    if disallowed:
        cmd += ["--disallowed-tools", disallowed]
    if resume_id:
        cmd += ["--resume", resume_id]

    try:
        r = subprocess.run(
            cmd, cwd=cwd_safe, capture_output=True, text=True,
            timeout=_DEFAULT_NODE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"timeout after {_DEFAULT_NODE_TIMEOUT}s"}
    except Exception as e:
        return {"status": "err", "output": "", "durationMs": _elapsed(), "error": str(e)}

    if r.returncode != 0:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": (r.stderr or "").strip()[:1000] or f"exit {r.returncode}"}

    stdout = r.stdout or ""
    output = stdout
    session_id = ""
    try:
        parsed = json.loads(stdout)
        if isinstance(parsed, dict):
            output = parsed.get("result") or parsed.get("content") or stdout
            session_id = (parsed.get("session_id") or parsed.get("sessionId") or "")
    except Exception:
        pass
    return {"status": "ok", "output": output, "sessionId": session_id, "durationMs": _elapsed()}


def _parse_hhmm(s: str) -> Optional[tuple[int, int]]:
    m = _TIME_RE.match(s or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def _minutes_now_local() -> int:
    from datetime import datetime as _dt
    n = _dt.now()
    return n.hour * 60 + n.minute


def _in_schedule(start_s: str, end_s: str) -> bool:
    a = _parse_hhmm(start_s); b = _parse_hhmm(end_s)
    if not a or not b:
        return True  # 잘못된 설정이면 항상 OK
    sm = a[0]*60 + a[1]; em = b[0]*60 + b[1]
    now = _minutes_now_local()
    if sm <= em:
        return sm <= now <= em
    # wrap over midnight
    return now >= sm or now <= em


def _find_feedback_target(nodes: list[dict], edges: list[dict]) -> str:
    """feedbackNodeId 가 지정되지 않았을 때 자동 탐지:
    start 바로 다음의 session/subagent 노드 id 반환. 없으면 첫 session 노드.
    """
    starts = [n["id"] for n in nodes if n.get("type") == "start"]
    if starts:
        after_start = {e["to"] for e in edges if e["from"] in starts}
        for n in nodes:
            if n["id"] in after_start and n.get("type") in ("session", "subagent"):
                return n["id"]
    for n in nodes:
        if n.get("type") in ("session", "subagent"):
            return n["id"]
    return ""


def _run_one_iteration(wf: dict, runId: str, iter_idx: int,
                       extra_inputs: dict[str, str] | None = None,
                       total_t0: float | None = None) -> tuple[bool, dict, str]:
    """한 번의 DAG 실행. (ok, results, final_output) 반환.

    - extra_inputs[nid] 가 있으면 해당 노드의 첫 input 으로 prepend (피드백 주입)
    - runs[runId].nodeResults 는 이 iteration 결과로 덮어씀
    - runs[runId].iteration 에 현재 iter_idx 기록
    """
    nodes = wf.get("nodes", [])
    edges = wf.get("edges", [])
    order = _topological_order(nodes, edges)
    node_by_id = {n["id"]: n for n in nodes}
    inputs_map: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for e in edges:
        inputs_map[e["to"]].append((e["from"], e["fromPort"]))
    disabled: set[str] = set()
    results: dict[str, dict] = {}
    extra = extra_inputs or {}
    if total_t0 is None:
        total_t0 = time.time()

    # 이 iteration 시작 시 nodeResults 초기화 + iter_idx 기록
    with _LOCK:
        s = _load_all()
        if runId in s["runs"]:
            s["runs"][runId]["nodeResults"] = {}
            s["runs"][runId]["iteration"] = iter_idx
            _dump_all(s)

    for nid in order:
        if nid in disabled:
            with _LOCK:
                s = _load_all()
                if runId in s["runs"]:
                    s["runs"][runId]["nodeResults"][nid] = {"status": "skipped"}
                    _dump_all(s)
            continue
        # 입력 수집
        in_items = inputs_map.get(nid, [])
        input_strs: list[str] = []
        for (src_id, src_port) in in_items:
            src = results.get(src_id)
            if src and src.get("status") == "ok":
                if "_branch" in src and src["_branch"] != src_port:
                    continue
                input_strs.append(src.get("output") or "")
        # 반복 피드백 주입 — 해당 노드에 extra_inputs 가 있으면 맨 앞에 prepend
        if extra.get(nid):
            input_strs.insert(0, extra[nid])
        # 전체 timeout
        if time.time() - total_t0 > _DEFAULT_TOTAL_TIMEOUT:
            with _LOCK:
                s = _load_all()
                if runId in s["runs"]:
                    s["runs"][runId]["status"] = "err"
                    s["runs"][runId]["error"] = "total workflow timeout"
                    s["runs"][runId]["finishedAt"] = int(time.time()*1000)
                    _dump_all(s)
            return (False, results, "")
        # 진행 상황: running
        with _LOCK:
            s = _load_all()
            if runId in s["runs"]:
                s["runs"][runId]["currentNodeId"] = nid
                s["runs"][runId]["nodeResults"][nid] = {"status": "running"}
                _dump_all(s)
        # 실행
        prev_sids = []
        for (src_id, _) in in_items:
            src = results.get(src_id)
            if src and src.get("sessionId"):
                prev_sids.append(src["sessionId"])
        node = node_by_id[nid]
        res = _execute_node(node, input_strs, prev_sids)
        results[nid] = res
        if node.get("type") == "branch" and "_branch" in res:
            active = res["_branch"]
            for e in edges:
                if e["from"] == nid and e["fromPort"] != active:
                    disabled.add(e["to"])
        if res.get("status") == "err":
            with _LOCK:
                s = _load_all()
                if runId in s["runs"]:
                    s["runs"][runId]["nodeResults"][nid] = {
                        "status": "err",
                        "error": res.get("error", ""),
                        "durationMs": res.get("durationMs", 0),
                    }
                    s["runs"][runId]["status"] = "err"
                    s["runs"][runId]["error"] = f"node {nid}: {res.get('error','')}"
                    s["runs"][runId]["finishedAt"] = int(time.time()*1000)
                    _dump_all(s)
            return (False, results, "")
        # 성공 기록
        with _LOCK:
            s = _load_all()
            if runId in s["runs"]:
                s["runs"][runId]["nodeResults"][nid] = {
                    "status": "ok",
                    "output": (res.get("output") or "")[:4000],
                    "sessionId": res.get("sessionId") or "",
                    "durationMs": res.get("durationMs", 0),
                }
                _dump_all(s)

    # iteration 최종 output 찾기: 마지막 output 노드 → 없으면 DAG 마지막 노드
    final_output = ""
    for n in reversed(nodes):
        if n.get("type") == "output":
            r = results.get(n["id"])
            if r and r.get("output"):
                final_output = r["output"]; break
    if not final_output:
        for nid_rev in reversed(order):
            r = results.get(nid_rev)
            if r and r.get("output"):
                final_output = r["output"]; break
    return (True, results, final_output)


def _run_workflow_background(wfId: str, runId: str) -> None:
    """repeat 설정에 따라 iteration 을 반복 실행."""
    try:
        store = _load_all()
        wf = store["workflows"].get(wfId)
        if not wf:
            with _LOCK:
                s = _load_all()
                if runId in s["runs"]:
                    s["runs"][runId]["status"] = "err"
                    s["runs"][runId]["error"] = "workflow not found"
                    s["runs"][runId]["finishedAt"] = int(time.time()*1000)
                    _dump_all(s)
            return

        cyc = _check_dag(wf.get("nodes", []), wf.get("edges", []))
        if cyc:
            with _LOCK:
                s = _load_all()
                if runId in s["runs"]:
                    s["runs"][runId]["status"] = "err"
                    s["runs"][runId]["error"] = cyc[0]
                    s["runs"][runId]["finishedAt"] = int(time.time()*1000)
                    _dump_all(s)
            return

        repeat = wf.get("repeat") or {"enabled": False}
        enabled = bool(repeat.get("enabled"))
        max_iter = max(1, int(repeat.get("maxIterations") or 1)) if enabled else 1
        interval = int(repeat.get("intervalSeconds") or 0) if enabled else 0
        schedule_on = bool(repeat.get("scheduleEnabled")) if enabled else False
        sch_start = repeat.get("scheduleStart") or ""
        sch_end   = repeat.get("scheduleEnd") or ""
        fb_note   = (repeat.get("feedbackNote") or "").strip()
        fb_nid    = (repeat.get("feedbackNodeId") or "").strip() \
                    or _find_feedback_target(wf.get("nodes", []), wf.get("edges", []))

        total_t0 = time.time()
        prev_output = ""

        for it in range(max_iter):
            # 스케줄 모드: 시간대 밖이면 최대 10분 간격으로 대기 (최대 총 12시간)
            if schedule_on and not _in_schedule(sch_start, sch_end):
                waited = 0
                while waited < 12 * 3600 and not _in_schedule(sch_start, sch_end):
                    time.sleep(60); waited += 60
                    # 실행 중단 요청 체크 (future: status 가 cancelled 로 바뀌면 탈출)

            # 피드백 주입: iteration > 0 이고 feedbackNodeId 가 설정되고 prev_output 이 있으면
            extra = {}
            if it > 0 and fb_nid and prev_output:
                extra[fb_nid] = f"# 이전 반복 결과\n{prev_output}\n\n# 추가 지시\n{fb_note or '(추가 지시 없음)'}"

            ok, _results, final_out = _run_one_iteration(wf, runId, it, extra, total_t0)
            if not ok:
                return  # 실패 시 _run_one_iteration 이 이미 status=err 기록
            prev_output = final_out

            if it + 1 < max_iter and interval > 0:
                time.sleep(interval)

        # 전체 완료
        with _LOCK:
            s = _load_all()
            if runId in s["runs"]:
                s["runs"][runId]["status"] = "ok"
                s["runs"][runId]["finishedAt"] = int(time.time()*1000)
                s["runs"][runId]["currentNodeId"] = None
                _dump_all(s)
    except Exception as e:
        log.exception("workflow run failed: %s", e)
        with _LOCK:
            s = _load_all()
            if runId in s["runs"]:
                s["runs"][runId]["status"] = "err"
                s["runs"][runId]["error"] = f"internal: {e}"
                s["runs"][runId]["finishedAt"] = int(time.time()*1000)
                _dump_all(s)


def api_workflow_run(body: dict) -> dict:
    """워크플로우를 백그라운드 스레드로 실행 시작. runId 를 즉시 반환."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    wfId = body.get("id")
    if not (isinstance(wfId, str) and _WF_ID_RE.match(wfId)):
        return {"ok": False, "error": "invalid id"}
    with _LOCK:
        store = _load_all()
        wf = store["workflows"].get(wfId)
        if not wf:
            return {"ok": False, "error": "not found"}
        cyc = _check_dag(wf.get("nodes", []), wf.get("edges", []))
        if cyc:
            return {"ok": False, "error": cyc[0]}
        runId = _new_run_id()
        store["runs"][runId] = {
            "id": runId,
            "workflowId": wfId,
            "status": "running",
            "startedAt": int(time.time()*1000),
            "finishedAt": 0,
            "currentNodeId": None,
            "nodeResults": {},
            "iteration": 0,
            "error": None,
        }
        _dump_all(store)
    # 백그라운드 시작
    th = threading.Thread(target=_run_workflow_background, args=(wfId, runId), daemon=True)
    th.start()
    return {"ok": True, "runId": runId, "workflowId": wfId}


def api_workflow_run_status(query: dict) -> dict:
    """GET /api/workflows/run-status?runId=... — 단일 run 스냅샷."""
    rid = None
    if isinstance(query, dict):
        v = query.get("runId")
        if isinstance(v, list) and v:
            rid = v[0]
        elif isinstance(v, str):
            rid = v
    if not (isinstance(rid, str) and _RUN_ID_RE.match(rid)):
        return {"ok": False, "error": "invalid runId"}
    return _run_status_snapshot(rid)


_TPL_ID_RE = re.compile(r"^tpl-[0-9]{10,14}-[a-z0-9]{3,6}$")


def _new_tpl_id() -> str:
    return f"tpl-{int(time.time()*1000)}-{uuid.uuid4().hex[:4]}"


def api_workflow_templates_list(query: dict | None = None) -> dict:
    store = _load_all()
    out = []
    for tid, tpl in (store.get("customTemplates") or {}).items():
        out.append({
            "id": tid,
            "name": tpl.get("name", "Untitled"),
            "description": tpl.get("description", ""),
            "icon": tpl.get("icon") or "💾",
            "nodeCount": len(tpl.get("nodes") or []),
            "edgeCount": len(tpl.get("edges") or []),
            "createdAt": tpl.get("createdAt", 0),
        })
    out.sort(key=lambda x: x["createdAt"], reverse=True)
    return {"ok": True, "templates": out}


def api_workflow_template_save(body: dict) -> dict:
    """현재 워크플로우 구조를 커스텀 템플릿으로 저장.

    body: { name, description?, icon?, nodes, edges, viewport? }
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    wf_clean = _sanitize_workflow(body)
    if wf_clean is None:
        return {"ok": False, "error": "invalid workflow"}
    name = (body.get("name") or "").strip() or "Untitled"
    now = int(time.time() * 1000)
    with _LOCK:
        store = _load_all()
        raw_id = body.get("id")
        is_new = not (isinstance(raw_id, str) and _TPL_ID_RE.match(raw_id) and raw_id in (store.get("customTemplates") or {}))
        tid = raw_id if not is_new else _new_tpl_id()
        tpl = {
            "id": tid,
            "name": _clamp_str(name, 120),
            "description": _clamp_str(body.get("description"), 2000),
            "icon": _clamp_str(body.get("icon"), 8) or "💾",
            "nodes": wf_clean["nodes"],
            "edges": wf_clean["edges"],
            "viewport": wf_clean["viewport"],
            "createdAt": (store.get("customTemplates", {}).get(tid) or {}).get("createdAt") or now,
            "updatedAt": now,
        }
        store.setdefault("customTemplates", {})[tid] = tpl
        _dump_all(store)
    return {"ok": True, "id": tid, "created": is_new}


def api_workflow_template_delete(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    tid = body.get("id")
    if not (isinstance(tid, str) and _TPL_ID_RE.match(tid)):
        return {"ok": False, "error": "invalid id"}
    with _LOCK:
        store = _load_all()
        if tid not in (store.get("customTemplates") or {}):
            return {"ok": False, "error": "not found"}
        del store["customTemplates"][tid]
        _dump_all(store)
    return {"ok": True, "id": tid}


def api_workflow_template_get(tid: str) -> dict:
    if not (isinstance(tid, str) and _TPL_ID_RE.match(tid)):
        return {"ok": False, "error": "invalid id"}
    store = _load_all()
    tpl = (store.get("customTemplates") or {}).get(tid)
    if not tpl:
        return {"ok": False, "error": "not found"}
    return {"ok": True, "template": tpl}


def api_workflow_runs_list(query: dict) -> dict:
    """GET /api/workflows/runs?wfId=... — 해당 워크플로우의 runs 리스트 (최신순).

    요약 필드만 반환. 상세는 run-status 로 재조회.
    """
    wfId = None
    if isinstance(query, dict):
        v = query.get("wfId")
        if isinstance(v, list) and v:
            wfId = v[0]
        elif isinstance(v, str):
            wfId = v
    if not (isinstance(wfId, str) and _WF_ID_RE.match(wfId)):
        return {"ok": False, "error": "invalid wfId"}
    store = _load_all()
    out = []
    for rid, r in (store.get("runs") or {}).items():
        if r.get("workflowId") != wfId:
            continue
        out.append({
            "id": rid,
            "status": r.get("status"),
            "startedAt": r.get("startedAt", 0),
            "finishedAt": r.get("finishedAt", 0),
            "durationMs": max(0, (r.get("finishedAt") or 0) - (r.get("startedAt") or 0)),
            "nodeCount": len(r.get("nodeResults") or {}),
            "error": r.get("error"),
        })
    out.sort(key=lambda x: x["startedAt"], reverse=True)
    return {"ok": True, "runs": out[:50]}  # 최근 50개 제한
