"""버전 + CHANGELOG 로딩 — 프론트 사이드바, 챗봇 프롬프트가 공유."""
from __future__ import annotations

import time
from pathlib import Path

from .config import ROOT
from .utils import _safe_read

# v2.36.2 — process-start timestamp captured at module import. The dashboard
# polls /api/version every 60s and shows a "server restarted, refresh" toast
# when this value changes — automatically catching the "I pulled new code but
# the user is still on the old build" race.
_SERVER_STARTED_AT_MS = int(time.time() * 1000)


def get_version() -> str:
    """VERSION 파일에서 현재 버전 문자열 반환. 없으면 '0.0.0'."""
    fp = ROOT / "VERSION"
    raw = _safe_read(fp).strip()
    return raw or "0.0.0"


def get_latest_changelog(max_entries: int = 3) -> str:
    """CHANGELOG.md 에서 최근 max_entries 개 릴리스 섹션만 반환. 챗봇 프롬프트 용."""
    fp = ROOT / "CHANGELOG.md"
    text = _safe_read(fp)
    if not text:
        return ""
    # '## [1.0.0]' 같은 라인이 섹션 시작
    lines = text.splitlines()
    out_blocks: list[list[str]] = []
    cur: list[str] | None = None
    for line in lines:
        if line.startswith("## ["):
            if cur is not None:
                out_blocks.append(cur)
                if len(out_blocks) >= max_entries:
                    break
            cur = [line]
        elif cur is not None:
            cur.append(line)
    if cur is not None and len(out_blocks) < max_entries:
        out_blocks.append(cur)
    return "\n".join("\n".join(b).rstrip() for b in out_blocks)


def api_version_info() -> dict:
    return {
        "version":         get_version(),
        "changelog":       get_latest_changelog(3),
        "serverStartedAt": _SERVER_STARTED_AT_MS,
    }
