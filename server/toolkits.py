"""Toolkits 설치 관리 — Everything Claude Code(ECC) · Claude Code Best Practice(CCB).

guideHub 탭의 툴킷 카드 3종 중 직접 설치/해제가 가능한 2개 관리.

스키마:
- ECC (Claude Code plugin marketplace):
    `~/.claude/plugins/marketplaces/everything-claude-code/` 에 git clone.
    `~/.claude/plugins/known_marketplaces.json` 에 entry 등록하면 Claude Code 가
    인식해 `/plugin install everything-claude-code@everything-claude-code` 로
    플러그인을 설치할 수 있게 된다.
    (실제 `/plugin install` 실행은 Claude Code session 필요 → 사용자가 CC 에서 실행.)

- CCB (문서 레포):
    단순 `git clone` → 사용자가 지정한 경로(기본 `~/claude-code-best-practice`) 에 저장.
    설치/제거 = 디렉터리 존재 여부.

보안:
- 외부 호출은 `git clone` 고정 URL 만. subprocess 인자 배열 전달 (shell=False).
- 쓰기 경로는 ~/.claude/plugins/... · ~/… 아래로 제한.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import PLUGINS_DIR, KNOWN_MARKETPLACES_JSON, CLAUDE_HOME
from .utils import _safe_write
from .cli_tools import _which


def _run_claude_plugin(args: list[str], timeout: int = 90) -> dict[str, Any]:
    """`claude plugin ...` subcommand — non-interactive.

    Used for full auto-install/uninstall/enable/disable of plugins without a CC session.
    """
    claude = _which("claude")
    if not claude:
        return {"ok": False, "error": "claude CLI not found", "error_key": "err_no_claude_cli"}
    try:
        proc = subprocess.run(
            [claude, "plugin", *args],
            capture_output=True, timeout=timeout, check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.decode("utf-8", "replace").strip(),
            "stderr": proc.stderr.decode("utf-8", "replace").strip(),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout}s"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# 고정 카탈로그 — guide.py 의 _TOOLKIT_SOURCES 와 정합성 유지
_ECC_ID = "everything-claude-code"
_ECC_REPO = "https://github.com/affaan-m/everything-claude-code.git"
_ECC_REPO_HTTPS = "https://github.com/affaan-m/everything-claude-code"

_CCB_ID = "claude-code-best-practice"
_CCB_REPO = "https://github.com/shanraisshan/claude-code-best-practice.git"
_CCB_REPO_HTTPS = "https://github.com/shanraisshan/claude-code-best-practice"
_CCB_DEFAULT_DIR = Path.home() / _CCB_ID


# ───────── 유틸 ─────────

def _marketplaces_dir() -> Path:
    return PLUGINS_DIR / "marketplaces"


def _ecc_install_dir() -> Path:
    return _marketplaces_dir() / _ECC_ID


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _save_known_marketplaces(data: dict[str, Any]) -> None:
    KNOWN_MARKETPLACES_JSON.parent.mkdir(parents=True, exist_ok=True)
    _safe_write(KNOWN_MARKETPLACES_JSON, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _run_git(args: list[str], cwd: Path | None = None, timeout: int = 120) -> dict[str, Any]:
    git_path = _which("git")
    if not git_path:
        return {"ok": False, "error": "git not found", "error_key": "err_no_git"}
    try:
        proc = subprocess.run(
            [git_path, *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True, timeout=timeout, check=False,
        )
        out = proc.stdout.decode("utf-8", "replace").strip()
        err = proc.stderr.decode("utf-8", "replace").strip()
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": out,
            "stderr": err,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "git timeout"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _dir_commit(repo_dir: Path) -> str:
    if not (repo_dir / ".git").exists():
        return ""
    r = _run_git(["rev-parse", "--short", "HEAD"], cwd=repo_dir, timeout=5)
    return r.get("stdout", "") if r.get("ok") else ""


def _dir_last_updated(repo_dir: Path) -> str:
    if not (repo_dir / ".git").exists():
        return ""
    r = _run_git(["log", "-1", "--format=%ci"], cwd=repo_dir, timeout=5)
    return r.get("stdout", "") if r.get("ok") else ""


def _under_home(p: Path) -> bool:
    """경로가 사용자 홈 디렉터리 아래인지 (symlink traversal 차단용)."""
    try:
        rp = os.path.realpath(str(p))
        home = os.path.realpath(str(Path.home()))
        return rp == home or rp.startswith(home + os.sep)
    except Exception:
        return False


# ───────── 상태 조회 ─────────

def api_toolkit_status(_q: dict | None = None) -> dict[str, Any]:
    """ECC marketplace · ECC plugin · CCB repo 설치 상태."""
    mkt_dir = _ecc_install_dir()
    ecc_known = _load_json(KNOWN_MARKETPLACES_JSON)
    ecc_registered = _ECC_ID in ecc_known

    # installed_plugins.json 에서 "@everything-claude-code" 들어간 plugin 검색
    ip_path = PLUGINS_DIR / "installed_plugins.json"
    ip = _load_json(ip_path)
    ecc_plugins: list[str] = []
    if isinstance(ip, dict):
        plugs = ip.get("plugins")
        if isinstance(plugs, dict):
            for k in plugs.keys():
                if isinstance(k, str) and k.endswith(f"@{_ECC_ID}"):
                    ecc_plugins.append(k)

    ccb_dir = _CCB_DEFAULT_DIR

    return {
        "ok": True,
        "gitAvailable": bool(_which("git")),
        "ecc": {
            "id": _ECC_ID,
            "repo": _ECC_REPO_HTTPS,
            "installDir": str(mkt_dir),
            "marketplaceCloned": mkt_dir.exists() and (mkt_dir / ".git").exists(),
            "registered": ecc_registered,
            "commit": _dir_commit(mkt_dir),
            "lastUpdated": _dir_last_updated(mkt_dir),
            "installedPlugins": ecc_plugins,
            "installCommand": f"/plugin install {_ECC_ID}@{_ECC_ID}",
        },
        "ccb": {
            "id": _CCB_ID,
            "repo": _CCB_REPO_HTTPS,
            "defaultDir": str(ccb_dir),
            "cloned": ccb_dir.exists() and (ccb_dir / ".git").exists(),
            "commit": _dir_commit(ccb_dir),
            "lastUpdated": _dir_last_updated(ccb_dir),
        },
    }


# ───────── ECC 설치/제거 ─────────

def api_toolkit_ecc_install(_body: dict | None = None) -> dict[str, Any]:
    """ECC marketplace 자동 설치.

    1) `git clone https://github.com/affaan-m/everything-claude-code.git <PLUGINS_DIR>/marketplaces/everything-claude-code`
    2) `known_marketplaces.json` 에 entry 추가

    이후 Claude Code 에서 `/plugin install everything-claude-code@everything-claude-code` 실행으로
    실제 플러그인 설치. 대시보드에서 자동 install 은 Claude Code session 필요하여 지원 X.
    """
    target = _ecc_install_dir()
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        # 이미 존재 — pull 로 갱신만
        r = _run_git(["pull", "--ff-only"], cwd=target)
        if not r.get("ok"):
            return {"ok": False, "error": f"git pull failed: {r.get('stderr') or r.get('error')}"}
        updated = True
    else:
        r = _run_git(["clone", "--depth", "1", _ECC_REPO, str(target)])
        if not r.get("ok"):
            return {"ok": False, "error": f"git clone failed: {r.get('stderr') or r.get('error')}"}
        updated = False

    # known_marketplaces.json 에 entry 추가/갱신
    known = _load_json(KNOWN_MARKETPLACES_JSON)
    known[_ECC_ID] = {
        "source": {"source": "github", "repo": "affaan-m/everything-claude-code"},
        "installLocation": str(target),
        "lastUpdated": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
    }
    _save_known_marketplaces(known)

    return {
        "ok": True,
        "installed": True,
        "updated": updated,
        "path": str(target),
        "nextStep": f"Claude Code 에서 `/plugin install {_ECC_ID}@{_ECC_ID}` 실행",
    }


def api_toolkit_ecc_install_plugin(body: dict | None = None) -> dict[str, Any]:
    """Run `claude plugin install everything-claude-code@everything-claude-code -s <scope>`.

    Non-interactive; finishes in a few seconds. Requires the marketplace to be
    registered first (run api_toolkit_ecc_install beforehand).
    """
    body = body or {}
    scope = (body.get("scope") or "user").lower()
    if scope not in ("user", "project", "local"):
        return {"ok": False, "error": "invalid scope"}
    # marketplace 가 없으면 먼저 시도
    if not _ecc_install_dir().exists():
        pre = api_toolkit_ecc_install()
        if not pre.get("ok"):
            return {"ok": False, "error": f"marketplace prep failed: {pre.get('error')}"}
    target = f"{_ECC_ID}@{_ECC_ID}"
    r = _run_claude_plugin(["install", target, "-s", scope])
    if not r.get("ok"):
        return {"ok": False, "error": r.get("stderr") or r.get("error") or "install failed"}
    return {"ok": True, "installed": True, "scope": scope, "plugin": target, "stdout": r.get("stdout", "")}


def api_toolkit_ecc_uninstall_plugin(body: dict | None = None) -> dict[str, Any]:
    """Run `claude plugin uninstall everything-claude-code@everything-claude-code`."""
    body = body or {}
    scope = (body.get("scope") or "user").lower()
    if scope not in ("user", "project", "local"):
        return {"ok": False, "error": "invalid scope"}
    target = f"{_ECC_ID}@{_ECC_ID}"
    r = _run_claude_plugin(["uninstall", target, "-s", scope])
    if not r.get("ok"):
        return {"ok": False, "error": r.get("stderr") or r.get("error") or "uninstall failed"}
    return {"ok": True, "uninstalled": True, "scope": scope, "plugin": target, "stdout": r.get("stdout", "")}


def api_toolkit_ecc_uninstall(_body: dict | None = None) -> dict[str, Any]:
    """ECC marketplace 제거 — 디렉터리 + known_marketplaces.json entry.

    실제 설치된 플러그인(`installed_plugins.json`) 은 Claude Code CLI 의 영역이라
    건드리지 않음. 사용자는 Claude Code 에서 `/plugin uninstall` 로 별도 해제 필요.
    """
    target = _ecc_install_dir()
    removed_dir = False
    if target.exists():
        if not _under_home(target):
            return {"ok": False, "error": "refusing to delete outside $HOME"}
        try:
            shutil.rmtree(target)
            removed_dir = True
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"rmtree failed: {e}"}

    known = _load_json(KNOWN_MARKETPLACES_JSON)
    removed_entry = False
    if _ECC_ID in known:
        known.pop(_ECC_ID, None)
        _save_known_marketplaces(known)
        removed_entry = True

    return {
        "ok": True,
        "removedDir": removed_dir,
        "removedRegistry": removed_entry,
        "note": "플러그인 자체는 Claude Code 에서 `/plugin uninstall ...` 로 별도 제거",
    }


# ───────── CCB 설치/제거 ─────────

def api_toolkit_ccb_install(body: dict | None = None) -> dict[str, Any]:
    """CCB 레포 git clone — 기본 경로 `~/claude-code-best-practice/`.

    body.path 로 커스텀 경로 지정 가능하지만 $HOME 밑으로만 허용.
    """
    body = body or {}
    raw_path = (body.get("path") or "").strip()
    target = Path(raw_path).expanduser() if raw_path else _CCB_DEFAULT_DIR

    # 안전성: $HOME 아래로 제한 (symlink realpath 검증)
    if not _under_home(target):
        return {"ok": False, "error": "path must be under $HOME"}

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        r = _run_git(["pull", "--ff-only"], cwd=target)
        if not r.get("ok"):
            return {"ok": False, "error": f"git pull failed: {r.get('stderr') or r.get('error')}"}
        return {"ok": True, "installed": True, "updated": True, "path": str(target)}

    r = _run_git(["clone", "--depth", "1", _CCB_REPO, str(target)])
    if not r.get("ok"):
        return {"ok": False, "error": f"git clone failed: {r.get('stderr') or r.get('error')}"}
    return {"ok": True, "installed": True, "updated": False, "path": str(target)}


def api_toolkit_ccb_uninstall(body: dict | None = None) -> dict[str, Any]:
    """CCB 레포 디렉터리 제거."""
    body = body or {}
    raw_path = (body.get("path") or "").strip()
    target = Path(raw_path).expanduser() if raw_path else _CCB_DEFAULT_DIR

    if not _under_home(target):
        return {"ok": False, "error": "path must be under $HOME"}
    if not target.exists():
        return {"ok": True, "removed": False, "message": "already absent"}

    # 안전성: 삭제 대상이 .git 포함 레포인지 확인 (임의 디렉터리 삭제 방지)
    if not (target / ".git").exists():
        return {"ok": False, "error": "target is not a git repo — refusing to delete"}

    try:
        shutil.rmtree(target)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"rmtree failed: {e}"}
    return {"ok": True, "removed": True, "path": str(target)}


def api_toolkit_ccb_open(body: dict | None = None) -> dict[str, Any]:
    """macOS Finder 에서 CCB 디렉터리 열기 (보너스 편의)."""
    body = body or {}
    raw_path = (body.get("path") or "").strip()
    target = Path(raw_path).expanduser() if raw_path else _CCB_DEFAULT_DIR
    if not _under_home(target) or not target.exists():
        return {"ok": False, "error": "path not found under $HOME"}
    if platform.system() != "Darwin":
        return {"ok": False, "error": "open action available on macOS only"}
    try:
        subprocess.run(["open", str(target)], check=False, timeout=5)
        return {"ok": True, "path": str(target)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
