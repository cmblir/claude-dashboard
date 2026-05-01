"""Tests for server.orchestrator — config, plan parser, dispatch wiring.

These tests stub out ``execute_with_assignee`` so we never make a real LLM call;
the goal is to verify routing/plan/aggregation logic, not the providers
themselves.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


@pytest.fixture
def orch(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_DASHBOARD_ORCHESTRATOR",
                       str(tmp_path / "orch.json"))
    monkeypatch.setenv("CLAUDE_DASHBOARD_DB", str(tmp_path / "bus.db"))
    from server import config as _c
    importlib.reload(_c)
    from server import db as _db
    importlib.reload(_db)
    from server import agent_bus
    importlib.reload(agent_bus)
    from server import orchestrator
    importlib.reload(orchestrator)
    return orchestrator


def test_config_roundtrip(orch):
    cfg_before = orch.load_config()
    assert cfg_before["plannerAssignee"]
    assert cfg_before["bindings"] == []

    r = orch.api_orch_config_save({
        "plannerAssignee": "claude:sonnet",
        "defaultAssignees": ["claude:sonnet", "openai:gpt-4.1"],
        "maxParallel": 3,
    })
    assert r["ok"]
    cfg = orch.load_config()
    assert cfg["plannerAssignee"] == "claude:sonnet"
    assert cfg["maxParallel"] == 3
    assert "openai:gpt-4.1" in cfg["defaultAssignees"]


def test_bind_unbind(orch):
    r1 = orch.api_orch_bind({"kind": "telegram", "chat": "-100",
                             "assignees": ["claude:sonnet"]})
    assert r1["ok"]
    assert orch.find_binding("telegram", "-100") is not None

    # Re-bind with same key replaces, not duplicates.
    r2 = orch.api_orch_bind({"kind": "telegram", "chat": "-100",
                             "assignees": ["claude:opus"]})
    assert r2["ok"]
    assert len(r2["bindings"]) == 1
    assert r2["bindings"][0]["assignees"] == ["claude:opus"]

    r3 = orch.api_orch_unbind({"kind": "telegram", "chat": "-100"})
    assert r3["ok"]
    assert orch.find_binding("telegram", "-100") is None


def test_invalid_binding_rejected(orch):
    assert orch.api_orch_bind({}).get("ok") is False
    assert orch.api_orch_bind({"kind": "fictional", "channel": "x"})["ok"] is False
    assert orch.api_orch_bind({"kind": "slack"})["ok"] is False  # missing channel


def test_parse_plan_fenced_json(orch):
    txt = """Here is the plan:
```json
{"plan":[
  {"assignee":"claude:sonnet","task":"summarise"},
  {"assignee":"openai:gpt-4.1","task":"counter-check"}
]}
```"""
    plan = orch._parse_plan(txt, ["claude:sonnet", "openai:gpt-4.1"])
    assert len(plan) == 2
    assert plan[0]["assignee"] == "claude:sonnet"
    assert plan[1]["task"] == "counter-check"


def test_parse_plan_substitutes_unknown_assignee(orch):
    plan = orch._parse_plan(
        '{"plan":[{"assignee":"unknown:model","task":"do thing"}]}',
        ["claude:sonnet"],
    )
    assert plan == [{"assignee": "claude:sonnet", "task": "do thing"}]


def test_parse_plan_fallback_when_garbage(orch):
    plan = orch._parse_plan("not json at all", ["claude:sonnet"])
    assert plan == [{"assignee": "claude:sonnet", "task": "not json at all"}]


def test_dispatch_uses_stubbed_provider(orch, monkeypatch):
    """dispatch() should plan, fan out, aggregate — without real LLM calls."""
    calls: list[tuple[str, str]] = []

    def fake_exec(assignee, prompt, **kw):
        calls.append((assignee, prompt[:80]))
        # Planner gets called first with the system prompt; return a plan.
        if "planner" in (kw.get("system_prompt") or "").lower():
            return SimpleNamespace(
                status="ok",
                output='{"plan":[{"assignee":"claude:sonnet","task":"step one"}]}',
                error="", model="m", provider="p", tokens_total=10,
                duration_ms=1, cost_usd=0.0, raw={},
            )
        # Sub-agent / aggregator: echo the prompt.
        return SimpleNamespace(
            status="ok", output=f"OK::{prompt[:40]}", error="",
            model="m", provider="p", tokens_total=5, duration_ms=1,
            cost_usd=0.0, raw={},
        )

    monkeypatch.setattr(orch, "execute_with_assignee", fake_exec)

    r = orch.dispatch("hello world", kind="http", channel="ui-test")
    assert r["ok"]
    assert r["plan"][0]["assignee"] == "claude:sonnet"
    assert r["results"][0]["ok"]
    assert "OK::" in r["final"]
    # planner + sub-agent + aggregator
    assert len(calls) >= 3
