"""Hyper Agent — sub-agents that self-refine their own settings over time.

A "hyper" sub-agent is a regular Claude Code agent (`~/.claude/agents/<name>.md`)
with an opt-in supervisor that periodically asks a meta-LLM (Opus by default)
to propose refinements to its system prompt, tool list, and description, given
the user's stated objective and recent transcripts. Each proposal is applied
atomically with a `.bak.md` backup so any iteration is reversible.

Storage:
- Agent body itself stays in ``~/.claude/agents/<name>.md`` (Claude Code
  compatible, no schema change).
- Meta + history live in ``~/.claude-dashboard-hyper-agents.json``.
- Per-iteration backup at ``~/.claude/agents/<name>.<ts>.bak.md``.

Public API:
- ``load_meta()`` / ``save_meta(meta)`` — read/write the index.
- ``configure_agent(name, patch)`` — toggle + set objective + targets + trigger.
- ``refine_agent(name, *, trigger, dry_run=False)`` — main refinement pipeline.
- ``apply_proposal(name, proposal, *, trigger, cost_usd, tokens)`` — write file
  + .bak + history; called by ``refine_agent`` and tests.
- ``rollback(name, version_ts)`` — restore from a backup file.
- ``list_hyper()`` / ``get_hyper(name)`` / ``history(name)`` — dashboard reads.
- ``api_*`` HTTP entrypoints registered by ``server/routes.py``.

The actual after-session / cron triggers live in ``server/hyper_agent_worker.py``.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .agents import _BUILTIN_AGENTS, get_agent
from .config import AGENTS_DIR, _env_path
from .logger import log
from .utils import _safe_read, _safe_write


HYPER_AGENTS_PATH = _env_path(
    "CLAUDE_DASHBOARD_HYPER_AGENTS",
    Path.home() / ".claude-dashboard-hyper-agents.json",
)


# ───────── Schema ─────────

_VALID_TARGETS = {"systemPrompt", "tools", "description"}
_VALID_TRIGGERS = {"manual", "after_session", "cron", "any"}
_AGENT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _empty_meta() -> dict:
    return {"version": 1, "agents": {}}


def _default_agent_meta() -> dict:
    return {
        "enabled":            False,
        "objective":          "",
        "refineTargets":      ["systemPrompt"],
        "refineProvider":     "claude:opus",
        "trigger":            "manual",
        "cronSpec":           "0 */6 * * *",
        "minSessionsBetween": 5,
        "budgetUSD":          5.0,
        "spentUSD":           0.0,
        "lastRefinedAt":      0,
        "totalRefinements":   0,
        "lastError":          "",
        "history":            [],
    }


def _coerce_agent_meta(raw: Any) -> dict:
    """Normalise a stored agent meta entry, dropping unknown keys, clamping
    out-of-range numbers, validating enums. Never raises."""
    base = _default_agent_meta()
    if not isinstance(raw, dict):
        return base
    out = dict(base)

    out["enabled"] = bool(raw.get("enabled", False))

    obj = raw.get("objective", "")
    out["objective"] = str(obj)[:4000] if obj else ""

    targets = raw.get("refineTargets") or []
    if isinstance(targets, list):
        out["refineTargets"] = [t for t in targets if t in _VALID_TARGETS] or ["systemPrompt"]

    rp = str(raw.get("refineProvider") or "claude:opus").strip()
    if len(rp) > 120:
        rp = rp[:120]
    out["refineProvider"] = rp or "claude:opus"

    trig = str(raw.get("trigger") or "manual")
    out["trigger"] = trig if trig in _VALID_TRIGGERS else "manual"

    cron = str(raw.get("cronSpec") or "0 */6 * * *")[:120]
    out["cronSpec"] = cron

    try:
        msb = int(raw.get("minSessionsBetween", 5))
        out["minSessionsBetween"] = max(0, min(msb, 1000))
    except Exception:
        pass

    try:
        budget = float(raw.get("budgetUSD", 5.0))
        out["budgetUSD"] = max(0.0, min(budget, 10000.0))
    except Exception:
        pass

    try:
        spent = float(raw.get("spentUSD", 0.0))
        out["spentUSD"] = max(0.0, spent)
    except Exception:
        pass

    try:
        out["lastRefinedAt"] = int(raw.get("lastRefinedAt", 0))
        out["totalRefinements"] = int(raw.get("totalRefinements", 0))
    except Exception:
        pass

    out["lastError"] = str(raw.get("lastError") or "")[:1000]

    hist = raw.get("history") or []
    if isinstance(hist, list):
        out["history"] = [_coerce_history_entry(h) for h in hist if isinstance(h, dict)][-100:]

    return out


def _coerce_history_entry(h: dict) -> dict:
    """Trim history entry to a known shape so the JSON file stays bounded."""
    return {
        "ts":             int(h.get("ts", 0) or 0),
        "trigger":        str(h.get("trigger") or "manual"),
        "provider":       str(h.get("provider") or ""),
        "model":          str(h.get("model") or ""),
        "rationale":      str(h.get("rationale") or "")[:2000],
        "appliedTargets": [t for t in (h.get("appliedTargets") or []) if t in _VALID_TARGETS],
        "backupPath":     str(h.get("backupPath") or ""),
        "costUSD":        float(h.get("costUSD") or 0.0),
        "tokens":         int(h.get("tokens") or 0),
        "scoreBefore":    h.get("scoreBefore"),
        "scoreAfter":     h.get("scoreAfter"),
        "dryRun":         bool(h.get("dryRun", False)),
        "error":          str(h.get("error") or "")[:1000],
        "diff":           h.get("diff") or {},
    }


# ───────── Persistence ─────────

def load_meta() -> dict:
    """Return meta with defaults applied for every entry. Safe even on missing
    or corrupted file."""
    if not HYPER_AGENTS_PATH.exists():
        return _empty_meta()
    raw = _safe_read(HYPER_AGENTS_PATH)
    if not raw:
        return _empty_meta()
    try:
        data = json.loads(raw)
    except Exception as e:
        log.warning("hyper-agents load failed: %s", e)
        return _empty_meta()
    if not isinstance(data, dict):
        return _empty_meta()
    out = _empty_meta()
    agents_in = data.get("agents") or {}
    if isinstance(agents_in, dict):
        for name, entry in agents_in.items():
            if not _AGENT_NAME_RE.match(str(name)):
                continue
            out["agents"][name] = _coerce_agent_meta(entry)
    return out


def save_meta(meta: dict) -> bool:
    text = json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True)
    return _safe_write(HYPER_AGENTS_PATH, text)


def get_hyper(name: str) -> dict:
    """Return the meta for a single agent, creating defaults if absent."""
    m = load_meta()
    return m["agents"].get(name) or _default_agent_meta()


def list_hyper() -> dict:
    """List all agents with hyper meta (enabled or not)."""
    m = load_meta()
    items = []
    for name, entry in m["agents"].items():
        items.append({
            "name":              name,
            "enabled":           entry["enabled"],
            "objective":         entry["objective"],
            "trigger":           entry["trigger"],
            "lastRefinedAt":     entry["lastRefinedAt"],
            "totalRefinements":  entry["totalRefinements"],
            "spentUSD":          entry["spentUSD"],
            "budgetUSD":         entry["budgetUSD"],
            "lastError":         entry["lastError"],
            "refineTargets":     entry["refineTargets"],
            "refineProvider":    entry["refineProvider"],
        })
    items.sort(key=lambda r: (-int(r["enabled"]), -r["lastRefinedAt"], r["name"]))
    return {"items": items, "count": len(items)}


def history(name: str) -> dict:
    entry = get_hyper(name)
    return {"name": name, "history": entry.get("history", [])}


# ───────── Configuration ─────────

def _is_writable_agent(name: str) -> tuple[bool, str]:
    """Hyper Agent only applies to writeable global agents — skip builtin /
    plugin / unknown."""
    if not _AGENT_NAME_RE.match(name):
        return False, "invalid agent name"
    for b in _BUILTIN_AGENTS:
        if b["id"] == name:
            return False, "builtin agent is read-only"
    if ":" in name:
        return False, "plugin agent is read-only"
    p = AGENTS_DIR / f"{name}.md"
    if not p.exists():
        return False, "agent file not found"
    return True, ""


def configure_agent(name: str, patch: dict) -> dict:
    """Set objective / targets / trigger / budget for an agent. Creates the
    meta entry on first call."""
    ok, why = _is_writable_agent(name)
    if not ok:
        return {"ok": False, "error": why}
    meta = load_meta()
    cur = meta["agents"].get(name) or _default_agent_meta()
    merged = dict(cur)
    if isinstance(patch, dict):
        merged.update(patch)
    merged = _coerce_agent_meta(merged)
    meta["agents"][name] = merged
    return {"ok": save_meta(meta), "agent": merged}


def toggle_agent(name: str, enabled: bool) -> dict:
    return configure_agent(name, {"enabled": bool(enabled)})


# ───────── Refinement engine ─────────

_META_SYSTEM_PROMPT = """You are an agent meta-improver. You will be shown the
current Claude Code sub-agent definition (frontmatter + system prompt body),
the user's stated objective, and a small sample of recent transcripts in
which this agent was used. Your task is to propose surgical refinements.

