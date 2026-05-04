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

class RateLimitError extends Error {
  constructor(retryAfterMs, body = '') {
    super(`openai api 429: rate limited (retry-after ${retryAfterMs}ms)`);
    this.name = 'RateLimitError';
    this.code = 'RATE_LIMIT';
    this.status = 429;
    this.retryAfterMs = retryAfterMs;
    this.body = body;
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

function parseRetryAfterMs(headers) {
  let raw = null;
  if (headers && typeof headers.get === 'function') raw = headers.get('retry-after') || headers.get('Retry-After');
  else if (headers) raw = headers['retry-after'] || headers['Retry-After'];
  if (!raw) return 1000;
  const asInt = parseInt(String(raw), 10);
  if (!Number.isNaN(asInt)) return Math.max(0, asInt * 1000);
  const date = Date.parse(String(raw));
  if (!Number.isNaN(date)) return Math.max(0, date - Date.now());
  return 1000;
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
    // Tool-use passthrough mirrors the anthropic provider: opts.tools is an
    // array of OpenAI-shaped tools. opts.toolChoice maps to tool_choice.
    if (Array.isArray(opts.tools) && opts.tools.length > 0) {
      body.tools = opts.tools;
      if (opts.toolChoice) body.tool_choice = opts.toolChoice;
    }
    // Usage capture is opt-in via stream_options. We only request it when
    // the caller provided an onUsage callback — otherwise we'd be paying
    // for an extra response field we'd just throw away. The shape comes
    // back as a top-level `usage` field on a final chunk that has empty
    // choices, right before `[DONE]`.
    if (typeof opts.onUsage === 'function') {
      body.stream_options = { include_usage: true };
    }

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
      if (res.status === 429) throw new RateLimitError(parseRetryAfterMs(res.headers), text || '');
      throw new ApiError(res.status, text || '');
    }

    const decoder = new TextDecoder('utf-8', { fatal: false });
    let buffer = '';
    // Usage accumulator. With stream_options.include_usage, the final
    // pre-[DONE] chunk carries `usage` at top level: {prompt_tokens,
    // completion_tokens, total_tokens}. We collect into a normalized
    // shape that mirrors the anthropic provider's onUsage payload so
    // callers don't have to special-case per provider.
    let usage = null;
    // OpenAI streams tool_calls as deltas with an `index` we use as the
    // accumulation key. Each delta may carry a partial id, name, and/or
    // arguments string. We assemble until the stream signals
    // finish_reason: tool_calls (the final tool_call delta in that choice).
    const toolCallsByIndex = new Map();
    const flushToolCall = (idx) => {
      const tc = toolCallsByIndex.get(idx);
      if (!tc || !tc.function?.name) return;
      toolCallsByIndex.delete(idx);
      if (typeof opts.onToolUse !== 'function') return;
      let input = {};
      try { input = tc.function.arguments ? JSON.parse(tc.function.arguments) : {}; }
      catch { /* malformed → empty + raw */ }
      try {
        opts.onToolUse({
          id: tc.id || null,
          name: tc.function.name,
          input,
          raw: tc.function.arguments || '',
        });
      } catch { /* never let a callback abort the stream */ }
    };
    for await (const chunk of iterateBody(res.body)) {
      if (opts.signal?.aborted) throw new AbortError('aborted mid-stream');
      buffer += typeof chunk === 'string' ? chunk : decoder.decode(chunk, { stream: true });
      let consumed = 0;
      for (const frame of parseSseFrames(buffer)) {
        consumed = frame.nextCursor;
        if (!frame.data) continue;
        if (frame.data === '[DONE]') {
          // Drain any tool calls that haven't been flushed by finish_reason.
          for (const idx of Array.from(toolCallsByIndex.keys())) flushToolCall(idx);
          if (usage && typeof opts.onUsage === 'function') {
            try { opts.onUsage(usage); } catch { /* never let a callback abort */ }
          }
          return;
        }
        try {
          const obj = JSON.parse(frame.data);
          // Usage frame: top-level `usage` (no choices content). Capture
          // and continue — the final stream terminator [DONE] still emits.
          if (obj?.usage && typeof obj.usage === 'object') {
            usage = {
              inputTokens: obj.usage.prompt_tokens ?? null,
              outputTokens: obj.usage.completion_tokens ?? null,
              totalTokens: obj.usage.total_tokens ?? null,
            };
          }
          const choice = obj?.choices?.[0];
          const delta = choice?.delta || {};
          if (delta.content) yield delta.content;
          if (Array.isArray(delta.tool_calls)) {
            for (const td of delta.tool_calls) {
              const idx = td.index ?? 0;
              const cur = toolCallsByIndex.get(idx) || { id: null, function: { name: '', arguments: '' } };
              if (td.id) cur.id = td.id;
              if (td.function?.name) cur.function.name = td.function.name;
              if (typeof td.function?.arguments === 'string') cur.function.arguments += td.function.arguments;
              toolCallsByIndex.set(idx, cur);
            }
          }
          if (choice?.finish_reason === 'tool_calls') {
            for (const idx of Array.from(toolCallsByIndex.keys())) flushToolCall(idx);
          }
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

export { InvalidApiKeyError, ApiError, AbortError, RateLimitError };
