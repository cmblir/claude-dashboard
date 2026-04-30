"""n8n 스타일 워크플로우 에디터 백엔드.

- 단일 JSON 파일(`~/.claude-dashboard-workflows.json`) 에 여러 워크플로우 저장
- 각 워크플로우 = 노드(세션·서브에이전트·취합·분기·결과) + 엣지(DAG)
- Run 엔진: DAG topological sort → 각 노드별 subprocess 로 `claude -p` 실행
- 모든 I/O 는 atomic write (tmp → rename) + 화이트리스트 검증
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
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
               "http", "transform", "variable", "subworkflow", "embedding",
               "loop", "retry", "error_handler", "merge", "delay",
               # v2.34.0 — Crew pattern: interactive Slack approval gate +
               # Obsidian markdown log appender.
               "slack_approval", "obsidian_log",
               # v2.37.0 — bind a target Claude session to the Auto-Resume
               # supervisor from inside a workflow.
               "auto_resume"}
_INPUT_MODES = {"concat", "first", "json"}
_ASSIGNEES = {"opus-4.7", "sonnet-4.6", "haiku-4.5"}  # UI 선택지용; 검증 여기서는 free-form

_WF_ID_RE = re.compile(r"^wf-[0-9]{10,14}-[a-z0-9]{3,6}$")
_NODE_ID_RE = re.compile(r"^n-[A-Za-z0-9_-]{1,40}$")
_RUN_ID_RE = re.compile(r"^run-[0-9]{10,14}-[a-z0-9]{3,8}$")

_DEFAULT_NODE_TIMEOUT = int(os.environ.get("WORKFLOW_NODE_TIMEOUT", "300"))
_DEFAULT_TOTAL_TIMEOUT = int(os.environ.get("WORKFLOW_TOTAL_TIMEOUT", "1800"))

# Run 엔진용 동시성 — 서버 프로세스 안에서 run 을 돌려야 하므로 lock 필요
_LOCK = threading.Lock()

# v2.44.0 — In-memory cache of live run state. Per-node status/result updates
# during a run mutate this dict instead of rewriting the entire
# ~/.claude-dashboard-workflows.json on every transition. We persist to disk
# only at iteration boundaries, on full-run completion, and on explicit
# cancel. SSE/poll snapshots read from this cache first; on process restart
# the cache is empty (no live runs survive restart anyway), so reads
# transparently fall back to the on-disk store.
_RUNS_CACHE: dict[str, dict] = {}
_RUNS_LOCK = threading.Lock()


def _runs_cache_set(runId: str, run: dict) -> None:
    """Insert/replace the in-memory run entry."""
    with _RUNS_LOCK:
        _RUNS_CACHE[runId] = run


def _runs_cache_get(runId: str) -> Optional[dict]:
    """Return a defensive copy of the cached run entry, or None."""
    with _RUNS_LOCK:
        r = _RUNS_CACHE.get(runId)
        if r is None:
            return None
        # Shallow copy + copy nodeResults dict so callers can serialize
        # without holding the lock.
        out = dict(r)
        nr = r.get("nodeResults")
        if isinstance(nr, dict):
            out["nodeResults"] = dict(nr)
        return out


def _runs_cache_update(runId: str, mutator) -> Optional[dict]:
    """Apply `mutator(run_dict)` under _RUNS_LOCK. Returns the post-mutation
    snapshot (defensive copy) or None if runId not cached."""
    with _RUNS_LOCK:
        r = _RUNS_CACHE.get(runId)
        if r is None:
            return None
        mutator(r)
        out = dict(r)
        nr = r.get("nodeResults")
        if isinstance(nr, dict):
            out["nodeResults"] = dict(nr)
        return out


def _runs_cache_pop(runId: str) -> Optional[dict]:
    """Remove and return the cached run entry. Used after persisting on
    completion so memory is reclaimed."""
    with _RUNS_LOCK:
        return _RUNS_CACHE.pop(runId, None)


def _persist_run(runId: str) -> None:
    """Flush the cached run dict to the on-disk store under _LOCK.

    Safe to call repeatedly; no-op if the run is not in cache. We deliberately
    take _RUNS_LOCK only briefly to copy, then take _LOCK for the file I/O,
    to avoid holding both locks across a synchronous fsync.
    """
    with _RUNS_LOCK:
        cached = _RUNS_CACHE.get(runId)
        if cached is None:
            return
        snap = dict(cached)
        nr = cached.get("nodeResults")
        if isinstance(nr, dict):
            snap["nodeResults"] = dict(nr)
    with _LOCK:
        store = _load_all()
        store.setdefault("runs", {})
        store["runs"][runId] = snap
        _dump_all(store)


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


# ── Output 노드 export 경로 화이트리스트 (v2.23.0, Finding 3) ──
# ~/Downloads, ~/Documents, ~/Desktop 만 허용. symlink 탈출 방지 위해 realpath 비교.
_EXPORT_ALLOWED_DIRS = ("Downloads", "Documents", "Desktop")


def _under_allowed_export(raw_path: str) -> Optional[str]:
    """export 용 경로 화이트리스트. 허용 디렉터리 하위면 realpath, 아니면 None.

    path traversal / symlink 탈출을 모두 방지:
      1) expanduser + abspath 로 ~/ 해석
      2) realpath 로 symlink 완전 해제 (파일이 존재하지 않아도 안전하게 동작)
      3) 허용된 루트 (realpath) 와 prefix 매칭
    """
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    try:
        expanded = os.path.expanduser(raw_path.strip())
        abs_p = os.path.abspath(expanded)
        real_p = os.path.realpath(abs_p)
    except Exception:
        return None
    home = str(Path.home())
    for name in _EXPORT_ALLOWED_DIRS:
        base_real = os.path.realpath(os.path.join(home, name))
        if real_p == base_real or real_p.startswith(base_real + os.sep):
            return real_p
    return None


# ── Webhook secret (v2.23.0, Finding 2) ──
_WEBHOOK_SECRET_BYTES = 32  # 43자 안팎의 URL-safe base64


def _gen_webhook_secret() -> str:
    return secrets.token_urlsafe(_WEBHOOK_SECRET_BYTES)


def _valid_secret(raw: Any) -> bool:
    return isinstance(raw, str) and 16 <= len(raw) <= 128 and re.match(r"^[A-Za-z0-9_\-]+$", raw) is not None


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
        # v2.44.1 — multiAssignee: list of "provider:model" strings for parallel
        # fan-out. Reuses the same string clamp as `assignee`. Dedupe while
        # preserving order. Cap at 8 to mirror execute_parallel's pool size.
        raw_multi = d.get("multiAssignee")
        clean_multi: list[str] = []
        if isinstance(raw_multi, list):
            seen: set[str] = set()
            for item in raw_multi:
                if not isinstance(item, str):
                    continue
                v = _clamp_str(item, 40).strip()
                if not v or v in seen:
                    continue
                seen.add(v)
                clean_multi.append(v)
                if len(clean_multi) >= 8:
                    break
        out["data"] = {
            "subject":     _clamp_str(d.get("subject"), 200),
            "description": _clamp_str(d.get("description"), 4000),
            "assignee":    _clamp_str(d.get("assignee"), 40),
            "multiAssignee": clean_multi,
            # v2.25.0 — modelHint: assignee 가 비어있을 때 프롬프트 길이/키워드 기반
            # 자동 모델 선택. "auto" · "fast" · "deep" · "" (비활성)
            "modelHint":   (d.get("modelHint") or "") if (d.get("modelHint") or "") in ("", "auto", "fast", "deep") else "",
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
            "allowInternal": bool(d.get("allowInternal")),  # v2.22.0 SSRF 옵트인
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
    elif ntype == "loop":
        out["data"] = {
            "loopType": d.get("loopType") if d.get("loopType") in ("for_each", "while", "count") else "for_each",
            "maxIterations": max(1, min(1000, int(d.get("maxIterations") or 10))),
            "condition": _clamp_str(d.get("condition"), 400),
            "separator": _clamp_str(d.get("separator"), 20) or "\n",
        }
    elif ntype == "retry":
        out["data"] = {
            "maxRetries": max(1, min(10, int(d.get("maxRetries") or 3))),
            "backoffMs": max(0, min(60000, int(d.get("backoffMs") or 1000))),
            "backoffMultiplier": max(1.0, min(5.0, float(d.get("backoffMultiplier") or 2.0))),
            "retryOn": _clamp_str(d.get("retryOn"), 200) or "error",
        }
    elif ntype == "error_handler":
        out["data"] = {
            "onError": d.get("onError") if d.get("onError") in ("skip", "default", "route") else "skip",
            "defaultOutput": _clamp_str(d.get("defaultOutput"), 4000),
        }
    elif ntype == "merge":
        out["data"] = {
            "mergeMode": d.get("mergeMode") if d.get("mergeMode") in ("all", "any", "count") else "all",
            "requiredCount": max(1, min(20, int(d.get("requiredCount") or 1))),
            "timeout": max(0, min(3600, int(d.get("timeout") or 300))),
        }
    elif ntype == "delay":
        out["data"] = {
            "delayMs": max(0, min(300000, int(d.get("delayMs") or 1000))),
            "delayType": d.get("delayType") if d.get("delayType") in ("fixed", "random") else "fixed",
            "maxDelayMs": max(0, min(300000, int(d.get("maxDelayMs") or 5000))),
        }
    elif ntype == "slack_approval":
        # Interactive admin gate. Posts the input to a Slack channel and
        # waits for an approval reaction/reply. Falls back to a configured
        # behaviour on timeout so autonomous mode can keep flowing.
        on_timeout = d.get("onTimeout") if d.get("onTimeout") in (
            "approve", "reject", "abort", "default") else "approve"
        out["data"] = {
            "channel":         _clamp_str(d.get("channel"), 80),
            "messageTemplate": _clamp_str(d.get("messageTemplate"), 4000),
            "timeoutSeconds":  max(5, min(int(d.get("timeoutSeconds") or 300), 60 * 60 * 4)),
            "pollIntervalSeconds": max(2, min(int(d.get("pollIntervalSeconds") or 5), 60)),
            "onTimeout":       on_timeout,
            "defaultOutput":   _clamp_str(d.get("defaultOutput"), 4000),
            # When True the upstream input is appended after the template.
            "includeInput":    bool(d.get("includeInput", True)),
        }
    elif ntype == "obsidian_log":
        out["data"] = {
            "vaultPath":  _clamp_str(d.get("vaultPath"), 500),
            "project":    _clamp_str(d.get("project"), 80),
            "heading":    _clamp_str(d.get("heading"), 200),
            "tagsCsv":    _clamp_str(d.get("tagsCsv"), 200),
            # Pass-through means the input is forwarded as the output AND
            # written to disk. False writes a fixed defaultOutput instead.
            "passThrough":   bool(d.get("passThrough", True)),
            "defaultOutput": _clamp_str(d.get("defaultOutput"), 4000),
        }
    elif ntype == "auto_resume":
        # v2.37.0 — bind a Claude Code session UUID to the Auto-Resume
        # supervisor. If sessionId is empty, the upstream input is parsed
        # as a UUID. Workflow flow stays alive — the supervisor runs in
        # its own background thread.
        out["data"] = {
            "sessionId":     _clamp_str(d.get("sessionId"), 80),
            "cwd":           _clamp_str(d.get("cwd"), 500),
            "prompt":        _clamp_str(d.get("prompt"), 4000),
            "pollInterval":  max(30, min(3600, int(d.get("pollInterval") or 300))),
            "idleSeconds":   max(30, int(d.get("idleSeconds") or 90)),
            "maxAttempts":   max(1, min(60, int(d.get("maxAttempts") or 12))),
            "useContinue":   bool(d.get("useContinue")),
            "installHooks":  bool(d.get("installHooks")),
            "action":        d.get("action") if d.get("action") in ("set", "cancel") else "set",
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
        "notify":      _sanitize_notify(raw.get("notify")),  # v2.25.0 Slack/Discord
        "policy":      _sanitize_policy(raw.get("policy")),  # v2.27.0 전역 토큰 예산
    }
    return out


_FALLBACK_PROVIDERS = {"", "claude-api", "openai-api", "gemini-api", "ollama-api"}


def _sanitize_policy(raw: Any) -> dict:
    """워크플로우 전역 정책.

    필드:
    - `tokenBudgetTotal`: 누적 토큰 예산 (0=unlimited, max 1억)
    - `onBudgetExceeded`: "stop" (기본) | "warn"
    - `fallbackProvider` (v2.29.0): session 노드 실행 실패 시 재시도 프로바이더.
      `""` · `claude-api` · `openai-api` · `gemini-api` · `ollama-api` 중 하나.
    """
    if not isinstance(raw, dict):
        return {"tokenBudgetTotal": 0, "onBudgetExceeded": "stop", "fallbackProvider": ""}
    try:
        budget = int(raw.get("tokenBudgetTotal") or 0)
    except Exception:
        budget = 0
    budget = max(0, min(budget, 100_000_000))
    on_exc = raw.get("onBudgetExceeded")
    if on_exc not in ("stop", "warn"):
        on_exc = "stop"
    fb = (raw.get("fallbackProvider") or "").strip()
    if fb not in _FALLBACK_PROVIDERS:
        fb = ""
    return {
        "tokenBudgetTotal": budget,
        "onBudgetExceeded": on_exc,
        "fallbackProvider": fb,
    }


def _sanitize_notify(raw: Any) -> dict:
    """알림 webhook URL sanitize. Slack/Discord 화이트리스트 호스트만 허용."""
    if not isinstance(raw, dict):
        return {"slack": "", "discord": ""}
    def _clean(url: str) -> str:
        url = (url or "").strip()
        if not url:
            return ""
        # 길이/형태 제한
        if len(url) > 400 or not url.startswith("https://"):
            return ""
        return url
    return {
        "slack":   _clean(raw.get("slack") or ""),
        "discord": _clean(raw.get("discord") or ""),
    }


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


# v2.44.0 — memoize topological sort. The same workflow's DAG is sorted on
# every iteration of every run; for repeating workflows this is wasted work.
# Cache key is graph-shape based, so any node/edge mutation invalidates
# automatically. Soft cap at 256 with FIFO eviction to bound memory.
_TOPO_CACHE_MAX = 256
_TOPO_ORDER_CACHE: dict[tuple, tuple[str, ...]] = {}
_TOPO_LEVELS_CACHE: dict[tuple, tuple[tuple[str, ...], ...]] = {}
_TOPO_CACHE_LOCK = threading.Lock()


def _topo_cache_key(nodes: list[dict], edges: list[dict]) -> tuple:
    return (
        tuple(sorted(n["id"] for n in nodes)),
        tuple(sorted((e["from"], e["to"]) for e in edges)),
    )


def _topo_cache_evict(cache: dict) -> None:
    # FIFO: drop oldest insertion(s) until under the cap.
    while len(cache) > _TOPO_CACHE_MAX:
        try:
            first_key = next(iter(cache))
        except StopIteration:
            return
        cache.pop(first_key, None)


def _topological_order(nodes: list[dict], edges: list[dict]) -> list[str]:
    """사이클 없다고 가정. Kahn's 결과 순서 반환."""
    key = _topo_cache_key(nodes, edges)
    with _TOPO_CACHE_LOCK:
        cached = _TOPO_ORDER_CACHE.get(key)
    if cached is not None:
        return list(cached)
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
    with _TOPO_CACHE_LOCK:
        _TOPO_ORDER_CACHE[key] = tuple(order)
        _topo_cache_evict(_TOPO_ORDER_CACHE)
    return order


