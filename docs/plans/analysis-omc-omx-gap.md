# OMC / OMX vs LazyClaude — Gap Analysis

생성: 2026-04-23
레퍼런스: 
- `Yeachan-Heo/oh-my-claudecode` (OMC, TS, 30.8k ★) — Claude Code 용 팀 오케스트레이션
- `Yeachan-Heo/oh-my-codex` (OMX, TS, 25.2k ★) — Codex 용 동일 계열
- 현재 상태: LazyClaude v2.24.1 (53 탭, 192 API 라우트, 3,291 i18n)

## 핵심 차별화 축

| 축 | OMC | OMX | LazyClaude (v2.24.1) |
|---|---|---|---|
| **형태** | 세션 내 슬래시 명령 + `omc` CLI | 세션 내 `$` 키워드 + `omx` CLI | 로컬 웹 대시보드 (단일 HTML SPA) |
| **런타임** | Node.js (npm 설치) | Node.js (npm 설치) | Python stdlib only |
| **주력** | 워크플로우 · 팀 · 자동화 | 워크플로우 · 팀 · 지식 | 관찰성 · 설정 관리 · API playground |
| **UI** | CLI + status bar HUD | CLI + `omx hud --watch` | **52+ 탭 GUI** |

---

## LazyClaude 가 이미 우위인 영역

- **시각적 설정 관리 전체** — agents / skills / hooks / plugins / MCP / commands / statusline / permissions / settings / claudemd / env / model config. OMC·OMX 는 CLI 만 제공.
- **n8n 스타일 DAG 워크플로우 엔진** — 16 노드 타입 × 5 빌트인 템플릿 × 조건부 11종 × webhook · cron · repeat.
- **Claude API 플레이그라운드 11 탭** — prompt cache / thinking / tool-use / batch / files / vision / model bench / server tools / citations / agent SDK 스캐폴드 / embedding. OMC·OMX 에는 없음.
- **통합 비용 타임라인** — 모든 playground + workflow run 비용을 소스별/모델별/일별 스택 차트로. OMC·OMX 는 비용 추적 개념 없음.
- **공식 문서 허브** — docs.anthropic.com 33 페이지 색인 + 관련 탭 링크.
- **Ollama 모델 허브** — 23 모델 카탈로그 + 원클릭 pull.
- **다국어** — ko/en/zh 3언어 × 3,291 키.
- **관찰성** — Usage / Metrics / Memory / Tasks / Backups / Bash history / Telemetry / Homunculus / System.

LazyClaude 는 **대시보드/플랫폼 레이어**, OMC/OMX 는 **세션 내 워크플로우 레이어**. 직접 대체 관계가 아니라 서로 다른 위치.

---

## OMC/OMX 에 있고 LazyClaude 에 없는 것 — 흡수 후보 (우선순위 높 → 낮)

### 🔴 HIGH — 핵심 차별화 가치 큼

1. **멀티 에이전트 팀 오케스트레이션 (OMC `omc team 3:executor` / OMX `$team`)**  
   현재 워크플로우는 단일 session/subagent 노드 DAG. 팀 개념 없음.  
   → LazyClaude 에 **Team 노드** 추가: `Plan → PRD → Exec(N병렬) → Verify → Fix` 파이프라인을 프리셋 템플릿으로. 기존 DAG 위에 구축 가능.

2. **실행 모드 프리셋 — autopilot / ralph / ultrawork / deep-interview (OMC)**  
   한 번의 지시로 자동 verify-fix 루프를 도는 모드. LazyClaude 의 Repeat + feedback node 는 있지만 "persistent until completion" 정책이 명시적이지 않음.  
   → 워크플로우 템플릿에 **4종 실행 모드 시드** 추가. `ralph-loop` = verify fail 시 자동 fix 반복, `autopilot` = 사용자 확인 없이 끝까지, `ultrawork` = 최대 병렬, `deep-interview` = 요구사항 명확화 단계.

3. **스마트 모델 라우팅 (OMC)** — Haiku/Opus 를 복잡도 기반으로 자동 선택, 30-50% 토큰 절감.  
   → 워크플로우 session 노드에 `modelHint: auto | fast | deep` 필드 → 내부적으로 프롬프트 길이 · 키워드 · 이전 노드 출력 기반 Haiku/Sonnet/Opus 선택.

4. **Session 분석 — JSONL replay + JSON 요약 (OMC `.omc/sessions/`)**  
   현재 sessions 탭은 Claude Code JSONL 을 읽지만 per-run diff/replay UI 는 워크플로우 run 에만 한정.  
   → **Session Replay Lab** 탭 — JSONL 타임라인 스크러버 + 툴 호출 하이라이트 + 토큰 누적 차트.

