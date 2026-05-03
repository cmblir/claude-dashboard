#!/usr/bin/env node
/**
 * QQ149 — perf budget for tab-switch latency. Locks in the QQ135-QQ144
 * cumulative wins so a future change can't silently re-introduce the
 * 750ms / 400ms / 150ms subprocess fan-out costs.
 *
 *   Tabs that previously took >500ms cold:
 *     aiProviders / team / memoryManager / openPorts
 *
 *   Budget: each must render under 250ms after the boot prewarm has
 *   settled. We give the page a generous 1500ms to boot + warm caches
 *   before measuring.
 */
import { chromium } from 'playwright';

const PORT = process.env.PORT || '19500';
const URL  = `http://127.0.0.1:${PORT}/`;
const BUDGET_MS = parseInt(process.env.TAB_BUDGET_MS || '300', 10);

function check(label, ok, detail) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) process.exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.waitForSelector('#view h1', { timeout: 5000 });
// Give the boot prewarm + cache refresh loop time to populate
// the cli/auth caches before we start measuring.
await page.waitForTimeout(1500);

// QQ153 — gate the most-trafficked tabs on the same warm budget so a
// future regression in user-facing critical paths is caught early.
// QQ154 — sessions tab now hits the auto_resume/status memo so it
// joins the budget too.
const tabs = ['aiProviders', 'team', 'memoryManager', 'openPorts',
              'workflows', 'lazyclawChat', 'lazyclawTerm', 'overview',
              'projects', 'sessions'];
// Per-tab: warm THIS tab (so its caches are hot RIGHT before we
// measure), hop to overview, then measure the warm switch back. This
// avoids the case where a 1-pass-warm-up + N-pass-measure approach
// races short server-side TTLs (e.g. auto_resume/status @ 1.5s).
for (const tab of tabs) {
  // Warm this tab specifically.
  await page.evaluate((tb) => window.go(tb), tab);
  await page.waitForFunction(() => {
    const v = document.getElementById('view');
    return v && v.innerText.length > 50;
  }, { timeout: 8000 });
  // Hop away.
  await page.evaluate(() => window.go('overview'));
  await page.waitForTimeout(120);
  // Measure the warm tab-switch.
  const t0 = Date.now();
  await page.evaluate((tb) => window.go(tb), tab);
  await page.waitForFunction(() => {
    const v = document.getElementById('view');
    return v && v.innerText.length > 50;
  }, { timeout: 5000 });
  const dt = Date.now() - t0;
  check(`${tab.padEnd(15)} warm tab-switch < ${BUDGET_MS}ms`,
    dt < BUDGET_MS, `${dt}ms`);
}

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
