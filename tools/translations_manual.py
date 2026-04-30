"""수동 번역 사전.

build_locales.py 에서 로드되며, 기존 HTML 인라인 사전보다 우선 적용된다.
여기서 빠진 항목은 기존 I18N.en · zhMap 으로 fallback.

- MANUAL_KO : 구조화 키(nav.*, settings.* 등) 한국어 라벨
- MANUAL_EN : 영어 번역 (추가/오버라이드)
- MANUAL_ZH : 중국어 번역 (추가/오버라이드)
- NEEDS_REVIEW : 번역 전문가 검수 필요 항목 (translation-review.md 로 출력)
"""
from __future__ import annotations

try:
    from translations_manual_zh_missing import MISSING_ZH as _MISSING_ZH
except Exception:
    _MISSING_ZH = {}

try:
    from translations_manual_2 import NEW_EN as _NEW_EN, NEW_ZH as _NEW_ZH
except Exception:
    _NEW_EN, _NEW_ZH = {}, {}

try:
    from translations_manual_3 import NEW_EN as _NEW_EN_3, NEW_ZH as _NEW_ZH_3
except Exception:
    _NEW_EN_3, _NEW_ZH_3 = {}, {}

try:
    from translations_manual_4 import NEW_EN as _NEW_EN_4, NEW_ZH as _NEW_ZH_4
except Exception:
    _NEW_EN_4, _NEW_ZH_4 = {}, {}

try:
    from translations_manual_5 import NEW_EN as _NEW_EN_5, NEW_ZH as _NEW_ZH_5
except Exception:
    _NEW_EN_5, _NEW_ZH_5 = {}, {}

try:
    from translations_manual_6 import NEW_EN as _NEW_EN_6, NEW_ZH as _NEW_ZH_6
except Exception:
    _NEW_EN_6, _NEW_ZH_6 = {}, {}

try:
    from translations_manual_7 import NEW_EN as _NEW_EN_7, NEW_ZH as _NEW_ZH_7
except Exception:
    _NEW_EN_7, _NEW_ZH_7 = {}, {}

try:
    from translations_manual_8 import NEW_EN as _NEW_EN_8, NEW_ZH as _NEW_ZH_8
except Exception:
    _NEW_EN_8, _NEW_ZH_8 = {}, {}

try:
    from translations_manual_9 import NEW_EN as _NEW_EN_9, NEW_ZH as _NEW_ZH_9
except Exception:
    _NEW_EN_9, _NEW_ZH_9 = {}, {}

# v2.34.x — Crew Wizard / palette categories / slack_approval / obsidian_log
try:
    from translations_manual_10 import NEW_EN as _NEW_EN_10, NEW_ZH as _NEW_ZH_10
except Exception:
    _NEW_EN_10, _NEW_ZH_10 = {}, {}

# v2.36.0 — Run Center / Workflow Quick Actions / Commands tab Run buttons
try:
    from translations_manual_11 import NEW_EN as _NEW_EN_11, NEW_ZH as _NEW_ZH_11
except Exception:
    _NEW_EN_11, _NEW_ZH_11 = {}, {}

# v2.37.0 — Auto-Resume: inject a retry loop into a live Claude Code session
try:
    from translations_manual_12 import NEW_EN as _NEW_EN_12, NEW_ZH as _NEW_ZH_12
except Exception:
    _NEW_EN_12, _NEW_ZH_12 = {}, {}

# v2.38.0 — Quick Settings drawer (per-user prefs: UI / AI / Behavior / Workflow)
try:
    from translations_manual_13 import NEW_EN as _NEW_EN_13, NEW_ZH as _NEW_ZH_13
except Exception:
    _NEW_EN_13, _NEW_ZH_13 = {}, {}

# v2.39.0 — Hyper Agent (sub-agents that self-refine over time)
try:
    from translations_manual_14 import NEW_EN as _NEW_EN_14, NEW_ZH as _NEW_ZH_14
except Exception:
    _NEW_EN_14, _NEW_ZH_14 = {}, {}

# v2.40.0 — Hyper Agent project scope + sidebar discovery aids
try:
    from translations_manual_15 import NEW_EN as _NEW_EN_15, NEW_ZH as _NEW_ZH_15
except Exception:
    _NEW_EN_15, _NEW_ZH_15 = {}, {}

# v2.40.2 — Hooks tab emergency UX (search · filter · risk chip · panic)
try:
    from translations_manual_16 import NEW_EN as _NEW_EN_16, NEW_ZH as _NEW_ZH_16
except Exception:
    _NEW_EN_16, _NEW_ZH_16 = {}, {}

# v2.40.4 — Hook Detective + Recent Blocks + Command pretty-decoder
try:
    from translations_manual_17 import NEW_EN as _NEW_EN_17, NEW_ZH as _NEW_ZH_17
