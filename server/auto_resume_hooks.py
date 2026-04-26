"""Auto-Resume hooks — install Stop + SessionStart hooks in a project.

Mechanism #3 (Stop hook progress snapshot) and #4 (SessionStart hook
context injection) live here so `auto_resume.py` itself stays focused
on the supervisor / state machine.

What this module does for a given `<cwd>`
-----------------------------------------
1. Creates `<cwd>/.claude/auto-resume/snapshot.sh` (0755) —
   a tiny bash script that finds the most recent jsonl under
   `~/.claude/projects/<slug>/` and writes a markdown snapshot of the
   last user prompt + tail of the last assistant message to
   `<cwd>/.claude/auto-resume/snapshot.md`.

2. Creates `<cwd>/.claude/auto-resume/inject.sh` (0755) —
   a bash script that `cat`s `snapshot.md` to stdout. Claude Code's
   SessionStart hook contract feeds stdout straight into the new
   session's context, so the next session naturally knows where it
   left off.

3. Patches `<cwd>/.claude/settings.json` to register both as
   `hooks.Stop[]` and `hooks.SessionStart[]` entries (idempotent —
   never doubles up).

`uninstall(cwd)` removes both entries from settings.json and deletes
the two scripts. `status(cwd)` reports current install state.

Safety
------
- Only writes inside `<cwd>/.claude/`. Never touches the user's global
  `~/.claude/settings.json`.
- Atomic writes via `_safe_write`.
- A pre-write backup of `settings.json` is kept at
  `<cwd>/.claude/settings.json.auto-resume.bak` so the user can revert.
"""
from __future__ import annotations

import json
import stat
from pathlib import Path

from .logger import log
from .utils import _safe_read, _safe_write


SNAPSHOT_DIRNAME = "auto-resume"
SNAPSHOT_SH = "snapshot.sh"
INJECT_SH = "inject.sh"
SNAPSHOT_MD = "snapshot.md"
SETTINGS_NAME = "settings.json"
BACKUP_NAME = "settings.json.auto-resume.bak"

HOOK_SIGNATURE = "# lazyclaude-auto-resume"

SNAPSHOT_SH_BODY = r"""#!/usr/bin/env bash
# {sig}
# Stop hook — write a markdown snapshot of the last user prompt + tail
# of the last assistant message so SessionStart can inject it on resume.
set -e
cwd="{cwd}"
out_dir="$cwd/.claude/auto-resume"
out_file="$out_dir/snapshot.md"
mkdir -p "$out_dir"

slug="-$(echo "$cwd" | sed 's,^/,,;s,/,-,g')"
proj_dir="$HOME/.claude/projects/$slug"
[ -d "$proj_dir" ] || exit 0

jsonl=$(ls -t "$proj_dir"/*.jsonl 2>/dev/null | head -n1 || true)
[ -n "$jsonl" ] || exit 0

tail_blob=$(tail -c 204800 "$jsonl")

{{
  echo "# Auto-Resume snapshot"
  echo
  echo "_Source: \\\`$jsonl\\\`_  "
  echo "_Captured: $(date -u +%Y-%m-%dT%H:%M:%SZ)_"
  echo
  echo "## Tail of session transcript (most recent ~200 KB)"
  echo
  echo '```'
  printf '%s\\n' "$tail_blob" | tail -c 6000
  echo '```'
}} > "$out_file.tmp" && mv "$out_file.tmp" "$out_file"
exit 0
"""

INJECT_SH_BODY = r"""#!/usr/bin/env bash
# {sig}
# SessionStart hook — feed the most recent snapshot to Claude.
# stdout is injected into the new session's context.
snap="{cwd}/.claude/auto-resume/snapshot.md"
if [ -f "$snap" ]; then
  echo "[auto-resume] Restoring context from previous session:"
  echo
  cat "$snap"
fi
exit 0
"""


def _project_settings(cwd: str) -> Path:
    return Path(cwd) / ".claude" / SETTINGS_NAME


def _hook_dir(cwd: str) -> Path:
    return Path(cwd) / ".claude" / SNAPSHOT_DIRNAME


def _snapshot_sh_path(cwd: str) -> Path:
    return _hook_dir(cwd) / SNAPSHOT_SH


def _inject_sh_path(cwd: str) -> Path:
    return _hook_dir(cwd) / INJECT_SH


def _backup_path(cwd: str) -> Path:
    return Path(cwd) / ".claude" / BACKUP_NAME