def _topological_levels(nodes: list[dict], edges: list[dict]) -> list[list[str]]:
    """Kahn's 알고리즘 level-based 변형 — 같은 level 의 노드들은 병렬 실행 가능.

    반환: [[level0_ids], [level1_ids], ...] 각 level 내 노드는 서로 의존 없음.
    """
    key = _topo_cache_key(nodes, edges)
    with _TOPO_CACHE_LOCK:
        cached = _TOPO_LEVELS_CACHE.get(key)
    if cached is not None:
        return [list(level) for level in cached]
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
    with _TOPO_CACHE_LOCK:
        _TOPO_LEVELS_CACHE[key] = tuple(tuple(lv) for lv in levels)
        _topo_cache_evict(_TOPO_LEVELS_CACHE)
    return levels


# ───────── ID 생성 ─────────

def _new_wf_id() -> str:
    return f"wf-{int(time.time()*1000)}-{uuid.uuid4().hex[:4]}"


def _new_run_id() -> str:
    return f"run-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"


# ───────── API: CRUD ─────────

def api_workflows_list(query: dict | None = None) -> dict:
    store = _load_all()
    # v2.42.1 — group runs by wfId so each list card can surface the latest 3
    # statuses + a "running" badge inline. Without this the user has to open
    # the workflow into the canvas just to see whether it last passed/failed.
    runs_by_wf: dict[str, list[dict]] = {}
    for rid, r in (store.get("runs") or {}).items():
        wid = r.get("wfId") or ""
        if not wid:
            continue
        runs_by_wf.setdefault(wid, []).append(r)
    out = []
    for wfId, wf in store["workflows"].items():
        runs = runs_by_wf.get(wfId, [])
        runs.sort(key=lambda x: x.get("startedAt") or 0, reverse=True)
        last_runs = []
        running_count = 0
        for r in runs[:3]:
            if r.get("status") == "running":
                running_count += 1
            last_runs.append({
                "runId":      r.get("id") or r.get("runId") or "",
                "status":     r.get("status") or "",
                "startedAt":  r.get("startedAt") or 0,
                "finishedAt": r.get("finishedAt") or 0,
                "durationMs": (r.get("finishedAt") or 0) - (r.get("startedAt") or 0)
                              if r.get("finishedAt") else 0,
                "currentNodeId": r.get("currentNodeId") or "",
                "error":      (r.get("error") or "")[:200],
            })
        active_run_id = ""
        for r in runs:
            if r.get("status") == "running":
                active_run_id = r.get("id") or r.get("runId") or ""
                break
        out.append({
            "id": wfId,
            "name": wf.get("name", "Untitled"),
            "description": wf.get("description", ""),
            "nodeCount": len(wf.get("nodes", [])),
            "edgeCount": len(wf.get("edges", [])),
            "createdAt": wf.get("createdAt", 0),
            "updatedAt": wf.get("updatedAt", 0),
            "lastRuns":     last_runs,
            "runningCount": running_count,
            "activeRunId":  active_run_id,
            "totalRuns":    len(runs),
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
        # webhookSecret 은 별도 API 로만 관리 — 저장 요청으로는 변경 불가, 기존값 보존만
        prev_secret = (store["workflows"].get(wfId) or {}).get("webhookSecret") or ""
        wf_clean["webhookSecret"] = prev_secret
        # ── 버전 히스토리 보관 (최근 20개) ──
        if not is_new and wfId in store["workflows"]:
            prev = store["workflows"][wfId]
            history = store.setdefault("history", {}).setdefault(wfId, [])
            history.append({
                "savedAt": now,
                "name": prev.get("name", ""),
                "nodeCount": len(prev.get("nodes", [])),
                "edgeCount": len(prev.get("edges", [])),
                "snapshot": {k: prev[k] for k in ("nodes", "edges", "viewport", "name", "description") if k in prev},
            })
            store["history"][wfId] = history[-20:]  # 최근 20개만
        store["workflows"][wfId] = wf_clean
        _dump_all(store)
    return {"ok": True, "id": wfId, "updatedAt": now, "created": is_new}


def _is_position_only_patch(patch: dict) -> bool:
    """True if `patch` only mutates node coordinates and/or viewport.

    Position/viewport-only patches are the high-frequency case (drag, pan,
    zoom). They take a fast path that touches existing in-memory nodes by id
    instead of re-running the full _sanitize_workflow over every field.
    """
    if not isinstance(patch, dict):
        return False
    allowed_top = {"nodes", "viewport"}
    if not patch:
        return False
    if any(k not in allowed_top for k in patch.keys()):
        return False
    nodes = patch.get("nodes")
    if nodes is not None:
        if not isinstance(nodes, list):
            return False
        for pn in nodes:
            if not isinstance(pn, dict):
                return False
            # Only id + x/y allowed in position-only mode.
            if any(k not in ("id", "x", "y") for k in pn.keys()):
                return False
            if "id" not in pn:
                return False
    vp = patch.get("viewport")
    if vp is not None:
        if not isinstance(vp, dict):
            return False
        if any(k not in ("panX", "panY", "zoom") for k in vp.keys()):
            return False
    return True


def api_workflow_patch(body: dict) -> dict:
    """부분 업데이트 — 노드 좌표 드래그 같은 고빈도 호출용. patch 는 키 단위 덮어쓰기.

    v2.44.0 — fast path for position/viewport-only patches: validate with
    isfinite checks and apply in place by id. We never re-run the full
    `_sanitize_workflow` here, since drag/pan dispatches dozens of these per
    second. Other patch shapes (name/description/etc.) keep the existing
    in-place merge path below.
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    wfId = body.get("id")
    if not (isinstance(wfId, str) and _WF_ID_RE.match(wfId)):
        return {"ok": False, "error": "invalid id"}
    patch = body.get("patch") or {}
    if not isinstance(patch, dict):
        return {"ok": False, "error": "invalid patch"}
    now = int(time.time() * 1000)

    # Position/viewport-only fast path: skip full sanitize, validate finite numbers.
    if _is_position_only_patch(patch):
        import math
        with _LOCK:
            store = _load_all()
            wf = store["workflows"].get(wfId)
            if not wf:
                return {"ok": False, "error": "not found"}
            existing = {n["id"]: n for n in wf.get("nodes", []) if isinstance(n, dict)}
            for pn in patch.get("nodes") or []:
                nid = pn.get("id")
                if not isinstance(nid, str) or nid not in existing:
                    continue
                if "x" in pn:
                    try:
                        xv = float(pn["x"])
                        if math.isfinite(xv):
                            existing[nid]["x"] = xv
                    except (TypeError, ValueError):
                        pass
                if "y" in pn:
                    try:
                        yv = float(pn["y"])
                        if math.isfinite(yv):
                            existing[nid]["y"] = yv
                    except (TypeError, ValueError):
                        pass
            if "viewport" in patch and isinstance(patch["viewport"], dict):
                vp = wf.get("viewport") or {"panX": 0, "panY": 0, "zoom": 1}
                pvp = patch["viewport"]
                for k in ("panX", "panY"):
                    if k in pvp:
                        try:
                            v = float(pvp[k])
                            if math.isfinite(v):
                                vp[k] = v
                        except (TypeError, ValueError):
                            pass
                if "zoom" in pvp:
                    try:
                        z = float(pvp["zoom"])
                        if math.isfinite(z):
                            vp["zoom"] = max(0.25, min(3.0, z))
                    except (TypeError, ValueError):
                        pass
                wf["viewport"] = vp
            wf["updatedAt"] = now
            _dump_all(store)
        return {"ok": True, "id": wfId, "updatedAt": now}

    # Generic patch path (data field changes, name/description, etc.).
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


def api_workflow_clone(body: dict) -> dict:
    """워크플로우 복제. body: {id}. 새 ID + "(copy)" 이름으로 생성."""
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
        now = int(time.time() * 1000)
        new_id = _new_wf_id()
        import copy
        clone = copy.deepcopy(wf)
        clone["id"] = new_id
        clone["name"] = (wf.get("name", "Untitled") + " (copy)")[:120]
        clone["createdAt"] = now
        clone["updatedAt"] = now
        # 스케줄은 복제하지 않음 (중복 실행 방지)
        clone.pop("schedule", None)
        store["workflows"][new_id] = clone
        _dump_all(store)
    return {"ok": True, "id": new_id, "name": clone["name"]}


def api_workflow_node_clipboard(body: dict) -> dict:
    """노드 그룹 복사/붙여넣기. body: {action:'copy'|'paste', wfId, nodeIds?[], clipboard?}

    copy: 지정 노드 + 연결 엣지를 클립보드 데이터로 반환
    paste: 클립보드 데이터를 워크플로우에 새 ID로 삽입 (좌표 +40px 오프셋)
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    action = body.get("action")
    wfId = body.get("wfId")

    if action == "copy":
        node_ids = body.get("nodeIds") or []
        if not node_ids:
            return {"ok": False, "error": "nodeIds required"}
        store = _load_all()
        wf = store["workflows"].get(wfId)
        if not wf:
            return {"ok": False, "error": "workflow not found"}
        node_set = set(node_ids)
        copied_nodes = [n for n in wf.get("nodes", []) if n["id"] in node_set]
        copied_edges = [e for e in wf.get("edges", []) if e["from"] in node_set and e["to"] in node_set]
        return {"ok": True, "clipboard": {"nodes": copied_nodes, "edges": copied_edges}}

    if action == "paste":
        clipboard = body.get("clipboard") or {}
        nodes = clipboard.get("nodes") or []
        edges = clipboard.get("edges") or []
        if not nodes:
            return {"ok": False, "error": "empty clipboard"}
        with _LOCK:
            store = _load_all()
            wf = store["workflows"].get(wfId)
            if not wf:
                return {"ok": False, "error": "workflow not found"}
            # 새 ID 매핑
            id_map = {}
            for n in nodes:
                old_id = n["id"]
                new_id = f"n-{uuid.uuid4().hex[:8]}"
                id_map[old_id] = new_id
            new_nodes = []
            for n in nodes:
                import copy
                nn = copy.deepcopy(n)
                nn["id"] = id_map[n["id"]]
                nn["x"] = nn.get("x", 0) + 40
                nn["y"] = nn.get("y", 0) + 40
                new_nodes.append(nn)
            new_edges = []
            for e in edges:
                if e["from"] in id_map and e["to"] in id_map:
                    import copy
                    ne = copy.deepcopy(e)
                    ne["id"] = f"e-{int(time.time()*1000)}-{uuid.uuid4().hex[:4]}"
                    ne["from"] = id_map[e["from"]]
                    ne["to"] = id_map[e["to"]]
                    new_edges.append(ne)
            wf.setdefault("nodes", []).extend(new_nodes)
            wf.setdefault("edges", []).extend(new_edges)
            wf["updatedAt"] = int(time.time() * 1000)
            _dump_all(store)
        return {"ok": True, "pastedNodes": [n["id"] for n in new_nodes]}

    return {"ok": False, "error": f"unknown action: {action}"}


# ───────── Run 엔진 ─────────

def _run_status_snapshot(runId: str) -> dict:
    # v2.44.0 — prefer the in-memory cache (live runs) to avoid rereading
    # ~/.claude-dashboard-workflows.json on every SSE/poll tick. Falls back
    # to disk for completed runs (cache is dropped on completion) and for
    # any run that started before a process restart.
    cached = _runs_cache_get(runId)
    if cached is not None:
        return {"ok": True, "run": cached}
    store = _load_all()
    r = store["runs"].get(runId)
    if not r:
        return {"ok": False, "error": "run not found"}
    return {"ok": True, "run": r}


def _execute_node(node: dict, inputs: list[str], prev_session_ids: list[str] | None = None,
                  fallback_provider: str = "") -> dict:
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
        matched = _evaluate_branch_condition(data, inputs)
        prev = inputs[0] if inputs else ""
        out_port = "out_y" if matched else "out_n"
        return {
            "status": "ok", "output": prev, "durationMs": _elapsed(), "sessionId": "",
            "_branch": out_port,
        }

    if ntype == "output":
        final = inputs[0] if inputs else ""
        exp_raw = data.get("exportTo") or ""
        if exp_raw:
            under = _under_allowed_export(exp_raw)
            if not under:
                return {
                    "status": "err", "output": "", "durationMs": _elapsed(),
                    "error": "exportTo must resolve under ~/Downloads, ~/Documents, or ~/Desktop",
                }
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

    # ── Merge 노드 — 병렬 경로 합류 ──
    if ntype == "merge":
        return _execute_merge_node(data, inputs, _elapsed)

    # ── Delay 노드 — 대기 후 통과 ──
    if ntype == "delay":
        return _execute_delay_node(data, inputs, _elapsed)

    # ── Loop 노드 — 반복 실행 ──
    if ntype == "loop":
        return _execute_loop_node(data, inputs, _elapsed)

    # ── Retry 노드 — 재시도 래퍼 (pass-through, 실제 재시도는 _run_one_iteration 에서) ──
    if ntype == "retry":
        # retry 노드는 입력을 그대로 전달 — 실제 재시도 로직은 노드 연결 패턴으로 구현
        return {"status": "ok", "output": inputs[0] if inputs else "",
                "durationMs": _elapsed(), "sessionId": "",
                "retryConfig": {"maxRetries": data.get("maxRetries", 3),
                                "backoffMs": data.get("backoffMs", 1000)}}

    # ── Error Handler 노드 — 에러 시 대안 출력 ──
    if ntype == "error_handler":
        return _execute_error_handler_node(data, inputs, _elapsed)

    # ── Embedding 노드 — 텍스트 임베딩 생성 ──
    if ntype == "embedding":
        return _execute_embedding_node(data, inputs, _elapsed)

    # ── Sub-workflow 노드 — 다른 워크플로우 호출 ──
    if ntype == "subworkflow":
        return _execute_subworkflow_node(data, inputs, _elapsed)

    # ── Slack approval gate (v2.34.0) ──
    if ntype == "slack_approval":
        return _execute_slack_approval_node(data, inputs, _elapsed)

    # ── Obsidian markdown log writer (v2.34.0) ──
    if ntype == "obsidian_log":
        return _execute_obsidian_log_node(data, inputs, _elapsed)

    # ── Auto-Resume binding (v2.37.0) ──
    if ntype == "auto_resume":
        return _execute_auto_resume_node(data, inputs, _elapsed)

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

    # v2.25.0 — Prompt Library 키워드 트리거: 입력 텍스트에 매칭되는 라이브러리
    # 항목이 있으면 그 body 를 systemPrompt 앞에 prepend 한다 (OMC ultrathink 대응).
    try:
        from .prompt_library import find_keyword_triggers
        triggered = find_keyword_triggers(prompt)
        if triggered:
            trigger_blocks = "\n\n".join(
                f"# [auto-injected: {it.get('title', '?')}]\n{it.get('body', '')}"
                for it in triggered
            )
            sys_prompt = (trigger_blocks + ("\n\n" + sys_prompt if sys_prompt else "")).strip()
    except Exception:
        pass

    assignee = (data.get("assignee") or "").strip()

    # v2.25.0 — modelHint 기반 자동 모델 선택. 명시적 assignee 가 비어있을 때만 적용.
    model_hint = (data.get("modelHint") or "").strip()
    chosen_model = ""
    if not assignee and model_hint:
        if model_hint == "fast":
            chosen_model = "claude:haiku"
        elif model_hint == "deep":
            chosen_model = "claude:opus"
        elif model_hint == "auto":
            # 휴리스틱: 길이 + 키워드
            plen = len(prompt)
            text_lower = prompt.lower()
            deep_keywords = ("architect", "design", "deep", "complex", "reason", "proof",
                             "설계", "구조", "분석", "철저", "심층")
            fast_keywords = ("list", "summary", "quick", "extract", "요약", "간단")
            has_deep = any(k in text_lower for k in deep_keywords)
            has_fast = any(k in text_lower for k in fast_keywords)
            if plen > 3000 or has_deep:
                chosen_model = "claude:opus"
            elif plen < 500 and has_fast:
                chosen_model = "claude:haiku"
            else:
                chosen_model = "claude:sonnet"
        if chosen_model:
            assignee = chosen_model

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

    # 멀티 프로바이더 실행 — 실패 시 policy.fallbackProvider 로 1회 재시도 (v2.29.0)
    def _pack(resp, fallback_used: str = "") -> dict:
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
            "chosenModel": chosen_model,
            "fallbackUsed": fallback_used,  # 비어있으면 원래 assignee 로 성공/실패
        }

    # v2.44.1 — multiAssignee fan-out. If the inspector configured >= 2
    # assignees, race them in parallel via ProviderRegistry.execute_parallel
    # and return the first ok response. The single-assignee path is preserved
    # untouched when multiAssignee is empty or has 1 entry.
    raw_multi = data.get("multiAssignee") or []
    multi_assignees: list[str] = []
    if isinstance(raw_multi, list):
        seen_ma: set[str] = set()
        for item in raw_multi:
            if not isinstance(item, str):
                continue
            v = item.strip()
            if not v or v in seen_ma:
                continue
            seen_ma.add(v)
            multi_assignees.append(v)
    use_parallel = len(multi_assignees) >= 2

    try:
        from .ai_providers import execute_with_assignee, get_registry
        if use_parallel:
            resp = get_registry().execute_parallel(
                multi_assignees,
                prompt,
                system_prompt=sys_prompt,
                cwd=cwd_safe,
                timeout=_DEFAULT_NODE_TIMEOUT,
                extra=extra,
                fallback=True,
            )
        else:
            resp = execute_with_assignee(
                assignee or "claude-cli",
                prompt,
                system_prompt=sys_prompt,
                cwd=cwd_safe,
                timeout=_DEFAULT_NODE_TIMEOUT,
                extra=extra,
                fallback=True,
            )
        # 실패 + policy.fallbackProvider 설정 → 해당 provider 로 1회 재시도
        if resp.status == "err" and fallback_provider and fallback_provider != (assignee or "claude-cli"):
            try:
                resp2 = execute_with_assignee(
                    fallback_provider,
                    prompt,
                    system_prompt=sys_prompt,
                    cwd=cwd_safe,
                    timeout=_DEFAULT_NODE_TIMEOUT,
                    extra=extra,
                    fallback=False,  # 이미 fallback 단계, 재귀 방지
                )
                if resp2.status == "ok":
                    return _pack(resp2, fallback_used=fallback_provider)
            except Exception as e:
                log.warning("policy fallback provider failed: %s", e)
        return _pack(resp)
    except Exception as e:
        log.exception("execute_with_assignee failed: %s", e)
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"provider execution failed: {e}", "sessionId": ""}


