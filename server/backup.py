"""v2.53.0 — backup/restore system for dashboard persistent data.

Single-archive backups to ~/.claude-dashboard-backups/<timestamp>.tar.gz
containing all *.json data files + a sqlite-vacuumed snapshot of the DB.
Restore from any backup; never overwrites without explicit user opt-in.
"""
from __future__ import annotations

import json
import re
import shutil
import socket
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

from .config import ROOT

# ── Source files to back up ─────────────────────────────────────────────
# Hard-coded since most are not exposed via config.py helpers.
_HOME = Path.home()
_DB_FILE = _HOME / ".claude-dashboard.db"
_JSON_FILES: list[Path] = [
    _HOME / ".claude-dashboard-workflows.json",
    _HOME / ".claude-dashboard-auto-resume.json",
    _HOME / ".claude-dashboard-ai-providers.json",
    _HOME / ".claude-dashboard-slack.json",
    _HOME / ".claude-dashboard-prefs.json",
    _HOME / ".claude-dashboard-hyper-agents.json",
    _HOME / ".claude-code-router" / "config.json",
]

# Map basename-in-archive → absolute restore target. CCR config lives in a
# subdirectory so we flatten into a unique key on archive.
_ARCHIVE_NAME_MAP: dict[str, Path] = {
    ".claude-dashboard.db": _DB_FILE,
    ".claude-dashboard-workflows.json": _HOME / ".claude-dashboard-workflows.json",
    ".claude-dashboard-auto-resume.json": _HOME / ".claude-dashboard-auto-resume.json",
    ".claude-dashboard-ai-providers.json": _HOME / ".claude-dashboard-ai-providers.json",
    ".claude-dashboard-slack.json": _HOME / ".claude-dashboard-slack.json",
    ".claude-dashboard-prefs.json": _HOME / ".claude-dashboard-prefs.json",
    ".claude-dashboard-hyper-agents.json": _HOME / ".claude-dashboard-hyper-agents.json",
    "claude-code-router__config.json": _HOME / ".claude-code-router" / "config.json",
}


def _backup_root() -> Path:
    """Return the backups directory; create if missing."""
    p = _HOME / ".claude-dashboard-backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _files_to_backup() -> list[Path]:
    """Return only existing source paths."""
    out: list[Path] = []
    if _DB_FILE.exists():
        out.append(_DB_FILE)
    for f in _JSON_FILES:
        if f.exists():
            out.append(f)
    return out


def _archive_name_for(src: Path) -> str:
    """Map an absolute source path to its in-archive basename."""
    for name, target in _ARCHIVE_NAME_MAP.items():
        if target == src:
            return name
    return src.name


def _make_db_snapshot(target: Path) -> bool:
    """Atomic SQLite snapshot via VACUUM INTO (no locks held on source)."""
    try:
        if not _DB_FILE.exists():
            return False
        # VACUUM INTO requires the destination to not exist.
        if target.exists():
            target.unlink()
        with sqlite3.connect(str(_DB_FILE)) as conn:
            conn.execute("VACUUM INTO ?", (str(target),))
        return target.exists()
    except Exception:
        return False


def _read_version() -> str:
    """Read VERSION file at repo root; fallback to 'unknown'."""
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip() or "unknown"
    except Exception:
        return "unknown"


