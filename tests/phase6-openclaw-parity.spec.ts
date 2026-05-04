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
