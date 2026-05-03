#!/usr/bin/env node
/**
 * Node search filter (LL24 fuzzy) + inspector webhook URL display.
 *
 * 1. _wfNodeSearchFilter('fy') matches a 'frontend' titled node and
 *    dims the others.
 * 2. Empty query restores all opacity = ''.
 * 3. Inspector renders the workflow's webhook URL field (the
 *    /api/workflows/webhook/<id> endpoint identifier).
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

await page.evaluate(() => {
  const wf = {
    id: 'wf-search-test',
    name: 'search-test',
    description: 'has webhook',
    nodes: [
      { id: 'n-fe', type: 'session', x:  80, y: 100, title: 'frontend',  data: { subject: 'x' } },
      { id: 'n-be', type: 'session', x: 320, y: 100, title: 'backend',   data: { subject: 'y' } },
      { id: 'n-db', type: 'session', x: 540, y: 100, title: 'database',  data: { subject: 'z' } },
    ],
    edges: [],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 3, edgeCount: 0, stickyCount: 0,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
});
await page.waitForTimeout(120);

// LL24 fuzzy — "fnd" matches "frontend" as subsequence (f,n,d).
await page.evaluate(() => _wfNodeSearchFilter('fnd'));
await page.waitForTimeout(80);
const f1 = await page.evaluate(() => {
  const op = id => (document.querySelector(`.wf-node[data-node="${id}"]`) || {}).style?.opacity;
  return { fe: op('n-fe'), be: op('n-be'), db: op('n-db') };
});
check('"fnd" highlights n-fe (frontend) opacity = 1', f1.fe === '1');
check('"fnd" dims n-be (backend) to opacity 0.2', f1.be === '0.2');
check('"fnd" dims n-db (database) to opacity 0.2', f1.db === '0.2');

// Empty query — all back to default.
await page.evaluate(() => _wfNodeSearchFilter(''));
await page.waitForTimeout(80);
const f2 = await page.evaluate(() => {
  const op = id => (document.querySelector(`.wf-node[data-node="${id}"]`) || {}).style?.opacity;
  return { fe: op('n-fe'), be: op('n-be'), db: op('n-db') };
});
check('empty query restores n-fe opacity to ""',  f2.fe === '');
check('empty query restores n-be opacity to ""',  f2.be === '');
check('empty query restores n-db opacity to ""',  f2.db === '');

// Inspector webhook URL.
await page.evaluate(() => {
  __wf.selectedNodeId = null;
  __wf._inspectorDirty = true;
  _wfRenderInspector({ force: true });
});
await page.waitForTimeout(120);

const wh = await page.evaluate(() => {
  const inp = document.getElementById('wfWebhookUrl');
  return { exists: !!inp, val: inp && inp.value };
});
check('inspector renders #wfWebhookUrl input', wh.exists);
check('webhook URL targets /api/workflows/webhook/<id>',
  /\/api\/workflows\/webhook\/wf-search-test/.test(wh.val || ''));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
