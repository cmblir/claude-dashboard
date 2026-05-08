#!/usr/bin/env node
// LazyClaw CLI — workflow + config commands.
import path from 'node:path';
import fs from 'node:fs';
import os from 'node:os';
import { pathToFileURL } from 'node:url';

async function loadEngine() {
  return import('./workflow/persistent.mjs');
}

function configPath() {
  const override = process.env.LAZYCLAW_CONFIG_DIR;
  const dir = override ? override : path.join(os.homedir(), '.lazyclaw');
  return path.join(dir, 'config.json');
}

function readConfig() {
  const p = configPath();
  if (!fs.existsSync(p)) return {};
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); }
  catch { return {}; }
}

function writeConfig(cfg) {
  const p = configPath();
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(cfg, null, 2));
}

// Synchronous, dependency-free resolver for the api-key the
// chat / agent flow sends. Mirrors config_features.resolveApiKey
// without forcing the dynamic import on every hot-path call.
//   1. cfg.authProfiles[provider] active label, if set
//   2. first profile in the array
//   3. legacy single `cfg["api-key"]` (pre-v3.93 configs)
function _resolveAuthKey(cfg, provider) {
  const arr = (cfg.authProfiles || {})[provider] || [];
  const active = (cfg.authActiveProfile || {})[provider];
  const hit = arr.find((p) => p && p.label === active) || arr[0];
  if (hit?.key) return hit.key;
  return cfg['api-key'] || '';
}

async function importWorkflow(file) {
  const abs = path.resolve(file);
  const url = pathToFileURL(abs).href;
  const mod = await import(url);
  if (!mod.nodes || !Array.isArray(mod.nodes)) {
    throw new Error(`Workflow file ${file} must export 'nodes' array`);
  }
  return mod.nodes;
}

// Wire SIGINT/SIGTERM to an AbortController so a workflow run aborts
// at the next node/level boundary (or sooner if execute() subscribed
// to the signal). Returns { signal, dispose } — the caller MUST call
// dispose() in a finally so we don't leak listeners across REPL turns.
//
// Exit-code semantics:
//   - normal success → 0
//   - normal failure → 1
//   - ABORT (signal-driven cancellation) → 130 (conventional Ctrl+C)
function makeRunSignal() {
  const ac = new AbortController();
  let received = null;
  const onSig = (sig) => {
    if (!received) {
      received = sig;
      ac.abort();
    } else {
      // Second signal: bail immediately without waiting for the engine.
      // Same "I really mean it" semantic the daemon uses.
      process.exit(130);
    }
  };
  const onSigint  = () => onSig('SIGINT');
  const onSigterm = () => onSig('SIGTERM');
  process.on('SIGINT', onSigint);
  process.on('SIGTERM', onSigterm);
  return {
    signal: ac.signal,
    dispose() {
      process.off('SIGINT', onSigint);
      process.off('SIGTERM', onSigterm);
    },
    wasAborted() { return ac.signal.aborted; },
  };
}

function exitCodeFor(result, sig) {
  if (sig.wasAborted() || result?.code === 'ABORT' || result?.error?.code === 'ABORT') return 130;
  return result?.success ? 0 : 1;
}

async function cmdRun(sessionId, file, opts = {}) {
  const nodes = await importWorkflow(file);
  const dir = opts.dir || '.workflow-state';
  const sig = makeRunSignal();
  try {
    if (opts['parallel-persistent']) {
      // --parallel-persistent: DAG with checkpoint + resume. Same state
      // file shape as the sequential path so a session id collision is
      // observable, not silently corrupting.
      const { runPersistentDag } = await loadEngine();
      const r = await runPersistentDag(nodes, { sessionId, dir, timeoutMs: opts.timeoutMs, signal: sig.signal, concurrency: opts.concurrency });
      console.log(JSON.stringify({
        success: r.success,
        executedNodes: r.executedNodes || [],
        failedAt: r.failedAt || null,
        mode: 'parallel-persistent',
        aborted: r.code === 'ABORT' || sig.wasAborted() || undefined,
        error: r.error || null,
      }));
      process.exit(exitCodeFor(r, sig));
    }
    if (opts.parallel) {
      // --parallel: schedule by `deps`. No state persistence — `runParallel`
      // is a one-shot DAG run; resume semantics belong to runPersistent or
      // runPersistentDag. failedAt + executedNodes are derived from results
      // so the JSON shape stays compatible with the sequential path.
      const { runParallel } = await import('./workflow/executor.mjs');
      const r = await runParallel(nodes, { signal: sig.signal, concurrency: opts.concurrency });
      const executedNodes = r.results.filter(x => x.status === 'success').map(x => x.id);
      console.log(JSON.stringify({
        success: r.success,
        executedNodes,
        failedAt: r.failedAt || null,
        mode: 'parallel',
        aborted: r.error?.code === 'ABORT' || sig.wasAborted() || undefined,
        error: r.error?.message || null,
      }));
      process.exit(exitCodeFor(r, sig));
    }
    const { runPersistent } = await loadEngine();
    const r = await runPersistent(nodes, { sessionId, dir, maxRetries: opts.maxRetries ?? 3, signal: sig.signal });
    console.log(JSON.stringify({
      success: r.success,
      executedNodes: r.executedNodes,
      failedAt: r.failedAt,
      mode: 'sequential',
      aborted: r.code === 'ABORT' || sig.wasAborted() || undefined,
    }));
    process.exit(exitCodeFor(r, sig));
  } finally {
    sig.dispose();
  }
}

// Pure transformation over a persisted state file — no execution.
// The shape mirrors the on-disk state plus a derived `summary` block
// so a script can decide "should I resume?" without parsing per-node
// statuses itself.
//
// With no sessionId, lists every state file in `dir` with a summary
// block per session — sorted by updatedAt descending so the most
// recently touched run sits at the top.
//
// Exit codes (single-session mode):
//   0 — state found and printed
//   1 — workflow completed (all nodes success, no work left to resume)
//   2 — state file not found
//   3 — workflow failed and is NOT resumable as-is (terminal failure
//       with retries exhausted; user must edit the workflow or state)
//
// Exit codes (list mode):
//   0 — listing produced (even if empty — empty dir is valid state)
//   2 — `dir` does not exist
async function cmdInspect(sessionId, opts = {}) {
  const dir = opts.dir || '.workflow-state';
  const { loadState } = await loadEngine();
  const { summarizeState, listSessions, aggregateNodeStats } = await import('./workflow/summary.mjs');

  // --aggregate (list mode): per-node statistics across every
  // session in the state dir — count, success/failed/pending/running
  // counts, and min/max/avg/total durations. Answers "which node
  // tends to be slow or fail across all my runs?" — a question
  // single-session inspect can't answer.
  if (!sessionId && opts.aggregate) {
    let stats;
    try {
      stats = aggregateNodeStats(dir, { filter: opts.filter });
    } catch (e) {
      if (e?.code === 'ENOENT') {
        console.error(`State directory ${dir} does not exist`);
        process.exit(2);
      }
      throw e;
    }
    // --aggregate --node <id>: drill into one node's cross-session
    // stats. Useful when you've already identified the bottleneck
    // and want to track its trend across runs without scrolling
    // the full table.
    if (opts.node) {
      const nodeStat = stats.nodeStats[opts.node];
      if (!nodeStat) {
        console.error(`No node "${opts.node}" found across sessions in ${dir} (known: ${Object.keys(stats.nodeStats).join(', ') || 'none'})`);
        process.exit(2);
      }
      console.log(JSON.stringify({
        dir,
        filter: opts.filter || null,
        sessionCount: stats.sessionCount,
        nodeId: opts.node,
        ...nodeStat,
      }, null, 2));
      process.exit(0);
    }
    console.log(JSON.stringify({ dir, filter: opts.filter || null, ...stats }, null, 2));
    process.exit(0);
  }

  // List mode — no sessionId given. Walks the state directory and
  // emits a summary per session. Per-node `nodes` map is omitted —
  // run with a session id for full detail.
  //
  // --status filters the listing by lifecycle: done, resumable,
  // failed, or running. Mutually exclusive — passing more than one
  // is an error rather than silent overlap so a script can rely on
  // the predicate it asked for.
  if (!sessionId) {
    let sessions;
    try {
      sessions = listSessions(dir);
    } catch (e) {
      if (e?.code === 'ENOENT') {
        console.error(`State directory ${dir} does not exist`);
        process.exit(2);
      }
      throw e;
    }
    const status = opts.status;
    if (status) {
      const valid = new Set(['done', 'resumable', 'failed', 'running']);
      if (!valid.has(status)) {
        console.error(`invalid --status: ${status} (expected one of: ${[...valid].join(', ')})`);
        process.exit(2);
      }
      sessions = sessions.filter(s => {
        if (status === 'done')      return s.summary.done;
        if (status === 'resumable') return s.summary.resumable;
        if (status === 'failed')    return s.summary.failed > 0;
        if (status === 'running')   return s.summary.running > 0;
        return true;
      });
    }
    // --filter <substr>: case-insensitive sessionId substring (same
    // semantic as v3.33's sessions/skills list filter).
    // --limit <N>: post-filter cap. Composes with --status (status
    // first, then filter, then limit).
    if (opts.filter) {
      const f = String(opts.filter).toLowerCase();
      sessions = sessions.filter(s => s.sessionId.toLowerCase().includes(f));
    }
    if (opts.limit !== undefined) {
      const n = parseInt(opts.limit, 10);
      if (Number.isFinite(n) && n > 0) sessions = sessions.slice(0, n);
    }
    console.log(JSON.stringify({ dir, status: status || null, sessions }, null, 2));
    process.exit(0);
  }

  const state = loadState(sessionId, dir);
  if (!state) {
    console.error(`No state for session ${sessionId} in ${dir}`);
    process.exit(2);
  }
  // --node <id>: drill into one node's state. Useful for scripts
  // checking a specific node ("did node 'classify' succeed?")
  // without reading the full state body. Exit codes mirror the
  // node's status:
  //   0 — node exists and status is success or pending or running
  //   1 — node exists and status is failed (script-friendly red)
  //   2 — node doesn't exist in this session (typo or wrong workflow)
  if (opts.node) {
    const ns = state.nodes?.[opts.node];
    if (!ns) {
      console.error(`No node "${opts.node}" in session ${sessionId} (known: ${Object.keys(state.nodes || {}).join(', ')})`);
      process.exit(2);
    }
    console.log(JSON.stringify({
      sessionId: state.sessionId,
      nodeId: opts.node,
      ...ns,
    }, null, 2));
    process.exit(ns.status === 'failed' ? 1 : 0);
  }
  // --slowest <N>: top N nodes by durationMs. Pure state-file
  // analysis — no workflow file needed (deps are irrelevant to
  // "which node took the longest"). Sorted descending; ties
  // broken by id ascending so the output is deterministic.
  if (opts.slowest !== undefined) {
    const n = parseInt(opts.slowest, 10);
    if (!Number.isFinite(n) || n <= 0) {
      console.error(`--slowest must be a positive integer (got ${JSON.stringify(opts.slowest)})`);
      process.exit(2);
    }
    const entries = Object.entries(state.nodes || {}).map(([id, ns]) => ({
      id,
      status: ns?.status || 'pending',
      durationMs: Number.isFinite(ns?.durationMs) ? ns.durationMs : 0,
      attempts: ns?.attempts ?? 0,
    }));
    entries.sort((a, b) => (b.durationMs - a.durationMs) || a.id.localeCompare(b.id));
    console.log(JSON.stringify({
      sessionId: state.sessionId,
      top: entries.slice(0, n),
    }, null, 2));
    process.exit(0);
  }
  // --critical-path <workflow.mjs>: compute the longest weighted path
  // through the DAG using each node's recorded durationMs. Useful for
  // "where's the bottleneck" analysis after a slow run. Requires the
  // workflow file because the state file doesn't persist deps.
  if (opts.criticalPath) {
    let workflowNodes;
    try {
      workflowNodes = await importWorkflow(opts.criticalPath);
    } catch (e) {
      console.error(`critical-path: ${e?.message || e}`);
      process.exit(2);
    }
    const { criticalPath } = await import('./workflow/summary.mjs');
    const result = criticalPath(workflowNodes, state.nodes || {});
    console.log(JSON.stringify({
      sessionId: state.sessionId,
      ...result,
    }, null, 2));
    process.exit(0);
  }
  const { summary, failedNodes } = summarizeState(state);
  // --summary trims the per-node `nodes` map and `order` from the
  // single-session output, leaving only `summary` + `failedNodes` +
  // timestamps. Useful for "I just want the headline" — the same
  // shape list-mode produces per session, so a script can normalize
  // output across both modes by passing --summary in single mode.
  const compact = !!opts.summary;
  const out = compact
    ? {
        sessionId: state.sessionId,
        dir,
        summary,
        failedNodes,
        startedAt: state.startedAt,
        updatedAt: state.updatedAt,
      }
    : {
        sessionId: state.sessionId,
        dir,
        summary,
        failedNodes,
        order: state.order,
        nodes: state.nodes,
        startedAt: state.startedAt,
        updatedAt: state.updatedAt,
      };
  console.log(JSON.stringify(out, null, 2));
  if (summary.done) process.exit(1);
  if (summary.failed > 0) process.exit(3);
  process.exit(0);
}

// Delete a persisted workflow state file. Idempotent — same shape
// as DELETE /workflows/<id> on the daemon. Confined to the state
// dir; a sessionId that resolves outside is rejected.
//
// Exit codes:
//   0 — file existed and was deleted (or didn't exist; either way ok)
//   1 — sessionId escapes the state dir / unsafe (refused)
//   2 — state directory does not exist (nothing to clear)
async function cmdClear(sessionId, opts = {}) {
  const dir = opts.dir || '.workflow-state';
  if (!fs.existsSync(dir)) {
    console.error(`State directory ${dir} does not exist`);
    process.exit(2);
  }
  const file = path.join(dir, `${sessionId}.json`);
  const resolvedDir = path.resolve(dir);
  const resolvedFile = path.resolve(file);
  if (!resolvedFile.startsWith(resolvedDir + path.sep) && resolvedFile !== resolvedDir) {
    console.error(`invalid sessionId: ${sessionId}`);
    process.exit(1);
  }
  const existed = fs.existsSync(resolvedFile);
  if (existed) fs.unlinkSync(resolvedFile);
  console.log(JSON.stringify({ ok: true, sessionId, removed: existed }));
  process.exit(0);
}

// Static validation of a workflow file. No execution — pure shape +
// topology check. Useful for CI:
//   $ lazyclaw validate ./flow.mjs && lazyclaw run job ./flow.mjs
//
// Checks (in order; the first hard failure short-circuits the rest
// for a fast CI signal, but soft warnings collect into `warnings`):
//   1. file imports cleanly and exports `nodes` (hard)
//   2. each node has a string `id` and an `execute` function (hard)
//   3. ids are unique (hard — duplicate is a silent bug)
//   4. deps reference known ids (warn — unknown deps are treated as
//      satisfied edges by topologicalLevels, so this is not fatal
//      but almost always a typo)
//   5. no cycles (hard — `topologicalLevels` returns `leftover` non-empty)
//
// Output JSON includes:
//   - ok: bool
//   - issues: hard-failure messages
//   - warnings: soft messages (still ok=true)
//   - levels: topological levels (one per concurrent batch)
//   - maxParallelism: max level width (informational — what the user's
//     `--concurrency` flag should at most be set to)
//
// Exit codes:
//   0 — valid (warnings ok)
//   1 — hard failure
//   2 — file path / import error (couldn't read or eval the file)
async function cmdValidate(file) {
  if (!file) { console.error('Usage: lazyclaw validate <workflow.mjs>'); process.exit(2); }
  let nodes;
  try {
    nodes = await importWorkflow(file);
  } catch (e) {
    console.error(`validate: ${e?.message || e}`);
    process.exit(2);
  }
  const issues = [];
  const warnings = [];
  // Per-node shape validation. We continue past per-node failures so
  // the user sees every issue at once, not one-per-edit-cycle.
  const ids = new Set();
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    const where = `nodes[${i}]`;
    if (!n || typeof n !== 'object') { issues.push(`${where}: must be an object`); continue; }
    if (typeof n.id !== 'string' || n.id.length === 0) { issues.push(`${where}: missing or non-string id`); continue; }
    if (typeof n.execute !== 'function') issues.push(`${where} (id=${n.id}): execute is not a function`);
    if (ids.has(n.id)) issues.push(`${where}: duplicate id "${n.id}"`);
    ids.add(n.id);
    if (n.deps !== undefined && !Array.isArray(n.deps)) {
      issues.push(`${where} (id=${n.id}): deps must be an array of strings`);
    }
  }
  // Dep reference check (warnings — topologicalLevels tolerates them).
  for (const n of nodes) {
    for (const d of n?.deps || []) {
      if (!ids.has(d)) warnings.push(`node "${n.id}": dep "${d}" not found in this workflow (will be treated as satisfied)`);
    }
  }
  // Topology / cycle check — only meaningful when shape passed.
  let levels = null;
  let maxParallelism = 0;
  if (issues.length === 0) {
    const { topologicalLevels } = await import('./workflow/executor.mjs');
    const { levels: lvls, leftover } = topologicalLevels(nodes);
    levels = lvls;
    maxParallelism = lvls.reduce((m, l) => Math.max(m, l.length), 0);
    if (leftover.length > 0) {
      issues.push(`workflow has a cycle or unreachable nodes: ${leftover.join(', ')}`);
    }
  }
  const ok = issues.length === 0;
  console.log(JSON.stringify({
    ok, file, nodeCount: nodes.length, issues, warnings,
    levels, maxParallelism,
  }, null, 2));
  process.exit(ok ? 0 : 1);
}

// Emit a workflow's DAG as Mermaid syntax. Useful for docs, code
// review, and quick visual debugging — Mermaid renders inline in
// GitHub markdown, GitLab, Notion, Obsidian, and most modern note
// tools, so the output is paste-ready.
//
// Direction is top-down (`graph TD`) by default; --lr flag flips it
// to left-right which is more readable for wide DAGs.
//
// Output goes to stdout as plain text (the Mermaid block contents,
// no fenced ```mermaid wrapper). The user adds the fence when
// embedding so the same output works for the editors that DON'T
// render markdown.
//
// Each node id is sanitized to a Mermaid-safe identifier (letters,
// digits, underscores) for the LHS reference, with the original id
// in brackets as the visible label. So `fetch-data` becomes
// `fetch_data[fetch-data]` in the output — Mermaid's id rules are
// stricter than ours.
async function cmdGraph(file, opts = {}) {
  if (!file) { console.error('Usage: lazyclaw graph <workflow.mjs> [--lr] [--state <session-id>] [--dir <state-dir>]'); process.exit(2); }
  let nodes;
  try {
    nodes = await importWorkflow(file);
  } catch (e) {
    console.error(`graph: ${e?.message || e}`);
    process.exit(2);
  }
  // --state <session-id> overlays current run status onto each node
  // (success/running/failed/pending). Without a state, every node
  // gets a neutral declaration. With state, nodes are tagged with a
  // CSS class via Mermaid's classDef + class syntax — paste-able
  // straight into a render, and renders that don't support classDef
  // (rare) just ignore the styling and show the raw graph.
  let state = null;
  if (opts.state) {
    const dir = opts.dir || '.workflow-state';
    const { loadState } = await loadEngine();
    state = loadState(opts.state, dir);
    if (!state) {
      console.error(`graph: no state for session ${opts.state} in ${dir}`);
      process.exit(2);
    }
  }
  const direction = opts.lr ? 'LR' : 'TD';
  const lines = [`graph ${direction}`];
  // Mermaid node ids must match /[a-zA-Z][a-zA-Z0-9_]*/ — anything
  // else needs the bracketed-label form. We always emit the bracket
  // label so the visible text is the user's actual id (no ambiguity)
  // while the LHS identifier is always Mermaid-safe.
  const safeId = (id) => {
    const s = String(id).replace(/[^a-zA-Z0-9_]/g, '_');
    return /^[a-zA-Z]/.test(s) ? s : `n_${s}`;
  };
  // Per-status visual cues. Unicode glyph in the label + classDef
  // class for color. The glyph alone works in plain markdown
  // viewers; the classDef adds color for Mermaid renders.
  const statusGlyph = {
    success: ' ✓',
    running: ' ⏳',
    failed:  ' ✗',
    pending: '',
  };
  const declared = new Set();
  const classedNodes = { success: [], running: [], failed: [], pending: [] };
  const declare = (id) => {
    if (declared.has(id)) return;
    let label = id;
    let cls = null;
    if (state) {
      const ns = state.nodes?.[id];
      const st = ns?.status || 'pending';
      label = id + (statusGlyph[st] || '');
      cls = st;
      classedNodes[st]?.push(safeId(id));
    }
    lines.push(`  ${safeId(id)}[${label}]`);
    declared.add(id);
  };
  for (const n of nodes) declare(n.id);
  for (const n of nodes) {
    for (const d of n.deps || []) {
      // Edge: dep → node. Mermaid syntax `a --> b`.
      lines.push(`  ${safeId(d)} --> ${safeId(n.id)}`);
    }
  }
  if (state) {
    // GitHub's Mermaid theme renders these well in both light/dark
    // mode. Operators rendering in their own theme can override.
    lines.push('  classDef success fill:#9f6,stroke:#363,stroke-width:1px;');
    lines.push('  classDef running fill:#fc6,stroke:#963,stroke-width:1px;');
    lines.push('  classDef failed  fill:#f66,stroke:#933,stroke-width:1px;');
    lines.push('  classDef pending fill:#ddd,stroke:#666,stroke-width:1px;');
    for (const [cls, ids] of Object.entries(classedNodes)) {
      if (ids.length === 0) continue;
      // `class id1,id2,id3 className` — Mermaid syntax for batch class assignment.
      lines.push(`  class ${ids.join(',')} ${cls};`);
    }
  }
  console.log(lines.join('\n'));
  process.exit(0);
}

