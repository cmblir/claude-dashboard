// LazyClaw auto-resume engine (phase 2).
// State is persisted to <dir>/<sessionId>.json before each node starts and
// after it transitions to success/failed. Re-running a successful node is a
// no-op. Timeouts retry with exponential backoff up to maxRetries.

import fs from 'node:fs';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import { topologicalLevels, retryWithBackoff, runWithTimeout } from './executor.mjs';

const DEFAULT_DIR = '.workflow-state';

/** @typedef {'pending'|'running'|'success'|'failed'} NodeStatus */

/**
 * @typedef {Object} NodeState
 * @property {NodeStatus} status
 * @property {unknown} [output]
 * @property {number} [attempts]
 * @property {string} [error]
 * @property {number} [durationMs]
 */

/**
 * @typedef {Object} PersistedState
 * @property {string} sessionId
 * @property {string[]} order
 * @property {Record<string, NodeState>} nodes
 * @property {number} startedAt
 * @property {number} updatedAt
 */

/**
 * @param {string} sessionId
 * @param {string} [dir]
 */
export function statePath(sessionId, dir = DEFAULT_DIR) {
  return path.join(dir, `${sessionId}.json`);
}

/**
 * @param {string} sessionId
 * @param {string} [dir]
 * @returns {PersistedState | null}
 */
