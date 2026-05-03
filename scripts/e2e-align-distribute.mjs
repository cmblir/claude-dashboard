#!/usr/bin/env node
/**
 * QQ34 — align / distribute toolbar appears on 2+ multi-select and
 * each mode reshapes the selected nodes correctly.
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
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1200 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('#wfCanvasHost', { timeout: 8000 });

// Build a workflow with 3 nodes at varying x/y so each mode has a
// detectable effect.
async function reset() {
  await page.evaluate(() => {
    const wf = {
      id: 'wf-align',
      name: 'align',
      nodes: [
        { id: 'n-a', type: 'session', x: 100, y: 100, title: 'A', data: { subject: 'a' } },
        { id: 'n-b', type: 'session', x: 250, y: 200, title: 'B', data: { subject: 'b' } },
        { id: 'n-c', type: 'session', x: 480, y: 350, title: 'C', data: { subject: 'c' } },
      ],
      edges: [],
      viewport: { panX: 0, panY: 0, zoom: 1 },
    };
    __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
    __wf.workflows.unshift({ ...wf, nodeCount: 3, edgeCount: 0, stickyCount: 0,
                             tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                             updatedAt: Date.now(), createdAt: Date.now() });
    __wf.current = wf;
    __wfMultiSelected.clear();
    __wfMultiSelected.add('n-a');
    __wfMultiSelected.add('n-b');
    __wfMultiSelected.add('n-c');
    __wf._forceFullCanvasRebuild = true;
    if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
    else _wfRenderCanvas();
    if (typeof _wfSyncMultiSelectClasses === 'function') _wfSyncMultiSelectClasses();
  });
  await page.waitForTimeout(80);
}

await reset();

// Toolbar visibility check.
const barShown = await page.evaluate(() => {
  const bar = document.getElementById('wfAlignBar');
  return bar && bar.style.display !== 'none';
});
check('alignment bar visible with 3 multi-selected', barShown);

// "left" — all nodes get x = min(x).
await page.evaluate(() => _wfAlignSelected('left'));
await page.waitForTimeout(60);
const xs = await page.evaluate(() => __wf.current.nodes.map(n => n.x));
check('left → all nodes share min x (100)', xs.every(x => x === 100));

await reset();
// "vcenter" — all nodes get y = average.
await page.evaluate(() => _wfAlignSelected('vcenter'));
await page.waitForTimeout(60);
const ys = await page.evaluate(() => __wf.current.nodes.map(n => n.y));
const avg = (100 + 200 + 350) / 3;
check('vcenter → all nodes share rounded average y',
  ys.every(y => Math.abs(y - Math.round(avg)) <= 1));

await reset();
// "hdist" — distribute horizontally so the middle node lands at midpoint.
await page.evaluate(() => _wfAlignSelected('hdist'));
await page.waitForTimeout(60);
const distX = await page.evaluate(() => {
  const m = {};
  for (const n of __wf.current.nodes) m[n.id] = n.x;
  return m;
});
const x0 = 100, x1 = 480;
const expectedB = Math.round(x0 + (x1 - x0) / 2);
check('hdist → A stays at min, C stays at max, B ≈ midpoint',
  distX['n-a'] === x0 && distX['n-c'] === x1 &&
  Math.abs(distX['n-b'] - expectedB) <= 1);

await reset();
// "right" — all nodes get x = max(x).
await page.evaluate(() => _wfAlignSelected('right'));
await page.waitForTimeout(60);
const xs2 = await page.evaluate(() => __wf.current.nodes.map(n => n.x));
check('right → all nodes share max x (480)', xs2.every(x => x === 480));

// Hide bar when selection drops below 2.
await page.evaluate(() => {
  __wfMultiSelected.clear();
  __wfMultiSelected.add('n-a');
  if (typeof _wfSyncMultiSelectClasses === 'function') _wfSyncMultiSelectClasses();
});
await page.waitForTimeout(80);
const hidden = await page.evaluate(() => {
  const bar = document.getElementById('wfAlignBar');
  return bar && bar.style.display === 'none';
});
check('alignment bar hides when only 1 node selected', hidden);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
