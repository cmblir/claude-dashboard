# Autonomous queue — 2026-05-01 (cycle 4: Ralph + Discord + failover)

User: "오케이 해당 순서대로 지금부터 전체적으로 자율모드 시작."
Reference: `decisions/2026-05-01-openclaw-nanoclaw-ralph-analysis.md` Tier-1+T2-1+T2-2.

Branch: `feat/v2.56-ralph-discord-failover`. Local --no-ff merge into main at end.

## [D1] Ralph engine — `server/ralph.py`
- Same-prompt loop with 4-fold termination: max-iter / completion-promise / cancel / budget-USD.
- Publishes to agent_bus on `ralph.<run_id>.*`. Persists each iteration to SQLite.
- Re-uses `execute_with_assignee` so any provider works.

## [D2] Ralph workflow node
- New node type `ralph` in `server/workflows.py`. Inspector form mirrors CLI flags.

## [D3] Ralph CLI — `tools/ralph_loop.py`
- `python3 tools/ralph_loop.py PROMPT.md --max 25 --completion DONE --budget-usd 5`
- Stdlib only. Ctrl+C → graceful cancel via the engine.

## [D4] Project Ralph recommender — `server/ralph_recommend.py`
- Synth PROMPT.md from CLAUDE.md + git log + TODO grep + last unfinished session.
- New API + projects-tab card.

## [D5] Discord bot — `server/discord_api.py`
- Bot token + interactions signature (ed25519 / nacl substitute via stdlib hashlib won't fit — use webhook events route instead).
- Falls back to gateway-less HTTP webhook posting for outbound; uses Slack-style polling for inbound where possible.

## [D6] Per-binding failover + daily budget cap
- Extend `_sanitize_binding` with `fallbackChain`, `budgetUsdPerDay`.
- Enforce in `dispatch()`. Surface remaining budget per binding.

## [D7] Tests + i18n + commit + LOCAL merge to main
- Suite must stay green. i18n verify 0 missing. `git merge --no-ff` into main locally; no `git push`.
