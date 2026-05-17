#!/usr/bin/env node
/**
 * QQ167 — verify the workflow Cmd+Shift+N shortcut (QQ165) is gated on
 * `state.view`. The handler must only fire on the workflows tab; pressing
 * the shortcut on any other tab is a no-op.
 */
import { chromium } from 'playwright';

const PORT = process.env.PORT || '19500';
const URL  = `http://127.0.0.1:${PORT}/`;

function check(label, ok, detail) {
  const tag = ok ? '\x1b[32m✅\x1b[0m' : '\x1b[31m❌\x1b[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) process.exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });

// Workflows tab: press Cmd+Shift+N → _wfCreateNew should fire once.
await page.evaluate(() => window.go('workflows'));
await page.waitForSelector('.wf-canvas, #wfCanvas');
await page.evaluate(() => {
  window.__cnWf = 0;
  window._wfCreateNew = () => { window.__cnWf++; };
});
await page.evaluate(() => {
  document.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'N', code: 'KeyN', metaKey: true, shiftKey: true, bubbles: true,
  }));
});
await page.waitForTimeout(150);
const r1 = await page.evaluate(() => ({ wf: window.__cnWf }));
check('on workflows: _wfCreateNew fires once', r1.wf === 1,
  JSON.stringify(r1));

// Overview tab: the workflow handler must NOT fire (gated on state.view).
await page.evaluate(() => window.go('overview'));
await page.waitForTimeout(300);
await page.evaluate(() => { window.__cnWf = 0; });
await page.evaluate(() => {
  document.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'N', code: 'KeyN', metaKey: true, shiftKey: true, bubbles: true,
  }));
});
await page.waitForTimeout(150);
const r2 = await page.evaluate(() => ({ wf: window.__cnWf }));
check('on overview: _wfCreateNew does not fire', r2.wf === 0,
  JSON.stringify(r2));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
