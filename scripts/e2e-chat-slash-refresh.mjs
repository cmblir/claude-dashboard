#!/usr/bin/env node
/**
 * QQ216 — `/refresh` (alias `/reload`) busts the client-side API cache
 * (_apiCache Map) so the next /workflows, /agents, /keys, etc. fetches
 * fresh data. Doesn't reload the page.
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
await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

async function slash(line) {
  await page.evaluate((l) => _lcChatSlashCommand(l), line);
  await page.waitForTimeout(220);
}

// Prime the cache by hitting /workflows (uses cachedApi).
await slash('/workflows');
const beforeSize = await page.evaluate(() => {
  // _apiCache is module-scoped; reach it via cachedApi indirection.
  // Trigger a cachedApi call and inspect its Map size via global state
  // probe — we know the chat surface populates _apiCache on /workflows.
  // Easier: count requests to /api/workflows/list before vs after.
  return null;
});

// Track requests to verify cache-bust effect: after /refresh, the next
// /workflows MUST refetch.
const wfListReqs = [];
page.on('request', req => {
  if (req.url().includes('/api/workflows/list') && req.method() === 'GET') {
    wfListReqs.push(req.url());
  }
});

// 1. /workflows again (cache hot) — should NOT add a new request, since
//    _apiCache is hot from the prior call.
const beforeWarm = wfListReqs.length;
await slash('/workflows');
const warmDelta = wfListReqs.length - beforeWarm;
check('/workflows hit twice in a row → cache hot (no extra request)',
  warmDelta === 0, `delta=${warmDelta}`);

// 2. /refresh emits ok toast
await page.evaluate(() => {
  window.__refreshToasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__refreshToasts.push({m, k}); return orig && orig(m, k); };
});
await slash('/refresh');
const ts = await page.evaluate(() => window.__refreshToasts);
check('/refresh emits 캐시 비움 ok toast',
  ts.some(t => /캐시 비움/.test(t.m) && t.k === 'ok'),
  JSON.stringify(ts));

// 3. After /refresh, the next /workflows DOES re-fetch
const beforeRefetch = wfListReqs.length;
await slash('/workflows');
const refetchDelta = wfListReqs.length - beforeRefetch;
check('after /refresh, /workflows refetches',
  refetchDelta >= 1, `delta=${refetchDelta}`);

// 4. /reload alias works
await page.evaluate(() => { window.__refreshToasts.length = 0; });
await slash('/reload');
const aliasTs = await page.evaluate(() => window.__refreshToasts);
check('/reload alias also emits 캐시 비움 toast',
  aliasTs.some(t => /캐시 비움/.test(t.m)));

// 5. Tab-complete: /ref<Tab> → /refresh
await page.evaluate(() => {
  const ta = document.getElementById('lcChatInput');
  ta.value = '/ref'; ta.focus();
  ta.selectionStart = ta.selectionEnd = 4;
  window.__lcTabCycle = null;
});
await page.keyboard.press('Tab');
await page.waitForTimeout(50);
const tabResult = await page.evaluate(() => document.getElementById('lcChatInput').value);
check('/ref<Tab> → /refresh', tabResult === '/refresh', `got="${tabResult}"`);

// 6. /help lists /refresh
await slash('/help');
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /refresh', /\/refresh/.test(help));
check('/help lists /reload alias', /\/reload/.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
