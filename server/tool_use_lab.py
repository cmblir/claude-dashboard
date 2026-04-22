"""Tool Use 플레이그라운드 — tool schema 정의 → Messages API 호출 → tool_use/tool_result 라운드 트립.

Stateless 한 턴 실행기. 프론트가 messages 배열을 유지하고, 본 모듈은
현재 상태에 기반한 한 턴만 수행한다.

기본 도구 템플릿 3종 제공: get_weather / calculator / web_search(mock).
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
    "CLAUDE_DASHBOARD_TOOL_USE_LAB",
    Path.home() / ".claude-dashboard-tool-use-lab.json",
)
_MAX_HISTORY = 20

TOOL_TEMPLATES: list[dict] = [
    {
        "id": "get_weather",
        "label": "get_weather",
        "description": "도시 이름으로 날씨 조회 (mock).",
        "tool": {
            "name": "get_weather",
            "description": "특정 도시의 현재 날씨를 조회합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "도시 이름 (예: 서울)"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"], "description": "온도 단위"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "id": "calculator",
        "label": "calculator",
        "description": "간단한 수식 계산.",
        "tool": {
            "name": "calculator",
            "description": "수식을 계산해 결과를 반환합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "계산할 수식 (예: 2+3*5)"},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "id": "web_search",
        "label": "web_search (mock)",
        "description": "웹 검색 시뮬레이션.",
        "tool": {
            "name": "web_search",
            "description": "키워드로 웹을 검색하고 상위 5건을 반환합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색어"},
                    "max_results": {"type": "integer", "description": "최대 결과 수", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
        },
    },
]


def _anthropic_key() -> str:
    keys = load_api_keys()
    val = keys.get("anthropic-api")
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("apiKey") or ""
    return ""


def _load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(_safe_read(HISTORY_PATH))
        if isinstance(data, list):
            return data[:_MAX_HISTORY]
    except Exception as e:
        log.warning("tool_use_lab history load failed: %s", e)
    return []


def _save_history(entry: dict) -> None:
    items = _load_history()
    items.insert(0, entry)
    items = items[:_MAX_HISTORY]
    try:
        _safe_write(HISTORY_PATH, json.dumps(items, ensure_ascii=False, indent=2))
    except Exception as e:
        log.warning("tool_use_lab history save failed: %s", e)


def api_tool_use_templates(_query: dict | None = None) -> dict:
    return {"templates": TOOL_TEMPLATES}


def api_tool_use_history(_query: dict | None = None) -> dict:
    return {"items": _load_history()}


def api_tool_use_turn(body: dict) -> dict:
    """현재 messages + tools 로 한 턴 실행. 반환: {assistant: {...}, stopReason: ...}"""
    import urllib.request
    import urllib.error

    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}

    model = (body.get("model") or "claude-sonnet-4-6").strip()
    max_tokens = int(body.get("maxTokens") or 2048)
    tools = body.get("tools") or []
    messages = body.get("messages") or []

    if not isinstance(tools, list) or not tools:
        return {"ok": False, "error": "tools required (non-empty list)"}
    if not isinstance(messages, list) or not messages:
        return {"ok": False, "error": "messages required (non-empty list)"}

    api_key = _anthropic_key()
    if not api_key:
        return {
            "ok": False,
            "needKey": True,
            "error": "ANTHROPIC_API_KEY 미설정 — aiProviders 탭에서 저장",
        }

    body_obj: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "tools": tools,
        "messages": messages,
    }

    t0 = int(time.time() * 1000)
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body_obj).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            err = (err_body.get("error") or {}).get("message") or f"HTTP {e.code}"
        except Exception:
            err = f"HTTP {e.code}"
        return {"ok": False, "error": err, "durationMs": int(time.time() * 1000) - t0}
    except Exception as e:
        return {"ok": False, "error": str(e), "durationMs": int(time.time() * 1000) - t0}

    duration = int(time.time() * 1000) - t0
    assistant_content = data.get("content") or []
    stop_reason = data.get("stop_reason") or ""
    usage = data.get("usage") or {}

    entry = {
        "id": f"tu-{uuid.uuid4().hex[:10]}",
        "ts": int(time.time()),
        "model": model,
        "stopReason": stop_reason,
        "durationMs": duration,
        "assistantContent": assistant_content,
        "usage": usage,
        "finalMessage": len(messages),
    }
    _save_history(entry)

    return {
        "ok": True,
        "model": model,
        "durationMs": duration,
        "assistantContent": assistant_content,
        "stopReason": stop_reason,
        "usage": usage,
    }
