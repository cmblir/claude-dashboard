"""세션 인덱스 · 스코어링 · 타임라인 API.

~/.claude/projects/*/*.jsonl 을 SQLite 에 인덱싱하고, 세션/토큰/타임라인
/ 에이전트 그래프 엔드포인트를 노출한다. `_compute_score` 는 세션 점수의
투명 휴리스틱 공식.
"""
from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import PROJECTS_DIR, SCORE_MIN_TOOLS, _cwd_to_slug
from .db import _db, _db_init
from .logger import log
from .utils import _iso_ms


def background_index() -> None:
    """부팅 시 호출 — 변경된 세션만 재인덱싱."""
    try:
        r = index_all_sessions(force=False)
        log.info("initial index: %s", r)
    except Exception as e:
        log.warning("index failed: %s", e)


def _first_user_prompt(lines: list[dict]) -> str:
    for msg in lines:
        if msg.get("type") != "user":
            continue
        c = msg.get("message", {})
        if isinstance(c, dict):
            content = c.get("content")
            if isinstance(content, str):
                return content.strip()[:500]
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        return (b.get("text") or "").strip()[:500]
    return ""


def _extract_model(lines: list[dict]) -> str:
    for msg in lines:
        if msg.get("type") == "assistant":
            m = (msg.get("message") or {}).get("model")
            if m:
                return str(m)
    return ""


