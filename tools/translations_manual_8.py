"""신규 탭 번역: 시작하기(onboarding) + 가이드 & 툴(guideHub).

프론트 신규 UI 문구 + 백엔드 server/guide.py 에서 emit 되는 한국어
라벨/설명/힌트 전체를 EN/ZH 로 번역.
"""

NEW_EN = {
    # ── NAV ──
    "시작하기": "Getting started",
    "가이드 & 툴": "Guide & Tools",
    "처음 사용자를 위한 단계별 체크리스트 (현재 셋업 자동 감지)":
        "Step-by-step checklist for new users (auto-detects your current setup)",
    "외부 가이드 · 유용한 툴 · 베스트 프랙티스 · 치트시트":
        "External guides · Useful tools · Best practices · Cheatsheet",

    # ── Onboarding UI ──
    "🚀 시작하기": "🚀 Getting started",
    "처음 사용자를 위한 단계별 체크리스트 — 현재 ~/.claude 상태를 실시간으로 감지합니다.":
        "Step-by-step checklist for new users — continuously detects your ~/.claude state.",
    "셋업 진행률": "Setup progress",
    "완료 🎉 — 이제 AI 종합 평가 탭에서 품질 점수를 받아보세요.":
        "Done 🎉 — head over to the AI Evaluation tab to get your quality score.",
    "남은 단계를 하나씩 체크하면 Claude Code 를 더 안전하고 생산적으로 쓸 수 있습니다.":
        "Ticking off each remaining step will make Claude Code safer and more productive.",
    "모든 항목 체크 후엔 'AI 종합 평가' 탭에서 0~100 점수를 받아보세요.":
        "Once every item is checked, visit the 'AI Evaluation' tab for a 0–100 score.",
    "가이드 허브 → 유용한 툴 탭에서 한 번에 설치 가능한 팩을 찾을 수 있습니다.":
        "Guide Hub → Useful tools tab hosts one-shot installable packs.",
    "완료": "Done",
    "필요": "Required",
    "해당 탭으로": "Jump to tab",
    "공식 문서": "Docs",

    # ── Guide Hub UI labels ──
    "📚 가이드 & 툴": "📚 Guide & Tools",
    "세 리소스(everything-claude-code · claude-code-best-practice · 위키독스 한국어 가이드) 를 한 곳에서.":
        "Three resources (everything-claude-code · claude-code-best-practice · Korean WikiDocs guide) in one place.",
    "🧰 유용한 툴": "🧰 Useful tools",
    "🔗 외부 가이드": "🔗 External guides",
    "💡 베스트 프랙티스": "💡 Best practices",
    "⌨️ 치트시트": "⌨️ Cheatsheet",
    "제작": "Author",
    "리포 열기": "Open repo",
    "하이라이트": "Highlights",
    "설치 & 사용": "Install & Use",
    "복사": "Copy",
    "복사됨": "Copied",
    "클립보드에 복사됨": "Copied to clipboard",
    "복사 실패": "Copy failed",
    "데이터 없음": "No data",
    "바로가기": "Open",
    "🎓 추천 학습 경로": "🎓 Recommended learning path",
    "추천 학습 경로": "Recommended learning path",
    "위키독스 한국어 가이드 기초 7강 → 개발 17강 순으로 학습":
        "Work through WikiDocs Korean guide — Basics (7) then Development (17)",
    "best-practice 레포에서 창시자(Boris Cherny) 워크플로 영상 시청":
        "Watch creator (Boris Cherny) workflow videos in the best-practice repo",
    "everything-claude-code 플러그인 설치 → 실전 기능 확보":
        "Install the everything-claude-code plugin for production-grade features",
    "시작하기 탭으로 돌아와 체크리스트 완료":
        "Return to the Getting started tab and finish the checklist",
    "/ 내장 슬래시 명령어": "/ Built-in slash commands",
    "내장 슬래시 명령어": "Built-in slash commands",
    "⌨️ 키보드 단축키": "⌨️ Keyboard shortcuts",
    "키보드 단축키": "Keyboard shortcuts",
    "개": "items",

    # ── server/guide.py — Toolkit subtitles / meta ──
    "멀티 플랫폼 클로드 코드 최적화 팩 (48 agents · 183 skills · 79 commands)":
        "Multi-platform Claude Code optimization pack (48 agents · 183 skills · 79 commands)",
    "47k ⭐ · 82 가지 팁 모음 + 창시자(Boris Cherny) 워크플로":
        "47k ⭐ · 82 tips + creator (Boris Cherny) workflows",
    "클래스 101 + 레퍼런스 21개 · 한국어 전체 가이드북":
        "Classes 101 + 21 reference chapters · complete Korean guidebook",
    "웹/eBook": "Web / eBook",
    "237 추천": "237 recommendations",
    "위키독스": "WikiDocs",

    # ── Toolkit highlights ──
    "Claude Code / Cursor / Codex / OpenCode 크로스 플랫폼":
        "Cross-platform: Claude Code / Cursor / Codex / OpenCode",
    "AgentShield 보안 감사 (1282 tests, 102 정적 룰)":
        "AgentShield security audit (1,282 tests, 102 static rules)",
    "Continuous Learning v2 — 세션에서 인스팅크트 자동 추출":
        "Continuous Learning v2 — auto-extract instincts from sessions",
    "토큰 최적화 (Sonnet 전환, thinking 10k cap, compact 50%)":
        "Token optimization (Sonnet switch, 10k thinking cap, compact at 50%)",
    "Agents · Commands · Skills 3축 정리":
        "Organized across 3 axes: Agents · Commands · Skills",
    "핫 기능: Routines · Ultrareview · Agent Teams · Auto Mode · Computer Use":
        "Hot features: Routines · Ultrareview · Agent Teams · Auto Mode · Computer Use",
    "Research → Plan → Execute → Review → Ship 표준 흐름":
        "Standard flow: Research → Plan → Execute → Review → Ship",
    "prototype > PRD · PR 은 작게(median 118 lines)":
        "prototype > PRD · keep PRs small (median 118 lines)",
    "설치부터 실전까지 단계별 실습 (기초 7 · 개발 17 · 비즈니스 15)":
        "Hands-on step-by-step from install to production (Basics 7 · Dev 17 · Business 15)",
    "크리에이터 · 연구 · 금융 · 법무/HR · 의료 특화 트랙":
        "Specialized tracks: Creator · Research · Finance · Legal/HR · Healthcare",
    "공식 문서 변경 사항 실시간 반영 (최종 2026-04-20)":
        "Mirrors official docs in real time (last updated 2026-04-20)",
    "창시자 워크플로, 스피너 동사 187개, 소스 분석서 별첨":
        "Creator workflow, 187 spinner verbs, source analysis appendix",

    # ── Toolkit install labels ──
    "플러그인 마켓플레이스 추가 (권장)": "Add plugin marketplace (recommended)",
    "전체 프로파일 설치": "Install full profile",
    "수동 설치 (macOS/Linux)": "Manual install (macOS/Linux)",
    "레포 클론 (참고용 문서)": "Clone repo (reference docs)",
    "웹에서 바로 읽기": "Read on the web",

    # ── Toolkit categories ──
    "창시자의 핵심 팁": "Creator's core tips",
    "워크플로 패턴": "Workflow patterns",
    "클래스 101 — 기초": "Classes 101 — Basics",
    "클래스 101 — 개발": "Classes 101 — Development",
    "클래스 101 — 비즈니스": "Classes 101 — Business",
    "레퍼런스 21권": "21 reference chapters",

    # Creator tips (bp card items)
    "항상 Plan Mode 로 시작하라 (Boris Cherny)":
        "Always start in Plan Mode (Boris Cherny)",
    "컨텍스트 40% 이상은 품질 저하 — 30% 이하 유지":
        "Context above 40% degrades quality — keep it under 30%",
    "실패한 시도는 /rewind 로 되돌리기":
        "Undo failed attempts with /rewind",
    "/compact 는 자동보다 힌트를 직접 주고 호출":
        "Call /compact manually with hints instead of relying on auto-compact",
    "새 태스크 = 새 세션, 관련 태스크만 컨텍스트 재사용":
        "New task = new session; only reuse context for related tasks",
    "Superpowers · gstack · BMAD-METHOD · Spec Kit 참조 구현":
        "Reference implementations: Superpowers · gstack · BMAD-METHOD · Spec Kit",
    "Cross-Model: Claude Code + Codex 조합":
        "Cross-model: Claude Code + Codex combo",
    "Agent Teams — 공유 코드베이스에 병렬 에이전트":
        "Agent Teams — parallel agents on a shared codebase",

    # Wikidocs category items
    "설치 · 대화와 세션 · 모델과 Effort":
        "Install · Conversations & sessions · Models & Effort",
    "자율권과 안전 · 컨텍스트 관리":
        "Autonomy & safety · Context management",
    "CLAUDE.md 작업 기억 · 첫 실전 프로젝트":
        "CLAUDE.md working memory · First production project",
    "코드베이스 탐색 · TDD · 리팩토링 · Hooks":
        "Codebase exploration · TDD · Refactoring · Hooks",
    "Git PR 코드리뷰 · GitHub Actions · Worktree 병렬":
        "Git PR reviews · GitHub Actions · Parallel worktrees",
    "Skills 활용/개발 · MCP · 서브에이전트 팀 · 팀 온보딩":
        "Skills use/build · MCP · Sub-agent teams · Team onboarding",
    "이메일 자동관리 · 회의록 · Excel · 보고서":
        "Email automation · Meeting notes · Excel · Reports",
    "일일 브리핑 · PPT 자동 · Chrome 자동화":
        "Daily briefings · Auto PPT · Chrome automation",
    "SOP · 경쟁사 병렬분석 · Vibe Coding 앱":
        "SOPs · Parallel competitor analysis · Vibe Coding apps",
    "퀵 레퍼런스 · 설정 · 권한 · 슬래시 · 단축키":
        "Quick reference · Settings · Permissions · Slash · Shortcuts",
    "MCP · 훅 · 서브에이전트 · 스킬 · IDE · CI/CD":
        "MCP · Hooks · Sub-agents · Skills · IDE · CI/CD",
    "고급 기능 · 베스트 프랙티스 · 플러그인 · 보안/프라이버시":
        "Advanced features · Best practices · Plugins · Security/Privacy",

    # ── Best practices (workflows) ──
    "Research → Plan → Execute → Review → Ship":
        "Research → Plan → Execute → Review → Ship",
    "모든 주요 작업은 이 5단계로. 각 단계마다 슬래시 명령어를 붙이면 품질이 올라간다.":
        "Every major task follows these 5 stages. Slash commands at each stage raise quality.",
    "/ask, /docs, 레포 탐색으로 맥락 먼저. 코드 쓰기 전 WHY 정리.":
        "Start with /ask, /docs, repo exploration. Nail down WHY before writing code.",
    "/plan 또는 Plan Mode. 파일별 변경안 · 리스크 · 롤백 플랜까지.":
        "/plan or Plan Mode. Per-file changes · risks · rollback plan included.",
    "/tdd 로 테스트 먼저. 한 묶음씩 작게 구현 · 작은 PR 유지.":
        "Use /tdd to write tests first. Ship in small batches, keep PRs small.",
    "/code-review + /security-scan. 자동 리뷰 통과 후 사람 리뷰.":
        "/code-review + /security-scan. Human review only after automated checks pass.",
    "/e2e 로 골든 패스 검증. 배포 후 /canary-watch 로 회귀 감시.":
        "Verify the golden path with /e2e. After deploy, monitor with /canary-watch.",

    "토큰 · 컨텍스트 최적화": "Token & context optimization",
    "Claude Code 에서 비용·지연·품질 모두 개선하는 핵심 스위치 5개.":
        "Five core switches in Claude Code that improve cost, latency, and quality.",
    "모델 라우팅": "Model routing",
    "일상은 Sonnet 4.6, 무거운 분석만 Opus 4.7 — 평균 60% 비용 절감.":
        "Daily work on Sonnet 4.6, heavy analysis on Opus 4.7 — about 60% cost savings.",
    "Thinking 캡": "Thinking cap",
    "extended thinking 10,000 토큰 이하로 제한. 무제한은 가성비 나쁨.":
        "Cap extended thinking at ≤10,000 tokens. Unlimited yields poor ROI.",
    "Compact 시점": "Compact timing",
    "자동 95% 대신 50% 에서 직접 /compact. 품질 유지 + 캐시 친화.":
        "Call /compact manually at 50% instead of the auto 95%. Preserves quality and cache.",
    "MCP 10개 이하": "Keep MCPs ≤ 10",
    "활성 MCP 서버는 10개 이하 — 매 턴마다 도구 디스크립션 비용.":
        "Keep active MCP servers ≤10 — tool descriptions cost tokens every turn.",
    "Session 분리": "Separate sessions",
    "새 태스크는 새 세션. 관련 태스크만 /continue 유지.":
        "New task → new session. Only use /continue for related tasks.",

    "Plan Mode · 컨텍스트 습관": "Plan Mode & context habits",
    "Boris Cherny(Claude Code 창시자)가 반복 강조하는 운용 팁.":
        "Operational tips Boris Cherny (Claude Code creator) repeats.",
    "Plan 먼저": "Plan first",
    "모든 비자명한 작업은 Plan Mode 로. 코드 생성 전 사용자 승인을 받는다.":
        "Every non-trivial task starts in Plan Mode. Get user approval before code.",
    "컨텍스트 감시": "Watch context",
    "40% 넘어가면 품질 저하. /clear · /compact · /rewind 세 가지 스위치.":
        "Past 40% quality drops. Three switches: /clear · /compact · /rewind.",
    "Prototype > PRD": "Prototype > PRD",
    "길게 쓴 스펙보다 20~30개의 작은 프로토타입이 빠른 수렴을 준다.":
        "20–30 small prototypes converge faster than a lengthy spec.",
    "작은 PR": "Small PRs",
    "PR 사이즈 median 118 lines. 커지면 쪼개라 — 리뷰 품질 & 롤백 용이.":
        "Median PR is ~118 lines. Split bigger ones — better review and easier rollback.",
    "Squash Merge": "Squash merge",
    "히스토리 선형 유지. rebase 보다 squash 가 충돌 복구에 유리.":
        "Keep history linear. Squash beats rebase for conflict recovery.",

    "보안 · 안전 기본값": "Security & safety defaults",
    "로컬/개인 사용에서도 꼭 켜두면 좋은 안전 스위치.":
        "Safety switches worth enabling even for local/personal use.",
    "Secret 훅": "Secret hook",
    "PreCommit 훅에서 sk-, ghp_, AKIA 패턴 검사 — 실수 커밋 방지.":
        "PreCommit hook scans for sk-, ghp_, AKIA patterns — prevent accidental commits.",
    "Deny 권한": "Deny permissions",
    "permissions.deny 에 rm -rf /, curl | sh, ssh 등 위험 명령 차단.":
        "Block dangerous commands via permissions.deny (rm -rf /, curl | sh, ssh).",
    "Auto Mode": "Auto Mode",
    "개별 승인 프롬프트 대신 분류기 기반 Auto Mode 로 일관성 확보.":
        "Use classifier-based Auto Mode instead of per-call approvals for consistency.",
    "MCP 범위": "MCP scope",
    "로컬 전용 MCP 는 OK, 인터넷 쓰는 MCP 는 allow-list / readOnly 권장.":
        "Local-only MCPs are fine; put internet-using MCPs on allow-list / readOnly.",

    # ── Cheatsheet command descs ──
    "Claude Code 사용법과 명령어 전체 목록":
        "How to use Claude Code and the full command list",
    "현재 세션 컨텍스트 초기화 — 새 주제 시작 시":
        "Reset the current session — start a fresh topic",
    "대화를 요약해 컨텍스트 압축 (힌트 프롬프트 동반 권장)":
        "Compact the conversation into a summary (pass a hint prompt)",
    "마지막 턴(또는 범위)을 되돌리고 실패 시도 제거":
        "Rewind the last turn (or range) and drop failed attempts",
    "같은 태스크를 새 세션에서 이어서":
        "Continue the same task in a fresh session",
    "Plan Mode 진입 — 코드 변경 전 승인 단계":
        "Enter Plan Mode — approval stage before code changes",
    "Opus 4.6 Fast 모드 토글 (빠른 출력, 같은 모델)":
        "Toggle Opus 4.6 Fast mode (faster output, same model)",
    "버그 재현 스펙 → 실패 테스트 → 수정 자동 흐름":
        "Auto flow: bug repro → failing test → fix",
    "현재 레포용 CLAUDE.md 를 자동 초기화":
        "Initialize CLAUDE.md for the current repo",
    "PR 코드리뷰 — 체크리스트 기반":
        "Checklist-driven PR code review",
    "현재 브랜치 변경분 보안 리뷰":
        "Security review of the current branch diff",
    "테마·모델 등 단순 설정 빠르게 전환":
        "Toggle simple settings like theme/model quickly",
    "Claude Code 환경 진단 (auth/MCP/hook 상태)":
        "Diagnose your Claude Code environment (auth/MCP/hook)",
    "현재 계정 로그아웃": "Log out of the current account",
    "Claude 계정 로그인": "Log in to a Claude account",
    "모델 변경 (Opus/Sonnet/Haiku)": "Switch model (Opus/Sonnet/Haiku)",
    "프로젝트 메모리 보기/편집": "View / edit project memory",
    "사용 가능한 서브에이전트 목록": "List available sub-agents",
    "설정된 훅 목록": "List configured hooks",
    "MCP 서버 목록 + 연결 상태": "MCP server list + connection status",
    "플러그인 마켓플레이스 · 설치/제거": "Plugin marketplace · install / uninstall",
    "상태라인 커스터마이즈": "Customize the statusline",
    "이전 세션 리스트 · 재개": "Previous sessions · resume",

    # Cheatsheet key descs
    "Plan Mode ↔ 실행 모드 토글": "Toggle Plan Mode ↔ execute mode",
    "현재 응답/도구 실행 중단": "Cancel the current response / tool",
    "Claude Code 종료": "Exit Claude Code",
    "출력 스타일 · 토큰 디테일 토글": "Toggle output style · token detail",
    "터미널 화면 클리어 (세션 유지)": "Clear terminal (session preserved)",
    "마지막 메시지 편집 (더블 Esc)": "Edit last message (double Esc)",
    "프롬프트 앞에 ! — 사용자 측에서 셸 실행 후 출력 공유":
        "Prefix with ! — run a shell command and share its output",
    "이전/다음 프롬프트 히스토리 이동": "Previous / next prompt history",
    "파일/경로 자동완성": "File / path autocomplete",

    # ── Onboarding steps (server/guide.py) ──
    "Claude Code CLI 설치": "Install the Claude Code CLI",
    "`~/.claude` 디렉토리가 존재해야 모든 기능이 동작합니다.":
        "Every feature requires the `~/.claude` directory to exist.",
    "npm i -g @anthropic-ai/claude-code 또는 공식 설치 스크립트.":
        "Run `npm i -g @anthropic-ai/claude-code` or use the official installer.",
    "전역 CLAUDE.md 작성": "Write a global CLAUDE.md",
    "모든 세션에 로드되는 개인/팀 규약. 100자 이상 작성을 권장합니다.":
        "Personal/team rules loaded into every session. At least 100 characters is recommended.",
    "CLAUDE.md 탭에서 편집 · `/init` 으로 자동 생성 가능.":
        "Edit from the CLAUDE.md tab · or bootstrap with `/init`.",
    "권한(permissions) 설정": "Configure permissions",
    "allow / deny 규칙으로 위험한 명령을 차단합니다.":
        "Use allow/deny rules to block dangerous commands.",
    "권한 탭에서 추천 프로파일 클릭 — rm -rf /, curl | sh 등 기본 차단.":
        "Click a recommended profile from the Permissions tab — blocks rm -rf /, curl | sh, etc.",
    "훅(hooks) 하나 이상 설정": "Configure at least one hook",
    "SessionStart/Stop · PreToolUse 훅으로 자동화 · 안전장치를 추가합니다.":
        "Add automation and safety nets with SessionStart/Stop · PreToolUse hooks.",
    "훅 탭 · PreToolUse 에 시크릿 감지 스크립트 추천.":
        "Hooks tab · recommended: a secret-scan script on PreToolUse.",
    "스킬 1개 이상 보유": "Own at least one skill",
    "스킬은 클로드가 자동으로 적재하는 지식 모듈입니다.":
        "Skills are knowledge modules Claude loads on demand.",
    "Everything Claude Code 설치 시 183개가 한 번에 추가됩니다.":
        "Installing Everything Claude Code adds 183 at once.",
    "서브에이전트 1개 이상": "At least one sub-agent",
    "특정 작업에 특화된 전담 에이전트를 만들어 두면 품질이 급상승.":
        "Dedicated agents for specific tasks raise quality dramatically.",
    "에이전트 탭 · planner / code-reviewer 먼저 만들어보세요.":
        "Agents tab · start with planner / code-reviewer.",
    "커스텀 슬래시 명령어": "Custom slash commands",
    "자주 쓰는 프롬프트를 /command 로 축약 — 반복 작업 자동화.":
        "Turn recurring prompts into /commands — automate repetitive work.",
    "슬래시 명령어 탭에서 /tdd, /plan, /code-review 등 추가.":
        "Add /tdd, /plan, /code-review, etc. from the Slash commands tab.",
    "MCP 커넥터 1개 이상": "At least one MCP connector",
    "GitHub / Context7 / Playwright 등 외부 시스템 연결.":
        "Connect external systems like GitHub / Context7 / Playwright.",
    "MCP 탭에서 원클릭 설치 · 처음엔 context7 + github 조합 추천.":
        "One-click install from the MCP tab · start with context7 + github.",
    "플러그인 또는 마켓플레이스 추가": "Add a plugin or marketplace",
    "Everything Claude Code 같은 번들로 한 번에 셋업.":
        "Bundles like Everything Claude Code set you up in one shot.",
    "플러그인 탭 → 마켓 추가 → everything-claude-code 설치.":
        "Plugins tab → add market → install everything-claude-code.",
    "출력 스타일 선택": "Pick an output style",
    "답변 톤/포맷을 프로젝트 성격에 맞게 고정.":
        "Lock response tone/format to your project's character.",
    "출력 스타일 탭에서 커스텀 스타일을 만들거나 기본값 확인.":
        "From the Output styles tab, create a custom style or check the default.",
}

