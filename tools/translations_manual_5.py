"""overview 등 템플릿 리터럴 composition 에 남는 Korean 조각들.

runtime 은 Hangul word-boundary 로 짧은 키도 안전하게 치환한다.
긴 문구는 full-match 우선 적용된다.
"""

NEW_EN = {
    # features.py score note/formula 에 쓰이는 토큰
    "사용자훅": "userHooks",
    "사용자스킬": "userSkills",
    "사용자 설정": "User-defined",
    "플러그인 제공": "plugin-provided",
    "는 'plugins' 축에서 평가": "counted under the 'plugins' axis",
    "는 별도": "are separate",
    "개는 별도": "are separate",
    "축에서": "axis",
    "활성 플러그인 사용 비율": "Ratio of active plugins actually used",
    "연결 성공률": "connection success rate",
    "활용 안 하는 플러그인은 비활성화로 노이즈 ↓": "Disable unused plugins to reduce noise",
    "자주 쓰는 명령을 allow 해 승인 프롬프트 ↓": "Allow frequent commands to reduce approval prompts",
    "자주 쓰는 명령을": "Frequently used commands:",
    "deny 규칙 늘리면 안전도 ↑": "More deny rules = higher safety",
    "deny 규칙 늘리면 안전도": "More deny rules = higher safety",
    "늘리면 안전도": "more rules → higher safety",
    "쓰는 명령을": "commands to use",
    "해 승인": ", reducing approvals",
    "settings.json 에 SessionStart 훅 하나만 추가해도 +15점. 최대 7개 = 만점.":
        "Adding just one SessionStart hook to settings.json gains +15 points. Max 7 = full score.",
    "하나만 추가해도": "adding just one gains",
    "~/.claude/skills/<id>/SKILL.md 로 자신만의 스킬 추가. 13개 = 만점.":
        "Add your own skills via ~/.claude/skills/<id>/SKILL.md. 13 = full score.",
    "~/.claude/agents/<name>.md 로 자신만의 서브에이전트 추가.":
        "Add your own sub-agents via ~/.claude/agents/<name>.md.",
    "로 자신만의": "to add your own",
    "자신만의 스킬 추가": "your own skills",
    "자신만의 서브에이전트 추가": "your own sub-agents",
    "자신만의": "your own",
    "플러그인 1개 활성화 = +6점. 활용 안 하는 플러그인은 비활성화로 노이즈 ↓.":
        "Enabling one plugin = +6 points. Disable unused plugins to reduce noise.",
    "활용": "utilization",
    "활용도": "utilization",
    "만점": "full score",
    "내 위임됨": "delegated within",
    "그 중 {used_plugin_agents}개 에이전트가 30일 내 위임됨 ({plugin_used_pct}%)":
        "of which {used_plugin_agents} agents delegated within 30 days ({plugin_used_pct}%)",
    "에이전트가 30일 내 위임됨": "agents delegated within 30 days",
    "에이전트 능력이 크게 확장됩니다": "greatly extends agent capabilities",
    "Context7, GitHub, Memory 같은 MCP로 에이전트 능력이 크게 확장됩니다":
        "MCPs like Context7, GitHub, Memory greatly extend agent capabilities",
    "같은": "like",
    "기준": "basis",
    "축별 계산식 상세 확인": "per-axis formula details",
    "축별 계산식": "per-axis formula",
    "통계 탭의 프로젝트 행 클릭 → 5축별 계산식 상세 확인.":
        "Click a project row in the Stats tab → see per-axis formulas in detail.",
    "통계 탭의": "In the Stats tab,",
    "rm -rf, sudo, .env 편집 등을 deny 목록에 추가하세요.":
        "Add rm -rf, sudo, .env edits etc. to the deny list.",
    "편집 등을": "edits etc.",
    "목록에 추가하세요": "add to the list",
    "거부 규칙 강화": "Strengthen deny rules",
    "거부 규칙": "Deny rules",
    "실패/인증필요 MCP 정리하면 점수 ↑": "Remove failed / auth-required MCPs to raise the score",
    "실패/인증필요 MCP 정리하면 점수": "Remove failed / auth-required MCPs to raise score",
    "정리하면": "clean up",
    "정상 연결": "healthy connections",
    "인증필요": "auth required",
    "플랫폼": "platform",
    "커넥터 추가": "Add connector",
    "짧은": "short",
    "점": "pt",
    "로컬": "local",
    "와": "and",
    "내": "within",
    "각": "each",
    "기반": "based",
    "가": "",

    "MCP 커넥터 추가": "Add MCP connector",
    "Context7, GitHub, Memory 같은 MCP로 에이전트 능력이 크게 확장됩니다.":
        "MCPs like Context7, GitHub and Memory greatly extend what your agents can do.",
    "현황 분석": "Current-state analysis",
    "번역 대상 전수 추출": "Exhaustive extraction of translation targets",
    "기존 번역 시스템 제거": "Remove legacy translation system",
    "새 번역 시스템 구축": "Build new translation system",
    "번역 누락 0건 검증": "Verify zero translation misses",
    "커밋 및 문서화": "Commit and documentation",

    # server/system.py env var catalog
    "API 키 인증용 (OAuth 로그인 대신 사용)": "API-key authentication (alternative to OAuth login)",
    "수동 Authorization Bearer 토큰 지정": "Manual Authorization Bearer token",
    "API base URL (self-hosted / proxy 시)": "API base URL (self-hosted / proxy)",
    "기본 모델 override (예: claude-opus-4-7)": "Default model override (e.g. claude-opus-4-7)",
    "Haiku 등 작은 보조 모델 지정": "Small helper model (e.g. Haiku)",
    "~/.claude 위치 override": "Override ~/.claude location",
    "AWS Bedrock 백엔드 사용 (0/1)": "Use AWS Bedrock backend (0/1)",
    "Bedrock 용 AWS region": "AWS region for Bedrock",
    "Google Vertex AI 백엔드 사용 (0/1)": "Use Google Vertex AI backend (0/1)",
    "Vertex 용 region": "Region for Vertex",
    "HTTP 프록시": "HTTP proxy",
    "HTTPS 프록시 (회사 망 등)": "HTTPS proxy (corporate network etc.)",
    "프록시 제외 도메인": "Proxy exclusion domains",
    "텔레메트리·업데이트 비활성화 (0/1)": "Disable telemetry & updates (0/1)",
    "자동 업데이트 끄기 (0/1)": "Disable auto-update (0/1)",
    "Bash 도구 기본 타임아웃 (ms)": "Bash-tool default timeout (ms)",
    "Bash 도구 최대 타임아웃 (ms)": "Bash-tool max timeout (ms)",
    "업데이트 비활성 (legacy)": "Disable update (legacy)",
    "텔레메트리 비활성 (0/1)": "Disable telemetry (0/1)",

    # model config
    "최강 성능, 느림/비쌈": "Top-tier performance, slower / pricier",
    "Fast mode 기본 모델": "Default model for Fast mode",
    "settings.model 비워두기": "Leave settings.model empty",

    # ideStatus / metrics text
    "Claude Code 는 현재 VS Code / JetBrains IDE 에 bridge 방식으로 연결됩니다. 연결된 IDE 는 세션 metadata 의 entrypoint/terminal 필드로 식별.":
        "Claude Code connects to VS Code / JetBrains IDEs via a bridge. Connected IDEs are identified by the session metadata's entrypoint/terminal fields.",
    # NOTE: keys must use the ORIGINAL Korean tokens (before short-key substitution)
    "토큰은 세션 DB (~/.claude/projects/*/*.jsonl 에서 파싱) 기반":
        "Tokens are parsed from the session DB (~/.claude/projects/*/*.jsonl)",
    "비용은 2025 공식 요금표 기반 추정":
        "Cost is estimated using the 2025 official pricing",
    "에서 파싱": "parsed from",
    "공식 요금표": "official pricing",
}

