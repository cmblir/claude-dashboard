"""v2.65.0 — M1 boot-timing card + M2 Ralph duplicate-run button.

Korean -> English / Chinese for strings introduced in cycle 13.
Loaded by ``tools/translations_manual.py``.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # X3 (v2.66.10) — Codex + provider wizard cards
    "Codex CLI 가 PATH 에 있으면 자동 감지됩니다.":
        "Codex CLI is auto-detected when present in PATH.",
    "지원 모델":  "Supported models",
    "빠른 LPU 추론 — Llama / Mixtral / DeepSeek R1":
        "Fast LPU inference — Llama / Mixtral / DeepSeek R1",
    "V3 chat + R1 reasoning":  "V3 chat + R1 reasoning",
    "Large / Medium / Small / Codestral":  "Large / Medium / Small / Codestral",
    "OpenAI Codex CLI":  "OpenAI Codex CLI",
    "발급":  "Get a key",
    # W1 (v2.66.9) — Orchestrator config picker UI
    "가용 프로바이더 없음 — AI 프로바이더 탭에서 키 설정":
        "No available provider — set keys in the AI Providers tab",
    "사용자 메시지를 단계별로 분해하는 모델":
        "Model that breaks the user's message into sub-tasks",
    "서브 에이전트 결과를 합쳐 채널 회신을 작성":
        "Merges sub-agent outputs into the channel reply",
    "아래 + 버튼으로 추가":  "Add via the + below",
    "어사이니 추가":         "Add assignee",
    "플래너가 작업 분배 시 후보로 사용하는 모델 목록":
        "Candidate models the planner picks from when fanning out tasks",
    # U1 — System tab refactor (newly t()-wrapped strings)
    "편집은 \"Settings 편집\" 또는 \"권한\" 탭에서.": "Edit via the \"Settings 편집\" or \"권한\" tab.",
    # M1 — System tab boot-timing card
    "서버 부팅":     "Server boot",
    "부팅 시간":     "Boot time",
    "listen 시작":   "Started listening",
    "python3 server.py 부팅부터 첫 HTTP listen 까지의 시간. db 마이그레이션, 백그라운드 인덱스, ollama auto-start 등은 데몬 스레드라 이 시간에 포함되지 않습니다.":
        "Time from python3 server.py startup to first HTTP listen. DB migration, background index, and ollama auto-start run as daemon threads and are not included.",
    # M2 — Ralph duplicate run button
    "이 실행을 동일 설정으로 다시 시작":
        "Restart with the same configuration",
    "이전 실행 설정 불러옴 — 검토 후 시작하세요":
        "Previous run configuration loaded — review and click Start",
}

NEW_ZH: dict[str, str] = {
    # X3 — Codex + provider wizard cards
    "Codex CLI 가 PATH 에 있으면 자동 감지됩니다.":
        "如果 Codex CLI 在 PATH 中,将自动检测。",
    "지원 모델":  "支持的模型",
    "빠른 LPU 추론 — Llama / Mixtral / DeepSeek R1":
        "快速 LPU 推理 — Llama / Mixtral / DeepSeek R1",
    "V3 chat + R1 reasoning":  "V3 chat + R1 推理",
    "Large / Medium / Small / Codestral":  "Large / Medium / Small / Codestral",
    "OpenAI Codex CLI":  "OpenAI Codex CLI",
    "발급":  "获取密钥",
    # W1 — Orchestrator picker UI
    "가용 프로바이더 없음 — AI 프로바이더 탭에서 키 설정":
        "无可用提供商 — 在 AI 提供商标签中设置密钥",
    "사용자 메시지를 단계별로 분해하는 모델": "将用户消息分解为子任务的模型",
    "서브 에이전트 결과를 합쳐 채널 회신을 작성": "合并子代理输出后写入频道回复",
    "아래 + 버튼으로 추가":  "通过下方 + 按钮添加",
    "어사이니 추가":         "添加 assignee",
    "플래너가 작업 분배 시 후보로 사용하는 모델 목록":
        "规划器分发任务时使用的候选模型列表",
    # U1 — System tab refactor
    "편집은 \"Settings 편집\" 또는 \"권한\" 탭에서.": "在 \"Settings 编辑\" 或 \"权限\" 标签中编辑。",
    # M1 — System tab boot-timing card
    "서버 부팅":     "服务器启动",
    "부팅 시간":     "启动耗时",
    "listen 시작":   "开始监听",
    "python3 server.py 부팅부터 첫 HTTP listen 까지의 시간. db 마이그레이션, 백그라운드 인덱스, ollama auto-start 등은 데몬 스레드라 이 시간에 포함되지 않습니다.":
        "从 python3 server.py 启动到首次 HTTP 监听的时间。DB 迁移、后台索引、ollama 自启动以守护线程运行，不计入此时间。",
    # M2 — Ralph duplicate run button
    "이 실행을 동일 설정으로 다시 시작":
        "以相同配置重新启动",
    "이전 실행 설정 불러옴 — 검토 후 시작하세요":
        "已加载上次运行配置 — 检查后点击启动",
}
