#!/usr/bin/env node
/**
 * QQ129 — Cmd/Ctrl+X cuts the multi-selected nodes (and their internal
 * edges) into __wf._clipboard so a follow-up Cmd+V can paste them
 * back. n8n parity.
 *
 *   - 3 nodes A→B→C, multi-select A+B, Cmd+X
 *   - canvas drops to 1 node (C)
 *   - clipboard holds 2 nodes + 1 edge (a→b)
 *   - Cmd+V pastes 2 nodes back (with offset) and re-wires the edge
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
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('.wf-canvas, #wfCanvas', { timeout: 8000 });

await page.evaluate(() => {
  __wf.current = {
    id: 'wf-cut-' + Date.now(),
    name: 'cut',
    nodes: [
      { id: 'n-a', type: 'session', x: 100, y: 200, data: { subject: 'A', assignee: 'claude:opus' } },
      { id: 'n-b', type: 'session', x: 300, y: 200, data: { subject: 'B', assignee: 'claude:opus' } },
      { id: 'n-c', type: 'session', x: 500, y: 200, data: { subject: 'C', assignee: 'claude:opus' } },
    ],
    edges: [
      { id: 'e-ab', from: 'n-a', to: 'n-b' },
      { id: 'e-bc', from: 'n-b', to: 'n-c' },
    ],
  };
  __wf.dirty = true;
  _wfRenderCanvas();
  __wfMultiSelected.clear();
  __wfMultiSelected.add('n-a');
  __wfMultiSelected.add('n-b');
  __wf.selectedNodeId = null;
  _wfSyncMultiSelectClasses();
});

await page.keyboard.press('Meta+KeyX');
await page.waitForTimeout(180);

const afterCut = await page.evaluate(() => ({
  total:        __wf.current.nodes.length,
  ids:          __wf.current.nodes.map(n => n.id),
  edgeCount:    (__wf.current.edges || []).length,
  clipNodes:    (__wf._clipboard || []).length,
  clipEdges:    (__wf._clipboardEdges || []).length,
  selected:     Array.from(__wfMultiSelected || []),
}));

check('cut leaves only n-c on canvas',
  afterCut.total === 1 && afterCut.ids[0] === 'n-c',
  `total=${afterCut.total}`);
check('cut removes internal edges (a→b) and dangling (b→c)',
  afterCut.edgeCount === 0,
  `edges=${afterCut.edgeCount}`);
check('clipboard holds 2 nodes',
  afterCut.clipNodes === 2,
  `nodes=${afterCut.clipNodes}`);
check('clipboard holds 1 internal edge (a→b)',
  afterCut.clipEdges === 1,
  `edges=${afterCut.clipEdges}`);
check('selection cleared after cut',
  afterCut.selected.length === 0);

// Now paste — should land 2 nodes + 1 edge with +40 offset.
await page.keyboard.press('Meta+KeyV');
await page.waitForTimeout(180);

const afterPaste = await page.evaluate(() => ({
  total:        __wf.current.nodes.length,
  edgeCount:    (__wf.current.edges || []).length,
  newSelected:  Array.from(__wfMultiSelected || []),
}));

check('paste restores 3 total nodes (1 surviving + 2 pasted)',
  afterPaste.total === 3,
  `total=${afterPaste.total}`);
check('paste re-wires the internal edge', afterPaste.edgeCount === 1);
check('pasted set is the new multi-selection',
  afterPaste.newSelected.length === 2,
  `sel=${afterPaste.newSelected.length}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
