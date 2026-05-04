// Response cache decorator for providers — opt-in, in-memory, LRU.
//
// Why a decorator and not a per-provider option:
//   - Same reasoning as withRateLimitRetry / withFallback: caching is
//     *policy* (caller decides how aggressive), not transport. The
//     providers themselves stay pure async iterators over a single call.
//   - A single decorator works across every concrete provider — anthropic,
//     openai, ollama, gemini, mock — without each having to grow its own
//     cache machinery.
//
// Hashing strategy:
//   - JSON-stringify the messages + model + cache-relevant opts and SHA-256
//     it. We use a stable property order (Object.keys.sort) so that
//     `{a:1,b:2}` and `{b:2,a:1}` hash identically — JSON.stringify alone
//     respects insertion order, which would cause spurious misses.
//   - opts that don't affect the response (signal, fetch, onThinking,
//     onToolUse) are excluded from the hash on purpose.
//
// LRU + TTL:
//   - On every hit/miss we touch the entry's recency. Eviction at
//     maxEntries removes the oldest. TTL wins over LRU — an entry
//     past its ttlMs is dropped before being treated as a hit.
//
// Streaming semantics:
//   - On a hit, the wrapper replays the cached chunks via the same
//     async-iterable shape callers expect. We don't re-introduce
//     the original delays — the cache is a perf feature.
//   - On a miss, we stream-through (yield each chunk as it arrives)
//     and accumulate into a buffer. The buffer lands in the cache
//     only when the source iterator completes successfully. Errors
//     and aborts mid-stream do not poison the cache.

import crypto from 'node:crypto';

const DEFAULT_MAX_ENTRIES = 256;
const DEFAULT_TTL_MS = 60 * 60 * 1000;  // 1 hour

function stableStringify(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(stableStringify).join(',') + ']';
  const keys = Object.keys(value).sort();
  return '{' + keys.map(k => JSON.stringify(k) + ':' + stableStringify(value[k])).join(',') + '}';
}

function hashKey(messages, model, opts) {
  const cacheable = {
    messages,
    model: model || null,
    thinking: opts?.thinking || null,
    system: opts?.system || null,
    tools: opts?.tools || null,
    toolChoice: opts?.toolChoice || null,
  };
  return crypto.createHash('sha256').update(stableStringify(cacheable)).digest('hex');
}

/**
 * @typedef {{ chunks: string[], expiresAt: number }} CacheEntry
 */

/**
 * Wrap a provider so identical calls are served from an in-memory cache.
 *
 * @param {{ name: string, sendMessage: Function }} provider
 * @param {{
 *   maxEntries?: number,
 *   ttlMs?: number,
 *   now?: () => number,
 *   onHit?: (info: { keyHash: string, size: number }) => void,
 *   onMiss?: (info: { keyHash: string }) => void,
 * }} [opts]
 */
export function withResponseCache(provider, opts = {}) {
  const maxEntries = opts.maxEntries ?? DEFAULT_MAX_ENTRIES;
  const ttlMs = opts.ttlMs ?? DEFAULT_TTL_MS;
  const now = opts.now ?? (() => Date.now());
  const onHit = typeof opts.onHit === 'function' ? opts.onHit : null;
  const onMiss = typeof opts.onMiss === 'function' ? opts.onMiss : null;
  /** @type {Map<string, CacheEntry>} */
  const cache = new Map();
  let hits = 0;
  let misses = 0;

  const touch = (key, entry) => {
    cache.delete(key);
    cache.set(key, entry);
  };

  return {
    name: `${provider.name}+cache`,
    /** Inspectable counters — useful for benchmarks and dashboards. */
    cacheStats() { return { hits, misses, size: cache.size, maxEntries }; },
    cacheClear() { cache.clear(); hits = 0; misses = 0; },
    async *sendMessage(messages, sendOpts = {}) {
      const key = hashKey(messages, sendOpts.model, sendOpts);
      const cached = cache.get(key);
      if (cached && cached.expiresAt > now()) {
        hits += 1;
        touch(key, cached);
        if (onHit) { try { onHit({ keyHash: key, size: cache.size }); } catch { /* swallow */ } }
        for (const chunk of cached.chunks) yield chunk;
        return;
      }
      misses += 1;
      if (onMiss) { try { onMiss({ keyHash: key }); } catch { /* swallow */ } }
      // Drop expired entry if we found one
      if (cached) cache.delete(key);

      const captured = [];
      try {
        for await (const chunk of provider.sendMessage(messages, sendOpts)) {
          captured.push(chunk);
          yield chunk;
        }
      } catch (err) {
        // Don't poison the cache with partial results — a half-stream is
        // useless to a future caller and would surface as a partial reply.
        throw err;
      }

      // Insert. LRU eviction if we're at the cap.
      while (cache.size >= maxEntries) {
        const oldestKey = cache.keys().next().value;
        if (oldestKey === undefined) break;
        cache.delete(oldestKey);
      }
      cache.set(key, { chunks: captured, expiresAt: now() + ttlMs });
    },
  };
}

export { stableStringify, hashKey };
