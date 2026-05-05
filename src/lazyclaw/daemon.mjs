// Local-only HTTP daemon for LazyClaw — the OpenClaw "gateway" shape,
// scoped down to what this CLI actually offers.
//
// Always binds 127.0.0.1 (loopback). The endpoints are read-only inspection
// (version / providers / sessions) and `agent` for one-shot inference. The
// daemon never writes to disk under its own authority — only `agent` with
// an explicit `sessionId` ends up appending a turn to that session, which
// is the exact same operation the CLI does.
//
// Streaming: POST /agent with `{stream: true}` returns SSE
// (`data: <json>\n\n` per token, `event: done` to terminate). Without it,
// the response is a single JSON object once the full reply has arrived.

import http from 'node:http';
import nodePath from 'node:path';
import fs from 'node:fs';

import { PROVIDERS, PROVIDER_INFO, maskApiKey } from './providers/registry.mjs';
import { withRateLimitRetry } from './providers/retry.mjs';
import { withFallback } from './providers/fallback.mjs';
import { withResponseCache } from './providers/cache.mjs';
import { costFromUsage } from './providers/rates.mjs';
import { composeSystemPrompt, listSkills, loadSkill, skillPath, installSkill, removeSkill } from './skills.mjs';
import { TokenBucketLimiter } from './ratelimit.mjs';
import { createLogger } from './logger.mjs';
import { summarizeState, listSessions as listWorkflowSessions, loadStateFile as loadWorkflowState } from './workflow/summary.mjs';

// Resolve the provider for a request. Composes opt-in wrappers in this
// order (innermost first):
//   1. cache  — wraps the base provider so cache hits never trigger
//               fallback or retry (a hit is a successful response).
//   2. fallback — chain of alternates; pre-yield recoverable errors fall
//                 through; mid-stream errors bubble.
//   3. retry  — outermost so each retry covers the full chain (retry
//               exhausts → 429 to client).
// `cachedByName` is a per-handler Map shared across requests so the
// cache state actually persists between calls. Without that the cache
// would be empty on every request.
//
// Returns { provider } on success or { error } when the primary or any
// listed fallback name is unknown.
function resolveProvider(body, providerName, cachedByName, logger) {
  if (!PROVIDERS[providerName]) return { error: `unknown provider: ${providerName}` };
  // The decorator callbacks emit one debug line each — useful for ops who
  // set --log debug to diagnose why a request is slow or which provider
  // actually served it. With the default level (info) these are silent.
  const dbg = (msg, fields) => { if (logger) logger.debug(msg, fields); };
  const wrapWithCache = (name) => {
    if (!cachedByName) return PROVIDERS[name];
    if (!cachedByName.has(name)) {
      cachedByName.set(name, withResponseCache(PROVIDERS[name], {
        maxEntries: cachedByName._opts?.maxEntries,
        ttlMs: cachedByName._opts?.ttlMs,
        onHit:  ({ keyHash, size }) => dbg('cache.hit',  { provider: name, keyHash: keyHash.slice(0, 12), size }),
        onMiss: ({ keyHash })       => dbg('cache.miss', { provider: name, keyHash: keyHash.slice(0, 12) }),
      }));
    }
    return cachedByName.get(name);
  };
  // Cache only when the request explicitly opts in. The handler-level
  // Map is shared so two requests with body.cache=true to the same base
  // provider hit the same cache.
  const useCache = !!body?.cache;
  let prov = useCache ? wrapWithCache(providerName) : PROVIDERS[providerName];
  if (Array.isArray(body?.fallback) && body.fallback.length > 0) {
    const chain = [prov];
    for (const name of body.fallback) {
      if (!PROVIDERS[name]) return { error: `unknown fallback provider: ${name}` };
      chain.push(useCache ? wrapWithCache(name) : PROVIDERS[name]);
    }
    prov = withFallback(chain, {
      onFallback: ({ from, to, err }) => dbg('provider.fallback', {
        from, to, errorCode: err?.code || null, errorMsg: String(err?.message || err).slice(0, 120),
      }),
    });
  }
  const r = body?.retry;
  if (r && Number.isFinite(r.attempts) && r.attempts > 0) {
    prov = withRateLimitRetry(prov, {
      attempts: r.attempts,
      maxBackoffMs: r.maxBackoffMs,
      onRetry: ({ attempt, retryAfterMs, err }) => dbg('provider.retry', {
        attempt, retryAfterMs, errorCode: err?.code || null,
      }),
    });
  }
  return { provider: prov };
}

async function fileExists(p) {
  try { await fs.promises.access(p); return true; }
  catch { return false; }
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let buf = '';
    req.setEncoding('utf8');
    req.on('data', d => { buf += d; if (buf.length > 5 * 1024 * 1024) { reject(new Error('body too large')); req.destroy(); } });
    req.on('end', () => {
      if (!buf) return resolve({});
      try { resolve(JSON.parse(buf)); }
      catch (e) { reject(new Error(`invalid JSON body: ${e.message}`)); }
    });
    req.on('error', reject);
  });
}

// Raw body reader — used for `PUT /skills/<name>` where the body is
// markdown rather than JSON. Same 1 MiB cap as the CLI's `--from-url`
// path so HTTP can't sneak past the safeguard the CLI enforces.
const SKILL_MAX_BYTES = 1_048_576;
function readTextBody(req, maxBytes = SKILL_MAX_BYTES) {
  return new Promise((resolve, reject) => {
    let buf = '';
    req.setEncoding('utf8');
    req.on('data', d => {
      buf += d;
      if (buf.length > maxBytes) {
        reject(new Error(`body exceeds ${maxBytes} bytes`));
        req.destroy();
      }
    });
    req.on('end', () => resolve(buf));
    req.on('error', reject);
  });
}

function writeJson(res, status, obj, extraHeaders = {}) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
    ...extraHeaders,
  });
  res.end(body);
}

// Has the cumulative cost in any capped currency reached the cap?
// Returns the offending currency + amount + cap so the caller can
// surface it cleanly, or null when no cap is breached.
function checkCostCap(metrics, costCap) {
  if (!costCap) return null;
  for (const [cur, cap] of Object.entries(costCap)) {
    if (!Number.isFinite(cap) || cap <= 0) continue;
    const spent = metrics.costsByCurrency[cur] || 0;
    if (spent >= cap) return { currency: cur, spent: Math.round(spent * 1_000_000) / 1_000_000, cap };
  }
  return null;
}

