#!/usr/bin/env node
/**
 * QQ127 — Cmd/Ctrl+D duplicates ALL multi-selected nodes (not just
 * the last-clicked one). Preserves the +40px offset and clones any
 * edge whose endpoints both live in the duplicated set so the
 * sub-graph stays wired (n8n parity).
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

// Seed: two session nodes with one edge between them.
await page.evaluate(() => {
  __wf.current = {
    id: 'wf-multi-dup-' + Date.now(),
    name: 'multi-dup',
    nodes: [
      { id: 'n-a', type: 'session',  x: 100, y: 100, data: { subject: 'A', assignee: 'claude:opus' } },
      { id: 'n-b', type: 'session',  x: 300, y: 100, data: { subject: 'B', assignee: 'claude:opus' } },
      { id: 'n-c', type: 'session',  x: 500, y: 100, data: { subject: 'C', assignee: 'claude:opus' } },
    ],
    edges: [
      { id: 'e-ab', from: 'n-a', to: 'n-b' },
      { id: 'e-bc', from: 'n-b', to: 'n-c' },
    ],
  };
  __wf.dirty = true;
  _wfRenderCanvas();
  // Multi-select n-a + n-b (NOT n-c)
  if (!window.__wfMultiSelected) window.__wfMultiSelected = new Set();
  __wfMultiSelected.clear();
  __wfMultiSelected.add('n-a');
  __wfMultiSelected.add('n-b');
  __wf.selectedNodeId = null;
  if (typeof _wfSyncMultiSelectClasses === 'function') _wfSyncMultiSelectClasses();
});

// Press Cmd+D (Meta on macOS, Ctrl elsewhere — both registered).
await page.keyboard.press('Meta+KeyD');
await page.waitForTimeout(180);

const after = await page.evaluate(() => ({
  nodes: __wf.current.nodes.map(n => ({ id: n.id, type: n.type, x: n.x, y: n.y, subject: n.data && n.data.subject })),
  edges: (__wf.current.edges || []).map(e => ({ from: e.from, to: e.to })),
  selected: Array.from(__wfMultiSelected || []),
}));

// Original 3 + 2 clones = 5
check('5 nodes after duplicating 2-of-3', after.nodes.length === 5, `count=${after.nodes.length}`);

// Two clones with subjects A / B at (140,140) / (340,140)
const clones = after.nodes.filter(n => !['n-a','n-b','n-c'].includes(n.id));
check('two clones produced', clones.length === 2, `clones=${clones.length}`);
const clonedSubjects = clones.map(c => c.subject).sort();
check('clones preserve subjects A, B',
  clonedSubjects.join(',') === 'A,B', `subj=${clonedSubjects}`);
const aClone = clones.find(c => c.subject === 'A');
const bClone = clones.find(c => c.subject === 'B');
check('A clone offset by +40,+40',
  aClone && aClone.x === 140 && aClone.y === 140);
check('B clone offset by +40,+40',
  bClone && bClone.x === 340 && bClone.y === 140);

// Edge n-a→n-b must be cloned to aClone→bClone (both endpoints in dup set);
// edge n-b→n-c must NOT be cloned (n-c wasn't selected).
const newEdge = after.edges.find(e => e.from === aClone.id && e.to === bClone.id);
check('a→b edge cloned alongside the nodes', !!newEdge);
const ghostEdge = after.edges.find(e => e.from === bClone.id && e.to === 'n-c');
check('b→c edge NOT cloned (n-c was unselected)', !ghostEdge);

// New multi-selection should contain ONLY the clones
check('multi-selection now points to the clones',
  after.selected.length === 2
    && after.selected.includes(aClone.id)
    && after.selected.includes(bClone.id),
  `sel=${after.selected.join(',')}`);

// QQ128 — ctx-menu '복제' should also use the multi-aware helper.
// Reset to a clean 3-node graph and multi-select n-a + n-b again.
await page.evaluate(() => {
  __wf.current = {
    id: 'wf-ctx-dup-' + Date.now(),
    name: 'ctx-dup',
    nodes: [
      { id: 'n-a', type: 'session',  x: 100, y: 200, data: { subject: 'A', assignee: 'claude:opus' } },
      { id: 'n-b', type: 'session',  x: 300, y: 200, data: { subject: 'B', assignee: 'claude:opus' } },
      { id: 'n-c', type: 'session',  x: 500, y: 200, data: { subject: 'C', assignee: 'claude:opus' } },
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
  // Open the ctx menu programmatically and click the 복제 item — we
  // can't reliably synthesise a real right-click on the SVG node here
  // without dealing with viewport coords, so we drive the rendered
  // menu directly.
  _wfShowNodeContextMenu('n-a', 200, 200);
});

// Click the 복제 row (it's the second row after Edit).
const dupClicked = await page.evaluate(() => {
  const menu = document.getElementById('wfNodeCtxMenu');
  if (!menu) return false;
  const rows = Array.from(menu.querySelectorAll('div'));
  // Find the row whose text starts with the duplicate emoji or label.
  const row = rows.find(el => /복제|Duplicate|复制/.test(el.textContent || ''));
  if (!row) return false;
  row.click();
  return true;
});
check('ctx-menu 복제 row found + clicked', dupClicked);
await page.waitForTimeout(150);

const ctxAfter = await page.evaluate(() => ({
  total:    __wf.current.nodes.length,
  selected: Array.from(__wfMultiSelected || []),
}));
check('ctx-menu duplicate cloned BOTH multi-selected nodes',
  ctxAfter.total === 5,
  `total=${ctxAfter.total}`);
check('ctx-menu duplicate updated multi-selection to the new clones',
  ctxAfter.selected.length === 2,
  `selected=${ctxAfter.selected.length}`);

// QQ158 — verify Cmd+Z undoes the multi-duplicate atomically.
await page.evaluate(() => {
  __wf.current = {
    id: 'wf-dup-undo-' + Date.now(),
    name: 'dup-undo',
    nodes: [
      { id: 'n-1', type: 'session', x: 100, y: 300, data: { subject: '1', assignee: 'claude:opus' } },
      { id: 'n-2', type: 'session', x: 300, y: 300, data: { subject: '2', assignee: 'claude:opus' } },
    ],
    edges: [{ id: 'e-12', from: 'n-1', to: 'n-2' }],
  };
  __wf._undoStack = [];
  _wfRenderCanvas();
  __wfMultiSelected.clear();
  __wfMultiSelected.add('n-1');
  __wfMultiSelected.add('n-2');
  __wf.selectedNodeId = null;
  _wfSyncMultiSelectClasses();
});

await page.keyboard.press('Meta+KeyD');
await page.waitForTimeout(150);

const dupd = await page.evaluate(() => __wf.current.nodes.length);
check('multi-duplicate creates 2 clones (4 total)', dupd === 4, `count=${dupd}`);

await page.keyboard.press('Meta+KeyZ');
await page.waitForTimeout(150);

const undone = await page.evaluate(() => ({
  count: __wf.current.nodes.length,
  ids: __wf.current.nodes.map(n => n.id).sort(),
}));
check('Cmd+Z reverts the multi-duplicate atomically',
  undone.count === 2 && undone.ids.join(',') === 'n-1,n-2',
  `count=${undone.count} ids=${undone.ids}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
