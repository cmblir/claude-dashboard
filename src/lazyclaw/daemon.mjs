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

import { PROVIDERS, PROVIDER_INFO, maskApiKey } from './providers/registry.mjs';

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

function writeJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
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
      switch (route) {
        case 'GET /version':
          return writeJson(res, 200, { version: ctx.version(), nodeVersion: process.version, platform: `${process.platform}-${process.arch}` });
        case 'GET /providers':
          return writeJson(res, 200, Object.keys(PROVIDERS).map(name => {
            const meta = PROVIDER_INFO[name] || { name };
            return { name, requiresApiKey: !!meta.requiresApiKey, defaultModel: meta.defaultModel || null, suggestedModels: meta.suggestedModels || [] };
          }));
        case 'GET /status': {
          const cfg = ctx.readConfig();
          return writeJson(res, 200, {
            provider: cfg.provider || null,
            model: cfg.model || null,
            keyMasked: maskApiKey(cfg['api-key']),
          });
        }
        case 'GET /sessions': {
          const list = ctx.sessionsMod.listSessions(ctx.sessionsDirGetter());
          return writeJson(res, 200, list.map(s => ({ id: s.id, bytes: s.bytes, mtime: new Date(s.mtimeMs).toISOString() })));
        }
        case 'POST /agent': {
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
          messages.push({ role: 'user', content: prompt });
          if (sid) ctx.sessionsMod.appendTurn(sid, 'user', prompt, cfgDir);

          if (body.stream === true) {
            writeSseHead(res);
            let acc = '';
            try {
              for await (const chunk of prov.sendMessage(messages, {
                apiKey: cfg['api-key'],
                model,
                thinking: thinkingBudget > 0 ? { enabled: true, budgetTokens: thinkingBudget } : undefined,
              })) {
                acc += chunk;
                writeSse(res, 'token', { text: chunk });
                // Backpressure: yield so the caller can read each frame.
                await new Promise(r => setImmediate(r));
              }
              if (sid) ctx.sessionsMod.appendTurn(sid, 'assistant', acc, cfgDir);
              writeSse(res, 'done', { ok: true });
              return res.end();
            } catch (err) {
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
            return writeJson(res, 502, { error: err?.message || String(err), code: err?.code || null });
          }
        }
        default:
          return writeJson(res, 404, { error: 'not found', route });
      }
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
