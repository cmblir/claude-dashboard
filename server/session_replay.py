"""Session Replay Lab — Claude Code JSONL 세션 로그 타임라인 뷰 (v2.25.0).

각 프로젝트 폴더 아래의 `*.jsonl` 을 파일 메타(최근 50건)로 나열하고,
개별 파일을 요청하면 이벤트 단위로 파싱해 (role, 요약, tool_use, timestamp,
tokens?) 를 반환한다. 대용량 파일은 최대 N 이벤트로 제한.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .logger import log

_PROJECTS = Path.home() / ".claude" / "projects"
_MAX_EVENTS = 2000


def api_session_replay_list(_q: dict | None = None) -> dict:
    """JSONL 파일 최근 50건 — (경로, 크기, mtime, 줄 수 근사)."""
    if not _PROJECTS.exists():
        return {"ok": True, "files": []}
    files = []
    for jsonl in _PROJECTS.glob("*/*.jsonl"):
        try:
            st = jsonl.stat()
            files.append({
                "path": str(jsonl.relative_to(_PROJECTS)),
                "fullPath": str(jsonl),
                "size": st.st_size,
                "mtime": int(st.st_mtime * 1000),
                "project": jsonl.parent.name,
            })
        except Exception:
            continue
    files.sort(key=lambda f: f["mtime"], reverse=True)
    return {"ok": True, "files": files[:50]}


def _summarize_content(content) -> str:
    """content 를 1줄 요약 문자열로. content 는 list[dict] 또는 str."""
    if isinstance(content, str):
        return content[:300]
    if isinstance(content, list):
        parts = []
        for blk in content:
            if not isinstance(blk, dict):
                continue
            bt = blk.get("type")
            if bt == "text":
                parts.append((blk.get("text") or "")[:300])
            elif bt == "tool_use":
                parts.append(f"[tool_use:{blk.get('name')}]")
            elif bt == "tool_result":
                parts.append(f"[tool_result:{blk.get('tool_use_id', '?')[:8]}]")
            elif bt == "thinking":
                parts.append("[thinking:…]")
        return " · ".join(parts)[:500]
    return ""


def api_session_replay_load(query: dict | None = None) -> dict:
    """특정 JSONL 파싱 — query 는 relative path 를 받음."""
    rel = ""
    if isinstance(query, dict):
        v = query.get("path")
        rel = v[0] if isinstance(v, list) and v else (v if isinstance(v, str) else "")
    if not rel or ".." in rel or rel.startswith("/"):
        return {"ok": False, "error": "invalid path"}
    full = _PROJECTS / rel
    if not full.exists() or not full.is_file() or full.suffix != ".jsonl":
        return {"ok": False, "error": "file not found"}
    # 상위 탈출 방어
    try:
        if _PROJECTS.resolve() not in full.resolve().parents and full.resolve().parent != _PROJECTS.resolve().parent:
            pass  # path 이미 _PROJECTS 기준이므로 필요 없음
    except Exception:
        return {"ok": False, "error": "resolve failed"}

    events = []
    total_tokens_in = 0
    total_tokens_out = 0
    try:
        with open(full, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= _MAX_EVENTS:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                ts_raw = d.get("timestamp") or ""
                ts_ms = 0
                if ts_raw:
                    try:
                        ts_ms = int(datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp() * 1000)
                    except Exception:
                        ts_ms = 0
                evt = {
                    "idx": i,
                    "type": d.get("type") or "",
                    "ts": ts_ms,
                    "sessionId": d.get("sessionId") or "",
                }
                # message 기반 (assistant/user turn)
                m = d.get("message")
                if isinstance(m, dict):
                    evt["role"] = m.get("role") or ""
                    evt["summary"] = _summarize_content(m.get("content"))
                    usage = m.get("usage") or {}
                    evt["tokensIn"] = int(usage.get("input_tokens") or 0)
                    evt["tokensOut"] = int(usage.get("output_tokens") or 0)
                    total_tokens_in += evt["tokensIn"]
                    total_tokens_out += evt["tokensOut"]
                elif "content" in d:
                    evt["summary"] = _summarize_content(d.get("content"))
                # operation (비-메시지 이벤트: compact, etc)
                if d.get("operation"):
                    evt["operation"] = d.get("operation")
                events.append(evt)
    except Exception as e:
        log.warning("session replay parse failed: %s", e)
        return {"ok": False, "error": f"parse failed: {e}"}

    return {
        "ok": True,
        "path": rel,
        "events": events,
        "eventCount": len(events),
        "truncated": len(events) >= _MAX_EVENTS,
        "totalTokensIn": total_tokens_in,
        "totalTokensOut": total_tokens_out,
    }
