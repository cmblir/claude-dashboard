#!/usr/bin/env node
/**
 * QQ213 — `/help` is now section-grouped (Session, AI, Workflow,
 * Cost/Status, Navigation/Appearance) and accepts an optional
 * substring filter. `/help workflow` shows only Workflow rows;
 * `/help no-such` warns "일치하는 명령 없음".
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
  await page.waitForTimeout(180);
}

// 1. Bare /help renders all section headers
await slash('/help');
const fullText = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/help shows Session group',     /세션/.test(fullText));
check('/help shows AI provider group', /AI 프로바이더|모델/.test(fullText));
check('/help shows Workflow group',    /워크플로우/.test(fullText));
check('/help shows Cost/Status group', /비용|상태/.test(fullText));
check('/help shows shortcuts section', /단축키/.test(fullText));
check('/help lists /run',              /\/run/.test(fullText));
check('/help lists /pin',              /\/pin/.test(fullText));
check('/help lists /uptime',           /\/uptime/.test(fullText));
check('/help lists Tab autocomplete shortcut', /자동완성/.test(fullText));

// 2. /help workflow filter narrows to workflow rows only (no Session)
await slash('/clear');  // Wipe so the filtered help is the only fresh content
await page.evaluate(() => { window.confirm = () => true; });
await slash('/clear');
await slash('/help workflow');
const wfText = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/help workflow header includes filter label',
  /필터.*workflow/i.test(wfText));
check('/help workflow shows /run',     /\/run/.test(wfText));
check('/help workflow shows /cancel',  /\/cancel/.test(wfText));
check('/help workflow does NOT show /clear',
  !/\/clear/.test(wfText));
check('/help workflow does NOT show shortcuts (filter mode)',
  !/Cmd\/Ctrl/.test(wfText));

// 3. /help <bogus> warns
await page.evaluate(() => {
  window.__hToasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__hToasts.push({m, k}); return orig && orig(m, k); };
});
await slash('/help nosuchword-zzz');
const hT = await page.evaluate(() => window.__hToasts.slice(-1)[0]);
check('/help <bogus> warns "일치하는 명령 없음"',
  hT && /일치하는 명령|no match/i.test(hT.m), JSON.stringify(hT));

// 4. /help temperature shows /temperature row even though it spans groups
await slash('/clear');
await slash('/help temperature');
const tText = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/help temperature shows /temperature row',
  /\/temperature/.test(tText));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
