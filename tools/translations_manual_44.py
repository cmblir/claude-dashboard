"""Chat connection-gate strings.

Translations for the lazyclawChat connection-verification overlay
(model picker + Test Connection) introduced to stop the silent
"중단됨" bubble that users were hitting on first send.

Loaded by ``tools/translations_manual.py``.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    "연결 확인": "Verify connection",
    "채팅을 시작하기 전에 모델을 선택하고 연결을 확인하세요. 첫 메시지가 응답 없이 끊기는 것을 방지합니다.":
        "Pick a model and verify the connection before chatting. "
        "Prevents the first message from silently dropping.",
    "확인 없이 진행 (위험)": "Skip without verifying (risky)",
    "확인 중…": "Verifying…",
    "연결을 확인하는 중…": "Verifying connection…",
    "연결 OK": "Connection OK",
    "먼저 연결을 확인하세요": "Verify the connection first",
    "응답이 비어 있습니다 — 모델/연결을 확인하세요":
        "Empty response — check the model and the connection",
}

NEW_ZH: dict[str, str] = {
    "연결 확인": "验证连接",
    "채팅을 시작하기 전에 모델을 선택하고 연결을 확인하세요. 첫 메시지가 응답 없이 끊기는 것을 방지합니다.":
        "在开始聊天前选择模型并验证连接，避免首条消息无响应中断。",
    "확인 없이 진행 (위험)": "跳过验证（有风险）",
    "확인 중…": "验证中…",
    "연결을 확인하는 중…": "正在验证连接…",
    "연결 OK": "连接正常",
    "먼저 연결을 확인하세요": "请先验证连接",
    "응답이 비어 있습니다 — 모델/연결을 확인하세요":
        "响应为空 — 请检查模型与连接",
}
