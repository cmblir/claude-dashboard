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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

from .config import WORKFLOWS_PATH
from .db import _db, _db_init
from .logger import log
from .utils import _safe_read, _safe_write


# ───────── 상수 ─────────

_NODE_TYPES = {"start", "session", "subagent", "aggregate", "branch", "output",
               "http", "transform", "variable", "subworkflow", "embedding"}
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
    elif ntype == "http":
        out["data"] = {
            "url": _clamp_str(d.get("url"), 2000),
            "method": _clamp_str(d.get("method"), 10) or "GET",
            "headers": d.get("headers") if isinstance(d.get("headers"), dict) else {},
            "body": _clamp_str(d.get("body"), 8000),
            "extractPath": _clamp_str(d.get("extractPath"), 200),
        }
    elif ntype == "transform":
        out["data"] = {
            "transformType": _clamp_str(d.get("transformType"), 30) or "template",
            "template": _clamp_str(d.get("template"), 4000),
            "jsonPath": _clamp_str(d.get("jsonPath"), 200),
            "regexPattern": _clamp_str(d.get("regexPattern"), 500),
            "regexReplacement": _clamp_str(d.get("regexReplacement"), 500),
            "separator": _clamp_str(d.get("separator"), 20) or "\n",
        }
    elif ntype == "variable":
        out["data"] = {
            "varName": _clamp_str(d.get("varName"), 60) or "var",
            "defaultValue": _clamp_str(d.get("defaultValue"), 4000),
        }
    elif ntype == "subworkflow":
        out["data"] = {
            "workflowId": _clamp_str(d.get("workflowId"), 60),
            "passInput": bool(d.get("passInput", True)),
        }
    elif ntype == "embedding":
        out["data"] = {
            "provider": _clamp_str(d.get("provider"), 60) or "ollama-api",
            "model": _clamp_str(d.get("model"), 80) or "bge-m3",
            "outputFormat": d.get("outputFormat") if d.get("outputFormat") in ("json", "dimensions", "raw") else "json",
        }
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


