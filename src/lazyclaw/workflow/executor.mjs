// LazyClaw sequential workflow executor (phase 1).
// Plain ESM so it runs under bare node (CLI) and under @playwright/test (TS-aware).

import { performance } from 'node:perf_hooks';

/**
 * @typedef {Object} WorkflowNode
 * @property {string} id
 * @property {string} type
 * @property {(input: unknown) => Promise<unknown>} execute
 * @property {(() => (Promise<void>|void))} [cleanup]
 */

/**
 * @typedef {Object} NodeRunRecord
 * @property {string} id
 * @property {number} duration
 * @property {unknown} output
 * @property {'success'|'failed'} status
 */

/**
 * @typedef {Object} RunResult
 * @property {boolean} success
 * @property {NodeRunRecord[]} results
 * @property {Record<string, unknown>} session
 * @property {Error} [error]
 * @property {string} [failedAt]
 */

/**
 * Run a flat list of nodes sequentially, threading the output of each into
 * the next. On any throw, run cleanup hooks on every started node and clear
 * the in-memory session record.
 *
 * @param {WorkflowNode[]} nodes
 * @param {unknown} [initialInput]
 * @returns {Promise<RunResult>}
 */
export async function runSequential(nodes, initialInput = null) {
  /** @type {Record<string, unknown>} */
  const session = {};
  /** @type {WorkflowNode[]} */
  const started = [];
  /** @type {NodeRunRecord[]} */
  const results = [];
  let input = initialInput;

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
        if (typeof n.cleanup === 'function') {
          try { await n.cleanup(); } catch { /* swallow cleanup errors */ }
        }
      }
      for (const k of Object.keys(session)) delete session[k];
      return { success: false, results, error, failedAt: node.id, session };
    }
  }
  return { success: true, results, session };
}
