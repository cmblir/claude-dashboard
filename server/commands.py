"""슬래시 명령어 (`~/.claude/commands/*.md` + 플러그인 커맨드) 목록 + 카테고리.

번역 배치 API (`api_translate_batch`) 는 auth/plugins 의존성이 있어
server.py 에 잠시 남아있다 — auth.py/plugins.py 분리 후 이 모듈로 합친다.
"""
from __future__ import annotations

from .config import COMMANDS_DIR, PLUGINS_DIR
from .translations import _load_translation_cache
from .utils import _parse_frontmatter, _safe_read, _strip_frontmatter


# ───────── 카테고리 휴리스틱 (키워드 → 카테고리 id) ─────────

CMD_CATEGORIES = [
    ("build",       "🔧 빌드 / 컴파일",     ["build", "compile", "resolve", "fix-build", "linker"]),
    ("test",        "🧪 테스트 / TDD",      ["test", "tdd", "jest", "pytest", "e2e", "fixtures"]),
    ("review",      "🔍 코드 리뷰",          ["review", "audit", "simplify", "quality"]),
    ("security",    "🔒 보안",              ["security", "bounty", "hipaa", "compliance", "phi", "privacy", "secret"]),
    ("plan",        "🏗️ 계획 / 아키텍처",    ["plan", "architect", "design", "rfc", "blueprint", "adr"]),
    ("agent",       "🤖 에이전트 / 오케스트레이션", ["agent", "orchestr", "devfleet", "harness", "fleet", "team-builder", "loop"]),
    ("commit",      "📝 커밋 / PR / Git",    ["commit", "pr-", "git", "prp", "merge", "branch"]),
    ("skill",       "✨ 스킬 관리",          ["skill", "hookify", "instinct"]),
    ("docs",        "📚 문서 / 검색",        ["docs", "documentation", "search", "research", "exa", "context7"]),
    ("deploy",      "🚀 배포 / DevOps",      ["deploy", "docker", "ci", "cd", "release", "canary"]),
    ("lang-rust",   "🦀 Rust",              ["rust"]),
    ("lang-go",     "🐹 Go",                ["go-", "go_", "golang"]),
    ("lang-kotlin", "🎯 Kotlin / KMP",       ["kotlin", "android", "compose", "ktor"]),
    ("lang-cpp",    "⚙️ C++",              ["cpp", "c++", "cmake"]),
    ("lang-csharp", "🟦 C# / .NET",          ["csharp", "dotnet", "c#"]),
    ("lang-java",   "☕ Java / Spring",      ["java", "spring", "jpa", "gradle"]),
    ("lang-python", "🐍 Python",            ["python", "django", "flask", "pytest"]),
    ("lang-flutter","📱 Flutter / Dart",     ["flutter", "dart"]),
    ("lang-swift",  "🍎 Swift / iOS",        ["swift", "swiftui", "xcode", "ios", "foundation-model"]),
    ("lang-ts",     "🌀 TypeScript / Node",  ["typescript", "node", "bun", "nestjs", "nextjs", "nuxt"]),
    ("lang-php",    "🐘 PHP / Laravel",      ["laravel", "php"]),
    ("lang-perl",   "🐫 Perl",              ["perl"]),
    ("lang-sql",    "🗄️ SQL / DB",          ["database", "postgres", "clickhouse", "supabase", "jpa", "migration"]),
    ("healthcare",  "🏥 헬스케어",           ["healthcare", "emr", "hipaa", "cdss", "ehr", "phi"]),
    ("content",     "✍️ 콘텐츠 / 마케팅",     ["content", "article", "brand-voice", "seo", "crosspost", "social"]),
    ("ops",         "🛡️ 운영 / 모니터링",     ["ops", "watch", "monitor", "canary-watch", "healthcheck", "observability"]),
    ("ai-ml",       "🧠 AI / ML",           ["ml", "pytorch", "llm", "claude-api", "claude_api", "agent-sdk", "rag"]),
    ("web3",        "⛓️ Web3 / EVM",        ["evm", "solidity", "web3", "defi", "x402", "keccak"]),
    ("other",       "🛠️ 기타 / 범용",        []),
]


def _categorize_command(cmd: dict) -> tuple[str, str]:
    """명령어 id + description 기반 카테고리 결정."""
    text = (
        cmd.get("id", "") + " "
        + cmd.get("name", "") + " "
        + (cmd.get("description") or "")
    ).lower()
    for cat_id, cat_label, kws in CMD_CATEGORIES:
        for kw in kws:
            if kw in text:
                return cat_id, cat_label
    return "other", "🛠️ 기타 / 범용"


def list_commands() -> list:
    out: list = []
    # user global commands
    if COMMANDS_DIR.exists():
        for p in sorted(COMMANDS_DIR.rglob("*.md")):
            raw = _safe_read(p)
            meta = _parse_frontmatter(raw)
            rel = p.relative_to(COMMANDS_DIR)
            cid = str(rel).replace("/", ":").replace(".md", "")
            out.append({
                "id": cid,
                "name": meta.get("name", cid),
                "description": meta.get("description", "") or meta.get("argument-hint", ""),
                "scope": "user",
                "path": str(p),
                "content": _strip_frontmatter(raw)[:4000],
            })
    # plugin commands (scan plugin marketplaces, but skip .bak)
    if PLUGINS_DIR.exists():
        for plugin_md in PLUGINS_DIR.rglob("commands/*.md"):
            try:
                if ".bak" in str(plugin_md):
                    continue
                raw = _safe_read(plugin_md, 4000)
                meta = _parse_frontmatter(raw)
                cid = plugin_md.stem
                out.append({
                    "id": f"plugin:{cid}",
                    "name": meta.get("name", cid),
                    "description": meta.get("description", ""),
                    "scope": "plugin",
                    "path": str(plugin_md),
                    "content": _strip_frontmatter(raw)[:2000],
                })
            except Exception:
                continue
    # 카테고리 + 번역 주입
    tr_cache = _load_translation_cache()
    for c in out:
        cat_id, cat_label = _categorize_command(c)
        c["category"] = cat_id
        c["categoryLabel"] = cat_label
        c["descriptionKo"] = tr_cache.get(c["id"], "")
    return out


def _cache_key(kind: str, item_id: str) -> str:
    """번역 캐시 키 규칙. cmd 는 prefix 없이 id 만 (기존 호환)."""
    return f"{kind}:{item_id}" if kind != "cmd" else item_id
