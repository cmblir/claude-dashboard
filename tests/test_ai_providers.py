"""Unit tests for server.ai_providers registry + parallel dispatcher.

Network-touching providers are never invoked here — every assertion uses
either the singleton accessor, a synthetic empty/invalid input, or
attribute introspection. No outbound HTTP calls.
"""
from __future__ import annotations

import pytest

from server import ai_providers as ap
from server.ai_providers import (
    AIResponse,
    OllamaApiProvider,
    ProviderRegistry,
    get_registry,
)


# ───────── singleton ─────────

class TestRegistrySingleton:
    def test_get_registry_is_singleton(self):
        a = get_registry()
        b = get_registry()
        assert a is b
        assert isinstance(a, ProviderRegistry)

    def test_builtin_providers_registered(self):
        reg = get_registry()
        ids = {p.provider_id for p in reg.all_providers()}
        # Each of these is registered unconditionally in get_registry().
        for expected in ("claude-cli", "openai-api", "gemini-api", "ollama-api"):
            assert expected in ids, f"missing provider: {expected}"


# ───────── execute_parallel ─────────

class TestExecuteParallel:
    def test_empty_list_returns_err(self):
        reg = get_registry()
        resp = reg.execute_parallel([], "hi")
        assert isinstance(resp, AIResponse)
        assert resp.status == "err"
        assert "no assignees" in resp.error.lower()

    def test_whitespace_only_assignees_returns_err(self):
        reg = get_registry()
        resp = reg.execute_parallel(["   ", ""], "hi")
        assert resp.status == "err"
        assert "no assignees" in resp.error.lower()

    def test_invalid_assignee_does_not_raise(self):
        # An unknown provider routes to claude-cli with a bogus model;
        # whether it errors or fallbacks, it must come back as an
        # AIResponse — never raise.
        reg = get_registry()
        resp = reg.execute_parallel(
            ["claude:__definitely_not_a_real_model__"],
            "hi",
            timeout=1,
            fallback=False,
        )
        assert isinstance(resp, AIResponse)
        # Status may be ok or err depending on local CLI install, but
        # it must be one of the two — execute_parallel never raises.
        assert resp.status in ("ok", "err")


# ───────── OllamaApiProvider cache shape ─────────

class TestOllamaApiCache:
    def test_cache_attributes_initialized(self):
        p = OllamaApiProvider(base_url="http://localhost:11434")
        assert hasattr(p, "_models_cache_at")
        assert hasattr(p, "_models_cache")
        assert p._models_cache_at == 0.0
        assert p._models_cache == []

    def test_returns_cached_when_within_ttl(self, monkeypatch):
        p = OllamaApiProvider(base_url="http://127.0.0.1:11434")
        # Pretend we already populated the cache 1 second ago.
        sentinel = [object()]  # any non-empty list short-circuits the fetch
        p._models_cache = sentinel  # type: ignore[assignment]
        import time as _t
        p._models_cache_at = _t.time()

        # urlopen must NOT be called when the cache is warm.
        def _boom(*a, **kw):  # pragma: no cover - assertion target
            raise AssertionError("urlopen called even though cache is warm")
        monkeypatch.setattr("urllib.request.urlopen", _boom)
        out = p.list_models()
        assert out is sentinel  # exact same object — no rebuild


# ───────── AIResponse dataclass shape ─────────

class TestAIResponseShape:
    def test_default_status_ok(self):
        r = AIResponse()
        assert r.status == "ok"
        assert r.output == ""
        assert r.tokens_in == 0

    def test_to_dict_round_trip(self):
        r = AIResponse(status="err", error="boom", provider="x")
        d = r.to_dict()
        assert d["status"] == "err"
        assert d["error"] == "boom"
        assert d["provider"] == "x"


# ───────── resolve_assignee (deterministic, no I/O) ─────────

class TestResolveAssignee:
    def test_provider_model_split(self):
        reg = get_registry()
        pid, model = reg.resolve_assignee("openai:gpt-4.1")
        assert pid == "openai-api"
        assert model == "gpt-4.1"

    def test_empty_assignee_defaults_to_claude(self):
        reg = get_registry()
        pid, _ = reg.resolve_assignee("")
        assert pid == "claude-cli"
