#!/usr/bin/env node
/**
 * QQ168 — Cmd/Ctrl+Shift+E exports the current workflow as JSON.
 * Mirrors the toolbar 📦 export button. Parallels the QQ166 chat
 * export shortcut.
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

// Stub _wfExport so the test doesn't actually trigger a download.
await page.evaluate(() => {
  window.__exportCalls = 0;
  window._wfExport = () => { window.__exportCalls++; };
});

// Cmd+Shift+E should fire _wfExport.
await page.evaluate(() => {
  document.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'E', code: 'KeyE', metaKey: true, shiftKey: true, bubbles: true,
  }));
});
await page.waitForTimeout(150);
const callCount = await page.evaluate(() => window.__exportCalls);
check('Cmd+Shift+E invokes _wfExport', callCount === 1, `calls=${callCount}`);

// Shortcut help modal lists the new shortcut.
await page.evaluate(() => _wfShowShortcutHelp());
await page.waitForSelector('#wfShortcutModal', { timeout: 3000 });
const helpHTML = await page.evaluate(() => document.getElementById('wfShortcutModal').innerHTML);
check('shortcut help mentions Ctrl+Shift+E', /Ctrl\+Shift\+E/.test(helpHTML));

// Esc closes
await page.keyboard.press('Escape');

// Confirm Cmd+Shift+E does NOT fire on a non-workflow tab.
await page.evaluate(() => window.go('overview'));
await page.waitForTimeout(300);
await page.evaluate(() => { window.__exportCalls = 0; });
await page.evaluate(() => {
  document.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'E', code: 'KeyE', metaKey: true, shiftKey: true, bubbles: true,
  }));
});
await page.waitForTimeout(150);
const offTabCount = await page.evaluate(() => window.__exportCalls);
check('Cmd+Shift+E suppressed on non-workflow tabs',
  offTabCount === 0, `calls=${offTabCount}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
