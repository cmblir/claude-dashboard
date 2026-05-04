#!/usr/bin/env node
/**
 * Deep dashboard QA pass.
 *
 * Per tab:
 *   - Records console errors AND warnings AND page errors AND failed network requests.
 *   - Detects horizontal overflow on the viewport and on individual elements.
 *   - Detects elements whose textContent is being clipped by overflow:hidden.
 *   - Probes the auto-resume "+ binding" modal specifically for the picker shape.
 *   - Captures viewport scrollbar status at 320 / 768 / 1280 widths.
 *
 * Usage:
 *   node scripts/e2e-dashboard-qa.mjs
 *   PORT=8080 node scripts/e2e-dashboard-qa.mjs
 *   TAB_ID=workflows node scripts/e2e-dashboard-qa.mjs
 */
import { chromium } from 'playwright';
import { readFileSync, writeFileSync } from 'node:fs';

const BASE = process.env.BASE || `http://127.0.0.1:${process.env.PORT || 8080}`;
const HEADLESS = process.env.HEADLESS !== '0';
const ONLY = process.env.TAB_ID || null;
const REPORT = process.env.REPORT || 'qa-report.json';

function readTabIds() {
  const src = readFileSync(new URL('../server/nav_catalog.py', import.meta.url), 'utf8');
  const startMarker = 'TAB_CATALOG: list[tuple[';
  const idx = src.indexOf(startMarker);
  if (idx < 0) throw new Error('TAB_CATALOG not found');
  const tail = src.slice(idx);
  return [...tail.matchAll(/^\s*\("([a-zA-Z][a-zA-Z0-9_]*)"\s*,/gm)].map(m => m[1]);
}

const tabIds = ONLY ? [ONLY] : readTabIds();
console.log(`🔍 qa: ${tabIds.length} tabs · base=${BASE} · headless=${HEADLESS}`);

const browser = await chromium.launch({ headless: HEADLESS });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await context.newPage();

const buckets = {};
const collect = (id, key, val) => {
  buckets[id] ??= { errors: [], warnings: [], pageErrors: [], failedRequests: [], overflow: [], clipped: [], notes: [] };
  buckets[id][key].push(val);
};

let currentTab = '__init__';
page.on('console', msg => {
  const t = msg.type();
  if (t === 'error') collect(currentTab, 'errors', msg.text());
  else if (t === 'warning') collect(currentTab, 'warnings', msg.text());
});
page.on('pageerror', err => collect(currentTab, 'pageErrors', err.message));
page.on('requestfailed', req => {
  const url = req.url();
  // Ignore favicon / hot-reload noise
  if (/favicon|hot-update|sockjs/.test(url)) return;
  collect(currentTab, 'failedRequests', `${req.method()} ${url} — ${req.failure()?.errorText || 'unknown'}`);
});

await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForSelector('#nav', { timeout: 10000 }).catch(() => {});
await page.waitForTimeout(500);

async function probeOverflow(id) {
  const result = await page.evaluate(() => {
    const root = document.documentElement;
    const bodyOverflow = document.body.scrollWidth > document.body.clientWidth + 1;
    const docOverflow = root.scrollWidth > root.clientWidth + 1;
    const offenders = [];
    const clippedTexts = [];
    const all = document.querySelectorAll('*');
    for (const el of all) {
      const cs = getComputedStyle(el);
      // horizontal overflow within an element — but skip intentional truncations
      // (any element using text-overflow: ellipsis is showing "..." on purpose)
      const isIntentionalTruncate = cs.textOverflow === 'ellipsis'
        || (cs.overflow === 'hidden' && cs.whiteSpace === 'nowrap');
      if (
        el.scrollWidth - el.clientWidth > 4
        && cs.overflowX !== 'auto'
        && cs.overflowX !== 'scroll'
        && !isIntentionalTruncate
      ) {
        offenders.push({
          tag: el.tagName.toLowerCase(),
          id: el.id || '',
          cls: (el.className || '').toString().slice(0, 80),
          sw: el.scrollWidth, cw: el.clientWidth,
        });
      }
      // text clipped by overflow:hidden + ellipsis: ok. But if hidden + no ellipsis + wider text -> bad
      if ((cs.overflow === 'hidden' || cs.overflowX === 'hidden') && cs.textOverflow !== 'ellipsis') {
        if (el.scrollWidth > el.clientWidth + 2 && el.textContent && el.textContent.trim().length > 0 && el.children.length === 0) {
          clippedTexts.push({
            tag: el.tagName.toLowerCase(),
            id: el.id || '',
            text: (el.textContent || '').trim().slice(0, 60),
          });
        }
      }
    }
    return { bodyOverflow, docOverflow, offenders: offenders.slice(0, 20), clippedTexts: clippedTexts.slice(0, 20) };
  });
  if (result.bodyOverflow || result.docOverflow) {
    collect(id, 'overflow', { scope: 'viewport', bodyOverflow: result.bodyOverflow, docOverflow: result.docOverflow });
  }
  for (const o of result.offenders) collect(id, 'overflow', { scope: 'element', ...o });
  for (const c of result.clippedTexts) collect(id, 'clipped', c);
}

async function gotoTab(id) {
  await page.evaluate(tid => { location.hash = '#/' + tid; }, id);
  await page.waitForTimeout(450);
}

for (const id of tabIds) {
  currentTab = id;
  buckets[id] ??= { errors: [], warnings: [], pageErrors: [], failedRequests: [], overflow: [], clipped: [], notes: [] };
  try {
    await gotoTab(id);
    const ok = await page.evaluate(tid => {
      try {
        return (window.state && window.state.view) === tid;
      } catch { return false; }
    }, id);
    if (!ok) collect(id, 'notes', 'view did not switch');
    await page.waitForTimeout(150);
    await probeOverflow(id);
  } catch (e) {
    collect(id, 'pageErrors', '[probe] ' + (e?.message || String(e)));
  }
}

// Auto-resume add-binding modal probe (autoResumeManager tab)
currentTab = 'autoResumeManager';
try {
  await gotoTab('autoResumeManager');
  await page.waitForTimeout(250);
  const opened = await page.evaluate(() => {
    if (typeof window._armOpenAddDialog !== 'function') return { hasFn: false };
    return window._armOpenAddDialog().then(() => ({ hasFn: true })).catch(e => ({ hasFn: true, err: String(e) }));
  });
  await page.waitForTimeout(700);
  const modalShape = await page.evaluate(() => {
    const sel = document.getElementById('armSidPick');
    const sid = document.getElementById('armSid');
    const cwd = document.getElementById('armCwd');
    return {
      hasSelect: !!sel,
      optionCount: sel ? sel.options.length : 0,
      sidEmpty: sid ? !sid.value : true,
      cwdEmpty: cwd ? !cwd.value : true,
      sample: sel ? Array.from(sel.options).slice(0, 4).map(o => ({ v: o.value, t: o.text.slice(0, 40) })) : [],
    };
  });
  collect('autoResumeManager', 'notes', `addDialog: hasSelect=${modalShape.hasSelect} options=${modalShape.optionCount}`);
  // pick first non-default option and confirm autofill
  if (modalShape.hasSelect && modalShape.optionCount > 1) {
    const filled = await page.evaluate(() => {
      const sel = document.getElementById('armSidPick');
      sel.value = '0';
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      const sid = document.getElementById('armSid');
      const cwd = document.getElementById('armCwd');
      return { sid: sid.value, cwd: cwd.value };
    });
    collect('autoResumeManager', 'notes', `autofill: sid=${filled.sid.slice(0,8)} cwd=${filled.cwd}`);
    if (!filled.sid) collect('autoResumeManager', 'errors', 'pick session did not autofill UUID');
  }
  // close modal
  await page.evaluate(() => { try { window.closeModal && window.closeModal(); } catch (_) {} });
  await page.waitForTimeout(150);
} catch (e) {
  collect('autoResumeManager', 'pageErrors', '[modal probe] ' + (e?.message || String(e)));
}

// Mobile viewport overflow check at 320 px
await context.setViewportSize ? null : null; // page-scoped only
await page.setViewportSize({ width: 320, height: 800 });
for (const id of ['overview', 'sessions', 'workflows', 'cliSessions', 'autoResumeManager']) {
  currentTab = id;
  try {
    await gotoTab(id);
    await page.waitForTimeout(250);
    const r = await page.evaluate(() => ({
      sw: document.documentElement.scrollWidth,
      cw: document.documentElement.clientWidth,
    }));
    if (r.sw > r.cw + 1) collect(id, 'overflow', { scope: 'viewport@320', sw: r.sw, cw: r.cw });
  } catch (e) {
    collect(id, 'pageErrors', '[mobile] ' + (e?.message || String(e)));
  }
}

await browser.close();

let totalErrors = 0, totalPageErrors = 0, totalOverflow = 0, totalClipped = 0, totalFailed = 0;
const offenderIds = [];
for (const [id, b] of Object.entries(buckets)) {
  totalErrors += b.errors.length;
  totalPageErrors += b.pageErrors.length;
  totalOverflow += b.overflow.length;
  totalClipped += b.clipped.length;
  totalFailed += b.failedRequests.length;
  if (b.errors.length || b.pageErrors.length || b.overflow.length || b.clipped.length || b.failedRequests.length) {
    offenderIds.push(id);
  }
}

writeFileSync(REPORT, JSON.stringify(buckets, null, 2));
console.log('\n=== summary ===');
console.log(`tabs probed: ${Object.keys(buckets).length}`);
console.log(`tabs with issues: ${offenderIds.length} → ${offenderIds.join(', ')}`);
console.log(`console errors: ${totalErrors}`);
console.log(`page errors: ${totalPageErrors}`);
console.log(`overflow violations: ${totalOverflow}`);
console.log(`clipped text nodes: ${totalClipped}`);
console.log(`failed network: ${totalFailed}`);
console.log(`report → ${REPORT}`);

const fatal = totalPageErrors + totalErrors;
process.exit(fatal > 0 ? 1 : 0);
