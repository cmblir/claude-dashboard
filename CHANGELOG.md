# Changelog

모든 의미 있는 변경은 이 파일에 기록된다. [Semantic Versioning](https://semver.org/lang/ko/) 을 따른다 — `MAJOR.MINOR.PATCH`.

기능 추가 시 규칙:
- **MAJOR** : 기존 워크플로우·스키마 파괴적 변경
- **MINOR** : 신규 탭/기능 추가 (하위 호환)
- **PATCH** : 버그 수정, UI 미세 조정, i18n 보강

기능 업데이트 시 (a) `VERSION` 파일 번호 bump, (b) 아래 표에 한 줄 추가, (c) `git tag v<버전>` 권장.

---

## [2.7.0] — 2026-04-23

### 👁️ Vision / PDF Lab — 신규 탭 (work 그룹)

이미지(PNG/JPG/WebP/GIF) 또는 PDF 를 업로드해 Opus / Sonnet / Haiku 3 모델에 병렬 질의 → 응답 비교.

**기능**
- 파일 선택 → 자동 base64 인코딩 (최대 10MB)
- 이미지: `type:"image"` 블록, PDF: `type:"document"` 블록으로 content 구성
- 3 모델을 **ThreadPoolExecutor** 로 병렬 호출
- 각 모델별 응답/지연/토큰 사용량 카드 나란히 표시
- 총 소요 시간 + 모델 수 요약

**Architecture**
- `server/vision_lab.py` 신설 — `api_vision_compare`, `api_vision_models` + `_call_one` 단일 모델 호출 유틸
- `server/routes.py` — 2개 라우트 추가 (`GET models`, `POST compare`)
- `server/nav_catalog.py` — `visionLab` 탭 등록 + en/zh desc
- `dist/index.html` — NAV + `VIEWS.visionLab` (파일 선택 카드 + 3-column 결과 그리드)
- `tools/translations_manual_9.py` — 16 키 × ko/en/zh 추가

---

## [2.6.0] — 2026-04-23

### 📎 Files API — 신규 탭 (work 그룹)

Anthropic Files API 의 업로드/목록/삭제 + 메시지 document reference 를 UI 에서 다룬다.

**기능**
- 브라우저 파일 선택 → 자동 base64 전송 → 서버에서 multipart/form-data 로 Anthropic 업로드 (최대 30MB)
- 업로드된 파일 목록 (filename · size · mime · id)
- 파일 선택 → 모델 선택 → 질문 textarea → 실행 (메시지 content 에 `{type:"document", source:{type:"file", file_id}}` 블록 삽입)
- 개별 삭제 + 삭제 전 확인 모달

**Architecture**
- `server/api_files.py` 신설 — `api_files_{list,upload,delete,test}` + stdlib multipart POST 유틸
- `server/routes.py` — 4개 라우트 추가 (`GET list` · `POST upload/delete/test`)
- `server/nav_catalog.py` — `apiFiles` 탭 등록 + en/zh desc
- `dist/index.html` — NAV + `VIEWS.apiFiles` (업로드 카드 + 질문 카드 + 파일 리스트)
- `tools/translations_manual_9.py` — 22 키 × ko/en/zh 추가
- beta header: `anthropic-beta: files-api-2025-04-14`

---

## [2.5.0] — 2026-04-23

### 📦 Batch Jobs — 신규 탭 (work 그룹)

Anthropic Message Batches API 를 감싸 대용량 프롬프트 병렬 제출·상태 폴링·결과 다운로드를 제공하는 관리 탭.

**기능**
- 원클릭 예시 2종: Q&A 10건 / 요약 5건
- 모델 (Opus 4.7 / Sonnet 4.6 / Haiku 4.5) + max_tokens 조절
- 프롬프트 한 줄당 1건 입력 (최대 1000건)
- 제출 전 **비용 발생 경고** 모달 (confirmModal)
- 최근 배치 목록 + 상태 + request_counts
- 배치 선택 시 JSONL 결과 미리보기
- 진행 중 배치 취소 지원

**Architecture**
- `server/batch_jobs.py` 신설 — `api_batch_{create,list,get,results,cancel,examples}`
- `server/routes.py` — 6개 라우트 추가 (`GET examples/list/get/results` · `POST create/cancel`)
- `server/nav_catalog.py` — `batchJobs` 탭 등록 + en/zh desc
- `dist/index.html` — NAV + `VIEWS.batchJobs` (배치 리스트 + 결과 프리뷰 카드)
- `tools/translations_manual_9.py` — 30 키 × ko/en/zh 추가
- beta header: `anthropic-beta: message-batches-2024-09-24`

---

## [2.4.0] — 2026-04-23

### 🛠️ Tool Use Playground — 신규 탭 (work 그룹)

Anthropic Tool Use 의 라운드 트립(user → assistant tool_use → user tool_result → assistant)을 수동으로 연습할 수 있는 플레이그라운드.

**기능**
- 기본 도구 템플릿 3종 원클릭 추가: `get_weather` / `calculator` / `web_search` (mock)
- tools JSON 배열을 직접 편집
- 대화 버블 시각화 (role, text, tool_use, tool_result 구분 색상)
- tool_use 수신 시 같은 메시지 안에서 바로 tool_result 수동 입력 → 제출 → 다음 턴
- "새 대화" 버튼으로 messages 배열 초기화
- 히스토리 최근 20건 (`~/.claude-dashboard-tool-use-lab.json`)

**Architecture**
- `server/tool_use_lab.py` 신설 — `api_tool_use_{turn,templates,history}`
- `server/routes.py` — 3개 라우트 추가 (`GET templates/history`, `POST turn`)
- `server/nav_catalog.py` — `toolUseLab` 탭 등록 + en/zh desc
- `dist/index.html` — NAV + `VIEWS.toolUseLab` (대화 버블 + tool_result 인라인 폼)
- `tools/translations_manual_9.py` — 13 키 × ko/en/zh 추가

---

## [2.3.0] — 2026-04-23

### 🧊 Prompt Cache Lab — 신규 탭 (work 그룹)

Anthropic Messages API 의 `cache_control` 을 실험/관측하는 전용 플레이그라운드 추가.

**기능**
- 원클릭 예시 3종: 시스템 프롬프트 캐시 / 대용량 문서 캐시 / 도구 정의 캐시
- 모델 선택 (Opus 4.7 / Sonnet 4.6 / Haiku 4.5) + max_tokens 조절
- system / tools / messages JSON 편집기
- 응답 즉시: input/output/cache_creation/cache_read 토큰 + USD 비용 상세 + 캐시 절감 추정
- 히스토리 최근 20건 (`~/.claude-dashboard-prompt-cache.json`)

**Architecture**
- `server/prompt_cache.py` 신설 (297줄) — `api_prompt_cache_test/history/examples` + `_estimate_cost` (3 모델 가격 테이블)
- `server/routes.py` — 3개 라우트 추가 (`GET /api/prompt-cache/examples`, `/history` · `POST /api/prompt-cache/test`)
- `server/nav_catalog.py` — `promptCache` 탭 등록 + `TAB_DESC_I18N` en/zh 등록
- `dist/index.html` — NAV + `VIEWS.promptCache` 추가 (pcRun / pcLoadExample / pcReset / pcSet)
- `tools/translations_manual_9.py` — 35 키 × ko/en/zh 추가

## [2.2.1] — 2026-04-22

### Fixed — 타이틀 리터럴 노출 + 위자드 테스트 오류

- **`ai_providers_title`/`ai_providers_subtitle` 리터럴 노출 수정** — 기존 `t(ko)` 함수가 1-인자만 받아 `t('ai_providers_title','AI 프로바이더')` 호출 시 fallback 을 무시하고 키 그대로 반환하던 문제. `t(key, fallback)` 2-인자 시그니처로 확장. ko 모드에서 구조화 키(영문 only) 가 오면 fallback 우선 사용.
- **`api_auth_login` NameError 수정** — `server/auth.py:170` 에서 `platform.system()` 호출하면서 `import platform` 이 누락돼 `/api/auth/login` 이 항상 500 을 반환하던 문제.
- **위자드 연결 테스트 UX 개선** — 테스트 결과에 응답 프리뷰(앞 80자) 표시, 404/unknown route 오류 시 "대시보드 서버를 재시작하면 최신 기능이 적용됩니다" 힌트 추가. 신규 라우트가 반영되지 않은 스테일 서버 상태를 사용자가 즉시 인지 가능.
- i18n: 신규 1개 키(ko/en/zh). 총 2,950 키 유지 (audit items 1806→1807).

## [2.2.0] — 2026-04-22

### 🎯 v2.2 — 프로바이더 탭 3종 개선

**프로바이더 CLI 감지 견고화**
- `server/ai_providers.py` 에 `_which()` 헬퍼 신설 — `shutil.which` PATH 탐지 실패 시 `/opt/homebrew/bin`·`~/.local/bin`·nvm/asdf node 버전 디렉터리 등 **11개 fallback 경로** 전수 검색. LaunchAgent·GUI 런치 등 PATH 가 좁혀진 환경에서도 Claude/Codex/Gemini/Ollama CLI 를 정확히 감지.
- `ClaudeCliProvider._bin`, `OllamaProvider._bin`, `GeminiCliProvider._bin`, `CodexCliProvider._bin`, `CustomCLIProvider._bin`, 임베딩 실행 경로 모두 `_which()` 로 교체.

**CLI 설치·로그인 원클릭 (신규)**
- 신규 모듈 `server/cli_tools.py` — 4종 CLI 설치·상태·로그인 통합 관리.
  - `GET /api/cli/status` — 4종(claude/codex/gemini/ollama) 설치 여부·버전·경로 + brew/npm 가용성 반환
  - `POST /api/cli/install` — brew 우선 → npm → 설치 스크립트 자동 선택, AppleScript 로 Terminal 열어 **대화형 설치 수행**
  - `POST /api/cli/login` — `claude auth login` / `codex login` / `gemini` 최초 실행 등을 터미널에서 실행
- 설치 방법 카탈로그: `brew install --cask claude-code` · `npm install -g @openai/codex` · `npm install -g @google/gemini-cli` · `curl ... ollama.com/install.sh`
- AI 프로바이더 탭의 CLI 카드에 상태 배지 추가:
  - 미설치 → `⬇️ 설치 (Homebrew|npm)` 버튼 · 클릭 시 터미널 열림, 10초마다 설치 감지 폴링(최대 5분)
  - 설치 완료 → `✅ 설치 완료 · <버전>` + `🔐 로그인` 버튼

**UI 간소화**
- AI 프로바이더 탭 하단 "💡 워크플로우 & 프로바이더 사용 가이드" 섹션 전체 제거(~50줄 삭제) — 별도 탭의 튜토리얼·노드 카탈로그와 중복.

**i18n**
- `translations_manual_9.py` 에 CLI 설치/로그인 문구 14개 키 등록(EN/ZH). ko/en/zh 각 **2,950 키** · 누락 0 · 한글 잔존 0.

## [2.1.4] — 2026-04-22

### Fixed — 설정 드롭다운 테마 3종 번역 누락
- `Midnight`/`Forest`/`Sunset` 테마 라벨이 하드코딩 영문으로 박혀 있어 ko/zh 선택 시에도 번역되지 않던 문제 수정.
- `dist/index.html` 설정 드롭다운 3개 버튼에 `data-i18n="settings.midnight|forest|sunset"` 속성 추가 (KO 기본값: 미드나잇/포레스트/선셋).
- `tools/translations_manual.py::MANUAL_KO` + `tools/translations_manual_9.py::NEW_EN/NEW_ZH` 에 구조화 키 + 한글-텍스트 키(`미드나잇 → Midnight/午夜`) 동시 등록 → `data-i18n` 경로와 text-node 스캐너 경로 양쪽 대응.
- 결과: ko/en/zh 각 **2,936 키** · 누락 0 · 한글 잔존 0 (기존 2,932 → +4).

## [2.1.3] — 2026-04-22

### Fixed — 워크플로우 탭 UX 정리
- **우측 하단 빈 박스 제거** — 워크플로우 미선택·빈 워크플로우 상태에서 `#wfMinimap` canvas 컨테이너(회색 박스)가 보이던 문제 수정. 기본 `display:none` + `_wfRenderMinimap()` 이 nodes 존재 시에만 표시하도록 변경.
- **캔버스 높이 캡 해제** — `#wfRoot` 의 `height: min(calc(100vh - 160px), 680px)` 캡을 제거하고 `calc(100vh - 230px)` 로 변경. 큰 모니터에서 680px 에 갇혀 스크롤해야 보이던 문제 해소 → 전체 워크플로우가 한눈에 보임.

## [2.1.2] — 2026-04-22

### Docs — 퍼블릭 배포용 README 3종 전면 재작성 + LICENSE 추가
- `README.md` / `README.ko.md` / `README.zh.md` 를 v2.1.1 통계 기준으로 동등 구조(305줄)로 재작성.
- 신규 섹션: Why(전/후 비교 표) · Use Cases(5 시나리오) · Troubleshooting 표 · Quick Start 30초 · Data Stores 표 · Tech Stack · Contributing 7단계.
- 통계 갱신: API 라우트 138 → **143**, i18n 2,893 → **2,932**, 서브에이전트 16 역할 프리셋·38 탭·18 튜토리얼·Rate Limiter 등 v2.1.x 신규 지표 반영.
- 배지 추가: Python 3.10+ · License · Version · Zero Dependencies.
- `LICENSE` 파일 신규 (MIT) — README 의 `./LICENSE` 링크가 404 였던 문제 수정.

## [2.1.1] — 2026-04-22

### Fixed — i18n 잔존 39건 전수 해소
- v2.1.0 신규 기능(HTTP/transform/variable/subworkflow/embedding/loop/retry/error_handler/merge/delay 노드 설명, AI 프로바이더 UI, Modelfile 편집 등)에서 누락됐던 **UI 문구 39개** 를 `translations_manual_9.py::NEW_EN`/`NEW_ZH` 에 등록.
- `tools/translations_manual.py` 에 `_EXTRACTOR_NOISE_OVERRIDES` 추가 — `const _KO_RE = /[가-힣]/` 같이 기존 MANUAL_EN 에 한글 원문으로 고정돼 있던 JS 리터럴을 유니코드 이스케이프(`가-힣`)로 override.
- 결과: **ko/en/zh 각 2,932 키 · 누락 0 · 영문/중문 한글 잔존 0** (origin 대비 값 회귀 0건).

## [2.1.0] — 2026-04-22

### 🎯 v2.1 — 미구현 23개 항목 전면 완료

**백엔드**
- 📌 **변수 스코프 시스템** — variable 노드에 글로벌/로컬 스코프 + `{{변수명}}` 템플릿 치환
- 🔀 **조건부 실행 11종** — contains/equals/not_equals/greater/less/regex/length_gt/length_lt/is_empty/not_empty/expression(AND/OR)
- ⏱️ **Rate Limiter** — 프로바이더별 토큰 버킷 알고리즘 (분당 요청 제한)
- 📝 **Ollama Modelfile 생성** — `POST /api/ollama/create` (커스텀 모델 생성)
- ✅ **에러 메시지 err() 전환 100%** — 모든 한글 에러에 error_key
- 🌍 **nav_catalog 다국어** — 38개 탭 설명 en/zh 동적 전환 구조 (`TAB_DESC_I18N`)

**프론트엔드 UX**
- 📱 **모바일 반응형** — 사이드바 접기, 그리드 반응형, 모달 전체 화면
- ♿ **접근성** — ARIA 레이블, role="dialog", 포커스 트랩
- 🔔 **브라우저 Notification** — 워크플로우 완료/실패, 사용량 초과 알림
- 🎨 **커스텀 테마 5종** — dark/light/midnight/forest/sunset
- 🔀 **조건부 실행 UI** — conditionType 11종 셀렉트
- 📌 **변수 스코프 UI** — scope 선택 + {{변수명}} 참조 안내
- 📝 **Modelfile 편집 UI** — 커스텀 모델 생성 모달
- 📊 **비용 히스토리 상세 차트** — 프로바이더별 일별 스택 차트
- 📦 **노드 그룹핑** — Shift+클릭 다중 선택 → 그룹 생성/접기/펴기
- 🔍 **워크플로우 diff** — 버전 비교 (추가/삭제/변경 노드 표시)

**i18n**
- +36개 키 사전 추가 (UX 신기능) + 전수 검증 0 miss
- 2,711+ 키 × 3언어

### Architecture
- `server/ai_providers.py` — `_RateLimiter` 토큰 버킷, `threading` import
- `server/workflows.py` — `_evaluate_branch_condition()` 11종, `_substitute_variables()`, variable 노드 `var_store` 인자
- `server/ollama_hub.py` — `api_ollama_create_model()`
- `server/nav_catalog.py` — `TAB_DESC_I18N` 38탭, `get_tab_desc()`
- `server/errors.py` — 에러 전환 100% 완료
- GET 75 + POST 63 = 138 라우트

## [2.0.0] — 2026-04-22

### 🎉 v2.0 메이저 릴리스 — 멀티 AI 오케스트라 플랫폼 완성

v1.0.2 → v2.0.0: **+10,800줄, 17개 커밋, 10개 태그**

### Added — Phase 10 (Final)
- 📋 **워크플로우 복제** — 목록에서 원클릭 clone (`POST /api/workflows/clone`)
- 📎 **노드 복사/붙여넣기** — `Ctrl+C`/`Ctrl+V` 선택 노드 복사 (+40px 오프셋, 새 ID)
- ↩️ **실행 취소** — `Ctrl+Z` undo 스택 (최대 30개, 노드/엣지 추가·삭제·이동 추적)
- ⌨️ **키보드 단축키** — `?` 키로 도움말 모달 (Delete/Ctrl+C/V/Z/S/F/Esc)
- 🌍 **i18n +22개 키** — 2,622개 × 3언어, **누락 0**

### v1.0.2 → v2.0.0 전체 누적
- **16개 노드 타입**: start, session, subagent, aggregate, branch, output, http, transform, variable, subworkflow, embedding, loop, retry, error_handler, merge, delay
- **8개 AI 프로바이더** + 커스텀 무제한: Claude CLI, Ollama, Gemini CLI, Codex + OpenAI API, Gemini API, Anthropic API, Ollama API
- **Ollama 모델 허브**: 23개 모델 카탈로그, 검색/다운로드/삭제
- **Embedding**: Ollama bge-m3, OpenAI text-embedding-3, 커스텀
- **워크플로우 엔진**: 병렬 실행, SSE 스트림, Webhook 트리거, Cron 스케줄러, Export/Import, 버전 히스토리, 빌트인 템플릿 8종
- **i18n**: ko/en/zh 2,622키, error_key 시스템 49키
- **API**: GET 73 + POST 59 = 132 라우트

## [1.9.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 9
- 📜 **워크플로우 버전 히스토리** — 저장 시 이전 버전 자동 보관 (최근 20개). Inspector에서 버전 목록 + 복원 버튼
- 📋 **빌트인 템플릿 5종** — 멀티 AI 비교, RAG 파이프라인, 코드 리뷰, 데이터 ETL, 재시도 워크플로우
- 🧙 **프로바이더 설정 위자드** — 3단계 가이드 (프로바이더 선택 → 연결 설정 → 테스트). localStorage "다시 보지 않기"
- 🏷️ **템플릿 갤러리 강화** — 카테고리 필터 (analysis/ai/dev/data/pattern/custom), 빌트인 배지, 삭제 불가 표시
- 🌍 **i18n +56개 키** — 2,599개 × 3언어, **누락 0**

### Architecture
- `server/workflows.py` — 저장 시 히스토리 보관, `api_workflow_history()`, `api_workflow_restore()`, `BUILTIN_TEMPLATES` 5종
- `server/routes.py` — `/api/workflows/history`, `/api/workflows/restore`
- GET 73 + POST 57 라우트

## [1.8.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 8
- 🦙 **Ollama 모델 허브** (Open WebUI 스타일) — 23개 모델 카탈로그 (LLM/Code/Embedding/Vision 4개 카테고리)
  - 모델 검색 + 카테고리 필터
  - 원클릭 다운로드 (`ollama pull`) + 진행률 바 (2초 폴링)
  - 모델 삭제 + 상세 정보 (modelfile/parameters/template)
  - 설치된 모델 테이블 (크기/패밀리/양자화/수정일)
- ⚙️ **커스텀 프로바이더 완전 관리** — capabilities 배지, 테스트 실행, 편집 모드, embed() 실행 지원
- 🎯 **프로바이더별 기본 모델 설정** — 드롭다운 선택 + 저장 API
- 🔧 **CustomCliProvider.embed()** — embedCommand/embedArgsTemplate 로 임베딩 CLI 실행
- 🌍 **i18n +52개 키** — 2,543개 × 3언어, **누락 0**

### Architecture
- `server/ollama_hub.py` (신규) — 모델 카탈로그 23종, pull/delete/info/pull-status API
- `server/ai_providers.py` — CustomCliProvider.embed() 구현
- `server/ai_keys.py` — api_set_default_model()
- `server/routes.py` — Ollama 5개 + default-model 1개 = 6개 새 라우트
- `dist/index.html` — Ollama 허브 UI, 커스텀 프로바이더 편집, 기본 모델 드롭다운
- GET 72 + POST 56 라우트

## [1.7.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 7
- 🔀 **Merge 노드** — 여러 병렬 경로를 조건부 합류. all(전부)/any(하나라도)/count(N개) 모드 + 타임아웃
- ⏱️ **Delay 노드** — 지정 시간 대기 후 통과. 고정/랜덤 딜레이 모드
- 📊 **워크플로우 통계 대시보드** — 총 실행/성공률/평균 소요시간/활성 스케줄 카드 + 프로바이더별 사용 분포 (접기/펴기)
- 🔍 **노드 검색 필터** — 캔버스 상단 검색창. 이름/타입 매칭 → 하이라이트 (비매칭 노드 dimming)
- 🗺️ **미니맵 색상** — merge(시안 #06b6d4) / delay(회색 #94a3b8) 추가
- 📈 **`/api/workflows/stats`** — 전체 실행 통계 집계 (성공률, 프로바이더별, 트리거별, 워크플로우별)
- 🌍 **i18n +24개 키** — 2,480개 × 3언어, **누락 0**

### Architecture
- `server/workflows.py` — merge/delay 노드 실행, `api_workflow_stats()` 통계 집계
- `dist/index.html` — merge/delay 편집 패널, 통계 대시보드, 노드 검색, 캔버스 색상
- 16개 노드 타입 · GET 68 + POST 53 라우트

## [1.6.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 6
- 🔄 **Loop 노드** — for_each(배열 순회) / count(횟수 반복) / while(조건 반복). 입력 분할 구분자 + 최대 반복 횟수
- 🔁 **Retry 노드** — 실패 시 자동 재시도. N회 + exponential backoff (초기 대기 × 배수). 지연 미리보기 UI
- 🛡️ **Error Handler 노드** — skip(무시) / default(기본값 반환) / route(에러 라우팅) 3가지 전략
- ⏰ **Cron 스케줄러** — 워크플로우를 cron 표현식으로 자동 실행. 서버 시작 시 스케줄러 스레드 자동 시작. 프리셋(매시/매일/평일/30분) + Inspector 설정 UI
- 🚨 **사용량 알림** — 일일 비용(USD) / 토큰 한도 설정. 초과 시 경고 배너 표시. `/api/ai-providers/usage-alert` API
- 🎨 **노드 캔버스 색상** — loop(연보라 #a78bfa) / retry(오렌지 #fb923c) / error_handler(빨강 #f87171)
- 🌍 **i18n +23개 키** — 2,456개 × 3언어, **누락 0**

### Architecture
- `server/workflows.py` — loop/retry/error_handler 노드 실행, `_cron_matches_now()`, `_scheduler_loop()`, `start_scheduler()`
- `server/ai_keys.py` — `api_usage_alert_check()` / `api_usage_alert_set()`
- `server/server.py` — `start_scheduler()` 부팅 시 호출
- `server/routes.py` — `/api/workflows/schedule/set`, `/schedules`, `/api/ai-providers/usage-alert`, `/usage-alert/set`
- `server/nav_catalog.py` — workflows 탭 키워드 확장 (loop, retry, cron, webhook 등)
- `dist/index.html` — 3종 노드 편집 패널, cron 설정 UI, 사용량 알림 설정/배너
- 14개 노드 타입 · GET 67 + POST 53 라우트

## [1.5.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 5
- 🔗 **Webhook 트리거** (`POST /api/workflows/webhook/{wfId}`) — 외부 시스템(GitHub Actions, Slack, cron 등)에서 HTTP로 워크플로우 실행. 입력 텍스트 주입 지원
- 🩺 **프로바이더 Health 대시보드** — AI 프로바이더 탭 상단에 실시간 초록/빨강 인디케이터 + "N/M 사용 가능" 요약
- 🗺️ **워크플로우 미니맵** — 캔버스 우하단 150×100px 조감도. 노드 타입별 색상 점 + 뷰포트 사각형 + 클릭 이동
- 📋 **Webhook URL 표시** — Inspector에 webhook URL + 클립보드 복사 + curl 예시 코드
- 🌐 **errMsg() 헬퍼** — `error_key` 기반 프론트 에러 번역 표시. 40+ toast 호출 전환
- 🔄 **백엔드 에러 i18n 완전 전환** — agents, skills, hooks, mcp, plugins, projects, features, commands, claude_md, actions 모듈 29개 에러에 `error_key` 추가

### Architecture
- `server/workflows.py` — `api_workflow_webhook()` Webhook 트리거
- `server/ai_keys.py` — `api_provider_health()` 병렬 헬스체크
- `server/agents.py`, `skills.py`, `hooks.py`, `mcp.py`, `plugins.py`, `projects.py`, `features.py`, `commands.py`, `claude_md.py`, `actions.py` — `err()` / `error_key` 전환
- `dist/index.html` — 헬스 바, Webhook URL, 미니맵, errMsg() 헬퍼
- `dist/locales/*.json` — 2,421개 키 × 3언어, **누락 0**

## [1.4.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 4
- 🔬 **멀티 AI 비교 전용 API** (`POST /api/ai-providers/compare`) — 여러 프로바이더에 동일 프롬프트 병렬 전송, 결과 일괄 반환
- 📦 **워크플로우 Export/Import** — JSON 파일로 내보내기/가져오기 (`POST /api/workflows/export`, `/import`). 툴바에 Export/Import 버튼
- 🔎 **노드 Inspector 프로바이더 정보** — 실행 결과 있는 노드 선택 시 프로바이더 아이콘, 모델, 소요 시간, 토큰, 비용 칩 표시
- 📊 **실행 이력 강화** — run 항목에 프로바이더별 색상 태그 + 집계 ("Claude ×3, GPT ×1"), duration 읽기 좋은 형태
- 🎨 **embedding 노드 캔버스 색상** — 분홍 `#f472b6`
- 🏗️ **에러 메시지 i18n 시스템** (`server/errors.py`) — 48개 에러 키 정의 + `err()` 헬퍼. 응답에 `error_key` 포함하여 프론트 번역 가능
- 🌍 **i18n +57개 키** — 48개 에러 키 + 9개 프론트 키 (export/import 등). 2,414개 × 3언어, **누락 0**
- 🔍 nav_catalog 키워드 확장 — aiProviders 탭에 embedding/비용/비교 키워드 추가

### Architecture
- `server/errors.py` (신규) — `ERROR_MESSAGES` dict + `err()`/`msg()` 헬퍼
- `server/ai_keys.py` — `api_provider_compare()` 병렬 비교 API
- `server/workflows.py` — `api_workflow_export()` / `api_workflow_import()`
- `server/actions.py` — 에러 메시지 `error_key` 포함 전환 시작
- `dist/index.html` — Export/Import 버튼, Inspector 프로바이더 칩, 이력 강화, embedding 색상
- `dist/locales/*.json` — 2,414개 키 × 3언어

## [1.3.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 3
- 🧲 **Embedding 노드** — Ollama bge-m3, OpenAI text-embedding-3 등 임베딩 모델로 텍스트→벡터 변환. RAG/검색 파이프라인 구축용
- 🎯 **프로바이더 Capability 시스템** — chat/embed/code/vision/reasoning 5종 태깅. 모델별·프로바이더별 기능 필터링
  - Ollama API: embedding 모델 자동 감지 (bge, nomic-embed, e5, gte 등 키워드)
  - OpenAI API: embedding 3종 모델 추가 (text-embedding-3-large/small, ada-002)
- ⚙️ **커스텀 프로바이더 완전 통합** — capabilities, embedCommand, embedArgsTemplate 설정 가능. 워크플로우 assignee 드롭다운에 자동 노출
- 💰 **비용 분석 차트** (프론트) — 일별 비용 타임라인 (Chart.js 라인) + 프로바이더별 비용 비교 (도넛) + 총 호출/토큰/비용 요약 카드
- 📡 **워크플로우 SSE 실시간 스트림** (프론트) — EventSource 로 노드 진행률 실시간 반영, 실패 시 폴링 fallback
- 🎨 **노드 타입별 캔버스 색상** — http(초록) / transform(보라) / variable(노랑) / subworkflow(시안) / embedding(분홍)
- 🔬 **멀티 AI 비교 모드** — 동일 프롬프트를 여러 AI에 동시 전송 → 결과 나란히 비교
- 🌍 **i18n 전수 감사 완료** — 32개 누락 키 발견·추가 + embedding 5개 키. 최종 3개 언어 2,357개 키, **누락 0**
- 📋 백엔드 한글 하드코딩 에러 메시지 68개 식별 (향후 i18n 전환 준비 목록)
- 📋 nav_catalog.py 탭 설명 38개의 en/zh 번역 목록 작성

### Architecture
- `server/ai_providers.py` — `EmbeddingResponse`, `CAP_*` 상수, `BaseProvider.embed()` + `supports()`, Ollama/OpenAI embed 구현
- `server/workflows.py` — `embedding` 노드 타입 + `_execute_embedding_node()`
- `server/routes.py` — `/api/ai-providers/by-capability?cap=embed`
- `dist/index.html` — 비용 차트, SSE 스트림, 노드 색상, AI 비교 모드, embedding 편집 패널
- `dist/locales/*.json` — 2,357개 키 × 3개 언어

## [1.2.0] — 2026-04-22

### Added
- 🎛️ **워크플로우 프로바이더 셀렉터** — 노드 편집 패널에서 프로바이더:모델 드롭다운 선택 (그룹화 + 직접 입력 지원)
- 💰 **멀티 AI 비용 추적** — DB `workflow_costs` 테이블 + 프로바이더별/일별 집계 API (`/api/ai-providers/costs`)
- 📡 **워크플로우 실행 SSE 스트림** — `/api/workflows/run-stream?runId=...` SSE 엔드포인트, 실시간 노드 진행률 전송
- 🔁 **Sub-workflow 노드** — 다른 워크플로우를 노드로 호출, 입력 전달 + 결과 반환 (워크플로우 재사용)
- 🌐 **HTTP 노드 UI** — URL/메서드/Body/추출경로 편집 패널
- 🔄 **Transform 노드 UI** — 템플릿/JSON 추출/Regex/결합 4가지 변환 유형 편집
- 📌 **Variable 노드 UI** — 변수 이름 + 기본값 편집
- 🔁 **Sub-workflow 노드 UI** — 워크플로우 목록에서 선택 + 입력 전달 체크박스

### Architecture
- `server/db.py` — `workflow_costs` 테이블 스키마 추가
- `server/workflows.py` — `_execute_subworkflow_node`, `_record_workflow_cost`, `handle_workflow_run_stream` (SSE)
- `server/ai_keys.py` — `api_workflow_costs_summary` 집계 API
- `dist/index.html` — 10개 노드 타입 (4개 신규), 프로바이더 셀렉터, 노드 편집 패널 확장

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
