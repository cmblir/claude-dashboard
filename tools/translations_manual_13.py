"""v2.38.0 — Quick Settings drawer: per-user prefs (UI / AI / Behavior / Workflow).

Adds EN + ZH translations for every t('...') call site and data-i18n label
introduced by the Quick Settings drawer (dist/index.html). Imported by
translations_manual.py.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # ── Drawer chrome ───────────────────────────────────────────
    "빠른 설정 — 모든 파라미터": "Quick Settings — All Parameters",
    "이 섹션 초기화": "Reset this section",
    "모두 초기화": "Reset all",
    "이 섹션의 모든 값을 기본값으로 되돌릴까요?":
        "Reset all values in this section to defaults?",
    "모든 빠른 설정을 초기화할까요? 이 작업은 되돌릴 수 없습니다.":
        "Reset all Quick Settings? This cannot be undone.",
    "스키마 로딩 실패": "Schema failed to load",

    # Section tabs
    "UI · 외관": "UI · Appearance",
    "AI 기본값": "AI Defaults",
    "워크플로우 기본값": "Workflow Defaults",

    # Section descriptions
    "테마·언어·밀도·강조 색 등 외관 관련 설정. 즉시 적용됩니다.":
        "Appearance: theme, language, density, accent color. Applied immediately.",
    "AI 호출의 기본 파라미터. 워크플로우 노드와 챗봇이 이 값을 시작점으로 사용합니다.":
        "Default parameters for AI calls. Workflow nodes and chat use these as starting values.",
    "대시보드의 기본 동작·알림·폴링 주기.":
        "Dashboard default behaviour, notifications, polling cadence.",
    "워크플로우 에디터의 기본값. 새 노드 생성 시 이 값으로 prefill 됩니다.":
        "Workflow-editor defaults. New nodes pre-fill with these values.",

    # ── UI rows ─────────────────────────────────────────────────
    "auto/dark/light/midnight/forest/sunset": "auto/dark/light/midnight/forest/sunset",
    "ko/en/zh — 변경 시 페이지 새로고침": "ko/en/zh — page reloads on change",
    "밀도": "Density",
    "카드/창의 안쪽 여백": "Inner padding of cards and windows",
    "글자 크기": "Font size",
    "본문 기본 폰트 크기": "Base body font size",
    "모션 감소": "Reduced motion",
    "애니메이션·전환을 거의 0으로": "Animations and transitions near zero",
    "강조 색": "Accent color",
    "액티브 상태·버튼 강조 색": "Active state and button highlight color",
    "사이드바 접힘": "Sidebar collapsed",
    "데스크톱에서 사이드바 기본 접힘": "Sidebar starts collapsed on desktop",
    "마스코트 표시": "Show mascot",
    "우하단 점프 캐릭터": "Bottom-right jumping character",
    "컴팩트 사이드바": "Compact sidebar",
    "카테고리 라벨 숨김": "Hide category labels",

    # ── AI rows ─────────────────────────────────────────────────
    "기본 프로바이더": "Default provider",
    "예: claude:sonnet, openai:gpt-4.1, ollama:llama3.1":
        "e.g. claude:sonnet, openai:gpt-4.1, ollama:llama3.1",
    "Effort": "Effort",
    "low / medium / high — 추론 깊이": "low / medium / high — reasoning depth",
    "Temperature": "Temperature",
    "0.0 결정적 ↔ 2.0 다양": "0.0 deterministic ↔ 2.0 diverse",
    "Top-p": "Top-p",
    "핵 샘플링 누적 확률": "Nucleus-sampling cumulative probability",
    "Max output tokens": "Max output tokens",
    "응답 최대 토큰": "Maximum tokens in the response",
    "Thinking budget": "Thinking budget",
    "확장 사고 예산 (0 = 비활성)": "Extended-thinking budget (0 = disabled)",
    "Extended thinking": "Extended thinking",
    "Claude 확장 사고 모드": "Claude extended-thinking mode",
    "스트리밍 응답": "Stream responses",
    "SSE 토큰 스트리밍": "SSE token streaming",
    "폴백 체인 사용": "Use fallback chain",
    "실패 시 다음 프로바이더로 자동 폴백":
        "Auto-fallback to the next provider on failure",

    # ── Behavior rows ──────────────────────────────────────────
    "한도 도달 시 자동 재개 워커": "Worker that auto-resumes on rate-limit",
    "Slack 알림": "Slack notifications",
    "워크플로우 완료/실패 알림": "Workflow complete/fail notifications",
    "Discord 알림": "Discord notifications",
    "텔레메트리 갱신(초)": "Telemetry refresh (s)",
    "0 = 비활성": "0 = disabled",
    "세션 spawn 전 확인": "Confirm before session spawn",
    "CLI 세션 시작 직전 모달": "Modal right before starting a CLI session",
    "워크플로우 자동 저장": "Autosave workflows",
    "편집 시 디바운스 저장": "Debounced save while editing",
    "라이브 티커(초)": "Live ticker (s)",
    "실시간 상태 폴링 주기": "Realtime status polling interval",
    "완료 알림 소리": "Sound on complete",
    "워크플로우 종료 시 비프": "Beep when a workflow finishes",
    "마지막 탭 자동 열기": "Open last tab on load",
    "재방문 시 직전 탭 복원": "Restore the previously open tab",

    # ── Workflow rows ──────────────────────────────────────────
    "기본 반복 횟수": "Default iterations",
    "Repeat 노드 기본값": "Default for the repeat node",
    "반복 간격(초)": "Repeat delay (s)",
    "반복 간 대기": "Wait between iterations",
    "Dry-run 기본": "Dry-run by default",
    "실행 시 dry-run 토글 기본 ON": "Dry-run toggle starts ON when running",
    "미니맵 표시": "Show minimap",
    "캔버스 우하단 미니맵": "Bottom-right canvas minimap",
    "그리드 스냅": "Snap to grid",
    "노드 이동 시 격자 정렬": "Snap nodes to a grid while dragging",
    "그리드 크기(px)": "Grid size (px)",
    "8~64": "8 to 64",
}

NEW_ZH: dict[str, str] = {
    # Drawer chrome
    "빠른 설정 — 모든 파라미터": "快速设置 — 所有参数",
    "이 섹션 초기화": "重置此节",
    "모두 초기화": "全部重置",
    "이 섹션의 모든 값을 기본값으로 되돌릴까요?":
        "将此节的所有值重置为默认值？",
    "모든 빠른 설정을 초기화할까요? 이 작업은 되돌릴 수 없습니다.":
        "重置所有快速设置？此操作不可撤销。",
    "스키마 로딩 실패": "架构加载失败",

    # Section tabs
    "UI · 외관": "UI · 外观",
    "AI 기본값": "AI 默认值",
    "워크플로우 기본값": "工作流默认值",

    # Section descriptions
    "테마·언어·밀도·강조 색 등 외관 관련 설정. 즉시 적용됩니다.":
        "外观相关设置：主题、语言、密度、强调色。即时生效。",
    "AI 호출의 기본 파라미터. 워크플로우 노드와 챗봇이 이 값을 시작점으로 사용합니다.":
        "AI 调用的默认参数。工作流节点和聊天机器人将以此为起点。",
    "대시보드의 기본 동작·알림·폴링 주기.":
        "仪表板默认行为、通知和轮询间隔。",
    "워크플로우 에디터의 기본값. 새 노드 생성 시 이 값으로 prefill 됩니다.":
        "工作流编辑器默认值。创建新节点时将以此预填充。",

    # UI rows
    "auto/dark/light/midnight/forest/sunset": "auto/dark/light/midnight/forest/sunset",
    "ko/en/zh — 변경 시 페이지 새로고침": "ko/en/zh — 切换时刷新页面",
    "밀도": "密度",
    "카드/창의 안쪽 여백": "卡片/窗口的内部留白",
    "글자 크기": "字体大小",
    "본문 기본 폰트 크기": "正文默认字体大小",
    "모션 감소": "减少动效",
    "애니메이션·전환을 거의 0으로": "动画与过渡接近零",
    "강조 색": "强调色",
    "액티브 상태·버튼 강조 색": "激活状态与按钮高亮色",
    "사이드바 접힘": "侧栏折叠",
    "데스크톱에서 사이드바 기본 접힘": "桌面端默认折叠侧栏",
    "마스코트 표시": "显示吉祥物",
    "우하단 점프 캐릭터": "右下角跳跃角色",
    "컴팩트 사이드바": "紧凑侧栏",
    "카테고리 라벨 숨김": "隐藏分类标签",

    # AI rows
    "기본 프로바이더": "默认提供商",
    "예: claude:sonnet, openai:gpt-4.1, ollama:llama3.1":
        "例：claude:sonnet, openai:gpt-4.1, ollama:llama3.1",
    "Effort": "Effort",
    "low / medium / high — 추론 깊이": "low / medium / high — 推理深度",
    "Temperature": "Temperature",
    "0.0 결정적 ↔ 2.0 다양": "0.0 确定 ↔ 2.0 多样",
    "Top-p": "Top-p",
    "핵 샘플링 누적 확률": "核采样累积概率",
    "Max output tokens": "最大输出 tokens",
    "응답 최대 토큰": "响应最大 tokens",
    "Thinking budget": "思考预算",
    "확장 사고 예산 (0 = 비활성)": "扩展思考预算（0 = 禁用）",
    "Extended thinking": "扩展思考",
    "Claude 확장 사고 모드": "Claude 扩展思考模式",
    "스트리밍 응답": "流式响应",
    "SSE 토큰 스트리밍": "SSE token 流式传输",
    "폴백 체인 사용": "使用回退链",
    "실패 시 다음 프로바이더로 자동 폴백":
        "失败时自动切换到下一个提供商",

    # Behavior rows
    "한도 도달 시 자동 재개 워커": "达到限额时自动恢复的 worker",
    "Slack 알림": "Slack 通知",
    "워크플로우 완료/실패 알림": "工作流完成/失败通知",
    "Discord 알림": "Discord 通知",
    "텔레메트리 갱신(초)": "遥测刷新（秒）",
    "0 = 비활성": "0 = 禁用",
    "세션 spawn 전 확인": "启动会话前确认",
    "CLI 세션 시작 직전 모달": "启动 CLI 会话前显示模态",
    "워크플로우 자동 저장": "工作流自动保存",
    "편집 시 디바운스 저장": "编辑时去抖保存",
    "라이브 티커(초)": "实时滴答（秒）",
    "실시간 상태 폴링 주기": "实时状态轮询周期",
    "완료 알림 소리": "完成提示音",
    "워크플로우 종료 시 비프": "工作流结束时蜂鸣",
    "마지막 탭 자동 열기": "自动打开上次的标签",
    "재방문 시 직전 탭 복원": "重新访问时恢复上次的标签",

    # Workflow rows
    "기본 반복 횟수": "默认迭代次数",
    "Repeat 노드 기본값": "Repeat 节点默认值",
    "반복 간격(초)": "迭代间隔（秒）",
    "반복 간 대기": "迭代之间的等待",
    "Dry-run 기본": "默认 Dry-run",
    "실행 시 dry-run 토글 기본 ON": "运行时 dry-run 切换默认开启",
    "미니맵 표시": "显示小地图",
    "캔버스 우하단 미니맵": "画布右下角小地图",
    "그리드 스냅": "对齐到网格",
    "노드 이동 시 격자 정렬": "拖动节点时对齐网格",
    "그리드 크기(px)": "网格大小（px）",
    "8~64": "8 到 64",
}
