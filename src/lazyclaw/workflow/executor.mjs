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
 * Race a promise against a timeout. Returns whatever the inner fn
 * resolves with; rejects with `Error('TIMEOUT'){code:'TIMEOUT'}` after
 * `ms` if the inner fn hasn't settled. Pass ms=0 / null / undefined
 * to skip the timer entirely.
 *
 * Exported so callers (workflow nodes, daemon endpoints, ad-hoc
 * scripts) can apply the same timeout shape without reinventing the
 * race + cleanup pattern.
 */
export function runWithTimeout(fn, ms) {
  if (!ms || ms <= 0) return fn();
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => {
      const e = new Error('TIMEOUT');
      e.code = 'TIMEOUT';
      reject(e);
    }, ms);
    fn().then(
      v => { clearTimeout(t); resolve(v); },
      e => { clearTimeout(t); reject(e); },
    );
  });
}

/**
 * Per-node retry helper. Honored by both runSequential and runParallel:
 * when `node.retry = { max: N, baseDelayMs: M }`, a throwing execute()
 * is retried up to N times with exponential backoff (baseDelayMs × 2^attempt).
 * Default baseDelayMs is 100. attempt counter is exposed via `attempts`
 * so a node can branch on it if needed.
 *
 * Returns the eventual successful output, or rethrows the LAST error
 * after exhausting retries — preserving the original error type so the
 * outer engine's failure path is unchanged.
 *
 * Exported for unit testing without spinning up a full workflow.
 *
 * @param {() => Promise<unknown>} fn
 * @param {{ max: number, baseDelayMs?: number, sleep?: (ms: number) => Promise<void> }} opts
 */
export async function retryWithBackoff(fn, opts) {
  const max = Math.max(0, Number(opts.max) || 0);
  const baseDelay = Number(opts.baseDelayMs) || 100;
  const sleep = opts.sleep || (ms => new Promise(r => setTimeout(r, ms)));
  let lastErr = null;
  for (let attempt = 0; attempt <= max; attempt++) {
    try { return await fn(); }
    catch (err) {
      lastErr = err;
      if (attempt >= max) break;
      await sleep(baseDelay * Math.pow(2, attempt));
    }
  }
  throw lastErr;
}

/**
 * Run a flat list of nodes sequentially, threading the output of each into
 * the next. On any throw, run cleanup hooks on every started node and clear
 * the in-memory session record.
 *
 * `opts.signal` (AbortSignal) is honored before each node starts AND
 * passed to `node.execute(input, { signal })` so long-running nodes
 * can react to outer cancellation. An aborted workflow runs cleanup
 * on every started node and returns failure with code 'ABORT'.
 *
 * @param {WorkflowNode[]} nodes
 * @param {unknown} [initialInput]
 * @param {{ signal?: AbortSignal }} [opts]
 * @returns {Promise<RunResult>}
 */
export async function runSequential(nodes, initialInput = null, opts = {}) {
  /** @type {Record<string, unknown>} */
  const session = {};
  /** @type {WorkflowNode[]} */
  const started = [];
  /** @type {NodeRunRecord[]} */
  const results = [];
  let input = initialInput;
  const signal = opts.signal;

  for (const node of nodes) {
    if (signal?.aborted) {
      // Cancellation between nodes: cleanup what we started, fail fast.
      await Promise.allSettled(started.map(n => {
        if (typeof n.cleanup !== 'function') return null;
        try { return Promise.resolve(n.cleanup()); }
        catch { return Promise.resolve(); }
      }));
      for (const k of Object.keys(session)) delete session[k];
      const e = new Error('aborted');
      /** @type {any} */ (e).code = 'ABORT';
      return { success: false, results, error: e, failedAt: node.id, session };
    }
    started.push(node);
    const t0 = performance.now();
    try {
      // Build the actual call: optional timeout wraps execute(); retry
      // wraps the timed call. So a flaky 5-second op with `retry:{max:3}`
      // and `timeoutMs:5000` gets up-to-3 attempts of up-to-5s each.
      // The signal is forwarded to execute() so the node can react.
      const call = () => runWithTimeout(() => node.execute(input, { signal }), node.timeoutMs);
      const output = node.retry && Number.isFinite(node.retry.max) && node.retry.max > 0
        ? await retryWithBackoff(call, node.retry)
        : await call();
      const duration = performance.now() - t0;
      results.push({ id: node.id, duration, output, status: 'success' });
      session[node.id] = output;
      input = output;
    } catch (err) {
      const duration = performance.now() - t0;
      results.push({ id: node.id, duration, output: undefined, status: 'failed' });
      const error = err instanceof Error ? err : new Error(String(err));
      // Cleanup runs in parallel via Promise.allSettled — for async cleanups
      // (close a socket, flush a buffer) total time is max(t_cleanup) instead
      // of sum(t_cleanup). Sync cleanups push their side-effects in array
      // order (the iterator runs synchronously in the .map call) so the
      // existing order-asserting tests keep passing without weakening.
      // Errors are swallowed individually so a flaky cleanup can't mask the
      // original failure that triggered cleanup in the first place.
      await Promise.allSettled(started.map(n => {
        if (typeof n.cleanup !== 'function') return null;
        try { return Promise.resolve(n.cleanup()); }
        catch (e) { return Promise.resolve(); }
      }));
      for (const k of Object.keys(session)) delete session[k];
      return { success: false, results, error, failedAt: node.id, session };
    }
  }
  return { success: true, results, session };
}

/**
 * Compute topological levels (Kahn's algorithm). Returns an array of
 * level groups; nodes within a group have no dependencies on each
 * other and can run concurrently. Cycles produce an empty trailing
 * remainder, which the caller turns into an error.
 *
 * @param {Array<{id: string, deps?: string[]}>} nodes
 * @returns {{ levels: string[][], leftover: string[] }}
 */
