#!/usr/bin/env node
/**
 * QQ29 — Cmd+C / Cmd+V copies all multi-selected nodes plus the
 * edges that lie within the selection, with edge endpoints remapped
 * to the freshly minted node ids.
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

// Build a workflow with 3 nodes + 2 edges (a→b inside selection,
// b→c crossing out).  Multi-select n-a + n-b only, so c stays
// out and the b→c edge must NOT get copied.
await page.evaluate(() => {
  const wf = {
    id: 'wf-cp',
    name: 'cp-test',
    nodes: [
      { id: 'n-a', type: 'session', x: 100, y: 100, title: 'A', data: { subject: 'a' } },
      { id: 'n-b', type: 'session', x: 320, y: 100, title: 'B', data: { subject: 'b' } },
      { id: 'n-c', type: 'session', x: 540, y: 100, title: 'C', data: { subject: 'c' } },
    ],
    edges: [
      { id: 'e-ab', from: 'n-a', fromPort: 'out', to: 'n-b', toPort: 'in' },
      { id: 'e-bc', from: 'n-b', fromPort: 'out', to: 'n-c', toPort: 'in' },
    ],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 3, edgeCount: 2, stickyCount: 0,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wfMultiSelected.clear();
  __wfMultiSelected.add('n-a');
  __wfMultiSelected.add('n-b');
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
  if (typeof _wfSyncMultiSelectClasses === 'function') _wfSyncMultiSelectClasses();
});
await page.waitForTimeout(80);

// Cmd+C — must hit the canvas-level shortcut, not type into an input.
await page.evaluate(() => document.body.focus());
await page.keyboard.press('Meta+c');
await page.waitForTimeout(60);

const clip = await page.evaluate(() => ({
  nodes: (__wf._clipboard || []).map(n => n.id),
  edges: (__wf._clipboardEdges || []).map(e => ({ from: e.from, to: e.to })),
}));
check('clipboard contains n-a + n-b', clip.nodes.length === 2 &&
  clip.nodes.includes('n-a') && clip.nodes.includes('n-b'));
check('clipboard contains the internal a→b edge only',
  clip.edges.length === 1 &&
  clip.edges[0].from === 'n-a' && clip.edges[0].to === 'n-b');

// Cmd+V — paste; new node ids must NOT collide with originals; the
// remapped edge must connect the new pair, not the originals.
await page.keyboard.press('Meta+v');
await page.waitForTimeout(120);

const after = await page.evaluate(() => ({
  nodes: __wf.current.nodes.map(n => ({ id: n.id, x: n.x, y: n.y })),
  edges: __wf.current.edges.map(e => ({ id: e.id, from: e.from, to: e.to })),
  multiSize: __wfMultiSelected.size,
  multi: Array.from(__wfMultiSelected),
}));

const originals = new Set(['n-a', 'n-b', 'n-c']);
const pastedNodes = after.nodes.filter(n => !originals.has(n.id));
check('2 new nodes appended after paste', pastedNodes.length === 2);

const originalEdges = new Set(['e-ab', 'e-bc']);
const newEdges = after.edges.filter(e => !originalEdges.has(e.id));
check('1 new edge appended (remapped a→b copy)', newEdges.length === 1);

if (newEdges.length === 1) {
  const newEdge = newEdges[0];
  const newIds = new Set(pastedNodes.map(n => n.id));
  check('new edge endpoints both inside the new pasted set',
    newIds.has(newEdge.from) && newIds.has(newEdge.to),
    `edge: ${newEdge.from} → ${newEdge.to}`);
}

check('pasted set becomes the new multi-selection',
  after.multiSize === 2 &&
  pastedNodes.every(n => after.multi.includes(n.id)));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