except Exception:
    _NEW_EN_17, _NEW_ZH_17 = {}, {}

# v2.41.0 — Agent Teams + Project Detail subagent activity timeline
try:
    from translations_manual_18 import NEW_EN as _NEW_EN_18, NEW_ZH as _NEW_ZH_18
except Exception:
    _NEW_EN_18, _NEW_ZH_18 = {}, {}

# v2.42.0 — Computer Use / Memory / Advisor labs + Claude Code Routines
try:
    from translations_manual_19 import NEW_EN as _NEW_EN_19, NEW_ZH as _NEW_ZH_19
except Exception:
    _NEW_EN_19, _NEW_ZH_19 = {}, {}

# v2.42.1 — Workflow run visibility (list cards + canvas auto-restore)
try:
    from translations_manual_20 import NEW_EN as _NEW_EN_20, NEW_ZH as _NEW_ZH_20
except Exception:
    _NEW_EN_20, _NEW_ZH_20 = {}, {}

# v2.43.0 — Setup Helpers (global ↔ project scope)
try:
    from translations_manual_21 import NEW_EN as _NEW_EN_21, NEW_ZH as _NEW_ZH_21
except Exception:
    _NEW_EN_21, _NEW_ZH_21 = {}, {}

# v2.43.2 — Project / session token usage drill-down
try:
    from translations_manual_22 import NEW_EN as _NEW_EN_22, NEW_ZH as _NEW_ZH_22
except Exception:
    _NEW_EN_22, _NEW_ZH_22 = {}, {}

# v2.44.0 — Process / Port / Memory monitors
try:
    from translations_manual_23 import NEW_EN as _NEW_EN_23, NEW_ZH as _NEW_ZH_23
except Exception:
    _NEW_EN_23, _NEW_ZH_23 = {}, {}

# v2.44.1 — Multi-assignee parallel fan-out (workflow inspector)
try:
    from translations_manual_24 import NEW_EN as _NEW_EN_24, NEW_ZH as _NEW_ZH_24
except Exception:
    _NEW_EN_24, _NEW_ZH_24 = {}, {}

# v2.45.0 — Claude Code Router (CCR / zclaude) setup wizard
try:
    from translations_manual_25 import NEW_EN as _NEW_EN_25, NEW_ZH as _NEW_ZH_25
except Exception:
    _NEW_EN_25, _NEW_ZH_25 = {}, {}

# v2.45.2 — Ollama auto-start toggle + installed-models render fix
try:
    from translations_manual_26 import NEW_EN as _NEW_EN_26, NEW_ZH as _NEW_ZH_26
except Exception:
    _NEW_EN_26, _NEW_ZH_26 = {}, {}

# v2.47.0 — sessions virtual-scroll sentinel
try:
    from translations_manual_27 import NEW_EN as _NEW_EN_27, NEW_ZH as _NEW_ZH_27
except Exception:
    _NEW_EN_27, _NEW_ZH_27 = {}, {}

# v2.49.0 — Auto-Resume Manager tab strings
try:
    from translations_manual_28 import NEW_EN as _NEW_EN_28, NEW_ZH as _NEW_ZH_28
except Exception:
    _NEW_EN_28, _NEW_ZH_28 = {}, {}

# ── 구조화 키 → 한국어 라벨 ──
MANUAL_KO: dict[str, str] = {
    "settings.theme": "테마",
    "settings.dark": "다크",
    "settings.light": "라이트",
    "settings.midnight": "미드나잇",
    "settings.forest": "포레스트",
    "settings.sunset": "선셋",
    "settings.language": "언어",
    "header.search": "검색… ⌘K",
    "header.connected": "연결됨",
    "sidebar.reindex": "세션 재인덱스",
    "sidebar.latest": "최신 불러오기",
    "nav.features": "신기능",
    "nav.overview": "개요",
    "nav.projects": "프로젝트",
    "nav.analytics": "통계 & 스코어",
    "nav.aiEval": "AI 종합 평가",
    "nav.sessions": "세션 히스토리",
    "nav.agents": "에이전트 & 그래프",
    "nav.projectAgents": "프로젝트 서브 에이전트",
    "nav.skills": "스킬",
    "nav.commands": "슬래시 명령어",
    "nav.hooks": "훅",
    "nav.permissions": "권한",
    "nav.mcp": "MCP 커넥터",
    "nav.plugins": "플러그인",
    "nav.settings": "Settings 편집",
    "nav.claudemd": "CLAUDE.md",
    "nav.team": "팀 / 조직",
    "nav.system": "시스템 상태",
    "nav.usage": "사용량 / 비용",
    "nav.memory": "프로젝트 메모리",
    "nav.tasks": "태스크 / TODO",
    "nav.outputStyles": "출력 스타일",
    "nav.statusline": "상태라인 / 키바인딩",
    "nav.plans": "플랜 보관소",
    "nav.envConfig": "환경 변수",
    "nav.modelConfig": "모델 설정",
    "nav.ideStatus": "IDE 통합",
    "nav.marketplaces": "마켓플레이스",
    "nav.scheduled": "예약된 작업",
    "nav.metrics": "토큰 메트릭",
    "nav.backups": "백업",
    "nav.bashHistory": "셸 명령 기록",
    "nav.telemetry": "텔레메트리",
    "nav.homunculus": "Homunculus",
}

