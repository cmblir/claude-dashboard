"""Unit tests for server.mcp catalog + claude-mcp-list cache."""
from __future__ import annotations

import json
import time

import pytest

from server import mcp as mcp_mod


@pytest.fixture
def mcp_isolated(tmp_path, monkeypatch, isolated_home):
    """Redirect the on-disk MCP cache file and reset in-memory cache."""
    cache_file = tmp_path / "mcp-cache.json"
    monkeypatch.setattr(mcp_mod, "_MCP_LIST_CACHE_FILE", cache_file)
    # Reset the module-level cache dict in place (other code holds the same ref).
    mcp_mod._MCP_LIST_CACHE["ts"] = 0.0
    mcp_mod._MCP_LIST_CACHE["status"] = {}
    mcp_mod._MCP_LIST_CACHE["url"] = {}
    # Pretend `claude` binary is missing so refresh is a no-op subprocess-wise.
    monkeypatch.setattr(mcp_mod.shutil, "which", lambda name: None)
    return cache_file


class TestLoadDiskCache:
    def test_missing_file_is_noop(self, mcp_isolated):
        mcp_mod._load_disk_cache()
        assert mcp_mod._MCP_LIST_CACHE["status"] == {}
        assert mcp_mod._MCP_LIST_CACHE["url"] == {}

    def test_loads_persisted_payload(self, mcp_isolated):
        payload = {
            "status": {"context7": "Connected"},
            "url": {"context7": "npx -y @upstash/context7-mcp"},
            "ts": 12345.0,
        }
        mcp_isolated.write_text(json.dumps(payload), encoding="utf-8")
        mcp_mod._load_disk_cache()
        assert mcp_mod._MCP_LIST_CACHE["status"] == payload["status"]
        assert mcp_mod._MCP_LIST_CACHE["url"] == payload["url"]
        assert mcp_mod._MCP_LIST_CACHE["ts"] == 12345.0

    def test_idempotent(self, mcp_isolated):
        mcp_isolated.write_text(json.dumps({
            "status": {"a": "ok"}, "url": {"a": "x"}, "ts": 1.0
        }), encoding="utf-8")
        mcp_mod._load_disk_cache()
        mcp_mod._load_disk_cache()
        assert mcp_mod._MCP_LIST_CACHE["status"] == {"a": "ok"}

    def test_garbage_file_is_swallowed(self, mcp_isolated):
        mcp_isolated.write_text("{not json", encoding="utf-8")
        mcp_mod._load_disk_cache()  # must not raise
        assert mcp_mod._MCP_LIST_CACHE["status"] == {}


class TestClaudeMcpListCached:
    def test_returns_tuple_of_two_dicts(self, mcp_isolated):
        status, url = mcp_mod._claude_mcp_list_cached()
        assert isinstance(status, dict)
        assert isinstance(url, dict)

    def test_fresh_cache_skips_refresh(self, mcp_isolated, monkeypatch):
        mcp_mod._MCP_LIST_CACHE["status"] = {"foo": "Connected"}
        mcp_mod._MCP_LIST_CACHE["url"] = {"foo": "stdio://x"}
        mcp_mod._MCP_LIST_CACHE["ts"] = time.time()
        called = {"n": 0}

        def _boom():
            called["n"] += 1
            return ({}, {})

        monkeypatch.setattr(mcp_mod, "_refresh_mcp_list_blocking", _boom)
        status, url = mcp_mod._claude_mcp_list_cached()
        assert status == {"foo": "Connected"}
        assert url == {"foo": "stdio://x"}
        assert called["n"] == 0

    def test_stale_cache_returns_cached_value_immediately(self, mcp_isolated, monkeypatch):
        mcp_mod._MCP_LIST_CACHE["status"] = {"foo": "Connected"}
        mcp_mod._MCP_LIST_CACHE["url"] = {"foo": "x"}
        mcp_mod._MCP_LIST_CACHE["ts"] = time.time() - (mcp_mod._MCP_LIST_TTL + 60)

        def _refresh():
            return ({"new": "ok"}, {"new": "y"})

        monkeypatch.setattr(mcp_mod, "_refresh_mcp_list_blocking", _refresh)
        status, _url = mcp_mod._claude_mcp_list_cached()
        # Cached value returned synchronously even though bg refresh kicks off.
        assert "foo" in status

    def test_no_cache_calls_refresh(self, mcp_isolated, monkeypatch):
        called = {"n": 0}

        def _refresh():
            called["n"] += 1
            return ({"r": "Connected"}, {"r": "u"})

        monkeypatch.setattr(mcp_mod, "_refresh_mcp_list_blocking", _refresh)
        status, _url = mcp_mod._claude_mcp_list_cached()
        assert called["n"] == 1
        assert status == {"r": "Connected"}


class TestApiMcpCatalog:
    def test_shape_has_catalog_and_count(self, mcp_isolated, monkeypatch):
        monkeypatch.setattr(mcp_mod, "list_connectors", lambda: {
            "platform": [], "local": [], "plugin": [], "desktop": [], "project": []
        })
        out = mcp_mod.api_mcp_catalog()
        assert "catalog" in out
        assert "installedCount" in out
        assert isinstance(out["catalog"], list)
        assert len(out["catalog"]) == len(mcp_mod.MCP_CATALOG)
        assert out["installedCount"] == 0

    def test_marks_installed_entries(self, mcp_isolated, monkeypatch):
        monkeypatch.setattr(mcp_mod, "list_connectors", lambda: {
            "platform": [], "plugin": [], "desktop": [], "project": [],
            "local": [{"name": "context7"}],
        })
        out = mcp_mod.api_mcp_catalog()
        installed_ids = [e["id"] for e in out["catalog"] if e.get("installed")]
        assert "context7" in installed_ids
        assert out["installedCount"] == 1

    def test_each_catalog_entry_has_required_fields(self, mcp_isolated, monkeypatch):
        monkeypatch.setattr(mcp_mod, "list_connectors", lambda: {
            "platform": [], "local": [], "plugin": [], "desktop": [], "project": []
        })
        out = mcp_mod.api_mcp_catalog()
        for entry in out["catalog"]:
            for key in ("id", "name", "description", "category", "install", "cli", "installed"):
                assert key in entry, f"missing {key} in {entry.get('id')}"


class TestRefreshBlockingMockedSubprocess:
    def test_refresh_with_no_claude_bin(self, mcp_isolated):
        # `which` patched to None in fixture — refresh yields empty dicts but stamps ts.
        status, url = mcp_mod._refresh_mcp_list_blocking()
        assert status == {}
        assert url == {}
        assert mcp_mod._MCP_LIST_CACHE["ts"] > 0

    def test_refresh_parses_subprocess_output(self, mcp_isolated, monkeypatch):
        monkeypatch.setattr(mcp_mod.shutil, "which", lambda name: "/usr/bin/claude")

        class _Proc:
            stdout = "context7: npx -y @upstash/context7-mcp - Connected\n"

        def _run(*a, **k):
            return _Proc()

        monkeypatch.setattr(mcp_mod.subprocess, "run", _run)
        status, url = mcp_mod._refresh_mcp_list_blocking()
        assert status.get("context7") == "Connected"
        assert "context7-mcp" in url.get("context7", "")
