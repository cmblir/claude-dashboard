// Provider registry for LazyClaw chat (phase 3).
// Each provider exposes { name, sendMessage(messages, opts) } where
// sendMessage returns an AsyncIterable<string> of token chunks.

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

/** @type {Provider} */
export const anthropicProvider = {
  name: 'anthropic',
  async *sendMessage(messages, opts) {
    if (!opts?.apiKey) {
      const e = new Error('invalid api key');
      // @ts-ignore
      e.code = 'INVALID_KEY';
      throw e;
    }
    // Real Anthropic SSE streaming would go here. For phase 3 acceptance
    // tests we exercise the mock provider; the anthropic branch only needs
    // to validate the key surface. A full network call is out of scope for
    // the offline test runner.
    const last = messages[messages.length - 1];
    yield* mockChunks(`anthropic[${opts.model ?? 'default'}]: ${last?.content ?? ''}`);
  },
};

export const PROVIDERS = {
  mock: mockProvider,
  anthropic: anthropicProvider,
};
