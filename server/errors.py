"""백엔드 에러 메시지 i18n 키 매핑.

에러 응답에 error_key 필드를 추가하여 프론트엔드에서 번역된 메시지를 표시할 수 있게 한다.
실제 에러 메시지(한글)는 하위 호환을 위해 유지하되, error_key 로 locale 기반 표시 가능.

사용법:
    from .errors import err
    return err("cli_not_installed")  # → {"ok": False, "error": "Claude CLI 미설치", "error_key": "err_cli_not_installed"}
    return err("cli_not_installed", detail="claude")  # → detail 추가
"""
from __future__ import annotations

# 에러 키 → 기본 메시지 (한글, 하위 호환용)
ERROR_MESSAGES: dict[str, str] = {
    # ── 공통 ──
    "bad_body":               "잘못된 요청",
    "cli_not_installed":      "Claude CLI 미설치",
    "cli_not_found":          "Claude CLI 를 찾을 수 없습니다",
    "auth_required":          "Claude 계정 연결 필요",
    "timeout":                "응답 시간 초과",
    "cli_error":              "CLI 실행 오류",
    "json_parse_error":       "JSON 파싱 실패",
    "not_found":              "찾을 수 없습니다",
    "invalid_id":             "유효하지 않은 ID",
    "outside_home":           "홈 디렉토리 밖 경로 거부",
    "path_not_found":         "경로가 존재하지 않습니다",
    "not_directory":          "디렉토리가 아님 또는 존재하지 않음",

    # ── 에이전트 ──
    "agent_name_invalid":     "이름은 소문자/숫자/-/_ 만 (첫 글자 영숫자)",
    "agent_exists":           "이미 존재 — overwrite=true 로 덮어쓰기",
    "agent_builtin_readonly": "빌트인 에이전트는 삭제할 수 없습니다",
    "agent_plugin_readonly":  "플러그인 에이전트는 마켓플레이스에서 관리 — 삭제는 비활성화로",

    # ── 인증 ──
    "login_terminal_opened":  "터미널에서 로그인 창이 열렸습니다. 브라우저 인증 완료 후 돌아오세요.",
    "logout_success":         "로그아웃 되었습니다.",
    "no_claude_json":         "~/.claude.json 이 없습니다 — Claude Code에 로그인하세요.",

    # ── MCP ──
    "mcp_values_missing":     "필수 값 누락",
    "mcp_already_registered": "이미 등록된 이름입니다 — 다른 이름으로 시도하세요",
    "mcp_not_registered":     "등록된 MCP 서버가 아닙니다",
    "mcp_cwd_name_required":  "cwd 와 name 필수",

    # ── 권한 ──
    "permission_invalid":     "유효하지 않은 권한 규칙",

    # ── 플러그인 ──
    "marketplace_name_invalid": "이름은 영숫자/-/_/. 만 허용",
    "marketplace_url_required": "git URL 필요",
    "marketplace_not_found":    "등록된 마켓플레이스가 아닙니다",

    # ── 스킬 ──
    "skill_plugin_readonly":  "플러그인 스킬은 편집 불가 (read-only)",

    # ── 훅 ──
    "hook_file_not_found":    "플러그인 훅 파일을 찾을 수 없음",
    "hook_parse_error":       "hooks.json 파싱 실패",
    "hook_index_error":       "인덱스 범위 오류",
    "hook_save_error":        "저장 실패",

    # ── 프로바이더 ──
    "provider_id_invalid":    "id 는 소문자/숫자/-/_ 만 (2~41자)",
    "provider_reserved":      "빌트인 프로바이더 — 다른 id 사용",
    "provider_not_found":     "프로바이더를 찾을 수 없습니다",
    "prompt_required":        "프롬프트를 입력하세요",
    "providers_required":     "프로바이더 목록 필수",

    # ── 워크플로우 ──
    "workflow_not_found":     "워크플로우를 찾을 수 없습니다",
    "workflow_cycle":         "워크플로우에 순환이 있습니다",
    "workflow_invalid":       "유효하지 않은 워크플로우 구조",
    "workflow_stale":         "동시 수정 감지 — 새로고침 후 다시 시도",

    # ── 번역 ──
    "translate_no_cli":       "Claude CLI 설치 필요",
    "translate_no_auth":      "Claude 계정 연결 필요",
    "translate_no_json":      "번역 JSON 을 찾지 못했습니다",

    # ── AI 평가 ──
    "eval_cli_timeout":       "Claude CLI 시간 초과 — 다시 시도해 주세요",
    "eval_cli_error":         "Claude CLI 실행 실패",
    "eval_no_json":           "Claude 응답에서 JSON 을 찾지 못했습니다",

    # ── 메시지 (ok 응답용) ──
    "msg_empty":              "메시지가 비어있습니다.",
}


def err(key: str, *, detail: str = "", code: int = 0) -> dict:
    """에러 응답 생성. error_key 포함하여 프론트에서 i18n 가능.

    사용: return err("cli_not_installed")
    결과: {"ok": False, "error": "Claude CLI 미설치", "error_key": "err_cli_not_installed"}
    """
    msg = ERROR_MESSAGES.get(key, key)
    if detail:
        msg = f"{msg}: {detail}"
    return {"ok": False, "error": msg, "error_key": f"err_{key}"}


def msg(key: str, *, detail: str = "") -> str:
    """성공 메시지 조회. locale 키는 msg_{key}."""
    m = ERROR_MESSAGES.get(key, key)
    if detail:
        m = f"{m}: {detail}"
    return m
