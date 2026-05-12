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
import { makeOpenAICompatProvider, fetchOpenAICompatModels } from './openai_compat.mjs';
import { makeOrchestratorProvider } from './orchestrator.mjs';

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
export { makeOpenAICompatProvider, fetchOpenAICompatModels };
export { makeOrchestratorProvider };

// Built-in OpenAI-compatible vendors. Same wire format → one factory call
// each. The picker treats these like first-class providers so users don't
// have to walk through "+ Add a custom endpoint" for the popular ones.
//
// Each entry must define baseUrl + envKey (the env var the chat path
// consults when no api-key is configured) + suggestedModels (curated list
// shown before the user fetches the live /v1/models catalogue).
//
// Adding a new vendor: drop a row here. The PROVIDERS / PROVIDER_INFO loops
// below pick it up automatically.
export const OPENAI_COMPAT_BUILTINS = {
  nim: {
    label: 'NVIDIA NIM',
    baseUrl: 'https://integrate.api.nvidia.com/v1',
    envKey: 'NVIDIA_API_KEY',
    altEnvKeys: ['NIM_API_KEY'],
    keyPrefix: 'nvapi-',
    docs: 'NVIDIA NIM hosted catalogue (Llama 3.x, Nemotron, DeepSeek-R1, Mixtral, Phi-3, Qwen, etc.). Auth: NVIDIA_API_KEY env var or in-app api-key. Endpoint speaks the OpenAI v1 wire format.',
    defaultModel: 'meta/llama-3.1-405b-instruct',
    suggestedModels: [
      'meta/llama-3.1-405b-instruct',
      'meta/llama-3.1-70b-instruct',
      'meta/llama-3.1-8b-instruct',
      'nvidia/llama-3.1-nemotron-70b-instruct',
      'nvidia/nemotron-mini-4b-instruct',
      'nvidia/llama-3.3-nemotron-super-49b-v1',
      'mistralai/mistral-nemo-12b-instruct',
      'mistralai/mixtral-8x22b-instruct-v0.1',
      'microsoft/phi-3-medium-4k-instruct',
      'deepseek-ai/deepseek-r1',
      'qwen/qwen2.5-7b-instruct',
      'qwen/qwen2.5-coder-32b-instruct',
    ],
  },
  openrouter: {
    label: 'OpenRouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    envKey: 'OPENROUTER_API_KEY',
    keyPrefix: 'sk-or-',
    docs: 'OpenRouter unified gateway — 200+ models behind one OpenAI-compatible endpoint. Auth: OPENROUTER_API_KEY env var or in-app api-key. Uses x-title/HTTP-Referer headers for attribution.',
    defaultModel: 'anthropic/claude-3.5-sonnet',
    headers: { 'http-referer': 'https://github.com/cmblir/lazyclaude', 'x-title': 'lazyclaw' },
    suggestedModels: [
      'anthropic/claude-3.5-sonnet',
      'anthropic/claude-3-opus',
      'openai/gpt-4o',
      'openai/gpt-4o-mini',
      'openai/o1-preview',
      'meta-llama/llama-3.1-405b-instruct',
      'meta-llama/llama-3.3-70b-instruct',
      'google/gemini-2.0-flash-exp:free',
      'google/gemini-pro-1.5',
      'deepseek/deepseek-chat',
      'deepseek/deepseek-r1',
      'qwen/qwen-2.5-coder-32b-instruct',
      'mistralai/mistral-large',
    ],
  },
  groq: {
    label: 'Groq',
    baseUrl: 'https://api.groq.com/openai/v1',
    envKey: 'GROQ_API_KEY',
    keyPrefix: 'gsk_',
    docs: 'Groq LPU inference — fastest-token-per-second tier for Llama / Mixtral / Gemma. Auth: GROQ_API_KEY env var or in-app api-key.',
    defaultModel: 'llama-3.3-70b-versatile',
    suggestedModels: [
      'llama-3.3-70b-versatile',
      'llama-3.1-70b-versatile',
      'llama-3.1-8b-instant',
      'llama-3.2-90b-vision-preview',
      'mixtral-8x7b-32768',
      'gemma2-9b-it',
      'qwen-2.5-coder-32b',
      'qwen-2.5-32b',
      'deepseek-r1-distill-llama-70b',
    ],
  },
  together: {
    label: 'Together AI',
    baseUrl: 'https://api.together.xyz/v1',
    envKey: 'TOGETHER_API_KEY',
    docs: 'Together AI hosted inference for open-weight models (Llama, Mixtral, Qwen, DeepSeek, etc.). Auth: TOGETHER_API_KEY env var or in-app api-key.',
    defaultModel: 'meta-llama/Llama-3.3-70B-Instruct-Turbo',
    suggestedModels: [
      'meta-llama/Llama-3.3-70B-Instruct-Turbo',
      'meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo',
      'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo',
      'meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo',
      'mistralai/Mixtral-8x22B-Instruct-v0.1',
      'mistralai/Mixtral-8x7B-Instruct-v0.1',
      'Qwen/Qwen2.5-72B-Instruct-Turbo',
      'Qwen/Qwen2.5-Coder-32B-Instruct',
      'deepseek-ai/DeepSeek-V3',
      'deepseek-ai/DeepSeek-R1',
    ],
  },
  xai: {
    label: 'xAI (Grok)',
    baseUrl: 'https://api.x.ai/v1',
    envKey: 'XAI_API_KEY',
    altEnvKeys: ['GROK_API_KEY'],
    keyPrefix: 'xai-',
    docs: 'xAI Grok models. Auth: XAI_API_KEY env var or in-app api-key.',
    defaultModel: 'grok-2-latest',
    suggestedModels: [
      'grok-2-latest',
      'grok-2-1212',
      'grok-2-vision-1212',
      'grok-beta',
      'grok-vision-beta',
    ],
  },
  deepseek: {
    label: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com/v1',
    envKey: 'DEEPSEEK_API_KEY',
    keyPrefix: 'sk-',
    docs: 'DeepSeek (deepseek-chat / deepseek-reasoner). Auth: DEEPSEEK_API_KEY env var or in-app api-key.',
    defaultModel: 'deepseek-chat',
    suggestedModels: [
      'deepseek-chat',
      'deepseek-reasoner',
      'deepseek-coder',
    ],
  },
  mistral: {
    label: 'Mistral La Plateforme',
    baseUrl: 'https://api.mistral.ai/v1',
    envKey: 'MISTRAL_API_KEY',
    docs: 'Mistral La Plateforme (mistral-large, codestral, ministral, pixtral). Auth: MISTRAL_API_KEY env var or in-app api-key.',
    defaultModel: 'mistral-large-latest',
    suggestedModels: [
      'mistral-large-latest',
      'mistral-small-latest',
      'codestral-latest',
      'ministral-8b-latest',
      'ministral-3b-latest',
      'pixtral-large-latest',
      'open-mistral-nemo',
    ],
  },
  fireworks: {
    label: 'Fireworks AI',
    baseUrl: 'https://api.fireworks.ai/inference/v1',
    envKey: 'FIREWORKS_API_KEY',
    docs: 'Fireworks AI hosted models. Auth: FIREWORKS_API_KEY env var or in-app api-key.',
    defaultModel: 'accounts/fireworks/models/llama-v3p3-70b-instruct',
    suggestedModels: [
      'accounts/fireworks/models/llama-v3p3-70b-instruct',
      'accounts/fireworks/models/llama-v3p1-405b-instruct',
      'accounts/fireworks/models/qwen2p5-coder-32b-instruct',
      'accounts/fireworks/models/deepseek-r1',
      'accounts/fireworks/models/deepseek-v3',
      'accounts/fireworks/models/mixtral-8x22b-instruct',
    ],
  },
};

