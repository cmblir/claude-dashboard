"""훅 설정 — 사용자 settings.json 의 hooks + 플러그인 마켓플레이스 hooks.json.

- get_hooks: 사용자+플러그인 훅 평탄화 + 권한/카운트 집계 (/api/hooks)
- _scan_plugin_hooks: 두 레이아웃 지원, (pluginKey, groupIdx, subIdx) 포함
- api_plugin_hook_update: 플러그인 훅 수정/삭제 (update/delete)
- _plugin_hooks_file: pluginKey → hooks.json 경로 해석
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .claude_md import get_settings
from .config import PLUGINS_DIR
from .utils import _safe_read, _safe_write


def _plugin_hooks_file(plugin_key: str) -> Optional[Path]:
    """pluginKey ('<plugin>@<market>') → hooks.json 경로 (없으면 None)."""
    if "@" not in (plugin_key or ""):
        return None
    plugin, market = plugin_key.split("@", 1)
    if not all(re.match(r"^[a-zA-Z0-9_.-]+$", x or "") for x in (plugin, market)):
        return None
    markets_dir = PLUGINS_DIR / "marketplaces"
    candidates = [
        markets_dir / market / "plugins" / plugin / "hooks" / "hooks.json",
        markets_dir / market / "hooks" / "hooks.json" if plugin == market else None,
    ]
    for c in candidates:
        if c and c.exists():
            return c
    return None


def _scan_plugin_hooks() -> list:
    """플러그인 마켓플레이스의 hooks/hooks.json 파싱 → 평탄화된 훅 리스트.

    각 항목에 (pluginKey, event, groupIdx, subIdx) 인덱스 포함 → 수정/삭제 가능.
    """
    out: list = []
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
            for gi, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                sub = item.get("hooks")
                matcher = item.get("matcher")
                if isinstance(sub, list) and sub:
                    for si, sh in enumerate(sub):
                        entry = {
                            "event": event, "scope": "plugin", "source": source_label,
                            "pluginKey": plugin_key, "pluginEnabled": enabled,
                            "groupIdx": gi, "subIdx": si,
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
                        "event": event, "scope": "plugin", "source": source_label,
                        "pluginKey": plugin_key, "pluginEnabled": enabled,
                        "groupIdx": gi, "subIdx": -1,
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


def api_plugin_hook_update(body: dict) -> dict:
    """플러그인 훅 수정/삭제.

    body: { pluginKey, event, groupIdx, subIdx, op:'update'|'delete', payload? }
    payload(update 시): { matcher, type, command, timeout, event(이동) }
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    pk = body.get("pluginKey", "")
    event = body.get("event", "")
    gi = body.get("groupIdx")
    si = body.get("subIdx")
    op = body.get("op", "update")
    payload = body.get("payload") or {}
    hf = _plugin_hooks_file(pk)
    if not hf:
        from .errors import err
        return err("hook_file_not_found")
    try:
        raw = _safe_read(hf)
        data = json.loads(raw) if raw else {}
    except Exception as e:
        from .errors import err
        return err("hook_parse_error", detail=str(e))
    if not isinstance(data, dict):
        data = {}
    hooks_obj = data.setdefault("hooks", {})
    items = hooks_obj.get(event)
    if not isinstance(items, list) or not (0 <= int(gi) < len(items)):
        return err("hook_index_error", detail="groupIdx")
    group = items[int(gi)]
    si = int(si) if si is not None else -1

    if op == "delete":
        if si >= 0 and isinstance(group, dict) and isinstance(group.get("hooks"), list):
            sub = group["hooks"]
            if si >= len(sub):
                return err("hook_index_error", detail="subIdx")
            sub.pop(si)
            if not sub:
                items.pop(int(gi))
        else:
            items.pop(int(gi))
        if not items:
            hooks_obj.pop(event, None)
    elif op == "update":
        new_event = payload.get("event") or event
        new_sub = {
            "type": payload.get("type", "command"),
            "command": payload.get("command", ""),
        }
        if payload.get("timeout"):
            try:
                new_sub["timeout"] = int(payload["timeout"])
            except Exception:
                pass
        # 기존 항목의 id / description 등 보존
        if (si >= 0 and isinstance(group, dict)
                and isinstance(group.get("hooks"), list) and si < len(group["hooks"])):
            old = group["hooks"][si]
            if isinstance(old, dict):
                for k in ("id", "description"):
                    if k in old and k not in new_sub:
                        new_sub[k] = old[k]
        new_matcher = payload.get("matcher")
        # 동일 이벤트 내 수정
        if new_event == event:
            if si >= 0 and isinstance(group, dict) and isinstance(group.get("hooks"), list):
                if si >= len(group["hooks"]):
                    return err("hook_index_error", detail="subIdx")
                if new_matcher is not None:
                    group["matcher"] = new_matcher
                group["hooks"][si] = new_sub
            else:
                items[int(gi)] = (
                    {"matcher": new_matcher, "hooks": [new_sub]}
                    if new_matcher else {**new_sub, "hooks": [new_sub]}
                )
        else:
            # 이벤트 이동: 기존에서 빼고 새 이벤트에 추가
            if si >= 0 and isinstance(group, dict) and isinstance(group.get("hooks"), list):
                group["hooks"].pop(si)
                if not group["hooks"]:
                    items.pop(int(gi))
            else:
                items.pop(int(gi))
            if not items:
                hooks_obj.pop(event, None)
            target = hooks_obj.setdefault(new_event, [])
            new_group = (
                {"matcher": new_matcher, "hooks": [new_sub]}
                if new_matcher else {"hooks": [new_sub]}
            )
            target.append(new_group)
    else:
        return {"ok": False, "error": f"unknown op: {op}"}

    try:
        _safe_write(hf, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    except Exception as e:
        return err("hook_save_error", detail=str(e))
    return {"ok": True}


def get_hooks() -> dict:
    s = get_settings()
    permissions = s.get("permissions") or {"allow": [], "deny": []}
    if not isinstance(permissions, dict):
        permissions = {"allow": [], "deny": []}
    permissions.setdefault("allow", [])
    permissions.setdefault("deny", [])

    hooks_out: list = []
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
