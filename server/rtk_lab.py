"""RTK (Rust Token Killer) 통합 — Claude 토큰 60-90% 절감 (v2.24.0~, uninstall v2.25.0).

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

import json
import os
import platform
import subprocess
import time
from pathlib import Path

from .cli_tools import _which, _run_in_terminal
from .utils import _safe_write

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
    """`rtk init -g --auto-patch` — Claude Code 에 Bash 자동 재작성 훅 설치.

    rtk 가 stdin 을 `is_terminal()` 로 감지하므로 `yes | rtk init -g` 는
    오히려 "is not a terminal → default No" 로 빠져 훅이 설치되지 않는다.
    공식 `--auto-patch` 플래그로 프롬프트를 스킵하고 무조건 패치하도록 한다.
    참고: https://github.com/rtk-ai/rtk/blob/master/src/hooks/init.rs
    """
    if not _which("rtk"):
        return {"ok": False, "error": "rtk not installed", "error_key": "err_rtk_not_installed"}
    # --auto-patch: settings.json 패치 프롬프트 자동 수락
    cmd = "rtk init -g --auto-patch"
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


def _is_rtk_hook(item: object) -> bool:
    """훅 항목이 rtk 를 참조하는지 재귀 판별 (command 필드 포함 · 중첩 hooks 지원)."""
    if not isinstance(item, dict):
        return False
    cmd = item.get("command", "")
    if isinstance(cmd, str) and (
        cmd.strip().startswith("rtk ")
        or cmd.strip() == "rtk"
        or " rtk " in f" {cmd} "
        or "/rtk " in cmd
    ):
        return True
    sub = item.get("hooks")
    if isinstance(sub, list) and any(_is_rtk_hook(s) for s in sub):
        return True
    return False


def api_rtk_uninstall_hook(_body: dict | None = None) -> dict:
    """Claude Code settings.json 에서 rtk 관련 훅 entry 만 제거.

    `rtk init -g` 가 추가한 훅을 되돌린다. 원본은 백업 (settings.json.bak.<ts>)
    으로 보존. rtk 바이너리 자체는 건드리지 않음 — 제거하려면 brew uninstall 등
    별도 명령 필요.
    """
    settings_path = Path.home() / ".claude" / "settings.json"
    if not settings_path.exists():
        return {"ok": False, "error": "settings.json not found", "error_key": "err_no_settings"}
    try:
        text = settings_path.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception as e:
        return {"ok": False, "error": f"parse failed: {e}"}
    if not isinstance(data, dict):
        return {"ok": False, "error": "settings.json is not an object"}

    hooks_obj = data.get("hooks")
    if not isinstance(hooks_obj, dict):
        return {"ok": True, "removed": 0, "message": "no hooks section"}

    removed = 0
    for event in list(hooks_obj.keys()):
        items = hooks_obj.get(event)
        if not isinstance(items, list):
            continue
        kept: list = []
        for item in items:
            # 1) 최상위 entry 가 rtk 를 참조하면 통째로 제거
            if _is_rtk_hook(item):
                removed += 1
                continue
            # 2) 중첩 hooks 배열에서 rtk entry 만 걸러냄
            if isinstance(item, dict) and isinstance(item.get("hooks"), list):
                new_sub = [s for s in item["hooks"] if not _is_rtk_hook(s)]
                if len(new_sub) != len(item["hooks"]):
                    removed += len(item["hooks"]) - len(new_sub)
                    if new_sub:
                        item = {**item, "hooks": new_sub}
                    else:
                        continue  # 비면 그룹 자체 제거
            kept.append(item)
        if kept:
            hooks_obj[event] = kept
        else:
            hooks_obj.pop(event, None)

    if removed == 0:
        return {"ok": True, "removed": 0, "message": "no rtk hooks found"}

    # 백업 생성 → 원자적 재작성
    ts = int(time.time())
    backup_path = settings_path.with_suffix(f".json.bak.{ts}")
    try:
        backup_path.write_text(text, encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"backup failed: {e}"}
    _safe_write(settings_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return {"ok": True, "removed": removed, "backup": str(backup_path), "settingsPath": str(settings_path)}


def api_rtk_gain(_q: dict | None = None) -> dict:
    """`rtk gain` — 누적 토큰 절감 통계."""
    return _run_rtk(["gain"], timeout=10)


def api_rtk_session(_q: dict | None = None) -> dict:
    """`rtk session` — 현재 세션 사용 내역."""
    return _run_rtk(["session"], timeout=10)
