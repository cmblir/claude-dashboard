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
