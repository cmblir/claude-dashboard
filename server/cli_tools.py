"""CLI 프로바이더 설치·상태·로그인 관리.

claude / codex / gemini / ollama 4종 CLI 에 대해
  - 설치 여부 + 버전 감지 (PATH 포함 넓은 경로 탐색)
  - brew/npm 기반 자동 설치 (macOS: AppleScript 터미널에서 sudo 없이 수행)
  - 로그인 명령을 대화형 터미널에서 실행

모든 설치·로그인은 **대화형 터미널 창** 을 연다 (사용자가 로그인·비밀번호를
입력해야 하므로 백그라운드 spawn 은 UX 가 나쁨).
"""
from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path

# ai_providers.py 와 동일한 탐지 경로
_CLI_SEARCH_PATHS: list[str] = [
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin", "/bin", "/sbin", "/usr/sbin",
    str(Path.home() / ".local/bin"),
    str(Path.home() / "bin"),
    str(Path.home() / ".bun/bin"),
    str(Path.home() / ".cargo/bin"),
    str(Path.home() / ".deno/bin"),
    "/opt/homebrew/sbin",
]


def _which(name: str) -> str:
    """PATH + 통상 설치 경로 fallback 탐지."""
    found = shutil.which(name)
    if found:
        return found
    extra_path = os.pathsep.join(_CLI_SEARCH_PATHS)
    merged = (os.environ.get("PATH", "") + os.pathsep + extra_path).strip(os.pathsep)
    found = shutil.which(name, path=merged)
    if found:
        return found
    for base in (
        Path.home() / ".nvm" / "versions" / "node",
        Path.home() / ".asdf" / "installs" / "nodejs",
        Path.home() / ".volta" / "bin",
    ):
        if not base.exists():
            continue
        if base.name == "bin":
            cand = base / name
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
            continue
        try:
            for ver in sorted(base.iterdir(), reverse=True):
                cand = ver / "bin" / name
                if cand.is_file() and os.access(cand, os.X_OK):
                    return str(cand)
        except Exception:
            pass
    return ""


# ───────── 설치 방법 카탈로그 ─────────
# 각 CLI 의 설치 방법 · 로그인 방법을 선언적으로 기록.
# installCmd 는 **단일 shell 명령**이며 AppleScript `do script` 에 그대로 전달됨.
CLI_CATALOG: dict[str, dict] = {
    "claude": {
        "label": "Claude Code CLI",
        "command": "claude",
        "homepage": "https://docs.anthropic.com/en/docs/claude-code",
        "installCmd": "npm install -g @anthropic-ai/claude-code",
        "installBrew": "brew install --cask claude-code",
        "loginCmd": "claude auth login",
        "logoutCmd": "claude auth logout",
        "versionArgs": ["--version"],
    },
    "codex": {
        "label": "Codex CLI",
        "command": "codex",
        "homepage": "https://github.com/openai/codex",
        "installCmd": "npm install -g @openai/codex",
        "installBrew": "brew install codex",
        "loginCmd": "codex login",
        "logoutCmd": "codex logout",
        "versionArgs": ["--version"],
    },
    "gemini": {
        "label": "Gemini CLI",
        "command": "gemini",
        "homepage": "https://github.com/google-gemini/gemini-cli",
        "installCmd": "npm install -g @google/gemini-cli",
        "installBrew": "brew install gemini-cli",
        "loginCmd": "gemini",  # 첫 실행 시 브라우저 OAuth 플로우
        "logoutCmd": "",
        "versionArgs": ["--version"],
    },
    "ollama": {
        "label": "Ollama",
        "command": "ollama",
        "homepage": "https://ollama.com",
        "installCmd": "curl -fsSL https://ollama.com/install.sh | sh",
        "installBrew": "brew install ollama",
        "loginCmd": "",  # 로컬 실행 · 로그인 불필요
        "logoutCmd": "",
        "versionArgs": ["--version"],
    },
}


def _cli_version(bin_path: str, args: list[str]) -> str:
    """v2.33.5 — timeout 5s → 2s (병렬 프로빙에서 한 도구가 5s 걸리면 전체 느림)."""
    if not bin_path:
        return ""
    try:
        out = subprocess.check_output(
            [bin_path, *args], text=True, timeout=2,
            env={**os.environ, "PATH": os.environ.get("PATH", "") + os.pathsep
                 + os.pathsep.join(_CLI_SEARCH_PATHS)},
        )
        return out.strip().split("\n")[0][:80]
    except Exception:
        return ""


def _brew_present() -> bool:
    return bool(_which("brew"))


def _npm_present() -> bool:
    return bool(_which("npm"))


_CLI_STATUS_CACHE: dict = {"data": None, "ts": 0.0}
# QQ135 — server-side cache for /api/cli/status. The `--version` subprocess
# fan-out (4-5 CLIs) was ~750ms on every aiProviders tab open, dominating
# the perceived load lag for that tab. CLI install state changes rarely;
# a 30s TTL is plenty and an explicit `?nocache=1` query bypasses the
# memo so the AI Providers refresh button still gets fresh data.
_CLI_STATUS_TTL_S = 30.0