# ── 영어 번역 추가 · 오버라이드 ──
MANUAL_EN: dict[str, str] = {
    "(cwd 미확인)": "(cwd unverified)",
    ") 하위": ") sub",
    "+ 추가": "+ Add",
    "AI 종합 평가": "AI Evaluation",
    "CLI 상태 확인": "Check CLI status",
    "CLI가 설치되어 있지 않습니다. 먼저 설치하세요": "CLI is not installed. Please install it first",
    "Claude CLI 미설치": "Claude CLI not installed",
    "Claude CLI 설치됨": "Claude CLI installed",
    "Claude Code 가 읽는 환경변수들. settings.json.env 값과 현재 프로세스 실제 값 비교": "Environment variables Claude Code reads — comparing settings.json.env against the actual running-process values",
    "Claude Code 내부 추적기 ·": "Claude Code internal tracker ·",
    "Claude Code 에서": "In Claude Code",
    "Claude Code 와 연결된 터미널/IDE 상태": "Terminal/IDE status connected to Claude Code",
    "Claude Control Center — 최적화 대시보드": "Claude Control Center — Optimization Dashboard",
    "Claude 가 최근 발표한 신기능을 찾아서 신기능 탭에 추가": "Fetch Claude's latest announcements and add them to the New Features tab",
    "Claude 계정에 로그인되지 않았습니다.": "Not logged into Claude account.",
    "Homunculus 프로젝트 추적": "Homunculus project tracking",
    "MCP 커넥터": "MCP Connectors",
    "Settings 편집": "Edit Settings",
    "Settings 편집으로 이동 →": "Go to Edit Settings →",
    "bash-commands.log 없음": "bash-commands.log not found",
    "const _KO_RE = /[가-힣]/": "const _KO_RE = /[가-힣]/",
    "git URL (예: https://github.com/user/repo.git)": "git URL (e.g. https://github.com/user/repo.git)",
    "memory 자동 기억": "auto-saved memory",
    "settings.json 의 모델 / 인증 / 자동업데이트 옵션": "Model / auth / auto-update options in settings.json",
    "telemetry/ 없음": "telemetry/ not found",
    "~/.claude/scheduled-tasks/ 에 정의된 cron 스킬": "cron skills defined in ~/.claude/scheduled-tasks/",
    "· 예상": "· estimated",
    "⏰ 시간 초과 — 페이지를 새로고침 하세요.": "⏰ Timeout — please refresh the page.",
    "⏳ 로그아웃 중…": "⏳ Logging out…",
    "⏳ 새 로그인 창 여는 중…": "⏳ Opening new login window…",
    "⏳ 터미널에서 로그인 창 여는 중…": "⏳ Opening login window in terminal…",
    "◀ 좌측(현재값) 유지": "◀ Keep left (current)",
    "✅ 터미널에서 브라우저 인증을 완료하세요.": "✅ Complete browser authentication in the terminal.",
    "➕ CLAUDE.md 에 추가": "➕ Append to CLAUDE.md",
    "각 추천은 프로젝트 루트(": "Each recommendation is per project root (",
    "개 · 이벤트": "entries · events",
    "개 마켓플레이스 · git URL 로 추가": "marketplaces · add via git URL",
    "개 세션의 5축 평균 · 각 세션은 max 100": "sessions (5-axis avg, max 100 per session)",
    "개 프로젝트": "projects",
    "개요": "Overview",
    "건 · 파싱 오류": "items · parse errors",
    "건너뛰기": "Skip",
    "검색… ⌘K": "Search… ⌘K",
    "권한": "Permissions",
    "는 Claude Code 가 자동으로 발견한 모든 프로젝트 루트를 기록합니다. 우리가": "records every project root Claude Code auto-discovers. Unlike what we see via",
    "다크": "Dark",
    "또는": "or",
    "또는 Claude Code 재시작으로 동기화.": "or restart Claude Code to sync.",
    "또는 터미널에서 직접 실행": "or run directly in the terminal",
    "라이트": "Light",
    "로 보는 세션 데이터와는 다르게, git remote 추적 + 마지막 작업 시간을 함께 저장.": "as session data, it also tracks the git remote and last-touched time.",
    "로 임시 전환.": "to switch temporarily.",
    "로 저장되는 서브 에이전트를 관리. 역할 프리셋으로 즉시 추가.": "Manage saved sub-agents. Add instantly from role presets.",
    "로 첫 스타일 추가": "to add the first style",
    "로 추가, 카드에서 삭제": "to add; delete from card",
    "로그인이 필요합니다": "Login required",
    "루트 경로": "Root path",
    "만 편집 가능 (안전장치).": "editable only (safeguard).",
    "명령 검색 (예: git, npm, curl)": "Search commands (e.g. git, npm, curl)",
    "번역 중 오류": "Translation error",
    "변수": "Variable",
    "비용 (": "Cost (",
    "사용량 / 비용": "Usage / Cost",
    "사이드바 접기/펼치기": "Collapse/expand sidebar",
    "사이드바 토글": "Toggle sidebar",
    "상태라인 / 키바인딩": "Status Line / Key Bindings",
    "서버 연결 실패": "Server connection failed",
    "설명 (description)": "Description",
    "설정": "Settings",
    "설정된 모델 관련 키 없음 — 기본값 사용 중": "No model-related keys set — using defaults",
    "설치 위치": "Install location",
    "세션 ID": "Session ID",
    "슬래시 명령어": "Slash Commands",
    "실행 프로세스 값": "Running process value",
    "아직 이 프로젝트에 에이전트가 없습니다. 아래 역할 프리셋에서 하나를 선택해 추가하세요.": "No agents in this project yet. Pick a role preset below to add one.",
    "알려진 마켓플레이스 없음": "No known marketplaces",
    "양쪽 값을 자유롭게 편집한 뒤 어느 쪽을 저장할지 고르세요. ·": "Edit either side and pick which to save. ·",
    "언어": "Language",
    "에게": "to",
    "에서 설정하면 모든 세션에 적용. 프로세스 값은 이 대시보드 서버가 실행 중인 쉘의 현재 값.": "Set here to apply to all sessions. The process value is the current value of the shell running this dashboard server.",
    "에이전트 & 그래프": "Agents & Graph",
    "에이전트 본문 (미리보기)": "Agent body (preview)",
    "역할 프리셋": "Role preset",
    "연결 오류": "Connection error",
    "예: MCP 어디서 설정해?": "e.g. Where do I configure MCP?",
    "요청 가능": "Requestable",
    "요청 가능.": "Requestable.",
    "우측(제안) 적용 ▶": "Apply right (suggestion) ▶",
    "으로 기본 모델 변경. 세션 내에서는": "to change the default model. Within a session use",
    "을 누르면 현재 계정이 로그아웃되고 터미널에서 새 로그인 창이 열립니다.": "will log out the current account and open a new login window in the terminal.",
    "의": "of",
    "이름 (예: my-marketplace)": "Name (e.g. my-marketplace)",
    "이미 권장 설정이 갖춰져 있습니다. 🎉": "Recommended settings are already in place. 🎉",
    "자": "characters",
    "재인덱스 실패": "Reindex failed",
    "저장 위치": "Save location",
    "저장됨 (": "Saved (",
    "전체에 적용": "Apply to all",
    "제안 (오른쪽) · AI": "Suggestion (right) · AI",
    "챗봇 열기": "Open chatbot",
    "처럼 추가.": "add like this.",
    "첫 발견": "First seen",
    "추가 후 터미널에서": "After adding, in the terminal",
    "추정)": "estimated)",
    "추천 비교 & 적용": "Compare & apply recommendations",
    "추천 편집": "Edit recommendation",
    "카드 클릭 → 프리셋 내용 미리보기 → 이름/설명 커스터마이즈 후 설치": "Click card → preview preset → customize name/description → install",
    "탭 이동, 기능 검색…": "Switch tabs, search features…",
    "탭에서 JSON 루트에": "in the tab at JSON root",
    "터미널 활성화 (": "Activate terminal (",
    "테마": "Theme",
    "파일 없음 / 빈값": "No file / empty",
    "편집 방법": "How to edit",
    "표시할 프로젝트 없음": "No projects to display",
    "프로젝트 서브 에이전트": "Project Sub-agents",
    "프로젝트 에이전트 편집 —": "Edit project agent —",
    "프로젝트마다": "Per project",
    "한국어": "Korean",
    "해서 상세 · 비활성 플러그인 에이전트는 뱃지 클릭으로 즉시 활성화 · 전역 에이전트는 우측 상단": "to expand · click the badge on a disabled plugin agent to enable it · add global agents via the top-right",
    "혹은 전역": "or global",
    "환경변수.": "environment variables.",
    "활성 세션 없음": "No active sessions",
    "회 호출 ·": "calls ·",
    "훅": "Hooks",
    "＋ 새 마켓플레이스 추가": "＋ Add marketplace",
    "＋ 이 프로젝트에 설치": "＋ Install to this project",
    "🌿 Claude Code 환경 변수 카탈로그": "🌿 Claude Code environment variable catalog",
    "🎉 로그인 성공! 대시보드를 불러옵니다…": "🎉 Login success! Loading dashboard…",
    "🎭 역할 프리셋 카탈로그 ·": "🎭 Role preset catalog ·",
    "🏆 최고 세션": "🏆 Top Sessions",
    "💀 하위 세션": "💀 Bottom Sessions",
    "💡 비활성화": "💡 Disabled",
    "💡 시크릿 형태(토큰/키) 값은 일부 마스킹됩니다.": "💡 Secret-like values (tokens/keys) are partially masked.",
    "💾 이 내용으로 저장": "💾 Save this content",
    "💻 활성 Claude Code 세션 (": "💻 Active Claude Code sessions (",
    "📁 최근 텔레메트리 파일": "📁 Recent telemetry files",
    "📊 상위 이벤트 타입": "📊 Top event types",
    "📋 사용 가능 모델": "📋 Available models",
    "📌 수동 단계": "📌 Manual step",
    "📐 5-축 점수 (계산식 + 실측)": "📐 5-axis score (formula + measured)",
    "📝 파일 편집": "📝 File edit",
    "📦 이 프로젝트의 에이전트 ·": "📦 Agents in this project ·",
    "🔄 로그인 확인 중…": "🔄 Checking login…",
    "🔍 검색": "🔍 Search",
    "🖥 감지된 터미널 / IDE (텔레메트리 기반)": "🖥 Detected terminal / IDE (telemetry-based)",
    "🚀 Claude 로그인": "🚀 Claude login",
    "🛠 파일별 개선 추천 (": "🛠 Per-file improvement recommendations (",
    "🤝 프로젝트 에이전트": "🤝 Project agents",
    "🧬 현재 Settings 키": "🧬 Current Settings keys",
}

