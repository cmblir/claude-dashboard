#!/usr/bin/env node
/**
 * QQ204 — terminal parity for chat /keys (QQ202) and /usage (QQ203).
 * `lazyclaude keys` lists registered providers + api-key state.
 * `lazyclaude usage [N]` aggregates cost across all sessions.
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
await page.evaluate(() => window.go('lazyclawTerm'));
await page.waitForSelector('#lcTermInput', { timeout: 8000 });
await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS.ui, { timeout: 8000 });

// Wait for AFTER-hook health check to settle
await page.waitForFunction(() =>
  /헬스체크 완료/.test((document.getElementById('lcTermLog') || {}).textContent || ''),
  { timeout: 12000 }).catch(() => {});

async function run(cmd) {
  await page.evaluate((c) => {
    const inp = document.getElementById('lcTermInput');
    inp.value = c;
    return window._lcTermRun();
  }, cmd);
  await page.waitForTimeout(350);
}

async function lastFull() {
  return await page.evaluate(() => (document.getElementById('lcTermLog') || {}).textContent || '');
}

// 1. lazyclaude keys lists providers
await run('lazyclaude keys');
const keysOut = await lastFull();
check('lazyclaude keys lists claude-cli', /claude-cli/.test(keysOut));
check('lazyclaude keys marks availability with ✅ or ❌',
  /[✅❌]\s+\S+/.test(keysOut));
check('lazyclaude keys distinguishes (cli) vs (api)',
  /\(cli\)/.test(keysOut) && /\(api\)/.test(keysOut));

// 2. lazyclaude usage default 7d
await run('lazyclaude usage');
const usageOut = await lastFull();
check('lazyclaude usage prints "Usage · 7d" header',
  /Usage\s*·\s*7d/.test(usageOut));
check('lazyclaude usage prints total line',
  /total:\s*\$/i.test(usageOut));
check('lazyclaude usage prints calls line',
  /calls:/i.test(usageOut));

// 3. lazyclaude usage 30
await run('lazyclaude usage 30');
const usage30 = await lastFull();
check('lazyclaude usage 30 prints 30d header',
  /Usage\s*·\s*30d/.test(usage30));

// 4. usage out-of-range emits ⚠ warn
await run('lazyclaude usage 9999');
const usageOob = await lastFull();
check('lazyclaude usage 9999 prints ⚠ warn',
  /⚠.*범위 밖/.test(usageOob));

// 5. lazyclaude help lists keys + usage
await run('lazyclaude help');
const helpOut = await lastFull();
check('help lists keys', /lazyclaude keys/.test(helpOut));
check('help lists usage', /lazyclaude usage/.test(helpOut));

// 6. typo did-you-mean still works after the verb list extension
await run('lazyclaude kez');
const typoOut = await lastFull();
check('lazyclaude kez → suggests keys',
  /lazyclaude keys/.test(typoOut));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
