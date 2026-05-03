"""v2.71.4 — QQ114 mixed-locale leak in nav tile title/aria-label.

The chat & terminal nav-tile descriptions were two-sentence
Korean strings absent from the locale dicts; the substring-walker
in `_translateDOM` then leaked partial Chinese into the title
attribute (e.g. `등록된 AI 提供商(...)与 직접 대화`). Adding the
exact full-sentence keys here so the dict-walker hits the
straight match and stops fragmenting.

Loaded by ``tools/translations_manual.py``.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    "등록된 AI 프로바이더(Claude·OpenAI·Gemini·Ollama 등)와 직접 대화. assignee 즉석 전환·히스토리 저장.":
        "Chat directly with any registered AI provider (Claude / OpenAI / Gemini / Ollama, etc.). "
        "Switch assignees inline and keep per-session history.",
    "lazyclaw 설정·CLI 상태를 화이트리스트된 read-only 명령으로 즉시 점검 (claude --version, ollama list 등).":
        "Inspect lazyclaw configuration and CLI state via a whitelist of read-only commands "
        "(claude --version, ollama list, etc.).",
}

NEW_ZH: dict[str, str] = {
    "등록된 AI 프로바이더(Claude·OpenAI·Gemini·Ollama 등)와 직접 대화. assignee 즉석 전환·히스토리 저장.":
        "与已注册的 AI 提供商（Claude / OpenAI / Gemini / Ollama 等）直接对话。"
        "可即时切换 assignee 并保留每会话历史。",
    "lazyclaw 설정·CLI 상태를 화이트리스트된 read-only 명령으로 즉시 점검 (claude --version, ollama list 등).":
        "通过白名单的只读命令即时检查 lazyclaw 配置 / CLI 状态"
        "（claude --version、ollama list 等）。",
}
