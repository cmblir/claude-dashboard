#!/usr/bin/env node
/**
 * QQ207 — `/run <id|name>` kicks off a workflow from chat. Resolves
 * by exact id, then id-prefix, then name substring (case-insensitive).
 * Ambiguous matches list options without guessing. Successful run
 * shows runId in the bubble.
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

// Track run POSTs so we can prove /run only fires on resolution
const runPosts = [];
page.on('request', req => {
  if (req.method() === 'POST' && req.url().endsWith('/api/workflows/run')) {
    let body = '';
    try { body = req.postData() || ''; } catch (_) {}
    runPosts.push(body);
  }
});

await page.goto(URL, { waitUntil: 'networkidle' });

// Seed with a name unique to this test run so repeated invocations
// don't accumulate ambiguous matches.
const uniqTag = 'runslash-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
const seed = await page.evaluate(async (tag) => {
  const r = await fetch('/api/workflows/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id: 'wf-run-test-' + Date.now(),
      name: 'qq207-' + tag,
      nodes: [
        { id: 'start',  type: 'start',  x: 100, y: 100, data: {} },
        { id: 'output', type: 'output', x: 300, y: 100, data: {} },
      ],
      edges: [{ from: 'start', fromPort: 'out', to: 'output', toPort: 'in' }],
    }),
  });
  return await r.json();
}, uniqTag);
check('test prereq: seeded workflow saved',
  seed && seed.ok, JSON.stringify(seed).slice(0, 200));

await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

async function slash(line) {
  await page.evaluate((l) => _lcChatSlashCommand(l), line);
  await page.waitForTimeout(300);
}

// 1. /run with no arg toasts usage and does NOT POST
const before1 = runPosts.length;
await page.evaluate(() => {
  window.__runToasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__runToasts.push({m, k}); return orig && orig(m, k); };
});
await slash('/run');
const usageToasts = await page.evaluate(() => window.__runToasts);
check('/run with no arg shows usage hint',
  usageToasts.some(t => /사용법|usage/i.test(t.m)),
  JSON.stringify(usageToasts));
check('/run with no arg does NOT POST',
  runPosts.length === before1, `posts=${runPosts.length - before1}`);

// 2. /run <unique substring of name> succeeds + bubble shows runId
const before2 = runPosts.length;
await slash(`/run qq207-${uniqTag}`);
await page.waitForTimeout(400);
check('/run by unique name fires POST /api/workflows/run',
  runPosts.length === before2 + 1, `posts=${runPosts.length - before2}`);
const fullText = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/run success bubble shows runId',
  /실행 id.*run-/.test(fullText));
check('/run success bubble points to /go workflows',
  /\/go workflows/.test(fullText));

// 3. /run with non-matching arg → no POST, warn toast
const before3 = runPosts.length;
await page.evaluate(() => { window.__runToasts.length = 0; });
await slash('/run no-such-workflow-zzz-xyz');
const noMatch = await page.evaluate(() => window.__runToasts);
check('/run <bogus> warns + does NOT POST',
  runPosts.length === before3 &&
  noMatch.some(t => /일치하는 워크플로우 없음/.test(t.m)),
  JSON.stringify(noMatch));

// 4. /run with ambiguous prefix → list bubble, no POST
// Seed a second workflow so 'wf-' prefix matches multiple
await page.evaluate(async () => {
  await fetch('/api/workflows/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id: 'wf-run-ambig-' + Date.now(),
      name: 'qq207-other-target',
      nodes: [{ id: 'n', type: 'start', x: 100, y: 100, data: {} }],
      edges: [],
    }),
  });
});
const before4 = runPosts.length;
// Bust the chat-side workflow list cache so the new wf is visible
await page.evaluate(() => { try { _apiCache && _apiCache.delete && _apiCache.delete('/api/workflows/list'); } catch(_){} });
await slash('/run wf-');
const fullText2 = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/run <ambiguous> shows multi-match listing',
  /여러 개 일치|multiple match|ambig/i.test(fullText2));
check('/run <ambiguous> does NOT POST',
  runPosts.length === before4, `posts=${runPosts.length - before4}`);

// 5. /help lists /run
await slash('/help');
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /run', /\/run/.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
