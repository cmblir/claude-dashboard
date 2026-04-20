"""Claude Code 에이전트 (전역 + 플러그인 + 빌트인).

- list_agents: 전역·플러그인·빌트인 통합 + 번역/활성 여부 주입
- get/put_agent: 단건 조회·편집
- api_agent_create/delete: 전역 에이전트 생성/삭제
- _scan_plugin_agents: 플러그인 두 레이아웃 스캔
- _resolve_agent_path: id → 실제 파일 경로

프로젝트별 에이전트·서브에이전트 모델 패치는 projects 단계에서 병합한다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .claude_md import get_settings
from .config import AGENTS_DIR, PLUGINS_DIR
from .translations import _load_translation_cache
from .utils import (
    _parse_frontmatter,
    _parse_tools_field,
    _safe_read,
    _safe_write,
    _strip_frontmatter,
)


# ───────── 빌트인 에이전트 (Claude Code 에 내장되어 파일 없음) ─────────

_BUILTIN_AGENTS = [
    {"id": "general-purpose", "name": "general-purpose",
     "description": "범용 에이전트 — 복잡한 질의 조사 / 코드 검색 / 멀티스텝 작업.",
     "model": "inherit", "tools": ["*"]},
    {"id": "Explore", "name": "Explore",
     "description": "코드베이스 탐색 전용 고속 에이전트.",
     "model": "haiku", "tools": ["Read", "Grep", "Glob", "WebFetch"]},
    {"id": "Plan", "name": "Plan",
     "description": "구현 전략 수립 — 단계별 플랜과 핵심 파일 식별.",
     "model": "sonnet", "tools": ["Read", "Grep", "Glob"]},
    {"id": "statusline-setup", "name": "statusline-setup",
     "description": "Claude Code 상태라인 커스터마이징.",
     "model": "haiku", "tools": ["Read", "Edit"]},
]


def _scan_plugin_agents() -> list:
    """활성 마켓플레이스의 에이전트 수집.

    두 레이아웃 지원:
      A) <market>/plugins/<plugin>/agents/*.md → id=market:plugin:stem
      B) <market>/agents/*.md (ecc 스타일)    → id=market:stem
    """
    out: list = []
    if not PLUGINS_DIR.exists():
        return out
    markets_dir = PLUGINS_DIR / "marketplaces"
    if not markets_dir.exists():
        return out

    seen_paths: set[str] = set()

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

        # Layout B
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
    agents: list = []

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

    # 빌트인 에이전트
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
        src = a.get("source", "")
        if "/" in src:
            market, plugin = src.split("/", 1)
            key = f"{plugin}@{market}"
        else:
            # ecc 스타일: market 전체가 하나의 플러그인 (composite_id = <market>@<market>)
            key = f"{src}@{src}"
        a["pluginEnabled"] = bool(enabled_map.get(key, False))
        a["pluginKey"] = key

    # counts by scope
    counts = {"global": 0, "plugin": 0, "builtin": 0}
    for a in agents:
        counts[a["scope"]] = counts.get(a["scope"], 0) + 1
    counts["pluginEnabled"] = sum(
        1 for a in agents if a.get("scope") == "plugin" and a.get("pluginEnabled")
    )

    return {"agents": agents, "counts": counts}


def _resolve_agent_path(agent_id: str) -> Optional[Path]:
    """에이전트 id → 실제 .md 파일 경로.

    지원 형식:
      1. 전역: `agent-name` → ~/.claude/agents/<name>.md
      2. 3-part 플러그인 (대시보드 내부): `market:plugin:stem` → .../<market>/plugins/<plugin>/agents/<stem>.md
      3. 2-part 플러그인 (Claude Code 호출 형식): `market:plugin` → 동일 market/plugin 의 첫 agent .md (또는 동명)
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
                markets_dir / market / "agents" / f"{second}.md",
            ]
            for p in candidates:
                if p.exists():
                    return p
            nested = markets_dir / market / "plugins" / second / "agents"
            if nested.exists():
                for p in sorted(nested.glob("*.md")):
                    return p
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
        return {"ok": False, "error": "이미 존재 — overwrite=true 로 덮어쓰기"}
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
    for b in _BUILTIN_AGENTS:
        if b["id"] == agent_id:
            return {"ok": False, "error": "builtin agent 는 삭제할 수 없습니다"}
    if ":" in agent_id:
        return {"ok": False, "error": "플러그인 에이전트는 마켓플레이스에서 관리 — 삭제는 플러그인 비활성화로"}
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
