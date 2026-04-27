"""액션 엔드포인트 — 터미널 활성화 · 폴더 열기 · 챗 API · SSE 스트림.

사이드 이펙트가 있는 엔드포인트들을 모아둔 모듈. 챗봇은 `claude -p` 를
호출하고, 터미널 활성화는 AppleScript 로 홈 디렉토리 내 대상만 허용한다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .config import SESSIONS_DIR
from .utils import _safe_read


def _find_terminal_app_for_pid(pid: int) -> str:
    terminal_apps = {"Terminal", "iTerm2", "Alacritty", "kitty", "Warp", "Hyper", "WezTerm"}
    current = pid
    for _ in range(20):
        try:
            line = subprocess.check_output(["ps", "-o", "ppid=,comm=", "-p", str(current)], text=True, timeout=3).strip()
        except Exception:
            break
        parts = line.split(None, 1)
        if len(parts) < 2:
            break
        ppid_str, comm = parts
        app_name = Path(comm).name
        if app_name in terminal_apps:
            return app_name
        try:
            current = int(ppid_str)
        except ValueError:
            break
        if current <= 1:
            break
    return ""


def open_session_action(body: dict) -> dict:
    session_id = body.get("sessionId") if isinstance(body, dict) else None
    if not session_id:
        return {"ok": False, "error": "no sessionId"}
    session_file = SESSIONS_DIR / f"{session_id}.json"
    found = None
    if session_file.exists():
        try:
            found = json.loads(_safe_read(session_file))
        except Exception:
            return {"ok": False, "error": "session unreadable"}
    else:
        if SESSIONS_DIR.exists():
            for p in SESSIONS_DIR.glob("*.json"):
                try:
                    data = json.loads(_safe_read(p))
                    if isinstance(data, dict) and data.get("sessionId") == session_id:
                        found = data
                        break
                except Exception:
                    continue
    if not found:
        return {"ok": False, "error": "session not found"}
    pid = found.get("pid")
    if not pid:
        return {"ok": False, "error": "no pid"}
    try:
        os.kill(pid, 0)
    except OSError:
        return {"ok": False, "error": "process not running"}
    app = _find_terminal_app_for_pid(pid)
    if app:
        try:
            subprocess.run(["osascript", "-e", f'tell application "{app}" to activate'], timeout=3, capture_output=True)
        except Exception:
            pass
    return {"ok": True, "app": app or "unknown", "pid": pid}


from .nav_catalog import render_tab_catalog_prompt, keyword_routing_hints
from .version import get_version, get_latest_changelog


def _build_chat_system_prompt() -> str:
    """탭 카탈로그 + 최신 CHANGELOG 를 조합해 챗봇 시스템 프롬프트 생성.

    신규 탭·기능이 추가되면 nav_catalog.py 와 CHANGELOG.md 만 갱신해도
    챗봇이 자동으로 최신 정보를 알게 된다 — 이 함수는 매 요청 시점에
    호출되어 최신 파일 상태를 반영한다.
    """
    version = get_version()
    changelog = get_latest_changelog(2)
    return f"""당신은 Claude Control Center 대시보드 v{version} 의 안내 도우미입니다.
사용자가 대시보드 기능에 대해 질문하면 친절하게 한국어로 답변하고, 관련 탭으로 안내합니다.

## 대시보드 탭 목록 (id → 설명)
{render_tab_catalog_prompt()}

## 최근 릴리스 (CHANGELOG 요약)
{changelog}

## 라우팅 키워드 힌트
{keyword_routing_hints()}

## 응답 규칙
1. 간결하게 2-3문장으로 답변
2. 관련 탭이 있으면 반드시 `navigate` 필드에 **위 목록의 정확한 탭 id** 를 포함.
   존재하지 않는 탭 id 는 절대 꾸며내지 말 것. 확신이 없으면 null.
