#!/usr/bin/env node
/**
 * QQ164 — Cmd/Ctrl+Shift+N creates a fresh chat session without
 * needing the mouse. Mirrors the "+ New chat" button.
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

await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  _lcSaveHistory(_lcCurrentId(), [
    { role: 'user', text: 'pre-existing', ts: 1, assignee: 'claude:opus' },
  ]);
  _lcChatRender();
});

const before = await page.evaluate(() => ({
  count: _lcGetSessions().length,
  curId: _lcCurrentId(),
}));
check('starts with 1 session', before.count === 1, `count=${before.count}`);

// Move focus OFF the textarea so the shortcut isn't suppressed.
await page.evaluate(() => {
  const ta = document.getElementById('lcChatInput');
  if (ta) ta.blur();
  // Click on a non-input element to shed focus.
  document.getElementById('lcChatLog')?.click();
});
await page.keyboard.press('Meta+Shift+KeyN');
await page.waitForTimeout(150);

const after = await page.evaluate(() => ({
  count: _lcGetSessions().length,
  curId: _lcCurrentId(),
}));
check('shortcut creates a new session', after.count === 2, `count=${after.count}`);
check('shortcut switches to the new session',
  after.curId !== before.curId, `before=${before.curId} after=${after.curId}`);

// While typing in the textarea, the shortcut should NOT fire.
await page.evaluate(() => document.getElementById('lcChatInput').focus());
const beforeTyping = await page.evaluate(() => _lcGetSessions().length);
await page.keyboard.press('Meta+Shift+KeyN');
await page.waitForTimeout(150);
const afterTyping = await page.evaluate(() => _lcGetSessions().length);
check('shortcut suppressed inside textarea', afterTyping === beforeTyping,
  `before=${beforeTyping} after=${afterTyping}`);

// /help mentions the new shortcut
await page.evaluate(() => _lcChatSlashCommand('/help'));
await page.waitForTimeout(150);
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/help lists Cmd+Shift+N', /Shift\s*\+\s*N/i.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
