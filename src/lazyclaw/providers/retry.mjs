// Opt-in retry wrapper for provider streams.
//
// Why this is a wrapper, not a provider option:
//   - The retry decision is *policy*, not *transport*. Different callers
//     want different retry budgets (a CLI script may want 3, a long-running
//     daemon may want 10 with a max wall clock).
//   - Wrapping keeps the providers themselves simple — they remain pure
//     async iterators over a single attempt.
//
// Strategy:
//   1. We only retry RATE_LIMIT errors that surface *before* any chunk has
//      been yielded. Once the model has started speaking we cannot retry
//      without producing duplicate output, so mid-stream RATE_LIMIT bubbles
//      to the caller unchanged.
//   2. Sleep duration is `min(opts.retryAfterMs, opts.maxBackoffMs)` —
//      we trust `Retry-After` but cap it so a misbehaving provider can't
//      pin us for an hour.
//   3. `attempts` is exclusive of the initial call: `attempts: 3` means
//      one attempt + up to three retries.
//   4. AbortSignal is checked in the sleep so a cancel during the wait
//      doesn't have to wait for the wake-up.

const DEFAULT_ATTEMPTS = 3;
const DEFAULT_MAX_BACKOFF_MS = 60_000;
const ABSOLUTE_MAX_BACKOFF_MS = 5 * 60_000;  // hard ceiling, ignores caller

function clampBackoff(retryAfterMs, max) {
  const ceiling = Math.min(max, ABSOLUTE_MAX_BACKOFF_MS);
  if (!Number.isFinite(retryAfterMs) || retryAfterMs < 0) return ceiling;
  return Math.min(retryAfterMs, ceiling);
}

async function abortableSleep(ms, signal) {
  if (ms <= 0) return;
  if (signal?.aborted) {
    const e = new Error('aborted during retry backoff');
    e.code = 'ABORT';
    throw e;
  }
  await new Promise((resolve, reject) => {
    const t = setTimeout(() => {
      signal?.removeEventListener?.('abort', onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(t);
      const e = new Error('aborted during retry backoff');
      e.code = 'ABORT';
      reject(e);
    }
    signal?.addEventListener?.('abort', onAbort, { once: true });
  });
}

/**
 * Wrap a provider's sendMessage with rate-limit-aware retries.
 *
 * @param {{ name: string, sendMessage: Function }} provider
 * @param {{
 *   attempts?: number,
 *   maxBackoffMs?: number,
 *   onRetry?: (info: { attempt: number, retryAfterMs: number, err: Error }) => void,
 *   sleep?: (ms: number, signal?: AbortSignal) => Promise<void>,
 * }} retryOpts
 */
export function withRateLimitRetry(provider, retryOpts = {}) {
  const attempts = Number.isFinite(retryOpts.attempts) ? retryOpts.attempts : DEFAULT_ATTEMPTS;
  const maxBackoffMs = retryOpts.maxBackoffMs ?? DEFAULT_MAX_BACKOFF_MS;
  const sleep = retryOpts.sleep || abortableSleep;
  const onRetry = retryOpts.onRetry;

  return {
    name: `${provider.name}+retry`,
    async *sendMessage(messages, opts = {}) {
      let lastErr = null;
      for (let attempt = 0; attempt <= attempts; attempt++) {
        let yieldedAny = false;
        try {
          for await (const chunk of provider.sendMessage(messages, opts)) {
            yieldedAny = true;
            yield chunk;
          }
          return;
        } catch (err) {
          lastErr = err;
          // Mid-stream errors cannot be retried: we'd produce duplicate text.
          if (yieldedAny) throw err;
          // Only retry RATE_LIMIT and only if we still have attempts left.
          if (err?.code !== 'RATE_LIMIT' || attempt >= attempts) throw err;
          const wait = clampBackoff(err.retryAfterMs, maxBackoffMs);
          if (typeof onRetry === 'function') {
            try { onRetry({ attempt: attempt + 1, retryAfterMs: wait, err }); } catch { /* swallow */ }
          }
          await sleep(wait, opts.signal);
        }
      }
      // Loop exits only when attempts exhausted; lastErr always set.
      throw lastErr;
    },
  };
}

export { clampBackoff, abortableSleep };
