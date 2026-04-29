"""v2.44.0 — process & resource monitors.

Three read-only monitors plus two narrow mutating endpoints:

  - api_ports_list           open TCP/UDP listening sockets via lsof
  - api_cli_sessions_list    live Claude Code CLI sessions w/ RSS + idle
  - api_memory_snapshot      macOS memory pressure + top-30 processes
  - api_process_kill         SIGTERM/SIGKILL with hard guards
  - api_session_open_terminal thin wrapper over actions.open_session_action
  - api_kill_idle_claude     bulk-SIGTERM idle CLI sessions

Stdlib only. macOS-first (vm_stat / sysctl / lsof / ps). On Linux the
memory snapshot still returns a usable shape but with zero-filled
fields when the macOS-specific commands are missing.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

# Late imports for optional reuse — avoid circulars.
try:
    from .system import _running_sessions  # type: ignore
except Exception:  # pragma: no cover
    _running_sessions = None  # type: ignore

try:
    from .actions import _find_terminal_app_for_pid, open_session_action
except Exception:  # pragma: no cover
    _find_terminal_app_for_pid = lambda pid: ""  # type: ignore
    open_session_action = None  # type: ignore

try:
    from .config import SESSIONS_DIR
except Exception:  # pragma: no cover
    SESSIONS_DIR = Path.home() / ".claude" / "sessions"


_LSOF_TIMEOUT = 5
_PS_TIMEOUT = 3
_KILL_PID_FLOOR = 500           # never touch system pids
_ALLOWED_SIGNALS = {"SIGTERM": signal.SIGTERM, "SIGKILL": signal.SIGKILL}
_CLAUDE_RE = re.compile(r"claude|claude-code|node.*claude", re.IGNORECASE)


# ───────── helpers ─────────

def _run(cmd: list[str], timeout: int) -> tuple[int, str, str]:
    """Run a command and return (rc, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""
    except FileNotFoundError:
        return 127, "", "command not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:  # pragma: no cover
        return 1, "", str(e)


def _ps_metrics(pid: int) -> dict:
    """Return rss_bytes / cpu_pct for a single pid via ps."""
    rc, out, _ = _run(["ps", "-o", "pid=,rss=,pcpu=", "-p", str(pid)], _PS_TIMEOUT)
    if rc != 0 or not out.strip():
        return {"rss_bytes": 0, "cpu_pct": 0.0}
    parts = out.split()
    if len(parts) < 3:
        return {"rss_bytes": 0, "cpu_pct": 0.0}
    try:
        rss_kb = int(parts[1])
        cpu = float(parts[2])
    except ValueError:
        return {"rss_bytes": 0, "cpu_pct": 0.0}
    return {"rss_bytes": rss_kb * 1024, "cpu_pct": cpu}


def _ps_metrics_batch(pids: list) -> dict:
    """Return {pid: {rss_bytes, cpu_pct}} for many pids via ONE ps call.

    perf(v2.45.1): replaces N+1 per-pid `ps` subprocesses in
    api_cli_sessions_list with a single comma-separated `-p` call.
    """
    if not pids:
        return {}
    arg = ",".join(str(p) for p in pids)
    rc, out, _ = _run(["ps", "-o", "pid=,rss=,pcpu=", "-p", arg], _PS_TIMEOUT)
    result = {}
    if rc != 0 or not out.strip():
        return result
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            pid_i = int(parts[0])
            rss_kb = int(parts[1])
            cpu = float(parts[2])
        except ValueError:
            continue
        result[pid_i] = {"rss_bytes": rss_kb * 1024, "cpu_pct": cpu}
    return result


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ───────── ports ─────────

def _parse_lsof_line(line: str, proto: str) -> dict | None:
    """Parse a single lsof row. Skip header. Tolerate malformed rows."""
    cols = line.split()
    if len(cols) < 9:
        return None
    if cols[0] == "COMMAND":  # header
        return None
    command, pid_s, user = cols[0], cols[1], cols[2]
    name = cols[8]
    state = cols[9].strip("()") if (proto == "tcp" and len(cols) >= 10) else ""
    try:
        pid = int(pid_s)
    except ValueError:
        return None
    # name looks like "127.0.0.1:8080" or "*:443" or "[::1]:5000"
    addr, _, port = name.rpartition(":")
    if not port.isdigit():
        return None
    return {
        "pid": pid,
        "command": command,
        "user": user,
        "proto": proto,
        "local_addr": addr or "*",
        "local_port": int(port),
        "state": state,
    }


def api_ports_list(query: dict | None = None) -> dict:
    """GET /api/ports/list — listening TCP + all UDP bindings."""
    rows: list[dict] = []
    rc_t, out_t, _ = _run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], _LSOF_TIMEOUT)
    if rc_t == 127:
        return {"ok": False, "error": "lsof unavailable"}
    for line in out_t.splitlines():
        row = _parse_lsof_line(line, "tcp")
        if row:
            rows.append(row)
    rc_u, out_u, _ = _run(["lsof", "-nP", "-iUDP"], _LSOF_TIMEOUT)
    if rc_u != 127:
        for line in out_u.splitlines():
            row = _parse_lsof_line(line, "udp")
            if row:
                rows.append(row)
    rows.sort(key=lambda r: (r["proto"], r["local_port"]))
    return {"ok": True, "ports": rows}


