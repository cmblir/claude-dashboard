#!/usr/bin/env node
/** GG2: measure lag on interactive workflow operations. */
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.addInitScript(() => { localStorage.setItem('dashboard-entered', '1'); });
await page.goto('http://127.0.0.1:8080/#/workflows', { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);

const r = await page.evaluate(async () => {
  const stats = {};
  // 1) cost of synthetic _wfApplyRunStatus call (the SSE handler)
  if (typeof _wfApplyRunStatus === 'function' && typeof __wf !== 'undefined') {
    __wf.current = __wf.current || { id:'g', name:'g', nodes:[], edges:[], viewport:{panX:0,panY:0,zoom:1} };
    const fakeRun = {
      runId: 'g-fake', status: 'running',
      startedAt: Date.now(),
      nodeResults: { 'n-x': { status: 'running', startedAt: Date.now() } },
      currentNodeId: 'n-x',
    };
    const t0 = performance.now();
    for (let i = 0; i < 50; i++) {
      _wfApplyRunStatus(fakeRun);
    }
    stats.applyRunStatus_50x_ms = +(performance.now() - t0).toFixed(1);
  }

  // 2) cost of full canvas re-render
  if (typeof _wfRenderCanvas === 'function' && __wf && __wf.current) {
    const t0 = performance.now();
    for (let i = 0; i < 30; i++) _wfRenderCanvas();
    stats.renderCanvas_30x_ms = +(performance.now() - t0).toFixed(1);
  }

  // 3) cost of inspector
  if (typeof _wfRenderInspector === 'function') {
    const t0 = performance.now();
    for (let i = 0; i < 30; i++) _wfRenderInspector();
    stats.renderInspector_30x_ms = +(performance.now() - t0).toFixed(1);
  }

  // 4) translation cost — t() is called on every render
  if (typeof t === 'function') {
    const t0 = performance.now();
    for (let i = 0; i < 5000; i++) t('실행 중');
    stats.t_5000x_ms = +(performance.now() - t0).toFixed(1);
  }

  // 5) renderView — global re-render
  if (typeof renderView === 'function') {
    const t0 = performance.now();
    renderView();
    stats.renderView_1x_ms = +(performance.now() - t0).toFixed(1);
  }

  return stats;
});

console.log('--- INTERACTION LAG (lower is better) ---');
for (const [k, v] of Object.entries(r)) {
  console.log(`  ${k}:  ${v} ms`);
}

await browser.close();
