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
| **v2.54.0** | 🧹 **Housekeeping + 264 tests + perf regression suite**. Backup retention (`api_backup_prune` keepLast/retentionDays + safety net), AR stale entry purge (`api_auto_resume_prune_stale` only terminal states past 30d), new `server/housekeeping.py` orchestrator with disk-usage report. UI "🧹 정리" card with dry-run preview → confirm → real run flow. Test count 171 → 264 (+93) covering backup/learner/hyper_agent/briefing/system + new perf regression suite (17 timing-budget assertions for hot paths). |
| **v2.53.0** | 💾 **Backup/restore + 🔍 session search + 171 tests**. New `server/backup.py` snapshots all `~/.claude-dashboard-*.json` + SQLite via `VACUUM INTO` into `~/.claude-dashboard-backups/lazyclaude-<ts>.tar.gz` with atomic `.tmp+rename` + manifest. `💾 백업 & 복원` tab under `reliability` category exposes list/create/restore/delete with safety guards. New `/api/sessions/search?q=&limit=&cwd=` streams JSONLs line-by-line, scores by occurrences + recency, top-200 sessions cap, ≤5 matches/session early-term, 30s TTL cache. Sessions tab gets debounced search box + result table. Test count 113 → 171 (+58) covering hooks/mcp/cost_timeline/notify. |
| **v2.52.0** | 🧠 **Hyper-Advisor + 113 tests + 467× AR status**. Picks up the v2.49.0-deferred Hyper-Agent ↔ Auto-Resume integration: new `hyper_advise_auto_resume(entry, recent_failures)` calls a Haiku meta-LLM with retry-policy decision rules per exit reason and returns a clamped JSON proposal. UI exposes "🧠 Hyper Advisor" button per row → modal with current vs suggested pollInterval / maxAttempts / promptHint / rationale → "Apply" merges into existing entry. Test count 68 → 113 (+45) covering workflows.py, ai_providers.py, ccr_setup.py. `/api/auto_resume/status` 327 ms → 0.7 ms (467×) via 0-binding short-circuit that skips the lsof+ps cross-ref. |
| **v2.51.0** | 🛠️ **UX hardening — QS lag fix + mascot + 현재 파라미터 + AR terminal-scoped + 🛟 reliability category**. Quick Settings tab-click was double-rendering (innerHTML + recursive openQuickSettings); extracted `_qsRefreshSection` so each click triggers `_qsRenderShell` ×1 and `_qsBindControls` ×1. Mascot timers (15s bubble + 6-10s wander) now early-exit when hidden. New 5th Quick Settings section `🔎 현재 파라미터` (read-only) showing effective prefs (with default/user-set source), runtime info, and `/api/version`·`/api/prefs/get`·`/api/auto_resume/status` quick links. Auto-Resume binding now restricted to currently-running CLI sessions: `api_auto_resume_set` rejects unless session is live or `allowUnboundSession=true`. Each binding gains `pid`, `terminal_app`, `liveSession`, `terminalClosedAction` (`wait`/`cancel`/`exhaust`). `cancel` auto-stops after 3 dead ticks. UI gets a 터미널 column + 🟢 실행 중 / ⚪ 종료됨 chip. Auto-resume tabs moved out of `observe` into a new `🛟 안정성 (reliability)` category. |
| **v2.50.0** | 📊 **Observability + reliability — telemetry, cost recommendations, +41 tests**. Surfaces the data v2.46.0–v2.49.0 quietly built up. New `📊 실행 텔레메트리` panel inside the workflows tab reads from the v2.47.0 `workflow_runs` SQLite — per-workflow p50/p95/p99 + success/retry rate + cost over selectable window (1h/24h/7d/30d), 30s auto-refresh with visibility guard. New `💡 비용 절감 추천` panel inside the costs timeline tab — rule-based recs (Haiku swap for short prompts, prompt caching for long context, ollama for repetitive batch, model-upgrade for stale models) with estimated savings. Test count 27 → 68 (+41) covering db.py / prefs.py / process_monitor.py. `/api/workflows/telemetry`, `/api/costs/recommendations` registered. |
| **v2.49.0** | 🔄 **Auto-Resume hardening** — mgmt tab (`🔄 Auto-Resume 관리` under `observe`) with active-bindings table + bulk cancel + per-state count chips + 10s auto-refresh (visibility-aware). Notification channels expanded: SMTP+STARTTLS email, Telegram Bot API — alongside existing Slack/Discord. Wired through `_sanitize_notify` + `_send_notify`. Haiku summary bypass via new `scripts/ar-haiku-summary.py` (stdlib-only, 198 lines, direct Anthropic Messages API call, 6 distinct exit codes, `--dry-run` redacts key) — install with `use_direct_api=True` (back-compat default off). 36-line docstring documents the snapshot+inject mechanism and both Haiku backends. **First pytest harness** for the project: `tests/test_auto_resume.py` covers 26 cases across `_classify_exit / _parse_reset_time / _exponential_backoff / _push_hash_and_check_stall / _jsonl_idle_seconds`. `make test` target. |
| **v2.48.1** | 🔄 **Auto-Resume worker concurrency** — single-threaded serial retry loop replaced with `ThreadPoolExecutor(max_workers=4)` fan-out per tick. With N pending sessions, up to 4 process concurrently instead of waiting N×retry-time serially. Lock discipline preserved (`_process_one` takes `_LOCK` for JSON IO, `_RUNNING_PROCS` blocks same-sid re-entry). Pool drains cleanly on worker shutdown via `cancel_futures=True`. |
| **v2.48.0** | 🧹 **Phase-3 — dead code purge + EXPLAIN-driven indexes + CSS prune**. JS: removed orphaned `VIEWS.design` + `addDesignDir` (128 lines, no NAV entry), unused `_wfAddNode`, `_wfInspectorBody` (superseded), `_wfNodeSet` (legacy variant) — total **354 JS lines / -23 KB**. Python: 4 unused imports across `system.py / auth.py / toolkits.py`. CSS: 3 dead custom classes (`.card-hi`, `.divider`, `.group-label`) — theme/state classes verified dynamic-set and kept. Database: ran `EXPLAIN QUERY PLAN` on every static SQL in `server/*.py` against live DB; **7 new indexes** turn `SCAN + TEMP B-TREE` into `SCAN/SEARCH USING INDEX` for `tool_use_count`, `total_tokens`, `duration_ms`, `subagent_type+ts`, `agent_edges.ts`, `workflow_runs.started_at`, `run_history(source, item_id, ts)`. `ANALYZE` runs once at `_db_init` (4.8 ms). DB index count 12 → 19. |
| **v2.47.0** | 🚀 **Phase-2 perf — workflows.runs → SQLite + 27× RSS drop + frontend consolidation**. Run state migrated from monolithic JSON blob to a `workflow_runs` SQLite table with `idx_runs_workflow / idx_runs_status` indexes; `_LOCK` now covers definitions only — concurrent saves no longer serialize on full-file fsync. One-time migration flagged in the JSON store; legacy `runs` dict preserved for rollback. RSS profiled with tracemalloc: `_index_jsonl` was reading entire JSONLs into memory + 3 separate iterations — rewrote as single-pass streaming (steady-state **700 MB → 42 MB**, force re-index **1947 MB → 102 MB**). Live server now 57 MB RSS (was 1577 MB → ~27×). Frontend: sessions table virtual-scrolled via IntersectionObserver (50-row chunks), 8 Chart.js sites switched to in-place `chart.update('none')` instead of destroy+recreate, 9 global keydown listeners consolidated into a single dispatcher (caught a latent `_wfBindCanvas` re-attach leak as bonus), `_makeDraggable` document listener leak plugged via `_detachDragListeners`. |
| **v2.46.0** | 🚀 **Comprehensive perf sweep — 33 surgical fixes** across backend (12) + frontend (8) + boot/static/i18n (4) + 9 deferred to v2.47.0+. Backend: `_db_init` guarded (was per-request), 3 missing SQL indexes, hooks/translations/ollama-models TTL caches, `lsof` TCP/UDP parallelized, sessions N+1 SQL bug fixed (cursor-after-`with` scope error), learner JSONL walk → indexed SQL, MCP module-level disk I/O deferred. Frontend: `_wfUpdateNodeTransform` 60fps `querySelector` → Map lookup, viewport ref cached, `escapeHtml` map hoisted, 11 read-only endpoints swapped to `cachedApi`, 5 polling timers gated by `document.hidden`, `_apiCache` LRU-capped, duplicate resize listener removed, `_recentTabsCache` memoized. Boot: `background_index` + `_auto_start_ollama` daemon-threaded — `Serving http://...` now logs **before** any I/O. Static: `ETag` + `If-None-Match` → 304 short-circuit, locale JSON gzipped through cache (was uncompressed every request), `_STATIC_CACHE` LRU-capped. i18n: pipeline mtime-guarded (skip when no source changed). Measured: `/api/hooks/recent-blocks` cold→warm **2754 ms → 4 ms (~700×)**, `_db_init` second call 0.00 ms. |
| **v2.45.2** | 🐛 **Fix + 🔌 toggle** — Ollama tab's "Installed models" table was forever empty: `_ollamaLoadInstalled` populated the data array but never called `_ollamaRenderInstalled()`. Now it does — the 🗑 delete + 상세 buttons per row finally appear. **New pref `behavior.autoStartOllama`** (default `true` for back-compat) wired into Quick Settings (⌘,). Flip off to skip the auto `ollama serve` spawn at dashboard boot and reclaim its idle RSS. |
| **v2.45.1** | 🚀 **Perf hotfix** — `/api/ccr/status` was running its 4 subprocess probes (node/ccr/claude `--version` + `lsof` port LISTEN) sequentially (~700 ms). Now fanned out via `ThreadPoolExecutor(4)` — measured **~700 ms → ~340 ms (≈50% ↓)**. `/api/sessions-monitor/list` per-session `ps` collapsed into a single `ps -p pid1,pid2,…` batch — N→1 subprocesses, scales linearly when many Claude Code instances are running. |
| **v2.45.0** | 🛣️ **`zclaude` setup wizard (claude-code-router)** — new `config` tab walks the user through routing Claude Code through Z.AI/DeepSeek/OpenRouter/Ollama/Gemini via `@musistudio/claude-code-router`. Five steps: status checks (node ≥20, `ccr`, `claude`, config, port-3456 listen), Providers editor with one-click presets, Router rules (default / background / think / longContext / webSearch) with provider×model dropdowns, service Start/Stop/Restart, and a copy-paste shell-alias block (`alias zclaude='ccr code'`) — the dashboard **never** edits your `~/.zshrc`. Backed by stdlib-only `server/ccr_setup.py` with atomic config writes, `chmod 600`, schema validation against CCR v2.0.0, and `$HOME` sandboxing. |
| **v2.44.1** | 🪢 **multiAssignee parallel fan-out + keyed canvas diff** — picks up v2.44.0's deferred items. Session/subagent inspector replaces the single assignee with a repeating row builder (`+ 어시니 추가`); when ≥2 rows are present the node fans out via `ProviderRegistry.execute_parallel` (openclaw-style: ThreadPoolExecutor + as_completed first-ok, cancels the rest). Single-assignee nodes behave exactly as before. `_wfRenderCanvas` rewritten as keyed-diff renderer (`__wf._nodeEls` Map + JSON snapshot per node) — only changed nodes are replaced; unchanged ones keep identity, so `data-status` writes, drag transforms, and selection classes survive subsequent renders. Edges still rebuild via `innerHTML` (fewer of them, position-dependent). Handlers stay attached because the canvas uses pure event delegation on `<svg>#wfSvg`. |
| **v2.44.0** | 🖥️ **Open ports / CLI sessions / memory monitors + workflow perf** — three new `observe` tabs: list every TCP/UDP listening port with `lsof` + the bound process and one-click kill (with `pid<500` / self-pid guards); list active Claude-Code/CLI sessions with RSS / idle-time and "Open Terminal" + kill; live memory snapshot (total/used/free/swap progress bars) with top-30 RSS table and a "Kill all idle Claude Code" sweep. Workflow engine: parallel worker cap 4 → `min(32, cpu*2)`, drag patch endpoint skips full sanitize, topological sort memoized, per-node status writes moved to an in-memory `_RUNS_CACHE` (disk only at boundaries). Backend `execute_parallel` openclaw-style fan-out (first-ok across providers) added; UI wiring lands in v2.44.1. Inspector early-exits when selection unchanged; webhook secret cached per workflow. |
| **v2.43.2** | 📊 **Project / session token drill-down** — the Usage tab's "Tokens by project" was capped at 20 read-only rows. Now: every project (full ranked list) is shown in a scrollable, **clickable** list. Click a row → modal with that project's totals (input/output/cache split), per-session table sorted by tokens, tool/agent distribution bars, and a daily timeline. Each session row jumps into the existing session-detail modal. New `GET /api/usage/project?cwd=...` (sandboxed under `$HOME`). |
| **v2.43.1** | 🚀 **Perf — workflow canvas + skills/commands lists** — Skills/Commands tabs blocked first paint on a 1.4 MB scan-and-parse (816 ms / 1116 ms). Now TTL+mtime-cached at the backend, ~22× / ~31× per warm visit. Workflow canvas drag fired `_wfRenderMinimap` synchronously every mousemove (~100/s) and ran O(N×E) edge lookups; now coalesced into ≤1 rAF tick and node/edge lookups dropped to O(deg) via cached Maps for the drag lifetime. |
| **v2.43.0** | 🛠️ **Setup Helpers — global ↔ project scope** — every config tab (CLAUDE.md / Settings / Skills / Commands / Hooks) now has a 🌐 Global / 📁 Project toggle with a project picker. Project mode reads/writes `<cwd>/CLAUDE.md` · `<cwd>/.claude/settings.json` · `<cwd>/.claude/settings.local.json` (gitignored personal overrides) · `<cwd>/.claude/skills/<id>/SKILL.md` · `<cwd>/.claude/commands/**/*.md`. 14 new endpoints, all sandboxed under `$HOME`, permissions sanitised through the existing global pipeline. |
| **v2.42.3** | 🩹 **Hooks tab — 2 s load → instant + delete actually deletes** — the Hooks tab blocked first paint on a 90 MB jsonl scan (1.94 s) and `deleteHook` never re-rendered the list. Now: `/api/hooks/recent-blocks` is TTL+mtime-cached (cold 0.97 s → warm 0.026 s, 37×) and lazy-fetched after first paint via `_renderRecentBlocksPanel` injection. Delete (both plugin + user paths) calls `renderView()` on success so the card disappears immediately. |
| **v2.42.2** | 🖥️ **Workflow node spawn → matching provider CLI** — clicking the 🖥️ on a node assigned to `@gemini:gemini-2.5-pro` now opens **Gemini CLI**; `@ollama:llama3.1` opens **`ollama run llama3.1`**; `@codex:o4-mini` opens **codex**. Previously every spawn launched Claude regardless of the node's assignee. Falls back to claude with a warning toast if the requested CLI isn't installed. Prompt is shown as a banner (so the interactive REPL stays open). |
| **v2.42.1** | 🔄 **Workflow run visibility** — list cards now show inline status chips (✅/❌/⏳) for the last 3 runs, a pulsing `● Running` badge for in-flight runs, and `(N runs)` total. Re-opening a workflow canvas auto-restores the last run state — live polling for active runs, one-shot node-color hydration for finished runs. Backend `api_workflows_list` now ships `lastRuns`/`runningCount`/`activeRunId`/`totalRuns`. |
| **v2.42.0** | 🖱️🧩🧭🔁 **Four Anthropic features in one release** — Computer Use Lab (`computer-use-2025-01-24` beta · plan-only), Memory Lab (`memory-2025-08-18` beta · server-side memory blocks), Advisor Lab (Executor + Advisor pair · cost/quality delta), and full Claude Code Routines CRUD + run-now. 14 new endpoints, 4 new playground tabs. |
| **v2.41.0** | 👥 **Agent Teams + 🤝 Recent sub-agent activity** — bundle agents into reusable teams (`Frontend Crew = ui-designer + frontend-dev + code-reviewer`), then 🚀 Spawn outputs every member's `claude /agents <name>` command at once. Project Detail modal gains a "Recent sub-agent activity" timeline grouped by source session — see what work each session delegated to its sub-agents, and click 🖥 CLI to bring up Terminal.app on that exact session resume. |
| **v2.40.5** | 🩹 **Hotfix** — Recent Blocks / Detective chips were unclickable: inline `onclick="state.data.hooksFilter=${JSON.stringify(id)};…"` emitted double-quotes that collided with the attribute quoting, so the parser ate the handler. Now `data-hook-id="…"` + a shared `_jumpToHookCard()` helper. Click → filter applied + card pulsed. |
| **v2.40.4** | 🔬 **Hook Detective + 🚨 Recent Blocks + 🧬 Dispatcher decoder** — paste a hook block-error message, get clickable hook-id chips that auto-jump and pulse the matching card; backend mines the most recent 60 jsonl transcripts and surfaces a top-N "🚨 Recently blocked hooks" panel; every card now has a 🔬 Detail modal that decodes `node -e "..."` wrappers into a `node → runner → hook id → handler → flags` chain. |
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

