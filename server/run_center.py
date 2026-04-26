"""Run Center — unified catalog + executor for ECC skills, ECC slash commands,
OMC modes, OMX commands.

Why: ECC v1.10 ships 181 skills + 79 slash commands. OMC contributed 4 named
modes (autopilot / ralph / ultrawork / deep-interview) which are already
present as built-in workflow templates. Until v2.36 the dashboard could only
*see* skills/commands (read-only list) — to actually invoke them users had to
go into Claude Code itself. Run Center wires them up to the existing
`execute_with_assignee` pipeline so a single dashboard click runs the skill.

Surfaces three things over HTTP:
- `GET  /api/run/catalog`            — all runnable items (filterable by source).
- `POST /api/run/execute`            — run an item with a goal, return result.
- `GET  /api/run/history`            — recent runs (per-user SQLite).
- `GET  /api/run/favorites`          — favorite item IDs.
- `POST /api/run/favorite/toggle`    — toggle a favorite.

The executor is **NOT** a session spawn — it is a one-shot prompt execution
through `execute_with_assignee`, same as a workflow `session` node. The result
comes back as JSON. For long-running flows users are pointed at the workflow
templates (Quick Actions in Phase 3 do that hand-off).
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .config import _env_path
from .db import _db
from .logger import log
from .utils import _safe_read

# ── Storage ──────────────────────────────────────────────────────────────────

RUN_CENTER_FAV_PATH = _env_path(
    "CLAUDE_DASHBOARD_RUN_FAVORITES",
    Path.home() / ".claude-dashboard-run-favorites.json",
)


def _ensure_history_table() -> None:
    """Create the `run_history` table if missing. Idempotent."""
    try:
        with _db() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS run_history (
              id TEXT PRIMARY KEY,
              source TEXT,
              item_id TEXT,
              item_name TEXT,
              goal TEXT,
              assignee TEXT,
              status TEXT,
              output TEXT,
              error TEXT,
              tokens_in INTEGER DEFAULT 0,
              tokens_out INTEGER DEFAULT 0,
              cost_usd REAL DEFAULT 0.0,
              duration_ms INTEGER DEFAULT 0,
              ts INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_runhist_ts ON run_history(ts DESC);
            CREATE INDEX IF NOT EXISTS idx_runhist_item ON run_history(source, item_id);
            """)
    except Exception as e:
        log.warning("run_history table init failed: %s", e)


_ensure_history_table()


# ── Catalog: ECC skills + ECC commands ──────────────────────────────────────

# Where the ECC plugin lives once installed via `claude plugin install ecc`.
# Path is computed dynamically because the version in the directory changes.
_ECC_PLUGIN_GLOB_ROOTS = [
    Path.home() / ".claude" / "plugins" / "cache" / "ecc" / "ecc",
    # Fallback: if marketplaces/ has a synced copy.
    Path.home() / ".claude" / "plugins" / "marketplaces" / "ecc",
]


def _ecc_root() -> Optional[Path]:
    """Find the latest installed ECC plugin path. Returns None if not installed."""
    for base in _ECC_PLUGIN_GLOB_ROOTS:
        if not base.exists():
            continue
        # Pick the highest-version subdirectory.
        candidates = [p for p in base.iterdir() if p.is_dir() and (p / "skills").exists()]
        if candidates:
            candidates.sort(key=lambda p: p.name, reverse=True)
            return candidates[0]
    return None


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body) from a markdown document."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    block = m.group(1)
    fm: dict = {}
    for line in block.splitlines():
        kv = re.match(r"^(\w[\w-]*):\s*(.*)$", line.strip())
        if kv:
            v = kv.group(2).strip().strip('"').strip("'")
            fm[kv.group(1)] = v
    return fm, text[m.end():]


