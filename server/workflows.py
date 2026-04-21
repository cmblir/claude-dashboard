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
    return {"version": 1, "workflows": {}, "runs": {}}


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
        if not isinstance(data["workflows"], dict):
            data["workflows"] = {}
        if not isinstance(data["runs"], dict):
            data["runs"] = {}
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
            "sessionRef":  {
                "mode":      _clamp_str((d.get("sessionRef") or {}).get("mode"), 20) or "spawn",
                "sessionId": _clamp_str((d.get("sessionRef") or {}).get("sessionId"), 80),
                "pid":       (d.get("sessionRef") or {}).get("pid"),
            },
            "lastRun": d.get("lastRun") if isinstance(d.get("lastRun"), dict) else {
                "status": "idle", "output": None, "durationMs": 0, "startedAt": 0
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


def _execute_node(node: dict, inputs: list[str]) -> dict:
    """단일 노드 실행. 동기. (subject/description + inputs) → stdout.

    반환: {status:"ok|err", output:str, durationMs:int, error?:str}
    """
    ntype = node["type"]
    data = node.get("data") or {}
    t0 = int(time.time() * 1000)

    def _elapsed() -> int:
        return int(time.time() * 1000) - t0

    if ntype == "start":
        return {"status": "ok", "output": "", "durationMs": _elapsed()}

    if ntype == "aggregate":
        mode = data.get("mode", "concat")
        if mode == "json":
            output = json.dumps(inputs, ensure_ascii=False)
        else:
            output = "\n---\n".join(inputs)
        return {"status": "ok", "output": output, "durationMs": _elapsed()}

    if ntype == "branch":
        cond = (data.get("condition") or "").strip().lower()
        prev = (inputs[0] if inputs else "").lower()
        # 단순 substring 매칭. 안전 위해 eval X.
        matched = bool(cond) and cond in prev
        out_port = "out_y" if matched else "out_n"
        return {
            "status": "ok", "output": prev, "durationMs": _elapsed(),
            "_branch": out_port,  # runner 가 읽어 제외 포트 처리
        }

    if ntype == "output":
        # 마지막 결과는 첫 입력을 그대로 보존 + optional export
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
        return {"status": "ok", "output": final, "durationMs": _elapsed()}

    # session / subagent — `claude -p` 호출
    prompt_parts = []
    if data.get("subject"):
        prompt_parts.append(data["subject"])
    if data.get("description"):
        prompt_parts.append(data["description"])
    if data.get("agentRole"):
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

    cmd = [claude_bin, "-p", prompt, "--output-format", "json"]
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

    # Claude CLI 는 --output-format json 시 {"result": "...", "session_id":"...", ...} 같은 구조.
    # 파싱 실패 시 stdout 전체를 output 으로.
    stdout = r.stdout or ""
    output = stdout
    try:
        parsed = json.loads(stdout)
        if isinstance(parsed, dict):
            output = parsed.get("result") or parsed.get("content") or stdout
    except Exception:
        pass
    return {"status": "ok", "output": output, "durationMs": _elapsed()}


def _run_workflow_background(wfId: str, runId: str) -> None:
    """스레드에서 돌리는 워크플로우 실행 함수. 진행 상황을 runs store 에 반영."""
    total_t0 = time.time()
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

        nodes = wf.get("nodes", [])
        edges = wf.get("edges", [])
        cyc = _check_dag(nodes, edges)
        if cyc:
            with _LOCK:
                s = _load_all()
                if runId in s["runs"]:
                    s["runs"][runId]["status"] = "err"
                    s["runs"][runId]["error"] = cyc[0]
                    s["runs"][runId]["finishedAt"] = int(time.time()*1000)
                    _dump_all(s)
            return

        order = _topological_order(nodes, edges)
        node_by_id = {n["id"]: n for n in nodes}
        # 입력 그래프: to_node → [(from_node, from_port)]
        inputs_map: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for e in edges:
            inputs_map[e["to"]].append((e["from"], e["fromPort"]))
        # branch 출력으로 인해 disable 될 downstream 집합
        disabled: set[str] = set()
        results: dict[str, dict] = {}

        for nid in order:
            if nid in disabled:
                # skip 상태 기록
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
                    # branch 의 활성 포트가 아니면 skip
                    if "_branch" in src and src["_branch"] != src_port:
                        continue
                    input_strs.append(src.get("output") or "")
            # 전체 timeout 체크
            if time.time() - total_t0 > _DEFAULT_TOTAL_TIMEOUT:
                with _LOCK:
                    s = _load_all()
                    if runId in s["runs"]:
                        s["runs"][runId]["status"] = "err"
                        s["runs"][runId]["error"] = "total workflow timeout"
                        s["runs"][runId]["finishedAt"] = int(time.time()*1000)
                        _dump_all(s)
                return
            # 진행 상황: running
            with _LOCK:
                s = _load_all()
                if runId in s["runs"]:
                    s["runs"][runId]["currentNodeId"] = nid
                    s["runs"][runId]["nodeResults"][nid] = {"status": "running"}
                    _dump_all(s)
            # 실행
            node = node_by_id[nid]
            res = _execute_node(node, input_strs)
            results[nid] = res
            # branch 의 비활성 포트로 이어진 downstream 을 disabled 에 표시
            if node.get("type") == "branch" and "_branch" in res:
                active = res["_branch"]
                for e in edges:
                    if e["from"] == nid and e["fromPort"] != active:
                        disabled.add(e["to"])
            # 실패면 중단
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
                return
            # 성공 기록
            with _LOCK:
                s = _load_all()
                if runId in s["runs"]:
                    s["runs"][runId]["nodeResults"][nid] = {
                        "status": "ok",
                        "output": (res.get("output") or "")[:4000],
                        "durationMs": res.get("durationMs", 0),
                    }
                    _dump_all(s)

        # 완료
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
