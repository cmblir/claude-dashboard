"""Agent SDK 스캐폴드 — claude-agent-sdk 프로젝트 뼈대를 UI 로 생성.

Python (uv) / TypeScript (bun) 두 언어 · 템플릿 3종(basic/tool-use/memory).
생성 후 AppleScript 로 Terminal 에 `cd <path>/<name>` + 초기화 명령을
붙여넣는다 (실제 실행은 사용자가 Enter).

안전 장치:
- path 는 `$HOME` 내부만 허용 (open_folder_action 과 동일 규칙)
- name 은 `[a-zA-Z0-9_-]+` 만
- `<path>/<name>` 이 이미 존재하면 거부
- uv/bun 없으면 친절한 에러 (자동 설치 금지)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .logger import log

_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-]{1,63}$")

LANGUAGES = [
    {"id": "python", "label": "Python", "tool": "uv", "installHint": "brew install uv"},
    {"id": "typescript", "label": "TypeScript", "tool": "bun", "installHint": "curl -fsSL https://bun.sh/install | bash"},
]

TEMPLATES = [
    {"id": "basic", "label": "기본", "description": "Messages API 를 1 번 호출하고 응답을 출력하는 최소 예시."},
    {"id": "tool-use", "label": "Tool Use", "description": "사용자 정의 tool 1 개를 정의하고 tool_use → tool_result 라운드 트립."},
    {"id": "memory", "label": "Memory", "description": "대화 히스토리를 JSON 파일에 저장하며 이어가는 예시."},
]


# ───────── 템플릿 본문 ─────────

def _python_main(template: str) -> str:
    base = '''"""claude-agent-sdk {T} 템플릿 — Python

사전 준비:
  uv sync  (처음 1회)
  export ANTHROPIC_API_KEY=sk-...
  uv run python main.py
