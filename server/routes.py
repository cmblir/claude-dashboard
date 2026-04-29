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
from .hooks import api_plugin_hook_update, api_recent_blocked_hooks, get_hooks
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
    api_batch_budget_get, api_batch_budget_set, api_batch_cancel,
    api_batch_create, api_batch_examples, api_batch_get,
    api_batch_list, api_batch_results,
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
from .prompt_library import (
    api_prompt_library_delete, api_prompt_library_duplicate,
    api_prompt_library_list, api_prompt_library_save,
    api_prompt_library_to_workflow,
)
from .cost_timeline import api_cost_timeline_summary
from .rtk_lab import (
    api_rtk_status, api_rtk_install, api_rtk_init,
    api_rtk_config, api_rtk_gain, api_rtk_session,
    api_rtk_uninstall_hook,
)
from .toolkits import (
    api_toolkit_status,
    api_toolkit_ecc_install, api_toolkit_ecc_uninstall,
    api_toolkit_ecc_install_plugin, api_toolkit_ecc_uninstall_plugin,
    api_toolkit_ccb_install, api_toolkit_ccb_uninstall, api_toolkit_ccb_open,
)
from .notify import api_notify_test
from .slack_api import (
    api_slack_config_clear, api_slack_config_get, api_slack_config_save,
    api_slack_test,
)
from .obsidian_log import api_obsidian_test
from .crew_wizard import api_crew_create, api_crew_preview
from .run_center import (
    api_run_catalog, api_run_execute, api_run_favorite_toggle,
    api_run_history, api_run_history_get, api_run_to_workflow,
)
from .session_replay import api_session_replay_list, api_session_replay_load
from .event_forwarder import (
    api_event_forwarder_list, api_event_forwarder_add,
    api_event_forwarder_remove, api_event_forwarder_meta,
)
from .learner import api_learner_patterns
from .security_scan import api_security_scan
from .mcp_server import api_mcp_server_info
from .artifacts import api_artifacts_list, api_artifacts_render
from .version import api_version_info
from .workflows import (
    api_workflow_clone, api_workflow_delete, api_workflow_export,
    api_workflow_get, api_workflow_history, api_workflow_import,
    api_workflow_node_clipboard, api_workflow_patch,
    api_workflow_dry_run, api_workflow_restore, api_workflow_run,
    api_workflow_run_diff, api_workflow_run_status,
    api_workflow_runs_list, api_workflow_save,
    api_workflow_schedule_list, api_workflow_schedule_set,
    api_workflow_stats,
    api_workflow_template_delete, api_workflow_template_get,
    api_workflow_template_save, api_workflow_templates_list,
    api_workflow_webhook, api_workflow_webhook_secret,
    api_workflows_list, handle_workflow_run_stream,
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
from .auto_resume import (
    api_auto_resume_cancel, api_auto_resume_get,
    api_auto_resume_hook_status, api_auto_resume_install_hooks,
    api_auto_resume_set, api_auto_resume_status,
    api_auto_resume_uninstall_hooks,
)
from .prefs import api_prefs_get, api_prefs_reset, api_prefs_set
from .hyper_agent import (
    api_hyper_configure, api_hyper_get, api_hyper_get_post, api_hyper_history,
    api_hyper_history_post, api_hyper_list, api_hyper_refine_now,
    api_hyper_rollback, api_hyper_toggle,
)
from .agent_teams import (
    api_agent_teams_delete, api_agent_teams_get, api_agent_teams_list,
    api_agent_teams_save, api_agent_teams_spawn,
)
from .computer_use_lab import (
    api_computer_use_examples, api_computer_use_history, api_computer_use_run,
)
from .memory_lab import (
    api_memory_lab_blocks, api_memory_lab_examples, api_memory_lab_history,
    api_memory_lab_run,
)
from .routines import (
    api_routines_delete, api_routines_get, api_routines_list,
    api_routines_run, api_routines_save,
)
from .advisor_lab import (
    api_advisor_lab_examples, api_advisor_lab_history, api_advisor_lab_models,
    api_advisor_lab_run,
)
from .process_monitor import (
    api_cli_sessions_list, api_kill_idle_claude, api_memory_snapshot,
    api_ports_list, api_process_kill, api_session_open_terminal,
)


def _ai_providers_by_cap(query: dict) -> dict:
    """GET /api/ai-providers/by-capability?cap=embed"""
    cap = (query.get("cap", ["chat"])[0] or "chat").strip()
    return {"capability": cap, "providers": list_providers_by_capability(cap)}
from .logger import log
from .mcp import (
    api_mcp_catalog, api_mcp_health, api_mcp_install, api_mcp_install_prepare,
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
    # v2.43.0 — project-scope config
    api_project_claude_md_get, api_project_claude_md_put,
    api_project_settings_get, api_project_settings_put,
    api_project_settings_local_get, api_project_settings_local_put,
    api_project_skills_list, api_project_commands_list,
    api_project_skill_get, api_project_skill_put, api_project_skill_delete,
    api_project_command_get, api_project_command_put, api_project_command_delete,
)
from .sessions import (
    api_agent_graph, api_project_timeline, api_session_detail,
    api_session_timeline, api_session_tokens, api_sessions_list,
    api_sessions_stats, index_all_sessions,
)
from .skills import get_skill, list_skills, put_skill
from .system import (
    api_backup_diff, api_backups_list, api_bash_history, api_env_config, api_homunculus_projects,
    api_ide_status, api_memory_list, api_metrics_summary, api_model_config,
    api_output_style_delete, api_output_style_save, api_output_styles_list,
    api_plans_list, api_scheduled_tasks, api_statusline_info,
    api_task_delete, api_task_save, api_tasks_list, api_telemetry_summary,
    api_usage_summary, api_usage_project, get_device_info, get_recommended_settings,
    get_system_status,
)


# ───────── 라우트 테이블 ─────────


def _q_truthy(q: dict, key: str) -> bool:
    """v2.43.1 — extract a boolean flag from the dispatcher's parsed query.
    Handles both flat dicts and parse_qs's list-valued mappings."""
    if not isinstance(q, dict):
        return False
    v = q.get(key)
    if isinstance(v, list):
        v = v[0] if v else ""
    return str(v).lower() in ("1", "true", "yes", "on")


ROUTES_GET: dict[str, Callable[[dict], Any]] = {
    "/api/claude-md": lambda q: get_claude_md(),
    "/api/system/status": lambda q: get_system_status(),
    "/api/skills": lambda q: list_skills(force_refresh=_q_truthy(q, "refresh")),
    "/api/agents": lambda q: list_agents(),
    "/api/commands": lambda q: list_commands(force_refresh=_q_truthy(q, "refresh")),
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
    # v2.43.0 — project-scope config (GET)
    "/api/project/claude-md": api_project_claude_md_get,
    "/api/project/settings": api_project_settings_get,
    "/api/project/settings-local": api_project_settings_local_get,
    "/api/project/skill": api_project_skill_get,
    "/api/project/command": api_project_command_get,
    "/api/project/skills/list": api_project_skills_list,
    "/api/project/commands/list": api_project_commands_list,
    "/api/mcp/catalog": lambda q: api_mcp_catalog(),
    "/api/mcp/health": api_mcp_health,
    "/api/plugins/browse": lambda q: api_plugins_browse(),
    "/api/project-agents/roles": lambda q: api_agent_roles(),
    "/api/project-agents/list": api_project_agents_list,
    "/api/subagent/model-choices": lambda q: api_subagent_model_choices(),
    "/api/usage/summary": lambda q: api_usage_summary(),
    "/api/usage/project": api_usage_project,
    "/api/memory/list": api_memory_list,
    "/api/tasks/list": lambda q: api_tasks_list(),
    "/api/team/info": lambda q: api_team_info(),
    "/api/output-styles/list": lambda q: api_output_styles_list(),
    "/api/statusline/info": lambda q: api_statusline_info(),
    "/api/plans/list": lambda q: api_plans_list(),
    "/api/metrics/summary": lambda q: api_metrics_summary(),
    "/api/backups/list": lambda q: api_backups_list(),
    "/api/backups/diff": api_backup_diff,
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
    "/api/slack/config": lambda q: api_slack_config_get(q),
    "/api/run/catalog":      api_run_catalog,
    "/api/run/history":      api_run_history,
    "/api/run/history/get":  api_run_history_get,
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
    "/api/batch/budget": api_batch_budget_get,
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
    "/api/prompt-library/list": api_prompt_library_list,
    "/api/cost-timeline/summary": api_cost_timeline_summary,
    "/api/auto_resume/status": api_auto_resume_status,
    "/api/auto_resume/get": api_auto_resume_get,
    "/api/auto_resume/hook_status": api_auto_resume_hook_status,
    "/api/rtk/status": api_rtk_status,
    "/api/rtk/config": api_rtk_config,
    "/api/rtk/gain": api_rtk_gain,
    "/api/rtk/session": api_rtk_session,
    "/api/toolkit/status": api_toolkit_status,
    "/api/session-replay/list": api_session_replay_list,
    "/api/session-replay/load": api_session_replay_load,
    "/api/event-forwarder/list": api_event_forwarder_list,
    "/api/event-forwarder/meta": api_event_forwarder_meta,
    "/api/learner/patterns": api_learner_patterns,
    "/api/security-scan": api_security_scan,
    "/api/mcp-server/info": api_mcp_server_info,
    "/api/artifacts/list": api_artifacts_list,
    "/api/artifacts/render": api_artifacts_render,
    "/api/prefs/get": api_prefs_get,
    "/api/hyper-agents/list": api_hyper_list,
    "/api/hooks/recent-blocks": api_recent_blocked_hooks,
    "/api/agent-teams/list": api_agent_teams_list,
    "/api/computer-use-lab/examples": api_computer_use_examples,
    "/api/computer-use-lab/history":  api_computer_use_history,
    "/api/memory-lab/examples":       api_memory_lab_examples,
    "/api/memory-lab/history":        api_memory_lab_history,
    "/api/memory-lab/blocks":         api_memory_lab_blocks,
    "/api/routines/list":             api_routines_list,
    "/api/advisor-lab/examples":      api_advisor_lab_examples,
    "/api/advisor-lab/history":       api_advisor_lab_history,
    "/api/advisor-lab/models":        api_advisor_lab_models,
    # v2.44.0 — process / port / memory monitors
    "/api/ports/list":                api_ports_list,
    "/api/sessions-monitor/list":     api_cli_sessions_list,
    "/api/memory/snapshot":           api_memory_snapshot,
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
    # v2.43.0 — project-scope config (POST: delete-style ops)
    "/api/project/skill/delete": api_project_skill_delete,
    "/api/project/command/delete": api_project_command_delete,
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
    "/api/workflows/dry-run": api_workflow_dry_run,
    "/api/workflows/templates/save": api_workflow_template_save,
    "/api/workflows/templates/delete": api_workflow_template_delete,
    "/api/workflows/export": api_workflow_export,
    "/api/workflows/import": api_workflow_import,
    "/api/workflows/schedule/set": api_workflow_schedule_set,
    "/api/workflows/restore": api_workflow_restore,
    "/api/workflows/clone": api_workflow_clone,
    "/api/workflows/run-diff": api_workflow_run_diff,
    "/api/workflows/node-clipboard": api_workflow_node_clipboard,
    "/api/workflows/webhook-secret": api_workflow_webhook_secret,
    "/api/rtk/install": api_rtk_install,
    "/api/rtk/init": api_rtk_init,
    "/api/rtk/uninstall-hook": api_rtk_uninstall_hook,
    "/api/toolkit/ecc/install": api_toolkit_ecc_install,
    "/api/toolkit/ecc/uninstall": api_toolkit_ecc_uninstall,
    "/api/toolkit/ecc/install-plugin": api_toolkit_ecc_install_plugin,
    "/api/toolkit/ecc/uninstall-plugin": api_toolkit_ecc_uninstall_plugin,
    "/api/toolkit/ccb/install": api_toolkit_ccb_install,
    "/api/toolkit/ccb/uninstall": api_toolkit_ccb_uninstall,
    "/api/toolkit/ccb/open": api_toolkit_ccb_open,
    "/api/notify/test": api_notify_test,
    "/api/slack/config/save":  api_slack_config_save,
    "/api/slack/config/clear": api_slack_config_clear,
    "/api/slack/test":         api_slack_test,
    "/api/obsidian/test":      api_obsidian_test,
    "/api/wizard/crew/create":  api_crew_create,
    "/api/run/execute":           api_run_execute,
    "/api/run/favorite/toggle":   api_run_favorite_toggle,
    "/api/run/to-workflow":       api_run_to_workflow,
    "/api/wizard/crew/preview": api_crew_preview,
    "/api/event-forwarder/add": api_event_forwarder_add,
    "/api/event-forwarder/remove": api_event_forwarder_remove,
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
    "/api/batch/budget/set": api_batch_budget_set,
    "/api/api-files/upload": api_files_upload,
    "/api/api-files/delete": api_files_delete,
    "/api/api-files/test": api_files_test,
    "/api/vision-lab/compare": api_vision_compare,
    "/api/model-bench/run": api_model_bench_run,
    "/api/server-tools/run": api_server_tools_run,
    "/api/citations-lab/test": api_citations_test,
    "/api/scaffold/create": api_scaffold_create,
    "/api/embedding-lab/compare": api_embedding_compare,
    "/api/prompt-library/save": api_prompt_library_save,
    "/api/prompt-library/delete": api_prompt_library_delete,
    "/api/prompt-library/duplicate": api_prompt_library_duplicate,
    "/api/prompt-library/to-workflow": api_prompt_library_to_workflow,
    "/api/auto_resume/set": api_auto_resume_set,
    "/api/auto_resume/cancel": api_auto_resume_cancel,
    "/api/auto_resume/install_hooks": api_auto_resume_install_hooks,
    "/api/auto_resume/uninstall_hooks": api_auto_resume_uninstall_hooks,
    "/api/prefs/set": api_prefs_set,
    "/api/prefs/reset": api_prefs_reset,
    "/api/hyper-agents/toggle": api_hyper_toggle,
    "/api/hyper-agents/configure": api_hyper_configure,
    "/api/hyper-agents/refine-now": api_hyper_refine_now,
    "/api/hyper-agents/rollback": api_hyper_rollback,
    "/api/hyper-agents/get": api_hyper_get_post,
    "/api/hyper-agents/history": api_hyper_history_post,
    "/api/agent-teams/save":   api_agent_teams_save,
    "/api/agent-teams/delete": api_agent_teams_delete,
    "/api/agent-teams/spawn":  api_agent_teams_spawn,
    "/api/computer-use-lab/run": api_computer_use_run,
    "/api/memory-lab/run":       api_memory_lab_run,
    "/api/routines/save":        api_routines_save,
    "/api/routines/delete":      api_routines_delete,
    "/api/routines/run":         api_routines_run,
    "/api/advisor-lab/run":      api_advisor_lab_run,
    # v2.44.0 — process / port / memory monitors (mutating)
    "/api/process/kill":                  api_process_kill,
    "/api/sessions-monitor/open-terminal": api_session_open_terminal,
    "/api/memory/kill-idle-claude":       api_kill_idle_claude,
}


ROUTES_PUT: dict[str, Callable[[dict], Any]] = {
    "/api/claude-md": put_claude_md,
    "/api/settings": put_settings,
    "/api/project-agents/save": api_project_agent_save,
    # v2.43.0 — project-scope config (PUT)
    "/api/project/claude-md": api_project_claude_md_put,
    "/api/project/settings": api_project_settings_put,
    "/api/project/settings-local": api_project_settings_local_put,
    "/api/project/skill": api_project_skill_put,
    "/api/project/command": api_project_command_put,
}


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "application/javascript",
    ".mjs": "application/javascript", ".css": "text/css",
    ".json": "application/json", ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2",
    ".map": "application/json",
}

