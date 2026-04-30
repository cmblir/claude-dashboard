"""Hyper Agent — sub-agents that self-refine their own settings over time.

A "hyper" sub-agent is a regular Claude Code agent (`<scope>/agents/<name>.md`)
with an opt-in supervisor that periodically asks a meta-LLM (Opus by default)
to propose refinements to its system prompt, tool list, and description, given
the user's stated objective and recent transcripts. Each proposal is applied
atomically with a `.bak.md` backup so any iteration is reversible.

Scope:
- ``cwd=None`` → global writeable agent at ``~/.claude/agents/<name>.md``.
- ``cwd=<path>`` → project-scoped agent at ``<cwd>/.claude/agents/<name>.md``.
  (v2.40.0)

Storage:
- Agent body itself stays in its scope-native ``.md`` (Claude Code compatible,
  no schema change).
- Meta + history live in ``~/.claude-dashboard-hyper-agents.json`` keyed by a
  composite ``<scope>:<id>``:
    * global: ``global:<name>``
    * project: ``project:<sha8(cwd)>:<name>``
  Legacy flat keys (``<name>`` alone, written by v2.39.0) are still recognised
  on read as global; subsequent writes use the canonical composite form.
- Per-iteration backup at ``<scope>/agents/<name>.<ts>.bak.md``.

Public API (all accept ``cwd: str | None = None`` for project scope):
- ``configure_agent(name, patch, cwd=None)``
- ``refine_agent(name, *, trigger, dry_run=False, cwd=None, transcripts=None)``
- ``apply_proposal(name, proposal, *, ..., cwd=None)``
- ``rollback(name, version_ts, cwd=None)``
- ``list_hyper()`` / ``get_hyper(name, cwd=None)`` / ``history(name, cwd=None)``
- ``api_*`` HTTP entrypoints registered by ``server/routes.py``.

The actual after-session / cron triggers live in ``server/hyper_agent_worker.py``.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from .agents import _BUILTIN_AGENTS, get_agent
from .config import AGENTS_DIR, _env_path
from .logger import log
from .utils import (
    _parse_frontmatter, _parse_tools_field,
    _safe_read, _safe_write, _strip_frontmatter,
)


HYPER_AGENTS_PATH = _env_path(
    "CLAUDE_DASHBOARD_HYPER_AGENTS",
    Path.home() / ".claude-dashboard-hyper-agents.json",
)


# ───────── Schema ─────────

_VALID_TARGETS = {"systemPrompt", "tools", "description"}
_VALID_TRIGGERS = {"manual", "after_session", "cron", "any", "interval"}
_AGENT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
# Composite key shapes — global:NAME or project:HEX:NAME (HEX = sha1[:8])
_COMPOSITE_KEY_RE = re.compile(
    r"^(?:global:[a-z0-9][a-z0-9_-]{0,63}"
    r"|project:[0-9a-f]{8}:[a-z0-9][a-z0-9_-]{0,63})$"
)


def _empty_meta() -> dict:
    return {"version": 2, "agents": {}}


def _default_agent_meta() -> dict:
    return {
        "scope":              "global",   # "global" | "project"
        "cwd":                "",          # set when scope == "project"
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

    scope = str(raw.get("scope") or "global")
    out["scope"] = scope if scope in ("global", "project") else "global"
    out["cwd"] = str(raw.get("cwd") or "")[:1024]

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


# ───────── Composite-key helpers ─────────

def _cwd_hash(cwd: str) -> str:
    """8-char sha1 of an absolute cwd. Stable for a given path string."""
    return hashlib.sha1(str(cwd).encode("utf-8")).hexdigest()[:8]


def _agent_key(name: str, cwd: str | None = None) -> str:
    """Canonical composite key used in the meta JSON."""
    if cwd:
        return f"project:{_cwd_hash(cwd)}:{name}"
    return f"global:{name}"


def _legacy_flat_key(name: str) -> str:
    """v2.39.0 wrote bare ``<name>`` for global agents. Keep recognising it."""
    return name


def _resolve_meta_key(meta: dict, name: str, cwd: str | None = None) -> str:
    """Return the actual key under which this agent's meta is stored.

    Preference order:
      1. canonical composite key (post-v2.40.0 writes use this)
      2. legacy flat key (v2.39.0 writes — only meaningful when cwd is None)
      3. canonical composite key (used as the *write* target for new entries)
    """
    canonical = _agent_key(name, cwd)
    agents = (meta or {}).get("agents") or {}
    if canonical in agents:
        return canonical
    if not cwd and _legacy_flat_key(name) in agents:
        return _legacy_flat_key(name)
    return canonical


def _agents_dir(cwd: str | None) -> Path:
    """Return the directory holding the .md file for this agent's scope."""
    if cwd:
        return Path(cwd) / ".claude" / "agents"
    return AGENTS_DIR


