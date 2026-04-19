#!/usr/bin/env python3
"""
Claude Control Center — 확장 백엔드
- dist/ 정적 서빙
- SQLite 세션 인덱스 (~/.claude-dashboard.db)
- ~/.claude 의 모든 리소스를 읽고 편집 가능한 REST API 노출
- 에이전트 상호작용 그래프 / 품질 스코어링 엔드포인트
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Optional, Any
from urllib.parse import urlparse, parse_qs, unquote

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
CLAUDE_HOME = Path.home() / ".claude"
CLAUDE_MD = CLAUDE_HOME / "CLAUDE.md"
SETTINGS_JSON = CLAUDE_HOME / "settings.json"
SKILLS_DIR = CLAUDE_HOME / "skills"
AGENTS_DIR = CLAUDE_HOME / "agents"
COMMANDS_DIR = CLAUDE_HOME / "commands"
PROJECTS_DIR = CLAUDE_HOME / "projects"
PLUGINS_DIR = CLAUDE_HOME / "plugins"
INSTALLED_PLUGINS_JSON = PLUGINS_DIR / "installed_plugins.json"
KNOWN_MARKETPLACES_JSON = PLUGINS_DIR / "known_marketplaces.json"
SESSIONS_DIR = CLAUDE_HOME / "sessions"
SESSION_DATA_DIR = CLAUDE_HOME / "session-data"
TODOS_DIR = CLAUDE_HOME / "todos"
TASKS_DIR = CLAUDE_HOME / "tasks"
SCHEDULED_TASKS_DIR = CLAUDE_HOME / "scheduled-tasks"
HISTORY_JSONL = CLAUDE_HOME / "history.jsonl"
CLAUDE_JSON = Path.home() / ".claude.json"
MEMORY_DIR = CLAUDE_HOME / "projects" / "-Users-yoo-claude-dashboard" / "memory"

DB_PATH = Path.home() / ".claude-dashboard.db"

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


# ───────────────── helpers ─────────────────

def _safe_read(p: Path, limit: Optional[int] = None) -> str:
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return text if limit is None else text[:limit]
    except Exception:
        return ""


def _safe_write(p: Path, text: str) -> bool:
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        # atomic write
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception as e:
        print(f"[server] write failed for {p}: {e}", file=sys.stderr)
        return False


def _parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    block = m.group(1)
    out = {}
    for line in block.splitlines():
        kv = re.match(r"^(\w[\w-]*):\s*(.*)$", line.strip())
        if kv:
            out[kv.group(1)] = kv.group(2).strip().strip('"').strip("'")
    return out


def _parse_tools_field(raw: str) -> list:
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("["):
        try:
            return [str(x) for x in json.loads(raw) if x]
        except Exception:
            pass
    return [t.strip().strip('"').strip("'") for t in raw.split(",") if t.strip()]


def _strip_frontmatter(text: str) -> str:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    return text[m.end():] if m else text


def _iso_ms(ts_str: str) -> Optional[int]:
    if not ts_str:
        return None
    try:
        return int(datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return None


def _fmt_rel(ms: Optional[int]) -> str:
    if not ms:
        return "—"
    now = int(time.time() * 1000)
    d = max(0, (now - ms) // 1000)
    if d < 60:
        return f"{d}초 전"
    if d < 3600:
        return f"{d // 60}분 전"
    if d < 86400:
        return f"{d // 3600}시간 전"
    return f"{d // 86400}일 전"


# ───────────────── device ─────────────────

_DEVICE_INFO_CACHE: Optional[dict] = None


def _detect_device_info() -> dict:
    global _DEVICE_INFO_CACHE
    if _DEVICE_INFO_CACHE is not None:
        return _DEVICE_INFO_CACHE
    hostname = socket.gethostname()
    model_id = model_name = chip = ""
    try:
        username = os.getlogin()
    except Exception:
        username = Path.home().name
    try:
        model_id = subprocess.check_output(["sysctl", "-n", "hw.model"], text=True, timeout=5).strip()
    except Exception:
        pass
    try:
        out = subprocess.check_output(["system_profiler", "SPHardwareDataType"], text=True, timeout=10)
        for line in out.splitlines():
            s = line.strip()
            if s.startswith("Model Name:"):
                model_name = s.split(":", 1)[1].strip()
            elif s.startswith("Chip:"):
                chip = s.split(":", 1)[1].strip()
    except Exception:
        pass
    label = _device_label_from_model(model_name, hostname)
    _DEVICE_INFO_CACHE = {
        "hostname": hostname, "modelId": model_id, "modelName": model_name,
        "chip": chip, "username": username, "label": label,
        "platform": platform.system(), "arch": platform.machine(),
    }
    return _DEVICE_INFO_CACHE


def _device_label_from_model(model_name: str, hostname: str) -> str:
    mn = (model_name or "").lower()
    if "macbook" in mn: return "맥북"
    if "mac mini" in mn: return "맥미니"
    if "imac" in mn: return "아이맥"
    if "mac pro" in mn: return "맥 프로"
    if "mac studio" in mn: return "맥 스튜디오"
    h = (hostname or "").lower()
    if "macbook" in h or "mbp" in h: return "맥북"
    if "macmini" in h or "mac-mini" in h or "mini" in h: return "맥미니"
    return hostname or "Mac"


# ───────────────── SQLite index ─────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _db_init() -> None:
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
          session_id TEXT PRIMARY KEY,
          project TEXT,
          project_dir TEXT,
          cwd TEXT,
          jsonl_path TEXT,
          started_at INTEGER,
          ended_at INTEGER,
          duration_ms INTEGER,
          message_count INTEGER DEFAULT 0,
          user_msg_count INTEGER DEFAULT 0,
          assistant_msg_count INTEGER DEFAULT 0,
          tool_use_count INTEGER DEFAULT 0,
          error_count INTEGER DEFAULT 0,
          agent_call_count INTEGER DEFAULT 0,
          subagent_types TEXT,
          model TEXT,
          first_user_prompt TEXT,
          last_summary TEXT,
          score INTEGER DEFAULT 0,
          score_breakdown TEXT,
          indexed_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS tool_uses (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT,
          ts INTEGER,
          tool TEXT,
          subagent_type TEXT,
          input_summary TEXT,
          had_error INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_tool_session ON tool_uses(session_id);
        CREATE INDEX IF NOT EXISTS idx_tool_name ON tool_uses(tool);
        CREATE TABLE IF NOT EXISTS agent_edges (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT,
          src TEXT,
          dst TEXT,
          ts INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_edge_session ON agent_edges(session_id);
        CREATE TABLE IF NOT EXISTS scores_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT,
          ts INTEGER,
          score INTEGER,
          breakdown TEXT
        );
        """)
        # 기존 DB에 cwd 컬럼이 없으면 추가 (호환성)
        try:
            cols = {r["name"] for r in c.execute("PRAGMA table_info(sessions)").fetchall()}
            if "cwd" not in cols:
                c.execute("ALTER TABLE sessions ADD COLUMN cwd TEXT")
        except Exception:
            pass


def _first_user_prompt(lines: list[dict]) -> str:
    for msg in lines:
        if msg.get("type") != "user":
            continue
        c = msg.get("message", {})
        if isinstance(c, dict):
            content = c.get("content")
            if isinstance(content, str):
                return content.strip()[:500]
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        return (b.get("text") or "").strip()[:500]
    return ""


def _extract_model(lines: list[dict]) -> str:
    for msg in lines:
        if msg.get("type") == "assistant":
            m = (msg.get("message") or {}).get("model")
            if m:
                return str(m)
    return ""


