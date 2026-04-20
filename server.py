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





























from server.features import (
    BUILTIN_NEW_FEATURES,
    _AI_EVAL_CACHE_FILE, _LATEST_FEATURES_CACHE,
    _count_enabled_plugin_assets, _quality_metrics_30d, _q_axis,
    api_optimization_score,
    _deep_merge_settings,
    _project_avg_breakdown, _suggest_files_for_project,
    _template_claude_md, _template_agent_md, _template_skill_md,
    _template_settings_local, _template_hooks_patch,
    _safe_join_under, _format_sample_prompts, _format_existing_md_block,
    api_project_ai_recommend,
    api_features_list, api_features_refresh,
    api_design_exports, api_design_add_dir,
    api_ai_evaluation, api_feature_recommend, api_global_claude_md_recommend,
    _format_projects_for_prompt, _format_tools_for_prompt,
    api_project_file_put, api_settings_preview,
)
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
from server.system import (
    COST_LOG, BASH_LOG,
    _running_sessions, get_system_status, get_recommended_settings, get_device_info,
    api_usage_summary, api_memory_list,
    api_tasks_list, api_task_save, api_task_delete,
    api_output_styles_list, api_output_style_save, api_output_style_delete,
    api_statusline_info, api_plans_list, api_metrics_summary,
    api_backups_list, api_env_config, _mask_secret, api_model_config,
    api_ide_status, api_scheduled_tasks, api_bash_history,
    api_telemetry_summary, api_homunculus_projects,
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
