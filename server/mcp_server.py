"""LazyClaude MCP Server (v2.32.0) — stdio JSON-RPC 2.0.

Claude Code 세션에서 `/lazyclaude/<tool>` 로 대시보드 기능을 호출할 수 있게
LazyClaude 를 Model Context Protocol 서버로 노출한다.

전송: stdio (newline-delimited JSON-RPC)
프로토콜: MCP 2024-11-05

등록 방법:
    claude mcp add lazyclaude -- python3 /Users/o/claude-dashboard/scripts/lazyclaude_mcp.py

노출 tools:
- lazyclaude_tabs               : 전체 탭 카탈로그 (id/label/desc)
- lazyclaude_cost_summary       : 비용 타임라인 요약
- lazyclaude_security_scan      : ~/.claude 정적 보안 검사
- lazyclaude_learner_patterns   : 세션 반복 패턴
- lazyclaude_rtk_status         : RTK 설치/훅 상태
- lazyclaude_workflow_templates : 빌트인 워크플로우 템플릿 목록
"""
from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from .version import get_version


# ───────── Tool 정의 ─────────

def _tool_tabs(_args: dict) -> str:
    from .nav_catalog import TAB_CATALOG, TAB_GROUPS, _new_group
    group_names = dict(TAB_GROUPS)
    lines = ["# LazyClaude 탭 카탈로그\n"]
    by_group: dict[str, list] = {gid: [] for gid, _ in TAB_GROUPS}
    for tid, legacy, desc, _kws in TAB_CATALOG:
        ng = _new_group(tid, legacy)
        by_group.setdefault(ng, []).append((tid, desc))
    for gid, glabel in TAB_GROUPS:
        items = by_group.get(gid) or []
        if not items:
            continue
        lines.append(f"\n## {glabel}")
        for tid, desc in items:
            lines.append(f"- **{tid}**: {desc}")
    return "\n".join(lines)


def _tool_cost_summary(_args: dict) -> str:
    from .cost_timeline import api_cost_timeline_summary
    d = api_cost_timeline_summary()
    if not d.get("ok"):
        return f"error: {d.get('error', 'unknown')}"
    total = d.get("totalUsd", 0)
    count = d.get("totalCount", 0)
    by_src = d.get("bySource", [])[:5]
    by_model = d.get("byModel", [])[:5]
    out = [
        f"# LazyClaude Cost Summary",
        f"- Total: **${total:.4f}** across {count} calls",
        "",
        "## Top sources",
    ]
    for s in by_src:
        out.append(f"- {s['source']}: ${s['usd']:.4f} ({s['count']} calls, {s['tokensIn']:,} in / {s['tokensOut']:,} out)")
    out.append("\n## Top models")
    for m in by_model:
        out.append(f"- {m['model']}: ${m['usd']:.4f} ({m['count']} calls)")
    return "\n".join(out)


def _tool_security_scan(_args: dict) -> str:
    from .security_scan import api_security_scan
    d = api_security_scan()
    counts = d.get("counts", {})
    sev = counts.get("bySeverity", {})
    issues = d.get("issues", [])
    total = counts.get("total", 0)
    out = [
        f"# LazyClaude Security Scan",
        f"- Total issues: **{total}**",
        f"- Critical: {sev.get('critical', 0)} · High: {sev.get('high', 0)} · Medium: {sev.get('medium', 0)} · Low: {sev.get('low', 0)} · Info: {sev.get('info', 0)}",
    ]
    if total:
        out.append("\n## Top issues")
        for iss in issues[:10]:
            out.append(f"- [{iss['severity']}] **{iss['title']}** ({iss['category']})")
            if iss.get("detail"):
                out.append(f"  - {iss['detail'][:200]}")
            if iss.get("location"):
                out.append(f"  - 📍 `{iss['location']}`")
    else:
        out.append("\n✅ No issues detected — clean!")
    return "\n".join(out)


def _tool_learner_patterns(_args: dict) -> str:
    from .learner import api_learner_patterns
    d = api_learner_patterns()
    if (d.get("sessions") or 0) == 0:
        return "No recent sessions found."
    stats = d.get("stats", {})
    top_tools = stats.get("topTools", [])[:8]
    patterns = d.get("patterns", [])[:10]
    out = [
        f"# LazyClaude Learner",
        f"- Sessions scanned: {d['sessions']} (last {d['days']} days)",
        f"- Cumulative tokens: {stats.get('totalTokens', 0):,}",
        "",
        "## Top tools",
    ]
    for t in top_tools:
        out.append(f"- {t['name']}: {t['count']}")
    out.append("\n## Patterns")
    for p in patterns:
        out.append(f"- [{p['type']}] {p['title']} ({p.get('count', 0)}×)")
    return "\n".join(out)


