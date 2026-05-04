# Ralph Loop Task

Build features INCREMENTALLY. Complete and verify ONE phase fully before moving to the next. Do NOT skip ahead.

## Build Order (strict sequential)
PHASE 1 → PHASE 2 → PHASE 3 → PHASE 4 → PHASE 5

You MUST NOT start a phase until the previous phase Playwright tests all pass.

---

## PHASE 1: Workflow Engine Core
Goal: node-based execution like n8n.

Implementation requirements:
- Node interface with id, type, and execute method returning a Promise
- Sequential executor that runs nodes in order, passing output to input
- Per-node latency must be under 50ms (measure with performance.now)
- On any node throw: stop execution, run cleanup hook on all started nodes, clear session

Playwright tests required (file: tests/phase1-workflow.spec.ts):
- runs 10 nodes sequentially — assert all 10 execute in order
- per-node latency under 50ms — assert each node duration is under 50ms
- failure cancels workflow — inject failure at node 5, assert nodes 6 to 10 never run
- failure triggers cleanup — assert cleanup called on nodes 1 to 5, session state empty after

Phase 1 done when: npx playwright test tests/phase1-workflow.spec.ts exits 0

---

## PHASE 2: Auto-resume
Goal: workflow survives process kill.

Implementation requirements:
- Persist state to .workflow-state/SESSION_ID.json (NOT memory)
- Write state BEFORE node starts (status running) and AFTER (success or failed)
- Idempotency: re-running a success node is a no-op
- CLI: resume SESSION_ID resumes from last checkpoint
- Exponential backoff retry (max 3) on timeout

Playwright tests required (file: tests/phase2-resume.spec.ts):
- state persists to disk — assert JSON file exists after each node
- resumes after process kill — spawn workflow, kill at node 5, restart, assert resumes at node 5 not node 1
- completed nodes do not re-execute — assert nodes 1 to 4 skipped on resume
- interrupted node re-runs cleanly — assert node 5 starts from clean state, no partial side effects
- timeout retries with backoff — mock timeout, assert 3 retries with increasing delay
- CLI resume command works — exec resume command, assert workflow continues

Phase 2 done when: npx playwright test tests/phase2-resume.spec.ts exits 0

---

## PHASE 3: AI Provider Integration
Goal: chat with at least one provider working end-to-end.

Implementation requirements:
- Provider interface with name and sendMessage method
- At least ONE concrete provider implemented (Anthropic or OpenAI)
- Chat UI: input box, send button, message list, streaming display
- Settings: API key and model name persisted

Playwright tests required (file: tests/phase3-chat.spec.ts):
- user can send message and receive reply — type, click send, assert response appears
- streaming displays incrementally — assert message text grows over time
- settings persist across reload — set API key, reload page, assert still set
- invalid API key shows error — assert error UI visible

Phase 3 done when: npx playwright test tests/phase3-chat.spec.ts exits 0

---

## PHASE 4: Terminal Configuration (lazyclaw)
Goal: configure provider from terminal, opencode-style.

Implementation requirements:
- CLI: config set provider NAME
- CLI: config set api-key VALUE
- CLI: config set model NAME
- CLI: chat command for interactive chat in terminal
- Config stored in ~/.lazyclaw/config.json

Playwright tests required (file: tests/phase4-terminal.spec.ts):
Use Node child_process to spawn the CLI from within Playwright tests.
- config set persists to file — exec command, assert file content
- config get returns stored value — assert read-after-write
- chat command sends and receives — spawn chat, send input, assert output contains response

Phase 4 done when: npx playwright test tests/phase4-terminal.spec.ts exits 0

---

## PHASE 5: Final Integration
Goal: everything works together.

Playwright tests required (file: tests/phase5-integration.spec.ts):
- full e2e: configure, run workflow with AI node, kill, resume, complete
- Run all tests: npx playwright test (no filter) must exit 0
- Run tsc --noEmit must exit 0
- Run npm run lint must exit 0

Phase 5 done when: all 3 commands exit 0

---

## Iteration Protocol
At the START of every iteration:
1. Read .ralph-progress.md (create if missing) to see current phase
2. Run that phase test file: npx playwright test tests/phaseN-*.spec.ts
3. If it passes: update .ralph-progress.md to next phase, commit progress
4. If it fails: read the SPECIFIC failure, fix ONLY that failure, do not touch other phases

## Hard Rules
- NEVER write code for phase N+1 until phase N tests pass
- NEVER modify tests to make them pass — fix the implementation
- NEVER claim done without showing the Playwright test command output
- If a test file does not exist yet, CREATE IT FIRST before writing implementation (TDD)
- After every code change, run the current phase test file
- Each iteration must end with either more tests passing than before, or a documented blocker

## Stopping Rules
- After 15 iterations: if still on phase 1 or 2, output the BLOCKED promise tag with diagnosis in BLOCKERS.md
- When phase 5 verification commands all exit 0 in the SAME iteration: output exactly the DONE promise tag

## Anti-patterns
- Do NOT scaffold all 5 phases at once with placeholder code
- Do NOT skip writing tests
- Do NOT output the DONE promise tag based on "I implemented it" — only based on green test runs in this iteration
- Do NOT delete or skip failing tests
- Do NOT add features outside the 5 phases

## Completion Signal
When all phase 5 commands exit 0, output exactly this on its own line:
<promise>DONE</promise>

If blocked after 15 iterations, output exactly this on its own line:
<promise>BLOCKED</promise>