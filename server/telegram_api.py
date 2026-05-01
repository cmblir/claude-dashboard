"""Telegram Bot API integration — long-poll based.

Mirror of `slack_api.py`: token + default chat stored in
`~/.claude-dashboard-telegram.json` (chmod 600), HTTPS only, hostname pinned to
``api.telegram.org``. The receiver is long-poll by default (no public URL
required) — a single background thread per configured bot calls
``getUpdates(offset, timeout=25)`` and dispatches inbound messages to a
caller-supplied handler. Webhook mode is opt-in.

Routes (registered in `routes.py`) plus a `start_long_poll(handler)` for the
orchestrator. The orchestrator is the only thing that *calls* the receiver —
this module only knows how to talk to Telegram.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import stat
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from . import http_pool
from .config import _env_path
from .logger import log
from .utils import _safe_read, _safe_write


TG_CONFIG_PATH = _env_path(
    "CLAUDE_DASHBOARD_TELEGRAM",
    Path.home() / ".claude-dashboard-telegram.json",
)

_TG_API_HOST = "api.telegram.org"
_TIMEOUT = 30                      # > long-poll wait (25)
_TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_\-]{20,80}$")
_CHAT_RE = re.compile(r"^-?\d{1,20}$|^@[A-Za-z][A-Za-z0-9_]{4,31}$")


# ───────── Config ─────────

def _empty_cfg() -> dict:
    return {
        "token": "",
        "defaultChat": "",
        "botUsername": "",
        "mode": "longpoll",     # "longpoll" | "webhook"
        "webhookSecret": "",
        "savedAt": 0,
    }


def load_telegram_config() -> dict:
    if not TG_CONFIG_PATH.exists():
        return _empty_cfg()
    try:
        data = json.loads(_safe_read(TG_CONFIG_PATH) or "{}")
        if not isinstance(data, dict):
            return _empty_cfg()
        cfg = _empty_cfg()
        cfg.update({
            "token":         str(data.get("token") or ""),
            "defaultChat":   str(data.get("defaultChat") or ""),
            "botUsername":   str(data.get("botUsername") or ""),
            "mode":          str(data.get("mode") or "longpoll"),
            "webhookSecret": str(data.get("webhookSecret") or ""),
            "savedAt":       int(data.get("savedAt") or 0),
        })
        if cfg["mode"] not in ("longpoll", "webhook"):
            cfg["mode"] = "longpoll"
        return cfg
    except Exception as e:
        log.warning("telegram config load failed: %s", e)
        return _empty_cfg()


def _save_cfg(cfg: dict) -> bool:
    try:
        text = json.dumps(cfg, ensure_ascii=False, indent=2)
        ok = _safe_write(TG_CONFIG_PATH, text)
        if ok:
            try:
                os.chmod(TG_CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)
            except Exception:
                pass
        return ok
    except Exception as e:
        log.error("telegram config save failed: %s", e)
        return False


def get_token() -> str:
    env_tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if env_tok:
        return env_tok
    return load_telegram_config().get("token", "")


# ───────── Low-level call ─────────

class TelegramError(Exception):
    pass


def _call(method: str, params: dict, token: Optional[str] = None,
          timeout: int = _TIMEOUT) -> dict:
    tok = (token or get_token()).strip()
    if not tok:
        raise TelegramError("telegram token not configured")
    if not _TOKEN_RE.match(tok):
        raise TelegramError("telegram token format invalid")
    path = f"/bot{tok}/{method}"
    body = json.dumps(params).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent":   "LazyClaude-Telegram/2.55",
    }
    try:
        resp = http_pool.request(_TG_API_HOST, "POST", path,
                                 body=body, headers=headers, timeout=timeout)
        if resp.status // 100 != 2:
            raise TelegramError(f"http {resp.status}")
        raw = resp.body.decode("utf-8", errors="replace")
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise TelegramError("unexpected response shape")
        if not obj.get("ok"):
            raise TelegramError(f"telegram error: {obj.get('description') or 'unknown'}")
        return obj.get("result") or {}
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        raise TelegramError(f"network error: {e}")
    except json.JSONDecodeError as e:
        raise TelegramError(f"non-json response: {e}")


# ───────── Public helpers ─────────

def get_me(token: Optional[str] = None) -> dict:
    return _call("getMe", {}, token=token, timeout=_TIMEOUT)


def send_message(chat: str, text: str, token: Optional[str] = None,
                 reply_to: Optional[int] = None,
                 parse_mode: Optional[str] = None) -> dict:
    if not _CHAT_RE.match(chat or ""):
        raise TelegramError("invalid chat id (expected numeric id or @username)")
    params: dict = {
        "chat_id":                  chat,
        # Telegram caps message text at 4096 chars; truncate generously.
        "text":                     text[:4090],
        "disable_web_page_preview": True,
    }
    if reply_to is not None:
        params["reply_to_message_id"] = int(reply_to)
    if parse_mode:
        params["parse_mode"] = parse_mode
    return _call("sendMessage", params, token=token)


def get_updates(offset: int = 0, timeout: int = 25,
                token: Optional[str] = None) -> list[dict]:
    """Long-poll. ``timeout`` is the *server-side* wait — Telegram blocks until
    new updates exist or the timeout elapses. The HTTP timeout we set is
    timeout+5 so we don't kill the connection prematurely.
    """
    params = {"offset": offset, "timeout": int(timeout), "allowed_updates":
              ["message", "edited_message", "callback_query"]}
    out = _call("getUpdates", params, token=token, timeout=timeout + 5)
    return out if isinstance(out, list) else []


# ───────── Long-poll receiver ─────────

# Module-level singleton — we only support one bot at a time. If the user
# rotates the token, ``stop_long_poll()`` then ``start_long_poll()`` again.

_RECV_LOCK = threading.Lock()
_RECV_THREAD: Optional[threading.Thread] = None
_RECV_STOP = threading.Event()
_RECV_OFFSET = 0


def _long_poll_loop(handler: Callable[[dict], None]) -> None:
    global _RECV_OFFSET
    backoff = 1.0
    while not _RECV_STOP.is_set():
        try:
            updates = get_updates(offset=_RECV_OFFSET, timeout=25)
        except TelegramError as e:
            log.warning("telegram long-poll error: %s — retry in %.1fs", e, backoff)
            if _RECV_STOP.wait(backoff):
                break
            backoff = min(backoff * 2, 60.0)
            continue
        backoff = 1.0
        for upd in updates:
            try:
                _RECV_OFFSET = max(_RECV_OFFSET, int(upd.get("update_id") or 0) + 1)
                handler(upd)
            except Exception as e:
                # Don't let a bad handler kill the bot.
                log.error("telegram handler crash on update: %s", e)


def start_long_poll(handler: Callable[[dict], None]) -> bool:
    """Start the long-poll background thread. Returns False if no token."""
    global _RECV_THREAD
    if not get_token():
        log.info("telegram token not configured — long-poll skipped")
        return False
    with _RECV_LOCK:
        if _RECV_THREAD is not None and _RECV_THREAD.is_alive():
            return True
        _RECV_STOP.clear()
        t = threading.Thread(target=_long_poll_loop, args=(handler,),
                             name="telegram-longpoll", daemon=True)
        _RECV_THREAD = t
        t.start()
    return True


def stop_long_poll(timeout: float = 2.0) -> None:
    global _RECV_THREAD
    with _RECV_LOCK:
        _RECV_STOP.set()
        t = _RECV_THREAD
        _RECV_THREAD = None
    if t is not None:
        t.join(timeout=timeout)


# ───────── HTTP API endpoints ─────────

def api_telegram_config_get(query: dict | None = None) -> dict:
    cfg = load_telegram_config()
    tok = cfg.get("token") or ""
    return {
        "ok":            True,
        "configured":    bool(tok),
        "tokenHint":     (tok[:6] + "..." + tok[-4:]) if len(tok) >= 12 else "",
        "defaultChat":   cfg.get("defaultChat", ""),
        "botUsername":   cfg.get("botUsername", ""),
        "mode":          cfg.get("mode", "longpoll"),
        "savedAt":       cfg.get("savedAt", 0),
    }


def api_telegram_config_save(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    token   = (body.get("token") or "").strip()
    chat    = (body.get("defaultChat") or "").strip()
    mode    = (body.get("mode") or "").strip() or "longpoll"
    secret  = (body.get("webhookSecret") or "").strip()
    if mode not in ("longpoll", "webhook"):
        return {"ok": False, "error": "mode must be longpoll|webhook"}

    if token and not _TOKEN_RE.match(token):
        return {"ok": False, "error": "invalid token format"}

    bot_username = ""
    if token:
        try:
            me = get_me(token)
            bot_username = str(me.get("username") or "")
        except TelegramError as e:
            return {"ok": False, "error": f"getMe failed: {e}"}
    else:
        prev = load_telegram_config()
        token = prev.get("token", "")
        bot_username = prev.get("botUsername", "")
        if not token:
            return {"ok": False, "error": "token required (none on file)"}

    if chat and not _CHAT_RE.match(chat):
        return {"ok": False, "error": "invalid chat id"}

    cfg = {
        "token":         token,
        "defaultChat":   chat,
        "botUsername":   bot_username,
        "mode":          mode,
        "webhookSecret": secret,
        "savedAt":       int(time.time() * 1000),
    }
    if not _save_cfg(cfg):
        return {"ok": False, "error": "save failed"}
    return {"ok": True, "botUsername": bot_username}


def api_telegram_config_clear(body: dict) -> dict:
    if not _save_cfg(_empty_cfg()):
        return {"ok": False, "error": "clear failed"}
    return {"ok": True}


def api_telegram_test(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    chat = (body.get("chat") or "").strip() or load_telegram_config().get("defaultChat", "")
    text = (body.get("text") or "LazyClaude · Telegram connection test").strip()
    try:
        me = get_me()
    except TelegramError as e:
        return {"ok": False, "error": str(e), "step": "auth"}
    out: dict[str, Any] = {"ok": True, "bot": me.get("username")}
    if chat:
        try:
            r = send_message(chat, text)
            out["messageId"] = r.get("message_id")
            out["chat"] = chat
        except TelegramError as e:
            out["sendWarning"] = str(e)
    return out
