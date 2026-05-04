// OpenAI Chat Completions API streaming provider.
//
// Format reference (matches OpenClaw and the OpenAI SDK shape):
//   POST https://api.openai.com/v1/chat/completions
//   Authorization: Bearer <key>
//   {"model": "...", "stream": true, "messages": [...]}
//
// SSE body: each frame is `data: <json>\n\n`. Terminator is the literal
// `data: [DONE]\n\n`. Token text lives at `choices[0].delta.content`.
//
// Test seam mirrors the Anthropic provider: opts.fetch overrides
// globalThis.fetch, opts.maxTokens caps `max_tokens`, opts.system seeds
// a system message.

const DEFAULT_MAX_TOKENS = 4096;

class InvalidApiKeyError extends Error {
  constructor(message = 'invalid OpenAI api key') {
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
    super(`openai api ${status}: ${String(body).slice(0, 200)}`);
    this.name = 'OpenAiApiError';
    this.status = status;
    this.body = body;
  }
}

async function* iterateBody(body) {
  if (body && typeof body.getReader === 'function') {
    const reader = body.getReader();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      if (value) yield value;
    }
    return;
  }
  if (body && typeof body[Symbol.asyncIterator] === 'function') {
    for await (const chunk of body) yield chunk;
    return;
  }
  if (typeof body === 'string') { yield new TextEncoder().encode(body); return; }
  if (body instanceof Uint8Array) { yield body; return; }
  throw new Error('openai: response body is not iterable');
}

function* parseSseFrames(buffer) {
  let cursor = 0;
  while (true) {
    const sep = buffer.indexOf('\n\n', cursor);
    if (sep < 0) break;
    const frame = buffer.slice(cursor, sep);
    cursor = sep + 2;
    const dataLines = [];
    for (const line of frame.split('\n')) {
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length > 0) yield { data: dataLines.join('\n'), nextCursor: cursor };
    else yield { data: '', nextCursor: cursor };
  }
}

export const openaiProvider = {
  name: 'openai',
  /**
   * @param {Array<{role:string,content:string}>} messages
   * @param {{apiKey?:string, model?:string, fetch?:typeof fetch, maxTokens?:number, system?:string}} opts
   */
  async *sendMessage(messages, opts = {}) {
    if (!opts.apiKey) throw new InvalidApiKeyError('missing api key');
    const fetchFn = opts.fetch || globalThis.fetch;
    if (!fetchFn) throw new Error('openai: no fetch implementation available');

    const model = opts.model || 'gpt-4.1';
    const apiMessages = [];
    const sys = opts.system || messages.find(m => m.role === 'system')?.content;
    if (sys) apiMessages.push({ role: 'system', content: String(sys) });
    for (const m of messages) {
      if (m.role === 'user' || m.role === 'assistant') {
        apiMessages.push({ role: m.role, content: String(m.content ?? '') });
      }
    }

    const body = {
      model,
      max_tokens: opts.maxTokens || DEFAULT_MAX_TOKENS,
      stream: true,
      messages: apiMessages,
    };

    if (opts.signal?.aborted) throw new AbortError('aborted before request');
    const res = await fetchFn('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'authorization': `Bearer ${opts.apiKey}`,
      },
      body: JSON.stringify(body),
      signal: opts.signal,
    });

    if (!res.ok) {
      const text = typeof res.text === 'function' ? await res.text() : '';
      if (res.status === 401 || res.status === 403) throw new InvalidApiKeyError(text || 'unauthorized');
      throw new ApiError(res.status, text || '');
    }

    const decoder = new TextDecoder('utf-8', { fatal: false });
    let buffer = '';
    for await (const chunk of iterateBody(res.body)) {
      if (opts.signal?.aborted) throw new AbortError('aborted mid-stream');
      buffer += typeof chunk === 'string' ? chunk : decoder.decode(chunk, { stream: true });
      let consumed = 0;
      for (const frame of parseSseFrames(buffer)) {
        consumed = frame.nextCursor;
        if (!frame.data) continue;
        if (frame.data === '[DONE]') return;
        try {
          const obj = JSON.parse(frame.data);
          const text = obj?.choices?.[0]?.delta?.content;
          if (text) yield text;
        } catch {
          // Ignore malformed frames; keep scanning the rest of the buffer.
        }
      }
      if (consumed > 0) buffer = buffer.slice(consumed);
    }
    const tail = decoder.decode();
    if (tail) buffer += tail;
  },
};

export { InvalidApiKeyError, ApiError, AbortError };