// Insertion order is the picker order. The list goes first-to-last in
// rough "user-familiar / popular" order so a first-time onboard lands
// the cursor on a vendor most users recognise. v3.99.5 reordered per
// user feedback ("gemini, codex 이런거 먼저 나오게끔").
export const PROVIDERS = {
  // Tier 1 — popular / brand-name vendors users come in looking for.
  gemini: geminiProvider,
  openai: openaiProvider,        // surfaces gpt-5-codex / gpt-5 / o3-pro etc.
  // Tier 2 — Claude. CLI variant first because it's keyless.
  'claude-cli': claudeCliProvider,
  anthropic: anthropicProvider,
  // Tier 3 — popular OpenAI-compatible aggregators / hosted catalogues.
  // Inserted by the loop below from OPENAI_COMPAT_BUILTINS so the order
  // here mirrors that object's insertion order.
  // Tier 4 — local + dev/test.
  ollama: ollamaProvider,
  mock: mockProvider,
};

// Orchestrator — multi-agent dispatcher that composes other providers.
// Registered upfront with no cfg/keyResolver so a bare process can list
// it via `lazyclaw providers list`; `registerOrchestrator(...)` from
// cli.mjs::ensureRegistry wires in the live cfg + auth-key resolver so
// sendMessage can reach env vars / authProfiles / customProviders.
PROVIDERS.orchestrator = makeOrchestratorProvider();