def _compute_score(stats: dict) -> tuple[int, dict]:
    """세션 품질 스코어 계산 (0–100). 투명한 휴리스틱:
    - 완료성: 메시지 수 / 대화 길이
    - 생산성: tool_use 수
    - 오류율 역가중
    - 에이전트 위임 보너스 (멀티에이전트 활용)
    - 다양성 (tool 다양성)
    """
    b = {}
    msgs = stats.get("message_count", 0)
    tools = stats.get("tool_use_count", 0)
    errors = stats.get("error_count", 0)
    agents = stats.get("agent_call_count", 0)
    diversity = stats.get("tool_diversity", 0)
    duration_min = max(1, stats.get("duration_ms", 0) // 60000)

    b["engagement"] = min(25, int(msgs / 4))
    b["productivity"] = min(25, int(tools * 1.2))
    b["delegation"] = min(15, agents * 3)
    b["diversity"] = min(15, diversity * 2)
    b["reliability"] = max(0, 20 - errors * 4)
    total = sum(b.values())
    return min(100, max(0, total)), b


def _index_jsonl(jsonl: Path, project_dir: str) -> Optional[dict]:
    """단일 세션 jsonl 파싱 → DB 업서트."""
    try:
        text = jsonl.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    if not text.strip():
        return None

    session_id = jsonl.stem
    lines: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            lines.append(json.loads(line))
        except Exception:
            continue
    if not lines:
        return None

    timestamps = []
    msg_count = user_cnt = asst_cnt = tool_cnt = err_cnt = agent_cnt = 0
    tok_in = tok_out = tok_cache_read = tok_cache_create = 0
    tool_counter: Counter = Counter()
    subagent_counter: Counter = Counter()
    tool_rows: list[tuple] = []
    edges: list[tuple] = []

    for m in lines:
        ts = _iso_ms(m.get("timestamp", "") or "")
        if ts:
            timestamps.append(ts)
        t = m.get("type")
        if t == "user":
            user_cnt += 1
            msg_count += 1
        elif t == "assistant":
            asst_cnt += 1
            msg_count += 1
            msg_obj = m.get("message") or {}
            content = msg_obj.get("content")
            # 이 턴에서 생긴 tool_use 들을 수집해 둔 뒤, turn_tokens 를 split
            turn_tools: list[tuple] = []
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        tool_cnt += 1
                        tool_name = b.get("name") or "?"
                        tool_counter[tool_name] += 1
                        inp = b.get("input") or {}
                        subagent = inp.get("subagent_type") if isinstance(inp, dict) else None
                        if tool_name == "Agent" and subagent:
                            agent_cnt += 1
                            subagent_counter[subagent] += 1
                            edges.append((session_id, "claude", subagent, ts or 0))
                        input_summary = ""
                        if isinstance(inp, dict):
                            for k in ("description", "command", "prompt", "file_path", "pattern"):
                                v = inp.get(k)
                                if v:
                                    input_summary = str(v)[:200]
                                    break
                        turn_tools.append((tool_name, subagent or "", input_summary))
            # usage 파싱 — 이 턴의 토큰
            usage = msg_obj.get("usage") or {}
            u_in = int(usage.get("input_tokens") or 0)
            u_out = int(usage.get("output_tokens") or 0)
            u_cr = int(usage.get("cache_read_input_tokens") or 0)
            u_cc = int(usage.get("cache_creation_input_tokens") or 0)
            tok_in += u_in
            tok_out += u_out
            tok_cache_read += u_cr
            tok_cache_create += u_cc
            # 턴 전체 토큰 (입력 + 출력) 을 이 턴의 tool 개수로 분배 — 0개면 무시
            turn_total = u_in + u_out + u_cr + u_cc
            per_tool = (turn_total // len(turn_tools)) if turn_tools else 0
            for (tn, sa, inp_sum) in turn_tools:
                tool_rows.append((session_id, ts or 0, tn, sa, inp_sum, 0, per_tool))
        elif t == "tool_result":
            content = (m.get("message") or {}).get("content")
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("is_error"):
                        err_cnt += 1

    started = min(timestamps) if timestamps else 0
    ended = max(timestamps) if timestamps else 0
    duration = max(0, ended - started)
    first_prompt = _first_user_prompt(lines)
    model = _extract_model(lines)
    # 프로젝트 슬러그(`-Users-<user>-foo-bar`) 에서 홈 prefix 를 제거 → 사람이 읽을 수 있는 이름으로
    home_slug = _cwd_to_slug(Path.home())  # 예: "-Users-<username>"
    project_name = ""
    if project_dir:
        if project_dir.startswith(home_slug + "-"):
            project_name = project_dir[len(home_slug) + 1 :].replace("-", "/")
        else:
            project_name = project_dir.lstrip("-").replace("-", "/")

    # 세션의 실제 cwd는 JSONL 메시지에 기록되어 있음 (첫 번째 찾은 값)
    cwd = ""
    for m in lines:
        c_val = m.get("cwd")
        if isinstance(c_val, str) and c_val:
            cwd = c_val
            break

    stats = {
        "message_count": msg_count,
        "tool_use_count": tool_cnt,
        "error_count": err_cnt,
        "agent_call_count": agent_cnt,
        "duration_ms": duration,
        "tool_diversity": len(tool_counter),
    }
    score, breakdown = _compute_score(stats)

    tok_total = tok_in + tok_out + tok_cache_read + tok_cache_create
    with _db() as c:
        c.execute("DELETE FROM tool_uses WHERE session_id=?", (session_id,))
        c.execute("DELETE FROM agent_edges WHERE session_id=?", (session_id,))
        if tool_rows:
            c.executemany(
                "INSERT INTO tool_uses (session_id,ts,tool,subagent_type,input_summary,had_error,turn_tokens) VALUES (?,?,?,?,?,?,?)",
                tool_rows,
            )
        if edges:
            c.executemany("INSERT INTO agent_edges (session_id,src,dst,ts) VALUES (?,?,?,?)", edges)
        c.execute("""
        INSERT OR REPLACE INTO sessions
        (session_id,project,project_dir,cwd,jsonl_path,started_at,ended_at,duration_ms,
         message_count,user_msg_count,assistant_msg_count,tool_use_count,error_count,
         agent_call_count,subagent_types,model,first_user_prompt,last_summary,
         score,score_breakdown,indexed_at,
         input_tokens,output_tokens,cache_read_tokens,cache_creation_tokens,total_tokens)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            session_id, project_name, project_dir, cwd, str(jsonl),
            started, ended, duration,
            msg_count, user_cnt, asst_cnt, tool_cnt, err_cnt, agent_cnt,
            json.dumps(dict(subagent_counter)), model, first_prompt, "",
            score, json.dumps(breakdown), int(time.time() * 1000),
            tok_in, tok_out, tok_cache_read, tok_cache_create, tok_total,
        ))
        c.execute("INSERT INTO scores_history (session_id,ts,score,breakdown) VALUES (?,?,?,?)",
                  (session_id, int(time.time() * 1000), score, json.dumps(breakdown)))

    return {
        "sessionId": session_id, "project": project_name, "projectDir": project_dir,
        "startedAt": started, "endedAt": ended, "durationMs": duration,
        "messageCount": msg_count, "toolUseCount": tool_cnt, "errorCount": err_cnt,
        "agentCallCount": agent_cnt, "score": score, "model": model,
    }


def index_all_sessions(force: bool = False) -> dict:
    """~/.claude/projects/*/*.jsonl 전부 재인덱스."""
    _db_init()
    indexed = 0
    skipped = 0
    if not PROJECTS_DIR.exists():
        return {"indexed": 0, "skipped": 0, "total": 0}

    with _db() as c:
        existing = {r["jsonl_path"]: r["indexed_at"] for r in c.execute("SELECT jsonl_path, indexed_at FROM sessions")}

    for project_dir_path in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir_path.is_dir():
            continue
        project_dir = project_dir_path.name
        for jsonl in sorted(project_dir_path.glob("*.jsonl")):
            try:
                mtime_ms = int(jsonl.stat().st_mtime * 1000)
            except Exception:
                mtime_ms = 0
            if not force:
                prev = existing.get(str(jsonl))
                if prev and prev >= mtime_ms:
                    skipped += 1
                    continue
            if _index_jsonl(jsonl, project_dir):
                indexed += 1
            else:
                skipped += 1
    return {"indexed": indexed, "skipped": skipped, "total": indexed + skipped}


def api_sessions_list(query: dict) -> dict:
    _db_init()
    limit = int(query.get("limit", ["200"])[0])
    offset = int(query.get("offset", ["0"])[0])
    q = (query.get("q", [""])[0] or "").strip()
    project = (query.get("project", [""])[0] or "").strip()
    sort = (query.get("sort", ["recent"])[0] or "recent").strip()

    sql = "SELECT * FROM sessions WHERE 1=1"
    params: list = []
    if q:
        sql += " AND (first_user_prompt LIKE ? OR project LIKE ? OR session_id LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if project:
        sql += " AND project_dir = ?"
        params.append(project)
    order_col = {
        "recent": "started_at DESC",
        "score": "score DESC",
        "tools": "tool_use_count DESC",
        "tokens": "total_tokens DESC",
        "duration": "duration_ms DESC",
    }.get(sort, "started_at DESC")
    sql += f" ORDER BY {order_col} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with _db() as c:
        rows = [dict(r) for r in c.execute(sql, params).fetchall()]
        total = c.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
    for r in rows:
        try:
            r["score_breakdown"] = json.loads(r.get("score_breakdown") or "{}")
        except Exception:
            r["score_breakdown"] = {}
        try:
            r["subagent_types"] = json.loads(r.get("subagent_types") or "{}")
        except Exception:
            r["subagent_types"] = {}
        # display helpers
        cwd = r.get("cwd") or ""
        r["project"] = Path(cwd).name if cwd else (r.get("project") or "")
        r["projectPath"] = cwd
    return {"sessions": rows, "total": total}


def api_session_tokens(session_id: str) -> dict:
    """세션의 토큰 사용량 분해 — 도구별 / 서브에이전트별 / 시간순."""
    _db_init()
    with _db() as c:
        s = c.execute(
            "SELECT input_tokens,output_tokens,cache_read_tokens,cache_creation_tokens,total_tokens "
            "FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        if not s:
            return {"error": "not found"}
        by_tool = [dict(r) for r in c.execute(
            "SELECT tool, COUNT(*) AS calls, SUM(turn_tokens) AS tokens "
            "FROM tool_uses WHERE session_id=? GROUP BY tool ORDER BY tokens DESC",
            (session_id,)
        ).fetchall()]
        by_agent = [dict(r) for r in c.execute(
            "SELECT subagent_type AS agent, COUNT(*) AS calls, SUM(turn_tokens) AS tokens "
            "FROM tool_uses WHERE session_id=? AND subagent_type != '' "
            "GROUP BY subagent_type ORDER BY tokens DESC",
            (session_id,)
        ).fetchall()]
    return {
        "session_id": session_id,
        "totals": {
            "input": s["input_tokens"], "output": s["output_tokens"],
            "cacheRead": s["cache_read_tokens"], "cacheCreate": s["cache_creation_tokens"],
            "total": s["total_tokens"],
        },
        "byTool": by_tool,
        "byAgent": by_agent,
    }


def api_session_timeline(session_id: str) -> dict:
    """세션 처음→끝 진행 타임라인. user 프롬프트 / Agent 위임 / 큰 도구 호출만 추려서 그래프 노드/엣지 형태로."""
    _db_init()
    with _db() as c:
        s = c.execute(
            "SELECT cwd, jsonl_path, started_at, ended_at, model, first_user_prompt FROM sessions WHERE session_id=?",
            (session_id,)
        ).fetchone()
        if not s:
            return {"error": "not found"}
        tools = [dict(r) for r in c.execute(
            "SELECT ts, tool, subagent_type, input_summary, turn_tokens "
            "FROM tool_uses WHERE session_id=? ORDER BY ts ASC",
            (session_id,)
        ).fetchall()]

    # JSONL 에서 user 프롬프트만 추출 (텍스트 / 시각)
    user_prompts: list = []
    jp = s["jsonl_path"]
    if jp and Path(jp).exists():
        for line in Path(jp).read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                m = json.loads(line)
            except Exception:
                continue
            if m.get("type") != "user":
                continue
            ts = _iso_ms(m.get("timestamp", "") or "")
            content = (m.get("message") or {}).get("content")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        text = b.get("text") or ""
                        break
            if not text or not ts:
                continue
            text = text.strip()
            # tool_result 같은 시스템 메시지 제외
            if text.startswith("[") and text.endswith("]"):
                continue
            user_prompts.append({"ts": ts, "text": text[:500]})

    # 그래프 노드: user prompt → 후속 도구/에이전트 호출들로 묶음
    nodes: list = []
    edges: list = []
    nid = 0
    def _add_node(kind: str, label: str, ts: int, meta: dict = None) -> int:
        nonlocal nid
        nid += 1
        nodes.append({"id": nid, "kind": kind, "label": label, "ts": ts, "meta": meta or {}})
        return nid

    # 첫 user prompt 가 없으면 그냥 'session start' 노드부터
    if not user_prompts:
        prev = _add_node("session", "세션 시작", s["started_at"], {"model": s["model"]})
    else:
        prev = _add_node("session", "세션 시작", s["started_at"], {"model": s["model"]})

    # 시간순 통합 이벤트 스트림 — Agent/Task 와 user prompt 우선, 일반 도구는 연속 묶기
    events: list = []
    for u in user_prompts:
        events.append({"ts": u["ts"], "kind": "prompt", "data": u})
    for t in tools:
        if t["tool"] == "Agent":
            events.append({"ts": t["ts"], "kind": "agent", "data": t})
        else:
            events.append({"ts": t["ts"], "kind": "tool", "data": t})
    events.sort(key=lambda e: e["ts"] or 0)

    # 연속된 일반 tool 들을 묶기 (prompt/agent 사이의 같은 tool 그룹)
    grouped: list = []
    bucket: dict = None
    for ev in events:
        if ev["kind"] in ("prompt", "agent"):
            if bucket:
                grouped.append(bucket); bucket = None
            grouped.append(ev)
        else:
            t = ev["data"]
            tool_name = t.get("tool")
            if bucket and bucket.get("toolName") == tool_name:
                bucket["count"] += 1
                bucket["tokens"] += t.get("turn_tokens") or 0
                bucket["lastTs"] = ev["ts"]
            else:
                if bucket:
                    grouped.append(bucket)
                bucket = {
                    "kind": "toolGroup", "toolName": tool_name,
                    "count": 1, "tokens": t.get("turn_tokens") or 0,
                    "ts": ev["ts"], "lastTs": ev["ts"],
                }
    if bucket:
        grouped.append(bucket)

    # 최대 200 이벤트로 cap (안전망)
    if len(grouped) > 200:
        # prompt/agent 는 모두 유지, toolGroup 은 토큰 기준 상위만
        prompts_agents = [g for g in grouped if g.get("kind") in ("prompt", "agent")]
        tool_groups = sorted(
            [g for g in grouped if g.get("kind") == "toolGroup"],
            key=lambda x: x["tokens"], reverse=True,
        )
        keep_set = set(id(g) for g in prompts_agents)
        for g in tool_groups[: max(0, 200 - len(prompts_agents))]:
            keep_set.add(id(g))
        grouped = [g for g in grouped if id(g) in keep_set]
        grouped.sort(key=lambda g: g.get("ts") or 0)

    for ev in grouped:
        kind = ev.get("kind")
        if kind == "prompt":
            n = _add_node("prompt", ev["data"]["text"][:80], ev["ts"],
                          {"full": ev["data"]["text"]})
            edges.append({"src": prev, "dst": n})
            prev = n
        elif kind == "agent":
            t = ev["data"]
            label = (t.get("subagent_type") or "agent")[:50]
            n = _add_node("agent", label, ev["ts"],
                          {"summary": t.get("input_summary", ""),
                           "tokens": t.get("turn_tokens") or 0,
                           "tool": "Agent"})
            edges.append({"src": prev, "dst": n})
        elif kind == "toolGroup":
            label = f"{ev['toolName']} ×{ev['count']}" if ev['count'] > 1 else ev['toolName']
            n = _add_node("tool", label, ev["ts"],
                          {"tokens": ev["tokens"], "tool": ev["toolName"], "count": ev["count"]})
            edges.append({"src": prev, "dst": n})

    # 마지막 노드 → 세션 끝
    end_n = _add_node("session", "세션 종료", s["ended_at"], {})
    edges.append({"src": prev, "dst": end_n})

    return {
        "session_id": session_id,
        "model": s["model"],
        "startedAt": s["started_at"],
        "endedAt": s["ended_at"],
        "firstPrompt": s["first_user_prompt"],
        "nodes": nodes,
        "edges": edges,
    }


def api_project_timeline(query: dict) -> dict:
    """프로젝트의 모든 세션을 시간순으로 묶어 그래프 데이터로. 세션 단위 노드 + 도구·에이전트 요약."""
    cwd = (query.get("cwd", [""])[0] or "").strip()
    if not cwd:
        return {"error": "cwd required"}
    _db_init()
    with _db() as c:
        sessions = [dict(r) for r in c.execute(
            "SELECT session_id, started_at, ended_at, score, tool_use_count, agent_call_count, "
            "       total_tokens, first_user_prompt, model, subagent_types "
            "FROM sessions WHERE cwd=? AND started_at IS NOT NULL "
            "ORDER BY started_at ASC",
            (cwd,)
        ).fetchall()]
    nodes: list = []
    edges: list = []
    nid = 0
    prev = None
    project_name = Path(cwd).name
    pid = nid + 1
    nid += 1
    nodes.append({"id": pid, "kind": "project", "label": project_name, "ts": sessions[0]["started_at"] if sessions else 0, "meta": {"cwd": cwd}})
    prev = pid
    for s in sessions:
        try:
            sub_map = json.loads(s.get("subagent_types") or "{}")
        except Exception:
            sub_map = {}
        nid += 1
        sn = nid
        nodes.append({
            "id": sn, "kind": "session",
            "label": (s.get("first_user_prompt") or "(요청 없음)")[:60],
            "ts": s["started_at"],
            "meta": {
                "sessionId": s["session_id"],
                "score": s["score"],
                "tools": s["tool_use_count"],
                "agents": s["agent_call_count"],
                "tokens": s["total_tokens"],
                "model": s["model"],
                "subagents": sub_map,
                "endedAt": s["ended_at"],
            },
        })
        edges.append({"src": prev, "dst": sn})
        prev = sn
    return {"cwd": cwd, "name": project_name, "nodes": nodes, "edges": edges, "sessionCount": len(sessions)}


def api_session_detail(session_id: str) -> dict:
    _db_init()
    with _db() as c:
        row = c.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not row:
            return {"error": "not found"}
        tools = [dict(r) for r in c.execute(
            "SELECT ts,tool,subagent_type,input_summary,had_error FROM tool_uses WHERE session_id=? ORDER BY ts ASC LIMIT 500",
            (session_id,)
        ).fetchall()]
        edges = [dict(r) for r in c.execute(
            "SELECT src,dst,ts FROM agent_edges WHERE session_id=? ORDER BY ts ASC",
            (session_id,)
        ).fetchall()]
    d = dict(row)
    try:
        d["score_breakdown"] = json.loads(d.get("score_breakdown") or "{}")
    except Exception:
        d["score_breakdown"] = {}
    try:
        d["subagent_types"] = json.loads(d.get("subagent_types") or "{}")
    except Exception:
        d["subagent_types"] = {}

    # messages preview from jsonl
    messages = []
    jp = d.get("jsonl_path")
    if jp and Path(jp).exists():
        try:
            for i, line in enumerate(Path(jp).read_text(encoding="utf-8", errors="replace").splitlines()):
                if i > 400:
                    break
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                t = msg.get("type")
                if t not in ("user", "assistant"):
                    continue
                preview = ""
                role = t
                content = (msg.get("message") or {}).get("content")
                if isinstance(content, str):
                    preview = content[:600]
                elif isinstance(content, list):
                    parts = []
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "text":
                            parts.append(b.get("text", ""))
                        elif b.get("type") == "tool_use":
                            parts.append(f"[tool: {b.get('name','')} ]")
                        elif b.get("type") == "tool_result":
                            parts.append("[result]")
                    preview = "\n".join(parts)[:600]
                messages.append({
                    "role": role,
                    "ts": _iso_ms(msg.get("timestamp", "") or ""),
                    "preview": preview,
                })
        except Exception:
            pass

    return {"session": d, "tools": tools, "edges": edges, "messages": messages}


def api_sessions_stats() -> dict:
    _db_init()
    with _db() as c:
        total = c.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
        # 점수 평균은 도구 호출 ≥ SCORE_MIN_TOOLS 인 세션만 포함
        avg = c.execute(
            "SELECT COALESCE(AVG(score), 0) AS s FROM sessions WHERE tool_use_count >= ?",
            (SCORE_MIN_TOOLS,),
        ).fetchone()["s"]
        scored_n = c.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE tool_use_count >= ?",
            (SCORE_MIN_TOOLS,),
        ).fetchone()["n"]
        total_tools = c.execute("SELECT COALESCE(SUM(tool_use_count),0) AS n FROM sessions").fetchone()["n"]
        total_agents = c.execute("SELECT COALESCE(SUM(agent_call_count),0) AS n FROM sessions").fetchone()["n"]
        total_errors = c.execute("SELECT COALESCE(SUM(error_count),0) AS n FROM sessions").fetchone()["n"]

        tool_rows = [dict(r) for r in c.execute(
            "SELECT tool, COUNT(*) AS n FROM tool_uses GROUP BY tool ORDER BY n DESC LIMIT 20"
        ).fetchall()]
        subagent_rows = [dict(r) for r in c.execute(
            "SELECT subagent_type AS name, COUNT(*) AS n FROM tool_uses WHERE subagent_type != '' GROUP BY subagent_type ORDER BY n DESC"
        ).fetchall()]
        # Top sessions 도 도구≥기준 만 (짧은 세션이 우연히 100점 받아 dominate 하는 것 방지)
        top_sessions = [dict(r) for r in c.execute(
            "SELECT session_id, project, score, started_at, first_user_prompt, tool_use_count "
            "FROM sessions WHERE tool_use_count >= ? ORDER BY score DESC LIMIT 10",
            (SCORE_MIN_TOOLS,),
        ).fetchall()]
        # 프로젝트별 평균: 짧은 세션 제외한 평균 + 짧은 세션 수도 함께
        proj_rows = [dict(r) for r in c.execute(
            """SELECT
                COALESCE(NULLIF(cwd,''), project_dir) AS key,
                MAX(cwd) AS cwd,
                MAX(project_dir) AS project_dir,
                COUNT(*) AS sessions,
                SUM(CASE WHEN tool_use_count >= ? THEN 1 ELSE 0 END) AS scored_sessions,
                AVG(CASE WHEN tool_use_count >= ? THEN score END) AS avg_score,
                SUM(tool_use_count) AS tools
               FROM sessions
               GROUP BY COALESCE(NULLIF(cwd,''), project_dir)
               ORDER BY sessions DESC""",
            (SCORE_MIN_TOOLS, SCORE_MIN_TOOLS),
        ).fetchall()]
    # name = cwd 의 basename (없으면 슬러그)
    for r in proj_rows:
        cwd = r.get("cwd") or ""
        r["name"] = Path(cwd).name if cwd else (r.get("project_dir") or "")

        # daily timeline (last 30 days)
        thirty_days_ago = int((time.time() - 30 * 86400) * 1000)
        daily_rows = c.execute(
            "SELECT started_at, score, tool_use_count, error_count FROM sessions WHERE started_at >= ? ORDER BY started_at",
            (thirty_days_ago,)
        ).fetchall()

    # bucket by day — 점수 평균은 도구≥기준 세션만 포함
    buckets: dict = defaultdict(lambda: {"sessions": 0, "tools": 0, "errors": 0, "score_sum": 0, "scored": 0})
    for r in daily_rows:
        if not r["started_at"]:
            continue
        d = datetime.fromtimestamp(r["started_at"] / 1000).strftime("%Y-%m-%d")
        b = buckets[d]
        b["sessions"] += 1
        b["tools"] += r["tool_use_count"] or 0
        b["errors"] += r["error_count"] or 0
        if (r["tool_use_count"] or 0) >= SCORE_MIN_TOOLS:
            b["score_sum"] += r["score"] or 0
            b["scored"] += 1
    timeline = []
    for d in sorted(buckets.keys()):
        b = buckets[d]
        timeline.append({
            "date": d,
            "sessions": b["sessions"],
            "tools": b["tools"],
            "errors": b["errors"],
            "avg_score": round(b["score_sum"] / max(1, b["scored"]), 1) if b["scored"] else None,
        })

    return {
        "totalSessions": total,
        "scoredSessions": scored_n,
        "minToolsForScore": SCORE_MIN_TOOLS,
        "avgScore": round(avg, 1),
        "totalTools": total_tools,
        "totalAgentCalls": total_agents,
        "totalErrors": total_errors,
        "toolDistribution": tool_rows,
        "subagentDistribution": subagent_rows,
        "topSessions": top_sessions,
        "projectDistribution": proj_rows,
        "timeline": timeline,
    }


def api_agent_graph(query: dict) -> dict:
    _db_init()
    days = int(query.get("days", ["30"])[0])
    since = int((time.time() - days * 86400) * 1000)
    with _db() as c:
        edges = c.execute(
            "SELECT src,dst,COUNT(*) AS n FROM agent_edges WHERE ts >= ? GROUP BY src,dst ORDER BY n DESC",
            (since,)
        ).fetchall()
        tool_rows = c.execute(
            "SELECT subagent_type AS agent, tool, COUNT(*) AS n FROM tool_uses WHERE subagent_type != '' AND ts >= ? GROUP BY subagent_type, tool",
            (since,)
        ).fetchall()

    nodes: dict = {}
    def _ensure(nid: str, kind: str, label: Optional[str] = None):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "kind": kind, "label": label or nid}

    _ensure("claude", "core", "Claude (메인)")
    edge_list = []
    for r in edges:
        src, dst, n = r["src"], r["dst"], r["n"]
        _ensure(src, "core" if src == "claude" else "agent")
        _ensure(dst, "agent")
        edge_list.append({"src": src, "dst": dst, "weight": n})
    for r in tool_rows:
        agent, tool, n = r["agent"], r["tool"], r["n"]
        _ensure(agent, "agent")
        tool_id = f"tool:{tool}"
        _ensure(tool_id, "tool", tool)
        edge_list.append({"src": agent, "dst": tool_id, "weight": n})

    return {"nodes": list(nodes.values()), "edges": edge_list}


