"""Agent Teams — pre-baked rosters of sub-agents to spawn together (v2.41.0).

A "team" is just a saved tuple of agent references plus a name and a free-form
description. The dashboard surfaces teams in the Agents tab; users build a team
once (e.g. "Frontend Crew" = ui-designer + frontend-dev + code-reviewer) and
then spawn every member with one click instead of hand-picking each time.

Design rules (mirrors prefs.py / hyper_agent.py):
- Whitelisted schema, strict per-key validation, atomic JSON writes.
- Members reference existing agents by ``(name, scope, cwd)``; the team store
  doesn't duplicate the agent body itself, so renaming or deleting an agent is
  visible immediately on the next list.
- Spawn does **not** run anything — it just returns the resolved member list
  + the canonical ``claude /agents <name>`` invocation per agent so the UI can
  hand the list to ``api_session_spawn`` (or the user can copy-paste).
"""
from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path
from typing import Any

from .agents import _BUILTIN_AGENTS, get_agent
from .config import _env_path
from .logger import log
from .utils import _safe_read, _safe_write


AGENT_TEAMS_PATH = _env_path(
    "CLAUDE_DASHBOARD_AGENT_TEAMS",
    Path.home() / ".claude-dashboard-agent-teams.json",
)


# ───────── Schema ─────────

_TEAM_ID_RE    = re.compile(r"^tm-[a-z0-9]{6,16}$")
# Allow plugin-style ids (`market:plugin:name`) too; agents.py uses the same shape.
_AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_:.-]{0,127}$")
_VALID_SCOPES  = {"global", "project", "builtin", "plugin"}


def _empty_store() -> dict:
    return {"version": 1, "teams": {}}


def _new_team_id() -> str:
    return f"tm-{secrets.token_hex(4)}"


def _coerce_member(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    if not name or not _AGENT_NAME_RE.match(name):
        return None
    scope = str(raw.get("scope") or "global")
    if scope not in _VALID_SCOPES:
        scope = "global"
    cwd  = str(raw.get("cwd") or "")[:1024]
    role = str(raw.get("role") or "")[:200]
    task = str(raw.get("task") or "")[:4000]   # default task prompt for spawn
    return {"name": name, "scope": scope, "cwd": cwd, "role": role, "task": task}


def _coerce_team(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    tid = str(raw.get("id") or "").strip()
    if not _TEAM_ID_RE.match(tid):
        return None
    name = str(raw.get("name") or "").strip()[:120]
    if not name:
        return None
    desc = str(raw.get("description") or "")[:1000]
    members_in = raw.get("agents") or []
    members: list = []
    if isinstance(members_in, list):
        for m in members_in:
            mm = _coerce_member(m)
            if mm:
                members.append(mm)
    if not members:
        return None
    try:
        created = int(raw.get("createdAt") or 0)
    except Exception:
        created = 0
    try:
        updated = int(raw.get("updatedAt") or 0)
    except Exception:
        updated = 0
    return {
        "id":          tid,
        "name":        name,
        "description": desc,
        "agents":      members,
        "createdAt":   created,
        "updatedAt":   updated,
    }


# ───────── Persistence ─────────

def load_store() -> dict:
    if not AGENT_TEAMS_PATH.exists():
        return _empty_store()
    raw = _safe_read(AGENT_TEAMS_PATH)
    if not raw:
        return _empty_store()
    try:
        data = json.loads(raw)
    except Exception as e:
        log.warning("agent-teams load failed: %s", e)
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    out = _empty_store()
    teams_in = data.get("teams") or {}
    if isinstance(teams_in, dict):
        for tid, entry in teams_in.items():
            te = _coerce_team(entry)
            if te:
                out["teams"][te["id"]] = te
    return out


def save_store(store: dict) -> bool:
    text = json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True)
    return _safe_write(AGENT_TEAMS_PATH, text)


# ───────── Agent existence check ─────────

def _agent_exists(member: dict) -> bool:
    """Best-effort verification: is this member's agent still on disk?"""
    name  = member.get("name") or ""
    scope = member.get("scope") or "global"
    cwd   = member.get("cwd")   or ""
    if scope == "builtin":
        return any(b["id"] == name for b in _BUILTIN_AGENTS)
    if scope == "project" and cwd:
        return (Path(cwd) / ".claude" / "agents" / f"{name}.md").exists()
    if scope == "plugin":
        try:
            a = get_agent(name)
            return bool(a) and "error" not in a
        except Exception:
            return False
    # global
    try:
        a = get_agent(name)
        return bool(a) and "error" not in a
    except Exception:
        return False


def _resolve_members(members: list[dict]) -> list[dict]:
    """Tag each member with `exists`."""
    return [{**m, "exists": _agent_exists(m)} for m in members]


# ───────── HTTP handlers ─────────

def api_agent_teams_list(query: dict) -> dict:
    store = load_store()
    teams = []
    for _, t in store["teams"].items():
        resolved = _resolve_members(t["agents"])
        teams.append({
            **t,
            "agents":       resolved,
            "missingCount": sum(1 for m in resolved if not m.get("exists")),
        })
    teams.sort(key=lambda x: -x.get("updatedAt", 0))
    return {"ok": True, "items": teams, "count": len(teams)}


def api_agent_teams_get(team_id: str) -> dict:
    store = load_store()
    team = store["teams"].get(team_id)
    if not team:
        return {"ok": False, "error": "team not found"}
    return {"ok": True, "team": {**team, "agents": _resolve_members(team["agents"])}}


def api_agent_teams_save(body: dict) -> dict:
    """Create or update.

    Body::
        { id?, name, description?, agents: [{name, scope, cwd?, role?, task?}] }

    Without ``id`` a new ``tm-<hex>`` is minted. With a known id the entry is
    updated in place.
    """
    body = body or {}
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}

    incoming = dict(body)
    tid = str(incoming.get("id") or "").strip()
    is_new = not tid
    if is_new:
        tid = _new_team_id()
    elif not _TEAM_ID_RE.match(tid):
        return {"ok": False, "error": "invalid team id"}

    name = str(incoming.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "name required"}
    members_in = incoming.get("agents") or []
    if not isinstance(members_in, list) or not members_in:
        return {"ok": False, "error": "at least one agent required"}

    now = int(time.time() * 1000)
    store = load_store()
    cur = store["teams"].get(tid) or {}
    raw_team = {
        "id":          tid,
        "name":        name,
        "description": str(incoming.get("description") or ""),
        "agents":      members_in,
        "createdAt":   cur.get("createdAt") if cur else now,
        "updatedAt":   now,
    }
    coerced = _coerce_team(raw_team)
    if not coerced:
        return {"ok": False, "error": "validation failed (no valid agents?)"}

    store["teams"][tid] = coerced
    if not save_store(store):
        return {"ok": False, "error": "write failed"}
    return {
        "ok":    True,
        "team":  {**coerced, "agents": _resolve_members(coerced["agents"])},
        "isNew": is_new,
    }


