#!/usr/bin/env node
/**
 * QQ138 — webhook URL + curl example respect the actual server origin.
 *
 * Until now the inspector hardcoded `http://localhost:8080/...` so when
 * the dashboard ran on any non-default port (e.g. PORT=19500, container,
 * remote tunnel), the user had to manually edit the URL after copying.
 * Both the input field and the curl `<pre>` snippet now use
 * `location.origin`.
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
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });

// Save a workflow so the inspector renders the webhook panel.
const wfId = await page.evaluate(async () => {
  const r = await fetch('/api/workflows/save', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'webhook-origin-' + Date.now(),
      nodes: [{ id: 'n-start', type: 'start', x: 50, y: 50, data: {} }],
      edges: [],
    }),
  }).then(r => r.json());
  return r.id;
});

await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('.wf-canvas, #wfCanvas', { timeout: 8000 });

// Open the saved workflow so __wf.current exists.
await page.evaluate(async (id) => {
  await _wfOpen(id);
}, wfId);
await page.waitForTimeout(300);

// Inspector renders the webhook input only when no node is selected (it
// lives in the workflow-level pane); ensure that's true.
await page.evaluate(() => {
  __wf.selectedNodeId = null;
  if (typeof _wfRenderInspector === 'function') _wfRenderInspector();
});
await page.waitForTimeout(150);

const probe = await page.evaluate(() => {
  const inp = document.getElementById('wfWebhookUrl');
  const pre = document.getElementById('wfWebhookCurl');
  return {
    url:  inp ? inp.value : null,
    curl: pre ? pre.textContent : null,
    origin: location.origin,
  };
});

check('webhook URL field exists', !!probe.url);
check(`webhook URL uses location.origin (${probe.origin})`,
  probe.url && probe.url.startsWith(probe.origin),
  `url=${probe.url}`);
check('webhook URL no longer hardcodes :8080',
  probe.url && !probe.url.includes('localhost:8080'),
  `url=${probe.url}`);
check('curl snippet exists', !!probe.curl);
check('curl snippet uses location.origin',
  probe.curl && probe.curl.includes(probe.origin),
  `curl=${(probe.curl || '').slice(0, 80)}`);

// Cleanup.
await page.evaluate(async (id) => {
  await fetch('/api/workflows/delete', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  });
}, wfId);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
