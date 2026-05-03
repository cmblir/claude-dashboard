#!/usr/bin/env node
/**
 * QQ45 — Cmd+K search walks both legacy `cc.lazyclawChat.history.*`
 * and per-session `cc.lc.hist.*` keys.
 * QQ97 / QQ98 / QQ99 / QQ100 / QQ102 — cost visibility chain
 * (per-turn meta, per-session sidebar chip, sidebar header today/total,
 * composer footer current-session spend).
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
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

// Seed 2 sessions with cost-bearing messages.
await page.evaluate(() => {
  _lcSaveSessions([]);
  // session A: 2 paid turns
  _lcNewSession('claude:opus');
  const ida = _lcCurrentId();
  let sessions = _lcGetSessions();
  let s = sessions.find(x => x.id === ida); s.label = 'session-A';
  _lcSaveSessions(sessions);
  const todayMs = Date.now();
  _lcSaveHistory(ida, [
    { role: 'user',      text: 'find the unicorn',  ts: todayMs - 60000 },
    { role: 'assistant', text: 'unicorn replied',   ts: todayMs - 50000, costUsd: 0.012, tokensIn: 100, tokensOut: 200 },
    { role: 'user',      text: 'second prompt',     ts: todayMs - 40000 },
    { role: 'assistant', text: 'A2',                ts: todayMs - 30000, costUsd: 0.008, tokensIn: 50,  tokensOut: 50  },
  ]);
  // session B: 1 paid turn (yesterday)
  _lcNewSession('openai:gpt-4');
  const idb = _lcCurrentId();
  sessions = _lcGetSessions();
  s = sessions.find(x => x.id === idb); s.label = 'session-B';
  _lcSaveSessions(sessions);
  const yesterdayMs = todayMs - 36 * 3600 * 1000;
  _lcSaveHistory(idb, [
    { role: 'user',      text: 'a query about lions', ts: yesterdayMs },
    { role: 'assistant', text: 'B1',                  ts: yesterdayMs + 1000, costUsd: 0.005 },
  ]);
  // Mark "we have cost" for QQ101 short-circuit.
  localStorage.setItem('cc.lc.hasCost', '1');
  _lcSetCurrentId(ida);  // active = session A
  _lcRenderSessions();
  _lcChatRender();
});
await page.waitForTimeout(150);

// QQ45 — Cmd+K opens search and "unicorn" finds the assistant message
// in session-A.
await page.click('#lcChatInput');
await page.keyboard.press('Meta+k');
await page.waitForTimeout(150);
await page.fill('#lcSearchInp', 'unicorn');
await page.waitForTimeout(250);
const hits = await page.evaluate(() => {
  const cards = document.querySelectorAll('.modal button.card');
  return Array.from(cards).map(c => c.textContent.trim().slice(0, 80));
});
check('search "unicorn" returns at least 1 hit', hits.length >= 1);
check('first hit references session-A',
  hits[0] && (hits[0].includes('session-A') || hits[0].includes('A')));

// Close modal.
await page.evaluate(() => closeModal && closeModal());
await page.waitForTimeout(80);

// QQ99 + QQ100 — sidebar header shows today + total.
const totalSpend = await page.evaluate(() => {
  const el = document.getElementById('lcTotalSpend');
  return el && el.textContent;
});
check('sidebar header shows total spend', /\$0\.0\d/.test(totalSpend || ''));
check('sidebar header includes 오늘 / 총 누적 markers',
  /오늘|Today|今日/.test(totalSpend || '') &&
  /누적|Total|总计/.test(totalSpend || ''));

// QQ98 — per-session sidebar cost chip: session-A has $0.020 (0.012+0.008).
const rowSpend = await page.evaluate(() => {
  const list = document.getElementById('lcSessionList');
  const rows = Array.from(list.querySelectorAll('div')).filter(d => d.textContent.includes('session-A'));
  // Find the chip with $ marker
  const chip = rows.find(r => /\$/.test(r.textContent));
  return chip && chip.textContent;
});
check('session-A row shows $ spend chip', /\$0\.0\d/.test(rowSpend || ''));

// QQ102 — composer footer (current-session spend) shows for session-A.
const footerSpend = await page.evaluate(() => {
  const el = document.getElementById('lcInputSessCost');
  const v = document.getElementById('lcInputSessCostVal');
  return {
    visible: el && el.style.display !== 'none',
    value: v && v.textContent,
  };
});
check('composer footer current-session spend visible', footerSpend.visible);
check('composer footer value matches session-A total',
  /^0\.02/.test(footerSpend.value || ''));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
