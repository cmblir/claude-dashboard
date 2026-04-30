"""Unit tests for server.backup (v2.53.0 — single-archive backup/restore).

All filesystem state is redirected to the per-test tmp_path so the user's
real ``~/.claude-dashboard-backups`` is never touched.
"""
from __future__ import annotations

import json
import re
import sqlite3
import tarfile
from pathlib import Path

import pytest

from server import backup as backup_mod


@pytest.fixture
def isolated_backup(tmp_path, monkeypatch, isolated_home):
    """Redirect every absolute path inside server.backup to tmp.

    server.backup captures ``Path.home()`` into a module-level ``_HOME`` at
    import time, so flipping ``$HOME`` after import isn't enough. We rebind
    each path constant explicitly.
    """
    home = tmp_path
    db = home / ".claude-dashboard.db"
    backups = home / ".claude-dashboard-backups"
    backups.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(backup_mod, "_HOME", home, raising=True)
    monkeypatch.setattr(backup_mod, "_DB_FILE", db, raising=True)
    json_files = [
        home / ".claude-dashboard-workflows.json",
        home / ".claude-dashboard-auto-resume.json",
        home / ".claude-dashboard-ai-providers.json",
        home / ".claude-dashboard-slack.json",
        home / ".claude-dashboard-prefs.json",
        home / ".claude-dashboard-hyper-agents.json",
        home / ".claude-code-router" / "config.json",
    ]
    monkeypatch.setattr(backup_mod, "_JSON_FILES", json_files, raising=True)
    monkeypatch.setattr(
        backup_mod,
        "_ARCHIVE_NAME_MAP",
        {
            ".claude-dashboard.db": db,
            ".claude-dashboard-workflows.json": json_files[0],
            ".claude-dashboard-auto-resume.json": json_files[1],
            ".claude-dashboard-ai-providers.json": json_files[2],
            ".claude-dashboard-slack.json": json_files[3],
            ".claude-dashboard-prefs.json": json_files[4],
            ".claude-dashboard-hyper-agents.json": json_files[5],
            "claude-code-router__config.json": json_files[6],
        },
        raising=True,
    )
    # Force _backup_root() to resolve under tmp.
    monkeypatch.setattr(backup_mod, "_backup_root", lambda: backups)

    return {"home": home, "db": db, "backups": backups, "json_files": json_files}


def _seed_data(layout: dict) -> None:
    """Create a minimal SQLite DB + a JSON file so create() has work to do."""
    db = layout["db"]
    with sqlite3.connect(str(db)) as c:
        c.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        c.execute("INSERT INTO t (v) VALUES ('hello')")
    workflows = layout["json_files"][0]
    workflows.write_text(json.dumps({"workflows": []}), encoding="utf-8")


# ───────── api_backup_list ─────────

class TestList:
    def test_empty_returns_ok_and_empty_array(self, isolated_backup):
        out = backup_mod.api_backup_list({})
        assert out["ok"] is True
        assert out["backups"] == []

    def test_lists_created_archive(self, isolated_backup):
        _seed_data(isolated_backup)
        backup_mod.api_backup_create({"label": "x"})
        out = backup_mod.api_backup_list({})
        assert out["ok"] is True
        assert len(out["backups"]) == 1
        item = out["backups"][0]
        for k in ("name", "path", "sizeBytes", "createdAt", "files"):
            assert k in item
        assert item["sizeBytes"] > 0


# ───────── api_backup_create ─────────

