"""비용 타임라인 통합 — 모든 플레이그라운드/워크플로우 히스토리를 aggregate.

소스:
- promptCache (history)
- thinkingLab (history)
- toolUseLab (history)
- batchJobs (history)
- apiFiles (history) - 사용량 미기록 시 skip
- visionLab (history) - 미기록 시 skip
- modelBench (history) - entry.usdCost per 응답
- serverTools (history)
- citationsLab (history)
- workflows costs (workflows store)

각 소스에서 (ts, source, usd, tokensIn, tokensOut, model) 튜플을 추출해
daily 집계 + source/model 별 집계를 반환.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .logger import log

# 가격표 — 추정 소스용 (source 엔트리에 usd 없으면 usage.tokens 로 계산)
_PRICING = {
    "claude-opus-4-7":    {"in": 15.0, "out": 75.0},
    "claude-sonnet-4-6":  {"in": 3.0,  "out": 15.0},
    "claude-haiku-4-5":   {"in": 0.8,  "out": 4.0},
}


def _estimate(model: str, ti: int, to: int) -> float:
    price = None
    for mid, p in _PRICING.items():
        if mid in (model or ""):
            price = p
            break
    if not price:
        return 0.0
    return (ti / 1_000_000) * price["in"] + (to / 1_000_000) * price["out"]


def _load(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("items") or []
    except Exception as e:
        log.warning("cost_timeline load failed (%s): %s", path, e)
    return []


def _coerce_entry(src: str, it: dict) -> dict | None:
    ts = it.get("ts") or 0
    if not ts:
        return None
    model = it.get("model") or ""
    usage = it.get("usage") or {}
    ti = usage.get("input_tokens") or it.get("inputTokens") or 0
    to = usage.get("output_tokens") or it.get("outputTokens") or 0
    cost_obj = it.get("cost") or {}
    usd = cost_obj.get("usdTotal")
    if usd is None:
        # modelBench 는 usdCost 필드를 사용
        usd = it.get("usdCost")
    if usd is None:
        usd = _estimate(model, ti, to)
    return {
        "ts": int(ts),
        "source": src,
        "model": model,
        "tokensIn": int(ti), "tokensOut": int(to),
        "usd": round(float(usd), 6),
        "status": it.get("status") or "ok",
    }


def _workflow_costs() -> list[dict]:
    """workflows store 의 costs 배열을 병합 (각 노드 실행 시 _record_workflow_cost 로 쌓임)."""
    from .workflows import _load_all as wf_load
    try:
        s = wf_load()
        raw = s.get("costs") or []
        out = []
        for row in raw:
            ts = row.get("ts") or 0
            if not ts:
                continue
            out.append({
                "ts": int(ts),
                "source": "workflows",
                "model": row.get("model") or "",
                "tokensIn": int(row.get("inputTok") or 0),
                "tokensOut": int(row.get("outputTok") or 0),
                "usd": round(float(row.get("usdEst") or 0), 6),
                "status": "ok",
            })
        return out
    except Exception as e:
        log.warning("workflow costs load failed: %s", e)
        return []


_SOURCES = [
    ("promptCache", ".claude-dashboard-prompt-cache.json"),
    ("thinkingLab", ".claude-dashboard-thinking-lab.json"),
    ("toolUseLab", ".claude-dashboard-tool-use-lab.json"),
    ("serverTools", ".claude-dashboard-server-tools.json"),
    ("citationsLab", ".claude-dashboard-citations-lab.json"),
    ("modelBench", ".claude-dashboard-model-bench.json"),
    # vision/files/batch/embedding 은 cost 필드 없는 경우 skip (0 으로 집계)
    ("visionLab", ".claude-dashboard-vision-lab.json"),
    ("apiFiles", ".claude-dashboard-api-files.json"),
]


def _gather_all() -> list[dict]:
    home = Path.home()
    entries: list[dict] = []
    for src, fname in _SOURCES:
        items = _load(home / fname)
        for it in items:
            e = _coerce_entry(src, it)
            if e:
                entries.append(e)
    entries.extend(_workflow_costs())
    entries.sort(key=lambda x: x["ts"], reverse=True)
    return entries


def _group_by_day(entries: list[dict]) -> list[dict]:
    """ts(초) → YYYY-MM-DD 별 합산."""
    import datetime as dt
    buckets: dict[str, dict] = {}
    for e in entries:
        d = dt.date.fromtimestamp(e["ts"]).isoformat()
        b = buckets.setdefault(d, {"day": d, "count": 0, "usd": 0.0, "sources": {}})
        b["count"] += 1
        b["usd"] = round(b["usd"] + e["usd"], 6)
        b["sources"][e["source"]] = round(b["sources"].get(e["source"], 0) + e["usd"], 6)
    return sorted(buckets.values(), key=lambda x: x["day"])


def _group_by_source(entries: list[dict]) -> list[dict]:
    buckets: dict[str, dict] = {}
    for e in entries:
        b = buckets.setdefault(e["source"], {"source": e["source"], "count": 0, "usd": 0.0, "tokensIn": 0, "tokensOut": 0})
        b["count"] += 1
        b["usd"] = round(b["usd"] + e["usd"], 6)
        b["tokensIn"] += e["tokensIn"]
        b["tokensOut"] += e["tokensOut"]
    return sorted(buckets.values(), key=lambda x: x["usd"], reverse=True)


def _group_by_model(entries: list[dict]) -> list[dict]:
    buckets: dict[str, dict] = {}
    for e in entries:
        key = e["model"] or "(unknown)"
        b = buckets.setdefault(key, {"model": key, "count": 0, "usd": 0.0})
        b["count"] += 1
        b["usd"] = round(b["usd"] + e["usd"], 6)
    return sorted(buckets.values(), key=lambda x: x["usd"], reverse=True)


def api_cost_timeline_summary(_q: dict | None = None) -> dict:
    entries = _gather_all()
    days = _group_by_day(entries)
    by_source = _group_by_source(entries)
    by_model = _group_by_model(entries)
    total_usd = round(sum(e["usd"] for e in entries), 6)
    total_count = len(entries)
    return {
        "ok": True,
        "totalUsd": total_usd,
        "totalCount": total_count,
        "days": days[-60:],  # 최근 60일만
        "bySource": by_source,
        "byModel": by_model[:20],
        "recent": entries[:30],  # 최신 30건 리스트
    }
