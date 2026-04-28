"""v2.43.0 — Setup Helpers (global ↔ project scope for CLAUDE.md /
settings / settings.local / skills / commands / hooks).

Imported by translations_manual.py.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # Scope toggle / picker
    "스코프":               "Scope",
    "글로벌":               "Global",
    "프로젝트":             "Project",
    "인덱스된 프로젝트 없음":  "No indexed projects",
    "CLAUDE.md 스코프":     "CLAUDE.md scope",
    "Settings 스코프":      "Settings scope",
    "스킬 스코프":           "Skills scope",
    "명령어 스코프":         "Commands scope",
    "훅 스코프":             "Hooks scope",

    # CLAUDE.md
    "아직 프로젝트 CLAUDE.md 가 없습니다": "No project CLAUDE.md yet",
    "이 프로젝트에서 작업할 때만 로드되는 지침을 작성하세요. 저장하면 즉시 ":
        "Write instructions that load only when working in this project. Saving writes to ",
    "이 프로젝트에서 작업할 때만 로드되는 지침.": "Loaded only when working in this project.",
    "모든 세션에 로드되는 글로벌 지침.": "Global instructions loaded into every session.",

    # Settings
    "(커밋됨)": "(committed)",
    "(개인, gitignore)": "(personal, gitignore)",
    "파일 없음 — 저장 시 생성됨": "File missing — will be created on save",
    "프로젝트 스코프": "Project scope",
    "팀과 공유 — git에 커밋": "Shared with the team — commit to git",
    "개인 오버라이드 — gitignore 권장": "Personal overrides — gitignore recommended",
    "Claude Code는 프로젝트 ▶ 글로벌 순서로 머지합니다.":
        "Claude Code merges project then global.",
    "유효한 JSON 이어야 저장됩니다.": "Must be valid JSON to save.",
    "공식 문서": "Docs",
    "JSON 오류": "JSON error",
    "편집 후 '저장' 하면 파일에 즉시 반영됩니다.":
        "Edit then click Save to write the file.",
    "추천 프로파일": "Recommended profiles",
    "클릭 시 Auth 확인 → 변경 미리보기 → 적용까지 안내됩니다.":
        "Click for the auth check → preview → apply flow.",
    "적용하기": "apply",
    "팁": "Tips",
    "자동 승인 규칙": "auto-approve rules",
    "절대 금지 규칙": "hard-deny rules",
    "이벤트 기반 자동 스크립트": "event-driven scripts",
    "활성화 플러그인": "enabled plugins",
    "파일": "File",

    # Skills
    "프로젝트 스킬": "Project skills",
    "스킬 검색…": "Search skills…",
    "사용자 설정만": "User skills only",
    "사용자 설정": "User",
    "전역": "Global",
    "활성(사용자 설정)": "Active (user)",
    "플러그인 제공": "Plugin",
    "비활성 플러그인 ▶ 활성화": "Disabled plugin ▶ enable",
    "이 플러그인은 비활성 — Claude Code 가 호출하지 않습니다.":
        "Plugin is disabled — Claude Code won't invoke it.",
    "스킬": "Skills",
    "스킬 없음": "No skills",
    "별도": "separate",
    "새 스킬": "New skill",
    "새 프로젝트 스킬": "New project skill",
    "프로젝트 스킬 편집": "Edit project skill",
    "프로젝트가 선택되지 않았습니다": "No project selected",
    "스킬 ID — 영숫자 / 하이픈 / 언더스코어": "Skill ID — alphanumeric / hyphen / underscore",
    "잘못된 스킬 ID": "Invalid skill ID",
    "스킬 로드 실패": "Failed to load skill",
    "플러그인 스킬 (read-only)": "Plugin skill (read-only)",
    "스킬 편집": "Edit skill",
    "생성": "Create",
    "생성 실패": "Failed to create",
    "생성됨": "Created",

    # Commands
    "슬래시 명령어": "Slash commands",
    "개 명령어": " commands",
    "개 카테고리": " categories",
    "검색…": "Search…",
    "미번역만": "Untranslated only",
    "전체": "All",
    "명령어 없음": "No commands",
    "새 명령어": "New command",
    "새 프로젝트 명령어": "New project command",
    "프로젝트 명령어 편집": "Edit project command",
    "프로젝트 명령어 삭제": "Delete project command",
    "이 명령어를 삭제할까요?": "Delete this command?",
    "명령어 로드 실패": "Failed to load command",
    "명령어 ID — '/' 대신 영숫자 / '-' / '_' / 하위경로는 ':' 사용":
        "Command ID — alphanumeric / '-' / '_' / use ':' for sub-paths instead of '/'",
    "잘못된 명령어 ID": "Invalid command ID",

    # Hooks
    "프로젝트 훅": "Project hooks",
    "Settings 탭에서 편집": "Edit in Settings tab",
    "아래 목록은 글로벌 + 플러그인 훅. 프로젝트 훅은 settings.json 의 hooks 키로 편집합니다.":
        "Below: global + plugin hooks. Project hooks are edited via the `hooks` key in settings.json.",
    "(파일 없음)": "(missing)",
    "훅 (Hooks)": "Hooks",
    "개 이벤트": " events",
    "위험": "risky",
    "개": "",
    "여기에 적은 지침(기억·규칙·선호)은 모든 세션 시작 시 자동 로드됩니다. 직접 쓰거나, 위의 \"AI 에게 추천 받기\"로 현재 작업 패턴 기반 초안을 받아보세요.":
        "Anything you write here (memories, rules, preferences) auto-loads on every session start. Write directly, or use \"Ask AI for suggestions\" above for a draft based on your work patterns.",
}

NEW_ZH: dict[str, str] = {
    # Scope toggle / picker
    "스코프":               "范围",
    "글로벌":               "全局",
    "프로젝트":             "项目",
    "인덱스된 프로젝트 없음":  "无已索引项目",
    "CLAUDE.md 스코프":     "CLAUDE.md 范围",
    "Settings 스코프":      "Settings 范围",
    "스킬 스코프":           "技能范围",
    "명령어 스코프":         "命令范围",
    "훅 스코프":             "钩子范围",

    "아직 프로젝트 CLAUDE.md 가 없습니다": "尚无项目 CLAUDE.md",
    "이 프로젝트에서 작업할 때만 로드되는 지침을 작성하세요. 저장하면 즉시 ":
        "编写仅在此项目工作时加载的指令。保存即写入 ",
    "이 프로젝트에서 작업할 때만 로드되는 지침.": "仅在该项目工作时加载的指令。",
    "모든 세션에 로드되는 글로벌 지침.": "加载到所有会话的全局指令。",

    "(커밋됨)": "（已提交）",
    "(개인, gitignore)": "（个人，gitignore）",
    "파일 없음 — 저장 시 생성됨": "文件不存在 — 保存时自动创建",
    "프로젝트 스코프": "项目范围",
    "팀과 공유 — git에 커밋": "与团队共享 — 提交到 git",
    "개인 오버라이드 — gitignore 권장": "个人覆盖 — 建议加入 gitignore",
    "Claude Code는 프로젝트 ▶ 글로벌 순서로 머지합니다.":
        "Claude Code 按 项目 ▶ 全局 顺序合并。",
    "유효한 JSON 이어야 저장됩니다.": "必须是有效 JSON 才能保存。",
    "공식 문서": "文档",
    "JSON 오류": "JSON 错误",
    "편집 후 '저장' 하면 파일에 즉시 반영됩니다.":
        "编辑后点击保存即刻写入文件。",
    "추천 프로파일": "推荐配置",
    "클릭 시 Auth 확인 → 변경 미리보기 → 적용까지 안내됩니다.":
        "点击进入 认证检查 → 预览 → 应用 流程。",
    "적용하기": "应用",
    "팁": "提示",
    "자동 승인 규칙": "自动批准规则",
    "절대 금지 규칙": "硬性拒绝规则",
    "이벤트 기반 자동 스크립트": "事件驱动脚本",
    "활성화 플러그인": "已启用插件",
    "파일": "文件",

    "프로젝트 스킬": "项目技能",
    "스킬 검색…": "搜索技能…",
    "사용자 설정만": "仅用户技能",
    "사용자 설정": "用户",
    "전역": "全局",
    "활성(사용자 설정)": "活跃（用户）",
    "플러그인 제공": "插件",
    "비활성 플러그인 ▶ 활성화": "未启用插件 ▶ 启用",
    "이 플러그인은 비활성 — Claude Code 가 호출하지 않습니다.":
        "插件未启用 — Claude Code 不会调用。",
    "스킬": "技能",
    "스킬 없음": "无技能",
    "별도": "独立",
    "새 스킬": "新建技能",
    "새 프로젝트 스킬": "新建项目技能",
    "프로젝트 스킬 편집": "编辑项目技能",
    "프로젝트가 선택되지 않았습니다": "未选择项目",
    "스킬 ID — 영숫자 / 하이픈 / 언더스코어": "技能 ID — 字母数字 / 连字符 / 下划线",
    "잘못된 스킬 ID": "无效的技能 ID",
    "스킬 로드 실패": "加载技能失败",
    "플러그인 스킬 (read-only)": "插件技能（只读）",
    "스킬 편집": "编辑技能",
    "생성": "创建",
    "생성 실패": "创建失败",
    "생성됨": "已创建",

    "슬래시 명령어": "斜杠命令",
    "개 명령어": " 个命令",
    "개 카테고리": " 个分类",
    "검색…": "搜索…",
    "미번역만": "仅未翻译",
    "전체": "全部",
    "명령어 없음": "无命令",
    "새 명령어": "新建命令",
    "새 프로젝트 명령어": "新建项目命令",
    "프로젝트 명령어 편집": "编辑项目命令",
    "프로젝트 명령어 삭제": "删除项目命令",
    "이 명령어를 삭제할까요?": "删除此命令？",
    "명령어 로드 실패": "加载命令失败",
    "명령어 ID — '/' 대신 영숫자 / '-' / '_' / 하위경로는 ':' 사용":
        "命令 ID — 字母数字 / '-' / '_' / 用 ':' 表示子路径而非 '/'",
    "잘못된 명령어 ID": "无效的命令 ID",

    "프로젝트 훅": "项目钩子",
    "Settings 탭에서 편집": "在 Settings 标签编辑",
    "아래 목록은 글로벌 + 플러그인 훅. 프로젝트 훅은 settings.json 의 hooks 키로 편집합니다.":
        "下方为全局 + 插件钩子。项目钩子通过 settings.json 的 hooks 键编辑。",
    "(파일 없음)": "（缺失）",
    "훅 (Hooks)": "钩子（Hooks）",
    "개 이벤트": " 事件",
    "위험": "危险",
    "개": "",
    "여기에 적은 지침(기억·규칙·선호)은 모든 세션 시작 시 자동 로드됩니다. 직접 쓰거나, 위의 \"AI 에게 추천 받기\"로 현재 작업 패턴 기반 초안을 받아보세요.":
        "您写在此处的内容（记忆、规则、偏好）将在每次会话启动时自动加载。直接编写，或使用上方的 \"AI 推荐\" 基于您的工作模式生成草稿。",
}
