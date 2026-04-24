"""Security Scan (v2.31.0) — ECC AgentShield 스타일 정적 검사.

~/.claude/ 하위 설정 · CLAUDE.md · hooks · agents · MCP 서버를 스캔해
시크릿 노출 · 위험 훅 · SSRF 가능 URL · 과도한 권한 · 신뢰 불가 MCP 등
보안 이슈를 휴리스틱으로 감지한다. AI 호출 없는 순수 정적 분석.

카테고리 (severity: critical / high / medium / low / info):
- secrets: API 키/토큰이 평문으로 남아있는지
- permissions: 위험한 `allow` 규칙
- hooks: 외부 네트워크 호출 · 임의 shell · sudo
- mcp: 임의 github URL 에서 받은 서버
- settings: autocompact 미설정 · thinking budget 과도 등 (token waste)
- integrity: settings.json 파싱 실패 등
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .logger import log

CLAUDE_HOME = Path.home() / ".claude"
SETTINGS = CLAUDE_HOME / "settings.json"
CLAUDE_MD = CLAUDE_HOME / "CLAUDE.md"
HOOKS_DIR = CLAUDE_HOME / "hooks"
AGENTS_DIR = CLAUDE_HOME / "agents"
MCP_JSON = CLAUDE_HOME / "mcp.json"

# 위험 패턴
_SECRET_PATTERNS = [
    # Anthropic 먼저 매칭 — `sk-ant-` 는 `sk-` 접두사 포함이므로 순서 중요.
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{50,}"), "anthropic api key"),
    # OpenAI — classic sk-…, project-scoped sk-proj-…, admin sk-admin-…
    (re.compile(r"sk-(?:proj|admin)-[A-Za-z0-9_\-]{20,}"), "openai scoped api key"),
    (re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}"), "openai api key"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "google api key"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "github personal access token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "github fine-grained pat"),
    (re.compile(r"gho_[A-Za-z0-9]{30,}"), "github oauth token"),
    (re.compile(r"ghs_[A-Za-z0-9]{30,}"), "github app server token"),
    (re.compile(r"AKIA[A-Z0-9]{16}"), "aws access key"),
    (re.compile(r"ASIA[A-Z0-9]{16}"), "aws session token"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9\-]{20,}"), "slack token"),
    (re.compile(r"hf_[A-Za-z0-9]{30,}"), "huggingface token"),
    (re.compile(r"glpat-[A-Za-z0-9_\-]{20,}"), "gitlab personal access token"),
    (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"), "private key"),
]
# v2.33.6 — 예제 / 플레이스홀더 패턴. 매칭되면 secret 경고 억제.
_SECRET_PLACEHOLDER_RE = re.compile(
    r"(?:YOUR[_-]?|EXAMPLE|PLACEHOLDER|XXXXXX|1234567890|REPLACE[_-]ME|\.\.\.\.|MASKED)",
    re.IGNORECASE,
)
_DANGEROUS_HOOK_PATTERNS = [
    (re.compile(r"\bsudo\b"), "sudo in hook"),
    (re.compile(r"\brm\s+-rf\s+/"), "rm -rf / in hook"),
    (re.compile(r"\bcurl\s+[^|]*\|\s*(?:sh|bash|zsh|ksh)\b"), "curl | shell (remote code execution)"),
    (re.compile(r"\bwget\s+[^|]*\|\s*(?:sh|bash|zsh|ksh)\b"), "wget | shell"),
    (re.compile(r"eval\s*\$\("), "eval of command substitution"),
    (re.compile(r"chmod\s+777"), "chmod 777 (world-writable)"),
    (re.compile(r"\bnc\s+-l\b"), "netcat listener in hook"),
    (re.compile(r"/dev/tcp/"), "bash /dev/tcp reverse shell"),
]
_DANGEROUS_PERMS = {
    "Bash(sudo *)": "unrestricted sudo",
    "Bash(rm -rf *)": "unrestricted rm -rf",
    "Bash(curl * | sh)": "pipe-to-shell allowed",
    "Bash(* | sh)": "pipe-to-shell allowed",
}


def _add(issues: list, severity: str, category: str, title: str, detail: str = "", loc: str = ""):
    issues.append({
        "severity": severity,
        "category": category,
        "title": title,
        "detail": detail,
        "location": loc,
    })


def _scan_secrets_in_text(text: str, where: str, issues: list):
    # v2.33.6 — .env.example / *.sample 류는 플레이스홀더로 가정하고 스킵.
    lower_where = where.lower()
    if (
        lower_where.endswith(".example")
        or ".example." in lower_where
        or lower_where.endswith(".sample")
        or ".sample." in lower_where
        or lower_where.endswith(".template")
        or "/fixtures/" in lower_where
        or "/tests/" in lower_where
        or "/test/" in lower_where
    ):
        return
    for pat, label in _SECRET_PATTERNS:
        for m in pat.finditer(text):
            sample = m.group(0)
            # 플레이스홀더 (YOUR_…, EXAMPLE, MASKED, ….) 는 false positive
            if _SECRET_PLACEHOLDER_RE.search(sample):
                continue
            _add(issues, "critical", "secrets",
                 f"{label} detected",
                 f"Literal secret found in {where} — rotate and store via env var.",
                 where)
            break  # 같은 유형은 1건만 보고 (noise 감소)


def _scan_settings(issues: list):
    if not SETTINGS.exists():
        _add(issues, "info", "integrity", "settings.json not found",
             "~/.claude/settings.json 이 없습니다.", str(SETTINGS))
        return
    try:
        text = SETTINGS.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception as e:
        _add(issues, "high", "integrity", "settings.json parse error", str(e), str(SETTINGS))
        return

    _scan_secrets_in_text(text, str(SETTINGS), issues)

    # 권한
    perms = (data.get("permissions") or {}) if isinstance(data, dict) else {}
    allow = (perms.get("allow") or []) if isinstance(perms, dict) else []
    for rule in allow if isinstance(allow, list) else []:
        if not isinstance(rule, str):
            continue
        for dang, reason in _DANGEROUS_PERMS.items():
            if rule.strip() == dang:
                _add(issues, "high", "permissions",
                     f"dangerous allow rule: {rule}",
                     reason, "settings.permissions.allow")
        if rule.strip() in ("Bash(*)", "*"):
            _add(issues, "critical", "permissions",
                 "wildcard Bash allow",
                 f"'{rule}' 는 모든 shell 명령을 무제한 허용합니다. 구체적 패턴으로 제한하세요.",
                 "settings.permissions.allow")

    # 토큰 설정 추천
    env = data.get("env") or {}
    if isinstance(env, dict):
        try:
            autocompact = env.get("CLAUDE_CODE_AUTOCOMPACT_THRESHOLD")
            if autocompact is None:
                _add(issues, "info", "tokens",
                     "autocompact threshold not set",
                     "ECC 권장: 50% (CLAUDE_CODE_AUTOCOMPACT_THRESHOLD=0.5) — 기본값 80% 보다 토큰 절약.",
                     "settings.env")
        except Exception:
            pass


def _scan_claude_md(issues: list):
    if not CLAUDE_MD.exists():
        return
    try:
        text = CLAUDE_MD.read_text(encoding="utf-8")
    except Exception:
        return
    _scan_secrets_in_text(text, str(CLAUDE_MD), issues)
    if len(text) > 50_000:
        _add(issues, "medium", "tokens",
             f"CLAUDE.md is large ({len(text)} chars)",
             "매 세션 시작 시 로드되어 토큰을 소모합니다. 필요 섹션만 유지하거나 skill/prompt library 로 분리 고려.",
             str(CLAUDE_MD))


def _scan_hooks(issues: list):
    if not SETTINGS.exists():
        return
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return
    hooks_obj = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    for event, groups in hooks_obj.items():
        if not isinstance(groups, list):
            continue
        for gi, g in enumerate(groups):
            if not isinstance(g, dict):
                continue
            for sub in (g.get("hooks") or []):
                if not isinstance(sub, dict):
                    continue
                cmd = sub.get("command") or ""
                if not isinstance(cmd, str):
                    continue
                for pat, label in _DANGEROUS_HOOK_PATTERNS:
                    if pat.search(cmd):
                        _add(issues, "high", "hooks",
                             f"{label} in {event} hook",
                             f"명령: `{cmd[:120]}`",
                             f"settings.hooks.{event}[{gi}]")
                # 매칭 matcher 없이 전체 적용되는 위험 훅
                if not g.get("matcher") and any(p.search(cmd) for p, _ in _DANGEROUS_HOOK_PATTERNS):
                    _add(issues, "medium", "hooks",
                         f"no matcher scope for risky hook in {event}",
                         "matcher 없이 모든 도구 호출에 적용됩니다.",
                         f"settings.hooks.{event}[{gi}]")


def _scan_mcp(issues: list):
    # settings.json 의 mcpServers + 별도 mcp.json
    configs = []
    if SETTINGS.exists():
        try:
            data = json.loads(SETTINGS.read_text(encoding="utf-8"))
            if isinstance(data.get("mcpServers"), dict):
                configs.append(("settings.mcpServers", data["mcpServers"]))
        except Exception:
            pass
    if MCP_JSON.exists():
        try:
            data = json.loads(MCP_JSON.read_text(encoding="utf-8"))
            if isinstance(data.get("mcpServers"), dict):
                configs.append((str(MCP_JSON) + ".mcpServers", data["mcpServers"]))
        except Exception:
            pass
    for loc, servers in configs:
        for name, cfg in servers.items():
            if not isinstance(cfg, dict):
                continue
            cmd = cfg.get("command") or ""
            args = cfg.get("args") or []
            full = (cmd + " " + " ".join(a for a in args if isinstance(a, str))).lower()
            # npx -y <scope>/pkg@latest 패턴이 검증 없이 임의 코드 실행
            if "npx" in full and "-y" in full:
                _add(issues, "medium", "mcp",
                     f"MCP '{name}' runs `npx -y` (auto-install)",
                     "신뢰할 수 없는 패키지면 임의 코드 실행 위험. github 레포의 signature 확인 권장.",
                     loc + "." + name)
            # uvx 방식도 동일
            if "uvx" in full:
                _add(issues, "low", "mcp",
                     f"MCP '{name}' uses uvx",
                     "uvx 자동 설치는 PyPI 에서 패키지를 받습니다. 신뢰 범위 확인.",
                     loc + "." + name)
            # 환경변수에 secret 직접 노출
            env = cfg.get("env") or {}
            if isinstance(env, dict):
                for k, v in env.items():
                    if not isinstance(v, str):
                        continue
                    for pat, label in _SECRET_PATTERNS:
                        if pat.search(v):
                            _add(issues, "critical", "secrets",
                                 f"{label} in MCP env var {name}.{k}",
                                 "MCP 서버 env 에 시크릿이 평문. 외부 env var 참조 또는 secret manager 사용.",
                                 loc + "." + name + ".env")


def _scan_agents(issues: list):
    if not AGENTS_DIR.exists():
        return
    for p in AGENTS_DIR.glob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        _scan_secrets_in_text(text, str(p), issues)
        # 과도한 권한 (allowedTools: *) 체크
        if re.search(r"^\s*allowedTools:\s*\*\s*$", text, re.MULTILINE):
            _add(issues, "medium", "permissions",
                 f"agent '{p.stem}' has wildcard tools",
                 "allowedTools: * 는 모든 도구를 허용합니다. 필요한 도구만 나열하세요.",
                 str(p))


def api_security_scan(_q: dict | None = None) -> dict:
    """정적 보안 스캔 실행. 이슈 리스트 + 카테고리별 카운트 반환."""
    issues: list[dict] = []
    _scan_settings(issues)
    _scan_claude_md(issues)
    _scan_hooks(issues)
    _scan_mcp(issues)
    _scan_agents(issues)

    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    by_category: dict[str, int] = {}
    for iss in issues:
        sev = iss.get("severity", "info")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        cat = iss.get("category", "other")
        by_category[cat] = by_category.get(cat, 0) + 1

    return {
        "ok": True,
        "issues": issues,
        "counts": {
            "total": len(issues),
            "bySeverity": by_severity,
            "byCategory": by_category,
        },
        "scannedAt": int(__import__("time").time()),
        "paths": {
            "settings": str(SETTINGS),
            "claudemd": str(CLAUDE_MD),
            "agents": str(AGENTS_DIR),
            "mcp": str(MCP_JSON),
        },
    }