def _make_executable(p: Path) -> None:
    try:
        cur = p.stat().st_mode
        p.chmod(cur | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass


def _load_settings(p: Path) -> dict:
    raw = _safe_read(p)
    if not raw.strip():
        return {}
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _is_our_entry(entry: dict, expected_cmd: str) -> bool:
    """An entry is ours if it carries our command. Tolerates either of the
    two Claude Code hook entry shapes:
        {"type": "command", "command": "..."}
        {"hooks": [{"type": "command", "command": "..."}]}
    """
    if not isinstance(entry, dict):
        return False
    if entry.get("command") == expected_cmd:
        return True
    inner = entry.get("hooks")
    if isinstance(inner, list):
        for h in inner:
            if isinstance(h, dict) and h.get("command") == expected_cmd:
                return True
    return False


def _add_hook(settings: dict, hook_name: str, command: str) -> bool:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        return False
    bucket = hooks.setdefault(hook_name, [])
    if not isinstance(bucket, list):
        return False
    if any(_is_our_entry(e, command) for e in bucket):
        return False
    bucket.append({"hooks": [{"type": "command", "command": command}]})
    return True


def _remove_hook(settings: dict, hook_name: str, command: str) -> int:
    hooks = settings.get("hooks") or {}
    if not isinstance(hooks, dict):
        return 0
    bucket = hooks.get(hook_name) or []
    if not isinstance(bucket, list):
        return 0
    before = len(bucket)
    keep = []
    for e in bucket:
        if _is_our_entry(e, command):
            continue
        if isinstance(e, dict) and isinstance(e.get("hooks"), list):
            inner = [h for h in e["hooks"] if not (isinstance(h, dict) and h.get("command") == command)]
            if inner:
                e = {**e, "hooks": inner}
                keep.append(e)
            continue
        keep.append(e)
    hooks[hook_name] = keep
    return before - len(keep)


def install(cwd: str) -> dict:
    cwd_p = Path(cwd).expanduser().resolve()
    if not cwd_p.is_dir():
        return {"ok": False, "error": f"cwd is not a directory: {cwd_p}"}

    hook_dir = _hook_dir(str(cwd_p))
    hook_dir.mkdir(parents=True, exist_ok=True)

    snapshot_sh = _snapshot_sh_path(str(cwd_p))
    inject_sh = _inject_sh_path(str(cwd_p))

    snapshot_body = SNAPSHOT_SH_BODY.format(sig=HOOK_SIGNATURE, cwd=str(cwd_p))
    inject_body = INJECT_SH_BODY.format(sig=HOOK_SIGNATURE, cwd=str(cwd_p))
    if not _safe_write(snapshot_sh, snapshot_body):
        return {"ok": False, "error": "failed to write snapshot.sh"}
    if not _safe_write(inject_sh, inject_body):
        return {"ok": False, "error": "failed to write inject.sh"}
    _make_executable(snapshot_sh)
    _make_executable(inject_sh)

    settings_p = _project_settings(str(cwd_p))
    settings_p.parent.mkdir(parents=True, exist_ok=True)
    settings = _load_settings(settings_p)

    bak = _backup_path(str(cwd_p))
    if settings_p.exists() and not bak.exists():
        try:
            bak.write_text(settings_p.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass

    added_stop = _add_hook(settings, "Stop", str(snapshot_sh))
    added_start = _add_hook(settings, "SessionStart", str(inject_sh))

    if not _safe_write(settings_p, json.dumps(settings, indent=2, ensure_ascii=False)):
        return {"ok": False, "error": "failed to write settings.json"}

    log.info(
        "auto_resume_hooks: installed for %s (stop+%s start+%s)",
        cwd_p, int(added_stop), int(added_start),
    )
    return {
        "ok": True,
        "cwd": str(cwd_p),
        "snapshotSh": str(snapshot_sh),
        "injectSh": str(inject_sh),
        "settingsPath": str(settings_p),
        "addedStop": added_stop,
        "addedSessionStart": added_start,
        "backupPath": str(bak) if bak.exists() else "",
    }


def uninstall(cwd: str) -> dict:
    cwd_p = Path(cwd).expanduser().resolve()
    settings_p = _project_settings(str(cwd_p))
    snapshot_sh = _snapshot_sh_path(str(cwd_p))
    inject_sh = _inject_sh_path(str(cwd_p))

    removed_stop = removed_start = 0
    if settings_p.exists():
        settings = _load_settings(settings_p)
        removed_stop = _remove_hook(settings, "Stop", str(snapshot_sh))
        removed_start = _remove_hook(settings, "SessionStart", str(inject_sh))
        if not _safe_write(settings_p, json.dumps(settings, indent=2, ensure_ascii=False)):
            return {"ok": False, "error": "failed to write settings.json"}

    deleted = []
    for p in (snapshot_sh, inject_sh):
        try:
            if p.exists():
                p.unlink()
                deleted.append(str(p))
        except Exception as e:
            log.warning("auto_resume_hooks: could not delete %s: %s", p, e)

    return {
        "ok": True,
        "cwd": str(cwd_p),
        "removedStop": removed_stop,
        "removedSessionStart": removed_start,
        "deletedFiles": deleted,
    }


def status(cwd: str) -> dict:
    cwd_p = Path(cwd).expanduser().resolve()
    settings_p = _project_settings(str(cwd_p))
    snapshot_sh = _snapshot_sh_path(str(cwd_p))
    inject_sh = _inject_sh_path(str(cwd_p))
    settings = _load_settings(settings_p) if settings_p.exists() else {}

    def _has_entry(hook_name: str, expected_cmd: str) -> bool:
        bucket = (settings.get("hooks") or {}).get(hook_name) or []
        return any(_is_our_entry(e, expected_cmd) for e in bucket if isinstance(e, dict))

    snapshot_md = _hook_dir(str(cwd_p)) / SNAPSHOT_MD
    last_snap_at = 0
    last_snap_size = 0
    if snapshot_md.exists():
        try:
            st = snapshot_md.stat()
            last_snap_at = int(st.st_mtime * 1000)
            last_snap_size = st.st_size
        except Exception:
            pass

    return {
        "ok": True,
        "cwd": str(cwd_p),
        "snapshotShExists": snapshot_sh.exists(),
        "injectShExists": inject_sh.exists(),
        "stopHookRegistered": _has_entry("Stop", str(snapshot_sh)),
        "sessionStartHookRegistered": _has_entry("SessionStart", str(inject_sh)),
        "settingsPath": str(settings_p),
        "snapshotMdExists": snapshot_md.exists(),
        "snapshotMdMtime": last_snap_at,
        "snapshotMdSize": last_snap_size,
    }
