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
  const nodes = await importWorkflow(file);
  if (opts.parallel) {
    // --parallel: schedule by `deps`. No state persistence — `runParallel`
    // is a one-shot DAG run; resume semantics belong to runPersistent.
    // failedAt + executedNodes are derived from results so the JSON
    // shape stays compatible with the sequential path.
    const { runParallel } = await import('./workflow/executor.mjs');
    const r = await runParallel(nodes);
    const executedNodes = r.results.filter(x => x.status === 'success').map(x => x.id);
    console.log(JSON.stringify({
      success: r.success,
      executedNodes,
      failedAt: r.failedAt || null,
      mode: 'parallel',
      error: r.error?.message || null,
    }));
    process.exit(r.success ? 0 : 1);
  }
  const { runPersistent } = await loadEngine();
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
  'run', 'resume',
  'config', 'chat', 'agent',
  'doctor', 'status', 'onboard',
  'sessions', 'skills', 'providers',
  'daemon', 'version', 'completion', 'help',
  'export', 'import',
];

const SUBCOMMAND_SUBS = {
  config:    ['get', 'set', 'list', 'delete', 'unset'],
  sessions:  ['list', 'show', 'clear', 'export'],
  skills:    ['list', 'show', 'install', 'remove'],
  providers: ['list', 'info'],
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
};

// Detailed usage per subcommand for `lazyclaw help <name>`. Kept as flat
// strings so the help output is identical in every terminal.
const HELP_DETAILS = {
  run: 'Usage: lazyclaw run <session-id> <workflow.mjs> [--parallel]\n  Sequential by default; persists state to .workflow-state/<session-id>.json so the run can be resumed.\n  --parallel runs nodes by topological level via runParallel — nodes must declare deps: string[].\n  --parallel does NOT persist state (not resumable; one-shot DAG).',
  resume: 'Usage: lazyclaw resume <session-id> <workflow.mjs>\n  Re-enters a previously persisted run; succeeds nodes are skipped.',
  config: 'Usage: lazyclaw config <get|set|list|delete> [key] [value]\n  Local key-value config at $LAZYCLAW_CONFIG_DIR/config.json (default ~/.lazyclaw).',
  chat: 'Usage: lazyclaw chat [--session <id>] [--skill name1,name2]\n  --session persists turns to <configDir>/sessions/<id>.jsonl across invocations.\n  --skill composes named skills into a system message at the head of the conversation.',
  agent: 'Usage: lazyclaw agent <prompt|-> [--provider X] [--model Y] [--skill list] [--thinking N] [--show-thinking]\n  One-shot non-interactive call. Pass "-" as the prompt to read from stdin.',
  doctor: 'Usage: lazyclaw doctor\n  Validates configuration and registered providers. Exits 0 only when no issues.',
  status: 'Usage: lazyclaw status\n  Provider, model, and masked API key. Never prints the raw key.',
  onboard: 'Usage: lazyclaw onboard [--non-interactive] [--provider X] [--model Y] [--api-key Z]\n  --model accepts the unified "provider/model" string (e.g. anthropic/claude-opus-4-7).',
  sessions: 'Usage: lazyclaw sessions <list|show <id>|clear <id>|export <id>>\n  list — recent sessions by mtime; export — render as Markdown for sharing.',
  skills: 'Usage: lazyclaw skills <list|show <name>|install <name> [--from <path> | --from-url <https://...>]|remove <name>>\n  --from-url fetches over HTTPS only; 1 MiB body cap.',
  providers: 'Usage: lazyclaw providers <list|info <name>>\n  Static metadata: requiresApiKey, defaultModel, suggestedModels, endpoint.',
  daemon: 'Usage: lazyclaw daemon [--port <N>] [--once] [--auth-token <token>] [--allow-origin <origin>] [--rate-limit <N>]\n  Always binds 127.0.0.1. --port 0 picks a random port and prints the URL.\n  --auth-token also reads $LAZYCLAW_AUTH_TOKEN; --allow-origin also reads $LAZYCLAW_ALLOW_ORIGINS.\n  --rate-limit <N> caps each remote IP at N requests / 60 s (token-bucket; smooths bursts).',
  version: 'Usage: lazyclaw version\n  Aliases: --version, -v.',
  completion: 'Usage: lazyclaw completion <bash|zsh>\n  bash:   eval "$(lazyclaw completion bash)"\n  zsh:    lazyclaw completion zsh > "${fpath[1]}/_lazyclaw"',
  export: 'Usage: lazyclaw export [--include-secrets] [--include-sessions] > bundle.json\n  --include-secrets keeps the raw api-key in the bundle (default redacts it).\n  --include-sessions adds full turn content (default keeps metadata only).',
  import: 'Usage: lazyclaw import [--from <path>] [--overwrite-skills] [--no-overwrite-config] [--import-sessions]\n  Reads JSON from stdin (or --from <path>). Sessions are NEVER overwritten.\n  Redacted api-keys (***REDACTED***) are dropped, never written.',
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
    rateLimit,
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

// Flags whose presence is the signal — they don't consume the next arg
// even when one is available. Without this allow-list,
// `lazyclaw run --parallel demo wf.mjs` would set `flags.parallel='demo'`
// and silently lose the session id; the user would only see a
// "missing positional" error after the dispatcher rejected it.
const BOOLEAN_FLAGS = new Set([
  'parallel',
  'once',
  'non-interactive',
  'include-secrets',
  'include-sessions',
  'overwrite-skills',
  'no-overwrite-config',
  'import-sessions',
  'show-thinking',
  'help',         // also handled as a subcommand alias
  'version',
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
      if (!sessionId || !file) { console.error('Usage: lazyclaw run <session-id> <workflow.mjs> [--parallel]'); process.exit(2); }
      await cmdRun(sessionId, file, { dir: rest.flags.dir, parallel: !!rest.flags.parallel });
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
