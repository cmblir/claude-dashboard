"""v2.53.0 — full-text session search UI strings.

Korean source -> English / Chinese for the new sessions tab search box.
Loaded by ``tools/translations_manual.py`` and emitted into
``dist/locales/{en,zh}.json`` by the build pipeline.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    "세션 내용 검색…": "Search session content…",
    "세션 내용 검색": "Search session content",
    "검색 결과": "Search results",
    "검색 지우기": "Clear search",
    "일치": "Matches",
    "점수": "Score",
    "스니펫": "Snippet",
    "검색어가 너무 짧음 (2글자 이상)": "Query too short (min 2 chars)",
    "검색 중…": "Searching…",
    "검색 결과 없음": "No results",
    "스캔한 세션": "Sessions scanned",
    "일치한 세션": "Sessions matched",
    "역할": "Role",
}

NEW_ZH: dict[str, str] = {
    "세션 내용 검색…": "搜索会话内容…",
    "세션 내용 검색": "搜索会话内容",
    "검색 결과": "搜索结果",
    "검색 지우기": "清除搜索",
    "일치": "匹配",
    "점수": "分数",
    "스니펫": "片段",
    "검색어가 너무 짧음 (2글자 이상)": "查询过短（至少 2 个字符）",
    "검색 중…": "搜索中…",
    "검색 결과 없음": "没有结果",
    "스캔한 세션": "已扫描会话",
    "일치한 세션": "匹配会话",
    "역할": "角色",
}