def _categorize_skill(name: str, description: str) -> str:
    """Best-effort tag a skill into a coarse category for filter chips."""
    low = (name + " " + description).lower()
    if any(k in low for k in ("frontend", "react", "ui", "css", "tailwind", "next", "nuxt", "vue", "svelte")):
        return "frontend"
    if any(k in low for k in ("backend", "api", "server", "rest", "django", "spring", "laravel", "nestjs", "fastapi")):
        return "backend"
    if any(k in low for k in ("test", "tdd", "pytest", "jest", "junit", "kotest", "kotlinstest", "playwright", "e2e")):
        return "testing"
    if any(k in low for k in ("review", "lint", "code-review", "quality")):
        return "review"
    if any(k in low for k in ("security", "owasp", "vuln", "auth", "secret", "csrf", "xss")):
        return "security"
    if any(k in low for k in ("deploy", "docker", "k8s", "ci/cd", "ops", "kubernetes")):
        return "ops"
    if any(k in low for k in ("ai", "llm", "claude", "agent", "embed", "prompt", "rag")):
        return "ai"
    if any(k in low for k in ("data", "sql", "database", "etl", "analytics", "postgres", "clickhouse", "mongo")):
        return "data"
    if any(k in low for k in ("ml", "pytorch", "tensorflow", "training", "model")):
        return "ml"
    if any(k in low for k in ("mobile", "android", "ios", "flutter", "swift", "kotlin")):
        return "mobile"
    return "general"


def _list_ecc_skills(root: Path) -> list[dict]:
    """Read every SKILL.md under <root>/skills/<name>/SKILL.md."""
    out = []
    skills_dir = root / "skills"
    if not skills_dir.exists():
        return out
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        sf = child / "SKILL.md"
        if not sf.exists():
            continue
        try:
            text = _safe_read(sf, limit=4_000)
            fm, _ = _parse_frontmatter(text)
        except Exception:
            continue
        name = fm.get("name") or child.name
        desc = fm.get("description") or ""
        out.append({
            "id":          f"ecc:skill:{child.name}",
            "source":      "ecc",
            "kind":        "skill",
            "name":        name,
            "description": desc,
            "category":    _categorize_skill(name, desc),
            "invocation":  f"Use the `{name}` skill",
            "tools":       fm.get("tools", ""),
            "path":        str(sf),
        })
    return out


def _list_ecc_commands(root: Path) -> list[dict]:
    """Read every commands/*.md."""
    out = []
    cdir = root / "commands"
    if not cdir.exists():
        return out
    for fp in sorted(cdir.glob("*.md")):
        try:
            text = _safe_read(fp, limit=4_000)
            fm, _ = _parse_frontmatter(text)
        except Exception:
            continue
        cname = fm.get("name") or fp.stem
        desc = fm.get("description") or ""
        out.append({
            "id":          f"ecc:cmd:{cname}",
            "source":      "ecc",
            "kind":        "command",
            "name":        f"/{cname}",
            "description": desc,
            "category":    _categorize_skill(cname, desc),
            "invocation":  f"Run the slash command /{cname}",
            "path":        str(fp),
        })
    return out


# ── OMC modes ───────────────────────────────────────────────────────────────
# These four are already shipped as built-in workflow templates (bt-*); the
# Run Center exposes them as quick-shot one-prompt items so users don't have
# to scaffold a workflow. The execution path for these is "one shot to the
# Planner" rather than a full multi-stage DAG.

