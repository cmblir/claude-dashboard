"""v2.40.2 — Hooks tab emergency UX (search · filter · risk chip · panic).

Adds EN + ZH translations for the new hook-management UI strings.
Imported by translations_manual.py.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # Filter bar / chips
    "훅 검색 — 매처 / 명령 / 플러그인 / 설명":
        "Search hooks — matcher / command / plugin / description",
    "사용자":            "User",
    "플러그인":          "Plugin",
    "위험":              "Danger",
    "위험 훅만":         "Risky only",
    "필터 초기화":       "Clear filter",
    "표시":              "shown",
    "필터에 매치되는 훅 없음": "No hooks match the filter",

    # Panic button + flow
    "위험 훅 일괄 비활성화": "Bulk-disable risky hooks",
    "PreToolUse + Edit/Write/Bash 매처를 가진 모든 훅을 한 번에 비활성화 (삭제)":
        "Delete every PreToolUse hook with an Edit / Write / Bash matcher in one click",
    "PreToolUse + Edit/Write/Bash 매처를 가진 ":
        "Delete the ",
    "개 훅을 모두 삭제할까요? 이 작업은 즉시 적용됩니다.":
        " PreToolUse + Edit/Write/Bash hooks now? This applies immediately.",
    "위험 훅 없음":      "No risky hooks",
    "위험 훅 비활성화 완료": "Risky hooks disabled",

    # Card-level danger chip tooltip
    "PreToolUse + Edit/Write/Bash 매처 — 작업이 막히는 원인일 가능성":
        "PreToolUse + Edit/Write/Bash matcher — likely cause of blocked work",
}

NEW_ZH: dict[str, str] = {
    "훅 검색 — 매처 / 명령 / 플러그인 / 설명":
        "搜索钩子 — 匹配器 / 命令 / 插件 / 说明",
    "사용자":            "用户",
    "플러그인":          "插件",
    "위험":              "危险",
    "위험 훅만":         "仅危险钩子",
    "필터 초기화":       "清除筛选",
    "표시":              "显示",
    "필터에 매치되는 훅 없음": "没有匹配筛选的钩子",

    "위험 훅 일괄 비활성화": "一键禁用危险钩子",
    "PreToolUse + Edit/Write/Bash 매처를 가진 모든 훅을 한 번에 비활성화 (삭제)":
        "一键删除所有匹配 PreToolUse + Edit / Write / Bash 的钩子",
    "PreToolUse + Edit/Write/Bash 매처를 가진 ":
        "删除 ",
    "개 훅을 모두 삭제할까요? 이 작업은 즉시 적용됩니다.":
        " 个 PreToolUse + Edit/Write/Bash 钩子吗？此操作立即生效。",
    "위험 훅 없음":      "没有危险钩子",
    "위험 훅 비활성화 완료": "危险钩子已禁用",

    "PreToolUse + Edit/Write/Bash 매처 — 작업이 막히는 원인일 가능성":
        "PreToolUse + Edit/Write/Bash 匹配器 — 可能是工作受阻的原因",
}
