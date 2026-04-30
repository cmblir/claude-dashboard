"""Unit tests for IO-free helpers in server.process_monitor.

Covers _parse_lsof_line shapes, _ps_metrics_batch boundaries, _pid_alive,
and the kill guards inside api_process_kill. We never actually send a kill
signal — only the guard rejection paths are exercised.
"""
from __future__ import annotations

import os

from server.process_monitor import (
    _KILL_PID_FLOOR,
    _parse_lsof_line,
    _pid_alive,
    _ps_metrics_batch,
    api_process_kill,
)


# ───────── _parse_lsof_line ─────────

class TestParseLsofLine:
    # lsof -nP -iTCP -sTCP:LISTEN row shape:
    # COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME (STATE)
    VALID_TCP = "python3   12345 alice   5u  IPv4 0x123      0t0  TCP 127.0.0.1:8080 (LISTEN)"
    HEADER = "COMMAND     PID USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME"

    def test_valid_tcp_line(self):
        row = _parse_lsof_line(self.VALID_TCP, "tcp")
        assert row is not None
        assert row["pid"] == 12345
        assert row["command"] == "python3"
        assert row["user"] == "alice"
        assert row["proto"] == "tcp"
        assert row["local_port"] == 8080
        assert row["local_addr"] == "127.0.0.1"
        assert row["state"] == "LISTEN"

    def test_header_skipped(self):
        assert _parse_lsof_line(self.HEADER, "tcp") is None

    def test_malformed_too_few_columns(self):
        assert _parse_lsof_line("only three cols here", "tcp") is None
        assert _parse_lsof_line("", "tcp") is None

    def test_wildcard_address(self):
        line = "nginx     900 root    6u  IPv4 0x999      0t0  TCP *:443 (LISTEN)"
        row = _parse_lsof_line(line, "tcp")
        assert row is not None
        assert row["local_addr"] == "*"
        assert row["local_port"] == 443

    def test_ipv6_address(self):
        line = "redis    1500 redis   4u  IPv6 0xabc      0t0  TCP [::1]:5000 (LISTEN)"
        row = _parse_lsof_line(line, "tcp")
        assert row is not None
        assert row["local_addr"] == "[::1]"
        assert row["local_port"] == 5000

    def test_non_numeric_pid_rejected(self):
        line = "python3   PIDX  alice   5u  IPv4 0x123      0t0  TCP 127.0.0.1:8080 (LISTEN)"
        assert _parse_lsof_line(line, "tcp") is None

    def test_non_numeric_port_rejected(self):
        line = "python3   12345 alice   5u  IPv4 0x123      0t0  TCP 127.0.0.1:notaport (LISTEN)"
        assert _parse_lsof_line(line, "tcp") is None

    def test_udp_has_empty_state(self):
        line = "dnsmasq    77 nobody  4u  IPv4 0x111      0t0  UDP 127.0.0.1:53"
        row = _parse_lsof_line(line, "udp")
        assert row is not None
        assert row["state"] == ""
        assert row["proto"] == "udp"


# ───────── _ps_metrics_batch ─────────

class TestPsMetricsBatch:
    def test_empty_pid_list(self):
        assert _ps_metrics_batch([]) == {}

    def test_init_pid_present(self):
        # init (pid 1) always exists on POSIX.
        result = _ps_metrics_batch([1])
        # ps may or may not return rows for pid 1 depending on sandbox,
        # but the shape must be a dict and any returned value has the
        # right keys.
        assert isinstance(result, dict)
        if 1 in result:
            assert "rss_bytes" in result[1]
            assert "cpu_pct" in result[1]


# ───────── _pid_alive ─────────

class TestPidAlive:
    def test_self_alive(self):
        # Sending signal 0 to a process we own is a valid liveness probe.
        # (We use the current process rather than init/pid 1 because macOS
        # raises EPERM for kill(1, 0) from a non-root user, which the
        # helper correctly treats as "not alive" by catching OSError.)
        assert _pid_alive(os.getpid()) is True

    def test_huge_pid_not_alive(self):
        assert _pid_alive(99_999_999) is False


# ───────── kill guards ─────────

class TestKillGuards:
    def test_system_pid_zero_rejected(self):
        # pid=0 is below the PID floor.
        r = api_process_kill({"pid": 0})
        assert r["ok"] is False
        assert "error" in r

    def test_self_pid_rejected(self):
        r = api_process_kill({"pid": os.getpid()})
        assert r["ok"] is False
        assert "self" in r["error"].lower() or str(_KILL_PID_FLOOR) in r["error"]

    def test_pid_below_floor_rejected(self):
        r = api_process_kill({"pid": 1, "signal": "SIGTERM"})
        assert r["ok"] is False
        assert str(_KILL_PID_FLOOR) in r["error"]

    def test_invalid_signal_rejected(self):
        # pid above floor + unknown signal name → signal-validation fires.
        r = api_process_kill({"pid": 12345, "signal": "INVALID"})
        assert r["ok"] is False
        assert "signal" in r["error"].lower()

    def test_missing_pid_rejected(self):
        r = api_process_kill({})
        assert r["ok"] is False

    def test_non_dict_body_rejected(self):
        r = api_process_kill(None)  # type: ignore[arg-type]
        assert r["ok"] is False
