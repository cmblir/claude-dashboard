import { test, expect } from '@playwright/test';
import { runSequential } from '../src/lazyclaw/workflow/executor.js';
import type { WorkflowNode } from '../src/lazyclaw/workflow/types.js';

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
});
