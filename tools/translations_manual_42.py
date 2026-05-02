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
}
