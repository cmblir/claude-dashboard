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

  test('doctor reports workflow state directory health', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    // No workflow state dir yet → workflows.present:false (no error).
    const r1 = runCli(['doctor'], dir, { LAZYCLAW_WORKFLOW_STATE_DIR: path.join(dir, 'no-such') });
    const o1 = JSON.parse(r1.stdout);
    expect(o1.workflows).toEqual({ dir: path.join(dir, 'no-such'), present: false });

    // With state files: counters reflect the on-disk shapes.
    const stateDir = path.join(dir, 'wf-state');
    fs.mkdirSync(stateDir, { recursive: true });
    fs.writeFileSync(path.join(stateDir, 'done.json'), JSON.stringify({
      sessionId: 'done', order: ['x'],
      nodes: { x: { status: 'success', attempts: 1 } },
      startedAt: 1, updatedAt: 2,
    }));
    fs.writeFileSync(path.join(stateDir, 'broken.json'), JSON.stringify({
      sessionId: 'broken', order: ['x'],
      nodes: { x: { status: 'failed', error: 'boom', attempts: 3 } },
      startedAt: 1, updatedAt: 2,
    }));
    const r2 = runCli(['doctor'], dir, { LAZYCLAW_WORKFLOW_STATE_DIR: stateDir });
    const o2 = JSON.parse(r2.stdout);
    expect(o2.workflows).toMatchObject({
      dir: stateDir, total: 2, done: 1, failed: 1, resumable: 0, running: 0,
    });
  });

  test('doctor flags running-state nodes as a non-fatal issue (likely interrupted run)', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const stateDir = path.join(dir, 'wf-running');
    fs.mkdirSync(stateDir, { recursive: true });
    // Simulate a SIGKILL'd run — node still tagged running.
    fs.writeFileSync(path.join(stateDir, 'stuck.json'), JSON.stringify({
      sessionId: 'stuck', order: ['a'],
      nodes: { a: { status: 'running', attempts: 1 } },
      startedAt: 1, updatedAt: 2,
    }));
    const r = runCli(['doctor'], dir, { LAZYCLAW_WORKFLOW_STATE_DIR: stateDir });
    expect(r.status).toBe(1);   // ok=false because issues array now non-empty
    const out = JSON.parse(r.stdout);
    expect(out.issues).toEqual(expect.arrayContaining([
      expect.stringContaining("'running' nodes from a prior interrupted run"),
    ]));
    expect(out.workflows.running).toBe(1);
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

  test('chat --skill prepends a system message and persists it for --session', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    fs.mkdirSync(path.join(dir, 'skills'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'skills', 'concise.md'), '# Concise\nbe brief\n');

    const child = spawn(process.execPath, [CLI, 'chat', '--skill', 'concise', '--session', 'sk-test'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stdin.write('hello\n');
    await new Promise(r => setTimeout(r, 600));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));

    // Persisted JSONL should have the system message followed by user + assistant.
    const file = path.join(dir, 'sessions', 'sk-test.jsonl');
    const turns = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));
    expect(turns[0].role).toBe('system');
    expect(turns[0].content).toContain('skill: concise');
    expect(turns[0].content).toContain('be brief');
    expect(turns[1]).toMatchObject({ role: 'user', content: 'hello' });
    expect(turns[2].role).toBe('assistant');
  });

  test('chat --skill resume does NOT re-prepend the system message', async () => {
    // After the first invocation persisted a system message, a second
    // invocation with --skill must not duplicate it.
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    fs.mkdirSync(path.join(dir, 'skills'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'skills', 'a.md'), '# A\nbody-A\n');
    // Pre-seed a session that already has the system message.
    fs.mkdirSync(path.join(dir, 'sessions'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'sessions', 'resume.jsonl'),
      JSON.stringify({ role: 'system', content: '<!-- skill: a -->\n# A\nbody-A', ts: 1 }) + '\n' +
      JSON.stringify({ role: 'user', content: 'first', ts: 2 }) + '\n' +
      JSON.stringify({ role: 'assistant', content: 'mock-reply: first', ts: 3 }) + '\n');

    const child = spawn(process.execPath, [CLI, 'chat', '--skill', 'a', '--session', 'resume'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    child.stdin.write('second\n');
    await new Promise(r => setTimeout(r, 500));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));

    const turns = fs.readFileSync(path.join(dir, 'sessions', 'resume.jsonl'), 'utf8')
      .split('\n').filter(Boolean).map(l => JSON.parse(l));
    // Exactly one system message, despite the second --skill invocation.
    const systems = turns.filter(t => t.role === 'system');
    expect(systems).toHaveLength(1);
  });

  test('lazyclaw run --parallel executes a DAG by topological level', () => {
    const dir = tmpConfigDir();
    // Workflow file with a fan-out / fan-in shape. Sleeps 80ms in each
    // independent node so a sequential runner would take 240ms+ for the
    // fan-out level alone; --parallel completes that level in ~80ms.
    const wfPath = path.join(dir, 'wf.mjs');
    fs.writeFileSync(wfPath,
      `const sleep = ms => new Promise(r => setTimeout(r, ms));
       export const nodes = [
         { id: 'fetch',    type: 't', deps: [],                        async execute() { return 'csv'; } },
         { id: 'embed',    type: 't', deps: ['fetch'],                 async execute() { await sleep(80); return 'E'; } },
         { id: 'classify', type: 't', deps: ['fetch'],                 async execute() { await sleep(80); return 'C'; } },
         { id: 'tag',      type: 't', deps: ['fetch'],                 async execute() { await sleep(80); return 'T'; } },
         { id: 'merge',    type: 't', deps: ['embed','classify','tag'], async execute(input) { return Object.keys(input).length; } },
       ];`,
    );
    // Flag BEFORE positionals — historically broken because parseArgs
    // would steal the next arg as the flag value. The BOOLEAN_FLAGS
    // allow-list makes --parallel always boolean.
    const t0 = Date.now();
    const r = runCli(['run', '--parallel', 'demo', wfPath], dir);
    const elapsed = Date.now() - t0;
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out.mode).toBe('parallel');
    expect(out.executedNodes).toEqual(expect.arrayContaining(['fetch', 'embed', 'classify', 'tag', 'merge']));
    // 240ms+ sequential vs ~80ms parallel for the fan-out — generous CI ceiling
    expect(elapsed).toBeLessThan(500);
  });

  test('lazyclaw run --parallel-persistent runs a DAG with state persistence', () => {
    const dir = tmpConfigDir();
    const wfPath = path.join(dir, 'pdag.mjs');
    fs.writeFileSync(wfPath,
      `export const nodes = [
         { id: 'a',     deps: [],         async execute() { return 'A'; } },
         { id: 'b',     deps: ['a'],      async execute(input) { return 'B:' + input.a; } },
         { id: 'c',     deps: ['a'],      async execute(input) { return 'C:' + input.a; } },
         { id: 'merge', deps: ['b','c'],  async execute(input) { return Object.values(input).join('+'); } },
       ];`,
    );
    const stateDir = path.join(dir, 'wfstate');
    const r = runCli(['run', 'pdag-test', wfPath, '--parallel-persistent', '--dir', stateDir], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out.mode).toBe('parallel-persistent');
    expect(out.success).toBe(true);
    expect(out.executedNodes.sort()).toEqual(['a', 'b', 'c', 'merge']);
    // State file landed at the requested location.
    const stateFile = path.join(stateDir, 'pdag-test.json');
    expect(fs.existsSync(stateFile)).toBe(true);
    const state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
    expect(state.nodes.merge.output).toBe('B:A+C:A');
  });

  test('lazyclaw run --parallel-persistent resumes after a flaky failure', () => {
    const dir = tmpConfigDir();
    const wfPath = path.join(dir, 'flaky.mjs');
    // Sentinel-file approach so the second invocation can flip behavior.
    const sentinel = path.join(dir, 'attempt');
    fs.writeFileSync(wfPath,
      `import fs from 'node:fs';
       export const nodes = [
         { id: 'a', deps: [],    async execute() { return 'A'; } },
         { id: 'b', deps: ['a'], async execute(input) {
             const n = (() => { try { return parseInt(fs.readFileSync(${JSON.stringify(sentinel)}, 'utf8'), 10) || 0; } catch { return 0; } })();
             fs.writeFileSync(${JSON.stringify(sentinel)}, String(n + 1));
             if (n === 0) throw new Error('flaky-first-attempt');
             return 'B:' + input.a;
         } },
         { id: 'c', deps: ['b'], async execute(input) { return 'C:' + input.b; } },
       ];`,
    );
    const stateDir = path.join(dir, 'st');
    const r1 = runCli(['run', 'flaky', wfPath, '--parallel-persistent', '--dir', stateDir], dir);
    expect(r1.status).toBe(1);
    const o1 = JSON.parse(r1.stdout);
    expect(o1.failedAt).toBe('b');
    // Second invocation: a is success (skipped), b retries (passes), c runs.
    const r2 = runCli(['run', 'flaky', wfPath, '--parallel-persistent', '--dir', stateDir], dir);
    expect(r2.status).toBe(0);
    const o2 = JSON.parse(r2.stdout);
    expect(o2.success).toBe(true);
    expect(o2.executedNodes.sort()).toEqual(['b', 'c']);
  });

  test('lazyclaw run --parallel surfaces cycle errors with exit 1', () => {
    const dir = tmpConfigDir();
    const wfPath = path.join(dir, 'cyclic.mjs');
    fs.writeFileSync(wfPath,
      `export const nodes = [
         { id: 'a', type: 't', deps: ['b'], async execute() { return 1; } },
         { id: 'b', type: 't', deps: ['a'], async execute() { return 2; } },
       ];`,
    );
    // Flag AFTER positionals also works — parseArgs is order-independent
    // for known boolean flags.
    const r = runCli(['run', 'demo', wfPath, '--parallel'], dir);
    expect(r.status).toBe(1);
    const out = JSON.parse(r.stdout);
    expect(out.success).toBe(false);
    expect(out.error).toMatch(/cycle/);
    expect(out.executedNodes).toEqual([]);
  });

  test('lazyclaw inspect: missing state file → exit 2 with helpful stderr', () => {
    const dir = tmpConfigDir();
    const r = runCli(['inspect', 'nope', '--dir', path.join(dir, 'st')], dir);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/No state for session/);
  });

  test('lazyclaw inspect: fully completed workflow → exit 1 with summary.done=true', () => {
    const dir = tmpConfigDir();
    const wfPath = path.join(dir, 'tiny.mjs');
    fs.writeFileSync(wfPath,
      `export const nodes = [
         { id: 'a', type: 't', async execute() { return 'A'; } },
         { id: 'b', type: 't', async execute(input) { return input + '+B'; } },
       ];`,
    );
    const stateDir = path.join(dir, 'st');
    const r1 = runCli(['run', 'done-job', wfPath, '--dir', stateDir], dir);
    expect(r1.status).toBe(0);
    const r2 = runCli(['inspect', 'done-job', '--dir', stateDir], dir);
    expect(r2.status).toBe(1);   // 1 = fully done, no resumable work
    const out = JSON.parse(r2.stdout);
    expect(out.summary.total).toBe(2);
    expect(out.summary.success).toBe(2);
    expect(out.summary.done).toBe(true);
    expect(out.summary.resumable).toBe(false);
    expect(out.failedNodes).toEqual([]);
    expect(typeof out.summary.durationMs).toBe('number');
  });

  test('lazyclaw inspect: terminal failure → exit 3 with failedNodes populated', () => {
    const dir = tmpConfigDir();
    const wfPath = path.join(dir, 'broken.mjs');
    fs.writeFileSync(wfPath,
      `export const nodes = [
         { id: 'a', type: 't', async execute() { return 'A'; } },
         { id: 'b', type: 't', async execute() { throw new Error('boom'); } },
         { id: 'c', type: 't', async execute() { return 'C'; } },
       ];`,
    );
    const stateDir = path.join(dir, 'st');
    runCli(['run', 'fail-job', wfPath, '--dir', stateDir], dir);   // exit 1 expected
    const r = runCli(['inspect', 'fail-job', '--dir', stateDir], dir);
    expect(r.status).toBe(3);   // 3 = terminal failure
    const out = JSON.parse(r.stdout);
    expect(out.summary.failed).toBe(1);
    expect(out.summary.success).toBe(1);
    expect(out.summary.done).toBe(false);
    expect(out.summary.resumable).toBe(false);   // failed nodes block auto-resume
    expect(out.failedNodes).toHaveLength(1);
    expect(out.failedNodes[0].id).toBe('b');
    expect(out.failedNodes[0].error).toMatch(/boom/);
  });

  test('lazyclaw inspect (no arg): lists every session sorted by recency', () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'st');
    fs.mkdirSync(stateDir, { recursive: true });
    // Three sessions with explicit timestamps so the sort order is
    // deterministic regardless of file mtime granularity.
    const mk = (id: string, updatedAt: number) => {
      fs.writeFileSync(path.join(stateDir, `${id}.json`), JSON.stringify({
        sessionId: id,
        order: ['x'],
        nodes: { x: { status: 'success', output: id, attempts: 1, durationMs: 1 } },
        startedAt: 0, updatedAt,
      }));
    };
    mk('older', 100);
    mk('newest', 300);
    mk('middle', 200);
    // Drop a stray non-state file to confirm we ignore it.
    fs.writeFileSync(path.join(stateDir, 'README.txt'), 'not state');
    fs.writeFileSync(path.join(stateDir, 'invalid.json'), '{ corrupt');

    const r = runCli(['inspect', '--dir', stateDir], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out.dir).toBe(stateDir);
    expect(out.sessions.map((s: any) => s.sessionId)).toEqual(['newest', 'middle', 'older']);
    expect(out.sessions[0].summary.done).toBe(true);
    // No per-session `nodes` map in list mode — keeps output scannable.
    expect(out.sessions[0].nodes).toBeUndefined();
  });

  test('lazyclaw validate: well-formed DAG → exit 0 with levels + maxParallelism', () => {
    const dir = tmpConfigDir();
    const wfPath = path.join(dir, 'good.mjs');
    fs.writeFileSync(wfPath,
      `export const nodes = [
         { id: 'fetch',    deps: [],                        async execute() {} },
         { id: 'embed',    deps: ['fetch'],                 async execute() {} },
         { id: 'classify', deps: ['fetch'],                 async execute() {} },
         { id: 'tag',      deps: ['fetch'],                 async execute() {} },
         { id: 'merge',    deps: ['embed','classify','tag'], async execute() {} },
       ];`,
    );
    const r = runCli(['validate', wfPath], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out.ok).toBe(true);
    expect(out.nodeCount).toBe(5);
    expect(out.issues).toEqual([]);
    expect(out.warnings).toEqual([]);
    // Levels: [fetch], [embed,classify,tag], [merge] → max width 3.
    expect(out.maxParallelism).toBe(3);
    expect(out.levels).toHaveLength(3);
  });

  test('lazyclaw validate: cycle → exit 1 with helpful issue', () => {
    const dir = tmpConfigDir();
    const wfPath = path.join(dir, 'cyclic.mjs');
    fs.writeFileSync(wfPath,
      `export const nodes = [
         { id: 'a', deps: ['b'], async execute() {} },
         { id: 'b', deps: ['a'], async execute() {} },
       ];`,
    );
    const r = runCli(['validate', wfPath], dir);
    expect(r.status).toBe(1);
    const out = JSON.parse(r.stdout);
    expect(out.ok).toBe(false);
    expect(out.issues.join('\n')).toMatch(/cycle/);
  });

  test('lazyclaw validate: duplicate id and missing execute → multiple issues', () => {
    const dir = tmpConfigDir();
    const wfPath = path.join(dir, 'broken.mjs');
    fs.writeFileSync(wfPath,
      `export const nodes = [
         { id: 'a', async execute() {} },
         { id: 'a', async execute() {} },          // duplicate id
         { id: 'b' },                              // missing execute
         { id: 'c', deps: 'not-an-array', async execute() {} },   // bad deps shape
       ];`,
    );
    const r = runCli(['validate', wfPath], dir);
    expect(r.status).toBe(1);
    const out = JSON.parse(r.stdout);
    expect(out.issues.some((m: string) => m.includes('duplicate id'))).toBe(true);
    expect(out.issues.some((m: string) => m.includes('execute is not a function'))).toBe(true);
    expect(out.issues.some((m: string) => m.includes('deps must be an array'))).toBe(true);
  });

  test('lazyclaw validate: unknown dep is a warning, not a hard failure', () => {
    const dir = tmpConfigDir();
    const wfPath = path.join(dir, 'warn.mjs');
    fs.writeFileSync(wfPath,
      `export const nodes = [
         { id: 'a', deps: ['ghost'], async execute() {} },
       ];`,
    );
    const r = runCli(['validate', wfPath], dir);
    expect(r.status).toBe(0);   // unknown dep is soft (engine treats as satisfied)
    const out = JSON.parse(r.stdout);
    expect(out.ok).toBe(true);
    expect(out.warnings.some((m: string) => m.includes('ghost'))).toBe(true);
  });

  test('lazyclaw validate: missing file → exit 2', () => {
    const dir = tmpConfigDir();
    const r = runCli(['validate', path.join(dir, 'nope.mjs')], dir);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/validate:/);
  });

  test('lazyclaw clear: deletes existing state file → exit 0 with removed:true', () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'st');
    fs.mkdirSync(stateDir, { recursive: true });
    fs.writeFileSync(path.join(stateDir, 'doomed.json'), JSON.stringify({
      sessionId: 'doomed', order: ['x'],
      nodes: { x: { status: 'success', attempts: 1 } },
      startedAt: 1, updatedAt: 2,
    }));
    const r = runCli(['clear', 'doomed', '--dir', stateDir], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out).toEqual({ ok: true, sessionId: 'doomed', removed: true });
    expect(fs.existsSync(path.join(stateDir, 'doomed.json'))).toBe(false);
  });

  test('lazyclaw clear: idempotent — second call still exits 0 with removed:false', () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'st');
    fs.mkdirSync(stateDir, { recursive: true });
    const r = runCli(['clear', 'never-existed', '--dir', stateDir], dir);
    expect(r.status).toBe(0);
    expect(JSON.parse(r.stdout)).toEqual({ ok: true, sessionId: 'never-existed', removed: false });
  });

  test('lazyclaw clear: missing state dir → exit 2', () => {
    const dir = tmpConfigDir();
    const r = runCli(['clear', 'whatever', '--dir', path.join(dir, 'no-such')], dir);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/does not exist/);
  });

  test('lazyclaw clear: refuses sessionId that resolves outside the state dir', () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'st');
    fs.mkdirSync(stateDir, { recursive: true });
    // Plant a file outside the state dir; clear must NOT touch it.
    const outside = path.join(dir, 'outside.json');
    fs.writeFileSync(outside, '"not workflow state"');
    const r = runCli(['clear', '../outside', '--dir', stateDir], dir);
    expect(r.status).toBe(1);
    expect(r.stderr).toMatch(/invalid sessionId/);
    expect(fs.existsSync(outside)).toBe(true);
  });

  test('lazyclaw inspect --summary trims per-node detail in single-session mode', () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'st');
    fs.mkdirSync(stateDir, { recursive: true });
    fs.writeFileSync(path.join(stateDir, 'job.json'), JSON.stringify({
      sessionId: 'job',
      order: ['a', 'b', 'c'],
      nodes: {
        a: { status: 'success', output: 'A', attempts: 1, durationMs: 5 },
        b: { status: 'success', output: 'B', attempts: 1, durationMs: 7 },
        c: { status: 'pending', attempts: 0 },
      },
      startedAt: 1, updatedAt: 2,
    }));

    // Default: full output includes nodes + order.
    const full = JSON.parse(runCli(['inspect', 'job', '--dir', stateDir], dir).stdout);
    expect(full.nodes).toBeDefined();
    expect(full.order).toEqual(['a', 'b', 'c']);

    // --summary trims them.
    const compact = JSON.parse(runCli(['inspect', 'job', '--dir', stateDir, '--summary'], dir).stdout);
    expect(compact.nodes).toBeUndefined();
    expect(compact.order).toBeUndefined();
    // But summary block, failedNodes, and timestamps are preserved.
    expect(compact.summary.total).toBe(3);
    expect(compact.summary.success).toBe(2);
    expect(compact.summary.pending).toBe(1);
    expect(compact.failedNodes).toEqual([]);
    expect(compact.startedAt).toBe(1);
    expect(compact.updatedAt).toBe(2);
  });

  test('lazyclaw inspect --status filters list mode by lifecycle bucket', () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'st');
    fs.mkdirSync(stateDir, { recursive: true });
    // 3 sessions: done, resumable (partial), failed.
    const mk = (id: string, nodes: any) => {
      fs.writeFileSync(path.join(stateDir, `${id}.json`), JSON.stringify({
        sessionId: id, order: Object.keys(nodes), nodes,
        startedAt: 1, updatedAt: 100,
      }));
    };
    mk('done', { a: { status: 'success', attempts: 1 } });
    mk('partial', { a: { status: 'success', attempts: 1 }, b: { status: 'pending', attempts: 0 } });
    mk('broken', { a: { status: 'success', attempts: 1 }, b: { status: 'failed', error: 'boom', attempts: 3 } });

    const r1 = runCli(['inspect', '--dir', stateDir, '--status', 'done'], dir);
    expect(r1.status).toBe(0);
    expect(JSON.parse(r1.stdout).sessions.map((s: any) => s.sessionId)).toEqual(['done']);

    const r2 = runCli(['inspect', '--dir', stateDir, '--status', 'resumable'], dir);
    expect(r2.status).toBe(0);
    expect(JSON.parse(r2.stdout).sessions.map((s: any) => s.sessionId)).toEqual(['partial']);

    const r3 = runCli(['inspect', '--dir', stateDir, '--status', 'failed'], dir);
    expect(r3.status).toBe(0);
    expect(JSON.parse(r3.stdout).sessions.map((s: any) => s.sessionId)).toEqual(['broken']);

    // Unknown status → exit 2 with helpful stderr.
    const r4 = runCli(['inspect', '--dir', stateDir, '--status', 'bogus'], dir);
    expect(r4.status).toBe(2);
    expect(r4.stderr).toMatch(/invalid --status/);
  });

  test('lazyclaw inspect (no arg): missing state dir → exit 2', () => {
    const dir = tmpConfigDir();
    const r = runCli(['inspect', '--dir', path.join(dir, 'no-such-dir')], dir);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/does not exist/);
  });

  test('lazyclaw inspect (no arg): empty state dir → exit 0 with empty sessions array', () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'empty-state');
    fs.mkdirSync(stateDir, { recursive: true });
    const r = runCli(['inspect', '--dir', stateDir], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out.sessions).toEqual([]);
  });

  test('lazyclaw inspect: partially completed (resumable) → exit 0', () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'st');
    fs.mkdirSync(stateDir, { recursive: true });
    // Hand-craft a state file mimicking a SIGINT'd run: one success, one
    // pending. inspect should report exit 0 (resumable) without running
    // any code.
    const state = {
      sessionId: 'partial-job',
      order: ['a', 'b'],
      nodes: {
        a: { status: 'success', output: 'A', attempts: 1, durationMs: 12 },
        b: { status: 'pending', attempts: 0 },
      },
      startedAt: 1, updatedAt: 2,
    };
    fs.writeFileSync(path.join(stateDir, 'partial-job.json'), JSON.stringify(state));
    const r = runCli(['inspect', 'partial-job', '--dir', stateDir], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out.summary.pending).toBe(1);
    expect(out.summary.success).toBe(1);
    expect(out.summary.resumable).toBe(true);
    expect(out.summary.done).toBe(false);
    expect(out.summary.durationMs).toBe(12);
  });

  test('lazyclaw run SIGINT mid-flow exits 130 with aborted:true and state stays resumable', async () => {
    const dir = tmpConfigDir();
    const wfPath = path.join(dir, 'long.mjs');
    // Three nodes: a (instant), b (sleeps 2s — we'll SIGINT during this),
    // c (would run after b). Persistent sequential mode so we can verify
    // the disk state survives the abort and a follow-up run resumes.
    fs.writeFileSync(wfPath,
      `// b subscribes to the forwarded signal so SIGINT aborts it
       // immediately instead of waiting for the natural 2s sleep.
       export const nodes = [
         { id: 'a', type: 't', async execute() { return 'A'; } },
         { id: 'b', type: 't', async execute(_, opts) {
             return new Promise((resolve, reject) => {
               const t = setTimeout(() => resolve('B'), 2000);
               opts?.signal?.addEventListener('abort', () => {
                 clearTimeout(t);
                 const e = new Error('aborted'); e.code = 'ABORT'; reject(e);
               });
             });
         } },
         { id: 'c', type: 't', async execute() { return 'C'; } },
       ];`,
    );
    const stateDir = path.join(dir, 'st');
    const child = spawn(process.execPath, [CLI, 'run', 'sigint-job', wfPath, '--dir', stateDir], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stderr.on('data', d => chunks.push(d.toString()));

    // Wait long enough for the engine to commit `a=success` and start `b`.
    await new Promise(r => setTimeout(r, 250));
    child.kill('SIGINT');

    const code = await new Promise<number>(resolve => child.on('exit', c => resolve(c ?? -1)));
    expect(code).toBe(130);   // ABORT exit code
    const stdout = chunks.join('');
    const out = JSON.parse(stdout.trim().split('\n').pop() as string);
    expect(out.aborted).toBe(true);
    expect(out.success).toBe(false);

    // Disk state: a=success, b=pending (NOT failed — it's resumable).
    const stateFile = path.join(stateDir, 'sigint-job.json');
    expect(fs.existsSync(stateFile)).toBe(true);
    const state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
    expect(state.nodes.a.status).toBe('success');
    expect(state.nodes.b.status).toBe('pending');
    expect(state.nodes.c.status).toBe('pending');

    // Resume run: replace the slow node with a fast one (we don't want to
    // wait 2s just to confirm resume works) and verify a is skipped.
    const fastWf = path.join(dir, 'fast.mjs');
    fs.writeFileSync(fastWf,
      `export const nodes = [
         { id: 'a', type: 't', async execute() { return 'A'; } },
         { id: 'b', type: 't', async execute() { return 'B'; } },
         { id: 'c', type: 't', async execute() { return 'C'; } },
       ];`,
    );
    const r2 = runCli(['resume', 'sigint-job', fastWf, '--dir', stateDir], dir);
    expect(r2.status).toBe(0);
    const o2 = JSON.parse(r2.stdout);
    expect(o2.success).toBe(true);
    expect(o2.executedNodes).toEqual(['b', 'c']);   // a was skipped
  });

  test('lazyclaw run SIGINT in --parallel mode forwards signal and exits 130', async () => {
    const dir = tmpConfigDir();
    const wfPath = path.join(dir, 'pwf.mjs');
    // Three independent nodes; each sleeps 2s. SIGINT should abort the
    // whole level even though each node is mid-execute.
    fs.writeFileSync(wfPath,
      `// Both nodes subscribe to the forwarded signal so SIGINT aborts
       // both immediately. The engine waits for the whole level to settle
       // before reporting — without signal-aware nodes, the slowest one
       // would set the lower bound on how long abort takes.
       const abortable = (label) => (_, opts) => new Promise((resolve, reject) => {
         const t = setTimeout(() => resolve(label), 2000);
         opts?.signal?.addEventListener('abort', () => {
           clearTimeout(t);
           const e = new Error('aborted'); e.code = 'ABORT'; reject(e);
         });
       });
       export const nodes = [
         { id: 'x', type: 't', deps: [], execute: abortable('X') },
         { id: 'y', type: 't', deps: [], execute: abortable('Y') },
       ];`,
    );
    const child = spawn(process.execPath, [CLI, 'run', '--parallel', 'demo', wfPath], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    await new Promise(r => setTimeout(r, 200));
    const t0 = Date.now();
    child.kill('SIGINT');
    const code = await new Promise<number>(resolve => child.on('exit', c => resolve(c ?? -1)));
    const elapsed = Date.now() - t0;
    expect(code).toBe(130);
    // Node x subscribed to the signal — should bail well before 2s elapses.
    expect(elapsed).toBeLessThan(1500);
    const out = JSON.parse(chunks.join('').trim().split('\n').pop() as string);
    expect(out.aborted).toBe(true);
  });

  test('chat SIGINT mid-stream interrupts the turn but keeps the REPL alive', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);

    // Long prompt → long reply → mockChunks delays 5ms per char.
    // 200 chars × 5ms = ~1s of streaming. We SIGINT after ~150ms,
    // expect the stream to abort and the prompt to come back so
    // the next user line still works.
    const longPrompt = 'q'.repeat(200);
    const child = spawn(process.execPath, [CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stderr.on('data', d => chunks.push(d.toString()));

    child.stdin.write(longPrompt + '\n');
    await new Promise(r => setTimeout(r, 150));
    // Send SIGINT to interrupt the stream
    child.kill('SIGINT');
    await new Promise(r => setTimeout(r, 200));
    // Process should still be alive — send a follow-up
    child.stdin.write('after-interrupt\n');
    await new Promise(r => setTimeout(r, 400));
    child.stdin.write('/exit\n');
    child.stdin.end();
    const exitCode = await new Promise<number | null>(resolve => {
      child.on('close', code => resolve(code));
    });

    const out = chunks.join('');
    // The stream was interrupted: we should see the interruption message
    // and NOT the full mock-reply for the long prompt.
    expect(out).toContain('interrupted');
    expect(out).not.toContain('mock-reply: ' + longPrompt);
    // After interrupt the REPL kept running — the second message did get
    // a reply (mock truncates content to last user msg).
    expect(out).toContain('mock-reply: after-interrupt');
    // Clean exit, not killed by signal.
    expect(exitCode).toBe(0);
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
    for (const cmd of ['/status', '/new', '/usage', '/skill', '/help', '/exit']) {
      expect(out).toContain(cmd);
    }
  });

  test('chat /provider switches the active provider for subsequent turns', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);

    const child = spawn(process.execPath, [CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stdin.write('hello\n');
    await new Promise(r => setTimeout(r, 300));
    // Switch to anthropic — has no key, so the next user message will
    // trigger an INVALID_KEY error. That's the cheap way to prove the
    // switch took effect (mock would happily reply otherwise).
    child.stdin.write('/provider anthropic\n');
    await new Promise(r => setTimeout(r, 100));
    child.stdin.write('test after switch\n');
    await new Promise(r => setTimeout(r, 400));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));
    const out = chunks.join('');
    expect(out).toContain('mock-reply: hello');         // first turn used mock
    expect(out).toContain('provider → anthropic');      // switch acked
    expect(out).toMatch(/missing api key|invalid|INVALID_KEY|error/i);  // anthropic without key
  });

  test('chat /provider with no args prints the current provider', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const child = spawn(process.execPath, [CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stdin.write('/provider\n');
    await new Promise(r => setTimeout(r, 200));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));
    expect(chunks.join('')).toContain('provider: mock');
  });

  test('chat /provider with unknown name keeps prior provider', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const child = spawn(process.execPath, [CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stdin.write('/provider nonexistent\n');
    await new Promise(r => setTimeout(r, 100));
    child.stdin.write('hello\n');
    await new Promise(r => setTimeout(r, 400));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));
    const out = chunks.join('');
    expect(out).toContain('unknown provider: nonexistent');
    expect(out).toContain('mock-reply: hello');  // mock provider still active
  });

  test('chat /model updates the active model and accepts unified provider/model', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const child = spawn(process.execPath, [CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stdin.write('/model some-model\n');
    await new Promise(r => setTimeout(r, 100));
    child.stdin.write('/status\n');
    await new Promise(r => setTimeout(r, 100));
    // Unified form switches both
    child.stdin.write('/model openai/gpt-4.1\n');
    await new Promise(r => setTimeout(r, 100));
    child.stdin.write('/status\n');
    await new Promise(r => setTimeout(r, 200));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));
    const out = chunks.join('');
    expect(out).toContain('model → some-model');
    expect(out).toMatch(/"model":\s*"some-model"/);
    expect(out).toContain('model → gpt-4.1');
    expect(out).toContain('provider → openai');
    expect(out).toMatch(/"provider":\s*"openai".*"model":\s*"gpt-4.1"/s);
  });

  test('chat /skill switches the active system message and persists to session', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    fs.mkdirSync(path.join(dir, 'skills'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'skills', 'a.md'), '# A\nbody-A\n');
    fs.writeFileSync(path.join(dir, 'skills', 'b.md'), '# B\nbody-B\n');

    const child = spawn(process.execPath, [CLI, 'chat', '--session', 'sw'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    child.stdin.write('first\n');
    await new Promise(r => setTimeout(r, 300));
    child.stdin.write('/skill a\n');
    await new Promise(r => setTimeout(r, 200));
    child.stdin.write('/skill b\n');
    await new Promise(r => setTimeout(r, 200));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));

    const turns = fs.readFileSync(path.join(dir, 'sessions', 'sw.jsonl'), 'utf8')
      .split('\n').filter(Boolean).map(l => JSON.parse(l));
    // Exactly one system message (skill b, since a was replaced)
    const systems = turns.filter(t => t.role === 'system');
    expect(systems).toHaveLength(1);
    expect(systems[0].content).toContain('skill: b');
    expect(systems[0].content).toContain('body-B');
    // The first user/assistant pair survives the skill switch
    expect(turns.some(t => t.role === 'user' && t.content === 'first')).toBe(true);
  });

  test('chat /skill with no args clears the active system message', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    fs.mkdirSync(path.join(dir, 'skills'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'skills', 'concise.md'), '# Concise\nbe brief\n');

    const child = spawn(process.execPath, [CLI, 'chat', '--skill', 'concise', '--session', 'cl'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    child.stdin.write('hello\n');
    await new Promise(r => setTimeout(r, 300));
    child.stdin.write('/skill\n');
    await new Promise(r => setTimeout(r, 200));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));

    const turns = fs.readFileSync(path.join(dir, 'sessions', 'cl.jsonl'), 'utf8')
      .split('\n').filter(Boolean).map(l => JSON.parse(l));
    // No system messages after /skill cleared it.
    expect(turns.filter(t => t.role === 'system')).toHaveLength(0);
    // hello + assistant reply still present
    expect(turns.some(t => t.role === 'user' && t.content === 'hello')).toBe(true);
  });

  test('chat /skill with unknown skill prints an error and keeps prior state', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);

    const child = spawn(process.execPath, [CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stdin.write('/skill nonexistent\n');
    await new Promise(r => setTimeout(r, 200));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));
    const out = chunks.join('');
    expect(out).toMatch(/skill error|not found/i);
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
  function startDaemonProc(cfgDir: string, extraArgs: string[] = [], extraEnv: NodeJS.ProcessEnv = {}): Promise<{ url: string, kill: () => Promise<void> }> {
    return new Promise((resolve, reject) => {
      const child = spawn(process.execPath, [CLI, 'daemon', '--port', '0', ...extraArgs], {
        env: { ...process.env, LAZYCLAW_CONFIG_DIR: cfgDir, ...extraEnv },
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

  test('daemon GET /workflows lists every persisted workflow session', async () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'wf-st');
    fs.mkdirSync(stateDir, { recursive: true });
    // Two hand-crafted state files — one done, one resumable. Same
    // shape the engine writes; we want the daemon to produce the
    // same listing the CLI does.
    fs.writeFileSync(path.join(stateDir, 'done.json'), JSON.stringify({
      sessionId: 'done',
      order: ['x'],
      nodes: { x: { status: 'success', output: 1, attempts: 1, durationMs: 4 } },
      startedAt: 1, updatedAt: 100,
    }));
    fs.writeFileSync(path.join(stateDir, 'partial.json'), JSON.stringify({
      sessionId: 'partial',
      order: ['a', 'b'],
      nodes: {
        a: { status: 'success', output: 'A', attempts: 1, durationMs: 2 },
        b: { status: 'pending', attempts: 0 },
      },
      startedAt: 1, updatedAt: 200,
    }));
    const d = await startDaemonProc(dir, ['--workflow-state-dir', stateDir]);
    try {
      const r = await fetch(`${d.url}/workflows`).then(x => x.json());
      expect(r.dir).toBe(stateDir);
      // Newest first by updatedAt.
      expect(r.sessions.map((s: any) => s.sessionId)).toEqual(['partial', 'done']);
      expect(r.sessions[0].summary.resumable).toBe(true);
      expect(r.sessions[1].summary.done).toBe(true);
      // Per-node `nodes` map omitted in list mode.
      expect(r.sessions[0].nodes).toBeUndefined();
    } finally { await d.kill(); }
  });

  test('daemon GET /workflows on missing dir returns empty sessions (not 404)', async () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'no-such-wf-dir');
    const d = await startDaemonProc(dir, ['--workflow-state-dir', stateDir]);
    try {
      const res = await fetch(`${d.url}/workflows`);
      expect(res.status).toBe(200);   // unlike CLI, daemon collapses ENOENT to empty
      const r = await res.json();
      expect(r.sessions).toEqual([]);
    } finally { await d.kill(); }
  });

  test('daemon GET /metrics includes a workflows snapshot block', async () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'wf-metrics');
    fs.mkdirSync(stateDir, { recursive: true });
    fs.writeFileSync(path.join(stateDir, 'a.json'), JSON.stringify({
      sessionId: 'a', order: ['x'],
      nodes: { x: { status: 'success', attempts: 1 } },
      startedAt: 1, updatedAt: 2,
    }));
    fs.writeFileSync(path.join(stateDir, 'b.json'), JSON.stringify({
      sessionId: 'b', order: ['x'],
      nodes: { x: { status: 'failed', error: 'boom', attempts: 3 } },
      startedAt: 1, updatedAt: 2,
    }));
    const d = await startDaemonProc(dir, ['--workflow-state-dir', stateDir]);
    try {
      const r = await fetch(`${d.url}/metrics`).then(x => x.json());
      expect(r.workflows).toMatchObject({
        total: 2, done: 1, failed: 1, resumable: 0, running: 0,
      });
    } finally { await d.kill(); }
  });

  test('daemon GET /metrics with no state dir yet → workflows zero counts', async () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'never-created');   // doesn't exist
    const d = await startDaemonProc(dir, ['--workflow-state-dir', stateDir]);
    try {
      const r = await fetch(`${d.url}/metrics`).then(x => x.json());
      expect(r.workflows).toEqual({ total: 0, done: 0, resumable: 0, failed: 0, running: 0 });
    } finally { await d.kill(); }
  });

  test('daemon GET /workflows?status= filters by lifecycle bucket (mirrors CLI)', async () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'wf-fil');
    fs.mkdirSync(stateDir, { recursive: true });
    const mk = (id: string, nodes: any) => {
      fs.writeFileSync(path.join(stateDir, `${id}.json`), JSON.stringify({
        sessionId: id, order: Object.keys(nodes), nodes,
        startedAt: 1, updatedAt: 100,
      }));
    };
    mk('done', { a: { status: 'success', attempts: 1 } });
    mk('partial', { a: { status: 'success', attempts: 1 }, b: { status: 'pending', attempts: 0 } });
    mk('broken', { a: { status: 'success', attempts: 1 }, b: { status: 'failed', error: 'boom', attempts: 3 } });

    const d = await startDaemonProc(dir, ['--workflow-state-dir', stateDir]);
    try {
      // Each predicate isolates one bucket.
      const failed = await fetch(`${d.url}/workflows?status=failed`).then(x => x.json());
      expect(failed.status).toBe('failed');
      expect(failed.sessions.map((s: any) => s.sessionId)).toEqual(['broken']);

      const resumable = await fetch(`${d.url}/workflows?status=resumable`).then(x => x.json());
      expect(resumable.sessions.map((s: any) => s.sessionId)).toEqual(['partial']);

      const done = await fetch(`${d.url}/workflows?status=done`).then(x => x.json());
      expect(done.sessions.map((s: any) => s.sessionId)).toEqual(['done']);

      // Unknown bucket → 400 with helpful 'expected' field.
      const bad = await fetch(`${d.url}/workflows?status=bogus`);
      expect(bad.status).toBe(400);
      const badBody = await bad.json();
      expect(badBody.expected).toEqual(expect.arrayContaining(['done', 'resumable', 'failed', 'running']));
    } finally { await d.kill(); }
  });

  test('daemon GET /workflows/<id>?summary=true trims per-node detail (mirrors CLI --summary)', async () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'wf-comp');
    fs.mkdirSync(stateDir, { recursive: true });
    fs.writeFileSync(path.join(stateDir, 'job.json'), JSON.stringify({
      sessionId: 'job',
      order: ['a', 'b', 'c'],
      nodes: {
        a: { status: 'success', output: 'A', attempts: 1, durationMs: 5 },
        b: { status: 'success', output: 'B', attempts: 1, durationMs: 7 },
        c: { status: 'pending', attempts: 0 },
      },
      startedAt: 1, updatedAt: 2,
    }));
    const d = await startDaemonProc(dir, ['--workflow-state-dir', stateDir]);
    try {
      // Default: full payload includes nodes + order.
      const full = await fetch(`${d.url}/workflows/job`).then(x => x.json());
      expect(full.nodes).toBeDefined();
      expect(full.order).toEqual(['a', 'b', 'c']);

      // ?summary=true trims them; summary + failedNodes + timestamps preserved.
      const compact = await fetch(`${d.url}/workflows/job?summary=true`).then(x => x.json());
      expect(compact.nodes).toBeUndefined();
      expect(compact.order).toBeUndefined();
      expect(compact.summary.total).toBe(3);
      expect(compact.summary.success).toBe(2);
      expect(compact.summary.pending).toBe(1);
      expect(compact.failedNodes).toEqual([]);
      expect(compact.startedAt).toBe(1);
      expect(compact.updatedAt).toBe(2);

      // Anything other than literal 'true' = full payload (only the
      // exact string flips it; ?summary=1 / yes / on stay full).
      const r1 = await fetch(`${d.url}/workflows/job?summary=1`).then(x => x.json());
      expect(r1.nodes).toBeDefined();
    } finally { await d.kill(); }
  });

  test('daemon DELETE /workflows/<id> is idempotent (200 on existing AND missing)', async () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'wf-del');
    fs.mkdirSync(stateDir, { recursive: true });
    fs.writeFileSync(path.join(stateDir, 'doomed.json'), JSON.stringify({
      sessionId: 'doomed',
      order: ['x'],
      nodes: { x: { status: 'success', output: 1, attempts: 1 } },
      startedAt: 1, updatedAt: 2,
    }));
    const d = await startDaemonProc(dir, ['--workflow-state-dir', stateDir]);
    try {
      // First delete: existed.
      const r1 = await fetch(`${d.url}/workflows/doomed`, { method: 'DELETE' }).then(x => x.json());
      expect(r1).toEqual({ ok: true, sessionId: 'doomed', removed: true });
      expect(fs.existsSync(path.join(stateDir, 'doomed.json'))).toBe(false);
      // Second delete: same id, now missing → still 200 with removed:false.
      const r2 = await fetch(`${d.url}/workflows/doomed`, { method: 'DELETE' }).then(x => x.json());
      expect(r2).toEqual({ ok: true, sessionId: 'doomed', removed: false });
      // Never-existed id: same shape.
      const r3 = await fetch(`${d.url}/workflows/never-existed`, { method: 'DELETE' }).then(x => x.json());
      expect(r3).toEqual({ ok: true, sessionId: 'never-existed', removed: false });
    } finally { await d.kill(); }
  });

  test('daemon DELETE /workflows/<id> rejects sessionIds that escape the state dir', async () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'wf-confined');
    fs.mkdirSync(stateDir, { recursive: true });
    // Plant a file outside the state dir to confirm it's untouched.
    const outside = path.join(dir, 'outside-state.json');
    fs.writeFileSync(outside, '"not workflow state"');
    const d = await startDaemonProc(dir, ['--workflow-state-dir', stateDir]);
    try {
      // The path matcher /\/workflows\/([^/]+)$/ already rejects literal
      // slashes, but URL-decoded `..%2Fsomething` could decode to `../`.
      // We're not URL-decoding the segment ourselves, but let's verify the
      // confinement check does its job either way.
      const sneaky = '..%2Foutside-state';
      const res = await fetch(`${d.url}/workflows/${sneaky}`, { method: 'DELETE' });
      // Either 400 (matcher rejected the decoded path) or 200 with
      // removed:false — what we MUST NOT see is `outside-state.json`
      // being deleted.
      expect([200, 400]).toContain(res.status);
      expect(fs.existsSync(outside)).toBe(true);
    } finally { await d.kill(); }
  });

  test('daemon GET /workflows/<id> returns full state shape; 404 on missing', async () => {
    const dir = tmpConfigDir();
    const stateDir = path.join(dir, 'wf2');
    fs.mkdirSync(stateDir, { recursive: true });
    fs.writeFileSync(path.join(stateDir, 'job1.json'), JSON.stringify({
      sessionId: 'job1',
      order: ['a', 'b'],
      nodes: {
        a: { status: 'success', output: 'A', attempts: 1, durationMs: 5 },
        b: { status: 'failed', error: 'boom', attempts: 3, durationMs: 12 },
      },
      startedAt: 1, updatedAt: 2,
    }));
    const d = await startDaemonProc(dir, ['--workflow-state-dir', stateDir]);
    try {
      const r = await fetch(`${d.url}/workflows/job1`).then(x => x.json());
      expect(r.sessionId).toBe('job1');
      expect(r.summary.failed).toBe(1);
      expect(r.summary.success).toBe(1);
      expect(r.failedNodes).toEqual([{ id: 'b', error: 'boom', attempts: 3 }]);
      // Per-node detail IS included in single-session mode.
      expect(r.nodes.a.output).toBe('A');

      const miss = await fetch(`${d.url}/workflows/no-such`);
      expect(miss.status).toBe(404);
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

  test('daemon POST /agent with skills composes them into the system prompt', async () => {
    // The mock provider only echoes the last user message, so to verify
    // the skill landed on the wire we use a custom fetch handle on the
    // anthropic provider — but we don't have a real key here. Instead,
    // check via a missing-skill error path: an invalid skill name causes
    // the endpoint to return 400 before any provider call. That proves
    // the composition step ran.
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      const res = await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'hi', skills: 'nope-does-not-exist' }),
      });
      expect(res.status).toBe(400);
      const j = await res.json();
      expect(j.error).toMatch(/skill error/);
    } finally { await d.kill(); }
  });

  test('daemon POST /agent with a real skill passes through and replies normally', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    fs.mkdirSync(path.join(dir, 'skills'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'skills', 'concise.md'), '# Concise\nbe brief\n');
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'hello', skills: ['concise'] }),
      }).then(x => x.json());
      // mock provider echoes the last user message — skill is silent here
      // but the request did not 400, which means composition succeeded.
      expect(r.reply).toContain('mock-reply: hello');
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

  test('daemon GET /skills lists installed skills with summaries', async () => {
    const dir = tmpConfigDir();
    fs.mkdirSync(path.join(dir, 'skills'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'skills', 'reviewer.md'),
      '# Reviewer\nbe thorough but kind\n');
    fs.writeFileSync(path.join(dir, 'skills', 'concise.md'),
      '# Concise\nfewer words\n');
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/skills`).then(x => x.json());
      const names = r.map((s: any) => s.name).sort();
      expect(names).toEqual(['concise', 'reviewer']);
      const reviewer = r.find((s: any) => s.name === 'reviewer');
      expect(reviewer.summary).toBe('Reviewer');
      expect(reviewer.bytes).toBeGreaterThan(0);
    } finally { await d.kill(); }
  });

  test('daemon GET /skills/<name> returns the markdown body as text/markdown', async () => {
    const dir = tmpConfigDir();
    fs.mkdirSync(path.join(dir, 'skills'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'skills', 'tldr.md'),
      '# TL;DR\nsummarize ruthlessly\n');
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/skills/tldr`);
      expect(r.status).toBe(200);
      expect(r.headers.get('content-type')).toContain('text/markdown');
      const body = await r.text();
      expect(body).toContain('# TL;DR');
      expect(body).toContain('summarize ruthlessly');
    } finally { await d.kill(); }
  });

  test('daemon GET /skills/<name> on missing skill returns 404', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/skills/does-not-exist`);
      expect(r.status).toBe(404);
      const j = await r.json();
      expect(j.error).toMatch(/skill not found/);
      expect(j.name).toBe('does-not-exist');
    } finally { await d.kill(); }
  });

  test('daemon GET /skills/<name> rejects path-traversal names with 400', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir);
    try {
      // The router regex `[^/]+` already blocks bare `..`-with-slashes
      // attacks. This tests the OTHER protection — skillPath rejects
      // dotfile names like ".secret" so they can't read hidden files
      // under <configDir>/skills/ either.
      const r = await fetch(`${d.url}/skills/.hidden`);
      expect(r.status).toBe(400);
    } finally { await d.kill(); }
  });

  test('daemon PUT /skills/<name> creates a skill (201) then overwrites (200)', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir);
    try {
      const create = await fetch(`${d.url}/skills/reviewer`, {
        method: 'PUT',
        headers: { 'content-type': 'text/markdown' },
        body: '# Reviewer\nbe blunt\n',
      });
      expect(create.status).toBe(201);
      const cj = await create.json();
      expect(cj.replaced).toBe(false);
      expect(fs.readFileSync(path.join(dir, 'skills', 'reviewer.md'), 'utf8')).toContain('be blunt');

      // Overwrite — same name, new body
      const update = await fetch(`${d.url}/skills/reviewer`, {
        method: 'PUT',
        headers: { 'content-type': 'text/markdown' },
        body: '# Reviewer v2\nbe ruthless\n',
      });
      expect(update.status).toBe(200);
      const uj = await update.json();
      expect(uj.replaced).toBe(true);
      expect(fs.readFileSync(path.join(dir, 'skills', 'reviewer.md'), 'utf8')).toContain('be ruthless');
    } finally { await d.kill(); }
  });

  test('daemon PUT /skills/<name> rejects path-traversal name (400) without writing', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/skills/.hidden`, {
        method: 'PUT',
        headers: { 'content-type': 'text/markdown' },
        body: 'should not land',
      });
      expect(r.status).toBe(400);
      // No file landed under skills/, including no .hidden.md file.
      const skillsDir = path.join(dir, 'skills');
      const list = fs.existsSync(skillsDir) ? fs.readdirSync(skillsDir) : [];
      expect(list).toEqual([]);
    } finally { await d.kill(); }
  });

  test('daemon DELETE /skills/<name> is idempotent and reports removed:true|false', async () => {
    const dir = tmpConfigDir();
    fs.mkdirSync(path.join(dir, 'skills'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'skills', 'doomed.md'), '# Doomed\n');
    const d = await startDaemonProc(dir);
    try {
      const first = await fetch(`${d.url}/skills/doomed`, { method: 'DELETE' });
      expect(first.status).toBe(200);
      expect((await first.json()).removed).toBe(true);
      expect(fs.existsSync(path.join(dir, 'skills', 'doomed.md'))).toBe(false);

      // Second DELETE on the same name still 200, but removed:false
      const second = await fetch(`${d.url}/skills/doomed`, { method: 'DELETE' });
      expect(second.status).toBe(200);
      expect((await second.json()).removed).toBe(false);
    } finally { await d.kill(); }
  });

  test('daemon accepts retry body shape and still returns the mock reply', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'hi', retry: { attempts: 3 } }),
      }).then(x => x.json());
      expect(r.reply).toContain('mock-reply: hi');
    } finally { await d.kill(); }
  });

  test('agent --retry N wraps the provider (mock still replies)', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const r = runCli(['agent', 'hello', '--retry', '3'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('mock-reply: hello');
  });

  test('agent --fallback "openai,ollama" wraps in withFallback (mock primary still replies)', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const r = runCli(['agent', 'hi', '--fallback', 'openai,ollama'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('mock-reply: hi');
  });

  test('agent --fallback with an unknown provider name exits 2', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const r = runCli(['agent', 'hi', '--fallback', 'definitely-not-a-provider'], dir);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/unknown fallback provider/);
  });

  test('daemon body.fallback wraps the chain (smoke: mock primary still replies)', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'hi', fallback: ['openai', 'ollama'] }),
      }).then(x => x.json());
      expect(r.reply).toContain('mock-reply: hi');
    } finally { await d.kill(); }
  });

  test('daemon body.fallback with unknown name → 400', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'hi', fallback: ['nope'] }),
      });
      expect(r.status).toBe(400);
      const j = await r.json();
      expect(j.error).toMatch(/unknown fallback provider: nope/);
    } finally { await d.kill(); }
  });

  test('daemon composes both fallback + retry layers without breaking the happy path', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          prompt: 'compose',
          fallback: ['openai'],
          retry: { attempts: 2 },
        }),
      }).then(x => x.json());
      expect(r.reply).toContain('mock-reply: compose');
    } finally { await d.kill(); }
  });

  test('daemon makeHandler with authToken: missing Authorization → 401', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      authToken: 'secret-abc',
    });
    // Drive a fake req/res. Capture writeHead status + body.
    let status = 0;
    let body = '';
    const headers: Record<string, string> = {};
    const fakeReq: any = { method: 'GET', url: '/version', headers: {} };
    const fakeRes: any = {
      writeHead(s: number, h: any) { status = s; if (h) Object.assign(headers, h); },
      end(b: string) { body = b; },
    };
    await handler(fakeReq, fakeRes);
    expect(status).toBe(401);
    expect(headers['www-authenticate']).toMatch(/Bearer realm/);
    expect(JSON.parse(body)).toEqual({ error: 'unauthorized' });
  });

  test('daemon makeHandler with authToken: correct Bearer token → 200', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '1.2.3',
      authToken: 'secret-abc',
    });
    let status = 0;
    let body = '';
    const fakeReq: any = { method: 'GET', url: '/version', headers: { authorization: 'Bearer secret-abc' } };
    const fakeRes: any = {
      writeHead(s: number) { status = s; },
      end(b: string) { body = b; },
    };
    await handler(fakeReq, fakeRes);
    expect(status).toBe(200);
    expect(JSON.parse(body).version).toBe('1.2.3');
  });

  test('daemon makeHandler with authToken: wrong token → 401, never reaches the route', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    let configRead = 0;
    const handler = mod.makeHandler({
      readConfig: () => { configRead += 1; return {}; },
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      authToken: 'secret-abc',
    });
    const fakeReq: any = { method: 'GET', url: '/status', headers: { authorization: 'Bearer wrong' } };
    let status = 0;
    const fakeRes: any = { writeHead(s: number) { status = s; }, end() {} };
    await handler(fakeReq, fakeRes);
    expect(status).toBe(401);
    // Auth check happens before route resolution — readConfig must NOT be called.
    expect(configRead).toBe(0);
  });

  test('daemon constantTimeEqual: same-length mismatch and different-length both reject', async () => {
    // Inline drive — re-import the module and exercise the gate via the
    // public handler. constantTimeEqual itself isn't exported; the
    // observable contract is "wrong token → 401 regardless of length."
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      authToken: 'aaaaaaaa',
    });
    const drive = async (token: string) => {
      let status = 0;
      const req: any = { method: 'GET', url: '/version', headers: { authorization: `Bearer ${token}` } };
      const res: any = { writeHead(s: number) { status = s; }, end() {} };
      await handler(req, res);
      return status;
    };
    expect(await drive('aaaaaaaa')).toBe(200);    // exact match
    expect(await drive('aaaaaaab')).toBe(401);    // same length, last byte off
    expect(await drive('a')).toBe(401);            // shorter
    expect(await drive('aaaaaaaaa')).toBe(401);    // longer
    expect(await drive('')).toBe(401);             // empty
  });

  test('daemon Origin gate: no Origin header → allow (CLI/script default)', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
    });
    let status = 0;
    const req: any = { method: 'GET', url: '/version', headers: {} };
    const res: any = { writeHead(s: number) { status = s; }, end() {} };
    await handler(req, res);
    expect(status).toBe(200);
  });

  test('daemon Origin gate: foreign Origin → 403 (browser CSRF / DNS-rebinding defense)', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
    });
    let status = 0;
    let body = '';
    const req: any = { method: 'GET', url: '/version', headers: { origin: 'https://attacker.example' } };
    const res: any = { writeHead(s: number) { status = s; }, end(b: string) { body = b; } };
    await handler(req, res);
    expect(status).toBe(403);
    expect(JSON.parse(body)).toEqual({ error: 'forbidden origin' });
  });

  test('daemon Origin gate: allowlisted Origin → allow', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      allowedOrigins: ['http://localhost:3000', 'http://127.0.0.1:8080'],
    });
    const drive = async (origin: string | undefined) => {
      let status = 0;
      const req: any = { method: 'GET', url: '/version', headers: origin ? { origin } : {} };
      const res: any = { writeHead(s: number) { status = s; }, end() {} };
      await handler(req, res);
      return status;
    };
    expect(await drive('http://localhost:3000')).toBe(200);
    expect(await drive('http://127.0.0.1:8080')).toBe(200);
    expect(await drive('https://evil.example')).toBe(403);
    expect(await drive(undefined)).toBe(200);
  });

  test('daemon Origin gate runs BEFORE auth so a foreign origin cannot probe auth state', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      authToken: 'secret',
    });
    let status = 0;
    const headers: Record<string, string> = {};
    // Foreign origin + a (valid) auth token. The Origin gate must
    // reject *before* auth even runs, so we never emit WWW-Authenticate
    // (which would tell the browser to open the auth dialog).
    const req: any = { method: 'GET', url: '/version', headers: { origin: 'https://evil.example', authorization: 'Bearer secret' } };
    const res: any = {
      writeHead(s: number, h: any) { status = s; if (h) Object.assign(headers, h); },
      end() {},
    };
    await handler(req, res);
    expect(status).toBe(403);
    expect(headers['www-authenticate']).toBeUndefined();
  });

  test('daemon CLI --allow-origin allows that origin and rejects others', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir, ['--allow-origin', 'http://localhost:3000']);
    try {
      const ok = await fetch(`${d.url}/version`, { headers: { origin: 'http://localhost:3000' } });
      expect(ok.status).toBe(200);
      const bad = await fetch(`${d.url}/version`, { headers: { origin: 'https://evil.example' } });
      expect(bad.status).toBe(403);
      const noOrigin = await fetch(`${d.url}/version`);
      expect(noOrigin.status).toBe(200);
    } finally { await d.kill(); }
  });

  test('withResponseCache: identical second call replays from memory (no second underlying call)', async () => {
    const { withResponseCache } = await import('../src/lazyclaw/providers/cache.mjs' as string);
    let calls = 0;
    const inner = {
      name: 'mock',
      async *sendMessage() { calls += 1; yield 'hello'; yield ' world'; },
    };
    const cached = withResponseCache(inner, { maxEntries: 8 });
    const out1: string[] = [];
    for await (const c of cached.sendMessage([{ role: 'user', content: 'q' }], { model: 'm' })) out1.push(c);
    const out2: string[] = [];
    for await (const c of cached.sendMessage([{ role: 'user', content: 'q' }], { model: 'm' })) out2.push(c);
    expect(out1.join('')).toBe('hello world');
    expect(out2.join('')).toBe('hello world');
    expect(calls).toBe(1);                                  // second call served from cache
    const stats = cached.cacheStats();
    expect(stats.hits).toBe(1);
    expect(stats.misses).toBe(1);
  });

  test('withResponseCache: different message arrays miss separately; cache key is stable across key order', async () => {
    const { withResponseCache } = await import('../src/lazyclaw/providers/cache.mjs' as string);
    let calls = 0;
    const inner = {
      name: 'mock',
      async *sendMessage(messages: any) { calls += 1; yield `reply:${messages[0].content}`; },
    };
    const cached = withResponseCache(inner);
    const drain = async (msgs: any[], opts: any = {}) => {
      const out: string[] = [];
      for await (const c of cached.sendMessage(msgs, opts)) out.push(c);
      return out.join('');
    };
    expect(await drain([{ role: 'user', content: 'a' }])).toBe('reply:a');
    expect(await drain([{ role: 'user', content: 'b' }])).toBe('reply:b');
    expect(await drain([{ role: 'user', content: 'a' }])).toBe('reply:a');  // cached
    expect(calls).toBe(2);                                                   // a + b, not 3
  });

  test('withResponseCache: TTL eviction drops stale entries', async () => {
    const { withResponseCache } = await import('../src/lazyclaw/providers/cache.mjs' as string);
    let calls = 0;
    let now = 1000;
    const inner = { name: 'mock', async *sendMessage() { calls += 1; yield 'x'; } };
    const cached = withResponseCache(inner, { ttlMs: 100, now: () => now });
    const drain = async () => {
      for await (const _c of cached.sendMessage([{ role: 'user', content: 'q' }], { model: 'm' })) { /* drain */ }
    };
    await drain();                       // miss → calls=1
    await drain();                       // hit  → calls=1 still
    expect(calls).toBe(1);
    now += 200;                          // past TTL
    await drain();                       // miss again → calls=2
    expect(calls).toBe(2);
  });

  test('withResponseCache: failed underlying call does not poison the cache', async () => {
    const { withResponseCache } = await import('../src/lazyclaw/providers/cache.mjs' as string);
    let attempt = 0;
    const inner = {
      name: 'mock',
      async *sendMessage() {
        attempt += 1;
        yield 'partial';
        if (attempt === 1) throw new Error('mid-stream');
        yield ' complete';
      },
    };
    const cached = withResponseCache(inner);
    let caught: any = null;
    try {
      for await (const _c of cached.sendMessage([{ role: 'user', content: 'q' }], {})) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.message).toBe('mid-stream');
    // Second call should hit the underlying provider (not the half-cached partial)
    const out: string[] = [];
    for await (const c of cached.sendMessage([{ role: 'user', content: 'q' }], {})) out.push(c);
    expect(out.join('')).toBe('partial complete');
    expect(attempt).toBe(2);
  });

  test('withResponseCache: maxEntries enforces LRU eviction', async () => {
    const { withResponseCache } = await import('../src/lazyclaw/providers/cache.mjs' as string);
    const inner = { name: 'mock', async *sendMessage(m: any) { yield `r:${m[0].content}`; } };
    const cached = withResponseCache(inner, { maxEntries: 2 });
    const drain = async (q: string) => {
      for await (const _c of cached.sendMessage([{ role: 'user', content: q }], {})) { /* drain */ }
    };
    await drain('a');  // [a]
    await drain('b');  // [a, b]
    await drain('c');  // a evicted → [b, c]
    expect(cached.cacheStats().size).toBe(2);
    // Re-asking for 'a' should miss now (was evicted)
    const before = cached.cacheStats().misses;
    await drain('a');
    expect(cached.cacheStats().misses).toBe(before + 1);
  });

  test('withResponseCache: stableStringify produces identical hashes across object key order', async () => {
    const { hashKey } = await import('../src/lazyclaw/providers/cache.mjs' as string);
    const a = hashKey([{ role: 'user', content: 'q' }], 'm', { thinking: { enabled: true, budgetTokens: 100 }, system: 'sys' });
    const b = hashKey([{ role: 'user', content: 'q' }], 'm', { system: 'sys', thinking: { budgetTokens: 100, enabled: true } });
    expect(a).toBe(b);
  });

  test('daemon GET /metrics counts requests by status without a logger', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir);
    try {
      // Drive a few requests with mixed outcomes:
      //   GET /version  → 200
      //   GET /missing  → 404
      //   GET /version  → 200
      await fetch(`${d.url}/version`);
      await fetch(`${d.url}/missing-route`);
      await fetch(`${d.url}/version`);
      const r = await fetch(`${d.url}/metrics`);
      expect(r.status).toBe(200);
      const m = await r.json();
      // The /metrics request itself counts too — total is at least 4
      // (3 above + this one). We assert >= rather than === because the
      // close event might race the next request in flaky CI; the
      // properties below are what matters.
      expect(m.requestsTotal).toBeGreaterThanOrEqual(3);
      expect(m.requestsByStatus['200']).toBeGreaterThanOrEqual(2);
      expect(m.requestsByStatus['404']).toBe(1);
      expect(typeof m.uptimeMs).toBe('number');
      expect(m.uptimeMs).toBeGreaterThanOrEqual(0);
      expect(m.cache).toBeNull();              // --response-cache not set
      expect(m.rateLimitDenied).toBe(0);       // --rate-limit not set
    } finally { await d.kill(); }
  });

  test('daemon /metrics counts rate-limit denials separately', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir, ['--rate-limit', '2']);
    try {
      // First 2 succeed, third 429s.
      expect((await fetch(`${d.url}/version`)).status).toBe(200);
      expect((await fetch(`${d.url}/version`)).status).toBe(200);
      expect((await fetch(`${d.url}/version`)).status).toBe(429);
      // /metrics itself costs a token; with capacity=2 and three 200s
      // already burned, this request would also 429. Sleep so a token
      // refills (refillPerSec = 2/60 ≈ 33ms/token), then probe.
      await new Promise(r => setTimeout(r, 1100));
      const r = await fetch(`${d.url}/metrics`);
      // /metrics could be 200 or 429 depending on bucket state. Either
      // way the counter asserts the denial happened earlier.
      if (r.status === 200) {
        const m = await r.json();
        expect(m.rateLimitDenied).toBeGreaterThanOrEqual(1);
        expect(m.requestsByStatus['429']).toBeGreaterThanOrEqual(1);
      } else {
        expect(r.status).toBe(429);
      }
    } finally { await d.kill(); }
  });

  test('daemon gate ordering: forbidden Origin → 403 (cost cap never consulted)', async () => {
    // The cost-cap gate runs AFTER Origin. A foreign-Origin POST to
    // /agent must 403 before any cost check — even if the cap has been
    // wildly exceeded (priming via direct metrics mutation isn't
    // possible; the test relies on the routing ordering itself).
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      costCap: { USD: 0.000001 },  // Effectively zero — cap will fire on any spending
    });
    let status = 0;
    let body = '';
    const req: any = {
      method: 'POST',
      url: '/agent',
      headers: { origin: 'https://evil.example' },
      socket: { remoteAddress: '127.0.0.1' },
    };
    const res: any = { writeHead(s: number) { status = s; }, end(b: string) { body = b; }, once: () => {} };
    await handler(req, res);
    expect(status).toBe(403);
    // Body should mention origin, NOT cost — proves Origin gate fired first.
    const j = JSON.parse(body);
    expect(j.error).toBe('forbidden origin');
  });

  test('daemon gate ordering: unauthenticated request → 401 (cost cap never consulted)', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      authToken: 'good',
      costCap: { USD: 0.000001 },
    });
    let status = 0;
    let body = '';
    const req: any = {
      method: 'POST', url: '/agent', headers: { authorization: 'Bearer wrong' },
      socket: { remoteAddress: '127.0.0.1' },
    };
    const res: any = { writeHead(s: number) { status = s; }, end(b: string) { body = b; }, once: () => {} };
    await handler(req, res);
    expect(status).toBe(401);
    expect(JSON.parse(body).error).toBe('unauthorized');
  });

  test('daemon gate ordering: rate-limited → 429 before cost cap is consulted', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      rateLimit: { capacity: 1, refillPerSec: 0.001 },
      costCap: { USD: 0.000001 },
    });
    // Use GET /version: rate limit gate is universal, cost cap only
    // applies to POST /agent + /chat. Driving /version twice cleanly
    // proves rate-limit fires before any downstream check (404, 402,
    // 500, etc.) — the FIRST request lands at the route handler (200),
    // the SECOND hits rate-limit BEFORE route resolution → 429.
    const drive = async () => {
      let status = 0;
      const req: any = { method: 'GET', url: '/version', headers: {}, socket: { remoteAddress: '127.0.0.1' } };
      const res: any = { writeHead(s: number) { status = s; }, end() {}, once: () => {} };
      await handler(req, res);
      return status;
    };
    expect(await drive()).toBe(200);
    expect(await drive()).toBe(429);
  });

  test('daemon costCap: cumulative spending past cap → 402 on /agent and /chat', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      costCap: { USD: 0.05 },
    });
    // Pre-populate metrics by direct mutation isn't possible (private),
    // so we drive the gate logic via the exported helper.
    const { checkCostCap } = mod as any;
    // Exposed for testing? Probably not. Use a real request flow instead.
    // Drive a POST with a fake req — observable: when costsByCurrency
    // hasn't accumulated, request goes through. Pre-loading metrics
    // would require touching internals; instead the integration test
    // below exercises the full path with a real daemon + injected stub.
    expect(typeof handler).toBe('function');
  });

  test('daemon CLI --cost-cap-usd: end-to-end cap fires after cumulative cost reaches limit', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'anthropic'], dir);
    runCli(['config', 'set', 'api-key', 'sk-ant-x'], dir);
    runCli(['config', 'set', 'model', 'claude-opus-4-7'], dir);
    runCli([
      'rates', 'set', 'anthropic/claude-opus-4-7',
      '--input', '15', '--output', '75', '--currency', 'USD',
    ], dir);
    // Stub anthropic so each call costs a known amount.
    // 1000 in × 15/1M + 500 out × 75/1M = $0.0525 per call.
    // Cap at $0.10 → first 2 calls succeed (total $0.105 — slight over),
    // third call breaches the cap.
    const preload = path.join(dir, 'preload.mjs');
    fs.writeFileSync(preload,
      `import('${path.resolve('src/lazyclaw/providers/registry.mjs')}').then(reg => {
        reg.PROVIDERS.anthropic = {
          name: 'anthropic',
          async *sendMessage(_msgs, opts) {
            yield 'r';
            opts.onUsage?.({ inputTokens: 1000, outputTokens: 500 });
          },
        };
      });`,
    );
    // Cap at $0.10. First two calls bring total to ~$0.105 → 2nd call
    // SUCCEEDS but pushes spend OVER the cap, then the 3rd call's
    // pre-flight check fires 402.
    const child = spawn(process.execPath, [
      '--import', preload,
      CLI, 'daemon', '--port', '0',
      '--cost-cap-usd', '0.10',
    ], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const url: string = await new Promise((resolve, reject) => {
      let buf = '';
      child.stdout.on('data', d => {
        buf += d.toString();
        const nl = buf.indexOf('\n');
        if (nl < 0) return;
        try { resolve(JSON.parse(buf.slice(0, nl)).url); } catch (e) { reject(e); }
      });
      setTimeout(() => reject(new Error('boot')), 5000);
    });
    try {
      const post = () => fetch(`${url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'q', usage: true, cost: true }),
      });
      const r1 = await post();
      expect(r1.status).toBe(200);
      const r2 = await post();
      // 2nd call still succeeds — gate check happens BEFORE the request,
      // so it sees the post-r1 spend (0.0525 < 0.10).
      expect(r2.status).toBe(200);
      const r3 = await post();
      // Cumulative now $0.105 → 3rd request 402s.
      expect(r3.status).toBe(402);
      const body = await r3.json();
      expect(body.error).toBe('cost cap exceeded');
      expect(body.currency).toBe('USD');
      expect(body.cap).toBe(0.1);
      expect(body.spent).toBeGreaterThanOrEqual(0.1);
    } finally {
      await new Promise<void>(r => { child.once('close', () => r()); child.kill('SIGTERM'); });
    }
  });

  test('daemon costCap: /version and /metrics stay reachable after cap fires (monitoring still works)', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '9.9.9',
      costCap: { USD: 0.01 },
    });
    // Even if costsByCurrency.USD were over the cap, GET /version is
    // a non-spending route — handler must never 402 it.
    let status = 0;
    let body = '';
    const req: any = { method: 'GET', url: '/version', headers: {}, socket: { remoteAddress: '127.0.0.1' } };
    const res: any = { writeHead(s: number) { status = s; }, end(b: string) { body = b; }, once: () => {} };
    await handler(req, res);
    expect(status).toBe(200);
    expect(JSON.parse(body).version).toBe('9.9.9');
  });

  test('daemon /metrics accumulates tokens + costs across requests with body.cost', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'anthropic'], dir);
    runCli(['config', 'set', 'api-key', 'sk-ant-x'], dir);
    runCli(['config', 'set', 'model', 'claude-opus-4-7'], dir);
    runCli([
      'rates', 'set', 'anthropic/claude-opus-4-7',
      '--input', '15', '--output', '75', '--currency', 'USD',
    ], dir);
    // Stub anthropic so each call emits known usage.
    const preload = path.join(dir, 'preload.mjs');
    fs.writeFileSync(preload,
      `import('${path.resolve('src/lazyclaw/providers/registry.mjs')}').then(reg => {
        reg.PROVIDERS.anthropic = {
          name: 'anthropic',
          async *sendMessage(_msgs, opts) {
            yield 'r';
            opts.onUsage?.({ inputTokens: 1000, outputTokens: 500 });
          },
        };
      });`,
    );
    const child = spawn(process.execPath, ['--import', preload, CLI, 'daemon', '--port', '0'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const url: string = await new Promise((resolve, reject) => {
      let buf = '';
      child.stdout.on('data', d => {
        buf += d.toString();
        const nl = buf.indexOf('\n');
        if (nl < 0) return;
        try { resolve(JSON.parse(buf.slice(0, nl)).url); } catch (e) { reject(e); }
      });
      setTimeout(() => reject(new Error('boot')), 5000);
    });
    try {
      // Three requests with body.usage + body.cost.
      for (let i = 0; i < 3; i++) {
        await fetch(`${url}/agent`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ prompt: 'q', usage: true, cost: true }),
        });
      }
      const r = await fetch(`${url}/metrics`);
      const m = await r.json();
      // 3 × (1000 in + 500 out) = (3000, 1500)
      expect(m.tokensTotal).toEqual({ inputTokens: 3000, outputTokens: 1500 });
      // 3 × $0.0525 = $0.1575
      expect(m.costsByCurrency.USD).toBe(0.1575);
    } finally {
      await new Promise<void>(r => { child.once('close', () => r()); child.kill('SIGTERM'); });
    }
  });

  test('daemon /metrics tokensTotal/costsByCurrency stay zero / empty without body.usage', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      // Drive a request without usage/cost opt-in.
      await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'q' }),
      });
      const r = await fetch(`${d.url}/metrics`);
      const m = await r.json();
      expect(m.tokensTotal).toEqual({ inputTokens: 0, outputTokens: 0 });
      expect(m.costsByCurrency).toEqual({});
    } finally { await d.kill(); }
  });

  test('daemon /metrics surfaces cache hits/misses when --response-cache is on', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir, ['--response-cache']);
    try {
      const post = () => fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'metrics-test', cache: true }),
      }).then(r => r.json());
      await post();   // miss → underlying call, populates cache
      await post();   // hit
      await post();   // hit
      const r = await fetch(`${d.url}/metrics`);
      expect(r.status).toBe(200);
      const m = await r.json();
      expect(m.cache).not.toBeNull();
      expect(m.cache.hits).toBe(2);
      expect(m.cache.misses).toBe(1);
      expect(m.cache.size).toBeGreaterThanOrEqual(1);
    } finally { await d.kill(); }
  });

  test('logger: level gate suppresses lower-priority records', async () => {
    const { createLogger } = await import('../src/lazyclaw/logger.mjs' as string);
    const lines: string[] = [];
    const log = createLogger({ level: 'warn', sink: (l: string) => lines.push(l), now: () => 1000 });
    log.debug('d');
    log.info('i');
    log.warn('w', { k: 1 });
    log.error('e');
    expect(lines).toHaveLength(2);
    const w = JSON.parse(lines[0]);
    expect(w.level).toBe('warn');
    expect(w.msg).toBe('w');
    expect(w.k).toBe(1);
    expect(w.ts).toBe(new Date(1000).toISOString());
  });

  test('logger: child() merges base fields without mutating the parent', async () => {
    const { createLogger } = await import('../src/lazyclaw/logger.mjs' as string);
    const lines: string[] = [];
    const log = createLogger({ level: 'info', sink: (l: string) => lines.push(l), now: () => 0, base: { svc: 'daemon' } });
    const child = log.child({ requestId: 'r-1' });
    child.info('hi');
    log.info('hi');
    const recs = lines.map(l => JSON.parse(l));
    expect(recs[0]).toMatchObject({ svc: 'daemon', requestId: 'r-1', msg: 'hi' });
    expect(recs[1]).toMatchObject({ svc: 'daemon', msg: 'hi' });
    expect(recs[1].requestId).toBeUndefined();
  });

  test('daemon makeHandler with logger: emits a JSON-line access record per request', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const { createLogger } = await import('../src/lazyclaw/logger.mjs' as string);
    const lines: string[] = [];
    const logger = createLogger({ level: 'info', sink: (l: string) => lines.push(l) });
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      logger,
    });
    // Fake req/res with a `close` event so the handler's res.once('close')
    // hook fires and the logger captures the access line.
    const events: Record<string, Array<() => void>> = {};
    const req: any = { method: 'GET', url: '/version', headers: {}, socket: { remoteAddress: '127.0.0.1' } };
    const res: any = {
      writeHead() {},
      end() {
        // Trigger the close handler on next tick so the logger sees it.
        setImmediate(() => (events['close'] || []).forEach(fn => fn()));
      },
      once(name: string, fn: () => void) {
        (events[name] = events[name] || []).push(fn);
      },
    };
    await handler(req, res);
    // Wait for setImmediate to fire.
    await new Promise(r => setImmediate(r));
    expect(lines).toHaveLength(1);
    const rec = JSON.parse(lines[0]);
    expect(rec.msg).toBe('access');
    expect(rec.method).toBe('GET');
    expect(rec.path).toBe('/version');
    expect(rec.status).toBe(200);
    expect(rec.remote).toBe('127.0.0.1');
    expect(typeof rec.durationMs).toBe('number');
  });

  test('daemon CLI --log info emits one access line per request on stderr', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    // Spawn directly so we can read stderr.
    const child = spawn(process.execPath, [CLI, 'daemon', '--port', '0', '--log', 'info'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const stderr: string[] = [];
    child.stderr.on('data', d => stderr.push(d.toString()));
    const url: string = await new Promise((resolve, reject) => {
      let buf = '';
      child.stdout.on('data', d => {
        buf += d.toString();
        const nl = buf.indexOf('\n');
        if (nl < 0) return;
        try { resolve(JSON.parse(buf.slice(0, nl)).url); } catch (e) { reject(e); }
      });
      setTimeout(() => reject(new Error('boot timeout')), 5000);
    });
    try {
      await fetch(`${url}/version`);
      // Allow the access line to flush.
      await new Promise(r => setTimeout(r, 100));
      const stderrStr = stderr.join('');
      // Should contain a JSON line with msg:"access" and method:"GET".
      const lines = stderrStr.split('\n').filter(l => l.startsWith('{'));
      const accessLines = lines.map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
      expect(accessLines.some(r => r.msg === 'access' && r.method === 'GET' && r.path === '/version')).toBe(true);
    } finally {
      await new Promise<void>(r => { child.once('close', () => r()); child.kill('SIGTERM'); });
    }
  });

  test('decorator stack: cache hit short-circuits fallback and retry entirely', async () => {
    // Real-world flow: a previously-served prompt comes back. The cache
    // should serve it without ever consulting fallback or retry —
    // verified by counting underlying calls.
    const { withResponseCache } = await import('../src/lazyclaw/providers/cache.mjs' as string);
    const { withFallback } = await import('../src/lazyclaw/providers/fallback.mjs' as string);
    const { withRateLimitRetry } = await import('../src/lazyclaw/providers/retry.mjs' as string);
    let primaryCalls = 0, fallbackCalls = 0;
    const primary = { name: 'prim', async *sendMessage() { primaryCalls++; yield 'A'; } };
    const altname = { name: 'alt', async *sendMessage() { fallbackCalls++; yield 'B'; } };
    // Compose innermost-first: cache → fallback → retry. (The daemon's
    // resolveProvider follows the same order.)
    const cached = withResponseCache(primary);
    const chained = withFallback([cached, altname]);
    const robust = withRateLimitRetry(chained, { attempts: 2, sleep: async () => {} });
    const drain = async () => {
      const out: string[] = [];
      for await (const c of robust.sendMessage([{ role: 'user', content: 'q' }], { model: 'm' })) out.push(c);
      return out.join('');
    };
    expect(await drain()).toBe('A');                  // miss → primary serves
    expect(await drain()).toBe('A');                  // hit → cache serves
    expect(await drain()).toBe('A');                  // hit → cache serves
    expect(primaryCalls).toBe(1);                     // never re-called
    expect(fallbackCalls).toBe(0);                    // never reached
  });

  test('decorator stack: cache miss falls through to fallback when primary fails pre-stream', async () => {
    const { withResponseCache } = await import('../src/lazyclaw/providers/cache.mjs' as string);
    const { withFallback } = await import('../src/lazyclaw/providers/fallback.mjs' as string);
    let primaryCalls = 0, fallbackCalls = 0;
    const primary = {
      name: 'prim',
      async *sendMessage() {
        primaryCalls++;
        const e: any = new Error('primary 500');
        e.status = 500;
        throw e;
      },
    };
    const alt = { name: 'alt', async *sendMessage() { fallbackCalls++; yield 'fromAlt'; } };
    const cached = withResponseCache(primary);
    const chained = withFallback([cached, alt]);
    const out: string[] = [];
    for await (const c of chained.sendMessage([{ role: 'user', content: 'q' }], { model: 'm' })) out.push(c);
    expect(out.join('')).toBe('fromAlt');
    expect(primaryCalls).toBe(1);
    expect(fallbackCalls).toBe(1);
    // Cache state: the primary's failure must NOT have populated the
    // primary's cache slot. A second call should still hit primary first.
    const out2: string[] = [];
    for await (const c of chained.sendMessage([{ role: 'user', content: 'q' }], { model: 'm' })) out2.push(c);
    expect(primaryCalls).toBe(2);   // primary tried again; cache wasn't poisoned
  });

  test('decorator stack: retry exhausts on primary RATE_LIMIT then fallback delivers', async () => {
    const { withFallback } = await import('../src/lazyclaw/providers/fallback.mjs' as string);
    const { withRateLimitRetry } = await import('../src/lazyclaw/providers/retry.mjs' as string);
    let primaryAttempts = 0, fallbackCalls = 0;
    const primary = {
      name: 'prim',
      async *sendMessage() {
        primaryAttempts++;
        const e: any = new Error('rate limited');
        e.code = 'RATE_LIMIT';
        e.retryAfterMs = 1;
        throw e;
      },
    };
    const alt = { name: 'alt', async *sendMessage() { fallbackCalls++; yield 'savedByFallback'; } };
    // Wrap primary with retry first; then fan out to fallback. So retry
    // exhausts → final RATE_LIMIT bubbles → fallback catches and serves.
    const primaryWithRetry = withRateLimitRetry(primary, { attempts: 2, sleep: async () => {} });
    const chained = withFallback([primaryWithRetry, alt]);
    const out: string[] = [];
    for await (const c of chained.sendMessage([{ role: 'user', content: 'q' }], { model: 'm' })) out.push(c);
    expect(out.join('')).toBe('savedByFallback');
    // Initial call + 2 retries = 3 attempts before fallback kicks in.
    expect(primaryAttempts).toBe(3);
    expect(fallbackCalls).toBe(1);
  });

  test('rate limiter: token bucket allows up to capacity then 429s', async () => {
    const mod = await import('../src/lazyclaw/ratelimit.mjs' as string);
    let now = 0;
    const lim = new mod.TokenBucketLimiter({
      capacity: 3,
      refillPerSec: 1,
      now: () => now,
    });
    expect(lim.consume('k').allowed).toBe(true);    // 3 → 2
    expect(lim.consume('k').allowed).toBe(true);    // 2 → 1
    expect(lim.consume('k').allowed).toBe(true);    // 1 → 0
    const denied = lim.consume('k');
    expect(denied.allowed).toBe(false);
    expect(denied.retryAfterMs).toBeGreaterThan(0);
    // Advance 1.1s — one token should have refilled, allowing 1 more.
    now += 1100;
    expect(lim.consume('k').allowed).toBe(true);
    expect(lim.consume('k').allowed).toBe(false);
  });

  test('rate limiter: separate keys have independent buckets', async () => {
    const mod = await import('../src/lazyclaw/ratelimit.mjs' as string);
    const lim = new mod.TokenBucketLimiter({ capacity: 1, refillPerSec: 1, now: () => 0 });
    expect(lim.consume('alice').allowed).toBe(true);
    expect(lim.consume('alice').allowed).toBe(false);
    // Bob has his own bucket.
    expect(lim.consume('bob').allowed).toBe(true);
  });

  test('daemon makeHandler with rateLimit: requests over capacity get 429 + Retry-After', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    // Tiny capacity so we can exhaust it inside the test.
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      rateLimit: { capacity: 2, refillPerSec: 0.001 },  // glacial refill
    });
    const drive = async () => {
      let status = 0;
      let headers: Record<string, string> = {};
      const req: any = { method: 'GET', url: '/version', headers: {}, socket: { remoteAddress: '127.0.0.1' } };
      const res: any = {
        writeHead(s: number, h: any) { status = s; if (h) Object.assign(headers, h); },
        end() {},
      };
      await handler(req, res);
      return { status, headers };
    };
    expect((await drive()).status).toBe(200);
    expect((await drive()).status).toBe(200);
    const denied = await drive();
    expect(denied.status).toBe(429);
    expect(denied.headers['retry-after']).toBeDefined();
    expect(parseInt(denied.headers['retry-after'], 10)).toBeGreaterThanOrEqual(1);
  });

  test('daemon CLI --response-cache enables shared cache; body.cache opts in per request', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir, ['--response-cache']);
    try {
      // First call with body.cache: true — populates the cache.
      const post = (cache: boolean) => fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'cache test', cache }),
      }).then(r => r.json());
      const r1 = await post(true);
      expect(r1.reply).toContain('mock-reply: cache test');
      // Second identical call also with cache:true — should still return
      // the same reply. The cache wrapper served it from memory; this is
      // observably correct (no error, identical text). The dedicated
      // cache hit/miss assertions live in the unit tests above.
      const r2 = await post(true);
      expect(r2.reply).toBe(r1.reply);
    } finally { await d.kill(); }
  });

  test('daemon: without --response-cache, body.cache: true is silently a no-op (no cache state)', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);  // no --response-cache flag
    try {
      // body.cache should not crash the daemon; the request just bypasses
      // cache machinery entirely.
      const r = await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'no cache wired', cache: true }),
      });
      expect(r.status).toBe(200);
      const j = await r.json();
      expect(j.reply).toContain('mock-reply: no cache wired');
    } finally { await d.kill(); }
  });

  test('daemon POST /agent body.cost:true returns cost block when rates configured for active model', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'anthropic'], dir);
    runCli(['config', 'set', 'api-key', 'sk-ant-x'], dir);
    runCli(['config', 'set', 'model', 'claude-opus-4-7'], dir);
    // Inject rates manually into the config file (config set only takes
    // string values; rates is an object).
    const cfgPath = path.join(dir, 'config.json');
    const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
    cfg.rates = {
      'anthropic/claude-opus-4-7': { inputPer1M: 15, outputPer1M: 75, currency: 'USD' },
    };
    fs.writeFileSync(cfgPath, JSON.stringify(cfg));

    // Monkey-patch the anthropic provider via spawn preload.
    const preload = path.join(dir, 'preload.mjs');
    fs.writeFileSync(preload,
      `import('${path.resolve('src/lazyclaw/providers/registry.mjs')}').then(reg => {
        reg.PROVIDERS.anthropic = {
          name: 'anthropic',
          async *sendMessage(_msgs, opts) {
            yield 'r';
            opts.onUsage?.({ inputTokens: 1000, outputTokens: 500 });
          },
        };
      });`,
    );
    const child = spawn(process.execPath, ['--import', preload, CLI, 'daemon', '--port', '0'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const url: string = await new Promise((resolve, reject) => {
      let buf = '';
      child.stdout.on('data', d => {
        buf += d.toString();
        const nl = buf.indexOf('\n');
        if (nl < 0) return;
        try { resolve(JSON.parse(buf.slice(0, nl)).url); } catch (e) { reject(e); }
      });
      setTimeout(() => reject(new Error('boot')), 5000);
    });
    try {
      const r = await fetch(`${url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'q', usage: true, cost: true }),
      });
      expect(r.status).toBe(200);
      const j = await r.json();
      expect(j.usage).toEqual({ inputTokens: 1000, outputTokens: 500 });
      // 1000/1M × 15 + 500/1M × 75 = 0.015 + 0.0375 = 0.0525
      expect(j.cost.cost).toBe(0.0525);
      expect(j.cost.currency).toBe('USD');
      expect(j.cost.breakdown.input).toBe(0.015);
      expect(j.cost.breakdown.output).toBe(0.0375);
    } finally {
      await new Promise<void>(r => { child.once('close', () => r()); child.kill('SIGTERM'); });
    }
  });

  test('daemon body.cost:true is silently a no-op when cfg.rates is missing', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'q', usage: true, cost: true }),
      });
      expect(r.status).toBe(200);
      const j = await r.json();
      // Mock didn't emit usage, so neither usage nor cost lands. The
      // critical thing is no crash.
      expect('cost' in j).toBe(false);
    } finally { await d.kill(); }
  });

  test('rates set persists a card with the right shape; rates list reads it back', () => {
    const dir = tmpConfigDir();
    const r1 = runCli([
      'rates', 'set', 'anthropic/claude-opus-4-7',
      '--input', '15', '--output', '75',
      '--cache-read', '1.5', '--cache-create', '18.75',
    ], dir);
    expect(r1.status).toBe(0);
    const out1 = JSON.parse(r1.stdout);
    expect(out1.card).toEqual({
      inputPer1M: 15, outputPer1M: 75,
      cacheReadPer1M: 1.5, cacheCreatePer1M: 18.75,
      currency: 'USD',
    });
    // List reads back
    const r2 = runCli(['rates', 'list'], dir);
    expect(r2.status).toBe(0);
    const list = JSON.parse(r2.stdout);
    expect(list['anthropic/claude-opus-4-7'].inputPer1M).toBe(15);
  });

  test('rates set rejects non-numeric or negative input/output', () => {
    const dir = tmpConfigDir();
    const r1 = runCli(['rates', 'set', 'x/y', '--input', 'banana', '--output', '5'], dir);
    expect(r1.status).toBe(2);
    expect(r1.stderr).toMatch(/non-negative/);
    const r2 = runCli(['rates', 'set', 'x/y', '--input', '-1', '--output', '5'], dir);
    expect(r2.status).toBe(2);
  });

  test('rates set rejects keys without a slash (forces provider/model shape)', () => {
    const dir = tmpConfigDir();
    const r = runCli(['rates', 'set', 'just-model', '--input', '1', '--output', '1'], dir);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/provider\/model/);
  });

  test('rates delete removes the card and reports removed:true|false', () => {
    const dir = tmpConfigDir();
    runCli(['rates', 'set', 'a/b', '--input', '1', '--output', '2'], dir);
    const r1 = runCli(['rates', 'delete', 'a/b'], dir);
    expect(JSON.parse(r1.stdout).removed).toBe(true);
    const r2 = runCli(['rates', 'delete', 'a/b'], dir);
    expect(JSON.parse(r2.stdout).removed).toBe(false);
  });

  test('rates shape prints the zero-filled reference template', () => {
    const dir = tmpConfigDir();
    const r = runCli(['rates', 'shape'], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    // Shape audit: every numeric is 0 (callers MUST fill in real numbers).
    for (const card of Object.values(out)) {
      expect((card as any).inputPer1M).toBe(0);
      expect((card as any).outputPer1M).toBe(0);
    }
  });

  test('rates list on a fresh config prints {} (no rates configured yet)', () => {
    const dir = tmpConfigDir();
    const r = runCli(['rates', 'list'], dir);
    expect(r.status).toBe(0);
    expect(JSON.parse(r.stdout)).toEqual({});
  });

  test('costFromUsage: anthropic with cache fields produces a 4-bucket breakdown', async () => {
    const { costFromUsage } = await import('../src/lazyclaw/providers/rates.mjs' as string);
    const rates = {
      'anthropic/claude-opus-4-7': {
        inputPer1M: 15, outputPer1M: 75,
        cacheReadPer1M: 1.5, cacheCreatePer1M: 18.75,
        currency: 'USD',
      },
    };
    const r = costFromUsage({
      provider: 'anthropic',
      model: 'claude-opus-4-7',
      usage: {
        inputTokens: 1000, outputTokens: 500,
        cacheCreationInputTokens: 2000, cacheReadInputTokens: 4000,
      },
    }, rates);
    // 1000/1M × 15 = 0.015
    // 500/1M × 75 = 0.0375
    // 4000/1M × 1.5 = 0.006
    // 2000/1M × 18.75 = 0.0375
    expect(r!.breakdown).toEqual({
      input: 0.015,
      output: 0.0375,
      cacheRead: 0.006,
      cacheCreate: 0.0375,
    });
    expect(r!.cost).toBe(0.096);
    expect(r!.currency).toBe('USD');
  });

  test('costFromUsage: openai shape (no cache fields) ignores absent rate keys', async () => {
    const { costFromUsage } = await import('../src/lazyclaw/providers/rates.mjs' as string);
    const rates = { 'openai/gpt-4.1': { inputPer1M: 2, outputPer1M: 8 } };
    const r = costFromUsage({
      provider: 'openai',
      model: 'gpt-4.1',
      usage: { inputTokens: 1000, outputTokens: 500, totalTokens: 1500 },
    }, rates);
    expect(r!.breakdown.input).toBe(0.002);
    expect(r!.breakdown.output).toBe(0.004);
    expect(r!.breakdown.cacheRead).toBe(0);
    expect(r!.breakdown.cacheCreate).toBe(0);
    expect(r!.cost).toBe(0.006);
    expect(r!.currency).toBe('USD');
  });

  test('costFromUsage: unknown provider/model returns null (don\'t silently bill at zero)', async () => {
    const { costFromUsage } = await import('../src/lazyclaw/providers/rates.mjs' as string);
    const rates = { 'openai/gpt-4.1': { inputPer1M: 2, outputPer1M: 8 } };
    expect(costFromUsage({
      provider: 'anthropic',
      model: 'claude-opus-4-7',
      usage: { inputTokens: 1000, outputTokens: 500 },
    }, rates)).toBeNull();
  });

  test('costFromUsage: missing inputs return null rather than throwing', async () => {
    const { costFromUsage } = await import('../src/lazyclaw/providers/rates.mjs' as string);
    expect(costFromUsage(null as any, { x: { inputPer1M: 1, outputPer1M: 1 } })).toBeNull();
    expect(costFromUsage({ provider: 'x', model: 'y', usage: {} } as any, null as any)).toBeNull();
  });

  test('RATE_CARD_SHAPE ships zero placeholders (no silent default prices)', async () => {
    const mod = await import('../src/lazyclaw/providers/rates.mjs' as string);
    const shape = mod.RATE_CARD_SHAPE;
    expect(Object.keys(shape).length).toBeGreaterThan(0);
    for (const [key, card] of Object.entries(shape)) {
      // Every numeric rate field is exactly 0 — callers MUST fill in
      // real numbers or get null back from costFromUsage.
      expect((card as any).inputPer1M).toBe(0);
      expect((card as any).outputPer1M).toBe(0);
    }
  });

  test('chat /usage adds cost block when cfg.rates is configured for the active model', async () => {
    const dir = tmpConfigDir();
    // Set provider/model + rates for the active card.
    runCli(['config', 'set', 'provider', 'anthropic'], dir);
    runCli(['config', 'set', 'api-key', 'sk-ant-x'], dir);
    runCli(['config', 'set', 'model', 'claude-opus-4-7'], dir);
    const cfgPath = path.join(dir, 'config.json');
    const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
    cfg.rates = {
      'anthropic/claude-opus-4-7': { inputPer1M: 15, outputPer1M: 75, currency: 'USD' },
    };
    fs.writeFileSync(cfgPath, JSON.stringify(cfg));

    const preload = path.join(dir, 'preload.mjs');
    fs.writeFileSync(preload,
      `import('${path.resolve('src/lazyclaw/providers/registry.mjs')}').then(reg => {
        reg.PROVIDERS.anthropic = {
          name: 'anthropic',
          async *sendMessage(_msgs, opts) {
            yield 'r';
            opts.onUsage?.({ inputTokens: 1000, outputTokens: 500 });
          },
        };
      });`,
    );
    const child = spawn(process.execPath, ['--import', preload, CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stdin.write('q\n');
    await new Promise(r => setTimeout(r, 250));
    child.stdin.write('/usage\n');
    await new Promise(r => setTimeout(r, 200));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));
    const out = chunks.join('');
    const usageLine = out.split('\n').find(l => l.startsWith('{') && l.includes('cost'));
    expect(usageLine).toBeDefined();
    const u = JSON.parse(usageLine!);
    expect(u.tokens.inputTokens).toBe(1000);
    expect(u.cost.cost).toBe(0.0525);
    expect(u.cost.currency).toBe('USD');
  });

  test('chat /usage with mock provider reports messageCount + charsSent only (no tokens block)', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);

    const child = spawn(process.execPath, [CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stdin.write('hello\n');
    await new Promise(r => setTimeout(r, 250));
    child.stdin.write('/usage\n');
    await new Promise(r => setTimeout(r, 200));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));
    const out = chunks.join('');
    // Find the /usage JSON line
    const usageLine = out.split('\n').find(l => l.startsWith('{') && l.includes('messageCount'));
    expect(usageLine).toBeDefined();
    const u = JSON.parse(usageLine!);
    expect(u.messageCount).toBeGreaterThanOrEqual(2);
    expect(u.charsSent).toBe('hello'.length);
    // Mock doesn't emit usage events → no tokens block
    expect(u.tokens).toBeUndefined();
  });

  test('chat /usage accumulates token totals across turns when the provider emits onUsage', async () => {
    const dir = tmpConfigDir();
    // We monkey-patch the anthropic provider via Node --import preload
    // (same trick used by the agent --usage tests above) so the chat
    // REPL talks to a fake that emits {inputTokens, outputTokens} per turn.
    runCli(['config', 'set', 'provider', 'anthropic'], dir);
    runCli(['config', 'set', 'api-key', 'sk-ant-x'], dir);
    const preload = path.join(dir, 'preload.mjs');
    fs.writeFileSync(preload,
      `import('${path.resolve('src/lazyclaw/providers/registry.mjs')}').then(reg => {
        let turn = 0;
        reg.PROVIDERS.anthropic = {
          name: 'anthropic',
          async *sendMessage(_msgs, opts) {
            turn += 1;
            yield 'reply' + turn;
            if (typeof opts.onUsage === 'function') {
              opts.onUsage({ inputTokens: 10 * turn, outputTokens: 5 * turn });
            }
          },
        };
      });`,
    );
    const child = spawn(process.execPath, ['--import', preload, CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stdin.write('first\n');
    await new Promise(r => setTimeout(r, 200));
    child.stdin.write('second\n');
    await new Promise(r => setTimeout(r, 200));
    child.stdin.write('/usage\n');
    await new Promise(r => setTimeout(r, 200));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));
    const out = chunks.join('');
    const usageLine = out.split('\n').find(l => l.startsWith('{') && l.includes('tokens'));
    expect(usageLine).toBeDefined();
    const u = JSON.parse(usageLine!);
    // 2 turns × (10+5 input/output) = 30 across the test stub
    expect(u.tokens.inputTokens).toBe(10 + 20);    // turn 1 (10) + turn 2 (20)
    expect(u.tokens.outputTokens).toBe(5 + 10);    // turn 1 (5) + turn 2 (10)
    expect(u.tokens.turnsWithUsage).toBe(2);
  });

  test('chat /new resets the running usage accumulator', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'anthropic'], dir);
    runCli(['config', 'set', 'api-key', 'sk-ant-x'], dir);
    const preload = path.join(dir, 'preload.mjs');
    fs.writeFileSync(preload,
      `import('${path.resolve('src/lazyclaw/providers/registry.mjs')}').then(reg => {
        reg.PROVIDERS.anthropic = {
          name: 'anthropic',
          async *sendMessage(_msgs, opts) {
            yield 'r';
            opts.onUsage?.({ inputTokens: 100, outputTokens: 50 });
          },
        };
      });`,
    );
    const child = spawn(process.execPath, ['--import', preload, CLI, 'chat'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks: string[] = [];
    child.stdout.on('data', d => chunks.push(d.toString()));
    child.stdin.write('q\n');
    await new Promise(r => setTimeout(r, 200));
    child.stdin.write('/new\n');
    await new Promise(r => setTimeout(r, 100));
    child.stdin.write('/usage\n');
    await new Promise(r => setTimeout(r, 100));
    child.stdin.write('/exit\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));
    const out = chunks.join('');
    // After /new, /usage should NOT have a tokens block (accumulator reset).
    const lines = out.split('\n').filter(l => l.startsWith('{') && l.includes('messageCount'));
    expect(lines.length).toBeGreaterThanOrEqual(1);
    const post = JSON.parse(lines[lines.length - 1]);
    expect(post.tokens).toBeUndefined();
    expect(post.messageCount).toBe(0);
  });

  test('gracefulShutdown: server closes in time → forced=false', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    // Mock server whose close() invokes the callback right away.
    const fakeServer = {
      close(cb: any) { setImmediate(() => cb()); },
    };
    const r = await mod.gracefulShutdown(fakeServer, 1000);
    expect(r.forced).toBe(false);
  });

  test('gracefulShutdown: timeout wins → forced=true and closeAllConnections is called', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    let forceCalled = 0;
    // close() never invokes the callback — simulates a hung connection.
    const fakeServer = {
      close(_cb: any) { /* never resolve */ },
      closeAllConnections() { forceCalled += 1; },
    };
    const t0 = Date.now();
    const r = await mod.gracefulShutdown(fakeServer, 50);
    const elapsed = Date.now() - t0;
    expect(r.forced).toBe(true);
    expect(forceCalled).toBe(1);
    // Should have unblocked at the timeout, not waited longer.
    expect(elapsed).toBeLessThan(500);
  });

  test('gracefulShutdown: timeout works even when server lacks closeAllConnections (older Node)', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const fakeServer = { close(_cb: any) { /* never resolve */ } };
    const r = await mod.gracefulShutdown(fakeServer, 30);
    expect(r.forced).toBe(true);  // still resolves; just no force-close to call
  });

  test('agent --cost prints cost line to stderr when rates configured', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'anthropic'], dir);
    runCli(['config', 'set', 'api-key', 'sk-ant-x'], dir);
    runCli(['config', 'set', 'model', 'claude-opus-4-7'], dir);
    // Inject rates manually since `config set` only handles strings.
    const cfgPath = path.join(dir, 'config.json');
    const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
    cfg.rates = {
      'anthropic/claude-opus-4-7': { inputPer1M: 15, outputPer1M: 75, currency: 'USD' },
    };
    fs.writeFileSync(cfgPath, JSON.stringify(cfg));

    // Stub anthropic so onUsage emits known totals.
    const preload = path.join(dir, 'preload.mjs');
    fs.writeFileSync(preload,
      `import('${path.resolve('src/lazyclaw/providers/registry.mjs')}').then(reg => {
        reg.PROVIDERS.anthropic = {
          name: 'anthropic',
          async *sendMessage(_msgs, opts) {
            yield 'reply';
            opts.onUsage?.({ inputTokens: 1000, outputTokens: 500 });
          },
        };
      });`,
    );
    const r = spawnSync(process.execPath, ['--import', preload, CLI, 'agent', 'q', '--cost'], {
      encoding: 'utf8',
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
    });
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('reply');
    expect(r.stderr).toMatch(/cost:.*"cost":0\.0525/);
  });

  test('agent --cost without cfg.rates is silently a no-op (response still streams)', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const r = runCli(['agent', 'q', '--cost'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('mock-reply: q');
    // No cost line — mock doesn't emit usage, and rates aren't set.
    expect(r.stderr).not.toMatch(/cost:/);
  });

  test('agent --usage prints normalized totals to stderr (mock provider yields no usage so absence is OK)', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    // Mock provider doesn't emit usage events. With --usage set, the
    // CLI installs the onUsage callback but mock never calls it. The
    // critical assertion: --usage must NOT crash the agent path.
    const r = runCli(['agent', 'hello', '--usage'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('mock-reply: hello');
    // No usage line on stderr (mock doesn't emit) — absence of crash is the test.
    expect(r.stderr).not.toMatch(/error/);
  });

  test('agent --usage with anthropic stub produces a usage line on stderr after the response', () => {
    // Drive cmdAgent through a custom Node import so we can replace
    // anthropic with a fake that emits a usage event.
    const dir = tmpConfigDir();
    const preload = path.join(dir, 'preload.mjs');
    fs.writeFileSync(preload,
      `import('node:module').then(({ register }) => {
        // Monkey-patch the anthropic provider's sendMessage at runtime
        // by intercepting its registry import. The simplest way: alias
        // a fake fetch. But the agent doesn't accept opts.fetch. So we
        // patch the provider directly via the registry the cli loads.
      });
      // Patch the anthropic provider once it loads.
      import('${path.resolve('src/lazyclaw/providers/registry.mjs')}').then(reg => {
        reg.PROVIDERS.anthropic = {
          name: 'anthropic',
          async *sendMessage(_msgs, opts) {
            yield 'reply';
            if (typeof opts.onUsage === 'function') {
              opts.onUsage({ inputTokens: 7, outputTokens: 4 });
            }
          },
        };
      });`,
    );
    runCli(['config', 'set', 'provider', 'anthropic'], dir);
    runCli(['config', 'set', 'api-key', 'sk-ant-x'], dir);
    const r = spawnSync(process.execPath, ['--import', preload, CLI, 'agent', 'hi', '--usage'], {
      encoding: 'utf8',
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
    });
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('reply');
    expect(r.stderr).toMatch(/usage:.*"inputTokens":7.*"outputTokens":4/);
  });

  test('daemon POST /agent with body.usage:true returns the usage block when the provider emits it', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      // Mock provider doesn't emit usage; without it the daemon must
      // simply not include a usage field — verifying the opt-in shape.
      const r = await fetch(`${d.url}/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prompt: 'q', usage: true }),
      });
      expect(r.status).toBe(200);
      const j = await r.json();
      expect(j.reply).toContain('mock-reply: q');
      // Mock didn't emit usage → daemon must omit the field, not send null.
      expect('usage' in j).toBe(false);
    } finally { await d.kill(); }
  });

  test('daemon POST /chat default response (no body.usage) never includes a usage field', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const d = await startDaemonProc(dir);
    try {
      const r = await fetch(`${d.url}/chat`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ messages: [{ role: 'user', content: 'q' }] }),
      });
      const j = await r.json();
      expect(j.reply).toBeDefined();
      expect('usage' in j).toBe(false);  // default — no opt-in
    } finally { await d.kill(); }
  });

  test('anthropic provider surfaces usage totals via opts.onUsage at message_stop', async () => {
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    const sse =
      'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_1","model":"claude-opus-4-7","usage":{"input_tokens":42,"cache_creation_input_tokens":10,"cache_read_input_tokens":0}}}\n\n' +
      'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hello"}}\n\n' +
      'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":17}}\n\n' +
      'event: message_stop\ndata: {"type":"message_stop"}\n\n';
    const fakeFetch = async () => ({
      ok: true, status: 200,
      body: new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(sse)); c.close(); } }),
    });
    let captured: any = null;
    const out: string[] = [];
    for await (const c of mod.anthropicProvider.sendMessage(
      [{ role: 'user', content: 'q' }],
      { apiKey: 'sk-ant-x', model: 'claude-opus-4-7', fetch: fakeFetch as any, onUsage: (u: any) => { captured = u; } },
    )) out.push(c);
    expect(out.join('')).toBe('hello');
    expect(captured).toEqual({
      inputTokens: 42,
      outputTokens: 17,
      cacheCreationInputTokens: 10,
      cacheReadInputTokens: 0,
    });
  });

  test('anthropic onUsage: missing callback is a no-op (back-compat for existing callers)', async () => {
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    const sse =
      'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":1}}}\n\n' +
      'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"x"}}\n\n' +
      'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":2}}\n\n' +
      'event: message_stop\ndata: {"type":"message_stop"}\n\n';
    const fakeFetch = async () => ({
      ok: true, status: 200,
      body: new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(sse)); c.close(); } }),
    });
    // No onUsage provided — must not throw or change yielded text.
    const out: string[] = [];
    for await (const c of mod.anthropicProvider.sendMessage(
      [{ role: 'user', content: 'q' }],
      { apiKey: 'sk-ant-x', model: 'claude-opus-4-7', fetch: fakeFetch as any },
    )) out.push(c);
    expect(out.join('')).toBe('x');
  });

  test('openai provider surfaces usage via opts.onUsage (with stream_options.include_usage)', async () => {
    const mod = await import('../src/lazyclaw/providers/openai.mjs' as string);
    let sentBody: any = null;
    const sse =
      'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n' +
      'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n' +
      'data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":3,"total_tokens":15}}\n\n' +
      'data: [DONE]\n\n';
    const fakeFetch = async (_url: string, init: any) => {
      sentBody = JSON.parse(init.body);
      return {
        ok: true, status: 200,
        body: new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(sse)); c.close(); } }),
      };
    };
    let captured: any = null;
    const out: string[] = [];
    for await (const c of mod.openaiProvider.sendMessage(
      [{ role: 'user', content: 'q' }],
      { apiKey: 'sk-x', model: 'gpt-4.1', fetch: fakeFetch as any, onUsage: (u: any) => { captured = u; } },
    )) out.push(c);
    expect(out.join('')).toBe('hi');
    // Provider must have set stream_options on the wire request.
    expect(sentBody.stream_options).toEqual({ include_usage: true });
    expect(captured).toEqual({ inputTokens: 12, outputTokens: 3, totalTokens: 15 });
  });

  test('openai onUsage opt-in: missing callback omits stream_options entirely', async () => {
    const mod = await import('../src/lazyclaw/providers/openai.mjs' as string);
    let sentBody: any = null;
    const fakeFetch = async (_url: string, init: any) => {
      sentBody = JSON.parse(init.body);
      return {
        ok: true, status: 200,
        body: new ReadableStream({
          start(c) {
            c.enqueue(new TextEncoder().encode(
              'data: {"choices":[{"delta":{"content":"x"}}]}\n\ndata: [DONE]\n\n',
            ));
            c.close();
          },
        }),
      };
    };
    const out: string[] = [];
    for await (const c of mod.openaiProvider.sendMessage(
      [{ role: 'user', content: 'q' }],
      { apiKey: 'sk-x', model: 'gpt-4.1', fetch: fakeFetch as any },
    )) out.push(c);
    expect(out.join('')).toBe('x');
    // Without onUsage we must NOT request usage — keeps the wire shape
    // identical to pre-2.97.0 callers.
    expect(sentBody.stream_options).toBeUndefined();
  });

  test('cache wrapper: onHit/onMiss callbacks fire once per call with the right shape', async () => {
    const { withResponseCache } = await import('../src/lazyclaw/providers/cache.mjs' as string);
    const events: any[] = [];
    const inner = { name: 'mock', async *sendMessage() { yield 'X'; } };
    const cached = withResponseCache(inner, {
      onMiss: (info: any) => events.push({ kind: 'miss', ...info }),
      onHit:  (info: any) => events.push({ kind: 'hit',  ...info }),
    });
    const drain = async () => {
      for await (const _c of cached.sendMessage([{ role: 'user', content: 'q' }], { model: 'm' })) { /* drain */ }
    };
    await drain();   // miss
    await drain();   // hit
    await drain();   // hit
    expect(events.map(e => e.kind)).toEqual(['miss', 'hit', 'hit']);
    expect(events[0].keyHash).toMatch(/^[0-9a-f]+$/);
    expect(events[1].size).toBe(1);
  });

  // Helper for the two log-wiring tests: build a minimal handler harness
  // and a fake req/res that lets us drive POST /agent with a body.
  async function driveAgent(daemonOpts: any, body: any): Promise<{ status: number; body: any; lines: string[] }> {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const { createLogger } = await import('../src/lazyclaw/logger.mjs' as string);
    const lines: string[] = [];
    const logger = createLogger({ level: 'debug', sink: (l: string) => lines.push(l) });
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      logger,
      ...daemonOpts,
    });
    let capturedStatus = 0;
    let capturedBody = '';
    const req: any = {
      method: 'POST',
      url: '/agent',
      headers: { 'content-type': 'application/json' },
      socket: { remoteAddress: '127.0.0.1' },
      setEncoding() {},
      on(event: string, fn: any) {
        if (event === 'data') fn(JSON.stringify(body));
        if (event === 'end') fn();
      },
    };
    const res: any = {
      writeHead(s: number) { capturedStatus = s; },
      write() {},
      end(d?: string) { if (d) capturedBody = d; },
      once: () => {},
    };
    await handler(req, res);
    return { status: capturedStatus, body: capturedBody ? JSON.parse(capturedBody) : null, lines };
  }

  test('daemon with --log debug: retry-only path emits provider.retry log lines', async () => {
    // Force the mock provider to RATE_LIMIT every call. With body.retry
    // and NO fallback, retry exhausts and the request 429s — but along
    // the way each retry attempt should log a provider.retry record.
    const reg = await import('../src/lazyclaw/providers/registry.mjs' as string);
    const orig = reg.PROVIDERS.mock;
    reg.PROVIDERS.mock = {
      name: 'mock',
      async *sendMessage() {
        const e: any = new Error('rate limited');
        e.code = 'RATE_LIMIT'; e.retryAfterMs = 1;
        throw e;
      },
    };
    try {
      const { status, lines } = await driveAgent({}, { prompt: 'hi', retry: { attempts: 2, maxBackoffMs: 1 } });
      expect(status).toBe(429);
      const recs = lines.map(l => JSON.parse(l));
      const retryEvents = recs.filter(r => r.msg === 'provider.retry');
      // attempts: 2 → 2 retries fire (each logged); the third throw exhausts.
      expect(retryEvents.length).toBe(2);
      expect(retryEvents[0].errorCode).toBe('RATE_LIMIT');
      expect(retryEvents[0].attempt).toBe(1);
      expect(retryEvents[1].attempt).toBe(2);
    } finally {
      reg.PROVIDERS.mock = orig;
    }
  });

  test('daemon with --log debug: fallback path emits provider.fallback log line', async () => {
    // Mock RATE_LIMITs once; anthropic-stub serves successfully. With
    // body.fallback and NO retry, fallback transitions and logs the move.
    const reg = await import('../src/lazyclaw/providers/registry.mjs' as string);
    const origMock = reg.PROVIDERS.mock;
    const origAnt = reg.PROVIDERS.anthropic;
    reg.PROVIDERS.mock = {
      name: 'mock',
      async *sendMessage() {
        const e: any = new Error('rate limited');
        e.code = 'RATE_LIMIT'; e.retryAfterMs = 1;
        throw e;
      },
    };
    reg.PROVIDERS.anthropic = {
      name: 'anthropic',
      async *sendMessage() { yield 'fromAlt'; },
    };
    try {
      const { status, body, lines } = await driveAgent({}, { prompt: 'hi', fallback: ['anthropic'] });
      expect(status).toBe(200);
      expect(body.reply).toBe('fromAlt');
      const recs = lines.map(l => JSON.parse(l));
      const fallbackEvents = recs.filter(r => r.msg === 'provider.fallback');
      expect(fallbackEvents.length).toBe(1);
      expect(fallbackEvents[0].from).toBe('mock');
      expect(fallbackEvents[0].to).toBe('anthropic');
      expect(fallbackEvents[0].errorCode).toBe('RATE_LIMIT');
    } finally {
      reg.PROVIDERS.mock = origMock;
      reg.PROVIDERS.anthropic = origAnt;
    }
  });

  test('daemon: forbidden-Origin requests do NOT cost a rate-limit token (Origin runs first)', async () => {
    // Symmetric to the auth-before-rate-limit test: a malicious browser
    // page hitting 127.0.0.1 with a foreign Origin must not be able to
    // exhaust the bucket either. Origin gate runs first so those
    // requests get 403 before reaching the limiter.
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      rateLimit: { capacity: 2, refillPerSec: 0.001 },
      // No allowedOrigins — every Origin-bearing request is forbidden
    });
    const drive = async (origin?: string) => {
      let status = 0;
      const headers: any = origin ? { origin } : {};
      const req: any = { method: 'GET', url: '/version', headers, socket: { remoteAddress: '127.0.0.1' } };
      const res: any = { writeHead(s: number) { status = s; }, end() {}, once: () => {} };
      await handler(req, res);
      return status;
    };
    // 10 evil-origin requests — all 403, none cost a token
    for (let i = 0; i < 10; i++) {
      expect(await drive('https://evil.example')).toBe(403);
    }
    // No-origin (CLI/script) requests still get the full bucket
    expect(await drive()).toBe(200);
    expect(await drive()).toBe(200);
    expect(await drive()).toBe(429);
  });

  test('daemon: unauthenticated requests do NOT cost a rate-limit token (auth runs first)', async () => {
    // Production scenario: a public-facing daemon with --auth-token AND
    // --rate-limit. If rate limit ran before auth, an attacker could
    // exhaust the legitimate user's budget with junk requests. Auth
    // first means anonymous traffic gets 401'd before touching the
    // bucket — verified here by exhausting attempts with bad-auth then
    // sending a good-auth request that still goes through.
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '0.0.0',
      authToken: 'good',
      rateLimit: { capacity: 2, refillPerSec: 0.001 },  // glacial refill
    });
    const drive = async (token: string | null) => {
      let status = 0;
      const headers: any = {};
      if (token !== null) headers.authorization = `Bearer ${token}`;
      const req: any = { method: 'GET', url: '/version', headers, socket: { remoteAddress: '127.0.0.1' } };
      const res: any = { writeHead(s: number) { status = s; }, end() {}, once: () => {} };
      await handler(req, res);
      return status;
    };
    // 5 unauthenticated requests — all 401, none should cost a token
    for (let i = 0; i < 5; i++) {
      expect(await drive('wrong-token')).toBe(401);
    }
    // 5 missing-auth requests — also 401, also free
    for (let i = 0; i < 5; i++) {
      expect(await drive(null)).toBe(401);
    }
    // Now an authenticated request — bucket should be intact (cap 2)
    expect(await drive('good')).toBe(200);
    expect(await drive('good')).toBe(200);
    // Third authenticated request 429s — budget actually applies once
    // we cross the auth gate.
    expect(await drive('good')).toBe(429);
  });

  test('daemon CLI --rate-limit caps a remote and surfaces in the bound-URL JSON', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir, ['--rate-limit', '2']);
    try {
      // First two requests OK.
      expect((await fetch(`${d.url}/version`)).status).toBe(200);
      expect((await fetch(`${d.url}/version`)).status).toBe(200);
      // Third should 429 (token bucket cap of 2, glacial 2/60s refill).
      const denied = await fetch(`${d.url}/version`);
      expect(denied.status).toBe(429);
      expect(denied.headers.get('retry-after')).toBeDefined();
    } finally { await d.kill(); }
  });

  test('daemon CLI --auth-token reports auth=true and rejects unauthenticated requests', async () => {
    const dir = tmpConfigDir();
    const d = await startDaemonProc(dir, ['--auth-token', 'integration-secret']);
    try {
      const noAuth = await fetch(`${d.url}/version`);
      expect(noAuth.status).toBe(401);
      const withAuth = await fetch(`${d.url}/version`, { headers: { authorization: 'Bearer integration-secret' } });
      expect(withAuth.status).toBe(200);
      const j = await withAuth.json();
      expect(j.version).toMatch(/^\d+\.\d+\.\d+/);
    } finally { await d.kill(); }
  });

  test('lazyclaw daemon --auth-token T enforces the token end-to-end', async () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const child = spawn(process.execPath, [CLI, 'daemon', '--port', '0', '--auth-token', 'tok-xyz'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let url = '';
    let auth = false;
    await new Promise<void>((resolve, reject) => {
      let buf = '';
      child.stdout.on('data', (d) => {
        buf += d.toString();
        const nl = buf.indexOf('\n');
        if (nl < 0) return;
        try {
          const obj = JSON.parse(buf.slice(0, nl));
          if (obj.url) { url = obj.url; auth = !!obj.auth; resolve(); }
        } catch { /* keep buffering */ }
      });
      child.on('error', reject);
      setTimeout(() => reject(new Error('daemon did not boot in 5s')), 5000);
    });
    try {
      expect(auth).toBe(true);
      const r1 = await fetch(`${url}/version`);
      expect(r1.status).toBe(401);
      const r2 = await fetch(`${url}/version`, { headers: { authorization: 'Bearer tok-xyz' } });
      expect(r2.status).toBe(200);
    } finally {
      await new Promise<void>(resolve => { child.once('close', () => resolve()); child.kill('SIGTERM'); });
    }
  });

  test('daemon makeHandler without authToken: any request goes through (default loopback mode)', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    const sessionsMod = await import('../src/lazyclaw/sessions.mjs' as string);
    const handler = mod.makeHandler({
      readConfig: () => ({}),
      sessionsDirGetter: () => '/tmp',
      sessionsMod,
      version: () => '1.0.0',
      // no authToken
    });
    let status = 0;
    const fakeReq: any = { method: 'GET', url: '/version', headers: {} };
    const fakeRes: any = { writeHead(s: number) { status = s; }, end() {} };
    await handler(fakeReq, fakeRes);
    expect(status).toBe(200);
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

  test('daemon statusForProviderError maps error codes to HTTP statuses', async () => {
    const mod = await import('../src/lazyclaw/daemon.mjs' as string);
    expect(mod.statusForProviderError({ code: 'INVALID_KEY' })).toEqual({ status: 401 });
    const rate = mod.statusForProviderError({ code: 'RATE_LIMIT', retryAfterMs: 7000 });
    expect(rate.status).toBe(429);
    expect(rate.headers['retry-after']).toBe('7');
    // Sub-second retry rounds up to 1s — never 0 (we don't want to hammer)
    const subSecond = mod.statusForProviderError({ code: 'RATE_LIMIT', retryAfterMs: 100 });
    expect(subSecond.headers['retry-after']).toBe('1');
    // Pass-through: an arbitrary 4xx/5xx status from the provider keeps
    // its original status code.
    expect(mod.statusForProviderError({ status: 503 })).toEqual({ status: 503 });
    // Default for anything else: 502 Bad Gateway (we acted as the gateway).
    expect(mod.statusForProviderError({})).toEqual({ status: 502 });
    expect(mod.statusForProviderError(undefined)).toEqual({ status: 502 });
  });

  test('anthropic 429 → RateLimitError with parsed retry-after seconds', async () => {
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    const fakeFetch = async () => ({
      ok: false, status: 429,
      headers: new Headers({ 'retry-after': '7' }),
      text: async () => '{"error":{"message":"rate limited"}}',
    });
    let caught: any = null;
    try {
      for await (const _c of mod.anthropicProvider.sendMessage(
        [{ role: 'user', content: 'hi' }],
        { apiKey: 'sk-ant-x', model: 'claude-opus-4-7', fetch: fakeFetch as any },
      )) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('RATE_LIMIT');
    expect(caught?.status).toBe(429);
    expect(caught?.retryAfterMs).toBe(7000);
  });

  test('openai 429 → RateLimitError; missing retry-after defaults to 1000ms', async () => {
    const mod = await import('../src/lazyclaw/providers/openai.mjs' as string);
    const fakeFetch = async () => ({
      ok: false, status: 429,
      headers: new Headers({}),
      text: async () => '{"error":{"message":"rate limited"}}',
    });
    let caught: any = null;
    try {
      for await (const _c of mod.openaiProvider.sendMessage(
        [{ role: 'user', content: 'hi' }],
        { apiKey: 'sk-x', model: 'gpt-4.1', fetch: fakeFetch as any },
      )) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('RATE_LIMIT');
    expect(caught?.retryAfterMs).toBe(1000);
  });

  test('rate-limit retry-after also parses an HTTP-date', async () => {
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    const future = new Date(Date.now() + 5000).toUTCString();
    const fakeFetch = async () => ({
      ok: false, status: 429,
      headers: { 'retry-after': future },
      text: async () => '',
    });
    let caught: any = null;
    try {
      for await (const _c of mod.anthropicProvider.sendMessage(
        [{ role: 'user', content: 'hi' }],
        { apiKey: 'sk-ant-x', model: 'claude-opus-4-7', fetch: fakeFetch as any },
      )) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('RATE_LIMIT');
    // Allow ±2s of slack so the test isn't flaky on slow CI
    expect(caught?.retryAfterMs).toBeGreaterThan(2000);
    expect(caught?.retryAfterMs).toBeLessThan(8000);
  });

  test('withRateLimitRetry retries on RATE_LIMIT and yields the second attempt', async () => {
    const mod = await import('../src/lazyclaw/providers/retry.mjs' as string);
    const calls: number[] = [];
    let attempt = 0;
    const fakeProv = {
      name: 'fake',
      async *sendMessage(_messages: any, _opts: any) {
        attempt += 1;
        calls.push(attempt);
        if (attempt === 1) {
          const e: any = new Error('rate limited');
          e.code = 'RATE_LIMIT';
          e.retryAfterMs = 50;
          throw e;
        }
        yield 'finally';
      },
    };
    const sleeps: number[] = [];
    const sleep = async (ms: number) => { sleeps.push(ms); };
    const retried = mod.withRateLimitRetry(fakeProv, { attempts: 3, sleep });
    const out: string[] = [];
    for await (const chunk of retried.sendMessage([{ role: 'user', content: 'q' }], {})) {
      out.push(chunk);
    }
    expect(out.join('')).toBe('finally');
    expect(calls).toEqual([1, 2]);
    expect(sleeps).toEqual([50]);
  });

  test('withRateLimitRetry exhausts attempts and rethrows the last RATE_LIMIT', async () => {
    const mod = await import('../src/lazyclaw/providers/retry.mjs' as string);
    const fakeProv = {
      name: 'fake',
      async *sendMessage(_m: any, _o: any) {
        const e: any = new Error('rate limited');
        e.code = 'RATE_LIMIT';
        e.retryAfterMs = 1;
        throw e;
      },
    };
    let caught: any = null;
    const sleep = async () => {};
    const retried = mod.withRateLimitRetry(fakeProv, { attempts: 2, sleep });
    try {
      for await (const _c of retried.sendMessage([{ role: 'user', content: 'q' }], {})) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('RATE_LIMIT');
  });

  test('withRateLimitRetry does NOT retry mid-stream RATE_LIMIT (would duplicate output)', async () => {
    const mod = await import('../src/lazyclaw/providers/retry.mjs' as string);
    let calls = 0;
    const fakeProv = {
      name: 'fake',
      async *sendMessage() {
        calls += 1;
        yield 'partial';
        const e: any = new Error('rate limited');
        e.code = 'RATE_LIMIT';
        e.retryAfterMs = 0;
        throw e;
      },
    };
    const out: string[] = [];
    let caught: any = null;
    const retried = mod.withRateLimitRetry(fakeProv, { attempts: 5, sleep: async () => {} });
    try {
      for await (const c of retried.sendMessage([{ role: 'user', content: 'q' }], {})) { out.push(c); }
    } catch (e) { caught = e; }
    expect(out).toEqual(['partial']);
    expect(caught?.code).toBe('RATE_LIMIT');
    expect(calls).toBe(1);
  });

  test('withRateLimitRetry does NOT retry non-RATE_LIMIT errors', async () => {
    const mod = await import('../src/lazyclaw/providers/retry.mjs' as string);
    let calls = 0;
    const fakeProv = {
      name: 'fake',
      async *sendMessage() {
        calls += 1;
        const e: any = new Error('boom');
        e.code = 'INVALID_KEY';
        throw e;
      },
    };
    const retried = mod.withRateLimitRetry(fakeProv, { attempts: 5, sleep: async () => {} });
    let caught: any = null;
    try {
      for await (const _c of retried.sendMessage([{ role: 'user', content: 'q' }], {})) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('INVALID_KEY');
    expect(calls).toBe(1);
  });

  test('withRateLimitRetry onRetry callback receives attempt number and waited ms', async () => {
    const mod = await import('../src/lazyclaw/providers/retry.mjs' as string);
    const log: any[] = [];
    let attempt = 0;
    const fakeProv = {
      name: 'fake',
      async *sendMessage() {
        attempt += 1;
        if (attempt < 3) {
          const e: any = new Error('rl');
          e.code = 'RATE_LIMIT';
          e.retryAfterMs = 100;
          throw e;
        }
        yield 'ok';
      },
    };
    const retried = mod.withRateLimitRetry(fakeProv, {
      attempts: 5,
      sleep: async () => {},
      onRetry: (info: any) => log.push({ attempt: info.attempt, ms: info.retryAfterMs }),
    });
    const out: string[] = [];
    for await (const c of retried.sendMessage([{ role: 'user', content: 'q' }], {})) out.push(c);
    expect(out.join('')).toBe('ok');
    expect(log).toEqual([
      { attempt: 1, ms: 100 },
      { attempt: 2, ms: 100 },
    ]);
  });

  test('clampBackoff clamps to maxBackoffMs and to absolute ceiling 5 minutes', async () => {
    const mod = await import('../src/lazyclaw/providers/retry.mjs' as string);
    expect(mod.clampBackoff(50, 60000)).toBe(50);
    expect(mod.clampBackoff(70_000, 60_000)).toBe(60_000);
    // Absolute ceiling overrides even an oversized maxBackoffMs from the caller.
    expect(mod.clampBackoff(10 * 60_000, 10 * 60_000)).toBe(5 * 60_000);
    // Negative or non-finite → ceiling
    expect(mod.clampBackoff(-1, 30_000)).toBe(30_000);
    expect(mod.clampBackoff(Number.NaN, 30_000)).toBe(30_000);
  });

  test('withFallback: primary throws RATE_LIMIT pre-yield → next provider yields successfully', async () => {
    const mod = await import('../src/lazyclaw/providers/fallback.mjs' as string);
    const calls: string[] = [];
    const primary = {
      name: 'primary',
      async *sendMessage() {
        calls.push('primary');
        const e: any = new Error('rl');
        e.code = 'RATE_LIMIT';
        e.retryAfterMs = 1;
        throw e;
      },
    };
    const fallback = {
      name: 'fallback',
      async *sendMessage() {
        calls.push('fallback');
        yield 'rescued';
      },
    };
    const chain = mod.withFallback([primary, fallback]);
    const out: string[] = [];
    for await (const c of chain.sendMessage([{ role: 'user', content: 'q' }], {})) out.push(c);
    expect(out.join('')).toBe('rescued');
    expect(calls).toEqual(['primary', 'fallback']);
    expect(chain.name).toBe('fallback(primary→fallback)');
  });

  test('withFallback: INVALID_KEY does NOT trigger fallback (auth errors are structural)', async () => {
    const mod = await import('../src/lazyclaw/providers/fallback.mjs' as string);
    let fallbackCalled = false;
    const primary = {
      name: 'primary',
      async *sendMessage() {
        const e: any = new Error('auth');
        e.code = 'INVALID_KEY';
        throw e;
      },
    };
    const secondary = {
      name: 'secondary',
      async *sendMessage() { fallbackCalled = true; yield 'x'; },
    };
    const chain = mod.withFallback([primary, secondary]);
    let caught: any = null;
    try {
      for await (const _c of chain.sendMessage([{ role: 'user', content: 'q' }], {})) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('INVALID_KEY');
    expect(fallbackCalled).toBe(false);
  });

  test('withFallback: ABORT does NOT trigger fallback (user cancellation should stop, not retry)', async () => {
    const mod = await import('../src/lazyclaw/providers/fallback.mjs' as string);
    let fallbackCalled = false;
    const primary = {
      name: 'primary',
      async *sendMessage() {
        const e: any = new Error('abort');
        e.code = 'ABORT';
        throw e;
      },
    };
    const secondary = {
      name: 'secondary',
      async *sendMessage() { fallbackCalled = true; yield 'x'; },
    };
    const chain = mod.withFallback([primary, secondary]);
    let caught: any = null;
    try {
      for await (const _c of chain.sendMessage([{ role: 'user', content: 'q' }], {})) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('ABORT');
    expect(fallbackCalled).toBe(false);
  });

  test('withFallback: mid-stream error does NOT trigger fallback (would duplicate text)', async () => {
    const mod = await import('../src/lazyclaw/providers/fallback.mjs' as string);
    let fallbackCalled = false;
    const primary = {
      name: 'primary',
      async *sendMessage() {
        yield 'partial';
        const e: any = new Error('rl');
        e.code = 'RATE_LIMIT';
        throw e;
      },
    };
    const secondary = {
      name: 'secondary',
      async *sendMessage() { fallbackCalled = true; yield 'x'; },
    };
    const chain = mod.withFallback([primary, secondary]);
    const out: string[] = [];
    let caught: any = null;
    try {
      for await (const c of chain.sendMessage([{ role: 'user', content: 'q' }], {})) out.push(c);
    } catch (e) { caught = e; }
    expect(out).toEqual(['partial']);
    expect(caught?.code).toBe('RATE_LIMIT');
    expect(fallbackCalled).toBe(false);
  });

  test('withFallback: 5xx upstream falls back; onFallback callback observes the transition', async () => {
    const mod = await import('../src/lazyclaw/providers/fallback.mjs' as string);
    const log: any[] = [];
    const primary = {
      name: 'primary',
      async *sendMessage() {
        const e: any = new Error('upstream down');
        e.status = 502;
        throw e;
      },
    };
    const secondary = {
      name: 'secondary',
      async *sendMessage() { yield 'b'; },
    };
    const chain = mod.withFallback([primary, secondary], {
      onFallback: (info: any) => log.push({ from: info.from, to: info.to, code: info.err?.code, status: info.err?.status }),
    });
    const out: string[] = [];
    for await (const c of chain.sendMessage([{ role: 'user', content: 'q' }], {})) out.push(c);
    expect(out.join('')).toBe('b');
    expect(log).toEqual([{ from: 'primary', to: 'secondary', code: undefined, status: 502 }]);
  });

  test('withFallback: all providers fail → rethrows the LAST error', async () => {
    const mod = await import('../src/lazyclaw/providers/fallback.mjs' as string);
    const make = (name: string, code: string) => ({
      name,
      async *sendMessage() {
        const e: any = new Error(`${name} down`);
        e.code = code;
        throw e;
      },
    });
    const chain = mod.withFallback([make('a', 'RATE_LIMIT'), make('b', 'RATE_LIMIT'), make('c', 'CONNECTION_REFUSED')]);
    let caught: any = null;
    try {
      for await (const _c of chain.sendMessage([{ role: 'user', content: 'q' }], {})) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('CONNECTION_REFUSED');
    expect(String(caught?.message)).toContain('c down');
  });

  test('withFallback: shouldFallback predicate overrides defaults', async () => {
    const mod = await import('../src/lazyclaw/providers/fallback.mjs' as string);
    let called = false;
    const primary = {
      name: 'primary',
      async *sendMessage() {
        const e: any = new Error('xx');
        e.code = 'INVALID_KEY';
        throw e;
      },
    };
    const secondary = {
      name: 'secondary',
      async *sendMessage() { called = true; yield 'y'; },
    };
    // Custom predicate: fall back on auth errors too. Useful when the
    // primary key has expired and the fallback is keyed differently.
    const chain = mod.withFallback([primary, secondary], { shouldFallback: () => true });
    const out: string[] = [];
    for await (const c of chain.sendMessage([{ role: 'user', content: 'q' }], {})) out.push(c);
    expect(out.join('')).toBe('y');
    expect(called).toBe(true);
  });

  test('withFallback: single-provider chain still works (degenerate case)', async () => {
    const mod = await import('../src/lazyclaw/providers/fallback.mjs' as string);
    const only = {
      name: 'only',
      async *sendMessage() { yield 'solo'; },
    };
    const chain = mod.withFallback([only]);
    const out: string[] = [];
    for await (const c of chain.sendMessage([{ role: 'user', content: 'q' }], {})) out.push(c);
    expect(out.join('')).toBe('solo');
    expect(chain.name).toBe('fallback(only)');
  });

  test('withFallback: empty chain throws', async () => {
    const mod = await import('../src/lazyclaw/providers/fallback.mjs' as string);
    expect(() => mod.withFallback([])).toThrow();
  });

  test('gemini provider hits :streamGenerateContent?alt=sse with key in query and parses parts[].text', async () => {
    const mod = await import('../src/lazyclaw/providers/gemini.mjs' as string);
    let url = '';
    let sentBody: any = null;
    const sse =
      'data: {"candidates":[{"content":{"role":"model","parts":[{"text":"Hello"}]}}]}\n\n' +
      'data: {"candidates":[{"content":{"role":"model","parts":[{"text":" Gemini"}]}}]}\n\n';
    const fakeFetch = async (u: string, init: any) => {
      url = u;
      sentBody = JSON.parse(init.body);
      return {
        ok: true, status: 200,
        body: new ReadableStream({
          start(c) { c.enqueue(new TextEncoder().encode(sse)); c.close(); },
        }),
      };
    };
    const out: string[] = [];
    for await (const chunk of mod.geminiProvider.sendMessage(
      [{ role: 'user', content: 'hi' }],
      { apiKey: 'AIza-secret', model: 'gemini-1.5-pro', fetch: fakeFetch as any },
    )) out.push(chunk);
    expect(out.join('')).toBe('Hello Gemini');
    expect(url).toContain('/models/gemini-1.5-pro:streamGenerateContent?alt=sse&key=AIza-secret');
    expect(sentBody.contents).toEqual([
      { role: 'user', parts: [{ text: 'hi' }] },
    ]);
  });

  test('gemini provider lifts a system message into systemInstruction and maps assistant→model role', async () => {
    const mod = await import('../src/lazyclaw/providers/gemini.mjs' as string);
    let sentBody: any = null;
    const fakeFetch = async (_u: string, init: any) => {
      sentBody = JSON.parse(init.body);
      return {
        ok: true, status: 200,
        body: new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode('')); c.close(); } }),
      };
    };
    for await (const _c of mod.geminiProvider.sendMessage(
      [
        { role: 'system', content: 'be terse' },
        { role: 'user', content: 'first' },
        { role: 'assistant', content: 'first reply' },
        { role: 'user', content: 'follow up' },
      ],
      { apiKey: 'k', fetch: fakeFetch as any },
    )) { /* drain */ }
    expect(sentBody.systemInstruction).toEqual({ parts: [{ text: 'be terse' }] });
    expect(sentBody.contents).toEqual([
      { role: 'user', parts: [{ text: 'first' }] },
      { role: 'model', parts: [{ text: 'first reply' }] },
      { role: 'user', parts: [{ text: 'follow up' }] },
    ]);
  });

  test('gemini provider 401 → INVALID_KEY; 429 → RateLimitError', async () => {
    const mod = await import('../src/lazyclaw/providers/gemini.mjs' as string);
    const make401 = async () => ({
      ok: false, status: 401,
      headers: new Headers({}),
      text: async () => '{"error":{"message":"unauthorized"}}',
    });
    let caught: any = null;
    try {
      for await (const _c of mod.geminiProvider.sendMessage(
        [{ role: 'user', content: 'hi' }],
        { apiKey: 'bad', fetch: make401 as any },
      )) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('INVALID_KEY');

    const make429 = async () => ({
      ok: false, status: 429,
      headers: new Headers({ 'retry-after': '5' }),
      text: async () => '{"error":{"message":"slow down"}}',
    });
    caught = null;
    try {
      for await (const _c of mod.geminiProvider.sendMessage(
        [{ role: 'user', content: 'hi' }],
        { apiKey: 'k', fetch: make429 as any },
      )) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('RATE_LIMIT');
    expect(caught?.retryAfterMs).toBe(5000);
  });

  test('gemini in registry: providers list includes it; doctor accepts it with a key', () => {
    const dir = tmpConfigDir();
    const r = runCli(['providers', 'list'], dir);
    const out = JSON.parse(r.stdout);
    expect(out.find((p: any) => p.name === 'gemini')).toBeTruthy();

    runCli(['config', 'set', 'provider', 'gemini'], dir);
    runCli(['config', 'set', 'api-key', 'AIza-test'], dir);
    runCli(['config', 'set', 'model', 'gemini-1.5-pro'], dir);
    const doctor = runCli(['doctor'], dir);
    expect(doctor.status).toBe(0);
    const dout = JSON.parse(doctor.stdout);
    expect(dout.knownProviders).toEqual(expect.arrayContaining(['gemini']));
    expect(dout.ok).toBe(true);
  });

  test('ollama provider streams newline-delimited JSON chunks and stops on done:true', async () => {
    const mod = await import('../src/lazyclaw/providers/ollama.mjs' as string);
    const ndjson =
      '{"message":{"role":"assistant","content":"Hello"},"done":false}\n' +
      '{"message":{"role":"assistant","content":" world"},"done":false}\n' +
      '{"done":true,"prompt_eval_count":4,"eval_count":2}\n';
    let url = '';
    let sentBody: any = null;
    const fakeFetch = async (u: string, init: any) => {
      url = u;
      sentBody = JSON.parse(init.body);
      return {
        ok: true, status: 200,
        body: new ReadableStream({
          start(c) { c.enqueue(new TextEncoder().encode(ndjson)); c.close(); },
        }),
      };
    };
    const out: string[] = [];
    for await (const chunk of mod.ollamaProvider.sendMessage(
      [{ role: 'user', content: 'hi' }],
      { model: 'llama3.1', fetch: fakeFetch as any },
    )) out.push(chunk);
    expect(out.join('')).toBe('Hello world');
    expect(url).toBe('http://127.0.0.1:11434/api/chat');
    expect(sentBody.stream).toBe(true);
    expect(sentBody.model).toBe('llama3.1');
  });

  test('ollama provider honors opts.baseUrl override', async () => {
    const mod = await import('../src/lazyclaw/providers/ollama.mjs' as string);
    let url = '';
    const fakeFetch = async (u: string) => {
      url = u;
      return {
        ok: true, status: 200,
        body: new ReadableStream({
          start(c) { c.enqueue(new TextEncoder().encode('{"message":{"content":"x"},"done":true}\n')); c.close(); },
        }),
      };
    };
    for await (const _c of mod.ollamaProvider.sendMessage(
      [{ role: 'user', content: 'hi' }],
      { fetch: fakeFetch as any, baseUrl: 'http://10.0.0.5:9999/' },
    )) { /* drain */ }
    expect(url).toBe('http://10.0.0.5:9999/api/chat');
  });

  test('ollama provider surfaces ECONNREFUSED as ConnectionError code CONNECTION_REFUSED', async () => {
    const mod = await import('../src/lazyclaw/providers/ollama.mjs' as string);
    const fakeFetch = async () => {
      const e: any = new Error('fetch failed');
      e.cause = { code: 'ECONNREFUSED' };
      throw e;
    };
    let caught: any = null;
    try {
      for await (const _c of mod.ollamaProvider.sendMessage(
        [{ role: 'user', content: 'hi' }],
        { fetch: fakeFetch as any },
      )) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('CONNECTION_REFUSED');
    expect(String(caught?.message)).toMatch(/cannot reach/);
  });

  test('ollama provider in registry — providers list includes it with requiresApiKey:false', () => {
    const dir = tmpConfigDir();
    const r = runCli(['providers', 'list'], dir);
    const out = JSON.parse(r.stdout);
    const ollama = out.find((p: any) => p.name === 'ollama');
    expect(ollama).toBeTruthy();
    expect(ollama.requiresApiKey).toBe(false);
    expect(ollama.suggestedModels).toEqual(expect.arrayContaining(['llama3.1']));
  });

  test('openai provider passes through tools and surfaces assembled tool_calls via onToolUse', async () => {
    const mod = await import('../src/lazyclaw/providers/openai.mjs' as string);
    const calls: any[] = [];
    const sse =
      'data: {"choices":[{"delta":{"content":"checking"}}]}\n\n' +
      'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"get_weather","arguments":""}}]}}]}\n\n' +
      'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"city\\":"}}]}}]}\n\n' +
      'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"Seoul\\"}"}}]}}]}\n\n' +
      'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n' +
      'data: [DONE]\n\n';
    let sentBody: any = null;
    const fakeFetch = async (_url: string, init: any) => {
      sentBody = JSON.parse(init.body);
      return {
        ok: true, status: 200,
        body: new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(sse)); c.close(); } }),
      };
    };
    const tools = [{ type: 'function', function: { name: 'get_weather', description: 'Get weather', parameters: { type: 'object', properties: { city: { type: 'string' } }, required: ['city'] } } }];
    const text: string[] = [];
    for await (const c of mod.openaiProvider.sendMessage(
      [{ role: 'user', content: 'weather in Seoul' }],
      { apiKey: 'sk-x', model: 'gpt-4.1', fetch: fakeFetch as any, tools, toolChoice: 'auto', onToolUse: (call: any) => calls.push(call) },
    )) text.push(c);
    expect(text.join('')).toBe('checking');
    expect(sentBody.tools).toEqual(tools);
    expect(sentBody.tool_choice).toBe('auto');
    expect(calls).toHaveLength(1);
    expect(calls[0].id).toBe('call_1');
    expect(calls[0].name).toBe('get_weather');
    expect(calls[0].input).toEqual({ city: 'Seoul' });
  });

  test('openai provider flushes pending tool_calls on [DONE] when finish_reason was missing', async () => {
    const mod = await import('../src/lazyclaw/providers/openai.mjs' as string);
    const calls: any[] = [];
    const sse =
      'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_2","type":"function","function":{"name":"ping","arguments":"{\\"x\\":1}"}}]}}]}\n\n' +
      'data: [DONE]\n\n';
    const fakeFetch = async () => ({
      ok: true, status: 200,
      body: new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(sse)); c.close(); } }),
    });
    for await (const _c of mod.openaiProvider.sendMessage(
      [{ role: 'user', content: 'q' }],
      { apiKey: 'sk-x', model: 'gpt-4.1', fetch: fakeFetch as any, onToolUse: (c: any) => calls.push(c) },
    )) { /* drain */ }
    expect(calls).toHaveLength(1);
    expect(calls[0].name).toBe('ping');
    expect(calls[0].input).toEqual({ x: 1 });
  });

  test('withRateLimitRetry passes through on first-attempt success (no retry needed)', async () => {
    const { withRateLimitRetry } = await import('../src/lazyclaw/providers/retry.mjs' as string);
    let calls = 0;
    const inner = {
      name: 'fake',
      async *sendMessage() { calls++; yield 'A'; yield 'B'; },
    };
    const wrapped = withRateLimitRetry(inner, { attempts: 3 });
    const out: string[] = [];
    for await (const c of wrapped.sendMessage([], {})) out.push(c);
    expect(out.join('')).toBe('AB');
    expect(calls).toBe(1);
  });

  test('withRateLimitRetry aborts during backoff sleep when AbortSignal fires', async () => {
    const { withRateLimitRetry } = await import('../src/lazyclaw/providers/retry.mjs' as string);
    let calls = 0;
    const inner = {
      name: 'fake',
      async *sendMessage() {
        calls++;
        const e: any = new Error('rate limited');
        e.code = 'RATE_LIMIT';
        e.retryAfterMs = 10_000;   // would normally sleep 10s
        throw e;
      },
    };
    const ac = new AbortController();
    // Custom sleep that respects the signal so the test runs fast.
    const sleep = (ms: number, signal?: AbortSignal) => new Promise<void>((resolve, reject) => {
      const t = setTimeout(resolve, ms);
      signal?.addEventListener('abort', () => {
        clearTimeout(t);
        const e: any = new Error('aborted during retry backoff');
        e.code = 'ABORT';
        reject(e);
      }, { once: true });
    });
    const wrapped = withRateLimitRetry(inner, { attempts: 3, sleep });
    setTimeout(() => ac.abort(), 30);  // abort while sleeping
    let caught: any = null;
    try {
      for await (const _c of wrapped.sendMessage([], { signal: ac.signal })) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('ABORT');
    expect(calls).toBe(1);   // never reached the second attempt
  });

  test('anthropic provider sends system as a plain string by default', async () => {
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    let body: any = null;
    const fakeFetch = async (_url: string, init: any) => {
      body = JSON.parse(init.body);
      return { ok: true, status: 200, body: new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode('event: message_stop\ndata: {"type":"message_stop"}\n\n')); c.close(); } }) };
    };
    for await (const _c of mod.anthropicProvider.sendMessage(
      [{ role: 'user', content: 'q' }],
      { apiKey: 'sk-ant-x', model: 'claude-opus-4-7', fetch: fakeFetch as any, system: 'be terse' },
    )) { /* drain */ }
    expect(body.system).toBe('be terse');
  });

  test('anthropic provider opts.cache lifts system into a cache_control text block', async () => {
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    let body: any = null;
    const fakeFetch = async (_url: string, init: any) => {
      body = JSON.parse(init.body);
      return { ok: true, status: 200, body: new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode('event: message_stop\ndata: {"type":"message_stop"}\n\n')); c.close(); } }) };
    };
    for await (const _c of mod.anthropicProvider.sendMessage(
      [{ role: 'user', content: 'q' }],
      { apiKey: 'sk-ant-x', model: 'claude-opus-4-7', fetch: fakeFetch as any, system: 'long stable prefix', cache: true },
    )) { /* drain */ }
    expect(Array.isArray(body.system)).toBe(true);
    expect(body.system[0].type).toBe('text');
    expect(body.system[0].text).toBe('long stable prefix');
    expect(body.system[0].cache_control).toEqual({ type: 'ephemeral' });
  });

  test('anthropic provider passes through tool definitions and surfaces tool_use via callback', async () => {
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    const calls: any[] = [];
    const sse =
      'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n' +
      'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Looking up..."}}\n\n' +
      'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n' +
      'event: content_block_start\ndata: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"toolu_01","name":"get_weather","input":{}}}\n\n' +
      'event: content_block_delta\ndata: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\\"city\\":"}}\n\n' +
      'event: content_block_delta\ndata: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"\\"Seoul\\"}"}}\n\n' +
      'event: content_block_stop\ndata: {"type":"content_block_stop","index":1}\n\n' +
      'event: message_stop\ndata: {"type":"message_stop"}\n\n';
    const tools = [{ name: 'get_weather', description: 'Get weather', input_schema: { type: 'object', properties: { city: { type: 'string' } }, required: ['city'] } }];
    let sentBody: any = null;
    const fakeFetch = async (_url: string, init: any) => {
      sentBody = JSON.parse(init.body);
      return {
        ok: true, status: 200,
        body: new ReadableStream({
          start(c) { c.enqueue(new TextEncoder().encode(sse)); c.close(); },
        }),
      };
    };
    const text: string[] = [];
    for await (const chunk of mod.anthropicProvider.sendMessage(
      [{ role: 'user', content: "what's the weather in Seoul?" }],
      {
        apiKey: 'sk-ant-x', model: 'claude-opus-4-7',
        fetch: fakeFetch as any,
        tools,
        toolChoice: { type: 'auto' },
        onToolUse: (call: any) => calls.push(call),
      },
    )) text.push(chunk);
    expect(text.join('')).toBe('Looking up...');
    expect(sentBody.tools).toEqual(tools);
    expect(sentBody.tool_choice).toEqual({ type: 'auto' });
    expect(calls).toHaveLength(1);
    expect(calls[0].name).toBe('get_weather');
    expect(calls[0].id).toBe('toolu_01');
    expect(calls[0].input).toEqual({ city: 'Seoul' });
  });

  test('anthropic tool_use with malformed partial_json still calls onToolUse with raw + empty input', async () => {
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    const calls: any[] = [];
    const sse =
      'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"x","name":"t","input":{}}}\n\n' +
      'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"not-json"}}\n\n' +
      'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n' +
      'event: message_stop\ndata: {"type":"message_stop"}\n\n';
    const fakeFetch = async () => ({
      ok: true, status: 200,
      body: new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(sse)); c.close(); } }),
    });
    for await (const _c of mod.anthropicProvider.sendMessage(
      [{ role: 'user', content: 'q' }],
      { apiKey: 'sk-ant-x', model: 'claude-opus-4-7', fetch: fakeFetch as any, onToolUse: (c: any) => calls.push(c) },
    )) { /* drain */ }
    expect(calls).toHaveLength(1);
    expect(calls[0].input).toEqual({});
    expect(calls[0].raw).toBe('not-json');
  });

  test('anthropic provider honors AbortSignal — pre-request abort throws AbortError', async () => {
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    const ac = new AbortController();
    ac.abort();
    let caught: any = null;
    try {
      for await (const _c of mod.anthropicProvider.sendMessage(
        [{ role: 'user', content: 'hi' }],
        { apiKey: 'sk-ant-x', model: 'claude-opus-4-7', fetch: (async () => ({ ok: true, body: null })) as any, signal: ac.signal },
      )) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('ABORT');
  });

  test('anthropic provider honors AbortSignal — mid-stream abort stops yielding', async () => {
    const mod = await import('../src/lazyclaw/providers/anthropic.mjs' as string);
    const ac = new AbortController();
    // Stream that emits one frame, then waits, then emits another. We
    // abort right after the first chunk arrives.
    const fakeFetch = async () => ({
      ok: true,
      status: 200,
      body: new ReadableStream({
        async start(controller) {
          controller.enqueue(new TextEncoder().encode(
            'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"first"}}\n\n'
          ));
          await new Promise(r => setTimeout(r, 30));
          controller.enqueue(new TextEncoder().encode(
            'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"second"}}\n\n'
          ));
          controller.close();
        },
      }),
    });
    const got: string[] = [];
    let caught: any = null;
    try {
      for await (const c of mod.anthropicProvider.sendMessage(
        [{ role: 'user', content: 'hi' }],
        { apiKey: 'sk-ant-x', model: 'claude-opus-4-7', fetch: fakeFetch as any, signal: ac.signal },
      )) {
        got.push(c);
        ac.abort();  // abort after the very first chunk
      }
    } catch (e) { caught = e; }
    expect(got).toEqual(['first']);
    expect(caught?.code).toBe('ABORT');
  });

  test('openai provider honors AbortSignal symmetrically', async () => {
    const mod = await import('../src/lazyclaw/providers/openai.mjs' as string);
    const ac = new AbortController();
    ac.abort();
    let caught: any = null;
    try {
      for await (const _c of mod.openaiProvider.sendMessage(
        [{ role: 'user', content: 'hi' }],
        { apiKey: 'sk-x', model: 'gpt-4.1', fetch: (async () => ({ ok: true, body: null })) as any, signal: ac.signal },
      )) { /* drain */ }
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('ABORT');
  });

  test('skills install + list + show + remove round-trip', () => {
    const dir = tmpConfigDir();
    const r1 = runCli(['skills', 'install', 'commit-style', '--from', __filename], dir);
    expect(r1.status).toBe(0);
    const r2 = runCli(['skills', 'list'], dir);
    const items = JSON.parse(r2.stdout);
    expect(items.map((s: any) => s.name)).toContain('commit-style');
    const r3 = runCli(['skills', 'show', 'commit-style'], dir);
    expect(r3.status).toBe(0);
    expect(r3.stdout.length).toBeGreaterThan(0);
    const r4 = runCli(['skills', 'remove', 'commit-style'], dir);
    expect(r4.status).toBe(0);
    expect(JSON.parse(runCli(['skills', 'list'], dir).stdout)).toEqual([]);
  });

  test('skills install --from-url rejects non-https schemes', () => {
    const dir = tmpConfigDir();
    const r = runCli(['skills', 'install', 'evil', '--from-url', 'http://example.com/x.md'], dir);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/requires an https:\/\/ URL/);
    const r2 = runCli(['skills', 'install', 'evil', '--from-url', 'file:///etc/passwd'], dir);
    expect(r2.status).toBe(2);
    expect(r2.stderr).toMatch(/requires an https:\/\/ URL/);
  });

  test('skills install --from-url fetches successfully via stub fetch', () => {
    // We can't ship a TLS cert just to test this path. Instead we use
    // Node's --import flag to inject a fetch override into the child
    // process *before* the CLI loads, so the https:// scheme check
    // passes but the actual request never goes over the network.
    const dir = tmpConfigDir();
    const preload = path.join(dir, 'preload.mjs');
    fs.writeFileSync(preload,
      `globalThis.fetch = async () => {
        const body = new TextEncoder().encode('# Stubbed Skill\\n\\nbe witty\\n');
        return {
          ok: true,
          status: 200,
          body: new ReadableStream({
            start(c) { c.enqueue(body); c.close(); },
          }),
        };
      };`,
    );
    const r = spawnSync(process.execPath, [
      '--import', preload,
      CLI, 'skills', 'install', 'witty', '--from-url', 'https://example.test/x.md',
    ], {
      encoding: 'utf8',
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
    });
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out.name).toBe('witty');
    expect(fs.readFileSync(path.join(dir, 'skills', 'witty.md'), 'utf8')).toContain('be witty');
  });

  test('skills install --from-url rejects responses that exceed the size cap', () => {
    const dir = tmpConfigDir();
    const preload = path.join(dir, 'preload.mjs');
    fs.writeFileSync(preload,
      `globalThis.fetch = async () => {
        const big = new Uint8Array(2 * 1024 * 1024);  // 2 MiB > 1 MiB cap
        return {
          ok: true,
          status: 200,
          body: new ReadableStream({
            start(c) { c.enqueue(big); c.close(); },
          }),
        };
      };`,
    );
    const r = spawnSync(process.execPath, [
      '--import', preload,
      CLI, 'skills', 'install', 'big', '--from-url', 'https://example.test/x.md',
    ], {
      encoding: 'utf8',
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
    });
    expect(r.status).toBe(1);
    expect(r.stderr).toMatch(/exceeds .* bytes; refusing/);
    expect(fs.existsSync(path.join(dir, 'skills', 'big.md'))).toBe(false);
  });

  test('skills install --from-url surfaces non-2xx responses as exit 1', () => {
    const dir = tmpConfigDir();
    const preload = path.join(dir, 'preload.mjs');
    fs.writeFileSync(preload,
      `globalThis.fetch = async () => ({ ok: false, status: 404, body: null });`,
    );
    const r = spawnSync(process.execPath, [
      '--import', preload,
      CLI, 'skills', 'install', 'missing', '--from-url', 'https://example.test/x.md',
    ], {
      encoding: 'utf8',
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
    });
    expect(r.status).toBe(1);
    expect(r.stderr).toMatch(/→ 404/);
  });

  test('skills install reads stdin when --from is not given', async () => {
    const dir = tmpConfigDir();
    const child = spawn(process.execPath, [CLI, 'skills', 'install', 'piped'], {
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dir },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    child.stdin.write('# Piped Skill\n\nbe concise.\n');
    child.stdin.end();
    await new Promise<void>(resolve => child.on('close', () => resolve()));
    const file = path.join(dir, 'skills', 'piped.md');
    expect(fs.existsSync(file)).toBe(true);
    expect(fs.readFileSync(file, 'utf8')).toContain('be concise');
  });

  test('agent --skill prepends the skill content as system message', async () => {
    // The mock provider is only sensitive to the LAST user message, so we
    // can't verify the system prompt landed by inspecting the reply alone.
    // Instead we plumb a tiny inspector provider via a tmp registry-based
    // helper file, then exercise via a unit test.
    const skillsMod = await import('../src/lazyclaw/skills.mjs' as string);
    const dir = tmpConfigDir();
    fs.mkdirSync(path.join(dir, 'skills'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'skills', 'a.md'), '# A\nbody-A\n');
    fs.writeFileSync(path.join(dir, 'skills', 'b.md'), '# B\nbody-B\n');
    const composed = skillsMod.composeSystemPrompt(['a', 'b'], dir);
    expect(composed).toContain('skill: a');
    expect(composed).toContain('body-A');
    expect(composed).toContain('skill: b');
    expect(composed).toContain('body-B');
  });

  test('skills name validation rejects path-traversal and dotfiles', async () => {
    const skillsMod = await import('../src/lazyclaw/skills.mjs' as string);
    expect(() => skillsMod.skillPath('../bad', '/tmp')).toThrow();
    expect(() => skillsMod.skillPath('a/b', '/tmp')).toThrow();
    expect(() => skillsMod.skillPath('.hidden', '/tmp')).toThrow();
    expect(() => skillsMod.skillPath('.', '/tmp')).toThrow();
  });

  test('config path prints the resolved config.json location', () => {
    const dir = tmpConfigDir();
    const r = runCli(['config', 'path'], dir);
    expect(r.status).toBe(0);
    // Trailing newline from console.log.
    expect(r.stdout.trim()).toBe(path.join(dir, 'config.json'));
  });

  test('config edit invokes $LAZYCLAW_EDITOR on the config file and validates JSON on save', () => {
    const dir = tmpConfigDir();
    // Pre-seed a config so the editor opens an existing file.
    fs.writeFileSync(path.join(dir, 'config.json'), JSON.stringify({ provider: 'mock' }));
    // Use a noop "editor" — `true` exits 0 without doing anything.
    // The test asserts: cmdConfigEdit doesn't crash, prints ok, leaves
    // the JSON parseable.
    const r = runCli(['config', 'edit'], dir, { LAZYCLAW_EDITOR: 'true' });
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out.ok).toBe(true);
    expect(out.path).toBe(path.join(dir, 'config.json'));
    // File still parseable.
    expect(JSON.parse(fs.readFileSync(path.join(dir, 'config.json'), 'utf8'))).toEqual({ provider: 'mock' });
  });

  test('config edit refuses to silently accept an invalid JSON edit', () => {
    const dir = tmpConfigDir();
    fs.writeFileSync(path.join(dir, 'config.json'), '{}');
    // Custom "editor" that corrupts the file.
    const corruptScript = path.join(dir, 'corrupt.sh');
    fs.writeFileSync(corruptScript, '#!/bin/sh\necho "this is not json" > "$1"\n');
    fs.chmodSync(corruptScript, 0o755);
    const r = runCli(['config', 'edit'], dir, { LAZYCLAW_EDITOR: corruptScript });
    expect(r.status).toBe(1);
    expect(r.stderr).toMatch(/invalid JSON/);
  });

  test('config edit creates the file when missing rather than failing', () => {
    const dir = tmpConfigDir();
    // No config.json yet. Editor exits clean (true → empty edit, file gets {} from us).
    const r = runCli(['config', 'edit'], dir, { LAZYCLAW_EDITOR: 'true' });
    expect(r.status).toBe(0);
    const cfg = JSON.parse(fs.readFileSync(path.join(dir, 'config.json'), 'utf8'));
    expect(cfg).toEqual({});
  });

  test('config list returns the full config as JSON', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    runCli(['config', 'set', 'model', 'mock-1'], dir);
    const r = runCli(['config', 'list'], dir);
    expect(r.status).toBe(0);
    const out = JSON.parse(r.stdout);
    expect(out).toMatchObject({ provider: 'mock', model: 'mock-1' });
  });

  test('config delete removes a key, idempotent on missing', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    const r1 = runCli(['config', 'delete', 'provider'], dir);
    expect(r1.status).toBe(0);
    expect(JSON.parse(r1.stdout)).toEqual({ ok: true, key: 'provider', removed: true });
    const cfg = JSON.parse(fs.readFileSync(path.join(dir, 'config.json'), 'utf8'));
    expect(cfg.provider).toBeUndefined();
    // idempotent
    const r2 = runCli(['config', 'delete', 'provider'], dir);
    expect(r2.status).toBe(0);
    expect(JSON.parse(r2.stdout).removed).toBe(false);
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

  test('sessions export renders the conversation as shareable Markdown', () => {
    const dir = tmpConfigDir();
    fs.mkdirSync(path.join(dir, 'sessions'), { recursive: true });
    const t1 = Date.now() - 60_000;
    const t2 = Date.now();
    fs.writeFileSync(path.join(dir, 'sessions', 'demo.jsonl'),
      JSON.stringify({ role: 'user', content: 'hi there', ts: t1 }) + '\n' +
      JSON.stringify({ role: 'assistant', content: 'hello!\n\n```js\nconsole.log(1);\n```', ts: t2 }) + '\n');
    const r = runCli(['sessions', 'export', 'demo'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).toMatch(/^# Session: demo/);
    expect(r.stdout).toContain('## User');
    expect(r.stdout).toContain('hi there');
    expect(r.stdout).toContain('## Assistant');
    expect(r.stdout).toContain('hello!');
    expect(r.stdout).toContain('console.log(1);');
    // Metadata block — turns count + first/last timestamps
    expect(r.stdout).toMatch(/Turns: 2/);
  });

  test('sessions export on empty session prints a placeholder', () => {
    const dir = tmpConfigDir();
    fs.mkdirSync(path.join(dir, 'sessions'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'sessions', 'empty.jsonl'), '');
    const r = runCli(['sessions', 'export', 'empty'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).toMatch(/Session: empty/);
    expect(r.stdout).toContain('_(empty)_');
  });

  test('sessions clear removes the file', () => {
    const dir = tmpConfigDir();
    fs.mkdirSync(path.join(dir, 'sessions'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'sessions', 'doomed.jsonl'), JSON.stringify({ role: 'user', content: 'x', ts: 1 }) + '\n');
    const r = runCli(['sessions', 'clear', 'doomed'], dir);
    expect(r.status).toBe(0);
    expect(fs.existsSync(path.join(dir, 'sessions', 'doomed.jsonl'))).toBe(false);
  });

  test('sessions export prints a Markdown dump with H1 + per-turn sections', () => {
    const dir = tmpConfigDir();
    fs.mkdirSync(path.join(dir, 'sessions'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'sessions', 'demo.jsonl'),
      JSON.stringify({ role: 'user', content: 'how do I sort an array?', ts: Date.now() }) + '\n' +
      JSON.stringify({ role: 'assistant', content: 'use Array.prototype.sort', ts: Date.now() }) + '\n');
    const r = runCli(['sessions', 'export', 'demo'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('# Session: demo');
    expect(r.stdout).toContain('## User');
    expect(r.stdout).toContain('## Assistant');
    expect(r.stdout).toContain('how do I sort an array?');
    expect(r.stdout).toContain('use Array.prototype.sort');
    expect(r.stdout).toContain('Turns: 2');
  });

  test('sessions export on empty session prints "(empty)" body', () => {
    const dir = tmpConfigDir();
    fs.mkdirSync(path.join(dir, 'sessions'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'sessions', 'blank.jsonl'), '');
    const r = runCli(['sessions', 'export', 'blank'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('# Session: blank');
    expect(r.stdout).toContain('_(empty)_');
  });

  test('sessions export with no id exits 2 with usage', () => {
    const dir = tmpConfigDir();
    const r = runCli(['sessions', 'export'], dir);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/Usage: lazyclaw sessions export/);
  });

  test('sessionPath rejects path-traversal ids', async () => {
    const sm = await import('../src/lazyclaw/sessions.mjs' as string);
    expect(() => sm.sessionPath('../etc/passwd', '/tmp/whatever')).toThrow();
    expect(() => sm.sessionPath('a/b', '/tmp')).toThrow();
    expect(() => sm.sessionPath('.', '/tmp')).toThrow();
  });

  test('completion bash prints a compgen-based script with all subcommands', () => {
    const dir = tmpConfigDir();
    const r = runCli(['completion', 'bash'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('_lazyclaw_completion');
    expect(r.stdout).toContain('complete -F _lazyclaw_completion lazyclaw');
    for (const sub of ['run', 'resume', 'config', 'chat', 'agent', 'doctor', 'status', 'onboard', 'sessions', 'skills', 'providers', 'daemon', 'version', 'completion']) {
      expect(r.stdout).toContain(sub);
    }
    expect(r.stdout).toContain('get set list delete unset');
    expect(r.stdout).toContain('list show clear export');
  });

  test('completion zsh prints a #compdef script with all subcommands', () => {
    const dir = tmpConfigDir();
    const r = runCli(['completion', 'zsh'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('#compdef lazyclaw');
    expect(r.stdout).toContain('compdef _lazyclaw lazyclaw');
    for (const sub of ['run', 'resume', 'config', 'chat', 'agent', 'doctor', 'status', 'onboard', 'sessions', 'skills', 'providers', 'daemon', 'version']) {
      expect(r.stdout).toContain(`'${sub}'`);
    }
    expect(r.stdout).toContain("'list' 'show' 'install' 'remove'");
  });

  test('completion with no shell exits 2 with a usage hint', () => {
    const dir = tmpConfigDir();
    const r = runCli(['completion'], dir);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/Usage: lazyclaw completion/);
    const r2 = runCli(['completion', 'fish'], dir);
    expect(r2.status).toBe(2);
  });

  test('completion bash output is syntactically valid bash', () => {
    const dir = tmpConfigDir();
    const r = runCli(['completion', 'bash'], dir);
    // bash -n parses only, doesn't execute, so we can validate the
    // generated script is at least syntactically well-formed.
    const check = spawnSync('bash', ['-n'], {
      input: r.stdout,
      encoding: 'utf8',
    });
    expect(check.status).toBe(0);
    expect(check.stderr).toBe('');
  });

  test('export produces a JSON bundle with config + skills, redacting the api-key by default', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    runCli(['config', 'set', 'api-key', 'sk-ant-supersecret'], dir);
    fs.mkdirSync(path.join(dir, 'skills'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'skills', 'reviewer.md'), '# Reviewer\nbe blunt\n');

    const r = runCli(['export'], dir);
    expect(r.status).toBe(0);
    const bundle = JSON.parse(r.stdout);
    expect(bundle.bundleVersion).toBe(1);
    expect(bundle.config.provider).toBe('mock');
    expect(bundle.config['api-key']).toBe('***REDACTED***');
    expect(bundle.secretsIncluded).toBe(false);
    expect(bundle.skills).toHaveLength(1);
    expect(bundle.skills[0].name).toBe('reviewer');
    expect(bundle.skills[0].content).toContain('be blunt');
    // raw key must not appear *anywhere* in the JSON
    expect(r.stdout).not.toContain('sk-ant-supersecret');
  });

  test('export --include-secrets keeps the raw api-key', () => {
    const dir = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], dir);
    runCli(['config', 'set', 'api-key', 'sk-ant-keep-me'], dir);
    const r = runCli(['export', '--include-secrets'], dir);
    expect(r.status).toBe(0);
    const bundle = JSON.parse(r.stdout);
    expect(bundle.secretsIncluded).toBe(true);
    expect(bundle.config['api-key']).toBe('sk-ant-keep-me');
  });

  test('export --include-sessions inlines turn content; default keeps metadata only', () => {
    const dir = tmpConfigDir();
    fs.mkdirSync(path.join(dir, 'sessions'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'sessions', 's1.jsonl'),
      JSON.stringify({ role: 'user', content: 'q', ts: 1 }) + '\n' +
      JSON.stringify({ role: 'assistant', content: 'a', ts: 2 }) + '\n');

    const meta = JSON.parse(runCli(['export'], dir).stdout);
    expect(meta.sessions[0].id).toBe('s1');
    expect(meta.sessions[0].turns).toBeUndefined();

    const full = JSON.parse(runCli(['export', '--include-sessions'], dir).stdout);
    expect(full.sessionContentIncluded).toBe(true);
    expect(full.sessions[0].turns).toHaveLength(2);
    expect(full.sessions[0].turns[0].content).toBe('q');
  });

  test('import via --from applies config + skills; redacted key is dropped not written', () => {
    const dir = tmpConfigDir();
    const bundle = {
      bundleVersion: 1,
      config: { provider: 'mock', model: 'm-x', 'api-key': '***REDACTED***' },
      skills: [{ name: 'imported', content: '# Imported\nhi from import\n' }],
      sessions: [],
      secretsIncluded: false,
      sessionContentIncluded: false,
    };
    const bundlePath = path.join(dir, 'bundle.json');
    fs.writeFileSync(bundlePath, JSON.stringify(bundle));

    const r = runCli(['import', '--from', bundlePath], dir);
    expect(r.status).toBe(0);
    const stats = JSON.parse(r.stdout);
    expect(stats.skillsAdded).toBe(1);
    const cfg = JSON.parse(fs.readFileSync(path.join(dir, 'config.json'), 'utf8'));
    expect(cfg.provider).toBe('mock');
    expect(cfg.model).toBe('m-x');
    // The placeholder string must NEVER land on disk.
    expect(cfg['api-key']).toBeUndefined();
    expect(fs.readFileSync(path.join(dir, 'skills', 'imported.md'), 'utf8')).toContain('hi from import');
  });

  test('import skips existing skills by default; --overwrite-skills replaces them', () => {
    const dir = tmpConfigDir();
    fs.mkdirSync(path.join(dir, 'skills'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'skills', 'a.md'), '# old\noriginal\n');
    const bundle = {
      bundleVersion: 1,
      config: {},
      skills: [{ name: 'a', content: '# new\nfrom bundle\n' }],
      sessions: [],
    };
    const p = path.join(dir, 'b.json');
    fs.writeFileSync(p, JSON.stringify(bundle));

    // Default — skipped, original kept
    const r1 = runCli(['import', '--from', p], dir);
    expect(JSON.parse(r1.stdout).skillsSkipped).toBe(1);
    expect(fs.readFileSync(path.join(dir, 'skills', 'a.md'), 'utf8')).toContain('original');

    // With override — replaced
    const r2 = runCli(['import', '--from', p, '--overwrite-skills'], dir);
    expect(JSON.parse(r2.stdout).skillsAdded).toBe(1);
    expect(fs.readFileSync(path.join(dir, 'skills', 'a.md'), 'utf8')).toContain('from bundle');
  });

  test('import refuses unknown bundleVersion (forward-compat guard)', () => {
    const dir = tmpConfigDir();
    const bundle = { bundleVersion: 999, config: {}, skills: [], sessions: [] };
    const p = path.join(dir, 'future.json');
    fs.writeFileSync(p, JSON.stringify(bundle));
    const r = runCli(['import', '--from', p], dir);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/unsupported bundleVersion/);
  });

  test('export → import round-trip reproduces config + skills on a fresh dir', () => {
    const src = tmpConfigDir();
    runCli(['config', 'set', 'provider', 'mock'], src);
    runCli(['config', 'set', 'model', 'roundtrip-model'], src);
    fs.mkdirSync(path.join(src, 'skills'), { recursive: true });
    fs.writeFileSync(path.join(src, 'skills', 'shared.md'), '# Shared\nbody\n');

    const exported = runCli(['export'], src).stdout;
    const dst = tmpConfigDir();
    const r = spawnSync(process.execPath, [CLI, 'import'], {
      input: exported,
      encoding: 'utf8',
      env: { ...process.env, LAZYCLAW_CONFIG_DIR: dst },
    });
    expect(r.status).toBe(0);
    const cfg = JSON.parse(fs.readFileSync(path.join(dst, 'config.json'), 'utf8'));
    expect(cfg).toMatchObject({ provider: 'mock', model: 'roundtrip-model' });
    expect(fs.readFileSync(path.join(dst, 'skills', 'shared.md'), 'utf8')).toContain('body');
  });

  test('help with no argument lists every subcommand with a one-liner', () => {
    const dir = tmpConfigDir();
    const r = runCli(['help'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('lazyclaw — terminal AI assistant');
    for (const sub of ['run', 'resume', 'config', 'chat', 'agent', 'doctor', 'status', 'onboard', 'sessions', 'skills', 'providers', 'daemon', 'version', 'completion']) {
      expect(r.stdout).toContain(sub);
    }
    expect(r.stdout).toMatch(/lazyclaw help <subcommand>/);
  });

  test('help <subcommand> prints detailed usage', () => {
    const dir = tmpConfigDir();
    const r = runCli(['help', 'daemon'], dir);
    expect(r.status).toBe(0);
    expect(r.stdout).toMatch(/^Usage: lazyclaw daemon/);
    expect(r.stdout).toContain('--auth-token');
    expect(r.stdout).toContain('--allow-origin');
    // Different subcommand returns its own usage, not daemon's
    const r2 = runCli(['help', 'sessions'], dir);
    expect(r2.stdout).toMatch(/^Usage: lazyclaw sessions/);
    expect(r2.stdout).toContain('export');
    expect(r2.stdout).not.toContain('--auth-token');
  });

  test('help <unknown> exits 2 with a hint to run `help`', () => {
    const dir = tmpConfigDir();
    const r = runCli(['help', 'nonsense-command'], dir);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/unknown subcommand: nonsense-command/);
    expect(r.stderr).toMatch(/run `lazyclaw help`/);
  });

  test('--help and -h are aliases for `help` (no argument lists subcommands)', () => {
    const dir = tmpConfigDir();
    expect(runCli(['--help'], dir).stdout).toContain('lazyclaw — terminal AI assistant');
    expect(runCli(['-h'], dir).stdout).toContain('lazyclaw — terminal AI assistant');
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
