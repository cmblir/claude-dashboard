// Structural integrity check for cfg.json. Distinct from runtime
// "doctor" checks (provider available, key works) — this is purely
// about shape: types, known providers, rate-card form.
//
// Shared between `lazyclaw config validate` (CLI) and
// `GET /config/validate` (daemon) so both produce bit-for-bit
// identical output.

const KNOWN_KEYS = new Set(['provider', 'model', 'api-key', 'rates']);

/**
 * @param {Record<string, unknown>} cfg
 * @param {Record<string, unknown>} providers   Registered providers map (keys = provider names)
 * @returns {{ ok: boolean, issues: string[], warnings: string[] }}
 */
export function validateConfig(cfg, providers) {
  const issues = [];
  const warnings = [];
  const knownProviderSet = new Set(Object.keys(providers || {}));
  // provider: optional but if present must be in PROVIDERS.
  if (cfg.provider !== undefined) {
    if (typeof cfg.provider !== 'string') {
      issues.push(`config.provider must be a string (got ${typeof cfg.provider})`);
    } else if (!knownProviderSet.has(cfg.provider)) {
      issues.push(`config.provider "${cfg.provider}" is not in registered providers (registered: ${[...knownProviderSet].join(', ')})`);
    }
  }
  if (cfg.model !== undefined && typeof cfg.model !== 'string') {
    issues.push(`config.model must be a string (got ${typeof cfg.model})`);
  }
  if (cfg['api-key'] !== undefined && typeof cfg['api-key'] !== 'string') {
    issues.push(`config['api-key'] must be a string (got ${typeof cfg['api-key']})`);
  }
  if (cfg.rates !== undefined) {
    if (typeof cfg.rates !== 'object' || cfg.rates === null || Array.isArray(cfg.rates)) {
      issues.push(`config.rates must be an object (got ${Array.isArray(cfg.rates) ? 'array' : typeof cfg.rates})`);
    } else {
      for (const key of Object.keys(cfg.rates)) {
        if (!key.includes('/')) {
          issues.push(`config.rates["${key}"]: expected "provider/model" shape (slash required)`);
          continue;
        }
        const card = cfg.rates[key];
        if (!card || typeof card !== 'object') {
          issues.push(`config.rates["${key}"]: value must be an object`);
          continue;
        }
        for (const required of ['inputPer1M', 'outputPer1M']) {
          const v = card[required];
          if (typeof v !== 'number' || !Number.isFinite(v) || v < 0) {
            issues.push(`config.rates["${key}"].${required} must be a non-negative finite number (got ${JSON.stringify(v)})`);
          }
        }
      }
    }
  }
  for (const key of Object.keys(cfg)) {
    if (!KNOWN_KEYS.has(key)) warnings.push(`unknown top-level key: ${key} (allowed: ${[...KNOWN_KEYS].join(', ')})`);
  }
  return { ok: issues.length === 0, issues, warnings };
}
