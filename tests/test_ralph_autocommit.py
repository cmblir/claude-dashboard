"""F3 — Ralph auto-commit on done."""
from __future__ import annotations

import importlib
import subprocess
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


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    (r / "a.txt").write_text("initial\n")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=r, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=r, check=True)
    subprocess.run(["git", "add", "."], cwd=r, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=r, check=True)
    return r


def _stub_done(*_, **__):
    return SimpleNamespace(status="ok", output="<promise>DONE</promise>",
                           error="", model="m", provider="p",
                           tokens_total=1, duration_ms=1, cost_usd=0.0,
                           raw={})


def _wait(ralph, rid, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = ralph.status(rid)
        if s and s["status"] != "running":
            return s
        time.sleep(0.05)
    raise AssertionError("ralph never finished")


def test_autocommit_when_dirty(ralph_mod, repo, monkeypatch):
    monkeypatch.setattr(ralph_mod, "execute_with_assignee", _stub_done)
    # Simulate Ralph editing files
    (repo / "a.txt").write_text("modified by ralph\n")
    (repo / "new.txt").write_text("brand new\n")

    r = ralph_mod.start("do work", max_iterations=3, budget_usd=10,
                         cwd=str(repo), auto_commit=True)
    s = _wait(ralph_mod, r["runId"])
    assert s["status"] == "done"

    log = subprocess.run(["git", "log", "--oneline"], cwd=repo,
                         capture_output=True, text=True)
    assert "autocommit" in log.stdout


def test_no_autocommit_when_disabled(ralph_mod, repo, monkeypatch):
    monkeypatch.setattr(ralph_mod, "execute_with_assignee", _stub_done)
    (repo / "a.txt").write_text("ralph edited\n")

    r = ralph_mod.start("do work", max_iterations=3, budget_usd=10,
                         cwd=str(repo), auto_commit=False)
    _wait(ralph_mod, r["runId"])

    # Working tree should still show the modification
    st = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                        capture_output=True, text=True)
    assert "a.txt" in st.stdout


def test_no_autocommit_when_clean(ralph_mod, repo, monkeypatch):
    """Clean tree → skip autocommit cleanly (no error, no empty commit)."""
    monkeypatch.setattr(ralph_mod, "execute_with_assignee", _stub_done)
    before = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=repo,
                            capture_output=True, text=True).stdout.strip()

    r = ralph_mod.start("do work", max_iterations=3, budget_usd=10,
                         cwd=str(repo), auto_commit=True)
    _wait(ralph_mod, r["runId"])

    after = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=repo,
                           capture_output=True, text=True).stdout.strip()
    assert before == after


def test_no_autocommit_when_not_a_repo(ralph_mod, tmp_path, monkeypatch):
    """Non-git cwd → safe no-op."""
    monkeypatch.setattr(ralph_mod, "execute_with_assignee", _stub_done)
    plain = tmp_path / "plain"; plain.mkdir()
    (plain / "x.txt").write_text("hi\n")
    r = ralph_mod.start("do", max_iterations=3, budget_usd=10,
                         cwd=str(plain), auto_commit=True)
    s = _wait(ralph_mod, r["runId"])
    assert s["status"] == "done"   # done despite no commit


def test_autocommit_skipped_on_max_iter(ralph_mod, repo, monkeypatch):
    """max-iter termination must not auto-commit (preserves partial work)."""
    monkeypatch.setattr(ralph_mod, "execute_with_assignee",
                        lambda *a, **k: SimpleNamespace(
                            status="ok", output="still going", error="",
                            model="m", provider="p", tokens_total=1,
                            duration_ms=1, cost_usd=0.0, raw={}))
    (repo / "a.txt").write_text("partial\n")
    before = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=repo,
                            capture_output=True, text=True).stdout.strip()

    r = ralph_mod.start("do", max_iterations=2, budget_usd=10,
                         cwd=str(repo), auto_commit=True)
    s = _wait(ralph_mod, r["runId"])
    assert s["status"] == "max_iter"

    after = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=repo,
                           capture_output=True, text=True).stdout.strip()
    assert before == after
