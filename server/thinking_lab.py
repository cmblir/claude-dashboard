"""Extended Thinking 플레이그라운드 — Claude 의 reasoning block 을 분리 시각화.

Anthropic Messages API 의 `thinking: {type: "enabled", budget_tokens: N}` 를
활성화 → 응답 `content` 에서 `type:"thinking"` 블록과 `type:"text"` 블록을
분리해서 돌려준다. Opus 4.7 / Sonnet 4.6 지원, Haiku 는 비지원 경고.

히스토리: `~/.claude-dashboard-thinking-lab.json` (최근 20건)
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
    "CLAUDE_DASHBOARD_THINKING_LAB",
    Path.home() / ".claude-dashboard-thinking-lab.json",
)
_MAX_HISTORY = 20

THINKING_MODELS = [
    {"id": "claude-opus-4-7", "label": "Opus 4.7", "supported": True},
    {"id": "claude-sonnet-4-6", "label": "Sonnet 4.6", "supported": True},
    {"id": "claude-haiku-4-5", "label": "Haiku 4.5", "supported": False},
]

EXAMPLES: list[dict] = [
    {
        "id": "math-reasoning",
        "label": "수학 추론",
        "description": "복잡한 수식 단계를 thinking block 으로 확인.",
        "model": "claude-sonnet-4-6",
        "budgetTokens": 4096,
        "maxTokens": 2048,
        "prompt": "자동차가 시속 72km 로 출발해 30분마다 속도를 10% 씩 높이면 2시간 후 누적 주행거리는 몇 km 인가?",
    },
    {
        "id": "code-debug",
        "label": "코드 디버깅",
        "description": "버그 분석 과정 · 가설 검증 과정을 시각화.",
        "model": "claude-sonnet-4-6",
        "budgetTokens": 6000,
        "maxTokens": 2048,
        "prompt": "파이썬 dict 의 키 순서 보존은 어느 버전부터 공식 보증되는지, 그리고 왜 이전에는 안 됐는지 설명해줘.",
    },
    {
        "id": "plan-design",
        "label": "설계 플래닝",
        "description": "아키텍처 결정 과정을 thinking 에 노출.",
        "model": "claude-opus-4-7",
        "budgetTokens": 10000,
        "maxTokens": 3000,
        "prompt": "소규모 팀(5명)이 매일 10만 이벤트를 처리하는 실시간 알림 시스템을 만들려고 한다. SQS vs Kafka vs Redis Streams 중 어떤 선택이 적합한지 트레이드오프를 설계해서 답해줘.",
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
        log.warning("thinking_lab history load failed: %s", e)
    return []


def _save_history(entry: dict) -> None:
    items = _load_history()
    items.insert(0, entry)
    items = items[:_MAX_HISTORY]
    try:
        _safe_write(HISTORY_PATH, json.dumps(items, ensure_ascii=False, indent=2))
    except Exception as e:
        log.warning("thinking_lab history save failed: %s", e)


def _anthropic_key() -> str:
    keys = load_api_keys()
    val = keys.get("anthropic-api")
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("apiKey") or ""
    return ""


def api_thinking_lab_models(_query: dict | None = None) -> dict:
    return {"models": THINKING_MODELS}


def api_thinking_lab_examples(_query: dict | None = None) -> dict:
    return {"examples": EXAMPLES}


def api_thinking_lab_history(_query: dict | None = None) -> dict:
    return {"items": _load_history()}


def api_thinking_lab_test(body: dict) -> dict:
    import urllib.request
    import urllib.error

    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}

    model = (body.get("model") or "claude-sonnet-4-6").strip()
    budget = int(body.get("budgetTokens") or 4096)
    max_tokens = int(body.get("maxTokens") or 2048)
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return {"ok": False, "error": "prompt required"}

    # budget 범위 안전화
    budget = max(1024, min(32000, budget))
    # max_tokens 는 budget + 일부 여유
    if max_tokens <= budget:
        max_tokens = budget + 1024

    if "haiku" in model:
        return {
            "ok": False,
            "unsupported": True,
            "error": "Extended Thinking 은 Haiku 에서 지원되지 않습니다. Opus 또는 Sonnet 사용.",
        }

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
        "thinking": {"type": "enabled", "budget_tokens": budget},
        "messages": [{"role": "user", "content": prompt}],
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
        duration = int(time.time() * 1000) - t0
        entry = {
            "id": f"tl-{uuid.uuid4().hex[:10]}",
            "ts": int(time.time()),
            "model": model,
            "budgetTokens": budget,
            "status": "err",
            "error": err,
            "durationMs": duration,
            "prompt": prompt,
        }
        _save_history(entry)
        return {"ok": False, "error": err}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    duration = int(time.time() * 1000) - t0

    thinking_blocks: list[str] = []
    text_blocks: list[str] = []
    for block in (data.get("content") or []):
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "thinking":
            thinking_blocks.append(block.get("thinking") or "")
        elif btype == "text":
            text_blocks.append(block.get("text") or "")

    usage = data.get("usage") or {}
    entry = {
        "id": f"tl-{uuid.uuid4().hex[:10]}",
        "ts": int(time.time()),
        "model": model,
        "budgetTokens": budget,
        "status": "ok",
        "durationMs": duration,
        "usage": usage,
        "thinking": "\n\n───\n\n".join(thinking_blocks),
        "output": "".join(text_blocks),
        "prompt": prompt,
        "stopReason": data.get("stop_reason"),
    }
    _save_history(entry)

    return {
        "ok": True,
        "model": model,
        "budgetTokens": budget,
        "durationMs": duration,
        "usage": usage,
        "thinking": entry["thinking"],
        "output": entry["output"],
        "thinkingBlocks": len(thinking_blocks),
        "stopReason": entry["stopReason"],
    }
