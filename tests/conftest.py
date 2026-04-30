"""Shared pytest fixtures for the auto_resume test suite."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the project root importable so `import server.auto_resume` works
# regardless of the cwd from which pytest is invoked.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Redirect $HOME to a tmp path so on-disk state never escapes the test."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def fixed_now():
    """Stable UNIX timestamp (2026-04-30T12:00:00Z) for time-dependent tests."""
    return 1777982400.0