export function topologicalLevels(nodes) {
  const idToNode = new Map(nodes.map(n => [n.id, n]));
  const indegree = new Map();
  const reverse = new Map(); // id → [dependents]
  for (const n of nodes) {
    indegree.set(n.id, 0);
    reverse.set(n.id, []);
  }
  for (const n of nodes) {
    for (const d of n.deps || []) {
      // Unknown dep — treated as a satisfied edge (don't lock the node out).
      // Caller can validate up front if they want strict mode.
      if (!idToNode.has(d)) continue;
      indegree.set(n.id, (indegree.get(n.id) || 0) + 1);
      reverse.get(d).push(n.id);
    }
  }
  const levels = [];
  let frontier = nodes.filter(n => (indegree.get(n.id) || 0) === 0).map(n => n.id);
  const visited = new Set();
  while (frontier.length) {
    levels.push(frontier);
    for (const id of frontier) visited.add(id);
    const next = [];
    for (const id of frontier) {
      for (const dep of reverse.get(id) || []) {
        const left = (indegree.get(dep) || 0) - 1;
        indegree.set(dep, left);
        if (left === 0) next.push(dep);
      }
    }
    frontier = next;
  }
  const leftover = nodes.map(n => n.id).filter(id => !visited.has(id));
  return { levels, leftover };
}

/**
 * Run a DAG of nodes by topological level — within a level, every node
 * runs concurrently via `Promise.all`. Each node receives a map of its
 * declared deps' outputs as input (`{ depId: depOutput }`), so a fan-in
 * node can see all its inputs at once.
 *
 * On any failure: stop scheduling further levels, run cleanup on every
 * node that started (in any level), clear the session, return failure.
 * Cleanups run via `Promise.allSettled` so a flaky cleanup can't mask
 * the original error.
 *
 * `opts.signal` is checked between levels and forwarded to each
 * `node.execute(input, { signal })`. An aborted signal between levels
 * stops further scheduling, runs cleanup, and returns
 * `{ success:false, error: ABORT }`.
 *
 * @param {Array<{
 *   id: string,
 *   type: string,
 *   deps?: string[],
 *   execute: (input: Record<string, unknown> | unknown, opts?: { signal?: AbortSignal }) => Promise<unknown>,
 *   cleanup?: (() => (Promise<void>|void)),
 *   retry?: { max: number, baseDelayMs?: number },
 *   timeoutMs?: number,
 * }>} nodes
 * @param {{ initialInput?: unknown, signal?: AbortSignal }} [opts]
 * @returns {Promise<RunResult>}
 */
export async function runParallel(nodes, opts = {}) {
  const session = {};
  const started = [];
  const results = [];
  const idToNode = new Map(nodes.map(n => [n.id, n]));
  const { levels, leftover } = topologicalLevels(nodes);
  if (leftover.length > 0) {
    const error = new Error(`workflow has a cycle or unreachable nodes: ${leftover.join(', ')}`);
    return { success: false, results, error, failedAt: leftover[0], session };
  }
  const signal = opts.signal;
  for (const level of levels) {
    // Cancellation check between levels: don't start a new level if
    // the caller has aborted. Cleanup runs over every node that
    // actually started (which excludes future levels by definition).
    if (signal?.aborted) {
      await Promise.allSettled(started.map(n => {
        if (typeof n.cleanup !== 'function') return null;
        try { return Promise.resolve(n.cleanup()); }
        catch { return Promise.resolve(); }
      }));
      for (const k of Object.keys(session)) delete session[k];
      const e = new Error('aborted');
      /** @type {any} */ (e).code = 'ABORT';
      return { success: false, results, error: e, failedAt: level[0], session };
    }
    // Build the input record for each node in the level: each node sees
    // a `{ depId: depOutput }` map, or `initialInput` when it has no deps.
    const settled = await Promise.allSettled(level.map(async (id) => {
      const node = idToNode.get(id);
      started.push(node);
      const deps = node.deps || [];
      const input = deps.length === 0
        ? (opts.initialInput ?? null)
        : Object.fromEntries(deps.map(d => [d, session[d]]));
      const t0 = performance.now();
      try {
        const call = () => runWithTimeout(() => node.execute(input, { signal }), node.timeoutMs);
        const output = node.retry && Number.isFinite(node.retry.max) && node.retry.max > 0
          ? await retryWithBackoff(call, node.retry)
          : await call();
        const duration = performance.now() - t0;
        return { ok: true, record: { id, duration, output, status: /** @type {'success'} */('success') } };
      } catch (err) {
        const duration = performance.now() - t0;
        return { ok: false, record: { id, duration, output: undefined, status: /** @type {'failed'} */('failed') }, err };
      }
    }));
    let firstFailure = null;
    for (const s of settled) {
      // Promise.allSettled never rejects; the inner async function caught.
      const v = s.status === 'fulfilled' ? s.value : { ok: false, record: { id: 'unknown', duration: 0, output: undefined, status: 'failed' }, err: s.reason };
      results.push(v.record);
      if (v.ok) {
        session[v.record.id] = v.record.output;
      } else if (!firstFailure) {
        firstFailure = v;
      }
    }
    if (firstFailure) {
      const error = firstFailure.err instanceof Error ? firstFailure.err : new Error(String(firstFailure.err));
      await Promise.allSettled(started.map(n => {
        if (typeof n.cleanup !== 'function') return null;
        try { return Promise.resolve(n.cleanup()); }
        catch { return Promise.resolve(); }
      }));
      for (const k of Object.keys(session)) delete session[k];
      return { success: false, results, error, failedAt: firstFailure.record.id, session };
    }
  }
  return { success: true, results, session };
}
