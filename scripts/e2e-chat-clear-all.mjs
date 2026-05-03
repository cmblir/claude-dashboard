#!/usr/bin/env node
/**
 * QQ174 — `/clear all` wipes every chat session after a confirm.
 * `/clear` (no arg) keeps the QQ173 single-session behaviour.
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
  window.__confirms = 0;
  window.confirm = () => { window.__confirms++; return true; };
});

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

// Seed three sessions, each with one user message.
await page.evaluate(() => {
  _lcSaveSessions([]);
  for (let i = 0; i < 3; i++) {
    _lcNewSession('claude:opus');
    _lcSaveHistory(_lcCurrentId(), [
      { role: 'user', text: 'session ' + i, ts: i, assignee: 'claude:opus' },
    ]);
  }
});

const before = await page.evaluate(() => ({
  sessions: _lcGetSessions().length,
  histCount: Object.keys(localStorage).filter(k => k.startsWith('cc.lc.hist.')).length,
}));
check('seeded 3 sessions', before.sessions === 3 && before.histCount === 3,
  JSON.stringify(before));

// /clear all wipes every session.
await page.evaluate(() => { window.__confirms = 0; });
await page.evaluate(() => _lcChatSlashCommand('/clear all'));
await page.waitForTimeout(200);
const after = await page.evaluate(() => ({
  sessions: _lcGetSessions().length,
  histCount: Object.keys(localStorage).filter(k => k.startsWith('cc.lc.hist.')).length,
  confirms: window.__confirms,
}));

check('/clear all confirmed once', after.confirms === 1, `confirms=${after.confirms}`);
// _lcEnsureSession('') is called after wipe so we're back to 1 fresh session.
check('/clear all ends with at most 1 fresh session',
  after.sessions <= 1, `sessions=${after.sessions}`);
check('/clear all removes all original cc.lc.hist.* keys',
  after.histCount === 0, `histKeys=${after.histCount}`);

// /help mentions /clear all
await page.evaluate(() => _lcChatSlashCommand('/help'));
await page.waitForTimeout(150);
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/help mentions /clear all', /\/clear\s*all/.test(help));

// QQ176 — `/clear all <junk>` still triggers the all-wipe path
//   (token-based match) instead of silently degrading to single-session.
await page.evaluate(() => {
  _lcSaveSessions([]);
  for (let i = 0; i < 3; i++) {
    _lcNewSession('claude:opus');
    _lcSaveHistory(_lcCurrentId(), [{role:'user',text:'x',ts:i,assignee:'claude:opus'}]);
  }
  window.__confirms = 0;
});
await page.evaluate(() => _lcChatSlashCommand('/clear all please'));
await page.waitForTimeout(200);
const r4 = await page.evaluate(() => ({
  sessions: _lcGetSessions().length,
  histCount: Object.keys(localStorage).filter(k => k.startsWith('cc.lc.hist.')).length,
  confirms: window.__confirms,
}));
check('/clear all <junk> still wipes everything (token match)',
  r4.sessions <= 1 && r4.histCount === 0 && r4.confirms === 1,
  JSON.stringify(r4));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
