# Autonomous queue — 2026-05-01 (cycle 2)

User directive: "계속 구현해. 자율모드 시작."
Branch: `feat/openclaw-orchestrator-tui` (continuing same branch).

Cycle 1 left these natural follow-ups; tackling in order.

## [B1] Agent Bus SSE bridge
- 목표: 프론트가 라이브로 `orch.*` / `wf.*` / 임의 토픽을 구독.
- 영향: `server/routes.py` (custom GET /api/agent-bus/stream — SSE),
  `dist/index.html` Orchestrator 탭 라이브 패널.
- 완료 기준: 디스패치 1회 → UI 패널에 plan/step/final이 실시간으로 흘러옴.
- 위험도: medium (HTTP handler 직접 작성 필요)

## [B2] Workflow binding execution
- 목표: 바인딩에 `workflowId` 있을 때 실제 해당 워크플로우 실행 + 결과 회신.
- 영향: `server/orchestrator.py::dispatch` 분기.
- 완료 기준: 바인딩된 채널에 메시지 → 워크플로우 run → final.text가 회신됨.
- 위험도: low

## [B3] Agent-to-agent request/reply protocol
- 목표: 한 에이전트가 다른 에이전트에 질문하고 답을 기다림 (synchronous over async bus).
- 영향: `server/agent_bus.py::ask(topic, payload, timeout)` + 매처.
- 완료 기준: pytest로 두 스레드가 ask/reply 라운드트립.
- 위험도: low

## [B4] Slack request signing verification
- 목표: `/api/slack/events`가 서명 검증을 강제 (env에 `SLACK_SIGNING_SECRET` 있으면).
- 영향: `server/orchestrator.py::api_slack_events` + 헤더 접근 위해 routes 수정.
- 완료 기준: 잘못된 서명 → 401, 올바른 서명 → 처리 진행.
- 위험도: low (시크릿 미설정 시 기존 동작 유지)

## [B5] Orchestrator run history
- 목표: `dispatch()` 결과를 SQLite에 저장 + `/api/orchestrator/history` + UI 리스트.
- 영향: `server/orchestrator.py` + 새 테이블, 라우트, UI 패널.
- 완료 기준: 디스패치 후 새로고침해도 결과 조회 가능.
- 위험도: low

## [B6] Tests + i18n + commit
- 영향: tests/test_agent_bus_ask.py 등, 추가 t() 문자열 번역.
- 완료 기준: 전체 pytest pass, i18n verify 0 missing.
- 위험도: low
