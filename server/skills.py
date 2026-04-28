"""Claude Code 스킬 (`~/.claude/skills/*`) + 플러그인 마켓플레이스 스킬.

- list_skills: 사용자 스킬 + 플러그인 스킬 + 번역 주입
- get_skill / put_skill: 단건 조회/편집 (플러그인 스킬은 read-only)
- _scan_plugin_skills / _resolve_skill_path: 플러그인 두 레이아웃 지원
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from threading import Lock
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


# v2.43.1 — TTL+mtime cache. The bare scan walks 485 SKILL.md files across
# user + every installed plugin marketplace and takes ~800 ms on a power
# user's machine. Invalidate on the newest top-level mtime so a freshly
# edited skill shows up immediately.
_SKILLS_TTL_S = 60
_skills_cache: dict = {"key": None, "ts": 0.0, "value": None}
_skills_lock = Lock()


def _skills_fingerprint() -> tuple:
    """Cheap fingerprint — only stat the top-level dirs, not every SKILL.md.
    A new/edited skill always lands inside one of these, so its parent's
    mtime bumps too on filesystem-level change."""
    parts: list[float] = []
    try:
        if SKILLS_DIR.exists():
            parts.append(SKILLS_DIR.stat().st_mtime)
            for p in SKILLS_DIR.iterdir():
                try:
                    parts.append(p.stat().st_mtime)
                except Exception:
                    continue
    except Exception:
        pass
    try:
        markets = PLUGINS_DIR / "marketplaces"
        if markets.exists():
            parts.append(markets.stat().st_mtime)
            for m in markets.iterdir():
                try:
                    parts.append(m.stat().st_mtime)
                except Exception:
                    continue
    except Exception:
        pass
    return tuple(round(x, 3) for x in parts)


def list_skills(force_refresh: bool = False) -> list:
    """Cached wrapper. Pass ``force_refresh=True`` (or hit the endpoint with
    ``?refresh=1``) to bypass the cache."""
    fp = _skills_fingerprint()
    now = time.time()
    if not force_refresh:
        with _skills_lock:
            if (_skills_cache["key"] == fp
                    and _skills_cache["value"] is not None
                    and (now - _skills_cache["ts"]) < _SKILLS_TTL_S):
                return _skills_cache["value"]
    value = _list_skills_uncached()
    with _skills_lock:
        _skills_cache["key"] = fp
        _skills_cache["ts"] = now
        _skills_cache["value"] = value
    return value


def _list_skills_uncached() -> list:
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

    # 번역 주입 (ko/en/zh)
    cache = _load_translation_cache()
    for s in out:
        sid = s["id"]
        s["descriptionKo"] = cache.get(f"skill:{sid}", "")
        s["descriptionEn"] = cache.get(f"en:skill:{sid}", "")
        s["descriptionZh"] = cache.get(f"zh:skill:{sid}", "")
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
        from .errors import err
        return err("skill_plugin_readonly")
    if not re.match(r"^[a-zA-Z0-9_-]+$", skill_id or ""):
        return {"ok": False, "error": "invalid skill id"}
    raw = body.get("raw", "") if isinstance(body, dict) else ""
    if not isinstance(raw, str):
        return {"ok": False, "error": "raw must be string"}
    p = SKILLS_DIR / skill_id / "SKILL.md"
    ok = _safe_write(p, raw)
    return {"ok": ok}
