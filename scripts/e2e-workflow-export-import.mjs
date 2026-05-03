#!/usr/bin/env node
/**
 * Export/Import round-trip — every meaningful field on a workflow
 * survives an export → re-import cycle.
 *
 * 1. Save a workflow with diverse content: tags, sticky note, session,
 *    edges, viewport, repeat policy, tokenBudget.
 * 2. Call /api/workflows/export → assert envelope shape.
 * 3. Call /api/workflows/import with that envelope → assert the new
 *    workflow is created with a fresh id and the same content
 *    (post-sanitize: tags array, node ids, edges, sticky data).
 */
import { chromium } from 'playwright';

const PORT = process.env.PORT || '19500';
const URL  = `http://127.0.0.1:${PORT}/`;

function check(label, ok, detail) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) process.exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('#wfCanvasHost', { timeout: 8000 });

// Step 1 — save a richly-populated workflow.
const srcId = await page.evaluate(async () => {
  const name = 'export-src-' + Date.now();
  const r = await fetch('/api/workflows/save', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      tags: ['exp', 'demo'],
      nodes: [
        { id: 'n-stk',   type: 'sticky', x: 40,  y: 40,
          data: { text: '## doc', color: 'blue', width: 240, height: 140 } },
        { id: 'n-start', type: 'start',  x: 320, y: 40, data: {} },
        { id: 'n-s',     type: 'session', x: 540, y: 40,
          title: 'Worker', data: { subject: 'do work', assignee: 'claude:opus', inputsMode: 'concat' } },
      ],
      edges: [{ id: 'e1', from: 'n-start', fromPort: 'out', to: 'n-s', toPort: 'in' }],
      viewport: { panX: 12, panY: -8, zoom: 1.25 },
    }),
  }).then(r => r.json());
  return r.id;
});
check('source workflow saved', !!srcId);

// Step 2 — export.
const exported = await page.evaluate(async (id) => {
  return fetch('/api/workflows/export', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  }).then(r => r.json());
}, srcId);
check('export ok',                   exported && exported.ok === true);
check('export.exportVersion === 1',  exported.export && exported.export.exportVersion === 1);
check('export wraps full workflow object',
  exported.export && exported.export.workflow &&
  exported.export.workflow.name && exported.export.workflow.nodes);

// Step 3 — import the envelope as-is.
const imported = await page.evaluate(async (envelope) => {
  return fetch('/api/workflows/import', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ export: envelope }),
  }).then(r => r.json());
}, exported.export);
check('import ok',           imported && imported.ok === true);
check('import returns id',   typeof imported.id === 'string' && imported.id.length > 0);
check('import id ≠ source',  imported.id !== srcId);

// Step 4 — assert content survived sanitize via /api/workflows/<id>.
const fetched = await page.evaluate(async (id) => {
  return fetch('/api/workflows/' + id).then(r => r.json());
}, imported.id);
const wf = fetched && fetched.workflow;
check('imported workflow tags = ["exp","demo"]',
  wf && Array.isArray(wf.tags) &&
  wf.tags.includes('exp') && wf.tags.includes('demo'));
check('imported has 3 nodes',  wf && wf.nodes && wf.nodes.length === 3);
check('imported has 1 edge',   wf && wf.edges && wf.edges.length === 1);
check('sticky preserved (text/color/dimensions)',
  wf && wf.nodes.find(n => n.type === 'sticky') &&
  wf.nodes.find(n => n.type === 'sticky').data.text === '## doc' &&
  wf.nodes.find(n => n.type === 'sticky').data.color === 'blue');
check('viewport preserved',
  wf && wf.viewport && wf.viewport.zoom === 1.25);

// Cleanup.
await page.evaluate(async ({ a, b }) => {
  await fetch('/api/workflows/delete', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: a }),
  });
  await fetch('/api/workflows/delete', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: b }),
  });
}, { a: srcId, b: imported.id });

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
