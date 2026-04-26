# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack

Pure-stdlib Python HTTP server + single-file HTML SPA. **No runtime build step** — `python3 server.py` serves `dist/index.html` as-is. The only npm dependency is Playwright (devDependency for E2E tests). i18n is the only meaningful tooling step.

## Common commands

```bash
# Run
make run                 # python3 server.py — binds 127.0.0.1:8080 by default
make dev                 # same with LOG_LEVEL=DEBUG
PORT=19500 python3 server.py    # different port (server.py auto-kills port 8080 occupants)
./start.sh               # one-liner with python3 + port pre-check

# i18n (REQUIRED before committing any new t('한국어') strings — see "i18n pipeline")
make i18n-refresh        # full pipeline: extract → build → verify → runtime scan
make i18n-verify         # verify only — must report 0 missing
make i18n-scan           # runtime DOM Korean residue scan

# Playwright E2E (Playwright is installed in node_modules; no headless browser bootstrap)
npm run test:e2e:smoke       # all 50+ tabs render without console errors
npm run test:e2e:workflow    # workflow editor flow
npm run test:e2e:headed      # smoke with visible browser
npm run screenshots          # regenerate docs/screenshots/{ko,en}/*.png

# A single ad-hoc Playwright script
node scripts/e2e-flyout-bug.mjs   # shape: import { chromium } from 'playwright'; ...
```

There is **no test runner** for the Python side. The validation strategy is in-process imports + Playwright. When you change `server/*.py`, run a quick `python3 -c "from server.<module> import ...; ..."` smoke check, then a focused Playwright script if it affects the UI.

## Architecture

### Backend — `server/` (~20 modules, stdlib only)

- `server.py` (root) — entry. Resolves port conflicts (kills existing 8080 occupant), initialises SQLite (`~/.claude-dashboard.db`), background-indexes Claude Code sessions, warms MCP cache, starts the workflow scheduler, auto-starts `ollama serve`, then `ThreadingHTTPServer(Handler)`.
- `server/routes.py` — single dispatch table. `ROUTES_GET` / `ROUTES_POST` / `ROUTES_PUT` map paths → handler functions in other modules. **Every new endpoint registers here.**
- `server/config.py` — all paths come from `_env_path(KEY, default)` so users can override via env (see `env.example`). Read this first to find where any data file lives.
- `server/workflows.py` — the workflow engine (~3000 lines). DAG topological-level execution via `ThreadPoolExecutor`; per-iteration repeat with feedback-note injection; SSE streaming. **Adding a node type requires four edits here**: `_NODE_TYPES` set, `_sanitize_node()` branch, `_execute_node()` dispatch, and a new `_execute_<type>_node()` helper. Then mirror in `dist/index.html` `WF_NODE_TYPES` array, `WF_NODE_CATEGORIES` mapping, and `_wfRenderInspector()` per-type form.
- `server/ai_providers.py` + `server/ai_keys.py` — provider registry. `execute_with_assignee("provider:model", prompt, ...)` is the unified entry — `assignee` like `claude:opus`, `openai:gpt-4.1`, `ollama:llama3.1`. Custom CLI providers register here.
- `server/slack_api.py` / `server/obsidian_log.py` / `server/crew_wizard.py` — v2.34 Crew Wizard pieces. The wizard is a **form → DAG builder**, not a separate engine; it produces a regular workflow saved via `api_workflow_save`.
- `server/notify.py` — webhook fire-and-forget (Slack/Discord). Distinct from `slack_api.py` which is the bot-token Web API client.
- `server/nav_catalog.py` — single source of truth for the 50+ tab catalogue with i18n descriptions, used by `/api/nav/*` and the Docs Hub.

### Frontend — `dist/index.html` (~18,000 lines, single file)

- All UI is one HTML file with inline `<script>`. There is **no module bundler**. Every tab is registered as `VIEWS.<id> = async () => htmlString` and an optional `AFTER.<id> = () => bindEventsAfterRender()`. The router calls these by `id` from the `NAV` array (top of the script section).
- Workflow canvas, palette, inspector, and the Crew Wizard live inside this file. Search for `__wf` (canvas state) and `__cw` (wizard state).
- Translation: every user-visible string goes through `t('한국어 원문')`. The function reads the locale dict matched to the `cc-lang` cookie (`ko` / `en` / `zh`) loaded from `dist/locales/{lang}.json`. **Korean is the source language**; English and Chinese are translations.

