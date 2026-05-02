#!/usr/bin/env node
/** BB1: verify n8n-style drawer dimensions, search, no infinite expand. */
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.addInitScript(() => { localStorage.setItem('dashboard-entered', '1'); });
await page.goto('http://127.0.0.1:8080/#/workflows', { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);

// Open the node editor for a brand-new node. We need __wf.current set
// or the function bails with a toast. Stub if missing.
const opened = await page.evaluate(() => {
  if (typeof _wfOpenNodeEditor !== 'function') return { error: 'no fn' };
  if (typeof __wf === 'undefined') return { error: '__wf undefined in this context' };
  if (!__wf.current) {
    __wf.current = { id: 'wf-stub', name: 'stub', nodes: [], edges: [],
                     viewport: { panX: 0, panY: 0, zoom: 1 } };
  }
  _wfOpenNodeEditor();   // no nid → new draft
  return { ok: true };
});
console.log('open:', opened);
if (opened.error) {
  await page.screenshot({ path: '/tmp/bb-fail.png', fullPage: false });
  await browser.close(); process.exit(1);
}
await page.waitForSelector('.wf-node-editor', { timeout: 3000 });
await page.waitForTimeout(500);

// Measure layout
const m1 = await page.evaluate(() => {
  const w = document.querySelector('.wf-node-editor');
  if (!w) return null;
  const cat = w.querySelector('[id$="-cat"]');
  const form = w.querySelector('[id$="-form"]');
  return {
    window:  { w: w.offsetWidth, h: w.offsetHeight },
    palette: { w: cat ? cat.offsetWidth  : 0, h: cat ? cat.offsetHeight : 0 },
    form:    { w: form ? form.offsetWidth : 0, h: form ? form.offsetHeight : 0 },
    hasSearch: !!w.querySelector('.wf-pal-search-input'),
    visibleCategories: w.querySelectorAll('.wf-pal-cat').length,
    paletteScrollable: cat ? cat.scrollHeight > cat.clientHeight : false,
  };
});
console.log('initial layout:', JSON.stringify(m1, null, 2));
await page.screenshot({ path: '/tmp/bb-drawer-initial.png' });

// Type into search to verify filtering
const inp = await page.$('.wf-pal-search-input');
if (inp) {
  await inp.fill('http');
  await page.waitForTimeout(250);
  const m2 = await page.evaluate(() => ({
    visibleCategories: document.querySelectorAll('.wf-node-editor .wf-pal-cat').length,
    visibleRows: document.querySelectorAll('.wf-node-editor .wf-pal-row').length,
  }));
  console.log('after search "http":', m2);
  await page.screenshot({ path: '/tmp/bb-drawer-search.png' });

  // Clear filter
  await inp.fill('');
  await page.waitForTimeout(150);
}

// Check no horizontal overflow / infinite growth
const m3 = await page.evaluate(() => {
  const w = document.querySelector('.wf-node-editor');
  if (!w) return null;
  const before = w.offsetHeight;
  // Toggle every category open and see if window grows
  document.querySelectorAll('.wf-node-editor .wf-pal-cat').forEach(c => c.classList.add('open'));
  const after = w.offsetHeight;
  return { before, after, sameSize: before === after };
});
console.log('window height stability under all-open:', m3);

await browser.close();
console.log('OK — see /tmp/bb-drawer-{initial,search}.png');