# ───────── Persistence ─────────

def load_meta() -> dict:
    """Return meta with defaults applied for every entry. Safe even on missing
    or corrupted file. Both legacy flat keys and v2.40 composite keys are kept
    intact — callers use ``_resolve_meta_key`` to look up either form."""
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
        for key, entry in agents_in.items():
            key_s = str(key)
            # Accept either composite or legacy flat (legal agent name) keys.
            if not (_COMPOSITE_KEY_RE.match(key_s) or _AGENT_NAME_RE.match(key_s)):
                continue
            out["agents"][key_s] = _coerce_agent_meta(entry)
    return out


def save_meta(meta: dict) -> bool:
    text = json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True)
    return _safe_write(HYPER_AGENTS_PATH, text)


def get_hyper(name: str, cwd: str | None = None) -> dict:
    """Return the meta for a single agent, creating defaults if absent."""
    m = load_meta()
    key = _resolve_meta_key(m, name, cwd)
    entry = m["agents"].get(key) or _default_agent_meta()
    # Ensure scope/cwd reflect the lookup even for legacy entries.
    if cwd:
        entry["scope"] = "project"
        entry["cwd"] = cwd
    elif entry.get("scope") != "project":
        entry["scope"] = "global"
        entry["cwd"] = ""
    return entry


def _parse_key(key: str) -> tuple[str, str]:
    """Return (scope, name) from a key. ``cwd`` itself isn't recoverable from
    the hash, so callers that need it must look at ``entry['cwd']``."""
    if key.startswith("global:"):
        return "global", key[len("global:"):]
    if key.startswith("project:"):
        rest = key[len("project:"):]
        parts = rest.split(":", 1)
        if len(parts) == 2:
            return "project", parts[1]
    # legacy flat
    return "global", key


