"""Ralph engine — termination paths + persistence."""
from __future__ import annotations

import importlib
import time
from types import SimpleNamespace

import pytest


@pytest.fixture
def ralph_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_DASHBOARD_DB", str(tmp_path / "ralph.db"))
    from server import config as _c; importlib.reload(_c)
    from server import db as _db; importlib.reload(_db)
    from server import agent_bus; importlib.reload(agent_bus)
    from server import ralph; importlib.reload(ralph)
    return ralph


def _stub(output="(working)", cost=0.05, status="ok"):
    return SimpleNamespace(status=status, output=output, error="",
                           model="m", provider="p", tokens_total=10,
                           duration_ms=1, cost_usd=cost, raw={})


def _wait_done(ralph, rid, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = ralph.status(rid)
        if s and s["status"] != "running":
            return s
        time.sleep(0.05)
    raise AssertionError("ralph run never finished")


def test_completion_promise_terminates(ralph_mod, monkeypatch):
    n = {"i": 0}

    def fake(*_, **__):
        n["i"] += 1
        if n["i"] >= 3:
            return _stub(output="alright <promise>DONE</promise>")
        return _stub()

    monkeypatch.setattr(ralph_mod, "execute_with_assignee", fake)
    r = ralph_mod.start("task", max_iterations=10, completion_promise="<promise>DONE</promise>",
                        budget_usd=10)
    s = _wait_done(ralph_mod, r["runId"])
    assert s["status"] == "done"
    assert s["iterations"] == 3


def test_max_iter_terminates(ralph_mod, monkeypatch):
    monkeypatch.setattr(ralph_mod, "execute_with_assignee",
                        lambda *_a, **_k: _stub())
    r = ralph_mod.start("task", max_iterations=4, budget_usd=999)
    s = _wait_done(ralph_mod, r["runId"])
    assert s["status"] == "max_iter"
    assert s["iterations"] == 4


def test_budget_terminates(ralph_mod, monkeypatch):
    monkeypatch.setattr(ralph_mod, "execute_with_assignee",
                        lambda *_a, **_k: _stub(cost=0.5))
    r = ralph_mod.start("task", max_iterations=999, budget_usd=1.2)
    s = _wait_done(ralph_mod, r["runId"])
    assert s["status"] == "budget"
    # 0.5 * 3 = 1.5 hit the cap on the third iteration
    assert s["iterations"] >= 2


def test_cancel_terminates(ralph_mod, monkeypatch):
    monkeypatch.setattr(ralph_mod, "execute_with_assignee",
                        lambda *_a, **_k: (time.sleep(0.05) or _stub()))
    r = ralph_mod.start("task", max_iterations=999, budget_usd=999)
    time.sleep(0.05)
    ralph_mod.cancel(r["runId"])
    s = _wait_done(ralph_mod, r["runId"], timeout=3)
    assert s["status"] == "cancelled"


def test_hard_max_clamp(ralph_mod, monkeypatch):
    monkeypatch.setattr(ralph_mod, "_HARD_MAX_ITER", 5)
    monkeypatch.setattr(ralph_mod, "execute_with_assignee",
                        lambda *_a, **_k: _stub())
    r = ralph_mod.start("task", max_iterations=9999, budget_usd=999)
    assert r["maxIter"] == 5


def test_iterations_recorded(ralph_mod, monkeypatch):
    monkeypatch.setattr(ralph_mod, "execute_with_assignee",
                        lambda *_a, **_k: _stub(output="hi", cost=0.1))
    r = ralph_mod.start("t", max_iterations=3, budget_usd=999)
    s = _wait_done(ralph_mod, r["runId"])
    assert len(s["iterationsDetail"]) == 3
    assert all(it["status"] == "ok" for it in s["iterationsDetail"])


def test_list_runs_persisted(ralph_mod, monkeypatch):
    monkeypatch.setattr(ralph_mod, "execute_with_assignee",
                        lambda *_a, **_k: _stub())
    r = ralph_mod.start("t", max_iterations=2, budget_usd=999)
    _wait_done(ralph_mod, r["runId"])
    runs = ralph_mod.list_runs(limit=10)
    assert len(runs) >= 1
    assert runs[0]["runId"] == r["runId"]
    assert runs[0]["status"] == "max_iter"
