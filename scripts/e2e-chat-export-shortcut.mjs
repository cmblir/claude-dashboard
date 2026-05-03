#!/usr/bin/env node
/**
 * QQ166 — Cmd/Ctrl+Shift+E exports the current chat to markdown.
 * Mirrors the toolbar 📥 button. Suppressed inside input/textarea.
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

// Seed a session so export has something to dump.
await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  _lcSaveHistory(_lcCurrentId(), [
    { role: 'user',      text: 'hi',    ts: 1, assignee: 'claude:opus' },
    { role: 'assistant', text: 'hello', ts: 2, assignee: 'claude:opus' },
  ]);
  _lcChatRender();
});

// Stub _lcChatExport so we don't actually trigger a download in headless.
await page.evaluate(() => {
  window.__exportCalls = 0;
  const orig = window._lcChatExport;
  window._lcChatExport = () => { window.__exportCalls++; /* don't call orig */ };
});

// Drop focus from the textarea so the shortcut isn't suppressed.
await page.evaluate(() => {
  const ta = document.getElementById('lcChatInput');
  if (ta) ta.blur();
  document.getElementById('lcChatLog')?.click();
});

await page.keyboard.press('Meta+Shift+KeyE');
await page.waitForTimeout(150);

const calls = await page.evaluate(() => window.__exportCalls);
check('Cmd+Shift+E invokes _lcChatExport', calls === 1, `calls=${calls}`);

// While typing in the textarea, the shortcut should NOT fire.
await page.evaluate(() => {
  document.getElementById('lcChatInput').focus();
  window.__exportCalls = 0;
});
await page.keyboard.press('Meta+Shift+KeyE');
await page.waitForTimeout(150);
const callsTyping = await page.evaluate(() => window.__exportCalls);
check('shortcut suppressed inside textarea', callsTyping === 0, `calls=${callsTyping}`);

// /help mentions the shortcut
await page.evaluate(() => _lcChatSlashCommand('/help'));
await page.waitForTimeout(150);
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/help lists Cmd+Shift+E', /Shift\s*\+\s*E/i.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
