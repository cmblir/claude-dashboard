"""HTTP 라우팅 · 정적 파일 서빙 · Handler 클래스.

경로별 dict 기반 dispatch + `/api/sessions/detail/<uuid>` 류 regex 라우트.
피처 모듈들이 여기서 한데 모인다 — 피처 모듈은 routes 를 import 하지 않는다.
"""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from .actions import (
    api_chat, api_session_spawn, handle_chat_stream,
    open_folder_action, open_session_action,
)
from .agents import (
    api_agent_create, api_agent_delete, get_agent, list_agents, put_agent,
)
from .auth import (
    api_auth_login, api_auth_logout, api_auth_status,
    api_set_claimed_plan, api_team_info,
)
from .briefing import (
    briefing_activity, briefing_devices, briefing_overview,
    briefing_pending_approvals, briefing_projects_summary, briefing_schedule,
)
from .claude_md import (
    get_claude_md, get_settings, put_claude_md, put_settings,
    validate_permissions,
)
from .commands import list_commands
from .config import DIST
from .features import (
    api_ai_evaluation, api_design_add_dir, api_design_exports,
    api_feature_recommend, api_features_list, api_features_refresh,
    api_global_claude_md_recommend, api_optimization_score,
    api_project_ai_recommend, api_project_file_put, api_settings_preview,
)
from .guide import api_guide_onboarding, api_guide_toolkit
from .hooks import api_plugin_hook_update, get_hooks
from .prompt_cache import (
    api_prompt_cache_examples, api_prompt_cache_history,
    api_prompt_cache_test,
)
from .thinking_lab import (
    api_thinking_lab_examples, api_thinking_lab_history,
    api_thinking_lab_models, api_thinking_lab_test,
)
from .tool_use_lab import (
    api_tool_use_history, api_tool_use_templates, api_tool_use_turn,
)
from .batch_jobs import (
    api_batch_cancel, api_batch_create, api_batch_examples,
    api_batch_get, api_batch_list, api_batch_results,
)
from .api_files import (
    api_files_delete, api_files_list, api_files_test, api_files_upload,
)
from .vision_lab import api_vision_compare, api_vision_models
from .model_bench import api_model_bench_run, api_model_bench_sets
from .server_tools import (
    api_server_tools_catalog, api_server_tools_history, api_server_tools_run,
)
from .claude_docs import api_claude_docs_list, api_claude_docs_search
from .citations_lab import (
    api_citations_examples, api_citations_history, api_citations_test,
)
from .agent_sdk_scaffold import api_scaffold_catalog, api_scaffold_create
from .embedding_lab import (
    api_embedding_compare, api_embedding_examples, api_embedding_providers,
)
from .version import api_version_info
from .workflows import (
    api_workflow_clone, api_workflow_delete, api_workflow_export,
    api_workflow_get, api_workflow_history, api_workflow_import,
    api_workflow_node_clipboard, api_workflow_patch,
    api_workflow_restore, api_workflow_run,
    api_workflow_run_status, api_workflow_runs_list, api_workflow_save,
    api_workflow_schedule_list, api_workflow_schedule_set,
    api_workflow_stats,
    api_workflow_template_delete, api_workflow_template_get,
    api_workflow_template_save, api_workflow_templates_list,
    api_workflow_webhook, api_workflows_list, handle_workflow_run_stream,
)
from .ai_keys import (
    api_providers_list, api_provider_test, api_provider_save_key,
    api_provider_delete_key, api_custom_provider_save,
    api_custom_provider_delete, api_fallback_chain_save,
    api_workflow_costs_summary, api_provider_compare,
    api_provider_health, api_usage_alert_check, api_usage_alert_set,
    api_set_default_model, api_ollama_settings_get, api_ollama_settings_save,
)
from .ai_providers import list_providers_by_capability
from .cli_tools import api_cli_status, api_cli_install, api_cli_login
from .ollama_hub import (
    api_ollama_models, api_ollama_catalog, api_ollama_pull,
    api_ollama_pull_status, api_ollama_delete, api_ollama_model_info,
    api_ollama_serve_start, api_ollama_serve_stop, api_ollama_serve_status,
    api_ollama_create_model,
)


def _ai_providers_by_cap(query: dict) -> dict:
    """GET /api/ai-providers/by-capability?cap=embed"""
    cap = (query.get("cap", ["chat"])[0] or "chat").strip()
    return {"capability": cap, "providers": list_providers_by_capability(cap)}
