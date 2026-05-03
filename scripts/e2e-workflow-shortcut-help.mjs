#!/usr/bin/env node
/**
 * QQ130 — verify the workflow shortcut help (`?` key) renders the
 * full grid of shortcuts including the recent additions
 * (Ctrl+X cut). Esc closes it; pressing `?` again toggles it off.
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
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('workflows'));
await page.waitForSelector('.wf-canvas, #wfCanvas', { timeout: 8000 });
// Make sure the workflow keydown listener is bound by giving the canvas focus.
await page.evaluate(() => {
  const cv = document.querySelector('.wf-canvas, #wfCanvas');
  if (cv) cv.focus();
});

// Open the help via the global function — '?' keystroke needs the
// canvas to have focus and varies by browser shift state, so the
// public API is more deterministic for an e2e.
await page.evaluate(() => _wfShowShortcutHelp());
await page.waitForSelector('#wfShortcutModal', { timeout: 3000 });

const helpHTML = await page.evaluate(() => {
  const m = document.getElementById('wfShortcutModal');
  return m ? m.innerHTML : '';
});

const expected = ['Ctrl+C', 'Ctrl+X', 'Ctrl+V', 'Ctrl+D', 'Ctrl+A',
                  'Ctrl+Z', 'Ctrl+S', 'Ctrl+Enter', 'Esc'];
for (const tok of expected) {
  check(`help mentions ${tok}`, helpHTML.includes(tok));
}

// Press Esc to close.
await page.keyboard.press('Escape');
await page.waitForTimeout(150);
const closed = await page.evaluate(() => !document.getElementById('wfShortcutModal'));
check('Esc closes the help modal', closed);

// Re-open + toggle off via the same call (the function self-closes).
await page.evaluate(() => _wfShowShortcutHelp());
await page.waitForSelector('#wfShortcutModal');
await page.evaluate(() => _wfShowShortcutHelp());
const toggledOff = await page.evaluate(() => !document.getElementById('wfShortcutModal'));
check('_wfShowShortcutHelp() toggles closed when called twice', toggledOff);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
