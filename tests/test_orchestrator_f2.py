"""F2 — Recurrence sweeper."""
from __future__ import annotations

import importlib
import time

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


def test_sanitize_keeps_valid_schedule(orch):
    b = orch._sanitize_binding({
        "kind": "http", "channel": "x",
        "schedule": {"everyMinutes": 30, "prompt": "tick"},
    })
    assert b["schedule"]["everyMinutes"] == 30
    assert b["schedule"]["prompt"] == "tick"
    assert b["schedule"]["lastRunMs"] == 0


def test_sanitize_drops_zero_minutes(orch):
    b = orch._sanitize_binding({
        "kind": "http", "channel": "x",
        "schedule": {"everyMinutes": 0, "prompt": "tick"},
    })
    assert "schedule" not in b


def test_sanitize_drops_empty_prompt(orch):
    b = orch._sanitize_binding({
        "kind": "http", "channel": "x",
        "schedule": {"everyMinutes": 5, "prompt": "  "},
    })
    assert "schedule" not in b


def test_sanitize_caps_at_one_week(orch):
    b = orch._sanitize_binding({
        "kind": "http", "channel": "x",
        "schedule": {"everyMinutes": 999_999, "prompt": "tick"},
    })
    assert b["schedule"]["everyMinutes"] == 7 * 24 * 60


def test_sweep_fires_due_binding(orch, monkeypatch):
    """A binding past its everyMinutes window should fire and update lastRunMs."""
    fired: list[dict] = []

    def fake_dispatch(*a, **kw):
        fired.append(kw)
        return {"ok": True, "runId": "fake"}

    monkeypatch.setattr(orch, "dispatch", fake_dispatch)

    orch.api_orch_bind({
        "kind": "http", "channel": "cron",
        "schedule": {"everyMinutes": 1, "prompt": "ping"},
    })
    n = orch._sweep_once()
    assert n == 1
    # Wait briefly for the daemon thread to invoke fake_dispatch.
    deadline = time.time() + 1.0
    while not fired and time.time() < deadline:
        time.sleep(0.05)
    assert fired, "expected dispatch to be called"
    assert fired[0]["text"] == "ping"
    assert fired[0]["kind"] == "http"


def test_sweep_idempotent_until_window_passes(orch, monkeypatch):
    monkeypatch.setattr(orch, "dispatch", lambda *a, **k: {"ok": True})
    orch.api_orch_bind({
        "kind": "http", "channel": "cron2",
        "schedule": {"everyMinutes": 60, "prompt": "ping"},
    })
    n1 = orch._sweep_once()
    n2 = orch._sweep_once()
    n3 = orch._sweep_once()
    assert n1 == 1 and n2 == 0 and n3 == 0


def test_sweep_no_op_for_unscheduled_binding(orch, monkeypatch):
    monkeypatch.setattr(orch, "dispatch",
                        lambda *a, **k: pytest.fail("should not fire"))
    orch.api_orch_bind({"kind": "http", "channel": "no-schedule"})
    assert orch._sweep_once() == 0


def test_start_sweeper_idempotent(orch):
    assert orch.start_sweeper() is True
    assert orch.start_sweeper() is True       # second call no-op
    orch.stop_sweeper()