OMC_MODES = [
    {
        "id":   "omc:autopilot",
        "source": "omc", "kind": "mode",
        "name": "/autopilot",
        "description": (
            "OMC mode — single uninterrupted flow: requirements → plan → execute → "
            "verify. No mid-flight confirmations. Maps to the `bt-autopilot` template; "
            "one-shot run here just dispatches to Planner."
        ),
        "category": "ai",
        "invocation": (
            "You are running in OMC autopilot mode. Decompose the user's goal into a "
            "checklist, execute each step in sequence, then verify the result. Do not "
            "stop for confirmation; surface blockers explicitly only when truly stuck."
        ),
        "workflow_template_id": "bt-autopilot",
    },
    {
        "id":   "omc:ralph",
        "source": "omc", "kind": "mode",
        "name": "/ralph",
        "description": (
            "OMC mode — verify → fix loop until pass. The full DAG is at `bt-ralph`; "
            "one-shot here runs verify and proposes the next fix."
        ),
        "category": "ai",
        "invocation": (
            "You are running in OMC ralph mode. Verify the user's goal against the "
            "current state, then propose a single concrete fix that would move it "
            "closer to PASS. Do not implement — output the next-fix plan."
        ),
        "workflow_template_id": "bt-ralph",
    },
    {
        "id":   "omc:ultrawork",
        "source": "omc", "kind": "mode",
        "name": "/ultrawork",
        "description": (
            "OMC mode — 5 parallel agents → merge. Full DAG is at `bt-ultrawork`. "
            "One-shot here returns the dispatch plan (which agent owns what)."
        ),
        "category": "ai",
        "invocation": (
            "You are running in OMC ultrawork mode. Split the user's goal into 5 "
            "independent sub-tasks suitable for parallel agents (label them A-E), "
            "then specify the merge criterion. Do not execute — output the dispatch "
            "plan only."
        ),
        "workflow_template_id": "bt-ultrawork",
    },
    {
        "id":   "omc:deep-interview",
        "source": "omc", "kind": "mode",
        "name": "/deep-interview",
        "description": (
            "OMC mode — Socratic clarification before design. Full DAG is at "
            "`bt-deep-interview`. One-shot returns the clarification questions."
        ),
        "category": "ai",
        "invocation": (
            "You are running in OMC deep-interview mode. Ask the user 3-7 sharp "
            "Socratic questions that surface hidden assumptions, scope ambiguity, and "
            "non-functional constraints. Do not propose a solution yet."
        ),
        "workflow_template_id": "bt-deep-interview",
    },
]


# ── OMX commands ────────────────────────────────────────────────────────────
# OMX (oh-my-codex) is the Codex-targeted sibling of OMC. The dashboard does
# not run codex by default but several OMX patterns are useful as one-shot
# prompts dispatched to whichever provider the user picks.

OMX_COMMANDS = [
    {
        "id": "omx:doctor",
        "source": "omx", "kind": "diagnostic",
        "name": "$doctor",
        "description": "OMX-style install/health diagnostic — sweep the user's setup for missing tools and stale config.",
        "category": "ops",
        "invocation": (
            "You are running an OMX-style doctor pass. Inspect the project's health: "
            "missing dependencies, stale lockfiles, broken scripts, env mismatches. "
            "Output a checklist with status per item."
        ),
    },
    {
        "id": "omx:wiki-summarise",
        "source": "omx", "kind": "knowledge",
        "name": "$wiki",
        "description": "OMX wiki helper — distil the working context into a 1-page reference for future agents.",
        "category": "ai",
        "invocation": (
            "You are an OMX wiki summariser. Read the user's input and produce a "
            "concise reference document covering: purpose, key concepts, key files, "
            "current open questions. Markdown."
        ),
    },
    {
        "id": "omx:hud-snapshot",
        "source": "omx", "kind": "diagnostic",
        "name": "$hud",
        "description": "OMX hud snapshot — one-line live status of the project (where things are right now).",
        "category": "ops",
        "invocation": (
            "You are taking an OMX-style hud snapshot. Output one or two lines that "
            "tell a returning developer: current phase, last action, next blocker. "
            "No prose — bullet form."
        ),
    },
    {
        "id": "omx:tasks-extract",
        "source": "omx", "kind": "knowledge",
        "name": "$tasks",
        "description": "OMX-style task extraction — pull every actionable TODO/FIXME/BUG from the user's input.",
        "category": "ops",
        "invocation": (
            "You are extracting actionable tasks OMX-style. Scan the input and emit a "
            "JSON array of { title, priority, source_line }. Skip vague aspirations."
        ),
    },
]


_CATALOG_CACHE: dict = {"ts": 0, "items": []}
_CATALOG_TTL_S = 30


def _build_catalog() -> list[dict]:
    """Combine all sources. Cached for 30s to avoid re-reading 260 markdown files."""
    items: list[dict] = []
    root = _ecc_root()
    if root:
        items.extend(_list_ecc_skills(root))
        items.extend(_list_ecc_commands(root))
    items.extend(OMC_MODES)
    items.extend(OMX_COMMANDS)
    return items


def _get_catalog() -> list[dict]:
    now = time.time()
    if now - _CATALOG_CACHE["ts"] < _CATALOG_TTL_S and _CATALOG_CACHE["items"]:
        return _CATALOG_CACHE["items"]
    items = _build_catalog()
    _CATALOG_CACHE["ts"] = now
    _CATALOG_CACHE["items"] = items
    return items


