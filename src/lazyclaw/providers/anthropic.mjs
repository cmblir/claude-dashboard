// Real Anthropic Messages API streaming provider for LazyClaw chat.
//
// Why a separate file from registry.mjs:
//   - registry.mjs hosts the *interface* and the offline mock used by the
//     phase 3 acceptance tests. Real network code belongs next to its own
//     unit tests so the mock surface in registry stays trivial.
//
// SSE parsing strategy:
//   - The Messages API streams `event: ... \n data: ... \n\n` blocks. We
//     read the body as Uint8Array chunks, accumulate into a buffer, split
//     on the blank-line boundary, and yield the `text_delta` payloads.
//   - We tolerate both a Web ReadableStream body and a Node Readable body
//     (so this works in Node 22+ fetch and in Playwright's injected fetch).
//
// Test seam:
//   - opts.fetch overrides globalThis.fetch. The phase 6 test injects a
//     fake fetch returning a hand-rolled SSE ReadableStream. Real code
//     defaults to globalThis.fetch.

const ANTHROPIC_VERSION = '2023-06-01';
const DEFAULT_MAX_TOKENS = 4096;

class InvalidApiKeyError extends Error {
  constructor(message = 'invalid x-api-key') {
    super(message);
    this.name = 'InvalidApiKeyError';
    this.code = 'INVALID_KEY';
  }
}

class AbortError extends Error {
  constructor(message = 'aborted') {
    super(message);
    this.name = 'AbortError';
    this.code = 'ABORT';
  }
}

class ApiError extends Error {
  constructor(status, body) {
    super(`anthropic api ${status}: ${body.slice(0, 200)}`);
    this.name = 'AnthropicApiError';
    this.status = status;
    this.body = body;
  }
}

async function* iterateBody(body) {
  // Web ReadableStream
  if (body && typeof body.getReader === 'function') {
    const reader = body.getReader();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      if (value) yield value;
    }
    return;
  }
  // Node Readable (async iterator)
  if (body && typeof body[Symbol.asyncIterator] === 'function') {
    for await (const chunk of body) yield chunk;
    return;
  }
  // Already a string / buffer (test convenience)
  if (typeof body === 'string') {
    yield new TextEncoder().encode(body);
    return;
  }
  if (body instanceof Uint8Array) {
    yield body;
    return;
  }
  throw new Error('anthropic: response body is not iterable');
}

function* parseSseFrames(buffer) {
  // Yields { event, data } per complete frame; advances the caller's
  // buffer cursor to the byte right after each consumed frame. We
  // implement this as a generator that returns the leftover buffer too.
  let cursor = 0;
  while (true) {
    const sep = buffer.indexOf('\n\n', cursor);
    if (sep < 0) break;
    const frame = buffer.slice(cursor, sep);
    cursor = sep + 2;
    let event = 'message';
    const dataLines = [];
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length > 0) {
      yield { event, data: dataLines.join('\n'), nextCursor: cursor };
    } else {
      yield { event, data: '', nextCursor: cursor };
    }
  }
  return cursor;
}

export const anthropicProvider = {
  name: 'anthropic',
  /**
   * @param {Array<{role:string,content:string}>} messages
   * @param {{apiKey?:string, model?:string, fetch?:typeof fetch, maxTokens?:number, system?:string}} opts
   */
  async *sendMessage(messages, opts = {}) {
    if (!opts.apiKey) throw new InvalidApiKeyError('missing api key');
    const fetchFn = opts.fetch || globalThis.fetch;
    if (!fetchFn) throw new Error('anthropic: no fetch implementation available');

    const model = opts.model || 'claude-opus-4-7';
    const apiMessages = messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => ({ role: m.role, content: String(m.content ?? '') }));

    const body = {
      model,
      max_tokens: opts.maxTokens || DEFAULT_MAX_TOKENS,
      stream: true,
      messages: apiMessages,
    };
    const sys = opts.system || messages.find(m => m.role === 'system')?.content;
    if (sys) body.system = sys;
    // Extended thinking. opts.thinking: { enabled?: boolean, budgetTokens?: number }.
    // The thinking field is opt-in; when budget is set we always treat it as enabled
    // because the API rejects budget without a corresponding type.
    if (opts.thinking && (opts.thinking.enabled || opts.thinking.budgetTokens)) {
      body.thinking = {
        type: 'enabled',
        budget_tokens: opts.thinking.budgetTokens || 1024,
      };
    }

    // Honor opts.signal (AbortSignal) so callers can cancel mid-stream.
    // Both the fetch itself and the body iterator check the signal — fetch
    // for in-flight aborts, the iterator so a cancel between bytes also
    // surfaces immediately rather than waiting for the next chunk.
    if (opts.signal?.aborted) throw new AbortError('aborted before request');

    const res = await fetchFn('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': opts.apiKey,
        'anthropic-version': ANTHROPIC_VERSION,
      },
      body: JSON.stringify(body),
      signal: opts.signal,
    });

    if (!res.ok) {
      const text = typeof res.text === 'function' ? await res.text() : '';
      if (res.status === 401 || res.status === 403) throw new InvalidApiKeyError(text || 'unauthorized');
      throw new ApiError(res.status, text || '');
    }

    // Stream-mode TextDecoder so UTF-8 sequences split across network
    // chunk boundaries decode correctly. Without {stream:true} a multi-byte
    // codepoint that lands across two reads would surface as U+FFFD.
    const decoder = new TextDecoder('utf-8', { fatal: false });
    let buffer = '';
    for await (const chunk of iterateBody(res.body)) {
      if (opts.signal?.aborted) throw new AbortError('aborted mid-stream');
      buffer += typeof chunk === 'string' ? chunk : decoder.decode(chunk, { stream: true });
      let consumed = 0;
      for (const frame of parseSseFrames(buffer)) {
        consumed = frame.nextCursor;
        if (frame.event === 'content_block_delta' && frame.data) {
          try {
            const obj = JSON.parse(frame.data);
            const delta = obj?.delta || {};
            // text_delta → yield as a normal token chunk
            // thinking_delta → route to opts.onThinking when provided; default is to drop
            //                  (keeping the public iterator a stream of *response* text).
            if (delta.type === 'text_delta' && delta.text) {
              yield delta.text;
            } else if (delta.type === 'thinking_delta' && delta.thinking && typeof opts.onThinking === 'function') {
              try { opts.onThinking(delta.thinking); } catch { /* never let a callback abort the stream */ }
            } else if (delta.text) {
              // Backwards-compat: older deltas without a type field still carried a `text`.
              yield delta.text;
            }
          } catch {
            // Ignore malformed frame; the buffer may still contain valid frames.
          }
        } else if (frame.event === 'message_stop') {
          return;
        } else if (frame.event === 'error' && frame.data) {
          let parsed = null;
          try { parsed = JSON.parse(frame.data); } catch { /* keep raw */ }
          const message = parsed?.error?.message || frame.data;
          throw new ApiError(500, message);
        }
      }
      if (consumed > 0) buffer = buffer.slice(consumed);
    }
    // Flush any pending bytes the streaming decoder was still holding.
    const tail = decoder.decode();
    if (tail) buffer += tail;
  },
};

export { InvalidApiKeyError, ApiError, AbortError };
