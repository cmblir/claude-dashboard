# ADR: lazyclaw ↔ lazyclaude 레포 분리

- 날짜: 2026-05-18
- 상태: 진행 중
- 작성: 분리 작업 세션

## 배경

`/Users/yoo/project/LazyClaude` 한 레포 안에 두 산출물이 공존:

- **lazyclaude**: stdlib Python HTTP 서버 + 단일 HTML SPA 대시보드 (`server/`, `dist/`).
- **lazyclaw**: 독립 npm 패키지 CLI (`src/lazyclaw/`, 자체 `package.json`, bin `lazyclaw`).

v3.99.26에서 lazyclaw CLI 16개 표면을 lazyclaude 대시보드 탭으로 노출하는 브릿지
(`server/lazyclaw_proxy.py` 776줄 + `routes.py` `/api/lc/*` ~50개 + `dist/app.js` `lc*` 탭)
가 추가되어 두 산출물이 강결합됨. `.github/workflows/publish-lazyclaw.yml`이 `src/lazyclaw/package.json`
version 변경 시 npm 자동 퍼블리시.

## 결정 (사용자 승인)

1. **lazyclaw를 별도 레포 `/Users/yoo/project/lazyclaw`로 분리.** GitHub `cmblir/lazyclaw` 신규 생성.
2. **새 레포 Git 히스토리: fresh `git init`** (모노레포 혼재 커밋을 안전 분리 불가).
3. **lazyclaude에서 lazyclaw 기능 전체 삭제** — 브릿지(proxy/routes/탭) 0 흔적.

## 이동 vs 삭제 정책 (엔지니어링 판단)

"분리"의 정석 = lazyclaw 소유 자산은 새 레포로 **이동**, lazyclaude 측 브릿지는 **삭제**.

| 자산 | 처리 | 근거 |
|---|---|---|
| `src/lazyclaw/**` | 이동 → 새 레포 root | lazyclaw 본체 |
| `dist-lazyclaw/` | 이동 | lazyclaw 웹 데모 (phase3-chat만 참조) |
| `tests/phase1-6*.spec.ts` | 이동 | `src/lazyclaw/**` 를 직접 import/exec — lazyclaw 패키지 테스트 |
| lazyclaw CLI/provider import한 e2e/perf 스크립트 | 이동 | lazyclaw 단위 검증 |
| `.github/workflows/publish-lazyclaw.yml` | 이동(경로 적응) | lazyclaw npm 퍼블리시 |
| `server/lazyclaw_proxy.py`, `routes.py /api/lc/*` | 삭제 | lazyclaude 측 브릿지 |
| `dist/app.js` `lc*` 탭 16개 + 그룹 | 삭제 | lazyclaude SPA 기능 |
| `e2e-chat-* / e2e-terminal-*` (탭 구동) | 삭제 | 삭제되는 lazyclaude 기능 테스트 |
| `tests/acceptance.spec.ts` | 보존 | lazyclaw 무관 |
| `tools/translations_manual_42.py` | 보존 | 권한/이메일 토글 — lazyclaw 무관 |
| `tools/translations_manual_43/44.py` | i18n-refresh 후 고아면 제거 | nav-tile chat/terminal·connection-gate (lazyclaw UI) |

## 리스크

- `dist/app.js` 28401줄·lazyclaw 참조 121건 — 정밀 단계 편집 후 grep 0 검증 필수.
- i18n: 소스 문자열 제거 후 `make i18n-verify` 0 보장. `_42` 오삭제 금지.
- 무관 테스트(uptime/whoami/shortcuts 등)가 lazyclaw 탭을 매개로 일반 기능을 검증 →
  탭 삭제 시 깨짐. 기능 자체가 lazyclaw 종속이면 삭제, 아니면 개별 판단.
- 새 레포: phase 스펙의 `../src/lazyclaw/...` import 경로 재작성 필요.
- Obsidian MCP 미연결 세션 → 본 ADR을 레포 `Projects/lazyclaude/`에 기록.

## 검증 관문

- lazyclaude: `make i18n-verify` 0, Python import smoke, Playwright 3뷰포트(375/768/1280) 콘솔 에러 0 + lazyclaw 탭 부재.
- lazyclaw 신규 레포: `node cli.mjs --version`, 이동한 phase 스펙 통과(가능 범위), `npm publish --dry-run`.

## Identity

커밋·태그·Release 모두 사용자 본인(`cmblir` / `sodlalwl14@gmail.com`), 영문, AI attribution 없음.
lazyclaude `main` 직접 푸시 금지 → `feat/separate-lazyclaw`. 신규 lazyclaw 레포 초기 푸시는 사용자 명시 승인 범위.
