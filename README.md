<div align="center">

# 💤 LazyClaude

<img src="./docs/logo/mascot.svg" alt="LazyClaude mascot — pixel character napping with closed eyes" width="200" height="171" />

**The lazy, elegant dashboard for everything Claude.**

_Don't memorize 50+ CLI commands. Just click._

[![한국어](https://img.shields.io/badge/🇰🇷_한국어-blue)](./README.ko.md)
[![中文](https://img.shields.io/badge/🇨🇳_中文-red)](./README.zh.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-v3.66.0-green.svg)](./CHANGELOG.md)

</div>

LazyClaude is a **local-first command center** for your `~/.claude/` directory (agents, skills, hooks, plugins, MCP, sessions, projects) plus an n8n-style workflow engine and a standalone CLI (`lazyclaw`). Everything ships behind one `python3 server.py` — Python stdlib, single-file HTML, no install step.

**No cloud. No telemetry. No package to install.**

---

## 🚀 Quick start

```bash
git clone https://github.com/cmblir/LazyClaude.git
cd LazyClaude
python3 server.py
# → http://127.0.0.1:8080
```

Requires Python 3.10+ and Anthropic's `claude` CLI on `$PATH` (optional — the dashboard works without it; only Claude-bound features need it).

```bash
# Optional environment overrides
PORT=19500 python3 server.py
LOG_LEVEL=DEBUG python3 server.py
CLAUDE_HOME=/path/to/.claude python3 server.py
```

---

## 🐚 LazyClaw CLI

A standalone Node CLI (separate from the dashboard) that exposes the same providers, sessions, skills, workflows, and rate-card surface over a fast terminal interface.

```bash
# from repo root
node src/lazyclaw/cli.mjs onboard          # one-time provider/key setup
node src/lazyclaw/cli.mjs chat             # interactive REPL
node src/lazyclaw/cli.mjs agent "summarize: $(cat file.md)"   # one-shot
node src/lazyclaw/cli.mjs run my-job ./flow.mjs --parallel-persistent
node src/lazyclaw/cli.mjs inspect my-job --critical-path ./flow.mjs
node src/lazyclaw/cli.mjs daemon --port 0  # local HTTP gateway
```

`lazyclaw help` lists every subcommand. The CLI and daemon share validators (`config-validate.mjs`, `rates-validate.mjs`) and analytics (`workflow/summary.mjs`) so output shape is bit-for-bit identical across both surfaces.

---

## 🔄 Auto-Resume with live TTY injection (v3.65.0+)

When a Claude session hits a rate-limit or selection prompt, Auto-Resume can now inject keystrokes into the **live terminal** — not just spawn a separate subprocess. macOS only:

- **Strategy A**: TTY-targeted AppleScript (iTerm, Terminal.app) — no focus shift
- **Strategy B**: System Events keystroke fallback (Warp, kitty, WezTerm, Alacritty, Ghostty, Hyper, Tabby, VS Code, Cursor) — clipboard-paste, handles arbitrary Unicode

Pass `pressChoice: "1"` (default) to dismiss `1) Continue / 2) Quit` selection prompts before injecting your prompt. Permission gate: System Events fallback requires Accessibility permission for python3 (granted once via System Settings → Privacy & Security → Accessibility).

```
POST /api/auto_resume/inject_live
{ "sessionId": "...", "prompt": "계속 시작.", "pressChoice": "1" }
```

Time-based deadlines (`durationSec` / `deadlineMs`) replace the legacy `maxAttempts` cap — pick how long, not how many tries.

---

## 📐 Architecture

```
LazyClaude/
├── server.py                  # entry — binds 127.0.0.1:8080
├── server/                    # ~25 stdlib-only Python modules
│   ├── routes.py              # single dispatch table
│   ├── workflows.py           # DAG engine (ThreadPoolExecutor)
│   ├── ai_providers.py        # provider registry (claude/openai/gemini/ollama/...)
│   ├── auto_resume.py         # rate-limit retry loop with deadlineMs
│   ├── auto_resume_inject.py  # macOS live TTY injection (v3.65)
│   └── ...
├── src/lazyclaw/              # Node CLI + daemon (separate from dashboard)
│   ├── cli.mjs                # entry
│   ├── daemon.mjs             # HTTP gateway
│   ├── workflow/              # engines: sequential, parallel, persistent
│   ├── providers/             # anthropic / openai / ollama / gemini / mock
│   ├── config-validate.mjs    # shared with daemon
│   └── rates-validate.mjs     # shared with daemon
├── dist/                      # single-file SPA (HTML + app.js + locales)
└── tests/                     # 491 pytest specs + 393 Playwright specs
```

### Data stores

| Path | Purpose | Override env |
|---|---|---|
| `~/.claude-dashboard.db` | SQLite — session index, costs, telemetry | `CLAUDE_DASHBOARD_DB` |
| `~/.claude-dashboard-workflows.json` | Workflows + runs + custom templates | `CLAUDE_DASHBOARD_WORKFLOWS` |
| `~/.claude-dashboard-ai-providers.json` | API keys, custom CLIs, fallback chain | `CLAUDE_DASHBOARD_AI_PROVIDERS` |
| `~/.claude-dashboard-auto-resume.json` | Auto-resume bindings | `CLAUDE_DASHBOARD_AUTO_RESUME` |
| `~/.claude/` | Claude Code's own state — read-only | `CLAUDE_HOME` |

All writes go through atomic `tmp + rename` (`server/utils.py::_safe_write`).

---

## 🌍 i18n

Korean is the source language. Every user-visible string passes through `t('한국어 원문')` and resolves via `dist/locales/{ko,en,zh}.json`. Run `make i18n-refresh` after adding new strings.

---

## 🛠️ Troubleshooting

**"port 8080 already in use"** — `server.py` auto-kills the prior occupant before binding. If you'd rather use a different port: `PORT=19500 python3 server.py`.

**"command not found: claude"** — install [Claude Code](https://claude.com/claude-code). The dashboard's tabs that don't depend on `claude` (workflow editor, AI providers, MCP, etc.) work without it.

**Auto-Resume live injection silently failing** — on macOS, grant Accessibility permission to `python3` in System Settings → Privacy & Security → Accessibility. The dashboard surfaces error code `1002 / -1719` with a hint when it's missing.

**Toast 📋 button breaking with broken-HTML output** — fixed in v3.66.0.

---

## 🤝 Contributing

```bash
make i18n-refresh          # required after touching any t('...') strings
python3 -m pytest tests/   # Python suite
npx playwright test        # CLI/daemon suite
node scripts/e2e-dashboard-qa.mjs   # full dashboard probe
```

Branches: `feat/*`, `fix/*`, `chore/*`. Annotated tags only (`git tag -a vX.Y.Z -m "..."`). Don't push directly to `main` from a fork without review.

See [CHANGELOG.md](./CHANGELOG.md) for the full per-release log.

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

## 📝 License

[MIT](./LICENSE) — free for personal and commercial use.

---

## 🙏 Acknowledgements

- [Anthropic Claude Code](https://claude.com/claude-code) — the CLI this dashboard is built around
- [n8n](https://n8n.io) — workflow editor inspiration
- [lazygit](https://github.com/jesseduffield/lazygit) / [lazydocker](https://github.com/jesseduffield/lazydocker) — the "lazy" spirit

<div align="center"><sub>Made with 💤 for those who'd rather click than type.</sub></div>
