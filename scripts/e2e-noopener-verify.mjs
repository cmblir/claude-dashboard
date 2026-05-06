#!/usr/bin/env node
/**
 * Confirm every <a target="_blank"> rendered by the SPA carries
 * rel="noopener noreferrer" — without that, Chrome can't recycle the
 * spawned renderer independently of the dashboard, which user
 * complained about as "Helper (Renderer) processes accumulating".
 *
 * The audit walks the DOM after visiting several heavy tabs that
 * include external doc / homepage / repo links.
 */
import { chromium } from 'playwright';

const URL = process.env.URL || `http://127.0.0.1:${process.env.PORT || 8080}/`;
const TABS = ['overview', 'aiProviders', 'features', 'team', 'sessions', 'agents', 'workflows'];

let exitCode = 0;
function check(label, ok, detail) {
  const tag = ok ? '\x1b[32m✅\x1b[0m' : '\x1b[31m❌\x1b[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
await page.goto(URL, { waitUntil: 'networkidle' });

const offenders = [];
for (const tab of TABS) {
  await page.evaluate(t => location.hash = '#/' + t, tab);
  await page.waitForFunction(t => state.view === t, tab, { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(400);
  const bad = await page.evaluate(() => {
    const links = Array.from(document.querySelectorAll('a[target="_blank"]'));
    return links
      .filter(a => {
        const rel = (a.getAttribute('rel') || '').toLowerCase();
        return !rel.includes('noopener') || !rel.includes('noreferrer');
      })
      .map(a => a.outerHTML.slice(0, 200));
  });
  if (bad.length) offenders.push({ tab, bad });
}

if (offenders.length === 0) {
  check('every rendered <a target=_blank> has noopener noreferrer', true,
    `tabs scanned: ${TABS.length}`);
} else {
  check('every rendered <a target=_blank> has noopener noreferrer', false,
    `${offenders.length} tab(s) with violations`);
  for (const o of offenders) {
    console.log(`  · ${o.tab}: ${o.bad.length} offender(s)`);
    for (const html of o.bad.slice(0, 3)) console.log('    ', html);
  }
}

await browser.close();
console.log(exitCode === 0 ? '\nOK' : '\nFAIL');
process.exit(exitCode);