def _topological_levels(nodes: list[dict], edges: list[dict]) -> list[list[str]]:
    """Kahn's 알고리즘 level-based 변형 — 같은 level 의 노드들은 병렬 실행 가능.

    반환: [[level0_ids], [level1_ids], ...] 각 level 내 노드는 서로 의존 없음.
    """
    ids = [n["id"] for n in nodes]
    adj: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = {nid: 0 for nid in ids}
    for e in edges:
        if e["from"] in indeg and e["to"] in indeg:
            adj[e["from"]].append(e["to"])
            indeg[e["to"]] += 1
    q = deque([nid for nid in ids if indeg[nid] == 0])
    levels: list[list[str]] = []
    while q:
        current_level = list(q)
        levels.append(current_level)
        next_q: deque = deque()
        for u in current_level:
            for v in adj[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    next_q.append(v)
        q = next_q
    return levels


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

    멀티 프로바이더: assignee 필드가 "provider:model" 형태면 해당 프로바이더로 실행.
    예: "claude:opus", "openai:gpt-4.1", "ollama:llama3.1", "gemini:2.5-pro", "codex:o4-mini"
    빈 값이거나 기존 형태(opus-4.7 등)면 Claude CLI 로 실행 (완전 호환).

    반환: {status:"ok|err", output:str, sessionId:str, durationMs:int, error?:str, provider?:str}
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

    # ── HTTP 노드 — 외부 API 호출 ──
    if ntype == "http":
        return _execute_http_node(data, inputs, _elapsed)

    # ── Transform 노드 — 텍스트/JSON 변환 ──
    if ntype == "transform":
        return _execute_transform_node(data, inputs, _elapsed)

    # ── Variable 노드 — 변수 저장/참조 ──
    if ntype == "variable":
        return _execute_variable_node(data, inputs, _elapsed)

    # ── Embedding 노드 — 텍스트 임베딩 생성 ──
    if ntype == "embedding":
        return _execute_embedding_node(data, inputs, _elapsed)

    # ── Sub-workflow 노드 — 다른 워크플로우 호출 ──
    if ntype == "subworkflow":
        return _execute_subworkflow_node(data, inputs, _elapsed)

    # ── session / subagent — 멀티 프로바이더 실행 ──
    prompt_parts = []
    if data.get("subject"):
        prompt_parts.append(data["subject"])
    if data.get("description"):
        prompt_parts.append(data["description"])
    if data.get("agentRole") and not data.get("systemPrompt"):
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

    cwd_raw = data.get("cwd") or str(Path.home())
    cwd_safe = _under_home(cwd_raw) or str(Path.home())

    sys_prompt = (data.get("systemPrompt") or "").strip()
    assignee = (data.get("assignee") or "").strip()

    # resume 대상 session_id 결정
    resume_id = (data.get("resumeSessionId") or "").strip()
    if not resume_id and data.get("continueFromPrev"):
        for sid in prev_session_ids:
            if sid:
                resume_id = sid
                break

    # ── 프로바이더 결정: assignee 에 ':' 가 있으면 멀티 프로바이더 ──
    # 기존 호환: 빈 값이거나 "opus-4.7" 같은 Claude alias 는 그대로 Claude CLI
    is_multi_provider = ":" in assignee and not assignee.startswith("claude-")

    # Claude CLI 전용 옵션 (다른 프로바이더에서는 extra 로 전달)
    extra = {
        "appendSystemPrompt": (data.get("appendSystemPrompt") or "").strip(),
        "allowedTools": (data.get("allowedTools") or "").strip(),
        "disallowedTools": (data.get("disallowedTools") or "").strip(),
        "resumeSessionId": resume_id,
    }

    # 멀티 프로바이더 실행
    try:
        from .ai_providers import execute_with_assignee
        resp = execute_with_assignee(
            assignee or "claude-cli",  # 빈 값이면 기존과 동일하게 Claude CLI
            prompt,
            system_prompt=sys_prompt,
            cwd=cwd_safe,
            timeout=_DEFAULT_NODE_TIMEOUT,
            extra=extra,
            fallback=True,
        )
        return {
            "status": resp.status,
            "output": resp.output,
            "sessionId": resp.session_id,
            "durationMs": resp.duration_ms or _elapsed(),
            "error": resp.error if resp.status == "err" else "",
            "provider": resp.provider,
            "model": resp.model,
            "tokensIn": resp.tokens_in,
            "tokensOut": resp.tokens_out,
            "costUsd": resp.cost_usd,
        }
    except Exception as e:
        log.exception("execute_with_assignee failed: %s", e)
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"provider execution failed: {e}", "sessionId": ""}


def _execute_http_node(data: dict, inputs: list[str], _elapsed) -> dict:
    """HTTP 노드 실행 — 외부 API 호출."""
    import urllib.request
    import urllib.error

    url = (data.get("url") or "").strip()
    if not url:
        return {"status": "err", "output": "", "durationMs": _elapsed(), "error": "URL required"}

    method = (data.get("method") or "GET").upper()
    headers_raw = data.get("headers") or {}
    body_template = (data.get("body") or "").strip()

    # 입력 텍스트를 body/url 에 주입
    input_text = inputs[0] if inputs else ""
    url = url.replace("{{input}}", input_text)
    body_template = body_template.replace("{{input}}", input_text)

    req_headers = {"Content-Type": "application/json"}
    if isinstance(headers_raw, dict):
        req_headers.update(headers_raw)

    req_body = body_template.encode("utf-8") if body_template and method in ("POST", "PUT", "PATCH") else None

    try:
        req = urllib.request.Request(url, data=req_body, headers=req_headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            response_text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")[:1000]
        except Exception:
            pass
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"HTTP {e.code}: {err_body}", "sessionId": ""}
    except Exception as e:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": str(e), "sessionId": ""}

    # JSON 응답이면 지정된 경로로 추출
    extract_path = (data.get("extractPath") or "").strip()
    output = response_text
    if extract_path:
        try:
            parsed = json.loads(response_text)
            for key in extract_path.split("."):
                if isinstance(parsed, dict):
                    parsed = parsed.get(key, "")
                elif isinstance(parsed, list) and key.isdigit():
                    parsed = parsed[int(key)]
            output = str(parsed) if not isinstance(parsed, str) else parsed
        except Exception:
            pass  # 추출 실패하면 원본 반환

    return {"status": "ok", "output": output, "durationMs": _elapsed(), "sessionId": ""}


