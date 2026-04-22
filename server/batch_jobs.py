"""Message Batches API 관리 — 대용량 배치 생성·상태 조회·결과 다운로드.

Anthropic Message Batches API 를 감싸는 얇은 프록시.
- 생성:     POST https://api.anthropic.com/v1/messages/batches
- 조회:     GET  /v1/messages/batches/{id}
- 결과:     GET  /v1/messages/batches/{id}/results   (JSONL stream)
- 목록:     GET  /v1/messages/batches
- 취소:     POST /v1/messages/batches/{id}/cancel

요청 수 한계: UI 에서 기본 100 건으로 경고. 하드 제한 없음.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from .ai_keys import load_api_keys
from .logger import log

_BASE = "https://api.anthropic.com/v1/messages/batches"
_TIMEOUT = 60

BATCH_EXAMPLES: list[dict] = [
    {
        "id": "qa-10",
        "label": "Q&A 10건",
        "description": "10개 질문을 Haiku 로 병렬 처리.",
        "model": "claude-haiku-4-5",
        "maxTokens": 256,
        "prompts": [
            "한국의 수도는?", "일본의 수도는?", "중국의 수도는?",
            "미국의 수도는?", "영국의 수도는?", "프랑스의 수도는?",
            "독일의 수도는?", "이탈리아의 수도는?", "스페인의 수도는?",
            "캐나다의 수도는?",
        ],
    },
    {
        "id": "summarize-5",
        "label": "요약 5건",
        "description": "각기 다른 짧은 문단 5개 요약.",
        "model": "claude-sonnet-4-6",
        "maxTokens": 128,
        "prompts": [
            "Claude 는 Anthropic 에서 만든 대규모 언어 모델이다. 그래서 뭘 잘해?",
            "파이썬 3.13 은 GIL 비활성화 옵션을 제공한다. 의미가 뭐야?",
            "Kubernetes 의 Deployment 와 StatefulSet 의 차이는?",
            "벡터 DB 가 RAG 에 쓰이는 이유는?",
            "CORS preflight 는 언제 발생해?",
        ],
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


def _request(method: str, url: str, api_key: str, body: dict | None = None) -> tuple[int, Any]:
    import urllib.request
    import urllib.error

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "message-batches-2024-09-24",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            # /results 엔드포인트는 JSONL 을 반환할 수 있음
            if method == "GET" and url.endswith("/results"):
                return resp.status, raw  # raw JSONL string
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode("utf-8")
            body_json = json.loads(body_text)
        except Exception:
            body_json = {"raw": body_text if "body_text" in locals() else ""}
        return e.code, body_json
    except Exception as e:
        return 0, {"error": {"message": str(e)}}


def api_batch_examples(_query: dict | None = None) -> dict:
    return {"examples": BATCH_EXAMPLES}


def api_batch_list(_query: dict | None = None) -> dict:
    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True, "data": []}
    status, data = _request("GET", _BASE, api_key)
    if status != 200:
        msg = (data.get("error") or {}).get("message") if isinstance(data, dict) else ""
        return {"ok": False, "error": msg or f"HTTP {status}"}
    return {"ok": True, "data": data.get("data") or []}


def api_batch_create(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}

    model = (body.get("model") or "claude-haiku-4-5").strip()
    max_tokens = int(body.get("maxTokens") or 256)
    prompts = body.get("prompts") or []

    if not isinstance(prompts, list) or not prompts:
        return {"ok": False, "error": "prompts required (non-empty list)"}
    if len(prompts) > 1000:
        return {"ok": False, "error": "prompts 최대 1000 건까지"}

    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True, "error": "ANTHROPIC_API_KEY 미설정"}

    requests_list = []
    for i, p in enumerate(prompts):
        if not isinstance(p, str) or not p.strip():
            continue
        requests_list.append({
            "custom_id": f"req-{i+1}-{uuid.uuid4().hex[:6]}",
            "params": {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": p}],
            },
        })

    if not requests_list:
        return {"ok": False, "error": "valid prompts required"}

    t0 = int(time.time() * 1000)
    status, data = _request("POST", _BASE, api_key, {"requests": requests_list})
    duration = int(time.time() * 1000) - t0

    if status not in (200, 201):
        msg = (data.get("error") or {}).get("message") if isinstance(data, dict) else ""
        return {"ok": False, "error": msg or f"HTTP {status}", "durationMs": duration}

    return {
        "ok": True,
        "batchId": data.get("id"),
        "status": data.get("processing_status") or data.get("status"),
        "createdAt": data.get("created_at"),
        "count": len(requests_list),
        "durationMs": duration,
        "raw": data,
    }


def api_batch_get(query: dict) -> dict:
    batch_id = (query.get("id", [""])[0] if isinstance(query, dict) else "").strip()
    if not batch_id:
        return {"ok": False, "error": "id required"}
    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True}
    status, data = _request("GET", f"{_BASE}/{batch_id}", api_key)
    if status != 200:
        msg = (data.get("error") or {}).get("message") if isinstance(data, dict) else ""
        return {"ok": False, "error": msg or f"HTTP {status}"}
    return {"ok": True, "batch": data}


def api_batch_results(query: dict) -> dict:
    batch_id = (query.get("id", [""])[0] if isinstance(query, dict) else "").strip()
    if not batch_id:
        return {"ok": False, "error": "id required"}
    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True}
    status, raw = _request("GET", f"{_BASE}/{batch_id}/results", api_key)
    if status != 200:
        if isinstance(raw, dict):
            msg = (raw.get("error") or {}).get("message") or ""
        else:
            msg = ""
        return {"ok": False, "error": msg or f"HTTP {status}"}
    # JSONL 파싱 시도
    items: list[dict] = []
    if isinstance(raw, str):
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception as e:
                log.warning("batch results parse error: %s", e)
    return {"ok": True, "items": items, "count": len(items)}


def api_batch_cancel(body: dict) -> dict:
    batch_id = (body or {}).get("id") if isinstance(body, dict) else ""
    if not batch_id:
        return {"ok": False, "error": "id required"}
    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True}
    status, data = _request("POST", f"{_BASE}/{batch_id}/cancel", api_key, {})
    if status != 200:
        msg = (data.get("error") or {}).get("message") if isinstance(data, dict) else ""
        return {"ok": False, "error": msg or f"HTTP {status}"}
    return {"ok": True, "batch": data}
