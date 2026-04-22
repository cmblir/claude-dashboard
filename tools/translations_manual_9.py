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
    # 튜토리얼 노드 title / sub 값 (SVG 내부 t() 적용용)
    "리서치": "Research",
    "작성": "Writing",
    "리드": "Lead",
    "프론트": "Frontend",
    "프론트엔드": "Frontend",
    "백엔드": "Backend",
    "리뷰": "Review",
    # 튜토리얼 커서 라벨
    "🎭 페르소나": "🎭 Persona",
    "🖥️ spawn": "🖥️ Spawn",
    "🔄 resume": "🔄 Resume",
    "📋 템플릿": "📋 Templates",
    # 신규 튜토리얼 장면 10–13
    "10. 🎭 세션 하네스 — 페르소나 · 허용 도구": "10. 🎭 Session harness — persona · allowed tools",
    "노드를 선택해 우측 패널을 열면 🎭 세션 하네스 섹션에서 시스템 프롬프트(페르소나) · 추가 지시 · 허용/차단 도구를 직접 설정. 각 세션이 고유 역할로 claude CLI 호출.":
        "Select a node and open the right panel → the 🎭 Session harness section lets you set system prompt (persona), append instructions, and allowed/disallowed tools. Each session calls the claude CLI with its own role.",
    "11. 🖥️ 터미널 새 창에서 대화형 spawn": "11. 🖥️ Spawn an interactive Terminal",
    "세션 노드 우상단 🖥️ 아이콘 → Terminal 새 창에서 claude 실행. 노드에 설정된 페르소나·허용 도구·resume 모두 CLI 플래그로 전달되어 바로 대화형 세션 시작.":
        "🖥️ icon at a session node's top-right → opens Terminal with claude. The node's persona · allowed tools · resume are all forwarded as CLI flags so the interactive session starts with full context.",
    "12. 🔄 session_id 이어쓰기로 재개": "12. 🔄 Continue a session by session_id",
    "실행 결과 모달의 session_id 를 📋 복사하거나 ↪ 이어쓰기 로 다른 노드 resume 필드에 적용. 다음 실행 시 claude --resume 으로 같은 컨텍스트에서 이어서 대화.":
        "Copy a session_id from the run result modal (📋) or use ↪ Resume to paste it into another node's resume field. On next run, claude --resume continues with the same context.",
    "13. 📋 템플릿 — 팀 개발 등 원클릭 시작": "13. 📋 Templates — one-click team dev & more",
    "툴바 📋 템플릿 버튼에서 팀 개발 · 리서치 파이프라인 · 병렬 3 작업 프리셋을 선택하면 페르소나까지 채워진 완성 DAG 가 한 번에 생성. 내 워크플로우를 커스텀 템플릿으로 저장해 재사용도 가능.":
        "The 📋 Templates button offers presets — Team dev, Research pipeline, Parallel 3 tasks. Pick one and a fully-wired DAG (with personas filled in) appears instantly. You can also save your own workflow as a reusable custom template.",
    "14. 🔁 Repeat — 자동 반복 실행": "14. 🔁 Repeat — automatic re-runs",
    "메타 패널의 🔁 반복 실행 섹션에서 최대 횟수·간격·스케줄(HH:MM)·피드백 노트를 설정. 실행 완료 후 결과에 노트를 덧붙여 피드백 노드로 자동 주입하며 같은 DAG 를 여러 번 반복 — 리드가 스프린트를 N회 이어서 기획/실행/리뷰하는 자동화.":
        "Configure max iterations · interval · schedule (HH:MM) · feedback note in the meta panel's 🔁 Repeat section. After each run, the output is appended with your note and injected into the feedback node — the same DAG repeats N times. Perfect for a Lead running N consecutive sprints autonomously.",
    "🔁 피드백": "🔁 Feedback",
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
    "자동 정렬 + 화면 맞춤": "Auto-layout + fit to view",
    "템플릿": "Templates",
    "템플릿에서 새 워크플로우 만들기": "Create from template",
    "워크플로우 템플릿": "Workflow templates",
    "자주 쓰는 DAG 패턴을 원클릭으로 만듭니다. 생성 후 노드별 업무 내용을 자유롭게 수정하세요.":
        "One-click common DAG patterns. Edit each node's task after creation.",
    "템플릿에서 생성됨": "Created from template",
    "세션 하네스": "Session harness",
    "페르소나·CLAUDE.md 스타일 지시·허용 도구 등 claude CLI 에 직접 전달될 설정.":
        "Persona, CLAUDE.md-style rules, allowed tools — passed directly to the claude CLI.",
    "시스템 프롬프트 (페르소나)": "System prompt (persona)",
    "예: 너는 10년차 시니어 백엔드 엔지니어다. Node.js·PostgreSQL 전문. 보안과 성능을 우선시한다.":
        "e.g. You are a senior backend engineer with 10y experience. Specialty: Node.js & PostgreSQL. Prioritize security and performance.",
    "추가 시스템 프롬프트 (기본에 덧붙임)": "Append system prompt (added to default)",
    "기본 claude 프롬프트에 추가할 규약·제약": "Rules/constraints appended to the default claude prompt",
    "허용 도구 (쉼표 구분)": "Allowed tools (comma-separated)",
    "차단 도구 (쉼표 구분)": "Disallowed tools (comma-separated)",
    "이전 세션 이어서 (resume)": "Resume previous session",
    "연결된 이전 노드의 session_id 자동 이어받기": "Auto-inherit session_id from the connected previous node",
    "또는 session_id 직접 입력": "Or paste a session_id directly",
    "마지막 실행 session_id": "Last run session_id",
    "이어쓰기": "Resume",
    "다른 노드의 resume 필드에 붙여넣기": "Paste into another node's resume field",
    "resume 대상 노드": "Resume target node",
    "이 session_id 를 어떤 노드의 resume 필드에 넣을까요? 번호 입력:":
        "Which node's resume field should receive this session_id? Enter number:",
    "적용할 노드가 없습니다": "No node available",
    "잘못된 번호": "Invalid number",
    "에 session_id 적용됨": "— session_id applied",
    "팀 개발 (리드 + 프론트 + 백엔드)": "Team dev (Lead + Frontend + Backend)",
    "리드가 스프린트 업무를 분배 → 프론트·백엔드가 병렬 작업 → 둘 다 완료되면 리드가 리뷰 + 다음 스프린트 기획.":
        "Lead distributes sprint tasks → Frontend & Backend work in parallel → when both are done, Lead reviews and plans the next sprint.",
    "리서치 파이프라인": "Research pipeline",
    "리서처가 자료 수집 → 작가가 초안 작성 → 리뷰어가 검토 → 최종 문서.":
        "Researcher gathers sources → Writer drafts → Reviewer polishes → Final doc.",
    "단순 병렬 3 작업": "Simple parallel 3 tasks",
    "독립적인 3개 세션이 병렬 실행 → 결과 취합 → 하나의 문서로 출력.":
        "Three independent sessions run in parallel → aggregate → single output.",

    # 템플릿 내부 한글 필드 (build() 에서 t() 로 감쌌음)
    "팀 개발 스프린트": "Team Development Sprint",
    "리드 ↔ 프론트·백엔드 병렬 협업 플로우. DAG 이 두 번째 리드에서 다시 분배하며 반복 스프린트를 확장할 수 있음.":
        "Lead ↔ Frontend/Backend parallel collaboration flow. The DAG can extend into repeated sprints by having a second Lead re-distribute tasks.",
    "리드 스프린트 기획": "Lead — Sprint Planning",
    "이번 스프린트 목표와 업무 분담": "This sprint's goals and task breakdown",
    "아래 형식으로 답하라.": "Answer in this format.",
    "(프론트엔드에게 전달할 구체적 업무 지시)": "(Concrete task instructions for the frontend team)",
    "(백엔드에게 전달할 구체적 업무 지시)": "(Concrete task instructions for the backend team)",
    "너는 스프린트를 이끄는 테크 리드다. 요구사항을 명확한 실행 단위로 분해해 프론트·백엔드 팀에게 분배한다. 모호함을 남기지 말고 수용 기준까지 명시하라.":
        "You are the tech lead running the sprint. Decompose requirements into clear execution units and distribute them to frontend/backend teams. Leave no ambiguity — include acceptance criteria.",
    "프론트엔드 구현": "Frontend implementation",
    "리드 지시 중 프론트 섹션만 구현. React + TypeScript 기준. 완료된 파일 경로·핵심 변경 요약 반환.":
        "Implement only the Frontend section of the Lead's instructions. React + TypeScript. Return the completed file paths and a summary of key changes.",
    "너는 React + TypeScript + Tailwind 에 능숙한 시니어 프론트엔드 개발자다. 접근성·성능·타입 안전성을 우선시한다. 입력에서 프론트 관련 업무만 실행하고, 백엔드 섹션은 무시한다.":
        "You are a senior frontend engineer fluent in React + TypeScript + Tailwind. Prioritize accessibility, performance, and type safety. Execute only the frontend portion of the input; ignore backend sections.",
    "백엔드 구현": "Backend implementation",
    "리드 지시 중 백엔드 섹션만 구현. API · DB · 테스트까지. 완료된 파일 경로·핵심 변경 요약 반환.":
        "Implement only the Backend section of the Lead's instructions — API, DB, tests included. Return the completed file paths and a summary of key changes.",
    "너는 Node.js · PostgreSQL · REST/GraphQL 에 능숙한 시니어 백엔드 개발자다. 보안·확장성·테스트 커버리지를 우선시한다. 입력에서 백엔드 관련 업무만 실행하고, 프론트 섹션은 무시한다.":
        "You are a senior backend engineer fluent in Node.js · PostgreSQL · REST/GraphQL. Prioritize security, scalability, and test coverage. Execute only the backend portion of the input; ignore frontend sections.",
    "결과 취합": "Result Aggregate",
    "리드 리뷰 + 다음 기획": "Lead — Review + Next Planning",
    "스프린트 리뷰 및 다음 스프린트 계획": "Sprint review and next sprint plan",
    "두 결과를 보고 1) 문제/개선, 2) 다음 스프린트 업무 분담(다시 프론트·백엔드 섹션) 을 생성. 같은 포맷 유지.":
        "Looking at both outputs: 1) issues & improvements, 2) next sprint task distribution (again Frontend/Backend sections). Keep the same format.",
    "너는 스프린트를 이끄는 테크 리드다. 이전 스프린트 결과를 비판적으로 평가하고, 리스크를 식별하며, 다음 스프린트의 업무 분담을 명확히 작성한다.":
        "You are the tech lead running the sprint. Critically evaluate the previous sprint, identify risks, and clearly specify the next sprint's task distribution.",
    "최종 결과": "Final Result",

    "리서치 → 초안 → 리뷰": "Research → Draft → Review",
    "순차 3 단계 리서치 파이프라인.": "A 3-stage sequential research pipeline.",
    "주제 심층 리서치": "In-depth topic research",
    "웹·문서·기존 자료를 종합해 핵심 근거와 인용 정리.":
        "Synthesize web, docs, and existing material — compile key evidence and citations.",
    "작가 초안": "Writer Draft",
    "초안 작성": "Write draft",
    "리서치 결과를 바탕으로 독자 친화적인 초안 작성. 톤·구조 명확히.":
        "Based on the research, write a reader-friendly draft. Clear tone and structure.",
    "편집 리뷰": "Editorial Review",
    "정확성·톤·가독성·중복을 체크하고 다듬은 최종본 반환.":
        "Check accuracy, tone, readability, redundancy, and return a polished final version.",
    "최종 문서": "Final Document",

    "병렬 3 작업": "Parallel 3 Tasks",
    "시작 → 3 개 병렬 세션 → 취합 → 결과.": "Start → 3 parallel sessions → aggregate → result.",
    "작업 A": "Task A", "작업 B": "Task B", "작업 C": "Task C",

    # 커스텀 템플릿 UI
    "기본 템플릿": "Built-in templates",
    "내 커스텀 템플릿": "My custom templates",
    "저장된 커스텀 템플릿이 없습니다": "No custom templates saved",
    "현재 워크플로우를 템플릿으로 저장": "Save current workflow as template",
    "템플릿으로 저장": "Save as template",
    "템플릿 이름을 입력하세요": "Enter a template name",
    "예: 내 리뷰 플로우": "e.g. My review flow",
    "템플릿 설명 (선택)": "Template description (optional)",
    "이 템플릿이 무엇인지 한두 줄로 적어주세요. 비워도 됩니다.":
        "Briefly describe what this template is for. Can be empty.",
    "커스텀 템플릿 저장됨": "Custom template saved",
    "커스텀 템플릿 삭제": "Delete custom template",
    "이 커스텀 템플릿을 삭제할까요?": "Delete this custom template?",
    "복제": "copy",

    # Repeat 기능
    "반복 실행": "Repeat",
    "활성": "Enabled",
    "반복 실행 활성": "Enable repeat",
    "피드백 노트": "Feedback note",
    "버전 정보": "Version",
    "잠시만요~! 결과를 불러오고 있어요": "Just a moment~ loading the answer",
    "🤔 좋은 답을 고르는 중…": "🤔 Picking a good answer…",
    "💡 관련 탭을 찾고 있어요": "💡 Finding the right tab",
    "⚡ 거의 다 왔어요!": "⚡ Almost there!",
    "🎯 정리해서 알려드릴게요": "🎯 I'll wrap it up for you",
    "최근 변경 이력 (CHANGELOG.md)": "Recent changes (CHANGELOG.md)",
    "이 결과를 기반으로 다음 스프린트 업무를 프론트/백엔드 형식으로 기획해줘. 실현 가능성과 우선순위를 명확히.":
        "Based on this result, plan the next sprint tasks in the Frontend/Backend format. Clarify feasibility and priorities.",
    "실행 완료 후 결과를 피드백 노드의 입력으로 주입하며 반복. DAG 는 수정 없이 같은 흐름을 여러 번 돌림.":
        "After each run, inject the result into a feedback node's input and repeat. The DAG itself stays unchanged.",
    "최대 반복 횟수": "Max iterations",
    "반복 사이 대기 (초)": "Wait between iterations (s)",
    "스케줄 (시간대 내에서만 실행)": "Schedule (run only within time window)",
    "시작 시각": "Start time",
    "종료 시각": "End time",
    "피드백 노트 (반복 시 이전 결과에 덧붙여 피드백 노드로 주입)":
        "Feedback note (appended to previous output and injected at each iteration)",
    "예: 이 결과를 기반으로 다음 액션 기획을 해줘. 실현 가능성과 우선순위를 명확히.":
        "e.g. Based on this result, plan the next actions. Clarify feasibility and priorities.",
    "피드백 대상 노드 (비우면 자동: start 다음 세션)":
        "Feedback target node (auto = first session after start)",
    "자동 선택": "Auto",
    "최종 반복": "Final iteration",
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

    # v2.1 신규: AI 프로바이더 / 멀티 AI
    "AI 프로바이더": "AI providers",
    "API 키 삭제 완료": "API key deleted",
    "Claude · GPT · Gemini · Ollama · Codex 등 멀티 AI 프로바이더 관리":
        "Manage multi-AI providers (Claude · GPT · Gemini · Ollama · Codex)",
    "Claude/GPT/Gemini/Ollama/Codex 멀티 AI — API 키 · CLI 감지 · 폴백 체인 · 연결 테스트":
        "Multi-AI (Claude/GPT/Gemini/Ollama/Codex) — API keys · CLI detect · fallback chain · connection test",
    "🖥️ CLI 프로바이더 (로컬)": "🖥️ CLI providers (local)",
    "⌨️ 직접 입력": "⌨️ Manual entry",
    "환경 변수(OPENAI_API_KEY 등)가 이미 설정되어 있으면 자동 감지됩니다. 여기서 추가로 설정할 수 있습니다.":
        "Environment variables (e.g., OPENAI_API_KEY) are auto-detected. You can also configure them here.",
    "노드의 Assignee 를 claude:opus, openai:gpt-4.1, ollama:qwen2.5 등으로 지정하면 각 노드가 다른 AI 로 실행됩니다":
        "Set each node's Assignee to claude:opus, openai:gpt-4.1, ollama:qwen2.5, etc. and every node will run on a different AI",
    "같은 프롬프트를 병렬로 3개 AI 에 보내고 결과를 합치는 멀티 AI 비교 워크플로우.":
        "A multi-AI comparison workflow that sends the same prompt to 3 AIs in parallel and merges the results.",

    # v2.1 신규: 신규 노드 타입 (http/transform/variable/subworkflow/embedding/loop/retry/error_handler/merge/delay)
    "HTTP 요청": "HTTP request",
    "외부 REST API 호출. GET/POST/PUT + 헤더 + 응답 JSON 경로 추출.":
        "Call an external REST API. GET/POST/PUT + headers + JSON path extraction on the response.",
    "요청 Body (POST/PUT 전용": "Request Body (POST/PUT only",
    "텍스트/JSON 변환. 템플릿 치환 · JSON 경로 추출 · regex 치환 · 결합. 코드 실행 없이 데이터 가공.":
        "Text/JSON transform. Template substitution · JSON path extraction · regex replace · concatenation. Shape data without executing code.",
    "입력 값을 변수 이름에 바인딩. 후속 노드에서 참조. 기본값 설정 가능.":
        "Bind the input to a variable name for downstream nodes to reference. Default value supported.",
    "다른 워크플로우를 호출하고 결과를 받는 노드. 워크플로우 재사용 가능.":
        "A node that invokes another workflow and returns its result. Enables workflow reuse.",
    "텍스트를 벡터로 변환. Ollama bge-m3, OpenAI text-embedding-3 등 임베딩 모델 사용. RAG/검색 파이프라인 구축용.":
        "Convert text to vectors via embedding models (Ollama bge-m3, OpenAI text-embedding-3, etc.). For building RAG/search pipelines.",
    "JSON (벡터 포함)": "JSON (with vector)",
    "루프": "Loop",
    "반복 처리 노드. for_each(리스트 순회) · count(횟수 반복) · while(조건 반복) 모드 지원. 입력을 분할하여 각 항목에 동일 흐름을 적용.":
        "Iteration node. Supports for_each (iterate list) · count (fixed reps) · while (condition). Splits input to apply the same flow to every item.",
    "실패 시 자동 재시도. 최대 재시도 횟수 · 백오프 간격 · 배수를 설정하여 일시적 오류를 자동 복구.":
        "Auto-retry on failure. Configure max attempts · backoff interval · multiplier to recover from transient errors.",
    "에러 처리 전략 노드. skip(무시) · default(기본값 반환) · route(다른 노드로 분기) 모드로 워크플로우 안정성 확보.":
        "Error-handling strategy node. Use skip (ignore) · default (fallback value) · route (branch to another node) to harden workflow stability.",
    "여러 병렬 경로를 합류. all/any/count 모드": "Merge parallel paths. Modes: all/any/count",
    "딜레이": "Delay",
    "지정 시간 대기 후 통과. 고정/랜덤 딜레이": "Wait a specified time, then pass through. Fixed or random delay.",

    # v2.1 신규: 기타 UI
    "채팅 전송": "Send chat",
    "사이드바 열기/닫기": "Toggle sidebar",
    "설정 메뉴 열기": "Open settings menu",
    "개발": "Dev",
    "커스텀": "Custom",
    "패턴": "Pattern",
    "템플릿 (": "Template (",
    "플레이스홀더로 이전 노드 출력 주입.": "Inject previous node output via placeholders.",
    "로 이전 출력 참조)": " to reference previous output)",
    "치환)": "substitution)",
    "✓ 성공 (": "✓ Success (",
    "[숫자]": "[number]",

    # extractor false positives (code/comments) — map to English-only text to keep en.json Korean-free
    ").replace(/[^a-zA-Z0-9가-힣_-]/g": ").replace(/[^a-zA-Z0-9_-]/g",
    "/* 비용 API 미지원 시 조용히 무시 */": "/* silently ignored when cost API is unsupported */",
    "const _KO_RE = /[가-힣]/": "const _KO_RE = /<korean-range>/",

    # settings — 테마 (v2.1.3: 기존 Midnight/Forest/Sunset 하드코딩 → data-i18n 적용)
    "settings.midnight": "Midnight",
    "settings.forest": "Forest",
    "settings.sunset": "Sunset",
    # 한글 text 키 — runtime text-based 번역 경로 대응 (data-i18n 외 텍스트 노드 스캐너)
    "미드나잇": "Midnight",

    # v2.2.0 — CLI 설치/로그인 UI
    "설치": "Install",
    "로그인": "Log in",
    "설치 완료": "Installed",
    "설치 시작": "Start install",
    "설치 스크립트": "Install script",
    "설치 실패": "Install failed",
    "로그인 실패": "Login failed",
    "CLI 설치": "Install CLI",
    "설치 시 터미널 창이 열립니다": "A terminal window will open for installation",
    "이미 설치되어 있습니다": "Already installed",
    "이 도구는 로그인이 필요하지 않습니다": "This tool does not require login",
    "설치가 감지되었습니다 — 새로고침합니다": "Installation detected — refreshing",
    "터미널 창이 열리고 설치 명령이 실행됩니다. 계속할까요?":
        "A terminal window will open and the install command will run. Continue?",
    "터미널에서 설치가 진행 중입니다. 완료 후 새로고침하세요.":
        "Installation is running in the terminal. Refresh after it completes.",
    "터미널에서 로그인 창이 열렸습니다": "A login window has opened in the terminal",
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
    "리서치": "研究",
    "작성": "撰写",
    "리드": "Lead",
    "프론트": "前端",
    "프론트엔드": "前端",
    "백엔드": "后端",
    "리뷰": "评审",
    "🎭 페르소나": "🎭 人设",
    "🖥️ spawn": "🖥️ 启动",
    "🔄 resume": "🔄 继续",
    "📋 템플릿": "📋 模板",
    "10. 🎭 세션 하네스 — 페르소나 · 허용 도구": "10. 🎭 会话配置 — 人设 · 允许工具",
    "노드를 선택해 우측 패널을 열면 🎭 세션 하네스 섹션에서 시스템 프롬프트(페르소나) · 추가 지시 · 허용/차단 도구를 직접 설정. 각 세션이 고유 역할로 claude CLI 호출.":
        "选中节点并打开右侧面板，在 🎭 会话配置 中设置系统提示词（人设）· 追加指令 · 允许/禁止工具。每个会话以独立角色调用 claude CLI。",
    "11. 🖥️ 터미널 새 창에서 대화형 spawn": "11. 🖥️ 在终端新窗口启动交互会话",
    "세션 노드 우상단 🖥️ 아이콘 → Terminal 새 창에서 claude 실행. 노드에 설정된 페르소나·허용 도구·resume 모두 CLI 플래그로 전달되어 바로 대화형 세션 시작.":
        "点击会话节点右上角 🖥️ → 在 Terminal 新窗口启动 claude。节点上设置的人设、允许工具、resume 都通过 CLI 标志传递，立即开始交互会话。",
    "12. 🔄 session_id 이어쓰기로 재개": "12. 🔄 通过 session_id 继续会话",
    "실행 결과 모달의 session_id 를 📋 복사하거나 ↪ 이어쓰기 로 다른 노드 resume 필드에 적용. 다음 실행 시 claude --resume 으로 같은 컨텍스트에서 이어서 대화.":
        "从运行结果弹窗复制 session_id（📋）或使用 ↪ 继续 将其写入其他节点的 resume 字段。下次运行 claude --resume 将在相同上下文中继续对话。",
    "13. 📋 템플릿 — 팀 개발 등 원클릭 시작": "13. 📋 模板 — 团队开发等一键生成",
    "툴바 📋 템플릿 버튼에서 팀 개발 · 리서치 파이프라인 · 병렬 3 작업 프리셋을 선택하면 페르소나까지 채워진 완성 DAG 가 한 번에 생성. 내 워크플로우를 커스텀 템플릿으로 저장해 재사용도 가능.":
        "工具栏的 📋 模板按钮提供预设：团队开发、研究流水线、并行 3 任务。选择后一次性生成含人设的完整 DAG。也可将自己的工作流保存为可复用的自定义模板。",
    "14. 🔁 Repeat — 자동 반복 실행": "14. 🔁 Repeat — 自动循环执行",
    "메타 패널의 🔁 반복 실행 섹션에서 최대 횟수·간격·스케줄(HH:MM)·피드백 노트를 설정. 실행 완료 후 결과에 노트를 덧붙여 피드백 노드로 자동 주입하며 같은 DAG 를 여러 번 반복 — 리드가 스프린트를 N회 이어서 기획/실행/리뷰하는 자동화.":
        "在元数据面板的 🔁 重复执行 中配置最大次数 · 间隔 · 计划 (HH:MM) · 反馈备注。每次运行后将输出附加备注并注入反馈节点，同一 DAG 重复 N 次 — 适合让 Lead 自动连续执行 N 个冲刺的规划/执行/复盘。",
    "🔁 피드백": "🔁 反馈",
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
    "자동 정렬 + 화면 맞춤": "自动布局 + 适配视图",
    "템플릿": "模板",
    "템플릿에서 새 워크플로우 만들기": "从模板创建工作流",
    "워크플로우 템플릿": "工作流模板",
    "자주 쓰는 DAG 패턴을 원클릭으로 만듭니다. 생성 후 노드별 업무 내용을 자유롭게 수정하세요.":
        "一键创建常用 DAG 模式。创建后可自由修改每个节点的任务。",
    "템플릿에서 생성됨": "已从模板创建",
    "세션 하네스": "会话配置",
    "페르소나·CLAUDE.md 스타일 지시·허용 도구 등 claude CLI 에 직접 전달될 설정.":
        "人设、CLAUDE.md 风格指令、允许的工具等 — 直接传递给 claude CLI。",
    "시스템 프롬프트 (페르소나)": "系统提示词（人设）",
    "예: 너는 10년차 시니어 백엔드 엔지니어다. Node.js·PostgreSQL 전문. 보안과 성능을 우선시한다.":
        "例：你是 10 年经验的资深后端工程师。专长 Node.js 与 PostgreSQL。优先考虑安全与性能。",
    "추가 시스템 프롬프트 (기본에 덧붙임)": "追加系统提示词（附加到默认）",
    "기본 claude 프롬프트에 추가할 규약·제약": "在默认 claude 提示词上追加的规则/约束",
    "허용 도구 (쉼표 구분)": "允许的工具（逗号分隔）",
    "차단 도구 (쉼표 구분)": "禁止的工具（逗号分隔）",
    "이전 세션 이어서 (resume)": "继续之前的会话 (resume)",
    "연결된 이전 노드의 session_id 자동 이어받기": "自动继承上游节点的 session_id",
    "또는 session_id 직접 입력": "或直接粘贴 session_id",
    "마지막 실행 session_id": "上次运行的 session_id",
    "이어쓰기": "继续",
    "다른 노드의 resume 필드에 붙여넣기": "粘贴到其他节点的 resume 字段",
    "resume 대상 노드": "resume 目标节点",
    "이 session_id 를 어떤 노드의 resume 필드에 넣을까요? 번호 입력:":
        "将此 session_id 写入哪个节点的 resume？请输入序号：",
    "적용할 노드가 없습니다": "无可用节点",
    "잘못된 번호": "无效序号",
    "에 session_id 적용됨": " — 已应用 session_id",
    "팀 개발 (리드 + 프론트 + 백엔드)": "团队开发（Lead + 前端 + 后端）",
    "리드가 스프린트 업무를 분배 → 프론트·백엔드가 병렬 작업 → 둘 다 완료되면 리드가 리뷰 + 다음 스프린트 기획.":
        "Lead 分配冲刺任务 → 前端、后端并行 → 双方完成后 Lead 复盘并规划下一个冲刺。",
    "리서치 파이프라인": "研究流水线",
    "리서처가 자료 수집 → 작가가 초안 작성 → 리뷰어가 검토 → 최종 문서.":
        "Researcher 收集资料 → Writer 撰稿 → Reviewer 审校 → 最终文档。",
    "단순 병렬 3 작업": "简单并行 3 任务",
    "독립적인 3개 세션이 병렬 실행 → 결과 취합 → 하나의 문서로 출력.":
        "三个独立会话并行执行 → 汇总 → 输出单一文档。",

    "팀 개발 스프린트": "团队开发冲刺",
    "리드 ↔ 프론트·백엔드 병렬 협업 플로우. DAG 이 두 번째 리드에서 다시 분배하며 반복 스프린트를 확장할 수 있음.":
        "Lead ↔ 前端·后端并行协作流程。DAG 可在第二个 Lead 再次分配，从而扩展为重复冲刺。",
    "리드 스프린트 기획": "Lead — 冲刺规划",
    "이번 스프린트 목표와 업무 분담": "本次冲刺的目标与任务分配",
    "아래 형식으로 답하라.": "按以下格式回答。",
    "(프론트엔드에게 전달할 구체적 업무 지시)": "（给前端的具体任务指令）",
    "(백엔드에게 전달할 구체적 업무 지시)": "（给后端的具体任务指令）",
    "너는 스프린트를 이끄는 테크 리드다. 요구사항을 명확한 실행 단위로 분해해 프론트·백엔드 팀에게 분배한다. 모호함을 남기지 말고 수용 기준까지 명시하라.":
        "你是领导冲刺的 Tech Lead。将需求拆解为明确的执行单元，分发给前端·后端团队。不要留下模糊地带，并注明验收标准。",
    "프론트엔드 구현": "前端实现",
    "리드 지시 중 프론트 섹션만 구현. React + TypeScript 기준. 완료된 파일 경로·핵심 변경 요약 반환.":
        "仅实现 Lead 指令中的前端部分。使用 React + TypeScript。返回已完成的文件路径与关键变更摘要。",
    "너는 React + TypeScript + Tailwind 에 능숙한 시니어 프론트엔드 개발자다. 접근성·성능·타입 안전성을 우선시한다. 입력에서 프론트 관련 업무만 실행하고, 백엔드 섹션은 무시한다.":
        "你是精通 React + TypeScript + Tailwind 的资深前端工程师。优先考虑可访问性、性能、类型安全。只执行输入中前端相关的任务，忽略后端部分。",
    "백엔드 구현": "后端实现",
    "리드 지시 중 백엔드 섹션만 구현. API · DB · 테스트까지. 완료된 파일 경로·핵심 변경 요약 반환.":
        "仅实现 Lead 指令中的后端部分，包括 API · DB · 测试。返回已完成的文件路径与关键变更摘要。",
    "너는 Node.js · PostgreSQL · REST/GraphQL 에 능숙한 시니어 백엔드 개발자다. 보안·확장성·테스트 커버리지를 우선시한다. 입력에서 백엔드 관련 업무만 실행하고, 프론트 섹션은 무시한다.":
        "你是精通 Node.js · PostgreSQL · REST/GraphQL 的资深后端工程师。优先考虑安全、可扩展性、测试覆盖率。只执行输入中后端相关的任务，忽略前端部分。",
    "결과 취합": "结果汇总",
    "리드 리뷰 + 다음 기획": "Lead — 复盘 + 下一轮规划",
    "스프린트 리뷰 및 다음 스프린트 계획": "冲刺复盘与下一冲刺计划",
    "두 결과를 보고 1) 문제/개선, 2) 다음 스프린트 업무 분담(다시 프론트·백엔드 섹션) 을 생성. 같은 포맷 유지.":
        "查看两个结果：1) 问题与改进，2) 下一冲刺的任务分配（再次按前端·后端分节）。保持相同格式。",
    "너는 스프린트를 이끄는 테크 리드다. 이전 스프린트 결과를 비판적으로 평가하고, 리스크를 식별하며, 다음 스프린트의 업무 분담을 명확히 작성한다.":
        "你是领导冲刺的 Tech Lead。批判性评估上一次冲刺结果，识别风险，并清晰书写下一冲刺的任务分配。",
    "최종 결과": "最终结果",

    "리서치 → 초안 → 리뷰": "研究 → 初稿 → 评审",
    "순차 3 단계 리서치 파이프라인.": "顺序 3 阶段研究流水线。",
    "주제 심층 리서치": "主题深度研究",
    "웹·문서·기존 자료를 종합해 핵심 근거와 인용 정리.":
        "综合网络、文档和现有材料，整理关键证据与引用。",
    "작가 초안": "作者初稿",
    "초안 작성": "撰写初稿",
    "리서치 결과를 바탕으로 독자 친화적인 초안 작성. 톤·구조 명확히.":
        "基于研究结果撰写对读者友好的初稿。语气与结构要明确。",
    "편집 리뷰": "编辑评审",
    "정확성·톤·가독성·중복을 체크하고 다듬은 최종본 반환.":
        "检查准确性、语气、可读性、重复内容，返回打磨后的最终版。",
    "최종 문서": "最终文档",

    "병렬 3 작업": "并行 3 任务",
    "시작 → 3 개 병렬 세션 → 취합 → 결과.": "开始 → 3 个并行会话 → 汇总 → 结果。",
    "작업 A": "任务 A", "작업 B": "任务 B", "작업 C": "任务 C",

    "기본 템플릿": "内置模板",
    "내 커스텀 템플릿": "我的自定义模板",
    "저장된 커스텀 템플릿이 없습니다": "尚无已保存的自定义模板",
    "현재 워크플로우를 템플릿으로 저장": "将当前工作流保存为模板",
    "템플릿으로 저장": "保存为模板",
    "템플릿 이름을 입력하세요": "请输入模板名称",
    "예: 내 리뷰 플로우": "例如：我的评审流程",
    "템플릿 설명 (선택)": "模板说明（可选）",
    "이 템플릿이 무엇인지 한두 줄로 적어주세요. 비워도 됩니다.":
        "用一两句话描述这个模板是做什么的。可以留空。",
    "커스텀 템플릿 저장됨": "已保存自定义模板",
    "커스텀 템플릿 삭제": "删除自定义模板",
    "이 커스텀 템플릿을 삭제할까요?": "要删除此自定义模板吗？",
    "복제": "副本",

    "반복 실행": "重复执行",
    "활성": "启用",
    "반복 실행 활성": "启用重复执行",
    "피드백 노트": "反馈备注",
    "버전 정보": "版本信息",
    "잠시만요~! 결과를 불러오고 있어요": "请稍等~ 正在加载结果",
    "🤔 좋은 답을 고르는 중…": "🤔 正在挑选合适的回答…",
    "💡 관련 탭을 찾고 있어요": "💡 正在查找相关标签",
    "⚡ 거의 다 왔어요!": "⚡ 快好了！",
    "🎯 정리해서 알려드릴게요": "🎯 马上整理告诉你",
    "최근 변경 이력 (CHANGELOG.md)": "近期变更 (CHANGELOG.md)",
    "이 결과를 기반으로 다음 스프린트 업무를 프론트/백엔드 형식으로 기획해줘. 실현 가능성과 우선순위를 명확히.":
        "基于此结果，按前端/后端格式规划下一冲刺的任务，明确可行性与优先级。",
    "실행 완료 후 결과를 피드백 노드의 입력으로 주입하며 반복. DAG 는 수정 없이 같은 흐름을 여러 번 돌림.":
        "运行结束后，将结果作为反馈节点的输入注入并重复执行。DAG 本身不变。",
    "최대 반복 횟수": "最大重复次数",
    "반복 사이 대기 (초)": "重复间隔（秒）",
    "스케줄 (시간대 내에서만 실행)": "计划（仅在时间段内运行）",
    "시작 시각": "开始时间",
    "종료 시각": "结束时间",
    "피드백 노트 (반복 시 이전 결과에 덧붙여 피드백 노드로 주입)":
        "反馈备注（每次重复附加到上次结果并注入反馈节点）",
    "예: 이 결과를 기반으로 다음 액션 기획을 해줘. 실현 가능성과 우선순위를 명확히.":
        "例：基于此结果规划下一步行动，明确可行性与优先级。",
    "피드백 대상 노드 (비우면 자동: start 다음 세션)":
        "反馈目标节点（留空 = 自动：start 后的第一个 session）",
    "자동 선택": "自动",
    "최종 반복": "最终迭代",
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

    # v2.1 신규: AI 프로바이더 / 멀티 AI
    "AI 프로바이더": "AI 提供商",
    "API 키 삭제 완료": "API 密钥已删除",
    "Claude · GPT · Gemini · Ollama · Codex 등 멀티 AI 프로바이더 관리":
        "管理多 AI 提供商（Claude · GPT · Gemini · Ollama · Codex）",
    "Claude/GPT/Gemini/Ollama/Codex 멀티 AI — API 키 · CLI 감지 · 폴백 체인 · 연결 테스트":
        "多 AI（Claude/GPT/Gemini/Ollama/Codex）— API 密钥 · CLI 检测 · 回退链 · 连接测试",
    "🖥️ CLI 프로바이더 (로컬)": "🖥️ CLI 提供商（本地）",
    "⌨️ 직접 입력": "⌨️ 手动输入",
    "환경 변수(OPENAI_API_KEY 등)가 이미 설정되어 있으면 자동 감지됩니다. 여기서 추가로 설정할 수 있습니다.":
        "已设置的环境变量（如 OPENAI_API_KEY）会自动检测，也可以在此处额外设置。",
    "노드의 Assignee 를 claude:opus, openai:gpt-4.1, ollama:qwen2.5 등으로 지정하면 각 노드가 다른 AI 로 실행됩니다":
        "将节点的 Assignee 指定为 claude:opus、openai:gpt-4.1、ollama:qwen2.5 等，每个节点就会在不同的 AI 上运行",
    "같은 프롬프트를 병렬로 3개 AI 에 보내고 결과를 합치는 멀티 AI 비교 워크플로우.":
        "将同一提示并行发送到 3 个 AI 并合并结果的多 AI 比较工作流。",

    # v2.1 신규: 신규 노드 타입
    "HTTP 요청": "HTTP 请求",
    "외부 REST API 호출. GET/POST/PUT + 헤더 + 응답 JSON 경로 추출.":
        "调用外部 REST API。GET/POST/PUT + 请求头 + 响应 JSON 路径提取。",
    "요청 Body (POST/PUT 전용": "请求 Body（仅 POST/PUT",
    "텍스트/JSON 변환. 템플릿 치환 · JSON 경로 추출 · regex 치환 · 결합. 코드 실행 없이 데이터 가공.":
        "文本/JSON 转换。模板替换 · JSON 路径提取 · 正则替换 · 合并。无需执行代码即可处理数据。",
    "입력 값을 변수 이름에 바인딩. 후속 노드에서 참조. 기본값 설정 가능.":
        "将输入值绑定到变量名，供后续节点引用。支持设置默认值。",
    "다른 워크플로우를 호출하고 결과를 받는 노드. 워크플로우 재사용 가능.":
        "调用其他工作流并接收结果的节点，支持工作流复用。",
    "텍스트를 벡터로 변환. Ollama bge-m3, OpenAI text-embedding-3 등 임베딩 모델 사용. RAG/검색 파이프라인 구축용.":
        "使用嵌入模型（Ollama bge-m3、OpenAI text-embedding-3 等）将文本转换为向量。用于构建 RAG/检索流水线。",
    "JSON (벡터 포함)": "JSON（含向量）",
    "루프": "循环",
    "반복 처리 노드. for_each(리스트 순회) · count(횟수 반복) · while(조건 반복) 모드 지원. 입력을 분할하여 각 항목에 동일 흐름을 적용.":
        "迭代节点。支持 for_each（遍历列表）· count（按次数重复）· while（按条件循环）。拆分输入以对每个元素应用相同流程。",
    "실패 시 자동 재시도. 최대 재시도 횟수 · 백오프 간격 · 배수를 설정하여 일시적 오류를 자동 복구.":
        "失败时自动重试。通过设置最大重试次数 · 退避间隔 · 倍数自动恢复暂时性错误。",
    "에러 처리 전략 노드. skip(무시) · default(기본값 반환) · route(다른 노드로 분기) 모드로 워크플로우 안정성 확보.":
        "错误处理策略节点。使用 skip（忽略）· default（返回默认值）· route（分支到其他节点）模式提升工作流稳定性。",
    "여러 병렬 경로를 합류. all/any/count 모드": "合并多条并行路径。模式：all/any/count",
    "딜레이": "延迟",
    "지정 시간 대기 후 통과. 고정/랜덤 딜레이": "等待指定时间后通过。固定或随机延迟。",

    # v2.1 신규: 기타 UI
    "채팅 전송": "发送聊天",
    "사이드바 열기/닫기": "切换侧边栏",
    "설정 메뉴 열기": "打开设置菜单",
    "개발": "开发",
    "커스텀": "自定义",
    "패턴": "模式",
    "템플릿 (": "模板（",
    "플레이스홀더로 이전 노드 출력 주입.": "通过占位符注入前一个节点的输出。",
    "로 이전 출력 참조)": " 以引用之前输出）",
    "치환)": "替换）",
    "✓ 성공 (": "✓ 成功（",
    "[숫자]": "[数字]",

    # extractor false positives (code/comments)
    ").replace(/[^a-zA-Z0-9가-힣_-]/g": ").replace(/[^a-zA-Z0-9_-]/g",
    "/* 비용 API 미지원 시 조용히 무시 */": "/* 不支持成本 API 时静默忽略 */",
    "const _KO_RE = /[가-힣]/": "const _KO_RE = /<korean-range>/",

    # settings — 主题 (v2.1.3)
    "settings.midnight": "午夜",
    "settings.forest": "森林",
    "settings.sunset": "日落",
    # 한글 text 키 — runtime text-based 번역 경로 대응
    "미드나잇": "午夜",

    # v2.2.0 — CLI 安装/登录 UI
    "설치": "安装",
    "로그인": "登录",
    "설치 완료": "已安装",
    "설치 시작": "开始安装",
    "설치 스크립트": "安装脚本",
    "설치 실패": "安装失败",
    "로그인 실패": "登录失败",
    "CLI 설치": "安装 CLI",
    "설치 시 터미널 창이 열립니다": "安装时将打开终端窗口",
    "이미 설치되어 있습니다": "已安装",
    "이 도구는 로그인이 필요하지 않습니다": "此工具无需登录",
    "설치가 감지되었습니다 — 새로고침합니다": "检测到安装 — 正在刷新",
    "터미널 창이 열리고 설치 명령이 실행됩니다. 계속할까요?":
        "将打开终端窗口并执行安装命令。是否继续？",
    "터미널에서 설치가 진행 중입니다. 완료 후 새로고침하세요.":
        "终端中正在安装。完成后请刷新。",
    "터미널에서 로그인 창이 열렸습니다": "已在终端中打开登录窗口",
}
