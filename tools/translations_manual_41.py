"""v2.65.0 — M1 boot-timing card + M2 Ralph duplicate-run button.

Korean -> English / Chinese for strings introduced in cycle 13.
Loaded by ``tools/translations_manual.py``.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # M1 — System tab boot-timing card
    "서버 부팅":     "Server boot",
    "부팅 시간":     "Boot time",
    "listen 시작":   "Started listening",
    "python3 server.py 부팅부터 첫 HTTP listen 까지의 시간. db 마이그레이션, 백그라운드 인덱스, ollama auto-start 등은 데몬 스레드라 이 시간에 포함되지 않습니다.":
        "Time from python3 server.py startup to first HTTP listen. DB migration, background index, and ollama auto-start run as daemon threads and are not included.",
    # M2 — Ralph duplicate run button
    "이 실행을 동일 설정으로 다시 시작":
        "Restart with the same configuration",
    "이전 실행 설정 불러옴 — 검토 후 시작하세요":
        "Previous run configuration loaded — review and click Start",
}

NEW_ZH: dict[str, str] = {
    # M1 — System tab boot-timing card
    "서버 부팅":     "服务器启动",
    "부팅 시간":     "启动耗时",
    "listen 시작":   "开始监听",
    "python3 server.py 부팅부터 첫 HTTP listen 까지의 시간. db 마이그레이션, 백그라운드 인덱스, ollama auto-start 등은 데몬 스레드라 이 시간에 포함되지 않습니다.":
        "从 python3 server.py 启动到首次 HTTP 监听的时间。DB 迁移、后台索引、ollama 自启动以守护线程运行，不计入此时间。",
    # M2 — Ralph duplicate run button
    "이 실행을 동일 설정으로 다시 시작":
        "以相同配置重新启动",
    "이전 실행 설정 불러옴 — 검토 후 시작하세요":
        "已加载上次运行配置 — 检查后点击启动",
}
