#!/usr/bin/env node
/**
 * QQ116 — chat slash commands /cost · /status · /rename:
 *
 * 1. Seed a session with a couple of fake assistant messages whose
 *    tokensIn/tokensOut/costUsd are populated, then run /cost — the
 *    next assistant bubble must contain the totals.
 * 2. /status posts an assistant bubble naming assignee + session label.
 * 3. /rename Foo bar updates the session label in storage.
 * 4. /help now lists /cost, /status, /rename.
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
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

// Seed a fresh session with two fake assistant messages carrying token + cost.
await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  const id = _lcCurrentId();
  const h = [
    { role: 'user',      text: 'hi', ts: 1, assignee: 'claude:opus' },
    { role: 'assistant', text: 'hello', ts: 2, assignee: 'claude:opus',
      tokensIn: 100, tokensOut: 50, costUsd: 0.0012 },
    { role: 'user',      text: 'more', ts: 3, assignee: 'claude:opus' },
    { role: 'assistant', text: 'ok',   ts: 4, assignee: 'claude:opus',
      tokensIn: 200, tokensOut: 75, costUsd: 0.0034 },
  ];
  _lcSaveHistory(id, h);
  _lcChatRender();
});

// Helper: invoke slash command via the existing entry-point.
async function slash(line) {
  await page.evaluate((l) => {
    const ta = document.getElementById('lcChatInput');
    ta.value = l;
    return _lcChatSlashCommand(l);
  }, line);
  await page.waitForTimeout(120);
}

// 1. /cost
await slash('/cost');
const lastCost = await page.evaluate(() => {
  const log = document.getElementById('lcChatLog');
  return log ? log.innerHTML : '';
});
check('/cost shows total input tokens (300)',
  /300/.test(lastCost));
check('/cost shows total output tokens (125)',
  /125/.test(lastCost));
check('/cost shows cumulative USD',
  /\$0\.0046/.test(lastCost) || /0\.004/.test(lastCost));

// QQ177 — /cost on a session with no token meta shows '$0' + a helpful
// note instead of '$0.000000' which looked like a bug.
await page.evaluate(() => {
  const id = _lcCurrentId();
  _lcSaveHistory(id, [
    { role: 'user', text: 'hi', ts: 1, assignee: 'claude:opus' },
    { role: 'assistant', text: 'hello', ts: 2, assignee: 'claude:opus' },
  ]);
  _lcChatRender();
});
await slash('/cost');
const zeroCost = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/cost on no-meta session shows "$0" not "$0.000000"',
  /\$0\b/.test(zeroCost) && !/\$0\.000000/.test(zeroCost));
check('/cost on no-meta session shows the metadata-missing note',
  /토큰·비용 메타데이터|metadata/i.test(zeroCost));

// 2. /status
await slash('/status');
const stat = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/status mentions assignee claude:opus', /claude:opus/.test(stat));

// 3. /rename
await slash('/rename ProjectAlpha');
const renamed = await page.evaluate(() => {
  const id = _lcCurrentId();
  const s = (_lcGetSessions() || []).find(x => x.id === id);
  return s ? s.label : null;
});
check('/rename updates session label', renamed === 'ProjectAlpha', `label=${renamed}`);

// 4. /agents lists registered assignees
await slash('/agents');
const agentsOut = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/agents lists current assignee claude:opus',
  /claude:opus/.test(agentsOut));
check('/agents marks current selection with ➜', /➜/.test(agentsOut));

// QQ183 — /copy falls back to document.execCommand when the async
// Clipboard API isn't available (e.g. permission denied, http-only
// origin, or older browsers).
{
  const beforeRm = await page.evaluate(() => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    return navigator.clipboard;
  });
  await page.evaluate(() => {
    const id = _lcCurrentId();
    _lcSaveHistory(id, [
      { role: 'user', text: 'q', ts: 1, assignee: 'claude:opus' },
      { role: 'assistant', text: 'FALLBACK-MARKER', ts: 2, assignee: 'claude:opus' },
    ]);
    window.__fallbackToasts = [];
    const orig = window.toast;
    window.toast = (m, k) => { window.__fallbackToasts.push({m,k}); return orig && orig(m, k); };
  });
  await slash('/copy');
  await page.waitForTimeout(200);
  const t = await page.evaluate(() => window.__fallbackToasts.slice(-1)[0]);
  check('/copy falls back to execCommand when clipboard API is undefined',
    t && /복사됨|copied/i.test(t.m), JSON.stringify(t));
  // Re-grant for any later tests on this page.
  await page.evaluate(() => {
    delete navigator.clipboard;  // best-effort restore — gone but tests ahead don't depend
  });
}

// QQ185 — /copy N out-of-range gets the dedicated "범위 밖" toast
//          rather than the generic "복사할 응답이 없습니다".
{
  await page.evaluate(() => {
    const id = _lcCurrentId();
    _lcSaveHistory(id, [
      { role: 'user',      text: 'q', ts: 1, assignee: 'claude:opus' },
      { role: 'assistant', text: 'a', ts: 2, assignee: 'claude:opus' },
    ]);
    window.__rangeToasts = [];
    const orig = window.toast;
    window.toast = (m, k) => { window.__rangeToasts.push({m,k}); return orig && orig(m, k); };
  });
  await slash('/copy 99');
  const tt = await page.evaluate(() => window.__rangeToasts.slice(-1)[0]);
  check('/copy 99 toasts "범위 밖" with the available count',
    tt && /범위 밖|range/i.test(tt.m) && /\b1\b/.test(tt.m),
    JSON.stringify(tt));
}

// 4a-pre. /copy copies the last assistant reply
try { await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: URL.replace(/\/$/, '') }); } catch (_) {}
// Re-seed with a known-last assistant reply so we can assert exact match.
await page.evaluate(() => {
  const id = _lcCurrentId();
  const h = _lcGetHistory(id);
  h.push({ role: 'assistant', text: 'COPY-MARKER-LMNO', assignee: 'claude:opus', ts: Date.now() });
  _lcSaveHistory(id, h);
  _lcChatRender();
});
await slash('/copy');
await page.waitForTimeout(200);
const clip = await page.evaluate(async () => {
  try { return await navigator.clipboard.readText(); }
  catch (_) { return null; }
});
check('/copy puts last assistant reply on clipboard',
  clip === 'COPY-MARKER-LMNO',
  clip === null ? 'clipboard read denied (headless permission)' : `clip="${(clip || '').slice(0, 50)}"`);

// 4a-bis. /theme toggles dark↔light without args
const beforeTheme = await page.evaluate(() => document.body.classList.contains('theme-light'));
await slash('/theme');
await page.waitForTimeout(200);
const afterTheme = await page.evaluate(() => document.body.classList.contains('theme-light'));
check('/theme without args toggles theme-light',
  beforeTheme !== afterTheme, `before=${beforeTheme} after=${afterTheme}`);

// /theme dark forces dark explicitly
await slash('/theme dark');
await page.waitForTimeout(150);
const dark = await page.evaluate(() => document.body.classList.contains('theme-light'));
check('/theme dark removes theme-light class', dark === false);

// 4b. /sessions lists current sessions with message counts
await slash('/sessions');
const sessOut = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/sessions shows the active session with ➜', /➜/.test(sessOut));
// We seeded 4 history entries above + several /-bubbles; expect a non-zero
// message count to render.
check('/sessions includes a message count', /\d+\s*메시지|\d+\s*messages|\d+\s*消息/.test(sessOut) || /\d+ 메시지/.test(sessOut));

// 5. /help lists the new commands
await slash('/help');
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /cost',   /\/cost/.test(help));
check('/help lists /status', /\/status/.test(help));
check('/help lists /rename', /\/rename/.test(help));
check('/help lists /agents', /\/agents/.test(help));
check('/help lists /sessions', /\/sessions/.test(help));
check('/help lists /theme',    /\/theme/.test(help));
check('/help lists /lang',     /\/lang/.test(help));
check('/help lists /copy',     /\/copy/.test(help));
check('/help lists /retry',    /\/retry/.test(help));
check('/help lists /version',  /\/version/.test(help));

// 8. /version posts a LazyClaude info bubble
await slash('/version');
await page.waitForTimeout(300);
const verLog = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/version mentions LazyClaude header', /LazyClaude/.test(verLog));
check('/version includes version label', /\b버전\b|version/i.test(verLog));

// 7. /retry trims trailing assistant replies and queues the last user msg.
//    Run AFTER /theme (which schedules a deferred renderView) has fully
//    settled — wait long enough for both 550ms theme-switch timers to
//    fire and the chat AFTER hook to re-bind the textarea.
await page.waitForTimeout(1300);
await page.waitForFunction(() => !!document.getElementById('lcChatInput'), { timeout: 3000 });
await page.evaluate(() => {
  // Reset to a known shape: U,A,U,A
  const id = _lcCurrentId();
  _lcSaveHistory(id, [
    { role: 'user',      text: 'q1', ts: 1, assignee: 'claude:opus' },
    { role: 'assistant', text: 'a1', ts: 2, assignee: 'claude:opus' },
    { role: 'user',      text: 'q2-LASTUSER', ts: 3, assignee: 'claude:opus' },
    { role: 'assistant', text: 'a2', ts: 4, assignee: 'claude:opus' },
  ]);
  _lcChatRender();
  // Stub the send so we don't hit /api/lazyclaw/chat in headless.
  window.__sendCalled = false;
  window._lcChatSend = async () => { window.__sendCalled = true; };
});
await slash('/retry');
await page.waitForTimeout(250);
const retryProbe = await page.evaluate(() => {
  const id = _lcCurrentId();
  const ta = document.getElementById('lcChatInput');
  return {
    hist: _lcGetHistory(id).map(m => m.text),
    input: ta ? ta.value : '<no-input>',
    sent: window.__sendCalled,
  };
});
check('/retry trimmed history at last user msg',
  retryProbe.hist.length === 3 && retryProbe.hist[2] === 'q2-LASTUSER');
check('/retry repopulated the composer with last user text',
  retryProbe.input === 'q2-LASTUSER', `input="${retryProbe.input}"`);
check('/retry called _lcChatSend', retryProbe.sent === true);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