_HTTP_BLOCKED_SCHEMES = {"file", "ftp", "gopher", "data", "dict", "tftp"}
_HTTP_BLOCKED_HOSTS = {
    "127.0.0.1", "0.0.0.0", "::1", "::",
    "localhost", "ip6-localhost", "ip6-loopback",
    # 클라우드 메타데이터
    "169.254.169.254", "metadata.google.internal", "metadata.goog",
    "fd00:ec2::254",
}
_HTTP_PRIVATE_PREFIXES_V4 = (
    "10.", "127.", "169.254.", "192.168.",
    # 172.16.0.0/12
    *(f"172.{i}." for i in range(16, 32)),
)
_HTTP_PRIVATE_PREFIXES_V6 = ("fc", "fd", "fe80:", "fe9", "fea", "feb")  # RFC 4193 ULA + link-local


def _http_is_internal(host: str) -> bool:
    """호스트가 내부/사설/메타데이터 대역인지 판정.

    IPv4/IPv6 리터럴과 일반 이름 모두 처리. DNS 이름은 getaddrinfo 로
    해석해 실제 IP 가 내부 대역이면 True (DNS rebinding 방어).
    """
    if not host:
        return True
    h = host.lower().strip("[]")
    if h in _HTTP_BLOCKED_HOSTS:
        return True
    if h.endswith(".localhost"):
        return True
    if h.startswith(_HTTP_PRIVATE_PREFIXES_V4):
        return True
    if any(h.startswith(p) for p in _HTTP_PRIVATE_PREFIXES_V6):
        return True
    # DNS 이름 → IP 해석 후 다시 검사 (DNS rebinding 방어)
    try:
        import socket as _sock
        for info in _sock.getaddrinfo(host, None):
            ip = info[4][0]
            if ip in _HTTP_BLOCKED_HOSTS:
                return True
            if ip.startswith(_HTTP_PRIVATE_PREFIXES_V4):
                return True
            if any(ip.startswith(p) for p in _HTTP_PRIVATE_PREFIXES_V6):
                return True
    except Exception:
        # 해석 실패 시엔 차단으로 처리 (fail-closed)
        return True
    return False


def _execute_http_node(data: dict, inputs: list[str], _elapsed) -> dict:
    """HTTP 노드 실행 — 외부 API 호출.

    보안: URL 의 scheme 을 http/https 로 제한하고, 호스트가 내부/사설/메타데이터
    대역이면 기본 차단. 사용자가 의도적으로 내부 호출을 원하면 노드 data 에
    `allowInternal: true` 플래그를 세팅해야 한다. (v2.22.0 SSRF 가드)
    """
    import urllib.request
    import urllib.error
    from urllib.parse import urlparse

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

    # ── SSRF 가드 ──
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"URL scheme '{scheme}' blocked (only http/https). "
                         f"file://, ftp:// 등은 보안상 차단됨."}
    allow_internal = bool(data.get("allowInternal"))
    if not allow_internal and _http_is_internal(parsed.hostname or ""):
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": (f"내부/사설 호스트 '{parsed.hostname}' 차단 (SSRF 방지). "
                          f"의도된 호출이면 노드 설정에서 'allowInternal: true' 체크.")}

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


def _execute_variable_node(data: dict, inputs: list[str], _elapsed,
                           var_store: dict | None = None) -> dict:
    """Variable 노드 — 변수 저장소에 값 저장 + 출력 전달.

    var_store: 워크플로우 실행 중 공유되는 변수 딕셔너리.
    저장 후 다른 노드에서 {{변수명}} 으로 참조 가능.
    scope: 'global' (워크플로우 전체) 또는 'local' (이 실행만).
    """
    var_name = (data.get("varName") or "var").strip()
    value = inputs[0] if inputs else (data.get("defaultValue") or "")
    if var_store is not None:
        var_store[var_name] = value
    return {"status": "ok", "output": value, "durationMs": _elapsed(),
            "sessionId": "", "varName": var_name}


def _evaluate_branch_condition(data: dict, inputs: list[str]) -> bool:
    """Branch 노드 복합 조건 평가.

    conditionType:
      - contains: 입력에 condition 문자열 포함 (기존 호환)
      - equals: 입력 == condition
      - not_equals: 입력 != condition
      - greater: 숫자 비교 >
      - less: 숫자 비교 <
      - regex: 정규식 매칭
      - length_gt: 입력 길이 > N
      - length_lt: 입력 길이 < N
      - is_empty: 입력 비어있음
      - not_empty: 입력 비어있지 않음
      - expression: AND/OR 복합 (콤마=AND, |=OR)
    """
    cond = (data.get("condition") or "").strip()
    cond_type = (data.get("conditionType") or "contains").strip()
    prev = inputs[0] if inputs else ""
    prev_lower = prev.lower()
    cond_lower = cond.lower()

    if cond_type == "equals":
        return prev.strip() == cond
    if cond_type == "not_equals":
        return prev.strip() != cond
    if cond_type == "greater":
        try:
            return float(prev.strip()) > float(cond)
        except ValueError:
            return False
    if cond_type == "less":
        try:
            return float(prev.strip()) < float(cond)
        except ValueError:
            return False
    if cond_type == "regex":
        try:
            return bool(re.search(cond, prev))
        except Exception:
            return False
    if cond_type == "length_gt":
        try:
            return len(prev) > int(cond)
        except ValueError:
            return False
    if cond_type == "length_lt":
        try:
            return len(prev) < int(cond)
        except ValueError:
            return False
    if cond_type == "is_empty":
        return not prev.strip()
    if cond_type == "not_empty":
        return bool(prev.strip())
    if cond_type == "expression":
        # OR: | 구분, AND: , 구분
        if "|" in cond:
            return any(part.strip().lower() in prev_lower for part in cond.split("|") if part.strip())
        if "," in cond:
            return all(part.strip().lower() in prev_lower for part in cond.split(",") if part.strip())
        return cond_lower in prev_lower
    # default: contains (기존 호환)
    return bool(cond) and cond_lower in prev_lower


def _substitute_variables(text: str, var_store: dict) -> str:
    """텍스트 내 {{변수명}} 을 변수 저장소 값으로 치환."""
    if not var_store or "{{" not in text:
        return text
    for k, v in var_store.items():
        text = text.replace(f"{{{{{k}}}}}", str(v))
    return text


def _execute_merge_node(data: dict, inputs: list[str], _elapsed) -> dict:
    """Merge 노드 — 여러 병렬 입력을 합류.

    mergeMode:
      - all: 모든 입력이 있어야 통과 (빈 입력 제외)
      - any: 하나라도 있으면 통과
      - count: requiredCount 개 이상이면 통과
    """
    mode = data.get("mergeMode", "all")
    required = data.get("requiredCount", 1)
    valid = [i for i in inputs if i.strip()]

    if mode == "all" and len(valid) < len(inputs):
        return {"status": "ok", "output": "", "durationMs": _elapsed(),
                "sessionId": "", "mergeWaiting": True}
    if mode == "count" and len(valid) < required:
        return {"status": "ok", "output": "", "durationMs": _elapsed(),
                "sessionId": "", "mergeWaiting": True}
    if mode == "any" and not valid:
        return {"status": "ok", "output": "", "durationMs": _elapsed(),
                "sessionId": "", "mergeWaiting": True}

    output = "\n---\n".join(valid)
    return {"status": "ok", "output": output, "durationMs": _elapsed(),
            "sessionId": "", "mergeCount": len(valid)}


def _execute_delay_node(data: dict, inputs: list[str], _elapsed) -> dict:
    """Delay 노드 — 지정 시간 대기 후 입력을 그대로 통과."""
    import random as _random
    delay_ms = data.get("delayMs", 1000)
    delay_type = data.get("delayType", "fixed")

    if delay_type == "random":
        max_ms = data.get("maxDelayMs", 5000)
        actual_ms = _random.randint(delay_ms, max(delay_ms, max_ms))
    else:
        actual_ms = delay_ms

    time.sleep(actual_ms / 1000.0)
    output = inputs[0] if inputs else ""
    return {"status": "ok", "output": output, "durationMs": _elapsed(),
            "sessionId": "", "actualDelayMs": actual_ms}


