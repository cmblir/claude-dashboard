#!/usr/bin/env node
/**
 * LL14 + QQ19 — node right-click context menu surfaces:
 *   ✏️ 편집 / 📑 복제 / ⏸ 비활성화 / ▶ 단독 실행 / 📋 출력 복사 / 📌 핀 / 🗑 삭제
 *
 * Verifies:
 *   1. dispatching contextmenu on a node opens #wfNodeCtxMenu.
 *   2. menu items match the expected label set for a session node
 *      with a recorded last-run output (so all conditional items
 *      surface).
 *   3. clicking 📑 (duplicate) appends a new node clone.
 *   4. clicking outside closes the menu (#wfNodeCtxMenu removed).
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
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1200 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('#wfCanvasHost', { timeout: 8000 });

await page.evaluate(() => {
  const wf = {
    id: 'wf-ctx',
    name: 'ctx-test',
    nodes: [
      { id: 'n-s', type: 'session', x: 200, y: 200, title: 'ctx-target',
        data: { subject: 'x', assignee: 'claude:opus' } },
    ],
    edges: [],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 1, edgeCount: 0, stickyCount: 0,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wf.lastRunResults = {
    'n-s': { status: 'ok', output: 'last output captured' },
  };
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
});
await page.waitForTimeout(120);

// Open ctx menu via dispatching contextmenu on the node element.
const labels = await page.evaluate(() => {
  const el = document.querySelector('.wf-node[data-node="n-s"]');
  if (!el) return null;
  const r = el.getBoundingClientRect();
  el.dispatchEvent(new MouseEvent('contextmenu', {
    bubbles: true, cancelable: true, view: window,
    clientX: r.x + r.width / 2, clientY: r.y + r.height / 2, button: 2,
  }));
  const menu = document.getElementById('wfNodeCtxMenu');
  if (!menu) return null;
  return Array.from(menu.children).map(c => c.textContent.trim()).filter(Boolean);
});
check('context menu opens (#wfNodeCtxMenu present)', Array.isArray(labels));
const want = ['편집', '복제', '비활성화', '단독 실행', '출력 복사', '마지막 출력 핀 설정', '삭제'];
const all = labels && labels.join(' ');
for (const w of want) {
  check(`menu has "${w}"`, all && all.includes(w));
}

// Click 복제.
const beforeDup = await page.evaluate(() => __wf.current.nodes.length);
await page.evaluate(() => {
  const menu = document.getElementById('wfNodeCtxMenu');
  const row = Array.from(menu.children).find(r => /복제|Duplicate/.test(r.textContent || ''));
  row.click();
});
await page.waitForTimeout(150);
const afterDup = await page.evaluate(() => __wf.current.nodes.length);
check('"복제" appends a new node', afterDup === beforeDup + 1);

// Confirm menu auto-closed.
const closed = await page.evaluate(() => !document.getElementById('wfNodeCtxMenu'));
check('menu closes after click', closed);

// Re-open and click outside via mousedown on body.
await page.evaluate(() => {
  const el = document.querySelector('.wf-node[data-node="n-s"]');
  const r = el.getBoundingClientRect();
  el.dispatchEvent(new MouseEvent('contextmenu', {
    bubbles: true, cancelable: true, view: window,
    clientX: r.x + 5, clientY: r.y + 5, button: 2,
  }));
});
await page.waitForTimeout(80);
const open = await page.evaluate(() => !!document.getElementById('wfNodeCtxMenu'));
check('re-opened menu before outside-click', open);

// The outside-click closer is registered with `setTimeout(() => addEventListener
// ('mousedown', closer, { once: true }), 0)`. Wait one tick, then click body.
await page.waitForTimeout(20);
await page.evaluate(() => {
  document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
});
await page.waitForTimeout(80);
const outClosed = await page.evaluate(() => !document.getElementById('wfNodeCtxMenu'));
check('outside mousedown closes the menu', outClosed);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
