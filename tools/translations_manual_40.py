"""v2.64.0 — L1 Ralph auto-refresh + K5 orchestrator model override UI.

Korean -> English / Chinese for strings introduced by L1 (Ralph run
auto-refresh) and the orchestrator per-dispatch model override panel.
Loaded by ``tools/translations_manual.py``.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # K5 — orchestrator per-dispatch model override panel
    "이 호출만 모델 오버라이드": "Model override for this call only",
    "비워두면 기본값":           "Leave blank to use default",
}

NEW_ZH: dict[str, str] = {
    "이 호출만 모델 오버라이드": "仅本次调用覆盖模型",
    "비워두면 기본값":           "留空则使用默认值",
}
