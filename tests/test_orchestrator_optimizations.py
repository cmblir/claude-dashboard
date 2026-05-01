"""Tests for cycle-3 optimizations: coalesced reply + plan LRU cache."""
from __future__ import annotations

import importlib
import time
from types import SimpleNamespace

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
    orchestrator._plan_cache_clear_for_tests()
    return orchestrator


# ───────── Coalesced reply ─────────


def test_coalesce_three_in_window(orch):
    """Three replies inside the debounce window collapse into one sink call."""
    sent: list[str] = []
    sink = sent.append
    orch.coalesced_reply("http", "ch", "first",  sink, debounce_ms=80)
    orch.coalesced_reply("http", "ch", "second", sink, debounce_ms=80)
    orch.coalesced_reply("http", "ch", "third",  sink, debounce_ms=80)
    time.sleep(0.2)
    assert sent == ["first\nsecond\nthird"]


def test_coalesce_immediate_when_zero_window(orch):
    sent: list[str] = []
    orch.coalesced_reply("http", "ch", "go", sent.append, debounce_ms=0)
    assert sent == ["go"]


def test_coalesce_isolated_per_channel(orch):
    sent: list[str] = []
    orch.coalesced_reply("http", "A", "alpha", sent.append, debounce_ms=80)
    orch.coalesced_reply("http", "B", "bravo", sent.append, debounce_ms=80)
    time.sleep(0.2)
    # Order is timer-fire order; only assert *what* was sent.
    assert sorted(sent) == ["alpha", "bravo"]


# ───────── Plan cache ─────────


def test_plan_cache_skips_planner_on_repeat(orch, monkeypatch):
    """Second dispatch with the same text + binding hits cache, planner is
    invoked once total (sub-agent + aggregator still run normally)."""
    planner_calls = 0
    other_calls = 0

    def fake_exec(assignee, prompt, **kw):
        nonlocal planner_calls, other_calls
        sysp = (kw.get("system_prompt") or "").lower()
        if "planner" in sysp:
            planner_calls += 1
            return SimpleNamespace(
                status="ok",
                output='{"plan":[{"assignee":"claude:sonnet","task":"step"}]}',
                error="", model="m", provider="p", tokens_total=1,
                duration_ms=1, cost_usd=0.0, raw={},
            )
        other_calls += 1
        return SimpleNamespace(
            status="ok", output="OK", error="",
            model="m", provider="p", tokens_total=1,
            duration_ms=1, cost_usd=0.0, raw={},
        )

    monkeypatch.setattr(orch, "execute_with_assignee", fake_exec)

    r1 = orch.dispatch("identical text", kind="http", channel="ui-test")
    r2 = orch.dispatch("identical text", kind="http", channel="ui-test")
    assert r1["ok"] and r2["ok"]
    assert planner_calls == 1, f"planner ran {planner_calls} times — cache miss?"
    # Each dispatch still runs sub-agents + aggregator (>= 2 each).
    assert other_calls >= 4


def test_plan_cache_distinguishes_text(orch, monkeypatch):
    planner_calls = 0

    def fake_exec(assignee, prompt, **kw):
        nonlocal planner_calls
        if "planner" in (kw.get("system_prompt") or "").lower():
            planner_calls += 1
            return SimpleNamespace(
                status="ok",
                output='{"plan":[{"assignee":"claude:sonnet","task":"x"}]}',
                error="", model="m", provider="p", tokens_total=1,
                duration_ms=1, cost_usd=0.0, raw={},
            )
        return SimpleNamespace(
            status="ok", output="ok", error="",
            model="m", provider="p", tokens_total=1,
            duration_ms=1, cost_usd=0.0, raw={},
        )

    monkeypatch.setattr(orch, "execute_with_assignee", fake_exec)

    orch.dispatch("text one", kind="http", channel="x")
    orch.dispatch("text two", kind="http", channel="x")
    assert planner_calls == 2


def test_plan_cache_lru_evicts(orch, monkeypatch):
    monkeypatch.setattr(orch, "_PLAN_CACHE_SIZE", 2)
    orch._plan_cache_clear_for_tests()
    # Fill cache to capacity, then add a third → first should evict.
    for i in range(3):
        k = orch._plan_cache_key(f"t{i}", None, ["claude:sonnet"])
        orch._plan_cache_set(k, [{"assignee": "claude:sonnet", "task": str(i)}])
    k0 = orch._plan_cache_key("t0", None, ["claude:sonnet"])
    assert orch._plan_cache_get(k0) is None  # evicted
    k2 = orch._plan_cache_key("t2", None, ["claude:sonnet"])
    assert orch._plan_cache_get(k2) is not None
