"""Claude Code 스킬 (`~/.claude/skills/*`) + 플러그인 마켓플레이스 스킬.

- list_skills: 사용자 스킬 + 플러그인 스킬 + 번역 주입
- get_skill / put_skill: 단건 조회/편집 (플러그인 스킬은 read-only)
- _scan_plugin_skills / _resolve_skill_path: 플러그인 두 레이아웃 지원
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .claude_md import get_settings
from .config import PLUGINS_DIR, SKILLS_DIR
from .translations import _load_translation_cache
from .utils import _parse_frontmatter, _safe_read, _safe_write, _strip_frontmatter


def _scan_plugin_skills() -> list:
    """활성·비활성 모든 마켓플레이스 플러그인의 스킬 수집."""
    out: list = []
    if not PLUGINS_DIR.exists():
        return out
    markets_dir = PLUGINS_DIR / "marketplaces"
    if not markets_dir.exists():
        return out
    seen: set[str] = set()
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
    out: list = []
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
            meta: dict = {}
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
