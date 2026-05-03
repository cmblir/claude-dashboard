#!/usr/bin/env node
/**
 * QQ209 — `/cancel` lists every running workflow run; `/cancel <runId>`
 * (or wf-name unique-running) sends POST /api/workflows/run-cancel.
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

// Seed a workflow with a long-sleeping shell node so a run stays
// 'running' long enough for /cancel to hit it. Then start a run.
const uniqTag = 'cancel-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
const seed = await page.evaluate(async (tag) => {
  const r = await fetch('/api/workflows/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'qq209-' + tag,
      nodes: [
        { id: 'start', type: 'start', x: 100, y: 100, data: {} },
        { id: 'sleep', type: 'shell', x: 300, y: 100, data: { cmd: 'sleep 60', timeoutSec: 120 } },
        { id: 'out',   type: 'output', x: 500, y: 100, data: {} },
      ],
      edges: [
        { from: 'start', fromPort: 'out', to: 'sleep', toPort: 'in' },
        { from: 'sleep', fromPort: 'out', to: 'out',   toPort: 'in' },
      ],
    }),
  });
  return await r.json();
}, uniqTag);
check('test prereq: seeded sleeping workflow', seed && seed.ok, JSON.stringify(seed).slice(0, 200));
const seedId = seed && seed.id;

// Start a run
const runResp = await page.evaluate(async (id) => {
  const r = await fetch('/api/workflows/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  });
  return await r.json();
}, seedId);
check('test prereq: started a run',
  runResp && runResp.ok && runResp.runId, JSON.stringify(runResp));
const liveRunId = runResp && runResp.runId;

// Give the orchestrator a beat to register the run
await page.waitForTimeout(400);

await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

async function slash(line) {
  await page.evaluate((l) => _lcChatSlashCommand(l), line);
  await page.waitForTimeout(300);
}

// 1. /cancel with no arg shows either the running list OR the
//    "no running" toast (depending on whether the orchestrator's
//    workflow-list cache has caught up).
await page.evaluate(() => {
  window.__listToasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__listToasts.push({m, k}); return orig && orig(m, k); };
});
await slash('/cancel');
const listText = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
const listToasts = await page.evaluate(() => window.__listToasts);
check('/cancel (no arg) renders running list OR no-running toast',
  /실행 중\s*\(\d+\)/.test(listText) ||
  listToasts.some(t => /실행 중인 워크플로우 없음/.test(t.m)));

// 2. /cancel <bogus> warns + does NOT POST
const before2 = cancelPosts.length;
await page.evaluate(() => {
  window.__cToasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__cToasts.push({m, k}); return orig && orig(m, k); };
});
await slash('/cancel no-such-zzz-xyz');
check('/cancel <bogus> does NOT POST',
  cancelPosts.length === before2, `posts=${cancelPosts.length - before2}`);
const cTo = await page.evaluate(() => window.__cToasts);
check('/cancel <bogus> warns "일치하는 실행 없음"',
  cTo.some(t => /일치하는 실행/.test(t.m)), JSON.stringify(cTo));

// 3. /cancel <runId> POSTs run-cancel + bubble shows confirmation
const before3 = cancelPosts.length;
await slash('/cancel ' + liveRunId);
await page.waitForTimeout(400);
check('/cancel <runId> fires POST /api/workflows/run-cancel',
  cancelPosts.length === before3 + 1, `posts=${cancelPosts.length - before3}`);
const fullText = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/cancel success bubble references the runId',
  fullText.includes(liveRunId));
check('/cancel POST body includes the runId',
  cancelPosts[cancelPosts.length - 1].includes(liveRunId));

// 4. /help lists /cancel
await slash('/help');
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /cancel', /\/cancel/.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
