"""Event Forwarder (v2.29.0) — Claude Code hooks → 외부 HTTP POST.

사용자가 UI 에서 "이벤트 타입 + URL" 을 지정하면 `~/.claude/settings.json` 의
hooks 섹션에 `curl -s -X POST <url> --data-binary @-` 타입 엔트리를 추가한다.
이 훅은 Claude Code 에서 해당 이벤트 발생 시 stdin 으로 이벤트 JSON 을
받아 외부 endpoint 로 그대로 포워딩한다.

보안:
- URL 은 https-only + 호스트 화이트리스트 (SSRF 방지)
  - webhook.site, hooks.slack.com, discord.com, discordapp.com,
    requestbin.com, pipedream.net, n8n.cloud, zapier.com,
    api.github.com, maker.ifttt.com
  - 사용자가 명시적으로 custom 호스트 추가 가능 (~/.claude-dashboard-config.json)
- settings.json 수정은 백업 자동 생성 (rtk_lab 패턴 재사용)
- forwarder 는 매 커맨드마다 고유 `lazyclaude-forwarder` 마커를 command 에 포함 →
  list/remove 시 우리 엔트리만 식별 가능
"""
from __future__ import annotations

import json
import re
import shlex
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .logger import log
from .utils import _safe_write

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

# Claude Code hook 이벤트 타입 (https://docs.anthropic.com/en/docs/claude-code/hooks)
_EVENT_TYPES = {
    "PreToolUse", "PostToolUse", "UserPromptSubmit", "Notification",
    "Stop", "SubagentStop", "PreCompact", "SessionStart", "SessionEnd",
}

# SSRF 방어용 호스트 화이트리스트 (notify.py 와 같은 패턴, 범위 확장)
_ALLOWED_HOSTS = {
    "hooks.slack.com", "discord.com", "discordapp.com",
    "webhook.site", "requestbin.com", "requestcatcher.com",
    "pipedream.net", "zapier.com", "api.github.com",
    "maker.ifttt.com", "n8n.cloud",
}

_MARKER = "__lazyclaude_forwarder__"


def _validate_url(url: str) -> tuple[bool, str]:
    try:
        p = urlparse(url)
    except Exception:
        return False, "invalid url"
    if p.scheme != "https":
        return False, "https only"
    if not p.hostname:
        return False, "missing host"
    if p.hostname not in _ALLOWED_HOSTS:
        # subdomain.webhook.site 같은 케이스 허용
        root = ".".join(p.hostname.split(".")[-2:])
        if root not in _ALLOWED_HOSTS:
            return False, f"host '{p.hostname}' not in whitelist"
    if len(url) > 500:
        return False, "url too long"
    # shell escape 단순화 위해 single quote/backslash/$/` 문자 금지
    if any(ch in url for ch in ("'", '"', "\\", "$", "`", "\n", "\r")):
        return False, "url contains forbidden shell chars"
    return True, ""


def _load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("settings.json parse failed: %s", e)
        return {}


