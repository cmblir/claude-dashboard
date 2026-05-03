#!/usr/bin/env node
/**
 * QQ201 — `/temperature` (alias `/temp`) reads and writes
 * CC_PREFS.ai.temperature without leaving the chat. Numeric arg
 * goes through setPref → /api/prefs/set (debounced 250ms persist),
 * range clamped to [0, 2].
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
await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });
await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS.ai, { timeout: 8000 });

async function slash(line) {
  await page.evaluate((l) => _lcChatSlashCommand(l), line);
  await page.waitForTimeout(180);
}

// 1. /temperature with no arg shows current value
await slash('/temperature');
const showHtml = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/temperature shows current value', /temperature/i.test(showHtml));

// 2. /temperature 1.4 sets value
await page.evaluate(() => {
  window.__tempToasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__tempToasts.push({m, k}); return orig && orig(m, k); };
});
await slash('/temperature 1.4');
const afterSet = await page.evaluate(() => window.CC_PREFS.ai.temperature);
check('/temperature 1.4 sets CC_PREFS.ai.temperature',
  Math.abs(afterSet - 1.4) < 1e-6, `actual=${afterSet}`);
const setToasts = await page.evaluate(() => window.__tempToasts);
check('/temperature 1.4 emits ok toast',
  setToasts.some(t => /1\.4/.test(t.m) && t.k === 'ok'),
  JSON.stringify(setToasts).slice(0, 200));

// 3. /temp alias works
await slash('/temp 0.7');
const afterAlias = await page.evaluate(() => window.CC_PREFS.ai.temperature);
check('/temp alias sets temperature',
  Math.abs(afterAlias - 0.7) < 1e-6, `actual=${afterAlias}`);

// 4. Out-of-range refuses + leaves value untouched
await slash('/temperature 5');
const afterOob = await page.evaluate(() => window.CC_PREFS.ai.temperature);
check('/temperature 5 (out of range) does NOT mutate',
  Math.abs(afterOob - 0.7) < 1e-6, `actual=${afterOob}`);
const oobToasts = await page.evaluate(() => window.__tempToasts);
check('/temperature 5 emits warn toast',
  oobToasts.some(t => /범위 밖|out of range/i.test(t.m)),
  JSON.stringify(oobToasts).slice(-200));

// 5. Persisted to backend (give the 250ms debounce a moment)
await page.waitForTimeout(500);
const persisted = await page.evaluate(async () => {
  const r = await fetch('/api/prefs/get');
  const j = await r.json();
  return (j && j.prefs && j.prefs.ai && j.prefs.ai.temperature);
});
check('temperature persisted to backend',
  Math.abs(persisted - 0.7) < 1e-6, `backend=${persisted}`);

// 6. /help lists it
await slash('/help');
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /temperature', /\/temperature/.test(help));
check('/help lists /temp alias', /\/temp/.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