def _execute_loop_node(data: dict, inputs: list[str], _elapsed) -> dict:
    """Loop 노드 — 입력을 분할하여 각 항목을 개별 출력으로 모아 반환.

    loopType:
      - for_each: 입력 텍스트를 separator 로 분할, 각 항목을 줄바꿈으로 결합
      - count: maxIterations 횟수만큼 입력을 반복 (인덱스 주입)
      - while: 조건 문자열이 출력에 포함되는 동안 반복 (최대 maxIterations)
    """
    loop_type = data.get("loopType", "for_each")
    max_iter = data.get("maxIterations", 10)
    separator = data.get("separator", "\n")
    input_text = inputs[0] if inputs else ""

    if loop_type == "for_each":
        items = input_text.split(separator) if separator else [input_text]
        items = [i.strip() for i in items if i.strip()][:max_iter]
        output = json.dumps(items, ensure_ascii=False)
        return {"status": "ok", "output": output, "durationMs": _elapsed(),
                "sessionId": "", "loopCount": len(items)}

    if loop_type == "count":
        results = []
        for i in range(max_iter):
            results.append(f"[{i}] {input_text}")
        output = "\n".join(results)
        return {"status": "ok", "output": output, "durationMs": _elapsed(),
                "sessionId": "", "loopCount": max_iter}

    # while — 단순 pass-through (실제 while 루프는 워크플로우 repeat 기능으로 대체)
    return {"status": "ok", "output": input_text, "durationMs": _elapsed(),
            "sessionId": "", "loopCount": 1}


def _execute_error_handler_node(data: dict, inputs: list[str], _elapsed) -> dict:
    """Error Handler 노드 — 이전 노드 에러 시 대안 출력 제공.

    onError:
      - skip: 에러 입력 무시, 빈 출력
      - default: 기본 출력 텍스트 반환
      - route: 에러 메시지를 출력으로 전달 (후속 노드가 처리)
    """
    on_error = data.get("onError", "skip")
    default_output = data.get("defaultOutput", "")
    input_text = inputs[0] if inputs else ""

    # error_handler 는 이전 노드가 에러일 때 대안을 제공
    # 정상 입력이면 그대로 통과
    if input_text:
        return {"status": "ok", "output": input_text, "durationMs": _elapsed(), "sessionId": ""}

    if on_error == "default":
        return {"status": "ok", "output": default_output, "durationMs": _elapsed(), "sessionId": ""}
    if on_error == "route":
        return {"status": "ok", "output": "[error routed]", "durationMs": _elapsed(), "sessionId": ""}
    # skip
    return {"status": "ok", "output": "", "durationMs": _elapsed(), "sessionId": ""}


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
    sub_entry = {
        "id": sub_run_id, "workflowId": wf_id,
        "status": "running", "startedAt": int(time.time() * 1000),
        "finishedAt": 0, "currentNodeId": None,
        "nodeResults": {}, "iteration": 0, "error": None,
        "isSubworkflow": True,
    }
    with _LOCK:
        store = _load_all()
        store["runs"][sub_run_id] = sub_entry
        _dump_all(store)
    _runs_cache_set(sub_run_id, dict(sub_entry))

    ok, _results, final_out = _run_one_iteration(
        sub_wf, sub_run_id, 0, extra_inputs)

    # 완료 기록 — flush cache and drop.
    def _finalize_sub(r: dict) -> None:
        r["status"] = "ok" if ok else "err"
        r["finishedAt"] = int(time.time() * 1000)
    _runs_cache_update(sub_run_id, _finalize_sub)
    _persist_run(sub_run_id)
    _runs_cache_pop(sub_run_id)

    if not ok:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"sub-workflow failed", "sessionId": ""}

    return {"status": "ok", "output": final_out, "durationMs": _elapsed(),
            "sessionId": "", "subRunId": sub_run_id}


# ───────── Slack approval gate (v2.34.0) ─────────

def _execute_slack_approval_node(data: dict, inputs: list[str], _elapsed) -> dict:
    """Post a Slack message and block until an admin reacts/replies.

    Output of this node mirrors the upstream input on `approve`/`commented`,
    and switches to `defaultOutput` on `reject`/`abort`. The upstream
    branch logic can route on the `_approval` field if needed.
    """
    from .slack_api import (
        SlackError, get_token, post_message, wait_for_approval,
        load_slack_config,
    )

    cfg = load_slack_config()
    channel = (data.get("channel") or "").strip() or cfg.get("defaultChannel", "")
    if not channel:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": "slack channel not configured", "sessionId": ""}
    if not get_token():
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": "slack token not configured (see Wizard → Slack 설정)",
                "sessionId": ""}

    template = (data.get("messageTemplate") or "").strip()
    upstream = inputs[0] if inputs else ""
    if data.get("includeInput", True) and upstream:
        body_text = (template + "\n\n" if template else "") + upstream
    else:
        body_text = template or upstream or "Approval requested."

    notice = ("\n\n_:white_check_mark: 승인 · :x: 거부 — 또는 스레드에 "
              "`approve`/`reject` 답장_")
    full_msg = body_text[:38000] + notice

    try:
        posted = post_message(channel, full_msg)
        ts = posted.get("ts") or ""
    except SlackError as e:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"slack post failed: {e}", "sessionId": ""}

    timeout_s = int(data.get("timeoutSeconds") or 300)
    poll_s = int(data.get("pollIntervalSeconds") or 5)
    on_timeout = data.get("onTimeout") or "approve"
    default_output = (data.get("defaultOutput") or "").strip()

    try:
        signal = wait_for_approval(channel, ts, timeout_s=timeout_s,
                                   poll_interval_s=poll_s)
    except Exception as e:
        log.exception("slack approval polling failed")
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"slack polling failed: {e}", "sessionId": ""}

    status = signal.get("status")
    decision = status

    if status == "timeout":
        # Autonomous-mode fallback.
        if on_timeout == "abort":
            return {"status": "err", "output": "",
                    "durationMs": _elapsed(),
                    "error": "slack approval timed out (onTimeout=abort)",
                    "sessionId": "", "_approval": "timeout"}
        if on_timeout == "reject":
            decision = "rejected"
        elif on_timeout == "default":
            return {"status": "ok", "output": default_output or upstream,
                    "durationMs": _elapsed(), "sessionId": "",
                    "_approval": "timeout-default"}
        else:  # approve
            decision = "approved"

    if decision == "rejected":
        return {"status": "ok",
                "output": default_output or "[approval rejected]",
                "durationMs": _elapsed(), "sessionId": "",
                "_approval": "rejected", "messageTs": ts, "channel": channel,
                "reactor": signal.get("reactor", ""),
                "replyText": signal.get("replyText", ""),
                "replyUser": signal.get("replyUser", "")}

    # approved or commented
    out_text = upstream
    reply = (signal.get("replyText") or "").strip()
    if decision == "commented" and reply:
        # Treat a freeform reply as authoritative override of the input.
        out_text = reply

    return {"status": "ok", "output": out_text,
            "durationMs": _elapsed(), "sessionId": "",
            "_approval": decision, "messageTs": ts, "channel": channel,
            "reactor": signal.get("reactor", ""),
            "replyText": reply, "replyUser": signal.get("replyUser", "")}


# ───────── Obsidian log writer (v2.34.0) ─────────

def _execute_obsidian_log_node(data: dict, inputs: list[str], _elapsed) -> dict:
    """Append the upstream output as a markdown entry under the configured vault."""
    from .obsidian_log import append_log

    vault = (data.get("vaultPath") or "").strip()
    project = (data.get("project") or "lazyclaude").strip()
    heading = (data.get("heading") or "").strip()
    tags_csv = (data.get("tagsCsv") or "").strip()
    pass_through = bool(data.get("passThrough", True))
    default_output = (data.get("defaultOutput") or "").strip()

    upstream = inputs[0] if inputs else ""
    body = upstream if pass_through else (default_output or upstream)
    if not body:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": "obsidian_log received empty input", "sessionId": ""}

    tags = [t.strip() for t in tags_csv.split(",") if t.strip()] if tags_csv else None
    res = append_log(vault, project, body, heading=heading, tags=tags)
    if not res.get("ok"):
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"obsidian write failed: {res.get('error')}",
                "sessionId": ""}

    return {"status": "ok", "output": upstream, "durationMs": _elapsed(),
            "sessionId": "", "logPath": res.get("path"),
            "bytesWritten": res.get("bytesWritten", 0)}


# Pattern for "session_id is the first hex UUID in the upstream input".
_AUTO_RESUME_UUID_RE = re.compile(
    r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
    re.IGNORECASE,
)


def _execute_auto_resume_node(data: dict, inputs: list[str], _elapsed) -> dict:
    """Bind / cancel an Auto-Resume worker for a target session.

    sessionId resolution order:
      1. data['sessionId'] if explicitly set
      2. first UUID found in the upstream input string

    The workflow flow continues immediately — the supervisor runs
    independently in its background thread.
    """
    from .auto_resume import api_auto_resume_set, api_auto_resume_cancel

    action = (data.get("action") or "set").strip()
    sid = (data.get("sessionId") or "").strip()
    if not sid:
        upstream = inputs[0] if inputs else ""
        m = _AUTO_RESUME_UUID_RE.search(upstream or "")
        if m:
            sid = m.group(1)
    if not sid:
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": "auto_resume node: no sessionId (set explicitly or "
                         "pipe a string containing a UUID into this node)",
                "sessionId": ""}

    if action == "cancel":
        r = api_auto_resume_cancel({"sessionId": sid})
    else:
        r = api_auto_resume_set({
            "sessionId":    sid,
            "cwd":          (data.get("cwd") or "").strip(),
            "prompt":       (data.get("prompt") or "").strip(),
            "pollInterval": int(data.get("pollInterval") or 300),
            "idleSeconds":  int(data.get("idleSeconds") or 90),
            "maxAttempts":  int(data.get("maxAttempts") or 12),
            "useContinue":  bool(data.get("useContinue")),
            "installHooks": bool(data.get("installHooks")),
        })
    if not r.get("ok"):
        return {"status": "err", "output": "", "durationMs": _elapsed(),
                "error": f"auto_resume {action}: {r.get('error') or '?'}",
                "sessionId": ""}
    entry = r.get("entry") or {}
    summary = (
        f"auto_resume {action} ok\n"
        f"  sessionId: {sid}\n"
        f"  state:     {entry.get('state')}\n"
        f"  attempts:  {entry.get('attempts')}/{entry.get('maxAttempts')}\n"
        f"  cwd:       {entry.get('cwd')}\n"
    )
    return {"status": "ok", "output": summary, "durationMs": _elapsed(),
            "sessionId": "", "autoResumeEntry": entry}


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


# v2.44.0 — default parallel worker cap was 4, which throttled wide DAGs on
# multi-core hosts. Default now scales with CPU count (min 8, max 32) so
# fan-out levels execute closer to actual hardware capacity. The
# WORKFLOW_MAX_PARALLEL env var still wins for explicit override.
def _default_max_parallel_workers() -> int:
    cpu = os.cpu_count() or 4
    return max(8, min(32, cpu * 2))


_MAX_PARALLEL_WORKERS = int(
    os.environ.get("WORKFLOW_MAX_PARALLEL") or _default_max_parallel_workers()
)
# Hard cap upper bound regardless of source, to prevent runaway thread counts.
if _MAX_PARALLEL_WORKERS > 32:
    _MAX_PARALLEL_WORKERS = 32
if _MAX_PARALLEL_WORKERS < 1:
    _MAX_PARALLEL_WORKERS = 1