async function cmdResume(sessionId, file, opts = {}) {
  const { runPersistent, runPersistentDag, loadState } = await loadEngine();
  const dir = opts.dir || '.workflow-state';
  const prior = loadState(sessionId, dir);
  if (!prior) {
    console.error(`No state for session ${sessionId} in ${dir}`);
    process.exit(2);
  }
  const nodes = await importWorkflow(file);
  const sig = makeRunSignal();
  try {
    // --parallel-persistent picks the DAG engine. Sequential by default
    // — same flag the run command uses, so the resume invocation
    // mirrors the original run invocation. (We can't auto-detect the
    // engine from the state file alone; both engines write the same
    // shape. The user knows which mode they originally ran.)
    if (opts['parallel-persistent']) {
      const r = await runPersistentDag(nodes, {
        sessionId, dir, timeoutMs: opts.timeoutMs,
        signal: sig.signal, concurrency: opts.concurrency,
      });
      console.log(JSON.stringify({
        success: r.success,
        executedNodes: r.executedNodes || [],
        failedAt: r.failedAt || null,
        resumed: true,
        mode: 'parallel-persistent',
        aborted: r.code === 'ABORT' || sig.wasAborted() || undefined,
        error: r.error || null,
      }));
      process.exit(exitCodeFor(r, sig));
    }
    const r = await runPersistent(nodes, { sessionId, dir, maxRetries: opts.maxRetries ?? 3, signal: sig.signal });
    console.log(JSON.stringify({
      success: r.success,
      executedNodes: r.executedNodes,
      failedAt: r.failedAt,
      resumed: true,
      mode: 'sequential',
      aborted: r.code === 'ABORT' || sig.wasAborted() || undefined,
    }));
    process.exit(exitCodeFor(r, sig));
  } finally {
    sig.dispose();
  }
}

async function cmdConfigEdit() {
  // Open config.json in $EDITOR (or sensible default), then validate
  // the result before letting the user walk away believing the edit
  // landed. A bad JSON syntax error here would silently break every
  // future invocation, so we re-parse the file post-edit and refuse
  // to leave it broken.
  const p = configPath();
  // Ensure the file exists with at least an empty object so $EDITOR
  // doesn't open a blank scratch buffer the user accidentally saves
  // as nothing.
  fs.mkdirSync(path.dirname(p), { recursive: true });
  if (!fs.existsSync(p)) fs.writeFileSync(p, '{}\n');
  const editor = process.env.LAZYCLAW_EDITOR || process.env.VISUAL || process.env.EDITOR || 'vi';
  const { spawn } = await import('node:child_process');
  await new Promise((resolve, reject) => {
    const child = spawn(editor, [p], { stdio: 'inherit' });
    child.on('exit', code => {
      if (code === 0) resolve();
      else reject(new Error(`editor exited ${code}`));
    });
    child.on('error', reject);
  });
  // Validate the result. If JSON.parse throws, restore from a backup
  // we made before the edit (the original content if the file existed,
  // or an empty {} otherwise — the file always has SOME valid JSON).
  try {
    const txt = fs.readFileSync(p, 'utf8');
    JSON.parse(txt);
    console.log(JSON.stringify({ ok: true, path: p }));
  } catch (e) {
    console.error(`config: edit produced invalid JSON: ${e.message}`);
    console.error(`Re-run \`lazyclaw config edit\` to fix; nothing else has been touched.`);
    process.exit(1);
  }
}

function cmdConfigSet(key, value) {
  const cfg = readConfig();
  cfg[key] = value;
  writeConfig(cfg);
  console.log(JSON.stringify({ ok: true, key, value }));
}

function applyOnboardConfig(currentCfg, flags) {
  // Honors the OpenClaw-style unified provider/model string ("anthropic/claude-opus-4-7")
  // by splitting it, but explicit --provider always wins.
  const { parseProviderModel } = require_registry_sync();
  const next = { ...currentCfg };
  if (flags.model) {
    const parsed = parseProviderModel(flags.model);
    if (parsed.provider && !flags.provider) next.provider = parsed.provider;
    next.model = parsed.model || flags.model;
  }
  if (flags.provider) next.provider = flags.provider;
  if (flags['api-key']) next['api-key'] = flags['api-key'];
  return next;
}

// Module is ESM but we want a synchronous-looking helper for the CLI flow.
// Cache the import on first use so we don't pay for it on every config call.
let _registryMod = null;
function require_registry_sync() {
  if (!_registryMod) {
    // eslint-disable-next-line no-undef
    throw new Error('registry module not pre-loaded — call ensureRegistry() first');
  }
  return _registryMod;
}
async function ensureRegistry() {
  if (!_registryMod) _registryMod = await import('./providers/registry.mjs');
  return _registryMod;
}

async function cmdOnboard(flags) {
  await ensureRegistry();
  if (!flags['non-interactive']) {
    // Interactive onboarding is a single guided prompt sequence — kept tiny.
    // For automation always use --non-interactive plus the value flags.
    // Skip the prompts entirely when the user passed --pick (or no
    // provider yet AND we're on a TTY) so they get the full picker.
    const wantPicker = !!flags.pick;
    if (wantPicker || (!flags.provider && process.stdin.isTTY)) {
      const picked = await _pickProviderInteractive();
      if (picked) {
        flags.provider = flags.provider || picked.provider;
        if (picked.model && !flags.model) flags.model = picked.model;
      }
    }
    const readline = await import('node:readline');
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    const ask = q => new Promise(resolve => rl.question(q, resolve));
    if (!flags.provider) {
      const provs = Object.keys(_registryMod.PROVIDERS).join('|');
      const noKeyHint = '\x1b[38;5;208mclaude-cli\x1b[0m (subscription, no key) is the default';
      process.stdout.write(`hint: ${noKeyHint}\n`);
      flags.provider = (await ask(`provider [${provs}]: `)).trim() || 'claude-cli';
    }
    if (!flags.model) {
      const meta = (_registryMod.PROVIDER_INFO || {})[flags.provider] || {};
      const sample = (meta.suggestedModels || []).slice(0, 4).join(' · ') || '(any)';
      const dflt = meta.defaultModel || '';
      flags.model = (await ask(`model (e.g. ${sample}) [${dflt}]: `)).trim() || dflt;
    }
    // Only ask for api-key when the picked provider actually needs one.
    // claude-cli / ollama / mock all skip this — that's the whole point
    // of supporting them.
    const meta = (_registryMod.PROVIDER_INFO || {})[flags.provider] || {};
    if (meta.requiresApiKey && !flags['api-key']) {
      const prefix = meta.keyPrefix ? ` (starts with "${meta.keyPrefix}")` : '';
      flags['api-key'] = (await ask(`api-key${prefix}: `)).trim();
    }
    rl.close();
  }
  const next = applyOnboardConfig(readConfig(), flags);
  if (!next.provider) { console.error('onboard: provider is required'); process.exit(2); }
  writeConfig(next);
  console.log(JSON.stringify({ ok: true, written: configPath(), provider: next.provider, model: next.model || null, hasApiKey: !!next['api-key'] }));
}

async function cmdDoctor() {
  await ensureRegistry();
  const cfg = readConfig();
  const issues = [];
  if (!cfg.provider) issues.push('config.provider is missing — run `lazyclaw onboard`');
  // Only flag a missing api-key when the picked provider actually
  // requires one. claude-cli / ollama / mock all run keylessly, so the
  // previous `provider !== 'mock'` check produced false positives.
  const _meta = (_registryMod.PROVIDER_INFO || {})[cfg.provider] || {};
  if (cfg.provider && _meta.requiresApiKey && !cfg['api-key']) {
    issues.push(`config['api-key'] is missing for provider "${cfg.provider}"`);
  }
  if (cfg.provider && !PROVIDERS_HAS(_registryMod.PROVIDERS, cfg.provider)) {
    issues.push(`unknown provider "${cfg.provider}" — registered: ${Object.keys(_registryMod.PROVIDERS).join(', ')}`);
  }
  // Workflow state health — informational counters that show whether
  // the user has any failed or stuck workflow runs to attend to. We
  // don't push these to `issues` (a stuck workflow doesn't break the
  // CLI) but they surface in the output so `lazyclaw doctor | jq` can
  // surface them in dashboards.
  const stateDir = process.env.LAZYCLAW_WORKFLOW_STATE_DIR || '.workflow-state';
  let workflows = null;
  try {
    const { listSessions } = await import('./workflow/summary.mjs');
    if (fs.existsSync(stateDir)) {
      const sessions = listSessions(stateDir);
      const counts = { total: sessions.length, done: 0, resumable: 0, failed: 0, running: 0 };
      for (const s of sessions) {
        if (s.summary.done)         counts.done++;
        if (s.summary.resumable)    counts.resumable++;
        if (s.summary.failed > 0)   counts.failed++;
        if (s.summary.running > 0)  counts.running++;
      }
      workflows = { dir: stateDir, ...counts };
      // Surface a hint when there are stuck runs that the engine will
      // demote to pending on next load — this often signals a process
      // that crashed; the user should at least know.
      if (counts.running > 0) {
        issues.push(`${counts.running} workflow session(s) have 'running' nodes from a prior interrupted run — they will be demoted to pending on next resume.`);
      }
    } else {
      workflows = { dir: stateDir, present: false };
    }
  } catch (e) {
    workflows = { dir: stateDir, error: e?.message || String(e) };
  }
  const ok = issues.length === 0;
  const out = {
    ok,
    configPath: configPath(),
    provider: cfg.provider || null,
    model: cfg.model || null,
    hasApiKey: !!cfg['api-key'],
    nodeVersion: process.version,
    platform: `${process.platform}-${process.arch}`,
    issues,
    knownProviders: Object.keys(_registryMod.PROVIDERS),
    workflows,
    timestamp: new Date().toISOString(),
  };
  console.log(JSON.stringify(out, null, 2));
  process.exit(ok ? 0 : 1);
}

function PROVIDERS_HAS(map, name) {
  return Object.prototype.hasOwnProperty.call(map, name);
}

async function cmdStatus() {
  await ensureRegistry();
  const cfg = readConfig();
  const out = {
    configPath: configPath(),
    provider: cfg.provider || null,
    model: cfg.model || null,
    keyMasked: _registryMod.maskApiKey(cfg['api-key']),
  };
  console.log(JSON.stringify(out, null, 2));
}

const SLASH_COMMANDS = [
  { cmd: '/help',   help: 'list available slash commands' },
  { cmd: '/status', help: 'print current provider, model, masked key' },
  { cmd: '/new',    help: 'clear conversation and start over' },
  { cmd: '/reset',  help: 'alias for /new' },
  { cmd: '/usage',  help: 'show message count + chars sent so far' },
  { cmd: '/skill',  help: 'switch active skills: /skill review,style (no arg → clear)' },
  { cmd: '/provider', help: 'switch provider: /provider openai (no arg → print current)' },
  { cmd: '/model',  help: 'switch model: /model gpt-4.1 or anthropic/claude-opus-4-7' },
  { cmd: '/exit',   help: 'leave the chat' },
];

function readVersionFromRepo() {
  // Two source-of-truth lookups, in order:
  //   1. The npm-published package's own package.json (sits next to
  //      cli.mjs once installed via `npm i -g lazyclaw`).
  //   2. The monorepo's VERSION file at the repo root (one or two
  //      levels up depending on how the file is symlinked / copied).
  // Either one wins on first hit. Falls back to '0.0.0' so the CLI
  // never crashes on a stripped-down install.
  const here = path.dirname(new URL(import.meta.url).pathname);
  const candidates = [
    { kind: 'pkg',     path: path.resolve(here, './package.json') },
    { kind: 'pkg',     path: path.resolve(here, '../package.json') },
    { kind: 'version', path: path.resolve(here, '../../VERSION') },
    { kind: 'version', path: path.resolve(here, '../../../VERSION') },
  ];
  for (const c of candidates) {
    try {
      const raw = fs.readFileSync(c.path, 'utf8').trim();
      if (!raw) continue;
      if (c.kind === 'pkg') {
        const v = JSON.parse(raw).version;
        if (v) return v;
      } else {
        return raw;
      }
    } catch { /* keep trying */ }
  }
  return '0.0.0';
}

async function cmdVersion() {
  const out = {
    version: readVersionFromRepo(),
    nodeVersion: process.version,
    platform: `${process.platform}-${process.arch}`,
  };
  console.log(JSON.stringify(out));
}

// Subcommand inventory used by `lazyclaw completion`. Single source of
// truth so adding a subcommand updates the completion script too. The
// dispatcher in main() is the runtime authority; this list mirrors it.
const SUBCOMMANDS = [
  'run', 'resume', 'inspect', 'clear', 'validate', 'graph',
  'config', 'chat', 'agent',
  'doctor', 'status', 'onboard',
  'sessions', 'skills', 'providers',
  'daemon', 'version', 'completion', 'help',
  'export', 'import',
  'rates',
  // OpenClaw-parity subsurfaces (v3.93–v3.98)
  'auth', 'pairing', 'nodes', 'message', 'workspace', 'browse', 'cron',
  // v3.99.6 — multi-step setup wizard + lazyclaw-only dashboard
  'setup', 'dashboard',
];

const SUBCOMMAND_SUBS = {
  config:    ['get', 'set', 'list', 'delete', 'unset', 'path', 'edit', 'validate'],
  sessions:  ['list', 'show', 'clear', 'export', 'search'],
  skills:    ['list', 'show', 'install', 'remove', 'search'],
  providers: ['list', 'info', 'test'],
  rates:     ['list', 'set', 'delete', 'shape', 'validate', 'copy'],
  completion: ['bash', 'zsh'],
  auth:      ['list', 'add', 'remove', 'use', 'rotate'],
  pairing:   ['list', 'add', 'remove'],
  nodes:     ['list', 'register', 'remove'],
  message:   ['list', 'add', 'remove', 'send'],
  workspace: ['list', 'init', 'show', 'remove', 'path'],
  cron:      ['list', 'add', 'remove', 'show', 'sync', 'run'],
};

function bashCompletion() {
  // Standard bash COMPREPLY pattern. We split COMP_WORDS into:
  //   [0] = lazyclaw, [1] = subcommand, [2+] = subcommand args.
  // Two-level completion: word index 1 → top subcommands; index 2 → the
  // sub-subcommand list (if defined for that subcommand). Beyond index 2
  // we don't try to enumerate dynamic items (session ids etc.) — that
  // would require running the CLI on every <Tab>, which is too slow.
  const subs = SUBCOMMANDS.join(' ');
  const subSubsCases = Object.entries(SUBCOMMAND_SUBS)
    .map(([name, list]) => `      ${name})\n        COMPREPLY=( $(compgen -W "${list.join(' ')}" -- "$cur") )\n        ;;`)
    .join('\n');
  return `# lazyclaw bash completion. Source from your shell:
#   eval "$(node /path/to/cli.mjs completion bash)"
_lazyclaw_completion() {
  local cur prev words cword
  _init_completion 2>/dev/null || {
    cur="\${COMP_WORDS[COMP_CWORD]}"
    prev="\${COMP_WORDS[COMP_CWORD-1]}"
    cword=$COMP_CWORD
  }
  if [ "$cword" -eq 1 ]; then
    COMPREPLY=( $(compgen -W "${subs}" -- "$cur") )
    return 0
  fi
  if [ "$cword" -eq 2 ]; then
    case "\${COMP_WORDS[1]}" in
${subSubsCases}
    esac
    return 0
  fi
  return 0
}
complete -F _lazyclaw_completion lazyclaw
`;
}

function zshCompletion() {
  // _arguments-style. We list subcommands then dispatch on the first
  // positional via a single `_describe`. Sub-subcommands handled by a
  // case inside the function. Same coverage rationale as bash.
  const subs = SUBCOMMANDS.map(s => `    '${s}'`).join('\n');
  const subSubsCases = Object.entries(SUBCOMMAND_SUBS)
    .map(([name, list]) => `      (${name}) _values 'sub' ${list.map(v => `'${v}'`).join(' ')} ;;`)
    .join('\n');
  return `#compdef lazyclaw
# lazyclaw zsh completion. Add to fpath, or eval inline:
#   eval "$(node /path/to/cli.mjs completion zsh)"
_lazyclaw() {
  local subs=(
${subs}
  )
  if (( CURRENT == 2 )); then
    _values 'subcommand' \${subs[@]}
    return
  fi
  if (( CURRENT == 3 )); then
    case \${words[2]} in
${subSubsCases}
    esac
    return
  fi
}
compdef _lazyclaw lazyclaw
_lazyclaw "$@"
`;
}

async function cmdCompletion(shell) {
  if (shell === 'bash') { process.stdout.write(bashCompletion()); return; }
  if (shell === 'zsh')  { process.stdout.write(zshCompletion()); return; }
  console.error('Usage: lazyclaw completion <bash|zsh>');
  process.exit(2);
}

const BUNDLE_VERSION = 1;

async function cmdExport(flags) {
  // Portable bundle: config + every installed skill + (optionally) every
  // persisted session. Writes JSON to stdout so the caller pipes it
  // wherever they want — disk, scp, gist, encrypted vault.
  //
  // Secrets default to redacted because a bundle on a teammate's laptop
  // shouldn't carry your API keys. --include-secrets flips that behavior
  // for the use case of "back up MY laptop to MY external drive".
  const skillsMod = await import('./skills.mjs');
  const sessionsMod = await import('./sessions.mjs');
  const cfgDir = path.dirname(configPath());
  const cfg = readConfig();
  const safeCfg = { ...cfg };
  if (!flags['include-secrets']) {
    if (safeCfg['api-key']) safeCfg['api-key'] = '***REDACTED***';
  }
  const skills = skillsMod.listSkills(cfgDir).map(s => ({
    name: s.name,
    content: skillsMod.loadSkill(s.name, cfgDir),
  }));
  const includeSessions = !!flags['include-sessions'];
  const sessions = sessionsMod.listSessions(cfgDir).map(s => {
    const base = { id: s.id, mtime: new Date(s.mtimeMs).toISOString(), bytes: s.bytes };
    if (includeSessions) base.turns = sessionsMod.loadTurns(s.id, cfgDir);
    return base;
  });
  const bundle = {
    bundleVersion: BUNDLE_VERSION,
    exportedAt: new Date().toISOString(),
    config: safeCfg,
    skills,
    sessions,
    secretsIncluded: !!flags['include-secrets'],
    sessionContentIncluded: includeSessions,
  };
  process.stdout.write(JSON.stringify(bundle, null, 2) + '\n');
}

async function cmdImport(flags) {
  // Read JSON bundle from stdin (or --from <path>). Apply with these rules:
  //   - config keys land via writeConfig; existing keys are overwritten
  //     UNLESS --no-overwrite-config is set.
  //   - skills land via installSkill; existing names are skipped UNLESS
  //     --overwrite-skills is set.
  //   - sessions land only when the bundle carried turn content AND
  //     --import-sessions is set; existing session files are NEVER
  //     overwritten (we don't want to clobber active conversations).
  //   - REDACTED api-key in the bundle is dropped (never written).
  const skillsMod = await import('./skills.mjs');
  const sessionsMod = await import('./sessions.mjs');
  const cfgDir = path.dirname(configPath());
  let raw;
  if (flags.from) raw = fs.readFileSync(flags.from, 'utf8');
  else {
    raw = await new Promise(resolve => {
      let buf = '';
      process.stdin.setEncoding('utf8');
      process.stdin.on('data', d => { buf += d; });
      process.stdin.on('end', () => resolve(buf));
    });
  }
  let bundle;
  try { bundle = JSON.parse(raw); }
  catch (e) { console.error(`import: invalid JSON: ${e.message}`); process.exit(2); }
  if (!bundle || typeof bundle !== 'object' || bundle.bundleVersion !== BUNDLE_VERSION) {
    console.error(`import: unsupported bundleVersion (got ${bundle?.bundleVersion}, expected ${BUNDLE_VERSION})`);
    process.exit(2);
  }
  const stats = { configKeys: 0, skillsAdded: 0, skillsSkipped: 0, sessionsAdded: 0, sessionsSkipped: 0 };
  // Config
  if (bundle.config && typeof bundle.config === 'object') {
    const existing = readConfig();
    const next = flags['no-overwrite-config']
      ? { ...bundle.config, ...existing }    // existing wins
      : { ...existing, ...bundle.config };   // bundle wins (default)
    // Drop redacted secrets so we never write the placeholder string.
    if (next['api-key'] === '***REDACTED***') delete next['api-key'];
    writeConfig(next);
    stats.configKeys = Object.keys(bundle.config).length;
  }
  // Skills
  for (const s of bundle.skills || []) {
    if (!s?.name || typeof s.content !== 'string') continue;
    const file = skillsMod.skillPath(s.name, cfgDir);
    if (fs.existsSync(file) && !flags['overwrite-skills']) {
      stats.skillsSkipped += 1;
      continue;
    }
    skillsMod.installSkill(s.name, s.content, cfgDir);
    stats.skillsAdded += 1;
  }
  // Sessions — never overwrite, only add new
  if (flags['import-sessions']) {
    for (const sess of bundle.sessions || []) {
      if (!sess?.id || !Array.isArray(sess.turns)) continue;
      try {
        const file = sessionsMod.sessionPath(sess.id, cfgDir);
        if (fs.existsSync(file)) { stats.sessionsSkipped += 1; continue; }
        for (const t of sess.turns) {
          if (t?.role && typeof t.content === 'string') {
            sessionsMod.appendTurn(sess.id, t.role, t.content, cfgDir);
          }
        }
        stats.sessionsAdded += 1;
      } catch { stats.sessionsSkipped += 1; }
    }
  }
  console.log(JSON.stringify({ ok: true, ...stats }));
}

