# QA — lazyclaw 기능 제거 후 lazyclaude 대시보드 자가 검증

- 날짜: 2026-05-18
- 대상 변경: lazyclaw 16탭 + `/api/lc/*` + proxy + i18n + e2e 제거 (v3.99.29)
- 도구: Playwright MCP (managed Chromium) — `node_modules/playwright` 미설치 환경
- 서버: `python3 server.py` @ 127.0.0.1:19500 (pid 83348)

## 검증 항목

| 항목 | 방법 |
|---|---|
| 콘솔 에러 0 | boot + lcChat(stale) + overview/workflows/aiProviders/sessions 네비게이션 전체 |
| lazyclaw nav/그룹 부재 | DOM `a,button,[role=tab],li` 텍스트 스캔 (🦞 Ralph Loop 오탐 제외 — 무관 기능) |
| 가시 lazyclaw 텍스트 부재 | `document.body.innerText` 정규식 |
| stale `lc*` 탭 안전 폴백 | `#/lcChat` / `#/lcRunner` → overview 렌더 (blank/throw 없음) |
| 핵심 탭 무회귀 | overview·workflows·aiProviders·sessions 렌더 길이 + 에러문구 검사 |
| 반응형 무파손 | `scrollWidth ≤ innerWidth` (가로 스크롤/잘림 없음) |

## 결과 — 3종 뷰포트 모두 PASS

| 뷰포트 | 콘솔 err/warn | lazyclaw nav | lazyclaw 텍스트 | stale→fallback | core 탭 | 가로 오버플로 | 스크린샷 |
|---|---|---|---|---|---|---|---|
| 1280×800 데스크톱 | 0 / 0 (16 msg) | 0 | 0 | overview ✓ | 4/4 렌더 | 없음 | qa-lazyclaw-removal-1280.png |
| 768×800 작은창 | 0 / 0 (8 msg) | 0 | 0 | overview ✓ | 3/3 렌더 | 757≤768 없음 | qa-lazyclaw-removal-768.png |
| 375×667 모바일 | 0 / 0 (8 msg) | 0 | 0 | overview ✓ | 3/3 렌더 | 364≤375 없음 | qa-lazyclaw-removal-375.png |

**한 뷰포트라도 fail 없음 → 전체 PASS.** Self-Healing Loop 불필요(0 failure).

## 비고 (정직성)

- `🦞 Ralph Loop`는 lobster 이모지를 쓰는 **별개 기능** — lazyclaw 아님. 정확히 미제거(과잉 제거 방지). 1차 정규식이 🦞로 오탐했으나 리터럴 `lazyclaw`/`lc*` 검사로 0 확인.
- `/api/lc/available` 등은 코드에서 제거됨(`ROUTES`에 `/api/lc/` 0개, in-proc assert). 서버가 미지정 `/api/*`에 `{}`+200을 주는 것은 **기존 동작**(404 아님)이며 lazyclaw 잔존 아님. 프런트는 더 이상 호출하지 않음.
- `node_modules/playwright` 미설치라 레포 관례인 `scripts/e2e-*.mjs` 대신 Playwright MCP로 검증. 수동 QA를 대체하지 않음.
- 스크린샷은 레포 루트 `.playwright-mcp/` 산출물 경로에 저장(gitignore 대상 — 커밋 안 함).
