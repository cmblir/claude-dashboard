#!/usr/bin/env node
/**
 * v3.69 verification — covers the new terminal verbs and the perf wins.
 *   - lazyclaude providers / inspect / runs / rates handled client-side
 *   - agents tab still renders without console errors after lazy
 *     vis-network deferral
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

await page.evaluate(() => window.go && window.go('lazyclawTerm'));
await page.waitForSelector('#lcTermInput', { timeout: 8000 });
await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS_SCHEMA, { timeout: 8000 }).catch(() => {});
await page.waitForFunction(() => {
  const log = document.getElementById('lcTermLog');
  return !!log && (/헬스체크 완료|Healthcheck complete/.test(log.textContent || '') || log.children.length === 0);
}, { timeout: 12000 }).catch(() => {});

let shellHits = 0;
page.on('request', req => { if (req.url().includes('/api/lazyclaw/term')) shellHits++; });

for (const verb of ['providers', 'runs', 'rates', 'inspect nope-no-such']) {
  await page.evaluate(async (cmd) => {
    document.getElementById('lcTermInput').value = cmd;
    await window._lcTermRun();
  }, `lazyclaude ${verb}`);
  await page.waitForTimeout(400);
}
check('providers/runs/rates/inspect stay client-side', shellHits === 0, `shellHits=${shellHits}`);

const termText = await page.evaluate(() => document.getElementById('lcTermLog').textContent || '');
check('providers output mentions provider id', /claude-cli|claude/.test(termText), 'termText contains provider data');
check('rates header present (or graceful empty)', /rate cards|no rate-cards/.test(termText), 'rates message visible');
check('inspect surfaces not-found message', /workflow not found/.test(termText), 'inspect not-found path');

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