You MUST respond with a single valid JSON object and nothing else, matching
this shape:

{
  "newSystemPrompt": string | null,   // the rewritten body, or null to keep
  "newTools":        string[] | null, // new tools list, or null to keep
  "newDescription":  string | null,   // new description, or null to keep
  "rationale":       string,          // 1-3 short sentences explaining the change
  "scoreBefore":     number,          // 0..1 estimate of current quality
  "scoreAfter":      number           // 0..1 estimate after proposed change
}

Rules:
- Refine ONLY the targets listed in "Refine targets". Set the others to null.
- Do not invent tools; restrict tool changes to the existing palette.
- Keep the agent's identity and primary role intact unless the objective demands change.
- If the agent is already strong, return the same content with rationale="no change needed".
- Never include markdown fences in the JSON output.
"""


def _read_agent_file(name: str) -> dict:
    """Read the agent .md file and return parsed parts."""
    a = get_agent(name)
    if "error" in a:
        return {"error": a["error"]}
    return {
        "name":          a["name"],
        "description":   a["description"],
        "model":         a["model"],
        "tools":         a["tools"],
        "systemPrompt":  a["content"],
        "raw":           a["raw"],
        "path":          a.get("path", ""),
    }


def _write_agent_file(name: str, *,
                      description: str,
                      model: str,
                      tools: list,
                      system_prompt: str) -> bool:
    """Re-emit ``~/.claude/agents/<name>.md`` from parts."""
    p = AGENTS_DIR / f"{name}.md"
    tools_str = ", ".join(t for t in tools) if tools else ""
    raw = (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"model: {model}\n"
        f"tools: {tools_str}\n"
        "---\n\n"
        f"{system_prompt}\n"
    )
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    return _safe_write(p, raw)


def _backup_agent(name: str, ts_ms: int) -> str:
    """Copy current agent file to ``<name>.<ts>.bak.md`` before overwriting.
    Returns the backup path (string), or empty string on failure."""
    src = AGENTS_DIR / f"{name}.md"
    if not src.exists():
        return ""
    dst = AGENTS_DIR / f"{name}.{ts_ms}.bak.md"
    try:
        dst.write_bytes(src.read_bytes())
        return str(dst)
    except Exception as e:
        log.warning("hyper-agent backup failed: %s", e)
        return ""


def _build_meta_prompt(*, agent: dict, objective: str, targets: list,
                       transcripts: list[str]) -> str:
    """Compose the user-side payload for the meta-LLM."""
    sample = "\n\n---\n\n".join(transcripts[:5]) if transcripts else "(no recent transcripts found)"
    return (
        f"# Current agent — {agent['name']}\n\n"
        f"## Description\n{agent['description']}\n\n"
        f"## Tools\n{', '.join(agent['tools']) or '(none)'}\n\n"
        f"## Model\n{agent['model']}\n\n"
        f"## System prompt body\n{agent['systemPrompt']}\n\n"
        f"# Objective (the human's stated goal for this agent)\n{objective or '(none provided)'}\n\n"
        f"# Refine targets\n{', '.join(targets)}\n\n"
        f"# Recent transcripts (sample)\n{sample}\n\n"
        "Return the JSON object now."
    )


def _parse_proposal(text: str) -> dict:
    """Extract the JSON object from the meta-LLM response, tolerating leading
    or trailing prose."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    return {}


