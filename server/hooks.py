"""훅 설정 — 사용자 settings.json 의 hooks + 플러그인 마켓플레이스 hooks.json.

- get_hooks: 사용자+플러그인 훅 평탄화 + 권한/카운트 집계 (/api/hooks)
- _scan_plugin_hooks: 두 레이아웃 지원, (pluginKey, groupIdx, subIdx) 포함
- api_plugin_hook_update: 플러그인 훅 수정/삭제 (update/delete)
- _plugin_hooks_file: pluginKey → hooks.json 경로 해석
- recent_blocked_hooks: 세션 jsonl 에서 hook block 이벤트 빈도 mining (v2.40.4)
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from threading import Lock
from typing import Optional

from .claude_md import get_settings
from .config import PLUGINS_DIR, PROJECTS_DIR
from .utils import _safe_read, _safe_write


# 30s mtime-aware cache for plugin hook scan — directory tree walk +
# JSON parsing is otherwise repeated on every /api/hooks call.
_HOOKS_CACHE: list | None = None
_HOOKS_CACHE_AT: float = 0.0
_HOOKS_DIR_MTIME: float = 0.0


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
    global _HOOKS_CACHE, _HOOKS_CACHE_AT, _HOOKS_DIR_MTIME
    out: list = []
    if not PLUGINS_DIR.exists():
        return out
    markets_dir = PLUGINS_DIR / "marketplaces"
    if not markets_dir.exists():
        return out
    # 30s TTL + mtime guard — invalidate when the marketplaces dir changes.
    try:
        dir_mtime = markets_dir.stat().st_mtime
    except OSError:
        dir_mtime = 0.0
    now = time.time()
    if (
        _HOOKS_CACHE is not None
        and dir_mtime == _HOOKS_DIR_MTIME
        and (now - _HOOKS_CACHE_AT) < 30.0
    ):
        return _HOOKS_CACHE
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
                        # v2.40.3 — propagate group-level identity (id / name /
                        # description) onto each sub-hook so the dashboard card
                        # surfaces the same name Claude Code's `/hooks` shows.
                        for k in ("id", "name", "description"):
                            if k not in entry and item.get(k):
                                entry[k] = item.get(k)
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
    _HOOKS_CACHE = out
    _HOOKS_CACHE_AT = now
    _HOOKS_DIR_MTIME = dir_mtime
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
                        # v2.40.3 — same identity propagation as plugin hooks.
                        for k in ("id", "name", "description"):
                            if k not in entry and item.get(k):
                                entry[k] = item.get(k)
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


# ───────── v2.40.4 — Hook block mining ─────────

# Match Claude Code's hook id shape (event:scope:name) anywhere it appears
# verbatim in transcript content. Keeping the regex strict avoids false
# positives on unrelated colon-separated identifiers.
_HOOK_ID_RE = re.compile(r"\b(pre|post|session|notification|user|stop|sub):[a-z][a-z0-9_-]*(?::[a-z][a-z0-9_-]*)+\b")
# Anchor lines that signal a hook block. Line-based scan keeps us robust to the
# nested escaping inside jsonl tool_result content (no JSON parser required).
_HOOK_BLOCK_MARKERS = (
    "hook returned blocking error",
    "hook blocking error",
    "PreToolUse:",
    "PostToolUse:",
    "blocked by hook",
)


def _scan_jsonl_for_hook_blocks(file: Path) -> list[tuple[str, int]]:
    """Scan one jsonl transcript for hook block events.

    Returns a list of (hook_id, mtime_ms) — one tuple per blocking event.
    The same hook id appearing in N separate lines counts N times so the
    aggregate can rank by recency × frequency.
    """
    text = _safe_read(file, limit=1_500_000) or ""
    if not text:
        return []
    try:
        mt_ms = int(file.stat().st_mtime * 1000)
    except Exception:
        mt_ms = 0
    out: list[tuple[str, int]] = []
    for line in text.split("\n"):
        if not any(m in line for m in _HOOK_BLOCK_MARKERS):
            continue
        for hid in _HOOK_ID_RE.findall(line):
            # findall on a grouped pattern returns the first group only — re-run
            # with explicit fullmatch to recover the full id.
            pass
        for m in _HOOK_ID_RE.finditer(line):
            out.append((m.group(0), mt_ms))
    return out


# In-process cache for recent_blocked_hooks. The bare scan walks up to
# 60 jsonl files (~90 MB total on a power user's machine) and takes ~2 s,
# which made the Hooks tab feel laggy on every visit. We cache by the
# fingerprint of the (top-of-mtime, max_files, top_n) tuple, refreshing
# only when a newer transcript appears or the 5-minute TTL expires.
_RECENT_BLOCKS_TTL_S = 300
_recent_blocks_cache: dict = {"key": None, "ts": 0.0, "value": None}
_recent_blocks_lock = Lock()


def _recent_blocks_fingerprint(max_files: int, top_n: int) -> tuple:
    """Cheap fingerprint — only stat()s the newest jsonl, not all 60.
    A new hook-block event always lands in the most-recently-touched
    transcript, so a single mtime is enough to invalidate."""
    if not PROJECTS_DIR.exists():
        return ("none", 0.0, max_files, top_n)
    newest = 0.0
    for proj in PROJECTS_DIR.iterdir():
        if not proj.is_dir():
            continue
        for jl in proj.glob("*.jsonl"):
            try:
                m = jl.stat().st_mtime
                if m > newest:
                    newest = m
            except Exception:
                continue
    return ("ok", newest, max_files, top_n)


def _compute_recent_blocked_hooks(max_files: int, top_n: int) -> dict:
    if not PROJECTS_DIR.exists():
        return {"items": [], "scanned": 0, "totalEvents": 0}
    files: list[tuple[float, Path]] = []
    for proj in PROJECTS_DIR.iterdir():
        if not proj.is_dir():
            continue
        for jl in proj.glob("*.jsonl"):
            try:
                files.append((jl.stat().st_mtime, jl))
            except Exception:
                continue
    files.sort(key=lambda x: -x[0])
    files = files[:max_files]

    bucket: dict[str, dict] = {}
    total = 0
    for _, jl in files:
        events = _scan_jsonl_for_hook_blocks(jl)
        for hid, mt in events:
            slot = bucket.setdefault(hid, {"id": hid, "count": 0, "lastSeen": 0})
            slot["count"] += 1
            if mt > slot["lastSeen"]:
                slot["lastSeen"] = mt
            total += 1
    items = sorted(bucket.values(), key=lambda r: (-r["count"], -r["lastSeen"]))[:top_n]
    return {"items": items, "scanned": len(files), "totalEvents": total}


def recent_blocked_hooks(*, max_files: int = 60, top_n: int = 20,
                         force_refresh: bool = False) -> dict:
    """Aggregate the most recent hook-block events across recent session
    transcripts. Returns a frequency-ranked list with the latest mtime per id.

    Cached for ``_RECENT_BLOCKS_TTL_S`` (5 min) and invalidated when a
    newer jsonl appears. Pass ``force_refresh=True`` to bypass the cache.

    Output shape::

        {
          "items": [
            {"id": "pre:edit-write:gateguard-fact-force",
             "count": 14, "lastSeen": 1777270000000},
             ...
          ],
          "scanned": <files scanned>,
          "totalEvents": <sum of counts>,
          "cached": <bool>
        }
    """
    fp = _recent_blocks_fingerprint(max_files, top_n)
    now = time.time()
    if not force_refresh:
        with _recent_blocks_lock:
            if (_recent_blocks_cache["key"] == fp
                    and _recent_blocks_cache["value"] is not None
                    and (now - _recent_blocks_cache["ts"]) < _RECENT_BLOCKS_TTL_S):
                v = dict(_recent_blocks_cache["value"])
                v["cached"] = True
                return v
    value = _compute_recent_blocked_hooks(max_files, top_n)
    with _recent_blocks_lock:
        _recent_blocks_cache["key"] = fp
        _recent_blocks_cache["ts"] = now
        _recent_blocks_cache["value"] = value
    out = dict(value)
    out["cached"] = False
    return out


def api_recent_blocked_hooks(query: dict) -> dict:
    force = False
    if isinstance(query, dict):
        v = query.get("refresh")
        if isinstance(v, list):
            v = v[0] if v else ""
        if str(v).lower() in ("1", "true", "yes"):
            force = True
    return {"ok": True, **recent_blocked_hooks(force_refresh=force)}
