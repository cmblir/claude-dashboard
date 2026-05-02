#!/usr/bin/env node
/** JJ2: simulate a live workflow run (7 nodes, SSE every 0.5s) and
 *  measure interaction lag during the run. */
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.addInitScript(() => { localStorage.setItem('dashboard-entered', '1'); });
await page.goto('http://127.0.0.1:8080/#/workflows', { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);

const r = await page.evaluate(async () => {
  // Build a synthetic 7-node workflow + simulate a live run with periodic
  // status updates (mirrors what SSE/polling does during an actual run).
  if (typeof __wf === 'undefined' || typeof _wfApplyRunStatus !== 'function') {
    return { err: 'workflow code not loaded' };
  }
  __wf.current = {
    id: 'jj-live', name: 'live test',
    nodes: Array.from({ length: 7 }, (_, i) => ({
      id: `n-${i}`, type: i === 0 ? 'start' : (i === 6 ? 'output' : 'session'),
      x: 60 + i * 220, y: 200,
      title: `node ${i}`,
      data: { assignee: 'sonnet-4.6', subject: 's', description: 'd' },
    })),
    edges: Array.from({ length: 6 }, (_, i) => ({
      id: `e-${i}`, from: `n-${i}`, to: `n-${i+1}`, fromPort: 'out', toPort: 'in',
    })),
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  if (typeof _wfRenderCanvas === 'function') _wfRenderCanvas();

  // Run 30 SSE-like ticks (~0.5s apart in real life), measure cumulative time
  const startedAt = Date.now() - 5000;
  const t0 = performance.now();
  for (let i = 0; i < 30; i++) {
    const completed = Math.min(i, 7);
    const nodeResults = {};
    for (let n = 0; n < 7; n++) {
      if (n < completed) nodeResults[`n-${n}`] = { status: 'ok', startedAt, finishedAt: Date.now() };
      else if (n === completed) nodeResults[`n-${n}`] = { status: 'running', startedAt: Date.now() - 1000 };
    }
    _wfApplyRunStatus({
      runId: 'jj-live', status: 'running', startedAt,
      currentNodeId: `n-${completed}`,
      nodeResults,
    });
  }
  const dur = performance.now() - t0;
  return { dur30Ticks_ms: +dur.toFixed(1), perTick_ms: +(dur/30).toFixed(2) };
});

console.log('--- live-run lag (30 SSE ticks on 7-node workflow) ---');
for (const [k, v] of Object.entries(r)) console.log(`  ${k}: ${v}`);

await browser.close();
