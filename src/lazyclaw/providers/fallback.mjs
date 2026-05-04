// Auto-fallback wrapper for provider chains.
//
// Why a wrapper, not a registry feature:
//   - Fallback policy is caller-specific. The daemon may want
//     "anthropic → openai" while a CLI script wants "ollama only" with
//     no remote fallback at all.
//   - Wrapping keeps each provider self-contained and testable.
//
// Strategy:
//   - Try providers in order. The first one that yields any chunk
//     "wins" — we forward its stream and never touch the next one.
//   - Fall through happens when the active provider throws BEFORE
//     yielding any chunk. Once a provider has yielded text, we cannot
//     retry without producing duplicate output, so post-yield errors
//     bubble unchanged. This mirrors `withRateLimitRetry`.
//   - Which errors are recoverable is configurable via `opts.shouldFallback`.
//     Default: every error code except 'INVALID_KEY' (auth errors are
//     usually structural — falling back doesn't fix them, it just delays
//     the diagnosis). Callers can pass their own predicate.

const DEFAULT_RECOVERABLE = new Set([
  'RATE_LIMIT',
  'CONNECTION_REFUSED',
  // Generic 5xx surfaces as ApiError without a code; we let the default
  // predicate fall back on them based on err.status >= 500.
]);

function defaultShouldFallback(err) {
  if (!err) return false;
  if (err.code === 'INVALID_KEY' || err.code === 'ABORT') return false;
  if (DEFAULT_RECOVERABLE.has(err.code)) return true;
  // Provider-side ApiError with a 5xx status → fall back.
  if (Number.isFinite(err.status) && err.status >= 500 && err.status < 600) return true;
  // Network-layer fetch failures (no status, no code) → fall back.
  if (!err.code && !err.status) return true;
  return false;
}

/**
 * Wrap a primary provider with a sequence of fallbacks.
 *
 * @param {Array<{ name: string, sendMessage: Function }>} chain
 *   Ordered list — the first provider is the primary. Must have at least one entry.
 * @param {{
 *   shouldFallback?: (err: Error) => boolean,
 *   onFallback?: (info: { from: string, to: string, err: Error }) => void,
 * }} fallbackOpts
 */
export function withFallback(chain, fallbackOpts = {}) {
  if (!Array.isArray(chain) || chain.length === 0) {
    throw new Error('withFallback: chain must contain at least one provider');
  }
  const shouldFallback = fallbackOpts.shouldFallback || defaultShouldFallback;
  const onFallback = fallbackOpts.onFallback;

  return {
    name: `fallback(${chain.map(p => p.name).join('→')})`,
    async *sendMessage(messages, opts = {}) {
      let lastErr = null;
      for (let i = 0; i < chain.length; i++) {
        const prov = chain[i];
        let yieldedAny = false;
        try {
          for await (const chunk of prov.sendMessage(messages, opts)) {
            yieldedAny = true;
            yield chunk;
          }
          return;
        } catch (err) {
          lastErr = err;
          // Cannot fall back once we've started yielding — would duplicate text.
          if (yieldedAny) throw err;
          // Last provider in the chain — re-throw, no more fallbacks.
          if (i === chain.length - 1) throw err;
          // Caller-controlled predicate decides what's worth falling back on.
          if (!shouldFallback(err)) throw err;
          if (typeof onFallback === 'function') {
            try { onFallback({ from: prov.name, to: chain[i + 1].name, err }); }
            catch { /* swallow */ }
          }
        }
      }
      // Loop exits only when all providers have been tried; lastErr is set
      // (we wouldn't have entered the catch otherwise).
      throw lastErr;
    },
  };
}

export { defaultShouldFallback };