3. 위 '라우팅 키워드 힌트' 에 나오는 키워드가 질문에 포함되면 해당 탭으로 라우팅.
4. JSON 형식으로만 응답:
{{"answer": "답변 텍스트", "navigate": "tab_id 또는 null"}}
"""


# 런타임에 매 호출마다 생성 — nav_catalog/VERSION/CHANGELOG 변경이 즉시 반영
def _CHAT_SYSTEM_PROMPT() -> str:  # type: ignore[misc]
    return _build_chat_system_prompt()

def api_chat(body: dict) -> dict:
    """챗봇 API — 사용자 질문을 받아 대시보드 안내 답변 반환."""
    from .errors import err, ERROR_MESSAGES
    if not isinstance(body, dict):
        return {"error": ERROR_MESSAGES["bad_body"], "error_key": "err_bad_body"}
    user_msg = (body.get("message") or "").strip()
    if not user_msg:
        return {"error": ERROR_MESSAGES["msg_empty"], "error_key": "err_msg_empty"}
    history = body.get("history") or []

    claude_bin = shutil.which("claude")
    if not claude_bin:
        return {"error": ERROR_MESSAGES["cli_not_installed"], "error_key": "err_cli_not_installed"}
    if not api_auth_status().get("connected"):
        return {"error": ERROR_MESSAGES["auth_required"], "error_key": "err_auth_required"}

    # 대화 히스토리를 프롬프트에 포함
    conv_lines = []
    for h in history[-6:]:  # 최근 6개까지만
        role = h.get("role", "")
        text = h.get("text", "")
        if role == "user":
            conv_lines.append(f"사용자: {text}")
        elif role == "assistant":
            conv_lines.append(f"도우미: {text}")

    lang = (body.get("lang") or "ko").lower()
    lang_instruction = {"en": "\n\nIMPORTANT: Respond in English only.", "zh": "\n\nIMPORTANT: Respond in Chinese (简体中文) only."}.get(lang, "")

    prompt_parts = [_CHAT_SYSTEM_PROMPT() + lang_instruction]
    if conv_lines:
        prompt_parts.append("\n## 이전 대화\n" + "\n".join(conv_lines))
    prompt_parts.append(f"\n## 현재 질문\n사용자: {user_msg}\n\nJSON으로만 답변:")

    full_prompt = "\n".join(prompt_parts)

    # 챗봇은 간단한 JSON 라우팅이므로 저비용 Haiku 로 고정.
    # CHAT_MODEL 환경변수로 오버라이드 가능 (예: 고품질 필요 시 sonnet).
    chat_model = os.environ.get("CHAT_MODEL", "haiku")
    try:
        proc = subprocess.run(
            [claude_bin, "-p", full_prompt, "--model", chat_model, "--output-format", "json"],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {"error": "응답 시간 초과 (30초)", "error_key": "err_timeout"}
    except Exception as e:
        return {"error": f"CLI 실행 실패: {e}"}

    if proc.returncode != 0:
        return {"error": f"CLI 오류: {(proc.stderr or '')[:200]}"}

    stdout = (proc.stdout or "").strip()
    # --output-format json 은 {"result": "..."} 래핑
    response_text = stdout
    try:
        meta = json.loads(stdout)
        if isinstance(meta, dict) and "result" in meta:
            response_text = meta["result"]
    except Exception:
        pass

    # JSON 파싱 시도
    parsed = {}
    m = re.search(r"\{[\s\S]*\}", response_text)
    if m:
        try:
            parsed = json.loads(m.group(0))
        except Exception:
            pass

    answer = parsed.get("answer") or response_text[:500]
    navigate = parsed.get("navigate")
    # navigate 검증 — nav_catalog 에 정의된 탭 id 만 허용 (신규 탭 자동 반영)
    from .nav_catalog import TAB_CATALOG as _TC
    valid_tabs = {tid for tid, _g, _d, _k in _TC}
    if navigate and navigate not in valid_tabs:
        navigate = None

    return {"answer": answer, "navigate": navigate}


def handle_chat_stream(handler: "Handler", body: dict) -> None:
    """SSE 스트리밍 챗 — claude CLI stream-json 을 SSE 로 중계."""
    user_msg = (body.get("message") or "").strip() if isinstance(body, dict) else ""
    if not user_msg:
        handler.send_response(400)
        handler.send_header("Content-Type", "text/plain")
        handler.end_headers()
        handler.wfile.write(b"empty message")
        return

    claude_bin = shutil.which("claude")
    if not claude_bin:
        handler.send_response(500)
        handler.send_header("Content-Type", "text/plain")
        handler.end_headers()
        handler.wfile.write(b"claude CLI not found")
        return

    history = body.get("history") or []
    lang = (body.get("lang") or "ko").lower()
    lang_instruction = {"en": "\n\nIMPORTANT: Respond in English only.", "zh": "\n\nIMPORTANT: Respond in Chinese (简体中文) only."}.get(lang, "")

    conv_lines = []
    for h in history[-6:]:
        role = h.get("role", "")
        text = h.get("text", "")
        if role == "user":
            conv_lines.append(f"사용자: {text}")
        elif role == "assistant":
            conv_lines.append(f"도우미: {text}")

    prompt_parts = [_CHAT_SYSTEM_PROMPT() + lang_instruction]
    if conv_lines:
        prompt_parts.append("\n## 이전 대화\n" + "\n".join(conv_lines))
    prompt_parts.append(f"\n## 현재 질문\n사용자: {user_msg}\n\nJSON으로만 답변:")
    full_prompt = "\n".join(prompt_parts)

    # SSE 헤더
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()

    def _sse(event: str, data: str) -> None:
        chunk = f"event: {event}\ndata: {data}\n\n"
        try:
            handler.wfile.write(chunk.encode("utf-8"))
            handler.wfile.flush()
        except Exception:
            pass

    # 스트리밍 챗도 동일하게 Haiku 사용 (CHAT_MODEL env 로 오버라이드)
    chat_model = os.environ.get("CHAT_MODEL", "haiku")
    try:
        proc = subprocess.Popen(
            [claude_bin, "-p", full_prompt, "--model", chat_model,
             "--output-format", "stream-json",
             "--verbose", "--include-partial-messages"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        full_text = ""
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            msg_type = obj.get("type")
            if msg_type == "assistant":
                content = (obj.get("message") or {}).get("content") or []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        new_text = block.get("text", "")
                        if len(new_text) > len(full_text):
                            delta = new_text[len(full_text):]
                            full_text = new_text
                            _sse("delta", json.dumps({"text": delta}, ensure_ascii=False))
            elif msg_type == "result":
                result_text = obj.get("result", "")
                if result_text and not full_text:
                    full_text = result_text
                    _sse("delta", json.dumps({"text": result_text}, ensure_ascii=False))
                # navigate 추출
                navigate = None
                m = re.search(r"\{[\s\S]*\}", full_text)
                if m:
                    try:
                        parsed = json.loads(m.group(0))
                        nav = parsed.get("navigate")
                        answer = parsed.get("answer", "")
                        if nav:
                            navigate = nav
                        # 만약 JSON 형태로 답변이 왔으면 answer 부분만 다시 전송
                        if answer and answer != full_text:
                            _sse("replace", json.dumps({"text": answer}, ensure_ascii=False))
                            full_text = answer
                    except Exception:
                        pass
                _sse("done", json.dumps({"navigate": navigate, "text": full_text}, ensure_ascii=False))
        proc.wait(timeout=5)
    except Exception as e:
        _sse("error", json.dumps({"error": str(e)}, ensure_ascii=False))


def open_folder_action(body: dict) -> dict:
    raw = body.get("folderPath") if isinstance(body, dict) else None
    if not raw:
        return {"ok": False, "error": "no folderPath"}
    expanded = os.path.expanduser(raw)
    abs_path = os.path.abspath(expanded)
    home = str(Path.home())
    if not (abs_path == home or abs_path.startswith(home + os.sep)):
        return {"ok": False, "error": "outside home"}
    if not Path(abs_path).exists():
        return {"ok": False, "error": "not found"}
    try:
        subprocess.Popen(["open", abs_path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": abs_path}


def _applescript_escape(s: str) -> str:
    """AppleScript 문자열 리터럴용 이스케이프 — \\ 과 " 만 처리."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _sh_quote(s: str) -> str:
    """single-quoted 쉘 이스케이프. 내부 ' 는 '\\'' 로 분리."""
    return "'" + s.replace("'", "'\\''") + "'"


