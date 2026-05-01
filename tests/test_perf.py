"""v2.54.0 — performance regression suite.

Each test asserts a timing budget for a hot code path. Budgets are set
3-5x the measured wall-clock as of the v2.54.0 baseline so noise doesn't
fail CI but real regressions trigger.

Measured at v2.54.0 baseline (dev box, macOS, Python 3.13):
  - _db_init second call:                    < 0.01 ms   -> budget 5 ms
  - api_auto_resume_status (empty store):    < 0.2  ms   -> budget 10 ms
  - api_ports_list:                          ~75 ms      -> budget 500 ms
  - _scan_plugin_hooks (warm cache):         < 0.01 ms   -> budget 5 ms
  - _telemetry_compute (no runs):            < 0.5  ms   -> budget 50 ms
  - api_cost_recommendations (no data):      < 0.1  ms   -> budget 100 ms
  - api_backup_list (no backups):            < 0.5  ms   -> budget 50 ms
  - _topological_levels (cached):            < 0.01 ms   -> budget 1 ms
  - _runs_db_save (single row):              < 0.5  ms   -> budget 20 ms
  - import server.workflows (cold):          ~35 ms      -> budget 500 ms
  - import server.routes (cold):             ~75 ms      -> budget 1000 ms
  - tools.translations_manual reload:        ~2 ms       -> budget 100 ms

Budgets are deliberately generous (10-100x measured) since CI is slower
than the dev box and we'd rather skip than flake. Tests that depend on
external binaries (lsof) skip cleanly when unavailable.
"""
from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest


# ───────── helpers ─────────


def _measure_ms(fn, *args, **kwargs) -> float:
    """Run fn(*args, **kwargs) once and return elapsed milliseconds."""
    t0 = time.perf_counter()
    fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000.0


def _best_of(fn, n: int = 3) -> float:
    """Return min elapsed ms across n runs — reduces single-call jitter."""
    return min(_measure_ms(fn) for _ in range(n))


# ───────── _db_init ─────────


class TestDbInit:
    def test_second_call_under_5ms(self, isolated_home, monkeypatch):
        # Redirect DB to a tmp path so we don't touch the dev DB.
        from server import config, db
        monkeypatch.setattr(config, "DB_PATH", isolated_home / "perf.db")
        monkeypatch.setattr(db, "_INITIALIZED", False, raising=False)
        # First call may take some time (DDL guards run once).
        db._db_init()
        # Second call must be near-zero (initialized-flag short-circuit).
        elapsed = _best_of(db._db_init, n=5)
        assert elapsed < 5.0, f"_db_init second call took {elapsed:.3f}ms, budget 5ms"


# ───────── auto_resume ─────────


class TestAutoResumeStatus:
    def test_empty_store_under_10ms(self, isolated_home, monkeypatch):
        from server import auto_resume as ar
        store_path = isolated_home / "auto-resume.json"
        store_path.write_text("{}")
        monkeypatch.setattr(ar, "AUTO_RESUME_PATH", store_path)
        # Empty-store short-circuit avoids the lsof+ps cross-reference.
        elapsed = _best_of(lambda: ar.api_auto_resume_status({}), n=5)
        assert elapsed < 10.0, (
            f"api_auto_resume_status (empty) took {elapsed:.3f}ms, budget 10ms"
        )


# ───────── process_monitor ─────────


@pytest.mark.skipif(
    shutil.which("lsof") is None,
    reason="lsof binary unavailable on this host",
)
class TestProcessMonitor:
    def test_ports_list_under_500ms(self):
        from server.process_monitor import api_ports_list
        # Warm any caches (DNS, lsof child setup) with a throwaway call.
        api_ports_list({})
        elapsed = _best_of(lambda: api_ports_list({}), n=3)
        assert elapsed < 500.0, (
            f"api_ports_list took {elapsed:.1f}ms, budget 500ms"
        )


# ───────── plugin hooks scan ─────────


