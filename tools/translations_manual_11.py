"""v2.36.0 — Run Center, Workflow Quick Actions, Commands tab Run buttons.

Adds EN + ZH translations for the new t('…') call sites. Imported by
translations_manual.py.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # ── Run Center tab ──────────────────────────────────────────
    "런 센터": "Run Center",
    "ECC 181 스킬 + 79 슬래시 명령 + OMC 4 모드 + OMX 명령을 한 화면에서 검색·1클릭 실행. 결과는 자동 저장되며 워크플로우로도 변환 가능.":
        "Search and one-click run ECC's 181 skills + 79 slash commands + 4 OMC modes + OMX commands from a single screen. Results are saved automatically and can be converted to a workflow.",
    "ECC 스킬 181개 + 슬래시 명령 79개 + OMC 4모드 + OMX 명령을 검색·1클릭 실행":
        "Search and one-click run ECC's 181 skills + 79 slash commands + 4 OMC modes + OMX commands.",
    "소스": "Source",
    "종류": "Kind",
    "카테고리": "Category",
    "전체": "All",
    "스킬": "Skill",
    "슬래시 명령": "Slash command",
    "모드": "Mode",
    "진단": "Diagnostic",
    "지식": "Knowledge",
    "이름 · 설명 · 카테고리 검색…": "Search name · description · category…",
    "즐겨찾기": "Favorites",
    "즐겨찾기만": "Favorites only",
    "일치하는 항목 없음. 검색어 또는 필터를 조정하세요.":
        "No matching items. Adjust the search query or filters.",
    "실행 히스토리 보기": "View run history",
    "설치됨": "installed",
    "미설치": "not installed",
    "설치하기": "Install",
    "즐겨찾기 토글 실패": "Failed to toggle favorite",
    "목표 (이 스킬/명령에 전달할 입력)": "Goal (input passed to this skill/command)",
    "예: 현재 디렉터리의 보안 취약점을 찾아 우선순위로 정리":
        "e.g. Find security vulnerabilities in the current directory and prioritise them",
    "모델": "Model",
    "타임아웃 (초)": "Timeout (seconds)",
    "일회성 실행입니다. 다단계 흐름이 필요하면": "One-shot execution. For multi-stage flows",
    "워크플로우로 변환": "Convert to workflow",
    "결과": "Result",
    "닫기": "Close",
    "실행": "Run",
    "목표를 입력하세요": "Enter a goal",
    "실행 중…": "Running…",
    "(빈 응답)": "(empty response)",
    "결과 복사": "Copy result",
    "프롬프트로 저장": "Save as prompt",
    "실행 성공": "Run succeeded",
    "실행 실패: ": "Run failed: ",
    "실행 오류": "Run error",
    "복사됨": "Copied",
    "복사 실패": "Copy failed",
    "프롬프트 라이브러리에 저장됨": "Saved to Prompt Library",
    "저장 실패": "Save failed",
    "저장 오류": "Save error",
    "변환 실패: ": "Conversion failed: ",
    "빌트인 템플릿: ": "Built-in template: ",
    "템플릿에서 직접 사용하세요": "use directly from the template",
    "워크플로우 생성 완료 — 워크플로우 탭으로 이동": "Workflow created — opening Workflows tab",
    "워크플로우 저장 실패": "Workflow save failed",

    # ── Workflow Quick Actions ──────────────────────────────────
    "빠른 실행 (OMC 모드)": "Quick run (OMC modes)",
    "요구사항 → 계획 → 실행 → 검증 단일 흐름": "Requirements → plan → execute → verify in one flow",
    "verify → fix 루프 (최대 5회)": "verify → fix loop (max 5)",
    "5 병렬 에이전트 → 합류": "5 parallel agents → merge",
    "소크라테스식 명확화 → 설계 문서": "Socratic clarification → design doc",
    "클릭 → 목표 입력 → 즉시 실행": "Click → enter goal → run immediately",
    "요구사항을 받아 계획 → 실행 → 검증을 단일 흐름으로 끝까지 자율 실행":
        "Run autonomously from requirements through plan → execute → verify in one flow.",
    "verify 통과까지 fix 루프를 자동 반복 (최대 5회)":
        "Auto-repeat the fix loop until verify passes (max 5 cycles).",
    "5명의 병렬 에이전트(Sonnet×2 + Haiku×3)가 동시 작업 후 결과 합류":
        "Five parallel agents (Sonnet×2 + Haiku×3) work concurrently and merge results.",
    "요구사항을 소크라테스식 질문으로 명확히한 후 설계 문서 산출":
        "Clarify requirements via Socratic questioning, then produce a design doc.",
    "목표를 한 줄로 입력하세요 (예: 다음주까지 신제품 출시 가이드 작성)":
        "Enter the goal in one line (e.g. Write a launch guide by next week)",
    "워크플로우 생성 + 실행": "Create workflow + run",
    "빌트인 템플릿을 찾을 수 없습니다: ": "Built-in template not found: ",
    "템플릿 조회 실패: ": "Template lookup failed: ",
    "템플릿 본문 비어있음 — 빌트인 등록 확인 필요":
        "Template body is empty — built-in registration must be checked",
    "워크플로우 생성됨 — 실행 시작": "Workflow created — starting run",

    # ── Commands tab Run button ─────────────────────────────────
    "대시보드에서 바로 실행": "Run directly from the dashboard",
    "이 명령은 ECC가 아니라 즉시 실행 대신 워크플로우로 변환됩니다":
        "This command is not from ECC — it will be converted to a workflow instead of running directly",
    "로컬 슬래시 명령 — 대시보드에서 1회성 실행":
        "Local slash command — one-shot execution from the dashboard",
    "You are dispatching the local slash command":
        "You are dispatching the local slash command",
    "Treat the user goal as the argument to the command.":
        "Treat the user goal as the argument to the command.",
    "Run the slash command": "Run the slash command",
    "카탈로그 로드 실패": "Catalog load failed",

    # ── v2.36.1 — Run Center info banner + diagnostics ──────────
    "ECC / OMC / OMX 의 출처와 설치": "Where ECC / OMC / OMX come from",
    "가이드 & 툴 탭에서 원클릭 설치. 181 스킬 + 79 슬래시 명령은 ~/.claude/plugins/ 의 ECC plugin을 직접 스캔.":
        "One-click install from the Guide & Tools tab. The 181 skills + 79 slash commands are scanned directly from the ECC plugin under ~/.claude/plugins/.",
    "별도 설치 불필요. 4 모드(autopilot/ralph/ultrawork/deep-interview)는 v2.25 부터 LazyClaude 빌트인 워크플로우 템플릿으로 흡수됨.":
        "No separate install needed. Since v2.25 the four modes (autopilot/ralph/ultrawork/deep-interview) ship as built-in LazyClaude workflow templates.",
    "별도 설치 불필요. 4 명령(doctor/wiki/hud/tasks)은 정적 매핑으로 임의 프로바이더에 dispatch.":
        "No separate install needed. The four commands (doctor/wiki/hud/tasks) are statically mapped and dispatched to any provider.",
    "진짜 OMC/OMX CLI를 Claude Code 세션에서 슬래시 명령으로 쓰고 싶다면 가이드 & 툴 탭의 카드를 참고하세요.":
        "If you want to invoke the real OMC/OMX CLIs as slash commands inside a Claude Code session, see the cards in the Guide & Tools tab.",
    "카탈로그 새로고침": "Refresh catalog",
    "카탈로그 새로고침 중…": "Refreshing catalog…",
    "카탈로그 갱신됨": "Catalog refreshed",
    "items": "items",
    "명령": "commands",
    "경로는 발견됐지만 항목 0개": "Path found but 0 items parsed",
    "진단 보기": "Show diagnostics",
    "스캔된 경로": "Scanned paths",

    # ── v2.36.2 — version-mismatch refresh banner ──────────────
    "새 버전 설치됨": "New version installed",
    "서버가 재시작되었습니다 — 새 코드 적용 가능성": "Server restarted — new code may be live",
    "지금 새로고침": "Reload now",
    "나중에": "Later",
}

NEW_ZH: dict[str, str] = {
    # ── Run Center tab ──────────────────────────────────────────
    "런 센터": "运行中心",
    "ECC 181 스킬 + 79 슬래시 명령 + OMC 4 모드 + OMX 명령을 한 화면에서 검색·1클릭 실행. 결과는 자동 저장되며 워크플로우로도 변환 가능.":
        "在一个屏幕上搜索并一键运行 ECC 的 181 个技能 + 79 个斜杠命令 + 4 个 OMC 模式 + OMX 命令。结果自动保存，可转换为工作流。",
    "ECC 스킬 181개 + 슬래시 명령 79개 + OMC 4모드 + OMX 명령을 검색·1클릭 실행":
        "搜索并一键运行 ECC 的 181 个技能 + 79 个斜杠命令 + 4 个 OMC 模式 + OMX 命令。",
    "소스": "来源",
    "종류": "类型",
    "카테고리": "分类",
    "전체": "全部",
    "스킬": "技能",
    "슬래시 명령": "斜杠命令",
    "모드": "模式",
    "진단": "诊断",
    "지식": "知识",
    "이름 · 설명 · 카테고리 검색…": "搜索名称 · 描述 · 分类…",
    "즐겨찾기": "收藏",
    "즐겨찾기만": "仅收藏",
    "일치하는 항목 없음. 검색어 또는 필터를 조정하세요.":
        "无匹配项。请调整搜索词或筛选条件。",
    "실행 히스토리 보기": "查看运行历史",
    "설치됨": "已安装",
    "미설치": "未安装",
    "설치하기": "安装",
    "즐겨찾기 토글 실패": "切换收藏失败",
    "목표 (이 스킬/명령에 전달할 입력)": "目标 (传给该技能/命令的输入)",
    "예: 현재 디렉터리의 보안 취약점을 찾아 우선순위로 정리":
        "例如: 找出当前目录的安全漏洞并按优先级整理",
    "모델": "模型",
    "타임아웃 (초)": "超时 (秒)",
    "일회성 실행입니다. 다단계 흐름이 필요하면": "一次性运行。如需多阶段流程",
    "워크플로우로 변환": "转换为工作流",
    "결과": "结果",
    "닫기": "关闭",
    "실행": "运行",
    "목표를 입력하세요": "请输入目标",
    "실행 중…": "运行中…",
    "(빈 응답)": "(空响应)",
    "결과 복사": "复制结果",
    "프롬프트로 저장": "保存为提示",
    "실행 성공": "运行成功",
    "실행 실패: ": "运行失败: ",
    "실행 오류": "运行错误",
    "복사됨": "已复制",
    "복사 실패": "复制失败",
    "프롬프트 라이브러리에 저장됨": "已保存到提示库",
    "저장 실패": "保存失败",
    "저장 오류": "保存错误",
    "변환 실패: ": "转换失败: ",
    "빌트인 템플릿: ": "内置模板: ",
    "템플릿에서 직접 사용하세요": "请直接从模板使用",
    "워크플로우 생성 완료 — 워크플로우 탭으로 이동": "工作流已创建 — 跳转到工作流标签",
    "워크플로우 저장 실패": "工作流保存失败",

    # ── Workflow Quick Actions ──────────────────────────────────
    "빠른 실행 (OMC 모드)": "快速运行 (OMC 模式)",
    "요구사항 → 계획 → 실행 → 검증 단일 흐름": "需求 → 计划 → 执行 → 验证 单一流程",
    "verify → fix 루프 (최대 5회)": "verify → fix 循环 (最多 5 次)",
    "5 병렬 에이전트 → 합류": "5 个并行代理 → 合流",
    "소크라테스식 명확화 → 설계 문서": "苏格拉底式澄清 → 设计文档",
    "클릭 → 목표 입력 → 즉시 실행": "点击 → 输入目标 → 立即运行",
    "요구사항을 받아 계획 → 실행 → 검증을 단일 흐름으로 끝까지 자율 실행":
        "从需求开始，按计划 → 执行 → 验证 的单一流程自主运行到底。",
    "verify 통과까지 fix 루프를 자동 반복 (최대 5회)":
        "自动重复 fix 循环直到 verify 通过 (最多 5 次)。",
    "5명의 병렬 에이전트(Sonnet×2 + Haiku×3)가 동시 작업 후 결과 합류":
        "5 个并行代理 (Sonnet×2 + Haiku×3) 同时工作并合并结果。",
    "요구사항을 소크라테스식 질문으로 명확히한 후 설계 문서 산출":
        "通过苏格拉底式提问澄清需求后产出设计文档。",
    "목표를 한 줄로 입력하세요 (예: 다음주까지 신제품 출시 가이드 작성)":
        "请用一句话输入目标 (例如: 下周前完成新品发布指南)",
    "워크플로우 생성 + 실행": "创建工作流 + 运行",
    "빌트인 템플릿을 찾을 수 없습니다: ": "找不到内置模板: ",
    "템플릿 조회 실패: ": "模板查询失败: ",
    "템플릿 본문 비어있음 — 빌트인 등록 확인 필요":
        "模板正文为空 — 需要检查内置注册",
    "워크플로우 생성됨 — 실행 시작": "工作流已创建 — 开始运行",

    # ── Commands tab Run button ─────────────────────────────────
    "대시보드에서 바로 실행": "直接从仪表板运行",
    "이 명령은 ECC가 아니라 즉시 실행 대신 워크플로우로 변환됩니다":
        "此命令非 ECC — 将被转换为工作流而非立即运行",
    "로컬 슬래시 명령 — 대시보드에서 1회성 실행":
        "本地斜杠命令 — 从仪表板一次性执行",
    "You are dispatching the local slash command":
        "您正在分派本地斜杠命令",
    "Treat the user goal as the argument to the command.":
        "将用户目标作为该命令的参数处理。",
    "Run the slash command": "运行斜杠命令",
    "카탈로그 로드 실패": "目录加载失败",

    # ── v2.36.1 — Run Center info banner + diagnostics ──────────
    "ECC / OMC / OMX 의 출처와 설치": "ECC / OMC / OMX 的来源与安装",
    "가이드 & 툴 탭에서 원클릭 설치. 181 스킬 + 79 슬래시 명령은 ~/.claude/plugins/ 의 ECC plugin을 직접 스캔.":
        "在「指南与工具」标签一键安装。181 技能 + 79 斜杠命令直接从 ~/.claude/plugins/ 的 ECC plugin 扫描。",
    "별도 설치 불필요. 4 모드(autopilot/ralph/ultrawork/deep-interview)는 v2.25 부터 LazyClaude 빌트인 워크플로우 템플릿으로 흡수됨.":
        "无需另行安装。自 v2.25 起，4 个模式 (autopilot/ralph/ultrawork/deep-interview) 已作为 LazyClaude 内置工作流模板提供。",
    "별도 설치 불필요. 4 명령(doctor/wiki/hud/tasks)은 정적 매핑으로 임의 프로바이더에 dispatch.":
        "无需另行安装。4 个命令 (doctor/wiki/hud/tasks) 通过静态映射分派到任意 provider。",
    "진짜 OMC/OMX CLI를 Claude Code 세션에서 슬래시 명령으로 쓰고 싶다면 가이드 & 툴 탭의 카드를 참고하세요.":
        "如需在 Claude Code 会话中以斜杠命令调用真正的 OMC/OMX CLI，请参见「指南与工具」标签的卡片。",
    "카탈로그 새로고침": "刷新目录",
    "카탈로그 새로고침 중…": "正在刷新目录…",
    "카탈로그 갱신됨": "目录已更新",
    "items": "项",
    "명령": "命令",
    "경로는 발견됐지만 항목 0개": "路径已找到但解析到 0 项",
    "진단 보기": "查看诊断",
    "스캔된 경로": "已扫描路径",

    # ── v2.36.2 — version-mismatch refresh banner ──────────────
    "새 버전 설치됨": "已安装新版本",
    "서버가 재시작되었습니다 — 새 코드 적용 가능성": "服务器已重启 — 可能有新代码生效",
    "지금 새로고침": "立即刷新",
    "나중에": "稍后",
}