export function loadState(sessionId, dir = DEFAULT_DIR) {
  const p = statePath(sessionId, dir);
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

/**
 * @param {PersistedState} state
 * @param {string} [dir]
 */
export function saveState(state, dir = DEFAULT_DIR) {
  fs.mkdirSync(dir, { recursive: true });
  state.updatedAt = Date.now();
  const p = statePath(state.sessionId, dir);
  const tmp = `${p}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(state, null, 2));
  fs.renameSync(tmp, p);
}

function initState(sessionId, nodes) {
  const now = Date.now();
  return {
    sessionId,
    order: nodes.map(n => n.id),
    nodes: Object.fromEntries(nodes.map(n => [n.id, { status: 'pending', attempts: 0 }])),
    startedAt: now,
    updatedAt: now,
  };
}

// runWithTimeout lives in executor.mjs (imported above) — single
// source of truth so the timeout shape stays identical across both
// engines and any caller that wants to reuse it.

function isTimeout(err) {
  if (!err) return false;
  if (err.code === 'TIMEOUT') return true;
  if (err.message === 'TIMEOUT') return true;
  if (typeof err.message === 'string' && err.message.toLowerCase().includes('timeout')) return true;
  return false;
}

/**
 * @param {import('./executor.mjs').WorkflowNode[]} nodes
 * @param {{
 *   sessionId: string,
 *   dir?: string,
 *   maxRetries?: number,
 *   baseDelayMs?: number,
 *   timeoutMs?: number,
 *   sleep?: (ms: number) => Promise<void>,
 * }} opts
 */
export async function runPersistent(nodes, opts) {
  const dir = opts.dir ?? DEFAULT_DIR;
  const maxRetries = opts.maxRetries ?? 3;
  const baseDelay = opts.baseDelayMs ?? 100;
  const sleep = opts.sleep ?? (ms => new Promise(r => setTimeout(r, ms)));

  let state = loadState(opts.sessionId, dir);
  if (!state) {
    state = initState(opts.sessionId, nodes);
    saveState(state, dir);
  } else {
    for (const id of state.order) {
      const ns = state.nodes[id];
      if (ns && ns.status === 'running') {
        state.nodes[id] = { status: 'pending', attempts: ns.attempts ?? 0 };
      }
    }
    saveState(state, dir);
  }

  const retryDelays = [];
  const executedNodes = [];
  let input = null;

  for (const node of nodes) {
    const ns = state.nodes[node.id] ?? { status: 'pending' };
    if (ns.status === 'success') {
      input = ns.output;
      continue;
    }
    let attempts = ns.attempts ?? 0;
    while (true) {
      attempts++;
      state.nodes[node.id] = { status: 'running', attempts };
      saveState(state, dir);
      const t0 = performance.now();
      try {
        const output = await runWithTimeout(() => node.execute(input), opts.timeoutMs);
        const durationMs = performance.now() - t0;
        state.nodes[node.id] = { status: 'success', output, attempts, durationMs };
        saveState(state, dir);
        executedNodes.push(node.id);
        input = output;
        break;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        if (isTimeout(err) && attempts < maxRetries) {
          const delay = baseDelay * Math.pow(2, attempts - 1);
          retryDelays.push(delay);
          await sleep(delay);
          continue;
        }
        const durationMs = performance.now() - t0;
        state.nodes[node.id] = { status: 'failed', attempts, error: msg, durationMs };
        saveState(state, dir);
        return { success: false, state, failedAt: node.id, error: msg, retryDelays, executedNodes };
      }
    }
  }
  return { success: true, state, retryDelays, executedNodes };
}

/**
 * Persistent DAG executor — combines `runParallel`'s topological-level
 * scheduling with `runPersistent`'s checkpoint-and-resume semantics.
 *
 * Differences from `runPersistent`:
 *   - Nodes declare `deps: string[]` (order in `nodes` array irrelevant).
 *   - Each topological level runs concurrently via `Promise.all`.
 *   - State is saved after every node transition, same atomic-rename
 *     pattern as `runPersistent`.
 *   - Resume: load state; running-status nodes from a prior interrupted
 *     run get reset to pending; success nodes are skipped.
 *
 * Each node receives `{ depId: depOutput }` as input. A node with no
 * deps gets `null`.
 *
 * @param {Array<{
 *   id: string,
 *   deps?: string[],
 *   execute: (input: Record<string, unknown> | null) => Promise<unknown>,
 *   cleanup?: () => (Promise<void>|void),
 * }>} nodes
 * @param {{
 *   sessionId: string,
 *   dir?: string,
 *   timeoutMs?: number,
 * }} opts
 */
export async function runPersistentDag(nodes, opts) {
  const dir = opts.dir ?? DEFAULT_DIR;

  // Compute topological levels at start. (Static import at module top
  // — a dynamic `import()` here trips the tsx loader's CJS conversion
  // path under @playwright/test in some configurations.)
  const { levels, leftover } = topologicalLevels(nodes);
  if (leftover.length > 0) {
    return {
      success: false,
      state: null,
      failedAt: leftover[0],
      error: `workflow has a cycle or unreachable nodes: ${leftover.join(', ')}`,
      executedNodes: [],
    };
  }

  // State init / resume — same shape as runPersistent so a session id
  // doesn't accidentally collide between modes.
  let state = loadState(opts.sessionId, dir);
  if (!state) {
    state = initState(opts.sessionId, nodes);
    saveState(state, dir);
  } else {
    // Demote any 'running' from a prior interrupted run back to pending.
    // success outputs are preserved so a fan-in node sees its predecessors.
    for (const id of Object.keys(state.nodes)) {
      const ns = state.nodes[id];
      if (ns && ns.status === 'running') {
        state.nodes[id] = { status: 'pending', attempts: ns.attempts ?? 0 };
      }
    }
    saveState(state, dir);
  }

  const idToNode = new Map(nodes.map(n => [n.id, n]));
  const executedNodes = [];

  for (const levelIds of levels) {
    // Each node in the level is independent of its peers — run concurrently.
    // We collect both success outputs and the first failure; on failure we
    // stop scheduling future levels (same as runParallel) but persist the
    // success outputs from the level that *did* finish before the throw.
    const tasks = levelIds.map(async (id) => {
      const ns = state.nodes[id] ?? { status: 'pending' };
      if (ns.status === 'success') return { id, ok: true, skipped: true };

      const node = idToNode.get(id);
      const deps = node.deps || [];
      const input = deps.length === 0 ? null : Object.fromEntries(deps.map(d => [d, state.nodes[d]?.output]));

      // Mark running and persist before we start. Concurrent runs of
      // different nodes will each write the state file; saveState's
      // tmp+rename keeps each write atomic, but the final file content
      // is the LAST writer's view — that's fine because each node only
      // mutates its own slot.
      state.nodes[id] = { status: 'running', attempts: (ns.attempts ?? 0) + 1 };
      saveState(state, dir);
      const t0 = performance.now();
      // Wrap each execute() in retryWithBackoff when node.retry is set.
      // The retry budget lives entirely *inside* this attempt — outer
      // resume semantics are unchanged: a level failure still flips
      // node status to 'failed' on disk, and a future runPersistentDag
      // call retries it from scratch (resume-level retry, separate from
      // node.retry). This composition gives users two distinct knobs:
      //   - node.retry  → recover transient faults within one run
      //   - resume      → recover catastrophic faults across runs
      // node.timeoutMs (per-node) takes precedence over opts.timeoutMs
      // (workflow-wide default) so a fast node with a tight cap doesn't
      // inherit a slower node's lenient cap.
      const effectiveTimeout = Number.isFinite(node.timeoutMs) ? node.timeoutMs : opts.timeoutMs;
      const fn = () => runWithTimeout(() => node.execute(input), effectiveTimeout);
      try {
        const output = node.retry && Number.isFinite(node.retry.max) && node.retry.max > 0
          ? await retryWithBackoff(fn, node.retry)
          : await fn();
        const durationMs = performance.now() - t0;
        state.nodes[id] = { status: 'success', output, attempts: state.nodes[id].attempts, durationMs };
        saveState(state, dir);
        return { id, ok: true };
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        const durationMs = performance.now() - t0;
        state.nodes[id] = { status: 'failed', error: msg, attempts: state.nodes[id].attempts, durationMs };
        saveState(state, dir);
        return { id, ok: false, error: msg };
      }
    });
    const settled = await Promise.all(tasks);
    let firstFailure = null;
    for (const r of settled) {
      if (r.ok && !r.skipped) executedNodes.push(r.id);
      if (!r.ok && !firstFailure) firstFailure = r;
    }
    if (firstFailure) {
      return { success: false, state, failedAt: firstFailure.id, error: firstFailure.error, executedNodes };
    }
  }

  return { success: true, state, executedNodes };
}
