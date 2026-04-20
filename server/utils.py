"""공용 헬퍼 — 파일 I/O · frontmatter 파싱 · 시간 포맷.

stdlib 만 의존. 다른 server.* 모듈의 말단 유틸.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .logger import log


# ───────── 파일 I/O ─────────

def _safe_read(p: Path, limit: Optional[int] = None) -> str:
    """존재 여부·읽기 실패를 흡수하고 빈 문자열 반환. 필요 시 앞 N 문자 제한."""
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return text if limit is None else text[:limit]
    except Exception:
        return ""


def _safe_write(p: Path, text: str) -> bool:
    """원자적 쓰기 — tmp 파일에 쓰고 rename. 부모 디렉토리 자동 생성."""
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception as e:
        log.error("write failed for %s: %s", p, e)
        return False


# ───────── Markdown frontmatter ─────────

def _parse_frontmatter(text: str) -> dict:
    """`---` 블록을 key/value dict 로. 파싱 불가 시 빈 dict."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    block = m.group(1)
    out: dict = {}
    for line in block.splitlines():
        kv = re.match(r"^(\w[\w-]*):\s*(.*)$", line.strip())
        if kv:
            out[kv.group(1)] = kv.group(2).strip().strip('"').strip("'")
    return out


def _parse_tools_field(raw: str) -> list:
    """frontmatter 의 `tools:` 필드를 list 로 — JSON 배열 또는 쉼표 구분 문자열."""
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("["):
        try:
            return [str(x) for x in json.loads(raw) if x]
        except Exception:
            pass
    return [t.strip().strip('"').strip("'") for t in raw.split(",") if t.strip()]


def _strip_frontmatter(text: str) -> str:
    """frontmatter 를 제거한 본문 반환."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    return text[m.end():] if m else text


# ───────── 시간 변환 ─────────

def _iso_ms(ts_str: str) -> Optional[int]:
    """ISO 8601 문자열을 epoch ms 로. 파싱 실패 시 None."""
    if not ts_str:
        return None
    try:
        return int(datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return None


def _fmt_rel(ms: Optional[int]) -> str:
    """상대 시간 문자열 — '3초 전', '5분 전', '2시간 전', '1일 전'."""
    if not ms:
        return "—"
    now = int(time.time() * 1000)
    d = max(0, (now - ms) // 1000)
    if d < 60:
        return f"{d}초 전"
    if d < 3600:
        return f"{d // 60}분 전"
    if d < 86400:
        return f"{d // 3600}시간 전"
    return f"{d // 86400}일 전"
