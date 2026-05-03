#!/usr/bin/env node
/**
 * QQ2 / QQ12 / QQ17 / QQ106 — lazyclaw terminal:
 *
 * 1. Open the terminal tab.
 * 2. Type a whitelisted command (`git status -s`) and run.
 * 3. Verify the log shows the command line + durationMs marker.
 * 4. Tab autocomplete: prefix `git stat` → expect a single
 *    completion to `git status` or candidate listing.
 * 5. QQ106 Esc clears input.
 */
import { chromium } from 'playwright';

const PORT = process.env.PORT || '19500';
const URL  = `http://127.0.0.1:${PORT}/`;

function check(label, ok) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}`);
  if (!ok) process.exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawTerm'));
await page.waitForSelector('#lcTermInput', { timeout: 8000 });

// Wait for the QQ4 auto health-check to complete so it doesn't mix
// into our user-driven command output.
await page.waitForFunction(() => {
  const log = document.getElementById('lcTermLog');
  return log && /헬스체크 완료|health.check.*done/i.test(log.textContent);
}, { timeout: 8000 }).catch(() => {});
const beforeText = await page.evaluate(() => document.getElementById('lcTermLog').textContent);

// Step 1: type a whitelisted command and Enter — pick one the
// health-check does NOT run (`uname -a`).
await page.click('#lcTermInput');
await page.keyboard.type('uname -a');
await page.keyboard.press('Enter');

// Wait for both the command echo AND the response with durationMs marker.
await page.waitForFunction((seed) => {
  const cur = document.getElementById('lcTermLog').textContent;
  const newPart = cur.slice(seed.length);
  return /uname -a/.test(newPart) && /\(\d+ms\)/.test(newPart);
}, beforeText, { timeout: 8000 });

const runOut = await page.evaluate((seed) => {
  const text = document.getElementById('lcTermLog').textContent;
  const newPart = text.slice(seed.length);
  return {
    newPart,
    hasCmd: /uname -a/.test(newPart),
    hasDur: /\(\d+ms\)/.test(newPart),
  };
}, beforeText);
check('terminal echoed the command', runOut.hasCmd);
if (!runOut.hasDur) {
  console.error('  newPart:', JSON.stringify(runOut.newPart).slice(0, 240));
}
check('QQ17 durationMs marker present in output', runOut.hasDur);

// Step 2: Tab autocomplete with a unique prefix.
await page.click('#lcTermInput');
await page.fill('#lcTermInput', 'lazyclaude sta');
await page.keyboard.press('Tab');
await page.waitForTimeout(120);
const completed = await page.$eval('#lcTermInput', el => el.value);
check('Tab completes "lazyclaude sta" → "lazyclaude status"',
  completed === 'lazyclaude status');

// Step 3: QQ106 Esc clears input.
await page.fill('#lcTermInput', 'something here');
await page.evaluate(() => document.getElementById('lcTermInput').focus());
await page.keyboard.press('Escape');
await page.waitForTimeout(80);
const afterEsc = await page.$eval('#lcTermInput', el => el.value);
check('Esc clears terminal input', afterEsc === '');

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
