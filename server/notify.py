"""워크플로우 완료 알림 — Slack / Discord webhook (v2.25.0).

의도적으로 Slack `hooks.slack.com` 과 Discord `discord.com` / `discordapp.com`
호스트 화이트리스트만 허용. 임의 URL 로의 SSRF 방지.

Telegram 은 token 노출 리스크 → 다음 단계에서 OAuth 방식으로 별도 탭으로 분리.

모든 전송은 **실패 조용히 로그만 남김** — 워크플로우 결과에 영향 없음.
"""
from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlparse

from .logger import log

# `ssl` is deferred to send time. Importing ssl at module load triggers
# CA-bundle loading + ~3-6 MB of RSS that is dead weight when no
# notification has been sent yet.

_ALLOWED_HOSTS = {"hooks.slack.com", "discord.com", "discordapp.com"}
_TIMEOUT = 5


def _validate(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    return p.scheme == "https" and p.hostname in _ALLOWED_HOSTS


# v2.28.0 보안 감사: 기본 urlopen 은 3xx 리다이렉트를 자동 추종 → 화이트리스트 호스트가
# 다른 호스트로 redirect 시키면 우회 가능. defense-in-depth 로 리다이렉트 전면 차단.
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        log.warning("notify: blocked redirect to %s (from %s)", newurl, req.full_url)
        return None  # redirect 중단


# Lazy-built opener; constructing build_opener() at import time is cheap
# but we defer it to first send to keep boot lean. Module-level cache.
_NO_REDIRECT_OPENER = None  # type: ignore[var-annotated]


def _get_opener():
    """Build (or return cached) the no-redirect opener on first use."""
    global _NO_REDIRECT_OPENER
    if _NO_REDIRECT_OPENER is None:
        _NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect())
    return _NO_REDIRECT_OPENER


def _post_json(url: str, payload: dict) -> bool:
    if not _validate(url):
        log.warning("notify: rejected URL (not in whitelist): %s", urlparse(url).hostname)
        return False
    try:
        # ssl import deferred — loads CA bundle on first send only.
        import ssl  # noqa: F401  (used implicitly by https handlers)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "LazyClaude/2.28"},
        )
        ctx = ssl.create_default_context()  # noqa: F841 (kept for parity; default opener uses it via https handler)
        with _get_opener().open(req, timeout=_TIMEOUT) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        log.warning("notify send failed to %s: %s", urlparse(url).hostname, e)
        return False


def send_slack(webhook_url: str, title: str, body: str) -> bool:
    text = f"*{title}*\n```\n{body[:1800]}\n```"
    return _post_json(webhook_url, {"text": text})


def send_discord(webhook_url: str, title: str, body: str) -> bool:
    content = f"**{title}**\n```\n{body[:1800]}\n```"
    return _post_json(webhook_url, {"content": content})


def notify_workflow_completion(
    slack_url: str, discord_url: str,
    wf_name: str, run_id: str, status: str,
    duration_ms: int = 0, cost_usd: float = 0.0, summary: str = "",
) -> dict:
    """워크플로우 완료 시 호출. 설정된 채널만 전송. 실패해도 예외 발생 안 함."""
    emoji = "✅" if status == "ok" else "❌"
    title = f"{emoji} LazyClaude · {wf_name}"
    body_lines = [
        f"run: {run_id}",
        f"status: {status}",
    ]
    if duration_ms:
        body_lines.append(f"duration: {duration_ms/1000:.1f}s")
    if cost_usd:
        body_lines.append(f"cost: ${cost_usd:.4f}")
    if summary:
        body_lines.append("")
        body_lines.append(summary)
    body = "\n".join(body_lines)
    result = {"slack": False, "discord": False}
    if slack_url:
        result["slack"] = send_slack(slack_url, title, body)
    if discord_url:
        result["discord"] = send_discord(discord_url, title, body)
    return result


