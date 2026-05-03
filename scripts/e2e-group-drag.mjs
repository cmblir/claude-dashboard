#!/usr/bin/env node
/**
 * QQ28 — when a node belongs to __wfMultiSelected, dragging it moves
 * the entire selection while preserving relative offsets.
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
    id: 'wf-group',
    name: 'group-drag',
    nodes: [
      { id: 'n-a', type: 'session', x: 100, y: 100, title: 'A', data: { subject: 'a' } },
      { id: 'n-b', type: 'session', x: 100, y: 220, title: 'B', data: { subject: 'b' } },
    ],
    edges: [],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 2, edgeCount: 0, stickyCount: 0,
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
  // QQ196 — center the canvas on the injected nodes. Without this the
  // default viewport (panY=0, zoom=1) places world-y=100 at screen y~1170,
  // off the bottom of the 1200px viewport, so mouse drags miss the node.
  if (typeof _wfFitView === 'function') _wfFitView();
});
await page.waitForTimeout(180);

const beforeAll = await page.evaluate(() => __wf.current.nodes.map(n => ({ id: n.id, x: n.x, y: n.y })));

// QQ196 — the workflows tab renders a list view above the canvas, so
// wfCanvasHost can sit below the viewport (y~1070 in a 1200px window).
// Scroll the canvas into view before grabbing the node rect, otherwise
// mouse events miss the off-screen node entirely.
await page.evaluate(() => {
  const host = document.getElementById('wfCanvasHost');
  if (host && host.scrollIntoView) host.scrollIntoView({ behavior: 'instant', block: 'center' });
});
await page.waitForTimeout(120);

// Read n-a's real on-screen rect rather than computing from world coords:
// the SVG often uses a viewBox so workflow units ≠ pixels.
const aRect = await page.evaluate(() => {
  const el = document.querySelector('.wf-node[data-node="n-a"] rect.wf-node-body, .wf-node[data-node="n-a"]');
  if (!el) return null;
  return el.getBoundingClientRect().toJSON();
});
if (!aRect) {
  console.error('n-a not found on canvas');
  process.exit(1);
}
const sx = aRect.x + aRect.width / 2;
const sy = aRect.y + aRect.height / 2;
const dx = 200, dy = 80;

await page.mouse.move(sx, sy);
await page.mouse.down();
for (let i = 1; i <= 6; i++) {
  await page.mouse.move(sx + dx * i / 6, sy + dy * i / 6);
}
await page.mouse.up();
await page.waitForTimeout(150);

const afterAll = await page.evaluate(() => __wf.current.nodes.map(n => ({ id: n.id, x: n.x, y: n.y })));

const before = Object.fromEntries(beforeAll.map(n => [n.id, n]));
const after  = Object.fromEntries(afterAll.map(n => [n.id, n]));

const dxA = after['n-a'].x - before['n-a'].x;
const dyA = after['n-a'].y - before['n-a'].y;
const dxB = after['n-b'].x - before['n-b'].x;
const dyB = after['n-b'].y - before['n-b'].y;

check('n-a moved horizontally',  Math.abs(dxA) > 80);
check('n-a moved vertically',    Math.abs(dyA) > 30);
check('n-b moved with the group (x)', Math.abs(dxA - dxB) < 5);
check('n-b moved with the group (y)', Math.abs(dyA - dyB) < 5);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
