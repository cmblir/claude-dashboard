"""Citations 플레이그라운드 — Anthropic Messages API citations.enabled 실습.

문서를 `content` 의 document 블록으로 전달 + `citations: {enabled: true}` 를
설정하면 응답 text block 에 `citations` 배열이 포함돼 정확한 인용 span 을
돌려준다.

히스토리: `~/.claude-dashboard-citations-lab.json` (최근 20건)
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
    "CLAUDE_DASHBOARD_CITATIONS_LAB",
    Path.home() / ".claude-dashboard-citations-lab.json",
)
_MAX_HISTORY = 20

EXAMPLES: list[dict] = [
    {
        "id": "company-overview",
        "label": "회사 소개문",
        "description": "짧은 회사 소개문에서 사실 추출 + 인용.",
        "model": "claude-sonnet-4-6",
        "document": (
            "Anthropic 은 2021년 샌프란시스코에서 설립된 AI 안전 연구 회사다. "
            "공동 창업자에는 전 OpenAI 연구진 다수가 포함됐다. 회사의 플래그십 모델은 Claude 이며, "
            "Opus / Sonnet / Haiku 3 티어로 제공된다. Anthropic 은 2024년 Amazon 으로부터 40억 달러 투자를 유치했고, "
            "Constitutional AI 접근법을 통해 유해 출력을 줄이는 방법을 연구한다."
        ),
        "title": "About Anthropic",
        "prompt": "이 회사의 핵심 특징과 투자 내역을 불릿 3개로 요약해줘. 인용을 활용.",
    },
    {
        "id": "tech-article",
        "label": "기술 아티클",
        "description": "기술 설명 글에서 구체 수치 추출.",
        "model": "claude-sonnet-4-6",
        "document": (
            "Prompt caching 은 반복되는 긴 컨텍스트(시스템 프롬프트, 도구 정의, 참조 문서)를 서버 측에 캐시해 "
            "재사용할 수 있게 하는 기능이다. 캐시 hit 시 input 토큰 단가의 10% 만 과금되고, "
            "캐시 생성 시에는 25% 추가 비용이 든다. 캐시 최소 크기는 모델별로 다르며, "
            "Opus/Sonnet 은 1024 토큰, Haiku 는 2048 토큰이다. TTL 은 기본 5분, 1시간 옵션도 있다."
        ),
        "title": "Prompt Caching 기초",
        "prompt": "캐시 hit 과 write 의 비용 차이, 그리고 최소 크기를 정리해줘.",
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
        log.warning("citations_lab history load failed: %s", e)
    return []


def _save_history(entry: dict) -> None:
    items = _load_history()
    items.insert(0, entry)
    items = items[:_MAX_HISTORY]
    try:
        _safe_write(HISTORY_PATH, json.dumps(items, ensure_ascii=False, indent=2))
    except Exception as e:
        log.warning("citations_lab history save failed: %s", e)


def api_citations_examples(_q: dict | None = None) -> dict:
    return {"examples": EXAMPLES}


def api_citations_history(_q: dict | None = None) -> dict:
    return {"items": _load_history()}


def api_citations_test(body: dict) -> dict:
    """{model, document, title?, prompt} → Messages API with citations enabled."""
    import urllib.request
    import urllib.error

    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}

    model = (body.get("model") or "claude-sonnet-4-6").strip()
    max_tokens = int(body.get("maxTokens") or 1024)
    document = (body.get("document") or "").strip()
    title = (body.get("title") or "").strip()
    prompt = (body.get("prompt") or "").strip()

    if not document:
        return {"ok": False, "error": "document required"}
    if not prompt:
        return {"ok": False, "error": "prompt required"}

    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True,
                "error": "ANTHROPIC_API_KEY 미설정 — aiProviders 탭에서 저장"}

    # citations 지원 content 블록 구조
    doc_block: dict[str, Any] = {
        "type": "document",
        "source": {"type": "text", "media_type": "text/plain", "data": document},
        "citations": {"enabled": True},
    }
    if title:
        doc_block["title"] = title

    body_obj = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "user", "content": [doc_block, {"type": "text", "text": prompt}]},
        ],
    }

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body_obj).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )

    t0 = int(time.time() * 1000)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            ej = json.loads(e.read().decode("utf-8"))
            msg = (ej.get("error") or {}).get("message") or f"HTTP {e.code}"
        except Exception:
            msg = f"HTTP {e.code}"
        return {"ok": False, "error": msg, "durationMs": int(time.time()*1000)-t0}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    duration = int(time.time() * 1000) - t0

    # content 블록 파싱 — text + citations 묶음 그대로 전달
    blocks = data.get("content") or []
    text_segments: list[dict] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            text_segments.append({
                "text": b.get("text") or "",
                "citations": b.get("citations") or [],
            })

    usage = data.get("usage") or {}
    entry = {
        "id": f"cit-{uuid.uuid4().hex[:10]}",
        "ts": int(time.time()),
        "model": model,
        "status": "ok",
        "durationMs": duration,
        "usage": usage,
        "stopReason": data.get("stop_reason"),
        "textSegments": text_segments,
        "document": document[:1000],  # 히스토리는 앞 1,000자만
        "title": title,
        "prompt": prompt,
    }
    _save_history(entry)

    return {
        "ok": True,
        "model": model,
        "durationMs": duration,
        "usage": usage,
        "textSegments": text_segments,
        "stopReason": data.get("stop_reason"),
    }
