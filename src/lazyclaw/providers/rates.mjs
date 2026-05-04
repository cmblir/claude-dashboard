// Token → currency conversion helper.
//
// Why no shipped rate card:
//   - Provider prices change. Hardcoding them sets up the library to
//     silently lie about cost the moment a price moves.
//   - Different teams negotiate different deals (volume contracts,
//     regional pricing, provider-managed proxies). A single global
//     default would be wrong for most users.
//
// Shape:
//   const rates = {
//     'anthropic/claude-opus-4-7': {
//       inputPer1M: 15.00,
//       outputPer1M: 75.00,
//       cacheReadPer1M: 1.50,
//       cacheCreatePer1M: 18.75,
//       currency: 'USD',
//     },
//     'openai/gpt-4.1': { inputPer1M: 2.00, outputPer1M: 8.00, currency: 'USD' },
//   };
//
// `costFromUsage({provider, model, usage}, rates)` returns
//   { cost, currency, breakdown }
// where breakdown shows the per-bucket charge so callers can audit.
//
// Rates are per *million* tokens because that's how every provider
// publishes them — multiplying tokens/1_000_000 keeps the arithmetic
// readable in tests.

/**
 * @param {{ provider: string, model: string, usage: object }} call
 * @param {Record<string, { inputPer1M: number, outputPer1M: number,
 *   cacheReadPer1M?: number, cacheCreatePer1M?: number,
 *   currency?: string }>} rates
 * @returns {{ cost: number, currency: string, breakdown: object } | null}
 */
export function costFromUsage(call, rates) {
  if (!call || !rates) return null;
  const key = `${call.provider}/${call.model}`;
  const r = rates[key];
  if (!r) return null;
  const u = call.usage || {};
  const million = 1_000_000;
  const inputCost = ((Number(u.inputTokens) || 0) / million) * (Number(r.inputPer1M) || 0);
  const outputCost = ((Number(u.outputTokens) || 0) / million) * (Number(r.outputPer1M) || 0);
  // Cache fields only contribute when both rate and usage are present.
  const cacheReadCost = (Number(u.cacheReadInputTokens) > 0 && Number(r.cacheReadPer1M) > 0)
    ? (u.cacheReadInputTokens / million) * r.cacheReadPer1M : 0;
  const cacheCreateCost = (Number(u.cacheCreationInputTokens) > 0 && Number(r.cacheCreatePer1M) > 0)
    ? (u.cacheCreationInputTokens / million) * r.cacheCreatePer1M : 0;
  return {
    cost: round6(inputCost + outputCost + cacheReadCost + cacheCreateCost),
    currency: r.currency || 'USD',
    breakdown: {
      input: round6(inputCost),
      output: round6(outputCost),
      cacheRead: round6(cacheReadCost),
      cacheCreate: round6(cacheCreateCost),
    },
  };
}

function round6(n) {
  // Six decimals → fractions of a cent at sub-USD prices, while still
  // rounding away IEEE-754 noise from the 1/1_000_000 division.
  return Math.round(n * 1_000_000) / 1_000_000;
}

/**
 * Reference shape so callers can copy-paste a starting point and edit
 * with their own current rates. The numbers here are deliberately
 * placeholders (zeros) — see this module's header for why we don't
 * ship real prices.
 */
export const RATE_CARD_SHAPE = {
  'anthropic/claude-opus-4-7': {
    inputPer1M: 0, outputPer1M: 0,
    cacheReadPer1M: 0, cacheCreatePer1M: 0,
    currency: 'USD',
  },
  'openai/gpt-4.1': {
    inputPer1M: 0, outputPer1M: 0,
    currency: 'USD',
  },
};
