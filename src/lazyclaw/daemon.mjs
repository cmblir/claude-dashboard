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
import path from 'node:path';
import fs from 'node:fs';

import { PROVIDERS, PROVIDER_INFO, maskApiKey } from './providers/registry.mjs';
import { composeSystemPrompt } from './skills.mjs';

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

function writeJson(res, status, obj, extraHeaders = {}) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
    ...extraHeaders,
  });
  res.end(body);
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
 * @param {{
 *   readConfig: () => Record<string, unknown>,
 *   sessionsDirGetter: () => string,
 *   sessionsMod: typeof import('./sessions.mjs'),
 *   version: () => string,
 * }} ctx
 */
export function makeHandler(ctx) {
  return async function handler(req, res) {
    try {
      const url = new URL(req.url || '/', 'http://localhost');
      const route = `${req.method} ${url.pathname}`;
      const sessionMatch = url.pathname.match(/^\/sessions\/([^/]+)$/);
      switch (true) {
        case route === 'GET /version':
          return writeJson(res, 200, { version: ctx.version(), nodeVersion: process.version, platform: `${process.platform}-${process.arch}` });
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
          const list = ctx.sessionsMod.listSessions(ctx.sessionsDirGetter());
          return writeJson(res, 200, list.map(s => ({ id: s.id, bytes: s.bytes, mtime: new Date(s.mtimeMs).toISOString() })));
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
        case route === 'POST /chat': {
          // Full message-array input, single response (or stream). Useful when
          // the caller already has a message history and doesn't want to use
          // the disk-persisted session model.
          const body = await readJson(req);
          const cfg = ctx.readConfig();
          const provName = body.provider || cfg.provider || 'mock';
          const prov = PROVIDERS[provName];
          if (!prov) return writeJson(res, 400, { error: `unknown provider: ${provName}` });
          const messages = Array.isArray(body.messages) ? body.messages.filter(m => m && typeof m.role === 'string' && typeof m.content === 'string') : null;
          if (!messages || messages.length === 0) return writeJson(res, 400, { error: 'messages array required' });
          const thinkingBudget = Number(body.thinkingBudget) || 0;
          const sendOpts = {
            apiKey: cfg['api-key'],
            model: body.model || cfg.model,
            thinking: thinkingBudget > 0 ? { enabled: true, budgetTokens: thinkingBudget } : undefined,
          };
          if (body.stream === true) {
            writeSseHead(res);
            try {
              for await (const chunk of prov.sendMessage(messages, sendOpts)) {
                writeSse(res, 'token', { text: chunk });
                await new Promise(r => setImmediate(r));
              }
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
            return writeJson(res, 200, { reply: acc });
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
          const body = await readJson(req);
          const cfg = ctx.readConfig();
          const provName = body.provider || cfg.provider || 'mock';
          const prov = PROVIDERS[provName];
          if (!prov) return writeJson(res, 400, { error: `unknown provider: ${provName}` });
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

          if (body.stream === true) {
            writeSseHead(res);
            // Forward client disconnect to the provider so we don't keep
            // burning tokens after the consumer has gone away.
            const ac = new AbortController();
            req.on('aborted', () => ac.abort());
            res.on('close', () => { if (!res.writableEnded) ac.abort(); });
            let acc = '';
            try {
              for await (const chunk of prov.sendMessage(messages, {
                apiKey: cfg['api-key'],
                model,
                thinking: thinkingBudget > 0 ? { enabled: true, budgetTokens: thinkingBudget } : undefined,
                signal: ac.signal,
              })) {
                if (ac.signal.aborted) break;
                acc += chunk;
                writeSse(res, 'token', { text: chunk });
                // Backpressure: yield so the caller can read each frame.
                await new Promise(r => setImmediate(r));
              }
              if (sid && !ac.signal.aborted) ctx.sessionsMod.appendTurn(sid, 'assistant', acc, cfgDir);
              if (!ac.signal.aborted) writeSse(res, 'done', { ok: true });
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

          // Non-streaming: collect then return once.
          let acc = '';
          try {
            for await (const chunk of prov.sendMessage(messages, {
              apiKey: cfg['api-key'],
              model,
              thinking: thinkingBudget > 0 ? { enabled: true, budgetTokens: thinkingBudget } : undefined,
            })) acc += chunk;
            if (sid) ctx.sessionsMod.appendTurn(sid, 'assistant', acc, cfgDir);
            return writeJson(res, 200, { reply: acc });
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
 * Start the daemon. Always binds 127.0.0.1.
 * @param {{
 *   port?: number,
 *   once?: boolean,
 *   readConfig: () => Record<string, unknown>,
 *   sessionsDirGetter: () => string,
 *   sessionsMod: typeof import('./sessions.mjs'),
 *   version: () => string,
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
