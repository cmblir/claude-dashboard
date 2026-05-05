// Structural integrity check for cfg.rates. Distinct from runtime
// "doctor" checks — this is purely about shape: keys in
// "provider/model" form, required fields present, numbers non-
// negative.
//
// Shared between `lazyclaw rates validate` (CLI) and
// `GET /rates/validate` (daemon) so both produce bit-for-bit
// identical output.

/**
 * @param {Record<string, unknown>} rates           cfg.rates map (or undefined)
 * @param {Record<string, unknown>} providers       Registered providers map (keys = provider names)
 * @returns {{ ok: boolean, rateCount: number, issues: string[], warnings: string[] }}
 */
export function validateRates(rates, providers) {
  const issues = [];
  const warnings = [];
  const safeRates = (rates && typeof rates === 'object' && !Array.isArray(rates)) ? rates : {};
  const knownProviders = new Set(Object.keys(providers || {}));
  for (const key of Object.keys(safeRates)) {
    if (!key.includes('/')) {
      issues.push(`key "${key}": expected "provider/model" shape (slash required)`);
      continue;
    }
    const [provider] = key.split('/');
    if (!knownProviders.has(provider)) {
      warnings.push(`key "${key}": provider "${provider}" not in registered providers (registered: ${[...knownProviders].join(', ')})`);
    }
    const card = safeRates[key];
    if (!card || typeof card !== 'object') {
      issues.push(`key "${key}": value must be an object`);
      continue;
    }
    for (const required of ['inputPer1M', 'outputPer1M']) {
      const v = card[required];
      if (typeof v !== 'number' || !Number.isFinite(v) || v < 0) {
        issues.push(`key "${key}": ${required} must be a non-negative finite number (got ${JSON.stringify(v)})`);
      }
    }
    for (const optional of ['cacheReadPer1M', 'cacheCreatePer1M']) {
      if (card[optional] !== undefined) {
        const v = card[optional];
        if (typeof v !== 'number' || !Number.isFinite(v) || v < 0) {
          issues.push(`key "${key}": ${optional} must be a non-negative finite number when set (got ${JSON.stringify(v)})`);
        }
      }
    }
    if (card.currency !== undefined && typeof card.currency !== 'string') {
      issues.push(`key "${key}": currency must be a string (got ${typeof card.currency})`);
    }
  }
  return {
    ok: issues.length === 0,
    rateCount: Object.keys(safeRates).length,
    issues,
    warnings,
  };
}
