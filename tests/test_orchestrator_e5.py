"""E5 — per-agent isolated workspace."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def orch(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_DASHBOARD_ORCHESTRATOR",
                       str(tmp_path / "orch.json"))
    monkeypatch.setenv("CLAUDE_DASHBOARD_DB", str(tmp_path / "bus.db"))
    monkeypatch.setenv("ORCH_AGENT_WORKSPACE_ROOT",
                       str(tmp_path / "agents"))
    from server import config as _c; importlib.reload(_c)
    from server import db as _db; importlib.reload(_db)
    from server import agent_bus; importlib.reload(agent_bus)
    from server import orchestrator; importlib.reload(orchestrator)
    return orchestrator


def test_workspace_creates_directory(orch, tmp_path):
    binding = {"kind": "slack", "channel": "C123", "label": "demo"}
    ws = orch._ensure_workspace(binding)
    assert ws["cwd"]
    p = (tmp_path / "agents" / orch._binding_id(binding))
    assert p.is_dir()
    assert (p / "CLAUDE.md").is_file()
    assert (p / "memory").is_dir()


def test_workspace_idempotent(orch):
    binding = {"kind": "telegram", "chat": "-100"}
    a = orch._ensure_workspace(binding)
    b = orch._ensure_workspace(binding)
    assert a == b


def test_workspace_isolated_per_binding(orch):
    a = orch._ensure_workspace({"kind": "slack", "channel": "A"})
    b = orch._ensure_workspace({"kind": "slack", "channel": "B"})
    assert a["cwd"] != b["cwd"]


def test_workspace_returns_empty_for_no_binding(orch):
    assert orch._ensure_workspace(None) == {}


def test_binding_id_is_directory_safe(orch):
    bid = orch._binding_id({"kind": "slack", "channel": "../etc/passwd"})
    assert ".." not in bid
    assert "/" not in bid
