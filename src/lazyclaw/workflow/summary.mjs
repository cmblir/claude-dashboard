// Pure transformations over persisted workflow state.
// Lifted out of the CLI so both `lazyclaw inspect` and the daemon's
// /workflows endpoint can produce the same shape — a single source
// of truth for what "workflow progress" looks like over the wire.
//
// We intentionally re-implement state-file reading here (a 3-line
// function) instead of importing from `persistent.mjs`. The daemon's
// import graph stays free of the workflow engine — under tsx/CJS
// conversion in @playwright/test, importing engine modules from the
// daemon's static graph has historically broken.

import fs from 'node:fs';
import path from 'node:path';

/**
 * Load a persisted state file. Returns null when the file does not
 * exist (a session that has never been written). Throws on JSON
 * parse errors so callers can surface the corruption rather than
 * masking it as "no state".
 *
 * @param {string} sessionId
 * @param {string} dir
 * @returns {object | null}
 */
export function loadStateFile(sessionId, dir) {
  const p = path.join(dir, `${sessionId}.json`);
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

/**
 * @typedef {{ status?: 'pending'|'running'|'success'|'failed', output?: unknown, attempts?: number, error?: string, durationMs?: number }} NodeState
 * @typedef {{ sessionId: string, order?: string[], nodes: Record<string, NodeState>, startedAt?: number, updatedAt?: number }} PersistedState
 * @typedef {{ total: number, pending: number, running: number, success: number, failed: number, done: boolean, resumable: boolean, durationMs: number }} StateSummary
 */

/**
 * Reduce a persisted state object to its summary block + the list of
 * failed nodes. The summary is the same regardless of whether you're
 * looking at a single session or one element of a listing.
 *
 * @param {PersistedState} state
 * @returns {{ summary: StateSummary, failedNodes: Array<{ id: string, error?: string, attempts?: number }> }}
 */
export function summarizeState(state) {
  const counts = { pending: 0, running: 0, success: 0, failed: 0 };
  const failedNodes = [];
  let totalDurationMs = 0;
  const nodes = state?.nodes || {};
  for (const id of Object.keys(nodes)) {
    const n = nodes[id];
    const status = n?.status || 'pending';
    if (counts[status] !== undefined) counts[status]++;
    if (status === 'failed') failedNodes.push({ id, error: n.error, attempts: n.attempts });
    if (typeof n?.durationMs === 'number') totalDurationMs += n.durationMs;
  }
  const total = Object.keys(nodes).length;
  const allDone = total > 0 && counts.success === total;
  const hasFailure = counts.failed > 0;
  return {
    summary: {
      total,
      ...counts,
      done: allDone,
      // "Resumable" = there's at least one non-success node AND no terminal
      // failure. Running/pending nodes from a prior interrupted run will be
      // demoted by the engine on next load — they count as resumable work.
      resumable: !allDone && !hasFailure,
      durationMs: totalDurationMs,
    },
    failedNodes,
  };
}

/**
 * Aggregate per-node statistics across every persisted session in
 * a state directory. For each node id seen across sessions, compute
 * how often it ran, how often it succeeded/failed, and the
 * min/max/avg/total durations.
 *
 * Useful for cross-run analysis: "which node tends to be slow or
 * fail across all my runs of this workflow?" — a question
 * single-session inspect can't answer.
 *
 * @param {string} dir
 * @param {{ filter?: string }} [opts]   Optional case-insensitive
 *        sessionId substring filter — only matching sessions
 *        contribute to the aggregate. Same semantic as v3.36's
 *        list-mode `--filter`.
 * @returns {{ sessionCount: number, nodeStats: Record<string, {
 *   count: number,
 *   successCount: number,
 *   failedCount: number,
 *   pendingCount: number,
 *   runningCount: number,
 *   minDurationMs: number,
 *   maxDurationMs: number,
 *   avgDurationMs: number,
 *   totalDurationMs: number,
 * }> }}
 */
export function aggregateNodeStats(dir, opts = {}) {
  if (!fs.existsSync(dir)) {
    const e = new Error(`State directory ${dir} does not exist`);
    /** @type {any} */ (e).code = 'ENOENT';
    throw e;
  }
  const files = fs.readdirSync(dir).filter(f => f.endsWith('.json'));
  let sessionCount = 0;
  /** @type {Record<string, { count: number, successCount: number, failedCount: number, pendingCount: number, runningCount: number, durations: number[] }>} */
  const accumulator = {};
  const filterLower = opts.filter ? String(opts.filter).toLowerCase() : null;
  for (const f of files) {
    let state;
    try {
      state = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
    } catch { continue; }
    if (!state?.sessionId || !state?.nodes) continue;
    if (filterLower && !state.sessionId.toLowerCase().includes(filterLower)) continue;
    sessionCount++;
    for (const id of Object.keys(state.nodes)) {
      const ns = state.nodes[id];
      const status = ns?.status || 'pending';
      const slot = accumulator[id] || (accumulator[id] = {
        count: 0, successCount: 0, failedCount: 0, pendingCount: 0, runningCount: 0,
        durations: [],
      });
      slot.count++;
      if (status === 'success')      slot.successCount++;
      else if (status === 'failed')  slot.failedCount++;
      else if (status === 'pending') slot.pendingCount++;
      else if (status === 'running') slot.runningCount++;
      if (Number.isFinite(ns?.durationMs)) slot.durations.push(ns.durationMs);
    }
  }
  /** @type {Record<string, ReturnType<typeof aggregateNodeStats>['nodeStats'][string]>} */
  const nodeStats = {};
  for (const id of Object.keys(accumulator)) {
    const slot = accumulator[id];
    const durations = slot.durations;
    const total = durations.reduce((s, x) => s + x, 0);
    nodeStats[id] = {
      count: slot.count,
      successCount: slot.successCount,
      failedCount: slot.failedCount,
      pendingCount: slot.pendingCount,
      runningCount: slot.runningCount,
      minDurationMs: durations.length ? Math.min(...durations) : 0,
      maxDurationMs: durations.length ? Math.max(...durations) : 0,
      avgDurationMs: durations.length ? Math.round((total / durations.length) * 100) / 100 : 0,
      totalDurationMs: Math.round(total * 100) / 100,
    };
  }
  return { sessionCount, nodeStats };
}

/**
 * Compute the critical path (longest weighted path) through a DAG.
 *
 * Given the persisted state's node order + a deps map (which the
 * caller supplies, since the engine doesn't persist deps — it
 * persists outputs and statuses), this walks the DAG in
 * topological order and finds the chain of nodes whose summed
 * `durationMs` is the largest among all root-to-leaf paths.
 *
 * Algorithm — straightforward DP over a topo order:
 *   for each node in topo order:
 *     bestPredecessor = arg max over deps (bestFinish[dep])
 *     bestFinish[node] = (bestFinish[bestPredecessor] || 0) + duration[node]
 *     prev[node] = bestPredecessor
 *
 * Then walk `prev[]` backwards from the node with the max
 * bestFinish to recover the path.
 *
 * @param {{ id: string, deps?: string[] }[]} graphNodes  Workflow shape (deps = id[])
 * @param {Record<string, { durationMs?: number, status?: string }>} stateNodes  Persisted state (durationMs)
 * @returns {{ path: string[], totalMs: number, perNodeMs: Record<string, number> }}
 *          - path: ordered list of node ids on the critical path
 *          - totalMs: sum of durationMs across the path
 *          - perNodeMs: durationMs lookup for every node (0 if missing)
 */
export function criticalPath(graphNodes, stateNodes) {
  const idToDeps = new Map(graphNodes.map(n => [n.id, n.deps || []]));
  const ids = graphNodes.map(n => n.id);
  // Topological order — Kahn's algorithm. We don't need levels here,
  // just an order where every dep comes before its dependents.
  const indegree = new Map(ids.map(id => [id, 0]));
  for (const n of graphNodes) {
    for (const d of n.deps || []) {
      if (indegree.has(d)) indegree.set(n.id, (indegree.get(n.id) || 0) + 1);
    }
  }
  const topo = [];
  const queue = ids.filter(id => (indegree.get(id) || 0) === 0);
  while (queue.length) {
    const id = queue.shift();
    topo.push(id);
    for (const m of graphNodes) {
      if ((m.deps || []).includes(id) && indegree.has(m.id)) {
        const next = (indegree.get(m.id) || 0) - 1;
        indegree.set(m.id, next);
        if (next === 0) queue.push(m.id);
      }
    }
  }
  // If there's a cycle, topo will be shorter than ids.length. Rather
  // than crash, we walk what we got — the result is the best path
  // we can compute over the acyclic portion. Caller can `validate`
  // up front if they want strict.
  const perNodeMs = {};
  for (const id of ids) {
    const ns = stateNodes?.[id];
    perNodeMs[id] = (ns && Number.isFinite(ns.durationMs)) ? ns.durationMs : 0;
  }
  const bestFinish = {};
  const chainLen = {};   // path length (node count) ending at this id
  const prev = {};
  let bestEnd = null;
  let bestEndFinish = -Infinity;
  let bestEndChainLen = 0;
  for (const id of topo) {
    const deps = idToDeps.get(id) || [];
    let bestPred = null;
    let bestPredFinish = 0;
    let bestPredChainLen = 0;
    for (const d of deps) {
      const f = bestFinish[d];
      const cl = chainLen[d] || 0;
      if (typeof f !== 'number') continue;
      // Tie-break: weight first, then chain length. Prefer longer
      // dependency chains when totalMs is the same — useful for
      // fresh / pre-run state where durations are all 0 and the
      // user actually wants topological depth.
      if (f > bestPredFinish || (f === bestPredFinish && cl > bestPredChainLen)) {
        bestPredFinish = f;
        bestPredChainLen = cl;
        bestPred = d;
      }
    }
    bestFinish[id] = bestPredFinish + perNodeMs[id];
    chainLen[id] = bestPredChainLen + 1;
    prev[id] = bestPred;
    if (bestFinish[id] > bestEndFinish ||
        (bestFinish[id] === bestEndFinish && chainLen[id] > bestEndChainLen)) {
      bestEndFinish = bestFinish[id];
      bestEndChainLen = chainLen[id];
      bestEnd = id;
    }
  }
  // Recover the path by walking prev[] backwards.
  const path = [];
  for (let cur = bestEnd; cur != null; cur = prev[cur]) path.unshift(cur);
  return {
    path,
    totalMs: Math.max(0, bestEndFinish),
    perNodeMs,
  };
}

/**
 * Read every state file in `dir` and return a sorted listing.
 * Newest activity first (by `updatedAt`); secondary sort by sessionId
 * for deterministic ordering on ties.
 *
 * Stray non-JSON files and corrupt state are silently skipped — a
 * left-over `.tmp` from a crashed write doesn't break the listing.
 * Throws if `dir` does not exist; the caller decides whether that's
 * an error (CLI exit 2) or empty result (auto-create on first run).
 *
 * @param {string} dir
 * @returns {Array<{ sessionId: string, summary: StateSummary, failedNodes: Array<{ id: string, error?: string, attempts?: number }>, startedAt?: number, updatedAt?: number }>}
 */
export function listSessions(dir) {
  if (!fs.existsSync(dir)) {
    const e = new Error(`State directory ${dir} does not exist`);
    /** @type {any} */ (e).code = 'ENOENT';
    throw e;
  }
  const files = fs.readdirSync(dir).filter(f => f.endsWith('.json'));
  const sessions = [];
  for (const f of files) {
    try {
      const raw = fs.readFileSync(path.join(dir, f), 'utf8');
      const state = JSON.parse(raw);
      if (!state?.sessionId) continue;
      const { summary, failedNodes } = summarizeState(state);
      sessions.push({
        sessionId: state.sessionId,
        summary,
        failedNodes,
        startedAt: state.startedAt,
        updatedAt: state.updatedAt,
      });
    } catch {
      // Skip non-state JSON / corrupt files — see saveState's atomic
      // tmp+rename for the normal write path.
    }
  }
  sessions.sort((a, b) => (b.updatedAt - a.updatedAt) || a.sessionId.localeCompare(b.sessionId));
  return sessions;
}
