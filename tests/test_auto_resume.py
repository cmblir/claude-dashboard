"""Unit tests for deterministic logic in server.auto_resume.

Covers: _classify_exit, _parse_reset_time, _exponential_backoff,
        _push_hash_and_check_stall, _jsonl_idle_seconds, _looks_rate_limited.

Run via `make test` or `pytest tests/ -v` from repo root.
"""
from __future__ import annotations

import pytest

from server.auto_resume import (
    EXIT_REASONS,
    SNAPSHOT_STALL_LIMIT,
    _classify_exit,
    _exponential_backoff,
    _jsonl_idle_seconds,
    _looks_rate_limited,
    _parse_reset_time,
    _push_hash_and_check_stall,
)


# ───────── _classify_exit ─────────

class TestClassifyExit:
    def test_exit_zero_is_clean(self):
        assert _classify_exit(0, "", "", "") == "clean"

    def test_auth_expired_takes_precedence(self):
        # Should win even if rate-limit hint is also present
        assert _classify_exit(1, "Unauthorized: please run /login", "rate limit", "") == "auth_expired"

    def test_context_full_classified(self):
        assert _classify_exit(1, "context window exceeded", "", "") == "context_full"
        assert _classify_exit(1, "prompt is too long for the model", "", "") == "context_full"

    def test_rate_limit_classified(self):
        assert _classify_exit(1, "5-hour limit reached", "", "") == "rate_limit"
        assert _classify_exit(1, "", "", "you have exceeded the usage limit") == "rate_limit"
        assert _classify_exit(1, "HTTP 429 Too Many Requests", "", "") == "rate_limit"

    def test_unknown_fallback(self):
        assert _classify_exit(139, "SIGSEGV", "", "") == "unknown"
        assert _classify_exit(2, "random error", "", "") == "unknown"

    def test_returns_only_valid_reason(self):
        for code in [0, 1, 2, 137, 139]:
            reason = _classify_exit(code, "noise", "noise", "noise")
            assert reason in EXIT_REASONS


# ───────── _parse_reset_time ─────────

class TestParseResetTime:
    def test_empty_returns_none(self, fixed_now):
        assert _parse_reset_time("", now_ts=fixed_now) is None
        assert _parse_reset_time("   ", now_ts=fixed_now) is None

    def test_relative_minutes(self, fixed_now):
        # "in 5 minutes" -> ~300s in future (returns epoch_ms)
        result = _parse_reset_time("try again in 5 minutes", now_ts=fixed_now)
        assert result is not None
        delta_sec = (result / 1000.0) - fixed_now
        assert 295 < delta_sec < 320  # 5min + safety margin

    def test_relative_seconds(self, fixed_now):
        result = _parse_reset_time("wait 30 seconds", now_ts=fixed_now)
        assert result is not None
        delta_sec = (result / 1000.0) - fixed_now
        assert 25 < delta_sec < 50

    def test_relative_hours(self, fixed_now):
        result = _parse_reset_time("try again in 2 hours", now_ts=fixed_now)
        assert result is not None
        delta_sec = (result / 1000.0) - fixed_now
        assert 7000 < delta_sec < 7300  # 2h ± margin

    def test_no_match_returns_none(self, fixed_now):
        assert _parse_reset_time("something completely unrelated", now_ts=fixed_now) is None


# ───────── _exponential_backoff ─────────

class TestExponentialBackoff:
    def test_first_attempt_is_base(self):
        # base = 60 (1m). attempt=1 -> 60*2^0 = 60
        assert _exponential_backoff(1) == 60

    def test_doubles_each_attempt(self):
        v1 = _exponential_backoff(1)
        v2 = _exponential_backoff(2)
        v3 = _exponential_backoff(3)
        assert v1 < v2 < v3
        assert v2 == v1 * 2
        assert v3 == v2 * 2

    def test_capped_at_30_min(self):
        # cap = 1800 (30m). attempt=10 capped, not 60*2^9=30720
        assert _exponential_backoff(10) == 1800
        assert _exponential_backoff(100) == 1800

    def test_attempt_lower_bound_clamped(self):
        # attempt < 1 normalized to 1
        assert _exponential_backoff(0) == 60
        assert _exponential_backoff(-5) == 60

    def test_monotone_until_cap(self):
        prev = 0
        for a in range(1, 20):
            v = _exponential_backoff(a)
            assert v >= prev
            prev = v


# ───────── _push_hash_and_check_stall ─────────

class TestPushHashStall:
    def test_first_call_records_no_stall(self):
        entry: dict = {}
        assert _push_hash_and_check_stall(entry, "h1") is False
        assert entry.get("snapshotHashes") == ["h1"]

    def test_repeated_same_hash_triggers_stall(self):
        entry: dict = {}
        # Up to SNAPSHOT_STALL_LIMIT identical hashes; the limit-th call signals stall
        results = []
        for _ in range(SNAPSHOT_STALL_LIMIT):
            results.append(_push_hash_and_check_stall(entry, "h1"))
        # The last one should be True (stall reached)
        assert results[-1] is True

    def test_different_hash_breaks_streak(self):
        entry: dict = {}
        _push_hash_and_check_stall(entry, "h1")
        _push_hash_and_check_stall(entry, "h1")
        # Different hash should NOT trigger stall
        assert _push_hash_and_check_stall(entry, "h2") is False

    def test_empty_hash_short_circuits(self):
        entry: dict = {"snapshotHashes": ["h1", "h1", "h1"]}
        # Empty fresh hash bails without stall signal
        assert _push_hash_and_check_stall(entry, "") is False

    def test_stall_limit_constant_present(self):
        # Sanity: constant is in a sensible range
        assert 2 <= SNAPSHOT_STALL_LIMIT <= 10


