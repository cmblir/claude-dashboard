# Autonomous queue — 2026-05-01

User directive: "PR은 쪼개지 말고, 모두 자율모드로 시작. 라이트하게, 알고리즘/최적화 기반, 하드코딩 금지."

Branch: `feat/openclaw-orchestrator-tui`

## [A1] Agent Bus
- 목표: 모든 에이전트(워크플로우 노드, 슬랙/텔레그램 봇, TUI)가 공통 토픽 채널로 상호 보고할 수 있는 경량 pub/sub.
- 영향: server/agent_bus.py (신규). SQLite 단일 테이블, in-memory deque, SSE.
- 완료 기준: 토픽 라우팅 + 1초 deque polling 없이 condition.notify 기반 wakeup. 같은 (topic,sha1(payload)) 중복은 LRU 8 윈도우에서 드롭.
- 위험도: low

## [A2] Telegram
- 목표: 슬랙과 동일 설정 UX. Bot Token + 기본 chat. long-poll로 인입.
- 영향: server/telegram_api.py (신규), config/.json 신규 경로.
- 완료 기준: getMe + sendMessage + getUpdates(offset, timeout=25) 동작.
- 위험도: low

## [A3] Orchestrator
- 목표: 채널 멘션 → planner(Claude) → 서브에이전트(execute_with_assignee) → 채널 회신. 워크플로우 바인딩 옵션.
- 영향: server/orchestrator.py (신규). agent_bus 발행.
- 완료 기준: 슬랙/텔레그램에서 멘션 1회로 멀티 에이전트 분담 + 결과 회신.
- 위험도: medium (외부 API 실호출 — 단, 토큰 설정 안 되어 있으면 no-op)

## [A4] TUI
- 목표: `python3 tools/tui_config.py` 한 줄로 키/모델/슬랙/텔레그램/오케스트레이터 바인딩.
- 영향: tools/tui_config.py (신규). curses 표준 라이브러리.
- 완료 기준: 화살표/Enter/q로 모든 핵심 설정 가능. JSON 파일 직접 갱신.
- 위험도: low

## [A5] Routes + Frontend
- 영향: server/routes.py (등록), dist/index.html (탭 1개 추가), server/nav_catalog.py.
- 완료 기준: /api/orchestrator/* 라우트 + Orchestrator 탭에서 라이브 이벤트 표시.
- 위험도: medium (dist/index.html 회귀 주의)

## [A6] Tests + docs
- 영향: tests/test_agent_bus.py (신규), README, i18n.
- 완료 기준: pytest 통과, i18n verify 0 missing.
- 위험도: low
