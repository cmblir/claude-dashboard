#!/usr/bin/env node
/**
 * QQ206 — `/workflows` (alias `/wfs`) lists workflows from chat with
 * filter + running/total counts + last-run status chip. Mirrors the
 * /tabs / /sessions / /agents / /keys pattern.
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

const meta = await page.evaluate(async () => {
  const r = await fetch('/api/workflows/list');
  return await r.json();
});
const total = (meta && meta.workflows && meta.workflows.length) || 0;
check('test prereq: workflow list non-empty', total > 0, `total=${total}`);

// 1. /workflows lists count + first workflow name + edit pointer
await slash('/workflows');
const fullText = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/workflows shows total count',
  new RegExp(`워크플로우\\s*\\(${total}\\)`).test(fullText), `total=${total}`);
check('/workflows lists at least one workflow id',
  /wf-\d+/.test(fullText));
check('/workflows points to workflows tab',
  /\/go workflows/.test(fullText));

// 2. Filter narrows results
const someName = (meta.workflows[0].name || '').slice(0, 6);
if (someName) {
  await slash('/workflows ' + someName);
  const filtered = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
  const headerRe = new RegExp(`\\(\\d+\\/\\d+ · "${someName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"\\)`);
  check('/workflows <filter> shows filtered count header',
    headerRe.test(filtered));
}

// 3. No-match toasts
await page.evaluate(() => {
  window.__wfToasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__wfToasts.push({m, k}); return orig && orig(m, k); };
});
await slash('/workflows nosuch-zzz-xyz');
const t = await page.evaluate(() => window.__wfToasts.slice(-1)[0]);
check('/workflows <bogus> toasts "일치하는 워크플로우 없음"',
  t && /일치하는 워크플로우|no match/i.test(t.m), JSON.stringify(t));

// 4. /wfs alias
await slash('/wfs');
const aliasText = await page.evaluate(() => document.getElementById('lcChatLog').innerText);
check('/wfs alias renders the same listing',
  new RegExp(`워크플로우\\s*\\(${total}\\)`).test(aliasText));

// 5. /help lists /workflows + /wfs
await slash('/help');
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /workflows', /\/workflows/.test(help));
check('/help lists /wfs alias', /\/wfs/.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
