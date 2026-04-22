"""`~/.claude/CLAUDE.md` · `~/.claude/settings.json` 읽기/쓰기.

CLAUDE.md 를 섹션 단위로 파싱하고, settings.json 의 permissions 필드를
검증·자동 교정한다. settings 는 대부분의 피처 모듈에서 read-only 로
참조하므로 순환 의존 없는 leaf 에 가깝게 둔다.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .config import CLAUDE_MD, SETTINGS_JSON
from .logger import log
from .utils import _safe_read, _safe_write


# ───────── CLAUDE.md ─────────

def parse_sections(raw: str) -> list:
    """`#`/`##`/`###` 헤더 기준으로 섹션 분리 — 에디터 프리뷰용."""
    sections, cur = [], None
    for line in raw.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            if cur:
                sections.append(cur)
            cur = {"title": m.group(2).strip(), "content": []}
        else:
            if cur is None:
                cur = {"title": "intro", "content": []}
            if line.strip():
                cur["content"].append(line)
    if cur:
        sections.append(cur)
    return sections


def get_claude_md() -> dict:
    raw = _safe_read(CLAUDE_MD)
    return {"sections": parse_sections(raw), "raw": raw}


def put_claude_md(body: dict) -> dict:
    raw = body.get("raw", "") if isinstance(body, dict) else ""
    if not isinstance(raw, str):
        return {"ok": False, "error": "raw must be string"}
    ok = _safe_write(CLAUDE_MD, raw)
    return {"ok": ok}


# ───────── settings.json ─────────

def get_settings() -> dict:
    """settings.json 내용 반환. 파일 없거나 파싱 실패 시 빈 dict."""
    if not SETTINGS_JSON.exists():
        return {}
    try:
        return json.loads(_safe_read(SETTINGS_JSON))
    except Exception:
        return {}


# 권한 규칙 검증 (Claude Code doctor 와 동일 룰)
# Bash(<cmd>:*)  → :* 는 반드시 마지막에만. 중간에 있으면 invalid.
_PERM_INVALID_MIDPATTERN = re.compile(r":\*[^\)]")


def validate_permission_rule(rule: str) -> Optional[str]:
    """규칙이 유효하면 None, 잘못이면 에러 메시지 반환."""
    if not isinstance(rule, str) or not rule.strip():
        return "빈 규칙"
    if _PERM_INVALID_MIDPATTERN.search(rule):
        return (
            "Claude Code 규칙: ':*' 는 패턴 맨 끝에만 올 수 있음. 중간에 쓰려면 '*' 사용. "
            "예: 'Bash(curl:* | sh)' → 'Bash(curl* | sh)'"
        )
    return None


def validate_permissions(perms: dict) -> list:
    """{allow:[], deny:[]} 검증 → [{rule, kind, error}, ...]"""
    issues = []
    if not isinstance(perms, dict):
        return issues
    for kind in ("allow", "deny"):
        for r in (perms.get(kind) or []):
            err = validate_permission_rule(r)
            if err:
                issues.append({"rule": r, "kind": kind, "error": err})
    return issues


def sanitize_permissions(perms: dict) -> tuple[dict, list]:
    """잘못된 규칙을 자동 교정 — ':*' 가 중간이면 '*' 로 치환. 변경 내역 함께 반환."""
    out: dict = {"allow": [], "deny": []}
    fixed: list = []
    if not isinstance(perms, dict):
        return out, fixed
    for kind in ("allow", "deny"):
        seen = set()
        for r in (perms.get(kind) or []):
            if not isinstance(r, str):
                continue
            new = r
            if _PERM_INVALID_MIDPATTERN.search(r):
                # ':*' 를 '*' 로 (단, 마지막의 ':*)' 는 그대로 보존)
                if r.endswith(":*)"):
                    head = r[:-3]
                    head = head.replace(":*", "*")
                    new = head + ":*)"
                else:
                    new = r.replace(":*", "*")
                if new != r:
                    fixed.append({"from": r, "to": new, "kind": kind})
            if new not in seen:
                seen.add(new)
                out[kind].append(new)
    return out, fixed


def put_settings(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}
    # 권한 규칙 자동 교정 + 잔존 invalid 차단
    if isinstance(body.get("permissions"), dict):
        sanitized, fixed = sanitize_permissions(body["permissions"])
        body["permissions"] = {**body["permissions"], **sanitized}
        remaining = validate_permissions(sanitized)
        if remaining:
            return {
                "ok": False,
                "error": "유효하지 않은 권한 규칙: "
                + "; ".join(f"{i['rule']} ({i['error']})" for i in remaining[:3]),
                "error_key": "err_permission_invalid",
            }
        if fixed:
            log.warning("permissions auto-fixed: %s", fixed)
    text = json.dumps(body, indent=2, ensure_ascii=False)
    ok = _safe_write(SETTINGS_JSON, text)
    return {"ok": ok, "fixed": fixed if isinstance(body.get("permissions"), dict) else []}
