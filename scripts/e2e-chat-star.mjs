#!/usr/bin/env node
/**
 * QQ15 — star toggle on a chat message persists `m.starred` and the
 * search modal's ⭐ filter restricts results to starred messages.
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
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

// Seed a session with 4 messages.
const sid = await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  const id = _lcCurrentId();
  _lcSaveHistory(id, [
    { role: 'user',      text: 'q1', ts: 1 },
    { role: 'assistant', text: 'a1 has KEEP-ME content', ts: 2 },
    { role: 'user',      text: 'q2', ts: 3 },
    { role: 'assistant', text: 'a2 normal',   ts: 4 },
  ]);
  _lcChatRender();
  return id;
});

// Star idx 1 (the KEEP-ME assistant message).
await page.evaluate((id) => _lcToggleStar(id, 1), sid);
await page.waitForTimeout(80);
const starredOn = await page.evaluate((id) => {
  const h = _lcGetHistory(id);
  return h[1].starred === true;
}, sid);
check('toggling star sets m.starred = true', starredOn);

// Star button text is ⭐ for starred / ☆ for not.
const buttonGlyph = await page.evaluate(() => {
  const log = document.getElementById('lcChatLog');
  const stars = Array.from(log.querySelectorAll('button'))
    .filter(b => /[⭐☆]/.test(b.textContent.trim()));
  return stars.map(b => b.textContent.trim());
});
check('exactly 1 ⭐ button rendered after starring',
  buttonGlyph.filter(g => g === '⭐').length === 1);
check('other 3 messages still show ☆',
  buttonGlyph.filter(g => g === '☆').length === 3);

// Open Cmd+K search, enable ⭐ filter — only the starred msg appears.
await page.click('#lcChatInput');
await page.keyboard.press('Meta+k');
await page.waitForTimeout(150);
// Set the ⭐ filter via JS — clicking the checkbox through Playwright
// is flaky because it's wrapped in a <label>; we just dispatch the
// change event the input listener bound to.
await page.evaluate(() => {
  const cb = document.getElementById('lcSearchStar');
  cb.checked = true;
  cb.dispatchEvent(new Event('change', { bubbles: true }));
});
await page.waitForTimeout(220);

const starredHits = await page.evaluate(() => {
  const cards = document.querySelectorAll('.modal button.card');
  return Array.from(cards).map(c => c.textContent.trim()).filter(Boolean);
});
check('⭐ filter returns exactly 1 hit',  starredHits.length === 1);
check('that hit references KEEP-ME content',
  /KEEP-ME/.test(starredHits[0] || ''));

// Close modal + un-star.
await page.evaluate(() => closeModal && closeModal());
await page.waitForTimeout(80);
await page.evaluate((id) => _lcToggleStar(id, 1), sid);
await page.waitForTimeout(60);
const starredOff = await page.evaluate((id) => _lcGetHistory(id)[1].starred === false || _lcGetHistory(id)[1].starred === undefined, sid);
check('un-toggle clears m.starred', starredOff);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
