// Claude subscription provider (no API key).
//
// Spawns the local `claude` CLI binary that ships with Claude Code and
// streams the JSON event format it emits with:
//
//   claude -p "<prompt>" --output-format stream-json
//          --include-partial-messages --verbose [--model opus|sonnet|haiku]
//
// The user's authentication is whatever `claude` is already logged in
// with — i.e. an Anthropic Pro / Max / Team subscription session — so
// no API key is needed and no key shows up in the lazyclaw config.
//
// Why this is a separate provider from ./anthropic.mjs:
// - anthropic.mjs talks to api.anthropic.com directly and requires
//   `sk-ant-` keys (pay-per-token).
// - claude_cli.mjs delegates auth + billing entirely to the `claude`
//   CLI's already-established session (Pro/Max subscription quota).
// Both can coexist; users pick at onboard time.

import { spawn } from 'node:child_process';

class AbortError extends Error {
  constructor(message = 'aborted') {
    super(message);
    this.name = 'AbortError';
    this.code = 'ABORT';
  }
}

class CliMissingError extends Error {
  constructor() {
    super('claude CLI not found in PATH — install Claude Code or use the anthropic provider');
    this.name = 'ClaudeCliMissingError';
    this.code = 'CLI_MISSING';
  }
}

class CliExitError extends Error {
  constructor(code, signal, stderr) {
    super(`claude CLI exited ${code ?? signal}: ${String(stderr).slice(0, 400)}`);
    this.name = 'ClaudeCliExitError';
    this.code = 'CLI_EXIT';
    this.exitCode = code;
    this.signal = signal;
    this.stderr = stderr;
  }
}

// Map canonical Anthropic model ids and friendly aliases to the short
// form `claude --model` actually accepts. The Python dashboard ran into
// the same issue (FF1) — passing the full id silently hangs the CLI.
const _CLI_MODEL_ALIASES = {
  'claude-opus-4-7':      'opus',
  'claude-opus-4-6':      'opus',
  'claude-sonnet-4-6':    'sonnet',
  'claude-sonnet-4-5':    'sonnet',
  'claude-haiku-4-5':     'haiku',
  'claude-haiku-4-5-20251001': 'haiku',
  opus: 'opus',
  sonnet: 'sonnet',
  haiku: 'haiku',
};

function resolveModelAlias(model) {
  if (!model) return '';
  const lower = String(model).toLowerCase();
  return _CLI_MODEL_ALIASES[lower] ?? '';
}

// Flatten the chat-style messages array into a single -p prompt the
// CLI accepts. Mirrors how the dashboard formats Claude turns when it
// has no native multi-turn channel.
function buildPrompt(messages, system) {
  const parts = [];
  if (system) parts.push(`[System instructions: ${system}]`);
  for (const m of messages) {
    if (!m || !m.content) continue;
    if (m.role === 'system' && !system) parts.push(`[System instructions: ${m.content}]`);
    else if (m.role === 'user') parts.push(`User: ${m.content}`);
    else if (m.role === 'assistant') parts.push(`Assistant: ${m.content}`);
  }
  // Trailing "Assistant:" cue so the CLI continues the conversation.
  return parts.length ? parts.join('\n') + '\n\nAssistant:' : '';
}

// Walk the partial-message JSON stream and pull text deltas out. The
// `claude` CLI emits one JSON object per line; the shapes we care about:
//   { type: 'stream_event', event: { type: 'content_block_delta',
//     delta: { type: 'text_delta', text: '...' } } }
//   { type: 'result', usage: {...}, total_cost_usd: ... }
function extractTextDelta(obj) {
  if (!obj || typeof obj !== 'object') return '';
  if (obj.type !== 'stream_event') return '';
  const ev = obj.event || {};
  if (ev.type === 'content_block_delta') {
    const d = ev.delta || {};
    if (d.type === 'text_delta' && typeof d.text === 'string') return d.text;
  }
  return '';
}