def _record_workflow_cost(run_id: str, workflow_id: str, node_id: str, res: dict) -> None:
    """워크플로우 노드 실행 비용을 DB에 기록."""
    provider = res.get("provider", "")
    model = res.get("model", "")
    if not provider and not model:
        return  # start/aggregate/branch 등 AI 호출 없는 노드는 스킵
    try:
        # _db_init() is invoked from API entry points; no need to repeat per cost write.
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
    # v2.44.0 — write through the in-memory cache. We only persist to disk
    # at iteration boundaries, on completion, on cancel, and on terminal
    # failures. Per-node running/done updates stay in memory.
    def _cache_reset_iter(r: dict) -> None:
        r["nodeResults"] = {}
        r["iteration"] = iter_idx

    if _runs_cache_update(runId, _cache_reset_iter) is None:
        # Run not yet seeded in cache (e.g., started by an older code path
        # that wrote directly to disk). Hydrate from disk so subsequent
        # cache updates have something to mutate.
        with _LOCK:
            s = _load_all()
            disk_run = s.get("runs", {}).get(runId)
        if disk_run is not None:
            disk_run["nodeResults"] = {}
            disk_run["iteration"] = iter_idx
            _runs_cache_set(runId, disk_run)

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

    # v2.27.0 — 워크플로우 전역 토큰 예산 정책
    # v2.29.0 — + fallbackProvider (session 노드 실패 시 재시도 프로바이더)
    policy = wf.get("policy") or {}
    token_budget = int(policy.get("tokenBudgetTotal") or 0)
    fallback_provider = (policy.get("fallbackProvider") or "").strip()

    def _run_single_node(nid: str) -> tuple[str, dict]:
        """단일 노드 실행 (병렬 워커에서 호출)."""
        node = node_by_id[nid]
        input_strs = _collect_inputs(nid)
        prev_sids = _collect_prev_sids(nid)
        res = _execute_node(node, input_strs, prev_sids, fallback_provider=fallback_provider)
        return (nid, res)

    for level in levels:
        # 전체 timeout 체크
        if time.time() - total_t0 > _DEFAULT_TOTAL_TIMEOUT:
            def _mark_timeout(r: dict) -> None:
                r["status"] = "err"
                r["error"] = "total workflow timeout"
                r["finishedAt"] = int(time.time() * 1000)
            _runs_cache_update(runId, _mark_timeout)
            _persist_run(runId)  # terminal failure: flush before returning
            return (False, results, "")

        # 토큰 예산 체크 — 초과 시 이후 모든 노드를 budget_exceeded 로 마크하고 종료
        if token_budget > 0:
            total_tokens = sum(
                (r.get("tokensIn", 0) or 0) + (r.get("tokensOut", 0) or 0)
                for r in results.values() if isinstance(r, dict)
            )
            if total_tokens >= token_budget:
                def _mark_budget(r: dict) -> None:
                    nr = r.setdefault("nodeResults", {})
                    for nid in order:
                        if nid not in nr:
                            nr[nid] = {
                                "status": "budget_exceeded",
                                "output": "",
                                "durationMs": 0,
                            }
                    r["budgetExceeded"] = True
                    r["totalTokens"] = total_tokens
                _runs_cache_update(runId, _mark_budget)
                _persist_run(runId)  # iteration-boundary equivalent
                log.info("workflow %s run %s stopped — token budget %d exceeded (%d)",
                         wf.get("id"), runId, token_budget, total_tokens)
                # ok=True (부분 완료) 로 종료, 마지막 노드 결과를 final_out 으로
                final_node = next((nid for nid in reversed(order) if nid in results
                                   and results[nid].get("status") == "ok"), None)
                final_out = results.get(final_node, {}).get("output", "") if final_node else ""
                return (True, results, final_out)

        # disabled 노드 제외
        active_nodes = [nid for nid in level if nid not in disabled]
        skipped_nodes = [nid for nid in level if nid in disabled]

        # skip 기록 — cache only.
        if skipped_nodes:
            def _mark_skipped(r: dict) -> None:
                nr = r.setdefault("nodeResults", {})
                for nid in skipped_nodes:
                    nr[nid] = {"status": "skipped"}
            _runs_cache_update(runId, _mark_skipped)

        if not active_nodes:
            continue

        # 진행 상황: running 표시 (프론트에서 elapsed 계산을 위해 startedAt 포함)
        # cache only — SSE/poll reads via _runs_cache_get.
        now_ms = int(time.time() * 1000)
        def _mark_running(r: dict) -> None:
            nr = r.setdefault("nodeResults", {})
            for nid in active_nodes:
                nr[nid] = {"status": "running", "startedAt": now_ms}
            r["currentNodeId"] = active_nodes[0]
        _runs_cache_update(runId, _mark_running)

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
                err_nid = nid
                err_msg = res.get("error", "")
                err_dur = res.get("durationMs", 0)
                def _mark_err(r: dict) -> None:
                    nr = r.setdefault("nodeResults", {})
                    nr[err_nid] = {
                        "status": "err",
                        "error": err_msg,
                        "durationMs": err_dur,
                    }
                    r["status"] = "err"
                    r["error"] = f"node {err_nid}: {err_msg}"
                    r["finishedAt"] = int(time.time() * 1000)
                _runs_cache_update(runId, _mark_err)
                _persist_run(runId)  # terminal failure: flush before returning
                had_error = True
                break
            else:
                ok_nid = nid
                ok_payload = {
                    "status": "ok",
                    "output": (res.get("output") or "")[:4000],
                    "sessionId": res.get("sessionId") or "",
                    "durationMs": res.get("durationMs", 0),
                    "provider": res.get("provider", ""),
                    "model": res.get("model", ""),
                }
                def _mark_ok(r: dict) -> None:
                    nr = r.setdefault("nodeResults", {})
                    nr[ok_nid] = ok_payload
                _runs_cache_update(runId, _mark_ok)
                # 비용 추적 DB 기록 (separate DB; not part of JSON store)
                _record_workflow_cost(
                    runId, wf.get("id", ""), nid, res)

        if had_error:
            return (False, results, "")

    # Iteration boundary — flush accumulated cache state to disk so completed
    # runs and visible progress survive restart, and so cost/timeline readers
    # that read from disk still see fresh data at iteration granularity.
    _persist_run(runId)

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
            def _err_notfound(r: dict) -> None:
                r["status"] = "err"
                r["error"] = "workflow not found"
                r["finishedAt"] = int(time.time() * 1000)
            _runs_cache_update(runId, _err_notfound)
            _persist_run(runId)
            return

        cyc = _check_dag(wf.get("nodes", []), wf.get("edges", []))
        if cyc:
            def _err_cycle(r: dict) -> None:
                r["status"] = "err"
                r["error"] = cyc[0]
                r["finishedAt"] = int(time.time() * 1000)
            _runs_cache_update(runId, _err_cycle)
            _persist_run(runId)
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

        # 전체 완료 — flush cache to disk and drop the in-memory entry.
        def _mark_done(r: dict) -> None:
            r["status"] = "ok"
            r["finishedAt"] = int(time.time() * 1000)
            r["currentNodeId"] = None
        _runs_cache_update(runId, _mark_done)
        _persist_run(runId)
        _runs_cache_pop(runId)
        _notify_run_completion(wfId, runId, "ok", prev_output)
    except Exception as e:
        log.exception("workflow run failed: %s", e)
        def _mark_internal(r: dict) -> None:
            r["status"] = "err"
            r["error"] = f"internal: {e}"
            r["finishedAt"] = int(time.time() * 1000)
        _runs_cache_update(runId, _mark_internal)
        _persist_run(runId)
        _runs_cache_pop(runId)
        _notify_run_completion(wfId, runId, "err", str(e))


def _notify_run_completion(wfId: str, runId: str, status: str, summary: str = "") -> None:
    """run 종료 시 workflow 에 설정된 Slack/Discord 채널로 알림 전송.

    workflows store 를 읽어 현재 wf 의 notify 필드를 확인, 설정된 채널만 전송.
    실패해도 조용히 로그만 (워크플로우 결과에 영향 없음).
    """
    try:
        store = _load_all()
        wf = store["workflows"].get(wfId) or {}
        notify = wf.get("notify") or {}
        slack_url = (notify.get("slack") or "").strip()
        discord_url = (notify.get("discord") or "").strip()
        if not slack_url and not discord_url:
            return
        run = (store.get("runs") or {}).get(runId) or {}
        started = run.get("startedAt") or 0
        finished = run.get("finishedAt") or int(time.time() * 1000)
        duration_ms = max(0, finished - started)
        # 비용 집계: store costs 에서 해당 run 합산
        cost_usd = 0.0
        for row in store.get("costs") or []:
            if row.get("runId") == runId:
                try:
                    cost_usd += float(row.get("usdEst") or 0)
                except Exception:
                    pass
        from .notify import notify_workflow_completion
        notify_workflow_completion(
            slack_url=slack_url, discord_url=discord_url,
            wf_name=wf.get("name", "Untitled"),
            run_id=runId, status=status,
            duration_ms=duration_ms, cost_usd=round(cost_usd, 6),
            summary=(summary or "")[:500],
        )
    except Exception as e:
        log.warning("notify dispatch failed: %s", e)


