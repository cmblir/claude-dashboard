"""대시보드 브리핑 집계 — 홈/개요 화면의 카드들을 채운다.

- `~/.claude/history.jsonl` 에서 최근 활동 요약 (today stats, devices)
- `~/.claude/tasks/*` 와 `~/.claude/scheduled-tasks/*` 병합
- 승인 대기 세션 탐지 (briefing_pending_approvals)
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path

from .config import (
    HISTORY_JSONL, PROJECTS_DIR, SCHEDULED_TASKS_DIR, SESSIONS_DIR,
    TASKS_DIR, TODOS_DIR, _UUID_RE,
)
from .device import _detect_device_info
from .projects import list_projects
from .utils import _iso_ms, _parse_frontmatter, _safe_read


def _today_start_ts_ms() -> int:
    midnight = datetime.combine(date.today(), datetime.min.time())
    return int(midnight.timestamp() * 1000)

def _iter_history_recent(limit_lines: int = 5000):
    if not HISTORY_JSONL.exists():
        return
    try:
        lines = HISTORY_JSONL.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-limit_lines:]:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue
    except Exception:
        return

def _today_history_stats() -> dict:
    today_start = _today_start_ts_ms()
    cmd_count = 0
    projects_today = set()
    for entry in _iter_history_recent():
        ts = entry.get("timestamp")
        if not isinstance(ts, (int, float)):
            continue
        if ts >= today_start:
            cmd_count += 1
            proj = entry.get("project")
            if proj:
                projects_today.add(proj)
    return {"commandCount": cmd_count, "projectCount": len(projects_today)}

def _count_projects() -> int:
    if not PROJECTS_DIR.exists():
        return 0
    return sum(1 for p in PROJECTS_DIR.iterdir() if p.is_dir())

def _count_active_sessions() -> int:
    if not SESSIONS_DIR.exists():
        return 0
    return sum(1 for p in SESSIONS_DIR.glob("*.json"))

def _count_tasks_in_todos() -> int:
    if not TODOS_DIR.exists():
        return 0
    total = 0
    for p in TODOS_DIR.glob("*.json"):
        try:
            data = json.loads(_safe_read(p))
            if isinstance(data, list):
                total += len(data)
        except Exception:
            pass
    return total

def briefing_overview() -> dict:
    today = _today_history_stats()
    auto_resume_active = 0
    try:
        from .auto_resume import _load_all as _ar_load_all
        store = _ar_load_all()
        auto_resume_active = sum(1 for e in store.values() if e.get("enabled"))
    except Exception:
        pass
    return {
        "projectCount": _count_projects(),
        "taskCount": _count_tasks_in_todos(),
        "sessionCount": _count_active_sessions(),
        "commandCount": today["commandCount"],
        "todayProjectCount": today["projectCount"],
        "autoResumeActiveCount": auto_resume_active,
        "lastUpdate": int(time.time() * 1000),
    }

def briefing_devices() -> dict:
    info = _detect_device_info()
    real_username = info["username"]
    device_label = info["label"]
    all_projects: dict = {}
    for entry in _iter_history_recent(limit_lines=3000):
        proj = entry.get("project")
        ts = entry.get("timestamp")
        if not proj or not isinstance(ts, (int, float)):
            continue
        slot = all_projects.setdefault(proj, {"displayName": Path(proj).name or proj, "path": proj, "lastActivity": 0})
        if ts > slot["lastActivity"]:
            slot["lastActivity"] = ts
    devices = []
    if all_projects:
        recent = sorted(all_projects.values(), key=lambda x: x["lastActivity"], reverse=True)[:8]
        devices.append({
            "id": real_username, "label": device_label,
            "projectCount": len(all_projects), "recentProjects": recent,
        })
    return {"devices": devices}

def briefing_activity() -> dict:
    today = _today_history_stats()
    return {"today": {"commandCount": today["commandCount"], "projectCount": today["projectCount"]}, "activities": []}

def _read_scheduled_tasks() -> list:
    out = []
    if not SCHEDULED_TASKS_DIR.exists():
        return out
    for d in sorted(SCHEDULED_TASKS_DIR.iterdir()):
        if not d.is_dir():
            continue
        skill_md = d / "SKILL.md"
        meta = {}
        updated_at = None
        if skill_md.exists():
            meta = _parse_frontmatter(_safe_read(skill_md, 4000))
            try:
                updated_at = int(skill_md.stat().st_mtime * 1000)
            except Exception:
                updated_at = None
        out.append({
            "id": d.name, "title": meta.get("name", d.name),
            "name": meta.get("name", d.name),
            "description": meta.get("description", ""),
            "updatedAt": updated_at,
        })
    return out

def _read_tasks() -> list:
    out = []
    if not TASKS_DIR.exists():
        return out
    device = _detect_device_info()["label"]
    for d in sorted(TASKS_DIR.iterdir()):
        if not d.is_dir():
            continue
        task_id = d.name
        is_uuid = bool(_UUID_RE.match(task_id))
        kind = "agent" if is_uuid else "named"
        subtasks = []
        try:
            for f in sorted(d.glob("*.json")):
                try:
                    data = json.loads(_safe_read(f))
                    if isinstance(data, dict):
                        subtasks.append({
                            "id": data.get("id", f.stem),
                            "subject": data.get("subject", ""),
                            "description": (data.get("description") or "")[:200],
                            "status": data.get("status", "pending"),
                        })
                except Exception:
                    continue
        except Exception:
            pass
        total = len(subtasks)
        completed = sum(1 for s in subtasks if s["status"] == "completed")
        try:
            updated_at = int(d.stat().st_mtime * 1000)
        except Exception:
            updated_at = None
        out.append({
            "id": task_id, "kind": kind,
            "teamName": task_id if not is_uuid else "",
            "totalCount": total, "completedCount": completed,
            "lockActive": (d / ".lock").exists(),
            "device": device, "updatedAt": updated_at, "subtasks": subtasks,
        })
    return out

def briefing_schedule() -> dict:
    return {"scheduled": _read_scheduled_tasks(), "tasks": _read_tasks()}

def briefing_projects_summary() -> dict:
    by_project: dict = {}
    for entry in _iter_history_recent(limit_lines=5000):
        proj = entry.get("project")
        ts = entry.get("timestamp")
        if not proj or not isinstance(ts, (int, float)):
            continue
        display = (entry.get("display") or "").strip()
        slot = by_project.setdefault(proj, {
            "displayName": Path(proj).name or proj,
            "cwd": proj,
            "device": _detect_device_info()["label"],
            "sessionCount": 0, "lastActivity": 0,
            "firstRequest": "", "firstTs": 0, "lastResult": "",
        })
        slot["sessionCount"] += 1
        if ts > slot["lastActivity"]:
            slot["lastActivity"] = ts
            if display:
                slot["lastResult"] = display[:160]
        if slot["firstTs"] == 0 or ts < slot["firstTs"]:
            slot["firstTs"] = ts
            if display:
                slot["firstRequest"] = display[:160]
    for v in by_project.values():
        v.pop("firstTs", None)
    summaries = sorted(by_project.values(), key=lambda x: x["lastActivity"], reverse=True)[:20]
    return {"summaries": summaries, "projects": list_projects().get("projects", [])}

def briefing_pending_approvals() -> dict:
    out: list = []
    if not SESSIONS_DIR.exists():
        return {"approvals": [], "pending": out}
    now_ms = int(time.time() * 1000)
    for p in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            sd = json.loads(_safe_read(p))
        except Exception:
            continue
        if not isinstance(sd, dict):
            continue
        sid = sd.get("sessionId")
        cwd = sd.get("cwd") or ""
        if not sid:
            continue
        jsonl_files = list(PROJECTS_DIR.glob(f"*/{sid}.jsonl"))
        if not jsonl_files:
            continue
        jsonl = jsonl_files[0]
        last_tool = None
        last_ts_ms = None
        try:
            text = jsonl.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()[-150:]
            for line in reversed(lines):
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                if msg.get("type") != "assistant":
                    continue
                content = (msg.get("message") or {}).get("content", [])
                if not isinstance(content, list):
                    continue
                tool_name = None
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        tool_name = c.get("name")
                        break
                if tool_name:
                    ts_str = msg.get("timestamp", "")
                    last_ts_ms = _iso_ms(ts_str)
                    last_tool = tool_name
                    break
        except Exception:
            continue
        if not last_tool:
            continue
        age_seconds = max(0, (now_ms - last_ts_ms) // 1000) if last_ts_ms else 0
        out.append({
            "project": Path(cwd).name or sid[:8],
            "tool": last_tool,
            "device": _detect_device_info()["label"],
            "ageSeconds": int(age_seconds),
            "sessionId": sid,
        })
    out.sort(key=lambda x: x["ageSeconds"])
    return {"approvals": [], "pending": out}

