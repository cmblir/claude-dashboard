"""표준 logging 설정 — 모든 server.* 모듈이 공용으로 쓰는 로거.

환경 변수 `LOG_LEVEL` 로 레벨 조정 (기본 INFO).
기존 `print("[server] ...")` 스타일을 대체한다.
"""
from __future__ import annotations

import logging
import os

_INITIALIZED = False


def setup_logging() -> None:
    """프로세스 시작 시 한 번 호출. 중복 호출은 무시."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    _INITIALIZED = True


# 루트 로거 — `log.info(...)`, `log.warning(...)` 로 사용.
log = logging.getLogger("dashboard")
