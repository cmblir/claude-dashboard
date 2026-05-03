#!/usr/bin/env node
/**
 * QQ124 — typo'd or unknown chat slash commands stop being sent to
 * the provider. Instead they're swallowed locally with a toast that
 * suggests the closest known command.
 *
 *   /clearr   → toast("혹시 /clear?")  history unchanged, no API hit
 *   /xyzzy    → toast(no hint)         swallowed
 *   /path/to  → falls through (multi-word/path-like — provider gets it)
 *   (this last case we just confirm `_lcChatSlashCommand` returns false)
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

let chatApiHits = 0;
page.on('request', req => {
  if (req.url().includes('/api/lazyclaw/chat')) chatApiHits++;
});

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

// Stash toast messages so we can assert hint text.
await page.evaluate(() => {
  window.__toasts = [];
  const orig = window.toast;
  window.toast = (msg, kind) => { window.__toasts.push({ msg, kind }); return orig && orig(msg, kind); };
});

await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  _lcSaveHistory(_lcCurrentId(), []);
  _lcChatRender();
});

// 1. /clearr — typo of /clear
const r1 = await page.evaluate(() => _lcChatSlashCommand('/clearr'));
check('/clearr is swallowed (returns true)', r1 === true);

const t1 = await page.evaluate(() => window.__toasts.slice(-1)[0]);
check('/clearr toast suggests /clear',
  t1 && /\/clear/.test(t1.msg) && t1.kind === 'warn',
  `toast=${JSON.stringify(t1)}`);

// 2. /xyzzy — no close match → toast WITHOUT hint
await page.evaluate(() => { window.__toasts.length = 0; });
const r2 = await page.evaluate(() => _lcChatSlashCommand('/xyzzy'));
check('/xyzzy is swallowed', r2 === true);
const t2 = await page.evaluate(() => window.__toasts.slice(-1)[0]);
check('/xyzzy toast points to /help',
  t2 && /\/help/.test(t2.msg),
  `toast=${JSON.stringify(t2)}`);
check('/xyzzy toast does NOT misleadingly suggest a far cmd',
  t2 && !/혹시|did you mean/.test(t2.msg));

// 3. /path/to/file — multi-word/path-like → must NOT swallow
await page.evaluate(() => { window.__toasts.length = 0; });
const r3 = await page.evaluate(() => _lcChatSlashCommand('/path/to/file'));
check('/path/to/file falls through (returns false)', r3 === false);

// 4. Real /help still works after the unknown handler
const r4 = await page.evaluate(() => _lcChatSlashCommand('/help'));
check('/help still works', r4 === true);

// 5. No /api/lazyclaw/chat requests fired throughout
check('no chat API requests for typo paths', chatApiHits === 0,
  `hits=${chatApiHits}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