// One-line summaries used by `lazyclaw help`. Format keeps it scan-friendly
// in a 80-column terminal: subcommand padded to 12 chars, then the summary.
const HELP_SUMMARIES = {
  run:        'Execute a workflow file (run <session-id> <workflow.mjs>)',
  resume:     'Resume a workflow from its last persisted checkpoint',
  config:     'Manage local config (get|set|list|delete <key>)',
  chat:       'Interactive REPL with the configured provider',
  agent:      'One-shot prompt: streams a single response, exits',
  doctor:     'Print diagnostic JSON; exits non-zero on issues',
  status:     'Print current provider/model/masked key as JSON',
  onboard:    'Guided setup (use --non-interactive for scripts)',
  sessions:   'Persistent chat sessions (list|show|clear|export)',
  skills:     'Markdown skill bundles (list|show|install|remove)',
  providers:  'Inspect registered providers (list|info <name>)',
  daemon:     'Run the local HTTP gateway (--port, --auth-token, --allow-origin)',
  version:    'Print VERSION + node + platform as JSON',
  completion: 'Emit shell completion script (completion <bash|zsh>)',
  export:     'Dump config + skills (+ optional sessions) as a JSON bundle',
  import:     'Apply a JSON bundle from stdin or --from <path>',
  rates:      'Manage cost rate-cards in config (rates list|set <provider/model>|delete|shape)',
  auth:       'Multiple keys per provider (auth list|add|remove|use|rotate <provider>)',
  pairing:    'Sender allowlist for the messaging surface (pairing list|add|remove <id>)',
  nodes:      'Companion device registration (nodes list|register|remove <id>)',
  message:    'Outbound webhook messaging (message list|add|remove|send <name>)',
  workspace:  'AGENTS.md / SOUL.md / TOOLS.md system-prompt convention (workspace list|init|show|remove|path)',
  browse:     'Fetch a URL and emit Markdown on stdout (browse <url> [--max-bytes <N>])',
  cron:       'Schedule recurring agent runs via launchd / crontab (cron list|add|remove|show|sync|run)',
  setup:      'OpenClaw-style multi-step first-run wizard (provider + workspace + skill + webhook + ping)',
  dashboard:  'Launch the lazyclaw-only web UI (lighter than the full lazyclaude dashboard)',
  inspect:    'Print persisted workflow state without executing',
  clear:      'Delete a persisted workflow state file (idempotent)',
  validate:   'Static-check a workflow file: shape, deps, cycles, parallelism',
  graph:      'Emit workflow DAG as Mermaid syntax (paste-ready for docs)',
};

// Detailed usage per subcommand for `lazyclaw help <name>`. Kept as flat
// strings so the help output is identical in every terminal.
const HELP_DETAILS = {
  run: 'Usage: lazyclaw run <session-id> <workflow.mjs> [--parallel | --parallel-persistent] [--concurrency <N>]\n  Default: runPersistent — sequential, persists state, resumable via `lazyclaw resume`.\n  --parallel: runParallel — topological-level DAG, in-memory only, NOT resumable.\n  --parallel-persistent: runPersistentDag — DAG + checkpoint + resume.\n  --concurrency <N>: cap in-flight nodes within a level (DAG modes only). 0/missing → unbounded.\n  Workflow file exports `nodes`; deps: string[] declares dependencies for both DAG modes.',
  resume: 'Usage: lazyclaw resume <session-id> <workflow.mjs> [--parallel-persistent] [--concurrency <N>]\n  Re-enters a previously persisted run; succeeds nodes are skipped.\n  Pass --parallel-persistent to resume a DAG run (must match the original run\'s mode).\n  --concurrency <N>: cap in-flight nodes per level (DAG mode only).',
  inspect: 'Usage: lazyclaw inspect [<session-id>] [--dir <state-dir>] [--status done|resumable|failed|running] [--summary] [--filter <substr>] [--limit <N>] [--node <node-id>] [--slowest <N>] [--critical-path <workflow.mjs>] [--aggregate]\n  With no session-id: list every persisted session in the state dir, sorted by recency.\n  --aggregate (list mode): per-node stats across all sessions (count, success/failed/pending/running, min/max/avg/total duration).\n  --status filters the listing to a single lifecycle bucket.\n  --filter / --limit refine list-mode further (case-insensitive sessionId substring + post-filter cap).\n  --summary trims per-node detail in single-session mode (matches list-mode shape).\n  --node <id>: print just that node\'s state. Exit 0 success/pending/running, 1 failed, 2 no such node.\n  --slowest <N>: top N nodes by durationMs (descending, ties broken by id).\n  --critical-path <workflow.mjs>: longest-weighted-path analysis using each node\'s recorded durationMs (bottleneck finder).\n  With a session-id (no per-node flag): print full state. Exit code: 0=resumable, 1=fully done, 2=no state, 3=terminal failure.',
  clear: 'Usage: lazyclaw clear <session-id> [--dir <state-dir>]\n  Delete the state file for <session-id>. Idempotent — exits 0 whether the file existed or not.\n  Refuses sessionIds that resolve outside <state-dir>. Mirrors DELETE /workflows/<id> on the daemon.',
  validate: 'Usage: lazyclaw validate <workflow.mjs>\n  Static check: load + shape + dep + cycle + parallelism estimate.\n  Exit 0 valid · 1 hard failure (issues populated) · 2 file/import error.',
  graph: 'Usage: lazyclaw graph <workflow.mjs> [--lr] [--state <session-id>] [--dir <state-dir>]\n  Emit the workflow DAG as Mermaid syntax (graph TD by default; --lr for left-right).\n  --state overlays a persisted run\'s status (success ✓ / running ⏳ / failed ✗ / pending) with classDef styling.\n  Output is paste-ready for GitHub markdown / Notion / Obsidian.',
  config: 'Usage: lazyclaw config <get|set|list|delete|path|edit|validate> [key] [value]\n  Local key-value config at $LAZYCLAW_CONFIG_DIR/config.json (default ~/.lazyclaw).\n  `path` prints the file location; `edit` opens it in $EDITOR (or $LAZYCLAW_EDITOR / $VISUAL / vi) and validates JSON on save.\n  `validate` checks the structural integrity of the whole config file (typed values, known providers, rate-card shape).',
  chat: 'Usage: lazyclaw chat [--session <id>] [--skill name1,name2] [--workspace <name>] [--pick] [--sandbox docker:<image>] [--sandbox-network <net>] [--sandbox-mount <m>] [--sandbox-env <e>]\n  --session persists turns to <configDir>/sessions/<id>.jsonl across invocations.\n  --skill composes named skills into a system message at the head of the conversation.\n  --workspace stitches AGENTS.md/SOUL.md/TOOLS.md from <configDir>/workspaces/<name>/ into the system prompt.\n  --pick opens an interactive provider/model picker before the prompt (also auto-fires on first run).\n  --sandbox routes the underlying claude CLI through `docker run --rm -i --network <net> -v cwd:cwd ...` (default --network=none).',
  agent: 'Usage: lazyclaw agent <prompt|-> [--provider X] [--model Y] [--skill list] [--workspace <name>] [--thinking N] [--show-thinking] [--usage] [--cost] [--sandbox docker:<image>]\n  One-shot non-interactive call. Pass "-" as the prompt to read from stdin.\n  --workspace stitches AGENTS.md/SOUL.md/TOOLS.md into the system prompt (combines with --skill).\n  --usage prints normalized {inputTokens, outputTokens, ...} to stderr after the response.\n  --cost adds a cost line on stderr when config.rates has a card for the active provider/model.\n  --sandbox docker:<image> wraps the subprocess provider (claude-cli) in a Docker container; --sandbox-network defaults to none.',
  doctor: 'Usage: lazyclaw doctor\n  Validates configuration and registered providers. Exits 0 only when no issues.',
  status: 'Usage: lazyclaw status\n  Provider, model, and masked API key. Never prints the raw key.',
  onboard: 'Usage: lazyclaw onboard [--non-interactive] [--provider X] [--model Y] [--api-key Z]\n  --model accepts the unified "provider/model" string (e.g. anthropic/claude-opus-4-7).',
  sessions: 'Usage: lazyclaw sessions <list [--filter <substr>] [--limit <N>]|show <id>|clear <id>|export <id> [--format md|json|text]|search <query> [--regex]>\n  list — recent sessions by mtime; --filter caps to ids containing substring (case-insensitive); --limit caps result count.\n  export — render in chosen format (md default for human sharing, json for tooling, text for paste).\n  search — case-insensitive substring (or --regex pattern) match across all session content; returns first excerpt + match count per matching session.',
  skills: 'Usage: lazyclaw skills <list [--filter <substr>] [--limit <N>]|show <name>|install <user/repo[@ref][:path]> [--prefix <p>] [--force] | install <name> [--from <path> | --from-url <https://...>]|remove <name>|search <query> [--regex]>\n  list — installed skills; --filter caps to names containing substring (case-insensitive); --limit caps result count.\n  install <user>/<repo>[@<ref>][:<subpath>] — fetch a GitHub tarball, install every .md under skills/ (or the explicit subpath, or repo root). Default ref is `main`.\n    --prefix prepends a name prefix so a multi-skill repo doesn\'t collide with locally-managed skills. --force overwrites existing names.\n  install <name> --from <path> | --from-url <https://...> — single-file install. --from-url is HTTPS-only with a 1 MiB cap.\n  search — case-insensitive substring (or --regex) match across all skill markdown bodies; returns first excerpt + match count per skill.',
  providers: 'Usage: lazyclaw providers <list [--filter <substr>] [--limit <N>] | info <name> | test <name> [--model X] [--prompt T] | test [--all] [--prompt T]>\n  list — registered providers (--filter case-insensitive name substring; --limit caps post-filter count).\n  info — static metadata: requiresApiKey, defaultModel, suggestedModels, endpoint.\n  test — send a 1-token "ping" through the provider and report ok/error + duration.\n         Useful after configuring an API key to verify it works before relying on it.\n         No name OR --all: tests every registered provider in parallel; exits 0 only when ALL pass.',
  daemon: 'Usage: lazyclaw daemon [--port <N>] [--once] [--auth-token <token>] [--allow-origin <origin>] [--rate-limit <N>] [--response-cache] [--log <level>] [--shutdown-timeout-ms <N>] [--cost-cap-<currency> <N> ...] [--workflow-state-dir <dir>]\n  Always binds 127.0.0.1. --port 0 picks a random port and prints the URL.\n  --auth-token also reads $LAZYCLAW_AUTH_TOKEN; --allow-origin also reads $LAZYCLAW_ALLOW_ORIGINS.\n  --rate-limit <N> caps each remote IP at N requests / 60 s.\n  --response-cache enables process-scoped memoization; per-request opt-in via body.cache.\n  --log <debug|info|warn|error> emits JSON-line access logs on stderr (also reads $LAZYCLAW_LOG_LEVEL).\n  --shutdown-timeout-ms <N> caps graceful drain on SIGINT/SIGTERM (default 10000). Second signal forces immediate exit.\n  --cost-cap-usd 100 (or any currency code in lowercase) rejects POST /agent + /chat with 402 once cumulative cost reaches the cap.\n  --workflow-state-dir <dir> backs GET /workflows + GET /workflows/<id> (default .workflow-state, also reads $LAZYCLAW_WORKFLOW_STATE_DIR).',
  version: 'Usage: lazyclaw version\n  Aliases: --version, -v.',
  completion: 'Usage: lazyclaw completion <bash|zsh>\n  bash:   eval "$(lazyclaw completion bash)"\n  zsh:    lazyclaw completion zsh > "${fpath[1]}/_lazyclaw"',
  export: 'Usage: lazyclaw export [--include-secrets] [--include-sessions] > bundle.json\n  --include-secrets keeps the raw api-key in the bundle (default redacts it).\n  --include-sessions adds full turn content (default keeps metadata only).',
  import: 'Usage: lazyclaw import [--from <path>] [--overwrite-skills] [--no-overwrite-config] [--import-sessions]\n  Reads JSON from stdin (or --from <path>). Sessions are NEVER overwritten.\n  Redacted api-keys (***REDACTED***) are dropped, never written.',
  rates: 'Usage: lazyclaw rates <list [--filter <substr>] [--limit <N>] | set <provider/model> --input <N> --output <N> [--cache-read <N>] [--cache-create <N>] [--currency USD] | delete <key> | shape | validate | copy <src> <dst> [--force]>\n  Rates are per million tokens. costFromUsage uses cfg.rates to compute the cost block in /usage and body.cost.\n  `list` accepts --filter (case-insensitive key substring) and --limit (post-filter cap), same shape sessions/skills/workflows lists use.\n  `shape` prints the reference template (zero-filled) you can copy into config.\n  `validate` checks the cfg.rates shape: required fields, non-negative numbers, known providers (warn-only).\n  `copy` clones an existing card to a new key (use when a new model launches at the same price as an old one).',
  auth: 'Usage: lazyclaw auth <list <provider> | add <provider> <key> [--label <name>] | remove <provider> <label> | use <provider> <label> | rotate <provider>>\n  Multiple keys per provider for rate-limit rotation. The active label is sent on every chat / agent call.\n  `rotate` advances the cursor to the next label; pair with a 429 hook for auto-failover.',
  pairing: 'Usage: lazyclaw pairing <list | add <id> [--label <name>] | remove <id>>\n  Sender allowlist for the messaging surface. Inbound senders not on this list are rejected.\n  Sender ids are opaque per-channel: Slack member id, Discord user id, phone number for SMS, etc.',
  nodes: 'Usage: lazyclaw nodes <list | register <id> [--platform macos|ios|android|web|cli] [--label <name>] | remove <id>>\n  Companion device registration table. CLI only — the actual mobile / menu-bar apps are out of scope here.\n  Platform is free-form lower-case; future surfaces (iOS / Android nodes) authenticate against the daemon using these ids.',
  message: 'Usage: lazyclaw message <list | add <name> <webhook-url> [--kind slack|discord|generic] | remove <name> | send <name> <text>>\n  Outbound webhook messaging — Slack / Discord Incoming Webhooks. Auto-detects kind from the URL pattern.\n  send accepts a literal string, or `-` to read the body from stdin.',
  workspace: 'Usage: lazyclaw workspace <list | init <name> | show <name> [<file>] | remove <name> | path <name>>\n  Workspace = a directory under <configDir>/workspaces/<name>/ containing AGENTS.md, SOUL.md, TOOLS.md.\n  When `chat` or `agent` is invoked with --workspace <name>, the three files are stitched into a single system prompt at the head of the conversation. Missing files are skipped silently.\n  init scaffolds the three files with short stubs you replace.\n  show prints the composed prompt; show <name> AGENTS.md (etc) prints just one file.',
  browse: 'Usage: lazyclaw browse <url> [--max-bytes <N>] [--timeout-ms <N>] [--user-agent <ua>] [--meta]\n  Fetches the URL and emits Markdown on stdout. Pipes cleanly into `agent`:\n      lazyclaw browse https://example.com/docs | lazyclaw agent -\n  Strips <script>/<style>/<svg>/comments, prefers <main>/<article>, falls back to <body>.\n  --max-bytes caps the body read (default 2 MB) so a misconfigured upstream can\'t OOM the process.\n  --meta prints { url, title, bytes, truncated } as JSON to stderr alongside the markdown on stdout.',
  cron: 'Usage: lazyclaw cron <list | add <name> "<cron-spec>" -- <cmd> ... | remove <name> | show <name> | sync | run <name>>\n  Schedule recurring agent runs. macOS uses launchd (~/Library/LaunchAgents/com.lazyclaw.<name>.plist); Linux / WSL uses the user crontab.\n  Cron spec is the standard 5-field form (minute hour dom month dow). Supports *, range a-b, list a,b,c, step */N.\n  add: pass the command after `--`. Typical use:\n      lazyclaw cron add daily-summary "0 9 * * 1-5" -- lazyclaw agent "Summarise today\'s TODOs"\n  list / show: read from cfg.cron[name] (config is the source of truth).\n  sync: re-installs every job in cfg.cron into the system scheduler — handy after a reinstall.\n  run: one-shot in-process execution of the named job; the OS scheduler does the same thing on its trigger.\n  Logs: ~/.lazyclaw/logs/cron-<name>.{out,err}.log (macOS launchd path).',
  setup: 'Usage: lazyclaw setup [--skip-test]\n  OpenClaw-style multi-step first-run wizard. Walks through:\n    1. Provider + model + api-key (delegates to onboard --pick)\n    2. Optional workspace init  (AGENTS.md / SOUL.md / TOOLS.md)\n    3. Optional skill bundle install from GitHub\n    4. Optional outbound webhook (Slack / Discord)\n    5. Reachability test against the picked provider\n  Each optional step takes Enter or "skip" to bypass. Re-runnable safely.\n  Also fires automatically on first run when `lazyclaw` is invoked with no config.',
  dashboard: 'Usage: lazyclaw dashboard [--port <N>] [--no-open]\n  Launches the lazyclaw-only web UI on http://127.0.0.1:<port> (default 19600) and opens it in the default browser.\n  Wraps `lazyclaw daemon` + a static HTML; no Python / lazyclaude dashboard required.\n  Tabs: Chat · Sessions · Skills · Workspace · Providers · Status. Each tab calls existing daemon endpoints.\n  --no-open keeps the browser closed (handy for SSH / headless / dev). The bound URL is always printed to stdout.',
};

function cmdHelp(name) {
  if (!name) {
    process.stdout.write('lazyclaw — terminal AI assistant + workflow engine\n\n');
    process.stdout.write('Subcommands:\n');
    for (const sub of SUBCOMMANDS) {
      const summary = HELP_SUMMARIES[sub] || '';
      process.stdout.write(`  ${sub.padEnd(12)}${summary}\n`);
    }
    process.stdout.write('\nlazyclaw help <subcommand>   detailed usage\n');
    return;
  }
  const detail = HELP_DETAILS[name];
  if (!detail) {
    process.stderr.write(`unknown subcommand: ${name}\n`);
    process.stderr.write(`run \`lazyclaw help\` to see the list\n`);
    process.exit(2);
  }
  process.stdout.write(detail + '\n');
}

async function cmdAgent(prompt, flags) {
  // OpenClaw-style one-shot: send a single prompt, stream the response,
  // exit. Useful in scripts and pipelines. Honors --provider and --model
  // flags as overrides over config.json. Reads stdin when prompt is "-"
  // so callers can pipe input.
  await ensureRegistry();
  const skillsMod = await import('./skills.mjs');
  const cfg = readConfig();
  const provName = flags.provider || cfg.provider || 'mock';
  let prov = _registryMod.PROVIDERS[provName];
  if (!prov) { console.error(`unknown provider: ${provName}`); process.exit(2); }
  // --fallback "openai,ollama" wraps the primary in a withFallback chain so
  // RATE_LIMIT/CONNECTION_REFUSED/5xx on the primary trips through to the
  // listed providers in order. Unknown names exit 2 — better than a silent
  // skip, the chain lengths matter for user expectations.
  const fallbackList = (flags.fallback ? String(flags.fallback) : '')
    .split(',').map(s => s.trim()).filter(Boolean);
  if (fallbackList.length > 0) {
    const chain = [prov];
    for (const fb of fallbackList) {
      const fp = _registryMod.PROVIDERS[fb];
      if (!fp) { console.error(`unknown fallback provider: ${fb}`); process.exit(2); }
      chain.push(fp);
    }
    const { withFallback } = await import('./providers/fallback.mjs');
    prov = withFallback(chain);
  }
  // --retry N wraps the chosen provider with the rate-limit-aware retry
  // helper. N is exclusive of the initial call (--retry 3 = up to 4 tries).
  // Default 0 keeps behavior identical to before for callers that don't
  // explicitly opt in.
  const retryN = flags.retry !== undefined ? parseInt(flags.retry, 10) : 0;
  if (Number.isFinite(retryN) && retryN > 0) {
    const { withRateLimitRetry } = await import('./providers/retry.mjs');
    prov = withRateLimitRetry(prov, { attempts: retryN });
  }

  // --skill resolves a comma-separated list to a composed system prompt.
  // Defaults from config.skills (same shape) if --skill not passed.
  const skillNames = (flags.skill ? String(flags.skill) : (Array.isArray(cfg.skills) ? cfg.skills.join(',') : ''))
    .split(',').map(s => s.trim()).filter(Boolean);
  // --workspace <name> stitches AGENTS.md / SOUL.md / TOOLS.md from
  // <configDir>/workspaces/<name>/ at the head of the system prompt.
  // Workspace + skill compose: workspace block first, skill block
  // after — same order as `lazyclaw workspace show` so the user can
  // preview exactly what the LLM will see.
  const workspaceName = flags.workspace || cfg.workspace || '';
  const promptParts = [];
  if (workspaceName) {
    try {
      const ws = await import('./workspace.mjs');
      const wsPrompt = ws.composeWorkspacePrompt(path.dirname(configPath()), workspaceName);
      if (wsPrompt) promptParts.push(wsPrompt);
    } catch (e) { console.error(`workspace error: ${e.message}`); process.exit(2); }
  }
  if (skillNames.length > 0) {
    try {
      const skillPrompt = skillsMod.composeSystemPrompt(skillNames, path.dirname(configPath()));
      if (skillPrompt) promptParts.push(skillPrompt);
    } catch (e) { console.error(`skill error: ${e.message}`); process.exit(2); }
  }
  const systemPrompt = promptParts.length ? promptParts.join('\n\n---\n\n') : null;

  let text = prompt;
  if (text === '-' || text === undefined) {
    text = await new Promise(resolve => {
      let buf = '';
      process.stdin.setEncoding('utf8');
      process.stdin.on('data', d => { buf += d; });
      process.stdin.on('end', () => resolve(buf));
    });
  }
  if (!text || !String(text).trim()) {
    console.error('agent: empty prompt'); process.exit(2);
  }
  const messages = [];
  if (systemPrompt) messages.push({ role: 'system', content: systemPrompt });
  messages.push({ role: 'user', content: String(text) });
  // --thinking <budgetTokens> enables Anthropic extended thinking. Other
  // providers ignore the flag silently because their opts shape doesn't
  // carry it.
  const thinkingBudget = flags.thinking ? parseInt(flags.thinking, 10) : 0;
  // --show-thinking prints thinking deltas to stderr while text deltas
  // continue to stream to stdout. This keeps stdout clean for piping.
  const showThinking = flags['show-thinking'];
  // --usage prints normalized token totals to stderr after the response
  // streams. --cost adds a cost line when cfg.rates has a card matching
  // the active provider/model. Both write to stderr so piping the answer
  // text downstream isn't polluted with metadata.
  const showUsage = flags.usage;
  const showCost = flags.cost;
  // Loading rates is lazy: only when --cost is on, and we resolve once
  // up-front so the onUsage callback below doesn't need to import on a
  // hot path.
  let costFromUsage = null;
  if (showCost) {
    const ratesMod = await import('./providers/rates.mjs');
    costFromUsage = ratesMod.costFromUsage;
  }
  // --sandbox docker:<image> routes the underlying subprocess
  // (currently only the claude-cli provider hits this branch)
  // through `docker run`. parseSandboxSpec returns null when the
  // flag is absent / "off" so the no-flag path is bit-identical.
  let sandboxSpec = null;
  if (flags.sandbox) {
    const sb = await import('./sandbox.mjs');
    try { sandboxSpec = sb.parseSandboxSpec(flags.sandbox, flags); }
    catch (e) { console.error(`error: ${e.message}`); process.exit(2); }
    if (sandboxSpec && provName !== 'claude-cli') {
      process.stderr.write(`warn: --sandbox only wraps subprocess providers; ${provName} ignores it\n`);
    }
  }
  try {
    for await (const chunk of prov.sendMessage(messages, {
      apiKey: _resolveAuthKey(cfg, provName),
      model: flags.model || cfg.model,
      sandbox: sandboxSpec,
      thinking: thinkingBudget > 0 ? { enabled: true, budgetTokens: thinkingBudget } : undefined,
      onThinking: showThinking ? t => process.stderr.write(t) : undefined,
      onUsage: (showUsage || showCost) ? (u) => {
        if (showUsage) process.stderr.write('usage: ' + JSON.stringify(u) + '\n');
        if (showCost && cfg.rates) {
          const c = costFromUsage(
            { provider: flags.provider || cfg.provider, model: flags.model || cfg.model, usage: u },
            cfg.rates,
          );
          if (c) process.stderr.write('cost: ' + JSON.stringify(c) + '\n');
        }
      } : undefined,
    })) {
      process.stdout.write(chunk);
    }
    process.stdout.write('\n');
  } catch (err) {
    process.stderr.write(`error: ${err?.message || String(err)}\n`);
    process.exit(1);
  }
}

