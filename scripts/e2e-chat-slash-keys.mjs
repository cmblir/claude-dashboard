#!/usr/bin/env node
/**
 * QQ202 — `/keys` (alias `/providers`) lists every registered provider
 * with availability + API key status (masked). Filter accepts a
 * substring (id/name) like `/agents` and `/sessions`.
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
  await page.waitForTimeout(220);
}

// Probe what providers actually exist so assertions reflect reality
const meta = await page.evaluate(async () => {
  const r = await fetch('/api/ai-providers/list');
  return await r.json();
});
const total = (meta && meta.providers && meta.providers.length) || 0;
check('test prereq: provider list non-empty', total > 0, `total=${total}`);

// 1. /keys lists providers + total count + AI tab pointer
await slash('/keys');
const fullText = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/keys shows total provider count',
  new RegExp(`프로바이더\\s*\\(${total}\\)`).test(fullText), `total=${total}`);
check('/keys lists claude-cli',
  /claude-cli/.test(fullText));
check('/keys lists at least one api-type provider',
  /\(api\)/.test(fullText));
check('/keys points to AI Providers tab',
  /\/go ai/.test(fullText));

// 2. Filter narrows results
await slash('/keys claude');
const filteredText = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/keys claude shows filtered count header',
  /\(\d+\/\d+ · "claude"\)/.test(filteredText));

// 3. No-match toasts
await page.evaluate(() => {
  window.__keysToasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__keysToasts.push({m, k}); return orig && orig(m, k); };
});
await slash('/keys nosuch-zzz');
const t = await page.evaluate(() => window.__keysToasts.slice(-1)[0]);
check('/keys <bogus> toasts "일치하는 프로바이더 없음"',
  t && /일치하는 프로바이더|no match/i.test(t.m), JSON.stringify(t));

// 4. /providers alias
await slash('/providers');
const aliasText = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/providers alias renders the same listing',
  new RegExp(`프로바이더\\s*\\(${total}\\)`).test(aliasText));

// 5. /help lists /keys and /providers
await slash('/help');
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /keys', /\/keys/.test(help));
check('/help lists /providers alias', /\/providers/.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
