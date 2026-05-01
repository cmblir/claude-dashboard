"""Tests for cycle-2 orchestrator additions: history persistence + Slack
signing verification."""
from __future__ import annotations

import hmac
import importlib
import time

import pytest


@pytest.fixture
def orch(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_DASHBOARD_ORCHESTRATOR",
                       str(tmp_path / "orch.json"))
    monkeypatch.setenv("CLAUDE_DASHBOARD_DB", str(tmp_path / "bus.db"))
    from server import config as _c
    importlib.reload(_c)
    from server import db as _db
    importlib.reload(_db)
    from server import agent_bus
    importlib.reload(agent_bus)
    from server import orchestrator
    importlib.reload(orchestrator)
    return orchestrator


def test_run_history_round_trip(orch):
    h = orch.api_orch_history({"limit": 10})
    assert h["ok"] and h["runs"] == []

    orch._persist_run_record(
        "rid001", kind="http", channel="ui", user="u1",
        text="hello", plan=[{"a": 1}], results=[{"ok": True, "output": "x"}],
        final="merged", via="ad-hoc", ok=True,
    )
    orch._persist_run_record(
        "rid002", kind="slack", channel="C1", user="u2",
        text="bye", plan=[], results=[],
        final="", via="workflow", ok=False, error="boom",
    )

    runs = orch.api_orch_history({"limit": 10})["runs"]
    assert len(runs) == 2
    # Newest first.
    assert runs[0]["runId"] == "rid002"
    assert runs[0]["error"] == "boom"
    assert runs[0]["ok"] is False
    assert runs[1]["runId"] == "rid001"

    detail = orch.api_orch_history_get({"runId": "rid001"})
    assert detail["ok"]
    assert detail["run"]["plan"] == [{"a": 1}]
    assert detail["run"]["results"][0]["output"] == "x"


def test_history_get_missing(orch):
    r = orch.api_orch_history_get({"runId": "does-not-exist"})
    assert r["ok"] is False


def test_slack_signature_valid(orch):
    secret = "sssh"
    body = b'{"type":"event_callback"}'
    ts = str(int(time.time()))
    sig = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + body,
                           "sha256").hexdigest()
    ok, reason = orch._verify_slack_signature(
        body, {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig},
        secret,
    )
    assert ok and reason == "ok"


def test_slack_signature_mismatch(orch):
    body = b'{"x":1}'
    ts = str(int(time.time()))
    ok, reason = orch._verify_slack_signature(
        body, {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": "v0=bogus"},
        "secret",
    )
    assert ok is False
    assert reason == "signature-mismatch"


def test_slack_signature_stale_timestamp(orch):
    body = b"{}"
    sig = "v0=" + hmac.new(b"k", b"v0:0:" + body, "sha256").hexdigest()
    ok, reason = orch._verify_slack_signature(
        body, {"X-Slack-Request-Timestamp": "0", "X-Slack-Signature": sig},
        "k",
    )
    assert ok is False
    assert reason == "stale-timestamp"


def test_slack_signature_missing_headers(orch):
    ok, reason = orch._verify_slack_signature(b"{}", {}, "secret")
    assert ok is False and reason == "missing-headers"
