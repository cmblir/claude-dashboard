#!/usr/bin/env node
/** GG1: trace workflow tab perf — find what's eating the main thread. */
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.addInitScript(() => { localStorage.setItem('dashboard-entered', '1'); });

// Track resource sizes
const resourceSummary = [];
page.on('response', async (resp) => {
  try {
    const url = resp.url();
    const size = parseInt(resp.headers()['content-length'] || '0', 10);
    if (size > 50_000) {
      resourceSummary.push({ url: url.replace(`http://127.0.0.1:${process.env.PORT || 8080}`, ''), size });
    }
  } catch (e) {}
});

const t0 = Date.now();
await page.goto(`http://127.0.0.1:${process.env.PORT || 8080}/#/workflows`, { waitUntil: 'networkidle' });
const loadMs = Date.now() - t0;

await page.waitForTimeout(800);

// Measure first render to interactive
const tStart = Date.now();
await page.waitForSelector('.wf-floating-right', { timeout: 5000 }).catch(() => null);
const interactiveMs = Date.now() - tStart;

// Long task observer + measure render cost of opening a workflow
const measure = await page.evaluate(async () => {
  const longTasks = [];
  if ('PerformanceObserver' in window) {
    try {
      const obs = new PerformanceObserver((list) => {
        for (const e of list.getEntries()) {
          if (e.duration > 50) longTasks.push({ name: e.name, dur: Math.round(e.duration) });
        }
      });
      obs.observe({ type: 'longtask', buffered: true });
    } catch (e) {}
  }
  // Force a workflow to load if there is one
  await new Promise(r => setTimeout(r, 600));
  // Stats
  return {
    longTasks: longTasks.slice(0, 12),
    domNodes: document.querySelectorAll('*').length,
    indexHtmlBytes: document.documentElement.innerHTML.length,
    inlineScriptCount: document.querySelectorAll('script:not([src])').length,
    inlineScriptBytes: Array.from(document.querySelectorAll('script:not([src])'))
                            .reduce((s, x) => s + (x.textContent || '').length, 0),
    externalScripts: Array.from(document.querySelectorAll('script[src]'))
                          .map(x => x.src.replace(/^https?:\/\/[^/]+/, '')),
    wfNodeCount: document.querySelectorAll('.wf-node').length,
    wfEdgeCount: document.querySelectorAll('.wf-edge').length,
    perf: {
      domContentLoadedMs: Math.round(performance.timing.domContentLoadedEventEnd - performance.timing.navigationStart),
      loadMs: Math.round(performance.timing.loadEventEnd - performance.timing.navigationStart),
    },
  };
});

console.log('--- LOAD ---');
console.log(`networkidle:        ${loadMs} ms`);
console.log(`first-interactive:  +${interactiveMs} ms`);
console.log(`DOMContentLoaded:   ${measure.perf.domContentLoadedMs} ms`);
console.log(`load event:         ${measure.perf.loadMs} ms`);
console.log();
console.log('--- BUNDLE ---');
console.log(`DOM nodes:          ${measure.domNodes}`);
console.log(`index.html bytes:   ${measure.indexHtmlBytes}`);
console.log(`inline <script>:    ${measure.inlineScriptCount} blocks, ${measure.inlineScriptBytes} bytes`);
console.log(`external scripts:`);
measure.externalScripts.forEach(s => console.log(`   ${s}`));
console.log();
console.log('--- WORKFLOW ---');
console.log(`wf nodes/edges:     ${measure.wfNodeCount} / ${measure.wfEdgeCount}`);
console.log();
console.log('--- LONG TASKS (>50ms main-thread blocks) ---');
measure.longTasks.forEach(t => console.log(`  ${t.dur} ms — ${t.name}`));
console.log();
console.log('--- RESOURCES >50KB ---');
resourceSummary.sort((a, b) => b.size - a.size);
resourceSummary.slice(0, 10).forEach(r => console.log(`  ${(r.size/1024).toFixed(0)} KB  ${r.url}`));

await browser.close();