def _write_settings(data: dict) -> tuple[bool, str]:
    try:
        text = SETTINGS_PATH.read_text(encoding="utf-8") if SETTINGS_PATH.exists() else "{}"
    except Exception as e:
        return False, f"read failed: {e}"
    ts = int(time.time())
    backup = SETTINGS_PATH.with_suffix(f".json.bak.{ts}")
    try:
        backup.write_text(text, encoding="utf-8")
    except Exception as e:
        return False, f"backup failed: {e}"
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ok = _safe_write(SETTINGS_PATH, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return ok, str(backup) if ok else "write failed"


def _build_command(url: str) -> str:
    """이벤트 JSON 을 stdin 으로 받아 지정 URL 로 POST.

    URL 은 `_validate_url` 에서 `'` `"` `\\` `$` ``` `` 등 shell metacharacter 가
    금지되어 있으므로 단순 single-quote 래핑으로 안전하게 escape 가능.
    정규식 `_CMD_URL_RE` 는 이 single-quote 래핑 포맷을 전제로 URL 추출.
    """
    return (
        "curl -sS --max-time 10 -X POST "
        "-H 'Content-Type: application/json' "
        "--data-binary @- "
        f"'{url}' "
        f"# {_MARKER}"
    )


# URL 추출: `--data-binary @- '<URL>' # marker` 바로 그 부분만 매칭해
# `-H 'Content-Type: application/json'` 의 single-quoted 값에 걸리지 않게.
_CMD_URL_RE = re.compile(r"--data-binary @-\s+'([^']+)'\s*#\s*" + re.escape(_MARKER))


def _extract_url(cmd: str) -> str:
    m = _CMD_URL_RE.search(cmd or "")
    return m.group(1) if m else ""


# ───────── 공개 API ─────────

def api_event_forwarder_list(_q: dict | None = None) -> dict:
    """현재 설정된 Event Forwarder 훅 목록 반환."""
    data = _load_settings()
    hooks_obj = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    forwarders = []
    for event, items in hooks_obj.items():
        if event not in _EVENT_TYPES or not isinstance(items, list):
            continue
        for gi, group in enumerate(items):
            if not isinstance(group, dict):
                continue
            matcher = group.get("matcher") or ""
            sub = group.get("hooks") or []
            if not isinstance(sub, list):
                continue
            for si, h in enumerate(sub):
                if not isinstance(h, dict):
                    continue
                cmd = h.get("command") or ""
                if _MARKER not in cmd:
                    continue
                forwarders.append({
                    "event": event,
                    "matcher": matcher,
                    "url": _extract_url(cmd),
                    "groupIdx": gi,
                    "subIdx": si,
                })
    return {"ok": True, "forwarders": forwarders, "allowedHosts": sorted(_ALLOWED_HOSTS)}


def api_event_forwarder_add(body: dict) -> dict:
    """Event Forwarder 추가. body: {event, url, matcher?}."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    event = (body.get("event") or "").strip()
    url = (body.get("url") or "").strip()
    matcher = (body.get("matcher") or "").strip()
    if event not in _EVENT_TYPES:
        return {"ok": False, "error": f"invalid event (valid: {sorted(_EVENT_TYPES)})"}
    valid, err = _validate_url(url)
    if not valid:
        return {"ok": False, "error": err, "error_key": "err_fwd_url"}
    if matcher and len(matcher) > 200:
        return {"ok": False, "error": "matcher too long"}

    data = _load_settings()
    if not isinstance(data, dict):
        data = {}
    hooks_obj = data.setdefault("hooks", {})
    if not isinstance(hooks_obj, dict):
        return {"ok": False, "error": "hooks field malformed"}
    items = hooks_obj.setdefault(event, [])
    if not isinstance(items, list):
        return {"ok": False, "error": f"hooks.{event} is not a list"}

    new_entry = {
        "hooks": [{"type": "command", "command": _build_command(url)}],
    }
    if matcher:
        new_entry["matcher"] = matcher
    items.append(new_entry)

    ok, info = _write_settings(data)
    if not ok:
        return {"ok": False, "error": info}
    return {"ok": True, "event": event, "url": url, "backup": info}


def api_event_forwarder_remove(body: dict) -> dict:
    """Event Forwarder 제거. body: {event, groupIdx, subIdx}."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    event = (body.get("event") or "").strip()
    gi = body.get("groupIdx")
    si = body.get("subIdx")
    if event not in _EVENT_TYPES:
        return {"ok": False, "error": "invalid event"}
    try:
        gi = int(gi); si = int(si)
    except Exception:
        return {"ok": False, "error": "invalid index"}

    data = _load_settings()
    hooks_obj = data.get("hooks") if isinstance(data.get("hooks"), dict) else None
    if not hooks_obj or event not in hooks_obj:
        return {"ok": False, "error": "not found"}
    items = hooks_obj.get(event)
    if not isinstance(items, list) or gi < 0 or gi >= len(items):
        return {"ok": False, "error": "group idx out of range"}
    group = items[gi]
    if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
        return {"ok": False, "error": "malformed group"}
    sub = group["hooks"]
    if si < 0 or si >= len(sub):
        return {"ok": False, "error": "sub idx out of range"}
    removed = sub[si]
    if _MARKER not in (removed.get("command") or ""):
        return {"ok": False, "error": "not a forwarder (marker missing) — refusing to remove"}
    del sub[si]
    # 그룹 비면 그룹 제거
    if not sub:
        del items[gi]
    # 이벤트 비면 이벤트 제거
    if not items:
        del hooks_obj[event]

    ok, info = _write_settings(data)
    if not ok:
        return {"ok": False, "error": info}
    return {"ok": True, "backup": info}


def api_event_forwarder_meta(_q: dict | None = None) -> dict:
    """UI 초기화용 — 이벤트 타입 + 허용 호스트 목록."""
    return {
        "ok": True,
        "events": sorted(_EVENT_TYPES),
        "allowedHosts": sorted(_ALLOWED_HOSTS),
    }
