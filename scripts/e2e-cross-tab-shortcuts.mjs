#!/usr/bin/env node
/**
 * QQ167 — verify QQ164 (chat Cmd+Shift+N) and QQ165 (workflow
 * Cmd+Shift+N) don't bleed into each other. Each handler must
 * gate on `state.view` so pressing the shortcut on the wrong tab
 * is a no-op.
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
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });

// Workflows tab: press Cmd+Shift+N → only _wfCreateNew should fire.
await page.evaluate(() => window.go('workflows'));
await page.waitForSelector('.wf-canvas, #wfCanvas');
await page.evaluate(() => {
  window.__cnWf = 0; window.__cnLc = 0;
  const oWf = window._wfCreateNew;
  const oLc = window._lcNewSession;
  window._wfCreateNew = () => { window.__cnWf++; };
  window._lcNewSession = (...a) => { window.__cnLc++; return oLc && oLc(...a); };
});
await page.evaluate(() => {
  document.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'N', code: 'KeyN', metaKey: true, shiftKey: true, bubbles: true,
  }));
});
await page.waitForTimeout(150);
const r1 = await page.evaluate(() => ({ wf: window.__cnWf, lc: window.__cnLc }));
check('on workflows: only _wfCreateNew fires', r1.wf === 1 && r1.lc === 0,
  JSON.stringify(r1));

// Chat tab: press Cmd+Shift+N → only _lcNewSession should fire.
await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput');
await page.evaluate(() => {
  window.__cnWf = 0; window.__cnLc = 0;
  document.getElementById('lcChatLog')?.click();
});
await page.evaluate(() => {
  document.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'N', code: 'KeyN', metaKey: true, shiftKey: true, bubbles: true,
  }));
});
await page.waitForTimeout(150);
const r2 = await page.evaluate(() => ({ wf: window.__cnWf, lc: window.__cnLc }));
check('on chat: only _lcNewSession fires', r2.wf === 0 && r2.lc === 1,
  JSON.stringify(r2));

// Overview tab: neither should fire.
await page.evaluate(() => window.go('overview'));
await page.waitForTimeout(300);
await page.evaluate(() => { window.__cnWf = 0; window.__cnLc = 0; });
await page.evaluate(() => {
  document.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'N', code: 'KeyN', metaKey: true, shiftKey: true, bubbles: true,
  }));
});
await page.waitForTimeout(150);
const r3 = await page.evaluate(() => ({ wf: window.__cnWf, lc: window.__cnLc }));
check('on overview: neither handler fires', r3.wf === 0 && r3.lc === 0,
  JSON.stringify(r3));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
