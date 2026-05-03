#!/usr/bin/env node
/**
 * QQ46 + QQ73 — inspector mini-Gantt:
 *
 * 1. Build a workflow with 4 nodes, inject mixed lastRunResults
 *    (durations + statuses + a pinned hit + an error).
 * 2. Render inspector → mini-Gantt panel appears with the rows
 *    sorted by duration descending.
 * 3. QQ73 status prefixes: pinned row leads with 📌, error row
 *    with ❌, normal rows just show the title.
 * 4. Clicking a row sets `__wf.selectedNodeId` to that node id
 *    so the inspector switches to its detail view.
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

// Build a synthetic workflow + lastRunResults.
await page.evaluate(() => {
  const wf = {
    id: 'wf-gantt',
    name: 'gantt-test',
    nodes: [
      { id: 'n-a',   type: 'session', x: 100, y: 100, title: 'AAA',      data: {} },
      { id: 'n-b',   type: 'session', x: 100, y: 220, title: 'BBB',      data: {} },
      { id: 'n-pin', type: 'session', x: 100, y: 340, title: 'PIN-NODE', data: {} },
      { id: 'n-err', type: 'session', x: 100, y: 460, title: 'ERR-NODE', data: {} },
    ],
    edges: [],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 4, edgeCount: 0, stickyCount: 0,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wf.lastRunResults = {
    'n-a':   { status: 'ok',  durationMs: 1500 },
    'n-b':   { status: 'ok',  durationMs: 800  },
    'n-pin': { status: 'ok',  durationMs: 1200, pinned: true, output: 'cached' },
    'n-err': { status: 'err', durationMs: 600,  error: 'boom' },
  };
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
  // Force inspector render with no node selected so the workflow-meta
  // mini-Gantt block appears.
  __wf.selectedNodeId = null;
  __wf._inspectorDirty = true;
  _wfRenderInspector({ force: true });
});
await page.waitForTimeout(120);

// Step 1 — Gantt panel exists.
const ganttRows = await page.evaluate(() => {
  const insp = document.getElementById('wfInspectorBody');
  if (!insp) return null;
  // The rows are inside the QQ46 block — they are <div onclick=…>
  // Each one's first inner <div> has the label (maybe '📌 PIN-NODE').
  const rows = Array.from(insp.querySelectorAll('div[onclick*="selectedNodeId"]'));
  return rows.map(r => (r.querySelector('span.truncate') || r).textContent.trim().slice(0, 40));
});
check('mini-Gantt panel rendered with 4 rows', ganttRows && ganttRows.length === 4);

// Step 2 — sorted by duration desc: AAA (1500) > PIN (1200) > BBB (800) > ERR (600).
check('row 0 is AAA (1500ms, longest)',
  ganttRows && /AAA/.test(ganttRows[0] || ''));
check('row 1 is PIN-NODE (1200ms)',
  ganttRows && /PIN-NODE/.test(ganttRows[1] || ''));

// Step 3 — QQ73 prefixes.
check('PIN row has 📌 prefix',
  ganttRows && /📌/.test(ganttRows[1] || ''));
check('ERR row has ❌ prefix',
  ganttRows && (ganttRows.find(r => /ERR-NODE/.test(r)) || '').includes('❌'));

// Step 4 — clicking a row selects that node in the inspector.
const selOk = await page.evaluate(() => {
  const insp = document.getElementById('wfInspectorBody');
  const rows = Array.from(insp.querySelectorAll('div[onclick*="selectedNodeId"]'));
  // Find the AAA row.
  const target = rows.find(r => /AAA/.test(r.textContent || ''));
  if (!target) return false;
  target.click();
  return __wf.selectedNodeId === 'n-a';
});
check('clicking the AAA row sets selectedNodeId = n-a', selOk);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
