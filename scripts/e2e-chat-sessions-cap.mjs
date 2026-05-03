#!/usr/bin/env node
/**
 * QQ188 — `/sessions` caps output at 30 entries so power users with
 * lots of sessions don't get a wall of text dumped into the chat.
 * Active session is pinned to the top so it's always visible.
 * Overflow line "_… N 개 더_" reports the count.
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

// Seed 50 sessions, mark session #25 as the current one so we can prove
// the active-pinned-to-top behaviour.
await page.evaluate(() => {
  const arr = [];
  for (let i = 0; i < 50; i++) arr.push({
    id: 'sess-' + String(i).padStart(3, '0'),
    label: 'Session ' + i,
    assignee: 'claude:opus',
  });
  _lcSaveSessions(arr);
  // Mark session-025 active by writing the correct localStorage key.
  localStorage.setItem('cc.lc.current', 'sess-025');
});

await page.evaluate(() => _lcChatSlashCommand('/sessions'));
await page.waitForTimeout(150);

const out = await page.evaluate(() => document.getElementById('lcChatLog').innerText);

// Count session-line entries by their "sess-NNN" prefix.
const visibleLines = (out.match(/sess-\d{3}/g) || []).length;
check('rendered ≤ 30 session lines (capped)',
  visibleLines <= 30, `count=${visibleLines}`);

check('active session-025 is in the rendered chunk',
  /➜.*sess-025/.test(out), `out=${out.slice(-300)}`);

check('overflow note shows the remaining count',
  /\b20\b.*개 더|… 20/.test(out), `excerpt=${out.slice(-100)}`);

check('total count in header is 50',
  /\(50\)/.test(out));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
