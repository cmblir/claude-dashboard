# Autonomous queue — 2026-05-01 (cycle 7: modes + AR add + ollama opt-out)

User directives (4):
1. "전체적으로 대시보드 최적화 진행해주고, 카테고리 정리"
2. "Auto-resume 관리에 활성 바인딩 없음 이라고 나오는데 이거 내가 활성 바인딩할 수 있게 해주는 기능도 추가해줘"
3. "워크플로우나 프로바이저, openclaw는 각각의 따로 모드로 전환해서 관리 할 수 있게 해줘"
4. "serve 할때 gemini나 ollama를 너가 켜지말고 내가 켤 수 있게 해줘"

Direct to main, no PR.

## [G1] Ollama/Gemini auto-start opt-out
- 목표: `python3 server.py` 부팅 시 ollama serve가 자동 실행되지 않게.
  사용자가 명시적으로 토글하거나 환경변수 `OLLAMA_AUTOSTART=1` 줘야 시작.
- 영향: `server.py` 부팅 시퀀스, `server/ollama_hub.py`.
- 완료 기준: 부팅 로그에 "auto-start: skipped" 표시, UI 버튼은 그대로.
- 위험도: low.

## [G2] Auto-Resume 활성 바인딩 추가 UI
- 목표: AR 관리 탭에 "+ 새 바인딩" 버튼 → sessionId/cwd/prompt 입력 모달
  → `api_auto_resume_set` 호출.
- 영향: `dist/index.html` AR 뷰.
- 완료 기준: 살아있는 Claude 세션을 골라서 바인딩 → 목록에 즉시 표시.
- 위험도: low.

## [G3] Top-level mode switcher (Claude / Workflow / Providers / OpenClaw)
- 목표: 한 대시보드 안에 4개 모드. 모드 선택 시 해당 모드의 탭만 보이고
  사이드바가 짧아짐. localStorage 영속.
- 영향: NAV/TAB_CATALOG에 `modes: []` 필드, 헤더에 모드 셀렉터.
- 완료 기준: 모드 전환 시 사이드바 즉시 갱신, 비-속한 탭은 검색에서도 제외.
- 위험도: medium.

## [G4] Category cleanup + tab → mode 매핑
- 목표: 기존 6 그룹 유지하되 각 탭에 `modes: ["claude"|"workflow"|...]` 배지.
  여러 모드에 속할 수 있음 (예: Settings는 모든 모드).
- 영향: `server/nav_catalog.py` + `dist/index.html` NAV.
- 완료 기준: 4 모드별 탭 수 측정 가능, 누락 탭 없음.
- 위험도: low.

## [G5] Boot-path optimization
- 목표: 부팅 시 동기 작업 줄이기 — 백그라운드 인덱스, MCP 캐시 워밍 등은
  데몬 스레드. Ollama 자동 시작 제거 (G1)와 함께 부팅 시간 측정.
- 영향: `server.py`.
- 완료 기준: 부팅 → 80포트 listen 까지 시간 단축 측정.
- 위험도: low (touching 부팅 코드).

## [G6] Tests + commit + push
- 위 변경 모두 커버. 단일 main push.
