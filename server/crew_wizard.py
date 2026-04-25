"""Crew Wizard — generates a Planner/Personas/Slack/Obsidian workflow from
a single form submission.

Pattern produced (left → right):

    Start ──▶ Planner ──▶ [Persona1, Persona2, …] ──▶ Aggregate ──▶
              ▲                                                    │
              │                                                    ▼
              ╰────── (loop via repeat.feedbackNodeId) ◀── SlackApproval
                                                                   │
                                                                   ▼
                                                           ObsidianLog ──▶ Output

Iteration is implemented by the existing workflow `repeat` mechanism — the
feedback note + previous final output are injected back into the planner each
cycle. This keeps the engine simple and lets us reuse the proven loop path.

Autonomy modes:
- "admin_gate"   : Slack approval gate added; workflow stops on reject/timeout
                   unless `autonomousFallback=approve` (the default).
- "autonomous"   : Slack node still posts a status message but `onTimeout` is
                   forced to "approve" so it never blocks past `timeoutSeconds`.
- "no_slack"     : Slack node omitted entirely; pure local crew + Obsidian.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Any, Optional

from .logger import log


_PROJECT_RE = re.compile(r"^[A-Za-z0-9 _\-./]{1,80}$")


def _nid(prefix: str = "n-") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _eid() -> str:
    return f"e-{int(time.time()*1000)}-{uuid.uuid4().hex[:4]}"


def _validate(form: dict) -> Optional[str]:
    if not isinstance(form, dict):
        return "bad form"
    project = (form.get("project") or "").strip()
    if not project or not _PROJECT_RE.match(project):
        return "project must be A-Za-z0-9 with optional space _ - . /"
    personas = form.get("personas") or []
    if not isinstance(personas, list) or not personas:
        return "at least one persona is required"
    if len(personas) > 8:
        return "max 8 personas (keep crews focused)"
    for i, p in enumerate(personas):
        if not isinstance(p, dict):
            return f"persona[{i}] must be an object"
        role = (p.get("role") or "").strip()
        model = (p.get("model") or "").strip()
        if not role:
            return f"persona[{i}].role required"
        if not model:
            return f"persona[{i}].model required"
    autonomy = form.get("autonomy") or "admin_gate"
    if autonomy not in ("admin_gate", "autonomous", "no_slack"):
        return "autonomy must be admin_gate | autonomous | no_slack"
    iters = int(form.get("maxIterations") or 3)
    if iters < 1 or iters > 20:
        return "maxIterations must be 1..20"
    return None


def build_crew_workflow(form: dict) -> dict:
    """Return a workflow dict ready to feed into `api_workflow_save`.

    Form schema:
      {
        project: str,                # required (file-safe name)
        goal: str,                   # high-level objective for the planner
        plannerModel: str,           # e.g. "claude:opus", "gemini:gemini-2.5-pro"
        personas: [                  # 1..8 entries
          { role: str, model: str, focus: str?, agentRole: str? }
        ],
        autonomy: "admin_gate" | "autonomous" | "no_slack",
        slackChannel: str,           # required if autonomy != "no_slack"
        slackTimeoutSeconds: int,    # default 300 (admin_gate) / 60 (autonomous)
        vaultPath: str,              # required (Obsidian vault under $HOME)
        maxIterations: int,          # 1..20, default 3
        feedbackNote: str,           # optional override
        cwd: str?,                   # optional working dir for sessions
      }

    Returns the workflow dict (NOT yet saved). Caller passes it to
    `api_workflow_save`.
    """
    project = form["project"].strip()
    goal = (form.get("goal") or "").strip()
    planner_model = (form.get("plannerModel") or "claude:opus").strip()
    personas = form["personas"]
    autonomy = form.get("autonomy") or "admin_gate"
    slack_channel = (form.get("slackChannel") or "").strip()
    slack_timeout = int(form.get("slackTimeoutSeconds")
                        or (300 if autonomy == "admin_gate" else 60))
    vault_path = (form.get("vaultPath") or "").strip()
    max_iter = int(form.get("maxIterations") or 3)
    feedback_note = (form.get("feedbackNote") or "").strip() or (
        "이전 사이클의 보고를 검토하고, 미해결 항목과 새로 발견된 리스크를 "
        "우선순위에 반영해 다음 단계 업무를 페르소나별로 다시 분배하세요."
    )
    cwd = (form.get("cwd") or "").strip()

    # ── Layout (left to right, top to bottom) ──
    X = {"start": 80, "plan": 280, "persona": 520, "agg": 760,
         "slack": 980, "obs": 1180, "out": 1380}
    persona_y_step = 110
    persona_top = 80

    nodes: list[dict] = []
    edges: list[dict] = []

    n_start = _nid("n-")
    n_plan = _nid("n-")
    n_agg = _nid("n-")
    n_obs = _nid("n-")
    n_out = _nid("n-")

    # 1. Start
    nodes.append({
        "id": n_start, "type": "start", "x": X["start"], "y": 200,
        "title": "시작", "data": {},
    })

    # 2. Planner
    plan_subject = goal or f"{project} — 작업 계획 수립"
    plan_desc = (
        f"당신은 '{project}' 프로젝트의 기획자입니다. 아래 입력을 바탕으로:\n"
        f"  1) 목표를 단계별 작업으로 쪼개고\n"
        f"  2) 각 작업을 어떤 페르소나에 맡길지 결정하며\n"
        f"  3) 전달 시 명확한 컨텍스트와 완료 기준을 함께 적습니다.\n"
        f"\n페르소나 목록: " + ", ".join(p["role"] for p in personas) + "\n"
        f"\n출력 형식: 각 페르소나별 지시 블록을 '### <role>' 헤딩으로 구분하세요."
    )
    nodes.append({
        "id": n_plan, "type": "session", "x": X["plan"], "y": 200,
        "title": "🧭 기획자",
        "data": {
            "subject":     plan_subject,
            "description": plan_desc,
            "assignee":    planner_model,
            "agentRole":   "planner",
            "cwd":         cwd,
            "inputsMode":  "concat",
            "continueFromPrev": True,
        },
    })
    edges.append({"id": _eid(), "from": n_start, "to": n_plan,
                  "fromPort": "out", "toPort": "in"})

    # 3. Personas — fan out from planner
    persona_ids: list[str] = []
    n = len(personas)
    total_h = (n - 1) * persona_y_step
    base_y = max(80, 200 - total_h // 2)
    for i, p in enumerate(personas):
        nid = _nid("n-")
        persona_ids.append(nid)
        focus = (p.get("focus") or "").strip()
        agent_role = (p.get("agentRole") or p["role"]).strip()
        desc_lines = [
            f"당신은 '{p['role']}' 역할의 페르소나입니다.",
            "기획자가 전달한 지시 블록 중 본인 역할에 해당하는 부분만 수행하세요.",
            "완료 후에는 (1) 무엇을 했는지 (2) 한계/막힌 지점 (3) 기획자에게 권하는 다음 단계를"
            " 명확히 정리해 보고하세요.",
        ]
        if focus:
            desc_lines.append(f"\n중점 영역: {focus}")
        nodes.append({
            "id": nid, "type": "subagent",
            "x": X["persona"], "y": base_y + i * persona_y_step,
            "title": f"👤 {p['role']}",
            "data": {
                "subject":     f"{p['role']} — 작업 수행",
                "description": "\n".join(desc_lines),
                "assignee":    p["model"],
                "agentRole":   agent_role,
                "cwd":         cwd,
                "inputsMode":  "concat",
            },
        })
        edges.append({"id": _eid(), "from": n_plan, "to": nid,
                      "fromPort": "out", "toPort": "in"})

    # 4. Aggregate — gather persona reports
    nodes.append({
        "id": n_agg, "type": "aggregate", "x": X["agg"], "y": 200,
        "title": "🧩 보고 취합", "data": {"mode": "concat"},
    })
    for pid in persona_ids:
        edges.append({"id": _eid(), "from": pid, "to": n_agg,
                      "fromPort": "out", "toPort": "in"})

    # 5. Slack approval (optional)
    last_before_obs = n_agg
    n_slack = ""
    if autonomy != "no_slack":
        n_slack = _nid("n-")
        on_timeout = "approve" if autonomy == "autonomous" else "default"
        msg_template = (
            f":memo: *{project}* — 사이클 보고가 도착했습니다.\n"
            f"_(승인 :white_check_mark: / 거부 :x: / 자유답장으로 다음 지시 입력)_"
        )
        default_out = (
            "타임아웃 — 자율 판단으로 계속 진행. 기획자에게 \"이전 보고를 그대로 반영해 "
            "다음 단계 진행\"이라고 지시하세요."
        ) if autonomy == "autonomous" else (
            "타임아웃 — 관리자 응답을 받지 못해 흐름 중단."
        )
        nodes.append({
            "id": n_slack, "type": "slack_approval",
            "x": X["slack"], "y": 200,
            "title": "🛂 어드민 게이트",
            "data": {
                "channel":             slack_channel,
                "messageTemplate":     msg_template,
                "timeoutSeconds":      slack_timeout,
                "pollIntervalSeconds": 5,
                "onTimeout":           on_timeout,
                "defaultOutput":       default_out,
                "includeInput":        True,
            },
        })
        edges.append({"id": _eid(), "from": n_agg, "to": n_slack,
                      "fromPort": "out", "toPort": "in"})
        last_before_obs = n_slack

    # 6. Obsidian log
    nodes.append({
        "id": n_obs, "type": "obsidian_log", "x": X["obs"], "y": 200,
        "title": "📝 옵시디언 기록",
        "data": {
            "vaultPath":   vault_path,
            "project":     project,
            "heading":     "crew cycle",
            "tagsCsv":     "lazyclaude,crew",
            "passThrough": True,
            "defaultOutput": "",
        },
    })
    edges.append({"id": _eid(), "from": last_before_obs, "to": n_obs,
                  "fromPort": "out", "toPort": "in"})

    # 7. Output
    nodes.append({
        "id": n_out, "type": "output", "x": X["out"], "y": 200,
        "title": "📤 결과", "data": {"exportTo": ""},
    })
    edges.append({"id": _eid(), "from": n_obs, "to": n_out,
                  "fromPort": "out", "toPort": "in"})

    wf = {
        "name":        f"Crew · {project}",
        "description": (
            f"Wizard로 생성된 페르소나 크루 워크플로우. "
            f"기획자({planner_model}) → {n}명 페르소나 → 보고 취합"
            + (" → Slack 승인" if autonomy != "no_slack" else "")
            + " → Obsidian 기록.\nautonomy: " + autonomy
        ),
        "nodes":   nodes,
        "edges":   edges,
        "viewport": {"panX": 0.0, "panY": 0.0, "zoom": 1.0},
        "repeat": {
            "enabled":         max_iter > 1,
            "maxIterations":   max_iter,
            "intervalSeconds": 0,
            "scheduleEnabled": False,
            "scheduleStart":   "",
            "scheduleEnd":     "",
            "feedbackNote":    feedback_note,
            "feedbackNodeId":  n_plan,
        },
        "notify": {"slack": "", "discord": ""},
        "policy": {"tokenBudgetTotal": 0, "onBudgetExceeded": "stop",
                   "fallbackProvider": ""},
    }
    return wf


def api_crew_create(body: dict) -> dict:
    """POST /api/wizard/crew/create — validate + build + save."""
    err = _validate(body or {})
    if err:
        return {"ok": False, "error": err}

    autonomy = body.get("autonomy") or "admin_gate"
    if autonomy != "no_slack" and not (body.get("slackChannel") or "").strip():
        return {"ok": False, "error": "slackChannel required when autonomy != no_slack"}
    if not (body.get("vaultPath") or "").strip():
        return {"ok": False, "error": "vaultPath required (Obsidian vault under $HOME)"}

    try:
        wf = build_crew_workflow(body)
    except Exception as e:
        log.exception("crew build failed")
        return {"ok": False, "error": f"build failed: {e}"}

    # Late import to keep this module importable even if workflows.py changes shape.
    from .workflows import api_workflow_save
    saved = api_workflow_save(wf)
    if not saved.get("ok"):
        return {"ok": False, "error": saved.get("error") or "save failed"}

    return {
        "ok":         True,
        "id":         saved["id"],
        "name":       wf["name"],
        "nodeCount":  len(wf["nodes"]),
        "edgeCount":  len(wf["edges"]),
        "autonomy":   autonomy,
        "personas":   len(body.get("personas") or []),
    }


def api_crew_preview(body: dict) -> dict:
    """POST /api/wizard/crew/preview — build but do NOT save (UI dry-run)."""
    err = _validate(body or {})
    if err:
        return {"ok": False, "error": err}
    try:
        wf = build_crew_workflow(body)
    except Exception as e:
        return {"ok": False, "error": f"build failed: {e}"}
    return {
        "ok":     True,
        "preview": {
            "name":      wf["name"],
            "nodes":     [{"id": n["id"], "type": n["type"], "title": n["title"],
                           "x": n["x"], "y": n["y"]} for n in wf["nodes"]],
            "edges":     [{"from": e["from"], "to": e["to"]} for e in wf["edges"]],
            "repeat":    wf["repeat"],
        },
    }
