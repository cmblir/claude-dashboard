# Today Queue — 2026-04-23 (OMC/OMX gap 흡수 세션)

생성: 2026-04-23  
기반: `analysis-omc-omx-gap.md` 의 B1~B5 (low 위험도)  
자율모드 규칙: `CLAUDE.md` §21 준수. high 위험 작업 금지, 매 작업 후 커밋/로그.

---

## [B1] 실행 모드 프리셋 4종 빌트인 워크플로우 템플릿
- 목표: OMC 의 `autopilot` · `ralph` · `ultrawork` · `deep-interview` 에 대응하는 DAG 템플릿 4종 추가. 사용자가 🔀 워크플로우 탭에서 원클릭 생성.
- 영향 범위: `server/workflows.py::_BUILTIN_TEMPLATES` (또는 동등 위치) + 프론트 템플릿 버튼
- 완료 기준: 
  1. 4 템플릿 각각 `bt-autopilot` / `bt-ralph` / `bt-ultrawork` / `bt-deep-interview` ID 로 `/api/workflows/templates/...` 조회 가능
  2. 각 템플릿 `save` 시 정상 실행 (최소 DAG 사이클 검사 통과)
  3. 영문/한글/중문 레이블
  4. i18n 누락 0
- 위험도: low

## [B2] Prompt Library 키워드 트리거 필드
- 목표: Prompt Library 엔트리에 `keywords: string[]` 필드 추가. 워크플로우 session 노드의 입력에 해당 키워드 포함 시 해당 프롬프트가 자동 시스템 프롬프트로 추가. OMC `ultrathink`/`deepsearch` 유사.
- 영향 범위: `server/prompt_library.py` + 저장 스키마 + `server/workflows.py` 세션 노드 실행 훅
- 완료 기준:
  1. `POST /api/prompt-library/save` 가 keywords 필드를 받고 저장
  2. session 노드 실행 시 입력 텍스트에 키워드 매칭되면 해당 프롬프트의 body 가 system 슬롯에 prepend
  3. UI 에서 keywords 편집 가능 (comma-separated 입력)
  4. 이전 엔트리는 빈 keywords 로 호환성 유지
- 위험도: low

## [B3] 워크플로우 완료 알림 — Slack / Discord / Telegram
- 목표: 각 워크플로우에 `notify: { slack?: webhook_url, discord?: webhook_url, telegram?: {bot, chat} }` 필드. run 종료 시 status + 요약 + 비용을 해당 채널로 POST.
- 영향 범위: `server/workflows.py` + 새 모듈 `server/notify.py` + 에디터 인스펙터
- 완료 기준:
  1. workflow 저장 시 notify 필드 보존 (sanitize 통과)
  2. run 종료 hook 에서 각 설정 채널로 비동기 HTTP POST (SSRF 가드 재사용 — 외부 호스트만 허용)
  3. 실패 시 조용히 로그만 (워크플로우 결과에 영향 없음)
  4. 에디터에 3 채널 입력 UI + 테스트 버튼
- 위험도: low

## [B4] Session 노드 modelHint → 자동 모델 라우팅
- 목표: session 노드에 `modelHint: "auto" | "fast" | "deep"` 필드. auto 일 때 프롬프트 길이 · 키워드 기반으로 haiku/sonnet/opus 자동 선택 (OMC 스마트 라우팅 대응).
- 영향 범위: `server/workflows.py::_execute_session_node` + sanitize + 에디터 UI
- 완료 기준:
  1. modelHint 필드 sanitize 및 저장 
  2. 기존 `assignee` 명시적 모델이 있으면 그것이 우선 (backward compat)
  3. "auto" 선택 시 입력 길이 < 500: haiku, 500-3000 + keywords like plan/review: sonnet, 3000+ or keywords like architect/deep: opus
  4. 어떤 모델이 선택됐는지 노드 실행 결과에 `chosenModel` 로 기록 → UI 에서 표시
- 위험도: low

## [B5] Session Replay Lab — JSONL 타임라인 뷰어
- 목표: Claude Code 의 `~/.claude/projects/**/*.jsonl` 파일을 선택해 시간순 타임라인으로 렌더. 툴 호출은 색상 강조, 토큰 사용량 누적 차트, 시간 점프 스크러버.
- 영향 범위: 새 탭 `sessionReplay` (work 그룹), 새 모듈 `server/session_replay.py`
- 완료 기준:
  1. JSONL 파일 목록 조회 (최근 50건)
  2. 선택한 파일 라인별 파싱 → role, content(요약), tool_use, timestamp 추출
  3. 프런트 가상 스크롤 타임라인 + 토큰 누적 SVG 스파크라인
  4. 시간 스크러버로 특정 이벤트 점프
  5. NAV 엔트리 추가 (work 그룹, `dist/index.html::NAV`)
- 위험도: low

---

## 처리 순서
B1 → B2 → B4 → B3 → B5 (간단·명확한 것부터, 위험도 같으면 파일 변경 작은 것 우선)

## 제외 (high 위험, 사용자 승인 필요)
- B6 Team 노드 프리셋 — UI 표면 크고 OMC 와 의존
- B7 Event Forwarder 탭 — Claude Code hook 설정 수정 이슈
- B8 Learner 탭 — AI 판단 영역 (false positive 리스크)
