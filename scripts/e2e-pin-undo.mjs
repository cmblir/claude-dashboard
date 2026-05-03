#!/usr/bin/env node
/**
 * QQ160 — Pin Data toggle is now undoable. Same class as QQ159
 * (D toggle): _wfTogglePin and _wfToggleNodeDisabled (ctx-menu
 * paths) used to mutate without pushing an undo entry, so users
 * lost the ability to revert an accidental pin.
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

// Seed: one session node + a faked lastRunResults entry so _wfTogglePin
// has a non-empty output to pin.
await page.evaluate(() => {
  __wf.current = {
    id: 'wf-pin-undo-' + Date.now(),
    name: 'pin-undo',
    nodes: [
      { id: 'n-a', type: 'session', x: 100, y: 200,
        data: { subject: 'A', assignee: 'claude:opus' } },
    ],
    edges: [],
  };
  __wf._undoStack = [];
  __wf.lastRunResults = { 'n-a': { status: 'ok', output: 'frozen-output' } };
  _wfRenderCanvas();
});

// Pin the node.
await page.evaluate(() => _wfTogglePin('n-a', true));
await page.waitForTimeout(120);

const pinned = await page.evaluate(() => {
  const n = __wf.current.nodes[0];
  return { pinned: !!n.data.pinned, output: n.data.pinnedOutput, undoLen: __wf._undoStack.length };
});
check('pin sets data.pinned + pinnedOutput', pinned.pinned === true && pinned.output === 'frozen-output');
check('pin pushes one undo entry', pinned.undoLen === 1, `undoLen=${pinned.undoLen}`);

// Cmd+Z reverts the pin.
await page.keyboard.press('Meta+KeyZ');
await page.waitForTimeout(120);
const undone = await page.evaluate(() => {
  const n = __wf.current.nodes[0];
  return { pinned: !!n.data.pinned, output: n.data.pinnedOutput || '' };
});
check('Cmd+Z removes the pin', undone.pinned === false && !undone.output);

// Pin again, then unpin, then Cmd+Z reverts the unpin.
await page.evaluate(() => _wfTogglePin('n-a', true));
await page.evaluate(() => _wfTogglePin('n-a', false));
await page.waitForTimeout(120);
await page.keyboard.press('Meta+KeyZ');
await page.waitForTimeout(120);
const unpinUndone = await page.evaluate(() => {
  const n = __wf.current.nodes[0];
  return { pinned: !!n.data.pinned, output: n.data.pinnedOutput || '' };
});
check('Cmd+Z restores the pinned state after an unpin',
  unpinUndone.pinned === true && unpinUndone.output === 'frozen-output',
  JSON.stringify(unpinUndone));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