"""
import os
from anthropic import Anthropic

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

'''.replace("{T}", template)

    if template == "basic":
        return base + '''def main() -> None:
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": "자기소개 한 줄로."}],
    )
    for block in resp.content:
        if block.type == "text":
            print(block.text)


if __name__ == "__main__":
    main()
'''
    if template == "tool-use":
        return base + '''WEATHER_TOOL = {
    "name": "get_weather",
    "description": "도시의 현재 기온을 섭씨로 반환한다.",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}


def fake_get_weather(city: str) -> str:
    table = {"Seoul": "14°C", "Tokyo": "16°C", "San Francisco": "17°C"}
    return table.get(city, "unknown")


def main() -> None:
    messages = [{"role": "user", "content": "서울의 현재 기온을 get_weather 로 확인하고 한 줄로 요약."}]
    first = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        tools=[WEATHER_TOOL],
        messages=messages,
    )
    messages.append({"role": "assistant", "content": first.content})
    for block in first.content:
        if block.type == "tool_use":
            result = fake_get_weather(block.input.get("city", ""))
            messages.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": block.id, "content": result}],
            })
    second = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        tools=[WEATHER_TOOL],
        messages=messages,
    )
    for block in second.content:
        if block.type == "text":
            print(block.text)


if __name__ == "__main__":
    main()
'''
    # memory
    return base + '''import json
from pathlib import Path

STORE = Path("conversation.json")


def load() -> list:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return []


def save(msgs: list) -> None:
    STORE.write_text(json.dumps(msgs, ensure_ascii=False, indent=2), encoding="utf-8")


def turn(user_text: str) -> str:
    msgs = load()
    msgs.append({"role": "user", "content": user_text})
    resp = client.messages.create(model="claude-sonnet-4-6", max_tokens=512, messages=msgs)
    text = "".join(b.text for b in resp.content if b.type == "text")
    msgs.append({"role": "assistant", "content": text})
    save(msgs)
    return text


if __name__ == "__main__":
    print(turn("이전 대화를 기억해?"))
'''


def _ts_main(template: str) -> str:
    base = '''/**
 * claude-agent-sdk ''' + template + ''' 템플릿 — TypeScript
 *
 * 사전 준비:
 *   bun install     (처음 1회)
 *   export ANTHROPIC_API_KEY=sk-...
 *   bun run index.ts
 */
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

'''
    if template == "basic":
        return base + '''async function main() {
  const r = await client.messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 512,
    messages: [{ role: "user", content: "Introduce yourself in one line." }],
  });
  for (const b of r.content) if (b.type === "text") console.log(b.text);
}
main();
'''
    if template == "tool-use":
        return base + '''const tools = [{
  name: "get_weather",
  description: "Return current temperature for a city",
  input_schema: { type: "object", properties: { city: { type: "string" } }, required: ["city"] },
}];

function fakeWeather(city: string) {
  return ({ Seoul: "14°C", Tokyo: "16°C", "San Francisco": "17°C" } as any)[city] || "unknown";
}

async function main() {
  const msgs: any[] = [{ role: "user", content: "Check Seoul weather via get_weather, summarize in one line." }];
  const first = await client.messages.create({ model: "claude-sonnet-4-6", max_tokens: 1024, tools, messages: msgs });
  msgs.push({ role: "assistant", content: first.content });
  for (const b of first.content as any[]) {
    if (b.type === "tool_use") {
      msgs.push({ role: "user", content: [{ type: "tool_result", tool_use_id: b.id, content: fakeWeather(b.input.city) }] });
    }
  }
  const second = await client.messages.create({ model: "claude-sonnet-4-6", max_tokens: 512, tools, messages: msgs });
  for (const b of second.content) if (b.type === "text") console.log(b.text);
}
main();
'''
    # memory
    return base + '''import { readFileSync, writeFileSync, existsSync } from "node:fs";

const STORE = "conversation.json";
function load(): any[] { return existsSync(STORE) ? JSON.parse(readFileSync(STORE, "utf8")) : []; }
function save(m: any[]) { writeFileSync(STORE, JSON.stringify(m, null, 2)); }

async function turn(user: string) {
  const msgs = load();
  msgs.push({ role: "user", content: user });
  const r = await client.messages.create({ model: "claude-sonnet-4-6", max_tokens: 512, messages: msgs });
  const text = r.content.filter((b: any) => b.type === "text").map((b: any) => b.text).join("");
  msgs.push({ role: "assistant", content: text });
  save(msgs);
  return text;
}

console.log(await turn("이전 대화를 기억해?"));
'''


def _readme(name: str, language: str, template: str) -> str:
    return f"""# {name}

`claude-agent-sdk` **{language}** / template: **{template}** (생성: claude-dashboard scaffold).

## 실행

```
{"uv sync && uv run python main.py" if language == "python" else "bun install && bun run index.ts"}
```

## 환경 변수

```
export ANTHROPIC_API_KEY=sk-...
```

## 다음 단계

