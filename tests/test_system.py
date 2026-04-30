"""Unit tests for server.system + the v2.46.0 sessions stats fix.

``api_sessions_stats`` lives in ``server.sessions`` (the user's brief flagged
it for the v2.46.0 daily-timeline bug fix). Everything else is in
``server.system``.
"""
from __future__ import annotations

import json
import sqlite3
import time

import pytest

from server import db as db_mod
from server import sessions as sessions_mod
from server import system as sys_mod


@pytest.fixture
def fresh_db(tmp_path, monkeypatch, isolated_home):
    """Tmp SQLite DB with full schema initialised."""
    db_file = tmp_path / "test-dashboard.db"
    monkeypatch.setattr(db_mod, "DB_PATH", db_file)
    monkeypatch.setattr(db_mod, "_INITIALIZED", False)
    with sqlite3.connect(str(db_file)) as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS run_history "
            "(id INTEGER PRIMARY KEY, source TEXT, item_id TEXT, ts INTEGER)"
        )
    db_mod._db_init()
    return db_file


@pytest.fixture
def tmp_sessions_dir(tmp_path, monkeypatch):
    """Redirect SESSIONS_DIR (used by _running_sessions) to tmp."""
    d = tmp_path / "sessions"
    d.mkdir()
    monkeypatch.setattr(sys_mod, "SESSIONS_DIR", d)
    return d


def _insert_session_row(db_file, sid: str, *,
                        cwd: str = "", project_dir: str = "fake-proj",
                        total_tokens: int = 100,
                        tool_use_count: int = 5,
                        score: float = 50.0,
                        started_at_ms: int | None = None) -> None:
    if started_at_ms is None:
        started_at_ms = int(time.time() * 1000) - 3600_000
    with sqlite3.connect(str(db_file)) as c:
        c.execute(
            "INSERT INTO sessions ("
            "session_id, jsonl_path, project_dir, cwd, started_at, "
            "first_user_prompt, message_count, total_tokens, "
            "input_tokens, output_tokens, cache_read_tokens, "
            "cache_creation_tokens, model, tool_use_count, "
            "agent_call_count, error_count, score, mtime"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, f"/fake/{sid}.jsonl", project_dir, cwd, started_at_ms,
             "hello", 5, total_tokens, 30, 70, 0, 0, "claude-sonnet-4",
             tool_use_count, 0, 0, score, started_at_ms),
        )
        c.commit()


# ───────── _running_sessions ─────────

class TestRunningSessions:
    def test_returns_list_when_dir_missing(self, tmp_path, monkeypatch):
        missing = tmp_path / "nope"
        monkeypatch.setattr(sys_mod, "SESSIONS_DIR", missing)
        assert sys_mod._running_sessions() == []

    def test_empty_dir_returns_empty(self, tmp_sessions_dir):
        assert sys_mod._running_sessions() == []

    def test_parses_session_json(self, tmp_sessions_dir):
        (tmp_sessions_dir / "s1.json").write_text(json.dumps({
            "sessionId": "abc",
            "cwd": "/work/foo",
            "pid": 999999,
            "kind": "claude",
            "entrypoint": "cli",
            "startedAt": 0,
        }))
        out = sys_mod._running_sessions()
        assert len(out) == 1
        assert out[0]["sessionId"] == "abc"
        # PID is unlikely-to-exist → alive False.
        assert out[0]["alive"] is False

    def test_skips_invalid_json(self, tmp_sessions_dir):
        (tmp_sessions_dir / "bad.json").write_text("not json {{{")
        assert sys_mod._running_sessions() == []


# ───────── api_usage_summary ─────────

class TestUsageSummary:
    def test_empty_db_shape(self, fresh_db):
        out = sys_mod.api_usage_summary()
        assert "tokens" in out
        for k in ("all", "last30d", "dailyTimeline", "byProject", "byTool",
                 "byAgent", "topSessions"):
            assert k in out["tokens"]
        assert out["tokens"]["all"]["total"] == 0
        assert out["tokens"]["all"]["sessions"] == 0

    def test_with_data(self, fresh_db):
        _insert_session_row(fresh_db, "s1", cwd="/work/foo", total_tokens=500)
        out = sys_mod.api_usage_summary()
        assert out["tokens"]["all"]["total"] >= 500
        assert out["tokens"]["all"]["sessions"] >= 1


# ───────── api_usage_project ─────────

class TestUsageProject:
    def test_missing_cwd_rejected(self, fresh_db):
        out = sys_mod.api_usage_project({})
        assert out["ok"] is False

    def test_empty_string_cwd_rejected(self, fresh_db):
        out = sys_mod.api_usage_project({"cwd": ""})
        assert out["ok"] is False

    def test_path_outside_home_rejected(self, fresh_db, isolated_home):
        # /etc/passwd resolves outside $HOME (which the fixture set to tmp).
        out = sys_mod.api_usage_project({"cwd": "/etc/passwd"})
        assert out["ok"] is False
        assert "home" in out["error"].lower()

    def test_path_traversal_rejected(self, fresh_db, isolated_home):
        # Traversal that resolves outside $HOME must be rejected.
        out = sys_mod.api_usage_project({"cwd": "/tmp/../etc"})
        assert out["ok"] is False

    def test_valid_path_under_home(self, fresh_db, isolated_home):
        cwd = str(isolated_home / "work")
        out = sys_mod.api_usage_project({"cwd": cwd})
        # Should not crash; ok=True is expected (path is under $HOME).
        assert out["ok"] is True


# ───────── api_sessions_stats (v2.46.0 daily-timeline fix) ─────────

class TestSessionsStats:
    def test_empty_db_shape(self, fresh_db):
        out = sessions_mod.api_sessions_stats()
        for k in (
            "totalSessions", "scoredSessions", "minToolsForScore",
            "avgScore", "totalTools", "totalAgentCalls", "totalErrors",
            "toolDistribution", "subagentDistribution",
            "topSessions", "projectDistribution", "timeline",
        ):
            assert k in out
        assert out["totalSessions"] == 0
        assert isinstance(out["timeline"], list)

    def test_counts_inserted_session(self, fresh_db):
        _insert_session_row(fresh_db, "s1", cwd="/work/foo",
                            tool_use_count=10, score=80.0)
        out = sessions_mod.api_sessions_stats()
        assert out["totalSessions"] == 1
        assert out["totalTools"] == 10

    def test_timeline_built_once_not_per_project(self, fresh_db):
        # The v2.46.0 fix moved the daily timeline query out of a per-project
        # loop. Insert sessions across two projects + days, then verify the
        # timeline returns at most 2 buckets (one per distinct day).
        now_ms = int(time.time() * 1000)
        _insert_session_row(fresh_db, "a", cwd="/work/p1",
                            started_at_ms=now_ms - 86400_000,
                            tool_use_count=10, score=70)
        _insert_session_row(fresh_db, "b", cwd="/work/p2",
                            started_at_ms=now_ms - 172800_000,
                            tool_use_count=10, score=80)
        out = sessions_mod.api_sessions_stats()
        assert isinstance(out["timeline"], list)
        assert len(out["timeline"]) <= 2
        for bucket in out["timeline"]:
            for k in ("date", "sessions", "tools", "errors"):
                assert k in bucket
