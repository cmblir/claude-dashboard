# OpenClaw / NanoClaw / Ralph 분석 + LazyClaude 통합 기획

**작성일**: 2026-05-01
**근거**: [§1.2 정직성](../../../CLAUDE.md) 준수 — 추측 대신 실제 1차 자료(GitHub README, 공식 plugin docs, 작성자 블로그) 기준.

---

## 1. 1차 자료 요약

### OpenClaw — `github.com/openclaw/openclaw`
*Local-first 게이트웨이*. 한 프로세스에서 세션·채널·도구·이벤트를 통합 관리.

- **23+ 메시징 플랫폼**: WhatsApp, Telegram, Slack, Discord, Signal, iMessage, Matrix, Microsoft Teams, Webex, Linear, GitHub, WeChat, Email(Resend) 등.
- **Voice Wake / Talk Mode**: macOS·iOS는 wake word, Android는 continuous voice. ElevenLabs + 시스템 TTS fallback.
- **Live Canvas (A2UI)**: 에이전트가 직접 조작하는 시각 워크스페이스.
- **컴패니언 앱**: macOS 메뉴바, iOS, Android — WebSocket로 device pairing.
- **27 first-class tools** + multi-model proxy (Anthropic↔OpenAI 포맷 변환, Gemini/GPT 라우팅) + council orchestration (다중 에이전트 합의).
- **Per-session 모델 failover**, DM pairing/open 보안 모드, 워크스페이스별 스킬 관리.
- 7일 disk TTL 세션 영속화 + 재시작 후 auto-resume + per-model 가격 기반 비용 추적.

### NanoClaw — `github.com/qwibitai/nanoclaw`
*OpenClaw의 lean 후속작*. ~500 라인 TS 코어, "bespoke fork" 철학.

- **12+ 채널**: WhatsApp/Telegram/Discord/Slack/Teams/iMessage/Matrix/GoogleChat/Webex/Linear/GitHub/WeChat + email(Resend). `/add-<channel>` 스킬로 on-demand 설치.
- **컨테이너 격리**: Docker(macOS/Linux/WSL2) + 옵션으로 Docker Sandboxes micro-VM 또는 Apple Container. 명령은 컨테이너 내부에서만 실행.
- **Agent Vault** 자격증명: OneCLI 경유 — 컨테이너에 raw key 마운트 안 함.
- **per-agent 워크스페이스**: 자체 CLAUDE.md / memory / 컨테이너.
- **메모리 IPC**: 세션당 `inbound.db`/`outbound.db` 두 SQLite, **각 파일 단일 writer**. cross-mount 경합 없음.
- **스케줄러**: 60초 호스트 sweep — stale detection + due-message wake + recurrence.
- Anthropic 공식 Claude Agent SDK 기반.

### Ralph (Ralph Wiggum loop)
- 작성자: Geoffrey Huntley. Anthropic 공식 plugin: `claude-code/plugins/ralph-wiggum`.
- 핵심: **Stop hook**이 Claude의 종료를 가로채서 같은 PROMPT.md를 다시 주입. 외부 bash loop 불필요 — 한 세션 내부에서 반복.
- 상태는 **파일 + git history**로만 유지 (프롬프트는 불변). Claude가 매 iteration에서 자기 이전 변경사항을 읽고 개선.
- 완료 신호: 정확한 문자열 매치 (`<promise>DONE</promise>`).
- 안전: `--max-iterations` (필수), `/cancel-ralph` 수동 중단.
- 실증: 3개월 루프로 프로그래밍 언어 1개 완성, YC 해커톤 팀 6+ 레포를 $297로 하룻밤에.
- 철학: "deterministically bad in an undeterministic world" — 예측 가능하게 실패하는 게 예측 불가능하게 성공하는 것보다 낫다.

---

## 2. LazyClaude 현황 (cycle 1-3 완료분)

