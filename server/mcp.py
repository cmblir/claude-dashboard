"""MCP 카탈로그 · 설치/삭제 · 커넥터 리스트 + `claude mcp list` 캐시.

- MCP_CATALOG: 알려진 MCP 서버 16종
- api_mcp_catalog: 카탈로그 + 현재 설치 상태
- api_mcp_install(_prepare)/remove/project_remove: `~/.claude.json` · `.mcp.json` 편집
- list_connectors: platform / local / plugin / desktop / project 분류
- `_claude_mcp_list_cached`: 5분 TTL + stale-while-revalidate 디스크 캐시
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .claude_md import get_settings
from .config import (
    CLAUDE_DESKTOP_CONFIG, CLAUDE_HOME, CLAUDE_JSON,
    PLUGINS_DIR, _env_path,
)
from .db import _db, _db_init
from .utils import _safe_read, _safe_write


# ───────── MCP 카탈로그 ─────────

MCP_CATALOG = [
    {
        "id": "context7",
        "name": "Context7",
        "description": "최신 라이브러리 문서·예제를 실시간으로 가져오는 MCP (Upstash 제공)",
        "category": "docs",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
        "cli": "claude mcp add context7 npx -y @upstash/context7-mcp",
    },
    {
        "id": "github-official",
        "name": "GitHub (공식)",
        "description": "이슈/PR/커밋/워크플로 조작. GITHUB_TOKEN 필요.",
        "category": "dev",
        "install": {"type": "stdio", "command": "docker",
                    "args": ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
                             "ghcr.io/github/github-mcp-server"]},
        "cli": "claude mcp add github -e GITHUB_PERSONAL_ACCESS_TOKEN=... -- docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN ghcr.io/github/github-mcp-server",
    },
    {
        "id": "filesystem",
        "name": "Filesystem",
        "description": "지정한 디렉토리 파일 읽기/쓰기. 보안상 allow-list 필수.",
        "category": "utility",
        "install": {"type": "stdio", "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/YOU/allowed-path"]},
        "cli": "claude mcp add filesystem npx -y @modelcontextprotocol/server-filesystem /Users/YOU/allowed-path",
    },
    {
        "id": "memory",
        "name": "Memory (knowledge graph)",
        "description": "세션 간 지식 그래프 저장 / 검색 (공식 MCP).",
        "category": "memory",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"]},
        "cli": "claude mcp add memory npx -y @modelcontextprotocol/server-memory",
    },
    {
        "id": "playwright",
        "name": "Playwright",
        "description": "실제 브라우저 자동화 (클릭/스냅샷/평가).",
        "category": "test",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@microsoft/mcp-server-playwright"]},
        "cli": "claude mcp add playwright npx -y @microsoft/mcp-server-playwright",
    },
    {
        "id": "puppeteer",
        "name": "Puppeteer",
        "description": "Playwright 대안. Chrome 자동화.",
        "category": "test",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-puppeteer"]},
        "cli": "claude mcp add puppeteer npx -y @modelcontextprotocol/server-puppeteer",
    },
    {
        "id": "brave-search",
        "name": "Brave Search",
        "description": "Brave API 기반 웹 검색. BRAVE_API_KEY 필요.",
        "category": "search",
        "install": {"type": "stdio", "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-brave-search"],
                    "env": {"BRAVE_API_KEY": ""}},
        "cli": "claude mcp add brave-search -e BRAVE_API_KEY=... -- npx -y @modelcontextprotocol/server-brave-search",
    },
    {
        "id": "fetch",
        "name": "Fetch",
        "description": "URL 가져오기 (HTML → 텍스트/마크다운 변환).",
        "category": "utility",
        "install": {"type": "stdio", "command": "uvx", "args": ["mcp-server-fetch"]},
        "cli": "claude mcp add fetch uvx mcp-server-fetch",
    },
    {
        "id": "sqlite",
        "name": "SQLite",
        "description": "로컬 SQLite DB 쿼리 실행.",
        "category": "db",
        "install": {"type": "stdio", "command": "uvx",
                    "args": ["mcp-server-sqlite", "--db-path", "/absolute/path.db"]},
        "cli": "claude mcp add sqlite uvx mcp-server-sqlite --db-path /absolute/path.db",
    },
    {
        "id": "postgres",
        "name": "PostgreSQL",
        "description": "읽기 전용 Postgres 쿼리.",
        "category": "db",
        "install": {"type": "stdio", "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-postgres",
                             "postgresql://user:pass@host/db"]},
        "cli": "claude mcp add postgres npx -y @modelcontextprotocol/server-postgres postgresql://user:pass@host/db",
    },
    {
        "id": "slack",
        "name": "Slack",
        "description": "Slack 메시지 조회/전송. SLACK_BOT_TOKEN 필요.",
        "category": "messaging",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-slack"],
                    "env": {"SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""}},
        "cli": "claude mcp add slack -e SLACK_BOT_TOKEN=... -e SLACK_TEAM_ID=... -- npx -y @modelcontextprotocol/server-slack",
    },
    {
        "id": "google-drive",
        "name": "Google Drive",
        "description": "Drive 검색 / 파일 가져오기 (OAuth 설정 필요).",
        "category": "productivity",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-gdrive"]},
        "cli": "claude mcp add gdrive npx -y @modelcontextprotocol/server-gdrive",
    },
    {
        "id": "sequential-thinking",
        "name": "Sequential Thinking",
        "description": "단계적 추론 프레임. 복잡한 설계 문제 정리용.",
        "category": "reasoning",
        "install": {"type": "stdio", "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]},
        "cli": "claude mcp add seq-think npx -y @modelcontextprotocol/server-sequential-thinking",
    },
    {
        "id": "exa",
        "name": "Exa Search",
        "description": "AI 네이티브 웹 검색. EXA_API_KEY 필요.",
        "category": "search",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "exa-mcp-server"],
                    "env": {"EXA_API_KEY": ""}},
        "cli": "claude mcp add exa -e EXA_API_KEY=... -- npx -y exa-mcp-server",
    },
    {
        "id": "linear",
        "name": "Linear",
        "description": "Linear 이슈/프로젝트 관리.",
        "category": "pm",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "linear-mcp"],
                    "env": {"LINEAR_API_KEY": ""}},
        "cli": "claude mcp add linear -e LINEAR_API_KEY=... -- npx -y linear-mcp",
    },
    {
        "id": "notion",
        "name": "Notion",
        "description": "Notion 페이지 검색/편집.",
        "category": "productivity",
        "install": {"type": "stdio", "command": "npx", "args": ["-y", "@makenotion/notion-mcp-server"],
                    "env": {"INTERNAL_INTEGRATION_TOKEN": ""}},
        "cli": "claude mcp add notion -e INTERNAL_INTEGRATION_TOKEN=... -- npx -y @makenotion/notion-mcp-server",
    },
]


# ───────── placeholder 치환 ─────────

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}|<([A-Za-z_][A-Za-z0-9_-]*)>|YOUR_([A-Z_]+)")


def _extract_placeholders(spec: dict) -> list:
    """install spec 에서 미설정 환경변수/플레이스홀더 추출.

    반환: [{key, where, raw, hint?}]
    """
    out: list = []
    seen: set[str] = set()

    def _scan(val, where: str):
        if isinstance(val, str):
            for m in _PLACEHOLDER_RE.finditer(val):
                key = m.group(1) or m.group(2) or m.group(3) or ""
                if key and key not in seen:
                    seen.add(key)
                    out.append({"key": key, "where": where, "raw": val})
            if "/Users/YOU" in val or "/Users/YOUR" in val:
                if "PATH" not in seen:
                    seen.add("PATH")
                    out.append({"key": "PATH", "where": where, "raw": val,
                                "hint": "허용할 디렉토리 절대경로 (예: /Users/yoo/projects)"})
        elif isinstance(val, list):
            for i, v in enumerate(val):
                _scan(v, f"{where}[{i}]")
        elif isinstance(val, dict):
            for k, v in val.items():
                _scan(v, f"{where}.{k}")

    _scan(spec.get("command", ""), "command")
    _scan(spec.get("args", []), "args")
    _scan(spec.get("env", {}), "env")
    return out


def _substitute_placeholders(spec: dict, values: dict) -> dict:
    """values = {placeholder_key: user_input} 로 spec 치환."""
    def _sub(val):
        if isinstance(val, str):
            r = val
            for k, v in (values or {}).items():
                r = r.replace(f"${{{k}}}", str(v))
                r = r.replace(f"<{k}>", str(v))
                r = r.replace(f"YOUR_{k}", str(v))
            if "PATH" in (values or {}):
                r = r.replace("/Users/YOU/allowed-path", str(values["PATH"]))
                r = r.replace("/Users/YOUR/allowed-path", str(values["PATH"]))
                r = r.replace("/Users/YOU", str(values["PATH"]).rstrip("/"))
            return r
        if isinstance(val, list):
            return [_sub(v) for v in val]
        if isinstance(val, dict):
            return {k: _sub(v) for k, v in val.items()}
        return val
    return _sub(spec)


# ───────── `claude mcp list` 캐시 ─────────

_MCP_LIST_CACHE_FILE = _env_path(
    "CLAUDE_DASHBOARD_MCP_CACHE",
    Path.home() / ".claude-dashboard-mcp-cache.json",
)
_MCP_LIST_CACHE = {"ts": 0.0, "status": {}, "url": {}}
_MCP_LIST_TTL = 300.0  # 5분 — 거의 안 바뀜
_MCP_LIST_LOCK = threading.Lock()
_MCP_LIST_REFRESH_LOCK = threading.Lock()  # 단일 in-flight refresh

# 디스크 캐시 로드 (서버 재시작해도 즉시 사용 가능)
try:
    if _MCP_LIST_CACHE_FILE.exists():
        _disk = json.loads(_MCP_LIST_CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(_disk, dict):
            _MCP_LIST_CACHE["status"] = _disk.get("status", {}) or {}
            _MCP_LIST_CACHE["url"] = _disk.get("url", {}) or {}
            _MCP_LIST_CACHE["ts"] = float(_disk.get("ts", 0) or 0)
except Exception:
    pass


def _refresh_mcp_list_blocking() -> tuple[dict, dict]:
    """실제 `claude mcp list` 호출 (단일 in-flight 보장)."""
    if not _MCP_LIST_REFRESH_LOCK.acquire(blocking=False):
        with _MCP_LIST_REFRESH_LOCK:
            return _MCP_LIST_CACHE["status"], _MCP_LIST_CACHE["url"]
    try:
        cli_status: dict = {}
        cli_url: dict = {}
        claude_bin = shutil.which("claude")
        if claude_bin:
            try:
                proc = subprocess.run(
                    [claude_bin, "mcp", "list"],
                    capture_output=True, text=True, timeout=12,
                )
                for line in (proc.stdout or "").splitlines():
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    m = re.match(r"^(.+?):\s+(.+?)\s+-\s+(.+)$", line)
                    if not m:
                        continue
                    name, endpoint, status = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
                    cli_status[name] = status
                    cli_url[name] = endpoint
            except Exception:
                pass
        with _MCP_LIST_LOCK:
            _MCP_LIST_CACHE["status"] = cli_status
            _MCP_LIST_CACHE["url"] = cli_url
            _MCP_LIST_CACHE["ts"] = time.time()
        try:
            _MCP_LIST_CACHE_FILE.write_text(
                json.dumps({"status": cli_status, "url": cli_url,
                            "ts": _MCP_LIST_CACHE["ts"]}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
        return cli_status, cli_url
    finally:
        _MCP_LIST_REFRESH_LOCK.release()


def _claude_mcp_list_cached() -> tuple[dict, dict]:
    """5분 캐시 + stale-while-revalidate. 캐시 있으면 절대 블로킹 안 함."""
    now = time.time()
    with _MCP_LIST_LOCK:
        has_cache = _MCP_LIST_CACHE["ts"] > 0
        fresh = (now - _MCP_LIST_CACHE["ts"]) < _MCP_LIST_TTL
        cached = (_MCP_LIST_CACHE["status"], _MCP_LIST_CACHE["url"])
    if has_cache and fresh:
        return cached
    if has_cache:
        def _bg():
            try:
                _refresh_mcp_list_blocking()
            except Exception:
                pass
        threading.Thread(target=_bg, daemon=True).start()
        return cached
    return _refresh_mcp_list_blocking()


def warmup_caches() -> None:
    """부팅 시 호출 — 첫 요청의 6초 지연을 제거한다."""
    def _run():
        try:
            t0 = time.time()
            _claude_mcp_list_cached()
            from .logger import log
            log.info("warmup mcp list: %.2fs", time.time() - t0)
        except Exception as e:
            from .logger import log
            log.warning("warmup failed: %s", e)
    threading.Thread(target=_run, daemon=True).start()


# ───────── 카탈로그 API ─────────

def api_mcp_catalog() -> dict:
    """알려진 MCP 카탈로그 + 현재 설치 상태."""
    installed = list_connectors()
    installed_names: set[str] = set()
    for m in (installed.get("local", []) + installed.get("platform", [])):
        installed_names.add(m["name"])
    out: list = []
    for entry in MCP_CATALOG:
        out.append({**entry, "installed": entry["id"] in installed_names
                    or entry["name"].lower().replace(" ", "-") in installed_names})
    return {"catalog": out, "installedCount": len(installed_names)}


# ───────── 설치/삭제 ─────────

def api_mcp_install_prepare(body: dict) -> dict:
    """설치 전 플레이스홀더 목록을 돌려줌 → 프런트가 값을 받아 install 호출."""
    if not isinstance(body, dict):
        return {"error": "bad body"}
    entry_id = body.get("id") or ""
    spec = next((x for x in MCP_CATALOG if x["id"] == entry_id), None)
    if not spec:
        return {"error": "unknown mcp id"}
    placeholders = _extract_placeholders(spec.get("install", {}))
    return {"id": entry_id, "name": spec.get("name"), "placeholders": placeholders,
            "preview": spec.get("install", {})}


def api_mcp_install(body: dict) -> dict:
    """~/.claude.json 의 mcpServers 에 엔트리 병합 저장.

    body: { "id": "context7", "as": "my-context7" (선택), "values": {PATH:"...", GITHUB_TOKEN:"..."} }
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    entry_id = body.get("id") or ""
    as_name = (body.get("as") or entry_id).strip()
    values = body.get("values") or {}
    spec = next((x for x in MCP_CATALOG if x["id"] == entry_id), None)
    if not spec:
        return {"ok": False, "error": "unknown mcp id"}
    install_spec = dict(spec["install"])
    placeholders = _extract_placeholders(install_spec)
    missing = [p["key"] for p in placeholders if not values.get(p["key"])]
    if missing:
        from .errors import err
        return {"ok": False, "error": f"필수 값 누락: {', '.join(missing)}", "error_key": "err_mcp_values_missing",
                "placeholders": placeholders}
    install_spec = _substitute_placeholders(install_spec, values)

    if not CLAUDE_JSON.exists():
        return {"ok": False, "error": "~/.claude.json 없음. `claude auth login` 먼저 실행.", "error_key": "err_no_claude_json"}
    try:
        data = json.loads(_safe_read(CLAUDE_JSON, 500000))
    except Exception as e:
        return {"ok": False, "error": f".claude.json 파싱 실패: {e}"}
    mcp_servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
        data["mcpServers"] = mcp_servers
    if as_name in mcp_servers:
        return {"ok": False, "error": f"이미 '{as_name}' 이름으로 등록됨 — 다른 이름으로 시도하세요.", "error_key": "err_mcp_already_registered"}
    mcp_servers[as_name] = install_spec
    text = json.dumps(data, indent=2, ensure_ascii=False)
    ok = _safe_write(CLAUDE_JSON, text)
    if ok:
        _MCP_LIST_CACHE["ts"] = 0
    return {"ok": ok, "name": as_name, "installed": install_spec,
            "note": "Claude Code 를 새 세션에서 이 MCP 호출 시 활성화. 필요 시 재시작."}