// Wire each OpenAI-compat builtin into PROVIDERS as a callable provider.
// Insertion is between Tier 2 (anthropic) and Tier 4 (ollama) by reordering
// the keys after the loop runs — JS objects honour insertion order and
// cmdLauncher's families helper relies on that for the picker.
{
  const local = { ollama: PROVIDERS.ollama, mock: PROVIDERS.mock };
  delete PROVIDERS.ollama;
  delete PROVIDERS.mock;
  for (const [name, def] of Object.entries(OPENAI_COMPAT_BUILTINS)) {
    PROVIDERS[name] = makeOpenAICompatProvider({
      name,
      baseUrl: def.baseUrl,
      defaultModel: def.defaultModel,
      headers: def.headers,
    });
  }
  PROVIDERS.ollama = local.ollama;
  PROVIDERS.mock = local.mock;
}

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

// Orchestrator metadata. Composes other providers; the planner/workers
// each carry their own keys (or none for claude-cli / ollama / mock),
// so the orchestrator itself reports requiresApiKey: false. The setup
// picker treats it as a CLI/Local-family entry — no api-key prompt.
PROVIDER_INFO.orchestrator = {
  name: 'orchestrator',
  label: 'Orchestrator (multi-agent)',
  requiresApiKey: false,
  docs: 'Orchestrator — decomposes the user message into 2-5 parallel subtasks, dispatches each to a worker provider, then synthesizes the answers. Configure cfg.orchestrator = { planner: "provider:model", workers: ["provider:model", ...], maxSubtasks?: 5 }. Composes any registered provider — Claude / OpenAI / Gemini / NIM / Groq / local Ollama / custom OpenAI-compat endpoints.',
  endpoint: '(composes other providers)',
  defaultModel: 'orchestrator',
  suggestedModels: ['orchestrator'],
  composite: true,
};

// Mirror the OpenAI-compat builtins into PROVIDER_INFO so picker / docs /
// `lazyclaw providers info` see them with the same shape as the hand-written
// entries above.
for (const [name, def] of Object.entries(OPENAI_COMPAT_BUILTINS)) {
  PROVIDER_INFO[name] = {
    name,
    label: def.label,
    requiresApiKey: true,
    keyPrefix: def.keyPrefix,
    envKey: def.envKey,
    altEnvKeys: Array.isArray(def.altEnvKeys) ? def.altEnvKeys.slice() : [],
    docs: def.docs,
    endpoint: `${def.baseUrl}/chat/completions`,
    defaultModel: def.defaultModel,
    suggestedModels: Array.isArray(def.suggestedModels) ? def.suggestedModels.slice() : [],
    builtin: true,
    builtinOpenAICompat: true,
    baseUrl: def.baseUrl,
    headers: def.headers,
  };
}

/**
 * Re-register PROVIDERS.orchestrator with a live config getter + auth-key
 * resolver, so each phase's worker call can pick up env vars / authProfiles
 * / customProviders. Called from cli.mjs::ensureRegistry on every entry
 * — idempotent (overwrites the previous registration in place).
 */
export function registerOrchestrator({ cfgGetter, keyResolver } = {}) {
  PROVIDERS.orchestrator = makeOrchestratorProvider({ cfgGetter, keyResolver });
}

/**
 * Resolve an api-key for a built-in OpenAI-compatible provider from the
 * environment, scanning {envKey} then any {altEnvKeys}. Returns '' when
 * no env var is set so the caller can fall through to its config-based
 * lookup chain.
 */
