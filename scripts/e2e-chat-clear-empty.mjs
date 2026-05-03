#!/usr/bin/env node
/**
 * QQ173 — /clear on an already-empty session no longer prompts for
 * confirmation. Toast says "이미 비어있습니다" instead. Non-empty
 * session still confirms (mistake-prevention).
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

await page.addInitScript(() => {
  window.__confirmCalls = 0;
  window.confirm = () => { window.__confirmCalls++; return true; };
});

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

await page.evaluate(() => {
  window.__toasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__toasts.push({m,k}); return orig && orig(m,k); };
});

// 1. Empty session — /clear should NOT confirm.
await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  _lcSaveHistory(_lcCurrentId(), []);
  _lcChatRender();
  window.__confirmCalls = 0;
  window.__toasts.length = 0;
});
await page.evaluate(() => _lcChatSlashCommand('/clear'));
await page.waitForTimeout(150);
const r1 = await page.evaluate(() => ({
  confirms: window.__confirmCalls,
  toast: window.__toasts.slice(-1)[0],
}));
check('empty session: no confirm prompt', r1.confirms === 0,
  `confirms=${r1.confirms}`);
check('empty session: toasts "이미 비어있습니다"',
  r1.toast && /이미 비어있습니다|already empty|empty/i.test(r1.toast.m),
  JSON.stringify(r1.toast));

// 2. Non-empty session — /clear should still confirm and wipe.
await page.evaluate(() => {
  const id = _lcCurrentId();
  _lcSaveHistory(id, [
    { role: 'user', text: 'hi', ts: 1, assignee: 'claude:opus' },
    { role: 'assistant', text: 'hello', ts: 2, assignee: 'claude:opus' },
  ]);
  _lcChatRender();
  window.__confirmCalls = 0;
});
await page.evaluate(() => _lcChatSlashCommand('/clear'));
await page.waitForTimeout(150);
const r2 = await page.evaluate(() => ({
  confirms: window.__confirmCalls,
  histLen: _lcGetHistory(_lcCurrentId()).length,
}));
check('non-empty session: confirm prompt fires', r2.confirms === 1,
  `confirms=${r2.confirms}`);
check('non-empty session: history is wiped', r2.histLen === 0,
  `histLen=${r2.histLen}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
