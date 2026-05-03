#!/usr/bin/env node
/**
 * QQ31 — every <pre> block in an assistant message gets a 📋 copy
 * button overlay.
 * QQ32 — assistant messages > 1500 chars or > 30 lines get a
 * collapsible window with `▾ 더보기` button; clicking expands.
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
// Grant clipboard permissions so navigator.clipboard.writeText works.
const ctx = await browser.newContext({
  viewport: { width: 1400, height: 900 },
  permissions: ['clipboard-read', 'clipboard-write'],
});
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

// Seed a session with a short-with-code reply (covers QQ31) and a
// long reply > 1500 chars (covers QQ32 collapse).
await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  const id = _lcCurrentId();
  const long = 'L'.repeat(1700);
  _lcSaveHistory(id, [
    { role: 'user',      text: 'q1', ts: 1, assignee: 'claude:opus' },
    { role: 'assistant', text: 'Sure, here is the code:\n\n```js\nconsole.log("hi");\n```\n\nAnd that\'s all.',
      ts: 2, assignee: 'claude:opus' },
    { role: 'user',      text: 'q2', ts: 3, assignee: 'claude:opus' },
    { role: 'assistant', text: long, ts: 4, assignee: 'claude:opus' },
  ]);
  _lcChatRender();
});
await page.waitForTimeout(150);

// QQ31 — assistant message #1 has a <pre> block + a 📋 button.
const codeBlock = await page.evaluate(() => {
  const log = document.getElementById('lcChatLog');
  const pres = Array.from(log.querySelectorAll('pre'));
  // Find the wrapper div that has both <pre> and the 📋 sibling.
  for (const pre of pres) {
    if (pre.parentElement) {
      const btn = Array.from(pre.parentElement.querySelectorAll('button'))
        .find(b => b.textContent.trim() === '📋');
      if (btn && /console\.log/.test(pre.textContent)) {
        return { hasPre: true, hasCopyBtn: !!btn, codeText: pre.querySelector('code') ? pre.querySelector('code').textContent : pre.textContent };
      }
    }
  }
  return { hasPre: false, hasCopyBtn: false };
});
check('assistant code block renders <pre>', codeBlock.hasPre);
check('QQ31 📋 copy overlay button present',  codeBlock.hasCopyBtn);
check('code text contains console.log("hi")',
  /console\.log\("hi"\)/.test(codeBlock.codeText || ''));

// Click the 📋 button → assert clipboard contents.
const clipResult = await page.evaluate(async () => {
  const log = document.getElementById('lcChatLog');
  const pres = Array.from(log.querySelectorAll('pre'));
  let btn = null;
  for (const pre of pres) {
    const candidate = pre.parentElement.querySelector('button');
    if (candidate && candidate.textContent.trim() === '📋' &&
        /console\.log/.test(pre.textContent)) {
      btn = candidate; break;
    }
  }
  if (!btn) return { ok: false };
  btn.click();
  await new Promise(r => setTimeout(r, 100));
  let read = '';
  try { read = await navigator.clipboard.readText(); } catch (_) {}
  return { ok: true, clip: read };
});
check('clicking 📋 writes code to clipboard',
  /console\.log\(/.test(clipResult.clip || ''));

// QQ32 — long reply collapses, click 더보기 to expand.
const collapseInit = await page.evaluate(() => {
  const log = document.getElementById('lcChatLog');
  // The long reply is the 4th message (idx 3). The collapse wrapper is
  // a sibling div with id starting with "_lcCollapsed_".
  const wraps = Array.from(log.querySelectorAll('[id^="_lcCollapsed_"]'));
  // Pick the largest one (the long message wrapper).
  wraps.sort((a, b) => b.scrollHeight - a.scrollHeight);
  const wrap = wraps[0];
  if (!wrap) return null;
  return {
    initiallyClamped: wrap.style.maxHeight === '300px',
    id: wrap.id,
  };
});
check('long message wraps in collapsed container (max-height 300px)',
  collapseInit && collapseInit.initiallyClamped);

// Click "더보기" — the toggle is rendered right after the wrapper.
const expanded = await page.evaluate((wrapId) => {
  const wrap = document.getElementById(wrapId);
  // The toggle button is the wrapper's sibling.
  let btn = wrap.nextElementSibling;
  while (btn && btn.tagName !== 'BUTTON') btn = btn.nextElementSibling;
  if (!btn) return { found: false };
  btn.click();
  return { found: true, maxHeight: wrap.style.maxHeight };
}, collapseInit && collapseInit.id);
check('"더보기" button clickable', expanded && expanded.found);
check('after expansion, max-height === "none"',
  expanded && expanded.maxHeight === 'none');

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
