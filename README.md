<div align="center">

# 💤 LazyClaude

<img src="./docs/logo/mascot.svg" alt="LazyClaude mascot — pixel character napping with closed eyes" width="200" height="171" />

**The lazy, elegant dashboard for everything Claude.**

_Don't memorize 50+ CLI commands. Just click._

[![한국어](https://img.shields.io/badge/🇰🇷_한국어-blue)](./README.ko.md)
[![中文](https://img.shields.io/badge/🇨🇳_中文-red)](./README.zh.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-v2.36.3-green.svg)](./CHANGELOG.md)
[![Zero Dependencies](https://img.shields.io/badge/deps-stdlib_only-brightgreen.svg)](#-architecture)

</div>

LazyClaude is a **local-first command center** that manages your entire `~/.claude/` directory (agents, skills, hooks, plugins, MCP, sessions, projects) and ships a powerful **n8n-style workflow engine** with multi-AI provider orchestration — all behind a single `python3 server.py`.

**No cloud. No telemetry. No package to install.** Just Python stdlib and one HTML file.

<sub>Inspired by `lazygit` / `lazydocker` — but for your Claude stack.</sub>

### What's new

| ver | highlight |
|---|---|
| **v2.40.3** | 🏷️ **Hook names** — plugin hooks.json keeps `id` / `name` at the group level (e.g. `pre:bash:dispatcher`); the dashboard now propagates them onto each sub-hook entry and surfaces them as the card's primary title in mono. Search by id works instantly (filter `pre:bash:dispatcher` → 1 card). |
| **v2.40.2** | 🚨 **Hooks tab emergency UX** — search · scope/event chips · "risky only" filter · 🚨 chip on every PreToolUse + Edit/Write/Bash card · one-click "Bulk-disable risky hooks" that walks both user `settings.json` and every plugin `hooks.json`. Designed for the case where 100+ plugin hooks make finding the one blocking your work impossible. |
| **v2.40.1** | 🚀 **Performance hotfix** — `dist/index.html` 1.12 MB → 270 KB on the wire (server-side gzip + mtime cache), Chart.js / vis-network / marked deferred so first paint isn't blocked by ~600 KB of CDN script parsing, in-flight GET dedupe halves concurrent fetches, and sidebar re-renders coalesce into the next animation frame. No behaviour changes. |
| **v2.40.0** | ⚡ **Hyper Agent → project-scoped sub-agents** + 🧭 **Sidebar discovery** (Favorites + Recent + `/`). Hyper toggles now apply to `<cwd>/.claude/agents/<name>.md`, with composite-key namespacing so a global and a project agent of the same name keep independent metas, objectives, and history. Sidebar adds a sticky ★ Favorites block (per-item toggle), 🕒 Recent MRU (auto-surfaced from `go()` calls, capped via prefs), and `/` keystroke to open the existing Cmd-K spotlight — no category restructure, just shorter paths. |
| **v2.39.0** | ⚡ **Hyper Agent** — sub-agents that self-refine over time. Per-agent toggle on every writeable global agent card. Set an objective + refine targets (systemPrompt / tools / description), pick a trigger (manual / interval / after_session / any), and a meta-LLM (Opus default) proposes surgical edits — applied atomically with a `.bak.md` backup so every iteration is one-click reversible. Budget cap, dry-run preview, expandable diff viewer, history timeline. |
| **v2.38.0** | ⚡ **Quick Settings** — one keyboard-accessible drawer (`⌘,` / `Ctrl+,`) for every dashboard parameter. 33 keys across UI · AI · Behavior · Workflow (effort, temperature, accent color, density, font size, reduced motion, telemetry refresh, autoResume, mascot, …). Schema-driven controls (toggle / segmented / select / range / text), strict server-side validation, atomic JSON persistence at `~/.claude-dashboard-prefs.json`. |
| **v2.37.0** | 🔄 **Auto-Resume** — inject a self-healing retry loop into a live Claude session. Background worker classifies the exit reason (rate-limit / context-full / auth-expired / unknown), parses precise reset times, runs `claude --resume <id>` with exponential backoff, snapshot-hash stall detection, and per-project Stop+SessionStart hooks for context preservation. UI panel in session detail; 🔄 AR badge in session list. |
| **v2.36.3** | 🔄 **Server-restart auto-banner** — dashboard polls `/api/version` every 60s and prompts a one-click reload when `serverStartedAt` changes (no more "I deployed but the user is on a stale build"). |
| **v2.36.1** | 🩹 **Run Center ECC discovery hotfix + OMC/OMX guide cards** — `_ecc_roots()` reads `installed_plugins.json` and recognises both `ecc@ecc` and `everything-claude-code@everything-claude-code` ids. Guide & Tools gains OMC and OMX cards explaining LazyClaude-absorbed vs CLI-only features. |
| **v2.36.0** | 🎯 **Run Center** — new tab unifying ECC's 181 skills + 79 slash commands + OMC's 4 modes + OMX's 4 commands into one searchable, runnable catalog. **Workflow Quick Actions** — 4 OMC modes (Autopilot / Ralph / Ultrawork / Deep Interview) launchable from the Workflows tab header. **Commands tab Run buttons** — every slash command card gets a ▶ button and an ECC chip. |
| **v2.35.0** | 📦 **Install as a real app** — PWA (Add to Home Screen / install icon, cross-platform) **and** a 72 KB macOS `.app` bundle (`make install-mac` → Spotlight + Dock + auto server lifecycle). |
| **v2.34.0** | 🧑‍✈️ **Crew Wizard** — Zapier-style 4-step form scaffolds Planner + Personas + Slack approval + Obsidian log in one click. New `slack_approval` (Slack Web API admin gate) and `obsidian_log` workflow nodes. |
| **v2.33.2** | 🔌 ECC plugin **full auto-install** via `claude plugin install` — one click from Guide & Tools |
| **v2.33.1** | 🧰 Guide toolkit manager (ECC + CCB install/remove) · flyout viewport fix · first-visit-only login gate |
| **v2.33.0** | 🎨 Artifacts Viewer — 4-layer safe preview (sandbox + CSP + postMessage + static filter) |
| **v2.32.0** | 🤝 MCP server mode — call LazyClaude directly from Claude Code sessions |
| **v2.31.0** | 🛡 Security Scan tab — static heuristics for secrets / risky hooks / over-privileged perms |
| **v2.30.0** | 🎓 Learner — repeated tool-sequence detection from recent session JSONLs |
| **v2.23.0** | 🛡 Webhook `X-Webhook-Secret` auth + output path whitelist (`~/Downloads` · `~/Documents` · `~/Desktop`) |
| **v2.22.1** | 📸 12 real screenshots auto-generated by Playwright script |
| **v2.22.0** | 🛡 HTTP-node SSRF guard (scheme/host/prefix + DNS rebinding defense) |
| **v2.20.0** | 💸 Unified **Costs Timeline** across every playground + workflow run |
| **v2.19.0** | 📜 Workflow **run diff / rerun** — compare two runs node-by-node |
| **v2.3 ~ v2.9** | 🧊🧠🛠️📦📎👁️🏁 Seven Claude API playground tabs (prompt cache · thinking · tool-use · batch · files · vision · model bench) |

---

## 🎬 What it looks like

```
┌────────────────────────────────────────────────────────────────┐
│  💤  LazyClaude                                     v2.36.3 🇺🇸│
├────────┬───────────────────────────────────────────────────────┤
│ 🆕 New │   🔀 Workflows                                         │
│ 🏠 Main│   ┌──────┐      ┌──────┐      ┌──────┐                │
│ 🛠 Work│   │🚀start│─────▶│🗂 Claude│─┬──▶│📤 out│              │
│ ⚙ Config│  └──────┘      └──────┘   │  └──────┘                │
│ 🎛 Adv │                  ┌──────┐   │                         │
│ 📈 Sys │                  │🗂 GPT │──┤                         │
│        │                  └──────┘   │                         │
│ 💬 🐙  │                  ┌──────┐   │                         │
│        │                  │🗂 Gemini│┘                         │
│        │                  └──────┘                              │
└────────┴───────────────────────────────────────────────────────┘
```

54 tabs across 6 groups · 18 workflow node types · 8 AI providers · 5 themes · 3 languages · **Run Center catalog with 268 entries (181 ECC skills + 79 ECC commands + 4 OMC modes + 4 OMX commands)**.

### 📸 Screenshots

**Overview & Workflow Editor**

| Overview (optimization score + briefing) | Workflow DAG Editor (n8n-style) |
|---|---|
| ![Overview](./docs/screenshots/en/overview.png) | ![Workflows](./docs/screenshots/en/workflows.png) |

**Multi-AI & Unified Cost**

| AI Providers (Claude/GPT/Gemini/Ollama/Codex) | Costs Timeline (all playgrounds + workflows) |
|---|---|
| ![AI Providers](./docs/screenshots/en/aiProviders.png) | ![Costs Timeline](./docs/screenshots/en/costsTimeline.png) |

**Claude API Playgrounds**

| 🧊 Prompt Cache Lab | 🧠 Extended Thinking Lab |
|---|---|
| ![Prompt Cache](./docs/screenshots/en/promptCache.png) | ![Thinking Lab](./docs/screenshots/en/thinkingLab.png) |
| 🛠️ Tool Use Playground | 🏁 Model Benchmark |
| ![Tool Use](./docs/screenshots/en/toolUseLab.png) | ![Model Bench](./docs/screenshots/en/modelBench.png) |

**Knowledge & Reuse**

| 📖 Claude Docs Hub | 📝 Prompt Library |
|---|---|
| ![Claude Docs](./docs/screenshots/en/claudeDocs.png) | ![Prompt Library](./docs/screenshots/en/promptLibrary.png) |
| 👥 Project Sub-agents | 🔗 MCP Connectors |
| ![Project Agents](./docs/screenshots/en/projectAgents.png) | ![MCP](./docs/screenshots/en/mcp.png) |

**One-click execution (v2.36)**

| 🎯 Run Center (ECC + OMC + OMX, 268 items) | 🧑‍✈️ Crew Wizard (Zapier-style scaffolder) |
|---|---|
| ![Run Center](./docs/screenshots/en/runCenter.png) | ![Crew Wizard](./docs/screenshots/en/crewWizard.png) |
| / Slash commands with Run buttons + ECC chips | 📚 Guide & Tools (ECC · OMC · OMX · best practice) |
| ![Commands](./docs/screenshots/en/commands.png) | ![Guide & Tools](./docs/screenshots/en/guideHub.png) |

**Token Optimization**

| 🦀 RTK Optimizer (install, activate, stats) |
|---|
| ![RTK Optimizer](./docs/screenshots/en/rtk.png) |

_All screenshots auto-generated by `scripts/capture-screenshots.mjs` (Playwright, 1440×900 @ 2x). Regenerate after UI changes._

---

## ✨ Why this project?

You already use Claude Code. But as you add more tools — GPT, Gemini, Ollama, Codex — you end up juggling CLIs, API keys, fallback logic, and cost tracking yourself. And Claude Code's configuration (`~/.claude/`) accumulates agents, skills, hooks, plugins, MCP servers, and sessions with no unified view.

**LazyClaude solves both problems in one tab.**

| Before | With Control Center |
|---|---|
| `cat ~/.claude/settings.json` and eyeball it | 54 tabs, each rendering the relevant slice |
| `ls ~/.claude/agents/` → open in editor | 16 role presets · one-click create |
| Shell-script multi-AI comparison | Drag 3 session nodes → merge → output |
| Manual RAG pipeline assembly | Built-in `RAG Pipeline` template |
| API cost a mystery | Daily stacked chart per provider |
| Korean/English context switching | Runtime `ko` / `en` / `zh` toggle |

---

## 🎯 Use cases

**Individual developer** — Manage your Claude Code setup: agents, skills, slash commands, MCP servers, and sessions from one place. One-click create sub-agents from 16 role presets.

**Team lead** — Build a `Lead → Frontend + Backend + Reviewer` parallel workflow. Spawn real Terminal sessions, resume by `session_id`, inject feedback notes, and loop for N sprints.

**AI researcher** — Send the same prompt to Claude + GPT + Gemini in parallel, merge results, and auto-save the comparison. Or build a RAG pipeline with `embedding → vector search (HTTP) → Claude` in five drag-and-drops.

**Automation engineer** — Trigger workflows via Webhook (`POST /api/workflows/webhook/{id}`) from GitHub Actions / Zapier. Schedule daily runs with Cron. Retry on failure, fall back to a cheaper provider, and alert on token budget overruns.

**Ollama power user** — Browse a 23-model catalog, one-click download, create custom models with Modelfile, and pick default chat / embedding models — no `ollama pull` memorization needed.

---

## 🚀 Quick Start (30 seconds)

**1 · Clone**
```bash
git clone https://github.com/cmblir/LazyClaude.git && cd LazyClaude
```

**2 · Run**
```bash
python3 server.py
```

**3 · Open**
→ [http://127.0.0.1:8080](http://127.0.0.1:8080)

That's it. No `pip install`, no `npm install`, no Docker. The server uses only Python stdlib.

### Prerequisites

| Required | Recommended | Optional |
|---|---|---|
| Python 3.10+ | Claude Code CLI — `npm i -g @anthropic-ai/claude-code` | Ollama (auto-started) |
| — | macOS (for Terminal.app session spawn) | GPT / Gemini / Anthropic API keys |

### Environment variables

```bash
HOST=127.0.0.1                       # Bind address (default)
PORT=8080                            # Port (default)
CHAT_MODEL=haiku                     # Chatbot model: haiku (default) / sonnet / opus
OLLAMA_HOST=http://localhost:11434   # Ollama server
OPENAI_API_KEY=sk-...                # Optional, can also be set in UI
GEMINI_API_KEY=AIza...               # Optional
ANTHROPIC_API_KEY=sk-...             # Optional
```

API keys can also be saved via the `🧠 AI Providers` tab — stored in `~/.claude-dashboard-config.json`.

### Install as an app (v2.35)

#### Option A — PWA (any browser, any OS)

1. Run `python3 server.py` and open `http://127.0.0.1:8080`.
2. Click the **install icon** in the address bar (Chrome / Edge / Brave),
   or **Share → Add to Home Screen** in Safari (iOS).
3. LazyClaude launches in its own window with no browser chrome,
   pinnable to the Dock / taskbar / home screen, with `Workflows`,
   `Crew Wizard`, and `AI Providers` shortcuts in the right-click menu.

#### Option B — macOS `.app` bundle (Spotlight + Dock)

```bash
make install-mac     # builds + copies LazyClaude.app to /Applications/
```

Then double-click in Finder, or `⌘Space → LazyClaude` from Spotlight.
The launcher starts the server on first open, reuses an already-running
server on subsequent opens, opens the dashboard in your default browser,
and shuts the server down on Quit. Logs go to `~/Library/Logs/LazyClaude/server.log`.

The bundle is **72 KB** — no Python interpreter, no Electron. It calls
your system `python3`, matching LazyClaude's stdlib-only philosophy.
Uninstall with `make uninstall-mac`.

---

## ✨ Features

### 🎯 Run Center — execute ECC / OMC / OMX from the dashboard (v2.36)

- **Unified catalog over 268 entries**: ECC's 181 skills + 79 slash commands (parsed from `~/.claude/plugins/cache/<ecc-or-everything-claude-code>/.../{skills,commands}/`), OMC's 4 modes, OMX's 4 commands.
- **One-click execution** via the existing `execute_with_assignee` pipeline — runs through Claude / GPT / Gemini / Ollama, reports tokens / cost / duration.
- **Filters**: 5 sources (All / ECC / OMC / OMX / ⭐ Favorites), 6 kinds (skill / command / mode / diagnostic / knowledge), auto-derived category chips.
- **Save-to-prompt** pushes the result into the Prompt Library; **Convert-to-workflow** hands off either to the matching built-in template (OMC) or scaffolds a 1-node workflow (ECC).
- **Diagnostics** — `installed_plugins.json` is read first; the sidebar surfaces every scanned root with per-root counts so users can debug "ECC installed but Run Center empty" on their own.
- **Workflow Quick Actions** — 4 OMC mode buttons (🚀 Autopilot / 🔁 Ralph / 🤝 Ultrawork / 🧐 Deep Interview) at the top of the Workflows tab. Click → enter a goal → workflow scaffolded + auto-run.
- **Commands tab Run buttons** — every slash command card now has a ▶ Run button and an ECC chip when applicable.

### 🧑‍✈️ Crew Wizard — Zapier-style scaffolder (v2.34)

- **4-step form** in the `Crew Wizard` tab → planner + personas + Slack approval + Obsidian log workflow built in one click
- **3 autonomy modes** — `admin_gate` (Slack waits for ✅/❌), `autonomous` (short timeout, agent decides), `no_slack` (pure local crew)
- **Free-form Slack reply** during a cycle is fed back into the planner as the next step's input — admin can steer mid-flight
- **Obsidian log node** appends each cycle's report to `<vault>/Projects/<project>/logs/YYYY-MM-DD.md`
- The generated workflow is just a regular workflow — open it in the canvas and edit freely

### 🔀 Workflow Engine (n8n-style DAG)

- **18 node types**: `start` · `session` · `subagent` · `aggregate` · `branch` · `output` · `http` · `transform` · `variable` · `subworkflow` · `embedding` · `loop` · `retry` · `error_handler` · `merge` · `delay` · `slack_approval` · `obsidian_log`
- **Parallel execution** via topological levels + ThreadPoolExecutor
- **SSE streaming** for live node progress
- **🔁 Repeat** — max iterations · interval · schedule window (`HH:MM~HH:MM`) · feedback-note injection
- **Cron scheduler** — 5-field `cron` expression, minute-granularity
- **Webhook trigger** — `POST /api/workflows/webhook/{wfId}` with `X-Webhook-Secret` header (mandatory since v2.23, generate/rotate/clear from editor)
- **Export / Import** — share workflows as JSON
- **Version history** — last 20 versions auto-saved + one-click restore
- **Conditional execution** — 11 condition types (contains, equals, regex, length, expression with AND/OR, ...)
- **Variable scope** — `{{var}}` template substitution, global or local
- **8 templates** — 5 built-in (Multi-AI Compare · RAG Pipeline · Code Review · Data ETL · Retry) + 3 team starters (Lead/FE/BE · Research · Parallel×3) + unlimited custom
- **Canvas UX** — minimap · node search (highlight + dim) · grouping (Shift+click) · Ctrl+C/V/Z · `?` shortcuts modal
- **18-scene interactive tutorial** with typewriter + cursor animation

### 🧠 Multi-AI Providers

- **8 built-in** — Claude CLI · Ollama · Gemini CLI · Codex + OpenAI API · Gemini API · Anthropic API · Ollama API
- **Custom CLI providers** — register any CLI as a provider (chat + embed commands)
- **Fallback chain** — auto-switch on failure (`claude-cli → anthropic-api → openai-api → gemini-api` default)
- **Rate limiter** — per-provider token bucket (requests/min)
- **Multi-AI comparison** — same prompt, multiple providers, side-by-side results
- **Setup wizard** — 3-step guide for first-timers (select → configure → test)
- **Health dashboard** — real-time availability per provider
- **Cost tracking** — per-provider / per-workflow / per-day stacked bar chart
- **Usage alerts** — configurable daily token / cost thresholds → browser notification

### 🦙 Ollama Model Hub (Open WebUI style)

- **23-model catalog** — LLM · Code · Embedding · Vision categories (llama3.1, qwen2.5, gemma2, deepseek-r1, bge-m3, ...)
- **One-click pull** with progress bar (SSE polling) + delete + model info
- **Auto-start** — dashboard launches `ollama serve` on boot
- **Default model picker** — per-provider chat / embedding defaults
- **Modelfile editor** — create custom models from the UI

### 🦀 RTK Optimizer — cut Claude tokens 60-90% (v2.24.0)

Integrates [`rtk-ai/rtk`](https://github.com/rtk-ai/rtk), a Rust CLI proxy that compresses command output before it reaches the LLM (a medium TS/Rust session went from 118K → 24K tokens in their benchmark).

- **One-click install** — Homebrew / `curl | sh` / Cargo, launched in a Terminal window
- **Claude Code hook activation** — run `rtk init -g` from the dashboard to auto-wrap Bash commands (`git status` → `rtk git status`)
- **Live savings** — `rtk gain` (cumulative) + `rtk session` (current session) rendered as cards with refresh
- **Config viewer** — read `~/Library/Application Support/rtk/config.toml` (macOS) or `~/.config/rtk/config.toml` (Linux)
- **Command reference** — 30+ subcommands grouped into 6 categories (file ops · git · test · build/lint · analytics · utility), with the `-u/--ultra-compact` flag hint

### 🤝 Claude Code Integration (54 tabs)

| Group | Tabs |
|---|---|
| 🆕 New | `features` · `onboarding` · `guideHub` · `claudeDocs` |
| 🏠 Main | `overview` · `projects` · `analytics` · `aiEval` · `sessions` |
| 🛠️ Build | `workflows` · 🆕 `runCenter` · 🆕 `crewWizard` · `agents` · `projectAgents` · `skills` · `commands` · `promptLibrary` · `agentSdkScaffold` · `rtk` |
| 🧪 Playground | `aiProviders` · `promptCache` · `thinkingLab` · `toolUseLab` · `batchJobs` · `apiFiles` · `visionLab` · `modelBench` · `serverTools` · `citationsLab` · `embeddingLab` · `sessionReplay` |
| ⚙️ Config | `hooks` · `permissions` · `mcp` · `plugins` · `settings` · `claudemd` |
| 🎛️ Advanced | `outputStyles` · `statusline` · `plans` · `envConfig` · `modelConfig` · `ideStatus` · `marketplaces` · `scheduled` |
| 📈 System | `usage` · `metrics` · `memory` · `tasks` · `backups` · `bashHistory` · `telemetry` · `homunculus` · `team` · `system` |

Highlights: **16 sub-agent role presets**, session timeline with quality scoring, CLAUDE.md editor, MCP connector installer, plugin marketplace. **Claude API playground** — 10 tabs: prompt caching, extended thinking, tool use, batch jobs, files API, vision/PDF, model benchmarking, **hosted server tools (web_search + code_execution)**, **citations**, **Agent SDK scaffold**. **Docs Hub** — 33 curated docs.anthropic.com pages with cross-links to dashboard tabs.

### 🌍 Internationalization

- **3 languages** — Korean (`ko`, default) · English (`en`) · Chinese (`zh`)
- **3,234 translation keys** per language · **zero residual Korean** verified
- **Runtime DOM translation** via MutationObserver (no page reload)
- **`error_key` system** — backend error messages localized on the frontend
- **Verification pipeline** — `scripts/verify-translations.js` enforces 4 checks (parity · `t()` calls · audit · static DOM)

### 🎨 UX & Accessibility

- **5 themes** — Dark · Light · Midnight · Forest · Sunset
- **Mobile responsive** — collapsible sidebar, full-screen modals
- **Accessibility** — ARIA labels, `role="dialog"`, focus traps, keyboard navigation
- **Browser notifications** — workflow complete, usage alert, system event
- **Performance** — API response caching, debounced auto-reload, RAF batching

---

## 📐 Architecture

```
claude-dashboard/
├── server.py                     # Entry (port-conflict resolution + ollama auto-start)
├── server/                       # 14,067 lines · stdlib only
│   ├── routes.py                 # 190 API routes (GET + POST + PUT + DELETE + regex webhook)
│   ├── workflows.py              # DAG engine · 16 node executors · Repeat · Cron · Webhook (2,296)
│   ├── ai_providers.py           # 8 providers · registry · rate limiter (1,723)
│   ├── ai_keys.py                # Key mgmt · custom providers · cost tracking (734)
│   ├── ollama_hub.py             # Catalog · pull/delete/create · serve mgmt (606)
│   ├── nav_catalog.py            # Single source of truth for 54 tabs + i18n descriptions
│   ├── run_center.py             # Run Center: ECC + OMC + OMX catalog + executor + history (~480)
│   ├── crew_wizard.py            # Crew Wizard form → DAG builder
│   ├── slack_api.py              # Slack Web API client (chat.postMessage, reactions.get)
│   ├── obsidian_log.py           # Obsidian markdown appender (host-rooted, realpath checked)
│   ├── features.py               # Feature discovery · AI evaluation · recommendations
│   ├── projects.py               # Project browser · 16 sub-agent role presets
│   ├── sessions.py               # Session indexing · quality scoring · agent graph
│   ├── system.py                 # Usage · memory · tasks · metrics · backups · telemetry
│   ├── errors.py                 # i18n error key system (49 keys)
│   └── …                         # 20 modules total
├── dist/
│   ├── index.html                # Single-file SPA (~13,500 lines)
│   └── locales/{ko,en,zh}.json   # 3,234 keys × 3 languages
├── tools/
│   ├── translations_manual_*.py  # Manual translation overrides
│   ├── extract_ko_strings.py     # Korean string extractor
│   ├── build_locales.py          # ko/en/zh JSON builder
│   └── i18n_audit.mjs            # Node-side audit
├── scripts/
│   ├── verify-translations.js    # 4-stage i18n verification
│   └── translate-refresh.sh      # One-shot pipeline
├── VERSION · CHANGELOG.md
└── README.md · README.ko.md · README.zh.md
```

### Data stores (all in `$HOME`, overridable via env vars)

| File | Contents |
|---|---|
| `~/.claude-dashboard-workflows.json` | Workflows + runs + custom templates + version history + costs |
| `~/.claude-dashboard-config.json` | API keys · custom providers · default models · fallback chain · usage thresholds |
| `~/.claude-dashboard-translations.json` | AI translation cache |
| `~/.claude-dashboard.db` | SQLite session index |
| `~/.claude-dashboard-mcp-cache.json` | MCP catalog cache |
| `~/.claude-dashboard-ai-evaluation.json` | AI evaluation cache |

Atomic writes via `server/utils.py::_safe_write` (`.tmp → rename`), threading locks for concurrent safety.

### Tech stack

| Layer | Technology |
|---|---|
| Backend | Python stdlib `ThreadingHTTPServer` (zero dependencies) |
| Database | SQLite WAL mode |
| Frontend | Single HTML + Tailwind CDN + Chart.js + vis-network |
| i18n | Runtime JSON fetch + MutationObserver DOM translation |
| Workflow | Topological DAG sort + `concurrent.futures.ThreadPoolExecutor` |
| Chatbot | Dynamic system prompt (reads VERSION + CHANGELOG + nav_catalog on every request) |

---

## 🔢 Stats (v2.36.3)

| Metric | Value |
|---|---|
| Backend code | ~19,000 lines · 50 modules · stdlib only |
| Frontend code | ~18,500 lines · single HTML file |
| API routes | **199** (GET 105 / POST 91 / PUT 3 + regex webhook) |
| Tabs | **54** across 6 groups |
| Workflow node types | **18** (incl. `slack_approval`, `obsidian_log`) |
| Run Center catalog | **268** entries (181 ECC skills + 79 ECC commands + 4 OMC modes + 4 OMX commands) |
| Workflow built-in templates | **10** (incl. `bt-autopilot`, `bt-ralph`, `bt-ultrawork`, `bt-deep-interview`, `bt-team-sprint`, `bt-crew`) |
| AI providers | **8** built-in + unlimited custom |
| Claude API playground tabs | **11** (prompt cache · extended thinking · tool use · batch · files · vision · model bench · server tools · citations · agent sdk scaffold · embedding lab) |
| Translations | **3,845** keys × ko / en / zh — 0 Korean residue |
| Install paths | local (`python3 server.py`) · PWA (any browser) · macOS `.app` (72 KB) |
| Unified cost timeline | ✓ (all playgrounds + workflows, daily stacked) |
| Workflow run diff / rerun | ✓ (per-node Δ) |
| Prompt Library | ✓ (tag search + convert to workflow) |
| Batch cost guard | ✓ (per-batch USD/token limits) |
| Curated docs pages | **33** |
| Ollama catalog | **23** models |
| Sub-agent role presets | **16** |
| Built-in workflow templates | **8** (5 built-in + 3 team) |
| i18n keys | **3,234** × 3 languages · 0 missing |
| Themes | **5** |
| Tutorial scenes | **18** |
| E2E test scripts | **3** (tabs smoke · workflow · ui elements) |

---

## 🛠️ Troubleshooting

| Problem | Solution |
|---|---|
| Port 8080 already in use | `PORT=8090 python3 server.py` (the server also offers to kill the existing process) |
| `claude` command not found | Install Claude Code CLI: `npm i -g @anthropic-ai/claude-code` |
| Ollama connection failed | Check `OLLAMA_HOST` (default `http://localhost:11434`) or let the dashboard auto-start it |
| Session spawn fails on macOS | Grant Terminal automation permission in System Settings → Privacy → Automation |
| English mode still shows Korean | Run `scripts/translate-refresh.sh` (rebuilds locales + verifies) |
| Chatbot says "I don't know about this feature" | Chatbot reads `VERSION` + `CHANGELOG.md` + `nav_catalog.py` live — update these 3 files when adding features |

---

## 🎭 E2E Testing (Playwright)

Playwright is pre-installed as a devDependency. First-time browser setup:

```bash
npx playwright install chromium
```

Then with the dashboard running (`python3 server.py`):

```bash
npm run test:e2e:smoke       # 54 tabs — view-render-fail / console-error detection
npm run test:e2e:ui          # workflow DOM + v2.10.x UX regression checks (v2.18.0)
npm run test:e2e:workflow    # builtin template create → run → banner observed
npm run test:e2e:all         # smoke + ui in sequence
npm run test:e2e:headed      # show the browser window
TAB_ID=workflows npm run test:e2e:smoke   # only one tab
```

Scripts live under `scripts/e2e-*.mjs` and run zero-dependency against a live `127.0.0.1:8080`.

---

## 🤝 Contributing

LazyClaude is a solo-maintained personal project, but issues and PRs are welcome at [github.com/cmblir/LazyClaude](https://github.com/cmblir/LazyClaude).

Small fixes (typos, i18n gaps, obvious bugs) can go straight to a PR. For larger features or refactors, please open an issue first so we can avoid duplicate work.

Install the repo pre-commit hook once so i18n drift can't land:

```bash
git config core.hooksPath scripts/git-hooks
```

### Adding a new tab (7 steps)

1. Add entry to `dist/index.html::NAV`
2. Implement `VIEWS.<id>` renderer in `dist/index.html`
3. Add `(id, group, desc, keywords)` to `server/nav_catalog.py::TAB_CATALOG`
4. Add `en` / `zh` descriptions to `TAB_DESC_I18N`
5. (If needed) Add backend route to `server/routes.py` + module under `server/`
6. Register new UI strings in `tools/translations_manual_9.py`
7. Run `python3 tools/extract_ko_strings.py && (cd tools && python3 build_locales.py) && node scripts/verify-translations.js`

### Translation contributions

See [`TRANSLATION_CONTRIBUTING.md`](./TRANSLATION_CONTRIBUTING.md) and [`TRANSLATION_MIGRATION.md`](./TRANSLATION_MIGRATION.md). All UI strings must exist in ko / en / zh; the CI check `verify-translations.js` enforces zero missing keys.

### Versioning rule

- `MAJOR` — breaking workflow / schema changes
- `MINOR` — new tabs or major features (backward compatible)
- `PATCH` — bug fixes, UI tweaks, i18n reinforcement

On every feature change, update `VERSION` + `CHANGELOG.md` + `git tag -a vX.Y.Z` together.

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

[MIT](./LICENSE) — free for personal and commercial use. Attribution appreciated but not required.

---

## 🙏 Acknowledgements

- [Anthropic Claude Code](https://claude.com/claude-code) — the CLI this dashboard is built around
- [n8n](https://n8n.io) — inspiration for the workflow editor
- [Open WebUI](https://openwebui.com) — inspiration for the Ollama model hub
- [lazygit](https://github.com/jesseduffield/lazygit) / [lazydocker](https://github.com/jesseduffield/lazydocker) — the "lazy" spirit that named this project
- All contributors to the open-source LLM ecosystem 🧠

<div align="center"><sub>Made with 💤 for those who'd rather click than type.</sub></div>
