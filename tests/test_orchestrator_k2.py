"""K2 — sweeper status endpoint."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def orch(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_DASHBOARD_ORCHESTRATOR",
                       str(tmp_path / "orch.json"))
    monkeypatch.setenv("CLAUDE_DASHBOARD_DB", str(tmp_path / "bus.db"))
    from server import config as _c; importlib.reload(_c)
    from server import db as _db; importlib.reload(_db)
    from server import agent_bus; importlib.reload(agent_bus)
    from server import orchestrator; importlib.reload(orchestrator)
    return orchestrator


def test_status_empty_no_schedules(orch):
    s = orch.sweeper_status()
    assert s["ok"] and s["schedules"] == []
    assert s["intervalSec"] >= 5


def test_status_lists_scheduled_bindings(orch):
    orch.api_orch_bind({
        "kind": "http", "channel": "x",
        "schedule": {"everyMinutes": 10, "prompt": "tick"},
    })
    orch.api_orch_bind({
        "kind": "http", "channel": "y",
        "schedule": {"everyMinutes": 30, "prompt": "tock"},
    })
    s = orch.sweeper_status()
    assert len(s["schedules"]) == 2
    # Sorted by nextFireMs ascending
    assert s["schedules"][0]["nextFireMs"] <= s["schedules"][1]["nextFireMs"]


def test_status_skips_unscheduled(orch):
    orch.api_orch_bind({"kind": "http", "channel": "no-schedule"})
    s = orch.sweeper_status()
    assert s["schedules"] == []


def test_status_marks_due_now_for_never_fired(orch):
    orch.api_orch_bind({
        "kind": "http", "channel": "x",
        "schedule": {"everyMinutes": 5, "prompt": "tick"},
    })
    s = orch.sweeper_status()
    assert s["schedules"][0]["dueNow"] is True


def test_status_after_fire_marks_not_due(orch, monkeypatch):
    monkeypatch.setattr(orch, "dispatch", lambda *a, **k: {"ok": True})
    orch.api_orch_bind({
        "kind": "http", "channel": "x",
        "schedule": {"everyMinutes": 60, "prompt": "tick"},
    })
    orch._sweep_once()    # marks lastRunMs
    s = orch.sweeper_status()
    assert s["schedules"][0]["dueNow"] is False


def test_api_endpoint(orch):
    r = orch.api_orch_sweeper_status({})
    assert r["ok"] is True
    assert "schedules" in r
