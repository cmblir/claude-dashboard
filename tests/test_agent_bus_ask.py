"""Tests for agent_bus.ask / reply round-trip."""
from __future__ import annotations

import importlib
import threading
import time

import pytest


@pytest.fixture
def bus(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_DASHBOARD_DB", str(tmp_path / "bus.db"))
    from server import config as _c
    importlib.reload(_c)
    from server import db as _db
    importlib.reload(_db)
    from server import agent_bus
    importlib.reload(agent_bus)
    agent_bus.reset_for_tests()
    return agent_bus


def test_ask_reply_roundtrip(bus):
    def responder():
        for ev in bus.subscribe(["echo.ask"], wait_s=0.5):
            if ev.topic == "echo.ask":
                bus.reply(ev.to_dict(), {"echoed": ev.payload.get("msg")},
                          source="echo-bot")
                return

    th = threading.Thread(target=responder, daemon=True); th.start()
    # Tiny delay so the subscriber registers before the ask publishes.
    time.sleep(0.05)
    out = bus.ask("echo", {"msg": "hello"}, timeout_s=3.0)
    assert out is not None
    assert out["echoed"] == "hello"


def test_ask_times_out_when_no_responder(bus):
    out = bus.ask("nobody.home", {"x": 1}, timeout_s=0.6)
    assert out is None


def test_ask_rejects_bad_input(bus):
    with pytest.raises(ValueError):
        bus.ask("", {})
    with pytest.raises(ValueError):
        bus.ask("topic", "not-a-dict")  # type: ignore[arg-type]


def test_correlation_isolates_replies(bus):
    """Two concurrent asks on the same topic must not cross wires."""
    received: dict[str, dict] = {}

    def responder():
        seen = 0
        for ev in bus.subscribe(["job.ask"], wait_s=0.5):
            if ev.topic == "job.ask":
                bus.reply(ev.to_dict(),
                          {"id": ev.payload["id"], "doubled": ev.payload["id"] * 2},
                          source="doubler")
                seen += 1
                if seen >= 2:
                    return

    def asker(idx: int):
        out = bus.ask("job", {"id": idx}, timeout_s=3.0)
        received[f"a{idx}"] = out or {}

    th_r = threading.Thread(target=responder, daemon=True); th_r.start()
    time.sleep(0.05)
    t1 = threading.Thread(target=asker, args=(7,))
    t2 = threading.Thread(target=asker, args=(11,))
    t1.start(); t2.start(); t1.join(timeout=4); t2.join(timeout=4)
    assert received["a7"]["doubled"] == 14
    assert received["a11"]["doubled"] == 22
