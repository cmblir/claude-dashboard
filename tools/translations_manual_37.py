"""v2.57.0 — Ralph UI tab + Project Ralph card + workflow node inspector.

Korean -> English / Chinese for the new UI strings introduced by cycle 5.
Loaded by ``tools/translations_manual.py``.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # Ralph tab
    "실행 목록":                   "Runs",
    "새 실행 시작":                "Start a new run",
    "Completion 표식":             "Completion marker",
    "예산 USD":                    "Budget USD",
    "아직 Ralph 실행 기록 없음":   "No Ralph runs yet",
    "라이브":                      "Live",
    "연결 중":                     "Connecting",
    "이 Ralph 루프를 중단할까요?": "Cancel this Ralph loop?",
    "취소 요청 전송됨":            "Cancel request sent",
    "프롬프트가 비어 있음":        "Prompt is empty",
    "시작됨":                      "Started",
    # Project card + recommend modal
    "Ralph 추천 PROMPT.md 생성":   "Generate Ralph PROMPT.md draft",
    "Ralph 프롬프트 생성 중…":     "Generating Ralph prompt…",
    "Ralph 추천":                  "Ralph recommendation",
    "LLM 다듬기":                  "Polish with LLM",
    "Ralph 시작":                  "Start Ralph",
    # Workflow node inspector
    "PROMPT (반복 입력)":          "PROMPT (repeated each iteration)",
    "매 iteration에 동일하게 주입될 PROMPT.md 본문. 비워두면 입력 노드의 출력이 사용됩니다.":
        "Body of PROMPT.md fed identically every iteration. Leave blank to "
        "use the upstream node's output.",
    "Completion 표식 (정확 일치)":
        "Completion marker (exact match)",
    "시스템 프롬프트 (선택)":      "System prompt (optional)",
    "이 노드는 Ralph 루프가 종료될 때까지 블로킹됩니다. 안전장치 4종(max-iter / completion / 예산 / cancel) 모두 강제 적용.":
        "This node blocks until the Ralph loop terminates. All four safety "
        "guards (max-iter, completion-promise, budget, cancel) are enforced.",
    ' 비워두면 기본값 사용: \\"이전 사이클 보고를 검토하고 미해결 항목을 우선 처리…\\"':
        ' Defaults to "Review the previous cycle and tackle outstanding "'
        '"items first…" if left blank',
    "비워두면 기본값 사용: \\\"이전 사이클 보고를 검토하고 미해결 항목을 우선 처리…\\\"":
        'Defaults to "Review the previous cycle and tackle outstanding items first…" if left blank',
    # v2.59.0 — header mode selector
    "대시보드 모드 — 사이드바 탭 필터": "Dashboard mode — sidebar tab filter",
    "대시보드 모드 선택":               "Select dashboard mode",
    # v2.59.0 — Auto-Resume add-binding modal
    "새 Auto-Resume 바인딩":            "New Auto-Resume binding",
    "새 바인딩 추가":                   "Add binding",
    "대상 Claude 세션을 골라서 Auto-Resume 워커를 붙입니다. 토큰/레이트 한도 발생 시 자동으로 claude --resume 으로 재시도합니다.":
        "Pick a target Claude session to attach an Auto-Resume worker. "
        "On token/rate-limit failure the worker auto-retries via `claude --resume`.",
    "실행 중인 세션 선택":              "Pick a running session",
    "직접 입력":                        "Enter manually",
    "실행 중인 Claude CLI 세션이 감지되지 않습니다. session UUID 와 cwd 를 직접 입력하세요.":
        "No running Claude CLI session detected. Enter the session UUID and "
        "cwd manually.",
    "Session UUID":                     "Session UUID",
    "재시도 시 추가 프롬프트 (선택)":   "Retry prompt (optional)",
    "예: 이전 작업을 이어서 진행해주세요.":
        "e.g. Continue the previous task.",
    "폴링 (s)":                         "Poll (s)",
    "idle (s)":                         "idle (s)",
    "최대 시도":                        "Max attempts",
    "--continue 사용 (--resume 대신)":   "Use --continue (instead of --resume)",
    "실행 중이지 않은 세션도 허용 (terminal closed)":
        "Allow sessions that are not currently running (terminal closed)",
    "바인딩 추가":                      "Add binding",
    "Session UUID 가 비어있음":          "Session UUID is empty",
    "바인딩 추가됨":                    "Binding added",
    "실패":                             "Failed",
    # v2.61.0 — mode usage stats + IPC panel
    "이 모드에서 가장 많이 사용한 탭": "Top tab in this mode",
    "IPC 스트림":                       "IPC streams",
    "inbound (사용자 → 오케) / outbound (오케 → 채널) 분리 로그":
        "inbound (user → orchestrator) / outbound (orchestrator → channel) split log",
    "채널 필터 (선택)":                 "Channel filter (optional)",
    "inbound 없음":                     "No inbound",
    "outbound 없음":                    "No outbound",
}

NEW_ZH: dict[str, str] = {
    "실행 목록":                   "执行列表",
    "새 실행 시작":                "新建执行",
    "Completion 표식":             "完成标识",
    "예산 USD":                    "预算 USD",
    "아직 Ralph 실행 기록 없음":   "尚无 Ralph 执行记录",
    "라이브":                      "实时",
    "연결 중":                     "连接中",
    "이 Ralph 루프를 중단할까요?": "确认中止该 Ralph 循环?",
    "취소 요청 전송됨":            "已发送取消请求",
    "프롬프트가 비어 있음":        "Prompt 为空",
    "시작됨":                      "已启动",
    "Ralph 추천 PROMPT.md 생성":   "生成 Ralph PROMPT.md 草稿",
    "Ralph 프롬프트 생성 중…":     "正在生成 Ralph 提示…",
    "Ralph 추천":                  "Ralph 推荐",
    "LLM 다듬기":                  "LLM 润色",
    "Ralph 시작":                  "启动 Ralph",
    "PROMPT (반복 입력)":          "PROMPT(每次迭代重复输入)",
    "매 iteration에 동일하게 주입될 PROMPT.md 본문. 비워두면 입력 노드의 출력이 사용됩니다.":
        "每次迭代以相同内容注入的 PROMPT.md 正文。留空则使用上游节点输出。",
    "Completion 표식 (정확 일치)":
        "完成标识(精确匹配)",
    "시스템 프롬프트 (선택)":      "系统提示(可选)",
    "이 노드는 Ralph 루프가 종료될 때까지 블로킹됩니다. 안전장치 4종(max-iter / completion / 예산 / cancel) 모두 강제 적용.":
        "该节点阻塞直至 Ralph 循环结束。四重安全机制(max-iter / completion / 预算 / cancel)全部强制启用。",
    "비워두면 기본값 사용: \\\"이전 사이클 보고를 검토하고 미해결 항목을 우선 처리…\\\"":
        '留空则使用默认值:"审阅上一周期的报告并优先处理未完成项…"',
    "대시보드 모드 — 사이드바 탭 필터": "仪表盘模式 — 侧边栏标签过滤",
    "대시보드 모드 선택":               "选择仪表盘模式",
    "새 Auto-Resume 바인딩":            "新建 Auto-Resume 绑定",
    "새 바인딩 추가":                   "新增绑定",
    "대상 Claude 세션을 골라서 Auto-Resume 워커를 붙입니다. 토큰/레이트 한도 발생 시 자동으로 claude --resume 으로 재시도합니다.":
        "选择目标 Claude 会话以挂载 Auto-Resume 工作进程。当 token / rate limit 触发时,工作进程会自动通过 `claude --resume` 重试。",
    "실행 중인 세션 선택":              "选择运行中的会话",
    "직접 입력":                        "手动输入",
    "실행 중인 Claude CLI 세션이 감지되지 않습니다. session UUID 와 cwd 를 직접 입력하세요.":
        "未检测到运行中的 Claude CLI 会话。请手动输入 session UUID 和 cwd。",
    "Session UUID":                     "Session UUID",
    "재시도 시 추가 프롬프트 (선택)":   "重试时附加 Prompt(可选)",
    "예: 이전 작업을 이어서 진행해주세요.":
        "例如:继续之前的任务。",
    "폴링 (s)":                         "轮询 (s)",
    "idle (s)":                         "idle (s)",
    "최대 시도":                        "最大尝试",
    "--continue 사용 (--resume 대신)":   "使用 --continue(替代 --resume)",
    "실행 중이지 않은 세션도 허용 (terminal closed)":
        "允许未在运行的会话(terminal 已关闭)",
    "바인딩 추가":                      "新增绑定",
    "Session UUID 가 비어있음":          "Session UUID 为空",
    "바인딩 추가됨":                    "绑定已新增",
    "실패":                             "失败",
    "이 모드에서 가장 많이 사용한 탭": "本模式中使用最多的标签",
    "IPC 스트림":                       "IPC 流",
    "inbound (사용자 → 오케) / outbound (오케 → 채널) 분리 로그":
        "inbound(用户 → 编排) / outbound(编排 → 频道)分离日志",
    "채널 필터 (선택)":                 "频道过滤(可选)",
    "inbound 없음":                     "无 inbound",
    "outbound 없음":                    "无 outbound",
}
