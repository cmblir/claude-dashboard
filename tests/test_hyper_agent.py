"""Unit tests for server.hyper_agent (v2.52.0 — Auto-Resume advisor + meta).

These tests exercise pure helpers and the LLM-mocked AR advisor path. No
real network calls are issued; ``execute_with_assignee`` is monkey-patched.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from server import hyper_agent as ha


# ───────── _empty_meta / _default_agent_meta ─────────

class TestEmptyMeta:
    def test_shape(self):
        m = ha._empty_meta()
        assert m == {"version": 2, "agents": {}}


class TestDefaultAgentMeta:
    def test_has_required_keys(self):
        d = ha._default_agent_meta()
        for key in (
            "scope", "cwd", "enabled", "objective", "refineTargets",
            "refineProvider", "trigger", "cronSpec", "minSessionsBetween",
            "budgetUSD", "spentUSD", "lastRefinedAt", "totalRefinements",
            "lastError", "history",
        ):
            assert key in d

    def test_defaults_are_sensible(self):
        d = ha._default_agent_meta()
        assert d["enabled"] is False
        assert d["refineTargets"] == ["systemPrompt"]
        assert d["refineProvider"] == "claude:opus"
        assert d["trigger"] == "manual"
        assert d["history"] == []


# ───────── _coerce_agent_meta ─────────

class TestCoerceAgentMeta:
    def test_non_dict_returns_default(self):
        assert ha._coerce_agent_meta(None) == ha._default_agent_meta()
        assert ha._coerce_agent_meta("garbage") == ha._default_agent_meta()
        assert ha._coerce_agent_meta(123) == ha._default_agent_meta()

    def test_clamps_budget(self):
        out = ha._coerce_agent_meta({"budgetUSD": 999_999})
        assert out["budgetUSD"] == 10000.0
        out2 = ha._coerce_agent_meta({"budgetUSD": -50})
        assert out2["budgetUSD"] == 0.0

    def test_invalid_trigger_falls_back_to_manual(self):
        out = ha._coerce_agent_meta({"trigger": "made_up"})
        assert out["trigger"] == "manual"

    def test_drops_unknown_refine_targets(self):
        out = ha._coerce_agent_meta({"refineTargets": ["junk", "tools"]})
        assert out["refineTargets"] == ["tools"]

    def test_invalid_scope_normalises_to_global(self):
        out = ha._coerce_agent_meta({"scope": "weird"})
        assert out["scope"] == "global"


# ───────── _cwd_hash / _agent_key ─────────

class TestCwdHash:
    def test_eight_chars(self):
        assert len(ha._cwd_hash("/tmp/example")) == 8

    def test_deterministic(self):
        a = ha._cwd_hash("/tmp/example")
        b = ha._cwd_hash("/tmp/example")
        assert a == b

    def test_different_inputs_differ(self):
        assert ha._cwd_hash("/a") != ha._cwd_hash("/b")


class TestAgentKey:
    def test_global_format(self):
        assert ha._agent_key("foo", None) == "global:foo"

    def test_project_format(self):
        k = ha._agent_key("foo", "/some/dir")
        assert k.startswith("project:")
        parts = k.split(":")
        assert len(parts) == 3
        assert parts[0] == "project"
        assert len(parts[1]) == 8
        assert parts[2] == "foo"


# ───────── hyper_advise_auto_resume ─────────

def _fake_resp(payload: dict, *, status: str = "ok",
               provider: str = "claude", model: str = "haiku",
               cost: float = 0.001, tokens: int = 50):
    """Return a SimpleNamespace mimicking ai_providers.ProviderResult."""
    return SimpleNamespace(
        status=status,
        output=json.dumps(payload),
        provider=provider,
        model=model,
        cost_usd=cost,
        tokens_total=tokens,
        error="",
    )


@pytest.fixture
def patched_provider(monkeypatch):
    """Replace execute_with_assignee with a programmable stub."""
    holder = {"resp": _fake_resp({
        "pollIntervalSec": 600, "maxAttempts": 12,
        "promptHint": "", "rationale": "ok",
    })}

    def fake_execute(assignee, prompt, *, system_prompt="", timeout=180, **kw):
        return holder["resp"]

    from server import ai_providers as ai_mod
    monkeypatch.setattr(ai_mod, "execute_with_assignee", fake_execute)
    return {"holder": holder}


class TestAdviseAutoResumePreflight:
    def test_rejects_non_dict_entry(self):
        out = ha.hyper_advise_auto_resume("not-a-dict", [{"x": 1}, {"y": 2}])
        assert out["ok"] is False

    def test_rejects_done_state(self):
        entry = {"state": "done", "sessionId": "s1"}
        out = ha.hyper_advise_auto_resume(entry, [{"a": 1}, {"a": 2}])
        assert out["ok"] is False
        assert out["error"] == "Session not actively retrying"

    def test_rejects_stopped_state(self):
        entry = {"state": "stopped", "sessionId": "s1"}
        out = ha.hyper_advise_auto_resume(entry, [{"a": 1}, {"a": 2}])
        assert out["ok"] is False
        assert "actively" in out["error"]

    def test_rejects_empty_failure_history(self):
        entry = {"state": "retrying", "sessionId": "s1"}
        out = ha.hyper_advise_auto_resume(entry, [])
        assert out["ok"] is False
        assert "Not enough failure history" in out["error"]

    def test_rejects_single_failure(self):
        entry = {"state": "retrying", "sessionId": "s1"}
        out = ha.hyper_advise_auto_resume(entry, [{"attempt": 1}])
        assert out["ok"] is False
        assert "Not enough failure history" in out["error"]


class TestAdviseAutoResumeClamping:
    def _entry(self):
        return {
            "state": "retrying",
            "sessionId": "abc123",
            "pollInterval": 300,
            "maxAttempts": 12,
            "attempts": 3,
            "lastExitReason": "rate_limit",
            "lastError": "",
        }

    def _failures(self):
        return [
            {"attempt": 1, "exitReason": "rate_limit"},
            {"attempt": 2, "exitReason": "rate_limit"},
        ]

    def test_clamps_high_poll_interval(self, patched_provider):
        patched_provider["holder"]["resp"] = _fake_resp({
            "pollIntervalSec": 99999, "maxAttempts": 12,
            "promptHint": "", "rationale": "x",
        })
        out = ha.hyper_advise_auto_resume(self._entry(), self._failures())
        assert out["ok"] is True
        assert out["advice"]["pollIntervalSec"] == 1800

    def test_clamps_low_poll_interval(self, patched_provider):
        patched_provider["holder"]["resp"] = _fake_resp({
            "pollIntervalSec": 1, "maxAttempts": 12,
            "promptHint": "", "rationale": "x",
        })
        out = ha.hyper_advise_auto_resume(self._entry(), self._failures())
        # poll<=0 falls back to entry.pollInterval (300), already in range.
        # poll=1 stays as 1, then clamped to 60.
        assert out["advice"]["pollIntervalSec"] == 60

    def test_clamps_high_max_attempts(self, patched_provider):
        patched_provider["holder"]["resp"] = _fake_resp({
            "pollIntervalSec": 600, "maxAttempts": 9999,
            "promptHint": "", "rationale": "x",
        })
        out = ha.hyper_advise_auto_resume(self._entry(), self._failures())
        assert out["advice"]["maxAttempts"] == 50

    def test_zero_max_attempts_falls_back_to_entry(self, patched_provider):
        patched_provider["holder"]["resp"] = _fake_resp({
            "pollIntervalSec": 600, "maxAttempts": 0,
            "promptHint": "", "rationale": "x",
        })
        out = ha.hyper_advise_auto_resume(self._entry(), self._failures())
        assert out["advice"]["maxAttempts"] == 12  # entry default

    def test_truncates_long_prompt_hint(self, patched_provider):
        long_hint = "x" * 5000
        patched_provider["holder"]["resp"] = _fake_resp({
            "pollIntervalSec": 600, "maxAttempts": 12,
            "promptHint": long_hint, "rationale": "x",
        })
        out = ha.hyper_advise_auto_resume(self._entry(), self._failures())
        assert len(out["advice"]["promptHint"]) <= 500

    def test_unparseable_response_returns_error(self, patched_provider):
        patched_provider["holder"]["resp"] = SimpleNamespace(
            status="ok", output="not json at all",
            provider="claude", model="haiku",
            cost_usd=0.0, tokens_total=0, error="",
        )
        out = ha.hyper_advise_auto_resume(self._entry(), self._failures())
        assert out["ok"] is False
        assert "JSON" in out["error"]
