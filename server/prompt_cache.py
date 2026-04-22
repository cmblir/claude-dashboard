"""Prompt Caching 플레이그라운드 — Anthropic Messages API cache_control 실험.

사용자가 system / tools / messages 의 각 블록에 `cache_control: ephemeral` 을
지정 → Messages API 호출 → `cache_creation_input_tokens`,
`cache_read_input_tokens` 를 UI 에 돌려준다.

히스토리: `~/.claude-dashboard-prompt-cache.json` (최근 20건)
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from .ai_keys import load_api_keys
from .config import _env_path
from .logger import log
from .utils import _safe_read, _safe_write

HISTORY_PATH = _env_path(
    "CLAUDE_DASHBOARD_PROMPT_CACHE",
    Path.home() / ".claude-dashboard-prompt-cache.json",
)
_MAX_HISTORY = 20

# 기본 예시 3종 — UI 첫 진입 시 보여줄 템플릿
EXAMPLES: list[dict] = [
    {
        "id": "system-prompt",
        "label": "시스템 프롬프트 캐시",
        "description": "대형 시스템 프롬프트를 캐시해 동일 대화 반복 시 비용 절감.",
        "model": "claude-sonnet-4-6",
        "maxTokens": 1024,
        "system": [
            {
                "type": "text",
                "text": (
                    "당신은 Claude 대시보드의 도우미입니다. "
                    "응답은 항상 한국어로 합니다. "
                    "코드는 ```로 감싸고 설명은 3줄 이내로 요약합니다. "
                    "이 시스템 프롬프트는 테스트용 고정 블록입니다. " * 40
                ),
                "cache_control": {"type": "ephemeral"},
            },
        ],
        "tools": [],
        "messages": [
            {"role": "user", "content": "오늘의 핵심 개념을 한 줄로 요약해줘."},
        ],
    },
    {
        "id": "document-cache",
        "label": "대용량 문서 캐시",
        "description": "긴 문서를 user 메시지로 첨부하고 캐시 → 추가 질문 시 재사용.",
        "model": "claude-sonnet-4-6",
        "maxTokens": 1024,
        "system": [],
        "tools": [],
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "다음 문서를 기반으로 답해주세요.\n\n"
                            "<document>\n"
                            + ("Claude API 는 Anthropic 의 고성능 LLM 접근 인터페이스입니다. " * 80)
                            + "\n</document>"
                        ),
                        "cache_control": {"type": "ephemeral"},
                    },
                    {"type": "text", "text": "문서의 핵심 주장을 2문장으로 요약해주세요."},
                ],
            },
        ],
    },
    {
        "id": "tools-cache",
        "label": "도구 정의 캐시",
        "description": "tool 정의를 캐시하면 같은 tools 세트를 반복 호출할 때 재활용.",
        "model": "claude-sonnet-4-6",
        "maxTokens": 1024,
        "system": [
            {"type": "text", "text": "당신은 여러 도구를 잘 쓰는 비서입니다."}
        ],
        "tools": [
            {
                "name": "get_weather",
                "description": "특정 도시의 날씨를 조회한다.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "도시 이름"},
                    },
                    "required": ["city"],
                },
                "cache_control": {"type": "ephemeral"},
            },
        ],
        "messages": [
            {"role": "user", "content": "서울 날씨 어때?"},
        ],
    },
]


def _load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(_safe_read(HISTORY_PATH))
        if isinstance(data, list):
            return data[:_MAX_HISTORY]
    except Exception as e:
        log.warning("prompt_cache history load failed: %s", e)
    return []


def _save_history(entry: dict) -> None:
    items = _load_history()
    items.insert(0, entry)
    items = items[:_MAX_HISTORY]
    try:
        _safe_write(HISTORY_PATH, json.dumps(items, ensure_ascii=False, indent=2))
    except Exception as e:
        log.warning("prompt_cache history save failed: %s", e)


def _anthropic_key() -> str:
    keys = load_api_keys()
    val = keys.get("anthropic-api")
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("apiKey") or ""
    return ""


def _call_messages_api(
    api_key: str,
    body_obj: dict,
    timeout: int = 60,
) -> tuple[int, dict]:
    """Messages API 호출. (status_code, json_body) 반환."""
    import urllib.request
    import urllib.error

    body = json.dumps(body_obj).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"error": {"message": f"HTTP {e.code}"}}
        return e.code, err
    except Exception as e:
        return 0, {"error": {"message": str(e)}}


# ───────── 비용 추정 ─────────
#
# Anthropic 공식 가격 (per 1M tokens, USD, 2026-04 기준):
#   opus-4-7   : input $15  / cache_write $18.75 / cache_read $1.5  / output $75
#   sonnet-4-6 : input $3   / cache_write $3.75  / cache_read $0.3  / output $15
#   haiku-4-5  : input $0.8 / cache_write $1.0   / cache_read $0.08 / output $4
_PRICING = {
    "claude-opus-4-7":    {"in": 15.0, "cw": 18.75, "cr": 1.50,  "out": 75.0},
    "claude-sonnet-4-6":  {"in": 3.0,  "cw": 3.75,  "cr": 0.30,  "out": 15.0},
    "claude-haiku-4-5":   {"in": 0.8,  "cw": 1.0,   "cr": 0.08,  "out": 4.0},
}


def _estimate_cost(model: str, usage: dict) -> dict:
    """usage dict → 비용 상세 (캐시 절감 계산 포함)."""
    price = None
    for mid, p in _PRICING.items():
        if mid in (model or ""):
            price = p
            break
    if not price:
        return {"usdTotal": 0.0, "usdSaved": 0.0, "note": "unknown-model"}

    ti = usage.get("input_tokens", 0) or 0
    to_ = usage.get("output_tokens", 0) or 0
    cw = usage.get("cache_creation_input_tokens", 0) or 0
    cr = usage.get("cache_read_input_tokens", 0) or 0

    cost_in = (ti / 1_000_000) * price["in"]
    cost_cw = (cw / 1_000_000) * price["cw"]
    cost_cr = (cr / 1_000_000) * price["cr"]
    cost_out = (to_ / 1_000_000) * price["out"]
    usd_total = cost_in + cost_cw + cost_cr + cost_out

    # 캐시 미사용 가정 비용: (ti + cw + cr) 전부를 input 단가로
    hypothetical = ((ti + cw + cr) / 1_000_000) * price["in"] + cost_out
    saved = max(0.0, hypothetical - usd_total)

    return {
        "usdInput": round(cost_in, 6),
        "usdCacheWrite": round(cost_cw, 6),
        "usdCacheRead": round(cost_cr, 6),
        "usdOutput": round(cost_out, 6),
        "usdTotal": round(usd_total, 6),
        "usdSaved": round(saved, 6),
    }


# ───────── API 엔드포인트 ─────────

def api_prompt_cache_examples(_query: dict | None = None) -> dict:
    return {"examples": EXAMPLES}


def api_prompt_cache_history(_query: dict | None = None) -> dict:
    return {"items": _load_history()}


def api_prompt_cache_test(body: dict) -> dict:
    """프롬프트 + cache_control 로 Messages API 호출 → usage 반환."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}

    model = (body.get("model") or "claude-sonnet-4-6").strip()
    max_tokens = int(body.get("maxTokens") or 1024)
    system = body.get("system") or []
    tools = body.get("tools") or []
    messages = body.get("messages") or []

    if not isinstance(messages, list) or not messages:
        return {"ok": False, "error": "messages required (list)"}

    api_key = _anthropic_key()
    if not api_key:
        return {
            "ok": False,
            "needKey": True,
            "error": "ANTHROPIC_API_KEY 미설정 — aiProviders 탭에서 저장하거나 환경변수 설정",
        }

    body_obj: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        body_obj["system"] = system
    if tools:
        body_obj["tools"] = tools

    t0 = int(time.time() * 1000)
    status, data = _call_messages_api(api_key, body_obj)
    duration = int(time.time() * 1000) - t0

    if status != 200:
        err = (data.get("error") or {}).get("message") or f"HTTP {status}"
        entry = {
            "id": f"pc-{uuid.uuid4().hex[:10]}",
            "ts": int(time.time()),
            "model": model,
            "status": "err",
            "error": err,
            "durationMs": duration,
            "request": body_obj,
        }
        _save_history(entry)
        return {"ok": False, "error": err, "status": status, "entry": entry}

    usage = data.get("usage") or {}
    text_blocks = [
        b.get("text", "")
        for b in (data.get("content") or [])
        if isinstance(b, dict) and b.get("type") == "text"
    ]
    cost = _estimate_cost(model, usage)

    entry = {
        "id": f"pc-{uuid.uuid4().hex[:10]}",
        "ts": int(time.time()),
        "model": model,
        "status": "ok",
        "durationMs": duration,
        "usage": usage,
        "cost": cost,
        "output": "".join(text_blocks),
        "request": body_obj,
        "raw": data,
    }
    _save_history(entry)

    return {
        "ok": True,
        "model": model,
        "durationMs": duration,
        "usage": usage,
        "cost": cost,
        "output": entry["output"],
        "entry": entry,
    }
