#!/usr/bin/env node
// Provider streaming throughput benchmark.
//
// What it measures:
//   - Tokens/sec the SSE parser sustains when fed a large in-memory stream.
//   - Total time to consume a worst-case-shape stream where every token is
//     its own SSE frame (the most expensive shape — many small frames =
//     many \n\n boundary searches and many JSON.parse calls).
//   - Memory delta across the run so we can spot accidental O(N²) buffer
//     growth where the unprocessed portion of the buffer would otherwise
//     keep extending into perpetuity.
//
// Usage:
//   node scripts/bench-providers.mjs
//   N=50000 node scripts/bench-providers.mjs        # custom token count
//   PROVIDER=openai node scripts/bench-providers.mjs
//
// Why we ship this script:
//   §9.2 of the engineering directives says "do not optimize without
//   measurement." This is the measurement. Future provider-parser changes
//   should re-run this and post the before/after numbers in their
//   commit message rather than guessing.

import { performance } from 'node:perf_hooks';

const N = parseInt(process.env.N || '20000', 10);
const PROVIDER = (process.env.PROVIDER || 'anthropic').toLowerCase();

function buildAnthropicSse(n) {
  const frames = [];
  for (let i = 0; i < n; i++) {
    frames.push(`event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"x"}}`);
  }
  frames.push('event: message_stop\ndata: {"type":"message_stop"}');
  return frames.join('\n\n') + '\n\n';
}

function buildOpenAiSse(n) {
  const frames = [];
  for (let i = 0; i < n; i++) {
    frames.push(`data: {"choices":[{"delta":{"content":"x"}}]}`);
  }
  frames.push('data: [DONE]');
  return frames.join('\n\n') + '\n\n';
}

function chunkStream(text, chunkSize = 4096) {
  const enc = new TextEncoder();
  const bytes = enc.encode(text);
  return new ReadableStream({
    start(controller) {
      let off = 0;
      while (off < bytes.length) {
        const end = Math.min(off + chunkSize, bytes.length);
        controller.enqueue(bytes.slice(off, end));
        off = end;
      }
      controller.close();
    },
  });
}

const TOTAL_BYTES_HINT = N * 100;
const sse = PROVIDER === 'openai' ? buildOpenAiSse(N) : buildAnthropicSse(N);
const sizeMB = (sse.length / 1_048_576).toFixed(2);

const mod = PROVIDER === 'openai'
  ? await import('../src/lazyclaw/providers/openai.mjs')
  : await import('../src/lazyclaw/providers/anthropic.mjs');
const prov = PROVIDER === 'openai' ? mod.openaiProvider : mod.anthropicProvider;

const fakeFetch = async () => ({
  ok: true,
  status: 200,
  body: chunkStream(sse, 4096),
});

if (global.gc) global.gc();
const memBefore = process.memoryUsage().heapUsed;

const t0 = performance.now();
let count = 0;
for await (const _chunk of prov.sendMessage(
  [{ role: 'user', content: 'hi' }],
  { apiKey: 'sk-x', model: 'm', fetch: fakeFetch },
)) {
  count++;
}
const elapsedMs = performance.now() - t0;

if (global.gc) global.gc();
const memAfter = process.memoryUsage().heapUsed;

const tokensPerSec = count / (elapsedMs / 1000);
const mbPerSec = (sse.length / 1_048_576) / (elapsedMs / 1000);
console.log(JSON.stringify({
  provider: PROVIDER,
  tokensRequested: N,
  tokensReceived: count,
  streamSizeMB: Number(sizeMB),
  elapsedMs: Number(elapsedMs.toFixed(2)),
  tokensPerSec: Number(tokensPerSec.toFixed(0)),
  mbPerSec: Number(mbPerSec.toFixed(2)),
  heapDeltaMB: Number(((memAfter - memBefore) / 1_048_576).toFixed(2)),
}, null, 2));

if (count !== N) {
  console.error(`expected ${N} tokens, got ${count}`);
  process.exit(1);
}