def _tool_rtk_status(_args: dict) -> str:
    from .rtk_lab import api_rtk_status
    d = api_rtk_status()
    installed = "✅ installed" if d.get("installed") else "❌ not installed"
    hook = "✅ active" if d.get("hookInstalled") else "❌ inactive"
    out = [
        f"# RTK Optimizer Status",
        f"- Installed: {installed} {d.get('version') or ''}",
        f"- Hook: {hook}",
        f"- Binary: `{d.get('binPath') or '(not on PATH)'}`",
        f"- Config: `{d.get('configPath')}` ({'exists' if d.get('configExists') else 'not yet'})",
        f"- Guide: {d.get('guide')}",
    ]
    return "\n".join(out)


def _tool_workflow_templates(_args: dict) -> str:
    from .workflows import BUILTIN_TEMPLATES
    out = ["# LazyClaude Built-in Workflow Templates\n"]
    for t in BUILTIN_TEMPLATES:
        out.append(f"## {t.get('icon', '')} {t['name']} (`{t['id']}`)")
        out.append(f"- Category: {t.get('category', 'general')}")
        out.append(f"- Nodes: {len(t.get('nodes', []))} · Edges: {len(t.get('edges', []))}")
        if t.get("repeat", {}).get("enabled"):
            out.append(f"- Repeat: maxIterations={t['repeat']['maxIterations']}, feedbackNode={t['repeat'].get('feedbackNodeId', '—')}")
        out.append(f"- {t.get('description', '')}")
        out.append("")
    return "\n".join(out)


# ───────── MCP Tool 카탈로그 ─────────

TOOLS = [
    {
        "name": "lazyclaude_tabs",
        "description": "List all LazyClaude dashboard tabs grouped by category (Learn/Main/Build/Playground/Config/Observe) with descriptions.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "_handler": _tool_tabs,
    },
    {
        "name": "lazyclaude_cost_summary",
        "description": "Summarize LazyClaude unified cost timeline — total USD, top sources (promptCache/thinkingLab/workflows/...), top models.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "_handler": _tool_cost_summary,
    },
    {
        "name": "lazyclaude_security_scan",
        "description": "Run a static security scan over ~/.claude (settings, CLAUDE.md, hooks, agents, MCP) for secret leaks, risky hooks, over-privileged permissions. 100% local, no AI.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "_handler": _tool_security_scan,
    },
    {
        "name": "lazyclaude_learner_patterns",
        "description": "Extract repeated tool sequences and prompts from recent Claude Code sessions — pure statistics (no AI).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "_handler": _tool_learner_patterns,
    },
    {
        "name": "lazyclaude_rtk_status",
        "description": "Report RTK (Rust Token Killer) install + hook status from the dashboard.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "_handler": _tool_rtk_status,
    },
    {
        "name": "lazyclaude_workflow_templates",
        "description": "List LazyClaude built-in workflow templates (autopilot, ralph, ultrawork, deep-interview, team-sprint, etc.) with node/edge counts.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "_handler": _tool_workflow_templates,
    },
]

_BY_NAME = {t["name"]: t for t in TOOLS}


# ───────── JSON-RPC 디스패치 ─────────

def _reply(resp: dict) -> None:
    sys.stdout.write(json.dumps(resp) + "\n")
    sys.stdout.flush()


def _handle(msg: dict) -> dict | None:
    msg_id = msg.get("id")
    method = msg.get("method", "")
    params = msg.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "lazyclaude", "version": get_version()},
            },
        }
    if method == "notifications/initialized":
        return None  # notification — no response
    if method == "tools/list":
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "result": {"tools": [{k: v for k, v in t.items() if not k.startswith("_")} for t in TOOLS]},
        }
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = _BY_NAME.get(name)
        if not tool:
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32601, "message": f"tool not found: {name}"}}
        try:
            text = tool["_handler"](args)
        except Exception as e:
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32000, "message": f"tool error: {e}", "data": traceback.format_exc()[:500]}}
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "result": {"content": [{"type": "text", "text": text}], "isError": False},
        }
    if method == "shutdown" or method == "exit":
        return {"jsonrpc": "2.0", "id": msg_id, "result": None}
    # Unknown method
    if msg_id is not None:
        return {"jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32601, "message": f"method not found: {method}"}}
    return None


def api_mcp_server_info(_q: dict | None = None) -> dict:
    """대시보드 UI 용 — LazyClaude MCP 서버 진입점 스크립트 경로 + 노출 도구 목록."""
    from pathlib import Path
    script = Path(__file__).resolve().parent.parent / "scripts" / "lazyclaude_mcp.py"
    return {
        "ok": True,
        "path": str(script),
        "exists": script.exists(),
        "tools": [
            {"name": t["name"], "description": t["description"]}
            for t in TOOLS
        ],
        "protocolVersion": "2024-11-05",
        "version": get_version(),
    }


def run() -> None:
    """stdin 에서 newline-delimited JSON-RPC 메시지를 읽어 처리."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as e:
            _reply({"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": f"parse error: {e}"}})
            continue
        resp = _handle(msg)
        if resp is not None:
            _reply(resp)
        if msg.get("method") in ("shutdown", "exit"):
            break
