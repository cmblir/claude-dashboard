"""모델 벤치마크 — 같은 프롬프트 셋을 여러 모델에 돌려 지연 · 토큰 · 비용 비교.

사용자가 사전 정의된 프롬프트 셋을 선택 → 모델 목록을 체크 → 실행 →
모델 × 프롬프트 매트릭스 + 집계 테이블 반환.

병렬 호출: prompt × model 조합을 ThreadPoolExecutor(max_workers=4) 로 실행.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .ai_keys import load_api_keys

# 기본 프롬프트 셋 (5종)
BENCH_SETS: list[dict] = [
    {
        "id": "basic-qa",
        "label": "기본 Q&A",
        "description": "짧은 지식 질문 5개.",
        "prompts": [
            "한국의 수도는?",
            "Python 의 GIL 을 1문장으로 설명.",
            "TCP 와 UDP 의 핵심 차이는?",
            "REST 와 GraphQL 중 CRUD 에 적합한 것은?",
            "프로세스와 스레드의 차이를 1줄로.",
        ],
    },
    {
        "id": "code-gen",
        "label": "코드 생성",
        "description": "간단한 코드 작성 3종.",
        "prompts": [
            "파이썬으로 1~N 까지 더하는 함수를 5줄 이내로 써줘.",
            "JavaScript 로 debounce 함수를 작성해줘.",
            "SQL 로 user 테이블의 id, email 을 email 기준 정렬.",
        ],
    },
    {
        "id": "reasoning",
        "label": "추론 / 수학",
        "description": "논리·수학 문제 3종.",
        "prompts": [
            "3명이 5분에 사과 3개를 먹는다. 10명이 사과 10개를 먹는 데 몇 분 걸리나?",
            "0.1 + 0.2 == 0.3 이 false 인 이유는?",
            "공장 A 가 B 보다 2배 빠르다. A 가 단독으로 만드는 데 6시간이면 둘이 함께는?",
        ],
    },
]

MODELS = [
    {"id": "claude-opus-4-7", "label": "Opus 4.7"},
    {"id": "claude-sonnet-4-6", "label": "Sonnet 4.6"},
    {"id": "claude-haiku-4-5", "label": "Haiku 4.5"},
]

# 가격 (per 1M tokens, USD) — prompt_cache.py 와 동기
_PRICING = {
    "claude-opus-4-7":    {"in": 15.0, "out": 75.0},
    "claude-sonnet-4-6":  {"in": 3.0,  "out": 15.0},
    "claude-haiku-4-5":   {"in": 0.8,  "out": 4.0},
}


def _anthropic_key() -> str:
    keys = load_api_keys()
    val = keys.get("anthropic-api")
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("apiKey") or ""
    return ""


def api_model_bench_sets(_query: dict | None = None) -> dict:
    return {"sets": BENCH_SETS, "models": MODELS}


def _call_once(api_key: str, model: str, prompt: str, max_tokens: int = 512) -> dict:
    import urllib.request
    import urllib.error

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    t0 = int(time.time() * 1000)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            ej = json.loads(e.read().decode("utf-8"))
            msg = (ej.get("error") or {}).get("message") or f"HTTP {e.code}"
        except Exception:
            msg = f"HTTP {e.code}"
        return {"ok": False, "model": model, "prompt": prompt, "error": msg, "durationMs": int(time.time()*1000)-t0}
    except Exception as e:
        return {"ok": False, "model": model, "prompt": prompt, "error": str(e), "durationMs": int(time.time()*1000)-t0}

    duration = int(time.time() * 1000) - t0
    text = ""
    for b in (data.get("content") or []):
        if isinstance(b, dict) and b.get("type") == "text":
            text += b.get("text", "")
    usage = data.get("usage") or {}
    price = _PRICING.get(model, {"in": 0, "out": 0})
    ti = usage.get("input_tokens", 0) or 0
    to_ = usage.get("output_tokens", 0) or 0
    cost = (ti / 1_000_000) * price["in"] + (to_ / 1_000_000) * price["out"]
    return {
        "ok": True,
        "model": model,
        "prompt": prompt,
        "output": text,
        "durationMs": duration,
        "inputTokens": ti,
        "outputTokens": to_,
        "usdCost": round(cost, 6),
    }


def api_model_bench_run(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}

    prompts = body.get("prompts") or []
    models = body.get("models") or []
    max_tokens = int(body.get("maxTokens") or 512)

    if not isinstance(prompts, list) or not prompts:
        return {"ok": False, "error": "prompts required"}
    if not isinstance(models, list) or not models:
        return {"ok": False, "error": "models required"}
    if len(prompts) > 20:
        return {"ok": False, "error": "prompts 최대 20 건"}
    valid_models = [m for m in models if m in {x["id"] for x in MODELS}]
    if not valid_models:
        return {"ok": False, "error": "유효한 모델 없음"}

    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True}

    tasks = [(m, p) for m in valid_models for p in prompts]

    t0 = int(time.time() * 1000)
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(_call_once, api_key, m, p, max_tokens) for m, p in tasks]
        for f in futures:
            try:
                results.append(f.result(timeout=120))
            except Exception as e:
                results.append({"ok": False, "error": str(e)})

    total_duration = int(time.time() * 1000) - t0

    # 집계 per model
    summary: dict[str, dict[str, Any]] = {}
    for m in valid_models:
        ms = [r for r in results if r.get("model") == m and r.get("ok")]
        if not ms:
            summary[m] = {"count": 0, "avgMs": 0, "totalCost": 0, "avgOut": 0}
            continue
        summary[m] = {
            "count": len(ms),
            "avgMs": round(sum(r.get("durationMs", 0) for r in ms) / len(ms)),
            "totalCost": round(sum(r.get("usdCost", 0) for r in ms), 6),
            "avgOut": round(sum(r.get("outputTokens", 0) for r in ms) / len(ms)),
        }

    return {
        "ok": True,
        "totalDurationMs": total_duration,
        "models": valid_models,
        "prompts": prompts,
        "results": results,
        "summary": summary,
    }
