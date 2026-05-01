"""G1 — verify ollama auto-start is opt-in (default skip)."""
from __future__ import annotations

import importlib
import logging

import pytest


@pytest.fixture
def server_mod(monkeypatch):
    """Load the top-level ``server.py`` script (not the ``server/`` package).

    ``import server`` resolves to the package; we want the boot script, which
    defines ``_auto_start_ollama``. Use importlib's machinery directly.
    """
    from importlib import util
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "server.py"
    spec = util.spec_from_file_location("server_boot_script", p)
    mod = util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_skip_when_neither_env_nor_pref(server_mod, monkeypatch, caplog):
    monkeypatch.delenv("OLLAMA_AUTOSTART", raising=False)
    # Force ollama presence so we get past the shutil.which short-circuit
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/local/bin/ollama")
    # Stub prefs to return autoStartOllama not set / false
    import server.prefs as prefs_mod
    monkeypatch.setattr(prefs_mod, "api_prefs_get",
                        lambda body=None: {"prefs": {"behavior": {}}})
    started = []
    monkeypatch.setattr("server.ollama_hub.api_ollama_serve_start",
                        lambda body=None: (started.append(True),
                                           {"ok": True, "status": "ok"})[1])
    monkeypatch.setattr("server.ollama_hub._is_ollama_reachable", lambda *_a: False)

    with caplog.at_level(logging.INFO):
        server_mod._auto_start_ollama()
    assert started == [], "must not auto-start without explicit opt-in"
    assert any("skipped" in r.getMessage().lower() for r in caplog.records)


def test_env_optin_starts(server_mod, monkeypatch):
    monkeypatch.setenv("OLLAMA_AUTOSTART", "1")
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/local/bin/ollama")
    monkeypatch.setattr("server.ollama_hub._is_ollama_reachable", lambda *_a: False)
    started = []
    monkeypatch.setattr("server.ollama_hub.api_ollama_serve_start",
                        lambda body=None: (started.append(True),
                                           {"ok": True, "status": "ok"})[1])
    server_mod._auto_start_ollama()
    assert started == [True]


def test_pref_optin_starts(server_mod, monkeypatch):
    monkeypatch.delenv("OLLAMA_AUTOSTART", raising=False)
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/local/bin/ollama")
    monkeypatch.setattr("server.ollama_hub._is_ollama_reachable", lambda *_a: False)
    import server.prefs as prefs_mod
    monkeypatch.setattr(prefs_mod, "api_prefs_get",
                        lambda body=None: {"prefs": {"behavior": {"autoStartOllama": True}}})
    started = []
    monkeypatch.setattr("server.ollama_hub.api_ollama_serve_start",
                        lambda body=None: (started.append(True),
                                           {"ok": True, "status": "ok"})[1])
    server_mod._auto_start_ollama()
    assert started == [True]


def test_already_running_is_noop(server_mod, monkeypatch):
    monkeypatch.setenv("OLLAMA_AUTOSTART", "1")
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/local/bin/ollama")
    monkeypatch.setattr("server.ollama_hub._is_ollama_reachable", lambda *_a: True)
    started = []
    monkeypatch.setattr("server.ollama_hub.api_ollama_serve_start",
                        lambda body=None: (started.append(True),
                                           {"ok": True})[1])
    server_mod._auto_start_ollama()
    assert started == [], "already-running short-circuit must not double-start"


def test_no_ollama_binary_is_noop(server_mod, monkeypatch):
    monkeypatch.setenv("OLLAMA_AUTOSTART", "1")
    monkeypatch.setattr("shutil.which", lambda _x: None)   # no binary
    started = []
    monkeypatch.setattr("server.ollama_hub.api_ollama_serve_start",
                        lambda body=None: (started.append(True),
                                           {"ok": True})[1])
    server_mod._auto_start_ollama()
    assert started == []
