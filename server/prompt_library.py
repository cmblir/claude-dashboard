"""Prompt Library — 자주 쓰는 프롬프트를 태그와 함께 저장 + 검색 + 워크플로우 복제.

저장소: `~/.claude-dashboard-prompt-library.json`
스키마: {"items": [{id, title, body, tags:[], model?, createdAt, updatedAt}]}

'워크플로우로 복제' 는 기존 workflows store 에 start → session → output 3 노드의
새 워크플로우를 추가한다.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from .config import _env_path
from .logger import log
from .utils import _safe_read, _safe_write

STORE_PATH = _env_path(
    "CLAUDE_DASHBOARD_PROMPT_LIBRARY",
    Path.home() / ".claude-dashboard-prompt-library.json",
)


SEED_ITEMS = [
    {
        "id": "seed-code-review",
        "title": "코드 리뷰 요청",
        "body": "다음 코드에 대해 보안·성능·가독성 관점에서 리뷰해줘. 개선 제안은 우선순위 순으로.\n\n```\n<CODE HERE>\n```",
        "tags": ["review", "code", "ko"],
        "model": "claude-sonnet-4-6",
    },
    {
        "id": "seed-summarize-meeting",
        "title": "회의 요약",
        "body": "다음 회의록을 5줄로 요약해. 핵심 결정, 액션 아이템, 담당자를 bullet 로 정리.\n\n<MEETING TRANSCRIPT>",
        "tags": ["summarize", "meeting", "ko"],
        "model": "claude-haiku-4-5",
    },
    {
        "id": "seed-sql-optimize",
        "title": "SQL 쿼리 최적화",
        "body": "다음 PostgreSQL 쿼리를 분석해. 인덱스 제안, EXPLAIN 읽는 법, 재작성 방안을 단계별로 제시해.\n\n```sql\n<SQL HERE>\n```",
        "tags": ["sql", "optimize", "db"],
        "model": "claude-sonnet-4-6",
    },
]


def _load() -> dict:
    if not STORE_PATH.exists():
        return {"items": list(SEED_ITEMS)}
    try:
        data = json.loads(_safe_read(STORE_PATH))
        if not isinstance(data, dict):
            return {"items": list(SEED_ITEMS)}
        data.setdefault("items", [])
        return data
    except Exception as e:
        log.warning("prompt_library load failed: %s", e)
        return {"items": list(SEED_ITEMS)}


def _save(data: dict) -> bool:
    try:
        return _safe_write(STORE_PATH, json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        log.warning("prompt_library save failed: %s", e)
        return False


def api_prompt_library_list(_q: dict | None = None) -> dict:
    store = _load()
    items = store.get("items") or []
    tag_set = sorted({t for it in items for t in (it.get("tags") or [])})
    return {"items": items, "tags": tag_set}


def api_prompt_library_save(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}
    title = (body.get("title") or "").strip()
    content = (body.get("body") or "").strip()
    if not title:
        return {"ok": False, "error": "title required"}
    if not content:
        return {"ok": False, "error": "body required"}

    tags_raw = body.get("tags") or []
    tags = [t.strip() for t in tags_raw if isinstance(t, str) and t.strip()][:10]
    model = (body.get("model") or "").strip() or None

    # v2.25.0 — keyword triggers: 입력 텍스트에 이 키워드가 포함되면 워크플로우
    # session 노드 실행 시 해당 프롬프트 body 가 system slot 에 prepend 됨.
    keywords_raw = body.get("keywords") or []
    keywords = [k.strip() for k in keywords_raw if isinstance(k, str) and k.strip()][:10]

    store = _load()
    items = store.get("items") or []
    pid = body.get("id")
    now = int(time.time())

    if pid:
        # 기존 수정
        found = next((i for i in items if i.get("id") == pid), None)
        if not found:
            return {"ok": False, "error": "not found"}
        found["title"] = title
        found["body"] = content
        found["tags"] = tags
        found["keywords"] = keywords
        if model:
            found["model"] = model
        else:
            found.pop("model", None)
        found["updatedAt"] = now
    else:
        # 신규
        pid = f"p-{uuid.uuid4().hex[:10]}"
        items.insert(0, {
            "id": pid, "title": title, "body": content, "tags": tags,
            "keywords": keywords,
            "model": model, "createdAt": now, "updatedAt": now,
        })
        store["items"] = items

    _save(store)
    return {"ok": True, "id": pid}


def find_keyword_triggers(input_text: str) -> list[dict]:
    """입력 텍스트에 키워드가 포함된 prompt library 항목 리스트 반환.

    v2.33.8 — 토큰 경계 매칭 (word boundary) 으로 정확도 개선:
    - 영문/숫자 키워드는 `\\b` 로 단어 경계 요구 (예: 'test' 가 'testing' 에 매칭되지 않음)
    - 한글/특수문자 포함 키워드는 기존처럼 부분 문자열 매칭 (Unicode word boundary 를
      기대할 수 없으므로)

    반환 시 `_matchedKeyword` 필드로 어떤 키워드가 매칭됐는지 기록해 run 로그에 표시 가능.
    """
    if not isinstance(input_text, str) or not input_text:
        return []
    import re
    text_lower = input_text.lower()
    out = []
    for it in _load().get("items") or []:
        kws = it.get("keywords") or []
        if not isinstance(kws, list):
            continue
        matched_kw = None
        for kw in kws:
            if not (isinstance(kw, str) and kw):
                continue
            kw_lower = kw.lower()
            # ASCII 전용 키워드는 단어 경계 요구
            if all(ord(ch) < 128 for ch in kw_lower) and re.fullmatch(r"[a-z0-9][a-z0-9_\-]*", kw_lower):
                pat = r"\b" + re.escape(kw_lower) + r"\b"
                if re.search(pat, text_lower):
                    matched_kw = kw
                    break
            else:
                # 한글/공백/특수문자 포함 — 부분 문자열
                if kw_lower in text_lower:
                    matched_kw = kw
                    break
        if matched_kw is not None:
            # mutation 방지 위해 얕은 복사 후 _matchedKeyword 주입
            out.append({**it, "_matchedKeyword": matched_kw})
    return out


def api_prompt_library_delete(body: dict) -> dict:
    pid = (body or {}).get("id") if isinstance(body, dict) else None
    if not pid:
        return {"ok": False, "error": "id required"}
    store = _load()
    items = [i for i in (store.get("items") or []) if i.get("id") != pid]
    store["items"] = items
    _save(store)
    return {"ok": True}


def api_prompt_library_duplicate(body: dict) -> dict:
    pid = (body or {}).get("id") if isinstance(body, dict) else None
    if not pid:
        return {"ok": False, "error": "id required"}
    store = _load()
    items = store.get("items") or []
    src = next((i for i in items if i.get("id") == pid), None)
    if not src:
        return {"ok": False, "error": "not found"}
    new_id = f"p-{uuid.uuid4().hex[:10]}"
    now = int(time.time())
    dup = dict(src)
    dup["id"] = new_id
    dup["title"] = (src.get("title") or "") + " (copy)"
    dup["createdAt"] = now
    dup["updatedAt"] = now
    items.insert(0, dup)
    _save(store)
    return {"ok": True, "id": new_id}


def api_prompt_library_to_workflow(body: dict) -> dict:
    """선택한 프롬프트로 start → session → output 3 노드 워크플로우 생성."""
    from .workflows import _load_all as _wf_load, _dump_all as _wf_dump, _new_wf_id

    pid = (body or {}).get("id") if isinstance(body, dict) else None
    if not pid:
        return {"ok": False, "error": "id required"}
    store = _load()
    item = next((i for i in (store.get("items") or []) if i.get("id") == pid), None)
    if not item:
        return {"ok": False, "error": "not found"}

    wf_store = _wf_load()
    wf_id = _new_wf_id()
    now = int(time.time() * 1000)
    model = item.get("model") or "claude-sonnet-4-6"
    # 간단 모델 라벨 → assignee 형식
    assignee = model

    wf = {
        "id": wf_id,
        "name": f"[Prompt] {item.get('title','untitled')}",
        "createdAt": now, "updatedAt": now,
        "nodes": [
            {"id": "n-start", "type": "start", "x": 60, "y": 160, "title": "start", "data": {}},
            {"id": "n-session", "type": "session", "x": 300, "y": 160, "title": item.get("title","prompt")[:40], "data": {
                "subject": item.get("title","")[:80],
                "description": item.get("body",""),
                "assignee": assignee,
                "agentRole": "",
                "cwd": "",
                "inputsMode": "concat",
            }},
            {"id": "n-out", "type": "output", "x": 560, "y": 160, "title": "output", "data": {"exportTo": ""}},
        ],
        "edges": [
            {"id": "e-1", "from": "n-start", "fromPort": "out", "to": "n-session", "toPort": "in"},
            {"id": "e-2", "from": "n-session", "fromPort": "out", "to": "n-out", "toPort": "in"},
        ],
    }
    wf_store["workflows"][wf_id] = wf
    _wf_dump(wf_store)
    return {"ok": True, "workflowId": wf_id, "workflowName": wf["name"]}
