#!/usr/bin/env node
/**
 * QQ214 — `lazyclaude help` is now section-grouped + filterable
 * (parity with chat /help QQ213). `lazyclaude help workflow`
 * narrows to the Workflow group; `lazyclaude help no-such` warns.
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
await page.waitForFunction(() =>
  /헬스체크 완료/.test((document.getElementById('lcTermLog') || {}).textContent || ''),
  { timeout: 12000 }).catch(() => {});

async function run(cmd) {
  await page.evaluate((c) => {
    const inp = document.getElementById('lcTermInput');
    inp.value = c;
    return window._lcTermRun();
  }, cmd);
  await page.waitForTimeout(300);
}
const fullLog = async () => await page.evaluate(() => (document.getElementById('lcTermLog') || {}).textContent || '');

// 1. Bare `lazyclaude help` shows all groups
await run('lazyclaude help');
const fullText = await fullLog();
check('help shows Preferences group',  /Preferences/.test(fullText));
check('help shows Navigation group',   /Navigation/.test(fullText));
check('help shows Workflow group',     /Workflow/.test(fullText));
check('help shows Provider/Status',    /Provider \/ Status/.test(fullText));
check('help shows Cost/Version',       /Cost \/ Version/.test(fullText));
check('help shows Terminal group',     /Terminal/.test(fullText));
check('help shows shell whitelist trailer (unfiltered)',
  /Shell whitelist:/.test(fullText));
check('help lists workflows row',      /lazyclaude workflows/.test(fullText));
check('help lists run row',            /lazyclaude run/.test(fullText));
check('help lists uptime row',         /lazyclaude uptime/.test(fullText));

// 2. `lazyclaude help workflow` narrows to Workflow group
await run('lazyclaude reset');
await run('lazyclaude help workflow');
const wfText = await fullLog();
check('help workflow shows Workflow header', /Workflow/.test(wfText));
check('help workflow shows run',           /lazyclaude run/.test(wfText));
check('help workflow shows cancel',        /lazyclaude cancel/.test(wfText));
check('help workflow does NOT show get/set rows',
  !/lazyclaude get \[section/.test(wfText));
check('help workflow does NOT show shell whitelist trailer',
  !/Shell whitelist:/.test(wfText));

// 3. `lazyclaude help cost` matches via alias
await run('lazyclaude reset');
await run('lazyclaude help cost');
const costText = await fullLog();
check('help cost shows usage row',     /lazyclaude usage/.test(costText));
check('help cost shows version row',   /lazyclaude version/.test(costText));

// 4. No-match
await run('lazyclaude help no-such-zzz');
const noMatchText = await fullLog();
check('help <bogus> prints ⚠ no match',
  /⚠.*no match.*no-such-zzz/.test(noMatchText));

// 5. Filter via cmd-name partial
await run('lazyclaude reset');
await run('lazyclaude help diag');
const diagText = await fullLog();
check('help diag shows diag row',       /lazyclaude diag/.test(diagText));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
