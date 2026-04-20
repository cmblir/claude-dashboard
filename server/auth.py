"""인증 / 계정 정보 — Claude CLI 연동 상태, 플랜, 로그인/로그아웃.

~/.claude.json 의 oauthAccount 를 읽어 UI 에 노출하고,
`claude auth login` / `logout` 을 감싸 로컬 훅을 제공한다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .config import CLAUDE_HOME, CLAUDE_JSON
from .logger import log
from .translations import _load_dash_config, _save_dash_config
from .utils import _safe_read


CLAUDE_PLANS = [
    {"id": "free",        "label": "무료 (Free)",          "note": "rate limit 있음"},
    {"id": "pro",         "label": "Claude Pro",          "note": "$20/월"},
    {"id": "max_5x",      "label": "Claude Max (5×)",      "note": "$100/월"},
    {"id": "max_20x",     "label": "Claude Max (20×)",     "note": "$200/월"},
    {"id": "team",        "label": "Claude Team",          "note": "팀 워크스페이스"},
    {"id": "enterprise",  "label": "Claude Enterprise",    "note": "엔터프라이즈"},
    {"id": "api_only",    "label": "API 키 전용",          "note": "종량제"},
]


def api_team_info() -> dict:
    """조직/워크스페이스/팀 정보 (claude.ai team 기능용)."""
    if not CLAUDE_JSON.exists():
        return {"connected": False}
    try:
        data = json.loads(_safe_read(CLAUDE_JSON, 500000))
    except Exception as e:
        return {"connected": False, "error": str(e)}
    oauth = data.get("oauthAccount") or {}
    cfg = _load_dash_config()
    claimed = cfg.get("claimedPlan") or ""
    return {
        "connected": bool(oauth),
        "displayName": oauth.get("displayName", ""),
        "email": oauth.get("emailAddress", ""),
        "organizationUuid": oauth.get("organizationUuid", ""),
        "organizationName": oauth.get("organizationName", ""),
        "organizationRole": oauth.get("organizationRole", ""),
        "workspaceRole": oauth.get("workspaceRole"),
        "accountUuid": oauth.get("accountUuid", ""),
        "billingType": oauth.get("billingType", ""),
        "hasExtraUsageEnabled": bool(oauth.get("hasExtraUsageEnabled", False)),
        "claimedPlan": claimed,
        "note": "상세 멤버 리스트/사용량은 claude.ai/settings/organization 에서 관리됩니다. 로컬에는 조직 식별자만 저장됨.",
    }


def api_auth_status() -> dict:
    """~/.claude.json 에서 oauth 정보 읽어 연결 상태 반환 + claude CLI 설치 여부."""
    cli_path = shutil.which("claude") or ""
    cli_version = ""
    if cli_path:
        try:
            cli_version = subprocess.check_output(
                [cli_path, "--version"], text=True, timeout=5,
            ).strip()
        except Exception:
            cli_version = ""

    if not CLAUDE_JSON.exists():
        return {
            "connected": False,
            "reason": "~/.claude.json 이 없습니다 — Claude Code에 로그인하세요.",
            "cliInstalled": bool(cli_path),
            "cliPath": cli_path,
            "cliVersion": cli_version,
        }
    try:
        data = json.loads(_safe_read(CLAUDE_JSON, 200000))
    except Exception as e:
        return {"connected": False, "reason": f"~/.claude.json 파싱 실패: {e}"}

    oauth = data.get("oauthAccount") or {}
    if not oauth:
        return {
            "connected": False, "reason": "OAuth 계정 없음 — `claude auth login` 실행 필요.",
            "cliInstalled": bool(cli_path), "cliPath": cli_path, "cliVersion": cli_version,
        }

    billing = oauth.get("billingType") or ""
    # 로컬에는 세부 플랜(Pro/Max/Team)이 저장되지 않음.
    # 사용자가 대시보드에서 직접 선택한 값이 있으면 우선.
    cfg = _load_dash_config()
    claimed_plan_id = cfg.get("claimedPlan") or ""
    claimed_plan = next((p for p in CLAUDE_PLANS if p["id"] == claimed_plan_id), None)

    if claimed_plan:
        plan_label = claimed_plan["label"]
    elif billing == "stripe_subscription":
        plan_label = "Claude 구독 활성 (세부 플랜 미지정)"
    elif billing == "api_key":
        plan_label = "API 키"
    else:
        plan_label = "무료 / 미확인"

    # `claude auth status` 에서 실시간 구독 타입 가져오기
    cli_auth: dict = {}
    if cli_path:
        try:
            raw = subprocess.check_output(
                [cli_path, "auth", "status"], text=True, timeout=5,
            ).strip()
            cli_auth = json.loads(raw) if raw.startswith("{") else {}
        except Exception:
            cli_auth = {}

    # CLI auth status 에 subscriptionType 이 있으면 plan label 덮어쓰기
    sub_type = cli_auth.get("subscriptionType", "")
    if sub_type and not claimed_plan:
        sub_map = {"free": "Free", "pro": "Pro", "max": "Max", "team": "Team", "enterprise": "Enterprise"}
        plan_label = f"Claude {sub_map.get(sub_type, sub_type)}"

    projects_count = len(data.get("projects", {}) or {})
    return {
        "connected": True,
        "email": cli_auth.get("email") or oauth.get("emailAddress", ""),
        "displayName": oauth.get("displayName", ""),
        "accountUuid": oauth.get("accountUuid", ""),
        "organizationUuid": cli_auth.get("orgId") or oauth.get("organizationUuid", ""),
        "organizationName": cli_auth.get("orgName") or "",
        "organizationRole": oauth.get("organizationRole", ""),
        "workspaceRole": oauth.get("workspaceRole", ""),
        "billingType": billing,
        "subscriptionType": sub_type,
        "planLabel": plan_label,
        "claimedPlanId": claimed_plan_id,
        "planNote": claimed_plan["note"] if claimed_plan else "플랜은 로컬에 저장되지 않습니다. 직접 선택하세요.",
        "availablePlans": CLAUDE_PLANS,
        "hasExtraUsageEnabled": bool(oauth.get("hasExtraUsageEnabled", False)),
        "subscriptionCreatedAt": oauth.get("subscriptionCreatedAt", ""),
        "accountCreatedAt": oauth.get("accountCreatedAt", ""),
        "userID": data.get("userID", ""),
        "firstTokenDate": data.get("claudeCodeFirstTokenDate", ""),
        "projectsKnown": projects_count,
        "cliInstalled": bool(cli_path),
        "cliPath": cli_path,
        "cliVersion": cli_version,
    }


def api_set_claimed_plan(body: dict) -> dict:
    pid = (body or {}).get("planId") if isinstance(body, dict) else ""
    if pid and not any(p["id"] == pid for p in CLAUDE_PLANS):
        return {"ok": False, "error": f"unknown plan id: {pid}"}
    cfg = _load_dash_config()
    if pid:
        cfg["claimedPlan"] = pid
    else:
        cfg.pop("claimedPlan", None)
    _save_dash_config(cfg)
    return {"ok": True, "planId": pid or ""}


def api_auth_login(body: dict) -> dict:
    """터미널에서 `claude auth login` 을 실행. 인터랙티브 명령이므로 터미널 앱을 열어준다."""
    cli = shutil.which("claude")
    if not cli:
        return {"ok": False, "error": "Claude CLI 가 설치되어 있지 않습니다. 먼저 설치하세요."}
    # macOS: AppleScript 로 기본 터미널에서 `claude auth login` 실행
    if platform.system() == "Darwin":
        script = f'''
        tell application "Terminal"
            activate
            do script "{cli} auth login"
        end tell
        '''
        try:
            subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True)
            return {"ok": True, "method": "terminal", "message": "터미널에서 로그인 창이 열렸습니다. 브라우저 인증 완료 후 돌아오세요."}
        except Exception as e:
            return {"ok": False, "error": f"터미널 실행 실패: {e}"}
    # Linux / fallback
    try:
        subprocess.Popen([cli, "auth", "login"], start_new_session=True)
        return {"ok": True, "method": "background", "message": "claude auth login 이 실행되었습니다. 완료 후 새로고침하세요."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def api_auth_logout(body: dict) -> dict:
    """로그아웃 — `claude auth logout` 실행."""
    cli = shutil.which("claude")
    if not cli:
        return {"ok": False, "error": "Claude CLI 미설치"}
    try:
        r = subprocess.run([cli, "auth", "logout"], capture_output=True, text=True, timeout=10)
        return {"ok": True, "message": "로그아웃 되었습니다.", "output": r.stdout.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


