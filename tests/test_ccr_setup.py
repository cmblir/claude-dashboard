"""Unit tests for server.ccr_setup wizard endpoints.

CCR_CONFIG_PATH is redirected into tmp_path so no real ~/.claude-code-router
file is touched. Network and the actual `ccr` binary are not invoked —
these tests cover only deterministic shape/validation logic.
"""
from __future__ import annotations

import pytest

from server import ccr_setup as ccr


@pytest.fixture
def ccr_tmp_config(tmp_path, monkeypatch, isolated_home):
    """Redirect CCR_CONFIG_DIR / CCR_CONFIG_PATH at tmp_path."""
    cfg_dir = tmp_path / ".claude-code-router"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "config.json"
    monkeypatch.setattr(ccr, "CCR_CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(ccr, "CCR_CONFIG_PATH", cfg_path)
    return cfg_path


# ───────── api_ccr_status ─────────

class TestStatus:
    def test_returns_expected_keys(self, ccr_tmp_config):
        out = ccr.api_ccr_status({})
        assert out.get("ok") is True
        for key in (
            "node_version", "ccr_installed", "claude_installed",
            "config_exists", "service_running", "service_port",
        ):
            assert key in out, f"missing key: {key}"

    def test_config_exists_false_when_missing(self, ccr_tmp_config):
        # Fresh tmp dir — file not created yet.
        assert not ccr_tmp_config.exists()
        out = ccr.api_ccr_status({})
        assert out["config_exists"] is False


# ───────── api_ccr_presets ─────────

class TestPresets:
    def test_returns_five_presets(self):
        out = ccr.api_ccr_presets({})
        assert out["ok"] is True
        assert len(out["presets"]) == 5

    def test_presets_have_required_fields(self):
        out = ccr.api_ccr_presets({})
        for preset in out["presets"]:
            for field in ("id", "label", "name", "api_base_url", "models"):
                assert field in preset, f"preset missing {field}: {preset}"
            assert isinstance(preset["models"], list)


# ───────── api_ccr_alias_snippet ─────────

class TestAliasSnippet:
    def test_returns_expected_keys(self, ccr_tmp_config):
        out = ccr.api_ccr_alias_snippet({})
        assert out["ok"] is True
        for key in ("current_shell", "rc_path", "zshrc_snippet",
                    "bashrc_snippet", "already_present"):
            assert key in out

    def test_snippet_contains_zclaude_alias(self, ccr_tmp_config):
        out = ccr.api_ccr_alias_snippet({})
        assert "alias zclaude='ccr code'" in out["zshrc_snippet"]
        assert "alias zclaude='ccr code'" in out["bashrc_snippet"]


# ───────── api_ccr_config_save ─────────

class TestConfigSave:
    def test_rejects_missing_config(self, ccr_tmp_config):
        out = ccr.api_ccr_config_save({})
        assert out["ok"] is False
        assert "config" in out["error"].lower()

    def test_rejects_non_dict_config(self, ccr_tmp_config):
        out = ccr.api_ccr_config_save({"config": "not-an-object"})
        assert out["ok"] is False

    def test_strips_unknown_top_level_keys(self, ccr_tmp_config):
        out = ccr.api_ccr_config_save({"config": {"INVALID_KEY": "x"}})
        assert out["ok"] is True
        assert "INVALID_KEY" not in out["config"]
        # The validator should also have warned about it.
        assert any("INVALID_KEY" in w for w in out["warnings"])

    def test_invalid_port_is_dropped_with_warning(self, ccr_tmp_config):
        out = ccr.api_ccr_config_save({"config": {"PORT": "not-int"}})
        assert out["ok"] is True
        assert "PORT" not in out["config"]
        assert any("PORT" in w for w in out["warnings"])

    def test_valid_provider_is_accepted(self, ccr_tmp_config):
        cfg = {
            "Providers": [{
                "name": "test",
                "api_base_url": "https://example.com",
                "api_key": "k",
                "models": ["m1"],
            }],
        }
        out = ccr.api_ccr_config_save({"config": cfg})
        assert out["ok"] is True
        assert len(out["config"]["Providers"]) == 1
        prov = out["config"]["Providers"][0]
        assert prov["name"] == "test"
        assert prov["models"] == ["m1"]

    def test_provider_missing_required_field_dropped(self, ccr_tmp_config):
        # Missing api_base_url ⇒ provider should be dropped, not raise.
        cfg = {
            "Providers": [{
                "name": "broken",
                "api_key": "k",
                "models": ["m1"],
            }],
        }
        out = ccr.api_ccr_config_save({"config": cfg})
        assert out["ok"] is True
        assert out["config"]["Providers"] == []
        assert any("dropped" in w.lower() for w in out["warnings"])

    def test_writes_config_file(self, ccr_tmp_config):
        out = ccr.api_ccr_config_save({"config": {"LOG": True, "PORT": 3456}})
        assert out["ok"] is True
        assert ccr_tmp_config.exists()
        text = ccr_tmp_config.read_text(encoding="utf-8")
        assert '"PORT": 3456' in text


# ───────── _validate_config (direct, no file I/O) ─────────

class TestValidateConfigDirect:
    def test_log_level_lowercased(self):
        sanitized, warnings = ccr._validate_config({"LOG_LEVEL": "DEBUG"})
        assert sanitized["LOG_LEVEL"] == "debug"
        assert warnings == []

    def test_invalid_log_level_dropped(self):
        sanitized, warnings = ccr._validate_config({"LOG_LEVEL": "shout"})
        assert "LOG_LEVEL" not in sanitized
        assert any("LOG_LEVEL" in w for w in warnings)

    def test_router_unknown_key_dropped(self):
        sanitized, warnings = ccr._validate_config({"Router": {"badKey": "x"}})
        assert "badKey" not in sanitized["Router"]
        assert any("badKey" in w for w in warnings)
