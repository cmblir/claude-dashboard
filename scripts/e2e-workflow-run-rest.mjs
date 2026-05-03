#!/usr/bin/env node
/**
 * REST run pipeline — POST /api/workflows/run on a `start`-only
 * workflow finishes synchronously (no provider needed) and the
 * run-status endpoint reports `ok`. Verifies the basic plumbing
 * of run id → SQLite → status fetch.
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
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });

// Step 1 — save a `start`-only workflow.
const wfId = await page.evaluate(async () => {
  const r = await fetch('/api/workflows/save', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'run-rest-' + Date.now(),
      nodes: [{ id: 'n-start', type: 'start', x: 50, y: 50, data: {} }],
      edges: [],
    }),
  }).then(r => r.json());
  return r.id;
});
check('start-only workflow saved', !!wfId);

// Step 2 — fire run.
const runId = await page.evaluate(async (id) => {
  const r = await fetch('/api/workflows/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  }).then(r => r.json());
  return r.runId || r.id || null;
}, wfId);
check('/api/workflows/run returned a runId', !!runId);

// Step 3 — poll run-status until terminal (ok/err/cancelled).
const finalStatus = await page.evaluate(async (rid) => {
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 100));
    const r = await fetch('/api/workflows/run-status?runId=' + encodeURIComponent(rid))
      .then(r => r.json());
    const run = r.run || r;
    const s = run && (run.status || run.state);
    if (s && s !== 'running') return { status: s, run };
  }
  return { status: 'timeout' };
}, runId);
check('run-status reports terminal status', finalStatus.status === 'ok');
check('nodeResults includes n-start', !!(finalStatus.run && finalStatus.run.nodeResults && finalStatus.run.nodeResults['n-start']));

// Step 4 — /api/workflows/runs?wfId=… returns the run we just fired.
const runsList = await page.evaluate(async (id) => {
  const r = await fetch('/api/workflows/runs?wfId=' + encodeURIComponent(id))
    .then(r => r.json());
  return (r.runs || r.items || []).length;
}, wfId);
check('/api/workflows/runs?wfId=… returns the run', runsList >= 1);

// Cleanup.
await page.evaluate(async (id) => {
  await fetch('/api/workflows/delete', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  });
}, wfId);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
