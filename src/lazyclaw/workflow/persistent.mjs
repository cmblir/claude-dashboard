// LazyClaw auto-resume engine (phase 2).
// State is persisted to <dir>/<sessionId>.json before each node starts and
// after it transitions to success/failed. Re-running a successful node is a
// no-op. Timeouts retry with exponential backoff up to maxRetries.

import fs from 'node:fs';
import path from 'node:path';
import { performance } from 'node:perf_hooks';

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

async function runWithTimeout(fn, ms) {
  if (!ms || ms <= 0) return fn();
  return await new Promise((resolve, reject) => {
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
