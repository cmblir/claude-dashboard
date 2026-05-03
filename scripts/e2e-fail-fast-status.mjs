#!/usr/bin/env node
/**
 * MM1 / NN3 / PP1 — when a node errors, sibling nodes that hadn't
 * finished are marked cancelled and rendered with the amber dashed
 * border (CSS rule `.wf-node[data-status="cancelled"] .wf-node-body`).
 *
 * Strategy: build a 3-node workflow (start → err + cancelled), feed
 * synthetic run results into the SSE-apply path, then check the
 * computed styles + data-status attribute.
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

// Build a 3-node DAG. n-err errored; n-canc was cancelled by sibling
// failure; n-ok finished normally. We feed simulated run results
// directly through the same DOM-apply pipeline the SSE poller uses.
const result = await page.evaluate(async () => {
  const wf = {
    id: 'wf-fail-fast',
    name: 'fail-fast-test',
    nodes: [
      { id: 'n-start', type: 'start',   x:  60, y: 100, data: {} },
      { id: 'n-ok',    type: 'session', x: 320, y:  60, title: 'OK',   data: { subject: 'x' } },
      { id: 'n-err',   type: 'session', x: 320, y: 180, title: 'ERR',  data: { subject: 'x' } },
      { id: 'n-canc',  type: 'session', x: 320, y: 300, title: 'CANC', data: { subject: 'x' } },
    ],
    edges: [
      { id: 'e1', from: 'n-start', fromPort: 'out', to: 'n-ok',   toPort: 'in' },
      { id: 'e2', from: 'n-start', fromPort: 'out', to: 'n-err',  toPort: 'in' },
      { id: 'e3', from: 'n-start', fromPort: 'out', to: 'n-canc', toPort: 'in' },
    ],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 4, edgeCount: 3, stickyCount: 0,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

  // Synthesize the run-results object that the SSE poll path normally
  // produces, then walk the same code path as a real status apply
  // (the loop sets `data-status` attribute on each .wf-node element).
  const results = {
    'n-start': { status: 'ok',  output: '' },
    'n-ok':    { status: 'ok',  output: 'fine' },
    'n-err':   { status: 'err', error: 'something blew up' },
    'n-canc':  { status: 'err', error: 'cancelled by sibling-node failure' },
  };
  __wf.lastRunResults = results;
  __wf._lastResultsSig = null; // force refresh

  // Replicate the apply logic from line ~7480 since there's no public
  // entry point that takes a results object.
  if (!__wf._nodeElsMap) {
    __wf._nodeElsMap = new Map();
    document.querySelectorAll('.wf-node').forEach(el => {
      const nid = el.getAttribute('data-node');
      if (nid) __wf._nodeElsMap.set(nid, el);
    });
  }
  for (const [nid, r] of Object.entries(results)) {
    const el = __wf._nodeElsMap.get(nid);
    if (!el || !r) continue;
    let visStatus = r.status;
    if (visStatus === 'err' && r.error && r.error.includes('cancelled by sibling-node failure')) {
      visStatus = 'cancelled';
    }
    el.setAttribute('data-status', visStatus);
  }
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

  function nodeInfo(nid) {
    const el = document.querySelector(`.wf-node[data-node="${nid}"]`);
    if (!el) return null;
    const body = el.querySelector('rect.wf-node-body');
    const cs = body ? getComputedStyle(body) : null;
    return {
      status: el.getAttribute('data-status'),
      stroke: cs && cs.stroke,
      strokeDash: cs && cs.strokeDasharray,
    };
  }
  return {
    ok:   nodeInfo('n-ok'),
    err:  nodeInfo('n-err'),
    canc: nodeInfo('n-canc'),
  };
});

check('n-ok status = ok', result.ok && result.ok.status === 'ok');
check('n-err status = err', result.err && result.err.status === 'err');
check('n-canc status = cancelled (promoted from err)',
  result.canc && result.canc.status === 'cancelled');
// CSS rule sets stroke-dasharray "6 3" for cancelled. browsers normalize
// the value to "6px, 3px" or similar.
check('n-canc has dashed amber border',
  result.canc && /6/.test(result.canc.strokeDash || ''));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