def api_cli_status(query: dict | None = None) -> dict:
    """4종 CLI 의 설치 여부 · 버전 · 경로 + 설치 도구(brew/npm) 가용성.

    v2.33.5 — 도구별 프로브 + brew/npm 존재 확인을 ThreadPoolExecutor 로 병렬.
    `--version` subprocess 가 4-5 개 직렬이면 1-2초, 병렬이면 ~300ms.
    QQ135 — 30s server-side memo eliminates repeat tab-load lag.
    """
    import time as _time
    from concurrent.futures import ThreadPoolExecutor

    # query is parse_qs output → values are lists. Pull first element.
    nc = (query or {}).get("nocache")
    if isinstance(nc, list):
        nc = nc[0] if nc else None
    nocache = nc in ("1", "true", "yes", True)
    if not nocache:
        cached = _CLI_STATUS_CACHE.get("data")
        if cached is not None and (_time.time() - _CLI_STATUS_CACHE.get("ts", 0)) < _CLI_STATUS_TTL_S:
            return cached

    def _probe(item):
        tool_id, meta = item
        bin_path = _which(meta["command"])
        installed = bool(bin_path)
        version = _cli_version(bin_path, meta["versionArgs"]) if installed else ""
        return tool_id, {
            "id": tool_id,
            "label": meta["label"],
            "command": meta["command"],
            "homepage": meta["homepage"],
            "installed": installed,
            "path": bin_path,
            "version": version,
            "installCmd": meta["installCmd"],
            "installBrew": meta["installBrew"],
            "loginCmd": meta["loginCmd"],
            "logoutCmd": meta["logoutCmd"],
        }

    max_workers = max(4, len(CLI_CATALOG) + 2)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        # 도구별 프로브 + 설치자 prescence 체크 모두 병렬
        tool_futs = [ex.submit(_probe, it) for it in CLI_CATALOG.items()]
        brew_fut = ex.submit(_brew_present)
        npm_fut = ex.submit(_npm_present)
        out = dict(f.result() for f in tool_futs)
        brew_ok = brew_fut.result()
        npm_ok = npm_fut.result()

    result = {
        "tools": out,
        "brewAvailable": brew_ok,
        "npmAvailable": npm_ok,
        "platform": platform.system(),
    }
    _CLI_STATUS_CACHE["data"] = result
    _CLI_STATUS_CACHE["ts"] = _time.time()
    return result


def _run_in_terminal(cmd: str) -> dict:
    """macOS: 기본 Terminal.app 에서 cmd 실행. 그 외 플랫폼: Popen 백그라운드."""
    if not cmd.strip():
        return {"ok": False, "error": "empty command"}
    if platform.system() == "Darwin":
        # AppleScript 주입 방지를 위해 쉘 쿼팅 + 이스케이프
        escaped = cmd.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            'tell application "Terminal"\n'
            '    activate\n'
            f'    do script "{escaped}"\n'
            'end tell'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                timeout=5, capture_output=True,
            )
            return {"ok": True, "method": "terminal", "command": cmd}
        except Exception as e:
            return {"ok": False, "error": f"osascript failed: {e}"}
    # Linux / 기타 — detached subprocess
    try:
        subprocess.Popen(shlex.split(cmd), start_new_session=True)
        return {"ok": True, "method": "background", "command": cmd}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def api_cli_install(body: dict) -> dict:
    """CLI 도구 설치. body: {tool: 'claude'|'codex'|'gemini'|'ollama', method?: 'brew'|'npm'|'script'}"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    tool_id = (body.get("tool") or "").strip().lower()
    meta = CLI_CATALOG.get(tool_id)
    if not meta:
        return {"ok": False, "error": f"unknown tool: {tool_id}"}

    # 이미 설치된 경우는 빠른 반환
    existing = _which(meta["command"])
    if existing:
        return {"ok": True, "alreadyInstalled": True, "path": existing,
                "version": _cli_version(existing, meta["versionArgs"])}

    method = (body.get("method") or "").strip().lower()
    # 우선순위 결정: 명시적 method > brew (있으면) > npm / script
    if method == "brew" and _brew_present():
        cmd = meta.get("installBrew") or ""
    elif method == "npm" and _npm_present():
        cmd = meta.get("installCmd") or ""
    elif method == "script":
        cmd = meta.get("installCmd") or ""
    else:
        # 자동 선택 — ollama 는 script, 나머지는 brew 우선 → npm fallback
        if tool_id == "ollama" and platform.system() == "Darwin" and _brew_present():
            cmd = meta.get("installBrew") or meta.get("installCmd")
        elif _brew_present() and meta.get("installBrew"):
            cmd = meta["installBrew"]
        elif _npm_present() and meta.get("installCmd", "").startswith("npm "):
            cmd = meta["installCmd"]
        else:
            cmd = meta.get("installCmd") or meta.get("installBrew") or ""

    if not cmd:
        return {"ok": False, "error": "no installer available — install brew or npm first"}

    # 설치 완료 후 바로 버전 확인 메시지를 붙여서 터미널에서 즉시 피드백
    wrapped = f'echo ">>> Installing {meta["label"]}"; {cmd}; echo; echo ">>> Installed version:"; {meta["command"]} --version 2>/dev/null || echo "(not detected — reopen terminal)"'
    r = _run_in_terminal(wrapped)
    if not r.get("ok"):
        return r
    r.update({"tool": tool_id, "installedVia": cmd.split()[0]})
    return r


def api_cli_login(body: dict) -> dict:
    """CLI 도구 로그인. body: {tool}"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    tool_id = (body.get("tool") or "").strip().lower()
    meta = CLI_CATALOG.get(tool_id)
    if not meta:
        return {"ok": False, "error": f"unknown tool: {tool_id}"}

    if not _which(meta["command"]):
        return {"ok": False, "error": f"{meta['label']} is not installed yet"}

    login_cmd = meta.get("loginCmd") or ""
    if not login_cmd:
        return {"ok": True, "noLoginRequired": True,
                "message": f"{meta['label']} does not require login."}

    r = _run_in_terminal(login_cmd)
    if not r.get("ok"):
        return r
    r.update({"tool": tool_id})
    return r
