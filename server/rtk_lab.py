"""RTK (Rust Token Killer) 통합 — Claude 토큰 60-90% 절감 (v2.24.0~).

https://github.com/rtk-ai/rtk — Rust 로 작성된 CLI 프록시. `rtk git status`
처럼 감싸거나, `rtk init -g` 로 Claude Code 에 Bash 훅을 설치하면 LLM 이
보는 출력이 자동으로 압축·필터링된다.

대시보드 통합 범위:
  - 설치 여부 + 버전 감지 (PATH + homebrew/cargo 경로 fallback)
  - 설정 파일 읽기 (macOS: `~/Library/Application Support/rtk/config.toml`)
  - 훅 설치 여부 점검 (`~/.claude/settings.json` 내 rtk 참조 탐지)
  - `rtk gain` · `rtk session` 출력 수집 (토큰 절감 통계)
  - brew / curl / cargo 3가지 설치 경로 — Terminal 창에서 대화형 실행
  - `rtk init -g` 훅 설치 트리거

모든 설치·init 명령은 `cli_tools._run_in_terminal` 재사용으로 AppleScript
Terminal 창을 띄워 사용자가 진행 상황을 직접 확인·수락할 수 있게 한다.
"""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from .cli_tools import _which, _run_in_terminal

RTK_HOMEPAGE = "https://github.com/rtk-ai/rtk"
RTK_GUIDE = "https://www.rtk-ai.app/guide"

# 명령 카탈로그 (UI 참조용, 서버는 실제 실행 X)
RTK_COMMAND_GROUPS: list[dict] = [
    {"group": "file", "label": "파일 조회",   "commands": ["ls", "read", "smart", "find", "grep", "diff"]},
    {"group": "git",  "label": "Git",        "commands": ["status", "log", "diff", "add", "commit", "push", "pull"]},
    {"group": "test", "label": "Test",       "commands": ["jest", "pytest", "cargo test", "go test"]},
    {"group": "build","label": "Build/Lint", "commands": ["lint", "tsc", "cargo build", "ruff check"]},
    {"group": "stat", "label": "Analytics",  "commands": ["gain", "discover", "session"]},
    {"group": "util", "label": "Utility",    "commands": ["json", "env", "log", "curl", "proxy"]},
]


def _rtk_config_path() -> Path:
    """RTK 설정 파일 경로 (OS 별)."""
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "rtk" / "config.toml"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "rtk" / "config.toml"


def _rtk_version(bin_path: str) -> str:
    if not bin_path:
        return ""
    try:
        out = subprocess.check_output([bin_path, "--version"], stderr=subprocess.STDOUT, timeout=5)
        return out.decode("utf-8", "replace").strip()
    except Exception:
        return ""


def _rtk_hook_installed() -> bool:
    """Claude Code 훅에 rtk 가 연결되어 있는지 (settings.json 문자열 탐지).

    `rtk init -g` 가 쓰는 정확한 필드를 모르므로 보수적으로 문자열 포함 여부로 판정.
    false positive 를 피하기 위해 user/agent 설정 외의 커맨드 필드에만 매칭.
    """
    settings = Path.home() / ".claude" / "settings.json"
    if not settings.exists():
        return False
    try:
        text = settings.read_text(encoding="utf-8")
        # hook / command / matcher 문맥에서 'rtk' 토큰 등장 시 True
        return ("rtk " in text) or ('"rtk"' in text) or ("'rtk'" in text)
    except Exception:
        return False


# ───────── 공개 API ─────────

def api_rtk_status(_q: dict | None = None) -> dict:
    bin_path = _which("rtk")
    installed = bool(bin_path)
    version = _rtk_version(bin_path) if installed else ""
    cfg = _rtk_config_path()
    return {
        "ok": True,
        "installed": installed,
        "binPath": bin_path,
        "version": version,
        "configPath": str(cfg),
        "configExists": cfg.exists(),
        "hookInstalled": _rtk_hook_installed() if installed else False,
        "brewAvailable": bool(_which("brew")),
        "cargoAvailable": bool(_which("cargo")),
        "homepage": RTK_HOMEPAGE,
        "guide": RTK_GUIDE,
        "commandGroups": RTK_COMMAND_GROUPS,
    }


def api_rtk_install(body: dict | None = None) -> dict:
    """RTK 설치 — Terminal 창에서 대화형 실행.

    body: {method: "brew" | "curl" | "cargo"}.
    이미 설치되어 있으면 no-op 반환.
    """
    if _which("rtk"):
        return {"ok": True, "already": True, "message": "rtk already installed"}

    method = ((body or {}).get("method") or "brew").lower()
    if method == "brew":
        if not _which("brew"):
            return {"ok": False, "error": "Homebrew not installed", "error_key": "err_no_brew"}
        cmd = "brew install rtk"
    elif method == "curl":
        cmd = "curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh"
    elif method == "cargo":
        if not _which("cargo"):
            return {"ok": False, "error": "cargo not installed", "error_key": "err_no_cargo"}
        cmd = "cargo install --git https://github.com/rtk-ai/rtk"
    else:
        return {"ok": False, "error": "invalid method", "error_key": "err_invalid_method"}
    result = _run_in_terminal(cmd)
    return {**result, "method": method, "command": cmd}


def api_rtk_init(_body: dict | None = None) -> dict:
    """`rtk init -g` — Claude Code 에 Bash 자동 재작성 훅 설치.

    대화형 y/n 프롬프트는 `yes` 파이프로 자동 응답한다. rtk 가 stdin 을
    쓰지 않는다면 yes 는 SIGPIPE 로 조기 종료되므로 부작용 없음.
    """
    if not _which("rtk"):
        return {"ok": False, "error": "rtk not installed", "error_key": "err_rtk_not_installed"}
    # 모든 확인 프롬프트에 자동 y 응답
    cmd = "yes | rtk init -g"
    result = _run_in_terminal(cmd)
    return {**result, "command": cmd}


def api_rtk_config(_q: dict | None = None) -> dict:
    cfg = _rtk_config_path()
    if not cfg.exists():
        return {"ok": True, "content": "", "path": str(cfg), "exists": False}
    try:
        return {"ok": True, "content": cfg.read_text(encoding="utf-8"), "path": str(cfg), "exists": True}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": str(cfg)}


def _run_rtk(args: list[str], timeout: int = 10) -> dict:
    bin_path = _which("rtk")
    if not bin_path:
        return {"ok": False, "error": "rtk not installed", "error_key": "err_rtk_not_installed"}
    try:
        proc = subprocess.run(
            [bin_path, *args],
            capture_output=True, timeout=timeout, check=False,
        )
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        return {"ok": proc.returncode == 0, "output": out, "stderr": err, "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def api_rtk_gain(_q: dict | None = None) -> dict:
    """`rtk gain` — 누적 토큰 절감 통계."""
    return _run_rtk(["gain"], timeout=10)


def api_rtk_session(_q: dict | None = None) -> dict:
    """`rtk session` — 현재 세션 사용 내역."""
    return _run_rtk(["session"], timeout=10)
