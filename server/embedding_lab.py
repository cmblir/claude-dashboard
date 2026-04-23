"""Embedding 비교 탭 — 같은 쿼리/문서 셋을 여러 프로바이더에 돌려 cosine rank 비교.

지원 프로바이더:
- voyage (Voyage AI · voyage-3-large)  — 별도 VOYAGE_API_KEY 필요
- openai-api (text-embedding-3-large / -small) — 기존 ai_providers 재사용
- ollama-api (bge-m3 등) — 로컬
"""
from __future__ import annotations

import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .ai_keys import load_api_keys
from .ai_providers import embed_with_provider
from .logger import log

# 프로바이더 카탈로그
PROVIDERS: list[dict] = [
    {
        "id": "voyage",
        "label": "Voyage AI",
        "icon": "🧭",
        "defaultModel": "voyage-3-large",
        "modelOptions": ["voyage-3-large", "voyage-3", "voyage-3-lite"],
        "keyEnv": "VOYAGE_API_KEY",
        "keyProviderId": "voyage",  # ai_keys 에 이 id 로 저장하도록 권장
    },
    {
        "id": "openai-api",
        "label": "OpenAI",
        "icon": "🤖",
        "defaultModel": "text-embedding-3-large",
        "modelOptions": ["text-embedding-3-large", "text-embedding-3-small"],
        "keyEnv": "OPENAI_API_KEY",
        "keyProviderId": "openai-api",
    },
    {
        "id": "ollama-api",
        "label": "Ollama (로컬)",
        "icon": "🦙",
        "defaultModel": "bge-m3",
        "modelOptions": ["bge-m3", "nomic-embed-text", "mxbai-embed-large"],
        "keyEnv": None,
        "keyProviderId": None,
    },
]

EXAMPLES: list[dict] = [
    {
        "id": "faq",
        "label": "FAQ 검색",
        "description": "질문 → 가장 관련 있는 FAQ 항목 랭킹.",
        "query": "대시보드 서버를 어떻게 다시 시작하나요?",
        "docs": [
            "서버 재시작: lsof -iTCP:8080 kill 후 python3 server.py 재실행",
            "Claude Code 플러그인 설치: 마켓플레이스 URL 추가 → toggle",
            "환경 변수 설정: envConfig 탭에서 ANTHROPIC_MODEL 등 수정",
            "API 키 저장: aiProviders 탭에서 저장-key 버튼",
            "워크플로우 생성: workflows 탭 → 새 워크플로우 + 템플릿",
        ],
    },
    {
        "id": "similar-sentences",
        "label": "유사 문장 찾기",
        "description": "쿼리와 가장 유사한 문장 랭킹.",
        "query": "고양이가 쥐를 쫓고 있다",
        "docs": [
            "The cat is chasing a mouse.",
            "The dog is barking at the mailman.",
            "A feline pursues a small rodent.",
            "Birds are singing in the morning.",
            "Kitty runs after a little mouse.",
        ],
    },
]


# ───────── cosine utilities ─────────

def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _rank_desc(scores: list[float]) -> list[int]:
    """scores[i] 에 대응하는 rank (1=가장 큼)."""
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    rank = [0] * len(scores)
    for r, idx in enumerate(order, 1):
        rank[idx] = r
    return rank


# ───────── Voyage 직접 호출 ─────────

def _voyage_key() -> str:
    keys = load_api_keys()
    v = keys.get("voyage")
    if isinstance(v, str) and v:
        return v
    if isinstance(v, dict):
        return v.get("apiKey") or ""
    return os.environ.get("VOYAGE_API_KEY", "")


