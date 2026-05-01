"""Ralph loop engine — same-prompt iteration with hard safety guards.

Named after Geoffrey Huntley's "Ralph Wiggum loop" pattern (and Anthropic's
``claude-code/plugins/ralph-wiggum``): feed the **same** PROMPT.md back to the
model in a tight loop. Between iterations the model's prior state lives in the
filesystem + git history (not in the prompt). The loop exits when *any* of:

1. The model emits the configured ``completion_promise`` string anywhere in
   its output (default ``<promise>DONE</promise>``).
2. ``max_iterations`` reached (default 25; **required as primary safety**).
3. ``budget_usd`` exhausted (sum of per-iteration ``cost_usd`` across the run).
4. ``cancel(run_id)`` called (CLI Ctrl+C, dashboard button, agent bus event).

Why a separate module from ``server.workflows``: workflows model a DAG —
Ralph is a single repeating cell. Trying to bend the DAG executor to do this
loses the simplicity that makes Ralph valuable. We re-use
``execute_with_assignee`` so any provider works, ``agent_bus`` for live
progress (one ``ralph.<run_id>.iter`` event per iteration), and the same
``orch_runs`` SQLite shape so the dashboard's history view shows Ralph runs
alongside orchestrator runs (with ``via='ralph'``).

Optimization decisions (no hardcoding, all env-overridable):

- ``RALPH_MAX_ITER_HARD`` (default 200): an absolute ceiling enforced even if
  the caller passes a higher ``max_iterations``. Defence-in-depth against
  forgotten ``--max`` flags.
- ``RALPH_PER_ITER_TIMEOUT_S`` (default 600): single-iteration timeout —
  prevents one stuck iteration from holding the run forever.
- ``RALPH_PROGRESS_DEDUPE_MS`` (default 250): per-event dedupe in the agent
  bus already collapses identical heartbeats; we keep the cadence sane by
  only publishing when state actually changes.

The engine is thread-safe; multiple loops can run in parallel under different
``run_id``s. Each loop is its own background ``Thread`` so the HTTP caller
returns immediately with a tracking id.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from . import agent_bus
from .ai_providers import AIResponse, execute_with_assignee
from .db import _db, _db_init
from .logger import log


# ───────── Tunables (env-overridable) ─────────

_HARD_MAX_ITER       = int(os.environ.get("RALPH_MAX_ITER_HARD", "200"))
_PER_ITER_TIMEOUT_S  = int(os.environ.get("RALPH_PER_ITER_TIMEOUT_S", "600"))
_DEFAULT_MAX_ITER    = int(os.environ.get("RALPH_DEFAULT_MAX_ITER", "25"))
_DEFAULT_BUDGET_USD  = float(os.environ.get("RALPH_DEFAULT_BUDGET_USD", "5.0"))
_DEFAULT_COMPLETION  = os.environ.get("RALPH_DEFAULT_COMPLETION",
                                       "<promise>DONE</promise>")
_DEFAULT_ASSIGNEE    = os.environ.get("RALPH_DEFAULT_ASSIGNEE", "claude:sonnet")


# ───────── Schema ─────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ralph_runs (
  run_id        TEXT PRIMARY KEY,
  ts_start      INTEGER NOT NULL,
  ts_end        INTEGER,
  prompt        TEXT NOT NULL,
  assignee      TEXT NOT NULL,
  max_iter      INTEGER NOT NULL,
  completion    TEXT NOT NULL,
  budget_usd    REAL NOT NULL,
  status        TEXT NOT NULL DEFAULT 'running',  -- running|done|cancelled|max_iter|budget|error
  iterations    INTEGER NOT NULL DEFAULT 0,
  cost_usd      REAL NOT NULL DEFAULT 0.0,
  last_output   TEXT NOT NULL DEFAULT '',
  error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_ralph_runs_ts ON ralph_runs(ts_start DESC);

CREATE TABLE IF NOT EXISTS ralph_iterations (
  run_id     TEXT NOT NULL,
  idx        INTEGER NOT NULL,
  ts         INTEGER NOT NULL,
  status     TEXT NOT NULL,        -- ok|err|timeout
  output     TEXT NOT NULL DEFAULT '',
  error      TEXT,
  cost_usd   REAL NOT NULL DEFAULT 0.0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (run_id, idx)
);
"""

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        _db_init()
        with _db() as c:
            c.executescript(_SCHEMA)
        _SCHEMA_READY = True


