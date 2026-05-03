#!/usr/bin/env node
/**
 * QQ203 — `/usage [N]` aggregates cost across all sessions via
 * /api/cost-timeline/summary?days=N. Default 7-day window; integer arg
 * 1-365. Renders total USD + call count + top-3 models + per-day list.
 * Out-of-range emits a warn toast and does not call the endpoint.
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
await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

async function slash(line) {
  await page.evaluate((l) => _lcChatSlashCommand(l), line);
  await page.waitForTimeout(250);
}

// Track requests so we can prove the endpoint is hit (and only when valid).
const requested = [];
page.on('request', req => {
  const u = req.url();
  if (u.includes('/api/cost-timeline/summary')) requested.push(u);
});

// 1. Default window = 7 days
await slash('/usage');
const default7 = requested.some(u => /[?&]days=7\b/.test(u));
check('/usage hits /api/cost-timeline/summary?days=7 by default', default7,
  JSON.stringify(requested.slice(-2)));

const fullText = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/usage renders header with day-window',
  /사용량.*7d/.test(fullText));
check('/usage renders total USD line',
  /총 비용.*\$/i.test(fullText));
check('/usage renders call count line',
  /호출 수/.test(fullText));

// 2. Explicit N — 30 days
const before30 = requested.length;
await slash('/usage 30');
const got30 = requested.slice(before30).some(u => /[?&]days=30\b/.test(u));
check('/usage 30 hits days=30', got30,
  JSON.stringify(requested.slice(before30)));

// 3. Out-of-range — toasts and does NOT hit the endpoint
const beforeOob = requested.length;
await page.evaluate(() => {
  window.__usageToasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__usageToasts.push({m, k}); return orig && orig(m, k); };
});
await slash('/usage 9999');
const oobReqs = requested.length - beforeOob;
check('/usage 9999 does NOT call the endpoint', oobReqs === 0, `oobReqs=${oobReqs}`);
const oobToasts = await page.evaluate(() => window.__usageToasts);
check('/usage 9999 emits range-out warn',
  oobToasts.some(t => /범위 밖|out of range/i.test(t.m)),
  JSON.stringify(oobToasts));

// 4. /help lists /usage
await slash('/help');
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /usage', /\/usage/.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
