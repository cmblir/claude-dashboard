"""Auto-Resume — inject a self-healing retry loop into a live Claude Code session.

This is the v2 implementation that fulfils every one of the seven mechanisms
the user specified:

    1. Exit-reason classification    -> _classify_exit()
    2. Precise reset-time parsing    -> _parse_reset_time()
    3. Stop-hook progress snapshot   -> auto_resume_hooks.install()
    4. SessionStart-hook injection   -> auto_resume_hooks.install()
    5. External wrapper restart loop -> _process_one() + _spawn_resume()
    6. Infinite-loop guards          -> _exponential_backoff() +
                                        max_attempts + snapshot-hash stall
    7. Observable state file         -> ~/.claude-dashboard-auto-resume.json

User flow
---------
1. UI lists live sessions (tracked by jsonl mtime).
2. User opens a session detail and clicks "Inject Auto-Resume", optionally
   tweaks prompt / poll / max-attempts and toggles "install hooks".
3. The background worker watches the jsonl. When the session looks
   stalled (no new entries for `idle_seconds`) AND the last activity
   smells like a usage cap, the worker classifies the exit, parses any
   reset time, schedules the next attempt, and spawns
   `claude --resume <id> -p "<prompt>"` from the session's cwd.
4. On non-zero exit it retries per the exit-reason policy, on success it
   reverts to monitor mode, on `context_full` / `auth_expired` / hash
   stall / max-attempts it short-circuits to a permanent stop with a
   user-visible reason.

Storage
-------
~/.claude-dashboard-auto-resume.json
    {
      "<session_id>": {
        "sessionId":        str,
        "enabled":          bool,
        "cwd":              str,
        "jsonlPath":        str,
        "prompt":           str,
        "pollInterval":     int,        # fallback retry interval (sec)
        "idleSeconds":      int,        # how long jsonl must be quiet
        "maxAttempts":      int,        # hard cap on retries (default 12)
        "useContinue":      bool,       # `--continue` instead of `--resume <id>`
        "extraArgs":        [str, ...],
        "installHooks":     bool,       # snapshot hook installed for cwd?
        "createdAt":        int,        # epoch ms
        "attempts":         int,
        "lastAttemptAt":    int,        # epoch ms
        "nextAttemptAt":    int,        # epoch ms
        "lastExitCode":     int|None,
        "lastExitReason":   str,        # one of EXIT_REASONS
        "lastError":        str,        # tail of stderr/stdout
        "snapshotHashes":   [str, ...], # last 5 snapshot hashes (stall detect)
        "state":            str,        # see STATE_*
        "stopReason":       str,        # populated when state=failed/exhausted
        "lastResetAt":      int,        # epoch ms parsed from rate-limit msg
      }
    }
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Optional

from .config import _env_path, CLAUDE_HOME
from .logger import log
from .utils import _safe_read, _safe_write


# ───────── Paths & constants ─────────

AUTO_RESUME_PATH = _env_path(
    "CLAUDE_DASHBOARD_AUTO_RESUME",
    Path.home() / ".claude-dashboard-auto-resume.json",
)

DEFAULT_POLL_INTERVAL = 300
MIN_POLL_INTERVAL = 30
MAX_POLL_INTERVAL = 3600

DEFAULT_IDLE_SECONDS = 90
MIN_IDLE_SECONDS = 30

DEFAULT_MAX_ATTEMPTS = 12          # 12 * 5min ≈ 1h floor; with backoff > 60h
SNAPSHOT_STALL_LIMIT = 3           # N identical hashes in a row -> stalled
SNAPSHOT_HASH_HISTORY = 5          # how many tail hashes to keep

DEFAULT_PROMPT = (
    "Continue the previous task. The session was interrupted by a usage / rate "
    "limit. Resume from exactly where you left off, do not start over, and keep "
    "going until the original objective is complete."
)

WORKER_TICK_SECONDS = 5

# ── Exit reason taxonomy (mechanism #1) ──
EXIT_REASONS = (
    "rate_limit",      # 5h / weekly cap or transient 429 — wait + retry
    "context_full",    # message too long / token cap exceeded — permanent stop
    "auth_expired",    # /login required — permanent stop, surface to user
    "clean",           # exit 0 — drop back to watch mode
    "unknown",         # everything else — exponential backoff
)

STATE_RUNNING   = "running"     # subprocess in flight
STATE_WAITING   = "waiting"     # cooling down, nextAttemptAt in future
STATE_WATCHING  = "watching"    # alive, monitoring jsonl
STATE_DONE      = "done"        # last attempt exited 0 cleanly
STATE_FAILED    = "failed"      # permanent stop (context/auth)
STATE_EXHAUSTED = "exhausted"   # maxAttempts hit OR snapshot hash stalled
STATE_STOPPED   = "stopped"     # user disabled
STATE_ERROR     = "error"       # internal error (jsonl missing etc.)

# Heuristic hints in the jsonl tail that suggest a rate-limit kill.
RATE_LIMIT_HINTS = (
    "usage limit",
    "usage_limit",
    "rate_limit",
    "rate limited",
    "rate-limited",
    "ratelimit",
    "5-hour limit",
    "5 hour limit",
    "weekly limit",
    "message limit",
    "claude usage",
    "try again",
    "please try later",
    "limit reached",
    "limit exceeded",
    "quota exceeded",
    "429",
    "resets at",
    "available again",
)

# Patterns inspected on stderr/stdout/jsonl tail to classify the exit reason.
_PAT_RATE_LIMIT = re.compile(
    r"(usage|rate|message|weekly|5[- ]?hour)\s*(limit|cap|quota)|"
    r"\b429\b|"
    r"too many requests|"
    r"please try later|"
    r"resets?\s+(at|in)|"
    r"available again",
    re.IGNORECASE,
)
_PAT_CONTEXT_FULL = re.compile(
    r"(context|prompt|input)\s+(window|length|tokens?)\s+(exceeded|too long|full)|"
    r"\b(maximum|max)\s+context|"
    r"prompt is too long",
    re.IGNORECASE,
)
_PAT_AUTH_EXPIRED = re.compile(
    r"\b(unauthori[sz]ed|invalid api key|please run\s+/login|please run\s+claude\s+login|"
    r"authentication\s+(failed|required|expired)|token\s+expired|"
    r"missing.*api.?key|not\s+(logged|signed)\s+in)\b",
    re.IGNORECASE,
)


# ───────── State ─────────

_LOCK = threading.RLock()
_WORKER_THREAD: Optional[threading.Thread] = None
_WORKER_STOP = threading.Event()
_RUNNING_PROCS: dict[str, subprocess.Popen] = {}


# ───────── Storage ─────────

def _load_all() -> dict:
    raw = _safe_read(AUTO_RESUME_PATH)
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log.warning("auto_resume: corrupt store, resetting: %s", e)
        return {}


def _dump_all(data: dict) -> bool:
    try:
        AUTO_RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return _safe_write(AUTO_RESUME_PATH, json.dumps(data, indent=2, ensure_ascii=False))


def _now_ms() -> int:
    return int(time.time() * 1000)


# ───────── Mechanism #1: classify exit reason ─────────

def _classify_exit(exit_code: int, stderr_tail: str, stdout_tail: str,
                   jsonl_tail: str) -> str:
    """Return one of EXIT_REASONS based on exit code + output text.

    Order matters: auth_expired and context_full are permanent so they are
    checked before rate_limit. `clean` only on exit_code == 0.
    """
    if exit_code == 0:
        return "clean"
    blob = "\n".join(filter(None, [stderr_tail or "", stdout_tail or "", jsonl_tail or ""]))
    if _PAT_AUTH_EXPIRED.search(blob):
        return "auth_expired"
    if _PAT_CONTEXT_FULL.search(blob):
        return "context_full"
    if _PAT_RATE_LIMIT.search(blob):
        return "rate_limit"
    return "unknown"


# ───────── Mechanism #2: parse reset time ─────────

# Match a wide range of "resets at HH:MM[am/pm]" / "in N minutes" wording.
_PAT_RESET_AT = re.compile(
    r"(?:reset(?:s|ting)?|available\s+again|try\s+again|next\s+window).{0,30}?"
    r"(?:at\s+)?"
    r"(\d{1,2})[:.](\d{2})\s*(am|pm|a\.m\.|p\.m\.)?",
    re.IGNORECASE,
)
_PAT_RESET_IN = re.compile(
    r"(?:in|after|wait)\s+(\d+)\s*(second|sec|s|minute|min|m|hour|hr|h)s?\b",
    re.IGNORECASE,
)


def _parse_reset_time(text: str, now_ts: Optional[float] = None) -> Optional[int]:
    """Try to extract a precise next-attempt epoch_ms from a rate-limit message.

    Returns None if no usable hint is found — caller falls back to
    pollInterval / exponential backoff.
    """
    if not text:
        return None
    now_ts = now_ts if now_ts is not None else time.time()

    # "in N units" — relative offset
    m = _PAT_RESET_IN.search(text)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith(("hour", "hr", "h")):
            sec = n * 3600
        elif unit.startswith(("min", "m")):
            sec = n * 60
        else:
            sec = n
        # tiny safety margin so we don't fire one tick early
        return int((now_ts + sec + 5) * 1000)

    # "at HH:MM[am/pm]" — absolute clock time, today or tomorrow if past
    m = _PAT_RESET_AT.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        meridiem = (m.group(3) or "").lower().rstrip(".")
        if meridiem in ("pm", "p", "p.m"):
            if hour < 12:
                hour += 12
        elif meridiem in ("am", "a", "a.m"):
            if hour == 12:
                hour = 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        try:
            target_t = dt_time(hour=hour, minute=minute)
        except ValueError:
            return None
        now_dt = datetime.fromtimestamp(now_ts)
        target = datetime.combine(now_dt.date(), target_t)
        if target <= now_dt:
            target += timedelta(days=1)
        return int(target.timestamp() * 1000) + 5000
    return None


# ───────── Mechanism #6: exponential backoff + snapshot stall ─────────

def _exponential_backoff(attempt: int) -> int:
    """1m → 2m → 4m → 8m → 16m → 30m cap. attempt is 1-indexed."""
    base = 60
    cap = 1800
    if attempt < 1:
        attempt = 1
    return min(cap, base * (2 ** (attempt - 1)))


def _snapshot_dir(cwd: str) -> Path:
    return Path(cwd) / ".claude" / "auto-resume"


def _snapshot_md_path(cwd: str) -> Path:
    return _snapshot_dir(cwd) / "snapshot.md"


def _read_snapshot_hash(cwd: str) -> str:
    p = _snapshot_md_path(cwd)
    try:
        data = p.read_bytes()
    except Exception:
        return ""
    return hashlib.sha256(data).hexdigest()[:16]


def _push_hash_and_check_stall(entry: dict, fresh_hash: str) -> bool:
    """Maintain rolling hash list. Return True if SNAPSHOT_STALL_LIMIT hits."""
    if not fresh_hash:
        return False
    hist = list(entry.get("snapshotHashes") or [])
    hist.append(fresh_hash)
    if len(hist) > SNAPSHOT_HASH_HISTORY:
        hist = hist[-SNAPSHOT_HASH_HISTORY:]
    entry["snapshotHashes"] = hist
    if len(hist) >= SNAPSHOT_STALL_LIMIT:
        recent = hist[-SNAPSHOT_STALL_LIMIT:]
        if all(h == recent[0] for h in recent):
            return True
    return False


# ───────── jsonl helpers ─────────

def _resolve_jsonl(session_id: str, cwd: str = "") -> Optional[Path]:
    if not session_id:
        return None
    projects_dir = CLAUDE_HOME / "projects"
    if not projects_dir.exists():
        return None
    if cwd:
        slug = "-" + str(Path(cwd).resolve()).strip("/").replace("/", "-")
        p = projects_dir / slug / f"{session_id}.jsonl"
        if p.exists():
            return p
    for proj in projects_dir.iterdir():
        if not proj.is_dir():
            continue
        p = proj / f"{session_id}.jsonl"
        if p.exists():
            return p
    return None


def _resolve_cwd_from_jsonl(jsonl: Path) -> str:
    try:
        with jsonl.open("r", encoding="utf-8", errors="replace") as fh:
            for _ in range(50):
                line = fh.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                c_val = msg.get("cwd")
                if isinstance(c_val, str) and c_val:
                    return c_val
    except Exception:
        pass
    return ""


def _read_jsonl_tail(jsonl: Path, byte_window: int = 16384) -> str:
    try:
        size = jsonl.stat().st_size
        with jsonl.open("rb") as fh:
            fh.seek(max(0, size - byte_window))
            return fh.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _looks_rate_limited(jsonl: Path) -> bool:
    tail = _read_jsonl_tail(jsonl).lower()
    if not tail:
        return False
    return any(hint in tail for hint in RATE_LIMIT_HINTS)


def _jsonl_idle_seconds(jsonl: Path) -> float:
    try:
        return max(0.0, time.time() - jsonl.stat().st_mtime)
    except Exception:
        return 0.0


def _claude_bin() -> Optional[str]:
    return shutil.which("claude")


# ───────── Public state helper ─────────

def _public_state(entry: dict) -> dict:
    notify = entry.get("notify") or {}
    return {
        "sessionId":      entry.get("sessionId"),
        "enabled":        bool(entry.get("enabled")),
        "cwd":            entry.get("cwd") or "",
        "jsonlPath":      entry.get("jsonlPath") or "",
        "prompt":         entry.get("prompt") or "",
        "pollInterval":   entry.get("pollInterval") or DEFAULT_POLL_INTERVAL,
        "idleSeconds":    entry.get("idleSeconds") or DEFAULT_IDLE_SECONDS,
        "maxAttempts":    entry.get("maxAttempts") or DEFAULT_MAX_ATTEMPTS,
        "useContinue":    bool(entry.get("useContinue")),
        "extraArgs":      list(entry.get("extraArgs") or []),
        "installHooks":   bool(entry.get("installHooks")),
        "notify":         {
            "slack":   (notify.get("slack") or "")[:500],
            "discord": (notify.get("discord") or "")[:500],
        },
        "attempts":       int(entry.get("attempts") or 0),
        "lastAttemptAt":  entry.get("lastAttemptAt") or 0,
        "nextAttemptAt":  entry.get("nextAttemptAt") or 0,
        "lastExitCode":   entry.get("lastExitCode"),
        "lastExitReason": entry.get("lastExitReason") or "",
        "lastError":      (entry.get("lastError") or "")[-2000:],
        "snapshotHashes": list(entry.get("snapshotHashes") or []),
        "state":          entry.get("state") or STATE_WATCHING,
        "stopReason":     entry.get("stopReason") or "",
        "lastResetAt":    entry.get("lastResetAt") or 0,
        "createdAt":      entry.get("createdAt") or 0,
    }


def _sanitize_notify(raw: dict) -> dict:
    """Accept only https://hooks.slack.com or discord.com webhook URLs.
    Validation is enforced again at send-time by notify._validate."""
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for k in ("slack", "discord"):
        v = (raw.get(k) or "").strip()
        if v:
            out[k] = v[:500]
    return out


def _send_notify(entry: dict, kind: str, summary: str) -> None:
    """Fire-and-forget Slack/Discord notification on state transition.
    `kind` ∈ {succeeded, failed, exhausted, retrying}."""
    notify = entry.get("notify") or {}
    slack = (notify.get("slack") or "").strip()
    discord = (notify.get("discord") or "").strip()
    if not slack and not discord:
        return
    try:
        from .notify import send_slack, send_discord
        emoji = {
            "succeeded": "✅",
            "failed":    "🚫",
            "exhausted": "⛔",
            "retrying":  "🔄",
        }.get(kind, "ℹ️")
        sid = entry.get("sessionId") or "?"
        cwd = entry.get("cwd") or "?"
        title = f"{emoji} LazyClaude Auto-Resume · {kind} · {sid[:8]}"
        body = f"session: {sid}\ncwd: {cwd}\nattempts: {entry.get('attempts')}/{entry.get('maxAttempts')}\nstate: {entry.get('state')}\n\n{summary[:1200]}"
        if slack:
            try: send_slack(slack, title, body)
            except Exception as e: log.warning("auto_resume notify slack: %s", e)
        if discord:
            try: send_discord(discord, title, body)
            except Exception as e: log.warning("auto_resume notify discord: %s", e)
    except Exception as e:
        log.warning("auto_resume notify failed: %s", e)


# ───────── Public API ─────────

def api_auto_resume_set(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}
    session_id = (body.get("sessionId") or "").strip()
    if not session_id:
        return {"ok": False, "error": "sessionId required"}

    cwd = (body.get("cwd") or "").strip()
    jsonl = _resolve_jsonl(session_id, cwd)
    if jsonl is None:
        return {"ok": False, "error": "session jsonl not found under ~/.claude/projects"}
    if not cwd:
        cwd = _resolve_cwd_from_jsonl(jsonl)
    if not cwd:
        return {"ok": False, "error": "could not resolve session cwd"}

    if _claude_bin() is None:
        return {"ok": False, "error": "`claude` binary not on PATH"}

    poll = int(body.get("pollInterval") or DEFAULT_POLL_INTERVAL)
    poll = max(MIN_POLL_INTERVAL, min(MAX_POLL_INTERVAL, poll))
    idle = max(MIN_IDLE_SECONDS, int(body.get("idleSeconds") or DEFAULT_IDLE_SECONDS))
    max_attempts = max(1, min(60, int(body.get("maxAttempts") or DEFAULT_MAX_ATTEMPTS)))
    use_continue = bool(body.get("useContinue"))
    install_hooks = bool(body.get("installHooks"))

    prompt = (body.get("prompt") or "").strip() or DEFAULT_PROMPT
    extra_args_raw = body.get("extraArgs") or []
    if not isinstance(extra_args_raw, list):
        return {"ok": False, "error": "extraArgs must be list"}
    extra_args = [str(a) for a in extra_args_raw if isinstance(a, (str, int, float))]
    notify_clean = _sanitize_notify(body.get("notify") or {})

    # Optional: install Stop + SessionStart hooks for this cwd
    hook_result = None
    if install_hooks:
        try:
            from .auto_resume_hooks import install as _hooks_install
            hook_result = _hooks_install(cwd)
            if not hook_result.get("ok"):
                return {"ok": False, "error": "hook install failed: " + (hook_result.get("error") or "?")}
        except Exception as e:
            return {"ok": False, "error": f"hook install crashed: {e}"}

    with _LOCK:
        store = _load_all()
        existing = store.get(session_id) or {}
        entry = {
            **existing,
            "sessionId":       session_id,
            "enabled":         True,
            "cwd":             cwd,
            "jsonlPath":       str(jsonl),
            "prompt":          prompt,
            "pollInterval":    poll,
            "idleSeconds":     idle,
            "maxAttempts":     max_attempts,
            "useContinue":     use_continue,
            "extraArgs":       extra_args,
            "installHooks":    install_hooks,
            "notify":          notify_clean,
            "createdAt":       existing.get("createdAt") or _now_ms(),
            "attempts":        int(existing.get("attempts") or 0),
            "lastAttemptAt":   existing.get("lastAttemptAt") or 0,
            "nextAttemptAt":   _now_ms(),
            "lastExitCode":    existing.get("lastExitCode"),
            "lastExitReason":  existing.get("lastExitReason") or "",
            "lastError":       existing.get("lastError") or "",
            "snapshotHashes":  list(existing.get("snapshotHashes") or []),
            "state":           STATE_WATCHING,
            "stopReason":      "",
            "lastResetAt":     existing.get("lastResetAt") or 0,
        }
        store[session_id] = entry
        _dump_all(store)

    _ensure_worker_running()
    out = {"ok": True, "entry": _public_state(entry)}
    if hook_result is not None:
        out["hooks"] = hook_result
    return out


def api_auto_resume_cancel(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}
    session_id = (body.get("sessionId") or "").strip()
    if not session_id:
        return {"ok": False, "error": "sessionId required"}

    with _LOCK:
        store = _load_all()
        entry = store.get(session_id)
        if not entry:
            return {"ok": False, "error": "no auto-resume binding for this session"}
        entry["enabled"] = False
        entry["state"] = STATE_STOPPED
        entry["stopReason"] = "user cancelled"
        _dump_all(store)
        proc = _RUNNING_PROCS.pop(session_id, None)

    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass

    return {"ok": True, "entry": _public_state(entry)}


def api_auto_resume_status(query: dict) -> dict:
    store = _load_all()
    entries = [_public_state(e) for e in store.values()]
    entries.sort(key=lambda e: -(e.get("createdAt") or 0))
    return {
        "ok": True,
        "workerAlive": bool(_WORKER_THREAD and _WORKER_THREAD.is_alive()),
        "claudeBin": _claude_bin() or "",
        "entries": entries,
        "active": [e for e in entries if e.get("enabled")],
    }


def api_auto_resume_get(query: dict) -> dict:
    sid = (query.get("sessionId", [""])[0] or "").strip()
    if not sid:
        return {"ok": False, "error": "sessionId required"}
    store = _load_all()
    entry = store.get(sid)
    if not entry:
        return {"ok": True, "entry": None}
    out = _public_state(entry)
    cwd = entry.get("cwd") or ""
    if cwd:
        snap = _snapshot_md_path(cwd)
        if snap.exists():
            try:
                out["snapshotPreview"] = snap.read_text(encoding="utf-8", errors="replace")[:4000]
            except Exception:
                out["snapshotPreview"] = ""
        else:
            out["snapshotPreview"] = ""
    return {"ok": True, "entry": out}


def api_auto_resume_install_hooks(body: dict) -> dict:
    cwd = (body.get("cwd") or "").strip()
    if not cwd:
        return {"ok": False, "error": "cwd required"}
    from .auto_resume_hooks import install as _hooks_install
    return _hooks_install(cwd)


def api_auto_resume_uninstall_hooks(body: dict) -> dict:
    cwd = (body.get("cwd") or "").strip()
    if not cwd:
        return {"ok": False, "error": "cwd required"}
    from .auto_resume_hooks import uninstall as _hooks_uninstall
    return _hooks_uninstall(cwd)


def api_auto_resume_hook_status(query: dict) -> dict:
    cwd = (query.get("cwd", [""])[0] or "").strip()
    if not cwd:
        return {"ok": False, "error": "cwd required"}
    from .auto_resume_hooks import status as _hooks_status
    return _hooks_status(cwd)


# ───────── Mechanism #5: external wrapper restart loop ─────────

def _spawn_resume(entry: dict) -> tuple[int, str, str]:
    """Run `claude` once and return (exit_code, stderr_tail, stdout_tail)."""
    bin_path = _claude_bin()
    if bin_path is None:
        return (127, "`claude` binary not on PATH", "")

    session_id = entry["sessionId"]
    cwd = entry.get("cwd") or os.path.expanduser("~")
    prompt = entry.get("prompt") or DEFAULT_PROMPT
    extra = list(entry.get("extraArgs") or [])

    if entry.get("useContinue"):
        cmd = [bin_path, "--continue", "-p", prompt, *extra]
    else:
        cmd = [bin_path, "--resume", session_id, "-p", prompt, *extra]
    log.info("auto_resume: spawn for %s in %s (extra=%s)", session_id, cwd, extra)

    env = os.environ.copy()
    env.setdefault("CI", "1")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception as e:
        return (1, f"spawn failed: {e}", "")

    with _LOCK:
        _RUNNING_PROCS[session_id] = proc

    try:
        out, err = proc.communicate(timeout=3600)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            proc.terminate()
        except Exception:
            pass
        out, err = "", "timed out after 1h"
        exit_code = 124
    except Exception as e:
        out, err = "", f"communicate failed: {e}"
        exit_code = 1
    finally:
        with _LOCK:
            _RUNNING_PROCS.pop(session_id, None)

    return (exit_code, (err or "")[-4000:], (out or "")[-4000:])


def _process_one(session_id: str) -> None:
    """One supervisor pass — honours nextAttemptAt / idle / hash-stall / cap."""
    with _LOCK:
        store = _load_all()
        entry = store.get(session_id)
        if not entry or not entry.get("enabled"):
            return
        if session_id in _RUNNING_PROCS:
            return
        next_at = int(entry.get("nextAttemptAt") or 0)
        idle_required = int(entry.get("idleSeconds") or DEFAULT_IDLE_SECONDS)
        attempts = int(entry.get("attempts") or 0)
        max_attempts = int(entry.get("maxAttempts") or DEFAULT_MAX_ATTEMPTS)

    now_ms = _now_ms()

    # Mechanism #6 — hard cap on attempts
    if attempts >= max_attempts:
        with _LOCK:
            store = _load_all()
            if session_id in store:
                store[session_id]["state"] = STATE_EXHAUSTED
                store[session_id]["enabled"] = False
                store[session_id]["stopReason"] = (
                    f"max attempts reached ({attempts}/{max_attempts})"
                )
                _dump_all(store)
        return

    if next_at and now_ms < next_at:
        with _LOCK:
            store = _load_all()
            if session_id in store and store[session_id].get("state") not in (
                STATE_FAILED, STATE_EXHAUSTED, STATE_STOPPED, STATE_DONE,
            ):
                store[session_id]["state"] = STATE_WAITING
                _dump_all(store)
        return

    jsonl = Path(entry.get("jsonlPath") or "")
    if not jsonl.exists():
        new_jsonl = _resolve_jsonl(session_id, entry.get("cwd") or "")
        if new_jsonl is None:
            with _LOCK:
                store = _load_all()
                if session_id in store:
                    store[session_id]["state"] = STATE_ERROR
                    store[session_id]["lastError"] = "session jsonl missing"
                    _dump_all(store)
            return
        jsonl = new_jsonl

    idle = _jsonl_idle_seconds(jsonl)
    if idle < idle_required:
        with _LOCK:
            store = _load_all()
            if session_id in store and store[session_id].get("state") not in (
                STATE_FAILED, STATE_EXHAUSTED, STATE_STOPPED, STATE_DONE,
            ):
                store[session_id]["state"] = STATE_WATCHING
                _dump_all(store)
        return

    # 2-signal gate: idle long AND last activity smells like cap
    if not _looks_rate_limited(jsonl):
        return

    with _LOCK:
        store = _load_all()
        if session_id not in store or not store[session_id].get("enabled"):
            return
        store[session_id]["state"] = STATE_RUNNING
        store[session_id]["lastAttemptAt"] = now_ms
        store[session_id]["attempts"] = attempts + 1
        _dump_all(store)
        attempt_entry = dict(store[session_id])

    exit_code, err_tail, out_tail = _spawn_resume(attempt_entry)
    jsonl_tail_for_class = _read_jsonl_tail(jsonl)
    reason = _classify_exit(exit_code, err_tail, out_tail, jsonl_tail_for_class)

    # Mechanism #2 — try to extract precise reset time from blob
    reset_ms = _parse_reset_time("\n".join([err_tail, out_tail, jsonl_tail_for_class]))

    # Mechanism #6 — track snapshot hash to detect "no progress" loops
    fresh_hash = _read_snapshot_hash(attempt_entry.get("cwd") or "")
    stalled = False
    new_hashes: list = list(attempt_entry.get("snapshotHashes") or [])
    if fresh_hash:
        scratch = {"snapshotHashes": new_hashes}
        stalled = _push_hash_and_check_stall(scratch, fresh_hash)
        new_hashes = scratch["snapshotHashes"]

    with _LOCK:
        store = _load_all()
        if session_id not in store:
            return
        e = store[session_id]
        e["lastExitCode"] = exit_code
        e["lastExitReason"] = reason
        e["lastError"] = err_tail or out_tail or ""
        e["snapshotHashes"] = new_hashes
        if reset_ms:
            e["lastResetAt"] = reset_ms

        notify_kind = None
        notify_summary = ""
        if reason == "clean":
            e["state"] = STATE_DONE
            e["nextAttemptAt"] = 0
            notify_kind = "succeeded"
            notify_summary = "Session resumed successfully on attempt #" + str(e.get("attempts"))
        elif reason == "context_full":
            e["state"] = STATE_FAILED
            e["enabled"] = False
            e["stopReason"] = "context window exceeded — manual intervention required"
            notify_kind = "failed"
            notify_summary = "context_full — session needs manual cleanup"
        elif reason == "auth_expired":
            e["state"] = STATE_FAILED
            e["enabled"] = False
            e["stopReason"] = "auth expired — run `claude /login` and re-enable"
            notify_kind = "failed"
            notify_summary = "auth_expired — run `claude /login` and re-enable"
        elif stalled:
            e["state"] = STATE_EXHAUSTED
            e["enabled"] = False
            e["stopReason"] = (
                f"snapshot hash stalled ({SNAPSHOT_STALL_LIMIT}× identical) "
                "— same place repeating, halting"
            )
            notify_kind = "exhausted"
            notify_summary = "snapshot hash stalled — same place repeating"
        else:
            # rate_limit or unknown — schedule next attempt
            if reason == "rate_limit" and reset_ms:
                e["nextAttemptAt"] = reset_ms
            elif reason == "rate_limit":
                e["nextAttemptAt"] = _now_ms() + int(e.get("pollInterval") or DEFAULT_POLL_INTERVAL) * 1000
            else:
                back = _exponential_backoff(int(e.get("attempts") or 1))
                e["nextAttemptAt"] = _now_ms() + back * 1000
            e["state"] = STATE_WAITING
            log.info(
                "auto_resume: %s exited %s (%s), next attempt in %ds",
                session_id, exit_code, reason,
                max(0, (e["nextAttemptAt"] - _now_ms()) // 1000),
            )
        _dump_all(store)
        # Also exhaustion via maxAttempts is handled at top of _process_one
        # — for the in-flight attempt, we emit the appropriate notify here.
        if notify_kind:
            try:
                _send_notify(e, notify_kind, notify_summary)
            except Exception as ex:
                log.warning("auto_resume: notify dispatch failed: %s", ex)


def _worker_loop() -> None:
    log.info("auto_resume worker started (tick=%ss)", WORKER_TICK_SECONDS)
    while not _WORKER_STOP.wait(WORKER_TICK_SECONDS):
        try:
            store = _load_all()
            ids = [sid for sid, e in store.items() if e.get("enabled")]
            for sid in ids:
                try:
                    _process_one(sid)
                except Exception as e:
                    log.warning("auto_resume: process error for %s: %s", sid, e)
        except Exception as e:
            log.warning("auto_resume worker error: %s", e)
    log.info("auto_resume worker stopped")


def _ensure_worker_running() -> None:
    global _WORKER_THREAD
    with _LOCK:
        if _WORKER_THREAD and _WORKER_THREAD.is_alive():
            return
        _WORKER_STOP.clear()
        _WORKER_THREAD = threading.Thread(
            target=_worker_loop, daemon=True, name="auto-resume-worker"
        )
        _WORKER_THREAD.start()


def start_auto_resume() -> None:
    store = _load_all()
    if any(e.get("enabled") for e in store.values()):
        _ensure_worker_running()
    else:
        log.info("auto_resume: no active bindings on boot")


def stop_auto_resume() -> None:
    _WORKER_STOP.set()
    with _LOCK:
        for proc in list(_RUNNING_PROCS.values()):
            try:
                proc.terminate()
            except Exception:
                pass
        _RUNNING_PROCS.clear()
