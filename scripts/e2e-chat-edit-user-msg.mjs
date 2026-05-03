#!/usr/bin/env node
/**
 * QQ22 — clicking ✏️ on a user message truncates the history at
 * that index and pre-fills the composer with the original text so
 * the user can revise + Enter to resubmit.
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

// Seed a session with 4 msgs (q1, a1, q2, a2). We'll edit q1 (idx 0).
const sid = await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  const id = _lcCurrentId();
  _lcSaveHistory(id, [
    { role: 'user',      text: 'first prompt',  ts: 100, assignee: 'claude:opus' },
    { role: 'assistant', text: 'reply A',        ts: 110, assignee: 'claude:opus' },
    { role: 'user',      text: 'second prompt', ts: 200, assignee: 'claude:opus' },
    { role: 'assistant', text: 'reply B',        ts: 210, assignee: 'claude:opus' },
  ]);
  _lcChatRender();
  return id;
});

// Trigger edit on idx 0 (first user msg).
await page.evaluate((id) => _lcEditUserMsg(id, 0), sid);
await page.waitForTimeout(120);

const after = await page.evaluate((id) => ({
  histLen: _lcGetHistory(id).length,
  inputVal: document.getElementById('lcChatInput').value,
}), sid);

check('history truncated to 0 messages (entries from idx 0 dropped)',
  after.histLen === 0);
check('composer pre-filled with the original user text',
  after.inputVal === 'first prompt');

// Edge case: editing idx 2 (the second user msg) keeps the first
// pair intact.
await page.evaluate((id) => {
  _lcSaveHistory(id, [
    { role: 'user',      text: 'q1', ts: 1, assignee: 'claude:opus' },
    { role: 'assistant', text: 'a1', ts: 2, assignee: 'claude:opus' },
    { role: 'user',      text: 'q2', ts: 3, assignee: 'claude:opus' },
    { role: 'assistant', text: 'a2', ts: 4, assignee: 'claude:opus' },
  ]);
  _lcChatRender();
  _lcEditUserMsg(id, 2);
}, sid);
await page.waitForTimeout(120);

const partial = await page.evaluate((id) => ({
  histLen: _lcGetHistory(id).length,
  hist: _lcGetHistory(id).map(m => `${m.role}:${m.text}`),
  inputVal: document.getElementById('lcChatInput').value,
}), sid);

check('partial edit: history truncated to first 2 entries',
  partial.histLen === 2);
check('partial edit: pre-filled with q2',
  partial.inputVal === 'q2');
check('partial edit: q1/a1 still in history',
  partial.hist.includes('user:q1') && partial.hist.includes('assistant:a1'));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
