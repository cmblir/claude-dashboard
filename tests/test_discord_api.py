"""Discord integration — config validation + ed25519 signature verification."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def disc(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_DASHBOARD_DISCORD",
                       str(tmp_path / "discord.json"))
    from server import config as _c; importlib.reload(_c)
    from server import discord_api; importlib.reload(discord_api)
    return discord_api


def test_config_starts_empty(disc):
    r = disc.api_discord_config_get({})
    assert r["ok"] and r["configured"] is False


def test_save_rejects_bad_token(disc):
    r = disc.api_discord_config_save({"token": "short"})
    assert r["ok"] is False
    assert "token" in r["error"].lower()


def test_save_rejects_bad_pubkey(disc, monkeypatch):
    """When token is already on file, saving with malformed pubkey fails."""
    # Pre-seed a token by going through _save_cfg directly.
    disc._save_cfg({**disc._empty_cfg(), "token": "x" * 60,
                    "applicationId": "111111111111111111"})
    r = disc.api_discord_config_save({"publicKey": "not hex"})
    assert r["ok"] is False
    assert "publickey" in r["error"].lower()


def test_save_rejects_bad_channel(disc):
    disc._save_cfg({**disc._empty_cfg(), "token": "x" * 60})
    r = disc.api_discord_config_save({"defaultChannel": "not-a-snowflake"})
    assert r["ok"] is False


def test_signature_verify_roundtrip(disc):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    sk = Ed25519PrivateKey.generate()
    pk_hex = sk.public_key().public_bytes_raw().hex()
    body = b'{"type":1}'
    ts = "1700000000"
    sig_hex = sk.sign(ts.encode() + body).hex()
    assert disc.verify_interaction_signature(body, sig_hex, ts, pk_hex)


def test_signature_verify_rejects_bad(disc):
    pk_hex = "0" * 64
    assert disc.verify_interaction_signature(b'{}', "ab" * 32, "0", pk_hex) is False


def test_signature_verify_rejects_malformed_pubkey(disc):
    assert disc.verify_interaction_signature(b'{}', "ab" * 32, "0", "bogus") is False


def test_signature_verify_rejects_empty(disc):
    assert disc.verify_interaction_signature(b"", "ab", "0", "0" * 64) is False
