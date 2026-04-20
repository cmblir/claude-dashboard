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

# 신규 패키지 — 점진적 리팩터링 중. 경로·유틸·로거는 server/ 패키지에서 공급.
from server.config import (
    ROOT, DIST,
    CLAUDE_HOME, CLAUDE_MD, SETTINGS_JSON, SKILLS_DIR, AGENTS_DIR, COMMANDS_DIR,
    PROJECTS_DIR, PLUGINS_DIR, INSTALLED_PLUGINS_JSON, KNOWN_MARKETPLACES_JSON,
    SESSIONS_DIR, SESSION_DATA_DIR, TODOS_DIR, TASKS_DIR, SCHEDULED_TASKS_DIR,
    HISTORY_JSONL, CLAUDE_JSON, CLAUDE_DESKTOP_CONFIG,
    MEMORY_DIR, DB_PATH, TRANSLATIONS_PATH, DASHBOARD_CONFIG_PATH,
    SCORE_MIN_TOOLS, _UUID_RE,
    _load_dotenv, _env_path, _cwd_to_slug, get_bind,
)
from server.utils import (
    _safe_read, _safe_write,
    _parse_frontmatter, _parse_tools_field, _strip_frontmatter,
    _iso_ms, _fmt_rel,
)
from server.logger import setup_logging, log
from server.device import _detect_device_info, _device_label_from_model
from server.db import _db, _db_init


from server.sessions import (
    _first_user_prompt, _extract_model, _compute_score,
    _index_jsonl, index_all_sessions,
    api_sessions_list, api_session_tokens, api_session_timeline,
    api_project_timeline, api_session_detail,
    api_sessions_stats, api_agent_graph,
)


# ───────────────── API: CLAUDE.md / settings ─────────────────

from server.claude_md import (
    parse_sections,
    get_claude_md, put_claude_md,
    get_settings, put_settings,
    validate_permission_rule, validate_permissions, sanitize_permissions,
    _PERM_INVALID_MIDPATTERN,
)


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

from server.skills import (
    _scan_plugin_skills, list_skills,
    _resolve_skill_path, get_skill, put_skill,
)


# ───────────────── API: agents ─────────────────

from server.agents import (
    _BUILTIN_AGENTS,
    _scan_plugin_agents,
    list_agents,
    _resolve_agent_path,
    get_agent, put_agent,
    api_agent_create, api_agent_delete,
)




# ───────────────── API: commands ─────────────────

DASHBOARD_CONFIG = DASHBOARD_CONFIG_PATH

from server.translations import (
    _load_dash_config, _save_dash_config,
    _load_translation_cache, _save_translation_cache,
)




TRANSLATION_CACHE = TRANSLATIONS_PATH  # 구 코드 호환 — 점진적으로 TRANSLATIONS_PATH 로 통일 예정


from server.commands import (
    CMD_CATEGORIES, _categorize_command, list_commands, _cache_key,
)

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


# ───────────────── MCP / plugins / connectors ─────────────────

from server.mcp import (
    MCP_CATALOG, _PLACEHOLDER_RE,
    _extract_placeholders, _substitute_placeholders,
    api_mcp_catalog, api_mcp_install_prepare, api_mcp_install,
    api_mcp_remove, api_mcp_project_remove,
    _scan_project_mcp, list_connectors,
    _MCP_LIST_CACHE, _MCP_LIST_CACHE_FILE, _MCP_LIST_TTL,
    _MCP_LIST_LOCK, _MCP_LIST_REFRESH_LOCK,
    _refresh_mcp_list_blocking, _claude_mcp_list_cached,
    warmup_caches,
)
from server.plugins import (
    api_plugins_browse, api_plugin_toggle,
    list_plugins_api, list_marketplaces,
    api_marketplace_list, api_marketplace_add, api_marketplace_remove,
)
from server.hooks import (
    _plugin_hooks_file, _scan_plugin_hooks,
    api_plugin_hook_update, get_hooks,
)
from server.projects import (
    _slug_to_cwd_map, _resolve_cwd_from_jsonl, _resolve_cwd_input,
    list_projects, _scan_repo_local_claude,
    api_project_detail, api_project_score_detail, api_project_tool_breakdown,
    AGENT_ROLE_CATALOG, SUBAGENT_MODEL_CHOICES,
    api_agent_roles, api_project_agents_list,
    api_project_agent_add, api_project_agent_delete, api_project_agent_save,
    _build_role_md, api_subagent_model_choices,
    _patch_frontmatter_key, api_subagent_set_model,
)




# ───────────────── API: projects ─────────────────

# ───────────────── briefing (original) ─────────────────












# ───────────────── NEW: session DB endpoints ─────────────────

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


