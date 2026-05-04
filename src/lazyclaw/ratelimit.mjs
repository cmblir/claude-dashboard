// Token-bucket rate limiter, opt-in for the daemon.
//
// Why token bucket and not fixed-window:
//   - Fixed windows allow burst-double at the boundary (last second of
//     window N + first second of window N+1 → 2× the limit). Token
//     bucket smooths that out.
//   - Bucket math is two arithmetic operations per request (refill +
//     deduct), no per-request log entries to truncate.
//
// Per-key buckets — `key` is whatever the caller wants to scope by.
// The daemon uses the remote IP. A future caller could scope by API
// key prefix or path.
//
// Memory bound: stale buckets are evicted on access (the bucket would
// have refilled to capacity anyway after `capacity / rate` seconds, so
// we lose nothing by dropping it). No background sweep needed.

const DEFAULT_CAPACITY = 60;          // requests
const DEFAULT_REFILL_PER_SEC = 1;     // 60 req/min sustained

export class TokenBucketLimiter {
  /**
   * @param {{ capacity?: number, refillPerSec?: number, now?: () => number }} [opts]
   */
  constructor(opts = {}) {
    this.capacity = opts.capacity ?? DEFAULT_CAPACITY;
    this.refillPerSec = opts.refillPerSec ?? DEFAULT_REFILL_PER_SEC;
    this.now = opts.now ?? (() => Date.now());
    /** @type {Map<string, { tokens: number, last: number }>} */
    this.buckets = new Map();
  }

  /**
   * Try to consume one token from the bucket for `key`.
   * Returns { allowed: boolean, retryAfterMs: number, remaining: number }.
   *
   * When `allowed: false`, `retryAfterMs` is the wall-clock delay until
   * one token would be available — the daemon advertises this in the
   * `Retry-After` header so a polite client backs off correctly.
   */
  consume(key) {
    const t = this.now();
    let b = this.buckets.get(key);
    if (!b) {
      b = { tokens: this.capacity, last: t };
      this.buckets.set(key, b);
    }
    const elapsedSec = Math.max(0, (t - b.last) / 1000);
    b.tokens = Math.min(this.capacity, b.tokens + elapsedSec * this.refillPerSec);
    b.last = t;
    if (b.tokens >= 1) {
      b.tokens -= 1;
      return { allowed: true, retryAfterMs: 0, remaining: Math.floor(b.tokens) };
    }
    const deficit = 1 - b.tokens;
    const retryAfterMs = Math.ceil((deficit / this.refillPerSec) * 1000);
    return { allowed: false, retryAfterMs, remaining: 0 };
  }

  /** Forget the bucket for `key`. Used by tests and by callers that
   *  know a client is gone. Memory is otherwise self-healing. */
  forget(key) {
    this.buckets.delete(key);
  }
}
