#!/usr/bin/env node
/**
 * QQ50 / QQ86 — Cmd+Shift+[/] navigates between chat sessions and
 * the active row auto-scrolls into view.
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
const ctx = await browser.newContext();
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

// Seed three sessions so we have something to navigate.
await page.evaluate(() => {
  // Wipe anything that was here before to make ordering deterministic.
  _lcSaveSessions([]);
  for (let i = 1; i <= 3; i++) {
    _lcNewSession('claude:opus');
    const id = _lcCurrentId();
    const sessions = _lcGetSessions();
    const s = sessions.find(x => x.id === id);
    if (s) s.label = 'sess-' + i;
    _lcSaveSessions(sessions);
  }
  _lcRenderSessions();
});

// Newest session is at top → most-recent _lcCurrentId is sess-3.
const initialId = await page.evaluate(() => _lcCurrentId());

// Move focus off the auto-focused composer textarea (QQ50 handler
// intentionally skips when focus is in INPUT/TEXTAREA so '[' / ']'
// typing in messages isn't hijacked).
await page.evaluate(() => {
  const ta = document.getElementById('lcChatInput');
  if (ta) ta.blur();
  document.body.focus();
});

// Use synthetic events dispatched on document so Playwright's per-element
// keystroke targeting doesn't refocus the textarea.
const dispatch = (key) => page.evaluate((k) => {
  const e = new KeyboardEvent('keydown', { key: k, metaKey: true, shiftKey: true, bubbles: true });
  document.dispatchEvent(e);
}, key);

await dispatch(']');
await page.waitForTimeout(80);
const afterNext = await page.evaluate(() => _lcCurrentId());
check('Cmd+Shift+] moved current session', afterNext !== initialId);

await dispatch('[');
await page.waitForTimeout(80);
const afterPrev = await page.evaluate(() => _lcCurrentId());
check('Cmd+Shift+[ moves back to original', afterPrev === initialId);

// Verify QQ86 — the active row carries data-active="1".
const activeRowOk = await page.evaluate(() => {
  const list = document.getElementById('lcSessionList');
  if (!list) return false;
  const active = list.querySelector('[data-active="1"]');
  return !!active;
});
check('active row carries data-active="1"', activeRowOk);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
