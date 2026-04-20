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
cp env.example .env       # (선택) 환경 변수 커스터마이징
./start.sh
```

브라우저에서 **http://localhost:8080** 열기. 최초 부팅 시 세션 자동 인덱싱.

- macOS 기본 Python 3.9+ 만 있으면 OK (의존성 0개)
- 프론트는 Tailwind · Chart.js · vis-network · marked CDN 사용

### 환경 변수 (모두 선택)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `HOST` | `127.0.0.1` | 바인드 주소 |
| `PORT` | `8080` | 포트 |
| `CLAUDE_HOME` | `~/.claude` | Claude Code CLI 설정 디렉토리 |
| `CLAUDE_JSON` | `~/.claude.json` | Claude Code 전역 설정 |
| `CLAUDE_DESKTOP_CONFIG` | `~/Library/Application Support/Claude/claude_desktop_config.json` | Desktop 앱 MCP (macOS 기준) |
| `CLAUDE_DASHBOARD_DB` | `~/.claude-dashboard.db` | 세션 SQLite |
| `CLAUDE_DASHBOARD_TRANSLATIONS` | `~/.claude-dashboard-translations.json` | AI 번역 캐시 |
| `CLAUDE_DASHBOARD_CONFIG` | `~/.claude-dashboard-config.json` | 사용자 플랜 등 |
| `CLAUDE_DASHBOARD_MEMORY_DIR` | (자동 산출) | 프로젝트 메모리 디렉토리 |

`.env` 는 자동 로드되며 `.gitignore` 로 제외됩니다.

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
server.py              — 얇은 엔트리 (~30줄): .env 로드 + DB 초기화 + HTTP 서버 시작
server/                — 기능별 모듈 (모두 stdlib only)
  ├ config.py          — 경로 상수 · 환경 변수
  ├ utils.py           — 파일 I/O · frontmatter 파서 · 시간 포맷
  ├ logger.py          — 표준 logging (LOG_LEVEL 환경변수)
  ├ db.py              — SQLite 커넥션 + 스키마
  ├ device.py          — macOS 호스트 정보 (cached)
  ├ claude_md.py       — CLAUDE.md · settings.json 편집
  ├ skills.py          — 스킬 + 플러그인 스킬
  ├ agents.py          — 에이전트 (전역 + 플러그인 + 빌트인)
  ├ commands.py        — 슬래시 명령어 + 카테고리 + 번역 배치
  ├ hooks.py           — 훅 설정 (사용자 + 플러그인)
  ├ mcp.py             — MCP 카탈로그 · 커넥터 · `claude mcp list` 캐시
  ├ plugins.py         — 플러그인 · 마켓플레이스
  ├ sessions.py        — JSONL 인덱서 · 스코어링 · 타임라인 · 에이전트 그래프
  ├ projects.py        — 프로젝트 상세 · 프로젝트별 에이전트 · 서브에이전트 모델
  ├ briefing.py        — 홈 개요 집계
  ├ features.py        — AI 평가 · 최적화 스코어 · 추천
  ├ system.py          — 사용량 · 메트릭 · 태스크 · 출력 스타일 등 정보 API
  ├ auth.py            — Claude CLI 인증 연동
  ├ actions.py         — 터미널 활성화 · 폴더 열기 · 챗
  ├ translations.py    — 번역 캐시 · 대시보드 설정
  └ routes.py          — Handler + ROUTES_GET/POST/PUT dict
dist/index.html        — 단일 파일 SPA (Vanilla JS + CDN)
~/.claude-dashboard.db — 세션 인덱스 (자동 생성)
```

## 🌐 다국어 (i18n)

한국어 · 영어 · 중국어 3개 언어 지원. 번역은 **런타임 fetch** 방식.

```
dist/locales/ko.json    # 한국어 원문 → 한국어 (identity)
dist/locales/en.json    # 한국어 원문 → 영어 번역
dist/locales/zh.json    # 한국어 원문 → 중국어 번역
```

- 페이지 로드 시 `_curLang` 감지 (`?lang=en|zh` 쿼리 또는 `cc-lang` 쿠키)
- `/api/locales/{lang}.json` 으로 사전 fetch → `_translateDOM` 가 정적 DOM 교체
- JS 에서는 `t('한국어 원문')` 헬퍼로 런타임 번역
- 누락 시 한국어 원문 fallback + 콘솔 경고

### 번역 추가 / 수정

```bash
python3 tools/extract_ko_strings.py     # dist/index.html 에서 한국어 phrase 전수 추출 → translation-audit.json
# 누락된 번역을 tools/translations_manual.py 에 추가 (MANUAL_EN / MANUAL_ZH)
python3 tools/build_locales.py          # dist/locales/{ko,en,zh}.json 재생성
node scripts/verify-translations.js     # 0 건 누락 검증 (실패 시 exit 1)
```

검수가 필요한 항목은 `translation-review.md` 에 자동 기록되며,
`tools/translations_manual.py::NEEDS_REVIEW` 에서 관리.

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
