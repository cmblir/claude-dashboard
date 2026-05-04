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
  return path.join(os.homedir(), '.lazyclaw', 'config.json');
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

async function cmdRun(sessionId, file, opts = {}) {
  const { runPersistent } = await loadEngine();
  const nodes = await importWorkflow(file);
  const dir = opts.dir || '.workflow-state';
  const r = await runPersistent(nodes, { sessionId, dir, maxRetries: opts.maxRetries ?? 3 });
  console.log(JSON.stringify({ success: r.success, executedNodes: r.executedNodes, failedAt: r.failedAt }));
  process.exit(r.success ? 0 : 1);
}

async function cmdResume(sessionId, file, opts = {}) {
  const { runPersistent, loadState } = await loadEngine();
  const dir = opts.dir || '.workflow-state';
  const prior = loadState(sessionId, dir);
  if (!prior) {
    console.error(`No state for session ${sessionId} in ${dir}`);
    process.exit(2);
  }
  const nodes = await importWorkflow(file);
  const r = await runPersistent(nodes, { sessionId, dir, maxRetries: opts.maxRetries ?? 3 });
  console.log(JSON.stringify({ success: r.success, executedNodes: r.executedNodes, failedAt: r.failedAt, resumed: true }));
  process.exit(r.success ? 0 : 1);
}

function cmdConfigSet(key, value) {
  const cfg = readConfig();
  cfg[key] = value;
  writeConfig(cfg);
  console.log(JSON.stringify({ ok: true, key, value }));
}

function cmdConfigGet(key) {
  const cfg = readConfig();
  if (key) console.log(JSON.stringify({ key, value: cfg[key] ?? null }));
  else console.log(JSON.stringify(cfg));
}

function parseArgs(argv) {
  const out = { positional: [], flags: {} };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const eq = a.indexOf('=');
      if (eq >= 0) out.flags[a.slice(2, eq)] = a.slice(eq + 1);
      else out.flags[a.slice(2)] = argv[++i];
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
      if (!sessionId || !file) { console.error('Usage: lazyclaw run <session-id> <workflow.mjs>'); process.exit(2); }
      await cmdRun(sessionId, file, { dir: rest.flags.dir });
      break;
    }
    case 'resume': {
      const [sessionId, file] = rest.positional;
      if (!sessionId || !file) { console.error('Usage: lazyclaw resume <session-id> <workflow.mjs>'); process.exit(2); }
      await cmdResume(sessionId, file, { dir: rest.flags.dir });
      break;
    }
    case 'config': {
      const sub = rest.positional[0];
      if (sub === 'set') {
        const [, key, ...valueParts] = rest.positional;
        cmdConfigSet(key, valueParts.join(' '));
      } else if (sub === 'get') {
        cmdConfigGet(rest.positional[1]);
      } else {
        console.error('Usage: lazyclaw config set|get <key> [value]'); process.exit(2);
      }
      break;
    }
    case 'chat': {
      // Phase 4 surface — interactive chat. Implemented in phase 3+4.
      const { startChatRepl } = await import('./chat/repl.js')
        .catch(async () => import('./chat/repl.mjs'));
      await startChatRepl();
      break;
    }
    default:
      console.error('Usage: lazyclaw <run|resume|config|chat> ...');
      process.exit(2);
  }
}

main().catch(e => { console.error(e?.stack || e?.message || String(e)); process.exit(1); });
