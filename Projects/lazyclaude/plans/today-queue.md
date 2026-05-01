# Autonomous queue — 2026-05-01 (cycle 3, optimization)

User directive: "계속 구현해. 자율모드. 그리고 main으로 모두 머지해. 최적화도 계속 구현해."

Branch continues `feat/openclaw-orchestrator-tui`; cycle 3 finishes with a
**local** merge into `main` (no remote push — §4.6, §21.3).

## [C1] HTTPS keep-alive connection pool
- 목표: Slack/Telegram 호출 시 매번 새 TCP+TLS handshake 하지 않음.
- 영향: `server/http_pool.py` (신규), slack_api / telegram_api 호출 경유.
- 완료 기준: 같은 host로 N번 연속 호출 시 두 번째 이후 connection 재사용.
- 위험도: low

## [C2] Coalesced channel reply (debounce per channel)
- 목표: 짧은 시간 내 동일 channel로 가는 회신을 1개로 합침. Slack 쿼터 보호.
- 영향: `server/orchestrator.py` reply pipeline.
- 완료 기준: pytest로 100ms 내 3회 reply → 1번만 호출.
- 위험도: low

## [C3] Plan cache (LRU by sha1)
- 목표: 같은 (binding, text) 조합의 planner 결과 재사용.
- 영향: orchestrator dispatch.
- 완료 기준: pytest로 동일 입력 2번째 호출은 planner 호출 0회.
- 위험도: low

## [C4] Agent Bus per-topic index (sparse subscribers)
- 목표: subscribe wakeup 시 ring 전체 스캔 대신 토픽별 last_id 인덱스 활용.
- 영향: `server/agent_bus.py`.
- 완료 기준: 1000 events 풀린 ring에 대해 subscribe(["one.topic"]) wakeup이
  O(matches) 만에 결과 반환.
- 위험도: medium (성능 회귀 위험 — 벤치 필수)

## [C5] Perf benchmark suite
- 목표: agent_bus throughput / latency / 메모리 회귀를 잡는 테스트.
- 영향: tests/perf/test_agent_bus_perf.py.
- 완료 기준: publish 10k events < 1.0s, history query < 100ms.
- 위험도: low

## [C6] Tests + commit + LOCAL merge to main
- 영향: i18n 0 missing, full pytest, then `git checkout main && git merge --no-ff feat/...`
- 완료 기준: main commit이 새 머지 커밋 포함, origin은 건드리지 않음.
- 위험도: low (로컬 작업만)
