"""v2.62.0 / v2.63.0 — J1 Ralph polish UI + K2 sweeper status panel + cycle-8/9 residue sweep.

Korean -> English / Chinese for strings left untranslated across H1-H5,
the new J1 (Ralph polish system prompt editor) UI, and the K2 orchestrator
sweeper-status panel.
Loaded by ``tools/translations_manual.py``.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # K2 — Orchestrator sweeper-status panel (v2.63.0)
    "스케줄러 상태":                            "Scheduler status",
    "schedule.everyMinutes 가 설정된 바인딩의 다음 실행 시각":
        "Next fire time for bindings with schedule.everyMinutes set",
    "예약된 바인딩 없음":                       "No scheduled bindings",
    "지금 실행 가능":                           "Due now",
    "주기":                                     "Interval",
    "다음 실행":                                "Next run",
    "예약됨":                                   "scheduled",
    "runId / assignee 검색":                    "Search runId / assignee",
    "이전에 입력한 값이 있으면 자동 채움":      "Auto-fills if previously entered",
    # J1 — Ralph polish system prompt editor
    "Polish 시스템 프롬프트":
        "Polish system prompt",
    "LLM polish 패스가 추천 PROMPT.md를 다듬을 때 사용하는 시스템 프롬프트. 비워두고 저장하면 기본값으로 복원.":
        "System prompt used by the LLM polish pass to refine the recommended PROMPT.md. Clear and save to restore the default.",
    "비어있는 프롬프트는 저장할 수 없음. 기본값 복원을 사용하세요.":
        "Empty prompt cannot be saved. Use Restore Default instead.",
    "Polish 시스템 프롬프트를 기본값으로 되돌릴까요?":
        "Reset polish system prompt to default?",
    "기본값으로 복원":   "Restore default",
    "기본값으로 복원됨": "Restored to default",
    "현재 로드":         "Load current",
    # I3 — mode usage stats (residue from v2.61)
    "모드별 사용량":     "Usage by mode",
    "전체 모드":         "All modes",
    "현재 모드 / 전체 모드 검색 전환":
        "Toggle current mode / all modes search",
    "현재: 전체 검색 (탭 클릭하여 현재 모드만 검색)":
        "Current: all search (click tab to search current mode only)",
    "현재: 현재 모드만 (탭 클릭하여 전체 검색)":
        "Current: current mode only (click tab to search all)",
    "지금 다듬기":       "Polish now",
    # H4 — docker_run node inspector (residue from v2.60)
    "Docker 이미지":                 "Docker image",
    "명령 (sh -c 로 실행)":          "Command (run via sh -c)",
    "볼륨 마운트 경로 (선택)":       "Volume mount path (optional)",
    "읽기 전용 마운트 (권장)":       "Read-only mount (recommended)",
    "네트워크":                      "Network",
    "타임아웃 (s)":                  "Timeout (s)",
    "메모리 (MB)":                   "Memory (MB)",
    "docker 미설치 시 호스트 실행 폴백 없이 명확한 에러를 반환합니다 (조용한 권한 상승 방지).":
        "Returns a clear error if docker is not installed rather than silently falling back to host (prevents privilege escalation).",
    "격리된 docker 컨테이너에서 셸 명령 실행. --rm + --network=none + read-only mount + memory cap 기본. docker 미설치 시 호스트 실행 폴백 없이 명확한 에러.":
        "Run shell commands in an isolated docker container. Defaults: --rm + --network=none + read-only mount + memory cap. Returns a clear error if docker is not installed.",
    # Nav / tab descriptions — residue from earlier cycles
    "Slack 어드민 · Obsidian 기록 · Auto-Resume · Ralph 루프 · Docker":
        "Slack admin · Obsidian log · Auto-Resume · Ralph loop · Docker",
    "Slack/Telegram 채널 멘션 → Claude 플래너 → 멀티 모델 병렬 분담 → 채널 회신. 에이전트 간 라이브 보고는 Agent Bus 탭/SSE 로 연결.":
        "Slack/Telegram channel mention → Claude planner → multi-model parallel split → channel reply. Live inter-agent reports via Agent Bus tab / SSE.",
    "Slack/Telegram/Discord 채널 멘션 → Claude 플래너 → 멀티 모델 병렬 분담 → 채널 회신. 채널별 fallback + 일일 예산 cap.":
        "Slack/Telegram/Discord channel mention → Claude planner → multi-model parallel split → channel reply. Per-channel fallback + daily budget cap.",
    "Geoffrey Huntley Ralph Wiggum 패턴 — 같은 PROMPT.md를 4중 안전장치 안에서 반복. 프로젝트 추천기 + 라이브 SSE + CLI.":
        "Geoffrey Huntley Ralph Wiggum pattern — repeat the same PROMPT.md inside 4 safety guards. Project recommender + live SSE + CLI.",
    "Same-prompt iteration (Ralph Wiggum) — max-iter / completion-promise / 예산 USD / cancel 4중 안전장치. 노드는 루프 종료까지 블로킹.":
        "Same-prompt iteration (Ralph Wiggum) — max-iter / completion-promise / USD budget / cancel — 4 safety guards. Node blocks until loop ends.",
    "Same-prompt 반복 — Geoffrey Huntley Ralph Wiggum 패턴. max-iter / completion-promise / 예산 USD / 수동 cancel 4중 안전장치.":
        "Same-prompt repeat — Geoffrey Huntley Ralph Wiggum pattern. max-iter / completion-promise / USD budget / manual cancel — 4 safety guards.",
    "Executor (Haiku) + Advisor (Opus) 페어링 · 토큰/비용/지연 델타 비교":
        "Executor (Haiku) + Advisor (Opus) pairing · token/cost/latency delta comparison",
    "computer-use-2025-01-24 beta · screenshot+mouse+key 시연 (plan-only, 안전)":
        "computer-use-2025-01-24 beta · screenshot+mouse+key demo (plan-only, safe)",
    "memory-2025-08-18 beta · 서버측 memory blocks · 기억/회상/삭제 라운드트립":
        "memory-2025-08-18 beta · server-side memory blocks · remember/recall/delete round-trip",
    "~/.claude/scheduled-tasks/ 목록 + Auto-Resume 활성 워커.":
        "~/.claude/scheduled-tasks/ list + active Auto-Resume workers.",
    "~/.claude/scheduled-tasks/*.yaml CRUD + 즉시 실행 — Claude Code Routines":
        "~/.claude/scheduled-tasks/*.yaml CRUD + immediate execution — Claude Code Routines",
    "Claude Code를 GLM/Z.AI/DeepSeek 등 다른 LLM으로 라우팅 + zclaude 별칭 안내":
        "Route Claude Code to other LLMs such as GLM/Z.AI/DeepSeek + zclaude alias guide",
    "대상 Claude 세션 UUID(또는 입력 문자열에서 추출)에 Auto-Resume 워커를 바인딩/해제":
        "Bind/unbind an Auto-Resume worker to a Claude session UUID (or extracted from the input string)",
    "워크플로우는 즉시 다음 노드로 진행되고, 워커는 백그라운드에서 토큰/레이트 한도 발생 시 claude --resume 으로 자동 재시도.":
        "The workflow advances immediately to the next node; the worker retries in the background via claude --resume when hitting token/rate limits.",
    "현재 적용 중인 모든 파라미터와 런타임 정보를 보여줍니다 (읽기 전용).":
        "Shows all currently active parameters and runtime info (read-only).",
    "여기에 적은 지침(기억·규칙·선호)은 모든 세션 시작 시 자동 로드됩니다. 직접 쓰거나, 위의":
        "Instructions here (memory · rules · preferences) auto-load at every session start. Write directly, or use the",
    "이 프로젝트에서 작업할 때만 로드되는 지침을 작성하세요. 저장하면 즉시":
        "Write instructions loaded only when working in this project. After saving,",
    "PreToolUse + Edit/Write/Bash 매처를 가진":
        "with PreToolUse + Edit/Write/Bash matchers",
    "OFF 상태에서도":    "Even when OFF",
    "버튼은 사용 가능합니다.": "button is available.",
    "대신 --continue 사용":    "Use --continue instead",
    "대신 영숫자 /":           "Use alphanumeric /",
    # I2 — docker_run result cache
    "캐시 적중":               "Cache hit",
    # Generic error / status strings
    "CLI 실행 실패":           "CLI execution failed",
    "Hyper Agent 로드 실패":   "Hyper Agent load failed",
    "Spawn 실패":              "Spawn failed",
    "롤백 실패":               "Rollback failed",
    "변환 실패":               "Conversion failed",
    "빌트인 템플릿을 찾을 수 없습니다": "Built-in template not found",
    "템플릿 조회 실패":        "Template lookup failed",
    "명령어 ID —":             "Command ID —",
    "사용":                    "used",
    # Path fragments
    "/ 하위경로는":            "/ sub-path",
    "/CLAUDE.md 로 기록됩니다.": "is recorded in /CLAUDE.md.",
}

NEW_ZH: dict[str, str] = {
    # K2 — Orchestrator sweeper-status panel (v2.63.0)
    "스케줄러 상태":                            "调度器状态",
    "schedule.everyMinutes 가 설정된 바인딩의 다음 실행 시각":
        "已设置 schedule.everyMinutes 的绑定的下次触发时间",
    "예약된 바인딩 없음":                       "无计划绑定",
    "지금 실행 가능":                           "立即可运行",
    "주기":                                     "间隔",
    "다음 실행":                                "下次运行",
    "예약됨":                                   "已计划",
    "runId / assignee 검색":                    "搜索 runId / assignee",
    "이전에 입력한 값이 있으면 자동 채움":      "若有之前输入的值则自动填充",
    # J1 — Ralph polish system prompt editor
    "Polish 시스템 프롬프트":
        "Polish 系统提示词",
    "LLM polish 패스가 추천 PROMPT.md를 다듬을 때 사용하는 시스템 프롬프트. 비워두고 저장하면 기본값으로 복원.":
        "LLM polish 阶段用于润色推荐 PROMPT.md 的系统提示词。留空并保存可恢复默认值。",
    "비어있는 프롬프트는 저장할 수 없음. 기본값 복원을 사용하세요.":
        '不能保存空提示词，请使用"恢复默认"。',
    "Polish 시스템 프롬프트를 기본값으로 되돌릴까요?":
        "将 Polish 系统提示词恢复为默认值？",
    "기본값으로 복원":   "恢复默认",
    "기본값으로 복원됨": "已恢复默认",
    "현재 로드":         "加载当前",
    # I3 — mode usage stats
    "모드별 사용량":     "按模式用量",
    "전체 모드":         "所有模式",
    "현재 모드 / 전체 모드 검색 전환":
        "切换当前模式 / 全局搜索",
    "현재: 전체 검색 (탭 클릭하여 현재 모드만 검색)":
        "当前：全局搜索（点击标签以仅搜索当前模式）",
    "현재: 현재 모드만 (탭 클릭하여 전체 검색)":
        "当前：仅当前模式（点击标签以全局搜索）",
    "지금 다듬기":       "立即 Polish",
    # H4 — docker_run node
    "Docker 이미지":                 "Docker 镜像",
    "명령 (sh -c 로 실행)":          "命令（通过 sh -c 执行）",
    "볼륨 마운트 경로 (선택)":       "卷挂载路径（可选）",
    "읽기 전용 마운트 (권장)":       "只读挂载（推荐）",
    "네트워크":                      "网络",
    "타임아웃 (s)":                  "超时（秒）",
    "메모리 (MB)":                   "内存（MB）",
    "docker 미설치 시 호스트 실행 폴백 없이 명확한 에러를 반환합니다 (조용한 권한 상승 방지).":
        "若未安装 docker，返回明确错误而非静默回退到宿主机执行（防止权限提升）。",
    "격리된 docker 컨테이너에서 셸 명령 실행. --rm + --network=none + read-only mount + memory cap 기본. docker 미설치 시 호스트 실행 폴백 없이 명확한 에러.":
        "在隔离 docker 容器中运行 shell 命令。默认：--rm + --network=none + 只读挂载 + 内存上限。未安装 docker 时返回明确错误。",
    # Nav / tab descriptions
    "Slack 어드민 · Obsidian 기록 · Auto-Resume · Ralph 루프 · Docker":
        "Slack 管理 · Obsidian 日志 · Auto-Resume · Ralph 循环 · Docker",
    "Slack/Telegram 채널 멘션 → Claude 플래너 → 멀티 모델 병렬 분담 → 채널 회신. 에이전트 간 라이브 보고는 Agent Bus 탭/SSE 로 연결.":
        "Slack/Telegram 频道提及 → Claude 规划器 → 多模型并行分工 → 频道回复。跨 Agent 实时报告通过 Agent Bus 标签/SSE 连接。",
    "Slack/Telegram/Discord 채널 멘션 → Claude 플래너 → 멀티 모델 병렬 분담 → 채널 회신. 채널별 fallback + 일일 예산 cap.":
        "Slack/Telegram/Discord 频道提及 → Claude 规划器 → 多模型并行分工 → 频道回复。按频道 fallback + 每日预算上限。",
    "Geoffrey Huntley Ralph Wiggum 패턴 — 같은 PROMPT.md를 4중 안전장치 안에서 반복. 프로젝트 추천기 + 라이브 SSE + CLI.":
        "Geoffrey Huntley Ralph Wiggum 模式 — 在四重安全守卫下重复同一 PROMPT.md。项目推荐器 + 实时 SSE + CLI。",
    "Same-prompt iteration (Ralph Wiggum) — max-iter / completion-promise / 예산 USD / cancel 4중 안전장치. 노드는 루프 종료까지 블로킹.":
        "Same-prompt 迭代（Ralph Wiggum）— max-iter / completion-promise / USD 预算 / cancel — 四重安全守卫。节点阻塞直至循环结束。",
    "Same-prompt 반복 — Geoffrey Huntley Ralph Wiggum 패턴. max-iter / completion-promise / 예산 USD / 수동 cancel 4중 안전장치.":
        "Same-prompt 重复 — Geoffrey Huntley Ralph Wiggum 模式。max-iter / completion-promise / USD 预算 / 手动 cancel — 四重安全守卫。",
    "Executor (Haiku) + Advisor (Opus) 페어링 · 토큰/비용/지연 델타 비교":
        "Executor（Haiku）+ Advisor（Opus）配对 · 令牌/成本/延迟 delta 对比",
    "computer-use-2025-01-24 beta · screenshot+mouse+key 시연 (plan-only, 안전)":
        "computer-use-2025-01-24 beta · screenshot+mouse+key 演示（仅规划，安全）",
    "memory-2025-08-18 beta · 서버측 memory blocks · 기억/회상/삭제 라운드트립":
        "memory-2025-08-18 beta · 服务端 memory blocks · 记忆/回想/删除往返",
    "~/.claude/scheduled-tasks/ 목록 + Auto-Resume 활성 워커.":
        "~/.claude/scheduled-tasks/ 列表 + 活跃 Auto-Resume 工作器。",
    "~/.claude/scheduled-tasks/*.yaml CRUD + 즉시 실행 — Claude Code Routines":
        "~/.claude/scheduled-tasks/*.yaml CRUD + 立即执行 — Claude Code Routines",
    "Claude Code를 GLM/Z.AI/DeepSeek 등 다른 LLM으로 라우팅 + zclaude 별칭 안내":
        "将 Claude Code 路由到 GLM/Z.AI/DeepSeek 等其他 LLM + zclaude 别名指南",
    "대상 Claude 세션 UUID(또는 입력 문자열에서 추출)에 Auto-Resume 워커를 바인딩/해제":
        "绑定/解绑 Auto-Resume 工作器到目标 Claude 会话 UUID（或从输入字符串提取）",
    "워크플로우는 즉시 다음 노드로 진행되고, 워커는 백그라운드에서 토큰/레이트 한도 발생 시 claude --resume 으로 자동 재시도.":
        "工作流立即推进到下一节点；工作器在后台遇到令牌/速率限制时通过 claude --resume 自动重试。",
    "현재 적용 중인 모든 파라미터와 런타임 정보를 보여줍니다 (읽기 전용).":
        "显示当前所有活跃参数及运行时信息（只读）。",
    "여기에 적은 지침(기억·규칙·선호)은 모든 세션 시작 시 자동 로드됩니다. 직접 쓰거나, 위의":
        "此处的指令（记忆·规则·偏好）将在每次会话开始时自动加载。可直接编写，或使用上方的",
    "이 프로젝트에서 작업할 때만 로드되는 지침을 작성하세요. 저장하면 즉시":
        "编写仅在此项目中工作时加载的指令。保存后",
    "PreToolUse + Edit/Write/Bash 매처를 가진":
        "具有 PreToolUse + Edit/Write/Bash 匹配器的",
    "OFF 상태에서도":    "即使在 OFF 状态下",
    "버튼은 사용 가능합니다.": "按钮仍可用。",
    "대신 --continue 사용":    "改用 --continue",
    "대신 영숫자 /":           "改用字母数字 /",
    # I2 — docker_run result cache
    "캐시 적중":               "缓存命中",
    # Generic error / status strings
    "CLI 실행 실패":           "CLI 执行失败",
    "Hyper Agent 로드 실패":   "Hyper Agent 加载失败",
    "Spawn 실패":              "Spawn 失败",
    "롤백 실패":               "回滚失败",
    "변환 실패":               "转换失败",
    "빌트인 템플릿을 찾을 수 없습니다": "找不到内置模板",
    "템플릿 조회 실패":        "模板查询失败",
    "명령어 ID —":             "命令 ID —",
    "사용":                    "已用",
    # Path fragments
    "/ 하위경로는":            "/ 子路径",
    "/CLAUDE.md 로 기록됩니다.": "记录到 /CLAUDE.md。",
}