def api_workflow_dry_run(body: dict) -> dict:
    """v2.33.7 — 실제 LLM/HTTP 호출 없이 DAG 검증 + 실행 순서 + 변수 해석 스텁.

    반환:
      - ok: bool
      - error: 사이클 / 미존재 시
      - levels: [[nodeId, ...], ...] — 같은 level 은 병렬 실행 대상
      - plan: [{id, kind, label, assignee, willRun, notes}, ...] 토폴로지 순
      - unresolved: [{nodeId, key}] — {{var}} 인데 어디서도 정의 안 된 항목
    """
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
    nodes = wf.get("nodes", []) or []
    edges = wf.get("edges", []) or []
    cyc = _check_dag(nodes, edges)
    if cyc:
        return {"ok": False, "error": cyc[0]}
    levels = _topological_levels(nodes, edges)
    order = [nid for lv in levels for nid in lv]
    by_id = {n["id"]: n for n in nodes}
    # 변수 스코프 수집 (전역 + variable 노드 output)
    defined: set = set()
    var_pat = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")
    wf_vars = wf.get("variables") or {}
    if isinstance(wf_vars, dict):
        defined.update(wf_vars.keys())
    # variable 노드도 해당 키를 출력에 추가한다고 가정
    for n in nodes:
        if n.get("kind") == "variable":
            k = (n.get("data") or {}).get("key") or n.get("label") or ""
            if k:
                defined.add(k)
    plan = []
    unresolved = []
    for nid in order:
        n = by_id[nid]
        data = n.get("data") or {}
        text_pieces = []
        for k in ("prompt", "input", "body", "command", "url", "code"):
            v = data.get(k)
            if isinstance(v, str) and v:
                text_pieces.append(v)
        joined = "\n".join(text_pieces)
        for m in var_pat.finditer(joined):
            key = m.group(1)
            if key.split(".")[0] not in defined and key not in defined:
                unresolved.append({"nodeId": nid, "key": key})
        plan.append({
            "id": nid,
            "kind": n.get("kind"),
            "label": n.get("label") or n.get("kind"),
            "assignee": n.get("assignee") or data.get("provider") or "",
            "willRun": n.get("kind") not in ("variable",),  # variable 은 노드 단위 실행 안 함
            "notes": f"kind={n.get('kind')}",
        })
    return {
        "ok": True,
        "workflowId": wfId,
        "levels": levels,
        "plan": plan,
        "unresolved": unresolved,
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
    }


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
        run_entry = {
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
        store["runs"][runId] = run_entry
        _dump_all(store)
    # v2.44.0 — seed in-memory cache so per-node updates avoid disk I/O.
    _runs_cache_set(runId, dict(run_entry))
    # 백그라운드 시작
    th = threading.Thread(target=_run_workflow_background, args=(wfId, runId), daemon=True)
    th.start()
    return {"ok": True, "runId": runId, "workflowId": wfId}


def api_workflow_webhook_secret(body: dict) -> dict:
    """워크플로우 webhook secret 조회/생성/재생성.

    body:
      - {id: "wf-..."}                    → 현재 secret 조회 (없으면 빈 문자열)
      - {id: "wf-...", action: "generate"} → 미발급 시 발급 (이미 있으면 기존값 반환)
      - {id: "wf-...", action: "rotate"}   → 항상 새 값으로 교체
      - {id: "wf-...", action: "clear"}    → secret 제거 (웹훅 비활성화)
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    wfId = body.get("id")
    if not (isinstance(wfId, str) and _WF_ID_RE.match(wfId)):
        return {"ok": False, "error": "invalid id", "error_key": "err_invalid_id"}
    action = body.get("action") or "get"
    if action not in ("get", "generate", "rotate", "clear"):
        return {"ok": False, "error": "invalid action"}
    now = int(time.time() * 1000)
    with _LOCK:
        store = _load_all()
        wf = store["workflows"].get(wfId)
        if not wf:
            return {"ok": False, "error": "not found", "error_key": "err_workflow_not_found"}
        current = wf.get("webhookSecret") or ""
        changed = False
        if action == "generate":
            if not current:
                current = _gen_webhook_secret(); changed = True
        elif action == "rotate":
            current = _gen_webhook_secret(); changed = True
        elif action == "clear":
            if current:
                current = ""; changed = True
        if changed:
            wf["webhookSecret"] = current
            wf["updatedAt"] = now
            store["workflows"][wfId] = wf
            _dump_all(store)
    return {"ok": True, "id": wfId, "secret": current, "changed": changed, "updatedAt": now if changed else wf.get("updatedAt", 0)}


def api_workflow_webhook(wfId: str, body: dict | None = None, secret_header: str = "") -> dict:
    """외부 Webhook 트리거 — POST /api/workflows/webhook/{wfId}.

    외부 시스템(GitHub Actions, Slack, cron 등)에서 HTTP 호출로 워크플로우 실행.
    body 의 내용은 start 노드 다음의 첫 session/subagent 노드 입력으로 주입됨.

    body: {input?: "텍스트", metadata?: {...}} (선택)

    인증 (v2.23.0~):
      - 워크플로우마다 `webhookSecret` 필드가 저장되며, 호출 시 `X-Webhook-Secret` 헤더가 필수.
      - secret 이 비어있으면 (생성 전) 401 거부. 에디터에서 먼저 secret 을 발급해야 함.
      - 비교는 `hmac.compare_digest` 로 타이밍 공격 방지.
    """
    if not (isinstance(wfId, str) and _WF_ID_RE.match(wfId)):
        return {"ok": False, "error": "invalid workflow id", "error_key": "err_invalid_id"}

    with _LOCK:
        store = _load_all()
        wf = store["workflows"].get(wfId)
        if not wf:
            return {"ok": False, "error": "workflow not found", "error_key": "err_workflow_not_found"}
        expected_secret = wf.get("webhookSecret") or ""
        if not expected_secret:
            return {"ok": False, "error": "webhook secret not configured — generate one in the editor",
                    "error_key": "err_webhook_no_secret"}
        provided = secret_header or ""
        if not hmac.compare_digest(expected_secret, provided):
            return {"ok": False, "error": "invalid webhook secret", "error_key": "err_webhook_bad_secret"}
        cyc = _check_dag(wf.get("nodes", []), wf.get("edges", []))
        if cyc:
            return {"ok": False, "error": cyc[0], "error_key": "err_workflow_cycle"}
        runId = _new_run_id()
        run_entry = {
            "id": runId,
            "workflowId": wfId,
            "status": "running",
            "startedAt": int(time.time() * 1000),
            "finishedAt": 0,
            "currentNodeId": None,
            "nodeResults": {},
            "iteration": 0,
            "error": None,
            "trigger": "webhook",
            "webhookInput": (body or {}).get("input", "") if isinstance(body, dict) else "",
        }
        store["runs"][runId] = run_entry
        _dump_all(store)
    # v2.44.0 — seed in-memory run cache.
    _runs_cache_set(runId, dict(run_entry))

    # webhook 입력을 start 다음 노드에 주입
    webhook_input = ((body or {}).get("input") or "") if isinstance(body, dict) else ""
    extra_inputs = {}
    if webhook_input:
        target_nid = _find_feedback_target(wf.get("nodes", []), wf.get("edges", []))
        if target_nid:
            extra_inputs[target_nid] = webhook_input

    def _run():
        try:
            ok, _results, _out = _run_one_iteration(wf, runId, 0, extra_inputs)
            def _finalize(r: dict) -> None:
                r["status"] = "ok" if ok else "err"
                r["finishedAt"] = int(time.time() * 1000)
            _runs_cache_update(runId, _finalize)
            _persist_run(runId)
            _runs_cache_pop(runId)
        except Exception as e:
            log.exception("webhook run failed: %s", e)
            def _finalize_err(r: dict) -> None:
                r["status"] = "err"
                r["error"] = str(e)
                r["finishedAt"] = int(time.time() * 1000)
            _runs_cache_update(runId, _finalize_err)
            _persist_run(runId)
            _runs_cache_pop(runId)

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "runId": runId, "workflowId": wfId, "trigger": "webhook"}


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
    max_polls = 3600  # 최대 30분 (0.5초 × 3600)

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

        time.sleep(0.5)

    # 타임아웃
    _sse("timeout", json.dumps({"error": "stream timeout"}))


_TPL_ID_RE = re.compile(r"^tpl-[0-9]{10,14}-[a-z0-9]{3,6}$")


def _new_tpl_id() -> str:
    return f"tpl-{int(time.time()*1000)}-{uuid.uuid4().hex[:4]}"


BUILTIN_TEMPLATES: list[dict] = [
    {
        "id": "bt-multi-ai-compare", "name": "멀티 AI 비교", "icon": "🔬", "builtin": True,
        "description": "동일 프롬프트를 Claude, GPT, Gemini에 동시 전송하여 결과 비교",
        "category": "analysis",
        "nodes": [
            {"id": "n-start", "type": "start", "x": 80, "y": 200, "title": "시작", "data": {}},
            {"id": "n-claude", "type": "session", "x": 320, "y": 80, "title": "Claude", "data": {"subject": "분석 요청", "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-gpt", "type": "session", "x": 320, "y": 200, "title": "GPT", "data": {"subject": "분석 요청", "assignee": "openai:gpt-4.1-mini", "inputsMode": "concat"}},
            {"id": "n-gemini", "type": "session", "x": 320, "y": 320, "title": "Gemini", "data": {"subject": "분석 요청", "assignee": "gemini:gemini-2.5-flash", "inputsMode": "concat"}},
            {"id": "n-merge", "type": "merge", "x": 560, "y": 200, "title": "결과 합류", "data": {"mergeMode": "all"}},
            {"id": "n-out", "type": "output", "x": 760, "y": 200, "title": "비교 결과", "data": {"exportTo": ""}},
        ],
        "edges": [
            {"id": "e1", "from": "n-start", "to": "n-claude", "fromPort": "out", "toPort": "in"},
            {"id": "e2", "from": "n-start", "to": "n-gpt", "fromPort": "out", "toPort": "in"},
            {"id": "e3", "from": "n-start", "to": "n-gemini", "fromPort": "out", "toPort": "in"},
            {"id": "e4", "from": "n-claude", "to": "n-merge", "fromPort": "out", "toPort": "in"},
            {"id": "e5", "from": "n-gpt", "to": "n-merge", "fromPort": "out", "toPort": "in"},
            {"id": "e6", "from": "n-gemini", "to": "n-merge", "fromPort": "out", "toPort": "in"},
            {"id": "e7", "from": "n-merge", "to": "n-out", "fromPort": "out", "toPort": "in"},
        ],
    },
    {
        "id": "bt-rag-pipeline", "name": "RAG 파이프라인", "icon": "🔍", "builtin": True,
        "description": "문서 임베딩 → 검색 → AI 응답 생성 파이프라인",
        "category": "ai",
        "nodes": [
            {"id": "n-start", "type": "start", "x": 80, "y": 160, "title": "시작", "data": {}},
            {"id": "n-embed", "type": "embedding", "x": 300, "y": 160, "title": "문서 임베딩", "data": {"provider": "ollama-api", "model": "bge-m3", "outputFormat": "json"}},
            {"id": "n-search", "type": "http", "x": 520, "y": 160, "title": "벡터 검색", "data": {"url": "http://localhost:8000/search", "method": "POST", "body": '{"query": "{{input}}"}', "extractPath": "results"}},
            {"id": "n-gen", "type": "session", "x": 740, "y": 160, "title": "답변 생성", "data": {"subject": "검색 결과 기반 답변", "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-out", "type": "output", "x": 960, "y": 160, "title": "최종 답변", "data": {}},
        ],
        "edges": [
            {"id": "e1", "from": "n-start", "to": "n-embed", "fromPort": "out", "toPort": "in"},
            {"id": "e2", "from": "n-embed", "to": "n-search", "fromPort": "out", "toPort": "in"},
            {"id": "e3", "from": "n-search", "to": "n-gen", "fromPort": "out", "toPort": "in"},
            {"id": "e4", "from": "n-gen", "to": "n-out", "fromPort": "out", "toPort": "in"},
        ],
    },
    {
        "id": "bt-code-review", "name": "코드 리뷰 파이프라인", "icon": "🔍", "builtin": True,
        "description": "보안 검사 → 코드 리뷰 → 결과 취합",
        "category": "dev",
        "nodes": [
            {"id": "n-start", "type": "start", "x": 80, "y": 180, "title": "코드 입력", "data": {}},
            {"id": "n-sec", "type": "subagent", "x": 320, "y": 80, "title": "보안 리뷰", "data": {"subject": "보안 취약점 검사", "agentRole": "security-reviewer", "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-review", "type": "subagent", "x": 320, "y": 280, "title": "코드 리뷰", "data": {"subject": "코드 품질 리뷰", "agentRole": "code-reviewer", "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-agg", "type": "aggregate", "x": 560, "y": 180, "title": "결과 취합", "data": {"mode": "concat"}},
            {"id": "n-out", "type": "output", "x": 760, "y": 180, "title": "리뷰 보고서", "data": {}},
        ],
        "edges": [
            {"id": "e1", "from": "n-start", "to": "n-sec", "fromPort": "out", "toPort": "in"},
            {"id": "e2", "from": "n-start", "to": "n-review", "fromPort": "out", "toPort": "in"},
            {"id": "e3", "from": "n-sec", "to": "n-agg", "fromPort": "out", "toPort": "in"},
            {"id": "e4", "from": "n-review", "to": "n-agg", "fromPort": "out", "toPort": "in"},
            {"id": "e5", "from": "n-agg", "to": "n-out", "fromPort": "out", "toPort": "in"},
        ],
    },
    {
        "id": "bt-data-etl", "name": "데이터 ETL", "icon": "📊", "builtin": True,
        "description": "API 데이터 수집 → 변환 → AI 분석 → 리포트 생성",
        "category": "data",
        "nodes": [
            {"id": "n-start", "type": "start", "x": 80, "y": 160, "title": "시작", "data": {}},
            {"id": "n-fetch", "type": "http", "x": 280, "y": 160, "title": "데이터 수집", "data": {"url": "", "method": "GET"}},
            {"id": "n-transform", "type": "transform", "x": 480, "y": 160, "title": "데이터 변환", "data": {"transformType": "json_extract", "jsonPath": "data"}},
            {"id": "n-analyze", "type": "session", "x": 680, "y": 160, "title": "AI 분석", "data": {"subject": "수집 데이터 분석", "assignee": "claude:sonnet"}},
            {"id": "n-out", "type": "output", "x": 880, "y": 160, "title": "리포트", "data": {}},
        ],
        "edges": [
            {"id": "e1", "from": "n-start", "to": "n-fetch", "fromPort": "out", "toPort": "in"},
            {"id": "e2", "from": "n-fetch", "to": "n-transform", "fromPort": "out", "toPort": "in"},
            {"id": "e3", "from": "n-transform", "to": "n-analyze", "fromPort": "out", "toPort": "in"},
            {"id": "e4", "from": "n-analyze", "to": "n-out", "fromPort": "out", "toPort": "in"},
        ],
    },
    {
        "id": "bt-retry-robust", "name": "재시도 워크플로우", "icon": "🔁", "builtin": True,
        "description": "에러 시 자동 재시도 + 실패 핸들링",
        "category": "pattern",
        "nodes": [
            {"id": "n-start", "type": "start", "x": 80, "y": 160, "title": "시작", "data": {}},
            {"id": "n-retry", "type": "retry", "x": 280, "y": 160, "title": "재시도 설정", "data": {"maxRetries": 3, "backoffMs": 2000, "backoffMultiplier": 2.0}},
            {"id": "n-work", "type": "session", "x": 480, "y": 160, "title": "작업 실행", "data": {"subject": "API 호출", "assignee": "claude:sonnet"}},
            {"id": "n-err", "type": "error_handler", "x": 480, "y": 320, "title": "에러 핸들러", "data": {"onError": "default", "defaultOutput": "작업 실패 — 관리자에게 알림"}},
            {"id": "n-out", "type": "output", "x": 680, "y": 160, "title": "결과", "data": {}},
        ],
        "edges": [
            {"id": "e1", "from": "n-start", "to": "n-retry", "fromPort": "out", "toPort": "in"},
            {"id": "e2", "from": "n-retry", "to": "n-work", "fromPort": "out", "toPort": "in"},
            {"id": "e3", "from": "n-work", "to": "n-out", "fromPort": "out", "toPort": "in"},
            {"id": "e4", "from": "n-work", "to": "n-err", "fromPort": "out", "toPort": "in"},
        ],
    },

    # ── v2.25.0: OMC 실행 모드 4종 (autopilot / ralph / ultrawork / deep-interview) ──
    {
        "id": "bt-autopilot", "name": "Autopilot", "icon": "🚀", "builtin": True,
        "description": "사용자 확인 없이 요구사항 → 실행 → 검증까지 단일 흐름으로 끝까지 돌리는 자율 파이프라인 (OMC /autopilot 에 대응).",
        "category": "pattern",
        "nodes": [
            {"id": "n-start", "type": "start", "x": 80, "y": 200, "title": "요구사항", "data": {}},
            {"id": "n-plan", "type": "session", "x": 300, "y": 200, "title": "계획 수립",
             "data": {"subject": "요구사항을 받아 실행 계획 수립 — 단계별 체크리스트 생성",
                      "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-exec", "type": "session", "x": 520, "y": 200, "title": "실행",
             "data": {"subject": "계획에 따라 작업 수행 — 코드/문서 결과물 출력",
                      "assignee": "claude:opus", "inputsMode": "concat"}},
            {"id": "n-verify", "type": "session", "x": 740, "y": 200, "title": "검증",
             "data": {"subject": "결과물이 요구사항을 만족하는지 검증 — PASS/FAIL 과 근거 리포트",
                      "assignee": "claude:haiku", "inputsMode": "concat"}},
            {"id": "n-out", "type": "output", "x": 960, "y": 200, "title": "최종 결과", "data": {}},
        ],
        "edges": [
            {"id": "e1", "from": "n-start",  "to": "n-plan",   "fromPort": "out", "toPort": "in"},
            {"id": "e2", "from": "n-plan",   "to": "n-exec",   "fromPort": "out", "toPort": "in"},
            {"id": "e3", "from": "n-exec",   "to": "n-verify", "fromPort": "out", "toPort": "in"},
            {"id": "e4", "from": "n-verify", "to": "n-out",    "fromPort": "out", "toPort": "in"},
        ],
    },
    {
        "id": "bt-ralph", "name": "Ralph — verify until pass", "icon": "🔁", "builtin": True,
        "description": "완료 기준 통과할 때까지 verify → fix 루프를 반복 (OMC /ralph 에 대응). 최대 5회 반복, 피드백 자동 주입.",
        "category": "pattern",
        "nodes": [
            {"id": "n-start", "type": "start", "x": 80, "y": 200, "title": "작업 지시", "data": {}},
            {"id": "n-do", "type": "session", "x": 300, "y": 200, "title": "작업/수정",
             "data": {"subject": "피드백이 있으면 반영해 수정, 없으면 초기 작업 수행",
                      "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-verify", "type": "session", "x": 520, "y": 200, "title": "검증",
             "data": {"subject": "결과물이 요구사항을 만족하면 'PASS' 로 시작, 아니면 'FAIL — <이유>' 로 시작",
                      "assignee": "claude:haiku", "inputsMode": "concat"}},
            {"id": "n-branch", "type": "branch", "x": 740, "y": 200, "title": "PASS?",
             "data": {"conditionType": "contains", "conditionValue": "PASS"}},
            {"id": "n-out", "type": "output", "x": 960, "y": 120, "title": "완료", "data": {}},
        ],
        "edges": [
            {"id": "e1", "from": "n-start",  "to": "n-do",     "fromPort": "out",   "toPort": "in"},
            {"id": "e2", "from": "n-do",     "to": "n-verify", "fromPort": "out",   "toPort": "in"},
            {"id": "e3", "from": "n-verify", "to": "n-branch", "fromPort": "out",   "toPort": "in"},
            {"id": "e4", "from": "n-branch", "to": "n-out",    "fromPort": "true",  "toPort": "in"},
        ],
        "repeat": {
            "enabled": True,
            "maxIterations": 5,
            "intervalSeconds": 0,
            "feedbackNote": "이전 검증에서 FAIL 로 판정된 항목을 해결하도록 수정 방향을 제시하세요.",
            "feedbackNodeId": "n-do",
        },
    },
    {
        "id": "bt-ultrawork", "name": "Ultrawork (5병렬)", "icon": "⚡", "builtin": True,
        "description": "동일 작업을 5개 병렬 에이전트로 분할 실행 후 취합 (OMC /ultrawork 에 대응). 속도 우선, 비용 5배.",
        "category": "pattern",
        "nodes": [
            {"id": "n-start", "type": "start", "x": 80, "y": 280, "title": "작업 입력", "data": {}},
            {"id": "n-a", "type": "session", "x": 300, "y":  80, "title": "Agent A (Sonnet)",
             "data": {"subject": "작업의 1/5 담당 — 섹션 A 처리", "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-b", "type": "session", "x": 300, "y": 180, "title": "Agent B (Sonnet)",
             "data": {"subject": "작업의 2/5 담당 — 섹션 B 처리", "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-c", "type": "session", "x": 300, "y": 280, "title": "Agent C (Haiku)",
             "data": {"subject": "작업의 3/5 담당 — 섹션 C 처리", "assignee": "claude:haiku", "inputsMode": "concat"}},
            {"id": "n-d", "type": "session", "x": 300, "y": 380, "title": "Agent D (Haiku)",
             "data": {"subject": "작업의 4/5 담당 — 섹션 D 처리", "assignee": "claude:haiku", "inputsMode": "concat"}},
            {"id": "n-e", "type": "session", "x": 300, "y": 480, "title": "Agent E (Haiku)",
             "data": {"subject": "작업의 5/5 담당 — 섹션 E 처리", "assignee": "claude:haiku", "inputsMode": "concat"}},
            {"id": "n-merge", "type": "merge", "x": 540, "y": 280, "title": "취합", "data": {"mergeMode": "all"}},
            {"id": "n-out", "type": "output", "x": 760, "y": 280, "title": "통합 결과", "data": {}},
        ],
        "edges": [
            {"id": "e1", "from": "n-start", "to": "n-a", "fromPort": "out", "toPort": "in"},
            {"id": "e2", "from": "n-start", "to": "n-b", "fromPort": "out", "toPort": "in"},
            {"id": "e3", "from": "n-start", "to": "n-c", "fromPort": "out", "toPort": "in"},
            {"id": "e4", "from": "n-start", "to": "n-d", "fromPort": "out", "toPort": "in"},
            {"id": "e5", "from": "n-start", "to": "n-e", "fromPort": "out", "toPort": "in"},
            {"id": "e6", "from": "n-a", "to": "n-merge", "fromPort": "out", "toPort": "in"},
            {"id": "e7", "from": "n-b", "to": "n-merge", "fromPort": "out", "toPort": "in"},
            {"id": "e8", "from": "n-c", "to": "n-merge", "fromPort": "out", "toPort": "in"},
            {"id": "e9", "from": "n-d", "to": "n-merge", "fromPort": "out", "toPort": "in"},
            {"id": "e10","from": "n-e", "to": "n-merge", "fromPort": "out", "toPort": "in"},
            {"id": "e11","from": "n-merge", "to": "n-out", "fromPort": "out", "toPort": "in"},
        ],
    },
    {
        "id": "bt-deep-interview", "name": "Deep Interview", "icon": "🧐", "builtin": True,
        "description": "모호한 요구사항을 Socratic 질문으로 명확화한 후 설계까지 (OMC /deep-interview 에 대응).",
        "category": "pattern",
        "nodes": [
            {"id": "n-start", "type": "start", "x": 80, "y": 200, "title": "초기 요청", "data": {}},
            {"id": "n-clarify", "type": "session", "x": 300, "y": 200, "title": "1차 질문",
             "data": {"subject": "요구사항에서 모호한 부분을 찾아 3~5개의 구체적 질문 생성",
                      "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-answer", "type": "session", "x": 520, "y": 200, "title": "예상 답변",
             "data": {"subject": "질문에 대해 합리적인 기본값/권장 답변을 제시하고 각각 근거 표기",
                      "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-spec", "type": "session", "x": 740, "y": 200, "title": "설계 문서",
             "data": {"subject": "명확화된 요구사항을 기반으로 기술 설계 문서 작성 (섹션: 목표/제약/아키/리스크)",
                      "assignee": "claude:opus", "inputsMode": "concat"}},
            {"id": "n-out", "type": "output", "x": 960, "y": 200, "title": "설계 보고서", "data": {}},
        ],
        "edges": [
            {"id": "e1", "from": "n-start",   "to": "n-clarify", "fromPort": "out", "toPort": "in"},
            {"id": "e2", "from": "n-clarify", "to": "n-answer",  "fromPort": "out", "toPort": "in"},
            {"id": "e3", "from": "n-answer",  "to": "n-spec",    "fromPort": "out", "toPort": "in"},
            {"id": "e4", "from": "n-spec",    "to": "n-out",     "fromPort": "out", "toPort": "in"},
        ],
    },

    # v2.27.0 — OMC /team 5단계 파이프라인 (Plan → PRD → 3-병렬 Exec → Verify → Fix 루프)
    {
        "id": "bt-team-sprint", "name": "Team Sprint (Plan→PRD→Exec×3→Verify→Fix)",
        "icon": "🏗️", "builtin": True,
        "description": "OMC /team 스타일 5단계: 계획(Opus)→요구사항명세(Sonnet)→3-병렬 실행(Sonnet)→취합→검증(Haiku)→실패 시 수정. Repeat 3회까지 자동 verify-fix 루프.",
        "category": "pattern",
        "nodes": [
            {"id": "n-start", "type": "start", "x":  80, "y": 300, "title": "스프린트 요청", "data": {}},
            {"id": "n-plan",  "type": "session", "x": 260, "y": 300, "title": "🧭 Plan",
             "data": {"subject": "전체 아키텍처 · 범위 · 리스크를 5섹션으로 설계 (목표/제약/접근/모듈/순서)",
                      "assignee": "claude:opus", "inputsMode": "concat"}},
            {"id": "n-prd",   "type": "session", "x": 460, "y": 300, "title": "📋 PRD",
             "data": {"subject": "계획을 받아 각 모듈별 세부 요구사항·수용 조건(Acceptance Criteria)·테스트 포인트 작성",
                      "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-exec-a", "type": "session", "x": 680, "y": 180, "title": "👷 Exec A",
             "data": {"subject": "PRD 의 모듈 1/3 담당 — 코드/문서 결과물과 실행 결과 보고",
                      "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-exec-b", "type": "session", "x": 680, "y": 300, "title": "👷 Exec B",
             "data": {"subject": "PRD 의 모듈 2/3 담당 — 코드/문서 결과물과 실행 결과 보고",
                      "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-exec-c", "type": "session", "x": 680, "y": 420, "title": "👷 Exec C",
             "data": {"subject": "PRD 의 모듈 3/3 담당 — 코드/문서 결과물과 실행 결과 보고",
                      "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-merge", "type": "merge", "x": 880, "y": 300, "title": "🔀 취합",
             "data": {"mergeMode": "all"}},
            {"id": "n-verify", "type": "session", "x": 1080, "y": 300, "title": "🔎 Verify",
             "data": {"subject": "취합된 결과물을 PRD 수용 조건과 대조. 통과면 'PASS', 아니면 'FAIL — <실패 항목 목록>' 으로 시작",
                      "assignee": "claude:haiku", "inputsMode": "concat"}},
            {"id": "n-branch", "type": "branch", "x": 1280, "y": 300, "title": "PASS?",
             "data": {"conditionType": "contains", "conditionValue": "PASS"}},
            {"id": "n-fix",   "type": "session", "x": 1280, "y": 460, "title": "🛠️ Fix",
             "data": {"subject": "실패한 항목만 선택적으로 수정. 변경점과 근거 명시.",
                      "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-out",   "type": "output", "x": 1480, "y": 220, "title": "✅ 완료", "data": {}},
        ],
        "edges": [
            {"id": "e01", "from": "n-start",  "to": "n-plan",   "fromPort": "out",   "toPort": "in"},
            {"id": "e02", "from": "n-plan",   "to": "n-prd",    "fromPort": "out",   "toPort": "in"},
            {"id": "e03", "from": "n-prd",    "to": "n-exec-a", "fromPort": "out",   "toPort": "in"},
            {"id": "e04", "from": "n-prd",    "to": "n-exec-b", "fromPort": "out",   "toPort": "in"},
            {"id": "e05", "from": "n-prd",    "to": "n-exec-c", "fromPort": "out",   "toPort": "in"},
            {"id": "e06", "from": "n-exec-a", "to": "n-merge",  "fromPort": "out",   "toPort": "in"},
            {"id": "e07", "from": "n-exec-b", "to": "n-merge",  "fromPort": "out",   "toPort": "in"},
            {"id": "e08", "from": "n-exec-c", "to": "n-merge",  "fromPort": "out",   "toPort": "in"},
            {"id": "e09", "from": "n-merge",  "to": "n-verify", "fromPort": "out",   "toPort": "in"},
            {"id": "e10", "from": "n-verify", "to": "n-branch", "fromPort": "out",   "toPort": "in"},
            {"id": "e11", "from": "n-branch", "to": "n-out",    "fromPort": "true",  "toPort": "in"},
            {"id": "e12", "from": "n-branch", "to": "n-fix",    "fromPort": "false", "toPort": "in"},
        ],
        "repeat": {
            "enabled": True,
            "maxIterations": 3,
            "intervalSeconds": 0,
            "feedbackNote": "이전 Fix 결과를 반영해 Exec 단계에서 실패 항목을 우선 처리하세요.",
            "feedbackNodeId": "n-plan",
        },
    },

    # ── v2.34.0: Crew (Planner + Personas + Slack approval + Obsidian) ──
    {
        "id": "bt-crew", "name": "페르소나 크루", "icon": "🧑‍✈️", "builtin": True,
        "description": "기획자(Planner) → 페르소나 3명 병렬 작업 → 보고 취합 → "
                       "Slack 어드민 승인 → Obsidian 기록 → 다음 사이클로 루프. "
                       "Wizard 탭에서 폼만 채우면 더 쉽게 만들 수 있습니다.",
        "category": "pattern",
        "nodes": [
            {"id": "n-start", "type": "start", "x": 80, "y": 240, "title": "시작", "data": {}},
            {"id": "n-plan",  "type": "session", "x": 280, "y": 240, "title": "🧭 기획자",
             "data": {"subject": "프로젝트 목표를 단계별 작업으로 쪼개고 페르소나에 분배",
                      "description": "각 페르소나별 지시 블록을 '### <role>' 헤딩으로 구분하세요.",
                      "assignee": "claude:opus", "agentRole": "planner",
                      "inputsMode": "concat", "continueFromPrev": True}},
            {"id": "n-p1",    "type": "subagent", "x": 520, "y": 100, "title": "👤 Researcher",
             "data": {"subject": "Researcher 작업", "agentRole": "researcher",
                      "assignee": "claude:sonnet", "inputsMode": "concat"}},
            {"id": "n-p2",    "type": "subagent", "x": 520, "y": 240, "title": "👤 Builder",
             "data": {"subject": "Builder 작업", "agentRole": "builder",
                      "assignee": "gemini:gemini-2.5-pro", "inputsMode": "concat"}},
            {"id": "n-p3",    "type": "subagent", "x": 520, "y": 380, "title": "👤 Reviewer",
             "data": {"subject": "Reviewer 작업", "agentRole": "reviewer",
                      "assignee": "ollama:llama3.1", "inputsMode": "concat"}},
            {"id": "n-agg",   "type": "aggregate", "x": 760, "y": 240, "title": "🧩 보고 취합",
             "data": {"mode": "concat"}},
            {"id": "n-slack", "type": "slack_approval", "x": 980, "y": 240, "title": "🛂 어드민 게이트",
             "data": {"channel": "", "messageTemplate": ":memo: 사이클 보고 도착",
                      "timeoutSeconds": 300, "pollIntervalSeconds": 5,
                      "onTimeout": "default",
                      "defaultOutput": "타임아웃 — 자율 판단으로 계속 진행",
                      "includeInput": True}},
            {"id": "n-obs",   "type": "obsidian_log", "x": 1200, "y": 240, "title": "📝 옵시디언 기록",
             "data": {"vaultPath": "~/ObsidianVault", "project": "lazyclaude",
                      "heading": "crew cycle", "tagsCsv": "crew",
                      "passThrough": True}},
            {"id": "n-out",   "type": "output", "x": 1420, "y": 240, "title": "📤 결과", "data": {}},
        ],
        "edges": [
            {"id": "e1", "from": "n-start", "to": "n-plan",  "fromPort": "out", "toPort": "in"},
            {"id": "e2", "from": "n-plan",  "to": "n-p1",    "fromPort": "out", "toPort": "in"},
            {"id": "e3", "from": "n-plan",  "to": "n-p2",    "fromPort": "out", "toPort": "in"},
            {"id": "e4", "from": "n-plan",  "to": "n-p3",    "fromPort": "out", "toPort": "in"},
            {"id": "e5", "from": "n-p1",    "to": "n-agg",   "fromPort": "out", "toPort": "in"},
            {"id": "e6", "from": "n-p2",    "to": "n-agg",   "fromPort": "out", "toPort": "in"},
            {"id": "e7", "from": "n-p3",    "to": "n-agg",   "fromPort": "out", "toPort": "in"},
            {"id": "e8", "from": "n-agg",   "to": "n-slack", "fromPort": "out", "toPort": "in"},
            {"id": "e9", "from": "n-slack", "to": "n-obs",   "fromPort": "out", "toPort": "in"},
            {"id": "e10","from": "n-obs",   "to": "n-out",   "fromPort": "out", "toPort": "in"},
        ],
        "repeat": {
            "enabled": True,
            "maxIterations": 3,
            "intervalSeconds": 0,
            "feedbackNote": "이전 사이클 보고를 검토하고 미해결 항목과 새 리스크를 반영해 다음 단계 업무를 페르소나별로 다시 분배하세요.",
            "feedbackNodeId": "n-plan",
        },
    },
]


def api_workflow_templates_list(query: dict | None = None) -> dict:
    store = _load_all()
    out = []
    # 빌트인 템플릿
    for bt in BUILTIN_TEMPLATES:
        out.append({
            "id": bt["id"],
            "name": bt["name"],
            "description": bt.get("description", ""),
            "icon": bt.get("icon", "📋"),
            "category": bt.get("category", "general"),
            "nodeCount": len(bt.get("nodes", [])),
            "edgeCount": len(bt.get("edges", [])),
            "builtin": True,
            "createdAt": 0,
        })
    # 커스텀 템플릿
    for tid, tpl in (store.get("customTemplates") or {}).items():
        out.append({
            "id": tid,
            "name": tpl.get("name", "Untitled"),
            "description": tpl.get("description", ""),
            "icon": tpl.get("icon") or "💾",
            "category": tpl.get("category", "custom"),
            "nodeCount": len(tpl.get("nodes") or []),
            "edgeCount": len(tpl.get("edges") or []),
            "builtin": False,
            "createdAt": tpl.get("createdAt", 0),
        })
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
    # 빌트인 템플릿 먼저 확인
    bt = next((t for t in BUILTIN_TEMPLATES if t["id"] == tid), None)
    if bt:
        return {"ok": True, "template": bt, "builtin": True}
    if not (isinstance(tid, str) and _TPL_ID_RE.match(tid)):
        return {"ok": False, "error": "invalid id"}
    store = _load_all()
    tpl = (store.get("customTemplates") or {}).get(tid)
    if not tpl:
        return {"ok": False, "error": "not found"}
    return {"ok": True, "template": tpl}


def api_workflow_export(body: dict) -> dict:
    """워크플로우 JSON export. body: {id}. 반환: 워크플로우 전체 JSON (import 호환)."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    wfId = body.get("id")
    if not (isinstance(wfId, str) and _WF_ID_RE.match(wfId)):
        return {"ok": False, "error": "invalid id"}
    store = _load_all()
    wf = store["workflows"].get(wfId)
    if not wf:
        return {"ok": False, "error": "not found"}
    export = {
        "exportVersion": 1,
        "exportedAt": int(time.time() * 1000),
        "workflow": wf,
    }
    return {"ok": True, "export": export}


def api_workflow_import(body: dict) -> dict:
    """워크플로우 JSON import. body: {export: {exportVersion, workflow}} 또는 {workflow: {...}}.

    새 ID 를 부여하여 저장. 기존 워크플로우와 충돌 없음.
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}

    # export 래퍼가 있으면 풀기
    raw_wf = body.get("workflow")
    if not raw_wf and isinstance(body.get("export"), dict):
        raw_wf = body["export"].get("workflow")
    if not isinstance(raw_wf, dict):
        return {"ok": False, "error": "workflow object required"}

    wf_clean = _sanitize_workflow(raw_wf)
    if wf_clean is None:
        return {"ok": False, "error": "invalid workflow structure"}

    now = int(time.time() * 1000)
    with _LOCK:
        store = _load_all()
        new_id = _new_wf_id()
        wf_clean["id"] = new_id
        wf_clean["createdAt"] = now
        wf_clean["updatedAt"] = now
        # 이름에 (imported) 추가
        orig_name = wf_clean.get("name", "Untitled")
        wf_clean["name"] = f"{orig_name} (imported)"
        store["workflows"][new_id] = wf_clean
        _dump_all(store)

    return {"ok": True, "id": new_id, "name": wf_clean["name"]}


def api_workflow_run_diff(body: dict) -> dict:
    """POST /api/workflows/run-diff — 두 run 간 per-node 상태/지연 비교.

    body: {a, b} — a (이전) / b (이후) runId.
    반환: {ok, nodes: [{nodeId, aStatus, bStatus, aDurationMs, bDurationMs, durationDelta, statusChanged, onlyA, onlyB}]}
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}
    a = body.get("a"); b = body.get("b")
    if not (isinstance(a, str) and _RUN_ID_RE.match(a)):
        return {"ok": False, "error": "invalid a"}
    if not (isinstance(b, str) and _RUN_ID_RE.match(b)):
        return {"ok": False, "error": "invalid b"}
    store = _load_all()
    runs = store.get("runs") or {}
    ra = runs.get(a); rb = runs.get(b)
    if not ra or not rb:
        return {"ok": False, "error": "run(s) not found"}
    nra = ra.get("nodeResults") or {}
    nrb = rb.get("nodeResults") or {}
    all_ids = sorted(set(list(nra.keys()) + list(nrb.keys())))
    out = []
    total_a_in = total_a_out = total_b_in = total_b_out = 0
    total_a_cost = total_b_cost = 0.0
    for nid in all_ids:
        ax = nra.get(nid) or {}
        bx = nrb.get(nid) or {}
        ad = ax.get("durationMs") or 0
        bd = bx.get("durationMs") or 0
        ati = int(ax.get("tokensIn") or 0); ato = int(ax.get("tokensOut") or 0)
        bti = int(bx.get("tokensIn") or 0); bto = int(bx.get("tokensOut") or 0)
        aco = float(ax.get("costUsd") or 0); bco = float(bx.get("costUsd") or 0)
        total_a_in += ati; total_a_out += ato; total_a_cost += aco
        total_b_in += bti; total_b_out += bto; total_b_cost += bco
        out.append({
            "nodeId": nid,
            "aStatus": ax.get("status"),
            "bStatus": bx.get("status"),
            "aDurationMs": ad,
            "bDurationMs": bd,
            "durationDelta": bd - ad,
            "aTokensIn": ati, "aTokensOut": ato,
            "bTokensIn": bti, "bTokensOut": bto,
            "tokensInDelta": bti - ati,
            "tokensOutDelta": bto - ato,
            "aCostUsd": round(aco, 6),
            "bCostUsd": round(bco, 6),
            "costDelta": round(bco - aco, 6),
            "statusChanged": ax.get("status") != bx.get("status"),
            "onlyA": nid not in nrb,
            "onlyB": nid not in nra,
        })
    # 요약 집계
    summary = {
        "a": {
            "status": ra.get("status"),
            "duration": max(0, (ra.get("finishedAt") or 0) - (ra.get("startedAt") or 0)),
            "tokensIn": total_a_in, "tokensOut": total_a_out, "costUsd": round(total_a_cost, 6),
        },
        "b": {
            "status": rb.get("status"),
            "duration": max(0, (rb.get("finishedAt") or 0) - (rb.get("startedAt") or 0)),
            "tokensIn": total_b_in, "tokensOut": total_b_out, "costUsd": round(total_b_cost, 6),
        },
    }
    summary["durationDelta"] = summary["b"]["duration"] - summary["a"]["duration"]
    summary["tokensInDelta"] = total_b_in - total_a_in
    summary["tokensOutDelta"] = total_b_out - total_a_out
    summary["costDelta"] = round(total_b_cost - total_a_cost, 6)
    return {"ok": True, "summary": summary, "nodes": out}


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


