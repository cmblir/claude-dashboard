"""Slack Web API integration — bot-token based (xoxb-*).

Used by the `slack_approval` workflow node and the Crew Wizard. Unlike the
older webhook-only `notify.py`, this module talks to `slack.com/api/*` with a
bearer token so it can both *send* messages and *read* replies/reactions to
implement an admin-approval gate.

Security:
- Only `slack.com` host is whitelisted.
- HTTPS-only, no redirects.
- Token loaded from `~/.claude-dashboard-slack.json` (chmod 600).
- All errors are surfaced to the caller (no silent swallow) so workflow runs
  reflect the real state.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import stat
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

from . import http_pool
from .config import _env_path
from .logger import log
from .utils import _safe_read, _safe_write


SLACK_CONFIG_PATH = _env_path(
    "CLAUDE_DASHBOARD_SLACK",
    Path.home() / ".claude-dashboard-slack.json",
)

_SLACK_API = "https://slack.com/api"
_SLACK_HOST = "slack.com"
_TIMEOUT = 8
_TOKEN_RE = re.compile(r"^xox[bp]-[A-Za-z0-9-]{10,}$")
_CHANNEL_RE = re.compile(r"^[A-Z0-9]{3,30}$|^#[a-z0-9_-]{1,80}$")


# ───────── Config persistence ─────────

def _empty_cfg() -> dict:
    return {"token": "", "defaultChannel": "", "teamId": "", "savedAt": 0}


def load_slack_config() -> dict:
    """Read the Slack config file. Returns an empty config if missing."""
    if not SLACK_CONFIG_PATH.exists():
        return _empty_cfg()
    try:
        data = json.loads(_safe_read(SLACK_CONFIG_PATH) or "{}")
        if not isinstance(data, dict):
            return _empty_cfg()
        cfg = _empty_cfg()
        cfg.update({
            "token":           str(data.get("token") or ""),
            "defaultChannel":  str(data.get("defaultChannel") or ""),
            "teamId":          str(data.get("teamId") or ""),
            "savedAt":         int(data.get("savedAt") or 0),
        })
        return cfg
    except Exception as e:
        log.warning("slack config load failed: %s", e)
        return _empty_cfg()


def _save_cfg(cfg: dict) -> bool:
    try:
        text = json.dumps(cfg, ensure_ascii=False, indent=2)
        ok = _safe_write(SLACK_CONFIG_PATH, text)
        if ok:
            try:
                os.chmod(SLACK_CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)
            except Exception:
                pass
        return ok
    except Exception as e:
        log.error("slack config save failed: %s", e)
        return False


def get_token() -> str:
    """Token resolution order: env var SLACK_BOT_TOKEN > config file."""
    env_tok = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    if env_tok:
        return env_tok
    return load_slack_config().get("token", "")


# ───────── Low-level Slack call ─────────

class SlackError(Exception):
    pass


def _call(method: str, payload: dict, token: Optional[str] = None,
          http_method: str = "POST") -> dict:
    """Single Slack Web API call.

    `method` is the API method name (e.g. "chat.postMessage"). Returns the
    parsed JSON dict on HTTP 2xx; raises SlackError otherwise.
    """
    tok = (token or get_token()).strip()
    if not tok:
        raise SlackError("slack token not configured")
    if not _TOKEN_RE.match(tok):
        raise SlackError("slack token format invalid (expected xoxb-* / xoxp-*)")

    path = f"/api/{method}"
    headers = {
        "Authorization": f"Bearer {tok}",
        "User-Agent":    "LazyClaude/2.55",
    }
    data: Optional[bytes] = None
    http_method = http_method.upper()
    if http_method == "POST":
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    else:
        if payload:
            path = path + "?" + urllib.parse.urlencode(payload)

    try:
        resp = http_pool.request(_SLACK_HOST, http_method, path,
                                 body=data, headers=headers, timeout=_TIMEOUT)
        raw = resp.body.decode("utf-8", errors="replace")
        try:
            obj = json.loads(raw)
        except Exception as e:
            raise SlackError(f"non-json response: {e}")
        if not isinstance(obj, dict):
            raise SlackError("unexpected response shape")
        if not obj.get("ok"):
            raise SlackError(f"slack error: {obj.get('error') or 'unknown'}")
        return obj
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        raise SlackError(f"network error: {e}")


# ───────── Public helpers ─────────

def auth_test(token: Optional[str] = None) -> dict:
    """Validate a token. Returns Slack's auth.test response on success."""
    return _call("auth.test", {}, token=token)


def post_message(channel: str, text: str, token: Optional[str] = None,
                 blocks: Optional[list] = None) -> dict:
    """chat.postMessage — returns {ok, ts, channel, ...}."""
    if not _CHANNEL_RE.match(channel or ""):
        raise SlackError("invalid channel id (expected Cxxxxx, Gxxxxx, or #name)")
    payload: dict = {"channel": channel, "text": text[:39000]}
    if blocks:
        payload["blocks"] = blocks
    return _call("chat.postMessage", payload, token=token)


def get_replies(channel: str, ts: str, token: Optional[str] = None) -> list:
    """conversations.replies — returns the messages in a thread (incl. parent)."""
    obj = _call("conversations.replies", {"channel": channel, "ts": ts},
                token=token, http_method="GET")
    return obj.get("messages") or []


def get_reactions(channel: str, ts: str, token: Optional[str] = None) -> list:
    """reactions.get — returns the reaction list on a single message."""
    obj = _call("reactions.get", {"channel": channel, "timestamp": ts, "full": "true"},
                token=token, http_method="GET")
    msg = (obj.get("message") or {})
    return msg.get("reactions") or []


