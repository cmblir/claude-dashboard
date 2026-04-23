"""Learner (v2.30.0) — Claude Code 세션 패턴 추출.

`~/.claude/projects/**/*.jsonl` 을 스캔해 최근 N 세션에서 반복 패턴을 찾고
"skill / prompt library / workflow template 으로 만드시겠습니까?" 카드를 제안.

AI 호출 없이 **순수 통계 기반** (MVP). AI 판단은 후속에서.

추출 패턴:
- Tool 빈도 TOP 10
- Tool 시퀀스 3-gram TOP 10 (같은 세션에서 연속 N-3 개 호출 패턴)
- 반복 사용자 프롬프트 (첫 60자 정규화 매칭, 3회 이상 반복)
- 세션 길이 분포 (짧은 반복 작업 vs 긴 복합 작업)
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from .logger import log

_PROJECTS = Path.home() / ".claude" / "projects"
_MAX_SESSIONS = 100     # 스캔 세션 상한
_MAX_LINES_PER = 500    # 세션당 파싱 라인 상한 (성능)
_RECENT_DAYS = 30
_MIN_REPEAT = 3         # 반복 프롬프트 최소 횟수
_MIN_SEQ_SUPPORT = 3    # tool 시퀀스 최소 발생 횟수

_WS_RE = re.compile(r"\s+")


def _norm_prompt(text: str) -> str:
    """프롬프트 첫 60자 정규화 — 공백 축약 + 소문자."""
    if not isinstance(text, str):
        return ""
    s = _WS_RE.sub(" ", text.strip())[:60].lower()
    return s


def _first_text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "text":
                return blk.get("text") or ""
    return ""


def _parse_session(path: Path) -> dict:
    """세션 하나에서 지표 추출. 실패 시 빈 결과."""
    tools: list[str] = []
    first_user_prompt = ""
    line_count = 0
    total_tokens = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= _MAX_LINES_PER:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                line_count += 1
                m = d.get("message")
                if isinstance(m, dict):
                    # 첫 user 텍스트 수집
                    if not first_user_prompt and m.get("role") == "user":
                        first_user_prompt = _first_text_of(m.get("content"))
                    # tool_use 추출
                    c = m.get("content")
                    if isinstance(c, list):
                        for blk in c:
                            if isinstance(blk, dict) and blk.get("type") == "tool_use":
                                name = blk.get("name") or ""
                                if name:
                                    tools.append(name)
                    usage = m.get("usage") or {}
                    total_tokens += int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)
    except Exception as e:
        log.warning("learner parse %s: %s", path, e)
        return {"tools": [], "firstPrompt": "", "lineCount": 0, "totalTokens": 0}
    return {
        "tools": tools,
        "firstPrompt": first_user_prompt,
        "lineCount": line_count,
        "totalTokens": total_tokens,
    }


def _collect_sessions() -> list[dict]:
    """최근 N 일 세션 메타 + 지표."""
    if not _PROJECTS.exists():
        return []
    cutoff = (datetime.now() - timedelta(days=_RECENT_DAYS)).timestamp()
    files = []
    for jsonl in _PROJECTS.glob("*/*.jsonl"):
        try:
            st = jsonl.stat()
            if st.st_mtime < cutoff:
                continue
            files.append((jsonl, st.st_mtime))
        except Exception:
            continue
    files.sort(key=lambda x: x[1], reverse=True)
    files = files[:_MAX_SESSIONS]
    sessions = []
    for jsonl, mtime in files:
        parsed = _parse_session(jsonl)
        sessions.append({
            "path": str(jsonl.relative_to(_PROJECTS)),
            "mtime": int(mtime * 1000),
            "project": jsonl.parent.name,
            **parsed,
        })
    return sessions


def _tool_ngrams(tools: list[str], n: int = 3) -> list[tuple]:
    if len(tools) < n:
        return []
    return [tuple(tools[i:i + n]) for i in range(len(tools) - n + 1)]


def api_learner_patterns(_q: dict | None = None) -> dict:
    """세션 스캔 후 패턴 카드 반환."""
    sessions = _collect_sessions()
    if not sessions:
        return {
            "ok": True, "sessions": 0, "days": _RECENT_DAYS,
            "patterns": [], "message": "no recent sessions",
        }

    # 1) tool 빈도
    tool_counter: Counter = Counter()
    for s in sessions:
        tool_counter.update(s["tools"])
    top_tools = tool_counter.most_common(10)

    # 2) tool 3-gram 시퀀스
    seq_counter: Counter = Counter()
    for s in sessions:
        seq_counter.update(_tool_ngrams(s["tools"], n=3))
    top_sequences = [
        {"sequence": list(seq), "count": cnt}
        for seq, cnt in seq_counter.most_common(10)
        if cnt >= _MIN_SEQ_SUPPORT
    ]

    # 3) 반복 프롬프트
    prompt_counter: Counter = Counter()
    prompt_samples: dict[str, str] = {}
    for s in sessions:
        norm = _norm_prompt(s.get("firstPrompt") or "")
        if norm:
            prompt_counter[norm] += 1
            if norm not in prompt_samples:
                prompt_samples[norm] = s["firstPrompt"]
    repeated_prompts = [
        {"normalized": k, "sample": prompt_samples[k], "count": v}
        for k, v in prompt_counter.most_common(10) if v >= _MIN_REPEAT
    ]

    # 4) 세션 길이 분포 (bucket)
    length_buckets = defaultdict(int)
    for s in sessions:
        lc = s["lineCount"]
        if lc < 10: length_buckets["small"] += 1
        elif lc < 50: length_buckets["medium"] += 1
        elif lc < 200: length_buckets["large"] += 1
        else: length_buckets["huge"] += 1

    # 5) 총 토큰
    total_tokens_sum = sum(s["totalTokens"] for s in sessions)

    # 패턴 카드 생성 — 각 카드는 { type, title, detail, action: {kind, payload} }
    patterns: list[dict] = []

    # 반복 프롬프트 → Prompt Library 추천
    for rp in repeated_prompts[:5]:
        patterns.append({
            "type": "repeated_prompt",
            "title": f"'{rp['sample'][:40]}...' 프롬프트 반복 ({rp['count']}회)",
            "detail": rp["sample"][:200],
            "count": rp["count"],
            "action": {"kind": "promptLibrary", "body": rp["sample"], "suggestedTitle": rp["sample"][:30]},
        })

    # 자주 쓰는 tool 시퀀스 → 워크플로우 템플릿 추천
    for seq in top_sequences[:5]:
        patterns.append({
            "type": "tool_sequence",
            "title": f"{' → '.join(seq['sequence'])} ({seq['count']}회)",
            "detail": f"이 tool 시퀀스가 {seq['count']}번 반복되었습니다. 워크플로우로 자동화하면 좋습니다.",
            "count": seq["count"],
            "action": {"kind": "workflowTemplate", "sequence": seq["sequence"]},
        })

    return {
        "ok": True,
        "sessions": len(sessions),
        "days": _RECENT_DAYS,
        "stats": {
            "totalTokens": total_tokens_sum,
            "lengthBuckets": dict(length_buckets),
            "topTools": [{"name": n, "count": c} for n, c in top_tools],
        },
        "patterns": patterns,
    }