# ───────── cli sessions ─────────

def _scan_sessions_fallback() -> list[dict]:
    if not SESSIONS_DIR.exists():
        return []
    rows = []
    for p in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        pid = data.get("pid")
        if not pid or not _pid_alive(pid):
            continue
        rows.append({
            "pid": pid,
            "sessionId": data.get("sessionId"),
            "workspace": data.get("cwd") or "",
            "entrypoint": data.get("entrypoint", ""),
            "startedAt": data.get("startedAt"),
            "_mtime": p.stat().st_mtime,
        })
    return rows


def _session_last_activity(session_id: str | None, started_at: Any) -> float:
    """Best-effort epoch for last activity. Falls back to JSON file mtime."""
    if session_id:
        fp = SESSIONS_DIR / f"{session_id}.json"
        if fp.exists():
            try:
                return fp.stat().st_mtime
            except Exception:
                pass
    if isinstance(started_at, (int, float)):
        return float(started_at)
    if isinstance(started_at, str):
        # ISO-8601 → epoch
        try:
            from datetime import datetime
            return datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0
    return 0.0


def api_cli_sessions_list(query: dict | None = None) -> dict:
    """GET /api/sessions-monitor/list — live CLI sessions with RSS/idle."""
    if _running_sessions is not None:
        try:
            base = [s for s in _running_sessions() if s.get("alive")]
        except Exception:
            base = _scan_sessions_fallback()
    else:
        base = _scan_sessions_fallback()
    now = time.time()
    pids = [s.get("pid") for s in base if isinstance(s.get("pid"), int)]
    metrics_map = _ps_metrics_batch(pids)
    out = []
    for s in base:
        pid = s.get("pid")
        if not isinstance(pid, int):
            continue
        metrics = metrics_map.get(pid, {"rss_bytes": 0, "cpu_pct": 0.0})
        last = _session_last_activity(s.get("sessionId"), s.get("startedAt"))
        idle = max(0, int(now - last)) if last > 0 else 0
        try:
            term = _find_terminal_app_for_pid(pid)
        except Exception:
            term = ""
        out.append({
            "sessionId": s.get("sessionId"),
            "pid": pid,
            "cwd": s.get("workspace") or s.get("cwd") or "",
            "entrypoint": s.get("entrypoint", ""),
            "startedAt": s.get("startedAt"),
            "lastActivityAt": last or None,
            "rss_bytes": metrics["rss_bytes"],
            "cpu_pct": metrics["cpu_pct"],
            "idle_seconds": idle,
            "terminal_app": term or "",
        })
    out.sort(key=lambda r: r["rss_bytes"], reverse=True)
    return {"ok": True, "sessions": out}


# ───────── memory snapshot ─────────

def _macos_page_size() -> int:
    rc, out, _ = _run(["sysctl", "-n", "hw.pagesize"], _PS_TIMEOUT)
    if rc == 0 and out.strip().isdigit():
        return int(out.strip())
    return 4096


def _macos_total_bytes() -> int:
    rc, out, _ = _run(["sysctl", "-n", "hw.memsize"], _PS_TIMEOUT)
    if rc == 0 and out.strip().isdigit():
        return int(out.strip())
    return 0


def _parse_vm_stat() -> dict:
    """Parse macOS `vm_stat` output → page counts."""
    rc, out, _ = _run(["vm_stat"], _PS_TIMEOUT)
    if rc != 0:
        return {}
    counts: dict[str, int] = {}
    for line in out.splitlines():
        m = re.match(r"^(.+?):\s+(\d+)\.?\s*$", line)
        if not m:
            continue
        key = m.group(1).strip().lower()
        try:
            counts[key] = int(m.group(2))
        except ValueError:
            continue
    return counts


def _parse_swap() -> dict:
    """Parse `sysctl vm.swapusage` → bytes."""
    rc, out, _ = _run(["sysctl", "-n", "vm.swapusage"], _PS_TIMEOUT)
    if rc != 0 or not out.strip():
        return {"total_bytes": 0, "used_bytes": 0, "free_bytes": 0}
    # e.g. "total = 2048.00M  used = 512.00M  free = 1536.00M  (encrypted)"
    def _to_bytes(tok: str) -> int:
        m = re.match(r"([\d.]+)([MGK])", tok)
        if not m:
            return 0
        v = float(m.group(1))
        unit = m.group(2)
        return int(v * {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}[unit])
    fields = dict(re.findall(r"(total|used|free)\s*=\s*([\d.]+[KMG])", out))
    return {
        "total_bytes": _to_bytes(fields.get("total", "0M")),
        "used_bytes": _to_bytes(fields.get("used", "0M")),
        "free_bytes": _to_bytes(fields.get("free", "0M")),
    }


