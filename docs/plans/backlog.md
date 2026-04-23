# Backlog — 2026-04-23+

today-queue 로 아직 올리지 않은 후속 작업 후보.

## OMC/OMX 영감 (medium 위험, 사용자 승인 필요)

- **B6. Team 노드 프리셋** — `Plan → PRD → Exec(N병렬) → Verify → Fix` 5단계를 단일 워크플로우 템플릿으로. 기존 DAG 위에 구축 가능하지만 role catalog × tier × 병렬 단계 정책이 얽혀 복잡.
- **B7. Event Forwarder 탭** — `~/.claude/settings.json` hooks 를 UI 에서 직접 조립 (PostToolUse · OnSessionStart 등) → 외부 HTTP POST. 기존 hooks 탭 확장으로도 가능.
- **B8. Learner 탭** — 최근 세션 JSONL 분석 → 반복 패턴 추출 → skill/prompt 후보 제안. AI 판단 정확도 검증 필요.

## LazyClaude 자체 개선

- **MCP 서버 모드** — `lazyclaude` 를 MCP 서버로 등록 → Claude Code 세션에서 `/lazyclaude/<tab>` 으로 대시보드 기능 호출. OMC/OMX 의 "세션 내 통합" 경쟁력 확보.
- **Policy 프리셋** — 워크플로우 전역 정책 ("token budget 초과 시 fallback" / "verify fail 시 N번 재시도") 을 한 블록에 모음.
- **Artifacts 로컬 뷰어** — v2.21.0 설계 후 구현 대기. 4중 보안 (sandbox + CSP + postMessage + 필터).

## 품질/보안 후속

- Webhook secret 의 OMC `omc config-stop-callback` 스타일 UI — 헤더뿐 아니라 Slack/Discord body 포맷팅도 프리셋.
- aiProviders 탭의 "smart model selection" 시각화 — 최근 N 분 동안 모델별 호출 · 평균 지연 · 실제 선택률.

## 언어/번역

- README 3종에 RTK 섹션 screenshots 추가 (ko/en/zh 별 rtk.png 이미 있음 · 미참조)

## 관찰성

- Costs Timeline 에 월별/주별 뷰 추가 옵션.
- 워크플로우 run diff 에 노드별 토큰 diff 도 표시.