def apply_proposal(name: str, proposal: dict, *,
                   trigger: str = "manual",
                   provider: str = "",
                   model: str = "",
                   cost_usd: float = 0.0,
                   tokens: int = 0,
                   targets: list | None = None,
                   dry_run: bool = False) -> dict:
    """Apply a meta-LLM proposal to the agent file. Always records to history."""
    ok, why = _is_writable_agent(name)
    if not ok:
        return {"ok": False, "error": why}

    cur = _read_agent_file(name)
    if "error" in cur:
        return {"ok": False, "error": cur["error"]}

    meta = load_meta()
    agent_meta = meta["agents"].get(name) or _default_agent_meta()

    new_sys = proposal.get("newSystemPrompt") if isinstance(proposal, dict) else None
    new_tools = proposal.get("newTools") if isinstance(proposal, dict) else None
    new_desc = proposal.get("newDescription") if isinstance(proposal, dict) else None
    rationale = str((proposal or {}).get("rationale") or "")[:2000]
    score_before = (proposal or {}).get("scoreBefore")
    score_after = (proposal or {}).get("scoreAfter")

    targets = targets or agent_meta.get("refineTargets") or ["systemPrompt"]

    applied: list = []
    diff: dict = {}
    next_sys = cur["systemPrompt"]
    next_tools = list(cur["tools"])
    next_desc = cur["description"]

    if "systemPrompt" in targets and isinstance(new_sys, str) and new_sys.strip() and new_sys != cur["systemPrompt"]:
        diff["systemPrompt"] = {"before": cur["systemPrompt"], "after": new_sys}
        next_sys = new_sys
        applied.append("systemPrompt")
    if "tools" in targets and isinstance(new_tools, list):
        cleaned = [str(t) for t in new_tools if isinstance(t, (str, int))]
        if cleaned and cleaned != cur["tools"]:
            diff["tools"] = {"before": cur["tools"], "after": cleaned}
            next_tools = cleaned
            applied.append("tools")
    if "description" in targets and isinstance(new_desc, str) and new_desc.strip() and new_desc != cur["description"]:
        diff["description"] = {"before": cur["description"], "after": new_desc}
        next_desc = new_desc
        applied.append("description")

    ts = int(time.time() * 1000)
    backup_path = ""
    write_ok = True

    if not dry_run and applied:
        backup_path = _backup_agent(name, ts)
        write_ok = _write_agent_file(
            name,
            description=next_desc,
            model=cur["model"],
            tools=next_tools,
            system_prompt=next_sys,
        )

    entry = _coerce_history_entry({
        "ts":             ts,
        "trigger":        trigger,
        "provider":       provider,
        "model":          model,
        "rationale":      rationale,
        "appliedTargets": applied,
        "backupPath":     backup_path,
        "costUSD":        cost_usd,
        "tokens":         tokens,
        "scoreBefore":    score_before,
        "scoreAfter":     score_after,
        "dryRun":         dry_run,
        "diff":           diff,
    })

    if not dry_run and applied and write_ok:
        agent_meta["lastRefinedAt"] = ts
        agent_meta["totalRefinements"] = int(agent_meta.get("totalRefinements", 0)) + 1
        agent_meta["spentUSD"] = float(agent_meta.get("spentUSD", 0.0)) + float(cost_usd or 0.0)
        agent_meta["lastError"] = ""
    agent_meta["history"] = (agent_meta.get("history") or []) + [entry]
    agent_meta["history"] = agent_meta["history"][-100:]
    meta["agents"][name] = _coerce_agent_meta(agent_meta)
    save_meta(meta)

    return {
        "ok":          write_ok if (not dry_run and applied) else True,
        "applied":     applied,
        "dryRun":      dry_run,
        "diff":        diff,
        "rationale":   rationale,
        "backupPath":  backup_path,
        "scoreBefore": score_before,
        "scoreAfter":  score_after,
        "costUSD":     cost_usd,
        "tokens":      tokens,
    }


