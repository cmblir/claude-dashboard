#!/usr/bin/env node
/**
 * Long-session leak probe.
 *
 * Walks through 67 tabs once, then ping-pongs between 5 heavy tabs
 * (workflows, agents, sessions, lazyclawDashboard, lazyclawChat) for
 * another 50 navigations. Reports JS heap before/after + total
 * scripting time accumulated. A clean session sees roughly flat heap;
 * a leaky AFTER hook shows monotonic growth.
 */
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';

const BASE = process.env.BASE || `http://127.0.0.1:${process.env.PORT || 8080}`;

function readTabIds() {
  const src = readFileSync(new URL('../server/nav_catalog.py', import.meta.url), 'utf8');
  const idx = src.indexOf('TAB_CATALOG: list[tuple[');
  return [...src.slice(idx).matchAll(/^\s*\("([a-zA-Z][a-zA-Z0-9_]*)"\s*,/gm)].map(m => m[1]);
}
const tabs = readTabIds();

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
await page.addInitScript(() => {
  window.__perfTasks = [];
  try { new PerformanceObserver(l => l.getEntries().forEach(e => window.__perfTasks.push(e.duration))).observe({type:'longtask',buffered:true}); } catch(_){}
});
await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForTimeout(500);

async function snapshot(label) {
  // Force GC via low-level CDP so the heap reading is steady-state.
  const client = await page.context().newCDPSession(page);
  try { await client.send('HeapProfiler.collectGarbage'); } catch (_) {}
  const m = await page.evaluate(() => ({
    heapMB: ((performance.memory && performance.memory.usedJSHeapSize) || 0) / 1048576,
    longSum: (window.__perfTasks || []).reduce((s, x) => s + x, 0),
    longCount: (window.__perfTasks || []).length,
  }));
  console.log(`${label.padEnd(28)} heap=${m.heapMB.toFixed(1).padStart(5)}MB  longSum=${m.longSum.toFixed(0).padStart(5)}ms  count=${m.longCount}`);
  return m;
}

const before = await snapshot('boot');

// Phase 1 — sweep all 67 tabs once.
for (const tab of tabs) {
  await page.evaluate(t => location.hash = '#/' + t, tab);
  await page.waitForFunction(t => state && state.view === t, tab, { timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(120);
}
const afterSweep = await snapshot('after 67-tab sweep');

// Phase 2 — ping-pong 50 navigations across the heavy tabs.
const heavy = ['workflows', 'agents', 'sessions', 'lazyclawDashboard', 'lazyclawChat'];
for (let i = 0; i < 50; i++) {
  const tab = heavy[i % heavy.length];
  await page.evaluate(t => location.hash = '#/' + t, tab);
  await page.waitForFunction(t => state && state.view === t, tab, { timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(80);
}
const afterPingPong = await snapshot('after 50 ping-pongs');

// Final force GC + idle.
await page.waitForTimeout(800);
const finalSnap = await snapshot('after 800ms idle');

console.log('\n--- summary ---');
console.log(`boot heap:        ${before.heapMB.toFixed(1)} MB`);
console.log(`final heap:       ${finalSnap.heapMB.toFixed(1)} MB`);
console.log(`heap growth:      ${(finalSnap.heapMB - before.heapMB).toFixed(1)} MB over ${tabs.length + 50} navigations`);
console.log(`total scripting:  ${finalSnap.longSum.toFixed(0)} ms across ${finalSnap.longCount} longtasks`);

await browser.close();
