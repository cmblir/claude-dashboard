#!/usr/bin/env node
/**
 * Workflow Undo (Cmd+Z) — _wfPushUndo snapshots nodes+edges before
 * a mutation; _wfUndo pops the latest snapshot and restores state.
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

// Build a workflow with 3 nodes + 2 edges so deletes have something
// to undo.
await page.evaluate(() => {
  const wf = {
    id: 'wf-undo',
    name: 'undo-test',
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
  __wf._undoStack = [];
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
});
await page.waitForTimeout(120);

// Setup baseline.
const before = await page.evaluate(() => ({
  nodeCount: __wf.current.nodes.length,
  edgeCount: __wf.current.edges.length,
}));
check('start with 3 nodes + 2 edges',
  before.nodeCount === 3 && before.edgeCount === 2);

// Delete n-b through the public path (selection + Delete key).
await page.evaluate(() => {
  __wf.selectedNodeId = 'n-b';
  _wfDeleteSelectedNode();
});
await page.waitForTimeout(80);

const afterDelete = await page.evaluate(() => ({
  nodeCount: __wf.current.nodes.length,
  edgeIds: __wf.current.edges.map(e => e.id),
  undoLen: (__wf._undoStack || []).length,
}));
check('after delete: 2 nodes', afterDelete.nodeCount === 2);
check('after delete: 0 edges (both incident)',
  afterDelete.edgeIds.length === 0);
check('undo stack has the pre-delete snapshot',
  afterDelete.undoLen === 1);

// Cmd+Z — invoke undo directly (function is exported, simulating
// keyboard shortcut). Restores the deleted node + edges.
await page.evaluate(() => _wfUndo());
await page.waitForTimeout(120);

const afterUndo = await page.evaluate(() => ({
  ids: __wf.current.nodes.map(n => n.id).sort(),
  edgeIds: __wf.current.edges.map(e => e.id).sort(),
  undoLen: (__wf._undoStack || []).length,
  hasBNode: !!document.querySelector('.wf-node[data-node="n-b"]'),
}));
check('undo restores n-b', afterUndo.ids.includes('n-b'));
check('undo restores both edges',
  afterUndo.edgeIds.length === 2 &&
  afterUndo.edgeIds.includes('e-ab') &&
  afterUndo.edgeIds.includes('e-bc'));
check('undo stack drained (1 → 0)', afterUndo.undoLen === 0);
check('canvas re-rendered with n-b in DOM', afterUndo.hasBNode);

// Calling undo again on empty stack should be a no-op (toast warns).
await page.evaluate(() => _wfUndo());
await page.waitForTimeout(60);
const noopState = await page.evaluate(() => __wf.current.nodes.length);
check('extra undo is a no-op', noopState === 3);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
