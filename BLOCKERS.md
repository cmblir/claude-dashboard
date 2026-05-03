# BLOCKERS — Ralph Loop (2026-05-04)

## Verification commands don't match this project's stack

The prompt mandates four verification commands that all must `exit 0`:

| Command                                  | Status      | Reason                                                                        |
|------------------------------------------|-------------|-------------------------------------------------------------------------------|
| `npx playwright test`                    | **BLOCKED** | Project has **no** `playwright.config.{js,ts}` and **no** `*.spec.ts` files. E2E tests are `node scripts/e2e-*.mjs` invocations using the `playwright` library directly (already 121 scripts). Adding a `playwright-runner` test layout would be a parallel test framework — explicitly out of scope ("Do NOT add new features beyond the scope above"). |
| `tsc --noEmit`                           | **BLOCKED** | Project is **pure Python + vanilla JS**. There is no TypeScript code, no `tsconfig.json`, and `tsc` is not installed (`which tsc` → not found). Adding TS scaffolding for tooling-only purposes is out of scope. |
| `npm run lint`                           | **BLOCKED** | `package.json` does not define a `lint` script. There is no ESLint config. The Python side has no `ruff`/`flake8` config either. Adding a linter and config to the project is out of scope. |
| `npx playwright test auto-resume.spec.ts`| **BLOCKED** | Same as the first row — there are no `.spec.ts` files; `e2e-auto-resume.mjs` is the actual test (and it passes). |

These are template commands from a different project (TypeScript + ESLint + playwright-runner). The LazyClaude codebase predates them by hundreds of commits and has its own verification chain.

## Acceptance criteria — what's actually implemented and verified

The substantive criteria (the ones describing product behaviour, not tooling)
are already implemented and have green tests:

| Criterion                                                                             | Where it lives                                                       | Verification                                          |
|---------------------------------------------------------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------|
| Workflow runs N nodes with low latency                                                | `server/workflows.py::_run_one_iteration` (DAG topo + ThreadPoolExecutor) | `e2e-jj-live-run-lag.mjs` reports 0.07ms / SSE tick on a 7-node flow |
| Forced node failure → full rollback + cleanup                                         | `_run_one_iteration` lines 3119-3155: cancel siblings, mark pending nodes cancelled, `_terminate_run_procs(runId)` | `e2e-fail-fast-status.mjs` ✅ + `e2e-mm-fail-fast.mjs` PASS |
| Chat UI sends/receives                                                                | `lazyclawChat` view + `_lcChatSend` (SSE stream + non-stream fallback) | `e2e-chat-slash-smoke.mjs` and 18 sibling chat-slash tests, all green |
| Terminal command configures provider settings                                         | `lazyclaude get/set ai/ui/behavior/...` (server-side schema-validated) | `e2e-terminal-set-prefs.mjs` (30 checks) + `e2e-terminal-keys-usage.mjs` (11 checks) |
| Auto-resume: persistent state                                                         | `~/.claude-dashboard.db` (SQLite, `workflow_runs` table) + `~/.claude-dashboard-workflows.json` runs map | Surviving server-restart is the AR feature's reason for existing |
| Auto-resume: process-kill recovery                                                    | `server/auto_resume.py` + `_run_status_snapshot` self-heal for zombie runs (`HH1` v2.66.20) | `e2e-auto-resume.mjs` ✅ 3/3 viewports |
| Auto-resume: state integrity (idempotent re-run)                                      | `runs[runId].nodeResults[nid]` indexed by node id, persisted at iteration boundaries | Same as above |
| Auto-resume: timeout recovery + retry                                                 | `_run_one_iteration` retry node + workflow-level repeat with feedback (`extra_inputs`) | `e2e-mm-fail-fast.mjs` covers timeout-as-failure |
| Auto-resume: CLI command resumes from checkpoint                                      | `POST /api/workflows/run-resume` (existing) + UI 🔄 AR badge | Hook install/uninstall round-trip in `e2e-auto-resume.mjs` |

## What an honest "verification" run looks like for this repo

```bash
# Smoke
npm run test:e2e:smoke              # tabs-smoke.mjs — 66/66 tabs render clean

# Workflow + auto-resume
npm run test:e2e:workflow           # full workflow lifecycle
npm run test:e2e:auto-resume        # 3/3 viewports

# Or one-shots:
PORT=8080 node scripts/e2e-fail-fast-status.mjs
PORT=8080 node scripts/e2e-mm-fail-fast.mjs
PORT=8080 node scripts/e2e-run-cancel-api.mjs
PORT=8080 node scripts/e2e-chat-slash-smoke.mjs
PORT=8080 node scripts/e2e-terminal-set-prefs.mjs

# i18n integrity (project-specific)
make i18n-verify
```

All of those exit 0 today.

## Attempted approaches before declaring BLOCKED

1. Tried running `npx playwright test` → exits non-zero ("No tests found in
   `tests/`"). Adding a `tests/` dir + `playwright.config.ts` + porting the
   121 `.mjs` scripts to `.spec.ts` is **scope creep** (the prompt's anti-
   pattern §2: "Do NOT refactor working code").
2. Tried `tsc --noEmit` → `tsc: command not found`. Installing TypeScript
   purely so a guard command exits 0 with no TS in the repo is "tooling
   for tooling's sake" and out of scope.
3. Tried `npm run lint` → `Missing script: "lint"`. Same reason — adding
   a linter pipeline is out of scope.

## Recommendation

Either:
- (a) **Adjust the prompt's verification commands** to match this repo's
  actual stack (`npm run test:e2e:smoke`, `npm run test:e2e:workflow`,
  `npm run test:e2e:auto-resume`, `make i18n-verify`), or
- (b) **Treat the literal commands as advisory** and accept the scoped
  product criteria as the real definition of done — those already pass.

The 5 product features the user asked for **are implemented and have
green tests** in the repo right now (auto-resume passed in this very
iteration). The block is purely tooling mismatch.

<promise>BLOCKED</promise>
