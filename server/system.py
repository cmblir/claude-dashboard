"""시스템 상태 · 사용량 · 메트릭 · 태스크 · 출력 스타일 · 호스트 정보.

대시보드의 여러 정보성 엔드포인트를 모은 모듈 — 대부분 파일 시스템·DB
조회만 하는 read-only API.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from .claude_md import get_settings
from .config import (
    CLAUDE_HOME, PROJECTS_DIR,
    SCHEDULED_TASKS_DIR, SESSIONS_DIR, TASKS_DIR,
)
from .db import _db, _db_init
from .device import _detect_device_info
from .projects import _resolve_cwd_from_jsonl, _slug_to_cwd_map
from .utils import _parse_frontmatter, _safe_read, _safe_write, _strip_frontmatter


COST_LOG = CLAUDE_HOME / "cost-tracker.log"
BASH_LOG = CLAUDE_HOME / "bash-commands.log"


def _running_sessions() -> list:
    if not SESSIONS_DIR.exists():
        return []
    out = []
    for p in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            data = json.loads(_safe_read(p))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        cwd = data.get("cwd") or ""
        pid = data.get("pid")
        alive = False
        if pid:
            try:
                os.kill(pid, 0)
                alive = True
            except OSError:
                alive = False
        out.append({
            "pid": pid,
            "sessionId": data.get("sessionId"),
            "workspace": cwd,
            "project": Path(cwd).name if cwd else (data.get("kind") or "Claude Code"),
            "kind": data.get("kind", ""),
            "entrypoint": data.get("entrypoint", ""),
            "startedAt": data.get("startedAt"),
            "name": data.get("name") or "",
            "version": data.get("version") or "",
            "alive": alive,
        })
    return out

def get_system_status() -> dict:
    s = get_settings()
    permissions = s.get("permissions") or {"allow": [], "deny": []}
    if not isinstance(permissions, dict):
        permissions = {"allow": [], "deny": []}
    permissions.setdefault("allow", [])
    permissions.setdefault("deny", [])

    hooks_out = []
    h = s.get("hooks", {})
    if isinstance(h, dict):
        for event, items in h.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        hooks_out.append({"event": event, **item})
                    else:
                        hooks_out.append({"event": event, "value": str(item)})

    return {
        "hooks": hooks_out,
        "permissions": permissions,
        "sessions": _running_sessions(),
        "settings": s,
        "device": _detect_device_info(),
    }

def get_recommended_settings() -> dict:
    return {
        "profiles": [
            {"name": "균형형 (Balanced)", "description": "기본적인 안전과 자동화를 균형있게",
             "settings": {"permissions": {"allow": ["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
                                           "deny": ["Bash(rm -rf:*)", "Bash(sudo:*)", "Edit(.env*)"]}}},
            {"name": "개발자형 (Developer)", "description": "자주 쓰는 도구 자동 승인 — 빠른 반복 작업",
             "settings": {"permissions": {"allow": ["Read", "Edit", "Write", "Bash", "Glob", "Grep", "WebFetch", "WebSearch"],
                                           "deny": ["Bash(rm -rf /:*)", "Bash(sudo:*)", "Edit(.env*)", "Edit(secrets/**)"]}}},
            {"name": "안전 우선 (Cautious)", "description": "모든 변경 작업에 수동 승인",
             "settings": {"permissions": {"allow": ["Read", "Glob", "Grep"], "deny": []}}},
            {"name": "탐색 모드 (Read-only)", "description": "읽기 전용",
             "settings": {"permissions": {"allow": ["Read", "Glob", "Grep"], "deny": ["Edit", "Write", "Bash", "WebFetch"]}}},
        ],
    }

def get_device_info() -> dict:
    return _detect_device_info()

def api_usage_summary() -> dict:
    """cost-tracker.log 의 도구 사용 + sessions DB 의 토큰 사용량 종합."""
    from collections import defaultdict

    # --- 1) cost-tracker.log (있으면) ---
    log_data = {"exists": False}
    if COST_LOG.exists():
        try:
            text = COST_LOG.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            tool_count: dict = defaultdict(int)
            daily: dict = defaultdict(int)
            parsed = 0
            for line in lines:
                m = re.match(r"^\[(\d{4}-\d{2}-\d{2})T[^\]]+\]\s+tool=(\S+)", line)
                if not m:
                    continue
                parsed += 1
                tool_count[m.group(2)] += 1
                daily[m.group(1)] += 1
            sorted_days = sorted(daily.keys())[-30:]
            log_data = {
                "exists": True,
                "totalLines": len(lines),
                "parsedEvents": parsed,
                "firstLine": lines[0][:120] if lines else "",
                "lastLine": lines[-1][:120] if lines else "",
                "timeline": [{"date": d, "count": daily[d]} for d in sorted_days],
                "topTools": [{"tool": t, "n": n} for t, n in sorted(tool_count.items(), key=lambda x: -x[1])[:20]],
                "fileSize": COST_LOG.stat().st_size,
            }
        except Exception as e:
            log_data = {"exists": True, "error": str(e)}

    # --- 2) sessions DB 의 토큰 집계 ---
    _db_init()
    thirty = int((time.time() - 30 * 86400) * 1000)
    with _db() as c:
        totals_all = c.execute(
            "SELECT COALESCE(SUM(total_tokens),0) AS tot, COALESCE(SUM(input_tokens),0) AS ti, "
            "       COALESCE(SUM(output_tokens),0) AS to_, COALESCE(SUM(cache_read_tokens),0) AS cr, "
            "       COALESCE(SUM(cache_creation_tokens),0) AS cc, COUNT(*) AS n "
            "FROM sessions"
        ).fetchone()
        totals_30d = c.execute(
            "SELECT COALESCE(SUM(total_tokens),0) AS tot, COALESCE(SUM(input_tokens),0) AS ti, "
            "       COALESCE(SUM(output_tokens),0) AS to_, COALESCE(SUM(cache_read_tokens),0) AS cr, "
            "       COALESCE(SUM(cache_creation_tokens),0) AS cc, COUNT(*) AS n "
            "FROM sessions WHERE started_at >= ?", (thirty,)
        ).fetchone()
        daily_tok = c.execute(
            "SELECT started_at, total_tokens FROM sessions WHERE started_at >= ? AND total_tokens > 0",
            (thirty,)
        ).fetchall()
        # v2.43.2 — return ALL projects (no LIMIT 20). Frontend caps the
        # visible rows but keeps the rest scrollable + clickable for drill-in.
        proj_tok = [dict(r) for r in c.execute(
            "SELECT COALESCE(NULLIF(cwd,''), project_dir) AS key, MAX(cwd) AS cwd, "
            "       COUNT(*) AS sessions, SUM(total_tokens) AS tokens "
            "FROM sessions WHERE total_tokens > 0 "
            "GROUP BY COALESCE(NULLIF(cwd,''), project_dir) "
            "ORDER BY tokens DESC"
        ).fetchall()]
        # 도구별 토큰 (turn_tokens)
        tool_tok = [dict(r) for r in c.execute(
            "SELECT tool, COUNT(*) AS calls, SUM(turn_tokens) AS tokens "
            "FROM tool_uses GROUP BY tool ORDER BY tokens DESC LIMIT 20"
        ).fetchall()]
        # 에이전트별 토큰
        agent_tok = [dict(r) for r in c.execute(
            "SELECT subagent_type AS name, COUNT(*) AS calls, SUM(turn_tokens) AS tokens "
            "FROM tool_uses WHERE subagent_type != '' GROUP BY subagent_type ORDER BY tokens DESC LIMIT 20"
        ).fetchall()]
        top_sessions = [dict(r) for r in c.execute(
            "SELECT session_id, project, first_user_prompt, total_tokens, started_at "
            "FROM sessions WHERE total_tokens > 0 ORDER BY total_tokens DESC LIMIT 10"
        ).fetchall()]

    # 일자별 토큰 bucket
    token_daily: dict = defaultdict(int)
    for r in daily_tok:
        if not r["started_at"]:
            continue
        d = datetime.fromtimestamp(r["started_at"] / 1000).strftime("%Y-%m-%d")
        token_daily[d] += r["total_tokens"] or 0
    token_timeline = [{"date": d, "tokens": token_daily[d]} for d in sorted(token_daily.keys())[-30:]]

    # project 이름 정리
    for p in proj_tok:
        cwd = p.get("cwd") or ""
        p["name"] = Path(cwd).name if cwd else (p.get("key") or "")

    return {
        **log_data,  # cost-tracker.log 관련 필드 포함 (exists, totalLines, parsedEvents, timeline, topTools, fileSize)
        "tokens": {
            "all": {"total": totals_all["tot"], "input": totals_all["ti"], "output": totals_all["to_"],
                     "cacheRead": totals_all["cr"], "cacheCreate": totals_all["cc"], "sessions": totals_all["n"]},
            "last30d": {"total": totals_30d["tot"], "input": totals_30d["ti"], "output": totals_30d["to_"],
                         "cacheRead": totals_30d["cr"], "cacheCreate": totals_30d["cc"], "sessions": totals_30d["n"]},
            "dailyTimeline": token_timeline,
            "byProject": proj_tok,
            "byTool": tool_tok,
            "byAgent": agent_tok,
            "topSessions": top_sessions,
        },
    }


def api_usage_project(query: dict) -> dict:
    """v2.43.2 — drill-down for one project.

    GET ``/api/usage/project?cwd=<absolute path>`` returns:

        {
          "ok": True, "cwd": "...",
          "totals": {total, input, output, cacheRead, cacheCreate, sessions},
          "sessions": [{session_id, started_at, model, total_tokens, ...}, ...],
          "byTool":   [{tool, calls, tokens}, ...],
          "byAgent":  [{name, calls, tokens}, ...],
          "dailyTimeline": [{date, count}, ...],
        }

    The ``cwd`` field selects on either ``sessions.cwd`` (preferred) or
    ``sessions.project_dir`` (when cwd was never resolved). Validates that
    the resolved path is under ``$HOME`` so we don't leak sessions that
    happen to share a project_dir slug from outside home.
    """
    from collections import defaultdict
    from datetime import datetime
    from pathlib import Path
    import os

    cwd_raw = ""
    if isinstance(query, dict):
        v = query.get("cwd")
        if isinstance(v, list):
            v = v[0] if v else ""
        cwd_raw = v if isinstance(v, str) else ""
    cwd_raw = (cwd_raw or "").strip()
    if not cwd_raw:
        return {"ok": False, "error": "cwd required"}

    # Resolve + sandbox under $HOME (same guard the rest of the app uses).
    try:
        abs_cwd = str(Path(os.path.expanduser(cwd_raw)).resolve())
    except Exception:
        return {"ok": False, "error": "invalid cwd"}
    home = str(Path.home())
    if not (abs_cwd == home or abs_cwd.startswith(home + os.sep)):
        return {"ok": False, "error": "cwd outside home"}

    _db_init()
    with _db() as c:
        # Match either resolved cwd or project_dir slug fallback.
        totals = c.execute(
            "SELECT COALESCE(SUM(total_tokens),0) AS tot, "
            "       COALESCE(SUM(input_tokens),0) AS ti, "
            "       COALESCE(SUM(output_tokens),0) AS to_, "
            "       COALESCE(SUM(cache_read_tokens),0) AS cr, "
            "       COALESCE(SUM(cache_creation_tokens),0) AS cc, "
            "       COUNT(*) AS n "
            "FROM sessions WHERE cwd = ? OR (cwd = '' AND project_dir = ?)",
            (abs_cwd, cwd_raw),
        ).fetchone()
        rows = [dict(r) for r in c.execute(
            "SELECT session_id, started_at, ended_at, duration_ms, model, "
            "       first_user_prompt, total_tokens, input_tokens, output_tokens, "
            "       cache_read_tokens, cache_creation_tokens, message_count, "
            "       tool_use_count "
            "FROM sessions WHERE cwd = ? OR (cwd = '' AND project_dir = ?) "
            "ORDER BY total_tokens DESC",
            (abs_cwd, cwd_raw),
        ).fetchall()]
        sids = [r["session_id"] for r in rows]
        by_tool: list = []
        by_agent: list = []
        if sids:
            placeholders = ",".join("?" * len(sids))
            by_tool = [dict(r) for r in c.execute(
                f"SELECT tool, COUNT(*) AS calls, SUM(turn_tokens) AS tokens "
                f"FROM tool_uses WHERE session_id IN ({placeholders}) "
                f"GROUP BY tool ORDER BY tokens DESC LIMIT 30",
                sids,
            ).fetchall()]
            by_agent = [dict(r) for r in c.execute(
                f"SELECT subagent_type AS name, COUNT(*) AS calls, "
                f"       SUM(turn_tokens) AS tokens "
                f"FROM tool_uses WHERE session_id IN ({placeholders}) "
                f"      AND subagent_type != '' "
                f"GROUP BY subagent_type ORDER BY tokens DESC LIMIT 30",
                sids,
            ).fetchall()]

    # Daily timeline (last 90 days) bucketed from session start times.
    daily: dict = defaultdict(int)
    cutoff = (time.time() - 90 * 86400) * 1000
    for r in rows:
        s = r.get("started_at") or 0
        if not s or s < cutoff:
            continue
        try:
            d = datetime.fromtimestamp(s / 1000).strftime("%Y-%m-%d")
        except Exception:
            continue
        daily[d] += int(r.get("total_tokens") or 0)
    timeline = [{"date": d, "tokens": daily[d]} for d in sorted(daily)]

    return {
        "ok": True,
        "cwd": abs_cwd,
        "totals": {
            "total": totals["tot"], "input": totals["ti"], "output": totals["to_"],
            "cacheRead": totals["cr"], "cacheCreate": totals["cc"],
            "sessions": totals["n"],
        },
        "sessions": rows,
        "byTool": by_tool,
        "byAgent": by_agent,
        "dailyTimeline": timeline,
    }


def api_memory_list(query: dict) -> dict:
    """~/.claude/projects/*/memory/*.md 전부 나열."""
    out = []
    if PROJECTS_DIR.exists():
        for proj in sorted(PROJECTS_DIR.iterdir()):
            if not proj.is_dir():
                continue
            mem_dir = proj / "memory"
            if not mem_dir.exists():
                continue
            slug_map = _slug_to_cwd_map()
            cwd = slug_map.get(proj.name) or _resolve_cwd_from_jsonl(proj)
            items = []
            for md in sorted(mem_dir.glob("*.md")):
                raw = _safe_read(md, 4000)
                meta = _parse_frontmatter(raw)
                items.append({
                    "file": md.name,
                    "path": str(md),
                    "name": meta.get("name", md.stem),
                    "type": meta.get("type", ""),
                    "description": meta.get("description", ""),
                    "content": _strip_frontmatter(raw)[:2000],
                })
            if items or (mem_dir / "MEMORY.md").exists():
                out.append({
                    "slug": proj.name,
                    "cwd": cwd or "",
                    "projectName": Path(cwd).name if cwd else proj.name,
                    "memoryDir": str(mem_dir),
                    "count": len(items),
                    "items": items,
                })
    return {"projects": out}

def api_tasks_list() -> dict:
    """~/.claude/tasks/<sessionId>/*.json 태스크 전부 수집."""
    out = []
    if not TASKS_DIR.exists():
        return {"sessions": out}
    for d in sorted(TASKS_DIR.iterdir()):
        if not d.is_dir():
            continue
        tasks = []
        for f in sorted(d.glob("*.json")):
            try:
                data = json.loads(_safe_read(f))
                if isinstance(data, dict):
                    tasks.append({
                        "id": data.get("id", f.stem),
                        "subject": data.get("subject", ""),
                        "status": data.get("status", "pending"),
                        "description": (data.get("description") or "")[:400],
                        "activeForm": data.get("activeForm", ""),
                    })
            except Exception:
                continue
        if not tasks:
            continue
        try:
            updated = int(d.stat().st_mtime * 1000)
        except Exception:
            updated = None
        out.append({
            "id": d.name,
            "taskCount": len(tasks),
            "completed": sum(1 for t in tasks if t["status"] == "completed"),
            "inProgress": sum(1 for t in tasks if t["status"] == "in_progress"),
            "updatedAt": updated,
            "tasks": tasks,
        })
    out.sort(key=lambda x: (x.get("updatedAt") or 0), reverse=True)
    return {"sessions": out}

def api_task_save(body: dict) -> dict:
    """태스크 추가/수정. body: { sessionId, id?, subject, description?, status?, activeForm? }
    sessionId 는 ~/.claude/tasks/<sessionId>/ 폴더. 기본 'dashboard-manual' 사용.
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    sid = (body.get("sessionId") or "dashboard-manual").strip()
    if not re.match(r"^[a-zA-Z0-9_-]+$", sid):
        return {"ok": False, "error": "invalid sessionId"}
    subject = (body.get("subject") or "").strip()
    if not subject:
        return {"ok": False, "error": "subject required"}
    status = body.get("status") or "pending"
    if status not in ("pending", "in_progress", "completed", "deleted"):
        return {"ok": False, "error": "invalid status"}
    task_id = body.get("id") or f"t-{int(time.time()*1000)}"
    if not re.match(r"^[a-zA-Z0-9_.-]+$", task_id):
        return {"ok": False, "error": "invalid task id"}

    d = TASKS_DIR / sid
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{task_id}.json"
    entry = {
        "id": task_id,
        "subject": subject,
        "description": body.get("description") or "",
        "status": status,
        "activeForm": body.get("activeForm") or "",
        "updatedAt": int(time.time() * 1000),
    }
    ok = _safe_write(target, json.dumps(entry, ensure_ascii=False, indent=2))
    return {"ok": ok, "id": task_id, "sessionId": sid}

def api_task_delete(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    sid = (body.get("sessionId") or "").strip()
    tid = (body.get("id") or "").strip()
    if not re.match(r"^[a-zA-Z0-9_-]+$", sid) or not re.match(r"^[a-zA-Z0-9_.-]+$", tid):
        return {"ok": False, "error": "invalid ids"}
    target = TASKS_DIR / sid / f"{tid}.json"
    if not target.exists():
        return {"ok": False, "error": "not found"}
    try:
        target.unlink()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


OUTPUT_STYLES_DIR = CLAUDE_HOME / "output-styles"
PLANS_DIR = CLAUDE_HOME / "plans"
SHELL_SNAPSHOTS_DIR = CLAUDE_HOME / "shell-snapshots"
FILE_HISTORY_DIR = CLAUDE_HOME / "file-history"
BACKUPS_DIR = CLAUDE_HOME / "backups"
METRICS_COSTS_JSONL = CLAUDE_HOME / "metrics" / "costs.jsonl"
KEYBINDINGS_JSON = CLAUDE_HOME / "keybindings.json"

def api_output_styles_list() -> dict:
    out = []
    if OUTPUT_STYLES_DIR.exists():
        for p in sorted(OUTPUT_STYLES_DIR.glob("*.md")):
            raw = _safe_read(p)
            meta = _parse_frontmatter(raw)
            out.append({
                "id": p.stem,
                "name": meta.get("name", p.stem),
                "description": meta.get("description", ""),
                "path": str(p),
                "raw": raw,
                "content": _strip_frontmatter(raw)[:4000],
            })
    return {"styles": out, "dirExists": OUTPUT_STYLES_DIR.exists(), "dir": str(OUTPUT_STYLES_DIR)}

def api_output_style_save(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    name = (body.get("id") or "").strip()
    raw = body.get("raw")
    if not isinstance(raw, str):
        return {"ok": False, "error": "raw required"}
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", name):
        return {"ok": False, "error": "name must be lowercase-kebab"}
    OUTPUT_STYLES_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_STYLES_DIR / f"{name}.md"
    ok = _safe_write(target, raw)
    return {"ok": ok, "path": str(target)}

def api_output_style_delete(body: dict) -> dict:
    name = (body or {}).get("id") if isinstance(body, dict) else None
    if not name or not re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", name):
        return {"ok": False, "error": "invalid id"}
    p = OUTPUT_STYLES_DIR / f"{name}.md"
    if not p.exists():
        return {"ok": False, "error": "not found"}
    try:
        p.unlink()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}

def api_statusline_info() -> dict:
    """settings.json 의 statusLine 관련 설정 + keybindings 파일 표시."""
    s = get_settings()
    status_line = s.get("statusLine") if isinstance(s, dict) else None
    keybindings_exists = KEYBINDINGS_JSON.exists()
    keybindings_raw = _safe_read(KEYBINDINGS_JSON) if keybindings_exists else ""
    return {
        "statusLine": status_line,
        "keybindingsExists": keybindings_exists,
        "keybindingsPath": str(KEYBINDINGS_JSON),
        "keybindingsRaw": keybindings_raw,
    }

def api_plans_list() -> dict:
    out = []
    if PLANS_DIR.exists():
        for p in sorted(PLANS_DIR.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
            raw = _safe_read(p)
            out.append({
                "id": p.stem,
                "path": str(p),
                "name": p.stem,
                "size": len(raw),
                "modifiedAt": int(p.stat().st_mtime * 1000),
                "preview": raw[:600],
                "raw": raw[:20000],
            })
    return {"plans": out, "dirExists": PLANS_DIR.exists()}

def api_metrics_summary() -> dict:
    """토큰 메트릭 — 세션 DB 가 진실 (costs.jsonl 은 Claude Code 훅 버그로 0만 기록됨).
    costs.jsonl 의 추정 비용 데이터가 있으면 보조로 사용.
    """
    from collections import defaultdict
    _db_init()

    # --- DB 기반 토큰 집계 (진실 source) ---
    with _db() as c:
        rows = c.execute(
            "SELECT started_at, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, total_tokens, model "
            "FROM sessions WHERE total_tokens > 0"
        ).fetchall()

    daily: dict = defaultdict(lambda: {"in": 0, "out": 0, "cacheRead": 0, "cacheCreate": 0, "total": 0, "cost": 0.0, "n": 0})
    by_model: dict = defaultdict(lambda: {"in": 0, "out": 0, "cacheRead": 0, "cacheCreate": 0, "total": 0, "cost": 0.0, "n": 0})
    total = {"in": 0, "out": 0, "cacheRead": 0, "cacheCreate": 0, "total": 0, "cost": 0.0, "n": 0}

    # Claude 모델 대략 요금 (USD per 1M tokens) — 2025 기준, 자주 바뀌니 참고값
    PRICING = {
        "claude-opus-4": {"in": 15.0, "out": 75.0, "cacheRead": 1.5, "cacheCreate": 18.75},
        "claude-sonnet-4": {"in": 3.0, "out": 15.0, "cacheRead": 0.3, "cacheCreate": 3.75},
        "claude-haiku-4": {"in": 0.8, "out": 4.0, "cacheRead": 0.08, "cacheCreate": 1.0},
    }
    def _estimate_cost(model: str, ti: int, to: int, cr: int, cc: int) -> float:
        m = (model or "").lower()
        p = None
        for prefix, v in PRICING.items():
            if prefix in m:
                p = v; break
        if not p:
            # 모델 모르면 Sonnet 로 추정
            p = PRICING["claude-sonnet-4"]
        return (ti * p["in"] + to * p["out"] + cr * p["cacheRead"] + cc * p["cacheCreate"]) / 1_000_000

    for r in rows:
        ts = r["started_at"] or 0
        day = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""
        model = r["model"] or "unknown"
        ti = r["input_tokens"] or 0
        to = r["output_tokens"] or 0
        cr = r["cache_read_tokens"] or 0
        cc = r["cache_creation_tokens"] or 0
        tot = r["total_tokens"] or 0
        cost = _estimate_cost(model, ti, to, cr, cc)
        for bucket in (daily[day] if day else None, by_model[model], total):
            if bucket is None:
                continue
            bucket["in"] += ti
            bucket["out"] += to
            bucket["cacheRead"] += cr
            bucket["cacheCreate"] += cc
            bucket["total"] += tot
            bucket["cost"] += cost
            bucket["n"] += 1

    timeline = [{"date": d, **v} for d, v in sorted(daily.items())][-60:]
    models = sorted(
        [{"model": m, **v} for m, v in by_model.items()],
        key=lambda x: x["total"], reverse=True,
    )[:20]

    return {
        "exists": True,
        "source": "sessions_db",
        "total": total,
        "timeline": timeline,
        "models": models,
        "note": "토큰은 세션 DB (~/.claude/projects/*/*.jsonl 에서 파싱) 기반. 비용은 2025 공식 요금표 기반 추정.",
    }