def api_mcp_remove(body: dict) -> dict:
    name = (body or {}).get("name") if isinstance(body, dict) else None
    if not name:
        return {"ok": False, "error": "name required"}
    if not CLAUDE_JSON.exists():
        return {"ok": False, "error": "~/.claude.json 없음", "error_key": "err_no_claude_json"}
    try:
        data = json.loads(_safe_read(CLAUDE_JSON, 500000))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict) or name not in servers:
        return {"ok": False, "error": f"등록된 MCP 서버가 아닙니다: {name}", "error_key": "err_mcp_not_registered"}
    removed = servers.pop(name)
    ok = _safe_write(CLAUDE_JSON, json.dumps(data, indent=2, ensure_ascii=False))
    if ok:
        _MCP_LIST_CACHE["ts"] = 0
    return {"ok": ok, "removed": removed}


def api_mcp_project_remove(body: dict) -> dict:
    """프로젝트 .mcp.json 에서 엔트리 삭제. body: { cwd, name }"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    cwd = (body.get("cwd") or "").strip()
    name = (body.get("name") or "").strip()
    if not cwd or not name:
        return {"ok": False, "error": "cwd 와 name 필수", "error_key": "err_mcp_cwd_name_required"}
    abs_cwd = Path(os.path.abspath(os.path.expanduser(cwd)))
    home = Path.home().resolve()
    try:
        abs_cwd.relative_to(home)
    except ValueError:
        return {"ok": False, "error": "홈 디렉토리 밖 경로 거부", "error_key": "err_outside_home"}
    mcp_file = abs_cwd / ".mcp.json"
    if not mcp_file.exists():
        return {"ok": False, "error": f"{mcp_file} 없음"}
    try:
        data = json.loads(_safe_read(mcp_file, 500000))
    except Exception as e:
        return {"ok": False, "error": f".mcp.json 파싱 실패: {e}"}
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict) or name not in servers:
        return {"ok": False, "error": f"'{name}' 가 {mcp_file} 에 없음"}
    removed = servers.pop(name)
    ok = _safe_write(mcp_file, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    if ok:
        _MCP_LIST_CACHE["ts"] = 0
    return {"ok": ok, "removed": removed, "configPath": str(mcp_file)}


# ───────── 커넥터 리스트 ─────────

def _scan_project_mcp() -> list:
    """사용자 home 안의 .mcp.json 파일들 → 프로젝트 범위 MCP 리스트."""
    out: list = []
    seen_paths: set[str] = set()
    candidates: set = set()
    try:
        _db_init()
        with _db() as c:
            for r in c.execute("SELECT DISTINCT cwd FROM sessions WHERE cwd != ''").fetchall():
                if r["cwd"]:
                    candidates.add(r["cwd"])
    except Exception:
        pass
    for cwd in candidates:
        p = Path(cwd) / ".mcp.json"
        if not p.exists() or str(p) in seen_paths:
            continue
        seen_paths.add(str(p))
        try:
            data = json.loads(_safe_read(p))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        mcp_servers = data.get("mcpServers", {}) or {}
        for name, cfg in mcp_servers.items():
            if not isinstance(cfg, dict):
                continue
            placeholders = _extract_placeholders(cfg)
            unresolved = [pl for pl in placeholders if not os.environ.get(pl["key"])]
            out.append({
                "id": name, "name": name,
                "scope": "project",
                "projectCwd": cwd,
                "configPath": str(p),
                "command": cfg.get("command", ""),
                "args": cfg.get("args", []),
                "env": cfg.get("env", {}),
                "description": cfg.get("description", ""),
                "missingEnv": [pl["key"] for pl in unresolved],
                "connected": None,
                "needsAuth": bool(unresolved),
                "endpoint": cfg.get("command", "") + (" " + " ".join(cfg.get("args") or []) if cfg.get("args") else ""),
                "enabled": True,
                "tools": [],
            })
    return out


def list_connectors() -> dict:
    """MCP 커넥터 분류.

    - platform: claude.ai 플랫폼 연결
    - local:    ~/.claude.json mcpServers (Claude Code CLI)
    - plugin:   활성 플러그인이 제공하는 MCP ('plugin:' 접두사)
    - desktop:  Claude Desktop 앱의 claude_desktop_config.json
    - project:  프로젝트별 .mcp.json
    """
    platform_list: list = []
    local: list = []
    plugin_list: list = []
    desktop_list: list = []

    local_cfg: dict = {}
    if CLAUDE_JSON.exists():
        try:
            data = json.loads(_safe_read(CLAUDE_JSON))
        except Exception:
            data = {}
        mcp = data.get("mcpServers", {}) if isinstance(data, dict) else {}
        if isinstance(mcp, dict):
            local_cfg = mcp

    if CLAUDE_DESKTOP_CONFIG.exists():
        try:
            d_data = json.loads(_safe_read(CLAUDE_DESKTOP_CONFIG))
        except Exception:
            d_data = {}
        d_mcp = d_data.get("mcpServers", {}) if isinstance(d_data, dict) else {}
        if isinstance(d_mcp, dict):
            for name, cfg in d_mcp.items():
                if not isinstance(cfg, dict):
                    cfg = {}
                desktop_list.append({
                    "id": name, "name": name, "scope": "desktop",
                    "type": cfg.get("type", "stdio"),
                    "command": cfg.get("command", ""),
                    "args": cfg.get("args", []),
                    "env": {k: ("***" if any(s in k.lower() for s in ("key", "token", "secret", "password")) else v)
                            for k, v in (cfg.get("env") or {}).items()},
                    "endpoint": cfg.get("command", "") + (" " + " ".join(cfg.get("args") or []) if cfg.get("args") else ""),
                    "enabled": True, "tools": [],
                    "connected": None, "needsAuth": False,
                    "configPath": str(CLAUDE_DESKTOP_CONFIG),
                })

    cli_status, cli_url = _claude_mcp_list_cached()

    # needs-auth 캐시 (플랫폼 MCP fallback)
    auth_cache_path = CLAUDE_HOME / "mcp-needs-auth-cache.json"
    needs_auth: dict = {}
    if auth_cache_path.exists():
        try:
            needs_auth = json.loads(_safe_read(auth_cache_path)) or {}
        except Exception:
            needs_auth = {}

    seen: set = set()

    for name, status in cli_status.items():
        seen.add(name)
        endpoint = cli_url.get(name, "")
        connected = "Connected" in status or "✓" in status
        needs_auth_flag = "auth" in status.lower() or "✗" in status or name in needs_auth
        entry = {
            "id": name, "name": name,
            "endpoint": endpoint,
            "status": status,
            "connected": connected,
            "needsAuth": needs_auth_flag,
            "enabled": True,
            "tools": [],
        }
        if name.startswith("claude.ai ") or name.startswith("claude_ai_") or name.startswith("anthropic_"):
            entry["scope"] = "platform"
            platform_list.append(entry)
        elif name.startswith("plugin:"):
            entry["scope"] = "plugin"
            plugin_list.append(entry)
        else:
            cfg = local_cfg.get(name, {}) if isinstance(local_cfg, dict) else {}
            entry["scope"] = "user"
            entry["type"] = cfg.get("type", "stdio")
            entry["command"] = cfg.get("command", "")
            entry["args"] = cfg.get("args", [])
            entry["env"] = cfg.get("env", {})
            local.append(entry)

    # cli 가 없거나 누락된 항목 보강
    for name, cfg in (local_cfg or {}).items():
        if name in seen:
            continue
        if not isinstance(cfg, dict):
            cfg = {}
        local.append({
            "id": name, "name": name,
            "type": cfg.get("type", "stdio"),
            "command": cfg.get("command", ""),
            "args": cfg.get("args", []),
            "env": cfg.get("env", {}),
            "scope": "user", "enabled": True, "tools": [],
            "connected": None, "needsAuth": False, "endpoint": "",
        })

    # needs-auth 캐시에서만 확인되는 platform 항목 보강 (claude CLI 미설치 fallback)
    for name in needs_auth.keys():
        if name in seen:
            continue
        if name.startswith("claude.ai ") or name.startswith("claude_ai_"):
            platform_list.append({
                "id": name, "name": name, "scope": "platform",
                "endpoint": "", "status": "Needs authentication",
                "connected": False, "needsAuth": True, "enabled": True, "tools": [],
            })

    project_list = _scan_project_mcp()
    return {"platform": platform_list, "local": local, "plugin": plugin_list,
            "desktop": desktop_list, "project": project_list}


# v2.33.7 — MCP health probe
#
# Non-intrusive: stdio 서버는 command 바이너리 존재 여부만 확인 (spawn 하지 않음).
# HTTP / SSE 서버는 짧은 GET 으로 status 확인. 결과는 { id: { status, note } }.
def api_mcp_health(_q: dict | None = None) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    import urllib.request
    import urllib.error

    out: dict = {}
    conns = list_connectors()
    items: list = []
    for group in ("local", "desktop", "project", "plugin"):
        for c in conns.get(group, []):
            items.append(c)

    def _probe(c):
        cid = c.get("id") or c.get("name") or ""
        ctype = (c.get("type") or "").lower()
        if ctype in ("http", "sse"):
            # URL 기반 probe
            url = c.get("url") or c.get("endpoint") or ""
            if not url or not url.startswith(("http://", "https://")):
                return cid, {"status": "unknown", "note": "no url"}
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=3) as r:
                    return cid, {"status": "ok", "note": f"HTTP {r.status}"}
            except urllib.error.HTTPError as e:
                # 4xx 가 와도 서버는 살아있음 (auth 등)
                return cid, {"status": "ok" if 400 <= e.code < 500 else "offline",
                             "note": f"HTTP {e.code}"}
            except Exception as e:  # noqa: BLE001
                return cid, {"status": "offline", "note": str(e)[:80]}
        # stdio — command 바이너리 존재만 확인
        cmd = c.get("command") or ""
        if not cmd:
            return cid, {"status": "unknown", "note": "no command"}
        exists = shutil.which(cmd) or (os.path.exists(cmd) and os.access(cmd, os.X_OK))
        if exists:
            return cid, {"status": "ok", "note": "binary present"}
        return cid, {"status": "offline", "note": "command not found"}

    with ThreadPoolExecutor(max_workers=min(16, max(4, len(items)))) as ex:
        for cid, res in ex.map(_probe, items):
            out[cid] = res
    return {"ok": True, "health": out, "ts": int(time.time() * 1000)}
