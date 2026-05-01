"""Channel orchestrator — Slack/Telegram-driven multi-agent runner.

The orchestrator receives a single message ("dispatch") from a chat channel or
the dashboard, plans a small set of sub-agent tasks (using the configured
*planner* model — Claude by default, but never hardcoded), runs them in
parallel via :func:`server.ai_providers.execute_with_assignee`, and posts a
final aggregated reply back to the channel. Each sub-agent publishes
start/progress/done events to ``server.agent_bus`` so the frontend, the TUI
and other agents can subscribe to live progress.

Storage: ``~/.claude-dashboard-orchestrator.json`` — pure data, the orchestrator
itself contains *no* model names, channel ids, or routing rules in code.

::

    {
      "plannerAssignee":  "claude:opus",
      "aggregatorAssignee": "claude:sonnet",
      "defaultAssignees": ["claude:sonnet", "openai:gpt-4.1", "ollama:llama3.1"],
      "maxParallel":      4,
      "channelDebounceMs": 2000,
      "bindings": [
        { "kind": "slack",    "channel": "C0XXXXX", "workflowId": "wf_..." },
        { "kind": "telegram", "chat":    "-100123",  "assignees": ["claude:sonnet"] }
      ]
    }

A binding either points at a saved workflow (``workflowId``) — in which case
that workflow runs with the inbound message as ``extra_inputs.message`` — or
specifies which assignees to use for an ad-hoc plan. Bindings can be added
from the TUI, the dashboard UI, or directly via ``/api/orchestrator/bind``.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

from . import agent_bus
from .ai_providers import AIResponse, execute_with_assignee, get_registry
from .config import _env_path
from .logger import log
from .utils import _safe_read, _safe_write


ORCH_CONFIG_PATH = _env_path(
    "CLAUDE_DASHBOARD_ORCHESTRATOR",
    Path.home() / ".claude-dashboard-orchestrator.json",
)


# ───────── Defaults (env-overridable) ─────────

_DEFAULT_PLANNER     = os.environ.get("ORCH_PLANNER",     "claude:sonnet")
_DEFAULT_AGGREGATOR  = os.environ.get("ORCH_AGGREGATOR",  "claude:sonnet")
_DEFAULT_MAX_PARA    = int(os.environ.get("ORCH_MAX_PARALLEL", "4"))
_CHANNEL_DEBOUNCE_MS = int(os.environ.get("ORCH_DEBOUNCE_MS", "2000"))
_PER_AGENT_TIMEOUT_S = int(os.environ.get("ORCH_AGENT_TIMEOUT_S", "180"))


# ───────── Config ─────────

def _empty_cfg() -> dict:
    return {
        "plannerAssignee":     _DEFAULT_PLANNER,
        "aggregatorAssignee":  _DEFAULT_AGGREGATOR,
        "defaultAssignees":    [_DEFAULT_PLANNER],
        "maxParallel":         _DEFAULT_MAX_PARA,
        "channelDebounceMs":   _CHANNEL_DEBOUNCE_MS,
        "bindings":            [],
        "savedAt":             0,
    }


def load_config() -> dict:
    if not ORCH_CONFIG_PATH.exists():
        return _empty_cfg()
    try:
        data = json.loads(_safe_read(ORCH_CONFIG_PATH) or "{}")
        if not isinstance(data, dict):
            return _empty_cfg()
        cfg = _empty_cfg()
        cfg.update({
            "plannerAssignee":    str(data.get("plannerAssignee") or _DEFAULT_PLANNER),
            "aggregatorAssignee": str(data.get("aggregatorAssignee") or _DEFAULT_AGGREGATOR),
            "defaultAssignees":   [str(a) for a in (data.get("defaultAssignees") or []) if a]
                                  or [_DEFAULT_PLANNER],
            "maxParallel":        max(1, min(int(data.get("maxParallel") or _DEFAULT_MAX_PARA), 16)),
            "channelDebounceMs":  max(0, int(data.get("channelDebounceMs") or _CHANNEL_DEBOUNCE_MS)),
            "bindings":           [_sanitize_binding(b) for b in (data.get("bindings") or [])
                                   if isinstance(b, dict)],
            "savedAt":            int(data.get("savedAt") or 0),
        })
        cfg["bindings"] = [b for b in cfg["bindings"] if b]
        return cfg
    except Exception as e:
        log.warning("orch config load failed: %s", e)
        return _empty_cfg()


def _sanitize_binding(b: dict) -> Optional[dict]:
    kind = (b.get("kind") or "").strip().lower()
    if kind not in ("slack", "telegram", "http"):
        return None
    out: dict = {"kind": kind}
    if kind == "slack":
        ch = (b.get("channel") or "").strip()
        if not ch:
            return None
        out["channel"] = ch
    elif kind == "telegram":
        chat = (b.get("chat") or "").strip()
        if not chat:
            return None
        out["chat"] = chat
    else:  # http
        out["channel"] = (b.get("channel") or "default").strip()
    wf = (b.get("workflowId") or "").strip()
    if wf:
        out["workflowId"] = wf
    assignees = [str(a).strip() for a in (b.get("assignees") or []) if a]
    if assignees:
        out["assignees"] = assignees
    label = (b.get("label") or "").strip()
    if label:
        out["label"] = label
    return out


def save_config(cfg: dict) -> bool:
    cfg = {**cfg, "savedAt": int(time.time() * 1000)}
    return _safe_write(ORCH_CONFIG_PATH, json.dumps(cfg, ensure_ascii=False, indent=2))


def find_binding(kind: str, channel_or_chat: str) -> Optional[dict]:
    cfg = load_config()
    for b in cfg.get("bindings") or []:
        if b.get("kind") != kind:
            continue
        if kind == "slack" and b.get("channel") == channel_or_chat:
            return b
        if kind == "telegram" and b.get("chat") == channel_or_chat:
            return b
        if kind == "http":
            return b
    return None


# ───────── Planner ─────────

_PLAN_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_PLAN_OBJ_RE = re.compile(r"(\{[\s\S]*\})")

_PLANNER_SYSTEM = """You are an orchestrator's planner. Break the user's request \
into 1-4 small parallel sub-tasks for sub-agents. Respond ONLY with a JSON object:
{"plan":[{"assignee":"<provider:model>","task":"<single-sentence prompt>"},...]}
Do not include any explanation. Choose assignees from the provided list."""


def _build_planner_prompt(user_text: str, available: list[str]) -> str:
    avail = ", ".join(available) or "claude:sonnet"
    return (f"Available assignees: {avail}\n"
            f"User request:\n{user_text.strip()}\n\n"
            f"Return JSON only.")


def _parse_plan(text: str, available: list[str]) -> list[dict]:
    """Best-effort plan extraction. Falls back to a single default-assignee step
    if the planner returned no parseable JSON. We never hardcode a model — the
    fallback uses the first entry of ``available``.
    """
    avail_set = set(available)
    candidates: list[str] = []
    m = _PLAN_FENCE_RE.search(text or "")
    if m:
        candidates.append(m.group(1))
    m2 = _PLAN_OBJ_RE.search(text or "")
    if m2:
        candidates.append(m2.group(1))
    candidates.append(text or "")
    for c in candidates:
        try:
            obj = json.loads(c)
        except Exception:
            continue
        plan = obj.get("plan") if isinstance(obj, dict) else None
        if not isinstance(plan, list):
            continue
        out: list[dict] = []
        for step in plan[:8]:
            if not isinstance(step, dict):
                continue
            a = str(step.get("assignee") or "").strip()
            t = str(step.get("task") or "").strip()
            if not t:
                continue
            if avail_set and a not in avail_set:
                a = available[0]
            out.append({"assignee": a or (available[0] if available else _DEFAULT_PLANNER),
                        "task": t})
        if out:
            return out
    # Fallback — just one task on the default assignee
    return [{"assignee": available[0] if available else _DEFAULT_PLANNER,
             "task": text.strip() or "Respond to the user."}]


# ───────── Run ─────────

def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _topic(run_id: str, *parts: str) -> str:
    return ".".join(("orch", run_id, *parts))


def _execute_step(run_id: str, idx: int, assignee: str, task: str) -> dict:
    agent_bus.publish(_topic(run_id, f"step.{idx}.start"),
                      {"assignee": assignee, "task": task}, source=assignee)
    t0 = time.time()
    try:
        resp: AIResponse = execute_with_assignee(
            assignee, task, timeout=_PER_AGENT_TIMEOUT_S, fallback=True,
        )
        ok = (resp.status == "ok")
        out = {
            "ok":        ok,
            "assignee":  assignee,
            "task":      task,
            "output":    resp.output if ok else "",
            "error":     resp.error if not ok else "",
            "model":     resp.model,
            "provider":  resp.provider,
            "tokens":    resp.tokens_total,
            "durationMs": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        out = {
            "ok": False, "assignee": assignee, "task": task,
            "output": "", "error": f"{type(e).__name__}: {e}",
            "durationMs": int((time.time() - t0) * 1000),
        }
    agent_bus.publish(_topic(run_id, f"step.{idx}.done"), out, source=assignee)
    return out


def _aggregate(aggregator: str, user_text: str, results: list[dict]) -> str:
    """Ask a small model to merge sub-agent outputs. If aggregation itself
    fails, fall back to a deterministic concatenation — we never lie about
    success.
    """
    bullets = []
    for i, r in enumerate(results):
        head = f"#{i+1} {r['assignee']} ({'ok' if r['ok'] else 'err'})"
        body = r.get("output") or r.get("error") or ""
        bullets.append(f"{head}\n{body[:1500]}")
    joined = "\n\n".join(bullets)
    prompt = (
        f"User asked:\n{user_text.strip()}\n\n"
        f"Sub-agent results:\n{joined}\n\n"
        "Write a single concise reply to the user that synthesises the above. "
        "Do not invent facts; if results disagree, note the disagreement briefly."
    )
    try:
        resp = execute_with_assignee(aggregator, prompt, timeout=_PER_AGENT_TIMEOUT_S)
        if resp.status == "ok" and resp.output.strip():
            return resp.output.strip()
        log.warning("aggregator returned err: %s", resp.error)
    except Exception as e:
        log.warning("aggregator crash: %s", e)
    # Deterministic fallback — clearly labelled.
    return ("(aggregator unavailable — concatenated sub-agent outputs)\n\n"
            + "\n\n---\n\n".join(b for b in bullets))


def dispatch(text: str, *, kind: str = "http", channel: str = "",
             user: str = "", reply: Optional[Any] = None) -> dict:
    """Run a single orchestrator turn for ``text``.

    ``kind`` ∈ {slack, telegram, http}. ``reply`` is an optional callable
    ``(text: str) -> None`` the caller passes in to deliver the final answer
    to the inbound channel; if absent, the caller can fetch the result from
    the return value or subscribe to ``orch.<run_id>.*`` on the agent bus.
    """
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "empty text"}

    cfg = load_config()
    binding = find_binding(kind, channel) if channel else None
    run_id = _new_run_id()

    # Determine assignee list for this dispatch — binding > config default.
    avail = list((binding or {}).get("assignees") or cfg["defaultAssignees"])
    avail = [a for a in avail if a]
    if not avail:
        avail = [cfg["plannerAssignee"]]

    agent_bus.publish(_topic(run_id, "begin"),
                      {"text": text, "kind": kind, "channel": channel,
                       "user": user, "available": avail,
                       "binding": binding},
                      source="orchestrator")

    # 1. Plan
    planner = cfg["plannerAssignee"]
    try:
        plan_resp = execute_with_assignee(
            planner,
            _build_planner_prompt(text, avail),
            system_prompt=_PLANNER_SYSTEM,
            timeout=_PER_AGENT_TIMEOUT_S,
        )
        plan_text = plan_resp.output if plan_resp.status == "ok" else ""
    except Exception as e:
        log.warning("planner crash: %s", e)
        plan_text = ""
    plan = _parse_plan(plan_text, avail)
    agent_bus.publish(_topic(run_id, "plan"),
                      {"steps": plan, "plannerOutput": plan_text[:2000]},
                      source=planner)

    # 2. Execute steps in parallel
    pool_size = min(cfg["maxParallel"], max(1, len(plan)))
    results: list[dict] = [{} for _ in plan]
    with ThreadPoolExecutor(max_workers=pool_size, thread_name_prefix="orch") as pool:
        futs = {pool.submit(_execute_step, run_id, i, step["assignee"], step["task"]): i
                for i, step in enumerate(plan)}
        for fut in as_completed(futs):
            idx = futs[fut]
            try:
                results[idx] = fut.result()
            except Exception as e:
                results[idx] = {"ok": False, "assignee": plan[idx]["assignee"],
                                "task": plan[idx]["task"], "error": str(e),
                                "output": "", "durationMs": 0}

    # 3. Aggregate
    final_text = _aggregate(cfg["aggregatorAssignee"], text, results)
    agent_bus.publish(_topic(run_id, "final"),
                      {"text": final_text, "results": results},
                      source=cfg["aggregatorAssignee"])

    # 4. Optional channel reply
    if callable(reply):
        try:
            reply(final_text)
        except Exception as e:
            log.warning("orch reply delivery failed: %s", e)

    return {
        "ok": True, "runId": run_id, "plan": plan,
        "results": results, "final": final_text,
    }


# ───────── Channel adapters ─────────

# Slack and Telegram both call into ``dispatch()`` via thin reply callbacks.
# Slack mode can be triggered either from the Events API webhook (registered
# as ``/api/slack/events`` in routes.py) or from a one-off dispatch.

def _slack_reply(channel: str, thread_ts: Optional[str] = None):
    from . import slack_api
    def _send(text: str) -> None:
        try:
            payload = {"channel": channel, "text": text[:38000]}
            if thread_ts:
                payload["thread_ts"] = thread_ts
            slack_api._call("chat.postMessage", payload)
        except Exception as e:
            log.warning("slack reply failed: %s", e)
    return _send


def _telegram_reply(chat: str, reply_to: Optional[int] = None):
    from . import telegram_api
    def _send(text: str) -> None:
        try:
            telegram_api.send_message(chat, text, reply_to=reply_to)
        except Exception as e:
            log.warning("telegram reply failed: %s", e)
    return _send


def handle_telegram_update(upd: dict) -> None:
    """Wire-up for telegram_api.start_long_poll(handler=this)."""
    msg = upd.get("message") or upd.get("edited_message") or {}
    chat = (msg.get("chat") or {}).get("id")
    if chat is None:
        return
    chat_str = str(chat)
    text = (msg.get("text") or "").strip()
    if not text:
        return
    binding = find_binding("telegram", chat_str)
    if binding is None:
        # Honour explicit-binding mode by default — silent if not bound.
        if os.environ.get("ORCH_TELEGRAM_BIND_REQUIRED", "1") != "0":
            return
    user = ((msg.get("from") or {}).get("username")
            or (msg.get("from") or {}).get("first_name") or "")
    threading.Thread(
        target=dispatch,
        kwargs={"text": text, "kind": "telegram", "channel": chat_str,
                "user": user,
                "reply": _telegram_reply(chat_str, reply_to=msg.get("message_id"))},
        name=f"orch-tg-{chat_str}",
        daemon=True,
    ).start()


def handle_slack_event(event: dict) -> None:
    """Wire-up for the Slack Events API webhook."""
    inner = event.get("event") or event
    if inner.get("type") not in ("app_mention", "message"):
        return
    if inner.get("subtype") in ("bot_message", "message_changed", "message_deleted"):
        return
    text = (inner.get("text") or "").strip()
    channel = (inner.get("channel") or "").strip()
    if not (text and channel):
        return
    binding = find_binding("slack", channel)
    if binding is None and os.environ.get("ORCH_SLACK_BIND_REQUIRED", "1") != "0":
        return
    user = inner.get("user") or ""
    thread_ts = inner.get("thread_ts") or inner.get("ts")
    threading.Thread(
        target=dispatch,
        kwargs={"text": text, "kind": "slack", "channel": channel, "user": user,
                "reply": _slack_reply(channel, thread_ts=thread_ts)},
        name=f"orch-sl-{channel}",
        daemon=True,
    ).start()


def start_listeners() -> dict:
    """Idempotently spin up Telegram long-poll if a token is configured.

    Slack inbound is webhook-driven (Slack Events API) — no listener needed
    here. Returns a small status dict so callers (server.py boot, /api/orch/start)
    can render the result.
    """
    from . import telegram_api
    started_tg = telegram_api.start_long_poll(handle_telegram_update)
    return {
        "telegram": "running" if started_tg else "skipped (no token)",
        "slack":    "webhook-mode",
    }


# ───────── HTTP API ─────────

def api_orch_config_get(query: dict | None = None) -> dict:
    cfg = load_config()
    # Don't redact — there are no secrets here, only model names + channels.
    avail_providers = [p.provider_id for p in get_registry().available_providers()]
    return {"ok": True, "config": cfg, "availableProviders": avail_providers}


def api_orch_config_save(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    cfg = load_config()
    for k in ("plannerAssignee", "aggregatorAssignee"):
        v = body.get(k)
        if isinstance(v, str) and v.strip():
            cfg[k] = v.strip()
    if isinstance(body.get("defaultAssignees"), list):
        cfg["defaultAssignees"] = [str(a).strip() for a in body["defaultAssignees"]
                                   if str(a).strip()] or cfg["defaultAssignees"]
    if "maxParallel" in body:
        try:
            cfg["maxParallel"] = max(1, min(int(body["maxParallel"]), 16))
        except Exception:
            pass
    if "channelDebounceMs" in body:
        try:
            cfg["channelDebounceMs"] = max(0, int(body["channelDebounceMs"]))
        except Exception:
            pass
    if isinstance(body.get("bindings"), list):
        cfg["bindings"] = [b for b in (_sanitize_binding(x) for x in body["bindings"])
                           if b]
    if not save_config(cfg):
        return {"ok": False, "error": "save failed"}
    return {"ok": True, "config": load_config()}


def api_orch_bind(body: dict) -> dict:
    """Add or update a single binding."""
    cfg = load_config()
    new_b = _sanitize_binding(body or {})
    if not new_b:
        return {"ok": False, "error": "invalid binding"}
    bindings = cfg.get("bindings") or []
    # Replace existing match by (kind, channel/chat)
    key_field = "channel" if new_b["kind"] in ("slack", "http") else "chat"
    bindings = [b for b in bindings
                if not (b.get("kind") == new_b["kind"]
                        and b.get(key_field) == new_b.get(key_field))]
    bindings.append(new_b)
    cfg["bindings"] = bindings
    if not save_config(cfg):
        return {"ok": False, "error": "save failed"}
    return {"ok": True, "binding": new_b, "bindings": bindings}


def api_orch_unbind(body: dict) -> dict:
    cfg = load_config()
    kind = (body.get("kind") or "").strip().lower()
    target = (body.get("channel") or body.get("chat") or "").strip()
    if not kind or not target:
        return {"ok": False, "error": "kind and channel/chat required"}
    field = "channel" if kind in ("slack", "http") else "chat"
    cfg["bindings"] = [b for b in (cfg.get("bindings") or [])
                       if not (b.get("kind") == kind and b.get(field) == target)]
    if not save_config(cfg):
        return {"ok": False, "error": "save failed"}
    return {"ok": True, "bindings": cfg["bindings"]}


def api_orch_dispatch(body: dict) -> dict:
    """POST /api/orchestrator/dispatch — synchronous run, returns final result.

    For UI use: lets you run the orchestrator without a chat platform attached.
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    text = (body.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "text required"}
    return dispatch(
        text,
        kind=(body.get("kind") or "http"),
        channel=(body.get("channel") or "default"),
        user=(body.get("user") or ""),
    )


def api_orch_start(body: dict | None = None) -> dict:
    return {"ok": True, "status": start_listeners()}


def api_slack_events(body: dict) -> dict:
    """POST /api/slack/events — Slack Events API receiver.

    Handles URL verification challenge and dispatches events to the
    orchestrator. Signature verification is delegated to a future hook (see
    ``SLACK_SIGNING_SECRET``); for now we accept any request and rely on
    keeping the URL secret + Slack's source IP set.
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge", "")}
    handle_slack_event(body)
    return {"ok": True}


def api_telegram_webhook(body: dict) -> dict:
    """POST /api/telegram/webhook — webhook-mode receiver (alternative to long-poll)."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    handle_telegram_update(body)
    return {"ok": True}