# ── 중국어 번역 추가 · 오버라이드 ──
# 기존 zhMap 은 573 개 수준이라 큰 공백이 있다. 여기서 채우고, 채우지 못한 항목은
# 최후 수단으로 EN 번역을 중국어로 옮긴 근사치를 제공한다.
MANUAL_ZH: dict[str, str] = {
    "(cwd 미확인)": "(未验证的工作目录)",
    ") 하위": ") 子",
    "+ 추가": "+ 添加",
    "AI 종합 평가": "AI 综合评估",
    "CLI 상태 확인": "检查 CLI 状态",
    "CLI가 설치되어 있지 않습니다. 먼저 설치하세요": "CLI 未安装，请先安装",
    "Claude CLI 미설치": "Claude CLI 未安装",
    "Claude CLI 설치됨": "Claude CLI 已安装",
    "Claude Code 가 읽는 환경변수들. settings.json.env 값과 현재 프로세스 실제 값 비교": "Claude Code 读取的环境变量 — 对比 settings.json.env 与实际运行进程的值",
    "Claude Code 내부 추적기 ·": "Claude Code 内部追踪器 ·",
    "Claude Code 에서": "在 Claude Code 中",
    "Claude Code 와 연결된 터미널/IDE 상태": "与 Claude Code 连接的终端/IDE 状态",
    "Claude Control Center — 최적화 대시보드": "Claude 控制中心 — 优化仪表板",
    "Claude 가 최근 발표한 신기능을 찾아서 신기능 탭에 추가": "获取 Claude 最新发布的新功能并添加到新功能标签",
    "Claude 계정에 로그인되지 않았습니다.": "未登录 Claude 账户。",
    "Homunculus 프로젝트 추적": "Homunculus 项目追踪",
    "MCP 커넥터": "MCP 连接器",
    "Settings 편집": "编辑设置",
    "Settings 편집으로 이동 →": "前往编辑设置 →",
    "bash-commands.log 없음": "bash-commands.log 不存在",
    "const _KO_RE = /[가-힣]/": "const _KO_RE = /[가-힣]/",
    "git URL (예: https://github.com/user/repo.git)": "git URL（例：https://github.com/user/repo.git）",
    "memory 자동 기억": "自动记忆",
    "settings.json 의 모델 / 인증 / 자동업데이트 옵션": "settings.json 中的模型/认证/自动更新选项",
    "telemetry/ 없음": "telemetry/ 不存在",
    "~/.claude/scheduled-tasks/ 에 정의된 cron 스킬": "~/.claude/scheduled-tasks/ 中定义的 cron 技能",
    "· 예상": "· 预估",
    "⏰ 시간 초과 — 페이지를 새로고침 하세요.": "⏰ 超时 — 请刷新页面。",
    "⏳ 로그아웃 중…": "⏳ 登出中…",
    "⏳ 새 로그인 창 여는 중…": "⏳ 正在打开新登录窗口…",
    "⏳ 터미널에서 로그인 창 여는 중…": "⏳ 正在终端中打开登录窗口…",
    "◀ 좌측(현재값) 유지": "◀ 保留左侧(当前值)",
    "✅ 터미널에서 브라우저 인증을 완료하세요.": "✅ 请在终端中完成浏览器认证。",
    "➕ CLAUDE.md 에 추가": "➕ 追加到 CLAUDE.md",
    "각 추천은 프로젝트 루트(": "每项建议针对项目根目录(",
    "개 · 이벤트": "项 · 事件",
    "개 마켓플레이스 · git URL 로 추가": "个市场 · 通过 git URL 添加",
    "개 세션의 5축 평균 · 각 세션은 max 100": "个会话的 5 轴平均(每会话最高 100)",
    "개 프로젝트": "个项目",
    "개요": "概览",
    "건 · 파싱 오류": "条 · 解析错误",
    "건너뛰기": "跳过",
    "검색… ⌘K": "搜索… ⌘K",
    "권한": "权限",
    "는 Claude Code 가 자동으로 발견한 모든 프로젝트 루트를 기록합니다. 우리가": "记录 Claude Code 自动发现的所有项目根目录。与我们通过",
    "다크": "暗色",
    "또는": "或",
    "또는 Claude Code 재시작으로 동기화.": "或重启 Claude Code 以同步。",
    "또는 터미널에서 직접 실행": "或在终端中直接执行",
    "라이트": "亮色",
    "로 보는 세션 데이터와는 다르게, git remote 추적 + 마지막 작업 시간을 함께 저장.": "查看的会话数据不同，此处还会保存 git remote 追踪和最后操作时间。",
    "로 임시 전환.": "以临时切换。",
    "로 저장되는 서브 에이전트를 관리. 역할 프리셋으로 즉시 추가.": "管理保存的子代理。通过角色预设立即添加。",
    "로 첫 스타일 추가": "添加第一个样式",
    "로 추가, 카드에서 삭제": "添加；从卡片删除",
    "로그인이 필요합니다": "需要登录",
    "루트 경로": "根路径",
    "만 편집 가능 (안전장치).": "仅可编辑(安全锁)。",
    "명령 검색 (예: git, npm, curl)": "搜索命令(例：git, npm, curl)",
    "번역 중 오류": "翻译错误",
    "변수": "变量",
    "비용 (": "费用 (",
    "사용량 / 비용": "用量/费用",
    "사이드바 접기/펼치기": "折叠/展开侧边栏",
    "사이드바 토글": "切换侧边栏",
    "상태라인 / 키바인딩": "状态栏/快捷键",
    "서버 연결 실패": "服务器连接失败",
    "설명 (description)": "描述",
    "설정": "设置",
    "설정된 모델 관련 키 없음 — 기본값 사용 중": "未设置模型相关键 — 使用默认值",
    "설치 위치": "安装位置",
    "세션 ID": "会话 ID",
    "슬래시 명령어": "斜杠命令",
    "실행 프로세스 값": "运行进程的值",
    "아직 이 프로젝트에 에이전트가 없습니다. 아래 역할 프리셋에서 하나를 선택해 추가하세요.": "该项目尚无代理。请从下方角色预设中选择添加。",
    "알려진 마켓플레이스 없음": "无已知市场",
    "양쪽 값을 자유롭게 편집한 뒤 어느 쪽을 저장할지 고르세요. ·": "自由编辑两侧值后选择保存哪一侧。·",
    "언어": "语言",
    "에게": "给",
    "에서 설정하면 모든 세션에 적용. 프로세스 값은 이 대시보드 서버가 실행 중인 쉘의 현재 값.": "在此设置则应用于所有会话。进程值为运行本面板服务器的 shell 当前值。",
    "에이전트 & 그래프": "代理与图谱",
    "에이전트 본문 (미리보기)": "代理正文(预览)",
    "역할 프리셋": "角色预设",
    "연결 오류": "连接错误",
    "예: MCP 어디서 설정해?": "例：MCP 在哪里配置？",
    "요청 가능": "可请求",
    "요청 가능.": "可请求。",
    "우측(제안) 적용 ▶": "应用右侧(建议) ▶",
    "으로 기본 모델 변경. 세션 내에서는": "以更改默认模型。会话内使用",
    "을 누르면 현재 계정이 로그아웃되고 터미널에서 새 로그인 창이 열립니다.": "按下将登出当前账户并在终端打开新登录窗口。",
    "의": "的",
    "이름 (예: my-marketplace)": "名称(例：my-marketplace)",
    "이미 권장 설정이 갖춰져 있습니다. 🎉": "已具备推荐设置。🎉",
    "자": "字符",
    "재인덱스 실패": "重建索引失败",
    "저장 위치": "保存位置",
    "저장됨 (": "已保存 (",
    "전체에 적용": "应用于全部",
    "제안 (오른쪽) · AI": "建议(右侧) · AI",
    "챗봇 열기": "打开聊天机器人",
    "처럼 추가.": "如此添加。",
    "첫 발견": "首次发现",
    "추가 후 터미널에서": "添加后在终端",
    "추정)": "预估)",
    "추천 비교 & 적용": "对比并应用建议",
    "추천 편집": "编辑建议",
    "카드 클릭 → 프리셋 내용 미리보기 → 이름/설명 커스터마이즈 후 설치": "点击卡片 → 预览预设 → 自定义名称/描述 → 安装",
    "탭 이동, 기능 검색…": "切换标签、搜索功能…",
    "탭에서 JSON 루트에": "在标签的 JSON 根下",
    "터미널 활성화 (": "激活终端 (",
    "테마": "主题",
    "파일 없음 / 빈값": "无文件/空值",
    "편집 방법": "编辑方法",
    "표시할 프로젝트 없음": "没有项目可显示",
    "프로젝트 서브 에이전트": "项目子代理",
    "프로젝트 에이전트 편집 —": "编辑项目代理 —",
    "프로젝트마다": "每个项目",
    "한국어": "韩语",
    "해서 상세 · 비활성 플러그인 에이전트는 뱃지 클릭으로 즉시 활성화 · 전역 에이전트는 우측 상단": "展开详情 · 点击已禁用的插件代理徽章可立即启用 · 全局代理通过右上角",
    "혹은 전역": "或全局",
    "환경변수.": "环境变量。",
    "활성 세션 없음": "无活跃会话",
    "회 호출 ·": "次调用 ·",
    "훅": "钩子",
    "＋ 새 마켓플레이스 추가": "＋ 添加市场",
    "＋ 이 프로젝트에 설치": "＋ 安装到此项目",
    "🌿 Claude Code 환경 변수 카탈로그": "🌿 Claude Code 环境变量目录",
    "🎉 로그인 성공! 대시보드를 불러옵니다…": "🎉 登录成功！正在加载仪表板…",
    "🎭 역할 프리셋 카탈로그 ·": "🎭 角色预设目录 ·",
    "🏆 최고 세션": "🏆 顶级会话",
    "💀 하위 세션": "💀 底部会话",
    "💡 비활성화": "💡 已禁用",
    "💡 시크릿 형태(토큰/키) 값은 일부 마스킹됩니다.": "💡 秘密形式(令牌/密钥)的值会部分被掩码。",
    "💾 이 내용으로 저장": "💾 以此内容保存",
    "💻 활성 Claude Code 세션 (": "💻 活跃 Claude Code 会话 (",
    "📁 최근 텔레메트리 파일": "📁 最近遥测文件",
    "📊 상위 이벤트 타입": "📊 顶部事件类型",
    "📋 사용 가능 모델": "📋 可用模型",
    "📌 수동 단계": "📌 手动步骤",
    "📐 5-축 점수 (계산식 + 실측)": "📐 5 轴评分(公式 + 实测)",
    "📝 파일 편집": "📝 文件编辑",
    "📦 이 프로젝트의 에이전트 ·": "📦 此项目的代理 ·",
    "🔄 로그인 확인 중…": "🔄 正在检查登录…",
    "🔍 검색": "🔍 搜索",
    "🖥 감지된 터미널 / IDE (텔레메트리 기반)": "🖥 检测到的终端/IDE(基于遥测)",
    "🚀 Claude 로그인": "🚀 Claude 登录",
    "🛠 파일별 개선 추천 (": "🛠 按文件的改进建议 (",
    "🤝 프로젝트 에이전트": "🤝 项目代理",
    "🧬 현재 Settings 키": "🧬 当前设置键",
}

