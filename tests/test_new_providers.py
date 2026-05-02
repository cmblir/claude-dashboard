"""W2 — new OpenAI-compatible providers (Groq, DeepSeek, Mistral, xAI)."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def reg(monkeypatch):
    # Drop any leftover env vars so is_available() returns False without
    # contaminating tests that explicitly set them.
    for var in ["GROQ_API_KEY", "DEEPSEEK_API_KEY", "MISTRAL_API_KEY",
                "XAI_API_KEY"]:
        monkeypatch.delenv(var, raising=False)
    from server import ai_providers
    importlib.reload(ai_providers)
    return ai_providers.get_registry()


def test_all_new_providers_registered(reg):
    ids = {p.provider_id for p in reg.all_providers()}
    assert "groq-api" in ids
    assert "deepseek-api" in ids
    assert "mistral-api" in ids
    assert "xai-api" in ids


@pytest.mark.parametrize("pid,env_var", [
    ("groq-api", "GROQ_API_KEY"),
    ("deepseek-api", "DEEPSEEK_API_KEY"),
    ("mistral-api", "MISTRAL_API_KEY"),
    ("xai-api", "XAI_API_KEY"),
])
def test_unavailable_without_key(reg, pid, env_var, monkeypatch):
    monkeypatch.delenv(env_var, raising=False)
    p = reg.get(pid)
    assert p is not None
    assert p.is_available() is False


@pytest.mark.parametrize("pid,env_var", [
    ("groq-api", "GROQ_API_KEY"),
    ("deepseek-api", "DEEPSEEK_API_KEY"),
    ("mistral-api", "MISTRAL_API_KEY"),
    ("xai-api", "XAI_API_KEY"),
])
def test_available_when_key_set(monkeypatch, pid, env_var):
    monkeypatch.setenv(env_var, "fake-test-key")
    from server import ai_providers
    importlib.reload(ai_providers)
    p = ai_providers.get_registry().get(pid)
    assert p.is_available() is True


def test_models_have_pricing_metadata(reg):
    for pid in ["groq-api", "deepseek-api", "mistral-api", "xai-api"]:
        p = reg.get(pid)
        models = p.list_models()
        assert models, f"{pid} should have at least one model"
        for m in models:
            assert m.id, f"{pid} model missing id"
            assert m.context_window > 0, f"{pid} model {m.id} missing context"
            assert m.price_in >= 0


def test_alias_resolution(reg):
    # The PROVIDER_ALIASES table should map short names to the new ids.
    for short, expected in [("groq", "groq-api"),
                             ("deepseek", "deepseek-api"),
                             ("mistral", "mistral-api"),
                             ("xai", "xai-api"),
                             ("grok", "xai-api"),
                             ("codestral", "mistral-api")]:
        pid, _ = reg.resolve_assignee(f"{short}:any-model")
        assert pid == expected, f"{short}: -> {pid} (expected {expected})"


def test_codex_models_include_gpt5(reg):
    """Codex now advertises gpt-5-codex / o3-pro plus existing o4-mini etc."""
    p = reg.get("codex")
    ids = [m.id for m in p.list_models()]
    assert "gpt-5-codex" in ids
    assert "o3-pro" in ids
    assert "o4-mini" in ids


def test_execute_returns_err_without_key(reg):
    p = reg.get("groq-api")
    r = p.execute("hello")
    assert r.status == "err"
    assert "GROQ_API_KEY" in r.error
