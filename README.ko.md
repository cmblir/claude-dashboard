<div align="center">

# 💤 LazyClaude

<img src="./docs/logo/mascot.svg" alt="LazyClaude 마스코트 — 눈을 감고 낮잠 자는 픽셀 캐릭터" width="200" height="171" />

**모든 Claude 작업을, 게으르고 우아하게.**

_50+ 개 CLI 명령어 외우지 마세요. 그냥 클릭하세요._

[![English](https://img.shields.io/badge/🇺🇸_English-blue)](./README.md)
[![中文](https://img.shields.io/badge/🇨🇳_中文-red)](./README.zh.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-v3.91.0-green.svg)](./CHANGELOG.md)
[![npm](https://img.shields.io/npm/v/lazyclaw.svg?label=lazyclaw%20cli)](https://www.npmjs.com/package/lazyclaw)

</div>

LazyClaude는 **로컬 우선 커맨드 센터**입니다. `~/.claude/` 디렉토리(에이전트, 스킬, 훅, 플러그인, MCP, 세션, 프로젝트) 관리 + n8n 스타일 워크플로우 엔진 + 독립 실행 CLI(`lazyclaw`)를 한 줄 명령(`python3 server.py`)으로 띄웁니다. 파이썬 표준 라이브러리, 단일 HTML 파일, 설치 단계 없음.

**클라우드 업로드 없음. 텔레메트리 없음. 의존성 없음.**

---

## 🚀 빠른 시작

```bash
git clone https://github.com/cmblir/LazyClaude.git
cd LazyClaude
python3 server.py
# → http://127.0.0.1:19500
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

### 설치

```bash
npm install -g lazyclaw
lazyclaw version
```

요구사항: **Node 18+**. macOS / Linux / WSL 에서 동작. Windows 네이티브 PowerShell 도 대부분 동작하지만 ghost-text · ANSI 배너는 TTY 한정이라 일반 prompt 로 fallback 될 수 있어요.

<details>
<summary>소스에서 직접 (기여자용)</summary>

```bash
git clone https://github.com/cmblir/LazyClaude.git
cd LazyClaude

# 그대로 실행 (설치 없음)
node src/lazyclaw/cli.mjs <subcommand>

# 또는 bin 을 $PATH 로 심볼릭 링크
sudo ln -s "$PWD/src/lazyclaw/cli.mjs" /usr/local/bin/lazyclaw
sudo chmod +x /usr/local/bin/lazyclaw

# 또는 셸 프로파일(~/.zshrc / ~/.bashrc) 에 alias
alias lazyclaw="node $HOME/path/to/LazyClaude/src/lazyclaw/cli.mjs"
```

npm 에 게시되는 `lazyclaw` 는 [`src/lazyclaw/`](./src/lazyclaw) 의 스냅샷입니다. `main` 에 푸시된 커밋이 `src/lazyclaw/package.json#version` 을 bump 하면 `.github/workflows/publish-lazyclaw.yml` 이 자동으로 npmjs.org 에 올립니다.

</details>

### 첫 실행 — 인터랙티브 onboarding

```bash
lazyclaw onboard               # 화살표 picker — 기본값은 claude-cli (키 불필요)
lazyclaw status                # 현재 provider/model + 마스킹된 키
lazyclaw doctor                # config 와 provider 레지스트리 검증
```

picker 의 각 항목에는 인증 방식이 라벨로 표시됩니다:

| 태그 | 의미 |
|---|---|
| `[subscription]` | 로컬 `claude` CLI 의 기존 로그인 사용 (Pro / Max / Team). API 키 불필요. |
| `[no key]` | 로컬 전용 provider (`ollama`, `mock`). |
| `[api key]` | provider API 직접 호출 (`anthropic`, `openai`, `gemini`) — `sk-...` 키 필요. |

자동화 시: `lazyclaw onboard --non-interactive --provider X --model Y [--api-key Z]`. `--api-key` 는 provider 의 `requiresApiKey` 가 true 일 때만 요구되므로, 구독·로컬 provider 는 그대로 키 없이 사용됩니다.

`onboard` 는 `~/.lazyclaw/config.json` 을 작성합니다. `LAZYCLAW_CONFIG_DIR=/path/to/dir` 로 위치를 바꿀 수 있어요.

### 인터랙티브 채팅 (배너 + 슬래시 ghost-text, v3.85+)

```bash
lazyclaw chat                  # REPL 시작 — 배너 + 활성 provider/model 출력
lazyclaw chat --pick           # prompt 진입 전 화살표 picker
lazyclaw chat --session daily  # ~/.lazyclaw/sessions/daily.jsonl 에 turn 영구 저장
lazyclaw chat --skill review,style  # 지정 skill 들을 system prompt 로 합성
```

시작 시 화면 (TTY 한정):

```text
  ╭──────────────────────────────╮
  │   _                          │
  │  | |__ _ _____  _ _          │
  │  | / _` |_ / || | '_|         │
  │  |_\__,_/__\_, |_|            │
  │  LazyClaw  |__/  3.86.0      │
  ╰──────────────────────────────╯

  provider · anthropic
  model    · claude-opus-4-7
  slash    · /help · /model · /provider · /exit
  hint     · → to accept the suggested command, Tab to cycle

›
```

REPL 안에서:

| Slash | 동작 |
|---|---|
| `/help`        | 슬래시 명령 목록 |
| `/status`      | provider + model + 마스킹된 키 출력 |
| `/provider X`  | 세션 도중 active provider 교체 (대화 유지) |
| `/model X`     | 모델 교체. `provider/model` 통합 폼도 지원 |
| `/skill a,b`   | system prompt 를 지정 skill 들의 합성으로 교체 |
| `/usage`       | 메시지 수 + 글자 + 누적 토큰 (provider 가 보고할 때) |
| `/new` / `/reset` | 대화 비우고 새로 시작 |
| `/exit`        | 종료 |

Cursor 식 ghost-text 자동완성: `/` 로 시작하는 입력에서 가장 긴 매칭 슬래시 명령의 나머지가 dim grey 로 커서 뒤에 미리 보입니다. **`→`** 로 수락, **`Tab`** 으로 cycle. 스트리밍 응답 중 **Ctrl-C** 는 그 turn 만 abort (프로세스는 유지); 빈 prompt 에서 **Ctrl-C** 는 정상 종료.

### 1회성 호출 (REPL 없이)

```bash
lazyclaw agent "summarize: $(cat file.md)"
lazyclaw agent - < prompt.txt                    # stdin 에서 읽기
lazyclaw agent "..." --provider openai --model gpt-4.1
lazyclaw agent "..." --skill review              # system prompt 합성
lazyclaw agent "..." --usage                     # 토큰 수를 stderr 로 출력
lazyclaw agent "..." --cost                      # rates 가 잡혀있으면 $ 출력
```

### 프로바이더 / 세션 / 스킬

```bash
lazyclaw providers list                          # 등록된 모든 provider
lazyclaw providers info anthropic                # 단일 provider 상세
lazyclaw providers test anthropic                # 1-token 도달성 프로브

lazyclaw sessions list                           # 영구 저장된 채팅
lazyclaw sessions show daily                     # 세션 turn 덤프
lazyclaw sessions search "deploy"                # 전문 검색
lazyclaw sessions export daily > daily.md
lazyclaw sessions clear daily                    # 세션 1개 비우기

lazyclaw skills list                             # 설치된 마크다운 skill 번들
lazyclaw skills show review                      # skill 본문 출력
lazyclaw skills install ./my-skill.md            # skill 추가
lazyclaw skills remove review
```

### 워크플로우 (DAG / sequential / persistent)

```bash
# 순차, 재개 가능 (기본). 상태는 ./.workflow-state/<id>/
lazyclaw run my-job ./flow.mjs

# 토폴로지컬-레벨 DAG, 메모리만 (빠름, 재개 X)
lazyclaw run my-job ./flow.mjs --parallel --concurrency 4

# DAG + 체크포인트 + 재개
lazyclaw run my-job ./flow.mjs --parallel-persistent

# 직전에 중단된 run 재개
lazyclaw resume my-job ./flow.mjs

# 영구 상태 확인 (실행 X)
lazyclaw inspect                                 # 모든 세션 list
lazyclaw inspect my-job --summary
lazyclaw inspect my-job --critical-path ./flow.mjs
lazyclaw inspect my-job --slowest 5
```

### 로컬 HTTP 게이트웨이

```bash
lazyclaw daemon                                  # 빈 포트 바인딩 후 { port, url } 출력
lazyclaw daemon --port 19600
lazyclaw daemon --auth-token $(openssl rand -hex 16)
lazyclaw daemon --rate-limit 60 --log info       # 60 req/min/IP, JSON access log
lazyclaw daemon --once                           # 1 회 응답 후 종료
```

daemon 은 CLI 와 config / rate card 를 공유 — `lazyclaw agent` 와 daemon `POST /agent` 의 응답은 바이트 단위로 동일.

### 비용 rate card

```bash
lazyclaw rates list                              # 현재 카드 출력
lazyclaw rates set anthropic/claude-opus-4-7 \
  --in 15 --out 75 --cache-read 1.5 --cache-create 18.75
lazyclaw rates copy anthropic/claude-opus-4-7 \
  anthropic/claude-opus-4-6                       # 카드 복제
lazyclaw rates delete openai/gpt-3.5-turbo
lazyclaw rates validate                          # 스키마 + 정합성 검사
```

`/usage` 와 `--cost` 는 이 카드를 사용해 USD 합계를 로컬에서 계산 — provider 추가 호출 없음.

### Config + 번들

```bash
lazyclaw config path                             # → ~/.lazyclaw/config.json
lazyclaw config get provider
lazyclaw config set provider openai
lazyclaw config list
lazyclaw config edit                             # $EDITOR 로 열기
lazyclaw config validate

lazyclaw export > backup.json                    # config + skills (+ 옵션 sessions)
lazyclaw import --from backup.json
```

### 셸 자동완성

```bash
lazyclaw completion bash >> ~/.bashrc
lazyclaw completion zsh  >> ~/.zshrc
```

### 파일 위치

| 경로 | 용도 |
|---|---|
| `~/.lazyclaw/config.json` | provider, model, api-key, skills, rates |
| `~/.lazyclaw/sessions/*.jsonl` | 영구 저장된 채팅 세션 |
| `~/.lazyclaw/skills/*.md` | 설치된 skill 번들 |
| `./.workflow-state/<id>/` | 세션별 워크플로우 체크포인트 (cwd 기준) |

`LAZYCLAW_CONFIG_DIR=/elsewhere` 로 앞 셋의 위치를, `LAZYCLAW_WORKFLOW_STATE_DIR=...` 로 마지막 위치를 옮길 수 있어요.

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
├── server.py                  # 엔트리 — 127.0.0.1:19500 바인딩 (PORT env 로 오버라이드)
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

**"port 19500 already in use"** — `server.py` 가 `$PORT`의 기존 점유자를 자동 kill 합니다. 다른 포트로 강제: `PORT=8080 python3 server.py`. v3.99에서 기본이 `8080 → 19500`으로 바뀌었어요 — 8080은 매우 흔한 로컬 dev 포트라(Tomcat / http-server / 수많은 튜토리얼 기본값) 같은 origin에 다른 PWA가 설치돼 있으면 대시보드의 "앱으로 열기" 버튼이 그 PWA로 hijack 되는 문제가 있었습니다. 기존 스크립트 / 바로가기가 8080 가정이면 `PORT=8080` 로 유지 가능.

**"앱으로 열기" 가 엉뚱한 앱을 띄우는 경우** — Chrome PWA는 origin (`http://127.0.0.1:<port>`) 단위로 등록되기 때문에, 같은 포트에 과거에 설치한 다른 PWA가 lauch를 가로챕니다. `chrome://apps` 에서 LazyClaude 외에 그 포트를 가리키는 항목 제거 → `chrome://settings/content/all` 에서 포트 검색 → "Delete data" 로 install state 까지 정리하세요. v3.99의 manifest는 명시적인 `id`를 갖고 있어 같은 origin에 다른 PWA가 있어도 Chrome 이 별개의 앱으로 인식합니다.

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
