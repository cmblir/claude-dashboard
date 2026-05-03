#!/usr/bin/env node
/**
 * QQ205 — `/clear N` drops the last N messages of the current session
 * (openclaw-style undo). Doesn't collide with `/clear all` (token
 * match) or bare `/clear` (whole-session clear).
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

// Seed a clean session with 6 messages
await page.evaluate(() => {
  for (const k of Object.keys(localStorage)) if (k.startsWith('cc.lc.')) localStorage.removeItem(k);
});
await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });
await page.evaluate(() => {
  const id = _lcMakeSessionId();
  _lcSaveSessions([{ id, label: 'clear-n-test', assignee: '', ts: Date.now(), preview: '' }]);
  _lcSetCurrentId(id);
  _lcSaveHistory(id, [
    { role: 'user',      text: 'q1', ts: Date.now() },
    { role: 'assistant', text: 'a1', ts: Date.now() },
    { role: 'user',      text: 'q2', ts: Date.now() },
    { role: 'assistant', text: 'a2', ts: Date.now() },
    { role: 'user',      text: 'q3', ts: Date.now() },
    { role: 'assistant', text: 'a3', ts: Date.now() },
  ]);
  _lcChatRender();
});

async function slash(line) {
  await page.evaluate((l) => _lcChatSlashCommand(l), line);
  await page.waitForTimeout(180);
}

const len = async () => await page.evaluate(() => _lcGetHistory(_lcCurrentId()).length);

// 1. /clear 2 drops last 2
check('seed 6 messages', (await len()) === 6);
await slash('/clear 2');
check('/clear 2 drops 2 (4 left)', (await len()) === 4);

// 2. /clear 99 (over-shoot) drops everything
await slash('/clear 99');
check('/clear 99 drops all remaining (0 left)', (await len()) === 0);

// 3. /clear 1 on empty toasts
await page.evaluate(() => {
  window.__clearToasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__clearToasts.push({m, k}); return orig && orig(m, k); };
});
await slash('/clear 3');
const emptyToasts = await page.evaluate(() => window.__clearToasts);
check('/clear N on empty session emits warn',
  emptyToasts.some(t => /비울 메시지/i.test(t.m)),
  JSON.stringify(emptyToasts));

// 4. Re-seed and verify /clear (no arg) still wipes the whole session.
// _lcChatClear() prompts via window.confirm — auto-accept it so the
// headless run doesn't stall on the modal.
await page.evaluate(() => {
  window.confirm = () => true;
  _lcSaveHistory(_lcCurrentId(), [
    { role: 'user', text: 'X', ts: Date.now() },
    { role: 'assistant', text: 'Y', ts: Date.now() },
  ]);
  _lcChatRender();
});
check('re-seeded 2 messages', (await len()) === 2);
await slash('/clear');
check('/clear (no arg) still wipes whole session', (await len()) === 0);

// 5. /clear all still wipes everything (we override confirm to true)
await page.evaluate(() => {
  const id = _lcMakeSessionId();
  _lcSaveSessions([
    ...(_lcGetSessions()),
    { id, label: 'extra', assignee: '', ts: Date.now(), preview: '' },
  ]);
  window.confirm = () => true;
});
const beforeAllCount = await page.evaluate(() => _lcGetSessions().length);
check('seeded extra session before /clear all', beforeAllCount >= 2);
await slash('/clear all');
const afterAllCount = await page.evaluate(() => _lcGetSessions().length);
check('/clear all reduces sessions to 1 (the auto-created blank)',
  afterAllCount === 1, `count=${afterAllCount}`);

// 6. /help mentions /clear N
await slash('/help');
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /clear N', /\/clear N/.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
