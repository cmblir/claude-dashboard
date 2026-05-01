# Autonomous queue — 2026-05-01 (cycle 8: mode polish + Docker sandbox + observability)

User: "자율모드 계속 진행. 모두 완료할때까지 나에게 의견 묻지말고 모두 승인."
Direct to main. No questions. Push at end.

## [H1] Mode-aware default tab + last-tab-per-mode memory
- 모드 전환 시 그 모드에서 마지막 봤던 탭으로 복귀 (없으면 모드별 default).
- 영향: dist/index.html setMode + localStorage `cc.mode.<mode>.lastTab`.

## [H2] Mode-scoped spotlight search
- 현재 모드의 탭만 검색 결과에 (Cmd+Shift+K로 전체 검색 escape 가능).
- 영향: dist/index.html spotlight 필터 로직.

## [H3] Mode badges in NAV
- "all" 모드에서 각 탭에 작은 모드 배지 (claude/wf/prov/oc) 표시 — 사용자가
  어느 모드에서 그 탭을 다시 만날 수 있는지 한눈에.
- 영향: dist/index.html renderNav.

## [H4] Docker sandbox workflow node option
- 워크플로우 노드 인스펙터에 `runIn: host | docker:<image>` 토글.
- bash/file-write 노드만 컨테이너로 실행 (선택). docker 없으면 host 폴백.
- 영향: server/workflows.py 노드 실행 경로 + dist/index.html 인스펙터.
- 위험도: medium (외부 docker CLI 의존).

## [H5] Boot timing observability
- `python3 server.py` 가 listen 까지 걸린 시간 로그 + `/api/system/boot-timing`.
- 영향: server.py + server/system.py.

## [H6] Tests + i18n + commit-per-phase + push
- 모든 phase 테스트 커버, 전체 pytest 통과, i18n 0 missing, 일괄 push.
