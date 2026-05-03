#!/usr/bin/env node
/**
 * QQ212 — Tab autocomplete + unknown-command heuristic vocab now
 * covers every slash added in QQ198-QQ211: /whoami, /pin, /unpin,
 * /branch, /fork, /temperature, /temp, /keys, /providers, /usage,
 * /workflows, /wfs, /run, /cancel, /uptime.
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
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

async function tab(seed, times = 1) {
  await page.evaluate((s) => {
    const ta = document.getElementById('lcChatInput');
    ta.focus();
    ta.value = s;
    ta.selectionStart = ta.selectionEnd = s.length;
    window.__lcTabCycle = null;
  }, seed);
  for (let i = 0; i < times; i++) {
    await page.keyboard.press('Tab');
    await page.waitForTimeout(30);
  }
  return await page.evaluate(() => document.getElementById('lcChatInput').value);
}

// 1. Single-match expansions
const cases = [
  ['/who', '/whoami'],
  ['/pi',  '/pin'],
  ['/unp', '/unpin'],
  ['/for', '/fork'],
  ['/key', '/keys'],
  ['/pro', '/providers'],
  ['/usa', '/usage'],
  ['/wfs', '/wfs'],
  ['/run', '/run'],
  ['/can', '/cancel'],
  ['/upt', '/uptime'],
];
for (const [seed, expect] of cases) {
  const got = await tab(seed);
  check(`${seed}<Tab> → ${expect}`, got === expect, `got="${got}"`);
}

// 2. /b<Tab> cycles between /branch (could overlap with nothing else
//    starting with b-)
const r1 = await tab('/b');
check('/b<Tab> picks /branch (only b- candidate)', r1 === '/branch', `got="${r1}"`);

// 3. /te<Tab> cycles temperature/temp (only those start with /te-)
const teSeen = new Set();
teSeen.add(await tab('/te', 1));
teSeen.add(await tab('/te', 2));
check('/te<Tab>×N cycles /temp + /temperature',
  teSeen.has('/temp') && teSeen.has('/temperature'),
  `seen=${[...teSeen].join(',')}`);

// 4. /w<Tab> cycles whoami / workflows / wfs
const wSeen = new Set();
wSeen.add(await tab('/w', 1));
wSeen.add(await tab('/w', 2));
wSeen.add(await tab('/w', 3));
check('/w<Tab>×3 covers whoami + workflows + wfs',
  wSeen.has('/whoami') && wSeen.has('/workflows') && wSeen.has('/wfs'),
  `seen=${[...wSeen].join(',')}`);

// 5. Unknown-command heuristic now suggests new commands.
//    /whoam<Enter> (typo of whoami) should toast a "혹시 /whoami?" hint.
await page.evaluate(() => {
  window.__unkToasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__unkToasts.push({m, k}); return orig && orig(m, k); };
});
await page.evaluate((l) => _lcChatSlashCommand(l), '/whoam');
const ut = await page.evaluate(() => window.__unkToasts);
check('typo /whoam → suggests /whoami',
  ut.some(t => /\/whoami/.test(t.m)), JSON.stringify(ut));

// 6. /upitme typo → suggests /uptime
await page.evaluate(() => { window.__unkToasts.length = 0; });
await page.evaluate((l) => _lcChatSlashCommand(l), '/upitme');
const ut2 = await page.evaluate(() => window.__unkToasts);
check('typo /upitme → suggests /uptime',
  ut2.some(t => /\/uptime/.test(t.m)), JSON.stringify(ut2));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