# ───────── Run state ─────────

@dataclass
class _RunState:
    run_id: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    thread: Optional[threading.Thread] = None
    cost_so_far: float = 0.0
    iterations: int = 0
    status: str = "running"


_RUNS: dict[str, _RunState] = {}
_RUNS_LOCK = threading.Lock()


def _new_run_id() -> str:
    return "ralph-" + uuid.uuid4().hex[:10]


def _topic(run_id: str, *parts: str) -> str:
    return ".".join(("ralph", run_id, *parts))


# ───────── Public surface ─────────

def start(prompt: str, *,
          assignee: str = "",
          max_iterations: int = 0,
          completion_promise: str = "",
          budget_usd: float = 0.0,
          system_prompt: str = "",
          cwd: str = "",
          auto_commit: bool = False) -> dict:
    """Kick off a Ralph loop in a daemon thread. Returns ``{run_id, ...}`` immediately.

    All optional fields fall back to env-tunable defaults so a caller with no
    config still gets a safe run.
    """
    if not isinstance(prompt, str) or not prompt.strip():
        return {"ok": False, "error": "prompt required"}
    assignee = (assignee or _DEFAULT_ASSIGNEE).strip()
    max_iter = int(max_iterations or _DEFAULT_MAX_ITER)
    if max_iter < 1:
        max_iter = 1
    if max_iter > _HARD_MAX_ITER:
        max_iter = _HARD_MAX_ITER
    completion = (completion_promise or _DEFAULT_COMPLETION).strip() or _DEFAULT_COMPLETION
    budget = float(budget_usd or _DEFAULT_BUDGET_USD)
    if budget <= 0:
        budget = _DEFAULT_BUDGET_USD

    _ensure_schema()
    rid = _new_run_id()
    state = _RunState(run_id=rid)
    with _RUNS_LOCK:
        _RUNS[rid] = state

    try:
        with _db() as c:
            c.execute(
                "INSERT INTO ralph_runs(run_id, ts_start, prompt, assignee, "
                "max_iter, completion, budget_usd, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'running')",
                (rid, int(time.time() * 1000), prompt, assignee,
                 max_iter, completion, budget),
            )
    except Exception as e:
        log.warning("ralph: failed to persist run row: %s", e)

    agent_bus.publish(_topic(rid, "begin"),
                      {"prompt": prompt[:1200], "assignee": assignee,
                       "maxIter": max_iter, "completion": completion,
                       "budgetUsd": budget},
                      source="ralph")

    th = threading.Thread(
        target=_run_loop,
        args=(rid, prompt, assignee, max_iter, completion, budget,
              system_prompt, cwd, auto_commit),
        name=f"ralph-{rid}",
        daemon=True,
    )
    state.thread = th
    th.start()
    return {"ok": True, "runId": rid, "maxIter": max_iter,
            "budgetUsd": budget, "completion": completion,
            "assignee": assignee}


def cancel(run_id: str) -> dict:
    with _RUNS_LOCK:
        state = _RUNS.get(run_id)
    if state is None:
        # Maybe it already finished — fine, idempotent.
        return {"ok": True, "alreadyDone": True}
    state.cancel_event.set()
    return {"ok": True}


def status(run_id: str) -> Optional[dict]:
    _ensure_schema()
    with _RUNS_LOCK:
        live = _RUNS.get(run_id)
    try:
        with _db() as c:
            r = c.execute(
                "SELECT * FROM ralph_runs WHERE run_id = ?", (run_id,),
            ).fetchone()
            if not r:
                return None
            iters = c.execute(
                "SELECT idx, ts, status, output, error, cost_usd, duration_ms "
                "FROM ralph_iterations WHERE run_id = ? ORDER BY idx",
                (run_id,),
            ).fetchall()
    except Exception as e:
        log.warning("ralph status query failed: %s", e)
        return None
    return {
        "runId": r["run_id"],
        "tsStart": r["ts_start"], "tsEnd": r["ts_end"],
        "prompt": r["prompt"], "assignee": r["assignee"],
        "maxIter": r["max_iter"], "completion": r["completion"],
        "budgetUsd": r["budget_usd"], "status": r["status"],
        "iterations": r["iterations"], "costUsd": r["cost_usd"],
        "lastOutput": r["last_output"], "error": r["error"],
        "live": live is not None,
        "iterationsDetail": [
            {"idx": x["idx"], "ts": x["ts"], "status": x["status"],
             "output": x["output"], "error": x["error"],
             "costUsd": x["cost_usd"], "durationMs": x["duration_ms"]}
            for x in iters
        ],
    }


