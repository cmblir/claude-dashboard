"""v2.51.0 — Auto-Resume terminal-scope + Reliability category strings.

Imported by translations_manual.py.

Covers new user-visible strings introduced by:
  - VIEWS.autoResumeManager terminal column / live-session chip
  - "Reliability" sidebar category (group label + short)
  - Auto-resume binding error when session is not currently running
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # Terminal-scope column
    "터미널": "Terminal",
    "종료됨": "Closed",
    "세션이 실행 중이 아님": "Session not currently running",
    # Reliability category
    "안정성": "Reliability",
    "Auto-Resume · 자동 복구 · 바인딩 관리": "Auto-Resume · auto-recovery · binding management",
}

NEW_ZH: dict[str, str] = {
    "터미널": "终端",
    "종료됨": "已关闭",
    "세션이 실행 중이 아님": "会话当前未在运行",
    "안정성": "稳定性",
    "Auto-Resume · 자동 복구 · 바인딩 관리": "Auto-Resume · 自动恢复 · 绑定管理",
}
