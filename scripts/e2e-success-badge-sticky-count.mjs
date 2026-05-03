#!/usr/bin/env node
/**
 * QQ78 — sidebar success-rate badge appears for workflows with ≥3
 * runs in lastRuns and uses the right colour bucket.
 * QQ79 — list API splits sticky from executable node count.
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

// Save a workflow with 1 sticky + 2 executable nodes via REST.
const { id, name } = await page.evaluate(async () => {
  const name = 'qq79-split-' + Date.now();
  const r = await fetch('/api/workflows/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      nodes: [
        { id: 'n-stk',   type: 'sticky', x: 50, y: 50, data: { text: 'note', color: 'yellow', width: 220, height: 140 } },
        { id: 'n-start', type: 'start',   x: 280, y: 50, data: {} },
        { id: 'n-s',     type: 'session', x: 460, y: 50, data: { subject: 'x', assignee: 'claude:opus' } },
      ],
      edges: [{ id: 'e1', from: 'n-start', fromPort: 'out', to: 'n-s', toPort: 'in' }],
    }),
  }).then(r => r.json());
  return { id: r.id, name };
});
check('workflow saved', !!id);

// Check the list API directly for QQ79 split.
const listed = await page.evaluate(async (id) => {
  const r = await fetch('/api/workflows/list').then(r => r.json());
  return (r.workflows || []).find(w => w.id === id);
}, id);
check(`QQ79: nodeCount = 2 (start + session, sticky excluded)`,
  listed && listed.nodeCount === 2);
check('QQ79: stickyCount = 1', listed && listed.stickyCount === 1);
check('QQ79: edgeCount = 1', listed && listed.edgeCount === 1);

// Inject synthetic lastRuns into the client-side workflow cache so the
// QQ78 success-rate badge has data to render. First sync the cache from
// the server (the freshly-saved id wasn't there yet).
await page.evaluate(async (id) => {
  const r = await fetch('/api/workflows/list').then(r => r.json());
  __wf.workflows = (r.workflows || []).map(w => {
    if (w.id !== id) return w;
    return {
      ...w,
      lastRuns: [
        { status: 'ok',  durationMs: 1200 },
        { status: 'ok',  durationMs: 1100 },
        { status: 'err', durationMs: 800, error: 'oops' },
        { status: 'ok',  durationMs: 1300 },
        { status: 'ok',  durationMs: 1000 },
      ],
    };
  });
  _wfRenderList();
}, id);
await page.waitForTimeout(120);

// Find the row in the sidebar and check the % chip.
const badge = await page.evaluate((id) => {
  const host = document.getElementById('wfListItems');
  const items = Array.from(host.querySelectorAll('.wf-list-item'));
  const re = /_wfOpen\('([^']+)'\)/;
  const row = items.find(el => {
    const oc = el.getAttribute('onclick') || '';
    const m = re.exec(oc);
    return m && m[1] === id;
  });
  if (!row) return null;
  const text = row.textContent;
  // The badge text is e.g. "80%". 4 ok / 5 = 80%
  const m = /(\d+)%/.exec(text);
  return m ? m[1] : null;
}, id);
check('QQ78 success-rate badge shows 80%', badge === '80');

// Cleanup.
await page.evaluate(async (id) => {
  await fetch('/api/workflows/delete', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  });
}, id);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