def api_agent_teams_delete(body: dict) -> dict:
    body = body or {}
    tid = str(body.get("id") or "").strip()
    if not _TEAM_ID_RE.match(tid):
        return {"ok": False, "error": "invalid team id"}
    store = load_store()
    if tid not in store["teams"]:
        return {"ok": False, "error": "team not found"}
    del store["teams"][tid]
    if not save_store(store):
        return {"ok": False, "error": "write failed"}
    return {"ok": True}


def api_agent_teams_spawn(body: dict) -> dict:
    """Resolve a team's members into per-agent spawn descriptors.

    Returns one entry per existing member with the canonical Claude Code
    invocation. The frontend either drives ``api_session_spawn`` per entry
    or shows them as copy-pasteable commands. Missing members are surfaced
    in ``skipped`` so the caller can warn.

    Body::
        { id, cwd?, prompt? }   # cwd/prompt override the team's defaults
    """
    body = body or {}
    tid = str(body.get("id") or "").strip()
    if not _TEAM_ID_RE.match(tid):
        return {"ok": False, "error": "invalid team id"}
    store = load_store()
    team = store["teams"].get(tid)
    if not team:
        return {"ok": False, "error": "team not found"}

    override_cwd    = str(body.get("cwd") or "").strip()
    override_prompt = str(body.get("prompt") or "").strip()

    spawn_descs: list = []
    skipped:     list = []
    for m in team["agents"]:
        if not _agent_exists(m):
            skipped.append({"name": m.get("name"), "reason": "agent not found on disk"})
            continue
        cwd    = override_cwd    or m.get("cwd")  or ""
        prompt = override_prompt or m.get("task") or ""
        spawn_descs.append({
            "name":      m.get("name"),
            "scope":     m.get("scope"),
            "role":      m.get("role"),
            "cwd":       cwd,
            "prompt":    prompt,
            "claudeCmd": _build_claude_cmd(m.get("name"), prompt),
        })
    return {"ok": True, "teamId": tid, "spawn": spawn_descs, "skipped": skipped}


def _build_claude_cmd(agent_name: str, prompt: str) -> str:
    """Compose the canonical CLI invocation. The dashboard's ``api_session_spawn``
    handles cwd, so this is the visual copy-paste form for the user."""
    name = (agent_name or "").strip()
    p = (prompt or "").replace('"', '\\"')
    if not p:
        return f'claude /agents {name}'
    return f'claude /agents {name} "{p}"'