def list_hyper() -> dict:
    """List all agents with hyper meta (enabled or not)."""
    m = load_meta()
    items = []
    for key, entry in m["agents"].items():
        scope_from_key, name = _parse_key(key)
        # Prefer entry-level scope/cwd when present; otherwise derive from key.
        scope = entry.get("scope") or scope_from_key
        cwd = entry.get("cwd") or ""
        items.append({
            "key":               key,
            "name":              name,
            "scope":             scope,
            "cwd":               cwd,
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
    items.sort(key=lambda r: (-int(r["enabled"]), -r["lastRefinedAt"], r["scope"], r["name"]))
    return {"items": items, "count": len(items)}


def history(name: str, cwd: str | None = None) -> dict:
    entry = get_hyper(name, cwd)
    return {"name": name, "cwd": cwd or "", "history": entry.get("history", [])}


# ───────── Configuration ─────────

def _is_writable_agent(name: str, cwd: str | None = None) -> tuple[bool, str]:
    """Hyper Agent only applies to writeable agents — skip builtin / plugin /
    unknown / nonexistent files. Project scope is always writeable when the
    file exists."""
    if not _AGENT_NAME_RE.match(name):
        return False, "invalid agent name"
    if not cwd:
        # Global scope guards
        for b in _BUILTIN_AGENTS:
            if b["id"] == name:
                return False, "builtin agent is read-only"
        if ":" in name:
            return False, "plugin agent is read-only"
    p = _agents_dir(cwd) / f"{name}.md"
    if not p.exists():
        return False, "agent file not found"
    return True, ""


def configure_agent(name: str, patch: dict, cwd: str | None = None) -> dict:
    """Set objective / targets / trigger / budget for an agent. Creates the
    meta entry on first call."""
    ok, why = _is_writable_agent(name, cwd)
    if not ok:
        return {"ok": False, "error": why}
    meta = load_meta()
    canonical = _agent_key(name, cwd)
    legacy = _resolve_meta_key(meta, name, cwd)
    cur = meta["agents"].get(legacy) or _default_agent_meta()
    merged = dict(cur)
    if isinstance(patch, dict):
        merged.update(patch)
    # Always force scope/cwd to match the call — patch can't override these.
    merged["scope"] = "project" if cwd else "global"
    merged["cwd"] = cwd or ""
    merged = _coerce_agent_meta(merged)
    # Migrate legacy flat key → canonical composite on first write.
    if legacy != canonical and legacy in meta["agents"]:
        meta["agents"].pop(legacy, None)
    meta["agents"][canonical] = merged
    return {"ok": save_meta(meta), "agent": merged}


def toggle_agent(name: str, enabled: bool, cwd: str | None = None) -> dict:
    return configure_agent(name, {"enabled": bool(enabled)}, cwd=cwd)


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


def _read_agent_file(name: str, cwd: str | None = None) -> dict:
    """Read the agent .md file and return parsed parts.

    Global scope reuses ``server.agents.get_agent``. Project scope reads the
    file directly with ``_safe_read`` + ``_parse_frontmatter`` to avoid
    crossing into builtin/plugin lookup paths.
    """
    if cwd:
        p = _agents_dir(cwd) / f"{name}.md"
        if not p.exists():
            return {"error": "agent file not found"}
        raw = _safe_read(p)
        if raw is None:
            return {"error": "agent file unreadable"}
        meta = _parse_frontmatter(raw)
        return {
            "name":          meta.get("name", name),
            "description":   meta.get("description", ""),
            "model":         meta.get("model", "inherit"),
            "tools":         _parse_tools_field(meta.get("tools", "")),
            "systemPrompt":  _strip_frontmatter(raw),
            "raw":           raw,
            "path":          str(p),
        }
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
                      system_prompt: str,
                      cwd: str | None = None) -> bool:
    """Re-emit ``<scope>/agents/<name>.md`` from parts."""
    p = _agents_dir(cwd) / f"{name}.md"
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
    p.parent.mkdir(parents=True, exist_ok=True)
    return _safe_write(p, raw)


def _backup_agent(name: str, ts_ms: int, cwd: str | None = None) -> str:
    """Copy current agent file to ``<name>.<ts>.bak.md`` before overwriting.
    Returns the backup path (string), or empty string on failure."""
    src = _agents_dir(cwd) / f"{name}.md"
    if not src.exists():
        return ""
    dst = _agents_dir(cwd) / f"{name}.{ts_ms}.bak.md"
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
                   dry_run: bool = False,
                   cwd: str | None = None) -> dict:
    """Apply a meta-LLM proposal to the agent file. Always records to history."""
    ok, why = _is_writable_agent(name, cwd)
    if not ok:
        return {"ok": False, "error": why}

    cur = _read_agent_file(name, cwd)
    if "error" in cur:
        return {"ok": False, "error": cur["error"]}

    meta = load_meta()
    canonical = _agent_key(name, cwd)
    legacy = _resolve_meta_key(meta, name, cwd)
    agent_meta = meta["agents"].get(legacy) or _default_agent_meta()
    agent_meta["scope"] = "project" if cwd else "global"
    agent_meta["cwd"] = cwd or ""

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
        backup_path = _backup_agent(name, ts, cwd=cwd)
        write_ok = _write_agent_file(
            name,
            description=next_desc,
            model=cur["model"],
            tools=next_tools,
            system_prompt=next_sys,
            cwd=cwd,
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
    if legacy != canonical and legacy in meta["agents"]:
        meta["agents"].pop(legacy, None)
    meta["agents"][canonical] = _coerce_agent_meta(agent_meta)
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
        "scope":       "project" if cwd else "global",
        "cwd":         cwd or "",
    }


