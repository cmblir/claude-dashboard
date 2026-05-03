#!/usr/bin/env python3
"""Claude Control Center — 엔트리포인트.

로컬 HTTP 서버 (stdlib only). 실제 로직은 `server/` 패키지 참조.
기동 순서: 중복 체크 → logging → .env 로드 → DB 초기화 → 세션 백그라운드 인덱스 →
MCP 캐시 warmup → 스케줄러 → Ollama 자동 시작 → ThreadingHTTPServer 시작.
"""
from __future__ import annotations

import os
import signal
import socket
import sys
import threading
from http.server import ThreadingHTTPServer

from server.config import DB_PATH, DIST, get_bind
from server.db import _db_init
from server.logger import log, setup_logging
from server.mcp import warmup_caches
from server.routes import Handler
from server.sessions import background_index
from server.workflows import _migrate_runs_to_db, start_scheduler
from server.auto_resume import start_auto_resume
from server.hyper_agent_worker import start_hyper_agent_worker


# ───────── 중복 서버 방지 ─────────

def _check_port_available(host: str, port: int) -> bool:
    """포트가 사용 가능한지 확인. 이미 사용 중이면 False."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result != 0  # 0이면 이미 사용 중
    except Exception:
        return True


def _kill_existing_server(port: int) -> bool:
    """기존에 같은 포트를 사용하는 서버 프로세스를 종료. macOS/Linux 지원."""
    import subprocess
    try:
        # lsof 로 포트 사용 PID 찾기
        r = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
        )
        pids = [p.strip() for p in r.stdout.strip().split("\n") if p.strip()]
        my_pid = str(os.getpid())
        killed = 0
        for pid in pids:
            if pid == my_pid:
                continue
            try:
                os.kill(int(pid), signal.SIGTERM)
                killed += 1
                log.info("killed existing server process: PID %s", pid)
            except (ProcessLookupError, PermissionError):
                pass
        if killed:
            import time
            time.sleep(1)  # 프로세스 종료 대기
        return killed > 0
    except Exception:
        return False


# ───────── Ollama 자동 시작 (중복 방지) ─────────

def _auto_start_ollama() -> None:
    """Auto-start ollama serve — *opt-in only* since v2.59.0.

    Activation order (first match wins):
      1. Env var ``OLLAMA_AUTOSTART=1`` → start
      2. Quick-Settings ``behavior.autoStartOllama=true`` → start
      3. Otherwise → skip silently (the dashboard's Ollama tab still has
         a "Start serve" button for one-click manual start)

    The previous default (start unless explicitly disabled) surprised users
    by spawning ``ollama serve`` and consuming GPU/RAM. Inverting the
    default to opt-in matches the project's "no surprises" stance.
    """
    import shutil
    if not shutil.which("ollama"):
        return
    env_optin = os.environ.get("OLLAMA_AUTOSTART", "").strip().lower() in ("1", "true", "yes", "on")
    pref_optin = False
    if not env_optin:
        try:
            from server.prefs import api_prefs_get
            prefs = api_prefs_get({}) or {}
            beh = (prefs.get("prefs") or prefs).get("behavior") or {}
            pref_optin = beh.get("autoStartOllama") is True
        except Exception as e:
            log.debug("ollama auto-start pref check skipped: %s", e)
    if not (env_optin or pref_optin):
        log.info("ollama auto-start: skipped (set OLLAMA_AUTOSTART=1 or behavior.autoStartOllama=true to opt in)")
        return
    try:
        from server.ollama_hub import _is_ollama_reachable, api_ollama_serve_start
        if _is_ollama_reachable():
            log.info("ollama already running — skipping auto-start")
            return
        log.info("auto-starting ollama serve... (opt-in)")
        result = api_ollama_serve_start({})
        log.info("ollama auto-start: %s", result.get("status") or result.get("error"))
    except Exception as e:
        log.warning("ollama auto-start failed: %s", e)


# ───────── 메인 ─────────

_BOOT_TIMING: dict = {"startedAtMs": 0, "listeningAtMs": 0, "bootDurationMs": 0}


def get_boot_timing() -> dict:
    """Returns a snapshot of boot timing — used by /api/system/boot-timing."""
    return dict(_BOOT_TIMING)


def main() -> None:
    setup_logging()

    import time as _time
    _BOOT_TIMING["startedAtMs"] = int(_time.time() * 1000)
    _t0 = _time.time()

    host, port = get_bind()

    # 포트 중복 체크 — 이미 실행 중이면 기존 프로세스 종료
    if not _check_port_available(host, port):
        log.warning("port %d already in use — killing existing process", port)
        if _kill_existing_server(port):
            log.info("existing server killed, proceeding with startup")
        else:
            log.error("cannot free port %d — exiting", port)
            sys.exit(1)

    _db_init()
    # v2.46.0 — non-blocking boot: defer slow probes/scans to daemon threads
    # so the HTTP server starts listening within ~hundreds of ms instead of
    # waiting on session indexing (~seconds) and ollama HTTP probe (1–3 s).
    # v2.59.0 (G5) — also defer the runs migration; it's one-time and
    # post-migration is a single flag-check that doesn't block boot, but
    # first-boot-after-upgrade can be O(legacy_runs) so move it off the
    # critical path. Fresh runs already go straight to SQLite, so a
    # late-finishing migration doesn't change behaviour.
    threading.Thread(target=_migrate_runs_to_db, daemon=True, name="runs-migrate").start()
    threading.Thread(target=background_index, daemon=True, name="bg-index").start()
    # QQ137 — pre-warm the slow `<tool> --version` and `claude auth status`
    # subprocess fan-outs in a daemon thread so the first AI Providers / Team
    # tab visit hits the 30s memo (QQ135 / QQ136) instead of paying the cold
    # cost on the user's critical path.
    def _prewarm_subprocess_caches() -> None:
        try:
            from server.cli_tools import api_cli_status
            api_cli_status()
        except Exception:
            pass
        try:
            from server.auth import api_auth_status
            api_auth_status()
        except Exception:
            pass
    threading.Thread(
        target=_prewarm_subprocess_caches,
        daemon=True, name="prewarm-subprocs",
    ).start()
    warmup_caches()
    start_scheduler()
    start_auto_resume()
    start_hyper_agent_worker()
    # v2.59.0 (G5) — auto-start orchestrator sweeper. Zero-binding cost
    # is one config read per 60s, so safe to always start; bindings with
    # schedule.everyMinutes get fired automatically.
    try:
        from server.orchestrator import start_sweeper
        start_sweeper()
    except Exception as e:
        log.warning("orchestrator sweeper start failed: %s", e)
    threading.Thread(target=_auto_start_ollama, daemon=True, name="ollama-autostart").start()
    boot_ms = int((_time.time() - _t0) * 1000)
    _BOOT_TIMING["listeningAtMs"] = int(_time.time() * 1000)
    _BOOT_TIMING["bootDurationMs"] = boot_ms
    log.info("Serving http://%s:%s (dist=%s, db=%s) — boot %dms", host, port, DIST, DB_PATH, boot_ms)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