### 🎼 Channel Orchestrator (v2.55.0)

A single dashboard tab — and a `python3 tools/tui_config.py` terminal UI — that
turns the dashboard into a multi-agent hub for chat platforms:

- **Slack and Telegram inbound.** Slack via the Events API (`/api/slack/events`),
  Telegram via long-poll (no public URL needed). One bot, many channels.
- **Plan → fan out → aggregate.** Inbound message goes to a configurable
  *planner* (default: a Claude model), which emits a JSON plan. Sub-tasks run
  in parallel via `execute_with_assignee` across any registered provider
  (Claude / OpenAI / Gemini / Ollama / Codex / custom CLI). A small
  *aggregator* call (also configurable) merges results before the channel
  reply.
- **Per-channel bindings.** A binding can either nail a channel to a saved
  workflow (run that DAG with the message as input) or specify which assignees
  to use for an ad-hoc plan. Configure from the **Orchestrator** tab or the
  TUI.
- **Live agent-to-agent reporting.** Every step publishes `start`/`done` events
  to an in-process pub/sub bus (`server/agent_bus.py`). The bus is wakeup-
  driven (no polling), batches writes to SQLite (single shared DB), dedups
  identical events inside a 5-second LRU window, and is queryable over HTTP
  for live UI streams (`GET /api/agent-bus/stream` SSE).
