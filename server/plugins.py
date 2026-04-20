"""플러그인 / 마켓플레이스 관리.

- api_plugins_browse : 설치된 모든 마켓플레이스의 plugins 목록 + 상태
- api_plugin_toggle  : settings.json 의 enabledPlugins 토글
- list_plugins_api   : installed_plugins.json 기반 설치 리스트
- list_marketplaces  : known_marketplaces.json 기반 (읽기)
- api_marketplace_list/add/remove : settings.extraKnownMarketplaces 편집
"""
from __future__ import annotations

import json
import re

from .claude_md import get_settings, put_settings
from .config import INSTALLED_PLUGINS_JSON, KNOWN_MARKETPLACES_JSON, PLUGINS_DIR
from .translations import _load_translation_cache
from .utils import _safe_read


def api_plugins_browse() -> dict:
    """설치된 마켓플레이스의 모든 plugins 리스트 + 설치/활성 상태."""
    markets_dir = PLUGINS_DIR / "marketplaces"
    if not markets_dir.exists():
        return {"plugins": []}
    settings = get_settings()
    enabled = settings.get("enabledPlugins", {}) if isinstance(settings, dict) else {}

    installed_json: dict = {}
    if INSTALLED_PLUGINS_JSON.exists():
        try:
            installed_json = json.loads(_safe_read(INSTALLED_PLUGINS_JSON))
        except Exception:
            installed_json = {}
    installed_plugins_map = installed_json.get("plugins", {}) if isinstance(installed_json, dict) else {}

    out: list = []
    for market in sorted(markets_dir.iterdir()):
        if not market.is_dir() or market.name.endswith(".bak"):
            continue
        plugins_root = market / "plugins"
        if not plugins_root.exists():
            continue
        # marketplace.json 읽기 시도
        mp_meta: dict = {}
        for candidate in ("marketplace.json", ".claude-plugin/marketplace.json"):
            f = market / candidate
            if f.exists():
                try:
                    mp_meta = json.loads(_safe_read(f))
                    break
                except Exception:
                    pass

        mp_plugins: dict = {}
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
            agents_n = len(list((plugin_dir / "agents").glob("*.md"))) if (plugin_dir / "agents").exists() else 0
            skills_n = sum(1 for x in (plugin_dir / "skills").iterdir() if x.is_dir()) if (plugin_dir / "skills").exists() else 0
            commands_n = len(list((plugin_dir / "commands").glob("*.md"))) if (plugin_dir / "commands").exists() else 0
            hooks_n = len(list((plugin_dir / "hooks").iterdir())) if (plugin_dir / "hooks").exists() else 0
            out.append({
                "id": composite_id,
                "name": name,
                "marketplace": market.name,
                "description": desc,
                "author": (mp_entry.get("author") or {}).get("name")
                    if isinstance(mp_entry.get("author"), dict) else mp_entry.get("author", ""),
                "tags": mp_entry.get("tags", []) if isinstance(mp_entry.get("tags"), list) else [],
                "version": mp_entry.get("version", ""),
                "installed": is_installed,
                "enabled": is_enabled,
                "counts": {"agents": agents_n, "skills": skills_n, "commands": commands_n, "hooks": hooks_n},
            })
    cache = _load_translation_cache()
    for p in out:
        p["descriptionKo"] = cache.get(f"plugin:{p['id']}", "")
    return {
        "plugins": out,
        "marketplaces": len({m.name for m in markets_dir.iterdir() if m.is_dir() and not m.name.endswith('.bak')}),
    }


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
    out: list = []
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


def api_marketplace_list() -> dict:
    """known_marketplaces.json + settings.extraKnownMarketplaces."""
    km: dict = {}
    if KNOWN_MARKETPLACES_JSON.exists():
        try:
            km = json.loads(_safe_read(KNOWN_MARKETPLACES_JSON))
        except Exception:
            km = {}
    s = get_settings()
    extra = (s.get("extraKnownMarketplaces") if isinstance(s, dict) else None) or {}
    out: list = []
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
