#!/usr/bin/env node
/**
 * QQ211 — `/uptime` chat slash + `lazyclaude uptime` terminal verb.
 * Both surface server uptime + version + start time from /api/version.
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

// 1. Chat /uptime
await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });
await page.evaluate((l) => _lcChatSlashCommand(l), '/uptime');
await page.waitForTimeout(300);
const chatText = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('chat /uptime shows version', /v\d+\.\d+\.\d+/.test(chatText));
check('chat /uptime shows uptime line', /가동 시간|uptime/i.test(chatText));
check('chat /uptime shows non-zero seconds',
  /\d+s/.test(chatText));

// 2. /help lists /uptime
await page.evaluate((l) => _lcChatSlashCommand(l), '/help');
await page.waitForTimeout(200);
const helpHtml = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /uptime', /\/uptime/.test(helpHtml));

// 3. Terminal lazyclaude uptime
await page.evaluate(() => window.go('lazyclawTerm'));
await page.waitForSelector('#lcTermInput', { timeout: 8000 });
await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS.ui, { timeout: 8000 });
await page.waitForFunction(() =>
  /헬스체크 완료/.test((document.getElementById('lcTermLog') || {}).textContent || ''),
  { timeout: 12000 }).catch(() => {});

await page.evaluate(() => {
  const inp = document.getElementById('lcTermInput');
  inp.value = 'lazyclaude uptime';
  return window._lcTermRun();
});
await page.waitForTimeout(400);
const termOut = await page.evaluate(() => (document.getElementById('lcTermLog') || {}).textContent || '');
check('term uptime prints version line', /version:\s+v\d+\.\d+\.\d+/.test(termOut));
check('term uptime prints uptime line',  /uptime:\s+\d+/.test(termOut));
check('term uptime prints ISO start time',
  /started:\s+\d{4}-\d{2}-\d{2}T/.test(termOut));

// 4. Terminal help lists uptime
await page.evaluate(() => {
  const inp = document.getElementById('lcTermInput');
  inp.value = 'lazyclaude help';
  return window._lcTermRun();
});
await page.waitForTimeout(300);
const termHelp = await page.evaluate(() => (document.getElementById('lcTermLog') || {}).textContent || '');
check('lazyclaude help lists uptime', /lazyclaude uptime/.test(termHelp));

// 5. Typo did-you-mean
await page.evaluate(() => {
  const inp = document.getElementById('lcTermInput');
  inp.value = 'lazyclaude uptiime';
  return window._lcTermRun();
});
await page.waitForTimeout(300);
const typoOut = await page.evaluate(() => (document.getElementById('lcTermLog') || {}).textContent || '');
check('lazyclaude uptiime → suggests uptime',
  /lazyclaude uptime/.test(typoOut));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