# ═══════════════════════════════════════════
#  Cron 스케줄러 — 워크플로우 자동 실행
# ═══════════════════════════════════════════

_CRON_RE = re.compile(r"^(\*|[0-9,/-]+)\s+(\*|[0-9,/-]+)\s+(\*|[0-9,/-]+)\s+(\*|[0-9,/-]+)\s+(\*|[0-9,/-]+)$")
_SCHEDULER_THREAD = None
_SCHEDULER_STOP = threading.Event()


def _cron_field_matches(field: str, value: int) -> bool:
    """단일 cron 필드가 현재 값과 매칭되는지 확인."""
    if field == "*":
        return True
    for part in field.split(","):
        part = part.strip()
        if "/" in part:
            base, step = part.split("/", 1)
            try:
                step = int(step)
                base_val = 0 if base == "*" else int(base)
                if step > 0 and (value - base_val) % step == 0 and value >= base_val:
                    return True
            except ValueError:
                continue
        elif "-" in part:
            try:
                lo, hi = part.split("-", 1)
                if int(lo) <= value <= int(hi):
                    return True
            except ValueError:
                continue
        else:
            try:
                if int(part) == value:
                    return True
            except ValueError:
                continue
    return False


def _cron_matches_now(expr: str) -> bool:
    """cron 표현식이 현재 시각과 매칭되는지. 형식: min hour dom month dow."""
    from datetime import datetime as _dt
    m = _CRON_RE.match(expr.strip())
    if not m:
        return False
    now = _dt.now()
    fields = [m.group(i) for i in range(1, 6)]
    values = [now.minute, now.hour, now.day, now.month, now.weekday()]  # weekday: 0=Mon
    return all(_cron_field_matches(f, v) for f, v in zip(fields, values))


