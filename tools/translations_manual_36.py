"""v2.55.0 — Orchestrator + Telegram + Agent Bus tab strings.

New strings introduced by ``dist/index.html`` for the Orchestrator UI and
related workflows. Korean source -> English / Chinese; loaded by
``tools/translations_manual.py``.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    "가용 프로바이더":            "Available providers",
    "리스너 시작":                "Start listeners",
    "기본 설정":                  "Defaults",
    "플래너":                     "Planner",
    "취합기":                     "Aggregator",
    "기본 어사이니":              "Default assignees",
    "동시 실행":                  "Max parallel",
    "바인딩":                     "Bindings",
    "바인딩 추가":                "Add binding",
    "라이브 디스패치 테스트":     "Live dispatch test",
    "메시지를 입력해 ad-hoc 디스패치":
        "Enter a message to run an ad-hoc dispatch",
    "바인딩을 삭제할까요?":       "Remove this binding?",
    "실행 중...":                  "Running…",
    "아직 바인딩 없음":           "No bindings yet",
    "kind (slack/telegram/http):":           "kind (slack/telegram/http):",
    "assignees (csv, blank=defaults):":      "assignees (csv, blank=defaults):",
    "workflowId (blank for ad-hoc):":        "workflowId (blank for ad-hoc):",
}

NEW_ZH: dict[str, str] = {
    "가용 프로바이더":            "可用提供商",
    "리스너 시작":                "启动监听器",
    "기본 설정":                  "默认设置",
    "플래너":                     "规划器",
    "취합기":                     "聚合器",
    "기본 어사이니":              "默认指派",
    "동시 실행":                  "并发数",
    "바인딩":                     "绑定",
    "바인딩 추가":                "新增绑定",
    "라이브 디스패치 테스트":     "实时调度测试",
    "메시지를 입력해 ad-hoc 디스패치":
        "输入消息以触发临时调度",
    "바인딩을 삭제할까요?":       "确认删除该绑定?",
    "실행 중...":                  "执行中…",
    "아직 바인딩 없음":           "尚无绑定",
    "kind (slack/telegram/http):":           "kind (slack/telegram/http):",
    "assignees (csv, blank=defaults):":      "assignees (csv, blank=defaults):",
    "workflowId (blank for ad-hoc):":        "workflowId (blank for ad-hoc):",
}
