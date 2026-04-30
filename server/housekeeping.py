"""v2.54.0 — housekeeping orchestrator.

Surfaces a single endpoint that:
  - reports disk usage of dashboard data files (DB + JSONs + backups dir)
  - exposes one-click prune for backups (retentionDays + keepLast)
  - exposes one-click prune for stale auto-resume entries
  - returns a combined disk-usage + last-prune report
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .auto_resume import api_auto_resume_prune_stale
from .backup import api_backup_prune

_HOME = Path.home()
_DB_PATH = _HOME / ".claude-dashboard.db"
_BACKUPS_DIR = _HOME / ".claude-dashboard-backups"
_SESSIONS_DIR = _HOME / ".claude" / "sessions"
_JSON_GLOB_PATTERN = ".claude-dashboard-*.json"


def _stat_path(p: Path, kind: str) -> dict[str, Any] | None:
    """Return basic stat info for a file path, or None when absent."""
    try:
        st = p.stat()
    except OSError:
        return None
    return {
        "path": str(p),
        "kind": kind,
        "sizeBytes": int(st.st_size),
        "mtime": int(st.st_mtime * 1000),
    }


def _dir_total_bytes(d: Path, *, glob: str | None = None) -> tuple[int, int]:
    """Return (total_size_bytes, file_count) for direct children of ``d``.

    Intentionally non-recursive past one level to keep this cheap on
    large session directories.
    """
    total = 0
    count = 0
    try:
        if not d.exists() or not d.is_dir():
            return 0, 0
        it = d.glob(glob) if glob else d.iterdir()
        for entry in it:
            try:
                st = entry.stat()
            except OSError:
                continue
            if not entry.is_file():
                continue
            total += int(st.st_size)
            count += 1
    except Exception:
        return total, count
    return total, count


def _disk_usage() -> dict[str, Any]:
    """Aggregate dashboard data-file disk usage."""
    paths: list[dict[str, Any]] = []
    total = 0

    db_info = _stat_path(_DB_PATH, "db")
    if db_info is not None:
        paths.append(db_info)
        total += db_info["sizeBytes"]

    # Dashboard JSON state files (workflows, ai-providers, slack, etc.)
    try:
        for jp in sorted(_HOME.glob(_JSON_GLOB_PATTERN)):
            info = _stat_path(jp, "json")
            if info is None:
                continue
            paths.append(info)
            total += info["sizeBytes"]
    except Exception:
        pass

    # Backups directory aggregate.
    backups_size, backups_count = _dir_total_bytes(_BACKUPS_DIR, glob="*.tar.gz")
    paths.append({
        "path": str(_BACKUPS_DIR),
        "kind": "backups",
        "sizeBytes": backups_size,
        "count": backups_count,
        "mtime": 0,
    })
    total += backups_size

    # Claude Code sessions — JSONL only, single-level.
    sessions_size, sessions_count = _dir_total_bytes(_SESSIONS_DIR, glob="*.jsonl")
    paths.append({
        "path": str(_SESSIONS_DIR),
        "kind": "sessions",
        "sizeBytes": sessions_size,
        "count": sessions_count,
        "mtime": 0,
    })
    total += sessions_size

    return {"paths": paths, "totalBytes": total}


def _backup_count() -> int:
    try:
        return sum(1 for _ in _BACKUPS_DIR.glob("*.tar.gz"))
    except Exception:
        return 0


def _ar_entry_count() -> int:
    """Cheap count of auto-resume entries without re-implementing the loader."""
    try:
        from .auto_resume import _load_all  # local import to avoid import cycle on init
        return len(_load_all() or {})
    except Exception:
        return 0


def api_housekeeping_report(query: dict) -> dict:
    """Return disk usage + counters for the housekeeping panel."""
    disk = _disk_usage()
    return {
        "ok": True,
        "diskUsage": disk,
        "backupCount": _backup_count(),
        "autoResumeEntries": _ar_entry_count(),
    }


def api_housekeeping_run(body: dict) -> dict:
    """Run one or more prune actions in sequence and return aggregated results.

    Body shape::

        {
          "prune": {"backups": bool, "autoResume": bool},
          "options": {
            "backups": {"retentionDays": 30, "keepLast": 5},
            "autoResume": {"thresholdDays": 30}
          },
          "dryRun": bool
        }
    """
    prune = body.get("prune") or {}
    options = body.get("options") or {}
    dry_run = bool(body.get("dryRun", False))

    out: dict[str, Any] = {"ok": True, "errors": []}

    if bool(prune.get("backups")):
        opts = dict(options.get("backups") or {})
        opts["dryRun"] = dry_run
        try:
            out["backupPrune"] = api_backup_prune(opts)
        except Exception as e:
            out["errors"].append(f"backupPrune: {e}")

    if bool(prune.get("autoResume")):
        opts = dict(options.get("autoResume") or {})
        opts["dryRun"] = dry_run
        try:
            out["arPrune"] = api_auto_resume_prune_stale(opts)
        except Exception as e:
            out["errors"].append(f"arPrune: {e}")

    return out