def _execute_transform_node(data: dict, inputs: list[str], _elapsed) -> dict:
    """Transform 노드 — 텍스트/JSON 변환."""
    transform_type = (data.get("transformType") or "template").strip()
    template = (data.get("template") or "").strip()
    input_text = inputs[0] if inputs else ""

    if transform_type == "template":
        # 간단한 템플릿 치환: {{input}}, {{input_json}}, {{input_lines}}
        output = template.replace("{{input}}", input_text)
        output = output.replace("{{input_json}}", json.dumps(input_text, ensure_ascii=False))
        try:
            lines = input_text.strip().splitlines()
            output = output.replace("{{input_lines}}", json.dumps(lines, ensure_ascii=False))
        except Exception:
            pass
        return {"status": "ok", "output": output, "durationMs": _elapsed(), "sessionId": ""}

    if transform_type == "json_extract":
        # JSON 경로 추출
        path = (data.get("jsonPath") or "").strip()
        try:
            parsed = json.loads(input_text)
            for key in path.split("."):
                if isinstance(parsed, dict):
                    parsed = parsed.get(key, "")
                elif isinstance(parsed, list) and key.isdigit():
                    parsed = parsed[int(key)]
            output = json.dumps(parsed, ensure_ascii=False) if not isinstance(parsed, str) else parsed
        except Exception as e:
            return {"status": "err", "output": "", "durationMs": _elapsed(),
                    "error": f"JSON extract failed: {e}", "sessionId": ""}
        return {"status": "ok", "output": output, "durationMs": _elapsed(), "sessionId": ""}

    if transform_type == "regex":
        pattern = (data.get("regexPattern") or "").strip()
        replacement = data.get("regexReplacement", "")
        try:
            import re as _re
            output = _re.sub(pattern, replacement, input_text)
        except Exception as e:
            return {"status": "err", "output": "", "durationMs": _elapsed(),
                    "error": f"regex failed: {e}", "sessionId": ""}
        return {"status": "ok", "output": output, "durationMs": _elapsed(), "sessionId": ""}

    if transform_type == "concat":
        # 모든 입력을 결합
        separator = data.get("separator", "\n")
        output = separator.join(inputs)
        return {"status": "ok", "output": output, "durationMs": _elapsed(), "sessionId": ""}

    return {"status": "ok", "output": input_text, "durationMs": _elapsed(), "sessionId": ""}


def _execute_variable_node(data: dict, inputs: list[str], _elapsed) -> dict:
    """Variable 노드 — 값 저장 (출력으로 전달). 현재는 pass-through."""
    # variable 노드는 입력을 그대로 출력으로 전달하면서
    # 워크플로우 상태에 이름을 붙인다 (프론트에서 참조용)
    var_name = (data.get("varName") or "var").strip()
    value = inputs[0] if inputs else (data.get("defaultValue") or "")
    return {"status": "ok", "output": value, "durationMs": _elapsed(),
            "sessionId": "", "varName": var_name}


