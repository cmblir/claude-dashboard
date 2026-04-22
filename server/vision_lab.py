"""Vision / PDF 플레이그라운드 — 이미지 또는 PDF 를 3개 모델에 병렬 호출해 비교.

지원 입력:
- image/png, image/jpeg, image/webp, image/gif
- application/pdf

요청 블록:
- image: {"type":"image","source":{"type":"base64","media_type":"image/...","data":"..."}}
- pdf:   {"type":"document","source":{"type":"base64","media_type":"application/pdf","data":"..."}}

모델 병렬 호출은 threading.ThreadPoolExecutor (stdlib).
"""
from __future__ import annotations

import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .ai_keys import load_api_keys
from .logger import log

VISION_MODELS = ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"]
_MAX_MB = 10
_TIMEOUT = 120


def _anthropic_key() -> str:
    keys = load_api_keys()
    val = keys.get("anthropic-api")
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("apiKey") or ""
    return ""


def _build_content(media_type: str, b64_data: str, question: str) -> list[dict]:
    if media_type == "application/pdf":
        return [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64_data}},
            {"type": "text", "text": question},
        ]
    # 이미지
    return [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_data}},
        {"type": "text", "text": question},
    ]


def _call_one(
    model: str, api_key: str, content: list[dict], max_tokens: int = 1024,
) -> dict:
    import urllib.request
    import urllib.error

    body_obj = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
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
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            ej = json.loads(e.read().decode("utf-8"))
            msg = (ej.get("error") or {}).get("message") or f"HTTP {e.code}"
        except Exception:
            msg = f"HTTP {e.code}"
        return {"model": model, "ok": False, "error": msg, "durationMs": int(time.time()*1000)-t0}
    except Exception as e:
        return {"model": model, "ok": False, "error": str(e), "durationMs": int(time.time()*1000)-t0}

    duration = int(time.time() * 1000) - t0
    text = ""
    for b in (data.get("content") or []):
        if isinstance(b, dict) and b.get("type") == "text":
            text += b.get("text", "")
    return {
        "model": model,
        "ok": True,
        "output": text,
        "durationMs": duration,
        "usage": data.get("usage") or {},
    }


def api_vision_models(_query: dict | None = None) -> dict:
    return {"models": VISION_MODELS}


def api_vision_compare(body: dict) -> dict:
    """{media_type, base64, question, models?, maxTokens?} → 병렬 응답 비교."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}

    media_type = (body.get("mediaType") or "").strip()
    b64 = body.get("base64") or ""
    question = (body.get("question") or "").strip()
    models = body.get("models") or VISION_MODELS
    max_tokens = int(body.get("maxTokens") or 1024)

    allowed_types = {"image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"}
    if media_type not in allowed_types:
        return {"ok": False, "error": f"지원하지 않는 타입: {media_type}"}
    if not isinstance(b64, str) or not b64:
        return {"ok": False, "error": "base64 required"}
    if not question:
        return {"ok": False, "error": "question required"}

    # 크기 검증
    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception as e:
        return {"ok": False, "error": f"base64 decode failed: {e}"}
    if len(raw) > _MAX_MB * 1024 * 1024:
        return {"ok": False, "error": f"최대 {_MAX_MB}MB"}

    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True}

    # models 화이트리스트
    valid = [m for m in models if m in VISION_MODELS]
    if not valid:
        valid = VISION_MODELS

    content = _build_content(media_type, b64, question)

    # 병렬 호출 (최대 3)
    t0 = int(time.time() * 1000)
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(3, len(valid))) as ex:
        futures = [ex.submit(_call_one, m, api_key, content, max_tokens) for m in valid]
        for f in futures:
            try:
                results.append(f.result(timeout=_TIMEOUT))
            except Exception as e:
                results.append({"model": "?", "ok": False, "error": str(e)})

    total_duration = int(time.time() * 1000) - t0

    # 모델 순서 유지
    order_map = {r["model"]: r for r in results}
    ordered = [order_map[m] for m in valid if m in order_map]

    return {
        "ok": True,
        "totalDurationMs": total_duration,
        "mediaType": media_type,
        "question": question,
        "results": ordered,
    }
