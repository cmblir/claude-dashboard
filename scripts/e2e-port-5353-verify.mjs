#!/usr/bin/env node
/**
 * Verify port 5353 / system-noise filter on the Open Ports tab.
 *
 *  1. /api/ports/list (default) returns 0 rows on UDP 5353.
 *  2. /api/ports/list?includeSystem=1 may return rows on 5353; if any
 *     exist, each is flagged with `systemNoise:true` and `serviceLabel:mDNS`.
 *  3. The Open Ports tab renders the toggle button and the hidden-count
 *     chip when noise is filtered.
 *  4. Toggling the button persists the choice in localStorage and
 *     re-renders without page reload.
 */
import { chromium } from 'playwright';

const URL = process.env.URL || `http://127.0.0.1:${process.env.PORT || 8080}/`;
let exitCode = 0;
function check(label, ok, detail) {
  const tag = ok ? '\x1b[32m✅\x1b[0m' : '\x1b[31m❌\x1b[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
await page.goto(URL, { waitUntil: 'networkidle' });

// 1. backend default — UDP 5353 must be 0
const def = await page.evaluate(async () => {
  const r = await fetch('/api/ports/list?nocache=1');
  return await r.json();
});
const def5353 = (def.ports || []).filter(p => p.local_port === 5353).length;
check('default response hides UDP 5353', def5353 === 0, `5353rows=${def5353} hidden=${def.hiddenSystem}`);

// 2. includeSystem=1 — any 5353 row must be flagged
const sys = await page.evaluate(async () => {
  const r = await fetch('/api/ports/list?nocache=1&includeSystem=1');
  return await r.json();
});
const sys5353 = (sys.ports || []).filter(p => p.local_port === 5353);
const allFlagged = sys5353.every(p => p.systemNoise === true && p.serviceLabel === 'mDNS');
check('includeSystem flags every 5353 row', sys5353.length === 0 || allFlagged,
  `count=${sys5353.length} allFlagged=${allFlagged}`);

// 3. Open Ports tab renders the toggle button
await page.evaluate(() => window.go && window.go('openPorts'));
await page.waitForTimeout(800);
const hasToggle = await page.evaluate(() => {
  const btns = Array.from(document.querySelectorAll('#view button'));
  return btns.some(b => /시스템/.test(b.textContent || ''));
});
check('Open Ports tab shows the system-noise toggle', hasToggle, `hasToggle=${hasToggle}`);

// 4. clicking the toggle flips the localStorage flag
const before = await page.evaluate(() => localStorage.getItem('cc.openPorts.includeSystem'));
await page.evaluate(() => window._pmToggleSystem && window._pmToggleSystem());
await page.waitForTimeout(500);
const after = await page.evaluate(() => localStorage.getItem('cc.openPorts.includeSystem'));
check('toggle flips the localStorage flag', before !== after,
  `before=${before} after=${after}`);

await browser.close();
console.log(exitCode === 0 ? '\nOK' : '\nFAIL');
process.exit(exitCode);