def _record_failure(name: str, err: str, cwd: str | None = None) -> None:
    meta = load_meta()
    canonical = _agent_key(name, cwd)
    legacy = _resolve_meta_key(meta, name, cwd)
    a = meta["agents"].get(legacy) or _default_agent_meta()
    a["scope"] = "project" if cwd else "global"
    a["cwd"] = cwd or ""
    a["lastError"] = str(err)[:1000]
    a["history"] = (a.get("history") or []) + [_coerce_history_entry({
        "ts":      int(time.time() * 1000),
        "trigger": "manual",
        "error":   err,
    })]
    a["history"] = a["history"][-100:]
    if legacy != canonical and legacy in meta["agents"]:
        meta["agents"].pop(legacy, None)
    meta["agents"][canonical] = _coerce_agent_meta(a)
    save_meta(meta)


def refine_agent(name: str, *, trigger: str = "manual",
                 dry_run: bool = False,
                 transcripts: list[str] | None = None,
                 cwd: str | None = None) -> dict:
    """Main pipeline: load agent → call meta-LLM → apply proposal (or dry-run).

    ``transcripts`` is injected by the after-session worker; when omitted, no
    transcripts are passed (the meta-LLM still sees the agent definition + the
    objective and can refine generically).
    """
    ok, why = _is_writable_agent(name, cwd)
    if not ok:
        return {"ok": False, "error": why}

    cur = _read_agent_file(name, cwd)
    if "error" in cur:
        return {"ok": False, "error": cur["error"]}

    meta = load_meta()
    legacy = _resolve_meta_key(meta, name, cwd)
    agent_meta = meta["agents"].get(legacy) or _default_agent_meta()
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
        _record_failure(name, f"meta-llm call failed: {e}", cwd=cwd)
        return {"ok": False, "error": f"meta-llm call failed: {e}"}

    if resp.status != "ok":
        _record_failure(name, f"meta-llm error: {resp.error}", cwd=cwd)
        return {"ok": False, "error": resp.error}

    proposal = _parse_proposal(resp.output)
    if not proposal:
        _record_failure(name, "could not parse JSON proposal", cwd=cwd)
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
        cwd=cwd,
    )


def rollback(name: str, version_ts: int, cwd: str | None = None) -> dict:
    """Restore the agent from a `.bak.md` snapshot. ``version_ts`` is the
    epoch_ms saved in the history entry's ``backupPath``."""
    ok, why = _is_writable_agent(name, cwd)
    if not ok:
        return {"ok": False, "error": why}
    bak = _agents_dir(cwd) / f"{name}.{int(version_ts)}.bak.md"
    if not bak.exists():
        return {"ok": False, "error": "backup not found"}
    target = _agents_dir(cwd) / f"{name}.md"
    try:
        ts = int(time.time() * 1000)
        _backup_agent(name, ts, cwd=cwd)
        target.write_bytes(bak.read_bytes())
    except Exception as e:
        return {"ok": False, "error": str(e)}

    meta = load_meta()
    canonical = _agent_key(name, cwd)
    legacy = _resolve_meta_key(meta, name, cwd)
    a = meta["agents"].get(legacy) or _default_agent_meta()
    a["scope"] = "project" if cwd else "global"
    a["cwd"] = cwd or ""
    a["history"] = (a.get("history") or []) + [_coerce_history_entry({
        "ts":             ts,
        "trigger":        "rollback",
        "rationale":      f"rolled back to backup {version_ts}",
        "appliedTargets": ["systemPrompt", "tools", "description"],
        "backupPath":     str(bak),
    })]
    a["history"] = a["history"][-100:]
    if legacy != canonical and legacy in meta["agents"]:
        meta["agents"].pop(legacy, None)
    meta["agents"][canonical] = _coerce_agent_meta(a)
    save_meta(meta)
    return {"ok": True, "restoredFrom": str(bak)}


