#!/usr/bin/env node
/**
 * QQ126 — Tab autocomplete inside the chat composer learns about every
 * slash command added since QQ62. Verifies:
 *   /co<Tab>       → cycles between /cost, /copy
 *   /the<Tab>      → /theme  (single match)
 *   /xyz<Tab>      → no change (no match)
 *   /se<Tab><Tab>  → cycles /sessions ↔ /set-something? we have no /set;
 *                    so 1 match, repeated Tab is a no-op
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

// Helper — set composer to seed, focus it, send Tab, return result.
async function tab(seed, times = 1) {
  await page.evaluate((s) => {
    const ta = document.getElementById('lcChatInput');
    ta.focus();
    ta.value = s;
    ta.selectionStart = ta.selectionEnd = s.length;
    // Reset the cycle state so each test starts fresh.
    window.__lcTabCycle = null;
  }, seed);
  for (let i = 0; i < times; i++) {
    await page.keyboard.press('Tab');
    await page.waitForTimeout(30);
  }
  return await page.evaluate(() => document.getElementById('lcChatInput').value);
}

// 1. /the → /theme (single match, expands)
const r1 = await tab('/the');
check('/the<Tab> expands to /theme', r1 === '/theme', `got="${r1}"`);

// 2. /co<Tab> → cycles between cost / copy / code (QQ171 added /code).
const r2a = await tab('/co');
const r2b = await tab('/co', 2);
check('/co<Tab> picks one of /cost, /copy, /code',
  ['/cost', '/copy', '/code'].includes(r2a), `first=${r2a}`);
check('/co<Tab><Tab> moves to a different candidate',
  r2a !== r2b && ['/cost', '/copy', '/code'].includes(r2b),
  `first=${r2a} second=${r2b}`);

// 3. /xyz → no match → unchanged
const r3 = await tab('/xyz');
check('/xyz<Tab> leaves input unchanged', r3 === '/xyz', `got="${r3}"`);

// 4. /se<Tab> → /sessions (only one match)
const r4 = await tab('/se');
check('/se<Tab> expands to /sessions', r4 === '/sessions', `got="${r4}"`);

// 5. /go and /open are tabbable
const r5 = await tab('/g');
check('/g<Tab> expands to /go', r5 === '/go', `got="${r5}"`);

const r6 = await tab('/op');
check('/op<Tab> expands to /open', r6 === '/open', `got="${r6}"`);

// 7. /retry and /regenerate both tabbable
const r7a = await tab('/re');
const r7b = await tab('/re', 2);
const r7c = await tab('/re', 3);
const set = new Set([r7a, r7b, r7c]);
// /re prefix matches: rename, retry, regenerate → 3 candidates
check('/re<Tab> cycles through rename/retry/regenerate',
  set.has('/rename') && set.has('/retry') && set.has('/regenerate'),
  `seen=${[...set].join(',')}`);

// 8. /v<Tab> expands to /version (QQ151).
const r8 = await tab('/v');
check('/v<Tab> expands to /version', r8 === '/version', `got="${r8}"`);

// 9. /co<Tab>×3 now cycles cost / copy / code (QQ171).
const seen = new Set();
seen.add(await tab('/co', 1));
seen.add(await tab('/co', 2));
seen.add(await tab('/co', 3));
check('/co<Tab>×3 cycles cost / copy / code',
  seen.has('/cost') && seen.has('/copy') && seen.has('/code'),
  `seen=${[...seen].join(',')}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
