"""Unit tests for server.notify channel dispatchers — fully offline."""
from __future__ import annotations

import urllib.error

import pytest

from server import notify as nt


# ───────── _send_notify ─────────

class TestSendNotify:
    def test_empty_config_is_noop(self):
        out = nt._send_notify({}, "test", "summary")
        assert isinstance(out, dict)
        assert out == {}

    def test_non_dict_config_returns_empty(self):
        out = nt._send_notify(None, "test", "summary")  # type: ignore[arg-type]
        assert out == {}

    def test_routes_only_configured_channels(self, monkeypatch):
        calls = []

        def _post(url, payload):
            calls.append((url, payload))
            return True

        monkeypatch.setattr(nt, "_post_json", _post)
        out = nt._send_notify(
            {"slack": "https://hooks.slack.com/services/xxx"},
            "kind", "body",
        )
        assert out.get("slack", {}).get("ok") is True
        assert calls and "hooks.slack.com" in calls[0][0]


# ───────── send_email ─────────

class TestSendEmail:
    def test_empty_config_rejects(self):
        out = nt.send_email({}, "t", "b")
        assert out["ok"] is False
        assert "error" in out

    def test_non_dict_rejects(self):
        out = nt.send_email("nope", "t", "b")  # type: ignore[arg-type]
        assert out["ok"] is False

    def test_missing_recipients_rejects(self):
        out = nt.send_email({
            "smtp_host": "smtp.example.com",
            "smtp_user": "u@example.com",
            "smtp_password": "pw",
            "from": "u@example.com",
            "to": "",
        }, "t", "b")
        assert out["ok"] is False
        assert "recipients" in out["error"] or "missing" in out["error"]

    def test_missing_password_rejects(self):
        out = nt.send_email({
            "smtp_host": "smtp.example.com",
            "smtp_user": "u@example.com",
            "smtp_password": "",
            "to": "x@example.com",
        }, "t", "b")
        assert out["ok"] is False


# ───────── send_telegram ─────────

class TestSendTelegram:
    def test_empty_config_rejects(self):
        out = nt.send_telegram({}, "t", "b")
        assert out["ok"] is False
        assert "missing" in out["error"]

    def test_non_dict_rejects(self):
        out = nt.send_telegram(None, "t", "b")  # type: ignore[arg-type]
        assert out["ok"] is False

    def test_missing_chat_id_rejects(self):
        out = nt.send_telegram({"bot_token": "abc"}, "t", "b")
        assert out["ok"] is False

    def test_network_error_returns_ok_false(self, monkeypatch):
        class _Opener:
            def open(self, *a, **k):
                raise urllib.error.URLError("no network")

        monkeypatch.setattr(nt.urllib.request, "build_opener",
                            lambda *a, **k: _Opener())
        out = nt.send_telegram({"bot_token": "fake", "chat_id": "123"}, "t", "b")
        assert out["ok"] is False
        assert "error" in out


# ───────── send_slack / send_discord signatures ─────────

class TestSlackDiscordSignatures:
    def test_send_slack_callable(self):
        assert callable(nt.send_slack)

    def test_send_discord_callable(self):
        assert callable(nt.send_discord)

    def test_slack_rejects_non_whitelisted_url(self):
        ok = nt.send_slack("https://evil.example.com/webhook", "t", "b")
        assert ok is False

    def test_discord_rejects_non_whitelisted_url(self):
        ok = nt.send_discord("http://insecure.example/webhook", "t", "b")
        assert ok is False

    def test_slack_post_to_whitelisted_host(self, monkeypatch):
        seen = {}

        def _post(url, payload):
            seen["url"] = url
            seen["payload"] = payload
            return True

        monkeypatch.setattr(nt, "_post_json", _post)
        assert nt.send_slack("https://hooks.slack.com/services/x", "T", "B") is True
        assert "hooks.slack.com" in seen["url"]
        assert "T" in seen["payload"]["text"]
