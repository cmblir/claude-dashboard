"""Discord integration — HTTPS bot API + interactions webhook.

Mirror of ``slack_api.py`` / ``telegram_api.py``: token + default channel
stored in ``~/.claude-dashboard-discord.json`` (chmod 600), HTTPS only via
``http_pool``, hostname pinned to ``discord.com``.

Two halves:

1. **Outbound** — ``send_message(channel_id, text)`` using the Bot Token.
   Always works. No optional dep.

2. **Inbound (interactions)** — Discord requires every webhook request be
   verified with **ed25519** over the raw body and ``X-Signature-Timestamp``
   header. We use the ``cryptography`` library when available; if it's not
   installed, the signature-verification path returns ``False`` with a
   clear log line, and the orchestrator skips dispatch (security-failsafe).
   The dashboard's main runtime is still stdlib-only — Discord inbound is
   an opt-in extension.

Storage / routes follow the same shape as Slack/Telegram so the TUI and
dashboard treat them interchangeably.
"""
from __future__ import annotations

import json
import os
import re
import stat
import time
from pathlib import Path
from typing import Any, Optional

from . import http_pool
from .config import _env_path
from .logger import log
from .utils import _safe_read, _safe_write


DISCORD_CONFIG_PATH = _env_path(
    "CLAUDE_DASHBOARD_DISCORD",
    Path.home() / ".claude-dashboard-discord.json",
)

_DISCORD_HOST = "discord.com"
_API_BASE = "/api/v10"
_TIMEOUT = 8

# Discord bot tokens are JWT-ish: 3 base64url segments. Loose validator —
# Discord doesn't publish a strict regex.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-\.]{40,200}$")
_CHANNEL_RE = re.compile(r"^\d{15,21}$")
_APP_ID_RE = re.compile(r"^\d{15,21}$")
_PUBKEY_RE = re.compile(r"^[0-9a-fA-F]{64}$")  # 32-byte ed25519 public key, hex


# ───────── Config ─────────

def _empty_cfg() -> dict:
    return {
        "token": "", "defaultChannel": "", "applicationId": "",
        "publicKey": "", "savedAt": 0,
    }


def load_discord_config() -> dict:
    if not DISCORD_CONFIG_PATH.exists():
        return _empty_cfg()
    try:
        data = json.loads(_safe_read(DISCORD_CONFIG_PATH) or "{}")
        if not isinstance(data, dict):
            return _empty_cfg()
        cfg = _empty_cfg()
        cfg.update({
            "token":          str(data.get("token") or ""),
            "defaultChannel": str(data.get("defaultChannel") or ""),
            "applicationId":  str(data.get("applicationId") or ""),
            "publicKey":      str(data.get("publicKey") or ""),
            "savedAt":        int(data.get("savedAt") or 0),
        })
        return cfg
    except Exception as e:
        log.warning("discord config load failed: %s", e)
        return _empty_cfg()


def _save_cfg(cfg: dict) -> bool:
    try:
        text = json.dumps(cfg, ensure_ascii=False, indent=2)
        ok = _safe_write(DISCORD_CONFIG_PATH, text)
        if ok:
            try:
                os.chmod(DISCORD_CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)
            except Exception:
                pass
        return ok
    except Exception as e:
        log.error("discord config save failed: %s", e)
        return False


def get_token() -> str:
    env_tok = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if env_tok:
        return env_tok
    return load_discord_config().get("token", "")


# ───────── Low-level call ─────────

class DiscordError(Exception):
    pass


def _call(method: str, path: str, payload: Optional[dict] = None,
          token: Optional[str] = None) -> dict:
    tok = (token or get_token()).strip()
    if not tok:
        raise DiscordError("discord token not configured")
    if not _TOKEN_RE.match(tok):
        raise DiscordError("discord token format invalid")
    headers = {
        "Authorization": f"Bot {tok}",
        "User-Agent":    "LazyClaude-Discord/2.56",
    }
    body: Optional[bytes] = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        resp = http_pool.request(_DISCORD_HOST, method.upper(),
                                 _API_BASE + path, body=body,
                                 headers=headers, timeout=_TIMEOUT)
    except Exception as e:
        raise DiscordError(f"network error: {e}")
    if resp.status // 100 != 2:
        snippet = resp.body[:200].decode("utf-8", errors="replace")
        raise DiscordError(f"http {resp.status}: {snippet}")
    if not resp.body:
        return {}
    try:
        obj = json.loads(resp.body.decode("utf-8"))
    except Exception as e:
        raise DiscordError(f"non-json response: {e}")
    return obj if isinstance(obj, dict) else {}


