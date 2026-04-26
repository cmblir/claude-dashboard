"""v2.37.0 — Auto-Resume: inject a retry loop into a live Claude Code session.

Adds EN + ZH translations for every t('…') call site introduced by the
auto-resume feature. Imported by translations_manual.py.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # ── Auto-Resume panel ───────────────────────────────────────
    "Auto-Resume — 세션에 재시도 워커 주입":
        "Auto-Resume — inject retry worker into session",
    "이 세션이 토큰/레이트 한도로 멈추면 백그라운드 워커가 claude --resume 으로 자동 재시도합니다 (셸 while-loop 동등).":
        "If this session is halted by a token / rate limit, a background worker auto-retries it with `claude --resume` (equivalent to the shell while-loop).",
    "Auto-Resume 주입": "Inject Auto-Resume",
    "Auto-Resume 주입 중": "Auto-Resume active",
    "Auto-Resume 주입 완료": "Auto-Resume injected",
    "Auto-Resume 중단": "Stop Auto-Resume",
    "Auto-Resume 중단됨": "Auto-Resume stopped",
    "Auto-Resume 워커를 중단할까요?": "Stop the Auto-Resume worker?",
    "상태 불러오는 중…": "Loading status…",
    "고급 설정": "Advanced settings",
    "재개 프롬프트 — 비우면 기본값 사용":
        "Resume prompt — leave blank to use default",
    "재시도 간격(초)": "Retry interval (seconds)",
    "정지 판정 idle(초)": "Idle threshold (seconds)",
    "재시도 간격": "Retry interval",
    "정지 idle": "Idle threshold",
    "재개 프롬프트": "Resume prompt",
    "마지막 오류 출력": "Last error output",
    "시도": "Attempts",
    "다음 시도까지": "Next attempt in",
    "마지막 시도": "Last attempt",
    "아직 없음": "None yet",
    "실패": "Failed",
    "대기 중 (idle 미충족)": "Watching (idle threshold not met)",
    "실행 중 (claude --resume)": "Retrying (claude --resume)",
    "쿨다운 중 (다음 시도 예약)": "Cooling down (next attempt scheduled)",
    "재개 성공": "Resumed successfully",
    "중단됨": "Stopped",
    "오류": "Error",
    # ── v2 panel additions ──────────────────────────────────────
    "이전 중단 사유": "Previous stop reason",
    "--resume <id> 대신 --continue 사용":
        "Use `--continue` instead of `--resume <id>`",
    "--continue 모드": "--continue mode",
    "Stop hook 으로 매 응답 시 스냅샷 저장 + SessionStart 로 자동 주입":
        "Stop-hook saves a snapshot on every response and SessionStart injects it on resume",
    "Stop+SessionStart Hook 자동 설치 (프로젝트)":
        "Auto-install Stop + SessionStart hooks (project-local)",
    "Stop hook 스냅샷 미리보기": "Stop-hook snapshot preview",
    "리셋": "Reset",
    "스냅샷 해시 기록": "Snapshot hash history",
    "Hook 제거": "Remove hooks",
    "Hook 설치": "Install hooks",
    "Hook 설치 완료": "Hooks installed",
    "Hook 제거 완료": "Hooks removed",
    "최대 재시도 횟수": "Max retry attempts",
    "레이트 한도": "Rate limit",
    "컨텍스트 한도 초과": "Context limit exceeded",
    "인증 만료": "Auth expired",
    "정상 종료": "Clean exit",
    "알 수 없음": "Unknown",
}

NEW_ZH: dict[str, str] = {
    "Auto-Resume — 세션에 재시도 워커 주입":
        "Auto-Resume — 向会话注入重试工作进程",
    "이 세션이 토큰/레이트 한도로 멈추면 백그라운드 워커가 claude --resume 으로 자동 재시도합니다 (셸 while-loop 동등).":
        "如果此会话因令牌 / 速率限制而停止,后台工作进程会用 `claude --resume` 自动重试(相当于 shell while 循环)。",
    "Auto-Resume 주입": "注入 Auto-Resume",
    "Auto-Resume 주입 중": "Auto-Resume 运行中",
    "Auto-Resume 주입 완료": "Auto-Resume 已注入",
    "Auto-Resume 중단": "停止 Auto-Resume",
    "Auto-Resume 중단됨": "Auto-Resume 已停止",
    "Auto-Resume 워커를 중단할까요?": "确认停止 Auto-Resume 工作进程?",
    "상태 불러오는 중…": "正在加载状态…",
    "고급 설정": "高级设置",
    "재개 프롬프트 — 비우면 기본값 사용":
        "恢复提示词 — 留空则使用默认值",
    "재시도 간격(초)": "重试间隔(秒)",
    "정지 판정 idle(초)": "停顿判定 idle(秒)",
    "재시도 간격": "重试间隔",
    "정지 idle": "停顿 idle",
    "재개 프롬프트": "恢复提示词",
    "마지막 오류 출력": "最后一次错误输出",
    "시도": "尝试次数",
    "다음 시도까지": "下次尝试还有",
    "마지막 시도": "最后一次尝试",
    "아직 없음": "暂无",
    "실패": "失败",
    "대기 중 (idle 미충족)": "监视中(未达 idle 阈值)",
    "실행 중 (claude --resume)": "重试中(claude --resume)",
    "쿨다운 중 (다음 시도 예약)": "冷却中(已安排下次尝试)",
    "재개 성공": "成功恢复",
    "중단됨": "已停止",
    "오류": "错误",
    "이전 중단 사유": "上次停止原因",
    "--resume <id> 대신 --continue 사용":
        "使用 `--continue` 替代 `--resume <id>`",
    "--continue 모드": "--continue 模式",
    "Stop hook 으로 매 응답 시 스냅샷 저장 + SessionStart 로 자동 주입":
        "Stop hook 在每次响应时保存快照,SessionStart 在恢复时自动注入",
    "Stop+SessionStart Hook 자동 설치 (프로젝트)":
        "自动安装 Stop + SessionStart 钩子(项目级)",
    "Stop hook 스냅샷 미리보기": "Stop hook 快照预览",
    "리셋": "重置",
    "스냅샷 해시 기록": "快照哈希历史",
    "Hook 제거": "移除钩子",
    "Hook 설치": "安装钩子",
    "Hook 설치 완료": "钩子已安装",
    "Hook 제거 완료": "钩子已移除",
    "최대 재시도 횟수": "最大重试次数",
    "레이트 한도": "速率限制",
    "컨텍스트 한도 초과": "上下文限制超出",
    "인증 만료": "认证已过期",
    "정상 종료": "正常退出",
    "알 수 없음": "未知",
}
