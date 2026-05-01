"""Tests for server.agent_bus — topic routing, dedup, history fallback."""
from __future__ import annotations

import time

import pytest


@pytest.fixture
def fresh_bus(tmp_path, monkeypatch):
    """Point the bus at a tmp DB and reset its in-memory state."""
    db_path = tmp_path / "bus.db"
    monkeypatch.setenv("CLAUDE_DASHBOARD_DB", str(db_path))
    # Re-import after env so config picks up the override.
    import importlib

    from server import config as _c
    importlib.reload(_c)
    from server import db as _db
    importlib.reload(_db)
    from server import agent_bus
    importlib.reload(agent_bus)
    agent_bus.reset_for_tests()
    return agent_bus


def test_publish_and_history_topic_filter(fresh_bus):
    bus = fresh_bus
    bus.publish("orch.run.A.start",    {"x": 1}, source="orch")
    bus.publish("orch.run.A.progress", {"pct": 10}, source="claude:opus")
    bus.publish("wf.42.node.foo",      {"k": "v"}, source="wf")

    only_orch = bus.history(["orch.*"])
    assert {e["topic"] for e in only_orch} == {
        "orch.run.A.start", "orch.run.A.progress",
    }

    only_wf = bus.history(["wf.**"])
    assert [e["topic"] for e in only_wf] == ["wf.42.node.foo"]

    both = bus.history(["orch.*", "wf.**"])
    assert len(both) == 3


def test_dedup_drops_identical_within_window(fresh_bus):
    bus = fresh_bus
    a = bus.publish("orch.run.B.heartbeat", {"alive": True}, source="x")
    b = bus.publish("orch.run.B.heartbeat", {"alive": True}, source="x")
    c = bus.publish("orch.run.B.heartbeat", {"alive": True, "i": 2}, source="x")
    assert a is not None
    assert b is None, "exact repeat within window should be deduped"
    assert c is not None, "different payload should not be deduped"


def test_history_since_id(fresh_bus):
    bus = fresh_bus
    e1 = bus.publish("topic.a", {"n": 1}, source="t")
    e2 = bus.publish("topic.a", {"n": 2}, source="t")
    e3 = bus.publish("topic.a", {"n": 3}, source="t")
    after = bus.history(["topic.*"], since_id=e1.id)
    nums = [e["payload"]["n"] for e in after]
    assert nums == [2, 3]


def test_glob_promotes_trailing_dot_star(fresh_bus):
    """``orch.*`` should match nested topics like ``orch.run.X.dispatch``."""
    bus = fresh_bus
    bus.publish("orch.run.X.dispatch", {"ok": True}, source="t")
    found = bus.history(["orch.*"])
    assert any(e["topic"] == "orch.run.X.dispatch" for e in found)


def test_history_pulls_from_sqlite_after_flush(fresh_bus):
    bus = fresh_bus
    bus.publish("topic.persisted", {"v": 1}, source="t")
    bus.flush_now()
    bus.reset_for_tests()  # Drop in-memory state, force SQLite path.
    # since_id large enough that the (now empty) ring won't satisfy it.
    rows = bus.history(["topic.*"], since_id=0, limit=10)
    assert any(e["topic"] == "topic.persisted" for e in rows)


def test_publish_rejects_bad_input(fresh_bus):
    bus = fresh_bus
    assert bus.publish("", {"x": 1}) is None
    assert bus.publish("topic", "not a dict") is None  # type: ignore[arg-type]


def test_api_publish_and_history(fresh_bus):
    bus = fresh_bus
    r = bus.api_agent_bus_publish({"topic": "api.test", "payload": {"k": 1},
                                   "source": "ui"})
    assert r["ok"] and not r["deduped"]
    h = bus.api_agent_bus_history({"topics": "api.*", "limit": 10})
    assert h["ok"]
    assert any(e["topic"] == "api.test" for e in h["events"])
