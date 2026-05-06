#!/usr/bin/env node
/**
 * Workflow canvas drag latency profile.
 *
 * Builds a workflow with 30 nodes via the API, opens it in the browser,
 * dispatches mousemove events at ~120Hz on a single node for 2 seconds,
 * and reports how many frames the page actually rendered + the longest
 * scripting task during the drag.
 */
import { chromium } from 'playwright';

const URL = process.env.URL || `http://127.0.0.1:${process.env.PORT || 8080}/`;
const N = parseInt(process.env.N || '30', 10);

// Build the workflow over the API first.
async function buildWorkflow() {
  const nodes = [];
  const edges = [];
  for (let i = 0; i < N; i++) {
    nodes.push({
      id: 'n-perf' + i,
      type: i === 0 ? 'start' : (i === N - 1 ? 'output' : 'session'),
      title: 'Node ' + i,
      x: 80 + (i % 6) * 220,
      y: 80 + Math.floor(i / 6) * 140,
      data: { assignee: 'claude:opus' },
    });
    if (i > 0) edges.push({ id: 'e-perf' + i, from: 'n-perf' + (i - 1), to: 'n-perf' + i });
  }
  const r = await fetch(URL + 'api/workflows/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      // The save handler reads sanitised fields off `body` directly.
      id: 'perf-drag', name: 'perf-drag', nodes, edges,
      viewport: { panX: 0, panY: 0, zoom: 1 },
    }),
  });
  if (!r.ok) return null;
  const j = await r.json();
  return j.id || null;
}

const wfId = await buildWorkflow();
if (!wfId) { console.error('failed to seed workflow'); process.exit(1); }
console.log('seeded workflow id =', wfId);

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1500, height: 950 } })).newPage();
await page.addInitScript(() => {
  window.__perfTasks = [];
  window.__frames = 0;
  let last = performance.now();
  function tick(t) { window.__frames++; last = t; requestAnimationFrame(tick); }
  requestAnimationFrame(tick);
  try {
    new PerformanceObserver(list => {
      for (const e of list.getEntries()) window.__perfTasks.push(e.duration);
    }).observe({ type: 'longtask', buffered: true });
  } catch (_) {}
});
await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('#wfCanvas', { timeout: 8000 });
// _wfOpen is async — await it so render finishes before we measure.
await page.evaluate(async (id) => { await _wfOpen(id); }, wfId);
// Force a full render in case the keyed-diff path skipped some nodes.
await page.evaluate(() => { __wf._forceFullCanvasRebuild = true; _wfRenderCanvas(); });
await page.waitForTimeout(600);
const dbg = await page.evaluate(() => ({
  current: !!__wf.current,
  curId: __wf.current && __wf.current.id,
  nodesInState: __wf.current ? (__wf.current.nodes || []).length : 0,
  nodesInDom: document.querySelectorAll('#wfNodes .wf-node').length,
}));
console.log('after open:', dbg);

// Locate any drag-able node — sanitizer renames ids on save.
await page.waitForFunction(() => document.querySelectorAll('#wfNodes .wf-node').length > 5, { timeout: 8000 });
const nodeBox = await page.evaluate(() => {
  const els = document.querySelectorAll('#wfNodes .wf-node');
  if (els.length < 6) return null;
  const el = els[5];
  const r = el.getBoundingClientRect();
  return { x: r.x + r.width / 2, y: r.y + r.height / 2, count: els.length };
});
if (!nodeBox) { console.error('target node not found'); process.exit(2); }
console.log('canvas has', nodeBox.count, 'nodes');

// Reset counters right before drag.
await page.evaluate(() => { window.__perfTasks = []; window.__frames = 0; });

const t0 = Date.now();
await page.mouse.move(nodeBox.x, nodeBox.y);
await page.mouse.down();
const STEPS = 240;
const DUR_MS = 2000;
const PER = DUR_MS / STEPS;
for (let i = 0; i < STEPS; i++) {
  const k = i / STEPS;
  const dx = Math.sin(k * Math.PI * 2) * 60;
  const dy = Math.cos(k * Math.PI * 2) * 60;
  await page.mouse.move(nodeBox.x + dx, nodeBox.y + dy);
  await page.waitForTimeout(PER);
}
await page.mouse.up();
const elapsed = Date.now() - t0;

const r = await page.evaluate(() => ({
  frames: window.__frames,
  tasks: (window.__perfTasks || []).slice(),
}));
const totalLong = r.tasks.reduce((s, x) => s + x, 0);
const longest = r.tasks.length ? Math.max(...r.tasks).toFixed(0) : '0';
const fps = (r.frames / (elapsed / 1000)).toFixed(1);

console.log(`drag elapsed: ${elapsed}ms · frames: ${r.frames} · fps: ${fps}`);
console.log(`longtasks: ${r.tasks.length} · total: ${totalLong.toFixed(0)}ms · longest: ${longest}ms`);
await browser.close();
