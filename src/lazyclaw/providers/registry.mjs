// Provider registry for LazyClaw chat.
// Each provider exposes { name, sendMessage(messages, opts) } where
// sendMessage returns an AsyncIterable<string> of token chunks.
//
// The mock provider is the offline default exercised by phase 3 tests.
// The real Anthropic Messages-API streaming provider lives next door in
// providers/anthropic.mjs and is re-exported here so callers only need to
// know about PROVIDERS.

import { anthropicProvider } from './anthropic.mjs';
import { openaiProvider } from './openai.mjs';
import { ollamaProvider } from './ollama.mjs';
import { geminiProvider } from './gemini.mjs';
import { claudeCliProvider } from './claude_cli.mjs';

/**
 * @typedef {{ role: 'user'|'assistant'|'system', content: string }} ChatMessage
 */

/**
 * @typedef {Object} Provider
 * @property {string} name
 * @property {(messages: ChatMessage[], opts: { apiKey?: string, model?: string }) => AsyncIterable<string>} sendMessage
 */

async function* mockChunks(text, delayMs = 5, signal) {
  for (const ch of text) {
    if (signal?.aborted) {
      const e = new Error('aborted');
      e.code = 'ABORT';
      throw e;
    }
    await new Promise(r => setTimeout(r, delayMs));
    yield ch;
  }
}

/** @type {Provider} */
export const mockProvider = {
  name: 'mock',
  async *sendMessage(messages, opts = {}) {
    const last = messages[messages.length - 1];
    const reply = `mock-reply: ${last?.content ?? ''}`;
    // Honor opts.signal so the chat REPL's Ctrl+C handler (and any
    // other caller) can stop the stream mid-flight. The other concrete
    // providers already do this; the mock should match for symmetry.
    yield* mockChunks(reply, 5, opts.signal);
  },
};

export { anthropicProvider, openaiProvider, ollamaProvider, geminiProvider, claudeCliProvider };

export const PROVIDERS = {
  mock: mockProvider,
  // claude-cli (subscription-backed, no API key) listed before
  // anthropic so first-time onboarding surfaces it as the default.
  'claude-cli': claudeCliProvider,
  anthropic: anthropicProvider,
  openai: openaiProvider,
  gemini: geminiProvider,
  ollama: ollamaProvider,
};

// Static metadata for `lazyclaw providers list/info`. Kept next to PROVIDERS
// so adding a provider in one place can't drift from the list shown to users.
export const PROVIDER_INFO = {
  mock: {
    name: 'mock',
    requiresApiKey: false,
    docs: 'In-process echo provider. Replies "mock-reply: <last user message>". Used for offline tests and demos.',
    defaultModel: null,
    suggestedModels: [],
  },
  'claude-cli': {
    name: 'claude-cli',
    requiresApiKey: false,
    docs: 'Anthropic via the local `claude` CLI (Pro / Max subscription). No API key — auth flows through whatever account `claude` is logged in with. Requires Claude Code installed.',
    endpoint: 'subprocess: claude -p',
    defaultModel: 'claude-opus-4-7',
    suggestedModels: [
      'claude-opus-4-7',
      'claude-sonnet-4-6',
      'claude-haiku-4-5',
      'opus',
      'sonnet',
      'haiku',
    ],
  },
  anthropic: {
    name: 'anthropic',
    requiresApiKey: true,
    keyPrefix: 'sk-ant-',
    docs: 'Anthropic Messages API (pay-per-token, requires sk-ant- key). Supports streaming + extended thinking. For subscription billing, use the `claude-cli` provider instead.',
    endpoint: 'https://api.anthropic.com/v1/messages',
    defaultModel: 'claude-opus-4-7',
    suggestedModels: [
      'claude-opus-4-7',
      'claude-opus-4-6',
      'claude-sonnet-4-6',
      'claude-sonnet-4-5',
      'claude-haiku-4-5',
      'claude-3-5-sonnet-20241022',
      'claude-3-5-haiku-20241022',
    ],
  },
  openai: {
    name: 'openai',
    requiresApiKey: true,
    keyPrefix: 'sk-',
    docs: 'OpenAI Chat Completions API. Streaming via SSE with [DONE] terminator.',
    endpoint: 'https://api.openai.com/v1/chat/completions',
    defaultModel: 'gpt-4.1',
    suggestedModels: [
      'gpt-5',
      'gpt-5-codex',
      'gpt-4.1',
      'gpt-4.1-mini',
      'gpt-4o',
      'gpt-4o-mini',
      'o3-pro',
      'o4-mini',
      'o1',
      'o1-mini',
    ],
  },
  gemini: {
    name: 'gemini',
    requiresApiKey: true,
    docs: 'Google Generative Language API (Gemini). SSE streaming via :streamGenerateContent?alt=sse. Auth via ?key= query param.',
    endpoint: 'https://generativelanguage.googleapis.com/v1/models/{model}:streamGenerateContent',
    defaultModel: 'gemini-2.5-pro',
    suggestedModels: [
      'gemini-2.5-pro',
      'gemini-2.5-flash',
      'gemini-2.0-flash',
      'gemini-2.0-flash-thinking-exp',
      'gemini-1.5-pro',
      'gemini-1.5-flash',
    ],
  },
  ollama: {
    name: 'ollama',
    requiresApiKey: false,
    docs: 'Local Ollama daemon. Streams newline-delimited JSON from /api/chat. No auth — defaults to 127.0.0.1:11434, override via OLLAMA_HOST or opts.baseUrl. Available models depend on what you have pulled locally (`ollama list`).',
    endpoint: 'http://127.0.0.1:11434/api/chat',
    defaultModel: 'llama3.1',
    suggestedModels: [
      'llama3.1',
      'llama3.2',
      'llama3.3',
      'qwen2.5-coder',
      'qwen3.5',
      'mistral',
      'mistral-nemo',
      'codellama',
      'deepseek-coder-v2',
      'phi3',
      'gemma2',
    ],
  },
};

/**
 * Split a unified "provider/model" string (OpenClaw style:
 * "anthropic/claude-opus-4-7"). Also accepts a bare model id and returns
 * provider=null so callers can fall back to a separately-stored provider.
 * @param {string} s
 * @returns {{ provider: string|null, model: string }}
 */
export function parseProviderModel(s) {
  if (!s || typeof s !== 'string') return { provider: null, model: '' };
  const slash = s.indexOf('/');
  if (slash > 0) {
    return { provider: s.slice(0, slash).trim().toLowerCase(), model: s.slice(slash + 1).trim() };
  }
  return { provider: null, model: s.trim() };
}

/**
 * Mask an API key for safe display. Keeps a recognised vendor prefix
 * (sk-ant-, sk-, etc.) and the last 4 characters; masks everything in
 * between. Returns '' when no key is set.
 *
 * The vendor prefix is deliberately conservative: only the well-known
 * ones (sk-ant-, sk-) — anything else yields "****…tail" with no prefix
 * so we never accidentally surface a meaningful chunk of a custom key.
 * @param {string|undefined|null} key
 * @returns {string}
 */
const KNOWN_KEY_PREFIXES = ['sk-ant-', 'sk-or-', 'sk-'];
export function maskApiKey(key) {
  if (!key) return '';
  const s = String(key);
  let prefix = '';
  for (const p of KNOWN_KEY_PREFIXES) {
    if (s.startsWith(p)) { prefix = p; break; }
  }
  const tail = s.length - prefix.length >= 8 ? s.slice(-4) : '';
  const middleLen = Math.max(4, Math.min(12, s.length - prefix.length - tail.length));
  return `${prefix}${'*'.repeat(middleLen)}${tail}`;
}
