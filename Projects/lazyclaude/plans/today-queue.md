# Autonomous queue — 2026-05-01 (cycle 5: Ralph UI + LLM polish + Email + workspace)

User: "깃푸시 권한 승인. 다음 사이클 구현. 자율모드".
Identity: **`cmblir <cmblir@users.noreply.github.com>`** (per memory; old email banned).

Branch: `feat/v2.57-ralph-ui-email-llm-polish`. Local merge to main + push.

## [E1] Ralph UI tab
- 목표: 대시보드에 🦞 Ralph 탭. 실행 목록 / 라이브 진행 SSE / 새 run 시작 폼 / 취소 버튼.
- 영향: `dist/index.html` (`VIEWS.ralph`), `nav_catalog.py`, i18n.
- 완료 기준: SSE로 iteration 도착, 비용/iter 카운터 라이브 갱신, 취소 버튼 작동.

## [E2] Project Ralph card
- 목표: Projects 탭의 각 프로젝트 카드에 🦞 버튼 → 추천 모달 → 미리보기/편집/시작.
- 영향: `dist/index.html` Projects 탭, `/api/ralph/recommend` 호출.
- 완료 기준: 1프로젝트 → recommend → start → Ralph 탭으로 점프 / 라이브 보이기.

## [E3] LLM-polish for PROMPT.md draft
- 목표: 추천기 mechanical 출력에 plan-cache 가능한 LLM 다듬기 옵션 추가 (`?polish=true`).
- 영향: `server/ralph_recommend.py` + plan-LRU 재사용.
- 완료 기준: pytest stub planner로 polish 분기 검증.

## [E4] Email-out reply (SMTP)
- 목표: orchestrator binding `kind: "email"` (default chat = recipient).
- 영향: `server/orchestrator.py` (sink 추가), `server/email_out.py` 신규 (SMTP+STARTTLS 재사용).
- 완료 기준: smoke 테스트로 reply sink가 SMTP 호출 (mocked).

## [E5] Per-agent isolated workspace
- 목표: binding마다 `~/.claude-dashboard-agents/<id>/CLAUDE.md` + `memory/` 자동 생성·로드.
- 영향: `server/orchestrator.py` execute_step에서 cwd/system_prompt 세팅.
- 완료 기준: 같은 binding 두 dispatch가 같은 워크스페이스 사용. 다른 binding은 격리.

## [E6] Workflow ralph-node inspector form
- 목표: 워크플로우 캔버스에서 Ralph 노드 클릭 → 인스펙터에 prompt/maxIter/budget/completion 필드.
- 영향: `dist/index.html` `_wfRenderInspector` 분기.
- 완료 기준: 저장-불러오기 round-trip + dry-run.

## [E7] Tests + i18n + commit + merge + push
- 위 5종 cover. 전체 pytest 통과. i18n 0 missing. main 머지 후 origin push.
