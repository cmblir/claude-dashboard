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

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
