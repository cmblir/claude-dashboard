#!/usr/bin/env node
/**
 * Chat connection gate — first visit must show the gate, Test Connection
 * must call /api/lazyclaw/chat/ping, and only after a successful probe
 * does the input area become live. Sending while the gate is up
 * re-opens it instead of producing the silent "중단됨" bubble that
 * users were hitting before this change.
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

// Wipe any prior chat data so we test the genuine first-visit path.
// The gate is skipped when the user has prior history (so existing
// users don't get re-gated mid-conversation), so we have to start
// from a clean slate.
await page.evaluate(() => {
  try {
    const keys = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && (k.startsWith('cc.lc.') || k.startsWith('cc.lazyclawChat.'))) keys.push(k);
    }
    keys.forEach(k => localStorage.removeItem(k));
  } catch (_) {}
});

await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatGate', { timeout: 8000 });

const gateVisible = await page.locator('#lcChatGate').isVisible();
check('gate visible on first visit', gateVisible);

const gateSelOk = await page.locator('#lcGateAssignee').count();
check('gate has model picker', gateSelOk === 1);

// Sending while the gate is up should re-show it (prevent stuck "중단됨").
// Manually trigger a send by calling the handler — the input area is
// covered by the gate overlay so the user couldn't reach it anyway, but
// _lcChatSend is callable from console / programmatic hooks.
await page.evaluate(() => {
  const ta = document.getElementById('lcChatInput');
  if (ta) ta.value = 'should be blocked';
  return _lcChatSend && _lcChatSend();
});
await page.waitForTimeout(150);
const stillGated = await page.locator('#lcChatGate').isVisible();
check('send before verify keeps gate open', stillGated);

// Stub the ping endpoint so the test runs without depending on a real
// provider. Forces ok:true → gate must close.
await page.route('**/api/lazyclaw/chat/ping', (route) => route.fulfill({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({ ok: true, provider: 'mock', model: 'echo', durationMs: 1, output: 'ok' }),
}));

await page.click('#lcGateTestBtn');
// The gate closes 400ms after the success status renders.
await page.waitForFunction(() => {
  const g = document.getElementById('lcChatGate');
  return g && g.style.display === 'none';
}, { timeout: 4000 });

const gateClosed = !(await page.locator('#lcChatGate').isVisible());
check('gate closes after successful ping', gateClosed);

const verified = await page.evaluate(() => localStorage.getItem('cc.lazyclawChat.verified'));
check('verified flag stored', !!verified, `verified=${verified}`);

// Failure path: clear verified, reload the page so the stub is the
// fresh route, and stub a failing ping. The gate must surface the
// server error instead of closing.
await page.unroute('**/api/lazyclaw/chat/ping').catch(() => {});
await page.route('**/api/lazyclaw/chat/ping', (route) => route.fulfill({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({ ok: false, error: 'simulated provider down' }),
}));
await page.evaluate(() => {
  try {
    const keys = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && (k.startsWith('cc.lc.') || k.startsWith('cc.lazyclawChat.'))) keys.push(k);
    }
    keys.forEach(k => localStorage.removeItem(k));
  } catch (_) {}
});
await page.reload({ waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatGate', { timeout: 8000 });
await page.click('#lcGateTestBtn');
await page.waitForFunction(() => {
  const s = document.getElementById('lcGateStatus');
  return s && (s.textContent || '').includes('❌');
}, { timeout: 8000 });
const stillVisible = await page.locator('#lcChatGate').isVisible();
const status = await page.locator('#lcGateStatus').textContent();
check('gate stays open on ping failure', stillVisible);
check('gate shows the server error', /simulated provider down/.test(status || ''),
  `status=${status}`);

await browser.close();
process.exit(process.exitCode || 0);
