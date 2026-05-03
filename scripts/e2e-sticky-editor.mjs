#!/usr/bin/env node
/**
 * QQ36 sticky inspector form — open the editor, change color +
 * dimensions, save, assert the canvas re-renders with the new
 * state via QQ108 snap-key digest.
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

// Build a workflow with a yellow sticky.
await page.evaluate(() => {
  const wf = {
    id: 'wf-sticky-edit',
    name: 'sticky-edit',
    nodes: [
      { id: 'n-stk', type: 'sticky', x: 80, y: 80,
        data: { text: 'old', color: 'yellow', width: 220, height: 140 } },
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
});
await page.waitForTimeout(120);

// Open the node editor for the sticky.
await page.evaluate(() => _wfOpenNodeEditor('n-stk'));
await page.waitForTimeout(150);

// Editor window = .feat-win — verify it has the sticky form
// (text textarea + color buttons + width/height number inputs).
const editorState = await page.evaluate(() => {
  const wins = document.querySelectorAll('.feat-win.wf-node-editor, .feat-win');
  const win = wins[wins.length - 1];
  if (!win) return null;
  const textArea = win.querySelector('textarea');
  const colorBtns = Array.from(win.querySelectorAll('button')).filter(b =>
    /^(yellow|blue|green|pink|gray)$/.test(b.textContent.trim()));
  const numbers = Array.from(win.querySelectorAll('input[type="number"]'));
  return {
    hasEditor: !!win,
    textLen: textArea && textArea.value.length,
    colorBtnCount: colorBtns.length,
    numberCount: numbers.length,
  };
});
check('sticky editor opens', editorState && editorState.hasEditor);
check('text area pre-filled with current value (3 chars: "old")',
  editorState && editorState.textLen === 3);
check('5 color buttons (yellow/blue/green/pink/gray)',
  editorState && editorState.colorBtnCount === 5);
check('2 number inputs (width + height)',
  editorState && editorState.numberCount === 2);

// Click the "blue" color button.
await page.evaluate(() => {
  const wins = document.querySelectorAll('.feat-win');
  const win = wins[wins.length - 1];
  const btn = Array.from(win.querySelectorAll('button')).find(b => b.textContent.trim() === 'blue');
  btn.click();
});
await page.waitForTimeout(80);

// Update width to 360, height to 200.
await page.evaluate(() => {
  const wins = document.querySelectorAll('.feat-win');
  const win = wins[wins.length - 1];
  const numbers = Array.from(win.querySelectorAll('input[type="number"]'));
  numbers[0].value = '360';
  numbers[0].dispatchEvent(new Event('input', { bubbles: true }));
  numbers[1].value = '200';
  numbers[1].dispatchEvent(new Event('input', { bubbles: true }));
});

// Update text via textarea.
await page.evaluate(() => {
  const wins = document.querySelectorAll('.feat-win');
  const win = wins[wins.length - 1];
  const ta = win.querySelector('textarea');
  ta.value = 'NEW NOTE';
  ta.dispatchEvent(new Event('input', { bubbles: true }));
});

// Save the editor (find the primary save button).
await page.evaluate(() => {
  const wins = document.querySelectorAll('.feat-win');
  const win = wins[wins.length - 1];
  const saveBtn = Array.from(win.querySelectorAll('button')).find(b =>
    /저장|Save|保存/.test(b.textContent.trim()));
  if (saveBtn) saveBtn.click();
});
await page.waitForTimeout(180);

// Assert n.data has updated values + canvas reflects them.
const after = await page.evaluate(() => {
  const n = __wf.current.nodes.find(x => x.id === 'n-stk');
  const rect = document.querySelector('.wf-node[data-node="n-stk"] rect:not(.wf-node-ring)');
  return {
    text: n.data.text,
    color: n.data.color,
    width: n.data.width,
    height: n.data.height,
    fill: rect && rect.getAttribute('fill'),
    rectW: rect && rect.getAttribute('width'),
  };
});
check('data.text updated to "NEW NOTE"', after.text === 'NEW NOTE');
check('data.color updated to "blue"',     after.color === 'blue');
check('data.width = 360',                  after.width === 360);
check('data.height = 200',                 after.height === 200);
check('canvas rect fill flips to #dbeafe', /dbeafe/i.test(after.fill || ''));
check('canvas rect width = "360"',         after.rectW === '360');

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
