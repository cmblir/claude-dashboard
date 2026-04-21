"""슬래시 명령어 (`~/.claude/commands/*.md` + 플러그인 커맨드) 목록 + 카테고리 + 번역 배치.

번역 배치 (`api_translate_batch`) 는 cmd/skill/plugin/agent 의 description
을 Claude CLI 한 번 호출로 번역 후 로컬 캐시에 저장 — skills/agents/plugins
를 순환 없이 참조하기 위해 late import 사용.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from .config import COMMANDS_DIR, PLUGINS_DIR
from .translations import _load_translation_cache, _save_translation_cache
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
    # 카테고리 + 번역 주입 (ko/en/zh 모두)
    tr_cache = _load_translation_cache()
    for c in out:
        cat_id, cat_label = _categorize_command(c)
        c["category"] = cat_id
        c["categoryLabel"] = cat_label
        # legacy: descriptionKo 유지
        c["descriptionKo"] = tr_cache.get(_cache_key("cmd", c["id"], "ko"), "")
        c["descriptionEn"] = tr_cache.get(_cache_key("cmd", c["id"], "en"), "")
        c["descriptionZh"] = tr_cache.get(_cache_key("cmd", c["id"], "zh"), "")
    return out


def _cache_key(kind: str, item_id: str, lang: str = "ko") -> str:
    """번역 캐시 키 규칙.

    - ko (기본): cmd 는 prefix 없이 id 만, 나머지는 `{kind}:{id}` (legacy 호환)
    - 기타 언어: `{lang}:{kind}:{id}`
    """
    if lang == "ko":
        return f"{kind}:{item_id}" if kind != "cmd" else item_id
    return f"{lang}:{kind}:{item_id}"


# ───────── 번역 배치 (cmd/skill/plugin/agent 공용) ─────────

def _collect_translate_items(kind: str) -> list:
    """kind 에 따라 [{id, desc}, ...] 수집. 순환 회피를 위해 late import."""
    items: list = []
    if kind == "cmd":
        for c in list_commands():
            d = c.get("description") or ""
            if d:
                items.append({"id": c["id"], "desc": d[:320]})
    elif kind == "skill":
        from .skills import list_skills
        for s in list_skills():
            d = s.get("description") or ""
            if d:
                items.append({"id": s["id"], "desc": d[:320]})
    elif kind == "plugin":
        from .plugins import api_plugins_browse
        for p in api_plugins_browse().get("plugins", []):
            d = p.get("description") or ""
            if d:
                items.append({"id": p["id"], "desc": d[:320]})
    elif kind == "agent":
        from .agents import list_agents
        for a in list_agents().get("agents", []):
            d = a.get("description") or ""
            if d:
                items.append({"id": a["id"], "desc": d[:320]})
    return items


_LANG_PROMPT = {
    "ko": {
        "label": "한국어",
        "instructions": "- 기술용어(Claude Code, PR, CLI 등)는 그대로 유지.\n"
                        "- 20~70자 정도, 핵심 동사 포함 (\"~한다\" 체).\n"
                        "- 한국어 요약이 불가능하면 원문 기술 용어 나열.",
    },
    "en": {
        "label": "English",
        "instructions": "- Keep technical terms (Claude Code, PR, CLI, etc.) as-is.\n"
                        "- One concise sentence, 10-20 words, present tense.\n"
                        "- If the input is already English, lightly polish and return.",
    },
    "zh": {
        "label": "简体中文",
        "instructions": "- 保留技术术语（Claude Code、PR、CLI 等）。\n"
                        "- 简洁一句话（20-40 字），使用动词短语。\n"
                        "- 若输入已是中文，轻度润色后返回。",
    },
}


def api_translate_batch(body: dict) -> dict:
    """범용 번역 배치.

    body:
      kind        : 'cmd' | 'skill' | 'plugin' | 'agent'
      targetLang  : 'ko' | 'en' | 'zh'  (기본 'ko', legacy 호환)
      limit       : 5~60, 기본 50

    캐시에 없는 항목만 Claude CLI 로 번역.
    """
    from .auth import api_auth_status

    claude_bin = shutil.which("claude")
    if not claude_bin:
        return {"error": "claude CLI 설치 필요"}
    if not api_auth_status().get("connected"):
        return {"error": "Claude 계정 연결 필요"}

    body = body or {}
    kind = body.get("kind") if isinstance(body, dict) else "cmd"
    if kind not in ("cmd", "skill", "plugin", "agent"):
        return {"error": "unknown kind"}
    target_lang = (body.get("targetLang") or body.get("lang") or "ko").lower()
    if target_lang not in _LANG_PROMPT:
        return {"error": f"unknown targetLang: {target_lang}"}
    limit = min(60, max(5, int(body.get("limit") or 50)))

    cache = _load_translation_cache()
    all_items = _collect_translate_items(kind)
    pending = [
        x for x in all_items
        if not cache.get(_cache_key(kind, x["id"], target_lang))
    ]
    if not pending:
        return {"translated": 0, "requested": 0, "remaining": 0,
                "total": len(all_items), "done": True,
                "targetLang": target_lang}

    batch = pending[:limit]
    kind_label = {"cmd": "slash command", "skill": "skill",
                  "plugin": "plugin", "agent": "agent"}[kind]
    lang_cfg = _LANG_PROMPT[target_lang]

    prompt = f"""Translate each Claude Code {kind_label} description below into **concise {lang_cfg['label']} (one line)**.
{lang_cfg['instructions']}

입력/Input:
{json.dumps(batch, ensure_ascii=False, indent=2)}

JSON 만 출력 / Output JSON only:
{{"translations": {{"<id>": "<translation>", ...}}}}
"""
    try:
        proc = subprocess.run(
            [claude_bin, "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=300,
        )
    except Exception as e:
        return {"error": f"Claude CLI 실행 실패: {e}"}
    if proc.returncode != 0:
        return {"error": f"Claude CLI 오류: {(proc.stderr or '')[:400]}"}

    stdout = (proc.stdout or "").strip()
    response_text = stdout
    try:
        meta = json.loads(stdout)
        if isinstance(meta, dict):
            response_text = meta.get("result") or stdout
    except Exception:
        pass
    m = re.search(r'\{[\s\S]*"translations"[\s\S]*\}', response_text)
    if not m:
        return {"error": "번역 JSON 없음", "raw": response_text[:1500]}
    try:
        parsed = json.loads(m.group(0))
        tr = parsed.get("translations", {})
    except Exception as e:
        return {"error": f"JSON 파싱 실패: {e}", "raw": response_text[:1500]}

    added = 0
    for item_id, val in tr.items():
        if isinstance(val, str) and val.strip():
            cache[_cache_key(kind, item_id, target_lang)] = val.strip()
            added += 1
    _save_translation_cache(cache)

    remaining = max(0, len(pending) - added)
    return {
        "translated": added, "requested": len(batch),
        "remaining": remaining, "total": len(all_items),
        "done": remaining == 0, "targetLang": target_lang,
    }


def api_commands_translate(body: dict) -> dict:
    """하위 호환 shim — kind=cmd 로 강제."""
    b = dict(body or {})
    b["kind"] = "cmd"
    return api_translate_batch(b)
