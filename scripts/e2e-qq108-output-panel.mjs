#!/usr/bin/env node
/**
 * QQ108 — verify the inspector output preview panel + full-output modal.
 *
 * 1. Open workflow tab; inject a workflow with one session node.
 * 2. Inject __wf.lastRunResults[nid] with output text.
 * 3. Select the node so the inspector renders the per-node block.
 * 4. Assert the <details> panel has been added with the preview text
 *    and a 📋 copy button.
 * 5. Click '⬆ 전체 보기' (only present when overflow) and assert the
 *    full-output modal is rendered.
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
const ctx = await browser.newContext();
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('#wfCanvasHost', { timeout: 8000 });

// Setup: workflow with a session node + a fake lastRunResults entry.
// Use a long output to trigger the overflow path (>600 chars).
const setupResult = await page.evaluate(async () => {
  const longOut = 'A'.repeat(800) + '\nend.';
  const wf = {
    id: 'wf-qq108-out',
    name: 'qq108-out',
    nodes: [
      { id: 'n-start', type: 'start', x: 50, y: 80, data: {} },
      { id: 'n-s', type: 'session', x: 320, y: 80, title: 'output-test',
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
      output: longOut,
      provider: 'claude-cli',
      model: 'opus',
      durationMs: 1234,
      tokensIn: 100,
      tokensOut: 200,
    },
  };
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();

  // Select the node so the inspector renders its per-node block.
  __wf.selectedNodeId = 'n-s';
  __wf._inspectorDirty = true;
  _wfRenderInspector({ force: true });

  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

  const insp = document.getElementById('wfInspectorBody');
  return {
    inspectorPresent: !!insp,
    hasDetails: !!(insp && insp.querySelector('details')),
    hasViewFull: !!(insp && Array.from(insp.querySelectorAll('button'))
      .some(b => b.textContent.includes('전체 보기'))),
    longOutLen: longOut.length,
  };
});

check('inspector body present', setupResult.inspectorPresent);
check('output <details> panel rendered', setupResult.hasDetails);
check('전체 보기 button shown for overflow', setupResult.hasViewFull);

// Click the 전체 보기 button and verify modal opens.
const modalResult = await page.evaluate(async () => {
  const insp = document.getElementById('wfInspectorBody');
  const btn = Array.from(insp.querySelectorAll('button')).find(b => b.textContent.includes('전체 보기'));
  if (!btn) return { clicked: false };
  btn.click();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  // Modal is appended to <body> with z-index:99999 inline style.
  const modals = Array.from(document.querySelectorAll('[style*="z-index:99999"]'));
  const modal = modals[modals.length - 1];
  if (!modal) return { clicked: true, modalRendered: false };
  const pre = modal.querySelector('pre');
  return {
    clicked: true,
    modalRendered: true,
    preLen: pre ? pre.textContent.length : 0,
  };
});

check('full-output modal opens after click', modalResult.modalRendered);
check('modal shows full output (no truncation)', modalResult.preLen >= setupResult.longOutLen);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
