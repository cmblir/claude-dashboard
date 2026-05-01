"""E3 — LLM polish pass on the mechanical recommender output."""
from __future__ import annotations

import importlib
import subprocess
from types import SimpleNamespace

import pytest


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    (root / "CLAUDE.md").write_text("# demo — small project\n", encoding="utf-8")
    (root / "main.py").write_text("# TODO: real implementation\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True)
    return root


@pytest.fixture
def rec_mod():
    from server import ralph_recommend
    importlib.reload(ralph_recommend)
    return ralph_recommend


def test_polish_returns_polished_text(rec_mod, project, monkeypatch):
    seen: list[str] = []

    def fake_exec(assignee, prompt, **kw):
        seen.append(assignee)
        return SimpleNamespace(
            status="ok",
            output="# Polished\n\n(LLM cleaned this up)\n<promise>DONE</promise>",
            error="", model="m", provider="p", tokens_total=1,
            duration_ms=1, cost_usd=0.0, raw={},
        )

    monkeypatch.setattr(rec_mod, "execute_with_assignee", fake_exec)
    rec = rec_mod.recommend(str(project))
    polished = rec_mod.polish(rec, assignee="claude:sonnet")
    assert polished.sources.get("polished") is True
    assert "Polished" in polished.promptMd
    assert seen == ["claude:sonnet"]


def test_polish_keeps_completion_marker(rec_mod, project, monkeypatch):
    """If the LLM's output drops the completion marker, polish() re-appends it."""
    monkeypatch.setattr(rec_mod, "execute_with_assignee",
        lambda a, p, **k: SimpleNamespace(
            status="ok",
            output="# Polished without marker\n\nNo promise here",
            error="", model="m", provider="p", tokens_total=1,
            duration_ms=1, cost_usd=0.0, raw={},
        ))
    rec = rec_mod.recommend(str(project))
    polished = rec_mod.polish(rec)
    assert "<promise>DONE</promise>" in polished.promptMd


def test_polish_falls_back_on_error(rec_mod, project, monkeypatch):
    monkeypatch.setattr(rec_mod, "execute_with_assignee",
                        lambda *a, **k: SimpleNamespace(
                            status="err", output="", error="boom",
                            model="", provider="", tokens_total=0,
                            duration_ms=0, cost_usd=0.0, raw={}))
    rec = rec_mod.recommend(str(project))
    polished = rec_mod.polish(rec)
    # On error, returns the original (no "polished" flag, original promptMd)
    assert polished.promptMd == rec.promptMd
    assert polished.sources.get("polished") is not True


def test_api_polish_flag_routes_through(rec_mod, project, monkeypatch):
    seen: dict = {"called": False}

    def fake_polish(rec, assignee=""):
        seen["called"] = True
        return rec

    monkeypatch.setattr(rec_mod, "polish", fake_polish)
    rec_mod.api_ralph_recommend({"project": str(project), "polish": True})
    assert seen["called"]


def test_api_no_polish_by_default(rec_mod, project, monkeypatch):
    seen: dict = {"called": False}
    monkeypatch.setattr(rec_mod, "polish",
                        lambda r, **k: (seen.update(called=True) or r))
    rec_mod.api_ralph_recommend({"project": str(project)})
    assert seen["called"] is False


# ───── api_ralph_polish_get / api_ralph_polish_set ─────

def test_polish_prompt_get_default(rec_mod, monkeypatch):
    monkeypatch.delenv("RALPH_POLISH_SYSTEM", raising=False)
    result = rec_mod.api_ralph_polish_get()
    assert result["ok"] is True
    assert result["source"] == "default"
    assert result["current"] == rec_mod._DEFAULT_POLISH_SYSTEM
    assert result["default"] == rec_mod._DEFAULT_POLISH_SYSTEM


def test_polish_prompt_get_from_env(rec_mod, monkeypatch):
    monkeypatch.setenv("RALPH_POLISH_SYSTEM", "custom env prompt")
    result = rec_mod.api_ralph_polish_get()
    assert result["ok"] is True
    assert result["source"] == "env"
    assert result["current"] == "custom env prompt"


def test_polish_prompt_set_and_get(rec_mod, tmp_path, monkeypatch):
    monkeypatch.delenv("RALPH_POLISH_SYSTEM", raising=False)
    cfg_file = tmp_path / "polish.md"
    monkeypatch.setenv("CLAUDE_DASHBOARD_RALPH_POLISH", str(cfg_file))

    set_result = rec_mod.api_ralph_polish_set({"text": "my custom system prompt"})
    assert set_result["ok"] is True
    assert cfg_file.exists()
    assert cfg_file.read_text() == "my custom system prompt"

    get_result = rec_mod.api_ralph_polish_get()
    assert get_result["source"] == "file"
    assert get_result["current"] == "my custom system prompt"


def test_polish_prompt_set_clear(rec_mod, tmp_path, monkeypatch):
    monkeypatch.delenv("RALPH_POLISH_SYSTEM", raising=False)
    cfg_file = tmp_path / "polish.md"
    cfg_file.write_text("old prompt")
    monkeypatch.setenv("CLAUDE_DASHBOARD_RALPH_POLISH", str(cfg_file))

    clear_result = rec_mod.api_ralph_polish_set({"clear": True})
    assert clear_result["ok"] is True
    assert clear_result.get("cleared") is True
    assert not cfg_file.exists()


def test_polish_prompt_set_bad_body(rec_mod):
    result = rec_mod.api_ralph_polish_set("not a dict")
    assert result["ok"] is False


def test_polish_prompt_set_empty_text(rec_mod):
    result = rec_mod.api_ralph_polish_set({"text": ""})
    assert result["ok"] is False


def test_polish_prompt_set_too_long(rec_mod):
    result = rec_mod.api_ralph_polish_set({"text": "x" * 16001})
    assert result["ok"] is False