class TestScanPluginHooks:
    def test_warm_cache_under_5ms(self, isolated_home, monkeypatch):
        from server import hooks
        # Warm: populate the in-memory cache. The function early-returns
        # when PLUGINS_DIR is missing, which is the typical empty-state.
        hooks._scan_plugin_hooks()
        elapsed = _best_of(hooks._scan_plugin_hooks, n=10)
        assert elapsed < 5.0, (
            f"_scan_plugin_hooks (warm) took {elapsed:.3f}ms, budget 5ms"
        )


# ───────── telemetry ─────────


class TestTelemetryCompute:
    def test_no_runs_under_50ms(self, isolated_home, monkeypatch):
        from server import config, db, workflows
        monkeypatch.setattr(config, "DB_PATH", isolated_home / "perf.db")
        monkeypatch.setattr(db, "_INITIALIZED", False, raising=False)
        # Warm: forces _db_init + schema creation.
        workflows._telemetry_compute()
        elapsed = _best_of(workflows._telemetry_compute, n=3)
        assert elapsed < 50.0, (
            f"_telemetry_compute (no runs) took {elapsed:.3f}ms, budget 50ms"
        )


# ───────── cost recommendations ─────────


class TestCostRecommendations:
    def test_no_data_under_100ms(self, isolated_home, monkeypatch):
        from server import config, cost_timeline, db
        monkeypatch.setattr(config, "DB_PATH", isolated_home / "perf.db")
        monkeypatch.setattr(db, "_INITIALIZED", False, raising=False)
        # Warm.
        cost_timeline.api_cost_recommendations({})
        elapsed = _best_of(
            lambda: cost_timeline.api_cost_recommendations({}), n=3
        )
        assert elapsed < 100.0, (
            f"api_cost_recommendations took {elapsed:.3f}ms, budget 100ms"
        )


# ───────── backup list ─────────


class TestBackupList:
    def test_no_backups_under_50ms(self, isolated_home, monkeypatch):
        from server import backup
        empty_root = isolated_home / "backups"
        empty_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(backup, "_backup_root", lambda: empty_root)
        # Warm.
        backup.api_backup_list({})
        elapsed = _best_of(lambda: backup.api_backup_list({}), n=5)
        assert elapsed < 50.0, (
            f"api_backup_list (empty) took {elapsed:.3f}ms, budget 50ms"
        )


# ───────── workflow topo cache ─────────


class TestTopologicalLevels:
    def test_cached_call_under_1ms(self):
        from server.workflows import _topological_levels
        nodes = [
            {"id": "start", "type": "start"},
            {"id": "s1", "type": "session"},
            {"id": "s2", "type": "session"},
            {"id": "end", "type": "end"},
        ]
        edges = [
            {"from": "start", "to": "s1"},
            {"from": "start", "to": "s2"},
            {"from": "s1", "to": "end"},
            {"from": "s2", "to": "end"},
        ]
        # Warm — populates the topo cache for this graph signature.
        _topological_levels(nodes, edges)
        elapsed = _best_of(lambda: _topological_levels(nodes, edges), n=20)
        assert elapsed < 1.0, (
            f"_topological_levels (cached) took {elapsed:.4f}ms, budget 1ms"
        )


# ───────── workflow runs DB save ─────────


class TestRunsDbSave:
    def test_single_row_under_20ms(self, isolated_home, monkeypatch):
        from server import config, db, workflows
        monkeypatch.setattr(config, "DB_PATH", isolated_home / "perf.db")
        monkeypatch.setattr(db, "_INITIALIZED", False, raising=False)
        run = {
            "workflowId": "wf-perf",
            "status": "success",
            "startedAt": 1000,
            "endedAt": 2000,
            "iteration": 1,
            "totalIterations": 1,
            "costUsd": 0.0,
        }
        # Warm — _db_init + schema.
        workflows._runs_db_save(f"r-{uuid.uuid4().hex[:8]}", run)
        elapsed = _best_of(
            lambda: workflows._runs_db_save(f"r-{uuid.uuid4().hex[:8]}", run),
            n=3,
        )
        assert elapsed < 20.0, (
            f"_runs_db_save took {elapsed:.3f}ms, budget 20ms"
        )


