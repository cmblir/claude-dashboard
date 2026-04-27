"""v2.40.0 — Hyper Agent project scope + sidebar discovery aids.

Adds EN + ZH translations for the new strings introduced by:
- Sidebar Recent quick-block (🕒).
- Star toggle aria-labels (즐겨찾기 추가/해제).
- '/' shortcut hint added to global search placeholder.
- Project-scoped Hyper Agent (modal labels are reused from v2.39 manual_14).

Note: bare "즐겨찾기" is already mapped in manual_11 (Run Center favorites).
We only declare it here for completeness; the setdefault merge in
``translations_manual.py`` keeps the earlier definition.

Imported by translations_manual.py.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # Sidebar quick-blocks (v2.40 sidebar UX)
    "최근 사용":         "Recent",
    "즐겨찾기 해제":      "Remove from favorites",
    "즐겨찾기 추가":      "Add to favorites",
    # Global search placeholder — now mentions '/' shortcut
    "검색… ⌘K · /":      "Search… ⌘K · /",
}

NEW_ZH: dict[str, str] = {
    "최근 사용":         "最近",
    "즐겨찾기 해제":      "从收藏中移除",
    "즐겨찾기 추가":      "添加到收藏",
    "검색… ⌘K · /":      "搜索… ⌘K · /",
}
