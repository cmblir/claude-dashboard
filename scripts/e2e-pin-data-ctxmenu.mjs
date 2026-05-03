#!/usr/bin/env node
/**
 * QQ20 + QQ19 — Pin Data via the canvas context menu.
 *
 * 1. Build a workflow with one session node.
 * 2. Inject __wf.lastRunResults[nid].output so QQ19 surfaces
 *    "📌 마지막 출력 핀 설정" in the right-click menu.
 * 3. Right-click the node → click the menu item.
 * 4. Assert n.data.pinned + pinnedOutput are populated.
 * 5. Assert the canvas pin badge appears.
 * 6. Right-click again → click "📌 핀 해제".
 * 7. Assert pinned=false, pinnedOutput cleared, badge gone.
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

// Inject a workflow + a fake last-run result so QQ19 menu logic
// surfaces the "마지막 출력 핀 설정" item.
await page.evaluate(() => {
  const wf = {
    id: 'wf-pin-ctx',
    name: 'pin-ctx',
    nodes: [
      { id: 'n-start', type: 'start',   x: 60,  y: 80, data: {} },
      { id: 'n-s',     type: 'session', x: 320, y: 80, title: 'pin-target',
        data: { subject: 'x', assignee: 'claude:opus' } },
    ],
    edges: [{ id: 'e1', from: 'n-start', fromPort: 'out', to: 'n-s', toPort: 'in' }],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 2, edgeCount: 1, stickyCount: 0,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wf.lastRunResults = {
    'n-s': {
      status: 'ok',
      output: 'this output should become the pinned value',
      provider: 'claude-cli', model: 'opus', durationMs: 1234,
    },
  };
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
});
await page.waitForTimeout(150);

// Helper — open ctx menu by dispatching a real contextmenu event on the
// node element (the canvas listener in app.js calls
// _wfShowNodeContextMenu internally) and click an item by label.
async function openCtxAndClick(label) {
  const ok = await page.evaluate((targetLabel) => {
    const el = document.querySelector('.wf-node[data-node="n-s"]');
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
    el.dispatchEvent(new MouseEvent('contextmenu', {
      bubbles: true, cancelable: true, view: window,
      clientX: cx, clientY: cy, button: 2,
    }));
    const menu = document.getElementById('wfNodeCtxMenu');
    if (!menu) return false;
    const rows = Array.from(menu.children);
    const row = rows.find(r => (r.textContent || '').includes(targetLabel));
    if (!row) return false;
    row.click();
    return true;
  }, label);
  await page.waitForTimeout(120);
  return ok;
}

// Step 1 — pin the last output.
const pinClicked = await openCtxAndClick('마지막 출력 핀 설정');
check('"마지막 출력 핀 설정" item clicked', pinClicked);

let state = await page.evaluate(() => {
  const n = __wf.current.nodes.find(x => x.id === 'n-s');
  const badge = document.querySelector('.wf-node[data-node="n-s"] .wf-node-pin-badge');
  return {
    pinned: !!(n.data && n.data.pinned),
    pinnedOutput: n.data && n.data.pinnedOutput,
    hasBadge: !!badge,
  };
});
check('node.data.pinned == true', state.pinned === true);
check('pinnedOutput captured from lastRunResults',
  state.pinnedOutput === 'this output should become the pinned value');
check('canvas pin badge rendered', state.hasBadge === true);

// Step 2 — unpin.
const unpinClicked = await openCtxAndClick('핀 해제');
check('"핀 해제" item clicked', unpinClicked);

state = await page.evaluate(() => {
  const n = __wf.current.nodes.find(x => x.id === 'n-s');
  const badge = document.querySelector('.wf-node[data-node="n-s"] .wf-node-pin-badge');
  return {
    pinned: !!(n.data && n.data.pinned),
    pinnedOutput: n.data && n.data.pinnedOutput,
    hasBadge: !!badge,
  };
});
check('node.data.pinned == false after unpin', state.pinned === false);
check('pinnedOutput cleared',                state.pinnedOutput === '');
check('canvas pin badge removed',            state.hasBadge === false);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
