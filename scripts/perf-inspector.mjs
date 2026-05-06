#!/usr/bin/env node
/**
 * Workflow inspector render perf — selecting a node should be ≤16ms.
 * Builds a 30-node workflow, opens it, then selects a session node and
 * times _wfRenderInspector + the selection click.
 */
import { chromium } from 'playwright';

const URL = process.env.URL || `http://127.0.0.1:${process.env.PORT || 8080}/`;

async function buildWorkflow() {
  const nodes = [];
  const edges = [];
  for (let i = 0; i < 30; i++) {
    nodes.push({
      id: 'n-perf' + i,
      type: i === 0 ? 'start' : (i === 29 ? 'output' : 'session'),
      title: 'Node ' + i,
      x: 80 + (i % 6) * 220,
      y: 80 + Math.floor(i / 6) * 140,
      data: { assignee: 'claude:opus', subject: 'task ' + i },
    });
    if (i > 0) edges.push({ id: 'e' + i, from: 'n-perf' + (i - 1), to: 'n-perf' + i });
  }
  const r = await fetch(URL + 'api/workflows/save', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: 'perf-insp', name: 'perf-insp', nodes, edges, viewport: { panX: 0, panY: 0, zoom: 1 } }),
  });
  const j = await r.json();
  return j.id || null;
}
const wfId = await buildWorkflow();
if (!wfId) { console.error('failed to seed'); process.exit(1); }

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1500, height: 950 } })).newPage();
await page.addInitScript(() => {
  window.__perfTasks = [];
  try { new PerformanceObserver(l => l.getEntries().forEach(e => window.__perfTasks.push(e.duration))).observe({type:'longtask',buffered:true}); } catch(_){}
});
await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('#wfCanvas', { timeout: 8000 });
await page.evaluate(async (id) => { await _wfOpen(id); }, wfId);
await page.evaluate(() => { __wf._forceFullCanvasRebuild = true; _wfRenderCanvas(); });
await page.waitForTimeout(700);

// Reset task buffer right before timing inspector render.
await page.evaluate(() => { window.__perfTasks = []; });

// Time _wfRenderInspector for 5 different nodes.
const samples = await page.evaluate(() => {
  const nodes = (__wf.current.nodes || []).filter(n => n.type === 'session').slice(0, 5);
  const out = [];
  for (const n of nodes) {
    __wf.selectedNodeId = n.id;
    __wf._lastInspSig = null;  // force render
    const t0 = performance.now();
    _wfRenderInspector({ force: true });
    out.push({ id: n.id, ms: performance.now() - t0 });
  }
  return out;
});
console.log('inspector render samples (ms):');
for (const s of samples) console.log('  ', s.id.padEnd(12), s.ms.toFixed(1));

const totalLong = await page.evaluate(() => (window.__perfTasks || []).reduce((s, x) => s + x, 0));
console.log('longtasks during 5 inspector renders:', totalLong.toFixed(0) + 'ms');

await page.evaluate(async (id) => fetch('/api/workflows/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) }), wfId);
await browser.close();
