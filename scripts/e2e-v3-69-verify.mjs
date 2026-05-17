#!/usr/bin/env node
/**
 * v3.69 verification — agents tab still renders without console errors
 * after the lazy vis-network deferral perf win.
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

// Agents tab — must paint without console errors despite vis-network being deferred.
await page.evaluate(() => window.go && window.go('agents'));
await page.waitForTimeout(800);
const agentsAlive = await page.evaluate(() => state.view === 'agents' && !!document.querySelector('#view'));
check('agents tab renders cleanly', agentsAlive && consoleErrs.length === 0,
  `alive=${agentsAlive} consoleErrs=${consoleErrs.length}`);

if (consoleErrs.length) {
  for (const e of consoleErrs.slice(0, 5)) console.log('  ', e);
}

await browser.close();
console.log(exitCode === 0 ? '\nOK' : '\nFAIL');
process.exit(exitCode);