// Cursor-style ghost autocomplete for the chat prompt. When the
// current readline buffer starts with `/` and prefix-matches a known
// slash command, the rest of the command is rendered in dim grey
// after the cursor. Right-arrow at end-of-line accepts the suggestion
// (replaces rl.line with the full command). Tab still goes through
// readline's tab-completer for cycling.
function _attachGhostAutocomplete(rl) {
  // Returns a `dispose()` callback that detaches the keypress listener
  // and the rl 'line' listener installed below. Without disposal the
  // process never exits — Node keeps the event loop alive while
  // process.stdin has a 'keypress' listener attached. (This was the
  // root cause of the slow `/exit` users reported.)
  if (!process.stdout.isTTY) return () => {};
  const cmds = SLASH_COMMANDS.map((c) => c.cmd);
  let lastGhost = '';
  // Find the longest match for the current input. Returns '' when
  // nothing matches or when the input already equals a command.
  const findMatch = () => {
    const buf = rl.line || '';
    if (!buf.startsWith('/')) return '';
    const exact = cmds.find((c) => c === buf);
    if (exact) return '';
    const hits = cmds.filter((c) => c.startsWith(buf) && c.length > buf.length);
    if (!hits.length) return '';
    return hits[0]; // first match is the shortest matching command
  };
  // Render the ghost after the user's cursor. We use ANSI save/restore
  // (\x1b[s / \x1b[u) so writing the suggestion doesn't move readline's
  // notion of where the cursor is; we just paint the dim text and snap
  // back. \x1b[K clears any leftover ghost from the previous keystroke.
  const render = () => {
    if (!process.stdout.isTTY) return;
    const match = findMatch();
    const buf = rl.line || '';
    // Always clear leftover ghost first.
    process.stdout.write('\x1b[s\x1b[K');
    if (match && match.length > buf.length) {
      const tail = match.slice(buf.length);
      process.stdout.write(`\x1b[2m${tail}\x1b[0m`);
      lastGhost = match;
    } else {
      lastGhost = '';
    }
    process.stdout.write('\x1b[u');
  };
  // Intercept Right-arrow at end-of-line to accept the suggestion.
  // We attach as a prependListener so we run before readline's own
  // handler — when we accept, we mutate rl.line ourselves and call
  // _refreshLine, then return without forwarding the keypress.
  const onKeypress = (_str, key) => {
    if (!key) return;
    if (key.name === 'right' && lastGhost && rl.line === rl.line.trim() &&
        rl.cursor === (rl.line || '').length && (rl.line || '').length < lastGhost.length) {
      const accepted = lastGhost;
      // Clear the dim ghost before redrawing the line (otherwise the
      // residue overlaps the new line content).
      process.stdout.write('\x1b[s\x1b[K\x1b[u');
      rl.line = accepted;
      rl.cursor = accepted.length;
      // _refreshLine is private but stable across Node 18+ readline
      // implementations. Falls back to manual redraw if it ever changes.
      if (typeof rl._refreshLine === 'function') rl._refreshLine();
      else { process.stdout.write('\r\x1b[K' + (rl._prompt || '') + accepted); }
      lastGhost = '';
      return;
    }
    // For any other key, schedule the ghost re-render after readline
    // has updated rl.line. setImmediate runs after readline's keypress
    // handler completes.
    setImmediate(render);
  };
  process.stdin.on('keypress', onKeypress);
  // Clear ghost on each new prompt so a stale dim hint doesn't carry
  // over between turns.
  const onLine = () => { lastGhost = ''; };
  rl.on('line', onLine);
  return () => {
    try { process.stdin.removeListener('keypress', onKeypress); } catch (_) {}
    try { rl.removeListener('line', onLine); } catch (_) {}
    // Wipe any leftover ghost on screen so the user's terminal doesn't
    // keep a dim suffix after we exit.
    try { process.stdout.write('\x1b[s\x1b[K\x1b[u'); } catch (_) {}
  };
}

// LazyClaw banner — printed once at the top of every interactive chat
// session so users see the active provider/model before they start
// typing. Plain ANSI; auto-skipped when stdout isn't a TTY (so piped
// invocations stay clean for tests/scripts).
// Single source of truth for the LazyClaw banner — used by the chat
// REPL header, the no-arg launcher, and the first-run welcome panel.
// Returns an array of pre-formatted lines (with ANSI colour) so the
// caller can splice in additional rows without re-implementing the
// alignment.
//
// Width-management rule: every inner line is forced through
// `.padEnd(W)` so a stray width miscount can't punch the right
// border off the box (which is exactly the bug v3.99.5 shipped:
// two of the inner lines were 33 cols vs the others' 32, so the
// ╮ rendered into the next line).
function _renderBanner(version) {
  const W = 30;
  const accent = (s) => `\x1b[38;5;208m${s}\x1b[0m`;
  const dim    = (s) => `\x1b[2m${s}\x1b[0m`;
  // Inner content of each banner row — DO NOT pad here, the wrapper
  // does it. Backslashes are JS-escaped so each `\\` renders as one
  // literal `\` in the output.
  const inner = [
    '   _',
    '  | |__ _ _____  _ _',
    "  | / _` |_ / || | '_|",
    '  |_\\__,_/__\\_, |_|',
    '  LazyClaw  |__/  ' + String(version || '?.?.?').padEnd(10).slice(0, 10),
  ];
  // Sleepy-cat mascot on the right, lined up with the busiest part
  // of the wordmark. Three rows of ASCII art + "zz" trail. Plain
  // ASCII (no box-drawing on the cat) so it lands well in any font.
  const mascot = [
    '',
    '',
    '   /\\_/\\',
    '  ( -.- )  ' + dim('z z'),
    '   > ^ <    ' + dim('z'),
    '',
    '',
  ];
  const banner = [
    '╭' + '─'.repeat(W) + '╮',
    ...inner.map((s) => '│' + s.padEnd(W).slice(0, W) + '│'),
    '╰' + '─'.repeat(W) + '╯',
  ];
  return banner.map((l, i) => '  ' + accent(l) + (mascot[i] ? '  ' + mascot[i] : ''));
}

function _printChatBanner(activeProvName, activeModel, version) {
  if (!process.stdout.isTTY) return;
  const dim = (s) => `\x1b[2m${s}\x1b[0m`;
  const ok = (s) => `\x1b[32m${s}\x1b[0m`;
  const lines = [
    '',
    ..._renderBanner(version),
    '',
    `  ${dim('provider ·')} ${ok(activeProvName)}`,
    `  ${dim('model    ·')} ${ok(activeModel || '(default)')}`,
    `  ${dim('slash    ·')} /help · /model · /provider · /exit`,
    `  ${dim('hint     ·')} → ${dim('to accept the suggested command,')} Tab ${dim('to cycle')}`,
    '',
  ];
  process.stdout.write(lines.join('\n') + '\n');
}

// Interactive provider/model picker. Used on first run (no config) or
// when the user passes --pick. Falls back to plain stdin reads when
// stdout isn't a TTY (CI/script callers should pass --non-interactive
// equivalents instead).
// Generic arrow-key menu used by the multi-step provider/model
// picker below. Returns the picked item, or one of the sentinel
// strings 'BACK' (Esc — caller should retry the previous step) or
// 'CANCEL' (q — caller should bail entirely). Ctrl-C exits the
// process directly, matching every other interactive prompt in the
// CLI.
//
// `items` is an array of { id, label, desc, tag }. `tag` is an
// optional pre-coloured pill (e.g. "[api key]") that lands on the
// right side of the row. `defaultIdx` lets the caller pin where the
// cursor lands; default 0.
async function _arrowMenu({ title, subtitle, footer, items, defaultIdx = 0 }) {
  if (!process.stdout.isTTY || !process.stdin.isTTY) {
    // Non-TTY fallback: print the labels on stderr and read a single
    // line of stdin. Used when somebody pipes input to `lazyclaw
    // setup` — the wizard still works, just without arrows.
    process.stderr.write(`${title}\n`);
    items.forEach((it, i) => process.stderr.write(`  ${i + 1}. ${it.label}${it.desc ? ' — ' + it.desc : ''}\n`));
    process.stderr.write('pick (number / id, blank for first): ');
    const ans = await new Promise((resolve) => {
      let buf = '';
      const onData = (chunk) => {
        buf += chunk.toString();
        if (buf.includes('\n')) { process.stdin.off('data', onData); resolve(buf.trim()); }
      };
      process.stdin.on('data', onData);
    });
    if (!ans) return items[0];
    const byNum = parseInt(ans, 10);
    if (Number.isFinite(byNum) && byNum >= 1 && byNum <= items.length) return items[byNum - 1];
    const byId = items.find((it) => it.id === ans || it.label === ans);
    return byId || items[0];
  }

  const readline = await import('node:readline');
  readline.emitKeypressEvents(process.stdin);
  if (process.stdin.setRawMode) process.stdin.setRawMode(true);
  let idx = Math.max(0, Math.min(items.length - 1, defaultIdx));
  const accent = (s) => `\x1b[38;5;208m${s}\x1b[0m`;
  const dim    = (s) => `\x1b[2m${s}\x1b[0m`;
  const bold   = (s) => `\x1b[1m${s}\x1b[0m`;

  const draw = () => {
    process.stdout.write('\x1b[?25l\x1b[2J\x1b[H');
    process.stdout.write(accent(title) + '\n');
    if (subtitle) process.stdout.write(dim(subtitle) + '\n');
    process.stdout.write(dim('↑/↓ to move · Enter to confirm · Esc to back · q to quit') + '\n\n');
    const rows = Math.max(6, (process.stdout.rows || 24) - 8);
    let from = Math.max(0, idx - Math.floor(rows / 2));
    if (from + rows > items.length) from = Math.max(0, items.length - rows);
    const to = Math.min(items.length, from + rows);
    // Pre-compute label width so descriptions line up across rows.
    const labelW = items.reduce((w, it) => Math.max(w, (it.label || '').length), 12);
    for (let i = from; i < to; i++) {
      const it = items[i];
      const marker = i === idx ? accent('❯ ') : '  ';
      const lbl = (it.label || '').padEnd(labelW);
      const lblOut = i === idx ? bold(lbl) : lbl;
      const desc = it.desc ? '  ' + dim(it.desc) : '';
      const tag = it.tag ? '  ' + it.tag : '';
      process.stdout.write(`${marker}${lblOut}${desc}${tag}\n`);
    }
    if (to < items.length) {
      process.stdout.write(`${dim(`  …(${items.length - to} more)`)}\n`);
    }
    if (footer) process.stdout.write('\n' + dim(footer) + '\n');
  };

  draw();
  return await new Promise((resolve) => {
    const onKey = (_str, key) => {
      if (!key) return;
      if (key.name === 'up')   { idx = (idx - 1 + items.length) % items.length; draw(); }
      else if (key.name === 'down') { idx = (idx + 1) % items.length; draw(); }
      else if (key.name === 'pageup')   { idx = Math.max(0, idx - 10); draw(); }
      else if (key.name === 'pagedown') { idx = Math.min(items.length - 1, idx + 10); draw(); }
      else if (key.name === 'home') { idx = 0; draw(); }
      else if (key.name === 'end')  { idx = items.length - 1; draw(); }
      else if (key.name === 'return') { cleanup(); resolve(items[idx]); }
      else if (key.ctrl && key.name === 'c') { cleanup(); process.exit(130); }
      else if (key.name === 'escape') { cleanup(); resolve('BACK'); }
      else if (key.name === 'q')      { cleanup(); resolve('CANCEL'); }
    };
    const cleanup = () => {
      process.stdin.off('keypress', onKey);
      if (process.stdin.setRawMode) process.stdin.setRawMode(false);
      process.stdout.write('\x1b[?25h\x1b[2J\x1b[H');
    };
    process.stdin.on('keypress', onKey);
  });
}

// Bucket every registered provider into one of three auth-method
// families. The picker's first step asks the user which family
// they want before drilling into specific providers — much less
// overwhelming than a flat 40-row list. Bucket assignment lives
// here (rather than registry.mjs) because it's a UX concept, not
// an intrinsic provider attribute.
function _providerFamilies() {
  const info = _registryMod.PROVIDER_INFO || {};
  const all = Object.keys(_registryMod.PROVIDERS);
  const buckets = {
    api: { label: 'API key', desc: 'paste an sk-... key during setup',  tag: '\x1b[38;5;245m[needs key]\x1b[0m', members: [] },
    cli: { label: 'CLI / Local', desc: 'keyless — uses an existing CLI login or a local daemon', tag: '\x1b[38;5;208m[no key]\x1b[0m', members: [] },
    mock: { label: 'Mock', desc: 'offline echo, only useful for testing', tag: '\x1b[38;5;245m[test]\x1b[0m', members: [] },
  };
  for (const name of all) {
    if (name === 'mock') buckets.mock.members.push(name);
    else if ((info[name] || {}).requiresApiKey) buckets.api.members.push(name);
    else buckets.cli.members.push(name);
  }
  return buckets;
}

// Multi-step provider / model picker — replaces the flat 40-row
// list of v3.99.5 with a drill-in:
//
//   Step 1 — auth family (API key / CLI-Local / Mock)
//   Step 2 — provider in that family (gemini / openai / claude-cli / …)
//   Step 3 — model in that provider's suggestedModels
//
// Esc at any step goes back one. q or Ctrl-C cancels entirely.
// Steps that have only one option auto-advance so the user doesn't
// stare at a single-row menu (e.g. the Mock family has just `mock`).
async function _pickProviderInteractive() {
  const providers = Object.keys(_registryMod.PROVIDERS);
  if (!providers.length) return { provider: 'mock', model: null };
  const info = _registryMod.PROVIDER_INFO || {};
  const families = _providerFamilies();

  // Non-TTY fallback — single-prompt picker, identical to before.
  if (!process.stdout.isTTY || !process.stdin.isTTY) {
    process.stdout.write(`provider [${providers.join('|')}]: `);
    const ans = await new Promise((resolve) => {
      let buf = '';
      const onData = (chunk) => {
        buf += chunk.toString();
        if (buf.includes('\n')) { process.stdin.off('data', onData); resolve(buf.trim()); }
      };
      process.stdin.on('data', onData);
    });
    return { provider: ans || providers[0], model: null };
  }

  // ── Step 1 — auth family ──────────────────────────────────────
  let family = null;
  while (!family) {
    const familyItems = Object.entries(families)
      .filter(([, b]) => b.members.length > 0)
      .map(([id, b]) => ({
        id,
        label: b.label,
        desc: `${b.desc}  ·  ${b.members.join(' / ')}`,
        tag: b.tag,
      }));
    const picked = await _arrowMenu({
      title: 'LazyClaw setup — Step 1 of 3:  pick how you want to auth',
      subtitle: 'API: bring your own key  ·  CLI/Local: use what\'s already on this machine  ·  Mock: offline test',
      items: familyItems,
    });
    if (picked === 'CANCEL' || picked === 'BACK') return null;
    family = picked;
  }

  // ── Step 2 — provider in that family ──────────────────────────
  let provider = null;
  while (!provider) {
    const memberNames = families[family.id].members;
    if (memberNames.length === 1) {
      // Auto-advance — no point making the user pick from a single
      // row.
      provider = { id: memberNames[0] };
      break;
    }
    const provItems = memberNames.map((name) => {
      const meta = info[name] || {};
      const models = (meta.suggestedModels || []).slice(0, 4).join(' · ') || '(default)';
      return {
        id: name,
        label: name,
        desc: `models: ${models}`,
        tag: meta.requiresApiKey ? '\x1b[38;5;245m[api key]\x1b[0m' : '\x1b[38;5;208m[no key]\x1b[0m',
      };
    });
    const picked = await _arrowMenu({
      title: `LazyClaw setup — Step 2 of 3:  pick a ${family.label} provider`,
      subtitle: `Showing ${memberNames.length} ${family.label.toLowerCase()} provider(s).`,
      items: provItems,
    });
    if (picked === 'CANCEL') return null;
    if (picked === 'BACK')   { family = null; return _pickProviderInteractive(); }
    provider = picked;
  }

  // ── Step 3 — model ────────────────────────────────────────────
  const meta = info[provider.id] || {};
  const models = Array.isArray(meta.suggestedModels) ? meta.suggestedModels : [];
  if (!models.length) {
    // Provider has no curated models (mock) — return without a
    // model so the underlying call uses the provider default.
    return { provider: provider.id, model: null };
  }
  while (true) {
    const modelItems = models.map((m) => ({ id: m, label: m, desc: '' }));
    // Pin the cursor to the provider's defaultModel so Enter without
    // navigation picks the most-recommended one.
    const defaultIdx = Math.max(0, models.indexOf(meta.defaultModel || models[0]));
    const picked = await _arrowMenu({
      title: `LazyClaw setup — Step 3 of 3:  pick a model for ${provider.id}`,
      subtitle: `Showing ${models.length} suggested model(s). Type the model id directly later via /model in chat to use anything not listed here.`,
      items: modelItems,
      defaultIdx,
    });
    if (picked === 'CANCEL') return null;
    if (picked === 'BACK')   return _pickProviderInteractive(); // back to step 1
    return { provider: provider.id, model: picked.id };
  }
}