// Bump per-handler metrics from a single request's cost+usage. Keys
// cost by currency so heterogeneous fleets (USD-priced anthropic, EUR
// regional contracts) don't silently sum mismatched numbers. Tokens
// are unit-free → single counter.
function accumulateMetricsFromCost(metrics, usage, cost) {
  if (cost && Number.isFinite(cost.cost)) {
    const cur = cost.currency || 'USD';
    metrics.costsByCurrency[cur] = (metrics.costsByCurrency[cur] || 0) + cost.cost;
  }
  if (usage) {
    if (Number.isFinite(usage.inputTokens)) metrics.tokensTotal.inputTokens += usage.inputTokens;
    if (Number.isFinite(usage.outputTokens)) metrics.tokensTotal.outputTokens += usage.outputTokens;
  }
}

// Map provider error codes to HTTP statuses so clients can branch on
// res.status instead of parsing error messages. Returns
// { status, headers? } so 429 can attach a Retry-After.
//
// Exported for unit testing without spinning up an actual provider that
// would only fail under live network conditions.
export function statusForProviderError(err) {
  if (err?.code === 'INVALID_KEY') return { status: 401 };
  if (err?.code === 'RATE_LIMIT') {
    const retrySeconds = Math.max(1, Math.ceil((err.retryAfterMs || 1000) / 1000));
    return { status: 429, headers: { 'retry-after': String(retrySeconds) } };
  }
  if (err?.status && err.status >= 400 && err.status < 600) return { status: err.status };
  return { status: 502 };
}

function writeSseHead(res) {
  res.writeHead(200, {
    'content-type': 'text/event-stream; charset=utf-8',
    'cache-control': 'no-cache, no-transform',
    'connection': 'close',
  });
}

function writeSse(res, event, data) {
  if (event) res.write(`event: ${event}\n`);
  res.write(`data: ${JSON.stringify(data)}\n\n`);
}

/**
 * Constant-time string equality. Plain `===` would short-circuit on the
 * first mismatching byte, leaking timing info that lets an attacker on
 * a shared host narrow the secret one byte at a time. We compare every
 * byte with XOR + accumulator.
 */
function constantTimeEqual(a, b) {
  const aStr = String(a ?? '');
  const bStr = String(b ?? '');
  if (aStr.length !== bStr.length) return false;
  let diff = 0;
  for (let i = 0; i < aStr.length; i++) {
    diff |= aStr.charCodeAt(i) ^ bStr.charCodeAt(i);
  }
  return diff === 0;
}

function isAuthorized(req, expectedToken) {
  if (!expectedToken) return true;  // auth disabled
  const header = req.headers['authorization'] || '';
  const m = /^Bearer\s+(.+)$/i.exec(header);
  if (!m) return false;
  return constantTimeEqual(m[1].trim(), expectedToken);
}

/**
 * Origin gate — protect against DNS-rebinding / CSRF where a page in
 * the user's browser posts to 127.0.0.1:<our port>. Browsers always
 * attach `Origin` for cross-origin POSTs (and increasingly for GETs);
 * CLI tools (curl, fetch from a script) usually don't.
 *
 * Policy:
 *   - No `Origin` header → assume non-browser caller, allow.
 *   - `Origin` set → must be in `allowedOrigins`. Empty allowlist
 *     means "reject all browser-originated requests" — the default,
 *     because the daemon is designed for CLI/script callers.
 *
 * Returns true when the request should proceed, false when it should
 * be rejected with 403.
 */
function isOriginAllowed(req, allowedOrigins) {
  const origin = req.headers['origin'];
  if (!origin) return true;
  if (!allowedOrigins || allowedOrigins.length === 0) return false;
  return allowedOrigins.includes(origin);
}

/**
 * @param {{
 *   readConfig: () => Record<string, unknown>,
 *   sessionsDirGetter: () => string,
 *   sessionsMod: typeof import('./sessions.mjs'),
 *   version: () => string,
 *   workflowStateDir?: () => string,
 *   authToken?: string,
 *   allowedOrigins?: string[],
 *   rateLimit?: { capacity?: number, refillPerSec?: number } | null,
 *   responseCache?: { maxEntries?: number, ttlMs?: number } | true | null,
 *   logger?: ReturnType<typeof createLogger> | null,
 *   costCap?: Record<string, number> | null,
 * }} ctx
 */
