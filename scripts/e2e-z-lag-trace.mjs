#!/usr/bin/env node
/**
 * Empirical lag profile for the workflows tab.
 * - Captures longtask totals during idle and after loading a workflow
 * - JS coverage to attribute CPU to inline scripts
 * - Saves /tmp/z1-lag-profile.json
 */
import { chromium } from 'playwright';
import { writeFileSync } from 'node:fs';

const BASE = process.env.BASE || `http://127.0.0.1:${process.env.PORT || 8080}`;
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await ctx.addInitScript(() => {
  try { localStorage.setItem('dashboard-entered', '1'); } catch (_) {}
});
const page = await ctx.newPage();

const consoleMsgs = [];
const errors = [];
page.on('console', m => consoleMsgs.push(`[${m.type()}] ${m.text().slice(0, 200)}`));
page.on('pageerror', e => errors.push(e.message));

// Install longtask + measure observers as early as possible
await page.addInitScript(() => {
  window.__lt = { tasks: [], totalMs: 0, byAttribution: {} };
  try {
    const obs = new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        window.__lt.tasks.push({ start: e.startTime, dur: e.duration, name: e.name });
        window.__lt.totalMs += e.duration;
        const attribs = (e.attribution || []).map(a => `${a.name || ''}@${a.containerType || ''}:${a.containerSrc || ''}`);
        const key = attribs.join('|') || 'unknown';
        window.__lt.byAttribution[key] = (window.__lt.byAttribution[key] || 0) + e.duration;
      }
    });
    obs.observe({ entryTypes: ['longtask'] });
  } catch (e) { window.__lt.err = String(e); }
});

await page.coverage.startJSCoverage({ resetOnNavigation: false });

// CDP sampling profiler
const cdp = await page.context().newCDPSession(page);
await cdp.send('Profiler.enable');
await cdp.send('Profiler.setSamplingInterval', { interval: 200 });

console.log('--> goto /#/workflows');
await page.goto(`${BASE}/#/workflows`, { waitUntil: 'networkidle', timeout: 25000 });

async function captureWindow(label, ms) {
  await page.evaluate(() => { window.__lt.tasks = []; window.__lt.totalMs = 0; window.__lt.byAttribution = {}; });
  await page.waitForTimeout(ms);
  const snap = await page.evaluate(() => JSON.parse(JSON.stringify(window.__lt)));
  console.log(`[${label}] longtasks=${snap.tasks.length}  total=${snap.totalMs.toFixed(1)}ms  windowed=${ms}ms`);
  return { label, windowMs: ms, ...snap };
}

const idleSnap = await captureWindow('idle-on-workflows', 5000);

// Force-open the existing workflow via global function.
let editorOpened = await page.evaluate(async () => {
  if (typeof _wfOpen === 'function' && typeof __wf !== 'undefined' && __wf.workflows && __wf.workflows[0]) {
    await _wfOpen(__wf.workflows[0].id);
    return { ok: true, id: __wf.workflows[0].id, nodes: __wf.current && __wf.current.nodes ? __wf.current.nodes.length : 0 };
  }
  return { ok: false };
}).catch(e => ({ ok: false, err: String(e) }));
console.log('editorOpened:', editorOpened);
await page.waitForTimeout(1500);
const loadedSnap = await captureWindow('after-load-workflow', 5000);

// Begin profiler before interactions
await cdp.send('Profiler.start');

// Pan/zoom interaction window — hover over canvas and wheel
let interactSnap = null;
try {
  const canvas = page.locator('#wf-canvas, .wf-canvas, [class*="canvas"]').first();
  if (await canvas.count()) {
    const box = await canvas.boundingBox();
    if (box) {
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.evaluate(() => { window.__lt.tasks = []; window.__lt.totalMs = 0; window.__lt.byAttribution = {}; });
      for (let i = 0; i < 20; i++) {
        await page.mouse.wheel(0, (i % 2 ? -120 : 120));
        await page.waitForTimeout(80);
      }
      // small drag
      await page.mouse.down();
      for (let i = 0; i < 15; i++) {
        await page.mouse.move(box.x + box.width / 2 + i * 6, box.y + box.height / 2 + i * 4);
        await page.waitForTimeout(40);
      }
      await page.mouse.up();
      await page.waitForTimeout(500);
      interactSnap = await page.evaluate(() => JSON.parse(JSON.stringify(window.__lt)));
      interactSnap.label = 'interact-pan-zoom';
      console.log(`[interact] longtasks=${interactSnap.tasks.length}  total=${interactSnap.totalMs.toFixed(1)}ms`);
    }
  }
} catch (e) { console.log('interact failed:', e.message); }

