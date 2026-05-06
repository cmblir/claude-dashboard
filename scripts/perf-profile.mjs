#!/usr/bin/env node
/**
 * Lag profiler — measures total scripting/long-task time + JS heap +
 * largest contentful render for several heavy tabs. Output is a single
 * table so we can compare iterations.
 *
 * Tabs probed: lazyclawDashboard, workflows, aiProviders, lazyclawChat.
 * For each tab we (a) navigate, (b) wait for first paint, (c) collect
 * PerformanceObserver longtasks fired during nav, and (d) read JS heap.
 */
import { chromium } from 'playwright';

const URL = process.env.URL || `http://127.0.0.1:${process.env.PORT || 8080}/`;
const TABS = (process.env.TABS || 'lazyclawDashboard,workflows,aiProviders,lazyclawChat,sessions,overview').split(',');

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

await page.goto(URL, { waitUntil: 'networkidle' });
// Install observer once (it persists through SPA navigations).
await page.evaluate(() => {
  window.__perfTasks = [];
  try {
    const obs = new PerformanceObserver(list => {
      for (const e of list.getEntries()) window.__perfTasks.push({ d: e.duration, s: e.startTime, n: e.name });
    });
    obs.observe({ type: 'longtask', buffered: true });
  } catch (_) {}
});

const results = [];
for (const tab of TABS) {
  // Reset task buffer + record nav timings.
  await page.evaluate(() => { window.__perfTasks = []; });
  const t0 = Date.now();
  await page.evaluate((tab) => location.hash = '#/' + tab, tab);
  // Wait for view to be confirmed by the SPA.
  try {
    await page.waitForFunction((tab) => typeof state !== 'undefined' && state.view === tab, tab, { timeout: 8000 });
  } catch (_) { /* still record what we got */ }
  await page.waitForTimeout(900);  // collect post-paint long tasks
  const elapsed = Date.now() - t0;
  const summary = await page.evaluate(() => {
    const tasks = (window.__perfTasks || []).slice();
    const total = tasks.reduce((s, x) => s + x.d, 0);
    const top = tasks.sort((a, b) => b.d - a.d).slice(0, 3).map(x => x.d.toFixed(0));
    const heap = (performance.memory && performance.memory.usedJSHeapSize / 1024 / 1024) || 0;
    return { taskCount: tasks.length, totalMs: total.toFixed(0), top, heapMB: heap.toFixed(1) };
  });
  results.push({ tab, ...summary, elapsedMs: elapsed });
}

console.log('\n#tab                    tasks  ttotal   top3                heapMB  elapsed');
console.log('—'.repeat(80));
for (const r of results) {
  console.log(
    r.tab.padEnd(22),
    String(r.taskCount).padStart(5),
    String(r.totalMs).padStart(7),
    (r.top.join(',') || '—').padEnd(20),
    String(r.heapMB).padStart(6),
    String(r.elapsedMs).padStart(7)
  );
}

await browser.close();
