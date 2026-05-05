"""Y1 — provider error message preservation across the fallback chain."""
from __future__ import annotations

import importlib
from dataclasses import dataclass

import pytest


@pytest.fixture
def reg(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from server import ai_providers
    importlib.reload(ai_providers)
    return ai_providers


def _stub_provider(reg_mod, pid: str, *, available: bool, error_msg: str = "rate-limited"):
    """Insert a stub provider with controllable behaviour."""
    base = reg_mod.BaseProvider

    @dataclass
    class StubProvider(base):
        provider_id: str = pid
        provider_name: str = pid
        provider_type: str = "api"
        icon: str = "?"

        def __init__(self):
            super().__init__()

        def is_available(self):
            return available

        def list_models(self):
            return []

        def execute(self, prompt, **kw):
            return reg_mod.AIResponse(
                status="err", error=error_msg,
                provider=pid, duration_ms=1,
            )

    return StubProvider()


def test_unavailable_provider_message(reg):
    """provider not available → message points the user at the AI Providers tab.

    fallback=False so the assertion is about THIS provider's error
    shape, not "did the chain happen to find a working provider on
    this machine." The default chain includes claude-cli / ollama,
    which may be installed locally; that path is covered by the
    integration tests downstream.
    """
    r = reg.get_registry().execute(
        provider_id="openai-api", model="gpt-4.1-mini", prompt="hi",
        fallback=False,
    )
    assert r.status == "err"
    assert "available" in r.error.lower() or "not installed" in r.error.lower()
    # The new message includes a hint about the AI Providers tab.
    assert "ai providers tab" in r.error.lower() or "key" in r.error.lower()


def test_unregistered_provider_message(reg):
    # fallback=False — same rationale as test_unavailable_provider_message.
    r = reg.get_registry().execute(
        provider_id="totally-fake-provider", model="x", prompt="hi",
        fallback=False,
    )
    assert r.status == "err"
    assert "not registered" in r.error.lower()


def test_primary_error_surfaces_when_all_fail(reg, monkeypatch):
    """When primary returns err and chain exhausted, primary's actual error
    must be in the final message — not a generic 'all providers failed'."""
    primary = _stub_provider(reg, "p-1", available=True,
                              error_msg="quota exceeded for opus")
    fallback = _stub_provider(reg, "p-2", available=True,
                               error_msg="API key invalid")

    registry = reg.get_registry()
    registry._providers["p-1"] = primary
    registry._providers["p-2"] = fallback
    registry.set_fallback_chain(["p-2"])

    r = registry.execute(provider_id="p-1", model="m", prompt="hi")
    assert r.status == "err"
    # Primary error visible
    assert "quota exceeded" in r.error.lower()
    # Chain step visible too
    assert "api key invalid" in r.error.lower() or "p-2" in r.error.lower()


def test_no_fallback_returns_primary_response(reg):
    """fallback=False short-circuits — primary's response is returned as-is."""
    primary = _stub_provider(reg, "p-1", available=True,
                              error_msg="claude rate limit")
    registry = reg.get_registry()
    registry._providers["p-1"] = primary
    r = registry.execute(provider_id="p-1", model="m", prompt="hi",
                          fallback=False)
    assert r.status == "err"
    assert r.error == "claude rate limit"