def _quality_metrics_30d() -> dict:
    """최근 30일치 사용 패턴 → 품질 가중치 계산용 데이터."""
    _db_init()
    since = int((time.time() - 30 * 86400) * 1000)
    with _db() as c:
        used_subagents = {r["subagent_type"] for r in c.execute(
            "SELECT DISTINCT subagent_type FROM tool_uses WHERE subagent_type != '' AND ts >= ?",
            (since,)
        ).fetchall()}
        agent_calls = c.execute(
            "SELECT COUNT(*) AS n FROM tool_uses WHERE tool='Agent' AND ts >= ?",
            (since,)
        ).fetchone()["n"]
        # 도구 사용 분포 — top 도구가 너무 한쪽으로 쏠리면 다양성 ↓
        tool_diversity = c.execute(
            "SELECT COUNT(DISTINCT tool) AS n FROM tool_uses WHERE ts >= ?", (since,)
        ).fetchone()["n"]
    return {
        "usedSubagents": used_subagents,
        "agentCalls30d": agent_calls,
        "toolDiversity30d": tool_diversity,
    }


def _q_axis(value_max: int, *, count: int, used: int, weight: float, base_q: float = 0.5) -> dict:
    """품질-가중 점수 계산.
      raw    = 단순 카운트 점수 (count × weight)
      Q      = used / count (0~1) — 0개면 base_q
      value  = raw × (base_q + (1-base_q) × Q)   ← Q=0 이면 raw 의 base_q 만, Q=1 이면 raw 그대로
    """
    raw = min(value_max, count * weight)
    if count == 0:
        q = 0.0
    else:
        q = max(0.0, min(1.0, used / count))
    factor = base_q + (1 - base_q) * q
    value = int(round(raw * factor))
    return {"raw": raw, "quality": round(q, 3), "factor": round(factor, 3), "value": min(value_max, value)}


