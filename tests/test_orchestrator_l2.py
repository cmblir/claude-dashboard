"""L2 — per-dispatch model overrides."""
from __future__ import annotations

import importlib
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


def _resp(out="ok", status="ok"):
    return SimpleNamespace(status=status, output=out, error="",
                           model="m", provider="p", tokens_total=1,
                           duration_ms=1, cost_usd=0.01, raw={})


def test_override_planner_used(orch, monkeypatch):
    seen: list[str] = []

    def fake(assignee, prompt, **kw):
        seen.append(assignee)
        sysp = (kw.get("system_prompt") or "").lower()
        if "planner" in sysp:
            return _resp('{"plan":[{"assignee":"claude:sonnet","task":"x"}]}')
        return _resp("step output")

    monkeypatch.setattr(orch, "execute_with_assignee", fake)
    orch.dispatch("hello", kind="http", channel="test",
                   override_planner="custom:planner-9")
    # Planner should have been the override, not the cfg default.
    assert "custom:planner-9" in seen


def test_override_aggregator_used(orch, monkeypatch):
    seen: list[str] = []

    def fake(assignee, prompt, **kw):
        seen.append(assignee)
        sysp = (kw.get("system_prompt") or "").lower()
        if "planner" in sysp:
            return _resp('{"plan":[{"assignee":"claude:sonnet","task":"x"}]}')
        # Sub-agent + aggregator both reach here. Distinguish by the prompt.
        if "synthesise" in prompt.lower() or "synthesize" in prompt.lower():
            return _resp("aggregated")
        return _resp("subagent output")

    monkeypatch.setattr(orch, "execute_with_assignee", fake)
    orch.dispatch("hello", kind="http", channel="test",
                   override_aggregator="custom:agg-9")
    assert "custom:agg-9" in seen


def test_override_assignees_used(orch, monkeypatch):
    seen: list[str] = []

    def fake(assignee, prompt, **kw):
        seen.append(assignee)
        sysp = (kw.get("system_prompt") or "").lower()
        if "planner" in sysp:
            # Planner sees the override list in its prompt — verify by output
            assert "custom:opus" in prompt
            assert "custom:sonnet" in prompt
            return _resp('{"plan":[{"assignee":"custom:opus","task":"x"}]}')
        return _resp("ok")

    monkeypatch.setattr(orch, "execute_with_assignee", fake)
    orch.dispatch("hello", kind="http", channel="test",
                   override_assignees=["custom:opus", "custom:sonnet"])


def test_no_override_uses_config(orch, monkeypatch):
    seen: list[str] = []

    def fake(assignee, prompt, **kw):
        seen.append(assignee)
        sysp = (kw.get("system_prompt") or "").lower()
        if "planner" in sysp:
            return _resp('{"plan":[{"assignee":"claude:sonnet","task":"x"}]}')
        return _resp("ok")

    monkeypatch.setattr(orch, "execute_with_assignee", fake)
    cfg = orch.load_config()
    orch.dispatch("hello", kind="http", channel="test")
    assert cfg["plannerAssignee"] in seen


def test_api_dispatch_passes_overrides(orch, monkeypatch):
    seen: dict = {}

    def fake_dispatch(text, **kw):
        seen.update(kw)
        return {"ok": True, "runId": "fake"}

    monkeypatch.setattr(orch, "dispatch", fake_dispatch)
    orch.api_orch_dispatch({
        "text": "hi", "kind": "http", "channel": "x",
        "plannerAssignee": "custom:p",
        "aggregatorAssignee": "custom:a",
        "assignees": ["custom:opus", "custom:sonnet"],
    })
    assert seen.get("override_planner") == "custom:p"
    assert seen.get("override_aggregator") == "custom:a"
    assert seen.get("override_assignees") == ["custom:opus", "custom:sonnet"]
