"""Unit tests for server.cost_timeline aggregation + recommendation rules."""
from __future__ import annotations

import time

import pytest

from server import cost_timeline as ct


def _entry(ts: int, model: str, usd: float, ti: int = 100, to: int = 50,
           src: str = "promptCache") -> dict:
    """Synthetic timeline entry — shape matches cost_timeline._coerce_entry output."""
    return {
        "ts": ts,
        "source": src,
        "model": model,
        "tokensIn": ti,
        "tokensOut": to,
        "usd": usd,
        "status": "ok",
    }


@pytest.fixture
def now_ts():
    return int(time.time())


# ───────── _infer_provider ─────────

class TestInferProvider:
    def test_claude_models(self):
        assert ct._infer_provider("claude-3-sonnet") == "claude"
        assert ct._infer_provider("claude-sonnet-4-6") == "claude"
        assert ct._infer_provider("claude-opus-4-7") == "claude"

    def test_openai_models(self):
        assert ct._infer_provider("gpt-5") == "openai"
        assert ct._infer_provider("gpt-4.1") == "openai"

    def test_gemini_models(self):
        assert ct._infer_provider("gemini-2.5-pro") == "gemini"

    def test_ollama_models(self):
        assert ct._infer_provider("llama3.1") == "ollama"
        assert ct._infer_provider("mistral-7b") == "ollama"
        assert ct._infer_provider("qwen2") == "ollama"

    def test_unknown_returns_empty(self):
        assert ct._infer_provider("") == ""
        assert ct._infer_provider("custom-foo") == ""


# ───────── _aggregate_by_model ─────────

class TestAggregateByModel:
    def test_sums_tokens_and_cost(self, now_ts):
        entries = [
            _entry(now_ts - 10, "claude-sonnet-4-6", 0.5, ti=100, to=50),
            _entry(now_ts - 20, "claude-sonnet-4-6", 1.5, ti=200, to=80),
        ]
        agg = ct._aggregate_by_model(entries, window_days=30)
        key = ("claude", "claude-sonnet-4-6")
        assert key in agg
        b = agg[key]
        assert b["call_count"] == 2
        assert b["total_cost"] == pytest.approx(2.0)
        assert b["tokens_in_sum"] == 300
        assert b["tokens_out_sum"] == 130
        assert b["avg_cost_per_call"] == pytest.approx(1.0)
        assert b["avg_tokens_in"] == 150

    def test_window_excludes_old_entries(self, now_ts):
        old = now_ts - 86400 * 60  # 60 days ago
        entries = [
            _entry(old, "claude-sonnet-4-6", 99.0),
            _entry(now_ts - 10, "claude-sonnet-4-6", 1.0),
        ]
        agg = ct._aggregate_by_model(entries, window_days=30)
        b = agg[("claude", "claude-sonnet-4-6")]
        assert b["call_count"] == 1
        assert b["total_cost"] == pytest.approx(1.0)

    def test_skips_entries_with_no_model(self, now_ts):
        entries = [_entry(now_ts - 10, "", 1.0)]
        agg = ct._aggregate_by_model(entries, window_days=30)
        assert agg == {}


# ───────── _recommendations rule logic ─────────

def _patch_entries(monkeypatch, entries: list[dict]) -> None:
    monkeypatch.setattr(ct, "_gather_all", lambda: entries)


class TestRecommendationsR1Haiku:
    def test_fires_on_short_prompt_premium_model(self, monkeypatch, now_ts):
        entries = [_entry(now_ts - i, "claude-sonnet-4-6", 0.1, ti=200, to=50)
                   for i in range(12)]
        _patch_entries(monkeypatch, entries)
        out = ct._recommendations(window_days=30)
        rule_ids = [r["ruleId"] for r in out["recommendations"]]
        assert "haiku_for_short_prompts" in rule_ids

    def test_does_not_fire_on_low_volume(self, monkeypatch, now_ts):
        entries = [_entry(now_ts - i, "claude-sonnet-4-6", 0.1, ti=200) for i in range(4)]
        _patch_entries(monkeypatch, entries)
        out = ct._recommendations(window_days=30)
        assert "haiku_for_short_prompts" not in [r["ruleId"] for r in out["recommendations"]]

    def test_does_not_fire_for_haiku_already(self, monkeypatch, now_ts):
        entries = [_entry(now_ts - i, "claude-haiku-4-5", 0.01, ti=200) for i in range(20)]
        _patch_entries(monkeypatch, entries)
        out = ct._recommendations(window_days=30)
        assert "haiku_for_short_prompts" not in [r["ruleId"] for r in out["recommendations"]]


