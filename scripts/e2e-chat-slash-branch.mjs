#!/usr/bin/env node
/**
 * QQ200 — `/branch` (and alias `/fork`) slash command. With no arg
 * clones the entire current session; with `/branch N` branches from
 * message N (1-based). Reuses _lcBranchFrom so lineage chip + parentId
 * stay consistent with the per-message 🍴 button.
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

await page.evaluate(() => {
  localStorage.removeItem('cc.lc.sessions');
  localStorage.removeItem('cc.lc.current');
  for (const k of Object.keys(localStorage)) if (k.startsWith('cc.lc.hist.')) localStorage.removeItem(k);
});

await page.evaluate(() => window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

// Seed a session with 4 messages
const seedId = await page.evaluate(() => {
  const id = _lcMakeSessionId();
  _lcSaveSessions([{ id, label: 'parent-session', assignee: '', ts: Date.now(), preview: '' }]);
  _lcSetCurrentId(id);
  _lcSaveHistory(id, [
    { role: 'user',      text: 'q1', ts: Date.now() },
    { role: 'assistant', text: 'a1', ts: Date.now() },
    { role: 'user',      text: 'q2', ts: Date.now() },
    { role: 'assistant', text: 'a2', ts: Date.now() },
  ]);
  _lcChatRender();
  _lcRenderSessions();
  return id;
});

async function slash(line) {
  await page.evaluate((l) => _lcChatSlashCommand(l), line);
  await page.waitForTimeout(180);
}

// 1. /branch with no arg → full clone (4 messages)
await slash('/branch');
const afterFull = await page.evaluate((parentId) => {
  const sessions = _lcGetSessions();
  const cur = _lcCurrentId();
  const newSession = sessions.find(s => s.id === cur);
  return {
    sessionsLen: sessions.length,
    currentIsBranch: cur !== parentId,
    parentId: newSession && newSession.parentId,
    historyLen: _lcGetHistory(cur).length,
    label: newSession && newSession.label,
  };
}, seedId);
check('/branch (no arg) creates a new session',
  afterFull.sessionsLen === 2 && afterFull.currentIsBranch);
check('/branch full clone copies all 4 messages',
  afterFull.historyLen === 4, `len=${afterFull.historyLen}`);
check('/branch sets parentId on the new session',
  afterFull.parentId === seedId, `parentId=${afterFull.parentId}`);
check('/branch label includes "분기" or "branch"',
  /분기|branch/i.test(afterFull.label || ''), `label=${afterFull.label}`);

// Switch back to parent
await page.evaluate((id) => _lcSetCurrentId(id), seedId);
await page.evaluate(() => { _lcChatRender(); _lcRenderSessions(); });

// 2. /branch 2 → branch at message #2 (1-based) = idx=1, slice 0..1+1 = 2 messages
await slash('/branch 2');
const afterIdx = await page.evaluate(() => {
  const cur = _lcCurrentId();
  return { historyLen: _lcGetHistory(cur).length, parentId: (_lcGetSessions().find(s=>s.id===cur)||{}).parentId };
});
check('/branch 2 truncates to 2 messages',
  afterIdx.historyLen === 2, `len=${afterIdx.historyLen}`);

// Switch back to parent for next assertion
await page.evaluate((id) => _lcSetCurrentId(id), seedId);

// 3. /branch with out-of-range index toasts "범위 밖"
await page.evaluate(() => {
  window.__branchToasts = [];
  const orig = window.toast;
  window.toast = (m, k) => { window.__branchToasts.push({m, k}); return orig && orig(m, k); };
});
await slash('/branch 99');
const oobToasts = await page.evaluate(() => window.__branchToasts);
check('/branch 99 (out of range) emits warn toast',
  oobToasts.some(t => /범위 밖|out of range/i.test(t.m)), JSON.stringify(oobToasts));

// 4. /fork is an alias for /branch
const beforeForkCount = await page.evaluate(() => _lcGetSessions().length);
await slash('/fork');
const afterForkCount = await page.evaluate(() => _lcGetSessions().length);
check('/fork creates a new session (alias)', afterForkCount === beforeForkCount + 1);

// 5. /help lists /branch
await slash('/help');
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /branch', /\/branch/.test(help));
check('/help lists /fork alias', /\/fork/.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