def _execute_embedding_node(data: dict, inputs: list[str], _elapsed) -> dict:
    """Embedding 노드 — 텍스트를 벡터로 변환.

    data.provider : "ollama-api", "openai-api" 등 (embed capability 필요)
    data.model    : "bge-m3", "text-embedding-3-small" 등
    data.outputFormat : "json" (벡터 JSON), "dimensions" (차원 수만), "raw" (전체)
    """
    provider_id = (data.get("provider") or "ollama-api").strip()
    model = (data.get("model") or "bge-m3").strip()
    output_fmt = data.get("outputFormat", "json")

    texts = [t for t in inputs if t.strip()] if inputs else []
    if not texts:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": "embedding input is empty", "sessionId": ""}

    try:
        from .ai_providers import get_registry
        reg = get_registry()
        p = reg.get(provider_id)
        if not p:
            return {"status": "err", "output": "", "durationMs": _elapsed(),
                    "error": f"provider not found: {provider_id}", "sessionId": ""}
        if not p.supports("embed"):
            return {"status": "err", "output": "", "durationMs": _elapsed(),
                    "error": f"provider '{provider_id}' does not support embeddings", "sessionId": ""}

        resp = p.embed(texts, model=model)
        if resp.status != "ok":
            return {"status": "err", "output": "", "durationMs": _elapsed(),
                    "error": resp.error, "sessionId": ""}

        if output_fmt == "dimensions":
            output = json.dumps({"dimensions": resp.dimensions, "count": len(resp.embeddings)})
        elif output_fmt == "raw":
            output = json.dumps(resp.to_dict(), ensure_ascii=False)
        else:  # json
            output = json.dumps({
                "model": resp.model,
                "dimensions": resp.dimensions,
                "count": len(resp.embeddings),
                "embeddings": resp.embeddings,
            }, ensure_ascii=False)

        return {
            "status": "ok", "output": output, "durationMs": resp.duration_ms or _elapsed(),
            "sessionId": "", "provider": resp.provider, "model": resp.model,
            "tokensIn": resp.tokens_used, "tokensOut": 0,
        }
    except Exception as e:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"embedding failed: {e}", "sessionId": ""}


def _execute_subworkflow_node(data: dict, inputs: list[str], _elapsed) -> dict:
    """Sub-workflow 노드 — 다른 워크플로우를 동기 실행하고 결과를 반환.

    data.workflowId : 실행할 워크플로우 ID
    data.passInput  : True 이면 이전 노드 출력을 start 노드에 주입
    """
    wf_id = (data.get("workflowId") or "").strip()
    if not wf_id:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": "workflowId required", "sessionId": ""}

    store = _load_all()
    sub_wf = store["workflows"].get(wf_id)
    if not sub_wf:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"workflow not found: {wf_id}", "sessionId": ""}

    cyc = _check_dag(sub_wf.get("nodes", []), sub_wf.get("edges", []))
    if cyc:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"sub-workflow has cycle: {cyc[0]}", "sessionId": ""}

    # 입력을 start 노드의 다음 노드에 피드백으로 전달
    extra_inputs = {}
    if data.get("passInput", True) and inputs:
        target_nid = _find_feedback_target(
            sub_wf.get("nodes", []), sub_wf.get("edges", []))
        if target_nid:
            extra_inputs[target_nid] = "\n---\n".join(inputs)

    # 동기 실행 (별도 runId 없이 inline)
    sub_run_id = _new_run_id()
    with _LOCK:
        store = _load_all()
        store["runs"][sub_run_id] = {
            "id": sub_run_id, "workflowId": wf_id,
            "status": "running", "startedAt": int(time.time() * 1000),
            "finishedAt": 0, "currentNodeId": None,
            "nodeResults": {}, "iteration": 0, "error": None,
            "isSubworkflow": True,
        }
        _dump_all(store)

    ok, _results, final_out = _run_one_iteration(
        sub_wf, sub_run_id, 0, extra_inputs)

    # 완료 기록
    with _LOCK:
        store = _load_all()
        if sub_run_id in store["runs"]:
            store["runs"][sub_run_id]["status"] = "ok" if ok else "err"
            store["runs"][sub_run_id]["finishedAt"] = int(time.time() * 1000)
            _dump_all(store)

    if not ok:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"sub-workflow failed", "sessionId": ""}

    return {"status": "ok", "output": final_out, "durationMs": _elapsed(),
            "sessionId": "", "subRunId": sub_run_id}


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


_MAX_PARALLEL_WORKERS = int(os.environ.get("WORKFLOW_MAX_PARALLEL", "4"))