def _resolve_provider_cli(assignee: str) -> dict:
    """Map ``provider:model`` assignee to the actual CLI binary + flags.

    Returns ``{provider, bin, args, model, fallback_reason}``. ``args`` is a
    list of pre-quoted shell tokens (model flag etc.); the caller appends
    prompt/options. Falls back to claude when the requested CLI isn't
    installed and records a ``fallback_reason``."""
    a = (assignee or "").strip()
    provider_hint = ""
    model = ""
    if ":" in a:
        provider_hint, model = a.split(":", 1)
        provider_hint = provider_hint.strip().lower()
        model = model.strip()
    elif a:
        provider_hint = a.strip().lower()

    PROVIDER_ALIASES = {
        "claude": "claude-cli", "claude-cli": "claude-cli",
        "anthropic": "claude-cli", "anthropic-api": "claude-cli",
        "gemini": "gemini-cli", "gemini-cli": "gemini-cli",
        "google": "gemini-cli", "gemini-api": "gemini-cli",
        "ollama": "ollama", "ollama-api": "ollama",
        "codex": "codex",
        "openai": "codex", "gpt": "codex", "openai-api": "codex",
    }
    pid = PROVIDER_ALIASES.get(provider_hint, "claude-cli")

    def _which_safe(name: str) -> str:
        try:
            from .ai_providers import _which
            return _which(name)
        except Exception:
            return shutil.which(name) or ""

    fallback_reason = ""
    if pid == "gemini-cli":
        b = _which_safe("gemini")
        if b:
            args = ["--model", _sh_quote(model)] if model else []
            return {"provider": "gemini-cli", "bin": b, "args": args, "model": model, "fallback_reason": ""}
        fallback_reason = "gemini CLI not installed — falling back to claude"
        pid = "claude-cli"
    elif pid == "ollama":
        b = _which_safe("ollama")
        if b and model:
            return {"provider": "ollama", "bin": b, "args": ["run", _sh_quote(model)], "model": model, "fallback_reason": ""}
        if b:
            return {"provider": "ollama", "bin": b, "args": [], "model": "", "fallback_reason": "no model — opening interactive ollama shell"}
        fallback_reason = "ollama CLI not installed — falling back to claude"
        pid = "claude-cli"
    elif pid == "codex":
        b = _which_safe("codex")
        if b:
            args = ["--model", _sh_quote(model)] if model else []
            return {"provider": "codex", "bin": b, "args": args, "model": model, "fallback_reason": ""}
        fallback_reason = "codex CLI not installed — falling back to claude"
        pid = "claude-cli"

    # claude-cli (default + every fallback)
    claude_bin = _which_safe("claude") or "claude"
    return {"provider": "claude-cli", "bin": claude_bin, "args": [],
            "model": model if pid == "claude-cli" else "",
            "fallback_reason": fallback_reason}


