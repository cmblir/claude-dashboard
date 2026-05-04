import { test, expect } from '@playwright/test';
import { runSequential } from '../src/lazyclaw/workflow/executor.mjs';

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
    // a and c both ran cleanup despite b throwing in between.
    expect(cleaned).toContain('a');
    expect(cleaned).toContain('c');
  });
});