# ───────── Approval polling ─────────

# Default reaction names interpreted as approve/reject. Slack delivers them
# without colons (e.g. "white_check_mark", "x").
APPROVE_REACTIONS = {"white_check_mark", "+1", "thumbsup", "ok_hand", "approve"}
REJECT_REACTIONS  = {"x", "-1", "thumbsdown", "no_entry", "reject"}


def wait_for_approval(channel: str, ts: str,
                      timeout_s: int = 300, poll_interval_s: int = 5,
                      token: Optional[str] = None) -> dict:
    """Block until an approval signal arrives or `timeout_s` elapses.

    Approval signals (in order of precedence):
      1. A reaction in APPROVE_REACTIONS → status="approved"
      2. A reaction in REJECT_REACTIONS  → status="rejected"
      3. A thread reply containing 'approve'/'ok'/'go'/'승인' → "approved"
      4. A thread reply containing 'reject'/'stop'/'거부'      → "rejected"
      5. Any other thread reply                              → "commented"
                                                              with reply text

    On timeout returns status="timeout".

    Returns: {status, reactor?, replyText?, replyUser?, polledFor}
    """
    timeout_s = max(5, min(int(timeout_s), 60 * 60 * 4))  # 5s..4h
    poll_interval_s = max(2, min(int(poll_interval_s), 60))
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        try:
            reactions = get_reactions(channel, ts, token=token)
        except SlackError as e:
            log.warning("slack poll reactions failed: %s", e)
            reactions = []
        for r in reactions:
            name = (r.get("name") or "").lower()
            users = r.get("users") or []
            if name in APPROVE_REACTIONS and users:
                return {"status": "approved", "reactor": users[0],
                        "polledFor": int(time.time() + timeout_s - deadline)}
            if name in REJECT_REACTIONS and users:
                return {"status": "rejected", "reactor": users[0],
                        "polledFor": int(time.time() + timeout_s - deadline)}

        try:
            replies = get_replies(channel, ts, token=token)
        except SlackError as e:
            log.warning("slack poll replies failed: %s", e)
            replies = []
        # The first message is the parent; replies are after it.
        for msg in replies[1:]:
            text = (msg.get("text") or "").strip()
            text_low = text.lower()
            user = msg.get("user") or ""
            if any(k in text_low for k in ("approve", "approved", "ok", "go ahead", "승인")):
                return {"status": "approved", "replyText": text, "replyUser": user}
            if any(k in text_low for k in ("reject", "rejected", "stop", "abort", "거부")):
                return {"status": "rejected", "replyText": text, "replyUser": user}
            if text:
                return {"status": "commented", "replyText": text, "replyUser": user}

        time.sleep(poll_interval_s)

    return {"status": "timeout", "polledFor": timeout_s}


# ───────── HTTP API endpoints (called from routes.py) ─────────

def api_slack_config_get(query: dict | None = None) -> dict:
    """GET /api/slack/config — never returns the raw token, only a redacted hint."""
    cfg = load_slack_config()
    tok = cfg.get("token") or ""
    return {
        "ok": True,
        "configured": bool(tok),
        "tokenHint": (tok[:6] + "..." + tok[-4:]) if len(tok) >= 12 else "",
        "defaultChannel": cfg.get("defaultChannel", ""),
        "teamId":         cfg.get("teamId", ""),
        "savedAt":        cfg.get("savedAt", 0),
    }


def api_slack_config_save(body: dict) -> dict:
    """POST /api/slack/config/save — stores token + default channel after auth.test."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    token = (body.get("token") or "").strip()
    channel = (body.get("defaultChannel") or "").strip()

    if not token and not channel:
        return {"ok": False, "error": "nothing to save"}

    if token:
        if not _TOKEN_RE.match(token):
            return {"ok": False, "error": "invalid token format (expected xoxb-* / xoxp-*)"}
        try:
            obj = auth_test(token)
        except SlackError as e:
            return {"ok": False, "error": f"auth.test failed: {e}"}
        team_id = obj.get("team_id") or ""
    else:
        cfg_prev = load_slack_config()
        token = cfg_prev.get("token", "")
        team_id = cfg_prev.get("teamId", "")
        if not token:
            return {"ok": False, "error": "token required (none on file)"}

    if channel and not _CHANNEL_RE.match(channel):
        return {"ok": False, "error": "invalid channel"}

    cfg = {
        "token":          token,
        "defaultChannel": channel,
        "teamId":         team_id,
        "savedAt":        int(time.time() * 1000),
    }
    if not _save_cfg(cfg):
        return {"ok": False, "error": "save failed"}
    return {"ok": True, "teamId": team_id}


def api_slack_config_clear(body: dict) -> dict:
    """POST /api/slack/config/clear — wipes saved token+channel."""
    if not _save_cfg(_empty_cfg()):
        return {"ok": False, "error": "clear failed"}
    return {"ok": True}


def api_slack_test(body: dict) -> dict:
    """POST /api/slack/test — auth.test + optional message echo."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    channel = (body.get("channel") or "").strip()
    msg = (body.get("text") or "LazyClaude · Slack connection test").strip()
    try:
        auth = auth_test()
    except SlackError as e:
        return {"ok": False, "error": str(e), "step": "auth"}
    out: dict[str, Any] = {"ok": True, "team": auth.get("team"), "user": auth.get("user")}
    if channel:
        try:
            r = post_message(channel, msg)
            out["messageTs"] = r.get("ts")
            out["postedTo"] = channel
        except SlackError as e:
            out["postWarning"] = str(e)
    return out
