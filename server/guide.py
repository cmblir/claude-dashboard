"""가이드 & 온보딩 — 외부 리소스 카탈로그 + 대시보드 온보딩 체크리스트.

- /api/guide/toolkit     : everything-claude-code / best-practice / wikidocs 등 툴 카탈로그 (정적)
- /api/guide/onboarding  : 사용자 ~/.claude 상태를 자동 감지해 체크리스트 진행률 계산

모든 데이터는 stdlib 만으로 생성되며 외부 호출/파일 쓰기 없음 (읽기 전용).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import (
    AGENTS_DIR, CLAUDE_HOME, CLAUDE_MD, COMMANDS_DIR,
    INSTALLED_PLUGINS_JSON, PLUGINS_DIR, SETTINGS_JSON, SKILLS_DIR,
)
from .utils import _safe_read


# ───────── 유용한 툴 카탈로그 (정적) ─────────
#
# 외부 리포/책의 URL·설치 명령·주요 카테고리를 한 화면에 모아
# 대시보드에서 그대로 복사·설치하도록 돕는다.

_TOOLKIT_SOURCES: list[dict[str, Any]] = [
    {
        "id": "everything-claude-code",
        "title": "Everything Claude Code",
        "subtitle": "멀티 플랫폼 클로드 코드 최적화 팩 (48 agents · 183 skills · 79 commands)",
        "author": "affaan-m",
        "repo": "https://github.com/affaan-m/everything-claude-code",
        "stars": "163k",
        "license": "MIT",
        "highlights": [
            "Claude Code / Cursor / Codex / OpenCode 크로스 플랫폼",
            "AgentShield 보안 감사 (1282 tests, 102 정적 룰)",
            "Continuous Learning v2 — 세션에서 인스팅크트 자동 추출",
            "토큰 최적화 (Sonnet 전환, thinking 10k cap, compact 50%)",
        ],
        "install": [
            {
                "label": "플러그인 마켓플레이스 추가 (권장)",
                "code": "/plugin marketplace add https://github.com/affaan-m/everything-claude-code",
            },
            {
                "label": "전체 프로파일 설치",
                "code": "/plugin install everything-claude-code@everything-claude-code",
            },
            {
                "label": "수동 설치 (macOS/Linux)",
                "code": "git clone https://github.com/affaan-m/everything-claude-code.git && cd everything-claude-code && ./install.sh --profile full",
            },
        ],
        "categories": [
            {
                "name": "Agents",
                "items": [
                    "planner", "architect", "code-reviewer", "security-reviewer",
                    "typescript-reviewer", "python-reviewer", "go-reviewer",
                    "build-error-resolver", "tdd-guide", "e2e-runner",
                    "doc-updater", "chief-of-staff", "loop-operator",
                ],
            },
            {
                "name": "Skills",
                "items": [
                    "frontend-patterns", "backend-patterns", "api-design",
                    "postgres-patterns", "tdd-workflow", "e2e-testing",
                    "security-review", "continuous-learning-v2",
                    "documentation-lookup", "deployment-patterns",
                ],
            },
            {
                "name": "Commands",
                "items": [
                    "/plan", "/tdd", "/code-review", "/build-fix", "/e2e",
                    "/security-scan", "/multi-plan", "/multi-execute",
                    "/instinct-import", "/instinct-export", "/sessions",
                ],
            },
            {
                "name": "Hooks",
                "items": [
                    "SessionStart — 컨텍스트 자동 로드",
                    "SessionEnd — 상태/요약 자동 저장",
                    "Edit — 포맷 검사 + console.log 경고",
                    "PreCommit — 시크릿 패턴 (sk-, ghp_, AKIA) 감지",
                ],
            },
        ],
    },
    {
        "id": "claude-code-best-practice",
        "title": "Claude Code Best Practice",
        "subtitle": "47k ⭐ · 82 가지 팁 모음 + 창시자(Boris Cherny) 워크플로",
        "author": "shanraisshan",
        "repo": "https://github.com/shanraisshan/claude-code-best-practice",
        "stars": "47k",
        "license": "MIT",
        "highlights": [
            "Agents · Commands · Skills 3축 정리",
            "핫 기능: Routines · Ultrareview · Agent Teams · Auto Mode · Computer Use",
            "Research → Plan → Execute → Review → Ship 표준 흐름",
            "prototype > PRD · PR 은 작게(median 118 lines)",
        ],
        "install": [
            {
                "label": "레포 클론 (참고용 문서)",
                "code": "git clone https://github.com/shanraisshan/claude-code-best-practice.git",
            },
        ],
        "categories": [
            {
                "name": "창시자의 핵심 팁",
                "items": [
                    "항상 Plan Mode 로 시작하라 (Boris Cherny)",
                    "컨텍스트 40% 이상은 품질 저하 — 30% 이하 유지",
                    "실패한 시도는 /rewind 로 되돌리기",
                    "/compact 는 자동보다 힌트를 직접 주고 호출",
                    "새 태스크 = 새 세션, 관련 태스크만 컨텍스트 재사용",
                ],
            },
            {
                "name": "워크플로 패턴",
                "items": [
                    "Superpowers · gstack · BMAD-METHOD · Spec Kit 참조 구현",
                    "Cross-Model: Claude Code + Codex 조합",
                    "Agent Teams — 공유 코드베이스에 병렬 에이전트",
                ],
            },
        ],
    },
    {
        "id": "oh-my-claudecode",
        "title": "OMC · oh-my-claudecode",
        "subtitle": "Claude Code 세션 안에서 슬래시 명령으로 호출하는 팀 오케스트레이션 (autopilot · ralph · ultrawork · deep-interview)",
        "author": "Yeachan-Heo",
        "repo": "https://github.com/Yeachan-Heo/oh-my-claudecode",
        "stars": "30.8k",
        "license": "MIT",
        "highlights": [
            "🎯 LazyClaude는 OMC의 4 모드를 이미 흡수 — 별도 설치 없이 워크플로우 탭의 빌트인 템플릿(bt-autopilot/ralph/ultrawork/deep-interview) 또는 런 센터에서 즉시 사용 가능",
            "외부 OMC CLI를 추가로 설치하면 Claude Code 세션 안에서도 슬래시 명령으로 호출 가능 (보완 관계, 충돌 없음)",
            "Smart routing — Haiku/Opus 자동 선택 (LazyClaude는 modelHint 'auto/fast/deep' 으로 흡수)",
            "Stop-callback — Slack/Discord/Telegram 알림 (LazyClaude는 워크플로우 notify 필드로 흡수)",
        ],
        "install": [
            {
                "label": "외부 OMC CLI 설치 (선택)",
                "code": "npm i -g oh-my-claudecode",
            },
            {
                "label": "Claude Code 세션 안에서 사용",
                "code": "/autopilot 다음 작업 자동 실행해줘",
            },
            {
                "label": "LazyClaude 흡수 기능만 쓰려면 (설치 불필요)",
                "code": "→ 워크플로우 탭 헤더의 Quick Actions 또는 런 센터의 OMC 카드",
            },
        ],
        "categories": [
            {
                "name": "LazyClaude에 흡수된 4 모드 (별도 설치 불필요)",
                "items": [
                    "/autopilot — 요구사항 → 계획 → 실행 → 검증 단일 흐름 (bt-autopilot)",
                    "/ralph — verify → fix 루프 (bt-ralph, max 5 cycles)",
                    "/ultrawork — 5 병렬 에이전트 → merge (bt-ultrawork)",
                    "/deep-interview — 소크라테스식 명확화 → 설계 (bt-deep-interview)",
                ],
            },
            {
                "name": "외부 CLI 전용 기능 (LazyClaude 흡수 안 됨)",
                "items": [
                    "터미널 status bar HUD (LazyClaude는 브라우저 대시보드 자체가 HUD)",
                    "Claude Code 세션 내부에서 직접 슬래시 명령 호출",
                    "OpenClaw Gateway 외부 연동 (LazyClaude는 Event Forwarder 탭으로 부분 대체)",
                ],
            },
        ],
    },
    {
        "id": "oh-my-codex",
        "title": "OMX · oh-my-codex",
        "subtitle": "OMC 의 Codex 버전 — Codex 세션 안에서 $ 키워드로 호출하는 워크플로우 도구",
        "author": "Yeachan-Heo",
        "repo": "https://github.com/Yeachan-Heo/oh-my-codex",
        "stars": "25.2k",
        "license": "MIT",
        "highlights": [
            "🎯 LazyClaude는 OMX의 4 명령을 정적 매핑으로 노출 — 런 센터에서 임의 프로바이더(Claude/GPT/Gemini/Ollama)로 dispatch",
            "외부 OMX CLI를 추가로 설치하면 Codex 세션 안에서 $ 키워드로 호출 가능",
            "Wiki 시스템 — 세션 내 지식 베이스 (LazyClaude는 Claude Docs Hub + Prompt Library 로 대체)",
            "Doctor 진단 — 설치 무결성 (LazyClaude는 Security Scan + AI 평가 탭으로 대체)",
        ],
        "install": [
            {
                "label": "외부 OMX CLI 설치 (선택)",
                "code": "npm i -g oh-my-codex",
            },
            {
                "label": "Codex 세션 안에서 사용",
                "code": "$doctor",
            },
            {
                "label": "LazyClaude 흡수 기능만 쓰려면 (설치 불필요)",
                "code": "→ 런 센터에서 OMX 카드 클릭",
            },
        ],
        "categories": [
            {
                "name": "LazyClaude에 흡수된 4 명령 (런 센터)",
                "items": [
                    "$doctor — 설치/헬스 진단 (의존성 · lockfile · env mismatch 체크리스트)",
                    "$wiki — 작업 컨텍스트를 1페이지 레퍼런스로 요약",
                    "$hud — 현재 상태 1-2줄 요약 (phase · last action · next blocker)",
                    "$tasks — 입력에서 actionable TODO/FIXME/BUG 추출",
                ],
            },
            {
                "name": "외부 CLI 전용 기능",
                "items": [
                    "Codex 세션 내부에서 $ 키워드 직접 호출",
                    ".omx/wiki 영구 저장소 (LazyClaude는 Prompt Library 로 대체)",
                    "omx hud --watch 터미널 라이브 갱신",
                ],
            },
        ],
    },
    {
        "id": "wikidocs-claude-code-guide",
        "title": "Claude Code 가이드 (한국어 · 위키독스)",
        "subtitle": "클래스 101 + 레퍼런스 21개 · 한국어 전체 가이드북",
        "author": "위키독스",
        "repo": "https://wikidocs.net/book/19104",
        "stars": "237 추천",
        "license": "웹/eBook",
        "highlights": [
            "설치부터 실전까지 단계별 실습 (기초 7 · 개발 17 · 비즈니스 15)",
            "크리에이터 · 연구 · 금융 · 법무/HR · 의료 특화 트랙",
            "공식 문서 변경 사항 실시간 반영 (최종 2026-04-20)",
            "창시자 워크플로, 스피너 동사 187개, 소스 분석서 별첨",
        ],
        "install": [
            {
                "label": "웹에서 바로 읽기",
                "code": "open https://wikidocs.net/book/19104",
            },
        ],
        "categories": [
            {
                "name": "클래스 101 — 기초",
                "items": [
                    "설치 · 대화와 세션 · 모델과 Effort",
                    "자율권과 안전 · 컨텍스트 관리",
                    "CLAUDE.md 작업 기억 · 첫 실전 프로젝트",
                ],
            },
            {
                "name": "클래스 101 — 개발",
                "items": [
                    "코드베이스 탐색 · TDD · 리팩토링 · Hooks",
                    "Git PR 코드리뷰 · GitHub Actions · Worktree 병렬",
                    "Skills 활용/개발 · MCP · 서브에이전트 팀 · 팀 온보딩",
                ],
            },
            {
                "name": "클래스 101 — 비즈니스",
                "items": [
                    "이메일 자동관리 · 회의록 · Excel · 보고서",
                    "일일 브리핑 · PPT 자동 · Chrome 자동화",
                    "SOP · 경쟁사 병렬분석 · Vibe Coding 앱",
                ],
            },
            {
                "name": "레퍼런스 21권",
                "items": [
                    "퀵 레퍼런스 · 설정 · 권한 · 슬래시 · 단축키",
                    "MCP · 훅 · 서브에이전트 · 스킬 · IDE · CI/CD",
                    "고급 기능 · 베스트 프랙티스 · 플러그인 · 보안/프라이버시",
                ],
            },
        ],
    },
]


# ───────── 베스트 프랙티스 (정적) ─────────

_BEST_PRACTICES: list[dict[str, Any]] = [
    {
        "id": "workflow-rpers",
        "title": "Research → Plan → Execute → Review → Ship",
        "desc": "모든 주요 작업은 이 5단계로. 각 단계마다 슬래시 명령어를 붙이면 품질이 올라간다.",
        "steps": [
            {"label": "Research", "tip": "/ask, /docs, 레포 탐색으로 맥락 먼저. 코드 쓰기 전 WHY 정리."},
            {"label": "Plan",     "tip": "/plan 또는 Plan Mode. 파일별 변경안 · 리스크 · 롤백 플랜까지."},
            {"label": "Execute",  "tip": "/tdd 로 테스트 먼저. 한 묶음씩 작게 구현 · 작은 PR 유지."},
            {"label": "Review",   "tip": "/code-review + /security-scan. 자동 리뷰 통과 후 사람 리뷰."},
            {"label": "Ship",     "tip": "/e2e 로 골든 패스 검증. 배포 후 /canary-watch 로 회귀 감시."},
        ],
    },
    {
        "id": "token-optimization",
        "title": "토큰 · 컨텍스트 최적화",
        "desc": "Claude Code 에서 비용·지연·품질 모두 개선하는 핵심 스위치 5개.",
        "steps": [
            {"label": "모델 라우팅",  "tip": "일상은 Sonnet 4.6, 무거운 분석만 Opus 4.7 — 평균 60% 비용 절감."},
            {"label": "Thinking 캡",  "tip": "extended thinking 10,000 토큰 이하로 제한. 무제한은 가성비 나쁨."},
            {"label": "Compact 시점",  "tip": "자동 95% 대신 50% 에서 직접 /compact. 품질 유지 + 캐시 친화."},
            {"label": "MCP 10개 이하", "tip": "활성 MCP 서버는 10개 이하 — 매 턴마다 도구 디스크립션 비용."},
            {"label": "Session 분리",  "tip": "새 태스크는 새 세션. 관련 태스크만 /continue 유지."},
        ],
    },
    {
        "id": "planning-habits",
        "title": "Plan Mode · 컨텍스트 습관",
        "desc": "Boris Cherny(Claude Code 창시자)가 반복 강조하는 운용 팁.",
        "steps": [
            {"label": "Plan 먼저",        "tip": "모든 비자명한 작업은 Plan Mode 로. 코드 생성 전 사용자 승인을 받는다."},
            {"label": "컨텍스트 감시",    "tip": "40% 넘어가면 품질 저하. /clear · /compact · /rewind 세 가지 스위치."},
            {"label": "Prototype > PRD",  "tip": "길게 쓴 스펙보다 20~30개의 작은 프로토타입이 빠른 수렴을 준다."},
            {"label": "작은 PR",           "tip": "PR 사이즈 median 118 lines. 커지면 쪼개라 — 리뷰 품질 & 롤백 용이."},
            {"label": "Squash Merge",     "tip": "히스토리 선형 유지. rebase 보다 squash 가 충돌 복구에 유리."},
        ],
    },
    {
        "id": "security",
        "title": "보안 · 안전 기본값",
        "desc": "로컬/개인 사용에서도 꼭 켜두면 좋은 안전 스위치.",
        "steps": [
            {"label": "Secret 훅",    "tip": "PreCommit 훅에서 sk-, ghp_, AKIA 패턴 검사 — 실수 커밋 방지."},
            {"label": "Deny 권한",    "tip": "permissions.deny 에 rm -rf /, curl | sh, ssh 등 위험 명령 차단."},
            {"label": "Auto Mode",     "tip": "개별 승인 프롬프트 대신 분류기 기반 Auto Mode 로 일관성 확보."},
            {"label": "MCP 범위",     "tip": "로컬 전용 MCP 는 OK, 인터넷 쓰는 MCP 는 allow-list / readOnly 권장."},
        ],
    },
]


# ───────── 슬래시 명령어 치트시트 ─────────

_CHEATSHEET_COMMANDS: list[dict[str, Any]] = [
    {"cmd": "/help",     "desc": "Claude Code 사용법과 명령어 전체 목록"},
    {"cmd": "/clear",    "desc": "현재 세션 컨텍스트 초기화 — 새 주제 시작 시"},
    {"cmd": "/compact",  "desc": "대화를 요약해 컨텍스트 압축 (힌트 프롬프트 동반 권장)"},
    {"cmd": "/rewind",   "desc": "마지막 턴(또는 범위)을 되돌리고 실패 시도 제거"},
    {"cmd": "/continue", "desc": "같은 태스크를 새 세션에서 이어서"},
    {"cmd": "/plan",     "desc": "Plan Mode 진입 — 코드 변경 전 승인 단계"},
    {"cmd": "/fast",     "desc": "Opus 4.6 Fast 모드 토글 (빠른 출력, 같은 모델)"},
    {"cmd": "/bug",      "desc": "버그 재현 스펙 → 실패 테스트 → 수정 자동 흐름"},
    {"cmd": "/init",     "desc": "현재 레포용 CLAUDE.md 를 자동 초기화"},
    {"cmd": "/review",   "desc": "PR 코드리뷰 — 체크리스트 기반"},
    {"cmd": "/security-review", "desc": "현재 브랜치 변경분 보안 리뷰"},
    {"cmd": "/config",   "desc": "테마·모델 등 단순 설정 빠르게 전환"},
    {"cmd": "/doctor",   "desc": "Claude Code 환경 진단 (auth/MCP/hook 상태)"},
    {"cmd": "/logout",   "desc": "현재 계정 로그아웃"},
    {"cmd": "/login",    "desc": "Claude 계정 로그인"},
    {"cmd": "/model",    "desc": "모델 변경 (Opus/Sonnet/Haiku)"},
    {"cmd": "/memory",   "desc": "프로젝트 메모리 보기/편집"},
    {"cmd": "/agents",   "desc": "사용 가능한 서브에이전트 목록"},
    {"cmd": "/hooks",    "desc": "설정된 훅 목록"},
    {"cmd": "/mcp",      "desc": "MCP 서버 목록 + 연결 상태"},
    {"cmd": "/plugin",   "desc": "플러그인 마켓플레이스 · 설치/제거"},
    {"cmd": "/statusline", "desc": "상태라인 커스터마이즈"},
    {"cmd": "/sessions", "desc": "이전 세션 리스트 · 재개"},
]

_CHEATSHEET_KEYS: list[dict[str, str]] = [
    {"key": "Shift+Tab",  "desc": "Plan Mode ↔ 실행 모드 토글"},
    {"key": "Ctrl+C",     "desc": "현재 응답/도구 실행 중단"},
    {"key": "Ctrl+D",     "desc": "Claude Code 종료"},
    {"key": "Ctrl+R",     "desc": "출력 스타일 · 토큰 디테일 토글"},
    {"key": "Ctrl+L",     "desc": "터미널 화면 클리어 (세션 유지)"},
    {"key": "Esc Esc",    "desc": "마지막 메시지 편집 (더블 Esc)"},
    {"key": "!<command>", "desc": "프롬프트 앞에 ! — 사용자 측에서 셸 실행 후 출력 공유"},
    {"key": "↑ / ↓",      "desc": "이전/다음 프롬프트 히스토리 이동"},
    {"key": "Tab",        "desc": "파일/경로 자동완성"},
]


# ───────── 온보딩 상태 진단 ─────────

def _count_dir(p: Path, pattern: str = "*") -> int:
    if not p.exists():
        return 0
    try:
        return sum(1 for _ in p.glob(pattern))
    except Exception:
        return 0


def _installed_plugins_count() -> int:
    if not INSTALLED_PLUGINS_JSON.exists():
        return 0
    try:
        data = json.loads(_safe_read(INSTALLED_PLUGINS_JSON) or "{}")
    except Exception:
        return 0
    # installed_plugins.json 스키마: {"<marketplace>": {"<plugin>": {...}}}
    total = 0
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, dict):
                total += len(v)
    return total


def _settings_has_permissions() -> bool:
    if not SETTINGS_JSON.exists():
        return False
    try:
        data = json.loads(_safe_read(SETTINGS_JSON) or "{}")
    except Exception:
        return False
    perms = data.get("permissions") if isinstance(data, dict) else None
    if not isinstance(perms, dict):
        return False
    return bool(perms.get("allow") or perms.get("deny"))


def _settings_has_hooks() -> bool:
    if not SETTINGS_JSON.exists():
        return False
    try:
        data = json.loads(_safe_read(SETTINGS_JSON) or "{}")
    except Exception:
        return False
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return False
    # 하나라도 이벤트에 훅이 걸려 있으면 True
    for v in hooks.values():
        if v:
            return True
    return False


def _claude_md_substantial() -> bool:
    """CLAUDE.md 가 100자 이상 내용을 담고 있으면 "작성된" 것으로 간주."""
    if not CLAUDE_MD.exists():
        return False
    try:
        text = _safe_read(CLAUDE_MD) or ""
    except Exception:
        return False
    return len(text.strip()) >= 100


def _mcp_count() -> int:
    """~/.claude.json 의 mcpServers 수를 합산 (프로젝트 스코프 포함)."""
    from .config import CLAUDE_JSON
    if not CLAUDE_JSON.exists():
        return 0
    try:
        data = json.loads(_safe_read(CLAUDE_JSON) or "{}")
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0
    total = 0
    servers = data.get("mcpServers")
    if isinstance(servers, dict):
        total += len(servers)
    projects = data.get("projects")
    if isinstance(projects, dict):
        for p in projects.values():
            if isinstance(p, dict):
                ps = p.get("mcpServers")
                if isinstance(ps, dict):
                    total += len(ps)
    return total


def api_guide_toolkit() -> dict[str, Any]:
    """외부 툴/가이드 카탈로그 + 베스트 프랙티스 + 치트시트."""
    return {
        "toolkits": _TOOLKIT_SOURCES,
        "bestPractices": _BEST_PRACTICES,
        "cheatsheet": {
            "commands": _CHEATSHEET_COMMANDS,
            "keys": _CHEATSHEET_KEYS,
        },
    }


def api_guide_onboarding() -> dict[str, Any]:
    """현재 ~/.claude 상태를 감지해 체크리스트를 채워서 반환.

    각 단계:
      id · title · desc · done · hint · navigate (관련 탭 id)
    """
    skills_n   = _count_dir(SKILLS_DIR)
    agents_n   = _count_dir(AGENTS_DIR, "*.md")
    commands_n = _count_dir(COMMANDS_DIR, "*.md")
    plugins_n  = _installed_plugins_count()
    mcp_n      = _mcp_count()

    steps = [
        {
            "id": "cli-installed",
            "title": "Claude Code CLI 설치",
            "desc": "`~/.claude` 디렉토리가 존재해야 모든 기능이 동작합니다.",
            "done": CLAUDE_HOME.exists(),
            "hint": "npm i -g @anthropic-ai/claude-code 또는 공식 설치 스크립트.",
            "navigate": "system",
            "doc": "https://docs.claude.com/en/docs/claude-code/overview",
        },
        {
            "id": "claude-md",
            "title": "전역 CLAUDE.md 작성",
            "desc": "모든 세션에 로드되는 개인/팀 규약. 100자 이상 작성을 권장합니다.",
            "done": _claude_md_substantial(),
            "hint": "CLAUDE.md 탭에서 편집 · `/init` 으로 자동 생성 가능.",
            "navigate": "claudemd",
            "doc": "https://docs.claude.com/en/docs/claude-code/memory",
        },
        {
            "id": "permissions",
            "title": "권한(permissions) 설정",
            "desc": "allow / deny 규칙으로 위험한 명령을 차단합니다.",
            "done": _settings_has_permissions(),
            "hint": "권한 탭에서 추천 프로파일 클릭 — rm -rf /, curl | sh 등 기본 차단.",
            "navigate": "permissions",
            "doc": "https://docs.claude.com/en/docs/claude-code/iam",
        },
        {
            "id": "hooks",
            "title": "훅(hooks) 하나 이상 설정",
            "desc": "SessionStart/Stop · PreToolUse 훅으로 자동화 · 안전장치를 추가합니다.",
            "done": _settings_has_hooks(),
            "hint": "훅 탭 · PreToolUse 에 시크릿 감지 스크립트 추천.",
            "navigate": "hooks",
            "doc": "https://docs.claude.com/en/docs/claude-code/hooks",
        },
        {
            "id": "skills",
            "title": "스킬 1개 이상 보유",
            "desc": "스킬은 클로드가 자동으로 적재하는 지식 모듈입니다.",
            "done": skills_n >= 1,
            "detail": f"{skills_n} 개 감지",
            "hint": "Everything Claude Code 설치 시 183개가 한 번에 추가됩니다.",
            "navigate": "skills",
            "doc": "https://docs.claude.com/en/docs/claude-code/skills",
        },
        {
            "id": "agents",
            "title": "서브에이전트 1개 이상",
            "desc": "특정 작업에 특화된 전담 에이전트를 만들어 두면 품질이 급상승.",
            "done": agents_n >= 1,
            "detail": f"{agents_n} 개 감지",
            "hint": "에이전트 탭 · planner / code-reviewer 먼저 만들어보세요.",
            "navigate": "agents",
            "doc": "https://docs.claude.com/en/docs/claude-code/sub-agents",
        },
        {
            "id": "commands",
            "title": "커스텀 슬래시 명령어",
            "desc": "자주 쓰는 프롬프트를 /command 로 축약 — 반복 작업 자동화.",
            "done": commands_n >= 1,
            "detail": f"{commands_n} 개 감지",
            "hint": "슬래시 명령어 탭에서 /tdd, /plan, /code-review 등 추가.",
            "navigate": "commands",
            "doc": "https://docs.claude.com/en/docs/claude-code/slash-commands",
        },
        {
            "id": "mcp",
            "title": "MCP 커넥터 1개 이상",
            "desc": "GitHub / Context7 / Playwright 등 외부 시스템 연결.",
            "done": mcp_n >= 1,
            "detail": f"{mcp_n} 개 감지",
            "hint": "MCP 탭에서 원클릭 설치 · 처음엔 context7 + github 조합 추천.",
            "navigate": "mcp",
            "doc": "https://docs.claude.com/en/docs/claude-code/mcp",
        },
        {
            "id": "plugins",
            "title": "플러그인 또는 마켓플레이스 추가",
            "desc": "Everything Claude Code 같은 번들로 한 번에 셋업.",
            "done": plugins_n >= 1,
            "detail": f"{plugins_n} 개 설치",
            "hint": "플러그인 탭 → 마켓 추가 → everything-claude-code 설치.",
            "navigate": "plugins",
            "doc": "https://docs.claude.com/en/docs/claude-code/plugins",
        },
        {
            "id": "output-style",
            "title": "출력 스타일 선택",
            "desc": "답변 톤/포맷을 프로젝트 성격에 맞게 고정.",
            "done": _count_dir(CLAUDE_HOME / "output-styles", "*") >= 1,
            "hint": "출력 스타일 탭에서 커스텀 스타일을 만들거나 기본값 확인.",
            "navigate": "outputStyles",
            "doc": "https://docs.claude.com/en/docs/claude-code/output-styles",
        },
    ]

    done_count = sum(1 for s in steps if s.get("done"))
    total = len(steps)
    pct = round(done_count / total * 100) if total else 0

    return {
        "steps": steps,
        "progress": {"done": done_count, "total": total, "percent": pct},
        "tips": [
            "모든 항목 체크 후엔 'AI 종합 평가' 탭에서 0~100 점수를 받아보세요.",
            "가이드 허브 → 유용한 툴 탭에서 한 번에 설치 가능한 팩을 찾을 수 있습니다.",
        ],
    }
