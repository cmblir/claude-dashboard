"""Cycle-4 D6 — per-binding fallback chain + daily budget cap."""
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


def _resp(*, status="ok", output="ok", cost=0.01, error=""):
    return SimpleNamespace(status=status, output=output, error=error,
                           model="m", provider="p", tokens_total=1,
                           duration_ms=1, cost_usd=cost, raw={})


# ───────── Failover chain ─────────


def test_step_succeeds_with_primary(orch, monkeypatch):
    monkeypatch.setattr(orch, "execute_with_assignee",
                        lambda a, p, **k: _resp(output=f"ok:{a}"))
    out = orch._execute_step("rid", 0, "claude:opus", "task",
                             fallback_chain=["claude:sonnet"])
    assert out["ok"] and out["assignee"] == "claude:opus"
    assert out["failoverIndex"] == 0


def test_step_falls_over_when_primary_errors(orch, monkeypatch):
    seen: list[str] = []

    def fake(a, p, **k):
        seen.append(a)
        if a == "claude:opus":
            return _resp(status="err", error="quota")
        return _resp(output=f"hello from {a}")

    monkeypatch.setattr(orch, "execute_with_assignee", fake)
    out = orch._execute_step("rid", 0, "claude:opus", "task",
                             fallback_chain=["claude:sonnet", "openai:gpt-4.1"])
    assert seen == ["claude:opus", "claude:sonnet"]
    assert out["assignee"] == "claude:sonnet"
    assert out["failoverIndex"] == 1


def test_step_exhausts_chain(orch, monkeypatch):
    monkeypatch.setattr(orch, "execute_with_assignee",
                        lambda a, p, **k: _resp(status="err", error="all dead"))
    out = orch._execute_step("rid", 0, "claude:opus", "task",
                             fallback_chain=["claude:sonnet"])
    assert out["ok"] is False
    assert out["failoverIndex"] == 1     # last one tried


def test_step_dedupes_chain(orch, monkeypatch):
    """Primary already in chain → not retried twice."""
    seen: list[str] = []
    monkeypatch.setattr(orch, "execute_with_assignee",
                        lambda a, p, **k: (seen.append(a), _resp())[1])
    orch._execute_step("rid", 0, "claude:opus", "task",
                       fallback_chain=["claude:opus", "claude:sonnet"])
    assert seen == ["claude:opus"]


# ───────── Daily budget cap ─────────


def test_spent_today_sums_results(orch):
    for r in (0.10, 0.25, 0.65):
        orch._persist_run_record(
            f"r{r}", kind="slack", channel="C1", user="u",
            text="x", plan=[],
            results=[{"ok": True, "cost_usd": r}],
            final="", via="ad-hoc", ok=True,
        )
    total = orch._spent_today_usd("slack", "C1")
    assert abs(total - 1.0) < 1e-6


def test_spent_today_isolates_by_channel(orch):
    orch._persist_run_record("a", kind="slack", channel="C1", user="u",
                              text="x", plan=[],
                              results=[{"ok": True, "cost_usd": 1.0}],
                              final="", via="ad-hoc", ok=True)
    orch._persist_run_record("b", kind="slack", channel="C2", user="u",
                              text="x", plan=[],
                              results=[{"ok": True, "cost_usd": 99.0}],
                              final="", via="ad-hoc", ok=True)
    assert abs(orch._spent_today_usd("slack", "C1") - 1.0) < 1e-6
    assert abs(orch._spent_today_usd("slack", "C2") - 99.0) < 1e-6


def test_dispatch_blocks_when_over_budget(orch, monkeypatch):
    # Pre-seed today's spend above the cap
    orch._persist_run_record("seed", kind="slack", channel="C1", user="u",
                              text="x", plan=[],
                              results=[{"ok": True, "cost_usd": 5.0}],
                              final="", via="ad-hoc", ok=True)
    # Bind with a $1/day cap
    orch.api_orch_bind({"kind": "slack", "channel": "C1",
                        "budgetUsdPerDay": 1.0})
    # Stub planner so we don't need real LLM
    monkeypatch.setattr(orch, "execute_with_assignee",
                        lambda *_a, **_k: _resp())
    sent: list[str] = []
    r = orch.dispatch("anything", kind="slack", channel="C1",
                      reply=sent.append)
    assert r["ok"] is False
    assert "budget" in (r.get("error") or "").lower()
    assert sent and "budget" in sent[0].lower()


# ───────── Binding sanitization ─────────


def test_sanitize_keeps_fallback_and_budget(orch):
    b = orch._sanitize_binding({
        "kind": "discord", "channel": "1234567890123456",
        "fallbackChain": ["claude:sonnet", "openai:gpt-4.1", " "],
        "budgetUsdPerDay": "2.5",
    })
    assert b["kind"] == "discord"
    assert b["fallbackChain"] == ["claude:sonnet", "openai:gpt-4.1"]
    assert abs(b["budgetUsdPerDay"] - 2.5) < 1e-6


def test_sanitize_rejects_negative_budget(orch):
    b = orch._sanitize_binding({"kind": "http", "channel": "x",
                                 "budgetUsdPerDay": -1})
    assert "budgetUsdPerDay" not in b


def test_sanitize_caps_fallback_chain_length(orch):
    chain = [f"x:{i}" for i in range(20)]
    b = orch._sanitize_binding({"kind": "http", "channel": "x",
                                 "fallbackChain": chain})
    assert len(b["fallbackChain"]) == 8
