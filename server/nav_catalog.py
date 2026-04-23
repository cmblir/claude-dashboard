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
        "AI 프로바이더 — Claude/GPT/Gemini/Ollama/Codex 멀티 AI 오케스트라. "
        "8개 빌트인 프로바이더 + 커스텀 무제한. API 키 설정, CLI 자동 감지, "
        "폴백 체인 편집, 연결 테스트, 프로바이더 헬스 대시보드. "
        "Ollama: 모델 허브(23종 카탈로그/다운로드/삭제), serve 자동 시작, "
        "기본 채팅/임베딩 모델 설정. 비용 분석 차트, 사용량 알림, 멀티 AI 비교, "
        "프로바이더 설정 위자드(초보자 3단계 가이드)",
        ["프로바이더", "provider", "AI 프로바이더", "멀티 AI", "GPT", "Gemini",
         "Ollama", "Codex", "OpenAI", "API 키", "폴백", "임베딩", "embedding",
         "bge-m3", "비용", "cost", "비교", "compare",
         "모델 다운로드", "모델 관리", "ollama pull", "모델 허브"]),
    ("agents",        "work",     "에이전트 목록 · 상호작용 그래프 (vis-network)",
        ["에이전트", "agent", "상호작용 그래프"]),
    ("projectAgents", "work",     "프로젝트별 서브 에이전트 관리 · 16 역할 프리셋",
        ["서브에이전트", "subagent", "프로젝트 에이전트"]),
    ("skills",        "work",     "사용자 정의 스킬 보기/편집",
        ["스킬", "skill"]),
    ("commands",      "work",     "슬래시 명령어 목록",
        ["슬래시", "슬래시 명령어", "slash"]),
    ("promptCache",   "work",
        "프롬프트 캐시 실험실 — Anthropic Messages API 의 cache_control 을 "
        "시스템/도구/메시지 블록에 적용해 cache_creation / cache_read 토큰과 "
        "비용 절감을 실측. 예시 3종(시스템/문서/도구) 원클릭 실행, 히스토리 20건.",
        ["프롬프트 캐시", "prompt cache", "cache_control", "ephemeral",
         "캐시 절감", "cache_read", "cache_creation"]),
    ("thinkingLab",   "work",
        "Extended Thinking 실험실 — Opus/Sonnet 의 thinking block 을 분리 시각화. "
        "budget_tokens 슬라이더, 예시 3종(수학/디버깅/플래닝), 히스토리 20건.",
        ["extended thinking", "thinking", "reasoning", "추론", "budget_tokens",
         "thinking block"]),
    ("toolUseLab",    "work",
        "Tool Use 플레이그라운드 — tool schema 정의 → Messages API 호출 → "
        "tool_use 블록 수신 시 tool_result 를 수동 입력해 멀티 턴 체인 실행. "
        "기본 도구 3종 (get_weather / calculator / web_search mock).",
        ["tool use", "function calling", "tool_result", "tool_use", "도구 호출",
         "function call"]),
    ("batchJobs",     "work",
        "Batch API 관리 — 대용량 프롬프트 배치 제출·상태 폴링·결과 JSONL 다운로드. "
        "예시 2종 (Q&A 10건 / 요약 5건), 최대 1000건/batch.",
        ["batch", "메시지 배치", "message batches", "대량 요청", "jsonl",
         "일괄 처리"]),
    ("apiFiles",      "work",
        "Files API — Anthropic 파일 업로드 · 목록 · 삭제 + 업로드한 파일을 "
        "메시지에 document 로 reference 해서 질문 테스트.",
        ["files api", "파일 업로드", "document reference", "files",
         "file_id"]),
    ("visionLab",     "work",
        "Vision / PDF 실험실 — 이미지(PNG/JPG/WebP/GIF) 또는 PDF 를 업로드해 "
        "Opus / Sonnet / Haiku 3 모델에 병렬 질문 → 응답 나란히 비교.",
        ["vision", "이미지 인식", "PDF", "멀티모달", "multimodal",
         "image_url", "비교"]),
    ("modelBench",    "work",
        "Model Benchmark — 사전 정의 프롬프트 셋(기본 Q&A / 코드 / 추론) × "
        "선택한 모델들을 교차 실행 → 모델별 평균 지연·토큰·비용 집계 + "
        "개별 응답 매트릭스. 결과 JSON 다운로드.",
        ["benchmark", "벤치마크", "모델 비교", "model compare",
         "지연 비교", "cost compare"]),
    ("serverTools",   "work",
        "Claude 공식 hosted tool 플레이그라운드 — 🌐 web_search + "
        "🧪 code_execution. Anthropic 서버가 직접 실행하는 도구를 체크박스로 "
        "활성화하고 응답 블록(server_tool_use / *_tool_result / text)을 분류 시각화.",
        ["web_search", "웹 검색", "code_execution", "코드 실행",
         "hosted tool", "server tool", "공식 도구"]),
    ("citationsLab",  "work",
        "Citations 플레이그라운드 — 문서를 제공하고 citations.enabled 로 "
        "정확한 인용 span 이 포함된 답변을 받아 원문 하이라이트로 시각화. "
        "예시 2종 (회사 소개문 / 기술 아티클).",
        ["citations", "인용", "citation", "document reference",
         "cited_text", "span highlight"]),
    ("agentSdkScaffold", "work",
        "Agent SDK 스캐폴드 — claude-agent-sdk Python(uv) / TypeScript(bun) "
        "프로젝트 뼈대를 UI 로 생성. 템플릿 3종(basic/tool-use/memory) + "
        "Terminal 새 창에서 초기화 명령 자동 붙여넣기.",
        ["scaffold", "sdk", "agent sdk", "프로젝트 생성", "claude-agent-sdk",
         "uv", "bun"]),
    ("embeddingLab",  "work",
        "Embedding 비교 실험실 — 같은 쿼리/문서 집합을 Voyage / OpenAI / "
        "Ollama 세 프로바이더에 돌려 cosine similarity + rank 매트릭스 비교. "
        "프로바이더별 rank 차이를 하이라이트.",
        ["embedding", "임베딩", "voyage", "bge-m3", "text-embedding-3",
         "cosine", "vector search", "rank 비교"]),
    ("promptLibrary", "work",
        "Prompt Library — 자주 쓰는 프롬프트를 태그와 함께 저장/검색/복제/"
        "워크플로우로 변환. 시드 3종 포함.",
        ["prompt library", "프롬프트 템플릿", "프롬프트 저장", "library",
         "template", "스니펫"]),
    ("rtk",           "work",
        "RTK Optimizer — Claude 토큰 60-90% 절감하는 Rust CLI 프록시 "
        "(rtk-ai/rtk) 를 한 탭에서 설치·활성화·통계 조회.",
        ["rtk", "token", "토큰 최적화", "rust token killer", "claude token",
         "token optimization", "비용 절감", "cost reduction", "rtk-ai"]),
    ("sessionReplay", "work",
        "Session Replay — Claude Code JSONL 세션 로그를 타임라인으로 재생 · "
        "툴 호출 하이라이트 · 누적 토큰 차트.",
        ["session replay", "jsonl", "세션 리플레이", "timeline", "타임라인",
         "replay", "session log", "세션 로그"]),
    ("claudeDocs",    "new",
        "Claude Docs Hub — docs.anthropic.com 주요 페이지(Claude Code / API / "
        "Agent SDK / Models / Account) 를 카테고리별 카드로 색인 + 검색. "
        "각 카드는 관련 대시보드 탭으로도 연결.",
        ["docs", "공식 문서", "documentation", "claude docs", "reference"]),

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
    ("costsTimeline", "system",
        "비용 타임라인 통합 — 모든 플레이그라운드/워크플로우 비용을 "
        "소스별/모델별/일별 집계 + 최근 30건. Claude Code 내부 + 대시보드 "
        "플레이그라운드 10종 + 워크플로우 비용을 한 화면에.",
        ["비용", "cost", "타임라인", "timeline", "spend",
         "daily cost", "예산"]),
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


