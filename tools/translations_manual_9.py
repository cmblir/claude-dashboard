"""워크플로우 에디터(workflows) 탭 — 신규 UI/백엔드 문구 EN/ZH 번역."""

NEW_EN = {
    # NAV
    "워크플로우": "Workflows",
    "세션 노드를 DAG 로 연결해 업무 흐름 설계": "Connect session nodes as a DAG to design task flows",

    # 탭 헤더/서브
    "🔀 워크플로우": "🔀 Workflows",
    "세션 노드를 DAG 로 연결해 업무 흐름 설계. 포트를 드래그해 화살표로 연결.":
        "Design task flows by connecting session nodes as a DAG. Drag ports to wire arrows.",

    # 리스트 / 생성
    "새 워크플로우": "New workflow",
    "워크플로우 이름": "Workflow name",
    "워크플로우 없음": "No workflows",
    "워크플로우를 선택하거나 생성하세요": "Pick or create a workflow",
    "워크플로우를 선택하세요": "Select a workflow",
    "워크플로우를 먼저 선택하세요": "Select a workflow first",
    "이 워크플로우를 삭제할까요?": "Delete this workflow?",
    "노드": "nodes",
    "연결": "edges",

    # 툴바
    "시작 노드": "Start node",
    "세션 노드": "Session node",
    "서브에이전트 노드": "Subagent node",
    "취합 노드": "Aggregate node",
    "분기 노드": "Branch node",
    "결과 노드": "Output node",

    # 상태
    "저장": "Save",
    "저장됨": "Saved",
    "저장 실패": "Save failed",
    "실행": "Run",
    "실행 시작됨": "Run started",
    "실행 실패": "Run failed",
    "실행 결과": "Run result",
    "실행 이력": "Run history",
    "이력": "History",
    "실행 이력 없음": "No run history",
    "최근 50건. 클릭하면 상세 결과": "Last 50 runs. Click for details",
    "노드 추가": "Add node",
    "새 노드 추가": "Add a new node",
    "새 노드": "New node",
    "노드 편집": "Edit node",
    "카테고리": "Category",
    "카테고리를 선택하세요": "Please select a category",
    "위에서 카테고리를 먼저 선택하세요": "Select a category above first",
    "편집": "Edit",
    "선택된 노드": "Selected node",
    "워크플로우 메타": "Workflow meta",
    "(업무 없음)": "(no task)",
    "상단 ＋ 노드 추가 를 누르거나 기존 노드를 더블클릭해 편집하세요":
        "Click ＋ Add node above or double-click a node to edit",
    "노드 추가됨": "Node added",
    "시작 노드는 추가 입력이 없습니다. 워크플로우 진입점이 됩니다.":
        "The start node takes no input — it is just the workflow entry point.",
    "내리기": "Minimize",
    "펼치기": "Expand",
    "카테고리별 설명": "What each category means",
    "사용법": "How it works",
    "사용법 보기": "Show how it works",
    "워크플로우 사용법": "Workflow walkthrough",
    "이전": "Previous",
    "다음": "Next",
    "1. 새 워크플로우 만들기": "1. Create a new workflow",
    "좌측 사이드바의 ＋ 새 워크플로우 버튼을 눌러 빈 캔버스를 엽니다. 커서가 ＋ 를 클릭하는 동작을 보여줍니다.":
        "Click ＋ New workflow in the left sidebar to open an empty canvas. The cursor shows where to click.",
    "2. 🚀 시작 노드 자동 배치": "2. Start node placed automatically",
    "워크플로우의 진입점인 🚀 시작 노드가 캔버스 왼쪽에 자동 배치됩니다.":
        "The 🚀 Start node (entry point) is auto-placed on the left of the canvas.",
    "3. 🗂️ 세션 + 🤝 서브에이전트 추가": "3. Add 🗂️ Session and 🤝 Subagent",
    "＋ 노드 추가 → 카테고리 선택 창에서 🗂️ 세션과 🤝 서브에이전트를 추가. subject(업무) · 모델 · 역할을 입력.":
        "＋ Add node → pick 🗂️ Session and 🤝 Subagent in the category window. Fill subject · model · role.",
    "4. 🧩 취합 + 🔀 분기 추가": "4. Add 🧩 Aggregate and 🔀 Branch",
    "🧩 취합 노드는 여러 입력을 concat/JSON 으로 합침. 🔀 분기 노드는 조건 문자열 일치 여부로 Y/N 포트를 활성화.":
        "🧩 Aggregate merges multiple inputs (concat/JSON). 🔀 Branch activates Y/N port based on a condition string.",
    "5. 포트 드래그로 화살표 연결": "5. Connect by dragging ports",
    "주황 out-port 에서 보라 in-port 로 드래그하면 베지어 곡선 + 방향 화살표가 자동 생성. DAG 사이클은 즉시 거부.":
        "Drag from orange out-port to purple in-port — a bezier curve with an arrow appears. DAG cycles are rejected on the spot.",
    "6. 📤 결과 노드 + DAG 완성": "6. 📤 Output node + complete DAG",
    "📤 결과 노드를 추가하고 분기 → 결과로 마무리. 이 노드가 워크플로우 종착지. exportTo 경로를 지정하면 파일로 저장.":
        "Add 📤 Output and wire Branch → Output. This is the end of the workflow. Set exportTo to also write a file.",
    "7. 🎯 맞춤으로 전체 한눈에": "7. 🎯 Fit everything into view",
    "캔버스 우하단 🎯 맞춤 버튼 → 모든 노드 bounding box 가 보이도록 pan/zoom 자동 조정. 복잡한 워크플로우도 한 번에 정렬.":
        "Click 🎯 Fit at the canvas bottom-right — pan/zoom auto-adjusts to fit every node. One tap tames even a busy flow.",
    "8. ▶ 실행 → 순차 자동 처리": "8. ▶ Run → sequential automation",
    "상단 ▶ 실행 → DAG 토폴로지 순서로 각 노드가 보라색 펄스(실행 중) → 녹색(완료)로 전환. 세션 노드는 claude -p 로 subprocess 실행.":
        "Top ▶ Run → nodes pulse purple (running) then turn green (ok) in topological order. Session nodes run via `claude -p` subprocesses.",
    "9. 완료 → 결과 모달 · 터미널 · 파일": "9. Done → result modal · Terminal · file",
    "완료된 노드는 녹색 테두리. 결과 모달에 노드별 출력 미리보기. 세션 노드 🖥️ 아이콘으로 Terminal 새 창에서 대화형 세션도 시작 가능. 📜 이력 으로 과거 실행 재조회.":
        "Completed nodes have a green border. The result modal previews each node's output. A session node's 🖥️ icon spawns an interactive Terminal, and 📜 History replays past runs.",
    "＋ 새 워크플로우": "＋ New workflow",
    "＋ 노드": "＋ Add",
    "🎯 맞춤": "🎯 Fit",
    "▶ 실행": "▶ Run",
    "메타": "Meta",
    "메타 패널 보이기/가리기": "Show/hide meta panel",
    "가리기": "Hide",
    "DAG 의 진입점. 입력 없음 — 워크플로우의 시작점. 각 워크플로우에 1개만 두는 것이 일반적.":
        "Entry point of the DAG. No input — where the workflow begins. Usually one per workflow.",
    "가상 Claude 세션. subject(업무) · description(상세) · 모델 · cwd 를 설정하면 실행 시 claude -p 로 자동 실행되거나, 노드의 🖥️ 버튼으로 Terminal 새 창에서 대화형으로 열 수 있음.":
        "Virtual Claude session. Configure subject · description · model · cwd — runs via claude -p on Run, or opens an interactive Terminal window via the node's 🖥️ button.",
    "특정 역할(researcher · writer · reviewer 등)을 부여한 전문 세션. session 과 동일하지만 agentRole 필드로 페르소나를 명시해 전문성을 강화.":
        "Specialized session with a specific role (researcher · writer · reviewer, etc.). Same as session but uses agentRole to pin a persona.",
    "여러 입력을 하나로 합치는 노드. concat(텍스트 이어붙이기) 또는 json(배열) 모드. 병렬로 수집한 결과를 하나로 모을 때 사용.":
        "Merges multiple inputs into one. concat (text join) or json (array) mode. Use to combine parallel results.",
    "조건에 따라 Y / N 두 포트 중 하나만 활성화. 조건 문자열이 입력에 포함되면 Y, 아니면 N 으로 흐름이 분기.":
        "Activates only Y or N port based on condition. If the condition string is present in the input, Y fires; otherwise N.",
    "워크플로우의 종착지. 이전 노드의 출력을 최종 결과로 저장. exportTo 에 경로(~/ 하위) 지정 시 파일로 저장됨.":
        "Final destination of the workflow. Saves the previous node's output. If exportTo is set (under ~/), also writes to a file.",
    "변경사항 있음": "Unsaved changes",
    "생성됨": "Created",
    "삭제됨": "Deleted",
    "실패": "Failed",
    "로드 실패": "Load failed",

    # 인스펙터
    "노드를 선택하면 편집 패널이 표시됩니다": "Select a node to edit it here",
    "노드를 클릭하면 편집 폼이 표시됩니다": "Click a node to edit its fields",
    "이름": "Name",
    "설명": "Description",
    "제목": "Title",
    "업무 (subject)": "Task (subject)",
    "이 세션이 수행할 업무 한 줄": "One-line task for this session",
    "설명 (description)": "Description",
    "상세 지시·제약·출력 형식": "Detailed instructions · constraints · output format",
    "모델": "Model",
    "에이전트 역할": "Agent role",
    "작업 디렉토리 (cwd)": "Working directory (cwd)",
    "입력 합치기 모드": "Inputs merge mode",
    "이어붙이기 (concat)": "Concatenate (concat)",
    "첫 입력만 (first)": "First input only (first)",
    "JSON 배열 (json)": "JSON array (json)",
    "조건 (입력에 포함되면 Y 포트 활성)": "Condition (Y port activates if input contains)",
    "합치기 모드": "Merge mode",
    "텍스트 concat": "Text concat",
    "JSON 배열": "JSON array",
    "파일로 저장 (선택, ~/ 하위만)": "Save to file (optional, under ~/)",

    # 버튼
    "새 Claude 세션 spawn": "Spawn new Claude session",
    "Claude 세션 시작됨": "Claude session started",
    "세션 생성 실패": "Failed to spawn session",
    "삭제": "Delete",
    "닫기": "Close",

    # 에러/경고
    "같은 노드에 연결할 수 없습니다": "Cannot connect a node to itself",
    "이미 연결되어 있습니다": "Already connected",
    "순환 연결은 허용되지 않습니다": "Cycles are not allowed",
    "결과 없음": "No results",

    # 라벨(노드 타입)
    "시작": "Start",
    "세션": "Session",
    "서브에이전트": "Subagent",
    "취합": "Aggregate",
    "분기": "Branch",
    "결과": "Output",

    # 기타
    "검색…": "Search…",
    "맞춤": "Fit",
    "화면에 맞춤": "Fit to screen",
    "이름을 입력하세요": "Enter a name",
    "예: README 작성 파이프라인": "e.g. README writing pipeline",
    "생성": "Create",
    "삭제 확인": "Delete confirmation",
    "규칙을 입력하세요 (예: Bash(git status:*))": "Enter a rule (e.g. Bash(git status:*))",
    "디자인 스캔 디렉토리 추가": "Add design scan directory",
    "추가로 스캔할 디렉토리 절대경로 (홈 디렉토리 내):":
        "Absolute path to scan (under home):",
    "허용 규칙 추가": "Add allow rule",
    "차단 규칙 추가": "Add deny rule",
    "전역 에이전트 삭제": "Delete global agent",
    "파일이 제거됩니다.": "The file will be removed.",
    "에이전트 삭제": "Delete agent",
    "플러그인 훅 삭제": "Delete plugin hook",
    "훅 삭제": "Delete hook",
    "MCP 서버 제거": "Remove MCP server",
    "제거": "Remove",
    "프로젝트 MCP 제거": "Remove project MCP",
    "마켓플레이스 제거": "Remove marketplace",
    "출력 스타일 삭제": "Delete output style",
    "TODO 삭제": "Delete TODO",
    "로그아웃": "Log out",
    "입력": "Input",
    "확인": "Confirm",
    "취소": "Cancel",
}

