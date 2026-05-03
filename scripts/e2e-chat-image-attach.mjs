#!/usr/bin/env node
/**
 * Chat image attach end-to-end (QQ39 paste/drop, QQ61 picker,
 * QQ92 counter, QQ93 clear-all).
 *
 * 1. Open lazyclaw chat tab.
 * 2. Synthesize a 1×1 PNG and call _lcAttachFiles([file]) — the
 *    same path the picker uses.
 * 3. Verify textarea contains a base64 data:image/png reference.
 * 4. Verify the 📷 N counter shows 1.
 * 5. Click the counter chip → assert the image markdown is gone
 *    and the counter is hidden.
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
const ctx = await browser.newContext();
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));
page.on('console', msg => { if (msg.type() === 'error') console.error('[console.error]', msg.text()); });

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

// Make sure a session exists (or create one).
await page.evaluate(() => {
  if (!_lcCurrentId() || !_lcGetSessions().find(s => s.id === _lcCurrentId())) {
    _lcNewSession('claude:opus');
  }
});

// Step 1: synthesize a 1×1 png via Blob + File and run the
// picker's _lcAttachFiles handler.
const attachResult = await page.evaluate(async () => {
  // 1×1 transparent png (smallest valid PNG)
  const b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  const blob = new Blob([arr], { type: 'image/png' });
  const file = new File([blob], 'pixel.png', { type: 'image/png' });
  await window._lcAttachFiles([file]);
  // Wait one tick for the input event + render.
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const ta = document.getElementById('lcChatInput');
  const cnt = document.getElementById('lcInputImgCount');
  const wrap = document.getElementById('lcInputImgs');
  return {
    hasDataUrl: /!\[[^\]]*\]\(data:image\/png;base64,/.test(ta.value),
    imgCountText: cnt && cnt.textContent,
    imgWrapVisible: wrap && wrap.style.display !== 'none',
    taLen: ta.value.length,
  };
});

check('textarea contains base64 image markdown', attachResult.hasDataUrl);
check('image counter shows 1', attachResult.imgCountText === '1');
check('image counter visible',  attachResult.imgWrapVisible === true);

// Step 2: click the counter to clear.
await page.evaluate(() => {
  const wrap = document.getElementById('lcInputImgs');
  if (wrap) wrap.click();
});
await page.waitForTimeout(150);

const clearResult = await page.evaluate(() => {
  const ta = document.getElementById('lcChatInput');
  const cnt = document.getElementById('lcInputImgCount');
  const wrap = document.getElementById('lcInputImgs');
  return {
    stillHasDataUrl: /!\[[^\]]*\]\(data:image\/png;base64,/.test(ta.value),
    imgCountText: cnt && cnt.textContent,
    imgWrapHidden: wrap && wrap.style.display === 'none',
  };
});

check('image markdown removed after clear', clearResult.stillHasDataUrl === false);
check('image counter back to 0',           clearResult.imgCountText === '0');
check('image counter hidden after clear',  clearResult.imgWrapHidden === true);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