# 탭 설명 다국어 매핑 (챗봇 + 프론트 다국어 전환용)
TAB_DESC_I18N: dict[str, dict[str, str]] = {
    "features": {"en": "New Features — Latest Anthropic announcements", "zh": "新功能 — Anthropic 最新发布"},
    "onboarding": {"en": "Getting Started — Step-by-step checklist", "zh": "快速入门 — 分步清单"},
    "guideHub": {"en": "Guides & Tools — Best practices & cheat sheets", "zh": "指南与工具 — 最佳实践/速查表"},
    "overview": {"en": "Overview / Optimization Score", "zh": "概览 / 优化评分"},
    "projects": {"en": "Per-project Claude settings & CLAUDE.md", "zh": "项目 Claude 设置 / CLAUDE.md"},
    "analytics": {"en": "Stats & Score / 30-day timeline", "zh": "统计与评分 / 30天时间线"},
    "aiEval": {"en": "AI Evaluation — Full setup diagnosis", "zh": "AI 综合评估"},
    "sessions": {"en": "Session History / Search / Quality Score", "zh": "会话历史 / 搜索 / 质量评分"},
    "workflows": {"en": "Workflow — n8n-style DAG editor with 16 node types", "zh": "工作流 — n8n 风格 DAG 编辑器，16 种节点"},
    "aiProviders": {"en": "AI Providers — Multi-AI orchestration with Ollama hub", "zh": "AI 供应商 — 多 AI 编排 + Ollama 模型中心"},
    "agents": {"en": "Agent list & interaction graph", "zh": "代理列表 / 交互图谱"},
    "projectAgents": {"en": "Per-project sub-agents / 16 role presets", "zh": "项目子代理 / 16 角色预设"},
    "skills": {"en": "User-defined skills", "zh": "用户自定义技能"},
    "commands": {"en": "Slash commands", "zh": "斜杠命令"},
    "promptCache": {"en": "Prompt Cache Lab — cache_control + cache_read/creation tokens + cost savings",
                   "zh": "提示缓存实验室 — cache_control + cache_read/creation 令牌 + 成本节约"},
    "thinkingLab": {"en": "Extended Thinking Lab — visualize Opus/Sonnet thinking blocks with budget slider",
                   "zh": "扩展思维实验室 — 可视化 Opus/Sonnet 思维块,带 budget 滑块"},
    "toolUseLab": {"en": "Tool Use Playground — define tools, trigger tool_use, feed tool_result across multi-turn chains",
                  "zh": "工具使用实验室 — 定义工具,触发 tool_use,多轮传递 tool_result"},
    "batchJobs": {"en": "Batch Jobs — submit large Message Batches, poll status, download JSONL results",
                 "zh": "批量任务 — 提交大批量 Message Batches,轮询状态,下载 JSONL 结果"},
    "apiFiles": {"en": "Files API — upload/list/delete files, reference them in messages as documents",
                "zh": "Files API — 上传/列出/删除文件,并在消息中以 document 形式引用"},
    "visionLab": {"en": "Vision/PDF Lab — drop an image or PDF, compare Opus/Sonnet/Haiku responses side-by-side",
                 "zh": "视觉/PDF 实验室 — 拖入图片或 PDF,并排比较 Opus/Sonnet/Haiku 响应"},
    "modelBench": {"en": "Model Benchmark — cross run prompt sets × models, aggregate latency/tokens/cost",
                  "zh": "模型基准测试 — 提示集 × 模型交叉运行,汇总延迟/令牌/费用"},
    "serverTools": {"en": "Server-side Tools — web_search + code_execution hosted by Anthropic",
                   "zh": "服务端工具 — Anthropic 托管的 web_search + code_execution"},
    "citationsLab": {"en": "Citations Lab — document + citations.enabled → span-highlighted answers",
                    "zh": "引用实验室 — 文档 + citations.enabled → 片段高亮的答案"},
    "agentSdkScaffold": {"en": "Agent SDK Scaffold — generate claude-agent-sdk Python/TS project skeletons",
                        "zh": "Agent SDK 脚手架 — 生成 claude-agent-sdk Python/TS 项目骨架"},
    "embeddingLab": {"en": "Embedding Lab — compare Voyage / OpenAI / Ollama embeddings via cosine-sim rank matrix",
                    "zh": "嵌入实验室 — 通过余弦相似度 rank 矩阵比较 Voyage / OpenAI / Ollama 嵌入"},
    "rtk": {"en": "RTK Optimizer — install & activate the rtk-ai/rtk proxy to cut Claude tokens by 60-90%",
            "zh": "RTK 优化器 — 在本标签页内安装/激活 rtk-ai/rtk 代理，将 Claude token 消耗减少 60-90%"},
    "sessionReplay": {"en": "Session Replay — replay Claude Code JSONL session logs as a timeline with tool-use highlights and cumulative token chart",
                      "zh": "会话重放 — 将 Claude Code JSONL 会话日志作为时间线重放，高亮工具调用并显示累计 token 图表"},
    "promptLibrary": {"en": "Prompt Library — save/search/duplicate prompts, convert to workflow",
                     "zh": "提示库 — 保存/搜索/复制提示,转换为工作流"},
    "claudeDocs": {"en": "Claude Docs Hub — curated docs.anthropic.com index with cross-links to dashboard tabs",
                  "zh": "Claude 文档中心 — docs.anthropic.com 分类索引,关联仪表板标签页"},
    "hooks": {"en": "Event hooks", "zh": "事件钩子"},
    "permissions": {"en": "Tool permissions", "zh": "工具权限"},
    "mcp": {"en": "MCP Connectors", "zh": "MCP 连接器"},
    "plugins": {"en": "Plugin management", "zh": "插件管理"},
    "settings": {"en": "settings.json editor", "zh": "settings.json 编辑"},
    "claudemd": {"en": "CLAUDE.md editor", "zh": "CLAUDE.md 编辑"},
    "outputStyles": {"en": "Output style customization", "zh": "输出样式自定义"},
    "statusline": {"en": "Status line / Key bindings", "zh": "状态栏 / 快捷键"},
    "plans": {"en": "Plan archive", "zh": "计划存档"},
    "envConfig": {"en": "Environment variables", "zh": "环境变量"},
    "modelConfig": {"en": "Model configuration", "zh": "模型设置"},
    "ideStatus": {"en": "IDE integration status", "zh": "IDE 集成状态"},
    "marketplaces": {"en": "Marketplace management", "zh": "市场管理"},
    "scheduled": {"en": "Scheduled tasks", "zh": "定时任务"},
    "usage": {"en": "Usage / Cost estimation", "zh": "使用量 / 费用估算"},
    "costsTimeline": {"en": "Costs Timeline — unified cost dashboard (per-source / per-model / daily)",
                     "zh": "费用时间线 — 统一费用仪表盘（按来源/模型/日）"},
    "metrics": {"en": "Token metrics time series", "zh": "Token 指标时序"},
    "memory": {"en": "Project memory management", "zh": "项目记忆管理"},
    "tasks": {"en": "Task / TODO management", "zh": "任务 / TODO 管理"},
    "backups": {"en": "Backup / File history", "zh": "备份 / 文件历史"},
    "bashHistory": {"en": "Shell command history", "zh": "Shell 命令记录"},
    "telemetry": {"en": "Telemetry logs", "zh": "遥测日志"},
    "homunculus": {"en": "Homunculus project tracker", "zh": "Homunculus 项目追踪"},
    "team": {"en": "Team / Organization info", "zh": "团队 / 组织信息"},
    "system": {"en": "System status / Device info", "zh": "系统状态 / 设备信息"},
}


def get_tab_desc(tab_id: str, lang: str = "ko") -> str:
    """탭 설명을 요청 언어로 반환. 없으면 한글 기본."""
    if lang == "ko":
        return next((desc for tid, _g, desc, _k in TAB_CATALOG if tid == tab_id), "")
    return TAB_DESC_I18N.get(tab_id, {}).get(lang, "")


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
