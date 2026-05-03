#!/usr/bin/env node
/**
 * QQ165 — Cmd/Ctrl+Shift+N creates a new workflow on the workflows
 * tab. Plain Cmd+N still opens the new-node editor (LL16). The
 * shortcut help modal (QQ130) lists both.
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

// Stub _wfCreateNew so we don't have to drive promptModal in headless;
// we only care that the shortcut WIRES UP to the function.
await page.evaluate(() => {
  window.__createNewCalls = 0;
  const orig = window._wfCreateNew;
  window._wfCreateNew = () => { window.__createNewCalls++; return orig && orig(); };
});

// Synthesise the keydown directly on document so we don't depend on
// where focus happens to land in this headless run.
await page.evaluate(() => {
  const ev = new KeyboardEvent('keydown', {
    key: 'N', code: 'KeyN', metaKey: true, shiftKey: true, bubbles: true,
  });
  document.dispatchEvent(ev);
});
await page.waitForTimeout(150);

// promptModal may now be open; press Esc to close so it doesn't pollute later tests.
await page.keyboard.press('Escape');
await page.waitForTimeout(100);

const callCount = await page.evaluate(() => window.__createNewCalls);
check('Cmd+Shift+N invoked _wfCreateNew', callCount >= 1, `calls=${callCount}`);

// The shortcut help modal lists the new shortcut.
await page.evaluate(() => _wfShowShortcutHelp());
await page.waitForSelector('#wfShortcutModal', { timeout: 3000 });
const helpHTML = await page.evaluate(() => document.getElementById('wfShortcutModal').innerHTML);
check('shortcut help mentions Ctrl+Shift+N', /Ctrl\+Shift\+N/.test(helpHTML));
check('shortcut help mentions Ctrl+N', /Ctrl\+N\b/.test(helpHTML));

// Esc closes the modal cleanly so the test ends in a known state.
await page.keyboard.press('Escape');

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