# ───────── Auto-Resume advisor ─────────

_AR_ADVISOR_SYSTEM_PROMPT = """You are an Auto-Resume advisor. Given a Claude Code
session that has been retrying with the same exit reason, propose surgical
adjustments to the retry policy. Output ONLY valid JSON matching this schema:
{
  "pollIntervalSec": int,        // suggested polling interval (60-1800)
  "maxAttempts": int,            // suggested max retries (1-50)
  "promptHint": str,              // suggested user-prompt prepend (or "")
  "rationale": str                // 1-2 sentence explanation
}
Decision rules:
- rate_limit → increase pollInterval to 600+, keep maxAttempts unchanged
- context_full → suggest "/clear and continue" or "summarize prior context" promptHint
- auth_expired → keep retrying low-frequency (pollInterval=300), short rationale telling user to run /login
- unknown with high failure rate → reduce maxAttempts, suggest manual review
"""


def _build_ar_advisor_prompt(entry: dict, recent_failures: list[dict]) -> str:
    """Compose a compact user prompt summarising the AR entry + last failures."""
    sid = (entry.get("sessionId") or "")[:64]
    state = entry.get("state") or ""
    poll = entry.get("pollInterval") or 0
    max_attempts = entry.get("maxAttempts") or 0
    attempts = entry.get("attempts") or 0
    last_reason = entry.get("lastExitReason") or ""
    last_error = (entry.get("lastError") or "")[-400:]

    lines = [
        "Auto-Resume session needs a policy adjustment.",
        f"sessionId: {sid}",
        f"state: {state}",
        f"attempts: {attempts}/{max_attempts}",
        f"pollIntervalSec: {poll}",
        f"lastExitReason: {last_reason}",
    ]
    if last_error:
        lines.append(f"lastError(tail): {last_error}")

    lines.append("")
    lines.append("Recent failures (most recent last):")
    for f in recent_failures:
        at = f.get("at") or 0
        att = f.get("attempt") or 0
        reason = f.get("exitReason") or ""
        notes = (f.get("notes") or "")[:200]
        lines.append(f"- attempt={att} at={at} reason={reason} notes={notes}")

    lines.append("")
    lines.append("Return JSON only — no prose.")
    return "\n".join(lines)


def hyper_advise_auto_resume(entry: dict, recent_failures: list[dict],
                             assignee: str = "claude:haiku") -> dict:
    """Ask meta-LLM for retry-policy adjustments given an AR entry's failure pattern.

    Returns ``{ok: bool, advice: dict | None, error: str | None, cost_usd: float}``.
    Uses Haiku by default (fast + cheap; advice is structural, not creative).
    """
    # Pre-call validation — short-circuit before spending tokens.
    if not isinstance(entry, dict):
        return {"ok": False, "advice": None, "error": "entry must be object", "cost_usd": 0.0}
    if entry.get("state") in ("done", "stopped"):
        return {"ok": False, "advice": None,
                "error": "Session not actively retrying", "cost_usd": 0.0}
    if not isinstance(recent_failures, list) or len(recent_failures) < 2:
        return {"ok": False, "advice": None,
                "error": "Not enough failure history (need >=2)", "cost_usd": 0.0}

    user_prompt = _build_ar_advisor_prompt(entry, recent_failures)

    try:
        from .ai_providers import execute_with_assignee
        resp = execute_with_assignee(
            assignee, user_prompt,
            system_prompt=_AR_ADVISOR_SYSTEM_PROMPT,
            timeout=180,
        )
    except Exception as e:
        return {"ok": False, "advice": None,
                "error": f"meta-llm call failed: {e}", "cost_usd": 0.0}

    cost = float(getattr(resp, "cost_usd", 0.0) or 0.0)
    if getattr(resp, "status", "") != "ok":
        return {"ok": False, "advice": None,
                "error": getattr(resp, "error", "unknown"), "cost_usd": cost}

    proposal = _parse_proposal(getattr(resp, "output", "") or "")
    if not proposal:
        return {"ok": False, "advice": None,
                "error": "could not parse JSON proposal", "cost_usd": cost}

    # After-call sanitisation / clamping.
    try:
        poll_iv = int(proposal.get("pollIntervalSec") or 0)
    except Exception:
        poll_iv = 0
    if poll_iv <= 0:
        poll_iv = int(entry.get("pollInterval") or 300)
    poll_iv = max(60, min(1800, poll_iv))

    try:
        max_att = int(proposal.get("maxAttempts") or 0)
    except Exception:
        max_att = 0
    if max_att <= 0:
        max_att = int(entry.get("maxAttempts") or 12)
    max_att = max(1, min(50, max_att))

    prompt_hint = str(proposal.get("promptHint") or "")[:500]
    rationale = str(proposal.get("rationale") or "")[:300]

    advice = {
        "pollIntervalSec": poll_iv,
        "maxAttempts":     max_att,
        "promptHint":      prompt_hint,
        "rationale":       rationale,
        "provider":        getattr(resp, "provider", "") or "",
        "model":           getattr(resp, "model", "") or "",
    }
    return {"ok": True, "advice": advice, "error": None, "cost_usd": cost}


