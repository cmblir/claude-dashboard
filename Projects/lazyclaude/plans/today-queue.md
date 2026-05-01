# Autonomous queue — 2026-05-01 (cycle 6: IPC split + recurrence + auto-commit)

User: "계속 개발 진행해. PR 만들지 말고 바로 main으로"
Identity: `cmblir <cmblir@users.noreply.github.com>`. **No feature branch — direct to main.**

Items pulled from `decisions/2026-05-01-openclaw-nanoclaw-ralph-analysis.md`
Tier-2 + natural extensions of cycles 4-5.

## [F1] Inbound/Outbound SQLite IPC (NanoClaw pattern)
- 목표: `orch_runs.text/final` 단일 컬럼을 `orch_inbound` / `orch_outbound`
  두 테이블로 분리. 각 테이블 단일 writer (cross-process 안전).
- 영향: `server/orchestrator.py` (스키마 + persist 경로 + 조회).
- 완료 기준: 기존 history API는 호환, 새 inbound/outbound 스트림 조회 API 추가.

## [F2] Recurrence (60s sweep) — scheduled dispatches
- 목표: 바인딩에 `schedule: {everyMinutes: N, prompt: "..."}` 추가.
  단일 60초 sweep 스레드가 due 바인딩을 깨워 dispatch 실행.
- 영향: `server/orchestrator.py` + `server.py` boot에 sweeper 시작.
- 완료 기준: pytest로 짧은 인터벌 시뮬레이션 (env 오버라이드).

## [F3] Ralph auto-commit on done
- 목표: Ralph 루프가 `status=done` 으로 끝나고 cwd가 git repo이면,
  변경 파일을 자동 커밋 (binding 또는 start 옵션 `autoCommit:true`).
- 영향: `server/ralph.py` finalize 경로.
- 완료 기준: 더미 git 디렉터리에서 단위 테스트로 동작 검증.

## [F4] Tests + i18n + commits-to-main + push
- 각 phase 단독 commit, main에 직접. push는 마지막에 일괄.
