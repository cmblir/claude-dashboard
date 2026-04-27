"""Computer Use playground — Anthropic computer-use beta tool, plan-only.

Lets the user post a prompt (+ optional screenshot) to Claude with the
``computer_20250124`` tool enabled, then surfaces the model's tool-use plan
(sequence of `screenshot` / `key` / `mouse_*` calls). The dashboard does
NOT execute any of these on the user's machine — this lab is intentionally
read-only. Use it to inspect what the model would do before wiring up a
real automation harness.

Storage: ``~/.claude-dashboard-computer-use-lab.json`` (history, ≤50).
"""
from __future__ import annotations

import base64
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
    "CLAUDE_DASHBOARD_COMPUTER_USE_LAB",
    Path.home() / ".claude-dashboard-computer-use-lab.json",
)
_MAX_HISTORY = 50

MODELS = ["claude-sonnet-4-6", "claude-opus-4-7", "claude-sonnet-4-5", "claude-opus-4-6"]
# (input, output) USD per 1M tokens
_PRICES = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-opus-4-7":   (15.0, 75.0),
    "claude-opus-4-6":   (15.0, 75.0),
}

EXAMPLES: list[dict] = [
    {"id": "open-finder", "title": "Finder 열기 + Documents 클릭",
     "prompt": "Open Finder and click on the Documents folder in the sidebar.",
     "screenSize": {"width": 1920, "height": 1080}},
    {"id": "search-browser", "title": "브라우저 주소창에 검색",
     "prompt": "Open Chrome, focus the address bar, and search for 'anthropic computer use docs'.",
     "screenSize": {"width": 1920, "height": 1080}},
    {"id": "fill-form", "title": "폼 채우기",
     "prompt": "There is a contact form on screen. Fill in the Name field with 'Alex' and click Submit.",
     "screenSize": {"width": 1440, "height": 900}},
    {"id": "screenshot-only", "title": "스크린샷만 (planning only)",
     "prompt": "Take a screenshot and describe what you see.",
     "screenSize": {"width": 1920, "height": 1080}},
    {"id": "multi-step", "title": "다단계 작업 — 파일 닫고 새로 열기",
     "prompt": "Close the current Slack window, open Notion, and click the page titled 'Sprint 14'.",
     "screenSize": {"width": 1920, "height": 1080}},
]


def _load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(_safe_read(HISTORY_PATH) or "[]")
        if isinstance(data, list):
            return data[:_MAX_HISTORY]
    except Exception as e:
        log.warning("computer_use history load failed: %s", e)
    return []


def _save_history(entry: dict) -> None:
    items = _load_history()
    items.insert(0, entry)
    items = items[:_MAX_HISTORY]
    try:
        _safe_write(HISTORY_PATH, json.dumps(items, ensure_ascii=False, indent=2))
    except Exception as e:
        log.warning("computer_use history save failed: %s", e)


def _anthropic_key() -> str:
    keys = load_api_keys()
    val = keys.get("anthropic-api")
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("apiKey") or ""
    return ""


def _read_screenshot_b64(path: str) -> tuple[str, str]:
    """Read a screenshot file under HOME and return (b64, error). Reject paths
    outside HOME to prevent arbitrary disk reads."""
    if not path:
        return "", ""
    try:
        p = Path(path).expanduser().resolve()
    except Exception as e:
        return "", f"path resolve failed: {e}"
    home = str(Path.home())
    if not (str(p) == home or str(p).startswith(home + "/")):
        return "", "screenshot path must be under $HOME"
    if not p.exists() or not p.is_file():
        return "", "screenshot file not found"
    try:
        return base64.b64encode(p.read_bytes()).decode("ascii"), ""
    except Exception as e:
        return "", f"screenshot read failed: {e}"


def _extract_tool_plan(content: list) -> list[dict]:
    out: list[dict] = []
    for block in (content or []):
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use":
            continue
        if block.get("name") != "computer":
            continue
        inp = block.get("input") or {}
        out.append({
            "id":     block.get("id"),
            "action": inp.get("action") or "",
            "params": {k: v for k, v in inp.items() if k != "action"},
        })
    return out


def _cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    pi, po = _PRICES.get(model, (3.0, 15.0))
    return round((tokens_in * pi + tokens_out * po) / 1_000_000, 4)


# ───────── HTTP handlers ─────────

def api_computer_use_examples(_query: dict | None = None) -> dict:
    return {"examples": EXAMPLES, "models": MODELS}


def api_computer_use_history(_query: dict | None = None) -> dict:
    return {"items": _load_history()}


def api_computer_use_run(body: dict) -> dict:
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
    ss = body.get("screenSize") or {}
    width = max(320, min(int(ss.get("width") or 1920), 3840))
    height = max(240, min(int(ss.get("height") or 1080), 2160))
    max_tokens = max(256, min(int(body.get("maxTokens") or 4096), 16384))

    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True,
                "error": "ANTHROPIC_API_KEY missing — set in aiProviders tab"}

    user_content: list[dict] = [{"type": "text", "text": prompt}]
    img_b64, img_err = _read_screenshot_b64(body.get("screenshotPath") or "")
    if img_b64:
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
        })

    req_body = {
        "model": model,
        "max_tokens": max_tokens,
        "tools": [{
            "type": "computer_20250124",
            "name": "computer",
            "display_width_px": width,
            "display_height_px": height,
            "display_number": 1,
        }],
        "messages": [{"role": "user", "content": user_content}],
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
                "anthropic-beta": "computer-use-2025-01-24,computer-use-2024-10-22",
            },
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            err = (err_body.get("error") or {}).get("message") or f"HTTP {e.code}"
        except Exception:
            err = f"HTTP {e.code}"
        duration = int(time.time() * 1000) - t0
        _save_history({"id": f"cu-{uuid.uuid4().hex[:10]}", "ts": int(time.time() * 1000),
                       "model": model, "prompt": prompt[:500], "toolPlanCount": 0,
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
    plan = _extract_tool_plan(data.get("content") or [])
    text_out = "".join(b.get("text", "") for b in (data.get("content") or [])
                       if isinstance(b, dict) and b.get("type") == "text")

    _save_history({"id": f"cu-{uuid.uuid4().hex[:10]}", "ts": int(time.time() * 1000),
                   "model": model, "prompt": prompt[:500], "toolPlanCount": len(plan),
                   "tokensIn": tokens_in, "tokensOut": tokens_out, "costUsd": cost,
                   "durationMs": duration, "error": ""})

    return {
        "ok":        True,
        "model":     model,
        "toolPlan":  plan,
        "text":      text_out,
        "tokensIn":  tokens_in,
        "tokensOut": tokens_out,
        "costUsd":   cost,
        "durationMs": duration,
        "imageWarning": img_err if img_err else "",
        "safetyNote": "Tool plan only — dashboard does not execute on your machine.",
    }
