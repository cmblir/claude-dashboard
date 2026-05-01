"""I1 — Ralph polish system prompt configurability."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def mod(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_DASHBOARD_RALPH_POLISH",
                       str(tmp_path / "polish.md"))
    monkeypatch.delenv("RALPH_POLISH_SYSTEM", raising=False)
    from server import config as _c; importlib.reload(_c)
    from server import ralph_recommend; importlib.reload(ralph_recommend)
    return ralph_recommend


def test_default_when_no_override(mod):
    assert mod._polish_system_prompt() == mod._DEFAULT_POLISH_SYSTEM


def test_env_overrides_file(mod, monkeypatch, tmp_path):
    cfg = tmp_path / "polish.md"
    cfg.write_text("from-file", encoding="utf-8")
    monkeypatch.setenv("RALPH_POLISH_SYSTEM", "from-env")
    assert mod._polish_system_prompt() == "from-env"


def test_file_overrides_default(mod, tmp_path):
    cfg = tmp_path / "polish.md"
    cfg.write_text("from-file", encoding="utf-8")
    assert mod._polish_system_prompt() == "from-file"


def test_api_get_reports_source(mod, tmp_path):
    cfg = tmp_path / "polish.md"
    cfg.write_text("custom", encoding="utf-8")
    r = mod.api_ralph_polish_get({})
    assert r["ok"] and r["source"] == "file"
    assert r["current"] == "custom"


def test_api_set_writes_file(mod, tmp_path):
    r = mod.api_ralph_polish_set({"text": "new prompt"})
    assert r["ok"]
    cfg = tmp_path / "polish.md"
    assert cfg.read_text() == "new prompt"


def test_api_set_clear_removes_file(mod, tmp_path):
    cfg = tmp_path / "polish.md"
    cfg.write_text("temp", encoding="utf-8")
    r = mod.api_ralph_polish_set({"clear": True})
    assert r["ok"]
    assert not cfg.exists()


def test_api_set_rejects_empty(mod):
    assert mod.api_ralph_polish_set({"text": "  "})["ok"] is False
    assert mod.api_ralph_polish_set({})["ok"] is False


def test_api_set_rejects_too_long(mod):
    big = "x" * 17000
    assert mod.api_ralph_polish_set({"text": big})["ok"] is False
