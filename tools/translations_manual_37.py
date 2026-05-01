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
}