def send_email(cfg: dict, title: str, body: str) -> dict:
    """Send via SMTP+STARTTLS using stdlib only.
    cfg keys: smtp_host, smtp_port, smtp_user, smtp_password, from, to (str|list).
    Never raises; returns {ok, error?}."""
    if not isinstance(cfg, dict):
        return {"ok": False, "error": "config must be object"}
    host = (cfg.get("smtp_host") or "").strip()
    port = int(cfg.get("smtp_port") or 587)
    user = (cfg.get("smtp_user") or "").strip()
    pwd = cfg.get("smtp_password") or ""
    sender = (cfg.get("from") or user).strip()
    to_raw = cfg.get("to")
    if isinstance(to_raw, str):
        recipients = [r.strip() for r in to_raw.replace(";", ",").split(",") if r.strip()]
    elif isinstance(to_raw, list):
        recipients = [str(r).strip() for r in to_raw if str(r).strip()]
    else:
        recipients = []
    if not host or not user or not pwd or not sender or not recipients:
        return {"ok": False, "error": "missing smtp credentials or recipients"}
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.utils import formatdate
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[LazyClaude] {title[:60]}"
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg["Date"] = formatdate(localtime=True)
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.ehlo()
            try:
                smtp.starttls()
                smtp.ehlo()
            except Exception as e:
                # STARTTLS not supported; abort rather than send plaintext creds
                log.warning("notify email: starttls failed on %s:%s — %s", host, port, e)
                return {"ok": False, "error": f"starttls failed: {e}"}
            smtp.login(user, pwd)
            smtp.sendmail(sender, recipients, msg.as_string())
        return {"ok": True}
    except Exception as e:
        log.warning("notify email send failed: %s", e)
        return {"ok": False, "error": str(e)}


def send_telegram(cfg: dict, title: str, body: str) -> dict:
    """Send via Telegram Bot API sendMessage.
    cfg keys: bot_token, chat_id. Never raises; returns {ok, error?}."""
    if not isinstance(cfg, dict):
        return {"ok": False, "error": "config must be object"}
    token = (cfg.get("bot_token") or "").strip()
    chat_id = cfg.get("chat_id")
    if isinstance(chat_id, str):
        chat_id = chat_id.strip()
    if not token or chat_id in (None, ""):
        return {"ok": False, "error": "missing bot_token or chat_id"}
    try:
        import ssl  # noqa: F401
        text = f"*{title}*\n```\n{body[:3500]}\n```"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "LazyClaude/2.49"},
        )
        # Telegram is not in webhook whitelist; use a dedicated no-redirect opener
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(req, timeout=10) as resp:
            ok = 200 <= resp.status < 300
            return {"ok": ok} if ok else {"ok": False, "error": f"http {resp.status}"}
    except Exception as e:
        log.warning("notify telegram send failed: %s", e)
        return {"ok": False, "error": str(e)}


def _send_notify(config: dict, kind: str, summary: str) -> dict:
    """Multi-channel dispatcher used by auto_resume and tests.

    `config` shape (all keys optional):
        {
            "slack":    "https://hooks.slack.com/...",
            "discord":  "https://discord.com/api/webhooks/...",
            "email":    {smtp_host, smtp_port, smtp_user, smtp_password, from, to},
            "telegram": {bot_token, chat_id},
        }
    Returns per-channel results; never raises. Empty config is a no-op.
    """
    results: dict = {}
    if not isinstance(config, dict):
        return results
    title = f"LazyClaude · {kind}"
    body = summary or ""
    slack_url = config.get("slack") if isinstance(config.get("slack"), str) else ""
    slack_url = (slack_url or "").strip()
    if slack_url:
        results["slack"] = {"ok": send_slack(slack_url, title, body)}
    discord_url = config.get("discord") if isinstance(config.get("discord"), str) else ""
    discord_url = (discord_url or "").strip()
    if discord_url:
        results["discord"] = {"ok": send_discord(discord_url, title, body)}
    email_cfg = config.get("email")
    if isinstance(email_cfg, dict) and email_cfg:
        results["email"] = send_email(email_cfg, title, body)
    tg_cfg = config.get("telegram")
    if isinstance(tg_cfg, dict) and tg_cfg:
        results["telegram"] = send_telegram(tg_cfg, title, body)
    return results


def api_notify_test(body: dict) -> dict:
    """UI 테스트 버튼용 — 지정된 채널에 test 메시지 1건 전송."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    target = (body.get("target") or "").lower()
    url = (body.get("url") or "").strip()
    if target not in ("slack", "discord"):
        return {"ok": False, "error": "target must be slack|discord"}
    if not url:
        return {"ok": False, "error": "url required"}
    if not _validate(url):
        return {"ok": False, "error": "url host not in whitelist (hooks.slack.com / discord.com)",
                "error_key": "err_notify_host"}
    ok = (send_slack if target == "slack" else send_discord)(
        url, "LazyClaude · test message",
        "This is a test from LazyClaude workflow notification settings.",
    )
    return {"ok": ok}
