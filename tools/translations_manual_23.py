"""v2.44.0 — Process / Port / Memory monitors.

Imported by translations_manual.py.

Covers all new Korean strings introduced by:
- VIEWS.openPorts (open ports monitor)
- VIEWS.cliSessions (active CLI sessions)
- VIEWS.memoryManager (memory + top processes + idle bulk-kill)
- NAV entries for openPorts / cliSessions / memoryManager
- Confirm prompts, button labels, toasts.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # Tab labels
    "열린 포트 모니터": "Open Ports Monitor",
    "활성 CLI 세션": "Active CLI Sessions",
    "메모리 관리": "Memory Manager",

    # NAV descriptions
    "TCP/UDP listening 소켓 + PID/Command/User · 한 번 클릭으로 프로세스 종료":
        "TCP/UDP listening sockets + PID/Command/User · one-click kill",
    "Claude Code CLI 세션의 PID·RSS·CPU·idle 시간 + 터미널 포커스 / SIGTERM":
        "Claude Code CLI session PID/RSS/CPU/idle time + terminal focus / SIGTERM",
    "vm_stat 기반 시스템 메모리 + 상위 30 프로세스 + idle Claude Code 일괄 종료":
        "System memory via vm_stat + top 30 processes + bulk-kill idle Claude Code",

    # View subtitles
    "TCP/UDP listening 소켓 모니터링": "TCP/UDP listening socket monitor",
    "Claude Code CLI 세션 모니터링": "Claude Code CLI session monitor",
    "시스템 메모리 + 상위 프로세스": "System memory + top processes",

    # Table headers / labels
    "포트": "Port",
    "프로토콜": "Proto",
    "명령": "Command",
    "사용자": "User",
    "상태": "State",
    "작업": "Action",
    "세션": "Session",
    "유휴": "Idle",
    "터미널": "Terminal",
    "열린 포트": "Open ports",
    "시스템 메모리": "System memory",
    "사용 중": "Used",
    "여유": "Free",
    "스왑": "Swap",
    "상위 30 프로세스": "Top 30 processes",

    # Buttons / actions
    "종료": "Kill",
    "터미널 열기": "Open terminal",
    "idle Claude Code 정리": "Clean up idle Claude Code",
    "idle Claude Code 일괄 종료": "Bulk kill idle Claude Code",
    "idle 600초 이상 세션": "Sessions idle ≥ 600s",

    # Confirm / toast / error
    "정말 이 프로세스를 종료하시겠습니까?": "Really kill this process?",
    "idle 상태인 모든 Claude Code 세션을 종료하시겠습니까?":
        "Kill all idle Claude Code sessions?",
    "프로세스를 종료했습니다": "Process killed",
    "종료 실패": "Kill failed",
    "터미널을 활성화했습니다": "Terminal activated",
    "터미널 열기 실패": "Open terminal failed",
    "일괄 종료 완료": "Bulk kill complete",
    "일괄 종료 실패": "Bulk kill failed",
    "건": "items",
    "포트 정보를 불러올 수 없습니다": "Failed to load port info",
    "세션 정보를 불러올 수 없습니다": "Failed to load session info",
    "메모리 정보를 불러올 수 없습니다": "Failed to load memory info",
    "열린 포트가 없습니다": "No open ports",
    "활성 CLI 세션이 없습니다": "No active CLI sessions",
    "SIGTERM 으로 안전하게 종료합니다. 시스템 PID(<500) 는 보호됩니다.":
        "Sends SIGTERM safely. System PIDs (<500) are protected.",
    # Extractor sentence-fragment shards (extract_ko_strings.py truncates at
    # period / paren — these never reach the user but must be covered to keep
    # _missing.json clean).
    "SIGTERM 으로 안전하게 종료합니다. 시스템 PID(":
        "Sends SIGTERM safely. System PID(",
    "500) 는 보호됩니다.": "500) is protected.",
}

NEW_ZH: dict[str, str] = {
    # Tab labels
    "열린 포트 모니터": "开放端口监控",
    "활성 CLI 세션": "活跃 CLI 会话",
    "메모리 관리": "内存管理",

    # NAV descriptions
    "TCP/UDP listening 소켓 + PID/Command/User · 한 번 클릭으로 프로세스 종료":
        "TCP/UDP 监听套接字 + PID/命令/用户 · 一键终止进程",
    "Claude Code CLI 세션의 PID·RSS·CPU·idle 시간 + 터미널 포커스 / SIGTERM":
        "Claude Code CLI 会话的 PID/RSS/CPU/空闲时间 + 聚焦终端 / SIGTERM",
    "vm_stat 기반 시스템 메모리 + 상위 30 프로세스 + idle Claude Code 일괄 종료":
        "基于 vm_stat 的系统内存 + 前 30 进程 + 批量终止空闲 Claude Code",

    # View subtitles
    "TCP/UDP listening 소켓 모니터링": "TCP/UDP 监听套接字监控",
    "Claude Code CLI 세션 모니터링": "Claude Code CLI 会话监控",
    "시스템 메모리 + 상위 프로세스": "系统内存 + 顶部进程",

    # Table headers / labels
    "포트": "端口",
    "프로토콜": "协议",
    "명령": "命令",
    "사용자": "用户",
    "상태": "状态",
    "작업": "操作",
    "세션": "会话",
    "유휴": "空闲",
    "터미널": "终端",
    "열린 포트": "开放端口",
    "시스템 메모리": "系统内存",
    "사용 중": "已使用",
    "여유": "空闲",
    "스왑": "交换分区",
    "상위 30 프로세스": "前 30 进程",

    # Buttons / actions
    "종료": "终止",
    "터미널 열기": "打开终端",
    "idle Claude Code 정리": "清理空闲 Claude Code",
    "idle Claude Code 일괄 종료": "批量终止空闲 Claude Code",
    "idle 600초 이상 세션": "空闲 ≥ 600 秒的会话",

    # Confirm / toast / error
    "정말 이 프로세스를 종료하시겠습니까?": "确定要终止该进程吗？",
    "idle 상태인 모든 Claude Code 세션을 종료하시겠습니까?":
        "确定要终止所有空闲 Claude Code 会话吗？",
    "프로세스를 종료했습니다": "进程已终止",
    "종료 실패": "终止失败",
    "터미널을 활성화했습니다": "终端已激活",
    "터미널 열기 실패": "打开终端失败",
    "일괄 종료 완료": "批量终止完成",
    "일괄 종료 실패": "批量终止失败",
    "건": "项",
    "포트 정보를 불러올 수 없습니다": "无法加载端口信息",
    "세션 정보를 불러올 수 없습니다": "无法加载会话信息",
    "메모리 정보를 불러올 수 없습니다": "无法加载内存信息",
    "열린 포트가 없습니다": "没有开放端口",
    "활성 CLI 세션이 없습니다": "没有活跃 CLI 会话",
    "SIGTERM 으로 안전하게 종료합니다. 시스템 PID(<500) 는 보호됩니다.":
        "通过 SIGTERM 安全终止。系统 PID(<500) 受保护。",
    # Extractor sentence-fragment shards
    "SIGTERM 으로 안전하게 종료합니다. 시스템 PID(":
        "通过 SIGTERM 安全终止。系统 PID(",
    "500) 는 보호됩니다.": "500) 受保护。",
}