def _record_failure(name: str, err: str) -> None:
    meta = load_meta()
    a = meta["agents"].get(name) or _default_agent_meta()
    a["lastError"] = str(err)[:1000]
    a["history"] = (a.get("history") or []) + [_coerce_history_entry({
        "ts":      int(time.time() * 1000),
        "trigger": "manual",
        "error":   err,
    })]
    a["history"] = a["history"][-100:]
    meta["agents"][name] = _coerce_agent_meta(a)
    save_meta(meta)


def refine_agent(name: str, *, trigger: str = "manual",
                 dry_run: bool = False,
                 transcripts: list[str] | None = None) -> dict:
    """Main pipeline: load agent → call meta-LLM → apply proposal (or dry-run).

    ``transcripts`` is injected by the after-session worker; when omitted, no
    transcripts are passed (the meta-LLM still sees the agent definition + the
    objective and can refine generically).
    """
    ok, why = _is_writable_agent(name)
    if not ok:
        return {"ok": False, "error": why}

    cur = _read_agent_file(name)
    if "error" in cur:
        return {"ok": False, "error": cur["error"]}

    meta = load_meta()
    agent_meta = meta["agents"].get(name) or _default_agent_meta()
    if not agent_meta.get("enabled") and trigger != "manual":
        return {"ok": False, "error": "hyper-agent disabled for this agent"}

    spent = float(agent_meta.get("spentUSD") or 0.0)
    budget = float(agent_meta.get("budgetUSD") or 0.0)
    if budget > 0 and spent >= budget:
        return {"ok": False, "error": f"budget exhausted ({spent:.2f}/{budget:.2f} USD)"}

    targets = agent_meta.get("refineTargets") or ["systemPrompt"]
    objective = agent_meta.get("objective") or ""
    assignee = agent_meta.get("refineProvider") or "claude:opus"

    user_prompt = _build_meta_prompt(
        agent=cur,
        objective=objective,
        targets=targets,
        transcripts=transcripts or [],
    )

    try:
        from .ai_providers import execute_with_assignee
        resp = execute_with_assignee(
            assignee, user_prompt,
            system_prompt=_META_SYSTEM_PROMPT,
            timeout=180,
        )
    except Exception as e:
        _record_failure(name, f"meta-llm call failed: {e}")
        return {"ok": False, "error": f"meta-llm call failed: {e}"}

    if resp.status != "ok":
        _record_failure(name, f"meta-llm error: {resp.error}")
        return {"ok": False, "error": resp.error}

    proposal = _parse_proposal(resp.output)
    if not proposal:
        _record_failure(name, "could not parse JSON proposal")
        return {"ok": False, "error": "could not parse JSON proposal"}

    return apply_proposal(
        name, proposal,
        trigger=trigger,
        provider=resp.provider,
        model=resp.model,
        cost_usd=resp.cost_usd,
        tokens=resp.tokens_total,
        targets=targets,
        dry_run=dry_run,
    )


