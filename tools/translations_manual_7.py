"""Features 탭 — server/features.py 의 BUILTIN_NEW_FEATURES 번역.

각 feature 카드의 label/summary 가 한국어로 하드코딩되어 있어 EN/ZH 모드에서
그대로 노출됨. 런타임 DOM 워커가 전체-일치 치환하도록 전체 문자열을 dict 에 등록.
"""

NEW_EN = {
    # Claude Design
    "프롬프트 → 비주얼 디자인/슬라이드/원페이저. Opus 4.7 기반.":
        "Prompt → visual design / slides / one-pager. Powered by Opus 4.7.",

    # Opus 4.7
    "복잡 추론 + 에이전틱 코딩 + 고해상도 비전. Opus 4.6 와 동가격 ($5/$25 per MTok).":
        "Complex reasoning + agentic coding + high-res vision. Same pricing as Opus 4.6 ($5/$25 per MTok).",

    # Managed Agents
    "Claude 를 완전 관리형 에이전트 하네스로 실행. 샌드박스 + 내장 도구 + SSE 스트리밍.":
        "Run Claude as a fully managed agent harness. Sandbox + built-in tools + SSE streaming.",

    # ant CLI
    "Claude API 커맨드라인 클라이언트. Claude Code 네이티브 통합 + YAML 리소스 버전 관리.":
        "Claude API command-line client. Claude Code native integration + YAML resource versioning.",

    # Advisor Tool
    "빠른 executor 모델 + 고지능 advisor 모델 페어링으로 장기 에이전트 품질↑ 비용↓.":
        "Fast executor model + smart advisor model pairing for higher long-running agent quality at lower cost.",

    # Claude Code Routines
    "반복 작업을 routine 으로 저장. Mac offline 이어도 웹 인프라에서 실행.":
        "Save repetitive tasks as routines. Runs on web infrastructure even when your Mac is offline.",

    # Agent Skills
    "스킬(지시+스크립트+리소스 묶음) 을 Claude 가 동적으로 로드. PowerPoint/Excel/Word/PDF 기본 제공.":
        "Claude dynamically loads skills (instructions + scripts + resources bundles). Built-in PowerPoint / Excel / Word / PDF.",

    # Claude Mythos
    "Claude Mythos (보안)": "Claude Mythos (Security)",
    "방어 보안 특화 언어모델. 초대제 research preview (Project Glasswing).":
        "Defensive-security specialized language model. Invite-only research preview (Project Glasswing).",
}

NEW_ZH = {
    "프롬프트 → 비주얼 디자인/슬라이드/원페이저. Opus 4.7 기반.":
        "提示词 → 视觉设计 / 幻灯片 / 单页。基于 Opus 4.7。",

    "복잡 추론 + 에이전틱 코딩 + 고해상도 비전. Opus 4.6 와 동가격 ($5/$25 per MTok).":
        "复杂推理 + 智能体编码 + 高分辨率视觉。与 Opus 4.6 同价（$5/$25 per MTok）。",

    "Claude 를 완전 관리형 에이전트 하네스로 실행. 샌드박스 + 내장 도구 + SSE 스트리밍.":
        "将 Claude 作为完全托管的代理框架运行。沙箱 + 内置工具 + SSE 流式传输。",

    "Claude API 커맨드라인 클라이언트. Claude Code 네이티브 통합 + YAML 리소스 버전 관리.":
        "Claude API 命令行客户端。Claude Code 原生集成 + YAML 资源版本管理。",

    "빠른 executor 모델 + 고지능 advisor 모델 페어링으로 장기 에이전트 품질↑ 비용↓.":
        "快速执行模型 + 高智能顾问模型配对，长时代理任务质量提升、成本下降。",

    "반복 작업을 routine 으로 저장. Mac offline 이어도 웹 인프라에서 실행.":
        "将重复任务保存为 routine。即使 Mac 离线，也在 Web 基础设施上运行。",

    "스킬(지시+스크립트+리소스 묶음) 을 Claude 가 동적으로 로드. PowerPoint/Excel/Word/PDF 기본 제공.":
        "Claude 动态加载技能（指令+脚本+资源集合）。默认提供 PowerPoint / Excel / Word / PDF。",

    "Claude Mythos (보안)": "Claude Mythos（安全）",
    "방어 보안 특화 언어모델. 초대제 research preview (Project Glasswing).":
        "专注防御安全的语言模型。邀请制研究预览（Project Glasswing）。",
}