# ── Favorites ───────────────────────────────────────────────────────────────

def _load_favorites() -> set[str]:
    if not RUN_CENTER_FAV_PATH.exists():
        return set()
    try:
        data = json.loads(_safe_read(RUN_CENTER_FAV_PATH) or "{}")
        ids = data.get("ids") or []
        return {x for x in ids if isinstance(x, str)}
    except Exception:
        return set()


def _save_favorites(ids: set[str]) -> bool:
    try:
        from .utils import _safe_write
        return _safe_write(RUN_CENTER_FAV_PATH, json.dumps({"ids": sorted(ids)}, ensure_ascii=False, indent=2))
    except Exception as e:
        log.error("favorites save failed: %s", e)
        return False


# ── Public APIs ─────────────────────────────────────────────────────────────

def api_run_catalog(query: dict | None = None) -> dict:
    """GET /api/run/catalog?source=ecc|omc|omx&kind=skill|command|mode|diagnostic|knowledge&q=..."""
    q = query or {}
    src    = (q.get("source", [""])[0] if isinstance(q.get("source"), list) else q.get("source", "")).strip()
    kind   = (q.get("kind",   [""])[0] if isinstance(q.get("kind"),   list) else q.get("kind",   "")).strip()
    needle = (q.get("q",      [""])[0] if isinstance(q.get("q"),      list) else q.get("q",      "")).strip().lower()

    items = _get_catalog()
    if src:
        items = [it for it in items if it.get("source") == src]
    if kind:
        items = [it for it in items if it.get("kind") == kind]
    if needle:
        def _match(it):
            return (
                needle in (it.get("name", "")     or "").lower()
                or needle in (it.get("description", "") or "").lower()
                or needle in (it.get("category", "") or "").lower()
            )
        items = [it for it in items if _match(it)]

    favs = _load_favorites()
    counts: dict[str, int] = {}
    for it in items:
        counts[it["source"]] = counts.get(it["source"], 0) + 1
    out_items = []
    for it in items:
        out = dict(it)
        out["favorite"] = it["id"] in favs
        # Strip the verbose `path` from the wire payload — the UI doesn't need it.
        out.pop("path", None)
        out_items.append(out)

    return {
        "ok": True,
        "items": out_items,
        "counts": counts,
        "total": len(out_items),
        "ecc_installed": _ecc_root() is not None,
    }


