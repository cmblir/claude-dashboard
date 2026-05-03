#!/usr/bin/env node
/**
 * QQ171 — `/code` copies just the LAST fenced code block from the
 * most recent assistant reply. Useful when the assistant returned
 * prose + code and you only want the snippet.
 *
 * Edge cases tested:
 *   - assistant reply with one code block → copies that block
 *   - assistant reply with TWO blocks → copies the last
 *   - reply with no code blocks → toast warning, no clipboard write
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
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
try { await ctx.grantPermissions(['clipboard-read','clipboard-write'], { origin: URL.replace(/\/$/, '') }); } catch (_) {}
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  window.__toasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__toasts.push({m,k}); return orig && orig(m,k); };
});

// 1. one code block
await page.evaluate(() => {
  const id = _lcCurrentId();
  _lcSaveHistory(id, [
    { role: 'user', text: 'how do I sum?', ts: 1, assignee: 'claude:opus' },
    { role: 'assistant',
      text: 'Sure!\n\n```js\nconst sum = (a, b) => a + b;\n```\n\nThat\'s it.',
      ts: 2, assignee: 'claude:opus' },
  ]);
});
await page.evaluate(() => _lcChatSlashCommand('/code'));
await page.waitForTimeout(200);
const clip1 = await page.evaluate(async () => {
  try { return await navigator.clipboard.readText(); } catch (_) { return null; }
});
check('/code copies the JS snippet (single block)',
  clip1 && /const sum = \(a, b\) => a \+ b;/.test(clip1),
  `clip="${(clip1 || '').slice(0, 60)}"`);

// 2. multiple code blocks → copies the LAST
await page.evaluate(() => {
  const id = _lcCurrentId();
  _lcSaveHistory(id, [
    { role: 'user', text: 'two flavours', ts: 1, assignee: 'claude:opus' },
    { role: 'assistant',
      text: 'Option A:\n\n```js\nlet x = 1;\n```\n\nOption B (preferred):\n\n```py\nx = 2\n```',
      ts: 2, assignee: 'claude:opus' },
  ]);
  // Wipe clipboard
  navigator.clipboard.writeText('');
});
await page.evaluate(() => _lcChatSlashCommand('/code'));
await page.waitForTimeout(200);
const clip2 = await page.evaluate(async () => {
  try { return await navigator.clipboard.readText(); } catch (_) { return null; }
});
check('/code with multiple blocks copies the LAST one',
  clip2 && /^x = 2/m.test(clip2) && !clip2.includes('let x = 1'),
  `clip="${(clip2 || '').slice(0, 60)}"`);

// 3. no code block → toast warning
await page.evaluate(() => {
  const id = _lcCurrentId();
  _lcSaveHistory(id, [
    { role: 'user', text: 'just words', ts: 1, assignee: 'claude:opus' },
    { role: 'assistant', text: 'Just plain prose, no code.',
      ts: 2, assignee: 'claude:opus' },
  ]);
  window.__toasts.length = 0;
});
await page.evaluate(() => _lcChatSlashCommand('/code'));
await page.waitForTimeout(150);
const t3 = await page.evaluate(() => window.__toasts.slice(-1)[0]);
check('/code on a no-code reply toasts a warning',
  t3 && /코드 블록|code/i.test(t3.m), JSON.stringify(t3));

// QQ184 — `/code N` (1-indexed) picks a specific block.
await page.evaluate(() => {
  const id = _lcCurrentId();
  _lcSaveHistory(id, [
    { role: 'user', text: 'three flavours', ts: 1, assignee: 'claude:opus' },
    { role: 'assistant',
      text: 'Pick:\n\n```js\nA\n```\n\n```py\nB\n```\n\n```rb\nC\n```',
      ts: 2, assignee: 'claude:opus' },
  ]);
  navigator.clipboard.writeText('');
});
await page.evaluate(() => _lcChatSlashCommand('/code 2'));
await page.waitForTimeout(200);
const clipB = await page.evaluate(async () => {
  try { return await navigator.clipboard.readText(); } catch (_) { return null; }
});
check('/code 2 picks the 2nd block (B)',
  clipB && /^B/m.test(clipB) && !/A/.test(clipB),
  `clip="${(clipB || '').slice(0, 30)}"`);

await page.evaluate(() => _lcChatSlashCommand('/code 1'));
await page.waitForTimeout(200);
const clipA = await page.evaluate(async () => {
  try { return await navigator.clipboard.readText(); } catch (_) { return null; }
});
check('/code 1 picks the 1st block (A)',
  clipA && /^A/m.test(clipA), `clip="${(clipA || '').slice(0, 30)}"`);

// Out-of-range
await page.evaluate(() => { window.__toasts.length = 0; });
await page.evaluate(() => _lcChatSlashCommand('/code 99'));
const t99 = await page.evaluate(() => window.__toasts.slice(-1)[0]);
check('/code 99 (out of range) toasts warning',
  t99 && /범위 밖|range/i.test(t99.m), JSON.stringify(t99));

// 4. /help lists /code
await page.evaluate(() => _lcChatSlashCommand('/help'));
await page.waitForTimeout(150);
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /code', /\/code/.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