export function makeHandler(ctx) {
  const authToken = ctx.authToken || null;
  const allowedOrigins = Array.isArray(ctx.allowedOrigins) ? ctx.allowedOrigins : [];
  // Default state dir matches the CLI's default. Callers can override
  // via ctx.workflowStateDir or LAZYCLAW_WORKFLOW_STATE_DIR env var.
  const workflowStateDir = ctx.workflowStateDir
    || (() => process.env.LAZYCLAW_WORKFLOW_STATE_DIR || '.workflow-state');
  ctx = { ...ctx, workflowStateDir };
  // Rate limiter is opt-in; passing nothing → unlimited (the historical
  // single-user-loopback default). When enabled, scope is per remote IP.
  const limiter = ctx.rateLimit
    ? new TokenBucketLimiter({
        capacity: ctx.rateLimit.capacity,
        refillPerSec: ctx.rateLimit.refillPerSec,
      })
    : null;
  // Cost cap: ctx.costCap = { USD: 1.50, EUR: 0.80, ... }. When the
  // cumulative cost in any listed currency reaches its cap, /chat and
  // /agent reject with 402 Payment Required. Other routes (/version,
  // /metrics, etc.) stay reachable so monitoring still works after the
  // cap fires. Empty/missing → unlimited (the historical default).
  const costCap = ctx.costCap && typeof ctx.costCap === 'object' ? ctx.costCap : null;
  // Per-handler cache map — populated lazily as requests opt in via
  // body.cache. Shared across requests so the second identical call
  // actually hits. We attach the configured opts so the lazy init
  // gets the right TTL/maxEntries.
  const cachedByName = ctx.responseCache ? Object.assign(new Map(), { _opts: ctx.responseCache === true ? {} : ctx.responseCache }) : null;
  // Logger is opt-in via ctx.logger (the CLI passes one when --log <level>
  // is set). Falsy → silent (the historical default; tests stay quiet).
  const logger = ctx.logger || null;
  // Per-handler metrics. The /metrics endpoint reads these. Bumped on
  // res.close so middleware short-circuits (403/401/429) get counted.
  const metrics = {
    startedAtMs: Date.now(),
    requestsTotal: 0,
    requestsByStatus: /** @type {Record<string, number>} */({}),
    rateLimitDenied: 0,
    // Cumulative cost across all requests that produced a `cost` block.
    // Keyed by currency so a heterogeneous fleet (USD-priced anthropic,
    // EUR-priced regional contract) doesn't silently sum mismatched
    // numbers. Tokens are unit-free so we keep them in a single counter.
    costsByCurrency: /** @type {Record<string, number>} */({}),
    tokensTotal: { inputTokens: 0, outputTokens: 0 },
  };
  return async function handler(req, res) {
    // Capture method+path before any handler logic runs; req.url survives
    // the response but capturing now keeps the log line stable even if a
    // future refactor mutates req.
    const startedAt = Date.now();
    const method = req.method;
    const path = (req.url || '/').split('?')[0];
    const remote = req.socket?.remoteAddress || 'no-socket';
    // Hook res.writeHead to capture the eventual status without
    // intercepting the response body. We log on res 'close'.
    let observedStatus = 0;
    const origWriteHead = res.writeHead.bind(res);
    res.writeHead = (status, ...rest) => {
      observedStatus = status;
      return origWriteHead(status, ...rest);
    };
    // Attach the close-handler only when res supports it. Unit tests
    // sometimes drive the handler with a stub `res` that has writeHead +
    // end but no event-emitter surface; those exercises don't care about
    // metrics or access logs and should not crash.
    if (typeof res.once === 'function') {
      res.once('close', () => {
        // Counters fire even without a logger so /metrics is meaningful
        // by default. Status 0 means writeHead never ran (e.g. body parse
        // crashed) — bucket those as "0" so we don't lose the request.
        metrics.requestsTotal += 1;
        const sk = String(observedStatus || 0);
        metrics.requestsByStatus[sk] = (metrics.requestsByStatus[sk] || 0) + 1;
        if (logger) {
          const durationMs = Date.now() - startedAt;
          logger.info('access', { method, path, status: observedStatus, durationMs, remote });
        }
      });
    }
    try {
      // Origin gate runs *before* auth so a browser-originated request
      // can't even probe whether a token is required.
      if (!isOriginAllowed(req, allowedOrigins)) {
        return writeJson(res, 403, { error: 'forbidden origin' });
      }
      // Authentication gate — when authToken is set, every request must
      // present `Authorization: Bearer <token>`. This is opt-in because
      // the default deployment is loopback-only single-user; the token
      // is for shared-host scenarios or when you want to expose the
      // daemon over an SSH tunnel and lock down the open port.
      if (authToken && !isAuthorized(req, authToken)) {
        return writeJson(res, 401, { error: 'unauthorized' }, {
          'www-authenticate': 'Bearer realm="lazyclaw"',
        });
      }
      // Rate limit gate — *after* auth so the budget is per authenticated
      // identity rather than per IP-pretending-to-be-someone-else. Authed
      // means the remote actually proved they have the shared secret.
      if (limiter) {
        // The remote-IP key falls back to a fixed string for tests that
        // drive the handler directly without a socket. socket.remoteAddress
        // is "127.0.0.1" for loopback; that's fine for our scope.
        const key = req.socket?.remoteAddress || 'no-socket';
        const verdict = limiter.consume(key);
        if (!verdict.allowed) {
          metrics.rateLimitDenied += 1;
          const retrySeconds = Math.max(1, Math.ceil(verdict.retryAfterMs / 1000));
          return writeJson(res, 429, {
            error: 'rate limit exceeded',
            retryAfterMs: verdict.retryAfterMs,
          }, { 'retry-after': String(retrySeconds) });
        }
      }
      const url = new URL(req.url || '/', 'http://localhost');
      const route = `${req.method} ${url.pathname}`;
      const sessionMatch = url.pathname.match(/^\/sessions\/([^/]+)$/);
      const sessionExportMatch = url.pathname.match(/^\/sessions\/([^/]+)\/export$/);
      const skillMatch = url.pathname.match(/^\/skills\/([^/]+)$/);
      const workflowMatch = url.pathname.match(/^\/workflows\/([^/]+)$/);
      switch (true) {
        case route === 'GET /version':
          return writeJson(res, 200, { version: ctx.version(), nodeVersion: process.version, platform: `${process.platform}-${process.arch}` });
        case route === 'GET /metrics': {
          // Aggregate per-handler counters. cacheStats are pulled per
          // wrapped provider — we report a sum across all populated
          // entries so the figure reflects total cache activity.
          let cacheHits = 0, cacheMisses = 0, cacheSize = 0;
          if (cachedByName) {
            for (const wrapped of cachedByName.values()) {
              const s = typeof wrapped.cacheStats === 'function' ? wrapped.cacheStats() : null;
              if (s) {
                cacheHits += s.hits || 0;
                cacheMisses += s.misses || 0;
                cacheSize += s.size || 0;
              }
            }
          }
          // Cumulative tokens / cost — meaningful only when callers used
          // body.usage / body.cost. The fields are always present (zero
          // by default) so monitoring tooling sees a stable schema.
          const tokensTotal = { ...metrics.tokensTotal };
          const costs = {};
          for (const [cur, n] of Object.entries(metrics.costsByCurrency)) {
            // Round to six decimals here too, matching costFromUsage's
            // precision so monitoring deltas line up with per-request
            // breakdowns.
            costs[cur] = Math.round(n * 1_000_000) / 1_000_000;
          }
          // Workflow snapshot — opportunistic. We scan the state dir
          // once per /metrics call and count per bucket. This is
          // cheap unless the user has thousands of state files; for
          // truly large fleets the operator can disable by passing
          // ctx.workflowMetrics === false.
          let workflows = null;
          if (ctx.workflowMetrics !== false) {
            try {
              const stateDir = ctx.workflowStateDir();
              if (fs.existsSync(stateDir)) {
                const sessions = listWorkflowSessions(stateDir);
                workflows = { total: sessions.length, done: 0, resumable: 0, failed: 0, running: 0 };
                for (const s of sessions) {
                  if (s.summary.done)        workflows.done++;
                  if (s.summary.resumable)   workflows.resumable++;
                  if (s.summary.failed > 0)  workflows.failed++;
                  if (s.summary.running > 0) workflows.running++;
                }
              } else {
                workflows = { total: 0, done: 0, resumable: 0, failed: 0, running: 0 };
              }
            } catch {
              // Don't fail /metrics because the state dir is unreadable —
              // expose the gap as null and keep monitoring alive.
              workflows = null;
            }
          }
          return writeJson(res, 200, {
            uptimeMs: Date.now() - metrics.startedAtMs,
            requestsTotal: metrics.requestsTotal,
            requestsByStatus: metrics.requestsByStatus,
            rateLimitDenied: metrics.rateLimitDenied,
            cache: cachedByName ? { hits: cacheHits, misses: cacheMisses, size: cacheSize } : null,
            tokensTotal,
            costsByCurrency: costs,
            workflows,
            timestamp: new Date().toISOString(),
          });
        }
        case route === 'GET /providers':
          return writeJson(res, 200, Object.keys(PROVIDERS).map(name => {
            const meta = PROVIDER_INFO[name] || { name };
            return { name, requiresApiKey: !!meta.requiresApiKey, defaultModel: meta.defaultModel || null, suggestedModels: meta.suggestedModels || [] };
          }));
        case route === 'GET /status': {
          const cfg = ctx.readConfig();
          return writeJson(res, 200, {
            provider: cfg.provider || null,
            model: cfg.model || null,
            keyMasked: maskApiKey(cfg['api-key']),
          });
        }
        case route === 'GET /doctor': {
          // Mirror the CLI doctor output — same field set so any tool that
          // already knows how to read CLI doctor JSON can hit this endpoint.
          const cfg = ctx.readConfig();
          const issues = [];
          if (!cfg.provider) issues.push('config.provider is missing');
          if (cfg.provider && cfg.provider !== 'mock' && !cfg['api-key']) {
            issues.push(`config['api-key'] is missing for provider "${cfg.provider}"`);
          }
          if (cfg.provider && !Object.prototype.hasOwnProperty.call(PROVIDERS, cfg.provider)) {
            issues.push(`unknown provider "${cfg.provider}"`);
          }
          const ok = issues.length === 0;
          return writeJson(res, ok ? 200 : 503, {
            ok,
            provider: cfg.provider || null,
            model: cfg.model || null,
            hasApiKey: !!cfg['api-key'],
            nodeVersion: process.version,
            platform: `${process.platform}-${process.arch}`,
            issues,
            knownProviders: Object.keys(PROVIDERS),
            timestamp: new Date().toISOString(),
          });
        }
        case route === 'GET /sessions': {
          // ?filter=<substr> case-insensitive id substring;
          // ?limit=<N> caps post-filter count.
          // Same composition (filter then limit) as v3.33's CLI flag.
          let list = ctx.sessionsMod.listSessions(ctx.sessionsDirGetter());
          const filter = url.searchParams.get('filter');
          if (filter) {
            const f = filter.toLowerCase();
            list = list.filter(s => s.id.toLowerCase().includes(f));
          }
          const limitStr = url.searchParams.get('limit');
          if (limitStr) {
            const n = parseInt(limitStr, 10);
            if (Number.isFinite(n) && n > 0) list = list.slice(0, n);
          }
          return writeJson(res, 200, list.map(s => ({ id: s.id, bytes: s.bytes, mtime: new Date(s.mtimeMs).toISOString() })));
        }
        case route === 'GET /sessions/search': {
          // Mirror of `lazyclaw sessions search <query> [--regex]`.
          // ?q=<query> required; ?regex=true switches to regex mode.
          // Returns { query, regex, matches: [{ id, mtime, matchCount, excerpt }] }
          // — same shape the CLI prints. A dashboard rendering the
          // search box can use the same parser for both surfaces.
          const q = url.searchParams.get('q');
          if (!q) return writeJson(res, 400, { error: 'missing q query parameter' });
          const useRegex = url.searchParams.get('regex') === 'true';
          let matcher;
          if (useRegex) {
            try { matcher = new RegExp(q, 'i'); }
            catch (e) { return writeJson(res, 400, { error: `invalid regex: ${e.message}` }); }
          } else {
            const ql = q.toLowerCase();
            matcher = { test: (s) => String(s).toLowerCase().includes(ql) };
          }
          const cfgDir = ctx.sessionsDirGetter();
          const list = ctx.sessionsMod.listSessions(cfgDir);
          const matches = [];
          for (const s of list) {
            const turns = ctx.sessionsMod.loadTurns(s.id, cfgDir);
            let matchCount = 0;
            let firstExcerpt = null;
            for (const t of turns) {
              if (typeof t?.content !== 'string') continue;
              if (matcher.test(t.content)) {
                matchCount++;
                if (firstExcerpt === null) {
                  const c = t.content;
                  let pos = useRegex ? c.search(matcher) : c.toLowerCase().indexOf(q.toLowerCase());
                  if (pos < 0) pos = 0;
                  const start = Math.max(0, pos - 40);
                  const end = Math.min(c.length, pos + q.length + 40);
                  firstExcerpt = (start > 0 ? '…' : '') + c.slice(start, end) + (end < c.length ? '…' : '');
                }
              }
            }
            if (matchCount > 0) {
              matches.push({
                id: s.id,
                mtime: new Date(s.mtimeMs).toISOString(),
                matchCount,
                excerpt: firstExcerpt,
              });
            }
          }
          return writeJson(res, 200, { query: q, regex: useRegex, matches });
        }
        case req.method === 'GET' && !!sessionExportMatch: {
          // GET /sessions/<id>/export?format=md|json|text — same body
          // the CLI's `lazyclaw sessions export <id> --format ...`
          // produces, with the appropriate content-type. The dashboard
          // can offer a "download as ..." button without spawning the
          // CLI.
          const id = sessionExportMatch[1];
          try {
            const cfgDir = ctx.sessionsDirGetter();
            const file = ctx.sessionsMod.sessionPath(id, cfgDir);
            if (!(await fileExists(file))) return writeJson(res, 404, { error: 'session not found', id });
            const fmt = (url.searchParams.get('format') || 'md').toLowerCase();
            const FORMATS = {
              md:       { fn: ctx.sessionsMod.exportMarkdown, mime: 'text/markdown; charset=utf-8' },
              markdown: { fn: ctx.sessionsMod.exportMarkdown, mime: 'text/markdown; charset=utf-8' },
              json:     { fn: ctx.sessionsMod.exportJson,     mime: 'application/json; charset=utf-8' },
              text:     { fn: ctx.sessionsMod.exportText,     mime: 'text/plain; charset=utf-8' },
              txt:      { fn: ctx.sessionsMod.exportText,     mime: 'text/plain; charset=utf-8' },
            };
            const f = FORMATS[fmt];
            if (!f) {
              return writeJson(res, 400, {
                error: `unknown format: ${fmt}`,
                expected: ['md', 'json', 'text'],
              });
            }
            const body = f.fn(id, cfgDir);
            res.writeHead(200, {
              'content-type': f.mime,
              'content-length': Buffer.byteLength(body),
            });
            return res.end(body);
          } catch (err) {
            return writeJson(res, 400, { error: err?.message || String(err) });
          }
        }
        case req.method === 'GET' && !!sessionMatch: {
          // GET /sessions/<id> — full turn log. Returns 404 when missing
          // rather than an empty array so the caller can distinguish
          // "session does not exist" from "session is empty".
          const id = sessionMatch[1];
          try {
            const cfgDir = ctx.sessionsDirGetter();
            const file = ctx.sessionsMod.sessionPath(id, cfgDir);
            if (!(await fileExists(file))) return writeJson(res, 404, { error: 'session not found', id });
            const turns = ctx.sessionsMod.loadTurns(id, cfgDir);
            return writeJson(res, 200, { id, turns });
          } catch (err) {
            return writeJson(res, 400, { error: err?.message || String(err) });
          }
        }
        case route === 'GET /workflows': {
          // List every persisted workflow session in the configured
          // state dir, newest activity first. Mirrors `lazyclaw inspect`
          // (no-arg) exactly so a dashboard can use the same renderer
          // for CLI and HTTP outputs. Per-node `nodes` map is omitted —
          // call /workflows/<sessionId> for full detail.
          //
          // ?status=done|resumable|failed|running mirrors the CLI's
          // --status flag — one shared predicate so a UI can paginate
          // by bucket without pulling the full list.
          const stateDir = ctx.workflowStateDir();
          const qStatus = url.searchParams.get('status');
          if (qStatus) {
            const valid = new Set(['done', 'resumable', 'failed', 'running']);
            if (!valid.has(qStatus)) {
              return writeJson(res, 400, {
                error: `invalid status: ${qStatus}`,
                expected: [...valid],
              });
            }
          }
          try {
            let sessions = listWorkflowSessions(stateDir);
            if (qStatus) {
              sessions = sessions.filter(s => {
                if (qStatus === 'done')      return s.summary.done;
                if (qStatus === 'resumable') return s.summary.resumable;
                if (qStatus === 'failed')    return s.summary.failed > 0;
                if (qStatus === 'running')   return s.summary.running > 0;
                return true;
              });
            }
            return writeJson(res, 200, { dir: stateDir, status: qStatus || null, sessions });
          } catch (err) {
            if (err?.code === 'ENOENT') {
              // Empty dir is a valid state (no workflows ever ran). The
              // CLI distinguishes "missing dir" from "empty dir" — the
              // daemon collapses both to an empty array so a fresh
              // process doesn't 404 a UI poll loop.
              return writeJson(res, 200, { dir: stateDir, status: qStatus || null, sessions: [] });
            }
            return writeJson(res, 500, { error: err?.message || String(err) });
          }
        }
        case req.method === 'GET' && !!workflowMatch: {
          // GET /workflows/<sessionId> — full state of a single
          // workflow run. Same shape as `lazyclaw inspect <id>` (the
          // engine's persisted object plus a derived summary block).
          // 404 when the state file is missing.
          const sid = workflowMatch[1];
          const stateDir = ctx.workflowStateDir();
          let state;
          try {
            state = loadWorkflowState(sid, stateDir);
          } catch (err) {
            return writeJson(res, 500, { error: err?.message || String(err) });
          }
          if (!state) return writeJson(res, 404, { error: 'workflow not found', sessionId: sid });
          const { summary, failedNodes } = summarizeState(state);
          // ?summary=true trims the per-node `nodes` map and `order`
          // array, matching v3.17's CLI `inspect --summary` shape and
          // the per-session shape that list-mode produces. A UI fetching
          // this endpoint to render a status badge doesn't want the
          // full per-node payload — `?summary=true` keeps the wire
          // small for high-frequency polls.
          const compact = url.searchParams.get('summary') === 'true';
          const body = compact
            ? {
                sessionId: state.sessionId,
                dir: stateDir,
                summary,
                failedNodes,
                startedAt: state.startedAt,
                updatedAt: state.updatedAt,
              }
            : {
                sessionId: state.sessionId,
                dir: stateDir,
                summary,
                failedNodes,
                order: state.order,
                nodes: state.nodes,
                startedAt: state.startedAt,
                updatedAt: state.updatedAt,
              };
          return writeJson(res, 200, body);
        }
        case route === 'GET /skills': {
          // List installed skills with their first-line summary so a UI
          // can render them without a follow-up read for each one.
          // ?filter=<substr>&limit=<N> mirror the v3.33 CLI flags.
          const cfgDir = ctx.sessionsDirGetter();
          let items = listSkills(cfgDir);
          const filter = url.searchParams.get('filter');
          if (filter) {
            const f = filter.toLowerCase();
            items = items.filter(s => s.name.toLowerCase().includes(f));
          }
          const limitStr = url.searchParams.get('limit');
          if (limitStr) {
            const n = parseInt(limitStr, 10);
            if (Number.isFinite(n) && n > 0) items = items.slice(0, n);
          }
          return writeJson(res, 200, items.map(s => ({
            name: s.name, bytes: s.bytes, summary: s.summary,
          })));
        }
        case route === 'GET /skills/search': {
          // Mirror of `lazyclaw skills search`. ?q=<query> required;
          // ?regex=true switches to regex mode. Returns
          //   { query, regex, matches: [{ name, bytes, matchCount, excerpt }] }
          // — same shape the CLI prints. A dashboard skill picker can
          // hit this endpoint instead of pulling every skill body and
          // searching client-side.
          const q = url.searchParams.get('q');
          if (!q) return writeJson(res, 400, { error: 'missing q query parameter' });
          const useRegex = url.searchParams.get('regex') === 'true';
          let matcher;
          if (useRegex) {
            try { matcher = new RegExp(q, 'gi'); }
            catch (e) { return writeJson(res, 400, { error: `invalid regex: ${e.message}` }); }
          }
          const cfgDir = ctx.sessionsDirGetter();
          const items = listSkills(cfgDir);
          const matches = [];
          for (const s of items) {
            let body;
            try { body = loadSkill(s.name, cfgDir); } catch { continue; }
            let matchCount = 0;
            let firstExcerpt = null;
            if (useRegex) {
              for (const m of body.matchAll(matcher)) {
                matchCount++;
                if (firstExcerpt === null) {
                  const pos = m.index ?? 0;
                  const start = Math.max(0, pos - 40);
                  const end = Math.min(body.length, pos + m[0].length + 40);
                  firstExcerpt = (start > 0 ? '…' : '') + body.slice(start, end) + (end < body.length ? '…' : '');
                }
              }
            } else {
              const lower = body.toLowerCase();
              const ql = q.toLowerCase();
              let pos = 0;
              while (true) {
                const i = lower.indexOf(ql, pos);
                if (i < 0) break;
                matchCount++;
                if (firstExcerpt === null) {
                  const start = Math.max(0, i - 40);
                  const end = Math.min(body.length, i + ql.length + 40);
                  firstExcerpt = (start > 0 ? '…' : '') + body.slice(start, end) + (end < body.length ? '…' : '');
                }
                pos = i + ql.length;
              }
            }
            if (matchCount > 0) {
              matches.push({ name: s.name, bytes: s.bytes, matchCount, excerpt: firstExcerpt });
            }
          }
          return writeJson(res, 200, { query: q, regex: useRegex, matches });
        }
        case req.method === 'GET' && !!skillMatch: {
          // GET /skills/<name> — full markdown body as text/markdown.
          // 404 when the file is missing so the caller can branch.
          // 400 when the name fails skillPath validation (path traversal,
          // dotfile, etc.) — same protections as the CLI.
          const name = skillMatch[1];
          try {
            const cfgDir = ctx.sessionsDirGetter();
            const file = skillPath(name, cfgDir);
            if (!(await fileExists(file))) return writeJson(res, 404, { error: 'skill not found', name });
            const body = loadSkill(name, cfgDir);
            res.writeHead(200, {
              'content-type': 'text/markdown; charset=utf-8',
              'content-length': Buffer.byteLength(body),
            });
            return res.end(body);
          } catch (err) {
            return writeJson(res, 400, { error: err?.message || String(err) });
          }
        }
        case req.method === 'PUT' && !!skillMatch: {
          // PUT /skills/<name>  body = markdown text
          //   201 on first write, 200 on overwrite (caller can branch on
          //   the status if they care about idempotency vs newness).
          //   400 on invalid name (skillPath validation) or oversize body.
          const name = skillMatch[1];
          const cfgDir = ctx.sessionsDirGetter();
          let priorExists = false;
          try {
            // Validate name before reading the body so a bogus name fails
            // fast and we don't waste bandwidth.
            const file = skillPath(name, cfgDir);
            priorExists = await fileExists(file);
          } catch (err) {
            return writeJson(res, 400, { error: err?.message || String(err) });
          }
          let body;
          try { body = await readTextBody(req); }
          catch (err) { return writeJson(res, 400, { error: err?.message || String(err) }); }
          try {
            const written = installSkill(name, body, cfgDir);
            return writeJson(res, priorExists ? 200 : 201, {
              ok: true, name, path: written, bytes: body.length, replaced: priorExists,
            });
          } catch (err) {
            return writeJson(res, 400, { error: err?.message || String(err) });
          }
        }
        case req.method === 'DELETE' && !!skillMatch: {
          // DELETE /skills/<name>  idempotent: 200 whether the file
          // existed or not, mirroring DELETE /sessions/<id>. The body
          // reports `removed: true|false` so callers can branch when
          // they care.
          const name = skillMatch[1];
          const cfgDir = ctx.sessionsDirGetter();
          try {
            const file = skillPath(name, cfgDir);
            const existed = await fileExists(file);
            removeSkill(name, cfgDir);
            return writeJson(res, 200, { ok: true, name, removed: existed });
          } catch (err) {
            return writeJson(res, 400, { error: err?.message || String(err) });
          }
        }
        case req.method === 'DELETE' && !!sessionMatch: {
          // DELETE /sessions/<id> — idempotent. 200 on both "deleted" and
          // "didn't exist" so callers can use it as a reset without checking
          // first.
          const id = sessionMatch[1];
          try {
            ctx.sessionsMod.clearSession(id, ctx.sessionsDirGetter());
            return writeJson(res, 200, { ok: true, id });
          } catch (err) {
            return writeJson(res, 400, { error: err?.message || String(err) });
          }
        }
        case req.method === 'DELETE' && !!workflowMatch: {
          // DELETE /workflows/<sessionId> — idempotent: 200 with
          // `removed: true|false`. Same protection as the rest of the
          // delete routes — only files inside the configured state dir
          // are touched. The path matcher already rejects `..` and `/`,
          // and we re-resolve via path.join so a sessionId that resolves
          // outside the dir is rejected with 400.
          const sid = workflowMatch[1];
          const stateDir = ctx.workflowStateDir();
          // Note: `path` is shadowed inside this handler by the URL path
          // variable above — use `nodePath` (aliased import) for fs ops.
          const file = nodePath.join(stateDir, `${sid}.json`);
          // Confined-path check: file must resolve under stateDir. fs.realpathSync
          // would resolve symlinks too, but the dir may not exist yet — use
          // the resolved string-prefix check, which is enough since stateDir
          // is operator-controlled.
          const resolvedDir = nodePath.resolve(stateDir);
          const resolvedFile = nodePath.resolve(file);
          if (!resolvedFile.startsWith(resolvedDir + nodePath.sep) && resolvedFile !== resolvedDir) {
            return writeJson(res, 400, { error: 'invalid sessionId' });
          }
          try {
            const existed = fs.existsSync(resolvedFile);
            if (existed) fs.unlinkSync(resolvedFile);
            return writeJson(res, 200, { ok: true, sessionId: sid, removed: existed });
          } catch (err) {
            return writeJson(res, 500, { error: err?.message || String(err) });
          }
        }
        case route === 'POST /chat': {
          // Cost-cap gate: short-circuit before parsing the body so the
          // 402 fires fast and we don't pay for body buffering on a
          // request we're refusing.
          const breach = checkCostCap(metrics, costCap);
          if (breach) {
            return writeJson(res, 402, {
              error: 'cost cap exceeded',
              currency: breach.currency,
              spent: breach.spent,
              cap: breach.cap,
            });
          }
          // Full message-array input, single response (or stream). Useful when
          // the caller already has a message history and doesn't want to use
          // the disk-persisted session model.
          const body = await readJson(req);
          const cfg = ctx.readConfig();
          const provName = body.provider || cfg.provider || 'mock';
          const resolved = resolveProvider(body, provName, cachedByName, logger);
          if (resolved.error) return writeJson(res, 400, { error: resolved.error });
          const prov = resolved.provider;
          const messages = Array.isArray(body.messages) ? body.messages.filter(m => m && typeof m.role === 'string' && typeof m.content === 'string') : null;
          if (!messages || messages.length === 0) return writeJson(res, 400, { error: 'messages array required' });
          const thinkingBudget = Number(body.thinkingBudget) || 0;
          // Usage capture: opt-in via body.usage. The provider only does
          // the extra work (and pays the wire cost on OpenAI) when the
          // caller asks for it.
          let captured = null;
          const sendOpts = {
            apiKey: cfg['api-key'],
            model: body.model || cfg.model,
            thinking: thinkingBudget > 0 ? { enabled: true, budgetTokens: thinkingBudget } : undefined,
            onUsage: body.usage ? (u) => { captured = u; } : undefined,
          };
          // Cost lookup: body.cost:true asks the daemon to attach a cost
          // block when usage was captured AND cfg.rates has a card for
          // the active provider/model. Pure arithmetic — no extra wire
          // calls. Inline rather than helper-extract because the two
          // response paths (stream / non-stream) need to bind it
          // differently (SSE event vs JSON field).
          const computeCost = () => {
            if (!body.cost || !captured || !cfg.rates) return null;
            try {
              const c = costFromUsage(
                { provider: provName, model: body.model || cfg.model, usage: captured },
                cfg.rates,
              );
              if (c) accumulateMetricsFromCost(metrics, captured, c);
              return c;
            } catch { return null; }
          };
          if (body.stream === true) {
            writeSseHead(res);
            try {
              for await (const chunk of prov.sendMessage(messages, sendOpts)) {
                writeSse(res, 'token', { text: chunk });
                await new Promise(r => setImmediate(r));
              }
              if (captured) writeSse(res, 'usage', captured);
              const cost = computeCost();
              if (cost) writeSse(res, 'cost', cost);
              writeSse(res, 'done', { ok: true });
              return res.end();
            } catch (err) {
              writeSse(res, 'error', { message: err?.message || String(err) });
              return res.end();
            }
          }
          let acc = '';
          try {
            for await (const chunk of prov.sendMessage(messages, sendOpts)) acc += chunk;
            const cost = computeCost();
            const out = { reply: acc };
            if (captured) out.usage = captured;
            if (cost) out.cost = cost;
            return writeJson(res, 200, out);
          } catch (err) {
            const m = statusForProviderError(err);
            return writeJson(res, m.status, {
              error: err?.message || String(err),
              code: err?.code || null,
              ...(err?.retryAfterMs ? { retryAfterMs: err.retryAfterMs } : {}),
            }, m.headers || {});
          }
        }
        case route === 'POST /agent': {
          const breach = checkCostCap(metrics, costCap);
          if (breach) {
            return writeJson(res, 402, {
              error: 'cost cap exceeded',
              currency: breach.currency,
              spent: breach.spent,
              cap: breach.cap,
            });
          }
          const body = await readJson(req);
          const cfg = ctx.readConfig();
          const provName = body.provider || cfg.provider || 'mock';
          const resolved = resolveProvider(body, provName, cachedByName, logger);
          if (resolved.error) return writeJson(res, 400, { error: resolved.error });
          const prov = resolved.provider;
          const prompt = String(body.prompt ?? '').trim();
          if (!prompt) return writeJson(res, 400, { error: 'prompt required' });
          const model = body.model || cfg.model;
          const thinkingBudget = Number(body.thinkingBudget) || 0;

          // Session hydration if sessionId provided.
          const sid = body.sessionId || null;
          const cfgDir = ctx.sessionsDirGetter();
          let messages = sid ? ctx.sessionsMod.loadTurns(sid, cfgDir).map(t => ({ role: t.role, content: t.content })) : [];
          // Skill composition: body.skills can be a comma-separated string
          // ("a,b") or an array (["a","b"]). Compose only when no system
          // message already exists in the message array (so re-runs of
          // the same session don't double-prepend).
          const skillNames = Array.isArray(body.skills)
            ? body.skills
            : (typeof body.skills === 'string' ? body.skills.split(',').map(s => s.trim()).filter(Boolean) : []);
          if (skillNames.length > 0 && !messages.some(m => m.role === 'system')) {
            try {
              const sys = composeSystemPrompt(skillNames, cfgDir);
              if (sys) messages.unshift({ role: 'system', content: sys });
            } catch (err) {
              return writeJson(res, 400, { error: `skill error: ${err?.message || String(err)}` });
            }
          }
          messages.push({ role: 'user', content: prompt });
          if (sid) ctx.sessionsMod.appendTurn(sid, 'user', prompt, cfgDir);

          // body.usage opt-in mirrors POST /chat — provider only does the
          // extra work when the caller asks for it.
          let agentCaptured = null;
          const agentSendOpts = {
            apiKey: cfg['api-key'],
            model,
            thinking: thinkingBudget > 0 ? { enabled: true, budgetTokens: thinkingBudget } : undefined,
            onUsage: body.usage ? (u) => { agentCaptured = u; } : undefined,
          };
          const computeAgentCost = () => {
            if (!body.cost || !agentCaptured || !cfg.rates) return null;
            try {
              const c = costFromUsage(
                { provider: provName, model, usage: agentCaptured },
                cfg.rates,
              );
              if (c) accumulateMetricsFromCost(metrics, agentCaptured, c);
              return c;
            } catch { return null; }
          };

          if (body.stream === true) {
            writeSseHead(res);
            // Forward client disconnect to the provider so we don't keep
            // burning tokens after the consumer has gone away.
            const ac = new AbortController();
            req.on('aborted', () => ac.abort());
            res.on('close', () => { if (!res.writableEnded) ac.abort(); });
            let acc = '';
            try {
              for await (const chunk of prov.sendMessage(messages, { ...agentSendOpts, signal: ac.signal })) {
                if (ac.signal.aborted) break;
                acc += chunk;
                writeSse(res, 'token', { text: chunk });
                // Backpressure: yield so the caller can read each frame.
                await new Promise(r => setImmediate(r));
              }
              if (sid && !ac.signal.aborted) ctx.sessionsMod.appendTurn(sid, 'assistant', acc, cfgDir);
              if (!ac.signal.aborted) {
                if (agentCaptured) writeSse(res, 'usage', agentCaptured);
                const cost = computeAgentCost();
                if (cost) writeSse(res, 'cost', cost);
                writeSse(res, 'done', { ok: true });
              }
              return res.end();
            } catch (err) {
              if (err?.code === 'ABORT' || ac.signal.aborted) {
                // Client gave up — partial assistant turn is discarded.
                return res.end();
              }
              writeSse(res, 'error', { message: err?.message || String(err) });
              return res.end();
            }
          }

          // Non-streaming: collect then return once. Reuse agentSendOpts
          // (carrying the optional onUsage capture) so usage lands in the
          // response when body.usage was set.
          let acc = '';
          try {
            for await (const chunk of prov.sendMessage(messages, agentSendOpts)) acc += chunk;
            if (sid) ctx.sessionsMod.appendTurn(sid, 'assistant', acc, cfgDir);
            const cost = computeAgentCost();
            const out = { reply: acc };
            if (agentCaptured) out.usage = agentCaptured;
            if (cost) out.cost = cost;
            return writeJson(res, 200, out);
          } catch (err) {
            const m = statusForProviderError(err);
            return writeJson(res, m.status, {
              error: err?.message || String(err),
              code: err?.code || null,
              ...(err?.retryAfterMs ? { retryAfterMs: err.retryAfterMs } : {}),
            }, m.headers || {});
          }
        }
        default:
          return writeJson(res, 404, { error: 'not found', route });
      } /* eslint-disable-line no-fallthrough */
    } catch (err) {
      return writeJson(res, 500, { error: err?.message || String(err) });
    }
  };
}

