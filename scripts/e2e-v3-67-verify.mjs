#!/usr/bin/env node
/**
 * v3.67 verification — saveDefaultModel persistence:
 *   - saveDefaultModel hits the right backend endpoint (default persisted)
 *   - the backend flags the chosen model as the provider default
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
const consoleErrs = [];
page.on('console', m => { if (m.type() === 'error') consoleErrs.push(m.text()); });
page.on('pageerror', e => consoleErrs.push('[pageerror] ' + e.message));

await page.goto(URL, { waitUntil: 'networkidle' });

// saveDefaultModel hits /api/ai-providers/default-model (not save-key)
let defaultModelHit = 0;
let saveKeyHit = 0;
await page.route('**/api/ai-providers/default-model', async (route) => { defaultModelHit++; await route.continue(); });
await page.route('**/api/ai-providers/save-key', async (route) => { saveKeyHit++; await route.continue(); });
await page.evaluate(async () => {
  await window.saveDefaultModel('claude-cli', 'claude-sonnet-4-6');
});
await page.waitForTimeout(500);
check('saveDefaultModel routes to default-model endpoint', defaultModelHit === 1 && saveKeyHit === 0,
  `defaultModelHit=${defaultModelHit} saveKeyHit=${saveKeyHit}`);

// Verify backend persisted it
const persisted = await page.evaluate(async () => {
  // bypass the cached version
  const r = await fetch('/api/ai-providers/list?_=' + Date.now());
  const j = await r.json();
  const p = (j.providers || []).find(x => x.id === 'claude-cli');
  return { defaultModel: p && p.defaultModel, isDefault: (p.models || []).some(m => m.isDefault && m.id === 'claude-sonnet-4-6') };
});
check('default model persists + flagged', persisted.defaultModel === 'claude-sonnet-4-6' && persisted.isDefault,
  `defaultModel=${persisted.defaultModel} flag=${persisted.isDefault}`);

if (consoleErrs.length) {
  console.log('\nconsole errors:');
  for (const e of consoleErrs.slice(0, 10)) console.log('  ', e);
}

await browser.close();
console.log(exitCode === 0 ? '\nOK' : '\nFAIL');
process.exit(exitCode);
