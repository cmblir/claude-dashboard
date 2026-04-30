"""Unit tests for server.hooks plugin scan + caching."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from server import hooks as hooks_mod


def _seed_plugin(plugins_dir: Path, market: str, plugin: str, hooks_obj: dict) -> Path:
    """Create a layout-A marketplace hooks.json with synthetic content."""
    p = plugins_dir / "marketplaces" / market / "plugins" / plugin / "hooks" / "hooks.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hooks": hooks_obj}, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def plugin_root(tmp_path, monkeypatch, isolated_home):
    """Redirect hooks.PLUGINS_DIR to a fresh tmp dir and clear the module cache."""
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    monkeypatch.setattr(hooks_mod, "PLUGINS_DIR", plugins)
    # stable settings so cache key doesn't depend on real ~/.claude
    monkeypatch.setattr(hooks_mod, "get_settings", lambda: {"enabledPlugins": {}})
    monkeypatch.setattr(hooks_mod, "_HOOKS_CACHE", None, raising=False)
    monkeypatch.setattr(hooks_mod, "_HOOKS_CACHE_AT", 0.0, raising=False)
    monkeypatch.setattr(hooks_mod, "_HOOKS_DIR_MTIME", 0.0, raising=False)
    return plugins


class TestScanPluginHooks:
    def test_no_plugins_dir_returns_empty(self, tmp_path, monkeypatch):
        missing = tmp_path / "nope"
        monkeypatch.setattr(hooks_mod, "PLUGINS_DIR", missing)
        monkeypatch.setattr(hooks_mod, "_HOOKS_CACHE", None, raising=False)
        monkeypatch.setattr(hooks_mod, "_HOOKS_CACHE_AT", 0.0, raising=False)
        assert hooks_mod._scan_plugin_hooks() == []

    def test_no_marketplaces_subdir_returns_empty(self, plugin_root):
        assert hooks_mod._scan_plugin_hooks() == []

    def test_returns_list_with_expected_keys(self, plugin_root):
        _seed_plugin(plugin_root, "market1", "pluginA", {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}
            ]
        })
        out = hooks_mod._scan_plugin_hooks()
        assert isinstance(out, list)
        assert len(out) == 1
        entry = out[0]
        for key in ("event", "scope", "source", "pluginKey", "groupIdx", "subIdx"):
            assert key in entry
        assert entry["scope"] == "plugin"
        assert entry["event"] == "PreToolUse"
        assert entry["pluginKey"] == "pluginA@market1"
        assert entry["matcher"] == "Bash"

    def test_cache_populated_after_first_call(self, plugin_root):
        _seed_plugin(plugin_root, "m1", "p1", {
            "PreToolUse": [{"hooks": [{"type": "command", "command": "x"}]}]
        })
        assert hooks_mod._HOOKS_CACHE is None
        first = hooks_mod._scan_plugin_hooks()
        assert hooks_mod._HOOKS_CACHE is not None
        assert hooks_mod._HOOKS_CACHE_AT > 0
        # Within TTL, second call returns the cached list (same object).
        second = hooks_mod._scan_plugin_hooks()
        assert second is first

    def test_cache_invalidates_on_dir_mtime_change(self, plugin_root):
        _seed_plugin(plugin_root, "m1", "p1", {
            "PreToolUse": [{"hooks": [{"type": "command", "command": "x"}]}]
        })
        first = hooks_mod._scan_plugin_hooks()
        assert len(first) == 1
        # Add a second plugin and bump marketplaces/ mtime past fs granularity.
        _seed_plugin(plugin_root, "m1", "p2", {
            "PostToolUse": [{"hooks": [{"type": "command", "command": "y"}]}]
        })
        import os
        import time as _t
        markets = plugin_root / "marketplaces"
        ts = _t.time() + 5
        os.utime(markets, (ts, ts))
        second = hooks_mod._scan_plugin_hooks()
        assert len(second) == 2

    def test_layout_b_market_level_hooks(self, plugin_root):
        hf = plugin_root / "marketplaces" / "solo" / "hooks" / "hooks.json"
        hf.parent.mkdir(parents=True, exist_ok=True)
        hf.write_text(json.dumps({"hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "z"}]}]
        }}), encoding="utf-8")
        out = hooks_mod._scan_plugin_hooks()
        assert any(e["event"] == "Stop" and e["pluginKey"] == "solo@solo" for e in out)

    def test_malformed_json_is_skipped(self, plugin_root):
        bad = plugin_root / "marketplaces" / "m1" / "plugins" / "broken" / "hooks" / "hooks.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("{not json", encoding="utf-8")
        # Must not raise.
        out = hooks_mod._scan_plugin_hooks()
        assert isinstance(out, list)

    def test_concurrent_calls_do_not_crash(self, plugin_root):
        _seed_plugin(plugin_root, "m1", "p1", {
            "PreToolUse": [{"hooks": [{"type": "command", "command": "x"}]}]
        })
        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(lambda _: hooks_mod._scan_plugin_hooks(), range(16)))
        for r in results:
            assert isinstance(r, list)
            assert all("event" in e for e in r)

    def test_get_hooks_shape(self, plugin_root):
        _seed_plugin(plugin_root, "m1", "p1", {
            "PreToolUse": [{"hooks": [{"type": "command", "command": "x"}]}]
        })
        out = hooks_mod.get_hooks()
        assert set(out.keys()) >= {"hooks", "permissions", "counts"}
        assert "user" in out["counts"] and "plugin" in out["counts"]
        assert out["counts"]["plugin"] == 1
