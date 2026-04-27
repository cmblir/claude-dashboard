"""Background supervisor for Hyper Agents.

Runs once a minute. For every enabled agent it checks whether the configured
trigger has fired since ``lastRefinedAt`` and, if so, calls
``hyper_agent.refine_agent(name, trigger=...)``. The actual meta-LLM call,
backup, history append, and budget tracking all live in ``hyper_agent.py`` —
this module only decides *when* to fire.

Triggers honoured:
- ``manual`` — never fired automatically.
- ``interval`` — every N hours, where N is parsed from ``cronSpec`` of the form
  ``"0 */N * * *"`` (any other shape falls back to 6h).
- ``cron`` — alias for ``interval`` in v1 (full cron parser deferred).
- ``after_session`` — fires when at least ``minSessionsBetween`` JSONL transcript
  files have been modified since ``lastRefinedAt`` AND those transcripts mention
  this agent by ``subagent_type`` or ``@<name>``.
- ``any`` — fires if either ``interval`` or ``after_session`` would fire.

Budget exhaustion / disabled flag / file-missing are all handled inside
``refine_agent`` so this loop just calls and logs.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

from .config import PROJECTS_DIR
from .hyper_agent import HYPER_AGENTS_PATH, load_meta, refine_agent
from .logger import log
from .utils import _safe_read


_STOP = threading.Event()
_THREAD: Optional[threading.Thread] = None
_TICK_SECONDS = 60         # how often the loop wakes up
_AFTER_SESSION_SCAN_LIMIT = 200   # cap jsonl files we scan per tick


# ───────── helpers ─────────

def _parse_interval_hours(cron_spec: str) -> int:
    """Minimal cron parser — recognises ``0 */N * * *`` only. Anything else → 6h.

    The full cron grammar is intentionally out of scope for v1; users who need
    finer control can use ``manual`` + their own scheduler-tasks integration.
    """
    parts = (cron_spec or "").split()
    if len(parts) == 5 and parts[1].startswith("*/"):
        try:
            n = int(parts[1][2:])
            return max(1, min(n, 168))
        except Exception:
            pass
    return 6


def _interval_due(agent_meta: dict, now_ms: int) -> bool:
    """True if ``intervalHours`` have elapsed since ``lastRefinedAt``."""
    last = int(agent_meta.get("lastRefinedAt") or 0)
    hours = _parse_interval_hours(agent_meta.get("cronSpec") or "")
    if last == 0:
        return True
    return (now_ms - last) >= hours * 3600 * 1000


def _project_slug(cwd: str) -> str:
    """Convert an absolute cwd to Claude Code's transcript-dir slug.

    Claude Code stores per-project sessions under
    ``~/.claude/projects/<slug>/`` where ``<slug>`` replaces every ``/`` in
    the absolute path with ``-``. e.g. ``/Users/x/work/proj`` →
    ``-Users-x-work-proj``.
    """
    return str(cwd).replace("/", "-")


def _recent_session_files(since_ms: int, limit: int,
                          cwd: str | None = None) -> list[Path]:
    """Return the most recent jsonl transcript files modified after ``since_ms``.

    When ``cwd`` is provided, only that project's transcript directory is
    scanned — this prevents a project-scoped agent from being refined based on
    chatter from a different project."""
    if not PROJECTS_DIR.exists():
        return []
    out: list[tuple[float, Path]] = []
    if cwd:
        proj = PROJECTS_DIR / _project_slug(cwd)
        if not proj.exists() or not proj.is_dir():
            return []
        candidates = [proj]
    else:
        candidates = [d for d in PROJECTS_DIR.iterdir() if d.is_dir()]
    for proj in candidates:
        for jl in proj.glob("**/*.jsonl"):
            try:
                mt = jl.stat().st_mtime * 1000
            except Exception:
                continue
            if mt > since_ms:
                out.append((mt, jl))
    out.sort(reverse=True)
    return [p for _, p in out[:limit]]


def _file_mentions_agent(path: Path, name: str) -> bool:
    """Quick string scan — agent file is jsonl so we look for either
    ``"subagent_type":"<name>"`` or ``@<name>`` mention."""
    text = _safe_read(path, limit=400_000)
    if not text:
        return False
    needle1 = f'"subagent_type":"{name}"'
    needle2 = f'"subagent_type": "{name}"'
    needle3 = f"@{name}"
    return needle1 in text or needle2 in text or needle3 in text


def _after_session_due(name: str, agent_meta: dict, now_ms: int) -> tuple[bool, list[str]]:
    """Returns (due, sample transcripts).

    "Due" requires at least ``minSessionsBetween`` jsonl files newer than
    ``lastRefinedAt`` that mention the agent. Returns up to 5 short transcript
    snippets to feed the meta-LLM as context.

    Project-scoped agents (entry has non-empty ``cwd``) restrict the scan to
    that project's transcript dir so cross-project sessions don't trigger.
    """
    last = int(agent_meta.get("lastRefinedAt") or 0)
    threshold = int(agent_meta.get("minSessionsBetween") or 5)
    cwd = agent_meta.get("cwd") or None
    files = _recent_session_files(since_ms=last, limit=_AFTER_SESSION_SCAN_LIMIT, cwd=cwd)
    matches = [p for p in files if _file_mentions_agent(p, name)]
    if len(matches) < max(1, threshold):
        return False, []
    snippets: list[str] = []
    for p in matches[:5]:
        body = _safe_read(p, limit=8000)
        if body:
            snippets.append(body)
    return True, snippets


def _parse_meta_key(key: str) -> tuple[str, str]:
    """Return ``(scope, name)`` from a meta dict key.

    Mirrors ``hyper_agent._parse_key`` — kept inline to avoid the import edge
    case on shutdown when modules unwind in arbitrary order.
    """
    if key.startswith("global:"):
        return "global", key[len("global:"):]
    if key.startswith("project:"):
        rest = key[len("project:"):]
        parts = rest.split(":", 1)
        if len(parts) == 2:
            return "project", parts[1]
    return "global", key  # legacy flat


def _tick_one(meta_key: str, agent_meta: dict, now_ms: int) -> None:
    """Decide whether to fire for one agent and call ``refine_agent``.

    ``meta_key`` is the composite key from the JSON store
    (``global:NAME`` / ``project:HASH:NAME`` / legacy ``NAME``); we extract the
    actual agent name from it and pull ``cwd`` from the entry itself.
    """
    if not agent_meta.get("enabled"):
        return
    trig = agent_meta.get("trigger") or "manual"
    if trig == "manual":
        return

    _, name = _parse_meta_key(meta_key)
    cwd = agent_meta.get("cwd") or None

    fire_interval = trig in ("interval", "cron", "any") and _interval_due(agent_meta, now_ms)
    fire_session  = False
    transcripts: list[str] = []
    if trig in ("after_session", "any"):
        fire_session, transcripts = _after_session_due(name, agent_meta, now_ms)

    if not (fire_interval or fire_session):
        return

    actual_trigger = "after_session" if fire_session else "interval"
    log.info("hyper-agent: refining %s%s (trigger=%s)",
             name, f" @ {cwd}" if cwd else "", actual_trigger)
    try:
        r = refine_agent(name, trigger=actual_trigger, transcripts=transcripts, cwd=cwd)
        if r.get("ok"):
            log.info("hyper-agent: %s refined — applied=%s cost=$%.4f",
                     name, r.get("applied"), r.get("costUSD") or 0.0)
        else:
            log.warning("hyper-agent: refine %s failed — %s", name, r.get("error"))
    except Exception as e:
        log.exception("hyper-agent: refine %s crashed: %s", name, e)


def _loop() -> None:
    log.info("hyper-agent worker started (tick=%ds, prefs=%s)",
             _TICK_SECONDS, HYPER_AGENTS_PATH)
    while not _STOP.is_set():
        try:
            meta = load_meta()
            now_ms = int(time.time() * 1000)
            for key, entry in (meta.get("agents") or {}).items():
                if _STOP.is_set():
                    break
                _tick_one(key, entry, now_ms)
        except Exception as e:
            log.exception("hyper-agent loop iteration failed: %s", e)
        _STOP.wait(_TICK_SECONDS)
    log.info("hyper-agent worker stopped")


def start_hyper_agent_worker() -> None:
    """Idempotent entry — call from ``server.py`` boot."""
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(target=_loop, daemon=True, name="hyper-agent-worker")
    _THREAD.start()


def stop_hyper_agent_worker() -> None:
    """Mainly for tests."""
    _STOP.set()
