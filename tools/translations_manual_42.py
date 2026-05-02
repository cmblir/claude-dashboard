"""v2.67.0 — Y1 missing translations: permissions summary, email toggle, settings link.

Fixes Korean residue in EN/ZH detected by i18n runtime scan.
Loaded by ``tools/translations_manual.py``.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # U1 (v2.66.7) — System tab permissions summary card
    "권한 요약": "Permissions Summary",
    # U1 — link to settings/permissions tab (override bad prev translation)
    '편집은 "Settings 편집" 또는 "권한" 탭에서.': 'Edit via the "Settings" or "Permissions" tab.',
    # O1 (v2.66.1) — auth panel email toggle tooltip
    "클릭으로 이메일 표시 전환": "Click to toggle email display",
}

NEW_ZH: dict[str, str] = {
    # U1 — System tab permissions summary card
    "권한 요약": "权限摘要",
    # O1 — auth panel email toggle tooltip
    "클릭으로 이메일 표시 전환": "点击切换邮件显示",
}
