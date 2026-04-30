"""Unit tests for server.briefing — overview / projects-summary / activity.

The public functions are named without the ``api_`` prefix in source
(``briefing_overview``, ``briefing_projects_summary``, etc.) — they are
wired up to ``/api/briefing/*`` routes from ``server.routes``.
"""
from __future__ import annotations

import json
import time

import pytest

from server import briefing as br_mod


@pytest.fixture
def isolated_briefing(tmp_path, monkeypatch, isolated_home):
    """Redirect every config path used by server.briefing to tmp."""
    claude_home = tmp_path / ".claude"
    claude_home.mkdir()
    history = claude_home / "history.jsonl"
    projects = claude_home / "projects"
    sessions = claude_home / "sessions"
    todos = claude_home / "todos"
    tasks = claude_home / "tasks"
    scheduled = claude_home / "scheduled-tasks"
    for d in (projects, sessions, todos, tasks, scheduled):
        d.mkdir()

    monkeypatch.setattr(br_mod, "HISTORY_JSONL", history)
    monkeypatch.setattr(br_mod, "PROJECTS_DIR", projects)
    monkeypatch.setattr(br_mod, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(br_mod, "TODOS_DIR", todos)
    monkeypatch.setattr(br_mod, "TASKS_DIR", tasks)
    monkeypatch.setattr(br_mod, "SCHEDULED_TASKS_DIR", scheduled)
    return {
        "history": history, "projects": projects, "sessions": sessions,
        "todos": todos, "tasks": tasks, "scheduled": scheduled,
    }


def _write_history(path, entries):
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n",
                    encoding="utf-8")


# ───────── briefing_overview ─────────

class TestOverview:
    def test_empty_state_shape(self, isolated_briefing):
        out = br_mod.briefing_overview()
        assert isinstance(out, dict)
        for k in (
            "projectCount", "taskCount", "sessionCount",
            "commandCount", "todayProjectCount",
            "autoResumeActiveCount", "lastUpdate",
        ):
            assert k in out

    def test_empty_state_counts_are_zero(self, isolated_briefing):
        out = br_mod.briefing_overview()
        assert out["projectCount"] == 0
        assert out["sessionCount"] == 0
        assert out["taskCount"] == 0

    def test_counts_non_negative(self, isolated_briefing):
        out = br_mod.briefing_overview()
        for k in ("projectCount", "taskCount", "sessionCount",
                 "commandCount", "todayProjectCount",
                 "autoResumeActiveCount"):
            assert out[k] >= 0

    def test_project_dir_count(self, isolated_briefing):
        (isolated_briefing["projects"] / "proj-a").mkdir()
        (isolated_briefing["projects"] / "proj-b").mkdir()
        out = br_mod.briefing_overview()
        assert out["projectCount"] == 2

    def test_session_count(self, isolated_briefing):
        (isolated_briefing["sessions"] / "s1.json").write_text("{}")
        (isolated_briefing["sessions"] / "s2.json").write_text("{}")
        out = br_mod.briefing_overview()
        assert out["sessionCount"] == 2

    def test_todo_task_count(self, isolated_briefing):
        (isolated_briefing["todos"] / "x.json").write_text(
            json.dumps([{"id": 1}, {"id": 2}, {"id": 3}])
        )
        out = br_mod.briefing_overview()
        assert out["taskCount"] == 3


# ───────── briefing_projects_summary ─────────

class TestProjectsSummary:
    def test_empty_returns_dict(self, isolated_briefing):
        out = br_mod.briefing_projects_summary()
        assert isinstance(out, dict)
        assert "summaries" in out
        assert "projects" in out
        assert isinstance(out["summaries"], list)

    def test_empty_summaries(self, isolated_briefing):
        out = br_mod.briefing_projects_summary()
        assert out["summaries"] == []

    def test_summarises_history_entries(self, isolated_briefing):
        now_ms = int(time.time() * 1000)
        _write_history(isolated_briefing["history"], [
            {"timestamp": now_ms, "project": "/work/foo", "display": "first"},
            {"timestamp": now_ms + 1, "project": "/work/foo", "display": "second"},
            {"timestamp": now_ms + 2, "project": "/work/bar", "display": "other"},
        ])
        out = br_mod.briefing_projects_summary()
        assert len(out["summaries"]) == 2
        cwds = {s["cwd"] for s in out["summaries"]}
        assert cwds == {"/work/foo", "/work/bar"}


# ───────── briefing_activity ─────────

class TestActivity:
    def test_shape(self, isolated_briefing):
        out = br_mod.briefing_activity()
        assert "today" in out
        assert "activities" in out
        assert out["today"]["commandCount"] >= 0