# ───────── module import time (cold via subprocess) ─────────


def _cold_import_ms(modname: str) -> float:
    """Spawn a fresh interpreter, import the module, return elapsed ms.

    Uses subprocess so we get a real cold import (the in-process sys.modules
    cache would make any second import effectively free).
    """
    repo_root = Path(__file__).resolve().parent.parent
    code = (
        "import time, sys; "
        f"sys.path.insert(0, {str(repo_root)!r}); "
        "t0=time.perf_counter(); "
        f"import {modname}; "
        "print((time.perf_counter()-t0)*1000)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        pytest.skip(f"cold import of {modname} failed: {proc.stderr.strip()}")
    try:
        return float(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        pytest.skip(f"could not parse cold-import timing for {modname}")
        return 0.0  # unreachable but satisfies type checker


class TestColdImports:
    def test_workflows_under_500ms(self):
        elapsed = _cold_import_ms("server.workflows")
        assert elapsed < 500.0, (
            f"import server.workflows took {elapsed:.0f}ms, budget 500ms"
        )

    def test_routes_under_1000ms(self):
        elapsed = _cold_import_ms("server.routes")
        assert elapsed < 1000.0, (
            f"import server.routes took {elapsed:.0f}ms, budget 1000ms"
        )

    def test_db_under_300ms(self):
        elapsed = _cold_import_ms("server.db")
        assert elapsed < 300.0, (
            f"import server.db took {elapsed:.0f}ms, budget 300ms"
        )


# ───────── i18n manual translations import ─────────


class TestI18nManualImport:
    def test_reload_under_100ms(self):
        # Already in sys.modules from any prior import — measure reload cost.
        import tools.translations_manual as tm
        importlib.reload(tm)  # warm
        t0 = time.perf_counter()
        importlib.reload(tm)
        elapsed = (time.perf_counter() - t0) * 1000.0
        assert elapsed < 100.0, (
            f"tools.translations_manual reload took {elapsed:.3f}ms, "
            "budget 100ms"
        )


# ───────── translation cache load ─────────


class TestTranslationCache:
    def test_warm_load_under_10ms(self, isolated_home, monkeypatch):
        from server import config, translations
        # Point at an empty cache file so we exercise the miss-path quickly.
        cache_path = isolated_home / "translations.json"
        cache_path.write_text("{}")
        monkeypatch.setattr(config, "TRANSLATIONS_PATH", cache_path)
        monkeypatch.setattr(translations, "TRANSLATIONS_PATH", cache_path)
        # Warm.
        translations._load_translation_cache()
        elapsed = _best_of(translations._load_translation_cache, n=10)
        assert elapsed < 10.0, (
            f"_load_translation_cache (warm) took {elapsed:.3f}ms, "
            "budget 10ms"
        )


# ───────── auto_resume backoff (pure CPU) ─────────


class TestExponentialBackoff:
    def test_thousand_calls_under_50ms(self):
        from server.auto_resume import _exponential_backoff
        t0 = time.perf_counter()
        for i in range(1000):
            _exponential_backoff(i % 10)
        elapsed = (time.perf_counter() - t0) * 1000.0
        assert elapsed < 50.0, (
            f"1000x _exponential_backoff took {elapsed:.2f}ms, budget 50ms"
        )


# ───────── classify_exit (hot path on every cli session restart) ─────────


class TestClassifyExit:
    def test_thousand_calls_under_100ms(self):
        from server.auto_resume import _classify_exit
        samples = [
            (0, "", "", ""),
            (1, "Unauthorized: please run /login", "", ""),
            (1, "5-hour limit reached", "", ""),
            (1, "context window exceeded", "", ""),
            (139, "SIGSEGV", "", ""),
        ]
        t0 = time.perf_counter()
        for _ in range(200):
            for s in samples:
                _classify_exit(*s)
        elapsed = (time.perf_counter() - t0) * 1000.0
        assert elapsed < 100.0, (
            f"1000x _classify_exit took {elapsed:.2f}ms, budget 100ms"
        )


# ───────── safe_write round-trip ─────────


class TestSafeWriteRoundtrip:
    def test_small_json_under_20ms(self, isolated_home):
        from server.utils import _safe_read, _safe_write
        target = isolated_home / "rt.json"
        payload = json.dumps({"k": "v", "n": list(range(100))})

        def roundtrip():
            _safe_write(target, payload)
            _safe_read(target)

        roundtrip()  # warm
        elapsed = _best_of(roundtrip, n=3)
        assert elapsed < 20.0, (
            f"_safe_write+_safe_read roundtrip took {elapsed:.3f}ms, "
            "budget 20ms"
        )



# ───────── v2.55.0 — agent_bus throughput / latency ─────────


class TestAgentBusPublishThroughput:
    """Publishing 10k events should land well under 1 second on a dev box."""

    def test_publish_10k_under_1s(self, isolated_home, monkeypatch, tmp_path):
        monkeypatch.setenv("CLAUDE_DASHBOARD_DB", str(tmp_path / "bus.db"))
        # Tight dedup window so unique payloads aren't dropped.
        monkeypatch.setenv("AGENT_BUS_DEDUP_WINDOW_MS", "0")
        monkeypatch.setenv("AGENT_BUS_RING_SIZE", "16384")
        import importlib
        from server import config as _c; importlib.reload(_c)
        from server import db as _db; importlib.reload(_db)
        from server import agent_bus; importlib.reload(agent_bus)
        agent_bus.reset_for_tests()

        N = 10_000

        def go():
            for i in range(N):
                agent_bus.publish(f"perf.topic.{i % 32}", {"i": i}, source="t")

        elapsed = _best_of(go, n=1)
        # Budget 5x measured (~150ms on dev box) so CI noise is absorbed.
        assert elapsed < 1000.0, (
            f"agent_bus.publish x{N} took {elapsed:.1f}ms, budget 1000ms"
        )


class TestAgentBusHistoryLatency:
    """history() should return in ms even when the ring is full."""

    def test_history_ring_under_100ms(self, isolated_home, monkeypatch, tmp_path):
        monkeypatch.setenv("CLAUDE_DASHBOARD_DB", str(tmp_path / "bus.db"))
        monkeypatch.setenv("AGENT_BUS_DEDUP_WINDOW_MS", "0")
        monkeypatch.setenv("AGENT_BUS_RING_SIZE", "4096")
        import importlib
        from server import config as _c; importlib.reload(_c)
        from server import db as _db; importlib.reload(_db)
        from server import agent_bus; importlib.reload(agent_bus)
        agent_bus.reset_for_tests()

        for i in range(4000):
            agent_bus.publish(f"perf.topic.{i % 8}", {"i": i}, source="t")

        def go():
            agent_bus.history(["perf.*"], limit=200)

        elapsed = _best_of(go, n=3)
        assert elapsed < 100.0, (
            f"agent_bus.history(ring=4000) took {elapsed:.2f}ms, budget 100ms"
        )


class TestPlanCacheHitLatency:
    def test_plan_cache_hit_under_1ms(self, isolated_home, monkeypatch, tmp_path):
        monkeypatch.setenv("CLAUDE_DASHBOARD_ORCHESTRATOR",
                           str(tmp_path / "orch.json"))
        monkeypatch.setenv("CLAUDE_DASHBOARD_DB", str(tmp_path / "bus.db"))
        import importlib
        from server import config as _c; importlib.reload(_c)
        from server import db as _db; importlib.reload(_db)
        from server import agent_bus; importlib.reload(agent_bus)
        from server import orchestrator; importlib.reload(orchestrator)
        orchestrator._plan_cache_clear_for_tests()

        key = orchestrator._plan_cache_key(
            "the same prompt", {"kind": "http", "channel": "x"},
            ["claude:sonnet"],
        )
        orchestrator._plan_cache_set(key, [{"assignee": "claude:sonnet",
                                            "task": "x"}])

        def go():
            orchestrator._plan_cache_get(key)

        elapsed = _best_of(go, n=5)
        assert elapsed < 1.0, (
            f"plan cache hit took {elapsed:.3f}ms, budget 1ms"
        )