def list_runs(limit: int = 50) -> list[dict]:
    _ensure_schema()
    try:
        with _db() as c:
            rows = c.execute(
                "SELECT run_id, ts_start, ts_end, assignee, status, "
                "iterations, cost_usd, max_iter, budget_usd "
                "FROM ralph_runs ORDER BY ts_start DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [{"runId": r["run_id"], "tsStart": r["ts_start"],
                 "tsEnd": r["ts_end"], "assignee": r["assignee"],
                 "status": r["status"], "iterations": r["iterations"],
                 "costUsd": r["cost_usd"], "maxIter": r["max_iter"],
                 "budgetUsd": r["budget_usd"]} for r in rows]
    except Exception as e:
        log.warning("ralph list_runs failed: %s", e)
        return []


# ───────── Internal loop ─────────

def _completion_seen(text: str, marker: str) -> bool:
    return bool(text) and (marker in text)


def _record_iteration(run_id: str, idx: int, *, status: str, output: str,
                      error: Optional[str], cost_usd: float,
                      duration_ms: int) -> None:
    try:
        with _db() as c:
            c.execute(
                "INSERT OR REPLACE INTO ralph_iterations"
                "(run_id, idx, ts, status, output, error, cost_usd, duration_ms)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, idx, int(time.time() * 1000), status,
                 (output or "")[:32000], error, cost_usd, duration_ms),
            )
            c.execute(
                "UPDATE ralph_runs SET iterations = ?, cost_usd = ?, "
                "last_output = ? WHERE run_id = ?",
                (idx + 1, _RUNS[run_id].cost_so_far if run_id in _RUNS else 0.0,
                 (output or "")[:32000], run_id),
            )
    except Exception as e:
        log.warning("ralph iteration persist failed: %s", e)


def _finalize(run_id: str, *, status: str, error: Optional[str] = None) -> None:
    with _RUNS_LOCK:
        state = _RUNS.pop(run_id, None)
    try:
        with _db() as c:
            c.execute(
                "UPDATE ralph_runs SET status = ?, ts_end = ?, error = ? "
                "WHERE run_id = ?",
                (status, int(time.time() * 1000), error, run_id),
            )
    except Exception as e:
        log.warning("ralph finalize persist failed: %s", e)
    agent_bus.publish(_topic(run_id, "end"),
                      {"status": status, "error": error,
                       "iterations": state.iterations if state else 0,
                       "costUsd": state.cost_so_far if state else 0.0},
                      source="ralph")


