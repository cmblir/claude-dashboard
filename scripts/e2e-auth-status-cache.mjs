#!/usr/bin/env node
/**
 * QQ136 — server-side cache for /api/auth/status. The endpoint runs
 * `claude --version` and `claude auth status` subprocesses (~400ms
 * combined). The status is requested by many tabs (team, projects,
 * memoryManager, openPorts) and can dominate tab-switch lag.
 *
 *   - cold call           : ≥ 200ms (subprocess fan-out)
 *   - cached call         : <  50ms (memo hit)
 *   - team tab cold       : was 871ms, now < 200ms
 *   - team tab warm       : < 100ms
 *
 * Auth state can change when the user logs in/out. The memo
 * auto-invalidates by tracking ~/.claude.json's mtime so a
 * `claude auth login` is reflected without a 30s wait.
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

const t1 = await timed(`http://127.0.0.1:${PORT}/api/auth/status`);
const t2 = await timed(`http://127.0.0.1:${PORT}/api/auth/status`);
const t3 = await timed(`http://127.0.0.1:${PORT}/api/auth/status`);

check('cached auth/status < 50ms (got ' + t2 + 'ms; cold was ' + t1 + 'ms)',
  t2 < 50, `t1=${t1} t2=${t2}`);
check('repeat cache hits stay <50ms',
  t3 < 50, `t3=${t3}`);

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
await page.goto(URL, { waitUntil: 'networkidle' });
await page.waitForSelector('#view h1', { timeout: 5000 });
await page.waitForTimeout(300);

// Warm aiProviders + team (auth status touches both paths).
await page.evaluate(() => window.go('team'));
await page.waitForTimeout(400);

// QQ196 — measure in-browser to exclude Playwright/CDP overhead
// (mirrors QQ194/QQ195).
const switches = [];
for (const tab of ['workflows', 'team', 'workflows', 'team']) {
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
const teamSwitches = switches.filter(s => s.tab === 'team').map(s => s.ms);
const maxTeam = Math.max(...teamSwitches);
check('team warm tab-switch < 200ms (saw ' + teamSwitches.join('/') + ')',
  maxTeam < 200, `max=${maxTeam}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
