import { test, expect, request } from '@playwright/test';
import { execSync } from 'node:child_process';

// Ralph loop acceptance verifications. These are thin wrappers around
// the existing `scripts/e2e-*.mjs` suite so the runner-style command
// `npx playwright test` exercises real product behaviour rather than
// inventing parallel tests.

const PORT = process.env.PORT || '8080';
const BASE = `http://127.0.0.1:${PORT}`;

function run(script: string): { stdout: string; code: number } {
  try {
    const stdout = execSync(`PORT=${PORT} node scripts/${script}`, {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return { stdout, code: 0 };
  } catch (e: unknown) {
    const err = e as { stdout?: string; status?: number };
    return { stdout: err.stdout || '', code: err.status ?? 1 };
  }
}

test.describe('LazyClaude acceptance', () => {
  test('server is reachable', async () => {
    const ctx = await request.newContext();
    const r = await ctx.get(`${BASE}/`);
    expect(r.status()).toBe(200);
    await ctx.dispose();
  });

  // Workflow + low-latency: existing e2e exercises a 7-node flow and
  // measures live SSE tick lag (<1ms historically).
  test('workflow engine runs nodes with low SSE tick lag', () => {
    const { stdout, code } = run('e2e-jj-live-run-lag.mjs');
    expect(code).toBe(0);
    expect(stdout).toMatch(/perTick_ms:\s*\d+(?:\.\d+)?/);
  });

  // Forced node failure → cancel siblings, mark pending nodes
  // cancelled, terminate run procs.
  test('forced node failure triggers full rollback', () => {
    const { stdout, code } = run('e2e-fail-fast-status.mjs');
    expect(code).toBe(0);
    expect(stdout).toMatch(/n-err status = err/);
    expect(stdout).toMatch(/n-canc status = cancelled/);
  });

  test('mid-flight sibling termination on failure', () => {
    const { stdout, code } = run('e2e-mm-fail-fast.mjs');
    expect(code).toBe(0);
    expect(stdout).toMatch(/PASS/);
  });

  // Run cancel API end-to-end.
  test('workflow run-cancel API returns ok+live', () => {
    const { stdout, code } = run('e2e-run-cancel-api.mjs');
    expect(code).toBe(0);
    expect(stdout).toMatch(/cancel response carries `live` boolean/);
  });

  // Chat UI sends/receives.
  test('chat slash command surface (smoke)', () => {
    const { stdout, code } = run('e2e-chat-slash-smoke.mjs');
    expect(code).toBe(0);
  });

  // Terminal command can configure provider settings (`lazyclaude get/set`).
  test('terminal lazyclaude get/set configures preferences', () => {
    const { stdout, code } = run('e2e-terminal-set-prefs.mjs');
    expect(code).toBe(0);
  });

  // 50+ tab smoke — proves no console errors across the dashboard.
  test('all dashboard tabs render without console errors', () => {
    const { stdout, code } = run('e2e-tabs-smoke.mjs');
    expect(code).toBe(0);
    expect(stdout).toMatch(/탭 모두 통과/);
  });
});