async function cmdChat(flags = {}) {
  await ensureRegistry();
  const sessionsMod = await import('./sessions.mjs');
  const skillsMod = await import('./skills.mjs');
  const cfg = readConfig();
  // Mutable in-REPL state: /provider and /model edit these without
  // touching config.json on disk. The CLI flag form (`chat --provider X`)
  // would normally seed these via cfg, but we leave that to a future
  // iteration; today the slash commands work against the on-disk default.
  let activeProvName = cfg.provider || '';
  let activeModel = cfg.model || null;
  const lookupProv = (name) => _registryMod.PROVIDERS[name];
  // Interactive picker fires when --pick is set OR no provider is
  // configured yet (first run). Skipped when stdin isn't a TTY so
  // automation stays predictable.
  const shouldPick = (!!flags.pick) || (!activeProvName && process.stdin.isTTY);
  if (shouldPick) {
    const picked = await _pickProviderInteractive();
    if (picked && picked.provider) {
      activeProvName = picked.provider;
      if (picked.model) activeModel = picked.model;
    }
  }
  if (!activeProvName) activeProvName = 'mock';
  let prov = lookupProv(activeProvName);
  if (!prov) { console.error(`unknown provider: ${activeProvName}`); process.exit(2); }

  // Top-of-session banner so the user can see at a glance what they're
  // talking to. Cheap (no provider call) and TTY-only.
  _printChatBanner(activeProvName, activeModel, readVersionFromRepo());

  const readline = await import('node:readline');
  // Use terminal:true when we're attached to a TTY so the prompt shows
  // and ghost-text autocomplete (below) can render. Falls back to the
  // plain non-terminal mode for piped/non-TTY callers.
  const useTerminal = !!process.stdin.isTTY;
  const rl = readline.createInterface({
    input: process.stdin,
    output: useTerminal ? process.stdout : undefined,
    terminal: useTerminal,
    prompt: useTerminal ? '\x1b[38;5;208m›\x1b[0m ' : '',
  });
  let _disposeGhost = () => {};
  if (useTerminal) {
    // Cursor-style ghost autocomplete: when the buffer starts with `/`,
    // render the longest matching command after the cursor in dim grey.
    // Right-arrow at end-of-line accepts. Tab still cycles via the
    // existing handleSlash branch; this only adds the inline preview.
    _disposeGhost = _attachGhostAutocomplete(rl) || (() => {});
    rl.prompt();
  }

  // --sandbox docker:<image> wraps subprocess-providers (claude-cli)
  // in a docker container. Parsed once up front so a slash-command
  // model switch doesn't have to re-parse every turn.
  let sandboxSpec = null;
  if (flags.sandbox) {
    const sb = await import('./sandbox.mjs');
    try { sandboxSpec = sb.parseSandboxSpec(flags.sandbox, flags); }
    catch (e) { console.error(`error: ${e.message}`); process.exit(2); }
  }

  // Persistent session ID. When --session is set we hydrate prior turns from
  // <configDir>/sessions/<id>.jsonl and append every new turn back to it.
  // Without --session, chat is in-memory only (matches phase 4 behavior).
  const sessionId = flags.session || null;
  const cfgDir = path.dirname(configPath());
  let messages = sessionId
    ? sessionsMod.loadTurns(sessionId, cfgDir).map(t => ({ role: t.role, content: t.content }))
    : [];

  // --skill (comma-separated names) composes into a system message at the
  // head of the conversation. Same shape as `agent --skill`. Defaults from
  // config.skills array when --skill not passed. We only inject if no
  // system message is already present (so resuming a session doesn't
  // double-prepend skills that the prior invocation already added).
  const skillNames = (flags.skill ? String(flags.skill) : (Array.isArray(cfg.skills) ? cfg.skills.join(',') : ''))
    .split(',').map(s => s.trim()).filter(Boolean);
  // --workspace <name> sits at the head of the system prompt, then
  // any --skill block. The two compose with the same `\n---\n`
  // separator the agent path uses, so `lazyclaw workspace show` is
  // a faithful preview.
  const workspaceName = flags.workspace || cfg.workspace || '';
  const sysParts = [];
  if (workspaceName && !messages.some(m => m.role === 'system')) {
    try {
      const ws = await import('./workspace.mjs');
      const wsPrompt = ws.composeWorkspacePrompt(cfgDir, workspaceName);
      if (wsPrompt) sysParts.push(wsPrompt);
    } catch (e) { console.error(`workspace error: ${e.message}`); process.exit(2); }
  }
  if (skillNames.length > 0 && !messages.some(m => m.role === 'system')) {
    try {
      const sys = skillsMod.composeSystemPrompt(skillNames, cfgDir);
      if (sys) sysParts.push(sys);
    } catch (e) {
      console.error(`skill error: ${e.message}`);
      process.exit(2);
    }
  }
  if (sysParts.length && !messages.some(m => m.role === 'system')) {
    const merged = sysParts.join('\n\n---\n\n');
    messages.unshift({ role: 'system', content: merged });
    if (sessionId) sessionsMod.appendTurn(sessionId, 'system', merged, cfgDir);
  }

  let charsSent = messages.reduce((n, m) => n + (m.role === 'user' ? String(m.content || '').length : 0), 0);
  if (sessionId && messages.length > (skillNames.length > 0 ? 1 : 0)) {
    process.stdout.write(`resumed session ${sessionId} with ${messages.length} prior turn(s)\n`);
  }
  // Running usage accumulator. /usage reports both the cheap local
  // estimate (messageCount + charsSent) AND the provider-reported
  // totals when the provider emits them on each turn. Mock provider
  // doesn't emit usage, so usage stays null there — no surprise.
  /** @type {{ inputTokens: number, outputTokens: number, totalTokens: number, turnsWithUsage: number } | null} */
  let runningUsage = null;
  const accumulateUsage = (u) => {
    if (!u) return;
    if (!runningUsage) runningUsage = { inputTokens: 0, outputTokens: 0, totalTokens: 0, turnsWithUsage: 0 };
    runningUsage.inputTokens  += Number(u.inputTokens) || 0;
    runningUsage.outputTokens += Number(u.outputTokens) || 0;
    runningUsage.totalTokens  += Number(u.totalTokens) || ((Number(u.inputTokens) || 0) + (Number(u.outputTokens) || 0));
    runningUsage.turnsWithUsage += 1;
  };
  const persistTurn = (role, content) => {
    if (!sessionId) return;
    sessionsMod.appendTurn(sessionId, role, content, cfgDir);
  };

  const handleSlash = async (line) => {
    const cmd = line.split(/\s+/)[0];
    switch (cmd) {
      case '/help': {
        process.stdout.write('slash commands:\n');
        for (const c of SLASH_COMMANDS) process.stdout.write(`  ${c.cmd.padEnd(8)} — ${c.help}\n`);
        return true;
      }
      case '/status': {
        const out = {
          provider: activeProvName,
          model: activeModel,
          keyMasked: _registryMod.maskApiKey(cfg['api-key']),
          messageCount: messages.length,
        };
        process.stdout.write(JSON.stringify(out) + '\n');
        return true;
      }
      case '/provider': {
        // `/provider <name>` switches the active provider for subsequent
        // turns. The conversation history stays put — the next user
        // message goes to the new provider with the existing context.
        // `/provider` (no arg) prints the current name.
        const arg = line.slice('/provider'.length).trim();
        if (!arg) {
          process.stdout.write(`provider: ${activeProvName}\n`);
          return true;
        }
        const next = lookupProv(arg);
        if (!next) {
          process.stdout.write(`unknown provider: ${arg} (known: ${Object.keys(_registryMod.PROVIDERS).join(', ')})\n`);
          return true;
        }
        activeProvName = arg;
        prov = next;
        process.stdout.write(`provider → ${arg}\n`);
        return true;
      }
      case '/model': {
        // `/model <name>` updates the active model without touching the
        // provider. `/model` (no arg) prints the current value.
        const arg = line.slice('/model'.length).trim();
        if (!arg) {
          process.stdout.write(`model: ${activeModel || '(default)'}\n`);
          return true;
        }
        // Honor unified provider/model: `/model anthropic/claude-opus-4-7`
        // splits and switches both.
        const { parseProviderModel } = _registryMod;
        const parsed = parseProviderModel(arg);
        if (parsed.provider) {
          const next = lookupProv(parsed.provider);
          if (!next) {
            process.stdout.write(`unknown provider: ${parsed.provider}\n`);
            return true;
          }
          activeProvName = parsed.provider;
          prov = next;
        }
        activeModel = parsed.model || arg;
        process.stdout.write(`model → ${activeModel}${parsed.provider ? ` (provider → ${parsed.provider})` : ''}\n`);
        return true;
      }
      case '/new':
      case '/reset': {
        messages = [];
        charsSent = 0;
        runningUsage = null;
        if (sessionId) {
          const sm = await import('./sessions.mjs');
          sm.resetSession(sessionId, cfgDir);
        }
        process.stdout.write('cleared — new conversation\n');
        return true;
      }
      case '/usage': {
        const out = { messageCount: messages.length, charsSent };
        if (runningUsage) out.tokens = runningUsage;
        // When cfg.rates has a card for the active provider/model AND
        // we accumulated real usage, surface the running cost too. The
        // computation is local (pure arithmetic), no extra network.
        if (runningUsage && cfg.rates && typeof cfg.rates === 'object') {
          try {
            const { costFromUsage } = await import('./providers/rates.mjs');
            const r = costFromUsage(
              { provider: activeProvName, model: activeModel, usage: runningUsage },
              cfg.rates,
            );
            if (r) out.cost = r;
          } catch { /* never let cost-card lookup fail the slash */ }
        }
        process.stdout.write(JSON.stringify(out) + '\n');
        return true;
      }
      case '/skill': {
        // `/skill name1,name2` — replace the active system message with a
        // composition of the named skills. `/skill` (no arg) clears the
        // system message. The replacement happens in-place on the
        // messages array; the prior system turn (if any) is dropped so
        // we don't end up with two stacked system messages talking past
        // each other. When --session is set we persist the new system
        // message so the next invocation resumes with the same context.
        const arg = line.slice('/skill'.length).trim();
        const names = arg.split(',').map(s => s.trim()).filter(Boolean);
        const sysIdx = messages.findIndex(m => m.role === 'system');
        if (names.length === 0) {
          if (sysIdx >= 0) messages.splice(sysIdx, 1);
          if (sessionId) {
            // Persistent session: rewrite the file from scratch so the
            // dropped system turn doesn't linger as a stale entry.
            const sm = await import('./sessions.mjs');
            sm.resetSession(sessionId, cfgDir);
            for (const m of messages) sm.appendTurn(sessionId, m.role, m.content, cfgDir);
          }
          process.stdout.write('cleared system prompt (no active skills)\n');
          return true;
        }
        try {
          const sys = await (async () => {
            const mod = await import('./skills.mjs');
            return mod.composeSystemPrompt(names, cfgDir);
          })();
          if (!sys) {
            process.stdout.write('no skill content composed (empty input?)\n');
            return true;
          }
          if (sysIdx >= 0) messages[sysIdx] = { role: 'system', content: sys };
          else messages.unshift({ role: 'system', content: sys });
          if (sessionId) {
            const sm = await import('./sessions.mjs');
            sm.resetSession(sessionId, cfgDir);
            for (const m of messages) sm.appendTurn(sessionId, m.role, m.content, cfgDir);
          }
          process.stdout.write(`active skills: ${names.join(', ')}\n`);
        } catch (e) {
          process.stdout.write(`skill error: ${e?.message || e}\n`);
        }
        return true;
      }
      case '/exit': {
        return 'EXIT';
      }
      default:
        process.stdout.write(`unknown slash: ${cmd} (try /help)\n`);
        return true;
    }
  };

  try { for await (const line of rl) {
    const text = line.trim();
    if (!text) { if (useTerminal) rl.prompt(); continue; }
    if (text.startsWith('/')) {
      const r = await handleSlash(text);
      if (r === 'EXIT') break;
      if (useTerminal) rl.prompt();
      continue;
    }
    messages.push({ role: 'user', content: text });
    charsSent += text.length;
    persistTurn('user', text);
    let acc = '';
    // Per-turn AbortController. Ctrl+C during a stream aborts THIS turn
    // and returns to the prompt instead of killing the process. Outside
    // a stream, Ctrl+C still terminates (we restore the default handler
    // below, after the try/finally).
    const turnAc = new AbortController();
    const onSigint = () => {
      turnAc.abort();
      process.stdout.write('\n^C interrupted — prompt is back\n');
    };
    process.on('SIGINT', onSigint);
    try {
      for await (const chunk of prov.sendMessage(messages, {
        apiKey: _resolveAuthKey(cfg, activeProvName),
        model: activeModel,
        sandbox: sandboxSpec,
        signal: turnAc.signal,
        onUsage: accumulateUsage,
      })) {
        process.stdout.write(chunk);
        acc += chunk;
      }
      process.stdout.write('\n');
      messages.push({ role: 'assistant', content: acc });
      persistTurn('assistant', acc);
    } catch (err) {
      // ABORT errors are user-initiated; partial assistant output is
      // discarded (we don't append a half-reply to the message history
      // because the next turn would treat it as a complete reply and
      // give odd context to the model).
      if (err?.code !== 'ABORT' && !turnAc.signal.aborted) {
        process.stdout.write(`error: ${err?.message || String(err)}\n`);
      }
    } finally {
      process.off('SIGINT', onSigint);
    }
    if (useTerminal) rl.prompt();
  } } finally {
    // Clean shutdown — without this, /exit "worked" but the process
    // hung for ~3-5 s while Node waited for stdin's keypress listener
    // and raw mode to release. Tearing them down explicitly drops the
    // exit time to <100 ms.
    try { _disposeGhost(); } catch (_) {}
    try { rl.close(); } catch (_) {}
    if (useTerminal && process.stdin.isTTY && process.stdin.setRawMode) {
      try { process.stdin.setRawMode(false); } catch (_) {}
    }
    // process.stdin keeps the event loop alive in raw / readline mode.
    // Pause + unref releases the hold so the process can exit cleanly
    // from natural completion (no need for a hard process.exit).
    try { process.stdin.pause(); } catch (_) {}
    try { process.stdin.unref(); } catch (_) {}
  }
}

