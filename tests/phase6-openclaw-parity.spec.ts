import { test, expect } from '@playwright/test';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';

const REPO_ROOT = process.cwd();
const CLI = path.join(REPO_ROOT, 'src/lazyclaw/cli.mjs');

function tmpConfigDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'lc-cfg-'));
}

function runCli(args: string[], cfgDir: string, env: NodeJS.ProcessEnv = {}) {
  return spawnSync(process.execPath, [CLI, ...args], {
    encoding: 'utf8',
    env: { ...process.env, LAZYCLAW_CONFIG_DIR: cfgDir, ...env },
  });
}

test.describe('Phase 6 — OpenClaw parity', () => {
  test('doctor returns diagnostic JSON with required fields', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    runCli(['config', 'set', 'model', 'claude-opus-4-7'], dir);
    const r = runCli(['doctor'], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out).toMatchObject({
      ok: expect.any(Boolean),
      configPath: expect.stringContaining('config.json'),
      provider: 'mock',
      model: 'claude-opus-4-7',
      hasApiKey: false,
      nodeVersion: expect.stringMatching(/^v\d+\./),
      platform: expect.any(String),
    });
  });

  test('doctor flags missing config as not ok', () => {
    const dir = tmpConfigDir();
    const r = runCli(['doctor'], dir);
    // doctor prints status with ok=false and exits 1 when required fields missing
    const out = JSON.parse(r.stdout);
    expect(out.ok).toBe(false);
    expect(out.issues).toEqual(expect.arrayContaining([expect.stringContaining('provider')]));
    expect(r.status).toBe(1);
  });

  test('onboard --non-interactive writes full config in one shot', () => {
    const dir = tmpConfigDir();
    const r = runCli(
      ['onboard', '--non-interactive', '--provider', 'anthropic', '--model', 'claude-opus-4-7', '--api-key', 'sk-ant-x'],
      dir,
    );
    expect(r.status).toBe(0);
    const cfg = JSON.parse(fs.readFileSync(path.join(dir, 'config.json'), 'utf8'));
    expect(cfg).toMatchObject({ provider: 'anthropic', model: 'claude-opus-4-7', 'api-key': 'sk-ant-x' });
  });

  test('onboard accepts unified provider/model string', () => {
    const dir = tmpConfigDir();
    const r = runCli(
      ['onboard', '--non-interactive', '--model', 'anthropic/claude-opus-4-7', '--api-key', 'sk-ant-x'],
      dir,
    );
    expect(r.status).toBe(0);
    const cfg = JSON.parse(fs.readFileSync(path.join(dir, 'config.json'), 'utf8'));
    // Splits "anthropic/claude-opus-4-7" into provider + model
    expect(cfg.provider).toBe('anthropic');
    expect(cfg.model).toBe('claude-opus-4-7');
  });

  test('status command prints provider/model/keyMasked and never leaks the raw key', () => {
    const dir = tmpConfigDir();
    runCli(['onboard', '--non-interactive', '--provider', 'mock', '--model', 'claude-opus-4-7', '--api-key', 'sk-secret-do-not-leak'], dir);
    const r = runCli(['status'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).not.toContain('sk-secret-do-not-leak');
    const out = JSON.parse(r.stdout);
    expect(out.provider).toBe('mock');
    expect(out.keyMasked).toMatch(/^sk-\*+/);
  });

  test('chat /status slash returns current config without leaking the key', async () => {
    const dir = tmpConfigDir();
    runCli(['onboard', '--non-interactive', '--provider', 'mock', '--model', 'claude-opus-4-7', '--api-key', 'sk-secret-leak-test'], dir);

    const child = spawn(process.execPath, [CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stderr.on('data', d => chunks.push(d.toString()));

    child.stdin.write('/status\n');
    const t0 = Date.now();
    while (Date.now() - t0 < 3000) {
      if (chunks.join('').includes('keyMasked')) break;
      await new Promise(r => setTimeout(r, 30));
    }
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));
    const all = chunks.join('');
    expect(all).toContain('keyMasked');
    expect(all).not.toContain('sk-secret-leak-test');
  });

  test('chat /new clears messages so the next reply does not see prior context', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);

    const child = spawn(process.execPath, [CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));

    child.stdin.write('first\n');
    await new Promise(r => setTimeout(r, 250));
    child.stdin.write('/new\n');
    await new Promise(r => setTimeout(r, 100));
    child.stdin.write('second\n');
    await new Promise(r => setTimeout(r, 400));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));

    const out = chunks.join('');
    expect(out).toContain('mock-reply: first');
    expect(out).toContain('mock-reply: second');
    expect(out).toMatch(/cleared|new conversation/i);
  });

  test('chat /help lists at least the documented slash commands', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);

    const child = spawn(process.execPath, [CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stdin.write('/help\n');
    await new Promise(r => setTimeout(r, 300));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));

    const out = chunks.join('');
    for (const cmd of ['/status', '/new', '/usage', '/help', '/exit']) {
      expect(out).toContain(cmd);
    }
  });

  test('anthropic provider hits messages endpoint with stream=true via injected fetch', async () => {
    // The provider should accept an injected fetch (for offline tests). When
    // a key is present and the model is set, it issues POST /v1/messages
    // with stream=true and parses the SSE delta events.
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    const calls: any[] = [];
    const fakeFetch = async (url: string, init: any) => {
      calls.push({ url, headers: init.headers, body: JSON.parse(init.body) });
      const sse =
        'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi"}}\n\n' +
        'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":" there"}}\n\n' +
        'event: message_stop\ndata: {"type":"message_stop"}\n\n';
      return {
        ok: true,
        status: 200,
        body: new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(sse));
            controller.close();
          },
        }),
      };
    };

    const out: string[] = [];
    for await (const chunk of mod.anthropicProvider.sendMessage(
      [{ role: 'user', content: 'hello' }],
      { apiKey: 'sk-ant-x', model: 'claude-opus-4-7', fetch: fakeFetch as any },
    )) {
      out.push(chunk);
    }
    expect(out.join('')).toBe('Hi there');
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain('/v1/messages');
    expect(calls[0].body.stream).toBe(true);
    expect(calls[0].body.model).toBe('claude-opus-4-7');
    expect(calls[0].headers['x-api-key']).toBe('sk-ant-x');
    expect(calls[0].headers['anthropic-version']).toBeTruthy();
  });

  // Daemon helper: spawn `lazyclaw daemon --port 0`, wait for the bound URL
  // line on stdout, return the URL plus a cleanup hook.
  function startDaemonProc(cfgDir: string): Promise<{ url: string, kill: () => Promise<void> }> {
    return new Promise((resolve, reject) => {
      const child = spawn(process.execPath, [CLI, 'daemon', '--port', '0'], {
        env: { ...process.env, LAZYCLAW_CONFIG_DIR: cfgDir },
        stdio: ['ignore', 'pipe', 'pipe'],
      });
      let buf = '';
      const onData = (d: Buffer) => {
        buf += d.toString();
        const nl = buf.indexOf('\n');
        if (nl < 0) return;
        const line = buf.slice(0, nl);
        try {
          const obj = JSON.parse(line);
          if (obj.url) {
            child.stdout.off('data', onData);
            resolve({
              url: obj.url,
              kill: () => new Promise(r => { child.once('close', () => r()); child.kill('SIGTERM'); }),
            });
          }
        } catch { /* keep buffering */ }
      };
      child.stdout.on('data', onData);
      child.stderr.on('data', d => { /* drain */ d; });
      child.on('error', reject);
      setTimeout(() => reject(new Error('daemon did not boot in 5s')), 5000);
    });
  }

  test('daemon GET /version returns the version JSON', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/version`).then(x => x.json());
      expect(r.version).toMatch(/^\d+\.\d+\.\d+/);
      expect(r.nodeVersion).toMatch(/^v\d+\./);
    } finally { await d.kill(); }
  });

  test('daemon GET /providers matches the providers list CLI subcommand', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/providers`).then(x => x.json());
      const names = r.map((p: any) => p.name);
      expect(names).toEqual(expect.arrayContaining(['mock', 'anthropic', 'openai']));
    } finally { await d.kill(); }
  });

  test('daemon POST /agent returns a non-streaming reply for the mock provider', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'hello daemon' }),
      }).then(x => x.json());
      expect(r.reply).toContain('mock-reply: hello daemon');
    } finally { await d.kill(); }
  });

  test('daemon POST /agent appends turns to a session when sessionId is set', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      const reply = await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'remember me', sessionId: 'daemon-test' }),
      }).then(x => x.json());
      expect(reply.reply).toContain('mock-reply: remember me');
      const log = path.join(dir, 'sessions', 'daemon-test.jsonl');
      expect(fs.existsSync(log)).toBe(true);
      const turns = fs.readFileSync(log, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));
      expect(turns.map(t => t.role)).toEqual(['user', 'assistant']);
    } finally { await d.kill(); }
  });

  test('daemon POST /agent with stream=true streams tokens via SSE', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      const res = await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'stream me', stream: true }),
      });
      expect(res.headers.get('content-type')).toContain('text/event-stream');
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let acc = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        acc += decoder.decode(value);
      }
      expect(acc).toMatch(/event: token/);
      expect(acc).toMatch(/event: done/);
      // Reassemble the streamed text from the token frames.
      const tokens: string[] = [];
      for (const frame of acc.split('\n\n')) {
        const m = frame.match(/^event: token\s*\ndata: (.+)$/m);
        if (m) try { tokens.push(JSON.parse(m[1]).text); } catch { /* skip */ }
      }
      expect(tokens.join('')).toContain('mock-reply: stream me');
    } finally { await d.kill(); }
  });

  test('daemon GET /doctor mirrors CLI doctor and 503s when config invalid', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/doctor`);
      // No config → ok=false → 503
      expect(r.status).toBe(503);
      const j = await r.json();
      expect(j.ok).toBe(false);
      expect(j.issues.length).toBeGreaterThan(0);
    } finally { await d.kill(); }
  });

  test('daemon GET /doctor returns 200 once config is valid', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/doctor`);
      expect(r.status).toBe(200);
      const j = await r.json();
      expect(j.ok).toBe(true);
      expect(j.knownProviders).toEqual(expect.arrayContaining(['mock']));
    } finally { await d.kill(); }
  });

  test('daemon POST /chat takes a full message array and returns the reply', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/chat`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ messages: [
          { role: 'user', content: 'first' },
          { role: 'assistant', content: 'first reply' },
          { role: 'user', content: 'follow up' },
        ]}),
      });
      expect(r.status).toBe(200);
      const j = await r.json();
      expect(j.reply).toContain('mock-reply: follow up');
    } finally { await d.kill(); }
  });

  test('daemon POST /chat 400 when messages is missing or empty', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir);
    try {
      const r1 = await fetch(`${d.url}/chat`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({}) });
      expect(r1.status).toBe(400);
      const r2 = await fetch(`${d.url}/chat`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ messages: [] }) });
      expect(r2.status).toBe(400);
    } finally { await d.kill(); }
  });

  test('daemon GET /sessions/<id> returns turns; DELETE clears the file', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    fs.mkdirSync(path.join(dir, 'sessions'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'sessions', 'apple.jsonl'),
      JSON.stringify({ role: 'user', content: 'hi', ts: 1 }) + '\n' +
      JSON.stringify({ role: 'assistant', content: 'hello', ts: 2 }) + '\n');
    const d = await startDaemonProc(dir);
    try {
      const get = await fetch(`${d.url}/sessions/apple`);
      expect(get.status).toBe(200);
      const got = await get.json();
      expect(got.id).toBe('apple');
      expect(got.turns.length).toBe(2);

      const del = await fetch(`${d.url}/sessions/apple`, { method: 'DELETE' });
      expect(del.status).toBe(200);
      expect(fs.existsSync(path.join(dir, 'sessions', 'apple.jsonl'))).toBe(false);

      // Idempotent: deleting again still 200s.
      const del2 = await fetch(`${d.url}/sessions/apple`, { method: 'DELETE' });
      expect(del2.status).toBe(200);

      // GET on a missing session is 404 (distinct from "session is empty").
      const getMissing = await fetch(`${d.url}/sessions/apple`);
      expect(getMissing.status).toBe(404);
    } finally { await d.kill(); }
  });

  test('daemon POST /agent with no prompt returns 400', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir);
    try {
      const res = await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({}),
      });
      expect(res.status).toBe(400);
      const j = await res.json();
      expect(j.error).toMatch(/prompt required/);
    } finally { await d.kill(); }
  });

  test('providers list returns the registered providers with their key requirement', () => {
    const dir = tmpConfigDir();
    const r = runCli(['providers', 'list'], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    const names = out.map((p: any) => p.name);
    expect(names).toEqual(expect.arrayContaining(['mock', 'anthropic', 'openai']));
    const mock = out.find((p: any) => p.name === 'mock');
    expect(mock.requiresApiKey).toBe(false);
    const anthropic = out.find((p: any) => p.name === 'anthropic');
    expect(anthropic.requiresApiKey).toBe(true);
    expect(anthropic.suggestedModels).toEqual(expect.arrayContaining(['claude-opus-4-7']));
  });

  test('providers info <name> returns the static metadata', () => {
    const dir = tmpConfigDir();
    const r = runCli(['providers', 'info', 'anthropic'], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out.name).toBe('anthropic');
    expect(out.endpoint).toContain('anthropic.com');
    expect(out.defaultModel).toBe('claude-opus-4-7');
  });

  test('providers info on unknown provider exits 2 with a registered-list hint', () => {
    const dir = tmpConfigDir();
    const r = runCli(['providers', 'info', 'nonsense'], dir);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/unknown provider/);
    expect(r.stderr).toMatch(/mock/);
  });

  test('chat --session persists turns to <configDir>/sessions/<id>.jsonl', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const child = spawn(process.execPath, [CLI, 'chat', '--session', 'feat-x'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stdin.write('first message\n');
    await new Promise(r => setTimeout(r, 600));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));

    const file = path.join(dir, 'sessions', 'feat-x.jsonl');
    expect(fs.existsSync(file)).toBe(true);
    const lines = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));
    expect(lines.length).toBeGreaterThanOrEqual(2);
    expect(lines[0]).toMatchObject({ role: 'user', content: 'first message' });
    expect(lines[1]).toMatchObject({ role: 'assistant', content: expect.stringContaining('mock-reply: first message') });
  });

  test('chat --session resumes prior turns on next invocation', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const turn = (input: string) => new Promise<string>((resolve) => {
      const child = spawn(process.execPath, [CLI, 'chat', '--session', 'sticky'], {
        env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      const chunks: string[] = [];
      child.stdout.on('data', d => chunks.push(d.toString()));
      child.stdin.write(input + '\n');
      setTimeout(() => { child.stdin.write('/exit\n'); child.stdin.end(); }, 500);
      child.on('close', () => resolve(chunks.join('')));
    });
    await turn('first');
    const second = await turn('second');
    // Second invocation should announce that it resumed prior turns.
    expect(second).toMatch(/resumed session sticky with 2 prior turn\(s\)/);
  });

  test('sessions list returns recent sessions sorted by mtime descending', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    // Record two sessions; the second one is newer.
    const dirSessions = path.join(dir, 'sessions');
    fs.mkdirSync(dirSessions, { recursive: true });
    fs.writeFileSync(path.join(dirSessions, 'older.jsonl'), JSON.stringify({ role: 'user', content: 'a', ts: 1 }) + '\n');
    fs.writeFileSync(path.join(dirSessions, 'newer.jsonl'), JSON.stringify({ role: 'user', content: 'b', ts: 2 }) + '\n');
    // Touch newer to ensure mtime ordering.
    const now = Date.now();
    fs.utimesSync(path.join(dirSessions, 'older.jsonl'), now / 1000 - 60, now / 1000 - 60);
    fs.utimesSync(path.join(dirSessions, 'newer.jsonl'), now / 1000, now / 1000);
    const r = runCli(['sessions', 'list'], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out.map((s: any) => s.id)).toEqual(['newer', 'older']);
  });

  test('sessions clear removes the file', () => {
    const dir = tmpConfigDir();
    fs.mkdirSync(path.join(dir, 'sessions'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'sessions', 'doomed.jsonl'), JSON.stringify({ role: 'user', content: 'x', ts: 1 }) + '\n');
    const r = runCli(['sessions', 'clear', 'doomed'], dir);
    expect(r.status).toBe(0);
    expect(fs.existsSync(path.join(dir, 'sessions', 'doomed.jsonl'))).toBe(false);
  });

  test('sessionPath rejects path-traversal ids', async () => {
    const sm = await import('../src/lazyclaw/sessions.mjs' as string);
    expect(() => sm.sessionPath('../etc/passwd', '/tmp/whatever')).toThrow();
    expect(() => sm.sessionPath('a/b', '/tmp')).toThrow();
    expect(() => sm.sessionPath('.', '/tmp')).toThrow();
  });

  test('version subcommand prints VERSION + node + platform as JSON', () => {
    const dir = tmpConfigDir();
    const r = runCli(['version'], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out.version).toMatch(/^\d+\.\d+\.\d+/);
    expect(out.nodeVersion).toMatch(/^v\d+\./);
    expect(out.platform).toMatch(/-/);
  });

  test('anthropic provider sends thinking config when budget is set, and routes thinking_delta to onThinking callback', async () => {
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    const calls: any[] = [];
    const sse =
      'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"weighing"}}\n\n' +
      'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":" options"}}\n\n' +
      'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"answer"}}\n\n' +
      'event: message_stop\ndata: {"type":"message_stop"}\n\n';
    const fakeFetch = async (url: string, init: any) => {
      calls.push({ url, body: JSON.parse(init.body) });
      return {
        ok: true, status: 200,
        body: new ReadableStream({
          start(controller) { controller.enqueue(new TextEncoder().encode(sse)); controller.close(); },
        }),
      };
    };
    const thinkingChunks: string[] = [];
    const textChunks: string[] = [];
    for await (const chunk of mod.anthropicProvider.sendMessage(
      [{ role: 'user', content: 'hard problem' }],
      {
        apiKey: 'sk-ant-x', model: 'claude-opus-4-7',
        fetch: fakeFetch as any,
        thinking: { enabled: true, budgetTokens: 5000 },
        onThinking: (t: string) => thinkingChunks.push(t),
      },
    )) textChunks.push(chunk);
    expect(textChunks.join('')).toBe('answer');
    expect(thinkingChunks.join('')).toBe('weighing options');
    expect(calls[0].body.thinking).toEqual({ type: 'enabled', budget_tokens: 5000 });
  });

  test('anthropic provider drops thinking_delta when no callback is provided (back-compat)', async () => {
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    const sse =
      'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"silent"}}\n\n' +
      'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hi"}}\n\n' +
      'event: message_stop\ndata: {"type":"message_stop"}\n\n';
    const fakeFetch = async () => ({
      ok: true, status: 200,
      body: new ReadableStream({
        start(c) { c.enqueue(new TextEncoder().encode(sse)); c.close(); },
      }),
    });
    const out: string[] = [];
    for await (const c of mod.anthropicProvider.sendMessage(
      [{ role: 'user', content: 'q' }],
      { apiKey: 'sk-ant-x', model: 'claude-opus-4-7', fetch: fakeFetch as any },
    )) out.push(c);
    expect(out.join('')).toBe('hi');
  });

  test('agent one-shot streams reply for a positional prompt and exits 0', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const r = runCli(['agent', 'hello world'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('mock-reply: hello world');
  });

  test('agent reads stdin when prompt is "-"', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const child = spawn(process.execPath, [CLI, 'agent', '-'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    child.stdin.write('piped prompt\n');
    child.stdin.end();
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    await new Promise<void>(resolve => child.on('close', () => resolve()));
    expect(chunks.join('')).toContain('mock-reply: piped prompt');
  });

  test('agent --provider flag overrides config provider', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    // Override to anthropic without an api-key so we expect the provider
    // to throw INVALID_KEY — this proves the flag actually switched
    // providers (otherwise the mock would happily reply).
    const r = runCli(['agent', 'hi', '--provider', 'anthropic'], dir);
    expect(r.status).toBe(1);
    expect(r.stderr).toMatch(/missing api key|invalid|INVALID_KEY/i);
  });

  test('openai provider hits chat/completions with stream=true and parses [DONE]', async () => {
    const mod = await import('../src/lazyclaw/providers/openai.mjs' as string);
    const calls: any[] = [];
    const fakeFetch = async (url: string, init: any) => {
      calls.push({ url, headers: init.headers, body: JSON.parse(init.body) });
      const sse =
        'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n' +
        'data: {"choices":[{"delta":{"content":" there"}}]}\n\n' +
        'data: [DONE]\n\n';
      return {
        ok: true,
        status: 200,
        body: new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(sse));
            controller.close();
          },
        }),
      };
    };
    const out: string[] = [];
    for await (const chunk of mod.openaiProvider.sendMessage(
      [{ role: 'user', content: 'hello' }],
      { apiKey: 'sk-x', model: 'gpt-4.1', fetch: fakeFetch as any },
    )) out.push(chunk);
    expect(out.join('')).toBe('Hi there');
    expect(calls[0].url).toContain('/v1/chat/completions');
    expect(calls[0].headers.authorization).toBe('Bearer sk-x');
    expect(calls[0].body.stream).toBe(true);
    expect(calls[0].body.model).toBe('gpt-4.1');
  });

  test('openai provider 401 → INVALID_KEY', async () => {
    const mod = await import('../src/lazyclaw/providers/openai.mjs' as string);
    const fakeFetch = async () => ({
      ok: false, status: 401,
      text: async () => '{"error":{"message":"invalid"}}',
    });
    let caught: any = null;
    try {
      for await (const _c of mod.openaiProvider.sendMessage(
        [{ role: 'user', content: 'hi' }],
        { apiKey: 'sk-bad', model: 'gpt-4.1', fetch: fakeFetch as any },
      )) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught).toBeTruthy();
    expect(String(caught?.code || caught?.message)).toMatch(/INVALID_KEY|invalid/i);
  });

  test('doctor knows about the openai provider too', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'openai'], dir);
    runCli(['config', 'set', 'api-key', 'sk-x'], dir);
    runCli(['config', 'set', 'model', 'gpt-4.1'], dir);
    const r = runCli(['doctor'], dir);
    const out = JSON.parse(r.stdout);
    expect(out.knownProviders).toEqual(expect.arrayContaining(['mock', 'anthropic', 'openai']));
    expect(out.ok).toBe(true);
  });

  test('anthropic provider preserves UTF-8 codepoints split across chunk boundaries', async () => {
    // Korean "안녕" = E384 ABC8 EB85 95 (6 bytes). We split mid-codepoint so
    // a non-streaming decoder would produce U+FFFD. The streaming TextDecoder
    // inside the provider must hold the partial bytes until the next chunk.
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    const fullSse =
      'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"안녕"}}\n\n' +
      'event: message_stop\ndata: {"type":"message_stop"}\n\n';
    const fullBytes = new TextEncoder().encode(fullSse);
    // Split right inside the first multi-byte codepoint of "안" so the first
    // chunk ends mid-character.
    const splitAt = fullSse.indexOf('안') + 1;  // string-index, not byte-index
    // Convert to byte-aware split by finding the byte offset of the string-index.
    const before = fullSse.slice(0, splitAt);
    const beforeBytes = new TextEncoder().encode(before);
    // Drop one trailing byte from beforeBytes so the codepoint is split.
    const cutByte = beforeBytes.length - 1;
    const part1 = fullBytes.slice(0, cutByte);
    const part2 = fullBytes.slice(cutByte);

    const fakeFetch = async () => ({
      ok: true,
      status: 200,
      body: new ReadableStream({
        start(controller) {
          controller.enqueue(part1);
          controller.enqueue(part2);
          controller.close();
        },
      }),
    });
    const out: string[] = [];
    for await (const chunk of mod.anthropicProvider.sendMessage(
      [{ role: 'user', content: 'hi' }],
      { apiKey: 'sk-ant-x', model: 'claude-opus-4-7', fetch: fakeFetch as any },
    )) {
      out.push(chunk);
    }
    expect(out.join('')).toBe('안녕');
  });

  test('anthropic provider surfaces 401 as INVALID_KEY error', async () => {
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    const fakeFetch = async () => ({
      ok: false,
      status: 401,
      text: async () => '{"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}',
    });
    let caught: any = null;
    try {
      for await (const _chunk of mod.anthropicProvider.sendMessage(
        [{ role: 'user', content: 'hi' }],
        { apiKey: 'sk-bad', model: 'claude-opus-4-7', fetch: fakeFetch as any },
      )) {
        // drain
      }
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeTruthy();
    expect(String(caught?.code || caught?.message)).toMatch(/INVALID_KEY|invalid/i);
  });
});
