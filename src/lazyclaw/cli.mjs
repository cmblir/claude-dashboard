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
//   3. customProviders[<provider>].apiKey (custom OpenAI-compat entries)
//   4. PROVIDER_INFO[<provider>].envKey / altEnvKeys env var (built-in
//      OpenAI-compat: nim → NVIDIA_API_KEY, openrouter → OPENROUTER_API_KEY, …)
//   5. legacy single `cfg["api-key"]` (pre-v3.93 configs)
function _resolveAuthKey(cfg, provider) {
  const arr = (cfg.authProfiles || {})[provider] || [];
  const active = (cfg.authActiveProfile || {})[provider];
  const hit = arr.find((p) => p && p.label === active) || arr[0];
  if (hit?.key) return hit.key;
  const custom = Array.isArray(cfg.customProviders)
    ? cfg.customProviders.find((p) => p && p.name === provider)
    : null;
  if (custom?.apiKey) return custom.apiKey;
  // Built-in OpenAI-compat env var fallback. Skipped silently when the
  // registry module isn't loaded yet (every chat / agent path calls
  // ensureRegistry() before _resolveAuthKey, so this is just defence-in-depth).
  if (_registryMod && typeof _registryMod.resolveBuiltinEnvKey === 'function') {
    const envHit = _registryMod.resolveBuiltinEnvKey(provider);
    if (envHit) return envHit;
  }
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
  // Re-run registration on every call so config changes within the same
  // process (e.g. setup wizard adding a custom endpoint mid-session) take
  // effect for the next chat / agent / picker invocation. registerCustom-
  // Providers is idempotent — re-registering the same name is a no-op.
  try {
    if (typeof _registryMod.registerCustomProviders === 'function') {
      _registryMod.registerCustomProviders(readConfig());
    }
  } catch { /* never let a malformed cfg.customProviders block startup */ }
  // Wire the orchestrator's live cfg + auth-key resolver. We do this on
  // every ensureRegistry() call (cheap — just replaces the closure) so a
  // mid-session config edit (custom provider added, env var exported)
  // takes effect on the next orchestrator turn without a restart.
  try {
    if (typeof _registryMod.registerOrchestrator === 'function') {
      _registryMod.registerOrchestrator({
        cfgGetter: readConfig,
        keyResolver: _resolveAuthKey,
      });
    }
  } catch { /* defensive */ }
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
  // v3.99.22 — multi-agent orchestrator config
  'orchestrator',
];

