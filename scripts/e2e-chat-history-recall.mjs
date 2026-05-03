#!/usr/bin/env node
/**
 * QQ51 / QQ85 — chat composer history recall.
 *
 * 1. Seed a session with 3 saved user messages.
 * 2. Press Cmd+↑ → composer fills with the most recent user msg.
 * 3. Press Cmd+↑ again → walks back one further.
 * 4. Press Cmd+↓ → walks forward.
 * 5. QQ85 — typing a regular character resets the cursor so the
 *    next Cmd+↑ starts fresh from the most recent.
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

// Seed 3 user messages in the current session's saved history.
await page.evaluate(() => {
  if (!_lcCurrentId() || !_lcGetSessions().find(s => s.id === _lcCurrentId())) {
    _lcNewSession('claude:opus');
  }
  const id = _lcCurrentId();
  _lcSaveHistory(id, [
    { role: 'user',      text: 'first message',  ts: 1, assignee: 'claude:opus' },
    { role: 'assistant', text: 'reply 1',        ts: 2, assignee: 'claude:opus' },
    { role: 'user',      text: 'second message', ts: 3, assignee: 'claude:opus' },
    { role: 'assistant', text: 'reply 2',        ts: 4, assignee: 'claude:opus' },
    { role: 'user',      text: 'third message',  ts: 5, assignee: 'claude:opus' },
  ]);
  _lcChatRender();
  // Reset the recall cursor to avoid a stale value across page nav.
  window.__lcHistIdx = -1;
});

// Make sure the composer has focus before sending arrow keys.
await page.click('#lcChatInput');
await page.evaluate(() => { document.getElementById('lcChatInput').value = ''; });

// Step 1 — Cmd+↑ recalls the most recent user msg ("third message").
await page.keyboard.press('Meta+ArrowUp');
await page.waitForTimeout(80);
let val = await page.$eval('#lcChatInput', el => el.value);
check('Cmd+↑ recalls "third message"', val === 'third message');

// Step 2 — Cmd+↑ again walks back to "second message".
await page.keyboard.press('Meta+ArrowUp');
await page.waitForTimeout(80);
val = await page.$eval('#lcChatInput', el => el.value);
check('Cmd+↑ again walks back to "second message"', val === 'second message');

// Step 3 — Cmd+↓ walks forward to "third message".
await page.keyboard.press('Meta+ArrowDown');
await page.waitForTimeout(80);
val = await page.$eval('#lcChatInput', el => el.value);
check('Cmd+↓ walks forward to "third message"', val === 'third message');

// Step 4 — QQ85 reset on input. Type a character (replacing field),
// then Cmd+↑ should pull the most recent again.
await page.fill('#lcChatInput', 'edited');
await page.waitForTimeout(60);
const histIdxAfterEdit = await page.evaluate(() => window.__lcHistIdx);
check('QQ85 cursor resets to -1 after typing', histIdxAfterEdit === -1);

await page.keyboard.press('Meta+ArrowUp');
await page.waitForTimeout(80);
val = await page.$eval('#lcChatInput', el => el.value);
check('post-reset Cmd+↑ recalls most recent again', val === 'third message');

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
