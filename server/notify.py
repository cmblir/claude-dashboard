"""워크플로우 완료 알림 — Slack / Discord webhook (v2.25.0).

의도적으로 Slack `hooks.slack.com` 과 Discord `discord.com` / `discordapp.com`
호스트 화이트리스트만 허용. 임의 URL 로의 SSRF 방지.

Telegram 은 token 노출 리스크 → 다음 단계에서 OAuth 방식으로 별도 탭으로 분리.

모든 전송은 **실패 조용히 로그만 남김** — 워크플로우 결과에 영향 없음.
"""
from __future__ import annotations

import json
import ssl
import urllib.request
from urllib.parse import urlparse

from .logger import log

_ALLOWED_HOSTS = {"hooks.slack.com", "discord.com", "discordapp.com"}
_TIMEOUT = 5


def _validate(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    return p.scheme == "https" and p.hostname in _ALLOWED_HOSTS


def _post_json(url: str, payload: dict) -> bool:
    if not _validate(url):
        log.warning("notify: rejected URL (not in whitelist): %s", urlparse(url).hostname)
        return False
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "LazyClaude/2.25"},
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as resp:
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
