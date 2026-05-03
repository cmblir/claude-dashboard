#!/usr/bin/env node
/**
 * QQ133 — `D` keystroke flips disabled on every multi-selected node
 * to the same new state (so users get a deterministic batch-disable /
 * batch-enable instead of toggling each individually).
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
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('.wf-canvas, #wfCanvas', { timeout: 8000 });

await page.evaluate(() => {
  __wf.current = {
    id: 'wf-disable-' + Date.now(),
    name: 'disable',
    nodes: [
      { id: 'n-a', type: 'session', x: 100, y: 200, data: { subject: 'A', assignee: 'claude:opus', disabled: false } },
      { id: 'n-b', type: 'session', x: 300, y: 200, data: { subject: 'B', assignee: 'claude:opus', disabled: true  } },
      { id: 'n-c', type: 'session', x: 500, y: 200, data: { subject: 'C', assignee: 'claude:opus', disabled: false } },
    ],
    edges: [],
  };
  _wfRenderCanvas();
  __wfMultiSelected.clear();
  __wfMultiSelected.add('n-a');
  __wfMultiSelected.add('n-b');
  __wfMultiSelected.add('n-c');
  __wf.selectedNodeId = null;
  _wfSyncMultiSelectClasses();
});

// First press: n-a is currently enabled, so the new state is "disabled
// = true" → all 3 should end up disabled.
await page.keyboard.press('KeyD');
await page.waitForTimeout(120);

const after1 = await page.evaluate(() =>
  __wf.current.nodes.map(n => ({ id: n.id, disabled: !!(n.data && n.data.disabled) }))
);
check('first D — all 3 selected nodes are disabled',
  after1.every(n => n.disabled === true),
  JSON.stringify(after1));

// Second press: now all are disabled → flip everyone to enabled.
await page.keyboard.press('KeyD');
await page.waitForTimeout(120);

const after2 = await page.evaluate(() =>
  __wf.current.nodes.map(n => ({ id: n.id, disabled: !!(n.data && n.data.disabled) }))
);
check('second D — all 3 selected nodes are enabled',
  after2.every(n => n.disabled === false),
  JSON.stringify(after2));

// Single-select fallback: select only n-b, press D, only n-b flips.
await page.evaluate(() => {
  __wfMultiSelected.clear();
  __wf.selectedNodeId = 'n-b';
  _wfSyncMultiSelectClasses();
});
await page.keyboard.press('KeyD');
await page.waitForTimeout(120);

const after3 = await page.evaluate(() =>
  __wf.current.nodes.map(n => ({ id: n.id, disabled: !!(n.data && n.data.disabled) }))
);
const aOnly = after3.find(n => n.id === 'n-a').disabled;
const bOnly = after3.find(n => n.id === 'n-b').disabled;
const cOnly = after3.find(n => n.id === 'n-c').disabled;
check('single-select D toggles only n-b',
  aOnly === false && bOnly === true && cOnly === false,
  `a=${aOnly} b=${bOnly} c=${cOnly}`);

// QQ159 — D toggle is undoable. Multi-toggle pushes a single undo
// entry so Cmd+Z restores the original disabled state in one keystroke.
await page.evaluate(() => {
  __wf.current = {
    id: 'wf-disable-undo-' + Date.now(),
    name: 'disable-undo',
    nodes: [
      { id: 'n-x', type: 'session', x: 100, y: 200, data: { subject: 'X', assignee: 'claude:opus', disabled: false } },
      { id: 'n-y', type: 'session', x: 300, y: 200, data: { subject: 'Y', assignee: 'claude:opus', disabled: false } },
    ],
    edges: [],
  };
  __wf._undoStack = [];
  _wfRenderCanvas();
  __wfMultiSelected.clear();
  __wfMultiSelected.add('n-x');
  __wfMultiSelected.add('n-y');
  __wf.selectedNodeId = null;
  _wfSyncMultiSelectClasses();
});

await page.keyboard.press('KeyD');
await page.waitForTimeout(120);
const after = await page.evaluate(() => __wf.current.nodes.map(n => !!(n.data && n.data.disabled)));
check('D disables both nodes', after.every(d => d === true), JSON.stringify(after));

await page.keyboard.press('Meta+KeyZ');
await page.waitForTimeout(120);
const undone = await page.evaluate(() => __wf.current.nodes.map(n => !!(n.data && n.data.disabled)));
check('Cmd+Z reverts both nodes back to enabled in one step',
  undone.every(d => d === false), JSON.stringify(undone));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
