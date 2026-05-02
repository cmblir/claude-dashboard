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
    # LL8
    "자동 정렬 완료": "Layout aligned",
    # LL9 — shortcut help additions
    "선택 노드 복제": "Duplicate selected node",
    "전체 노드 선택": "Select all nodes",
    "인스펙터 패널 토글": "Toggle inspector panel",
    "100% 줌으로 리셋": "Reset to 100% zoom",
    "줌 인/아웃": "Zoom in / out",
    "성능 HUD 토글": "Toggle perf HUD",
    "선택 노드 10px 이동": "Move selected node 10px",
    "선택 노드 1px 이동 (정밀)": "Move selected node 1px (fine)",
    "자동 정렬": "Auto-layout",
    "캔버스 패닝": "Pan canvas",
    "커서 기준 줌": "Cursor-anchored zoom",
    "grid snap 우회": "Bypass grid snap",
    "더블클릭 (빈 영역)": "Double-click (empty area)",
    "미니맵 토글": "Toggle minimap",
    "다음 / 이전 노드 선택": "Select next / previous node",
    "선택 노드 편집창 열기": "Open editor for selected node",
    "줌 아웃": "Zoom out",
    "줌 인": "Zoom in",
    "연결 삭제": "Delete connection",
    "우클릭": "Right-click",
    "미니맵 클릭": "Click minimap",
    "노드/엣지 컨텍스트 메뉴": "Node / edge context menu",
    "해당 위치로 캔버스 이동": "Pan canvas to that location",
    "드래그로 너비 조절": "Drag to resize",
    "노드 검색 (예: fy / ses)": "Search nodes (e.g. fy / ses)",
    "이름·타입·assignee·역할 fuzzy 검색": "Fuzzy search across name / type / assignee / role",
    "검색 지우기": "Clear search",
    "이전 / 다음 워크플로우로 전환": "Switch to previous / next workflow",
    "워크플로우 실행 / 중단": "Run / stop workflow",
    # LL16 already covered: 새 노드 추가 — exists.
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
    # LL8
    "자동 정렬 완료": "已自动排列",
    # LL9
    "선택 노드 복제": "复制所选节点",
    "전체 노드 선택": "选择所有节点",
    "인스펙터 패널 토글": "切换检查面板",
    "100% 줌으로 리셋": "重置到 100% 缩放",
    "줌 인/아웃": "放大 / 缩小",
    "성능 HUD 토글": "切换性能 HUD",
    "선택 노드 10px 이동": "移动所选节点 10px",
    "선택 노드 1px 이동 (정밀)": "移动所选节点 1px（精细）",
    "자동 정렬": "自动布局",
    "캔버스 패닝": "平移画布",
    "커서 기준 줌": "光标锚定缩放",
    "grid snap 우회": "绕过网格对齐",
    "더블클릭 (빈 영역)": "双击（空白区域）",
    "미니맵 토글": "切换迷你地图",
    "다음 / 이전 노드 선택": "选择下一个 / 上一个节点",
    "선택 노드 편집창 열기": "打开所选节点的编辑器",
    "줌 아웃": "缩小",
    "줌 인": "放大",
    "연결 삭제": "删除连接",
    "우클릭": "右键单击",
    "미니맵 클릭": "单击迷你地图",
    "노드/엣지 컨텍스트 메뉴": "节点 / 连接的上下文菜单",
    "해당 위치로 캔버스 이동": "将画布平移到该位置",
    "드래그로 너비 조절": "拖动调整宽度",
    "노드 검색 (예: fy / ses)": "搜索节点（例如 fy / ses）",
    "이름·타입·assignee·역할 fuzzy 검색": "在名称 / 类型 / 执行者 / 角色中模糊搜索",
    "검색 지우기": "清除搜索",
    "이전 / 다음 워크플로우로 전환": "切换到上一个 / 下一个工作流",
    "워크플로우 실행 / 중단": "运行 / 停止工作流",
}
