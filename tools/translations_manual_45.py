"""Sidebar chat mode-toggle strings (v3.99.25 orchestrator chat).

The chat panel gained a chip toggle that swaps between the navigation
help-bot and the multi-agent orchestrator, plus a preset <select>
exposed only in orchestrator mode.

Loaded by ``tools/translations_manual.py``.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    "💬 도우미 모드": "💬 Helper mode",
    "🎼 오케스트레이터 모드": "🎼 Orchestrator mode",
    "네비게이션 도우미 ↔ 멀티 에이전트 오케스트레이터 전환":
        "Toggle navigation helper ↔ multi-agent orchestrator",
    "오케스트레이터 프리셋": "Orchestrator preset",
}

NEW_ZH: dict[str, str] = {
    "💬 도우미 모드": "💬 助手模式",
    "🎼 오케스트레이터 모드": "🎼 编排器模式",
    "네비게이션 도우미 ↔ 멀티 에이전트 오케스트레이터 전환":
        "切换导航助手 ↔ 多代理编排器",
    "오케스트레이터 프리셋": "编排器预设",
}