### 🟡 MEDIUM — 있으면 유저 경험 크게 향상

5. **알림 라우팅 (OMC `omc config-stop-callback` → Telegram/Discord/Slack)**  
   워크플로우 완료/실패를 외부 채널로. LazyClaude 는 브라우저 토스트 + 사용량 알림 뿐.  
   → 워크플로우 run 종료 hook + Slack/Discord/Telegram webhook 프리셋. 기존 workflow webhook trigger 와 대칭.

6. **프롬프트 키워드 트리거 (OMC `ultrathink` / `deepsearch`)**  
   세션 내 특정 키워드로 특별 동작 유발. LazyClaude 의 Prompt Library 는 저장·복제만.  
   → Prompt Library 에 **키워드 트리거** 필드 추가 → 프롬프트에 해당 키워드 포함 시 자동 적용할 시스템 프롬프트 추가.

7. **OpenClaw Gateway 식 외부 연동 (OMC)**  
   세션 이벤트 (시작·종료·키워드·tool use) 를 외부 webhook 으로 포워딩.  
   → LazyClaude 에 **Event Forwarder** 탭 (system 그룹) — claude-code 의 hooks 이벤트 일부를 HTTP POST 로 포워드.

8. **Portable Skills + Learner (OMC `/learner`)**  
   세션에서 쓸모있는 패턴을 자동 추출해 재사용 가능한 skill 로 저장.  
   → 기존 skills 탭 + Prompt Library 연계, 대시보드 내 **Learner** 탭: 최근 세션의 반복 패턴 ai 추천 → skill 자동 생성.

### 🟢 LOW — 기호 수준, 차별화 기여 작음

9. **Status bar HUD (OMC `omc hud` / OMX `omx hud --watch`)**  
   터미널 상태 바에 실시간 정보. 이미 LazyClaude 는 브라우저 대시보드 자체가 HUD 역할.  
   → 제외 (중복).

10. **Wiki 시스템 (OMX `.omx/wiki`)**  
    세션 내 지식 베이스. LazyClaude 의 Claude Docs Hub + Prompt Library 로 이미 커버됨.  
    → 제외 (중복).

11. **`omx doctor` 진단** (OMX)  
    설치 무결성 검증. LazyClaude 의 aiEval + system 탭이 유사 기능.  
    → 제외.

---

## LazyClaude 가 개선해야 할 최적화 포인트 (OMC/OMX 관찰로부터)

- **세션 내 통합 부재** — OMC/OMX 는 Claude Code 세션 안에서 슬래시 명령으로 호출. LazyClaude 는 브라우저 전환 필요. → 해결: **MCP 서버 모드** 추가 검토 — `lazyclaude` MCP 서버로 등록하면 세션 내에서 `/lazyclaude/...` 로 주요 기능 호출.
- **실행 정책 언어 부족** — "verify fail 시 몇 번 재시도" / "token budget 초과 시 fallback" 같은 정책이 워크플로우 노드 단위에 분산. → 워크플로우 전체 **Policy 프리셋** 도입.
- **텔레메트리 외부 공유 없음** — 현재 모든 데이터는 local. OMC 는 Slack 알림 등. → Finding 5 와 연결.

---

## 자율모드 적용 가능 작업

아래 중 **위험도 low** 인 작업만 자율모드로 처리. high 는 사용자 승인.

| # | 작업 | 출처 | 위험도 | 예상 규모 |
|---|---|---|---|---|
| B1 | 실행 모드 프리셋 4종 빌트인 템플릿 추가 | HIGH #2 | low | 중 |
| B2 | Prompt Library 키워드 트리거 필드 | MED #6 | low | 소 |
| B3 | Workflow 완료시 Slack/Discord/Telegram webhook 알림 | MED #5 | low | 중 |
| B4 | 워크플로우 session 노드 `modelHint` → 자동 라우팅 | HIGH #3 | low | 중 |
| B5 | Session Replay Lab 탭 (JSONL 타임라인 뷰어) | HIGH #4 | low | 중 |
| B6 | Team 노드 프리셋 (Plan→PRD→Exec→Verify→Fix) | HIGH #1 | medium | 대 |
| B7 | Event Forwarder 탭 (Claude Code hook → HTTP POST) | MED #7 | medium | 중 |
| B8 | Learner 탭 (세션 패턴 추출 → skill 제안) | MED #8 | medium | 대 |

자율모드 적합 범위: **B1 ~ B5** (low, 독립 기능, 되돌리기 쉬움).  
사용자 확인 필요: **B6, B7, B8** (new UI 표면이 크고 ai 판단 여지 있음).
