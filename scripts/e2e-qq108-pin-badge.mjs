#!/usr/bin/env node
/**
 * QQ108 verification — pin / disabled / sticky state changes must
 * propagate to the canvas via the keyed-diff renderer.
 *
 * 1. Open workflow tab.
 * 2. Inject a workflow with one session node (no pin).
 * 3. Toggle data.pinned=true + pinnedOutput, call _wfRenderCanvas.
 * 4. Assert the .wf-node-pin-badge SVG group is visible.
 * 5. Toggle pinned=false, render, assert badge gone.
 */
import { chromium } from 'playwright';

const PORT = process.env.PORT || '19500';
const URL  = `http://127.0.0.1:${PORT}/`;

function check(label, ok) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}`);
  if (!ok) process.exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const ctx = await browser.newContext();
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
// Switch to workflow tab
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('#wfCanvasHost', { timeout: 8000 });

// Build a synthetic workflow + render it
const result = await page.evaluate(async () => {
  const wf = {
    id: 'wf-qq108-test',
    name: 'qq108',
    nodes: [
      { id: 'n-start', type: 'start', x: 50, y: 80, data: {} },
      { id: 'n-s', type: 'session', x: 320, y: 80,
        title: 'pin-test', data: { subject: 'x', assignee: 'claude:opus' } },
    ],
    edges: [{ id: 'e1', from: 'n-start', fromPort: 'out', to: 'n-s', toPort: 'in' }],
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

  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

  const beforePin = !!document.querySelector('#wfNodes .wf-node[data-node="n-s"] .wf-node-pin-badge');

  // Toggle pin via the session node
  const sn = wf.nodes.find(n => n.id === 'n-s');
  sn.data.pinned = true;
  sn.data.pinnedOutput = 'frozen';
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

  const afterPin = !!document.querySelector('#wfNodes .wf-node[data-node="n-s"] .wf-node-pin-badge');

  // Unpin
  sn.data.pinned = false;
  sn.data.pinnedOutput = '';
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

  const afterUnpin = !!document.querySelector('#wfNodes .wf-node[data-node="n-s"] .wf-node-pin-badge');

  return { beforePin, afterPin, afterUnpin };
});

check('pin badge absent before toggle', result.beforePin === false);
check('pin badge appears after pin=true', result.afterPin === true);
check('pin badge gone after unpin',     result.afterUnpin === false);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
