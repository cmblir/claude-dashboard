#!/usr/bin/env node
/**
 * QQ199 — `/pin` and `/unpin` toggle the `pinned` flag on the current
 * session. `/sessions` orders pinned sessions above unpinned (after the
 * active one) and prepends a 📌 marker. /help lists both commands.
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

// Clear and seed two sessions: one is the current/active, the other is a
// non-active "older" session that we'll pin to verify ordering.
await page.evaluate(() => {
  localStorage.removeItem('cc.lc.sessions');
  localStorage.removeItem('cc.lc.current');
  const sessions = [
    { id: 'lcs-active',  label: 'ActiveSession',  assignee: '', ts: Date.now(),       preview: '' },
    { id: 'lcs-pinme',   label: 'PinTarget',      assignee: '', ts: Date.now() - 100, preview: '' },
    { id: 'lcs-other',   label: 'OtherSession',   assignee: '', ts: Date.now() - 200, preview: '' },
  ];
  localStorage.setItem('cc.lc.sessions', JSON.stringify(sessions));
  localStorage.setItem('cc.lc.current', 'lcs-active');
});

await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

async function slash(line) {
  await page.evaluate((l) => _lcChatSlashCommand(l), line);
  await page.waitForTimeout(180);
}

// 1. Switch to PinTarget so we pin THAT session
await page.evaluate(() => { localStorage.setItem('cc.lc.current', 'lcs-pinme'); });
await slash('/pin');
const afterPin = await page.evaluate(() => {
  const ss = JSON.parse(localStorage.getItem('cc.lc.sessions') || '[]');
  return ss.find(s => s.id === 'lcs-pinme') || {};
});
check('/pin sets pinned=true on current session', afterPin.pinned === true);

// 2. Switch back to ActiveSession and run /sessions; PinTarget should
//    appear before OtherSession (active is always first regardless).
await page.evaluate(() => { localStorage.setItem('cc.lc.current', 'lcs-active'); });
await slash('/sessions');
const order = await page.evaluate(() => {
  const log = document.getElementById('lcChatLog');
  const txt = log.innerText || '';
  const idx = (s) => txt.indexOf(s);
  return { active: idx('ActiveSession'), pin: idx('PinTarget'), other: idx('OtherSession'), pinIcon: txt.indexOf('📌') };
});
check('/sessions lists ActiveSession first',  order.active >= 0 && order.active < order.pin);
check('/sessions lists PinTarget before OtherSession (pinned bubbles up)',
  order.pin > 0 && order.pin < order.other);
check('/sessions shows 📌 marker for pinned',  order.pinIcon > 0);

// 3. /unpin clears the flag
await page.evaluate(() => { localStorage.setItem('cc.lc.current', 'lcs-pinme'); });
await slash('/unpin');
const afterUnpin = await page.evaluate(() => {
  const ss = JSON.parse(localStorage.getItem('cc.lc.sessions') || '[]');
  return ss.find(s => s.id === 'lcs-pinme') || {};
});
check('/unpin clears pinned flag', afterUnpin.pinned === false);

// 4. /pin twice in a row → second emits "already pinned" toast and is a no-op
await page.evaluate(() => {
  window.__pinToasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__pinToasts.push({m, k}); return orig && orig(m, k); };
});
await slash('/pin');
await slash('/pin');
const toasts = await page.evaluate(() => window.__pinToasts);
check('second /pin emits already-pinned warn',
  toasts.length >= 2 && toasts.some(t => /이미 고정/.test(t.m) || /already/i.test(t.m)),
  JSON.stringify(toasts).slice(0, 200));

// 5. /help lists /pin and /unpin
await slash('/help');
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /pin', /\/pin/.test(help));
check('/help lists /unpin', /\/unpin/.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