# 자동 병합: MISSING_ZH 의 항목을 MANUAL_ZH 에 추가 (MANUAL_ZH 우선)
for _k, _v in _MISSING_ZH.items():
    MANUAL_ZH.setdefault(_k, _v)

# PHASE 1 후속: 이번 세션 감사에서 추가 발견된 111 phrase 번역 병합
for _k, _v in _NEW_EN.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH.items():
    MANUAL_ZH.setdefault(_k, _v)

# 버그 수정(/* */ false match) 후 감사에 복구된 280 phrase 번역 병합
for _k, _v in _NEW_EN_3.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_3.items():
    MANUAL_ZH.setdefault(_k, _v)

# 실 브라우저 스캔에서 발견된 UI 잔존 fragment · 서버 emit 라벨 · 짧은 glue token
for _k, _v in _NEW_EN_4.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_4.items():
    MANUAL_ZH.setdefault(_k, _v)

# overview 등 템플릿 composition 잔존 Korean 조각 번역
for _k, _v in _NEW_EN_5.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_5.items():
    MANUAL_ZH.setdefault(_k, _v)

# Deep-scan 에서 새로 발견된 109 서버 emit 라벨·설명·메시지
for _k, _v in _NEW_EN_6.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_6.items():
    MANUAL_ZH.setdefault(_k, _v)

