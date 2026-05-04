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
  try {
    for await (const chunk of prov.sendMessage(messages, {
      apiKey: cfg['api-key'],
      model: flags.model || cfg.model,
      thinking: thinkingBudget > 0 ? { enabled: true, budgetTokens: thinkingBudget } : undefined,
      onThinking: showThinking ? t => process.stderr.write(t) : undefined,
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
  const provName = cfg.provider || 'mock';
  const prov = _registryMod.PROVIDERS[provName];
  if (!prov) { console.error(`unknown provider: ${provName}`); process.exit(2); }

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
          provider: cfg.provider || null,
          model: cfg.model || null,
          keyMasked: _registryMod.maskApiKey(cfg['api-key']),
          messageCount: messages.length,
        };
        process.stdout.write(JSON.stringify(out) + '\n');
        return true;
      }
      case '/new':
      case '/reset': {
        messages = [];
        charsSent = 0;
        if (sessionId) {
          const sm = await import('./sessions.mjs');
          sm.resetSession(sessionId, cfgDir);
        }
        process.stdout.write('cleared — new conversation\n');
        return true;
      }
      case '/usage': {
        process.stdout.write(JSON.stringify({ messageCount: messages.length, charsSent }) + '\n');
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
    try {
      for await (const chunk of prov.sendMessage(messages, { apiKey: cfg['api-key'], model: cfg.model })) {
        process.stdout.write(chunk);
        acc += chunk;
      }
      process.stdout.write('\n');
      messages.push({ role: 'assistant', content: acc });
      persistTurn('assistant', acc);
    } catch (err) {
      process.stdout.write(`error: ${err?.message || String(err)}\n`);
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
  const cfgDir = path.dirname(configPath());
  const d = await startDaemon({
    port: Number.isFinite(port) ? port : 0,
    once,
    readConfig,
    sessionsDirGetter: () => cfgDir,
    sessionsMod,
    version: () => readVersionFromRepo(),
    authToken: authToken || undefined,
    allowedOrigins,
  });
  // Print the bound port immediately so test/script callers can pick it up
  // even when we asked for port 0. Indicate auth presence (not the token)
  // and the allowed-origin count (not the values, just whether browser
  // access has been opened).
  process.stdout.write(JSON.stringify({
    ok: true, url: `http://127.0.0.1:${d.port}`, port: d.port, once,
    auth: !!authToken,
    allowedOriginCount: allowedOrigins.length,
  }) + '\n');
  if (!once) {
    // Forward SIGINT/SIGTERM to a clean shutdown.
    const shutdown = async () => { try { await d.close(); } catch {} process.exit(0); };
    process.on('SIGINT', shutdown);
    process.on('SIGTERM', shutdown);
  } else {
    // In once mode, exit naturally after the server closes.
    d.server.on('close', () => process.exit(0));
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
      // Two forms: --from <path>, or read content from stdin.
      const name = positional[0];
      if (!name) { console.error('Usage: lazyclaw skills install <name> [--from <path>]'); process.exit(2); }
      let content;
      if (flags.from) {
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
    default:
      console.error('Usage: lazyclaw skills <list|show <name>|install <name> [--from path]|remove <name>>');
      process.exit(2);
  }
}

async function cmdProviders(sub, positional) {
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
    default:
      console.error('Usage: lazyclaw providers <list|info <name>>');
      process.exit(2);
  }
}

async function cmdSessions(sub, positional) {
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
    default:
      console.error('Usage: lazyclaw sessions <list|show <id>|clear <id>|export <id>>');
      process.exit(2);
  }
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
      if (eq >= 0) {
        out.flags[a.slice(2, eq)] = a.slice(eq + 1);
      } else {
        const next = argv[i + 1];
        if (next === undefined || next.startsWith('--')) {
          // bare boolean flag
          out.flags[a.slice(2)] = true;
        } else {
          out.flags[a.slice(2)] = next;
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
      } else {
        console.error('Usage: lazyclaw config set|get|list|delete <key> [value]'); process.exit(2);
      }
      break;
    }
    case 'chat': {
      await cmdChat(rest.flags);
      break;
    }
    case 'sessions': {
      const sub = rest.positional[0];
      await cmdSessions(sub, rest.positional.slice(1));
      break;
    }
    case 'providers': {
      const sub = rest.positional[0];
      await cmdProviders(sub, rest.positional.slice(1));
      break;
    }
    case 'skills': {
      const sub = rest.positional[0];
      await cmdSkills(sub, rest.positional.slice(1), rest.flags);
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
    default:
      console.error('Usage: lazyclaw <run|resume|config|chat|agent|doctor|status|onboard|sessions|providers|skills|daemon|version> ...');
      process.exit(2);
  }
}

main().catch(e => { console.error(e?.stack || e?.message || String(e)); process.exit(1); });