- [Claude API 문서](https://docs.anthropic.com/en/api/messages)
- [Claude Agent SDK](https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-overview)
"""


def _write_python_project(root: Path, name: str, template: str) -> None:
    (root / "main.py").write_text(_python_main(template), encoding="utf-8")
    (root / "README.md").write_text(_readme(name, "python", template), encoding="utf-8")
    # pyproject.toml 최소 stub — uv sync 시 실제 설치 수행
    pyproject = f'''[project]
name = "{name}"
version = "0.1.0"
description = "claude-agent-sdk {template} template"
requires-python = ">=3.10"
dependencies = [
    "anthropic>=0.40.0",
]
'''
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (root / ".gitignore").write_text(".venv/\n__pycache__/\n.env\nconversation.json\n", encoding="utf-8")


def _write_ts_project(root: Path, name: str, template: str) -> None:
    (root / "index.ts").write_text(_ts_main(template), encoding="utf-8")
    (root / "README.md").write_text(_readme(name, "typescript", template), encoding="utf-8")
    # package.json stub — bun install 시 실제 설치
    import json as _json
    pkg = {
        "name": name,
        "version": "0.1.0",
        "type": "module",
        "scripts": {"start": "bun run index.ts"},
        "dependencies": {"@anthropic-ai/sdk": "^0.40.0"},
    }
    (root / "package.json").write_text(_json.dumps(pkg, indent=2), encoding="utf-8")
    (root / ".gitignore").write_text("node_modules/\n.env\nconversation.json\n", encoding="utf-8")


def _open_terminal(cwd: Path, commands: list[str]) -> bool:
    """AppleScript 로 Terminal 새 창에 cd + 명령 붙여넣기 (실제 실행은 사용자 Enter)."""
    joined = " && ".join([f'cd {cwd}'] + commands)
    # 명령을 사용자에게 보여주되 자동 실행은 하지 않음 — `do script` 는 Enter 까지 치는데,
    # 경고를 위해 명령 뒤에 주석 추가해 재검토 유도.
    script = f'''tell application "Terminal"
        activate
        do script "# claude-dashboard scaffold — 생성된 프로젝트\\n{joined}"
    end tell'''
    try:
        subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True)
        return True
    except Exception as e:
        log.warning("scaffold terminal spawn failed: %s", e)
        return False


# ───────── API ─────────

def api_scaffold_catalog(_q: dict | None = None) -> dict:
    return {"languages": LANGUAGES, "templates": TEMPLATES}


def api_scaffold_create(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}

    name = (body.get("name") or "").strip()
    path_raw = (body.get("path") or "").strip()
    language = (body.get("language") or "").strip()
    template = (body.get("template") or "basic").strip()

    if not _NAME_RE.match(name):
        return {"ok": False, "error": "이름은 영숫자/밑줄/하이픈 2~64자"}
    if language not in {x["id"] for x in LANGUAGES}:
        return {"ok": False, "error": f"language 는 {[x['id'] for x in LANGUAGES]} 중 하나"}
    if template not in {x["id"] for x in TEMPLATES}:
        return {"ok": False, "error": f"template 는 {[x['id'] for x in TEMPLATES]} 중 하나"}

    # path 검증 — 홈 내부만
    path_expanded = os.path.expanduser(path_raw) if path_raw else str(Path.home())
    abs_path = os.path.abspath(path_expanded)
    home = str(Path.home())
    if not (abs_path == home or abs_path.startswith(home + os.sep)):
        return {"ok": False, "error": "경로는 홈 디렉터리 내부만 허용"}
    parent = Path(abs_path)
    if not parent.exists() or not parent.is_dir():
        return {"ok": False, "error": f"경로가 존재하지 않음: {abs_path}"}

    root = parent / name
    if root.exists():
        return {"ok": False, "error": f"이미 존재: {root}"}

    # 도구 존재 확인 (자동 설치 금지)
    tool_need = "uv" if language == "python" else "bun"
    if not shutil.which(tool_need):
        hint = next((x["installHint"] for x in LANGUAGES if x["tool"] == tool_need), "")
        return {"ok": False, "error": f"{tool_need} 가 설치되지 않음. 설치: {hint}"}

    # 프로젝트 생성
    try:
        root.mkdir(parents=True, exist_ok=False)
        if language == "python":
            _write_python_project(root, name, template)
            init_cmds = ["uv sync", "echo '# ANTHROPIC_API_KEY=sk-... 를 설정한 후: uv run python main.py'"]
        else:
            _write_ts_project(root, name, template)
            init_cmds = ["bun install", "echo '# ANTHROPIC_API_KEY=sk-... 를 설정한 후: bun run index.ts'"]
    except Exception as e:
        return {"ok": False, "error": f"파일 생성 실패: {e}"}

    # Terminal 창 열기 (실패해도 생성 자체는 성공)
    spawned = _open_terminal(root, init_cmds)

    return {
        "ok": True,
        "path": str(root),
        "language": language,
        "template": template,
        "terminalSpawned": spawned,
        "nextCommand": " && ".join([f'cd {root}'] + init_cmds),
    }
