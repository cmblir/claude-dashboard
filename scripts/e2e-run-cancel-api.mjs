#!/usr/bin/env node
/**
 * /api/workflows/run-cancel — cooperative cancel returns
 * `{ok: true, live: <bool>}`. With an invalid run id the API
 * rejects with `{ok: false, error: 'invalid runId'}`. With a real
 * but already-finished run id, `live === false`.
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

// Step 1 — POST run-cancel with no/invalid runId → ok=false.
const noId = await page.evaluate(() =>
  fetch('/api/workflows/run-cancel', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  }).then(r => r.json()));
check('run-cancel without runId returns ok=false',
  noId && noId.ok === false);
check('error message mentions runId',
  noId && /runId/.test(noId.error || ''));

const badId = await page.evaluate(() =>
  fetch('/api/workflows/run-cancel', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ runId: 'not-a-real-id' }),
  }).then(r => r.json()));
check('run-cancel with malformed runId returns ok=false',
  badId && badId.ok === false);

// Step 2 — fire a quick run, immediately cancel it. Even if it
// already finished, run-cancel should return `{ok:true, live:bool}`.
const wfId = await page.evaluate(async () => {
  const r = await fetch('/api/workflows/save', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'cancel-' + Date.now(),
      nodes: [{ id: 'n-start', type: 'start', x: 50, y: 50, data: {} }],
      edges: [],
    }),
  }).then(r => r.json());
  return r.id;
});
const rid = await page.evaluate(async (id) => {
  const r = await fetch('/api/workflows/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  }).then(r => r.json());
  return r.runId;
}, wfId);

const cancel = await page.evaluate(async (rid) =>
  fetch('/api/workflows/run-cancel', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ runId: rid }),
  }).then(r => r.json()), rid);
check('run-cancel for real runId returns ok=true', cancel && cancel.ok === true);
check('cancel response carries `live` boolean',
  typeof cancel.live === 'boolean');

// Cleanup.
await page.evaluate(async (id) => {
  await fetch('/api/workflows/delete', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  });
}, wfId);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
