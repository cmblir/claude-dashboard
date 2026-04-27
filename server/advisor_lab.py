"""Advisor Tool playground — pair a fast/cheap *executor* with a smart/expensive
*advisor* model and surface the round-trip + cost/quality delta.

Sequence per request:
  1. POST executor with the user's prompt.
  2. POST advisor with a system prompt that says "review the executor draft"
     plus the original prompt and the executor's output as context.
  3. Compute a delta (token diff, cost diff, latency diff) and store both
     responses in history.

Storage: ``~/.claude-dashboard-advisor-lab.json`` (history, ≤50).
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
    "CLAUDE_DASHBOARD_ADVISOR_LAB",
    Path.home() / ".claude-dashboard-advisor-lab.json",
)
_MAX_HISTORY = 50

EXECUTORS = ["claude-haiku-4-5", "claude-sonnet-4-5", "claude-sonnet-4-6"]
ADVISORS  = ["claude-opus-4-6", "claude-opus-4-7"]
# (input, output) USD per 1M tokens
_PRICES = {
    "claude-haiku-4-5":  (1.0, 5.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-6":   (15.0, 75.0),
    "claude-opus-4-7":   (15.0, 75.0),
}

EXAMPLES: list[dict] = [
    {"id": "code-review", "title": "코드 리뷰",
     "prompt": "Review this Python: ```def merge(a,b): return list(set(a+b))```. Edge cases? Performance? Style?"},
    {"id": "edge-cases",  "title": "엣지 케이스 열거",
     "prompt": "List every edge case for a function that converts a phone number string into E.164 format."},
    {"id": "design-call", "title": "설계 결정",
     "prompt": "Should we use SQS, Kafka, or Redis Streams for 100k events/day? Justify with trade-offs."},
    {"id": "math-step",   "title": "다단계 추론",
     "prompt": "A car starts at 72 km/h and increases speed 10% every 30 min. Total distance after 2 hours?"},
    {"id": "summary-chk", "title": "요약 검증",
     "prompt": "Summarise the trade-offs of monorepo vs polyrepo in <60 words. Then audit the summary for missing items."},
]

_ADVISOR_SYS = (
    "You are an advisor reviewing an executor's draft answer to a user "
    "request. The user's original request and the executor's draft follow. "
    "If the draft is correct and complete, sign off in 1-2 sentences. "
    "Otherwise, critique briefly and provide an improved answer."
)


def _load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(_safe_read(HISTORY_PATH) or "[]")
        if isinstance(data, list):
            return data[:_MAX_HISTORY]
    except Exception as e:
        log.warning("advisor_lab history load failed: %s", e)
    return []


def _save_history(entry: dict) -> None:
    items = _load_history()
    items.insert(0, entry)
    items = items[:_MAX_HISTORY]
    try:
        _safe_write(HISTORY_PATH, json.dumps(items, ensure_ascii=False, indent=2))
    except Exception as e:
        log.warning("advisor_lab history save failed: %s", e)


def _anthropic_key() -> str:
    keys = load_api_keys()
    val = keys.get("anthropic-api")
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("apiKey") or ""
    return ""


def _cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    pi, po = _PRICES.get(model, (3.0, 15.0))
    return round((tokens_in * pi + tokens_out * po) / 1_000_000, 4)


def _call_anthropic(api_key: str, body: dict, timeout: int = 90) -> tuple[dict | None, str, int]:
    import urllib.request
    import urllib.error
    t0 = int(time.time() * 1000)
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data, "", int(time.time() * 1000) - t0
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            err = (err_body.get("error") or {}).get("message") or f"HTTP {e.code}"
        except Exception:
            err = f"HTTP {e.code}"
        return None, err, int(time.time() * 1000) - t0
    except Exception as e:
        return None, str(e), int(time.time() * 1000) - t0


def _extract_text(data: dict | None) -> str:
    if not data:
        return ""
    return "".join(b.get("text", "") for b in (data.get("content") or [])
                   if isinstance(b, dict) and b.get("type") == "text")


def _summarise(model: str, data: dict | None, duration_ms: int) -> dict:
    usage = (data or {}).get("usage") or {}
    tin = int(usage.get("input_tokens") or 0)
    tout = int(usage.get("output_tokens") or 0)
    return {
        "model":     model,
        "response":  _extract_text(data),
        "tokensIn":  tin,
        "tokensOut": tout,
        "costUsd":   _cost_usd(model, tin, tout),
        "durationMs": duration_ms,
    }


# ───────── HTTP handlers ─────────

def api_advisor_lab_models(_query: dict | None = None) -> dict:
    return {"executors": EXECUTORS, "advisors": ADVISORS}


def api_advisor_lab_examples(_query: dict | None = None) -> dict:
    return {"examples": EXAMPLES, "executors": EXECUTORS, "advisors": ADVISORS}


def api_advisor_lab_history(_query: dict | None = None) -> dict:
    return {"items": _load_history()}


def api_advisor_lab_run(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}
    prompt = (body.get("prompt") or "").strip()[:8000]
    if not prompt:
        return {"ok": False, "error": "prompt required"}
    executor = (body.get("executor") or "claude-haiku-4-5").strip()
    advisor  = (body.get("advisor")  or "claude-opus-4-7").strip()
    if executor not in EXECUTORS:
        executor = "claude-haiku-4-5"
    if advisor not in ADVISORS:
        advisor = "claude-opus-4-7"
    max_tokens = max(256, min(int(body.get("maxTokens") or 2048), 16384))

    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True,
                "error": "ANTHROPIC_API_KEY missing — set in aiProviders tab"}

    # 1) Executor pass
    exec_body = {
        "model":      executor,
        "max_tokens": max_tokens,
        "messages":   [{"role": "user", "content": prompt}],
    }
    exec_data, exec_err, exec_dur = _call_anthropic(api_key, exec_body, timeout=90)
    exec_summary = _summarise(executor, exec_data, exec_dur)
    if exec_err:
        return {"ok": False, "stage": "executor", "error": exec_err,
                "executor": exec_summary}

    # 2) Advisor pass — review the executor's draft
    advisor_body = {
        "model":      advisor,
        "max_tokens": max_tokens,
        "system":     _ADVISOR_SYS,
        "messages": [{
            "role": "user",
            "content": f"User request:\n{prompt}\n\nExecutor draft:\n{exec_summary['response']}",
        }],
    }
    adv_data, adv_err, adv_dur = _call_anthropic(api_key, advisor_body, timeout=120)
    adv_summary = _summarise(advisor, adv_data, adv_dur)
    if adv_err:
        return {"ok": False, "stage": "advisor", "error": adv_err,
                "executor": exec_summary, "advisor": adv_summary}

    delta = {
        "tokensDiff":  (adv_summary["tokensIn"] + adv_summary["tokensOut"])
                       - (exec_summary["tokensIn"] + exec_summary["tokensOut"]),
        "costDiff":    round(adv_summary["costUsd"] - exec_summary["costUsd"], 4),
        "latencyDiff": adv_summary["durationMs"] - exec_summary["durationMs"],
    }

    entry = {
        "id":         f"al-{uuid.uuid4().hex[:10]}",
        "ts":         int(time.time() * 1000),
        "executor":   executor,
        "advisor":    advisor,
        "prompt":     prompt[:500],
        "execText":   exec_summary["response"][:1000],
        "advText":    adv_summary["response"][:1000],
        "tokensIn":   exec_summary["tokensIn"] + adv_summary["tokensIn"],
        "tokensOut":  exec_summary["tokensOut"] + adv_summary["tokensOut"],
        "costUsd":    round(exec_summary["costUsd"] + adv_summary["costUsd"], 4),
        "durationMs": exec_summary["durationMs"] + adv_summary["durationMs"],
        "delta":      delta,
        "error":      "",
    }
    _save_history(entry)

    return {
        "ok":       True,
        "executor": exec_summary,
        "advisor":  adv_summary,
        "delta":    delta,
        "totalTokensIn":  entry["tokensIn"],
        "totalTokensOut": entry["tokensOut"],
        "totalCostUsd":   entry["costUsd"],
        "totalDurationMs": entry["durationMs"],
    }