# ───────── _jsonl_idle_seconds & _looks_rate_limited ─────────

class TestJsonlHelpers:
    def test_idle_seconds_missing_file(self, tmp_path):
        missing = tmp_path / "does-not-exist.jsonl"
        assert _jsonl_idle_seconds(missing) == 0.0

    def test_idle_seconds_fresh_file(self, tmp_path):
        f = tmp_path / "fresh.jsonl"
        f.write_text("hello\n")
        idle = _jsonl_idle_seconds(f)
        assert 0.0 <= idle < 5.0

    def test_looks_rate_limited_true(self, tmp_path):
        f = tmp_path / "rl.jsonl"
        f.write_text(
            '{"role":"assistant","content":"You have hit the 5-hour limit."}\n'
        )
        assert _looks_rate_limited(f) is True

    def test_looks_rate_limited_false_on_normal(self, tmp_path):
        f = tmp_path / "ok.jsonl"
        f.write_text('{"role":"assistant","content":"Hello world."}\n')
        assert _looks_rate_limited(f) is False

    def test_looks_rate_limited_missing_file(self, tmp_path):
        f = tmp_path / "missing.jsonl"
        assert _looks_rate_limited(f) is False


# ───────── _process_one full lifecycle (integration) ─────────

class TestProcessOneLifecycle:
    """End-to-end: idle+rate-limited jsonl -> spawn fake claude -> STATE_DONE -> auto-disable."""

    def _setup(self, tmp_path, monkeypatch, claude_exit: int, claude_stderr: str = ""):
        import os
        import server.auto_resume as ar

        # Redirect on-disk state to tmp
        state_path = tmp_path / "auto-resume.json"
        monkeypatch.setattr(ar, "AUTO_RESUME_PATH", state_path)

        # Build a fake jsonl with rate-limit signature, mtime old enough
        # to trip idleSeconds gate
        cwd = tmp_path / "session-cwd"
        cwd.mkdir()
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            '{"role":"assistant","content":"5-hour limit reached, try again later"}\n'
        )
        old_mtime = time.time() - 600  # 10 min ago
        os.utime(jsonl, (old_mtime, old_mtime))

        # Stub out terminal liveness check (otherwise dead-tick logic kicks in)
        monkeypatch.setattr(ar, "_live_cli_sessions", lambda: {"sess-int-1": {}})

        # Fake `claude` binary as a shell script
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        fake_claude = fake_bin / "claude"
        if claude_exit == 0:
            fake_claude.write_text("#!/bin/sh\necho resumed-ok\nexit 0\n")
        else:
            fake_claude.write_text(
                f"#!/bin/sh\nprintf '%s' {claude_stderr!r} 1>&2\nexit {claude_exit}\n"
            )
        fake_claude.chmod(0o755)
        monkeypatch.setattr(ar, "_claude_bin", lambda: str(fake_claude))

        # Seed an enabled binding
        sid = "sess-int-1"
        store = {
            sid: {
                "sessionId": sid,
                "enabled": True,
                "cwd": str(cwd),
                "jsonlPath": str(jsonl),
                "prompt": "continue",
                "pollInterval": 60,
                "idleSeconds": 30,
                "maxAttempts": 5,
                "useContinue": False,
                "extraArgs": [],
                "installHooks": False,
                "createdAt": int(time.time() * 1000),
                "attempts": 0,
                "lastAttemptAt": 0,
                "nextAttemptAt": 0,
                "state": "watching",
                "snapshotHashes": [],
            }
        }
        ar._dump_all(store)
        return ar, sid

    def test_clean_exit_marks_done_and_disables(self, tmp_path, monkeypatch):
        ar, sid = self._setup(tmp_path, monkeypatch, claude_exit=0)
        ar._process_one(sid)
        store = ar._load_all()
        e = store[sid]
        assert e["state"] == "done", f"expected STATE_DONE, got {e['state']} err={e.get('lastError')}"
        assert e["lastExitCode"] == 0
        assert e["lastExitReason"] == "clean"
        assert e["attempts"] == 1
        assert e["nextAttemptAt"] == 0

    def test_rate_limit_exit_schedules_retry_keeps_enabled(self, tmp_path, monkeypatch):
        ar, sid = self._setup(
            tmp_path, monkeypatch, claude_exit=1,
            claude_stderr="HTTP 429 Too Many Requests",
        )
        ar._process_one(sid)
        store = ar._load_all()
        e = store[sid]
        assert e["lastExitReason"] == "rate_limit"
        assert e["enabled"] is True
        assert e["nextAttemptAt"] > 0
        assert e["attempts"] == 1

    def test_auth_expired_disables_permanently(self, tmp_path, monkeypatch):
        ar, sid = self._setup(
            tmp_path, monkeypatch, claude_exit=1,
            claude_stderr="Unauthorized: please run /login",
        )
        ar._process_one(sid)
        store = ar._load_all()
        e = store[sid]
        assert e["state"] == "failed"
        assert e["lastExitReason"] == "auth_expired"
        assert e["enabled"] is False


# Needed for the integration tests above
import time  # noqa: E402
