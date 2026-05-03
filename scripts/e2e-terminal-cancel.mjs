#!/usr/bin/env node
/**
 * QQ210 — terminal `lazyclaude cancel` parity with chat /cancel.
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

const cancelPosts = [];
page.on('request', req => {
  if (req.method() === 'POST' && req.url().endsWith('/api/workflows/run-cancel')) {
    cancelPosts.push(req.postData() || '');
  }
});

await page.goto(URL, { waitUntil: 'networkidle' });

const uniqTag = 'cancelterm-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
const seed = await page.evaluate(async (tag) => {
  const r = await fetch('/api/workflows/save', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'qq210-' + tag,
      nodes: [{ id: 'start', type: 'start', x: 100, y: 100, data: {} }],
      edges: [],
    }),
  });
  return await r.json();
}, uniqTag);
check('seed: workflow saved', seed && seed.ok);
const seedId = seed && seed.id;

const runResp = await page.evaluate(async (id) => {
  const r = await fetch('/api/workflows/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  });
  return await r.json();
}, seedId);
check('seed: run started', runResp && runResp.ok && runResp.runId);
const liveRunId = runResp.runId;

await page.evaluate(() => window.go('lazyclawTerm'));
await page.waitForSelector('#lcTermInput', { timeout: 8000 });
await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS.ui, { timeout: 8000 });
await page.waitForFunction(() =>
  /헬스체크 완료/.test((document.getElementById('lcTermLog') || {}).textContent || ''),
  { timeout: 12000 }).catch(() => {});

async function run(cmd) {
  await page.evaluate((c) => {
    const inp = document.getElementById('lcTermInput');
    inp.value = c;
    return window._lcTermRun();
  }, cmd);
  await page.waitForTimeout(350);
}
const fullLog = async () => await page.evaluate(() => (document.getElementById('lcTermLog') || {}).textContent || '');

// 1. lazyclaude cancel (no arg) — either lists or "no running"
await run('lazyclaude cancel');
const noArgOut = await fullLog();
check('lazyclaude cancel (no arg) prints list or no-running line',
  /Running runs|no workflows currently running/i.test(noArgOut));

// 2. lazyclaude cancel <bogus> — ⚠
await run('lazyclaude cancel no-such-zzz');
const bogusOut = await fullLog();
check('lazyclaude cancel <bogus> prints ⚠ no-match',
  /⚠.*일치하는 실행 없음/.test(bogusOut));

// 3. lazyclaude cancel <runId> — POSTs run-cancel
const before = cancelPosts.length;
await run('lazyclaude cancel ' + liveRunId);
await page.waitForTimeout(400);
check('cancel <runId> fires POST',
  cancelPosts.length === before + 1, `posts=${cancelPosts.length - before}`);
const okOut = await fullLog();
check('cancel <runId> prints "Cancel requested"',
  /Cancel requested/.test(okOut));
check('POST body includes runId',
  cancelPosts[cancelPosts.length - 1].includes(liveRunId));

// 4. lazyclaude help lists cancel
await run('lazyclaude help');
const helpOut = await fullLog();
check('help lists cancel', /lazyclaude cancel/.test(helpOut));

// 5. typo did-you-mean
await run('lazyclaude cancl');
const typoOut = await fullLog();
check('lazyclaude cancl → suggests cancel',
  /lazyclaude cancel/.test(typoOut));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
