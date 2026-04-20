"""실 브라우저 스캔에서 발견된 UI 잔존 fragment 번역.

대부분 사용자 데이터(CLAUDE.md · 세션 · 스킬 설명 등)는 원본 언어 그대로 두는 것이
옳지만, 다음 카테고리는 UI 라벨이라 번역이 필요하다:

1. server/system.py 가 내보내는 권한 preset 이름/설명
2. server/device.py 가 내보내는 "맥북" · "아이맥" 같은 디바이스 라벨
3. overview 에서 템플릿 리터럴로 조합되는 짧은 Korean 토큰
4. env var · model 설명 중 Korean suffix

runtime 은 최근 패치로 짧은 키도 Hangul word-boundary 로 안전하게 치환 가능.
"""

NEW_EN = {
    # server/system.py permission presets
    "균형형 (Balanced)": "Balanced",
    "개발자형 (Developer)": "Developer",
    "안전 우선 (Cautious)": "Cautious",
    "탐색 모드 (Read-only)": "Read-only",
    "기본적인 안전과 자동화를 균형있게": "Balanced safety and automation",
    "자주 쓰는 도구 자동 승인 — 빠른 반복 작업": "Auto-approve common tools — fast iteration",
    "모든 변경 작업에 수동 승인": "Manual approval for every mutating action",
    "읽기 전용": "Read-only",
    "개발자형": "Developer",
    "안전 우선": "Cautious",
    "탐색 모드": "Read-only",
    "Sonnet (균형형)": "Sonnet (Balanced)",

    # device labels
    "맥북": "MacBook",
    "아이맥": "iMac",
    "맥미니": "Mac mini",
    "맥프로": "Mac Pro",
    "맥스튜디오": "Mac Studio",

    # short glue tokens
    "개": " ",
    "자": " chars",
    "회": "×",
    "건": " items",
    "종": " kinds",
    "명": " people",
    "일": "d",
    "시간": "h",
    "분": "m",
    "초": "s",
    "그 중": "of which",
    "그중": "of which",
    "30일": "30 days",
    "60일": "60 days",
    "7일": "7 days",
    "강화": "reinforcement",
    "슬림화": "slimming",
    "최소화": "minimize",
    "최대화": "maximize",
    "활성화": "enable",
    "비활성화": "disable",

    "<git url 옵션>": "<git url option>",
    "<workflow 에 어떻게 도움되는지>": "<how it helps the workflow>",
    "<왜 도움이 되는지>": "<why it helps>",

    # built-in agent descriptions (server/agents.py)
    "범용 에이전트 — 복잡한 질의 조사 / 코드 검색 / 멀티스텝 작업.": "General-purpose agent — complex research, code search, multi-step tasks.",
    "코드베이스 탐색 전용 고속 에이전트.": "Fast agent specialized for codebase exploration.",
    "구현 전략 수립 — 단계별 플랜과 핵심 파일 식별.": "Devise implementation strategy — step plan + key-file identification.",
    "Claude Code 상태라인 커스터마이징.": "Customize the Claude Code status line.",
}

NEW_ZH = {
    "균형형 (Balanced)": "均衡型 (Balanced)",
    "개발자형 (Developer)": "开发者型 (Developer)",
    "안전 우선 (Cautious)": "安全优先 (Cautious)",
    "탐색 모드 (Read-only)": "探索模式 (Read-only)",
    "기본적인 안전과 자동화를 균형있게": "在安全性与自动化之间平衡",
    "자주 쓰는 도구 자동 승인 — 빠른 반복 작업": "自动批准常用工具 — 快速迭代",
    "모든 변경 작업에 수동 승인": "对所有变更操作手动批准",
    "읽기 전용": "只读",
    "개발자형": "开发者型",
    "안전 우선": "安全优先",
    "탐색 모드": "探索模式",
    "Sonnet (균형형)": "Sonnet (均衡型)",

    "맥북": "MacBook",
    "아이맥": "iMac",
    "맥미니": "Mac mini",
    "맥프로": "Mac Pro",
    "맥스튜디오": "Mac Studio",

    "개": " ",
    "자": " 字",
    "회": " 次",
    "건": " 条",
    "종": " 种",
    "명": " 人",
    "일": " 天",
    "시간": " 小时",
    "분": " 分",
    "초": " 秒",
    "그 중": "其中",
    "그중": "其中",
    "30일": "30 天",
    "60일": "60 天",
    "7일": "7 天",
    "강화": "强化",
    "슬림화": "精简",
    "최소화": "最小化",
    "최대화": "最大化",
    "활성화": "启用",
    "비활성화": "禁用",

    "<git url 옵션>": "<git url 选项>",
    "<workflow 에 어떻게 도움되는지>": "<如何帮助工作流>",
    "<왜 도움이 되는지>": "<为什么有帮助>",

    "범용 에이전트 — 복잡한 질의 조사 / 코드 검색 / 멀티스텝 작업.": "通用代理 — 复杂查询调研、代码搜索、多步任务。",
    "코드베이스 탐색 전용 고속 에이전트.": "专门用于代码库探索的高速代理。",
    "구현 전략 수립 — 단계별 플랜과 핵심 파일 식별.": "制定实施策略 — 分步计划与关键文件识别。",
    "Claude Code 상태라인 커스터마이징.": "自定义 Claude Code 状态栏。",
}