// Light wrapper around the daemon — meant for users who installed
// via npm and don't want to remember `daemon` flags. Boots the
// daemon on a fixed default port (override with --port), then opens
// the dashboard URL in the user's default browser.
//
// Why a separate command: typing `lazyclaw daemon` works too, but
// `dashboard` is the discoverable name and it auto-opens the browser
// (which the bare daemon doesn't, since most daemon callers are
// scripts).
async function cmdDashboard(flags = {}) {
  await ensureRegistry();
  const sessionsMod = await import('./sessions.mjs');
  const { startDaemon } = await import('./daemon.mjs');
  const port = flags.port !== undefined ? parseInt(flags.port, 10) : 19600;
  const cfgDir = path.dirname(configPath());
  const d = await startDaemon({
    port,
    once: false,
    readConfig,
    sessionsDirGetter: () => cfgDir,
    sessionsMod,
    version: () => readVersionFromRepo(),
    workflowStateDir: () => process.env.LAZYCLAW_WORKFLOW_STATE_DIR || '.workflow-state',
    // No auth token by default — same loopback-only assumption the
    // bare daemon uses. Users who want to expose the dashboard set
    // LAZYCLAW_AUTH_TOKEN + --allow-origin via the daemon command.
    authToken: undefined,
    allowedOrigins: [],
    rateLimit: null,
    responseCache: null,
    logger: null,
    costCap: null,
  });
  const url = `http://127.0.0.1:${d.port}/dashboard`;
  process.stdout.write(`🦞 LazyClaw dashboard listening at ${url}\n`);
  if (!flags['no-open']) {
    // macOS uses `open`; Linux generally `xdg-open`; Windows
    // `cmd /c start`. Detect by platform; bail silently if the
    // helper fails — the URL is already on stdout for fallback.
    const { spawn } = await import('node:child_process');
    let cmd, args;
    if (process.platform === 'darwin')      { cmd = 'open';      args = [url]; }
    else if (process.platform === 'win32')  { cmd = 'cmd';       args = ['/c', 'start', '""', url]; }
    else                                    { cmd = 'xdg-open';  args = [url]; }
    try {
      spawn(cmd, args, { stdio: 'ignore', detached: true }).unref();
    } catch (_) { /* user can click the URL above */ }
  }
  // Forward SIGINT/SIGTERM to a graceful shutdown so Ctrl-C doesn't
  // strand a port-bound server. Same shape cmdDaemon uses.
  const { gracefulShutdown } = await import('./daemon.mjs');
  let shuttingDown = false;
  const shutdown = async () => {
    if (shuttingDown) return process.exit(1);
    shuttingDown = true;
    process.stdout.write('\n  shutting down…\n');
    const result = await gracefulShutdown(d.server, 5_000);
    process.exit(result.forced ? 1 : 0);
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

async function cmdDaemon(flags) {
  await ensureRegistry();
  const sessionsMod = await import('./sessions.mjs');
  const { startDaemon } = await import('./daemon.mjs');
  const port = flags.port !== undefined ? parseInt(flags.port, 10) : 0;
  const once = !!flags.once;
  // --auth-token wins over the env var so a per-invocation override works.
  // When neither is set, the daemon runs unauthenticated (the historical
  // single-user-loopback default).
  const authToken = flags['auth-token'] || process.env.LAZYCLAW_AUTH_TOKEN || null;
  // --allow-origin accepts a comma-separated list (also reads
  // LAZYCLAW_ALLOW_ORIGINS env). When neither is set, any request that
  // carries an `Origin` header is rejected with 403 — the browser-CSRF
  // / DNS-rebinding default. CLI/script callers don't send Origin so
  // they're unaffected.
  const originSrc = flags['allow-origin'] || process.env.LAZYCLAW_ALLOW_ORIGINS || '';
  const allowedOrigins = String(originSrc).split(',').map(s => s.trim()).filter(Boolean);
  // --rate-limit <capacity> sets a token-bucket cap per remote IP.
  // refillPerSec defaults to capacity/60 so the bucket sustains the
  // same long-run rate (a bucket of 60 / 1 per second == 60 req/min).
  // Pass 0 (or omit) to leave the daemon unlimited.
  const rlCap = flags['rate-limit'] ? parseInt(flags['rate-limit'], 10) : 0;
  const rateLimit = (Number.isFinite(rlCap) && rlCap > 0)
    ? { capacity: rlCap, refillPerSec: rlCap / 60 }
    : null;
  // --response-cache flips the daemon-scope cache on (no value form ⇒ true).
  // Per-request opt-in still happens via body.cache; this just allocates
  // the shared map so the cache state actually persists.
  const responseCache = flags['response-cache'] ? true : null;
  // --log <level> enables structured access logging. Also reads
  // LAZYCLAW_LOG_LEVEL. When set, every request emits a JSON line on
  // stderr at info level: {ts, level, msg:'access', method, path, status,
  // durationMs, remote}. Default is silent.
  const logLevel = flags.log || process.env.LAZYCLAW_LOG_LEVEL || null;
  const { createLogger } = await import('./logger.mjs');
  const logger = logLevel ? createLogger({ level: logLevel }) : null;
  // Cost cap parsing: any --cost-cap-<currency> <amount> flag pair
  // contributes one entry to the costCap map. Currency codes are upper-
  // cased to match what costFromUsage's rate cards produce. Bad/zero
  // values are silently skipped — the daemon should never reject a
  // request because the operator typo'd the limit.
  const costCap = {};
  for (const [k, v] of Object.entries(flags)) {
    if (!k.startsWith('cost-cap-')) continue;
    const cur = k.slice('cost-cap-'.length).toUpperCase();
    const amt = Number(v);
    if (Number.isFinite(amt) && amt > 0) costCap[cur] = amt;
  }
  const costCapOrNull = Object.keys(costCap).length > 0 ? costCap : null;
  // Workflow state dir: --workflow-state-dir flag wins, then env, then
  // the CLI's default of `.workflow-state` (cwd-relative). Mirrors the
  // CLI's `lazyclaw run --dir` resolution so `inspect` and the daemon
  // see the same files.
  const workflowStateDirValue = flags['workflow-state-dir']
    || process.env.LAZYCLAW_WORKFLOW_STATE_DIR
    || '.workflow-state';
  const cfgDir = path.dirname(configPath());
  const d = await startDaemon({
    port: Number.isFinite(port) ? port : 0,
    once,
    readConfig,
    sessionsDirGetter: () => cfgDir,
    sessionsMod,
    version: () => readVersionFromRepo(),
    workflowStateDir: () => workflowStateDirValue,
    authToken: authToken || undefined,
    allowedOrigins,
    rateLimit,
    responseCache,
    logger,
    costCap: costCapOrNull,
  });
  // Print the bound port immediately so test/script callers can pick it up
  // even when we asked for port 0. Indicate auth presence (not the token)
  // and the allowed-origin count (not the values, just whether browser
  // access has been opened).
  process.stdout.write(JSON.stringify({
    ok: true, url: `http://127.0.0.1:${d.port}`, port: d.port, once,
    auth: !!authToken,
    allowedOriginCount: allowedOrigins.length,
    rateLimit: rateLimit ? { capacity: rateLimit.capacity, refillPerSec: rateLimit.refillPerSec } : null,
    responseCache: !!responseCache,
    log: logLevel || null,
    costCap: costCapOrNull,
  }) + '\n');
  if (!once) {
    // Forward SIGINT/SIGTERM to a graceful shutdown with a hard timeout
    // (default 10 s, override with --shutdown-timeout-ms). Second signal
    // bypasses the wait and exits immediately — the orchestrator's "I
    // mean it" signal.
    const { gracefulShutdown } = await import('./daemon.mjs');
    const timeoutMs = flags['shutdown-timeout-ms'] ? parseInt(flags['shutdown-timeout-ms'], 10) : 10_000;
    let shuttingDown = false;
    const shutdown = async () => {
      if (shuttingDown) {
        if (logger) logger.warn('shutdown.force', { reason: 'second signal' });
        return process.exit(1);
      }
      shuttingDown = true;
      if (logger) logger.info('shutdown.begin', { timeoutMs });
      const result = await gracefulShutdown(d.server, timeoutMs);
      if (logger) logger.info('shutdown.end', result);
      process.exit(result.forced ? 1 : 0);
    };
    process.on('SIGINT', shutdown);
    process.on('SIGTERM', shutdown);
  } else {
    // In once mode, exit naturally after the server closes.
    d.server.on('close', () => process.exit(0));
  }
}

async function cmdRates(sub, positional, flags = {}) {
  // Manage cfg.rates without hand-editing JSON. Same shape as
  // RATE_CARD_SHAPE in providers/rates.mjs:
  //   { 'provider/model': { inputPer1M, outputPer1M, cacheReadPer1M?, cacheCreatePer1M?, currency? } }
  switch (sub) {
    case undefined:
    case 'list': {
      const cfg = readConfig();
      const rates = cfg.rates && typeof cfg.rates === 'object' ? cfg.rates : {};
      // Same --filter / --limit pattern as v3.33-v3.36 across
      // sessions/skills/workflows. Filter on key (provider/model)
      // case-insensitive, then post-filter cap.
      let entries = Object.entries(rates);
      if (flags.filter) {
        const f = String(flags.filter).toLowerCase();
        entries = entries.filter(([key]) => key.toLowerCase().includes(f));
      }
      if (flags.limit !== undefined) {
        const n = parseInt(flags.limit, 10);
        if (Number.isFinite(n) && n > 0) entries = entries.slice(0, n);
      }
      console.log(JSON.stringify(Object.fromEntries(entries), null, 2));
      return;
    }
    case 'set': {
      const key = positional[0];
      if (!key || !key.includes('/')) {
        console.error('Usage: lazyclaw rates set <provider/model> --input <N> --output <N> [--cache-read <N>] [--cache-create <N>] [--currency USD]');
        process.exit(2);
      }
      const inputPer1M = flags.input !== undefined ? Number(flags.input) : null;
      const outputPer1M = flags.output !== undefined ? Number(flags.output) : null;
      if (!Number.isFinite(inputPer1M) || !Number.isFinite(outputPer1M) || inputPer1M < 0 || outputPer1M < 0) {
        console.error('rates set: --input and --output must be non-negative numbers (per million tokens)');
        process.exit(2);
      }
      const card = { inputPer1M, outputPer1M };
      if (flags['cache-read'] !== undefined) card.cacheReadPer1M = Number(flags['cache-read']);
      if (flags['cache-create'] !== undefined) card.cacheCreatePer1M = Number(flags['cache-create']);
      if (flags.currency) card.currency = String(flags.currency);
      else card.currency = 'USD';
      const cfg = readConfig();
      cfg.rates = cfg.rates || {};
      cfg.rates[key] = card;
      writeConfig(cfg);
      console.log(JSON.stringify({ ok: true, key, card }));
      return;
    }
    case 'delete':
    case 'unset': {
      const key = positional[0];
      if (!key) { console.error('Usage: lazyclaw rates delete <provider/model>'); process.exit(2); }
      const cfg = readConfig();
      const had = !!(cfg.rates && cfg.rates[key]);
      if (cfg.rates) delete cfg.rates[key];
      writeConfig(cfg);
      console.log(JSON.stringify({ ok: true, key, removed: had }));
      return;
    }
    case 'shape': {
      // Print the reference shape so users can copy-paste into config.
      const mod = await import('./providers/rates.mjs');
      console.log(JSON.stringify(mod.RATE_CARD_SHAPE, null, 2));
      return;
    }
    case 'copy': {
      // Clone a rate card from <src/model> to <dst/model>. Useful when
      // a new model launches at the same price as a known one and you
      // don't want to retype every field.
      //
      // Refuses to overwrite an existing destination unless --force is
      // passed (a rate card is operator-curated; silent overwrite is
      // exactly the wrong default).
      const src = positional[0];
      const dst = positional[1];
      if (!src || !dst || !src.includes('/') || !dst.includes('/')) {
        console.error('Usage: lazyclaw rates copy <src-provider/model> <dst-provider/model> [--force]');
        process.exit(2);
      }
      const cfg = readConfig();
      const rates = cfg.rates && typeof cfg.rates === 'object' ? cfg.rates : {};
      if (!rates[src]) {
        console.error(`rates copy: source key "${src}" not found in cfg.rates`);
        process.exit(1);
      }
      if (rates[dst] && !flags.force) {
        console.error(`rates copy: destination "${dst}" already exists (pass --force to overwrite)`);
        process.exit(1);
      }
      // Deep clone (small object) so a later edit to one doesn't
      // mutate the other.
      cfg.rates = rates;
      cfg.rates[dst] = JSON.parse(JSON.stringify(rates[src]));
      writeConfig(cfg);
      console.log(JSON.stringify({ ok: true, src, dst, card: cfg.rates[dst] }));
      return;
    }
    case 'validate': {
      // Shape check shared with daemon's GET /rates/validate via
      // rates-validate.mjs. Single source of truth.
      const cfg = readConfig();
      await ensureRegistry();
      const { validateRates } = await import('./rates-validate.mjs');
      const result = validateRates(cfg.rates, _registryMod.PROVIDERS);
      console.log(JSON.stringify(result, null, 2));
      process.exit(result.ok ? 0 : 1);
    }
    default:
      console.error('Usage: lazyclaw rates <list|set <key>|delete <key>|shape|validate>');
      process.exit(2);
  }
}

// Loads on first use to avoid paying the import cost when the user
// only ran `lazyclaw chat` or similar; cli.mjs is already a 2700-line
// hot path and we don't need every helper paged in.
let _configFeatures = null;
async function _ensureConfigFeatures() {
  if (!_configFeatures) _configFeatures = await import('./config_features.mjs');
  return _configFeatures;
}

async function cmdAuth(sub, positional, flags = {}) {
  const m = await _ensureConfigFeatures();
  const cfg = readConfig();
  switch (sub) {
    case undefined:
    case 'list': {
      const provider = positional[0];
      if (!provider) {
        // No provider given → return the active-label map for every
        // provider that has at least one profile so the user can see
        // their full auth state at once.
        const out = {};
        for (const p of Object.keys(cfg.authProfiles || {})) {
          out[p] = {
            active: (cfg.authActiveProfile || {})[p] || null,
            profiles: m.authList(cfg, p),
          };
        }
        console.log(JSON.stringify(out, null, 2));
        return;
      }
      const profiles = m.authList(cfg, provider);
      console.log(JSON.stringify({
        provider,
        active: (cfg.authActiveProfile || {})[provider] || null,
        profiles,
      }, null, 2));
      return;
    }
    case 'add': {
      const [provider, key] = positional;
      if (!provider || !key) {
        console.error('Usage: lazyclaw auth add <provider> <key> [--label <name>]');
        process.exit(2);
      }
      try {
        const lbl = m.authAdd(cfg, provider, key, flags.label);
        writeConfig(cfg);
        console.log(JSON.stringify({ ok: true, provider, label: lbl }));
      } catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      return;
    }
    case 'remove': {
      const [provider, label] = positional;
      if (!provider || !label) {
        console.error('Usage: lazyclaw auth remove <provider> <label>');
        process.exit(2);
      }
      try { m.authRemove(cfg, provider, label); writeConfig(cfg); }
      catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      console.log(JSON.stringify({ ok: true, provider, removed: label }));
      return;
    }
    case 'use': {
      const [provider, label] = positional;
      if (!provider || !label) {
        console.error('Usage: lazyclaw auth use <provider> <label>');
        process.exit(2);
      }
      try { m.authUse(cfg, provider, label); writeConfig(cfg); }
      catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      console.log(JSON.stringify({ ok: true, provider, active: label }));
      return;
    }
    case 'rotate': {
      const provider = positional[0];
      if (!provider) {
        console.error('Usage: lazyclaw auth rotate <provider>');
        process.exit(2);
      }
      const next = m.authRotate(cfg, provider);
      if (!next) {
        console.error(`error: need at least 2 profiles to rotate (provider "${provider}")`);
        process.exit(1);
      }
      writeConfig(cfg);
      console.log(JSON.stringify({ ok: true, provider, active: next }));
      return;
    }
    default:
      console.error('Usage: lazyclaw auth <list|add|remove|use|rotate> ...');
      process.exit(2);
  }
}

async function cmdPairing(sub, positional, flags = {}) {
  const m = await _ensureConfigFeatures();
  const cfg = readConfig();
  switch (sub) {
    case undefined:
    case 'list':
      console.log(JSON.stringify(m.pairingList(cfg), null, 2));
      return;
    case 'add': {
      const id = positional[0];
      if (!id) {
        console.error('Usage: lazyclaw pairing add <id> [--label <name>]');
        process.exit(2);
      }
      try { m.pairingAdd(cfg, id, flags.label); writeConfig(cfg); }
      catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      console.log(JSON.stringify({ ok: true, id }));
      return;
    }
    case 'remove': {
      const id = positional[0];
      if (!id) {
        console.error('Usage: lazyclaw pairing remove <id>');
        process.exit(2);
      }
      try { m.pairingRemove(cfg, id); writeConfig(cfg); }
      catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      console.log(JSON.stringify({ ok: true, removed: id }));
      return;
    }
    default:
      console.error('Usage: lazyclaw pairing <list|add|remove> ...');
      process.exit(2);
  }
}

async function cmdNodes(sub, positional, flags = {}) {
  const m = await _ensureConfigFeatures();
  const cfg = readConfig();
  switch (sub) {
    case undefined:
    case 'list':
      console.log(JSON.stringify(m.nodesList(cfg), null, 2));
      return;
    case 'register': {
      const id = positional[0];
      if (!id) {
        console.error('Usage: lazyclaw nodes register <id> [--platform macos|ios|android|web|cli] [--label <name>]');
        process.exit(2);
      }
      try { m.nodesRegister(cfg, id, flags.platform || 'cli', flags.label || ''); writeConfig(cfg); }
      catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      console.log(JSON.stringify({ ok: true, id, platform: flags.platform || 'cli' }));
      return;
    }
    case 'remove': {
      const id = positional[0];
      if (!id) {
        console.error('Usage: lazyclaw nodes remove <id>');
        process.exit(2);
      }
      try { m.nodesRemove(cfg, id); writeConfig(cfg); }
      catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      console.log(JSON.stringify({ ok: true, removed: id }));
      return;
    }
    default:
      console.error('Usage: lazyclaw nodes <list|register|remove> ...');
      process.exit(2);
  }
}

async function cmdMessage(sub, positional, flags = {}) {
  const m = await _ensureConfigFeatures();
  const cfg = readConfig();
  switch (sub) {
    case undefined:
    case 'list':
      console.log(JSON.stringify(m.messageList(cfg), null, 2));
      return;
    case 'add': {
      const [name, url] = positional;
      if (!name || !url) {
        console.error('Usage: lazyclaw message add <name> <webhook-url> [--kind slack|discord|generic]');
        process.exit(2);
      }
      try { m.messageAdd(cfg, name, url, flags.kind); writeConfig(cfg); }
      catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      console.log(JSON.stringify({ ok: true, name }));
      return;
    }
    case 'remove': {
      const name = positional[0];
      if (!name) {
        console.error('Usage: lazyclaw message remove <name>');
        process.exit(2);
      }
      try { m.messageRemove(cfg, name); writeConfig(cfg); }
      catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      console.log(JSON.stringify({ ok: true, removed: name }));
      return;
    }
    case 'send': {
      const [name, ...textParts] = positional;
      if (!name) {
        console.error('Usage: lazyclaw message send <name> <text|->');
        process.exit(2);
      }
      let text = textParts.join(' ');
      // `-` reads body from stdin so a long agent reply can be piped:
      //   lazyclaw agent "summarize foo" | lazyclaw message send team -
      if (text === '-' || (!text && !process.stdin.isTTY)) {
        text = await new Promise((resolve) => {
          let buf = '';
          process.stdin.on('data', (c) => { buf += c; });
          process.stdin.on('end', () => resolve(buf.trim()));
        });
      }
      if (!text) {
        console.error('error: empty message body');
        process.exit(1);
      }
      try {
        const r = await m.messageSend(cfg, name, text);
        console.log(JSON.stringify(r));
      } catch (e) {
        console.error(`error: ${e.message}`); process.exit(1);
      }
      return;
    }
    default:
      console.error('Usage: lazyclaw message <list|add|remove|send> ...');
      process.exit(2);
  }
}

async function cmdWorkspace(sub, positional, flags = {}) {
  const ws = await import('./workspace.mjs');
  const cfgDir = path.dirname(configPath());
  switch (sub) {
    case undefined:
    case 'list': {
      console.log(JSON.stringify(ws.listWorkspaces(cfgDir), null, 2));
      return;
    }
    case 'init': {
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw workspace init <name>'); process.exit(2); }
      try {
        const dir = ws.initWorkspace(cfgDir, name);
        console.log(JSON.stringify({ ok: true, name, dir, files: ws.WORKSPACE_FILES }));
      } catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      return;
    }
    case 'show': {
      const [name, fileName] = positional;
      if (!name) { console.error('Usage: lazyclaw workspace show <name> [<file>]'); process.exit(2); }
      try {
        if (fileName) process.stdout.write(ws.readWorkspaceFile(cfgDir, name, fileName));
        else          process.stdout.write(ws.composeWorkspacePrompt(cfgDir, name) + '\n');
      } catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      return;
    }
    case 'remove': {
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw workspace remove <name>'); process.exit(2); }
      try { ws.removeWorkspace(cfgDir, name); }
      catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      console.log(JSON.stringify({ ok: true, removed: name }));
      return;
    }
    case 'path': {
      const name = positional[0];
      if (!name) { console.log(ws.workspaceRoot(cfgDir)); return; }
      try { console.log(ws.workspaceDir(cfgDir, name)); }
      catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      return;
    }
    default:
      console.error('Usage: lazyclaw workspace <list|init|show|remove|path> ...');
      process.exit(2);
  }
}

async function cmdBrowse(url, flags = {}) {
  if (!url) { console.error('Usage: lazyclaw browse <url> [--max-bytes <N>] [--timeout-ms <N>] [--meta]'); process.exit(2); }
  const { browse } = await import('./browse.mjs');
  const opts = {};
  if (flags['max-bytes'] !== undefined) opts.maxBytes = parseInt(flags['max-bytes'], 10);
  if (flags['timeout-ms'] !== undefined) opts.timeoutMs = parseInt(flags['timeout-ms'], 10);
  if (flags['user-agent']) opts.userAgent = flags['user-agent'];
  try {
    const r = await browse(url, opts);
    if (flags.meta) {
      process.stderr.write(JSON.stringify({
        url: r.url, title: r.title, bytes: r.bytes, truncated: r.truncated,
      }) + '\n');
    }
    process.stdout.write(r.markdown);
  } catch (e) {
    console.error(`error: ${e?.message || e}`);
    process.exit(1);
  }
}

async function cmdCron(sub, positional, flags = {}) {
  const cron = await import('./cron.mjs');
  const cfg = readConfig();
  const backend = cron.pickBackend();
  switch (sub) {
    case undefined:
    case 'list': {
      const jobs = cron.listJobs(cfg);
      console.log(JSON.stringify({ backend, jobs }, null, 2));
      return;
    }
    case 'show': {
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw cron show <name>'); process.exit(2); }
      const job = cron.getJob(cfg, name);
      if (!job) { console.error(`error: no job "${name}"`); process.exit(1); }
      console.log(JSON.stringify({ backend, name, ...job }, null, 2));
      return;
    }
    case 'add': {
      // Shape: lazyclaw cron add <name> "<cron-spec>" -- <cmd> [args...]
      // The `--` separator was already consumed by parseArgs, but
      // the spec is the second positional and the command is
      // everything after it. parseArgs preserves order, so:
      //   positional[0] = name
      //   positional[1] = "0 9 * * *"
      //   positional[2..] = cmd argv
      const [name, schedule, ...cmd] = positional;
      if (!name || !schedule || !cmd.length) {
        console.error('Usage: lazyclaw cron add <name> "<cron-spec>" -- <cmd> ...');
        process.exit(2);
      }
      try {
        cron.upsertJob(cfg, name, schedule, cmd);
      } catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      writeConfig(cfg);
      // Install to system scheduler — failure here doesn't roll
      // back the config write because the job is "scheduled in
      // intent". `cron sync` reconciles.
      try {
        if (backend === 'launchd') cron.installLaunchdJob(name, schedule, cmd);
        else                       cron.installCrontabJob(name, schedule, cmd);
      } catch (e) {
        console.error(`warn: backend install failed: ${e.message} — config saved; run \`cron sync\` to retry`);
        process.exit(1);
      }
      console.log(JSON.stringify({ ok: true, backend, name, schedule, command: cmd }, null, 2));
      return;
    }
    case 'remove': {
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw cron remove <name>'); process.exit(2); }
      try { cron.removeJob(cfg, name); } catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      writeConfig(cfg);
      try {
        if (backend === 'launchd') cron.uninstallLaunchdJob(name);
        else                       cron.uninstallCrontabJob(name);
      } catch (e) {
        console.error(`warn: backend uninstall failed: ${e.message}`);
      }
      console.log(JSON.stringify({ ok: true, backend, removed: name }));
      return;
    }
    case 'sync': {
      // Re-install every job in cfg.cron — useful after a fresh
      // OS image where the launchd plists / crontab were wiped.
      const out = [];
      for (const [name, job] of Object.entries(cfg.cron || {})) {
        try {
          if (backend === 'launchd') cron.installLaunchdJob(name, job.schedule, job.command);
          else                       cron.installCrontabJob(name, job.schedule, job.command);
          out.push({ name, ok: true });
        } catch (e) {
          out.push({ name, ok: false, error: e.message });
        }
      }
      console.log(JSON.stringify({ backend, results: out }, null, 2));
      return;
    }
    case 'run': {
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw cron run <name>'); process.exit(2); }
      try {
        const code = cron.runJob(cfg, name);
        process.exit(code || 0);
      } catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
      return;
    }
    default:
      console.error('Usage: lazyclaw cron <list|add|remove|show|sync|run> ...');
      process.exit(2);
  }
}

async function cmdSkills(sub, positional, flags = {}) {
  const skillsMod = await import('./skills.mjs');
  const cfgDir = path.dirname(configPath());
  switch (sub) {
    case undefined:
    case 'list': {
      // Same --filter / --limit semantic as v3.33's sessions list:
      // case-insensitive name substring, then post-filter cap.
      let items = skillsMod.listSkills(cfgDir);
      if (flags.filter) {
        const f = String(flags.filter).toLowerCase();
        items = items.filter(s => s.name.toLowerCase().includes(f));
      }
      if (flags.limit !== undefined) {
        const n = parseInt(flags.limit, 10);
        if (Number.isFinite(n) && n > 0) items = items.slice(0, n);
      }
      console.log(JSON.stringify(items.map(s => ({ name: s.name, bytes: s.bytes, summary: s.summary })), null, 2));
      return;
    }
    case 'show': {
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw skills show <name>'); process.exit(2); }
      try { process.stdout.write(skillsMod.loadSkill(name, cfgDir)); }
      catch (e) { console.error(e.message); process.exit(1); }
      return;
    }
    case 'install': {
      // Four forms:
      //   1. install user/repo[@ref][:subpath]   — GitHub bundle
      //   2. install <name> --from <path>
      //   3. install <name> --from-url <https://...>
      //   4. install <name>                       — body via stdin
      // Detect form 1 via a slash in the first positional and the
      // absence of any --from* flag (so a literal local skill name
      // with `/` still routes to the explicit-flag branch — though
      // skillPath() rejects slashes anyway).
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw skills install <user/repo[@ref][:path]> | <name> [--from <path> | --from-url <https://...>]'); process.exit(2); }
      if (name.includes('/') && !flags.from && !flags['from-url']) {
        const inst = await import('./skills_install.mjs');
        try {
          const r = await inst.installFromGithub(name, cfgDir, {
            prefix: flags.prefix || '',
            force: !!flags.force,
            maxBytes: flags['max-bytes'] !== undefined ? parseInt(flags['max-bytes'], 10) : undefined,
            timeoutMs: flags['timeout-ms'] !== undefined ? parseInt(flags['timeout-ms'], 10) : undefined,
          });
          console.log(JSON.stringify({
            ok: true,
            spec: `${r.spec.owner}/${r.spec.repo}@${r.spec.ref}${r.spec.subpath ? ':' + r.spec.subpath : ''}`,
            installed: r.installed,
            skipped: r.skipped,
          }, null, 2));
          return;
        } catch (e) {
          console.error(`error: ${e?.message || e}`);
          process.exit(1);
        }
      }
      let content;
      if (flags['from-url']) {
        const url = String(flags['from-url']);
        // Refuse http/file/data — only https. The skill content goes
        // straight into the system prompt, so source authenticity matters.
        if (!url.startsWith('https://')) {
          console.error('skills install --from-url requires an https:// URL');
          process.exit(2);
        }
        const fetchFn = globalThis.fetch;
        if (!fetchFn) { console.error('fetch is not available in this Node runtime'); process.exit(1); }
        // Configurable max size — protect against pathological responses
        // that would balloon the prompt and the disk file. 1 MiB cap.
        const MAX_BYTES = 1_048_576;
        try {
          const res = await fetchFn(url, { redirect: 'follow' });
          if (!res.ok) { console.error(`fetch ${url} → ${res.status}`); process.exit(1); }
          // Stream the body so we can stop at the cap rather than loading
          // an arbitrarily large response into memory.
          const reader = res.body?.getReader?.();
          if (!reader) { content = await res.text(); }
          else {
            const chunks = [];
            let total = 0;
            while (true) {
              const { value, done } = await reader.read();
              if (done) break;
              total += value.length;
              if (total > MAX_BYTES) {
                console.error(`skills install: response exceeds ${MAX_BYTES} bytes; refusing`);
                process.exit(1);
              }
              chunks.push(value);
            }
            content = new TextDecoder('utf-8', { fatal: false }).decode(Buffer.concat(chunks.map(c => Buffer.from(c))));
          }
        } catch (e) {
          console.error(`skills install fetch failed: ${e?.message || e}`);
          process.exit(1);
        }
      } else if (flags.from) {
        content = fs.readFileSync(flags.from, 'utf8');
      } else {
        content = await new Promise(resolve => {
          let buf = '';
          process.stdin.setEncoding('utf8');
          process.stdin.on('data', d => { buf += d; });
          process.stdin.on('end', () => resolve(buf));
        });
      }
      const written = skillsMod.installSkill(name, content, cfgDir);
      console.log(JSON.stringify({ ok: true, name, path: written, bytes: content.length }));
      return;
    }
    case 'remove': {
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw skills remove <name>'); process.exit(2); }
      skillsMod.removeSkill(name, cfgDir);
      console.log(JSON.stringify({ ok: true, removed: name }));
      return;
    }
    case 'search': {
      // Mirror of `lazyclaw sessions search` — case-insensitive substring
      // by default, --regex for pattern mode. Returns per-skill match
      // count + first-excerpt window (40 chars before/after match).
      // The skill body IS markdown so users typically search for terms
      // mentioned in instructions or examples.
      const query = positional[0];
      if (!query) { console.error('Usage: lazyclaw skills search <query> [--regex]'); process.exit(2); }
      const useRegex = !!flags.regex;
      let matcher;
      if (useRegex) {
        try { matcher = new RegExp(query, 'i'); }
        catch (e) { console.error(`invalid regex: ${e.message}`); process.exit(2); }
      } else {
        const q = query.toLowerCase();
        matcher = { test: (s) => String(s).toLowerCase().includes(q) };
      }
      const items = skillsMod.listSkills(cfgDir);
      const matches = [];
      for (const s of items) {
        let body;
        try { body = skillsMod.loadSkill(s.name, cfgDir); }
        catch { continue; }   // file may have been removed mid-listing
        // Count matches across the whole body, not per-line. For a
        // skill body that's a few KB this is plenty fast and the count
        // matches the user's intuition of "how many times does it
        // mention X."
        let matchCount = 0;
        let firstExcerpt = null;
        if (useRegex) {
          // Re-anchor the regex with /gi so we can iterate; the original
          // matcher was /i for boolean test() above. Rebuild here.
          const gFlag = new RegExp(query, 'gi');
          for (const m of body.matchAll(gFlag)) {
            matchCount++;
            if (firstExcerpt === null) {
              const pos = m.index ?? 0;
              const start = Math.max(0, pos - 40);
              const end = Math.min(body.length, pos + m[0].length + 40);
              firstExcerpt = (start > 0 ? '…' : '') + body.slice(start, end) + (end < body.length ? '…' : '');
            }
          }
        } else {
          const lower = body.toLowerCase();
          const q = query.toLowerCase();
          let pos = 0;
          while (true) {
            const i = lower.indexOf(q, pos);
            if (i < 0) break;
            matchCount++;
            if (firstExcerpt === null) {
              const start = Math.max(0, i - 40);
              const end = Math.min(body.length, i + q.length + 40);
              firstExcerpt = (start > 0 ? '…' : '') + body.slice(start, end) + (end < body.length ? '…' : '');
            }
            pos = i + q.length;
          }
        }
        if (matchCount > 0) {
          matches.push({
            name: s.name,
            bytes: s.bytes,
            matchCount,
            excerpt: firstExcerpt,
          });
        }
      }
      console.log(JSON.stringify({ query, regex: useRegex, matches }, null, 2));
      return;
    }
    default:
      console.error('Usage: lazyclaw skills <list|show <name>|install <name> [--from path]|remove <name>|search <query> [--regex]>');
      process.exit(2);
  }
}

async function cmdProviders(sub, positional, flags = {}) {
  await ensureRegistry();
  switch (sub) {
    case undefined:
    case 'list': {
      // Defensive: if metadata is missing for a registered provider, fall back
      // to a minimal shape so this never crashes the CLI even mid-refactor.
      // --filter / --limit pattern matches v3.33-v3.46 across the other
      // list surfaces. Filter on provider name, case-insensitive.
      let out = Object.keys(_registryMod.PROVIDERS).map(name => {
        const meta = _registryMod.PROVIDER_INFO[name] || { name, requiresApiKey: false, docs: '' };
        return {
          name,
          requiresApiKey: !!meta.requiresApiKey,
          defaultModel: meta.defaultModel || null,
          suggestedModels: meta.suggestedModels || [],
        };
      });
      if (flags.filter) {
        const f = String(flags.filter).toLowerCase();
        out = out.filter(p => p.name.toLowerCase().includes(f));
      }
      if (flags.limit !== undefined) {
        const n = parseInt(flags.limit, 10);
        if (Number.isFinite(n) && n > 0) out = out.slice(0, n);
      }
      console.log(JSON.stringify(out, null, 2));
      return;
    }
    case 'info': {
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw providers info <name>'); process.exit(2); }
      const meta = _registryMod.PROVIDER_INFO[name];
      if (!meta) {
        console.error(`unknown provider: ${name} (registered: ${Object.keys(_registryMod.PROVIDERS).join(', ')})`);
        process.exit(2);
      }
      console.log(JSON.stringify(meta, null, 2));
      return;
    }
    case 'test': {
      // Smoke-test a provider with a tiny ("ping") prompt. Useful after
      // configuring a new API key — surfaces auth errors fast without
      // waiting for the next real call to fail.
      //
      // Output:
      //   { ok: bool, provider, model, durationMs, [reply | error, code] }
      //
      // Exit codes:
      //   0 — provider returned a non-empty reply
      //   1 — provider returned an error (auth failure, rate limit, ...)
      //   2 — invalid invocation (unknown name)
      //
      // No name OR --all: smoke-test every registered provider in
      // parallel. Output is `{ ok, results: [...] }` where ok is true
      // iff every entry passed. Exit 0 when all pass, 1 otherwise.
      const name = positional[0];
      const cfg = readConfig();
      const promptIdx = positional.indexOf('--prompt');
      const sharedPrompt = flags.prompt || (promptIdx >= 0 ? positional[promptIdx + 1] : null) || 'ping';
      if (!name || flags.all) {
        const apiKey = cfg['api-key'] || '';
        const t0all = Date.now();
        const results = await Promise.all(
          Object.entries(_registryMod.PROVIDERS).map(async ([pid, provider]) => {
            const meta = _registryMod.PROVIDER_INFO[pid] || {};
            const model = flags.model || cfg.model || meta.defaultModel || 'unknown';
            const t0 = Date.now();
            try {
              let reply = '';
              const stream = provider.sendMessage([{ role: 'user', content: sharedPrompt }], { apiKey, model });
              for await (const chunk of stream) {
                if (typeof chunk === 'string') reply += chunk;
              }
              return {
                name: pid, ok: reply.length > 0, model,
                durationMs: Date.now() - t0,
                replyLength: reply.length,
              };
            } catch (err) {
              return {
                name: pid, ok: false, model,
                durationMs: Date.now() - t0,
                error: err?.message || String(err),
                code: err?.code || null,
              };
            }
          }),
        );
        const allOk = results.every(r => r.ok);
        console.log(JSON.stringify({
          ok: allOk,
          totalDurationMs: Date.now() - t0all,
          results,
        }, null, 2));
        process.exit(allOk ? 0 : 1);
      }
      const provider = _registryMod.PROVIDERS[name];
      if (!provider) {
        console.error(`unknown provider: ${name} (registered: ${Object.keys(_registryMod.PROVIDERS).join(', ')})`);
        process.exit(2);
      }
      // cfg already declared above for the all-mode branch; reuse it.
      const meta = _registryMod.PROVIDER_INFO[name] || {};
      // --model / --prompt come in via the parsed flags map (parseArgs
      // lifted them out of positional). --model wins over config.model
      // wins over PROVIDER_INFO.defaultModel.
      const model = flags.model || cfg.model || meta.defaultModel || 'unknown';
      const prompt = flags.prompt || 'ping';
      const apiKey = cfg['api-key'] || '';
      const t0 = Date.now();
      try {
        // Drain the streaming response (every provider yields chunks of
        // string). For mock this is instant; for real providers it's
        // bounded by the prompt length and provider latency. We don't
        // support a timeout flag here — the user can SIGINT if a
        // provider hangs.
        let reply = '';
        const stream = provider.sendMessage([{ role: 'user', content: prompt }], { apiKey, model });
        for await (const chunk of stream) {
          if (typeof chunk === 'string') reply += chunk;
        }
        const durationMs = Date.now() - t0;
        const ok = reply.length > 0;
        console.log(JSON.stringify({
          ok,
          provider: name,
          model,
          durationMs,
          replyLength: reply.length,
          reply: reply.slice(0, 200) + (reply.length > 200 ? '…' : ''),
        }, null, 2));
        process.exit(ok ? 0 : 1);
      } catch (err) {
        const durationMs = Date.now() - t0;
        console.log(JSON.stringify({
          ok: false,
          provider: name,
          model,
          durationMs,
          error: err?.message || String(err),
          code: err?.code || null,
        }, null, 2));
        process.exit(1);
      }
    }
    default:
      console.error('Usage: lazyclaw providers <list|info <name>|test <name> [--model X] [--prompt T]>');
      process.exit(2);
  }
}

async function cmdSessions(sub, positional, flags = {}) {
  const sessionsMod = await import('./sessions.mjs');
  const cfgDir = path.dirname(configPath());
  switch (sub) {
    case 'list': {
      // --filter <substring> applies a case-insensitive id substring
      // filter (no regex, deliberately — filtering on session ids is
      // typically about prefixes or fragments).
      // --limit <N> caps the result count after filter+sort. Negative
      // or zero values are ignored so a script can pass `--limit 0`
      // explicitly to opt out without special-casing.
      // --with-turn-count: opt-in flag that adds `turnCount` per
      // session. Loads each session file (one fs.read each) — opt-in
      // because the default `list` should be fast even with thousands
      // of sessions.
      let items = sessionsMod.listSessions(cfgDir);
      if (flags.filter) {
        const f = String(flags.filter).toLowerCase();
        items = items.filter(s => s.id.toLowerCase().includes(f));
      }
      if (flags.limit !== undefined) {
        const n = parseInt(flags.limit, 10);
        if (Number.isFinite(n) && n > 0) items = items.slice(0, n);
      }
      let out = items.map(s => {
        const base = { id: s.id, bytes: s.bytes, mtime: new Date(s.mtimeMs).toISOString(), _mtimeMs: s.mtimeMs };
        if (flags['with-turn-count'] || flags['sort-by'] === 'turn-count') {
          try { base.turnCount = sessionsMod.loadTurns(s.id, cfgDir).length; }
          catch { base.turnCount = null; }
        }
        return base;
      });
      // --sort-by mtime|turn-count|bytes|id. Default is mtime descending
      // (matches the underlying listSessions behavior). turn-count
      // implicitly enables turnCount loading above.
      if (flags['sort-by']) {
        const valid = new Set(['mtime', 'turn-count', 'bytes', 'id']);
        if (!valid.has(flags['sort-by'])) {
          console.error(`invalid --sort-by: ${flags['sort-by']} (expected: mtime, turn-count, bytes, id)`);
          process.exit(2);
        }
        const cmp = {
          mtime:        (a, b) => b._mtimeMs - a._mtimeMs,
          'turn-count': (a, b) => (b.turnCount ?? 0) - (a.turnCount ?? 0),
          bytes:        (a, b) => b.bytes - a.bytes,
          id:           (a, b) => a.id.localeCompare(b.id),
        };
        out.sort(cmp[flags['sort-by']]);
      }
      // Strip the internal helper field before serializing.
      out = out.map(({ _mtimeMs, ...rest }) => rest);
      console.log(JSON.stringify(out, null, 2));
      return;
    }
    case 'show': {
      const id = positional[0];
      if (!id) { console.error('Usage: lazyclaw sessions show <id>'); process.exit(2); }
      const turns = sessionsMod.loadTurns(id, cfgDir);
      console.log(JSON.stringify(turns, null, 2));
      return;
    }
    case 'clear': {
      const id = positional[0];
      if (!id) { console.error('Usage: lazyclaw sessions clear <id>'); process.exit(2); }
      sessionsMod.clearSession(id, cfgDir);
      console.log(JSON.stringify({ ok: true, cleared: id }));
      return;
    }
    case 'export': {
      const id = positional[0];
      if (!id) { console.error('Usage: lazyclaw sessions export <id> [--format md|json|text]'); process.exit(2); }
      const format = (flags.format || 'md').toLowerCase();
      const formatters = {
        md: sessionsMod.exportMarkdown,
        markdown: sessionsMod.exportMarkdown,
        json: sessionsMod.exportJson,
        text: sessionsMod.exportText,
        txt: sessionsMod.exportText,
      };
      const fn = formatters[format];
      if (!fn) {
        console.error(`unknown export format: ${format} (expected: md, json, text)`);
        process.exit(2);
      }
      try { process.stdout.write(fn(id, cfgDir)); }
      catch (e) { console.error(e.message); process.exit(1); }
      return;
    }
    case 'search': {
      const query = positional[0];
      if (!query) { console.error('Usage: lazyclaw sessions search <query> [--regex]'); process.exit(2); }
      // --regex came in via the parsed flags map (parseArgs lifted it
      // out of positional). 'regex' is also in BOOLEAN_FLAGS so it
      // never consumes the next argument.
      const useRegex = !!flags.regex;
      let matcher;
      if (useRegex) {
        try { matcher = new RegExp(query, 'i'); }
        catch (e) { console.error(`invalid regex: ${e.message}`); process.exit(2); }
      } else {
        // Case-insensitive substring search. The naive `s.includes(q)`
        // pattern is exactly what the user wants — same shape they'd
        // get from `grep -i`.
        const q = query.toLowerCase();
        matcher = { test: (s) => String(s).toLowerCase().includes(q) };
      }
      const items = sessionsMod.listSessions(cfgDir);
      const matches = [];
      for (const s of items) {
        const turns = sessionsMod.loadTurns(s.id, cfgDir);
        let matchCount = 0;
        let firstExcerpt = null;
        for (const t of turns) {
          if (typeof t?.content !== 'string') continue;
          if (matcher.test(t.content)) {
            matchCount++;
            if (firstExcerpt === null) {
              // Excerpt: 40 chars before/after first match, clamped at
              // string boundaries. For regex matches we need to find
              // the actual position; for substring use indexOf.
              const c = t.content;
              let pos;
              if (useRegex) {
                pos = c.search(matcher);
              } else {
                pos = c.toLowerCase().indexOf(query.toLowerCase());
              }
              if (pos < 0) pos = 0;
              const start = Math.max(0, pos - 40);
              const end = Math.min(c.length, pos + query.length + 40);
              firstExcerpt = (start > 0 ? '…' : '') + c.slice(start, end) + (end < c.length ? '…' : '');
            }
          }
        }
        if (matchCount > 0) {
          matches.push({
            id: s.id,
            mtime: new Date(s.mtimeMs).toISOString(),
            matchCount,
            excerpt: firstExcerpt,
          });
        }
      }
      console.log(JSON.stringify({ query, regex: useRegex, matches }, null, 2));
      // Exit 0 even on no matches — `grep` convention is exit 1, but
      // a CLI tool that returns JSON should always exit 0 on a
      // successful search; the caller checks `matches.length` for
      // emptiness.
      return;
    }
    default:
      console.error('Usage: lazyclaw sessions <list|show <id>|clear <id>|export <id>|search <query> [--regex]>');
      process.exit(2);
  }
}

function cmdConfigGet(key) {
  const cfg = readConfig();
  if (key) console.log(JSON.stringify({ key, value: cfg[key] ?? null }));
  else console.log(JSON.stringify(cfg));
}

// Structural integrity check across the whole config. Distinct from
// `lazyclaw doctor` (runtime checks: provider available, key present
// for the active provider). Validate is purely about *shape* — does
// every value have the right type, is `provider` known, are rates
// well-formed.
//
// Hard issues exit 1; unknown top-level keys produce warnings (kept
// exit 0 so a forward-compatible config from a newer CLI doesn't
// fail validate on an older CLI).
async function cmdConfigValidate() {
  const cfg = readConfig();
  await ensureRegistry();
  const { validateConfig } = await import('./config-validate.mjs');
  const { ok, issues, warnings } = validateConfig(cfg, _registryMod.PROVIDERS);
  console.log(JSON.stringify({
    ok,
    configPath: configPath(),
    keys: Object.keys(cfg),
    issues,
    warnings,
  }, null, 2));
  process.exit(ok ? 0 : 1);
}

// Flags whose presence is the signal — they don't consume the next arg
// even when one is available. Without this allow-list,
// `lazyclaw run --parallel demo wf.mjs` would set `flags.parallel='demo'`
// and silently lose the session id; the user would only see a
// "missing positional" error after the dispatcher rejected it.
const BOOLEAN_FLAGS = new Set([
  'parallel',
  'parallel-persistent',
  'once',
  'non-interactive',
  'include-secrets',
  'include-sessions',
  'overwrite-skills',
  'no-overwrite-config',
  'import-sessions',
  'show-thinking',
  'usage',
  'cost',
  'response-cache',
  'help',         // also handled as a subcommand alias
  'version',
  'summary',      // inspect: trim per-node detail
  'regex',        // sessions search: treat query as a regex
  'lr',           // graph: emit Mermaid `graph LR` (left-right)
  'force',        // rates copy: overwrite existing destination
  'aggregate',    // inspect (list mode): per-node stats across sessions
  'all',          // providers test: run all providers in parallel
  'with-turn-count', // sessions list: include turn count per session
]);

function parseArgs(argv) {
  const out = { positional: [], flags: {} };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    // POSIX `--`: everything after is positional verbatim. Used by
    // `cron add <name> "<spec>" -- <cmd> [args...]` so a recurring
    // command with --flag of its own doesn't get parsed as our flag.
    if (a === '--') {
      for (let j = i + 1; j < argv.length; j++) out.positional.push(argv[j]);
      break;
    }
    if (a.startsWith('--')) {
      const eq = a.indexOf('=');
      if (eq >= 0) {
        out.flags[a.slice(2, eq)] = a.slice(eq + 1);
      } else {
        const name = a.slice(2);
        if (BOOLEAN_FLAGS.has(name)) {
          // Known boolean — never consumes the next arg.
          out.flags[name] = true;
          continue;
        }
        const next = argv[i + 1];
        if (next === undefined || next.startsWith('--')) {
          // Unknown flag at end-of-args or before another --flag: still boolean.
          out.flags[name] = true;
        } else {
          out.flags[name] = next;
          i += 1;
        }
      }
    } else out.positional.push(a);
  }
  return out;
}

// Interactive launcher — fired when the user types `lazyclaw` with
// no subcommand AND we're attached to a TTY. OpenClaw's launcher
// pattern: ASCII banner + provider/model status + arrow-key menu of
// every common action. Selecting a row drops the user into the
// matching subcommand via process.argv mutation + main() re-entry,
// so chat / agent / etc. behave bit-identically to typing them
// directly. Non-TTY (piped, scripted) callers still see the
// classic "Usage: …" line so automation isn't surprised.
// Multi-step setup wizard — OpenClaw-style first-run experience.
// Provider/model/key + optional workspace + optional sample skill
// + reachability ping. Each step can be skipped (Enter on prompt /
// "n" on yes-no). Re-runnable safely: existing state is reused, not
// clobbered, except when the user explicitly opts in.
//
// `lazyclaw setup` exposes this directly so users can re-run the
// wizard any time. The first-run code path also funnels through it
// so a fresh install sees the same flow whether they typed
// `lazyclaw` or `lazyclaw setup`.
async function cmdSetup(_sub, _positional, flags = {}) {
  await ensureRegistry();
  const accent = (s) => `\x1b[38;5;208m${s}\x1b[0m`;
  const bold   = (s) => `\x1b[1m${s}\x1b[0m`;
  const dim    = (s) => `\x1b[2m${s}\x1b[0m`;
  const ok     = (s) => `\x1b[32m${s}\x1b[0m`;
  const warn   = (s) => `\x1b[33m${s}\x1b[0m`;

  // Header.
  if (process.stdout.isTTY) process.stdout.write('\x1b[2J\x1b[H');
  _renderBanner(readVersionFromRepo()).forEach((l) => process.stdout.write(l + '\n'));
  process.stdout.write('\n');
  process.stdout.write(`  ${bold('🔧 Setup wizard')}\n`);
  process.stdout.write(`  ${dim('Five short steps. Press Enter to accept the default; type "skip" or "n" to bypass an optional step.')}\n\n`);

  const cfg = readConfig();
  const cfgDir = path.dirname(configPath());

  // ── Step 1: Provider + model (mandatory) ────────────────────
  process.stdout.write(`  ${accent('Step 1/5 ·')} ${bold('Pick a provider + model')}\n`);
  process.stdout.write(`  ${dim('Opens the arrow-key picker. The list leads with gemini / openai / claude-cli — pick the one you have an account or login for.')}\n\n`);
  await _quickPrompt('  ▶ press Enter to open the picker ');
  try {
    await cmdOnboard({ pick: true });
  } catch (e) {
    process.stderr.write(`onboard error: ${e?.message || e}\n`);
    process.exit(1);
  }
  // Re-read config after onboard wrote it. If the user aborted with
  // no provider set, bail out early — the rest of the wizard depends
  // on a provider being configured.
  const cfgAfterOnboard = readConfig();
  if (!cfgAfterOnboard.provider) {
    process.stdout.write(`\n  ${warn('Setup aborted — no provider configured. Run `lazyclaw setup` again when ready.')}\n\n`);
    process.exit(0);
  }
  process.stdout.write(`\n  ${ok('✓ provider:')} ${cfgAfterOnboard.provider}  ${dim('model:')} ${cfgAfterOnboard.model || '(default)'}\n\n`);

  // ── Step 2: Optional workspace ──────────────────────────────
  process.stdout.write(`  ${accent('Step 2/5 ·')} ${bold('Initialise a workspace?')} ${dim('(optional)')}\n`);
  process.stdout.write(`  ${dim('A workspace is a folder of AGENTS.md / SOUL.md / TOOLS.md prompt files that auto-inject into chat / agent. Skip if you don\'t need project-specific personas yet.')}\n\n`);
  const wsName = (await _quickPrompt('  workspace name (Enter to skip): ')).trim();
  if (wsName && /^[A-Za-z0-9_.-]+$/.test(wsName)) {
    try {
      const ws = await import('./workspace.mjs');
      const dir = ws.initWorkspace(cfgDir, wsName);
      process.stdout.write(`  ${ok('✓ workspace created:')} ${dir}\n`);
      process.stdout.write(`  ${dim('Edit AGENTS.md / SOUL.md / TOOLS.md any time. Use with: lazyclaw chat --workspace ' + wsName)}\n\n`);
    } catch (e) {
      process.stdout.write(`  ${warn('skipped:')} ${e?.message || e}\n\n`);
    }
  } else if (wsName) {
    process.stdout.write(`  ${warn('skipped:')} workspace name must match [A-Za-z0-9_.-]+\n\n`);
  } else {
    process.stdout.write(`  ${dim('— skipped —')}\n\n`);
  }

  // ── Step 3: Optional skill bundle install ───────────────────
  process.stdout.write(`  ${accent('Step 3/5 ·')} ${bold('Install a skill bundle from GitHub?')} ${dim('(optional)')}\n`);
  process.stdout.write(`  ${dim('Format: <user>/<repo>[@<ref>]. Skills are .md prompt fragments that compose into the system prompt via --skill.')}\n\n`);
  const skillSpec = (await _quickPrompt('  github spec (Enter to skip): ')).trim();
  if (skillSpec) {
    try {
      const inst = await import('./skills_install.mjs');
      const r = await inst.installFromGithub(skillSpec, cfgDir, { force: false });
      process.stdout.write(`  ${ok('✓ installed')} ${r.installed.length} ${dim('skill(s) from')} ${skillSpec}\n`);
      r.installed.forEach((s) => process.stdout.write(`    · ${s.name} ${dim(`(${s.bytes} bytes)`)}\n`));
      if (r.skipped.length) {
        process.stdout.write(`  ${dim('skipped (already installed):')} ${r.skipped.map((s) => s.name).join(', ')}\n`);
      }
      process.stdout.write('\n');
    } catch (e) {
      process.stdout.write(`  ${warn('skipped:')} ${e?.message || e}\n\n`);
    }
  } else {
    process.stdout.write(`  ${dim('— skipped —')}\n\n`);
  }

  // ── Step 4: Optional outbound webhook ───────────────────────
  process.stdout.write(`  ${accent('Step 4/5 ·')} ${bold('Add an outbound webhook?')} ${dim('(optional)')}\n`);
  process.stdout.write(`  ${dim('Use with: lazyclaw message send <name> <text>. Slack / Discord Incoming Webhook URLs work as-is.')}\n\n`);
  const hookName = (await _quickPrompt('  webhook name (Enter to skip): ')).trim();
  if (hookName) {
    const hookUrl = (await _quickPrompt('  webhook URL: ')).trim();
    if (!hookUrl) {
      process.stdout.write(`  ${warn('skipped:')} URL required\n\n`);
    } else {
      try {
        const cf = await import('./config_features.mjs');
        const fresh = readConfig();
        cf.messageAdd(fresh, hookName, hookUrl);
        writeConfig(fresh);
        process.stdout.write(`  ${ok('✓ webhook saved:')} ${hookName}\n\n`);
      } catch (e) {
        process.stdout.write(`  ${warn('skipped:')} ${e?.message || e}\n\n`);
      }
    }
  } else {
    process.stdout.write(`  ${dim('— skipped —')}\n\n`);
  }

  // ── Step 5: Reachability check ──────────────────────────────
  process.stdout.write(`  ${accent('Step 5/5 ·')} ${bold('Verify the picked provider responds')}\n`);
  process.stdout.write(`  ${dim('Sends a 1-token "ping" via `lazyclaw providers test`. Confirms your key / subscription / local daemon is wired up.')}\n\n`);
  const wantPing = !flags['skip-test'] && (await _quickPrompt('  test now? [Y/n] ')).trim().toLowerCase() !== 'n';
  if (wantPing) {
    try {
      // Reuse the existing providers-test path so behaviour matches
      // a manual `lazyclaw providers test`.
      await cmdProviders('test', [cfgAfterOnboard.provider], {});
    } catch (e) {
      process.stdout.write(`  ${warn('test errored:')} ${e?.message || e}\n`);
      process.stdout.write(`  ${dim('Setup still completed; you can retry with:')} lazyclaw providers test ${cfgAfterOnboard.provider}\n`);
    }
  } else {
    process.stdout.write(`  ${dim('— skipped —')}\n`);
  }

  // ── Wrap up ─────────────────────────────────────────────────
  process.stdout.write('\n');
  process.stdout.write(`  ${ok(bold('🎉 Setup complete.'))}\n`);
  process.stdout.write(`  ${dim('Run')} ${bold('lazyclaw')} ${dim('any time to open the menu, or jump in directly:')}\n`);
  process.stdout.write(`    ${dim('•')} lazyclaw chat                ${dim('— REPL with the configured provider')}\n`);
  process.stdout.write(`    ${dim('•')} lazyclaw agent "..."          ${dim('— one-shot prompt')}\n`);
  process.stdout.write(`    ${dim('•')} lazyclaw doctor              ${dim('— diagnostic JSON')}\n`);
  process.stdout.write(`    ${dim('•')} lazyclaw setup               ${dim('— re-run this wizard any time')}\n\n`);
}

// First-run welcome panel + delegated onboard. Drawn once before the
// main launcher menu when the config has no provider yet. Walks the
// user through the same arrow-key picker that `lazyclaw onboard`
// uses; on success the launcher continues, on cancel the launcher
// exits politely instead of dropping into a menu where every option
// would error.
async function _runFirstTimeOnboard() {
  const accent = (s) => `\x1b[38;5;208m${s}\x1b[0m`;
  const dim    = (s) => `\x1b[2m${s}\x1b[0m`;
  const bold   = (s) => `\x1b[1m${s}\x1b[0m`;
  process.stdout.write('\x1b[2J\x1b[H');
  _renderBanner(readVersionFromRepo()).forEach((l) => process.stdout.write(l + '\n'));
  process.stdout.write('\n');
  process.stdout.write(`  ${bold('👋 Welcome — first-time setup')}\n\n`);
  process.stdout.write(`  ${dim('No provider configured yet at')} ${configPath()}\n`);
  process.stdout.write(`  ${dim('Pick a provider + model below; LazyClaw stores it in ~/.lazyclaw/config.json.')}\n\n`);
  process.stdout.write(`  ${dim('Quick rule of thumb:')}\n`);
  process.stdout.write(`  ${dim('  · gemini / openai / anthropic — need an API key (sk-... / paste during setup)')}\n`);
  process.stdout.write(`  ${dim('  · claude-cli / ollama          — keyless (use your existing Claude Code login or local Ollama)')}\n`);
  process.stdout.write(`  ${dim('  · mock                         — offline echo, only useful for testing')}\n\n`);
  process.stdout.write(`  ${dim('Press Enter to open the picker · Ctrl+C to abort.')}\n`);
  await _quickPrompt('  ▶ ');
  // Delegate to the real onboard flow with --pick so the picker UI
  // fires regardless of how this entry point was reached. cmdOnboard
  // owns config writing.
  try {
    await cmdOnboard({ pick: true });
  } catch (e) {
    process.stderr.write(`onboard error: ${e?.message || e}\n`);
  }
  process.stdout.write('\n');
}

async function cmdLauncher() {
  await ensureRegistry();
  let cfg = readConfig();
  // First-run guard: a fresh install has no `provider` set, so any
  // menu pick that calls a provider (Chat / Agent / Doctor / etc.)
  // would error halfway through with a confusing "missing api key"
  // or "unknown provider". Detect that state up front and walk the
  // user through onboard before showing the menu — once they've
  // picked, re-read the config and continue normally.
  if (!cfg.provider) {
    // Delegate to the full setup wizard rather than the bare onboard
    // picker — first-time users benefit from the workspace / skill /
    // ping steps too. cmdSetup exits the process on abort, so the
    // re-read below only fires when the wizard completed successfully.
    await cmdSetup(undefined, [], {});
    cfg = readConfig();
    if (!cfg.provider) {
      process.stdout.write('\n  Setup not completed — exiting.\n  Run `lazyclaw setup` when ready, then try `lazyclaw` again.\n\n');
      process.exit(0);
    }
  }
  const provider = cfg.provider;
  const model = cfg.model || '(default)';
  const items = [
    { id: 'chat',      label: 'Chat',          desc: 'interactive REPL with the configured provider', argv: ['chat'] },
    { id: 'agent',     label: 'Agent',         desc: 'one-shot prompt — read text and exit',           argv: ['agent'], promptForBody: true },
    { id: 'onboard',   label: 'Onboard',       desc: 'pick provider / model / api-key',                argv: ['onboard'] },
    { id: 'workspace', label: 'Workspace',     desc: 'AGENTS.md / SOUL.md / TOOLS.md prompt bundles',  argv: ['workspace', 'list'] },
    { id: 'browse',    label: 'Browse',        desc: 'fetch a URL → markdown',                         argv: ['browse'], promptForUrl: true },
    { id: 'skills',    label: 'Skills',        desc: 'installed skill bundles',                        argv: ['skills', 'list'] },
    { id: 'sessions',  label: 'Sessions',      desc: 'persisted chat sessions',                        argv: ['sessions', 'list'] },
    { id: 'providers', label: 'Providers',     desc: 'registered providers + reachability',            argv: ['providers', 'list'] },
    { id: 'cron',      label: 'Cron',          desc: 'recurring agent runs (launchd / crontab)',       argv: ['cron', 'list'] },
    { id: 'doctor',    label: 'Doctor',        desc: 'diagnostic — config, providers, workflows',     argv: ['doctor'] },
    { id: 'status',    label: 'Status',        desc: 'current provider / model / masked key',          argv: ['status'] },
    { id: 'help',      label: 'Help',          desc: 'one-line summary of every subcommand',           argv: ['help'] },
    { id: 'quit',      label: 'Quit',          desc: 'exit without doing anything',                    argv: null },
  ];

  const readline = await import('node:readline');
  readline.emitKeypressEvents(process.stdin);
  if (process.stdin.setRawMode) process.stdin.setRawMode(true);
  let idx = 0;

  // Pretty header — same accent palette as _printChatBanner so
  // returning users recognise it.
  const accent = (s) => `\x1b[38;5;208m${s}\x1b[0m`;
  const dim    = (s) => `\x1b[2m${s}\x1b[0m`;
  const bold   = (s) => `\x1b[1m${s}\x1b[0m`;
  const ok     = (s) => `\x1b[32m${s}\x1b[0m`;
  const warn   = (s) => `\x1b[33m${s}\x1b[0m`;

  const draw = () => {
    process.stdout.write('\x1b[?25l\x1b[2J\x1b[H'); // hide cursor + clear
    _renderBanner(readVersionFromRepo()).forEach((l) => process.stdout.write(l + '\n'));
    process.stdout.write('\n');
    const provDisplay = provider === '(unset — pick during onboard)'
      ? warn(provider)
      : ok(provider);
    process.stdout.write(`  ${dim('provider ·')} ${provDisplay}\n`);
    process.stdout.write(`  ${dim('model    ·')} ${ok(model)}\n`);
    process.stdout.write(`  ${dim('config   ·')} ${dim(configPath())}\n`);
    process.stdout.write('\n');
    process.stdout.write(`  ${dim('↑/↓ to move · Enter to select · q or Esc to quit')}\n\n`);

    // Trim list to terminal height so the menu still fits when
    // someone shrinks the window or runs in a small split pane.
    const rowsAvail = Math.max(items.length, (process.stdout.rows || 30) - 14);
    const fromIdx = Math.max(0, Math.min(items.length - rowsAvail, idx - Math.floor(rowsAvail / 2)));
    const toIdx = Math.min(items.length, fromIdx + rowsAvail);
    for (let i = fromIdx; i < toIdx; i++) {
      const it = items[i];
      const marker = i === idx ? accent('❯ ') : '  ';
      const lbl = i === idx ? bold(it.label.padEnd(11)) : it.label.padEnd(11);
      process.stdout.write(`${marker}${lbl}  ${dim(it.desc)}\n`);
    }
    process.stdout.write('\n');
  };

  // Tear down raw mode + listeners cleanly so the next subcommand
  // starts with a sane stdin (otherwise `chat` after launcher inherits
  // the launcher's raw mode and behaves weirdly).
  const teardown = (onKey) => {
    if (onKey) process.stdin.off('keypress', onKey);
    if (process.stdin.setRawMode) process.stdin.setRawMode(false);
    process.stdout.write('\x1b[?25h'); // show cursor
    process.stdout.write('\x1b[2J\x1b[H'); // clear screen
  };

  draw();
  const picked = await new Promise((resolve) => {
    const onKey = (_str, key) => {
      if (!key) return;
      if (key.name === 'up')        { idx = (idx - 1 + items.length) % items.length; draw(); }
      else if (key.name === 'down') { idx = (idx + 1) % items.length; draw(); }
      else if (key.name === 'home') { idx = 0; draw(); }
      else if (key.name === 'end')  { idx = items.length - 1; draw(); }
      else if (key.name === 'pageup')   { idx = Math.max(0, idx - 5); draw(); }
      else if (key.name === 'pagedown') { idx = Math.min(items.length - 1, idx + 5); draw(); }
      else if (key.name === 'return')   { teardown(onKey); resolve(items[idx]); }
      else if (key.ctrl && key.name === 'c') { teardown(onKey); resolve({ id: 'quit', argv: null }); }
      else if (key.name === 'escape' || key.name === 'q') { teardown(onKey); resolve({ id: 'quit', argv: null }); }
    };
    process.stdin.on('keypress', onKey);
  });

  if (!picked || !picked.argv) {
    process.exit(0);
  }
  // Two surfaces need a follow-up question before they can run:
  // - `agent`: needs a prompt body
  // - `browse`: needs a URL
  // Ask via a simple readline prompt so the launcher stays
  // self-contained instead of forwarding into a half-typed argv.
  if (picked.promptForBody) {
    const body = await _quickPrompt('prompt: ');
    if (!body) process.exit(0);
    picked.argv = ['agent', body];
  } else if (picked.promptForUrl) {
    const url = await _quickPrompt('url: ');
    if (!url) process.exit(0);
    picked.argv = ['browse', url];
  }
  // Replace argv and re-enter main(). The chosen subcommand sees
  // the same parser surface as if the user had typed it directly.
  process.argv = [process.argv[0], process.argv[1], ...picked.argv];
  await main();
}

async function _quickPrompt(label) {
  const readline = await import('node:readline');
  process.stdout.write('\n');
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const ans = await new Promise((resolve) => rl.question(label, resolve));
  rl.close();
  return ans.trim();
}

async function main() {
  const argv = process.argv.slice(2);
  const cmd = argv[0];
  const rest = parseArgs(argv.slice(1));
  // No subcommand at all: drop into the interactive launcher when we
  // can render one (TTY both ways), otherwise fall through to the
  // historical "Usage: ..." line so scripts / piped callers stay
  // predictable.
  if (cmd === undefined) {
    if (process.stdin.isTTY && process.stdout.isTTY) {
      await cmdLauncher();
      return;
    }
    console.error('Usage: lazyclaw <' + SUBCOMMANDS.join('|') + '> ...');
    console.error('Run `lazyclaw help` for a one-line summary of each subcommand.');
    console.error('Tip: launch in an interactive terminal to get the arrow-key menu.');
    process.exit(2);
  }
  switch (cmd) {
    case 'run': {
      const [sessionId, file] = rest.positional;
      if (!sessionId || !file) { console.error('Usage: lazyclaw run <session-id> <workflow.mjs> [--parallel | --parallel-persistent] [--concurrency <N>]'); process.exit(2); }
      // --concurrency caps in-flight nodes within a single level for
      // both --parallel and --parallel-persistent. Sequential mode
      // ignores it (only one node runs at a time anyway).
      const concurrency = rest.flags.concurrency !== undefined
        ? Math.max(0, parseInt(rest.flags.concurrency, 10) || 0)
        : undefined;
      await cmdRun(sessionId, file, {
        dir: rest.flags.dir,
        parallel: !!rest.flags.parallel,
        'parallel-persistent': !!rest.flags['parallel-persistent'],
        concurrency,
      });
      break;
    }
    case 'resume': {
      const [sessionId, file] = rest.positional;
      if (!sessionId || !file) { console.error('Usage: lazyclaw resume <session-id> <workflow.mjs> [--parallel-persistent] [--concurrency <N>]'); process.exit(2); }
      const concurrency = rest.flags.concurrency !== undefined
        ? Math.max(0, parseInt(rest.flags.concurrency, 10) || 0)
        : undefined;
      await cmdResume(sessionId, file, {
        dir: rest.flags.dir,
        'parallel-persistent': !!rest.flags['parallel-persistent'],
        concurrency,
      });
      break;
    }
    case 'inspect': {
      // No-arg form lists every persisted session in the state dir.
      // Pass the empty positional through; cmdInspect's list mode
      // handles it.
      const [sessionId] = rest.positional;
      await cmdInspect(sessionId, {
        dir: rest.flags.dir,
        status: rest.flags.status,
        summary: !!rest.flags.summary,
        filter: rest.flags.filter,
        limit: rest.flags.limit,
        node: rest.flags.node,
        criticalPath: rest.flags['critical-path'],
        slowest: rest.flags.slowest,
        aggregate: !!rest.flags.aggregate,
      });
      break;
    }
    case 'clear': {
      const [sessionId] = rest.positional;
      if (!sessionId) { console.error('Usage: lazyclaw clear <session-id> [--dir <state-dir>]'); process.exit(2); }
      await cmdClear(sessionId, { dir: rest.flags.dir });
      break;
    }
    case 'validate': {
      const [file] = rest.positional;
      await cmdValidate(file);
      break;
    }
    case 'graph': {
      const [file] = rest.positional;
      await cmdGraph(file, {
        lr: !!rest.flags.lr,
        state: rest.flags.state,
        dir: rest.flags.dir,
      });
      break;
    }
    case 'config': {
      const sub = rest.positional[0];
      if (sub === 'set') {
        const [, key, ...valueParts] = rest.positional;
        cmdConfigSet(key, valueParts.join(' '));
      } else if (sub === 'get') {
        cmdConfigGet(rest.positional[1]);
      } else if (sub === 'list') {
        cmdConfigGet(undefined);
      } else if (sub === 'delete' || sub === 'unset') {
        const key = rest.positional[1];
        if (!key) { console.error('Usage: lazyclaw config delete <key>'); process.exit(2); }
        const cfg = readConfig();
        const had = Object.prototype.hasOwnProperty.call(cfg, key);
        delete cfg[key];
        writeConfig(cfg);
        console.log(JSON.stringify({ ok: true, key, removed: had }));
      } else if (sub === 'path') {
        // Useful for shell pipelines: `cat $(lazyclaw config path)`.
        console.log(configPath());
      } else if (sub === 'edit') {
        await cmdConfigEdit();
      } else if (sub === 'validate') {
        await cmdConfigValidate();
      } else {
        console.error('Usage: lazyclaw config set|get|list|delete|path|edit|validate <key> [value]'); process.exit(2);
      }
      break;
    }
    case 'chat': {
      await cmdChat(rest.flags);
      break;
    }
    case 'sessions': {
      const sub = rest.positional[0];
      await cmdSessions(sub, rest.positional.slice(1), rest.flags);
      break;
    }
    case 'providers': {
      const sub = rest.positional[0];
      await cmdProviders(sub, rest.positional.slice(1), rest.flags);
      break;
    }
    case 'skills': {
      const sub = rest.positional[0];
      await cmdSkills(sub, rest.positional.slice(1), rest.flags);
      break;
    }
    case 'rates': {
      const sub = rest.positional[0];
      await cmdRates(sub, rest.positional.slice(1), rest.flags);
      break;
    }
    case 'auth': {
      const sub = rest.positional[0];
      await cmdAuth(sub, rest.positional.slice(1), rest.flags);
      break;
    }
    case 'pairing': {
      const sub = rest.positional[0];
      await cmdPairing(sub, rest.positional.slice(1), rest.flags);
      break;
    }
    case 'nodes': {
      const sub = rest.positional[0];
      await cmdNodes(sub, rest.positional.slice(1), rest.flags);
      break;
    }
    case 'message': {
      const sub = rest.positional[0];
      await cmdMessage(sub, rest.positional.slice(1), rest.flags);
      break;
    }
    case 'workspace': {
      const sub = rest.positional[0];
      await cmdWorkspace(sub, rest.positional.slice(1), rest.flags);
      break;
    }
    case 'browse': {
      await cmdBrowse(rest.positional[0], rest.flags);
      break;
    }
    case 'cron': {
      const sub = rest.positional[0];
      await cmdCron(sub, rest.positional.slice(1), rest.flags);
      break;
    }
    case 'setup': {
      await cmdSetup(undefined, rest.positional, rest.flags);
      break;
    }
    case 'dashboard': {
      await cmdDashboard(rest.flags);
      break;
    }
    case 'daemon': {
      await cmdDaemon(rest.flags);
      break;
    }
    case 'agent': {
      const prompt = rest.positional[0];
      await cmdAgent(prompt, rest.flags);
      break;
    }
    case 'doctor': {
      await cmdDoctor();
      break;
    }
    case 'status': {
      await cmdStatus();
      break;
    }
    case 'onboard': {
      await cmdOnboard(rest.flags);
      break;
    }
    case 'version':
    case '--version':
    case '-v': {
      await cmdVersion();
      break;
    }
    case 'completion': {
      await cmdCompletion(rest.positional[0]);
      break;
    }
    case 'export': {
      await cmdExport(rest.flags);
      break;
    }
    case 'import': {
      await cmdImport(rest.flags);
      break;
    }
    case 'help':
    case '--help':
    case '-h': {
      cmdHelp(rest.positional[0]);
      break;
    }
    default:
      console.error('Usage: lazyclaw <' + SUBCOMMANDS.join('|') + '> ...');
      console.error('Run `lazyclaw help` for a one-line summary of each subcommand.');
      process.exit(2);
  }
}

main().catch(e => { console.error(e?.stack || e?.message || String(e)); process.exit(1); });
