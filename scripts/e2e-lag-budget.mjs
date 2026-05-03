#!/usr/bin/env node
/**
 * Lag budget — verify two perf-critical invariants stay within a
 * sane envelope so a regression yells immediately:
 *
 * 1. Initial DOMContentLoaded under 600ms (threshold loose enough
 *    to handle CI variance; we're ≈ 60–120ms in healthy state).
 * 2. Forcing a full canvas rebuild with 50 nodes finishes in
 *    < 250ms (was up to ~2s before keyed-diff + RAF coalescing).
 * 3. Calling _wfRenderCanvas() 50 times within one tick coalesces
 *    to a single actual render (QQ25 RAF dedupe contract).
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

// Step 1: DOMContentLoaded.
const navStart = Date.now();
await page.goto(URL, { waitUntil: 'domcontentloaded' });
const dcl = Date.now() - navStart;
check(`DOMContentLoaded under 600ms (got ${dcl}ms)`, dcl < 600);

// Wait for the SPA to be ready before driving it.
await page.waitForSelector('#wfCanvasHost, [data-view]', { timeout: 8000 }).catch(() => {});
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('#wfCanvasHost', { timeout: 8000 });

// Step 2: 50-node full rebuild.
const rebuildResult = await page.evaluate(async () => {
  const nodes = [];
  for (let i = 0; i < 50; i++) {
    nodes.push({
      id: 'n-' + i,
      type: i === 0 ? 'start' : 'session',
      x: 60 + (i % 10) * 200,
      y: 60 + Math.floor(i / 10) * 120,
      title: 'N' + i,
      data: i === 0 ? {} : { subject: 's' + i, assignee: 'claude:opus' },
    });
  }
  const wf = {
    id: 'wf-lag-50',
    name: 'lag-50',
    nodes,
    edges: [],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 49, edgeCount: 0, stickyCount: 0,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wf._forceFullCanvasRebuild = true;
  const t0 = performance.now();
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
  const dur = performance.now() - t0;
  const renderedCount = document.querySelectorAll('#wfNodes .wf-node').length;
  return { dur, renderedCount };
});
check(`full rebuild 50 nodes < 250ms (got ${rebuildResult.dur.toFixed(1)}ms)`,
  rebuildResult.dur < 250);
check(`50 nodes actually rendered (got ${rebuildResult.renderedCount})`,
  rebuildResult.renderedCount === 50);

// Step 3: RAF coalescing — calling _wfRenderCanvas() 50× in one tick
// should produce only one actual sync render in the next animation
// frame. We hook _wfRenderGroups (always invoked inside the sync
// wrapper, see app.js _wfRenderCanvasSync) to count actual renders.
const coalesceResult = await page.evaluate(async () => {
  let calls = 0;
  const origGroups = window._wfRenderGroups;
  window._wfRenderGroups = function () {
    calls++;
    return origGroups && origGroups.apply(this, arguments);
  };
  for (let i = 0; i < 50; i++) _wfRenderCanvas();
  // Wait two animation frames for the RAF to fire and settle.
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  // Restore.
  window._wfRenderGroups = origGroups;
  return { syncCalls: calls };
});
check(`50 _wfRenderCanvas() calls coalesced to 1 sync render (got ${coalesceResult.syncCalls})`,
  coalesceResult.syncCalls === 1);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
