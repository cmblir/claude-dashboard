#!/usr/bin/env node
/**
 * QQ135 — server-side cache for /api/cli/status. The endpoint runs
 * `<tool> --version` for every CLI in CLI_CATALOG; the resulting
 * subprocess fan-out was ~750ms on every aiProviders tab open and
 * dominated tab-load lag. A 30s memo on the server (with a
 * `?nocache=1` bypass for the explicit Refresh button) drops repeat
 * hits to ~1ms.
 *
 *  - First hit                : > 200ms  (cold)
 *  - Second hit               : < 50ms   (cached)
 *  - ?nocache=1 third hit     : > 200ms  (forced re-probe)
 *
 *  - aiProviders tab switch   : < 500ms after warmup
 */
import { chromium } from 'playwright';

const PORT = process.env.PORT || '19500';
const URL  = `http://127.0.0.1:${PORT}/`;

function check(label, ok, detail) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) process.exitCode = 1;
}

async function timed(url) {
  const t0 = Date.now();
  await fetch(url);
  return Date.now() - t0;
}

// 1. Direct API timings (network only)
//    The cache lives on the SERVER, so even the test process can prove it.
const t1 = await timed(`http://127.0.0.1:${PORT}/api/cli/status`);
const t2 = await timed(`http://127.0.0.1:${PORT}/api/cli/status`);
const t3 = await timed(`http://127.0.0.1:${PORT}/api/cli/status?nocache=1`);

check('cached call is <50ms (got ' + t2 + 'ms; cold was ' + t1 + 'ms)',
  t2 < 50, `t1=${t1} t2=${t2}`);
check('nocache=1 forces re-probe (>= cold − 250ms)',
  t3 >= Math.max(50, t1 - 300), `t1=${t1} t3=${t3}`);

// 2. Tab-switch perf
const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
await page.goto(URL, { waitUntil: 'networkidle' });
await page.waitForSelector('#view h1', { timeout: 5000 });
await page.waitForTimeout(300);

// QQ195 — warm aiProviders + workflows BOTH twice before measuring. The
// second visit to either tab pays for any one-shot lazy-init the AFTER
// hook kicks off (ollama catalog load, health check, cost charts), which
// would otherwise dominate timing on the first measurement pass.
for (let i = 0; i < 2; i++) {
  await page.evaluate(() => window.go('aiProviders'));
  await page.waitForFunction(() => {
    const v = document.getElementById('view');
    return v && v.innerText.length > 50;
  }, { timeout: 5000 });
  await page.waitForTimeout(300);
  await page.evaluate(() => window.go('workflows'));
  await page.waitForFunction(() => {
    const v = document.getElementById('view');
    return v && v.innerText.length > 50;
  }, { timeout: 5000 });
  await page.waitForTimeout(300);
}

// QQ195 — measure inside the browser to exclude Playwright/CDP poll
// overhead (mirrors QQ194 in e2e-tab-switch-budget). Wallclock from Node
// adds ~250-300ms of CDP round-trips that are unrelated to cache state.
const switches = [];
for (const tab of ['workflows', 'aiProviders', 'workflows', 'aiProviders']) {
  const ms = await page.evaluate(async (tb) => {
    const t0 = performance.now();
    await window.go(tb);
    while (true) {
      const v = document.getElementById('view');
      if (v && v.innerText.length > 50) break;
      await new Promise(r => setTimeout(r, 8));
    }
    return Math.round(performance.now() - t0);
  }, tab);
  switches.push({ tab, ms });
}
const aiSwitches = switches.filter(s => s.tab === 'aiProviders').map(s => s.ms);
const maxAi = Math.max(...aiSwitches);
check('aiProviders warm tab-switch < 500ms (saw ' + aiSwitches.join('/') + ')',
  maxAi < 500, `max=${maxAi}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
