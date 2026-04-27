"""Memory tool playground — Anthropic ``memory_20250818`` server-side blocks.

Direct-API lab: send a prompt to Claude with the memory tool enabled
(``anthropic-beta: memory-2025-08-18``), then walk the response for
``tool_use`` blocks named ``memory`` and surface the create/read/update/delete
events in the dashboard. Lets the user see how the model decides what to
remember and how it later recalls it.

Storage: ``~/.claude-dashboard-memory-lab.json`` (history, ≤50).
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
    "CLAUDE_DASHBOARD_MEMORY_LAB",
    Path.home() / ".claude-dashboard-memory-lab.json",
)
_MAX_HISTORY = 50

MODELS = ["claude-sonnet-4-6", "claude-opus-4-7", "claude-sonnet-4-5", "claude-opus-4-6"]
_PRICES = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-opus-4-7":   (15.0, 75.0),
    "claude-opus-4-6":   (15.0, 75.0),
}

EXAMPLES: list[dict] = [
    {"id": "remember-name", "title": "이름 기억",
     "prompt": "My name is Alex and I prefer concise replies. Save this for future sessions."},
    {"id": "recall-name",   "title": "이름 회상",
     "prompt": "What's my name and how do I prefer replies?"},
    {"id": "build-todo",    "title": "TODO 리스트 구축",
     "prompt": "Add 'review PR #42' and 'update docs' to my TODO list, then list everything."},
    {"id": "clear-mem",     "title": "메모리 모두 삭제",
     "prompt": "Forget everything you know about me — clear all stored memories."},
    {"id": "summary",       "title": "메모리 요약",
     "prompt": "Tell me everything you currently remember about me, formatted as bullets."},
]


def _load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(_safe_read(HISTORY_PATH) or "[]")
        if isinstance(data, list):
            return data[:_MAX_HISTORY]
    except Exception as e:
        log.warning("memory_lab history load failed: %s", e)
    return []


def _save_history(entry: dict) -> None:
    items = _load_history()
    items.insert(0, entry)
    items = items[:_MAX_HISTORY]
    try:
        _safe_write(HISTORY_PATH, json.dumps(items, ensure_ascii=False, indent=2))
    except Exception as e:
        log.warning("memory_lab history save failed: %s", e)


def _anthropic_key() -> str:
    keys = load_api_keys()
    val = keys.get("anthropic-api")
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("apiKey") or ""
    return ""


def _extract_memory_events(content: list) -> list[dict]:
    """Pull every memory tool_use call out of the response content list."""
    out: list[dict] = []
    ts = int(time.time() * 1000)
    for block in (content or []):
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if block.get("name") != "memory":
            continue
        inp = block.get("input") or {}
        op = (inp.get("command") or inp.get("op") or "").lower()
        out.append({
            "ts":    ts,
            "op":    op,
            "key":   str(inp.get("path") or inp.get("key") or "")[:200],
            "value": str(inp.get("file_text") or inp.get("value") or inp.get("query") or "")[:500],
            "raw":   {k: v for k, v in inp.items() if k not in ("file_text",)},
        })
    return out


def _cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    pi, po = _PRICES.get(model, (3.0, 15.0))
    return round((tokens_in * pi + tokens_out * po) / 1_000_000, 4)


# ───────── HTTP handlers ─────────

def api_memory_lab_examples(_query: dict | None = None) -> dict:
    return {"examples": EXAMPLES, "models": MODELS}


def api_memory_lab_history(_query: dict | None = None) -> dict:
    return {"items": _load_history()}


def api_memory_lab_blocks(_query: dict | None = None) -> dict:
    """Aggregate every memory event observed across history into a {key:value}
    snapshot. This is best-effort — the source of truth is server-side at
    Anthropic; we just surface what we've seen."""
    snap: dict = {}
    for h in _load_history():
        for ev in (h.get("memoryEvents") or []):
            k = ev.get("key") or ""
            if not k:
                continue
            op = (ev.get("op") or "").lower()
            if op in ("create", "update", "write", "save", "set", "str_replace", "insert"):
                snap[k] = ev.get("value") or ""
            elif op in ("delete", "remove", "clear", "unset"):
                snap.pop(k, None)
    return {"items": [{"key": k, "value": v} for k, v in snap.items()]}


def api_memory_lab_run(body: dict) -> dict:
    import urllib.request
    import urllib.error

    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}
    prompt = (body.get("prompt") or "").strip()[:8000]
    if not prompt:
        return {"ok": False, "error": "prompt required"}
    model = (body.get("model") or "claude-sonnet-4-6").strip()
    if model not in MODELS:
        model = "claude-sonnet-4-6"
    max_tokens = max(256, min(int(body.get("maxTokens") or 4096), 16384))

    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True,
                "error": "ANTHROPIC_API_KEY missing — set in aiProviders tab"}

    req_body = {
        "model": model,
        "max_tokens": max_tokens,
        "tools": [{"type": "memory_20250818", "name": "memory"}],
        "messages": [{"role": "user", "content": prompt}],
    }

    t0 = int(time.time() * 1000)
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(req_body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "memory-2025-08-18,context-management-2025-06-27",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            err = (err_body.get("error") or {}).get("message") or f"HTTP {e.code}"
        except Exception:
            err = f"HTTP {e.code}"
        duration = int(time.time() * 1000) - t0
        _save_history({"id": f"ml-{uuid.uuid4().hex[:10]}", "ts": int(time.time() * 1000),
                       "model": model, "prompt": prompt[:500], "memoryEvents": [],
                       "tokensIn": 0, "tokensOut": 0, "costUsd": 0.0,
                       "durationMs": duration, "error": err})
        return {"ok": False, "error": err, "durationMs": duration}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    duration = int(time.time() * 1000) - t0
    usage = data.get("usage") or {}
    tokens_in = int(usage.get("input_tokens") or 0)
    tokens_out = int(usage.get("output_tokens") or 0)
    cost = _cost_usd(model, tokens_in, tokens_out)
    events = _extract_memory_events(data.get("content") or [])
    text_out = "".join(b.get("text", "") for b in (data.get("content") or [])
                       if isinstance(b, dict) and b.get("type") == "text")

    _save_history({"id": f"ml-{uuid.uuid4().hex[:10]}", "ts": int(time.time() * 1000),
                   "model": model, "prompt": prompt[:500], "memoryEvents": events,
                   "tokensIn": tokens_in, "tokensOut": tokens_out, "costUsd": cost,
                   "durationMs": duration, "error": ""})

    return {
        "ok":           True,
        "model":        model,
        "text":         text_out,
        "memoryEvents": events,
        "tokensIn":     tokens_in,
        "tokensOut":    tokens_out,
        "costUsd":      cost,
        "durationMs":   duration,
    }