/**
 * Graceful shutdown with a hard timeout. Calls `server.close()` so the
 * server stops accepting new connections and waits for in-flight to
 * drain — but races against `timeoutMs` so a hung stream can't keep
 * the process alive forever. After timeout we force-close every open
 * connection (Node ≥18.2) and resolve.
 *
 * Returns `{ forced: boolean }`:
 *   forced=false → graceful drain completed in time
 *   forced=true  → timeout fired; connections were force-closed
 *
 * Exported for unit testing without spawning a real daemon.
 *
 * @param {{ close: (cb: (err?: Error) => void) => void, closeAllConnections?: () => void }} server
 * @param {number} timeoutMs
 */
export function gracefulShutdown(server, timeoutMs) {
  return new Promise((resolve) => {
    let resolved = false;
    const finish = (forced) => {
      if (resolved) return;
      resolved = true;
      resolve({ forced });
    };
    const timer = setTimeout(() => {
      if (typeof server.closeAllConnections === 'function') {
        try { server.closeAllConnections(); } catch { /* swallow */ }
      }
      finish(true);
    }, timeoutMs);
    timer.unref?.();
    server.close((err) => {
      clearTimeout(timer);
      finish(false);
    });
  });
}

/**
 * Start the daemon. Always binds 127.0.0.1.
 * @param {{
 *   port?: number,
 *   once?: boolean,
 *   readConfig: () => Record<string, unknown>,
 *   sessionsDirGetter: () => string,
 *   sessionsMod: typeof import('./sessions.mjs'),
 *   version: () => string,
 *   authToken?: string,
 *   allowedOrigins?: string[],
 *   rateLimit?: { capacity?: number, refillPerSec?: number } | null,
 *   responseCache?: { maxEntries?: number, ttlMs?: number } | true | null,
 *   logger?: ReturnType<typeof createLogger> | null,
 *   costCap?: Record<string, number> | null,
 * }} opts
 * @returns {Promise<{ port: number, server: http.Server, close: () => Promise<void> }>}
 */
export async function startDaemon(opts) {
  const handler = makeHandler(opts);
  const server = http.createServer(async (req, res) => {
    await handler(req, res);
    if (opts.once) {
      // Allow the response to flush before closing.
      setImmediate(() => server.close());
    }
  });
  return new Promise((resolve) => {
    server.listen(opts.port ?? 0, '127.0.0.1', () => {
      const addr = server.address();
      const port = typeof addr === 'object' && addr ? addr.port : 0;
      resolve({
        port,
        server,
        close: () => new Promise(r => server.close(() => r())),
      });
    });
  });
}
