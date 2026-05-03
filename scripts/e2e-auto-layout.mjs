#!/usr/bin/env node
/**
 * `_wfBeautifyLayout` — DAG topological auto-layout.
 *
 * Build a 4-node chain a → b → c → d but with all nodes at the same
 * y and overlapping x. After auto-layout the longest path
 * assigns layers 0/1/2/3 → x increases left-to-right, y stays
 * within the same band.
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

// Build a 4-node chain — purposely overlapping positions.
await page.evaluate(() => {
  const wf = {
    id: 'wf-layout',
    name: 'auto-layout',
    nodes: [
      { id: 'n-a', type: 'start',   x: 100, y: 100, data: {} },
      { id: 'n-b', type: 'session', x: 100, y: 100, data: { subject: 'b' } },
      { id: 'n-c', type: 'session', x: 100, y: 100, data: { subject: 'c' } },
      { id: 'n-d', type: 'session', x: 100, y: 100, data: { subject: 'd' } },
    ],
    edges: [
      { id: 'e1', from: 'n-a', fromPort: 'out', to: 'n-b', toPort: 'in' },
      { id: 'e2', from: 'n-b', fromPort: 'out', to: 'n-c', toPort: 'in' },
      { id: 'e3', from: 'n-c', fromPort: 'out', to: 'n-d', toPort: 'in' },
    ],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 4, edgeCount: 3, stickyCount: 0,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
});
await page.waitForTimeout(120);

// Run the layout — call the helper directly.
const result = await page.evaluate(() => {
  if (typeof _wfBeautifyLayout !== 'function') return { ok: false, msg: 'fn missing' };
  const ok = _wfBeautifyLayout();
  // _wfBeautifyLayout doesn't render — we trigger render explicitly.
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
  const m = {};
  for (const n of __wf.current.nodes) m[n.id] = { x: n.x, y: n.y };
  return { ok, m };
});
check('_wfBeautifyLayout returned truthy', result.ok === true);

// Each successive layer must have strictly greater x than the
// previous (longest-path layout produces left-to-right chain).
const m = result.m || {};
check('a.x < b.x', m['n-a'] && m['n-b'] && m['n-a'].x < m['n-b'].x);
check('b.x < c.x', m['n-b'] && m['n-c'] && m['n-b'].x < m['n-c'].x);
check('c.x < d.x', m['n-c'] && m['n-d'] && m['n-c'].x < m['n-d'].x);
// Same single-row chain → all y should be equal.
check('all y equal (single row)',
  m['n-a'] && m['n-a'].y === m['n-b'].y &&
  m['n-b'].y === m['n-c'].y && m['n-c'].y === m['n-d'].y);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
