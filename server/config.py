"""경로 상수 · 환경 변수 로드.

모든 Path 는 환경 변수로 오버라이드 가능해 개인정보·시스템 차이를 흡수한다.
이 모듈은 stdlib 만 의존하며, 다른 server.* 모듈보다 먼저 import 되어야 한다.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# ───────── 루트 ─────────
ROOT = Path(__file__).resolve().parent.parent  # server/ 의 부모 = 프로젝트 루트
DIST = ROOT / "dist"


def _load_dotenv(p: Path) -> None:
    """`.env` 파일을 읽어 현재 프로세스 환경 변수에 반영. 이미 설정된 키는 유지."""
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


# 모듈 import 시점에 바로 .env 로드 — 이후 _env_path() 호출들이 올바른 값을 읽도록.
_load_dotenv(ROOT / ".env")


def _env_path(key: str, default: Path) -> Path:
    """환경 변수에 경로가 설정되어 있으면 확장·절대화해서 반환, 아니면 기본값."""
    v = os.environ.get(key)
    return Path(os.path.expanduser(v)).resolve() if v else default


def _cwd_to_slug(cwd: Path) -> str:
    """Claude Code 의 프로젝트 슬러그 규칙: '/' → '-', 선두에 '-' 추가."""
    return "-" + str(cwd).strip("/").replace("/", "-")


# ───────── ~/.claude 자원 경로 ─────────
CLAUDE_HOME = _env_path("CLAUDE_HOME", Path.home() / ".claude")
CLAUDE_MD = CLAUDE_HOME / "CLAUDE.md"
SETTINGS_JSON = CLAUDE_HOME / "settings.json"
SKILLS_DIR = CLAUDE_HOME / "skills"
AGENTS_DIR = CLAUDE_HOME / "agents"
COMMANDS_DIR = CLAUDE_HOME / "commands"
PROJECTS_DIR = CLAUDE_HOME / "projects"
PLUGINS_DIR = CLAUDE_HOME / "plugins"
INSTALLED_PLUGINS_JSON = PLUGINS_DIR / "installed_plugins.json"
KNOWN_MARKETPLACES_JSON = PLUGINS_DIR / "known_marketplaces.json"
SESSIONS_DIR = CLAUDE_HOME / "sessions"
SESSION_DATA_DIR = CLAUDE_HOME / "session-data"
TODOS_DIR = CLAUDE_HOME / "todos"
TASKS_DIR = CLAUDE_HOME / "tasks"
SCHEDULED_TASKS_DIR = CLAUDE_HOME / "scheduled-tasks"
HISTORY_JSONL = CLAUDE_HOME / "history.jsonl"

# ───────── Claude 전역 JSON ─────────
CLAUDE_JSON = _env_path("CLAUDE_JSON", Path.home() / ".claude.json")
CLAUDE_DESKTOP_CONFIG = _env_path(
    "CLAUDE_DESKTOP_CONFIG",
    Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
)

# ───────── 대시보드 전용 경로 ─────────
MEMORY_DIR = _env_path(
    "CLAUDE_DASHBOARD_MEMORY_DIR",
    CLAUDE_HOME / "projects" / _cwd_to_slug(ROOT) / "memory",
)
DB_PATH = _env_path("CLAUDE_DASHBOARD_DB", Path.home() / ".claude-dashboard.db")
TRANSLATIONS_PATH = _env_path(
    "CLAUDE_DASHBOARD_TRANSLATIONS", Path.home() / ".claude-dashboard-translations.json"
)
DASHBOARD_CONFIG_PATH = _env_path(
    "CLAUDE_DASHBOARD_CONFIG", Path.home() / ".claude-dashboard-config.json"
)
WORKFLOWS_PATH = _env_path(
    "CLAUDE_DASHBOARD_WORKFLOWS", Path.home() / ".claude-dashboard-workflows.json"
)

# ───────── 세션 점수 필터 ─────────
# 도구 호출이 적은(=짧거나 시범) 세션을 점수 평균에서 제외해 UX 노이즈를 줄인다.
SCORE_MIN_TOOLS = int(os.environ.get("SCORE_MIN_TOOLS", "11"))

# ───────── 자주 쓰는 regex ─────────
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def get_bind() -> tuple[str, int]:
    """HOST/PORT 환경 변수를 읽어 (host, port) 반환. 기본 127.0.0.1:8080."""
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    return host, port
