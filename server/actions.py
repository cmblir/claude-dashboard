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


_CHAT_SYSTEM_PROMPT = """당신은 Claude Control Center 대시보드의 안내 도우미입니다.
사용자가 대시보드 기능에 대해 질문하면 친절하게 한국어로 답변하고, 관련 탭으로 안내합니다.

## 대시보드 탭 목록 (id → 설명)
- overview: 전체 개요 · 최적화 점수 · 시스템 요약
- projects: 프로젝트별 Claude 세팅 · AI 추천 · CLAUDE.md 관리
- analytics: 통계 & 스코어 · 30일 타임라인 · 도구 분포
- aiEval: AI 종합 평가 · Claude가 전체 셋업을 진단
- sessions: 세션 히스토리 · 과거 대화 검색 · 세션 품질 스코어
- agents: 에이전트 목록 · 상호작용 그래프 (vis-network)
- projectAgents: 프로젝트별 서브 에이전트 관리 · 16개 역할 프리셋
- skills: 사용자 정의 스킬 보기/편집
- commands: 슬래시 명령어 목록
- hooks: 이벤트 훅 설정
- permissions: 도구 권한 관리
- mcp: MCP 커넥터 · 외부 도구 연결
- plugins: 플러그인 관리
- settings: settings.json 편집
- claudemd: CLAUDE.md 편집 (마크다운 프리뷰)
- usage: 사용량 / 비용 추정
- metrics: 토큰 메트릭 상세
- memory: 프로젝트 메모리 관리
- tasks: 태스크 / TODO 관리
- team: 팀 / 조직 정보
- system: 시스템 상태 · 디바이스 정보

## 응답 규칙
1. 간결하게 2-3문장으로 답변
2. 관련 탭이 있으면 반드시 `navigate` 필드에 탭 id를 포함
3. JSON 형식으로만 응답:
{"answer": "답변 텍스트", "navigate": "tab_id 또는 null"}
"""

def api_chat(body: dict) -> dict:
    """챗봇 API — 사용자 질문을 받아 대시보드 안내 답변 반환."""
    if not isinstance(body, dict):
        return {"error": "잘못된 요청"}
    user_msg = (body.get("message") or "").strip()
    if not user_msg:
        return {"error": "메시지가 비어있습니다."}
    history = body.get("history") or []

    claude_bin = shutil.which("claude")
    if not claude_bin:
        return {"error": "Claude CLI 미설치"}
    if not api_auth_status().get("connected"):
        return {"error": "Claude 계정 연결 필요"}

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

    prompt_parts = [_CHAT_SYSTEM_PROMPT + lang_instruction]
    if conv_lines:
        prompt_parts.append("\n## 이전 대화\n" + "\n".join(conv_lines))
    prompt_parts.append(f"\n## 현재 질문\n사용자: {user_msg}\n\nJSON으로만 답변:")

    full_prompt = "\n".join(prompt_parts)

    try:
        proc = subprocess.run(
            [claude_bin, "-p", full_prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {"error": "응답 시간 초과 (30초)"}
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
    # navigate 검증
    valid_tabs = {
        "overview", "projects", "analytics", "aiEval", "sessions", "agents",
        "projectAgents", "skills", "commands", "hooks", "permissions", "mcp",
        "plugins", "settings", "claudemd", "usage", "metrics", "memory",
        "tasks", "team", "system", "features", "statusline", "plans",
        "envConfig", "modelConfig", "ideStatus", "scheduled", "backups",
        "bashHistory", "telemetry", "homunculus", "outputStyles",
    }
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

    prompt_parts = [_CHAT_SYSTEM_PROMPT + lang_instruction]
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

    try:
        proc = subprocess.Popen(
            [claude_bin, "-p", full_prompt, "--output-format", "stream-json",
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


def api_session_spawn(body: dict) -> dict:
    """새 Terminal 창을 열고 `claude [옵션] [prompt]` 실행. macOS 전용.

    body:
      cwd:                 "~/path"   (홈 하위)
      prompt:              "first message"     (선택)
      systemPrompt:        "..."      (--system-prompt)
      appendSystemPrompt:  "..."      (--append-system-prompt)
      allowedTools:        "Bash,..." (--allowed-tools)
      disallowedTools:     "..."      (--disallowed-tools)
      resumeSessionId:     "..."      (--resume)
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
    sys_prompt = (body.get("systemPrompt") or "").strip()
    app_prompt = (body.get("appendSystemPrompt") or "").strip()
    allowed = (body.get("allowedTools") or "").strip()
    disallowed = (body.get("disallowedTools") or "").strip()
    resume_id = (body.get("resumeSessionId") or "").strip()
    claude_bin = shutil.which("claude") or "claude"

    parts = [claude_bin]
    if sys_prompt: parts += ["--system-prompt", _sh_quote(sys_prompt)]
    if app_prompt: parts += ["--append-system-prompt", _sh_quote(app_prompt)]
    if allowed:    parts += ["--allowed-tools", _sh_quote(allowed)]
    if disallowed: parts += ["--disallowed-tools", _sh_quote(disallowed)]
    if resume_id:  parts += ["--resume", _sh_quote(resume_id)]
    if prompt:     parts += [_sh_quote(prompt)]
    shell_cmd = f'cd {_sh_quote(abs_cwd)} && ' + " ".join(parts)

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
    return {"ok": True, "terminal": "Terminal.app", "cwd": abs_cwd}

