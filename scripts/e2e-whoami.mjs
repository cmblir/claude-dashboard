#!/usr/bin/env node
/**
 * QQ198 — `/whoami` chat slash + `lazyclaude whoami` terminal verb.
 * Both surface Claude CLI identity (email/plan/org) from /api/auth/status,
 * with graceful fallback when not logged in.
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

// Probe what /api/auth/status returns so the assertions match reality
// regardless of whether the dev box is logged in.
const auth = await page.evaluate(async () => {
  const r = await fetch('/api/auth/status');
  return await r.json();
});

// 1. Chat /whoami
await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });
await page.evaluate((l) => _lcChatSlashCommand(l), '/whoami');
await page.waitForTimeout(400);
const chatHtml = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);

if (auth && auth.connected) {
  check('chat /whoami shows email when connected',
    auth.email ? new RegExp(auth.email.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).test(chatHtml) : true);
  check('chat /whoami shows plan label',
    auth.planLabel ? chatHtml.includes(auth.planLabel) : true);
} else {
  check('chat /whoami says not logged in',
    /로그인 안 됨|not logged in|claude auth login/i.test(chatHtml));
}
check('chat /whoami includes current assignee section',
  /현재 어시니|어시니/.test(chatHtml));

// 2. /help lists /whoami
await page.evaluate((l) => _lcChatSlashCommand(l), '/help');
await page.waitForTimeout(200);
const helpHtml = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /whoami', /\/whoami/.test(helpHtml));

// 3. Terminal lazyclaude whoami
await page.evaluate(() => window.go('lazyclawTerm'));
await page.waitForSelector('#lcTermInput', { timeout: 8000 });
await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS.ui, { timeout: 8000 });
// Wait for AFTER-hook health check to finish so its output doesn't
// interleave with our commands.
await page.waitForFunction(() => /헬스체크 완료/.test((document.getElementById('lcTermLog') || {}).textContent || ''), { timeout: 12000 }).catch(() => {});

await page.evaluate(() => {
  const inp = document.getElementById('lcTermInput');
  inp.value = 'lazyclaude whoami';
  return window._lcTermRun();
});
await page.waitForTimeout(500);
const termFullAfterWhoami = await page.evaluate(() => (document.getElementById('lcTermLog') || {}).textContent || '');

if (auth && auth.connected) {
  check('term whoami prints email/plan/cli marker',
    (auth.email && termFullAfterWhoami.includes(auth.email)) ||
    (auth.planLabel && termFullAfterWhoami.includes(auth.planLabel)) ||
    /claude.*--version|claude CLI/.test(termFullAfterWhoami));
} else {
  check('term whoami prints not-logged-in line',
    /not logged in|claude auth login/i.test(termFullAfterWhoami));
}

// 4. Terminal help lists whoami
await page.evaluate(() => {
  const inp = document.getElementById('lcTermInput');
  inp.value = 'lazyclaude help';
  return window._lcTermRun();
});
await page.waitForTimeout(400);
const termFullAfterHelp = await page.evaluate(() => (document.getElementById('lcTermLog') || {}).textContent || '');
check('lazyclaude help lists whoami', /lazyclaude whoami/.test(termFullAfterHelp));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
