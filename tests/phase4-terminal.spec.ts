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

test.describe('Phase 4 — Terminal Configuration', () => {
  test('config set persists to file', () => {
    const dir = tmpConfigDir();
    const r = runCli(['config', 'set', 'provider', 'mock'], dir);
    expect(r.status).toBe(0);
    const file = path.join(dir, 'config.json');
    expect(fs.existsSync(file)).toBe(true);
    const cfg = JSON.parse(fs.readFileSync(file, 'utf8'));
    expect(cfg.provider).toBe('mock');
  });

  test('config set api-key and model persist', () => {
    const dir = tmpConfigDir();
    expect(runCli(['config', 'set', 'provider', 'mock'], dir).status).toBe(0);
    expect(runCli(['config', 'set', 'api-key', 'sk-test-xyz'], dir).status).toBe(0);
    expect(runCli(['config', 'set', 'model', 'claude-haiku-4-5-20251001'], dir).status).toBe(0);
    const cfg = JSON.parse(fs.readFileSync(path.join(dir, 'config.json'), 'utf8'));
    expect(cfg.provider).toBe('mock');
    expect(cfg['api-key']).toBe('sk-test-xyz');
    expect(cfg.model).toBe('claude-haiku-4-5-20251001');
  });

  test('config get returns stored value (read-after-write)', () => {
    const dir = tmpConfigDir();
    expect(runCli(['config', 'set', 'provider', 'anthropic'], dir).status).toBe(0);
    const r = runCli(['config', 'get', 'provider'], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out).toEqual({ key: 'provider', value: 'anthropic' });
  });

  test('chat command sends input and receives response', async () => {
    const dir = tmpConfigDir();
    expect(runCli(['config', 'set', 'provider', 'mock'], dir).status).toBe(0);

    const child = spawn(process.execPath, [CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stderr.on('data', d => chunks.push(d.toString()));

    child.stdin.write('hello\n');
    // Wait for streamed reply.
    const start = Date.now();
    while (Date.now() - start < 5000) {
      if (chunks.join('').includes('mock-reply: hello')) break;
      await new Promise(r => setTimeout(r, 50));
    }
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));

    expect(chunks.join('')).toContain('mock-reply: hello');
  });
});
