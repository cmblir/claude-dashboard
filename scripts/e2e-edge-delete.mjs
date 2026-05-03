#!/usr/bin/env node
/**
 * LL20 — right-click an edge → context menu offers delete only.
 * Selecting + Delete key removes the selected edge.
 */
import { chromium } from 'playwright';

const PORT = process.env.PORT || '19500';
const URL  = `http://127.0.0.1:${PORT}/`;

function check(label, ok) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}`);
  if (!ok) process.exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1200 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('#wfCanvasHost', { timeout: 8000 });

await page.evaluate(() => {
  const wf = {
    id: 'wf-eddel',
    name: 'edge-delete',
    nodes: [
      { id: 'n-a', type: 'start',   x: 80,  y: 100, data: {} },
      { id: 'n-b', type: 'session', x: 320, y: 100, title: 'B', data: { subject: 'b' } },
    ],
    edges: [{ id: 'e-ab', from: 'n-a', fromPort: 'out', to: 'n-b', toPort: 'in' }],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 2, edgeCount: 1, stickyCount: 0,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
});
await page.waitForTimeout(120);

// Path A: select edge + Delete key.
const deletedViaSelection = await page.evaluate(() => {
  __wf.selectedEdgeId = 'e-ab';
  if (typeof _wfDeleteSelectedEdge === 'function') {
    _wfDeleteSelectedEdge();
    return __wf.current.edges.length;
  }
  return -1;
});
check('selection + delete removes edge', deletedViaSelection === 0);

// Path B: re-add edge, open ctx menu, click Delete.
await page.evaluate(() => {
  _wfAddEdge('n-a', 'out', 'n-b', 'in');
});
await page.waitForTimeout(120);
const beforeRC = await page.evaluate(() => __wf.current.edges.length);
check('edge re-added (length 1)', beforeRC === 1);

const menuShown = await page.evaluate(() => {
  const path = document.querySelector('#wfEdges path.wf-edge');
  if (!path) return false;
  const r = path.getBoundingClientRect();
  path.dispatchEvent(new MouseEvent('contextmenu', {
    bubbles: true, cancelable: true, view: window,
    clientX: r.x + r.width / 2, clientY: r.y + r.height / 2, button: 2,
  }));
  return !!document.getElementById('wfNodeCtxMenu');
});
check('right-click on edge opens ctx menu', menuShown);

const afterRC = await page.evaluate(() => {
  const menu = document.getElementById('wfNodeCtxMenu');
  if (!menu) return -1;
  const row = Array.from(menu.children).find(r => /삭제|Delete/.test(r.textContent || ''));
  if (!row) return -2;
  row.click();
  return __wf.current.edges.length;
});
check('clicking 삭제 in edge ctx menu removes edge', afterRC === 0);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