const SUBCOMMAND_SUBS = {
  config:    ['get', 'set', 'list', 'delete', 'unset', 'path', 'edit', 'validate'],
  sessions:  ['list', 'show', 'clear', 'export', 'search'],
  skills:    ['list', 'show', 'install', 'remove', 'search'],
  providers: ['list', 'info', 'test', 'add', 'remove', 'models'],
  rates:     ['list', 'set', 'delete', 'shape', 'validate', 'copy'],
  completion: ['bash', 'zsh'],
  auth:      ['list', 'add', 'remove', 'use', 'rotate'],
  pairing:   ['list', 'add', 'remove'],
  nodes:     ['list', 'register', 'remove'],
  message:   ['list', 'add', 'remove', 'send'],
  workspace: ['list', 'init', 'show', 'remove', 'path'],
  cron:      ['list', 'add', 'remove', 'show', 'sync', 'run'],
  orchestrator: ['status', 'set-planner', 'workers', 'set-max-subtasks', 'clear'],
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
  providers:  'Inspect / register providers (list|info|test|add|remove|models)',
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
  orchestrator: 'Multi-agent dispatch — planner decomposes, workers run, planner synthesises',
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
  providers: 'Usage: lazyclaw providers <list [--filter <substr>] [--limit <N>] | info <name> | test <name> [--model X] [--prompt T] | test [--all] [--prompt T] | add <name> --base-url <url> [--api-key <k>] [--default-model <id>] [--no-probe] | remove <name> | models <name> [--filter <substr>]>\n  list   — registered providers (--filter case-insensitive name substring; --limit caps post-filter count).\n  info   — static metadata: requiresApiKey, defaultModel, suggestedModels, endpoint.\n  test   — send a 1-token "ping" through the provider and report ok/error + duration.\n           Useful after configuring an API key to verify it works before relying on it.\n           No name OR --all: tests every registered provider in parallel; exits 0 only when ALL pass.\n  add    — register a custom OpenAI-compatible endpoint (NIM / OpenRouter / Together / Groq / vLLM / LM Studio / …).\n           Probes /v1/models on success unless --no-probe is set; persists to cfg.customProviders[].\n  remove — drop a custom provider entry from cfg.customProviders[].\n  models — fetch + print the live model catalogue from <provider>/v1/models (works for openai / ollama / custom).',
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
  orchestrator: 'Usage: lazyclaw orchestrator <status | set-planner <provider[:model]> | workers add <spec> | workers remove <spec> | workers set <spec,spec,...> | workers clear | set-max-subtasks <N> | clear>\n  Read/write cfg.orchestrator without editing config.json by hand.\n  status               — print {planner, workers, maxSubtasks} as JSON; lists registered providers for reference.\n  set-planner          — replace the planner spec ("provider" or "provider:model"). "orchestrator" itself is rejected (self-recursion).\n  workers add          — append a worker (idempotent — duplicates skipped).\n  workers remove       — drop a worker by exact match. Idempotent.\n  workers set          — replace the whole list (comma-separated specs).\n  workers clear        — empty the workers list.\n  set-max-subtasks <N> — cap subtasks per request, clamped 1..10 (default 5).\n  clear                — delete the cfg.orchestrator block entirely.\n  Pair with: `lazyclaw config set provider orchestrator` to route chats through it.',
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
  // Returns `{ dispose, suspend, resume }`. Dispose detaches the
  // keypress + rl 'line' listeners (failure to do so leaks the
  // event-loop ref, which is exactly the slow-exit bug v3.92
  // fixed). Suspend / resume gate the keypress handler so the
  // streaming chat output isn't interleaved with `\x1b[s\x1b[K\x1b[u`
  // ghost-render escapes — that interleaving is what surfaces as
  // visible gaps between Korean characters in long replies.
  const noop = () => {};
  if (!process.stdout.isTTY) return { dispose: noop, suspend: noop, resume: noop };
  const cmds = SLASH_COMMANDS.map((c) => c.cmd);
  let lastGhost = '';
  let suspended = false;
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
    // While a streaming response is being printed, do nothing —
    // any ANSI cursor save / restore we emit would tear the wide-
    // character (CJK) output apart on the visible terminal.
    if (suspended) return;
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
  const dispose = () => {
    try { process.stdin.removeListener('keypress', onKeypress); } catch (_) {}
    try { rl.removeListener('line', onLine); } catch (_) {}
    // Wipe any leftover ghost on screen so the user's terminal doesn't
    // keep a dim suffix after we exit.
    try { process.stdout.write('\x1b[s\x1b[K\x1b[u'); } catch (_) {}
  };
  return {
    dispose,
    suspend: () => {
      suspended = true;
      // Wipe any half-rendered ghost before streaming starts so the
      // first chunk lands at the same column as the prompt.
      try { process.stdout.write('\x1b[s\x1b[K\x1b[u'); } catch (_) {}
    },
    resume: () => { suspended = false; },
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
// v3.99.26 — canonical Big ASCII mascot from the v0.1 Claude Design
// handoff bundle. 12 rows. Claude's square body + lobster pincers (◂▸)
// + helmet (╔═╗) + asterisk-star tail. Sleepy slit eyes (│ │) by
// default — name says lazyclaw.
//
// State variants live in _renderMascot(state). Big variant = banner.
// Inline 3-row Tiny variant lives in _renderMascotTiny(state).
const _MASCOT_BIG = {
  idle: [
    '  ◂▸        ◂▸  ',
    '  │           │  ',
    '  │           │  ',
    '╔═════════════╗',
    '║             ║',
    '╚═════════════╝',
    '┌─────────────┐',
    '│  │     │  │',
    '┤  │     │  ├',
    '└─────────────┘',
    '   ┃        ┃   ',
    '   ┃        ┃   ',
  ],
  working: [
    '  ◂▸        ◂▸  ',
    '  │  ···      │  ',
    '  │           │  ',
    '╔═════════════╗',
    '║     *       ║',
    '╚═════════════╝',
    '┌─────────────┐',
    '│  ·     ·  │',
    '┤           ├',
    '└─────────────┘',
    '   ┃        ┃   ',
    '   ┃        ┃   ',
  ],
  done: [
    '✦ ◂▸        ◂▸ ✦',
    '  │           │  ',
    '  │           │  ',
    '╔═════════════╗',
    '║             ║',
    '╚═════════════╝',
    '┌─────────────┐',
    '│  ^     ^  │',
    '┤    ‿‿‿    ├',
    '└─────────────┘',
    '   ┃        ┃   ',
    '   ┃        ┃   ',
  ],
  error: [
    '   ▾        ▾   ',
    '  │           │  ',
    '  │           │  ',
    '╔═════════════╗',
    '║     ~       ║',
    '╚═════════════╝',
    '┌─────────────┐',
    '│  ×     ×  │',
    '┤    ⏜      ├',
    '└─────────────┘',
    '   ┃        ┃   ',
    '   ┃        ┃   ',
  ],
};
const _MASCOT_TINY = {
  idle:    '◂▸  ◂▸\n[│  │]\n ┃  ┃ ',
  working: '◂▸  ◂▸\n[·  ·] ···\n ┃  ┃ ',
  done:    '◂▸  ◂▸\n[^  ^] ✓\n ┃  ┃ ',
  error:   '▾   ▾ \n[×  ×] !\n ┃  ┃ ',
};

// Ink helpers. State picks a primary colour; the banner caller layers
// a secondary "wordmark" right column.
function _mascotInkers(state) {
  const helmet = (s) => `\x1b[38;2;195;61;42m${s}\x1b[0m`;
  const helmetDim = (s) => `\x1b[38;2;122;31;21m${s}\x1b[0m`;
  const star = (s) => `\x1b[38;2;217;119;87m${s}\x1b[0m`;
  const ok = (s) => `\x1b[38;2;111;185;143m${s}\x1b[0m`;
  const err = (s) => `\x1b[38;2;230;57;70m${s}\x1b[0m`;
  if (state === 'done') return (s) => ok(s);
  if (state === 'error') return (s) => err(s);
  if (state === 'working') return (s) => helmet(s);
  return (s) => helmet(s);
}

function _renderMascot(state) {
  const rows = _MASCOT_BIG[state] || _MASCOT_BIG.idle;
  const ink = _mascotInkers(state);
  return rows.map((r) => ink(r));
}

// Tiny inline mascot — picked up by chat/agent helpers when they want
// to flash a one-line status without re-rendering the whole banner.
// Returns a string; callers add their own newline.
function _renderMascotTiny(state) {
  const ink = _mascotInkers(state);
  return ink((_MASCOT_TINY[state] || _MASCOT_TINY.idle));
}

function _renderBanner(version) {
  const ink = (s) => `\x1b[38;2;241;234;217m${s}\x1b[0m`;
  const dim = (s) => `\x1b[2m${s}\x1b[0m`;
  const v = String(version || '?.?.?');
  const left = _renderMascot('idle');
  const right = [
    '',
    '',
    '',
    `   ${ink('lazyclaw')}  ${dim('v' + v)}`,
    `   ${dim('a sleepy 8-bit')}`,
    `   ${dim('terminal assistant')}`,
    '',
    '',
    '',
    '',
    '',
    '',
  ];
  return left.map((l, i) => '  ' + l + (right[i] || ''));
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
async function _arrowMenu({ title, subtitle, footer, items, defaultIdx = 0, searchable = false }) {
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
  // A previous `readline.createInterface(...).close()` (e.g. from
  // `_quickPrompt`) leaves stdin paused — the keypress listener we
  // attach below would never fire and the menu would appear frozen
  // instead of responding to arrow keys. Resume + ref defensively
  // before drawing so the picker always receives the first keypress.
  process.stdin.resume();
  if (process.stdin.ref) process.stdin.ref();
  const accent = (s) => `\x1b[38;5;208m${s}\x1b[0m`;
  const dim    = (s) => `\x1b[2m${s}\x1b[0m`;
  const bold   = (s) => `\x1b[1m${s}\x1b[0m`;

  // Typeahead state. `query` accumulates printable chars when searchable
  // is on; the visible item slice is recomputed on every keystroke. We
  // keep `defaultIdx` semantics by mapping it to the unfiltered list and
  // tracking selection inside the filtered view via the item identity.
  let query = '';
  const matchScore = (it, q) => {
    if (!q) return 0;
    const hay = `${it.label || ''}  ${it.desc || ''}  ${it.id || ''}`.toLowerCase();
    const needle = q.toLowerCase();
    if (hay.includes(needle)) return hay.indexOf(needle) === 0 ? 2 : 1;
    // simple subsequence fallback so "g4o" matches "gpt-4o".
    let i = 0; let matched = 0;
    for (const ch of hay) {
      if (ch === needle[matched]) { matched++; if (matched === needle.length) break; }
      i++;
    }
    return matched === needle.length ? 0.5 : 0;
  };
  const filterItems = () => {
    if (!searchable || !query) return items.slice();
    const scored = items
      .map((it) => ({ it, s: matchScore(it, query) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s);
    return scored.map((x) => x.it);
  };
  let view = filterItems();
  let idx = Math.max(0, Math.min(view.length - 1, defaultIdx));
  if (idx < 0) idx = 0;

  const draw = () => {
    process.stdout.write('\x1b[?25l\x1b[2J\x1b[H');
    process.stdout.write(accent(title) + '\n');
    if (subtitle) process.stdout.write(dim(subtitle) + '\n');
    const help = searchable
      ? '↑/↓ to move · Enter to confirm · type to search · Esc to back · Ctrl+U to clear · q to quit'
      : '↑/↓ to move · Enter to confirm · Esc to back · q to quit';
    process.stdout.write(dim(help) + '\n');
    if (searchable) {
      const q = query ? bold(query) : dim('(type to filter)');
      process.stdout.write(dim('  search: ') + q + dim(`   ${view.length}/${items.length} match`) + '\n\n');
    } else {
      process.stdout.write('\n');
    }
    if (view.length === 0) {
      process.stdout.write('  ' + dim('(no matches — backspace or Ctrl+U to clear the filter)') + '\n');
      if (footer) process.stdout.write('\n' + dim(footer) + '\n');
      return;
    }
    const headerLines = subtitle ? 4 : 3;
    const rows = Math.max(6, (process.stdout.rows || 24) - (headerLines + (searchable ? 3 : 4)));
    let from = Math.max(0, idx - Math.floor(rows / 2));
    if (from + rows > view.length) from = Math.max(0, view.length - rows);
    const to = Math.min(view.length, from + rows);
    // Pre-compute label width so descriptions line up across rows.
    const labelW = view.reduce((w, it) => Math.max(w, (it.label || '').length), 12);
    for (let i = from; i < to; i++) {
      const it = view[i];
      const marker = i === idx ? accent('❯ ') : '  ';
      const lbl = (it.label || '').padEnd(labelW);
      const lblOut = i === idx ? bold(lbl) : lbl;
      const desc = it.desc ? '  ' + dim(it.desc) : '';
      const tag = it.tag ? '  ' + it.tag : '';
      process.stdout.write(`${marker}${lblOut}${desc}${tag}\n`);
    }
    if (to < view.length) {
      process.stdout.write(`${dim(`  …(${view.length - to} more)`)}\n`);
    }
    if (footer) process.stdout.write('\n' + dim(footer) + '\n');
  };

  draw();
  return await new Promise((resolve) => {
    const recompute = () => {
      view = filterItems();
      if (idx >= view.length) idx = Math.max(0, view.length - 1);
      draw();
    };
    const onKey = (str, key) => {
      if (!key) return;
      if (key.name === 'up')   { if (view.length) { idx = (idx - 1 + view.length) % view.length; draw(); } }
      else if (key.name === 'down') { if (view.length) { idx = (idx + 1) % view.length; draw(); } }
      else if (key.name === 'pageup')   { idx = Math.max(0, idx - 10); draw(); }
      else if (key.name === 'pagedown') { idx = Math.min(view.length - 1, idx + 10); draw(); }
      else if (key.name === 'home') { idx = 0; draw(); }
      else if (key.name === 'end')  { idx = view.length - 1; draw(); }
      else if (key.name === 'return') {
        if (view.length === 0) return;
        cleanup();
        resolve(view[idx]);
      }
      else if (key.ctrl && key.name === 'c') { cleanup(); process.exit(130); }
      else if (key.ctrl && key.name === 'u') { if (searchable) { query = ''; recompute(); } }
      else if (key.name === 'escape') {
        if (searchable && query) { query = ''; recompute(); return; }
        cleanup(); resolve('BACK');
      }
      else if (key.name === 'backspace') {
        if (searchable && query.length > 0) { query = query.slice(0, -1); recompute(); }
      }
      else if (searchable && str && str.length === 1 && str >= ' ' && str !== '\x7f' && !key.ctrl && !key.meta) {
        // Printable char → append to filter buffer. We deliberately do not
        // intercept 'q' as a shortcut when searchable is on, because the
        // user might be typing a model id that contains 'q'. Use Esc / Ctrl+C
        // to bail out instead.
        query += str;
        recompute();
      }
      else if (!searchable && key.name === 'q') { cleanup(); resolve('CANCEL'); }
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
      .map(([id, b]) => {
        // Show member count + a few names instead of the full list — the
        // API-key family alone now has 12 vendors and joining all of them
        // produced an unreadable line.
        const preview = b.members.slice(0, 3).join(' / ');
        const more = b.members.length > 3 ? ` … (+${b.members.length - 3} more)` : '';
        return {
          id,
          label: b.label,
          desc: `${b.desc}  ·  ${preview}${more}`,
          tag: b.tag,
        };
      });
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
    const provItems = memberNames.map((name) => {
      const meta = info[name] || {};
      const isCustom = !!meta.custom;
      const isBuiltinCompat = !!meta.builtinOpenAICompat;
      // Step-2 desc used to preview four suggested model ids per provider.
      // That made the row read like "gemini · models: gemini-2.5-pro ·
      // gemini-2.5-flash · gemini-2.0-flash · gemini-2.0-flash-thinking-exp",
      // which is too dense and partly redundant — step 3 already shows the
      // full curated list. Keep the row to a vendor label + endpoint hint.
      let desc = '';
      if (isCustom) desc = `custom · ${meta.baseUrl || ''}`;
      else if (isBuiltinCompat) desc = meta.label || meta.baseUrl || '';
      else if (meta.label && meta.label !== name) desc = meta.label;
      return {
        id: name,
        label: name,
        desc,
        tag: isCustom
          ? '\x1b[38;5;213m[custom]\x1b[0m'
          : (meta.requiresApiKey ? '\x1b[38;5;245m[api key]\x1b[0m' : '\x1b[38;5;208m[no key]\x1b[0m'),
      };
    });
    // Surface a "+ Add a new custom endpoint…" entry inside the API-key
    // family. NIM, OpenRouter, vLLM, LM Studio, Together, Groq, etc. all
    // speak the OpenAI Chat-Completions wire format — this single hook
    // covers every one of them without shipping a per-vendor provider.
    if (family.id === 'api') {
      provItems.push({
        id: '__add_custom__',
        label: '+ Add a custom OpenAI-compatible endpoint…',
        desc: 'NVIDIA NIM · OpenRouter · Together · Groq · vLLM · LM Studio · …',
        tag: '\x1b[38;5;213m[new]\x1b[0m',
      });
    }
    if (memberNames.length === 1 && family.id !== 'api') {
      // Auto-advance — no point making the user pick from a single row,
      // unless we just appended the "+ Add custom" entry above.
      provider = { id: memberNames[0] };
      break;
    }
    const picked = await _arrowMenu({
      title: `LazyClaw setup — Step 2 of 3:  pick a ${family.label} provider`,
      subtitle: `Showing ${provItems.length} ${family.label.toLowerCase()} option(s). Type to filter.`,
      items: provItems,
      searchable: true,
    });
    if (picked === 'CANCEL') return null;
    if (picked === 'BACK')   { family = null; return _pickProviderInteractive(); }
    if (picked && picked.id === '__add_custom__') {
      const added = await _addCustomProviderInteractive();
      if (!added) continue; // back to provider list
      // Force the registry to pick up the new entry and recompute the
      // family bucket for the next loop iteration.
      await ensureRegistry();
      Object.assign(families, _providerFamilies());
      provider = { id: added.name };
      break;
    }
    provider = picked;
  }

  // ── Step 3 — model (or, for composite providers, a config wizard) ───
  // The orchestrator (and any future composite provider) has no model
  // of its own — it dispatches to other providers. Step 3 routes
  // through a custom wizard instead of the standard model picker.
  const providerMeta = (_registryMod.PROVIDER_INFO || {})[provider.id] || {};
  if (providerMeta.composite || provider.id === 'orchestrator') {
    const result = await _setupOrchestratorInteractive();
    if (result === 'CANCEL') return null;
    if (result === 'BACK')   return _pickProviderInteractive();
    return { provider: provider.id, model: 'orchestrator' };
  }
  const picked = await _pickModelInteractive(provider.id, {
    titlePrefix: 'LazyClaw setup — Step 3 of 3:',
    onBack: 'restart',
  });
  if (picked === 'CANCEL') return null;
  if (picked === 'BACK')   return _pickProviderInteractive();
  return { provider: provider.id, model: picked };
}

// Step-3 alternative for composite providers (currently only the
// orchestrator). Builds `cfg.orchestrator = { planner, workers,
// maxSubtasks }` interactively and persists it before returning.
//
// planner: single picker over registered non-composite providers.
// workers: multi-select with a running list + add/remove/done loop.
// maxSubtasks: typed integer, default 5.
async function _setupOrchestratorInteractive() {
  const accent = (s) => `\x1b[38;5;208m${s}\x1b[0m`;
  const dim    = (s) => `\x1b[2m${s}\x1b[0m`;
  const bold   = (s) => `\x1b[1m${s}\x1b[0m`;
  const ok     = (s) => `\x1b[32m${s}\x1b[0m`;
  const info = _registryMod.PROVIDER_INFO || {};
  const eligibleNames = Object.keys(_registryMod.PROVIDERS).filter((n) => n !== 'orchestrator' && n !== 'mock');
  if (eligibleNames.length === 0) {
    process.stdout.write('\n' + accent('orchestrator setup') + ': no eligible workers — register a real provider first.\n');
    await _quickPrompt('  press Enter to continue ');
    return 'CANCEL';
  }
  const cfg = readConfig();
  const existing = cfg.orchestrator && typeof cfg.orchestrator === 'object' ? cfg.orchestrator : {};

  // ── Pick planner ─────────────────────────────────────────────────
  const plannerItems = eligibleNames.map((name) => {
    const m = info[name] || {};
    const defaultModel = m.defaultModel || '';
    return {
      id: `${name}${defaultModel ? ':' + defaultModel : ''}`,
      label: m.label && m.label !== name ? `${name} — ${m.label}` : name,
      desc: defaultModel ? `default model: ${defaultModel}` : '',
    };
  });
  const plannerPick = await _arrowMenu({
    title: 'LazyClaw setup — Step 3 of 3:  orchestrator — pick the planner',
    subtitle: 'The planner decomposes the user request into subtasks and writes the final synthesis. Strong reasoning models work best here.',
    items: plannerItems,
    searchable: true,
    defaultIdx: Math.max(0, plannerItems.findIndex((p) => p.id === existing.planner)),
  });
  if (plannerPick === 'CANCEL') return 'CANCEL';
  if (plannerPick === 'BACK')   return 'BACK';
  const planner = plannerPick.id;

  // ── Pick workers (iterative add/remove) ──────────────────────────
  const workers = Array.isArray(existing.workers) ? existing.workers.slice() : [];
  while (true) {
    process.stdout.write('\x1b[2J\x1b[H');
    process.stdout.write(accent('Orchestrator workers') + '\n');
    process.stdout.write(dim('Subtasks are dispatched round-robin across this list.') + '\n\n');
    if (workers.length === 0) {
      process.stdout.write('  ' + dim('(none yet — add at least one)') + '\n\n');
    } else {
      workers.forEach((w, i) => {
        process.stdout.write(`  ${i + 1}. ${ok(w)}\n`);
      });
      process.stdout.write('\n');
    }
    const items = [
      { id: '__add__',    label: '+ Add a worker',     desc: 'pick from registered providers' },
      { id: '__remove__', label: '- Remove a worker',  desc: workers.length ? 'pick which entry to drop' : '(nothing to remove)' },
      { id: '__done__',   label: `Done${workers.length ? ` (${workers.length} worker${workers.length === 1 ? '' : 's'})` : ' — at least one worker required'}`, desc: workers.length ? 'save cfg.orchestrator and finish' : 'add one worker first' },
    ];
    const action = await _arrowMenu({
      title: 'LazyClaw setup — orchestrator workers',
      subtitle: `Planner: ${planner}`,
      items,
    });
    if (action === 'CANCEL') return 'CANCEL';
    if (action === 'BACK')   return 'BACK';
    if (action.id === '__add__') {
      const wPick = await _arrowMenu({
        title: 'Add worker',
        subtitle: 'Picked entries are appended to the workers list.',
        items: plannerItems.filter((p) => !workers.includes(p.id)),
        searchable: true,
      });
      if (wPick === 'CANCEL' || wPick === 'BACK') continue;
      workers.push(wPick.id);
      continue;
    }
    if (action.id === '__remove__') {
      if (!workers.length) continue;
      const rPick = await _arrowMenu({
        title: 'Remove worker',
        subtitle: 'Highlighted entry is removed from the list.',
        items: workers.map((w) => ({ id: w, label: w })),
      });
      if (rPick === 'CANCEL' || rPick === 'BACK') continue;
      const idx = workers.indexOf(rPick.id);
      if (idx >= 0) workers.splice(idx, 1);
      continue;
    }
    if (action.id === '__done__') {
      if (workers.length === 0) continue;
      break;
    }
  }

  // ── maxSubtasks ──────────────────────────────────────────────────
  const defaultMax = Number.isFinite(existing.maxSubtasks) && existing.maxSubtasks > 0
    ? Math.min(10, existing.maxSubtasks)
    : 5;
  const rawMax = (await _quickPrompt(`  ${bold('maxSubtasks')} ${dim(`(2..10, blank → ${defaultMax}):`)} `)).trim();
  let maxSubtasks = defaultMax;
  if (rawMax) {
    const n = parseInt(rawMax, 10);
    if (Number.isFinite(n) && n >= 1) maxSubtasks = Math.min(10, Math.max(1, n));
  }

  // ── Persist ──────────────────────────────────────────────────────
  cfg.orchestrator = { planner, workers, maxSubtasks };
  writeConfig(cfg);
  process.stdout.write('\n');
  process.stdout.write(`  ${ok('✓ orchestrator saved')}  ${dim('→')} ` +
    `planner ${ok(planner)}  ·  ${workers.length} worker${workers.length === 1 ? '' : 's'}  ·  maxSubtasks ${maxSubtasks}\n`);
  await _quickPrompt('  press Enter to continue ');
  return { ok: true };
}

// Pause the chat REPL's readline + ghost-autocomplete while a sub-picker
// (provider / model arrow menu) takes over the terminal. The sub-picker
// installs its own `keypress` listener and toggles raw mode; the chat's
// readline would race it for stdin if we left it active. After `body`
// returns we re-emit keypress events, restore raw mode, and re-prompt
// so the chat resumes cleanly. `body` is awaited — exceptions propagate.
async function _pauseChatForSubMenu(rl, ghost, body) {
  if (ghost && typeof ghost.suspend === 'function') ghost.suspend();
  try { rl.pause(); } catch (_) {}
  // Drop the readline keypress hook so the picker's own listener has
  // sole ownership while it's open. We re-arm it on the way out.
  if (process.stdin.setRawMode) {
    try { process.stdin.setRawMode(false); } catch (_) {}
  }
  try {
    await body();
  } finally {
    const readline = await import('node:readline');
    try { readline.emitKeypressEvents(process.stdin); } catch (_) {}
    if (process.stdin.setRawMode && process.stdin.isTTY) {
      try { process.stdin.setRawMode(false); } catch (_) {}
    }
    process.stdin.resume();
    if (process.stdin.ref) process.stdin.ref();
    if (ghost && typeof ghost.resume === 'function') ghost.resume();
    try { rl.resume(); } catch (_) {}
    try { rl.prompt(); } catch (_) {}
  }
}

// Standalone model picker for the chat REPL's `/model` slash. Returns
// the chosen model id (string), 'BACK', or 'CANCEL'. Falls through to
// null when the provider has no curated models and no live-fetch surface
// (mock) — the caller should treat that as "use the provider default".
async function _pickModelInteractive(providerId, opts = {}) {
  const info = _registryMod.PROVIDER_INFO || {};
  const meta = info[providerId] || {};
  const baseModels = Array.isArray(meta.suggestedModels) ? meta.suggestedModels.slice() : [];
  const isCustom = !!meta.custom;
  const isBuiltinCompat = !!meta.builtinOpenAICompat;
  const supportsLiveFetch = !!meta.baseUrl || providerId === 'openai' || providerId === 'ollama' || isBuiltinCompat;

  if (!baseModels.length && !supportsLiveFetch) return null;

  let dynamicModels = [];
  while (true) {
    const allModels = Array.from(new Set([...baseModels, ...dynamicModels]));
    const modelItems = allModels.map((m) => ({ id: m, label: m, desc: '' }));
    if (supportsLiveFetch) {
      modelItems.unshift({
        id: '__fetch_models__',
        label: '↻ Fetch live model list from /v1/models',
        desc: isCustom || isBuiltinCompat ? `GET ${meta.baseUrl}/models` : 'pulls the up-to-date catalogue from the provider',
        tag: '\x1b[38;5;245m[live]\x1b[0m',
      });
    }
    modelItems.push({
      id: '__custom_model__',
      label: '… type a custom model id',
      desc: 'use any model id supported by this provider, even if not listed above',
      tag: '\x1b[38;5;245m[free]\x1b[0m',
    });

    const defaultIdx = supportsLiveFetch
      ? Math.max(0, 1 + allModels.indexOf(meta.defaultModel || allModels[0]))
      : Math.max(0, allModels.indexOf(meta.defaultModel || allModels[0]));
    const titlePrefix = opts.titlePrefix ? `${opts.titlePrefix}  ` : '';
    const picked = await _arrowMenu({
      title: `${titlePrefix}pick a model for ${providerId}`,
      subtitle: `Type to filter ${allModels.length} model(s). Enter to confirm. Backspace clears one char, Ctrl+U clears the filter.`,
      items: modelItems,
      defaultIdx,
      searchable: true,
    });
    if (picked === 'CANCEL') return 'CANCEL';
    if (picked === 'BACK')   return 'BACK';
    if (picked.id === '__custom_model__') {
      const typed = (await _quickPrompt(`  model id for ${providerId}: `)).trim();
      if (!typed) continue;
      return typed;
    }
    if (picked.id === '__fetch_models__') {
      try {
        process.stdout.write(`\n  fetching ${providerId} model list…\n`);
        const fetched = await _fetchModelsForProvider(providerId);
        if (!fetched.length) {
          process.stdout.write(`  ${'\x1b[33m'}no models returned${'\x1b[0m'} — falling back to the suggested list.\n`);
          await _quickPrompt('  press Enter to continue ');
        } else {
          dynamicModels = fetched;
          process.stdout.write(`  fetched ${fetched.length} model(s).\n`);
          await _quickPrompt('  press Enter to pick one ');
        }
      } catch (e) {
        process.stdout.write(`\n  ${'\x1b[33m'}fetch failed:${'\x1b[0m'} ${e?.message || e}\n`);
        await _quickPrompt('  press Enter to continue ');
      }
      continue;
    }
    return picked.id;
  }
}

// Resolve {baseUrl, apiKey} for a provider so we can call /v1/models on
// its behalf. Returns null when the provider doesn't expose an OpenAI-
// compatible model catalogue (e.g. anthropic, gemini, claude-cli).
function _modelCatalogueFor(providerId) {
  const cfg = readConfig();
  const meta = (_registryMod.PROVIDER_INFO || {})[providerId] || {};
  if (meta.custom && meta.baseUrl) {
    const entry = (cfg.customProviders || []).find((p) => p && p.name === providerId) || {};
    return { baseUrl: meta.baseUrl, apiKey: entry.apiKey || cfg['api-key'] || '' };
  }
  // Built-in OpenAI-compatible vendors (nim / openrouter / groq / together /
  // xai / deepseek / mistral / fireworks). The registry exposes a baseUrl
  // and the auth-key resolver already knows about the env-var fallback.
  if (meta.builtinOpenAICompat && meta.baseUrl) {
    return { baseUrl: meta.baseUrl, apiKey: _resolveAuthKey(cfg, providerId) };
  }
  if (providerId === 'openai') {
    return { baseUrl: 'https://api.openai.com/v1', apiKey: _resolveAuthKey(cfg, 'openai') };
  }
  if (providerId === 'ollama') {
    const host = process.env.OLLAMA_HOST || 'http://127.0.0.1:11434';
    return { baseUrl: `${host.replace(/\/$/, '')}/v1`, apiKey: '' };
  }
  return null;
}

async function _fetchModelsForProvider(providerId) {
  const c = _modelCatalogueFor(providerId);
  if (!c) throw new Error(`provider "${providerId}" does not expose an OpenAI-compatible /v1/models endpoint`);
  const { fetchOpenAICompatModels } = await import('./providers/openai_compat.mjs');
  return fetchOpenAICompatModels({ baseUrl: c.baseUrl, apiKey: c.apiKey });
}

// Walk the user through registering a new OpenAI-compatible custom
// provider (NIM, OpenRouter, vLLM, LM Studio, Together, Groq, …).
// Persists into cfg.customProviders[] and returns { name } on success,
// or null when the user backs out.
async function _addCustomProviderInteractive() {
  const accent = (s) => `\x1b[38;5;208m${s}\x1b[0m`;
  const dim    = (s) => `\x1b[2m${s}\x1b[0m`;
  const bold   = (s) => `\x1b[1m${s}\x1b[0m`;
  const ok     = (s) => `\x1b[32m${s}\x1b[0m`;

  process.stdout.write('\x1b[2J\x1b[H');
  process.stdout.write(accent('Add a custom OpenAI-compatible endpoint') + '\n');
  process.stdout.write(dim('Works with any service that speaks the OpenAI v1 wire format.') + '\n');
  process.stdout.write(dim('Examples:') + '\n');
  process.stdout.write(dim('  · NVIDIA NIM       https://integrate.api.nvidia.com/v1') + '\n');
  process.stdout.write(dim('  · OpenRouter       https://openrouter.ai/api/v1') + '\n');
  process.stdout.write(dim('  · Together AI      https://api.together.xyz/v1') + '\n');
  process.stdout.write(dim('  · Groq             https://api.groq.com/openai/v1') + '\n');
  process.stdout.write(dim('  · vLLM / LM Studio http://localhost:8000/v1') + '\n\n');

  const { validateCustomProviderName, registerCustomProviders, fetchOpenAICompatModels, isBuiltinOpenAICompatName } = _registryMod;
  let name;
  while (true) {
    const raw = (await _quickPrompt(`  ${bold('name')} ${dim('(short id, e.g. "nim", "openrouter"):')} `)).trim();
    if (!raw) {
      process.stdout.write(dim('  cancelled — back to the picker.\n'));
      return null;
    }
    try { name = validateCustomProviderName(raw); }
    catch (e) {
      process.stdout.write(`  \x1b[33m${e.message}\x1b[0m — try again.\n`);
      continue;
    }
    // OpenAI-compat builtins (nim / openrouter / groq / …) can be overridden
    // by a custom entry of the same name — both go through
    // makeOpenAICompatProvider, so the wire format is identical and the
    // user is just pointing the same alias at a different URL/key. Surface
    // the override so it isn't a silent surprise.
    if (typeof isBuiltinOpenAICompatName === 'function' && isBuiltinOpenAICompatName(name)) {
      process.stdout.write(
        `  \x1b[2mNote: "${name}" is a built-in OpenAI-compatible provider; ` +
        `your custom entry will override the built-in baseUrl/api-key for this install. ` +
        `Remove with: lazyclaw providers remove ${name}\x1b[0m\n`
      );
    }
    break;
  }
  const baseUrlRaw = (await _quickPrompt(`  ${bold('baseUrl')} ${dim('(must end in /v1, no trailing slash needed):')} `)).trim();
  if (!baseUrlRaw) { process.stdout.write(dim('  cancelled — baseUrl is required.\n')); return null; }
  if (!/^https?:\/\//i.test(baseUrlRaw)) {
    process.stdout.write('  \x1b[33mbaseUrl must start with http:// or https://\x1b[0m — cancelled.\n');
    return null;
  }
  const apiKey = (await _quickPrompt(`  ${bold('api-key')} ${dim('(blank if the endpoint is auth-less, e.g. local vLLM):')} `)).trim();

  // Persist to cfg.customProviders[]. Overwrite an existing entry of the
  // same name so re-running setup with a corrected URL just works.
  const cfg = readConfig();
  cfg.customProviders = Array.isArray(cfg.customProviders) ? cfg.customProviders : [];
  const existingIdx = cfg.customProviders.findIndex((p) => p && p.name === name);
  const entry = {
    name,
    baseUrl: baseUrlRaw.replace(/\/+$/, ''),
    apiKey: apiKey || undefined,
  };
  if (existingIdx >= 0) cfg.customProviders[existingIdx] = { ...cfg.customProviders[existingIdx], ...entry };
  else cfg.customProviders.push(entry);
  writeConfig(cfg);

  // Hot-register so the provider is callable in this same process.
  registerCustomProviders(cfg);

  // Best-effort live model probe so the user sees we can reach it. Skip
  // silently on failure — registration still succeeds and /v1/models can
  // be re-tried from the model picker.
  let probeMsg = '';
  try {
    const list = await fetchOpenAICompatModels({ baseUrl: entry.baseUrl, apiKey: entry.apiKey || '' });
    if (list.length) {
      probeMsg = `  ${ok('✓')} reachable — ${list.length} model(s) advertised at ${entry.baseUrl}/models\n`;
      // Persist the catalogue so the picker can show it without re-fetching.
      const updated = readConfig();
      const i = (updated.customProviders || []).findIndex((p) => p && p.name === name);
      if (i >= 0) {
        updated.customProviders[i].suggestedModels = list.slice(0, 50);
        if (!updated.customProviders[i].defaultModel) updated.customProviders[i].defaultModel = list[0];
        writeConfig(updated);
        registerCustomProviders(updated);
      }
    } else {
      probeMsg = `  ${ok('✓')} registered — /v1/models returned no entries (will rely on free-text model id).\n`;
    }
  } catch (e) {
    probeMsg = `  \x1b[33m!\x1b[0m registered, but /v1/models probe failed: ${e?.message || e}\n`;
  }
  process.stdout.write('\n');
  process.stdout.write(`  ${ok(bold('✓ custom provider saved:'))} ${name}  ${dim('→')} ${entry.baseUrl}\n`);
  process.stdout.write(probeMsg);
  process.stdout.write(dim(`  Removable any time via:  lazyclaw providers remove ${name}\n`));
  await _quickPrompt('  press Enter to continue ');
  return { name };
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
  let _ghost = { dispose: () => {}, suspend: () => {}, resume: () => {} };
  if (useTerminal) {
    // Cursor-style ghost autocomplete: when the buffer starts with `/`,
    // render the longest matching command after the cursor in dim grey.
    // Right-arrow at end-of-line accepts. Tab still cycles via the
    // existing handleSlash branch; this only adds the inline preview.
    _ghost = _attachGhostAutocomplete(rl) || _ghost;
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
        // `/provider` (no arg) opens the family/provider/model picker so
        // the user can switch with arrow keys instead of memorising names.
        const arg = line.slice('/provider'.length).trim();
        if (!arg) {
          if (!useTerminal) {
            process.stdout.write(`provider: ${activeProvName}\n`);
            return true;
          }
          await _pauseChatForSubMenu(rl, _ghost, async () => {
            const picked = await _pickProviderInteractive();
            if (picked && picked.provider) {
              const next = lookupProv(picked.provider);
              if (!next) {
                process.stdout.write(`unknown provider: ${picked.provider}\n`);
                return;
              }
              activeProvName = picked.provider;
              prov = next;
              if (picked.model) activeModel = picked.model;
              process.stdout.write(`provider → ${activeProvName}${picked.model ? ` · model → ${picked.model}` : ''}\n`);
            }
          });
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
        // provider. `/model` (no arg) opens the per-provider model picker
        // — same UX as setup step 3, scoped to the active provider.
        const arg = line.slice('/model'.length).trim();
        if (!arg) {
          if (!useTerminal) {
            process.stdout.write(`model: ${activeModel || '(default)'}\n`);
            return true;
          }
          await _pauseChatForSubMenu(rl, _ghost, async () => {
            const chosen = await _pickModelInteractive(activeProvName, { titlePrefix: 'LazyClaw chat —' });
            if (chosen === 'CANCEL' || chosen === 'BACK' || !chosen) return;
            activeModel = chosen;
            process.stdout.write(`model → ${activeModel}\n`);
          });
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
    // Pause the ghost-autocomplete keypress handler while the
    // provider is streaming. Without this, every stale stdin event
    // would trigger `\x1b[s\x1b[K\x1b[u` cursor save/restore writes
    // that interleave with the streamed text and surface as visible
    // gaps between CJK characters (visible in user-reported screen
    // captures of Korean replies).
    if (useTerminal) _ghost.suspend();
    // Buffered writer — coalesce single-character streaming chunks
    // into ~30 ms windows. Two reasons:
    //   1. Korean / Japanese / Chinese tokens often arrive as one
    //      character per chunk. Each individual `process.stdout.write`
    //      can race against terminal redraw on a wide-cell character,
    //      producing the same "visible space between every character"
    //      symptom the suspend above also addresses.
    //   2. Far fewer syscalls. A 200-char Korean reply was ~200
    //      separate writes; this collapses to ~7-10.
    let _writeBuf = '';
    let _writeTimer = null;
    const _flush = () => {
      if (_writeBuf) { process.stdout.write(_writeBuf); _writeBuf = ''; }
      _writeTimer = null;
    };
    const _writeChunk = (s) => {
      _writeBuf += s;
      if (!_writeTimer) _writeTimer = setTimeout(_flush, 30);
    };
    try {
      for await (const chunk of prov.sendMessage(messages, {
        apiKey: _resolveAuthKey(cfg, activeProvName),
        model: activeModel,
        sandbox: sandboxSpec,
        signal: turnAc.signal,
        onUsage: accumulateUsage,
      })) {
        _writeChunk(chunk);
        acc += chunk;
      }
      // Drain anything still buffered before the trailing newline so
      // the prompt lands on its own line cleanly.
      if (_writeTimer) clearTimeout(_writeTimer);
      _flush();
      process.stdout.write('\n');
      messages.push({ role: 'assistant', content: acc });
      persistTurn('assistant', acc);
    } catch (err) {
      // Drain pending buffer so partial reply stays on screen even
      // when the stream errors mid-flight.
      if (_writeTimer) clearTimeout(_writeTimer);
      _flush();
      // ABORT errors are user-initiated; partial assistant output is
      // discarded (we don't append a half-reply to the message history
      // because the next turn would treat it as a complete reply and
      // give odd context to the model).
      if (err?.code !== 'ABORT' && !turnAc.signal.aborted) {
        process.stdout.write(`error: ${err?.message || String(err)}\n`);
      }
    } finally {
      process.off('SIGINT', onSigint);
      if (useTerminal) _ghost.resume();
    }
    if (useTerminal) rl.prompt();
  } } finally {
    // Clean shutdown — without this, /exit "worked" but the process
    // hung for ~3-5 s while Node waited for stdin's keypress listener
    // and raw mode to release. Tearing them down explicitly drops the
    // exit time to <100 ms.
    try { _ghost.dispose(); } catch (_) {}
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
// Best-effort port-occupant kill — macOS / Linux only. Returns true when
// at least one PID was signalled. Used by cmdDashboard so a leftover
// listener from a previous run doesn't crash the launch with EADDRINUSE.
// Mirrors the Python server's auto-kill behaviour described in CLAUDE.md.
async function _killPortOccupant(port) {
  if (process.platform === 'win32') return false;
  const { spawn } = await import('node:child_process');
  return new Promise((resolve) => {
    let lsof;
    try {
      lsof = spawn('lsof', ['-ti', `tcp:${port}`], { stdio: ['ignore', 'pipe', 'ignore'] });
    } catch (_) { return resolve(false); }
    let buf = '';
    lsof.stdout.on('data', (d) => { buf += d.toString('utf8'); });
    lsof.on('error', () => resolve(false));
    lsof.on('close', () => {
      const pids = buf.trim().split(/\s+/).map((s) => parseInt(s, 10)).filter(Number.isFinite);
      if (!pids.length) return resolve(false);
      // SIGTERM first so node has a chance to clean up; SIGKILL the
      // holdouts after a short grace window.
      for (const pid of pids) {
        try { process.kill(pid, 'SIGTERM'); } catch (_) { /* gone already */ }
      }
      setTimeout(() => {
        for (const pid of pids) {
          try { process.kill(pid, 'SIGKILL'); } catch (_) { /* gone */ }
        }
        resolve(true);
      }, 200);
    });
  });
}

async function cmdDashboard(flags = {}) {
  await ensureRegistry();
  const sessionsMod = await import('./sessions.mjs');
  const { startDaemon } = await import('./daemon.mjs');
  const port = flags.port !== undefined ? parseInt(flags.port, 10) : 19600;
  const cfgDir = path.dirname(configPath());
  const daemonOpts = {
    port,
    once: false,
    readConfig,
    writeConfig,
    sessionsDirGetter: () => cfgDir,
    sessionsMod,
    version: () => readVersionFromRepo(),
    workflowStateDir: () => process.env.LAZYCLAW_WORKFLOW_STATE_DIR || '.workflow-state',
    // No auth token by default — same loopback-only assumption the
    // bare daemon uses. Users who want to expose the dashboard set
    // LAZYCLAW_AUTH_TOKEN + --allow-origin via the daemon command.
    authToken: undefined,
    allowedOrigins: [],
    // The dashboard's browser tab posts back to the same loopback URL
    // it was served from (e.g. `http://127.0.0.1:19600`). Without this
    // opt-in every chat send / mutation tripped the daemon's CSRF gate
    // with `403 forbidden origin`. Safe — the daemon binds 127.0.0.1
    // only, so an attacker can't reach it with a loopback origin
    // unless they're already on the machine.
    allowLoopbackOrigin: true,
    rateLimit: null,
    responseCache: null,
    logger: null,
    costCap: null,
  };
  let d;
  try {
    d = await startDaemon(daemonOpts);
  } catch (err) {
    if (err?.code !== 'EADDRINUSE') throw err;
    // Port is held by a leftover dashboard / daemon. Try to free it
    // (lsof + kill on macOS/Linux); on failure, fall back to a random
    // port so the user always gets a working dashboard rather than a
    // crash trace.
    const portInUse = port;
    process.stderr.write(`  ⚠ port ${portInUse} is in use — likely a previous dashboard didn't shut down.\n`);
    const killed = await _killPortOccupant(portInUse);
    if (killed) {
      process.stderr.write(`  ✓ freed port ${portInUse} (killed prior listener) — retrying…\n`);
      // Short pause so the OS releases the port before we re-listen.
      await new Promise(r => setTimeout(r, 250));
      try { d = await startDaemon(daemonOpts); }
      catch (err2) {
        if (err2?.code !== 'EADDRINUSE') throw err2;
        process.stderr.write(`  ⚠ still in use — falling back to a random port.\n`);
        d = await startDaemon({ ...daemonOpts, port: 0 });
      }
    } else {
      process.stderr.write(`  ⚠ couldn't free port ${portInUse} automatically — falling back to a random port.\n`);
      d = await startDaemon({ ...daemonOpts, port: 0 });
    }
  }
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
  let d;
  try {
    d = await startDaemon({
      port: Number.isFinite(port) ? port : 0,
      once,
      readConfig,
      // `lazyclaw daemon` exposes mutation endpoints (POST /providers,
      // PUT /rates/<key>, etc.) only when an auth token is configured
      // — without one the daemon is loopback-only but still untrusted
      // (any process on the box can hit it). dashboard subcommand sets
      // writeConfig unconditionally because it always runs as the user.
      writeConfig: authToken ? writeConfig : undefined,
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
  } catch (err) {
    // `lazyclaw daemon` exits cleanly on EADDRINUSE with a readable
    // message instead of the historical unhandled-error stack trace.
    // Unlike `lazyclaw dashboard`, daemon doesn't auto-kill the prior
    // listener — bare daemon callers are usually scripts that expect
    // exact port semantics, so we surface the failure and let them
    // choose (re-run with --port 0 for random, or kill the holdout).
    if (err?.code === 'EADDRINUSE') {
      process.stderr.write(
        `lazyclaw daemon: port ${port} is in use.\n` +
        `  Re-run with --port 0 for a random port, or free the port:\n` +
        `    lsof -ti tcp:${port} | xargs kill -9\n`
      );
      process.exit(2);
    }
    throw err;
  }
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
    case 'add': {
      // Register an OpenAI-compatible custom endpoint non-interactively.
      // Mirrors the picker's "+ Add custom" flow but scriptable, so users
      // can wire NIM / OpenRouter / vLLM into config without entering the
      // arrow-key UI.
      //   lazyclaw providers add nim \
      //     --base-url https://integrate.api.nvidia.com/v1 \
      //     --api-key nvapi-xxx \
      //     [--default-model meta/llama-3.1-70b] \
      //     [--no-probe]
      const name = positional[0];
      const baseUrl = flags['base-url'] || flags.baseUrl;
      const apiKey = flags['api-key'] || flags.apiKey || '';
      if (!name || !baseUrl) {
        console.error('Usage: lazyclaw providers add <name> --base-url <url> [--api-key <key>] [--default-model <id>] [--no-probe]');
        process.exit(2);
      }
      let validName;
      try { validName = _registryMod.validateCustomProviderName(name); }
      catch (e) { console.error(e.message); process.exit(2); }
      if (!/^https?:\/\//i.test(String(baseUrl))) {
        console.error('--base-url must start with http:// or https://');
        process.exit(2);
      }
      const cfg = readConfig();
      cfg.customProviders = Array.isArray(cfg.customProviders) ? cfg.customProviders : [];
      const idx = cfg.customProviders.findIndex((p) => p && p.name === validName);
      const entry = {
        name: validName,
        baseUrl: String(baseUrl).replace(/\/+$/, ''),
        apiKey: apiKey || undefined,
      };
      if (flags['default-model']) entry.defaultModel = flags['default-model'];
      if (idx >= 0) cfg.customProviders[idx] = { ...cfg.customProviders[idx], ...entry };
      else cfg.customProviders.push(entry);
      writeConfig(cfg);
      _registryMod.registerCustomProviders(cfg);

      let probe = null;
      if (!flags['no-probe']) {
        try {
          const list = await _registryMod.fetchOpenAICompatModels({
            baseUrl: entry.baseUrl, apiKey: entry.apiKey || '',
          });
          probe = { ok: true, modelCount: list.length, sample: list.slice(0, 8) };
          if (list.length) {
            const updated = readConfig();
            const i = (updated.customProviders || []).findIndex((p) => p && p.name === validName);
            if (i >= 0) {
              updated.customProviders[i].suggestedModels = list.slice(0, 50);
              if (!updated.customProviders[i].defaultModel) updated.customProviders[i].defaultModel = list[0];
              writeConfig(updated);
              _registryMod.registerCustomProviders(updated);
            }
          }
        } catch (e) {
          probe = { ok: false, error: e?.message || String(e) };
        }
      }
      console.log(JSON.stringify({
        ok: true, added: validName, baseUrl: entry.baseUrl, hasApiKey: !!entry.apiKey, probe,
      }, null, 2));
      return;
    }
    case 'remove': {
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw providers remove <name>'); process.exit(2); }
      const cfg = readConfig();
      const list = Array.isArray(cfg.customProviders) ? cfg.customProviders : [];
      const before = list.length;
      cfg.customProviders = list.filter((p) => !(p && p.name === name));
      if (cfg.customProviders.length === before) {
        console.error(`no custom provider named "${name}" — registered: ${list.map((p) => p.name).join(', ') || '(none)'}`);
        process.exit(2);
      }
      writeConfig(cfg);
      // The in-memory PROVIDERS map keeps the dropped entry until process
      // restart — fine for the CLI (each invocation re-registers from
      // disk). We don't try to mutate it here.
      console.log(JSON.stringify({ ok: true, removed: name }, null, 2));
      return;
    }
    case 'models': {
      // Fetch + print the live model list from a provider's /v1/models.
      // Works for any registered OpenAI-compatible endpoint (custom +
      // openai + ollama). Used by the picker but useful standalone too:
      //   lazyclaw providers models nim
      //   lazyclaw providers models openai --filter gpt-4
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw providers models <name> [--filter <substr>]'); process.exit(2); }
      if (!_registryMod.PROVIDERS[name]) {
        console.error(`unknown provider: ${name}`);
        process.exit(2);
      }
      try {
        const list = await _fetchModelsForProvider(name);
        let out = list;
        if (flags.filter) {
          const f = String(flags.filter).toLowerCase();
          out = out.filter((m) => m.toLowerCase().includes(f));
        }
        console.log(JSON.stringify({ ok: true, provider: name, count: out.length, models: out }, null, 2));
        return;
      } catch (e) {
        console.log(JSON.stringify({ ok: false, provider: name, error: e?.message || String(e) }, null, 2));
        process.exit(1);
      }
    }
    default:
      console.error('Usage: lazyclaw providers <list|info <name>|test <name>|add <name> --base-url <url> [--api-key <k>]|remove <name>|models <name>>');
      process.exit(2);
  }
}

// `lazyclaw orchestrator` — read/write the cfg.orchestrator section
// without editing config.json by hand. Mirrors the shape `lazyclaw
// providers` / `lazyclaw rates` already use.
//
// Subcommands:
//   status                        Print current planner / workers / maxSubtasks as JSON.
//   set-planner <provider[:model]>  Replace the planner spec.
//   workers add <provider[:model]>  Append a worker (idempotent — duplicates skipped).
//   workers remove <provider[:model]>  Drop a worker by exact match. Idempotent.
//   workers clear                 Empty the workers list.
//   workers set <provider[:model],...>  Replace the whole list (comma-separated).
//   set-max-subtasks <N>          Cap the number of subtasks (clamped 1..10).
//   clear                         Delete the entire cfg.orchestrator block.
async function cmdOrchestrator(sub, positional, _flags = {}) {
  await ensureRegistry();
  const cfg = readConfig();
  const orch = cfg.orchestrator && typeof cfg.orchestrator === 'object' ? cfg.orchestrator : {};
  const known = Object.keys(_registryMod.PROVIDERS);
  const validateSpec = (spec) => {
    if (!spec) throw new Error('provider spec required (e.g. "claude-cli" or "openai:gpt-4o")');
    const colon = spec.indexOf(':');
    const provName = colon > 0 ? spec.slice(0, colon) : spec;
    if (provName === 'orchestrator') throw new Error('"orchestrator" cannot reference itself — pick a real provider');
    if (!known.includes(provName)) {
      throw new Error(`unknown provider "${provName}" — registered: ${known.join(', ')}`);
    }
    return spec;
  };
  const saveAndPrint = (next) => {
    if (next === null) delete cfg.orchestrator;
    else cfg.orchestrator = next;
    writeConfig(cfg);
    console.log(JSON.stringify(cfg.orchestrator || null, null, 2));
  };
  switch (sub) {
    case undefined:
    case 'status': {
      console.log(JSON.stringify({
        ok: true,
        configured: !!cfg.orchestrator,
        planner: orch.planner || null,
        workers: Array.isArray(orch.workers) ? orch.workers : [],
        maxSubtasks: Number.isFinite(orch.maxSubtasks) ? orch.maxSubtasks : null,
        knownProviders: known,
      }, null, 2));
      return;
    }
    case 'set-planner': {
      try {
        const spec = validateSpec(positional[0]);
        saveAndPrint({ ...orch, planner: spec });
      } catch (e) { console.error(`orchestrator: ${e.message}`); process.exit(2); }
      return;
    }
    case 'workers': {
      const wsub = positional[0];
      const workers = Array.isArray(orch.workers) ? orch.workers.slice() : [];
      switch (wsub) {
        case 'add': {
          try {
            const spec = validateSpec(positional[1]);
            if (!workers.includes(spec)) workers.push(spec);
            saveAndPrint({ ...orch, workers });
          } catch (e) { console.error(`orchestrator: ${e.message}`); process.exit(2); }
          return;
        }
        case 'remove': {
          const spec = positional[1];
          if (!spec) { console.error('orchestrator: workers remove <provider[:model]>'); process.exit(2); }
          const idx = workers.indexOf(spec);
          if (idx >= 0) workers.splice(idx, 1);
          saveAndPrint({ ...orch, workers });
          return;
        }
        case 'clear': {
          saveAndPrint({ ...orch, workers: [] });
          return;
        }
        case 'set': {
          const raw = positional[1] || '';
          const specs = raw.split(',').map((s) => s.trim()).filter(Boolean);
          try {
            specs.forEach(validateSpec);
            saveAndPrint({ ...orch, workers: specs });
          } catch (e) { console.error(`orchestrator: ${e.message}`); process.exit(2); }
          return;
        }
        default: {
          console.error('Usage: lazyclaw orchestrator workers <add <spec> | remove <spec> | clear | set <spec,spec,...>>');
          process.exit(2);
        }
      }
    }
    case 'set-max-subtasks': {
      const n = parseInt(positional[0], 10);
      if (!Number.isFinite(n) || n < 1) { console.error('orchestrator: set-max-subtasks <N>  (1..10)'); process.exit(2); }
      saveAndPrint({ ...orch, maxSubtasks: Math.min(10, Math.max(1, n)) });
      return;
    }
    case 'clear': {
      saveAndPrint(null);
      return;
    }
    default: {
      console.error(
        'Usage:\n' +
        '  lazyclaw orchestrator status\n' +
        '  lazyclaw orchestrator set-planner <provider[:model]>\n' +
        '  lazyclaw orchestrator workers add <provider[:model]>\n' +
        '  lazyclaw orchestrator workers remove <provider[:model]>\n' +
        '  lazyclaw orchestrator workers set <provider[:model],...>\n' +
        '  lazyclaw orchestrator workers clear\n' +
        '  lazyclaw orchestrator set-max-subtasks <N>\n' +
        '  lazyclaw orchestrator clear'
      );
      process.exit(2);
    }
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
  'no-probe',     // providers add: skip the /v1/models reachability probe
  'pick',         // onboard / chat: force the interactive picker even when provider already set
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
    // Don't kill the process — the setup wizard is often called
    // from inside cmdLauncher's loop, and a process.exit there
    // would close the launcher entirely (the surface bug the
    // user reported as "Setup 누르고 엔터 누르니까 바로 꺼져").
    // Surface the error and let the caller decide.
    process.stderr.write(`onboard error: ${e?.message || e}\n`);
    return;
  }
  // Re-read config after onboard wrote it. If the user aborted with
  // no provider set, bail out early — the rest of the wizard depends
  // on a provider being configured. `return` (not process.exit) so a
  // launcher caller can re-prompt or fall back gracefully.
  const cfgAfterOnboard = readConfig();
  if (!cfgAfterOnboard.provider) {
    process.stdout.write(`\n  ${warn('Setup not completed — provider was not configured.')}\n`);
    process.stdout.write(`  ${dim('Run `lazyclaw setup` again when ready, or pick "Onboard" from the menu for a single-step picker.')}\n\n`);
    return;
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

// Marker exception used by the launcher's process.exit guard. See
// _dispatchMenuChoice below for why intercepting process.exit is
// the cleanest way to keep the menu loop alive.
class _DispatchExit extends Error {
  constructor(code) {
    super(`subcommand requested exit ${code}`);
    this.name = 'DispatchExit';
    this.exitCode = Number.isFinite(code) ? code : 0;
  }
}

// Direct dispatch from a launcher pick. Replaces the previous
// `process.argv = [...]; await main()` round-trip so we can reuse
// the launcher across multiple iterations without compounding
// state.
//
// Subcommand functions across this CLI freely call `process.exit()`
// to signal their result — perfectly fine for one-shot CLI use,
// fatal to a launcher loop because the first exit kills the whole
// process before we can redraw the menu. Intercept process.exit for
// the duration of the dispatch and turn it into a thrown exception
// the loop can catch + log + continue from. This mirrors how Python
// CLI frameworks handle SystemExit when running inside a REPL.
async function _dispatchMenuChoice(argv) {
  const sub = argv[0];
  const rest = argv.slice(1);
  const realExit = process.exit.bind(process);
  process.exit = (code) => { throw new _DispatchExit(code); };
  try {
    switch (sub) {
      case 'chat':         return await cmdChat({});
      case 'agent':        return await cmdAgent(rest[0] || '-', {});
      case 'onboard':      return await cmdOnboard({});
      case 'setup':        return await cmdSetup(undefined, rest, {});
      case 'workspace':    return await cmdWorkspace(rest[0], rest.slice(1), {});
      case 'browse':       return await cmdBrowse(rest[0], {});
      case 'skills':       return await cmdSkills(rest[0], rest.slice(1), {});
      case 'sessions':     return await cmdSessions(rest[0], rest.slice(1), {});
      case 'providers':    return await cmdProviders(rest[0], rest.slice(1), {});
      case 'cron':         return await cmdCron(rest[0], rest.slice(1), {});
      case 'auth':         return await cmdAuth(rest[0], rest.slice(1), {});
      case 'pairing':      return await cmdPairing(rest[0], rest.slice(1), {});
      case 'nodes':        return await cmdNodes(rest[0], rest.slice(1), {});
      case 'message':      return await cmdMessage(rest[0], rest.slice(1), {});
      case 'doctor':       return await cmdDoctor();
      case 'status':       return await cmdStatus();
      // v3.99.27 — fill the rest of the lazyclaw <subcommand> surface
      // so the no-arg launcher mirrors every entry in SUBCOMMANDS.
      case 'orchestrator': return await cmdOrchestrator(rest[0], rest.slice(1), {});
      case 'rates':        return await cmdRates(rest[0], rest.slice(1), {});
      case 'config':       {
        // Mirror the main switch's tiny dispatcher.
        const csub = rest[0];
        if (csub === 'list' || csub === undefined) return cmdConfigGet(undefined);
        if (csub === 'get')   return cmdConfigGet(rest[1]);
        if (csub === 'set')   return cmdConfigSet(rest[1], rest.slice(2).join(' '));
        if (csub === 'path')  { process.stdout.write(configPath() + '\n'); return; }
        if (csub === 'edit')  return await cmdConfigEdit();
        if (csub === 'validate') return await cmdConfigValidate();
        process.stderr.write('Usage: lazyclaw config <get|set|list|delete|path|edit|validate>\n');
        return;
      }
      case 'inspect':      return await cmdInspect(rest[0], {});
      case 'export':       return await cmdExport({});
      case 'version':      return await cmdVersion();
      // help <cmd> is the safe fallback for commands that need real
      // arguments (run / resume / clear / validate / graph / daemon /
      // import / completion). Print the usage so the user can re-launch
      // with proper flags — the menu stays alive.
      case 'help':         return cmdHelp(rest[0]);
      case 'dashboard':    return await cmdDashboard({});
      default:             throw new Error(`unknown menu choice: ${sub}`);
    }
  } catch (e) {
    if (e instanceof _DispatchExit) {
      // Subcommand wanted to exit. Surface a non-zero code so the
      // user knows something flagged, but DON'T propagate — we want
      // the launcher loop to continue.
      if (e.exitCode !== 0) {
        process.stderr.write(`  \x1b[2m(subcommand returned exit code ${e.exitCode})\x1b[0m\n`);
      }
      return;
    }
    throw e;
  } finally {
    process.exit = realExit;
  }
}

async function cmdLauncher() {
  await ensureRegistry();
  // Item table is fixed across iterations — only the dispatcher and
  // the per-iteration draw redraw on each loop tick.
  // Mirror every top-level `lazyclaw <subcommand>` here so the no-arg
  // launcher is a complete discovery surface. Commands that need
  // arguments (workflow runner, daemon, completion, import) route
  // through `help <cmd>` so the menu pick prints copy-pasteable usage
  // instead of erroring or blocking. Commands with a sensible default
  // ('list' / 'status') get dispatched directly.
  const items = [
    // Core interaction
    { id: 'chat',         label: 'Chat',         desc: 'interactive REPL with the configured provider', argv: ['chat'] },
    { id: 'agent',        label: 'Agent',        desc: 'one-shot prompt — read text and exit',          argv: ['agent'], promptForBody: true },
    { id: 'orchestrator', label: 'Orchestrator', desc: 'multi-agent dispatch — planner + workers',      argv: ['orchestrator', 'status'] },
    // UI & onboarding
    { id: 'dashboard',    label: 'Dashboard',    desc: 'open the lazyclaw web UI in your browser',      argv: ['dashboard'] },
    { id: 'setup',        label: 'Setup',        desc: 'multi-step provider / workspace / skill wizard',argv: ['setup'] },
    { id: 'onboard',      label: 'Onboard',      desc: 'pick provider / model / api-key',               argv: ['onboard'] },
    // Auth & config
    { id: 'providers',    label: 'Providers',    desc: 'registered providers + reachability',           argv: ['providers', 'list'] },
    { id: 'auth',         label: 'Auth',         desc: 'multi-key rotation per provider',               argv: ['help', 'auth'] },
    { id: 'config',       label: 'Config',       desc: 'cfg.json get/set/list/delete/path/edit',        argv: ['config', 'list'] },
    { id: 'rates',        label: 'Rates',        desc: 'per-model input/output pricing cards',          argv: ['rates', 'list'] },
    // Workspaces & assets
    { id: 'workspace',    label: 'Workspace',    desc: 'AGENTS.md / SOUL.md / TOOLS.md prompt bundles', argv: ['workspace', 'list'] },
    { id: 'skills',       label: 'Skills',       desc: 'installed skill bundles',                       argv: ['skills', 'list'] },
    { id: 'sessions',     label: 'Sessions',     desc: 'persisted chat sessions',                       argv: ['sessions', 'list'] },
    // Outbound & schedule
    { id: 'browse',       label: 'Browse',       desc: 'fetch a URL → markdown',                        argv: ['browse'], promptForUrl: true },
    { id: 'message',      label: 'Message',      desc: 'outbound webhook (Slack / Discord / generic)',  argv: ['message', 'list'] },
    { id: 'cron',         label: 'Cron',         desc: 'recurring agent runs (launchd / crontab)',      argv: ['cron', 'list'] },
    // Workflow runner (.mjs)
    { id: 'run',          label: 'Run',          desc: '.mjs workflow runner (needs session + file)',   argv: ['help', 'run'] },
    { id: 'resume',       label: 'Resume',       desc: 're-enter a persisted workflow run',             argv: ['help', 'resume'] },
    { id: 'inspect',      label: 'Inspect',      desc: 'list / drill into persisted workflow sessions', argv: ['inspect'] },
    { id: 'clear',        label: 'Clear',        desc: 'delete the state file for a session',           argv: ['help', 'clear'] },
    { id: 'validate',     label: 'Validate',     desc: 'static-check a workflow.mjs (shape + deps)',    argv: ['help', 'validate'] },
    { id: 'graph',        label: 'Graph',        desc: 'emit Mermaid graph TD / LR from a workflow',    argv: ['help', 'graph'] },
    // Devices & process
    { id: 'pairing',      label: 'Pairing',      desc: 'sender allowlist for the messaging surface',    argv: ['pairing', 'list'] },
    { id: 'nodes',        label: 'Nodes',        desc: 'companion device registry',                     argv: ['nodes', 'list'] },
    { id: 'daemon',       label: 'Daemon',       desc: 'localhost HTTP daemon (blocking — see usage)',  argv: ['help', 'daemon'] },
    // Bundle
    { id: 'export',       label: 'Export',       desc: 'redacted config bundle → stdout',               argv: ['export'] },
    { id: 'import',       label: 'Import',       desc: 'restore from a bundle on stdin',                argv: ['help', 'import'] },
    // Tools
    { id: 'completion',   label: 'Completion',   desc: 'shell completion (bash | zsh)',                 argv: ['help', 'completion'] },
    { id: 'version',      label: 'Version',      desc: 'lazyclaw version + Node + platform',            argv: ['version'] },
    // Diagnostics
    { id: 'doctor',       label: 'Doctor',       desc: 'diagnostic — config, providers, workflows',    argv: ['doctor'] },
    { id: 'status',       label: 'Status',       desc: 'current provider / model / masked key',         argv: ['status'] },
    // Meta
    { id: 'help',         label: 'Help',         desc: 'one-line summary of every subcommand',          argv: ['help'] },
    { id: 'quit',         label: 'Quit',         desc: 'exit lazyclaw',                                 argv: null },
  ];

  const accent = (s) => `\x1b[38;5;208m${s}\x1b[0m`;
  const dim    = (s) => `\x1b[2m${s}\x1b[0m`;
  const bold   = (s) => `\x1b[1m${s}\x1b[0m`;
  const ok     = (s) => `\x1b[32m${s}\x1b[0m`;
  const warn   = (s) => `\x1b[33m${s}\x1b[0m`;

  let idx = 0;
  // Outer loop — each iteration is one menu render → pick →
  // dispatch round. Subcommand return drops back here and the menu
  // is redrawn. Quit / Esc / Ctrl-C breaks the loop and returns,
  // which lets the calling main() exit naturally.
  //
  // try/finally below is load-bearing: the loop body keeps stdin
  // ref'd so the picker's keypress events fire. If we just `return`
  // on Quit, stdin stays ref'd and Node's event loop never empties
  // → the `lazyclaw` process hangs forever after the user picked
  // Quit. The finally explicitly pauses + unrefs stdin so the
  // process exits cleanly the moment the user picks Quit.
  try {
  while (true) {
    // First-run / config-missing guard: a fresh install has no
    // `provider` set, so any menu pick that calls a provider would
    // error halfway through. Funnel through cmdSetup before
    // rendering the menu the first time around.
    let cfg = readConfig();
    if (!cfg.provider) {
      try { await cmdSetup(undefined, [], {}); }
      catch (e) {
        process.stderr.write(`setup error: ${e?.message || e}\n`);
      }
      cfg = readConfig();
      if (!cfg.provider) {
        process.stdout.write('\n  Setup not completed — exiting.\n  Run `lazyclaw setup` when ready, then try `lazyclaw` again.\n\n');
        return;
      }
    }
    const provider = cfg.provider;
    const model = cfg.model || '(default)';

    // Re-establish stdin in raw / ref'd mode. A previous iteration
    // (e.g. `chat`) deliberately paused + unref'd stdin in its
    // exit-cleanup path so the process could end on /exit; now that
    // we want to keep going, re-attach.
    const readline = await import('node:readline');
    readline.emitKeypressEvents(process.stdin);
    if (process.stdin.setRawMode) process.stdin.setRawMode(true);
    process.stdin.resume();
    process.stdin.ref();

    const draw = () => {
      process.stdout.write('\x1b[?25l\x1b[2J\x1b[H'); // hide cursor + clear
      _renderBanner(readVersionFromRepo()).forEach((l) => process.stdout.write(l + '\n'));
      process.stdout.write('\n');
      process.stdout.write(`  ${dim('provider ·')} ${ok(provider)}\n`);
      process.stdout.write(`  ${dim('model    ·')} ${ok(model)}\n`);
      process.stdout.write(`  ${dim('config   ·')} ${dim(configPath())}\n`);
      process.stdout.write('\n');
      process.stdout.write(`  ${dim('↑/↓ to move · Enter to select · / for slash command (e.g. /exit) · q or Esc to quit')}\n\n`);
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

    // Slash-command mini prompt rendered just below the menu. Lets users
    // type `/exit` / `/quit` / `/help` to leave (or get a list of slash
    // commands) without hunting for the right special key. The menu is
    // raw-mode and never sees a newline-terminated line, so we accumulate
    // keystrokes locally instead of round-tripping through readline.
    let slashBuffer = null; // null = menu mode; string = slash mode (always starts with '/')
    let slashNotice = '';   // one-line hint shown after the buffer (e.g. "unknown command")
    const LAUNCHER_SLASH_HELP = [
      { cmd: '/exit',    help: 'leave lazyclaw' },
      { cmd: '/quit',    help: 'alias for /exit' },
      { cmd: '/help',    help: 'list slash commands' },
      { cmd: '/version', help: 'print version + node + platform' },
    ];
    const drawWithSlash = () => {
      draw();
      process.stdout.write(`  ${dim('slash ›')} ${slashBuffer}`);
      if (slashNotice) process.stdout.write(`   ${slashNotice}`);
      process.stdout.write('\x1b[?25h'); // show cursor while typing
    };

    draw();
    const picked = await new Promise((resolve) => {
      const onKey = (str, key) => {
        if (!key) return;

        // ── Slash-command input mode ─────────────────────────────────
        if (slashBuffer !== null) {
          if (key.ctrl && key.name === 'c') { cleanup(); resolve({ id: 'quit', argv: null }); return; }
          if (key.name === 'escape') { slashBuffer = null; slashNotice = ''; draw(); return; }
          if (key.name === 'return') {
            const cmd = slashBuffer.trim().toLowerCase();
            if (cmd === '/exit' || cmd === '/quit') { cleanup(); resolve({ id: 'quit', argv: null }); return; }
            if (cmd === '/help') {
              slashBuffer = '/';
              slashNotice = dim(LAUNCHER_SLASH_HELP.map(c => `${c.cmd} (${c.help})`).join(' · '));
              drawWithSlash();
              return;
            }
            if (cmd === '/version') {
              const v = readVersionFromRepo();
              slashNotice = ok(`v${v} · node ${process.version} · ${process.platform}-${process.arch}`);
              drawWithSlash();
              return;
            }
            // Unknown command — keep the buffer so the user can edit it
            // rather than retyping from scratch. Esc / Backspace bails.
            slashNotice = warn(`unknown — try ${LAUNCHER_SLASH_HELP.map(c => c.cmd).join(' · ')}`);
            drawWithSlash();
            return;
          }
          if (key.name === 'backspace') {
            slashNotice = '';
            if (slashBuffer.length > 1) slashBuffer = slashBuffer.slice(0, -1);
            else slashBuffer = null;
            slashBuffer === null ? draw() : drawWithSlash();
            return;
          }
          // Append printable characters. Filter control / meta chords so
          // Ctrl+L etc. don't pollute the buffer.
          if (str && str.length === 1 && !key.ctrl && !key.meta && str >= ' ') {
            slashBuffer += str;
            slashNotice = '';
            drawWithSlash();
          }
          return;
        }

        // ── Menu navigation mode ─────────────────────────────────────
        if (key.name === 'up')        { idx = (idx - 1 + items.length) % items.length; draw(); }
        else if (key.name === 'down') { idx = (idx + 1) % items.length; draw(); }
        else if (key.name === 'home') { idx = 0; draw(); }
        else if (key.name === 'end')  { idx = items.length - 1; draw(); }
        else if (key.name === 'pageup')   { idx = Math.max(0, idx - 5); draw(); }
        else if (key.name === 'pagedown') { idx = Math.min(items.length - 1, idx + 5); draw(); }
        else if (key.name === 'return')   { cleanup(); resolve(items[idx]); }
        else if (key.ctrl && key.name === 'c') { cleanup(); resolve({ id: 'quit', argv: null }); }
        else if (key.name === 'escape' || key.name === 'q') { cleanup(); resolve({ id: 'quit', argv: null }); }
        else if (str === '/') { slashBuffer = '/'; slashNotice = ''; drawWithSlash(); }
        function cleanup() {
          process.stdin.off('keypress', onKey);
          if (process.stdin.setRawMode) process.stdin.setRawMode(false);
          process.stdout.write('\x1b[?25h\x1b[2J\x1b[H');
        }
      };
      process.stdin.on('keypress', onKey);
    });

    if (!picked || picked.id === 'quit' || !picked.argv) {
      // Plain return so main() can exit naturally.
      return;
    }

    // Two menu items need a follow-up question before they can run:
    // agent (prompt body), browse (URL). Ask once, then dispatch.
    let argv = picked.argv;
    if (picked.promptForBody) {
      const body = await _quickPrompt('prompt: ');
      if (!body) continue; // back to menu
      argv = ['agent', body];
    } else if (picked.promptForUrl) {
      const url = await _quickPrompt('url: ');
      if (!url) continue; // back to menu
      argv = ['browse', url];
    }

    // Dispatch. Errors don't terminate the launcher — they're
    // surfaced as a stderr line and the menu redraws. Lets the
    // user recover from a transient API hiccup without a relaunch.
    try {
      await _dispatchMenuChoice(argv);
    } catch (e) {
      process.stderr.write(`\n  ${accent('✗')} ${e?.message || String(e)}\n`);
    }

    // Pause before re-drawing so the user can read the subcommand's
    // output. `chat` is the special case: its REPL has already kept
    // the user oriented for a long session, and they typed /exit
    // explicitly, so jumping straight back to the menu reads as
    // "ok, done with that conversation, back to the dashboard."
    if (picked.id !== 'chat') {
      process.stdout.write('\n');
      await _quickPrompt(`  ${dim('Press Enter to return to the menu… ')}`);
    }
  }
  } finally {
    // Drop the stdin holds we kept open while the menu was active.
    // Without this, the Node event loop never empties on Quit and
    // the `lazyclaw` process hangs at the shell prompt. Mirrors the
    // cleanup path cmdChat installed in v3.92 for the same reason.
    if (process.stdin.isTTY && process.stdin.setRawMode) {
      try { process.stdin.setRawMode(false); } catch (_) {}
    }
    try { process.stdout.write('\x1b[?25h'); } catch (_) {} // restore cursor
    try { process.stdin.pause(); } catch (_) {}
    try { process.stdin.unref(); } catch (_) {}
  }
  // User reached the end of the launcher session — Quit / Esc / q /
  // /exit / /quit / Ctrl-C, or a failed first-run setup. Skip the
  // natural-exit wait and terminate now: a previously imported
  // subcommand (ollama auto-start probe, registry caches, retry timers,
  // etc.) may have registered an interval or socket that keeps the
  // event loop alive for several seconds. Ctrl-C exits immediately;
  // /exit and Quit should feel the same.
  process.exit(0);
}

async function _quickPrompt(label) {
  const readline = await import('node:readline');
  process.stdout.write('\n');
  // Make sure stdin is in cooked / line-buffered mode for the
  // duration of the prompt — a prior `_arrowMenu` may have left raw
  // mode on, in which case readline.question() never fires its
  // line-event because each byte is delivered as a keypress instead.
  if (process.stdin.isTTY && process.stdin.setRawMode) {
    try { process.stdin.setRawMode(false); } catch (_) {}
  }
  process.stdin.resume();
  if (process.stdin.ref) process.stdin.ref();
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
    case 'orchestrator': {
      const sub = rest.positional[0];
      await cmdOrchestrator(sub, rest.positional.slice(1), rest.flags);
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