from .logger import log
from .mcp import (
    api_mcp_catalog, api_mcp_install, api_mcp_install_prepare,
    api_mcp_project_remove, api_mcp_remove, list_connectors,
)
from .plugins import (
    api_marketplace_add, api_marketplace_list, api_marketplace_remove,
    api_plugin_toggle, api_plugins_browse, list_marketplaces, list_plugins_api,
)
from .projects import (
    api_agent_roles, api_project_agent_add, api_project_agent_delete,
    api_project_agent_save, api_project_agents_list, api_project_detail,
    api_project_score_detail, api_project_tool_breakdown,
    api_subagent_model_choices, api_subagent_set_model, list_projects,
)
from .sessions import (
    api_agent_graph, api_project_timeline, api_session_detail,
    api_session_timeline, api_session_tokens, api_sessions_list,
    api_sessions_stats, index_all_sessions,
)
from .skills import get_skill, list_skills, put_skill
from .system import (
    api_backups_list, api_bash_history, api_env_config, api_homunculus_projects,
    api_ide_status, api_memory_list, api_metrics_summary, api_model_config,
    api_output_style_delete, api_output_style_save, api_output_styles_list,
    api_plans_list, api_scheduled_tasks, api_statusline_info,
    api_task_delete, api_task_save, api_tasks_list, api_telemetry_summary,
    api_usage_summary, get_device_info, get_recommended_settings,
    get_system_status,
)


# ───────── 라우트 테이블 ─────────

ROUTES_GET: dict[str, Callable[[dict], Any]] = {
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
    "/api/permissions/diagnose": lambda q: {
        "issues": validate_permissions(get_settings().get("permissions") or {}),
    },
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
    "/api/guide/toolkit": lambda q: api_guide_toolkit(),
    "/api/guide/onboarding": lambda q: api_guide_onboarding(),
    "/api/workflows/list": lambda q: api_workflows_list(q),
    "/api/workflows/run-status": api_workflow_run_status,
    "/api/workflows/runs": api_workflow_runs_list,
    "/api/workflows/templates/list": lambda q: api_workflow_templates_list(q),
    "/api/workflows/schedules": lambda q: api_workflow_schedule_list(),
    "/api/workflows/stats": lambda q: api_workflow_stats(),
    "/api/workflows/history": api_workflow_history,
    "/api/version": lambda q: api_version_info(),
    "/api/ai-providers/list": lambda q: api_providers_list(),
    "/api/ai-providers/costs": lambda q: api_workflow_costs_summary(),
    "/api/ai-providers/by-capability": lambda q: _ai_providers_by_cap(q),
    "/api/ai-providers/health": lambda q: api_provider_health(),
    "/api/ai-providers/usage-alert": lambda q: api_usage_alert_check(),
    "/api/cli/status": api_cli_status,
    "/api/ollama/models": lambda q: api_ollama_models(),
    "/api/ollama/catalog": api_ollama_catalog,
    "/api/ollama/pull-status": api_ollama_pull_status,
    "/api/ollama/info": api_ollama_model_info,
    "/api/ollama/serve/status": lambda q: api_ollama_serve_status(),
    "/api/ollama/settings": lambda q: api_ollama_settings_get(),
    "/api/prompt-cache/examples": api_prompt_cache_examples,
    "/api/prompt-cache/history": api_prompt_cache_history,
    "/api/thinking-lab/examples": api_thinking_lab_examples,
    "/api/thinking-lab/history": api_thinking_lab_history,
    "/api/thinking-lab/models": api_thinking_lab_models,
    "/api/tool-use-lab/templates": api_tool_use_templates,
    "/api/tool-use-lab/history": api_tool_use_history,
    "/api/batch/examples": api_batch_examples,
    "/api/batch/list": api_batch_list,
    "/api/batch/get": api_batch_get,
    "/api/batch/results": api_batch_results,
    "/api/api-files/list": api_files_list,
    "/api/vision-lab/models": api_vision_models,
    "/api/model-bench/sets": api_model_bench_sets,
    "/api/server-tools/catalog": api_server_tools_catalog,
    "/api/server-tools/history": api_server_tools_history,
    "/api/claude-docs/list": api_claude_docs_list,
    "/api/claude-docs/search": api_claude_docs_search,
    "/api/citations-lab/examples": api_citations_examples,
    "/api/citations-lab/history": api_citations_history,
    "/api/scaffold/catalog": api_scaffold_catalog,
    "/api/embedding-lab/providers": api_embedding_providers,
    "/api/embedding-lab/examples": api_embedding_examples,
}


# POST 라우트 — body(dict) 를 받는 핸들러 매핑
def _reindex_handler(body: dict) -> dict:
    force = bool((body or {}).get("force", False))
    return index_all_sessions(force=force)


