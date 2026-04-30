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
