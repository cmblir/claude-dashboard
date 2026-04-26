"""v2.34.x — Crew Wizard, palette categories, slack_approval/obsidian_log,
guide modal, and assorted strings that surfaced in the missing report.

This module provides NEW_EN / NEW_ZH dicts that translations_manual.py merges
into MANUAL_EN / MANUAL_ZH on every build.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # ── Sidebar / palette categories ────────────────────────────
    "AI 작업": "AI work",
    "DAG 진입점": "DAG entry point",
    "데이터 / HTTP": "Data / HTTP",
    "분기 · 루프 · 재시도 · 합류": "Branch · loop · retry · merge",
    "변환 · 변수 · 외부 호출 · 서브워크플로우": "Transform · variable · HTTP · subworkflow",
    "세션 · 페르소나 · 임베딩": "Session · persona · embedding",
    "워크플로우 종착": "Workflow terminus",
    "흐름 제어": "Flow control",
    "트리거": "Trigger",
    "연동": "Integrations",
    "기록": "Logging",
    "Slack 어드민 · Obsidian 기록": "Slack admin gate · Obsidian log",
    "카테고리 → 노드 선택": "Category → pick a node",

    # ── Crew wizard headers ─────────────────────────────────────
    "🧑‍✈️ 크루 위저드": "🧑‍✈️ Crew Wizard",
    "크루 위저드": "Crew Wizard",
    "크루 위저드 사용법": "Crew Wizard guide",
    "Zapier 식 4-스텝 폼 → 워크플로우 자동 생성": "Zapier-style 4-step form → workflow auto-generated",
    "폼만 채우면 기획자 + 페르소나 N명 + Slack 어드민 게이트 + Obsidian 기록까지 자동 생성":
        "Fill in the form: planner + N personas + Slack admin gate + Obsidian log are scaffolded for you",
    "폼만 채우면 기획자 + 페르소나 N명 + Slack 어드민 게이트 + Obsidian 기록까지 자동 생성. 워크플로우 탭에서 그대로 캔버스 편집 가능.":
        "Fill in the form: planner + N personas + Slack admin gate + Obsidian log are scaffolded for you. The result is a regular workflow you can edit on the canvas.",
    "처음이라면 사용법을 먼저 확인하세요": "First time? Open the guide first",
    "사용법은 언제든 📖 버튼으로 다시 열 수 있습니다.":
        "You can re-open this guide any time via the 📖 button.",
    "이해했습니다": "Got it",
    "이게 뭐죠?": "What is this?",
    "워크플로우 탭은 자유도가 높지만 처음엔 노드 18종을 보고 어디서 시작할지 막막합니다. 크루 위저드는 가장 흔한 패턴 —":
        "The Workflows tab is powerful but the 18 node types can feel overwhelming. The Crew Wizard distils the most common pattern —",
    "기획자가 페르소나 여러 명에게 일을 분배하고, 보고를 받아 다음 사이클을 지시하는":
        "a planner who delegates to multiple personas, then steers the next cycle from their reports",
    "구조 — 를 폼 4 스텝으로 추출해 한 번에 만들어 줍니다. 결과는 일반 워크플로우라 워크플로우 탭에서 그대로 자유 편집 가능합니다.":
        "— into 4 form steps. The output is a regular workflow you can freely edit on the canvas.",
    "생성되는 구조": "Generated structure",
    "4 스텝 가이드": "4-step guide",
    "스텝 1 · 프로젝트": "Step 1 · Project",
    "스텝 2 · 페르소나": "Step 2 · Personas",
    "스텝 3 · Slack & Obsidian": "Step 3 · Slack & Obsidian",
    "스텝 4 · 자율성": "Step 4 · Autonomy",
    "Slack 인터랙션": "Slack interaction",
    "자주 막히는 곳": "Common gotchas",
    "생성 후 다음 단계": "After generation",
    "🚀 시작": "🚀 Start",
    "🧭 기획자 (Planner — Opus 권장)": "🧭 Planner (Opus recommended)",
    "🧩 보고 취합 (Aggregate)": "🧩 Aggregate reports",
    "🛂 Slack 어드민 게이트  ← (autonomy 모드에 따라 선택적)":
        "🛂 Slack admin gate  ← (optional based on autonomy mode)",
    "📝 Obsidian 기록 (logs/YYYY-MM-DD.md)": "📝 Obsidian log (logs/YYYY-MM-DD.md)",
    "📤 결과": "📤 Output",
    "↓ ↓ ↓     (페르소나마다 병렬 분기)": "↓ ↓ ↓     (parallel fan-out per persona)",
    "└─ (loop) ──→ 다시 기획자에게 피드백 주입":
        "└─ (loop) ──→ feedback re-injected into the planner",

    # ── Wizard step labels & form ────────────────────────────────
    "프로젝트": "Project",
    "페르소나": "Personas",
    "자율성": "Autonomy",
    "자율성 모드": "Autonomy mode",
    "자율 모드": "Autonomous",
    "🤖 자율 모드": "🤖 Autonomous",
    "🛂 어드민 게이트": "🛂 Admin gate",
    "🔕 Slack 없음": "🔕 No Slack",
    "어드민 게이트": "Admin gate",
    "프로젝트 이름": "Project name",
    "프로젝트 폴더명": "Project folder name",
    "예: weekly-report": "e.g. weekly-report",
    "예: 다음주까지 신제품 출시 가이드를 작성한다 — 시장조사·초안·리뷰까지":
        "e.g. Write a launch guide for next week — research → draft → review",
    "예: Researcher(Claude Sonnet) + Builder(Gemini Pro) + Reviewer(Ollama)":
        "e.g. Researcher (Claude Sonnet) + Builder (Gemini Pro) + Reviewer (Ollama)",
    "영문/숫자/공백/_-./ 만 허용 — Obsidian 폴더와 워크플로우 이름에 그대로 사용됩니다.":
        "Alphanumeric / space / _-./ only — used as-is for the Obsidian folder and workflow name.",
    "목표 (Planner 가 받는 첫 입력)": "Goal (initial input to the planner)",
    "목표 — Planner 가 받는 첫 입력. 한 줄로 명확하게.":
        "Goal — the planner's initial input. Keep it sharp and one-line.",
    "Planner 모델": "Planner model",
    "Planner 모델 — Opus 권장. 사이클을 지휘하는 두뇌입니다.":
        "Planner model — Opus recommended. This is the brain steering each cycle.",
    "전체 사이클을 지휘하는 두뇌 — Opus 등 가장 깊이 있는 모델 권장.":
        "The brain that steers every cycle — pick the deepest model you have (Opus etc.).",
    "작업 디렉터리 (선택)": "Working directory (optional)",
    "1~8명. 같은 역할이라도 모델이 다르면 별도 페르소나로 등록 가능 — Claude · Gemini · Ollama 자유 조합.":
        "1–8 personas. Same role with different models is fine — mix Claude · Gemini · Ollama freely.",
    "1~8명. 역할 + 모델 + 중점 영역 입력.":
        "1–8 personas. Enter role + model + focus area.",
    "Claude · Gemini · Ollama 자유 조합 — 서로 다른 모델을 섞을수록 다양한 시각을 얻습니다.":
        "Mix Claude · Gemini · Ollama freely — different models bring different perspectives.",
    "역할": "Role",
    "중점 영역 (선택)": "Focus area (optional)",
    "시장조사": "Market research",
    "페르소나 추가": "Add persona",
    "최대 8명까지": "Max 8 personas",
    "최소 1명은 필요합니다": "At least one persona is required",

    # ── Slack settings + Obsidian path ──────────────────────────
    "Slack 어드민 게이트": "Slack admin gate",
    "Slack Bot Token (xoxb-…) 이 필요합니다":
        "A Slack Bot Token (xoxb-…) is required",
    "https://api.slack.com/apps 에서 봇을 만들고 chat:write, reactions:read, channels:history 권한을 부여하세요.":
        "Create a bot at https://api.slack.com/apps and grant chat:write, reactions:read, channels:history.",
    "필요한 Slack 권한: chat:write · reactions:read · channels:history (또는 groups:history)":
        "Required Slack scopes: chat:write · reactions:read · channels:history (or groups:history)",
    "Slack 봇 토큰(xoxb-…) 을 한 번만 저장 — auth.test 로 즉시 검증. 토큰은 ~/.claude-dashboard-slack.json 에 chmod 600 으로 저장.":
        "Save the bot token (xoxb-…) once — verified via auth.test, stored at ~/.claude-dashboard-slack.json with chmod 600.",
    "기본 채널 (예: C012345)": "Default channel (e.g. C012345)",
    "이 워크플로우에서 사용할 채널 ID (선택, 비우면 기본 채널 사용)":
        "Channel ID for this workflow (optional, falls back to the default)",
    "저장 + 검증": "Save + verify",
    "테스트 메시지": "Test message",
    "Slack 토큰 저장 + 검증 성공": "Slack token saved + verified",
    "Slack 인증 OK": "Slack auth OK",
    "Slack 실패": "Slack failed: ",
    "Slack 응답 대기 (초)": "Slack wait timeout (seconds)",
    "Vault 경로 (": "Vault path (",
    "HOME 하위)": "$HOME-only)",
    "HOME 하위만 허용.": "$HOME-only.",
    "HOME 하위 경로만 허용. 사이클별로 Projects/":
        "$HOME-only path. Each cycle appends to Projects/",
    "/logs/YYYY-MM-DD.md 에 사이클별로 append 됩니다.":
        "/logs/YYYY-MM-DD.md is appended every cycle.",
    "/logs/YYYY-MM-DD.md 에 append.": "/logs/YYYY-MM-DD.md (append).",
    "/logs/YYYY-MM-DD.md — 사이클마다 append.": "/logs/YYYY-MM-DD.md — appended each cycle.",
    "/logs/YYYY-MM-DD.md 에 입력을 마크다운으로 append. 사이클 보고/감사 로그용.":
        "Append the input as markdown to /logs/YYYY-MM-DD.md — for cycle reports / audit logs.",

    # ── Multi-sentence WF_NODE_TYPES desc strings (extractor only catches first sentence) ──
    "DAG 의 진입점. 입력 없음 — 워크플로우의 시작점. 각 워크플로우에 1개만 두는 것이 일반적.":
        "DAG entry point. No input — the workflow's starting node. Usually exactly one per workflow.",
    "가상 Claude 세션. subject(업무) · description(상세) · 모델 · cwd 를 설정하면 실행 시 claude -p 로 자동 실행되거나, 노드의 🖥️ 버튼으로 Terminal 새 창에서 대화형으로 열 수 있음.":
        "Virtual Claude session. Set subject (task) · description · model · cwd, then it runs via `claude -p` automatically, or click the 🖥️ button to open it interactively in a new Terminal window.",
    "특정 역할(researcher · writer · reviewer 등)을 부여한 전문 세션. session 과 동일하지만 agentRole 필드로 페르소나를 명시해 전문성을 강화.":
        "A specialised session with a role (researcher · writer · reviewer …). Same engine as `session` but with an explicit `agentRole` to lock in a persona.",
    "여러 입력을 하나로 합치는 노드. concat(텍스트 이어붙이기) 또는 json(배열) 모드. 병렬로 수집한 결과를 하나로 모을 때 사용.":
        "Combines multiple inputs into one. Modes: concat (join text) or json (array). Use to collect parallel branches into a single value.",
    "조건에 따라 Y / N 두 포트 중 하나만 활성화. 조건 문자열이 입력에 포함되면 Y, 아니면 N 으로 흐름이 분기.":
        "Activates exactly one of two ports (Y / N) by condition. If the condition string is in the input the flow goes Y, otherwise N.",
    "워크플로우의 종착지. 이전 노드의 출력을 최종 결과로 저장. exportTo 에 경로(~/ 하위) 지정 시 파일로 저장됨.":
        "Workflow terminus — saves the previous node's output as the final result. With `exportTo` set (path under ~/) it is also written to disk.",
    "외부 REST API 호출. GET/POST/PUT + 헤더 + 응답 JSON 경로 추출. {{input}} 플레이스홀더로 이전 노드 출력 주입.":
        "Call an external REST API. GET/POST/PUT + headers + JSON path extraction on the response. Use {{input}} to inject the previous node's output.",
    "텍스트/JSON 변환. 템플릿 치환 · JSON 경로 추출 · regex 치환 · 결합. 코드 실행 없이 데이터 가공.":
        "Text / JSON transform. Template substitution · JSON path extraction · regex substitution · join. Reshape data without running code.",
    "입력 값을 변수 이름에 바인딩. 후속 노드에서 참조. 기본값 설정 가능.":
        "Bind the input to a variable name. Referenced by downstream nodes. Default value supported.",
    "다른 워크플로우를 호출하고 결과를 받는 노드. 워크플로우 재사용 가능.":
        "Calls another workflow and returns its result. Lets you reuse workflows.",
    "텍스트를 벡터로 변환. Ollama bge-m3, OpenAI text-embedding-3 등 임베딩 모델 사용. RAG/검색 파이프라인 구축용.":
        "Convert text to a vector. Uses an embedding model (Ollama bge-m3, OpenAI text-embedding-3, etc.). For RAG / search pipelines.",
    "반복 처리 노드. for_each(리스트 순회) · count(횟수 반복) · while(조건 반복) 모드 지원. 입력을 분할하여 각 항목에 동일 흐름을 적용.":
        "Iteration node. Modes: for_each (over list) · count (N times) · while (until condition). Splits the input and applies the downstream flow to each item.",
    "실패 시 자동 재시도. 최대 재시도 횟수 · 백오프 간격 · 배수를 설정하여 일시적 오류를 자동 복구.":
        "Auto-retry on failure. Configure max retries · backoff interval · multiplier to recover from transient errors.",
    "에러 처리 전략 노드. skip(무시) · default(기본값 반환) · route(다른 노드로 분기) 모드로 워크플로우 안정성 확보.":
        "Error-handling strategy node. Modes: skip (ignore) · default (return a default) · route (branch elsewhere) keep workflows resilient.",
    "여러 병렬 경로를 합류. all/any/count 모드":
        "Joins multiple parallel paths. Modes: all / any / count.",
    "지정 시간 대기 후 통과. 고정/랜덤 딜레이":
        "Waits the specified time before passing through. Fixed or random delay.",
    "Slack 채널에 메시지를 올리고 ✅/❌ 반응 또는 스레드 답장을 기다림. 타임아웃 시 자동 통과/거부/중단/기본값 중 선택. 자율모드에서 어드민 개입 지점.":
        "Post to a Slack channel and wait for a ✅/❌ reaction or a thread reply. On timeout choose auto-pass / reject / abort / default. The admin intervention point in autonomous mode.",
    "Vault 의 Projects/<프로젝트>/logs/YYYY-MM-DD.md 에 입력을 마크다운으로 append. 사이클 보고/감사 로그용.":
        "Append the input as markdown to <vault>/Projects/<project>/logs/YYYY-MM-DD.md. For cycle reports / audit logs.",
    "Vault 의 Projects/": "Vault's Projects/",
    "Obsidian 기록": "Obsidian log",
    "Obsidian 쓰기 성공": "Obsidian write OK",
    "Obsidian 실패": "Obsidian failed: ",
    "두 항목 다 즉석 테스트 버튼 제공.": "Both have an instant test button.",
    "경로 테스트": "Test path",

    # ── Autonomy descriptions ───────────────────────────────────
    "매 사이클마다 Slack 으로 보고하고 ✅/❌ 응답을 기다림. 타임아웃 시 흐름 중단.":
        "Reports each cycle to Slack and waits for ✅/❌. Aborts on timeout.",
    "매 사이클마다 Slack 으로 보고하고 어드민이 승인할 때까지 대기. 타임아웃 시 흐름 중단.":
        "Reports each cycle to Slack and waits for admin approval. Aborts on timeout.",
    "Slack 알림은 보내지만 짧은 타임아웃 후 스스로 다음 사이클 진행. 어드민이 끼어들 때만 답장하면 됨.":
        "Posts a status to Slack but auto-proceeds after a short timeout. Admin only needs to reply to intervene.",
    "Slack 으로 상태 알림은 보내지만 짧은 타임아웃 후 스스로 판단해 다음 사이클 진행. 어드민이 끼어들고 싶을 때만 답장하면 됨.":
        "Posts to Slack as a status update but proceeds autonomously after a short timeout. Admin only replies to steer.",
    "Slack 노드 없이 페르소나 → Obsidian → 다음 사이클로 바로 흐름.":
        "Skips Slack — personas → Obsidian → next cycle directly.",
    "Slack 노드를 빼고 페르소나 → Aggregate → Obsidian → 다음 사이클로 바로 흐름.":
        "Skips Slack — personas → aggregate → Obsidian → next cycle.",
    "최대 사이클 수": "Max cycles",
    "최대 사이클 수 1~20. 매 사이클마다 직전 보고가 Planner 입력으로 다시 주입됩니다.":
        "Max cycles 1–20. Each cycle re-injects the previous report into the planner's input.",
    "1=한번만, 3~5 권장. 매 사이클마다 기획자에게 직전 보고가 다시 주입됩니다.":
        "1 = single shot, 3–5 recommended. Each cycle re-injects the previous report into the planner.",
    "루프 피드백 노트 (선택)": "Loop feedback note (optional)",
    "비워두면 기본값 사용": "Leave empty for the default note",
    "이전 사이클 보고를 검토하고 미해결 항목을 우선 처리…":
        "Review the previous cycle's report and prioritise unresolved items…",

    # ── Slack interaction copy ──────────────────────────────────
    "승인": "Approve",
    "승인: ✅ (white_check_mark) / 👍 / 답장에":
        "Approve: ✅ (white_check_mark) / 👍 / reply contains",
    "승인: ✅ 또는 답장에": "Approve: ✅ or reply contains",
    "approve/ok/승인": "approve / ok / approve",
    "거부: ❌ (x) / 👎 / 답장에": "Reject: ❌ (x) / 👎 / reply contains",
    "· 거부: ❌ 또는": "· Reject: ❌ or",
    "reject/거부": "reject / reject",
    "프로젝트 이름 — Obsidian 폴더명으로 그대로 사용. 영문/숫자/공백/_-./ 만.":
        "Project name — used as-is for the Obsidian folder. Alphanumeric / space / _-./ only.",
    "자유 답장 (예": "Free-form reply (e.g.",
    "Reviewer 보고를 더 깊게 다시": "Re-run the Reviewer with more depth",
    "): 다음 사이클 입력으로 사용 → 어드민이 흐름 중간에 방향 조정 가능":
        "): used as the next cycle's input → admin can steer mid-flight",
    "· 자유 답장은 다음 사이클 입력으로 사용됩니다.":
        "· A free-form reply is used as the next cycle's input.",
    "Slack 채널 ID (Cxxxx, Gxxxx, 또는 #name)": "Slack channel ID (Cxxxx, Gxxxx, or #name)",
    "C012345 또는 #ops": "C012345 or #ops",
    "메시지 템플릿": "Message template",
    "memo: 사이클 보고 도착": "memo: cycle report arrived",
    "이전 노드 출력 포함": "Include previous node output",
    "타임아웃 시 동작": "On timeout",
    "자동 승인 (계속 진행)": "Auto-approve (continue)",
    "자동 거부 (defaultOutput 사용)": "Auto-reject (use defaultOutput)",
    "defaultOutput 으로 통과": "Pass through using defaultOutput",
    "워크플로우 중단": "Abort workflow",
    "Default 출력 (거부 / 타임아웃-default 시)": "Default output (on reject / timeout-default)",
    "Slack 채널에 메시지를 올리고 ✅/❌ 반응 또는 스레드 답장을 기다림. 타임아웃 시 자동 통과/거부/중단/기본값 중 선택. 자율모드에서 어드민 개입 지점.":
        "Post to a Slack channel and wait for ✅/❌ reactions or a thread reply. On timeout choose auto-pass / reject / abort / default. The admin intervention point in autonomous mode.",
    "대신 기록할 텍스트": "Text to log instead",
    "입력을 그대로 다음 노드로 통과": "Pass input through to the next node",
    "헤딩 (선택)": "Heading (optional)",
    "태그 (콤마 구분)": "Tags (comma-separated)",

    # ── Common gotchas ──────────────────────────────────────────
    "— 스텝 3 의 토큰 저장 버튼을 눌렀는지 확인. 또는 환경변수 SLACK_BOT_TOKEN 으로 주입 가능.":
        "— make sure you pressed the Save button in Step 3, or set the SLACK_BOT_TOKEN env var.",
    "— Vault 경로가 ~/ 안에 있는지 확인. realpath 후 검증되므로 symlink 도 주의.":
        "— make sure the vault path is under ~/. realpath is checked so symlinks count.",
    "Slack 메시지가 도착하지 않음 — 봇이 채널에 초대돼 있는지 확인. 비공개 채널에는 /invite @봇이름 필요.":
        "Message never arrives — confirm the bot is in the channel. Private channels need /invite @botname.",
    "타임아웃이 너무 짧음 — 자율 모드에서도 사이클당 최소 60s 권장. admin_gate 는 5분~30분이 일반적.":
        "Timeout too short — autonomous mode still wants ≥60s per cycle. admin_gate usually wants 5–30 minutes.",
    "자동으로 워크플로우 탭으로 이동 — 캔버스에서 노드 추가/제거/연결 자유 편집":
        "Auto-redirects to the Workflows tab — add/remove/connect nodes freely on the canvas",
    "▶ 실행 버튼으로 바로 시작 · 또는 Webhook URL 로 외부 트리거 연결":
        "Hit ▶ to run immediately, or wire the Webhook URL to an external trigger",
    "실행 중에는 노드별 진행 상태가 실시간 표시 — Slack 게이트는 응답 대기 상태로 노출됨":
        "Per-node progress streams live during a run — the Slack gate shows as 'waiting'.",

    # ── Misc ─────────────────────────────────────────────────────
    "사이클": "cycles",
    "생성 미리보기": "Generation preview",
    "아직 미리보기를 생성하지 않았습니다.": "No preview generated yet.",
    "미리보기 생성 중…": "Generating preview…",
    "미설정": "Not configured",
    "워크플로우 탭으로 이동": "Open Workflows tab",
    "에디터에 미리 채워졌습니다 — 검토 후 저장하세요": "Pre-filled in the editor — review and save",
    "LazyClaude · Crew Wizard 연결 테스트": "LazyClaude · Crew Wizard connection test",
    "메시지 전송": "message sent",

    # ── Misc unrelated keys also reported as missing
    # (these popped up because extract_ko_strings caught them in other tabs)
    "감지된 이슈": "Issues found",
    "감지된 이슈 없음 — 깨끗합니다!": "No issues found — clean!",
    "검사 대상: settings.json · CLAUDE.md · settings.hooks · ~/.claude/agents · mcp.json":
        "Targets: settings.json · CLAUDE.md · settings.hooks · ~/.claude/agents · mcp.json",
    "발견된 시크릿은 rotate 후 env var 로 옮기세요.":
        "Rotate any found secrets and move them to env vars.",
    "분석은 완전히 로컬에서 수행됩니다. Claude API 호출 없음. 제안 카드는 클릭 시 해당 탭으로 이동하여 수동 저장할 수 있습니다.":
        "Analysis is fully local — no Claude API calls. Click a suggestion card to jump to the relevant tab and save manually.",
    "최근 세션에서 반복되는 패턴을 자동 추출. AI 판단 없이 통계 기반.":
        "Extract recurring patterns from recent sessions — statistics only, no AI calls.",
    "최근 30일 세션이 없습니다. Claude Code 를 한 번 이상 사용하세요.":
        "No sessions in the last 30 days. Run Claude Code at least once.",
    "아직 제안할 패턴이 충분히 누적되지 않았습니다.":
        "Not enough recurring patterns yet to make a suggestion.",
    "스캔한 세션": "Sessions scanned",
    "개 세션 중": " of",
    "최근 세션": "Recent sessions",
    "최근 50 run": "Last 50 runs",
    "개 표시. 행을 클릭하면 상세 타임라인.": " shown. Click a row for full timeline.",
    "출력물이 있는 run 이 없습니다.": "No runs with output yet.",
    "왼쪽에서 run 을 선택하세요.": "Select a run on the left.",
    "자동 추출된 제안": "Auto-extracted suggestions",
    "Tool 시퀀스": "Tool sequences",
    "반복 프롬프트": "Repeating prompts",
    "자주 쓰는 Tool": "Frequent tools",
    "세션 길이 분포": "Session length distribution",
    "Telemetry 오류 급등": "Telemetry error spikes",
    "Prompt Library 로 저장": "Save to Prompt Library",
    "ECC AgentShield 방식에서 영감": "Inspired by ECC AgentShield",
    "(없음)": "(none)",
    "(모든 권한 차단) + CSP default-src:none + 정적 필터 (script/iframe/on*/javascript: 제거).":
        "(all permissions blocked) + CSP default-src:none + static filter (strips script/iframe/on*/javascript:).",
    "— 스크립트·폼·쿠키·탐색·플러그인 전부 차단. CSP default-src:none, img-src:data 만 허용.":
        "— blocks scripts/forms/cookies/navigation/plugins. CSP default-src:none, img-src:data only.",
    "sandbox 속성 =": "sandbox attribute =",
    "워크플로우 출력물을 sandbox iframe + CSP + 정적 필터 4중 보안으로 안전하게 미리보기 — 스크립트 실행·외부 네트워크·쿠키 모두 차단.":
        "Preview workflow output safely via 4-layer hardening (sandbox iframe + CSP + static filter) — no script execution, no external network, no cookies.",
    "session 노드가 assignee 로 실패 시 선택한 프로바이더로 1회 재시도. 노드 결과에 fallbackUsed 기록.":
        "When a session node fails on its assignee, retry once with the chosen provider. fallbackUsed is recorded on the node result.",
    "실패 시 fallback 프로바이더": "Fallback provider on failure",
    "matcher (예: Bash, *, 비워두면 all)": "matcher (e.g. Bash, *, empty = all)",
    "매처": "Matcher",
    "허용 호스트": "Allowed hosts",
    "Forwarder 추가": "Add forwarder",
    "Forwarder 추가됨": "Forwarder added",
    "새 Forwarder 추가": "Add new forwarder",
    "등록된 Forwarder": "Registered forwarders",
    "등록된 forwarder 가 없습니다": "No forwarders registered",
    "이 forwarder 를 settings.json 에서 제거합니다. 계속할까요?":
        "Remove this forwarder from settings.json. Continue?",
    "forwarder 는 settings.json 의 hooks 섹션에 curl 명령으로 등록됩니다. 매 변경 시 자동 백업 생성.":
        "Forwarders are registered as curl commands in the settings.json hooks section. Every change makes a backup.",
    "Claude Code hooks 이벤트를 외부 HTTP endpoint 로 포워딩 — 화이트리스트 호스트만 허용, settings.json 자동 백업.":
        "Forward Claude Code hook events to external HTTP endpoints — whitelist only, auto-backed-up settings.json.",
    "Claude Code 세션 안에서 대시보드 기능을 호출할 수 있게 LazyClaude 를 stdio MCP 서버로 등록합니다":
        "Register LazyClaude as a stdio MCP server so dashboard features can be called from inside Claude Code sessions.",
    "LazyClaude 자체를 MCP 서버로 (v2.32.0)": "LazyClaude as an MCP server (v2.32.0)",
    "노출되는 6 tool": "6 exposed tools",
    "6 tool 노출: 탭 카탈로그 · 비용 요약 · 보안 스캔 · 러너 패턴 · RTK 상태 · 워크플로우 템플릿.":
        "Exposes 6 tools: tab catalog · cost summary · security scan · learner patterns · RTK status · workflow templates.",
    "설치 명령 (Terminal)": "Install command (Terminal)",
    "~/.claude 전체(설정·훅·에이전트·MCP)를 정적 검사 — 시크릿 · 위험 훅 · 과도한 권한 · 신뢰 불가 MCP. AI 호출 없음, 100% 로컬.":
        "Statically scan all of ~/.claude (settings · hooks · agents · MCP) for secrets, risky hooks, over-broad permissions, and untrusted MCP servers. 100% local, no AI calls.",
    "전체 키보드 단축키 보기": "Show all keyboard shortcuts",
    "누적 토큰": "Cumulative tokens",
}

NEW_ZH: dict[str, str] = {
    # ── Sidebar / palette categories ────────────────────────────
    "AI 작업": "AI 工作",
    "DAG 진입점": "DAG 入口",
    "데이터 / HTTP": "数据 / HTTP",
    "분기 · 루프 · 재시도 · 합류": "分支 · 循环 · 重试 · 合并",
    "변환 · 변수 · 외부 호출 · 서브워크플로우": "变换 · 变量 · HTTP · 子工作流",
    "세션 · 페르소나 · 임베딩": "会话 · 角色 · 嵌入",
    "워크플로우 종착": "工作流终点",
    "흐름 제어": "流程控制",
    "트리거": "触发器",
    "연동": "集成",
    "기록": "日志",
    "Slack 어드민 · Obsidian 기록": "Slack 管理员审批 · Obsidian 日志",
    "카테고리 → 노드 선택": "分类 → 选择节点",

    # ── Crew wizard headers ─────────────────────────────────────
    "🧑‍✈️ 크루 위저드": "🧑‍✈️ 团队向导",
    "크루 위저드": "团队向导",
    "크루 위저드 사용법": "团队向导使用说明",
    "Zapier 식 4-스텝 폼 → 워크플로우 자동 생성": "Zapier 风格 4 步表单 → 自动生成工作流",
    "폼만 채우면 기획자 + 페르소나 N명 + Slack 어드민 게이트 + Obsidian 기록까지 자동 생성":
        "填写表单即可自动生成：策划者 + N 个角色 + Slack 管理员审批 + Obsidian 日志",
    "폼만 채우면 기획자 + 페르소나 N명 + Slack 어드민 게이트 + Obsidian 기록까지 자동 생성. 워크플로우 탭에서 그대로 캔버스 편집 가능.":
        "填写表单即可自动生成：策划者 + N 个角色 + Slack 管理员审批 + Obsidian 日志。生成的是普通工作流，可在工作流标签的画布中自由编辑。",
    "처음이라면 사용법을 먼저 확인하세요": "首次使用？请先查看使用说明",
    "사용법은 언제든 📖 버튼으로 다시 열 수 있습니다.":
        "可随时通过 📖 按钮再次打开使用说明。",
    "이해했습니다": "我明白了",
    "이게 뭐죠?": "这是什么？",
    "워크플로우 탭은 자유도가 높지만 처음엔 노드 18종을 보고 어디서 시작할지 막막합니다. 크루 위저드는 가장 흔한 패턴 —":
        "工作流标签很灵活，但 18 种节点初看很容易迷失。团队向导提取了最常见的模式 —",
    "기획자가 페르소나 여러 명에게 일을 분배하고, 보고를 받아 다음 사이클을 지시하는":
        "策划者将任务分发给多个角色、接收报告并指挥下一个周期",
    "구조 — 를 폼 4 스텝으로 추출해 한 번에 만들어 줍니다. 결과는 일반 워크플로우라 워크플로우 탭에서 그대로 자유 편집 가능합니다.":
        "— 提炼为 4 步表单一次生成。结果是普通工作流，可在画布中自由编辑。",
    "생성되는 구조": "生成的结构",
    "4 스텝 가이드": "4 步指南",
    "스텝 1 · 프로젝트": "步骤 1 · 项目",
    "스텝 2 · 페르소나": "步骤 2 · 角色",
    "스텝 3 · Slack & Obsidian": "步骤 3 · Slack 和 Obsidian",
    "스텝 4 · 자율성": "步骤 4 · 自主性",
    "Slack 인터랙션": "Slack 交互",
    "자주 막히는 곳": "常见问题",
    "생성 후 다음 단계": "生成后下一步",
    "🚀 시작": "🚀 开始",
    "🧭 기획자 (Planner — Opus 권장)": "🧭 策划者 (Planner — 推荐 Opus)",
    "🧩 보고 취합 (Aggregate)": "🧩 汇总报告 (Aggregate)",
    "🛂 Slack 어드민 게이트  ← (autonomy 모드에 따라 선택적)":
        "🛂 Slack 管理员审批  ← (依 autonomy 模式可选)",
    "📝 Obsidian 기록 (logs/YYYY-MM-DD.md)": "📝 Obsidian 日志 (logs/YYYY-MM-DD.md)",
    "📤 결과": "📤 结果",
    "↓ ↓ ↓     (페르소나마다 병렬 분기)": "↓ ↓ ↓     (按角色并行分发)",
    "└─ (loop) ──→ 다시 기획자에게 피드백 주입":
        "└─ (循环) ──→ 反馈再注入策划者",

    # ── Wizard step labels & form ────────────────────────────────
    "프로젝트": "项目",
    "페르소나": "角色",
    "자율성": "自主性",
    "자율성 모드": "自主性模式",
    "자율 모드": "自主模式",
    "🤖 자율 모드": "🤖 自主模式",
    "🛂 어드민 게이트": "🛂 管理员审批",
    "🔕 Slack 없음": "🔕 不使用 Slack",
    "어드민 게이트": "管理员审批",
    "프로젝트 이름": "项目名称",
    "프로젝트 폴더명": "项目文件夹名",
    "예: weekly-report": "例如: weekly-report",
    "예: 다음주까지 신제품 출시 가이드를 작성한다 — 시장조사·초안·리뷰까지":
        "例如: 下周前完成新品发布指南 — 调研·草稿·复核",
    "예: Researcher(Claude Sonnet) + Builder(Gemini Pro) + Reviewer(Ollama)":
        "例如: Researcher (Claude Sonnet) + Builder (Gemini Pro) + Reviewer (Ollama)",
    "영문/숫자/공백/_-./ 만 허용 — Obsidian 폴더와 워크플로우 이름에 그대로 사용됩니다.":
        "仅允许字母数字 / 空格 / _-./ — 直接用作 Obsidian 文件夹和工作流名称。",
    "목표 (Planner 가 받는 첫 입력)": "目标 (策划者的初始输入)",
    "목표 — Planner 가 받는 첫 입력. 한 줄로 명확하게.":
        "目标 — 策划者的初始输入。一句话清晰说明。",
    "Planner 모델": "策划者模型",
    "Planner 모델 — Opus 권장. 사이클을 지휘하는 두뇌입니다.":
        "策划者模型 — 推荐 Opus。这是指挥每个周期的大脑。",
    "전체 사이클을 지휘하는 두뇌 — Opus 등 가장 깊이 있는 모델 권장.":
        "指挥所有周期的大脑 — 推荐 Opus 等最深度的模型。",
    "작업 디렉터리 (선택)": "工作目录 (可选)",
    "1~8명. 같은 역할이라도 모델이 다르면 별도 페르소나로 등록 가능 — Claude · Gemini · Ollama 자유 조합.":
        "1–8 个角色。同角色不同模型可注册为独立角色 — Claude · Gemini · Ollama 自由组合。",
    "1~8명. 역할 + 모델 + 중점 영역 입력.":
        "1–8 个角色。填写角色 + 模型 + 关注领域。",
    "Claude · Gemini · Ollama 자유 조합 — 서로 다른 모델을 섞을수록 다양한 시각을 얻습니다.":
        "Claude · Gemini · Ollama 自由组合 — 不同模型带来不同视角。",
    "역할": "角色",
    "중점 영역 (선택)": "关注领域 (可选)",
    "시장조사": "市场调研",
    "페르소나 추가": "添加角色",
    "최대 8명까지": "最多 8 个角色",
    "최소 1명은 필요합니다": "至少需要一个角色",

    # ── Slack settings + Obsidian path ──────────────────────────
    "Slack 어드민 게이트": "Slack 管理员审批",
    "Slack Bot Token (xoxb-…) 이 필요합니다":
        "需要 Slack Bot Token (xoxb-…)",
    "https://api.slack.com/apps 에서 봇을 만들고 chat:write, reactions:read, channels:history 권한을 부여하세요.":
        "在 https://api.slack.com/apps 创建机器人并授予 chat:write, reactions:read, channels:history 权限。",
    "필요한 Slack 권한: chat:write · reactions:read · channels:history (또는 groups:history)":
        "所需 Slack 权限: chat:write · reactions:read · channels:history (或 groups:history)",
    "Slack 봇 토큰(xoxb-…) 을 한 번만 저장 — auth.test 로 즉시 검증. 토큰은 ~/.claude-dashboard-slack.json 에 chmod 600 으로 저장.":
        "保存 Bot Token (xoxb-…) 一次 — 通过 auth.test 即时验证。Token 存于 ~/.claude-dashboard-slack.json (chmod 600)。",
    "기본 채널 (예: C012345)": "默认频道 (例如: C012345)",
    "이 워크플로우에서 사용할 채널 ID (선택, 비우면 기본 채널 사용)":
        "本工作流使用的频道 ID (可选，留空则用默认频道)",
    "저장 + 검증": "保存 + 验证",
    "테스트 메시지": "测试消息",
    "Slack 토큰 저장 + 검증 성공": "Slack Token 保存并验证成功",
    "Slack 인증 OK": "Slack 认证 OK",
    "Slack 실패": "Slack 失败: ",
    "Slack 응답 대기 (초)": "Slack 等待超时 (秒)",
    "Vault 경로 (": "Vault 路径 (",
    "HOME 하위)": "$HOME 下)",
    "HOME 하위만 허용.": "仅允许 $HOME 下路径。",
    "HOME 하위 경로만 허용. 사이클별로 Projects/":
        "仅允许 $HOME 下路径。每个周期 append 到 Projects/",
    "/logs/YYYY-MM-DD.md 에 사이클별로 append 됩니다.":
        "/logs/YYYY-MM-DD.md 每个周期 append。",
    "/logs/YYYY-MM-DD.md 에 append.": "/logs/YYYY-MM-DD.md (append)。",
    "/logs/YYYY-MM-DD.md — 사이클마다 append.": "/logs/YYYY-MM-DD.md — 每周期 append。",
    "/logs/YYYY-MM-DD.md 에 입력을 마크다운으로 append. 사이클 보고/감사 로그용.":
        "将输入以 Markdown 形式 append 到 /logs/YYYY-MM-DD.md — 用于周期报告 / 审计日志。",

    # ── Multi-sentence WF_NODE_TYPES desc strings ─────────────────────────
    "DAG 의 진입점. 입력 없음 — 워크플로우의 시작점. 각 워크플로우에 1개만 두는 것이 일반적.":
        "DAG 入口。无输入 — 工作流的起点。通常每个工作流仅一个。",
    "가상 Claude 세션. subject(업무) · description(상세) · 모델 · cwd 를 설정하면 실행 시 claude -p 로 자동 실행되거나, 노드의 🖥️ 버튼으로 Terminal 새 창에서 대화형으로 열 수 있음.":
        "虚拟 Claude 会话。设置 subject (任务) · description · 模型 · cwd 后，运行时通过 `claude -p` 自动执行；也可点击 🖥️ 按钮在新终端窗口交互运行。",
    "특정 역할(researcher · writer · reviewer 등)을 부여한 전문 세션. session 과 동일하지만 agentRole 필드로 페르소나를 명시해 전문성을 강화.":
        "带特定角色 (researcher · writer · reviewer …) 的专门会话。引擎与 session 相同，但通过 agentRole 字段显式锁定角色。",
    "여러 입력을 하나로 합치는 노드. concat(텍스트 이어붙이기) 또는 json(배열) 모드. 병렬로 수집한 결과를 하나로 모을 때 사용.":
        "把多个输入合为一个。模式：concat (拼接文本) 或 json (数组)。用于把并行分支聚合为单一值。",
    "조건에 따라 Y / N 두 포트 중 하나만 활성화. 조건 문자열이 입력에 포함되면 Y, 아니면 N 으로 흐름이 분기.":
        "按条件激活 Y / N 两个端口之一。若输入包含条件字符串则走 Y，否则走 N。",
    "워크플로우의 종착지. 이전 노드의 출력을 최종 결과로 저장. exportTo 에 경로(~/ 하위) 지정 시 파일로 저장됨.":
        "工作流终点 — 把上一节点输出作为最终结果保存。设置 exportTo (~/ 下路径) 还会写入磁盘。",
    "외부 REST API 호출. GET/POST/PUT + 헤더 + 응답 JSON 경로 추출. {{input}} 플레이스홀더로 이전 노드 출력 주입.":
        "调用外部 REST API。GET/POST/PUT + 请求头 + 响应 JSON 路径提取。用 {{input}} 注入上一节点输出。",
    "텍스트/JSON 변환. 템플릿 치환 · JSON 경로 추출 · regex 치환 · 결합. 코드 실행 없이 데이터 가공.":
        "文本 / JSON 变换。模板替换 · JSON 路径提取 · 正则替换 · 拼接。无需运行代码即可重塑数据。",
    "입력 값을 변수 이름에 바인딩. 후속 노드에서 참조. 기본값 설정 가능.":
        "把输入绑定到变量名。下游节点可引用。支持默认值。",
    "다른 워크플로우를 호출하고 결과를 받는 노드. 워크플로우 재사용 가능.":
        "调用另一个工作流并返回结果。可复用工作流。",
    "텍스트를 벡터로 변환. Ollama bge-m3, OpenAI text-embedding-3 등 임베딩 모델 사용. RAG/검색 파이프라인 구축용.":
        "把文本转为向量。使用嵌入模型 (Ollama bge-m3, OpenAI text-embedding-3 等)。用于 RAG / 检索流水线。",
    "반복 처리 노드. for_each(리스트 순회) · count(횟수 반복) · while(조건 반복) 모드 지원. 입력을 분할하여 각 항목에 동일 흐름을 적용.":
        "循环节点。模式：for_each (遍历列表) · count (重复 N 次) · while (条件循环)。把输入拆分并对每项应用下游流程。",
    "실패 시 자동 재시도. 최대 재시도 횟수 · 백오프 간격 · 배수를 설정하여 일시적 오류를 자동 복구.":
        "失败自动重试。配置最大重试次数 · 退避间隔 · 倍数以恢复瞬时错误。",
    "에러 처리 전략 노드. skip(무시) · default(기본값 반환) · route(다른 노드로 분기) 모드로 워크플로우 안정성 확보.":
        "错误处理策略节点。模式：skip (忽略) · default (返回默认值) · route (分支到其他节点) 保证工作流稳健。",
    "여러 병렬 경로를 합류. all/any/count 모드":
        "汇合多条并行路径。模式：all / any / count。",
    "지정 시간 대기 후 통과. 고정/랜덤 딜레이":
        "等待指定时间后通过。固定 / 随机延迟。",
    "Slack 채널에 메시지를 올리고 ✅/❌ 반응 또는 스레드 답장을 기다림. 타임아웃 시 자동 통과/거부/중단/기본값 중 선택. 자율모드에서 어드민 개입 지점.":
        "向 Slack 频道发消息并等待 ✅/❌ 反应或线程回复。超时可选自动通过 / 拒绝 / 中断 / 默认值。自主模式下的管理员介入点。",
    "Vault 의 Projects/<프로젝트>/logs/YYYY-MM-DD.md 에 입력을 마크다운으로 append. 사이클 보고/감사 로그용.":
        "把输入以 Markdown 形式 append 到 <vault>/Projects/<项目>/logs/YYYY-MM-DD.md。用于周期报告 / 审计日志。",
    "Vault 의 Projects/": "Vault 的 Projects/",
    "Obsidian 기록": "Obsidian 日志",
    "Obsidian 쓰기 성공": "Obsidian 写入成功",
    "Obsidian 실패": "Obsidian 失败: ",
    "두 항목 다 즉석 테스트 버튼 제공.": "两项均提供即时测试按钮。",
    "경로 테스트": "测试路径",

    # ── Autonomy descriptions ───────────────────────────────────
    "매 사이클마다 Slack 으로 보고하고 ✅/❌ 응답을 기다림. 타임아웃 시 흐름 중단.":
        "每个周期向 Slack 汇报并等待 ✅/❌ 响应。超时则中断。",
    "매 사이클마다 Slack 으로 보고하고 어드민이 승인할 때까지 대기. 타임아웃 시 흐름 중단.":
        "每个周期向 Slack 汇报并等待管理员批准。超时则中断。",
    "Slack 알림은 보내지만 짧은 타임아웃 후 스스로 다음 사이클 진행. 어드민이 끼어들 때만 답장하면 됨.":
        "向 Slack 发状态通知但短超时后自行推进。管理员只需在想干预时回复即可。",
    "Slack 으로 상태 알림은 보내지만 짧은 타임아웃 후 스스로 판단해 다음 사이클 진행. 어드민이 끼어들고 싶을 때만 답장하면 됨.":
        "向 Slack 发状态通知但短超时后自主推进。管理员仅在想引导时回复。",
    "Slack 노드 없이 페르소나 → Obsidian → 다음 사이클로 바로 흐름.":
        "无 Slack 节点 — 角色 → Obsidian → 下个周期。",
    "Slack 노드를 빼고 페르소나 → Aggregate → Obsidian → 다음 사이클로 바로 흐름.":
        "去掉 Slack 节点 — 角色 → 汇总 → Obsidian → 下个周期。",
    "최대 사이클 수": "最大周期数",
    "최대 사이클 수 1~20. 매 사이클마다 직전 보고가 Planner 입력으로 다시 주입됩니다.":
        "最大周期数 1–20。每个周期把上次报告再注入策划者输入。",
    "1=한번만, 3~5 권장. 매 사이클마다 기획자에게 직전 보고가 다시 주입됩니다.":
        "1 = 单次, 推荐 3–5。每个周期把上次报告再注入策划者输入。",
    "루프 피드백 노트 (선택)": "循环反馈备注 (可选)",
    "비워두면 기본값 사용": "留空使用默认备注",
    "이전 사이클 보고를 검토하고 미해결 항목을 우선 처리…":
        "复核上一周期报告并优先处理未解项…",

    # ── Slack interaction copy ──────────────────────────────────
    "승인": "批准",
    "승인: ✅ (white_check_mark) / 👍 / 답장에":
        "批准: ✅ (white_check_mark) / 👍 / 回复包含",
    "승인: ✅ 또는 답장에": "批准: ✅ 或回复包含",
    "approve/ok/승인": "approve / ok / 批准",
    "거부: ❌ (x) / 👎 / 답장에": "拒绝: ❌ (x) / 👎 / 回复包含",
    "· 거부: ❌ 또는": "· 拒绝: ❌ 或",
    "reject/거부": "reject / 拒绝",
    "프로젝트 이름 — Obsidian 폴더명으로 그대로 사용. 영문/숫자/공백/_-./ 만.":
        "项目名称 — 直接用作 Obsidian 文件夹名。仅允许字母数字 / 空格 / _-./。",
    "자유 답장 (예": "自由回复 (例如",
    "Reviewer 보고를 더 깊게 다시": "Reviewer 重做并加深",
    "): 다음 사이클 입력으로 사용 → 어드민이 흐름 중간에 방향 조정 가능":
        "): 用作下个周期输入 → 管理员可中途调整方向",
    "· 자유 답장은 다음 사이클 입력으로 사용됩니다.":
        "· 自由回复将作为下一周期的输入。",
    "Slack 채널 ID (Cxxxx, Gxxxx, 또는 #name)": "Slack 频道 ID (Cxxxx, Gxxxx, 或 #name)",
    "C012345 또는 #ops": "C012345 或 #ops",
    "메시지 템플릿": "消息模板",
    "memo: 사이클 보고 도착": "memo: 周期报告已到达",
    "이전 노드 출력 포함": "包含上一节点输出",
    "타임아웃 시 동작": "超时行为",
    "자동 승인 (계속 진행)": "自动批准 (继续)",
    "자동 거부 (defaultOutput 사용)": "自动拒绝 (使用 defaultOutput)",
    "defaultOutput 으로 통과": "用 defaultOutput 直通",
    "워크플로우 중단": "中断工作流",
    "Default 출력 (거부 / 타임아웃-default 시)": "默认输出 (拒绝 / 超时-default 时)",
    "Slack 채널에 메시지를 올리고 ✅/❌ 반응 또는 스레드 답장을 기다림. 타임아웃 시 자동 통과/거부/중단/기본값 중 선택. 자율모드에서 어드민 개입 지점.":
        "向 Slack 频道发消息并等待 ✅/❌ 反应或线程回复。超时可选自动通过 / 拒绝 / 中断 / 默认值。自主模式下的管理员介入点。",
    "대신 기록할 텍스트": "改为记录的文本",
    "입력을 그대로 다음 노드로 통과": "把输入直通到下一节点",
    "헤딩 (선택)": "标题 (可选)",
    "태그 (콤마 구분)": "标签 (逗号分隔)",

    # ── Common gotchas ──────────────────────────────────────────
    "— 스텝 3 의 토큰 저장 버튼을 눌렀는지 확인. 또는 환경변수 SLACK_BOT_TOKEN 으로 주입 가능.":
        "— 检查是否点击了步骤 3 的保存按钮，或通过 SLACK_BOT_TOKEN 环境变量注入。",
    "— Vault 경로가 ~/ 안에 있는지 확인. realpath 후 검증되므로 symlink 도 주의.":
        "— 检查 vault 路径是否在 ~/ 之下。会进行 realpath 校验，注意 symlink。",
    "Slack 메시지가 도착하지 않음 — 봇이 채널에 초대돼 있는지 확인. 비공개 채널에는 /invite @봇이름 필요.":
        "Slack 消息未到达 — 确认机器人在频道中。私有频道需要 /invite @机器人名。",
    "타임아웃이 너무 짧음 — 자율 모드에서도 사이클당 최소 60s 권장. admin_gate 는 5분~30분이 일반적.":
        "超时太短 — 自主模式也建议每周期至少 60 秒。admin_gate 通常 5–30 分钟。",
    "자동으로 워크플로우 탭으로 이동 — 캔버스에서 노드 추가/제거/연결 자유 편집":
        "自动跳转到工作流标签 — 在画布中自由添加/删除/连接节点",
    "▶ 실행 버튼으로 바로 시작 · 또는 Webhook URL 로 외부 트리거 연결":
        "点击 ▶ 立即运行，或将 Webhook URL 接入外部触发器",
    "실행 중에는 노드별 진행 상태가 실시간 표시 — Slack 게이트는 응답 대기 상태로 노출됨":
        "运行中按节点显示实时进度 — Slack 审批以「等待中」呈现。",

    # ── Misc ─────────────────────────────────────────────────────
    "사이클": "周期",
    "생성 미리보기": "生成预览",
    "아직 미리보기를 생성하지 않았습니다.": "尚未生成预览。",
    "미리보기 생성 중…": "正在生成预览…",
    "미설정": "未配置",
    "워크플로우 탭으로 이동": "前往工作流标签",
    "에디터에 미리 채워졌습니다 — 검토 후 저장하세요": "已预填到编辑器 — 请检查后保存",
    "LazyClaude · Crew Wizard 연결 테스트": "LazyClaude · Crew Wizard 连接测试",
    "메시지 전송": "消息已发送",

    # ── Misc unrelated keys
    "감지된 이슈": "检测到的问题",
    "감지된 이슈 없음 — 깨끗합니다!": "未发现问题 — 一切正常！",
    "검사 대상: settings.json · CLAUDE.md · settings.hooks · ~/.claude/agents · mcp.json":
        "检查目标: settings.json · CLAUDE.md · settings.hooks · ~/.claude/agents · mcp.json",
    "발견된 시크릿은 rotate 후 env var 로 옮기세요.":
        "请轮换发现的密钥并迁移到环境变量。",
    "분석은 완전히 로컬에서 수행됩니다. Claude API 호출 없음. 제안 카드는 클릭 시 해당 탭으로 이동하여 수동 저장할 수 있습니다.":
        "分析完全在本地进行，无 Claude API 调用。点击建议卡片跳转到对应标签并手动保存。",
    "최근 세션에서 반복되는 패턴을 자동 추출. AI 판단 없이 통계 기반.":
        "从最近会话中自动提取重复模式 — 仅统计，无 AI 调用。",
    "최근 30일 세션이 없습니다. Claude Code 를 한 번 이상 사용하세요.":
        "最近 30 天无会话。请至少运行一次 Claude Code。",
    "아직 제안할 패턴이 충분히 누적되지 않았습니다.":
        "尚未累积足够的重复模式提供建议。",
    "스캔한 세션": "扫描的会话",
    "개 세션 중": " / 共",
    "최근 세션": "最近会话",
    "최근 50 run": "最近 50 次运行",
    "개 표시. 행을 클릭하면 상세 타임라인.": " 显示。点击行查看完整时间线。",
    "출력물이 있는 run 이 없습니다.": "暂无带输出的运行。",
    "왼쪽에서 run 을 선택하세요.": "请在左侧选择一个运行。",
    "자동 추출된 제안": "自动提取的建议",
    "Tool 시퀀스": "工具序列",
    "반복 프롬프트": "重复提示",
    "자주 쓰는 Tool": "常用工具",
    "세션 길이 분포": "会话长度分布",
    "Telemetry 오류 급등": "遥测错误激增",
    "Prompt Library 로 저장": "保存到 Prompt Library",
    "ECC AgentShield 방식에서 영감": "受 ECC AgentShield 启发",
    "(없음)": "(无)",
    "(모든 권한 차단) + CSP default-src:none + 정적 필터 (script/iframe/on*/javascript: 제거).":
        "(屏蔽所有权限) + CSP default-src:none + 静态过滤 (移除 script/iframe/on*/javascript:)。",
    "— 스크립트·폼·쿠키·탐색·플러그인 전부 차단. CSP default-src:none, img-src:data 만 허용.":
        "— 屏蔽脚本·表单·Cookie·导航·插件。CSP default-src:none, 仅允许 img-src:data。",
    "sandbox 속성 =": "sandbox 属性 =",
    "워크플로우 출력물을 sandbox iframe + CSP + 정적 필터 4중 보안으로 안전하게 미리보기 — 스크립트 실행·외부 네트워크·쿠키 모두 차단.":
        "通过 sandbox iframe + CSP + 静态过滤 4 重防护安全预览工作流输出 — 屏蔽脚本运行·外部网络·Cookie。",
    "session 노드가 assignee 로 실패 시 선택한 프로바이더로 1회 재시도. 노드 결과에 fallbackUsed 기록.":
        "session 节点的 assignee 失败时用选定的 provider 重试一次。节点结果记录 fallbackUsed。",
    "실패 시 fallback 프로바이더": "失败回退 provider",
    "matcher (예: Bash, *, 비워두면 all)": "matcher (例如: Bash, *, 留空 = 全部)",
    "매처": "匹配器",
    "허용 호스트": "允许的主机",
    "Forwarder 추가": "添加 forwarder",
    "Forwarder 추가됨": "已添加 forwarder",
    "새 Forwarder 추가": "新增 forwarder",
    "등록된 Forwarder": "已注册的 forwarder",
    "등록된 forwarder 가 없습니다": "暂无注册的 forwarder",
    "이 forwarder 를 settings.json 에서 제거합니다. 계속할까요?":
        "将此 forwarder 从 settings.json 中移除。是否继续？",
    "forwarder 는 settings.json 의 hooks 섹션에 curl 명령으로 등록됩니다. 매 변경 시 자동 백업 생성.":
        "forwarder 以 curl 命令注册在 settings.json 的 hooks 部分。每次变更自动备份。",
    "Claude Code hooks 이벤트를 외부 HTTP endpoint 로 포워딩 — 화이트리스트 호스트만 허용, settings.json 자동 백업.":
        "把 Claude Code hook 事件转发到外部 HTTP endpoint — 仅白名单主机，settings.json 自动备份。",
    "Claude Code 세션 안에서 대시보드 기능을 호출할 수 있게 LazyClaude 를 stdio MCP 서버로 등록합니다":
        "把 LazyClaude 注册为 stdio MCP 服务器，可在 Claude Code 会话内调用仪表板功能。",
    "LazyClaude 자체를 MCP 서버로 (v2.32.0)": "LazyClaude 作为 MCP 服务器 (v2.32.0)",
    "노출되는 6 tool": "暴露的 6 个工具",
    "6 tool 노출: 탭 카탈로그 · 비용 요약 · 보안 스캔 · 러너 패턴 · RTK 상태 · 워크플로우 템플릿.":
        "暴露 6 个工具: 标签目录 · 成本汇总 · 安全扫描 · 学习器模式 · RTK 状态 · 工作流模板。",
    "설치 명령 (Terminal)": "安装命令 (终端)",
    "~/.claude 전체(설정·훅·에이전트·MCP)를 정적 검사 — 시크릿 · 위험 훅 · 과도한 권한 · 신뢰 불가 MCP. AI 호출 없음, 100% 로컬.":
        "对 ~/.claude 全部(设置·钩子·代理·MCP)进行静态检查 — 密钥 · 风险钩子 · 过度权限 · 不可信 MCP。100% 本地，无 AI 调用。",
    "전체 키보드 단축키 보기": "查看全部键盘快捷键",
    "누적 토큰": "累计令牌",
}
