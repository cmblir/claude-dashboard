#!/usr/bin/env node
/** HH2: synthetic drag/scroll perf — find what re-renders during interaction. */
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.addInitScript(() => { localStorage.setItem('dashboard-entered', '1'); });
await page.goto(`http://127.0.0.1:${process.env.PORT || 8080}/#/workflows`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);

const r = await page.evaluate(async () => {
  const stats = {};
  // Wrap top-level renderers and count invocations during a synthetic drag.
  const counters = { canvas: 0, inspector: 0, minimap: 0, sessionsPanel: 0, banner: 0, applyRun: 0, draftRender: 0 };
  const orig = {};
  const targets = ['_wfRenderCanvas', '_wfRenderInspector', '_wfRenderMinimap', '_wfRenderSessionsPanel', '_wfRenderRunBanner', '_wfApplyRunStatus', '_wfDraftRender'];
  const keys = ['canvas', 'inspector', 'minimap', 'sessionsPanel', 'banner', 'applyRun', 'draftRender'];
  for (let i = 0; i < targets.length; i++) {
    const fn = window[targets[i]];
    if (typeof fn === 'function') {
      orig[targets[i]] = fn;
      window[targets[i]] = function (...a) { counters[keys[i]]++; return fn.apply(this, a); };
    }
  }

  // Synthetic SSE-tick simulation — 20 ticks
  if (typeof __wf !== 'undefined' && typeof _wfApplyRunStatus === 'function') {
    __wf.current = __wf.current || { id:'g', name:'g', nodes:[], edges:[], viewport:{panX:0,panY:0,zoom:1} };
    const fakeRun = {
      runId: 'g', status: 'running', startedAt: Date.now(),
      nodeResults: { 'n-x': { status: 'running', startedAt: Date.now() } },
      currentNodeId: 'n-x',
    };
    const t0 = performance.now();
    for (let i = 0; i < 20; i++) _wfApplyRunStatus(fakeRun);
    stats.tick20_ms = +(performance.now() - t0).toFixed(1);
  }
  stats.callsPerTick = {};
  for (const k of keys) stats.callsPerTick[k] = +(counters[k] / 20).toFixed(2);

  // Restore wrappers
  for (const t of targets) if (orig[t]) window[t] = orig[t];

  return stats;
});

console.log('--- HOT-PATH CALLS PER SSE TICK ---');
for (const [k, v] of Object.entries(r.callsPerTick)) {
  const flag = v > 1 ? ' ⚠️ over-rendering' : '';
  console.log(`  ${k.padEnd(15)} ${v}${flag}`);
}
console.log(`\n20-tick total: ${r.tick20_ms} ms`);

await browser.close();
