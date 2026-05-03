#!/usr/bin/env node
/**
 * QQ132 — arrow-key nudging respects multi-selection. Pressing
 * → with two nodes selected moves BOTH by 10px; Shift+→ moves
 * BOTH by 1px (fine).
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
    id: 'wf-arrow-' + Date.now(),
    name: 'arrow',
    nodes: [
      { id: 'n-a', type: 'session', x: 100, y: 200, data: { subject: 'A', assignee: 'claude:opus' } },
      { id: 'n-b', type: 'session', x: 300, y: 200, data: { subject: 'B', assignee: 'claude:opus' } },
    ],
    edges: [],
  };
  _wfRenderCanvas();
  __wfMultiSelected.clear();
  __wfMultiSelected.add('n-a');
  __wfMultiSelected.add('n-b');
  __wf.selectedNodeId = null;
  _wfSyncMultiSelectClasses();
});

// 1. ArrowRight — both move +10
await page.keyboard.press('ArrowRight');
await page.waitForTimeout(100);
const after1 = await page.evaluate(() => __wf.current.nodes.map(n => ({id:n.id, x:n.x, y:n.y})));
const a1 = after1.find(n => n.id === 'n-a');
const b1 = after1.find(n => n.id === 'n-b');
check('ArrowRight nudges both by +10x',
  a1.x === 110 && b1.x === 310, `a=${a1.x},${a1.y} b=${b1.x},${b1.y}`);

// 2. Shift+ArrowDown — both move +1y
await page.keyboard.press('Shift+ArrowDown');
await page.waitForTimeout(100);
const after2 = await page.evaluate(() => __wf.current.nodes.map(n => ({id:n.id, x:n.x, y:n.y})));
const a2 = after2.find(n => n.id === 'n-a');
const b2 = after2.find(n => n.id === 'n-b');
check('Shift+ArrowDown nudges both by +1y',
  a2.x === 110 && a2.y === 201 && b2.x === 310 && b2.y === 201,
  `a=${a2.x},${a2.y} b=${b2.x},${b2.y}`);

// 3. Single-select fallback still works
await page.evaluate(() => {
  __wfMultiSelected.clear();
  __wf.selectedNodeId = 'n-a';
  _wfSyncMultiSelectClasses();
});
await page.keyboard.press('ArrowLeft');
await page.waitForTimeout(100);
const after3 = await page.evaluate(() => __wf.current.nodes.map(n => ({id:n.id, x:n.x, y:n.y})));
const a3 = after3.find(n => n.id === 'n-a');
const b3 = after3.find(n => n.id === 'n-b');
check('Single-select ArrowLeft moves only n-a',
  a3.x === 100 && b3.x === 310,
  `a=${a3.x} b=${b3.x}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
