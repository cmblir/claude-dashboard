#!/usr/bin/env node
/**
 * QQ217 — `lazyclaude refresh` (alias `reload`) terminal verb.
 * Parity with chat /refresh (QQ216): busts the client-side _apiCache
 * Map. Doesn't reload the page.
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
await page.waitForFunction(() =>
  /헬스체크 완료/.test((document.getElementById('lcTermLog') || {}).textContent || ''),
  { timeout: 12000 }).catch(() => {});

async function run(cmd) {
  await page.evaluate((c) => {
    const inp = document.getElementById('lcTermInput');
    inp.value = c;
    return window._lcTermRun();
  }, cmd);
  await page.waitForTimeout(280);
}
const fullLog = async () => await page.evaluate(() => (document.getElementById('lcTermLog') || {}).textContent || '');

// 1. Prime the cache via something that hits cachedApi (workflows list)
await run('lazyclaude workflows');

// 2. lazyclaude refresh prints "cache cleared (N entries)"
await run('lazyclaude refresh');
const out = await fullLog();
check('lazyclaude refresh prints cache cleared',
  /cache cleared \(\d+ entries\)/.test(out));

// 3. lazyclaude reload alias works
await run('lazyclaude reload');
const out2 = await fullLog();
check('lazyclaude reload also prints cache cleared',
  (out2.match(/cache cleared/g) || []).length >= 2);

// 4. lazyclaude help lists refresh
await run('lazyclaude reset');
await run('lazyclaude help');
const helpOut = await fullLog();
check('lazyclaude help lists refresh', /lazyclaude refresh/.test(helpOut));

// 5. Tab-suggest covers `lazyclaude ref`
await page.evaluate(() => {
  const inp = document.getElementById('lcTermInput');
  inp.value = 'lazyclaude ref';
  inp.focus();
  inp.setSelectionRange(inp.value.length, inp.value.length);
  inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }));
});
await page.waitForTimeout(80);
const post = await page.evaluate(() => document.getElementById('lcTermInput').value);
check('lazyclaude ref<Tab> → lazyclaude refresh',
  post === 'lazyclaude refresh', `got="${post}"`);

// 6. Typo did-you-mean
await run('lazyclaude refesh');
const typoOut = await fullLog();
check('lazyclaude refesh → suggests refresh',
  /lazyclaude refresh/.test(typoOut));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
