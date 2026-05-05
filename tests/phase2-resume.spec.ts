import { test, expect } from '@playwright/test';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { spawnSync } from 'node:child_process';

import {
  runPersistent,
  runPersistentDag,
  loadState,
  statePath,
} from '../src/lazyclaw/workflow/persistent.mjs';

const REPO_ROOT = process.cwd();

interface PNode {
  id: string;
  type: string;
  execute(input: unknown, opts?: { signal?: AbortSignal }): Promise<unknown>;
}

function tmpDir(prefix: string): string {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), `lc-${prefix}-`));
  return d;
}

function makeChain(count: number, opts: { failAt?: number; rec?: string[] } = {}): PNode[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `n${i + 1}`,
    type: 'test',
    async execute(input: unknown) {
      opts.rec?.push(`n${i + 1}`);
      if (opts.failAt && i + 1 === opts.failAt) throw new Error(`fail@n${opts.failAt}`);
      return ((typeof input === 'number' ? input : 0) + 1);
    },
  }));
}

test.describe('Phase 2 — Auto-resume', () => {
  test('state persists to disk before and after each node', async () => {
    const dir = tmpDir('p2a');
    const sid = 'sess-persist-1';
    const seenAfterEach: string[][] = [];
    const nodes: PNode[] = Array.from({ length: 3 }, (_, i) => ({
      id: `n${i + 1}`,
      type: 'test',
      async execute() {
        // While running this node, file must exist with status=running for it.
        const s = loadState(sid, dir);
        seenAfterEach.push(Object.entries(s!.nodes).map(([id, v]) => `${id}:${v.status}`));
        return i;
      },
    }));
    const r = await runPersistent(nodes, { sessionId: sid, dir });
    expect(r.success).toBe(true);
    expect(fs.existsSync(statePath(sid, dir))).toBe(true);
    // While n1 was running, n1 status was 'running'.
    expect(seenAfterEach[0]).toContain('n1:running');
    // After full run, all success.
    const finalState = loadState(sid, dir)!;
    for (const id of ['n1', 'n2', 'n3']) {
      expect(finalState.nodes[id].status).toBe('success');
    }
  });

  test('resume after simulated kill skips completed nodes and re-runs interrupted', async () => {
    const dir = tmpDir('p2b');
    const sid = 'sess-resume-1';

    // First run: nodes 1..5 succeed, then we throw to simulate kill before 6.
    const rec1: string[] = [];
    const nodesRun1: PNode[] = makeChain(10, { failAt: 6, rec: rec1 });
    const r1 = await runPersistent(nodesRun1, { sessionId: sid, dir });
    expect(r1.success).toBe(false);
    expect(rec1).toEqual(['n1', 'n2', 'n3', 'n4', 'n5', 'n6']);

    // Simulate "kill mid-flight" by hand-editing n5 back to running, n6 absent.
    const mid = loadState(sid, dir)!;
    mid.nodes['n5'] = { status: 'running', attempts: 1 };
    mid.nodes['n6'] = { status: 'pending' };
    fs.writeFileSync(statePath(sid, dir), JSON.stringify(mid, null, 2));

    // Second run: a fresh node set with no failure injection. Resume must
    // re-run the interrupted n5 cleanly and continue 6..10. Nodes 1..4 must
    // be skipped (status='success').
    const rec2: string[] = [];
    const nodesRun2: PNode[] = makeChain(10, { rec: rec2 });
    const r2 = await runPersistent(nodesRun2, { sessionId: sid, dir });
    expect(r2.success).toBe(true);
    // Completed nodes do not re-execute.
    for (const skipped of ['n1', 'n2', 'n3', 'n4']) {
      expect(rec2).not.toContain(skipped);
    }
    // Interrupted node + remainder did execute.
    expect(rec2).toEqual(['n5', 'n6', 'n7', 'n8', 'n9', 'n10']);
    expect(r2.executedNodes).toEqual(['n5', 'n6', 'n7', 'n8', 'n9', 'n10']);
  });

  test('timeout retries with exponential backoff (max 3) and gives up', async () => {
    const dir = tmpDir('p2c');
    const sid = 'sess-timeout-1';
    let calls = 0;
    const slept: number[] = [];
    const nodes: PNode[] = [
      {
        id: 'slow',
        type: 'test',
        async execute() {
          calls++;
          // Always exceed timeout window.
          await new Promise(r => setTimeout(r, 50));
          return 'never';
        },
      },
    ];
    const r = await runPersistent(nodes, {
      sessionId: sid,
      dir,
      timeoutMs: 5,
      baseDelayMs: 10,
      maxRetries: 3,
      sleep: async (ms: number) => { slept.push(ms); /* skip real sleep */ },
    });
    expect(r.success).toBe(false);
    expect(calls).toBe(3); // 3 attempts
    // Backoff: 10, 20 (between attempts 1→2 and 2→3). No sleep after final fail.
    expect(slept).toEqual([10, 20]);
    expect(r.state.nodes.slow.status).toBe('failed');
    expect(r.state.nodes.slow.attempts).toBe(3);
  });

  test('CLI resume command continues from checkpoint', async () => {
    const dir = tmpDir('p2d');
    const sid = 'sess-cli-1';
    const sentinel = path.join(dir, 'cli-rec.txt');

    // Workflow fixture: writes its node id to sentinel. node 4 throws on
    // first invocation only (controlled by env var), then on resume succeeds.
    const wfFile = path.join(dir, 'wf.mjs');
    fs.writeFileSync(wfFile, `
      import fs from 'node:fs';
      const SENT = ${JSON.stringify(sentinel)};
      const FAIL = process.env.LC_FAIL_AT;
      function append(line){ fs.appendFileSync(SENT, line + '\\n'); }
      export const nodes = Array.from({length:8}, (_,i) => ({
        id: 'n' + (i+1),
        type: 'test',
        async execute(input){
          append('n'+(i+1));
          if (FAIL && String(i+1) === FAIL) throw new Error('forced');
          return (typeof input === 'number' ? input : 0) + 1;
        },
      }));
    `);

    const cli = path.join(REPO_ROOT, 'src/lazyclaw/cli.mjs');

    // First run: fail at node 4.
    const r1 = spawnSync(process.execPath, [cli, 'run', sid, wfFile, '--dir', dir], {
      encoding: 'utf8',
      env: { ...process.env, LC_FAIL_AT: '4' },
    });
    expect(r1.status).toBe(1);
    const recAfter1 = fs.readFileSync(sentinel, 'utf8').trim().split('\n');
    expect(recAfter1).toEqual(['n1', 'n2', 'n3', 'n4']);
    const s1 = loadState(sid, dir)!;
    expect(s1.nodes.n4.status).toBe('failed');
    expect(s1.nodes.n3.status).toBe('success');

    // Resume: no failure injection now.
    const r2 = spawnSync(process.execPath, [cli, 'resume', sid, wfFile, '--dir', dir], {
      encoding: 'utf8',
      env: { ...process.env },
    });
    expect(r2.status).toBe(0);
    const recAfter2 = fs.readFileSync(sentinel, 'utf8').trim().split('\n');
    // n1..n3 must NOT have re-executed; n4..n8 must have.
    expect(recAfter2).toEqual(['n1', 'n2', 'n3', 'n4', 'n4', 'n5', 'n6', 'n7', 'n8']);
    const s2 = loadState(sid, dir)!;
    for (const id of ['n1', 'n2', 'n3', 'n4', 'n5', 'n6', 'n7', 'n8']) {
      expect(s2.nodes[id].status).toBe('success');
    }
  });

  test('runPersistentDag: 4-node diamond runs to completion and persists state per node', async () => {
    const dir = tmpDir('pdag');
    const sid = 'diamond-1';
    const nodes = [
      { id: 'a',     deps: [],            async execute() { return 'A'; } },
      { id: 'b',     deps: ['a'],         async execute(input: any) { return `B:${input.a}`; } },
      { id: 'c',     deps: ['a'],         async execute(input: any) { return `C:${input.a}`; } },
      { id: 'merge', deps: ['b', 'c'],    async execute(input: any) { return `M:${input.b}+${input.c}`; } },
    ];
    const r = await runPersistentDag(nodes, { sessionId: sid, dir });
    expect(r.success).toBe(true);
    expect(r.executedNodes.sort()).toEqual(['a', 'b', 'c', 'merge']);
    const s = loadState(sid, dir)!;
    expect(s.nodes.merge.output).toBe('M:B:A+C:A');
    for (const id of ['a', 'b', 'c', 'merge']) {
      expect(s.nodes[id].status).toBe('success');
    }
  });

  test('runPersistentDag: resume after a failed node skips success nodes and retries the failed one', async () => {
    const dir = tmpDir('pdag-resume');
    const sid = 'flaky-1';
    let attempt = 0;
    const nodes = [
      { id: 'a',     deps: [],         async execute() { return 'A'; } },
      // b fails on the first attempt, succeeds the second.
      {
        id: 'b',
        deps: ['a'],
        async execute(input: any) {
          attempt += 1;
          if (attempt === 1) throw new Error('flaky');
          return `B:${input.a}`;
        },
      },
      { id: 'c',     deps: ['a', 'b'], async execute(input: any) { return `C:${input.a}/${input.b}`; } },
    ];
    const first = await runPersistentDag(nodes, { sessionId: sid, dir });
    expect(first.success).toBe(false);
    expect(first.failedAt).toBe('b');
    const s1 = loadState(sid, dir)!;
    expect(s1.nodes.a.status).toBe('success');
    expect(s1.nodes.b.status).toBe('failed');
    expect(s1.nodes.c?.status ?? 'pending').toBe('pending');  // never started

    // Resume — same nodes array; b will pass on the second attempt.
    const second = await runPersistentDag(nodes, { sessionId: sid, dir });
    expect(second.success).toBe(true);
    expect(second.executedNodes.sort()).toEqual(['b', 'c']);  // a skipped
    const s2 = loadState(sid, dir)!;
    expect(s2.nodes.a.status).toBe('success');
    expect(s2.nodes.b.status).toBe('success');
    expect(s2.nodes.c.status).toBe('success');
    expect(s2.nodes.c.output).toBe('C:A/B:A');
  });

  test('runPersistentDag: cycle is detected before any node runs', async () => {
    const dir = tmpDir('pdag-cycle');
    const sid = 'cyc-1';
    let executed = false;
    const nodes = [
      { id: 'a', deps: ['b'], async execute() { executed = true; return 1; } },
      { id: 'b', deps: ['a'], async execute() { executed = true; return 2; } },
    ];
    const r = await runPersistentDag(nodes, { sessionId: sid, dir });
    expect(r.success).toBe(false);
    expect(r.error).toMatch(/cycle/);
    expect(executed).toBe(false);  // refused before scheduling
  });

  test('runPersistentDag: per-node retry recovers from a flaky execute() within a single run', async () => {
    const dir = tmpDir('pdag-retry');
    const sid = 'retry-1';
    let bAttempt = 0;
    const nodes = [
      { id: 'a', deps: [],    async execute() { return 'A'; } },
      {
        id: 'b',
        deps: ['a'],
        retry: { max: 2, baseDelayMs: 1 },
        async execute(input: any) {
          bAttempt += 1;
          if (bAttempt < 2) throw new Error('flaky-attempt-' + bAttempt);
          return `B:${input.a}`;
        },
      },
    ];
    const r = await runPersistentDag(nodes, { sessionId: sid, dir });
    expect(r.success).toBe(true);
    expect(bAttempt).toBe(2);   // 1 fail + 1 success — retry recovered
    const s = loadState(sid, dir)!;
    expect(s.nodes.b.status).toBe('success');
    expect(s.nodes.b.output).toBe('B:A');
  });

  test('runPersistentDag: per-node retry exhaustion still marks failed and is resumable', async () => {
    const dir = tmpDir('pdag-retry-exhaust');
    const sid = 'exhaust-1';
    const nodes = [
      {
        id: 'b',
        deps: [],
        retry: { max: 2, baseDelayMs: 1 },
        async execute() { throw new Error('always-fails'); },
      },
    ];
    const r = await runPersistentDag(nodes, { sessionId: sid, dir });
    expect(r.success).toBe(false);
    expect(r.failedAt).toBe('b');
    expect(r.error).toMatch(/always-fails/);
    // State persisted as 'failed' so a second runPersistentDag call retries
    // the node from scratch (resume-level retry, separate from node.retry).
    const s = loadState(sid, dir)!;
    expect(s.nodes.b.status).toBe('failed');
  });

  test('runPersistentDag: state file demotes "running" → "pending" on resume so an interrupted level retries', async () => {
    const dir = tmpDir('pdag-interrupted');
    const sid = 'crash-1';
    // Hand-craft a state file that mimics a process killed mid-level:
    // a is success, b is running (was alive when SIGKILL hit).
    const dirPath = path.join(dir);
    fs.mkdirSync(dirPath, { recursive: true });
    const state = {
      sessionId: sid,
      order: ['a', 'b'],
      nodes: {
        a: { status: 'success', output: 'A', attempts: 1, durationMs: 1 },
        b: { status: 'running', attempts: 1 },
      },
      startedAt: 1, updatedAt: 1,
    };
    fs.writeFileSync(path.join(dirPath, `${sid}.json`), JSON.stringify(state));

    const nodes = [
      { id: 'a', deps: [],    async execute() { throw new Error('a should be skipped'); } },
      { id: 'b', deps: ['a'], async execute(input: any) { return `B:${input.a}`; } },
    ];
    const r = await runPersistentDag(nodes, { sessionId: sid, dir });
    expect(r.success).toBe(true);
    expect(r.executedNodes).toEqual(['b']);   // a skipped, b retried
    const s = loadState(sid, dir)!;
    expect(s.nodes.b.output).toBe('B:A');
  });

  // ───── AbortSignal propagation (v3.8) ─────
  // The persistent engines treat abort as RESUMABLE: aborted nodes
  // are demoted back to 'pending', not 'failed'. A future
  // runPersistent()/runPersistentDag() call with the same sessionId
  // picks up where the aborted run stopped — same shape as
  // resume-from-crash, just driven by an explicit AbortController.

  test('runPersistent: signal aborted between nodes → ABORT, current node stays pending, resume completes the run', async () => {
    const dir = tmpDir('persist-abort-seq');
    const sid = 'abort-seq-1';
    const ac = new AbortController();
    const order: string[] = [];
    const nodes: PNode[] = [
      { id: 'a', type: 'test', async execute() { order.push('a'); return 'A'; } },
      { id: 'b', type: 'test', async execute() { order.push('b'); ac.abort(); return 'B'; } },
      { id: 'c', type: 'test', async execute() { order.push('c'); return 'C'; } },
    ];
    const r1 = await runPersistent(nodes, { sessionId: sid, dir, signal: ac.signal });
    expect(r1.success).toBe(false);
    expect((r1 as any).code).toBe('ABORT');
    expect(r1.failedAt).toBe('c');
    expect(order).toEqual(['a', 'b']);

    // Disk state: a=success, b=success, c=pending. Resume picks up at c only.
    const s1 = loadState(sid, dir)!;
    expect(s1.nodes.a.status).toBe('success');
    expect(s1.nodes.b.status).toBe('success');
    expect(s1.nodes.c.status).toBe('pending');

    const order2: string[] = [];
    const nodes2: PNode[] = nodes.map(n => ({
      ...n,
      async execute() { order2.push(n.id); return n.id.toUpperCase(); },
    }));
    const r2 = await runPersistent(nodes2, { sessionId: sid, dir });
    expect(r2.success).toBe(true);
    expect(order2).toEqual(['c']);   // a/b skipped — only c re-ran
  });

  test('runPersistent: signal aborted DURING execute() (forwarded) → node stays pending, resume re-runs it', async () => {
    const dir = tmpDir('persist-abort-during');
    const sid = 'abort-during-1';
    const ac = new AbortController();
    let attempts = 0;
    const nodes: PNode[] = [
      {
        id: 'slow',
        type: 'test',
        async execute(_, opts) {
          attempts++;
          if (attempts === 1) {
            // Simulate a node that subscribes to signal and aborts itself.
            ac.abort();
            const e: any = new Error('aborted');
            e.code = 'ABORT';
            throw e;
          }
          return 'done';
        },
      },
    ];
    const r1 = await runPersistent(nodes, { sessionId: sid, dir, signal: ac.signal });
    expect(r1.success).toBe(false);
    expect((r1 as any).code).toBe('ABORT');
    const s1 = loadState(sid, dir)!;
    expect(s1.nodes.slow.status).toBe('pending');   // NOT 'failed'

    // Resume without a signal — the node retries and succeeds.
    const r2 = await runPersistent(nodes, { sessionId: sid, dir });
    expect(r2.success).toBe(true);
    const s2 = loadState(sid, dir)!;
    expect(s2.nodes.slow.status).toBe('success');
    expect(s2.nodes.slow.output).toBe('done');
  });

  test('runPersistentDag: opts.concurrency caps in-flight nodes within a level', async () => {
    const dir = tmpDir('pdag-conc');
    const sid = 'conc-1';
    let inFlight = 0;
    let peakInFlight = 0;
    // Single fan-out level with 6 independent nodes; cap=2.
    const nodes = Array.from({ length: 6 }, (_, i) => ({
      id: `n${i}`,
      deps: [],
      async execute() {
        inFlight++;
        if (inFlight > peakInFlight) peakInFlight = inFlight;
        await new Promise(r => setTimeout(r, 30));
        inFlight--;
        return i;
      },
    }));
    const r = await runPersistentDag(nodes, { sessionId: sid, dir, concurrency: 2 });
    expect(r.success).toBe(true);
    expect(peakInFlight).toBeLessThanOrEqual(2);
    // All 6 outputs landed on disk despite the concurrency cap.
    const state = loadState(sid, dir)!;
    for (let i = 0; i < 6; i++) expect(state.nodes[`n${i}`].status).toBe('success');
  });

  test('runPersistentDag: signal aborted between levels → ABORT, downstream level skipped, success outputs preserved', async () => {
    const dir = tmpDir('pdag-abort-level');
    const sid = 'abort-dag-1';
    const ac = new AbortController();
    const order: string[] = [];
    const nodes = [
      { id: 'a', deps: [],    async execute() { order.push('a'); return 'A'; } },
      { id: 'b', deps: ['a'], async execute() { order.push('b'); ac.abort(); return 'B'; } },
      { id: 'c', deps: ['b'], async execute() { order.push('c'); return 'C'; } },
    ];
    const r1 = await runPersistentDag(nodes, { sessionId: sid, dir, signal: ac.signal });
    expect(r1.success).toBe(false);
    expect((r1 as any).code).toBe('ABORT');
    expect(r1.failedAt).toBe('c');
    expect(order).toEqual(['a', 'b']);   // c never scheduled

    // Disk: a=success, b=success, c=pending.
    const s1 = loadState(sid, dir)!;
    expect(s1.nodes.a.status).toBe('success');
    expect(s1.nodes.b.status).toBe('success');
    expect(s1.nodes.c.status).toBe('pending');

    // Resume runs only c — fan-in input from b is preserved.
    const order2: string[] = [];
    const nodes2 = nodes.map(n => ({
      ...n,
      async execute(input: any) { order2.push(n.id); return n.id === 'c' ? `C:${input?.b}` : n.id.toUpperCase(); },
    }));
    const r2 = await runPersistentDag(nodes2, { sessionId: sid, dir });
    expect(r2.success).toBe(true);
    expect(order2).toEqual(['c']);
    const s2 = loadState(sid, dir)!;
    expect(s2.nodes.c.output).toBe('C:B');
  });

  test('runPersistentDag: in-flight node aborted via signal demotes back to pending (not failed) — resumable', async () => {
    const dir = tmpDir('pdag-abort-during');
    const sid = 'abort-dag-2';
    const ac = new AbortController();
    let attempts = 0;
    const nodes = [
      {
        id: 'only',
        deps: [],
        async execute(_input: any, opts: any) {
          attempts++;
          if (attempts === 1) {
            ac.abort();
            const e: any = new Error('aborted');
            e.code = 'ABORT';
            throw e;
          }
          return 'recovered';
        },
      },
    ];
    const r1 = await runPersistentDag(nodes, { sessionId: sid, dir, signal: ac.signal });
    expect(r1.success).toBe(false);
    expect((r1 as any).code).toBe('ABORT');
    const s1 = loadState(sid, dir)!;
    expect(s1.nodes.only.status).toBe('pending');   // demoted, not failed

    const r2 = await runPersistentDag(nodes, { sessionId: sid, dir });
    expect(r2.success).toBe(true);
    const s2 = loadState(sid, dir)!;
    expect(s2.nodes.only.status).toBe('success');
    expect(s2.nodes.only.output).toBe('recovered');
  });
});