def rollback(name: str, version_ts: int) -> dict:
    """Restore the agent from a `.bak.md` snapshot. ``version_ts`` is the
    epoch_ms saved in the history entry's ``backupPath``."""
    ok, why = _is_writable_agent(name)
    if not ok:
        return {"ok": False, "error": why}
    bak = AGENTS_DIR / f"{name}.{int(version_ts)}.bak.md"
    if not bak.exists():
        return {"ok": False, "error": "backup not found"}
    target = AGENTS_DIR / f"{name}.md"
    try:
        ts = int(time.time() * 1000)
        _backup_agent(name, ts)
        target.write_bytes(bak.read_bytes())
    except Exception as e:
        return {"ok": False, "error": str(e)}

    meta = load_meta()
    a = meta["agents"].get(name) or _default_agent_meta()
    a["history"] = (a.get("history") or []) + [_coerce_history_entry({
        "ts":             ts,
        "trigger":        "rollback",
        "rationale":      f"rolled back to backup {version_ts}",
        "appliedTargets": ["systemPrompt", "tools", "description"],
        "backupPath":     str(bak),
    })]
    a["history"] = a["history"][-100:]
    meta["agents"][name] = _coerce_agent_meta(a)
    save_meta(meta)
    return {"ok": True, "restoredFrom": str(bak)}


# ───────── HTTP handlers ─────────

def api_hyper_list(query: dict) -> dict:
    return {"ok": True, **list_hyper()}


def api_hyper_get(name: str) -> dict:
    return {"ok": True, "name": name, "agent": get_hyper(name)}


def api_hyper_history(name: str) -> dict:
    return {"ok": True, **history(name)}


def api_hyper_toggle(body: dict) -> dict:
    body = body or {}
    name = str(body.get("name") or "")
    enabled = bool(body.get("enabled", False))
    if not name:
        return {"ok": False, "error": "name required"}
    return toggle_agent(name, enabled)


def api_hyper_configure(body: dict) -> dict:
    body = body or {}
    name = str(body.get("name") or "")
    if not name:
        return {"ok": False, "error": "name required"}
    patch = body.get("patch") if isinstance(body.get("patch"), dict) else {}
    return configure_agent(name, patch)


def api_hyper_refine_now(body: dict) -> dict:
    body = body or {}
    name = str(body.get("name") or "")
    if not name:
        return {"ok": False, "error": "name required"}
    dry = bool(body.get("dryRun", False))
    return refine_agent(name, trigger="manual", dry_run=dry)


def api_hyper_rollback(body: dict) -> dict:
    body = body or {}
    name = str(body.get("name") or "")
    try:
        ts = int(body.get("versionTs") or 0)
    except Exception:
        ts = 0
    if not name or not ts:
        return {"ok": False, "error": "name + versionTs required"}
    return rollback(name, ts)
