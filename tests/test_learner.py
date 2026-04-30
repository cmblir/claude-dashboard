"""Unit tests for server.learner (v2.46.0 SQL-based pattern extraction)."""
from __future__ import annotations

import sqlite3
import time

import pytest

from server import db as db_mod
from server import learner as learner_mod


@pytest.fixture
def fresh_db(tmp_path, monkeypatch, isolated_home):
    """Redirect server.db at a tmp DB and ensure schema exists."""
    db_file = tmp_path / "test-dashboard.db"
    monkeypatch.setattr(db_mod, "DB_PATH", db_file)
    monkeypatch.setattr(db_mod, "_INITIALIZED", False)
    # run_history is owned by server.run_center; create a stub so _db_init's
    # CREATE INDEX doesn't blow up the test before learner code runs.
    with sqlite3.connect(str(db_file)) as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS run_history "
            "(id INTEGER PRIMARY KEY, source TEXT, item_id TEXT, ts INTEGER)"
        )
    db_mod._db_init()
    return db_file


def _insert_session(
    db_file, sid: str, prompt: str, tools: list[str], started_at_ms: int | None = None
) -> None:
    """Insert one session row + its tool_uses children using the live schema."""
    if started_at_ms is None:
        started_at_ms = int(time.time() * 1000) - 3600_000
    with sqlite3.connect(str(db_file)) as c:
        c.execute(
            "INSERT INTO sessions (session_id, jsonl_path, project_dir, started_at, "
            "first_user_prompt, message_count, total_tokens, mtime) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, f"/fake/{sid}.jsonl", "fake-proj", started_at_ms,
             prompt, 5, 100, started_at_ms),
        )
        for i, tool in enumerate(tools):
            c.execute(
                "INSERT INTO tool_uses (session_id, ts, tool, subagent_type, turn_tokens) "
                "VALUES (?, ?, ?, '', 0)",
                (sid, started_at_ms + i, tool),
            )
        c.commit()


# ───────── _collect_sessions ─────────

class TestCollectSessions:
    def test_empty_db_returns_empty_list(self, fresh_db):
        out = learner_mod._collect_sessions()
        assert out == []

    def test_does_not_raise_on_empty(self, fresh_db):
        learner_mod._collect_sessions()  # must not raise

    def test_returns_inserted_session(self, fresh_db):
        _insert_session(fresh_db, "s1", "do the thing", ["Read", "Edit", "Bash"])
        out = learner_mod._collect_sessions()
        assert len(out) == 1
        s = out[0]
        assert s["firstPrompt"] == "do the thing"
        assert s["tools"] == ["Read", "Edit", "Bash"]

    def test_skips_old_sessions(self, fresh_db):
        # 60 days ago — outside RECENT_DAYS=30 window.
        old_ms = int((time.time() - 60 * 86400) * 1000)
        _insert_session(fresh_db, "old", "stale", ["X"], started_at_ms=old_ms)
        out = learner_mod._collect_sessions()
        assert out == []


# ───────── api_learner_patterns ─────────

class TestApiLearnerPatterns:
    def test_empty_db_shape(self, fresh_db):
        out = learner_mod.api_learner_patterns({})
        assert out["ok"] is True
        assert out["sessions"] == 0
        assert out["patterns"] == []
        assert out["days"] == learner_mod._RECENT_DAYS

    def test_single_session_returns_ok(self, fresh_db):
        _insert_session(fresh_db, "s1", "hello", ["Read", "Edit", "Bash"])
        out = learner_mod.api_learner_patterns({})
        assert out["ok"] is True
        assert out["sessions"] == 1
        assert "stats" in out
        assert "topTools" in out["stats"]

    def test_repeated_prompts_become_pattern(self, fresh_db):
        # _MIN_REPEAT == 3 → seed 3 sessions with the same prompt.
        for i in range(3):
            _insert_session(fresh_db, f"r{i}", "build the feature please",
                            ["Read", "Edit"])
        out = learner_mod.api_learner_patterns({})
        kinds = {p["type"] for p in out["patterns"]}
        assert "repeated_prompt" in kinds

    def test_tool_3gram_becomes_pattern(self, fresh_db):
        # _MIN_SEQ_SUPPORT == 3 — same 3-tool sequence in 3 sessions.
        seq = ["Read", "Edit", "Bash"]
        for i in range(3):
            _insert_session(fresh_db, f"q{i}", f"prompt-{i}-unique-text", seq)
        out = learner_mod.api_learner_patterns({})
        kinds = {p["type"] for p in out["patterns"]}
        assert "tool_sequence" in kinds


# ───────── pure helpers ─────────

class TestPureHelpers:
    def test_norm_prompt_lowercases_and_truncates(self):
        out = learner_mod._norm_prompt("  HELLO   World  " + "x" * 80)
        assert len(out) <= 60
        assert out.startswith("hello world")

    def test_norm_prompt_handles_non_string(self):
        assert learner_mod._norm_prompt(None) == ""
        assert learner_mod._norm_prompt(42) == ""

    def test_tool_ngrams_short_input(self):
        assert learner_mod._tool_ngrams(["A", "B"], n=3) == []

    def test_tool_ngrams_basic(self):
        out = learner_mod._tool_ngrams(["A", "B", "C", "D"], n=3)
        assert out == [("A", "B", "C"), ("B", "C", "D")]