def api_run_favorite_toggle(body: dict) -> dict:
    """POST /api/run/favorite/toggle  body: {id}"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    item_id = (body.get("id") or "").strip()
    if not item_id:
        return {"ok": False, "error": "id required"}
    favs = _load_favorites()
    if item_id in favs:
        favs.discard(item_id)
        toggled = False
    else:
        favs.add(item_id)
        toggled = True
    if not _save_favorites(favs):
        return {"ok": False, "error": "save failed"}
    return {"ok": True, "favorite": toggled, "count": len(favs)}


def api_run_history(query: dict | None = None) -> dict:
    """GET /api/run/history?limit=50&item=ecc:cmd:foo"""
    q = query or {}
    limit_raw = q.get("limit")
    limit = int((limit_raw[0] if isinstance(limit_raw, list) else limit_raw) or 50)
    limit = max(1, min(limit, 200))
    item_raw = q.get("item")
    item_id = (item_raw[0] if isinstance(item_raw, list) else (item_raw or "")) or ""

    rows: list[dict] = []
    try:
        with _db() as c:
            sql = "SELECT * FROM run_history"
            args: list = []
            if item_id:
                sql += " WHERE source = ? AND item_id = ?"
                src, _, rid = item_id.partition(":")
                rid = rid.replace("skill:", "").replace("cmd:", "")
                args.extend([src, rid])
            sql += " ORDER BY ts DESC LIMIT ?"
            args.append(limit)
            for r in c.execute(sql, args).fetchall():
                rows.append({
                    "id":         r["id"],
                    "source":     r["source"],
                    "itemId":     r["item_id"],
                    "itemName":   r["item_name"],
                    "goal":       (r["goal"] or "")[:200],
                    "assignee":   r["assignee"],
                    "status":     r["status"],
                    "tokensIn":   r["tokens_in"] or 0,
                    "tokensOut":  r["tokens_out"] or 0,
                    "costUsd":    r["cost_usd"] or 0.0,
                    "durationMs": r["duration_ms"] or 0,
                    "ts":         r["ts"],
                })
    except sqlite3.OperationalError as e:
        log.warning("run_history query failed: %s", e)
    return {"ok": True, "rows": rows, "count": len(rows)}


def api_run_history_get(query: dict | None = None) -> dict:
    """GET /api/run/history/get?id=<run_id> — one row including output/error bodies."""
    q = query or {}
    rid = q.get("id")
    rid = rid[0] if isinstance(rid, list) else rid
    if not rid:
        return {"ok": False, "error": "id required"}
    try:
        with _db() as c:
            r = c.execute("SELECT * FROM run_history WHERE id = ?", (rid,)).fetchone()
            if not r:
                return {"ok": False, "error": "not found"}
            return {"ok": True, "run": {k: r[k] for k in r.keys()}}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _build_prompt(item: dict, goal: str) -> tuple[str, str]:
    """Compose (system_prompt, user_prompt) from an item + the user's goal."""
    invocation = (item.get("invocation") or "").strip()
    name = item.get("name", "")
    desc = item.get("description", "")
    src = item.get("source", "")

    system_parts = [f"You are LazyClaude Run Center invoking the `{name}` {item.get('kind', 'task')} ({src.upper()})."]
    if desc:
        system_parts.append(f"Item description: {desc}")
    if invocation:
        system_parts.append(invocation)
    system_parts.append(
        "Reply concisely. If the task expects code or a file, output it inside a single fenced block."
    )
    system_prompt = "\n\n".join(system_parts)
    user_prompt = goal.strip() or "(no goal supplied)"
    return system_prompt, user_prompt


def _record_history(rec: dict) -> None:
    try:
        with _db() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO run_history
                (id, source, item_id, item_name, goal, assignee, status, output, error,
                 tokens_in, tokens_out, cost_usd, duration_ms, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec["id"], rec["source"], rec["item_id"], rec["item_name"],
                    rec["goal"], rec["assignee"], rec["status"],
                    (rec.get("output") or "")[:200_000],
                    (rec.get("error")  or "")[:8_000],
                    int(rec.get("tokens_in")  or 0),
                    int(rec.get("tokens_out") or 0),
                    float(rec.get("cost_usd")  or 0.0),
                    int(rec.get("duration_ms") or 0),
                    int(rec.get("ts") or time.time() * 1000),
                ),
            )
    except Exception as e:
        log.warning("run history insert failed: %s", e)