def api_backup_diff(query: dict) -> dict:
    """v2.33.8 — backups / file-history 아래 파일 두 개(또는 백업 vs 현재)의 unified diff.

    GET /api/backups/diff?a=<path>&b=<path>
    두 경로 모두 ~/.claude/ 하위여야 함. 파일 크기 1MB 이하만 허용.
    """
    import difflib
    import os
    a = ((query.get("a", [""])[0] if isinstance(query.get("a"), list) else query.get("a", "")) or "").strip()
    b = ((query.get("b", [""])[0] if isinstance(query.get("b"), list) else query.get("b", "")) or "").strip()
    if not a or not b:
        return {"ok": False, "error": "a and b required"}
    claude_home_real = os.path.realpath(str(CLAUDE_HOME))
    home_real = os.path.realpath(str(Path.home()))

    def _allowed(p: str) -> bool:
        try:
            rp = os.path.realpath(p)
        except Exception:
            return False
        return rp.startswith(claude_home_real + os.sep) or rp.startswith(home_real + os.sep)

    if not _allowed(a) or not _allowed(b):
        return {"ok": False, "error": "path outside allowed root"}
    try:
        sa = Path(a).stat(); sb = Path(b).stat()
    except Exception as e:
        return {"ok": False, "error": f"stat: {e}"}
    max_bytes = 1024 * 1024
    if sa.st_size > max_bytes or sb.st_size > max_bytes:
        return {"ok": False, "error": "file too large (>1MB)"}
    try:
        ta = Path(a).read_text(encoding="utf-8", errors="replace").splitlines(keepends=False)
        tb = Path(b).read_text(encoding="utf-8", errors="replace").splitlines(keepends=False)
    except Exception as e:
        return {"ok": False, "error": f"read: {e}"}
    diff_lines = list(difflib.unified_diff(
        ta, tb,
        fromfile=Path(a).name,
        tofile=Path(b).name,
        lineterm="",
        n=3,
    ))
    added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
    return {
        "ok": True, "diff": "\n".join(diff_lines),
        "added": added, "removed": removed,
        "aSize": sa.st_size, "bSize": sb.st_size,
    }


