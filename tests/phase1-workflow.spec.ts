import { test, expect } from '@playwright/test';
import { runSequential, runParallel, topologicalLevels, retryWithBackoff, runWithTimeout } from '../src/lazyclaw/workflow/executor.mjs';

interface WorkflowNode {
  id: string;
  type: string;
  execute(input: unknown): Promise<unknown>;
  cleanup?: () => void | Promise<void>;
}

function makeNodes(count: number, failAt?: number): { nodes: WorkflowNode[]; order: string[]; cleaned: string[] } {
  const order: string[] = [];
  const cleaned: string[] = [];
  const nodes: WorkflowNode[] = Array.from({ length: count }, (_, i) => ({
    id: `n${i + 1}`,
    type: 'test',
    async execute(input: unknown): Promise<number> {
      order.push(`n${i + 1}`);
      if (failAt !== undefined && i + 1 === failAt) throw new Error(`boom@n${failAt}`);
      const prev = typeof input === 'number' ? input : 0;
      return prev + 1;
    },
    cleanup() { cleaned.push(`n${i + 1}`); },
  }));
  return { nodes, order, cleaned };
}

test.describe('Phase 1 — Workflow Engine Core', () => {
  test('runs 10 nodes sequentially in order', async () => {
    const { nodes, order } = makeNodes(10);
    const r = await runSequential(nodes, 0);
    expect(r.success).toBe(true);
    expect(order).toEqual(['n1','n2','n3','n4','n5','n6','n7','n8','n9','n10']);
    expect(r.results.map(x => x.id)).toEqual(order);
    expect(r.results.at(-1)?.output).toBe(10);
  });

  test('per-node latency under 50ms', async () => {
    const { nodes } = makeNodes(10);
    const r = await runSequential(nodes, 0);
    expect(r.success).toBe(true);
    for (const rec of r.results) {
      expect(rec.duration).toBeLessThan(50);
    }
  });

  test('failure at node 5 cancels nodes 6..10', async () => {
    const { nodes, order } = makeNodes(10, 5);
    const r = await runSequential(nodes, 0);
    expect(r.success).toBe(false);
    expect(r.failedAt).toBe('n5');
    expect(order).toEqual(['n1','n2','n3','n4','n5']);
    for (const skipped of ['n6','n7','n8','n9','n10']) {
      expect(order).not.toContain(skipped);
    }
  });

  test('failure triggers cleanup on started nodes and clears session', async () => {
    const { nodes, cleaned } = makeNodes(10, 5);
    const r = await runSequential(nodes, 0);
    expect(r.success).toBe(false);
    expect(cleaned).toEqual(['n1','n2','n3','n4','n5']);
    expect(Object.keys(r.session)).toEqual([]);
  });

  test('async cleanup runs in parallel — total time is max(t_cleanup), not sum', async () => {
    // 5 nodes; each cleanup sleeps 80ms. Sequential cleanup = 400ms+.
    // Parallel via Promise.allSettled = ~80ms (one slot of wall-clock).
    // We allow up to 200ms for slow CI; sequential would be ~400ms+.
    const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
    let executed = 0;
    const nodes: WorkflowNode[] = Array.from({ length: 5 }, (_, i) => ({
      id: `n${i + 1}`,
      type: 'test',
      async execute() {
        executed++;
        if (i === 4) throw new Error('boom@n5');  // last node fails
        return i;
      },
      async cleanup() { await sleep(80); },
    }));
    const t0 = performance.now();
    const r = await runSequential(nodes, 0);
    const elapsed = performance.now() - t0;
    expect(r.success).toBe(false);
    expect(executed).toBe(5);
    // Hard ceiling well below the sequential floor (5 × 80 = 400ms).
    expect(elapsed).toBeLessThan(200);
  });

  test('one cleanup throwing does not stop the others (allSettled, not allFulfilled)', async () => {
    const cleaned: string[] = [];
    const nodes: WorkflowNode[] = [
      { id: 'a', type: 't', async execute() { return 1; }, async cleanup() { cleaned.push('a'); } },
      { id: 'b', type: 't', async execute() { return 2; }, async cleanup() { throw new Error('cleanup-b-failed'); } },
      { id: 'c', type: 't', async execute() { return 3; }, async cleanup() { cleaned.push('c'); } },
      { id: 'd', type: 't', async execute() { throw new Error('boom@d'); } },
    ];
    const r = await runSequential(nodes, 0);
    expect(r.success).toBe(false);
    expect(r.failedAt).toBe('d');
    expect(cleaned).toContain('a');
    expect(cleaned).toContain('c');
  });

  test('topologicalLevels groups nodes by dependency depth', () => {
    const nodes = [
      { id: 'a', deps: [] },
      { id: 'b', deps: ['a'] },
      { id: 'c', deps: ['a'] },
      { id: 'd', deps: ['b', 'c'] },
    ];
    const { levels, leftover } = topologicalLevels(nodes);
    expect(leftover).toEqual([]);
    expect(levels).toHaveLength(3);
    expect(levels[0]).toEqual(['a']);
    expect(new Set(levels[1])).toEqual(new Set(['b', 'c']));  // order within level not guaranteed
    expect(levels[2]).toEqual(['d']);
  });

  test('topologicalLevels reports leftover when there is a cycle', () => {
    const { leftover } = topologicalLevels([
      { id: 'a', deps: ['b'] },
      { id: 'b', deps: ['a'] },
    ]);
    expect(leftover.sort()).toEqual(['a', 'b']);
  });

  test('runParallel: independent nodes execute concurrently', async () => {
    // Three independent 100ms nodes. Sequential would be 300ms+.
    // Parallel should be ~100ms.
    const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
    const nodes = [
      { id: 'a', type: 't', deps: [], async execute() { await sleep(100); return 'A'; } },
      { id: 'b', type: 't', deps: [], async execute() { await sleep(100); return 'B'; } },
      { id: 'c', type: 't', deps: [], async execute() { await sleep(100); return 'C'; } },
    ];
    const t0 = performance.now();
    const r = await runParallel(nodes);
    const elapsed = performance.now() - t0;
    expect(r.success).toBe(true);
    expect(elapsed).toBeLessThan(220);  // parallel; sequential floor is 300+
    expect(r.session).toEqual({ a: 'A', b: 'B', c: 'C' });
  });

  test('runParallel: fan-in node receives a {dep: output} input map', async () => {
    let receivedInput: any = null;
    const nodes = [
      { id: 'a', type: 't', deps: [], async execute() { return 'fromA'; } },
      { id: 'b', type: 't', deps: [], async execute() { return 'fromB'; } },
      {
        id: 'merge',
        type: 't',
        deps: ['a', 'b'],
        async execute(input: any) { receivedInput = input; return 'merged'; },
      },
    ];
    const r = await runParallel(nodes);
    expect(r.success).toBe(true);
    expect(receivedInput).toEqual({ a: 'fromA', b: 'fromB' });
    expect(r.session.merge).toBe('merged');
  });

  test('runParallel: failure in one level cancels later levels and runs cleanup on started nodes', async () => {
    const cleaned: string[] = [];
    const nodes = [
      { id: 'a', type: 't', deps: [], async execute() { return 1; }, cleanup() { cleaned.push('a'); } },
      { id: 'b', type: 't', deps: [], async execute() { throw new Error('boom@b'); }, cleanup() { cleaned.push('b'); } },
      { id: 'c', type: 't', deps: ['a'], async execute() { return 2; }, cleanup() { cleaned.push('c'); } },
    ];
    const r = await runParallel(nodes);
    expect(r.success).toBe(false);
    expect(r.failedAt).toBe('b');
    // Level 0 (a + b) both ran; cleanup ran for both. c is in level 1
    // and never started.
    expect(cleaned.sort()).toEqual(['a', 'b']);
    expect(Object.keys(r.session)).toEqual([]);
  });

  test('retryWithBackoff: succeeds on the second attempt and the result propagates', async () => {
    let calls = 0;
    const sleeps: number[] = [];
    const r = await retryWithBackoff(async () => {
      calls += 1;
      if (calls === 1) throw new Error('flaky');
      return 'ok';
    }, {
      max: 3,
      baseDelayMs: 10,
      sleep: async (ms: number) => { sleeps.push(ms); },
    });
    expect(r).toBe('ok');
    expect(calls).toBe(2);
    // baseDelayMs × 2^0 = 10
    expect(sleeps).toEqual([10]);
  });

  test('retryWithBackoff: exhaustion rethrows the LAST error', async () => {
    let calls = 0;
    let caught: any = null;
    try {
      await retryWithBackoff(async () => {
        calls += 1;
        const e = new Error(`attempt-${calls}`);
        (e as any).code = 'CUSTOM';
        throw e;
      }, { max: 2, baseDelayMs: 1, sleep: async () => {} });
    } catch (e) { caught = e; }
    // 1 initial + 2 retries = 3 calls
    expect(calls).toBe(3);
    expect(caught.message).toBe('attempt-3');
    expect(caught.code).toBe('CUSTOM');  // type preserved
  });

  test('runSequential: per-node retry recovers from a flaky execute() and the workflow succeeds', async () => {
    let bAttempt = 0;
    const nodes = [
      { id: 'a', type: 't', async execute() { return 'A'; } },
      {
        id: 'b', type: 't',
        retry: { max: 2, baseDelayMs: 1 },
        async execute(input: any) {
          bAttempt += 1;
          if (bAttempt < 2) throw new Error('flaky');
          return `B:${input}`;
        },
      },
      { id: 'c', type: 't', async execute(input: any) { return `C:${input}`; } },
    ];
    const r = await runSequential(nodes, null);
    expect(r.success).toBe(true);
    expect(bAttempt).toBe(2);  // 1 fail + 1 success
    expect(r.results.at(-1)?.output).toBe('C:B:A');
  });

  test('runParallel: per-node retry preserves DAG semantics', async () => {
    let bAttempt = 0;
    const nodes = [
      { id: 'a', type: 't', deps: [], async execute() { return 'A'; } },
      {
        id: 'b', type: 't', deps: ['a'],
        retry: { max: 1, baseDelayMs: 1 },
        async execute() { bAttempt += 1; if (bAttempt < 2) throw new Error('flaky'); return 'B'; },
      },
    ];
    const r = await runParallel(nodes);
    expect(r.success).toBe(true);
    expect(bAttempt).toBe(2);
    expect(r.session.b).toBe('B');
  });

  test('runWithTimeout: passes through fast results', async () => {
    const r = await runWithTimeout(async () => 'fast', 1000);
    expect(r).toBe('fast');
  });

  test('runWithTimeout: rejects with TIMEOUT code on slow execution', async () => {
    const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
    let caught: any = null;
    try {
      await runWithTimeout(async () => { await sleep(200); return 'late'; }, 30);
    } catch (e) { caught = e; }
    expect(caught?.code).toBe('TIMEOUT');
    expect(caught?.message).toBe('TIMEOUT');
  });

  test('runWithTimeout: ms=0 / null disables the timer (returns whenever the fn settles)', async () => {
    const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
    expect(await runWithTimeout(async () => { await sleep(20); return 'A'; }, 0)).toBe('A');
    expect(await runWithTimeout(async () => 'B', null as any)).toBe('B');
  });

  test('runSequential: per-node timeoutMs trips a slow node and the workflow fails at that node', async () => {
    const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
    const nodes = [
      { id: 'fast', type: 't', async execute() { return 'A'; } },
      { id: 'slow', type: 't', timeoutMs: 30, async execute() { await sleep(200); return 'late'; } },
      { id: 'never', type: 't', async execute() { return 'unreachable'; } },
    ];
    const r = await runSequential(nodes, null);
    expect(r.success).toBe(false);
    expect(r.failedAt).toBe('slow');
    expect(r.error?.message).toBe('TIMEOUT');
    // 'never' must not have run
    expect(r.results.find(x => x.id === 'never')).toBeUndefined();
  });

  test('runSequential: timeout + retry compose — N attempts of M-ms each', async () => {
    const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
    let attempts = 0;
    const nodes = [
      {
        id: 'flaky-slow',
        type: 't',
        timeoutMs: 30,
        retry: { max: 2, baseDelayMs: 1 },
        async execute() {
          attempts += 1;
          // Succeed on the third attempt; first two time out.
          if (attempts < 3) { await sleep(200); return 'late'; }
          return 'fast';
        },
      },
    ];
    const r = await runSequential(nodes, null);
    expect(r.success).toBe(true);
    expect(attempts).toBe(3);
    expect(r.results[0].output).toBe('fast');
  });

  test('runParallel: detects cycles and refuses to run', async () => {
    const nodes = [
      { id: 'a', type: 't', deps: ['b'], async execute() { return 1; } },
      { id: 'b', type: 't', deps: ['a'], async execute() { return 2; } },
    ];
    const r = await runParallel(nodes);
    expect(r.success).toBe(false);
    expect(r.error?.message).toMatch(/cycle/);
  });
});
