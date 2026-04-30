"""Unit tests for server.prefs HTTP handlers + validation logic.

Covers shape of api_prefs_get, round-trip via api_prefs_set (single + batch),
api_prefs_reset (section + full), and the validation rules that protect the
on-disk file from malformed input.
"""
from __future__ import annotations

import pytest

from server import prefs as prefs_mod
from server.prefs import (
    DEFAULT_PREFS,
    api_prefs_get,
    api_prefs_reset,
    api_prefs_set,
)


@pytest.fixture
def prefs_file(tmp_path, monkeypatch):
    """Redirect PREFS_PATH at a tmp file so each test starts clean."""
    p = tmp_path / "prefs.json"
    monkeypatch.setattr(prefs_mod, "PREFS_PATH", p)
    return p


# ───────── api_prefs_get ─────────

class TestPrefsGet:
    def test_returns_full_shape(self, prefs_file):
        out = api_prefs_get({})
        assert out["ok"] is True
        for key in ("prefs", "defaults", "schema", "savedAt"):
            assert key in out

    def test_all_sections_present(self, prefs_file):
        out = api_prefs_get({})
        for section in ("ui", "ai", "behavior", "workflow"):
            assert section in out["prefs"], f"missing section: {section}"

    def test_defaults_match_module_defaults(self, prefs_file):
        out = api_prefs_get({})
        assert out["defaults"] == DEFAULT_PREFS


# ───────── api_prefs_set ─────────

class TestPrefsSet:
    def test_single_key_round_trip(self, prefs_file):
        r = api_prefs_set({"section": "behavior", "key": "autoStartOllama", "value": False})
        assert r["ok"] is True
        assert r["prefs"]["behavior"]["autoStartOllama"] is False
        # persisted across reads
        assert api_prefs_get({})["prefs"]["behavior"]["autoStartOllama"] is False

    def test_batch_patch(self, prefs_file):
        r = api_prefs_set({"patch": {"ui": {"theme": "midnight"}, "ai": {"effort": "high"}}})
        assert r["ok"] is True
        assert r["prefs"]["ui"]["theme"] == "midnight"
        assert r["prefs"]["ai"]["effort"] == "high"

    def test_missing_payload_rejected(self, prefs_file):
        r = api_prefs_set({})
        assert r["ok"] is False
        assert "error" in r

    def test_wrong_type_coerced_or_dropped(self, prefs_file):
        # bool field given non-bool string → coerced ("true" → True)
        r = api_prefs_set({"section": "behavior", "key": "autoResume", "value": "false"})
        assert r["ok"] is True
        assert r["prefs"]["behavior"]["autoResume"] is False

    def test_unknown_key_silent_drop(self, prefs_file):
        # Unknown key should be silently ignored (validator design).
        r = api_prefs_set({"section": "ui", "key": "doesNotExist", "value": "x"})
        assert r["ok"] is True
        assert "doesNotExist" not in r["prefs"]["ui"]


# ───────── validation rules ─────────

class TestValidation:
    def test_int_clamp_low(self, prefs_file):
        r = api_prefs_set({"section": "behavior", "key": "telemetryRefresh", "value": -1})
        assert r["prefs"]["behavior"]["telemetryRefresh"] == 0  # clamped to lo

    def test_int_clamp_high(self, prefs_file):
        r = api_prefs_set({"section": "behavior", "key": "telemetryRefresh", "value": 99999})
        assert r["prefs"]["behavior"]["telemetryRefresh"] == 3600  # clamped to hi

    def test_int_in_range(self, prefs_file):
        r = api_prefs_set({"section": "behavior", "key": "telemetryRefresh", "value": 60})
        assert r["prefs"]["behavior"]["telemetryRefresh"] == 60

    def test_enum_accepts_known(self, prefs_file):
        for theme in ("auto", "dark", "light", "midnight", "forest", "sunset"):
            r = api_prefs_set({"section": "ui", "key": "theme", "value": theme})
            assert r["prefs"]["ui"]["theme"] == theme

    def test_enum_rejects_unknown(self, prefs_file):
        # Set a known good value first.
        api_prefs_set({"section": "ui", "key": "theme", "value": "midnight"})
        # Unknown enum value → validator falls back to current/default.
        r = api_prefs_set({"section": "ui", "key": "theme", "value": "neon"})
        assert r["prefs"]["ui"]["theme"] != "neon"
        assert r["prefs"]["ui"]["theme"] in ("auto", "dark", "light", "midnight", "forest", "sunset")


# ───────── api_prefs_reset ─────────

class TestPrefsReset:
    def test_reset_section(self, prefs_file):
        api_prefs_set({"section": "ui", "key": "theme", "value": "midnight"})
        r = api_prefs_reset({"section": "ui"})
        assert r["ok"] is True
        assert r["prefs"]["ui"]["theme"] == DEFAULT_PREFS["ui"]["theme"]

    def test_reset_all(self, prefs_file):
        api_prefs_set({"patch": {"ui": {"theme": "midnight"}, "ai": {"effort": "high"}}})
        r = api_prefs_reset({})
        assert r["ok"] is True
        assert r["prefs"] == DEFAULT_PREFS

    def test_reset_invalid_section_does_not_crash(self, prefs_file):
        # Invalid section name → falls through to "reset everything" branch.
        # The contract is "graceful, no crash" — we accept either behaviour
        # as long as the response is well-formed and ok=True.
        api_prefs_set({"section": "ui", "key": "theme", "value": "midnight"})
        r = api_prefs_reset({"section": "doesNotExist"})
        assert r["ok"] is True
        assert "prefs" in r