### i18n pipeline — non-obvious

The audit extractor (`tools/extract_ko_strings.py`) **truncates at sentence boundaries** (period / slash etc.). Multi-sentence `desc` strings only get their first clause auto-captured. For long descriptions, add the full Korean → EN/ZH mapping by hand to the latest `tools/translations_manual_<N>.py` file (currently `_10`), then `make i18n-refresh`. `_missing.json` must end at 0 for both EN and ZH.

To add a new manual override file:
1. Create `tools/translations_manual_<N+1>.py` with `NEW_EN: dict[str, str]` and `NEW_ZH: dict[str, str]`.
2. Wire it into `tools/translations_manual.py` (mirror the `_NEW_EN_10` block).
3. `make i18n-refresh`.

When EN/ZH translations need a Korean keyword preserved verbatim (e.g. Slack reply commands users type in any locale), strip the Korean from the value too — the missing-detector flags any value still containing `[가-힣]` against a Korean key as a leak.

### Data stores — all `$HOME`-rooted JSON

| Path | Purpose | Override env |
|---|---|---|
| `~/.claude-dashboard-workflows.json` | Workflows + runs + custom templates + history | `CLAUDE_DASHBOARD_WORKFLOWS` |
| `~/.claude-dashboard-ai-providers.json` | API keys, custom CLIs, fallback chain | `CLAUDE_DASHBOARD_AI_PROVIDERS` |
| `~/.claude-dashboard-slack.json` | Bot token (chmod 600) + default channel | `CLAUDE_DASHBOARD_SLACK` |
| `~/.claude-dashboard.db` | SQLite — session index, costs, telemetry | `CLAUDE_DASHBOARD_DB` |
| `~/.claude/` | Claude Code's own state — read-only from this app | `CLAUDE_HOME` |

All writes go through `server/utils.py::_safe_write` (atomic tmp + rename). Path validation uses `_under_home` (resolves to `$HOME` realpath only) — apply this to any user-supplied path.

## Workflow node lifecycle

1. **UI** clicks `+ node` → opens the editor window (a draggable `.feat-win`). User picks a category in the palette accordion (`WF_NODE_CATEGORIES`), picks a node type, fills the inspector form. Title auto-fills via `t(WF_TYPE_MAP[type].label)`.
2. **Save** posts `_wfDraft` JSON to `/api/workflows/save`. `_sanitize_workflow` strict-validates every field (the validator silently drops unknown node types — if a save round-trip loses your nodes, you forgot to extend `_NODE_TYPES`).
3. **Run** posts to `/api/workflows/run`. `_run_one_iteration` (a) computes topological levels, (b) executes one level in parallel via `ThreadPoolExecutor`, (c) writes `runs[runId].nodeResults[nid]` per node before / during / after for live SSE polling.
4. **Repeat** wraps step 3 — on the next iteration, the previous run's final output + `repeat.feedbackNote` get injected into `extra_inputs[feedbackNodeId]` (default: first `session`/`subagent` after `start`).

## Conventions enforced by this repo

- **No main pushes.** `~/.claude/CLAUDE.md` §4.6 forbids `git push origin main`. Work on `feat/*` or `fix/*` branches and push there.
- **English for everything externally visible.** Commit messages, tags, GitHub Release notes, README, CHANGELOG entries — all English. Korean stays in Obsidian ADRs and `README.ko.md`. The mapping table inside CHANGELOG entries can keep the Korean column as illustrative content.
- **Module split rule of thumb.** A frontend feature touching the workflow canvas usually means: one new `server/<feature>.py`, one new entry in `routes.py`, one new helper section in `dist/index.html` (search the file for the closest existing analogue and place yours nearby).
- **Annotated tags only.** Use `git tag -a vX.Y.Z <commit> -m "..."` so the message ships with the GitHub Release.
- **Mobile is in scope.** Anything touching layout must work down to 320 px; `dist/index.html` has a `<480px` full-width sidebar fallback that should not regress.
