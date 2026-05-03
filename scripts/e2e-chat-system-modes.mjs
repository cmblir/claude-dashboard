#!/usr/bin/env node
/**
 * QQ175 — `/system` is now three-modal:
 *   /system          → SHOW current prompt (was: silent clear)
 *   /system <text>   → set
 *   /system clear    → explicit clear
 *
 * Previously a bare `/system` silently wiped the prompt — easy
 * mistake for users who expected "show current".
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
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });
await page.waitForTimeout(500);

const assignee = await page.evaluate(() => document.getElementById('lcChatAssignee').value);
const storeKey = 'cc.lazyclawChat.sys.' + assignee;

await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  _lcSaveHistory(_lcCurrentId(), []);
  _lcChatRender();
});

// 1. /system <text> sets
await page.evaluate(() => _lcChatSlashCommand('/system Be terse.'));
await page.waitForTimeout(150);
const set = await page.evaluate((k) => localStorage.getItem(k), storeKey);
check('/system <text> persists prompt', set === 'Be terse.', `got=${JSON.stringify(set)}`);

// 2. Bare /system shows current — does NOT mutate.
await page.evaluate(() => _lcChatSlashCommand('/system'));
await page.waitForTimeout(150);
const stillSet = await page.evaluate((k) => localStorage.getItem(k), storeKey);
check('bare /system does NOT clear (was the QQ175 bug)',
  stillSet === 'Be terse.', `got=${JSON.stringify(stillSet)}`);
const log = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('bare /system displays current prompt inline',
  /Be terse\./.test(log));

// 3. /system clear explicitly wipes.
await page.evaluate(() => _lcChatSlashCommand('/system clear'));
await page.waitForTimeout(150);
const cleared = await page.evaluate((k) => localStorage.getItem(k), storeKey);
check('/system clear empties the prompt', cleared === '', `got=${JSON.stringify(cleared)}`);

// 4. After clear, bare /system shows "(설정되지 않음)".
await page.evaluate(() => _lcChatSlashCommand('/system'));
await page.waitForTimeout(150);
const log2 = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('bare /system on empty prompt shows "(설정되지 않음)"',
  /설정되지 않음|not set/i.test(log2));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
