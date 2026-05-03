#!/usr/bin/env node
/**
 * QQ125 — /go <tab> (and alias /open) jumps to another dashboard
 * tab without leaving the chat. Aliases ('term', 'wf', 'proj', 'ai',
 * 'settings', etc.) resolve via a small alias map; literal tab ids
 * pass through unchanged.
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

async function slash(line) {
  await page.evaluate((l) => _lcChatSlashCommand(l), line);
  await page.waitForTimeout(180);
}

// 1. /go term — alias resolves to lazyclawTerm
await slash('/go term');
await page.waitForFunction(() => state && state.view === 'lazyclawTerm', { timeout: 4000 });
const v1 = await page.evaluate(() => state.view);
check('/go term lands on lazyclawTerm', v1 === 'lazyclawTerm');

// Hop back to chat
await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput');

// 2. /go wf — alias resolves to workflows
await slash('/go wf');
await page.waitForFunction(() => state && state.view === 'workflows', { timeout: 4000 });
const v2 = await page.evaluate(() => state.view);
check('/go wf lands on workflows', v2 === 'workflows');

// Hop back
await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput');

// 3. /open analytics — literal tab id (also alias-mapped to itself)
await slash('/open analytics');
await page.waitForFunction(() => state && state.view === 'analytics', { timeout: 4000 });
const v3 = await page.evaluate(() => state.view);
check('/open analytics lands on analytics', v3 === 'analytics');

// 4. /go (no arg) toasts a usage hint, doesn't navigate
await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput');
await page.evaluate(() => {
  window.__toastMsg = '';
  const orig = window.toast;
  window.toast = (msg, kind) => { window.__toastMsg = msg; return orig && orig(msg, kind); };
});
await slash('/go');
const t4 = await page.evaluate(() => window.__toastMsg);
const stayed = await page.evaluate(() => state.view);
check('/go without arg toasts usage', /\/go|tab/i.test(t4), `toast="${t4}"`);
check('/go without arg stays on lazyclawChat', stayed === 'lazyclawChat');

// 5. /help lists /go
await slash('/help');
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /go', /\/go/.test(help));

// QQ169 — `/go bogusXYZ` must NOT navigate; toast warns + view stays put.
await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput');
await page.evaluate(() => {
  window.__toastMsg = '';
  const orig = window.toast;
  window.toast = (m, k) => { window.__toastMsg = m; return orig && orig(m, k); };
});
await slash('/go bogusXYZ');
const v = await page.evaluate(() => state.view);
const toast = await page.evaluate(() => window.__toastMsg);
check('/go bogusXYZ stays on lazyclawChat', v === 'lazyclawChat',
  `view=${v}`);
check('/go bogusXYZ toasts unknown-tab + points to /tabs',
  /알 수 없는 탭|unknown/i.test(toast) && /tabs|\/tabs/.test(toast),
  `toast="${toast}"`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
