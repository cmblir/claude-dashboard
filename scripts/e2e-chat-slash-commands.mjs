#!/usr/bin/env node
/**
 * QQ1 — chat slash commands.
 *
 * /clear  — wipes the current session's history.
 * /system <text> — saves text under the per-assignee key.
 * /model  <provider:model> — flips the dropdown + persists.
 * /help   — appends a help message into the chat log.
 * QQ62   — Tab autocompletes the slash prefix.
 * QQ70   — slash commands also clear the QQ33 draft.
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

// Seed a clean session with 4 msgs and an assignee.
await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  const id = _lcCurrentId();
  _lcSaveHistory(id, [
    { role: 'user',      text: 'q1', ts: 1 },
    { role: 'assistant', text: 'a1', ts: 2 },
    { role: 'user',      text: 'q2', ts: 3 },
    { role: 'assistant', text: 'a2', ts: 4 },
  ]);
  _lcChatRender();
  // Mock confirm() so /clear's prompt auto-accepts.
  window.confirm = () => true;
});

// QQ62 — Tab autocomplete.
await page.click('#lcChatInput');
await page.fill('#lcChatInput', '/cl');
await page.keyboard.press('Tab');
await page.waitForTimeout(80);
const tabExpand = await page.$eval('#lcChatInput', el => el.value);
check('Tab autocompletes "/cl" → "/clear"', tabExpand === '/clear');

// /clear → history wipes.
await page.fill('#lcChatInput', '/clear');
await page.keyboard.press('Enter');
await page.waitForTimeout(120);
const afterClear = await page.evaluate(() =>
  _lcGetHistory(_lcCurrentId()).length);
check('/clear emptied current session', afterClear === 0);

// Composer must be cleared after slash.
const composerCleared = await page.$eval('#lcChatInput', el => el.value);
check('composer cleared post-slash', composerCleared === '');

// QQ70 — draft autosave entry must also be gone.
const draftRemoved = await page.evaluate(() => {
  const id = _lcCurrentId();
  return localStorage.getItem('cc.lc.draft.' + id) === null;
});
check('QQ70: cc.lc.draft.<sid> cleared after slash', draftRemoved);

// /system — saves system prompt under per-assignee key.
await page.fill('#lcChatInput', '/system You are a helpful pirate.');
await page.keyboard.press('Enter');
await page.waitForTimeout(120);
const sysSaved = await page.evaluate(() => {
  const sel = document.getElementById('lcChatAssignee');
  const a = sel.value || 'default';
  return localStorage.getItem('cc.lazyclawChat.sys.' + a);
});
check('/system <text> saved to cc.lazyclawChat.sys.<assignee>',
  /pirate/.test(sysSaved || ''));

// /model claude:haiku — flips dropdown + persists.
await page.fill('#lcChatInput', '/model claude:haiku');
await page.keyboard.press('Enter');
await page.waitForTimeout(120);
const modelSwap = await page.evaluate(() => ({
  selValue: document.getElementById('lcChatAssignee').value,
  ls: localStorage.getItem('cc.lazyclawChat.assignee'),
}));
check('/model claude:haiku → dropdown.value === "claude:haiku"',
  modelSwap.selValue === 'claude:haiku');
check('/model persisted to cc.lazyclawChat.assignee',
  modelSwap.ls === 'claude:haiku');

// /help — appends a help assistant message.
await page.fill('#lcChatInput', '/help');
await page.keyboard.press('Enter');
await page.waitForTimeout(120);
const helpAdded = await page.evaluate(() => {
  const h = _lcGetHistory(_lcCurrentId());
  return h.length >= 1 && /슬래시 명령|Slash command|斜杠命令/i.test(h[h.length-1].text || '');
});
check('/help appends help text into the session', helpAdded);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
