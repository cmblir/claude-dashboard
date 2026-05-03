#!/usr/bin/env node
/**
 * Node editor save flow — open the editor for a session node,
 * change subject + assignee fields, click save, assert
 * `__wf.current.nodes[…].data` reflects the new values and the
 * canvas updates the visible @assignee label.
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
    id: 'wf-edit',
    name: 'edit-test',
    nodes: [
      { id: 'n-s', type: 'session', x: 200, y: 200,
        title: 'orig-title',
        data: { subject: 'orig-subject', assignee: 'claude:opus', inputsMode: 'concat' } },
    ],
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

// Initial canvas: assignee label shows "@claude:opus".
const initialAssigneeText = await page.evaluate(() => {
  const sub = document.querySelector('.wf-node[data-node="n-s"] .wf-node-sub');
  return sub && sub.textContent;
});
check('canvas shows initial @claude:opus assignee',
  /claude:opus/.test(initialAssigneeText || ''));

// Open editor.
await page.evaluate(() => _wfOpenNodeEditor('n-s'));
await page.waitForTimeout(150);

// Editor present + form prefilled.
const editor = await page.evaluate(() => {
  const wins = document.querySelectorAll('.feat-win.wf-node-editor, .feat-win');
  const win = wins[wins.length - 1];
  if (!win) return null;
  const inputs = Array.from(win.querySelectorAll('input, textarea, select'));
  const titleInp = inputs.find(i => i.value === 'orig-title');
  const subjInp  = inputs.find(i => i.value === 'orig-subject');
  return {
    hasEditor: !!win,
    foundTitle:   !!titleInp,
    foundSubject: !!subjInp,
  };
});
check('editor opens', editor && editor.hasEditor);
check('title input prefilled with current value',   editor && editor.foundTitle);
check('subject input prefilled with current value', editor && editor.foundSubject);

// Change title to "renamed" + subject to "new subject".
await page.evaluate(() => {
  const wins = document.querySelectorAll('.feat-win');
  const win = wins[wins.length - 1];
  const inputs = Array.from(win.querySelectorAll('input, textarea, select'));
  const titleInp = inputs.find(i => i.value === 'orig-title');
  const subjInp  = inputs.find(i => i.value === 'orig-subject');
  if (titleInp) {
    titleInp.value = 'renamed';
    titleInp.dispatchEvent(new Event('input', { bubbles: true }));
  }
  if (subjInp) {
    subjInp.value = 'new subject';
    subjInp.dispatchEvent(new Event('input', { bubbles: true }));
  }
});

// Click save.
await page.evaluate(() => {
  const wins = document.querySelectorAll('.feat-win');
  const win = wins[wins.length - 1];
  const saveBtn = Array.from(win.querySelectorAll('button')).find(b =>
    /저장|Save/.test(b.textContent.trim()));
  if (saveBtn) saveBtn.click();
});
await page.waitForTimeout(180);

// Assert state updated.
const updated = await page.evaluate(() => {
  const n = __wf.current.nodes.find(x => x.id === 'n-s');
  const titleEl = document.querySelector('.wf-node[data-node="n-s"] .wf-node-title');
  return {
    nodeTitle: n && n.title,
    nodeSubject: n && n.data && n.data.subject,
    canvasTitle: titleEl && titleEl.textContent,
  };
});
check('node.title updated to "renamed"',     updated.nodeTitle === 'renamed');
check('node.data.subject updated',           updated.nodeSubject === 'new subject');
check('canvas title text reflects rename',   /renamed/.test(updated.canvasTitle || ''));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
