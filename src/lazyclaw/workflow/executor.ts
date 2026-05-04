import { performance } from 'node:perf_hooks';
import type { NodeRunRecord, RunResult, WorkflowNode } from './types.js';

export async function runSequential(
  nodes: WorkflowNode[],
  initialInput: unknown = null,
): Promise<RunResult> {
  const session: Record<string, unknown> = {};
  const started: WorkflowNode[] = [];
  const results: NodeRunRecord[] = [];
  let input: unknown = initialInput;

  for (const node of nodes) {
    started.push(node);
    const t0 = performance.now();
    try {
      const output = await node.execute(input);
      const duration = performance.now() - t0;
      results.push({ id: node.id, duration, output, status: 'success' });
      session[node.id] = output;
      input = output;
    } catch (err) {
      const duration = performance.now() - t0;
      results.push({ id: node.id, duration, output: undefined, status: 'failed' });
      const error = err instanceof Error ? err : new Error(String(err));
      for (const n of started) {
        if (n.cleanup) {
          try { await n.cleanup(); } catch { /* swallow cleanup errors */ }
        }
      }
      for (const k of Object.keys(session)) delete session[k];
      return { success: false, results, error, failedAt: node.id, session };
    }
  }
  return { success: true, results, session };
}
