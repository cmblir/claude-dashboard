"""Unit tests for server.db schema initialisation.

Covers idempotent _db_init, table/index presence, WAL mode, and the
module-level _INITIALIZED flag. The DB path is redirected to a tmp file
so the user's real ~/.claude-dashboard.db is never touched.
"""
from __future__ import annotations

import sqlite3
import time

import pytest

from server import db as db_mod


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Point server.db at a tmp DB file and force re-init for each test."""
    db_file = tmp_path / "test-dashboard.db"
    monkeypatch.setattr(db_mod, "DB_PATH", db_file)
    monkeypatch.setattr(db_mod, "_INITIALIZED", False)
    # run_history is created by server.run_center, not server.db; create
    # a stub so the index DDL inside _db_init does not silently swallow
    # a missing-table error (it is wrapped in try/except, but we want
    # to exercise the index creation path too).
    with sqlite3.connect(str(db_file)) as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS run_history "
            "(id INTEGER PRIMARY KEY, source TEXT, item_id TEXT, ts INTEGER)"
        )
    return db_file


# ───────── _db_init ─────────

class TestDbInit:
    def test_runs_without_error(self, fresh_db):
        db_mod._db_init()
        assert db_mod._INITIALIZED is True

    def test_initialized_flag_set(self, fresh_db):
        assert db_mod._INITIALIZED is False
        db_mod._db_init()
        assert db_mod._INITIALIZED is True

    def test_second_call_is_fast(self, fresh_db):
        db_mod._db_init()
        t0 = time.perf_counter()
        db_mod._db_init()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        # Idempotent fast-path returns before taking the lock.
        assert elapsed_ms < 5.0, f"second call took {elapsed_ms:.2f}ms"

    def test_creates_db_file(self, fresh_db):
        # The fixture pre-creates run_history; _db_init must keep the file
        # in place and add its own tables on top.
        db_mod._db_init()
        assert fresh_db.exists()


# ───────── schema ─────────

class TestSchema:
    EXPECTED_TABLES = {
        "sessions",
        "tool_uses",
        "agent_edges",
        "workflow_runs",
        "workflow_costs",
        "scores_history",
    }

    EXPECTED_INDEXES = {
        "idx_sess_started",
        "idx_sess_score",
        "idx_sess_cwd_started",
        "idx_sess_tool_use_count",
        "idx_sess_total_tokens",
        "idx_sess_duration_ms",
        "idx_tool_subagent_ts",
        "idx_edge_ts",
        "idx_runs_started",
        "idx_runs_workflow",
        "idx_runs_status",
        "idx_runhist_item_ts",
    }

    def test_all_tables_exist(self, fresh_db):
        db_mod._db_init()
        with db_mod._db() as c:
            rows = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        names = {r["name"] for r in rows}
        missing = self.EXPECTED_TABLES - names
        assert not missing, f"missing tables: {missing}"

    def test_all_indexes_exist(self, fresh_db):
        db_mod._db_init()
        with db_mod._db() as c:
            rows = c.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        names = {r["name"] for r in rows}
        missing = self.EXPECTED_INDEXES - names
        assert not missing, f"missing indexes: {missing}"

    def test_wal_mode_enabled(self, fresh_db):
        db_mod._db_init()
        with db_mod._db() as c:
            mode = c.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

    def test_sessions_has_token_columns(self, fresh_db):
        # Migration path: tokens columns should exist after init.
        db_mod._db_init()
        with db_mod._db() as c:
            cols = {r["name"] for r in c.execute("PRAGMA table_info(sessions)").fetchall()}
        for col in ("input_tokens", "output_tokens", "total_tokens", "cache_read_tokens"):
            assert col in cols, f"sessions.{col} missing"
