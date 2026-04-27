"""v2.39.0 — Hyper Agent: sub-agents that self-refine over time.

Adds EN + ZH translations for every t('...') call site introduced by the
Hyper Agent modal (dist/index.html). Imported by translations_manual.py.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # ── Modal chrome ────────────────────────────────────────────
    "Hyper Agent": "Hyper Agent",
    "Hyper Agent — 자동 정교화 토글/설정": "Hyper Agent — toggle / configure auto-refine",
    "Hyper Agent 로드 실패: ": "Hyper Agent load failed: ",
    "서브 에이전트의 시스템 프롬프트·툴·디스크립션을 메타 LLM이 주기적으로 다듬습니다.":
        "A meta-LLM periodically refines this sub-agent's system prompt, tools, and description.",

    # ── Toggle + objective ──────────────────────────────────────
    "자동 정교화 활성화": "Auto-refine enabled",
    "OFF 상태에서도 \"지금 다듬기\" 버튼은 사용 가능합니다.":
        "The \"Refine now\" button still works while this is OFF.",
    "목표 (Objective)": "Objective",
    "예: 응답을 더 간결하게, 액션 위주로. 또는 특정 도메인 지식 강조.":
        "e.g. make replies tighter and more action-oriented; emphasise a specific domain.",

    # ── Refine targets ──────────────────────────────────────────
    "시스템 프롬프트": "System prompt",
    "툴 목록": "Tools",
    "디스크립션": "Description",

    # ── Trigger / provider ──────────────────────────────────────
    "트리거": "Trigger",
    "manual=수동만 / after_session=세션 종료 시 / interval=시간 주기 / any=둘 다":
        "manual=manual only / after_session=on session end / interval=time-based / any=both",
    "Refine 프로바이더": "Refine provider",
    "메타 LLM (Opus 권장)": "Meta-LLM (Opus recommended)",

    # ── Throttle / budget ───────────────────────────────────────
    "최소 세션 간격": "Min sessions between",
    "after_session 트리거 디바운스": "after_session trigger debounce",
    "예산 (USD)": "Budget (USD)",
    "총 누적 비용 한도 (도달 시 정지)": "Cumulative cost cap (stops on hit)",
    "누적 사용 / 정교화": "Spent / refinements",

    # ── Buttons ─────────────────────────────────────────────────
    "💾 저장": "💾 Save",
    "👁 Dry-run 미리보기": "👁 Dry-run preview",
    "⚡ 지금 다듬기": "⚡ Refine now",
    "진행 중": "Working",

    # ── History ─────────────────────────────────────────────────
    "정교화 이력": "Refinement history",
    "아직 정교화 이력이 없습니다.": "No refinements yet.",
    "롤백": "Roll back",

    # ── Toasts / confirms ───────────────────────────────────────
    "이 에이전트를 지금 다듬을까요? 메타 LLM 호출 비용이 발생합니다.":
        "Refine this agent now? A meta-LLM call will be billed.",
    "Dry-run 완료 — 제안 확인": "Dry-run complete — review proposal",
    "정교화 적용 완료": "Refinement applied",
    "실패: ": "Failed: ",
    "이 시점의 백업으로 에이전트를 되돌릴까요?":
        "Roll the agent back to this snapshot?",
    "롤백 완료": "Rolled back",
    "롤백 실패: ": "Rollback failed: ",
    "저장 실패: ": "Save failed: ",
}

NEW_ZH: dict[str, str] = {
    # Modal chrome
    "Hyper Agent": "Hyper Agent",
    "Hyper Agent — 자동 정교화 토글/설정": "Hyper Agent — 切换 / 配置自动精炼",
    "Hyper Agent 로드 실패: ": "Hyper Agent 加载失败：",
    "서브 에이전트의 시스템 프롬프트·툴·디스크립션을 메타 LLM이 주기적으로 다듬습니다.":
        "元 LLM 会定期精炼此子代理的系统提示、工具和描述。",

    # Toggle + objective
    "자동 정교화 활성화": "启用自动精炼",
    "OFF 상태에서도 \"지금 다듬기\" 버튼은 사용 가능합니다.":
        "即使关闭，也仍可点击「立即精炼」。",
    "목표 (Objective)": "目标 (Objective)",
    "예: 응답을 더 간결하게, 액션 위주로. 또는 특정 도메인 지식 강조.":
        "例：让回复更简洁、更注重行动；或强调特定领域知识。",

    # Refine targets
    "시스템 프롬프트": "系统提示",
    "툴 목록": "工具列表",
    "디스크립션": "描述",

    # Trigger / provider
    "트리거": "触发器",
    "manual=수동만 / after_session=세션 종료 시 / interval=시간 주기 / any=둘 다":
        "manual=仅手动 / after_session=会话结束时 / interval=按时间 / any=两者",
    "Refine 프로바이더": "Refine 提供商",
    "메타 LLM (Opus 권장)": "元 LLM（推荐 Opus）",

    # Throttle / budget
    "최소 세션 간격": "最小会话间隔",
    "after_session 트리거 디바운스": "after_session 触发防抖",
    "예산 (USD)": "预算 (USD)",
    "총 누적 비용 한도 (도달 시 정지)": "累计费用上限（达到即停止）",
    "누적 사용 / 정교화": "已用 / 精炼次数",

    # Buttons
    "💾 저장": "💾 保存",
    "👁 Dry-run 미리보기": "👁 Dry-run 预览",
    "⚡ 지금 다듬기": "⚡ 立即精炼",
    "진행 중": "进行中",

    # History
    "정교화 이력": "精炼历史",
    "아직 정교화 이력이 없습니다.": "尚无精炼记录。",
    "롤백": "回滚",

    # Toasts / confirms
    "이 에이전트를 지금 다듬을까요? 메타 LLM 호출 비용이 발생합니다.":
        "现在精炼此代理？将产生元 LLM 调用费用。",
    "Dry-run 완료 — 제안 확인": "Dry-run 完成 — 请查看建议",
    "정교화 적용 완료": "精炼已应用",
    "실패: ": "失败：",
    "이 시점의 백업으로 에이전트를 되돌릴까요?":
        "将代理回滚到此快照？",
    "롤백 완료": "已回滚",
    "롤백 실패: ": "回滚失败：",
    "저장 실패: ": "保存失败：",
}