- **Two-way agent protocol.** `agent_bus.ask(topic, payload, timeout_s)` lets
  one agent block on a correlated reply from any subscriber — built on the
  same wakeup-driven primitive (no second condition variable, no polling).
- **Workflow-bound channels.** A binding can point at a saved workflow; the
  inbound message runs that DAG and the workflow's last meaningful output
  becomes the channel reply.
- **Run history.** Every dispatch (ad-hoc or workflow) is persisted to SQLite
  (`orch_runs` table) and surfaced in the Orchestrator tab.
- **Slack signature verification.** Set `SLACK_SIGNING_SECRET` to enforce
  HMAC-SHA256 over `v0:<ts>:<raw-body>` on `/api/slack/events`; stale
  timestamps (>5 min) are rejected.
- **No hardcoding.** Models, channels, debounce intervals, retention windows,
  and pool sizes are all env-overridable. Storage paths follow the existing
  `_env_path()` convention (`CLAUDE_DASHBOARD_ORCHESTRATOR`,
  `CLAUDE_DASHBOARD_TELEGRAM`, `AGENT_BUS_*`).

```bash
python3 tools/tui_config.py          # configure providers / Slack / Telegram / bindings
curl -X POST localhost:8080/api/orchestrator/dispatch \
     -d '{"text":"draft a release note for v2.55","kind":"http"}'
```

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