def _auto_commit_if_dirty(cwd: str, run_id: str) -> Optional[str]:
    """Commit any changes in ``cwd`` if it's a git repo. Returns the commit
    SHA on success, ``None`` if not applicable or skipped.

    Conservative — never force-pushes, never amends, never touches branches.
    Adds *all* tracked + untracked changes (matches the user's manual flow:
    Ralph edits files, we capture the result). Author/committer come from
    the local git config so the user's identity sticks (cycle-5 cmblir).
    """
    import subprocess
    if not cwd:
        return None
    try:
        # Quick check: is this a git working tree?
        rc = subprocess.run(["git", "-C", cwd, "rev-parse", "--is-inside-work-tree"],
                            capture_output=True, text=True, timeout=4)
        if rc.returncode != 0 or rc.stdout.strip() != "true":
            return None
        # Anything to commit?
        st = subprocess.run(["git", "-C", cwd, "status", "--porcelain"],
                            capture_output=True, text=True, timeout=4)
        if not st.stdout.strip():
            agent_bus.publish(_topic(run_id, "autocommit.skip"),
                              {"reason": "clean tree"}, source="ralph")
            return None
        subprocess.run(["git", "-C", cwd, "add", "-A"],
                       check=True, timeout=10)
        msg = (f"chore(ralph): autocommit from loop {run_id}\n\n"
               f"Captured by server.ralph._auto_commit_if_dirty after the "
               f"loop emitted its completion-promise.")
        subprocess.run(["git", "-C", cwd, "commit", "-m", msg],
                       check=True, capture_output=True, timeout=10)
        head = subprocess.run(["git", "-C", cwd, "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=4)
        sha = head.stdout.strip() if head.returncode == 0 else ""
        agent_bus.publish(_topic(run_id, "autocommit.done"),
                          {"sha": sha[:12]}, source="ralph")
        return sha
    except Exception as e:
        log.warning("ralph auto-commit failed: %s", e)
        agent_bus.publish(_topic(run_id, "autocommit.error"),
                          {"error": str(e)}, source="ralph")
        return None


def _run_loop(run_id: str, prompt: str, assignee: str, max_iter: int,
              completion: str, budget_usd: float,
              system_prompt: str, cwd: str,
              auto_commit: bool = False) -> None:
    state = _RUNS[run_id]
    try:
        for i in range(max_iter):
            if state.cancel_event.is_set():
                _finalize(run_id, status="cancelled")
                return
            if state.cost_so_far >= budget_usd:
                _finalize(run_id, status="budget",
                          error=f"budget ${budget_usd:.2f} exhausted "
                                f"after {state.iterations} iters")
                return

            agent_bus.publish(_topic(run_id, "iter.begin"),
                              {"idx": i, "costSoFar": round(state.cost_so_far, 4)},
                              source="ralph")
            t0 = time.time()
            try:
                resp: AIResponse = execute_with_assignee(
                    assignee, prompt,
                    system_prompt=system_prompt,
                    cwd=cwd,
                    timeout=_PER_ITER_TIMEOUT_S,
                    fallback=True,
                )
            except Exception as e:
                dur = int((time.time() - t0) * 1000)
                _record_iteration(run_id, i, status="err", output="",
                                  error=f"{type(e).__name__}: {e}",
                                  cost_usd=0.0, duration_ms=dur)
                agent_bus.publish(_topic(run_id, "iter.error"),
                                  {"idx": i, "error": str(e)}, source="ralph")
                continue

            dur_ms = int((time.time() - t0) * 1000)
            ok = (resp.status == "ok")
            output = resp.output if ok else ""
            err = resp.error if not ok else None
            cost = float(resp.cost_usd or 0.0)
            state.cost_so_far += cost
            state.iterations = i + 1

            _record_iteration(run_id, i,
                              status="ok" if ok else "err",
                              output=output, error=err,
                              cost_usd=cost, duration_ms=dur_ms)
            agent_bus.publish(_topic(run_id, "iter.done"),
                              {"idx": i, "ok": ok,
                               "outputLen": len(output),
                               "costUsd": round(cost, 4),
                               "totalCostUsd": round(state.cost_so_far, 4),
                               "durationMs": dur_ms},
                              source="ralph")

            if ok and _completion_seen(output, completion):
                if auto_commit:
                    _auto_commit_if_dirty(cwd, run_id)
                _finalize(run_id, status="done")
                return
            if state.cost_so_far >= budget_usd:
                _finalize(run_id, status="budget",
                          error=f"budget ${budget_usd:.2f} hit after iter {i}")
                return

        _finalize(run_id, status="max_iter")
    except Exception as e:
        log.exception("ralph loop crashed: %s", e)
        _finalize(run_id, status="error", error=str(e))


# ───────── HTTP API ─────────

def api_ralph_start(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    return start(
        prompt=str(body.get("prompt") or ""),
        assignee=str(body.get("assignee") or ""),
        max_iterations=int(body.get("maxIterations") or 0),
        completion_promise=str(body.get("completion") or ""),
        budget_usd=float(body.get("budgetUsd") or 0.0),
        system_prompt=str(body.get("systemPrompt") or ""),
        cwd=str(body.get("cwd") or ""),
        auto_commit=bool(body.get("autoCommit")),
    )


def api_ralph_cancel(body: dict) -> dict:
    rid = str((body or {}).get("runId") or "")
    if not rid:
        return {"ok": False, "error": "runId required"}
    return cancel(rid)


def api_ralph_status(query: dict) -> dict:
    rid = ""
    if isinstance(query, dict):
        v = query.get("runId")
        if isinstance(v, list):
            v = v[0] if v else ""
        rid = str(v or "")
    if not rid:
        return {"ok": False, "error": "runId required"}
    s = status(rid)
    if s is None:
        return {"ok": False, "error": "not found"}
    return {"ok": True, "run": s}


def api_ralph_list(query: dict | None = None) -> dict:
    limit = 50
    if isinstance(query, dict):
        v = query.get("limit")
        if isinstance(v, list):
            v = v[0] if v else 50
        try:
            limit = int(v or 50)
        except (TypeError, ValueError):
            limit = 50
    return {"ok": True, "runs": list_runs(limit)}
