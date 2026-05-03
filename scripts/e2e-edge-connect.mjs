#!/usr/bin/env node
/**
 * Edge connection — calling `_wfAddEdge(from, fromPort, to, 'in')`
 * appends a new edge, prevents self-loop, prevents duplicate, and
 * rejects cycles.
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

// Build 2 nodes, no edges yet.
await page.evaluate(() => {
  const wf = {
    id: 'wf-edge',
    name: 'edge-test',
    nodes: [
      { id: 'n-a', type: 'start',   x: 80,  y: 100, data: {} },
      { id: 'n-b', type: 'session', x: 320, y: 100, title: 'B', data: { subject: 'b' } },
    ],
    edges: [],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 2, edgeCount: 0, stickyCount: 0,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
});
await page.waitForTimeout(120);

// Step 1 — happy path: add a→b.
const ok1 = await page.evaluate(() =>
  _wfAddEdge('n-a', 'out', 'n-b', 'in'));
check('a → b connect succeeds', ok1 === true);
check('edges.length === 1',
  await page.evaluate(() => __wf.current.edges.length) === 1);

// Step 2 — duplicate: same connection again returns false.
const ok2 = await page.evaluate(() =>
  _wfAddEdge('n-a', 'out', 'n-b', 'in'));
check('duplicate connect returns false', ok2 === false);
check('edges still length 1',
  await page.evaluate(() => __wf.current.edges.length) === 1);

// Step 3 — self-loop: a → a returns false.
const ok3 = await page.evaluate(() =>
  _wfAddEdge('n-a', 'out', 'n-a', 'in'));
check('self-loop rejected', ok3 === false);

// Step 4 — cycle: b → a (since a → b already exists) returns false.
const ok4 = await page.evaluate(() =>
  _wfAddEdge('n-b', 'out', 'n-a', 'in'));
check('cycle rejected', ok4 === false);
check('edges still length 1 after cycle attempt',
  await page.evaluate(() => __wf.current.edges.length) === 1);

// Step 5 — canvas renders one edge path element. _wfAddEdge calls
// _wfRenderCanvas which is RAF-coalesced; wait one frame so the DOM
// catches up before querying.
await page.waitForTimeout(100);
const pathCount = await page.evaluate(() =>
  document.querySelectorAll('#wfEdges path.wf-edge').length);
check('canvas renders 1 edge path', pathCount === 1);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