def api_workflow_schedule_set(body: dict) -> dict:
    """워크플로우 cron 스케줄 설정.

    body: {id, schedule: {enabled, cron, timezone?}}
    cron 형식: "*/30 * * * *" (매 30분), "0 9 * * 1-5" (평일 9시)
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    wfId = body.get("id")
    if not (isinstance(wfId, str) and _WF_ID_RE.match(wfId)):
        return {"ok": False, "error": "invalid id"}
    schedule = body.get("schedule") or {}
    if not isinstance(schedule, dict):
        return {"ok": False, "error": "schedule must be object"}

    cron_expr = (schedule.get("cron") or "").strip()
    enabled = bool(schedule.get("enabled", False))

    if enabled and cron_expr and not _CRON_RE.match(cron_expr):
        return {"ok": False, "error": "invalid cron expression", "error_key": "err_invalid_cron"}

    with _LOCK:
        store = _load_all()
        wf = store["workflows"].get(wfId)
        if not wf:
            return {"ok": False, "error": "not found"}
        wf["schedule"] = {
            "enabled": enabled,
            "cron": cron_expr,
            "timezone": (schedule.get("timezone") or "").strip()[:40],
            "lastRunAt": wf.get("schedule", {}).get("lastRunAt", 0),
        }
        wf["updatedAt"] = int(time.time() * 1000)
        _dump_all(store)
    return {"ok": True, "id": wfId, "schedule": wf["schedule"]}


def api_workflow_history(query: dict) -> dict:
    """워크플로우 버전 히스토리. GET /api/workflows/history?id=..."""
    wfId = ((query.get("id", [""])[0] if isinstance(query.get("id"), list) else query.get("id", "")) or "").strip()
    if not (isinstance(wfId, str) and _WF_ID_RE.match(wfId)):
        return {"ok": False, "error": "invalid id"}
    store = _load_all()
    history = (store.get("history") or {}).get(wfId, [])
    # snapshot 의 nodes/edges 는 요약만 (전체는 restore 시)
    summaries = []
    for h in reversed(history):
        snap = h.get("snapshot") or {}
        summaries.append({
            "savedAt": h.get("savedAt", 0),
            "name": h.get("name", ""),
            "nodeCount": h.get("nodeCount", 0),
            "edgeCount": h.get("edgeCount", 0),
        })
    return {"ok": True, "id": wfId, "history": summaries, "count": len(summaries)}


def api_workflow_restore(body: dict) -> dict:
    """히스토리 버전 복원. body: {id, savedAt}"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    wfId = body.get("id")
    saved_at = body.get("savedAt")
    if not (isinstance(wfId, str) and _WF_ID_RE.match(wfId)):
        return {"ok": False, "error": "invalid id"}
    with _LOCK:
        store = _load_all()
        history = (store.get("history") or {}).get(wfId, [])
        target = next((h for h in history if h.get("savedAt") == saved_at), None)
        if not target:
            return {"ok": False, "error": "version not found"}
        snap = target.get("snapshot") or {}
        wf = store["workflows"].get(wfId)
        if not wf:
            return {"ok": False, "error": "workflow not found"}
        # 현재를 히스토리에 보관 후 복원
        now = int(time.time() * 1000)
        history.append({
            "savedAt": now,
            "name": wf.get("name", ""),
            "nodeCount": len(wf.get("nodes", [])),
            "edgeCount": len(wf.get("edges", [])),
            "snapshot": {k: wf[k] for k in ("nodes", "edges", "viewport", "name", "description") if k in wf},
        })
        store.setdefault("history", {})[wfId] = history[-20:]
        # 복원 적용
        for k in ("nodes", "edges", "viewport", "name", "description"):
            if k in snap:
                wf[k] = snap[k]
        wf["updatedAt"] = now
        _dump_all(store)
    return {"ok": True, "id": wfId, "restoredFrom": saved_at}


def api_workflow_stats() -> dict:
    """전체 워크플로우 실행 통계 집계."""
    store = _load_all()
    runs = store.get("runs", {})
    total = len(runs)
    ok_count = sum(1 for r in runs.values() if r.get("status") == "ok")
    err_count = sum(1 for r in runs.values() if r.get("status") == "err")
    running = sum(1 for r in runs.values() if r.get("status") == "running")

    # 평균 소요 시간
    durations = [
        max(0, (r.get("finishedAt") or 0) - (r.get("startedAt") or 0))
        for r in runs.values() if r.get("finishedAt") and r.get("startedAt")
    ]
    avg_dur = int(sum(durations) / len(durations)) if durations else 0

    # 프로바이더별 사용 횟수 (nodeResults 에서)
    from collections import Counter
    provider_counter: Counter = Counter()
    for r in runs.values():
        for nid, nr in (r.get("nodeResults") or {}).items():
            prov = nr.get("provider", "")
            if prov:
                provider_counter[prov] += 1

    # 워크플로우별 성공률
    wf_stats: dict = {}
    for r in runs.values():
        wfId = r.get("workflowId", "")
        if not wfId:
            continue
        s = wf_stats.setdefault(wfId, {"ok": 0, "err": 0, "total": 0, "name": ""})
        s["total"] += 1
        if r.get("status") == "ok":
            s["ok"] += 1
        elif r.get("status") == "err":
            s["err"] += 1
    # 이름 매핑
    for wfId, s in wf_stats.items():
        wf = store["workflows"].get(wfId)
        s["name"] = wf.get("name", "Untitled") if wf else wfId
        s["successRate"] = round(s["ok"] / max(1, s["total"]) * 100, 1)

    # 트리거별 카운트
    trigger_counter: Counter = Counter()
    for r in runs.values():
        trigger_counter[r.get("trigger", "manual")] += 1

    return {
        "ok": True,
        "totals": {
            "runs": total, "ok": ok_count, "err": err_count, "running": running,
            "successRate": round(ok_count / max(1, total) * 100, 1),
            "avgDurationMs": avg_dur,
        },
        "byProvider": [{"provider": p, "count": n} for p, n in provider_counter.most_common(20)],
        "byWorkflow": sorted(wf_stats.values(), key=lambda x: x["total"], reverse=True)[:20],
        "byTrigger": [{"trigger": t, "count": n} for t, n in trigger_counter.most_common()],
        "workflowCount": len(store["workflows"]),
        "scheduleCount": sum(1 for wf in store["workflows"].values()
                             if (wf.get("schedule") or {}).get("enabled")),
    }


def api_workflow_schedule_list() -> dict:
    """스케줄이 설정된 워크플로우 목록."""
    store = _load_all()
    out = []
    for wfId, wf in store["workflows"].items():
        sched = wf.get("schedule") or {}
        if sched.get("cron"):
            out.append({
                "id": wfId,
                "name": wf.get("name", "Untitled"),
                "schedule": sched,
                "nodeCount": len(wf.get("nodes", [])),
            })
    return {"ok": True, "schedules": out}


def _scheduler_loop() -> None:
    """60초 간격으로 cron 매칭 검사 + 워크플로우 자동 실행."""
    log.info("workflow scheduler started")
    while not _SCHEDULER_STOP.wait(60):
        try:
            store = _load_all()
            now_ms = int(time.time() * 1000)
            for wfId, wf in store["workflows"].items():
                sched = wf.get("schedule") or {}
                if not sched.get("enabled") or not sched.get("cron"):
                    continue
                last = sched.get("lastRunAt", 0) or 0
                # 같은 분에 중복 실행 방지 (60초 이내)
                if now_ms - last < 55000:
                    continue
                if _cron_matches_now(sched["cron"]):
                    log.info("cron trigger: %s (%s)", wfId, sched["cron"])
                    # lastRunAt 즉시 업데이트 (중복 방지)
                    with _LOCK:
                        s = _load_all()
                        if wfId in s["workflows"]:
                            s["workflows"][wfId].setdefault("schedule", {})["lastRunAt"] = now_ms
                            _dump_all(s)
                    # 실행
                    api_workflow_run({"id": wfId})
        except Exception as e:
            log.warning("scheduler error: %s", e)
    log.info("workflow scheduler stopped")


def start_scheduler() -> None:
    """서버 시작 시 호출 — 스케줄러 백그라운드 스레드 시작."""
    global _SCHEDULER_THREAD
    if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
        return
    _SCHEDULER_STOP.clear()
    _SCHEDULER_THREAD = threading.Thread(target=_scheduler_loop, daemon=True)
    _SCHEDULER_THREAD.start()


def stop_scheduler() -> None:
    """서버 종료 시 스케줄러 정지."""
    _SCHEDULER_STOP.set()
