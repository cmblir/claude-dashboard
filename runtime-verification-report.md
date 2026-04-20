# Runtime Verification Report

**Date:** 2026-04-21
**Scope:** dist/index.html + dist/locales/{ko,en,zh}.json + server/routes.py

---

## 1. 정적 번역 시뮬레이션 (tools/runtime_ko_scan.py)

브라우저 런타임 `_translateDOM` 의 번역 규칙(전체 일치 → 길이 내림차순 부분 치환 ≥5 글자)을
파이썬에서 동일하게 재현하여 `dist/index.html` 의 모든 정적 DOM 텍스트 노드와
`t('…')` 호출 인자를 적용 후 한글 잔존을 검사.

| 언어 | static node residue | t() 인자 residue | 합계 |
|---|---:|---:|---:|
| en | 0 | 0 | **0** |
| zh | 0 | 0 | **0** |

→ **en/zh 모드에서 한글 잔존 0건** (불변 규칙 충족).

## 2. 빌드 파이프라인 검증 (scripts/verify-translations.js)

| 검증 | 결과 |
|---|---|
| ① 키 일치 (ko/en/zh 동일 1,259 키) | ✓ |
| ② t() 인자 번역 존재 (48/48) | ✓ |
| ③ translation-audit.json 모두 번역 (466/466) | ✓ |
| ④ 정적 DOM phrase 커버리지 (22/22) | ✓ |

## 3. 라이브 서버 스모크 (127.0.0.1:8091)

| 요청 | 결과 | 크기 |
|---|---|---:|
| `GET /` | 200 | 379,355 B |
| `GET /?lang=en` | 200 | 379,355 B |
| `GET /?lang=zh` | 200 | 379,355 B |
| `GET /api/locales/ko.json` | 200 | 68,465 B |
| `GET /api/locales/en.json` | 200 | 63,072 B |
| `GET /api/locales/zh.json` | 200 | 62,197 B |
| `GET /api/locales/xx.json` | 404 | — |
| `GET /` (쿠키 `cc-lang=en`) | 200 | 379,355 B |

## 4. API 회귀 테스트

| 엔드포인트 | 상태 |
|---|---|
| `GET /api/skills` | 200 (1,397,377 B) |
| `GET /api/agents` | 200 (306,187 B) |
| `GET /api/projects` | 200 (1,098 B) |
| `GET /api/system/info` | 200 |

→ 번역 외 기능 회귀 없음.

## 5. JS / Python 문법 검증

| 파일 | 결과 |
|---|---|
| `dist/index.html` (JS 본문) — `new Function(...)` | ✓ 파싱 성공 |
| `server/routes.py` — `py_compile` | ✓ 통과 |

## 6. Locale 파일 크기

| 파일 | 키 수 | 크기 |
|---|---:|---:|
| `dist/locales/ko.json` | 1,259 | 68,465 B |
| `dist/locales/en.json` | 1,259 | 63,072 B |
| `dist/locales/zh.json` | 1,259 | 62,197 B |

대시보드 전체 HTML (379KB) 대비 각 ~16% 수준, 페이지 로드 1-RTT 내 수신 가능.
청킹 불필요.

## 7. 언어 전환 UX (static review)

- `setLang(lang)` → 쿠키 세팅 + `location.reload()`  
  → reload 후 `_initLang` 가 쿠키/쿼리로 `_curLang` 재감지  
  → `window._i18nReady` 가 해당 언어 locale 을 `fetch('/api/locales/{lang}.json')` 후 `_translateDOM`  
  → `boot()` 가 `await window._i18nReady` 이후 렌더
- `localStorage` 저장 없음 (쿠키 1년 + URL 쿼리 동기화로 충분)
- 새 탭 → 쿠키 공유로 선택 언어 자동 유지

## 결론

✅ **프로덕션 투입 가능 상태 — en/zh 모드에서 한글 잔존 0건 달성.**