export function resolveBuiltinEnvKey(provider) {
  const meta = PROVIDER_INFO[provider];
  if (!meta || !meta.builtinOpenAICompat) return '';
  const candidates = [meta.envKey, ...(meta.altEnvKeys || [])].filter(Boolean);
  for (const k of candidates) {
    if (process.env[k]) return process.env[k];
  }
  return '';
}

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
// Reserved provider names — names whose factory is bespoke (not the
// generic OpenAI-compat one) so a custom registration of the same name
// would silently break the wire format. The OpenAI-compat builtins are
// deliberately NOT listed: a user can register `nim` / `openrouter` /
// etc. as a custom entry to override the baseUrl / api-key / headers,
// because both the built-in and the custom go through
// `makeOpenAICompatProvider` — overriding is well-defined.
const RESERVED_PROVIDER_NAMES = new Set([
  'mock', 'claude-cli', 'anthropic', 'openai', 'gemini', 'ollama',
  'orchestrator',
  '__add_custom__', '__custom_model__', '__fetch_models__',
]);

/**
 * Whether the supplied name belongs to one of the OpenAI-compatible
 * builtins. Used by the custom-add interactive flow so it can warn the
 * user that their custom entry will shadow the built-in registration.
 */
export function isBuiltinOpenAICompatName(name) {
  return Object.prototype.hasOwnProperty.call(OPENAI_COMPAT_BUILTINS, String(name || '').trim().toLowerCase());
}

/**
 * Validate a custom provider name. Allowed: lowercase alnum + dash + dot.
 * Returns the trimmed name on success; throws on collision / bad format.
 */
export function validateCustomProviderName(raw) {
  const name = String(raw || '').trim().toLowerCase();
  if (!name) throw new Error('custom provider name is required');
  if (!/^[a-z0-9][a-z0-9._-]{0,31}$/.test(name)) {
    throw new Error('custom provider name must match [a-z0-9][a-z0-9._-]{0,31}');
  }
  if (RESERVED_PROVIDER_NAMES.has(name)) {
    throw new Error(`custom provider name "${name}" is reserved (built-in)`);
  }
  return name;
}

/**
 * Merge user-defined OpenAI-compatible custom providers into PROVIDERS /
 * PROVIDER_INFO. Idempotent — safe to call multiple times; later calls
 * overwrite earlier registrations of the same name. Returns the list of
 * names that were added.
 *
 * Each entry shape (cfg.customProviders is an array):
 *   {
 *     name: 'nim',
 *     baseUrl: 'https://integrate.api.nvidia.com/v1',
 *     apiKey: 'nvapi-...',                  // optional — falls back to opts.apiKey
 *     defaultModel: 'meta/llama-3.1-70b',   // optional
 *     suggestedModels: ['meta/...', ...],   // optional — surfaced in the picker
 *     headers: { 'x-foo': 'bar' },          // optional — extra request headers
 *     docs: 'NVIDIA NIM hosted endpoint',   // optional
 *   }
 */
export function registerCustomProviders(cfg) {
  const list = Array.isArray(cfg?.customProviders) ? cfg.customProviders : [];
  const added = [];
  for (const entry of list) {
    if (!entry || typeof entry !== 'object') continue;
    let name;
    try { name = validateCustomProviderName(entry.name); }
    catch { continue; }
    if (!entry.baseUrl) continue;
    PROVIDERS[name] = makeOpenAICompatProvider({
      name,
      baseUrl: entry.baseUrl,
      apiKey: entry.apiKey,
      defaultModel: entry.defaultModel,
      headers: entry.headers,
    });
    PROVIDER_INFO[name] = {
      name,
      requiresApiKey: !!entry.apiKey || entry.requiresApiKey !== false,
      docs: entry.docs || `Custom OpenAI-compatible endpoint registered via setup. baseUrl=${entry.baseUrl}`,
      endpoint: `${entry.baseUrl}/chat/completions`,
      defaultModel: entry.defaultModel || null,
      suggestedModels: Array.isArray(entry.suggestedModels) ? entry.suggestedModels.slice() : [],
      custom: true,
      baseUrl: entry.baseUrl,
    };
    added.push(name);
  }
  return added;
}

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