export const claudeCliProvider = {
  name: 'claude-cli',
  /**
   * @param {Array<{role:string,content:string}>} messages
   * @param {{
   *   model?: string,
   *   system?: string,
   *   signal?: AbortSignal,
   *   bin?: string,           // override the resolved binary (tests)
   *   cwd?: string,           // working dir for the subprocess
   *   onUsage?: (u: object) => void,
   * }} opts
   */
  async *sendMessage(messages, opts = {}) {
    const bin = opts.bin || 'claude';
    const prompt = buildPrompt(messages, opts.system || messages.find(m => m.role === 'system')?.content);
    if (!prompt) return;

    const args = [
      '-p', prompt,
      '--output-format', 'stream-json',
      '--include-partial-messages',
      '--verbose',
    ];
    const modelAlias = resolveModelAlias(opts.model);
    if (modelAlias) args.push('--model', modelAlias);

    if (opts.signal?.aborted) throw new AbortError('aborted before spawn');

    let proc;
    try {
      proc = spawn(bin, args, {
        cwd: opts.cwd || process.cwd(),
        stdio: ['ignore', 'pipe', 'pipe'],
      });
    } catch (err) {
      // ENOENT means the binary isn't on PATH. Surface a clearer error
      // than the raw spawn failure so onboard / doctor can hint at
      // "install Claude Code or pick a different provider".
      if (err && err.code === 'ENOENT') throw new CliMissingError();
      throw err;
    }

    const onAbort = () => {
      try { proc.kill('SIGTERM'); } catch (_) { /* ignore */ }
    };
    if (opts.signal) opts.signal.addEventListener('abort', onAbort);

    let stderr = '';
    proc.stderr.setEncoding('utf8');
    proc.stderr.on('data', (chunk) => { stderr += chunk; });

    // The stdout protocol is newline-delimited JSON. We buffer partial
    // lines across chunks (shapes can straddle a single read).
    proc.stdout.setEncoding('utf8');
    let buffer = '';
    let exitInfo = null;
    const exitPromise = new Promise((resolve) => {
      proc.on('close', (code, signal) => {
        exitInfo = { code, signal };
        resolve();
      });
    });

    try {
      for await (const chunk of proc.stdout) {
        if (opts.signal?.aborted) throw new AbortError('aborted mid-stream');
        buffer += chunk;
        let nl;
        while ((nl = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, nl).trim();
          buffer = buffer.slice(nl + 1);
          if (!line) continue;
          let obj;
          try { obj = JSON.parse(line); } catch { continue; }
          const text = extractTextDelta(obj);
          if (text) yield text;
          if (obj?.type === 'result') {
            // Last event of a successful run carries usage + cost.
            if (typeof opts.onUsage === 'function') {
              try {
                opts.onUsage({
                  inputTokens:  obj.usage?.input_tokens || 0,
                  outputTokens: obj.usage?.output_tokens || 0,
                  totalCostUsd: obj.total_cost_usd || 0,
                });
              } catch (_) { /* never fail the stream on usage callback */ }
            }
          }
        }
      }
      // Drain trailing buffered line.
      if (buffer.trim()) {
        try {
          const obj = JSON.parse(buffer.trim());
          const text = extractTextDelta(obj);
          if (text) yield text;
        } catch (_) { /* incomplete tail — drop */ }
      }
      await exitPromise;
      if (exitInfo && exitInfo.code !== 0 && !opts.signal?.aborted) {
        throw new CliExitError(exitInfo.code, exitInfo.signal, stderr);
      }
    } finally {
      if (opts.signal) opts.signal.removeEventListener('abort', onAbort);
      // Make sure we don't leave a runaway subprocess if the consumer
      // bailed mid-iteration without explicit abort.
      if (!proc.killed && exitInfo === null) {
        try { proc.kill('SIGTERM'); } catch (_) { /* ignore */ }
      }
    }
  },
};

export { CliMissingError, CliExitError, AbortError, resolveModelAlias, buildPrompt };