class TestRecommendationsR2Caching:
    def test_fires_on_long_prompts(self, monkeypatch, now_ts):
        entries = [_entry(now_ts - i, "claude-sonnet-4-6", 0.5, ti=8000, to=200)
                   for i in range(6)]
        _patch_entries(monkeypatch, entries)
        out = ct._recommendations(window_days=30)
        assert "enable_prompt_caching" in [r["ruleId"] for r in out["recommendations"]]


class TestRecommendationsR3Local:
    def test_fires_on_high_volume_high_cost(self, monkeypatch, now_ts):
        entries = [_entry(now_ts - i, "claude-sonnet-4-6", 0.02, ti=300, to=100)
                   for i in range(120)]
        _patch_entries(monkeypatch, entries)
        out = ct._recommendations(window_days=30)
        assert "local_model_for_batch" in [r["ruleId"] for r in out["recommendations"]]

    def test_does_not_fire_for_ollama_already(self, monkeypatch, now_ts):
        entries = [_entry(now_ts - i, "llama3.1", 0.02, ti=300) for i in range(120)]
        _patch_entries(monkeypatch, entries)
        out = ct._recommendations(window_days=30)
        assert "local_model_for_batch" not in [r["ruleId"] for r in out["recommendations"]]


class TestRecommendationsR4Stale:
    def test_fires_on_stale_model(self, monkeypatch, now_ts):
        entries = [_entry(now_ts - i, "claude-3-sonnet", 0.05, ti=300) for i in range(6)]
        _patch_entries(monkeypatch, entries)
        out = ct._recommendations(window_days=30)
        recs = [r for r in out["recommendations"] if r["ruleId"] == "stale_model_upgrade"]
        assert recs, "stale upgrade rec missing"
        assert recs[0]["suggestedModel"] == "claude-sonnet-4-6"

    def test_no_stale_rec_for_current_model(self, monkeypatch, now_ts):
        entries = [_entry(now_ts - i, "claude-sonnet-4-6", 0.05) for i in range(6)]
        _patch_entries(monkeypatch, entries)
        out = ct._recommendations(window_days=30)
        assert "stale_model_upgrade" not in [r["ruleId"] for r in out["recommendations"]]


class TestApiCostRecommendations:
    def test_shape(self, monkeypatch, now_ts):
        _patch_entries(monkeypatch, [_entry(now_ts - 10, "claude-sonnet-4-6", 0.1)])
        out = ct.api_cost_recommendations({})
        assert out["ok"] is True
        for key in ("ok", "windowDays", "computedAt", "recommendations",
                    "totalCost30d", "estimatedSavingsTotal"):
            assert key in out
        assert isinstance(out["recommendations"], list)

    def test_empty_input(self, monkeypatch):
        _patch_entries(monkeypatch, [])
        out = ct.api_cost_recommendations({})
        assert out["ok"] is True
        assert out["recommendations"] == []
        assert out["totalCost30d"] == 0
        assert out["estimatedSavingsTotal"] == 0

    def test_window_clamped(self, monkeypatch):
        _patch_entries(monkeypatch, [])
        assert ct.api_cost_recommendations({"window": 9999})["windowDays"] == 365
        # `window=0` is falsy in api_cost_recommendations → falls back to 30.
        assert ct.api_cost_recommendations({"window": -5})["windowDays"] == 1

    def test_invalid_window_defaults_to_30(self, monkeypatch):
        _patch_entries(monkeypatch, [])
        assert ct.api_cost_recommendations({"window": "not-a-number"})["windowDays"] == 30
