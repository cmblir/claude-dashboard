#!/usr/bin/env node
/**
 * Cycle-23 (X batch) inspection — verify the recent UI changes the user
 * complained about:
 *   1. Screen flicker — record console + count renderView() loops + screenshot
 *   2. AI Provider setup wizard — does Codex CLI show up?
 *   3. Codex models display — are labels rendering correctly?
 *   4. Input box shapes — collect computed border-radius for inputs/selects
 *   5. Ralph loop tab — does it render? Any console errors?
 *
 * Output:
 *   - Per-tab JSON report at /tmp/x-inspect-<tab>.json
 *   - Screenshots at /tmp/x-shot-<tab>.png
 *   - Summary printed to stdout
 */
import { chromium } from 'playwright';
import { writeFileSync } from 'node:fs';

const BASE = process.env.BASE || `http://127.0.0.1:${process.env.PORT || 8080}`;
const HEADLESS = process.env.HEADLESS !== '0';

const browser = await chromium.launch({ headless: HEADLESS });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();

const results = {};

async function inspect(tabId, label) {
  console.log(`\n— ${label} (${tabId}) —`);
  const consoleMsgs = [];
  const errors = [];
  page.on('console', m => {
    const txt = m.text();
    consoleMsgs.push(`[${m.type()}] ${txt.slice(0, 200)}`);
  });
  page.on('pageerror', e => errors.push(e.message));

  await page.goto(`${BASE}/#/${tabId}`, { waitUntil: 'networkidle', timeout: 20000 });

  // Detect flicker: count innerHTML resets on the #view element over 3 seconds.
  const flicker = await page.evaluate(() => new Promise((resolve) => {
    const v = document.getElementById('view');
    if (!v) return resolve({ available: false });
    let resets = 0;
    const obs = new MutationObserver(muts => {
      for (const m of muts) {
        // Counting "innerHTML wipes" — when childList replaced everything
        if (m.type === 'childList' &&
            m.removedNodes.length > 1 &&
            m.addedNodes.length > 0) {
          resets++;
        }
      }
    });
    obs.observe(v, { childList: true, subtree: true });
    setTimeout(() => { obs.disconnect(); resolve({ available: true, resets }); }, 3000);
  }));

  // Collect input/select shape info
  const inputShapes = await page.evaluate(() => {
    const els = [...document.querySelectorAll('#view input, #view select, #view textarea')];
    return els.slice(0, 50).map(el => {
      const cs = window.getComputedStyle(el);
      return {
        tag: el.tagName.toLowerCase(),
        cls: el.className.slice(0, 60),
        radius: cs.borderRadius,
        border: cs.borderWidth + ' ' + cs.borderStyle + ' ' + cs.borderColor,
        bg: cs.backgroundColor,
      };
    });
  });
  // Bucket by radius value
  const byRadius = {};
  for (const i of inputShapes) {
    const r = i.radius;
    byRadius[r] = (byRadius[r] || 0) + 1;
  }

  await page.screenshot({ path: `/tmp/x-shot-${tabId}.png`, fullPage: false });

  results[tabId] = {
    label,
    flicker,
    inputShapes_total: inputShapes.length,
    inputShapes_byRadius: byRadius,
    inputShapes_sample: inputShapes.slice(0, 6),
    consoleMsgs: consoleMsgs.slice(-20),
    errors,
  };
  console.log('  flicker resets in 3s:', flicker.resets);
  console.log('  inputs on page:', inputShapes.length, '— radii:', byRadius);
  console.log('  console msgs (last 20):', consoleMsgs.length);
  console.log('  errors:', errors.length);
  if (errors.length) console.log('   ', errors.slice(0, 3));
}

await inspect('orchestrator',  'Orchestrator config');
await inspect('aiProviders',   'AI Providers tab');
await inspect('ralph',         'Ralph Loop tab');
await inspect('overview',      'Overview (sanity)');

writeFileSync('/tmp/x-inspect-report.json', JSON.stringify(results, null, 2));
console.log('\n=== summary written to /tmp/x-inspect-report.json ===');

await browser.close();
