#!/usr/bin/env node
/**
 * QQ5 / PP2 / PP3 — node disable badge + class flip via the public
 * `_wfToggleNodeDisabled(nid)` helper. Verifies that the QQ108
 * snap-key digest catches the toggle so the canvas badge updates
 * immediately.
 */
import { chromium } from 'playwright';

const PORT = process.env.PORT || '19500';
const URL  = `http://127.0.0.1:${PORT}/`;

function check(label, ok) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}`);
  if (!ok) process.exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1200 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('#wfCanvasHost', { timeout: 8000 });

await page.evaluate(() => {
  const wf = {
    id: 'wf-disable',
    name: 'disable',
    nodes: [
      { id: 'n-a', type: 'session', x: 100, y: 100, title: 'A', data: { subject: 'a' } },
    ],
    edges: [],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 1, edgeCount: 0, stickyCount: 0,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
});
await page.waitForTimeout(120);

// Initial state — not disabled.
const initial = await page.evaluate(() => {
  const el = document.querySelector('.wf-node[data-node="n-a"]');
  return {
    hasDisabledClass: el.classList.contains('wf-disabled'),
    hasBadge: !!el.querySelector('.wf-node-disabled-badge'),
    badgeVisible: (() => {
      const b = el.querySelector('.wf-node-disabled-badge');
      if (!b) return false;
      // Visible only when CSS class .wf-disabled is set on parent.
      return getComputedStyle(b).display !== 'none';
    })(),
    dataDisabled: !!(__wf.current.nodes[0].data && __wf.current.nodes[0].data.disabled),
  };
});
check('initial: data.disabled = false', initial.dataDisabled === false);
check('initial: no .wf-disabled class', initial.hasDisabledClass === false);
check('badge element always present in SVG (CSS-gated)',
  initial.hasBadge === true);

// Toggle disable on.
await page.evaluate(() => _wfToggleNodeDisabled('n-a'));
await page.waitForTimeout(80);

const onState = await page.evaluate(() => {
  const el = document.querySelector('.wf-node[data-node="n-a"]');
  const b = el.querySelector('.wf-node-disabled-badge');
  return {
    classOn: el.classList.contains('wf-disabled'),
    dataDisabled: !!(__wf.current.nodes[0].data && __wf.current.nodes[0].data.disabled),
    badgeVisible: b ? getComputedStyle(b).display !== 'none' : false,
  };
});
check('after toggle: data.disabled = true', onState.dataDisabled === true);
check('after toggle: .wf-disabled class added',  onState.classOn === true);
check('⏸ badge becomes visible',                  onState.badgeVisible === true);

// Toggle off.
await page.evaluate(() => _wfToggleNodeDisabled('n-a'));
await page.waitForTimeout(80);

const offState = await page.evaluate(() => {
  const el = document.querySelector('.wf-node[data-node="n-a"]');
  const b = el.querySelector('.wf-node-disabled-badge');
  return {
    classOff: !el.classList.contains('wf-disabled'),
    dataDisabled: !!(__wf.current.nodes[0].data && __wf.current.nodes[0].data.disabled),
    badgeVisible: b ? getComputedStyle(b).display !== 'none' : false,
  };
});
check('after un-toggle: data.disabled = false',  offState.dataDisabled === false);
check('after un-toggle: .wf-disabled removed',    offState.classOff === true);
check('⏸ badge hidden again',                     offState.badgeVisible === false);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