def api_session_spawn(body: dict) -> dict:
    """Open a new Terminal window and run the AI CLI matching the node's
    ``assignee`` (e.g. ``claude:opus``, ``gemini:gemini-2.5-pro``,
    ``ollama:llama3.1``, ``codex:o4-mini``). macOS only.

    body:
      cwd:                 "~/path"   (under $HOME)
      assignee:            "provider:model"  (optional — defaults to claude)
      prompt:              "first message"     (optional)
      systemPrompt:        "..."      (claude only)
      appendSystemPrompt:  "..."      (claude only)
      allowedTools:        "Bash,..." (claude only)
      disallowedTools:     "..."      (claude only)
      resumeSessionId:     "..."      (claude only)
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    raw_cwd = (body.get("cwd") or "").strip()
    if not raw_cwd:
        return {"ok": False, "error": "no cwd"}
    expanded = os.path.expanduser(raw_cwd)
    abs_cwd = os.path.abspath(expanded)
    home = str(Path.home())
    if not (abs_cwd == home or abs_cwd.startswith(home + os.sep)):
        return {"ok": False, "error": "cwd must be under home"}
    if not Path(abs_cwd).is_dir():
        return {"ok": False, "error": "cwd not found"}

    prompt = (body.get("prompt") or "").strip()
    assignee = (body.get("assignee") or "").strip()
    resolved = _resolve_provider_cli(assignee)
    provider = resolved["provider"]
    bin_path = resolved["bin"]

    parts = [bin_path] + list(resolved["args"])

    if provider == "claude-cli":
        sys_prompt = (body.get("systemPrompt") or "").strip()
        app_prompt = (body.get("appendSystemPrompt") or "").strip()
        allowed = (body.get("allowedTools") or "").strip()
        disallowed = (body.get("disallowedTools") or "").strip()
        resume_id = (body.get("resumeSessionId") or "").strip()
        if resolved.get("model"):
            parts += ["--model", _sh_quote(resolved["model"])]
        if sys_prompt: parts += ["--system-prompt", _sh_quote(sys_prompt)]
        if app_prompt: parts += ["--append-system-prompt", _sh_quote(app_prompt)]
        if allowed:    parts += ["--allowed-tools", _sh_quote(allowed)]
        if disallowed: parts += ["--disallowed-tools", _sh_quote(disallowed)]
        if resume_id:  parts += ["--resume", _sh_quote(resume_id)]

    # claude takes a positional prompt and stays interactive (TUI); the
    # other CLIs (gemini, ollama run <model>, codex) treat a positional as
    # one-shot, so we print the prompt as a banner instead and launch the
    # CLI interactively.
    cli_cmd = " ".join(parts)
    if prompt and provider == "claude-cli":
        shell_cmd = f'cd {_sh_quote(abs_cwd)} && {cli_cmd} {_sh_quote(prompt)}'
    elif prompt:
        banner = (
            "echo '────── Prompt ──────'; "
            f"printf '%s\\n' {_sh_quote(prompt)}; "
            "echo '────────────────────'; "
        )
        shell_cmd = f'cd {_sh_quote(abs_cwd)} && {banner}{cli_cmd}'
    else:
        shell_cmd = f'cd {_sh_quote(abs_cwd)} && {cli_cmd}'

    script = f'''
tell application "Terminal"
    activate
    do script "{_applescript_escape(shell_cmd)}"
end tell
'''
    try:
        r = subprocess.run(
            ["osascript", "-e", script], timeout=5, capture_output=True, text=True,
        )
        if r.returncode != 0:
            return {"ok": False, "error": (r.stderr or "osascript failed").strip()}
    except FileNotFoundError:
        return {"ok": False, "error": "osascript not available (macOS only)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "terminal": "Terminal.app",
        "cwd": abs_cwd,
        "provider": provider,
        "cli": bin_path,
        "model": resolved.get("model", ""),
        "fallbackReason": resolved.get("fallback_reason", ""),
    }

