"""Claude Code Routines — CRUD + run-now over ``~/.claude/scheduled-tasks/*.yaml``.

The dashboard already had a listing-only tab (``api_scheduled_tasks`` in
``server/system.py``). This module adds the missing create / edit / delete /
run-now backend so users can manage routines without leaving the dashboard.

A routine is a YAML file. We keep the parser tiny (line-based, no PyYAML —
stdlib only):

    name: my-routine
    description: short description
    schedule: "0 */6 * * *"
    command: "claude --print 'do the thing'"
    cwd: "~/work/proj"
    enabled: true

Storage: ``~/.claude/scheduled-tasks/<name>.yaml``.
Run safety: ``cwd`` must resolve under ``$HOME``; we never execute outside.
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import CLAUDE_HOME
from .logger import log
from .utils import _safe_read, _safe_write

ROUTINES_DIR = CLAUDE_HOME / "scheduled-tasks"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_RUN_TIMEOUT = 120
_OUT_CAP = 4000


def _parse_yaml_simple(text: str) -> dict:
    """Tiny line-based YAML extractor — root-level ``key: value`` only.
    Coerces ``enabled`` to bool. Strips surrounding quotes."""
    out: dict = {}
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        if line[0] in (" ", "\t"):  # ignore nested
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        val = v.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        out[key] = val
    if isinstance(out.get("enabled"), str):
        out["enabled"] = out["enabled"].lower() in ("true", "yes", "1", "on")
    return out


def _serialise_yaml(d: dict) -> str:
    """Inverse of `_parse_yaml_simple`. Quotes any value containing a colon
    or hash so the parser can round-trip."""
    lines = []
    order = ["name", "description", "schedule", "command", "cwd", "enabled"]
    for k in order:
        if k not in d:
            continue
        v = d[k]
        if isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
            continue
        s = "" if v is None else str(v)
        if any(c in s for c in (":", "#", "'", '"', "\n")):
            s = '"' + s.replace('"', '\\"') + '"'
        lines.append(f"{k}: {s}")
    return "\n".join(lines) + "\n"


def _under_home(path: str) -> bool:
    try:
        p = Path(path).expanduser().resolve()
    except Exception:
        return False
    home = str(Path.home())
    return str(p) == home or str(p).startswith(home + "/")


def _routine_path(name: str) -> Path | None:
    if not _NAME_RE.match(name or ""):
        return None
    return ROUTINES_DIR / f"{name}.yaml"


# ───────── HTTP handlers ─────────

def api_routines_list(_query: dict | None = None) -> dict:
    if not ROUTINES_DIR.exists():
        return {"items": [], "dir": str(ROUTINES_DIR), "exists": False}
    items: list[dict] = []
    for yp in ROUTINES_DIR.glob("*.yaml"):
        if not yp.is_file():
            continue
        try:
            mtime = int(yp.stat().st_mtime * 1000)
        except Exception:
            mtime = 0
        meta = _parse_yaml_simple(_safe_read(yp) or "")
        items.append({
            "name":        meta.get("name") or yp.stem,
            "description": meta.get("description", ""),
            "schedule":    meta.get("schedule", ""),
            "command":     meta.get("command", ""),
            "cwd":         meta.get("cwd", ""),
            "enabled":     bool(meta.get("enabled", True)),
            "path":        str(yp),
            "mtime":       mtime,
        })
    items.sort(key=lambda x: -x.get("mtime", 0))
    return {"items": items, "dir": str(ROUTINES_DIR), "exists": True, "count": len(items)}


def api_routines_get(name: str) -> dict:
    p = _routine_path(name)
    if not p:
        return {"ok": False, "error": "invalid name"}
    if not p.exists():
        return {"ok": False, "error": "not found"}
    raw = _safe_read(p) or ""
    meta = _parse_yaml_simple(raw)
    return {
        "ok":   True,
        "name": meta.get("name") or p.stem,
        "raw":  raw,
        "meta": {
            "name":        meta.get("name") or p.stem,
            "description": meta.get("description", ""),
            "schedule":    meta.get("schedule", ""),
            "command":     meta.get("command", ""),
            "cwd":         meta.get("cwd", ""),
            "enabled":     bool(meta.get("enabled", True)),
        },
        "path": str(p),
    }


def api_routines_save(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    name = (body.get("name") or "").strip()
    p = _routine_path(name)
    if not p:
        return {"ok": False, "error": "invalid name (^[a-z0-9][a-z0-9_-]{0,63}$)"}
    ROUTINES_DIR.mkdir(parents=True, exist_ok=True)
    raw = body.get("raw")
    if isinstance(raw, str) and raw.strip():
        text = raw if raw.endswith("\n") else raw + "\n"
    else:
        d = {
            "name":        name,
            "description": (body.get("description") or "")[:500],
            "schedule":    (body.get("schedule") or "")[:120],
            "command":     (body.get("command") or "")[:4000],
            "cwd":         (body.get("cwd") or "")[:1024],
            "enabled":     bool(body.get("enabled", True)),
        }
        text = _serialise_yaml(d)
    ok = _safe_write(p, text)
    return {"ok": bool(ok), "path": str(p), "name": name}


def api_routines_delete(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    name = (body.get("name") or "").strip()
    p = _routine_path(name)
    if not p:
        return {"ok": False, "error": "invalid name"}
    if not p.exists():
        return {"ok": False, "error": "not found"}
    try:
        p.unlink()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


def api_routines_run(body: dict) -> dict:
    """Execute the routine's ``command`` once via subprocess. Strict cwd
    sandbox: must resolve under ``$HOME``."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    name = (body.get("name") or "").strip()
    dry  = bool(body.get("dryRun"))
    p = _routine_path(name)
    if not p:
        return {"ok": False, "error": "invalid name"}
    if not p.exists():
        return {"ok": False, "error": "not found"}
    meta = _parse_yaml_simple(_safe_read(p) or "")
    cmd  = meta.get("command") or ""
    cwd_raw = meta.get("cwd") or str(Path.home())
    if not _under_home(cwd_raw):
        return {"ok": False, "error": "cwd outside $HOME — refusing to run"}
    cwd = str(Path(cwd_raw).expanduser().resolve())
    if not cmd.strip():
        return {"ok": False, "error": "command is empty"}

    if dry:
        return {"ok": True, "dryRun": True, "command": cmd, "cwd": cwd}

    t0 = int(time.time() * 1000)
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=_RUN_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {_RUN_TIMEOUT}s",
                "durationMs": int(time.time() * 1000) - t0}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    duration = int(time.time() * 1000) - t0
    return {
        "ok":         proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout":     (proc.stdout or "")[:_OUT_CAP],
        "stderr":     (proc.stderr or "")[:_OUT_CAP],
        "durationMs": duration,
        "command":    cmd,
        "cwd":        cwd,
    }
