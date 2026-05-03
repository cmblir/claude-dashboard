#!/usr/bin/env node
/**
 * QQ115 — openclaw-style settings via the lazyclaw terminal:
 *   lazyclaude get [section[.key]]   → prints current value(s)
 *   lazyclaude set <sec> <key> <val> → updates CC_PREFS + persists
 *
 * Verifies:
 *   1. `lazyclaude get ui` prints the JSON of CC_PREFS.ui.
 *   2. `lazyclaude set ui theme light` flips body.theme-light on.
 *   3. `lazyclaude set ai temperature 1.2` coerces to float, persists,
 *      and CC_PREFS.ai.temperature reflects it.
 *   4. Bad section / bad key paths emit a `⚠` error line.
 *   5. The shell whitelist endpoint is *not* hit for these built-ins.
 */
import { chromium } from 'playwright';

const PORT = process.env.PORT || '19500';
const URL  = `http://127.0.0.1:${PORT}/`;

function check(label, ok, detail) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) process.exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

// Track shell-API hits so we can prove built-ins short-circuit. The
// AFTER hook on the term tab may auto-run a health check, so we only
// count requests fired AFTER the health check completes (see baseline
// reset below).
let termApiHits = 0;
let countingTermHits = false;
page.on('request', req => {
  if (countingTermHits && req.url().includes('/api/lazyclaw/term')) termApiHits++;
});

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawTerm'));
await page.waitForSelector('#lcTermInput', { timeout: 8000 });
// Wait for prefs to be loaded (boot may still be in flight).
await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS.ui && window.CC_PREFS_SCHEMA, { timeout: 8000 });
// AFTER hook may auto-run a health check; wait for it to finish so our
// command lines aren't interleaved with `claude --version` etc.
await page.waitForFunction(() => {
  const el = document.getElementById('lcTermLog');
  if (!el) return false;
  const txt = el.textContent || '';
  return /헬스체크 완료/.test(txt) || el.children.length === 0;
}, { timeout: 12000 }).catch(() => {});
// Start counting only after the health check window has closed.
countingTermHits = true;

async function runCmd(cmd) {
  await page.evaluate((c) => {
    const inp = document.getElementById('lcTermInput');
    inp.value = c;
    return window._lcTermRun();
  }, cmd);
  await page.waitForTimeout(180);
}

async function lastOutput(n = 1) {
  return await page.evaluate((cnt) => {
    const log = document.querySelectorAll('#lcTermLog > div');
    const out = [];
    for (let i = log.length - 1; i >= 0 && out.length < cnt; i--) {
      out.unshift(log[i].textContent || '');
    }
    return out;
  }, n);
}

// 1. lazyclaude get ui → JSON output that mentions the theme key
await runCmd('lazyclaude get ui');
const get1 = (await lastOutput(1)).join('\n');
check('get ui prints JSON of ui section',
  /"theme"/.test(get1));

// 2. set ui theme light flips body class on
await runCmd('lazyclaude set ui theme light');
await page.waitForTimeout(200);
const themeApplied = await page.evaluate(() => document.body.classList.contains('theme-light'));
check('set ui theme light → body has .theme-light',
  themeApplied);

// Restore so subsequent runs don't show the light theme.
await runCmd('lazyclaude set ui theme dark');
await page.waitForTimeout(150);

// 3. set ai temperature 1.2 — coerce float
await runCmd('lazyclaude set ai temperature 1.2');
await page.waitForTimeout(200);
const t = await page.evaluate(() => window.CC_PREFS.ai.temperature);
check('set ai temperature 1.2 → CC_PREFS.ai.temperature === 1.2',
  Math.abs(t - 1.2) < 1e-6, `actual=${t}`);

// 4. Bad section + bad key → error line
await runCmd('lazyclaude set bogus key 1');
const err1 = (await lastOutput(1)).join('\n');
check('bad section emits warning', /⚠/.test(err1));

await runCmd('lazyclaude set ui not_a_real_key 1');
const err2 = (await lastOutput(1)).join('\n');
check('bad key emits warning', /⚠/.test(err2));

// 5. Built-ins must NOT have hit the shell endpoint
check('built-ins short-circuit /api/lazyclaw/term',
  termApiHits === 0, `hits=${termApiHits}`);

// 6. The `lz` short alias also works
await runCmd('lz get ai');
const get2 = (await lastOutput(1)).join('\n');
check('`lz get ai` shorthand works', /"temperature"/.test(get2));

// 7. QQ117 — `lazyclaude help` shows command listing without hitting shell
const hitsBefore = termApiHits;
await runCmd('lazyclaude help');
const helpOut = (await lastOutput(1)).join('\n');
check('lazyclaude help lists get/set/reset',
  /lazyclaude get/.test(helpOut) && /lazyclaude set/.test(helpOut) && /lazyclaude reset/.test(helpOut));
check('help did not hit /api/lazyclaw/term', termApiHits === hitsBefore);

// 8. QQ117 — `lazyclaude reset` wipes the log
await runCmd('lazyclaude reset');
const logSize = await page.evaluate(() => {
  return document.querySelectorAll('#lcTermLog > div').length;
});
// After reset there should be exactly the new "terminal cleared" line +
// the cmd line emitted by _lcTermRun → 2.
check('lazyclaude reset wipes the term log',
  logSize <= 2, `lines=${logSize}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