class TestCreate:
    def test_returns_expected_shape(self, isolated_backup):
        _seed_data(isolated_backup)
        out = backup_mod.api_backup_create({"label": "test"})
        assert out["ok"] is True
        assert isinstance(out["name"], str)
        assert isinstance(out["path"], str)
        assert out["sizeBytes"] > 0
        assert isinstance(out["files"], list)
        assert len(out["files"]) >= 1

    def test_filename_pattern(self, isolated_backup):
        _seed_data(isolated_backup)
        out = backup_mod.api_backup_create({"label": "test"})
        # lazyclaude-YYYYMMDD-HHMMSS-test.tar.gz
        assert re.match(
            r"^lazyclaude-\d{8}-\d{6}-test\.tar\.gz$", out["name"]
        ), out["name"]

    def test_archive_contains_manifest(self, isolated_backup):
        _seed_data(isolated_backup)
        out = backup_mod.api_backup_create({"label": "m"})
        with tarfile.open(out["path"], "r:gz") as tf:
            names = [m.name for m in tf.getmembers()]
        assert "manifest.json" in names

    def test_manifest_contents(self, isolated_backup):
        _seed_data(isolated_backup)
        out = backup_mod.api_backup_create({"label": "m"})
        with tarfile.open(out["path"], "r:gz") as tf:
            f = tf.extractfile("manifest.json")
            assert f is not None
            mani = json.loads(f.read().decode("utf-8"))
        assert "version" in mani
        assert "files" in mani
        assert isinstance(mani["files"], list)
        assert "createdAt" in mani
        assert mani.get("label") == "m"

    def test_no_label_still_works(self, isolated_backup):
        _seed_data(isolated_backup)
        out = backup_mod.api_backup_create({})
        assert out["ok"] is True
        assert re.match(r"^lazyclaude-\d{8}-\d{6}\.tar\.gz$", out["name"]), out["name"]

    def test_create_does_not_leak_outside_isolated_root(self, isolated_backup):
        _seed_data(isolated_backup)
        out = backup_mod.api_backup_create({"label": "iso"})
        archived = Path(out["path"]).resolve()
        root = isolated_backup["backups"].resolve()
        assert str(archived).startswith(str(root))


# ───────── api_backup_delete ─────────

class TestDelete:
    def test_round_trip_create_then_delete(self, isolated_backup):
        _seed_data(isolated_backup)
        c = backup_mod.api_backup_create({"label": "rt"})
        assert c["ok"]
        d = backup_mod.api_backup_delete({"name": c["name"]})
        assert d["ok"] is True
        assert backup_mod.api_backup_list({})["backups"] == []

    def test_rejects_path_traversal(self, isolated_backup):
        for bad in ("../etc/passwd", "..\\windows", "../../foo.tar.gz"):
            out = backup_mod.api_backup_delete({"name": bad})
            assert out["ok"] is False

    def test_rejects_slash_in_name(self, isolated_backup):
        out = backup_mod.api_backup_delete({"name": "subdir/foo.tar.gz"})
        assert out["ok"] is False

    def test_rejects_non_archive_extension(self, isolated_backup):
        out = backup_mod.api_backup_delete({"name": "evil.txt"})
        assert out["ok"] is False

    def test_rejects_missing_file(self, isolated_backup):
        out = backup_mod.api_backup_delete({"name": "no-such.tar.gz"})
        assert out["ok"] is False

    def test_rejects_non_manifest_archive(self, isolated_backup, tmp_path):
        # Drop a tar.gz lacking manifest.json into the backup dir.
        bogus = isolated_backup["backups"] / "bogus.tar.gz"
        with tarfile.open(bogus, "w:gz") as tf:
            data = tmp_path / "x.txt"
            data.write_text("noise")
            tf.add(data, arcname="x.txt")
        out = backup_mod.api_backup_delete({"name": "bogus.tar.gz"})
        assert out["ok"] is False
        assert bogus.exists(), "non-manifest archive must NOT be deleted"


# ───────── api_backup_restore ─────────

class TestRestore:
    def test_missing_name_rejected(self, isolated_backup):
        out = backup_mod.api_backup_restore({"name": "no-such.tar.gz"})
        assert out["ok"] is False

    def test_invalid_name_rejected(self, isolated_backup):
        out = backup_mod.api_backup_restore({"name": "../evil.tar.gz"})
        assert out["ok"] is False