NEW_ZH = {
    # ── NAV ──
    "시작하기": "入门指南",
    "가이드 & 툴": "指南与工具",
    "처음 사용자를 위한 단계별 체크리스트 (현재 셋업 자동 감지)":
        "面向新用户的分步清单（自动检测当前配置）",
    "외부 가이드 · 유용한 툴 · 베스트 프랙티스 · 치트시트":
        "外部指南 · 实用工具 · 最佳实践 · 速查表",

    # ── Onboarding UI ──
    "🚀 시작하기": "🚀 入门指南",
    "처음 사용자를 위한 단계별 체크리스트 — 현재 ~/.claude 상태를 실시간으로 감지합니다.":
        "面向新用户的分步清单 — 实时检测 ~/.claude 状态。",
    "셋업 진행률": "配置进度",
    "완료 🎉 — 이제 AI 종합 평가 탭에서 품질 점수를 받아보세요.":
        "已完成 🎉 — 现在可在「AI 综合评估」选项卡获取质量评分。",
    "남은 단계를 하나씩 체크하면 Claude Code 를 더 안전하고 생산적으로 쓸 수 있습니다.":
        "逐项完成剩余步骤，让 Claude Code 更安全、更高效。",
    "모든 항목 체크 후엔 'AI 종합 평가' 탭에서 0~100 점수를 받아보세요.":
        "全部勾选后，请前往「AI 综合评估」获取 0~100 分的评分。",
    "가이드 허브 → 유용한 툴 탭에서 한 번에 설치 가능한 팩을 찾을 수 있습니다.":
        "指南中心 → 实用工具标签包含一键安装的工具包。",
    "완료": "已完成",
    "필요": "待完成",
    "해당 탭으로": "前往对应标签",
    "공식 문서": "官方文档",

    # ── Guide Hub UI labels ──
    "📚 가이드 & 툴": "📚 指南与工具",
    "세 리소스(everything-claude-code · claude-code-best-practice · 위키독스 한국어 가이드) 를 한 곳에서.":
        "三大资源（everything-claude-code · claude-code-best-practice · 韩文 WikiDocs 指南）一站聚合。",
    "🧰 유용한 툴": "🧰 实用工具",
    "🔗 외부 가이드": "🔗 外部指南",
    "💡 베스트 프랙티스": "💡 最佳实践",
    "⌨️ 치트시트": "⌨️ 速查表",
    "제작": "作者",
    "리포 열기": "打开仓库",
    "하이라이트": "亮点",
    "설치 & 사용": "安装与使用",
    "복사": "复制",
    "복사됨": "已复制",
    "클립보드에 복사됨": "已复制到剪贴板",
    "복사 실패": "复制失败",
    "데이터 없음": "无数据",
    "바로가기": "打开",
    "🎓 추천 학습 경로": "🎓 推荐学习路径",
    "추천 학습 경로": "推荐学习路径",
    "위키독스 한국어 가이드 기초 7강 → 개발 17강 순으로 학습":
        "依次学习 WikiDocs 韩文指南：基础 7 讲 → 开发 17 讲",
    "best-practice 레포에서 창시자(Boris Cherny) 워크플로 영상 시청":
        "在 best-practice 仓库观看创始人 (Boris Cherny) 工作流视频",
    "everything-claude-code 플러그인 설치 → 실전 기능 확보":
        "安装 everything-claude-code 插件 → 获取生产级能力",
    "시작하기 탭으로 돌아와 체크리스트 완료":
        "返回「入门指南」并完成清单",
    "/ 내장 슬래시 명령어": "/ 内置斜杠命令",
    "내장 슬래시 명령어": "内置斜杠命令",
    "⌨️ 키보드 단축키": "⌨️ 键盘快捷键",
    "키보드 단축키": "键盘快捷键",
    "개": "项",

    # ── server/guide.py — Toolkit subtitles / meta ──
    "멀티 플랫폼 클로드 코드 최적화 팩 (48 agents · 183 skills · 79 commands)":
        "多平台 Claude Code 优化套件（48 个 agents · 183 个 skills · 79 个 commands）",
    "47k ⭐ · 82 가지 팁 모음 + 창시자(Boris Cherny) 워크플로":
        "47k ⭐ · 82 条技巧 + 创始人 (Boris Cherny) 工作流",
    "클래스 101 + 레퍼런스 21개 · 한국어 전체 가이드북":
        "101 课程 + 21 章参考 · 完整韩文指南",
    "웹/eBook": "网页 / 电子书",
    "237 추천": "237 条推荐",
    "위키독스": "WikiDocs",

    # ── Toolkit highlights ──
    "Claude Code / Cursor / Codex / OpenCode 크로스 플랫폼":
        "跨平台：Claude Code / Cursor / Codex / OpenCode",
    "AgentShield 보안 감사 (1282 tests, 102 정적 룰)":
        "AgentShield 安全审计（1,282 测试，102 静态规则）",
    "Continuous Learning v2 — 세션에서 인스팅크트 자동 추출":
        "Continuous Learning v2 — 从会话中自动提取直觉",
    "토큰 최적화 (Sonnet 전환, thinking 10k cap, compact 50%)":
        "令牌优化（切换 Sonnet、thinking 上限 10k、50% 触发 compact）",
    "Agents · Commands · Skills 3축 정리":
        "按三大支柱组织：Agents · Commands · Skills",
    "핫 기능: Routines · Ultrareview · Agent Teams · Auto Mode · Computer Use":
        "热门功能：Routines · Ultrareview · Agent Teams · Auto Mode · Computer Use",
    "Research → Plan → Execute → Review → Ship 표준 흐름":
        "标准流程：Research → Plan → Execute → Review → Ship",
    "prototype > PRD · PR 은 작게(median 118 lines)":
        "prototype > PRD · PR 保持小巧（中位 118 行）",
    "설치부터 실전까지 단계별 실습 (기초 7 · 개발 17 · 비즈니스 15)":
        "从安装到实战的分步练习（基础 7 · 开发 17 · 商务 15）",
    "크리에이터 · 연구 · 금융 · 법무/HR · 의료 특화 트랙":
        "专项赛道：创作者 · 研究 · 金融 · 法务/HR · 医疗",
    "공식 문서 변경 사항 실시간 반영 (최종 2026-04-20)":
        "实时同步官方文档变更（最后更新 2026-04-20）",
    "창시자 워크플로, 스피너 동사 187개, 소스 분석서 별첨":
        "创始人工作流、187 个加载动画动词、源码分析附录",

    # ── Toolkit install labels ──
    "플러그인 마켓플레이스 추가 (권장)": "添加插件市场（推荐）",
    "전체 프로파일 설치": "安装完整套件",
    "수동 설치 (macOS/Linux)": "手动安装 (macOS/Linux)",
    "레포 클론 (참고용 문서)": "克隆仓库（参考文档）",
    "웹에서 바로 읽기": "在网页上阅读",

    # ── Toolkit categories ──
    "창시자의 핵심 팁": "创始人核心技巧",
    "워크플로 패턴": "工作流模式",
    "클래스 101 — 기초": "101 课程 — 基础",
    "클래스 101 — 개발": "101 课程 — 开发",
    "클래스 101 — 비즈니스": "101 课程 — 商务",
    "레퍼런스 21권": "21 章参考",

    "항상 Plan Mode 로 시작하라 (Boris Cherny)":
        "永远从 Plan Mode 开始 (Boris Cherny)",
    "컨텍스트 40% 이상은 품질 저하 — 30% 이하 유지":
        "上下文超过 40% 会降质 — 保持在 30% 以下",
    "실패한 시도는 /rewind 로 되돌리기":
        "用 /rewind 回滚失败尝试",
    "/compact 는 자동보다 힌트를 직접 주고 호출":
        "手动带提示调用 /compact，而不是依赖自动压缩",
    "새 태스크 = 새 세션, 관련 태스크만 컨텍스트 재사용":
        "新任务 = 新会话；仅相关任务复用上下文",
    "Superpowers · gstack · BMAD-METHOD · Spec Kit 참조 구현":
        "参考实现：Superpowers · gstack · BMAD-METHOD · Spec Kit",
    "Cross-Model: Claude Code + Codex 조합":
        "跨模型：Claude Code + Codex 组合",
    "Agent Teams — 공유 코드베이스에 병렬 에이전트":
        "Agent Teams — 在共享代码库上并行运行多个 agent",

    # Wikidocs items
    "설치 · 대화와 세션 · 모델과 Effort":
        "安装 · 对话与会话 · 模型与 Effort",
    "자율권과 안전 · 컨텍스트 관리":
        "自主权与安全 · 上下文管理",
    "CLAUDE.md 작업 기억 · 첫 실전 프로젝트":
        "CLAUDE.md 作业记忆 · 首个实战项目",
    "코드베이스 탐색 · TDD · 리팩토링 · Hooks":
        "代码库探索 · TDD · 重构 · Hooks",
    "Git PR 코드리뷰 · GitHub Actions · Worktree 병렬":
        "Git PR 代码审查 · GitHub Actions · Worktree 并行",
    "Skills 활용/개발 · MCP · 서브에이전트 팀 · 팀 온보딩":
        "Skills 使用/开发 · MCP · 子 agent 团队 · 团队导入",
    "이메일 자동관리 · 회의록 · Excel · 보고서":
        "邮件自动化 · 会议纪要 · Excel · 报告",
    "일일 브리핑 · PPT 자동 · Chrome 자동화":
        "每日简报 · PPT 自动生成 · Chrome 自动化",
    "SOP · 경쟁사 병렬분석 · Vibe Coding 앱":
        "SOP · 竞争对手并行分析 · Vibe Coding 应用",
    "퀵 레퍼런스 · 설정 · 권한 · 슬래시 · 단축키":
        "快速参考 · 设置 · 权限 · 斜杠 · 快捷键",
    "MCP · 훅 · 서브에이전트 · 스킬 · IDE · CI/CD":
        "MCP · Hooks · 子 agent · Skills · IDE · CI/CD",
    "고급 기능 · 베스트 프랙티스 · 플러그인 · 보안/프라이버시":
        "高级功能 · 最佳实践 · 插件 · 安全/隐私",

    # ── Best practices ──
    "Research → Plan → Execute → Review → Ship":
        "Research → Plan → Execute → Review → Ship",
    "모든 주요 작업은 이 5단계로. 각 단계마다 슬래시 명령어를 붙이면 품질이 올라간다.":
        "所有核心工作都按这 5 步推进。每一步配合斜杠命令，质量大幅提升。",
    "/ask, /docs, 레포 탐색으로 맥락 먼저. 코드 쓰기 전 WHY 정리.":
        "先用 /ask、/docs、仓库浏览理清背景，写代码前想明白 WHY。",
    "/plan 또는 Plan Mode. 파일별 변경안 · 리스크 · 롤백 플랜까지.":
        "/plan 或 Plan Mode。按文件列出修改、风险与回滚方案。",
    "/tdd 로 테스트 먼저. 한 묶음씩 작게 구현 · 작은 PR 유지.":
        "用 /tdd 先写测试。小批量实现，保持 PR 简洁。",
    "/code-review + /security-scan. 자동 리뷰 통과 후 사람 리뷰.":
        "/code-review + /security-scan。自动审查通过后再人工复核。",
    "/e2e 로 골든 패스 검증. 배포 후 /canary-watch 로 회귀 감시.":
        "用 /e2e 验证黄金路径。发布后用 /canary-watch 监控回归。",

    "토큰 · 컨텍스트 최적화": "令牌与上下文优化",
    "Claude Code 에서 비용·지연·품질 모두 개선하는 핵심 스위치 5개.":
        "在 Claude Code 中同时改善成本、延迟与质量的 5 个核心开关。",
    "모델 라우팅": "模型路由",
    "일상은 Sonnet 4.6, 무거운 분석만 Opus 4.7 — 평균 60% 비용 절감.":
        "日常用 Sonnet 4.6，重度分析用 Opus 4.7 — 平均节省约 60% 成本。",
    "Thinking 캡": "Thinking 上限",
    "extended thinking 10,000 토큰 이하로 제한. 무제한은 가성비 나쁨.":
        "将扩展思考限制在 10,000 tokens 以内。无上限性价比差。",
    "Compact 시점": "Compact 时机",
    "자동 95% 대신 50% 에서 직접 /compact. 품질 유지 + 캐시 친화.":
        "在 50% 处手动 /compact 而非等到自动 95%。保持质量且缓存友好。",
    "MCP 10개 이하": "MCP ≤ 10 个",
    "활성 MCP 서버는 10개 이하 — 매 턴마다 도구 디스크립션 비용.":
        "保持活跃 MCP 服务器 ≤10 — 每轮对话都要计入工具描述。",
    "Session 분리": "会话隔离",
    "새 태스크는 새 세션. 관련 태스크만 /continue 유지.":
        "新任务开新会话；仅相关任务继续使用 /continue。",

    "Plan Mode · 컨텍스트 습관": "Plan Mode 与上下文习惯",
    "Boris Cherny(Claude Code 창시자)가 반복 강조하는 운용 팁.":
        "Boris Cherny（Claude Code 创始人）反复强调的操作要点。",
    "Plan 먼저": "先做计划",
    "모든 비자명한 작업은 Plan Mode 로. 코드 생성 전 사용자 승인을 받는다.":
        "所有非明显的任务都从 Plan Mode 开始，先获得用户批准再动代码。",
    "컨텍스트 감시": "监控上下文",
    "40% 넘어가면 품질 저하. /clear · /compact · /rewind 세 가지 스위치.":
        "超过 40% 质量下降。三个开关：/clear · /compact · /rewind。",
    "Prototype > PRD": "Prototype > PRD",
    "길게 쓴 스펙보다 20~30개의 작은 프로토타입이 빠른 수렴을 준다.":
        "20~30 个小原型比长篇规格说明收敛更快。",
    "작은 PR": "小 PR",
    "PR 사이즈 median 118 lines. 커지면 쪼개라 — 리뷰 품질 & 롤백 용이.":
        "PR 中位大小约 118 行。过大就拆 — 审查质量 & 回滚更友好。",
    "Squash Merge": "Squash 合并",
    "히스토리 선형 유지. rebase 보다 squash 가 충돌 복구에 유리.":
        "保持历史线性。相比 rebase，squash 在冲突恢复上更优。",

    "보안 · 안전 기본값": "安全 · 默认防护",
    "로컬/개인 사용에서도 꼭 켜두면 좋은 안전 스위치.":
        "即便本地/个人使用也建议开启的安全开关。",
    "Secret 훅": "Secret Hook",
    "PreCommit 훅에서 sk-, ghp_, AKIA 패턴 검사 — 실수 커밋 방지.":
        "PreCommit 钩子扫描 sk-、ghp_、AKIA 模式 — 防止误提交。",
    "Deny 권한": "Deny 权限",
    "permissions.deny 에 rm -rf /, curl | sh, ssh 등 위험 명령 차단.":
        "通过 permissions.deny 屏蔽 rm -rf /、curl | sh、ssh 等危险命令。",
    "Auto Mode": "Auto Mode",
    "개별 승인 프롬프트 대신 분류기 기반 Auto Mode 로 일관성 확보.":
        "用分类器驱动的 Auto Mode 代替逐次确认，保证一致性。",
    "MCP 범위": "MCP 作用域",
    "로컬 전용 MCP 는 OK, 인터넷 쓰는 MCP 는 allow-list / readOnly 권장.":
        "本地 MCP 没问题；联网 MCP 建议 allow-list / readOnly。",

    # ── Cheatsheet command descs ──
    "Claude Code 사용법과 명령어 전체 목록":
        "Claude Code 用法与完整命令列表",
    "현재 세션 컨텍스트 초기화 — 새 주제 시작 시":
        "重置当前会话上下文 — 适合切换新主题",
    "대화를 요약해 컨텍스트 압축 (힌트 프롬프트 동반 권장)":
        "把对话压缩为摘要（建议附带提示词）",
    "마지막 턴(또는 범위)을 되돌리고 실패 시도 제거":
        "回滚最后一轮（或范围），丢弃失败尝试",
    "같은 태스크를 새 세션에서 이어서":
        "在新会话继续同一任务",
    "Plan Mode 진입 — 코드 변경 전 승인 단계":
        "进入 Plan Mode — 代码变更前的审批阶段",
    "Opus 4.6 Fast 모드 토글 (빠른 출력, 같은 모델)":
        "切换 Opus 4.6 Fast 模式（输出更快，模型不变）",
    "버그 재현 스펙 → 실패 테스트 → 수정 자동 흐름":
        "自动流程：复现规格 → 失败测试 → 修复",
    "현재 레포용 CLAUDE.md 를 자동 초기화":
        "为当前仓库自动初始化 CLAUDE.md",
    "PR 코드리뷰 — 체크리스트 기반":
        "基于清单的 PR 代码审查",
    "현재 브랜치 변경분 보안 리뷰":
        "对当前分支改动做安全审查",
    "테마·모델 등 단순 설정 빠르게 전환":
        "快速切换主题/模型等简单设置",
    "Claude Code 환경 진단 (auth/MCP/hook 상태)":
        "诊断 Claude Code 环境（auth/MCP/hook 状态）",
    "현재 계정 로그아웃": "注销当前账户",
    "Claude 계정 로그인": "登录 Claude 账户",
    "모델 변경 (Opus/Sonnet/Haiku)": "切换模型（Opus/Sonnet/Haiku）",
    "프로젝트 메모리 보기/편집": "查看 / 编辑项目记忆",
    "사용 가능한 서브에이전트 목록": "可用的子 agent 列表",
    "설정된 훅 목록": "已配置的 hook 列表",
    "MCP 서버 목록 + 연결 상태": "MCP 服务器列表 + 连接状态",
    "플러그인 마켓플레이스 · 설치/제거": "插件市场 · 安装 / 卸载",
    "상태라인 커스터마이즈": "自定义状态栏",
    "이전 세션 리스트 · 재개": "过往会话列表 · 继续",

    # Cheatsheet key descs
    "Plan Mode ↔ 실행 모드 토글": "切换 Plan Mode ↔ 执行模式",
    "현재 응답/도구 실행 중단": "中断当前响应 / 工具执行",
    "Claude Code 종료": "退出 Claude Code",
    "출력 스타일 · 토큰 디테일 토글": "切换输出样式 · 令牌细节",
    "터미널 화면 클리어 (세션 유지)": "清空终端（会话保留）",
    "마지막 메시지 편집 (더블 Esc)": "编辑最后一条消息（连按两次 Esc）",
    "프롬프트 앞에 ! — 사용자 측에서 셸 실행 후 출력 공유":
        "以 ! 作前缀 — 在用户侧执行 shell 并分享输出",
    "이전/다음 프롬프트 히스토리 이동": "上一条 / 下一条提示词历史",
    "파일/경로 자동완성": "文件 / 路径自动补全",

    # ── Onboarding steps ──
    "Claude Code CLI 설치": "安装 Claude Code CLI",
    "`~/.claude` 디렉토리가 존재해야 모든 기능이 동작합니다.":
        "所有功能都依赖 `~/.claude` 目录存在。",
    "npm i -g @anthropic-ai/claude-code 또는 공식 설치 스크립트.":
        "运行 `npm i -g @anthropic-ai/claude-code` 或使用官方安装脚本。",
    "전역 CLAUDE.md 작성": "编写全局 CLAUDE.md",
    "모든 세션에 로드되는 개인/팀 규약. 100자 이상 작성을 권장합니다.":
        "在所有会话中加载的个人/团队约定。建议不少于 100 个字符。",
    "CLAUDE.md 탭에서 편집 · `/init` 으로 자동 생성 가능.":
        "在 CLAUDE.md 标签中编辑 · 也可用 `/init` 自动生成。",
    "권한(permissions) 설정": "配置权限（permissions）",
    "allow / deny 규칙으로 위험한 명령을 차단합니다.":
        "通过 allow / deny 规则屏蔽危险命令。",
    "권한 탭에서 추천 프로파일 클릭 — rm -rf /, curl | sh 등 기본 차단.":
        "在权限标签中点击推荐配置 — 默认屏蔽 rm -rf /、curl | sh 等。",
    "훅(hooks) 하나 이상 설정": "配置至少一个 hook",
    "SessionStart/Stop · PreToolUse 훅으로 자동화 · 안전장치를 추가합니다.":
        "通过 SessionStart/Stop · PreToolUse 钩子添加自动化与安全防护。",
    "훅 탭 · PreToolUse 에 시크릿 감지 스크립트 추천.":
        "Hooks 标签 · 建议在 PreToolUse 上挂载密钥扫描脚本。",
    "스킬 1개 이상 보유": "至少拥有一个 skill",
    "스킬은 클로드가 자동으로 적재하는 지식 모듈입니다.":
        "Skills 是 Claude 按需加载的知识模块。",
    "Everything Claude Code 설치 시 183개가 한 번에 추가됩니다.":
        "安装 Everything Claude Code 会一次性加入 183 个。",
    "서브에이전트 1개 이상": "至少一个子 agent",
    "특정 작업에 특화된 전담 에이전트를 만들어 두면 품질이 급상승.":
        "为特定任务创建专用 agent，能显著提升质量。",
    "에이전트 탭 · planner / code-reviewer 먼저 만들어보세요.":
        "Agents 标签 · 建议先创建 planner / code-reviewer。",
    "커스텀 슬래시 명령어": "自定义斜杠命令",
    "자주 쓰는 프롬프트를 /command 로 축약 — 반복 작업 자동화.":
        "把常用提示词做成 /command — 自动化重复工作。",
    "슬래시 명령어 탭에서 /tdd, /plan, /code-review 등 추가.":
        "在斜杠命令标签添加 /tdd、/plan、/code-review 等。",
    "MCP 커넥터 1개 이상": "至少一个 MCP 连接器",
    "GitHub / Context7 / Playwright 등 외부 시스템 연결.":
        "连接 GitHub / Context7 / Playwright 等外部系统。",
    "MCP 탭에서 원클릭 설치 · 처음엔 context7 + github 조합 추천.":
        "MCP 标签一键安装 · 建议先用 context7 + github 组合。",
    "플러그인 또는 마켓플레이스 추가": "添加插件或插件市场",
    "Everything Claude Code 같은 번들로 한 번에 셋업.":
        "使用像 Everything Claude Code 这样的合集一次完成配置。",
    "플러그인 탭 → 마켓 추가 → everything-claude-code 설치.":
        "Plugins 标签 → 添加市场 → 安装 everything-claude-code。",
    "출력 스타일 선택": "选择输出样式",
    "답변 톤/포맷을 프로젝트 성격에 맞게 고정.":
        "根据项目性质固定回复的语气 / 格式。",
    "출력 스타일 탭에서 커스텀 스타일을 만들거나 기본값 확인.":
        "在 Output styles 标签中创建自定义样式或查看默认值。",
}
