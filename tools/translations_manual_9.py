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
}