// Stress test the suspected hot paths
const stress = await page.evaluate(async () => {
  const out = {};
  function timeIt(label, fn, n) {
    const t0 = performance.now();
    for (let i = 0; i < n; i++) fn();
    return { label, n, totalMs: +(performance.now() - t0).toFixed(2), perCallUs: +((performance.now() - t0) / n * 1000).toFixed(1) };
  }
  if (typeof _wfRenderList === 'function') out.renderList = timeIt('_wfRenderList', () => _wfRenderList(), 50);
  if (typeof _wfRenderCanvas === 'function') out.renderCanvas = timeIt('_wfRenderCanvas', () => _wfRenderCanvas(), 50);
  if (typeof _wfRenderInspector === 'function') out.renderInspector = timeIt('_wfRenderInspector', () => _wfRenderInspector(), 50);
  if (typeof renderView === 'function') out.renderView = timeIt('renderView', () => renderView(), 30);
  if (typeof t === 'function') out.t1k = timeIt('t("새 워크플로우")', () => t('새 워크플로우'), 5000);
  return out;
});
console.log('stress:', JSON.stringify(stress, null, 2));

// Stop profiler and aggregate
const profile = await cdp.send('Profiler.stop');
const cpuProfile = profile.profile;
// Aggregate self time per (url, function)
const selfTime = new Map();
const totalSamples = (cpuProfile.samples || []).length;
const sampleInterval = 200; // microseconds (we set 200us)
const idToNode = new Map();
for (const n of cpuProfile.nodes) idToNode.set(n.id, n);
const hits = new Map();
for (const id of cpuProfile.samples || []) hits.set(id, (hits.get(id) || 0) + 1);
for (const [id, count] of hits) {
  const n = idToNode.get(id);
  if (!n) continue;
  const cf = n.callFrame || {};
  const key = `${cf.functionName || '<anon>'}  ${cf.url || ''}:${cf.lineNumber}:${cf.columnNumber}`;
  const prev = selfTime.get(key) || { count: 0, us: 0, cf };
  prev.count += count;
  prev.us += count * sampleInterval;
  selfTime.set(key, prev);
}
const topSelf = [...selfTime.entries()]
  .map(([k, v]) => ({ key: k, count: v.count, us: v.us, url: v.cf.url, line: v.cf.lineNumber, col: v.cf.columnNumber, fn: v.cf.functionName }))
  .sort((a, b) => b.us - a.us)
  .slice(0, 25);

const coverage = await page.coverage.stopJSCoverage();

// Reduce coverage: per-source used bytes & "hot" function ranges
const cov = coverage.map(c => {
  const totalBytes = c.text ? c.text.length : 0;
  const usedBytes = (c.functions || []).reduce((acc, f) => {
    for (const r of (f.ranges || [])) if (r.count > 0) acc += (r.endOffset - r.startOffset);
    return acc;
  }, 0);
  // Top hot functions by hit count * span
  const hot = [];
  for (const f of (c.functions || [])) {
    const span = (f.ranges || []).reduce((s, r) => s + (r.endOffset - r.startOffset), 0);
    const hits = (f.ranges || []).reduce((s, r) => s + (r.count || 0), 0);
    if (hits > 50 && span > 200) hot.push({ name: f.functionName || '<anon>', hits, span });
  }
  hot.sort((a, b) => b.hits - a.hits);
  return {
    url: c.url,
    totalBytes,
    usedBytes,
    pctUsed: totalBytes ? +(usedBytes / totalBytes * 100).toFixed(1) : 0,
    topHotFunctions: hot.slice(0, 25),
  };
}).sort((a, b) => b.usedBytes - a.usedBytes);

// Snapshot of timers / intervals from the page (heuristic)
const pageDiag = await page.evaluate(() => {
  const out = { setIntervalCount: 0, rafActive: false, viewLen: 0, nodes: 0 };
  out.nodes = document.querySelectorAll('*').length;
  const v = document.getElementById('view');
  if (v) out.viewLen = v.innerHTML.length;
  // detect known globals
  try { out.has_wf = typeof __wf !== 'undefined'; } catch(e){ out.has_wf = false; }
  try { out.wfNodes = (typeof __wf !== 'undefined' && __wf.current && __wf.current.nodes) ? __wf.current.nodes.length : null; } catch(e){}
  try { out.wfWorkflows = (typeof __wf !== 'undefined') ? (__wf.workflows||[]).length : null; } catch(e){}
  return out;
});

const report = {
  baseUrl: BASE,
  idleSnap,
  loadedSnap,
  interactSnap,
  pageDiag,
  errors,
  consoleMsgsTail: consoleMsgs.slice(-30),
  coverageTop: cov.slice(0, 6),
  cpuProfile: { totalSamples, topSelf },
  stress,
};
writeFileSync('/tmp/z1-lag-profile.json', JSON.stringify(report, null, 2));
console.log('\n=== written /tmp/z1-lag-profile.json ===');
console.log('pageDiag:', pageDiag);
console.log('coverage top sources:');
for (const c of cov.slice(0, 4)) {
  console.log(`  ${c.url}  total=${c.totalBytes}  used=${c.usedBytes}  pct=${c.pctUsed}%`);
  for (const h of c.topHotFunctions.slice(0, 8)) {
    console.log(`     ${h.hits.toString().padStart(7)}× ${h.name}  span=${h.span}`);
  }
}

console.log('\nCPU profile top self-time (us):');
for (const t of topSelf.slice(0, 15)) {
  console.log(`  ${String(t.us).padStart(8)}us  ${t.fn || '<anon>'}  ${t.url ? t.url.split('/').pop() : ''}:${t.line}`);
}

await browser.close();
