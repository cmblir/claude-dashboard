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


# --- Recommendations -----------------------------------------------------

# Map of stale model id substrings to their successor.
# Quality-only (not cost-based). Match is substring on the recorded model string.
_MODEL_SUCCESSORS = {
    "claude-3-sonnet": "claude-sonnet-4-6",
    "claude-3-haiku": "claude-haiku-4-5",
    "claude-3-opus": "claude-opus-4-7",
    "claude-3-5-sonnet": "claude-sonnet-4-6",
    "claude-3.5-sonnet": "claude-sonnet-4-6",
    "claude-sonnet-3-5": "claude-sonnet-4-6",
    "gpt-4-turbo": "gpt-4.1",
    "gpt-4-0": "gpt-4.1",
    "gpt-4 ": "gpt-4.1",
}


def _infer_provider(model: str) -> str:
    """Recover a provider hint from a bare model id when entries don't carry one."""
    m = (model or "").lower()
    if not m:
        return ""
    if "claude" in m:
        return "claude"
    if m.startswith("gpt") or "openai" in m:
        return "openai"
    if "gemini" in m:
        return "gemini"
    if "llama" in m or "mistral" in m or "ollama" in m or "qwen" in m:
        return "ollama"
    return ""


def _aggregate_by_model(entries: list[dict], window_days: int) -> dict[tuple, dict]:
    """Aggregate entries by (provider, model) over the trailing window."""
    import time
    cutoff = int(time.time()) - window_days * 86400
    agg: dict[tuple, dict] = {}
    for e in entries:
        if e.get("ts", 0) < cutoff:
            continue
        model = e.get("model") or ""
        if not model:
            continue
        provider = e.get("provider") or _infer_provider(model)
        key = (provider, model)
        b = agg.setdefault(key, {
            "provider": provider, "model": model,
            "total_cost": 0.0, "call_count": 0,
            "tokens_in_sum": 0, "tokens_out_sum": 0,
        })
        b["total_cost"] += float(e.get("usd") or 0.0)
        b["call_count"] += 1
        b["tokens_in_sum"] += int(e.get("tokensIn") or 0)
        b["tokens_out_sum"] += int(e.get("tokensOut") or 0)
    for b in agg.values():
        n = max(1, b["call_count"])
        b["avg_cost_per_call"] = round(b["total_cost"] / n, 6)
        b["avg_tokens_in"] = b["tokens_in_sum"] // n
        b["avg_tokens_out"] = b["tokens_out_sum"] // n
        b["total_cost"] = round(b["total_cost"], 6)
    return agg


def _recommendations(window_days: int = 30) -> dict:
    """Analyze last `window_days` of usage and return concrete swap recommendations.

    Rules:
      1. Sonnet/Opus + avg_tokens_in < 500 + call_count >= 10 → swap to Haiku (~85% saving)
      2. avg_tokens_in > 5000 + call_count >= 5 → enable prompt caching (~50% saving)
      3. call_count >= 100 + total_cost > $1 → try ollama local (~100% saving)
      4. Stale model in _MODEL_SUCCESSORS → upgrade for quality (no $ saving)
    """
    import time
    entries = _gather_all()
    agg = _aggregate_by_model(entries, window_days)

    total_cost = round(sum(b["total_cost"] for b in agg.values()), 6)
    recs: list[dict] = []

    for (provider, model), b in agg.items():
        mlow = model.lower()
        cc = b["call_count"]
        tcost = b["total_cost"]
        ati = b["avg_tokens_in"]

        # Rule 1 — Haiku for short prompts
        is_premium = ("sonnet" in mlow) or ("opus" in mlow)
        is_haiku_already = "haiku" in mlow
        if is_premium and not is_haiku_already and ati < 500 and cc >= 10:
            saving = round(tcost * 0.85, 6)
            recs.append({
                "ruleId": "haiku_for_short_prompts",
                "priority": 3,
                "currentModel": model,
                "currentProvider": provider,
                "currentCost": tcost,
                "suggestedModel": "claude-haiku-4-5",
                "estimatedSavings": saving,
                "callCount": cc,
                "rationale": (
                    f"평균 입력 토큰 {ati} (<500). 짧은 프롬프트에는 Haiku가 "
                    f"~15% 비용으로 충분합니다."
                ),
            })

        # Rule 2 — Cache long context
        if ati > 5000 and cc >= 5:
            saving = round(tcost * 0.5, 6)
            recs.append({
                "ruleId": "enable_prompt_caching",
                "priority": 2,
                "currentModel": model,
                "currentProvider": provider,
                "currentCost": tcost,
                "suggestedModel": model,  # same model, different config
                "estimatedSavings": saving,
                "callCount": cc,
                "rationale": (
                    f"평균 입력 토큰 {ati} (>5000). 프롬프트 캐싱을 활성화하면 "
                    f"캐시 워밍 후 입력 비용이 ~50% 감소합니다."
                ),
            })

        # Rule 3 — Local model for repetitive batch tasks
        is_ollama_already = (provider == "ollama") or ("ollama" in mlow) or ("llama" in mlow)
        if cc >= 100 and tcost > 1.0 and not is_ollama_already:
            saving = round(tcost * 1.0, 6)
            recs.append({
                "ruleId": "local_model_for_batch",
                "priority": 1,
                "currentModel": model,
                "currentProvider": provider,
                "currentCost": tcost,
                "suggestedModel": "ollama:llama3.1",
                "estimatedSavings": saving,
                "callCount": cc,
                "rationale": (
                    f"호출 {cc}회, 누적 ${tcost:.2f}. 반복적/배치성 작업이면 "
                    f"로컬 ollama 모델을 시도해보세요 (비용 $0)."
                ),
            })

        # Rule 4 — Stale model (quality, not cost)
        for stale_key, successor in _MODEL_SUCCESSORS.items():
            if stale_key in mlow:
                recs.append({
                    "ruleId": "stale_model_upgrade",
                    "priority": 4,
                    "currentModel": model,
                    "currentProvider": provider,
                    "currentCost": tcost,
                    "suggestedModel": successor,
                    "estimatedSavings": 0.0,
                    "callCount": cc,
                    "rationale": (
                        f"구버전 모델 사용 중. 품질 향상을 위해 {successor}로 "
                        f"업그레이드를 권장합니다."
                    ),
                })
                break

    # Sort by priority DESC then estimatedSavings DESC, cap at 20
    recs.sort(key=lambda r: (r["priority"], r["estimatedSavings"]), reverse=True)
    recs = recs[:20]

    est_total = round(sum(r["estimatedSavings"] for r in recs), 6)

    return {
        "ok": True,
        "windowDays": window_days,
        "computedAt": int(time.time() * 1000),
        "recommendations": recs,
        "totalCost30d": total_cost,
        "estimatedSavingsTotal": est_total,
    }


def api_cost_recommendations(query: dict | None = None) -> dict:
    """Public wrapper. Optional query.window (days, default 30, clamped 1..365)."""
    q = query or {}
    try:
        window = int(q.get("window") or 30)
    except (TypeError, ValueError):
        window = 30
    window = max(1, min(365, window))
    try:
        return _recommendations(window)
    except Exception as e:
        log.warning("cost recommendations failed: %s", e)
        return {"ok": False, "error": str(e)}


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