# Features 탭 BUILTIN_NEW_FEATURES (server/features.py 하드코딩 카탈로그)
for _k, _v in _NEW_EN_7.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_7.items():
    MANUAL_ZH.setdefault(_k, _v)

# 신규 탭: 시작하기(onboarding) + 가이드 & 툴(guideHub) — server/guide.py 및 프론트 UI
for _k, _v in _NEW_EN_8.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_8.items():
    MANUAL_ZH.setdefault(_k, _v)

# 워크플로우 에디터(n8n 스타일) 신규 탭 — server/workflows.py 및 프론트 UI
for _k, _v in _NEW_EN_9.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_9.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.34.x — Crew Wizard / palette categories / slack_approval / obsidian_log
for _k, _v in _NEW_EN_10.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_10.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.36.0 — Run Center / Workflow Quick Actions / Commands tab Run buttons
for _k, _v in _NEW_EN_11.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_11.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.37.0 — Auto-Resume retry-loop injection
for _k, _v in _NEW_EN_12.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_12.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.38.0 — Quick Settings drawer (per-user prefs)
for _k, _v in _NEW_EN_13.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_13.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.39.0 — Hyper Agent
for _k, _v in _NEW_EN_14.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_14.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.40.0 — Hyper Agent project scope + sidebar UX
for _k, _v in _NEW_EN_15.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_15.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.40.2 — Hooks tab emergency UX
for _k, _v in _NEW_EN_16.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_16.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.40.4 — Hook Detective + Recent Blocks + Command decoder
for _k, _v in _NEW_EN_17.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_17.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.41.0 — Agent Teams + Project Detail subagent activity
for _k, _v in _NEW_EN_18.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_18.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.42.0 — 4 new labs / features
for _k, _v in _NEW_EN_19.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_19.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.42.1 — Workflow run visibility
for _k, _v in _NEW_EN_20.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_20.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.43.0 — Setup Helpers
for _k, _v in _NEW_EN_21.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_21.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.43.2 — Project / session token usage drill-down
for _k, _v in _NEW_EN_22.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_22.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.44.0 — Process / Port / Memory monitors
for _k, _v in _NEW_EN_23.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_23.items():
    MANUAL_ZH.setdefault(_k, _v)