def api_optimization_score() -> dict:
    """전반적 최적화 스코어 — **사용자가 직접 설정한 자원**만 카운트.
    플러그인이 제공하는 자원은 별도 'plugins' 축에서 측정 (이중 가산 ×).
    품질 가중치(Q): 보유한 자원 중 30일 안에 실제로 사용된 비율로 점수 조정.
    """
    _db_init()
    qm = _quality_metrics_30d()
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
    # 30일 내 위임된 user/builtin 에이전트 (subagent_type 매칭)
    # subagent_type 은 보통 frontmatter 의 name (또는 invokeId) — 둘 다 시도
    def _agent_call_keys(a: dict) -> set:
        keys = set()
        if a.get("name"): keys.add(a["name"])
        if a.get("invokeId"): keys.add(a["invokeId"])
        if a.get("id"): keys.add(a["id"])
        return keys
    user_builtin_keys = set()
    for a in agents_data.get("agents", []):
        if a.get("scope") in ("global", "builtin"):
            user_builtin_keys |= _agent_call_keys(a)
    used_user_builtin = len(user_builtin_keys & qm["usedSubagents"])
    # configured_agents 카운트와 일치시키려면 매칭된 distinct names 수만 셈
    used_user_builtin = min(used_user_builtin, configured_agents)
    ag_q = _q_axis(100, count=configured_agents, used=used_user_builtin, weight=10, base_q=0.4)
    score["agents"] = {
        "value": ag_q["value"], "max": 100,
        "rawValue": min(100, ag_q["raw"]), "quality": ag_q["quality"],
        "note": f"사용자 설정 {user_agents_n}개 + 빌트인 {builtin_n}개 = {configured_agents}개 · 30일 활용 {used_user_builtin}개 ({int(ag_q['quality']*100)}%) · 플러그인 제공 {plugin_enabled_n}/{plugin_total} 활성 (별도)",
        "formula": f"raw=min(100, {configured_agents}×10)={ag_q['raw']}, Q={used_user_builtin}/{configured_agents}={ag_q['quality']}, value=raw×(0.4+0.6×Q)={ag_q['value']}",
        "suggest": ("위임을 더 활용해보세요 — 정의된 에이전트가 30일간 적게 호출됨" if ag_q['quality'] < 0.5 and configured_agents > 0
                    else "~/.claude/agents/<name>.md 로 자신만의 서브에이전트 추가."),
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
    # 활성 플러그인이 제공한 에이전트 중 30일 내 위임된 것 수 → 활용도
    plugin_agent_keys = set()
    for a in agents_data.get("agents", []):
        if a.get("scope") == "plugin" and a.get("pluginEnabled"):
            plugin_agent_keys |= _agent_call_keys(a)
    used_plugin_agents = len(plugin_agent_keys & qm["usedSubagents"]) if plugin_agent_keys else 0
    pl_q = _q_axis(100, count=enabled, used=min(enabled, used_plugin_agents), weight=6, base_q=0.5)
    if enabled > 0 and plugin_agent_keys:
        plugin_used_pct = round(used_plugin_agents / max(1, len(plugin_agent_keys)) * 100)
    else:
        plugin_used_pct = None
    score["plugins"] = {
        "value": pl_q["value"], "max": 100,
        "rawValue": min(100, pl_q["raw"]), "quality": pl_q["quality"],
        "note": (f"활성 {enabled} / 설치 {len(plugins)}" +
                 (f" · 그 중 {used_plugin_agents}개 에이전트가 30일 내 위임됨 ({plugin_used_pct}%)"
                  if plugin_used_pct is not None else "")),
        "formula": f"raw=min(100, {enabled}×6)={pl_q['raw']}, Q={pl_q['quality']} (활성 플러그인 사용 비율), value={pl_q['value']}",
        "suggest": "플러그인 1개 활성화 = +6점. 활용 안 하는 플러그인은 비활성화로 노이즈 ↓.",
        "target": "plugins",
    }

    connectors = list_connectors()
    mcp_local_list = connectors.get("local", [])
    mcp_local = len(mcp_local_list)
    mcp_platform = len(connectors.get("platform", []))
    mcp_plugin = len(connectors.get("plugin", []))
    mcp_n = mcp_local + mcp_platform  # 사용자 설정 기준
    # 품질: connected 인 것의 비율 (failed/needsAuth 는 감점)
    healthy = sum(1 for m in (mcp_local_list + connectors.get("platform", [])) if m.get("connected"))
    mcp_q = _q_axis(100, count=mcp_n, used=healthy, weight=8, base_q=0.3)
    score["mcp"] = {
        "value": mcp_q["value"], "max": 100,
        "rawValue": min(100, mcp_q["raw"]), "quality": mcp_q["quality"],
        "note": f"MCP {mcp_n}개 (로컬 {mcp_local} + 플랫폼 {mcp_platform}) · 그 중 정상 연결 {healthy}개 ({int(mcp_q['quality']*100)}%) · 플러그인 제공 {mcp_plugin}개는 별도",
        "formula": f"raw=min(100, {mcp_n}×8)={mcp_q['raw']}, Q={healthy}/{mcp_n}={mcp_q['quality']} (연결 성공률), value={mcp_q['value']}",
        "suggest": ("실패/인증필요 MCP 정리하면 점수 ↑" if mcp_n > 0 and mcp_q['quality'] < 1.0
                    else "MCP 탭의 카탈로그에서 Context7, GitHub, Memory 등 원클릭 설치."),
        "target": "mcp",
    }

    with _db() as c:
        row = c.execute(
            "SELECT AVG(score) AS s, COUNT(*) AS n FROM sessions WHERE tool_use_count >= ?",
            (SCORE_MIN_TOOLS,),
        ).fetchone()
        total_sess = c.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
    avg = int(row["s"] or 0)
    sess_n = row["n"] or 0
    excluded = (total_sess or 0) - sess_n
    score["sessionQuality"] = {
        "value": avg, "max": 100,
        "note": f"평균 세션 스코어 ({sess_n}개 / 도구≥{SCORE_MIN_TOOLS}회 세션 기준 · 짧은 {excluded}개 제외)",
        "formula": f"AVG(score WHERE tool_use_count ≥ {SCORE_MIN_TOOLS}) = {avg} · 각 세션: engagement+productivity+delegation+diversity+reliability",
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
        proj_tok = [dict(r) for r in c.execute(
            "SELECT COALESCE(NULLIF(cwd,''), project_dir) AS key, MAX(cwd) AS cwd, "
            "       COUNT(*) AS sessions, SUM(total_tokens) AS tokens "
            "FROM sessions WHERE total_tokens > 0 "
            "GROUP BY COALESCE(NULLIF(cwd,''), project_dir) "
            "ORDER BY tokens DESC LIMIT 20"
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
    """세션 행 리스트 → 평균 5축 점수. 짧은 세션(도구<기준) 제외."""
    if not rows:
        return {k: 0 for k in SCORE_FORMULA}
    sums = {k: 0 for k in SCORE_FORMULA}
    cnt = 0
    for r in rows:
        if (r.get("tool_use_count") or 0) < SCORE_MIN_TOOLS:
            continue
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
    lang = (body.get("lang") or "ko").lower()
    _lang_map = {"en": "\n\nIMPORTANT: ALL text in the JSON must be in English.", "zh": "\n\nIMPORTANT: ALL text in the JSON must be in Chinese (简体中文)."}
    if lang in _lang_map:
        prompt += _lang_map[lang]

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


_AI_EVAL_CACHE_FILE = _env_path(
    "CLAUDE_DASHBOARD_AI_EVAL_CACHE",
    Path.home() / ".claude-dashboard-ai-evaluation.json",
)


_LATEST_FEATURES_CACHE = _env_path(
    "CLAUDE_DASHBOARD_LATEST_FEATURES",
    Path.home() / ".claude-dashboard-latest-features.json",
)

# 빌트인 신기능 카탈로그 — 수동으로 큐레이션 (최신 공식 발표 기반)
BUILTIN_NEW_FEATURES = [
    {
        "id": "design", "icon": "🎨", "label": "Claude Design",
        "released": "2026-04-17",
        "launchUrl": "https://claude.ai/design",
        "docUrl": "https://www.anthropic.com/news/claude-design-anthropic-labs",
        "summary": "프롬프트 → 비주얼 디자인/슬라이드/원페이저. Opus 4.7 기반.",
    },
    {
        "id": "opus47", "icon": "🧠", "label": "Opus 4.7",
        "released": "2026-04-16",
        "launchUrl": "https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-7",
        "docUrl": "https://www.anthropic.com/news/claude-opus-4-7",
        "summary": "복잡 추론 + 에이전틱 코딩 + 고해상도 비전. Opus 4.6 와 동가격 ($5/$25 per MTok).",
    },
    {
        "id": "managedAgents", "icon": "🤖", "label": "Managed Agents",
        "released": "2026-04-08",
        "launchUrl": "https://platform.claude.com/docs/en/managed-agents/overview",
        "docUrl": "https://platform.claude.com/docs/en/managed-agents/overview",
        "summary": "Claude 를 완전 관리형 에이전트 하네스로 실행. 샌드박스 + 내장 도구 + SSE 스트리밍.",
    },
    {
        "id": "antCli", "icon": "⌨️", "label": "ant CLI",
        "released": "2026-04-08",
        "launchUrl": "https://platform.claude.com/docs/en/api/sdks/cli",
        "docUrl": "https://platform.claude.com/docs/en/api/sdks/cli",
        "summary": "Claude API 커맨드라인 클라이언트. Claude Code 네이티브 통합 + YAML 리소스 버전 관리.",
    },
    {
        "id": "advisorTool", "icon": "🧭", "label": "Advisor Tool",
        "released": "2026-04-09",
        "launchUrl": "https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool",
        "docUrl": "https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool",
        "summary": "빠른 executor 모델 + 고지능 advisor 모델 페어링으로 장기 에이전트 품질↑ 비용↓.",
    },
    {
        "id": "codeRoutines", "icon": "🔁", "label": "Claude Code Routines",
        "released": "2026-04-14",
        "launchUrl": "https://www.anthropic.com/engineering/claude-code-routines",
        "docUrl": "https://docs.claude.com/en/docs/claude-code/routines",
        "summary": "반복 작업을 routine 으로 저장. Mac offline 이어도 웹 인프라에서 실행.",
    },
    {
        "id": "agentSkills", "icon": "🎯", "label": "Agent Skills",
        "released": "2025-10-16",
        "launchUrl": "https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview",
        "docUrl": "https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills",
        "summary": "스킬(지시+스크립트+리소스 묶음) 을 Claude 가 동적으로 로드. PowerPoint/Excel/Word/PDF 기본 제공.",
    },
    {
        "id": "mythos", "icon": "🛡", "label": "Claude Mythos (보안)",
        "released": "2026-04-07",
        "launchUrl": "https://anthropic.com/glasswing",
        "docUrl": "https://red.anthropic.com/2026/mythos-preview/",
        "summary": "방어 보안 특화 언어모델. 초대제 research preview (Project Glasswing).",
    },
]


def api_features_list() -> dict:
    """빌트인 신기능 + 사용자가 '최신 정보 로딩' 으로 발견한 동적 항목."""
    dynamic = []
    if _LATEST_FEATURES_CACHE.exists():
        try:
            cache = json.loads(_LATEST_FEATURES_CACHE.read_text(encoding="utf-8"))
            dynamic = cache.get("features") or []
        except Exception:
            dynamic = []
    return {"builtin": BUILTIN_NEW_FEATURES, "dynamic": dynamic,
            "lastFetched": _LATEST_FEATURES_CACHE.stat().st_mtime if _LATEST_FEATURES_CACHE.exists() else 0}


def api_features_refresh(body: dict) -> dict:
    """Claude CLI 로 최신 Anthropic 발표 조회 → 기존 카탈로그에 없는 항목만 dynamic 에 저장."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return {"error": "claude CLI 설치 필요"}
    if not api_auth_status().get("connected"):
        return {"error": "Claude 계정 연결 필요"}

    existing_ids = {f["id"] for f in BUILTIN_NEW_FEATURES}
    existing_summary = "\n".join(f"- {f['label']} ({f['released']}): {f['summary']}" for f in BUILTIN_NEW_FEATURES)
    today = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""오늘은 {today} 입니다. 최근 60일 안에 Anthropic/Claude 가 공식 발표한 **신기능** 을 조사해 JSON 으로만 답하세요.

## 이미 알고 있는 항목 (중복 제외)
{existing_summary}

## 출력 형식 — JSON 만:
{{
  "features": [
    {{
      "id": "<kebab-case>",
      "icon": "<single emoji>",
      "label": "<한국어 짧은 이름>",
      "released": "<YYYY-MM-DD>",
      "launchUrl": "<사용/시작 URL>",
      "docUrl": "<공식 문서 또는 발표 URL>",
      "summary": "<한 문장 한국어 설명>"
    }},
    ...최대 10개
  ]
}}

조건:
- 위 '이미 알고 있는 항목' 과 같은 기능은 제외.
- Claude API 파라미터 미세 조정 같은 것 말고, **사용자가 직접 체험 가능한** 제품/도구/모델 신기능만.
- 공식 URL (anthropic.com / claude.ai / platform.claude.com / docs.claude.com) 우선.
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
            cost_info = {"costUsd": meta.get("total_cost_usd"), "durationMs": meta.get("duration_ms")}
    except Exception:
        pass

    parsed = {}
    m = re.search(r"\{[\s\S]*\}", response_text)
    if m:
        try: parsed = json.loads(m.group(0))
        except Exception: parsed = {}

    found = parsed.get("features") or []
    # 중복 제거 (빌트인 id 충돌 방지)
    filtered = []
    for f in found:
        if not isinstance(f, dict):
            continue
        fid = (f.get("id") or "").strip()
        if not fid or fid in existing_ids:
            continue
        filtered.append({
            "id": fid,
            "icon": f.get("icon", "✨"),
            "label": f.get("label", fid),
            "released": f.get("released", ""),
            "launchUrl": f.get("launchUrl", ""),
            "docUrl": f.get("docUrl", ""),
            "summary": f.get("summary", ""),
            "isDynamic": True,
        })

    out = {"features": filtered, "fetchedAt": int(time.time() * 1000), "costInfo": cost_info}
    try:
        _LATEST_FEATURES_CACHE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return out


def api_design_exports(query: dict) -> dict:
    """Claude Design export 의심 파일을 스캔 (~/Downloads + 사용자 지정 경로).
    공식 API 가 아직 없어서 로컬 파일시스템 휴리스틱.
    """
    cfg = _load_dash_config()
    extra_dirs = cfg.get("designExportDirs") or []
    default_dirs = [
        str(Path.home() / "Downloads"),
        str(Path.home() / "Documents" / "Claude Design"),
        str(Path.home() / "Desktop"),
    ]
    search_dirs = list(dict.fromkeys(default_dirs + extra_dirs))

    # Claude Design export 파일 패턴:
    # - .pdf, .pptx, .html, .canva 확장자
    # - 파일명에 'claude-design' 또는 'design-handoff' 포함 가능
    out = []
    seen = set()
    now = time.time()
    for d in search_dirs:
        p = Path(d)
        if not p.exists() or not p.is_dir():
            continue
        try:
            # 최근 180일 이내만
            for item in p.iterdir():
                if not item.is_file():
                    continue
                try:
                    mtime = item.stat().st_mtime
                except Exception:
                    continue
                if now - mtime > 180 * 86400:
                    continue
                name_lower = item.name.lower()
                ext = item.suffix.lower()
                # 명시적 keyword 우선, 그 외 design-typical 확장자도 수집
                is_design_keyword = any(k in name_lower for k in
                    ("claude-design", "claude_design", "design-handoff", "handoff-bundle"))
                is_design_ext = ext in (".pdf", ".pptx", ".html")
                if not (is_design_keyword or is_design_ext):
                    continue
                key = str(item)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    size = item.stat().st_size
                except Exception:
                    size = 0
                out.append({
                    "path": key,
                    "name": item.name,
                    "dir": str(p),
                    "ext": ext.lstrip("."),
                    "size": size,
                    "mtime": int(mtime * 1000),
                    "matchedByKeyword": is_design_keyword,
                })
        except Exception:
            continue
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return {
        "searchedDirs": search_dirs,
        "files": out[:60],
        "hint": "Claude Design 공식 API 는 아직 미공개. claude.ai/design 에서 PDF/PPTX/HTML 로 export 한 파일을 기본 경로에서 스캔합니다.",
    }


def api_design_add_dir(body: dict) -> dict:
    """Claude Design export 를 저장하는 추가 디렉토리 등록."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    dir_path = (body.get("dir") or "").strip()
    if not dir_path:
        return {"ok": False, "error": "dir required"}
    p = Path(os.path.expanduser(dir_path)).resolve()
    home = Path.home().resolve()
    try:
        p.relative_to(home)
    except ValueError:
        return {"ok": False, "error": "홈 디렉토리 밖 경로 거부"}
    if not p.is_dir():
        return {"ok": False, "error": "디렉토리가 아님 또는 존재하지 않음"}
    cfg = _load_dash_config()
    arr = cfg.get("designExportDirs") or []
    if str(p) not in arr:
        arr.append(str(p))
    cfg["designExportDirs"] = arr
    _save_dash_config(cfg)
    return {"ok": True, "dirs": arr}


def api_ai_evaluation(body: dict) -> dict:
    """전체 셋업을 Claude 에게 평가받음. 비싸므로 force=true 시에만 새로 호출."""
    if not isinstance(body, dict):
        body = {}
    force = bool(body.get("force"))
    # 캐시 (수동 갱신 방식)
    if not force and _AI_EVAL_CACHE_FILE.exists():
        try:
            cached = json.loads(_AI_EVAL_CACHE_FILE.read_text(encoding="utf-8"))
            return {"cached": True, **cached}
        except Exception:
            pass
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return {"error": "claude CLI 설치 필요"}
    if not api_auth_status().get("connected"):
        return {"error": "Claude 계정 연결 필요"}

    # 컨텍스트 수집 — 결정론적 점수 + 사용 패턴 통계
    det = api_optimization_score()
    qm = _quality_metrics_30d()
    plugin_assets = _count_enabled_plugin_assets()
    settings = get_settings()
    auth = api_auth_status()
    _db_init()
    with _db() as c:
        proj_rows = c.execute(
            """SELECT cwd, COUNT(*) AS n, AVG(score) AS avg_s, SUM(total_tokens) AS toks
               FROM sessions WHERE cwd != '' GROUP BY cwd ORDER BY n DESC LIMIT 8"""
        ).fetchall()
        top_tools = [dict(r) for r in c.execute(
            "SELECT tool, COUNT(*) AS n FROM tool_uses GROUP BY tool ORDER BY n DESC LIMIT 12"
        ).fetchall()]
        top_subagents = [dict(r) for r in c.execute(
            "SELECT subagent_type AS name, COUNT(*) AS n FROM tool_uses WHERE subagent_type != '' GROUP BY subagent_type ORDER BY n DESC LIMIT 10"
        ).fetchall()]

    projects = [{"name": Path(r["cwd"]).name, "cwd": r["cwd"], "sessions": r["n"],
                 "avg": int(r["avg_s"] or 0), "tokens": r["toks"] or 0} for r in proj_rows]

    deterministic_summary = {k: {"value": v["value"], "quality": v.get("quality"), "note": v["note"]}
                             for k, v in (det.get("breakdown") or {}).items()}

    prompt = f"""당신은 Claude Code 워크플로우 최적화 전문가입니다.
아래 사용자의 셋업과 30일 사용 패턴을 보고, 종합적인 평가와 개선 우선순위를 JSON 으로 답하세요.

## 사용자
- 이름: {auth.get('displayName','')}, 플랜: {auth.get('planLabel','')}

## 결정론적 점수 (참고용 — 단순 휴리스틱)
- 종합: {det.get('overall')}/100
{json.dumps(deterministic_summary, ensure_ascii=False, indent=2)[:2500]}

## 30일 사용 패턴
- 전체 도구 호출 종류: {qm['toolDiversity30d']}종
- 위임된 서브에이전트 종류: {len(qm['usedSubagents'])}종 → {sorted(list(qm['usedSubagents']))[:20]}
- Agent 도구 호출 총: {qm['agentCalls30d']}회
- 상위 도구: {', '.join(t['tool']+'×'+str(t['n']) for t in top_tools[:8])}
- 상위 위임 에이전트: {', '.join(s['name']+'×'+str(s['n']) for s in top_subagents[:6])}

## 주요 프로젝트 (상위 6개)
{_format_projects_for_prompt(projects[:6])}

## 셋업 인벤토리
- 사용자 정의 스킬: {sum(1 for s in list_skills() if s.get('scope')=='user')} (플러그인 제공 추가 {plugin_assets['skills']})
- 사용자 훅: {sum(len(v) if isinstance(v,list) else 0 for v in (settings.get('hooks',{}) or {}).values())}
- 사용자 에이전트: {len([a for a in list_agents().get('agents',[]) if a.get('scope')=='global'])}
- 활성 플러그인: {sum(1 for p in list_plugins_api() if p.get('enabled'))}

## 출력 형식 — JSON 만:
{{
  "overall": 0~100 정수,
  "verdict": "한 줄 종합 평가",
  "strengths": ["잘하고 있는 점 3개 이내"],
  "weaknesses": ["개선이 필요한 점 3개 이내"],
  "priorities": [
    {{"rank": 1, "title": "최우선 개선 항목", "impact": "high|medium|low", "effort": "low|medium|high",
      "rationale": "왜", "action": "구체적으로 무엇을 해야 하는지"}},
    ... 최대 5개
  ],
  "patternInsights": ["사용 패턴에서 발견한 흥미로운 점 2-3개"]
}}
"""
    # 언어 지시 주입
    lang = (body.get("lang") or "ko").lower() if isinstance(body, dict) else "ko"
    lang_map = {"en": "\n\nIMPORTANT: ALL text values in the JSON must be in English.", "zh": "\n\nIMPORTANT: ALL text values in the JSON must be in Chinese (简体中文)."}
    if lang in lang_map:
        prompt += lang_map[lang]
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

    # JSON 추출
    parsed: dict = {}
    m = re.search(r"\{[\s\S]*\}", response_text)
    if m:
        try:
            parsed = json.loads(m.group(0))
        except Exception:
            parsed = {}

    out = {
        "evaluation": parsed,
        "raw": response_text[:6000],
        "costInfo": cost_info,
        "deterministic": {"overall": det.get("overall"), "breakdown": det.get("breakdown")},
        "ts": int(time.time() * 1000),
        "cached": False,
        "lang": lang,
    }
    try:
        _AI_EVAL_CACHE_FILE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return out


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
    elif kind == "plugins":
        # 사용자가 설치한 플러그인 + 비활성 플러그인 + 사용 패턴 → 추천
        plugins = list_plugins_api()
        installed_plugins = [{"id": p.get("id"), "enabled": p.get("enabled"), "marketplace": p.get("marketplace"),
                              "description": (p.get("description") or "")[:200]} for p in plugins]
        # 마켓플레이스 카탈로그 (browse) 에서 후보 가져오기
        try:
            browse = api_plugins_browse()
            available = [{"id": p.get("id") or p.get("name"), "marketplace": p.get("marketplace"),
                          "description": (p.get("description") or "")[:200],
                          "tags": p.get("tags") or [], "enabled": p.get("enabled")}
                         for p in browse.get("plugins", []) if not p.get("enabled")][:60]
        except Exception:
            available = []
        current_obj = {"installed": installed_plugins, "candidates": available}
        system_intro = (
            "사용자의 작업 패턴에 맞는 Claude Code 플러그인 활성화/추가를 추천하세요. "
            "이미 활성화된 플러그인은 제외하고, candidates 안에서만 골라 최대 5개까지 우선순위 매겨 추천하세요. "
            "사용자가 새 마켓플레이스를 추가해야 하는 경우 marketplaceUrl 필드도 함께."
        )
        output_shape = (
            '{"recommendations": ['
            '{"action":"enable","pluginKey":"<plugin>@<market>","why":"<왜 도움이 되는지>","priority":1},'
            '{"action":"install","pluginId":"<plugin>","marketplace":"<market>","marketplaceUrl":"<git url 옵션>","why":"...","priority":2}'
            ']}'
        )
        apply_hint = "각 추천을 클릭해 토글/설치"
    elif kind == "mcp":
        connectors = list_connectors()
        # 카탈로그 후보
        try:
            cat = api_mcp_catalog()
            candidates = [{"id": m.get("id"), "name": m.get("name"), "category": m.get("category"),
                          "description": (m.get("description") or "")[:200], "cli": m.get("cli","")[:200]}
                         for m in cat.get("catalog", []) if not m.get("installed")][:30]
        except Exception:
            candidates = []
        current_obj = {
            "installed": {
                "local": [m.get("name") for m in connectors.get("local", [])],
                "platform": [m.get("name") for m in connectors.get("platform", [])],
                "plugin": [m.get("name") for m in connectors.get("plugin", [])],
                "desktop": [m.get("name") for m in connectors.get("desktop", [])],
            },
            "candidates": candidates,
        }
        system_intro = (
            "사용자 작업 패턴에 맞는 MCP 서버 추가를 추천하세요. "
            "candidates 안에서만 고르고, 이미 설치된 것(installed) 은 제외. "
            "사용자가 자주 호출하는 도구(top_tools)를 보고 어떤 MCP 가 워크플로우를 더 효율적으로 만들지 판단."
        )
        output_shape = (
            '{"recommendations": ['
            '{"mcpId":"<id from candidates>","why":"<workflow 에 어떻게 도움되는지>","cli":"<claude mcp add ...>","priority":1}'
            ']}'
        )
        apply_hint = "각 추천을 클릭해 한 번에 설치"
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
    lang = (body.get("lang") or "ko").lower()
    lang_map = {"en": "\n\nIMPORTANT: ALL text in the response must be in English.", "zh": "\n\nIMPORTANT: ALL text in the response must be in Chinese (简体中文)."}
    if lang in lang_map:
        prompt += lang_map[lang]
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
    lang = (body.get("lang") or "ko").lower()
    _lang_map = {"en": "\n\nIMPORTANT: Write the CLAUDE.md content in English.", "zh": "\n\nIMPORTANT: Write the CLAUDE.md content in Chinese (简体中文)."}
    if lang in _lang_map:
        prompt += _lang_map[lang]
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




# ───────────────── routes ─────────────────

from server.briefing import (
    _today_start_ts_ms, _iter_history_recent, _today_history_stats,
    _count_projects, _count_active_sessions, _count_tasks_in_todos,
    _read_scheduled_tasks, _read_tasks,
    briefing_overview, briefing_devices, briefing_activity,
    briefing_schedule, briefing_projects_summary, briefing_pending_approvals,
)
from server.auth import (
    CLAUDE_PLANS,
    api_team_info, api_auth_status, api_set_claimed_plan,
    api_auth_login, api_auth_logout,
)
from server.actions import (
    _find_terminal_app_for_pid, _CHAT_SYSTEM_PROMPT,
    open_session_action, open_folder_action,
    api_chat, handle_chat_stream,
)


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
    "/api/permissions/diagnose": lambda q: {"issues": validate_permissions(get_settings().get("permissions") or {})},
    "/api/evaluation/ai": lambda q: api_ai_evaluation({"force": False}),
    "/api/design/exports": api_design_exports,
    "/api/features/list": lambda q: api_features_list(),
    "/api/auth/status": lambda q: api_auth_status(),
    "/api/project/detail": api_project_detail,
    "/api/project/score-detail": api_project_score_detail,
    "/api/project/tool-breakdown": api_project_tool_breakdown,
    "/api/project/timeline": api_project_timeline,
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

    def _get_lang(self) -> str:
        """쿼리 파라미터 또는 쿠키에서 언어 감지."""
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        lang = (qs.get("lang", [""])[0] or "").lower()
        if lang in ("en", "zh"):
            return lang
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("cc-lang="):
                v = part.split("=", 1)[1].strip().lower()
                if v in ("en", "zh"):
                    return v
        return "ko"

    def _send_static(self, path: str) -> None:
        if path in ("/", ""):
            path = "/index.html"
        rel = path.lstrip("/")
        fp = (DIST / rel).resolve()
        if not str(fp).startswith(str(DIST.resolve())):
            self.send_response(403); self.end_headers(); return
        if not fp.exists() or not fp.is_file():
            fp = DIST / "index.html"
        # 언어별 HTML 파일 서빙
        if fp.name == "index.html":
            lang = self._get_lang()
            if lang == "en":
                alt = DIST / "index-en.html"
                if alt.exists(): fp = alt
            elif lang == "zh":
                alt = DIST / "index-zh.html"
                if alt.exists(): fp = alt
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
        m = re.match(r"^/api/sessions/tokens/([0-9a-f-]+)$", path)
        if m:
            try:
                self._send_json(api_session_tokens(m.group(1)))
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return
        m = re.match(r"^/api/sessions/timeline/([0-9a-f-]+)$", path)
        if m:
            try:
                self._send_json(api_session_timeline(m.group(1)))
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
        if path == "/api/evaluation/ai":
            self._send_json(api_ai_evaluation(self._read_body())); return
        if path == "/api/design/add-dir":
            self._send_json(api_design_add_dir(self._read_body())); return
        if path == "/api/features/refresh":
            self._send_json(api_features_refresh(self._read_body())); return
        if path == "/api/commands/translate":
            self._send_json(api_commands_translate(self._read_body())); return
        if path == "/api/translate/batch":
            self._send_json(api_translate_batch(self._read_body())); return
        if path == "/api/mcp/install":
            self._send_json(api_mcp_install(self._read_body())); return
        if path == "/api/mcp/install/prepare":
            self._send_json(api_mcp_install_prepare(self._read_body())); return
        if path == "/api/mcp/remove":
            self._send_json(api_mcp_remove(self._read_body())); return
        if path == "/api/mcp/project/remove":
            self._send_json(api_mcp_project_remove(self._read_body())); return
        if path == "/api/plugins/toggle":
            self._send_json(api_plugin_toggle(self._read_body())); return
        if path == "/api/hooks/plugin/update":
            self._send_json(api_plugin_hook_update(self._read_body())); return
        if path == "/api/auth/claimed-plan":
            self._send_json(api_set_claimed_plan(self._read_body())); return
        if path == "/api/auth/login":
            self._send_json(api_auth_login(self._read_body())); return
        if path == "/api/auth/logout":
            self._send_json(api_auth_logout(self._read_body())); return
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
        if path == "/api/chat":
            self._send_json(api_chat(self._read_body())); return
        if path == "/api/chat/stream":
            handle_chat_stream(self, self._read_body()); return
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


def _warmup_caches() -> None:
    """비싼 외부 호출 결과를 미리 채워둠 — 첫 사용자 요청이 6초 걸리던 문제 해결."""
    import threading
    def _run():
        try:
            t0 = time.time()
            _claude_mcp_list_cached()  # 6초 caches 채움
            print(f"[server] warmup mcp list: {time.time()-t0:.2f}s")
        except Exception as e:
            print(f"[server] warmup failed: {e}")
    threading.Thread(target=_run, daemon=True).start()


def main() -> None:
    _db_init()
    _background_index()
    _warmup_caches()
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "127.0.0.1")
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving http://{host}:{port} (dist={DIST}, db={DB_PATH})")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