NEW_ZH = {
    # NAV
    "워크플로우": "工作流",
    "세션 노드를 DAG 로 연결해 업무 흐름 설계": "以 DAG 连接会话节点，设计任务流程",

    # 탭 헤더/서브
    "🔀 워크플로우": "🔀 工作流",
    "세션 노드를 DAG 로 연결해 업무 흐름 설계. 포트를 드래그해 화살표로 연결.":
        "以 DAG 连接会话节点设计任务流程。拖动端口连接箭头。",

    # 리스트 / 생성
    "새 워크플로우": "新建工作流",
    "워크플로우 이름": "工作流名称",
    "워크플로우 없음": "暂无工作流",
    "워크플로우를 선택하거나 생성하세요": "请选择或创建工作流",
    "워크플로우를 선택하세요": "请选择工作流",
    "워크플로우를 먼저 선택하세요": "请先选择工作流",
    "이 워크플로우를 삭제할까요?": "要删除此工作流吗？",
    "노드": "节点",
    "연결": "连线",

    # 툴바
    "시작 노드": "起始节点",
    "세션 노드": "会话节点",
    "서브에이전트 노드": "子代理节点",
    "취합 노드": "聚合节点",
    "분기 노드": "分支节点",
    "결과 노드": "结果节点",

    # 상태
    "저장": "保存",
    "저장됨": "已保存",
    "저장 실패": "保存失败",
    "실행": "运行",
    "실행 시작됨": "已开始运行",
    "실행 실패": "运行失败",
    "실행 결과": "运行结果",
    "실행 이력": "运行历史",
    "이력": "历史",
    "실행 이력 없음": "暂无运行历史",
    "최근 50건. 클릭하면 상세 결과": "最近 50 条。点击查看详情",
    "노드 추가": "添加节点",
    "새 노드 추가": "添加新节点",
    "새 노드": "新节点",
    "노드 편집": "编辑节点",
    "카테고리": "类别",
    "카테고리를 선택하세요": "请选择类别",
    "위에서 카테고리를 먼저 선택하세요": "请先在上方选择类别",
    "편집": "编辑",
    "선택된 노드": "已选节点",
    "워크플로우 메타": "工作流元数据",
    "(업무 없음)": "(无任务)",
    "상단 ＋ 노드 추가 를 누르거나 기존 노드를 더블클릭해 편집하세요":
        "点击上方「＋ 添加节点」或双击现有节点进行编辑",
    "노드 추가됨": "已添加节点",
    "시작 노드는 추가 입력이 없습니다. 워크플로우 진입점이 됩니다.":
        "起始节点无额外输入，仅作为工作流入口。",
    "내리기": "最小化",
    "펼치기": "展开",
    "카테고리별 설명": "各类别说明",
    "사용법": "用法",
    "사용법 보기": "查看用法",
    "워크플로우 사용법": "工作流演示",
    "이전": "上一步",
    "다음": "下一步",
    "1. 새 워크플로우 만들기": "1. 创建新工作流",
    "좌측 사이드바의 ＋ 새 워크플로우 버튼을 눌러 빈 캔버스를 엽니다. 커서가 ＋ 를 클릭하는 동작을 보여줍니다.":
        "点击左侧 ＋ 新建工作流打开空白画布。光标演示点击位置。",
    "2. 🚀 시작 노드 자동 배치": "2. 自动放置 🚀 起始节点",
    "워크플로우의 진입점인 🚀 시작 노드가 캔버스 왼쪽에 자동 배치됩니다.":
        "作为入口的 🚀 起始节点自动放置在画布左侧。",
    "3. 🗂️ 세션 + 🤝 서브에이전트 추가": "3. 添加 🗂️ 会话与 🤝 子代理",
    "＋ 노드 추가 → 카테고리 선택 창에서 🗂️ 세션과 🤝 서브에이전트를 추가. subject(업무) · 모델 · 역할을 입력.":
        "＋ 添加节点 → 在类别选择窗口中添加 🗂️ 会话和 🤝 子代理。填写 subject（任务）· 模型 · 角色。",
    "4. 🧩 취합 + 🔀 분기 추가": "4. 添加 🧩 聚合与 🔀 分支",
    "🧩 취합 노드는 여러 입력을 concat/JSON 으로 합침. 🔀 분기 노드는 조건 문자열 일치 여부로 Y/N 포트를 활성화.":
        "🧩 聚合节点将多个输入通过 concat/JSON 合并。🔀 分支节点根据条件字符串激活 Y/N 端口。",
    "5. 포트 드래그로 화살표 연결": "5. 拖动端口连接箭头",
    "주황 out-port 에서 보라 in-port 로 드래그하면 베지어 곡선 + 방향 화살표가 자동 생성. DAG 사이클은 즉시 거부.":
        "从橙色 out-port 拖到紫色 in-port，自动生成贝塞尔曲线与方向箭头。循环连接会立即被拒绝。",
    "6. 📤 결과 노드 + DAG 완성": "6. 📤 结果节点 + 完成 DAG",
    "📤 결과 노드를 추가하고 분기 → 결과로 마무리. 이 노드가 워크플로우 종착지. exportTo 경로를 지정하면 파일로 저장.":
        "添加 📤 结果节点并连接 分支→结果。这是工作流终点。设置 exportTo 可同时写入文件。",
    "7. 🎯 맞춤으로 전체 한눈에": "7. 🎯 一键适配全视图",
    "캔버스 우하단 🎯 맞춤 버튼 → 모든 노드 bounding box 가 보이도록 pan/zoom 자동 조정. 복잡한 워크플로우도 한 번에 정렬.":
        "点击画布右下角 🎯 适配 — 自动 pan/zoom 将所有节点收入视图。再复杂的流程也能一键归位。",
    "8. ▶ 실행 → 순차 자동 처리": "8. ▶ 运行 → 顺序自动处理",
    "상단 ▶ 실행 → DAG 토폴로지 순서로 각 노드가 보라색 펄스(실행 중) → 녹색(완료)로 전환. 세션 노드는 claude -p 로 subprocess 실행.":
        "顶部 ▶ 运行 → 按 DAG 拓扑顺序，节点先紫色脉冲（运行中）再转绿色（完成）。会话节点通过 claude -p 子进程执行。",
    "9. 완료 → 결과 모달 · 터미널 · 파일": "9. 完成 → 结果弹窗 · 终端 · 文件",
    "완료된 노드는 녹색 테두리. 결과 모달에 노드별 출력 미리보기. 세션 노드 🖥️ 아이콘으로 Terminal 새 창에서 대화형 세션도 시작 가능. 📜 이력 으로 과거 실행 재조회.":
        "已完成节点呈绿色边框。结果弹窗预览每个节点的输出。会话节点的 🖥️ 图标可在 Terminal 新窗口启动交互会话，📜 历史 可重新查看过去运行。",
    "＋ 새 워크플로우": "＋ 新建工作流",
    "＋ 노드": "＋ 节点",
    "🎯 맞춤": "🎯 适配",
    "▶ 실행": "▶ 运行",
    "메타": "元数据",
    "메타 패널 보이기/가리기": "显示/隐藏元数据面板",
    "가리기": "隐藏",
    "DAG 의 진입점. 입력 없음 — 워크플로우의 시작점. 각 워크플로우에 1개만 두는 것이 일반적.":
        "DAG 的入口。无输入 — 工作流起点。通常每个工作流只保留一个。",
    "가상 Claude 세션. subject(업무) · description(상세) · 모델 · cwd 를 설정하면 실행 시 claude -p 로 자동 실행되거나, 노드의 🖥️ 버튼으로 Terminal 새 창에서 대화형으로 열 수 있음.":
        "虚拟 Claude 会话。设置 subject · description · 模型 · cwd；运行时通过 claude -p 自动执行，或点击节点 🖥️ 在 Terminal 新窗口中交互打开。",
    "특정 역할(researcher · writer · reviewer 등)을 부여한 전문 세션. session 과 동일하지만 agentRole 필드로 페르소나를 명시해 전문성을 강화.":
        "具有特定角色（researcher · writer · reviewer 等）的专用会话。与 session 相同，但通过 agentRole 指定角色强化专业性。",
    "여러 입력을 하나로 합치는 노드. concat(텍스트 이어붙이기) 또는 json(배열) 모드. 병렬로 수집한 결과를 하나로 모을 때 사용.":
        "将多个输入合并为一个的节点。支持 concat（文本拼接）或 json（数组）模式。用于汇总并行结果。",
    "조건에 따라 Y / N 두 포트 중 하나만 활성화. 조건 문자열이 입력에 포함되면 Y, 아니면 N 으로 흐름이 분기.":
        "根据条件仅激活 Y 或 N 端口之一。输入包含条件字符串则走 Y，否则走 N。",
    "워크플로우의 종착지. 이전 노드의 출력을 최종 결과로 저장. exportTo 에 경로(~/ 하위) 지정 시 파일로 저장됨.":
        "工作流终点。保存上一节点输出为最终结果。若设置 exportTo 路径（~/ 下）则同时写入文件。",
    "변경사항 있음": "有未保存更改",
    "생성됨": "已创建",
    "삭제됨": "已删除",
    "실패": "失败",
    "로드 실패": "加载失败",

    # 인스펙터
    "노드를 선택하면 편집 패널이 표시됩니다": "选中节点后将显示编辑面板",
    "노드를 클릭하면 편집 폼이 표시됩니다": "点击节点即可编辑其字段",
    "이름": "名称",
    "설명": "说明",
    "제목": "标题",
    "업무 (subject)": "任务 (subject)",
    "이 세션이 수행할 업무 한 줄": "此会话的一行任务",
    "설명 (description)": "说明",
    "상세 지시·제약·출력 형식": "详细指令 · 约束 · 输出格式",
    "모델": "模型",
    "에이전트 역할": "代理角色",
    "작업 디렉토리 (cwd)": "工作目录 (cwd)",
    "입력 합치기 모드": "输入合并模式",
    "이어붙이기 (concat)": "拼接 (concat)",
    "첫 입력만 (first)": "仅首个输入 (first)",
    "JSON 배열 (json)": "JSON 数组 (json)",
    "조건 (입력에 포함되면 Y 포트 활성)": "条件（输入包含该字符串则激活 Y 端口）",
    "합치기 모드": "合并模式",
    "텍스트 concat": "文本 concat",
    "JSON 배열": "JSON 数组",
    "파일로 저장 (선택, ~/ 하위만)": "保存到文件（可选，仅限 ~/ 下）",

    # 버튼
    "새 Claude 세션 spawn": "启动新的 Claude 会话",
    "Claude 세션 시작됨": "Claude 会话已启动",
    "세션 생성 실패": "会话启动失败",
    "삭제": "删除",
    "닫기": "关闭",

    # 에러/경고
    "같은 노드에 연결할 수 없습니다": "不能连接到同一节点",
    "이미 연결되어 있습니다": "已经连接",
    "순환 연결은 허용되지 않습니다": "不允许循环连接",
    "결과 없음": "暂无结果",

    # 라벨(노드 타입)
    "시작": "起始",
    "세션": "会话",
    "서브에이전트": "子代理",
    "취합": "聚合",
    "분기": "分支",
    "결과": "结果",

    # 기타
    "검색…": "搜索…",
    "맞춤": "适配",
    "화면에 맞춤": "适配视图",
    "이름을 입력하세요": "请输入名称",
    "예: README 작성 파이프라인": "例如：README 撰写流程",
    "생성": "创建",
    "삭제 확인": "删除确认",
    "규칙을 입력하세요 (예: Bash(git status:*))": "请输入规则（例：Bash(git status:*)）",
    "디자인 스캔 디렉토리 추가": "添加设计扫描目录",
    "추가로 스캔할 디렉토리 절대경로 (홈 디렉토리 내):":
        "要扫描的目录绝对路径（位于主目录下）:",
    "허용 규칙 추가": "添加允许规则",
    "차단 규칙 추가": "添加阻止规则",
    "전역 에이전트 삭제": "删除全局 agent",
    "파일이 제거됩니다.": "将删除该文件。",
    "에이전트 삭제": "删除 agent",
    "플러그인 훅 삭제": "删除插件 hook",
    "훅 삭제": "删除 hook",
    "MCP 서버 제거": "移除 MCP 服务器",
    "제거": "移除",
    "프로젝트 MCP 제거": "移除项目 MCP",
    "마켓플레이스 제거": "移除插件市场",
    "출력 스타일 삭제": "删除输出样式",
    "TODO 삭제": "删除 TODO",
    "로그아웃": "注销",
    "입력": "输入",
    "확인": "确认",
    "취소": "取消",
}
