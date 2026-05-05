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
  const { summarizeState, listSessions } = await import('./workflow/summary.mjs');

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
    console.log(JSON.stringify({ dir, status: status || null, sessions }, null, 2));
    process.exit(0);
  }

  const state = loadState(sessionId, dir);
  if (!state) {
    console.error(`No state for session ${sessionId} in ${dir}`);
    process.exit(2);
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
  if (!file) { console.error('Usage: lazyclaw graph <workflow.mjs> [--lr]'); process.exit(2); }
  let nodes;
  try {
    nodes = await importWorkflow(file);
  } catch (e) {
    console.error(`graph: ${e?.message || e}`);
    process.exit(2);
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
  // First emit a node declaration for every id (so isolated nodes
  // still appear in the rendered graph). Then emit edges in dep order.
  // Use a Set to dedupe even though the workflow shouldn't have dupes
  // — defensive against malformed input. Validate-then-graph is the
  // recommended pipeline.
  const declared = new Set();
  const declare = (id) => {
    if (declared.has(id)) return;
    lines.push(`  ${safeId(id)}[${id}]`);
    declared.add(id);
  };
  for (const n of nodes) declare(n.id);
  for (const n of nodes) {
    for (const d of n.deps || []) {
      // Edge: dep → node. Mermaid syntax `a --> b`.
      lines.push(`  ${safeId(d)} --> ${safeId(n.id)}`);
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
    const readline = await import('node:readline');
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    const ask = q => new Promise(resolve => rl.question(q, resolve));
    flags.provider = flags.provider || (await ask('provider [mock|anthropic]: ')).trim();
    flags.model = flags.model || (await ask('model (or "anthropic/claude-opus-4-7"): ')).trim();
    flags['api-key'] = flags['api-key'] || (await ask('api-key (leave blank for mock): ')).trim();
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
  if (cfg.provider && cfg.provider !== 'mock' && !cfg['api-key']) {
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
  // VERSION lives at the repo root. From <repo>/src/lazyclaw/cli.mjs that is two levels up.
  const here = path.dirname(new URL(import.meta.url).pathname);
  const candidates = [
    path.resolve(here, '../../VERSION'),
    path.resolve(here, '../../../VERSION'),
  ];
  for (const c of candidates) {
    try {
      const v = fs.readFileSync(c, 'utf8').trim();
      if (v) return v;
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
];

const SUBCOMMAND_SUBS = {
  config:    ['get', 'set', 'list', 'delete', 'unset', 'path', 'edit'],
  sessions:  ['list', 'show', 'clear', 'export', 'search'],
  skills:    ['list', 'show', 'install', 'remove', 'search'],
  providers: ['list', 'info', 'test'],
  rates:     ['list', 'set', 'delete', 'shape'],
  completion: ['bash', 'zsh'],
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
  inspect: 'Usage: lazyclaw inspect [<session-id>] [--dir <state-dir>] [--status done|resumable|failed|running] [--summary]\n  With no session-id: list every persisted session in the state dir, sorted by recency.\n  --status filters the listing to a single lifecycle bucket.\n  --summary trims per-node detail in single-session mode (matches list-mode shape).\n  With a session-id: print full state. Exit code: 0=resumable, 1=fully done, 2=no state, 3=terminal failure.',
  clear: 'Usage: lazyclaw clear <session-id> [--dir <state-dir>]\n  Delete the state file for <session-id>. Idempotent — exits 0 whether the file existed or not.\n  Refuses sessionIds that resolve outside <state-dir>. Mirrors DELETE /workflows/<id> on the daemon.',
  validate: 'Usage: lazyclaw validate <workflow.mjs>\n  Static check: load + shape + dep + cycle + parallelism estimate.\n  Exit 0 valid · 1 hard failure (issues populated) · 2 file/import error.',
  graph: 'Usage: lazyclaw graph <workflow.mjs> [--lr]\n  Emit the workflow DAG as Mermaid syntax (graph TD by default; --lr for left-right).\n  Output is paste-ready for GitHub markdown / Notion / Obsidian.',
  config: 'Usage: lazyclaw config <get|set|list|delete|path|edit> [key] [value]\n  Local key-value config at $LAZYCLAW_CONFIG_DIR/config.json (default ~/.lazyclaw).\n  `path` prints the file location; `edit` opens it in $EDITOR (or $LAZYCLAW_EDITOR / $VISUAL / vi) and validates JSON on save.',
  chat: 'Usage: lazyclaw chat [--session <id>] [--skill name1,name2]\n  --session persists turns to <configDir>/sessions/<id>.jsonl across invocations.\n  --skill composes named skills into a system message at the head of the conversation.',
  agent: 'Usage: lazyclaw agent <prompt|-> [--provider X] [--model Y] [--skill list] [--thinking N] [--show-thinking] [--usage] [--cost]\n  One-shot non-interactive call. Pass "-" as the prompt to read from stdin.\n  --usage prints normalized {inputTokens, outputTokens, ...} to stderr after the response.\n  --cost adds a cost line on stderr when config.rates has a card for the active provider/model.',
  doctor: 'Usage: lazyclaw doctor\n  Validates configuration and registered providers. Exits 0 only when no issues.',
  status: 'Usage: lazyclaw status\n  Provider, model, and masked API key. Never prints the raw key.',
  onboard: 'Usage: lazyclaw onboard [--non-interactive] [--provider X] [--model Y] [--api-key Z]\n  --model accepts the unified "provider/model" string (e.g. anthropic/claude-opus-4-7).',
  sessions: 'Usage: lazyclaw sessions <list|show <id>|clear <id>|export <id>|search <query> [--regex]>\n  list — recent sessions by mtime; export — render as Markdown for sharing.\n  search — case-insensitive substring (or --regex pattern) match across all session content; returns first excerpt + match count per matching session.',
  skills: 'Usage: lazyclaw skills <list|show <name>|install <name> [--from <path> | --from-url <https://...>]|remove <name>|search <query> [--regex]>\n  --from-url fetches over HTTPS only; 1 MiB body cap.\n  search — case-insensitive substring (or --regex) match across all skill markdown bodies; returns first excerpt + match count per skill.',
  providers: 'Usage: lazyclaw providers <list | info <name> | test <name> [--model X] [--prompt T]>\n  list/info — static metadata: requiresApiKey, defaultModel, suggestedModels, endpoint.\n  test — send a 1-token "ping" through the provider and report ok/error + duration.\n         Useful after configuring an API key to verify it works before relying on it.',
  daemon: 'Usage: lazyclaw daemon [--port <N>] [--once] [--auth-token <token>] [--allow-origin <origin>] [--rate-limit <N>] [--response-cache] [--log <level>] [--shutdown-timeout-ms <N>] [--cost-cap-<currency> <N> ...] [--workflow-state-dir <dir>]\n  Always binds 127.0.0.1. --port 0 picks a random port and prints the URL.\n  --auth-token also reads $LAZYCLAW_AUTH_TOKEN; --allow-origin also reads $LAZYCLAW_ALLOW_ORIGINS.\n  --rate-limit <N> caps each remote IP at N requests / 60 s.\n  --response-cache enables process-scoped memoization; per-request opt-in via body.cache.\n  --log <debug|info|warn|error> emits JSON-line access logs on stderr (also reads $LAZYCLAW_LOG_LEVEL).\n  --shutdown-timeout-ms <N> caps graceful drain on SIGINT/SIGTERM (default 10000). Second signal forces immediate exit.\n  --cost-cap-usd 100 (or any currency code in lowercase) rejects POST /agent + /chat with 402 once cumulative cost reaches the cap.\n  --workflow-state-dir <dir> backs GET /workflows + GET /workflows/<id> (default .workflow-state, also reads $LAZYCLAW_WORKFLOW_STATE_DIR).',
  version: 'Usage: lazyclaw version\n  Aliases: --version, -v.',
  completion: 'Usage: lazyclaw completion <bash|zsh>\n  bash:   eval "$(lazyclaw completion bash)"\n  zsh:    lazyclaw completion zsh > "${fpath[1]}/_lazyclaw"',
  export: 'Usage: lazyclaw export [--include-secrets] [--include-sessions] > bundle.json\n  --include-secrets keeps the raw api-key in the bundle (default redacts it).\n  --include-sessions adds full turn content (default keeps metadata only).',
  import: 'Usage: lazyclaw import [--from <path>] [--overwrite-skills] [--no-overwrite-config] [--import-sessions]\n  Reads JSON from stdin (or --from <path>). Sessions are NEVER overwritten.\n  Redacted api-keys (***REDACTED***) are dropped, never written.',
  rates: 'Usage: lazyclaw rates <list | set <provider/model> --input <N> --output <N> [--cache-read <N>] [--cache-create <N>] [--currency USD] | delete <key> | shape>\n  Rates are per million tokens. costFromUsage uses cfg.rates to compute the cost block in /usage and body.cost.\n  `shape` prints the reference template (zero-filled) you can copy into config.',
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
  let systemPrompt = null;
  if (skillNames.length > 0) {
    try { systemPrompt = skillsMod.composeSystemPrompt(skillNames, path.dirname(configPath())); }
    catch (e) { console.error(`skill error: ${e.message}`); process.exit(2); }
  }

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
  try {
    for await (const chunk of prov.sendMessage(messages, {
      apiKey: cfg['api-key'],
      model: flags.model || cfg.model,
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

async function cmdChat(flags = {}) {
  await ensureRegistry();
  const sessionsMod = await import('./sessions.mjs');
  const skillsMod = await import('./skills.mjs');
  const cfg = readConfig();
  // Mutable in-REPL state: /provider and /model edit these without
  // touching config.json on disk. The CLI flag form (`chat --provider X`)
  // would normally seed these via cfg, but we leave that to a future
  // iteration; today the slash commands work against the on-disk default.
  let activeProvName = cfg.provider || 'mock';
  let activeModel = cfg.model || null;
  const lookupProv = (name) => _registryMod.PROVIDERS[name];
  let prov = lookupProv(activeProvName);
  if (!prov) { console.error(`unknown provider: ${activeProvName}`); process.exit(2); }

  const readline = await import('node:readline');
  const rl = readline.createInterface({ input: process.stdin, terminal: false });

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
  if (skillNames.length > 0 && !messages.some(m => m.role === 'system')) {
    try {
      const sys = skillsMod.composeSystemPrompt(skillNames, cfgDir);
      if (sys) {
        messages.unshift({ role: 'system', content: sys });
        if (sessionId) sessionsMod.appendTurn(sessionId, 'system', sys, cfgDir);
      }
    } catch (e) {
      console.error(`skill error: ${e.message}`);
      process.exit(2);
    }
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

  for await (const line of rl) {
    const text = line.trim();
    if (!text) continue;
    if (text.startsWith('/')) {
      const r = await handleSlash(text);
      if (r === 'EXIT') break;
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
        apiKey: cfg['api-key'],
        model: activeModel,
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
  }
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
      console.log(JSON.stringify(rates, null, 2));
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
    default:
      console.error('Usage: lazyclaw rates <list|set <key>|delete <key>|shape>');
      process.exit(2);
  }
}

async function cmdSkills(sub, positional, flags = {}) {
  const skillsMod = await import('./skills.mjs');
  const cfgDir = path.dirname(configPath());
  switch (sub) {
    case undefined:
    case 'list': {
      const items = skillsMod.listSkills(cfgDir);
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
      // Three forms: --from <path>, --from-url <https://...>, or stdin.
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw skills install <name> [--from <path> | --from-url <https://...>]'); process.exit(2); }
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
      const out = Object.keys(_registryMod.PROVIDERS).map(name => {
        const meta = _registryMod.PROVIDER_INFO[name] || { name, requiresApiKey: false, docs: '' };
        return {
          name,
          requiresApiKey: !!meta.requiresApiKey,
          defaultModel: meta.defaultModel || null,
          suggestedModels: meta.suggestedModels || [],
        };
      });
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
      //   2 — invalid invocation (missing/unknown name)
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw providers test <name> [--model <id>] [--prompt <text>]'); process.exit(2); }
      const provider = _registryMod.PROVIDERS[name];
      if (!provider) {
        console.error(`unknown provider: ${name} (registered: ${Object.keys(_registryMod.PROVIDERS).join(', ')})`);
        process.exit(2);
      }
      const cfg = readConfig();
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
      const items = sessionsMod.listSessions(cfgDir);
      console.log(JSON.stringify(items.map(s => ({ id: s.id, bytes: s.bytes, mtime: new Date(s.mtimeMs).toISOString() })), null, 2));
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
      if (!id) { console.error('Usage: lazyclaw sessions export <id>'); process.exit(2); }
      try { process.stdout.write(sessionsMod.exportMarkdown(id, cfgDir)); }
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
]);

function parseArgs(argv) {
  const out = { positional: [], flags: {} };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
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

async function main() {
  const argv = process.argv.slice(2);
  const cmd = argv[0];
  const rest = parseArgs(argv.slice(1));
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
      await cmdInspect(sessionId, { dir: rest.flags.dir, status: rest.flags.status, summary: !!rest.flags.summary });
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
      await cmdGraph(file, { lr: !!rest.flags.lr });
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
      } else {
        console.error('Usage: lazyclaw config set|get|list|delete|path|edit <key> [value]'); process.exit(2);
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