# ───────── HTTP handlers ─────────

def _body_cwd(body: dict) -> str | None:
    """Extract optional ``cwd`` from a request body. Empty string → None."""
    if not isinstance(body, dict):
        return None
    cwd = body.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return cwd.strip()
    return None


def api_hyper_list(query: dict) -> dict:
    return {"ok": True, **list_hyper()}


def api_hyper_get(name: str) -> dict:
    """Path-param GET for global agents only. Project-scoped agents are
    fetched via the POST endpoint below to avoid encoding cwd in the URL."""
    return {"ok": True, "name": name, "agent": get_hyper(name)}


def api_hyper_get_post(body: dict) -> dict:
    """POST /api/hyper-agents/get — body: {name, cwd?}.

    Required for project-scoped lookups since cwd doesn't fit cleanly in a
    URL path parameter."""
    body = body or {}
    name = str(body.get("name") or "")
    if not name:
        return {"ok": False, "error": "name required"}
    cwd = _body_cwd(body)
    return {"ok": True, "name": name, "cwd": cwd or "", "agent": get_hyper(name, cwd)}


def api_hyper_history(name: str) -> dict:
    return {"ok": True, **history(name)}


def api_hyper_history_post(body: dict) -> dict:
    """POST /api/hyper-agents/history — body: {name, cwd?}."""
    body = body or {}
    name = str(body.get("name") or "")
    if not name:
        return {"ok": False, "error": "name required"}
    cwd = _body_cwd(body)
    return {"ok": True, **history(name, cwd)}


def api_hyper_toggle(body: dict) -> dict:
    body = body or {}
    name = str(body.get("name") or "")
    enabled = bool(body.get("enabled", False))
    if not name:
        return {"ok": False, "error": "name required"}
    return toggle_agent(name, enabled, cwd=_body_cwd(body))


def api_hyper_configure(body: dict) -> dict:
    body = body or {}
    name = str(body.get("name") or "")
    if not name:
        return {"ok": False, "error": "name required"}
    patch = body.get("patch") if isinstance(body.get("patch"), dict) else {}
    return configure_agent(name, patch, cwd=_body_cwd(body))


def api_hyper_refine_now(body: dict) -> dict:
    body = body or {}
    name = str(body.get("name") or "")
    if not name:
        return {"ok": False, "error": "name required"}
    dry = bool(body.get("dryRun", False))
    return refine_agent(name, trigger="manual", dry_run=dry, cwd=_body_cwd(body))


def api_hyper_rollback(body: dict) -> dict:
    body = body or {}
    name = str(body.get("name") or "")
    try:
        ts = int(body.get("versionTs") or 0)
    except Exception:
        ts = 0
    if not name or not ts:
        return {"ok": False, "error": "name + versionTs required"}
    return rollback(name, ts, cwd=_body_cwd(body))
