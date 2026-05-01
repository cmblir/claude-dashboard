"""H4 — docker_run workflow node sanitisation + execution paths."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def wf(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_DASHBOARD_DB", str(tmp_path / "wf.db"))
    monkeypatch.setenv("CLAUDE_DASHBOARD_WORKFLOWS",
                       str(tmp_path / "workflows.json"))
    from server import config as _c; importlib.reload(_c)
    from server import db as _db; importlib.reload(_db)
    from server import workflows; importlib.reload(workflows)
    return workflows


def test_sanitize_keeps_image_command(wf):
    n = wf._sanitize_node({"id": "n-x", "type": "docker_run",
                            "x": 0, "y": 0,
                            "data": {"image": "alpine:3", "command": "echo hi"}})
    assert n["type"] == "docker_run"
    assert n["data"]["image"] == "alpine:3"
    assert n["data"]["command"] == "echo hi"


def test_sanitize_clamps_memory_and_timeout(wf):
    n = wf._sanitize_node({"id": "n-x", "type": "docker_run",
                            "x": 0, "y": 0,
                            "data": {"command": "x", "memMb": 99999,
                                     "timeoutSec": 99999}})
    assert n["data"]["memMb"] == 4096
    assert n["data"]["timeoutSec"] == 600


def test_sanitize_strips_bad_env_keys(wf):
    n = wf._sanitize_node({"id": "n-x", "type": "docker_run",
                            "x": 0, "y": 0,
                            "data": {"command": "x", "env": {
                                "GOOD_KEY": "v",
                                "lower": "no",       # rejected (lowercase)
                                "1NUMERIC": "no",     # rejected (leading digit)
                                "WITH-DASH": "no",   # rejected (dash)
                            }}})
    assert "GOOD_KEY" in n["data"]["env"]
    assert "lower" not in n["data"]["env"]
    assert "1NUMERIC" not in n["data"]["env"]
    assert "WITH-DASH" not in n["data"]["env"]


def test_sanitize_defaults_network_to_none(wf):
    n = wf._sanitize_node({"id": "n-x", "type": "docker_run",
                            "x": 0, "y": 0,
                            "data": {"command": "x"}})
    assert n["data"]["network"] == "none"
    n2 = wf._sanitize_node({"id": "n-x", "type": "docker_run",
                             "x": 0, "y": 0,
                             "data": {"command": "x", "network": "host"}})
    # 'host' isn't an allowed value → coerced to 'none'
    assert n2["data"]["network"] == "none"


def test_sanitize_keeps_explicit_bridge(wf):
    n = wf._sanitize_node({"id": "n-x", "type": "docker_run",
                            "x": 0, "y": 0,
                            "data": {"command": "x", "network": "bridge"}})
    assert n["data"]["network"] == "bridge"


def test_execute_rejects_empty_command(wf):
    r = wf._execute_docker_run_node({"image": "alpine:3", "command": "  "},
                                     [], lambda: 0)
    assert r["status"] == "err"
    assert "command" in r["error"].lower()


def test_execute_rejects_missing_docker(wf, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _x: None)
    r = wf._execute_docker_run_node({"image": "alpine:3", "command": "echo hi",
                                       "timeoutSec": 5, "memMb": 64,
                                       "network": "none"}, [], lambda: 0)
    assert r["status"] == "err"
    assert "docker" in r["error"].lower()
    # Critical: must NOT fall back to host execution.
    assert "host" not in r.get("output", "")


def test_execute_uses_subprocess(wf, monkeypatch):
    """Verify the argv we pass to subprocess.run includes the safety flags."""
    captured = {}

    class FakeProc:
        def __init__(self, rc=0, stdout="ok\n", stderr=""):
            self.returncode = rc; self.stdout = stdout; self.stderr = stderr

    def fake_run(argv, input=None, capture_output=None, text=None, timeout=None):
        captured["argv"] = argv
        captured["input"] = input
        captured["timeout"] = timeout
        return FakeProc()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/local/bin/docker")
    r = wf._execute_docker_run_node({
        "image": "alpine:3", "command": "echo hi",
        "timeoutSec": 30, "memMb": 256,
        "mountPath": "/data", "mountReadonly": True,
        "network": "none", "env": {"FOO": "bar"},
    }, ["upstream input"], lambda: 0)
    assert r["status"] == "ok"
    assert r["output"] == "ok\n"
    argv = captured["argv"]
    assert "--rm" in argv
    assert "--network=none" in argv
    assert "--memory=256m" in argv
    assert "--security-opt=no-new-privileges" in argv
    assert "/data:/data:ro" in " ".join(argv)
    assert "FOO=bar" in argv
    assert captured["input"] == "upstream input"
    assert captured["timeout"] == 30


# ───── I2 (v2.61.0) — docker_run result cache ─────

def test_sanitize_cache_defaults_false(wf):
    n = wf._sanitize_node({"id": "n-x", "type": "docker_run",
                            "x": 0, "y": 0,
                            "data": {"command": "x"}})
    assert n["data"]["cache"] is False
    assert n["data"]["cacheTtlSec"] == 300


def test_sanitize_cache_true_survives(wf):
    n = wf._sanitize_node({"id": "n-x", "type": "docker_run",
                            "x": 0, "y": 0,
                            "data": {"command": "x", "cache": True,
                                     "cacheTtlSec": 60}})
    assert n["data"]["cache"] is True
    assert n["data"]["cacheTtlSec"] == 60


def test_sanitize_cache_ttl_clamped(wf):
    n = wf._sanitize_node({"id": "n-x", "type": "docker_run",
                            "x": 0, "y": 0,
                            "data": {"command": "x", "cache": True,
                                     "cacheTtlSec": 999999}})
    assert n["data"]["cacheTtlSec"] == 86400


def test_cache_hit_skips_subprocess(wf, monkeypatch):
    """A cached result should be returned without calling subprocess.run."""
    import subprocess
    subprocess_called = {"n": 0}

    class FakeProc:
        returncode = 0
        stdout = "live result\n"
        stderr = ""

    def fake_run(*a, **k):
        subprocess_called["n"] += 1
        return FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/docker")
    wf._docker_cache_clear_for_tests()

    data = {"image": "alpine:3", "command": "echo hi",
            "timeoutSec": 5, "memMb": 64, "network": "none", "env": {},
            "cache": True, "cacheTtlSec": 300}

    # First call — cache miss, subprocess is invoked.
    r1 = wf._execute_docker_run_node(data, [], lambda: 0)
    assert r1["status"] == "ok"
    assert subprocess_called["n"] == 1
    assert r1["cached"] is False

    # Second call — cache hit, subprocess should NOT be called again.
    r2 = wf._execute_docker_run_node(data, [], lambda: 0)
    assert r2["status"] == "ok"
    assert subprocess_called["n"] == 1      # still 1
    assert r2["cached"] is True
    assert r2["output"] == "live result\n"


def test_cache_key_changes_with_different_stdin(wf):
    key1 = wf._docker_cache_key({"image": "a", "command": "x",
                                  "mountPath": None, "mountReadonly": True,
                                  "network": "none", "env": {}}, "input-a")
    key2 = wf._docker_cache_key({"image": "a", "command": "x",
                                  "mountPath": None, "mountReadonly": True,
                                  "network": "none", "env": {}}, "input-b")
    assert key1 != key2


def test_cache_disabled_does_not_cache(wf, monkeypatch):
    import subprocess
    call_count = {"n": 0}

    class FakeProc:
        returncode = 0
        stdout = "out\n"
        stderr = ""

    def fake_run(*a, **k):
        call_count["n"] += 1
        return FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/docker")
    wf._docker_cache_clear_for_tests()

    data = {"image": "alpine:3", "command": "echo hi",
            "timeoutSec": 5, "memMb": 64, "network": "none", "env": {},
            "cache": False, "cacheTtlSec": 300}

    wf._execute_docker_run_node(data, [], lambda: 0)
    wf._execute_docker_run_node(data, [], lambda: 0)
    assert call_count["n"] == 2     # subprocess called both times
