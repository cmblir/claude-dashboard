# Translation System Migration (2026-04-21)

## 요약

대시보드의 i18n 시스템을 **인라인 사전 + 사전 빌드 HTML 3벌** 구조에서
**런타임 fetch 기반 단일 HTML + 외부 JSON 로케일** 구조로 교체.

## 배경

### 기존 방식의 문제
- `dist/index.html` 안에 `I18N.en = {...}` · `const zhMap = {...}` 인라인 사전
  (두 블록 합쳐 약 1,160 줄)
- `build-i18n.py` 가 정규식으로 한국어를 치환해서 `dist/index-en.html`
  · `dist/index-zh.html` 두 파일을 별도로 생성 (8,056 줄짜리 파일 3벌)
- 번역 누락 편차 심각: EN 사전 999 항목, ZH 사전 573 항목
  (ZH 에 없는 항목 424건 존재 — 런타임에 한국어 그대로 노출됨)

### 새 방식의 이점
- `dist/index.html` 1 개 파일만 존재 (2,000+ 줄 감소)
- 번역은 `dist/locales/{ko,en,zh}.json` 으로 분리 — 편집 · 검수 용이
- `scripts/verify-translations.js` 가 CI-friendly 0-miss 검증
- 언어 변경 시 HTML 리로드 유지 (쿠키 · 쿼리 파라미터는 그대로)

## 변경 사항

### 추가
| 파일 | 목적 |
|---|---|
| `dist/locales/ko.json` | 한국어 원문 (identity 매핑) |
| `dist/locales/en.json` | 영어 번역 1,148 키 |
| `dist/locales/zh.json` | 중국어 번역 1,148 키 |
| `tools/extract_ko_strings.py` | 한국어 phrase 전수 추출기 |
| `tools/build_locales.py` | 사전 빌드 + 누락 보고 |
| `tools/translations_manual.py` | 수동 번역 사전 (구조화 키 · 신규 · 오버라이드) |
| `tools/translations_manual_zh_missing.py` | ZH 보충 번역 (426 항목) |
| `scripts/verify-translations.js` | 4-단계 검증 스크립트 |
| `translation-audit.json` | 원본 phrase 감사 파일 (1,104 항목) |
| `translation-review.md` | 번역 검수 권장 목록 (자동 생성) |
| `TRANSLATION_MIGRATION.md` | 이 문서 |

### 수정
- `dist/index.html`
  - `I18N.en` · `zhMap` 인라인 사전 블록 제거 (약 61KB · 1,162 줄 삭제)
  - `_loadLocale(lang)` 추가 — `/api/locales/{lang}.json` fetch
  - `window._i18nReady` 프로미스 도입 · `boot()` 가 await
- `server/routes.py`
  - `_send_locale(lang)` 추가 — 화이트리스트(ko/en/zh) 검증 후 JSON 서빙
  - `_send_static` 의 `index-en.html` · `index-zh.html` 분기 제거
  - `_get_lang` 제거 (더 이상 서버측 언어 판별 불필요)
- `.gitignore`
  - `dist/index-en.html` · `dist/index-zh.html` 제외 규칙 제거
  - `_missing.json` (빌드 산출물) 추가

### 삭제
- `build-i18n.py`
- `dist/index-en.html`
- `dist/index-zh.html`

## 검증 결과

```
─── 1) 키 일치 검증 ───
ko: 1148, en: 1148, zh: 1148
  ✓ 3개 파일의 키 집합 일치

─── 2) 사용처 검증 (t('...') 호출) ───
t() 호출 한국어 인자: 48
  ✓ 모든 t() 인자가 ko/en/zh 에 존재

─── 3) 원본 대조 검증 (translation-audit.json) ───
audit items: 1104
  ✓ audit 항목 모두 번역됨

─── 4) 정적 DOM 한국어 phrase 검증 ───
static DOM phrases: 22
  ✓ 모든 정적 DOM phrase 가 번역 커버됨

─── 요약 ───
✓ 모든 검증 통과
```

## 런타임 확인
- `PORT=8090 python3 server.py` — 구동 성공
- `GET /` → 200 (단일 `index.html`, 379KB)
- `GET /api/locales/ko.json` → 200 (68KB · 1,148 키)
- `GET /api/locales/en.json` → 200 (63KB · 1,148 키)
- `GET /api/locales/zh.json` → 200 (62KB · 1,148 키)
- `GET /api/locales/xx.json` → 404 (화이트리스트 차단 확인)

## 다음 단계 (권장)
1. 번역 전문가 검수 — `translation-review.md` 9개 항목 (긴 안내 문구)
2. E2E 테스트에서 3개 언어 각각 렌더링 검증
3. 후속 UI 수정 시 다음 순서 준수:
   ```
   python3 tools/extract_ko_strings.py
   # 신규 phrase 를 tools/translations_manual.py 에 번역 추가
   python3 tools/build_locales.py
   node scripts/verify-translations.js
   ```

---

## Phase 2 (2026-04-21 추가분) — 프로덕션 투입 확정

이전 마이그레이션 이후의 후속 작업을 기록.

### 추가된 파일
| 파일 | 역할 |
|---|---|
| `tools/runtime_ko_scan.py` | 브라우저 런타임 `_translateDOM` 규칙을 파이썬으로 시뮬레이션 — en/zh 적용 후 한글 잔존 0 검증 |
| `tools/translations_manual_2.py` | 이번 세션 재추출에서 추가 발견된 111개 phrase 의 EN/ZH 번역 |
| `scripts/translate-refresh.sh` | 파이프라인 단일 진입점 (추출 → 빌드 → 검증 → 런타임 스캔) |
| `.github/workflows/translations.yml` | CI — PR/merge 시 4단계 검증 자동 실행 |
| `.github/pull_request_template.md` | i18n 관련 체크리스트 포함 PR 템플릿 |
| `Makefile` | `make i18n-refresh` / `i18n-verify` / `i18n-scan` / `run` / `dev` |
| `TRANSLATION_CONTRIBUTING.md` | 신규 텍스트 추가 워크플로 · 트러블슈팅 |
| `runtime-verification-report.md` | PHASE 2 실측 리포트 |

### 변경된 파일
- `tools/extract_ko_strings.py` — `const _KO_RE = /[가-힣]/` 같은 JS 정규식 리터럴 선언 라인은 UI 문자열에서 제외
- `tools/build_locales.py` — **멱등성 강화**: 기존 `dist/locales/*.json` 을 baseline 으로 로드, 재빌드해도 번역 유실 없음
- `tools/translations_manual.py` — 검수 9건 확정 번역으로 폴리싱 · `NEEDS_REVIEW = set()` (전부 처리) · `translations_manual_2` 자동 병합

### 번역 확장
- 이번 세션 재추출에서 기존 baseline 에 없던 111 phrase 가 발견되어 EN/ZH 수동 번역 완료.
- 최종 사전 키 수: **1,148 → 1,259** (모든 언어 동일).

### 최종 검증 결과 (2026-04-21)
```
✓ 4-step verifier: 키 일치 · t() · audit · static DOM
✓ runtime scan: en/zh 한글 잔존 0건
✓ live endpoints: / 200 · /api/locales/{ko,en,zh}.json 200 · xx 404
✓ API 회귀: /api/skills /api/agents /api/projects /api/system/info 전부 200
✓ 응답시간: html ~2ms · locale ~1ms (로컬 vanilla HTTP)
```

### 상태
🟢 **프로덕션 투입 준비 완료**
- 번역 누락 0건, 한글 잔존 0건, CI 자동화, 기여 가이드 확립.
