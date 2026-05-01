"""F1 — Inbound/Outbound SQLite IPC tables."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def orch(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_DASHBOARD_ORCHESTRATOR",
                       str(tmp_path / "orch.json"))
    monkeypatch.setenv("CLAUDE_DASHBOARD_DB", str(tmp_path / "bus.db"))
    from server import config as _c; importlib.reload(_c)
    from server import db as _db; importlib.reload(_db)
    from server import agent_bus; importlib.reload(agent_bus)
    from server import orchestrator; importlib.reload(orchestrator)
    return orchestrator


def test_inbound_persists_and_lists(orch):
    orch._persist_inbound("r1", kind="slack", channel="C1", user="alice",
                           text="hello")
    orch._persist_inbound("r2", kind="slack", channel="C1", user="bob",
                           text="hi")
    rows = orch.list_inbound(channel="C1")
    assert len(rows) == 2
    assert rows[0]["text"] == "hi"        # newest first
    assert rows[1]["user"] == "alice"


def test_inbound_channel_filter(orch):
    orch._persist_inbound("r1", kind="slack", channel="A", user="u", text="x")
    orch._persist_inbound("r2", kind="slack", channel="B", user="u", text="y")
    a = orch.list_inbound(channel="A")
    assert len(a) == 1 and a[0]["text"] == "x"


def test_outbound_run_filter(orch):
    orch._persist_outbound("r1", kind="slack", channel="C1", via="ad-hoc",
                            ok=True, text="reply 1")
    orch._persist_outbound("r1", kind="slack", channel="C1", via="ad-hoc",
                            ok=True, text="reply 2")
    orch._persist_outbound("r2", kind="slack", channel="C1", via="ad-hoc",
                            ok=True, text="other")
    rows = orch.list_outbound(run_id="r1")
    assert len(rows) == 2
    assert {r["text"] for r in rows} == {"reply 1", "reply 2"}


def test_inbound_since_id_resumes(orch):
    e1 = orch._persist_inbound("r1", kind="http", channel="x", user="u", text="a")
    orch._persist_inbound("r2", kind="http", channel="x", user="u", text="b")
    rows = orch.list_inbound(channel="x")
    last = rows[0]["id"]   # newest
    cursor = rows[1]["id"]  # older — pretend we processed up to here
    rows2 = orch.list_inbound(channel="x", since_id=cursor)
    assert len(rows2) == 1
    assert rows2[0]["id"] == last


def test_persist_run_record_writes_outbound(orch):
    orch._persist_run_record("r99", kind="slack", channel="C1", user="u",
                              text="ask", plan=[], results=[],
                              final="here is the answer", via="ad-hoc",
                              ok=True)
    rows = orch.list_outbound(run_id="r99")
    assert len(rows) == 1
    assert rows[0]["text"] == "here is the answer"


def test_api_inbound_and_outbound(orch):
    orch._persist_inbound("r1", kind="slack", channel="C1", user="u", text="hi")
    orch._persist_outbound("r1", kind="slack", channel="C1", via="ad-hoc",
                            ok=True, text="reply")
    inb = orch.api_orch_inbound({"channel": "C1"})
    out = orch.api_orch_outbound({"runId": "r1"})
    assert inb["ok"] and len(inb["items"]) == 1
    assert out["ok"] and len(out["items"]) == 1
