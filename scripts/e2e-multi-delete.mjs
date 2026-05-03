#!/usr/bin/env node
/**
 * QQ30 — Delete / Backspace removes every node in
 * __wfMultiSelected plus all incident edges. With > 3 selected,
 * a confirm prompt appears; we auto-accept it.
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
page.on('dialog', d => d.accept());  // auto-accept QQ30 confirm

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('#wfCanvasHost', { timeout: 8000 });

// Build 4 nodes + 3 edges. Multi-select 2 of them so the confirm
// path is NOT triggered (QQ30 prompts only at >3 selected).
async function setup(selectedIds) {
  await page.evaluate((sel) => {
    const wf = {
      id: 'wf-del',
      name: 'del-test',
      nodes: [
        { id: 'n-a', type: 'session', x: 100, y: 100, title: 'A', data: { subject: 'a' } },
        { id: 'n-b', type: 'session', x: 320, y: 100, title: 'B', data: { subject: 'b' } },
        { id: 'n-c', type: 'session', x: 540, y: 100, title: 'C', data: { subject: 'c' } },
        { id: 'n-d', type: 'session', x: 760, y: 100, title: 'D', data: { subject: 'd' } },
      ],
      edges: [
        { id: 'e-ab', from: 'n-a', fromPort: 'out', to: 'n-b', toPort: 'in' },
        { id: 'e-bc', from: 'n-b', fromPort: 'out', to: 'n-c', toPort: 'in' },
        { id: 'e-cd', from: 'n-c', fromPort: 'out', to: 'n-d', toPort: 'in' },
      ],
      viewport: { panX: 0, panY: 0, zoom: 1 },
    };
    __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
    __wf.workflows.unshift({ ...wf, nodeCount: 4, edgeCount: 3, stickyCount: 0,
                             tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                             updatedAt: Date.now(), createdAt: Date.now() });
    __wf.current = wf;
    __wfMultiSelected.clear();
    for (const id of sel) __wfMultiSelected.add(id);
    __wf._forceFullCanvasRebuild = true;
    if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
    else _wfRenderCanvas();
    if (typeof _wfSyncMultiSelectClasses === 'function') _wfSyncMultiSelectClasses();
  }, selectedIds);
  await page.waitForTimeout(60);
}

// Case 1: 2-node delete (no confirm).
await setup(['n-b', 'n-c']);
await page.evaluate(() => document.body.focus());
await page.keyboard.press('Backspace');
await page.waitForTimeout(120);
const r1 = await page.evaluate(() => ({
  ids: __wf.current.nodes.map(n => n.id),
  edges: __wf.current.edges.map(e => e.id),
  multi: Array.from(__wfMultiSelected),
}));
check('2-node delete: only n-a + n-d remain',
  r1.ids.length === 2 && r1.ids.includes('n-a') && r1.ids.includes('n-d'));
check('2-node delete: incident edges (ab, bc, cd) all removed',
  r1.edges.length === 0);
check('multi-selection cleared after delete', r1.multi.length === 0);

// Case 2: 4-node delete with confirm dialog.
await setup(['n-a', 'n-b', 'n-c', 'n-d']);
await page.evaluate(() => document.body.focus());
await page.keyboard.press('Backspace');
await page.waitForTimeout(150);
const r2 = await page.evaluate(() => ({
  ids: __wf.current.nodes.map(n => n.id),
  edges: __wf.current.edges.map(e => e.id),
}));
check('4-node delete: all nodes gone after confirm', r2.ids.length === 0);
check('4-node delete: all edges gone',                r2.edges.length === 0);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
