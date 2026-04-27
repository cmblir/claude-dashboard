"""v2.40.4 — Hook Detective + Recent Blocks + Command pretty-decoder.

Adds EN + ZH translations for the hook-introspection UI strings.
Imported by translations_manual.py.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # Detective box
    "Hook Detective": "Hook Detective",
    "차단 에러 메시지를 붙여넣으면 어떤 훅인지 자동 식별":
        "Paste a block-error message — auto-identifies which hook fired",
    "PreToolUse:Edit hook returned blocking error from command: …":
        "PreToolUse:Edit hook returned blocking error from command: …",
    "hook id 패턴을 찾지 못했습니다": "No hook-id pattern found in the pasted text",
    "클릭하면 해당 훅 카드로 이동": "Click to jump to the matching hook card",

    # Recent Blocks
    "최근 차단된 훅": "Recently blocked hooks",
    "차단 이벤트": "block events",
    "파일 스캔": "files scanned",
    "카드를 클릭하면 검색 자동 적용": "Click a card to auto-apply the search",

    # Detail modal
    "🔬 상세": "🔬 Detail",
    "훅 상세":           "Hook detail",
    "Dispatcher chain (디코드됨)": "Dispatcher chain (decoded)",
    "node":              "node",
    "runner script":     "runner script",
    "hook id":           "hook id",
    "handler script":    "handler script",
    "flags":             "flags",
    "매처":              "Matcher",
    "스코프":            "Scope",
    "소스":              "Source",
    "플러그인 키":       "Plugin key",
    "타입":              "Type",
    "타임아웃":          "Timeout",
    "Full command (raw)": "Full command (raw)",
}

NEW_ZH: dict[str, str] = {
    "Hook Detective": "Hook Detective",
    "차단 에러 메시지를 붙여넣으면 어떤 훅인지 자동 식별":
        "粘贴拦截错误消息 — 自动识别是哪个钩子",
    "PreToolUse:Edit hook returned blocking error from command: …":
        "PreToolUse:Edit hook returned blocking error from command: …",
    "hook id 패턴을 찾지 못했습니다": "在粘贴的文本中未找到 hook id 模式",
    "클릭하면 해당 훅 카드로 이동": "点击跳转到对应的钩子卡片",

    "최근 차단된 훅": "近期被拦截的钩子",
    "차단 이벤트": "拦截事件",
    "파일 스캔": "扫描的文件",
    "카드를 클릭하면 검색 자동 적용": "点击卡片自动应用搜索",

    "🔬 상세": "🔬 详情",
    "훅 상세":           "钩子详情",
    "Dispatcher chain (디코드됨)": "调度链（已解码）",
    "node":              "node",
    "runner script":     "runner 脚本",
    "hook id":           "hook id",
    "handler script":    "handler 脚本",
    "flags":             "flags",
    "매처":              "匹配器",
    "스코프":            "范围",
    "소스":              "来源",
    "플러그인 키":       "插件 key",
    "타입":              "类型",
    "타임아웃":          "超时",
    "Full command (raw)": "完整命令（原文）",
}
