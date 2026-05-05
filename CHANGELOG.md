# Changelog

모든 의미 있는 변경은 이 파일에 기록된다. [Semantic Versioning](https://semver.org/lang/ko/) 을 따른다 — `MAJOR.MINOR.PATCH`.

기능 추가 시 규칙:
- **MAJOR** : 기존 워크플로우·스키마 파괴적 변경
- **MINOR** : 신규 탭/기능 추가 (하위 호환)
- **PATCH** : 버그 수정, UI 미세 조정, i18n 보강

기능 업데이트 시 (a) `VERSION` 파일 번호 bump, (b) 아래 표에 한 줄 추가, (c) `git tag v<버전>` 권장.

---
## [3.3.0] — 2026-05-05

**Daemon `/metrics`: cumulative `tokensTotal` and `costsByCurrency`.**

The metrics endpoint counted requests/cache; now it also accumulates
the token and money totals from every request that opted in to
`body.cost`:

```json
{
  "uptimeMs": 12345,
  "requestsTotal": 42,
  "requestsByStatus": { "200": 38, "404": 3, "429": 1 },
  "rateLimitDenied": 1,
  "cache": { "hits": 5, "misses": 8, "size": 8 },
  "tokensTotal": { "inputTokens": 12000, "outputTokens": 4500 },
  "costsByCurrency": { "USD": 0.0525, "EUR": 0.012 },
  "timestamp": "..."
}
```

### Per-currency keys (anti-silent-mix)
Heterogeneous fleets — USD-priced anthropic + EUR regional contracts —
shouldn't silently sum into a single number that's neither correct.
Costs are always keyed by currency, which means `costsByCurrency.USD`
is what costs USD totalled, not "all costs interpreted as USD."

### Fields always present (stable schema)
`tokensTotal` is `{inputTokens: 0, outputTokens: 0}` and
`costsByCurrency` is `{}` when no request has provided the data —
never null/undefined. Monitoring tooling sees a stable shape
regardless of which optional features the daemon has on.

### Six-decimal rounding
Same rounding as `costFromUsage` so a single per-request cost and
the cumulative total share precision. No drift from IEEE-754 over
many small additions.

### Tests
2 new phase 6 specs:
- 3 requests × (1000 in, 500 out) at $15/$75 per million → `tokensTotal`
  exactly `{3000, 1500}` and `costsByCurrency.USD` exactly `0.1575`
- request without body.usage/body.cost → `tokensTotal` stays
  `{0, 0}` and `costsByCurrency` stays `{}`

Suite: 249/249. tsc clean. Dashboard QA still 0/66.

---
## [3.2.0] — 2026-05-05

**`lazyclaw rates` subcommand for managing cost-card config.**

3.0.x cost wiring required hand-editing `cfg.rates` JSON. This adds
a first-class subcommand so users can write rate cards safely:

```bash
lazyclaw rates set anthropic/claude-opus-4-7 \
  --input 15 --output 75 --cache-read 1.5 --cache-create 18.75
lazyclaw rates list
lazyclaw rates delete anthropic/claude-opus-4-7
lazyclaw rates shape    # zero-filled reference template
```

### Validation
- Key MUST be `provider/model` form (slash required) — prevents
  someone from setting `claude-opus-4-7` and wondering why
  `costFromUsage` never finds it.
- `--input` and `--output` must be non-negative numbers (per million
  tokens). Negative or non-numeric → exit 2 with a usage hint.
- `--currency` defaults to `USD` when omitted; `--cache-read` and
  `--cache-create` are optional (provider-dependent).

### Anti-typo guarantee
The `provider/model` slash check catches the most common cost-card
mistake: shipping a card under just the model name and getting
silent zero-cost lookups forever. Now you get an immediate `usage`
hint instead.

### Tests
6 new phase 6 specs covering set/list round-trip, validation
rejection (non-numeric, negative, missing slash), idempotent delete
with `removed:true|false`, `shape` audit, and the `{}` default for
fresh configs.

Suite: 247/247. tsc clean.

---
## [3.1.0] — 2026-05-05

**Daemon: graceful shutdown with hard timeout + double-signal force exit.**

Production hardening. The previous shutdown awaited `server.close()`
forever — a hung stream could keep the process alive past any
orchestrator's deadline. Now SIGINT/SIGTERM run a graceful drain
**bounded** by `--shutdown-timeout-ms` (default 10000):

1. First signal:
   - Stop accepting new connections.
   - Wait up to `timeoutMs` for in-flight requests to finish.
   - On timeout: `server.closeAllConnections()` (Node ≥18.2),
     exit code 1.
   - On clean drain: exit code 0.
2. Second signal (orchestrator's "I mean it"):
   - Exit immediately with code 1.

Exit codes give orchestrators a useful signal: 0 = clean drain,
1 = forced or double-tap. Same convention as `systemd` graceful-stop
semantics.

### Logging
With `--log info` the shutdown emits structured records on stderr:
```
{"msg":"shutdown.begin","timeoutMs":10000}
{"msg":"shutdown.end","forced":false}
```
or `{"msg":"shutdown.force","reason":"second signal"}` on the
double-tap path.

### `gracefulShutdown` helper
Exported from `daemon.mjs` so callers wrapping a daemon manually can
reuse the same logic. Returns `{forced: boolean}`. Tested directly
with mock servers — no real socket needed.

### Tests
3 new phase 6 specs:
- close completes in time → `forced: false`
- close hangs → timeout fires within budget, `closeAllConnections`
  called, `forced: true`, elapsed within `< 500ms` even with timeout
  set to 50ms
- works on older Node lacking `closeAllConnections` — still resolves
  with `forced: true`, just no force-close to call

Suite: 241/241. tsc clean.

---
## [3.0.2] — 2026-05-05

**`lazyclaw agent --cost` for parity with daemon `body.cost`.**

The daemon could surface cost in 3.0.1; the CLI's one-shot couldn't.
Now it can:

```bash
$ lazyclaw agent --usage --cost "summarize this" 2> meta.log
[response on stdout]
$ cat meta.log
usage: {"inputTokens":1234,"outputTokens":567}
cost:  {"cost":0.0525,"currency":"USD","breakdown":{...}}
```

Both flags write to stderr (`stdout` stays pipe-clean). `--cost` is a
silent no-op without `cfg.rates` — same posture as the daemon, same
posture as `body.cost`. No surprise zero values.

`costFromUsage` is dynamically imported only when `--cost` is set, so
the agent's hot path doesn't pay the import cost when the flag is off.

### Tests
2 new phase 6 specs:
- `agent --cost` with rates populated + injected anthropic stub:
  stderr matches `/cost:.*"cost":0\.0525/`, stdout still has the
  reply
- `agent --cost` without rates: no `cost:` line on stderr, response
  still streams normally — no crash

Suite: 238/238. tsc clean.

---
## [3.0.1] — 2026-05-05

**Cost wiring: chat `/usage` and daemon `body.cost` surface dollar
amounts when rates are configured.**

3.0.0 shipped `costFromUsage()` as a pure helper. This iteration
wires it through the user-facing surfaces so callers don't have to
hand-roll the lookup.

### Chat
`/usage` now includes a `cost` block when (a) `runningUsage` has
accumulated real tokens AND (b) `config.rates` has a card matching
the *active* provider/model:

```json
{"messageCount": 4, "charsSent": 87,
 "tokens": {"inputTokens": 1234, "outputTokens": 567, ...},
 "cost":   {"cost": 0.063, "currency": "USD",
            "breakdown": {"input": 0.018, "output": 0.045, ...}}}
```

The active provider/model can change mid-chat via `/provider` and
`/model`, so the lookup uses the *current* values, not what was set
at chat start.

### Daemon
`POST /agent` and `POST /chat` now accept `body.cost: true`. When set
alongside `body.usage: true` AND `cfg.rates` has a matching card, the
response gains a `cost` field (non-stream) or emits an `event: cost`
SSE frame (stream).

Without `cfg.rates`, `body.cost` is silently a no-op — same posture
as `body.usage` without `--response-cache`. The schema stays stable;
optional features just don't populate optional fields.

### Tests
3 new phase 6 specs:
- daemon `POST /agent` with `usage:true, cost:true` + injected
  anthropic stub + `cfg.rates` populated → response carries both
  `usage` and `cost` blocks; cost arithmetic verified
  (1000 in × 15/1M + 500 out × 75/1M = $0.0525)
- daemon `body.cost:true` against mock provider with no rates: response
  has neither `usage` nor `cost` field; daemon doesn't crash
- chat `/usage` with `cfg.rates` + injected stub: same verification
  via the REPL JSON line

Suite: 236/236. tsc clean.

---
## [3.0.0] — 2026-05-05

**`costFromUsage()` helper for token → currency conversion. v3 mark.**

The 28-iteration cycle (v2.71.116 → v2.99.0) is closing out. v3.0.0
caps the run with the missing piece that completes the cost-tracking
story: a small helper that turns the normalized usage objects from
2.97.0/2.97.1 into actual money.

### `src/lazyclaw/providers/rates.mjs`
```js
import { costFromUsage } from './src/lazyclaw/providers/rates.mjs';

const rates = {
  'anthropic/claude-opus-4-7': {
    inputPer1M: 15.00, outputPer1M: 75.00,
    cacheReadPer1M: 1.50, cacheCreatePer1M: 18.75,
    currency: 'USD',
  },
};

const cost = costFromUsage(
  { provider: 'anthropic', model: 'claude-opus-4-7', usage: capturedUsage },
  rates,
);
// → { cost: 0.012345, currency: 'USD', breakdown: { input, output, cacheRead, cacheCreate } }
```

### Why no shipped rate card
Hardcoding prices sets up the library to silently lie the moment
provider pricing moves. Different teams negotiate different deals
(volume contracts, regional pricing, provider-managed proxies).
A single global default would be wrong for most users.

So:
- The library is **shape-only**: `costFromUsage(call, rates)` is pure
  arithmetic.
- `RATE_CARD_SHAPE` ships a zero-filled template with the right keys
  for the 5 supported providers — copy-paste, fill in your current
  prices, ship.
- Unknown `provider/model` keys return `null` (not zero) so callers
  can spot "we never registered a rate for this" and decide what to
  do — billing at $0 by default is dishonest.

### Six-decimal rounding
Token rates land in fractions of a cent at sub-USD prices (10000
tokens × $1/M = $0.01). We round to six decimals to (a) keep IEEE-754
noise out of test assertions and (b) preserve 1/100¢ precision for
batch-aggregation use cases.

### Tests
5 new phase 6 specs:
- anthropic 4-bucket breakdown: input + output + cacheRead + cacheCreate
  with exact rounded numbers
- openai shape (no cache fields): cache rates absent → cache buckets
  return 0, not undefined
- unknown provider/model: returns `null` not `{cost: 0}` (anti-silent-zero)
- bad inputs (`null`, missing rates): returns `null` rather than throwing
- `RATE_CARD_SHAPE` audit: every numeric field is exactly 0 — guarantees
  no shipped rate is "almost right" and easy to miss

Suite: 233/233. tsc clean.

### v3 closing note
This Ralph run delivered roughly 28 versions across:
- 5 concrete providers (mock, anthropic, openai, ollama, gemini)
- 3 composable provider decorators (retry, fallback, cache) with
  end-to-end ordering tests for their composition
- 3 workflow execution modes (sequential / parallel / persistent DAG)
- A daemon with three-layer security (Origin → auth → rate limit)
  proven correct in pairwise composition
- Structured logging, runtime metrics, full usage-token capture,
  cost calculation, portable export/import bundles
- Shell completion (bash + zsh), tab-friendly help, slash commands
  for mid-conversation skill/provider/model switching
- 233 tests, dashboard QA 0/66, all gates green

Out of scope (per §1.1): multi-channel inbox (WhatsApp / Signal /
iMessage / Telegram), voice / wake-word, mobile companion apps,
Live Canvas A2UI, Docker/SSH/OpenShell sandbox backends, daemon
graceful-shutdown timeout. These need real platform credentials,
mobile builds, or daemon-installation steps that don't fit the
autonomous-mode contract.

---
## [2.99.0] — 2026-05-05

**`config path` and `config edit` for shell-friendly config access.**

Two small CLI niceties that round out `config get/set/list/delete`:

### `lazyclaw config path`
Prints the resolved config.json location and nothing else, so shell
pipelines work cleanly:

```bash
cat $(lazyclaw config path)
diff <(lazyclaw config path) ~/.lazyclaw/config.json
```

### `lazyclaw config edit`
Opens the config file in `$LAZYCLAW_EDITOR` (then `$VISUAL`, then
`$EDITOR`, then `vi` as final fallback). After the editor exits, we
**re-read the file and run `JSON.parse` on it**. If the result is
malformed JSON we print the parse error and exit 1 — instead of
letting the user walk away thinking the edit landed and then
silently breaking every subsequent invocation.

The file is also auto-created with `{}` if it doesn't exist, so
opening a fresh install in `$EDITOR` doesn't surface as a "scratch
buffer the user accidentally saves as nothing."

### Tests
4 new phase 6 specs:
- `config path` prints the right path with no extra output
- `config edit` with `$LAZYCLAW_EDITOR=true` (no-op editor) → exit 0,
  file unchanged and still parseable
- `config edit` with a script that writes garbage to the file → exit 1
  with `invalid JSON` on stderr
- `config edit` against a fresh dir creates `{}` rather than failing
  on the missing file

Suite: 228/228. tsc clean.

---
## [2.98.1] — 2026-05-05

**Chat `/usage` slash now reports running token totals.**

The slash always reported `{messageCount, charsSent}` — useful but
local-only. Now it accumulates real provider usage across turns and
includes a `tokens` block when the provider emits `onUsage`:

```json
{"messageCount": 4, "charsSent": 87, "tokens": {
  "inputTokens": 1234,
  "outputTokens": 567,
  "totalTokens": 1801,
  "turnsWithUsage": 2
}}
```

`turnsWithUsage` ≤ `messageCount/2` because not every model call
emits usage (e.g., the mock provider doesn't). Lets the user spot
when their session has hit a provider that doesn't expose token
counts.

### Reset semantics
`/new` and `/reset` clear the accumulator alongside `messages` and
`charsSent` — start of a new conversation = start of a new bill.

### No `tokens` field when nothing emitted
The mock provider doesn't emit usage, so a session that ran entirely
against mock leaves the `tokens` field absent (not null, not zeros).
Tests pin this down: callers reading the `/usage` JSON know that
`tokens` being present means "the provider actually told us
something" and not "we attributed work to it without confirmation."

### Tests
3 new phase 6 specs:
- mock-only chat: `/usage` returns `{messageCount, charsSent}` with
  no `tokens` field
- anthropic-stub chat over 2 turns emitting usage per turn: `/usage`
  reports `inputTokens=10+20`, `outputTokens=5+10`, `turnsWithUsage=2`
- `/new` resets the accumulator: `/usage` after `/new` has no `tokens`
  field even though the previous turn had populated it

Suite: 224/224. tsc clean.

---
## [2.98.0] — 2026-05-05

**Usage capture: end-to-end CLI + daemon plumbing.**

The provider-level `opts.onUsage` callback shipped in 2.97.0/2.97.1.
This iteration plumbs it through to the user-facing surfaces.

### CLI: `agent --usage`
Prints the normalized usage totals to **stderr** (not stdout — keeps
the answer text pipe-clean) after the response streams:

```bash
$ lazyclaw agent --usage "summarize this" 2> usage.log
[response goes to stdout]
$ cat usage.log
usage: {"inputTokens":1234,"outputTokens":567}
```

Mock provider doesn't emit usage events, so `--usage` against mock
is silently a no-op (no crash, no spurious stderr).

### Daemon: `body.usage: true`
- `POST /agent` — when set, the response JSON gains a `usage` field:
  `{"reply": "...", "usage": {"inputTokens": ..., "outputTokens": ...}}`.
- `POST /chat` — same.
- Streaming mode (`stream: true`) emits an `event: usage` SSE frame
  before `event: done`.
- Without `body.usage`, the response shape is **identical** to before —
  no `usage` field, no `null`, no shape change. Verified by spec.

### Why opt-in
OpenAI requires `stream_options: {include_usage: true}` to emit usage
on the wire — that's an extra response chunk for every request. The
opt-in keeps the cost zero for callers who don't need the data.

### Tests
4 new phase 6 specs:
- `agent --usage` against mock: no crash, no spurious stderr (verifies
  the opt-in surface tolerates providers that don't emit usage)
- `agent --usage` against an anthropic stub that emits `{inputTokens, outputTokens}`:
  stderr contains the JSON line; stdout still has the response text
- daemon `POST /agent` with `body.usage:true` against mock: response
  body omits `usage` (mock doesn't emit), but doesn't crash
- daemon `POST /chat` default (no `body.usage`): no `usage` field on
  the response — guarantees backwards-compatible shape

Suite: 221/221. tsc clean.

---
## [2.97.1] — 2026-05-05

**OpenAI: usage capture via `opts.onUsage` (parity with anthropic).**

2.97.0 deferred OpenAI usage as out-of-scope; this iteration delivers
it. The Chat Completions API only emits usage on the stream when
`stream_options: { include_usage: true }` is set in the request body,
so the provider now adds that field **only when the caller provides
an `onUsage` callback** — preserving the wire shape for every
existing caller.

### Output shape
Normalized to mirror anthropic's `onUsage` payload but with the
fields OpenAI actually returns:

```js
{ inputTokens: 12, outputTokens: 3, totalTokens: 15 }
```

(Anthropic adds `cacheCreationInputTokens` / `cacheReadInputTokens`;
OpenAI doesn't expose cache fields in the same way, so we report
`totalTokens` instead.)

### Wire-shape guarantee
- Without `onUsage` → request body has no `stream_options` field at
  all (verified by a spec). Existing callers see no behavior change.
- With `onUsage` → `stream_options: {include_usage: true}` is added.

### Tests
2 new phase 6 specs:
- happy path: SSE includes a usage frame; callback fires with normalized
  shape; request body contains `stream_options.include_usage: true`
- opt-in guarantee: no `onUsage` → no `stream_options` on the wire

Suite: 217/217. tsc clean.

Now both real-network providers expose normalized usage, closing the
parity gap §1.1 flagged in 2.97.0.

---
## [2.97.0] — 2026-05-05

**Anthropic: usage totals surfaced via `opts.onUsage` callback.**

The Messages API splits usage across two SSE events:
- `message_start` carries `message.usage` with `input_tokens`,
  `cache_creation_input_tokens`, `cache_read_input_tokens`
- `message_delta` carries the final `usage.output_tokens`

The provider already parsed the rest of the stream; usage was being
discarded. Now they get accumulated and emitted once via
`opts.onUsage` right before the iterator returns on `message_stop`:

```js
let usage = null;
for await (const chunk of anthropic.sendMessage(messages, {
  apiKey, model,
  onUsage: u => { usage = u; },
})) {
  process.stdout.write(chunk);
}
console.log(usage);
// { inputTokens: 1234, outputTokens: 567,
//   cacheCreationInputTokens: 500, cacheReadInputTokens: 0 }
```

### Why this matters
- Cost tracking: input × input-rate + output × output-rate
- Prompt-caching ROI: `cacheReadInputTokens` shows how much of the
  prefix actually hit the cache vs paid full input cost
- Budget enforcement: callers can shed load when running totals
  cross a threshold

### Back-compat
Missing callback is a no-op — existing callers see no behavior
change. Malformed `message_start` / `message_delta` JSON is
swallowed at parse time, same posture as the rest of the SSE
parser.

### Tests
2 new phase 6 specs:
- happy path: `message_start` (input + cache fields) + `message_delta`
  (output) → callback fires once with all four fields populated
- back-compat: missing `onUsage` is a no-op; iterator still yields
  the text and completes normally

Suite: 215/215. tsc clean.

Out of scope: OpenAI usage capture. The Chat Completions API only
emits usage in the stream when `stream_options: {include_usage: true}`
is set in the request body, and even then the field shape varies
between endpoint versions. Adding that needs a careful contract
design and another round of tests; deferring rather than scaffolding.

---
## [2.96.0] — 2026-05-05

**Provider tracing: decorator transitions land in the daemon log at debug level.**

The daemon's structured logger (2.93.0) covered access lines but the
decorator stack (retry / fallback / cache) was opaque. With
`--log debug`, the daemon now emits one debug record per transition:

- `provider.retry` — `{attempt, retryAfterMs, errorCode}` per retry
  attempt
- `provider.fallback` — `{from, to, errorCode, errorMsg}` when a
  chain link transitions to the next
- `cache.hit` / `cache.miss` — `{provider, keyHash, size}` (keyHash
  truncated to 12 chars; full hash is overkill for a log)

These ride on the existing decorator hooks (`onRetry`, `onFallback`,
new `onHit` / `onMiss` on the cache wrapper). Default level is `info`,
so production deployments don't pay the noise unless they set
`--log debug` to diagnose a specific issue.

### Cache wrapper API expansion
`withResponseCache(provider, { onHit, onMiss })` — both fire once per
`sendMessage` call with the same `keyHash` so a caller can correlate
hit/miss events back to a specific cache key.

### Composition order
Reminder: `cache → fallback → retry` (innermost to outermost). So:
- A cache hit fires `cache.hit` and short-circuits — no
  `provider.fallback` or `provider.retry` log lines for that request.
- A cache miss + fallback transition fires `cache.miss` then
  `provider.fallback` (assuming the request was configured with both).
- Retry events appear only when the *full chain* fails — so when both
  retry and fallback are configured, retry events imply both providers
  in the chain hit `RATE_LIMIT`.

### Tests
3 new phase 6 specs:
- `withResponseCache` `onHit`/`onMiss` callbacks fire once per call
  with `{keyHash, size}` shape and the right ordering across 1 miss + 2 hits
- daemon retry-only path: `RATE_LIMIT` from primary, `body.retry: {attempts: 2}`,
  no fallback → 2 `provider.retry` records with `attempt=1` and `attempt=2`,
  third throw exhausts → 429
- daemon fallback-only path: primary RATE_LIMITs, alt serves → exactly
  one `provider.fallback` record with `from='mock'`, `to='anthropic'`,
  `errorCode='RATE_LIMIT'`

Suite: 213/213. tsc clean.

---
## [2.95.3] — 2026-05-05

**Test coverage: gate ordering for the security stack — pinned down.**

The README documents Origin → auth → rate-limit and a test confirms
Origin-before-auth (a forbidden Origin gets 403 with no
`WWW-Authenticate` header). Two more orderings remained implicit;
this fills them in:

1. **Auth runs before rate limit.** With both `--auth-token` and
   `--rate-limit 2` set, ten unauthenticated requests + ten
   missing-auth requests all 401 without spending a token. A
   subsequent authenticated burst still gets the full bucket and
   429s only on the 3rd legitimate request.

   Why this matters in production: if rate-limit ran first, an
   attacker could DoS the legitimate user's budget with junk
   requests. Auth-first means anonymous traffic never touches the
   limiter — the budget is per *authenticated identity*, not per IP.

2. **Origin runs before rate limit.** Symmetric: ten foreign-Origin
   requests all 403 without spending a token. CLI/script callers
   (no Origin header) still get the full bucket. So a malicious
   browser page on `evil.example` cannot exhaust the legitimate
   user's budget by hitting 127.0.0.1 cross-origin.

These two tests pin down the contract the README asserts. Together
with the existing Origin-before-auth test, the gate ordering is
fully covered: an attacker can't get *anywhere* into the daemon
without first passing every gate, and each gate is both correct in
isolation and correct in composition.

No production code changes. Suite: 210/210. tsc clean.

---
## [2.95.2] — 2026-05-05

**Docs: README catches up on the post-2.82.2 surface (§4.5).**

A lot landed without README updates between 2.82.2 and now:

- chat slashes: `/skill`, `/provider`, `/model`; SIGINT-aborts-turn behavior
- agent flags: `--provider`, `--model`, `--fallback`
- daemon: `--allow-origin`, `--rate-limit`, `--response-cache`, `--log`
- daemon endpoints: `/metrics`, `GET/PUT/DELETE /skills/<name>`,
  `body.cache`, `body.fallback`
- `lazyclaw` subcommands: `export`, `import`, `help`, `completion`,
  `sessions export`, `skills install --from-url`
- providers: `ollama`, `gemini` (now 5 total)
- workflow: `runParallel`, `runPersistentDag`, `run --parallel`,
  `run --parallel-persistent`
- composable decorators: `withRateLimitRetry`, `withFallback`,
  `withResponseCache`

The "🐚 LazyClaw CLI" section now reflects all of this:

- Conversation table mentions `/skill`, `/provider`, `/model`,
  Ctrl+C-aborts-turn, `--fallback` flag, `--provider`/`--model` overrides
- Inspection table adds `sessions export`, `--from-url` for skills,
  `export`/`import`, `help`/`completion`, `run --parallel-persistent`
- HTTP daemon section: full security gate ordering (Origin → auth →
  rate limit), every endpoint listed including `/metrics` and the
  skill CRUD endpoints, body fields for `retry`/`fallback`/`cache`,
  observability via `--log` and `/metrics`
- Providers section: 5 concrete providers with capability summaries,
  the three `withX` decorator wrappers with their composition semantics

Version badges (en/ko/zh) bumped from v2.79.4 to v2.95.1.

No code changes. Suite still 208/208.

---
## [2.95.1] — 2026-05-05

**`lazyclaw run --parallel-persistent` exposes `runPersistentDag`.**

The engine landed in 2.95.0; now the CLI flag wires it up. Three
explicit modes:

| Flag | Engine | Resumable | Concurrent |
|---|---|---|---|
| (none) | `runPersistent` | yes | no — sequential |
| `--parallel` | `runParallel` | no — in-memory | yes — by topo level |
| `--parallel-persistent` | `runPersistentDag` | yes | yes — by topo level |

State files live at `<--dir>/<session-id>.json` for both resumable
modes; running `lazyclaw resume <id> <wf>` continues from the last
checkpoint regardless of which mode wrote it.

### Tests
2 new phase 6 specs:
- `--parallel-persistent` runs a 4-node diamond, exits 0, JSON output
  has `mode: 'parallel-persistent'`, state file landed at the
  configured `--dir`, `merge.output` reflects fan-in inputs
- end-to-end resume: workflow file flips behavior on a sentinel-file
  attempt counter — first invocation fails at b (exit 1), second
  invocation skips a, retries b (succeeds), runs c. `executedNodes` on
  the second call is `['b', 'c']`.

Suite: 208/208. tsc clean.

---
## [2.95.0] — 2026-05-05

**Workflow: `runPersistentDag` — DAG with checkpoint-and-resume.**

Until now LazyClaw had two non-overlapping workflow engines:
- `runPersistent` (phase 2): sequential, persists state to JSON, resumable.
- `runParallel` (phase 5): topological levels, in-memory only.

Real n8n-style workflows want both: parallel level execution AND
resume after a process kill. `runPersistentDag` is that union.

### API
```js
import { runPersistentDag } from './src/lazyclaw/workflow/persistent.mjs';

const r = await runPersistentDag([
  { id: 'a',     deps: [],            execute() {...} },
  { id: 'b',     deps: ['a'],         execute(input) {...} },
  { id: 'c',     deps: ['a'],         execute(input) {...} },
  { id: 'merge', deps: ['b','c'],     execute(input) {...} },
], { sessionId: 'demo', dir: '.workflow-state' });
```

### Resume semantics
- `success` nodes: skipped on resume; their outputs feed into fan-in
  nodes that depend on them.
- `running` nodes (= a process killed mid-level): demoted to `pending`
  on the next start; the level retries.
- `failed` nodes: re-attempted on the next run. Idempotency is the
  caller's responsibility (same as `runPersistent`).
- `pending` nodes never started; they run normally.

### Cycle detection
Inherited from `topologicalLevels` (Kahn's algorithm). Cycle → exit
before any node executes; the state file is never written.

### Failure semantics
First failure in level N stops scheduling N+1. Successful nodes within
the failing level still get their state persisted before the function
returns — so a partial recovery on resume sees everything that
actually succeeded.

### Subtle test-runner bug found and fixed
`runPersistentDag` originally used `await import('./executor.mjs')` so
the executor wouldn't load when only the sequential path was used.
Under `@playwright/test`, that tripped tsx's CJS conversion path
when phase 1 had already loaded executor.mjs statically — the dynamic
re-import surfaced as `exports is not defined in ES module scope`.
Switched to a top-level static import. Cost is one extra import on
boot for callers who never use the DAG path; benefit is a stable
loader contract.

### Tests
4 new phase 2 specs:
- 4-node diamond runs to completion; merge sees `{b, c}` outputs;
  state file has all four `success` records
- resume after a flaky failure: first run fails at b, state shows
  `b: failed`, c untouched. Second run skips a, retries b (succeeds
  this time), executes c. `executedNodes` is `['b', 'c']`.
- cycle detected before any node runs (no state file written)
- hand-crafted state with `b: running` (mimicking a SIGKILL): on
  resume, b is demoted to pending and retries; a (success) is skipped

Suite: 206/206. tsc clean.

---
## [2.94.0] — 2026-05-05

**Daemon: `GET /metrics` for runtime observability.**

Counters track every request and the access-log code already had the
hook point. This iteration exposes them as JSON:

```json
{
  "uptimeMs": 12345,
  "requestsTotal": 42,
  "requestsByStatus": { "200": 38, "404": 3, "429": 1 },
  "rateLimitDenied": 1,
  "cache": { "hits": 5, "misses": 8, "size": 8 },
  "timestamp": "2026-05-05T..."
}
```

`cache` is `null` unless `--response-cache` is on; `rateLimitDenied`
is `0` unless `--rate-limit` is set — but the counter exists either
way, so monitoring tooling sees a stable schema regardless of the
daemon's optional features.

### Counters fire on res.close
The same hook point as the access log, so middleware short-circuits
(403 / 401 / 429) get counted. This means `requestsByStatus["429"]`
and `rateLimitDenied` *both* increment for a denied request — one
records the HTTP outcome, the other the policy decision. The two are
useful in different observability contexts (alerting on 429s vs
charting cap saturation).

### Robustness fix found by the new tests
The metrics hook crashed when unit tests drove the handler with a
stub `res` that lacked `once`. Fixed by guarding `typeof res.once === 'function'`
before attaching — exercise without an event-emitter surface no
longer breaks.

### Tests
3 new phase 6 specs:
- `/metrics` without optional features: counts 200s + a 404, reports
  cache:null, rateLimitDenied:0
- `/metrics` with `--rate-limit 2`: third request 429s; the counter
  registers `rateLimitDenied >= 1`
- `/metrics` with `--response-cache`: 1 miss + 2 hits → `cache.hits=2,
  cache.misses=1, cache.size>=1`

Suite: 202/202. tsc clean.

---
## [2.93.0] — 2026-05-05

**Structured logging + daemon access log (opt-in).**

Plain stderr printlns are fine for a CLI; once the daemon is taking
remote requests with auth + rate limits, a structured log makes
observability tractable.

### `src/lazyclaw/logger.mjs`
80-line module, no transitive deps. JSON-line output, level-gated
(`debug` < `info` < `warn` < `error`). `createLogger({level, sink, base, now})`
returns a logger; `logger.child({extraBase})` derives a child without
mutating the parent. Default sink writes to `process.stderr`; tests
inject their own.

### Daemon access log
`lazyclaw daemon --log info` (also `LAZYCLAW_LOG_LEVEL`) emits one
JSON line per request on stderr:
```json
{"ts":"2026-05-05T12:34:56.789Z","level":"info","msg":"access","method":"GET","path":"/version","status":200,"durationMs":3,"remote":"127.0.0.1"}
```

The line lands on `res.close` so it captures the actual final status
even when middleware (Origin gate, auth, rate limit) short-circuits.
We hook `res.writeHead` to capture status without intercepting the
body — zero overhead per chunk.

### Bound-URL JSON
Now includes `log: <level>|null` so callers can see whether logging
is enabled.

### Why JSON-line and not a real logger lib (pino/winston)
A single dep would dwarf the entire CLI. JSON-line is the de-facto
observability format — `jq` and every log shipper ingest it natively.

### Tests
4 new phase 6 specs:
- level gate: `warn` suppresses `debug`+`info`, allows `warn`+`error`
- `child()` merges base fields without mutating parent (verified via
  field appearance in child output and absence from sibling parent
  output)
- `makeHandler` with logger: GET /version emits one access record
  with `msg:'access'`, method, path, status, durationMs, remote
- CLI integration: `--log info` produces JSON access lines on stderr;
  one matching record per HTTP request

Suite: 199/199. tsc clean.

---
## [2.92.2] — 2026-05-05

**Test coverage: decorator-stack composition (cache + fallback + retry).**

The three decorators have unit tests each, but no test verified that
they actually compose without surprising each other. This iteration
fills that gap with three integration specs that pin down the
contract:

1. **Cache hit short-circuits both fallback and retry.** Primary serves
   on first call (1× underlying invocation); two more identical calls
   are served from cache; fallback never reached, retry never invoked.
   Verified via call counters.

2. **Cache miss falls through to fallback** when the primary fails
   pre-stream. The fallback delivers; importantly, the primary's
   *failure* did **not** populate the primary's cache slot. A second
   call still tries the primary again — the cache wasn't poisoned.

3. **Retry exhausts on primary `RATE_LIMIT`, then fallback delivers.**
   Initial call + 2 retries = 3 attempts before the bubbled error
   reaches the fallback wrapper, which then serves successfully.
   This validates the "retry wraps each chain link individually"
   composition story.

These three together cover the realistic production flows: re-asks
hit the cache, transient outages route around the primary, and rate
limits don't blow the user's budget on the primary if alternates
exist.

No production code changes. Suite: 195/195. tsc clean.

---
## [2.92.1] — 2026-05-05

**Daemon: wire `withResponseCache` through `resolveProvider`.**

The cache decorator shipped in 2.92.0 but wasn't reachable from the
HTTP surface. Now:

- `lazyclaw daemon --response-cache` allocates a per-handler shared
  cache map. Without the flag, no cache state exists.
- Per-request opt-in: `POST /agent` and `POST /chat` honor
  `body.cache: true` (or an object — currently treated as `true`).
- The cache wraps the BASE provider before fallback / retry so a
  cache hit short-circuits both — a hit is itself a successful
  response, no need to fail-and-retry through alternates.

### Composition order
Innermost to outermost: cache → fallback → retry. So:
- A cache HIT skips fallback and retry entirely.
- A cache MISS goes through fallback → retry as usual; a successful
  response from any chain member populates the cache for the
  primary's key (we cache by the primary's identity).

### Tests
2 new phase 6 specs:
- `--response-cache` + `body.cache: true` — two identical requests
  return the same reply (the cache served the second one)
- without `--response-cache`, `body.cache: true` is a silent no-op:
  the daemon doesn't crash, doesn't leak state, just ignores the flag

Suite: 192/192. tsc clean.

---
## [2.92.0] — 2026-05-05

**`withResponseCache`: provider decorator for memoizing identical calls.**

A wrapper, not a per-provider option — same shape as `withRateLimitRetry`
and `withFallback`. Caching is policy (caller decides how aggressive),
not transport. The concrete providers stay pure async iterators over a
single call.

### Use case
Development workflows: re-running the same prompt during agent design
shouldn't keep burning tokens. Now:

```js
import { withResponseCache } from './src/lazyclaw/providers/cache.mjs';
import { PROVIDERS } from './src/lazyclaw/providers/registry.mjs';

const cached = withResponseCache(PROVIDERS.anthropic, {
  maxEntries: 256,
  ttlMs: 60 * 60 * 1000,   // 1 hour
});
```

Identical messages + model + cache-relevant opts hit the cache.
`signal`, `fetch`, `onThinking`, `onToolUse` are deliberately not
part of the key — they don't change the response.

### Hash stability
`stableStringify` sorts object keys before serialization so
`{a:1,b:2}` and `{b:2,a:1}` hash identically. Plain `JSON.stringify`
respects insertion order which would cause spurious cache misses
when callers built the opts object differently between calls.

### Eviction
- **TTL** wins over LRU: an entry past `ttlMs` is dropped before it
  could be served as a hit.
- **LRU**: `maxEntries` defaults to 256; on insert, the oldest entry
  is evicted to make room.
- **Touch-on-hit** so frequently-asked prompts stay alive.

### Failure isolation
Mid-stream errors do **not** poison the cache. The buffer lands in
the cache only when the source iterator completes successfully —
errors and aborts let the next caller try fresh.

### Inspection
`cached.cacheStats()` returns `{ hits, misses, size, maxEntries }` —
useful for benchmarks and dashboards. `cached.cacheClear()` empties
the cache and resets counters.

### Tests
6 new phase 6 specs:
- second identical call replays from memory; underlying `calls = 1`,
  `hits = 1`, `misses = 1`
- different message bodies miss separately; key-order independence
  verified by hashing two different opts orderings and comparing
- TTL eviction: pre-TTL hit, post-TTL miss (injected `now()`)
- failed mid-stream call doesn't poison; second call gets a fresh
  underlying invocation that completes cleanly
- LRU eviction at `maxEntries=2`: 'a' evicted by 'c', re-asking 'a'
  misses
- `hashKey` produces identical hashes across reordered opts properties

Suite: 190/190. tsc clean.

---
## [2.91.0] — 2026-05-05

**Daemon: per-IP rate limit (token-bucket, opt-in).**

Defense-in-depth alongside the auth-token gate (2.82.1) and Origin
allowlist (2.83.0). When the daemon is exposed beyond loopback —
or when an authenticated client misbehaves — a token-bucket cap
keeps any single remote from monopolizing the host.

### CLI
- `lazyclaw daemon --rate-limit 60` → 60 requests / 60 s sustained,
  burst-tolerant via the bucket
- Default off (no flag → unlimited, the historical loopback default)
- Bound-URL JSON includes `rateLimit: {capacity, refillPerSec}` so
  test/script callers can see the active policy without inspecting
  the daemon process

### Why token bucket and not fixed-window
A fixed window of N requests/minute allows a 2N burst at the boundary
(last second of window K + first second of window K+1). Token-bucket
math (refill on access + deduct one) smooths bursts without that edge.
Two arithmetic ops per request, no per-request log entries to truncate.

### Ordering
Origin → auth → rate limit. The bucket runs *after* auth so the
budget is per authenticated identity rather than per IP-pretending-
to-be-someone-else; an unauthenticated request never costs a token.
Forbidden Origins also never cost a token — short-circuited at the
front gate.

### Memory bound
Stale buckets are evicted on access (a bucket abandoned past its
refill-to-capacity time would have refilled to capacity anyway). No
background sweep needed. Per-key state is `{tokens, last}` — 16
bytes plus the key.

### Tests
4 new phase 6 specs:
- token bucket: capacity exhaustion → `allowed:false` with
  `retryAfterMs > 0`; advance time → bucket refills; verified with
  injectable `now()` so the test runs offline
- separate keys have independent buckets (alice exhausted, bob still OK)
- daemon `makeHandler` with `rateLimit` returns 429 + `Retry-After`
  header after capacity exhaustion (handler-level test, no real
  network)
- CLI `--rate-limit 2` integration: third request 429s, header set,
  bound-URL JSON exposes the policy

Suite: 184/184. tsc clean.

---
## [2.90.0] — 2026-05-05

**`lazyclaw run --parallel` exposes `runParallel` in the CLI; parser
gains a boolean-flag allow-list.**

### `lazyclaw run --parallel <session-id> <workflow.mjs>`
Executes the workflow as a DAG via `runParallel` instead of the
default sequential path. The workflow file exports `nodes` with
optional `deps: string[]`; topologically independent nodes run
concurrently in their level. The parallel mode does **not** persist
state (`runPersistent` is the resumable path; `--parallel` is a
one-shot DAG run).

### Boolean-flag allow-list (parser fix)
Until now `parseArgs` couldn't tell `--parallel` (boolean) from
`--port` (value-taking) and assumed any non-`--` next arg was the
flag's value. `lazyclaw run --parallel demo wf.mjs` would set
`flags.parallel = 'demo'` and silently lose the session id.

Added a `BOOLEAN_FLAGS` set listing every flag that's a presence-only
signal:
```
parallel, once, non-interactive, include-secrets, include-sessions,
overwrite-skills, no-overwrite-config, import-sessions, show-thinking,
help, version
```
These never consume the next arg even when one's available — both
`--parallel demo wf.mjs` and `demo wf.mjs --parallel` work now.

### Tests
2 new phase 6 specs (one each ordering):
- `run --parallel demo wf.mjs` — flag *before* positionals — DAG
  executes, fan-out level finishes in <500 ms (sequential floor 240+
  per node × 3 = 720+ ms)
- `run demo wf.mjs --parallel` — flag *after* positionals — same DAG
  fails on a deliberate cycle, exit 1, error mentions cycle

Suite: 180/180. tsc clean.

---
## [2.89.0] — 2026-05-05

**Workflow: `runParallel` for DAG-with-deps execution (n8n-style).**

Until now the executor was strictly sequential. New `runParallel`
takes nodes that declare `deps: string[]` and runs each topological
level concurrently — a fan-out / fan-in graph completes in the time
of its longest path, not the sum of all nodes.

### API
```js
import { runParallel } from './src/lazyclaw/workflow/executor.mjs';

const r = await runParallel([
  { id: 'fetch',   deps: [],            async execute() { return await loadCsv(); } },
  { id: 'classify',deps: ['fetch'],     async execute(input) { /* input = {fetch: rows} */ } },
  { id: 'embed',   deps: ['fetch'],     async execute(input) { /* same input shape */ } },
  { id: 'merge',   deps: ['classify','embed'], async execute(input) {
      // input = { classify: ..., embed: ... }
  } },
]);
```

A fan-in node sees `{ depId: depOutput }` so it can branch on every
predecessor's result without rebuilding the lookup itself.

### Topological grouping
`topologicalLevels(nodes)` is exported separately for callers who
just want the schedule (e.g., to render a workflow visualization).
Returns `{ levels, leftover }` — a non-empty `leftover` indicates a
cycle or unreachable nodes.

### Failure semantics
- One node failing in level N stops scheduling level N+1.
- Cleanup runs on every node that *started* (any prior level), via
  `Promise.allSettled` — same isolation as `runSequential`.
- Session is cleared, `failedAt` reports the first failure within
  the failing level (deterministic but `Promise.all` order, not
  declaration order).

### Cycle detection
Built into Kahn's algorithm: any node never enters the frontier when
a cycle traps it. `runParallel` refuses to run the graph and returns
`{success: false, error: 'workflow has a cycle or unreachable nodes: ...'}`.

### Tests
6 new phase 1 specs:
- `topologicalLevels` produces `[[a], [b,c], [d]]` for a diamond
- `topologicalLevels` reports `leftover` for a cycle
- `runParallel`: 3 independent 100 ms nodes finish in <220 ms wall
  (sequential floor is 300+)
- `runParallel`: fan-in receives `{a: 'fromA', b: 'fromB'}`
- `runParallel`: failure in level 0 stops level 1; cleanup ran for
  every started node, none for the never-scheduled ones
- `runParallel`: cycle detected, refuses to run, error mentions cycle

Suite: 178/178. tsc clean.

---
## [2.88.1] — 2026-05-05

**Chat: Ctrl+C aborts the current turn instead of killing the process.**

Long replies were impossible to interrupt without losing the whole
chat session — Ctrl+C terminated the CLI. Now SIGINT during a stream
aborts only that turn; the REPL keeps running so the next prompt
still works.

### Behavior
- During a stream: SIGINT calls `AbortController.abort()` on the
  per-turn signal, the provider stops yielding, the partial reply is
  discarded (we don't append a half-reply to the message history —
  the model would see it as a complete reply on the next turn), and
  the REPL prints `^C interrupted — prompt is back`.
- Outside a stream (waiting at the prompt): SIGINT still terminates
  the process (default behavior). The handler is installed only for
  the duration of the stream and removed on the way out via `finally`.

### Mock provider also honors the signal now
Symmetry with the other providers — checked at the top of every chunk
yield. Tests rely on this so the abort case is reproducible offline.

### Tests
1 new phase 6 spec:
- 200-char prompt → ~1s mock stream
- spawn child, write prompt, wait 150 ms, send SIGINT
- assert: process didn't die (next stdin write still produces output),
  the interrupted notice landed, the *full* long mock-reply is NOT in
  output (proving the stream actually aborted), follow-up message gets
  its own reply, exit code 0 on `/exit`

Suite: 172/172. tsc clean.

---
## [2.88.0] — 2026-05-05

**Portable bundles: `lazyclaw export` / `lazyclaw import`.**

A bundle is a JSON object with `config + skills + sessions`. Pipe it
to wherever you want — disk, scp, gist, encrypted vault — and apply
it on another machine with `import`. Useful for backing up before a
clean reinstall, syncing between machines, or sharing a curated skill
set with a teammate.

### Export
```bash
lazyclaw export > backup.json                   # default: redacted key, metadata-only sessions
lazyclaw export --include-secrets > full.json   # MY-laptop-to-MY-drive only
lazyclaw export --include-sessions > talks.json # full turn content
```

Defaults are conservative because a bundle on someone else's laptop
shouldn't carry your API keys. The default redacts `api-key` to
`***REDACTED***`. The placeholder is recognised on import and dropped
rather than written.

### Import
```bash
lazyclaw import < backup.json                   # stdin
lazyclaw import --from backup.json              # path
lazyclaw import --overwrite-skills < new.json   # replace existing skills
lazyclaw import --import-sessions < talks.json  # also create sessions
```

Conflict policy:
- **Config keys** overwrite by default (`--no-overwrite-config` to
  preserve existing values when both define the same key).
- **Skills** skip on existing-name by default (`--overwrite-skills`
  to replace).
- **Sessions** are NEVER overwritten — only created when the id is
  free *and* `--import-sessions` is set. We don't want to clobber
  active conversations.
- **Redacted api-keys** are dropped, never written.
- **Unknown `bundleVersion`** → exit 2 (forward-compat guard).

### Tests
7 new phase 6 specs:
- export redacts api-key; raw secret never appears anywhere in output
- `--include-secrets` opts back in
- `--include-sessions` inlines turn content; default keeps metadata
- import via `--from` applies config + skills; redacted placeholder
  is dropped, not written to disk
- import skips existing skills (default); `--overwrite-skills` replaces
- unknown `bundleVersion` → exit 2 with the expected version in stderr
- end-to-end round-trip: export from one config dir, import via stdin
  into a fresh dir, config + skill content match

Suite: 171/171. tsc clean.

---
## [2.87.0] — 2026-05-05

**Daemon: `PUT` and `DELETE /skills/<name>` for HTTP skill management.**

The read endpoints (`GET /skills`, `GET /skills/<name>`) shipped in
2.85.1; this fills out the CRUD surface so a remote tool can write
and remove skills without shelling into the host.

### `PUT /skills/<name>`
- Body: raw markdown (Content-Type ignored — we don't dictate)
- Validates the name **before** reading the body so a bogus path-
  traversal name fails fast and we don't waste bandwidth
- 1 MiB body cap; oversize → 400 + connection destroyed
- Distinct status codes:
  - `201 Created` on first write
  - `200 OK` on overwrite (with `replaced: true` in the body)
  Caller can branch on status if they care about idempotency vs newness.

### `DELETE /skills/<name>`
- Idempotent: 200 whether the file existed or not
- Body reports `removed: true|false` so callers that *do* care can branch
- Same `skillPath` validation as `GET`/`PUT` — dotfiles and traversal
  names rejected with 400

### Authorization model
When `--auth-token` is set, both endpoints require Bearer auth (the
existing gate runs before the route resolver). The Origin gate runs
even before auth, so a browser CSRF attempt to `PUT` a skill is
rejected with 403 before any read of the request body.

### Tests
3 new phase 6 specs:
- PUT first-write 201, then PUT same name → 200 with `replaced: true`,
  body content read back to verify overwrite landed
- PUT `.hidden` → 400 + skills/ directory remains empty (no leaked
  write under any name)
- DELETE existing → `removed: true`; DELETE again → `removed: false`,
  both 200

Suite: 164/164. tsc clean.

---
## [2.86.1] — 2026-05-05

**Chat slashes: `/provider` and `/model` for mid-chat switching.**

The conversation history sticks; the next user message goes to the
new provider/model with the existing context. No restart needed.

### Behavior
- `/provider <name>` — switch the active provider. Unknown name →
  error in stdout, prior provider kept.
- `/provider` (no arg) — print the current provider name.
- `/model <name>` — update the active model.
- `/model anthropic/claude-opus-4-7` — unified form switches both
  provider and model in one shot.
- `/model` (no arg) — print the current model.
- `/status` now reflects the *active* (mutable) provider/model rather
  than the on-disk config — accurate after any switch.

### Why mid-chat switching matters
Common workflow: start with a cheap fast model for ideation, switch
to the heavyweight model once you've nailed down what you want.
Previously you'd `/exit`, edit config, and `chat` again — losing the
context. Now the conversation history rides with you.

### Note
The on-disk `config.json` is **not** updated by the slashes — switches
are session-scoped. To persist, run `lazyclaw config set provider X`.

### Tests
4 new phase 6 specs:
- `/provider <known>` switches; verified by triggering INVALID_KEY
  on a switch to anthropic-without-key (proves mock no longer active)
- `/provider` (bare) prints current name
- `/provider <unknown>` errors and keeps prior provider (subsequent
  message still gets a mock-reply)
- `/model some-model` and `/model openai/gpt-4.1` — both update
  active state, the second also flips provider — verified via
  `/status` JSON snapshots before and after

Suite: 161/161. tsc clean.

---
## [2.86.0] — 2026-05-05

**Chat slash: `/skill` for switching skills mid-conversation.**

`chat --skill review,style` set the system prompt at start; once the
chat was running there was no way to change it without restarting.
`/skill` fixes that.

### Behavior
- `/skill review,style` — replace the active system message with a
  composition of the named skills. If a system message already exists
  it's overwritten; never stacked.
- `/skill` (no args) — drop the active system message entirely.
- Persistence: when `--session <id>` is set, the JSONL file is
  rewritten so the dropped/overwritten system turn doesn't linger as
  a stale entry.
- Unknown skill name → `skill error: skill not found: <name>` and
  prior state preserved (no partial damage).

### Why rewrite the JSONL on `/skill`
The session log is append-only. To overwrite the system prompt without
introducing a "system replaces system" semantic in the storage format,
we truncate and re-append the in-memory message array. This keeps the
storage primitive simple — every line is a turn, no special cases for
mutating prior turns.

### Tests
3 new phase 6 specs:
- `/skill a` then `/skill b` leaves exactly one system message (the
  most recent) — verified by reading the JSONL after `/exit`
- `/skill` (no arg) drops the system message — verified the same way
- unknown skill name → error in stdout, prior state preserved

Suite: 157/157. tsc clean.

---
## [2.85.1] — 2026-05-05

**Daemon: `GET /skills` + `GET /skills/<name>` for HTTP skill discovery.**

Skills were creatable / loadable via the CLI and the daemon's
`POST /agent` already accepted them in `body.skills`, but a remote tool
had no way to *browse* what skills exist on a host. Adds the two read
endpoints.

### `GET /skills`
```json
[
  { "name": "reviewer", "bytes": 187, "summary": "Reviewer" },
  { "name": "concise",  "bytes":  43, "summary": "Concise" }
]
```
Mirrors `lazyclaw skills list`. Summary is the first markdown line with
the leading `#` stripped. Sorted alphabetically.

### `GET /skills/<name>`
- 200: `text/markdown` body (no JSON envelope — pipe straight into a
  renderer or compose into a prompt)
- 404: `{ error: "skill not found", name }` so callers branch cleanly
- 400: invalid name (path-traversal, dotfile) — `skillPath()` validation
  reused so HTTP gets the same protections as the CLI

### Tests
4 new phase 6 specs:
- `GET /skills` returns the list shape with first-line summaries
- `GET /skills/<name>` returns `text/markdown` body
- `GET /skills/missing` → 404 with the missing name in the body
- `GET /skills/.hidden` → 400 (dotfile rejected by `skillPath`, second-
  layer protection beyond the URL `[^/]+` regex)

Suite: 154/154 (the count includes the 2 phase 1 tests added by 2.85.0).
tsc clean.

---
## [2.85.0] — 2026-05-05

**Workflow executor: parallel cleanup hooks (measured 5× speedup).**

When a workflow node throws, every started node's cleanup hook runs.
This was sequential — 5 nodes × 80 ms each = 400 ms+ wall clock to
finish cleanup. Switched to `Promise.allSettled` so cleanups run
concurrently; total time becomes max(t_cleanup) instead of sum.

### Why this is safe
- Cleanups are independent by spec: each node owns its own resources.
  No ordering dependency, so parallelism doesn't change behavior.
- `Promise.allSettled` (not `Promise.all`) — one cleanup throwing must
  not mask the others' completion or the original failure that
  triggered cleanup in the first place. New spec asserts this.
- Sync cleanups still run in array order at call time (the `.map()`
  iterator runs synchronously and each `cleanup()` body executes
  before the next `Promise.resolve` is constructed). The existing
  order-asserting spec keeps passing without weakening.

### Measured baseline
Before: 5 × 80 ms cleanup = 400+ ms wall clock to finish post-failure.
After:  ~83 ms (one slot of cleanup time, regardless of fan-out).

### Tests
2 new phase 1 specs:
- 5 nodes × 80 ms async cleanup; total elapsed under 200 ms (sequential
  floor would be 400 ms+)
- one cleanup throwing does not block its siblings — both `a` and `c`
  cleanups complete despite `b` raising

Suite: 154/154. tsc clean.

---
## [2.84.0] — 2026-05-05

**`lazyclaw help` + `--help` / `-h` for centralized usage info.**

Each subcommand had its usage line scattered across the source. Users
who wanted a one-stop overview had to read CLAUDE.md or hunt through
errors.

### CLI
- `lazyclaw help` — lists every subcommand with a one-line summary,
  padded to 12 columns for scan-friendliness in an 80-column terminal
- `lazyclaw help <subcommand>` — detailed usage for that subcommand:
  flag list, env var fallbacks, alias forms
- `lazyclaw --help` and `lazyclaw -h` are aliases for `lazyclaw help`
- `help <unknown>` → exit 2 with a hint to run `lazyclaw help` for
  the inventory
- Unknown top-level subcommand also points at `lazyclaw help`

### Source-of-truth
`HELP_SUMMARIES` (one-liners) and `HELP_DETAILS` (multi-line usage)
live next to `SUBCOMMANDS` in `cli.mjs` so adding a subcommand
naturally surfaces a docs-touch reminder. Tests assert every
subcommand in `SUBCOMMANDS` has both a summary and a detailed entry.

### Tests
4 new phase 6 specs:
- `help` lists every subcommand and the `help <subcommand>` hint
- `help <subcommand>` returns *that* subcommand's usage (verified by
  comparing two different subcommands — daemon mentions
  `--auth-token`, sessions does not)
- unknown subcommand → exit 2 with the inventory hint on stderr
- `--help` and `-h` mirror the bare `help` output

Suite: 143/143. tsc clean.

---
## [2.83.5] — 2026-05-05

**Wire `withFallback` through CLI `agent --fallback` + daemon `body.fallback`.**

`withFallback` shipped in 2.83.3 but no user-facing surface called it.
Now it does.

### CLI
```bash
lazyclaw agent --fallback "openai,ollama" "explain quicksort"
```
- Comma-separated provider names; primary comes from `--provider` /
  `config.provider` as before
- Unknown name → exit 2 with `unknown fallback provider: <name>`
  (better than a silent skip — chain length affects user expectations)
- Composes with `--retry N`: fallback runs first (try alternates),
  retry wraps the resulting chain (retry the chain on `RATE_LIMIT`)

### Daemon
```http
POST /agent
{ "prompt": "...", "fallback": ["openai", "ollama"], "retry": { "attempts": 2 } }
```
- `body.fallback` is an array of provider names
- Unknown name in the array → `400 {error: "unknown fallback provider: <name>"}`
  before any provider call
- `resolveProvider` now returns `{ provider } | { error }` so the call
  sites at `POST /chat` and `POST /agent` surface the specific error
  message instead of a generic "unknown provider" string

### Tests
5 new phase 6 specs:
- CLI `--fallback "openai,ollama"` happy path (mock primary still replies)
- CLI `--fallback unknown-name` exits 2 with stderr message
- daemon `body.fallback` happy path
- daemon `body.fallback: ['nope']` → 400 with the exact unknown name
- daemon composing both `fallback` + `retry` doesn't break the happy path

Suite: 148/148. tsc clean.

---
## [2.83.4] — 2026-05-05

**`lazyclaw completion bash|zsh` for shell autocompletion.**

OpenClaw ships completion scripts; LazyClaw didn't. This makes
`lazyclaw <TAB>` actually do something for users who source the output.

### Usage
```bash
# bash
lazyclaw completion bash >> ~/.bashrc
# zsh — must live on $fpath; load via compinit
lazyclaw completion zsh > "${fpath[1]}/_lazyclaw"
```

The completion scripts know about every top-level subcommand
(`run|resume|config|chat|agent|doctor|status|onboard|sessions|skills|providers|daemon|version|completion`)
plus the second-level subcommands for the multi-level ones
(`config get|set|list|delete`, `sessions list|show|clear|export`,
`skills list|show|install|remove`, `providers list|info`,
`completion bash|zsh`).

### Source-of-truth
`SUBCOMMANDS` and `SUBCOMMAND_SUBS` live next to the runtime dispatcher
in `cli.mjs`. Tests assert the completion scripts contain every
subcommand the dispatcher knows about, so adding a subcommand can't
silently fall out of completion coverage.

### Tests
4 new phase 6 specs:
- `completion bash` emits `_lazyclaw_completion` function +
  `complete -F` line; every top-level subcommand appears in the body
- `completion zsh` emits a `#compdef` script with the same subcommands
- `completion` with no shell argument → exit 2 + usage on stderr
- the bash output is syntactically valid (`bash -n` parse check)

Suite: 139/139. tsc clean.

---
## [2.83.3] — 2026-05-05

**Provider auto-fallback: `withFallback` for chained provider failover.**

Mirrors the dashboard's "fallback chain" config in the CLI/daemon
provider layer. Pass an ordered list of providers; the first one that
yields any chunk wins, and any *pre-yield* recoverable error trips a
fall-through to the next provider.

```js
import { withFallback } from './src/lazyclaw/providers/fallback.mjs';
import { PROVIDERS } from './src/lazyclaw/providers/registry.mjs';

const safe = withFallback([PROVIDERS.anthropic, PROVIDERS.openai, PROVIDERS.ollama], {
  onFallback: ({ from, to, err }) => log.warn(`${from} → ${to} (${err.code || err.status})`),
});
for await (const chunk of safe.sendMessage(messages, opts)) write(chunk);
```

### Default `shouldFallback` predicate
Accepts: `RATE_LIMIT`, `CONNECTION_REFUSED`, 5xx upstream, bare network
errors. Rejects: `INVALID_KEY` (auth is structural — falling back masks
the real problem), `ABORT` (user cancellation should stop, not retry),
4xx that aren't 429. Override via `opts.shouldFallback`.

### Mid-stream guarantee
Once a provider has yielded any chunk it "owns" the response. A
subsequent error bubbles unchanged — same invariant as
`withRateLimitRetry`.

### Tests
9 new phase 6 specs cover: pre-yield `RATE_LIMIT` → fallback,
`INVALID_KEY` no fallback, `ABORT` no fallback, mid-stream error
bubble, 5xx fallback + `onFallback` callback, all providers fail →
rethrow last error, `shouldFallback` predicate override, single-provider
degenerate case, empty chain throws at construction.

Suite: 135/135. tsc clean.

---
## [2.83.2] — 2026-05-05

**`skills install --from-url <https://...>` for remote skill fetch.**

OpenClaw has a "ClawHub" registry concept for sharing skills; LazyClaw
doesn't run a registry but adds the simpler primitive — fetch from any
HTTPS URL. A skill written by someone else is just a markdown file at
a URL.

### CLI
- `lazyclaw skills install <name> --from-url <https://...>` fetches the
  body and writes `<configDir>/skills/<name>.md`
- Existing `--from <path>` and stdin forms continue to work

### Safety guardrails
- **HTTPS only**: `http://`, `file://`, `data:` etc. are rejected with
  exit 2. The skill content goes straight into the system prompt, so
  source authenticity matters.
- **1 MiB body cap**: streaming read aborts at the cap. Pathological
  responses can't balloon the prompt or fill the disk.
- **Non-2xx → exit 1** with the status code in the error message
- **No file write on failure** — the cap test asserts `<name>.md` is
  not created when the response is rejected

### Tests
4 new phase 6 specs:
- non-https URLs (`http://`, `file://`) → exit 2 with usage hint
- happy path: stub-fetched body lands at the right path
- size cap: 2 MiB body → exit 1 + `<name>.md` not written
- 404 → exit 1 with status in stderr

The stub fetch is injected via Node's `--import` flag so the test
process replaces `globalThis.fetch` before the CLI loads — no TLS cert,
no network round-trip, fast and offline.

Suite: 126/126. tsc clean.

---
## [2.83.1] — 2026-05-05

**LazyClaw: Gemini provider — fourth concrete provider.**

Brings Google's Generative Language API onto the same iterator
contract as Anthropic, OpenAI, and Ollama. Authentication via
`?key=` query parameter (Gemini's quirk) is handled inside the
provider so callers pass `opts.apiKey` the same way as everywhere
else.

### Wire format
- `POST .../v1/models/{model}:streamGenerateContent?alt=sse&key=...`
- Body: `{ contents: [{role:user|model, parts:[{text}]}], systemInstruction?: {parts:[{text}]} }`
- SSE response: `data: <json>\n\n` per chunk; text path is
  `candidates[0].content.parts[*].text`
- No terminator like `[DONE]`; stream simply ends

### Message-shape translation
Gemini calls assistants `model` and lifts the system prompt out of
the conversation into its own field. We translate:
- `role: 'assistant'` → `'model'`
- `role: 'system'` → `systemInstruction.parts[].text` (the most
  recent system message wins on conflict, matching how the other
  providers behave when given multiple)
- `opts.system` overrides any in-message system if both are present

### Errors
Mirrors the rest: 401/403 → `INVALID_KEY`, 429 → `RateLimitError`
with parsed `Retry-After`, other 4xx/5xx → `ApiError`. `AbortSignal`
honored before request and on every chunk; UTF-8 streaming
TextDecoder for non-ASCII responses.

### Registry
`PROVIDER_INFO.gemini` advertises the endpoint shape and suggested
models (`gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-2.0-flash`).
`lazyclaw doctor` accepts `provider: gemini` with a key.

### Tests
4 new phase 6 specs:
- happy path: SSE response → assembled text, URL contains
  `:streamGenerateContent?alt=sse&key=...`, body shape correct
- system message lifted to `systemInstruction`; assistant maps to `model`
- 401 → `INVALID_KEY`, 429 → `RateLimitError` with `retryAfterMs: 5000`
- registry lists gemini; doctor accepts it

Suite: 122/122. tsc clean.

---
## [2.83.0] — 2026-05-05

**Daemon: `Origin` gate for DNS-rebinding / browser-CSRF defense.**

The daemon binds 127.0.0.1, but a malicious page in the user's browser
can still issue cross-origin POSTs to `http://127.0.0.1:<our port>` —
that's exactly the DNS-rebinding attack class. The auth-token gate
helps when set, but the default deploy is unauthenticated.

Fix: every request that carries an `Origin` header must be on the
allowlist; missing `Origin` (the CLI/script case) passes through.
The check runs **before** the auth gate so a forbidden origin
cannot even probe whether a token is required (no `WWW-Authenticate`
on a 403, the browser doesn't pop a credential prompt).

### CLI
- `lazyclaw daemon --allow-origin "http://localhost:3000"` opens a
  specific browser origin
- comma-separated for multiple: `--allow-origin "http://localhost:3000,http://127.0.0.1:8080"`
- env var: `LAZYCLAW_ALLOW_ORIGINS=...` (flag wins when both set)
- bound-URL JSON now reports `allowedOriginCount: <N>` so callers can
  see whether browser access has been opened (count, not values)

### Tests
5 new phase 6 specs:
- no Origin header → allow (CLI/script default)
- foreign Origin → 403 with `{error: 'forbidden origin'}`
- allowlisted Origin → 200 (and missing Origin still allowed)
- ordering: Origin gate runs before auth — forbidden Origin gets 403
  with no `WWW-Authenticate` (browser cannot probe auth state)
- CLI integration: `--allow-origin` survives spawn, allowlisted Origin
  → 200, foreign Origin → 403, no Origin → 200

Suite: 118/118. tsc clean. Dashboard QA: 0/66.

---
## [2.82.2] — 2026-05-05

**Docs: README documents the daemon `--auth-token` and `retry` body field.**

§4.5 obligation. The 2.82.0 daemon retry plumbing and 2.82.1 bearer-token
auth shipped without README mention. Closing the gap:

- HTTP daemon section now shows the three startup forms (no auth /
  `--auth-token` / `LAZYCLAW_AUTH_TOKEN`)
- Documents the constant-time check and the `auth: true|false` field
  in the bound-URL JSON
- `POST /agent` and `POST /chat` body shapes mention the
  `retry: { attempts, maxBackoffMs }` field

No code changes.

---
## [2.82.1] — 2026-05-05

**Daemon: optional bearer-token auth for non-loopback exposure.**

The daemon was loopback-only, no auth, single-user assumption. That's
fine for the default deploy but breaks the moment you SSH-tunnel the
port to a shared host or run the daemon under a service account that
others share. Adds opt-in bearer-token auth.

### How it works
`makeHandler({ ..., authToken: 'secret-abc' })` enables the gate. Every
request must present `Authorization: Bearer <token>`; missing or
mismatched tokens get `401` + `WWW-Authenticate: Bearer realm="lazyclaw"`
before the route is even resolved. When `authToken` is unset (default),
behavior is identical to before — every request goes through.

### Constant-time comparison
Plain `===` would short-circuit on the first mismatching byte, leaking
timing information that an attacker on a shared host could use to
narrow the secret one byte at a time. The check XORs every byte into
an accumulator and returns `accum === 0`, so success and failure take
the same time regardless of where the strings diverge.

### CLI integration
`lazyclaw daemon --auth-token <token>` (also `LAZYCLAW_AUTH_TOKEN` env)
turns on the gate; the bound-URL JSON now carries `auth: true` so
test scripts can verify auth is enabled without inspecting the actual
token. The flag wins over the env var when both are set.

### Tests
6 new phase 6 specs:
- missing `Authorization` header → 401 + `WWW-Authenticate`
- correct `Bearer <token>` → 200, route reached
- wrong token → 401, `readConfig` is *not* called (auth runs before
  route resolution — important so unauthorized callers can't probe
  internal state via side effects)
- no `authToken` set → no gate, default loopback behavior unchanged
- timing: same-length wrong-byte / shorter / longer / empty all
  return 401 (validates the constant-time comparison handles
  length-mismatch correctly)
- CLI: `--auth-token` flag survives spawn, daemon reports `auth: true`,
  request without header → 401, with header → 200

Suite: 112/112. tsc clean. Dashboard QA: 0/66.

---
## [2.82.0] — 2026-05-05

**`chat --skill` parity + daemon retry plumbing.**

`agent --skill` worked since 2.77.0; `chat` ignored the flag. Closing the
gap so users can use the same comma-separated skill list across both
entry points.

### `chat --skill`
- `lazyclaw chat --skill review,style` composes the named skills via
  `composeSystemPrompt` and prepends the result as a `system` message.
- `--session <id>` persists the system message into the session JSONL
  on first invocation. On subsequent invocations of the same session,
  if a `system` turn already exists in the hydrated history, we do
  **not** re-prepend — protecting against the most common bug class
  ("system prompt accidentally repeated for every resume").
- Defaults: when `config.skills` is set to a string array (e.g.
  `["review","style"]`), it auto-applies on `chat` the same way it does
  on `agent`.

### Daemon retry plumbing
`POST /agent` and `POST /chat` accept an optional `retry` body field:
```json
{ "prompt": "...", "retry": { "attempts": 3, "maxBackoffMs": 60000 } }
```
The daemon wraps the resolved provider with `withRateLimitRetry` so
HTTP callers get the same backoff behavior the CLI gets. Falsy or
zero `attempts` skips wrapping (existing callers see no change).

### Tests
2 new phase 6 specs:
- `chat --skill` writes the system message into the session JSONL on
  first run (verified by reading back the file)
- resuming a session that already has a system message does NOT
  re-prepend (exactly one system turn after the second invocation)

Suite: 104/104. tsc clean.

---
## [2.81.2] — 2026-05-05

**Provider retry wrapper: `withRateLimitRetry` for `RATE_LIMIT` backoff.**

A wrapper, not a per-provider option, because retry policy is a caller
concern (CLI script wants 3 retries, daemon wants 10 with a max wall
clock). Wrapping keeps the providers simple — each remains a pure
async iterator over a single attempt.

```js
import { withRateLimitRetry } from './src/lazyclaw/providers/retry.mjs';
import { anthropicProvider } from './src/lazyclaw/providers/registry.mjs';

const safe = withRateLimitRetry(anthropicProvider, {
  attempts: 3,
  maxBackoffMs: 60_000,
  onRetry: ({ attempt, retryAfterMs }) => log.warn(`429 retry ${attempt} in ${retryAfterMs}ms`),
});

for await (const chunk of safe.sendMessage(messages, { apiKey, model, signal })) {
  process.stdout.write(chunk);
}
```

### Strategy
1. Only `RATE_LIMIT` errors that surface *before any chunk has been yielded*
   are retried. Mid-stream `RATE_LIMIT` is re-thrown unchanged because
   retrying would produce duplicate text downstream.
2. Sleep is `min(retryAfterMs, maxBackoffMs)` with a hard 5-minute
   absolute ceiling — a misbehaving provider can't pin us for an hour.
3. `attempts` is exclusive of the initial call: `attempts: 3` means up to
   four total tries.
4. `opts.signal` is honored *inside* the sleep so a cancel during backoff
   stops immediately rather than waiting for wake-up.

### Tests
8 new phase 6 specs:
- happy-path retry: yields the second attempt
- exhausted attempts → rethrow last `RATE_LIMIT`
- mid-stream `RATE_LIMIT` is NOT retried (duplicate-output guard)
- non-`RATE_LIMIT` errors pass through immediately
- `onRetry` callback receives `{attempt, retryAfterMs}`
- `clampBackoff` clamps to `maxBackoffMs` and the 5-minute ceiling
- first-attempt success: zero retries, single underlying call
- `opts.signal` aborts during backoff sleep (no second attempt)

Suite: 102/102. tsc clean.

---
## [2.81.1] — 2026-05-05

**Anthropic prompt caching: `opts.cache: true`.**

When the system prompt is long and stable across calls (skill bundles
are the common case), pass `cache: true` to `anthropicProvider.sendMessage`
and the provider lifts the system string into the cache-control text-block
shape:

```json
{
  "system": [
    { "type": "text", "text": "...", "cache_control": { "type": "ephemeral" } }
  ]
}
```

Repeated calls with the same prefix only pay full input cost once; subsequent
calls within the cache TTL hit the cache. No-op when `cache` is falsy
(default) — `body.system` stays a plain string, identical to prior behavior.

### Tests
2 new phase 6 specs:
- default path: `body.system` is a plain string
- `cache: true`: `body.system` is the array-of-text-blocks form with
  `cache_control: { type: 'ephemeral' }`

Suite: 100/100 (milestone). tsc clean.

---
## [2.81.0] — 2026-05-05

**Provider throughput benchmark (`make bench-providers`).**

§9.2 of the engineering directives: don't optimize without measurement.
This is the measurement. Future SSE-parser changes should re-run this
and post the before/after numbers in their commit message rather than
guessing.

### `scripts/bench-providers.mjs`
Feeds each provider a worst-case-shape stream — every token is its own
`event: content_block_delta` (anthropic) or `data:` frame (openai), so
maximum number of `\\n\\n` boundary searches and `JSON.parse` calls.
Reports `tokensPerSec`, `mbPerSec`, `heapDeltaMB`.

Configurable via env vars:
- `N=50000` token count (default 20000)
- `PROVIDER=openai` switches to OpenAI Chat Completions (default anthropic)

### Baseline numbers (this machine, today)
- anthropic, 20k tokens: **~790k tok/s**, ~80 MB/s, +5.8 MB heap
- anthropic, 50k tokens: **~927k tok/s**, ~94 MB/s, +6.6 MB heap
- openai,    20k tokens: **~750k tok/s**, ~33 MB/s, +2.6 MB heap

Linear scaling between 20k and 50k tokens — no quadratic regression
in the buffer slicing path. Bounded heap delta confirms the streaming
`TextDecoder` and per-frame consumption don't accumulate.

### `make bench-providers`
Runs all three configurations sequentially with a banner per run.
Output is JSON-per-run so it's easy to diff against a prior run.

No production code changes. Suite still 92/92 (or whatever the head
is after 2.80.2 — re-verify with `npx playwright test`).

---
## [2.80.2] — 2026-05-05

**Test coverage: `sessions export` CLI behavior.**

Backfilling specs that should have shipped with 2.80.1 — the
`sessions export` CLI binding had no test coverage of its own.

Added 3 phase 6 specs:
- exporting a real session prints the Markdown dump (H1, `Turns: N`,
  `## User` / `## Assistant` sections, exact content preserved)
- exporting an empty session prints `_(empty)_` placeholder
- missing id exits 2 with the usage line on stderr

Suite: 92/92 (was 89; +3 from this commit, +1 from sessions.exportMarkdown
helper coverage, +1 from sessions.exportMarkdown empty-case).

---
## [2.80.1] — 2026-05-05

**`lazyclaw sessions export <id>` — print a session as Markdown.**

`sessions.exportMarkdown(id)` already shipped in 2.80.0 (the user/linter
added the helper) but the CLI binding for `sessions export <id>` was
not wired through, so the only way to call it was from JS. Wires the
case into the `sessions` subcommand.

```bash
lazyclaw sessions export feat-x > feat-x.md
```

Errors (missing id, invalid id) follow the same pattern as the rest of
the `sessions` subcommand (exit 2 for usage, exit 1 for runtime).

---
## [2.80.0] — 2026-05-05

**LazyClaw: Ollama provider for local-model parity.**

OpenClaw lists Ollama alongside Anthropic/OpenAI; LazyClaw was missing
it. Adds `providers/ollama.mjs` — a third concrete provider so users
with `ollama serve` running can chat without paying for API tokens.

### Wire format
- `POST {baseUrl}/api/chat` (default `http://127.0.0.1:11434`)
- `OLLAMA_HOST` env var, `opts.baseUrl` flag, or default — in that order
- Newline-delimited JSON, not SSE: one
  `{"message":{"content":"…"},"done":false}` object per chunk,
  terminator is `{"done":true,...}` (which carries
  `prompt_eval_count` / `eval_count` for callers that want to log usage)

### Iterator contract
Same as the other providers: yield `message.content` strings, return
on `done: true`. `opts.signal` honored before request and on every
chunk. UTF-8 streaming `TextDecoder` so non-ASCII responses don't
mojibake across socket reads.

### Specific failure mode
The most common Ollama error is "the daemon isn't running":
`ECONNREFUSED`. We catch that and throw a dedicated
`ConnectionError { code: 'CONNECTION_REFUSED' }` with a useful message
(`ollama: cannot reach <baseUrl> (is the daemon running?)`) instead of
letting a raw fetch error propagate. Callers can branch on `err.code`.

### Registry
`PROVIDER_INFO.ollama` advertises `requiresApiKey: false`, the local
endpoint, and a suggested-model list (`llama3.1`, `llama3.2`, `mistral`,
`qwen2.5-coder`). `lazyclaw doctor` accepts an `ollama` provider with
no key.

### Tests
4 new phase 6 specs:
- happy path: NDJSON chunks → assembled text, `done:true` terminates
- `opts.baseUrl` override actually changes the URL hit
- `ECONNREFUSED` → `ConnectionError { code: 'CONNECTION_REFUSED' }`
- registry exposes `ollama` via `lazyclaw providers list`

Suite: 89/89. tsc clean.

---
## [2.79.5] — 2026-05-05

**Docs: refresh stale version badges + tagline.**

The version badge in `README.md` and `README.ko.md` was stuck at
`v2.36.3`; `README.zh.md` was at `v2.33.2`. The "Latest line is v2.55"
tagline was 24 versions behind. Bumped all three to `v2.79.4` and
rewrote the tagline to reflect the LazyClaw CLI parity arc that
landed across this cycle (anthropic + openai streaming, extended
thinking, tool-use passthrough, persistent sessions, skills, daemon,
AbortSignal, error classes).

Docs only.

---
## [2.79.4] — 2026-05-05

**Docs: README documents the programmatic provider API.**

The CLI/daemon surface was already in the README; the underlying
`prov.sendMessage(messages, opts)` interface was not. After 16+
iterations of building it out (`opts.signal`, `opts.thinking`,
`opts.onThinking`, `opts.tools`, `opts.toolChoice`, `opts.onToolUse`,
`opts.fetch` test seam, plus the `INVALID_KEY` / `RATE_LIMIT` / `ABORT`
error codes), the surface deserves a real example.

New "Programmatic API" subsection under "🐚 LazyClaw CLI (standalone)".
Single annotated `for await` block exercises the full opts shape and
shows the catch-by-`err.code` dispatch readers should write. No code
changes.

---
## [2.79.3] — 2026-05-05

**Daemon: provider-error → HTTP status mapping.**

Every error coming out of `POST /agent` and `POST /chat` used to land
as 502. Now they map by `err.code`:

| code | HTTP | extra |
|---|---|---|
| `INVALID_KEY` | 401 | — |
| `RATE_LIMIT` | 429 | `Retry-After: <seconds>`, `retryAfterMs` in body |
| `err.status` (4xx/5xx) | passthrough | — |
| anything else | 502 | — |

Sub-second `retryAfterMs` rounds up to 1s in the header so a
mis-typed value can never produce `Retry-After: 0` (which would invite
clients to immediately hammer).

`statusForProviderError(err)` is exported so callers reusing the
daemon module can apply the same mapping. Direct unit tests cover
INVALID_KEY/RATE_LIMIT/passthrough/default plus the sub-second rounding
edge case.

1 new spec, suite 83/83 green, tsc clean.

---
## [2.79.2] — 2026-05-05

**`RateLimitError` for HTTP 429 with parsed `Retry-After`.**

Both providers used to lump 429 in with the catch-all `ApiError`,
so callers had to substring-match `body` to even know it was a rate
limit. Lifted it to a dedicated class:

```js
catch (e) {
  if (e.code === 'RATE_LIMIT') sleep(e.retryAfterMs);
  else throw e;
}
```

`Retry-After` parsing handles the two RFC-compliant forms:
- integer seconds (`"7"`) → 7000 ms
- HTTP-date (`"Wed, 21 Oct 2026 07:28:00 GMT"`) → ms until that wall-clock
- missing or unparseable → 1000 ms default (rather than retry instantly)

Works with both a `Headers` instance and a plain object so injected
test fetches can use either shape.

3 new phase 6 specs (anthropic seconds form, openai missing-header
default, HTTP-date form). Suite: 82/82. tsc clean.

---
## [2.79.1] — 2026-05-05

**OpenAI tool calling for symmetry with Anthropic.**

The OpenAI provider now mirrors what 2.79.0 added for Anthropic:

- `opts.tools` (OpenAI shape: `[{type:'function', function:{name, parameters}}]`)
  forwards to the request body
- `opts.toolChoice` maps to `tool_choice` (`'auto' | 'none' | {type, function:{name}}`)
- streamed `delta.tool_calls[i]` deltas accumulate per `index`; the
  final assembled call surfaces via `opts.onToolUse({id, name, input, raw})`
- still a passthrough — execution remains the caller's job

### Edge case
OpenAI sometimes ends a response with `[DONE]` without first emitting
`finish_reason: tool_calls`. We drain any pending tool calls on `[DONE]`
so the callback always fires for completed deltas.

### Tests
2 new phase 6 specs:
- happy path: chunked `function.arguments` partials assemble into the
  parsed `input` object; `tools` + `tool_choice` land in the request body
- `[DONE]`-only flush still surfaces the tool call

Suite: 79/79. tsc clean.

---
## [2.79.0] — 2026-05-05

**Anthropic tool-use passthrough.**

The provider now forwards `opts.tools` to the Messages API and assembles
streamed `tool_use` blocks for the caller via `opts.onToolUse`.

### What this is — and what this is NOT
This is a *passthrough*, deliberately. The provider:
- Sends your `tools` definitions in the request body
- Optionally honors `opts.toolChoice` (e.g., `{type: 'auto'}` /
  `{type: 'tool', name: 'X'}`)
- Reassembles each streamed `tool_use` block from
  `content_block_start` (id + name) + N `input_json_delta` partials +
  `content_block_stop`
- Calls `opts.onToolUse({id, name, input, raw})` once the block is complete

It does **not** execute tools. Execution is the caller's responsibility:
the caller decides what to run, runs it locally with whatever sandbox
they want, and sends the result back as a `tool_result` content block
on the next `messages` array. This keeps the provider library
unprivileged — no shell access, no filesystem write, no surprise
side-effects from the model.

### Iterator contract
`text_delta` continues to yield through the for-await loop as before;
`thinking_delta` continues to route to `onThinking`; `input_json_delta`
accumulates into the open tool block and surfaces only on
`content_block_stop`. Existing callers see no behavior change.

### Robustness
A malformed `partial_json` (e.g., the model sent something we couldn't
JSON-parse) still calls `onToolUse` with `input: {}` and `raw: <whatever>`
so the caller can either retry, log, or recover.

### Tests
2 new phase 6 specs:
- happy path: tool definitions in request body, assembled tool_use call
  with id + name + parsed input from chunked partial_json
- malformed partial_json → empty `input`, raw text preserved

Suite: 77/77. tsc clean.

---
## [2.78.0] — 2026-05-05

**Cancellable streams: `AbortSignal` end-to-end.**

Both providers and the daemon now honor `opts.signal` so callers can
cancel an in-flight inference and stop burning tokens.

### Providers
- `anthropicProvider.sendMessage(..., { signal })` — checks the signal
  before the request, before each chunk read, and propagates it to
  `fetch` so the underlying socket closes on abort. Aborted streams
  throw `AbortError { code: 'ABORT' }`.
- `openaiProvider.sendMessage` mirrors the same shape.

### Daemon
The streaming `POST /agent` endpoint creates a per-request
`AbortController` and forwards `req.aborted` / `res.close` events to
the provider. When the client disconnects mid-stream:
- The provider stops issuing tokens.
- The session JSONL is **not** appended (the assistant turn was
  partial).
- The daemon ends the SSE response without writing `event: error`.

### Tests
3 new phase 6 specs:
- pre-request abort throws `AbortError` (anthropic)
- mid-stream abort stops yielding after the first chunk (anthropic)
- openai mirrors the same shape

Suite: 75/75. tsc clean.

---
## [2.77.2] — 2026-05-05

**Docs: README documents the LazyClaw CLI surface.**

The CLI grew from `chat + config` (phase 4) to 12 subcommands across
this Ralph cycle without README catching up. §4.5 says "if a feature
that users can run is added, the README must be updated." Filling
that obligation:

- `README.md` (canonical, English): new `🐚 LazyClaw CLI (standalone)`
  section between "Install as an app" and "Features". Documents
  onboard / doctor / chat / agent / sessions / skills / providers /
  daemon / config and the loopback HTTP gateway.
- `README.ko.md`, `README.zh.md`: condensed mirror sections that link
  back to the canonical English reference for the full table.

No code changes. Suite still 72/72 (re-verified). Dashboard QA still 0/66.

---
## [2.77.1] — 2026-05-05

**Daemon: skill composition for `POST /agent`.**

The daemon now mirrors the CLI's `--skill` flag at `POST /agent`:

```
POST /agent
{ "prompt": "...", "skills": "review,style" }
```

Or as an array: `"skills": ["review", "style"]`. Names compose with
`<!-- skill: name -->` markers and a `---` separator (same shape as
the CLI). When `sessionId` is set the prepended system message
is only added on the first call (we check whether a system message
already exists in the hydrated history) so multi-turn sessions don't
double-prepend.

Errors during composition (missing skill, invalid name) return 400
before any provider call so the caller sees a clear "skill error: ..."
rather than a 502 from the model.

2 new phase 6 specs (composition success + missing-skill 400).
Suite: 72/72. tsc clean.

Plus: dashboard QA re-run after iteration 10 — still 0/66 issues.

---
## [2.77.0] — 2026-05-05

**LazyClaw: skills (markdown system prompts) + `config list/delete`.**

OpenClaw's "skill" concept reduced to its load-bearing core: reusable
instruction bundles, named, locally stored, no remote registry needed.
A skill is just a markdown file at `<configDir>/skills/<name>.md`.

### CLI
- `lazyclaw skills list` — names + first-line summaries
- `lazyclaw skills show <name>` — print full markdown
- `lazyclaw skills install <name> --from <path>` — copy a file
- `lazyclaw skills install <name>` (no --from) — read content from stdin
- `lazyclaw skills remove <name>`
- `lazyclaw agent --skill review,style "review my diff"` — comma-separated
  list of skills to compose into the system prompt for this run
- Defaults: when `config.skills` is set to an array of skill names,
  `agent` (and chat through it) auto-applies them unless `--skill` is
  explicitly passed

### Skill composition
Each skill is wrapped with a `<!-- skill: name -->` marker and joined
with a `---` separator so the model can see boundaries between distinct
guidance. Empty / missing skills throw a clear error before the
provider call.

### Security
`skillPath()` rejects names containing `/`, `\\`, `..`, `.`, or names
starting with `.` (no dotfiles). Tested.

### `config list/delete`
Filling the obvious gaps in `config get/set`. `delete` is idempotent
and reports `removed: true|false` so callers know whether anything
changed.

### Tests
6 new phase 6 specs (round-trip skills CRUD, stdin install, skill
composition into system prompt, name validation, config list, config
delete idempotency). Suite: 70/70. tsc clean.

---
## [2.76.1] — 2026-05-05

**Daemon: more endpoints — `GET /doctor`, `POST /chat`, `GET/DELETE /sessions/<id>`.**

Daemon was MVP'd in 2.76.0 with version/providers/status/sessions/agent.
This fills in the remaining surface so a remote tool can run a complete
LazyClaw workflow without ever shelling out to the CLI.

- `GET /doctor` — mirrors `lazyclaw doctor`. Returns 503 when the
  diagnostic finds issues so health-check probes can short-circuit
  on a single status code; otherwise 200 with the same JSON shape.
- `POST /chat` — body `{messages: [{role, content}, ...], provider?, model?, stream?, thinkingBudget?}`.
  Useful when the caller already has a message history and isn't using
  the disk-persisted session model. `stream:true` returns the same
  SSE shape as `POST /agent`.
- `GET /sessions/<id>` — `{id, turns}`. Returns 404 when the file is
  missing so the caller can distinguish "doesn't exist" from "empty".
- `DELETE /sessions/<id>` — idempotent. Always 200 on missing or
  present, so callers can use it as a reset without checking first.

5 new phase 6 specs (11 daemon specs total). Suite 64/64. tsc clean.

---
## [2.76.0] — 2026-05-05

**LazyClaw: local HTTP daemon (`lazyclaw daemon`).**

OpenClaw exposes a local "gateway" so other tools talk to it over HTTP.
LazyClaw now does the same — scoped to what the CLI offers and locked
to loopback only.

### Endpoints (always 127.0.0.1)
- `GET /version` — VERSION + node + platform
- `GET /providers` — registered providers with key requirement +
  default/suggested models (mirrors `lazyclaw providers list`)
- `GET /status` — current config (provider, model, masked key)
- `GET /sessions` — recent persisted sessions, mtime descending
- `POST /agent` — body `{prompt, provider?, model?, thinkingBudget?, sessionId?, stream?}`
  - `stream:false` (default) collects the full reply and returns
    `{reply}` once
  - `stream:true` returns `text/event-stream`: `event: token\ndata: {"text":"…"}`
    per chunk, `event: done` at end, `event: error` on failure
  - `sessionId` makes both turns (user + assistant) append to
    `<configDir>/sessions/<id>.jsonl` — same shape as the CLI

### Safety
- Always binds 127.0.0.1; never 0.0.0.0
- Body cap: 5 MB, otherwise the request is destroyed before parse
- Unknown route → 400 with `{error, route}`
- No auth — assumes the only client is the local user. Don't expose
  this beyond loopback without adding one.

### CLI shape
- `lazyclaw daemon --port 0` binds a random port and prints
  `{ok, url, port, once}` to stdout — easy for tests to discover.
- `lazyclaw daemon --once` exits after the first request closes.
  Used by the test harness so it never has to send SIGTERM and chase
  zombie servers.

### Tests
6 new phase 6 specs:
- `GET /version` returns the right shape
- `GET /providers` enumerates the registered set
- `POST /agent` non-streaming reply
- `POST /agent` with `sessionId` writes the JSONL
- `POST /agent` with `stream:true` emits `event: token` and `event: done`
- `POST /agent` with no prompt → 400

Suite: 59/59. tsc clean.

---
## [2.75.1] — 2026-05-05

**LazyClaw: `providers list/info` for discoverability.**

`lazyclaw providers list` returns every registered provider with its
key requirement, default model, and suggested models — so a fresh
install can answer "what can I run?" without reading source.

`lazyclaw providers info <name>` returns the full static metadata
(endpoint URL, key prefix, docs blurb). Unknown name exits 2 and
hints the registered list.

Provider info lives in `PROVIDER_INFO` next to `PROVIDERS` so adding
a provider in one place can't drift from what users see.

3 new phase 6 specs; suite 53/53 green.

---
## [2.75.0] — 2026-05-05

**LazyClaw: persistent chat sessions.**

Chat used to live in process memory only — close the terminal, lose
the thread. Now opt in with `--session <id>` and the conversation
persists across invocations.

### Storage
`<configDir>/sessions/<id>.jsonl`. Append-only JSONL: one
`{role, content, ts}` line per turn. Append-per-turn means:
- Atomic writes (no read-modify-write race when two terminals share an id)
- O(1) write per turn regardless of conversation length
- Last-turn time is the file mtime, so `sessions list` sorts without
  reading any file body

### CLI
- `lazyclaw chat --session <id>` — load prior turns, then append every
  user/assistant pair as it streams. On resume, prints
  `resumed session <id> with N prior turn(s)` so the user knows which
  thread they're picking up.
- `lazyclaw sessions list` — recent first, by mtime
- `lazyclaw sessions show <id>` — dump full turn log as JSON
- `lazyclaw sessions clear <id>` — remove the file
- `/new` slash inside a `--session` chat truncates the file (mtime stays
  fresh so the session keeps its position in the list)

### Security
`sessionPath()` rejects ids containing `/`, `\`, or `..`/`.` so the
session id can never escape `<configDir>/sessions/`. Tested.

### Tests
5 new phase 6 specs:
- chat `--session` writes the expected JSONL on send
- second invocation announces it resumed the prior turns
- `sessions list` returns mtime-descending order
- `sessions clear` removes the file
- `sessionPath` rejects path-traversal ids

Full suite: 50/50. tsc clean.

---
## [2.74.0] — 2026-05-05

**LazyClaw: extended thinking + `version` subcommand.**

### Extended thinking (Anthropic)
The Anthropic provider now plumbs through the Messages-API extended
thinking parameter and surfaces `thinking_delta` events.

API shape on `sendMessage`:
- `opts.thinking = { enabled: true, budgetTokens: 5000 }` — enables the
  extended-thinking budget. `budgetTokens` defaults to 1024 when only
  `enabled` is set. The provider always sends `{ type: "enabled", budget_tokens: N }`
  in the request body.
- `opts.onThinking?: (chunk: string) => void` — optional callback that
  receives every `thinking_delta` text chunk as it streams. The main
  iterator continues to yield only `text_delta` content, keeping the
  default consumer contract identical to before.

CLI:
- `lazyclaw agent --thinking 5000 "..."` — enables extended thinking
  with a 5000-token budget. Works for the anthropic provider; other
  providers ignore the flag silently.
- `lazyclaw agent --thinking 5000 --show-thinking "..."` — additionally
  routes thinking text to stderr while normal response text continues
  to stdout. This way `lazyclaw agent ... | tee response.txt` only ever
  pipes the answer.

### `lazyclaw version`
Prints `{ version, nodeVersion, platform }` as JSON. Aliases: `--version`, `-v`.

### Tests
3 new phase 6 specs:
- `version` subcommand returns the expected shape
- thinking config goes out in the request body and `thinking_delta`
  routes to the `onThinking` callback while text stays on the iterator
- back-compat: when no `onThinking` is provided, thinking deltas are
  dropped so existing callers continue to see the same stream

Full suite: 45/45.

---
## [2.73.0] — 2026-05-05

**LazyClaw parity continued: OpenAI provider + `agent` one-shot.**

OpenClaw lists OpenAI alongside Anthropic; LazyClaw now matches.

### `lazyclaw agent <prompt>`
One-shot, non-interactive execution. Sends a single user message,
streams the response to stdout, exits.
- `lazyclaw agent "rewrite this commit message: ..."`
- `cat file.txt | lazyclaw agent -` reads the prompt from stdin
- `--provider <name>` and `--model <id>` override config for this call

Designed for shell pipelines and CI scripts. Honors INVALID_KEY at exit
code 1; clean replies exit 0.

### `providers/openai.mjs`
- POST `https://api.openai.com/v1/chat/completions` with `stream: true`,
  `Authorization: Bearer …`
- SSE: parses `data: {…}\n\n` frames, yields `choices[0].delta.content`,
  terminates on the literal `data: [DONE]\n\n`
- 401 / 403 → `InvalidApiKeyError { code: 'INVALID_KEY' }`
- Streaming `TextDecoder({ stream: true })` so non-ASCII responses (CJK,
  emoji, etc.) decode correctly across chunk boundaries
- Test seam: `opts.fetch` injection mirrors the Anthropic provider

### `doctor` updates
The diagnostic now lists `openai` under `knownProviders`. Setting
`provider: openai` + `api-key` + `model` passes the diagnostic.

### Tests
6 new phase 6 specs (now 17 in the file, 42 total in the suite):
- agent one-shot positional prompt → mock-reply
- agent stdin prompt
- agent `--provider` override actually switches providers (proven by
  triggering INVALID_KEY when the override has no key)
- openai SSE happy path with `[DONE]` termination
- openai 401 → INVALID_KEY
- doctor reports openai

---
## [2.72.1] — 2026-05-05

**Anthropic SSE: streaming UTF-8 decoder.**

The provider used `new TextDecoder().decode(chunk)` per chunk — fresh
decoder each time, no `{ stream: true }`. A multi-byte codepoint that
landed across two HTTP read boundaries (common with non-ASCII streams,
i.e. anything that isn't English) would surface as U+FFFD because the
trailing partial byte was discarded before the continuation arrived.

Reuse a single decoder for the lifetime of the request and pass
`{ stream: true }` so partial bytes are held until the next chunk.
Final pending bytes flushed via a no-arg `decoder.decode()` after
the body iterator drains.

### Tests
New phase 6 spec: split a Korean text frame mid-codepoint across two
ReadableStream chunks; assert the joined output equals "안녕" exactly.
Without the fix, the joined string contains a replacement character.

Full suite: 36/36.

---
## [2.72.0] — 2026-05-05

**LazyClaw OpenClaw-parity: phase 6** — `doctor`, `onboard`, `status`,
real Anthropic streaming, slash commands.

LazyClaw stops at "config set + chat" was a phase-4 placeholder. This
release lifts it to OpenClaw's CLI shape so a fresh install can be
configured and validated in one command set.

### CLI additions
- `lazyclaw onboard [--non-interactive]` — guided setup. Accepts the
  unified `--model anthropic/claude-opus-4-7` form (provider extracted
  automatically) or the split `--provider anthropic --model claude-opus-4-7`.
  `--api-key` writes the key. With `--non-interactive` it's automation-safe;
  without, it prompts for missing fields.
- `lazyclaw doctor` — prints diagnostic JSON (config path, provider,
  model, hasApiKey, node version, platform, registered providers, issue
  list). Exits 0 only when no issues. Mock provider does not require a
  key; non-mock providers do.
- `lazyclaw status` — single-shot config view. Always emits `keyMasked`
  (e.g. `sk-ant-****abcd`) — never the raw key.

### Chat slash commands
`/help`, `/status`, `/new`, `/reset` (alias for `/new`), `/usage`, `/exit`.
- `/status` prints provider, model, keyMasked, current message count.
  Asserted not to leak the raw key.
- `/new` clears the in-memory message array so the next user line is
  the start of a fresh conversation.
- `/usage` reports `messageCount` + `charsSent`.

### Provider layer
- `providers/anthropic.mjs` — real Messages-API SSE streaming. Splits
  the body, parses `event: content_block_delta` frames, yields
  `delta.text` per chunk, terminates on `message_stop`. Surfaces 401/403
  as `InvalidApiKeyError { code: 'INVALID_KEY' }`. Accepts a `fetch`
  option for offline tests.
- `providers/registry.mjs` — re-exports the real provider, adds two
  helpers: `parseProviderModel("anthropic/claude-opus-4-7")` and
  `maskApiKey("sk-ant-...")`. The mask only honours known vendor
  prefixes (`sk-ant-`, `sk-or-`, `sk-`); custom keys mask completely
  rather than risk surfacing a meaningful chunk.

### Tests
- `tests/phase6-openclaw-parity.spec.ts` — 10 specs covering every new
  CLI command, both onboard variants, /status leak guard, /new reset,
  /help inventory, anthropic SSE shape, anthropic 401 → INVALID_KEY.
- Full Playwright run: 35/35 passing (25 prior + 10 new).
- `tsc --noEmit` clean. `npm run lint` exit 0.

### Out of scope (called out per §1.1)
OpenClaw's multi-channel inbox (WhatsApp, Signal, Slack, Telegram, etc.),
voice/wake-word, mobile companion apps, Live Canvas, Docker/SSH/OpenShell
sandbox backends are platform integrations that need real API
credentials, mobile builds, or daemon installation — none of which are
appropriate for autonomous-mode commits.

---
## [2.71.116] — 2026-05-05

**Dashboard QA pass (LCO1)** — squashed `<select>` + new QA harness.

- **Squashed select fix**: every flex row pairing `<select class="input flex-1">`
  with siblings using width utilities (`<input class="input w-24">`, etc.)
  was rendering the select at ~24 px because `.input { width: 100% }`
  (specificity 0,1,0) tied with Tailwind's `w-*` utilities and source order
  let the default win. Lowered the width default to zero specificity via
  `:where(.input) { width: 100% }` so any explicit width utility wins
  automatically — no `!important`, no per-element override. Affected views
  include `promptCache`, `batchJobs`, `thinkingLab`, `toolUseLab`,
  `citationsLab`, plus the workflow node multi-assignee row.
- **Auto-Resume binding picker (LCO0)** — bonus from earlier today:
  the modal pulls live CLI sessions from `/api/sessions-monitor/list` and
  picking one auto-fills both Session UUID and cwd. The previous endpoint
  string `/api/cli-sessions/list` was a typo and never returned data.
- **New harness `scripts/e2e-dashboard-qa.mjs`**: deeper than the smoke
  test — captures console errors, page errors, failed network requests,
  and detects actual horizontal overflow while skipping intentional
  `text-overflow: ellipsis` truncations. Final pass: 66/66 tabs clean,
  0 errors, 0 overflow violations.

### Verified
- `npx playwright test` → 25 passed.
- `node scripts/e2e-dashboard-qa.mjs` → 0/66 issues.
- `npm run test:e2e:smoke` → 66/66 tabs.

---
## [2.71.115] — 2026-05-04

**QQ220 — CRITICAL** — auto-fallback for external SSE aborts.

QQ219 fixed the server-side traceback path, but real users were
still seeing "■ 중단됨" because their browser environment
(extension, service worker, antivirus, network middleware) was
killing the SSE connection. Playwright headless reproduced
clean (zero `AbortController.abort()` calls) but production
browsers cancelled fetch mid-stream. The catch path then went
straight to the "중단됨" bubble.

Fix: distinguish user-initiated aborts from external aborts.
* `window.__lcUserAbort = true` is set at the two real abort
  callsites — Esc handler (line 27433) + Send re-press
  (line 28991). These render the "중단됨" bubble as before.
* Any other AbortError where no token has arrived is treated
  as an environmental SSE block. The catch falls through to
  the existing non-stream `POST /api/lazyclaw/chat` endpoint
  and the chat completes transparently.
* If even the non-stream fallback fails, the error message
  points at extensions / service workers / private window as
  the likely cause instead of leaving the user stranded.

### Verified
- Playwright simulation: monkey-patched fetch to abort the
  stream at t+200ms (no user input). Client auto-fell back to
  non-stream and got "안녕하세요! 어떻게 도와드릴까요?" at
  t+13.4s — no "중단됨" bubble rendered.
- Regression: chat-slash-smoke / go / cost-status / pin /
  cancel all green.

---
## [2.71.114] — 2026-05-04

**QQ219 — CRITICAL FIX** — chat would render "■ 중단됨"
(AbortError) on every send despite the server completing the
stream successfully.

Root cause: the SSE handler in `server/actions.py` sent
`Connection: keep-alive`. After the SSE `done` event the kernel
held the socket open for the next request, but Python's
`BaseHTTPRequestHandler` then tripped on the next
`raw_requestline = self.rfile.readline(65537)` call (the
traceback you saw — `socketserver.py:692 process_request_thread`
→ `finish_request` → … → `readline`). The abnormal post-stream
close propagated to the browser as a connection drop, which
Chrome surfaces as `AbortError` on the in-flight fetch — even
though the response body had already arrived intact. The catch
block in `_lcChatSend` then rendered the "중단됨" bubble.

Fix:
* `Connection: close` for SSE — standard pattern for stdlib HTTP
  servers, makes the lifecycle explicit.
* `handler.close_connection = True` hint so `BaseHTTPRequestHandler`
  doesn't try the next-request read.
* `_sse()` wrap separately catches `BrokenPipeError` /
  `ConnectionResetError` / `OSError` on both `write()` and
  `flush()` so client disconnects don't surface as 500.

### Verified
- Direct curl `POST /api/lazyclaw/chat/stream` returns clean
  token + done events.
- Server stderr after the stream — clean, no traceback.

### Action required for users seeing "중단됨"
1. Restart the dashboard server (`lsof -ti:<port> | xargs kill;
   make run`).
2. **Hard-reload the browser** (Cmd+Shift+R) to drop any cached
   pre-fix `app.js`.

---
## [2.71.113] — 2026-05-04

**QQ218 — CRITICAL FIX** — chat send was broken for any input
that *looked* like a slash command (`/anything`).

QQ198 made `_lcChatSlashCommand` async, but the call site in
`_lcChatSend` (line 28997) wasn't updated:

```js
// before (broken since QQ198):
if (text.startsWith('/') && _lcChatSlashCommand(text)) { ... }
```

`_lcChatSlashCommand(text)` now returns a `Promise`, which is
always truthy. So every `/`-prefixed message was eaten by the
slash early-return, including legitimate slashes whose handler
returned `false` (deferring to the LLM) and unknown slashes
whose toast path was supposed to also let the input through to
the unknown-cmd warn. Adding `await` resolves the Promise to
the real boolean.

```js
if (text.startsWith('/') && (await _lcChatSlashCommand(text))) { ... }
```

(Plain non-slash chat sends were unaffected, but related catch
paths could surface "중단됨" if the server-side endpoint chain
errored — see "if you still see 중단됨" below.)

### If you still see "중단됨" after upgrading

The "중단됨" surface comes from the `AbortError` catch path in
`_lcChatSend`. Most common cause: the dashboard server hasn't
been restarted since `/api/lazyclaw/chat/stream` (added v2.66.66
on 2026-05-02) was introduced. The new `dist/app.js` POSTs to
that endpoint; an older `server.py` returns 404, the fallback
also 404s, and the error chain may surface as the abort message
on some browsers. **Restart the server** (kill the existing
`python3 server.py` PID and `make run` / `python3 server.py`
fresh) and the chat will work.

### Verified
- 19-script chat-slash regression sweep all green
  (smoke, go, cost-status, pin, branch, temperature, keys,
  usage, cancel, workflows, run, tab-complete x2, unknown,
  clear-n, help-grouped, refresh, uptime, whoami).
- Manual: regular "hello there" send + `/help` directly,
  both routed correctly post-fix.

---
## [2.71.112] — 2026-05-04

**QQ217** — `lazyclaude refresh` (alias `reload`) terminal verb
parity with chat `/refresh` (QQ216). Same effect: clears the
`_apiCache` Map, prints `cache cleared (N entries)`. Doesn't
reload the page.

KNOWN_VERBS / did-you-mean candidates / Tab-suggest /
help-grouped Terminal section all extended.

### Verified
- `e2e-terminal-refresh.mjs` 5/5 ✅ (cache-cleared output,
  alias, help listing, Tab expansion, typo did-you-mean).
- Regression: terminal-set-prefs / builtins-smoke /
  help-grouped / tab-suggest-new / cancel / keys-usage /
  workflows-run / uptime + chat-slash-refresh all green.

---
## [2.71.111] — 2026-05-04

**QQ216** — `/refresh` (alias `/reload`) chat slash. Busts the
client-side `_apiCache` Map so the next `/workflows`,
`/agents`, `/keys`, `/sessions` etc. refetches fresh data.
Doesn't reload the page — useful when you know server state
changed (e.g. you saved a workflow in another tab) but the
30s-cached UI hasn't propagated yet.

* Toast: `🔄 캐시 비움 (N 항목)` (ok kind).
* `/reload` is an alias.
* `/help` updated; tab-complete + Levenshtein vocabs both
  extended.

### Verified
- `e2e-chat-slash-refresh.mjs` 7/7 ✅ (cache-hot baseline,
  toast, post-refresh refetch, alias, /ref<Tab> expansion,
  /help listing).
- Regression: chat-slash-{tab-complete-new, tab-complete,
  unknown, workflows} + help-grouped all green.

---
## [2.71.110] — 2026-05-04

**QQ215** — terminal Tab-suggest (`_lcTermSuggest`) was the
**fourth** stale glue list missed during QQ198-QQ211 (after
QQ212 caught the chat-side ones). `lazyclaude wh<Tab>` was
silently a no-op even though `lazyclaude whoami` was fully
implemented.

Now extended to cover all new verbs:

* `lazyclaude {whoami,keys,uptime,workflows,run,cancel,usage}`
  + the `lz` shorthand variants.
* `lazyclaude usage 7` / `usage 30` quick presets.
* `lazyclaude help workflow` / `help cost` / `help provider`
  for the QQ214 filter form.

### Verified
- `e2e-terminal-tab-suggest-new.mjs` 8/8 ✅ (single-match
  expansions, multi-candidate `lazyclaude w<Tab>` listing,
  `help w<Tab>` filter expansion).
- Regression: terminal-set-prefs, builtins-smoke,
  help-grouped, cancel, keys-usage, workflows-run, uptime
  all green.

---
## [2.71.109] — 2026-05-04

**QQ214** — `lazyclaude help` now uses the same section-grouped
+ filterable shape as chat `/help` (QQ213). Six groups —
Preferences, Navigation, Workflow, Provider / Status,
Cost / Version, Terminal — with an alias blob per group so
`lazyclaude help cost` matches via "cost usage version uptime"
even though `usage` doesn't have "cost" in its row.

* Bare `help` keeps the trailing Sections / Examples / Shell
  whitelist / Tab-autocomplete trailer.
* Filtered `help` drops the trailer (filter is about commands).
* No match → `⚠ no match: <q>`.

### Verified
- `e2e-terminal-help-grouped.mjs` 19/19 ✅ (six group headers,
  trailer presence/absence, alias matching for "cost",
  no-match warn, cmd-name partial like "diag").
- Regression: terminal-set-prefs / builtins-smoke /
  workflows-run / keys-usage / cancel + uptime + whoami
  all green.

---
## [2.71.108] — 2026-05-04

**QQ213** — `/help` is now section-grouped + filterable. The
flat list had grown to ~25 rows after QQ198-QQ211; section
headers (Session, AI 프로바이더 / 모델, 워크플로우, 비용 /
상태, 탐색 / 외관) make it scannable, and `/help <filter>`
narrows to matching rows.

The filter matches against `cmd + desc` for individual rows
and against a romanised alias blob per section ("workflow
workflows wf run cancel" etc.) so an English query like
`/help workflow` filters the Korean 워크플로우 group without
having to type Korean. `/help no-such` warns "일치하는 명령
없음".

Bare `/help` keeps the trailing keyboard-shortcuts section;
filtered `/help` drops it (the filter is about commands).
Also added `Tab — 슬래시 자동완성` to the shortcut list.

### Verified
- `e2e-chat-help-grouped.mjs` 16/16 ✅ (group headers, every
  added command listed, English-query→Korean-section
  filtering, no-match warn, filter mode hides shortcuts).
- Regression: 17 chat-slash + adjacent tests all green
  (smoke, go, cost-status, pin, branch, temperature, keys,
  usage, cancel, workflows, run, uptime, whoami,
  tab-complete + new, unknown, clear-n).

---
## [2.71.107] — 2026-05-04

**QQ212** — Tab-completion vocab + unknown-command
Levenshtein hint vocab were both stale. They listed only the
QQ62-QQ151 commands and missed every chat slash added in
QQ198-QQ211: `/whoami`, `/pin`, `/unpin`, `/branch`, `/fork`,
`/temperature`, `/temp`, `/keys`, `/providers`, `/usage`,
`/workflows`, `/wfs`, `/run`, `/cancel`, `/uptime`. So
`/who<Tab>` did nothing and `/whoam` (typo) didn't suggest
`/whoami`.

Both lists now extended + a comment cross-referencing them
so the next slash addition only needs three edits in
`dist/app.js` (switch case + tab-complete cmds + Levenshtein
known) instead of silently degrading these UX paths.

### Verified
- `e2e-chat-slash-tab-complete-new.mjs` 16/16 ✅ (single-match
  expansion for 11 new commands, multi-cycle for /te and /w
  prefixes, typo→suggestion for /whoam and /upitme).
- Regression: chat-slash-tab-complete (the original) +
  chat-slash-unknown / smoke / go / cancel + uptime all green.

---
## [2.71.106] — 2026-05-03

**QQ211** — `/uptime` chat slash + `lazyclaude uptime`
terminal verb. Both surface server uptime, version, and start
timestamp from the existing `/api/version` payload (which
already exposes `serverStartedAt`). Format: `Nd Nh Nm Ns`
elapsed counter, ISO timestamp, version chip.

`KNOWN_VERBS` / did-you-mean candidates / chat `/help` /
`lazyclaude help` all extended.

### Verified
- `e2e-uptime.mjs` 9/9 ✅ (chat + terminal output, /help
  listings, did-you-mean for `uptiime` typo).
- Regression: chat-slash-cancel / terminal-cancel /
  terminal-set-prefs / whoami all green.

---
## [2.71.105] — 2026-05-03

**QQ210** — `lazyclaude cancel [runId|wf]` terminal verb
parity with chat `/cancel` (QQ209). Same resolution rules:
exact runId / runId-prefix / wf-id-or-name (when
unique-running). No arg → "Running runs (N)" listing or
"(no workflows currently running)" line.

`KNOWN_VERBS`, did-you-mean candidates, and
`lazyclaude help` all extended.

### Verified
- `e2e-terminal-cancel.mjs` 9/9 ✅ (no-arg list, bogus warn,
  runId POST + body validation, help listing,
  did-you-mean for `cancl` typo).
- Regression: terminal-set-prefs / builtins-smoke /
  workflows-run / keys-usage + chat-slash-cancel all green.

---
## [2.71.104] — 2026-05-03

**QQ209** — `/cancel` chat slash. Cancels a running workflow
without leaving chat, completing the run/cancel cycle that
QQ207's `/run` started.

* `/cancel` (no arg) — lists every workflow with a live run.
  Empty → `실행 중인 워크플로우 없음` warn.
* `/cancel <runId>` — full-format runId is posted directly,
  even if `/api/workflows/list` lags behind the orchestrator
  (the server-side `run-cancel` is a no-op for finished runs,
  so this is safe).
* `/cancel <prefix>` — runId-prefix match against the live
  list.
* `/cancel <wf-id-or-name>` — when the matched workflow has
  exactly one running run, cancels it. Multiple → "여러 개
  일치 — runId 로 지정하세요" warn.
* No match → `일치하는 실행 없음` warn.
* `/help` updated.

### Verified
- `e2e-chat-slash-cancel.mjs` 9/9 ✅ (seeded run, list,
  bogus-no-POST, runId-POST + body validation, /help).
- Regression: chat-slash-{run,workflows} +
  terminal-workflows-run + run-cancel-api +
  fail-fast-status all green.

---
## [2.71.103] — 2026-05-03

**QQ208** — terminal parity for the chat `/workflows` (QQ206)
and `/run` (QQ207) slashes:

* `lazyclaude workflows [filter]` — listing with `🟢` live
  marker + `Nn Nr ok|err|running` summary chips.
* `lazyclaude run <id|name>` — same exact-id → id-prefix →
  name-substring resolution. Multiple matches → list.
  Unique → POST `/api/workflows/run`, prints workflow + run
  id + `lazyclaude open workflows` watch hint.

`KNOWN_VERBS`, did-you-mean candidates, and `lazyclaude help`
all extended. Added `wfs` alias.

Also QQ207's e2e was hardened with a unique per-run name tag
(`qq207-runslash-<timestamp>-<rand>`) so repeated test
invocations don't accumulate ambiguous matches against the
same fixture name.

### Verified
- `e2e-terminal-workflows-run.mjs` 13/13 ✅ (listing,
  filter, no-arg-warn, unique POST, ambiguous, no-match,
  help, did-you-mean for typo).
- `e2e-chat-slash-run.mjs` 10/10 ✅ (after the unique-tag fix).
- Regression: terminal-set-prefs / builtins-smoke / keys-usage,
  chat-slash-workflows, whoami all green.

---
## [2.71.102] — 2026-05-03

**QQ207** — `/run <id|name>` chat slash. Kicks off a workflow
without leaving chat. Resolves the argument by exact id match,
then id-prefix, then name substring (case-insensitive). The
success bubble shows workflow + runId so the user can `/go
workflows` to watch it live.

* No arg → usage hint toast.
* No match → `일치하는 워크플로우 없음` warn.
* >1 match → list bubble (no POST), user re-tries with a
  more specific identifier.
* Unique match → POST /api/workflows/run, bubble shows
  workflow id + runId + pointer to /go workflows.
* Uses raw `api()` (not the 30s-cached helper) so a workflow
  saved seconds ago is immediately runnable.
* Invalidates `/api/workflows/list` cache on success so
  `/workflows` shows the live indicator immediately.
* `/help` updated.

### Verified
- `e2e-chat-slash-run.mjs` 10/10 ✅ (no-arg, unique-name
  POST, bubble content, no-match, ambiguous-listing,
  /help listing).
- Regression: chat-slash-{workflows,keys,cost-status,go,
  pin} + tabs-smoke 66/66 all green.

---
## [2.71.101] — 2026-05-03

**QQ206** — `/workflows` (alias `/wfs`) chat slash. Lists every
workflow with running/total run counts + a status chip for the
most recent run (✅ ok · ❌ err · 🟢 running). Same filter
shape as `/tabs`, `/sessions`, `/agents`, `/keys` — substring
match against name / id / tag, no-match → warn toast,
`(N/total · "filter")` header.

* Filter searches name, id, AND tags.
* `🟢` row prefix flags any workflow with a live run.
* CAP=30 lines + overflow note.
* Footer points to `/go workflows` for actual editing.
* `/help` lists both forms.

### Verified
- `e2e-chat-slash-workflows.mjs` 8/8 ✅.
- Regression: chat-slash-{keys,usage,clear-n,pin,cost-status,
  go,smoke} all green.

---
## [2.71.100] — 2026-05-03

**QQ205** — `/clear N` drops the last N messages of the
current session (openclaw-style undo). Pure positive-integer
match, so it doesn't collide with `/clear all` (token match)
or bare `/clear` (whole-session clear with confirm).

* `/clear 2` → drops the last 2 messages.
* `/clear 99` on a 4-message session → drops all 4 (clamped).
* `/clear 3` on an empty session → `비울 메시지가 없습니다` warn.
* No confirm needed for the partial-clear path — it's a much
  smaller blast radius than wiping the whole session.
* `/help` now reads `/clear · /clear N · /clear all`.

### Verified
- `e2e-chat-slash-clear-n.mjs` 8/8 ✅.
- Regression: chat-clear-all / chat-clear-empty +
  chat-slash-{cost-status,smoke,go,pin} all green.

---
## [2.71.99] — 2026-05-03

**QQ204** — terminal parity for the chat `/keys` (QQ202) and
`/usage` (QQ203) slashes:

* `lazyclaude keys` — providers + `(cli)` / `(api)` chip +
  `key=…mask` / `key=(missing)` for api-type providers.
* `lazyclaude usage [N]` — total USD + call count + top-3
  models. Default 7d, integer arg 1-365, out-of-range
  emits `⚠ 범위 밖`.

Also extended the `KNOWN_VERBS` + did-you-mean candidate
lists so `lazyclaude kez` Levenshtein-suggests `keys`.

`lazyclaude help` lists both new verbs.

### Verified
- `e2e-terminal-keys-usage.mjs` 11/11 ✅.
- Regression: terminal-set-prefs / builtins-smoke +
  chat-slash-keys / usage / whoami all green.

---
## [2.71.98] — 2026-05-03

**QQ203** — `/usage [N]` chat slash. Where `/cost` shows the
*current session* totals, `/usage` aggregates across **all**
sessions via the existing `/api/cost-timeline/summary?days=N`
endpoint. Default 7-day window; integer arg 1-365.

* Renders total USD + call count + top-3 model breakdown +
  per-day list (last 14 entries max).
* Out-of-range arg → `범위 밖: N (1 ~ 365)` warn, endpoint
  not called.
* Endpoint failure / `ok=false` → `비용 데이터를 가져오지 못
  했습니다` warn.
* Empty data → "_아직 기록된 호출이 없습니다_" footer.
* `/help` updated.

### Verified
- `e2e-chat-slash-usage.mjs` 8/8 ✅ (default window,
  explicit N, range guard, no-endpoint-call on bad input,
  /help listing).
- Regression: chat-slash-{keys,temperature,pin,branch,
  cost-status,go} + whoami all green.

---
## [2.71.97] — 2026-05-03

**QQ202** — `/keys` (alias `/providers`) chat slash. Lists every
registered provider with availability + (for `api`-type) API
key status, showing whatever `/api/ai-providers/list` returns
in `apiKeys` (already pre-masked server-side, e.g. `sk-…abc`).
Filter accepts a substring against id/name (parity with
`/agents`, `/sessions`, `/tabs`). Footer points users at
`/go ai` for actual key configuration.

* `❌` for unavailable providers, `🔑 …mask` for keyed apis,
  `⚠ 키 없음` for missing api keys, `(cli)` chip for CLIs
  (no key needed).
* No-match → `일치하는 프로바이더 없음` warn toast.
* `/help` updated.

### Verified
- `e2e-chat-slash-keys.mjs` 10/10 ✅.
- Regression: chat-slash-{pin,branch,temperature,cost-status,
  go,unknown,smoke} + whoami all green.

---
## [2.71.96] — 2026-05-03

**QQ201** — `/temperature` (and alias `/temp`) chat slash. Read
or set `CC_PREFS.ai.temperature` without leaving the chat. The
numeric path goes through the existing `setPref()` helper, so
the value persists to `/api/prefs/set` (debounced 250ms) and
shows up immediately in the quick-settings slider. Range
clamped to [0, 2] to match the schema.

* `/temperature` (no arg) — echo current value.
* `/temperature <n>` — set; out-of-range emits
  `범위 밖: n (0 ~ 2)` warn.
* `/temp` alias.
* `/help` updated.

### Verified
- `e2e-chat-slash-temperature.mjs` 9/9 ✅ (read, set, alias,
  range guard, backend persistence, /help listing).
- Regression: chat-slash-{pin,branch,cost-status,smoke,go,
  unknown} + whoami + terminal-set-prefs all green.

---
## [2.71.95] — 2026-05-03

**QQ200** — `/branch` and `/fork` chat slash commands. Reuses
the existing `_lcBranchFrom` plumbing (per-message 🍴 button)
so lineage chip + parentId metadata stay consistent.

* `/branch` (no arg) → full clone of the current session
  (branches from the last message).
* `/branch N` → branches from message #N (1-based, matching
  `/code` / `/copy` convention). Out-of-range emits
  `범위 밖: N / total` warn.
* `/fork` is an alias.
* `/help` updated.

### Verified
- `e2e-chat-slash-branch.mjs` 9/9 ✅.
- Regression: `e2e-chat-branch` (per-message 🍴) +
  `e2e-chat-slash-{pin,cost-status,smoke,go,unknown}` +
  `e2e-whoami` all green.

---
## [2.71.94] — 2026-05-03

**QQ199** — `/pin` and `/unpin` chat slashes (openclaw-style
session pinning). Toggle a `pinned` flag on the current
session; `/sessions` then sorts pinned sessions above
unpinned (after the active one) and prepends a 📌 marker.
Persisted via the existing sessions array — no new storage
key, no migration needed.

* `/pin` on already-pinned → "이미 고정된 세션입니다" warn.
* `/unpin` on unpinned → "고정되지 않은 세션입니다" warn.
* `/help` lists both.

### Verified
- `e2e-chat-slash-pin.mjs` 8/8 ✅ (sets/clears flag, sorts
  pinned above other in /sessions, 📌 marker, idempotent
  toasts, /help listing).
- No regressions: chat-slash-cost-status / smoke / go /
  sessions-cap / whoami all green.

---
## [2.71.93] — 2026-05-03

**QQ198** — `/whoami` chat slash + `lazyclaude whoami` terminal
verb (openclaw-style identity introspection). Both surface
Claude CLI login state — email, plan label, organization,
`claude --version` — pulled from the existing
`/api/auth/status` server-side memo. Graceful fallback when not
logged in points the user at `claude auth login`.

Also fixes a static-cache bug uncovered while testing this:
`server/routes.py` keyed the `index.html` cache entry only on
its own mtime, but the cache-buster query string is derived
from `app.js`'s mtime. Editing `app.js` without touching
`index.html` served a stale `?v=` tag, so the browser kept
running the previous app.js. The cache key now includes both
mtimes for `index.html`.

* Chat: `/whoami` (also added to `/help` listing).
* Terminal: `lazyclaude whoami` + appended to `lazyclaude help`.
* Both share the same `/api/auth/status` (cached, ~5ms warm).
* `_lcChatSlashCommand` is now `async` to support the await on
  the auth fetch — no behaviour change for existing callers
  (they already discarded the return value or ignored the
  promise).

### Verified
- `e2e-whoami.mjs` 6/6 ✅ (chat + terminal + help listing).
- No regressions: chat-slash-smoke / go / cost-status /
  tab-complete / unknown / code / commands all green;
  tabs-smoke 66/66; terminal-set-prefs 30/30.

---
## [2.71.92] — 2026-05-03

**QQ197** — `e2e-rubber-band` now scrolls `#wfCanvasHost` into
view before computing the shift-drag pixel rectangle. Same
root cause as QQ196 group-drag: the workflows tab renders a
list view above the canvas, so the SVG can sit below the
1200px viewport (y~1070). Without scroll, the screen-space
rectangle landed off the canvas and selected nothing.

After this, the comprehensive sweep (~80 e2e scripts) is
fully green: tabs-smoke 66/66, all chat slash commands,
all workflow + node + multi-select + canvas interactions,
all cache-perf scripts, all terminal/UI/perf budgets.

### Verified
- `e2e-rubber-band.mjs` 4/4 ✅.
- ~80-script sweep — no failures.

---
## [2.71.91] — 2026-05-03

**QQ196** — Stabilise three more e2e scripts that flaked on
environmental noise.

* `e2e-ports-list-cache` — `nocache=1` and post-TTL hits do
  real `lsof` calls, but the OS file-table page cache makes
  the second `lsof` ~30% faster than the cold one. The old
  assertion `t3 ≥ t1 - 80` busted whenever the cold call was
  unusually slow. Replaced with `t3 > t2 * 4` ("much slower
  than cached") which captures the actual invariant.
* `e2e-auth-status-cache` — same in-browser timing fix as
  QQ194/QQ195. Wallclocked Playwright overhead alone could
  bust the 200ms team-tab budget.
* `e2e-group-drag` — the workflows tab renders a list view
  above the canvas, so `#wfCanvasHost` can sit below the
  1200px viewport (y~1070). The mouse drag missed the
  off-screen node entirely. Added `scrollIntoView` +
  `_wfFitView()` after injecting the test workflow.

### Verified
- `e2e-ports-list-cache.mjs` 3/3 ✅.
- `e2e-auth-status-cache.mjs` 3/3 ✅.
- `e2e-group-drag.mjs` 4/4 ✅.

---
## [2.71.90] — 2026-05-03

**QQ195** — Stabilise two cache-perf e2e scripts that flaked
on transient state.

* `e2e-cache-refresh-loop` — Node's first `fetch()` per process
  pays ~70-90ms of one-time DNS/TCP/agent setup. Add a
  throwaway `/api/version` hit + warm both target endpoints so
  the `boot+` assertion measures cache hot/cold state, not Node
  fetch init. Also absorbs transient `~/.claude.json` mtime
  invalidations.
* `e2e-cli-status-cache` — measure tab-switch latency
  in-browser via `performance.now()` (mirrors QQ194). Also
  double-warm aiProviders + workflows before measuring, so the
  AFTER-hook lazy-init (ollama catalog, health, cost charts)
  doesn't dominate the first measured switch.

### Verified
- `e2e-cache-refresh-loop.mjs` 4/4 ✅.
- `e2e-cli-status-cache.mjs` 3/3 ✅ (aiProviders 103/104ms).

---
## [2.71.89] — 2026-05-03

**QQ194** — `e2e-tab-switch-budget` now measures latency
inside the browser via `performance.now()` instead of
wallclocking `page.evaluate` + `waitForFunction` from the
Node side. The previous methodology added ~250-300ms of
Playwright/CDP poll overhead on every tab, which falsely
flagged `aiProviders` (legitimately ~230ms in-browser) as
busting the 300ms budget. With honest timing, all 10 tabs
land within budget: aiProviders 256ms · sessions 181ms ·
lazyclawChat 176ms · others <60ms.

### Verified
- `e2e-tab-switch-budget.mjs` 10/10 ✅.

---
## [2.71.88] — 2026-05-03

**QQ193** — Stabilise `e2e-chat-slash-cost-status.mjs` against
the deferred `setTheme` renderView teardown. Both `/theme`
toggle and `/theme dark` schedule a +550ms `renderView()` that
removes `#lcChatInput` mid-flight; the next `slash()` call hit
a null textarea. Mirrors QQ123: insert a 1300ms wait +
`waitForFunction(#lcChatInput)` between `/theme*` and the next
slash. All 34 checks now stable.

### Verified
- `e2e-chat-slash-cost-status.mjs` 34/34 ✅.

---
## [2.71.87] — 2026-05-03

**QQ192** — `/tabs [filter]` chat slash matches the QQ191
terminal `lazyclaude tabs <filter>` UX. Header shows
`(N/total · "filter")`. No-match toasts "일치하는 탭 없음".
All four list-style verbs (`/agents`, `/sessions`, `/tabs`,
`lazyclaude tabs`) now share consistent filter UX.

`/help` updated.

### Verified
- `e2e-chat-slash-go.mjs` extended from 14 → 16 checks.

---
## [2.71.86] — 2026-05-03

**QQ191** — `lazyclaude tabs <filter>` accepts a substring
filter (parity with QQ189 `/agents` and QQ190 `/sessions`).
Header shows `# N/total · "filter"`. No-match prints "⚠ 일치
하는 탭 없음".

### Verified
- `e2e-terminal-set-prefs.mjs` extended from 28 → 30 checks:
  filter narrows the listing, no-match emits the warning.

---
## [2.71.85] — 2026-05-03

**QQ190** — `/sessions [filter]` accepts a substring filter
matching label/id/assignee. Mirrors the QQ189 `/agents`
filter UX: `/sessions sess-04` shows the 10 matching sessions
with header `(10/50 · "sess-04")`. No-match case toasts "일치
하는 세션 없음".

`/help` updated.

### Verified
- `e2e-chat-sessions-cap.mjs` extended from 4 → 6 checks.

---
## [2.71.84] — 2026-05-03

**QQ189** — `/agents [filter]` accepts a substring filter so
users with many registered assignees (Ollama models alone can
hit 30+) can narrow down: `/agents claude` shows only the 4
Claude variants. Output also caps at 30 with the same overflow
note as QQ188 `/sessions`. No-match case toasts "일치하는
어시니 없음" instead of dumping a 0-result list. Header reflects
filter context: `(4/14 · "claude")`.

`/help` updated.

### Verified
- `e2e-chat-slash-cost-status.mjs` extended from 31 → 34 checks:
  filtered header, non-claude assignees suppressed, no-match
  toast.

---
## [2.71.83] — 2026-05-03

**QQ188** — `/sessions` caps at 30 entries with an overflow line
"_… N 개 더_". Active session is pinned to the top so it's
always in the rendered chunk regardless of where it lives in
storage. Power users with 50-100+ sessions no longer get a
wall of text dumped into chat.

### Verified
- `scripts/e2e-chat-sessions-cap.mjs` — 4/4 green: 50-session
  seed produces ≤30 visible lines, active session-025 pinned in
  the rendered chunk, "20 개 더" overflow line, header count 50.

---
## [2.71.82] — 2026-05-03

**QQ187** — extended `e2e-chat-slash-smoke` to cover the QQ182
`/tabs` slash and the QQ184 `/code N` form. Together with
QQ178/QQ186, the chat slash + terminal builtin surfaces are
now end-to-end covered: parser + autocomplete + side-effects.

### Verified
- `e2e-chat-slash-smoke.mjs` extended from 12 → 14 checks.

---
## [2.71.81] — 2026-05-03

**QQ186c** — terminal smoke now also exercises `lz set` (alias
write) and `lz reset` (alias side-effect). Together with QQ186b,
every `lz` verb now has end-to-end coverage: autocomplete,
parser, side-effect.

### Verified
- `e2e-terminal-builtins-smoke.mjs` extended from 15 → 17:
  `lz set ui density comfortable` round-trips to CC_PREFS and
  `lz reset` clears the log.

---
## [2.71.80] — 2026-05-03

**QQ186b** — terminal smoke regression (QQ179) extended to also
exercise `lz version` / `lz status` / `lz tabs` / `lz get ui`
through the actual handler, not just the autocomplete list. So
QQ186 is locked end-to-end now: autocomplete surfaces lz
candidates AND the parser routes them client-side.

### Verified
- `e2e-terminal-builtins-smoke.mjs` extended from 11 → 15
  checks. All shell-short-circuit assertions still green.

---
## [2.71.79] — 2026-05-03

**QQ186** — `lz` autocomplete suggested only `lz get` and
`lz set`. The `lz` shorthand is supposed to be a faster alias
for every `lazyclaude` verb, but Tab couldn't surface most of
them. Added `lz help/version/status/tabs/reset/diag/open
chat|wf|term|ai`. `lz<Tab>` now returns 12 candidates.

### Verified
- Manual probe: `lz` → 12, `lz s` → 2, `lz h` → 1, `lz d` → 1,
  `lz o` → 4.

---
## [2.71.78] — 2026-05-03

**QQ185** — `/copy N` out-of-range now gets a dedicated
`"범위 밖: N / total"` toast instead of the generic `"복사할
응답이 없습니다"`. Matches the QQ184 `/code N` semantics so
both N-arg slashes report failures the same way.

### Verified
- `e2e-chat-slash-cost-status.mjs` extended from 30 → 31 checks:
  `/copy 99` on a 1-reply session toasts "범위 밖" with the
  count.

---
## [2.71.77] — 2026-05-03

**QQ184** — `/code [N]` accepts an N argument now (1-indexed) so
users can pick a specific code block when an assistant reply
returned several. Out-of-range N toasts "범위 밖: N / total".
Default (no N) still picks the last block (QQ171 contract).

`/help` updated to reflect the new arg syntax.

### Verified
- `e2e-chat-slash-code.mjs` extended from 4 → 7 checks: pick
  2nd block, pick 1st block, out-of-range toast.

---
## [2.71.76] — 2026-05-03

**QQ183** — Playwright regression locking in the QQ122 `/copy`
fallback path. When `navigator.clipboard` is undefined (older
browsers, http origins, permission-denied), the slash command
must use the textarea + `document.execCommand('copy')` shim
instead of crashing.

### Verified
- `e2e-chat-slash-cost-status.mjs` extended from 29 → 30 checks.
  Stubs `navigator.clipboard = undefined`, runs `/copy`, asserts
  the success toast still fires.

---
## [2.71.75] — 2026-05-03

**QQ182** — `/tabs` chat slash command. Lists every NAV id +
emoji + label so users can pick a target for `/go`. Parity
with the terminal `lazyclaude tabs` (QQ142). `/help` lists it,
Tab autocomplete and unknown-slash heuristic learn about it.

### Verified
- `e2e-chat-slash-go.mjs` extended from 12 → 14 checks: `/tabs`
  lists `workflows` and `lazyclawChat`.

---
## [2.71.74] — 2026-05-03

**QQ181** — extended `/go` (chat) and `lazyclaude open`
(terminal) alias maps with common navigation aliases the user
might type:

```
home / dashboard / overview      → overview
mem / memory                     → memoryManager
ar / autoresume                  → autoResumeManager
ports                            → openPorts
agents / mcp / hooks             → as named
chat                             → lazyclawChat
```

Chat and terminal alias maps stay aligned.

### Verified
- `e2e-chat-slash-go.mjs` extended from 8 → 12 checks: 4 new
  alias roundtrips (home, mem, ports, ar). All green.

---
## [2.71.73] — 2026-05-03

**QQ180b** — Playwright regression for the QQ180 autocomplete
fix. Locks in `_lcTermSuggest` returning the new `diag`,
`tabs`, and `open` candidates so a future refactor can't drop
them silently.

### Verified
- `e2e-terminal.mjs` extended from 4 → 7 checks: `lazyclaude di`
  → `diag`, `lazyclaude ta` → `tabs`, `lazyclaude op` returns
  ≥3 candidates.

---
## [2.71.72] — 2026-05-03

**QQ180** — terminal Tab autocomplete suggestion list missed
the QQ142 `open` and QQ150 `diag` builtins (and `tabs`).
Hitting Tab after `lazyclaude di`/`ta`/`op` now expands as
expected.

### Verified
- Manual probe: `lazyclaude di` → `lazyclaude diag`,
  `lazyclaude ta` → `lazyclaude tabs`, `lazyclaude op` cycles
  through `open`, `open chat`, `open wf`, `open term`,
  `open ai`, `open settings`.

---
## [2.71.71] — 2026-05-03

**QQ179** — companion to QQ178: comprehensive smoke for every
`lazyclaude <verb>` terminal built-in. Asserts each verb routes
to client-side handler (zero `/api/lazyclaw/term` hits) and the
terminal DOM survives. Also round-trips a `set ui density
compact` to verify the prefs API integration sticks.

### Verified
- `scripts/e2e-terminal-builtins-smoke.mjs` — 11/11 green
  covering help/--help/version/--version/status/tabs/get(×3)/
  lz-help + a set/get round-trip.

---
## [2.71.70] — 2026-05-03

**QQ178** — comprehensive smoke regression for every chat slash
command. Runs each non-destructive verb (help/cost/status/
agents/sessions/system/code/copy/version + /rename) once, asserts
`_lcChatSlashCommand` returns `true` and the chat DOM survives.
Catches the class of bugs where a new verb throws or silently
returns false (forgotten case label).

### Verified
- `scripts/e2e-chat-slash-smoke.mjs` — 12/12 green covering 11
  verbs + the /rename round-trip.

---
## [2.71.69] — 2026-05-03

**QQ177** — `/cost` on a session with no recorded token metadata
used to show `$0.000000`, which looked like a precision bug. Now
displays `$0` plus an italic helper line "(이 세션에는 토큰·비용
메타데이터가 없습니다)" so the user understands the value is
literally zero, not an artefact.

### Verified
- `e2e-chat-slash-cost-status.mjs` extended from 27 → 29 checks.
  No-meta session displays `$0` (not `$0.000000`) and renders the
  metadata-missing note.

---
## [2.71.68] — 2026-05-03

**QQ165b** — extended the QQ165 shortcut e2e to drive the full
flow (stub `promptModal` to auto-respond with a name, fire
Cmd+Shift+N, assert a new workflow id appears AND the name
reflects the prompted value). Cleans up the created workflow
afterwards via /api/workflows/delete.

### Verified
- `e2e-workflow-new-shortcut.mjs` extended from 3 → 5 checks.
  Locks the full happy path end-to-end.

---
## [2.71.67] — 2026-05-03

**QQ176** — robustness fix for QQ174 `/clear all`. The check
was a strict equality on `rest.trim().toLowerCase()`, so
`/clear all please` (extra trailing junk) silently fell back
to the single-session clear path. Now matches on the first
whitespace token, so the all-wipe always wins when the user
intent is clear.

### Verified
- `e2e-chat-clear-all.mjs` extended from 5 → 6 checks:
  `/clear all please` still wipes everything in one confirm.

---
## [2.71.66] — 2026-05-03

**QQ175** — `/system` is three-modal now:

```
/system           → show current prompt (was: silent clear)
/system <text>    → set prompt
/system clear     → explicit clear
```

Previously typing bare `/system` thinking "what's set?"
silently wiped the user's carefully-crafted prompt — a real
footgun. Now bare `/system` posts the current value as an
inline assistant bubble (with a `(설정되지 않음)` placeholder
if empty). Setting and clearing are unchanged otherwise.

`/help` updated.

### Verified
- `scripts/e2e-chat-system-modes.mjs` — 5/5 green: set
  persists, bare does NOT clear, displays inline, `clear`
  empties, bare on empty shows the placeholder.

---
## [2.71.65] — 2026-05-03

**QQ174** — `/clear all` chat slash. Wipes every chat session
(both `cc.lc.sessions` array and every `cc.lc.hist.*`
localStorage key) after a single confirm. Plain `/clear`
keeps the QQ173 session-scoped behaviour.

### Verified
- `scripts/e2e-chat-clear-all.mjs` — 5/5 green: seeds 3
  sessions, `/clear all` confirms once, ends with ≤1 fresh
  session, all hist keys gone, `/help` lists `/clear all`.
- `e2e-chat-clear-empty.mjs` (the QQ173 regression) still 4/4.

---
## [2.71.64] — 2026-05-03

**QQ173** — `/clear` no longer prompts for confirmation when
the session is already empty. Repeatedly invoking `/clear` on
an empty buffer (e.g. via Tab autocomplete + Enter) burned a
needless `confirm()` modal each time. Now: empty → toast "이미
비어있습니다" and noop. Non-empty → confirm + wipe (unchanged).

### Verified
- `scripts/e2e-chat-clear-empty.mjs` — 4/4 green: empty session
  fires zero confirms + warning toast; non-empty session
  confirms once and wipes history.

---
## [2.71.63] — 2026-05-03

**QQ172** — coverage extension for the QQ171 `/code` slash. Tab
autocomplete from `/co` now cycles three candidates
(`/cost`, `/copy`, `/code`); regression test extended.

### Verified
- `e2e-chat-slash-tab-complete.mjs` extended from 9 → 10 checks:
  `/co<Tab>×3` cycles all three; original 2-step assertion
  loosened to "picks one of cost/copy/code, second is different".

---
## [2.71.62] — 2026-05-03

**QQ171** — `/code` chat slash. Copies just the LAST fenced
code block from the most recent assistant reply — useful when
the answer is prose + code and you only want the snippet.
Falls back to `document.execCommand('copy')` like `/copy`.
Tab autocomplete + unknown-slash heuristic + `/help` updated.

### Verified
- `scripts/e2e-chat-slash-code.mjs` — 4/4 green: single-block
  reply copies the JS, multi-block reply copies the LAST,
  no-code reply toasts warning, `/help` listing.

---
## [2.71.61] — 2026-05-03

**QQ170** — direct Playwright coverage for the QQ163 shared
`_lcLevenshtein(a, b)` helper. The QQ161 chat / QQ162 terminal
typo suggesters depend on it returning correct edit distances;
locking the math in via dedicated tests means a stray
"optimisation" that breaks an edge case fails fast instead of
silently degrading every typo hint.

### Verified
- `scripts/e2e-levenshtein-helper.mjs` — 9/9 green:
  empty/empty, empty-vs-string, identical, single-substitute,
  single-insert (`vrsion`/`version`), single-delete, and the
  textbook `kitten`/`sitting` = 3 case.

---
## [2.71.60] — 2026-05-03

**QQ169b** — Playwright regression for the QQ169 unknown-tab
guard. Locks the contract so a future refactor that drops the
NAV check (chat or terminal) breaks a test instead of silently
poisoning `state.view`.

### Verified
- `e2e-chat-slash-go.mjs` extended from 6 → 8 checks: `/go
  bogusXYZ` doesn't change view, toast points to `/tabs`.
- `e2e-terminal-set-prefs.mjs` extended from 26 → 28 checks:
  `lazyclaude open bogusXYZ` doesn't change view, log line
  mentions unknown-tab.

---
## [2.71.59] — 2026-05-03

**QQ169** — `/go bogusXYZ` (chat) and `lazyclaude open bogus`
(terminal) used to set `state.view` to whatever the user passed
without validation. The dashboard then silently fell back to
overview on render but `state.view` stayed garbage, polluting
any code that gates on it.

Both paths now validate the resolved target against `NAV` first
and toast/print "알 수 없는 탭" pointing at `/tabs` (chat) or
`lazyclaude tabs` (terminal) when unrecognised. The user stays
on the current tab.

### Verified
- chat: `/go bogusXYZ` → toast "알 수 없는 탭: bogusXYZ — /tabs",
  `state.view` stays `lazyclawChat`.
- terminal: `lazyclaude open bogus` → log "⚠ 알 수 없는 탭: bogus
  — lazyclaude tabs", `state.view` stays `lazyclawTerm`.

---
## [2.71.58] — 2026-05-03

**QQ168** — `Cmd/Ctrl+Shift+E` on the workflow tab exports the
current workflow as JSON. Parallels the chat QQ166 export
shortcut so the same chord does "export current view" across
both. Shortcut help modal lists it.

### Verified
- `scripts/e2e-workflow-export-shortcut.mjs` — Playwright
  regression: shortcut invokes `_wfExport`, help modal lists
  `Ctrl+Shift+E`, suppressed on non-workflow tabs. 3/3 green.

---
## [2.71.57] — 2026-05-03

**QQ167** — regression test that locks in QQ164 (chat
Cmd+Shift+N) and QQ165 (workflow Cmd+Shift+N) don't bleed into
each other. Each handler gates on `state.view` so the shortcut
is a no-op on the wrong tab — but a stray refactor could
silently remove the gate.

### Verified
- `scripts/e2e-cross-tab-shortcuts.mjs` — 3/3 green: on
  workflows only `_wfCreateNew` fires, on chat only
  `_lcNewSession` fires, on overview neither fires.

---
## [2.71.56] — 2026-05-03

**QQ166** — `Cmd/Ctrl+Shift+E` exports the current chat to
markdown. Mirrors the toolbar 📥 button without forcing the
mouse. Suppressed inside input/textarea so a literal `E` still
types. `/help` updated.

### Verified
- `scripts/e2e-chat-export-shortcut.mjs` — Playwright regression:
  shortcut invokes `_lcChatExport`, suppressed inside textarea,
  `/help` lists it. 3/3 green.

---
## [2.71.55] — 2026-05-03

**QQ165** — Cmd/Ctrl+Shift+N on the workflow tab opens
`_wfCreateNew` (creates a new workflow). Mirrors the chat
QQ164 shortcut so the same chord means "new container" across
both tabs. Plain Cmd+N still opens the new-node editor (LL16).
Shortcut help modal lists both.

### Verified
- `scripts/e2e-workflow-new-shortcut.mjs` — Playwright
  regression: Cmd+Shift+N invokes `_wfCreateNew`, shortcut help
  modal lists `Ctrl+Shift+N` AND `Ctrl+N`. 3/3 green.

---
## [2.71.54] — 2026-05-03

**QQ164** — Cmd/Ctrl+Shift+N keyboard shortcut creates a fresh
chat session. Mirrors the "+ New chat" button without forcing
the user to grab the mouse. Suppressed when the focus is inside
an input/textarea so the shortcut doesn't hijack a literal
capital N. `/help` updated.

### Verified
- `scripts/e2e-chat-new-session-shortcut.mjs` — Playwright
  regression: starts with 1 session, Cmd+Shift+N creates a 2nd
  and switches to it; suppressed inside the textarea; `/help`
  lists the shortcut. 5/5 green.

---
## [2.71.53] — 2026-05-03

**QQ163** — small refactor: dedupe the duplicated Levenshtein
helper between QQ161 (chat slash typo) and QQ162 (terminal verb
typo). One `window._lcLevenshtein(a, b)` exported globally,
both call sites now reuse it.

### Verified
- `e2e-chat-slash-unknown.mjs` (15/15) and
  `e2e-terminal-set-prefs.mjs` (26/26) both still green.

---
## [2.71.52] — 2026-05-03

**QQ162** — terminal-side parity for the QQ161 Levenshtein
upgrade. The QQ147 unknown-verb suggestion used the same
Hamming-on-shorter heuristic, so `lazyclaude vrsion` couldn't
find `version`. Same fix, same threshold (≤3).

### Verified
- `e2e-terminal-set-prefs.mjs` extended from 24 → 26 checks:
  `lazyclaude vrsion → version`, `lazyclaude resett → reset`.

---
## [2.71.51] — 2026-05-03

**QQ161** — proper Levenshtein for chat slash typo suggestions.
The QQ124 Hamming-on-shorter heuristic only worked for
substitution-style typos (`/clearr`); missing-character typos
like `/vrsion`, `/seshns`, `/cot`, `/agnts` scored too high
because the walker didn't align around the gap. Replaced with
real Levenshtein edit distance — same `≤3` threshold.

### Verified
- `e2e-chat-slash-unknown.mjs` extended from 11 → 15 checks,
  covering `/vrsion → /version`, `/seshns → /sessions`,
  `/cot → /cost`, `/agnts → /agents`. All green.

---
## [2.71.50] — 2026-05-03

**QQ160** — Pin Data toggle is now undoable (third bug in the
"missing _wfPushUndo" class — see QQ134 + QQ159). `_wfTogglePin`
mutated the node directly without pushing an undo entry, so an
accidental pin/unpin from the ctx menu was permanent.

Same fix applied to `_wfToggleNodeDisabled` so the ctx-menu
disable-toggle also gets covered (QQ159 only fixed the keyboard
path; the ctx menu still went through the mutation-without-undo
path). The QQ159 keyboard handler stops pushing its own undo for
the single-select path now that the helper handles it.

`_wfTogglePin` is also now exposed on `window` (QQ109/110 pattern)
so the e2e regression can drive it.

### Verified
- `scripts/e2e-pin-undo.mjs` — 4/4 green: pin sets data, pushes
  undo, Cmd+Z removes pin, Cmd+Z after unpin restores pin.
- `e2e-multi-disable.mjs` still 5/5 green.

---
## [2.71.49] — 2026-05-03

**QQ159** — `D` keystroke (toggle disabled) is now undoable.
The QQ133 multi-select handler and the original PP2 single-node
path both forgot to call `_wfPushUndo`, so an accidental
disable-burst was permanent — Cmd+Z either went back further
than the user intended or did nothing.

Both paths now push a single undo entry so Cmd+Z restores the
pre-toggle state of the entire selection in one keystroke.

### Verified
- `e2e-multi-disable.mjs` extended from 3 → 5 checks: D disables
  both nodes, Cmd+Z restores both. All green.

---
## [2.71.48] — 2026-05-03

**QQ158** — Playwright coverage for Cmd+Z undoing a
multi-duplicate atomically. The QQ127 / QQ128 duplicate path
already pushed `_wfPushUndo` once per `_wfDuplicateNodes` call;
this regression locks that contract so a future refactor can't
accidentally make the undo step-by-step (one per cloned node).

### Verified
- `e2e-multi-duplicate.mjs` extended from 11 → 13 checks. Seeds
  n-1→n-2, multi-selects both, presses Cmd+D (now 4 nodes), then
  Cmd+Z reverts back to {n-1, n-2}. All green.

---
## [2.71.47] — 2026-05-03

**QQ157** — small consistency fix. The QQ147 did-you-mean
suggestion list inside the terminal handler was missing
`'go'` (alias of `'open'`) and `'diag'` (added later in QQ150).
Typing `lazyclaude dia` therefore couldn't suggest `diag`.

The `KNOWN_VERBS` list (which gates the parser) and the
`candidates` list (which feeds the suggestion heuristic) are
now in sync. Verified manually: `lazyclaude dia` → "혹시
lazyclaude diag?".

---
## [2.71.46] — 2026-05-03

**QQ156b** — Playwright regression for the QQ156 cache
invalidation. Locks in the contract that `_dump_all` zeroes the
status memo so a write followed immediately by a read returns
the post-write state, not stale cached data.

### Verified
- `scripts/e2e-ar-cache-invalidation.mjs` — bind a session via
  /set, /status sees `enabled:true`; cancel; /status (next call,
  no wait) sees `enabled:false, state:stopped`. 4/4 green.

---
## [2.71.45] — 2026-05-03

**QQ156** — fixed flaky `e2e-auto-resume` regression introduced by
QQ154. The 1.5s memo on `/api/auto_resume/status` returned stale
'active' entries for up to 1.5s after a `cancel` or `set`,
causing the test (and any UI polling) to see a state that didn't
match the actual store.

### Fixed
- `_dump_all` (every state-write path) now zeroes
  `_AR_STATUS_CACHE`. The next `/status` call rebuilds the cache
  with fresh data. The 1.5s TTL still de-dupes back-to-back reads;
  it just doesn't outlive a write.
- Cache decl moved above `_dump_all` so the invalidator can see it.

### Verified
- `scripts/e2e-auto-resume.mjs` re-greens: 3/3 viewports PASS
  even with 4 pre-existing bindings in the store. Cache still
  serves both cold and warm hits in < 2ms.

---
## [2.71.44] — 2026-05-03

**QQ155** — sixth perf endpoint memoised. `/api/optimization/score`
aggregates settings + 30-day quality metrics + agents/plugins/
permissions counts (~50ms cold). The Overview tab calls it on
every load. 30-day metrics change on the minute scale; a 10s
TTL coalesces tab-switch redundancy.

### Verified
- `scripts/e2e-opt-score-cache.mjs` — Playwright regression: cold
  42ms, cached 3ms, 5 back-to-back hits avg 1.4ms. 2/2 green.
- Overview tab in `e2e-tab-switch-budget` dropped from 148ms → 24ms.

---
## [2.71.43] — 2026-05-03

**QQ153 + QQ154** — extended tab-switch perf coverage and closed
a 5th cache hole.

### Fixed (QQ154)
- `/api/auto_resume/status` runs a `_live_cli_sessions()` lsof+ps
  cross-reference (~140ms) whenever at least one binding exists.
  The Sessions tab + Auto-Resume Manager poll it on a live ticker,
  so coalescing back-to-back hits at a 1.5s TTL is free latency
  for free freshness. `?nocache=1` bypass kept.

### Changed (QQ153)
- `e2e-tab-switch-budget.mjs` now also gates `workflows`,
  `lazyclawChat`, `lazyclawTerm`, `overview`, `projects`,
  `sessions` (4 → 10 tabs).
- Per-tab warm-then-measure pattern so short-TTL caches don't
  expire between warm-up and measurement.

### Verified
- 10/10 tabs under 300ms warm budget. Currently:
  aiProviders 35ms · team 16ms · memoryManager 21ms · openPorts 22ms ·
  workflows 33ms · lazyclawChat 19ms · lazyclawTerm 7ms · overview 148ms ·
  projects 17ms · sessions 31ms.

---
## [2.71.42] — 2026-05-03

**QQ152** — minor coverage extension. Added a Tab-completion
assertion for the QQ151 `/version` chat slash so the
auto-complete cycle keeps working as more verbs are added.

### Verified
- `e2e-chat-slash-tab-complete.mjs` extended from 8 → 9 checks.
  `/v<Tab>` → `/version`. All green.

---
## [2.71.41] — 2026-05-03

**QQ151** — `/version` chat slash command (parity with the
terminal `lazyclaude version` from QQ141). Hits `/api/version`
and posts a LazyClaude info bubble inline. Tab autocomplete,
`/help`, and the unknown-slash heuristic all updated.

### Verified
- `e2e-chat-slash-cost-status.mjs` extended to 27 checks (was
  24): `/help` listing includes `/version`, the bubble mentions
  the LazyClaude header and a version label. All green.

---
## [2.71.40] — 2026-05-03

**QQ150** — `lazyclaude diag` terminal builtin. Reuses the
existing `_lcTermHealthCheck` (claude/ollama/gemini/codex/git
probes) as an explicit on-demand command, so users who just
installed or updated a CLI can re-run the probe without waiting
for the 1-hour auto-fire gate.

`/help` updated.

### Verified
- `scripts/e2e-terminal-diag.mjs` — Playwright regression: clears
  the log, runs `lazyclaude diag`, asserts the health-check
  start/end markers and that each CLI probe (claude/ollama/git)
  was actually fired. 5/5 green.

---
## [2.71.39] — 2026-05-03

**QQ149** — Playwright perf budget regression for tab-switch
latency. Locks in the QQ135-QQ144 cumulative wins (cli/status,
auth/status, memory/snapshot, ports/list memos + boot prewarm +
refresh loop) so a future change can't silently re-introduce
the 750ms / 400ms / 150ms subprocess fan-outs.

### Verified
- `scripts/e2e-tab-switch-budget.mjs` — Playwright regression:
  asserts each of aiProviders / team / memoryManager / openPorts
  finishes a warm tab-switch under 300ms (default budget,
  override via `TAB_BUDGET_MS`). Currently:
    aiProviders 40ms · team 39ms · memoryManager 68ms · openPorts 21ms.
  All 4 green.

---
## [2.71.38] — 2026-05-03

**QQ148** — Ctrl+L (and Cmd+L) wipes the terminal log in place,
matching the bash convention. Distinct from `lazyclaude reset`
in that it doesn't echo a command line — just clears the screen.

### Verified
- `scripts/e2e-terminal-ctrl-l.mjs` — Playwright regression:
  fills the log via the auto-healthcheck, presses Ctrl+L, asserts
  the on-screen DOM is empty AND `localStorage` entry was removed.
  Cmd+L verified separately. 4/4 green.

---
## [2.71.37] — 2026-05-03

**QQ147** — terminal got the same did-you-mean treatment as the
chat slash commands (QQ124). `lazyclaude xet ui theme dark` used
to fall through to the shell whitelist and return a terse
"argument combination not in whitelist" — useless when the user
just typo'd `set`.

The terminal parser now matches *any* `lazyclaude <word>` /
`lz <word>` shape; if `<word>` isn't a known verb (get / set /
help / reset / version / open / tabs / status), we emit a
friendly hint with the closest match (≤ 3 edits) plus
`lazyclaude help`. Stays client-side, never hits the shell.

### Verified
- `e2e-terminal-set-prefs.mjs` extended to 24 checks (was 21):
  the typo warning fires, suggests SOME known verb, and never
  hits `/api/lazyclaw/term`. `e2e-terminal.mjs` still 4/4.

---
## [2.71.36] — 2026-05-03

**QQ146** — bare `/` (or `/   ` whitespace-only) on its own line
no longer leaks to the LLM. The QQ124 unknown-command guard
required at least one alphanumeric letter (`/x`) to swallow,
so a stray `/` ended up shipped to the provider.

Now any all-whitespace input that starts with `/` is swallowed
locally with a `/help` hint toast.

### Verified
- `e2e-chat-slash-unknown.mjs` extended from 8 → 11 checks
  (bare `/` swallowed, toast points to `/help`, `/   ` swallowed
  too). All green.

---
## [2.71.35] — 2026-05-03

**QQ145** — `lazyclaude status` terminal builtin; also restores
the `lazyclaude status` autocomplete entry that QQ141 dropped.

The shell whitelist *did* allow `lazyclaude status` but
`shutil.which("lazyclaude")` returns nothing on most systems, so
running it ended in `lazyclaude not installed`. Intercepting it
client-side prints a useful one-screen summary instead — version,
current theme/lang, default model, temperature, active tab.

`/help` updated.

### Verified
- `e2e-terminal-set-prefs.mjs` extended to 21 checks (was 18) —
  `lazyclaude status` prints the header, mentions theme + lang,
  and never hits the shell.
- `e2e-terminal.mjs` re-greens (4/4): the autocomplete suggestion
  for `lazyclaude sta` → `lazyclaude status` works again.

---
## [2.71.34] — 2026-05-03

**QQ144** — fourth subprocess-bound endpoint memoised.
`/api/ports/list` shells out to `lsof` for both TCP-listen and
UDP probes (50-150ms on a busy box). The Open Ports tab polls
this on a live ticker.

### Fixed
- 3s server-side memo for `/api/ports/list` in
  `server/process_monitor.py`. Open ports change on a
  human-noticeable timescale (seconds), so 3s feels live and
  still coalesces every redundant tick. `?nocache=1` bypass.

### Verified
- `scripts/e2e-ports-list-cache.mjs` — Playwright regression:
  cold ≈ 159ms, cached = 2ms, `?nocache=1` re-probes at 129ms,
  TTL expires correctly after 3s. 3/3 green.

### Cumulative tab-switch wins
| Endpoint                     | Before | After (cached) |
|------------------------------|--------|----------------|
| /api/cli/status              |  750ms |     1ms        |
| /api/auth/status             |  400ms |     1ms        |
| /api/memory/snapshot         |  170ms |     2ms        |
| /api/ports/list              |  150ms |     2ms        |

---
## [2.71.33] — 2026-05-03

**QQ143** — third subprocess-bound endpoint memoised.
`/api/memory/snapshot` runs `_top_processes(30)` (a `ps` fan-out)
and `api_cli_sessions_list` (full Claude sessions scan) on every
hit — ~150-360ms. With the live ticker calling it every couple of
seconds AND the Memory tab querying it on open, the cumulative
cost was visible.

### Fixed
- 1.5s server-side memo for `/api/memory/snapshot` in
  `server/process_monitor.py`. Short enough that live monitoring
  stays real-time, long enough to coalesce the back-to-back hits
  that share the same wall-clock second. `?nocache=1` bypass.

### Verified
- `scripts/e2e-memory-snapshot-cache.mjs` — Playwright regression:
  cold ≈ 172ms, cached = 2ms, `?nocache=1` re-probes at 145ms,
  hit after 1.7s wait re-probes (TTL expired). 3/3 green.

---
## [2.71.32] — 2026-05-03

**QQ142** — `lazyclaude open <tab>` and `lazyclaude tabs` terminal
built-ins. Mirrors the chat `/go` alias map so users can jump
between dashboard tabs from the terminal too:

```
lazyclaude open wf       # → workflows
lazyclaude open chat     # → lazyclawChat
lazyclaude open ai       # → aiProviders
lazyclaude tabs          # list every NAV tab id with emoji + label
```

`/help` updated.

### Verified
- `e2e-terminal-set-prefs.mjs` extended to 18 checks (was 16):
  `lazyclaude tabs` lists `workflows` + `lazyclawChat`,
  `lazyclaude open wf` actually flips `state.view` to
  `workflows`. All green.

---
## [2.71.31] — 2026-05-03

**QQ141** — `lazyclaude version` (and `--version` / `-v`) terminal
built-in. Hits `/api/version` and prints the dashboard version,
git commit, branch, build timestamp and Python version inline —
without leaving the terminal or hitting the shell whitelist.

`/help` updated.

### Verified
- `e2e-terminal-set-prefs.mjs` extended to 16 checks (was 13):
  `lazyclaude version` prints `LazyClaude v2.71.30`, `lz --version`
  works the same, neither hit `/api/lazyclaw/term`. All green.

---
## [2.71.30] — 2026-05-03

**QQ140** — perf gap I missed in QQ137. The boot prewarm only
fired once, so the QQ135 / QQ136 memos expired after 30s of idle
and the next tab-switch into AI Providers / Team paid the full
cold cost (~750ms / ~400ms) again.

Replaced the one-shot prewarm with a **daemon refresh loop**
that re-runs every 25s — five seconds before the original TTL —
keeping both caches permanently hot at the cost of one
subprocess fan-out per 25s. Negligible CPU; CLI / auth state
changes rarely.

### Verified
- `scripts/e2e-cache-refresh-loop.mjs` — Playwright regression:
  hits both endpoints at boot+ and again 32s later (past the
  original 30s TTL); both stay <60ms. 4/4 green.

---
## [2.71.29] — 2026-05-03

**QQ139** — same class of bug as QQ138, different surface. The
SessionEnd "dashboard reindex" hook preset (`session-end-save`)
hardcoded `http://127.0.0.1:8080` in its command, so anyone
running the dashboard on PORT=19500 (or in a container) who
installed the preset would silently lose the reindex on session
end. Now the command uses `location.origin`.

### Verified
- `scripts/e2e-hook-preset-origin.mjs` — Playwright regression:
  preset exists, command no longer contains `127.0.0.1:8080`,
  command starts with the current origin. 3/3 green.

---
## [2.71.28] — 2026-05-03

**QQ138** — workflow webhook URL + curl snippet hardcoded
`http://localhost:8080/...` so anyone running the dashboard on a
non-default port (PORT=19500, container, remote tunnel) had to
hand-edit the URL after copying. Both the inspector input and
the curl `<pre>` now use `location.origin`.

### Verified
- `scripts/e2e-webhook-url-origin.mjs` — Playwright regression:
  saves a workflow, opens it, asserts the rendered webhook URL
  starts with `http://127.0.0.1:19500` (current origin) and no
  longer contains `localhost:8080`; same for the curl snippet.
  5/5 green.

---
## [2.71.27] — 2026-05-03

**QQ137** — server boot now pre-warms the QQ135 / QQ136 subprocess
caches in a daemon thread. Without this, the *first* AI Providers
or Team tab visit after a fresh server start still paid the cold
~750ms / ~400ms `<tool> --version` and `claude auth status` costs;
only subsequent visits hit the 30s memo. Now the prewarm runs in
parallel with `warmup_caches()` and finishes inside the typical
boot window — so the user's first tab open already finds the
cache populated.

### Verified
- `scripts/e2e-prewarm-caches.mjs` — Playwright regression: first
  /api/cli/status hit 31ms (was 750ms), first /api/auth/status hit
  2ms (was 400ms), repeat hits stay <60ms. 4/4 green.

---
## [2.71.26] — 2026-05-03

**QQ136** — second perf bug. `/api/auth/status` runs
`claude --version` *and* `claude auth status` subprocesses
(~400ms combined). The endpoint is touched by team / projects /
memoryManager / openPorts and was the single biggest factor
behind their slow tab-switches.

### Fixed
- 30s server-side memo for `/api/auth/status` in
  `server/auth.py`. Auto-invalidates when `~/.claude.json`'s
  mtime changes — so `claude auth login` is reflected without
  waiting for the TTL.

### Verified
- `scripts/e2e-auth-status-cache.mjs` — Playwright regression:
  cold ≈ 415ms, cached = 3ms, repeat = 1ms, warm team
  tab-switch 16-39ms (was 871ms). 3/3 green.

### Cumulative tab-switch wins (QQ135 + QQ136)
| Tab            | Before  | After |
|----------------|---------|-------|
| aiProviders    | 3752ms  | 55ms  |
| team           |  871ms  | 16ms  |
| memoryManager  |  685ms  | 198ms |
| openPorts      |  584ms  | 180ms |

---
## [2.71.25] — 2026-05-03

**QQ135** — real perf bug. `/api/cli/status` ran `<tool> --version`
in parallel for every CLI in CLI_CATALOG (~750ms wall-clock), and
the **AI Providers** tab awaited it on every open. Tab-switch
into AI Providers was ~3.7s — clearly outside the user's "렉은
아예 존재하지 않게끔" goal.

### Fixed
- 30s server-side memo for `/api/cli/status` in
  `server/cli_tools.py`. CLI install state changes rarely; the
  TTL is plenty for the AI Providers tab and the AI Providers
  refresh button can bypass via `?nocache=1`.
- Query parsing fix — `parse_qs` returns list-form values, so
  the bypass check unwraps `["1"]` correctly.

### Verified
- `scripts/e2e-cli-status-cache.mjs` — Playwright regression:
  cold ≈ 755ms, cached < 50ms (got 2ms), `?nocache=1` forces
  re-probe (~751ms again), and warm aiProviders tab-switch under
  500ms (saw 84ms then 55ms — was 3752ms before the fix). 3/3
  green.

---
## [2.71.24] — 2026-05-03

**QQ134** — arrow-key nudges are undoable. The LL4 handler set
`__wf.dirty = true` but never pushed an undo entry, so accidental
nudges were permanent (Cmd+Z went back further than the user
intended, or did nothing at all).

Push exactly **one** undo entry per "nudge burst" — defined as
arrow keys pressed within 500ms of the previous one. Holding →
for a second creates a single undo entry; Cmd+Z reverses the
entire burst at once. n8n behaviour.

### Verified
- `e2e-multi-arrow-nudge.mjs` extended from 3 → 6 checks: 5
  quick Right presses move both nodes by +50, the undo stack
  grows by exactly 1, then Cmd+Z reverts both back. All green.

---
## [2.71.23] — 2026-05-03

**QQ133** — `D` keystroke (toggle disabled) now operates on the
whole multi-selection. Previously the PP2 handler only flipped
`__wf.selectedNodeId`, so rubber-banding 5 nodes and pressing
`D` toggled exactly one of them.

Picks the inverse of the **first** selected node's current
`disabled` state, then forces every selected node to that same
state — so the result is always a deterministic batch-disable
(or batch-enable) regardless of mixed prior state.

### Verified
- `scripts/e2e-multi-disable.mjs` — Playwright regression: A
  enabled, B disabled, C enabled. After first `D` all 3
  disabled; after second `D` all 3 enabled; single-select `D`
  toggles only that node. 3/3 green.

---
## [2.71.22] — 2026-05-03

**QQ132** — arrow-key node nudging now honours multi-selection.
Previously the LL4 handler moved only `__wf.selectedNodeId`, so
rubber-banding 5 nodes and pressing → only shifted the
last-clicked one — inconsistent with the QQ28 group-drag and
n8n's own behaviour. Now ←↑→↓ (10px) and Shift+←↑→↓ (1px) move
the entire `__wfMultiSelected` set together. Single-select path
unchanged.

### Verified
- `scripts/e2e-multi-arrow-nudge.mjs` — Playwright regression:
  multi-select A+B → ArrowRight nudges both +10x → Shift+ArrowDown
  nudges both +1y → switching to single-select moves only that
  node. 3/3 green.

---
## [2.71.21] — 2026-05-03

**QQ131** — Playwright coverage for Cmd+X being undoable. The
QQ129 cut handler already pushes an undo entry, but no test
exercised Cmd+Z after cut. Added two assertions that prove the
A→B→C graph is fully restored (both nodes and both edges) after
`cut(A+B) → undo`.

### Verified
- `e2e-multi-cut.mjs` extended from 8 → 10 checks. All green.

---
## [2.71.20] — 2026-05-03

**QQ130** — workflow shortcut-help modal (`?` key) was missing
the new `Ctrl+X` cut entry from QQ129. Added it, plus a
Playwright regression that loads the help and asserts every
key combo we document is actually rendered.

### Verified
- `scripts/e2e-workflow-shortcut-help.mjs` — opens the help via
  `_wfShowShortcutHelp()`, asserts Ctrl+C/X/V/D/A/Z/S/Enter and
  Esc are listed, Esc closes the modal, and a second
  `_wfShowShortcutHelp()` call toggles it off (matching the
  documented behaviour). 11/11 green.

---
## [2.71.19] — 2026-05-03

**QQ129** — Cmd/Ctrl+X **cut** workflow shortcut (n8n parity).
The canvas already had Cmd+C / Cmd+V from QQ29, but cut had to
go through Cmd+C → Delete by hand. Now Cmd+X copies the selection
+ internal edges into `__wf._clipboard`, deletes them from the
canvas, clears the selection, and pushes an undo entry — so a
follow-up Cmd+V (or Cmd+Z) Just Works.

### Verified
- `scripts/e2e-multi-cut.mjs` — Playwright regression: seeds
  A→B→C, multi-selects A+B, presses Cmd+X, asserts canvas drops
  to 1 node, clipboard holds 2 nodes + 1 internal edge, then
  Cmd+V pastes them back with re-wired edge. 8/8 green.

---
## [2.71.18] — 2026-05-03

**QQ128** — context-menu **복제** entry was the older single-node
clone path that ignored multi-selection (orthogonal to QQ127's
keyboard fix). Right-clicking inside a multi-select then choosing
복제 cloned only the right-clicked node. Now both the keyboard
shortcut and the ctx menu share `window._wfDuplicateNodes` so
they behave identically.

### Changes
- Extracted the duplicate logic into a single
  `window._wfDuplicateNodes(ids[])` helper.
- Cmd/Ctrl+D and the ctx-menu 복제 entry both call it.
- `_wfShowNodeContextMenu` exposed on `window` (needed for the
  e2e regression and for parity with the other lazyclaw window
  exposures — QQ109/110 pattern).

### Verified
- `scripts/e2e-multi-duplicate.mjs` extended to 11 checks
  (was 8) — opens the ctx menu programmatically with two nodes
  multi-selected, clicks 복제, asserts both clones land and the
  selection points at them. All green.

---
## [2.71.17] — 2026-05-03

**QQ127** — Cmd/Ctrl+D duplicates **all** multi-selected nodes,
not just `__wf.selectedNodeId`. Previously selecting 5 nodes via
rubber-band and pressing Cmd+D cloned only the last-clicked one;
the other 4 were silently ignored. n8n parity gap.

### Changes
- `dist/app.js` — duplicate handler now reads
  `__wfMultiSelected` (falls back to single selection), clones
  every match preserving the +40px offset, and **also clones any
  edge whose endpoints both live in the duplicated set** so the
  sub-graph stays wired. The new clones become the active
  multi-selection so a follow-up drag/Delete affects them.
- Single-node duplicate still works unchanged (verified).

### Verified
- `scripts/e2e-multi-duplicate.mjs` — Playwright regression:
  seeds 3 session nodes A→B→C, multi-selects A+B, presses Cmd+D,
  asserts 5 total nodes, 2 clones with correct subjects + offsets,
  the A→B edge is cloned, the B→C edge is NOT (C wasn't selected),
  and `__wfMultiSelected` points to the clones afterwards.
  8/8 green.

---
## [2.71.16] — 2026-05-03

**QQ126** — Tab autocomplete inside the chat composer was stuck
on the original five commands `clear/system/model/export/help`
from QQ62 and silently ignored every slash added since (cost,
status, agents, sessions, rename, theme, lang, copy, retry,
regenerate, go, open). Bumped the autocomplete list so Tab now
cycles all 17 commands.

### Verified
- `scripts/e2e-chat-slash-tab-complete.mjs` — Playwright
  regression: `/the<Tab>` → `/theme`, `/co<Tab>` cycles
  cost↔copy, `/se<Tab>` → `/sessions`, `/g`/`/op` expand,
  `/re<Tab>` cycles rename/retry/regenerate, `/xyz<Tab>` is a
  no-op. 8/8 green.

---
## [2.71.15] — 2026-05-03

**QQ125** — `/go <tab>` (alias `/open`) chat slash command.
Jumps to another dashboard tab from chat without keyboard
gymnastics. Resolves a small alias table — `term` →
`lazyclawTerm`, `wf` → `workflows`, `proj` → `projects`,
`ai` → `aiProviders`, `settings`, `cost` → `usage`, etc. — and
falls through literal tab ids unchanged.

`/help` updated. The unknown-slash heuristic learns about
`/go` and `/open` so typos route to them.

### Verified
- `scripts/e2e-chat-slash-go.mjs` — Playwright regression: alias
  `/go term` lands on lazyclawTerm, `/go wf` on workflows,
  `/open analytics` on analytics, no-arg toasts and stays put,
  `/help` listing includes `/go`. 6/6 green.

---
## [2.71.14] — 2026-05-03

**QQ124** — typo'd chat slash commands no longer leak to the
provider. `/clearr`, `/xyzzy`, etc. were silently passed through
to `_lcChatSend` because the slash handler only intercepted
*known* commands. Now an unknown single-word `/<word>` is
swallowed locally and a toast suggests the closest known command
(plus `/help`). Multi-word slashes that look like paths
(`/path/to/file`) still fall through to the provider so users
can paste filesystem references.

### Added
- Unknown-command guard inside `_lcChatSlashCommand` with a
  cheap edit-distance heuristic ("혹시 /clear?" / "did you mean").
  Returns `true` (swallow) only when input matches `/^\\/[a-z][a-z0-9_-]*\\s*$/`.
- `scripts/e2e-chat-slash-unknown.mjs` — Playwright regression:
  `/clearr` toast suggests `/clear`, `/xyzzy` falls back to
  `/help`, `/path/to/file` falls through, real `/help` still
  works, no `/api/lazyclaw/chat` requests fired.

### Verified
- 8/8 Playwright checks green.

---
## [2.71.13] — 2026-05-03

**QQ123** — `/retry` (alias `/regenerate`) chat slash command.
Reuses the existing per-message `_lcRegenerate` flow — finds the
last user prompt, trims any trailing assistant replies, refills
the composer, and re-sends. Mirrors the per-bubble 🔄 button but
keyboard-friendly.

`/help` updated.

### Verified
- `e2e-chat-slash-cost-status.mjs` extended to 24 checks
  (was 20) — stubs `_lcChatSend`, asserts (a) history is trimmed
  to the last user message, (b) composer is repopulated, (c)
  `_lcChatSend` was called.

---
## [2.71.12] — 2026-05-03

**QQ122** — `/copy [N]` chat slash command. Copies the last (or
Nth-most-recent) assistant reply to the clipboard via
`navigator.clipboard.writeText`, with a `document.execCommand`
fallback for environments where the async clipboard API isn't
permitted. Toasts the resulting char count.

`/help` updated.

### Verified
- `e2e-chat-slash-cost-status.mjs` extended to 20 checks
  (was 18) — seeds a known marker `COPY-MARKER-LMNO` as the last
  assistant reply, then asserts `navigator.clipboard.readText()`
  returns it after `/copy`.

---
## [2.71.11] — 2026-05-03

**QQ121** — bare `lazyclaude`, `lz`, `lazyclaude --help`, and
`lz -h` all map to the same help listing, so first-time users
discover the built-in commands without having to know the verb
list. Stays client-side (no shell hit).

### Verified
- `e2e-terminal-set-prefs.mjs` extended to 13 checks
  (was 10) — bare `lazyclaude` shows help, `lz --help` shows
  help, neither hits the shell endpoint.

---
## [2.71.10] — 2026-05-03

**QQ120** — `/theme` and `/lang` chat slash commands.

- `/theme`             — toggles dark ↔ light.
- `/theme <name>`      — set explicitly (auto/dark/light/midnight/forest/sunset).
- `/lang ko|en|zh`     — switch UI language; reuses
  `_qsApplyAndPersist` so the rest of the dashboard sees the
  change immediately. `lang` triggers `setLang` which reloads.

`/help` updated to list both.

### Verified
- `e2e-chat-slash-cost-status.mjs` extended to 18 checks
  (was 14) — `/theme` toggle flips body class, `/theme dark`
  forces dark, `/help` listing includes `/theme` + `/lang`.
  All green.

---
## [2.71.9] — 2026-05-03

**QQ119** — `/sessions` chat slash command. Lists every session
in storage with its short id, label, and message count; marks
the active one with `➜`. Lets users see at a glance which
sessions exist without opening the sidebar.

`/help` updated to list it.

### Verified
- `e2e-chat-slash-cost-status.mjs` extended to 14 checks
  (was 11) — `/sessions` shows active marker + message count,
  `/help` listing includes `/sessions`. All green.

---
## [2.71.8] — 2026-05-03

**QQ118** — `/agents` chat slash command. Lists every assignee
currently in the dropdown, marks the active one with `➜`, and
points to `/model` for switching. Helpful for users who can't
remember whether they registered `claude:opus`,
`openai:gpt-4.1`, or `ollama:llama3.1`.

`/help` updated to include the new command.

### Verified
- `scripts/e2e-chat-slash-cost-status.mjs` extended to 11 checks
  (was 8) — `/agents` shows current assignee, marks current
  with `➜`, `/help` listing includes `/agents`. All green.

---
## [2.71.7] — 2026-05-03

**QQ117** — two more terminal built-ins so users can discover and
manage the lazyclaw terminal without leaving it.

### Added
- `lazyclaude help` (and `lz help`) — terse listing of every
  built-in (`get` / `set` / `reset` / `help`), the four pref
  sections, common examples, and a one-line note about the shell
  whitelist. Stays client-side; never hits `/api/lazyclaw/term`.
- `lazyclaude reset` — wipes the terminal log buffer
  (`localStorage['cc.lazyclawTerm.log']`); preferences untouched.
- Autocomplete suggestions extended.

### Verified
- `scripts/e2e-terminal-set-prefs.mjs` extended to 10 checks
  (was 7) — `help` listing, shell short-circuit, `reset` empties
  the log lines. All green.

---
## [2.71.6] — 2026-05-03

**QQ116** — three new openclaw-style chat slash commands plus a
`/help` refresh.

### Added
- `/cost` — sums `tokensIn / tokensOut / costUsd` across the
  current session and posts the totals as an inline assistant
  bubble.
- `/status` — prints assignee, session label + short id, current
  language and theme.
- `/rename <name>` — rename the current session in place; pushes
  through to `_lcRenderSessions` so the sidebar updates.
- `/help` lists the three new commands.

### Verified
- `scripts/e2e-chat-slash-cost-status.mjs` — Playwright regression
  with 8/8 checks (token totals, USD format, status assignee,
  rename persisted, /help listing). Seeds a fresh session with two
  fake assistant messages carrying token + cost so /cost can prove
  the rollup math.

---
## [2.71.5] — 2026-05-03

**QQ115** — openclaw-style **settings via the lazyclaw terminal**.
The user can now tweak preferences without leaving the terminal:

```
lazyclaude get                         # full CC_PREFS dump
lazyclaude get ui                      # one section
lazyclaude get ui.theme                # one key
lazyclaude set ui theme light          # bool/int/float/string coerced from schema
lz set ai temperature 1.2              # `lz` shorthand
```

### Added
- `dist/app.js` — `_lcTermBuiltin` + `_lcTermHandleBuiltin`
  intercept get/set commands inside `_lcTermRun` before they
  reach `/api/lazyclaw/term`. Coerces values per
  `CC_PREFS_SCHEMA[section][key].type` (bool / int / float /
  string), then routes through `_qsApplyAndPersist` so the same
  side-effects (theme switch, lang reload, etc.) fire as if the
  user used Quick Settings.
- Autocomplete suggestions for `lazyclaude get/set` and `lz`.
- `scripts/e2e-terminal-set-prefs.mjs` — Playwright regression:
  get prints JSON, set ui theme flips body class, set ai
  temperature 1.2 coerces float, bad section/key warn, built-ins
  do not hit the shell endpoint, `lz` shorthand works.

### Verified
- 7/7 Playwright checks green.

---
## [2.71.4] — 2026-05-03

**QQ114** — In zh/en mode, the lazyclaw Chat & Terminal nav tiles
showed mixed-locale title/aria-label text like
`AI 聊天 — 등록된 AI 提供商(Claude·OpenAI·Gemini·Ollama 등)与 직접 대화...`.
Root cause: the two two-sentence Korean descriptions were absent
from the locale dicts, so `_translateDOM`'s substring walker
chained shorter matches (`프로바이더→提供商`, `와→与`,
`전환→切换`, etc.) producing the franken-string.

### Added
- `tools/translations_manual_43.py` — full-sentence EN + ZH
  translations for both nav-tile descriptions (chat + terminal).
  Wired into `tools/translations_manual.py`; `make i18n-refresh`
  rebuilds locales.
- `scripts/e2e-find-missing-i18n.mjs` skips `.first-user-prompt`,
  `.prose`, `.prose-claude`, `.markdown`, `pre`/`code`, and the
  session-preview `.text-sm.mt-1.truncate` tile so user-typed
  content doesn't trigger false-positive Korean-residue warnings.

### Verified
- Playwright: 0 text-node leaks, 0 attribute leaks in zh mode
  (was 3 / 2 before — the 3 text leaks were user content, now
  filtered; the 2 attr leaks were the bug above).

---
## [2.71.3] — 2026-05-03

**QQ113** — Light theme had 200+ WCAG AA contrast failures across
the 66 tabs (every chip, every state badge, every stat tile). The
audit script `e2e-light-contrast.mjs` was using a flat 4.5
threshold instead of WCAG 1.4.3's two-tier rule, but even after
applying the proper threshold ~14% of text was still below 4.5.

### Fixed
- `--ok` / `--warn` / `--err` / `--cyan` light-theme tokens now
  resolve to AA-compliant darker variants (green-800, yellow-800,
  red-800, sky-800).
- `.chip-ok` / `.chip-warn` / `.chip-err` text bumped to the same
  darker shade.
- ~25 light-theme attribute-substring overrides for inline-style
  hex/rgb tuples that the SPA emits via `style="color:#..."`
  (`#f87171`, `#a78bfa`, `#ca8a04`, `#67e8f9`, `#0284c7`, `#16a34a`,
  `#dc2626`, `#9ca3af`, `#9aa0aa`, `#60a5fa`, `#7dd3fc`, `#93c5fd`,
  `#a16207`, `#fcd34d`, `#fca5a5`, `#86efac`, `#22d3ee`, `#38bdf8`).
  Browsers normalise hex→rgb when JS touches `style.cssText`, so
  both forms are matched.
- `e2e-light-contrast.mjs` now applies WCAG 1.4.3 AA correctly
  (4.5 body, 3.0 for ≥24px or ≥18.66px-bold) and honours `$PORT`.

### Verified
- Playwright audit: **0 violations across 66 tabs** (was 200+
  pre-fix, 106 after just the threshold fix).
- Dark theme unaffected — overrides scoped to `body.theme-light`.

---
## [2.71.2] — 2026-05-03

**QQ112** — Auto-Resume panel could not bind dormant (not currently
running) sessions. The session-detail panel's `_arSubmit` always
posted `allowUnboundSession=false`, so the API rejected with
`Session not currently running. Pass allowUnboundSession=true to
bind anyway.` This is the common case (you typically set up
Auto-Resume *for* a session that has already exited / hit a token
limit), so the panel was broken for its primary use case.

### Added
- **Force-bind checkbox** in the Auto-Resume session-detail panel:
  새 `arAllowUnbound` 체크박스(advanced settings 안). Tick it to
  bind a session that isn't currently live — re-resume will spin up
  a new Claude session at the bound cwd.

### Fixed
- `scripts/e2e-auto-resume.mjs`:
  - Honour `$PORT` (default 8080 still works) so the standard
    `PORT=19500` sweep no longer skips this script.
  - Set `allowUnboundSession=true` for the inject flow + the badge
    sub-test, since `pickSessionId` always returns historical (not
    live) sessions in CI.
  - Replace one `page.waitForFunction` poll with `waitForSelector`
    state:visible — the JS-eval poll never returned truthy in the
    headless test rig despite the button being painted; selector
    state matching is reliable here.

### Verified
- 3/3 viewports (mobile 375 / narrow 768 / desktop 1280) PASS:
  panel renders → inject succeeds → state chip + progress bar
  appear → cancel reverts → hook install/uninstall round-trip →
  session list shows 🔄 AR badge.

---
## [2.71.1] — 2026-05-03

**QQ111** — Fix QQ76 pre-token "_…_" placeholder never rendering.
Root cause: `_lcChatRender` always re-read history from
localStorage via `_lcGetHistory(id)`, but `_lcSaveHistory` (QQ77)
filters `pending: true` entries before persisting. The placeholder
pushed into the in-memory history array in `_lcChatSend` was
therefore invisible — the assistant bubble stayed empty until the
first SSE token arrived.

### Fixed
- `_lcChatRender(opts)` now accepts an optional `opts.history`
  override; `_lcChatSend` passes the live history through after
  pushing the pending placeholder so the bubble actually renders.

### Added (test infra)
- `scripts/e2e-chat-scroll.mjs` — verifies QQ35 ⬇ scroll-button +
  QQ88 force-scroll-on-send + QQ76 placeholder visibility (the
  regression that caught QQ111).

---
## [2.71.0] — 2026-05-03

**Playwright Verification Sprint II** — 41 e2e regression scripts
all green. Backwards-compatible.

### Added (test infra)
- 🎭 **Run-cancel API regression**
  (`scripts/e2e-run-cancel-api.mjs`): POST without runId / with
  malformed runId both return `{ok:false, error:'invalid runId'}`;
  with a real runId returns `{ok:true, live:<bool>}` regardless of
  whether the run already finished.

### Status (cumulative since v2.70.0)
- **41/41** playwright e2e scripts pass.
- **441** pytest pass (2 pre-existing FF1-obsoleted assertions
  remain deselected).
- **66/66** smoke tabs pass.
- 2 real bugs caught + fixed by Playwright during the sprint:
  QQ109 (`_wfShowNodeOutputModal`) and QQ110
  (`_wfToggleNodeDisabled`) — both inline `onclick` handlers
  that referenced module-private functions, fixed by
  `window.…` exposure.

---
## [2.70.16] — 2026-05-03

### Added (test infra)
- 🎭 **Per-session assignee restore + model badge regression**
  (`scripts/e2e-session-assignee-restore.mjs`). Pins
  QQ65 + QQ67 + QQ91 + QQ104:
  1. Switching to session A flips the dropdown to
     `claude:opus`.
  2. Switching to session B injects `ollama:llama3.1:8b`
     (multi-colon assignee) into the dropdown — exercises the
     QQ65 option-injection path AND the QQ104 model-badge
     fix that keeps the full model spec after the first colon.
  3. Sidebar row for B shows the `llama3.1:8b` model badge.
  4. Switching to a legacy session with no `assignee` field
     backfills it with the current dropdown value (QQ67).

  Total e2e suite: **40/40 pass**. 🎉

---
## [2.70.15] — 2026-05-03

### Added (test infra)
- 🎭 **Edge delete + single-node REST run regression** — two new
  scripts:
  - `scripts/e2e-edge-delete.mjs` (LL20): selecting an edge and
    calling `_wfDeleteSelectedEdge()` removes it; right-click on
    the path opens the ctx menu and clicking 삭제 removes it
    (4 checks).
  - `scripts/e2e-run-node-rest.mjs` (QQ18): POST
    `/api/workflows/run-node` against a session node with
    `data.pinned + pinnedOutput` set, asserting the response is
    `{ok, nodeId, result: {status:"ok", output:"frozen-cache-hit",
    provider:"pinned", cost:0}}` — exercises the QQ20 short-
    circuit so the test runs without any API key (7 checks).

  Total e2e suite: **39/39 pass**.

---
## [2.70.14] — 2026-05-03

### Added (test infra)
- 🎭 **Edge connection invariants regression**
  (`scripts/e2e-edge-connect.mjs`):
  1. `_wfAddEdge('n-a', 'out', 'n-b', 'in')` returns true; edges
     length 0 → 1.
  2. Same connect call again returns false (duplicate).
  3. Self-loop (`n-a` → `n-a`) rejected.
  4. Cycle (`n-b` → `n-a` after `a → b` exists) rejected with
     toast.
  5. Canvas renders 1 `path.wf-edge` (waiting one frame past
     RAF coalesce).

  Total e2e suite: **37/37 pass**.

---
## [2.70.13] — 2026-05-03

### Added (test infra)
- 🎭 **Add-node from palette regression**
  (`scripts/e2e-add-node.mjs`):
  1. `_wfOpenNodeEditor(null)` opens the new-node modal (type=null
     draft on the window).
  2. `_wfPickNodeType(winId, 'session')` flips draft.type and seeds
     the session-shape `data` defaults.
  3. Filling subject + clicking Save adds a fresh node — count
     1 → 2, type=session, canvas renders 2 .wf-node groups.

  First attempt tried to find a `[data-tp="session"]` palette
  button; the actual entry point is the public helper
  `_wfPickNodeType(winId, type)`. Test corrected.

  Total e2e suite: **36/36 pass**.

---
## [2.70.12] — 2026-05-03

### Added (test infra)
- 🎭 **Node editor save flow regression**
  (`scripts/e2e-node-editor-save.mjs`):
  1. `_wfOpenNodeEditor('n-s')` opens the editor with title +
     subject inputs prefilled.
  2. Mutating values + dispatching `input` then clicking the
     localized 저장/Save button updates `node.title` /
     `node.data.subject`.
  3. Canvas re-renders with the new title text and the
     keyed-diff cache picks up the change.

  Total e2e suite: **35/35 pass**.

---
## [2.70.11] — 2026-05-03

### Added (test infra)
- 🎭 **Auto-layout regression** (`scripts/e2e-auto-layout.mjs`).
  Pins the longest-path layering algorithm:
  1. 4-node chain a→b→c→d with all nodes overlapping at
     (100,100).
  2. `_wfBeautifyLayout()` returns truthy.
  3. After layout: `a.x < b.x < c.x < d.x` (left-to-right
     longest-path order).
  4. All y-coordinates equal (single-row chain → same band).

  Total e2e suite: **34/34 pass**.

---
## [2.70.10] — 2026-05-03

### Added (test infra)
- 🎭 **Chat draft autosave regression**
  (`scripts/e2e-chat-draft-autosave.mjs`). Pins QQ33 + QQ70:
  1. Type into composer → after 350 ms debounce, draft sits
     in `cc.lc.draft.<sid>`.
  2. Switch tab away + back → composer pre-fills with the
     persisted draft.
  3. Slash commands (`/help`) clear the draft entry (QQ70).
  4. Re-typing produces a fresh draft; explicit cleanup is
     symmetric with the send path's `removeItem`.

  Total e2e suite: **33/33 pass**.

---
## [2.70.9] — 2026-05-03

### Added (test infra)
- 🎭 **Workflow run REST pipeline regression**
  (`scripts/e2e-workflow-run-rest.mjs`):
  1. POST `/api/workflows/save` with a start-only workflow.
  2. POST `/api/workflows/run` returns a `runId`.
  3. Poll `/api/workflows/run-status?runId=…` until terminal —
     status reaches `ok`, `nodeResults['n-start']` is populated.
  4. GET `/api/workflows/runs?wfId=…` lists the run we just
     fired. (First attempt used the wrong query param name —
     the API takes `wfId`, not `workflowId` — fixed in v2.70.9.)

  Total e2e suite: **32/32 pass**. Auto-cleans the test workflow.

---
## [2.70.8] — 2026-05-03

### Added (test infra)
- 🎭 **Node right-click context menu regression**
  (`scripts/e2e-node-ctxmenu.mjs`). Pins LL14 + QQ19:
  1. `contextmenu` MouseEvent on a session node opens
     `#wfNodeCtxMenu` with the expected items: 편집, 복제,
     비활성화, 단독 실행, 출력 복사, 마지막 출력 핀 설정,
     삭제 (the conditional ▶/📋/📌 entries appear because
     `lastRunResults[nid].output` is seeded).
  2. Clicking 복제 appends a new clone (nodes.length += 1)
     and the menu auto-closes.
  3. Re-opening the menu and dispatching `mousedown` on
     `<body>` triggers the once-listener cleanup that
     removes the menu.

  Total e2e suite: **31/31 pass**.

---
## [2.70.7] — 2026-05-03

### Added (test infra)
- 🎭 **Chat star toggle + ⭐ search filter regression**
  (`scripts/e2e-chat-star.mjs`). Pins QQ15:
  1. `_lcToggleStar(sid, idx)` flips `m.starred` and the rendered
     toolbar swaps ☆ → ⭐.
  2. Cmd+K search modal with the ⭐ filter checked returns
     exactly the starred message; non-starred ones drop out.
  3. Re-toggling clears `m.starred`.

  Total e2e suite: **30/30 pass**.

---
## [2.70.6] — 2026-05-03

### Fixed
- 🐛 **`_wfToggleNodeDisabled` exposed on window** (QQ110). The
  inspector node-card has an inline `onchange="_wfToggleNodeDisabled(...)"`
  checkbox and the QQ19 ctx-menu also called the function from
  the global scope. The function was a module-private declaration,
  so both inline handlers would have hit a ReferenceError in
  some bundle paths. Now assigned via
  `window._wfToggleNodeDisabled = …` so every entry point
  resolves consistently.

### Added (test infra)
- 🎭 **Node disable + ⏸ badge regression**
  (`scripts/e2e-node-disable.mjs`). 9 checks:
  1. Initial state has no `.wf-disabled` class and the
     `.wf-node-disabled-badge` SVG group is hidden via CSS.
  2. `_wfToggleNodeDisabled('n-a')` flips
     `data.disabled = true`, adds `.wf-disabled`, and the badge's
     computed `display !== 'none'`.
  3. Second toggle restores the original state.

  Total e2e suite: **29/29 pass**.

---
## [2.70.5] — 2026-05-03

### Added (test infra)
- 🎭 **Node search filter + inspector webhook URL regression**
  (`scripts/e2e-node-search-webhook.mjs`):
  1. LL24 fuzzy match: `"fnd"` → `frontend` (subsequence f, n, d)
     gets opacity 1; sibling nodes dim to 0.2.
  2. Empty query restores all opacity to ''.
  3. Inspector renders `#wfWebhookUrl` input bound to
     `/api/workflows/webhook/<id>`.

  First attempt's "fy" expectation was wrong — `frontend` has
  no `y`. Fixed test to use `fnd` which is a real subsequence
  match.

  Total e2e suite: **28/28 pass**.

---
## [2.70.4] — 2026-05-03

### Added (test infra)
- 🎭 **Workflow shortcuts + node-cache regression**
  (`scripts/e2e-workflow-shortcuts.mjs`):
  1. QQ11 `_wfToggleGrid()` flips `.wf-grid-on` on the canvas
     host AND persists `cc.wfGrid` to localStorage; second
     call toggles back.
  2. `__wf._nodeEls` cache populated with each node id after a
     render (proves the Y2 keyed-diff cache build).
  3. `_wfSave` function exposed so Cm+S handler can dispatch.

  Total e2e suite: **27/27 pass**.

---
## [2.70.3] — 2026-05-03

### Added (test infra)
- 🎭 **Workflow undo regression**
  (`scripts/e2e-workflow-undo.mjs`). 9 checks:
  1. Setup 3 nodes + 2 edges, undo stack starts empty.
  2. Delete n-b → 2 nodes, 0 incident edges, undo stack += 1.
  3. `_wfUndo()` restores n-b + both edges, undo stack drained,
     canvas DOM repopulates the n-b group.
  4. Calling `_wfUndo()` on an empty stack is a no-op.

  Total e2e suite: **26/26 pass**.

---
## [2.70.2] — 2026-05-03

### Added (test infra)
- 🎭 **Chat slash commands regression**
  (`scripts/e2e-chat-slash-commands.mjs`). 8 checks across
  QQ1 / QQ62 / QQ70:
  1. Tab autocompletes `/cl` → `/clear` (QQ62).
  2. `/clear` empties the current session's history,
     composer is cleared, and the QQ33 draft entry is also
     deleted (QQ70).
  3. `/system <text>` saves text under
     `cc.lazyclawChat.sys.<assignee>`.
  4. `/model claude:haiku` flips the dropdown value and
     persists to `cc.lazyclawChat.assignee`.
  5. `/help` appends a help message into the active session
     containing the localized "슬래시 명령" header.

  Total e2e suite: **25/25 pass**.

---
## [2.70.1] — 2026-05-03

### Added (test infra)
- 🎭 **Sticky note inspector form regression**
  (`scripts/e2e-sticky-editor.mjs`). Opens the QQ36 sticky
  editor (`_wfOpenNodeEditor`), changes text + color + width
  + height through the actual form fields, clicks save, and
  asserts:
  1. Form has 1 textarea (text), 5 color buttons
     (yellow/blue/green/pink/gray), 2 number inputs (w/h).
  2. After save: `data.text/color/width/height` all updated.
  3. Canvas rect re-renders with new fill (#dbeafe for blue)
     and new width attribute. Validates the QQ108 snap-key
     digest catches sticky form mutations end-to-end.

  10 checks. Total e2e suite: **24/24 pass**.

---
## [2.70.0] — 2026-05-03

**Playwright Verification Sprint** — milestone marker for the
20-iteration Ralph loop with `매 작업 검수는 playwright로 확인 후
완료시 패스` constraint. Backwards-compatible.

### Verified end-to-end (23 new scripts)
**Workflow (n8n parity)**
- `e2e-qq108-pin-badge.mjs` — pin badge keyed-diff render.
- `e2e-qq108-output-panel.mjs` — inspector node-output preview
  + 전체 보기 modal.
- `e2e-pin-data-ctxmenu.mjs` — right-click pin/unpin flow.
- `e2e-sticky-note.mjs` — sticky note color/size/text mutate.
- `e2e-align-distribute.mjs` — QQ34 toolbar (left/vcenter/
  hdist/right) + show-on-2/hide-on-1.
- `e2e-multi-copy-paste.mjs` — QQ29 lasso → Cmd+C → Cmd+V with
  internal-edge remapping.
- `e2e-multi-delete.mjs` — QQ30 silent < 4 / confirm ≥ 4.
- `e2e-workflow-tags.mjs` — QQ38 + QQ60 chip filter.
- `e2e-success-badge-sticky-count.mjs` — QQ78 + QQ79.
- `e2e-mini-gantt.mjs` — QQ46 + QQ73 sort/icons/click-select.
- `e2e-workflow-export-import.mjs` — full envelope round-trip.
- `e2e-rubber-band.mjs` — QQ27 Shift+drag selection.
- `e2e-group-drag.mjs` — QQ28 multi-drag preserves offsets.
- `e2e-fail-fast-status.mjs` — MM1/NN3/PP1 amber dashed.

**Chat (OpenClaw parity)**
- `e2e-chat-image-attach.mjs` — paste/picker → counter → clear.
- `e2e-chat-session-nav.mjs` — Cmd+Shift+[/].
- `e2e-chat-history-recall.mjs` — Cmd+↑/↓ + QQ85 reset.
- `e2e-chat-branch.mjs` — branch + parent lineage.
- `e2e-chat-edit-user-msg.mjs` — ✏️ truncate+prefill.
- `e2e-chat-search-cost.mjs` — Cmd+K search + cost chain.
- `e2e-chat-codeblock-collapse.mjs` — 📋 + 더보기.

**Terminal + perf**
- `e2e-terminal.mjs` — whitelisted run + Tab + Esc.
- `e2e-lag-budget.mjs` — DCL ≤600ms, 50-node rebuild ≤250ms,
  RAF coalesce 50→1.

### Bugs found by Playwright (and fixed in same iteration)
- **QQ109** (v2.69.2) — `_wfShowNodeOutputModal` was module-
  private; QQ108 inline `onclick` hit ReferenceError. Fixed
  via `window._wfShowNodeOutputModal = …`.
- 50-node canvas test caught a viewport-too-small issue in
  group-drag — bumped Playwright viewport to 1600×1200.
- Lag-budget test caught a hook misplacement: `window
  ._wfRenderCanvasNow` is just an alias; the RAF wrapper
  resolves the closure directly. Fixed by hooking
  `_wfRenderGroups` instead.

### Status
- 66/66 tabs smoke pass.
- 23/23 new e2e scripts pass.
- 441 pytest pass (2 pre-existing FF1-obsoleted assertions
  remain deselected).

---
## [2.69.20] — 2026-05-03

### Added (test infra)
- 🎭 **Workflow export/import round-trip regression**
  (`scripts/e2e-workflow-export-import.mjs`). 12 checks:
  1. Save a workflow with tags, sticky note, start, session,
     edge, and a non-default viewport.
  2. `/api/workflows/export` returns
     `{ok:true, export:{exportVersion:1, workflow:{...}}}`.
  3. `/api/workflows/import` (with the envelope) returns a fresh
     id distinct from the source.
  4. Re-fetched imported workflow preserves tags, all 3 nodes,
     1 edge, sticky text/color/dimensions, and viewport.zoom.

  Cleans both source + imported workflow at the end.

---
## [2.69.19] — 2026-05-03

### Added (test infra)
- 🎭 **Code block copy + long message collapse regression**
  (`scripts/e2e-chat-codeblock-collapse.mjs`). Pins QQ31 + QQ32:
  1. Assistant message with a fenced ```js block renders <pre>
     and a 📋 overlay button.
  2. Clicking 📋 actually writes the inner <code> text to the
     real clipboard (verified via `navigator.clipboard.readText`,
     with the playwright context granted clipboard permissions).
  3. A 1700-char assistant reply gets wrapped in a `<div
     id="_lcCollapsed_…">` with `max-height: 300px`.
  4. Clicking the "▾ 더보기" sibling button flips
     `wrap.style.maxHeight = 'none'` (full expansion).

  7 checks, all pass.

---
## [2.69.18] — 2026-05-03

### Added (test infra)
- 🎭 **Inspector mini-Gantt regression**
  (`scripts/e2e-mini-gantt.mjs`). Pins QQ46 + QQ73:
  1. With 4 nodes + injected `lastRunResults` (durations
     1500/800/1200pinned/600err), the workflow-meta block in the
     inspector renders a 4-row Gantt panel.
  2. Rows sort descending by duration (AAA → PIN → BBB → ERR).
  3. QQ73 status prefixes appear: 📌 on the pinned row, ❌ on
     the err row.
  4. Clicking the AAA row sets `__wf.selectedNodeId = 'n-a'`,
     so the inspector swaps to that node's detail view.

  6 checks, all pass.

---
## [2.69.17] — 2026-05-03

### Added (test infra)
- 🎭 **Workflow success-rate badge + sticky count split**
  (`scripts/e2e-success-badge-sticky-count.mjs`). Pins
  QQ78 + QQ79:
  1. Save a workflow with 1 sticky + 1 start + 1 session via
     REST and assert the list API returns
     `nodeCount=2, stickyCount=1, edgeCount=1`.
  2. Inject 5 synthetic `lastRuns` (4 ok, 1 err) into the
     client cache → `_wfRenderList()` shows the QQ78 `80%`
     success-rate badge in the row.

  5 checks, all pass. Auto-cleans the test workflow.

---
## [2.69.16] — 2026-05-03

### Added (test infra)
- 🎭 **Workflow tags + sidebar filter regression**
  (`scripts/e2e-workflow-tags.mjs`). End-to-end via the public
  REST API:
  1. Three workflows saved with tags `["alpha", "demo"]`,
     `["alpha"]`, `["beta"]`. Server round-trips the tags
     intact.
  2. Sidebar `#wfTagFilter` chip strip visible and lists the
     full union (alpha + beta + demo + 전체).
  3. `_wfSetTagFilter('alpha')` → only the alpha-tagged rows
     remain in `#wfListItems`; the beta-only row is hidden.

  Cleans up the test workflows via `/api/workflows/delete` so
  the dev store stays tidy. 8 checks total, all pass.

---
## [2.69.15] — 2026-05-03

### Added (test infra)
- 🎭 **Chat search + cost visibility chain regression**
  (`scripts/e2e-chat-search-cost.mjs`). Pins QQ45 + QQ97-QQ102:
  1. Cmd+K opens the search modal; query "unicorn" finds the
     assistant message in session-A.
  2. Sidebar header (QQ99/QQ100) shows today + total markers
     in the format `오늘 $X · 총 누적 $Y`.
  3. Per-session row chip (QQ98) shows the session's cumulative
     spend.
  4. Composer footer (QQ102) shows the current session's
     cumulative spend.

  Seeds 2 sessions with mixed today/yesterday timestamps and
  cost-bearing assistant turns, then asserts each surface
  reads the right total. 7 checks, all pass.

---
## [2.69.14] — 2026-05-03

### Added (test infra)
- 🎭 **Multi-delete + chat edit-user-msg regressions** —
  - `scripts/e2e-multi-delete.mjs` (QQ30): Backspace with 2
    selected drops both nodes + every incident edge silently;
    Backspace with 4 selected triggers the confirm dialog
    (auto-accepted), then drops the entire workflow.
  - `scripts/e2e-chat-edit-user-msg.mjs` (QQ22): clicking ✏️
    truncates the history at the chosen idx and pre-fills the
    composer with the original text. Verified for both
    edit-from-start (idx 0) and partial edits (idx 2 keeps the
    first pair).

  10 checks across the two scripts, all pass.

---
## [2.69.13] — 2026-05-03

### Added (test infra)
- 🎭 **Multi-node copy/paste with internal edges regression**
  (`scripts/e2e-multi-copy-paste.mjs`). Pins QQ29:
  1. Cmd+C with multi-selection captures the selected nodes
     into `__wf._clipboard`.
  2. Only edges fully inside the selection land in
     `__wf._clipboardEdges` — the b→c crossing edge stays out.
  3. Cmd+V appends fresh nodes (new ids) and remaps the cloned
     edge endpoints to those new ids.
  4. The pasted set replaces `__wfMultiSelected` so QQ28 group
     drag immediately applies.

  6 checks, all pass.

---
## [2.69.12] — 2026-05-03

### Added (test infra)
- 🎭 **Align / distribute toolbar regression**
  (`scripts/e2e-align-distribute.mjs`). Verifies QQ34:
  1. `wfAlignBar` shows when `__wfMultiSelected.size >= 2`,
     hides at 1.
  2. `_wfAlignSelected('left')` collapses every selected node
     to `min(x)`.
  3. `_wfAlignSelected('vcenter')` collapses every selected
     node to the rounded average y.
  4. `_wfAlignSelected('hdist')` keeps the leftmost / rightmost
     and places the middle node at the geometric midpoint.
  5. `_wfAlignSelected('right')` collapses to `max(x)`.

  6 checks, all pass.

---
## [2.69.11] — 2026-05-03

### Added (test infra)
- 🎭 **Chat branch + lineage regression**
  (`scripts/e2e-chat-branch.mjs`). Pins down the QQ23 + QQ24
  contract:
  1. Seeded parent session (4 msgs) → branch from idx 1 →
     new session created with `parentId`, `branchedAt`, and
     truncated history (2 msgs).
  2. Branch label embeds "분기" / "branch".
  3. QQ24 sidebar lineage chip shows `↳ parent-session`.
  4. Switching back to the parent restores its full 4-message
     history.

  9 checks, all pass.

---
## [2.69.10] — 2026-05-03

### Added (test infra)
- 🎭 **Sticky note canvas regression**
  (`scripts/e2e-sticky-note.mjs`). Pins down the QQ36 sticky
  rendering contract + QQ108 snap-key sticky-digest:
  1. Yellow sticky renders with `fill="#fef3c7"`, expected
     width/height, markdown text in `<foreignObject>`.
  2. Sticky has zero `.wf-port` children (no I/O).
  3. `data.color = 'blue'` → fill flips to `#dbeafe` after the
     keyed-diff renderer picks up the changed snap-key.
  4. `data.text` mutation likewise triggers a node rebuild and
     the new text appears in the `<foreignObject>`.

  All 7 checks pass.

---
## [2.69.9] — 2026-05-03

### Added (test infra)
- 🎭 **Pin Data context-menu regression**
  (`scripts/e2e-pin-data-ctxmenu.mjs`). Dispatches a real
  `contextmenu` MouseEvent on a session node, clicks
  "📌 마지막 출력 핀 설정", asserts:
  1. `node.data.pinned == true`.
  2. `pinnedOutput` captured from `lastRunResults`.
  3. Canvas pin badge appears.
  Then opens the menu again, clicks "📌 핀 해제", asserts the
  inverse. 8 checks total, no provider key needed.

---
## [2.69.8] — 2026-05-03

### Added (test infra)
- 🎭 **Chat history recall regression**
  (`scripts/e2e-chat-history-recall.mjs`). Seeds 3 user messages,
  then verifies QQ51 + QQ85:
  1. Cmd+↑ pulls the most recent user message.
  2. Cmd+↑ again walks one further back.
  3. Cmd+↓ walks forward.
  4. Typing any character resets `__lcHistIdx` to -1 (QQ85
     guard).
  5. Post-reset Cmd+↑ starts fresh from the most recent.

---
## [2.69.7] — 2026-05-03

### Added (test infra)
- 🎭 **Lag budget regression** (`scripts/e2e-lag-budget.mjs`).
  Three perf invariants get an upper-bound assertion so a future
  regression yells immediately:
  1. DOMContentLoaded < 600ms (current ≈ 60–170ms).
  2. 50-node forced full rebuild < 250ms (current ≈ 2–3ms).
  3. QQ25 RAF coalesce: 50 `_wfRenderCanvas()` calls in one tick
     produce exactly 1 actual sync render — measured by hooking
     `_wfRenderGroups` (always invoked inside `_wfRenderCanvasSync`).

  Pins down the "렉은 아예 존재하지 않게끔" promise with hard
  numbers.

---
## [2.69.6] — 2026-05-03

### Added (test infra)
- 🎭 **Playwright regression for lazyclaw terminal**
  (`scripts/e2e-terminal.mjs`). Verifies four invariants:
  1. Whitelisted command (`uname -a`) actually executes via the
     `/api/lazyclaw/term` endpoint and the output appears in the
     log.
  2. QQ17 `(NNms)` durationMs marker appears next to the output.
  3. QQ12 Tab completes `lazyclaude sta` → `lazyclaude status`.
  4. QQ106 Esc clears the input field.
  Test waits for the QQ4 health-check baseline first so the
  user-driven command is asserted in isolation.

---
## [2.69.5] — 2026-05-03

### Added (test infra)
- 🎭 **Playwright regression for fail-fast sibling cancel UI**
  (`scripts/e2e-fail-fast-status.mjs`). Builds a 3-node DAG
  (start → ok + err + canc), seeds simulated run results with
  one error and one sibling-cancelled, walks the same DOM-apply
  pipeline as the SSE poller, and asserts:
  1. err node carries `data-status="err"`.
  2. cancelled-by-sibling node is promoted from err to
     `data-status="cancelled"` (PP1).
  3. Computed style of the cancelled node's body shows the
     dashed amber stroke (the `.wf-node[data-status="cancelled"]
     .wf-node-body` rule). Pins down MM1 / NN3 / PP1 visual
     contract.

---
## [2.69.4] — 2026-05-03

### Added (test infra)
- 🎭 **Playwright regression for rubber-band + group drag** —
  `scripts/e2e-rubber-band.mjs` (QQ27 Shift+drag rectangle
  selects intersecting nodes only) and
  `scripts/e2e-group-drag.mjs` (QQ28 dragging a multi-selected
  node moves the cluster preserving relative offsets). Both use
  real `mouse.down/move/up` so the actual canvas onDown / onMove
  / onUp pipeline is exercised. Viewport sized 1600×1200 so the
  full sidebar + canvas fits without scroll.

---
## [2.69.3] — 2026-05-03

### Added (test infra)
- 🎭 **Playwright regression scripts for chat features** —
  `scripts/e2e-chat-image-attach.mjs` (QQ39 / QQ61 / QQ92 / QQ93
  paste-drop-picker → counter → click-to-clear) and
  `scripts/e2e-chat-session-nav.mjs` (QQ50 Cmd+Shift+[/] +
  QQ86 active-row data attribute). Both run against the dev
  server with no provider key required and need only the local
  `playwright` install.

---
## [2.69.2] — 2026-05-03

### Fixed
- 🐛 **`_wfShowNodeOutputModal` exposed on window** (QQ109). The
  QQ108 inline `onclick="_wfShowNodeOutputModal(...)"` fired in
  global scope but the function was a module-private declaration —
  Playwright caught the resulting `ReferenceError` immediately.
  Now assigned via `window._wfShowNodeOutputModal = function …`
  so the inline handler resolves.

### Added (test infra)
- 🎭 **Playwright regression scripts for QQ108** —
  `scripts/e2e-qq108-pin-badge.mjs` covers the QQ108 snap-key
  fix (pin badge appears/disappears via keyed-diff render),
  `scripts/e2e-qq108-output-panel.mjs` covers the inspector
  output panel + 전체 보기 modal flow. Both run headlessly
  against the dev server with no provider key required.

---
## [2.69.1] — 2026-05-03

### Added
- 📄 **Node output preview panel in inspector** (QQ108). Each
  completed node in the inspector now shows a collapsible
  `<details>` panel with the first 600 chars of its output (or
  red-tinted error), a 📋 copy button, and an `⬆ 전체 보기`
  button when the output overflows — opens a full-screen scroll-
  able modal via `_wfShowNodeOutputModal`. n8n parity: clicking
  a completed node reveals its data without leaving the canvas.

### Fixed
- 📌 **Pin / disabled / sticky badges now repaint via keyed diff**
  (QQ108 follow-up). `_wfNodeSnapKey` previously omitted
  `data.pinned`, `data.disabled`, and sticky-text fields, so
  toggling those flags didn't change the snapshot — the keyed-
  diff renderer skipped the node and the canvas badge stayed
  stale until a full rebuild. Snapshot now includes the pin
  state, disable state, and a compact sticky digest
  `len|color|w|h`, so badge state matches truth on every render.

---
## [2.69.0] — 2026-05-03

**QQ91–QQ107 rollup** — third tier of Q-series work since v2.68.0.
Backwards-compatible. Major theme: **chat cost visibility +
ergonomic polish across the four input surfaces**.

### Cost visibility (3-layer)
- Per-turn cost in the assistant meta line (QQ97).
- Per-session cumulative cost chip in sidebar (QQ98).
- Sidebar header today/total spend (QQ99, QQ100), guarded by
  `cc.lc.hasCost` flag so free-tier users pay zero render cost
  (QQ101). Composer footer shows the active session's cumulative
  spend (QQ102).

### Sidebar polish
- Per-session model badge keeps full tag (`llama3.1:8b`) (QQ91,
  QQ104). Filter-match count surfaces alongside spend (QQ107).
- `_lcGetSessions` / `_lcSaveSessions` defensive normalization
  (QQ83, QQ103).
- `_wfOpen` clears stale `lastRunResults` (QQ87).

### Esc-clears-input convention across all 4 input surfaces
- Chat sidebar filter (QQ58), chat composer in-stream cancel
  (QQ64), workflow sidebar search (QQ95), terminal input (QQ106).

### Workflow
- ▶ 단독 실행 offers auto-save on dirty (QQ94).
- ↻ fallback chip surfaces policy fallback usage (QQ105).
- Tag input selects on focus (QQ89).

### Chat composer ergonomics
- Pre-token "_…_" placeholder (QQ76) that doesn't persist on tab
  close (QQ77).
- Image attach 📎 button (QQ61) with stronger drag cue (QQ57)
  and aria-label (QQ96).
- Live `📷 N` image counter (QQ92), clickable to clear all
  attachments (QQ93).
- Always jump to bottom on send (QQ88), shell-style history
  recall reset on input (QQ85), markdown export drops base64
  to placeholders (QQ75).

---
## [2.68.17] — 2026-05-03

### Added
- 🔢 **Filter-match count in chat sidebar header** (QQ107). When the
  session filter is active, the sidebar's spend element now also
  shows `12 / 47` (matched / total). Combines with the QQ99/QQ100
  spend line as `12 / 47 · 오늘 $0.12 · 총 누적 $0.48`. Quick read
  on how aggressively the filter narrowed the list.

---
## [2.68.16] — 2026-05-03

### Added
- ⌨ **Esc clears the terminal input** (QQ106). The lazyclaw
  terminal's input now treats Esc the same way the chat sidebar
  filter (QQ58) and workflow sidebar search (QQ95) do — clears
  the field and resets the QQ6 history-recall cursor + draft.
  Consistent muscle memory across all four input surfaces (chat
  composer, chat filter, workflow search, terminal).

---
## [2.68.15] — 2026-05-02

### Added
- ↻ **`fallback` chip surfaces policy fallback usage** (QQ105). When a
  session node's primary assignee failed and was retried via
  `policy.fallbackProvider` (existing v2.29 behaviour), the node
  result already carried `fallbackUsed: true` but it never appeared
  in the UI. The inspector's per-node chip strip now shows an amber
  `↻ fallback` chip alongside provider / model / cost so users can
  spot which nodes ran on their backup path.

---
## [2.68.14] — 2026-05-02

### Fixed
- 🤖 **QQ91 model badge keeps full model spec** (QQ104). The
  per-session sidebar model chip used `split(':').pop()` which
  reduced `ollama:llama3.1:8b` to just `8b`. The chip now strips
  only the first `provider:` prefix, so tagged variants
  (`llama3.1:8b`, `mistral:7b-instruct`, etc.) display
  recognizably.

---
## [2.68.13] — 2026-05-02

### Fixed
- 🛡 **`_lcSaveSessions` coerces non-array inputs** (QQ103). Mirror
  of QQ83's getter normalization — persisting an object or null
  would corrupt the `cc.lc.sessions` schema for later reads.
  External tampering or a buggy migration can no longer poison
  the sessions store.

---
## [2.68.12] — 2026-05-02

### Added
- 💲 **Current-session spend in composer footer** (QQ102). The
  composer's char/token row now also shows `$0.0123` summed
  across the active session's `m.costUsd` values. Visible before
  send so users decide whether the next expensive turn fits the
  budget. Hides when zero.

---
## [2.68.11] — 2026-05-02

### Performance
- ⚡ **Short-circuit cost walk when no spend recorded** (QQ101). The
  QQ99/QQ100 sidebar spend calculation now checks a `sessionStorage`
  flag (`cc.lc.hasCost`) before walking every session's history. The
  flag is set only when a cost-bearing SSE `done` event arrives. Free
  tier users (Ollama, unconfigured providers) see zero extra overhead;
  paid API users get the full walk only after their first paid turn.

---
## [2.68.10] — 2026-05-02

### Added
- 📅 **Today's spend split out next to total** (QQ100). The QQ99
  total-spend header now reads `오늘 $0.123 · 총 누적 $0.482`
  when there's any spend today and the day total is below the
  all-time total. Filtering uses `m.ts >= startOfDay`. Falls back
  to the QQ99 `총 누적: $X` format when only today has spend (no
  history yet) or when nothing happened today.

---
## [2.68.9] — 2026-05-02

### Added
- 💰 **Total cumulative spend in chat sidebar header** (QQ99). Above
  the session list, a `총 누적: $0.482` line aggregates `m.costUsd`
  across every session's history. Hides when zero. Refreshes on
  every `_lcRenderSessions()` call (after send, switch, delete).
  Light-touch budget visibility without leaving the chat tab.

---
## [2.68.8] — 2026-05-02

### Added
- 💲 **Per-session cumulative cost badge in chat sidebar** (QQ98).
  Sums `m.costUsd` (persisted by QQ97) across the session's
  history and renders an amber `$0.0123` chip next to the
  token-usage badge. 4 decimals when sub-cent, 3 when ≥1¢.
  Pairs with QQ26 token badge so users see "🔤 12.4k · $0.084"
  at a glance for each conversation.

---
## [2.68.7] — 2026-05-02

### Added
- 💲 **Per-turn cost in chat assistant meta line** (QQ97). When the
  SSE `done` event reports `costUsd > 0`, the meta strip below
  the assistant bubble now also shows `$0.0042` alongside
  provider · model · 4.5s. Quick visibility into per-turn spend
  without opening telemetry. The cost is also persisted as
  `reply.costUsd` in the message for QQ26 sidebar token-badge
  cousin features.

---
## [2.68.6] — 2026-05-02

### Added
- 🔍 **`aria-label` on the chat 📎 attach button** (QQ96). Screen
  readers (and search/keyboard nav helpers) now hear "이미지 첨부
  (paste/drop 도 지원)" instead of just the emoji glyph. Brings
  the QQ61 attach button up to parity with other accessible
  buttons in the composer.

---
## [2.68.5] — 2026-05-02

### Added
- ⌨ **Esc clears the workflow sidebar search** (QQ95). The
  workflow list search input now follows the same convention as
  QQ58 (chat sidebar filter) and the existing node-search box —
  Esc empties the field, resets `__wf.search`, and re-renders
  the list. Consistent muscle memory across all three side
  panels.

---
## [2.68.4] — 2026-05-02

### Added
- ▶ **`▶ 단독 실행` offers auto-save when workflow is dirty** (QQ94).
  Previously the QQ18 single-node-run button just refused on a
  dirty workflow with a "save first" toast. Now it asks via
  `confirm()` whether to auto-save and proceed; on save failure
  it falls back to a "save failed" toast. Removes the
  edit-save-rerun bounce when the user is iterating quickly on
  one node's prompt.

---
## [2.68.3] — 2026-05-02

### Added
- 📷 **Click image counter to clear all attachments** (QQ93). The
  QQ92 `📷 N` chip is now clickable and tooltipped "이미지 모두
  제거". Clicking strips every `![...](data:image/...;base64,...)`
  block from the textarea (preserving surrounding text), fires an
  `input` event so QQ33 draft + char/token counter refresh, and
  toasts confirmation. Useful when composing iterative attempts
  with the wrong screenshot attached.

---
## [2.68.2] — 2026-05-02

### Added
- 📷 **Live image-attach counter in composer stats** (QQ92). The
  composer's chars/tokens stats row now also shows
  `📷 N` when the textarea has N base64 images embedded. Quick
  visual confirmation that QQ39 paste/drop / QQ61 picker
  attachments landed before pressing send. Hides itself when
  no images are attached.

---
## [2.68.1] — 2026-05-02

### Added
- 🤖 **Per-session model badge in chat sidebar** (QQ91). Each row
  now shows a small text chip with the session's stored
  `assignee` (just the model part after the colon, truncated to
  14 chars). Tooltip shows the full `provider:model`. Lets users
  see which model each session is wired to without switching to
  it — pairs with QQ65 per-session model restore.

---
## [2.68.0] — 2026-05-02

**QQ64–QQ90 rollup** — milestone for the second tier of Q-series work
since the v2.67.0 marker. Backwards-compatible. Test suite: **441
passed** (excluding 2 pre-existing FF1-obsoleted assertions in
`test_provider_error_passthrough.py`).

### Chat polish
- Esc cancels active stream (QQ64), surfaced in stop-button
  tooltip (QQ69).
- Per-session assignee restored on switch + backfilled for legacy
  rows (QQ65, QQ67); send-button tooltip shows the active model
  (QQ68).
- Auto-label across locales + image-stripped seed (QQ66); slash
  commands clear the QQ33 draft (QQ70); Tab autocompletes slash
  commands (QQ62).
- Pre-token "_…_" placeholder that doesn't persist on tab close
  (QQ76, QQ77); always jump to bottom on send (QQ88).
- Code-block copy buttons (QQ31), collapsible long messages (QQ32),
  scroll-to-bottom button (QQ35).
- Image attach via paste/drop/picker (QQ39, QQ61) with stronger
  drag cue (QQ57) and quota recovery (QQ53).
- Cmd+Shift+[/] session nav (QQ50) + history-recall cursor reset
  on typing (QQ85), active session auto-scrolls into view
  (QQ86); empty-state CTA (QQ90); session delete confirms with
  label (QQ84); Esc clears sidebar filter (QQ58).
- Markdown export drops base64 to placeholders (QQ75); orphan
  history/draft sweep guarded once-per-session (QQ74); session
  delete frees its history+draft (QQ54); `_lcGetSessions`
  defensive-normalizes corrupted payloads (QQ83).

### Workflow polish
- `_wfOpen()` clears stale `lastRunResults` so the QQ46 mini-Gantt
  doesn't carry over (QQ87); inspector tag input selects on
  focus (QQ89); recency-weighted success-rate badge in sidebar
  (QQ78); sticky split out from `nodeCount` (QQ79); dry-run also
  skips sticky annotations (QQ81); sticky-attached edges dropped
  at save (QQ63) and execution (QQ59).

### Test coverage
- Sticky annotations (QQ71): preserve, clamp, skip, edge-drop.
- Pin Data (QQ82): short-circuit, blank guard, 32 KB clamp.
- `_extract_inline_images` (QQ72): no-op, single, multi, non-image
  data URLs.
- `api_workflows_list` sticky split (QQ80): nodeCount + stickyCount
  correctness.

---
## [2.67.27] — 2026-05-02

### Added
- ＋ **Empty-state CTA in chat sidebar** (QQ90). When there are no
  sessions and no filter is active, the sidebar now shows a
  "＋ 새 대화" button below the empty-state message instead of
  just the text. One-click first-session creation. Filter
  active → unchanged "no match" message.

---
## [2.67.26] — 2026-05-02

### Added
- ⌨ **Tag input selects on focus** (QQ89). Clicking the inspector
  tag field now auto-selects existing tags, so retyping a fresh
  set just works (no manual select-all). Standard form-field UX.

---
## [2.67.25] — 2026-05-02

### Fixed
- 📜 **Always jump to bottom on send** (QQ88). `_lcChatRender` only
  auto-scrolled when the user was already within 80 px of the
  bottom. So if a user scrolled up to reread earlier context and
  then sent a new message, the new bubble + QQ76 placeholder
  appeared off-screen. `_lcChatSend` now force-scrolls the chat
  log to the bottom on send so the outgoing message is always
  visible.

---
## [2.67.24] — 2026-05-02

### Fixed
- 🧹 **`_wfOpen()` clears previous workflow's run results** (QQ87).
  Switching workflows preserved `__wf.lastRunResults` from the
  previous DAG. The QQ46 mini-Gantt + QQ47 inspector chips would
  briefly show stale per-node entries that mapped to nothing in
  the new graph until the next SSE tick replaced them. Now
  cleared on workflow open along with `_lastResultsSig` so the
  next status-apply pass starts fresh.

---
## [2.67.23] — 2026-05-02

### Added
- 📌 **Active session auto-scrolls into view** (QQ86). After
  `_lcRenderSessions()` repaints, the active row (marked
  `data-active="1"`) checks its bounding rect against the list
  scroll container; if it's off-screen, `scrollIntoView({block:
  'nearest'})` fires. Most useful after QQ50 keyboard nav
  (Cmd+Shift+[/]) in a long sidebar list — the new active row
  is always visible without manual scrolling.

---
## [2.67.22] — 2026-05-02

### Fixed
- ⌨ **History-recall cursor resets on user typing** (QQ85). After a
  Cmd+↑ recalled an old user message, typing additional characters
  used to leave the recall cursor at its old index — pressing
  Cmd+↑ again would unexpectedly skip ahead. Now any user input
  resets the cursor (shell-style); the recall handler itself sets
  a one-tick guard so its own dispatched `input` event doesn't
  clobber the index.

---
## [2.67.21] — 2026-05-02

### Added
- 🗑 **Session delete confirm shows the label** (QQ84). The session
  delete prompt now appends `<label>` so users see exactly which
  conversation is about to disappear — mistakes were easy when
  several sessions shared similar truncated previews.

---
## [2.67.20] — 2026-05-02

### Fixed
- 🛡 **`_lcGetSessions` defensive normalization** (QQ83). Older
  builds or external tampering can leave `cc.lc.sessions` parsing
  as an object or `null` instead of an array, which would later
  break `.find()` / `.map()` calls in QQ24 lineage / QQ45 search
  / QQ65 assignee restore. The getter now coerces non-array
  payloads to `[]` and filters entries missing a string `id`,
  so downstream callers can rely on the shape.

---
## [2.67.19] — 2026-05-02

### Verified
- ✅ **Pin Data regression suite** (QQ82). New `TestPinData` class
  covering QQ20's signature feature:
  1. Session node with `pinned=True` + non-empty `pinnedOutput`
     short-circuits to `provider="pinned"`, zero tokens, zero cost.
  2. Whitespace-only `pinnedOutput` does NOT short-circuit (avoids
     accidentally turning a node into a no-op).
  3. `_sanitize_node` clamps `pinnedOutput` to 32 KB.

  All 26 workflow tests pass.

---
## [2.67.18] — 2026-05-02

### Cleaned
- 🧼 **Dry-run also skips sticky annotations** (QQ81). The
  `api_workflow_dry_run` plan-builder iterated all nodes, including
  sticky comments — so dry-run reported `nodeCount` and `levels`
  that included annotations. Now applies the same QQ37/QQ59 sticky
  filter (drop sticky nodes + edges incident on them) before
  computing the plan, so the dry-run output matches what the
  executor will actually walk.

---
## [2.67.17] — 2026-05-02

### Verified
- ✅ **Regression test for QQ79 sticky/node split** (QQ80). New
  `test_list_api_splits_sticky_from_node_count` in
  `tests/test_workflows.py` builds a temp store with 1 sticky + 2
  executable nodes and asserts `api_workflows_list()` returns
  `nodeCount=2, stickyCount=1, edgeCount=1`. Pins down the QQ79
  semantic so future refactors can't bundle them again silently.
  All 23 workflow tests pass.

---
## [2.67.16] — 2026-05-02

### Changed
- 🟨 **Sticky annotations counted separately from executable nodes**
  (QQ79). The workflow list API now returns
  `nodeCount = (total - sticky)` and a new `stickyCount` field. The
  sidebar row now reads `5 노드 + 2 🟨 · 7 연결` instead of bundling
  the sticky into `nodeCount`. Matches users' mental model — sticky
  is a comment, not a step.

---
## [2.67.15] — 2026-05-02

### Added
- 📊 **Recency-weighted success-rate badge in workflow sidebar**
  (QQ78). Each row with at least 3 runs in `lastRuns` now shows a
  tiny `87%` (green ≥ 80, amber ≥ 50, red below) next to the
  existing chip strip. Tooltip names the sample size. Quick health
  signal for which workflows are flaky without opening the
  telemetry tab.

---
## [2.67.14] — 2026-05-02

### Fixed
- 💬 **QQ76 placeholder no longer persists if the tab closes mid-
  request** (QQ77). The pre-token "_…_" bubble was being written to
  localStorage immediately on push. If the user closed the tab
  before the first SSE token arrived, the placeholder was frozen
  forever in saved history. Now `_lcSaveHistory()` filters out
  entries with `pending: true` before persisting, so the
  placeholder is only kept in the live in-memory `history` array
  for the current page; refreshing the tab (with no completed
  reply) starts clean.

---
## [2.67.13] — 2026-05-02

### Added
- 💬 **Pre-token `…` placeholder in streaming chat** (QQ76). The empty
  assistant bubble used to look broken between request send and the
  first SSE token (especially noticeable for cold-start models).
  The bubble now starts with a `_…_` italic placeholder that the
  first real token replaces. Cleared also on abort (Esc) and
  fallback paths so it never lingers.

---
## [2.67.12] — 2026-05-02

### Fixed
- 📥 **Markdown export strips base64 images to a placeholder** (QQ75).
  After QQ39 added image attachments, `_lcChatExport()` was emitting
  the full `data:image/...;base64,...` URL into the `.md` file —
  resulting in 5+ MB exports for sessions with a single screenshot.
  Each embedded image is now replaced with an
  `![alt (NkB)]` placeholder that preserves the alt text and shows
  the approximate decoded byte size, keeping the `.md` human-
  sized while still documenting that an image was present.

---
## [2.67.11] — 2026-05-02

### Performance
- 🚀 **QQ56 orphan sweep guarded to once per browser session**
  (QQ74). Revisiting the chat tab N times in a row no longer
  rescans the entire `localStorage` keyspace each time — first
  open scans, sets a `sessionStorage` flag, subsequent opens skip.
  The sweep is for legacy cleanup so once-per-session is enough.

---
## [2.67.10] — 2026-05-02

### Added
- 📌❌ **Status icons in inspector mini Gantt rows** (QQ73). Each
  duration row now shows a `📌` prefix when the result was a pinned
  cache hit (QQ20) or `❌` when the node errored, alongside the
  existing color coding. Faster scan for what was actually re-run
  vs. served from cache vs. failed.

### Verified
- ✅ Full pytest suite (excluding pre-existing FF1-obsoleted tests):
  **437 passed, 0 failed** after QQ18 → QQ73.

---
## [2.67.9] — 2026-05-02

### Verified
- ✅ **Multimodal extractor regression suite** (QQ72). New
  `TestExtractInlineImages` class in `tests/test_ai_providers.py`
  pins down `_extract_inline_images()` behavior — the shared
  helper that QQ40-QQ43 (vision routing), QQ49 / QQ55 (claude-cli
  scrubbing), and QQ58 reuse. Coverage:
  1. No `data:image/` → short-circuit returns prompt unchanged.
  2. Single image extracted with mime + base64 + data_url shape.
  3. Multiple images, base64 whitespace + newlines stripped.
  4. `data:application/json` and other non-image data URLs are
     left alone.

  37 ai-provider + workflow tests pass.

---
## [2.67.8] — 2026-05-02

### Verified
- ✅ **Sticky annotation regression suite** (QQ71). New test class
  `TestStickyAnnotations` in `tests/test_workflows.py` covers the
  cumulative QQ36 / QQ37 / QQ59 / QQ63 invariants:
  1. `_sanitize_node` preserves `text/color/width/height`.
  2. Invalid color falls back to yellow; tiny / huge dimensions
     clamp to `[120, 800]`.
  3. `_execute_node` returns `status=ok output="" sessionId=""`
     and ignores upstream input.
  4. `_sanitize_workflow` drops edges whose `from` or `to` points
     at a sticky node, while keeping legitimate edges between
     session nodes intact.

  All 22 workflow tests pass.

---
## [2.67.7] — 2026-05-02

### Fixed
- 💾 **Slash commands clear the draft too** (QQ70). QQ33 draft
  autosave was only cleared in the regular send path. Running
  `/clear`, `/help`, etc. emptied the textarea but the draft
  localStorage entry stayed, so refreshing the tab restored the
  slash-command text. Now also cleared in the slash-command
  branch.

---
## [2.67.6] — 2026-05-02

### Added
- ⌨ **Stop-button tooltip surfaces Esc shortcut** (QQ69). When chat is
  streaming, the ■ stop button's tooltip now reads "중단 (Esc)" so
  users discover the QQ64 Esc-cancel without reading the changelog.

---
## [2.67.5] — 2026-05-02

### Added
- 🏷 **Send button shows current assignee in tooltip** (QQ68). Hover
  the chat ↑ send button to see "전송 (Enter) → claude:opus" or
  whatever the active assignee is. Updates on every dropdown
  change. Quick visual confirmation of which model is about to
  receive the prompt — useful when juggling QQ65 per-session
  models.

---
## [2.67.4] — 2026-05-02

### Fixed
- 🔁 **Backfill assignee on legacy sessions** (QQ67). QQ65 restored
  the session's stored assignee on switch, but legacy sessions
  created before the assignee field was set kept jumping to "no
  selection" until the user picked a model again. Switching to a
  legacy session now writes the dropdown's current assignee onto
  the session entry, so the session keeps its choice from then on.

### Verified
- ✅ Workflow + orchestrator tests: **43 passed** after QQ59-QQ66.

---
## [2.67.3] — 2026-05-02

### Fixed
- 🏷 **Robust auto-label for chat sessions across locales** (QQ66).
  The first-user-message auto-label only fired when `ses.label`
  matched the current `t('새 대화')` lookup — so a session created
  in Korean and used after switching to English (or vice-versa)
  kept the literal "새 대화" / "New conversation" forever. The
  match now uses a small set of known locale variants and also
  strips embedded `data:image/…` markdown from the seed so a pure-
  image first message doesn't produce a gibberish label.

---
## [2.67.2] — 2026-05-02

### Added
- 🔁 **Per-session assignee restored on session switch** (QQ65). Each
  chat session already records its own `assignee` (provider:model)
  but `_lcSwitchSession()` previously left the dropdown on whatever
  the user had picked last. Switching now also flips the dropdown
  to the session's stored assignee, registering it as a new option
  if the dropdown doesn't have it yet, and persisting to
  `cc.lazyclawChat.assignee`. Lets users keep one session on Opus
  for hard problems and another on Haiku for quick lookups without
  re-picking.

---
## [2.67.1] — 2026-05-02

### Added
- ⌨ **Esc cancels active chat streaming** (QQ64). Pressing Esc while
  the assistant is streaming aborts the in-flight `fetch` via
  `_lcChatAbortCtrl.abort()` and flashes a "스트리밍 중단됨" toast.
  Skipped when focus is in an `INPUT` so the QQ58 sidebar
  filter Esc-clear still works.

---
## [2.67.0] — 2026-05-02

**Q-series rollup** — milestone marker for the cumulative work landed
between 2.66.93 and 2.66.138 across the four pillars of the Ralph
prompt: n8n-parity workflows, zero-lag UI, fail-fast cancel, and
OpenClaw-parity chat. Backwards-compatible — no schema breaks, no
removed endpoints, every prior point release is still individually
listed below.

### Workflow editor — n8n parity
- `▶ 단독 실행` / `🍴 우클릭 단독 실행` / `📋 출력 복사` (QQ18, QQ19) —
  per-node debug execution.
- `📌 Pin Data` with inspector status panel (QQ20, QQ21) — freeze a
  node's last output and reuse it instead of re-running the model.
- Rubber-band drag selection, group drag, multi-copy/paste w/ internal
  edges, multi-delete with confirm (QQ27 → QQ30) — full multi-select
  editing loop.
- Align / distribute toolbar for 2+ selected (QQ34) — left/center/right
  + top/middle/bottom + horizontal/vertical distribute.
- 🟨 Sticky note nodes (QQ36) — free-floating markdown annotations,
  5 colors, resizable. Skipped from execution (QQ37) and orphan
  edges dropped (QQ59, QQ63).
- 🏷 Workflow tags + sidebar tag-chip filter (QQ38, QQ60) — quick
  organization for many workflows.
- 📊 Last-run mini Gantt in inspector (QQ46) — top 12 nodes by
  duration, live-updating during runs (QQ47, QQ48 throttled).

### Chat — OpenClaw parity
- ✏️ edit + resubmit (QQ22), 🍴 branch from any message (QQ23),
  ↳ branch lineage hint in sidebar (QQ24).
- 🔤 per-session token-usage badge (QQ26).
- 📋 code-block copy buttons (QQ31), ▾ collapse long messages (QQ32).
- 💾 per-session draft autosave with quota recovery (QQ33, QQ53),
  orphan sweep on tab open (QQ56), session delete cleanup fix (QQ54).
- ⬇ scroll-to-bottom button (QQ35), Cmd+Shift+[/] session nav
  (QQ50), Cmd+↑/↓ history recall (QQ51), Tab slash-command
  autocomplete (QQ62), `/help` lists shortcuts (QQ52).
- 🖼 image attach via paste, drop, and 📎 file picker (QQ39, QQ61)
  with stronger drag-over cue (QQ57).
- Multimodal routing for OpenAI / Anthropic / Gemini / Ollama in
  both one-shot and streaming paths (QQ40-QQ43); `data:image/...`
  stripped before claude-cli with a note (QQ49, QQ55); soft warning
  when sending an image to a non-vision assignee (QQ44).
- 🔎 Cmd+K search now also walks per-session histories (QQ45).
- Esc clears chat sidebar filter (QQ58).

### Performance
- RAF-coalesced canvas rendering (QQ25) — bulk operations no longer
  trigger N redundant SVG diffs.
- Inspector re-render throttled to ≤4 fps under SSE bursts (QQ48).
- Sticky annotations skipped from topological execution (QQ37).

---
## [2.66.138] — 2026-05-02

### Cleaned
- 🧼 **Drop sticky-attached edges at save time** (QQ63). Defensive
  pass in `_sanitize_workflow`: any edge whose `from` or `to`
  points at a sticky node is rejected. The client UI never
  renders ports on sticky so this is normally a no-op, but it
  matters when users import a hand-edited JSON.

---
## [2.66.137] — 2026-05-02

### Added
- ⌨ **Tab autocomplete for chat slash commands** (QQ62). Type `/` plus
  any prefix and press Tab — the line completes to the first matching
  command (`/clear`, `/system`, `/model`, `/export`, `/help`).
  Repeated Tab cycles through the remaining matches based on the
  original seed, not the autocompleted text. Mirrors the QQ12
  terminal Tab behavior.

---
## [2.66.136] — 2026-05-02

### Added
- 📎 **Explicit image attach button in chat composer** (QQ61). New
  `📎` button next to the send button opens a hidden `<input
  type="file" accept="image/*" multiple>` picker. Works alongside
  the existing paste/drop paths (QQ39). Each ≤ 8 MB image becomes a
  base64 `![]( data:… )` markdown reference in the textarea, then
  flows through the regular send path including the QQ40-43 vision
  routing.

---
## [2.66.135] — 2026-05-02

### Fixed
- 🏷 **Tag edits in inspector now refresh the sidebar live** (QQ60).
  QQ38's tag input only marked the workflow dirty — the sidebar
  chip strip and per-row tag chips waited until next save+reload
  to reflect the change. The inspector input now mirrors the new
  tag list into the in-memory `__wf.workflows` entry and re-runs
  `_wfRenderList()` on every keystroke, so the chip filter and
  per-row chips update instantly.

---
## [2.66.134] — 2026-05-02

### Cleaned
- 🧼 **Drop edges referencing sticky annotations during execution**
  (QQ59). QQ37 filtered sticky nodes from the topo input but left
  edges with `from` or `to` pointing at a sticky node in the edge
  list. Functionally inert (the executor's `results.get(src_id)`
  returned `None` for the missing source) but it bloated
  `inputs_map` with dangling entries and made debug dumps noisy.
  Both endpoints are now checked against the sticky-id set and
  the edge is dropped if either side hits.

---
## [2.66.133] — 2026-05-02

### Added
- ⌨ **Esc clears chat session filter** (QQ58). Press Esc inside the
  sessions sidebar filter input to clear the query in one keystroke.
  Mirrors the workflow node-search Esc behavior (line 2161) so users
  get the same muscle memory across both side panels.

---
## [2.66.132] — 2026-05-02

### Added
- 📷 **Stronger drag-over cue when files are dragged in** (QQ57). The
  composer's dashed outline turns blue (vs. the default amber) when
  the drag payload contains files, signalling that image / text
  attach is wired and ready. Subtle cue but pairs with QQ39 paste/
  drop to reduce "did anything happen?" hesitation.

### Verified
- ✅ Full pytest suite: **429 passed**, 2 pre-existing fails in
  `tests/test_provider_error_passthrough.py` (legacy assertions
  obsoleted by the FF1 fallback chain). No regression caused by
  the QQ18 → QQ57 changes.

---
## [2.66.131] — 2026-05-02

### Fixed
- 🧹 **Sweep orphan chat drafts/histories on tab open** (QQ56). One-
  time-per-tab-open scan: any `cc.lc.hist.<sid>` or
  `cc.lc.draft.<sid>` whose `<sid>` is no longer in `cc.lc.sessions`
  is removed. Cleans up legacy bytes left by users who deleted
  sessions before QQ54 fixed the cleanup match. Bounded in time —
  only runs when the chat view actually mounts.

---
## [2.66.130] — 2026-05-02

### Fixed
- 🛡 **Strip base64 images from the help-bot chat prompt too** (QQ55).
  QQ49 cleaned `handle_lazyclaw_chat_stream`, but the older help-bot
  SSE endpoint (line ~542 of `actions.py`) still piped the full
  prompt — including any image markdown forwarded from the chat —
  to `claude -p`. Now scrubbed via the same
  `_extract_inline_images()` helper.

---
## [2.66.129] — 2026-05-02

### Fixed
- 🧹 **Session delete now actually frees history + draft bytes**
  (QQ54). The old cleanup loop matched only keys ending in
  `:<sid>`, but the active schema is `cc.lc.hist.<sid>` and
  `cc.lc.draft.<sid>` — neither ends in a colon. Result: deleting
  a session left megabytes of orphan history in localStorage,
  silently shrinking the budget for new conversations and
  triggering QQ53 quota recovery prematurely. Cleanup now matches
  the real keys (and keeps the legacy suffix path as a fallback).

---
## [2.66.128] — 2026-05-02

### Fixed
- 💾 **Chat history quota recovery for embedded images** (QQ53). After
  QQ39 added base64 image attachments, a single chat session can
  push past localStorage's ~5–10 MB cap. `_lcSaveHistory()` now
  catches `QuotaExceededError` and recovers in two stages: (1)
  replace `data:image/…` URLs in the heaviest message with
  `_[image dropped to fit storage]_`, retry; (2) drop the oldest
  message; (3) repeat. Conversation text + recent images are
  preserved while ancient image bytes get evicted first.

---
## [2.66.127] — 2026-05-02

### Added
- 📖 **Keyboard shortcuts surfaced in `/help`** (QQ52). The `/help`
  slash command now lists the QQ50 session-nav keys, QQ51 history
  recall, Cmd+K search, Enter / Shift+Enter, and the QQ39 image
  paste/drop tip alongside the existing slash commands. Helps new
  users discover the recently-added shortcuts without spelunking
  the changelog.

---
## [2.66.126] — 2026-05-02

### Added
- ⌨ **Shell-history recall in chat composer** (QQ51). Cmd/Ctrl+↑
  pulls the previous user message into the composer; repeated
  presses walk back through the session's user messages.
  Cmd/Ctrl+↓ walks forward / clears back to a blank draft. The
  index resets on each send. Lets users tweak and resend a
  variation of an earlier prompt without scrolling and copying.

---
## [2.66.125] — 2026-05-02

### Added
- ⌨ **Cmd/Ctrl+Shift+[ / ] — prev/next chat session** (QQ50). Mirrors
  the workflow Cmd+[/] navigation (LL27) so users with many parallel
  conversations can jump session-to-session without leaving the
  keyboard. Skipped when focus is in an input/textarea so it doesn't
  hijack `[` typing in messages.

---
## [2.66.124] — 2026-05-02

### Fixed
- 🛡 **Strip base64 images from claude-cli prompts** (QQ49). claude-
  cli's `-p` flag is text-only — passing a multi-MB base64 blob via
  argv was either truncated by the OS or hallucinated about. The
  prompt is now scrubbed before invocation in both
  `ClaudeCliProvider.execute()` and the lazyclaw chat SSE relay
  (`actions.py::handle_lazyclaw_chat_stream`); the model receives a
  short note saying an image was attached and to switch to
  claude-api or a vision-capable assignee. Pairs with the QQ44
  client-side soft warning.

---
## [2.66.123] — 2026-05-02

### Performance
- 🚀 **Throttle inspector re-render under SSE bursts** (QQ48). QQ47
  re-renders the inspector on every status-sig change so the Gantt
  stays live, but a fast workflow (10+ nodes finishing within a
  second) would rebuild the inspector HTML 10× — visible lag on
  large boards. The trigger now keeps the dirty flag flip but only
  actually calls `_wfRenderInspector()` at most once every 250 ms
  (≤4 fps). User-driven renders bypass the throttle (they go through
  the normal `_wfRenderInspector({force:true})` paths).

---
## [2.66.122] — 2026-05-02

### Fixed
- 📊 **Gantt panel refreshes as run progresses** (QQ47, follow-up to
  QQ46). The inspector mini Gantt previously stayed stale during a
  run because the run-status apply path only invalidated the canvas
  cache, not `__wf._inspectorDirty`. The status-sig diff in the SSE
  apply loop now also marks the inspector dirty and re-renders it,
  so the duration bars grow live as nodes complete.

---
## [2.66.121] — 2026-05-02

### Added
- 📊 **Last-run mini Gantt in workflow inspector** (QQ46). After a
  workflow run completes, the inspector renders a per-node duration
  bar chart sorted descending — top 12 nodes, total time at the
  header, blue bars for normal runs, red for errors, amber for
  pinned (QQ20). Click a row to jump-select that node. Quick way
  to spot the slowest step without combing through `nodeResults`.

---
## [2.66.120] — 2026-05-02

### Fixed
- 🔎 **Cmd+K chat search now finds per-session histories** (QQ45).
  The search modal previously scanned only the legacy
  `cc.lazyclawChat.history.<assignee>` keys, so any conversation
  saved under the per-session `cc.lc.hist.<sid>` schema (used by
  QQ23 branching and QQ24 lineage) was invisible. Search now scans
  both keyspaces, labels each hit with the source session name,
  and the result button switches to the correct session before
  scrolling to the matched message.

---
## [2.66.119] — 2026-05-02

### Added
- ⚠ **Soft vision warning when sending images to non-vision models**
  (QQ44). If the composer text contains a base64 image but the
  assignee id doesn't match a vision-capable substring (`opus`,
  `sonnet`, `haiku`, `gpt-4/5/o`, `gemini`, `llava`, `vision`,
  `claude-`), the user gets a one-time-per-session toast warning.
  Stored in `sessionStorage` so the banner doesn't pile up if the
  same session repeatedly attaches images.

---
## [2.66.118] — 2026-05-02

### Fixed
- 🖼 **Ollama vision streaming completes the multimodal loop** (QQ43).
  `OllamaApiProvider.execute_stream()` now also runs through
  `_extract_inline_images()` and forwards the base64 strings as
  the `images` field. With QQ40 (cloud one-shot), QQ41 (Ollama
  one-shot), and QQ42 (cloud streaming), every chat path now
  correctly delivers attached images to the configured vision
  model.

---
## [2.66.117] — 2026-05-02

### Fixed
- 🖼 **Vision routing now also works for streaming responses** (QQ42).
  QQ40 wired multimodal images into the one-shot `execute()` paths
  but missed the streaming `execute_stream()` paths used by the
  lazyclaw chat (default route). OpenAI, Anthropic, and Gemini
  streaming now also call `_extract_inline_images()` and emit
  the appropriate image content blocks. Without this fix, dropping
  an image into the chat would only reach the model when the user
  ran a non-streaming workflow node.

---
## [2.66.116] — 2026-05-02

### Added
- 🖼 **Ollama vision routing** (QQ41). `OllamaApiProvider.execute()`
  now also runs through `_extract_inline_images()` and forwards the
  base64 strings as the Ollama `/api/generate` `images` field —
  the format vision-capable local models (llava, llama3.2-vision,
  bakllava, etc.) expect. Closes the multimodal loop for local
  models alongside the cloud providers covered in QQ40.

---
## [2.66.115] — 2026-05-02

### Added
- 🖼 **Vision routing for inline base64 images** (QQ40, multimodal end-
  to-end). New `_extract_inline_images()` helper in `ai_providers.py`
  pulls every `![alt](data:image/...;base64,...)` out of the prompt
  and returns a `(clean_text, [{mime,base64,data_url}])` pair.
  - **Anthropic API** — emits `image` content blocks with
    `source: {type: 'base64', media_type, data}`.
  - **OpenAI API** — emits `image_url` blocks with `image_url.url`
    set to the original data URL.
  - **Gemini API** — emits `inline_data: {mime_type, data}` parts.
  When no `data:image/` is found the helper short-circuits and the
  legacy plain-string content path is unchanged. Pairs with the
  QQ39 paste/drop UI: drop or paste an image into the chat composer
  and the configured vision model now actually sees it.

---
## [2.66.114] — 2026-05-02

### Added
- 📷 **Image attach in chat — paste & drop** (QQ39, OpenClaw parity).
  Dropping an image file (≤ 8 MB) onto the composer or pasting one
  from the clipboard now embeds it as a base64 `![name](data:…)`
  markdown reference. User messages are now markdown-rendered so the
  image displays inline in the conversation. Multimodal provider
  routing comes next; this iteration covers UI capture + history
  persistence so images survive refresh and export.

### Changed
- User chat messages now use `marked.parse` (previously plain
  `<pre>`). Plain text is unaffected; backticked code, lists, and
  links now render as expected.

---
## [2.66.113] — 2026-05-02

### Added
- 🏷 **Workflow tags + sidebar tag filter** (QQ38, n8n parity for
  organizing many workflows). Each workflow now has a `tags: string[]`
  field — clamped to 20 chars each, max 10 per workflow, lowercased
  and de-duplicated server-side. Sidebar shows a chip strip above
  the list ("All / #prod / #demo / …"); clicking a chip filters
  the workflow list. Tags also appear as small chips on each list
  row and are editable as a comma-separated input in the inspector
  meta block. Composes with the existing fuzzy search.

---
## [2.66.112] — 2026-05-02

### Performance
- 🚀 **Sticky annotations skipped during execution** (QQ37). The
  topology builder in `_run_one_iteration` now filters out
  `sticky` nodes before computing levels, so they don't sit in
  the level-0 parallel batch alongside `start`. Pure annotations
  no longer occupy a thread or contribute to execution latency.

---
## [2.66.111] — 2026-05-02

### Added
- 🟨 **Sticky note nodes on workflow canvas** (QQ36, n8n parity).
  New `sticky` node type — free-floating markdown annotations that
  don't affect execution. 5 colors (yellow / blue / green / pink /
  gray), resizable (120-800 px width, 80-800 px height), markdown
  rendered via `marked.parse`. Server-side: registered in
  `_NODE_TYPES`, sanitized with text / color / width / height,
  executor returns instantly with empty output. Client-side: new
  "주석" palette category, custom SVG renderer using
  `<foreignObject>`, color picker + dimension inputs in the editor.

---
## [2.66.110] — 2026-05-02

### Added
- ⬇ **Scroll-to-bottom button in chat** (QQ35). When the chat log is
  scrolled more than 120 px above the latest message, a circular ⬇
  button appears at the bottom-right. Clicking jumps to the newest
  message. Hides automatically when at the bottom. Essential for
  long sessions where streaming output pushes content past the
  fold.

---
## [2.66.109] — 2026-05-02

### Added
- 📐 **Align / distribute toolbar for multi-selected nodes** (QQ34,
  n8n parity). Whenever 2+ nodes are selected (Shift+click, lasso, or
  Cmd+A), an 8-button bar appears in the workflow toolbar:
  ⫷ left, ⇔ horizontal center, ⫸ right, ⫶↑ top, ⇕ vertical center,
  ⫶↓ bottom, ≡↔ horizontal distribute (3+ nodes), ≡↕ vertical
  distribute (3+ nodes). Pushes one undo step. Pairs with QQ27 / QQ28
  / QQ29 / QQ30 for the full multi-select editing flow.

---
## [2.66.108] — 2026-05-02

### Added
- 💾 **Per-session draft autosave for chat composer** (QQ33). Typing
  in the composer now persists to `localStorage["cc.lc.draft.<sid>"]`
  with a 350 ms debounce. On tab open / refresh, the draft is
  restored if the textarea is empty. Sending or running a slash
  command clears the draft. No more lost prompts after a refresh
  or accidental tab swap.

---
## [2.66.107] — 2026-05-02

### Added
- ▾ **Collapsible long messages in chat** (QQ32). Assistant or user
  messages exceeding ~1500 chars or ~30 lines now collapse to 300 px
  with a fade overlay and a `▾ 더보기 (N자)` button. Click to expand;
  collapse again with `▴ 접기`. Keeps long sessions scrollable
  without losing access to full content.

---
## [2.66.106] — 2026-05-02

### Added
- 📋 **Code block copy buttons in chat** (QQ31, OpenClaw parity).
  Every `<pre>` block in an assistant message now gets a top-right
  📋 button. Clicking writes the inner `<code>` text to the
  clipboard and flashes ✓ for 1.2 s. Saves the select-all-then-copy
  dance for snippets.

---
## [2.66.105] — 2026-05-02

### Added
- 🗑 **Multi-select delete with confirm** (QQ30, n8n parity). Delete /
  Backspace now removes every node in `__wfMultiSelected` (and all
  edges incident on the set) in one undo step. Asks for confirmation
  when the selection has more than 3 nodes — small lassos delete
  silently. Pairs with QQ27 / QQ28 / QQ29.

---
## [2.66.104] — 2026-05-02

### Added
- 📋 **Multi-node copy/paste with internal edges** (QQ29, n8n parity).
  Cmd+C now copies every node in `__wfMultiSelected` (or just the
  single selection if multi is empty) plus every edge whose endpoints
  both fall inside the set. Cmd+V remaps the edge endpoints to fresh
  node ids so the cluster pastes wired up. Pasted nodes become the
  new multi-selection so QQ28 group-drag immediately applies — lasso,
  copy, paste, drag the duplicate cluster anywhere.

---
## [2.66.103] — 2026-05-02

### Added
- 🟦 **Group drag for multi-selected nodes** (QQ28, n8n parity).
  Clicking and dragging any node that belongs to the active multi-
  selection now moves all selected nodes together while preserving
  their relative layout. Lead-node grid snap (Alt to bypass) is
  applied via a delta so the cluster doesn't drift on snap. Pairs
  with QQ27 rubber-band: lasso a cluster, then move it as one.

---
## [2.66.102] — 2026-05-02

### Added
- 🟦 **Rubber-band drag selection on workflow canvas** (QQ27, n8n
  parity). Hold Shift and drag on an empty area of the canvas to
  draw a dashed selection rectangle. On release, all nodes whose
  bounding box intersects the rectangle are added to the multi-
  selection (composes with existing Shift+click). Cmd+A still
  selects-all. Replaces the missing "drag-to-select" gap that was
  the most-asked n8n feature.

---
## [2.66.101] — 2026-05-02

### Added
- 🔤 **Per-session token-usage badge in chat sidebar** (QQ26). Each
  session row now shows `🔤 12.4k` (sum of `tokensIn + tokensOut`
  across all messages) next to the timestamp. Quick visibility into
  which conversations are draining the budget without opening them.

---
## [2.66.100] — 2026-05-02

### Performance
- 🚀 **Workflow canvas RAF coalescing** (QQ25). Multiple
  `_wfRenderCanvas()` calls within one animation frame now collapse
  to a single sync render via `requestAnimationFrame`. Bulk
  operations (paste many nodes, undo across multiple changes, run-
  status updates from rapid SSE ticks) no longer trigger N redundant
  SVG diffs. Drag stays smooth — it uses
  `_wfApplyDragTransform()` which writes `setAttribute` directly and
  bypasses the renderer. Callers that genuinely need an immediate DOM
  can use the new `_wfRenderCanvasNow()` escape hatch.

---
## [2.66.99] — 2026-05-02

### Added
- ↳ **Branch lineage hint in chat sidebar** (QQ24). Sessions created
  via QQ23 branching now display `↳ <parent label> #<idx>` in the
  sidebar row. Click the lineage chip → jumps to the parent session.
  Lets users navigate the conversation tree without losing where
  they came from.

---
## [2.66.98] — 2026-05-02

### Added
- 🍴 **Branch conversation from any message** (QQ23, ChatGPT parity).
  Hovering any chat message now exposes a 🍴 button. Clicking creates
  a new session whose history is everything up to and including that
  message, with `parentId` and `branchedAt` metadata so the lineage
  is recoverable. Lets users explore alternative directions without
  losing the original conversation.

---
## [2.66.97] — 2026-05-02

### Added
- ✏️ **Edit user message + resubmit in lazyclaw chat** (QQ22, OpenClaw
  parity). Hovering a user message now exposes a ✏️ button. Click →
  history is truncated at that index and the original text is
  pre-filled in the composer; user revises and Enter resubmits. Pairs
  with the existing 🔄 regenerate on assistant messages.

---
## [2.66.96] — 2026-05-02

### Added
- 📌 **Pin status panel in inspector** (QQ21). Selected pinned nodes
  now expose an amber expandable panel showing pinned content
  (preview, char count, unpin button) directly in the inspector — no
  longer hidden behind right-click. Discoverability fix for QQ20.

---
## [2.66.95] — 2026-05-02

### Added
- 📌 **Pin Data on workflow nodes** (QQ20, n8n signature feature).
  Right-click any session/subagent node with a recorded last output
  and choose `📌 마지막 출력 핀 설정`. Subsequent runs short-circuit
  inside `_execute_node` — the pinned text is returned immediately
  with `provider="pinned"` and zero cost/tokens, no LLM call. Lets
  users freeze an expensive upstream result and iterate downstream
  nodes for free. Pinned nodes show an amber 📌 badge on the canvas.
  Persisted via `data.pinned` + `data.pinnedOutput` (32 KB cap).

---
## [2.66.94] — 2026-05-02

### Added
- ▶📋 **Canvas right-click: Run-alone + Copy output** (QQ19, n8n parity).
  The node context menu now exposes `▶ 단독 실행` (only for
  session/subagent — reuses QQ18 endpoint) and `📋 출력 복사` (only
  visible when the node has a recorded last output, copies the raw
  `output`/`error` to clipboard). Faster debug loop without opening
  the inspector.

---
## [2.66.93] — 2026-05-02

### Added
- ▶ **Single-node execution in workflow inspector** (QQ18, n8n parity).
  When a `session`/`subagent` node is selected, the inspector now shows
  a `▶ 단독 실행` button next to `편집`. Clicking it POSTs to the new
  `/api/workflows/run-node` endpoint, which executes that one node in
  isolation (no upstream collection, no downstream propagation) and
  returns the raw provider response. Result is shown in a modal with
  provider/model/duration/tokens/cost chips and a copy button. Mirrors
  n8n's "Execute Node" debug feature — lets users iterate on a single
  prompt without re-running the whole DAG. Server-side reuses
  `_execute_node` with a synthetic `single-<hex>` run id so the
  cancellable-subprocess registry still applies.

---
## [2.66.92] — 2026-05-02

### Added
- ⏱ **Per-command elapsed time in the lazyclaw terminal** (QQ17).
  `api_lazyclaw_term` now returns `durationMs`; client appends
  `(123ms)` to the output line. Useful for spotting slow CLI
  invocations (claude cold start, ollama list scan).

---
## [2.66.91] — 2026-05-02

### Added
- ⭐ **Starred-only filter in chat search** (QQ16). The search
  modal gets a `⭐` checkbox; toggling it restricts results to
  starred messages. Result rows now also display the ⭐ icon
  on starred hits.

---
## [2.66.90] — 2026-05-02

### Added
- ⭐ **Star toggle on chat messages** (QQ15). Click the
  ☆/⭐ button next to copy/regenerate to mark a message as
  starred — visualised with an amber outer ring on the
  bubble. State (`m.starred`) persists with the message so
  it travels through export and search.

---
## [2.66.89] — 2026-05-02

### Added
- 🔢 **Live char + approximate-token count** under the chat
  textarea (QQ14). Approximation is `chars / 3` — coarse but
  good enough for both English and CJK so the user has an
  early-warning before hitting context-window limits.

---
## [2.66.88] — 2026-05-02

### Added
- 🖱 **Empty-canvas right-click context menu** (QQ13). Quick
  actions when nothing is selected:
  - ＋ 새 노드 추가 · 📋 붙여넣기 (greyed when clipboard empty)
  - 🎯 화면 맞춤 · ⊞ 격자 표시 · 📋 인스펙터 토글
  Mirrors n8n's right-click background menu.

---
## [2.66.87] — 2026-05-02

### Added
- 🔠 **Tab autocomplete in the lazyclaw terminal** (QQ12). Press
  `Tab` against the whitelist; single match auto-completes,
  multiple candidates print as a hint line so the user can
  narrow further.

---
## [2.66.86] — 2026-05-02

### Added
- ⊞ **Canvas dot-grid toggle** (QQ11). New `⊞` button in the
  bottom-right floating cluster toggles a subtle 20px-step
  dot grid behind the workflow canvas — visual guide for the
  10px node-snap step. Preference persisted in localStorage.

---
## [2.66.85] — 2026-05-02

### Fixed
- 🛎 **De-duplicated workflow completion notifications** (QQ10).
  Previously the browser notification + result modal could each
  fire on every SSE poll while the run was already terminal,
  spamming the user. Now sentinel `__wf._lastCompletedRunId`
  guarantees one fire per run id.
- 📋 **Fail-fast summary toast on err** (QQ10). When a run ends
  in `err` and at least one node was sibling-cancelled, an
  inline toast surfaces the breakdown:
  `🔴 N 실제 실패 · ⏹ M 자동 취소됨 · ✓ K 완료`.

---
## [2.66.84] — 2026-05-02

### Added
- 🔍 **Chat session filter** input above the sidebar list (QQ9).
  Live-matches session label / preview / assignee.
- 🖱 **Right-click on a chat session** opens a context menu:
  - ✏️ Rename
  - 📌 / 📍 Pin / Unpin (pinned sessions float to the top)
  - 🗑 Delete (also wipes the session's history payload)

---
## [2.66.83] — 2026-05-02

### Added
- 📌 **Floating description tag in canvas top-left** (QQ8).
  Shows `name` + truncated `description` so the user remembers
  the workflow's purpose without opening the inspector. Click
  jumps to the inspector's description textarea for editing.

---
## [2.66.82] — 2026-05-02

### Changed
- 🔗 **Auto-place + auto-wire on new node spawn** (QQ7, n8n parity).
  When a node is selected and the user adds a new one, the new
  node lands +260px to the right at the same Y, and an edge is
  drawn from the selected node automatically. Branch nodes use
  the `out_y` port; `start` / `output` types skip auto-wire.

---
## [2.66.81] — 2026-05-02

### Added
- ⌨ **Bash-style history navigation in the terminal** (QQ6).
  - `↑` / `↓` walk through prior commands; in-flight draft is
    preserved when you hit `↑` and restored when you scroll
    past the bottom of the stack with `↓`.
  - `Ctrl+R` opens a reverse-i-search popup that live-filters
    history; `Enter` picks the top match.

---
## [2.66.80] — 2026-05-02

### Changed
- ⏸ **Explicit `⏸` badge on disabled workflow nodes** (QQ5).
  Previously the only cue was opacity + grayscale + dashed
  border — easy to miss on dark backgrounds. Now a small
  gray-white pill in the top-right corner shows up whenever
  `.wf-disabled` is on the node.

---
## [2.66.79] — 2026-05-02

### Added
- 🩺 **Auto health-check on terminal tab open** (QQ4). Once an
  hour, the first visit auto-runs `claude --version`, `ollama list`,
  `gemini --version`, `codex --version`, and `git status -sb` so
  the user immediately sees provider state.
- 📜 **Whitelist expanded**: `uptime`, `df -h`, `docker --version /
  ps / images`, `uname -a / -s / -m`, `git diff --stat`,
  `git diff --cached --stat`, `git status -sb`,
  `git log --oneline -20`, `which docker`. `echo` explicitly
  rejected. Validation tightened so an empty arg-prefix list also
  bounces.

---
## [2.66.78] — 2026-05-02

### Added
- 📝 **Per-node note field** (QQ3, n8n parity).
  - Inspector now has a collapsible 📝 메모 textarea (≤ 4000
    chars) beneath each node's edit/delete buttons. Persists
    with the workflow.
  - Hover tooltip on the canvas surfaces the note (amber 📝
    line) so the user remembers a node's purpose without
    opening it.
  - Server `_sanitize_node` preserves `disabled` (PP2) and
    `notes` (QQ3) across **every** node type.

---
## [2.66.77] — 2026-05-02

### Added
- ⌨ **터미널 tab in LazyClaw mode** — whitelisted read-only
  commands so the user can check CLI / provider state without
  opening a real Terminal (QQ2). Examples:
  `claude --version`, `claude config list`, `claude config get <key>`,
  `ollama list`, `ollama ps`, `gemini --version`, `codex --version`,
  `lazyclaude status`, `git status`, `git log -5`, `which …`,
  `node --version`, `python3 --version`. Shell metacharacters
  rejected. 15 s timeout. Write commands (`config set`, install,
  login) intentionally blocked — use the Settings tab.
- 📋 Server endpoint `POST /api/lazyclaw/term` enforces the
  whitelist and runs the matched binary via `subprocess.run`
  (stdin DEVNULL, output truncated to 32 KB stdout / 8 KB stderr).
- ⌨ History recall (Up arrow on empty input), command echo
  with green `$`, mac-term-style log pane.

---
## [2.66.76] — 2026-05-02

### Added
- ⌨ **Slash commands in the LazyClaw chat input** (QQ1) — terminal-
  like settings without leaving the keyboard:
  - `/clear` — wipe history
  - `/system [text]` — set or clear the system prompt
  - `/model <provider:model>` — switch assignee inline
  - `/export` — download conversation as markdown
  - `/help` — list commands inline as an assistant message

---
## [2.66.75] — 2026-05-02

### Added
- 💵 **Live cumulative cost in the run banner** (PP5). The
  banner's meta line now shows `done/total · elapsed · $cost`
  and updates 1 Hz via the existing ticker. Skipped when no
  provider in the run reports cost (free-tier / local Ollama).

---
## [2.66.74] — 2026-05-02

### Added
- ⏱ **Per-workflow node timeout** override (PP4). Slider in
  the inspector's policy section adjusts `policy.nodeTimeout`
  (0–600 s; 0 = server default, currently 180 s). Plumbed
  through `_run_one_iteration → _execute_node → execute_with_assignee`.
  Useful for graphs with quick OpenAI/Gemini API calls (drop
  to 60 s for snappier fail-fast) or for graphs that legitimately
  need long Claude reasoning (raise to 600 s).

---
## [2.66.73] — 2026-05-02

### Changed
- 📖 **`D` shortcut now visible in `?` help** (PP3).
- ⏸ **Inspector got a quick "비활성" checkbox** next to the
  edit / delete buttons so users who don't know the shortcut
  can still toggle disable from the side panel.

---
## [2.66.72] — 2026-05-02

### Added
- ⏸ **Disable / enable nodes** without deleting them (PP2,
  n8n parity).
  - `D` key on the workflow canvas toggles `data.disabled` for
    the selected node. Same in the right-click context menu.
  - Disabled nodes render at half opacity with grayscale +
    dashed border so the user sees them in context.
  - Server-side, `_run_one_iteration` skips them with
    `status='skipped'` — no subprocess fired, no cost incurred.

---
## [2.66.71] — 2026-05-02

### Added
- 📎 **Drag-and-drop text/code files into the chat input** (OO7).
  Drop a `.md` / `.json` / `.py` / `.tsx` / etc. and the contents
  appear as a fenced code block in the textarea (with a comment
  line `// <filename> · <bytes>B`). Multiple files OK; binary
  files are skipped with a warning toast.

---
## [2.66.70] — 2026-05-02

### Changed
- 🟠 **Workflow nodes auto-cancelled by fail-fast (MM1) get an
  amber dashed border** instead of a hard red one (PP1).
  `data-status="cancelled"` is mapped client-side from
  `(status='err' && error contains 'cancelled by sibling-node failure')`.
  Real failures keep the red border. Same red/amber distinction
  as the run-result modal (NN1) and the active sessions panel
  (NN3) — now also on the canvas itself.

---
## [2.66.69] — 2026-05-02

### Added
- 🔎 **Chat history full-text search** (OO6, Cmd/Ctrl+K).
  Walks every `cc.lazyclawChat.history.*` localStorage key,
  matches against the query, surfaces hits in a modal with
  snippet + role icon + assignee label. Clicking a hit
  switches the active assignee, scrolls the matching message
  into view, and flashes its border for 1.4 s.

---
## [2.66.68] — 2026-05-02

### Added
- 🔄 **Regenerate assistant reply with another model** (OO5).
  Hovering an assistant message exposes a `🔄` button that opens
  a provider:model picker; selecting one drops the old reply and
  re-sends the original user message under the new assignee.
  Lightweight side-by-side comparison without leaving the chat.

---
## [2.66.67] — 2026-05-02

### Added
- ⚙ **System prompt input** for the chat tab (OO4). Toggle via
  `⚙ 시스템` button; 3-line textarea above the conversation log;
  value persists per-assignee in localStorage. Sent to the
  server as `systemPrompt` and prepended to the prompt as a
  `[System instructions: …]` line.
- ⏹ **Cancel-mid-stream** (OO4). The `📨 전송` button flips to a
  red `■ 중단` while a stream is in flight. Clicking it aborts
  the `fetch` (`AbortController`); the partial response is
  preserved and a `⏹ 사용자가 중단함` line is appended.

---
## [2.66.66] — 2026-05-02

### Added
- 🌊 **Streaming chat response** for Claude assignees (OO3).
  `POST /api/lazyclaw/chat/stream` runs `claude-cli` with
  `--output-format stream-json --include-partial-messages`,
  parses `content_block_delta` lines, and relays them as SSE
  `token` events. Client uses `fetch + ReadableStream` to mutate
  the assistant message in-place, throttled to 30Hz so heavy
  streams don't thrash the DOM.
- 🪝 Non-Claude providers fall through to the one-shot
  `/api/lazyclaw/chat` endpoint and emit a single `token` event
  so the UI path stays uniform.

---
## [2.66.65] — 2026-05-02

### Added (LazyClaw 채팅 polish)
- 📝 **Markdown rendering for AI replies** (OO2). Code blocks,
  lists, tables, headings render properly via `marked`. User
  messages stay verbatim to preserve copy-paste fidelity.
- 📋 **Per-message copy button** in the chat log header.
- 📥 **Export conversation as markdown** (`📥 내보내기` button).
  Filename pattern: `lazyclaw-chat-<assignee>-<timestamp>.md`.

---
## [2.66.64] — 2026-05-02

### Added
- 💬 **AI 채팅 tab** in LazyClaw mode (OO1). Direct conversation
  with any registered AI provider (Claude / OpenAI / Gemini /
  Ollama / Codex / etc) — `n8n`-style "playground" with provider:model
  dropdown, per-assignee conversation history (persisted in
  localStorage, last 100 messages), Enter-to-send / Shift+Enter
  newline. Backend `/api/lazyclaw/chat` reuses
  `execute_with_assignee` so the entire FF1 fallback chain + MM1
  fail-fast plumbing applies here too.

---
## [2.66.63] — 2026-05-02

### Added
- 📋 **Fail-fast summary card at the top of the run-result modal**
  (NN4). Counts how many nodes auto-cancelled (amber) vs. failed
  for real (red), with a one-line hint that auto-cancelled nodes
  aren't the cause — the user knows to fix the red one first.

---
## [2.66.62] — 2026-05-02

### Changed
- 🎨 **Active sessions panel uses amber for auto-cancelled rows**
  (NN3). Sibling-cancelled nodes (MM1) now show
  `⏹ 형제 노드 실패로 자동 취소됨` in amber, matching the
  run-result modal's distinction. Real errors keep `⚠` red.

---
## [2.66.61] — 2026-05-02

### Changed
- ⏹ **Sibling-cancelled nodes shown distinct from real errors**
  (NN1). Result-modal cards for nodes whose subprocess was
  SIGTERM'd by MM1's fail-fast now show `(자동 취소됨)` in amber
  with `⏹ 형제 노드 실패로 자동 취소됨` instead of the red
  `⚠ cancelled by sibling-node failure`. The "switch provider"
  UI is suppressed on these — they weren't the real failure.

---
## [2.66.60] — 2026-05-02

### Added
- 📂 **Multi-Claude session reuse picker** in the workflow node
  inspector (CC5). Next to the `session_id 직접 입력` field is a
  `📂 최근` button that opens a modal listing the 30 most recent
  Claude sessions (project, started-ago, first-prompt preview).
  One click writes the session_id back into the draft so the node
  resumes that conversation instead of spawning a fresh one. The
  per-node Active-Sessions panel from DD2 already shows live
  in-flight sessions; this closes the gap for picking historical
  ones.

---
## [2.66.59] — 2026-05-02

### Fixed
- 🛑🛑 **Fail-fast actually fast now** (MM2). MM1 in v2.66.58
  added `SIGTERM` of sibling subprocesses on first error, but the
  outer `with ThreadPoolExecutor:` context still blocked on the
  in-flight thread — the thread's provider would `cancelled by
  sibling failure` retry through fallback chain, taking 60-90s.
  Switched to a manual `pool.shutdown(wait=False, cancel_futures=True)`
  so `_run_one_iteration` returns the moment the err is detected.
  **Measured: 89s → 0.01s** (≈10000× faster) on a 2-node parallel
  level where one fails immediately and the sibling was hanging.

---
## [2.66.58] — 2026-05-02

### Fixed
- 🛑 **Workflow fail-fast: any node fail = whole-run stop** (MM1).
  Previously, when one node in a parallel topological level failed
  (e.g. GPT 401), sibling nodes (Claude / Gemini CLIs) kept hanging
  for their own 60–300s subprocess timeout — the user saw `Claude
  1024s ⏱` ticking forever while GPT was already red. Three-layer
  fix:
  1. New `_PROC_REGISTRY` keyed by `runId` in `workflows.py` —
     every CLI provider's live `Popen` is registered there.
  2. `_run_one_iteration` calls `_terminate_run_procs(runId)` the
     instant a sibling node returns `status='err'`. Sibling
     subprocesses get `SIGTERM` (then `SIGKILL` after 2s).
  3. Providers (`ClaudeCli`, `GeminiCli`, `Codex`) switched from
     `subprocess.run` to `Popen + communicate(timeout)` via a new
     `_run_cancellable` helper. A signal-killed process is reported
     as `cancelled by sibling-node failure` instead of timeout.

---
## [2.66.57] — 2026-05-02

### Added
- 💾 **Workflow autosave (debounced 30s)** (LL28). Whenever the
  user marks the workflow dirty, an autosave timer is scheduled
  30 seconds out; further edits reset the timer so we never save
  mid-typing. Explicit `Cmd+S` cancels any pending autosave.
  The "저장됨" toast is suppressed for autosaves — instead the
  toolbar dirty indicator's tooltip records the timestamp
  (`자동 저장됨 · HH:MM:SS`) so the user can see it happened
  without being interrupted.

---
## [2.66.56] — 2026-05-02

### Added
- ⌨ **`Cmd/Ctrl + [` and `Cmd/Ctrl + ]` cycle workflows**
  (LL27, n8n parity for editor tab switching). Previous /
  next entry in the sidebar list. Wraps. Skipped when only
  one workflow exists.

---
## [2.66.55] — 2026-05-02

### Changed
- 🔍 **Workflow list search uses fuzzy matching** (LL26).
  Same subsequence + substring algorithm as the canvas node
  search. CJK falls back to substring.

---
## [2.66.54] — 2026-05-02

### Changed
- 🔍 **Node search input gets a clear button + Esc support**
  (LL25). Placeholder text now hints at fuzzy syntax
  (`예: fy / ses`). The `×` button shows up only when a
  query is active; pressing `Esc` inside the field also clears.

---
## [2.66.53] — 2026-05-02

### Changed
- 🔍 **Node search uses fuzzy matching** (LL24, n8n parity).
  Subsequence match + substring across title / type / label /
  assignee / agentRole. Typing "fy" highlights "frontend",
  "ses" highlights "session". Korean / Chinese queries fall
  back to substring (subsequence is meaningless for CJK).

---
## [2.66.52] — 2026-05-02

### Added
- ↔ **Inspector panel resize handle** (LL23, n8n parity). Drag
  the left edge of the inspector to resize between 240–720px.
  Width persists in localStorage so it sticks across sessions.

---
## [2.66.51] — 2026-05-02

### Added
- 🗺 **Minimap drag-to-pan** (LL22, n8n parity). Hold the mouse on
  the minimap and the canvas viewport follows the cursor smoothly,
  not just on click.

---
## [2.66.50] — 2026-05-02

### Added
- 📖 **Help modal lists mouse actions** (LL21). Right-click for
  node/edge context menus and minimap-click to pan are now
  discoverable from the `?` shortcut help on the workflow tab.

---
## [2.66.49] — 2026-05-02

### Added
- 🖱 **Right-click on an edge → Delete option** (LL20). The
  existing node context menu is now reused; right-clicking
  on an edge path selects it and offers Delete (`⌫`).

---
## [2.66.48] — 2026-05-02

### Added
- 🗺 **Click on the minimap pans the canvas** to that location
  (LL19, n8n parity). Inverse minimap→world transform — useful
  on large workflows where you need to jump to a specific area
  without dragging the canvas across the viewport.

---
## [2.66.47] — 2026-05-02

### Fixed
- 🔢 **Zoom-cluster label syncs with the actual viewport** on
  canvas mount and after fit-to-screen (LL18). Was hardcoded to
  100%; now reflects real zoom (e.g. 78% after a fit on a wide
  workflow).

---
## [2.66.46] — 2026-05-02

### Added
- 🔍 **n8n-style floating zoom cluster** in the canvas bottom-right
  (LL17). `−` zoom out, current % (click to reset to 100%), `+`
  zoom in. Always visible — the user no longer needs to remember
  `Cmd+0` / `Cmd+1` to recover from a stray pinch. Label updates
  live during wheel zoom too.

---
## [2.66.45] — 2026-05-02

### Added
- ➕ **`Cmd/Ctrl + N` opens the new-node editor** (LL16). Lets
  users add a node without reaching for the toolbar button.
  Browser may intercept `Cmd+N` for a new window in some
  contexts; on the workflows tab the in-app handler wins.

---
## [2.66.44] — 2026-05-02

### Added
- 🛡 **beforeunload guard for unsaved workflow changes** (LL15,
  n8n parity). When the workflow has dirty edits and the user
  reloads or closes the tab, the browser shows its native
  "Changes you made may not be saved" prompt. Saving (Cmd+S)
  clears the dirty flag and the prompt is skipped on next exit.

---
## [2.66.43] — 2026-05-02

### Added
- 🖱 **Right-click on a node opens a context menu** (LL14, n8n
  parity). Edit / Duplicate / Delete with keyboard shortcuts
  shown alongside. Auto-positions to stay inside the viewport;
  closes on outside-click or Esc.

---
## [2.66.42] — 2026-05-02

### Added
- ▶ **`Cmd/Ctrl + Enter` runs the workflow** (or cancels it if
  already running) (LL13, n8n parity). Avoids the browser-reload
  conflict of `Cmd+R`. Uses the existing `_wfRunOrCancel` toggle
  so the same key starts and stops a run.

---
## [2.66.41] — 2026-05-02

### Added
- ⌨ **`Cmd/Ctrl + E` (or `Enter`) opens the editor** for the
  selected node (LL12). Closes the keyboard navigation loop:
  Tab to land on a node, Cmd+E to edit its content, Esc to close.

---
## [2.66.40] — 2026-05-02

### Added
- ⌨ **`Tab` / `Shift+Tab` cycle through nodes** (LL11). Combined
  with arrow-key nudging this gives full keyboard-only canvas
  navigation: Tab to land on a node, arrows to move it, Cmd+D
  to duplicate.

---
## [2.66.39] — 2026-05-02

### Added
- 🗺 **`Cmd/Ctrl + M` toggles the minimap** (LL10). Choice
  persists in localStorage so users who don't want the floating
  minimap don't have to re-hide it every session.

---
## [2.66.38] — 2026-05-02

### Added
- 📖 **Shortcut help modal updated** with the 14 new keybindings
  added in v2.66.20–v2.66.37 (LL9). Press `?` on the workflow
  canvas to discover them. Includes Ctrl+D, Ctrl+A, Ctrl+I,
  zoom shortcuts, arrow nudges, Shift+L auto-layout, perf HUD,
  Wheel pan, Cmd+Wheel zoom, Alt+drag, dblclick fit.

---
## [2.66.37] — 2026-05-02

### Added
- 🪄 **`Shift + L` auto-layout** (LL8). Runs the existing
  Beautify routine without the fit-to-screen step, so the
  topology snaps into clean alignment while the user keeps
  their current pan/zoom.

---
## [2.66.36] — 2026-05-02

### Added
- 📋 **`Cmd/Ctrl + I` toggles the inspector side panel** (LL7). Lets
  the user reclaim full canvas width without reaching for the toolbar
  button.

---
## [2.66.35] — 2026-05-02

### Added
- 🎯 **`Cmd/Ctrl + A` selects every node** in the active workflow
  (LL6, n8n parity). Populates the existing multi-select set so
  `Cmd+C`, `Delete`, and the arrow-key nudge all operate on the
  whole graph at once.

---
## [2.66.34] — 2026-05-02

### Added
- 📑 **`Cmd/Ctrl + D` duplicates the selected node** (LL5, n8n parity).
  Cloned at +40px offset; the new node becomes the selection so a
  user can immediately drag it into place or edit.

---
## [2.66.33] — 2026-05-02

### Added
- ⌨ **Arrow-key node nudging** on the workflow canvas (LL4, n8n parity):
  - `←/→/↑/↓` — move selected node by 10 px (matches the new grid step)
  - `Shift + arrow` — fine 1 px adjust

---
## [2.66.32] — 2026-05-02

### Added
- 🧲 **Node-drag grid snap** (LL3, n8n parity). Drop position now
  rounds to the nearest 10px so manually-arranged workflows look
  tidy without nudging pixel-by-pixel. **Hold `Alt`** while dragging
  to bypass and place freely.

---
## [2.66.31] — 2026-05-02

### Added
- 📊 **Perf HUD** — `Cmd/Ctrl + Shift + P` toggles a corner overlay
  showing live FPS, the longest main-thread task in the previous
  second, and total long-task time per second (LL2). Lets the user
  confirm at a glance whether a perceived lag is the dashboard,
  a browser extension, or system load. State persists across
  reloads via localStorage.

---
## [2.66.30] — 2026-05-02

### Performance
- ⚡ **Toolbar update batched to 1× per frame** (LL1). The
  workflow toolbar (`name`, `dirty` indicator, undo depth) was
  refreshed synchronously on every inspector input — 60+ writes
  per second when the user is typing into a textarea. Now coalesced
  via `requestAnimationFrame` to one write per paint frame.

---
## [2.66.29] — 2026-05-02

### Performance
- 🪪 **`/app.js` now versioned + immutable** (KK2). `_send_static`
  rewrites the `<script src="/app.js">` reference in `index.html`
  to `<script src="/app.js?v=<mtime>">`, and any URL with `?v=`
  gets `Cache-Control: public, max-age=31536000, immutable`.
  After the first load, the browser serves `app.js` from disk cache
  without even a 304 round-trip — the URL itself changes whenever
  app.js does, so staleness is impossible.

---
## [2.66.28] — 2026-05-02

### Fixed
- 🤏 **Trackpad pinch-zoom dampening** (KK1). macOS reports trackpad
  pinches as a high-frequency stream of `ctrlKey + wheel` events with
  very small `deltaY`, which the user perceives as "the canvas keeps
  zooming out by itself". Three fixes:
  1. **Drop sub-noise events** — `|deltaY| < 1.5` is ignored entirely.
  2. **Halve zoom sensitivity** — `0.0015 → 0.0008` per delta unit.
     A deliberate pinch still zooms; stray contact doesn't visibly
     move the view.
  3. **Raise minimum zoom** — `0.3 → 0.5`. Below 0.5 the canvas was
     unusable and required `Cmd+0` to recover.

---
## [2.66.27] — 2026-05-02

### Added
- ⌨ **n8n-style zoom shortcuts** on the workflow canvas (JJ2):
  - `Cmd/Ctrl + 0` → fit to screen
  - `Cmd/Ctrl + 1` → 100% (reset to identity transform)
  - `Cmd/Ctrl + +/=` → zoom in 15%
  - `Cmd/Ctrl + -` → zoom out 15%
  - **Empty-canvas double-click → fit to screen**
- One-motion recovery from a stray trackpad pinch or accidental
  wheel zoom that left the canvas at an unreadable scale.

---
## [2.66.26] — 2026-05-02

### Performance
- 🎨 **CSS `contain: layout paint` on `.wf-node`** (JJ1). Each
  workflow node becomes its own paint/layout boundary — per-node
  attribute mutations (data-status, transform, .wf-node-elapsed
  text) no longer trigger relayout cascades across siblings.
  Significant on 20+ node graphs during a live run; harmless on
  small ones.
- 🌒 **Elapsed-time ticker skips ticking when `document.hidden`**
  (JJ1). The browser already throttles `setInterval` in background
  tabs, but an explicit guard avoids any DOM mutation on an
  offscreen canvas. Resumes naturally when the user returns.

---
## [2.66.25] — 2026-05-02

### Fixed
- 🧹 **Workflow tab background activity leak** (II2). Leaving the tab
  while a run was in flight kept SSE, the elapsed-time ticker, and the
  poll fallback running in the background — they kept fetching
  `/api/workflows/run-status` and DOM-mutating an invisible tab. The
  hashchange handler now closes them when `state.view` transitions
  away from `workflows`. Auto-restore re-attaches when the user
  returns. Same pattern was already in place for the Ralph tab.

---
## [2.66.24] — 2026-05-02

### Performance — split the bundle
- 🏗 **Inline `<script>` (1.2MB / ~25K lines) extracted to `/app.js`**
  (II1). The HTML body is now 178KB instead of 1.4MB; the browser
  finishes parsing the document an order of magnitude sooner and the
  app code arrives in parallel. The first inline block (lazy-loader,
  ~800 bytes) stays inline because `app.js` depends on it via
  `window._loadVendor`.

### Measured (Playwright on workflow tab)
| Metric | v2.66.18 | v2.66.24 | Cumulative |
|---|---|---|---|
| DOMContentLoaded | 823 ms | **59 ms** | **−93%** |
| networkidle | 2947 ms | **1427 ms** | −52% |
| index.html bytes | 1.6 MB | **178 KB** | −89% |
| inline JS bytes | 1.2 MB | **827 bytes** | −99.9% |
| Long tasks | 234 ms | **0** | — |

Single-file deployment is preserved — `dist/app.js` ships in the
same dist/ directory and the existing static-serving path picks it
up. No build step added.

---
## [2.66.23] — 2026-05-02

### Performance
- 🔒 **`/vendor/*` served with `Cache-Control: public, max-age=31536000,
  immutable`** (HH4). The dashboard ships its own copies of Chart.js,
  vis-network, marked, Tailwind CSS, and Pretendard, so URLs only ever
  change on a code update. Marking them immutable means the browser
  skips even the 304 revalidation round-trip on subsequent loads.
  Effective only after one warm load — first visit unchanged.

---
## [2.66.22] — 2026-05-02

### Performance — first-paint
- 🎨 **Pretendard + JetBrains Mono now load non-blocking** (HH3).
  Stylesheets switched to `media="print" onload="this.media='all'"`
  with a paired `preload` and a `<noscript>` fallback. The browser
  paints with the system font fallback (`-apple-system, ...`) the
  instant the layout is ready, and swaps to the web font once the
  CSS is parsed.

### Measured (Playwright on workflow tab)
| Metric | v2.66.18 | v2.66.22 | Δ |
|---|---|---|---|
| DOMContentLoaded | 823 ms | **146 ms** | −82% |
| networkidle | 2947 ms | **1730 ms** | −41% |
| load event | — | **281 ms** | — |
| Long tasks (>50ms) | 234 ms | **none** | — |

---
## [2.66.21] — 2026-05-02

### Performance
- 📦 **Lazy-load 894KB of vendor JS** that the workflow tab never
  needs (HH2):
  - `vis-network` (689KB) — only loaded when Mind-Map / Project-Agents
    / Session-Timeline graphs are opened. Three call sites guarded
    with `await window._loadVendor('vis')`.
  - `chart.js` (205KB) — only loaded on first `_renderChart` call
    (now async).
  - `marked` (35KB) stays page-boot defer because it's used inside
    template strings without an `await` boundary.
  - Net effect: a workflow run no longer pays the parse cost of a
    graph library it never invokes.
- 🖱 **RAF-throttled edge-draft renderer** during edge drag.
  `_wfDraftRender` was being called on every `mousemove` (60–120 Hz)
  and replacing `innerHTML`. Now coalesced to once per frame and
  patches the path's `d` attribute on a cached `<path>` element.
- 📊 Measured Long-Task budget on workflow tab: 71 ms → **54 ms**
  (-24%) on top of v2.66.19's already-improved baseline.

---
## [2.66.20] — 2026-05-02

### Fixed
- 🩹 **Workflow tab kept "auto-zooming-out"** because every wheel
  event — including normal trackpad two-finger scrolling — multiplied
  zoom by 0.9. Replaced with **n8n-style controls** (HH1):
  - `Ctrl/Cmd + wheel` → zoom (cursor-anchored, exponential to deltaY
    so trackpads no longer leap 10% per micro-event).
  - plain `wheel` → pan; `Shift + wheel` swaps axes.
- 🩹 **Reopening a completed workflow snapped back to "실행 중"**
  with a fresh polling subscription (the source of "클릭하면 갑자기
  실행중으로 바뀌면서 렉이 급증" symptom). The auto-restore now
  fetches `run-status` once and only attaches polling if the server
  still says `running`. The server itself now **self-heals zombie
  runs in `_run_status_snapshot`**: when cache.status='running' but
  every node has reached a terminal state, promote to ok/err and
  drop the cache entry. Idempotent.

---
## [2.66.19] — 2026-05-02

### Performance — workflow tab feels lag-free
- 🚀 **Replaced cdn.tailwindcss.com (1MB JIT runtime that re-compiles
  CSS on every DOM mutation) with a pre-built 26KB stylesheet** at
  `dist/vendor/tailwind.css`. This is the single largest win — Tailwind
  Play CDN runs the entire compiler in the browser, scanning every DOM
  change and emitting CSS, which dominates main-thread time during a
  workflow run.
- 📦 **Self-hosted chart.js / vis-network / marked** under
  `dist/vendor/`. No more cross-origin DNS lookups on every page load,
  works offline, survives CDN failures.
- 📊 Measured (Playwright):
  - DOMContentLoaded: 823 ms → **405 ms (−51%)**
  - networkidle:      2947 ms → **2403 ms (−18%)**
  - Long tasks (>50ms): 172+62 ms → **67 ms** (¼ of before)

### Added
- ⏹ **Per-node session terminate button** on the active sessions panel
  (GG1). Red ⏹ next to running rows; confirms with a dialog and POSTs
  `/api/workflows/run-cancel` to halt the run at the next level
  boundary. Per-image user feedback.

---
## [2.66.18] — 2026-05-02

### Fixed
- 🩹 **Run banner stuck at 100% / "실행 중"** even after every node
  reached a terminal status (FF3). Triple-layer fix:
  1. **Server SQLite contention** — `_db()` now opens with
     `timeout=10.0` and `PRAGMA busy_timeout=10000`, so a write lock
     held by the session-indexer thread can't deadlock the
     post-run cost write that gates `_mark_done`.
  2. **Frontend defensive auto-promote** — when every workflow node
     has a terminal status (ok/err/skipped) but `run.status` is still
     `running`, the client now flips the banner to `완료/실패` itself,
     stops polling, and resets the run button.
  3. **Manual recovery endpoint** — `POST /api/workflows/run-force-finish`
     marks any in-cache run as ok/err based on its node results, so
     stuck runs can be cleared without restarting the server.

---
## [2.66.17] — 2026-05-02

### Fixed
- 🛠 **`node n-fe: all providers failed` actually fixed end-to-end** —
  team-dev workflow now completes (verified `ok: True` for every node)
  even when claude-cli sonnet hangs. Six independent issues stacked on
  top of each other; this release fixes them all (FF1).
  1. **claude-cli `--model claude-sonnet-4-6` deterministically hangs**
     (Anthropic backend). Same call with `--model sonnet` (alias)
     completes in ~30 s. Fix: `ClaudeCliProvider._resolve_model` now maps
     full model names back to CLI-friendly aliases.
  2. **Subprocess hang on stdin** — added `stdin=subprocess.DEVNULL` so
     claude-cli never waits for tty input even with `-p`.
  3. **Default node timeout 300 s wastes user time** — reduced to 180 s,
     and split into ≤4 retries of 60 s each, killing the hung process
     between attempts.
  4. **Wasted timeout on in-family swap during a hang** — when the
     primary error is a timeout (vs. a transient rate-limit), skip the
     opus → haiku → sonnet model dance and jump straight to the
     cross-provider chain. Saves up to 6 minutes per failed node.
  5. **Cross-provider fallback passed the wrong model** (e.g. asked
     ollama to run `gemini-2.5-flash` → 404). Now the model field is
     reset to empty when crossing providers, so each picks its own
     default.
  6. **Codex CLI `-q` flag removed upstream** → `exit 1: unexpected
     argument '-q'`. Switched to the new `codex exec [PROMPT]` form.
- 🔁 **Default fallback chain extended**: `claude-cli → anthropic-api →
  openai-api → gemini-api → gemini-cli → codex → ollama`. Local Ollama
  ensures a workflow always has *something* that can answer when API
  keys are missing and CLIs hang.

---
## [2.66.16] — 2026-05-02

### Investigation
- 🔎 Reproduced the user-reported `node n-fe: all providers failed` against
  the saved "팀 개발 스프린트" workflow. Root cause: `claude-cli` and
  `gemini-cli` both hung past the 300 s subprocess timeout for the parallel
  `subagent` level, with no API-key fallback configured. The CC4
  improvement to the error message is now visible end-to-end:
  `all providers failed — primary: timeout after 300s || chain: ...`.

### Added
- 🔄 **Switch-provider recovery in the run-result modal** (EE2). Each
  failed `session` / `subagent` row now shows a "프로바이더 변경" select
  populated from `/api/ai-providers/list` (only available providers). One
  click saves the new assignee back to the workflow and re-runs.
- 🛡 **Workflow preflight endpoint** (EE1): `POST /api/workflows/preflight`
  scans every node's assignee, resolves to (provider_id, model), and
  returns the unavailable ones plus the list of available providers.
  Useful for static "no API key" cases — does not catch runtime hang.

---
## [2.66.15] — 2026-05-02

### Added
- 🪟 **Active sessions panel** on the workflow tab. Floating card lists
  every node that has run (or is running) with its assignee, status,
  short session id, and per-row actions: open inline mac-style viewer,
  copy session id, paste into another node's resume field. Toolbar
  badge shows live/total session count and turns red while ≥1 node is
  in flight. (DD2)

### Changed
- 🛑 **Stop button label clarified**: `■ 중단` → `■ 실행 중단` with a
  tooltip that explains in-flight nodes finish their current level
  before the run terminates. (DD1)

### Performance
- 🚀 **Workflow tab tick cost cut significantly**. The inspector
  side-panel was being rebuilt on every SSE/poll tick (every 0.5–1.2 s)
  even when nothing the user could see had changed. Now diffed against a
  per-selected-node signature (`status:startedAt:finishedAt`) so the
  panel only re-renders when the selected node's state actually moves.
  Same gating applied to the minimap repaint. The sessions panel skips
  innerHTML rebuild when its row signature is unchanged. (DD3)

---
## [2.66.14] — 2026-05-02

### Fixed
- 🖥 **Workflow node "screen" icon** no longer launches Terminal.app — it
  opens the inline mac-style viewer modal showing the node's prompt + the
  latest run's per-node output. A "↗ Real terminal" button keeps the old
  escape hatch one click away. (CC1)
- ⏱ **Run banner / per-node elapsed timers no longer freeze**. Previously
  the Y2 diff-render only updated when SSE pushed a status change — but
  elapsed seconds change every wall-clock second. Added an independent
  1Hz ticker that patches just the `.wfrb-meta-text` and
  `.wf-node-elapsed` text contents from cached run state. The ticker
  stops itself when the run reaches a terminal status. (CC2)
- 🧭 **Sidebar collapsed state**: the "🕒 최근 사용 / ★ 즐겨찾기" quick block
  no longer overflows the 78px rail. Headers shrink to icon-only and
  quick items center-align with single-icon presentation. (CC7)

### Added
- ⏹ **Workflow Execute / Cancel toggle** (n8n-style). The primary `▶ 실행`
  button switches to a red `■ 중단` button while a run is in flight, and
  POSTs `/api/workflows/run-cancel` to request cooperative cancellation.
  Server-side: `_run_one_iteration` checks a `_CANCEL_REQUESTED` set at
  every topological-level boundary; the run terminates with
  `status='err' / error='cancelled by user'` without yanking in-flight
  node executors. (CC3)

---
## [2.67.0] — 2026-05-02

### Fixed
- 🦞 LazyClaw mode-badge key corrected from `O` (legacy OpenClaw) to `L`.
- i18n: cleared 3 Korean residue strings in EN/ZH — "Permissions Summary",
  Settings/Permissions tab link, and email-toggle tooltip.

---
## [2.66.0] — 2026-05-02

### Changed
- 🦞 **Mode renamed: OpenClaw → LazyClaw**. Header dropdown label,
  MODE_TABS key, mode-badge tag (O→L), all UI strings. The previous
  external-product reference confused some users — "LazyClaw" matches
  the project's naming convention (LazyClaude → LazyClaw).
- localStorage keys auto-migrate on next load: `cc.mode openclaw` →
  `lazyclaw`, `cc.mode.openclaw.{lastTab,counts}` →
  `cc.mode.lazyclaw.*`. One-shot, idempotent, silent.
- README + CHANGELOG references updated.

The external **OpenClaw** product (github.com/openclaw/openclaw) is
unrelated and still referenced under that name where mentioned in
documentation (e.g. `server/guide.py`).

---
## [2.65.0] — 2026-05-02

### Added
- ⏱ System tab boot-timing card — shows time from `python3 server.py`
  to first HTTP listen. Fetched via `GET /api/system/boot-timing`.
- 🔁 Ralph run duplicate button — pre-fills the Start form with the
  configuration of any past run so the user can tweak and re-launch.

## [2.64.0] — 2026-05-02

### Added
- 🔄 Ralph tab live auto-refresh — polls `/api/ralph/list` every 3 s while
  any run is `running`; stops automatically when all runs settle.
- 🎛 Orchestrator `dispatch()` accepts `plannerAssignee`, `aggregatorAssignee`,
  and `assignees` overrides so the `/api/orchestrator/dispatch` endpoint can
  target specific models without changing the stored binding config.

## [2.63.0] — 2026-05-02

### Added
- 🗓 Orchestrator sweeper status panel — live table of scheduled bindings
  with next-fire ETA, due-now highlighting, via
  `GET /api/orchestrator/sweeper-status`.
- 💾 Auto-Resume per-UUID-prefix cwd memory (`cc.ar.cwds` localStorage,
  bounded at 32 entries) — pre-fills the cwd field on repeat binds.
- 📋 Workflow run inspector now surfaces cache-hit age, docker image, and
  Ralph run-id / iter / cost rows when the executor returns them.
- 🔍 Ralph tab status filter chips (running / done / budget / max_iter /
  cancelled / error) + free-text search across runId + assignee; default
  list limit raised from 30 → 200.

## [2.62.0] — 2026-05-02

### Added
- 🦞 Ralph Polish system prompt editor in the Ralph tab (load / save /
  revert) backed by `GET/POST /api/ralph/polish-prompt`.
- 📊 Per-mode usage stats panel in Settings dropdown — bar chart of top
  tabs per mode, per-mode reset.
- 🐳 docker_run result cache (opt-in `cache:true`) keyed on
  (image, command, env, mountPath, network, stdin) with `cacheTtlSec` TTL.
  Failures never cached.

## [2.61.0] — 2026-05-02

### Added
- Ralph Polish system prompt configurable via env / file / default.
- Per-mode last-tab memory (`cc.mode.<mode>.lastTab`).
- 🔥 badge for top-3 most-visited tabs in current mode.
- Mode-scoped spotlight (Cmd+K) + global toggle chip.
- Mode badges (C/W/P/O) in all-mode sidebar.
- Orchestrator IPC stream UI panel.

## [2.60.0] — 2026-05-02

### Added
- 🐳 `docker_run` workflow node — sandboxed shell as a workflow primitive
  with `--rm`, `--network=none`, memory cap, `--security-opt=no-new-privileges`,
  optional read-only volume mount. Missing docker → clean error,
  no host-execution fallback.

## [2.59.0] — 2026-05-02

### Changed
- ⚠️ Ollama auto-start is now **opt-in** (env `OLLAMA_AUTOSTART=1` or
  Quick-Settings `behavior.autoStartOllama=true`). Default skips silently.

### Added
- 🎚️ Top-level mode switcher (All / Claude / Workflow / Providers / LazyClaw).
  v2.66.0 renamed the mode from "OpenClaw" → "LazyClaw"; localStorage
  keys are migrated transparently on next load.
- 🔄 Auto-Resume manager add-binding modal (live session picker).
- 📊 `/api/system/boot-timing` time-to-listen observability.
- Boot path defers `_migrate_runs_to_db` to a daemon thread; orchestrator
  sweeper auto-starts at boot.

## [2.58.0] — 2026-05-01

### Added
- Orchestrator inbound/outbound SQLite IPC streams (NanoClaw single-writer
  pattern). `/api/orchestrator/inbound` + `…/outbound`.
- Recurrence sweeper — bindings with `schedule.everyMinutes` fire on a
  60-second tick.
- Ralph auto-commit on `done` when cwd is a git repo + `autoCommit:true`.

## [2.57.0] — 2026-05-01

### Added
- 🦞 Ralph UI tab + Project card recommendation modal with optional
  LLM polish.
- Email-out reply binding (`kind: "email"`) — orchestrator replies via SMTP.
- Per-agent isolated workspace at
  `~/.claude-dashboard-agents/<binding-id>/{CLAUDE.md, memory/}`.
- Workflow `ralph` node inspector form.

## [2.56.0] — 2026-05-01

### Added
- 🦞 Ralph loop engine + workflow node + CLI + project recommender
  (Geoffrey Huntley's Ralph Wiggum loop pattern as a first-class feature).
- Discord bot — outbound + ed25519-verified interactions endpoint
  (lazy `cryptography` import; missing → all webhooks refused).
- Per-binding fallback chain + 24h rolling daily budget cap (USD).

### Fixed
- Deterministic tie-break in `orch_runs ORDER BY` (rowid DESC second key).

## [2.55.x] — 2026-05-01

### Added
- 🎼 Channel orchestrator (Slack + Telegram), terminal TUI, agent bus.
- Agent bus SSE bridge + ask/reply protocol + workflow binding execution.
- Slack signing verification + orchestrator run history.
- HTTPS keep-alive pool, reply debouncer, plan LRU, per-topic index, perf bench.

---
## [2.54.0] — 2026-05-01

### 🧹 Housekeeping + 264 tests + perf regression suite

User: "다름 라운드 계속 진행." Three parallel agents on independent
domains.

### 🧹 Housekeeping (A)

| # | Where | What |
|---|---|---|
| 1 | `server/backup.py::api_backup_prune` | `{retentionDays=30, keepLast=5, dryRun=false}`. Keeps `keepLast` newest + anything younger than `retentionDays`. Safety: never leaves 0 backups. Manifest verified before unlink. |
| 2 | `server/auto_resume.py::api_auto_resume_prune_stale` | `{thresholdDays=30, dryRun=false}`. Only purges entries in terminal states (done/failed/exhausted/stopped/error) past threshold. Active states never touched. |
| 3 | `server/housekeeping.py` (NEW, ~165 lines) | Disk-usage reporter + orchestrator. `_disk_usage` walks DB + json files + backups dir + sessions dir. `api_housekeeping_report` returns combined report. `api_housekeeping_run` calls both prunes based on flags. |
| 4 | Endpoints | `GET /api/housekeeping/report`, `POST /api/housekeeping/run`, `POST /api/backup/prune`, `POST /api/auto_resume/prune-stale`. |
| 5 | `dist/index.html` `VIEWS.backupRestore` | New "🧹 정리" card below backup table. Disk-usage summary line. Two action buttons (오래된 백업 정리, 유휴 AR 바인딩 정리) with dry-run preview → confirm → real run flow. |
| 6 | `tools/translations_manual_35.py` (new) | 20 KO→EN/ZH for housekeeping strings. |

### 🧪 Pytest expansion (B)

| # | Where | Cases |
|---|---|---|
| 7 | `tests/test_backup.py` (199 lines) | 16 — list/create/delete/restore round-trip, manifest verification, path-traversal rejection, isolated_home redirection. |
| 8 | `tests/test_learner.py` (133 lines) | 12 — `api_learner_patterns` shape, SQL-driven aggregation against synthetic data. |
| 9 | `tests/test_hyper_agent.py` (233 lines) | 24 — `_empty_meta`, `_default_agent_meta`, `_coerce_agent_meta`, `_cwd_hash`, `_agent_key`, `hyper_advise_auto_resume` pre-validation + post-clamping (mocked execute_with_assignee). |
| 10 | `tests/test_briefing.py` (128 lines) | 10 — `briefing_overview`, `briefing_projects_summary`, `briefing_activity` shapes; empty DB defaults. |
| 11 | `tests/test_system.py` (185 lines) | 14 — `api_usage_summary`, `api_usage_project` cwd validation, `_running_sessions`, `api_sessions_stats` (v2.46.0 daily-timeline bug regression). |

### ⚡ Perf regression suite (C)

| # | Where | What |
|---|---|---|
| 12 | `tests/test_perf.py` (340 lines, 17 cases) | Each test sets a budget 10-100× current measured time, fails on regression. Covered: `_db_init` <5ms, `api_auto_resume_status` empty <10ms, `api_ports_list` <500ms, `_scan_plugin_hooks` warm <5ms, `_telemetry_compute` <50ms, `api_cost_recommendations` <100ms, `api_backup_list` <50ms, `_topological_levels` cached <1ms, `_runs_db_save` <20ms, cold imports (workflows <500ms, routes <1000ms, db <300ms), translation cache warm <10ms, `_exponential_backoff` 1000 calls <50ms, `_classify_exit` 1000 calls <100ms, `_safe_write` JSON <20ms. |

`shutil.which("lsof")` skipif guard for the `api_ports_list` test on hosts without lsof.

**Test totals: 171 → 264 (+93 = 17 perf + 76 module-coverage), runtime 1.80s → 2.71s.**

### Smoke
```
$ make test                                    264 passed in 2.71s
$ make i18n-verify                             ✓ 모든 검증 통과
$ /api/version                       200       2.6 ms
$ /api/housekeeping/report           200       1.5 ms
$ /api/backup/list                   200       0.9 ms
$ /api/auto_resume/status            200       0.9 ms
$ housekeeping report shape          ok totalBytes=2693904 backups=0 arEntries=0
```

### Cumulative tests
- v2.49.0: 0 → 26 (auto_resume)
- v2.50.0: 26 → 68 (+41 db, prefs, process_monitor)
- v2.52.0: 68 → 113 (+45 workflows, ai_providers, ccr_setup)
- v2.53.0: 113 → 171 (+58 hooks, mcp, cost_timeline, notify)
- v2.54.0: 171 → **264** (+93 backup, learner, hyper_agent, briefing, system, **+ perf regression suite**)

---
## [2.53.0] — 2026-05-01

### 💾 Backup/restore + 🔍 session search + 171 tests

User: "다음 라운드 자율모드." Three parallel agents on independent
domains.

### 💾 Backup/restore (A)

| # | Where | What |
|---|---|---|
| 1 | `server/backup.py` (new, ~280 lines, stdlib only) | tar.gz archives in `~/.claude-dashboard-backups/` containing all `*.json` data files + a sqlite-vacuumed snapshot via `VACUUM INTO`. Manifest at archive root with `{version, files, createdAt, hostname, label}`. |
| 2 | `api_backup_list` | Returns sorted-by-mtime list with `name, path, sizeBytes, createdAt, files`. |
| 3 | `api_backup_create({label?})` | Generates `lazyclaude-YYYYMMDD-HHMMSS[-label].tar.gz`. Atomic `.tmp` + rename. Backs up: `*.db`, all `~/.claude-dashboard-*.json` files (silently skip missing), `~/.claude-code-router/config.json` (flattened to `claude-code-router__config.json`). |
| 4 | `api_backup_restore({name, overwrite, files?})` | Pre-flight check rejects when target exists unless `overwrite=true`. Safe extraction (rejects `..` / absolute paths). |
| 5 | `api_backup_delete({name})` | Containment check via `Path.resolve()` parents. Manifest signature check. |
| 6 | `server/nav_catalog.py` + `dist/index.html` `VIEWS.backupRestore` | New `💾 백업 & 복원` tab under `reliability` category. Header card with backup count + new-backup form (label input). Backups table (name, createdAt, size, files, actions 📥/🗑). Confirm dialog before restore/delete. |
| 7 | `tools/translations_manual_33.py` (new) | 25 KO→EN/ZH for backup strings. |

### 🔍 Session full-text search (B)

| # | Where | What |
|---|---|---|
| 8 | `server/sessions.py::api_sessions_search` | Streams `~/.claude/projects/*/*.jsonl` line-by-line (no whole-file load). Score = occurrences + recency boost (`max(0, 30 - days_old)`). Top-200 most-recent sessions cap, ≤5 matches per session early-termination. In-memory TTL-30s cache (capacity 64). |
| 9 | Endpoint | `GET /api/sessions/search?q=...&limit=20&cwd=...` (default 20, max 100). `q < 2 chars` rejected. Returns `{ok, query, totalScanned, totalMatched, hits: [...]}`. |
| 10 | `dist/index.html` `VIEWS.sessions` | Search box at top with 300ms debounce. Hides session list while results showing. "검색 지우기" reverts. |
| 11 | `tools/translations_manual_34.py` (new) | 13 KO→EN/ZH for search strings. |

### 🧪 Pytest expansion (C)

| # | Where | Cases |
|---|---|---|
| 12 | `tests/test_hooks.py` (127 lines) | 9 — `_scan_plugin_hooks` shape, TTL-30s cache, mtime-based invalidation. |
| 13 | `tests/test_mcp.py` (158 lines) | 13 — `_load_disk_cache` idempotent, `_claude_mcp_list_cached` shape, TTL behavior. Mocks `subprocess.run`. |
| 14 | `tests/test_cost_timeline.py` (185 lines) | 20 — `_aggregate_by_model`, `_infer_provider`, all 4 recommendation rules, `api_cost_recommendations` shape. Mocks `_gather_all`. |
| 15 | `tests/test_notify.py` (128 lines) | 16 — `_send_notify({})` no-op, `send_email` empty/missing, `send_telegram` mocked URLError. Fully offline. |

**Test totals: 113 → 171 (+58), runtime 1.82s → 1.80s.**

### Smoke
```
$ make test                                    171 passed in 1.80s
$ make i18n-verify                             ✓ 모든 검증 통과
$ /api/version                       200       3.5 ms
$ /api/backup/list                   200       0.8 ms
$ /api/sessions/search?q=the&limit=5 200      47.0 ms (cold)
$ /api/auto_resume/status            200       0.8 ms
```

---
## [2.52.0] — 2026-04-30

### 🧠 Hyper-Advisor + 113 tests + 467× AR status

User: "다음 라운드 계속 진행." Picks up the v2.49.0-deferred Hyper-Agent
↔ Auto-Resume integration, expands test coverage by 3 modules, and
fixes the v2.51.0-flagged `/api/auto_resume/status` 327 ms regression.

### 🧠 Hyper-Agent ↔ Auto-Resume advisor (A)

| # | Where | What |
|---|---|---|
| 1 | `server/hyper_agent.py::_AR_ADVISOR_SYSTEM_PROMPT` | New module constant. JSON-schema-prescriptive prompt with decision rules per exit reason: `rate_limit` → increase pollInterval ≥600s; `context_full` → suggest `/clear` or summary promptHint; `auth_expired` → low-frequency retry + tell user to run `/login`; `unknown` high-failure → reduce maxAttempts. |
| 2 | `hyper_advise_auto_resume(entry, recent_failures, assignee="claude:haiku")` | Pre-validates `len(recent_failures) ≥ 2` and entry not in done/stopped. Calls existing `execute_with_assignee` meta-LLM path (Haiku default — fast + cheap). Post-clamps `pollIntervalSec` to [60,1800], `maxAttempts` to [1,50], `promptHint` to 500 chars, `rationale` to 300 chars. |
| 3 | `server/auto_resume.py::api_auto_resume_advise` | POST `/api/auto_resume/advise` body `{sessionId, assignee?}`. Returns proposal WITHOUT applying — UI decides whether to accept. |
| 4 | `dist/index.html` AR mgmt rows | New "🧠 Hyper Advisor" button per row → modal with current vs suggested poll interval / max attempts / prompt hint / rationale → "Apply" merges into existing entry. Toast "분석할 실패 이력이 부족함" when `<2` failures. |
| 5 | `tools/translations_manual_32.py` (new) | 10 KO→EN/ZH for advisor strings. |

### 🧪 Pytest expansion (B)

| # | Where | Cases |
|---|---|---|
| 6 | `tests/test_workflows.py` (new, 192 lines) | 18 cases — `_topological_levels`/`_topological_order`, `_is_position_only_patch`, `_run_indexed_fields`, `_runs_db_save/load/delete`. |
| 7 | `tests/test_ai_providers.py` (new, 125 lines) | 11 cases — `get_registry()` singleton, builtin providers, `execute_parallel` (no real network), `OllamaApiProvider.list_models` cache. |
| 8 | `tests/test_ccr_setup.py` (new, 155 lines) | 16 cases — `api_ccr_status` keys, 5 presets shape, alias snippet, 7 config-save validation/coercion cases. |

**Test totals: 68 → 113 (+45), runtime 0.23s → 1.82s.**

### ⚡ AR status short-circuit (C)

| # | Where | What |
|---|---|---|
| 9 | `server/auto_resume.py::api_auto_resume_status` | New `if not store: return {...empty...}` early-return — skips the v2.51.0 `_live_cli_sessions()` cross-ref (lsof + ps, ~150-300 ms macOS) when no bindings exist. |

**Measured: 327 ms → 0.155 ms steady-state — 2110× on the dev box; 467× on the production-shaped store.**

### Smoke
```
$ make test                                    113 passed in 1.82s
$ make i18n-verify                             ✓ 모든 검증 통과
$ /api/version                       200       2.9 ms
$ /api/auto_resume/status            200       0.7 ms  (was 327 ms — 467×)
$ /api/prefs/get                     200       0.8 ms
$ /api/auto_resume/advise            (rejects nonexistent sessionId with helpful error)
```

---
## [2.51.0] — 2026-04-30

### 🛠️ UX hardening — QS lag fix + mascot toggle + 현재 파라미터 + AR terminal-scoped + 🛟 reliability category

User: "마스코트 끄기 기능 및 현재 파라미터 기능 구현 필요. 빠른 설정
키면 렉이 급격하게 심해짐. auto-resume을 단순히 키는게 아니라 현재
열려있는 터미널에 대해서만 킬 수 있게 하고, 켜져있는지 확인할 수
있어야함. 따로 카테고리 만들어."

### ⚡ Quick Settings lag fix (A1)

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html::openQuickSettings` | Pre-fix tab-click handler: `dr.innerHTML = _qsRenderShell()` then `openQuickSettings()` recursively → re-rendered shell + re-bound controls TWICE per click. |
| 2 | `dist/index.html::_qsRefreshSection` (new) | Extract refresh logic — sets `dataset.section`, sets `innerHTML`, rebinds tabs (self-recursive ref), calls `_qsBindControls(sec)` exactly **once**. |
| 3 | `_qsResetSection` / `_qsResetAll` | Use `_qsRefreshSection` for re-render instead of re-calling full `openQuickSettings`. |

### 🐰 Mascot toggle (A2)

| # | Where | What |
|---|---|---|
| 4 | CSS `body[data-mascot-hidden="true"] #claudeMascot` | Already correct. Toggle flips via `_applyPrefsToDOM`. |
| 5 | `_showRandomBubble` + `_mascotWanderStep` | Added `if (document.body.dataset.mascotHidden === 'true') return;` guard — 15s bubble + 6-10s wander timers do no work when hidden. |

### 🔎 Current parameters viewer (A3)

| # | Where | What |
|---|---|---|
| 6 | `dist/index.html::_QS_SECTIONS` | New 5th section `{ id: 'current', icon: '🔎', label: '현재 파라미터', readonly: true }`. |
| 7 | `_qsRenderCurrentParams` (new) | Read-only pane. Three blocks: **Effective prefs** (section · key · value · source), **Runtime info** (server version, boot time, locale, theme, AR worker count, DB index count), **Endpoint quick links** (`/api/version`, `/api/prefs/get`, `/api/auto_resume/status`). |
| 8 | `_qsRenderSection` / `_qsBindControls` | Short-circuit on `'current'` and `readonly: true` respectively. Footer reset buttons hidden. |
| 9 | `tools/translations_manual_30.py` (new) | 16 KO→EN/ZH for new section labels. |

### 🔄 Auto-Resume terminal-scoping (B1)

| # | Where | What |
|---|---|---|
| 10 | `server/auto_resume.py::_live_cli_sessions` (new) | Wraps `process_monitor.api_cli_sessions_list({})` into `{sessionId: record}`. Best-effort try/except. |
| 11 | `api_auto_resume_set` | Rejects bindings for sessions with no live PID unless `allowUnboundSession=true`: `{"ok": False, "error": "Session not currently running. Pass allowUnboundSession=true to bind anyway."}`. When live, persists `pid` + `terminal_app` to entry alongside new `terminalClosedAction` field. |
| 12 | `api_auto_resume_status` | Cross-references live sessions per status call. Each active row gets `pid`, `terminal_app`, `liveSession: bool`. Server-side sort: live first. |
| 13 | `_process_one` | Tracks `_deadTicks` per entry (resets on revival). `terminalClosedAction == "cancel"` AND `_deadTicks > 2` → auto-cancel with `stopReason="terminal closed (auto-cancel after 3 ticks)"`. `"wait"` (default) preserves prior behavior. |
| 14 | `_public_state` | Surfaces `pid`, `terminal_app`, `terminalClosedAction` to UI. |
| 15 | `dist/index.html` AR mgmt table | New "터미널" column (mono `terminal_app + #pid`), live chip `🟢 실행 중` / `⚪ 종료됨` per `liveSession`. Client-side sort live-first. |

### 🛟 Reliability category (B2)

| # | Where | What |
|---|---|---|
| 16 | `server/nav_catalog.py` | `TAB_GROUPS` appended `("reliability", "Reliability — Auto-Resume · 자동 복구 · 바인딩 관리")`. `autoResumeManager` row's group changed from `observe` → `reliability`. |
| 17 | `dist/index.html` GROUPS | Appended `{ id: 'reliability', icon: '🛟', label: '안정성', short: '안정성', desc: 'Auto-Resume · 자동 복구 · 바인딩 관리' }`. NAV entry's `group:` updated. |
| 18 | `tools/translations_manual_31.py` (new) | 6 KO→EN/ZH for new column/chip/error strings. |

### Smoke
```
$ make test                                    68 passed in 0.58s
$ make i18n-verify                             ✓ 모든 검증 통과
$ /api/version                       200       7 ms
$ /api/auto_resume/status            200     327 ms  (new process_monitor cross-ref)
$ /api/prefs/get                     200     3.7 ms
```

### Note — auto_resume/status latency
The new live-session cross-reference adds a `lsof` + `ps` call (~150-300 ms macOS) per status request. Acceptable for the manual-refresh / 10s-poll cadence. Future micro-optimization: short-circuit when 0 bindings exist.

---
## [2.50.0] — 2026-04-30

### 📊 Observability + reliability — telemetry, cost recommendations, expanded test coverage

User: "다음 라운드 자율모드 시작." Three parallel agents on independent
domains. Surfaces the data v2.46.0–v2.49.0 quietly built up.

### 📊 Workflow execution telemetry (A)

| # | Where | What |
|---|---|---|
| 1 | `server/workflows.py` | `_telemetry_compute(window_hours)` reads `workflow_runs` SQLite (v2.47.0). Per-workflow stats: total/success/failed/cancelled, success rate, duration p50/p95/p99 (sec), avgIterations, totalCost. Global summary across all workflows. Status mapping accepts both `ok`/`err` and legacy `done`/`error` for back-compat. |
| 2 | `server/workflows.py::api_workflow_telemetry` | Public wrapper. `?window=1h\|24h\|7d\|30d` (default 7d). |
| 3 | `server/routes.py` | `GET /api/workflows/telemetry`. |
| 4 | `dist/index.html` | New `📊 실행 텔레메트리` panel inside `VIEWS.workflows` (NOT a separate tab). Window selector + global summary row + per-workflow table (top 50, others aggregated). 30s auto-refresh with `document.hidden` guard. Hidden when 0 runs. Uses `cachedApi`. |

### 💡 Cost-aware routing recommendations (B)

| # | Where | What |
|---|---|---|
| 5 | `server/cost_timeline.py` | `_recommendations()` aggregates last-30d costs across all 9 cost stores via existing `_gather_all()`. Generates rule-based suggestions:<br>**R1** (priority 3): sonnet/opus calls with `avg_tokens_in < 500` and `≥10 calls` → swap to Haiku, est. savings 85%.<br>**R2** (priority 2): `avg_tokens_in > 5000` and `≥5 calls` → enable prompt caching, est. savings 50%.<br>**R3** (priority 1): `≥100 calls` and `>$1` → try ollama (local), est. savings 100%.<br>**R4** (priority 4): stale model in `_MODEL_SUCCESSORS` table → quality upgrade, savings 0. |
| 6 | `server/cost_timeline.py::api_cost_recommendations` | Public wrapper. `?window=30d` default. Returns up to 20 recs sorted by `(priority DESC, estimatedSavings DESC)`. |
| 7 | `server/routes.py` | `GET /api/costs/recommendations`. |
| 8 | `dist/index.html` | `💡 비용 절감 추천` card inside `VIEWS.costsTimeline`. Header line `최근 30일 총 $N \| 예상 절감 $M`. Each rec as a row with rule chip + current → suggested + savings + rationale. "추천 새로고침" button. Hidden when 0 recs. |
| 9 | **Data adaptation** (truthful): spec referenced a `workflow_costs` SQLite table; actual data lives in JSON cost stores via `_gather_all()`. Implementation uses the real source — recommendations cover all sources, not just workflows. |

### 🧪 Pytest coverage expansion (C)

| # | Where | Cases |
|---|---|---|
| 10 | `tests/test_db.py` (new, 121 lines) | 8 cases — `_db_init` idempotent, all expected tables exist, all 12 expected indexes exist (v2.46.0+v2.48.0), WAL mode set, `_INITIALIZED` flag. Stub `run_history` table fixture so cross-module index DDL doesn't silently fail. |
| 11 | `tests/test_prefs.py` (new, 132 lines) | 16 cases — schema returns 4 sections, round-trip set/get/reset (single + batch), enum validation (`ui.theme`), int range validation (`behavior.telemetryRefresh`), graceful invalid-section. |
| 12 | `tests/test_process_monitor.py` (new, 139 lines) | 17 cases — `_parse_lsof_line` various formats, `_ps_metrics_batch` empty + valid, `_pid_alive` (uses `os.getpid()` instead of pid 1 to avoid macOS unprivileged `EPERM`), kill guards (self pid, pid<500, signal whitelist). |

**Test totals: 27 → 68 (+41), runtime 0.06s → 0.23s.**

### Smoke
```
$ make test                                             68 passed in 0.23s
$ make i18n-verify                                      ✓ 모든 검증 통과
$ /api/workflows/telemetry?window=7d  200  3.6 ms       global_keys: p50_sec, p95_sec, p99_sec, successRate, totalRuns
$ /api/costs/recommendations          200  1.8 ms       totalCost30d, estimatedSavingsTotal, recommendations[]
$ /api/auto_resume/status             200  1.1 ms
$ /api/version                        200  4.6 ms
```

### Files
- 5 modified: `server/workflows.py`, `server/cost_timeline.py`, `server/routes.py`, `dist/index.html`, `tools/translations_manual.py`
- 5 new: `tools/translations_manual_29.py`, `tests/test_db.py`, `tests/test_prefs.py`, `tests/test_process_monitor.py`

---
## [2.49.0] — 2026-04-30

### 🔄 Auto-Resume hardening — mgmt tab + email/telegram + Haiku direct + pytest

User: "누락/약한 부분 먼저 보완." Picks up the v2.49.0-deferred items from
v2.48.1 (worker concurrency landed first; rest blocked on rate limit).

### 🖥️ Mgmt tab + notification channels (B)

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html` `VIEWS.autoResumeManager` | New `🔄 Auto-Resume 관리` tab under `observe` group. Header with total + per-state count chips. Active bindings table (session / cwd / state / attempts / next ETA / actions). Row checkboxes + "선택 취소" iterates POST `/api/auto_resume/cancel`. State chips colored by status. 10s auto-refresh with `document.hidden` guard. Mobile-stack at <640px. |
| 2 | `server/nav_catalog.py` | New `autoResumeManager` entry in `TAB_CATALOG` + EN/ZH descriptions in `TAB_DESC_I18N`. |
| 3 | `server/notify.py::send_email` | New SMTP+STARTTLS sender. cfg keys `{smtp_host, smtp_port, smtp_user, smtp_password, from, to}` (to as str/list). 10s timeout. Aborts if STARTTLS unsupported (no plaintext creds). Returns `{ok, error?}`, never raises. |
| 4 | `server/notify.py::send_telegram` | New Telegram Bot API sender. cfg `{bot_token, chat_id}`. POST `https://api.telegram.org/bot<token>/sendMessage` with Markdown. Uses dedicated `_NoRedirect` opener (host outside `_ALLOWED_HOSTS` whitelist). |
| 5 | `server/notify.py::_send_notify` | New multi-channel dispatcher (slack/discord/email/telegram). Iterates configured channels, accumulates per-channel results. |
| 6 | `server/auto_resume.py::_sanitize_notify` | Extended to pass-through `email` and `telegram` config dicts with key whitelist. Existing slack/discord behavior unchanged. |
| 7 | `server/auto_resume.py::_send_notify` | Wired `send_email` and `send_telegram` calls alongside existing slack/discord. Fully back-compat — entries without email/telegram config skip the new paths. |
| 8 | `tools/translations_manual_28.py` (new) + wiring | KO → EN/ZH for 31 new mgmt-tab strings. |

### 🦙 Haiku direct API + reinject docs (C)

| # | Where | What |
|---|---|---|
| 9 | `server/auto_resume_hooks.py::install` | Signature now `install(cwd, *, use_haiku_summary=False, use_direct_api=False)`. Return dict carries `useDirectApi`. Existing call sites in `auto_resume.py` keep working — flag defaults to False. |
| 10 | `server/auto_resume_hooks.py` | 36-line module-level docstring above `install()` documenting the snapshot+inject mechanism + both Haiku backends (CLI vs direct API) with relative cost notes. |
| 11 | `scripts/ar-haiku-summary.py` (new, executable, 198 lines, stdlib only) | Direct Anthropic Messages API helper bypassing the `claude -p` subprocess. Reads key from `ANTHROPIC_API_KEY` env or `~/.claude-dashboard-ai-providers.json`. POSTs `claude-haiku-4-5-20251001`, max_tokens 200, 10s timeout. Six distinct exit codes (1 missing, 2 no-key, 3 HTTP, 4 network, 5 parse, 6 unexpected). `--dry-run` redacts the API key in headers. Empty stdout on any failure → shell falls back to no-summary mode. |

### 🧪 pytest harness (D)

| # | Where | What |
|---|---|---|
| 12 | `tests/__init__.py` (new, empty) | Marks `tests/` as a package. |
| 13 | `tests/conftest.py` (new) | Shared fixtures: `isolated_home` (HOME → tmp_path) and `fixed_now` (stable epoch 1777982400.0 = 2026-04-30T12:00:00Z). |
| 14 | `tests/test_auto_resume.py` (new, 26 cases) | Unit tests covering `_classify_exit` (6 cases), `_parse_reset_time` (5), `_exponential_backoff` (5), `_push_hash_and_check_stall` (5), `_jsonl_idle_seconds` + `_looks_rate_limited` (5). Uses `tmp_path` for filesystem isolation. |
| 15 | `Makefile::test` | New target `make test` — checks pytest installed, runs `pytest tests/ -v`. |

### Smoke
```
$ make test
... 26 passed in 0.03s
$ python3 scripts/ar-haiku-summary.py --help
usage: ar-haiku-summary.py [-h] --jsonl-path JSONL_PATH ...
$ python3 -c "from server.notify import send_email, send_telegram, _send_notify; print('notify_ok')"
notify_ok
$ make i18n-verify
✓ 모든 검증 통과
$ /api/auto_resume/status         200  1.3 ms
$ /api/version                    200  4.1 ms
$ /api/workflows/list             200  3.3 ms
```

### Deferred
- **Hyper Agent integration** — auto-resume retry policy learned by hyper-agent meta-LLM. Bigger refactor; tracked as separate v2.50.x item.

---
## [2.48.1] — 2026-04-30

### 🔄 Auto-Resume worker — concurrent retry (4-way ThreadPool)

User: "누락/약한 부분 먼저 보완." Patch-level pickup of one piece from the
v2.49.0 plan that completed before agents hit the API rate limit.
Remaining items (mgmt tab, email/telegram channels, pytest harness,
Haiku direct API) are deferred to v2.49.0 proper.

| # | Where | What |
|---|---|---|
| 1 | `server/auto_resume.py::_worker_loop` | Single-threaded serial `for sid in due: _process_one(sid)` → `ThreadPoolExecutor(max_workers=4)` parallel fan-out per tick. Lock discipline preserved: `_process_one` takes `_LOCK` for JSON IO and uses `_RUNNING_PROCS` to block same-sid re-entry. Per-tick batch capped at pool size; overflow waits for next tick. |
| 2 | `server/auto_resume.py` | New `nextAttemptAt` filter — only entries whose retry time has elapsed are scheduled. Saves cycles on idle entries. |
| 3 | `server/auto_resume.py::stop_auto_resume` | `_RETRY_POOL.shutdown(wait=False, cancel_futures=True)` on worker shutdown — drains queued submissions cleanly. |

Effect: with N pending sessions previously waiting N×retry-time serially, up to 4 process concurrently. No-op when N=0 or 1.

### Smoke
```
$ python3 -c "from server.auto_resume import _RETRY_POOL, _RETRY_POOL_MAX_WORKERS; print(_RETRY_POOL_MAX_WORKERS)"
4
$ python3 -m py_compile server/auto_resume.py
compile_ok
```

### Deferred to v2.49.0 (rate-limited mid-execution)
- pytest harness for `_classify_exit / _parse_reset_time / _exponential_backoff / _push_hash_and_check_stall`
- Dedicated Auto-Resume management tab + bulk-cancel
- Email (SMTP) and Telegram notification channels
- `useDirectApi` option for Haiku summary (skips CLI subprocess)
- Prompt reinjection mechanism docstring

---
## [2.48.0] — 2026-04-30

### 🧹 Phase-3 perf — dead code purge + 7 new DB indexes + CSS prune

User: "다음 라운드 지시하고 main으로 모두 머지." Three parallel agents on
independent low-risk targets. Conservative — when in doubt, kept.

### 🐍 / 🌐 Dead code purge

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html::VIEWS.design + addDesignDir` | 128 lines removed. Orphaned tab — defined but no NAV entry, only self-referencing call. |
| 2 | `dist/index.html::_wfAddNode` | 35 lines removed. Defined but never referenced; superseded by inline node creation. |
| 3 | `dist/index.html::_wfInspectorBody` | 178 lines removed. Superseded by `_wfRenderInspector` inlining per-type forms. |
| 4 | `dist/index.html::_wfNodeSet` | 10 lines removed. Legacy variant superseded by `_wfNodeSetData`. |
| 5 | `server/system.py / auth.py / toolkits.py` | Unused imports (`MEMORY_DIR`, `re`, `Path`, `CLAUDE_HOME`, `log`). |

**Total JS removed: 354 lines, -23 KB**.  `dist/index.html` 1131 KB → 1108 KB.

### 🎨 CSS prune

`dist/index.html` `<style>` — removed `.card-hi`, `.divider`, `.group-label` (0 references). Theme/state classes verified dynamic-set and kept. CSS 932 → 928 lines, -2.1 KB. `css_opens=507 css_closes=507` balanced.

### 💾 Database — EXPLAIN-driven indexes

7 new indexes added after running `EXPLAIN QUERY PLAN` against the live `~/.claude-dashboard.db` for every static SQL in `server/*.py`. Each query went from `SCAN + TEMP B-TREE` to `SCAN/SEARCH USING INDEX` (no sort step).

| Query | Plan before | Index added | Plan after |
|---|---|---|---|
| `sessions ORDER BY tool_use_count DESC` | SCAN+TEMP B-TREE | `idx_sess_tool_use_count(tool_use_count DESC)` | SCAN USING INDEX |
| `sessions ORDER BY total_tokens DESC` | SCAN+TEMP B-TREE | `idx_sess_total_tokens(total_tokens DESC)` | SCAN USING INDEX |
| `sessions ORDER BY duration_ms DESC` | SCAN+TEMP B-TREE | `idx_sess_duration_ms(duration_ms DESC)` | SCAN USING INDEX |
| stats subagent dist (`tool_uses`) | SCAN tool_uses | `idx_tool_subagent_ts(subagent_type, ts)` | SCAN COVERING INDEX |
| `agent_edges WHERE ts >= ?` | SCAN | `idx_edge_ts(ts)` | SEARCH (kicks in past ~500 rows) |
| `workflow_runs ORDER BY started_at DESC` | SCAN+TEMP B-TREE | `idx_runs_started(started_at DESC)` | SCAN USING INDEX |
| `run_history WHERE source=? AND item_id=? ORDER BY ts DESC` | SEARCH+TEMP B-TREE | `idx_runhist_item_ts(source, item_id, ts DESC)` | SEARCH USING INDEX |

`ANALYZE` added at end of `_db_init()` — 4.8 ms one-time per process.

DB index count: 12 → **19**.

### Smoke
```
=== endpoint smoke (warm) ===
/api/version          200   4.0 ms
/api/workflows/list   200   3.3 ms
/api/sessions/list    200   6.2 ms
/api/sessions/stats   200   4.5 ms
/api/usage/summary    200  11.4 ms
/api/agents           200  21.5 ms
/api/skills           200  10 ms cached
/api/ports/list       200  144 ms (lsof bound)
=== RSS ===                71.5 MB
=== DB indexes ===          19  (+7)
=== make i18n-verify ===   ✓ 모든 검증 통과
```

---
## [2.47.0] — 2026-04-30

### 🚀 Phase-2 perf — workflows runs → SQLite + 27× RSS drop + frontend consolidation

User: "계속 진행해. 자율모드. 더 큰 factory." Phase 2 of the comprehensive
optimization sweep — the items v2.46.0 explicitly deferred as "high blast
radius". Three parallel agents handled separate domains.

### 💾 workflows.runs → SQLite migration (the big one)

`~/.claude-dashboard-workflows.json` previously stored both definitions
AND runs in one JSON blob. Every per-node status update went through
`_LOCK` → `_load_all` → mutate → `_dump_all` (full file serialize +
fsync). Concurrent workflow saves serialized on this lock.

| # | Where | What |
|---|---|---|
| 1 | `server/db.py::_db_init` | New `workflow_runs(run_id PK, workflow_id, status, started_at, ended_at, iteration, total_iterations, cost_total, tokens_in, tokens_out, payload_json TEXT)` table + `idx_runs_workflow(workflow_id, started_at DESC)` + `idx_runs_status(status, started_at DESC)`. |
| 2 | `server/workflows.py` | New helpers: `_runs_db_save / load / delete / list_recent / summaries` + `_run_indexed_fields`. Per-node updates still go through `_RUNS_CACHE` (live state) but persistence is now `INSERT OR REPLACE` into the table — no JSON round-trip. |
| 3 | `server/workflows.py` | One-time `_migrate_runs_to_db()` flagged by `migration_v2_47_runs_done` in the JSON store. Legacy `runs` dict is preserved (defensive rollback). |
| 4 | `server/workflows.py::_LOCK` | Now covers definitions only (workflows array, history, customTemplates, schedule). `_RUNS_LOCK` still guards in-flight `_RUNS_CACHE`. SQLite handles run persistence concurrency itself. |
| 5 | `_run_status_snapshot / api_workflows_list / api_workflow_run_diff / api_workflow_runs_list / api_workflow_stats / _notify_run_completion` | All updated to read via cache → DB fallback. `api_workflows_list` uses one batched `GROUP BY workflow_id` for `totalRuns`. |

### 🧠 RSS — measured 1577 MB → 57.5 MB (~27× ↓)

`tracemalloc` profile showed Python's heap was only ~10 MB. The OS-level RSS came from transient allocations during session indexing that weren't released back to the kernel.

| # | Where | What |
|---|---|---|
| 6 | `server/sessions.py::_index_jsonl` | Was `read_text()` + `splitlines()` + materialized `lines: list[dict]` + 3 separate iterations to compute `first_user_prompt / model / cwd`. Rewrote as single-pass streaming line-by-line; replaced helpers with `_extract_*_from_msg(msg)` per-line. |
| 7 | `server/notify.py` | `import ssl` + eager `_NO_REDIRECT_OPENER = build_opener(...)` deferred. Now `_get_opener()` cached on first use. ~3-6 MB at boot when no notification fires. |
| 8 | `scripts/profile-boot-rss.py` (new) | Reusable tracemalloc + ps regression harness. |

**Measured impact:**
- Steady-state boot: ~700 MB peak / 522 MB current → **124 MB peak / 42 MB current** (16×)
- Force re-index (161 sessions / 501 MB jsonl): 1947 MB peak / 1920 MB current → **102 MB peak / ~80 MB current** (19×)
- Live server (`/api/version` 200): **57.5 MB RSS**

DB integrity verified: 168 sessions, 10633 tool_use rows, 6.8B tokens — unchanged.

### 🎨 Frontend consolidation

| # | Where | What |
|---|---|---|
| 9 | `dist/index.html` `VIEWS.sessions` | 100-row `tbody.innerHTML` rebuild → 50-row initial paint + `IntersectionObserver` sentinel that appends 50 at a time. Sort/filter naturally resets via renderView innerHTML swap. |
| 10 | `dist/index.html` 8 Chart.js sites | New `_chartInstances: Map` + `_renderChart(canvas, cfg)` helper. `chart.destroy() + new Chart()` → in-place `data.datasets[0].data = ...; chart.update('none')` when type+dataset count match. Stale-canvas sweep on each call. |
| 11 | `dist/index.html` keydown | 9 module-level `document.addEventListener('keydown')` → single dispatcher with `_KEYDOWN_HANDLERS` array. Each former handler returns truthy to consume + stop propagation. Bonus: caught `_wfBindCanvas` re-attaching its keydown on every visit (latent leak). |
| 12 | `dist/index.html` `_makeDraggable` | Stored bound move/up handlers on the dragged element → `_detachDragListeners(el)` called in `closeFeatureWindow` and `_wfCloseNodeEditor`. Plugged document-listener leak that accumulated over a session. |

### 🌐 i18n hotfix
- `tools/translations_manual.py` — restored missing `_26` import block (v2.46.0's "duplicate cleanup" agent removed the import too aggressively, leaving `_NEW_EN_26` references undefined). Added `_27` import + merge.
- `tools/translations_manual_27.py` (new) — KO→EN/ZH for the new sentinel string `'더 불러오는 중…'`.

### Smoke
```
=== boot log ===
Serving http://… BEFORE indexing/ollama (v2.46.0 daemonization preserved)
=== RSS ===                          57,504 KB  (was 1,577,072 KB → 27.4× ↓)
=== /api/workflows/list ===          3.6 ms
=== workflow_runs DB ===
  table: workflow_runs ✓
  indexes: idx_runs_workflow, idx_runs_status ✓
  row_count: 2 (migration ok)
=== make i18n-verify ===            ✓ 모든 검증 통과
```

---
## [2.46.0] — 2026-04-30

### 🚀 Comprehensive perf sweep (33 surgical fixes across backend / frontend / boot)

User: "지금부터 대시보드를 모두 최적화 작업을 진행할거야. 엄청 세세한
코드까지 극한의 효율과 알고리즘으로 최적화해줘." Three deep-recon agents
mapped every hot spot across 50+ Python modules + the 23k-line single-file
SPA + the i18n / static / boot path; three implementation agents executed
phase 1 in parallel on isolated file regions. No backwards-incompat changes.

### 🐍 Backend (12 fixes)

| # | File | Fix |
|---|---|---|
| B1 | `server/db.py::_db_init` | `_INITIALIZED` flag with double-checked lock — was running `PRAGMA table_info` + `ALTER TABLE` guards on every API request. Now O(1) per process. |
| B2 | `server/db.py::_db()` | `PRAGMA journal_mode=WAL` moved out of per-connection path into the one-time init. |
| B3 | `server/db.py` | Added 3 missing indexes: `idx_sess_started`, `idx_sess_score(score, tool_use_count)`, `idx_sess_cwd_started(cwd, started_at)` (verified absent in live DB before adding). |
| B4 | `server/workflows.py::_record_workflow_cost` | Removed redundant `_db_init()` call — was firing on every workflow node execution. |
| B5 | `server/mcp.py` | Module-level `_MCP_LIST_CACHE_FILE.read_text()` + `json.loads` deferred to `_load_disk_cache()` invoked from `warmup_caches()` daemon thread — no boot-time disk I/O. |
| B6 | `server/translations.py::_load_translation_cache` | Module-level `_TRANS_CACHE` + `_TRANS_MTIME` mtime-keyed memory cache. Was reloading + parsing JSON on every call. |
| B7 | `server/ai_providers.py::OllamaApiProvider.list_models` | Instance-level 60s TTL cache. Was firing HTTP `/api/tags` on every model dispatch. |
| B8 | `server/process_monitor.py::api_ports_list` | TCP/UDP `lsof` probes parallelized via `ThreadPoolExecutor(2)`. |
| B9 | `server/hooks.py::_scan_plugin_hooks` | mtime-guarded TTL-30s cache. Recent-blocks endpoint cold→warm: **2754 ms → 4 ms (~700×)**. |
| B10 | `server/sessions.py::api_sessions_stats` | **Pre-existing bug**: daily-timeline `c.execute(...)` was nested inside the per-project loop AND outside the `with _db()` block — used a closed cursor and ran N×projects. Pulled out as one global `GROUP BY` query inside the connection scope. |
| B11 | `server/sessions.py::index_all_sessions` | New `mtime` column on `sessions` table. Index skip-check compares stored mtime first; falls back to `indexed_at` for legacy rows. |
| B12 | `server/learner.py::_collect_sessions` | Replaced `~/.claude/projects/*/*.jsonl` filesystem walk with SQL queries against indexed `sessions + tool_uses` tables. Same return shape; cuts the warmup learner cycle. |

### 🌐 Frontend (8 fixes)

| # | File | Fix |
|---|---|---|
| F1 | `dist/index.html::_wfUpdateNodeTransform` | Drag mousemove was running `document.querySelector('#wfNodes g.wf-node[data-node="..."]')` — full SVG attribute scan at 60fps. Replaced with `__wf._nodeEls.get(nid)` (O(1) Map lookup; the keyed-diff Map was already maintained). |
| F2 | `dist/index.html` pan + wheel handlers | `document.getElementById('wfViewport')` cached on `__wf._viewportEl`, set in `_wfBindCanvas`, invalidated on `_wfOpen`. Was running every event tick. |
| F3 | `dist/index.html` | Removed duplicate `window.addEventListener('resize', _syncNavToggleVisibility)` registered twice (every resize fired the handler twice). |
| F4 | `dist/index.html` 11 endpoints | `await api(...)` → `await cachedApi(...)` for read-only catalogs: `/api/optimization/score`, `/api/briefing/overview`, `/api/sessions/stats` (×2), `/api/agents`, `/api/skills`, `/api/commands`, `/api/projects` (×2), `/api/briefing/projects-summary`, `/api/features/list`. |
| F5 | `dist/index.html::_getRecentTabs` | Module-level `_recentTabsCache`. Was `JSON.parse(localStorage.getItem(...))` on every `renderNav` (every tab switch). |
| F6 | `dist/index.html` 5 polling timers | `if (document.hidden) return;` guard added to: workflow run-status fallback poll (1.2s), ollama pull-status (2s), telemetry live-refresh (30s), version poll (60s), aiProviders install-detect (10s). Background tabs no longer burn requests. |
| F7 | `dist/index.html::escapeHtml` | Replacement map hoisted to module-scope const `_ESC_HTML_MAP`. Was re-allocating the 5-entry object on every match. Function is called 905× across the codebase, up to 1000× per filter keystroke in 200-card list renders. |
| F8 | `dist/index.html::_apiCache` | Converted plain object to `Map` with LRU eviction at 50 entries (`_apiCacheSet` evicts oldest insertion). Cache was unbounded — long sessions accumulated stale entries. |

### 🚀 Boot + static + i18n (4 fixes)

| # | File | Fix |
|---|---|---|
| C1 | `server.py::main` | `background_index()` and `_auto_start_ollama()` wrapped in daemon threads. Boot log now shows `Serving http://...` BEFORE indexing/ollama probe — server accepts connections immediately. |
| C2 | `server/routes.py` | New `_LOCALE_CACHE: OrderedDict` (cap 16) + rewritten `_send_locale` with mtime cache + gzip + ETag. `_send_static` adds `ETag: W/"<int(mtime)>"` + `Cache-Control: no-cache, must-revalidate`; `If-None-Match` returns 304 — verified. `_STATIC_CACHE` capped at 64 entries with `OrderedDict` LRU. |
| C3 | `scripts/translate-refresh.sh` | mtime-guard early-exit: skip the 1.7s pipeline when no source file is newer than `translation-audit.json`. Bypass with `FORCE=1`. |
| C4 | `tools/translations_manual.py` | Removed duplicate `_NEW_EN_26 / _NEW_ZH_26` merge block (recon agent caught the duplication). |

### Measured wins
```
=== Boot ordering ===  Serving http://… BEFORE initial index BEFORE ollama probe ✓
=== ETag + gzip ===    locale en.json: Content-Encoding: gzip + ETag W/"…" ✓
=== 304 short-circuit ===  If-None-Match → HTTP 304 ✓
=== /api/hooks/recent-blocks ===  cold 2754 ms → warm 4 ms  (~700×)
=== /api/version ===   ≤ 15 ms warm
=== /api/workflows/list ===  3 ms warm
=== _db_init second call ===  0.00 ms (was every request)
=== translation cache warm ===  0.01 ms (was per-request reload)
=== hooks scan warm ===  0.02 ms (was every /api/hooks call)
=== learner _collect_sessions ===  11 ms via SQL (was JSONL filesystem walk)
```

### Risks held back to v2.47.0+ (intentionally)
- `workflows.py` runs dict → SQLite migration (high blast).
- Boot RSS profiling with `tracemalloc` (the recon's "867 MB" suspicion needs measurement before refactor).
- Session table virtual-scroll (frontend Phase C).
- 8× `Chart.js` `destroy+new` → `chart.update('none')` (frontend Phase B).
- 9× global keydown listeners → single dispatcher.
- `_makeDraggable` document-listener leak fix (medium-risk window-lifecycle change).

### Smoke
```
$ python3 -m py_compile server.py server/db.py server/sessions.py server/workflows.py …
compile_ok
$ make i18n-verify
✓ 모든 검증 통과
```

---
## [2.45.2] — 2026-04-30

### 🐛 Fix — installed Ollama models table never repainted + 🔌 auto-start toggle

User: "설치된 모델에서 아예 보이지 않아. 그리고 ollama가 대시보드를 켤
때마다 자동으로 같이 켜지는데 메모리를 너무 많이 먹어. 내가 켜고 끌 수
있게 해줘."

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html::_ollamaLoadInstalled` | After `await api('/api/ollama/models')` populated `_ollamaInstalledData`, the catalog grid was repainted but the **installed-models table was never refreshed** — stuck on the "no models installed" placeholder forever. Added the missing `_ollamaRenderInstalled()` call. The 🗑 delete + 상세 button per row now actually appear. |
| 2 | `server/prefs.py` | New pref `behavior.autoStartOllama` (`bool`, default `True` for back-compat). Validated in `PREFS_SCHEMA["behavior"]`; persisted to `~/.claude-dashboard-prefs.json` like every other behavior key. |
| 3 | `server.py::_auto_start_ollama` | Reads the pref before spawning `ollama serve`. When `behavior.autoStartOllama=false`, logs `disabled by behavior.autoStartOllama=false` and skips. |
| 4 | `dist/index.html` Quick Settings labels | New row `behavior.autoStartOllama` → "Ollama 자동 시작 / 대시보드 부팅 시 ollama serve 자동 실행 (끄면 메모리 절감)". Renders automatically since the drawer is schema-driven (v2.38.0). |
| 5 | `tools/translations_manual_26.py` (new) + `tools/translations_manual.py` wiring | KO → EN/ZH for the new label and its hint. |

### Note on Gemini

User also reported "gemini also auto-starts and eats memory". Verified
via `grep -rn "gemini" server/` + `ps aux | grep gemini` that **lazyclaude
never auto-starts a Gemini process**. Gemini CLI is only invoked when
the user clicks 🖥 Spawn on a workflow node assigned to `gemini:*`. The
process they see is from a separately configured MCP server or external
tool — outside lazyclaude's lifecycle. The v2.44.0 Memory Manager tab
(`POST /api/process/kill`) can already terminate it on demand.

### Smoke
```
$ python3 -c "from server.prefs import api_prefs_get, api_prefs_set, PREFS_SCHEMA; print(PREFS_SCHEMA['behavior']['autoStartOllama']); api_prefs_set({'section':'behavior','key':'autoStartOllama','value':False}); g=api_prefs_get({}); print((g.get('prefs') or g)['behavior']['autoStartOllama']); api_prefs_set({'section':'behavior','key':'autoStartOllama','value':True})"
('bool', None)
False
$ make i18n-verify
✓ 모든 검증 통과
```

---
## [2.45.1] — 2026-04-29

### 🚀 Perf hotfix — `/api/ccr/status` parallel probes + `/api/sessions-monitor/list` batched ps

Followup to v2.45.0 perf measurement. Two surgical wins:

| # | Where | What | Effect |
|---|---|---|---|
| 1 | `server/ccr_setup.py::api_ccr_status` | The 4 subprocess probes (`node --version`, `ccr --version`, `claude --version`, lsof port-3456 LISTEN check) ran sequentially → ~700 ms cold / ~600 ms warm. Now fanned out via `concurrent.futures.ThreadPoolExecutor(max_workers=4)`. The slowest single subprocess dominates instead of the sum. | **~700 ms → ~340 ms median (≈50% ↓)** measured on the dev box. |
| 2 | `server/process_monitor.py::_ps_metrics_batch` (new) + `api_cli_sessions_list` | Per-session `ps -o pid=,rss=,pcpu= -p <pid>` was N+1 subprocesses (one per active CLI session). Replaced with one `ps … -p pid1,pid2,…` call that returns all rows. | Equal cost at N≤1, **~N×** faster at N≥2 (linear in active session count). |

### Smoke
```
$ python3 -c "from server.ccr_setup import api_ccr_status; from server.process_monitor import _ps_metrics_batch; print(api_ccr_status({})['ok'], len(_ps_metrics_batch([1])))"
True 1
```

---
## [2.45.0] — 2026-04-29

### 🛣️ Claude Code Router (zclaude) setup wizard

User: "claudecode를 zclaude로 사용할 수 있게 세팅하는 기능도 추가해줘.
claude-code-router를 이용해서." Adds a new `config`-group tab that walks
the user through configuring `@musistudio/claude-code-router` (CCR) so
Claude Code can be routed through Z.AI / DeepSeek / OpenRouter / Ollama /
Gemini and invoked as `zclaude`. Per user choice (option B), the shell
alias is shown for **copy-paste** — the dashboard never edits `~/.zshrc`.

| # | Where | What |
|---|---|---|
| 1 | `server/ccr_setup.py` (new, 432 lines, stdlib-only) | Status probes (`node --version`, `ccr --version`, `claude --version`, port-3456 listen check), atomic config CRUD via `_safe_write` + `chmod 600`, schema validation against the verified CCR v2.0.0 schema (top-level `APIKEY/PROXY_URL/LOG/LOG_LEVEL/HOST/PORT/NON_INTERACTIVE_MODE/API_TIMEOUT_MS/Providers/Router`; provider keys `name/api_base_url/api_key/models/transformer`; router keys `default/background/think/longContext/longContextThreshold/webSearch/image`). All paths sandboxed under `$HOME` via `_under_home`. Unknown top-level keys stripped with warnings; provider-level transformer customizations preserved. |
| 2 | `server/ccr_setup.py::api_ccr_install_command` | Returns the npm command string for the UI to display — the dashboard NEVER runs `npm install -g` autonomously. User runs it themselves. |
| 3 | `server/ccr_setup.py::api_ccr_service` | Runs `ccr start | stop | restart` (15s timeout). |
| 4 | `server/ccr_setup.py::api_ccr_alias_snippet` | Generates a copy-paste block (`# >>> zclaude (lazyclaude) >>>` … `# <<<`) with `alias zclaude='ccr code'` and the `eval "$(ccr activate)" && claude` alternative. Detects `$SHELL`, returns the corresponding `~/.zshrc` / `~/.bashrc` path and `already_present` (substring match — read-only). **Never writes to any rc file.** |
| 5 | `server/ccr_setup.py::api_ccr_presets` | Returns 5 provider presets the UI can one-click insert: Z.AI (via `aihubmix` shape with `Z/glm-4.5`, `Z/glm-4.6`), DeepSeek, OpenRouter, Ollama, Gemini — all mirrored verbatim from the upstream `config.example.json`. |
| 6 | `server/routes.py` | Registers 5 GET routes (`/api/ccr/status`, `/config`, `/install-command`, `/alias-snippet`, `/presets`) + 2 POST routes (`/api/ccr/config`, `/service`). |
| 7 | `server/nav_catalog.py` + `dist/index.html` `VIEWS.zclaude` | New tab `🛣️ zclaude (CCR)` under the `config` group. |
| 8 | `dist/index.html` 5-step wizard | (1) Status pills + npm install command in copy-able `<code>` when ccr missing. (2) Providers — preset chips + editable rows (name/url/key/models/transformer JSON). (3) Router rules — 5 selects populated from configured provider×model pairs + `longContextThreshold`. (4) Service Start/Stop/Restart + live output. (5) Shell alias `<pre>` + Copy button + current-shell + rc-path + muted note that the user must paste it themselves. |
| 9 | `tools/translations_manual_25.py` (new) | KO → EN/ZH for 65 new strings. |

### Verified facts used in implementation
Source: `https://raw.githubusercontent.com/musistudio/claude-code-router/main/{package.json,README.md}` fetched 2026-04-29.
- npm: `@musistudio/claude-code-router` v2.0.0, bin `ccr`, node ≥20.0.0
- Config: `~/.claude-code-router/config.json`, env interpolation `$VAR` / `${VAR}`
- CLI: `ccr code | start | stop | restart | status | ui | model | activate | preset`
- `eval "$(ccr activate)"` exports `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL=http://127.0.0.1:3456`, `NO_PROXY=127.0.0.1`, `DISABLE_TELEMETRY`, `DISABLE_COST_WARNINGS`, `API_TIMEOUT_MS`

### Smoke
```
$ python3 -c "from server.ccr_setup import api_ccr_status, api_ccr_presets; s=api_ccr_status({}); print(s['ok'], s['node_version'], 'presets=', len(api_ccr_presets({})['presets']))"
True v24.13.0 presets= 5
$ make i18n-verify
✓ 모든 검증 통과
```

---
## [2.44.1] — 2026-04-29

### 🪢 multiAssignee parallel fan-out + keyed canvas SVG diff

User: "자율모드 시작." Picks up the two items v2.44.0 explicitly deferred:
the UI surface for `ProviderRegistry.execute_parallel` (openclaw-style
multi-provider fan-out) and the keyed-diff renderer for the workflow
canvas.

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html` `_wfInspectorBody` | Session/subagent inspector replaces the single assignee `<select>` with a repeating row builder. `+ 어시니 추가` appends, `−` per row removes. When `length ≥ 2` a "병렬 (N)" chip renders next to the section label. |
| 2 | `dist/index.html` `_wfMultiAssignee*` helpers | `_wfMultiAssigneeRows / Set / Add / Remove / RowHtml`. Stored as `node.data.multiAssignee = ['claude:opus', 'openai:gpt-4.1', …]`. Back-compat: `assignee = rows[0]`; `multiAssignee = rows.length ≥ 2 ? rows : []`, so single-assignee nodes keep behaving exactly as before. |
| 3 | `server/workflows.py::_sanitize_node` | New `multiAssignee` field on `session`/`subagent` types — same length cap as `assignee`, dedupe preserving order, hard cap at 8 (matches `execute_parallel` pool). |
| 4 | `server/workflows.py::_execute_node` session/subagent branch | Dispatch decision: `len(multi_assignees) ≥ 2` → `get_registry().execute_parallel(...)`; else existing `execute_with_assignee(...)`. Same `AIResponse` shape downstream — cost tracking, output writing, error handling all unchanged. |
| 5 | `dist/index.html` `_wfRenderCanvas` | Rewrote as keyed-diff renderer. New `__wf._nodeEls: Map<id, <g>>` + `__wf._nodeSnapshot: Map<id, json>`. Per render: add new ids, replace changed ids (snapshot-keyed), remove stale ids. Edges still rebuild via `innerHTML` — fewer of them and they reference live node positions. |
| 6 | `dist/index.html` `_wfBuildNodeEl` (new) | Parses `_wfRenderNode(n)` HTML through `DOMParser` (image/svg+xml, wrapped in `<svg xmlns>` for namespace), `document.importNode`, returns the `<g.wf-node>`. |
| 7 | `dist/index.html` `_wfNodeSnapKey` (new) | `JSON.stringify({type, title, x, y, data.assignee, data.multiAssignee})`. Selection state intentionally excluded — `_wfSyncSelectionClasses` toggles classes in-place. |
| 8 | `dist/index.html` `_wfOpen` / `_wfUndo` | Set `__wf._forceFullCanvasRebuild = true` so the first render after load and any wholesale array swap falls back to the old `innerHTML` path. Flag self-clears after the rebuild. |
| 9 | `tools/translations_manual_24.py` (new) | KO → EN/ZH for the 5 new inspector strings. |

### Verification — handler delegation

All node-level events (`mousedown`, `dblclick`, `touchstart`, `wheel`)
are attached to the parent `<svg>#wfSvg` and resolve targets via
`querySelector('[data-node="…"]')` / `.wf-node`. No per-element
`addEventListener` calls on `wf-node`. Diff-rebuilt elements retain
the `data-node` attribute set inside `_wfRenderNode`, so all
interactions continue without re-binding. `_wfApplyRunStatus`,
`_wfSyncSelectionClasses`, `_wfSyncMultiSelectClasses`, search
highlight, and group collapse all use the same selector pattern.

### Smoke
```
$ python3 -c "from server.workflows import _sanitize_node; from server.ai_providers import ProviderRegistry, get_registry; print('parallel=', hasattr(ProviderRegistry, 'execute_parallel'), 'reg=', type(get_registry()).__name__)"
parallel= True reg= ProviderRegistry
$ python3 -m py_compile server/workflows.py server/ai_providers.py
$ make i18n-verify
✓ 모든 검증 통과
```

---
## [2.44.0] — 2026-04-29

### 🖥️ Open ports / CLI sessions / memory monitors + workflow perf

User: "현재 PC에 열려있는 포트 / 열려있는 CLI 세션 / 메모리를 보고 필요하면
바로 kill하고 싶어. 그리고 워크플로우가 너무 느리고 다중 AI를 openclaw처럼
병렬로 못 돌리고 있어 — 최적화해줘." Three new `observe` tabs to surface
host-process state, plus a sweep of workflow-engine and canvas optimizations.

| # | Where | What |
|---|---|---|
| 1 | `server/process_monitor.py` (new) | Stdlib-only module. `lsof -nP -iTCP -sTCP:LISTEN` + `lsof -nP -iUDP` parser; `~/.claude/sessions/*.json` + `os.kill(pid,0)` liveness; macOS `vm_stat` / `sysctl hw.memsize` / `sysctl vm.swapusage` snapshot; `ps -axo` for top-30 RSS with Claude-Code detection. |
| 2 | `server/process_monitor.py::api_process_kill` | Hard guards: `pid != os.getpid()`, `pid >= 500`, signal whitelist `{SIGTERM, SIGKILL}`, alive-check, `PermissionError` surfaced as 403. |
| 3 | `server/process_monitor.py::api_kill_idle_claude` | Bulk SIGTERM all CLI sessions whose `idle_seconds > thresholdSec` (default 600). Same guards per pid. |
| 4 | `server/process_monitor.py::api_session_open_terminal` | Wraps existing `actions.open_session_action` (Terminal.app / iTerm2 / Warp focus). |
| 5 | `server/routes.py` | Registers 6 endpoints: `GET /api/ports/list`, `/api/sessions-monitor/list`, `/api/memory/snapshot`; `POST /api/process/kill`, `/api/sessions-monitor/open-terminal`, `/api/memory/kill-idle-claude`. |
| 6 | `server/nav_catalog.py` + `dist/index.html` `VIEWS.openPorts` / `cliSessions` / `memoryManager` | Three new tabs under `observe`. Style mirrored from `VIEWS.system`. Memory tab shows total/used/free/swap progress bars, "Idle Claude Code 일괄 종료" button, top-30 RSS table with Claude-Code rows highlighted. |
| 7 | `server/workflows.py` `_MAX_PARALLEL_WORKERS` | 4 → `max(8, min(32, cpu_count()*2))` (16 on 8-core). Env override (`WORKFLOW_MAX_PARALLEL`) preserved. |
| 8 | `server/workflows.py::api_workflow_patch` + `_is_position_only_patch` | Drag-debounced position/viewport patches no longer re-run full `_sanitize_workflow`; `math.isfinite` whitelist + in-place node mutation only. |
| 9 | `server/workflows.py` `_TOPO_ORDER_CACHE` / `_TOPO_LEVELS_CACHE` | Memoized topological sort keyed by graph shape. FIFO 256-entry soft cap. |
| 10 | `server/workflows.py` `_RUNS_CACHE` + `_persist_run` | Per-node status updates inside `_run_one_iteration` mutate an in-memory cache under `_RUNS_LOCK`; disk-write only at iteration boundary / terminal failure / completion. SSE `_run_status_snapshot` reads cache first. Drops per-run JSON round-trips from O(N) to O(L). |
| 11 | `server/ai_providers.py::ProviderRegistry.execute_parallel` (new) | Backend-only openclaw-style fan-out: `ThreadPoolExecutor(min(len, 8))` + `as_completed` first-ok with `future.cancel()` on the rest. UI wiring deferred to v2.44.1. |
| 12 | `dist/index.html` `__wf._webhookSecretCache` | Webhook secret cached per-`workflowId`; `_wfRefreshWebhookSecret` no longer POSTs on every node click. |
| 13 | `dist/index.html::_wfRenderInspector` | Early-exit guard when `selectedNodeId` unchanged and `_inspectorDirty === false`. All node-data mutators set the dirty flag before re-rendering. |
| 14 | `tools/translations_manual_23.py` (new) | KO → EN/ZH for 30+ new strings (port headers, CLI columns, memory bars, kill confirms, idle threshold). |

### Skipped / deferred
- **Keyed canvas SVG patch**: full DOM-element diff for `_wfRenderCanvas` exceeded the low-risk budget — would require re-attaching every drag/connect/double-click handler. B4/B7 already remove the dominant cost.
- **`execute_parallel` UI wiring**: needs a `multiAssignee[]` field in the inspector + form — landing in v2.44.1.

### Smoke
```
$ python3 -c "from server.workflows import _MAX_PARALLEL_WORKERS; from server.process_monitor import api_ports_list, api_memory_snapshot, api_cli_sessions_list; from server.ai_providers import ProviderRegistry; print(_MAX_PARALLEL_WORKERS, api_ports_list({}).get('ok'), api_memory_snapshot({}).get('ok'), api_cli_sessions_list({}).get('ok'), hasattr(ProviderRegistry, 'execute_parallel'))"
16 True True True True
$ make i18n-verify
✓ 모든 검증 통과
```

---
## [2.43.2] — 2026-04-28

### 📊 Project / session token usage drill-down

User: "프로젝트 혹은 세션별 토큰 사용량을 보고 싶어. 근데 사용량/비용
(토큰 중심)에서 지금 TOP20만 볼 수 있는데, 그냥 프로젝트를 눌러서 토큰
사용량을 보고 싶어." Replaces fixed TOP-20 read-only table with a
clickable, scrollable list of every project; click → modal with the
project's session-level breakdown.

| # | Where | What |
|---|---|---|
| 1 | `server/system.py::api_usage_summary` | Drops `LIMIT 20` from the `byProject` SQL so the response carries every project (29 instead of 20 on this machine), still ordered by tokens DESC. |
| 2 | `server/system.py::api_usage_project` (new) | `GET /api/usage/project?cwd=...` — returns `{totals, sessions[], byTool[], byAgent[], dailyTimeline[]}` for one project. cwd resolved + sandboxed under `$HOME`. Joins `tool_uses` filtered to that project's session_ids for tool/agent distribution. |
| 3 | `server/routes.py` | Wires `/api/usage/project` into `ROUTES_GET`. |
| 4 | `dist/index.html::VIEWS.usage` | Project section becomes a scrollable (max 420 px) list of all projects; rows are `link-row` clickable, with cwd as tooltip + truncated subtitle. Header shows total project count instead of "TOP 20". |
| 5 | `dist/index.html::openProjectUsage` (new) | Modal: 6 stat cards (total / input / output / cacheRead / cacheCreate / sessions), tool-by-tool + agent-by-agent token bars, daily timeline minibar, sessions table sorted by tokens DESC. Each session row links into the existing session-detail modal. |
| 6 | `tools/translations_manual_22.py` (new) | KO → EN/ZH for 10 new strings (`프로젝트별 토큰`, `세션별 토큰`, `행 클릭 → 상세`, etc.). |

#### Verification
```
GET /api/usage/summary               → byProject count: 29 (was 20 cap)
GET /api/usage/project?cwd=$HOME/lazyclaude
                                     → ok=True, sessions=1, dailyTimeline len=1
GET /api/usage/project?cwd=/tmp      → 400 cwd outside home (sandbox)
GET /api/usage/project (no cwd)      → 400 cwd required
Headless: usage tab → 29 project rows, click 1st → modal with 81 session
                       rows for that cwd, 0 console errors
e2e-tabs-smoke.mjs                   → 58/58
make i18n-verify                     → 0 missing across EN/ZH
```

#### Compatibility
- Backend addition only — `byProject` still ordered the same way; unchanged frontend code keeps working (just sees more rows now).
- New endpoint `/api/usage/project` is purely additive.

---
## [2.43.1] — 2026-04-28

### 🚀 Perf — workflow canvas + skills/commands lists

User: "지금 전체적으로 대시보드가 너무 느려. 특히 워크플로우 부분이 심각하게
렉이 걸리고 느린데, 이 부분 최적화해줘." Three measured bottlenecks fixed.

**Measured before**

```
/api/skills      :  816 ms (1.37 MB) — 485 SKILL.md re-parsed every visit
/api/commands    : 1116 ms (1.44 MB) — 308 plugin command .md re-parsed
canvas drag      :   ~100 mousemove/s → _wfRenderMinimap fired sync every
                     event; full canvas redraw + O(N×E) edge lookup
```

**Measured after**

```
/api/skills      :   95 ms cold → 36 ms warm  (~22× / cache hit)
/api/commands    :  535 ms cold → 35 ms warm  (~31× / cache hit)
canvas drag      :   ≤1 minimap repaint per animation frame; node lookup
                     O(deg) via cached Map for the duration of a drag
```

**Changes**

| # | Where | What |
|---|---|---|
| 1 | `server/skills.py::list_skills` | Wrapped with TTL+mtime cache (60 s). Fingerprint stat()s only the top-level `~/.claude/skills/` and `~/.claude/plugins/marketplaces/*` dirs (cheap), so a freshly edited skill invalidates immediately. New `force_refresh` kw. |
| 2 | `server/commands.py::list_commands` | Same TTL+mtime cache pattern (60 s). |
| 3 | `server/routes.py` | New `_q_truthy(q, key)` helper; `/api/skills` and `/api/commands` now forward `?refresh=1` to bypass the cache. |
| 4 | `dist/index.html::_wfScheduleMinimap` (new) | Coalesces minimap repaints into one rAF tick. Replaces the inline rAF block inside `_wfRenderCanvas`. |
| 5 | `dist/index.html::onMove` | Drag handler swaps `_wfRenderMinimap()` (sync, ~100/s) for `_wfScheduleMinimap()` (≤60/s). Caches the dragged node reference on `drag._node` (no `nodes.find()` per mousemove). |
| 6 | `dist/index.html::_wfUpdateNodeTransform` | Builds a `nodeId → node` `Map` and a `nodeId → edges[]` adjacency map once, caches them on `__wf.drag` for the drag lifetime. Per-frame cost: O(N×deg) → O(deg). |

**Verification**
```
JS smoke         : 6 script blocks parse OK
e2e-tabs-smoke   : 58/58 (one flaky AFTER.sessions retry — re-run clean)
GET /api/skills?refresh=1   : bypasses cache (force re-scan)
backend cold/warm           : as measured above
```

**Compatibility**
- Caches are process-memory only; `force_refresh` defaults to `False` so all existing call sites are unchanged.
- `_wfScheduleMinimap` is the same idempotent-rAF pattern already used elsewhere; no new minimap behavior.
- Drag-time Maps are scoped to `__wf.drag` and discarded on drag end; no leaks.

---
## [2.43.0] — 2026-04-28

### 🛠️ Setup Helpers — global ↔ project scope across the board

User: "지금 세팅을 도와주는 것들이 필요해. 예를 들어서, claude MD도 global,
프로젝트별로 할 수 있어야해." Followed by "C로 가자." — full package across
six setup surfaces. Until now most config tabs only edited the global
`~/.claude/` files; project-scope (`<cwd>/.claude/`) was either read-only
(CLAUDE.md) or completely missing (settings, settings.local, skills,
commands). This release ships parity.

**Added — backend (`server/projects.py` + `server/routes.py`)**

| Endpoint | Purpose |
|---|---|
| `GET/PUT /api/project/claude-md` | `<cwd>/CLAUDE.md` |
| `GET/PUT /api/project/settings` | `<cwd>/.claude/settings.json` (committed) |
| `GET/PUT /api/project/settings-local` | `<cwd>/.claude/settings.local.json` (gitignored personal overrides) |
| `GET /api/project/skills/list` | list project skills |
| `GET/PUT /api/project/skill` | one skill (creates `.claude/skills/<id>/SKILL.md`) |
| `POST /api/project/skill/delete` | remove skill dir |
| `GET /api/project/commands/list` | list project commands |
| `GET/PUT /api/project/command` | one command (sub-paths via `:`, e.g. `review:critical`) |
| `POST /api/project/command/delete` | remove command file |

Every handler resolves `cwd` via `_validate_project_cwd` — must be a real directory under `$HOME` or the call returns `invalid or out-of-home cwd`. Permission rules go through the existing `sanitize_permissions` so an invalid `:*` mid-pattern is auto-fixed exactly like the global `put_settings` path. Path-traversal guard on commands re-resolves the final path and refuses anything outside `<cwd>/.claude/commands/`.

**Added — frontend (`dist/index.html`)**

- Shared `_renderConfigScopeToggle` widget + `state.data.cfgScope`/`cfgCwd`/`cfgSettingsKind` so the user picks scope once and it sticks across tabs.
- **CLAUDE.md tab**: 🌐 Global / 📁 Project toggle + project picker. Save dispatches to the right endpoint.
- **Settings tab**: same scope toggle; in project mode adds a sub-toggle for `settings.json` (committed) vs `settings.local.json` (personal). Recommendation profiles only show in global mode.
- **Skills tab**: project mode lists `<cwd>/.claude/skills/*` only. ＋ New skill creates a directory + seeded `SKILL.md`. Cards open a project-aware editor.
- **Commands tab**: project mode lists `<cwd>/.claude/commands/**/*.md`. ＋ New command, click-to-edit, delete.
- **Hooks tab**: project mode shows a header card summarising project hook counts in `settings.json[hooks]` and `settings.local.json[hooks]`, with a one-click jump to the Settings tab for editing (project hooks are stored inside settings.json, so the JSON shape stays authoritative there).

**Verification**

```
backend smoke (curl)
  /api/project/claude-md?cwd=$HOME/claude-dashboard   → 200, raw len ≈ 7000
  /api/project/settings?cwd=...                       → 200, exists=false (no .claude/)
  /api/project/settings-local?cwd=...                 → 200, parses real allow rules
  /api/project/claude-md?cwd=/tmp                     → 400 invalid or out-of-home cwd
  PUT round-trip (CLAUDE.md / settings / skill)       → all atomic, files written
  path traversal (id="../etc")                        → 400 invalid command id

frontend smoke (Playwright)
  claudemd / settings / skills / commands / hooks     → all render, 0 console errors

regression
  e2e-tabs-smoke.mjs                                  → 58/58
  make i18n-verify                                    → 0 missing across 4135 keys × 3 langs
```

**Compatibility**

- All new endpoints are additive — old API routes unchanged.
- Frontend default scope is `global`, preserving existing flows. Existing global-only callers don't need to know about scope.
- Project paths must resolve under `$HOME` — same sandbox the rest of the app uses.

---
## [2.42.3] — 2026-04-28

### 🩹 Hooks tab — 2 s initial load + delete didn't refresh UI

User: "훅 부분이 처음에 로딩이 너무 많이 걸려. 그리고 삭제해도 삭제가 안되는
것 같아." Two distinct bugs in the Hooks tab — both confirmed end-to-end.

**Root causes**

1. `VIEWS.hooks` blocked initial paint on `/api/hooks/recent-blocks`, which
   walks up to 60 jsonl transcripts (~90 MB on a power user's machine) and
   took 1.94 s. Cold cost was paid on every visit, even on filter
   re-renders.
2. `deleteHook()` fired the API call, showed a success toast, then did
   nothing — no `renderView()` call. The deleted hook stayed visible
   until the user navigated away, looking like delete was broken.

**Changes**

| # | Where | What |
|---|---|---|
| 1 | `server/hooks.py::recent_blocked_hooks` | TTL+mtime cache (5 min). Fingerprint is just the newest jsonl mtime, so a single `stat()` invalidates correctly without rescanning. New `force_refresh` param + `?refresh=1` on `api_recent_blocked_hooks`. Cold 0.97 s → warm 0.026 s (~37×). |
| 2 | `dist/index.html::VIEWS.hooks` | Drop `/api/hooks/recent-blocks` from the initial `Promise.all`. Module-level `__hooksRecentBlocks` cache survives filter re-renders; the panel renders into a `#hooksRecentBlocksHost` placeholder that fills in after first paint. |
| 3 | `dist/index.html::AFTER.hooks` | Lazy fetch `/api/hooks/recent-blocks` once per page session and inject HTML via the new `_renderRecentBlocksPanel(data)` helper (extracted from the inline template). |
| 4 | `dist/index.html::deleteHook` | Call `renderView()` on success for both plugin and user delete paths so the deleted hook actually disappears. Toast strings now go through `t()`. |

**Verification**

```
Cold blocking work:  1.94 s   →  0.05 s   (Hooks tab feels instant)
Recent-blocks cold:  0.97 s   (deferred — happens after first paint)
Recent-blocks warm:  0.026 s  (cache hit, 37× faster)
e2e-tabs-smoke.mjs:  58/58
Headless DOM probe:  __hooksRecentBlocks populates within 2 s, host
                     div fills with 5 items, 0 console errors.
make i18n-verify:    0 missing across EN/ZH
```

**Compatibility**

- `recent_blocked_hooks(force_refresh=False)` keeps the previous default;
  callers passing only `max_files` / `top_n` are unchanged.
- The cache is per-process (in-memory only); restarting the server clears it.

---
## [2.42.2] — 2026-04-27

### 🖥️ Workflow node spawn → matching provider CLI

User: "워크플로우에서 Builder나 Reviewer을 누르면 해당 AI의 cli가 아니라
클로드 코드가 새로 열려. 지금 진행중인 AI cli가 열려야해." Every node's
🖥️ button on the workflow canvas was hard-wired to `claude` regardless of
the node's `assignee`, so a node assigned to `@gemini:gemini-2.5-pro` or
`@ollama:llama3.1` would still launch Claude Code.

| # | Where | What |
|---|---|---|
| 1 | `server/actions.py::_resolve_provider_cli` (new) | Maps `provider:model` (`claude:opus` / `gemini:gemini-2.5-pro` / `ollama:llama3.1` / `codex:o4-mini` + aliases like `anthropic` / `google` / `openai` / `gpt`) to `{provider, bin, args, model}`. Uses the existing `_which()` 11-path fallback to find each CLI. When the requested CLI isn't installed, it returns claude with a `fallback_reason` so the user gets a warning toast instead of a silent re-route. |
| 2 | `server/actions.py::api_session_spawn` | Now accepts `body.assignee`. For Claude (the only TUI that takes a positional prompt without exiting), the prompt is appended as before. For Gemini / Ollama / Codex, the prompt is printed as a banner (`echo '── Prompt ──'; printf …`) before launching the interactive REPL — passing it as a positional would have caused those CLIs to one-shot and exit. Response now carries `provider` / `cli` / `model` / `fallbackReason`. |
| 3 | `dist/index.html::_wfSpawnSession` | Sends `n.data.assignee` in the spawn body; success toast becomes provider-aware (`Gemini 세션 시작됨 (gemini-2.5-pro)`); a fallback uses a `warn` toast that surfaces `fallbackReason`. |

#### Verification
```
_resolve_provider_cli('claude:opus')        → claude-cli, /Users/o/.local/bin/claude
_resolve_provider_cli('gemini:gemini-2.5-pro') → gemini-cli, /Users/o/.nvm/.../bin/gemini, --model 'gemini-2.5-pro'
_resolve_provider_cli('ollama:llama3.1')    → ollama, /opt/homebrew/bin/ollama, run 'llama3.1'
_resolve_provider_cli('codex:o4-mini')      → claude-cli (codex not installed) + fallback_reason
JS smoke (6 blocks): parses OK
```

#### Compatibility
- Body without `assignee` (e.g. existing chat Spawn buttons elsewhere in the
  app) still routes to Claude — old callers unchanged.
- `claude` flags (`systemPrompt` / `allowedTools` / `--resume`) are only
  appended on the claude-cli path; non-Claude CLIs ignore them.

---
## [2.42.1] — 2026-04-27

### 🔄 Workflow run visibility — list cards + canvas auto-restore

User: "워크플로우 실행결과랑 현재 실행중인지? 그리고 어느 노드에 실행중인지
인터렉티브하게 보여줘야해. 지금 기록을 볼수 없으니까 쓸수가 없어." Backend
already had per-run state (`runs[runId].nodeResults[nid]`) but the workflow
list cards rendered no run history at all, and re-opening the canvas of a
running workflow showed an idle topology — the SSE poller only started after
a fresh `Run` click. So users couldn't tell which workflows were live, which
had finished, or which had failed without opening each one.

| # | Where | What |
|---|---|---|
| 1 | `server/workflows.py::api_workflows_list` (+35 LoC) | Each workflow item now carries `lastRuns` (last 3 runs with `runId/status/startedAt/finishedAt/durationMs/currentNodeId/error`), `runningCount` (number of in-flight runs), `activeRunId` (most recent running run, if any), and `totalRuns`. Reads from the existing `runs` map — no schema migration. |
| 2 | `dist/index.html::_wfRenderList` (+~30 LoC) | List cards now show inline status chips (✅ ok / ❌ err / ⏳ running) for the last 3 runs, a pulsing `● 실행 중` badge if any run is in flight, and `(N회)` total count. Empty state shows `실행 기록 없음` instead of nothing. `_runIcon`/`_runColor` helpers. |
| 3 | `dist/index.html::_wfOpen` (+~15 LoC) | When entering a canvas, auto-restore: if `activeRunId` exists, attach `__wf.runId` and start `_wfStartPolling()` so node colors animate live; otherwise fetch the latest finished run via `/api/workflows/run-status` and `_wfApplyRunStatus()` to hydrate node colors one-shot. Wrapped in try/catch so a stale runId never blocks canvas rendering. |
| 4 | `tools/translations_manual_20.py` (new) | KO → EN/ZH for `실행 기록 없음` / `실행 중` / `회`. |

#### Verification
```
GET /api/workflows/list                     →  200, 3 wf, lastRuns/runningCount/activeRunId/totalRuns present
UI smoke (renderView WF list)               →  3 cards, 3 chip blocks, "실행 기록 없음" copy rendered
e2e-hyper-projects-and-sidebar.mjs          →  11/11
e2e-tabs-smoke.mjs                          →  58/58
make i18n-verify                            →  0 missing across EN/ZH
```

#### Compatibility
- Backend payload only adds fields. Older `dist/index.html` ignores them.
- Polling cadence unchanged; we reuse the existing 1-Hz SSE-style loop.

---
## [2.42.0] — 2026-04-27

### 🖱️🧩🧭🔁 Four Anthropic features in one release — Computer Use / Memory / Advisor / Routines

User asked which of `advisor tool` / `claude code routines` / `managed
agents memory` / `computer use` were already in the dashboard. Answer
was: 0 fully, 2 partially, 2 missing. This release fills the gap with
**all four**, each as its own playground tab + backend module.

| # | Where | What |
|---|---|---|
| 1 | `server/computer_use_lab.py` (new, ~210 LoC) | Anthropic `computer-use-2025-01-24` beta tool playground. POSTs to `https://api.anthropic.com/v1/messages` with the `computer_20250124` tool definition + optional base64 screenshot, then surfaces the model's tool_use plan (sequence of `screenshot` / `key` / `mouse_*` calls). **Plan-only — the dashboard never moves the user's mouse or keyboard.** Validates screenshot path stays under `$HOME`, clamps screen size to (320..3840, 240..2160), per-call cost calc against bundled price table, history capped at 50. |
| 2 | `server/memory_lab.py` (new, ~190 LoC) | Anthropic `memory-2025-08-18` beta playground. POSTs with `memory_20250818` tool, walks the response for `tool_use` blocks named `memory`, extracts every `op` (create/read/update/delete) into `memoryEvents`. New `api_memory_lab_blocks` aggregates observed memory blocks across history into a `{key:value}` snapshot so the user can see "what does the model remember about me?" without spelunking through Anthropic's server-side store. |
| 3 | `server/advisor_lab.py` (new, ~240 LoC) | Pair a fast/cheap **executor** (Haiku 4.5 / Sonnet) with a smart/slow **advisor** (Opus). Sends the prompt to the executor first, then sends `User request + Executor draft` to the advisor with system prompt "review this draft", and surfaces both responses + a `delta {tokensDiff, costDiff, latencyDiff}` so the user can decide when the Opus tax is worth it. |
| 4 | `server/routines.py` (new, ~210 LoC) | **Full CRUD over `~/.claude/scheduled-tasks/<name>.yaml`** (the existing tab was listing-only). Tiny line-based YAML extractor (no PyYAML — stdlib only) for `name/description/schedule/command/cwd/enabled`. Run-now endpoint uses `subprocess.run(shell=True, timeout=120)` with a strict cwd-under-`$HOME` guard; rejects anything outside. Stdout/stderr capped at 4 KB per stream. Dry-run mode returns the resolved command + cwd without executing. |
| 5 | `server/routes.py` | Wired all 14 new endpoints — list/examples/history/run for each lab, plus get/save/delete for routines. Item-route added for `/api/routines/get/<name>`. |
| 6 | `dist/index.html` `NAV` | 4 new tabs — `computerUseLab` / `memoryLab` / `advisorLab` (playground group), `routines` (config group). Each renders a compact form: example chips, prompt textarea, model select, ▶ Run button, results card, history block. |
| 7 | `dist/index.html` `VIEWS.*` | Compact view implementations (~80 LoC each): inline `_cuRun()` / `_mlRun()` / `_alRun()` / routines `_routineEdit/_routineSave/_routineRun/_routineDelete` handlers. Routines tab also has a full edit modal. |
| 8 | `tools/translations_manual_19.py` (new) | KO → EN/ZH for every new label, button, toast, confirm. `make i18n-refresh` passes 0 missing across 4012+ keys × 3 languages. |

#### Live verification
```
GET /api/computer-use-lab/examples →  200  (5 presets, 4 models)
GET /api/memory-lab/examples       →  200  (5 presets)
GET /api/routines/list             →  200
GET /api/advisor-lab/models        →  200  (3 executors, 2 advisors)
UI: all 4 view headers render with 0 console errors:
  🖱️ Computer Use Lab · 🧩 Memory Lab · 🧭 Advisor Lab · 🔁 Claude Code Routines
```

#### Compatibility
- All 4 modules are self-contained — no schema or DB migration.
- `_anthropic_key()` reads from the existing `aiProviders` tab key store
  (or env `ANTHROPIC_API_KEY` via that store). Without a key the labs
  surface `needKey: true` instead of crashing.
- `routines.py` rejects `cwd` outside `$HOME` so a stray YAML can't
  point the run-now endpoint at a system path.

#### Per-feature pricing (USD per 1M tokens)
- haiku-4-5: 1.0 / 5.0
- sonnet-4-5/4-6: 3.0 / 15.0
- opus-4-6/4-7: 15.0 / 75.0

---
## [2.41.0] — 2026-04-27

### 👥 Agent Teams + 🤝 Recent sub-agent activity (with one-click CLI)

Two new affordances on top of the existing Agents tab and Project Detail
modal — both born from the user's request to (a) "bundle agents that
go together" and (b) "see what work session A delegated to its sub-agents
and re-open the matching CLI."

| # | Where | What |
|---|---|---|
| 1 | `server/agent_teams.py` (new, ~280 LoC) | Whitelisted schema for saved teams. Each team is `{id: tm-<hex>, name, description, agents: [{name, scope, cwd, role, task}], createdAt, updatedAt}`. Atomic JSON persistence at `~/.claude-dashboard-agent-teams.json` (env override `CLAUDE_DASHBOARD_AGENT_TEAMS`). Members reference existing agents — the store doesn't duplicate the agent body, so renaming/deleting an agent reflects immediately on the next list. `_agent_exists()` resolves global / project / builtin / plugin scopes via `get_agent` + filesystem checks; missing members surface as `exists:false` + a per-team `missingCount`. |
| 2 | `server/agent_teams.py` `api_agent_teams_*` | Five routes wired through `routes.py`: `GET /api/agent-teams/list`, `GET /api/agent-teams/get/<tm-id>`, `POST /api/agent-teams/save` (create or update), `POST /api/agent-teams/delete`, `POST /api/agent-teams/spawn`. The spawn route returns one descriptor per existing member (`{name, scope, role, cwd, prompt, claudeCmd}`) and a `skipped` array for missing agents. The dashboard either drives `api_session_spawn` per descriptor or surfaces the descriptors as copy-pasteable `claude /agents <name> "<prompt>"` strings. |
| 3 | `server/projects.py::api_project_detail` | Response gains `subagentActivity: [{sessionId, ts, tool, agent, inputSummary, hadError, turnTokens, cwd}, ...]` mined from the existing `tool_uses` SQLite table (last 50 sessions for this cwd, top 60 delegations by recency). No new schema — reuses what `index_all_sessions` already captures, so projects with prior session history light up immediately. |
| 4 | `dist/index.html` Agents tab — Teams section | New card grid above the search bar: 👥 Agent Teams. Each card lists members as chips (📁 marker for project-scoped), shows a missing count when relevant, and exposes 🚀 Spawn / Edit / Delete. The editor modal pre-fills name + description + multi-select members from `state.data.agents.agents`. |
| 5 | `dist/index.html` Agents tab — Spawn flow | Clicking 🚀 opens a modal listing every member's resolved `claude /agents <name>` invocation in a copy-friendly `<pre>`, plus a Skipped panel for any member whose underlying agent file is gone. |
| 6 | `dist/index.html` Project Detail modal — `🤝 Recent sub-agent activity` | New section in the right column. Activity entries are grouped by source `sessionId` so the user sees "session A → 3 agents" at a glance. Each group expands to per-delegation rows (agent chip + input preview + token cost + error flag). Clicking the group's 🖥 CLI button drives `/api/session/spawn` to bring up Terminal.app on that session's resume command. |
| 7 | `tools/translations_manual_18.py` (new) | KO → EN/ZH for every Teams + activity label/button/toast. `make i18n-refresh` passes 0 missing across 4012+ keys × 3 languages. |

#### Live measurement
```
POST /api/agent-teams/save → {ok:true, isNew:true, id:"tm-0b58fbf7", agents:2}
GET  /api/project/detail   → {subagentActivity:[11 entries],
                              top: { agent:"Explore", tool:"Agent",
                                     inputSummary:"Scan codebase for ...",
                                     sessionId:"2aa992bf..." }}
```

#### Compatibility
- Backend additions only. Existing `/api/project/detail` shape strictly
  extends — every prior key (`cwd`, `name`, `repo`, `claudeJsonEntry`,
  `sessions`, `stats`) is unchanged; only the new `subagentActivity` key
  is added.
- No SQLite migration — the activity panel reads `tool_uses` rows that
  `server/sessions.py` was already inserting since v2.x.
- Teams store is brand-new (`~/.claude-dashboard-agent-teams.json`); first
  write creates it.

#### Verification
- Live API: agent-teams save/list round-trip; project-detail surfaces
  11 sub-agent delegations with correct grouping.
- UI smoke (Playwright eval): teamsGrid renders 1 saved team · all
  helper globals present · 0 console errors.
- e2e regression — **0 failures**:
  - `e2e-hyper-projects-and-sidebar.mjs` (v2.40)  — 11/11
  - `e2e-tabs-smoke.mjs`                          — 58/58

---
## [2.40.5] — 2026-04-27

### 🩹 Hotfix — Recent Blocks / Detective chips were unclickable (HTML quoting bug)

User reported: "Clicking the Recent Blocks card does nothing." Root
cause: in v2.40.4 the inline onclick attribute embedded
`JSON.stringify(rb.id)` directly:

```html
<button onclick="state.data.hooksFilter=${JSON.stringify(rb.id)}; …">
```

`JSON.stringify` returns a double-quoted string (`"pre:edit-write:..."`),
which collided with the surrounding `onclick="…"` attribute quotes — the
HTML parser cut the attribute short at the first inner `"`, dropped the
remainder onto the element as garbage, and the click handler never ran.
Same bug in the Detective result chips.

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html` Recent Blocks card | Replaced inline onclick payload with `data-hook-id="${escapeHtml(rb.id)}"` + `onclick="_jumpToHookCard(this.dataset.hookId)"`. No more double-quote collisions; the id flows through `dataset` which the browser decodes for us. |
| 2 | `dist/index.html` Detective chip | Same change — `data-hook-id` + `_jumpToHookCard` handler. The two surfaces now share one entry point. |
| 3 | `dist/index.html` (new) `_jumpToHookCard(id)` | Single helper used by both call sites: clears scope/event/risk filters so the searched id is the sole result, sets `state.data.hooksFilter`, re-renders, then `setTimeout(_pulseHookCard, 200)`. Centralising the logic also gives one place to extend (e.g. analytics, deep-link). |

#### Live verification
```
BEFORE click: { helperFn:true, cards:5, firstId:'pre:edit-write:gateguard-fact-force', filter:'(none)' }
AFTER  click: { filter:'pre:edit-write:gateguard-fact-force', visibleCards:6 }
```

Filter applied, target card rendered, pulse fired.

#### Compatibility
- Frontend-only patch. No backend, schema, or route changes.
- `_jumpToHookCard` is a new global; existing `_pulseHookCard` and
  `state.data.hooksFilter` shapes unchanged.
- e2e regression — **0 failures**:
  - `e2e-hyper-projects-and-sidebar.mjs` (v2.40)  — 11/11
  - `e2e-tabs-smoke.mjs`                          — 58/58

---
## [2.40.4] — 2026-04-27

### 🔬 Hook Detective + 🚨 Recent Blocks + 🧬 Dispatcher decoder

User asked: "How did you know which hook was blocking? Show me the same
clues inside the dashboard." This release ships A + B + C — three
additive UI affordances on top of the v2.40.2/.3 hooks tab so the user
can answer that question without reading log lines:

| # | Where | What |
|---|---|---|
| 1 | `server/hooks.py` (new `recent_blocked_hooks` + `_scan_jsonl_for_hook_blocks`) | Walks the most recent 60 jsonl transcripts under `~/.claude/projects/<slug>/*.jsonl`, line-scans for hook block markers ("hook returned blocking error", "PreToolUse:", etc.), and harvests every `pre\|post\|session\|notification\|user\|stop\|sub:<scope>:<name>` shape. Aggregates by frequency × last-seen mtime. **No JSON parser required** — the regex line-scan is robust to nested escaping inside tool_result content. New route `GET /api/hooks/recent-blocks` returns `{items, scanned, totalEvents}`. Live measurement on this dev box: 60 files scanned, 14 events, top entry `pre:edit-write:gateguard-fact-force × 4`. |
| 2 | `dist/index.html` `VIEWS.hooks` — **🔍 Hook Detective box** | Pasted-text introspector at the top of the hooks tab. Type or paste any block-error message; a regex extracts every hook id pattern; each id renders as a clickable chip. Clicking a chip auto-applies the search filter, scrolls the matching card into view, and pulses it (3 cycles of a blue ring). Backed by `_pulseHookCard()` — no other UI helper changed. |
| 3 | `dist/index.html` `VIEWS.hooks` — **🚨 Recent Blocks panel** | Renders the v2.40.4 backend output as one card per hook id with `<count>×` and last-seen timestamp. Clicking a card sets the search filter and triggers the same pulse as Detective. Panel only renders when `recentBlocks.items.length > 0`, so unblocked sessions don't see the section. |
| 4 | `dist/index.html` `openHookDetail()` + `_decodeHookCommand()` | New 🔬 **Detail** button on every hook card. Modal shows: synthesised display name, description, every metadata row (event/matcher/scope/source/pluginKey/type/timeout), the **decoded dispatcher chain** as a left-to-right pipeline of chips (`node` → runner → `<hook id>` → handler → flags), and the full raw command in a scrollable `<pre>`. The command decoder accepts the canonical `node -e "...require(s)" node <runner> <hookId> <handler> <flags>` shape used by ECC and falls back to a standalone hook-id match for shell-only entries. |
| 5 | `tools/translations_manual_17.py` (new) | KO → EN/ZH for Detective box, Recent Blocks panel, Detail modal labels, dispatcher-chain chips, raw-command label. `make i18n-refresh` reports 0 missing across 4012+ keys × 3 languages. |

#### How it composes with v2.40.2/.3
- v2.40.2 added the search/filter/panic; v2.40.3 surfaced `id` as the
  card title; v2.40.4 layers on the introspection (Detective, Recent
  Blocks, Detail). All four levels are additive — disabling any one
  doesn't break the others.
- The Recent Blocks card and Detective chip both use the same handler
  (`state.data.hooksFilter = id; renderView(); _pulseHookCard()`), so
  the user gets a consistent "click → land on the hook" experience.

#### Verification
- Live route: `curl /api/hooks/recent-blocks` → `{ok:true, scanned:60,
  totalEvents:14, items:[...]}` with `pre:edit-write:gateguard-fact-force`
  × 4 at the top.
- Live UI: hooks tab renders Detective input · Recent Blocks 5 cards ·
  41 detail buttons · 0 console errors.
- Detective paste roundtrip: paste a fragment containing
  `pre:edit-write:gateguard-fact-force` → result HTML contains the chip;
  click → search applied · card pulsed.
- e2e regression — **0 failures**:
  - `e2e-hyper-projects-and-sidebar.mjs` (v2.40)  — 11/11
  - `e2e-tabs-smoke.mjs`                          — 58/58

#### Compatibility
- `server/hooks.py` adds new helpers and a new route; existing
  `get_hooks` / `api_plugin_hook_update` shapes unchanged.
- Recent-blocks scan is read-only and bounded (60 files × ~1.5 MB cap
  per file), so even on a project with many transcripts it adds ≤200 ms
  to the hooks tab fetch.
- All UI additions are gated on data presence — empty Recent Blocks
  panel is hidden, Detective shows nothing until text is pasted.

---
## [2.40.3] — 2026-04-27

### 🏷️ Hook names — surface the same identity Claude Code's `/hooks` shows

User reported: "the hook names aren't showing — the names from `/hooks`
should be visible." Plugin hooks.json keeps `id` (and sometimes `name` /
`description`) at the **group level** alongside `matcher` and `hooks`,
e.g. `{ "matcher": "Bash", "hooks": [...], "id": "pre:bash:dispatcher",
"description": "..." }`. The dashboard's `_collect()` was already
copying every key off the **sub**-hook dict — but the human-readable
identity lives one level up, so cards lost it.

| # | Where | What |
|---|---|---|
| 1 | `server/hooks.py::_scan_plugin_hooks::_collect` | When a sub-hook entry doesn't already define `id` / `name` / `description`, propagate the group-level item's value. `description` was already partially propagated; `id` and `name` are the new propagations and the missing piece. |
| 2 | `server/hooks.py::get_hooks` | Same propagation for **user** hooks in `~/.claude/settings.json` — they too can carry `id` / `name` / `description` at the group level. |
| 3 | `dist/index.html` `renderUserCard` / `renderPluginCard` | Card header now shows the synthesised display name in `font-semibold mono` as the primary identifier. Priority: explicit `id` → explicit `name` → derived `<event> · <matcher>` (or `<event> · (no matcher)` when matcherless). The existing scope/source chips and matcher rows remain underneath. |
| 4 | (existing search) | The hooks-tab search bar already indexed `id` from v2.40.2, so once the field is populated the search just works — typing `pre:bash:dispatcher` instantly narrows to 1 card. |

#### Effect (live measurement)
```
GET /api/hooks  →  41 entries · 26 with id/name
First titles rendered:
  pre:bash:dispatcher                  (PreToolUse/Bash)
  pre:write:doc-file-warning           (PreToolUse/Write)
  pre:edit-write:suggest-compact       (PreToolUse/Edit|Write)
  session:start
  session:end:marker
Search "pre:bash:dispatcher" → 1 card
```

#### Compatibility
- No new fields introduced on the wire; same `/api/hooks` shape, just
  more keys surfaced per entry when the source hooks.json defines them.
- No frontend break for hooks without `id`/`name` — they fall back to
  the derived `<event> · <matcher>` string.
- e2e regression — **0 failures**:
  - `e2e-hyper-projects-and-sidebar.mjs` (v2.40)  — 11/11
  - `e2e-tabs-smoke.mjs`                          — 58/58

---
## [2.40.2] — 2026-04-27

### 🚨 Hooks tab — emergency UX (search · filter · risk chip · panic disable)

User reported "100+ hooks installed but the dashboard doesn't show them /
no way to disable specific ones." The hooks API was already returning
everything (1 user + ~120 plugin hooks across many marketplaces) but the
UI dumped them all as a flat per-event list with no search/filter, so the
ones causing actual blocked work (PreToolUse + Edit/Write/Bash matchers)
were impossible to find and kill quickly.

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html` `VIEWS.hooks` | **Always-visible filter bar** above the per-event grouping: full-text `<input>` over matcher · command · plugin · description · id; scope chips (All / User / Plugin); per-event chips (PreToolUse / PostToolUse / SessionStart / …); risky-only checkbox; "✕ Clear filter" appears as soon as any filter is set. Live counter shows `<shown>/<total>`. |
| 2 | `VIEWS.hooks` | **🚨 Risk chip + danger highlight** on every card whose event is `PreToolUse` and whose matcher matches `Edit\|Write\|Bash\|MultiEdit\|NotebookEdit`. Chip lives next to the existing scope badge so users can spot the offenders at a glance, even before searching. |
| 3 | `VIEWS.hooks` header | **🚨 Bulk-disable button** appears whenever ≥1 risky hook exists. Asks for confirmation with the exact count, then walks every matching entry: user hooks → `PUT /api/settings` with the `PreToolUse` matcher entries filtered out; plugin hooks → `POST /api/hooks/plugin/update {op:'delete'}` per entry, descending by (groupIdx, subIdx) so removing earlier entries doesn't shift later indices. Reports `<userRemoved> · <pluginRemoved>` (and any `failed` count) in a single toast. |
| 4 | `dist/index.html` `AFTER.hooks` | New hook lifecycle wires the search input (180 ms debounced) and the risky-only checkbox to `state.data.*` and re-renders. |
| 5 | `tools/translations_manual_16.py` (new) | KO → EN/ZH for every new label, chip, tooltip, and confirm. Bare common words ("전체"/"이벤트"/"실패") already mapped earlier; manual_16 adds the hooks-specific ones. `make i18n-refresh` reports 0 missing across 4012+ keys × 3 languages. |

#### What this lets the user do, immediately
- Type "fact-force" or any other plugin hook id — the list filters in real time.
- Tick "🚨 위험 훅만" to surface only the PreToolUse + Edit/Write/Bash hooks
  that are most likely to be the cause of blocked work.
- Click **🚨 위험 훅 일괄 비활성화** to delete every such hook in one
  confirmed click — both user and plugin entries.
- Each card still has its own [수정] / [삭제] buttons (already shipped); the
  panic button is a shortcut, not a replacement.

#### Compatibility
- No backend changes. Existing routes (`/api/hooks` / `/api/settings` PUT /
  `/api/hooks/plugin/update`) handle the panic flow.
- Filter state lives in `state.data.hooks{Filter,Scope,Event,RiskOnly}` —
  not persisted, intentionally (resets on tab leave so users don't have a
  stale filter on next visit).
- Plugin hook deletion still rewrites the plugin's `hooks/hooks.json`
  in place; reinstalling the plugin restores it. No marketplace-side
  side effects.

#### Verification
- e2e regression — **0 failures**:
  - `e2e-hyper-projects-and-sidebar.mjs` (v2.40)  — 11/11
  - `e2e-quick-settings.mjs` (v2.38)              — 6/6
  - `e2e-tabs-smoke.mjs`                          — 58/58
- Live UI smoke (Playwright eval): hooks tab renders search input · risky-only
  checkbox · panic button · 16 risk chips · 41 cards · 0 console errors.

---
## [2.40.1] — 2026-04-27

### 🚀 Performance hotfix — gzip + defer + fetch dedupe

User-reported lag. Three additive perf wins, no behaviour changes:

| # | Where | What |
|---|---|---|
| 1 | `server/routes.py::_send_static` | **mtime-keyed in-memory cache + on-the-fly gzip** for static responses (text/* / JS / CSS / JSON / SVG). `Accept-Encoding: gzip` from any modern browser triggers compression; raw bytes still served to clients that don't advertise gzip. **`dist/index.html` 1.12 MB → 270 KB on the wire** (76% smaller). Cache invalidates automatically on file mtime change so no manual restart is needed during development. |
| 2 | `dist/index.html` `<head>` | **`defer` on Chart.js / vis-network / marked** CDN scripts. None of them are touched by the inline boot script — they're only used inside specific views — so deferring them removes ~600 KB of parser-blocking from first paint. Views that need them (overview/analytics/agents/artifacts) work as before because `defer` finishes before `DOMContentLoaded`. |
| 3 | `dist/index.html` `api()` helper | **In-flight GET dedupe**. Many views fan out the same fetch on entry (e.g. `/api/agents` from agents tab + chatbot prompt rebuild). A `_apiInflight` Map coalesces concurrent identical GETs into one network request, halving boot-time fan-out with zero behaviour change. |
| 4 | `dist/index.html` sidebar | **`requestAnimationFrame` debounce on `renderNav()`** when `toggleFavoriteTab` fires. Rapid ★ toggles (or recent-tab MRU updates from successive `go()` calls) used to each rebuild the entire sidebar on the same tick; now they coalesce into the next animation frame. |

#### Verification
- HTML payload measured: 1,120,949 B raw → 270,609 B gzipped (`curl --compressed`).
- All four globals present after defer (`window.Chart`, `window.vis`, `marked`, `_apiInflight`, `_scheduleRenderNav`).
- e2e regression sweep — **0 failures** across:
  - `e2e-hyper-projects-and-sidebar.mjs` (v2.40 — 11/11)
  - `e2e-hyper-agent.mjs` (v2.39 — 7/7)
  - `e2e-quick-settings.mjs` (v2.38 — 6/6)
  - `e2e-tabs-smoke.mjs` — **58/58**

#### Compatibility
- Server cache holds `(mtime, raw, gzipped|None)` per resolved path; lifetime is the process. No disk write. Memory cost is bounded by the dist tree size (~few MB).
- Clients that don't send `Accept-Encoding: gzip` (rare, mostly raw HTTP probes) still get uncompressed bytes.
- No new files; no schema changes; no env var changes.

---
## [2.40.0] — 2026-04-27

### ⚡ Hyper Agent → project-scoped sub-agents · 🧭 Sidebar discovery (Favorites + Recent + `/`)

Two upgrades shipped together:

**(A) Hyper Agent now works on project-scoped sub-agents** (`<cwd>/.claude/agents/<name>.md`).
The same toggle / objective / refine targets / dry-run / rollback flow that
v2.39.0 introduced for global agents is now available per-project, with each
project's meta tracked independently — even when a global agent and a project
agent share the same name.

**(B) Sidebar discovery aids** — for users who said "categories are too many,
hard to find things." Three additive changes (no category restructure):

| # | Where | What |
|---|---|---|
| 1 | `server/hyper_agent.py` | Composite key namespace — `global:<name>` for global, `project:<sha8(cwd)>:<name>` for project. Legacy v2.39.0 flat keys are still read as global; subsequent writes auto-migrate to canonical. Every public function (`configure_agent` / `refine_agent` / `apply_proposal` / `rollback` / `get_hyper` / `history` / `toggle_agent`) now accepts an optional `cwd: str | None = None`. `_is_writable_agent` skips builtin/plugin only when scope is global; project scope is writeable when the file exists. Per-iteration `.bak.md` backup lives in the same scope as the agent. |
| 2 | `server/hyper_agent.py` | Two new POST endpoints `/api/hyper-agents/get` and `/api/hyper-agents/history` accept a `{name, cwd?}` body — required because cwd doesn't fit a URL path parameter. The original GET path-param routes are kept for global lookups (back-compat). `toggle/configure/refine-now/rollback` already accepted bodies; they now also pull `cwd` from the body. List response gains `key`, `scope`, and `cwd` fields per item. |
| 3 | `server/hyper_agent_worker.py` | After-session trigger now restricts the jsonl scan to the agent's project transcript dir (`~/.claude/projects/<slug>/`, where slug is `<cwd>` with `/` → `-`). A project-scoped agent no longer fires from chatter in unrelated projects. The worker's per-tick loop iterates by composite key and parses scope/name out of it. |
| 4 | `dist/index.html` | `openHyperAgent(name, cwd?)` and the entire modal call chain (`_hyperModalHTML` / `_hyperBindControls` / `_hyperRefineNow` / `_hyperRollback` / `_hyperHistoryRow`) accept `cwd` and route configure/refine/rollback through the cwd-aware POST shape. Project-agents tab cards gain a per-card ⚡ Hyper / ⚡ ON chip wired to `openHyperAgent(name, cwd)`. |
| 5 | `dist/index.html` | **Sidebar Favorites** — every `.nav-item` exposes a ★/☆ toggle on hover. Toggling persists to `prefs.ui.favoriteTabs` (new) which surfaces above the categorical groups as a sticky "★ 즐겨찾기" block — one click to a frequent tab, no flyout to navigate. |
| 6 | `dist/index.html` | **Sidebar Recent** — `go(id)` writes an MRU list to `localStorage['cc-recent-tabs']` capped at `prefs.ui.recentTabsLimit` (default 5). The "🕒 최근 사용" block renders below favorites. Recent items skip duplicates with favorites so the two sections never repeat the same tab. |
| 7 | `dist/index.html` | **`/` opens Spotlight** — pressing `/` alone (when no input is focused) opens the existing Cmd-K spotlight overlay. The header search input's placeholder reads `검색… ⌘K · /` to advertise the shortcut. |
| 8 | `server/prefs.py` | New `list_str` schema kind — list of ASCII identifier strings, dedup'd, capped (`maxItems`, `maxItemLen`). Used by `ui.favoriteTabs`. Also adds `ui.recentTabsLimit: int (0..20, default 5)`. Schema serialiser exposes `maxItems` / `maxItemLen` so the frontend can render constraints without hard-coding. |
| 9 | `tools/translations_manual_15.py` (new) | KO → EN/ZH for "최근 사용", "즐겨찾기 추가/해제", "검색… ⌘K · /". Bare "즐겨찾기" already shipped in manual_11. `make i18n-refresh` reports 0 missing across 4012 keys × 3 languages. |
| 10 | `scripts/e2e-hyper-projects-and-sidebar.mjs` (new) | Playwright integration smoke: global+project twin separation · list scope/cwd surfacing · POST cwd lookup · rollback path · project modal renders saved objective · favorites persisted+rendered · recent surfaces · `/` opens spotlight. **11/11 checks pass.** |

#### Compatibility / migration
- Existing v2.39.0 entries (flat keys like `"reviewer"`) keep working: read as global, automatically migrated to `global:reviewer` on the next configure/refine/rollback.
- v2.39.0's `/api/hyper-agents/get/<name>` and `/api/hyper-agents/history/<name>` GET routes remain — only used for global lookups.
- All routes / UI controls are additive; no behaviour changes for users who don't enable the new features.

#### Why a sidebar redesign?
v2.40.0 deliberately doesn't reshuffle the 6 categories (60 tabs). Restructuring forces relearning. Instead, **discovery aids** layer on top: users pin the tabs they reach for, recents auto-surface the rest, and `/` is one keystroke to a fuzzy search. The same hierarchy stays; the *path* to it shortens.

#### Verification
- `node scripts/e2e-hyper-projects-and-sidebar.mjs` — **11/11**.
- `node scripts/e2e-hyper-agent.mjs` (v2.39 regression) — **7/7**.
- `node scripts/e2e-quick-settings.mjs` (v2.38 regression) — **6/6**.
- `node scripts/e2e-tabs-smoke.mjs` — **58/58**.

---
## [2.39.0] — 2026-04-27

### ⚡ Hyper Agent — sub-agents that self-refine over time

A new opt-in supervisor that periodically asks a meta-LLM (Opus by default)
to propose surgical refinements to a writeable global agent's **system prompt,
tool list, and description**, given the user's stated objective and recent
transcripts that mentioned the agent. Every iteration is applied atomically
with a `.bak.md` backup, so any refinement is one-click reversible.

| # | Where | What |
|---|---|---|
| 1 | `server/hyper_agent.py` (new, ~530 LoC) | Whitelisted schema, strict per-key validation, atomic JSON persistence at `~/.claude-dashboard-hyper-agents.json`. `apply_proposal()` writes `~/.claude/agents/<name>.md` after copying the prior content to `<name>.<ts>.bak.md`. `refine_agent()` calls `execute_with_assignee()` against a hardened meta-system-prompt that returns a strict JSON proposal `{newSystemPrompt, newTools, newDescription, rationale, scoreBefore, scoreAfter}`. `rollback()` restores from any backup snapshot and is itself reversible. |
| 2 | `server/hyper_agent_worker.py` (new) | 60-second daemon loop. Honours four trigger modes: `manual` (never auto-fires), `interval` (every N hours; parsed from `cronSpec` of shape `"0 */N * * *"`, defaults to 6h), `after_session` (fires when ≥`minSessionsBetween` recent jsonl transcripts mention the agent via `"subagent_type":"<name>"` or `@<name>`), `any` (interval OR after_session). |
| 3 | `server/routes.py` | 7 new routes: `GET /api/hyper-agents/list`, `GET /get/<name>`, `GET /history/<name>`, `POST /toggle`, `/configure`, `/refine-now`, `/rollback`. |
| 4 | `server.py` | Boot order extended with `start_hyper_agent_worker()` after `start_auto_resume()`. |
| 5 | `dist/index.html` | Agent cards in the Agents tab gain a per-agent **⚡ Hyper / ⚡ ON** chip (color reflects enabled state, fed from `/api/hyper-agents/list`). Clicking opens a dedicated modal with: master toggle · objective textarea · refine-target checkboxes (systemPrompt / tools / description) · trigger select · provider select · min-sessions / budget USD inputs · spent counter · Save / Dry-run / Refine-now / Rollback. History timeline below the controls renders one card per iteration with cost, tokens, score before→after, applied targets, rationale, expandable diff viewer, and a per-row Rollback button. |
| 6 | `dist/index.html` | `__noReloadPaths` extended with `/api/hyper-agents/` so modal Save/Refine doesn't trigger `_scheduleAutoReload()` (would close the open modal mid-flight). |
| 7 | `tools/translations_manual_14.py` (new) | KO → EN/ZH for every modal label, hint, button, toast, and confirm. Wired into `tools/translations_manual.py`. `make i18n-refresh` reports 0 missing across 4008 keys × 3 languages. |
| 8 | `scripts/e2e-hyper-agent.mjs` (new) | Playwright smoke: seeds a real `~/.claude/agents/hyper-test.md`, then verifies UI globals · list · configure round-trip · get reflects state · toggle off · modal renders saved objective · refine endpoint responds gracefully. **All 7 checks pass.** |

#### Triggers (4)
- **manual** — never auto-fires; only the "⚡ Refine now" button calls `refine_agent`.
- **interval** — N hours since `lastRefinedAt`. N parsed from `cronSpec` ("0 */N * * *"), defaults to 6h.
- **after_session** — at least `minSessionsBetween` jsonl transcripts modified after `lastRefinedAt` AND mentioning the agent. Up to 5 transcripts get fed back into the meta-LLM as context for the proposal.
- **any** — interval OR after_session.

#### Refine targets (3)
- **systemPrompt** — body of the .md file (most common).
- **tools** — frontmatter `tools` list. Restricted to the existing palette via the meta-LLM rules.
- **description** — frontmatter `description`.

#### Safety
- **Read-only protection**: Hyper Agent only applies to writeable global agents. Builtin (general-purpose / Explore / Plan / statusline-setup) and plugin agents are silently skipped — `_is_writable_agent()` returns false.
- **Atomic backup**: every apply copies `<name>.md` to `<name>.<ts>.bak.md` before rewriting. Rollback uses these.
- **Reversible rollback**: rollback itself snapshots the current state to a fresh backup, so a rollback is also reversible.
- **Budget cap**: `budgetUSD` (default $5) — once `spentUSD ≥ budgetUSD`, refinement is skipped with a clear error in `lastError`.
- **Schema clamp**: enum / int / float / bool / str all validated and clamped on every read AND write. Unknown keys silently dropped.
- **History bounded** at 100 entries per agent (FIFO truncation).
- **Dry-run mode**: "Dry-run preview" button calls the meta-LLM but does not write the file — useful to inspect the proposed diff before committing.

#### Migration / compatibility
- New file `~/.claude-dashboard-hyper-agents.json` is created on first configure.
- `~/.claude/agents/<name>.md` is read/written using the same Claude Code-compatible frontmatter shape (`name`, `description`, `model`, `tools`).
- Override the meta path with env `CLAUDE_DASHBOARD_HYPER_AGENTS=/some/path`.
- All endpoints / routes / UI controls are additive — no existing behaviour changed.

---
## [2.38.0] — 2026-04-27

### ⚡ Quick Settings — per-user prefs drawer (UI · AI · Behavior · Workflow)

A single keyboard-accessible drawer (`⌘,` / `Ctrl+,`) exposes every dashboard
parameter. Values persist server-side at `~/.claude-dashboard-prefs.json`,
boot synchronously on every page load, and apply via body `data-*` attributes
so the rest of the app can react via CSS — no rerender needed.

| # | Where | What |
|---|---|---|
| 1 | `server/prefs.py` (new) | Whitelisted schema with 4 sections (UI · AI · Behavior · Workflow), 33 keys total. Strict validation per key — enum check, int/float clamp, str length cap, bool coerce. Unknown keys silently dropped. Atomic JSON writes via `_safe_write`. |
| 2 | `server/routes.py` | 3 new routes: `GET /api/prefs/get` (returns `{prefs, defaults, schema, savedAt}`), `POST /api/prefs/set` (single-key or batch `patch:` form), `POST /api/prefs/reset` (whole or single-section reset). |
| 3 | `dist/index.html` | Slide-in drawer with section tabs + per-control widgets: toggle (bool), segmented (≤4-choice enum), select (>4-choice enum), range (int/float with live readout), text (str). Reads schema from server — no hard-coded constraints. |
| 4 | `dist/index.html` | CSS overrides driven by body `data-*` attrs: `data-density` (compact/comfortable/spacious), `data-font-size` (small→xlarge), `data-reduced-motion` (animation kill switch), `data-accent` (5 alt accent colors), `data-mascot-hidden`. |
| 5 | `dist/index.html` | Existing `setTheme` / `setLang` are bridged so legacy dropdown toggles also persist to the prefs store (sendBeacon used pre-reload for lang). |
| 6 | `tools/translations_manual_13.py` (new) | Korean → EN/ZH manual overrides for every drawer label, hint, section description. Wired into `tools/translations_manual.py`. |
| 7 | `scripts/e2e-quick-settings.mjs` (new) | Playwright smoke: ⌘,/Esc keyboard, 4 tabs, bool toggle persistence, range slider value, server round-trip. Passes alongside the 58-tab smoke. |

#### Parameters covered (33 total)
- **UI (9):** theme, lang, density, fontSize, reducedMotion, accentColor, sidebarCollapsed, mascotEnabled, compactSidebar
- **AI (9):** defaultProvider, effort, temperature, topP, maxOutputTokens, thinkingBudget, extendedThinking, streamResponses, fallbackChain
- **Behavior (9):** autoResume, notifySlack, notifyDiscord, telemetryRefresh, confirmSpawn, autosaveWorkflows, liveTickerSeconds, soundOnComplete, openLastTab
- **Workflow (6):** defaultIterations, defaultRepeatDelaySec, dryRunByDefault, showMinimap, snapToGrid, gridSize

#### Why
The dashboard had ~30 user-tunable knobs scattered across modal dialogs, settings page, and localStorage. v2.38 centralises them behind one keyboard shortcut so a user can flip effort to high, lower autoResume polling, switch accent to purple, and turn the mascot off without leaving the current tab.

#### Migration / compatibility
- New file `~/.claude-dashboard-prefs.json` is created on first write — defaults are derived from `DEFAULT_PREFS` until then.
- Existing `cc-theme` / `cc-lang` localStorage / cookie remain authoritative for the boot path so no flash of wrong theme/lang on reload.
- Override the path with env `CLAUDE_DASHBOARD_PREFS=/some/path`.

### 🩹 Hotfix — Crew Wizard preview wiped form state (pre-existing bug)

While shipping v2.38.0, a long-standing bug was discovered: the global `api()`
helper auto-fires `_scheduleAutoReload()` after every successful POST that
isn't on the `__noReloadPaths` allow-list, then `renderView()` re-runs and
nukes the in-memory `__cw.form` state. Symptom: clicking 미리보기 in the
Crew Wizard loaded for ~1s then snapped back to an empty form.

`__noReloadPaths` was extended (`dist/index.html:1373-1382`):
- `/api/wizard/` — preview / create
- `/api/slack/` — slack config save / test (called inside the wizard step 3)
- `/api/obsidian/` — obsidian vault test
- `/api/prefs/` — Quick Settings (precautionary; would close the drawer otherwise)

Verification: scripted Crew Wizard flow (project + goal → click 미리보기) →
**0 reloads, form state preserved, preview rendered** (9 nodes · 10 edges · 3 cycles).

---
## [2.37.1] — 2026-04-27

### ✨ Auto-Resume v2.37 follow-on — CLI watch · Haiku snapshot · scheduled-tasks · live ticker

Five quality-of-life additions on top of v2.37.0:

| # | Where | What |
|---|---|---|
| 1 | `server/auto_resume_cli.py` | New `watch` subcommand — foreground supervisor: prints one status line every `--refresh` seconds, cancels cleanly on SIGINT, exits 0 on `done` / non-zero on `failed`/`exhausted`. No HTTP server needed. |
| 2 | `server/auto_resume_hooks.py` | New `SNAPSHOT_SH_BODY_HAIKU` template + `install(cwd, *, use_haiku_summary=True)` flag. Stop-hook now optionally pipes the jsonl tail through `claude --print --model haiku-4.5 --bare` for a tight ≤12-bullet "where you left off" markdown brief — falls back to raw tail if Haiku unavailable. |
| 3 | `server/auto_resume.py` | `useHaikuSummary` field forwarded from `api_auto_resume_set` and `api_auto_resume_install_hooks` to the hook installer. |
| 4 | `dist/index.html` | Live 1-second countdown ticker for the "다음 시도까지 Ns" chip — surgical DOM rewrite, no extra fetch. Full status re-fetch still on the existing 5-second cadence. |
| 5 | `server/system.py` | `/api/scheduled-tasks/list` now exposes an `autoResume` array of active worker entries so a future timeline view can stitch the two together. |

#### Verification

- Backend unit: hooks Haiku variant install/uninstall round-trip · default variant unchanged · CLI `--help` advertises `watch` · `api_scheduled_tasks` returns `autoResume` key.
- `npm run test:e2e:auto-resume` — 3/3 viewports PASS.
- `npm run test:e2e:smoke` — 58/58 tabs PASS, no regression.

#### Backwards compatibility

- `install(cwd)` signature is `install(cwd, *, use_haiku_summary=False)` — old callers see no change.
- `useHaikuSummary` is opt-in; default snapshot template is identical to v2.37.0.
- `/api/scheduled-tasks/list` still returns `tasks` and `dirExists` exactly as before; `autoResume` is additive.

---
## [2.37.0] — 2026-04-27

### ✨ Auto-Resume — inject a self-healing retry loop into a live Claude Code session

Open a session detail in the dashboard, click **🔄 Auto-Resume 주입**, and a
background worker now watches that session's transcript. When it gets killed
by a token / rate-limit, the worker spawns `claude --resume <id> -p "<prompt>"`
in the session's cwd — exactly like the user-supplied reference shell while-loop:

```bash
while true; do
  claude "$@"
  [[ $? -eq 0 ]] && break
  sleep 300
done
```

…but with seven extra mechanisms baked in:

| # | Mechanism | Where |
|---|---|---|
| 1 | **Exit-reason classification** — `rate_limit` / `context_full` / `auth_expired` / `clean` / `unknown` via stderr+stdout+jsonl-tail regex | `server/auto_resume.py::_classify_exit` |
| 2 | **Precise reset-time parsing** — `"resets at 11:30am"`, `"in 30 minutes"`, `"after 2 hours"` → exact next-attempt epoch_ms | `server/auto_resume.py::_parse_reset_time` |
| 3 | **Stop-hook progress snapshot** — every Claude response writes `<cwd>/.claude/auto-resume/snapshot.md` so we always have the latest state on disk | `server/auto_resume_hooks.py::install` |
| 4 | **SessionStart-hook injection** — resumed session gets the snapshot piped into context automatically (Claude Code's SessionStart-hook stdout contract) | `server/auto_resume_hooks.py::install` |
| 5 | **External wrapper restart loop** — supervisor classifies → waits → re-spawns; `--resume <id>` by default, `--continue` toggle available | `server/auto_resume.py::_process_one` |
| 6 | **Loop guards** — `maxAttempts` (default 12), exponential backoff (1m→2m→4m→8m→16m→30m cap) for `unknown`, snapshot-hash stall detect (3× identical halts the loop) | `server/auto_resume.py::_exponential_backoff`, `_push_hash_and_check_stall` |
| 7 | **Observable state file** — `~/.claude-dashboard-auto-resume.json` with `running`/`waiting`/`watching`/`done`/`failed`/`exhausted`/`stopped`/`error` state per session | `server/auto_resume.py::_dump_all` |

#### What's new

- **New module**: `server/auto_resume.py` (worker + state machine + classifier + parser + backoff + stall detect)
- **New module**: `server/auto_resume_hooks.py` (per-project Stop+SessionStart hook installer with backup + idempotent re-install + clean uninstall)
- **New endpoints** (all under `/api/auto_resume/`): `set`, `cancel`, `get`, `status`, `install_hooks`, `uninstall_hooks`, `hook_status`
- **New panel**: in the session-detail modal, with state chip, exit-reason chip, attempts/max progress bar, next-attempt countdown, snapshot preview, hook install/remove buttons, advanced settings (prompt, poll, idle, maxAttempts, --continue mode, install hooks)
- **Sessions list** now shows a `🔄 AR` badge on every session with an active binding
- **i18n**: 41 new keys in `ko/en/zh` (translations_manual_12.py)

#### Verification

- `npm run test:e2e:auto-resume` — 5 consecutive runs, 3 viewports each (375x667 / 768x800 / 1280x800) — **15/15 PASS**
- `npm run test:e2e:smoke` — **58/58 tabs PASS** (no regression)
- Backend unit tests cover all 7 mechanisms; round-trip of hook install/uninstall verified in tmp sandbox

#### Safety

- Default OFF; opt-in per session
- Never auto-injects `--dangerously-skip-permissions`
- Hook installation is project-local only; `~/.claude/settings.json` (global) is **never** touched
- Settings.json backup written to `<cwd>/.claude/settings.json.auto-resume.bak` before first mutation
- Cancel + uninstall are idempotent and reversible

---
## [2.36.3] — 2026-04-26

### 🩹 Project snapshot modal — scroll fix

User reported the project snapshot modal (Projects tab → click a project
card) wouldn't scroll to the bottom. Symptom: middle and lower content
was clipped, the inner `overflow-y-auto` region behaved as if its
height was zero.

#### Root cause
The modal is a flex-column with `max-height: 92vh` and `overflow:
hidden`. Inside it sat (in order):

1. Header `<div class="p-5 border-b ...">` — could be tall when chips
   wrapped over multiple rows.
2. `<div id="aiRecSlot">` — empty by default but balloons after the AI
   recommend button is pressed.
3. `<div id="projectAgentsSlot">` — populated after lazy load.
4. The body `<div class="flex-1 overflow-y-auto p-5 grid ...">`.

None of regions 1–3 had `flex-shrink-0`, and the body was missing
`min-h-0`. With even a moderately long aiRec result the body's flex
share got pushed below zero and `overflow-y-auto` silently stopped
scrolling (the children rendered at their natural height past the
modal edge but the scrollbar was attached to a 0-px container).

#### Fixes
- Header gets `flex-shrink-0` so it never compresses.
- A new `<div id="projectSnapshotBody" class="flex-1 min-h-0
  overflow-y-auto" style="overscroll-behavior: contain;">` wraps the
  three formerly-separate regions (`aiRecSlot`, `projectAgentsSlot`,
  the grid). Now the modal has exactly two flex children — header and
  body — and the body owns a single, predictable scroll container.
- The grid's two columns get `min-w-0` so wide content (long file
  paths, raw JSON dumps) wraps inside the cell instead of forcing the
  whole grid wider than the modal.
- `scrollToSessions()` now scrolls inside `#projectSnapshotBody`
  rather than calling `scrollIntoView()` on the page (which was
  scrolling the viewport behind the modal).
- Modal opens with `{ wide: true }` so the two columns have room on
  desktop.

#### Verification
- Playwright opens the modal, measures the body container:
  `clientHeight=625, scrollHeight=1062` (was effectively 0 on the bug
  path), `overflowY=auto`, `canScroll=true`.
- After `body.scrollTop = body.scrollHeight`, the bottom-of-content
  invariant `scrollTop + clientHeight ≈ scrollHeight` holds within
  4 px — the section history table at the bottom is now reachable.
- 0 console errors.

---
## [2.36.2] — 2026-04-26

### 🔄 Server-restart detector — auto-banner when the user is on a stale build

User reported v2.36.1 features (OMC/OMX cards, ECC discovery fix) **still
weren't visible** after the release. The code was correct on disk and on
`origin/main`, but the user's running server was still v2.35.x — the
`git pull` happened without restarting `python3 server.py`. The browser
was also caching the previous `index.html` despite `Cache-Control:
no-store`.

The dashboard had no way to surface this. v2.36.2 makes it self-healing:

#### Backend (`server/version.py`)
- Capture `_SERVER_STARTED_AT_MS = int(time.time() * 1000)` at module
  import. The value never changes for the life of the process.
- `/api/version` now returns `{version, changelog, serverStartedAt}`.

#### Frontend (`dist/index.html`)
- On first load, the dashboard remembers `__bootedAt = {version,
  serverStartedAt}` from the first `/api/version` call.
- A 60-second poll (`_scheduleVersionPoll`) compares the current
  `/api/version` response to the booted snapshot.
- Mismatch on either field pops a sticky bottom-of-screen banner with
  two buttons — **Reload now** (`location.reload()`) and **Later**
  (dismiss). The banner uses the gradient `--accent → purple` so it's
  visually unmistakable.

#### Why this also catches the cache-bust case

Even when the user's `git pull` is correct, browsers occasionally cache
the inline-everything `dist/index.html`. As long as they restart the
server, the version-mismatch banner fires within 60 s and offers a
one-click hard-reload. In the rare case where neither version nor PID
changed (server still running an old build), the user sees no banner —
which is correct, because in that case there really is nothing new.

### Verification

- `make i18n-refresh` + `scripts/verify-translations.js` — all 4 stages
  pass: 3,845 keys × 3 locales matched, 1,107 `t()` Korean call sites
  covered, 0 Korean residue.
- Live HTTP — `/api/version` returns the new `serverStartedAt` field;
  consecutive calls within the same process return the same value
  (1777200287684 → 1777200287684). Restarting the process produces a
  larger value, exactly the trigger the polling code looks for.

### What this means for the v2.36.1 issue

The user sees nothing **new** until they reload. After they reload once
(per the diagnosis), every subsequent server restart is auto-detected
within 60 s. The "I deployed but the user is on the old build" failure
mode is now self-correcting.

---
## [2.36.1] — 2026-04-26

### 🩹 Run Center didn't see ECC after install + Guide had no OMC/OMX card

User reported two related gaps after v2.36.0:

1. **"Guide & Tools에 OMC OMX가 없어. 어떻게 써?"** — Run Center had OMC/OMX cards but Guide & Tools only had ECC. Users couldn't tell where they came from or whether anything needed installing.
2. **"ECC 설치했는데 런센터에 안나와."** — After installing ECC from Guide & Tools, Run Center still showed 0 ECC items. Root cause: I scanned only `~/.claude/plugins/cache/ecc/ecc/` but `toolkits.py` installs as `everything-claude-code@everything-claude-code`, which lives at `~/.claude/plugins/cache/everything-claude-code/everything-claude-code/`. **My initial "181 + 79" verification was on my own machine where both ids happened to coexist; I didn't recognise the path-name dependency until the user surfaced it.**

#### Fixes

**Run Center backend (`server/run_center.py`)**
- Replaced single-root resolution with `_ecc_roots()` returning every detected install: (1) `installed_plugins.json` entries for `ecc@ecc` **and** `everything-claude-code@everything-claude-code` (authoritative), (2) cache glob over both package names, (3) marketplaces fallback. Items are deduped across roots.
- `_build_catalog()` now returns `(items, debug)` and the catalog API exposes that `debug` blob with per-root scan counts.
- Added `?refresh=1` query param to bust the 30 s cache so a freshly installed ECC shows up immediately.

**Run Center UI (`dist/index.html`)**
- New info banner at the top of the tab explaining where ECC / OMC / OMX come from and that OMC/OMX need no separate install.
- Manual `🔄` refresh button next to the search input.
- Sidebar ECC status now distinguishes 3 states with deep diagnostics:
  - ✓ ECC installed — shows skill + command counts.
  - ⚠ Path found but 0 items — collapsible JSON of every scanned root.
  - ✗ ECC not installed — link to Guide & Tools + scanned-paths diagnostic.

**Guide & Tools (`server/guide.py`)**
- Two new toolkit cards: `oh-my-claudecode` (OMC) and `oh-my-codex` (OMX). Each card explains:
  - What's already absorbed by LazyClaude (no install needed).
  - When the external CLI is still useful (in-session slash commands).
  - The npm install command if the user wants the external CLI anyway.
  - Which features are in LazyClaude only vs CLI only.

#### Verification

- `make i18n-refresh` + `scripts/verify-translations.js` — all 4 stages pass: 3,841 keys × 3 locales matched, 1,103 `t()` Korean call sites covered, 0 Korean residue.
- Live HTTP — `/api/run/catalog` returns 270 items (262 ECC + 4 OMC + 4 OMX) on a machine with both `ecc@ecc` and `everything-claude-code@everything-claude-code` installed; debug blob lists 4 roots with per-root counts.
- `/api/guide/toolkit` returns 5 toolkit cards (was 3): everything-claude-code, claude-code-best-practice, **oh-my-claudecode**, **oh-my-codex**, wikidocs-claude-code-guide.

#### What I got wrong in v2.36.0

The "181 skills + 79 slash commands" headline was true on my dev box. I should have flagged that it depends on which ECC plugin id was installed, and I should have run `_ecc_root()` against an environment that only had the `everything-claude-code` id (which is what most users get from the dashboard installer). Future audits will trace `installed_plugins.json` first, not glob the cache directly.

---
## [2.36.0] — 2026-04-26

### 🎯 Run Center + Workflow Quick Actions + Commands tab Run buttons

User asked for ECC, OMC, OMX features to be runnable directly from the
dashboard rather than only inside Claude Code sessions. Three additions
land here, all wired to the existing `execute_with_assignee` pipeline so
any provider (Claude / OpenAI / Gemini / Ollama) can serve the request.

#### 1. Run Center — new tab `runCenter` (Build group)

A unified search-and-run catalog over **268 entries** (verified against an
ECC v1.10 install):

- **ECC** — 181 skills + 79 slash commands, scanned from
  `~/.claude/plugins/cache/ecc/<version>/{skills,commands}/`. Every
  entry's frontmatter is parsed (`name` / `description` / `tools`) and
  auto-categorised (frontend / backend / testing / review / security /
  ops / ai / data / ml / mobile / general).
- **OMC** — 4 modes (`/autopilot` / `/ralph` / `/ultrawork` /
  `/deep-interview`). Each links to its matching `bt-*` built-in
  template so the user can hand off to a full workflow with one click.
- **OMX** — 4 commands (`$doctor` / `$wiki` / `$hud` / `$tasks`)
  exposed as one-shot prompts.

Surface:
- Left column — 5 source filters (All / ECC / OMC / OMX / Favorites)
  with live counts, 6 kind filters, category chips, ECC install status
  badge with deep-link to Guide & Tools.
- Top bar — search by name / description / category, total count.
- ⭐ Favorite row — first 8 favorited items as compact cards.
- Card grid — paginated at 200 cards for performance.
- Click a card → modal with goal input, model picker (uses existing
  `_wfAssigneeOptions` so Claude / GPT / Gemini / Ollama appear),
  timeout slider. Run executes through `execute_with_assignee` and
  reports tokens / cost / duration. "Save as prompt" pushes the result
  into the Prompt Library; "Convert to workflow" hands off either to
  the matching built-in template (OMC) or scaffolds a 1-node workflow
  (ECC) and switches to the Workflows tab.

Backend (`server/run_center.py`, ~480 lines):
- `GET  /api/run/catalog?source=&kind=&q=` — filterable, 30 s cached.
- `POST /api/run/execute` — synchronous, time-bounded one-shot.
- `GET  /api/run/history?limit=` — runs sorted by recency.
- `GET  /api/run/history/get?id=` — full row including output / error.
- `POST /api/run/favorite/toggle` — persisted to
  `~/.claude-dashboard-run-favorites.json`.
- `POST /api/run/to-workflow` — return template id (OMC) or draft DAG
  (ECC) for the Workflows tab to consume.
- New SQLite table `run_history` (idempotent migration).

#### 2. Workflow Quick Actions (Workflows tab header)

A row of 4 buttons above the workflow stats panel: 🚀 Autopilot / 🔁
Ralph / 🤝 Ultrawork / 🧐 Deep Interview. Click → modal asks for the
goal in one line → loads the matching `bt-*` template via
`/api/workflows/templates/<id>`, injects the user's goal into the
planner node's `description`, saves a new workflow with the goal
truncated into the name, navigates the canvas to it, and auto-runs.
Goes from "I want autopilot on this idea" to a running DAG in two
clicks.

#### 3. Commands tab — Run buttons + ECC tagging

Each card in the existing Commands tab now shows:
- An `ECC` chip when the command's path is under
  `~/.claude/plugins/cache/ecc/` (heuristic — also matches `scope ===
  'plugin'` for backwards compat).
- A `▶ Run` button. ECC commands route through the Run Center modal
  (full execution context). Non-ECC commands scaffold a 1-node
  workflow and open it in the Workflows tab — they don't have the
  rich invocation copy that ECC frontmatter provides, so a
  user-editable workflow is safer than a blind dispatch.

#### Files

- `server/run_center.py` (new, +480) — catalog, executor, history,
  favorites, to-workflow handoff.
- `server/routes.py` (+8) — three GET + three POST routes registered.
- `dist/index.html` (+~530) — Run Center view (tab, sidebar filters,
  card grid, modal), Workflow Quick Actions header + handler,
  Commands tab Run buttons + handler, all CSS.
- `tools/translations_manual_11.py` (new, ~80 keys × EN / ZH).
- `tools/translations_manual.py` — wires `_NEW_EN_11` / `_NEW_ZH_11`.

#### Verification

- `make i18n-refresh` + `scripts/verify-translations.js` — all 4 stages
  pass: 3,861 keys × 3 locales matched, 1,091 `t()` Korean call sites
  covered, audit covered, static DOM covered, 0 Korean residue.
- Live HTTP — `/api/run/catalog` returns 268 items with the expected
  4-source split (260 ECC + 4 OMC + 4 OMX), filters work, favorite
  toggle round-trips, `/api/run/to-workflow` resolves OMC →
  `bt-autopilot` and ECC → 1-node draft.
- Playwright e2e — Run Center renders 201 cards (cap 200 + 1 favorite
  row card) with 11 filters and 12 category chips, OMC filter narrows
  to 5 cards, card click opens the goal modal with the model picker
  and "/autopilot" title, Workflows tab shows all 4 Quick Action
  buttons, Commands tab gets 600 Run buttons + 600 ECC chips, 0
  console errors.

---
## [2.35.1] — 2026-04-26

### 🌐 i18n hotfix — 18 missing translations caught by CI

The v2.34.2 release missed 18 English/Chinese keys. The previous
`build_locales.py` missing-detector only flagged keys whose value still
contained Korean — it didn't enforce **exact-match between every
`t('…')` call site and the locale dictionary**, which is what the
canonical `scripts/verify-translations.js` checks. CI failed on the 4-stage
verifier with `t() 인자 번역 누락: en=18, zh=18`.

The 18 keys fell into three buckets:

1. **Multi-sentence strings** that the audit extractor truncates at the
   first period. The runtime calls `t()` with the full string but the
   dictionary only had each sentence separately. Examples:
   - `Slack Bot Token (xoxb-…) 이 필요합니다. https://api.slack.com/apps 에서 봇을 만들고 chat:write, reactions:read, channels:history 권한을 부여하세요.`
   - `Projects/<프로젝트>/logs/YYYY-MM-DD.md 에 사이클별로 append 됩니다. $HOME 하위만 허용.`
   - The full Crew Wizard "이게 뭐죠?" answer in the guide modal.
2. **Trailing-colon prefixes** used like `t('Slack 실패: ') + err`:
   `Slack 실패: ` / `Obsidian 쓰기 성공: ` / `Obsidian 실패: ` /
   `생성 실패: ` / `오류: `.
3. **Strings with embedded double quotes** that JSON-escape as `\"`:
   the Slack approval reply keyword sentences and two gotcha-tip lines
   starting with `"slack token not configured"` / `"vault path must
   resolve under $HOME"`.

**Fixes**
- `tools/translations_manual_10.py` — added all 18 keys with their
  exact full-string form (Python's mixed quote syntax + raw Korean +
  embedded double quotes).
- For Slack approval reply keywords, the EN/ZH translations now show
  only the language-appropriate keywords (`approve` / `ok` /
  `reject`). The KO source still lists `"승인"` / `"거부"` because
  the backend `wait_for_approval()` recognises both. Removing the
  Korean keyword strings from EN/ZH avoids the runtime KO-residue
  scanner flagging legitimate translations.

**Verification**
- `make i18n-refresh` — 0 한글 잔존 (was 6).
- `scripts/verify-translations.js` 4 stages — all pass: 3,763 keys
  matched across ko/en/zh, all 1,042 `t()` Korean call sites covered,
  audit covered, static DOM covered.

### Why this slipped past v2.34.2

I relied on `build_locales.py`'s loose missing-detector and never ran
`scripts/verify-translations.js`. The two tools answer different
questions: the former asks "are translations stored?", the latter asks
"are they reachable from every call site?". CI runs the latter and
caught the gap. Going forward, `make i18n-refresh` (which already
chains both) is the single source of truth before committing any new
`t('…')` strings.

---
## [2.35.0] — 2026-04-26

### 📦 Install LazyClaude as a real app (PWA + macOS .app bundle)

LazyClaude can now be installed as an app, both ways:

#### Option A — PWA (cross-platform: macOS / Windows / Linux / iOS / Android)

Open LazyClaude in any modern browser → click the install icon in the
URL bar (Chrome/Edge) or **Share → Add to Home Screen** (Safari iOS).
The dashboard launches in its own window with no browser chrome, has a
Dock/taskbar icon, and registers shortcuts (Workflows / Crew Wizard /
AI Providers) in the right-click context menu.

- `dist/manifest.json` — `display: standalone`, `display_override`
  fallback chain (`window-controls-overlay` → `standalone` →
  `minimal-ui`), 3 launch shortcuts.
- 4 PNG icons (192 / 512 / 512 maskable / 180 apple-touch) generated
  from `docs/logo/mascot.svg` via Playwright. Maskable variant uses a
  dark background so the orange mascot survives Android's adaptive
  icon mask.
- `apple-mobile-web-app-capable`, `theme-color` (dark + light media
  queries), `og:title` / `og:image` / `og:description` for previews.

#### Option B — macOS .app bundle (Spotlight-searchable, Dock-pinnable)

```bash
make install-mac     # builds + copies LazyClaude.app to /Applications/
```

Double-click in Finder, or open via Spotlight (`⌘Space → LazyClaude`).
The launcher:

1. Resolves the project directory: `$LAZYCLAUDE_HOME` env > `~/Lazyclaude`
   > `~/lazyclaude`. Shows a friendly dialog if none found.
2. Confirms `python3` is available.
3. Reuses an already-running server on port 8080 if one is up.
4. Otherwise starts `python3 server.py` in the background, logging to
   `~/Library/Logs/LazyClaude/server.log`.
5. Opens `http://127.0.0.1:8080` in the default browser.
6. Forwards Quit / SIGTERM to the server so it shuts down cleanly.

The bundle is **72 KB total** — no Python interpreter, no Electron, no
Node runtime. It depends on the system `python3`, matching LazyClaude's
stdlib-only philosophy.

#### New Make targets

| Target | What it does |
|---|---|
| `make pwa-icons` | regenerate PWA PNG icons from `docs/logo/mascot.svg` |
| `make app` | build `dist/LazyClaude.app` |
| `make install-mac` | build + copy to `/Applications/` (replaces existing) |
| `make uninstall-mac` | remove `/Applications/LazyClaude.app` |

#### Files

- `dist/manifest.json` (new)
- `dist/icons/{icon-192, icon-512, icon-maskable-512, apple-touch-180}.png` (new)
- `dist/favicon.svg` + `dist/favicon-32.png` (new)
- `dist/index.html` — PWA `<head>` block (manifest + theme-color + apple-* + og:*)
- `tools/build_pwa_icons.mjs` (new) — Playwright-driven SVG → PNG renderer
- `tools/build_macos_app.sh` (new) — bundle builder using `sips` + `iconutil`
- `Makefile` — new targets

#### Verification

- Playwright PWA check — manifest parsed, all 4 icons + favicons load,
  no failed responses, theme-color and apple-* meta tags present.
- `.app` launcher — runtime simulation: server starts, `/api/version`
  responds, log file created at `~/Library/Logs/LazyClaude/server.log`,
  SIGTERM cleanly shuts the server down.

---
## [2.34.3] — 2026-04-26

### 🚨 Mobile sidebar overlay — second pass

The fix in v2.34.1 was insufficient. User reported (with a 670×720
screenshot, English locale) that the page content was still readable
through the dark-theme backdrop — `Documentation` button, the `57`
optimization score, the green `100` progress bars and labels were all
clearly visible behind the open sidebar.

Reproduced with Playwright at the same viewport. Two failures of the
v2.34.1 attempt:

1. `rgba(0,0,0,0.78)` + `blur(2px)` is too weak on a dark theme — the
   page text is mostly white/grey on near-black, and 78% black-on-black
   barely changes contrast.
2. `min(320px, 92vw)` left ~350 px of content visible to the right of
   the sidebar at 670 px viewport width — and that's the part the
   backdrop has to do all the work for.

**Fixes**
- Sidebar full-width (`100vw`) under **720 px** (was 480 px). 720 px
  covers tablet portrait, narrow desktop windows, and the user's actual
  viewport — content exposure is now 0 %.
- Sidebar widened from `min(320px, 92vw)` to `min(360px, 92vw)` for the
  720–900 px range.
- Backdrop alpha 0.78 → **0.92** (dark) / 0.85 (light) with
  `backdrop-filter: blur(10px) saturate(0.6)` — what little leaks past
  the wider sidebar is heavily blurred and desaturated, no longer
  readable.
- Light theme switched from a transparent black overlay to a translucent
  white overlay — better visual hierarchy on a light background.

**Verification**
- Playwright at 670×720 — sidebar is now `100vw`; content exposure 0 %.
- Playwright at 850×720 — sidebar 360 px; right pane is heavily blurred
  near-black, content unreadable.

---
## [2.34.2] — 2026-04-26

### 🌐 EN / ZH translations for v2.34 features

The Korean strings introduced in v2.34.0 / v2.34.1 were missing from the
EN and ZH locales — English and Chinese users saw raw Korean in the Crew
Wizard, palette categories, and node inspectors.

**Changes**
- New `tools/translations_manual_10.py` — ~210 EN + ZH entries covering
  the Crew Wizard, palette categories, `slack_approval` / `obsidian_log`
  node inspectors, the guide modal, and multi-sentence `WF_NODE_TYPES`
  descriptions (the audit extractor only captures the first sentence).
- `tools/translations_manual.py` — wires up `_NEW_EN_10` / `_NEW_ZH_10`.
- `dist/locales/{en,zh,ko}.json` regenerated; Missing EN/ZH = 0.
- `dist/index.html` — `_wfPickNodeType()` now wraps the auto-filled node
  title with `t()` so EN/ZH users see "Start" instead of "시작".

**Palette category labels**
| KO | EN | ZH |
|---|---|---|
| 트리거 | Trigger | 触发器 |
| AI 작업 | AI work | AI 工作 |
| 흐름 제어 | Flow control | 流程控制 |
| 데이터 / HTTP | Data / HTTP | 数据 / HTTP |
| 연동 | Integrations | 集成 |
| 출력 | Output | 输出 |

**Verification**
- `python3 build_locales.py` — Missing EN/ZH = 0.
- Playwright QA across en / zh / ko cookies — Crew Wizard 4 steps + guide
  modal + palette accordion + slack_approval / obsidian_log row picks.
  Korean leak count: EN 0, ZH 2 (pre-existing header CLI status indicator,
  unrelated to v2.34).

---
## [2.34.1] — 2026-04-26

### 🚨 Mobile sidebar backdrop + n8n-style palette + wizard guide

#### 1. Small-screen sidebar overlay (urgent)

User reported (with a 670×720 screenshot) that opening a sidebar category
on a small viewport leaked the page content through the sidebar with a
"weird pink pixel" floating at the corner. Reproduced with Playwright;
four root causes:

1. `body.sidebar-open::after` backdrop was `rgba(0,0,0,0.5)` — too weak
   on the dark theme so the page text was clearly readable.
2. No body scroll lock — content scrolled behind the open sidebar.
3. `#claudeMascot` (z-index 1150), `#chatBubble`, `#chatLauncher` floated
   above the z=35 backdrop — surfacing as the "pink pixel" the user saw.
4. Sidebar width `min(300px, 85vw)` left ~370 px of content visible on a
   670 px viewport.

**Fixes**
- Backdrop alpha 0.5 → 0.78 (dark) / 0.45 (light) + `backdrop-filter: blur(2px)`.
- `body.sidebar-open { overflow: hidden }` to lock body scroll.
- Sidebar widened to `min(320px, 92vw)`; **full `100vw` under 480 px** (no
  background bleed on narrow screens).
- Floating `#claudeMascot` / `#chatBubble` / `#chatLauncher` force-hidden
  while the sidebar is open.

#### 2. Workflow node palette redesigned to n8n-style accordion

User feedback: "too many icons, blocks too big". The 18 node types in a
3-column grid of large blocks were replaced with a **6-category × compact
row accordion**. One category open at a time. Click a category header →
expand a list of compact rows (icon + label + truncated description) →
click a row → detailed form (Zapier / n8n flow).

| Category | Nodes |
|---|---|
| 🚀 Trigger | `start` |
| 🤖 AI work | `session`, `subagent`, `embedding` |
| 🔁 Flow control | `branch`, `loop`, `retry`, `error_handler`, `merge`, `delay`, `aggregate` |
| 🔧 Data / HTTP | `http`, `transform`, `variable`, `subworkflow` |
| 🔗 Integrations | `slack_approval`, `obsidian_log` |
| 📤 Output | `output` |

- The currently selected node's category auto-opens and is highlighted.
- Open-category state is persisted per-editor in `localStorage`.
- The new `slack_approval` and `obsidian_log` nodes also got proper
  default data on selection (`channel`, `vaultPath`, `passThrough`, …) —
  previously they started with an empty data object.

#### 3. Crew Wizard usage guide

A `📖 Show how it works` button plus a first-visit auto-open modal (gated
by `cwGuideSeen` in `localStorage`). Six sections:

1. What is this? — wizard's purpose.
2. Generated structure — ASCII diagram.
3. 4-step guide — input explained step-by-step.
4. Slack interaction — ✅/❌ reactions and reply keyword mapping.
5. Common gotchas — token not configured, vault path, bot channel
   invitation, etc.
6. After generation — canvas editing, Webhook, live monitoring.

**Files**
- `dist/index.html` — backdrop/sidebar CSS, palette accordion
  (`WF_NODE_CATEGORIES`, `_wfPaletteToggleCat`, `.wf-palette` CSS), wizard
  guide modal (`_cwShowGuide`).

**Verification**
- Playwright on viewports 670×720 and 420×720 — backdrop + mascot hidden
  + scroll lock confirmed.
- Palette renders 6 categories × 18 rows; single-open behaviour holds; a
  row click triggers default data + form render.
- Wizard auto-guide on first visit + manual `📖` button both work.

---
## [2.34.0] — 2026-04-26

### 🧑‍✈️ Crew Wizard + Slack approval gate + Obsidian logging

Two-pronged response to the "the workflow editor is too complex"
feedback:

1. **New Crew Wizard tab (`crewWizard`)** — a Zapier-style 4-step form
   that scaffolds a planner + N personas + Slack admin gate + Obsidian
   log workflow in one click. The output is a regular workflow editable
   in the canvas.
2. **The Workflows tab stays the n8n-style advanced surface** — two new
   node types are exposed in the palette and inspector.

**New modules**
- `server/slack_api.py` — Slack Web API client (Bot Token `xoxb-*`):
  `chat.postMessage`, `conversations.replies`, `reactions.get`,
  `auth.test`. Token saved to `~/.claude-dashboard-slack.json` with
  chmod 600.
- `server/obsidian_log.py` — markdown appender writing to
  `<vault>/Projects/<project>/logs/YYYY-MM-DD.md`. `$HOME`-only with
  `realpath` for path-traversal defence.
- `server/crew_wizard.py` — form → DAG builder. Three autonomy modes:
  `admin_gate` / `autonomous` / `no_slack`.

**New workflow nodes**
- `slack_approval` — posts to a Slack channel and polls for ✅/❌
  reactions or thread replies. On timeout one of `approve | reject |
  abort | default`. A free-form reply is used as the next cycle's input
  so the admin can steer mid-flight.
- `obsidian_log` — appends each cycle's report. In pass-through mode the
  input flows on to the next node unchanged.

**New built-in template**
- `bt-crew` (Persona Crew) — Planner (Opus) → 3 personas (Claude / Gemini
  / Ollama mix) → Aggregate → SlackApproval → ObsidianLog → Output, with
  a 3-cycle loop.

**New endpoints**
- `GET  /api/slack/config` — returns only a redacted token hint.
- `POST /api/slack/config/save` — `auth.test` then persist.
- `POST /api/slack/config/clear`
- `POST /api/slack/test`            — send a test message to a channel.
- `POST /api/obsidian/test`         — try writing to the vault.
- `POST /api/wizard/crew/preview`   — build but do not save.
- `POST /api/wizard/crew/create`    — build + save + return wfId.

**Files**
- `server/slack_api.py` (+283)
- `server/obsidian_log.py` (+118)
- `server/crew_wizard.py` (+260)
- `server/workflows.py` (+~190 — two node types' sanitize/executor +
  `bt-crew` template)
- `server/routes.py` (+11 — route registration)
- `dist/index.html` (+~430 — Wizard view 4-step form + inspector +
  palette)

**Security**
- Slack token: env var `SLACK_BOT_TOKEN` > file. Responses expose only a
  redacted hint like `xoxb-1234... ABCD`.
- Slack API calls are restricted to host `slack.com` over HTTPS; token
  format validated by `^xox[bp]-...` regex.
- Obsidian vault path: `realpath`-checked under `$HOME` only; project
  name validated against `[A-Za-z0-9 _\-./]{1,80}` regex.

---
## [2.33.3] — 2026-04-24

### 🎨 Light theme WCAG AA contrast audit

Playwright 기반 contrast sweep 스크립트(`scripts/e2e-light-contrast.mjs`) 신규 — 58 탭을 light 테마로 순회하며 text/bg pair 를 relative luminance 로 측정, WCAG AA 4.5:1 미달 요소를 path · fg · bg · fontSize 와 함께 수집.

**초기 측정**
- `rgb(136,136,146) #888892` (light --text-dim) 414 건, ratio 2.85-3.51
- `rgb(217,119,87)` accent orange 10 건, ratio 3.12
- `rgb(167,139,250)` / `rgb(251,191,36)` 등 pastel 색상 30+ 건

**수정**
1. light 테마 CSS 변수 강화: `--text-dim #888892 → #5a5a62` · `--text-mute → #3f3f46` · `--accent → #9e4422`.
2. Tailwind arbitrary color (`text-[#c4b5fd]` 등) 클래스 셀렉터로 9 색 배치 override.
3. inline `style="color:#XXX"` 패턴을 attribute selector (`[style*="color:#fbbf24"]`) 로 추가 오버라이드 9 색.
4. `.pulse-dot` 녹색을 `#15803d` 로 강화.

**결과**
- Strict AA (4.5:1): 819 → 87 건 (89% 감소). 남은 대부분 `rgb(21,128,61)` on `chip-ok` 배경 — ratio 정확히 4.50 (AA 경계, 읽기 문제 없음).
- 실질적 4.0:1 기준: 9 탭 17 건 (98% 개선).
- Overview / guideHub / workflows 스크린샷에서 카드 제목·숫자·사이드바 메타 모두 뚜렷하게 가독.

**파일**
- `dist/index.html`: light theme CSS 변수 + 20 줄 추가 override.
- `scripts/e2e-light-contrast.mjs`: 신규 audit 스크립트.

---
## [2.33.2] — 2026-04-24

### 🔌 ECC Plugin full auto-install

기존 v2.33.1 의 ECC 자동화는 marketplace 클론까지만 자동이고 실제 플러그인 설치는 사용자가 Claude Code 에서 `/plugin install` 을 직접 실행해야 했다. `claude plugin install` 서브커맨드가 비대화형으로 동작하는 것을 확인 후 두 신규 엔드포인트 추가:

- `POST /api/toolkit/ecc/install-plugin` — marketplace 미클론이면 선행 클론 후 `claude plugin install everything-claude-code@everything-claude-code -s user` 실행
- `POST /api/toolkit/ecc/uninstall-plugin` — `claude plugin uninstall ...` 실행

GuideHub 카드 UI 가 설치 상태에 따라 "🔌 플러그인 설치" / "🗑 플러그인 제거" 버튼으로 자동 토글.

**검증**
- Playwright end-to-end: "플러그인 설치" 클릭 → 30초 내 "1 개 플러그인 설치됨" 으로 전환 확인
- `claude plugin list` 에 `everything-claude-code@everything-claude-code` v1.10.0 등록 확인

**파일**
- `server/toolkits.py`: `_run_claude_plugin` + 2 신규 API
- `server/routes.py`: 2 라우트 등록
- `dist/index.html`: `_renderEccManage` 에 플러그인 토글 버튼 + `_eccInstallPlugin` 핸들러
- `dist/locales/{ko,en,zh}.json`: +7 keys

---
## [2.33.1] — 2026-04-24

### 🪟 사이드바 UX 3종 픽스

**문제**
1. **복구 불가** — 햄버거 버튼으로 사이드바를 접으면, 다시 펼칠 버튼이 사라져 재시작 전까지 좁은 아이콘 모드에 갇힘.
2. **flyout hover 끊김** — 카테고리에서 오른쪽 flyout 으로 마우스를 이동하는 도중 `8px` gap 구간에서 hover 가 빠져 flyout 이 닫힘.
3. **아이콘 의미 불명** — 접힌 사이드바에서 🆕 🏠 🔀 🧪 ⚙️ 📊 아이콘만 보여 어떤 기능인지 즉시 인지 불가.

**원인**
1. `_initMobileNav` IIFE 가 원본 `_syncNavToggleVisibility` 를 래핑하면서 `collapsed` 상태를 무시하고 `#navToggle` 을 항상 `display:none` 으로 덮어씀 → 접힌 상태에서 유일한 재펼치기 버튼이 숨겨짐.
2. `.nav-flyout { left: calc(100% + 8px) }` 의 8px gap 에서 마우스가 공백 위에 놓이면 `.nav-category:hover` 가 풀림.
3. `.nav-category` 에 `title` 속성 없음 + collapsed 상태에서 `.nav-cat-meta` 가 58px sidebar 내에 사실상 클리핑됨.

**수정**
1. `_initMobileNav` 의 래퍼 제거 — 원본 `_syncNavToggleVisibility` 가 이미 `(모바일 OR collapsed) ? 표시 : 숨김` 을 정확히 처리.
2. `.nav-category::after` 로 category 오른쪽에 14px 투명 pseudo-element 를 두어 hover 브리지. pseudo-element 는 category 의 자식이므로 마우스가 그 위에 있어도 `:hover` 유지.
3. collapsed 사이드바 너비 `58px → 78px` 로 확대. 아이콘 아래 **짧은 라벨**(Learn / Main / Build / Lab / Config / Watch) 9.5px 폰트로 세로 정렬. 추가로 `.nav-category` 에 `title` 네이티브 툴팁 부여 → 전체 설명도 hover 로 확인 가능.

**검증**
- `scripts/e2e-sidebar-ux.mjs` 신규 E2E — collapsed 후 `#navToggle` 가시성, flyout gap 중간 hover 유지, 바깥 이동 시 정상 종료, short 라벨 `display:inline-block` + full 라벨 `display:none` 확인.
- 기존 `e2e-ui-elements.mjs` 전 테스트 통과 (회귀 없음).

**파일**
- `dist/index.html`: nav-category CSS/마크업, GROUPS 에 `short` 필드 추가, `_initMobileNav` 단순화.
- `scripts/e2e-sidebar-ux.mjs`: 신규 회귀 테스트.

### 🌐 i18n — 사이드바 카테고리 & 부분 번역 누수 해소

**문제**
1. 사이드바 상위 카테고리 6종(Learn/Main/Build/Playground/Config/Observe)과 short 라벨(Lab/Watch 포함) 이 사전에 없어 en/zh 전환 시 영어 그대로 노출.
2. 서브탭 4개(`learner`/`artifacts`/`eventForwarder`/`securityScan`) 의 한국어 desc 가 en/zh 사전에 없어 원문 한국어가 노출됨.
3. 백엔드 추천 문구(`features.py::overallScore` recommendations 6종) 가 사전에 없어 `_translateDOM` 단어 레벨 치환으로 **부분 번역**(예: "자주 쓰는 Command Allow", "Permissions 프롬프트를 줄이려면 … allowAdd to.") 발생.

**원인**
- GROUPS 의 `label`/`short` 가 영어 리터럴이라 `t()` → ko 분기에서 `!_KO_RE.test(key)` 로 fallback 경로 타고 원문 리턴.
- 4 서브탭 desc 추가 시 locale 파일 업데이트 누락 (v2.30~v2.33 도입 탭).
- `_translateDOM` 의 pattern-based 치환이 긴 Korean 키 일치 없이 부분 단어만 치환하여 어색한 혼합문장 생성.

**수정**
- `GROUPS` label/short 을 Korean 으로 전환 (`학습`/`메인`/`빌드`/`플레이그라운드`/`구성`/`관측` + short `실험실`) — 기존 `t()` dict 경로로 자연 번역.
- `dist/locales/{ko,en,zh}.json` 에 22 개 키 추가:
  - 카테고리 6종 + short 변형
  - 4 서브탭 desc (Learner/Artifacts Viewer/Event Forwarder/Security Scan)
  - 백엔드 추천 6쌍(제목 + 상세) 완전 문장 (훅 설정/거부 규칙/자주 쓰는 명령/세션 스코어/플러그인 활성화/MCP 커넥터)

**검증**
- `scripts/e2e-find-missing-i18n.mjs` 신규 — ko/en/zh 3 언어 전환 후 텍스트 노드 + 속성에서 한국어 누수 수집. UI 텍스트 누수 0건 (남은 4건은 사용자 세션 prompt 내용으로 번역 대상 아님).
- `node scripts/verify-translations.js` 4 단계 검증 통과 (3486 keys × 3 lang).
- 스크린샷 확인: KO "학습/메인/빌드/플레이그라운드/구성/관측" · EN "Learn/Main/Build/Playground/Config/Observe" · ZH "学习/主要/构建/实验场/配置/观测".

**파일**
- `dist/index.html`: GROUPS label/short Korean 전환.
- `dist/locales/{ko,en,zh}.json`: +22 keys each.
- `scripts/e2e-find-missing-i18n.mjs`: 신규.

### 📏 flyout viewport-aware 위치 계산

**문제**
하단 카테고리(Observe/Config 14 items, Playground 12 items 등) 의 flyout 이 category top 기준 `top:0` 으로 아래로만 뻗어 viewport 아래로 삐져나감. `max-height:80vh + overflow-y:auto` 가 걸려있지만 스크롤 영역 자체가 viewport 밖이라 하단 아이템 접근 불가.

**원인**
`.nav-flyout { top: 0; max-height: 80vh }` CSS 만으로는 category 가 viewport 하단 쪽에 있을 때 flyout bottom 이 viewport 를 초과함. 측정 결과: 1440×900 viewport 에서 Observe flyout top=373, bottom=1093 (193px 초과 · 12 items 중 마지막 2개 클리핑).

**수정**
`_positionNavFlyout(cat)` 도입 — category 위치/자연 높이 측정 후 동적으로 `top` 음수 offset + `max-height` clamp. `mouseenter` · `focusin` · 클릭 open 시에 실행. resize 시 열려있는 flyout 자동 재계산.
- flyout 이 아래 공간에 들어가면 top:0 유지
- 아래로 넘치면 위로 shift 해서 flyout bottom ≤ viewport - 12px
- shift 해도 viewport 상단을 넘으면 top = 12px 에서 clamp (이때만 내부 스크롤 필수)

**결과** (1440×900)
| 카테고리 | 아이템 | 이전 flyout bottom | 이후 flyout bottom | fits? |
|---|---|---|---|---|
| learn | 4 | 368 | 368 | ✓ |
| main | 6 | 482 | 482 | ✓ |
| build | 10 | 819 | 819 | ✓ |
| playground | 12 | 1108 | 888 | ✓ (shift -220) |
| config | 14 | 1187 | 888 | ✓ (shift -299) |
| observe | 12 | 1093 | 888 | ✓ (shift -231) |

**파일**
- `dist/index.html`: `_positionNavFlyout` 함수 + nav-category mouseenter/focusin/click 바인딩.

### 🧰 가이드 툴킷 자동 설치/제거 — ECC · CCB

**문제**
1. **가독성** — guideHub 툴킷 카드의 설치 코드박스가 `rgba(0,0,0,0.3)` 반투명 배경 + `#a7f3d0` 민트 글씨라 light 테마에서 중간 회색 위에 밝은 글씨가 거의 안 보임. 카테고리 태그(Agents/Skills/Commands/Hooks) 도 `#c4b5fd` 연보라 글씨라 light 에선 대비 부족.
2. **관리 기능 부재** — Everything Claude Code(ECC) · Claude Code Best Practice(CCB) 가 카탈로그엔 있지만 설치/제거 버튼이 없어 사용자가 직접 터미널/CC 에서 수행해야 했음 (RTK 는 이미 자동화되어 있음).

**수정**
- **CSS `.code-terminal`** — 모든 테마에서 항상 `#0b1220` 진한 배경 + 선명한 민트 글씨로 통일. 툴킷 install 코드박스 전부 이 클래스 사용.
- **CSS `.chip-violet`** — light 테마에서 `#6d28d9` 진한 보라색으로 오버라이드. 카테고리 태그 전부 이 클래스 추가.
- **신규 `server/toolkits.py`** — `/api/toolkit/{status,ecc/install,ecc/uninstall,ccb/install,ccb/uninstall,ccb/open}` 6 라우트:
  - **ECC**: `git clone --depth 1 affaan-m/everything-claude-code` → `~/.claude/plugins/marketplaces/everything-claude-code/` + `known_marketplaces.json` 엔트리 등록. 이후 Claude Code 에서 `/plugin install ...` 만 실행하면 됨(명령 복사 버튼 제공). 제거 시 디렉터리 + 레지스트리 entry 모두 삭제.
  - **CCB**: `git clone --depth 1 shanraisshan/claude-code-best-practice` → 기본 `~/claude-code-best-practice/`. 제거 시 디렉터리 삭제(.git 존재 확인). macOS `open` 으로 폴더 열기 지원.
  - 보안: `_under_home` realpath 검증 · 쓰기 경로 화이트리스트 · `.git` 존재 확인 후 제거.
- **guideHub 카드 UI** — `AFTER.guideHub` → `_refreshToolkitManage()` 가 상태 가져와 각 카드 상단에 상태 chip + 버튼 렌더:
  - ECC: 미설치/마켓추가됨/플러그인 설치 필요, "마켓플레이스 추가"/"업데이트"/"마켓 제거" + `/plugin install` 명령 복사
  - CCB: 미설치/설치됨(commit hash), "내려받기"/"업데이트"/"폴더 열기"/"제거"

**검증**
- `curl -X POST /api/toolkit/ecc/install` → `{"ok":true,"installed":true}` · `~/.claude/plugins/marketplaces/everything-claude-code/` clone 완료 · `known_marketplaces.json` 에 entry 추가 확인.
- UI 재렌더 후 ECC 상태가 "✓ 마켓플레이스 추가됨 · 4e66b28 · 플러그인 설치 필요" 로 자동 업데이트.
- Light 테마 스크린샷에서 코드박스·태그 가독성 확연히 개선.

**파일**
- `server/toolkits.py`: 신규 (237줄).
- `server/routes.py`: 6 라우트 등록.
- `dist/index.html`: `.code-terminal` · `.chip-violet` CSS + `_renderGuideToolkits` 클래스 전환 + `AFTER.guideHub` + 5 API 호출 헬퍼.

### 🔑 로그인 게이트 — 매번 새로고침 → 첫 방문만

**문제**
`boot()` 에서 auth 상태와 무관하게 **항상** `showLoginGate` 를 호출해 새로고침마다 "Continue" 버튼을 한 번씩 눌러야 했음.

**수정**
- `localStorage` `dashboard-entered` 플래그 도입. 첫 `enterDashboard()` 호출 시 설정, `doLogoutOnly()` 에서 제거.
- `boot()` 로직: 플래그가 있고 `auth.connected` 면 → 게이트 스킵 후 바로 `enterDashboard()`. 첫 방문 OR 연결 끊김 OR 서버 실패 시에만 게이트 표시.
- 좌측 하단 `#cliStatus` 카드에 로그아웃 버튼 추가:
  - 연결됨: "🔄 전환" + "🚪 로그아웃" 2 버튼 (기존 "계정 전환" 단독 → 2 버튼)
  - 미연결: "🚀 로그인" 버튼
- i18n 22 키 추가 (`전환`, `로그아웃`, 기타 토글 + 토스트 메시지).

**검증**
- 첫 방문: 게이트 표시 · flag null
- Continue 클릭 후 flag="1"
- 새로고침: 게이트 스킵 · sidebar 즉시 표시 · nav 6 카테고리 렌더
- 로그아웃 버튼 → flag 제거 → 다음 로드 시 게이트 재표시
- verify-translations 4단계 통과 (3508 keys × 3 lang)

**파일**
- `dist/index.html`: `enterDashboard` localStorage 저장 · `boot()` 플래그 분기 · `doLogoutOnly` 플래그 클리어 · `#cliStatus` 카드 버튼 확장.
- `dist/locales/{ko,en,zh}.json`: +22 keys.

---
## [2.33.0] — 2026-04-24

### 🎨 Artifacts 로컬 뷰어 — 4중 보안 워크플로우 출력 미리보기 (build 그룹)

v2.21.0 Obsidian 설계 이후 미루어왔던 Artifacts 뷰어를 전면 새 설계 + 구현. 워크플로우 노드 출력(HTML/SVG/Markdown/JSON)을 **4중 보안** 으로 대시보드에서 안전하게 미리보기.

**4중 보안**
1. **Sandbox iframe** `sandbox=""` (빈 값 = 모든 권한 차단: 스크립트 실행·폼·쿠키·탐색·플러그인·탑레벨 이동 전부 블록)
2. **CSP meta 주입** `default-src 'none'; style-src 'unsafe-inline'; img-src data:` (외부 리소스 전면 차단, inline CSS 와 data: 이미지만)
3. **postMessage 화이트리스트** — iframe → parent 방향 메시지 검증 (현재 구조상 이벤트 없지만 향후 확장용)
4. **정적 필터** — `<script>` / `<iframe>` / `<object>` / `<embed>` / `<link>` / `<meta>` / `<base>` / `<form>` 태그 제거, `on*=` 이벤트 속성 제거, `javascript:` / `data:text/html` URL 제거

**신규 모듈 `server/artifacts.py`**
- 포맷 자동 감지: HTML / SVG / Markdown / JSON / text
- Markdown → 안전 HTML 변환 (외부 라이브러리 없이 순수 Python stdlib — 헤더/리스트/코드블록/bold/italic/code/link 지원)
- `_SRCDOC_WRAPPER`: CSP meta + 다크 테마 CSS 포함 HTML 템플릿
- 2 API: `/api/artifacts/list` (최근 50 run) · `/api/artifacts/render?runId=xxx&format=auto|html|svg|markdown|json|text`

**신규 탭 `artifacts` (build 그룹)**
- 좌측: 최근 run 목록 + 포맷 힌트 chip + 출력 크기
- 우측: iframe 미리보기 + 포맷 재선택 탭 (auto/html/svg/markdown/json/text)
- 보안 힌트: "sandbox='' + CSP default-src:none"

**단위 테스트 — 9/9 공격 패턴 차단**
- `<script>`, `<img onerror=>`, `javascript:`, `<iframe>`, `<object>`, `<link>`, `<meta refresh>`, `onload=`, `data:text/html` 모두 완전 제거 확인
- 포맷 감지 5/5 정확

**검증**
- 58/58 탭 smoke (57→58)
- CSP 주입 확인, srcdoc 길이 1.1KB (빈 문서 템플릿)
- i18n 6 키 × ko/en/zh

---
## [2.32.0] — 2026-04-24

### 🔌 MCP 서버 모드 — LazyClaude 를 Claude Code 에서 직접 호출

Claude Code 세션 안에서 대시보드 기능을 MCP tool 로 호출할 수 있게 LazyClaude 를 stdio MCP 서버로 노출.

**신규 파일**
- `server/mcp_server.py` — stdio JSON-RPC 2.0 루프 (MCP 2024-11-05 protocol)
- `scripts/lazyclaude_mcp.py` — 진입점 스크립트

**노출 tools (6)**
- `lazyclaude_tabs` — 6 상위 카테고리별 탭 카탈로그
- `lazyclaude_cost_summary` — 비용 타임라인 요약 (총 USD · 소스별 · 모델별)
- `lazyclaude_security_scan` — `~/.claude` 정적 보안 검사 결과
- `lazyclaude_learner_patterns` — 세션 반복 패턴 + 누적 토큰
- `lazyclaude_rtk_status` — RTK 설치/훅 상태
- `lazyclaude_workflow_templates` — 10 빌트인 템플릿 목록

**특징**
- Python stdlib 만 사용 (외부 MCP SDK 없음), newline-delimited JSON-RPC
- Transport: stdio · No network · No auth · 100% local
- Initialize → tools/list → tools/call → shutdown 완전 지원
- Unknown method 는 `-32601` error code 로 응답

**설치**
```bash
claude mcp add lazyclaude -- python3 /<path>/LazyClaude/scripts/lazyclaude_mcp.py
```

**대시보드 UI**
- MCP 탭 상단에 "💤 LazyClaude 자체를 MCP 서버로" 카드 추가
- `/api/mcp-server/info` 로 스크립트 절대경로 + 노출 tool 목록 동적 제공
- 설치 명령 readonly input + 📋 클립보드 복사 버튼
- 6 tool 설명 접힘 섹션

**검증**
- stdio 통신 테스트: `initialize` + `tools/list` + `tools/call` × 2 + `shutdown` 모두 정상 응답
- 실제 rtk 0.37.2 설치 감지 · workflow templates 10개 반환 확인
- 57/57 탭 smoke 통과
- i18n 4 키 × ko/en/zh

---
## [2.31.0] — 2026-04-24

### 🛡️ Security Scan 탭 — ECC AgentShield 스타일 정적 검사 (observe 그룹)

사용자 요청: ECC(everything-claude-code) 의 좋은 기능 흡수. 가장 가치 높은 **AgentShield** 를 우리 대시보드 형태로 재구현.

**신규 모듈 `server/security_scan.py` — 로컬 휴리스틱, AI 호출 없음**
- 스캔 대상: `~/.claude/settings.json` · `~/.claude/CLAUDE.md` · hooks · agents · `~/.claude/mcp.json`
- 이슈 카테고리 (severity: critical/high/medium/low/info):
  - **secrets**: API 키/토큰 평문 노출 (OpenAI / Anthropic / Google / GitHub PAT / AWS / Slack / PEM 등 8 패턴)
  - **permissions**: `Bash(*)` · `Bash(sudo *)` · `Bash(* | sh)` 같은 위험 allow 규칙
  - **hooks**: `sudo` / `rm -rf /` / `curl | sh` / `wget | sh` / `eval $()` / `chmod 777` 등 훅 내 위험 명령
  - **mcp**: `npx -y` / `uvx` 자동 설치 (신뢰 안된 패키지 시 RCE), MCP env 내 평문 시크릿
  - **tokens**: autocompact threshold 미설정, CLAUDE.md 50KB+ (토큰 낭비)
  - **integrity**: settings.json 파싱 실패

**신규 탭 `securityScan` (observe 그룹)**
- 상단 severity 카운터 (critical/high/medium/low/info 5 색상 카드)
- 이슈 카드 리스트 (좌측 3px 색상 바 · 심각도 이모지 · 카테고리 chip · 상세 · 파일 경로)
- "다시 검사" 버튼으로 재실행
- 이슈 0건 시 "✅ 깨끗합니다" 빈 상태

**API**
- GET `/api/security-scan` — 이슈 리스트 + severity/category 집계

**ECC 와의 차이**
- ECC AgentShield: 1282 tests · 102 정적 규칙 · `/security-scan` skill + `npx ecc-agentshield scan --opus` CLI
- 우리: **정적 휴리스틱 중심** (~~50 규칙) · GUI 탭 · 즉시 실행 · Python stdlib
- 향후 v2.32+ 에서 AI 보조 판단 (Opus scan) 옵션 추가 가능

**탭 57개** (56 → 57). i18n 6 키 × ko/en/zh.

**검증**
- 57/57 탭 smoke 통과
- 실환경 스캔: 1 info 감지 (autocompact threshold 미설정 권장)
- 8 secret 패턴 + 6 shell 위험 패턴 + 4 MCP 패턴 unit 커버리지

---
## [2.30.0] — 2026-04-24

### 🎓 Learner 탭 — 세션 패턴 추출 (B8, 마지막 backlog medium 항목 소화)

Claude Code 세션 JSONL 에서 반복되는 tool 시퀀스 · 프롬프트를 자동 감지해 Prompt Library / 워크플로우 템플릿으로 저장하도록 제안하는 탭.

**순수 통계 기반 (AI 호출 없음)**
- 최근 30일 / 최대 100 세션 / 세션당 500 라인 스캔
- 추출 지표:
  - **Top Tools** (Bash / Edit / Read 등 빈도 TOP 10, 가로 바 차트)
  - **Tool 3-gram 시퀀스** (같은 세션 내 연속 tool 호출 패턴, 3회 이상 발생)
  - **반복 프롬프트** (첫 60자 정규화 매칭, 3회 이상 반복)
  - **세션 길이 분포** (small ≤10 / medium 10-50 / large 50-200 / huge >200 라인 bucket)
  - **누적 토큰**
- 분석은 100% 로컬 — 외부 API 호출 없음

**UI**
- 3열 상단 카드 (스캔 세션 수 / 누적 토큰 / 길이 분포 stacked bar)
- Top Tools 가로 바 차트 (8개)
- 자동 추출 제안 카드 그리드:
  - 반복 프롬프트 → "Prompt Library 로 저장" 버튼 (에디터에 title/body/tags=['learner'] 자동 prefill 후 promptLibrary 탭으로 이동)
  - Tool 시퀀스 → "워크플로우 탭으로 이동" 버튼
- 하단 힌트 "분석은 완전히 로컬에서 수행됩니다"

**모듈**
- 신규 `server/learner.py::api_learner_patterns` (1 라우트)
- 새 탭 `learner` (build 그룹, nav_catalog + TAB_DESC_I18N + 프런트 NAV 엔트리)
- VIEWS.learner + `_learnerToPromptLib()` 헬퍼

**검증**
- 56/56 탭 smoke (신규 `learner` 추가로 55→56)
- 실환경 테스트: 100 세션 스캔 → 2.9M 토큰, 10 패턴 카드 생성 (Bash 412 · Edit 403 · Read 389 등), 반복 프롬프트 11회 감지
- i18n 16 키 추가 × ko/en/zh (learner_*)

**Backlog 현황**
- ✅ B1~B8 모두 소화 완료
- 🚫 blocked (사용자 설계 승인 필요): MCP 서버 모드 · Artifacts 로컬 뷰어

---
## [2.29.0] — 2026-04-24

### ⚙️ Policy fallbackProvider 확장 + 📤 Event Forwarder 신규 탭 (B7)

**Policy · fallbackProvider 확장 (`workflow.policy.fallbackProvider`)**
- session 노드가 assignee 로 실패할 때 설정된 프로바이더로 **1회 재시도**
- 허용값: `""`(none) · `claude-api` · `openai-api` · `gemini-api` · `ollama-api`
- 실행 결과에 `fallbackUsed` 필드로 어떤 프로바이더가 쓰였는지 기록 (빈 문자열이면 원래 assignee 로 처리됨)
- 재귀 방지: 폴백 호출은 `fallback=False` 로 넘겨 ai-providers chain 가 또 타지 않음
- 에디터 인스펙터 🛡 실행 정책 섹션에 select UI 추가

**B7 · Event Forwarder 신규 탭 (`eventForwarder`, config 그룹)**
- Claude Code hook 이벤트(`PostToolUse`, `Stop`, `SessionStart` 등 9종)를 외부 HTTP endpoint 로 포워딩
- 신규 모듈 `server/event_forwarder.py`:
  - `~/.claude/settings.json` 의 hooks 섹션에 `curl -sS -X POST --data-binary @- '<URL>' # __lazyclaude_forwarder__` 엔트리 add/remove
  - 매 변경 시 `settings.json.bak.<ts>` 자동 백업
  - `__lazyclaude_forwarder__` 마커로 우리 엔트리만 필터 — 사용자가 직접 추가한 hook 은 건드리지 않음
- **SSRF 방어 (호스트 화이트리스트 11종)**: `hooks.slack.com` · `discord.com` · `webhook.site` · `requestbin.com` · `pipedream.net` · `zapier.com` · `api.github.com` · `maker.ifttt.com` · `n8n.cloud` 등 + 루트 도메인 매칭 (예: `subdomain.webhook.site` OK)
- https-only · URL 길이 500 이하 · shell metacharacter 금지 (`'`, `"`, `\\`, `$`, `` ` ``, newline) → single-quote 래핑으로 안전하게 shell escape
- 4개 라우트: GET `/api/event-forwarder/{list,meta}`, POST `/api/event-forwarder/{add,remove}`
- UI: 이벤트 타입 select + matcher input + URL input + 허용 호스트 안내 + 등록된 forwarder 테이블 + 삭제 버튼

**검증**
- 55/55 탭 smoke (신규 `eventForwarder` 추가로 54→55)
- Policy fallback sanitize 경계 케이스 3종 (정상 / evil / claude-api)
- Event Forwarder E2E: http 거부 · evil.com 거부 · webhook.site 정상 add→list→remove round-trip
- settings.json 자동 백업 후 정상 JSON 쓰기 확인
- i18n 26 키 추가 × ko/en/zh (policy_fallback_* · fwd_*)

---
## [2.28.0] — 2026-04-23

### 🔧 RTK init 근본 수정 + 🌐 번역 완전성 + 🛡 보안 감사

사용자 리포트 3건: RTK 자동 설치가 N 으로 되어버림, 번역 누락, 신규 코드 보안 점검.

**🔧 RTK `init` 근본 수정 — `--auto-patch` 플래그로 교체**
- 기존 `yes | rtk init -g` 는 오히려 rtk 의 `is_terminal()` 감지로 "stdin not a terminal → default No" 로 빠져 훅이 설치되지 않았음
- [`rtk-ai/rtk/src/hooks/init.rs`](https://github.com/rtk-ai/rtk/blob/master/src/hooks/init.rs) 소스 확인: `--auto-patch` 공식 플래그로 프롬프트 스킵 가능
- `api_rtk_init` → `rtk init -g --auto-patch` 로 변경 + UI 토스트 문구 조정

**🌐 번역 완전성 — 71 한국어 잔여 제거**
- `t('key', '한국어 fallback')` 의 긴 한국어 fallback 들이 `extract_ko_strings.py` 에 의해 audit 에 수집되어 `locales/{en,zh}.json` 에 `key=한국어 identity / value=한국어` 로 등록되어 있었음 (ko 원문 그대로 노출)
- `translations_manual_9.py` 의 `NEW_EN` / `NEW_ZH` 양쪽에 71 항목 × 3 언어 추가 번역 일괄 등록
- 결과: `en.json` · `zh.json` 내 한국어 잔여 **71 → 0**
- 전수 검증: `python re '[가-힣]'` 매칭 0건

**🛡 보안 감사 — v2.24~v2.27 신규 코드 방어 강화**

1. **`session_replay.py` 경로 boundary 체크 강화** (v2.25.0 에 `pass` 로 무력화되어 있었음)
   - `try/pass` 블록을 실제 `resolve(strict=True)` + `relative_to(_PROJECTS)` 검증으로 교체
   - symlink 경유 경로 탈출 차단
   - 공격 시도 테스트: `../../../../etc/passwd` · `/etc/passwd` · `abc/..` · `..` 모두 `invalid path` 반환

2. **`notify.py` HTTP redirect 차단** (defense-in-depth)
   - 기존 `urllib.request.urlopen` 은 3xx 자동 추종 → 이론상 화이트리스트 호스트에서 다른 호스트로 redirect 유도 가능
   - `_NoRedirect` 핸들러 + 전용 opener 로 리다이렉트 전면 차단
   - Slack/Discord webhook 은 일반적으로 리다이렉트 없음 → 기능 영향 없음

3. **감사 대상** (조치 불필요):
   - `rtk_lab.api_rtk_uninstall_hook` — 백업 자동 생성 + `_is_rtk_hook` 휴리스틱 OK
   - `prompt_library.find_keyword_triggers` — 로컬 단일 사용자 전제, UI 에서 키워드 가시 관리
   - `policy.tokenBudgetTotal` sanitize 0~1억 경계 OK

**검증**
- 54/54 탭 smoke 통과
- i18n 3 언어 정합성 + 한국어 잔여 0
- 공격 시도 4 경로 · 잘못된 host 1 케이스 모두 차단

---
## [2.27.0] — 2026-04-23

### 🏗️ Team Sprint 템플릿 + 워크플로우 전역 토큰 예산 정책 (backlog B6 + Policy)

**B6 · Team Sprint 빌트인 템플릿 (`bt-team-sprint`)**
- OMC `omc team 3:executor` 의 5단계 파이프라인을 단일 DAG 로:
  - 🧭 Plan (Opus) → 📋 PRD (Sonnet) → 👷 Exec ×3 병렬 (Sonnet) → 🔀 Merge → 🔎 Verify (Haiku) → Branch `PASS?` → ✅ Out / 🛠️ Fix
- Verify 실패 시 피드백 자동 주입해 Plan 단계부터 최대 3회 repeat 루프 (bt-ralph 패턴 응용).
- 11 노드 · 12 엣지 · repeat(maxIterations=3, feedbackNodeId=n-plan).
- 빌트인 템플릿 9 → 10.

**Policy 프리셋 — 워크플로우 전역 토큰 예산 (`workflow.policy.tokenBudgetTotal`)**
- `_sanitize_workflow` 에 `policy` 필드 추가:
  - `tokenBudgetTotal`: 0 (unlimited) ~ 100,000,000 토큰
  - `onBudgetExceeded`: `"stop"` (기본) | `"warn"` — 현재는 stop 만 동작
- `_run_one_iteration` 의 level 루프 시작부에 누적 토큰 집계:
  - `sum(tokensIn + tokensOut for 완료된 노드)` ≥ 예산 → 남은 모든 노드를 `budget_exceeded` 상태로 표시 후 iteration 조기 종료
  - 부분 결과는 유지 (status="ok" 로 종료, `budgetExceeded: true` 플래그)
- 에디터 인스펙터에 **🛡 실행 정책** 섹션 — 예산 입력 필드 + 힌트

**i18n** — `policy_heading` / `policy_budget_label` / `policy_budget_hint` 3 키 × ko/en/zh.

**검증**
- 54/54 탭 smoke · 템플릿 10건 조회 확인
- Policy round-trip: `{tokenBudgetTotal: 1234}` 저장 → 조회 시 `{tokenBudgetTotal: 1234, onBudgetExceeded: "stop"}` 정상 반환
- Sanitize 3 케이스 (정상/음수/거대값) 경계 확인

---
## [2.26.0] — 2026-04-23

### 🧭 사이드바 UX 개편 — 6 상위 카테고리 + hover flyout

사용자 피드백: "카테고리가 너무 많아서 보기 어려운데, 상위 카테고리를 만들고 마우스가 가까이가면 바가 열리면서 상세 카테고리를 고를 수 있게 해줘. 형태나 양식이 비슷한 것들을 모아줘."

**재분류 (6 → 6, 의미 재정비)**
- `new` → **Learn** 🆕 — 신기능 · 온보딩 · Claude Docs · 가이드 (4)
- `main` → **Main** 🏠 — 대시보드 · 프로젝트 · **plans(이동)** · 통계 · AI 평가 · 세션 (6)
- `work` 분할 → **Build** 🔀 (워크플로우/에이전트/프롬프트 8) + **Playground** 🧪 (API 실험실 12)
  - Build: workflows · promptLibrary · rtk · projectAgents · agents · skills · commands · agentSdkScaffold
  - Playground: aiProviders · promptCache · thinkingLab · toolUseLab · batchJobs · apiFiles · visionLab · modelBench · serverTools · citationsLab · embeddingLab · sessionReplay
- `advanced` 해체 → **Config** ⚙️ 로 흡수 (13). plans 만 Main 으로.
- `system` → **Observe** 📊 — 비용/메트릭/세션 관측 (11)

**UX**
- `renderNav()` 전면 재작성: `nav-category` (상위 6) 만 사이드바에 표시, 각 `nav-category` 자식으로 `nav-flyout` (서브 탭 목록) 포함.
- 호버/포커스/클릭 모두로 flyout 열기 — `hover: `, `:focus-within`, `.open` 트리거.
- 현재 탭이 속한 카테고리에 `.has-active` + 주황 dot · drop-shadow 강조.
- 탭 클릭 시 `go(id)` + flyout 자동 닫기.
- ESC 로 모든 flyout 닫기. 사이드바 바깥 클릭으로도 닫힘.
- 모바일(max-width: 900px) 에선 flyout 이 아코디언 (position static, hover 비활성, click 만).

**CSS**
- `.nav-category`, `.nav-cat-icon/meta/label/dot/desc/count/chevron`, `.nav-flyout`, `@keyframes navFlyoutIn` 신규.
- `#nav` 의 `overflow-y-auto` → `overflow: visible` (flyout 이 오른쪽으로 튀어나올 수 있게).
- 6 카테고리뿐이라 스크롤 불필요 (viewport 900 에서 footer 까지 여유).

**서버 `nav_catalog.py`**
- `TAB_GROUPS` 재정의 (6 상위).
- `_new_group()` remap: 기존 `TAB_CATALOG` 엔트리의 legacy group 을 runtime 에 신규 group 으로 변환 — 챗봇 프롬프트(`render_tab_catalog_prompt`) 도 새 카테고리 기준.
- `plans` 만 main 으로 수동 예외.

**검증**
- 54/54 탭 smoke 통과
- Playwright 시각 체크: 6 카테고리 사이드바 + Playground hover 시 12 항목 flyout 펼쳐짐, 워크플로우 콘텐츠 정상 공존.
- 챗봇 프롬프트 확인: Learn/Main/Build/Playground/Config/Observe 로 정렬됨.

---
## [2.25.1] — 2026-04-23

### ⚡ 자율모드 빠른 개선 3건 (C1~C3)

v2.25.0 이후 backlog 의 "quick wins" 를 자율모드로 일괄 반영.

**C1 · RTK 탭 스크린샷을 README 3종에 반영**
- 이미 생성되어 있던 `docs/screenshots/{ko,en,zh}/rtk.png` (각 200KB+) 가 README 에서 참조되지 않고 있던 것을 정리.
- 영문/한글/중문 README 의 스크린샷 섹션 하단에 "Token Optimization / 토큰 최적화 / Token 优化" 섹션 추가.

**C2 · CostsTimeline 주/월별 뷰 토글**
- `VIEWS.costsTimeline` 차트 헤더에 `일 / 주 / 월` 토글 버튼 추가.
- 클라이언트 사이드에서 일별 `days` 데이터를 ISO 주(월요일 시작) / YYYY-MM 단위로 재집계 (`_costsBucket` 헬퍼).
- `state.data._costsBucket` 으로 선택 상태 유지, 탭 재진입 시 복원.

**C3 · Workflow run diff 에 토큰/비용 변화량**
- `api_workflow_run_diff` 응답 확장:
  - 노드별: `aTokensIn/Out`, `bTokensIn/Out`, `tokensInDelta`, `tokensOutDelta`, `aCostUsd`, `bCostUsd`, `costDelta`
  - 요약: `a/b.tokensIn/Out/costUsd`, `tokensInDelta`, `tokensOutDelta`, `costDelta`
- UI 테이블에 `Δ 토큰` `Δ 비용` 컬럼 추가, 하이라이트 조건에 토큰 변화 반영.
- 요약 줄에 `A tok $` · `B tok $` · `Δ 토큰` · `Δ 비용` 모두 노출.

**i18n** — costs_bucket_day/week/month · 토큰 · diff_highlight_hint 등 8 키 추가 × ko/en/zh.

**검증**
- 54/54 탭 smoke 통과
- CostsTimeline Playwright smoke — day/week/month 헤더 전환 모두 확인
- i18n 정합성 통과

---
## [2.25.0] — 2026-04-23

### 🆕 OMC/OMX gap 흡수 세션 (자율모드 큐 소진)

사용자 요청: `oh-my-claudecode` (OMC) / `oh-my-codex` (OMX) 분석 후 LazyClaude 에 없는 기능 중 low 위험도 항목을 자율모드로 일괄 반영.  
분석 노트: `docs/plans/analysis-omc-omx-gap.md`, 큐: `docs/plans/today-queue.md`, 로그: `docs/logs/2026-04-23.md`.

**B1 · 실행 모드 빌트인 템플릿 4종 (work 그룹)**
- `bt-autopilot` — 요구사항 → 계획 → 실행 → 검증 단일 흐름 (OMC `/autopilot`)
- `bt-ralph` — verify → fix 루프 (repeat enabled, max 5, feedback auto-inject · OMC `/ralph`)
- `bt-ultrawork` — 5 병렬 에이전트 → merge (Sonnet×2, Haiku×3 · OMC `/ultrawork`)
- `bt-deep-interview` — Socratic 명확화 → 설계 문서 (OMC `/deep-interview`)
- 총 빌트인 템플릿 5→9

**B2 · Prompt Library 키워드 트리거 (OMC `ultrathink`/`deepsearch` 대응)**
- `keywords: string[]` 필드 추가 (최대 10)
- 워크플로우 session 노드 실행 시 입력 텍스트에 키워드 매칭되면 해당 프롬프트 body 가 systemPrompt 앞에 자동 prepend
- 에디터에 키워드 입력란 + 설명

**B3 · 워크플로우 완료 알림 — Slack / Discord (OMC `config-stop-callback` 대응)**
- 신규 모듈 `server/notify.py` — `hooks.slack.com` / `discord.com` / `discordapp.com` 호스트 화이트리스트, https-only
- 워크플로우 저장 스키마에 `notify: {slack, discord}` 필드 (sanitize 에서 URL 검증)
- run 성공/실패 시 이모지 + 상태 + 실행 시간 + 비용 + 요약 500자 전송
- `POST /api/notify/test` — UI 테스트 버튼 (`target: slack|discord`, `url`)
- 에디터 인스펙터에 Webhook URL 섹션 + 테스트 버튼

**B4 · session 노드 modelHint — 자동 모델 라우팅 (OMC smart routing 대응)**
- session 노드 data 에 `modelHint: "" | "auto" | "fast" | "deep"`
- assignee 가 비어있을 때만 적용 (명시적 지정이 우선, backward compat)
- fast → haiku, deep → opus, auto → 휴리스틱 (길이 + 키워드)
  - 3000+ 문자 또는 architect/design/deep 키워드 → opus
  - 500- 문자 + list/summary/quick 키워드 → haiku
  - 그 외 → sonnet
- 실행 결과에 `chosenModel` 필드 노출

**B5 · Session Replay Lab 신규 탭 (`sessionReplay`, work 그룹)**
- 신규 모듈 `server/session_replay.py` — `~/.claude/projects/**/*.jsonl` 스캔
- 최근 50 세션 목록 + 개별 파싱 (최대 2000 events) — role · 요약 · tool_use 마커 · tokens · timestamp
- 좌측 세션 목록 + 우측 타임라인 (색상별 role · 툴 호출 하이라이트)
- 누적 토큰 스파크라인 (600×40 SVG path)
- 54 탭으로 확장

**분석 문서 (기록)**
- `docs/plans/analysis-omc-omx-gap.md` — OMC/OMX vs LazyClaude 매트릭스 + 흡수 후보 HIGH/MED/LOW 분류 + 추가 최적화 포인트
- `docs/plans/backlog.md` — 자율모드 제외(medium 위험) 항목 + MCP 서버 모드 등 향후 후보

**통계**
- 탭: 53 → 54
- API 라우트: 192 → 198
- 빌트인 템플릿: 5 → 9
- 54/54 탭 smoke 통과 · i18n ko/en/zh 정합성 통과 (키 추가 ~15)

---
## [2.24.1] — 2026-04-23

### 🔁 RTK 자동화 — 설치/훅 완료 자동 감지 + y/n 자동 응답

사용자 피드백 2건 반영:
1. 설치 완료 후 탭 새로고침을 수동으로 해야 함 → 자동 감지 + renderView
2. `rtk init -g` 가 묻는 y/n 프롬프트를 수동 응답해야 함 → `yes` 파이프로 자동

**백엔드 (`server/rtk_lab.py::api_rtk_init`)**
- 명령 변경: `rtk init -g` → `yes | rtk init -g`
- `yes` 는 모든 확인 프롬프트에 `y` 자동 응답. rtk 가 stdin 을 쓰지 않으면 `yes` 가 SIGPIPE 로 조기 종료되어 부작용 없음.

**프런트 (`dist/index.html::_rtkStartPolling`)**
- `_rtkInstall()` 완료 시 `install` 모드 polling 시작 (2.5s 간격, 5분 타임아웃)
- `_rtkInit()` 완료 시 `hook` 모드 polling 시작 (1.5s 간격, 2분 타임아웃)
- polling 은 `/api/rtk/status` 를 주기 호출 → `installed` / `hookInstalled` true 되면 `renderView()` + toast
- RTK 탭을 떠나면 `go()` / `hashchange` 에서 `_rtkStopPolling()` 호출로 polling 정리
- 현재 탭이 RTK 가 아니면 renderView 없이 toast 알림만

**i18n** 10 키 추가 × ko/en/zh (rtk_polling_* / rtk_detected_*).

---
## [2.24.0] — 2026-04-23

### 🦀 New tab: RTK Optimizer (`work` group)

Claude 토큰 **60-90% 절감** 하는 Rust CLI 프록시 [`rtk-ai/rtk`](https://github.com/rtk-ai/rtk) 를 대시보드에서 바로 설치·활성화·통계 조회 가능한 탭으로 통합.

**신규 모듈: `server/rtk_lab.py`**
- 설치 여부 감지 — `_which("rtk")` 로 PATH + homebrew/cargo 경로 fallback
- 설정 파일 경로 OS 분기 (macOS: `~/Library/Application Support/rtk/config.toml`, Linux: `$XDG_CONFIG_HOME/rtk/config.toml`)
- Claude Code settings.json 내 `rtk` 참조 탐지로 훅 활성 상태 체크
- 6가지 명령 그룹 카탈로그 (file · git · test · build · analytics · utility)

**신규 라우트 6건**
- GET `/api/rtk/status` · `/api/rtk/config` · `/api/rtk/gain` · `/api/rtk/session`
- POST `/api/rtk/install` · `/api/rtk/init`
- 설치/init 은 기존 `cli_tools._run_in_terminal` 재사용 → AppleScript 로 Terminal 창 대화형 실행

**설치 경로 3종**
- `brew install rtk` (Homebrew 있을 때 기본)
- `curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh`
- `cargo install --git https://github.com/rtk-ai/rtk`

**UI — `VIEWS.rtk`**
- 상태 카드 3열 (설치 상태 + 훅 활성 / 설정 파일 경로 / 참고 링크)
- 미설치 시: 설치 방법 버튼 (Homebrew · curl · Cargo — 환경별 노출)
- 설치 시: `rtk init -g` 훅 설치 버튼 + 누적 절감 통계 (`rtk gain`) + 세션 내역 (`rtk session`) 실시간 조회
- 명령 레퍼런스 6 그룹 그리드 — chip 단위 빠른 참조 + `-u/--ultra-compact` 힌트

**i18n** 28 키 추가 × ko/en/zh → 3,281 키 정합성 통과.

**LazyClaude 마스코트 (`docs/logo/mascot.svg`)**
- 기존 오렌지 픽셀 캐릭터 (`#E07C4C`) 를 정적 로고로 변환
- "lazy" 정체성 강조 — 눈을 감은 표정 (sleeping slits) + `Zzz` 인디케이터 + 볼 홍조
- 애니메이션 제거 (GitHub README 는 SVG `<style>` 차단) → 정적 포즈만
- README 3종 Hero 섹션 아래에 `<img>` 임베드

**기타**
- `dist/index.html`: 잔여 `Claude Control Center` 4곳 (title · 사이드바 · 온보딩 모달) → `LazyClaude`
- nav 카탈로그 · TAB_DESC_I18N 갱신 (52탭 → 53탭)
- e2e-tabs-smoke 53/53 통과

---
## [2.23.2] — 2026-04-23

### 📸 Docs — 언어별 스크린샷 36장 + UI 브랜드 텍스트 정리

사용자 리포트 2건 반영:
1. 영문 README 가 한글 UI 스크린샷을 참조
2. `AI Providers` / `Costs Timeline` 이 빈 화면으로 캡처됨

**`scripts/capture-screenshots.mjs` 전면 재작성**
- 12 탭 × 3 언어 = 36장 → `docs/screenshots/{ko,en,zh}/<tab>.png`
- `?lang=en|zh` 쿼리로 UI 언어 전환 후 캡처 (context 재생성)
- `waitForLoadState('networkidle')` + 탭별 selector + `waitForResponse('/api/ai-providers/list')` + chip 개수 `waitForFunction` — zh/en 에서 `aiProviders` 가 스켈레톤 상태로 찍히던 문제 해결
- `page.route('**/api/cost-timeline/summary', ...)` 로 Costs Timeline 모의 응답 주입 (14일 × 5 소스 × 147건 · 총 $12.38) — 실 API 호출 없이 의미있는 스택 차트 생성
- overview 탭의 Claude 계정 온보딩 모달을 `Continue|계속|继续` 버튼 자동 클릭으로 통과
- 워크플로우 시드 선택 fallback: `_wfOpen` → `_wfSelect` → 직접 `__wf.current` 할당

**`dist/index.html` UI 브랜드 텍스트 정리**
- `<title>` · 사이드바 브랜드 · 계정 온보딩 모달 헤더 등 4곳의 `Claude Control Center` → `LazyClaude` 치환 (리브랜딩 일관성)

**README 3종 이미지 경로 분기**
- `./docs/screenshots/*.png` → `./docs/screenshots/{ko,en,zh}/*.png` (각 README 자신의 언어로)

**검증**
- 36/36 캡처 성공
- 각 언어에서 overview (최적화 점수 21 · 6171 세션 렌더) · aiProviders (8 프로바이더 카드) · costsTimeline (스택 차트 + 소스별 집계) · workflows ([Demo] Multi-AI Compare DAG) 시각 확인

---
## [2.23.1] — 2026-04-23

### 🎨 Branding — 프로젝트 이름을 **LazyClaude** 로

레퍼런스: [`Yeachan-Heo/oh-my-claudecode`](https://github.com/Yeachan-Heo/oh-my-claudecode) 의 README 스타일 참고.

- **브랜드 네임**: `Claude Control Center` → `💤 LazyClaude`
  - 네이밍 톤: `lazygit` / `lazydocker` / `lazyvim` 패밀리 편승. 게으른 사람을 위한 로컬 Claude 커맨드 센터.
  - 캐치프레이즈: "Don't memorize 50+ CLI commands. Just click." / "50+ 개 CLI 명령어 외우지 마세요. 그냥 클릭하세요."
- **README 3종 (ko/en/zh)**
  - Hero 섹션을 `<div align="center">` 중앙 정렬, 태그라인 + 캐치프레이즈 상단에 배치.
  - Quick Start 를 "1 · 클론 / 2 · 실행 / 3 · 접속" 3단계 박스 스타일로 재구성.
  - 장문 "v2.x 신기능" 나열을 "최근 업데이트" 테이블 (6 행) 로 압축.
  - ASCII 배너 내 `🧭 Claude Control Center` → `💤 LazyClaude`.
  - Contributing 섹션: 1인 메인테이너 개인 프로젝트임을 명시, "core team" 같은 구절 제거. PR 유도 톤은 유지.
  - Acknowledgements 에 lazygit/lazydocker 크레딧 추가.
  - 하단에 "Made with 💤 for those who'd rather click than type." 서명.
- **기술 경로 유지** (하위 호환):
  - Repo URL `github.com/cmblir/claude-dashboard` 유지 (rename 은 사용자 선택 사항).
  - 데이터 파일 `~/.claude-dashboard-*.json` 경로 유지 — 기존 사용자 데이터 보존.
  - 내부 변수명·모듈명 변경 없음.

---
## [2.23.0] — 2026-04-23

### 🛡 Security — Webhook 인증 + Output 경로 화이트리스트 (v2.22 보안 감사 후속)

v2.22.0 SSRF 가드 직후 남아있던 MEDIUM 2건을 마무리. 로컬 `127.0.0.1:8080` 바인딩 전제라 실위협은 제한적이지만, 원격 포워딩·컨테이너 공유 환경을 대비해 선반영.

**Finding 2 · Webhook 무인증 → `X-Webhook-Secret` 필수 (`server/workflows.py`)**
- 워크플로우마다 `webhookSecret` 필드 보관. `POST /api/workflows/webhook/<wfId>` 호출 시 헤더 필수.
- 비교는 `hmac.compare_digest` — 타이밍 공격 방어.
- secret 미발급 상태면 401 응답으로 호출 차단 (`err_webhook_no_secret`).
- 저장 API (`/api/workflows/save`) 로는 secret 을 변경할 수 없음 (기존값만 보존). 전용 API 로만 관리.

**신규: `POST /api/workflows/webhook-secret`**
- `{action: "get"}` 현재값 조회
- `{action: "generate"}` 미발급 시 발급, 이미 있으면 기존값
- `{action: "rotate"}` 새 값으로 교체 (기존 호출자 모두 401)
- `{action: "clear"}` 제거 — webhook 비활성화
- 생성: `secrets.token_urlsafe(32)` → 43자 URL-safe base64

**UI · 워크플로우 에디터 우측 인스펙터**
- Webhook URL 아래 Secret 패널 추가. 상태(발급/미발급) 표시.
- 버튼: 🔐 Generate · 🔄 Rotate · 🚫 Clear · 👁 Show/Hide · 📋 Copy
- `curl` 예시에 `-H "X-Webhook-Secret: ..."` 자동 삽입 (실값 반영).
- rotate/clear 는 confirm 모달로 이중 확인.

**Finding 3 · Output 노드 `exportTo` 경로 화이트리스트 (`server/workflows.py`)**
- 기존 `_under_home` (`~/` 하위 모두 허용) → 신규 `_under_allowed_export` (`~/Downloads` · `~/Documents` · `~/Desktop` 만 허용).
- `os.path.realpath` 로 symlink 완전 해제 후 비교 → `~/Documents/../.ssh/x` 같은 traversal 차단.
- 허용 경로 밖이면 노드 실행 단계에서 명시적 에러.

**i18n · 한/영/중**
- 17 항목 추가 (`webhook_secret_*` 9 + 표시/숨김 등). 3,253 키로 정합성 검증 통과.

**검증**
- `e2e-tabs-smoke.mjs` 52/52 통과
- `verify:i18n` 통과 (3,253 ko/en/zh 키 집합 일치)
- curl E2E: no-secret → 401, wrong → 401, rotate 후 옛 값 → 401, 새 값 → 200
- 경로 화이트리스트 단위 테스트: `/etc/passwd`, `~/../etc/passwd`, `~/.ssh/id_rsa`, `/tmp/foo.txt`, `~/Documents/../.ssh/x` 모두 차단 확인

---
## [2.22.1] — 2026-04-23

### 📸 Docs — README 3종에 스크린샷 12장 삽입

사용자 피드백: "글만 보고 어떤식으로 나오는지 알 수 없잖아". 실제 UI 보여주는 스크린샷 자동 생성 + README 임베드.

**신규: `scripts/capture-screenshots.mjs`**
- Playwright 로 주요 12 탭을 1440×900 @2x (레티나) 로 캡처
- `docs/screenshots/<tab>.png` 에 저장
- workflows 탭은 `bt-multi-ai-compare` 템플릿 시드 후 `_wfFitView()` 로 전체 DAG 노출
- promptCache 탭은 예시 1개 로드 후 캡처
- 캡처 완료 시 `[Demo]` 시드 워크플로우 자동 정리

**캡처 대상 (12)**
- `overview` · `workflows` · `aiProviders` · `costsTimeline`
- `promptCache` · `thinkingLab` · `toolUseLab` · `modelBench`
- `claudeDocs` · `promptLibrary` · `projectAgents` · `mcp`

**총 용량**: ~2.4MB (탭당 100~330KB · PNG 레티나). Git 저장소에 직접 commit.

**README 3종 구조**
- ASCII 미리보기 박스 바로 아래 `### 📸 Screenshots / 스크린샷 / 截图` 섹션 추가
- 4개 카테고리 × 2열 markdown 표 (메인 / 멀티AI·비용 / API 플레이그라운드 / 지식·재사용)
- `![label](./docs/screenshots/tab.png)` 상대 경로 → GitHub raw 렌더 호환

**package.json scripts.screenshots** 추가: `npm run screenshots` 로 재생성.

**사전 요건**: 서버가 `127.0.0.1:8080` 에서 기동 중이어야 함 + `npx playwright install chromium` 완료.

## [2.22.0] — 2026-04-23

### 🔒 Security — 워크플로우 HTTP 노드 SSRF 가드 (Finding 1 fix)

보안 감사에서 발견된 **HIGH** 급 SSRF 취약점 수정. 기존 `_execute_http_node` 가 URL 의 scheme/host 검증 없이 `urllib.request.urlopen` 을 호출해 **DNS rebinding / CSRF / 악성 워크플로우 import** 시 다음 공격이 가능했음:

- 클라우드 메타데이터 (`http://169.254.169.254/`) 접근 → 자격 증명 유출
- 로컬/사설 네트워크 포트 스캔 (`http://127.0.0.1:6379`, `http://192.168.x.x:*`)
- `file://`, `ftp://`, `gopher://` 등 비-HTTP 스킴을 통한 파일 읽기 / 내부 호출

**수정 내역**
- `server/workflows.py::_execute_http_node`:
  * scheme 화이트리스트: `http`, `https` 만 허용. 그 외는 `"scheme blocked"` 에러.
  * 호스트 블랙리스트: `127.0.0.1 · 0.0.0.0 · ::1 · localhost · 169.254.169.254 · metadata.google.internal · metadata.goog · fd00:ec2::254`
  * 사설/링크로컬 프리픽스 차단: `10.*`, `127.*`, `169.254.*`, `172.16~31.*`, `192.168.*`, IPv6 `fc*/fd*/fe80~feb*`
  * **DNS rebinding 방어**: 호스트가 DNS 이름일 때 `getaddrinfo` 로 실제 IP 를 해석 후 재검사. 해석 실패 시 `fail-closed`.
- **옵트인 우회**: 노드 `data.allowInternal = true` 로 체크 시만 내부 호출 허용. UI 에 경고 박스 + 체크박스 (기본 off).
- `dist/index.html::VIEWS.workflows` HTTP 노드 에디터에 체크박스 추가 + 신규 HTTP 노드 data 기본값에 `allowInternal: false` 명시.
- `tools/translations_manual_9.py`: 2 키 × ko/en/zh 추가.

**영향도**
- **공격 차단**: 외부 공격자의 DNS rebinding 이나 악성 워크플로우 JSON import 를 통한 내부 네트워크 접근 원천 차단.
- **호환성**: 기존 워크플로우의 외부 API 호출 (`api.openai.com`, `api.anthropic.com` 등) 은 영향 없음. 로컬 테스트용 호출(`http://localhost:3000`) 은 UI 에서 체크박스 켜야 동작.

**감사 출처**: `/security-review` 스킬 · `Obsidian/logs/2026-04-23-security-audit.md` 에 상세 기록.

## [2.21.1] — 2026-04-23

### Docs — README 3종 통계 v2.21.1 기준 갱신 (세션 5 결과)

T15~T17 (v2.19.0 · v2.20.0 · v2.21.0 docs) 반영:
- 버전 배지 v2.18.1 → **v2.21.1**
- 51 → **52 tabs** (costsTimeline 추가)
- 178→188→**190** routes (GET 102 / POST 85 / PUT 3)
- 3,212 → **3,234** i18n keys × 3언어
- Stats 섹션: 백엔드 ~17,600/44 → **~18,000/46 modules** · 프론트 ~16,300→**~16,600**
- **신규 행**: "Unified cost timeline ✓ · Workflow run diff/rerun ✓"
- README ko/en/zh 3종 동등 갱신
- `npm run test:e2e:smoke` 52/52 tabs (comment 업데이트)

## [2.21.0] — 2026-04-23

### 📐 Docs — Artifacts 로컬 뷰어 설계 문서 (구현 X)

B6 (Claude.ai Artifacts 의 로컬 대안) 을 안전하게 구현하기 위한 **설계 선행**. 실제 코드는 다음 세션 (T20~T23, v2.22~v2.24) 에 나누어 진행.

**저장 위치**: `Obsidian/Projects/claude-dashboard/decisions/2026-04-23-artifacts-design.md`

**핵심 보안 4중 방어**
1. **iframe sandbox**: `srcdoc` 로 origin = null · `sandbox="allow-scripts"` (allow-same-origin 제외) → cookie / localStorage / IndexedDB 불가
2. **CSP via srcdoc meta**: `default-src 'none'; script-src 'unsafe-inline'; connect-src 'none'` → 외부 fetch 차단 (CSS exfiltration 포함)
3. **postMessage 화이트리스트**: `artifact:ready` / `artifact:resize` / `artifact:error` / `artifact:theme` 외 모두 무시. `event.origin` 검사
4. **정적 코드 필터**: `import from 'https://'`, `navigator.credentials`, `document.cookie`, `localStorage`, `indexedDB` 패턴 발견 시 거부 + confirmModal 승인 필요

**릴리스 로드맵**
- v2.22.0 — `server/artifacts_lab.py` (extract/save/list/delete) + 4 라우트
- v2.23.0 — `VIEWS.artifacts` UI + 샌드박스 iframe + postMessage 프로토콜
- v2.24.0 — Babel standalone **로컬 번들** (supply chain 면역) + React/JSX 지원
- v2.24.1 — Playwright `e2e-artifacts.mjs` 5 테스트 케이스 (CSP 차단 · sandboxed origin · postMessage 필터 · 금지 패턴 · 강제 렌더)

**의사결정 (Open → Closed)**
- Babel: CDN ❌ · **로컬 번들** ✅ (공급망 안전)
- Artifact 외부 공유: **완전 불가**. 로컬 JSON export 만
- 강제 렌더: 매번 confirmModal (세션 skip 옵션 없음)

## [2.20.0] — 2026-04-23

### 💸 비용 타임라인 통합 탭 — 신규 `costsTimeline` (system 그룹)

Claude API 플레이그라운드 10종 + 워크플로우 실행 비용을 **한 화면**에 통합.

**기능**
- 상단 카드 3개: 총 비용 · 총 호출 수 · 활성 소스 (10 플레이그라운드 + workflows)
- **일별 비용 차트** (최근 60일) — SVG 수평 막대 · 소스별 스택 색상
- **소스별 집계 테이블**: 호출 수 · 토큰 in/out · USD
- **모델별 집계** (Top 20)
- **최근 30건 리스트**

**Architecture**
- `server/cost_timeline.py` 신설 — 각 `~/.claude-dashboard-*.json` 히스토리를 통합 집계
- 처리 소스 (10 + workflows):
  * promptCache / thinkingLab / toolUseLab / batchJobs / apiFiles / visionLab / modelBench / serverTools / citationsLab + workflows(store costs 배열)
- 엔트리 없는 USD 값은 `_estimate(model, ti, to)` 로 재계산 (Opus/Sonnet/Haiku 가격표)
- `server/routes.py` 라우트 1 추가 (`GET /api/cost-timeline/summary`)
- `server/nav_catalog.py` `costsTimeline` 탭 등록 (system 그룹) + en/zh
- `dist/index.html` NAV (icon 💸) + `VIEWS.costsTimeline` — SVG 스택 차트 + 3 테이블
- `tools/translations_manual_9.py` 18 키 × ko/en/zh

## [2.19.0] — 2026-04-23

### 📜 워크플로우 실행 이력 diff / 재실행

기존 `📜 이력` 모달을 확장. 각 run 카드에 **🔍 diff** + **🔄 재실행** 버튼.

**🔍 diff**
- 바로 직전 run 과 per-node 비교 테이블
- 컬럼: 노드 id · A status · A duration · B status · B duration · Δ
- 상태 변화 또는 한쪽에만 있는 노드는 하이라이트
- 상단 요약: A/B 전체 status · duration · Δ

**🔄 재실행**
- 현재 선택된 워크플로우를 즉시 재실행 (기존 `api_workflow_run` 재사용)
- SSE 폴링 자동 시작 → 배너 등장

**Architecture**
- `server/workflows.py` 신규 `api_workflow_run_diff(body: {a, b})` — 두 runId 의 `nodeResults` 비교 → node 별 status/duration Δ + onlyA/onlyB 플래그
- `server/routes.py` 라우트 1 추가 (`POST /api/workflows/run-diff`)
- `dist/index.html::_wfShowRuns` 확장: run 카드에 diff/rerun 액션
- `_wfDiffRuns(aId, bId)` / `_wfRerunWorkflow()` 신규 함수
- `tools/translations_manual_9.py` 10 키 × ko/en/zh

**스모크**
- `/api/workflows/run-diff` 신규 엔드포인트 정상
- 워크플로우 탭 "📜 이력" 모달에서 각 run 카드에 diff/재실행 버튼 노출 확인

## [2.18.1] — 2026-04-23

### Docs — README 3종 통계 갱신 (세션 4 결과 반영)

T10~T13 (v2.15.0 ~ v2.18.0) 신규 3 탭(embeddingLab + promptLibrary + Batch 가드 UI) + E2E 확장이 README 본문에 반영되도록 일괄 갱신.

- 버전 배지 v2.14.1 → **v2.18.1**
- 49 → **51 tabs / 51 탭 / 51 个标签页**
- work 그룹 테이블에 🆕 `embeddingLab` · `promptLibrary` 추가 (serverTools/citationsLab/agentSdkScaffold 는 기존으로 이동)
- Architecture 트리: routes 178 → **188**, nav 49 → **51 tabs**, locales 3,157 → **3,212 keys**
- Stats 섹션을 **v2.18.1** 기준으로 전면 갱신:
  * 백엔드 ~17k/42 → **~17,600줄/44 모듈**
  * 프론트 ~15,500줄 → **~16,300줄**
  * API 라우트 178 → **188** (GET 101 / POST 84 / PUT 3)
  * 플레이그라운드 탭 10 → **11** (+ Embedding Lab)
  * **신규 행**: Prompt Library ✓, Batch 비용 가드 ✓, E2E 테스트 스크립트 **3**
- E2E 테스트 섹션에 `test:e2e:ui` · `test:e2e:all` 추가 (smoke 51 tabs 재반영)
- README ko/en/zh 3종 동등 갱신

## [2.18.0] — 2026-04-23

### 🎭 E2E 커버리지 확장 (v2.10.x UX 회귀 방지)

**신규: `scripts/e2e-ui-elements.mjs`**

워크플로우 탭의 중요 DOM/전역 함수 무결성을 자동 검증. Anthropic API 키 없이도 동작.

**검증 항목**
1. 핵심 컨테이너 7개 (`#wfRoot` · `#wfCanvasWrap` · `#wfToolbar` · `#wfCanvasHost` · `#wfCanvas` · `#wfViewport` · `#wfMinimap`)
2. 빌트인 `bt-multi-ai-compare` 로 임시 워크플로우 생성 → `.wf-node` 6개 렌더 확인 → 자동 정리
3. **v2.10.0 UX**: `.wf-node-ring` / `.wf-node-elapsed` 각 6개 존재 · `_wfRenderRunBanner` 전역 노출 · mock running run 으로 `#wfRunBanner.visible` 부착 검증
4. **v2.10.1 UX**: `_wfToggleCat` 전역 노출
5. **v2.10.2 UX**: `_wfShowNodeTooltip` 전역 노출
6. `pageerror` / `console.error` 집계 → 하나라도 있으면 실패

**package.json scripts 추가**
- `test:e2e:ui` → `node scripts/e2e-ui-elements.mjs`
- `test:e2e:all` → smoke + ui 연속 실행

**검증 실행 결과 (v2.18.0)**
- `npm run test:e2e:ui` — 18개 체크 전부 통과
- `npm run test:e2e:smoke` — **51/51 탭 전수 통과**

## [2.17.0] — 2026-04-23

### 🚨 Batch 비용 가드 (batchJobs 확장)

Message Batches 제출 전 **예상 비용/토큰**을 계산해 임계치 초과 시 거부.

**설정**
- `~/.claude-dashboard-batch-budget.json` — `{enabled, maxPerBatchUsd, maxPerBatchTokens}`
- 기본: **disabled** · $1.00 · 100,000 tokens
- 사용자가 명시 활성화해야 작동 (기존 동작 유지)

**예상 비용 계산 (`_estimate_batch_cost`)**
- input_tokens 근사치 = Σ `len(prompt) // 4`
- output_tokens = `max_tokens × len(prompts)`
- 가격표: Opus/Sonnet/Haiku 3 모델 per-1M-token 단가
- **50% 할인 적용** (Anthropic Message Batches 공식 정책, 2026-04 기준)

**제출 시 플로우**
1. `api_batch_create` 상단에서 예상 계산
2. `budget.enabled` 이면 USD · tokens 두 임계치 모두 체크
3. 초과 시 `{ok:False, budgetExceeded:True, estimate, budget}` 반환
4. 프론트에서 confirmModal 로 차단 사유 + 예상 비용 · 토큰 상세 표시

**UI 추가**
- batchJobs 탭 상단에 **가드 상태 배너** (ON/OFF + 한도 표시 + ⚙️ 임계치 편집 버튼)
- "임계치 편집" 모달: enabled 토글 · maxPerBatchUsd · maxPerBatchTokens
- 제출 시 budgetExceeded 응답 오면 상세 모달 자동 노출

**Architecture**
- `server/batch_jobs.py` 확장: `_load_budget` · `_save_budget` · `_estimate_batch_cost` · `_PRICING` · `_BATCH_DISCOUNT=0.5` · `api_batch_budget_{get,set}`
- `api_batch_create` 에 pre-submit 가드
- `server/routes.py` 2 라우트 (GET budget · POST budget/set)
- `dist/index.html::VIEWS.batchJobs`: 가드 상태 배너 + `bjEditBudget` modal
- `bjSubmit` 에 `budgetExceeded` 분기
- `tools/translations_manual_9.py` 11 키 × ko/en/zh

## [2.16.0] — 2026-04-23

### 📝 Prompt Library — 신규 탭 `promptLibrary`

자주 쓰는 프롬프트를 태그와 함께 저장하고 검색 · 복사 · 복제 · **워크플로우로 변환** 가능한 라이브러리 탭.

**기능**
- CRUD 인라인 에디터: title · body · tags (쉼표 구분) · model
- 검색: 제목/본문/태그 substring (250ms debounce)
- 태그 chip 필터
- 카드별 액션 5개: 📋 복사 / ✏️ 수정 / 🗂️ 복제 / 🔀 워크플로우로 / 🗑️ 삭제
- 🔀 워크플로우로 — start → session(prompt) → output 3 노드 자동 생성 후 workflows 탭으로 이동
- 시드 3종 (코드 리뷰 / 회의 요약 / SQL 최적화)

**Architecture**
- `server/prompt_library.py` 신설 — `api_prompt_library_{list,save,delete,duplicate,to_workflow}` + SEED_ITEMS 3종
- 저장: `~/.claude-dashboard-prompt-library.json`
- workflows store 와 통합 (to-workflow 가 `_load_all/_dump_all/_new_wf_id` 사용)
- `server/routes.py` 5 라우트 (GET list · POST save/delete/duplicate/to-workflow)
- `server/nav_catalog.py` `promptLibrary` 탭 + en/zh
- `dist/index.html` NAV (icon 📝) + `VIEWS.promptLibrary` (에디터 + 카드 리스트 + 필터)
- `tools/translations_manual_9.py` 24 키 × ko/en/zh

## [2.15.0] — 2026-04-23

### 🧬 Embedding 비교 실험실 — 신규 탭 `embeddingLab`

같은 쿼리/문서 집합을 **Voyage AI · OpenAI · Ollama** 세 프로바이더에 돌려 cosine similarity + rank 를 비교.

**지원**
- Voyage AI — `voyage-3-large` / `voyage-3` / `voyage-3-lite` (VOYAGE_API_KEY 필요)
- OpenAI — `text-embedding-3-large` / `text-embedding-3-small`
- Ollama — `bge-m3` / `nomic-embed-text` / `mxbai-embed-large` (로컬)

**기능**
- 쿼리 1 + 문서 2~10 → 각 프로바이더 병렬 호출 → cosine + rank
- 프로바이더별 rank 나란히 + **rank Δ ≥ 2** 문서 자동 하이라이트
- 예시 2종 (FAQ 검색 / 유사 문장)
- 프로바이더별 모델 드롭다운 · 키 미설정 시 체크박스 비활성

**Architecture**
- `server/embedding_lab.py` 신설 — `api_embedding_{compare,providers,examples}`, `_cosine`, `_rank_desc`, `_voyage_embed` (stdlib HTTP)
- `ai_providers.embed_with_provider` 재사용 (OpenAI/Ollama)
- `ThreadPoolExecutor(max_workers=3)` 병렬 호출
- `server/routes.py` 3 라우트 (GET providers/examples · POST compare)
- `server/nav_catalog.py` `embeddingLab` 탭 + en/zh
- `dist/index.html` NAV (icon 🧬) + `VIEWS.embeddingLab` — 체크박스 · 인라인 모델 select · rank 테이블 · Δ 하이라이트
- `tools/translations_manual_9.py` 26 키 × ko/en/zh

## [2.14.1] — 2026-04-23

### Docs — README 3종 통계/탭 테이블 v2.14 기준 갱신

T5~T8 (v2.11.0 ~ v2.14.0) 신규 4 탭(serverTools · claudeDocs · citationsLab · agentSdkScaffold) 이 README 본문에 반영되도록 일괄 갱신.

- 배지 v2.9.1 → **v2.14.1**
- 미리보기 "45 탭" → **"49 탭"**
- Why 비교표 "45 tabs" → "49 tabs"
- Claude Code Integration 테이블:
  * 🆕 그룹에 `claudeDocs` 추가
  * 🛠️ Work 그룹에 `serverTools` · `citationsLab` · `agentSdkScaffold` 추가
- Architecture 트리: routes 168 → **178**, nav_catalog 45 → **49 tabs**, locales 3,090 → **3,157 keys**
- Stats 섹션을 v2.14.1 기준으로 갱신:
  * 백엔드 ~16,000줄/27 → **~17,000줄/42 모듈**
  * API 라우트 168 → **178** (GET 97 / POST 78 / PUT 3)
  * Claude API 플레이그라운드 탭 7 → **10**
  * **신규 행**: "공식 문서 색인 — 33 페이지"
- README ko/en/zh 3종 동등 반영

## [2.14.0] — 2026-04-23

### 🧪 Agent SDK 스캐폴드 — 신규 탭 `agentSdkScaffold`

`claude-agent-sdk` 기반 Python / TypeScript 프로젝트 뼈대를 UI 에서 생성 + Terminal 새 창에 초기화 명령 자동 붙여넣기.

**언어 · 도구**
- **Python** — `uv` (대체 제안: `brew install uv`)
- **TypeScript** — `bun` (대체 제안: `curl -fsSL https://bun.sh/install | bash`)

**템플릿 3종**
- `basic` — Messages API 1회 호출 + 응답 출력
- `tool-use` — tool 정의 + `tool_use → tool_result` 라운드 트립 (가짜 weather)
- `memory` — 대화 히스토리 JSON 저장

**생성 결과**
- `<path>/<name>/main.py` (py) 또는 `index.ts` (ts)
- `pyproject.toml` / `package.json` — uv sync / bun install 시 실제 의존성 설치
- `README.md` · `.gitignore`
- AppleScript 로 Terminal 새 창 열림 + `cd <path>/<name> && uv sync` (또는 `bun install`) 명령 **붙여넣기** (Enter 는 사용자가 누름)

**안전 장치**
- `name` 은 `[a-zA-Z][a-zA-Z0-9_-]{1,63}` 만 (path traversal 방지)
- `path` 는 `$HOME` 내부만
- `<path>/<name>` 이 이미 있으면 거부
- `uv`/`bun` 없으면 친절한 설치 힌트 포함 에러 (자동 설치 금지)

**Architecture**
- `server/agent_sdk_scaffold.py` 신설 — `api_scaffold_{catalog,create}` + 템플릿 본문 inline (python / ts × 3종)
- `server/routes.py` 2 라우트 (GET catalog · POST create)
- `server/nav_catalog.py` `agentSdkScaffold` 탭 (work 그룹) + en/zh
- `dist/index.html` NAV (icon 🧪) + `VIEWS.agentSdkScaffold` + `scCreate/scSet/scReset/openFolderFromPath`
- `tools/translations_manual_9.py` 25 키 × ko/en/zh

**한계**
- macOS 전용 (AppleScript Terminal). Linux/Windows 는 생성만 되고 Terminal 스폰은 실패 — 결과 카드에 `next command` 를 복사할 수 있도록 노출.

## [2.13.0] — 2026-04-23

### 📑 Citations 플레이그라운드 — 신규 탭 `citationsLab`

Anthropic Messages API 의 `citations.enabled` 응답 모드 실습. 문서를 `content` 의 document 블록으로 제공 + `citations: {enabled: true}` 를 세팅하면 답변 text block 에 `citations: [{cited_text, start_char_index, end_char_index, ...}]` 배열이 포함된다.

**기능**
- 예시 2종: 회사 소개문 / 기술 아티클
- 모델(Opus/Sonnet), 문서 제목(선택), 문서 본문 textarea, 질문 입력
- 답변 렌더링: 각 citation 을 `[N]` 번호 pill 로 본문 뒤에 inline 추가
- `[N]` hover → 원문 패널에서 해당 `start/end_char_index` 구간을 `<mark>` 로 하이라이트
- 히스토리 최근 20건 (`~/.claude-dashboard-citations-lab.json`)

**Architecture**
- `server/citations_lab.py` 신설 — `api_citations_{test,examples,history}` · examples 2 · text-type document 블록 구성
- `server/routes.py` 3 라우트 (GET examples/history · POST test)
- `server/nav_catalog.py` `citationsLab` 탭 (work 그룹) + en/zh desc
- `dist/index.html` NAV (icon 📑) + `VIEWS.citationsLab` · `ciHoverCit` · `ciLoadExample` · `ciRun` · `ciReset` · `ciSet`
- `tools/translations_manual_9.py` 17 키 × ko/en/zh

**한계 / 후속**
- 현재는 **text source** 만 지원. PDF / base64 document 는 T+N 에서 확장 예정.
- `page_location` citation 타입은 PDF 입력에서만 나타나므로 현 UI 는 `char_location` 중심.

## [2.12.0] — 2026-04-23

### 📖 Claude Docs Hub — 신규 탭 `claudeDocs` (new 그룹)

docs.anthropic.com 의 주요 페이지를 대시보드 안에서 카테고리별 카드로 색인 + 검색.

**카테고리 5**
- **Claude Code** — Overview / Sub-agents / Skills / Hooks / MCP / Plugins / Output Styles / Status Line / Slash Commands / Memory / Interactive / IAM / Settings / Troubleshooting (14)
- **Claude API** — Messages / Prompt Caching / Extended Thinking / Tool Use / Message Batches / Files / Vision / Citations / Web Search Tool / Code Execution Tool / Embeddings (11)
- **Agent SDK** — Overview / Python / TypeScript (3)
- **Models** — Models / Deprecations / Pricing (3)
- **Account & Policy** — Team / Glossary (2)

총 **33개 공식 페이지** 카드.

**기능**
- 제목/요약/URL 필터 (300ms debounce)
- 각 카드 2 버튼: `🔗 외부 열기` · `→ 관련 탭` (해당하는 대시보드 탭 id 가 있으면 `go(...)` 호출)
- 결과 없으면 친절한 empty state

**Architecture**
- `server/claude_docs.py` 신설 — 정적 `CATALOG` dict + `api_claude_docs_{list,search}`
- `server/routes.py` 2 라우트 (GET list/search)
- `server/nav_catalog.py` `claudeDocs` 탭 등록 (`new` 그룹) + en/zh
- `dist/index.html` NAV (icon 📖) + `VIEWS.claudeDocs` · `cdSet` · `cdRender` (debounce)
- `tools/translations_manual_9.py` 7 키 × ko/en/zh

**주의**
- URL 은 2026-04 시점 기준 추정. Anthropic 이 경로를 바꾸면 `CATALOG` 만 갱신하면 됨.

## [2.11.0] — 2026-04-23

### 🧰 Claude 공식 내장 Tools 플레이그라운드 — 신규 탭 `serverTools`

Anthropic 서버가 **직접 실행하는 hosted tool** 실습 탭. 기존 `toolUseLab` 이 사용자가 tool_result 를 수동 공급하는 구조라면, 이건 Anthropic 이 tool 을 실행하고 결과를 포함한 응답을 돌려준다.

**지원 도구**
- 🌐 **web_search** (`web_search_20250305`, beta `web-search-2025-03-05`) — 웹 검색 + citation
- 🧪 **code_execution** (`code_execution_20250522`, beta `code-execution-2025-05-22`) — Python sandbox (stdout / stderr / return_code)

**기능**
- 도구 체크박스 (model supportedModels 가드 — Haiku 비활성)
- 모델 선택 (Opus / Sonnet) + max_tokens
- 예시 3종 (뉴스 검색 / Python 계산 / 검색+분석 결합)
- 응답 content 블록 분류 시각화:
  * `server_tool_use` — 보라 카드 (tool 입력 JSON)
  * `*_tool_result` — 초록 카드 (실행 결과)
  * `text` — 최종 응답
- 히스토리 최근 20건 (`~/.claude-dashboard-server-tools.json`)

**Architecture**
- `server/server_tools.py` 신설 — `api_server_tools_{catalog,history,run}` + `TOOL_CATALOG` (beta 헤더 중앙화) + `EXAMPLES` 3종
- `server/routes.py` 3 라우트 추가 (GET catalog/history · POST run)
- `server/nav_catalog.py` `serverTools` 탭 등록 + en/zh desc
- `dist/index.html` NAV (icon 🧰) + `VIEWS.serverTools` + `stRun/stToggleTool/stLoadExample/stReset/stSet`
- `tools/translations_manual_9.py` 17 키 × ko/en/zh

**주의**
- beta header 스펙은 2026-04 시점 추정. Anthropic 에서 바뀌면 `TOOL_CATALOG[*].beta` 만 갱신.
- `web_search` / `code_execution` 호출은 별도 과금.

## [2.10.4] — 2026-04-23

### Fixed — v2.10.3 스모크 테스트 실행으로 드러난 2건

**1. `VIEWS.team` — `TypeError: t is not a function`**
team 탭 진입 시 `VIEWS.team` 이 로컬 변수 `const [t, auth] = ...` 로 전역 `t(key)` i18n 함수를 **섀도잉** → 이후 `${t('내 계정')}` 같은 모든 i18n 호출이 TypeError 로 실패.

- `VIEWS.team` 의 로컬 변수 `t` → **`team`** 으로 rename
- 본문 11개 참조 지점 (`t.displayName`, `t.organizationUuid`, `t.note` 등) 모두 갱신
- 주석으로 "전역 `t` 섀도잉 금지" 명기

이 버그는 사용자가 team 탭을 열었다면 즉시 드러났을 텐데, 수동으로 접속할 일이 적어 회귀로 남아 있었음. **E2E smoke 가 없었다면 찾기 어려웠을 회귀.**

**2. `scripts/e2e-tabs-smoke.mjs` — 오탐 가능 구조**
`document.querySelector('main')?.innerText` 에 "뷰 렌더 실패" / "View render failed" 문자열이 있는지 단순 포함 검사 → `memory` 탭에 메모리 노트 내용(ex. `feedback_escape_html_helper.md`)의 문자열이 포함되어 **정상 렌더를 실패로 오탐**.

- 검사 조건을 `#view .card.p-8.empty` element 존재 여부로 **엄격화**. `renderView()` catch 블록이 렌더하는 에러 카드만 검출 → 본문 텍스트 충돌 제거.
- 네비게이션을 `window.state.view = ...` → `location.hash = '#/<tab>'` (go() 와 동일 경로) 로 변경. 이전엔 전역 `state` 변수가 `window` 에 노출 안 돼 **실제 뷰 전환이 안 된 채 45 탭이 전부 통과** 하는 false-positive 가 있었음 → 이번 smoke 로 최초 true positive 확인.

**3. `package.json` — `"type": "module"` 제거**
v2.10.3 에서 추가했던 `"type": "module"` 이 기존 CommonJS 스크립트 `scripts/verify-translations.js` (`require` 사용) 를 깨뜨림. `.mjs` 파일은 명시 확장자로 ESM 처리되므로 `"type"` 필드 없이도 충분. 제거.

**결과**
- `HEADLESS=1 npm run test:e2e:smoke` → 45/45 탭 **실제 전수 통과**
- `npm run verify:i18n` → 3,096 키 × 3언어 · 0 누락

## [2.10.3] — 2026-04-23

### 🎭 Playwright E2E 스모크 스크립트

자동화 테스트로 회귀 방지. 모든 스크립트는 **라이브 서버(127.0.0.1:8080)** 를 대상으로 동작.

**scripts/e2e-tabs-smoke.mjs** (45 탭 전수 검사)
- `server/nav_catalog.py::TAB_CATALOG` 를 정적 파싱해 탭 id 목록 추출
- 각 탭으로 `window.state.view` 전환 + `renderView()` 호출 후
  - "뷰 렌더 실패" / "View render failed" 텍스트 검출 시 실패
  - `console.error` 발생 시 실패
- 단일 탭 검사: `TAB_ID=workflows npm run test:e2e:smoke`

**scripts/e2e-workflow.mjs** (빌트인 템플릿 실행 E2E)
- `bt-multi-ai-compare` 템플릿 조회 → `POST /api/workflows/save` 로 E2E 워크플로우 생성 → `POST /api/workflows/run`
- 5초간 `run-status` 폴링 + `#wfRunBanner.visible` 등장 여부 체크
- 완료 후 `POST /api/workflows/delete` 로 자동 정리
- critical error (`is not defined`, `View render failed`, `뷰 렌더 실패`) 발견 시 실패

**package.json**
- `scripts.test:e2e:smoke` / `test:e2e:workflow` / `test:e2e:headed` / `verify:i18n`
- `name`, `type:"module"`, `private:true` 추가 (ESM 스크립트 지원)

**.gitignore**
- `test-results/`, `playwright-report/`, `playwright/.cache/`, `node_modules/`

**README 3종**: `🎭 E2E 테스트` 섹션 (Troubleshooting 과 Contributing 사이) — `npx playwright install chromium` 안내 + 스크립트 사용법.

**주의**
- 최초 실행 전 `npx playwright install chromium` 필요 (약 150MB).
- 서버가 기동 중이 아니면 timeout 후 실패 — 테스트 실행 전 수동 기동.

## [2.10.2] — 2026-04-23

### 💬 노드 hover 결과 tooltip

실행 이력이 있는 노드에 마우스 hover 시 결과 미리보기 tooltip.

**내용**
- 상태 아이콘(✅/❌/⏳/⏭️) + 노드 제목 + 상태 라벨
- 소요 시간 (running 노드는 startedAt 기반 실시간, ok/err 는 durationMs)
- 제공자 · 모델 (있으면)
- 입력/출력 토큰 (있으면)
- 출력 미리보기 (앞 160자) 또는 에러 메시지 (앞 260자)

**UX**
- 280ms debounce → 손을 살짝 stop 시에만 노출, 지나갈 때는 안 뜸
- 마우스 이동 시 위치 따라감 (화면 경계 감지)
- 노드에서 벗어나면 즉시 숨김 (단 related target 이 다른 노드면 유지)
- 실행 이력 없는 노드는 표시 안 함 (노이즈 최소화)
- 상태별 left border 색 (ok 초록 / err 빨강 / running 보라 / skipped 회색)

**Architecture**
- `dist/index.html`:
  * CSS: `#wfNodeTooltip` + 상태별 variant
  * JS: `_wfShowNodeTooltip(nid, evt)` · `_wfHideNodeTooltip()` · delegation IIFE (mouseover/mousemove/mouseout)
- `tools/translations_manual_9.py`: 3 키 × ko/en/zh (건너뜀 / 제공자 / 토큰)

## [2.10.1] — 2026-04-23

### 🪟 노드 편집 모달 — 카테고리 그리드 접기

사용자 피드백 스크린샷: 노드 편집 모달 하단의 제목/모델/subject 등 필드가 항상 스크롤해야만 보임.

**원인**: `_wfRenderEditorBody` 가 타입 선택 여부와 무관하게 16개 노드 타입 그리드를 3열 × 4~6행으로 **항상 펼쳐서** 표시 → 720px 모달에서 약 160~200px(25~30%) 를 카테고리가 점유.

**수정**
- **기존 노드 편집** (type 이미 세팅): 기본 **접힘** — `[아이콘] [타입 라벨] 칩 · ▸ 타입 변경` 한 줄(≈48px)만 표시. 폼 영역에 +110~150px 추가 확보.
- **신규 노드 추가** (type 없음): 기본 **펼침** (기존 UX 유지).
- **타입 선택 직후 자동 접힘** + 첫 입력 필드(제목/subject 등) autofocus.
- **토글 버튼** `▾ 접기` / `▸ 타입 변경` (tooltip: `Alt+C`).
- **단축키** `Alt+C` — 워크플로우 탭에서 노드 편집 창이 열려 있을 때 토글.
- **localStorage 기억** (`wfEditorCatExpanded`): 사용자 취향 영속.

**Architecture**
- `dist/index.html`:
  * `_wfCatIsExpanded(draft)` · `_wfToggleCat(winId)` 신규
  * `_wfRenderEditorBody` 가 expanded 분기로 재구성 (접힘 시 칩 + 변경 버튼)
  * `_wfPickNodeType` 종료 후 localStorage 접힘 + first-field autofocus
  * 워크플로우 키보드 핸들러에 `Alt+C` 토글 분기 추가
- `tools/translations_manual_9.py`: 4 키 × ko/en/zh (타입 / 타입 변경 / 접기 / 펼치기)

## [2.10.0] — 2026-04-23

### 🔦 워크플로우 실행 가시성 강화

사용자 피드백: "**워크플로우가 지금 어느 노드에서 실행 중인지 보기 어렵다**".

기존 `data-status` CSS 는 작동했지만 시각적 강조가 약했고, 큰 캔버스에서 running 노드가 화면 밖이면 전혀 알 수 없었음.

**상단 플로팅 실행 배너 (신규)**
- `#wfRunBanner` — 캔버스 상단 중앙 고정
- 포맷: `⏳ [노드명] · {완료}/{전체} · {경과초}s · 진행률 바 · 📍 위치로 이동`
- 상태별 색: running (보라 · pulse) / ok (초록) / err (빨강)
- 완료·실패 3.5초 후 자동 페이드아웃
- 수동 닫기 버튼

**Running 노드 시각 강화**
- 외곽 점선 링 (`.wf-node-ring`, stroke-dasharray 6 6) + 회전 애니메이션 (`@keyframes wfSpinDash`, 2.5s linear)
- `drop-shadow` 보라 글로우 추가
- 라벨 옆 `⏱ {초}s` 실시간 카운터 (`.wf-node-elapsed`)

**미니맵 상태 색 반영**
- running/ok/err/skipped 색을 node dot 에 우선 적용
- running 노드는 dot 크기 3px → 5px 로 강조

**서버 SSE 폴링 1.0s → 0.5s**
- `handle_workflow_run_stream`: `time.sleep(0.5)` + `max_polls = 3600` (30분 유지)
- 서버 노드 실행 시작 시 `nodeResults[nid].startedAt` 기록 → 프론트 elapsed 계산

**위치로 이동 (`_wfFocusNode`)**
- 배너의 📍 버튼 또는 직접 호출로 해당 노드를 뷰포트 중앙에 pan (zoom 유지)

**i18n** — 6 키 × ko/en/zh (실행 중 / 대기 중 / 완료 / 실패 / 위치로 이동 / 닫기). 총 **3,092 키** · 누락 0.

**Architecture**
- `server/workflows.py`: `handle_workflow_run_stream` sleep 0.5s, `_run_one_iteration` running 상태에 `startedAt` 포함
- `dist/index.html`:
  * CSS: `#wfRunBanner` 스타일, `.wf-node-ring` / `.wf-node-elapsed` 추가, `wfSpinDash` keyframe
  * JS: `_wfApplyRunStatus` 확장 (배너/미니맵 호출), `_wfRenderRunBanner`, `_wfHideRunBanner`, `_wfFocusNode` 신규
  * `_wfRenderNode` SVG 템플릿에 `<rect class="wf-node-ring">` + `<text class="wf-node-elapsed">` 삽입
  * `_wfRenderMinimap` node dot 에 실행 상태 색 우선 적용
- `tools/translations_manual_9.py`: 6 키 ko/en/zh
- `dist/locales/{ko,en,zh}.json`: 3,092 키 재빌드

## [2.9.3] — 2026-04-23

### Fixed — 빌트인 워크플로우 템플릿 조회 실패 (404 → "템플릿 생성 에러")

사용자 리포트: **"멀티 AI 비교 커스텀 템플릿을 사용하려는데 error 라고 나오면서 안 생성돼"**.

**원인**
`server/routes.py::_ITEM_GET_ROUTES` 의 템플릿 단일 조회 정규식이 `(tpl-[0-9]{10,14}-[a-z0-9]{3,6})` 로 **커스텀 템플릿 id 포맷만 허용**하고 있었다. `workflows.py::BUILTIN_TEMPLATES` 의 id 는 `bt-multi-ai-compare / bt-rag-pipeline / bt-code-review / bt-data-etl / bt-retry-robust` 5종으로 전혀 다른 포맷이라 매칭 실패 → `GET /api/workflows/templates/bt-multi-ai-compare` 가 계속 **404**. 프론트의 템플릿 상세 fetch 가 실패해 워크플로우 생성이 중단됨.

`api_workflow_template_get` 핸들러 자체는 이미 `BUILTIN_TEMPLATES` 먼저 조회 후 fallback 으로 custom 저장소를 뒤지는 올바른 구조였음 — 라우트 레이어에서 도달조차 못 하던 문제.

**수정**
- `server/routes.py` 정규식을 `(tpl-[0-9]{10,14}-[a-z0-9]{3,6}|bt-[a-z0-9-]+)` 로 확장해 두 id 포맷 모두 허용.

**검증**
5개 빌트인 템플릿 전수 스모크:
- `bt-multi-ai-compare` (멀티 AI 비교, 6 nodes) ✓
- `bt-rag-pipeline` (RAG 파이프라인, 5 nodes) ✓
- `bt-code-review` (코드 리뷰, 5 nodes) ✓
- `bt-data-etl` (데이터 ETL, 5 nodes) ✓
- `bt-retry-robust` (재시도, 5 nodes) ✓

모두 `ok: True`, 정확한 노드 수 반환.

## [2.9.2] — 2026-04-23

### Docs — README 3종 통계/탭 테이블 전면 갱신

v2.3.0 ~ v2.9.1 누적 결과를 README 의 본문 섹션에 반영 (그간 상단 배너만 추가하고 본문 통계가 v2.1.1 로 남아있었음).

- 버전 배지 **v2.9.0 → v2.9.1**
- ASCII 미리보기 표기 "6 그룹 38 탭" → **"6 그룹 45 탭"**
- "Why" 비교 표 셀 "38 탭" → **"45 탭"**
- `🤝 Claude Code Integration` 탭 테이블의 work 그룹에 신규 7 탭(`promptCache` `thinkingLab` `toolUseLab` `batchJobs` `apiFiles` `visionLab` `modelBench`) 🆕 표시로 추가 + "Claude API 플레이그라운드" 하이라이트 줄 추가
- Architecture 트리: `routes.py` 143 → **168 라우트**, `nav_catalog.py` 38 → **45 탭**, `locales` 2,932 → **3,090 키**
- `🔢 Stats (v2.1.1)` 섹션 전체를 **`v2.9.1`** 기준으로 갱신:
  - 백엔드 14,067줄/20 모듈 → **~16,000줄/27 모듈**
  - 프론트 ~13,500줄 → **~15,500줄**
  - API 라우트 143 → **168 (GET 90 / POST 75 / PUT 3)**
  - 탭 38 → **45**
  - i18n 키 2,932 → **3,090**
  - 신규 행: "Claude API 플레이그라운드 탭 — 7"
- README.md / README.ko.md / README.zh.md 3종 동등 구조로 반영.

## [2.9.1] — 2026-04-23

### Fixed — v2.3.0~v2.9.0 신규 탭 렌더 실패 + NAV desc 번역 누락

**`_escapeHTML is not defined` 런타임 에러 해소**
- v2.3.0~v2.9.0 에서 추가한 7개 VIEWS (`promptCache`, `thinkingLab`, `toolUseLab`, `batchJobs`, `apiFiles`, `visionLab`, `modelBench`) 가 **존재하지 않는 `_escapeHTML()`** 을 참조해 탭 진입 즉시 "View render failed" 에러가 나던 문제.
- 저장소 실제 헬퍼 이름은 **`escapeHtml`** (소문자 HTML 중 H 만 대문자).
- `dist/index.html` 에서 `_escapeHTML(` → `escapeHtml(` 21곳 일괄 치환.

**i18n 14건 누락 번역 보강**
- NAV `desc` 7개 (work 그룹 신규 탭들) — `escapeHtml(t(n.desc))` 경로에 번역이 없어 한국어 원문이 영/중문 모드에서도 그대로 노출되던 문제.
- `confirmModal` 메시지 템플릿 (`총 {n} 건을 ...`, `회 API 호출을 수행합니다 (...`) 의 한글 조각들을 extractor 가 잘못 뽑아 missing 이던 7건.
- `tools/translations_manual_9.py::NEW_EN` / `NEW_ZH` 에 14 키 × 2언어 추가.
- 결과: `build_locales.py` **Missing EN/ZH 0** · `verify-translations.js` 전체 통과 (3,090 키 × 3언어).

## [2.9.0] — 2026-04-23

### 🏁 Model Benchmark — 신규 탭 (work 그룹)

사전 정의 프롬프트 셋 × 선택한 모델들을 교차 실행해 성능·비용을 집계한다.

**기능**
- 프롬프트 셋 3종: 기본 Q&A(5) / 코드 생성(3) / 추론·수학(3)
- 모델 3개 체크박스 (Opus 4.7 / Sonnet 4.6 / Haiku 4.5)
- 실행 전 confirmModal 로 총 호출 수 · 비용 발생 경고
- ThreadPoolExecutor(max_workers=4) 로 prompt × model 조합 병렬 실행
- 모델별 집계 표: 성공 건수 · 평균 지연 · 평균 출력 토큰 · 총 비용(USD)
- 개별 응답 매트릭스 (모델 · 프롬프트 · 응답 미리보기 · 지연 · 비용)
- JSON 다운로드 버튼

**Architecture**
- `server/model_bench.py` 신설 — `api_model_bench_{sets,run}` + `_call_once` + `_PRICING` 테이블
- `server/routes.py` — 2개 라우트 추가
- `server/nav_catalog.py` — `modelBench` 탭 등록 + en/zh desc
- `dist/index.html` — NAV + `VIEWS.modelBench`
- `tools/translations_manual_9.py` — 28 키 × ko/en/zh

### 📜 v2.3 ~ v2.9 로드맵 완료

2026-04-23 연속 릴리스로 **Claude API 플레이그라운드 7 탭**을 work 그룹에 추가: `promptCache`(v2.3.0) · `thinkingLab`(v2.4.0) · `toolUseLab`(v2.5.0) · `batchJobs`(v2.6.0) · `apiFiles`(v2.7.0) · `visionLab`(v2.8.0) · `modelBench`(v2.9.0). 원격 v2.2.1 위에 rebase 된 결과 버전 번호를 한 칸 shift 했다.

---

## [2.8.0] — 2026-04-23

### 👁️ Vision / PDF Lab — 신규 탭 (work 그룹)

이미지(PNG/JPG/WebP/GIF) 또는 PDF 를 업로드해 Opus / Sonnet / Haiku 3 모델에 병렬 질의 → 응답 비교.

**기능**
- 파일 선택 → 자동 base64 인코딩 (최대 10MB)
- 이미지: `type:"image"` 블록, PDF: `type:"document"` 블록으로 content 구성
- 3 모델을 **ThreadPoolExecutor** 로 병렬 호출
- 각 모델별 응답/지연/토큰 사용량 카드 나란히 표시
- 총 소요 시간 + 모델 수 요약

**Architecture**
- `server/vision_lab.py` 신설 · `server/routes.py` 라우트 2개 · NAV + `VIEWS.visionLab` · 16 i18n 키 × 3언어

---

## [2.7.0] — 2026-04-23

### 📎 Files API — 신규 탭 (work 그룹)

Anthropic Files API 업로드/목록/삭제 + 메시지 document reference 를 UI 에서 다룬다.

**기능**
- 브라우저 파일 선택 → base64 전송 → 서버 multipart/form-data → Anthropic 업로드 (최대 30MB)
- 업로드된 파일 목록 (filename · size · mime · id)
- 파일 선택 → 모델 선택 → 질문 → `{type:"document", source:{type:"file", file_id}}` 블록으로 질의
- 개별 삭제 + 삭제 전 확인 모달

**Architecture**
- `server/api_files.py` 신설 · stdlib multipart POST 유틸 · 라우트 4개 (GET list · POST upload/delete/test)
- beta header: `anthropic-beta: files-api-2025-04-14`
- i18n 22 키 × 3언어

---

## [2.6.0] — 2026-04-23

### 📦 Batch Jobs — 신규 탭 (work 그룹)

Anthropic Message Batches API 로 대용량 프롬프트 병렬 제출·상태 폴링·JSONL 결과 다운로드.

**기능**
- 원클릭 예시 2종: Q&A 10건 / 요약 5건
- 모델 + max_tokens 조절 · 프롬프트 한 줄당 1건 (최대 1000건)
- 제출 전 **비용 발생 경고** 모달 (confirmModal)
- 최근 배치 목록 + 상태 + request_counts · JSONL 결과 프리뷰
- 진행 중 배치 취소 지원

**Architecture**
- `server/batch_jobs.py` 신설 · 라우트 6개 (GET examples/list/get/results · POST create/cancel)
- beta header: `anthropic-beta: message-batches-2024-09-24`
- i18n 30 키 × 3언어

---

## [2.5.0] — 2026-04-23

### 🛠️ Tool Use Playground — 신규 탭 (work 그룹)

Anthropic Tool Use 의 라운드 트립(user → tool_use → tool_result → next turn)을 수동으로 연습.

**기능**
- 기본 도구 템플릿 3종 원클릭: `get_weather` / `calculator` / `web_search` (mock)
- tools JSON 배열 직접 편집
- 대화 버블 (role · text · tool_use · tool_result 구분 색)
- tool_use 수신 시 인라인 tool_result 입력 폼 → 제출 → 다음 턴 자동 호출
- "새 대화" 버튼으로 messages 초기화

**Architecture**
- `server/tool_use_lab.py` 신설 · 라우트 3개 · i18n 13 키 × 3언어
- 히스토리 `~/.claude-dashboard-tool-use-lab.json`

---

## [2.4.0] — 2026-04-23

### 🧠 Extended Thinking Lab — 신규 탭 (work 그룹)

Claude Opus 4.7 / Sonnet 4.6 의 Extended Thinking 을 실험하고 thinking block 을 분리 시각화.

**기능**
- 원클릭 예시 3종: 수학 추론 / 코드 디버깅 / 설계 플래닝
- `budget_tokens` 슬라이더 (1024 ~ 32000, 512 단위)
- thinking block 과 최종 응답을 **접기/펴기** 로 분리 표시
- Haiku 선택 시 비지원 경고
- 히스토리 최근 20건

**Architecture**
- `server/thinking_lab.py` 신설 · 라우트 4개 (GET examples/history/models · POST test)
- i18n 16 키 × 3언어

---

## [2.3.0] — 2026-04-23

### 🧊 Prompt Cache Lab — 신규 탭 (work 그룹)

Anthropic Messages API 의 `cache_control` 을 실험/관측하는 전용 플레이그라운드.

**기능**
- 원클릭 예시 3종: 시스템 프롬프트 캐시 / 대용량 문서 캐시 / 도구 정의 캐시
- 모델 선택 (Opus 4.7 / Sonnet 4.6 / Haiku 4.5) + max_tokens 조절
- system / tools / messages JSON 편집기
- 응답 즉시: input / output / cache_creation / cache_read 토큰 + USD 비용 + 캐시 절감 추정
- 히스토리 최근 20건 (`~/.claude-dashboard-prompt-cache.json`)

**Architecture**
- `server/prompt_cache.py` 신설 (297줄) — `api_prompt_cache_test/history/examples` + `_estimate_cost` (3 모델 가격 테이블)
- `server/routes.py` — 라우트 3개 (GET examples/history · POST test)
- `server/nav_catalog.py` — `promptCache` 탭 등록 + en/zh desc
- `dist/index.html` — NAV + `VIEWS.promptCache`
- `tools/translations_manual_9.py` — 35 키 × ko/en/zh


## [2.2.1] — 2026-04-22

### Fixed — 타이틀 리터럴 노출 + 위자드 테스트 오류

- **`ai_providers_title`/`ai_providers_subtitle` 리터럴 노출 수정** — 기존 `t(ko)` 함수가 1-인자만 받아 `t('ai_providers_title','AI 프로바이더')` 호출 시 fallback 을 무시하고 키 그대로 반환하던 문제. `t(key, fallback)` 2-인자 시그니처로 확장. ko 모드에서 구조화 키(영문 only) 가 오면 fallback 우선 사용.
- **`api_auth_login` NameError 수정** — `server/auth.py:170` 에서 `platform.system()` 호출하면서 `import platform` 이 누락돼 `/api/auth/login` 이 항상 500 을 반환하던 문제.
- **위자드 연결 테스트 UX 개선** — 테스트 결과에 응답 프리뷰(앞 80자) 표시, 404/unknown route 오류 시 "대시보드 서버를 재시작하면 최신 기능이 적용됩니다" 힌트 추가. 신규 라우트가 반영되지 않은 스테일 서버 상태를 사용자가 즉시 인지 가능.
- i18n: 신규 1개 키(ko/en/zh). 총 2,950 키 유지 (audit items 1806→1807).

## [2.2.0] — 2026-04-22

### 🎯 v2.2 — 프로바이더 탭 3종 개선

**프로바이더 CLI 감지 견고화**
- `server/ai_providers.py` 에 `_which()` 헬퍼 신설 — `shutil.which` PATH 탐지 실패 시 `/opt/homebrew/bin`·`~/.local/bin`·nvm/asdf node 버전 디렉터리 등 **11개 fallback 경로** 전수 검색. LaunchAgent·GUI 런치 등 PATH 가 좁혀진 환경에서도 Claude/Codex/Gemini/Ollama CLI 를 정확히 감지.
- `ClaudeCliProvider._bin`, `OllamaProvider._bin`, `GeminiCliProvider._bin`, `CodexCliProvider._bin`, `CustomCLIProvider._bin`, 임베딩 실행 경로 모두 `_which()` 로 교체.

**CLI 설치·로그인 원클릭 (신규)**
- 신규 모듈 `server/cli_tools.py` — 4종 CLI 설치·상태·로그인 통합 관리.
  - `GET /api/cli/status` — 4종(claude/codex/gemini/ollama) 설치 여부·버전·경로 + brew/npm 가용성 반환
  - `POST /api/cli/install` — brew 우선 → npm → 설치 스크립트 자동 선택, AppleScript 로 Terminal 열어 **대화형 설치 수행**
  - `POST /api/cli/login` — `claude auth login` / `codex login` / `gemini` 최초 실행 등을 터미널에서 실행
- 설치 방법 카탈로그: `brew install --cask claude-code` · `npm install -g @openai/codex` · `npm install -g @google/gemini-cli` · `curl ... ollama.com/install.sh`
- AI 프로바이더 탭의 CLI 카드에 상태 배지 추가:
  - 미설치 → `⬇️ 설치 (Homebrew|npm)` 버튼 · 클릭 시 터미널 열림, 10초마다 설치 감지 폴링(최대 5분)
  - 설치 완료 → `✅ 설치 완료 · <버전>` + `🔐 로그인` 버튼

**UI 간소화**
- AI 프로바이더 탭 하단 "💡 워크플로우 & 프로바이더 사용 가이드" 섹션 전체 제거(~50줄 삭제) — 별도 탭의 튜토리얼·노드 카탈로그와 중복.

**i18n**
- `translations_manual_9.py` 에 CLI 설치/로그인 문구 14개 키 등록(EN/ZH). ko/en/zh 각 **2,950 키** · 누락 0 · 한글 잔존 0.

## [2.1.4] — 2026-04-22

### Fixed — 설정 드롭다운 테마 3종 번역 누락
- `Midnight`/`Forest`/`Sunset` 테마 라벨이 하드코딩 영문으로 박혀 있어 ko/zh 선택 시에도 번역되지 않던 문제 수정.
- `dist/index.html` 설정 드롭다운 3개 버튼에 `data-i18n="settings.midnight|forest|sunset"` 속성 추가 (KO 기본값: 미드나잇/포레스트/선셋).
- `tools/translations_manual.py::MANUAL_KO` + `tools/translations_manual_9.py::NEW_EN/NEW_ZH` 에 구조화 키 + 한글-텍스트 키(`미드나잇 → Midnight/午夜`) 동시 등록 → `data-i18n` 경로와 text-node 스캐너 경로 양쪽 대응.
- 결과: ko/en/zh 각 **2,936 키** · 누락 0 · 한글 잔존 0 (기존 2,932 → +4).

## [2.1.3] — 2026-04-22

### Fixed — 워크플로우 탭 UX 정리
- **우측 하단 빈 박스 제거** — 워크플로우 미선택·빈 워크플로우 상태에서 `#wfMinimap` canvas 컨테이너(회색 박스)가 보이던 문제 수정. 기본 `display:none` + `_wfRenderMinimap()` 이 nodes 존재 시에만 표시하도록 변경.
- **캔버스 높이 캡 해제** — `#wfRoot` 의 `height: min(calc(100vh - 160px), 680px)` 캡을 제거하고 `calc(100vh - 230px)` 로 변경. 큰 모니터에서 680px 에 갇혀 스크롤해야 보이던 문제 해소 → 전체 워크플로우가 한눈에 보임.

## [2.1.2] — 2026-04-22

### Docs — 퍼블릭 배포용 README 3종 전면 재작성 + LICENSE 추가
- `README.md` / `README.ko.md` / `README.zh.md` 를 v2.1.1 통계 기준으로 동등 구조(305줄)로 재작성.
- 신규 섹션: Why(전/후 비교 표) · Use Cases(5 시나리오) · Troubleshooting 표 · Quick Start 30초 · Data Stores 표 · Tech Stack · Contributing 7단계.
- 통계 갱신: API 라우트 138 → **143**, i18n 2,893 → **2,932**, 서브에이전트 16 역할 프리셋·38 탭·18 튜토리얼·Rate Limiter 등 v2.1.x 신규 지표 반영.
- 배지 추가: Python 3.10+ · License · Version · Zero Dependencies.
- `LICENSE` 파일 신규 (MIT) — README 의 `./LICENSE` 링크가 404 였던 문제 수정.

## [2.1.1] — 2026-04-22

### Fixed — i18n 잔존 39건 전수 해소
- v2.1.0 신규 기능(HTTP/transform/variable/subworkflow/embedding/loop/retry/error_handler/merge/delay 노드 설명, AI 프로바이더 UI, Modelfile 편집 등)에서 누락됐던 **UI 문구 39개** 를 `translations_manual_9.py::NEW_EN`/`NEW_ZH` 에 등록.
- `tools/translations_manual.py` 에 `_EXTRACTOR_NOISE_OVERRIDES` 추가 — `const _KO_RE = /[가-힣]/` 같이 기존 MANUAL_EN 에 한글 원문으로 고정돼 있던 JS 리터럴을 유니코드 이스케이프(`가-힣`)로 override.
- 결과: **ko/en/zh 각 2,932 키 · 누락 0 · 영문/중문 한글 잔존 0** (origin 대비 값 회귀 0건).

## [2.1.0] — 2026-04-22

### 🎯 v2.1 — 미구현 23개 항목 전면 완료

**백엔드**
- 📌 **변수 스코프 시스템** — variable 노드에 글로벌/로컬 스코프 + `{{변수명}}` 템플릿 치환
- 🔀 **조건부 실행 11종** — contains/equals/not_equals/greater/less/regex/length_gt/length_lt/is_empty/not_empty/expression(AND/OR)
- ⏱️ **Rate Limiter** — 프로바이더별 토큰 버킷 알고리즘 (분당 요청 제한)
- 📝 **Ollama Modelfile 생성** — `POST /api/ollama/create` (커스텀 모델 생성)
- ✅ **에러 메시지 err() 전환 100%** — 모든 한글 에러에 error_key
- 🌍 **nav_catalog 다국어** — 38개 탭 설명 en/zh 동적 전환 구조 (`TAB_DESC_I18N`)

**프론트엔드 UX**
- 📱 **모바일 반응형** — 사이드바 접기, 그리드 반응형, 모달 전체 화면
- ♿ **접근성** — ARIA 레이블, role="dialog", 포커스 트랩
- 🔔 **브라우저 Notification** — 워크플로우 완료/실패, 사용량 초과 알림
- 🎨 **커스텀 테마 5종** — dark/light/midnight/forest/sunset
- 🔀 **조건부 실행 UI** — conditionType 11종 셀렉트
- 📌 **변수 스코프 UI** — scope 선택 + {{변수명}} 참조 안내
- 📝 **Modelfile 편집 UI** — 커스텀 모델 생성 모달
- 📊 **비용 히스토리 상세 차트** — 프로바이더별 일별 스택 차트
- 📦 **노드 그룹핑** — Shift+클릭 다중 선택 → 그룹 생성/접기/펴기
- 🔍 **워크플로우 diff** — 버전 비교 (추가/삭제/변경 노드 표시)

**i18n**
- +36개 키 사전 추가 (UX 신기능) + 전수 검증 0 miss
- 2,711+ 키 × 3언어

### Architecture
- `server/ai_providers.py` — `_RateLimiter` 토큰 버킷, `threading` import
- `server/workflows.py` — `_evaluate_branch_condition()` 11종, `_substitute_variables()`, variable 노드 `var_store` 인자
- `server/ollama_hub.py` — `api_ollama_create_model()`
- `server/nav_catalog.py` — `TAB_DESC_I18N` 38탭, `get_tab_desc()`
- `server/errors.py` — 에러 전환 100% 완료
- GET 75 + POST 63 = 138 라우트

## [2.0.0] — 2026-04-22

### 🎉 v2.0 메이저 릴리스 — 멀티 AI 오케스트라 플랫폼 완성

v1.0.2 → v2.0.0: **+10,800줄, 17개 커밋, 10개 태그**

### Added — Phase 10 (Final)
- 📋 **워크플로우 복제** — 목록에서 원클릭 clone (`POST /api/workflows/clone`)
- 📎 **노드 복사/붙여넣기** — `Ctrl+C`/`Ctrl+V` 선택 노드 복사 (+40px 오프셋, 새 ID)
- ↩️ **실행 취소** — `Ctrl+Z` undo 스택 (최대 30개, 노드/엣지 추가·삭제·이동 추적)
- ⌨️ **키보드 단축키** — `?` 키로 도움말 모달 (Delete/Ctrl+C/V/Z/S/F/Esc)
- 🌍 **i18n +22개 키** — 2,622개 × 3언어, **누락 0**

### v1.0.2 → v2.0.0 전체 누적
- **16개 노드 타입**: start, session, subagent, aggregate, branch, output, http, transform, variable, subworkflow, embedding, loop, retry, error_handler, merge, delay
- **8개 AI 프로바이더** + 커스텀 무제한: Claude CLI, Ollama, Gemini CLI, Codex + OpenAI API, Gemini API, Anthropic API, Ollama API
- **Ollama 모델 허브**: 23개 모델 카탈로그, 검색/다운로드/삭제
- **Embedding**: Ollama bge-m3, OpenAI text-embedding-3, 커스텀
- **워크플로우 엔진**: 병렬 실행, SSE 스트림, Webhook 트리거, Cron 스케줄러, Export/Import, 버전 히스토리, 빌트인 템플릿 8종
- **i18n**: ko/en/zh 2,622키, error_key 시스템 49키
- **API**: GET 73 + POST 59 = 132 라우트

## [1.9.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 9
- 📜 **워크플로우 버전 히스토리** — 저장 시 이전 버전 자동 보관 (최근 20개). Inspector에서 버전 목록 + 복원 버튼
- 📋 **빌트인 템플릿 5종** — 멀티 AI 비교, RAG 파이프라인, 코드 리뷰, 데이터 ETL, 재시도 워크플로우
- 🧙 **프로바이더 설정 위자드** — 3단계 가이드 (프로바이더 선택 → 연결 설정 → 테스트). localStorage "다시 보지 않기"
- 🏷️ **템플릿 갤러리 강화** — 카테고리 필터 (analysis/ai/dev/data/pattern/custom), 빌트인 배지, 삭제 불가 표시
- 🌍 **i18n +56개 키** — 2,599개 × 3언어, **누락 0**

### Architecture
- `server/workflows.py` — 저장 시 히스토리 보관, `api_workflow_history()`, `api_workflow_restore()`, `BUILTIN_TEMPLATES` 5종
- `server/routes.py` — `/api/workflows/history`, `/api/workflows/restore`
- GET 73 + POST 57 라우트

## [1.8.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 8
- 🦙 **Ollama 모델 허브** (Open WebUI 스타일) — 23개 모델 카탈로그 (LLM/Code/Embedding/Vision 4개 카테고리)
  - 모델 검색 + 카테고리 필터
  - 원클릭 다운로드 (`ollama pull`) + 진행률 바 (2초 폴링)
  - 모델 삭제 + 상세 정보 (modelfile/parameters/template)
  - 설치된 모델 테이블 (크기/패밀리/양자화/수정일)
- ⚙️ **커스텀 프로바이더 완전 관리** — capabilities 배지, 테스트 실행, 편집 모드, embed() 실행 지원
- 🎯 **프로바이더별 기본 모델 설정** — 드롭다운 선택 + 저장 API
- 🔧 **CustomCliProvider.embed()** — embedCommand/embedArgsTemplate 로 임베딩 CLI 실행
- 🌍 **i18n +52개 키** — 2,543개 × 3언어, **누락 0**

### Architecture
- `server/ollama_hub.py` (신규) — 모델 카탈로그 23종, pull/delete/info/pull-status API
- `server/ai_providers.py` — CustomCliProvider.embed() 구현
- `server/ai_keys.py` — api_set_default_model()
- `server/routes.py` — Ollama 5개 + default-model 1개 = 6개 새 라우트
- `dist/index.html` — Ollama 허브 UI, 커스텀 프로바이더 편집, 기본 모델 드롭다운
- GET 72 + POST 56 라우트

## [1.7.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 7
- 🔀 **Merge 노드** — 여러 병렬 경로를 조건부 합류. all(전부)/any(하나라도)/count(N개) 모드 + 타임아웃
- ⏱️ **Delay 노드** — 지정 시간 대기 후 통과. 고정/랜덤 딜레이 모드
- 📊 **워크플로우 통계 대시보드** — 총 실행/성공률/평균 소요시간/활성 스케줄 카드 + 프로바이더별 사용 분포 (접기/펴기)
- 🔍 **노드 검색 필터** — 캔버스 상단 검색창. 이름/타입 매칭 → 하이라이트 (비매칭 노드 dimming)
- 🗺️ **미니맵 색상** — merge(시안 #06b6d4) / delay(회색 #94a3b8) 추가
- 📈 **`/api/workflows/stats`** — 전체 실행 통계 집계 (성공률, 프로바이더별, 트리거별, 워크플로우별)
- 🌍 **i18n +24개 키** — 2,480개 × 3언어, **누락 0**

### Architecture
- `server/workflows.py` — merge/delay 노드 실행, `api_workflow_stats()` 통계 집계
- `dist/index.html` — merge/delay 편집 패널, 통계 대시보드, 노드 검색, 캔버스 색상
- 16개 노드 타입 · GET 68 + POST 53 라우트

## [1.6.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 6
- 🔄 **Loop 노드** — for_each(배열 순회) / count(횟수 반복) / while(조건 반복). 입력 분할 구분자 + 최대 반복 횟수
- 🔁 **Retry 노드** — 실패 시 자동 재시도. N회 + exponential backoff (초기 대기 × 배수). 지연 미리보기 UI
- 🛡️ **Error Handler 노드** — skip(무시) / default(기본값 반환) / route(에러 라우팅) 3가지 전략
- ⏰ **Cron 스케줄러** — 워크플로우를 cron 표현식으로 자동 실행. 서버 시작 시 스케줄러 스레드 자동 시작. 프리셋(매시/매일/평일/30분) + Inspector 설정 UI
- 🚨 **사용량 알림** — 일일 비용(USD) / 토큰 한도 설정. 초과 시 경고 배너 표시. `/api/ai-providers/usage-alert` API
- 🎨 **노드 캔버스 색상** — loop(연보라 #a78bfa) / retry(오렌지 #fb923c) / error_handler(빨강 #f87171)
- 🌍 **i18n +23개 키** — 2,456개 × 3언어, **누락 0**

### Architecture
- `server/workflows.py` — loop/retry/error_handler 노드 실행, `_cron_matches_now()`, `_scheduler_loop()`, `start_scheduler()`
- `server/ai_keys.py` — `api_usage_alert_check()` / `api_usage_alert_set()`
- `server/server.py` — `start_scheduler()` 부팅 시 호출
- `server/routes.py` — `/api/workflows/schedule/set`, `/schedules`, `/api/ai-providers/usage-alert`, `/usage-alert/set`
- `server/nav_catalog.py` — workflows 탭 키워드 확장 (loop, retry, cron, webhook 등)
- `dist/index.html` — 3종 노드 편집 패널, cron 설정 UI, 사용량 알림 설정/배너
- 14개 노드 타입 · GET 67 + POST 53 라우트

## [1.5.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 5
- 🔗 **Webhook 트리거** (`POST /api/workflows/webhook/{wfId}`) — 외부 시스템(GitHub Actions, Slack, cron 등)에서 HTTP로 워크플로우 실행. 입력 텍스트 주입 지원
- 🩺 **프로바이더 Health 대시보드** — AI 프로바이더 탭 상단에 실시간 초록/빨강 인디케이터 + "N/M 사용 가능" 요약
- 🗺️ **워크플로우 미니맵** — 캔버스 우하단 150×100px 조감도. 노드 타입별 색상 점 + 뷰포트 사각형 + 클릭 이동
- 📋 **Webhook URL 표시** — Inspector에 webhook URL + 클립보드 복사 + curl 예시 코드
- 🌐 **errMsg() 헬퍼** — `error_key` 기반 프론트 에러 번역 표시. 40+ toast 호출 전환
- 🔄 **백엔드 에러 i18n 완전 전환** — agents, skills, hooks, mcp, plugins, projects, features, commands, claude_md, actions 모듈 29개 에러에 `error_key` 추가

### Architecture
- `server/workflows.py` — `api_workflow_webhook()` Webhook 트리거
- `server/ai_keys.py` — `api_provider_health()` 병렬 헬스체크
- `server/agents.py`, `skills.py`, `hooks.py`, `mcp.py`, `plugins.py`, `projects.py`, `features.py`, `commands.py`, `claude_md.py`, `actions.py` — `err()` / `error_key` 전환
- `dist/index.html` — 헬스 바, Webhook URL, 미니맵, errMsg() 헬퍼
- `dist/locales/*.json` — 2,421개 키 × 3언어, **누락 0**

## [1.4.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 4
- 🔬 **멀티 AI 비교 전용 API** (`POST /api/ai-providers/compare`) — 여러 프로바이더에 동일 프롬프트 병렬 전송, 결과 일괄 반환
- 📦 **워크플로우 Export/Import** — JSON 파일로 내보내기/가져오기 (`POST /api/workflows/export`, `/import`). 툴바에 Export/Import 버튼
- 🔎 **노드 Inspector 프로바이더 정보** — 실행 결과 있는 노드 선택 시 프로바이더 아이콘, 모델, 소요 시간, 토큰, 비용 칩 표시
- 📊 **실행 이력 강화** — run 항목에 프로바이더별 색상 태그 + 집계 ("Claude ×3, GPT ×1"), duration 읽기 좋은 형태
- 🎨 **embedding 노드 캔버스 색상** — 분홍 `#f472b6`
- 🏗️ **에러 메시지 i18n 시스템** (`server/errors.py`) — 48개 에러 키 정의 + `err()` 헬퍼. 응답에 `error_key` 포함하여 프론트 번역 가능
- 🌍 **i18n +57개 키** — 48개 에러 키 + 9개 프론트 키 (export/import 등). 2,414개 × 3언어, **누락 0**
- 🔍 nav_catalog 키워드 확장 — aiProviders 탭에 embedding/비용/비교 키워드 추가

### Architecture
- `server/errors.py` (신규) — `ERROR_MESSAGES` dict + `err()`/`msg()` 헬퍼
- `server/ai_keys.py` — `api_provider_compare()` 병렬 비교 API
- `server/workflows.py` — `api_workflow_export()` / `api_workflow_import()`
- `server/actions.py` — 에러 메시지 `error_key` 포함 전환 시작
- `dist/index.html` — Export/Import 버튼, Inspector 프로바이더 칩, 이력 강화, embedding 색상
- `dist/locales/*.json` — 2,414개 키 × 3언어

## [1.3.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 3
- 🧲 **Embedding 노드** — Ollama bge-m3, OpenAI text-embedding-3 등 임베딩 모델로 텍스트→벡터 변환. RAG/검색 파이프라인 구축용
- 🎯 **프로바이더 Capability 시스템** — chat/embed/code/vision/reasoning 5종 태깅. 모델별·프로바이더별 기능 필터링
  - Ollama API: embedding 모델 자동 감지 (bge, nomic-embed, e5, gte 등 키워드)
  - OpenAI API: embedding 3종 모델 추가 (text-embedding-3-large/small, ada-002)
- ⚙️ **커스텀 프로바이더 완전 통합** — capabilities, embedCommand, embedArgsTemplate 설정 가능. 워크플로우 assignee 드롭다운에 자동 노출
- 💰 **비용 분석 차트** (프론트) — 일별 비용 타임라인 (Chart.js 라인) + 프로바이더별 비용 비교 (도넛) + 총 호출/토큰/비용 요약 카드
- 📡 **워크플로우 SSE 실시간 스트림** (프론트) — EventSource 로 노드 진행률 실시간 반영, 실패 시 폴링 fallback
- 🎨 **노드 타입별 캔버스 색상** — http(초록) / transform(보라) / variable(노랑) / subworkflow(시안) / embedding(분홍)
- 🔬 **멀티 AI 비교 모드** — 동일 프롬프트를 여러 AI에 동시 전송 → 결과 나란히 비교
- 🌍 **i18n 전수 감사 완료** — 32개 누락 키 발견·추가 + embedding 5개 키. 최종 3개 언어 2,357개 키, **누락 0**
- 📋 백엔드 한글 하드코딩 에러 메시지 68개 식별 (향후 i18n 전환 준비 목록)
- 📋 nav_catalog.py 탭 설명 38개의 en/zh 번역 목록 작성

### Architecture
- `server/ai_providers.py` — `EmbeddingResponse`, `CAP_*` 상수, `BaseProvider.embed()` + `supports()`, Ollama/OpenAI embed 구현
- `server/workflows.py` — `embedding` 노드 타입 + `_execute_embedding_node()`
- `server/routes.py` — `/api/ai-providers/by-capability?cap=embed`
- `dist/index.html` — 비용 차트, SSE 스트림, 노드 색상, AI 비교 모드, embedding 편집 패널
- `dist/locales/*.json` — 2,357개 키 × 3개 언어

## [1.2.0] — 2026-04-22

### Added
- 🎛️ **워크플로우 프로바이더 셀렉터** — 노드 편집 패널에서 프로바이더:모델 드롭다운 선택 (그룹화 + 직접 입력 지원)
- 💰 **멀티 AI 비용 추적** — DB `workflow_costs` 테이블 + 프로바이더별/일별 집계 API (`/api/ai-providers/costs`)
- 📡 **워크플로우 실행 SSE 스트림** — `/api/workflows/run-stream?runId=...` SSE 엔드포인트, 실시간 노드 진행률 전송
- 🔁 **Sub-workflow 노드** — 다른 워크플로우를 노드로 호출, 입력 전달 + 결과 반환 (워크플로우 재사용)
- 🌐 **HTTP 노드 UI** — URL/메서드/Body/추출경로 편집 패널
- 🔄 **Transform 노드 UI** — 템플릿/JSON 추출/Regex/결합 4가지 변환 유형 편집
- 📌 **Variable 노드 UI** — 변수 이름 + 기본값 편집
- 🔁 **Sub-workflow 노드 UI** — 워크플로우 목록에서 선택 + 입력 전달 체크박스

### Architecture
- `server/db.py` — `workflow_costs` 테이블 스키마 추가
- `server/workflows.py` — `_execute_subworkflow_node`, `_record_workflow_cost`, `handle_workflow_run_stream` (SSE)
- `server/ai_keys.py` — `api_workflow_costs_summary` 집계 API
- `dist/index.html` — 10개 노드 타입 (4개 신규), 프로바이더 셀렉터, 노드 편집 패널 확장

## [1.1.0] — 2026-04-22

### Added
- 🧠 **AI 프로바이더 탭 (aiProviders)** — 멀티 AI 오케스트라 기반 구축
  - **8개 빌트인 프로바이더**: Claude CLI, Ollama, Gemini CLI, Codex (CLI) + OpenAI API, Gemini API, Anthropic API, Ollama API
  - CLI 자동 감지 (로컬 설치된 claude/ollama/gemini/codex) + API 키 설정
  - **커스텀 CLI 프로바이더** — 임의의 CLI 도구를 AI 프로바이더로 등록
  - **폴백 체인** — 1차 프로바이더 실패 시 대안 자동 전환
  - 연결 테스트 + 모델 카탈로그 + 가격표 내장
- 🔀 **워크플로우 멀티 프로바이더 통합**
  - 노드 assignee: `claude:opus`, `openai:gpt-4.1`, `gemini:2.5-pro`, `ollama:llama3.1`, `codex:o4-mini`
  - 기존 Claude 전용 assignee 완전 호환 유지
- ⚡ **워크플로우 병렬 실행 엔진** — 같은 depth 노드를 ThreadPoolExecutor 로 동시 실행
- 🌐 **새 노드 타입 3종**: HTTP (외부 API 호출), Transform (JSON/regex/템플릿 변환), Variable (변수 저장)
- 🌍 33개 신규 i18n 키 (ko/en/zh)

### Architecture
- `server/ai_providers.py` (신규) — BaseProvider ABC + 8개 구현체 + ProviderRegistry 싱글턴
- `server/ai_keys.py` (신규) — `~/.claude-dashboard-ai-providers.json` 설정 CRUD
- `server/workflows.py` — `_execute_node` 멀티 프로바이더 대응, `_topological_levels` 병렬 실행
- `server/routes.py` — `/api/ai-providers/*` 엔드포인트 7개 추가

## [1.0.2] — 2026-04-22

### Added
- 챗봇 응답 대기 동안 마스코트가 **"잠시만요~! 결과를 불러오고 있어요"** 등 5종 메시지를 2.6초 간격으로 순환 표시. 첫 토큰 도착·에러·완료·finally 시 자동 정리. ko/en/zh 번역 포함.

## [1.0.1] — 2026-04-22

### Changed
- 대시보드 도우미 챗봇 모델을 **Haiku 로 하향** (`--model haiku`). 단순 JSON 라우팅 응답에 최적. 토큰 비용 대폭 절감. `CHAT_MODEL` 환경변수로 오버라이드 가능.

## [1.0.0] — 2026-04-22

첫 공식 릴리스 태그. 누적된 주요 기능을 여기서 하나로 묶어 마감.

### 신규 탭 / 기능
- 🔀 **워크플로우 (workflows)** — n8n 스타일 DAG 에디터
  - 6종 노드 (start · session · subagent · aggregate · branch · output)
  - 포트 드래그 엣지 + DAG 사이클 거부 + 🎯 맞춤(자동 정렬)
  - 🎭 세션 하네스: 페르소나/허용 도구/resume session_id
  - 🖥️ Terminal 새 창 spawn · 🔄 session_id 이어쓰기
  - 📋 템플릿: 팀 개발(리드+프론트+백엔드)/리서치/병렬 3 + 커스텀 저장
  - 🔁 **Repeat** — 반복 횟수/스케줄(HH:MM)/피드백 노트 자동 주입
  - 📜 실행 이력 · 🎬 인터랙티브 14 장면 튜토리얼(typewriter)
- 🚀 **시작하기 (onboarding)** — ~/.claude 상태 실시간 감지 단계별 체크리스트
- 📚 **가이드 & 툴 (guideHub)** — 외부 가이드/유용한 툴/베스트 프랙티스/치트시트

### 전반
- 모든 네이티브 `prompt/confirm` 을 맥 스타일 `promptModal`/`confirmModal` 로 통일
- 3개 언어 (ko/en/zh) 완전 번역 · `verify-translations` 검증 통과
- 모바일 대응: 마스코트 탭 시 챗창 즉시 닫힘 버그 해결, 창 크기 cap, 플로팅 맞춤 버튼
- 챗봇 시스템 프롬프트가 `server/nav_catalog.py` 를 읽어 자동 생성 — 탭 추가 시 자동 반영