def _top_processes(limit: int = 30) -> list[dict]:
    rc, out, _ = _run(["ps", "-axo", "pid=,rss=,pcpu=,comm="], _PS_TIMEOUT * 2)
    if rc != 0:
        return []
    rows: list[dict] = []
    for line in out.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
            rss_kb = int(parts[1])
            cpu = float(parts[2])
        except ValueError:
            continue
        comm = parts[3]
        rows.append({
            "pid": pid,
            "rss_bytes": rss_kb * 1024,
            "cpu_pct": cpu,
            "command": comm,
            "isClaudeCode": bool(_CLAUDE_RE.search(comm)),
        })
    rows.sort(key=lambda r: r["rss_bytes"], reverse=True)
    return rows[:limit]


def api_memory_snapshot(query: dict | None = None) -> dict:
    """GET /api/memory/snapshot — system memory + top processes."""
    page = _macos_page_size()
    counts = _parse_vm_stat()
    free_pages = counts.get("pages free", 0)
    active = counts.get("pages active", 0)
    inactive = counts.get("pages inactive", 0)
    wired = counts.get("pages wired down", 0)
    compressed = counts.get("pages occupied by compressor", 0)
    free_b = free_pages * page
    active_b = active * page
    inactive_b = inactive * page
    wired_b = wired * page
    compressed_b = compressed * page
    used_b = active_b + wired_b + compressed_b
    total_b = _macos_total_bytes()
    if total_b == 0:
        total_b = used_b + free_b + inactive_b
    swap = _parse_swap()
    top = _top_processes(30)

    # idle Claude Code session count — reuse cli_sessions_list result
    cli = api_cli_sessions_list({})
    idle_count = sum(1 for s in cli.get("sessions", []) if s.get("idle_seconds", 0) > 600)

    return {
        "ok": True,
        "memory": {
            "total_bytes": total_b,
            "used_bytes": used_b,
            "free_bytes": free_b,
            "active_bytes": active_b,
            "inactive_bytes": inactive_b,
            "wired_bytes": wired_b,
            "compressed_bytes": compressed_b,
            "swap_total_bytes": swap["total_bytes"],
            "swap_used_bytes": swap["used_bytes"],
        },
        "topProcesses": top,
        "idleClaudeCodeCount": idle_count,
    }


# ───────── kill / open-terminal ─────────

def _guard_kill(pid: int, sig_name: str) -> tuple[bool, str | None, int]:
    """Return (ok, error_msg, http_code). 0 = no http hint."""
    if pid == os.getpid():
        return False, "cannot kill self", 400
    if not isinstance(pid, int) or pid < _KILL_PID_FLOOR:
        return False, f"pid must be >= {_KILL_PID_FLOOR}", 400
    if sig_name not in _ALLOWED_SIGNALS:
        return False, f"signal must be one of {sorted(_ALLOWED_SIGNALS)}", 400
    if not _pid_alive(pid):
        return False, "process not running", 404
    return True, None, 0


def api_process_kill(body: dict) -> dict:
    """POST /api/process/kill — SIGTERM/SIGKILL a single pid."""
    if not isinstance(body, dict):
        body = {}
    try:
        pid = int(body.get("pid"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return {"ok": False, "error": "pid required"}
    sig_name = (body.get("signal") or "SIGTERM").strip().upper()
    ok, err, _ = _guard_kill(pid, sig_name)
    if not ok:
        return {"ok": False, "error": err}
    try:
        os.kill(pid, _ALLOWED_SIGNALS[sig_name])
    except PermissionError:
        return {"ok": False, "error": "permission denied"}
    except ProcessLookupError:
        return {"ok": False, "error": "process not running"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "pid": pid, "signal": sig_name}


def api_session_open_terminal(body: dict) -> dict:
    """POST /api/sessions-monitor/open-terminal — focus a session's terminal."""
    if not isinstance(body, dict) or not body.get("sessionId"):
        return {"ok": False, "error": "sessionId required"}
    if open_session_action is None:
        return {"ok": False, "error": "actions module unavailable"}
    try:
        return open_session_action({"sessionId": body["sessionId"]})
    except Exception as e:
        return {"ok": False, "error": str(e)}


def api_kill_idle_claude(body: dict) -> dict:
    """POST /api/memory/kill-idle-claude — SIGTERM all idle CLI sessions."""
    if not isinstance(body, dict):
        body = {}
    try:
        threshold = int(body.get("thresholdSec", 600))
    except (TypeError, ValueError):
        threshold = 600
    threshold = max(60, threshold)
    cli = api_cli_sessions_list({})
    killed: list[int] = []
    skipped: list[dict] = []
    for s in cli.get("sessions", []):
        if s.get("idle_seconds", 0) <= threshold:
            continue
        pid = s.get("pid")
        if not isinstance(pid, int):
            skipped.append({"pid": pid, "reason": "no pid"})
            continue
        ok, err, _ = _guard_kill(pid, "SIGTERM")
        if not ok:
            skipped.append({"pid": pid, "reason": err or "guard"})
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except PermissionError:
            skipped.append({"pid": pid, "reason": "permission denied"})
        except Exception as e:
            skipped.append({"pid": pid, "reason": str(e)})
    return {"ok": True, "killed": killed, "skipped": skipped, "thresholdSec": threshold}