| 영역 | 보유 | 부족 |
|---|---|---|
| 멀티 모델 디스패치 | ✓ `execute_with_assignee` (claude/openai/gemini/ollama/codex) | per-binding failover (전역 fallback chain만) |
| Slack | ✓ Events API + 서명 검증 + 봇 token | DMs, file uploads, blocks 풍부함 |
| Telegram | ✓ long-poll + Bot API | 메시지 외 (sticker, voice) |
| 워크플로우 DAG | ✓ 16+ 노드, repeat, cron, webhook | Ralph-style loop pattern 없음 |
| 에이전트 보고 | ✓ Agent Bus pub/sub + ask/reply | 채널 간 라우팅 (오케스트레이터 한정) |
| 터미널 설정 | ✓ TUI (curses) | 대화형 supervisor 없음 |
| 비용 추적 | ✓ per-model pricing | 채널 단위 예산 cap 없음 |
| 격리 | ❌ — 모든 워크플로우가 호스트에서 실행 | Docker / micro-VM 옵션 |
| Voice / TTS | ❌ | OS-specific, scope 밖 |
| 컴패니언 앱 | ❌ — 웹 UI만 | scope 밖 |
| 채널 다양성 | Slack/Telegram만 | Discord/Email out/Signal/Matrix/Linear/GitHub |

---

## 3. 추천 통합 (가치 / 비용 매트릭스)

각 항목: **R**OI · **E**ffort · **F**it (얼마나 자연스럽게 기존 구조에 들어가는지) — 모두 H/M/L.

### 🟢 Tier 1 — 즉시 추천 (R:H · E:L-M · F:H)

#### **T1-1. Ralph 루프 통합** ⭐ (사용자 명시 목표)
- 워크플로우 노드 1종 + 독립 CLI(`tools/ralph_loop.py`) + 대시보드 탭
- 동작: `PROMPT.md` 입력 + `--max-iterations N` + `--completion "DONE"` → 같은 프롬프트 N번 또는 완료 마커까지 반복 실행. 매 iteration 사이 git commit + agent_bus 진행 publish + 비용 누적.
- 안전: max-iter (필수, 기본 25), per-iter 비용 cap, `/api/ralph/cancel/<id>`, "iteration N마다 git stash 백업" 옵션.
- 재사용: `execute_with_assignee` (model 선택 가능), agent_bus (라이브 SSE), orch_runs 히스토리, 코드는 ~250 LoC.
- 위험: 무한 비용 폭증 — 안전장치 3중 (max-iter + budget USD + manual cancel).

#### **T1-2. Project Ralph 추천** ⭐ (사용자 명시 목표)
- "프로젝트 탭"에서 각 프로젝트 카드에 🦞 버튼 → 자동 PROMPT.md 생성기
- 입력 자동수집: 해당 프로젝트의 `CLAUDE.md`, 최근 git log 30개, 미해결 TODO/FIXME 목록(grep), 최근 5개 세션의 미완 작업, 실패한 마지막 워크플로우 run.
- 출력: 플래너 LLM이 합성한 PROMPT.md 초안 — "이 프로젝트의 가장 가치 있는 다음 작업 N개를 Ralph 루프로 처리하세요" 템플릿 + 평가 기준 + 완료 promise 마커.
- UI: 미리보기 → 수정 → "🚀 Ralph 시작" → live SSE 패널.
- 재사용: `server/projects.py`, `server/learner.py` (TODO 추출은 이미 부분 있음), 플랜 LRU 캐시.

#### **T1-3. Discord 봇 (channels 확장 1단)**
- Slack과 동일 패턴 (`server/discord_api.py` + Events API webhook + Bot token).
- 우리는 이미 `server/notify.py`에 Discord webhook 송신만 있음 — 인입 추가만 하면 멀티에이전트 디스패치까지 자동 동작.
- 효과: 사용자 1명에게도 Discord는 무료/persistent — Slack 워크스페이스가 없어도 OS.

#### **T1-4. Email-out (SMTP) reply**
- AR에는 이미 SMTP+STARTTLS notify 있음 (`server/notify.py`). 오케스트레이터 reply sink로 등록만 하면 됨.
- "이 채널 binding은 답을 이메일로" — 비대면 long-running task용.

### 🟡 Tier 2 — 가치 큼, 작업량 중간 (R:H · E:M · F:M)

#### **T2-1. Per-binding model failover chain**
- 전역 fallback chain만 있는 걸 `binding.fallbackChain: ["claude:opus", "claude:sonnet", "openai:gpt-4.1"]`로 확장.
- 채널별로 "값비싼 모델 우선, 실패 시 cheap 모델"의 정책을 다르게 둘 수 있음. 라이트 구현: 30 LoC.

#### **T2-2. Per-channel 예산 cap (USD/day)**
- 비용 추적은 이미 있음 (`server/cost_timeline.py`). orchestrator config에 `bindings[].budgetUsdPerDay` 추가 → 초과 시 채널에 정중한 거부 메시지.
- 비용 폭주 방지의 1차 방어선.

