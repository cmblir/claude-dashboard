# Changelog

모든 의미 있는 변경은 이 파일에 기록된다. [Semantic Versioning](https://semver.org/lang/ko/) 을 따른다 — `MAJOR.MINOR.PATCH`.

기능 추가 시 규칙:
- **MAJOR** : 기존 워크플로우·스키마 파괴적 변경
- **MINOR** : 신규 탭/기능 추가 (하위 호환)
- **PATCH** : 버그 수정, UI 미세 조정, i18n 보강

기능 업데이트 시 (a) `VERSION` 파일 번호 bump, (b) 아래 표에 한 줄 추가, (c) `git tag v<버전>` 권장.

---

## [1.1.0] — 2026-04-22

### Added
- 🧠 **AI 프로바이더 탭 (aiProviders)** — 멀티 AI 오케스트라 기반 구축
  - **8개 빌트인 프로바이더**: Claude CLI, Ollama, Gemini CLI, Codex (CLI) + OpenAI API, Gemini API, Anthropic API, Ollama API
  - CLI 자동 감지 (로컬 설치된 claude/ollama/gemini/codex) + API 키 설정
  - **커스텀 CLI 프로바이더** — 임의의 CLI 도구를 AI 프로바이더로 등록
  - **폴백 체인** — 1차 프로바이더 실패 시 대안 자동 전환
  - 연결 테스트 + 모델 카탈로그 + 가격표 내장
- 🔀 **워크플로우 멀티 프로바이더 통합**
  - 노드 assignee: `claude:opus`, `openai:gpt-4.1`, `gemini:2.5-pro`, `ollama:llama3.1`, `codex:o4-mini`
  - 기존 Claude 전용 assignee 완전 호환 유지
- ⚡ **워크플로우 병렬 실행 엔진** — 같은 depth 노드를 ThreadPoolExecutor 로 동시 실행
- 🌐 **새 노드 타입 3종**: HTTP (외부 API 호출), Transform (JSON/regex/템플릿 변환), Variable (변수 저장)
- 🌍 33개 신규 i18n 키 (ko/en/zh)

### Architecture
- `server/ai_providers.py` (신규) — BaseProvider ABC + 8개 구현체 + ProviderRegistry 싱글턴
- `server/ai_keys.py` (신규) — `~/.claude-dashboard-ai-providers.json` 설정 CRUD
- `server/workflows.py` — `_execute_node` 멀티 프로바이더 대응, `_topological_levels` 병렬 실행
- `server/routes.py` — `/api/ai-providers/*` 엔드포인트 7개 추가

## [1.0.2] — 2026-04-22

### Added
- 챗봇 응답 대기 동안 마스코트가 **"잠시만요~! 결과를 불러오고 있어요"** 등 5종 메시지를 2.6초 간격으로 순환 표시. 첫 토큰 도착·에러·완료·finally 시 자동 정리. ko/en/zh 번역 포함.

## [1.0.1] — 2026-04-22

### Changed
- 대시보드 도우미 챗봇 모델을 **Haiku 로 하향** (`--model haiku`). 단순 JSON 라우팅 응답에 최적. 토큰 비용 대폭 절감. `CHAT_MODEL` 환경변수로 오버라이드 가능.

## [1.0.0] — 2026-04-22

첫 공식 릴리스 태그. 누적된 주요 기능을 여기서 하나로 묶어 마감.

### 신규 탭 / 기능
- 🔀 **워크플로우 (workflows)** — n8n 스타일 DAG 에디터
  - 6종 노드 (start · session · subagent · aggregate · branch · output)
  - 포트 드래그 엣지 + DAG 사이클 거부 + 🎯 맞춤(자동 정렬)
  - 🎭 세션 하네스: 페르소나/허용 도구/resume session_id
  - 🖥️ Terminal 새 창 spawn · 🔄 session_id 이어쓰기
  - 📋 템플릿: 팀 개발(리드+프론트+백엔드)/리서치/병렬 3 + 커스텀 저장
  - 🔁 **Repeat** — 반복 횟수/스케줄(HH:MM)/피드백 노트 자동 주입
  - 📜 실행 이력 · 🎬 인터랙티브 14 장면 튜토리얼(typewriter)
- 🚀 **시작하기 (onboarding)** — ~/.claude 상태 실시간 감지 단계별 체크리스트
- 📚 **가이드 & 툴 (guideHub)** — 외부 가이드/유용한 툴/베스트 프랙티스/치트시트

### 전반
- 모든 네이티브 `prompt/confirm` 을 맥 스타일 `promptModal`/`confirmModal` 로 통일
- 3개 언어 (ko/en/zh) 완전 번역 · `verify-translations` 검증 통과
- 모바일 대응: 마스코트 탭 시 챗창 즉시 닫힘 버그 해결, 창 크기 cap, 플로팅 맞춤 버튼
- 챗봇 시스템 프롬프트가 `server/nav_catalog.py` 를 읽어 자동 생성 — 탭 추가 시 자동 반영
