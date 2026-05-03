#!/usr/bin/env node
/**
 * QQ148 — Ctrl+L (and Cmd+L) wipes the terminal log buffer in-place
 * (bash convention). Distinct from `lazyclaude reset` in that it
 * doesn't echo a command line; just clears the screen.
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
await page.evaluate(() => window.go && window.go('lazyclawTerm'));
await page.waitForSelector('#lcTermInput', { timeout: 8000 });
await page.waitForTimeout(2200); // let healthcheck finish

const before = await page.evaluate(() => document.querySelectorAll('#lcTermLog > div').length);
check('term log has content from healthcheck', before > 0, `lines=${before}`);

// Focus the input and press Ctrl+L
await page.evaluate(() => document.getElementById('lcTermInput').focus());
await page.keyboard.press('Control+KeyL');
await page.waitForTimeout(150);

const after = await page.evaluate(() => document.querySelectorAll('#lcTermLog > div').length);
const stored = await page.evaluate(() => localStorage.getItem('cc.lazyclawTerm.log'));
check('Ctrl+L wipes the on-screen log', after === 0, `lines=${after}`);
check('Ctrl+L removes localStorage log entry', !stored, `stored=${stored && stored.slice(0, 40)}`);

// Cmd+L should work the same on macOS
// First, repopulate with a quick health check.
await page.evaluate(() => {
  const log = document.getElementById('lcTermLog');
  log.innerHTML = '<div>preexisting</div><div>more</div>';
  localStorage.setItem('cc.lazyclawTerm.log', JSON.stringify([{kind:'cmd',text:'x',ts:0}]));
});
await page.evaluate(() => document.getElementById('lcTermInput').focus());
await page.keyboard.press('Meta+KeyL');
await page.waitForTimeout(150);
const after2 = await page.evaluate(() => document.querySelectorAll('#lcTermLog > div').length);
check('Cmd+L also wipes the log', after2 === 0, `lines=${after2}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
