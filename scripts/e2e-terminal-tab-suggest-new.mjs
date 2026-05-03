#!/usr/bin/env node
/**
 * QQ215 — `_lcTermSuggest` Tab autocomplete now covers verbs added
 * in QQ198-QQ211 (whoami, keys, usage, workflows, run, cancel,
 * uptime). Without this, `lazyclaude wh<Tab>` was a silent no-op.
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
await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go('lazyclawTerm'));
await page.waitForSelector('#lcTermInput', { timeout: 8000 });
await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS.ui, { timeout: 8000 });
// Wait for the AFTER-hook health check to finish so its async log
// writes don't race with the candidate-list append below.
await page.waitForFunction(() =>
  /헬스체크 완료/.test((document.getElementById('lcTermLog') || {}).textContent || ''),
  { timeout: 12000 }).catch(() => {});

async function tab(seed) {
  return await page.evaluate((s) => {
    const inp = document.getElementById('lcTermInput');
    inp.value = s;
    inp.focus();
    inp.setSelectionRange(s.length, s.length);
    inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }));
    return inp.value;
  }, seed);
}

// Single-match expansions for the new QQ198-QQ211 verbs.
const cases = [
  ['lazyclaude who',  'lazyclaude whoami'],
  ['lazyclaude key',  'lazyclaude keys'],
  ['lazyclaude upt',  'lazyclaude uptime'],
  ['lz who',          'lz whoami'],
  ['lz upt',          'lz uptime'],
];
for (const [seed, expect] of cases) {
  const got = await tab(seed);
  check(`${seed}<Tab> → ${expect}`, got === expect, `got="${got}"`);
}

// Multi-match: `lazyclaude w` should produce a candidate listing,
// not silently expand. Verify the input stays the same and the log
// gained a candidate-list line.
await page.evaluate(() => {
  const inp = document.getElementById('lcTermInput');
  inp.value = 'lazyclaude w';
  inp.focus();
  inp.setSelectionRange(inp.value.length, inp.value.length);
  inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }));
});
await page.waitForTimeout(150);
const post = await page.evaluate(() => ({
  value: document.getElementById('lcTermInput').value,
  log: (document.getElementById('lcTermLog') || {}).textContent || '',
}));
check('lazyclaude w<Tab> stays multi-candidate (input unchanged)',
  post.value === 'lazyclaude w');
check('multi-candidate listing mentions whoami AND workflows',
  /whoami/.test(post.log) && /workflows/.test(post.log));

// `lazyclaude help w<Tab>` (filter form) — single match: 'help workflow'
const hw = await tab('lazyclaude help w');
check('lazyclaude help w<Tab> → lazyclaude help workflow',
  hw === 'lazyclaude help workflow', `got="${hw}"`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
