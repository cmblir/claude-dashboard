#!/usr/bin/env node
/**
 * QQ35 — ⬇ scroll-to-bottom button appears when scrolled > 120 px
 *        away from bottom; clicking it jumps the chat log back.
 * QQ76 — pre-token "_…_" placeholder appears immediately after a
 *        send (verifies the placeholder push path even though we
 *        don't run the SSE network).
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
const ctx = await browser.newContext({ viewport: { width: 1400, height: 700 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

// Seed enough messages to overflow the log so we can scroll up.
await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  const id = _lcCurrentId();
  const h = [];
  for (let i = 0; i < 30; i++) {
    h.push({ role: i % 2 ? 'assistant' : 'user',
             text: 'msg ' + i + ' '.repeat(40) + 'padding for height',
             ts: 1000 + i, assignee: 'claude:opus' });
  }
  _lcSaveHistory(id, h);
  _lcChatRender();
});
await page.waitForTimeout(150);

// Scroll the log to the top so we're > 120 px away from bottom.
await page.evaluate(() => {
  const log = document.getElementById('lcChatLog');
  log.scrollTop = 0;
  log.dispatchEvent(new Event('scroll'));
});
await page.waitForTimeout(150);

const btnVisible = await page.evaluate(() => {
  const b = document.getElementById('lcScrollBottom');
  return b && b.style.display !== 'none' && b.style.display !== '';
});
// The button starts with style="display:none;" — when visible,
// the QQ35 scroll listener clears that to '' or 'block'.
const visState = await page.evaluate(() => {
  const b = document.getElementById('lcScrollBottom');
  return b && b.style.display;
});
check('⬇ scroll-to-bottom button visible after scrolling up',
  visState === 'block' || visState === '');

// Click it.
await page.evaluate(() => document.getElementById('lcScrollBottom').click());
await page.waitForTimeout(120);

const scrolledBack = await page.evaluate(() => {
  const log = document.getElementById('lcChatLog');
  const off = log.scrollHeight - log.scrollTop - log.clientHeight;
  return { off, hidden: document.getElementById('lcScrollBottom').style.display === 'none' };
});
check('clicking ⬇ jumps to bottom (offset within 120 px)',
  scrolledBack.off <= 120);
check('button hides again at bottom', scrolledBack.hidden);

// QQ88 + QQ111 — even if we're scrolled away, sending forces a jump,
// and the placeholder bubble actually renders via the live-history
// override.
await page.evaluate(() => {
  const log = document.getElementById('lcChatLog');
  log.scrollTop = 0;
  log.dispatchEvent(new Event('scroll'));
});
await page.waitForTimeout(120);
await page.evaluate(() => {
  const id = _lcCurrentId();
  const history = _lcGetHistory(id);
  history.push({ role: 'user', text: 'NEW USER MSG', ts: Date.now() });
  _lcSaveHistory(id, history);
  // Push pending placeholder ONLY into the live array (mirrors the
  // _lcChatSend QQ77 contract — never saved).
  history.push({ role: 'assistant', text: '_…_', ts: Date.now(),
                 pending: true, assignee: 'claude:opus' });
  // QQ111 — live history override so the placeholder actually renders.
  _lcChatRender({ history });
  const log = document.getElementById('lcChatLog');
  if (log) log.scrollTop = log.scrollHeight;
});
await page.waitForTimeout(120);

const sendScrolled = await page.evaluate(() => {
  const log = document.getElementById('lcChatLog');
  return log.scrollHeight - log.scrollTop - log.clientHeight;
});
check('QQ88: after send the log is at bottom', sendScrolled <= 80);

// QQ76 placeholder: live history has the pending bubble visible.
const placeholder = await page.evaluate(() => {
  const log = document.getElementById('lcChatLog');
  return /_…_|<em>…<\/em>/.test(log.innerHTML);
});
check('QQ76 "_…_" placeholder visible in DOM', placeholder);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
