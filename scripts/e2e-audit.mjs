#!/usr/bin/env node
/**
 * Comprehensive audit — full tab sweep collecting signals for UX improvements.
 *
 * Per tab:
 *   - Console errors / warnings
 *   - Failed network (4xx / 5xx) — excluding 401/404 by design
 *   - Load time (navigate -> idle)
 *   - Empty-state ("데이터 없음" / "No data") occurrence
 *   - Visible fetch-style error text ("실패", "Error", etc.)
 *   - Horizontal overflow (wider than viewport)
 *   - Buttons with no accessible name
 *   - Viewport-overflow elements (clipped)
 */
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';

const BASE = process.env.BASE || 'http://127.0.0.1:8080';
const HEADLESS = process.env.HEADLESS !== '0';

function readTabIds() {
  const src = readFileSync(new URL('../server/nav_catalog.py', import.meta.url), 'utf8');
  const idx = src.indexOf('TAB_CATALOG: list[tuple[');
  return [...src.slice(idx).matchAll(/^\s*\("([a-zA-Z][a-zA-Z0-9_]*)"\s*,/gm)].map(m => m[1]);
}

const tabs = readTabIds();
const browser = await chromium.launch({ headless: HEADLESS });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

const perTab = {};
let currentTab = 'boot';
page.on('console', msg => {
  const type = msg.type();
  if (type === 'error' || type === 'warning') {
    perTab[currentTab] = perTab[currentTab] || { errors: [], warnings: [], failed: [] };
    perTab[currentTab][type === 'error' ? 'errors' : 'warnings'].push(msg.text().slice(0, 160));
  }
});
page.on('pageerror', e => {
  perTab[currentTab] = perTab[currentTab] || { errors: [], warnings: [], failed: [] };
  perTab[currentTab].errors.push('[pageerror] ' + e.message.slice(0, 160));
});
page.on('response', resp => {
  const s = resp.status();
  if (s >= 400 && s !== 404 && !resp.url().includes('favicon')) {
    perTab[currentTab] = perTab[currentTab] || { errors: [], warnings: [], failed: [] };
    perTab[currentTab].failed.push(`${s} ${resp.url().replace(BASE,'')}`);
  }
});

await page.goto(BASE, { waitUntil: 'networkidle' });
try { await page.waitForSelector('#gateContinueBtn', { timeout: 5000 }); } catch {}
const gb = await page.$('#gateContinueBtn'); if (gb) await gb.click();
await page.waitForFunction(() => document.querySelectorAll('.nav-category').length >= 6, { timeout: 8000 });

const perfReport = [];
const emptyTabs = [];
const errorTextTabs = [];
const overflowTabs = [];
const unlabeledBtns = [];

for (const id of tabs) {
  currentTab = id;
  const t0 = Date.now();
  await page.evaluate((t) => { location.hash = '#/' + t; }, id);
  // 렌더 완료 대기: view innerHTML 채워질 때까지
  try {
    await page.waitForFunction((t) =>
      typeof state !== 'undefined' && state.view === t && document.getElementById('view').innerHTML.length > 100,
      id, { timeout: 6000 });
  } catch {}
  await page.waitForTimeout(250);
  const elapsed = Date.now() - t0;
  perfReport.push({ id, elapsed });

  // empty-state / error / overflow signals
  const signals = await page.evaluate(() => {
    const view = document.getElementById('view');
    const text = view ? view.textContent : '';
    const hasEmpty = /데이터 없음|데이터가 없습니다|No data|empty|아직 없습니다/.test(text) && text.length < 400;
    const errRe = /(렌더 실패|fetch failed|Error:|에러:|실패:|Internal Server)/;
    const errHit = errRe.exec(text);
    const hasError = !!errHit;
    // horizontal overflow
    const hOverflow = document.documentElement.scrollWidth > window.innerWidth + 4;
    // unlabeled buttons
    const unlabeled = Array.from(document.querySelectorAll('button')).filter(b => {
      const txt = (b.innerText || '').trim();
      const aria = b.getAttribute('aria-label');
      const title = b.getAttribute('title');
      return !txt && !aria && !title;
    }).length;
    return { hasEmpty, hasError, errSample: errHit ? errHit[0] : '', hOverflow, unlabeled };
  });
  if (signals.hasEmpty) emptyTabs.push(id);
  if (signals.hasError) errorTextTabs.push({ id, sample: signals.errSample });
  if (signals.hOverflow) overflowTabs.push(id);
  if (signals.unlabeled > 0) unlabeledBtns.push({ id, count: signals.unlabeled });
}

await browser.close();

// Summary
console.log(`\n====== Audit summary (${tabs.length} tabs) ======\n`);
const failed = Object.entries(perTab).filter(([k,v]) => v && (v.errors.length || v.warnings.length || v.failed.length));
console.log(`Tabs with console errors/warnings/failed-network: ${failed.length}`);
for (const [tab, data] of failed) {
  if (data.errors.length) {
    console.log(`  [${tab}] errors:`);
    data.errors.slice(0, 3).forEach(e => console.log(`    · ${e}`));
  }
  if (data.failed.length) {
    console.log(`  [${tab}] failed HTTP:`);
    data.failed.slice(0, 3).forEach(f => console.log(`    · ${f}`));
  }
}

console.log(`\nSlowest 10 tabs:`);
perfReport.sort((a,b) => b.elapsed - a.elapsed).slice(0,10).forEach(r =>
  console.log(`  ${r.elapsed.toString().padStart(5)}ms  ${r.id}`));

console.log(`\nTabs showing empty-state shell: ${emptyTabs.length}`);
emptyTabs.forEach(id => console.log(`  · ${id}`));

console.log(`\nTabs showing visible error text: ${errorTextTabs.length}`);
errorTextTabs.forEach(e => console.log(`  · ${e.id}: "${e.sample}"`));

console.log(`\nTabs with horizontal overflow (desktop 1440w): ${overflowTabs.length}`);
overflowTabs.forEach(id => console.log(`  · ${id}`));

console.log(`\nTabs with unlabeled buttons (a11y): ${unlabeledBtns.length}`);
unlabeledBtns.forEach(x => console.log(`  · ${x.id}: ${x.count} btns`));
