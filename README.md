# 🧭 Claude Control Center

내 `~/.claude/` 디렉토리 (에이전트 / 스킬 / 훅 / 플러그인 / MCP / 세션 / 프로젝트) 전체를 한 화면에서 보고 **편집**하고, 세션마다 품질 스코어를 매겨 Claude를 통계적으로 최적화하도록 도와주는 로컬 대시보드.

> 로컬 전용, 외부 호출 없음 — 단일 Python 스크립트 + 단일 HTML 파일.

---

## ✨ 핵심 기능

### 🎯 최적화 스코어 (0–100)
권한·훅·에이전트·스킬·플러그인·MCP·세션품질 7개 축으로 셋업을 평가하고 부족한 부분을 추천 액션으로 제시.

### 🗂 세션 히스토리 DB
`~/.claude/projects/*/*.jsonl` 을 SQLite (`~/.claude-dashboard.db`) 로 인덱싱.
- 세션별 점수 (engagement · productivity · delegation · diversity · reliability)
- 첫 요청, 도구 호출 순서, 서브에이전트 위임 타임라인, 메시지 프리뷰
- 최신 / 스코어 / 도구 / 지속시간 정렬 + 전문 검색

### 🤝 에이전트 상호작용 그래프
vis-network 기반 force-directed 그래프로 **Claude Core ↔ 서브에이전트 ↔ 도구** 관계를 시각화. 60일치 `Agent` 툴 호출을 집계.

### 📊 실시간 통계
- 최근 30일 타임라인 (평균 점수 / 도구 호출 / 오류) · Chart.js
- 도구 사용 분포 (가로 막대)
- 서브에이전트 위임 분포 (도넛)
- 프로젝트별 평균 스코어

### ✍️ 편집 가능
- **CLAUDE.md** — 마크다운 프리뷰
- **settings.json** — JSON 에디터 + 추천 프로파일 4종 원클릭 머지
- **스킬** — `~/.claude/skills/<id>/SKILL.md` 전체 편집
- **에이전트** — `~/.claude/agents/<id>.md` 전체 편집

### 🔍 탐색
훅 · 권한 · MCP 커넥터 · 플러그인 · 마켓플레이스 · 슬래시 명령어 (사용자 + 플러그인) · 프로젝트 · 실행 세션

---

## 🚀 시작하기

```bash
./start.sh
```

브라우저에서 **http://localhost:8080** 열기. 최초 부팅 시 세션 자동 인덱싱.

- macOS 기본 Python 3.9+ 만 있으면 OK (의존성 0개)
- 프론트는 Tailwind · Chart.js · vis-network · marked CDN 사용

---

## 🛡 안전성

| 동작 | 결과 |
|---|---|
| GET | 항상 `~/.claude/` 읽기만 |
| PUT `/api/settings`, `/api/claude-md`, `/api/skills/{id}`, `/api/agents/{id}` | 원자적 파일 쓰기 (`.tmp` → rename) |
| POST `/api/open-folder`, `/api/open-session` | 홈 디렉토리 내 경로만 허용, AppleScript로 터미널 활성화 |
| POST `/api/sessions/reindex` | DB만 재빌드 (~/.claude 건드리지 않음) |

서버는 `127.0.0.1`에 바인드되어 외부에서 접근 불가.

---

## 📂 구조

```
server.py         — HTTP 서버 + SQLite 인덱서 + API
dist/index.html   — 단일 파일 SPA (Vanilla JS + CDN)
~/.claude-dashboard.db   — 세션 인덱스 (자동 생성)
```

## 🔌 API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/optimization/score` | 셋업 품질 점수 + 추천 액션 |
| GET | `/api/sessions/list?q=&sort=` | DB 세션 리스트 |
| GET | `/api/sessions/detail/{id}` | 세션 상세 + 도구 타임라인 |
| GET | `/api/sessions/stats` | 집계 통계 (타임라인, 도구 분포, 탑 세션) |
| GET | `/api/agents/graph?days=60` | 에이전트 호출 그래프 |
| GET | `/api/{skills,agents,commands,hooks,plugins,connectors,projects,settings,marketplaces}` | 리스트 |
| GET | `/api/{skills,agents}/{id}` | 단일 리소스 |
| PUT | `/api/{settings,claude-md,skills/id,agents/id}` | 저장 |
| POST | `/api/sessions/reindex` | 세션 재인덱스 (`force=true` 시 전체) |
