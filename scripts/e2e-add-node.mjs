#!/usr/bin/env node
/**
 * Add-node from palette flow:
 *
 * 1. Open editor with nid=null → draft with type=null is created.
 * 2. Click a palette button (e.g. "session" type).
 * 3. Set required fields (subject) and save.
 * 4. Assert nodes.length += 1 and the new node appears on canvas.
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

// Build empty workflow.
await page.evaluate(() => {
  const wf = {
    id: 'wf-add',
    name: 'add-test',
    nodes: [{ id: 'n-start', type: 'start', x: 60, y: 60, data: {} }],
    edges: [],
    viewport: { panX: 0, panY: 0, zoom: 1 },
  };
  __wf.workflows = (__wf.workflows || []).filter(w => w.id !== wf.id);
  __wf.workflows.unshift({ ...wf, nodeCount: 1, edgeCount: 0, stickyCount: 0,
                           tags: [], lastRuns: [], runningCount: 0, totalRuns: 0,
                           updatedAt: Date.now(), createdAt: Date.now() });
  __wf.current = wf;
  __wf._forceFullCanvasRebuild = true;
  if (typeof _wfRenderCanvasNow === 'function') _wfRenderCanvasNow();
  else _wfRenderCanvas();
});
await page.waitForTimeout(120);

const before = await page.evaluate(() => __wf.current.nodes.length);
check('initial: 1 node (start)', before === 1);

// Open editor in "new" mode.
await page.evaluate(() => _wfOpenNodeEditor(null));
await page.waitForTimeout(180);

const editorOk = await page.evaluate(() => !!document.querySelector('.feat-win.wf-node-editor, .feat-win'));
check('"new node" editor opened', editorOk);

// Pick a session type via the public _wfPickNodeType helper, which
// is what the palette buttons call.
const picked = await page.evaluate(() => {
  const wins = document.querySelectorAll('.feat-win');
  const win = wins[wins.length - 1];
  if (!win || !win.id) return false;
  if (typeof _wfPickNodeType !== 'function') return false;
  _wfPickNodeType(win.id, 'session');
  return win._wfDraft && win._wfDraft.type === 'session';
});
check('palette session-type picked', picked);

await page.waitForTimeout(150);

// Fill subject.
await page.evaluate(() => {
  const wins = document.querySelectorAll('.feat-win');
  const win = wins[wins.length - 1];
  const subj = Array.from(win.querySelectorAll('input, textarea'))
    .find(i => /subject|업무|주제/i.test(i.previousElementSibling && i.previousElementSibling.textContent || ''))
    || win.querySelector('input[type="text"]');
  if (subj) {
    subj.value = 'newly-added';
    subj.dispatchEvent(new Event('input', { bubbles: true }));
  }
});

// Save.
await page.evaluate(() => {
  const wins = document.querySelectorAll('.feat-win');
  const win = wins[wins.length - 1];
  const saveBtn = Array.from(win.querySelectorAll('button')).find(b =>
    /저장|Save/.test(b.textContent.trim()));
  if (saveBtn) saveBtn.click();
});
await page.waitForTimeout(180);

const after = await page.evaluate(() => ({
  count: __wf.current.nodes.length,
  types: __wf.current.nodes.map(n => n.type),
}));
check('node count incremented (1 → 2)', after.count === 2);
check('new node has type=session', after.types.includes('session'));

// Canvas DOM also has the new node element.
const inDom = await page.evaluate(() =>
  document.querySelectorAll('#wfNodes .wf-node').length);
check('canvas renders 2 nodes', inDom === 2);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
