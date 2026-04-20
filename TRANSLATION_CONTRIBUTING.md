# Translation Contributing Guide

이 프로젝트의 다국어(i18n) 아키텍처와 신규 텍스트 추가 워크플로를 정리한 문서.

## 한 줄 요약

`dist/index.html` 의 한국어 텍스트를 **런타임**에 `dist/locales/{ko,en,zh}.json` 로 치환한다.
UI 를 수정한 뒤에는 반드시 `make i18n-refresh` (또는 `bash scripts/translate-refresh.sh`) 실행.

## 아키텍처

```
browser                          server                            repo
────────                         ──────                            ─────
GET /                   ─►  server.Handler._send_static   ─►  dist/index.html (단일 파일)
  └ boot() ──await window._i18nReady──►
       _loadLocale(curLang)                                    
         └ GET /api/locales/{ko|en|zh}.json                    
                                ─►  _send_locale              ─►  dist/locales/*.json
                                                                  (번역 사전)
       _translateDOM(document.body)
         └ 한국어 원문을 key 로 dict lookup → 텍스트 노드 · 속성값 교체
```

- **한국어 원문이 key**: `I18N.en['저장'] = 'Save'` 식 — 번역 파일은 "원문 → 번역" 매핑.
- **JS 런타임 헬퍼**: `t('한국어 원문')` → 현재 언어 번역 반환 (없으면 원문 fallback).
- **DOM 워커**: `_translateDOM(root)` — 텍스트 노드 전체 일치 → 길이 내림차순 부분 치환 (≥5 글자 키).
- **언어 전환**: `setLang('en')` → 쿠키 세팅 → `location.reload()` → 재로드 시 새 locale fetch.

## 파일 구조

| 파일 | 역할 |
|---|---|
| `dist/index.html` | UI 원본 (한국어) |
| `dist/locales/ko.json` | identity — `{ "저장": "저장", ... }` |
| `dist/locales/en.json` | 영어 번역 사전 |
| `dist/locales/zh.json` | 중국어 번역 사전 |
| `tools/extract_ko_strings.py` | dist/index.html → translation-audit.json |
| `tools/build_locales.py` | audit + manual 병합 → dist/locales/*.json |
| `tools/translations_manual.py` | 수동 번역 사전 (EN · ZH · KO 라벨 · NEEDS_REVIEW) |
| `tools/translations_manual_zh_missing.py` | ZH 보충 (Phase 1) |
| `tools/translations_manual_2.py` | Phase 1 재검증에서 추가 111 phrase 번역 |
| `tools/runtime_ko_scan.py` | 런타임 번역 시뮬레이터 — 한글 잔존 0 체크 |
| `scripts/verify-translations.js` | 4-단계 사전 검증 (키 일치 · t() · audit · DOM 커버리지) |
| `scripts/translate-refresh.sh` | 파이프라인 단일 진입점 |
| `translation-audit.json` | 감사 파일 (phrase 전수 목록) |
| `translation-review.md` | 검수 필요 목록 (NEEDS_REVIEW 로부터 자동 생성) |

## 신규 텍스트 추가 워크플로

### A. UI 에 새 한국어 문자열을 넣은 경우

1. `dist/index.html` 편집 (HTML 텍스트 · 속성 · JS `t('…')` · 템플릿 리터럴)
2. `make i18n-refresh`
   - 한글 phrase 자동 추출
   - 기존 사전과 병합 후 누락 보고
   - 누락이 있으면 빌드 결과에 `Missing EN: n, Missing ZH: n` 표시
3. 누락된 phrase 를 `tools/translations_manual.py` 의 `MANUAL_EN` / `MANUAL_ZH` 에 추가
4. 다시 `make i18n-refresh` → `Missing EN: 0, Missing ZH: 0` 확인
5. `git diff dist/locales/` 로 신규 키 확인 후 커밋

### B. 기존 번역을 다듬을 때

1. `tools/translations_manual.py` 에서 해당 key 의 EN/ZH 값을 덮어쓰기
   (MANUAL_* 는 baseline locale 보다 우선 적용되는 override)
2. `make i18n-refresh`
3. 커밋

### C. 번역 검수가 필요한 항목 등록

- 확신이 없거나 브랜드/법률 용어가 포함된 경우:
  `tools/translations_manual.py::NEEDS_REVIEW` 에 key 추가
- `make i18n-refresh` 후 `translation-review.md` 에 자동 등록됨
- 검수 완료되면 `NEEDS_REVIEW` 에서 제거

## 트러블슈팅

### `Missing EN/ZH: N` 이 0 이 아니다
→ `_missing.json` 에서 누락 key 목록 확인. `tools/translations_manual.py` 에 추가 후 재실행.

### verify-translations.js 의 `t() 인자 번역 누락`
→ JS 코드에서 `t('새 한국어')` 가 추가됐는데 사전에 없을 때. 위 A 단계 진행.

### runtime_ko_scan.py 에서 `static nodes with Korean residue > 0`
→ HTML 에 새 한국어 텍스트 노드가 있으나 사전에 없거나 부분 치환 미커버. 위 A 단계 진행.

### CI 에서 `dist/locales 가 최신 빌드와 다릅니다`
→ 로컬에서 `make i18n-refresh` 실행 후 생성된 `dist/locales/*.json` · `translation-audit.json` 을 커밋.

## 설계 원칙

1. **한국어 원문 = key** — 이중 관리 방지, `ko.json` 은 identity.
2. **MANUAL 이 baseline 보다 우선** — 한 번 번역한 값은 재빌드에도 유지.
3. **파이프라인은 idempotent** — 여러 번 돌려도 결과 동일.
4. **CI 는 Local 과 동일한 스크립트 사용** — `translate-refresh.sh` 하나.
5. **번역 누락 0건** — verify-translations.js + runtime_ko_scan.py 둘 다 통과해야 merge.
