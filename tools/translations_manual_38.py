"""v2.61.0 — Hot badge (I3) + IPC stream log panel (orchestrator tab).

Korean -> English / Chinese for the new UI strings introduced by cycle 9.
Loaded by ``tools/translations_manual.py``.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # I3 — per-mode hot badge
    "이 모드에서 가장 많이 사용한 탭":        "Most-used tab in this mode",
    # Orchestrator IPC log panel
    "IPC 스트림":                              "IPC stream",
    "inbound (사용자 → 오케) / outbound (오케 → 채널) 분리 로그":
        "Inbound (user → orch) / outbound (orch → channel) split log",
    "채널 필터 (선택)":                        "Channel filter (optional)",
    "inbound 없음":                            "No inbound",
    "outbound 없음":                           "No outbound",
}

NEW_ZH: dict[str, str] = {
    "이 모드에서 가장 많이 사용한 탭":        "本模式使用最多的标签",
    "IPC 스트림":                              "IPC 流",
    "inbound (사용자 → 오케) / outbound (오케 → 채널) 분리 로그":
        "入站（用户→编排）/ 出站（编排→频道）分离日志",
    "채널 필터 (선택)":                        "频道过滤器（可选）",
    "inbound 없음":                            "无入站",
    "outbound 없음":                           "无出站",
}
