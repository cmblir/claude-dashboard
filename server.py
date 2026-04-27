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
from http.server import ThreadingHTTPServer

from server.config import DB_PATH, DIST, get_bind
from server.db import _db_init
from server.logger import log, setup_logging
from server.mcp import warmup_caches
from server.routes import Handler
from server.sessions import background_index
from server.workflows import start_scheduler
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
    """Ollama 가 설치되어 있고 아직 실행 중이 아니면 자동 시작."""
    import shutil
    if not shutil.which("ollama"):
        return
    try:
        from server.ollama_hub import _is_ollama_reachable, api_ollama_serve_start
        if _is_ollama_reachable():
            log.info("ollama already running — skipping auto-start")
            return
        log.info("auto-starting ollama serve...")
        result = api_ollama_serve_start({})
        log.info("ollama auto-start: %s", result.get("status") or result.get("error"))
    except Exception as e:
        log.warning("ollama auto-start failed: %s", e)


# ───────── 메인 ─────────

def main() -> None:
    setup_logging()

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
    background_index()
    warmup_caches()
    start_scheduler()
    start_auto_resume()
    start_hyper_agent_worker()
    _auto_start_ollama()
    log.info("Serving http://%s:%s (dist=%s, db=%s)", host, port, DIST, DB_PATH)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
