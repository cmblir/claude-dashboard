# Changelog

모든 의미 있는 변경은 이 파일에 기록된다. [Semantic Versioning](https://semver.org/lang/ko/) 을 따른다 — `MAJOR.MINOR.PATCH`.

기능 추가 시 규칙:
- **MAJOR** : 기존 워크플로우·스키마 파괴적 변경
- **MINOR** : 신규 탭/기능 추가 (하위 호환)
- **PATCH** : 버그 수정, UI 미세 조정, i18n 보강

기능 업데이트 시 (a) `VERSION` 파일 번호 bump, (b) 아래 표에 한 줄 추가, (c) `git tag v<버전>` 권장.

---
## [2.23.2] — 2026-04-23

### 📸 Docs — 언어별 스크린샷 36장 + UI 브랜드 텍스트 정리

사용자 리포트 2건 반영:
1. 영문 README 가 한글 UI 스크린샷을 참조
2. `AI Providers` / `Costs Timeline` 이 빈 화면으로 캡처됨

**`scripts/capture-screenshots.mjs` 전면 재작성**
- 12 탭 × 3 언어 = 36장 → `docs/screenshots/{ko,en,zh}/<tab>.png`
- `?lang=en|zh` 쿼리로 UI 언어 전환 후 캡처 (context 재생성)
- `waitForLoadState('networkidle')` + 탭별 selector + `waitForResponse('/api/ai-providers/list')` + chip 개수 `waitForFunction` — zh/en 에서 `aiProviders` 가 스켈레톤 상태로 찍히던 문제 해결
- `page.route('**/api/cost-timeline/summary', ...)` 로 Costs Timeline 모의 응답 주입 (14일 × 5 소스 × 147건 · 총 $12.38) — 실 API 호출 없이 의미있는 스택 차트 생성
- overview 탭의 Claude 계정 온보딩 모달을 `Continue|계속|继续` 버튼 자동 클릭으로 통과
- 워크플로우 시드 선택 fallback: `_wfOpen` → `_wfSelect` → 직접 `__wf.current` 할당

**`dist/index.html` UI 브랜드 텍스트 정리**
- `<title>` · 사이드바 브랜드 · 계정 온보딩 모달 헤더 등 4곳의 `Claude Control Center` → `LazyClaude` 치환 (리브랜딩 일관성)

**README 3종 이미지 경로 분기**
- `./docs/screenshots/*.png` → `./docs/screenshots/{ko,en,zh}/*.png` (각 README 자신의 언어로)

**검증**
- 36/36 캡처 성공
- 각 언어에서 overview (최적화 점수 21 · 6171 세션 렌더) · aiProviders (8 프로바이더 카드) · costsTimeline (스택 차트 + 소스별 집계) · workflows ([Demo] Multi-AI Compare DAG) 시각 확인

---
## [2.23.1] — 2026-04-23

### 🎨 Branding — 프로젝트 이름을 **LazyClaude** 로

레퍼런스: [`Yeachan-Heo/oh-my-claudecode`](https://github.com/Yeachan-Heo/oh-my-claudecode) 의 README 스타일 참고.

- **브랜드 네임**: `Claude Control Center` → `💤 LazyClaude`
  - 네이밍 톤: `lazygit` / `lazydocker` / `lazyvim` 패밀리 편승. 게으른 사람을 위한 로컬 Claude 커맨드 센터.
  - 캐치프레이즈: "Don't memorize 50+ CLI commands. Just click." / "50+ 개 CLI 명령어 외우지 마세요. 그냥 클릭하세요."
- **README 3종 (ko/en/zh)**
  - Hero 섹션을 `<div align="center">` 중앙 정렬, 태그라인 + 캐치프레이즈 상단에 배치.
  - Quick Start 를 "1 · 클론 / 2 · 실행 / 3 · 접속" 3단계 박스 스타일로 재구성.
  - 장문 "v2.x 신기능" 나열을 "최근 업데이트" 테이블 (6 행) 로 압축.
  - ASCII 배너 내 `🧭 Claude Control Center` → `💤 LazyClaude`.
  - Contributing 섹션: 1인 메인테이너 개인 프로젝트임을 명시, "core team" 같은 구절 제거. PR 유도 톤은 유지.
  - Acknowledgements 에 lazygit/lazydocker 크레딧 추가.
  - 하단에 "Made with 💤 for those who'd rather click than type." 서명.
- **기술 경로 유지** (하위 호환):
  - Repo URL `github.com/cmblir/claude-dashboard` 유지 (rename 은 사용자 선택 사항).
  - 데이터 파일 `~/.claude-dashboard-*.json` 경로 유지 — 기존 사용자 데이터 보존.
  - 내부 변수명·모듈명 변경 없음.

---
## [2.23.0] — 2026-04-23

### 🛡 Security — Webhook 인증 + Output 경로 화이트리스트 (v2.22 보안 감사 후속)

v2.22.0 SSRF 가드 직후 남아있던 MEDIUM 2건을 마무리. 로컬 `127.0.0.1:8080` 바인딩 전제라 실위협은 제한적이지만, 원격 포워딩·컨테이너 공유 환경을 대비해 선반영.

**Finding 2 · Webhook 무인증 → `X-Webhook-Secret` 필수 (`server/workflows.py`)**
- 워크플로우마다 `webhookSecret` 필드 보관. `POST /api/workflows/webhook/<wfId>` 호출 시 헤더 필수.
- 비교는 `hmac.compare_digest` — 타이밍 공격 방어.
- secret 미발급 상태면 401 응답으로 호출 차단 (`err_webhook_no_secret`).
- 저장 API (`/api/workflows/save`) 로는 secret 을 변경할 수 없음 (기존값만 보존). 전용 API 로만 관리.

**신규: `POST /api/workflows/webhook-secret`**
- `{action: "get"}` 현재값 조회
- `{action: "generate"}` 미발급 시 발급, 이미 있으면 기존값
- `{action: "rotate"}` 새 값으로 교체 (기존 호출자 모두 401)
- `{action: "clear"}` 제거 — webhook 비활성화
- 생성: `secrets.token_urlsafe(32)` → 43자 URL-safe base64

**UI · 워크플로우 에디터 우측 인스펙터**
- Webhook URL 아래 Secret 패널 추가. 상태(발급/미발급) 표시.
- 버튼: 🔐 Generate · 🔄 Rotate · 🚫 Clear · 👁 Show/Hide · 📋 Copy
- `curl` 예시에 `-H "X-Webhook-Secret: ..."` 자동 삽입 (실값 반영).
- rotate/clear 는 confirm 모달로 이중 확인.

**Finding 3 · Output 노드 `exportTo` 경로 화이트리스트 (`server/workflows.py`)**
- 기존 `_under_home` (`~/` 하위 모두 허용) → 신규 `_under_allowed_export` (`~/Downloads` · `~/Documents` · `~/Desktop` 만 허용).
- `os.path.realpath` 로 symlink 완전 해제 후 비교 → `~/Documents/../.ssh/x` 같은 traversal 차단.
- 허용 경로 밖이면 노드 실행 단계에서 명시적 에러.

**i18n · 한/영/중**
- 17 항목 추가 (`webhook_secret_*` 9 + 표시/숨김 등). 3,253 키로 정합성 검증 통과.

**검증**
- `e2e-tabs-smoke.mjs` 52/52 통과
- `verify:i18n` 통과 (3,253 ko/en/zh 키 집합 일치)
- curl E2E: no-secret → 401, wrong → 401, rotate 후 옛 값 → 401, 새 값 → 200
- 경로 화이트리스트 단위 테스트: `/etc/passwd`, `~/../etc/passwd`, `~/.ssh/id_rsa`, `/tmp/foo.txt`, `~/Documents/../.ssh/x` 모두 차단 확인

---
## [2.22.1] — 2026-04-23

### 📸 Docs — README 3종에 스크린샷 12장 삽입

사용자 피드백: "글만 보고 어떤식으로 나오는지 알 수 없잖아". 실제 UI 보여주는 스크린샷 자동 생성 + README 임베드.

**신규: `scripts/capture-screenshots.mjs`**
- Playwright 로 주요 12 탭을 1440×900 @2x (레티나) 로 캡처
- `docs/screenshots/<tab>.png` 에 저장
- workflows 탭은 `bt-multi-ai-compare` 템플릿 시드 후 `_wfFitView()` 로 전체 DAG 노출
- promptCache 탭은 예시 1개 로드 후 캡처
- 캡처 완료 시 `[Demo]` 시드 워크플로우 자동 정리

**캡처 대상 (12)**
- `overview` · `workflows` · `aiProviders` · `costsTimeline`
- `promptCache` · `thinkingLab` · `toolUseLab` · `modelBench`
- `claudeDocs` · `promptLibrary` · `projectAgents` · `mcp`

**총 용량**: ~2.4MB (탭당 100~330KB · PNG 레티나). Git 저장소에 직접 commit.

**README 3종 구조**
- ASCII 미리보기 박스 바로 아래 `### 📸 Screenshots / 스크린샷 / 截图` 섹션 추가
- 4개 카테고리 × 2열 markdown 표 (메인 / 멀티AI·비용 / API 플레이그라운드 / 지식·재사용)
- `![label](./docs/screenshots/tab.png)` 상대 경로 → GitHub raw 렌더 호환

**package.json scripts.screenshots** 추가: `npm run screenshots` 로 재생성.

**사전 요건**: 서버가 `127.0.0.1:8080` 에서 기동 중이어야 함 + `npx playwright install chromium` 완료.

## [2.22.0] — 2026-04-23

### 🔒 Security — 워크플로우 HTTP 노드 SSRF 가드 (Finding 1 fix)

보안 감사에서 발견된 **HIGH** 급 SSRF 취약점 수정. 기존 `_execute_http_node` 가 URL 의 scheme/host 검증 없이 `urllib.request.urlopen` 을 호출해 **DNS rebinding / CSRF / 악성 워크플로우 import** 시 다음 공격이 가능했음:

- 클라우드 메타데이터 (`http://169.254.169.254/`) 접근 → 자격 증명 유출
- 로컬/사설 네트워크 포트 스캔 (`http://127.0.0.1:6379`, `http://192.168.x.x:*`)
- `file://`, `ftp://`, `gopher://` 등 비-HTTP 스킴을 통한 파일 읽기 / 내부 호출

**수정 내역**
- `server/workflows.py::_execute_http_node`:
  * scheme 화이트리스트: `http`, `https` 만 허용. 그 외는 `"scheme blocked"` 에러.
  * 호스트 블랙리스트: `127.0.0.1 · 0.0.0.0 · ::1 · localhost · 169.254.169.254 · metadata.google.internal · metadata.goog · fd00:ec2::254`
  * 사설/링크로컬 프리픽스 차단: `10.*`, `127.*`, `169.254.*`, `172.16~31.*`, `192.168.*`, IPv6 `fc*/fd*/fe80~feb*`
  * **DNS rebinding 방어**: 호스트가 DNS 이름일 때 `getaddrinfo` 로 실제 IP 를 해석 후 재검사. 해석 실패 시 `fail-closed`.
- **옵트인 우회**: 노드 `data.allowInternal = true` 로 체크 시만 내부 호출 허용. UI 에 경고 박스 + 체크박스 (기본 off).
- `dist/index.html::VIEWS.workflows` HTTP 노드 에디터에 체크박스 추가 + 신규 HTTP 노드 data 기본값에 `allowInternal: false` 명시.
- `tools/translations_manual_9.py`: 2 키 × ko/en/zh 추가.

**영향도**
- **공격 차단**: 외부 공격자의 DNS rebinding 이나 악성 워크플로우 JSON import 를 통한 내부 네트워크 접근 원천 차단.
- **호환성**: 기존 워크플로우의 외부 API 호출 (`api.openai.com`, `api.anthropic.com` 등) 은 영향 없음. 로컬 테스트용 호출(`http://localhost:3000`) 은 UI 에서 체크박스 켜야 동작.

**감사 출처**: `/security-review` 스킬 · `Obsidian/logs/2026-04-23-security-audit.md` 에 상세 기록.

## [2.21.1] — 2026-04-23

### Docs — README 3종 통계 v2.21.1 기준 갱신 (세션 5 결과)

T15~T17 (v2.19.0 · v2.20.0 · v2.21.0 docs) 반영:
- 버전 배지 v2.18.1 → **v2.21.1**
- 51 → **52 tabs** (costsTimeline 추가)
- 178→188→**190** routes (GET 102 / POST 85 / PUT 3)
- 3,212 → **3,234** i18n keys × 3언어
- Stats 섹션: 백엔드 ~17,600/44 → **~18,000/46 modules** · 프론트 ~16,300→**~16,600**
- **신규 행**: "Unified cost timeline ✓ · Workflow run diff/rerun ✓"
- README ko/en/zh 3종 동등 갱신
- `npm run test:e2e:smoke` 52/52 tabs (comment 업데이트)

## [2.21.0] — 2026-04-23

### 📐 Docs — Artifacts 로컬 뷰어 설계 문서 (구현 X)

B6 (Claude.ai Artifacts 의 로컬 대안) 을 안전하게 구현하기 위한 **설계 선행**. 실제 코드는 다음 세션 (T20~T23, v2.22~v2.24) 에 나누어 진행.

**저장 위치**: `Obsidian/Projects/claude-dashboard/decisions/2026-04-23-artifacts-design.md`

**핵심 보안 4중 방어**
1. **iframe sandbox**: `srcdoc` 로 origin = null · `sandbox="allow-scripts"` (allow-same-origin 제외) → cookie / localStorage / IndexedDB 불가
2. **CSP via srcdoc meta**: `default-src 'none'; script-src 'unsafe-inline'; connect-src 'none'` → 외부 fetch 차단 (CSS exfiltration 포함)
3. **postMessage 화이트리스트**: `artifact:ready` / `artifact:resize` / `artifact:error` / `artifact:theme` 외 모두 무시. `event.origin` 검사
4. **정적 코드 필터**: `import from 'https://'`, `navigator.credentials`, `document.cookie`, `localStorage`, `indexedDB` 패턴 발견 시 거부 + confirmModal 승인 필요

**릴리스 로드맵**
- v2.22.0 — `server/artifacts_lab.py` (extract/save/list/delete) + 4 라우트
- v2.23.0 — `VIEWS.artifacts` UI + 샌드박스 iframe + postMessage 프로토콜
- v2.24.0 — Babel standalone **로컬 번들** (supply chain 면역) + React/JSX 지원
- v2.24.1 — Playwright `e2e-artifacts.mjs` 5 테스트 케이스 (CSP 차단 · sandboxed origin · postMessage 필터 · 금지 패턴 · 강제 렌더)

**의사결정 (Open → Closed)**
- Babel: CDN ❌ · **로컬 번들** ✅ (공급망 안전)
- Artifact 외부 공유: **완전 불가**. 로컬 JSON export 만
- 강제 렌더: 매번 confirmModal (세션 skip 옵션 없음)

## [2.20.0] — 2026-04-23

### 💸 비용 타임라인 통합 탭 — 신규 `costsTimeline` (system 그룹)

Claude API 플레이그라운드 10종 + 워크플로우 실행 비용을 **한 화면**에 통합.

**기능**
- 상단 카드 3개: 총 비용 · 총 호출 수 · 활성 소스 (10 플레이그라운드 + workflows)
- **일별 비용 차트** (최근 60일) — SVG 수평 막대 · 소스별 스택 색상
- **소스별 집계 테이블**: 호출 수 · 토큰 in/out · USD
- **모델별 집계** (Top 20)
- **최근 30건 리스트**

**Architecture**
- `server/cost_timeline.py` 신설 — 각 `~/.claude-dashboard-*.json` 히스토리를 통합 집계
- 처리 소스 (10 + workflows):
  * promptCache / thinkingLab / toolUseLab / batchJobs / apiFiles / visionLab / modelBench / serverTools / citationsLab + workflows(store costs 배열)
- 엔트리 없는 USD 값은 `_estimate(model, ti, to)` 로 재계산 (Opus/Sonnet/Haiku 가격표)
- `server/routes.py` 라우트 1 추가 (`GET /api/cost-timeline/summary`)
- `server/nav_catalog.py` `costsTimeline` 탭 등록 (system 그룹) + en/zh
- `dist/index.html` NAV (icon 💸) + `VIEWS.costsTimeline` — SVG 스택 차트 + 3 테이블
- `tools/translations_manual_9.py` 18 키 × ko/en/zh

## [2.19.0] — 2026-04-23

### 📜 워크플로우 실행 이력 diff / 재실행

기존 `📜 이력` 모달을 확장. 각 run 카드에 **🔍 diff** + **🔄 재실행** 버튼.

**🔍 diff**
- 바로 직전 run 과 per-node 비교 테이블
- 컬럼: 노드 id · A status · A duration · B status · B duration · Δ
- 상태 변화 또는 한쪽에만 있는 노드는 하이라이트
- 상단 요약: A/B 전체 status · duration · Δ

**🔄 재실행**
- 현재 선택된 워크플로우를 즉시 재실행 (기존 `api_workflow_run` 재사용)
- SSE 폴링 자동 시작 → 배너 등장

**Architecture**
- `server/workflows.py` 신규 `api_workflow_run_diff(body: {a, b})` — 두 runId 의 `nodeResults` 비교 → node 별 status/duration Δ + onlyA/onlyB 플래그
- `server/routes.py` 라우트 1 추가 (`POST /api/workflows/run-diff`)
- `dist/index.html::_wfShowRuns` 확장: run 카드에 diff/rerun 액션
- `_wfDiffRuns(aId, bId)` / `_wfRerunWorkflow()` 신규 함수
- `tools/translations_manual_9.py` 10 키 × ko/en/zh

**스모크**
- `/api/workflows/run-diff` 신규 엔드포인트 정상
- 워크플로우 탭 "📜 이력" 모달에서 각 run 카드에 diff/재실행 버튼 노출 확인

## [2.18.1] — 2026-04-23

### Docs — README 3종 통계 갱신 (세션 4 결과 반영)

T10~T13 (v2.15.0 ~ v2.18.0) 신규 3 탭(embeddingLab + promptLibrary + Batch 가드 UI) + E2E 확장이 README 본문에 반영되도록 일괄 갱신.

- 버전 배지 v2.14.1 → **v2.18.1**
- 49 → **51 tabs / 51 탭 / 51 个标签页**
- work 그룹 테이블에 🆕 `embeddingLab` · `promptLibrary` 추가 (serverTools/citationsLab/agentSdkScaffold 는 기존으로 이동)
- Architecture 트리: routes 178 → **188**, nav 49 → **51 tabs**, locales 3,157 → **3,212 keys**
- Stats 섹션을 **v2.18.1** 기준으로 전면 갱신:
  * 백엔드 ~17k/42 → **~17,600줄/44 모듈**
  * 프론트 ~15,500줄 → **~16,300줄**
  * API 라우트 178 → **188** (GET 101 / POST 84 / PUT 3)
  * 플레이그라운드 탭 10 → **11** (+ Embedding Lab)
  * **신규 행**: Prompt Library ✓, Batch 비용 가드 ✓, E2E 테스트 스크립트 **3**
- E2E 테스트 섹션에 `test:e2e:ui` · `test:e2e:all` 추가 (smoke 51 tabs 재반영)
- README ko/en/zh 3종 동등 갱신

## [2.18.0] — 2026-04-23

### 🎭 E2E 커버리지 확장 (v2.10.x UX 회귀 방지)

**신규: `scripts/e2e-ui-elements.mjs`**

워크플로우 탭의 중요 DOM/전역 함수 무결성을 자동 검증. Anthropic API 키 없이도 동작.

**검증 항목**
1. 핵심 컨테이너 7개 (`#wfRoot` · `#wfCanvasWrap` · `#wfToolbar` · `#wfCanvasHost` · `#wfCanvas` · `#wfViewport` · `#wfMinimap`)
2. 빌트인 `bt-multi-ai-compare` 로 임시 워크플로우 생성 → `.wf-node` 6개 렌더 확인 → 자동 정리
3. **v2.10.0 UX**: `.wf-node-ring` / `.wf-node-elapsed` 각 6개 존재 · `_wfRenderRunBanner` 전역 노출 · mock running run 으로 `#wfRunBanner.visible` 부착 검증
4. **v2.10.1 UX**: `_wfToggleCat` 전역 노출
5. **v2.10.2 UX**: `_wfShowNodeTooltip` 전역 노출
6. `pageerror` / `console.error` 집계 → 하나라도 있으면 실패

**package.json scripts 추가**
- `test:e2e:ui` → `node scripts/e2e-ui-elements.mjs`
- `test:e2e:all` → smoke + ui 연속 실행

**검증 실행 결과 (v2.18.0)**
- `npm run test:e2e:ui` — 18개 체크 전부 통과
- `npm run test:e2e:smoke` — **51/51 탭 전수 통과**

## [2.17.0] — 2026-04-23

### 🚨 Batch 비용 가드 (batchJobs 확장)

Message Batches 제출 전 **예상 비용/토큰**을 계산해 임계치 초과 시 거부.

**설정**
- `~/.claude-dashboard-batch-budget.json` — `{enabled, maxPerBatchUsd, maxPerBatchTokens}`
- 기본: **disabled** · $1.00 · 100,000 tokens
- 사용자가 명시 활성화해야 작동 (기존 동작 유지)

**예상 비용 계산 (`_estimate_batch_cost`)**
- input_tokens 근사치 = Σ `len(prompt) // 4`
- output_tokens = `max_tokens × len(prompts)`
- 가격표: Opus/Sonnet/Haiku 3 모델 per-1M-token 단가
- **50% 할인 적용** (Anthropic Message Batches 공식 정책, 2026-04 기준)

**제출 시 플로우**
1. `api_batch_create` 상단에서 예상 계산
2. `budget.enabled` 이면 USD · tokens 두 임계치 모두 체크
3. 초과 시 `{ok:False, budgetExceeded:True, estimate, budget}` 반환
4. 프론트에서 confirmModal 로 차단 사유 + 예상 비용 · 토큰 상세 표시

**UI 추가**
- batchJobs 탭 상단에 **가드 상태 배너** (ON/OFF + 한도 표시 + ⚙️ 임계치 편집 버튼)
- "임계치 편집" 모달: enabled 토글 · maxPerBatchUsd · maxPerBatchTokens
- 제출 시 budgetExceeded 응답 오면 상세 모달 자동 노출

**Architecture**
- `server/batch_jobs.py` 확장: `_load_budget` · `_save_budget` · `_estimate_batch_cost` · `_PRICING` · `_BATCH_DISCOUNT=0.5` · `api_batch_budget_{get,set}`
- `api_batch_create` 에 pre-submit 가드
- `server/routes.py` 2 라우트 (GET budget · POST budget/set)
- `dist/index.html::VIEWS.batchJobs`: 가드 상태 배너 + `bjEditBudget` modal
- `bjSubmit` 에 `budgetExceeded` 분기
- `tools/translations_manual_9.py` 11 키 × ko/en/zh

## [2.16.0] — 2026-04-23

### 📝 Prompt Library — 신규 탭 `promptLibrary`

자주 쓰는 프롬프트를 태그와 함께 저장하고 검색 · 복사 · 복제 · **워크플로우로 변환** 가능한 라이브러리 탭.

**기능**
- CRUD 인라인 에디터: title · body · tags (쉼표 구분) · model
- 검색: 제목/본문/태그 substring (250ms debounce)
- 태그 chip 필터
- 카드별 액션 5개: 📋 복사 / ✏️ 수정 / 🗂️ 복제 / 🔀 워크플로우로 / 🗑️ 삭제
- 🔀 워크플로우로 — start → session(prompt) → output 3 노드 자동 생성 후 workflows 탭으로 이동
- 시드 3종 (코드 리뷰 / 회의 요약 / SQL 최적화)

**Architecture**
- `server/prompt_library.py` 신설 — `api_prompt_library_{list,save,delete,duplicate,to_workflow}` + SEED_ITEMS 3종
- 저장: `~/.claude-dashboard-prompt-library.json`
- workflows store 와 통합 (to-workflow 가 `_load_all/_dump_all/_new_wf_id` 사용)
- `server/routes.py` 5 라우트 (GET list · POST save/delete/duplicate/to-workflow)
- `server/nav_catalog.py` `promptLibrary` 탭 + en/zh
- `dist/index.html` NAV (icon 📝) + `VIEWS.promptLibrary` (에디터 + 카드 리스트 + 필터)
- `tools/translations_manual_9.py` 24 키 × ko/en/zh

## [2.15.0] — 2026-04-23

### 🧬 Embedding 비교 실험실 — 신규 탭 `embeddingLab`

같은 쿼리/문서 집합을 **Voyage AI · OpenAI · Ollama** 세 프로바이더에 돌려 cosine similarity + rank 를 비교.

**지원**
- Voyage AI — `voyage-3-large` / `voyage-3` / `voyage-3-lite` (VOYAGE_API_KEY 필요)
- OpenAI — `text-embedding-3-large` / `text-embedding-3-small`
- Ollama — `bge-m3` / `nomic-embed-text` / `mxbai-embed-large` (로컬)

**기능**
- 쿼리 1 + 문서 2~10 → 각 프로바이더 병렬 호출 → cosine + rank
- 프로바이더별 rank 나란히 + **rank Δ ≥ 2** 문서 자동 하이라이트
- 예시 2종 (FAQ 검색 / 유사 문장)
- 프로바이더별 모델 드롭다운 · 키 미설정 시 체크박스 비활성

**Architecture**
- `server/embedding_lab.py` 신설 — `api_embedding_{compare,providers,examples}`, `_cosine`, `_rank_desc`, `_voyage_embed` (stdlib HTTP)
- `ai_providers.embed_with_provider` 재사용 (OpenAI/Ollama)
- `ThreadPoolExecutor(max_workers=3)` 병렬 호출
- `server/routes.py` 3 라우트 (GET providers/examples · POST compare)
- `server/nav_catalog.py` `embeddingLab` 탭 + en/zh
- `dist/index.html` NAV (icon 🧬) + `VIEWS.embeddingLab` — 체크박스 · 인라인 모델 select · rank 테이블 · Δ 하이라이트
- `tools/translations_manual_9.py` 26 키 × ko/en/zh

## [2.14.1] — 2026-04-23

### Docs — README 3종 통계/탭 테이블 v2.14 기준 갱신

T5~T8 (v2.11.0 ~ v2.14.0) 신규 4 탭(serverTools · claudeDocs · citationsLab · agentSdkScaffold) 이 README 본문에 반영되도록 일괄 갱신.

- 배지 v2.9.1 → **v2.14.1**
- 미리보기 "45 탭" → **"49 탭"**
- Why 비교표 "45 tabs" → "49 tabs"
- Claude Code Integration 테이블:
  * 🆕 그룹에 `claudeDocs` 추가
  * 🛠️ Work 그룹에 `serverTools` · `citationsLab` · `agentSdkScaffold` 추가
- Architecture 트리: routes 168 → **178**, nav_catalog 45 → **49 tabs**, locales 3,090 → **3,157 keys**
- Stats 섹션을 v2.14.1 기준으로 갱신:
  * 백엔드 ~16,000줄/27 → **~17,000줄/42 모듈**
  * API 라우트 168 → **178** (GET 97 / POST 78 / PUT 3)
  * Claude API 플레이그라운드 탭 7 → **10**
  * **신규 행**: "공식 문서 색인 — 33 페이지"
- README ko/en/zh 3종 동등 반영

## [2.14.0] — 2026-04-23

### 🧪 Agent SDK 스캐폴드 — 신규 탭 `agentSdkScaffold`

`claude-agent-sdk` 기반 Python / TypeScript 프로젝트 뼈대를 UI 에서 생성 + Terminal 새 창에 초기화 명령 자동 붙여넣기.

**언어 · 도구**
- **Python** — `uv` (대체 제안: `brew install uv`)
- **TypeScript** — `bun` (대체 제안: `curl -fsSL https://bun.sh/install | bash`)

**템플릿 3종**
- `basic` — Messages API 1회 호출 + 응답 출력
- `tool-use` — tool 정의 + `tool_use → tool_result` 라운드 트립 (가짜 weather)
- `memory` — 대화 히스토리 JSON 저장

**생성 결과**
- `<path>/<name>/main.py` (py) 또는 `index.ts` (ts)
- `pyproject.toml` / `package.json` — uv sync / bun install 시 실제 의존성 설치
- `README.md` · `.gitignore`
- AppleScript 로 Terminal 새 창 열림 + `cd <path>/<name> && uv sync` (또는 `bun install`) 명령 **붙여넣기** (Enter 는 사용자가 누름)

**안전 장치**
- `name` 은 `[a-zA-Z][a-zA-Z0-9_-]{1,63}` 만 (path traversal 방지)
- `path` 는 `$HOME` 내부만
- `<path>/<name>` 이 이미 있으면 거부
- `uv`/`bun` 없으면 친절한 설치 힌트 포함 에러 (자동 설치 금지)

**Architecture**
- `server/agent_sdk_scaffold.py` 신설 — `api_scaffold_{catalog,create}` + 템플릿 본문 inline (python / ts × 3종)
- `server/routes.py` 2 라우트 (GET catalog · POST create)
- `server/nav_catalog.py` `agentSdkScaffold` 탭 (work 그룹) + en/zh
- `dist/index.html` NAV (icon 🧪) + `VIEWS.agentSdkScaffold` + `scCreate/scSet/scReset/openFolderFromPath`
- `tools/translations_manual_9.py` 25 키 × ko/en/zh

**한계**
- macOS 전용 (AppleScript Terminal). Linux/Windows 는 생성만 되고 Terminal 스폰은 실패 — 결과 카드에 `next command` 를 복사할 수 있도록 노출.

## [2.13.0] — 2026-04-23

### 📑 Citations 플레이그라운드 — 신규 탭 `citationsLab`

Anthropic Messages API 의 `citations.enabled` 응답 모드 실습. 문서를 `content` 의 document 블록으로 제공 + `citations: {enabled: true}` 를 세팅하면 답변 text block 에 `citations: [{cited_text, start_char_index, end_char_index, ...}]` 배열이 포함된다.

**기능**
- 예시 2종: 회사 소개문 / 기술 아티클
- 모델(Opus/Sonnet), 문서 제목(선택), 문서 본문 textarea, 질문 입력
- 답변 렌더링: 각 citation 을 `[N]` 번호 pill 로 본문 뒤에 inline 추가
- `[N]` hover → 원문 패널에서 해당 `start/end_char_index` 구간을 `<mark>` 로 하이라이트
- 히스토리 최근 20건 (`~/.claude-dashboard-citations-lab.json`)

**Architecture**
- `server/citations_lab.py` 신설 — `api_citations_{test,examples,history}` · examples 2 · text-type document 블록 구성
- `server/routes.py` 3 라우트 (GET examples/history · POST test)
- `server/nav_catalog.py` `citationsLab` 탭 (work 그룹) + en/zh desc
- `dist/index.html` NAV (icon 📑) + `VIEWS.citationsLab` · `ciHoverCit` · `ciLoadExample` · `ciRun` · `ciReset` · `ciSet`
- `tools/translations_manual_9.py` 17 키 × ko/en/zh

**한계 / 후속**
- 현재는 **text source** 만 지원. PDF / base64 document 는 T+N 에서 확장 예정.
- `page_location` citation 타입은 PDF 입력에서만 나타나므로 현 UI 는 `char_location` 중심.

## [2.12.0] — 2026-04-23

### 📖 Claude Docs Hub — 신규 탭 `claudeDocs` (new 그룹)

docs.anthropic.com 의 주요 페이지를 대시보드 안에서 카테고리별 카드로 색인 + 검색.

**카테고리 5**
- **Claude Code** — Overview / Sub-agents / Skills / Hooks / MCP / Plugins / Output Styles / Status Line / Slash Commands / Memory / Interactive / IAM / Settings / Troubleshooting (14)
- **Claude API** — Messages / Prompt Caching / Extended Thinking / Tool Use / Message Batches / Files / Vision / Citations / Web Search Tool / Code Execution Tool / Embeddings (11)
- **Agent SDK** — Overview / Python / TypeScript (3)
- **Models** — Models / Deprecations / Pricing (3)
- **Account & Policy** — Team / Glossary (2)

총 **33개 공식 페이지** 카드.

**기능**
- 제목/요약/URL 필터 (300ms debounce)
- 각 카드 2 버튼: `🔗 외부 열기` · `→ 관련 탭` (해당하는 대시보드 탭 id 가 있으면 `go(...)` 호출)
- 결과 없으면 친절한 empty state

**Architecture**
- `server/claude_docs.py` 신설 — 정적 `CATALOG` dict + `api_claude_docs_{list,search}`
- `server/routes.py` 2 라우트 (GET list/search)
- `server/nav_catalog.py` `claudeDocs` 탭 등록 (`new` 그룹) + en/zh
- `dist/index.html` NAV (icon 📖) + `VIEWS.claudeDocs` · `cdSet` · `cdRender` (debounce)
- `tools/translations_manual_9.py` 7 키 × ko/en/zh

**주의**
- URL 은 2026-04 시점 기준 추정. Anthropic 이 경로를 바꾸면 `CATALOG` 만 갱신하면 됨.

## [2.11.0] — 2026-04-23

### 🧰 Claude 공식 내장 Tools 플레이그라운드 — 신규 탭 `serverTools`

Anthropic 서버가 **직접 실행하는 hosted tool** 실습 탭. 기존 `toolUseLab` 이 사용자가 tool_result 를 수동 공급하는 구조라면, 이건 Anthropic 이 tool 을 실행하고 결과를 포함한 응답을 돌려준다.

**지원 도구**
- 🌐 **web_search** (`web_search_20250305`, beta `web-search-2025-03-05`) — 웹 검색 + citation
- 🧪 **code_execution** (`code_execution_20250522`, beta `code-execution-2025-05-22`) — Python sandbox (stdout / stderr / return_code)

**기능**
- 도구 체크박스 (model supportedModels 가드 — Haiku 비활성)
- 모델 선택 (Opus / Sonnet) + max_tokens
- 예시 3종 (뉴스 검색 / Python 계산 / 검색+분석 결합)
- 응답 content 블록 분류 시각화:
  * `server_tool_use` — 보라 카드 (tool 입력 JSON)
  * `*_tool_result` — 초록 카드 (실행 결과)
  * `text` — 최종 응답
- 히스토리 최근 20건 (`~/.claude-dashboard-server-tools.json`)

**Architecture**
- `server/server_tools.py` 신설 — `api_server_tools_{catalog,history,run}` + `TOOL_CATALOG` (beta 헤더 중앙화) + `EXAMPLES` 3종
- `server/routes.py` 3 라우트 추가 (GET catalog/history · POST run)
- `server/nav_catalog.py` `serverTools` 탭 등록 + en/zh desc
- `dist/index.html` NAV (icon 🧰) + `VIEWS.serverTools` + `stRun/stToggleTool/stLoadExample/stReset/stSet`
- `tools/translations_manual_9.py` 17 키 × ko/en/zh

**주의**
- beta header 스펙은 2026-04 시점 추정. Anthropic 에서 바뀌면 `TOOL_CATALOG[*].beta` 만 갱신.
- `web_search` / `code_execution` 호출은 별도 과금.

## [2.10.4] — 2026-04-23

### Fixed — v2.10.3 스모크 테스트 실행으로 드러난 2건

**1. `VIEWS.team` — `TypeError: t is not a function`**
team 탭 진입 시 `VIEWS.team` 이 로컬 변수 `const [t, auth] = ...` 로 전역 `t(key)` i18n 함수를 **섀도잉** → 이후 `${t('내 계정')}` 같은 모든 i18n 호출이 TypeError 로 실패.

- `VIEWS.team` 의 로컬 변수 `t` → **`team`** 으로 rename
- 본문 11개 참조 지점 (`t.displayName`, `t.organizationUuid`, `t.note` 등) 모두 갱신
- 주석으로 "전역 `t` 섀도잉 금지" 명기

이 버그는 사용자가 team 탭을 열었다면 즉시 드러났을 텐데, 수동으로 접속할 일이 적어 회귀로 남아 있었음. **E2E smoke 가 없었다면 찾기 어려웠을 회귀.**

**2. `scripts/e2e-tabs-smoke.mjs` — 오탐 가능 구조**
`document.querySelector('main')?.innerText` 에 "뷰 렌더 실패" / "View render failed" 문자열이 있는지 단순 포함 검사 → `memory` 탭에 메모리 노트 내용(ex. `feedback_escape_html_helper.md`)의 문자열이 포함되어 **정상 렌더를 실패로 오탐**.

- 검사 조건을 `#view .card.p-8.empty` element 존재 여부로 **엄격화**. `renderView()` catch 블록이 렌더하는 에러 카드만 검출 → 본문 텍스트 충돌 제거.
- 네비게이션을 `window.state.view = ...` → `location.hash = '#/<tab>'` (go() 와 동일 경로) 로 변경. 이전엔 전역 `state` 변수가 `window` 에 노출 안 돼 **실제 뷰 전환이 안 된 채 45 탭이 전부 통과** 하는 false-positive 가 있었음 → 이번 smoke 로 최초 true positive 확인.

**3. `package.json` — `"type": "module"` 제거**
v2.10.3 에서 추가했던 `"type": "module"` 이 기존 CommonJS 스크립트 `scripts/verify-translations.js` (`require` 사용) 를 깨뜨림. `.mjs` 파일은 명시 확장자로 ESM 처리되므로 `"type"` 필드 없이도 충분. 제거.

**결과**
- `HEADLESS=1 npm run test:e2e:smoke` → 45/45 탭 **실제 전수 통과**
- `npm run verify:i18n` → 3,096 키 × 3언어 · 0 누락

## [2.10.3] — 2026-04-23

### 🎭 Playwright E2E 스모크 스크립트

자동화 테스트로 회귀 방지. 모든 스크립트는 **라이브 서버(127.0.0.1:8080)** 를 대상으로 동작.

**scripts/e2e-tabs-smoke.mjs** (45 탭 전수 검사)
- `server/nav_catalog.py::TAB_CATALOG` 를 정적 파싱해 탭 id 목록 추출
- 각 탭으로 `window.state.view` 전환 + `renderView()` 호출 후
  - "뷰 렌더 실패" / "View render failed" 텍스트 검출 시 실패
  - `console.error` 발생 시 실패
- 단일 탭 검사: `TAB_ID=workflows npm run test:e2e:smoke`

**scripts/e2e-workflow.mjs** (빌트인 템플릿 실행 E2E)
- `bt-multi-ai-compare` 템플릿 조회 → `POST /api/workflows/save` 로 E2E 워크플로우 생성 → `POST /api/workflows/run`
- 5초간 `run-status` 폴링 + `#wfRunBanner.visible` 등장 여부 체크
- 완료 후 `POST /api/workflows/delete` 로 자동 정리
- critical error (`is not defined`, `View render failed`, `뷰 렌더 실패`) 발견 시 실패

**package.json**
- `scripts.test:e2e:smoke` / `test:e2e:workflow` / `test:e2e:headed` / `verify:i18n`
- `name`, `type:"module"`, `private:true` 추가 (ESM 스크립트 지원)

**.gitignore**
- `test-results/`, `playwright-report/`, `playwright/.cache/`, `node_modules/`

**README 3종**: `🎭 E2E 테스트` 섹션 (Troubleshooting 과 Contributing 사이) — `npx playwright install chromium` 안내 + 스크립트 사용법.

**주의**
- 최초 실행 전 `npx playwright install chromium` 필요 (약 150MB).
- 서버가 기동 중이 아니면 timeout 후 실패 — 테스트 실행 전 수동 기동.

## [2.10.2] — 2026-04-23

### 💬 노드 hover 결과 tooltip

실행 이력이 있는 노드에 마우스 hover 시 결과 미리보기 tooltip.

**내용**
- 상태 아이콘(✅/❌/⏳/⏭️) + 노드 제목 + 상태 라벨
- 소요 시간 (running 노드는 startedAt 기반 실시간, ok/err 는 durationMs)
- 제공자 · 모델 (있으면)
- 입력/출력 토큰 (있으면)
- 출력 미리보기 (앞 160자) 또는 에러 메시지 (앞 260자)

**UX**
- 280ms debounce → 손을 살짝 stop 시에만 노출, 지나갈 때는 안 뜸
- 마우스 이동 시 위치 따라감 (화면 경계 감지)
- 노드에서 벗어나면 즉시 숨김 (단 related target 이 다른 노드면 유지)
- 실행 이력 없는 노드는 표시 안 함 (노이즈 최소화)
- 상태별 left border 색 (ok 초록 / err 빨강 / running 보라 / skipped 회색)

**Architecture**
- `dist/index.html`:
  * CSS: `#wfNodeTooltip` + 상태별 variant
  * JS: `_wfShowNodeTooltip(nid, evt)` · `_wfHideNodeTooltip()` · delegation IIFE (mouseover/mousemove/mouseout)
- `tools/translations_manual_9.py`: 3 키 × ko/en/zh (건너뜀 / 제공자 / 토큰)

## [2.10.1] — 2026-04-23

### 🪟 노드 편집 모달 — 카테고리 그리드 접기

사용자 피드백 스크린샷: 노드 편집 모달 하단의 제목/모델/subject 등 필드가 항상 스크롤해야만 보임.

**원인**: `_wfRenderEditorBody` 가 타입 선택 여부와 무관하게 16개 노드 타입 그리드를 3열 × 4~6행으로 **항상 펼쳐서** 표시 → 720px 모달에서 약 160~200px(25~30%) 를 카테고리가 점유.

**수정**
- **기존 노드 편집** (type 이미 세팅): 기본 **접힘** — `[아이콘] [타입 라벨] 칩 · ▸ 타입 변경` 한 줄(≈48px)만 표시. 폼 영역에 +110~150px 추가 확보.
- **신규 노드 추가** (type 없음): 기본 **펼침** (기존 UX 유지).
- **타입 선택 직후 자동 접힘** + 첫 입력 필드(제목/subject 등) autofocus.
- **토글 버튼** `▾ 접기` / `▸ 타입 변경` (tooltip: `Alt+C`).
- **단축키** `Alt+C` — 워크플로우 탭에서 노드 편집 창이 열려 있을 때 토글.
- **localStorage 기억** (`wfEditorCatExpanded`): 사용자 취향 영속.

**Architecture**
- `dist/index.html`:
  * `_wfCatIsExpanded(draft)` · `_wfToggleCat(winId)` 신규
  * `_wfRenderEditorBody` 가 expanded 분기로 재구성 (접힘 시 칩 + 변경 버튼)
  * `_wfPickNodeType` 종료 후 localStorage 접힘 + first-field autofocus
  * 워크플로우 키보드 핸들러에 `Alt+C` 토글 분기 추가
- `tools/translations_manual_9.py`: 4 키 × ko/en/zh (타입 / 타입 변경 / 접기 / 펼치기)

## [2.10.0] — 2026-04-23

### 🔦 워크플로우 실행 가시성 강화

사용자 피드백: "**워크플로우가 지금 어느 노드에서 실행 중인지 보기 어렵다**".

기존 `data-status` CSS 는 작동했지만 시각적 강조가 약했고, 큰 캔버스에서 running 노드가 화면 밖이면 전혀 알 수 없었음.

**상단 플로팅 실행 배너 (신규)**
- `#wfRunBanner` — 캔버스 상단 중앙 고정
- 포맷: `⏳ [노드명] · {완료}/{전체} · {경과초}s · 진행률 바 · 📍 위치로 이동`
- 상태별 색: running (보라 · pulse) / ok (초록) / err (빨강)
- 완료·실패 3.5초 후 자동 페이드아웃
- 수동 닫기 버튼

**Running 노드 시각 강화**
- 외곽 점선 링 (`.wf-node-ring`, stroke-dasharray 6 6) + 회전 애니메이션 (`@keyframes wfSpinDash`, 2.5s linear)
- `drop-shadow` 보라 글로우 추가
- 라벨 옆 `⏱ {초}s` 실시간 카운터 (`.wf-node-elapsed`)

**미니맵 상태 색 반영**
- running/ok/err/skipped 색을 node dot 에 우선 적용
- running 노드는 dot 크기 3px → 5px 로 강조

**서버 SSE 폴링 1.0s → 0.5s**
- `handle_workflow_run_stream`: `time.sleep(0.5)` + `max_polls = 3600` (30분 유지)
- 서버 노드 실행 시작 시 `nodeResults[nid].startedAt` 기록 → 프론트 elapsed 계산

**위치로 이동 (`_wfFocusNode`)**
- 배너의 📍 버튼 또는 직접 호출로 해당 노드를 뷰포트 중앙에 pan (zoom 유지)

**i18n** — 6 키 × ko/en/zh (실행 중 / 대기 중 / 완료 / 실패 / 위치로 이동 / 닫기). 총 **3,092 키** · 누락 0.

**Architecture**
- `server/workflows.py`: `handle_workflow_run_stream` sleep 0.5s, `_run_one_iteration` running 상태에 `startedAt` 포함
- `dist/index.html`:
  * CSS: `#wfRunBanner` 스타일, `.wf-node-ring` / `.wf-node-elapsed` 추가, `wfSpinDash` keyframe
  * JS: `_wfApplyRunStatus` 확장 (배너/미니맵 호출), `_wfRenderRunBanner`, `_wfHideRunBanner`, `_wfFocusNode` 신규
  * `_wfRenderNode` SVG 템플릿에 `<rect class="wf-node-ring">` + `<text class="wf-node-elapsed">` 삽입
  * `_wfRenderMinimap` node dot 에 실행 상태 색 우선 적용
- `tools/translations_manual_9.py`: 6 키 ko/en/zh
- `dist/locales/{ko,en,zh}.json`: 3,092 키 재빌드

## [2.9.3] — 2026-04-23

### Fixed — 빌트인 워크플로우 템플릿 조회 실패 (404 → "템플릿 생성 에러")

사용자 리포트: **"멀티 AI 비교 커스텀 템플릿을 사용하려는데 error 라고 나오면서 안 생성돼"**.

**원인**
`server/routes.py::_ITEM_GET_ROUTES` 의 템플릿 단일 조회 정규식이 `(tpl-[0-9]{10,14}-[a-z0-9]{3,6})` 로 **커스텀 템플릿 id 포맷만 허용**하고 있었다. `workflows.py::BUILTIN_TEMPLATES` 의 id 는 `bt-multi-ai-compare / bt-rag-pipeline / bt-code-review / bt-data-etl / bt-retry-robust` 5종으로 전혀 다른 포맷이라 매칭 실패 → `GET /api/workflows/templates/bt-multi-ai-compare` 가 계속 **404**. 프론트의 템플릿 상세 fetch 가 실패해 워크플로우 생성이 중단됨.

`api_workflow_template_get` 핸들러 자체는 이미 `BUILTIN_TEMPLATES` 먼저 조회 후 fallback 으로 custom 저장소를 뒤지는 올바른 구조였음 — 라우트 레이어에서 도달조차 못 하던 문제.

**수정**
- `server/routes.py` 정규식을 `(tpl-[0-9]{10,14}-[a-z0-9]{3,6}|bt-[a-z0-9-]+)` 로 확장해 두 id 포맷 모두 허용.

**검증**
5개 빌트인 템플릿 전수 스모크:
- `bt-multi-ai-compare` (멀티 AI 비교, 6 nodes) ✓
- `bt-rag-pipeline` (RAG 파이프라인, 5 nodes) ✓
- `bt-code-review` (코드 리뷰, 5 nodes) ✓
- `bt-data-etl` (데이터 ETL, 5 nodes) ✓
- `bt-retry-robust` (재시도, 5 nodes) ✓

모두 `ok: True`, 정확한 노드 수 반환.

## [2.9.2] — 2026-04-23

### Docs — README 3종 통계/탭 테이블 전면 갱신

v2.3.0 ~ v2.9.1 누적 결과를 README 의 본문 섹션에 반영 (그간 상단 배너만 추가하고 본문 통계가 v2.1.1 로 남아있었음).

- 버전 배지 **v2.9.0 → v2.9.1**
- ASCII 미리보기 표기 "6 그룹 38 탭" → **"6 그룹 45 탭"**
- "Why" 비교 표 셀 "38 탭" → **"45 탭"**
- `🤝 Claude Code Integration` 탭 테이블의 work 그룹에 신규 7 탭(`promptCache` `thinkingLab` `toolUseLab` `batchJobs` `apiFiles` `visionLab` `modelBench`) 🆕 표시로 추가 + "Claude API 플레이그라운드" 하이라이트 줄 추가
- Architecture 트리: `routes.py` 143 → **168 라우트**, `nav_catalog.py` 38 → **45 탭**, `locales` 2,932 → **3,090 키**
- `🔢 Stats (v2.1.1)` 섹션 전체를 **`v2.9.1`** 기준으로 갱신:
  - 백엔드 14,067줄/20 모듈 → **~16,000줄/27 모듈**
  - 프론트 ~13,500줄 → **~15,500줄**
  - API 라우트 143 → **168 (GET 90 / POST 75 / PUT 3)**
  - 탭 38 → **45**
  - i18n 키 2,932 → **3,090**
  - 신규 행: "Claude API 플레이그라운드 탭 — 7"
- README.md / README.ko.md / README.zh.md 3종 동등 구조로 반영.

## [2.9.1] — 2026-04-23

### Fixed — v2.3.0~v2.9.0 신규 탭 렌더 실패 + NAV desc 번역 누락

**`_escapeHTML is not defined` 런타임 에러 해소**
- v2.3.0~v2.9.0 에서 추가한 7개 VIEWS (`promptCache`, `thinkingLab`, `toolUseLab`, `batchJobs`, `apiFiles`, `visionLab`, `modelBench`) 가 **존재하지 않는 `_escapeHTML()`** 을 참조해 탭 진입 즉시 "View render failed" 에러가 나던 문제.
- 저장소 실제 헬퍼 이름은 **`escapeHtml`** (소문자 HTML 중 H 만 대문자).
- `dist/index.html` 에서 `_escapeHTML(` → `escapeHtml(` 21곳 일괄 치환.

**i18n 14건 누락 번역 보강**
- NAV `desc` 7개 (work 그룹 신규 탭들) — `escapeHtml(t(n.desc))` 경로에 번역이 없어 한국어 원문이 영/중문 모드에서도 그대로 노출되던 문제.
- `confirmModal` 메시지 템플릿 (`총 {n} 건을 ...`, `회 API 호출을 수행합니다 (...`) 의 한글 조각들을 extractor 가 잘못 뽑아 missing 이던 7건.
- `tools/translations_manual_9.py::NEW_EN` / `NEW_ZH` 에 14 키 × 2언어 추가.
- 결과: `build_locales.py` **Missing EN/ZH 0** · `verify-translations.js` 전체 통과 (3,090 키 × 3언어).

## [2.9.0] — 2026-04-23

### 🏁 Model Benchmark — 신규 탭 (work 그룹)

사전 정의 프롬프트 셋 × 선택한 모델들을 교차 실행해 성능·비용을 집계한다.

**기능**
- 프롬프트 셋 3종: 기본 Q&A(5) / 코드 생성(3) / 추론·수학(3)
- 모델 3개 체크박스 (Opus 4.7 / Sonnet 4.6 / Haiku 4.5)
- 실행 전 confirmModal 로 총 호출 수 · 비용 발생 경고
- ThreadPoolExecutor(max_workers=4) 로 prompt × model 조합 병렬 실행
- 모델별 집계 표: 성공 건수 · 평균 지연 · 평균 출력 토큰 · 총 비용(USD)
- 개별 응답 매트릭스 (모델 · 프롬프트 · 응답 미리보기 · 지연 · 비용)
- JSON 다운로드 버튼

**Architecture**
- `server/model_bench.py` 신설 — `api_model_bench_{sets,run}` + `_call_once` + `_PRICING` 테이블
- `server/routes.py` — 2개 라우트 추가
- `server/nav_catalog.py` — `modelBench` 탭 등록 + en/zh desc
- `dist/index.html` — NAV + `VIEWS.modelBench`
- `tools/translations_manual_9.py` — 28 키 × ko/en/zh

### 📜 v2.3 ~ v2.9 로드맵 완료

2026-04-23 연속 릴리스로 **Claude API 플레이그라운드 7 탭**을 work 그룹에 추가: `promptCache`(v2.3.0) · `thinkingLab`(v2.4.0) · `toolUseLab`(v2.5.0) · `batchJobs`(v2.6.0) · `apiFiles`(v2.7.0) · `visionLab`(v2.8.0) · `modelBench`(v2.9.0). 원격 v2.2.1 위에 rebase 된 결과 버전 번호를 한 칸 shift 했다.

---

## [2.8.0] — 2026-04-23

### 👁️ Vision / PDF Lab — 신규 탭 (work 그룹)

이미지(PNG/JPG/WebP/GIF) 또는 PDF 를 업로드해 Opus / Sonnet / Haiku 3 모델에 병렬 질의 → 응답 비교.

**기능**
- 파일 선택 → 자동 base64 인코딩 (최대 10MB)
- 이미지: `type:"image"` 블록, PDF: `type:"document"` 블록으로 content 구성
- 3 모델을 **ThreadPoolExecutor** 로 병렬 호출
- 각 모델별 응답/지연/토큰 사용량 카드 나란히 표시
- 총 소요 시간 + 모델 수 요약

**Architecture**
- `server/vision_lab.py` 신설 · `server/routes.py` 라우트 2개 · NAV + `VIEWS.visionLab` · 16 i18n 키 × 3언어

---

## [2.7.0] — 2026-04-23

### 📎 Files API — 신규 탭 (work 그룹)

Anthropic Files API 업로드/목록/삭제 + 메시지 document reference 를 UI 에서 다룬다.

**기능**
- 브라우저 파일 선택 → base64 전송 → 서버 multipart/form-data → Anthropic 업로드 (최대 30MB)
- 업로드된 파일 목록 (filename · size · mime · id)
- 파일 선택 → 모델 선택 → 질문 → `{type:"document", source:{type:"file", file_id}}` 블록으로 질의
- 개별 삭제 + 삭제 전 확인 모달

**Architecture**
- `server/api_files.py` 신설 · stdlib multipart POST 유틸 · 라우트 4개 (GET list · POST upload/delete/test)
- beta header: `anthropic-beta: files-api-2025-04-14`
- i18n 22 키 × 3언어

---

## [2.6.0] — 2026-04-23

### 📦 Batch Jobs — 신규 탭 (work 그룹)

Anthropic Message Batches API 로 대용량 프롬프트 병렬 제출·상태 폴링·JSONL 결과 다운로드.

**기능**
- 원클릭 예시 2종: Q&A 10건 / 요약 5건
- 모델 + max_tokens 조절 · 프롬프트 한 줄당 1건 (최대 1000건)
- 제출 전 **비용 발생 경고** 모달 (confirmModal)
- 최근 배치 목록 + 상태 + request_counts · JSONL 결과 프리뷰
- 진행 중 배치 취소 지원

**Architecture**
- `server/batch_jobs.py` 신설 · 라우트 6개 (GET examples/list/get/results · POST create/cancel)
- beta header: `anthropic-beta: message-batches-2024-09-24`
- i18n 30 키 × 3언어

---

## [2.5.0] — 2026-04-23

### 🛠️ Tool Use Playground — 신규 탭 (work 그룹)

Anthropic Tool Use 의 라운드 트립(user → tool_use → tool_result → next turn)을 수동으로 연습.

**기능**
- 기본 도구 템플릿 3종 원클릭: `get_weather` / `calculator` / `web_search` (mock)
- tools JSON 배열 직접 편집
- 대화 버블 (role · text · tool_use · tool_result 구분 색)
- tool_use 수신 시 인라인 tool_result 입력 폼 → 제출 → 다음 턴 자동 호출
- "새 대화" 버튼으로 messages 초기화

**Architecture**
- `server/tool_use_lab.py` 신설 · 라우트 3개 · i18n 13 키 × 3언어
- 히스토리 `~/.claude-dashboard-tool-use-lab.json`

---

## [2.4.0] — 2026-04-23

### 🧠 Extended Thinking Lab — 신규 탭 (work 그룹)

Claude Opus 4.7 / Sonnet 4.6 의 Extended Thinking 을 실험하고 thinking block 을 분리 시각화.

**기능**
- 원클릭 예시 3종: 수학 추론 / 코드 디버깅 / 설계 플래닝
- `budget_tokens` 슬라이더 (1024 ~ 32000, 512 단위)
- thinking block 과 최종 응답을 **접기/펴기** 로 분리 표시
- Haiku 선택 시 비지원 경고
- 히스토리 최근 20건

**Architecture**
- `server/thinking_lab.py` 신설 · 라우트 4개 (GET examples/history/models · POST test)
- i18n 16 키 × 3언어

---

## [2.3.0] — 2026-04-23

### 🧊 Prompt Cache Lab — 신규 탭 (work 그룹)

Anthropic Messages API 의 `cache_control` 을 실험/관측하는 전용 플레이그라운드.

**기능**
- 원클릭 예시 3종: 시스템 프롬프트 캐시 / 대용량 문서 캐시 / 도구 정의 캐시
- 모델 선택 (Opus 4.7 / Sonnet 4.6 / Haiku 4.5) + max_tokens 조절
- system / tools / messages JSON 편집기
- 응답 즉시: input / output / cache_creation / cache_read 토큰 + USD 비용 + 캐시 절감 추정
- 히스토리 최근 20건 (`~/.claude-dashboard-prompt-cache.json`)

**Architecture**
- `server/prompt_cache.py` 신설 (297줄) — `api_prompt_cache_test/history/examples` + `_estimate_cost` (3 모델 가격 테이블)
- `server/routes.py` — 라우트 3개 (GET examples/history · POST test)
- `server/nav_catalog.py` — `promptCache` 탭 등록 + en/zh desc
- `dist/index.html` — NAV + `VIEWS.promptCache`
- `tools/translations_manual_9.py` — 35 키 × ko/en/zh


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