def _compute_score(stats: dict) -> tuple[int, dict]:
    """세션 품질 스코어 계산 (0–100). 투명한 휴리스틱:
    - 완료성: 메시지 수 / 대화 길이
    - 생산성: tool_use 수
    - 오류율 역가중
    - 에이전트 위임 보너스 (멀티에이전트 활용)
    - 다양성 (tool 다양성)
    """
    b = {}
    msgs = stats.get("message_count", 0)
    tools = stats.get("tool_use_count", 0)
    errors = stats.get("error_count", 0)
    agents = stats.get("agent_call_count", 0)
    diversity = stats.get("tool_diversity", 0)
    duration_min = max(1, stats.get("duration_ms", 0) // 60000)

    b["engagement"] = min(25, int(msgs / 4))
    b["productivity"] = min(25, int(tools * 1.2))
    b["delegation"] = min(15, agents * 3)
    b["diversity"] = min(15, diversity * 2)
    b["reliability"] = max(0, 20 - errors * 4)
    total = sum(b.values())
    return min(100, max(0, total)), b


def _index_jsonl(jsonl: Path, project_dir: str) -> Optional[dict]:
    """단일 세션 jsonl 파싱 → DB 업서트."""
    try:
        text = jsonl.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    if not text.strip():
        return None

    session_id = jsonl.stem
    lines: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            lines.append(json.loads(line))
        except Exception:
            continue
    if not lines:
        return None

    timestamps = []
    msg_count = user_cnt = asst_cnt = tool_cnt = err_cnt = agent_cnt = 0
    tool_counter: Counter = Counter()
    subagent_counter: Counter = Counter()
    tool_rows: list[tuple] = []
    edges: list[tuple] = []

    for m in lines:
        ts = _iso_ms(m.get("timestamp", "") or "")
        if ts:
            timestamps.append(ts)
        t = m.get("type")
        if t == "user":
            user_cnt += 1
            msg_count += 1
        elif t == "assistant":
            asst_cnt += 1
            msg_count += 1
            content = (m.get("message") or {}).get("content")
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        tool_cnt += 1
                        tool_name = b.get("name") or "?"
                        tool_counter[tool_name] += 1
                        inp = b.get("input") or {}
                        subagent = inp.get("subagent_type") if isinstance(inp, dict) else None
                        if tool_name == "Agent" and subagent:
                            agent_cnt += 1
                            subagent_counter[subagent] += 1
                            edges.append((session_id, "claude", subagent, ts or 0))
                        input_summary = ""
                        if isinstance(inp, dict):
                            for k in ("description", "command", "prompt", "file_path", "pattern"):
                                v = inp.get(k)
                                if v:
                                    input_summary = str(v)[:200]
                                    break
                        tool_rows.append((session_id, ts or 0, tool_name, subagent or "", input_summary, 0))
        elif t == "tool_result":
            content = (m.get("message") or {}).get("content")
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("is_error"):
                        err_cnt += 1

    started = min(timestamps) if timestamps else 0
    ended = max(timestamps) if timestamps else 0
    duration = max(0, ended - started)
    first_prompt = _first_user_prompt(lines)
    model = _extract_model(lines)
    project_name = project_dir.replace("-Users-yoo-", "").replace("-", "/") if project_dir else ""

    # 세션의 실제 cwd는 JSONL 메시지에 기록되어 있음 (첫 번째 찾은 값)
    cwd = ""
    for m in lines:
        c_val = m.get("cwd")
        if isinstance(c_val, str) and c_val:
            cwd = c_val
            break

    stats = {
        "message_count": msg_count,
        "tool_use_count": tool_cnt,
        "error_count": err_cnt,
        "agent_call_count": agent_cnt,
        "duration_ms": duration,
        "tool_diversity": len(tool_counter),
    }
    score, breakdown = _compute_score(stats)

    with _db() as c:
        c.execute("DELETE FROM tool_uses WHERE session_id=?", (session_id,))
        c.execute("DELETE FROM agent_edges WHERE session_id=?", (session_id,))
        if tool_rows:
            c.executemany("INSERT INTO tool_uses (session_id,ts,tool,subagent_type,input_summary,had_error) VALUES (?,?,?,?,?,?)", tool_rows)
        if edges:
            c.executemany("INSERT INTO agent_edges (session_id,src,dst,ts) VALUES (?,?,?,?)", edges)
        c.execute("""
        INSERT OR REPLACE INTO sessions
        (session_id,project,project_dir,cwd,jsonl_path,started_at,ended_at,duration_ms,
         message_count,user_msg_count,assistant_msg_count,tool_use_count,error_count,
         agent_call_count,subagent_types,model,first_user_prompt,last_summary,
         score,score_breakdown,indexed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            session_id, project_name, project_dir, cwd, str(jsonl),
            started, ended, duration,
            msg_count, user_cnt, asst_cnt, tool_cnt, err_cnt, agent_cnt,
            json.dumps(dict(subagent_counter)), model, first_prompt, "",
            score, json.dumps(breakdown), int(time.time() * 1000),
        ))
        c.execute("INSERT INTO scores_history (session_id,ts,score,breakdown) VALUES (?,?,?,?)",
                  (session_id, int(time.time() * 1000), score, json.dumps(breakdown)))

    return {
        "sessionId": session_id, "project": project_name, "projectDir": project_dir,
        "startedAt": started, "endedAt": ended, "durationMs": duration,
        "messageCount": msg_count, "toolUseCount": tool_cnt, "errorCount": err_cnt,
        "agentCallCount": agent_cnt, "score": score, "model": model,
    }


def index_all_sessions(force: bool = False) -> dict:
    """~/.claude/projects/*/*.jsonl 전부 재인덱스."""
    _db_init()
    indexed = 0
    skipped = 0
    if not PROJECTS_DIR.exists():
        return {"indexed": 0, "skipped": 0, "total": 0}

    with _db() as c:
        existing = {r["jsonl_path"]: r["indexed_at"] for r in c.execute("SELECT jsonl_path, indexed_at FROM sessions")}

    for project_dir_path in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir_path.is_dir():
            continue
        project_dir = project_dir_path.name
        for jsonl in sorted(project_dir_path.glob("*.jsonl")):
            try:
                mtime_ms = int(jsonl.stat().st_mtime * 1000)
            except Exception:
                mtime_ms = 0
            if not force:
                prev = existing.get(str(jsonl))
                if prev and prev >= mtime_ms:
                    skipped += 1
                    continue
            if _index_jsonl(jsonl, project_dir):
                indexed += 1
            else:
                skipped += 1
    return {"indexed": indexed, "skipped": skipped, "total": indexed + skipped}


# ───────────────── API: CLAUDE.md / settings / system ─────────────────

def parse_sections(raw: str) -> list:
    sections, cur = [], None
    for line in raw.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            if cur:
                sections.append(cur)
            cur = {"title": m.group(2).strip(), "content": []}
        else:
            if cur is None:
                cur = {"title": "intro", "content": []}
            if line.strip():
                cur["content"].append(line)
    if cur:
        sections.append(cur)
    return sections


def get_claude_md() -> dict:
    raw = _safe_read(CLAUDE_MD)
    return {"sections": parse_sections(raw), "raw": raw}


def put_claude_md(body: dict) -> dict:
    raw = body.get("raw", "") if isinstance(body, dict) else ""
    if not isinstance(raw, str):
        return {"ok": False, "error": "raw must be string"}
    ok = _safe_write(CLAUDE_MD, raw)
    return {"ok": ok}


def get_settings() -> dict:
    if not SETTINGS_JSON.exists():
        return {}
    try:
        return json.loads(_safe_read(SETTINGS_JSON))
    except Exception:
        return {}


def put_settings(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}
    text = json.dumps(body, indent=2, ensure_ascii=False)
    ok = _safe_write(SETTINGS_JSON, text)
    return {"ok": ok}


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


# ───────────────── API: skills ─────────────────

def _scan_plugin_skills() -> list:
    """활성·비활성 모든 마켓플레이스 플러그인의 스킬 수집."""
    out = []
    if not PLUGINS_DIR.exists():
        return out
    markets_dir = PLUGINS_DIR / "marketplaces"
    if not markets_dir.exists():
        return out
    seen = set()
    for market in sorted(markets_dir.iterdir()):
        if not market.is_dir() or market.name.endswith(".bak"):
            continue
        # Layout A: <market>/plugins/<plugin>/skills/<id>/SKILL.md
        plugins_root = market / "plugins"
        if plugins_root.exists():
            for plugin_dir in sorted(plugins_root.iterdir()):
                if not plugin_dir.is_dir():
                    continue
                skills_dir = plugin_dir / "skills"
                if not skills_dir.exists():
                    continue
                for sd in sorted(skills_dir.iterdir()):
                    if not sd.is_dir():
                        continue
                    skill_md = sd / "SKILL.md"
                    if not skill_md.exists():
                        continue
                    if str(sd) in seen:
                        continue
                    seen.add(str(sd))
                    raw = _safe_read(skill_md)
                    meta = _parse_frontmatter(raw)
                    sid = f"{market.name}:{plugin_dir.name}:{sd.name}"
                    out.append({
                        "id": sid,
                        "name": meta.get("name", sd.name),
                        "path": str(sd),
                        "description": meta.get("description", ""),
                        "source": f"{market.name}/{plugin_dir.name}",
                        "scope": "plugin",
                        "pluginKey": f"{plugin_dir.name}@{market.name}",
                        "files": [f.name for f in sd.iterdir() if f.is_file()],
                        "content": _strip_frontmatter(raw)[:8000],
                    })
        # Layout B: <market>/skills/<id>/SKILL.md  (ecc 스타일)
        direct = market / "skills"
        if direct.exists():
            for sd in sorted(direct.iterdir()):
                if not sd.is_dir():
                    continue
                skill_md = sd / "SKILL.md"
                if not skill_md.exists():
                    continue
                if str(sd) in seen:
                    continue
                seen.add(str(sd))
                raw = _safe_read(skill_md)
                meta = _parse_frontmatter(raw)
                sid = f"{market.name}:{sd.name}"
                out.append({
                    "id": sid,
                    "name": meta.get("name", sd.name),
                    "path": str(sd),
                    "description": meta.get("description", ""),
                    "source": f"{market.name}",
                    "scope": "plugin",
                    "pluginKey": f"{market.name}@{market.name}",
                    "files": [f.name for f in sd.iterdir() if f.is_file()],
                    "content": _strip_frontmatter(raw)[:8000],
                })
    return out


def list_skills() -> list:
    out = []
    if SKILLS_DIR.exists():
        try:
            entries = sorted(SKILLS_DIR.iterdir())
        except Exception:
            entries = []
        for p in entries:
            try:
                ok = p.is_dir() or p.is_symlink()
            except Exception:
                ok = False
            if not ok:
                continue
            meta = {}
            content = ""
            try:
                skill_md = p / "SKILL.md"
                if skill_md.exists():
                    raw = _safe_read(skill_md)
                    meta = _parse_frontmatter(raw)
                    content = _strip_frontmatter(raw)
            except Exception:
                pass
            try:
                files = [f.name for f in p.iterdir() if f.is_file()]
            except Exception:
                files = []
            out.append({
                "id": p.name,
                "name": meta.get("name", p.name),
                "path": str(p),
                "description": meta.get("description", ""),
                "source": "user",
                "scope": "user",
                "files": files,
                "content": content[:8000],
            })

    # 플러그인 스킬 — 활성 여부 주입
    plugin_skills = _scan_plugin_skills()
    settings = get_settings()
    enabled_map = (settings.get("enabledPlugins") or {}) if isinstance(settings, dict) else {}
    for ps in plugin_skills:
        ps["pluginEnabled"] = bool(enabled_map.get(ps.get("pluginKey", ""), False))
    out.extend(plugin_skills)

    # 번역 주입
    cache = _load_translation_cache()
    for s in out:
        s["descriptionKo"] = cache.get(f"skill:{s['id']}", "")
    return out


def _resolve_skill_path(skill_id: str) -> tuple[Optional[Path], str]:
    """skill_id → (실제 SKILL.md 경로, scope). scope ∈ {'user','plugin',''}."""
    if ":" in skill_id:
        parts = skill_id.split(":")
        if not all(re.match(r"^[a-zA-Z0-9_.-]+$", x or "") for x in parts):
            return None, ""
        markets_dir = PLUGINS_DIR / "marketplaces"
        if len(parts) == 3:
            market, plugin, sd = parts
            p = markets_dir / market / "plugins" / plugin / "skills" / sd / "SKILL.md"
            return (p if p.exists() else None), "plugin"
        if len(parts) == 2:
            market, sd = parts
            p = markets_dir / market / "skills" / sd / "SKILL.md"
            return (p if p.exists() else None), "plugin"
        return None, ""
    if not re.match(r"^[a-zA-Z0-9_-]+$", skill_id or ""):
        return None, ""
    p = SKILLS_DIR / skill_id / "SKILL.md"
    return (p if p.exists() else None), "user"


def get_skill(skill_id: str) -> dict:
    p, scope = _resolve_skill_path(skill_id)
    if not p:
        return {"error": "not found"}
    raw = _safe_read(p)
    meta = _parse_frontmatter(raw)
    return {
        "id": skill_id,
        "name": meta.get("name", skill_id),
        "description": meta.get("description", ""),
        "raw": raw,
        "content": _strip_frontmatter(raw),
        "scope": scope,
        "readOnly": scope == "plugin",
        "path": str(p),
    }


def put_skill(skill_id: str, body: dict) -> dict:
    if ":" in (skill_id or ""):
        return {"ok": False, "error": "플러그인 스킬은 편집 불가 (read-only)"}
    if not re.match(r"^[a-zA-Z0-9_-]+$", skill_id or ""):
        return {"ok": False, "error": "invalid skill id"}
    raw = body.get("raw", "") if isinstance(body, dict) else ""
    if not isinstance(raw, str):
        return {"ok": False, "error": "raw must be string"}
    p = SKILLS_DIR / skill_id / "SKILL.md"
    ok = _safe_write(p, raw)
    return {"ok": ok}


# ───────────────── API: agents ─────────────────

_BUILTIN_AGENTS = [
    {"id": "general-purpose", "name": "general-purpose", "description": "범용 에이전트 — 복잡한 질의 조사 / 코드 검색 / 멀티스텝 작업.", "model": "inherit", "tools": ["*"]},
    {"id": "Explore", "name": "Explore", "description": "코드베이스 탐색 전용 고속 에이전트.", "model": "haiku", "tools": ["Read", "Grep", "Glob", "WebFetch"]},
    {"id": "Plan", "name": "Plan", "description": "구현 전략 수립 — 단계별 플랜과 핵심 파일 식별.", "model": "sonnet", "tools": ["Read", "Grep", "Glob"]},
    {"id": "statusline-setup", "name": "statusline-setup", "description": "Claude Code 상태라인 커스터마이징.", "model": "haiku", "tools": ["Read", "Edit"]},
]


def _scan_plugin_agents() -> list:
    """활성 마켓플레이스의 에이전트 수집.
    두 레이아웃 지원:
      A) <market>/plugins/<plugin>/agents/*.md → id=market:plugin:stem
      B) <market>/agents/*.md (ecc 스타일) → id=market:stem
    """
    out = []
    if not PLUGINS_DIR.exists():
        return out
    markets_dir = PLUGINS_DIR / "marketplaces"
    if not markets_dir.exists():
        return out

    seen_paths = set()

    for market in sorted(markets_dir.iterdir()):
        if not market.is_dir() or market.name.endswith(".bak"):
            continue

        # Layout A
        plugins_root = market / "plugins"
        if plugins_root.exists():
            for plugin_dir in sorted(plugins_root.iterdir()):
                if not plugin_dir.is_dir():
                    continue
                agents_dir = plugin_dir / "agents"
                if not agents_dir.exists():
                    continue
                for agent_md in sorted(agents_dir.glob("*.md")):
                    if str(agent_md) in seen_paths:
                        continue
                    seen_paths.add(str(agent_md))
                    raw = _safe_read(agent_md, 8000)
                    meta = _parse_frontmatter(raw)
                    stem = agent_md.stem
                    out.append({
                        "id": f"{market.name}:{plugin_dir.name}:{stem}",
                        "invokeId": f"{market.name}:{plugin_dir.name}",
                        "name": meta.get("name") or stem,
                        "description": meta.get("description", ""),
                        "model": meta.get("model", "inherit"),
                        "tools": _parse_tools_field(meta.get("tools", "")),
                        "scope": "plugin",
                        "source": f"{market.name}/{plugin_dir.name}",
                        "path": str(agent_md),
                        "content": _strip_frontmatter(raw)[:8000],
                    })

        # Layout B (market 루트의 agents/ 직결)
        direct_agents = market / "agents"
        if direct_agents.exists():
            for agent_md in sorted(direct_agents.glob("*.md")):
                if str(agent_md) in seen_paths:
                    continue
                seen_paths.add(str(agent_md))
                raw = _safe_read(agent_md, 8000)
                meta = _parse_frontmatter(raw)
                stem = agent_md.stem
                out.append({
                    "id": f"{market.name}:{stem}",
                    "invokeId": f"{market.name}:{stem}",
                    "name": meta.get("name") or stem,
                    "description": meta.get("description", ""),
                    "model": meta.get("model", "inherit"),
                    "tools": _parse_tools_field(meta.get("tools", "")),
                    "scope": "plugin",
                    "source": f"{market.name}",
                    "path": str(agent_md),
                    "content": _strip_frontmatter(raw)[:8000],
                })

    return out


def list_agents() -> dict:
    agents = []

    # ~/.claude/agents (전역 사용자 정의)
    if AGENTS_DIR.exists():
        for p in sorted(AGENTS_DIR.glob("*.md")):
            raw = _safe_read(p)
            meta = _parse_frontmatter(raw)
            content = _strip_frontmatter(raw)
            agents.append({
                "id": p.stem,
                "name": meta.get("name", p.stem),
                "description": meta.get("description", ""),
                "model": meta.get("model", "inherit"),
                "tools": _parse_tools_field(meta.get("tools", "")),
                "scope": "global",
                "source": "user",
                "path": str(p),
                "content": content[:8000],
            })

    # 플러그인 에이전트
    agents.extend(_scan_plugin_agents())

    # 빌트인 에이전트 (Claude Code에 내장된 Explore/Plan/general-purpose/statusline-setup)
    for b in _BUILTIN_AGENTS:
        agents.append({**b, "scope": "builtin", "source": "Claude Code", "path": "", "content": ""})

    # 번역 주입
    tr_cache = _load_translation_cache()
    for a in agents:
        a["descriptionKo"] = tr_cache.get(f"agent:{a['id']}", "")

    # 플러그인 활성 여부 주입 — settings.json.enabledPlugins 참조
    settings = get_settings()
    enabled_map = (settings.get("enabledPlugins") or {}) if isinstance(settings, dict) else {}
    # plugin_id 는 `<plugin>@<market>` 형식. 에이전트의 source 에서 market, plugin 추출
    for a in agents:
        if a.get("scope") != "plugin":
            a["pluginEnabled"] = None
            continue
        src = a.get("source", "")  # "claude-plugins-official/agent-sdk-dev" or "ecc"
        if "/" in src:
            market, plugin = src.split("/", 1)
            key = f"{plugin}@{market}"
        else:
            # ecc 스타일: market 전체가 하나의 플러그인으로 취급 (composite_id 는 "<market>@<market>")
            key = f"{src}@{src}"
        a["pluginEnabled"] = bool(enabled_map.get(key, False))
        a["pluginKey"] = key

    # counts by scope
    counts = {"global": 0, "plugin": 0, "builtin": 0}
    for a in agents:
        counts[a["scope"]] = counts.get(a["scope"], 0) + 1
    # 활성화된 플러그인 에이전트 수
    counts["pluginEnabled"] = sum(1 for a in agents if a.get("scope") == "plugin" and a.get("pluginEnabled"))

    return {"agents": agents, "counts": counts}


def _resolve_agent_path(agent_id: str) -> Optional[Path]:
    """에이전트 id → 실제 .md 파일 경로.
    지원 형식:
      1. 전역: `agent-name` → ~/.claude/agents/<name>.md
      2. 3-part 플러그인 (대시보드 내부): `market:plugin:stem` → .../<market>/plugins/<plugin>/agents/<stem>.md
      3. 2-part 플러그인 (Claude Code 호출 형식): `market:plugin` → 동일 market/plugin 디렉토리의 첫 agent .md (또는 동명)
    """
    if ":" in agent_id:
        parts = agent_id.split(":")
        if not all(re.match(r"^[a-zA-Z0-9_.-]+$", x or "") for x in parts):
            return None
        markets_dir = PLUGINS_DIR / "marketplaces"
        if len(parts) == 3:
            market, plugin, stem = parts
            p = markets_dir / market / "plugins" / plugin / "agents" / f"{stem}.md"
            return p if p.exists() else None
        if len(parts) == 2:
            market, second = parts
            candidates = [
                markets_dir / market / "plugins" / second / "agents" / f"{second}.md",
                markets_dir / market / "agents" / f"{second}.md",  # ecc 스타일
            ]
            for p in candidates:
                if p.exists():
                    return p
            # plugins/<second>/agents/ 의 첫 .md
            nested = markets_dir / market / "plugins" / second / "agents"
            if nested.exists():
                for p in sorted(nested.glob("*.md")):
                    return p
            # market 전체 agents 디렉토리에서 stem 매칭
            any_agents = markets_dir / market / "agents"
            if any_agents.exists():
                for p in sorted(any_agents.glob("*.md")):
                    if p.stem == second:
                        return p
            return None
        return None
    if not re.match(r"^[a-zA-Z0-9_-]+$", agent_id):
        return None
    return AGENTS_DIR / f"{agent_id}.md"


def get_agent(agent_id: str) -> dict:
    # 빌트인은 편집 불가 — 메타만 반환
    for b in _BUILTIN_AGENTS:
        if b["id"] == agent_id:
            return {
                **b, "scope": "builtin", "raw": "",
                "content": "빌트인 에이전트는 Claude Code에 내장되어 있어 파일로 편집할 수 없습니다.",
                "readOnly": True,
            }
    p = _resolve_agent_path(agent_id)
    if not p or not p.exists():
        return {"error": "not found"}
    raw = _safe_read(p)
    meta = _parse_frontmatter(raw)
    scope = "plugin" if ":" in agent_id else "global"
    return {
        "id": agent_id,
        "name": meta.get("name", agent_id),
        "description": meta.get("description", ""),
        "model": meta.get("model", "inherit"),
        "tools": _parse_tools_field(meta.get("tools", "")),
        "scope": scope,
        "path": str(p),
        "raw": raw,
        "content": _strip_frontmatter(raw),
    }


def put_agent(agent_id: str, body: dict) -> dict:
    # 빌트인은 쓰기 금지
    for b in _BUILTIN_AGENTS:
        if b["id"] == agent_id:
            return {"ok": False, "error": "builtin agent is read-only"}
    p = _resolve_agent_path(agent_id)
    if not p:
        return {"ok": False, "error": "invalid agent id"}
    raw = body.get("raw", "") if isinstance(body, dict) else ""
    if not isinstance(raw, str):
        return {"ok": False, "error": "raw must be string"}
    ok = _safe_write(p, raw)
    return {"ok": ok}


def api_agent_create(body: dict) -> dict:
    """전역 ~/.claude/agents/<name>.md 생성. body: {name, description?, model?, tools?, content?}"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    name = (body.get("name") or "").strip()
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", name):
        return {"ok": False, "error": "이름은 소문자/숫자/-/_ 만 (첫 글자 영숫자)"}
    target = AGENTS_DIR / f"{name}.md"
    if target.exists() and not body.get("overwrite"):
        return {"ok": False, "error": f"이미 존재 — overwrite=true 로 덮어쓰기"}
    desc = (body.get("description") or "").strip() or "TODO: 이 에이전트의 용도"
    model = (body.get("model") or "inherit").strip()
    tools = body.get("tools") or []
    if isinstance(tools, str):
        tools = _parse_tools_field(tools)
    content = body.get("content") or "너는 ... 역할이다. 다음 원칙을 지킨다:\n\n1. ...\n2. ...\n"
    tools_str = ", ".join(t for t in tools) if tools else "Read, Grep, Glob, Edit, Write, Bash"
    raw = (
        "---\n"
        f"name: {name}\n"
        f"description: {desc}\n"
        f"model: {model}\n"
        f"tools: {tools_str}\n"
        "---\n\n"
        f"{content}\n"
    )
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    ok = _safe_write(target, raw)
    return {"ok": ok, "name": name, "path": str(target)}


def api_agent_delete(body: dict) -> dict:
    """전역 에이전트 삭제. 플러그인/빌트인 삭제 불가."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    agent_id = (body.get("id") or "").strip()
    if not agent_id:
        return {"ok": False, "error": "id required"}
    # 빌트인 차단
    for b in _BUILTIN_AGENTS:
        if b["id"] == agent_id:
            return {"ok": False, "error": "builtin agent 는 삭제할 수 없습니다"}
    # 플러그인 차단 — 마켓플레이스 파일을 지우면 플러그인 무결성 깨짐
    if ":" in agent_id:
        return {"ok": False, "error": "플러그인 에이전트는 마켓플레이스에서 관리 — 삭제는 플러그인 비활성화로"}
    # 전역
    if not re.match(r"^[a-zA-Z0-9_-]+$", agent_id):
        return {"ok": False, "error": "invalid agent id"}
    target = AGENTS_DIR / f"{agent_id}.md"
    if not target.exists():
        return {"ok": False, "error": "not found"}
    try:
        target.unlink()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


# ───────────────── API: commands ─────────────────

DASHBOARD_CONFIG = Path.home() / ".claude-dashboard-config.json"

def _load_dash_config() -> dict:
    if not DASHBOARD_CONFIG.exists():
        return {}
    try:
        return json.loads(_safe_read(DASHBOARD_CONFIG))
    except Exception:
        return {}

def _save_dash_config(cfg: dict) -> bool:
    return _safe_write(DASHBOARD_CONFIG, json.dumps(cfg, indent=2, ensure_ascii=False))


CLAUDE_PLANS = [
    {"id": "free",        "label": "무료 (Free)",          "note": "rate limit 있음"},
    {"id": "pro",         "label": "Claude Pro",          "note": "$20/월"},
    {"id": "max_5x",      "label": "Claude Max (5×)",      "note": "$100/월"},
    {"id": "max_20x",     "label": "Claude Max (20×)",     "note": "$200/월"},
    {"id": "team",        "label": "Claude Team",          "note": "팀 워크스페이스"},
    {"id": "enterprise",  "label": "Claude Enterprise",    "note": "엔터프라이즈"},
    {"id": "api_only",    "label": "API 키 전용",          "note": "종량제"},
]


TRANSLATION_CACHE = Path.home() / ".claude-dashboard-translations.json"

def _load_translation_cache() -> dict:
    if not TRANSLATION_CACHE.exists():
        return {}
    try:
        return json.loads(_safe_read(TRANSLATION_CACHE))
    except Exception:
        return {}

def _save_translation_cache(cache: dict) -> None:
    _safe_write(TRANSLATION_CACHE, json.dumps(cache, ensure_ascii=False, indent=2))


# 명령어 카테고리 휴리스틱 (키워드 → 카테고리 id)
CMD_CATEGORIES = [
    ("build",       "🔧 빌드 / 컴파일",     ["build", "compile", "resolve", "fix-build", "linker"]),
    ("test",        "🧪 테스트 / TDD",      ["test", "tdd", "jest", "pytest", "e2e", "fixtures"]),
    ("review",      "🔍 코드 리뷰",          ["review", "audit", "simplify", "quality"]),
    ("security",    "🔒 보안",              ["security", "bounty", "hipaa", "compliance", "phi", "privacy", "secret"]),
    ("plan",        "🏗️ 계획 / 아키텍처",    ["plan", "architect", "design", "rfc", "blueprint", "adr"]),
    ("agent",       "🤖 에이전트 / 오케스트레이션", ["agent", "orchestr", "devfleet", "harness", "fleet", "team-builder", "loop"]),
    ("commit",      "📝 커밋 / PR / Git",    ["commit", "pr-", "git", "prp", "merge", "branch"]),
    ("skill",       "✨ 스킬 관리",          ["skill", "hookify", "instinct"]),
    ("docs",        "📚 문서 / 검색",        ["docs", "documentation", "search", "research", "exa", "context7"]),
    ("deploy",      "🚀 배포 / DevOps",      ["deploy", "docker", "ci", "cd", "release", "canary"]),
    ("lang-rust",   "🦀 Rust",              ["rust"]),
    ("lang-go",     "🐹 Go",                ["go-", "go_", "golang"]),
    ("lang-kotlin", "🎯 Kotlin / KMP",       ["kotlin", "android", "compose", "ktor"]),
    ("lang-cpp",    "⚙️ C++",              ["cpp", "c++", "cmake"]),
    ("lang-csharp", "🟦 C# / .NET",          ["csharp", "dotnet", "c#"]),
    ("lang-java",   "☕ Java / Spring",      ["java", "spring", "jpa", "gradle"]),
    ("lang-python", "🐍 Python",            ["python", "django", "flask", "pytest"]),
    ("lang-flutter","📱 Flutter / Dart",     ["flutter", "dart"]),
    ("lang-swift",  "🍎 Swift / iOS",        ["swift", "swiftui", "xcode", "ios", "foundation-model"]),
    ("lang-ts",     "🌀 TypeScript / Node",  ["typescript", "node", "bun", "nestjs", "nextjs", "nuxt"]),
    ("lang-php",    "🐘 PHP / Laravel",      ["laravel", "php"]),
    ("lang-perl",   "🐫 Perl",              ["perl"]),
    ("lang-sql",    "🗄️ SQL / DB",          ["database", "postgres", "clickhouse", "supabase", "jpa", "migration"]),
    ("healthcare",  "🏥 헬스케어",           ["healthcare", "emr", "hipaa", "cdss", "ehr", "phi"]),
    ("content",     "✍️ 콘텐츠 / 마케팅",     ["content", "article", "brand-voice", "seo", "crosspost", "social"]),
    ("ops",         "🛡️ 운영 / 모니터링",     ["ops", "watch", "monitor", "canary-watch", "healthcheck", "observability"]),
    ("ai-ml",       "🧠 AI / ML",           ["ml", "pytorch", "llm", "claude-api", "claude_api", "agent-sdk", "rag"]),
    ("web3",        "⛓️ Web3 / EVM",        ["evm", "solidity", "web3", "defi", "x402", "keccak"]),
    ("other",       "🛠️ 기타 / 범용",        []),
]

def _categorize_command(cmd: dict) -> tuple[str, str]:
    """명령어 id + description 기반 카테고리 결정."""
    text = (cmd.get("id","") + " " + cmd.get("name","") + " " + (cmd.get("description") or "")).lower()
    for cat_id, cat_label, kws in CMD_CATEGORIES:
        for kw in kws:
            if kw in text:
                return cat_id, cat_label
    return "other", "🛠️ 기타 / 범용"


def list_commands() -> list:
    out = []
    # user global commands
    if COMMANDS_DIR.exists():
        for p in sorted(COMMANDS_DIR.rglob("*.md")):
            raw = _safe_read(p)
            meta = _parse_frontmatter(raw)
            rel = p.relative_to(COMMANDS_DIR)
            cid = str(rel).replace("/", ":").replace(".md", "")
            out.append({
                "id": cid,
                "name": meta.get("name", cid),
                "description": meta.get("description", "") or meta.get("argument-hint", ""),
                "scope": "user",
                "path": str(p),
                "content": _strip_frontmatter(raw)[:4000],
            })
    # plugin commands (scan plugin marketplaces, but skip .bak)
    if PLUGINS_DIR.exists():
        for plugin_md in PLUGINS_DIR.rglob("commands/*.md"):
            try:
                if ".bak" in str(plugin_md):
                    continue
                raw = _safe_read(plugin_md, 4000)
                meta = _parse_frontmatter(raw)
                cid = plugin_md.stem
                out.append({
                    "id": f"plugin:{cid}",
                    "name": meta.get("name", cid),
                    "description": meta.get("description", ""),
                    "scope": "plugin",
                    "path": str(plugin_md),
                    "content": _strip_frontmatter(raw)[:2000],
                })
            except Exception:
                continue
    # 카테고리 + 번역 주입
    tr_cache = _load_translation_cache()
    for c in out:
        cat_id, cat_label = _categorize_command(c)
        c["category"] = cat_id
        c["categoryLabel"] = cat_label
        c["descriptionKo"] = tr_cache.get(c["id"], "")
    return out


def _cache_key(kind: str, item_id: str) -> str:
    return f"{kind}:{item_id}" if kind != "cmd" else item_id  # cmd 는 기존 호환 (prefix 없음)

def _collect_translate_items(kind: str) -> list:
    """kind 에 따라 [{id, desc}, ...] 수집."""
    items = []
    if kind == "cmd":
        for c in list_commands():
            d = c.get("description") or ""
            if d:
                items.append({"id": c["id"], "desc": d[:320]})
    elif kind == "skill":
        for s in list_skills():
            d = s.get("description") or ""
            if d:
                items.append({"id": s["id"], "desc": d[:320]})
    elif kind == "plugin":
        for p in api_plugins_browse().get("plugins", []):
            d = p.get("description") or ""
            if d:
                items.append({"id": p["id"], "desc": d[:320]})
    elif kind == "agent":
        for a in list_agents().get("agents", []):
            d = a.get("description") or ""
            if d:
                items.append({"id": a["id"], "desc": d[:320]})
    return items


def api_translate_batch(body: dict) -> dict:
    """범용 번역 배치. body: {kind: 'cmd'|'skill'|'plugin', limit: N (기본 50, 최대 60)}
    캐시에 없는 것만 선별 → Claude CLI 1회 호출."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return {"error": "claude CLI 설치 필요"}
    if not api_auth_status().get("connected"):
        return {"error": "Claude 계정 연결 필요"}

    kind = (body or {}).get("kind") if isinstance(body, dict) else "cmd"
    if kind not in ("cmd", "skill", "plugin", "agent"):
        return {"error": "unknown kind"}
    limit = min(60, max(5, int((body or {}).get("limit") or 50)))

    cache = _load_translation_cache()
    all_items = _collect_translate_items(kind)
    pending = [x for x in all_items if not cache.get(_cache_key(kind, x["id"]))]
    if not pending:
        return {"translated": 0, "requested": 0, "remaining": 0, "total": len(all_items), "done": True}

    batch = pending[:limit]
    kind_label = {"cmd": "슬래시 명령어", "skill": "스킬", "plugin": "플러그인", "agent": "에이전트"}[kind]

    prompt = f"""다음 Claude Code {kind_label}의 영문 description 들을 **간결한 한국어 한 줄**로 번역하세요.
- 기술용어(Claude Code, PR, CLI 등)는 그대로 유지.
- 20~70자 정도, 핵심 동사 포함 ("~한다" 체).
- 한국어 요약이 불가능하면 원문 기술 용어 나열.

입력:
{json.dumps(batch, ensure_ascii=False, indent=2)}

JSON 만 출력 (다른 텍스트 금지):
{{"translations": {{"<id>": "<한국어>", ...}}}}
"""
    try:
        proc = subprocess.run(
            [claude_bin, "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=300,
        )
    except Exception as e:
        return {"error": f"Claude CLI 실행 실패: {e}"}
    if proc.returncode != 0:
        return {"error": f"Claude CLI 오류: {(proc.stderr or '')[:400]}"}

    stdout = (proc.stdout or "").strip()
    response_text = stdout
    try:
        meta = json.loads(stdout)
        if isinstance(meta, dict):
            response_text = meta.get("result") or stdout
    except Exception:
        pass
    m = re.search(r'\{[\s\S]*"translations"[\s\S]*\}', response_text)
    if not m:
        return {"error": "번역 JSON 없음", "raw": response_text[:1500]}
    try:
        parsed = json.loads(m.group(0))
        tr = parsed.get("translations", {})
    except Exception as e:
        return {"error": f"JSON 파싱 실패: {e}", "raw": response_text[:1500]}

    added = 0
    for item_id, ko in tr.items():
        if isinstance(ko, str) and ko.strip():
            cache[_cache_key(kind, item_id)] = ko.strip()
            added += 1
    _save_translation_cache(cache)

    remaining = max(0, len(pending) - added)
    return {
        "translated": added, "requested": len(batch),
        "remaining": remaining, "total": len(all_items),
        "done": remaining == 0,
    }


# 하위 호환 shim
def api_commands_translate(body: dict) -> dict:
    b = dict(body or {})
    b["kind"] = "cmd"
    return api_translate_batch(b)


# ───────────────── MCP catalog ─────────────────

MCP_CATALOG = [
    {
        "id": "context7",
        "name": "Context7",
        "description": "최신 라이브러리 문서·예제를 실시간으로 가져오는 MCP (Upstash 제공)",
        "category": "docs",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
        "cli": "claude mcp add context7 npx -y @upstash/context7-mcp",
    },
    {
        "id": "github-official",
        "name": "GitHub (공식)",
        "description": "이슈/PR/커밋/워크플로 조작. GITHUB_TOKEN 필요.",
        "category": "dev",
        "install": {"type": "stdio", "command": "docker", "args": ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server"]},
        "cli": "claude mcp add github -e GITHUB_PERSONAL_ACCESS_TOKEN=... -- docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN ghcr.io/github/github-mcp-server",
    },
    {
        "id": "filesystem",
        "name": "Filesystem",
        "description": "지정한 디렉토리 파일 읽기/쓰기. 보안상 allow-list 필수.",
        "category": "utility",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/YOU/allowed-path"]},
        "cli": "claude mcp add filesystem npx -y @modelcontextprotocol/server-filesystem /Users/YOU/allowed-path",
    },
    {
        "id": "memory",
        "name": "Memory (knowledge graph)",
        "description": "세션 간 지식 그래프 저장 / 검색 (공식 MCP).",
        "category": "memory",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"]},
        "cli": "claude mcp add memory npx -y @modelcontextprotocol/server-memory",
    },
    {
        "id": "playwright",
        "name": "Playwright",
        "description": "실제 브라우저 자동화 (클릭/스냅샷/평가).",
        "category": "test",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@microsoft/mcp-server-playwright"]},
        "cli": "claude mcp add playwright npx -y @microsoft/mcp-server-playwright",
    },
    {
        "id": "puppeteer",
        "name": "Puppeteer",
        "description": "Playwright 대안. Chrome 자동화.",
        "category": "test",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-puppeteer"]},
        "cli": "claude mcp add puppeteer npx -y @modelcontextprotocol/server-puppeteer",
    },
    {
        "id": "brave-search",
        "name": "Brave Search",
        "description": "Brave API 기반 웹 검색. BRAVE_API_KEY 필요.",
        "category": "search",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-brave-search"], "env": {"BRAVE_API_KEY": ""}},
        "cli": "claude mcp add brave-search -e BRAVE_API_KEY=... -- npx -y @modelcontextprotocol/server-brave-search",
    },
    {
        "id": "fetch",
        "name": "Fetch",
        "description": "URL 가져오기 (HTML → 텍스트/마크다운 변환).",
        "category": "utility",
        "install": {"type": "stdio", "command": "uvx", "args": ["mcp-server-fetch"]},
        "cli": "claude mcp add fetch uvx mcp-server-fetch",
    },
    {
        "id": "sqlite",
        "name": "SQLite",
        "description": "로컬 SQLite DB 쿼리 실행.",
        "category": "db",
        "install": {"type": "stdio", "command": "uvx", "args": ["mcp-server-sqlite", "--db-path", "/absolute/path.db"]},
        "cli": "claude mcp add sqlite uvx mcp-server-sqlite --db-path /absolute/path.db",
    },
    {
        "id": "postgres",
        "name": "PostgreSQL",
        "description": "읽기 전용 Postgres 쿼리.",
        "category": "db",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://user:pass@host/db"]},
        "cli": "claude mcp add postgres npx -y @modelcontextprotocol/server-postgres postgresql://user:pass@host/db",
    },
    {
        "id": "slack",
        "name": "Slack",
        "description": "Slack 메시지 조회/전송. SLACK_BOT_TOKEN 필요.",
        "category": "messaging",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-slack"], "env": {"SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""}},
        "cli": "claude mcp add slack -e SLACK_BOT_TOKEN=... -e SLACK_TEAM_ID=... -- npx -y @modelcontextprotocol/server-slack",
    },
    {
        "id": "google-drive",
        "name": "Google Drive",
        "description": "Drive 검색 / 파일 가져오기 (OAuth 설정 필요).",
        "category": "productivity",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-gdrive"]},
        "cli": "claude mcp add gdrive npx -y @modelcontextprotocol/server-gdrive",
    },
    {
        "id": "sequential-thinking",
        "name": "Sequential Thinking",
        "description": "단계적 추론 프레임. 복잡한 설계 문제 정리용.",
        "category": "reasoning",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]},
        "cli": "claude mcp add seq-think npx -y @modelcontextprotocol/server-sequential-thinking",
    },
    {
        "id": "exa",
        "name": "Exa Search",
        "description": "AI 네이티브 웹 검색. EXA_API_KEY 필요.",
        "category": "search",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "exa-mcp-server"], "env": {"EXA_API_KEY": ""}},
        "cli": "claude mcp add exa -e EXA_API_KEY=... -- npx -y exa-mcp-server",
    },
    {
        "id": "linear",
        "name": "Linear",
        "description": "Linear 이슈/프로젝트 관리.",
        "category": "pm",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "linear-mcp"], "env": {"LINEAR_API_KEY": ""}},
        "cli": "claude mcp add linear -e LINEAR_API_KEY=... -- npx -y linear-mcp",
    },
    {
        "id": "notion",
        "name": "Notion",
        "description": "Notion 페이지 검색/편집.",
        "category": "productivity",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@makenotion/notion-mcp-server"], "env": {"INTERNAL_INTEGRATION_TOKEN": ""}},
        "cli": "claude mcp add notion -e INTERNAL_INTEGRATION_TOKEN=... -- npx -y @makenotion/notion-mcp-server",
    },
]


def api_mcp_catalog() -> dict:
    """알려진 MCP 카탈로그 + 현재 설치 상태."""
    installed = list_connectors()
    installed_names = set()
    for m in (installed.get("local", []) + installed.get("platform", [])):
        installed_names.add(m["name"])
    out = []
    for entry in MCP_CATALOG:
        out.append({**entry, "installed": entry["id"] in installed_names or entry["name"].lower().replace(" ", "-") in installed_names})
    return {"catalog": out, "installedCount": len(installed_names)}


def api_mcp_install(body: dict) -> dict:
    """~/.claude.json 의 mcpServers 에 엔트리 병합 저장.
    body: { "id": "context7", "as": "my-context7" (선택) }
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    entry_id = body.get("id") or ""
    as_name = (body.get("as") or entry_id).strip()
    spec = next((x for x in MCP_CATALOG if x["id"] == entry_id), None)
    if not spec:
        return {"ok": False, "error": "unknown mcp id"}
    if not CLAUDE_JSON.exists():
        return {"ok": False, "error": "~/.claude.json 없음. `claude login` 먼저 실행."}
    try:
        data = json.loads(_safe_read(CLAUDE_JSON, 500000))
    except Exception as e:
        return {"ok": False, "error": f".claude.json 파싱 실패: {e}"}
    mcp_servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
        data["mcpServers"] = mcp_servers
    if as_name in mcp_servers:
        return {"ok": False, "error": f"이미 '{as_name}' 이름으로 등록됨 — 다른 이름으로 시도하세요."}
    mcp_servers[as_name] = dict(spec["install"])
    # 안전한 쓰기
    text = json.dumps(data, indent=2, ensure_ascii=False)
    ok = _safe_write(CLAUDE_JSON, text)
    return {"ok": ok, "name": as_name, "note": "Claude Code 를 재시작하면 활성화됩니다."}


def api_mcp_remove(body: dict) -> dict:
    name = (body or {}).get("name") if isinstance(body, dict) else None
    if not name:
        return {"ok": False, "error": "name required"}
    if not CLAUDE_JSON.exists():
        return {"ok": False, "error": "~/.claude.json 없음"}
    try:
        data = json.loads(_safe_read(CLAUDE_JSON, 500000))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict) or name not in servers:
        return {"ok": False, "error": "등록된 MCP 서버가 아닙니다"}
    del servers[name]
    ok = _safe_write(CLAUDE_JSON, json.dumps(data, indent=2, ensure_ascii=False))
    return {"ok": ok}


# ───────────────── Plugin browsing ─────────────────

def api_plugins_browse() -> dict:
    """설치된 마켓플레이스의 모든 plugins 리스트 + 설치/활성 상태."""
    markets_dir = PLUGINS_DIR / "marketplaces"
    if not markets_dir.exists():
        return {"plugins": []}
    settings = get_settings()
    enabled = settings.get("enabledPlugins", {}) if isinstance(settings, dict) else {}

    installed_json = {}
    if INSTALLED_PLUGINS_JSON.exists():
        try:
            installed_json = json.loads(_safe_read(INSTALLED_PLUGINS_JSON))
        except Exception:
            installed_json = {}
    installed_plugins_map = installed_json.get("plugins", {}) if isinstance(installed_json, dict) else {}

    out = []
    for market in sorted(markets_dir.iterdir()):
        if not market.is_dir() or market.name.endswith(".bak"):
            continue
        plugins_root = market / "plugins"
        if not plugins_root.exists():
            continue
        # marketplace.json 읽기 시도
        mp_meta = {}
        for candidate in ("marketplace.json", ".claude-plugin/marketplace.json"):
            f = market / candidate
            if f.exists():
                try:
                    mp_meta = json.loads(_safe_read(f))
                    break
                except Exception:
                    pass

        mp_plugins = {}
        if isinstance(mp_meta, dict):
            for p in mp_meta.get("plugins", []) or []:
                if isinstance(p, dict) and p.get("name"):
                    mp_plugins[p["name"]] = p

        for plugin_dir in sorted(plugins_root.iterdir()):
            if not plugin_dir.is_dir():
                continue
            name = plugin_dir.name
            mp_entry = mp_plugins.get(name, {})
            desc = mp_entry.get("description", "")
            # fallback: plugin 디렉토리 내 claude-plugin.json
            if not desc:
                pj = plugin_dir / "claude-plugin.json"
                if pj.exists():
                    try:
                        pjd = json.loads(_safe_read(pj))
                        desc = pjd.get("description", "")
                    except Exception:
                        pass
            composite_id = f"{name}@{market.name}"
            is_installed = composite_id in installed_plugins_map
            is_enabled = bool(enabled.get(composite_id, False))
            # 구성 요소 개수
            agents_n = len(list((plugin_dir / "agents").glob("*.md"))) if (plugin_dir / "agents").exists() else 0
            skills_n = sum(1 for x in (plugin_dir / "skills").iterdir() if x.is_dir()) if (plugin_dir / "skills").exists() else 0
            commands_n = len(list((plugin_dir / "commands").glob("*.md"))) if (plugin_dir / "commands").exists() else 0
            hooks_n = len(list((plugin_dir / "hooks").iterdir())) if (plugin_dir / "hooks").exists() else 0
            out.append({
                "id": composite_id,
                "name": name,
                "marketplace": market.name,
                "description": desc,
                "author": (mp_entry.get("author") or {}).get("name") if isinstance(mp_entry.get("author"), dict) else mp_entry.get("author", ""),
                "tags": mp_entry.get("tags", []) if isinstance(mp_entry.get("tags"), list) else [],
                "version": mp_entry.get("version", ""),
                "installed": is_installed,
                "enabled": is_enabled,
                "counts": {"agents": agents_n, "skills": skills_n, "commands": commands_n, "hooks": hooks_n},
            })
    # 번역 주입
    cache = _load_translation_cache()
    for p in out:
        p["descriptionKo"] = cache.get(f"plugin:{p['id']}", "")
    return {"plugins": out, "marketplaces": len({m.name for m in markets_dir.iterdir() if m.is_dir() and not m.name.endswith('.bak')})}


def api_plugin_toggle(body: dict) -> dict:
    """settings.json 의 enabledPlugins 토글."""
    plugin_id = (body or {}).get("id")
    enable = bool((body or {}).get("enable", True))
    if not plugin_id:
        return {"ok": False, "error": "id required"}
    s = get_settings()
    if not isinstance(s, dict):
        s = {}
    ep = s.get("enabledPlugins")
    if not isinstance(ep, dict):
        ep = {}
        s["enabledPlugins"] = ep
    ep[plugin_id] = bool(enable)
    return put_settings(s)


# ───────────────── API: hooks ─────────────────

def _scan_plugin_hooks() -> list:
    """플러그인 마켓플레이스의 hooks/hooks.json 파싱 → 평탄화된 훅 리스트."""
    out = []
    if not PLUGINS_DIR.exists():
        return out
    markets_dir = PLUGINS_DIR / "marketplaces"
    if not markets_dir.exists():
        return out
    settings = get_settings()
    enabled_map = (settings.get("enabledPlugins") or {}) if isinstance(settings, dict) else {}

    def _collect(hooks_obj: dict, source_label: str, plugin_key: str):
        if not isinstance(hooks_obj, dict):
            return
        enabled = bool(enabled_map.get(plugin_key, False))
        for event, items in hooks_obj.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                sub = item.get("hooks")
                matcher = item.get("matcher")
                if isinstance(sub, list) and sub:
                    for sh in sub:
                        entry = {
                            "event": event,
                            "scope": "plugin",
                            "source": source_label,
                            "pluginKey": plugin_key,
                            "pluginEnabled": enabled,
                            "readOnly": True,
                        }
                        if matcher:
                            entry["matcher"] = matcher
                        if isinstance(sh, dict):
                            entry.update({k: v for k, v in sh.items() if k not in ("scope",)})
                        if "description" not in entry and item.get("description"):
                            entry["description"] = item.get("description")
                        out.append(entry)
                else:
                    entry = {
                        "event": event,
                        "scope": "plugin",
                        "source": source_label,
                        "pluginKey": plugin_key,
                        "pluginEnabled": enabled,
                        "readOnly": True,
                    }
                    entry.update({k: v for k, v in item.items() if k != "hooks"})
                    out.append(entry)

    for market in sorted(markets_dir.iterdir()):
        if not market.is_dir() or market.name.endswith(".bak"):
            continue
        # Layout A
        plugins_root = market / "plugins"
        if plugins_root.exists():
            for plugin_dir in sorted(plugins_root.iterdir()):
                if not plugin_dir.is_dir():
                    continue
                hf = plugin_dir / "hooks" / "hooks.json"
                if not hf.exists():
                    continue
                try:
                    data = json.loads(_safe_read(hf))
                except Exception:
                    continue
                _collect(
                    data.get("hooks", {}) if isinstance(data, dict) else {},
                    f"{market.name}/{plugin_dir.name}",
                    f"{plugin_dir.name}@{market.name}",
                )
        # Layout B
        hf = market / "hooks" / "hooks.json"
        if hf.exists():
            try:
                data = json.loads(_safe_read(hf))
            except Exception:
                data = {}
            _collect(
                data.get("hooks", {}) if isinstance(data, dict) else {},
                f"{market.name}",
                f"{market.name}@{market.name}",
            )
    return out


def get_hooks() -> dict:
    s = get_settings()
    permissions = s.get("permissions") or {"allow": [], "deny": []}
    if not isinstance(permissions, dict):
        permissions = {"allow": [], "deny": []}
    permissions.setdefault("allow", [])
    permissions.setdefault("deny", [])

    hooks_out = []
    raw_hooks = s.get("hooks", {})
    if isinstance(raw_hooks, dict):
        for event, items in raw_hooks.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                sub = item.get("hooks")
                matcher = item.get("matcher")
                if isinstance(sub, list) and sub:
                    for sh in sub:
                        entry = {"event": event, "scope": "user"}
                        if matcher:
                            entry["matcher"] = matcher
                        if isinstance(sh, dict):
                            entry.update(sh)
                        hooks_out.append(entry)
                else:
                    entry = {"event": event, "scope": "user"}
                    entry.update({k: v for k, v in item.items() if k != "hooks"})
                    hooks_out.append(entry)

    plugin_hooks = _scan_plugin_hooks()
    counts = {
        "user": len(hooks_out),
        "plugin": len(plugin_hooks),
        "pluginEnabled": sum(1 for h in plugin_hooks if h.get("pluginEnabled")),
    }
    return {"hooks": hooks_out + plugin_hooks, "permissions": permissions, "counts": counts}


# ───────────────── API: plugins ─────────────────

def list_plugins_api() -> list:
    if not INSTALLED_PLUGINS_JSON.exists():
        return []
    try:
        data = json.loads(_safe_read(INSTALLED_PLUGINS_JSON))
    except Exception:
        return []
    plugins_raw = data.get("plugins", {}) if isinstance(data, dict) else {}
    settings = get_settings()
    enabled_map = settings.get("enabledPlugins", {}) if isinstance(settings, dict) else {}
    out: list = []
    if not isinstance(plugins_raw, dict):
        return out
    for plugin_id, installs in plugins_raw.items():
        if not isinstance(installs, list) or not installs:
            continue
        latest = installs[-1] if isinstance(installs[-1], dict) else {}
        name = plugin_id.split("@")[0] if "@" in plugin_id else plugin_id
        marketplace = plugin_id.split("@")[1] if "@" in plugin_id else "unknown"
        out.append({
            "id": plugin_id, "name": name, "marketplace": marketplace,
            "version": latest.get("version", ""), "scope": latest.get("scope", "user"),
            "enabled": bool(enabled_map.get(plugin_id, False)),
            "installPath": latest.get("installPath", ""),
            "installedAt": latest.get("installedAt", ""),
            "lastUpdated": latest.get("lastUpdated", ""),
        })
    return out


def list_marketplaces() -> list:
    if not KNOWN_MARKETPLACES_JSON.exists():
        return []
    try:
        data = json.loads(_safe_read(KNOWN_MARKETPLACES_JSON))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    out = []
    for name, meta in data.items():
        if not isinstance(meta, dict):
            continue
        source = meta.get("source") or {}
        out.append({
            "id": name,
            "name": name,
            "type": source.get("source", ""),
            "repo": source.get("repo", ""),
            "installLocation": meta.get("installLocation", ""),
            "lastUpdated": meta.get("lastUpdated", ""),
        })
    return out


# ───────────────── API: connectors / MCP ─────────────────

def list_connectors() -> dict:
    platform_list: list = []
    local: list = []
    if CLAUDE_JSON.exists():
        try:
            data = json.loads(_safe_read(CLAUDE_JSON))
        except Exception:
            data = {}
        mcp = data.get("mcpServers", {}) if isinstance(data, dict) else {}
        if isinstance(mcp, dict):
            for name, cfg in mcp.items():
                if not isinstance(cfg, dict):
                    cfg = {}
                entry = {
                    "id": name, "name": name,
                    "type": cfg.get("type", "stdio"),
                    "command": cfg.get("command", ""),
                    "args": cfg.get("args", []),
                    "env": cfg.get("env", {}),
                    "scope": "user", "enabled": True, "tools": [],
                }
                if any(s in name.lower() for s in ("claude_ai_", "anthropic_", "claude.ai")):
                    platform_list.append(entry)
                else:
                    local.append(entry)
    return {"platform": platform_list, "local": local}


# ───────────────── API: projects ─────────────────

def _slug_to_cwd_map() -> dict:
    """DB에서 slug(project_dir) → 실제 cwd 매핑."""
    _db_init()
    mapping: dict = {}
    try:
        with _db() as c:
            for r in c.execute(
                "SELECT project_dir, MAX(cwd) AS cwd FROM sessions WHERE cwd != '' GROUP BY project_dir"
            ).fetchall():
                if r["project_dir"] and r["cwd"]:
                    mapping[r["project_dir"]] = r["cwd"]
    except Exception:
        pass
    return mapping


def _resolve_cwd_from_jsonl(meta_dir: Path) -> str:
    """메타 디렉토리 하위 jsonl 첫 줄에서 cwd 복원 (DB 미인덱스 세션용 fallback)."""
    for jsonl in meta_dir.glob("*.jsonl"):
        try:
            text = jsonl.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines()[:30]:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                c_val = msg.get("cwd")
                if isinstance(c_val, str) and c_val:
                    return c_val
        except Exception:
            continue
    return ""


def list_projects() -> dict:
    projects = []
    if not PROJECTS_DIR.exists():
        return {"projects": []}

    slug_map = _slug_to_cwd_map()

    for p in sorted(PROJECTS_DIR.iterdir()):
        if not p.is_dir():
            continue
        slug = p.name
        cwd = slug_map.get(slug) or _resolve_cwd_from_jsonl(p)

        name = Path(cwd).name if cwd else slug
        has_claude_md = False
        if cwd:
            try:
                has_claude_md = (Path(cwd) / "CLAUDE.md").exists()
            except Exception:
                has_claude_md = False

        session_files = list(p.glob("*.jsonl"))
        projects.append({
            "name": name,
            "slug": slug,
            "path": cwd,                 # 실제 cwd (없으면 빈 문자열)
            "metaDir": str(p),           # ~/.claude/projects/<slug>
            "cwdResolved": bool(cwd),
            "hasClaudeMd": has_claude_md,
            "sessionCount": len(session_files),
        })
    return {"projects": projects}


# ───────────────── briefing (original) ─────────────────

def _today_start_ts_ms() -> int:
    midnight = datetime.combine(date.today(), datetime.min.time())
    return int(midnight.timestamp() * 1000)


def _iter_history_recent(limit_lines: int = 5000):
    if not HISTORY_JSONL.exists():
        return
    try:
        lines = HISTORY_JSONL.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-limit_lines:]:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue
    except Exception:
        return


def _today_history_stats() -> dict:
    today_start = _today_start_ts_ms()
    cmd_count = 0
    projects_today = set()
    for entry in _iter_history_recent():
        ts = entry.get("timestamp")
        if not isinstance(ts, (int, float)):
            continue
        if ts >= today_start:
            cmd_count += 1
            proj = entry.get("project")
            if proj:
                projects_today.add(proj)
    return {"commandCount": cmd_count, "projectCount": len(projects_today)}


def _count_projects() -> int:
    if not PROJECTS_DIR.exists():
        return 0
    return sum(1 for p in PROJECTS_DIR.iterdir() if p.is_dir())


def _count_active_sessions() -> int:
    if not SESSIONS_DIR.exists():
        return 0
    return sum(1 for p in SESSIONS_DIR.glob("*.json"))


def _count_tasks_in_todos() -> int:
    if not TODOS_DIR.exists():
        return 0
    total = 0
    for p in TODOS_DIR.glob("*.json"):
        try:
            data = json.loads(_safe_read(p))
            if isinstance(data, list):
                total += len(data)
        except Exception:
            pass
    return total


# ───────────────── NEW: session DB endpoints ─────────────────

def api_sessions_list(query: dict) -> dict:
    _db_init()
    limit = int(query.get("limit", ["200"])[0])
    offset = int(query.get("offset", ["0"])[0])
    q = (query.get("q", [""])[0] or "").strip()
    project = (query.get("project", [""])[0] or "").strip()
    sort = (query.get("sort", ["recent"])[0] or "recent").strip()

    sql = "SELECT * FROM sessions WHERE 1=1"
    params: list = []
    if q:
        sql += " AND (first_user_prompt LIKE ? OR project LIKE ? OR session_id LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if project:
        sql += " AND project_dir = ?"
        params.append(project)
    order_col = {
        "recent": "started_at DESC",
        "score": "score DESC",
        "tools": "tool_use_count DESC",
        "duration": "duration_ms DESC",
    }.get(sort, "started_at DESC")
    sql += f" ORDER BY {order_col} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with _db() as c:
        rows = [dict(r) for r in c.execute(sql, params).fetchall()]
        total = c.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
    for r in rows:
        try:
            r["score_breakdown"] = json.loads(r.get("score_breakdown") or "{}")
        except Exception:
            r["score_breakdown"] = {}
        try:
            r["subagent_types"] = json.loads(r.get("subagent_types") or "{}")
        except Exception:
            r["subagent_types"] = {}
        # display helpers
        cwd = r.get("cwd") or ""
        r["project"] = Path(cwd).name if cwd else (r.get("project") or "")
        r["projectPath"] = cwd
    return {"sessions": rows, "total": total}


def api_session_detail(session_id: str) -> dict:
    _db_init()
    with _db() as c:
        row = c.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not row:
            return {"error": "not found"}
        tools = [dict(r) for r in c.execute(
            "SELECT ts,tool,subagent_type,input_summary,had_error FROM tool_uses WHERE session_id=? ORDER BY ts ASC LIMIT 500",
            (session_id,)
        ).fetchall()]
        edges = [dict(r) for r in c.execute(
            "SELECT src,dst,ts FROM agent_edges WHERE session_id=? ORDER BY ts ASC",
            (session_id,)
        ).fetchall()]
    d = dict(row)
    try:
        d["score_breakdown"] = json.loads(d.get("score_breakdown") or "{}")
    except Exception:
        d["score_breakdown"] = {}
    try:
        d["subagent_types"] = json.loads(d.get("subagent_types") or "{}")
    except Exception:
        d["subagent_types"] = {}

    # messages preview from jsonl
    messages = []
    jp = d.get("jsonl_path")
    if jp and Path(jp).exists():
        try:
            for i, line in enumerate(Path(jp).read_text(encoding="utf-8", errors="replace").splitlines()):
                if i > 400:
                    break
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                t = msg.get("type")
                if t not in ("user", "assistant"):
                    continue
                preview = ""
                role = t
                content = (msg.get("message") or {}).get("content")
                if isinstance(content, str):
                    preview = content[:600]
                elif isinstance(content, list):
                    parts = []
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "text":
                            parts.append(b.get("text", ""))
                        elif b.get("type") == "tool_use":
                            parts.append(f"[tool: {b.get('name','')} ]")
                        elif b.get("type") == "tool_result":
                            parts.append("[result]")
                    preview = "\n".join(parts)[:600]
                messages.append({
                    "role": role,
                    "ts": _iso_ms(msg.get("timestamp", "") or ""),
                    "preview": preview,
                })
        except Exception:
            pass

    return {"session": d, "tools": tools, "edges": edges, "messages": messages}


def api_sessions_stats() -> dict:
    _db_init()
    with _db() as c:
        total = c.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
        avg = c.execute("SELECT COALESCE(AVG(score), 0) AS s FROM sessions").fetchone()["s"]
        total_tools = c.execute("SELECT COALESCE(SUM(tool_use_count),0) AS n FROM sessions").fetchone()["n"]
        total_agents = c.execute("SELECT COALESCE(SUM(agent_call_count),0) AS n FROM sessions").fetchone()["n"]
        total_errors = c.execute("SELECT COALESCE(SUM(error_count),0) AS n FROM sessions").fetchone()["n"]

        tool_rows = [dict(r) for r in c.execute(
            "SELECT tool, COUNT(*) AS n FROM tool_uses GROUP BY tool ORDER BY n DESC LIMIT 20"
        ).fetchall()]
        subagent_rows = [dict(r) for r in c.execute(
            "SELECT subagent_type AS name, COUNT(*) AS n FROM tool_uses WHERE subagent_type != '' GROUP BY subagent_type ORDER BY n DESC"
        ).fetchall()]
        top_sessions = [dict(r) for r in c.execute(
            "SELECT session_id, project, score, started_at, first_user_prompt FROM sessions ORDER BY score DESC LIMIT 10"
        ).fetchall()]
        proj_rows = [dict(r) for r in c.execute(
            """SELECT
                COALESCE(NULLIF(cwd,''), project_dir) AS key,
                MAX(cwd) AS cwd,
                MAX(project_dir) AS project_dir,
                COUNT(*) AS sessions,
                AVG(score) AS avg_score,
                SUM(tool_use_count) AS tools
               FROM sessions
               GROUP BY COALESCE(NULLIF(cwd,''), project_dir)
               ORDER BY sessions DESC"""
        ).fetchall()]
    # name = cwd 의 basename (없으면 슬러그)
    for r in proj_rows:
        cwd = r.get("cwd") or ""
        r["name"] = Path(cwd).name if cwd else (r.get("project_dir") or "")

        # daily timeline (last 30 days)
        thirty_days_ago = int((time.time() - 30 * 86400) * 1000)
        daily_rows = c.execute(
            "SELECT started_at, score, tool_use_count, error_count FROM sessions WHERE started_at >= ? ORDER BY started_at",
            (thirty_days_ago,)
        ).fetchall()

    # bucket by day
    buckets: dict = defaultdict(lambda: {"sessions": 0, "tools": 0, "errors": 0, "score_sum": 0})
    for r in daily_rows:
        if not r["started_at"]:
            continue
        d = datetime.fromtimestamp(r["started_at"] / 1000).strftime("%Y-%m-%d")
        b = buckets[d]
        b["sessions"] += 1
        b["tools"] += r["tool_use_count"] or 0
        b["errors"] += r["error_count"] or 0
        b["score_sum"] += r["score"] or 0
    timeline = []
    for d in sorted(buckets.keys()):
        b = buckets[d]
        timeline.append({
            "date": d,
            "sessions": b["sessions"],
            "tools": b["tools"],
            "errors": b["errors"],
            "avg_score": round(b["score_sum"] / max(1, b["sessions"]), 1),
        })

    return {
        "totalSessions": total,
        "avgScore": round(avg, 1),
        "totalTools": total_tools,
        "totalAgentCalls": total_agents,
        "totalErrors": total_errors,
        "toolDistribution": tool_rows,
        "subagentDistribution": subagent_rows,
        "topSessions": top_sessions,
        "projectDistribution": proj_rows,
        "timeline": timeline,
    }


def api_agent_graph(query: dict) -> dict:
    _db_init()
    days = int(query.get("days", ["30"])[0])
    since = int((time.time() - days * 86400) * 1000)
    with _db() as c:
        edges = c.execute(
            "SELECT src,dst,COUNT(*) AS n FROM agent_edges WHERE ts >= ? GROUP BY src,dst ORDER BY n DESC",
            (since,)
        ).fetchall()
        tool_rows = c.execute(
            "SELECT subagent_type AS agent, tool, COUNT(*) AS n FROM tool_uses WHERE subagent_type != '' AND ts >= ? GROUP BY subagent_type, tool",
            (since,)
        ).fetchall()

    nodes: dict = {}
    def _ensure(nid: str, kind: str, label: Optional[str] = None):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "kind": kind, "label": label or nid}

    _ensure("claude", "core", "Claude (메인)")
    edge_list = []
    for r in edges:
        src, dst, n = r["src"], r["dst"], r["n"]
        _ensure(src, "core" if src == "claude" else "agent")
        _ensure(dst, "agent")
        edge_list.append({"src": src, "dst": dst, "weight": n})
    for r in tool_rows:
        agent, tool, n = r["agent"], r["tool"], r["n"]
        _ensure(agent, "agent")
        tool_id = f"tool:{tool}"
        _ensure(tool_id, "tool", tool)
        edge_list.append({"src": agent, "dst": tool_id, "weight": n})

    return {"nodes": list(nodes.values()), "edges": edge_list}


def _count_enabled_plugin_assets() -> dict:
    """활성화된 플러그인들이 실제로 제공하는 스킬/커맨드/훅/에이전트 카운트.
    훅은 hooks.json 안의 항목을 평탄화하여 카운트 (파일 수 ×).
    """
    settings = get_settings()
    enabled_map = (settings.get("enabledPlugins") or {}) if isinstance(settings, dict) else {}
    enabled_keys = {k for k, v in enabled_map.items() if v}
    res = {"skills": 0, "commands": 0, "agents": 0, "hooks": 0, "enabledPluginKeys": list(enabled_keys)}
    if not enabled_keys:
        return res
    markets_dir = PLUGINS_DIR / "marketplaces"
    if not markets_dir.exists():
        return res

    def _count_hooks_json(p: Path) -> int:
        try:
            data = json.loads(_safe_read(p))
        except Exception:
            return 0
        n = 0
        hooks_obj = data.get("hooks", {}) if isinstance(data, dict) else {}
        for _ev, items in hooks_obj.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                sub = item.get("hooks")
                if isinstance(sub, list):
                    n += len(sub)
                else:
                    n += 1
        return n

    for key in enabled_keys:
        if "@" not in key:
            continue
        plugin_name, market_name = key.split("@", 1)
        market_dir = markets_dir / market_name
        if not market_dir.exists() or market_dir.name.endswith(".bak"):
            continue
        layout_a = market_dir / "plugins" / plugin_name
        layout_b = market_dir if plugin_name == market_name else None
        for base in [p for p in (layout_a, layout_b) if p and p.exists()]:
            skills_dir = base / "skills"
            if skills_dir.exists():
                res["skills"] += sum(1 for x in skills_dir.iterdir() if x.is_dir() and (x / "SKILL.md").exists())
            cmd_dir = base / "commands"
            if cmd_dir.exists():
                res["commands"] += len(list(cmd_dir.rglob("*.md")))
            agents_dir = base / "agents"
            if agents_dir.exists():
                res["agents"] += len(list(agents_dir.glob("*.md")))
            hooks_json = base / "hooks" / "hooks.json"
            if hooks_json.exists():
                res["hooks"] += _count_hooks_json(hooks_json)
    return res


def api_optimization_score() -> dict:
    """전반적 최적화 스코어 — **사용자가 직접 설정한 자원**만 카운트.
    플러그인이 제공하는 자원은 별도 'plugins' 축에서 측정 (이중 가산 ×).
    """
    _db_init()
    score = {}

    s = get_settings()
    permissions = s.get("permissions", {}) if isinstance(s, dict) else {}
    allow_n = len(permissions.get("allow", []) if isinstance(permissions, dict) else [])
    deny_n = len(permissions.get("deny", []) if isinstance(permissions, dict) else [])

    # 사용자가 settings.json 에 직접 설정한 훅만 카운트
    user_hook_n = 0
    for _ev, items in (s.get("hooks", {}) or {}).items():
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    sub = item.get("hooks")
                    user_hook_n += len(sub) if isinstance(sub, list) else 1
    plugin_assets = _count_enabled_plugin_assets()  # 점수에는 미반영, 표시용

    perm_raw = allow_n * 4 + deny_n * 3
    score["permissions"] = {
        "value": min(100, perm_raw), "max": 100,
        "note": f"허용 {allow_n}개 / 차단 {deny_n}개",
        "formula": f"min(100, 허용×4 + 차단×3) = min(100, {allow_n}×4 + {deny_n}×3) = min(100, {perm_raw})",
        "suggest": "deny 규칙 늘리면 안전도 ↑. 자주 쓰는 명령을 allow 해 승인 프롬프트 ↓.",
        "target": "permissions",
    }

    hook_raw = user_hook_n * 15
    score["hooks"] = {
        "value": min(100, hook_raw), "max": 100,
        "note": f"사용자 설정 훅 {user_hook_n}개 (settings.json) · 플러그인 제공 {plugin_assets['hooks']}개는 'plugins' 축에서 평가",
        "formula": f"min(100, 사용자훅×15) = min(100, {user_hook_n}×15) = min(100, {hook_raw})",
        "suggest": "settings.json 에 SessionStart 훅 하나만 추가해도 +15점. 최대 7개 = 만점.",
        "target": "hooks",
    }

    # === Agents: 사용자가 직접 만든 것 (~/.claude/agents) + 빌트인 ===
    agents_data = list_agents()
    counts = agents_data.get("counts", {})
    user_agents_n = counts.get("global", 0)
    builtin_n = counts.get("builtin", 0)
    plugin_total = counts.get("plugin", 0)
    plugin_enabled_n = counts.get("pluginEnabled", 0)
    configured_agents = user_agents_n + builtin_n
    ag_raw = configured_agents * 10  # 사용자 설정 1개 = 10점
    score["agents"] = {
        "value": min(100, ag_raw), "max": 100,
        "note": f"사용자 설정 {user_agents_n}개 + 빌트인 {builtin_n}개 = {configured_agents}개 · 플러그인 제공 {plugin_enabled_n}/{plugin_total} 활성 (별도)",
        "formula": f"min(100, 사용자에이전트×10) = min(100, {configured_agents}×10) = min(100, {ag_raw})",
        "suggest": "~/.claude/agents/<name>.md 로 자신만의 서브에이전트 추가. 1개 = +10점.",
        "target": "agents",
    }

    # === Skills: 사용자가 직접 만든 것 (~/.claude/skills) ===
    user_skills_n = sum(1 for s in list_skills() if s.get("scope") == "user")
    plugin_skills_n = plugin_assets["skills"]
    sk_raw = user_skills_n * 8  # 1개 = 8점, 최대 13개로 만점
    score["skills"] = {
        "value": min(100, sk_raw), "max": 100,
        "note": f"사용자 설정 {user_skills_n}개 (~/.claude/skills) · 플러그인 제공 {plugin_skills_n}개는 'plugins' 축에서 평가",
        "formula": f"min(100, 사용자스킬×8) = min(100, {user_skills_n}×8) = min(100, {sk_raw})",
        "suggest": "~/.claude/skills/<id>/SKILL.md 로 자신만의 스킬 추가. 13개 = 만점.",
        "target": "skills",
    }

    plugins = list_plugins_api()
    enabled = sum(1 for p in plugins if p.get("enabled"))
    pl_raw = enabled * 6
    score["plugins"] = {
        "value": min(100, pl_raw), "max": 100,
        "note": f"플러그인 활성 {enabled} / 설치 {len(plugins)}",
        "formula": f"min(100, 활성플러그인×6) = min(100, {enabled}×6) = min(100, {pl_raw})",
        "suggest": "플러그인 1개 활성화 = +6점. 플러그인 탭에서 토글.",
        "target": "plugins",
    }

    connectors = list_connectors()
    mcp_local = len(connectors.get("local", []))
    mcp_platform = len(connectors.get("platform", []))
    mcp_n = mcp_local + mcp_platform
    mcp_raw = mcp_n * 8
    score["mcp"] = {
        "value": min(100, mcp_raw), "max": 100,
        "note": f"MCP 서버 {mcp_n}개 (로컬 {mcp_local} + 플랫폼 {mcp_platform})",
        "formula": f"min(100, MCP수×8) = min(100, {mcp_n}×8) = min(100, {mcp_raw})",
        "suggest": "MCP 탭의 카탈로그에서 Context7, GitHub, Memory 등 원클릭 설치.",
        "target": "mcp",
    }

    with _db() as c:
        row = c.execute("SELECT AVG(score) AS s, COUNT(*) AS n FROM sessions").fetchone()
    avg = int(row["s"] or 0)
    sess_n = row["n"] or 0
    score["sessionQuality"] = {
        "value": avg, "max": 100,
        "note": f"평균 세션 스코어 ({sess_n}개 세션 기준)",
        "formula": f"AVG(세션별 100점 만점 스코어) = {avg} · 각 세션: engagement+productivity+delegation+diversity+reliability",
        "suggest": "통계 탭의 프로젝트 행 클릭 → 5축별 계산식 상세 확인.",
        "target": "analytics",
    }

    overall = int(sum(v["value"] for v in score.values()) / len(score))

    # 추천 액션
    recs = []
    if user_hook_n == 0:
        recs.append({"icon": "🪝", "title": "훅 설정하기", "detail": "SessionStart 훅으로 이전 세션 요약 자동 로드. 효율 크게 상승."})
    if deny_n < 5:
        recs.append({"icon": "🛡️", "title": "거부 규칙 강화", "detail": "rm -rf, sudo, .env 편집 등을 deny 목록에 추가하세요."})
    if allow_n < 10:
        recs.append({"icon": "✅", "title": "자주 쓰는 명령 허용", "detail": "권한 프롬프트를 줄이려면 git, npm, docker 등 안전 명령을 allow에 추가."})
    if avg < 60 and sess_n > 5:
        recs.append({"icon": "📈", "title": "세션 스코어 낮음", "detail": "에이전트 위임과 도구 다양성을 늘리면 스코어가 상승합니다."})
    if enabled < 3 and len(plugins) > 0:
        recs.append({"icon": "🔌", "title": "플러그인 활성화", "detail": "설치했지만 비활성화된 플러그인이 있습니다. settings.json enabledPlugins 확인."})
    if mcp_n < 3:
        recs.append({"icon": "🔗", "title": "MCP 커넥터 추가", "detail": "Context7, GitHub, Memory 같은 MCP로 에이전트 능력이 크게 확장됩니다."})

    return {"overall": overall, "breakdown": score, "recommendations": recs}


# ───────────────── original briefing ─────────────────

def briefing_overview() -> dict:
    today = _today_history_stats()
    return {
        "projectCount": _count_projects(),
        "taskCount": _count_tasks_in_todos(),
        "sessionCount": _count_active_sessions(),
        "commandCount": today["commandCount"],
        "todayProjectCount": today["projectCount"],
        "lastUpdate": int(time.time() * 1000),
    }


def briefing_devices() -> dict:
    info = _detect_device_info()
    real_username = info["username"]
    device_label = info["label"]
    all_projects: dict = {}
    for entry in _iter_history_recent(limit_lines=3000):
        proj = entry.get("project")
        ts = entry.get("timestamp")
        if not proj or not isinstance(ts, (int, float)):
            continue
        slot = all_projects.setdefault(proj, {"displayName": Path(proj).name or proj, "path": proj, "lastActivity": 0})
        if ts > slot["lastActivity"]:
            slot["lastActivity"] = ts
    devices = []
    if all_projects:
        recent = sorted(all_projects.values(), key=lambda x: x["lastActivity"], reverse=True)[:8]
        devices.append({
            "id": real_username, "label": device_label,
            "projectCount": len(all_projects), "recentProjects": recent,
        })
    return {"devices": devices}


def briefing_activity() -> dict:
    today = _today_history_stats()
    return {"today": {"commandCount": today["commandCount"], "projectCount": today["projectCount"]}, "activities": []}


def _read_scheduled_tasks() -> list:
    out = []
    if not SCHEDULED_TASKS_DIR.exists():
        return out
    for d in sorted(SCHEDULED_TASKS_DIR.iterdir()):
        if not d.is_dir():
            continue
        skill_md = d / "SKILL.md"
        meta = {}
        updated_at = None
        if skill_md.exists():
            meta = _parse_frontmatter(_safe_read(skill_md, 4000))
            try:
                updated_at = int(skill_md.stat().st_mtime * 1000)
            except Exception:
                updated_at = None
        out.append({
            "id": d.name, "title": meta.get("name", d.name),
            "name": meta.get("name", d.name),
            "description": meta.get("description", ""),
            "updatedAt": updated_at,
        })
    return out


def _read_tasks() -> list:
    out = []
    if not TASKS_DIR.exists():
        return out
    device = _detect_device_info()["label"]
    for d in sorted(TASKS_DIR.iterdir()):
        if not d.is_dir():
            continue
        task_id = d.name
        is_uuid = bool(_UUID_RE.match(task_id))
        kind = "agent" if is_uuid else "named"
        subtasks = []
        try:
            for f in sorted(d.glob("*.json")):
                try:
                    data = json.loads(_safe_read(f))
                    if isinstance(data, dict):
                        subtasks.append({
                            "id": data.get("id", f.stem),
                            "subject": data.get("subject", ""),
                            "description": (data.get("description") or "")[:200],
                            "status": data.get("status", "pending"),
                        })
                except Exception:
                    continue
        except Exception:
            pass
        total = len(subtasks)
        completed = sum(1 for s in subtasks if s["status"] == "completed")
        try:
            updated_at = int(d.stat().st_mtime * 1000)
        except Exception:
            updated_at = None
        out.append({
            "id": task_id, "kind": kind,
            "teamName": task_id if not is_uuid else "",
            "totalCount": total, "completedCount": completed,
            "lockActive": (d / ".lock").exists(),
            "device": device, "updatedAt": updated_at, "subtasks": subtasks,
        })
    return out


def briefing_schedule() -> dict:
    return {"scheduled": _read_scheduled_tasks(), "tasks": _read_tasks()}


def briefing_projects_summary() -> dict:
    by_project: dict = {}
    for entry in _iter_history_recent(limit_lines=5000):
        proj = entry.get("project")
        ts = entry.get("timestamp")
        if not proj or not isinstance(ts, (int, float)):
            continue
        display = (entry.get("display") or "").strip()
        slot = by_project.setdefault(proj, {
            "displayName": Path(proj).name or proj,
            "cwd": proj,
            "device": _detect_device_info()["label"],
            "sessionCount": 0, "lastActivity": 0,
            "firstRequest": "", "firstTs": 0, "lastResult": "",
        })
        slot["sessionCount"] += 1
        if ts > slot["lastActivity"]:
            slot["lastActivity"] = ts
            if display:
                slot["lastResult"] = display[:160]
        if slot["firstTs"] == 0 or ts < slot["firstTs"]:
            slot["firstTs"] = ts
            if display:
                slot["firstRequest"] = display[:160]
    for v in by_project.values():
        v.pop("firstTs", None)
    summaries = sorted(by_project.values(), key=lambda x: x["lastActivity"], reverse=True)[:20]
    return {"summaries": summaries, "projects": list_projects().get("projects", [])}


def briefing_pending_approvals() -> dict:
    out: list = []
    if not SESSIONS_DIR.exists():
        return {"approvals": [], "pending": out}
    now_ms = int(time.time() * 1000)
    for p in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            sd = json.loads(_safe_read(p))
        except Exception:
            continue
        if not isinstance(sd, dict):
            continue
        sid = sd.get("sessionId")
        cwd = sd.get("cwd") or ""
        if not sid:
            continue
        jsonl_files = list(PROJECTS_DIR.glob(f"*/{sid}.jsonl"))
        if not jsonl_files:
            continue
        jsonl = jsonl_files[0]
        last_tool = None
        last_ts_ms = None
        try:
            text = jsonl.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()[-150:]
            for line in reversed(lines):
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                if msg.get("type") != "assistant":
                    continue
                content = (msg.get("message") or {}).get("content", [])
                if not isinstance(content, list):
                    continue
                tool_name = None
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        tool_name = c.get("name")
                        break
                if tool_name:
                    ts_str = msg.get("timestamp", "")
                    last_ts_ms = _iso_ms(ts_str)
                    last_tool = tool_name
                    break
        except Exception:
            continue
        if not last_tool:
            continue
        age_seconds = max(0, (now_ms - last_ts_ms) // 1000) if last_ts_ms else 0
        out.append({
            "project": Path(cwd).name or sid[:8],
            "tool": last_tool,
            "device": _detect_device_info()["label"],
            "ageSeconds": int(age_seconds),
            "sessionId": sid,
        })
    out.sort(key=lambda x: x["ageSeconds"])
    return {"approvals": [], "pending": out}


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


# ───────────────── NEW: auth / project detail / settings preview ─────────────────

COST_LOG = CLAUDE_HOME / "cost-tracker.log"
BASH_LOG = CLAUDE_HOME / "bash-commands.log"

def api_usage_summary() -> dict:
    """cost-tracker.log 에서 지난 30일 사용량 집계 (파일 크기, 라인 수, 도구별, 날짜별)."""
    from collections import defaultdict
    if not COST_LOG.exists():
        return {"exists": False}
    try:
        text = COST_LOG.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"exists": True, "error": str(e)}
    lines = text.splitlines()
    tool_count: dict = defaultdict(int)
    daily: dict = defaultdict(int)
    parsed = 0
    for line in lines:
        m = re.match(r"^\[(\d{4}-\d{2}-\d{2})T[^\]]+\]\s+tool=(\S+)", line)
        if not m:
            continue
        parsed += 1
        day = m.group(1)
        tool = m.group(2)
        tool_count[tool] += 1
        daily[day] += 1
    # 최근 30일만
    sorted_days = sorted(daily.keys())[-30:]
    timeline = [{"date": d, "count": daily[d]} for d in sorted_days]
    top_tools = sorted(tool_count.items(), key=lambda x: -x[1])[:20]
    return {
        "exists": True,
        "totalLines": len(lines),
        "parsedEvents": parsed,
        "firstLine": lines[0][:120] if lines else "",
        "lastLine": lines[-1][:120] if lines else "",
        "timeline": timeline,
        "topTools": [{"tool": t, "n": n} for t, n in top_tools],
        "fileSize": COST_LOG.stat().st_size,
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
    """metrics/costs.jsonl 를 파싱해 일자별 토큰/비용 요약."""
    from collections import defaultdict
    if not METRICS_COSTS_JSONL.exists():
        return {"exists": False}
    daily: dict = defaultdict(lambda: {"in": 0, "out": 0, "cost": 0.0, "n": 0})
    by_model: dict = defaultdict(lambda: {"in": 0, "out": 0, "cost": 0.0, "n": 0})
    total = {"in": 0, "out": 0, "cost": 0.0, "n": 0}
    try:
        for line in METRICS_COSTS_JSONL.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            ts = e.get("timestamp", "")
            day = ts[:10] if ts else ""
            model = e.get("model", "unknown")
            ti = int(e.get("input_tokens") or 0)
            to = int(e.get("output_tokens") or 0)
            cost = float(e.get("estimated_cost_usd") or 0)
            if day:
                daily[day]["in"] += ti
                daily[day]["out"] += to
                daily[day]["cost"] += cost
                daily[day]["n"] += 1
            by_model[model]["in"] += ti
            by_model[model]["out"] += to
            by_model[model]["cost"] += cost
            by_model[model]["n"] += 1
            total["in"] += ti
            total["out"] += to
            total["cost"] += cost
            total["n"] += 1
    except Exception as e:
        return {"exists": True, "error": str(e)}

    timeline = [{"date": d, **v} for d, v in sorted(daily.items())][-60:]
    models = sorted(
        [{"model": m, **v} for m, v in by_model.items()],
        key=lambda x: x["cost"], reverse=True,
    )[:20]
    return {"exists": True, "total": total, "timeline": timeline, "models": models}


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
    """~/.claude/scheduled-tasks/ 목록."""
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
    return {"tasks": out, "dirExists": SCHEDULED_TASKS_DIR.exists()}


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


def api_marketplace_list() -> dict:
    """known_marketplaces.json + settings.extraKnownMarketplaces."""
    km = {}
    if KNOWN_MARKETPLACES_JSON.exists():
        try:
            km = json.loads(_safe_read(KNOWN_MARKETPLACES_JSON))
        except Exception:
            km = {}
    s = get_settings()
    extra = (s.get("extraKnownMarketplaces") if isinstance(s, dict) else None) or {}
    out = []
    for name, meta in {**km, **extra}.items():
        src = (meta or {}).get("source") or {}
        out.append({
            "id": name,
            "name": name,
            "type": src.get("source", ""),
            "repo": src.get("repo") or src.get("url") or "",
            "installLocation": meta.get("installLocation", ""),
            "lastUpdated": meta.get("lastUpdated", ""),
            "inSettingsExtra": name in extra,
        })
    return {"marketplaces": out}


def api_marketplace_add(body: dict) -> dict:
    """settings.json 의 extraKnownMarketplaces 에 추가. body: {name, url}"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    name = (body.get("name") or "").strip()
    url = (body.get("url") or "").strip()
    if not re.match(r"^[a-zA-Z0-9_.-]+$", name):
        return {"ok": False, "error": "이름은 영숫자/-/_/. 만 허용"}
    if not url.startswith("http"):
        return {"ok": False, "error": "git URL 필요"}
    s = get_settings()
    if not isinstance(s, dict):
        s = {}
    extra = s.get("extraKnownMarketplaces") or {}
    extra[name] = {"source": {"source": "git", "url": url}}
    s["extraKnownMarketplaces"] = extra
    return put_settings(s)


def api_marketplace_remove(body: dict) -> dict:
    name = (body or {}).get("name") if isinstance(body, dict) else None
    if not name:
        return {"ok": False, "error": "name required"}
    s = get_settings()
    extra = s.get("extraKnownMarketplaces") if isinstance(s, dict) else None
    if not isinstance(extra, dict) or name not in extra:
        return {"ok": False, "error": "등록된 마켓플레이스가 아닙니다"}
    del extra[name]
    s["extraKnownMarketplaces"] = extra
    return put_settings(s)


def api_team_info() -> dict:
    """조직/워크스페이스/팀 정보 (claude.ai team 기능용)."""
    if not CLAUDE_JSON.exists():
        return {"connected": False}
    try:
        data = json.loads(_safe_read(CLAUDE_JSON, 500000))
    except Exception as e:
        return {"connected": False, "error": str(e)}
    oauth = data.get("oauthAccount") or {}
    cfg = _load_dash_config()
    claimed = cfg.get("claimedPlan") or ""
    return {
        "connected": bool(oauth),
        "displayName": oauth.get("displayName", ""),
        "email": oauth.get("emailAddress", ""),
        "organizationUuid": oauth.get("organizationUuid", ""),
        "organizationName": oauth.get("organizationName", ""),
        "organizationRole": oauth.get("organizationRole", ""),
        "workspaceRole": oauth.get("workspaceRole"),
        "accountUuid": oauth.get("accountUuid", ""),
        "billingType": oauth.get("billingType", ""),
        "hasExtraUsageEnabled": bool(oauth.get("hasExtraUsageEnabled", False)),
        "claimedPlan": claimed,
        "note": "상세 멤버 리스트/사용량은 claude.ai/settings/organization 에서 관리됩니다. 로컬에는 조직 식별자만 저장됨.",
    }


def api_auth_status() -> dict:
    """~/.claude.json 에서 oauth 정보 읽어 연결 상태 반환 + claude CLI 설치 여부."""
    cli_path = shutil.which("claude") or ""
    cli_version = ""
    if cli_path:
        try:
            cli_version = subprocess.check_output(
                [cli_path, "--version"], text=True, timeout=5,
            ).strip()
        except Exception:
            cli_version = ""

    if not CLAUDE_JSON.exists():
        return {
            "connected": False,
            "reason": "~/.claude.json 이 없습니다 — Claude Code에 로그인하세요.",
            "cliInstalled": bool(cli_path),
            "cliPath": cli_path,
            "cliVersion": cli_version,
        }
    try:
        data = json.loads(_safe_read(CLAUDE_JSON, 200000))
    except Exception as e:
        return {"connected": False, "reason": f"~/.claude.json 파싱 실패: {e}"}

    oauth = data.get("oauthAccount") or {}
    if not oauth:
        return {
            "connected": False, "reason": "OAuth 계정 없음 — `claude login` 실행 필요.",
            "cliInstalled": bool(cli_path), "cliPath": cli_path, "cliVersion": cli_version,
        }

    billing = oauth.get("billingType") or ""
    # 로컬에는 세부 플랜(Pro/Max/Team)이 저장되지 않음.
    # 사용자가 대시보드에서 직접 선택한 값이 있으면 우선.
    cfg = _load_dash_config()
    claimed_plan_id = cfg.get("claimedPlan") or ""
    claimed_plan = next((p for p in CLAUDE_PLANS if p["id"] == claimed_plan_id), None)

    if claimed_plan:
        plan_label = claimed_plan["label"]
    elif billing == "stripe_subscription":
        plan_label = "Claude 구독 활성 (세부 플랜 미지정)"
    elif billing == "api_key":
        plan_label = "API 키"
    else:
        plan_label = "무료 / 미확인"

    projects_count = len(data.get("projects", {}) or {})
    return {
        "connected": True,
        "email": oauth.get("emailAddress", ""),
        "displayName": oauth.get("displayName", ""),
        "accountUuid": oauth.get("accountUuid", ""),
        "organizationUuid": oauth.get("organizationUuid", ""),
        "organizationRole": oauth.get("organizationRole", ""),
        "workspaceRole": oauth.get("workspaceRole", ""),
        "billingType": billing,
        "planLabel": plan_label,
        "claimedPlanId": claimed_plan_id,
        "planNote": claimed_plan["note"] if claimed_plan else "플랜은 로컬에 저장되지 않습니다. 직접 선택하세요.",
        "availablePlans": CLAUDE_PLANS,
        "hasExtraUsageEnabled": bool(oauth.get("hasExtraUsageEnabled", False)),
        "subscriptionCreatedAt": oauth.get("subscriptionCreatedAt", ""),
        "accountCreatedAt": oauth.get("accountCreatedAt", ""),
        "userID": data.get("userID", ""),
        "firstTokenDate": data.get("claudeCodeFirstTokenDate", ""),
        "projectsKnown": projects_count,
        "cliInstalled": bool(cli_path),
        "cliPath": cli_path,
        "cliVersion": cli_version,
    }


def api_set_claimed_plan(body: dict) -> dict:
    pid = (body or {}).get("planId") if isinstance(body, dict) else ""
    if pid and not any(p["id"] == pid for p in CLAUDE_PLANS):
        return {"ok": False, "error": f"unknown plan id: {pid}"}
    cfg = _load_dash_config()
    if pid:
        cfg["claimedPlan"] = pid
    else:
        cfg.pop("claimedPlan", None)
    _save_dash_config(cfg)
    return {"ok": True, "planId": pid or ""}


def _scan_repo_local_claude(cwd: str) -> dict:
    """<cwd>/.claude 디렉토리에서 에이전트/커맨드/훅/스킬/settings 전부 스캔."""
    out = {
        "exists": False,
        "claudeMd": None,
        "claudeMdPath": "",
        "agents": [],
        "commands": [],
        "skills": [],
        "hooks": [],
        "settingsLocal": None,
        "settingsLocalPath": "",
    }
    base = Path(cwd) if cwd else None
    if not base or not base.exists():
        return out

    # CLAUDE.md (repo root)
    claude_md = base / "CLAUDE.md"
    if claude_md.exists():
        out["claudeMd"] = _safe_read(claude_md, 20000)
        out["claudeMdPath"] = str(claude_md)

    dot = base / ".claude"
    if not dot.exists() or not dot.is_dir():
        return out
    out["exists"] = True

    # agents
    agents_dir = dot / "agents"
    if agents_dir.exists():
        for p in sorted(agents_dir.glob("*.md")):
            meta = _parse_frontmatter(_safe_read(p, 4000))
            out["agents"].append({
                "id": p.stem,
                "name": meta.get("name", p.stem),
                "description": meta.get("description", ""),
                "model": meta.get("model", "inherit"),
                "tools": _parse_tools_field(meta.get("tools", "")),
                "path": str(p),
            })

    # commands
    cmd_dir = dot / "commands"
    if cmd_dir.exists():
        for p in sorted(cmd_dir.rglob("*.md")):
            meta = _parse_frontmatter(_safe_read(p, 2000))
            rel = p.relative_to(cmd_dir)
            out["commands"].append({
                "id": str(rel).replace("/", ":").replace(".md", ""),
                "name": meta.get("name", p.stem),
                "description": meta.get("description", ""),
                "path": str(p),
            })

    # skills
    skills_dir = dot / "skills"
    if skills_dir.exists():
        for sp in sorted(skills_dir.iterdir()):
            if not sp.is_dir():
                continue
            sm = sp / "SKILL.md"
            meta = _parse_frontmatter(_safe_read(sm)) if sm.exists() else {}
            out["skills"].append({
                "id": sp.name,
                "name": meta.get("name", sp.name),
                "description": meta.get("description", ""),
                "path": str(sp),
            })

    # hooks (dir listing — 자유 형식)
    hooks_dir = dot / "hooks"
    if hooks_dir.exists():
        for p in sorted(hooks_dir.iterdir()):
            if p.is_file():
                out["hooks"].append({"name": p.name, "path": str(p)})

    # settings.local.json
    settings_local = dot / "settings.local.json"
    if settings_local.exists():
        try:
            out["settingsLocal"] = json.loads(_safe_read(settings_local))
        except Exception:
            out["settingsLocal"] = {"_raw": _safe_read(settings_local, 4000)}
        out["settingsLocalPath"] = str(settings_local)

    return out


def api_project_detail(query: dict) -> dict:
    """프로젝트 cwd 기준 스냅샷: 저장소-로컬 .claude + ~/.claude.json 프로젝트 엔트리 + 세션 목록."""
    cwd = (query.get("cwd", [""])[0] or "").strip()
    if not cwd:
        return {"error": "cwd required"}

    # 입력이 슬러그 형태(절대경로/틸드 아님)면 DB의 실제 cwd로 복원
    if not cwd.startswith("/") and not cwd.startswith("~"):
        slug_map = _slug_to_cwd_map()
        resolved = slug_map.get(cwd) or slug_map.get(cwd.replace("/", "-"))
        if not resolved:
            # 메타 디렉토리 jsonl 에서 복원 시도
            meta_dir = PROJECTS_DIR / cwd
            if meta_dir.exists():
                resolved = _resolve_cwd_from_jsonl(meta_dir)
        if not resolved:
            return {"error": f"프로젝트 슬러그 '{cwd}' 의 실제 경로를 찾을 수 없습니다 (세션 재인덱스 필요할 수 있음)"}
        cwd = resolved

    # 안전: 홈 디렉토리 하위만 허용
    expanded = os.path.expanduser(cwd)
    abs_path = os.path.abspath(expanded)
    home = str(Path.home())
    if not (abs_path == home or abs_path.startswith(home + os.sep)):
        return {"error": "path outside home"}

    # 저장소-로컬 설정
    repo = _scan_repo_local_claude(abs_path)

    # ~/.claude.json 내 per-project 엔트리
    project_entry = {}
    if CLAUDE_JSON.exists():
        try:
            data = json.loads(_safe_read(CLAUDE_JSON, 200000))
            projects = data.get("projects") or {}
            entry = projects.get(abs_path) or {}
            # 큰 필드는 잘라서
            project_entry = {
                "allowedTools": entry.get("allowedTools", []),
                "mcpServers": list((entry.get("mcpServers") or {}).keys()),
                "enabledMcpjsonServers": entry.get("enabledMcpjsonServers", []),
                "disabledMcpjsonServers": entry.get("disabledMcpjsonServers", []),
                "hasTrustDialogAccepted": entry.get("hasTrustDialogAccepted"),
                "lastCost": entry.get("lastCost"),
                "lastAPIDuration": entry.get("lastAPIDuration"),
                "lastDuration": entry.get("lastDuration"),
                "lastLinesAdded": entry.get("lastLinesAdded"),
                "lastLinesRemoved": entry.get("lastLinesRemoved"),
                "onboardingSeenCount": entry.get("projectOnboardingSeenCount"),
            }
        except Exception:
            pass

    # 이 cwd 에서 실행된 세션들 (DB)
    _db_init()
    with _db() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT session_id, score, score_breakdown, started_at, duration_ms, message_count, tool_use_count, agent_call_count, error_count, first_user_prompt, model, subagent_types FROM sessions WHERE cwd=? ORDER BY started_at DESC LIMIT 200",
            (abs_path,)
        ).fetchall()]
    for r in rows:
        try: r["score_breakdown"] = json.loads(r.get("score_breakdown") or "{}")
        except Exception: r["score_breakdown"] = {}
        try: r["subagent_types"] = json.loads(r.get("subagent_types") or "{}")
        except Exception: r["subagent_types"] = {}
    avg_score = int(sum(r["score"] or 0 for r in rows) / len(rows)) if rows else 0

    return {
        "cwd": abs_path,
        "name": Path(abs_path).name,
        "repo": repo,
        "claudeJsonEntry": project_entry,
        "sessions": rows,
        "stats": {
            "sessionCount": len(rows),
            "avgScore": avg_score,
            "totalTools": sum(r["tool_use_count"] or 0 for r in rows),
            "totalErrors": sum(r["error_count"] or 0 for r in rows),
            "totalAgents": sum(r["agent_call_count"] or 0 for r in rows),
        },
    }


def _deep_merge_settings(base: dict, patch: dict) -> dict:
    """permissions.allow / permissions.deny 는 set-union, 나머지는 top-level override."""
    out = dict(base or {})
    for k, v in (patch or {}).items():
        if k == "permissions" and isinstance(v, dict) and isinstance(out.get("permissions"), dict):
            merged = dict(out["permissions"])
            for arr_key in ("allow", "deny"):
                if arr_key in v:
                    existing = merged.get(arr_key, []) or []
                    incoming = v.get(arr_key, []) or []
                    seen = set()
                    combined = []
                    for item in list(existing) + list(incoming):
                        if item not in seen:
                            seen.add(item)
                            combined.append(item)
                    merged[arr_key] = combined
            # 병합되지 않은 permissions 하위 키
            for pk, pv in v.items():
                if pk not in ("allow", "deny"):
                    merged[pk] = pv
            out["permissions"] = merged
        else:
            out[k] = v
    return out


SCORE_FORMULA = {
    "engagement": {
        "label": "참여도 (Engagement)", "weight": 25,
        "formula": "min(25, floor(메시지수 / 4))",
        "why": "세션 안에서 충분히 대화를 이어가면 맥락이 누적되어 품질이 오릅니다.",
        "howToIncrease": [
            "플래닝 → 실행 → 리뷰 3-라운드 대화를 한 세션에서 끝내기",
            "CLAUDE.md에 '작업 시작 전 요구사항 확인' 지침 추가",
        ],
    },
    "productivity": {
        "label": "생산성 (Productivity)", "weight": 25,
        "formula": "min(25, floor(도구호출수 × 1.2))",
        "why": "Read/Grep/Edit 같은 도구를 적극 쓸수록 실제 작업이 일어났다는 신호.",
        "howToIncrease": [
            "권한 allow 목록을 늘려 매 도구 호출마다 승인 프롬프트 제거",
            "자주 쓰는 Bash 명령을 allow에 pattern으로 미리 등록",
        ],
    },
    "delegation": {
        "label": "에이전트 위임 (Delegation)", "weight": 15,
        "formula": "min(15, Agent툴_호출수 × 3)",
        "why": "서브에이전트에게 위임하면 메인 컨텍스트를 절약하고 병렬화 가능.",
        "howToIncrease": [
            "탐색 작업은 Explore 에이전트로 위임",
            "프로젝트 전용 에이전트(.claude/agents/*.md) 추가",
            "복잡한 리뷰는 ecc:code-reviewer, ecc:security-reviewer 로 위임",
        ],
    },
    "diversity": {
        "label": "도구 다양성 (Diversity)", "weight": 15,
        "formula": "min(15, 사용된_고유도구수 × 2)",
        "why": "한 도구에만 의존하지 않고 올바른 도구를 골라 쓰는 패턴.",
        "howToIncrease": [
            "MCP 서버 추가해서 사용 가능한 도구 범위 확장",
            "WebFetch/WebSearch 허용해서 최신 정보 참조 가능하게",
        ],
    },
    "reliability": {
        "label": "안정성 (Reliability)", "weight": 20,
        "formula": "max(0, 20 - 오류수 × 4)",
        "why": "도구 오류 없이 깔끔하게 실행될수록 높음. 오류 1회당 -4점.",
        "howToIncrease": [
            "위험한 명령을 deny 목록에 등록 (rm -rf, sudo 등)",
            "환경별 의존성을 CLAUDE.md에 명시",
            "빌드/테스트 훅을 PostToolUse에 연결해 조기 실패 감지",
        ],
    },
}


def _project_avg_breakdown(rows: list) -> dict:
    """세션 행 리스트 → 평균 5축 점수."""
    if not rows:
        return {k: 0 for k in SCORE_FORMULA}
    sums = {k: 0 for k in SCORE_FORMULA}
    cnt = 0
    for r in rows:
        try:
            b = json.loads(r.get("score_breakdown") or "{}")
        except Exception:
            b = {}
        if not b:
            continue
        cnt += 1
        for k in sums:
            sums[k] += int(b.get(k, 0) or 0)
    if cnt == 0:
        return {k: 0 for k in SCORE_FORMULA}
    return {k: round(sums[k] / cnt, 1) for k in sums}


def _suggest_files_for_project(cwd: str, avg_breakdown: dict, repo: dict, settings: dict) -> list:
    """프로젝트 상태 + 점수 약점을 보고 '이 파일을 이렇게 추가/편집하세요' 추천."""
    recs: list = []
    home = str(Path.home())

    def _safe_rel(rel: str) -> str:
        return rel  # relpath는 별도 검증 경로에서 체크

    # 1) CLAUDE.md 없음
    if not (repo or {}).get("claudeMd"):
        recs.append({
            "id": "create-claude-md",
            "title": "프로젝트 CLAUDE.md 생성",
            "axis": "engagement",
            "impact": "+5~10",
            "reason": "CLAUDE.md 는 세션 시작 시 자동 로드됩니다. 프로젝트 맥락(스택·규칙·도메인용어)을 여기 적으면 매 세션 설명 반복이 사라져 참여도·안정성 모두 상승.",
            "relpath": "CLAUDE.md",
            "mode": "create",
            "content": _template_claude_md(cwd),
        })

    # 2) .claude/agents 비어있음
    if not (repo or {}).get("agents"):
        recs.append({
            "id": "create-project-agent",
            "title": "프로젝트 전용 에이전트 추가",
            "axis": "delegation",
            "impact": "+10~15",
            "reason": "프로젝트 도메인에 특화된 에이전트를 `.claude/agents/<name>.md`에 두면 Agent 툴로 위임 가능. 위임(delegation) 축 점수가 직접 오릅니다.",
            "relpath": ".claude/agents/domain-expert.md",
            "mode": "create",
            "content": _template_agent_md(Path(cwd).name),
        })

    # 3) .claude/skills 비어있음
    if not (repo or {}).get("skills"):
        recs.append({
            "id": "create-project-skill",
            "title": "프로젝트 전용 스킬 추가",
            "axis": "diversity",
            "impact": "+4~8",
            "reason": "반복 작업(배포/마이그레이션/PR 만들기 등)을 스킬로 정의하면 Claude가 자동 활용. 다양성 축을 올립니다.",
            "relpath": ".claude/skills/deploy/SKILL.md",
            "mode": "create",
            "content": _template_skill_md(),
        })

    # 4) .claude/settings.local.json 없음 or allow가 너무 빈약
    sl = (repo or {}).get("settingsLocal") or {}
    allow_n = len(((sl or {}).get("permissions") or {}).get("allow", []))
    if allow_n < 6:
        recs.append({
            "id": "project-settings-local",
            "title": "프로젝트 settings.local.json 보강",
            "axis": "productivity",
            "impact": "+6~12",
            "reason": f"현재 프로젝트 로컬 allow 규칙 {allow_n}개. 자주 쓰는 명령을 allow에 두면 도구 호출(productivity) 축이 크게 오릅니다.",
            "relpath": ".claude/settings.local.json",
            "mode": "create" if not sl else "edit",
            "content": _template_settings_local(sl),
        })

    # 5) 전역 settings에 훅 없음
    hooks = settings.get("hooks") if isinstance(settings, dict) else None
    if not hooks:
        recs.append({
            "id": "global-hooks",
            "title": "SessionStart 훅 추가 (~/.claude/settings.json)",
            "axis": "reliability",
            "impact": "+4~8",
            "reason": "SessionStart 훅으로 이전 세션 요약/체크리스트를 자동 주입하면 모든 프로젝트에서 맥락 로딩이 안정화됩니다.",
            "relpath": "~/.claude/settings.json",
            "mode": "edit-global-settings",
            "content": _template_hooks_patch(settings or {}),
        })

    # 6) 도구 다양성 낮으면
    if avg_breakdown.get("diversity", 0) < 8:
        recs.append({
            "id": "add-mcp-connector",
            "title": "MCP 커넥터 추가 제안",
            "axis": "diversity",
            "impact": "+4~10",
            "reason": f"평균 다양성 점수 {avg_breakdown.get('diversity',0)}. MCP 서버(Context7, GitHub, Memory) 중 하나라도 붙이면 도구 풀이 크게 늘어납니다.",
            "relpath": "~/.claude.json",
            "mode": "manual",
            "content": "터미널에서: claude mcp add context7 npx -y @upstash/context7-mcp  (MCP는 대시보드에서 직접 편집하지 않고 CLI로 추가)",
        })

    # 7) 에이전트 위임이 낮으면
    if avg_breakdown.get("delegation", 0) < 3:
        recs.append({
            "id": "claude-md-delegation",
            "title": "위임 프롬프트를 CLAUDE.md에 추가",
            "axis": "delegation",
            "impact": "+3~8",
            "reason": f"평균 위임 점수 {avg_breakdown.get('delegation',0)}. 'Explore/Plan 에이전트 우선 사용' 지침을 CLAUDE.md 에 넣으면 반복 위임이 정착.",
            "relpath": "CLAUDE.md",
            "mode": "append-claude-md",
            "content": (
                "\n## 🤝 에이전트 위임 우선순위\n"
                "- 코드베이스 **탐색**은 Explore 에이전트로 먼저 위임한 뒤 본 작업 시작.\n"
                "- 복잡한 아키텍처 **플랜**은 Plan 에이전트로 결과물을 받아 검토 후 실행.\n"
                "- 3개 이상 파일 리뷰는 ecc:code-reviewer 에 위임.\n"
            ),
        })

    return recs


def _template_claude_md(cwd: str) -> str:
    name = Path(cwd).name
    return f"""# {name}

## 프로젝트 개요
이 프로젝트는 ...(TODO: 한 줄 설명)

## 기술 스택
- 언어/프레임워크: TODO
- 주요 의존성: TODO

## 디렉토리 규칙
- `src/` — 소스 코드
- `tests/` — 테스트
- TODO

## 작업 시 지침
- 커밋 메시지는 한국어 conventional format.
- 새 기능 추가 시 테스트 필수.
- 외부 API 호출은 모킹으로 테스트.

## 자주 쓰는 명령
- 개발: `TODO`
- 테스트: `TODO`
- 빌드: `TODO`

## 🤝 에이전트 위임
- 탐색: Explore 먼저
- 플랜: Plan 사용 후 확정
"""


def _template_agent_md(project_name: str) -> str:
    return f"""---
name: domain-expert
description: {project_name} 프로젝트의 도메인 전문가. 비즈니스 로직/도메인 용어에 익숙하고 새 기능을 설계할 때 리드함.
model: inherit
tools: Read, Grep, Glob, Edit, Write, Bash
---

너는 {project_name} 프로젝트 전담 도메인 전문가다. 다음 원칙을 지킨다:

1. 새 기능 요청이 오면 먼저 기존 코드 컨벤션을 Grep 으로 확인한다.
2. 도메인 용어를 그대로 사용하고 일반화하지 않는다.
3. 큰 변경 전에는 변경 계획을 한국어로 3~5줄로 요약해 보여준다.
4. 테스트 없이 기능만 추가하지 않는다.

### 출력 형식
- **변경 계획:** 3~5줄
- **영향 범위:** 파일 경로 리스트
- **테스트:** 어떤 케이스를 추가할지
"""


def _template_skill_md() -> str:
    return """---
name: deploy
description: 프로젝트를 프로덕션에 배포하는 표준 플로우 (빌드 → 테스트 → 릴리스). Use when the user asks to deploy, ship, or release this project.
---

# Deploy Skill

## 트리거
- 사용자가 "deploy", "ship", "release", "prod에 올리기" 등을 요청할 때.

## 체크리스트
1. `git status` — 클린 상태 확인
2. `<빌드 명령>` 실행
3. `<테스트 명령>` 실행 (전체 pass 필수)
4. 버전 태그 (semver) 추가
5. 배포 스크립트 실행

## 실패 처리
- 테스트 실패 → 멈추고 원인 보고
- 빌드 실패 → 마지막 커밋 차이 분석

(TODO: 프로젝트 실 명령으로 교체)
"""


def _template_settings_local(existing: dict) -> str:
    base = {
        "permissions": {
            "allow": [
                "Bash(git status:*)",
                "Bash(git diff:*)",
                "Bash(git log:*)",
                "Bash(npm run:*)",
                "Bash(pnpm run:*)",
                "Bash(pytest:*)",
                "Bash(python3:*)",
                "Read",
                "Grep",
                "Glob",
            ],
            "deny": [
                "Bash(rm -rf:*)",
                "Bash(sudo:*)",
                "Edit(.env*)",
                "Edit(secrets/**)",
            ],
        },
    }
    if isinstance(existing, dict) and existing:
        # 기존 것을 기반으로 병합 힌트 제공
        cur = existing.get("permissions") or {}
        seen = set()
        new_allow = list(cur.get("allow", []) or []) + base["permissions"]["allow"]
        dedup = []
        for x in new_allow:
            if x not in seen:
                seen.add(x); dedup.append(x)
        base["permissions"]["allow"] = dedup
        seen = set()
        new_deny = list(cur.get("deny", []) or []) + base["permissions"]["deny"]
        dedup = []
        for x in new_deny:
            if x not in seen:
                seen.add(x); dedup.append(x)
        base["permissions"]["deny"] = dedup
    return json.dumps(base, indent=2, ensure_ascii=False)


def _template_hooks_patch(existing_settings: dict) -> str:
    merged = dict(existing_settings or {})
    hooks = dict(merged.get("hooks", {}) or {})
    # SessionStart 훅 예시
    ss = hooks.get("SessionStart", [])
    if not isinstance(ss, list):
        ss = []
    ss.append({
        "matcher": "startup",
        "hooks": [{
            "type": "command",
            "command": "echo '📋 이전 세션 요약은 $HOME/.claude/session-data/ 참조'",
            "timeout": 3000,
        }]
    })
    hooks["SessionStart"] = ss
    merged["hooks"] = hooks
    return json.dumps(merged, indent=2, ensure_ascii=False)


def api_project_score_detail(query: dict) -> dict:
    cwd = (query.get("cwd", [""])[0] or "").strip()
    project_dir = (query.get("projectDir", [""])[0] or "").strip()
    if not cwd and not project_dir:
        return {"error": "cwd or projectDir required"}

    _db_init()
    with _db() as c:
        if cwd:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM sessions WHERE cwd=? ORDER BY started_at DESC",
                (cwd,)
            ).fetchall()]
        else:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM sessions WHERE project_dir=? ORDER BY started_at DESC",
                (project_dir,)
            ).fetchall()]
    if not rows and not cwd:
        # project_dir 슬러그에서 cwd 복원 시도 (첫 행의 cwd)
        cwd = ""

    # cwd 가 row에서 추출 가능하면 사용
    cwd_resolved = cwd or (rows[0].get("cwd") if rows and rows[0].get("cwd") else "")

    avg_breakdown = _project_avg_breakdown(rows)
    total_avg = round(sum(avg_breakdown.values()), 1)

    # sessions 요약 (상위/하위)
    rows_sorted = sorted(rows, key=lambda r: r.get("score") or 0, reverse=True)
    best = rows_sorted[:3]
    worst = rows_sorted[-3:][::-1] if len(rows_sorted) > 3 else []
    for r in best + worst:
        try: r["score_breakdown"] = json.loads(r.get("score_breakdown") or "{}")
        except Exception: r["score_breakdown"] = {}

    # 프로젝트-로컬 상태
    repo = _scan_repo_local_claude(cwd_resolved) if cwd_resolved else {}
    settings = get_settings()
    recs = _suggest_files_for_project(cwd_resolved, avg_breakdown, repo, settings) if cwd_resolved else []

    return {
        "cwd": cwd_resolved,
        "projectDir": project_dir,
        "sessionCount": len(rows),
        "totalAvg": total_avg,
        "avgBreakdown": avg_breakdown,
        "formula": SCORE_FORMULA,
        "best": best,
        "worst": worst,
        "recommendations": recs,
        "repoHas": {
            "claudeMd": bool(repo.get("claudeMd")) if repo else False,
            "agents": len((repo or {}).get("agents", [])),
            "skills": len((repo or {}).get("skills", [])),
            "commands": len((repo or {}).get("commands", [])),
            "settingsLocal": bool((repo or {}).get("settingsLocal")),
            "hooks": len((repo or {}).get("hooks", [])),
        },
    }


def api_project_tool_breakdown(query: dict) -> dict:
    """프로젝트 cwd 의 도구 사용 내역 드릴다운."""
    cwd = (query.get("cwd", [""])[0] or "").strip()
    if not cwd:
        return {"error": "cwd required"}
    if not cwd.startswith("/"):
        mapping = _slug_to_cwd_map()
        cwd = mapping.get(cwd, cwd)

    _db_init()
    with _db() as c:
        sess_rows = c.execute(
            "SELECT session_id, score FROM sessions WHERE cwd=?", (cwd,)
        ).fetchall()
        if not sess_rows:
            return {"cwd": cwd, "tools": [], "subagents": [], "total": 0, "sessionCount": 0}
        session_ids = [r["session_id"] for r in sess_rows]
        placeholders = ",".join("?" * len(session_ids))
        tools = [dict(r) for r in c.execute(
            f"""SELECT tool,
                       COUNT(*) AS n,
                       SUM(CASE WHEN had_error=1 THEN 1 ELSE 0 END) AS errors,
                       SUM(CASE WHEN subagent_type != '' THEN 1 ELSE 0 END) AS via_agents
                FROM tool_uses WHERE session_id IN ({placeholders})
                GROUP BY tool ORDER BY n DESC""",
            session_ids,
        ).fetchall()]
        subagents = [dict(r) for r in c.execute(
            f"""SELECT subagent_type AS name, COUNT(*) AS n
                FROM tool_uses
                WHERE session_id IN ({placeholders}) AND subagent_type != ''
                GROUP BY subagent_type ORDER BY n DESC""",
            session_ids,
        ).fetchall()]
    total = sum(t["n"] for t in tools)
    return {
        "cwd": cwd,
        "sessionCount": len(session_ids),
        "total": total,
        "tools": tools,
        "subagents": subagents,
    }


def _safe_join_under(base: Path, relpath: str) -> Optional[Path]:
    """relpath 가 base 하위 경로인지 검증하고 실제 경로 반환. 바깥으로 나가면 None."""
    if not relpath or ".." in Path(relpath).parts or Path(relpath).is_absolute():
        return None
    candidate = (base / relpath).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    return candidate


def _format_sample_prompts(prompts: list) -> str:
    if not prompts:
        return "- (샘플 없음)"
    out = []
    for p in prompts[:5]:
        one_line = p.replace("\n", " ").strip()[:220]
        out.append("- " + one_line)
    return "\n".join(out)


def _format_existing_md_block(md: str) -> str:
    if not md:
        return ""
    return "## 현재 CLAUDE.md 내용 (앞 1800자)\n" + md


AGENT_ROLE_CATALOG = [
    {
        "id": "backend-dev", "icon": "🖥️", "label": "백엔드 개발자",
        "summary": "REST/GraphQL API, DB 스키마, 비즈니스 로직 구현을 주도.",
        "defaultName": "backend-dev",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 이 프로젝트의 **백엔드 개발자**다. 다음 원칙을 지킨다:\n\n"
            "1. 새 API 추가 시 기존 레이어링(router/use-case/repository) 패턴을 Grep 으로 확인 후 일치시킨다.\n"
            "2. DB 변경은 반드시 마이그레이션 파일을 함께 만든다.\n"
            "3. 비즈니스 로직은 use-case 레이어에 두고 router 는 얇게 유지.\n"
            "4. 외부 API 호출은 반드시 timeout/retry 정책 포함.\n"
            "5. 변경 후 관련 테스트를 실행·통과시킨다.\n\n"
            "### 출력 형식\n- 변경 계획 3-5줄\n- 영향 파일 리스트\n- 추가된/변경된 테스트 케이스\n"
        ),
    },
    {
        "id": "frontend-dev", "icon": "🎨", "label": "프론트엔드 개발자",
        "summary": "React/Next.js/Vue 컴포넌트와 상태 관리, 접근성·성능 고려.",
        "defaultName": "frontend-dev",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 이 프로젝트의 **프론트엔드 개발자**다.\n\n"
            "1. 컴포넌트 생성 전 기존 디자인 토큰/컴포넌트 라이브러리를 Grep 으로 확인.\n"
            "2. 접근성(aria-*, 키보드) 기본. 시각 요소에만 의존 금지.\n"
            "3. 상태 관리는 기존 패턴(zustand/redux/context) 따르기.\n"
            "4. 성능: 큰 리스트는 가상화, 이미지 lazy-loading, 불필요 re-render 제거.\n"
            "5. 스토리북/테스트를 함께 업데이트.\n"
        ),
    },
    {
        "id": "fullstack-dev", "icon": "🧩", "label": "풀스택 개발자",
        "summary": "프론트·백엔드 모두 다루는 얇은 수직 슬라이스 구현.",
        "defaultName": "fullstack-dev",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 풀스택 개발자다. 기능 요청이 오면:\n"
            "1. DB 스키마 → 백엔드 엔드포인트 → 프론트 UI → 테스트 순으로 얇게 먼저 완성.\n"
            "2. 레이어 사이 계약(타입/스키마)을 먼저 정의하고 양쪽에서 참조.\n"
            "3. 완전 구현 전 mock 으로 통합 흐름 확인.\n"
        ),
    },
    {
        "id": "ml-engineer", "icon": "🧠", "label": "머신러닝 엔지니어",
        "summary": "모델 학습·평가·배포 파이프라인, 데이터셋 처리, 지표 추적.",
        "defaultName": "ml-engineer",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 머신러닝 엔지니어다.\n\n"
            "1. 새 모델은 baseline 부터 시작: 기존 평가 지표로 먼저 측정.\n"
            "2. 학습 스크립트는 시드 고정 + config 파일화.\n"
            "3. 데이터셋 변경 시 버전 태그/해시 기록.\n"
            "4. 추론 코드에는 배치 크기·디바이스·dtype 명시.\n"
            "5. 실험 결과는 표 형식으로 보고 (base vs new).\n"
        ),
    },
    {
        "id": "data-scientist", "icon": "📊", "label": "데이터 사이언티스트",
        "summary": "EDA, 가설 검증, 비즈니스 지표 분석, 대시보드 작성.",
        "defaultName": "data-scientist",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 데이터 사이언티스트다. 분석 요청 시:\n"
            "1. 먼저 데이터 shape/결측/이상치 요약.\n"
            "2. 가설 → 검정 방법 → 결과 → 해석 순으로 정리.\n"
            "3. 시각화는 핵심 지표 최대 3개까지.\n"
            "4. SQL 쿼리는 재현 가능하도록 완전 형태로 기록.\n"
        ),
    },
    {
        "id": "devops-sre", "icon": "⚙️", "label": "DevOps / SRE",
        "summary": "CI/CD, 인프라 자동화, 모니터링, 온콜 런북.",
        "defaultName": "devops-sre",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 DevOps/SRE 역할이다.\n\n"
            "1. 인프라 변경은 IaC(terraform/pulumi)로만, 콘솔 직접 변경 금지.\n"
            "2. 새 서비스는 health check + metrics endpoint 필수.\n"
            "3. 배포 파이프라인은 롤백 경로를 먼저 확인.\n"
            "4. 경보는 심각도 기준/런북 링크와 함께 정의.\n"
        ),
    },
    {
        "id": "security-reviewer", "icon": "🔒", "label": "보안 리뷰어",
        "summary": "OWASP 관점 코드 리뷰, 비밀 누출, 인증·인가, 의존성 취약점.",
        "defaultName": "security-reviewer",
        "tools": ["Read", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 보안 리뷰 전담이다. 변경 사항에서 다음을 점검:\n\n"
            "- 인증/인가 우회 가능성\n- SQL/Command Injection\n- SSRF / 경로 탈출\n"
            "- 하드코딩된 secrets\n- 안전하지 않은 crypto 사용\n- 신뢰 경계에서의 입력 검증 누락\n\n"
            "심각도(Critical/High/Medium/Low) 표시 후 PoC/재현 경로 포함해 보고.\n"
        ),
    },
    {
        "id": "qa-engineer", "icon": "🧪", "label": "QA 엔지니어",
        "summary": "테스트 설계, E2E 자동화, 회귀 방지, 품질 게이트.",
        "defaultName": "qa-engineer",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 QA 엔지니어다. 새 기능이 들어오면:\n"
            "1. 해피 패스 + 엣지 케이스 + 에러 경로 3종 테스트.\n"
            "2. Given-When-Then 주석으로 의도 명시.\n"
            "3. 외부 I/O 는 mock, 순수 로직은 단위 테스트.\n"
            "4. flaky 테스트는 격리 후 근본 원인 리포트.\n"
        ),
    },
    {
        "id": "architect", "icon": "🏛️", "label": "아키텍트",
        "summary": "상위 설계, 모듈 경계, 트레이드오프 분석, ADR 작성.",
        "defaultName": "architect",
        "tools": ["Read", "Grep", "Glob"],
        "model": "inherit",
        "content": (
            "너는 시스템 아키텍트다. 새 기능/리팩터링 제안이 오면:\n"
            "1. 기존 모듈 경계·의존 방향을 먼저 Grep 으로 파악.\n"
            "2. 2-3개 대안 비교: 장/단점/유지비용.\n"
            "3. 선택 근거와 함께 ADR 형식으로 요약.\n"
            "4. 변경이 큰 경우 단계별 마이그레이션 경로 제시.\n"
        ),
    },
    {
        "id": "code-reviewer", "icon": "🔍", "label": "코드 리뷰어",
        "summary": "변경된 코드의 정확성·가독성·유지보수성 점검.",
        "defaultName": "code-reviewer",
        "tools": ["Read", "Grep", "Glob"],
        "model": "inherit",
        "content": (
            "너는 코드 리뷰어다.\n\n"
            "체크리스트: 의도 명확성 / 네이밍 / 에러 처리 / 예외 경로 / 테스트 커버리지 / 리팩터 기회 / 문서 업데이트.\n"
            "각 지적은 severity (blocker/suggestion/nit) 명시.\n"
        ),
    },
    {
        "id": "db-expert", "icon": "🗄️", "label": "데이터베이스 전문가",
        "summary": "스키마 설계, 인덱싱, 쿼리 튜닝, 마이그레이션.",
        "defaultName": "db-expert",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 DB 전문가다.\n\n"
            "1. 새 쿼리는 EXPLAIN 으로 plan 확인 후 필요 시 인덱스 추가.\n"
            "2. 마이그레이션은 forward/backward 모두 테스트.\n"
            "3. 대량 변경은 락 시간 추정 후 배치로 분할.\n"
        ),
    },
    {
        "id": "performance", "icon": "⚡", "label": "성능 엔지니어",
        "summary": "프로파일링, 병목 분석, 알고리즘·메모리·IO 최적화.",
        "defaultName": "performance",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 성능 엔지니어다.\n\n"
            "1. 최적화 전에 먼저 벤치마크로 현재 값 측정.\n"
            "2. 병목 후보를 데이터로 증명한 뒤 수정.\n"
            "3. 수정 후 동일 조건 재측정 + 개선율 수치 제시.\n"
        ),
    },
    {
        "id": "mobile-dev", "icon": "📱", "label": "모바일 개발자",
        "summary": "iOS(SwiftUI) / Android(Kotlin) / Flutter 공통 패턴.",
        "defaultName": "mobile-dev",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 모바일 개발자다.\n\n"
            "1. 네트워크 호출은 반드시 상태(idle/loading/error/success) 관리.\n"
            "2. 접근성: VoiceOver/TalkBack 레이블 / Dynamic Type / 컬러 대비.\n"
            "3. 오프라인 대비: 캐시 + 재시도.\n"
        ),
    },
    {
        "id": "tech-writer", "icon": "✍️", "label": "기술 문서 작성자",
        "summary": "API 레퍼런스, 온보딩 가이드, ADR, 릴리즈 노트.",
        "defaultName": "tech-writer",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob"],
        "model": "inherit",
        "content": (
            "너는 기술 문서 작성자다.\n\n"
            "독자 관점에서 '처음 오는 개발자가 30분 안에 돌릴 수 있는가' 를 기준.\n"
            "각 섹션은 예제 코드 + 실패 시 해결 팁 포함.\n"
        ),
    },
    {
        "id": "pm", "icon": "📋", "label": "프로젝트 매니저",
        "summary": "요구사항 분석, 스프린트 플래닝, 이슈 관리, 보고.",
        "defaultName": "pm",
        "tools": ["Read", "Grep", "Glob"],
        "model": "inherit",
        "content": (
            "너는 프로젝트 매니저다.\n\n"
            "새 요구사항이 오면:\n- 목적/성공기준/비기능요건을 먼저 추출\n- 관련 이슈/PR 을 검색해 중복·선행 조건 확인\n- 작업을 1-3일 크기로 쪼개 리스트화\n"
        ),
    },
    {
        "id": "ux-designer", "icon": "🎨", "label": "UX/UI 디자이너",
        "summary": "사용자 플로우, 정보구조, 마이크로인터랙션, 접근성.",
        "defaultName": "ux-designer",
        "tools": ["Read", "Grep", "Glob"],
        "model": "inherit",
        "content": (
            "너는 UX/UI 디자이너 역할이다. 변경이 UI 관련이면:\n"
            "- 3가지 대안 스케치 → 트레이드오프 비교\n- 상태별(empty/loading/error/success) 명시\n- 접근성 체크리스트 통과 여부 확인\n"
        ),
    },
]


def _resolve_cwd_input(cwd: str) -> Optional[str]:
    """cwd 문자열(절대경로 or 슬러그) → 실제 홈 하위 절대경로."""
    if not cwd:
        return None
    if not cwd.startswith("/") and not cwd.startswith("~"):
        cwd = _slug_to_cwd_map().get(cwd, cwd)
    abs_path = os.path.abspath(os.path.expanduser(cwd))
    home = str(Path.home())
    if not (abs_path == home or abs_path.startswith(home + os.sep)):
        return None
    if not Path(abs_path).is_dir():
        return None
    return abs_path


def api_agent_roles() -> dict:
    return {"roles": AGENT_ROLE_CATALOG}


def api_project_agents_list(query: dict) -> dict:
    cwd_in = (query.get("cwd", [""])[0] or "").strip()
    cwd = _resolve_cwd_input(cwd_in)
    if not cwd:
        return {"error": "cwd required"}
    agents_dir = Path(cwd) / ".claude" / "agents"
    if not agents_dir.exists():
        return {"cwd": cwd, "agents": [], "dirExists": False}
    out = []
    for p in sorted(agents_dir.glob("*.md")):
        raw = _safe_read(p)
        meta = _parse_frontmatter(raw)
        out.append({
            "id": p.stem,
            "name": meta.get("name", p.stem),
            "description": meta.get("description", ""),
            "model": meta.get("model", "inherit"),
            "tools": _parse_tools_field(meta.get("tools", "")),
            "path": str(p),
            "raw": raw,
            "content": _strip_frontmatter(raw),
        })
    return {"cwd": cwd, "agents": out, "dirExists": True}


def _build_role_md(role: dict, override_name: Optional[str] = None, override_desc: Optional[str] = None) -> str:
    name = (override_name or role["defaultName"]).strip()
    desc = (override_desc or role.get("summary", "")).strip()
    tools = role.get("tools") or []
    frontmatter = (
        f"---\n"
        f"name: {name}\n"
        f"description: {desc}\n"
        f"model: {role.get('model','inherit')}\n"
        f"tools: {', '.join(tools)}\n"
        f"---\n\n"
    )
    return frontmatter + role["content"]


def api_project_agent_add(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    cwd = _resolve_cwd_input(body.get("cwd", ""))
    if not cwd:
        return {"ok": False, "error": "cwd not resolvable or outside home"}
    role_id = body.get("roleId") or ""
    role = next((r for r in AGENT_ROLE_CATALOG if r["id"] == role_id), None)
    if not role:
        return {"ok": False, "error": f"unknown roleId: {role_id}"}
    name = (body.get("name") or role["defaultName"]).strip()
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", name):
        return {"ok": False, "error": "에이전트 이름은 소문자/숫자/-/_ 만 허용"}
    desc_override = body.get("description")
    target = Path(cwd) / ".claude" / "agents" / f"{name}.md"
    if target.exists() and not body.get("overwrite"):
        return {"ok": False, "error": f"이미 존재: {target.name} (overwrite=true 로 덮어쓰기)"}
    md = _build_role_md(role, override_name=name, override_desc=desc_override)
    ok = _safe_write(target, md)
    return {"ok": ok, "path": str(target), "name": name}


def api_project_agent_delete(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    cwd = _resolve_cwd_input(body.get("cwd", ""))
    if not cwd:
        return {"ok": False, "error": "cwd not resolvable"}
    name = body.get("name") or ""
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        return {"ok": False, "error": "invalid name"}
    target = Path(cwd) / ".claude" / "agents" / f"{name}.md"
    if not target.exists():
        return {"ok": False, "error": "not found"}
    try:
        target.unlink()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


def api_project_agent_save(body: dict) -> dict:
    """raw 통째 저장 (기존 편집)."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    cwd = _resolve_cwd_input(body.get("cwd", ""))
    if not cwd:
        return {"ok": False, "error": "cwd not resolvable"}
    name = body.get("name") or ""
    raw = body.get("raw") or ""
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        return {"ok": False, "error": "invalid name"}
    target = Path(cwd) / ".claude" / "agents" / f"{name}.md"
    ok = _safe_write(target, raw)
    return {"ok": ok, "path": str(target)}


SUBAGENT_MODEL_CHOICES = [
    {"id": "inherit",              "label": "inherit (메인 Claude 따라감)", "note": "세션의 메인 모델과 동일 — 기본값"},
    {"id": "haiku",                "label": "Haiku (가장 빠름/저렴)",       "note": "Haiku 4.5 alias"},
    {"id": "sonnet",               "label": "Sonnet (균형형)",              "note": "Sonnet 4.6 alias"},
    {"id": "opus",                 "label": "Opus (최강/느림)",             "note": "Opus 4.7 alias"},
    {"id": "claude-haiku-4-5",     "label": "claude-haiku-4-5 (핀)",        "note": "특정 버전 고정"},
    {"id": "claude-sonnet-4-6",    "label": "claude-sonnet-4-6 (핀)",       "note": "특정 버전 고정"},
    {"id": "claude-opus-4-7",      "label": "claude-opus-4-7 (핀)",         "note": "1M context"},
    {"id": "claude-opus-4-6",      "label": "claude-opus-4-6 (핀)",         "note": "Fast mode 기본"},
]


def api_subagent_model_choices() -> dict:
    return {"choices": SUBAGENT_MODEL_CHOICES}


def _patch_frontmatter_key(raw: str, key: str, value: str) -> str:
    """markdown frontmatter의 특정 키를 업서트 (---...--- 블록 없으면 생성)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", raw or "", re.DOTALL)
    if not m:
        # 새 frontmatter 추가
        return f"---\n{key}: {value}\n---\n\n{raw}"
    block = m.group(1)
    rest = raw[m.end():]
    lines = block.splitlines()
    replaced = False
    new_lines = []
    for line in lines:
        if re.match(rf"^\s*{re.escape(key)}\s*:", line):
            new_lines.append(f"{key}: {value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"{key}: {value}")
    return f"---\n" + "\n".join(new_lines) + f"\n---\n" + rest


def api_subagent_set_model(body: dict) -> dict:
    """
    서브에이전트 파일의 frontmatter `model` 값만 패치.
    body: { scope: 'project'|'global'|'plugin', agentId: <...>, cwd?: <path for project>, model: <value> }
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    scope = body.get("scope") or "project"
    agent_id = body.get("agentId") or ""
    model = body.get("model") or "inherit"
    if not isinstance(model, str) or len(model) > 80 or not re.match(r"^[a-zA-Z0-9_.-]+$", model):
        return {"ok": False, "error": "invalid model id"}

    if scope == "project":
        cwd = _resolve_cwd_input(body.get("cwd", ""))
        if not cwd:
            return {"ok": False, "error": "cwd required for project scope"}
        if not re.match(r"^[a-zA-Z0-9_-]+$", agent_id):
            return {"ok": False, "error": "invalid agent name"}
        target = Path(cwd) / ".claude" / "agents" / f"{agent_id}.md"
    elif scope == "global":
        if not re.match(r"^[a-zA-Z0-9_-]+$", agent_id):
            return {"ok": False, "error": "invalid agent name"}
        target = AGENTS_DIR / f"{agent_id}.md"
    elif scope == "plugin":
        p = _resolve_agent_path(agent_id)
        if not p:
            return {"ok": False, "error": "plugin agent path not resolvable"}
        target = p
    else:
        return {"ok": False, "error": "unknown scope"}

    if not target.exists():
        return {"ok": False, "error": f"not found: {target.name}"}

    raw = _safe_read(target)
    patched = _patch_frontmatter_key(raw, "model", model)
    ok = _safe_write(target, patched)
    return {"ok": ok, "model": model, "path": str(target)}


def api_project_ai_recommend(body: dict) -> dict:
    """실제 claude CLI 를 subprocess 로 호출해 이 프로젝트 맞춤 추천을 JSON 으로 받음.
    cwd=프로젝트루트로 실행해서 Claude 가 실제 파일들을 읽을 수 있게 함.
    """
    cwd = (body.get("cwd") or "").strip() if isinstance(body, dict) else ""
    if not cwd:
        return {"error": "cwd required"}
    # slug 들어오면 해석
    if not cwd.startswith("/"):
        cwd = _slug_to_cwd_map().get(cwd, cwd)
    if not Path(cwd).exists():
        return {"error": f"경로가 존재하지 않습니다: {cwd}"}

    claude_bin = shutil.which("claude")
    if not claude_bin:
        return {"error": "claude CLI가 설치되어 있지 않습니다. `brew install claude` 또는 https://docs.claude.com/en/docs/claude-code 참고"}

    auth = api_auth_status()
    if not auth.get("connected"):
        return {"error": "Claude 계정 연결이 필요합니다: " + (auth.get("reason") or "unknown")}

    # 컨텍스트 수집
    detail = api_project_score_detail({"cwd": [cwd]})
    if detail.get("error"):
        return detail
    repo = _scan_repo_local_claude(cwd)

    _db_init()
    sample_prompts: list[str] = []
    with _db() as c:
        rows = c.execute(
            """SELECT first_user_prompt FROM sessions
               WHERE cwd=? AND first_user_prompt IS NOT NULL AND first_user_prompt != ''
               ORDER BY score DESC LIMIT 6""",
            (cwd,),
        ).fetchall()
        for r in rows:
            p = (r["first_user_prompt"] or "").strip()
            if p:
                sample_prompts.append(p[:280])

    bd = detail["avgBreakdown"]
    existing_md = (repo.get("claudeMd") or "")[:1800]

    prompt = f"""당신은 Claude Code 최적화 컨설턴트입니다. 아래 프로젝트 상태를 읽고, 점수를 올릴 수 있는 Claude 설정 파일 개선안을 JSON 으로만 답하세요.

## 프로젝트
- 이름: {Path(cwd).name}
- 경로: {cwd}
- 인덱스 세션: {detail['sessionCount']}개
- 평균 점수: {detail['totalAvg']}/100

## 5축 평균 (만점 대비 비율이 낮은 축을 우선 개선)
- engagement: {bd.get('engagement',0)}/25 — 세션당 메시지 수
- productivity: {bd.get('productivity',0)}/25 — 도구 호출 수 (권한 자동승인 필요)
- delegation: {bd.get('delegation',0)}/15 — 서브에이전트 위임 수
- diversity: {bd.get('diversity',0)}/15 — 고유 도구 종류
- reliability: {bd.get('reliability',0)}/20 — 20 - 오류수×4

## 현재 파일 상태
- CLAUDE.md: {'있음 (' + str(len(repo.get('claudeMd') or '')) + '자)' if repo.get('claudeMd') else '없음'}
- .claude/agents: {len(repo.get('agents',[]))}개
- .claude/skills: {len(repo.get('skills',[]))}개
- .claude/commands: {len(repo.get('commands',[]))}개
- .claude/settings.local.json: {'있음' if repo.get('settingsLocal') else '없음'}

{_format_existing_md_block(existing_md)}

## 이 프로젝트에서 자주 들어온 사용자 요청들 (톤/도메인 파악용)
{_format_sample_prompts(sample_prompts)}

## 요구
이 프로젝트의 도메인·요청 스타일에 딱 맞는 **구체적** 개선안을 3~6개 제안하세요. 각 항목은:
- 이 프로젝트 맥락에서 왜 필요한지 설명 (일반론 금지)
- 파일 내용은 **즉시 저장 가능한 완전한 전체 내용** (TODO 최소화, 실제 도메인 용어 사용)
- 낮은 축을 올리는 추천을 우선

## 출력 형식 (JSON 만, 다른 텍스트 금지)
{{
  "recommendations": [
    {{
      "title": "한 줄 제목",
      "axis": "engagement|productivity|delegation|diversity|reliability",
      "impact": "+5~10",
      "reason": "이 프로젝트 맥락에서 왜 필요한지 2~3문장",
      "relpath": "CLAUDE.md 또는 .claude/agents/<name>.md 또는 .claude/skills/<name>/SKILL.md 또는 .claude/settings.local.json",
      "mode": "create|edit|append-claude-md",
      "content": "파일에 저장될 완전한 전체 내용"
    }}
  ]
}}
"""

    try:
        proc = subprocess.run(
            [claude_bin, "-p", prompt, "--output-format", "json"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=240,
        )
    except subprocess.TimeoutExpired:
        return {"error": "Claude CLI 시간 초과 (240초) — 다시 시도해 주세요."}
    except Exception as e:
        return {"error": f"Claude CLI 실행 실패: {e}"}

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()[:600]
        return {"error": f"Claude CLI 비정상 종료 (exit {proc.returncode}): {stderr}"}

    stdout = (proc.stdout or "").strip()
    response_text = stdout
    cost_info = {}
    try:
        meta = json.loads(stdout)
        if isinstance(meta, dict):
            response_text = meta.get("result") or meta.get("content") or stdout
            cost_info = {
                "costUsd": meta.get("total_cost_usd"),
                "durationMs": meta.get("duration_ms"),
                "sessionId": meta.get("session_id"),
                "model": meta.get("model"),
                "numTurns": meta.get("num_turns"),
            }
    except Exception:
        response_text = stdout

    # JSON 블록 추출 (fence 감싸져 있거나 앞뒤 설명 섞여 있어도 처리)
    m = re.search(r"\{[\s\S]*\"recommendations\"[\s\S]*\}", response_text)
    if not m:
        return {
            "error": "Claude 응답에서 recommendations JSON 을 찾지 못했습니다.",
            "rawResponse": response_text[:4000],
            "costInfo": cost_info,
        }
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {
            "error": f"JSON 파싱 실패: {e}",
            "rawResponse": response_text[:4000],
            "costInfo": cost_info,
        }

    recs = parsed.get("recommendations", []) if isinstance(parsed, dict) else []
    for i, r in enumerate(recs):
        if isinstance(r, dict):
            r.setdefault("id", f"ai-{i}")

    return {
        "recommendations": recs,
        "rawResponse": response_text[:4000],
        "costInfo": cost_info,
        "cwd": cwd,
    }


def api_feature_recommend(body: dict) -> dict:
    """훅/권한/출력스타일/상태라인 등 기능별 AI 추천.
    body: { kind: 'hooks'|'permissions'|'output-styles'|'statusline' }
    반환: { current, proposed, rawResponse, costInfo, applyHint }
    """
    if not isinstance(body, dict):
        return {"error": "bad body"}
    kind = body.get("kind") or ""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return {"error": "claude CLI 설치 필요"}
    if not api_auth_status().get("connected"):
        return {"error": "Claude 계정 연결 필요"}

    s = get_settings()
    auth = api_auth_status()

    # 프로젝트 상황 컨텍스트
    _db_init()
    with _db() as c:
        proj_rows = c.execute(
            """SELECT cwd, COUNT(*) AS n, AVG(score) AS avg_s
               FROM sessions WHERE cwd != '' GROUP BY cwd ORDER BY n DESC LIMIT 6"""
        ).fetchall()
        top_tools = [dict(r) for r in c.execute(
            "SELECT tool, COUNT(*) AS n FROM tool_uses GROUP BY tool ORDER BY n DESC LIMIT 10"
        ).fetchall()]
    projects = [{"name": Path(r["cwd"]).name, "cwd": r["cwd"], "sessions": r["n"], "avg": int(r["avg_s"] or 0)} for r in proj_rows]

    current_obj = None
    system_intro = ""
    output_shape = ""
    apply_hint = ""

    if kind == "hooks":
        current_obj = s.get("hooks") or {}
        system_intro = "사용자의 Claude Code 를 위한 ~/.claude/settings.json 'hooks' 섹션을 만드세요."
        output_shape = '{"hooks": {"SessionStart": [...], "PreToolUse": [...], ...}}'
        apply_hint = "settings.json.hooks 에 병합"
    elif kind == "permissions":
        current_obj = s.get("permissions") or {"allow": [], "deny": []}
        system_intro = "사용자의 ~/.claude/settings.json 'permissions' 를 최적화하세요."
        output_shape = '{"permissions": {"allow": [...], "deny": [...]}}'
        apply_hint = "settings.json.permissions 에 병합"
    elif kind == "output-styles":
        current_obj = {"existing": [p.stem for p in OUTPUT_STYLES_DIR.glob("*.md")] if OUTPUT_STYLES_DIR.exists() else []}
        system_intro = "사용자를 위한 새 output style (~/.claude/output-styles/<name>.md) 초안을 작성하세요."
        output_shape = '{"id": "<kebab-name>", "raw": "---\\nname: ...\\n---\\n\\n본문"}'
        apply_hint = "~/.claude/output-styles/<id>.md 로 저장"
    elif kind == "statusline":
        current_obj = {"statusLine": s.get("statusLine"), "keybindings": KEYBINDINGS_JSON.exists()}
        system_intro = "~/.claude/settings.json 의 statusLine 설정을 추천하세요. 쉘 명령으로 current branch, model, cost 표시."
        output_shape = '{"statusLine": {"type": "command", "command": "<shell command>"}}'
        apply_hint = "settings.json.statusLine 덮어쓰기"
    else:
        return {"error": f"unknown kind: {kind}"}

    prompt = f"""{system_intro}

## 사용자 정보
- 이름: {auth.get('displayName', '')}
- 플랜: {auth.get('planLabel', '')}
- 주요 프로젝트: {_format_projects_for_prompt(projects)}
- 상위 도구 호출: {', '.join(t['tool']+'×'+str(t['n']) for t in top_tools[:6])}

## 현재 설정 (JSON)
{json.dumps(current_obj, ensure_ascii=False, indent=2)[:3000]}

## 요구
- 사용자 실제 작업 패턴에 기반한 구체적 추천 (일반론 금지).
- 한국어 주석 최소화, 실제 적용 가능한 JSON/마크다운만 작성.

## 출력 형식
JSON 만: {output_shape}
"""
    try:
        proc = subprocess.run(
            [claude_bin, "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=180,
        )
    except Exception as e:
        return {"error": f"Claude CLI 실행 실패: {e}"}
    if proc.returncode != 0:
        return {"error": f"Claude CLI 오류: {(proc.stderr or '')[:400]}"}

    stdout = (proc.stdout or "").strip()
    response_text = stdout
    cost_info = {}
    try:
        meta = json.loads(stdout)
        if isinstance(meta, dict):
            response_text = meta.get("result") or stdout
            cost_info = {
                "costUsd": meta.get("total_cost_usd"),
                "durationMs": meta.get("duration_ms"),
                "model": meta.get("model"),
            }
    except Exception:
        pass

    # JSON 블록 추출
    m = re.search(r"\{[\s\S]*\}", response_text)
    proposed = None
    if m:
        try:
            proposed = json.loads(m.group(0))
        except Exception:
            proposed = None

    return {
        "kind": kind,
        "current": current_obj,
        "proposed": proposed,
        "rawResponse": response_text[:6000],
        "costInfo": cost_info,
        "applyHint": apply_hint,
    }


def api_global_claude_md_recommend(body: dict) -> dict:
    """사용자의 여러 프로젝트 활동을 종합해 글로벌 ~/.claude/CLAUDE.md 초안 추천.
    body: {}
    """
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return {"error": "claude CLI가 설치되어 있지 않습니다."}
    auth = api_auth_status()
    if not auth.get("connected"):
        return {"error": "Claude 계정 연결이 필요합니다."}

    _db_init()
    with _db() as c:
        proj_rows = c.execute(
            """SELECT cwd, COUNT(*) AS n, AVG(score) AS avg_s
               FROM sessions WHERE cwd != '' GROUP BY cwd ORDER BY n DESC LIMIT 10"""
        ).fetchall()
        tool_rows = c.execute(
            "SELECT tool, COUNT(*) AS n FROM tool_uses GROUP BY tool ORDER BY n DESC LIMIT 12"
        ).fetchall()
        sample_prompts_rows = c.execute(
            "SELECT first_user_prompt FROM sessions WHERE first_user_prompt != '' ORDER BY score DESC LIMIT 6"
        ).fetchall()

    projects = [{"cwd": r["cwd"], "name": Path(r["cwd"]).name, "sessions": r["n"], "avg": round(r["avg_s"] or 0)} for r in proj_rows]
    top_tools = [(r["tool"], r["n"]) for r in tool_rows]
    sample_prompts = [(r["first_user_prompt"] or "")[:240] for r in sample_prompts_rows if r["first_user_prompt"]]

    # 기존 글로벌 CLAUDE.md
    existing = _safe_read(CLAUDE_MD) if CLAUDE_MD.exists() else ""

    prompt = f"""당신은 Claude Code 셋업 컨설턴트입니다. 사용자의 작업 패턴을 보고 ~/.claude/CLAUDE.md (모든 세션에 자동 로드되는 글로벌 지침) 초안을 작성하세요.

## 사용자 정보
- 이름: {auth.get('displayName', '사용자')}
- 플랜: {auth.get('planLabel', '')}

## 주요 프로젝트 (최근 활동순)
{_format_projects_for_prompt(projects)}

## 자주 쓰는 도구 TOP 12
{_format_tools_for_prompt(top_tools)}

## 대표 사용자 요청 샘플 (톤/도메인 파악용)
{_format_sample_prompts(sample_prompts)}

## 기존 글로벌 CLAUDE.md (수정 대상)
{existing if existing else '(없음 — 새로 생성)'}

## 요구
- 이 사용자의 실제 도메인·작업 스타일에 맞춘 구체적 지침을 한국어로 작성.
- 일반론 금지, 관측된 패턴 기반 규칙 포함 (예: "n8n 워크플로 수정 시 mcp__n8n-mcp 우선 사용" 등).
- 섹션: 정체성 · 협업 규칙 · 도구 선호 · 응답 스타일 · 프로젝트별 힌트(프로젝트 1~3개 한 줄씩)
- 길이 300~800자 적당.

## 출력 형식
JSON 만 반환: {{"content": "<CLAUDE.md 전체 내용>"}}
"""
    try:
        proc = subprocess.run(
            [claude_bin, "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=240,
        )
    except subprocess.TimeoutExpired:
        return {"error": "Claude CLI 시간 초과 (240초)"}
    except Exception as e:
        return {"error": f"Claude CLI 실행 실패: {e}"}

    if proc.returncode != 0:
        return {"error": f"Claude CLI 비정상 종료: {(proc.stderr or '')[:500]}"}

    stdout = (proc.stdout or "").strip()
    response_text = stdout
    cost_info = {}
    try:
        meta = json.loads(stdout)
        if isinstance(meta, dict):
            response_text = meta.get("result") or stdout
            cost_info = {
                "costUsd": meta.get("total_cost_usd"),
                "durationMs": meta.get("duration_ms"),
                "model": meta.get("model"),
            }
    except Exception:
        pass

    # content 추출
    m = re.search(r'\{[\s\S]*?"content"[\s\S]*?\}', response_text)
    content = ""
    if m:
        try:
            parsed = json.loads(m.group(0))
            content = parsed.get("content", "") if isinstance(parsed, dict) else ""
        except json.JSONDecodeError:
            pass
    if not content:
        # fallback: 전체 응답을 그대로 반환
        content = response_text.strip()

    return {"content": content, "existing": existing, "costInfo": cost_info, "rawResponse": response_text[:4000]}


def _format_projects_for_prompt(projects: list) -> str:
    if not projects:
        return "- (데이터 없음)"
    out = []
    for p in projects:
        avg = p.get("avg")
        avg_str = f" · 평균 {avg}점" if avg is not None else ""
        out.append(f"- {p.get('name','')} ({p.get('cwd','')}) · {p.get('sessions',0)}세션{avg_str}")
    return "\n".join(out)


def _format_tools_for_prompt(tools: list) -> str:
    if not tools:
        return "- (없음)"
    return ", ".join(f"{t[0]}×{t[1]}" for t in tools)


def api_project_file_put(body: dict) -> dict:
    """프로젝트 cwd 하위에 파일 생성/편집.
    body: { cwd, relpath, raw }
    - cwd 는 홈 하위여야 함
    - relpath 는 `.claude/…`, `CLAUDE.md`, `~/.claude/settings.json` 중 하나만 허용
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    cwd = body.get("cwd") or ""
    relpath = body.get("relpath") or ""
    raw = body.get("raw")
    if not isinstance(raw, str):
        return {"ok": False, "error": "raw must be string"}
    if not isinstance(cwd, str) or not isinstance(relpath, str):
        return {"ok": False, "error": "cwd/relpath must be strings"}

    home = str(Path.home())

    # 글로벌 settings 특례
    if relpath == "~/.claude/settings.json":
        try:
            parsed = json.loads(raw)
        except Exception as e:
            return {"ok": False, "error": f"JSON parse error: {e}"}
        return put_settings(parsed)

    # 일반: cwd 하위만
    abs_cwd = Path(os.path.abspath(os.path.expanduser(cwd)))
    if not (str(abs_cwd) == home or str(abs_cwd).startswith(home + os.sep)):
        return {"ok": False, "error": "cwd outside home"}
    if not abs_cwd.exists() or not abs_cwd.is_dir():
        return {"ok": False, "error": "cwd not a directory"}

    target = _safe_join_under(abs_cwd, relpath)
    if target is None:
        return {"ok": False, "error": "relpath rejected (traversal or absolute)"}

    # 허용 패턴만 (안전)
    rel_parts = Path(relpath).parts
    allowed = (
        relpath == "CLAUDE.md"
        or (rel_parts and rel_parts[0] == ".claude")
    )
    if not allowed:
        return {"ok": False, "error": "only CLAUDE.md or .claude/** allowed"}

    ok = _safe_write(target, raw)
    return {"ok": ok, "path": str(target)}


def api_settings_preview(body: dict) -> dict:
    """추천 프로파일(혹은 임의 패치)을 현재 settings와 병합한 preview + diff 반환."""
    patch = body.get("patch") if isinstance(body, dict) else None
    if not isinstance(patch, dict):
        return {"error": "patch (object) required"}

    current = get_settings()
    merged = _deep_merge_settings(current, patch)

    # 간단한 diff: top-level 키 변경 / permissions allow/deny 추가 목록
    added_allow = []
    added_deny = []
    cur_perm = current.get("permissions") or {}
    new_perm = patch.get("permissions") or {}
    for k in ("allow", "deny"):
        cur_set = set(cur_perm.get(k, []) or [])
        for item in (new_perm.get(k, []) or []):
            if item not in cur_set:
                (added_allow if k == "allow" else added_deny).append(item)

    top_changed = []
    for k in patch.keys():
        if k == "permissions":
            continue
        if current.get(k) != merged.get(k):
            top_changed.append(k)

    return {
        "current": current,
        "patch": patch,
        "merged": merged,
        "diff": {
            "addedAllow": added_allow,
            "addedDeny": added_deny,
            "topChanged": top_changed,
        },
    }


# ───────────────── actions ─────────────────

def _find_terminal_app_for_pid(pid: int) -> str:
    terminal_apps = {"Terminal", "iTerm2", "Alacritty", "kitty", "Warp", "Hyper", "WezTerm"}
    current = pid
    for _ in range(20):
        try:
            line = subprocess.check_output(["ps", "-o", "ppid=,comm=", "-p", str(current)], text=True, timeout=3).strip()
        except Exception:
            break
        parts = line.split(None, 1)
        if len(parts) < 2:
            break
        ppid_str, comm = parts
        app_name = Path(comm).name
        if app_name in terminal_apps:
            return app_name
        try:
            current = int(ppid_str)
        except ValueError:
            break
        if current <= 1:
            break
    return ""


def open_session_action(body: dict) -> dict:
    session_id = body.get("sessionId") if isinstance(body, dict) else None
    if not session_id:
        return {"ok": False, "error": "no sessionId"}
    session_file = SESSIONS_DIR / f"{session_id}.json"
    found = None
    if session_file.exists():
        try:
            found = json.loads(_safe_read(session_file))
        except Exception:
            return {"ok": False, "error": "session unreadable"}
    else:
        if SESSIONS_DIR.exists():
            for p in SESSIONS_DIR.glob("*.json"):
                try:
                    data = json.loads(_safe_read(p))
                    if isinstance(data, dict) and data.get("sessionId") == session_id:
                        found = data
                        break
                except Exception:
                    continue
    if not found:
        return {"ok": False, "error": "session not found"}
    pid = found.get("pid")
    if not pid:
        return {"ok": False, "error": "no pid"}
    try:
        os.kill(pid, 0)
    except OSError:
        return {"ok": False, "error": "process not running"}
    app = _find_terminal_app_for_pid(pid)
    if app:
        try:
            subprocess.run(["osascript", "-e", f'tell application "{app}" to activate'], timeout=3, capture_output=True)
        except Exception:
            pass
    return {"ok": True, "app": app or "unknown", "pid": pid}


def open_folder_action(body: dict) -> dict:
    raw = body.get("folderPath") if isinstance(body, dict) else None
    if not raw:
        return {"ok": False, "error": "no folderPath"}
    expanded = os.path.expanduser(raw)
    abs_path = os.path.abspath(expanded)
    home = str(Path.home())
    if not (abs_path == home or abs_path.startswith(home + os.sep)):
        return {"ok": False, "error": "outside home"}
    if not Path(abs_path).exists():
        return {"ok": False, "error": "not found"}
    try:
        subprocess.Popen(["open", abs_path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": abs_path}


# ───────────────── routes ─────────────────

ROUTES_GET = {
    "/api/claude-md": lambda q: get_claude_md(),
    "/api/system/status": lambda q: get_system_status(),
    "/api/skills": lambda q: list_skills(),
    "/api/agents": lambda q: list_agents(),
    "/api/commands": lambda q: list_commands(),
    "/api/hooks": lambda q: get_hooks(),
    "/api/plugins": lambda q: list_plugins_api(),
    "/api/marketplaces": lambda q: list_marketplaces(),
    "/api/connectors": lambda q: list_connectors(),
    "/api/projects": lambda q: list_projects(),
    "/api/settings": lambda q: get_settings(),
    "/api/guide/recommended-settings": lambda q: get_recommended_settings(),
    "/api/briefing/overview": lambda q: briefing_overview(),
    "/api/briefing/devices": lambda q: briefing_devices(),
    "/api/briefing/activity": lambda q: briefing_activity(),
    "/api/briefing/schedule": lambda q: briefing_schedule(),
    "/api/briefing/projects-summary": lambda q: briefing_projects_summary(),
    "/api/briefing/pending-approvals": lambda q: briefing_pending_approvals(),
    "/api/device/info": lambda q: get_device_info(),
    "/api/sessions/list": api_sessions_list,
    "/api/sessions/stats": lambda q: api_sessions_stats(),
    "/api/agents/graph": api_agent_graph,
    "/api/optimization/score": lambda q: api_optimization_score(),
    "/api/auth/status": lambda q: api_auth_status(),
    "/api/project/detail": api_project_detail,
    "/api/project/score-detail": api_project_score_detail,
    "/api/project/tool-breakdown": api_project_tool_breakdown,
    "/api/mcp/catalog": lambda q: api_mcp_catalog(),
    "/api/plugins/browse": lambda q: api_plugins_browse(),
    "/api/project-agents/roles": lambda q: api_agent_roles(),
    "/api/project-agents/list": api_project_agents_list,
    "/api/subagent/model-choices": lambda q: api_subagent_model_choices(),
    "/api/usage/summary": lambda q: api_usage_summary(),
    "/api/memory/list": api_memory_list,
    "/api/tasks/list": lambda q: api_tasks_list(),
    "/api/team/info": lambda q: api_team_info(),
    "/api/output-styles/list": lambda q: api_output_styles_list(),
    "/api/statusline/info": lambda q: api_statusline_info(),
    "/api/plans/list": lambda q: api_plans_list(),
    "/api/metrics/summary": lambda q: api_metrics_summary(),
    "/api/backups/list": lambda q: api_backups_list(),
    "/api/env/config": lambda q: api_env_config(),
    "/api/model/config": lambda q: api_model_config(),
    "/api/ide/status": lambda q: api_ide_status(),
    "/api/scheduled-tasks/list": lambda q: api_scheduled_tasks(),
    "/api/bash-history/list": api_bash_history,
    "/api/telemetry/summary": lambda q: api_telemetry_summary(),
    "/api/homunculus/projects": lambda q: api_homunculus_projects(),
    "/api/marketplaces/list": lambda q: api_marketplace_list(),
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "application/javascript",
    ".mjs": "application/javascript", ".css": "text/css",
    ".json": "application/json", ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2",
    ".map": "application/json",
}


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, path: str) -> None:
        if path in ("/", ""):
            path = "/index.html"
        rel = path.lstrip("/")
        fp = (DIST / rel).resolve()
        if not str(fp).startswith(str(DIST.resolve())):
            self.send_response(403); self.end_headers(); return
        if not fp.exists() or not fp.is_file():
            fp = DIST / "index.html"
        try:
            data = fp.read_bytes()
        except Exception:
            self.send_response(500); self.end_headers(); return
        ct = CONTENT_TYPES.get(fp.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except Exception:
            return {}

    def _drain(self) -> None:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length:
            self.rfile.read(length)

    def do_GET(self) -> None:
        u = urlparse(self.path)
        path = unquote(u.path)
        query = parse_qs(u.query)
        # exact-path routes take precedence over regex item-routes
        if path in ROUTES_GET:
            try:
                self._send_json(ROUTES_GET[path](query))
            except Exception as e:
                import traceback; traceback.print_exc()
                self._send_json({"error": str(e)}, 500)
            return
        m = re.match(r"^/api/sessions/detail/([0-9a-f-]+)$", path)
        if m:
            try:
                self._send_json(api_session_detail(m.group(1)))
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return
        m = re.match(r"^/api/skills/([^/]+)$", path)
        if m:
            try:
                self._send_json(get_skill(m.group(1)))
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return
        m = re.match(r"^/api/agents/([A-Za-z0-9_.:-]+)$", path)
        if m:
            try:
                self._send_json(get_agent(m.group(1)))
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return
        if path.startswith("/api/"):
            self._send_json({})
            return
        self._send_static(path)

    def do_PUT(self) -> None:
        path = unquote(urlparse(self.path).path)
        body = self._read_body()
        if path == "/api/claude-md":
            self._send_json(put_claude_md(body)); return
        if path == "/api/settings":
            self._send_json(put_settings(body)); return
        m = re.match(r"^/api/skills/([^/]+)$", path)
        if m:
            self._send_json(put_skill(m.group(1), body)); return
        m = re.match(r"^/api/agents/([A-Za-z0-9_.:-]+)$", path)
        if m:
            self._send_json(put_agent(m.group(1), body)); return
        if path == "/api/project-agents/save":
            self._send_json(api_project_agent_save(body)); return
        self._send_json({"ok": False, "error": "unknown route"}, 404)

    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path == "/api/open-folder":
            self._send_json(open_folder_action(self._read_body())); return
        if path == "/api/open-session":
            self._send_json(open_session_action(self._read_body())); return
        if path == "/api/sessions/reindex":
            body = self._read_body()
            force = bool(body.get("force", False))
            self._send_json(index_all_sessions(force=force)); return
        if path == "/api/settings/preview":
            self._send_json(api_settings_preview(self._read_body())); return
        if path == "/api/project/file":
            self._send_json(api_project_file_put(self._read_body())); return
        if path == "/api/project/ai-recommend":
            self._send_json(api_project_ai_recommend(self._read_body())); return
        if path == "/api/global/claude-md-recommend":
            self._send_json(api_global_claude_md_recommend(self._read_body())); return
        if path == "/api/feature/recommend":
            self._send_json(api_feature_recommend(self._read_body())); return
        if path == "/api/commands/translate":
            self._send_json(api_commands_translate(self._read_body())); return
        if path == "/api/translate/batch":
            self._send_json(api_translate_batch(self._read_body())); return
        if path == "/api/mcp/install":
            self._send_json(api_mcp_install(self._read_body())); return
        if path == "/api/mcp/remove":
            self._send_json(api_mcp_remove(self._read_body())); return
        if path == "/api/plugins/toggle":
            self._send_json(api_plugin_toggle(self._read_body())); return
        if path == "/api/auth/claimed-plan":
            self._send_json(api_set_claimed_plan(self._read_body())); return
        if path == "/api/project-agents/add":
            self._send_json(api_project_agent_add(self._read_body())); return
        if path == "/api/project-agents/delete":
            self._send_json(api_project_agent_delete(self._read_body())); return
        if path == "/api/project-agents/save":
            self._send_json(api_project_agent_save(self._read_body())); return
        if path == "/api/subagent/set-model":
            self._send_json(api_subagent_set_model(self._read_body())); return
        if path == "/api/agents/create":
            self._send_json(api_agent_create(self._read_body())); return
        if path == "/api/agents/delete":
            self._send_json(api_agent_delete(self._read_body())); return
        if path == "/api/tasks/save":
            self._send_json(api_task_save(self._read_body())); return
        if path == "/api/tasks/delete":
            self._send_json(api_task_delete(self._read_body())); return
        if path == "/api/output-styles/save":
            self._send_json(api_output_style_save(self._read_body())); return
        if path == "/api/output-styles/delete":
            self._send_json(api_output_style_delete(self._read_body())); return
        if path == "/api/marketplaces/add":
            self._send_json(api_marketplace_add(self._read_body())); return
        if path == "/api/marketplaces/remove":
            self._send_json(api_marketplace_remove(self._read_body())); return
        self._drain()
        self._send_json({"ok": False, "error": "unknown route"}, 404)

    def do_DELETE(self) -> None:
        self._drain()
        self._send_json({"ok": False, "readOnly": True})

    def log_message(self, fmt, *args) -> None:
        print(f"[server] {self.command} {self.path}")


def _background_index() -> None:
    try:
        r = index_all_sessions(force=False)
        print(f"[server] initial index: {r}")
    except Exception as e:
        print(f"[server] index failed: {e}")


def main() -> None:
    _db_init()
    _background_index()
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "127.0.0.1")
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving http://{host}:{port} (dist={DIST}, db={DB_PATH})")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
