"""v2.42.0 — Computer Use / Memory / Advisor labs + Claude Code Routines.

KO → EN/ZH for the 4 new playground/feature tabs introduced in v2.42.0.
Imported by translations_manual.py.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # Computer Use Lab
    "Computer Use Lab": "Computer Use Lab",
    "Anthropic computer-use-2025-01-24 beta · plan-only (실행하지 않음)":
        "Anthropic computer-use-2025-01-24 beta · plan-only (no execution)",
    "대시보드는 모델의 tool plan만 표시 — 실제 마우스/키보드 제어는 하지 않습니다.":
        "Dashboard surfaces the model's tool plan only — never executes mouse/keyboard.",
    "예: Open Finder and click Documents…": "e.g. Open Finder and click Documents…",
    "스크린샷 경로 (~/.claude 하위, 선택)": "Screenshot path (under ~/, optional)",
    "실행":           "Run",
    "최근 호출":      "Recent calls",
    "툴 호출":        "tool calls",
    "Tool Plan":      "Tool Plan",
    "텍스트 응답":    "Text response",
    "툴 호출 없음 — 모델이 텍스트로만 응답":
        "No tool calls — the model replied with text only",
    "실행 중…":       "Running…",

    # Memory Lab
    "Memory Lab":     "Memory Lab",
    "Anthropic memory-2025-08-18 beta · 서버측 memory blocks 라운드트립":
        "Anthropic memory-2025-08-18 beta · server-side memory-block round-trip",
    "예: 내 이름은 Alex 이고 간결한 답변 선호. 기억해줘.":
        "e.g. My name is Alex and I prefer concise replies. Remember this.",
    "관찰된 메모리 블록": "Observed memory blocks",
    "이벤트":         "events",
    "메모리 이벤트":  "Memory events",
    "응답":           "Response",
    "메모리 이벤트 없음 — 모델이 메모리를 사용하지 않음":
        "No memory events — the model did not use the memory tool",

    # Advisor Lab
    "Advisor Lab":    "Advisor Lab",
    "Executor (저비용/빠름) + Advisor (고지능/느림) 페어링 — 비용/품질 델타 시각화":
        "Pair Executor (cheap/fast) with Advisor (smart/slow) — visualise the cost/quality delta",
    "동일 프롬프트가 두 모델에 보내지고 결과가 비교됩니다.":
        "The same prompt goes to both models and the results are compared.",
    "Executor":       "Executor",
    "Advisor":        "Advisor",
    "실행 중 (executor → advisor)…": "Running (executor → advisor)…",
    "델타":           "Delta",
    "토큰":           "tokens",
    "비용":           "cost",
    "지연":           "latency",

    # Routines
    "Claude Code Routines": "Claude Code Routines",
    "Path:":          "Path:",
    "새 루틴":        "New routine",
    "루틴 편집":      "Edit routine",
    "스케줄":         "Schedule",
    "Dry-run":        "Dry-run",
    "Dry-run…":       "Dry-run…",
    "루틴이 없습니다. ＋ 새 루틴 으로 만들어보세요.":
        "No routines yet. Click ＋ New routine to create one.",
    "이름":           "Name",
    "스케줄 (cron)":  "Schedule (cron)",
    "명령":           "Command",
    "작업 디렉토리 (cwd)": "Working directory (cwd)",
    "활성":           "Enabled",
    "이 루틴을 삭제할까요?":     "Delete this routine?",
    "이 루틴을 지금 실행할까요?": "Run this routine now?",
    "이름과 명령이 필요합니다":   "Name and command are required",
    "삭제됨":         "Deleted",
}

NEW_ZH: dict[str, str] = {
    # Computer Use Lab
    "Computer Use Lab": "Computer Use Lab",
    "Anthropic computer-use-2025-01-24 beta · plan-only (실행하지 않음)":
        "Anthropic computer-use-2025-01-24 beta · 仅计划（不执行）",
    "대시보드는 모델의 tool plan만 표시 — 실제 마우스/키보드 제어는 하지 않습니다.":
        "仪表板仅显示模型的 tool plan — 不执行任何鼠标/键盘操作。",
    "예: Open Finder and click Documents…": "例：Open Finder and click Documents…",
    "스크린샷 경로 (~/.claude 하위, 선택)": "截图路径 (~/  下，可选)",
    "실행":           "运行",
    "최근 호출":      "最近调用",
    "툴 호출":        "tool 调用",
    "Tool Plan":      "Tool Plan",
    "텍스트 응답":    "文本响应",
    "툴 호출 없음 — 모델이 텍스트로만 응답":
        "无 tool 调用 — 模型仅以文本响应",
    "실행 중…":       "运行中…",

    "Memory Lab":     "Memory Lab",
    "Anthropic memory-2025-08-18 beta · 서버측 memory blocks 라운드트립":
        "Anthropic memory-2025-08-18 beta · 服务器端 memory blocks 往返",
    "예: 내 이름은 Alex 이고 간결한 답변 선호. 기억해줘.":
        "例：我叫 Alex，喜欢简洁的回复。请记住。",
    "관찰된 메모리 블록": "已观察的内存块",
    "이벤트":         "事件",
    "메모리 이벤트":  "内存事件",
    "응답":           "响应",
    "메모리 이벤트 없음 — 모델이 메모리를 사용하지 않음":
        "无内存事件 — 模型未使用 memory 工具",

    "Advisor Lab":    "Advisor Lab",
    "Executor (저비용/빠름) + Advisor (고지능/느림) 페어링 — 비용/품질 델타 시각화":
        "Executor (低成本/快) + Advisor (高智商/慢) 配对 — 可视化成本/质量差异",
    "동일 프롬프트가 두 모델에 보내지고 결과가 비교됩니다.":
        "同一提示发给两个模型，结果会被对比。",
    "Executor":       "Executor",
    "Advisor":        "Advisor",
    "실행 중 (executor → advisor)…": "运行中 (executor → advisor)…",
    "델타":           "差异",
    "토큰":           "tokens",
    "비용":           "成本",
    "지연":           "延迟",

    "Claude Code Routines": "Claude Code Routines",
    "Path:":          "路径：",
    "새 루틴":        "新建例程",
    "루틴 편집":      "编辑例程",
    "스케줄":         "调度",
    "Dry-run":        "Dry-run",
    "Dry-run…":       "Dry-run…",
    "루틴이 없습니다. ＋ 새 루틴 으로 만들어보세요.":
        "尚无例程。点击 ＋ 新建例程 来创建。",
    "이름":           "名称",
    "스케줄 (cron)":  "调度 (cron)",
    "명령":           "命令",
    "작업 디렉토리 (cwd)": "工作目录 (cwd)",
    "활성":           "启用",
    "이 루틴을 삭제할까요?":     "删除此例程？",
    "이 루틴을 지금 실행할까요?": "现在运行此例程？",
    "이름과 명령이 필요합니다":   "需要名称和命令",
    "삭제됨":         "已删除",
}
