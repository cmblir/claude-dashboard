<div align="center">

# 💤 LazyClaude

<img src="./docs/logo/mascot.svg" alt="LazyClaude 마스코트 — 눈을 감고 낮잠 자는 픽셀 캐릭터" width="200" height="171" />

**모든 Claude 작업을, 게으르고 우아하게.**

_50+ 개 CLI 명령어 외우지 마세요. 그냥 클릭하세요._

[![English](https://img.shields.io/badge/🇺🇸_English-blue)](./README.md)
[![中文](https://img.shields.io/badge/🇨🇳_中文-red)](./README.zh.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-v3.66.0-green.svg)](./CHANGELOG.md)

</div>

LazyClaude는 **로컬 우선 커맨드 센터**입니다. `~/.claude/` 디렉토리(에이전트, 스킬, 훅, 플러그인, MCP, 세션, 프로젝트) 관리 + n8n 스타일 워크플로우 엔진 + 독립 실행 CLI(`lazyclaw`)를 한 줄 명령(`python3 server.py`)으로 띄웁니다. 파이썬 표준 라이브러리, 단일 HTML 파일, 설치 단계 없음.

**클라우드 업로드 없음. 텔레메트리 없음. 의존성 없음.**

---

## 🚀 빠른 시작

```bash
git clone https://github.com/cmblir/LazyClaude.git
cd LazyClaude
python3 server.py
# → http://127.0.0.1:8080
```

Python 3.10+ 와 Anthropic `claude` CLI(선택사항 — Claude 연동 기능에만 필요)가 필요합니다.

```bash
# 환경변수 오버라이드 (옵션)
PORT=19500 python3 server.py
LOG_LEVEL=DEBUG python3 server.py
CLAUDE_HOME=/path/to/.claude python3 server.py
```

---

## 🐚 LazyClaw CLI

대시보드와는 별개의 독립 Node CLI. 같은 프로바이더 / 세션 / 스킬 / 워크플로우 / 요금표를 빠른 터미널 인터페이스로 노출합니다.

```bash
# 저장소 루트에서
node src/lazyclaw/cli.mjs onboard          # 최초 1회 프로바이더/키 설정
node src/lazyclaw/cli.mjs chat             # 인터랙티브 REPL
node src/lazyclaw/cli.mjs agent "summarize: $(cat file.md)"   # 1회성
node src/lazyclaw/cli.mjs run my-job ./flow.mjs --parallel-persistent
node src/lazyclaw/cli.mjs inspect my-job --critical-path ./flow.mjs
node src/lazyclaw/cli.mjs daemon --port 0  # 로컬 HTTP 게이트웨이
```

`lazyclaw help` 로 모든 서브커맨드 확인. CLI 와 daemon 은 검증기(`config-validate.mjs`, `rates-validate.mjs`)와 분석기(`workflow/summary.mjs`)를 공유 — 두 surface 의 출력이 비트 단위로 동일.

---

## 🔄 Auto-Resume + 라이브 TTY 주입 (v3.65.0+)

Claude 세션이 rate-limit 또는 선택 prompt 에 막혔을 때, Auto-Resume 이 **별도 subprocess** 가 아닌 **라이브 터미널** 에 직접 키 입력 가능. macOS 한정:

- **전략 A**: TTY 매칭 AppleScript (iTerm, Terminal.app) — 포커스 이동 없음
- **전략 B**: System Events 키 입력 fallback (Warp / kitty / WezTerm / Alacritty / Ghostty / Hyper / Tabby / VS Code / Cursor) — 클립보드 paste 로 Unicode 안전

`pressChoice: "1"` (기본) 로 `1) Continue / 2) Quit` 선택지 자동 dismiss 후 prompt 주입. System Events 경로는 python3 의 Accessibility 권한 필요 (시스템 설정 → 개인정보보호 및 보안 → 손쉬운 사용에서 1회 허용).

```
POST /api/auto_resume/inject_live
{ "sessionId": "...", "prompt": "계속 시작.", "pressChoice": "1" }
```

시간 기반 마감(`durationSec` / `deadlineMs`)이 레거시 `maxAttempts` 캡을 대체 — 시도 횟수가 아니라 "언제까지" 를 지정.

---

## 📐 아키텍처

```
LazyClaude/
├── server.py                  # 엔트리 — 127.0.0.1:8080 바인딩
├── server/                    # ~25 stdlib 모듈
│   ├── routes.py              # 단일 dispatch 테이블
│   ├── workflows.py           # DAG 엔진 (ThreadPoolExecutor)
│   ├── ai_providers.py        # 프로바이더 레지스트리
│   ├── auto_resume.py         # rate-limit 재시도 + deadlineMs
│   ├── auto_resume_inject.py  # macOS 라이브 TTY 주입 (v3.65)
│   └── ...
├── src/lazyclaw/              # Node CLI + daemon (대시보드와 별개)
│   ├── cli.mjs                # 엔트리
│   ├── daemon.mjs             # HTTP 게이트웨이
│   ├── workflow/              # sequential / parallel / persistent 엔진
│   ├── providers/             # anthropic / openai / ollama / gemini / mock
│   ├── config-validate.mjs    # daemon 과 공유
│   └── rates-validate.mjs     # daemon 과 공유
├── dist/                      # 단일 SPA (HTML + app.js + locales)
└── tests/                     # 491 pytest + 393 Playwright
```

### 데이터 저장소

| 경로 | 용도 | 환경변수 |
|---|---|---|
| `~/.claude-dashboard.db` | SQLite — 세션 인덱스, 비용, 텔레메트리 | `CLAUDE_DASHBOARD_DB` |
| `~/.claude-dashboard-workflows.json` | 워크플로우 + 실행 + 커스텀 템플릿 | `CLAUDE_DASHBOARD_WORKFLOWS` |
| `~/.claude-dashboard-ai-providers.json` | API 키, 커스텀 CLI, fallback 체인 | `CLAUDE_DASHBOARD_AI_PROVIDERS` |
| `~/.claude-dashboard-auto-resume.json` | Auto-Resume 바인딩 | `CLAUDE_DASHBOARD_AUTO_RESUME` |
| `~/.claude/` | Claude Code 자체 상태 — 읽기만 | `CLAUDE_HOME` |

모든 쓰기는 atomic `tmp + rename`(`server/utils.py::_safe_write`).

---

## 🌍 다국어

한국어가 원본. 모든 사용자 노출 문자열은 `t('한국어 원문')` 으로 감싸고 `dist/locales/{ko,en,zh}.json` 에서 해석. 새 문자열 추가 후 `make i18n-refresh`.

---

## 🛠️ 트러블슈팅

**"port 8080 already in use"** — `server.py` 가 기존 점유자를 자동 kill 합니다. 다른 포트가 좋다면: `PORT=19500 python3 server.py`.

**"command not found: claude"** — [Claude Code](https://claude.com/claude-code) 설치. claude 의존하지 않는 탭(워크플로우 에디터, AI 프로바이더, MCP 등)은 그대로 동작.

**Auto-Resume 라이브 주입 무반응** — macOS 시스템 설정 → 개인정보보호 및 보안 → 손쉬운 사용에서 `python3` 허용. 권한 누락 시 에러 코드 `1002 / -1719` 와 안내 메시지가 표시됨.

**토스트 📋 버튼이 깨진 HTML 출력** — v3.66.0 에서 수정.

---

## 🤝 기여하기

```bash
make i18n-refresh          # t('...') 문자열 추가/변경 후 필수
python3 -m pytest tests/   # Python 스위트
npx playwright test        # CLI/daemon 스위트
node scripts/e2e-dashboard-qa.mjs   # 전체 대시보드 probe
```

브랜치: `feat/*`, `fix/*`, `chore/*`. 어노테이트 태그만 (`git tag -a vX.Y.Z -m "..."`). 포크에서 `main` 으로 직접 push 금지 (리뷰 후).

전체 릴리스 로그는 [CHANGELOG.md](./CHANGELOG.md).

---

## Star History

<a href="https://www.star-history.com/?repos=cmblir/lazyclaude&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=cmblir/lazyclaude&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=cmblir/lazyclaude&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=cmblir/lazyclaude&type=date&legend=top-left" />
 </picture>
</a>

---

## 📝 라이선스

[MIT](./LICENSE) — 개인/상업적 사용 자유.

---

## 🙏 감사의 말

- [Anthropic Claude Code](https://claude.com/claude-code) — 이 대시보드의 기반이 되는 CLI
- [n8n](https://n8n.io) — 워크플로우 에디터의 영감
- [lazygit](https://github.com/jesseduffield/lazygit) / [lazydocker](https://github.com/jesseduffield/lazydocker) — 프로젝트 이름의 영감

<div align="center"><sub>타이핑보다 클릭이 좋은 사람들을 위해, 💤 로 만들었습니다.</sub></div>
