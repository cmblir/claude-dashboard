#!/usr/bin/env node
/**
 * v3.70 verification:
 *   - testProvider on a missing provider surfaces error_key + translated msg
 */
import { chromium } from 'playwright';

const URL = process.env.URL || `http://127.0.0.1:${process.env.PORT || 8080}/`;
let exitCode = 0;
function check(label, ok, detail) {
  const tag = ok ? '\x1b[32m✅\x1b[0m' : '\x1b[31m❌\x1b[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();

// testProvider surfaces error_key for an unknown provider id.
await page.goto(URL, { waitUntil: 'networkidle' });
const testResult = await page.evaluate(async () => {
  const r = await fetch('/api/ai-providers/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ providerId: 'definitely-not-real' }),
  });
  return await r.json();
});
check('testProvider returns error_key for unknown', testResult.error_key === 'err_provider_unknown',
  `error_key=${testResult.error_key}`);

await browser.close();
console.log(exitCode === 0 ? '\nOK' : '\nFAIL');
process.exit(exitCode);