def _voyage_embed(texts: list[str], model: str, input_type: str = "document") -> dict:
    import urllib.request
    import urllib.error

    key = _voyage_key()
    if not key:
        return {"ok": False, "needKey": True, "error": "VOYAGE_API_KEY 미설정"}
    body = {"model": model, "input": texts, "input_type": input_type}
    req = urllib.request.Request(
        "https://api.voyageai.com/v1/embeddings",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            d = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            ej = json.loads(e.read().decode("utf-8"))
            msg = (ej.get("error") or {}).get("message") or f"HTTP {e.code}"
        except Exception:
            msg = f"HTTP {e.code}"
        return {"ok": False, "error": msg}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    vecs = [row.get("embedding", []) for row in (d.get("data") or [])]
    return {"ok": True, "embeddings": vecs, "dimensions": len(vecs[0]) if vecs else 0}


# ───────── 통합 호출 ─────────

def _embed_one_provider(pid: str, model: str, query: str, docs: list[str]) -> dict:
    """query 먼저, docs N 개 embed. 실패하면 error 반환."""
    texts = [query] + list(docs)
    t0 = int(time.time() * 1000)
    if pid == "voyage":
        # Voyage 는 query/document type 분리 권장 — 단순화를 위해 모두 document 로 한 번에
        res = _voyage_embed(texts, model, input_type="document")
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error") or "voyage embed failed",
                    "needKey": res.get("needKey", False)}
        vectors = res.get("embeddings", [])
    else:
        r = embed_with_provider(pid, texts, model=model)
        if r.status != "ok":
            return {"ok": False, "error": r.error or "embed failed"}
        vectors = r.embeddings or []

    duration = int(time.time() * 1000) - t0
    if len(vectors) < 1 + len(docs):
        return {"ok": False, "error": f"기대 {1+len(docs)} 벡터, 수신 {len(vectors)}"}

    q_vec = vectors[0]
    doc_vecs = vectors[1:]
    sims = [_cosine(q_vec, v) for v in doc_vecs]
    ranks = _rank_desc(sims)
    dims = len(q_vec) if q_vec else 0

    return {
        "ok": True,
        "providerId": pid, "model": model,
        "dimensions": dims, "durationMs": duration,
        "sims": [round(s, 6) for s in sims],
        "ranks": ranks,
    }


# ───────── API 엔드포인트 ─────────

def api_embedding_providers(_q: dict | None = None) -> dict:
    # Voyage 는 key 상태 주석, OpenAI/Ollama 도 표시
    keys = load_api_keys()
    enriched = []
    for p in PROVIDERS:
        has_key = bool(keys.get(p["id"])) or (p["keyEnv"] and os.environ.get(p["keyEnv"]))
        enriched.append({**p, "available": bool(has_key) if p["id"] != "ollama-api" else True})
    return {"providers": enriched}


def api_embedding_examples(_q: dict | None = None) -> dict:
    return {"examples": EXAMPLES}


def api_embedding_compare(body: dict) -> dict:
    """{query, docs:[...], selections:[{providerId, model}]} → 각 프로바이더별 결과."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}

    query = (body.get("query") or "").strip()
    docs = body.get("docs") or []
    selections = body.get("selections") or []

    if not query:
        return {"ok": False, "error": "query required"}
    if not isinstance(docs, list) or not docs:
        return {"ok": False, "error": "docs required (non-empty list)"}
    if not isinstance(selections, list) or not selections:
        return {"ok": False, "error": "selections required"}

    docs = [d for d in docs if isinstance(d, str) and d.strip()][:10]
    if not docs:
        return {"ok": False, "error": "docs 유효한 항목 없음"}

    # 병렬 호출
    t0 = int(time.time() * 1000)
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(3, len(selections))) as ex:
        futs = [
            ex.submit(_embed_one_provider, s.get("providerId"), s.get("model"), query, docs)
            for s in selections
        ]
        for s, f in zip(selections, futs):
            try:
                res = f.result(timeout=90)
                res.setdefault("providerId", s.get("providerId"))
                res.setdefault("model", s.get("model"))
            except Exception as e:
                res = {"ok": False, "providerId": s.get("providerId"), "model": s.get("model"), "error": str(e)}
            results.append(res)

    return {
        "ok": True,
        "query": query, "docs": docs,
        "totalDurationMs": int(time.time() * 1000) - t0,
        "results": results,
    }