def _record_workflow_cost(run_id: str, workflow_id: str, node_id: str, res: dict) -> None:
    """워크플로우 노드 실행 비용을 DB에 기록."""
    provider = res.get("provider", "")
    model = res.get("model", "")
    if not provider and not model:
        return  # start/aggregate/branch 등 AI 호출 없는 노드는 스킵
    try:
        _db_init()
        with _db() as c:
            c.execute(
                """INSERT INTO workflow_costs
                   (run_id, workflow_id, node_id, provider, model,
                    tokens_in, tokens_out, tokens_total, cost_usd,
                    duration_ms, ts, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, workflow_id, node_id, provider, model,
                 res.get("tokensIn", 0), res.get("tokensOut", 0),
                 res.get("tokensIn", 0) + res.get("tokensOut", 0),
                 res.get("costUsd", 0.0),
                 res.get("durationMs", 0),
                 int(time.time() * 1000),
                 res.get("status", "ok")),
            )
    except Exception as e:
        log.warning("workflow cost record failed: %s", e)


def _run_one_iteration(wf: dict, runId: str, iter_idx: int,
                       extra_inputs: dict[str, str] | None = None,
                       total_t0: float | None = None) -> tuple[bool, dict, str]:
    """한 번의 DAG 실행 — **level-based 병렬 실행**.

    같은 topological level 의 노드들은 서로 의존이 없으므로 ThreadPoolExecutor 로
    동시에 실행한다. 순차 실행 대비 분기형 워크플로우에서 큰 속도 향상.

    - extra_inputs[nid] 가 있으면 해당 노드의 첫 input 으로 prepend (피드백 주입)
    - runs[runId].nodeResults 는 이 iteration 결과로 덮어씀
    - runs[runId].iteration 에 현재 iter_idx 기록
    """
    nodes = wf.get("nodes", [])
    edges = wf.get("edges", [])
    levels = _topological_levels(nodes, edges)
    order = _topological_order(nodes, edges)  # final_output 검색용
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

    def _collect_inputs(nid: str) -> list[str]:
        """노드의 입력 텍스트 수집 (이전 노드 결과에서)."""
        in_items = inputs_map.get(nid, [])
        input_strs: list[str] = []
        for (src_id, src_port) in in_items:
            src = results.get(src_id)
            if src and src.get("status") == "ok":
                if "_branch" in src and src["_branch"] != src_port:
                    continue
                input_strs.append(src.get("output") or "")
        if extra.get(nid):
            input_strs.insert(0, extra[nid])
        return input_strs

    def _collect_prev_sids(nid: str) -> list[str]:
        """이전 노드의 session_id 수집 (resume 용)."""
        in_items = inputs_map.get(nid, [])
        prev_sids = []
        for (src_id, _) in in_items:
            src = results.get(src_id)
            if src and src.get("sessionId"):
                prev_sids.append(src["sessionId"])
        return prev_sids

    def _run_single_node(nid: str) -> tuple[str, dict]:
        """단일 노드 실행 (병렬 워커에서 호출)."""
        node = node_by_id[nid]
        input_strs = _collect_inputs(nid)
        prev_sids = _collect_prev_sids(nid)
        res = _execute_node(node, input_strs, prev_sids)
        return (nid, res)

    for level in levels:
        # 전체 timeout 체크
        if time.time() - total_t0 > _DEFAULT_TOTAL_TIMEOUT:
            with _LOCK:
                s = _load_all()
                if runId in s["runs"]:
                    s["runs"][runId]["status"] = "err"
                    s["runs"][runId]["error"] = "total workflow timeout"
                    s["runs"][runId]["finishedAt"] = int(time.time()*1000)
                    _dump_all(s)
            return (False, results, "")

        # disabled 노드 제외
        active_nodes = [nid for nid in level if nid not in disabled]
        skipped_nodes = [nid for nid in level if nid in disabled]

        # skip 기록
        for nid in skipped_nodes:
            with _LOCK:
                s = _load_all()
                if runId in s["runs"]:
                    s["runs"][runId]["nodeResults"][nid] = {"status": "skipped"}
                    _dump_all(s)

        if not active_nodes:
            continue

        # 진행 상황: running 표시
        with _LOCK:
            s = _load_all()
            if runId in s["runs"]:
                for nid in active_nodes:
                    s["runs"][runId]["nodeResults"][nid] = {"status": "running"}
                s["runs"][runId]["currentNodeId"] = active_nodes[0]
                _dump_all(s)

        # ── 병렬 실행: 같은 level 의 노드들 ──
        level_results: dict[str, dict] = {}
        if len(active_nodes) == 1:
            # 단일 노드는 스레드풀 오버헤드 없이 직접 실행
            nid, res = _run_single_node(active_nodes[0])
            level_results[nid] = res
        else:
            # 여러 노드 병렬 실행
            max_w = min(_MAX_PARALLEL_WORKERS, len(active_nodes))
            with ThreadPoolExecutor(max_workers=max_w) as pool:
                futures = {pool.submit(_run_single_node, nid): nid for nid in active_nodes}
                for future in as_completed(futures):
                    try:
                        nid, res = future.result()
                        level_results[nid] = res
                    except Exception as e:
                        nid = futures[future]
                        level_results[nid] = {
                            "status": "err", "output": "", "error": str(e),
                            "durationMs": 0, "sessionId": "",
                        }

        # 결과 기록 + branch 처리
        had_error = False
        for nid, res in level_results.items():
            results[nid] = res
            node = node_by_id[nid]

            if node.get("type") == "branch" and "_branch" in res:
                active_port = res["_branch"]
                for e in edges:
                    if e["from"] == nid and e["fromPort"] != active_port:
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
                had_error = True
                break
            else:
                with _LOCK:
                    s = _load_all()
                    if runId in s["runs"]:
                        s["runs"][runId]["nodeResults"][nid] = {
                            "status": "ok",
                            "output": (res.get("output") or "")[:4000],
                            "sessionId": res.get("sessionId") or "",
                            "durationMs": res.get("durationMs", 0),
                            "provider": res.get("provider", ""),
                            "model": res.get("model", ""),
                        }
                        _dump_all(s)
                # 비용 추적 DB 기록
                _record_workflow_cost(
                    runId, wf.get("id", ""), nid, res)

        if had_error:
            return (False, results, "")

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


def handle_workflow_run_stream(handler, query: dict) -> None:
    """GET /api/workflows/run-stream?runId=... — SSE 로 실행 상태를 실시간 스트림.

    1초 간격으로 run 상태를 폴링하여 변경 사항을 SSE 로 전송.
    run 이 완료(ok/err)되면 done 이벤트 후 연결 종료.
    """
    rid = None
    if isinstance(query, dict):
        v = query.get("runId")
        if isinstance(v, list) and v:
            rid = v[0]
        elif isinstance(v, str):
            rid = v

    if not (isinstance(rid, str) and _RUN_ID_RE.match(rid)):
        handler.send_response(400)
        handler.send_header("Content-Type", "text/plain")
        handler.end_headers()
        handler.wfile.write(b"invalid runId")
        return

    # SSE 헤더
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()

    def _sse(event: str, data: str) -> bool:
        chunk = f"event: {event}\ndata: {data}\n\n"
        try:
            handler.wfile.write(chunk.encode("utf-8"))
            handler.wfile.flush()
            return True
        except Exception:
            return False

    prev_snapshot = ""
    max_polls = 1800  # 최대 30분 (1초 × 1800)

    for _ in range(max_polls):
        snap = _run_status_snapshot(rid)
        snap_json = json.dumps(snap, ensure_ascii=False)

        # 변경 있을 때만 전송 (대역폭 절약)
        if snap_json != prev_snapshot:
            if not _sse("status", snap_json):
                return  # 클라이언트 연결 끊김
            prev_snapshot = snap_json

        # 완료 체크
        run = snap.get("run") or {}
        status = run.get("status", "")
        if status in ("ok", "err"):
            _sse("done", snap_json)
            return

        time.sleep(1)

    # 타임아웃
    _sse("timeout", json.dumps({"error": "stream timeout"}))


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