# 번역 배치는 auth/plugins/skills/agents 를 모두 참조 — late import 로 순환 회피
def _translate_batch_handler(body: dict) -> dict:
    from .commands import api_translate_batch
    return api_translate_batch(body)


def _commands_translate_handler(body: dict) -> dict:
    from .commands import api_commands_translate
    return api_commands_translate(body)


ROUTES_POST: dict[str, Callable[[dict], Any]] = {
    "/api/open-folder": open_folder_action,
    "/api/open-session": open_session_action,
    "/api/sessions/reindex": _reindex_handler,
    "/api/settings/preview": api_settings_preview,
    "/api/project/file": api_project_file_put,
    "/api/project/ai-recommend": api_project_ai_recommend,
    "/api/global/claude-md-recommend": api_global_claude_md_recommend,
    "/api/feature/recommend": api_feature_recommend,
    "/api/evaluation/ai": api_ai_evaluation,
    "/api/design/add-dir": api_design_add_dir,
    "/api/features/refresh": api_features_refresh,
    "/api/commands/translate": _commands_translate_handler,
    "/api/translate/batch": _translate_batch_handler,
    "/api/mcp/install": api_mcp_install,
    "/api/mcp/install/prepare": api_mcp_install_prepare,
    "/api/mcp/remove": api_mcp_remove,
    "/api/mcp/project/remove": api_mcp_project_remove,
    "/api/plugins/toggle": api_plugin_toggle,
    "/api/hooks/plugin/update": api_plugin_hook_update,
    "/api/auth/claimed-plan": api_set_claimed_plan,
    "/api/auth/login": api_auth_login,
    "/api/auth/logout": api_auth_logout,
    "/api/cli/install": api_cli_install,
    "/api/cli/login": api_cli_login,
    "/api/project-agents/add": api_project_agent_add,
    "/api/project-agents/delete": api_project_agent_delete,
    "/api/project-agents/save": api_project_agent_save,
    "/api/subagent/set-model": api_subagent_set_model,
    "/api/agents/create": api_agent_create,
    "/api/agents/delete": api_agent_delete,
    "/api/tasks/save": api_task_save,
    "/api/tasks/delete": api_task_delete,
    "/api/output-styles/save": api_output_style_save,
    "/api/output-styles/delete": api_output_style_delete,
    "/api/marketplaces/add": api_marketplace_add,
    "/api/marketplaces/remove": api_marketplace_remove,
    "/api/chat": api_chat,
    "/api/workflows/save": api_workflow_save,
    "/api/workflows/patch": api_workflow_patch,
    "/api/workflows/delete": api_workflow_delete,
    "/api/workflows/run": api_workflow_run,
    "/api/workflows/templates/save": api_workflow_template_save,
    "/api/workflows/templates/delete": api_workflow_template_delete,
    "/api/workflows/export": api_workflow_export,
    "/api/workflows/import": api_workflow_import,
    "/api/workflows/schedule/set": api_workflow_schedule_set,
    "/api/workflows/restore": api_workflow_restore,
    "/api/workflows/clone": api_workflow_clone,
    "/api/workflows/node-clipboard": api_workflow_node_clipboard,
    "/api/session/spawn": api_session_spawn,
    "/api/ai-providers/test": api_provider_test,
    "/api/ai-providers/compare": api_provider_compare,
    "/api/ai-providers/save-key": api_provider_save_key,
    "/api/ai-providers/delete-key": api_provider_delete_key,
    "/api/ai-providers/custom/save": api_custom_provider_save,
    "/api/ai-providers/custom/delete": api_custom_provider_delete,
    "/api/ai-providers/fallback-chain": api_fallback_chain_save,
    "/api/ai-providers/usage-alert/set": api_usage_alert_set,
    "/api/ollama/pull": api_ollama_pull,
    "/api/ollama/delete": api_ollama_delete,
    "/api/ollama/serve/start": api_ollama_serve_start,
    "/api/ollama/create": api_ollama_create_model,
    "/api/ollama/settings/save": api_ollama_settings_save,
    "/api/ollama/serve/stop": api_ollama_serve_stop,
    "/api/ai-providers/default-model": api_set_default_model,
    "/api/prompt-cache/test": api_prompt_cache_test,
    "/api/thinking-lab/test": api_thinking_lab_test,
    "/api/tool-use-lab/turn": api_tool_use_turn,
    "/api/batch/create": api_batch_create,
    "/api/batch/cancel": api_batch_cancel,
    "/api/api-files/upload": api_files_upload,
    "/api/api-files/delete": api_files_delete,
    "/api/api-files/test": api_files_test,
    "/api/vision-lab/compare": api_vision_compare,
    "/api/model-bench/run": api_model_bench_run,
    "/api/server-tools/run": api_server_tools_run,
    "/api/citations-lab/test": api_citations_test,
    "/api/scaffold/create": api_scaffold_create,
    "/api/embedding-lab/compare": api_embedding_compare,
}


