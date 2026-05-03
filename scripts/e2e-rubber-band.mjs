#!/usr/bin/env node
/**
 * QQ27 — Shift + drag on the empty canvas selects all nodes whose
 * bounding boxes intersect the rectangle. QQ28 — clicking and
 * dragging any selected node moves the cluster as one.
 *
 * Strategy: use real mouse events through Playwright so the existing
 * onDown / onMove / onUp handlers fire just like a real user.
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

// Build a deterministic workflow with nodes spread out in known positions.
await page.evaluate(() => {
  const wf = {
    id: 'wf-rubber',
    name: 'rubber-test',
    nodes: [
      { id: 'n-a', type: 'session', x: 100, y: 100, title: 'A', data: { subject: 'a' } },
      { id: 'n-b', type: 'session', x: 100, y: 220, title: 'B', data: { subject: 'b' } },
      { id: 'n-c', type: 'session', x: 600, y: 100, title: 'C', data: { subject: 'c' } },
    ],
    edges: [],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 3, edgeCount: 0, stickyCount: 0,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
});

await page.waitForTimeout(150);

// Find the SVG client-rect so we can convert workflow-space x/y to
// screen pixels. The SVG covers the canvas host with viewport (0,0)
// + zoom 1 so workflow coords are SVG coords are pixel offsets.
const rect = await page.evaluate(() => {
  const svg = document.querySelector('#wfCanvasHost svg') || document.getElementById('wfSvg');
  const r = svg.getBoundingClientRect();
  return { x: r.x, y: r.y, w: r.width, h: r.height, vp: __wf.current.viewport };
});

// Drag a rectangle from world(50, 80) to world(420, 320).
// In screen px: rect.x + worldX, rect.y + worldY (zoom 1, pan 0).
const sx = rect.x + 50, sy = rect.y + 80;
const ex = rect.x + 420, ey = rect.y + 320;

await page.keyboard.down('Shift');
await page.mouse.move(sx, sy);
await page.mouse.down();
// Move in a few steps so the canvas onMove fires.
for (let i = 1; i <= 6; i++) {
  await page.mouse.move(sx + ((ex - sx) * i / 6), sy + ((ey - sy) * i / 6));
}
await page.mouse.up();
await page.keyboard.up('Shift');
await page.waitForTimeout(150);

const sel = await page.evaluate(() => Array.from(__wfMultiSelected || []));
check('rubber-band selected n-a', sel.includes('n-a'));
check('rubber-band selected n-b', sel.includes('n-b'));
check('rubber-band did NOT select n-c (out of rect)', !sel.includes('n-c'));
check('multi-selection size is 2', sel.length === 2);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