# v2.44.1 — Multi-assignee parallel fan-out
for _k, _v in _NEW_EN_24.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_24.items():
    MANUAL_ZH.setdefault(_k, _v)

for _k, _v in _NEW_EN_25.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_25.items():
    MANUAL_ZH.setdefault(_k, _v)

for _k, _v in _NEW_EN_26.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_26.items():
    MANUAL_ZH.setdefault(_k, _v)

for _k, _v in _NEW_EN_27.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_27.items():
    MANUAL_ZH.setdefault(_k, _v)

for _k, _v in _NEW_EN_28.items():
    MANUAL_EN.setdefault(_k, _v)
for _k, _v in _NEW_ZH_28.items():
    MANUAL_ZH.setdefault(_k, _v)

# extractor 오탐(코드/주석)이 초기 MANUAL_EN/ZH 에 한글 원문으로 등록돼 있는 경우 덮어쓰기
_EXTRACTOR_NOISE_OVERRIDES = {
    # origin 이 사용하던 클린 표기(유니코드 이스케이프)로 맞춤 — en.json 에 한글 잔존 0 유지
    "const _KO_RE = /[가-힣]/": ("const _KO_RE = /[\\uAC00-\\uD7A3]/", "const _KO_RE = /[\\uAC00-\\uD7A3]/"),
}
for _k, (_en, _zh) in _EXTRACTOR_NOISE_OVERRIDES.items():
    MANUAL_EN[_k] = _en
    MANUAL_ZH[_k] = _zh

# ── 번역 검수 권장 항목 ──
# 2026-04-21: 이전 9 항목 모두 확정 — 긴 안내 문구만 자연스러운 현지어로 재작성.
# 향후 브랜드/금융 전문용어 등 외부 결정이 필요한 항목이 생기면 여기 등록.
NEEDS_REVIEW: set[str] = set()