# v2.40.1 — process-wide static cache: {abs_path: (mtime, raw_bytes, gz_or_None)}.
# Invalidates automatically when mtime changes (e.g. after a dist/index.html edit).
_STATIC_CACHE: dict[str, tuple[float, bytes, "bytes | None"]] = {}


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
        # v2.40.1 — mtime-keyed in-memory cache + on-the-fly gzip.
        # dist/index.html is ~1.1 MB raw; gzipped it drops to ~150 KB,
        # so this cuts first-paint network time by ~80% on every reload.
        ct = CONTENT_TYPES.get(fp.suffix.lower(), "application/octet-stream")
        try:
            mtime = fp.stat().st_mtime
        except Exception:
            self.send_response(500); self.end_headers(); return
        entry = _STATIC_CACHE.get(str(fp))
        if not entry or entry[0] != mtime:
            try:
                data = fp.read_bytes()
            except Exception:
                self.send_response(500); self.end_headers(); return
            # gzip pays for itself only on compressible types.
            if ct.startswith(("text/", "application/javascript", "application/json", "image/svg+xml")):
                import gzip
                gz = gzip.compress(data, compresslevel=6)
            else:
                gz = None
            entry = (mtime, data, gz)
            _STATIC_CACHE[str(fp)] = entry
        _, raw_body, gz_body = entry
        accept_enc = self.headers.get("Accept-Encoding", "") or ""
        if gz_body is not None and "gzip" in accept_enc.lower():
            body = gz_body
            content_encoding: str | None = "gzip"
        else:
            body = raw_body
            content_encoding = None
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if content_encoding:
            self.send_header("Content-Encoding", content_encoding)
            self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        self.wfile.write(body)

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
            secret_header = self.headers.get("X-Webhook-Secret", "") or ""
            self._send_json(api_workflow_webhook(m.group(1), self._read_body(), secret_header)); return
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
    (re.compile(r"^/api/hyper-agents/get/([a-z0-9][a-z0-9_-]{0,63})$"), api_hyper_get),
    (re.compile(r"^/api/hyper-agents/history/([a-z0-9][a-z0-9_-]{0,63})$"), api_hyper_history),
    (re.compile(r"^/api/agent-teams/get/(tm-[a-z0-9]{6,16})$"), api_agent_teams_get),
    (re.compile(r"^/api/routines/get/([a-z0-9][a-z0-9_-]{0,63})$"), api_routines_get),
]