def api_backups_list() -> dict:
    def _list(root: Path, limit: int = 30):
        if not root.exists():
            return {"exists": False, "items": []}
        items = []
        try:
            entries = sorted(root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]
        except Exception:
            entries = []
        for e in entries:
            try:
                st = e.stat()
                items.append({
                    "name": e.name,
                    "path": str(e),
                    "size": st.st_size if e.is_file() else sum(f.stat().st_size for f in e.rglob('*') if f.is_file()) if e.is_dir() else 0,
                    "isDir": e.is_dir(),
                    "modifiedAt": int(st.st_mtime * 1000),
                })
            except Exception:
                continue
        return {"exists": True, "items": items, "total": len(list(root.iterdir())) if root.exists() else 0}
    return {
        "backups": _list(BACKUPS_DIR),
        "fileHistory": _list(FILE_HISTORY_DIR),
        "shellSnapshots": _list(SHELL_SNAPSHOTS_DIR),
    }


TELEMETRY_DIR = CLAUDE_HOME / "telemetry"
HOMUNCULUS_JSON = CLAUDE_HOME / "homunculus" / "projects.json"
IMAGE_CACHE_DIR = CLAUDE_HOME / "image-cache"


CLAUDE_ENV_VARS = [
    {"key": "ANTHROPIC_API_KEY",           "doc": "API 키 인증용 (OAuth 로그인 대신 사용)"},
    {"key": "ANTHROPIC_AUTH_TOKEN",        "doc": "수동 Authorization Bearer 토큰 지정"},
    {"key": "ANTHROPIC_BASE_URL",          "doc": "API base URL (self-hosted / proxy 시)"},
    {"key": "ANTHROPIC_MODEL",             "doc": "기본 모델 override (예: claude-opus-4-7)"},
    {"key": "ANTHROPIC_SMALL_FAST_MODEL",  "doc": "Haiku 등 작은 보조 모델 지정"},
    {"key": "CLAUDE_CONFIG_DIR",           "doc": "~/.claude 위치 override"},
    {"key": "CLAUDE_CODE_USE_BEDROCK",     "doc": "AWS Bedrock 백엔드 사용 (0/1)"},
    {"key": "AWS_REGION",                  "doc": "Bedrock 용 AWS region"},
    {"key": "CLAUDE_CODE_USE_VERTEX",      "doc": "Google Vertex AI 백엔드 사용 (0/1)"},
    {"key": "CLOUD_ML_REGION",             "doc": "Vertex 용 region"},
    {"key": "ANTHROPIC_VERTEX_PROJECT_ID", "doc": "Vertex GCP project id"},
    {"key": "HTTP_PROXY",                  "doc": "HTTP 프록시"},
    {"key": "HTTPS_PROXY",                 "doc": "HTTPS 프록시 (회사 망 등)"},
    {"key": "NO_PROXY",                    "doc": "프록시 제외 도메인"},
    {"key": "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "doc": "텔레메트리·업데이트 비활성화 (0/1)"},
    {"key": "CLAUDE_CODE_AUTO_UPDATE",     "doc": "자동 업데이트 끄기 (0/1)"},
    {"key": "BASH_DEFAULT_TIMEOUT_MS",     "doc": "Bash 도구 기본 타임아웃 (ms)"},
    {"key": "BASH_MAX_TIMEOUT_MS",         "doc": "Bash 도구 최대 타임아웃 (ms)"},
    {"key": "DISABLE_AUTOUPDATER",         "doc": "업데이트 비활성 (legacy)"},
    {"key": "DISABLE_TELEMETRY",           "doc": "텔레메트리 비활성 (0/1)"},
]

def api_env_config() -> dict:
    """settings.json.env + 현재 프로세스의 실제 환경값 표시."""
    s = get_settings()
    cfg_env = (s.get("env") if isinstance(s, dict) else None) or {}
    rows = []
    for spec in CLAUDE_ENV_VARS:
        k = spec["key"]
        live = os.environ.get(k, "")
        cfg = cfg_env.get(k, "") if isinstance(cfg_env, dict) else ""
        rows.append({
            "key": k, "doc": spec["doc"],
            "processValue": _mask_secret(k, live),
            "settingsValue": _mask_secret(k, str(cfg) if cfg is not None else ""),
            "inProcess": bool(live),
            "inSettings": k in (cfg_env or {}),
        })
    return {"vars": rows, "settingsEnv": {k: _mask_secret(k, str(v)) for k, v in (cfg_env or {}).items()}}

def _mask_secret(key: str, val: str) -> str:
    if not val:
        return ""
    if any(s in key.upper() for s in ("TOKEN", "KEY", "SECRET", "PASSWORD")):
        if len(val) <= 12:
            return val[:2] + "…" + val[-2:] if len(val) > 4 else "•"*len(val)
        return val[:6] + "…" + val[-4:]
    return val

def api_model_config() -> dict:
    """settings.json 의 model 관련 키 요약 + 빌트인 모델 목록."""
    s = get_settings()
    entries = {}
    for key in ("model", "apiKeyHelper", "forceLoginMethod", "cleanupPeriodDays",
                "outputStyle", "statusLine", "includeCoAuthoredBy",
                "autoUpdates", "skipAutoPermissionPrompt", "skipDangerousModePermissionPrompt"):
        if isinstance(s, dict) and key in s:
            entries[key] = s[key]
    known_models = [
        {"id": "claude-opus-4-7", "label": "Opus 4.7 (1M context)", "note": "최강 성능, 느림/비쌈"},
        {"id": "claude-opus-4-6", "label": "Opus 4.6", "note": "Fast mode 기본 모델"},
        {"id": "claude-sonnet-4-6", "label": "Sonnet 4.6", "note": "균형형"},
        {"id": "claude-haiku-4-5", "label": "Haiku 4.5 (20251001)", "note": "가장 빠름/저렴"},
        {"id": "default", "label": "기본 (Claude Code 선택)", "note": "settings.model 비워두기"},
    ]
    return {"settings": entries, "models": known_models}

def api_ide_status() -> dict:
    """활성 세션 JSONL 에서 terminal / IDE 정보 추출 (best-effort)."""
    ides = []
    if SESSIONS_DIR.exists():
        for p in sorted(SESSIONS_DIR.glob("*.json")):
            try:
                d = json.loads(_safe_read(p))
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            sid = d.get("sessionId") or ""
            ides.append({
                "sessionId": sid,
                "pid": d.get("pid"),
                "cwd": d.get("cwd", ""),
                "entrypoint": d.get("entrypoint", ""),
                "version": d.get("version", ""),
            })
    # 텔레메트리에서 terminal 감지
    detected_terminals: dict = {}
    if TELEMETRY_DIR.exists():
        for f in list(TELEMETRY_DIR.glob("*.json"))[:5]:
            try:
                for line in f.read_text(errors="replace").splitlines()[:200]:
                    m = re.search(r'"terminal":"([^"]+)"', line)
                    if m:
                        detected_terminals[m.group(1)] = detected_terminals.get(m.group(1), 0) + 1
            except Exception:
                continue
    return {
        "activeSessions": ides,
        "detectedTerminals": [{"name": k, "count": v} for k, v in sorted(detected_terminals.items(), key=lambda x: -x[1])],
        "note": "Claude Code 는 현재 VS Code / JetBrains IDE 에 bridge 방식으로 연결됩니다. 연결된 IDE 는 세션 metadata 의 entrypoint/terminal 필드로 식별.",
    }

def api_scheduled_tasks() -> dict:
    """~/.claude/scheduled-tasks/ 목록 + Auto-Resume 활성 워커."""
    out = []
    if SCHEDULED_TASKS_DIR.exists():
        for d in sorted(SCHEDULED_TASKS_DIR.iterdir()):
            if not d.is_dir():
                continue
            skill_md = d / "SKILL.md"
            meta = _parse_frontmatter(_safe_read(skill_md)) if skill_md.exists() else {}
            cron_f = d / "cron.txt"
            cron = _safe_read(cron_f).strip() if cron_f.exists() else ""
            out.append({
                "id": d.name,
                "name": meta.get("name", d.name),
                "description": meta.get("description", ""),
                "cron": cron,
                "path": str(d),
                "hasSkill": skill_md.exists(),
            })
    auto_resume_entries = []
    try:
        from .auto_resume import _load_all as _ar_load_all, _public_state
        store = _ar_load_all()
        for sid, entry in store.items():
            if entry.get("enabled"):
                auto_resume_entries.append(_public_state(entry))
    except Exception:
        pass
    return {
        "tasks": out,
        "dirExists": SCHEDULED_TASKS_DIR.exists(),
        "autoResume": auto_resume_entries,
    }

def api_bash_history(query: dict) -> dict:
    """bash-commands.log tail. q= 검색어, limit= 기본 200."""
    if not BASH_LOG.exists():
        return {"exists": False}
    q = (query.get("q", [""])[0] or "").strip().lower()
    limit = min(1000, max(10, int(query.get("limit", ["200"])[0] or 200)))
    try:
        lines = BASH_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return {"exists": True, "error": str(e)}
    entries = []
    for line in lines:
        m = re.match(r"^\[([^\]]+)\]\s+tool=(\S+)\s+command=(.+)$", line)
        if not m:
            continue
        entries.append({
            "ts": m.group(1),
            "tool": m.group(2),
            "command": m.group(3),
        })
    if q:
        entries = [e for e in entries if q in e["command"].lower() or q in e["tool"].lower()]
    return {
        "exists": True,
        "totalLines": len(lines),
        "totalParsed": len(entries),
        "items": entries[-limit:][::-1],  # 최신 역순
        "fileSize": BASH_LOG.stat().st_size,
    }

def api_telemetry_summary() -> dict:
    """telemetry 파일들 요약 (이벤트 타입 카운트)."""
    from collections import Counter
    if not TELEMETRY_DIR.exists():
        return {"exists": False}
    files = sorted(TELEMETRY_DIR.glob("*.json"))
    event_counts: Counter = Counter()
    total_lines = 0
    errors = 0
    file_entries = []
    for f in files[:100]:
        try:
            size = f.stat().st_size
            file_entries.append({"name": f.name, "size": size, "mtime": int(f.stat().st_mtime * 1000)})
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                total_lines += 1
                try:
                    e = json.loads(line)
                    name = (e.get("event_data") or {}).get("event_name") or e.get("event_type", "unknown")
                    event_counts[name] += 1
                except Exception:
                    errors += 1
        except Exception:
            continue
    top = [{"event": k, "n": v} for k, v in event_counts.most_common(30)]
    file_entries.sort(key=lambda x: -x["mtime"])
    return {
        "exists": True,
        "files": file_entries[:20],
        "fileCount": len(files),
        "totalLines": total_lines,
        "parseErrors": errors,
        "topEvents": top,
    }

def api_homunculus_projects() -> dict:
    """~/.claude/homunculus/projects.json — Claude Code 내부 프로젝트 추적."""
    if not HOMUNCULUS_JSON.exists():
        return {"exists": False}
    try:
        data = json.loads(_safe_read(HOMUNCULUS_JSON))
    except Exception as e:
        return {"exists": True, "error": str(e)}
    rows = []
    if isinstance(data, dict):
        for key, val in data.items():
            if not isinstance(val, dict):
                continue
            rows.append({
                "id": val.get("id", key),
                "name": val.get("name", ""),
                "root": val.get("root", ""),
                "remote": val.get("remote", ""),
                "createdAt": val.get("created_at", ""),
                "lastSeen": val.get("last_seen", ""),
            })
    rows.sort(key=lambda x: x.get("lastSeen", ""), reverse=True)
    return {"exists": True, "projects": rows, "count": len(rows)}