# ───────── Public helpers ─────────

def get_current_user(token: Optional[str] = None) -> dict:
    return _call("GET", "/users/@me", token=token)


def send_message(channel: str, text: str,
                 token: Optional[str] = None) -> dict:
    if not _CHANNEL_RE.match(channel or ""):
        raise DiscordError("invalid channel id (expected 15-21 digit snowflake)")
    return _call("POST", f"/channels/{channel}/messages",
                 {"content": text[:1990]}, token=token)


# ───────── Interactions signature verification ─────────

def verify_interaction_signature(raw_body: bytes, signature_hex: str,
                                 timestamp: str, public_key_hex: str) -> bool:
    """Verify Discord's ed25519 signature.

    Returns True on success, False on any failure (including missing
    cryptography lib). Never raises — security-failsafe behaviour.
    """
    if not (raw_body and signature_hex and timestamp and public_key_hex):
        return False
    if not _PUBKEY_RE.match(public_key_hex):
        log.warning("discord publicKey malformed (expected 64 hex chars)")
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except Exception:
        log.warning("discord interactions: 'cryptography' not installed — "
                    "verification disabled, refusing all webhooks")
        return False
    try:
        pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        sig = bytes.fromhex(signature_hex)
        message = timestamp.encode("utf-8") + raw_body
        pk.verify(sig, message)
        return True
    except (InvalidSignature, ValueError):
        return False
    except Exception as e:
        log.warning("discord verify error: %s", e)
        return False


# ───────── HTTP API (config) ─────────

def api_discord_config_get(query: dict | None = None) -> dict:
    cfg = load_discord_config()
    tok = cfg.get("token") or ""
    pk = cfg.get("publicKey") or ""
    return {
        "ok":             True,
        "configured":     bool(tok),
        "tokenHint":      (tok[:6] + "..." + tok[-4:]) if len(tok) >= 12 else "",
        "defaultChannel": cfg.get("defaultChannel", ""),
        "applicationId":  cfg.get("applicationId", ""),
        "publicKeySet":   bool(pk),
        "savedAt":        cfg.get("savedAt", 0),
    }


def api_discord_config_save(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    token   = (body.get("token") or "").strip()
    channel = (body.get("defaultChannel") or "").strip()
    app_id  = (body.get("applicationId") or "").strip()
    pubkey  = (body.get("publicKey") or "").strip()

    if token and not _TOKEN_RE.match(token):
        return {"ok": False, "error": "invalid token format"}

    if token:
        try:
            me = get_current_user(token)
        except DiscordError as e:
            return {"ok": False, "error": f"users/@me failed: {e}"}
        # Discord's /users/@me returns the bot user.
        me_id = me.get("id") or ""
    else:
        prev = load_discord_config()
        token = prev.get("token", "")
        me_id = prev.get("applicationId", "")
        if not token:
            return {"ok": False, "error": "token required (none on file)"}

    if channel and not _CHANNEL_RE.match(channel):
        return {"ok": False, "error": "invalid channel id"}
    if app_id and not _APP_ID_RE.match(app_id):
        return {"ok": False, "error": "invalid applicationId"}
    if pubkey and not _PUBKEY_RE.match(pubkey):
        return {"ok": False, "error": "publicKey must be 64-hex-char ed25519 key"}

    cfg = {
        "token":          token,
        "defaultChannel": channel,
        "applicationId":  app_id or me_id,
        "publicKey":      pubkey,
        "savedAt":        int(time.time() * 1000),
    }
    if not _save_cfg(cfg):
        return {"ok": False, "error": "save failed"}
    return {"ok": True, "applicationId": cfg["applicationId"]}


def api_discord_config_clear(body: dict) -> dict:
    if not _save_cfg(_empty_cfg()):
        return {"ok": False, "error": "clear failed"}
    return {"ok": True}


def api_discord_test(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    channel = (body.get("channel") or "").strip() \
              or load_discord_config().get("defaultChannel", "")
    text = (body.get("text") or "LazyClaude · Discord connection test").strip()
    try:
        me = get_current_user()
    except DiscordError as e:
        return {"ok": False, "error": str(e), "step": "auth"}
    out: dict[str, Any] = {"ok": True, "bot": me.get("username")}
    if channel:
        try:
            r = send_message(channel, text)
            out["messageId"] = r.get("id")
            out["channel"] = channel
        except DiscordError as e:
            out["sendWarning"] = str(e)
    return out
