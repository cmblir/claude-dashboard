#!/usr/bin/env python3
"""Claude Control Center — 엔트리포인트.

로컬 HTTP 서버 (stdlib only). 실제 로직은 `server/` 패키지 참조.
기동 순서: logging → .env 로드 → DB 초기화 → 세션 백그라운드 인덱스 →
MCP 캐시 warmup → ThreadingHTTPServer 시작.
"""
from __future__ import annotations

from http.server import ThreadingHTTPServer

from server.config import DB_PATH, DIST, get_bind
from server.db import _db_init
from server.logger import log, setup_logging
from server.mcp import warmup_caches
from server.routes import Handler
from server.sessions import background_index
from server.workflows import start_scheduler


def main() -> None:
    setup_logging()
    _db_init()
    background_index()
    warmup_caches()
    start_scheduler()
    host, port = get_bind()
    log.info("Serving http://%s:%s (dist=%s, db=%s)", host, port, DIST, DB_PATH)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