def _safe_label(label: str) -> str:
    """Sanitize user label for filename use."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", label.strip())
    return s.strip("-")[:40]


def _is_safe_backup_name(name: str) -> bool:
    """Reject path traversal and non-archive names."""
    if not name or "/" in name or "\\" in name or ".." in name:
        return False
    return name.endswith(".tar.gz")


def _archive_has_manifest(path: Path) -> bool:
    """Quick check: does the tarball contain a manifest.json?"""
    try:
        with tarfile.open(path, "r:gz") as tf:
            for m in tf.getmembers():
                if m.name == "manifest.json" or m.name.endswith("/manifest.json"):
                    return True
    except Exception:
        return False
    return False


# ── API handlers ────────────────────────────────────────────────────────


def _backup_age_days(path: Path) -> float:
    """Return age in days based on file mtime (now - mtime). 0 if unavailable."""
    try:
        st = path.stat()
    except OSError:
        return 0.0
    return max(0.0, (time.time() - st.st_mtime) / 86400.0)


def _list_backups_meta(*, with_files: bool = False) -> list[dict[str, Any]]:
    """Return backup archive metadata sorted by mtime desc.

    Factored out so prune can reuse the same listing logic. When
    ``with_files`` is True the inner-tar file count is computed (slower).
    """
    root = _backup_root()
    items: list[dict[str, Any]] = []
    for p in root.glob("*.tar.gz"):
        try:
            st = p.stat()
        except OSError:
            continue
        items.append({
            "name": p.name,
            "path": str(p),
            "sizeBytes": st.st_size,
            "createdAt": int(st.st_mtime * 1000),
            "ageDays": (time.time() - st.st_mtime) / 86400.0,
            "files": 0,
        })
    items.sort(key=lambda x: x["createdAt"], reverse=True)
    if with_files:
        for it in items:
            try:
                with tarfile.open(it["path"], "r:gz") as tf:
                    names = [m.name for m in tf.getmembers() if m.isfile()]
                    it["files"] = max(0, len([n for n in names if not n.endswith("manifest.json")]))
            except Exception:
                it["files"] = 0
    return items


def api_backup_list(query: dict) -> dict:
    """List backups in ~/.claude-dashboard-backups, mtime desc."""
    items = _list_backups_meta(with_files=True)
    # Strip internal-only fields for response stability.
    for it in items:
        it.pop("ageDays", None)
    return {"ok": True, "backups": items}


def api_backup_prune(body: dict) -> dict:
    """Prune backups older than ``retentionDays`` while keeping the most recent ``keepLast``.

    Body: ``{retentionDays: int = 30, keepLast: int = 5, dryRun: bool = false}``.
    Safety: refuses to leave zero backups behind.
    """
    try:
        retention_days = int(body.get("retentionDays", 30))
    except Exception:
        retention_days = 30
    try:
        keep_last = int(body.get("keepLast", 5))
    except Exception:
        keep_last = 5
    dry_run = bool(body.get("dryRun", False))
    retention_days = max(0, retention_days)
    keep_last = max(0, keep_last)

    items = _list_backups_meta(with_files=False)
    if not items:
        return {"ok": True, "kept": [], "deleted": [], "freedBytes": 0, "dryRun": dry_run}

    keep_names: set[str] = set()
    delete_candidates: list[dict[str, Any]] = []
    # ``items`` already sorted newest-first.
    for idx, it in enumerate(items):
        if idx < keep_last:
            keep_names.add(it["name"])
            continue
        if it.get("ageDays", 0.0) < retention_days:
            keep_names.add(it["name"])
            continue
        delete_candidates.append(it)

    # Safety net: never delete down to zero backups.
    if delete_candidates and len(items) - len(delete_candidates) <= 0:
        # Promote the newest deletion candidate back to kept.
        rescued = delete_candidates.pop(0)
        keep_names.add(rescued["name"])

    deleted_names: list[str] = []
    freed = 0
    root = _backup_root()
    root_resolved = root.resolve()
    for it in delete_candidates:
        name = it["name"]
        size = int(it.get("sizeBytes", 0) or 0)
        if dry_run:
            deleted_names.append(name)
            freed += size
            continue
        try:
            target = (root / name).resolve()
            if root_resolved not in target.parents:
                continue
            if not _archive_has_manifest(target):
                continue
            target.unlink()
            deleted_names.append(name)
            freed += size
        except Exception:
            continue

    return {
        "ok": True,
        "kept": sorted(keep_names),
        "deleted": deleted_names,
        "freedBytes": freed,
        "dryRun": dry_run,
    }


def api_backup_create(body: dict) -> dict:
    """Create a new backup archive containing all existing data files."""
    label = _safe_label(str(body.get("label") or ""))
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    suffix = f"-{label}" if label else ""
    name = f"lazyclaude-{ts}{suffix}.tar.gz"
    root = _backup_root()
    final_path = root / name
    tmp_path = root / (name + ".tmp")

    sources = _files_to_backup()
    archived: list[str] = []

    with tempfile.TemporaryDirectory(prefix="lcbk_") as tmpdir:
        staging = Path(tmpdir)
        # DB snapshot
        if _DB_FILE.exists():
            db_snap = staging / ".claude-dashboard.db"
            if _make_db_snapshot(db_snap):
                archived.append(db_snap.name)
        # Copy JSON files into staging using mapped archive names
        for src in sources:
            if src == _DB_FILE:
                continue
            dst = staging / _archive_name_for(src)
            try:
                shutil.copy2(src, dst)
                archived.append(dst.name)
            except Exception:
                continue

        # Manifest
        manifest = {
            "version": _read_version(),
            "files": archived,
            "createdAt": int(time.time() * 1000),
            "hostname": socket.gethostname(),
            "label": label,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Tar (atomic via tmp + rename)
        try:
            with tarfile.open(tmp_path, "w:gz") as tf:
                for entry in sorted(staging.iterdir()):
                    tf.add(entry, arcname=entry.name)
            tmp_path.replace(final_path)
        except Exception as e:
            try:
                tmp_path.unlink()
            except Exception:
                pass
            return {"ok": False, "error": f"archive failed: {e}"}

    try:
        size = final_path.stat().st_size
    except OSError:
        size = 0
    return {
        "ok": True,
        "name": final_path.name,
        "path": str(final_path),
        "sizeBytes": size,
        "files": archived,
    }


def api_backup_restore(body: dict) -> dict:
    """Restore files from a backup archive. Refuses to overwrite by default."""
    name = str(body.get("name") or "")
    overwrite = bool(body.get("overwrite", False))
    only_files = body.get("files")
    if only_files is not None and not isinstance(only_files, list):
        return {"ok": False, "error": "files must be a list"}

    if not _is_safe_backup_name(name):
        return {"ok": False, "error": "invalid backup name"}
    src = _backup_root() / name
    if not src.exists():
        return {"ok": False, "error": "backup not found"}
    if not _archive_has_manifest(src):
        return {"ok": False, "error": "archive missing manifest.json"}

    restored: list[str] = []
    skipped: list[str] = []

    with tempfile.TemporaryDirectory(prefix="lcrest_") as tmpdir:
        staging = Path(tmpdir)
        try:
            with tarfile.open(src, "r:gz") as tf:
                # Safe extraction: validate names, no absolute / parent traversal
                for m in tf.getmembers():
                    if m.name.startswith("/") or ".." in Path(m.name).parts:
                        return {"ok": False, "error": f"unsafe path in archive: {m.name}"}
                tf.extractall(staging)
        except Exception as e:
            return {"ok": False, "error": f"extract failed: {e}"}

        # Pre-flight overwrite check
        if not overwrite:
            for archive_name, target in _ARCHIVE_NAME_MAP.items():
                staged = staging / archive_name
                if not staged.exists():
                    continue
                if only_files and archive_name not in only_files:
                    continue
                if target.exists():
                    return {
                        "ok": False,
                        "error": f"target exists: {target.name}, pass overwrite=true to confirm",
                    }

        # Copy each file to its target
        for archive_name, target in _ARCHIVE_NAME_MAP.items():
            staged = staging / archive_name
            if not staged.exists():
                continue
            if only_files and archive_name not in only_files:
                skipped.append(archive_name)
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged, target)
                restored.append(archive_name)
            except Exception:
                skipped.append(archive_name)

    return {"ok": True, "restored": restored, "skipped": skipped}


def api_backup_delete(body: dict) -> dict:
    """Delete a backup archive — only files inside _backup_root() with manifest."""
    name = str(body.get("name") or "")
    if not _is_safe_backup_name(name):
        return {"ok": False, "error": "invalid backup name"}
    root = _backup_root()
    target = root / name
    try:
        target_resolved = target.resolve()
        root_resolved = root.resolve()
        # Containment check (no traversal escape)
        if root_resolved not in target_resolved.parents:
            return {"ok": False, "error": "path escapes backup root"}
    except Exception:
        return {"ok": False, "error": "invalid path"}
    if not target_resolved.exists():
        return {"ok": False, "error": "backup not found"}
    if not _archive_has_manifest(target_resolved):
        return {"ok": False, "error": "not a recognized backup archive"}
    try:
        target_resolved.unlink()
    except Exception as e:
        return {"ok": False, "error": f"delete failed: {e}"}
    return {"ok": True}
