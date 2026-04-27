"""v2.41.0 — Agent Teams + Project Detail subagent activity timeline.

Adds EN + ZH translations for the Agents-tab Teams section and the
"Recent sub-agent activity" panel inside the project detail modal.
Imported by translations_manual.py.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # Agent Teams section header / actions
    "에이전트 팀":                 "Agent Teams",
    "자주 같이 쓰는 에이전트들을 묶어 한 번에 spawn — 예: Frontend Crew = ui-designer + frontend-dev + code-reviewer":
        "Bundle the agents you spawn together — e.g. Frontend Crew = ui-designer + frontend-dev + code-reviewer",
    "새 팀":                       "New team",
    "로딩…":                       "Loading…",
    "아직 팀이 없습니다. 우측 상단 ＋ 새 팀 으로 만들어보세요.":
        "No teams yet. Use ＋ New team in the top-right to create one.",
    "에이전트가 디스크에 없음":     "Agent not found on disk",
    "명 디스크에 없음":            "missing on disk",
    "Spawn":                       "Spawn",
    "팀 로드 실패":                "Failed to load team",
    "팀 로드 실패: ":              "Team load failed: ",

    # Editor modal
    "팀 편집":                     "Edit team",
    "팀 이름":                     "Team name",
    "예: Frontend Crew":           "e.g. Frontend Crew",
    "멤버":                        "Members",
    "사용 가능한 에이전트가 없습니다": "No available agents",
    "팀 이름이 필요합니다":        "Team name is required",
    "최소 한 명의 에이전트가 필요합니다": "At least one agent is required",
    "팀 생성 완료":                "Team created",
    "팀 업데이트 완료":            "Team updated",
    "이 팀을 삭제할까요? (멤버 에이전트는 그대로 유지됩니다)":
        "Delete this team? (Member agents are preserved.)",
    "삭제 완료":                   "Deleted",
    "삭제 실패: ":                 "Delete failed: ",

    # Spawn flow
    "팀 Spawn":                    "Team Spawn",
    "각 멤버를 어떻게 띄울지 복사·실행": "Copy / run the per-member commands",
    "실행 가능한 멤버 없음":       "No runnable members",
    "건너뛴 멤버":                 "Skipped members",
    "Spawn 실패: ":                "Spawn failed: ",

    # Project Detail — sub-agent activity timeline
    "최근 서브에이전트 활동":      "Recent sub-agent activity",
    "이 프로젝트에서 서브에이전트 위임 기록 없음":
        "No sub-agent delegations recorded for this project",
    "위임":                        "delegations",
    "CLI":                         "CLI",
    "Terminal 에서 세션 재개 중…": "Resuming session in Terminal…",
    "CLI 실행 실패: ":             "CLI launch failed: ",
}

NEW_ZH: dict[str, str] = {
    "에이전트 팀":                 "代理团队",
    "자주 같이 쓰는 에이전트들을 묶어 한 번에 spawn — 예: Frontend Crew = ui-designer + frontend-dev + code-reviewer":
        "把经常一起使用的代理打包一次启动 — 例：Frontend Crew = ui-designer + frontend-dev + code-reviewer",
    "새 팀":                       "新建团队",
    "로딩…":                       "加载中…",
    "아직 팀이 없습니다. 우측 상단 ＋ 새 팀 으로 만들어보세요.":
        "尚未创建团队。点击右上角 ＋ 新建团队 来创建。",
    "에이전트가 디스크에 없음":     "代理在磁盘上不存在",
    "명 디스크에 없음":            "个在磁盘上缺失",
    "Spawn":                       "启动",
    "팀 로드 실패":                "加载团队失败",
    "팀 로드 실패: ":              "加载团队失败：",

    "팀 편집":                     "编辑团队",
    "팀 이름":                     "团队名称",
    "예: Frontend Crew":           "例：Frontend Crew",
    "멤버":                        "成员",
    "사용 가능한 에이전트가 없습니다": "没有可用的代理",
    "팀 이름이 필요합니다":        "需要团队名称",
    "최소 한 명의 에이전트가 필요합니다": "至少需要一个代理",
    "팀 생성 완료":                "团队已创建",
    "팀 업데이트 완료":            "团队已更新",
    "이 팀을 삭제할까요? (멤버 에이전트는 그대로 유지됩니다)":
        "删除此团队吗？(成员代理将保留)",
    "삭제 완료":                   "已删除",
    "삭제 실패: ":                 "删除失败：",

    "팀 Spawn":                    "团队启动",
    "각 멤버를 어떻게 띄울지 복사·실행": "复制 / 执行每个成员的命令",
    "실행 가능한 멤버 없음":       "没有可执行的成员",
    "건너뛴 멤버":                 "已跳过的成员",
    "Spawn 실패: ":                "启动失败：",

    "최근 서브에이전트 활동":      "最近子代理活动",
    "이 프로젝트에서 서브에이전트 위임 기록 없음":
        "此项目没有子代理委派记录",
    "위임":                        "委派",
    "CLI":                         "CLI",
    "Terminal 에서 세션 재개 중…": "正在 Terminal 中恢复会话…",
    "CLI 실행 실패: ":             "CLI 启动失败：",
}