ROUTES_PUT: dict[str, Callable[[dict], Any]] = {
    "/api/claude-md": put_claude_md,
    "/api/settings": put_settings,
    "/api/project-agents/save": api_project_agent_save,
}


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "application/javascript",
    ".mjs": "application/javascript", ".css": "text/css",
    ".json": "application/json", ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2",
    ".map": "application/json",
}


# ───────── Handler ─────────

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
        # i18n 은 이제 런타임 fetch (dist/locales/*.json). index.html 은 단일 파일만 서빙.
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

    def _send_locale(self, lang: str) -> None:
        """/api/locales/{lang}.json 서빙. 화이트리스트 검증."""
        if lang not in ("ko", "en", "zh"):
            self.send_response(404); self.end_headers(); return
        fp = DIST / "locales" / f"{lang}.json"
        if not fp.exists():
            self.send_response(404); self.end_headers(); return
        try:
            data = fp.read_bytes()
        except Exception:
            self.send_response(500); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
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
        # /api/locales/{lang}.json 전용 핸들러 (JSON 이지만 dist/locales 파일 서빙)
        m = re.match(r"^/api/locales/([a-z]{2})\.json$", path)
        if m:
            self._send_locale(m.group(1))
            return
        # SSE 스트림 엔드포인트 — 일반 JSON 이 아닌 text/event-stream
        if path == "/api/workflows/run-stream":
            handle_workflow_run_stream(self, query)
            return
        if path in ROUTES_GET:
            try:
                self._send_json(ROUTES_GET[path](query))
            except Exception as e:
                log.exception("route error: %s", path)
                self._send_json({"error": str(e)}, 500)
            return
        # regex item-routes
        for pattern, fn in _ITEM_GET_ROUTES:
            m = pattern.match(path)
            if m:
                try:
                    self._send_json(fn(m.group(1)))
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
        if path in ROUTES_PUT:
            self._send_json(ROUTES_PUT[path](body)); return
        # regex item-routes
        m = re.match(r"^/api/skills/([^/]+)$", path)
        if m:
            self._send_json(put_skill(m.group(1), body)); return
        m = re.match(r"^/api/agents/([A-Za-z0-9_.:-]+)$", path)
        if m:
            self._send_json(put_agent(m.group(1), body)); return
        self._send_json({"ok": False, "error": "unknown route"}, 404)

    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path)
        # chat/stream 은 SSE 응답 — dict 외 Handler 를 직접 받음
        if path == "/api/chat/stream":
            handle_chat_stream(self, self._read_body())
            return
        if path in ROUTES_POST:
            self._send_json(ROUTES_POST[path](self._read_body())); return
        # regex POST routes — webhook
        m = re.match(r"^/api/workflows/webhook/(wf-[0-9]{10,14}-[a-z0-9]{3,6})$", path)
        if m:
            self._send_json(api_workflow_webhook(m.group(1), self._read_body())); return
        self._drain()
        self._send_json({"ok": False, "error": "unknown route"}, 404)

    def do_DELETE(self) -> None:
        self._drain()
        self._send_json({"ok": False, "readOnly": True})

    def log_message(self, fmt, *args) -> None:
        log.info("%s %s", self.command, self.path)


# regex 기반 GET 아이템 라우트 (path param 1개)
_ITEM_GET_ROUTES = [
    (re.compile(r"^/api/sessions/detail/([0-9a-f-]+)$"), api_session_detail),
    (re.compile(r"^/api/sessions/tokens/([0-9a-f-]+)$"), api_session_tokens),
    (re.compile(r"^/api/sessions/timeline/([0-9a-f-]+)$"), api_session_timeline),
    (re.compile(r"^/api/skills/([^/]+)$"), get_skill),
    (re.compile(r"^/api/agents/([A-Za-z0-9_.:-]+)$"), get_agent),
    (re.compile(r"^/api/workflows/(wf-[0-9]{10,14}-[a-z0-9]{3,6})$"), api_workflow_get),
    (re.compile(r"^/api/workflows/templates/(tpl-[0-9]{10,14}-[a-z0-9]{3,6}|bt-[a-z0-9-]+)$"), api_workflow_template_get),
]
