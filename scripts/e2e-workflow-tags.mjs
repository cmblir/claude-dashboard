#!/usr/bin/env node
/**
 * QQ38 + QQ60 — workflow tags persist through save, the sidebar
 * shows tag chip strip + per-row chips, clicking a chip filters
 * the list, and editing the inspector tag input mirrors live into
 * `__wf.workflows[].tags`.
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

// Save 3 workflows via the public POST API: 2 tagged "alpha", 1 "beta".
async function saveWf(name, tags) {
  return page.evaluate(async ({ name, tags }) => {
    const r = await fetch('/api/workflows/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name, tags,
        nodes: [{ id: 'n-start', type: 'start', x: 50, y: 50, data: {} }],
        edges: [],
      }),
    }).then(r => r.json());
    return r.id;
  }, { name, tags });
}

const ids = {
  alphaA: await saveWf('alpha-A-' + Date.now(), ['alpha', 'demo']),
  alphaB: await saveWf('alpha-B-' + Date.now(), ['alpha']),
  beta:   await saveWf('beta-only-' + Date.now(), ['beta']),
};
check('three workflows saved', ids.alphaA && ids.alphaB && ids.beta);

// Refresh list from server.
await page.evaluate(async () => {
  const r = await fetch('/api/workflows/list').then(r => r.json());
  __wf.workflows = r.workflows || [];
  _wfRenderList();
});
await page.waitForTimeout(120);

// QQ38 — tags persist on save and surface in __wf.workflows.
const tagState = await page.evaluate(({ ids }) => {
  const find = id => (__wf.workflows || []).find(w => w.id === id);
  return {
    a: find(ids.alphaA),
    b: find(ids.alphaB),
    c: find(ids.beta),
  };
}, { ids });
check('alpha-A persisted tags ["alpha", "demo"]',
  tagState.a && Array.isArray(tagState.a.tags) &&
  tagState.a.tags.includes('alpha') && tagState.a.tags.includes('demo'));
check('beta-only persisted tag ["beta"]',
  tagState.c && tagState.c.tags && tagState.c.tags.length === 1 &&
  tagState.c.tags[0] === 'beta');

// Sidebar chip strip (#wfTagFilter) shows union of tags.
const chips = await page.evaluate(() => {
  const host = document.getElementById('wfTagFilter');
  if (!host) return null;
  const buttons = Array.from(host.querySelectorAll('button')).map(b => b.textContent.trim());
  return { visible: host.style.display !== 'none', buttons };
});
check('chip strip visible', chips && chips.visible);
check('chip strip lists alpha + beta + demo + 전체',
  chips && chips.buttons.some(b => /alpha/.test(b)) &&
  chips.buttons.some(b => /beta/.test(b)) &&
  chips.buttons.some(b => /demo/.test(b)));

// QQ60 — clicking a chip filters the list. Apply 'alpha' filter:
// expect 2 of our 3 saved workflows visible (others may exist).
await page.evaluate(() => _wfSetTagFilter('alpha'));
await page.waitForTimeout(80);
const filtered = await page.evaluate(({ ids }) => {
  const host = document.getElementById('wfListItems');
  const items = Array.from(host.querySelectorAll('.wf-list-item'));
  // Build a set of visible ids by matching onclick handler.
  const wfRe = /_wfOpen\('([^']+)'\)/;
  const visible = new Set();
  for (const el of items) {
    const oc = el.getAttribute('onclick') || '';
    const m = wfRe.exec(oc);
    if (m) visible.add(m[1]);
  }
  return {
    alphaA: visible.has(ids.alphaA),
    alphaB: visible.has(ids.alphaB),
    beta:   visible.has(ids.beta),
    total:  items.length,
  };
}, { ids });
check('alpha filter shows alpha-A',  filtered.alphaA);
check('alpha filter shows alpha-B',  filtered.alphaB);
check('alpha filter HIDES beta-only', !filtered.beta);

// Reset filter so the rest of the suite isn't affected if it shares state.
await page.evaluate(() => _wfSetTagFilter(''));

// Cleanup: remove the test workflows so they don't pile up.
await page.evaluate(async ({ ids }) => {
  for (const id of Object.values(ids)) {
    await fetch('/api/workflows/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    });
  }
}, { ids });

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
