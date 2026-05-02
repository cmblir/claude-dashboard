#!/usr/bin/env node
/**
 * Deep flicker investigation: which DOM ancestor is being replaced repeatedly?
 */
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();

const TABS = ['orchestrator', 'aiProviders', 'ralph', 'overview', 'workflows'];

for (const tab of TABS) {
  await page.goto(`http://127.0.0.1:8080/#/${tab}`, { waitUntil: 'networkidle' });
  // Wait for AFTER hooks to settle
  await page.waitForTimeout(1500);

  const data = await page.evaluate(() => new Promise(resolve => {
    const counts = {};   // selector → count
    const lastWrite = {}; // selector → ts
    const obs = new MutationObserver(muts => {
      for (const m of muts) {
        const t = m.target;
        if (!t || !t.tagName) continue;
        const id = t.id || '';
        const cls = (t.className || '').toString().slice(0, 30);
        const key = id ? `#${id}` : `${t.tagName.toLowerCase()}.${cls}`;
        counts[key] = (counts[key] || 0) + 1;
        lastWrite[key] = Date.now();
      }
    });
    obs.observe(document.body, { childList: true, subtree: true, attributes: true });
    setTimeout(() => {
      obs.disconnect();
      // top 8 by count
      const top = Object.entries(counts).sort((a,b) => b[1]-a[1]).slice(0, 8);
      resolve({ top, totalNodes: Object.keys(counts).length });
    }, 5000);
  }));

  console.log(`\n${tab}:`);
  console.log(`  total mutated nodes: ${data.totalNodes}`);
  for (const [sel, n] of data.top) {
    console.log(`  ${n.toString().padStart(4)} × ${sel}`);
  }
}

await browser.close();
