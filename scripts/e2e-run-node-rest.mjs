#!/usr/bin/env node
/**
 * QQ18 — POST /api/workflows/run-node executes a single
 * session/subagent node in isolation. With a Pin Data flag the
 * node short-circuits to the pinned output without invoking
 * any provider — perfect for a no-API-key smoke test.
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

// Save a workflow with a session node that has Pin Data set, so
// the QQ18 single-node path takes the QQ20 short-circuit and we
// don't need a real provider.
const wfId = await page.evaluate(async () => {
  const r = await fetch('/api/workflows/save', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'run-node-' + Date.now(),
      nodes: [
        { id: 'n-pin', type: 'session', x: 50, y: 50,
          data: { subject: 'x', assignee: 'claude:opus',
                  pinned: true, pinnedOutput: 'frozen-cache-hit' } },
      ],
      edges: [],
    }),
  }).then(r => r.json());
  return r.id;
});
check('workflow saved', !!wfId);

const r = await page.evaluate(async (id) => {
  return fetch('/api/workflows/run-node', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ wfId: id, nodeId: 'n-pin', inputs: ['ignored'] }),
  }).then(r => r.json());
}, wfId);

check('/api/workflows/run-node ok=true', r && r.ok === true);
check('returned node id matches', r && r.nodeId === 'n-pin');
check('result.status === "ok"',          r && r.result && r.result.status === 'ok');
check('result.output is the pinned text',
  r && r.result && r.result.output === 'frozen-cache-hit');
check('result.provider === "pinned"',     r && r.result && r.result.provider === 'pinned');
check('result.cost === 0',                r && r.result && r.result.cost === 0);

// Cleanup.
await page.evaluate(async (id) => {
  await fetch('/api/workflows/delete', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  });
}, wfId);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