def api_run_execute(body: dict) -> dict:
    """POST /api/run/execute  body: {itemId, goal, assignee?, cwd?, timeoutSeconds?}

    One-shot execution. For long-running multi-stage flows use the Workflow Quick
    Actions in the Workflows tab — this endpoint is intentionally synchronous and
    bounded.
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    item_id = (body.get("itemId") or "").strip()
    goal    = (body.get("goal") or "").strip()
    if not item_id:
        return {"ok": False, "error": "itemId required"}
    if not goal:
        return {"ok": False, "error": "goal required"}

    items = _get_catalog()
    item = next((it for it in items if it["id"] == item_id), None)
    if not item:
        return {"ok": False, "error": f"item not found: {item_id}"}

    assignee = (body.get("assignee") or "claude:sonnet").strip()
    cwd      = (body.get("cwd") or "").strip()
    timeout  = max(15, min(int(body.get("timeoutSeconds") or 180), 1800))

    system_prompt, user_prompt = _build_prompt(item, goal)
    run_id = f"run-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
    t0 = time.time()

    try:
        from .ai_providers import execute_with_assignee
        resp = execute_with_assignee(
            assignee, user_prompt,
            system_prompt=system_prompt,
            cwd=cwd or "",
            timeout=timeout,
            extra=None,
            fallback=True,
        )
    except Exception as e:
        log.exception("run execute failed")
        rec = {
            "id": run_id, "source": item["source"],
            "item_id": item["id"], "item_name": item["name"],
            "goal": goal, "assignee": assignee,
            "status": "err", "output": "", "error": f"executor crashed: {e}",
            "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
            "duration_ms": int((time.time() - t0) * 1000),
            "ts": int(time.time() * 1000),
        }
        _record_history(rec)
        return {"ok": False, "error": rec["error"], "runId": run_id}

    duration_ms = resp.duration_ms or int((time.time() - t0) * 1000)
    rec = {
        "id": run_id, "source": item["source"],
        "item_id": item["id"], "item_name": item["name"],
        "goal": goal, "assignee": assignee,
        "status": resp.status,
        "output": resp.output, "error": resp.error or "",
        "tokens_in": resp.tokens_in, "tokens_out": resp.tokens_out,
        "cost_usd": resp.cost_usd or 0.0,
        "duration_ms": duration_ms,
        "ts": int(time.time() * 1000),
    }
    _record_history(rec)

    return {
        "ok":          resp.status == "ok",
        "runId":       run_id,
        "status":      resp.status,
        "output":      resp.output,
        "error":       resp.error or "",
        "provider":    resp.provider,
        "model":       resp.model,
        "tokensIn":    resp.tokens_in,
        "tokensOut":   resp.tokens_out,
        "costUsd":     resp.cost_usd or 0.0,
        "durationMs":  duration_ms,
        "item": {
            "id":       item["id"],
            "name":     item["name"],
            "source":   item["source"],
            "category": item.get("category", ""),
        },
    }


def api_run_to_workflow(body: dict) -> dict:
    """POST /api/run/to-workflow  body: {itemId} — for OMC modes that have a
    matching built-in template, return the template id so the UI can hand off
    to the Workflows tab. For ECC items, scaffold a minimal one-node workflow.
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    item_id = (body.get("itemId") or "").strip()
    items = _get_catalog()
    item = next((it for it in items if it["id"] == item_id), None)
    if not item:
        return {"ok": False, "error": f"item not found: {item_id}"}

    tpl_id = item.get("workflow_template_id")
    if tpl_id:
        return {"ok": True, "kind": "template", "templateId": tpl_id, "item": item["name"]}

    # No template → emit a draft workflow (caller saves via /api/workflows/save).
    nid_start = "n-rcstart"
    nid_session = "n-rcrun"
    nid_out = "n-rcout"
    invocation = (item.get("invocation") or item.get("description") or "").strip()
    draft = {
        "name":        f"Run · {item.get('name', item_id)}",
        "description": f"Generated from Run Center · {item.get('source', '').upper()} · {item.get('description', '')[:140]}",
        "nodes": [
            {"id": nid_start,   "type": "start",   "x": 80,  "y": 200, "title": "Start", "data": {}},
            {"id": nid_session, "type": "session", "x": 320, "y": 200, "title": item.get("name", "Run"),
             "data": {
                 "subject":     item.get("name", "Run Center item"),
                 "description": invocation or item.get("description", ""),
                 "assignee":    "claude:sonnet",
                 "inputsMode":  "concat",
             }},
            {"id": nid_out,     "type": "output",  "x": 560, "y": 200, "title": "Output", "data": {"exportTo": ""}},
        ],
        "edges": [
            {"id": "e1", "from": nid_start,   "to": nid_session, "fromPort": "out", "toPort": "in"},
            {"id": "e2", "from": nid_session, "to": nid_out,     "fromPort": "out", "toPort": "in"},
        ],
        "viewport": {"panX": 0.0, "panY": 0.0, "zoom": 1.0},
        "repeat":   {"enabled": False, "maxIterations": 1, "intervalSeconds": 0,
                     "scheduleEnabled": False, "scheduleStart": "", "scheduleEnd": "",
                     "feedbackNote": "", "feedbackNodeId": ""},
        "notify":   {"slack": "", "discord": ""},
        "policy":   {"tokenBudgetTotal": 0, "onBudgetExceeded": "stop", "fallbackProvider": ""},
    }
    return {"ok": True, "kind": "draft", "draft": draft, "item": item["name"]}
