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

/**
 * @typedef {{ role: 'user'|'assistant'|'system', content: string }} ChatMessage
 */

/**
 * @typedef {Object} Provider
 * @property {string} name
 * @property {(messages: ChatMessage[], opts: { apiKey?: string, model?: string }) => AsyncIterable<string>} sendMessage
 */

async function* mockChunks(text, delayMs = 5) {
  for (const ch of text) {
    await new Promise(r => setTimeout(r, delayMs));
    yield ch;
  }
}

/** @type {Provider} */
export const mockProvider = {
  name: 'mock',
  async *sendMessage(messages /*, opts */) {
    const last = messages[messages.length - 1];
    const reply = `mock-reply: ${last?.content ?? ''}`;
    yield* mockChunks(reply);
  },
};

export { anthropicProvider, openaiProvider };

export const PROVIDERS = {
  mock: mockProvider,
  anthropic: anthropicProvider,
  openai: openaiProvider,
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
  anthropic: {
    name: 'anthropic',
    requiresApiKey: true,
    keyPrefix: 'sk-ant-',
    docs: 'Anthropic Messages API. Supports streaming + extended thinking.',
    endpoint: 'https://api.anthropic.com/v1/messages',
    defaultModel: 'claude-opus-4-7',
    suggestedModels: ['claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'],
  },
  openai: {
    name: 'openai',
    requiresApiKey: true,
    keyPrefix: 'sk-',
    docs: 'OpenAI Chat Completions API. Streaming via SSE with [DONE] terminator.',
    endpoint: 'https://api.openai.com/v1/chat/completions',
    defaultModel: 'gpt-4.1',
    suggestedModels: ['gpt-4.1', 'gpt-4o', 'gpt-4o-mini'],
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
