"""대시보드 탭 카탈로그 — 챗봇 안내가 참조하는 단일 진실.

새로운 탭을 추가하거나 기존 탭 설명을 고칠 때는 **이 파일만 수정**하면
`_CHAT_SYSTEM_PROMPT` 가 자동으로 갱신되어 챗봇이 최신 기능을 알게 된다.

각 엔트리:
    (id, group, desc, keywords)

- id        : 프론트 NAV 배열과 1:1 매칭
- group     : 탭이 속한 그룹 (new / main / work / config / advanced / system)
- desc      : 챗봇 프롬프트에 들어갈 한 줄 설명
- keywords  : 이 탭으로 라우팅해야 할 사용자 질문 키워드 (선택)
"""

# 그룹 라벨
TAB_GROUPS = [
    ("new",      "신기능 그룹"),
    ("main",     "메인"),
    ("work",     "작업 자원"),
    ("config",   "설정 & 구성"),
    ("advanced", "고급"),
    ("system",   "시스템 & 관측"),
]


# (id, group, desc, keywords)
TAB_CATALOG: list[tuple[str, str, str, list[str]]] = [
    # ── 신기능 ─────────────────────────────────────
    ("features",      "new",      "신기능 — Anthropic 최신 발표 카드",
        ["신기능", "Anthropic 발표", "최신 기능"]),
    ("onboarding",    "new",      "시작하기 — ~/.claude 상태 실시간 감지 단계별 체크리스트",
        ["시작하기", "온보딩", "checklist", "체크리스트"]),
    ("guideHub",      "new",      "가이드 & 툴 — 외부 가이드·유용한 툴·베스트 프랙티스·치트시트",
        ["가이드", "치트시트", "cheatsheet", "베스트 프랙티스"]),

    # ── 메인 ───────────────────────────────────────
    ("overview",      "main",     "개요 · 최적화 점수 · 시스템 요약",
        ["개요", "점수", "최적화"]),
    ("projects",      "main",     "프로젝트별 Claude 세팅 · AI 추천 · CLAUDE.md 관리",
        ["프로젝트", "CLAUDE.md"]),
    ("analytics",     "main",     "통계 & 스코어 · 30일 타임라인 · 도구 분포",
        ["통계", "스코어", "analytics"]),
    ("aiEval",        "main",     "AI 종합 평가 — Claude 가 전체 셋업 진단",
        ["평가", "evaluation"]),
    ("sessions",      "main",     "세션 히스토리 · 과거 대화 검색 · 세션 품질 스코어",
        ["세션 히스토리", "대화 검색"]),

    # ── 작업 자원 ───────────────────────────────────
    ("workflows",     "work",
        "워크플로우 — n8n 스타일 DAG 에디터. 세션 노드 생성·포트 드래그 연결·실행·"
        "세션 하네스(페르소나/허용 도구/resume)·🔁 Repeat 자동 반복·📋 템플릿"
        "(팀 개발/리서치/병렬 3) + 커스텀 템플릿 저장·🖥️ Terminal 새 세션 spawn·"
        "📜 실행 이력·🎬 14장면 인터랙티브 튜토리얼",
        ["워크플로우", "workflow", "DAG", "repeat", "반복", "피드백", "스케줄",
         "팀 개발", "리드", "프론트", "백엔드", "병렬", "노드", "포트", "드래그",
         "하네스", "persona", "페르소나", "spawn", "resume", "템플릿", "template",
         "loop", "루프", "retry", "재시도", "error handler", "에러 핸들러",
         "webhook", "cron", "스케줄러", "import", "export"]),
    ("aiProviders",   "work",
        "AI 프로바이더 — Claude/GPT/Gemini/Ollama/Codex 멀티 AI 관리. "
        "API 키 설정, CLI 감지, 커스텀 프로바이더 등록, 폴백 체인, 연결 테스트, "
        "임베딩(bge-m3 등), 비용 분석 차트, 멀티 AI 비교",
        ["프로바이더", "provider", "AI 프로바이더", "멀티 AI", "GPT", "Gemini",
         "Ollama", "Codex", "OpenAI", "API 키", "폴백", "임베딩", "embedding",
         "bge-m3", "비용", "cost", "비교", "compare"]),
    ("agents",        "work",     "에이전트 목록 · 상호작용 그래프 (vis-network)",
        ["에이전트", "agent", "상호작용 그래프"]),
    ("projectAgents", "work",     "프로젝트별 서브 에이전트 관리 · 16 역할 프리셋",
        ["서브에이전트", "subagent", "프로젝트 에이전트"]),
    ("skills",        "work",     "사용자 정의 스킬 보기/편집",
        ["스킬", "skill"]),
    ("commands",      "work",     "슬래시 명령어 목록",
        ["슬래시", "슬래시 명령어", "slash"]),

    # ── 설정 & 구성 ─────────────────────────────────
    ("hooks",         "config",   "이벤트 훅 설정",
        ["훅", "hook"]),
    ("permissions",   "config",   "도구 권한 관리",
        ["권한", "permission", "allow", "deny"]),
    ("mcp",           "config",   "MCP 커넥터 · 외부 도구 연결",
        ["MCP", "커넥터"]),
    ("plugins",       "config",   "플러그인 관리",
        ["플러그인", "plugin"]),
    ("settings",      "config",   "settings.json 직접 편집",
        ["settings", "세팅"]),
    ("claudemd",      "config",   "CLAUDE.md 편집 (마크다운 프리뷰)",
        ["CLAUDE.md"]),

    # ── 고급 ───────────────────────────────────────
    ("outputStyles",  "advanced", "출력 스타일 커스터마이즈",
        ["출력 스타일", "output style"]),
    ("statusline",    "advanced", "상태라인 · 키바인딩",
        ["상태라인", "statusline", "키바인딩"]),
    ("plans",         "advanced", "플랜 보관소",
        ["플랜", "plan mode"]),
    ("envConfig",     "advanced", "환경 변수",
        ["환경 변수", "env"]),
    ("modelConfig",   "advanced", "모델 설정",
        ["모델 설정"]),
    ("ideStatus",     "advanced", "IDE 통합 상태",
        ["IDE", "VS Code", "JetBrains"]),
    ("marketplaces",  "advanced", "마켓플레이스 관리",
        ["마켓플레이스", "marketplace"]),
    ("scheduled",     "advanced", "예약된 작업",
        ["예약", "scheduled"]),

    # ── 시스템 & 관측 ───────────────────────────────
    ("usage",         "system",   "사용량 / 비용 추정",
        ["사용량", "비용", "usage"]),
    ("metrics",       "system",   "토큰 메트릭 상세 시계열",
        ["메트릭", "token", "토큰"]),
    ("memory",        "system",   "프로젝트 메모리 관리",
        ["메모리", "memory"]),
    ("tasks",         "system",   "태스크 / TODO 관리",
        ["태스크", "TODO"]),
    ("backups",       "system",   "백업 / 파일 히스토리",
        ["백업", "backup"]),
    ("bashHistory",   "system",   "셸 명령 기록",
        ["bash", "셸 명령"]),
    ("telemetry",     "system",   "텔레메트리 로그",
        ["텔레메트리", "telemetry"]),
    ("homunculus",    "system",   "Homunculus 프로젝트 추적기",
        ["Homunculus"]),
    ("team",          "system",   "팀 / 조직 정보",
        ["팀", "조직"]),
    ("system",        "system",   "시스템 상태 · 디바이스 정보",
        ["시스템 상태", "디바이스"]),
]


def render_tab_catalog_prompt() -> str:
    """챗봇 시스템 프롬프트에 삽입할 탭 목록 문자열 생성."""
    group_to_label = dict(TAB_GROUPS)
    group_buckets: dict[str, list[tuple[str, str, list[str]]]] = {g: [] for g, _ in TAB_GROUPS}
    for tid, group, desc, kws in TAB_CATALOG:
        group_buckets.setdefault(group, []).append((tid, desc, kws))
    lines = []
    for gid, glabel in TAB_GROUPS:
        items = group_buckets.get(gid) or []
        if not items:
            continue
        lines.append(f"\n### {glabel}")
        for tid, desc, _kws in items:
            lines.append(f"- {tid}: {desc}")
    return "\n".join(lines)


def keyword_routing_hints() -> str:
    """키워드 → 탭 id 매핑을 자연어 지시로 반환."""
    parts = []
    for tid, _group, _desc, kws in TAB_CATALOG:
        if kws:
            parts.append(f"- [{tid}] 관련 키워드: {', '.join(kws)}")
    return "\n".join(parts)