#### **T2-3. Agent 격리 워크스페이스 (ephemeral CLAUDE.md)**
- NanoClaw의 per-agent isolated CLAUDE.md를 차용.
- `~/.claude-dashboard-agents/<binding-id>/CLAUDE.md` + `memory/` — 한 채널의 컨텍스트가 다른 채널을 오염시키지 않음.
- 우리 `server/hyper_agent.py`가 이미 비슷한 패턴 — 일반화하면 됨.

#### **T2-4. Inbound/Outbound SQLite 분리 (cross-process 안전)**
- 현재 `orch_runs` 한 테이블에 모든 게 들어감. NanoClaw 패턴: inbound(사용자→에이전트), outbound(에이전트→사용자) 분리, 각 한 명만 쓰기.
- 효과: 외부 도구(다른 셸, CLI replay)가 안전하게 인입을 inject하거나 응답을 tail.

### 🟠 Tier 3 — 흥미롭지만 큰 작업 (R:M · E:H · F:M)

#### **T3-1. Docker 샌드박스 옵션 (워크플로우 노드 단위)**
- 노드 inspector에 `runIn: host | docker:<image>` 토글.
- bash/file-write를 사용하는 노드만 컨테이너로 — 100% 격리는 아니지만 실수 폭발 반경 제한.
- 의존성 추가: docker CLI 감지(`server/cli_tools.py` 패턴 재사용). Docker 없으면 그냥 host 실행.

#### **T3-2. /add-channel 스킬 모델**
- NanoClaw의 `/add-discord` `/add-signal` 같은 점진 설치 패턴을 우리 Skills 시스템과 결합.
- 새 채널 통합을 코드 변경 없이 스킬로 추가 가능 — 마켓플레이스 친화적.

### 🔴 Tier 4 — Scope 밖 (스킵 권장)

- **T4-1. Voice Wake / TTS** — OS별 코드 + macOS Speech.framework / iOS / Android 분기. 의존성 폭발.
- **T4-2. 컴패니언 모바일 앱** — 별도 프로젝트 1개 분량.
- **T4-3. Live Canvas / A2UI** — 워크플로우 캔버스가 이미 인접 — 합치면 캔버스 ~18000 LoC HTML 더 부풀음.

---

## 4. 1차 구현 권장 묶음 (다음 자율 사이클 후보)

다음 cycle을 돌릴 때 **D1-D6** 큐로 제안:

| ID | Phase | 추정 LoC | 의존성 |
|---|---|---|---|
| D1 | Ralph 엔진 (`server/ralph.py`) — 루프 + max-iter + budget cap + cancel | ~250 | 없음 |
| D2 | Ralph 워크플로우 노드 (`workflows.py` 노드 1종 추가) | ~80 | D1 |
| D3 | Ralph CLI (`tools/ralph_loop.py`, ~200 LoC) | ~200 | D1 |
| D4 | Project Ralph 추천 (`server/ralph_recommend.py` + 프로젝트 탭 카드) | ~200 | D1, projects.py, learner.py |
| D5 | Discord 봇 (`server/discord_api.py` + Events 라우트) | ~250 | http_pool.py, orchestrator.py |
| D6 | Per-binding failover chain + 일일 예산 cap | ~120 | orchestrator.py, cost_timeline.py |

**합계 ~1100 LoC** — 한 사이클(2-3 commit)에 무리 없음. 모두 stdlib only, 하드코딩 0, 기존 최적화(plan cache, http pool, agent_bus)와 자연스럽게 결합.

---

## 5. 의도적으로 *제외*한 것

- 외부 SaaS 연결 (ElevenLabs, Resend 등) — *.dev API 키 발급 흐름이 사용자 수동 단계라 정직성 §1.2 위배 위험.
- "council orchestration"의 정확한 OpenClaw 구현 — README가 명시하지 않아 추측 금지.
- 컴패니언 앱 / Live Canvas — scope.

---

## 6. 다음 단계

1. 이 문서로 사용자 검토 (특히 Tier 1·2 우선순위 합의).
2. 합의되면 D1-D6를 `plans/today-queue.md`로 옮기고 자율모드 cycle 4 진입.
3. README의 Features 섹션도 cycle 4 commit과 함께 한 번 더 정돈 — 지금 단계에서는 v-by-v 테이블 제거만 적용 (이미 완료).
