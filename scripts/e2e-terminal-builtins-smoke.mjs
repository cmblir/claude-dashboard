#!/usr/bin/env node
/**
 * QQ179 — companion to QQ178: comprehensive smoke for every terminal
 * `lazyclaude <verb>` built-in. Runs each verb once with safe args,
 * asserts the parser routes to a builtin (no shell hit) and the
 * terminal DOM is intact.
 */
import { chromium } from 'playwright';

const PORT = process.env.PORT || '19500';
const URL  = `http://127.0.0.1:${PORT}/`;

function check(label, ok, detail) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) process.exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

let shellHits = 0;
let countShell = false;
page.on('request', req => {
  if (countShell && req.url().includes('/api/lazyclaw/term')) shellHits++;
});

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawTerm'));
await page.waitForSelector('#lcTermInput', { timeout: 8000 });
// Wait for any auto-fired health-check + cache settling.
await page.waitForFunction(() => {
  const log = document.getElementById('lcTermLog');
  if (!log) return false;
  const t = log.textContent || '';
  return /헬스체크 완료/.test(t) || log.children.length === 0;
}, { timeout: 12000 }).catch(() => {});
await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS_SCHEMA, { timeout: 8000 });
countShell = true;

// Each case: { line, label, expectShellHit }. Most builtins must NOT
// hit the shell endpoint; the few that fall through (none here) would
// set expectShellHit = true.
const cases = [
  ['lazyclaude help',            'help'],
  ['lazyclaude --help',          '--help'],
  ['lazyclaude version',         'version'],
  ['lazyclaude --version',       '--version'],
  ['lazyclaude status',          'status'],
  ['lazyclaude tabs',             'tabs'],
  ['lazyclaude get',             'get'],
  ['lazyclaude get ui',          'get section'],
  ['lazyclaude get ui.theme',    'get key'],
  ['lz help',                    'lz help'],
  ['lz version',                 'lz version'],
  ['lz status',                  'lz status'],
  ['lz tabs',                    'lz tabs'],
  ['lz get ui',                  'lz get section'],
];

for (const [line, label] of cases) {
  shellHits = 0;
  await page.evaluate((l) => {
    const inp = document.getElementById('lcTermInput');
    inp.value = l;
    return window._lcTermRun();
  }, line);
  await page.waitForTimeout(150);
  const alive = await page.evaluate(() => !!document.getElementById('lcTermInput'));
  check(`${label.padEnd(14)} stays client-side, DOM alive`,
    shellHits === 0 && alive,
    `shellHits=${shellHits} alive=${alive}`);
}

// Round-trip: set a pref via terminal then verify CC_PREFS reflects it.
await page.evaluate(() => {
  const inp = document.getElementById('lcTermInput');
  inp.value = 'lazyclaude set ui density compact';
  return window._lcTermRun();
});
await page.waitForTimeout(150);
const density = await page.evaluate(() => window.CC_PREFS.ui.density);
check('lazyclaude set persists into CC_PREFS', density === 'compact',
  `density=${density}`);

// Reset to default so the test is idempotent
await page.evaluate(() => {
  const inp = document.getElementById('lcTermInput');
  inp.value = 'lazyclaude set ui density comfortable';
  return window._lcTermRun();
});

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