NEW_ZH = {
    "사용자훅": "用户钩子",
    "사용자스킬": "用户技能",
    "사용자 설정": "用户配置",
    "플러그인 제공": "插件提供",
    "는 'plugins' 축에서 평가": "在 'plugins' 轴下统计",
    "는 별도": "另行计算",
    "개는 별도": "另行计算",
    "축에서": "轴上",
    "활성 플러그인 사용 비율": "活跃插件的实际使用率",
    "연결 성공률": "连接成功率",
    "활용 안 하는 플러그인은 비활성화로 노이즈 ↓": "禁用未使用的插件可减少噪声",
    "자주 쓰는 명령을 allow 해 승인 프롬프트 ↓": "允许常用命令以减少批准提示",
    "자주 쓰는 명령을": "常用命令:",
    "deny 규칙 늘리면 안전도 ↑": "增加 deny 规则 = 提高安全性",
    "deny 규칙 늘리면 안전도": "增加 deny 规则 = 提高安全性",
    "늘리면 안전도": "增加 → 提高安全",
    "쓰는 명령을": "命令",
    "해 승인": "，减少审批",
    "settings.json 에 SessionStart 훅 하나만 추가해도 +15점. 최대 7개 = 만점.":
        "仅添加一个 SessionStart 钩子即可 +15 分。最多 7 = 满分。",
    "하나만 추가해도": "仅添加一个即可获得",
    "~/.claude/skills/<id>/SKILL.md 로 자신만의 스킬 추가. 13개 = 만점.":
        "通过 ~/.claude/skills/<id>/SKILL.md 添加自己的技能。13 = 满分。",
    "~/.claude/agents/<name>.md 로 자신만의 서브에이전트 추가.":
        "通过 ~/.claude/agents/<name>.md 添加自己的子代理。",
    "로 자신만의": "添加自己的",
    "자신만의 스킬 추가": "自己的技能",
    "자신만의 서브에이전트 추가": "自己的子代理",
    "자신만의": "自己的",
    "플러그인 1개 활성화 = +6점. 활용 안 하는 플러그인은 비활성화로 노이즈 ↓.":
        "启用 1 个插件 = +6 分。禁用未使用的插件以减少噪声。",
    "활용": "使用",
    "활용도": "使用率",
    "만점": "满分",
    "내 위임됨": "内已委派",
    "그 중 {used_plugin_agents}개 에이전트가 30일 내 위임됨 ({plugin_used_pct}%)":
        "其中 {used_plugin_agents} 个代理在 30 天内被委派 ({plugin_used_pct}%)",
    "에이전트가 30일 내 위임됨": "个代理在 30 天内被委派",
    "에이전트 능력이 크게 확장됩니다": "大幅扩展代理能力",
    "Context7, GitHub, Memory 같은 MCP로 에이전트 능력이 크게 확장됩니다":
        "Context7、GitHub、Memory 等 MCP 大幅扩展代理能力",
    "같은": "等",
    "기준": "基准",
    "축별 계산식 상세 확인": "按轴查看公式详情",
    "축별 계산식": "按轴的公式",
    "통계 탭의 프로젝트 행 클릭 → 5축별 계산식 상세 확인.":
        "在统计标签中点击项目行 → 按 5 轴查看公式详情。",
    "통계 탭의": "在统计标签中，",
    "rm -rf, sudo, .env 편집 등을 deny 목록에 추가하세요.":
        "请将 rm -rf、sudo、.env 编辑等添加到 deny 列表。",
    "편집 등을": "编辑等",
    "목록에 추가하세요": "添加到列表",
    "거부 규칙 강화": "强化 deny 规则",
    "거부 규칙": "拒绝规则",
    "실패/인증필요 MCP 정리하면 점수 ↑": "清理失败/需认证的 MCP 可提升分数",
    "실패/인증필요 MCP 정리하면 점수": "清理失败/需认证的 MCP 可提升分数",
    "정리하면": "清理",
    "정상 연결": "正常连接",
    "인증필요": "需认证",
    "플랫폼": "平台",
    "커넥터 추가": "添加连接器",
    "짧은": "短",
    "점": "分",
    "로컬": "本地",
    "와": "与",
    "내": "内",
    "각": "每",
    "기반": "基于",
    "가": "",

    "MCP 커넥터 추가": "添加 MCP 连接器",
    "Context7, GitHub, Memory 같은 MCP로 에이전트 능력이 크게 확장됩니다.":
        "Context7、GitHub、Memory 等 MCP 可以大幅增强代理能力。",
    "현황 분석": "现状分析",
    "번역 대상 전수 추출": "翻译对象全量提取",
    "기존 번역 시스템 제거": "移除旧翻译系统",
    "새 번역 시스템 구축": "构建新翻译系统",
    "번역 누락 0건 검증": "验证零翻译遗漏",
    "커밋 및 문서화": "提交与文档化",

    "API 키 인증용 (OAuth 로그인 대신 사용)": "API 密钥认证（代替 OAuth 登录）",
    "수동 Authorization Bearer 토큰 지정": "手动指定 Authorization Bearer 令牌",
    "API base URL (self-hosted / proxy 시)": "API 基础 URL（自托管 / 代理时）",
    "기본 모델 override (예: claude-opus-4-7)": "默认模型覆盖（例：claude-opus-4-7）",
    "Haiku 등 작은 보조 모델 지정": "指定 Haiku 等小型辅助模型",
    "~/.claude 위치 override": "覆盖 ~/.claude 位置",
    "AWS Bedrock 백엔드 사용 (0/1)": "使用 AWS Bedrock 后端（0/1）",
    "Bedrock 용 AWS region": "Bedrock 的 AWS 区域",
    "Google Vertex AI 백엔드 사용 (0/1)": "使用 Google Vertex AI 后端（0/1）",
    "Vertex 용 region": "Vertex 的区域",
    "HTTP 프록시": "HTTP 代理",
    "HTTPS 프록시 (회사 망 등)": "HTTPS 代理（公司网络等）",
    "프록시 제외 도메인": "代理排除域名",
    "텔레메트리·업데이트 비활성화 (0/1)": "禁用遥测与更新（0/1）",
    "자동 업데이트 끄기 (0/1)": "关闭自动更新（0/1）",
    "Bash 도구 기본 타임아웃 (ms)": "Bash 工具默认超时（毫秒）",
    "Bash 도구 최대 타임아웃 (ms)": "Bash 工具最大超时（毫秒）",
    "업데이트 비활성 (legacy)": "禁用更新（legacy）",
    "텔레메트리 비활성 (0/1)": "禁用遥测（0/1）",

    "최강 성능, 느림/비쌈": "顶级性能，较慢/较贵",
    "Fast mode 기본 모델": "Fast 模式默认模型",
    "settings.model 비워두기": "保留 settings.model 为空",

    "Claude Code 는 현재 VS Code / JetBrains IDE 에 bridge 방식으로 연결됩니다. 연결된 IDE 는 세션 metadata 의 entrypoint/terminal 필드로 식별.":
        "Claude Code 通过 bridge 方式连接 VS Code / JetBrains IDE。已连接的 IDE 通过会话元数据的 entrypoint/terminal 字段识别。",
    "토큰은 세션 DB (~/.claude/projects/*/*.jsonl 에서 파싱) 기반":
        "令牌来自会话 DB（解析自 ~/.claude/projects/*/*.jsonl）",
    "비용은 2025 공식 요금표 기반 추정":
        "费用基于 2025 官方价目预估",
    "에서 파싱": "解析自",
    "공식 요금표": "官方价目",
}
