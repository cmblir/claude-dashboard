"""번역 캐시 · 대시보드 사용자 설정 파일 I/O.

- 번역 캐시: 스킬/에이전트/커맨드의 description 을 한국어로 번역한 결과 저장.
- 대시보드 설정: 사용자가 수동 지정한 플랜 등 (auth/status 응답에 사용).

여러 피처 모듈 (skills, agents, commands, auth) 이 공유하는 leaf 헬퍼.
"""
from __future__ import annotations

import json

from .config import DASHBOARD_CONFIG_PATH, TRANSLATIONS_PATH
from .utils import _safe_read, _safe_write


# ───────── 대시보드 설정 ─────────

def _load_dash_config() -> dict:
    if not DASHBOARD_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(_safe_read(DASHBOARD_CONFIG_PATH))
    except Exception:
        return {}


def _save_dash_config(cfg: dict) -> bool:
    return _safe_write(DASHBOARD_CONFIG_PATH, json.dumps(cfg, indent=2, ensure_ascii=False))


# ───────── 번역 캐시 ─────────

def _load_translation_cache() -> dict:
    if not TRANSLATIONS_PATH.exists():
        return {}
    try:
        return json.loads(_safe_read(TRANSLATIONS_PATH))
    except Exception:
        return {}


def _save_translation_cache(cache: dict) -> None:
    _safe_write(TRANSLATIONS_PATH, json.dumps(cache, ensure_ascii=False, indent=2))
