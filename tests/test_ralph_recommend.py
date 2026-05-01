"""Project Ralph recommender — synthesises PROMPT.md drafts."""
from __future__ import annotations

import subprocess

import pytest


@pytest.fixture
def project(tmp_path):
    """Set up a tiny git repo with CLAUDE.md + a TODO + a dirty file."""
    root = tmp_path / "demo"
    root.mkdir()
    (root / "CLAUDE.md").write_text(
        "# demo — a project for testing\n\nDoes the demo thing.\n",
        encoding="utf-8",
    )
    (root / "main.py").write_text(
        "# TODO: implement the main feature\nprint('hi')\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
    # Make one file dirty (uncommitted change)
    (root / "extra.txt").write_text("wip\n")
    return root


def test_recommend_returns_structured_draft(project):
    from server import ralph_recommend
    rec = ralph_recommend.recommend(str(project))
    assert rec is not None
    assert "demo" in rec.promptMd
    assert rec.completion == "<promise>DONE</promise>"
    assert "Rules" in rec.promptMd
    # Sources reflect what we set up
    src = rec.sources
    assert src["hasClaudeMd"] is True
    assert src["dirtyFiles"] >= 1
    assert src["todoCount"] >= 1


def test_recommend_picks_dirty_first(project):
    from server import ralph_recommend
    rec = ralph_recommend.recommend(str(project))
    assert "uncommitted" in rec.promptMd.lower()


def test_recommend_uses_tagline(project):
    from server import ralph_recommend
    rec = ralph_recommend.recommend(str(project))
    # tagline parser strips "name — " prefix
    assert "a project for testing" in rec.promptMd


def test_recommend_missing_project(tmp_path):
    from server import ralph_recommend
    assert ralph_recommend.recommend(str(tmp_path / "nope")) is None


def test_api_recommend_shape(project):
    from server import ralph_recommend
    r = ralph_recommend.api_ralph_recommend({"project": str(project)})
    assert r["ok"]
    assert "promptMd" in r["recommendation"]
    assert r["recommendation"]["completion"] == "<promise>DONE</promise>"


def test_api_recommend_bad_input():
    from server import ralph_recommend
    assert ralph_recommend.api_ralph_recommend({})["ok"] is False
    assert ralph_recommend.api_ralph_recommend("nope")["ok"] is False
