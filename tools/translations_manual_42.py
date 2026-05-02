"""v2.67.0 — Y1 missing translations: permissions summary, email toggle, settings link.

Fixes Korean residue in EN/ZH detected by i18n runtime scan.
Loaded by ``tools/translations_manual.py``.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # U1 (v2.66.7) — System tab permissions summary card
    "권한 요약": "Permissions Summary",
    # U1 — link to settings/permissions tab (override bad prev translation)
    '편집은 "Settings 편집" 또는 "권한" 탭에서.': 'Edit via the "Settings" or "Permissions" tab.',
    # O1 (v2.66.1) — auth panel email toggle tooltip
    "클릭으로 이메일 표시 전환": "Click to toggle email display",
    # Y3 + Y4 (v2.66.11)
    "실행 이력 + 노드별 상세 보기": "Run history + per-node detail",
    "워크플로우를 불러올 수 없습니다": "Could not load workflow",
    "(이 세션의 대화 기록이 아직 비어있습니다)": "(this session has no recorded conversation yet)",
    "최근 도구 호출": "Recent tool calls",
    "세션 불러오는 중…": "Loading session…",
    "실제 터미널에서 이어서 열기": "Open in a real terminal",
    "실제 터미널": "Real terminal",
    "터미널 활성화": "Terminal activated",
    # Z2 (v2.66.12) — n8n-style palette
    "일치하는 노드 없음": "No matching node",
    "왼쪽 패널에서 노드 타입을 선택하세요": "Pick a node type from the left panel",
    # CC (v2.66.14) — workflow run cancel + inline mac-term + sidebar
    "실행 취소 요청됨": "Cancel requested",
    "중단": "Stop",
    "(아직 실행 결과 없음 — 워크플로우를 실행하면 여기에 표시됨)": "(no run output yet — execute the workflow to populate this)",
    # DD (v2.66.15) — sessions panel + cancel button labels
    "실행 중단": "Stop run",
    "현재 워크플로우 실행을 안전하게 중단합니다 (진행 중인 노드는 마무리)": "Cancel the current workflow run safely (in-flight nodes finish their level)",
    "워크플로우 실행 중단": "Stop workflow run",
    "실행 중·완료된 노드 세션 목록 (sessionId, 이어쓰기, 보기)": "List of running and finished node sessions (session id, resume, view)",
    "실행 세션": "Run sessions",
    "세션 없음": "No session",
    "Session ID 복사": "Copy session ID",
    "인라인 터미널 보기": "View inline terminal",
    "아직 실행된 노드가 없습니다": "No nodes have run yet",
    "건너뜀": "Skipped",
    # EE (v2.66.16) — switch-provider recovery in run-result modal
    "프로바이더 변경": "Switch provider",
    "선택…": "Select…",
    "적용 + 재실행": "Apply + re-run",
    "프로바이더를 선택하세요": "Pick a provider",
    "적용됨, 재실행합니다": "applied — re-running",
    # GG (v2.66.19) — per-node session terminate
    "이 노드의 실행 세션 종료": "Terminate this node's run session",
    "이 노드의 실행을 중단하시겠습니까? (워크플로우 전체 실행이 다음 레벨에서 멈춥니다)": "Stop this node's run? (the whole workflow run halts at the next level boundary)",
    "세션 종료 요청됨": "Termination requested",
    "진행 중인 실행이 없습니다": "No run in progress",
    # LL5
    "노드 복제됨": "Node duplicated",
    # LL6
    "노드 선택됨": "nodes selected",
}

NEW_ZH: dict[str, str] = {
    # U1 — System tab permissions summary card
    "권한 요약": "权限摘要",
    # O1 — auth panel email toggle tooltip
    "클릭으로 이메일 표시 전환": "点击切换邮件显示",
    # Y3 + Y4
    "실행 이력 + 노드별 상세 보기": "执行历史 + 各节点详情",
    "워크플로우를 불러올 수 없습니다": "无法加载工作流",
    "(이 세션의 대화 기록이 아직 비어있습니다)": "(该会话尚无对话记录)",
    "최근 도구 호출": "最近的工具调用",
    "세션 불러오는 중…": "正在加载会话…",
    "실제 터미널에서 이어서 열기": "在真实终端中继续",
    "실제 터미널": "真实终端",
    "터미널 활성화": "终端已激活",
    # Z2
    "일치하는 노드 없음": "没有匹配的节点",
    "왼쪽 패널에서 노드 타입을 선택하세요": "请从左侧面板选择节点类型",
    # CC (v2.66.14)
    "실행 취소 요청됨": "已请求取消",
    "중단": "停止",
    "(아직 실행 결과 없음 — 워크플로우를 실행하면 여기에 표시됨)": "(尚无运行结果 — 执行工作流后将显示在此)",
    # DD (v2.66.15)
    "실행 중단": "停止运行",
    "현재 워크플로우 실행을 안전하게 중단합니다 (진행 중인 노드는 마무리)": "安全停止当前工作流运行（进行中的节点将完成当前层级）",
    "워크플로우 실행 중단": "停止工作流运行",
    "실행 중·완료된 노드 세션 목록 (sessionId, 이어쓰기, 보기)": "运行中和已完成节点的会话列表（sessionId、续接、查看）",
    "실행 세션": "运行会话",
    "세션 없음": "无会话",
    "Session ID 복사": "复制会话 ID",
    "인라인 터미널 보기": "查看内嵌终端",
    "아직 실행된 노드가 없습니다": "尚未执行任何节点",
    "건너뜀": "已跳过",
    # EE (v2.66.16)
    "프로바이더 변경": "切换提供商",
    "선택…": "选择…",
    "적용 + 재실행": "应用 + 重新运行",
    "프로바이더를 선택하세요": "请选择提供商",
    "적용됨, 재실행합니다": "已应用 — 重新运行",
    # GG (v2.66.19)
    "이 노드의 실행 세션 종료": "终止此节点的运行会话",
    "이 노드의 실행을 중단하시겠습니까? (워크플로우 전체 실행이 다음 레벨에서 멈춥니다)": "停止此节点的运行？（整个工作流运行将在下一层级边界处停止）",
    "세션 종료 요청됨": "已请求终止",
    "진행 중인 실행이 없습니다": "没有正在进行的运行",
    # LL5
    "노드 복제됨": "节点已复制",
    # LL6
    "노드 선택됨": "节点已选中",
}
