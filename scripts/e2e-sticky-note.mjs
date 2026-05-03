#!/usr/bin/env node
/**
 * QQ36 / QQ108 — sticky note canvas rendering + state propagation.
 *
 * 1. Inject a workflow with one yellow sticky and verify the SVG
 *    renders the expected color, dimensions, and markdown text.
 * 2. Mutate `data.color` to "blue" and re-render — assert the rect
 *    fill colour changes (snap-key digest covers sticky state per
 *    QQ108 so the diff renderer must rebuild the node).
 * 3. Mutate `data.text` and assert the rendered foreignObject
 *    content updates.
 * 4. Verify the sticky has NO ports (portIn=false, portOut=false).
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

// Step 1: yellow sticky.
const initial = await page.evaluate(async () => {
  const wf = {
    id: 'wf-sticky',
    name: 'sticky-test',
    nodes: [
      { id: 'n-stk', type: 'sticky', x: 80, y: 80,
        data: { text: '## hello\nworld', color: 'yellow', width: 240, height: 140 } },
    ],
    edges: [],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 0, edgeCount: 0, stickyCount: 1,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const g = document.querySelector('.wf-node[data-node="n-stk"]');
  if (!g) return null;
  const rect = g.querySelector('rect:not(.wf-node-ring)');
  const fo = g.querySelector('foreignObject');
  return {
    fill: rect && rect.getAttribute('fill'),
    width: rect && rect.getAttribute('width'),
    height: rect && rect.getAttribute('height'),
    foText: fo && fo.textContent,
    portCount: g.querySelectorAll('.wf-port').length,
  };
});

check('sticky renders yellow fill', initial && /fef3c7/i.test(initial.fill || ''));
check('sticky width 240', initial && initial.width === '240');
check('sticky height 140', initial && initial.height === '140');
check('sticky text rendered (markdown header)',
  initial && /hello/.test(initial.foText || '') && /world/.test(initial.foText || ''));
check('sticky has NO ports', initial && initial.portCount === 0);

// Step 2: mutate color to blue.
const afterBlue = await page.evaluate(async () => {
  __wf.current.nodes[0].data.color = 'blue';
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const rect = document.querySelector('.wf-node[data-node="n-stk"] rect:not(.wf-node-ring)');
  return rect && rect.getAttribute('fill');
});
check('color change → fill #dbeafe (blue)', /dbeafe/i.test(afterBlue || ''));

// Step 3: mutate text.
const afterText = await page.evaluate(async () => {
  __wf.current.nodes[0].data.text = '## CHANGED\nnew content';
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const fo = document.querySelector('.wf-node[data-node="n-stk"] foreignObject');
  return fo && fo.textContent;
});
check('text change reflected via QQ108 snap-key digest',
  /CHANGED/.test(afterText || '') && /new content/.test(afterText || ''));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
