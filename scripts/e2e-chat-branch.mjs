#!/usr/bin/env node
/**
 * QQ23 + QQ24 — branch a chat session from a specific message and
 * verify lineage hint in the sidebar.
 */
import { chromium } from 'playwright';

const PORT = process.env.PORT || '19500';
const URL  = `http://127.0.0.1:${PORT}/`;

function check(label, ok) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}`);
  if (!ok) process.exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

// Seed a session with 4 messages so we can branch from message #1.
const seeded = await page.evaluate(() => {
  // Wipe sessions for a clean slate.
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  const id = _lcCurrentId();
  const sessions = _lcGetSessions();
  const s = sessions.find(x => x.id === id);
  if (s) s.label = 'parent-session';
  _lcSaveSessions(sessions);
  _lcSaveHistory(id, [
    { role: 'user',      text: 'q1', ts: 100, assignee: 'claude:opus' },
    { role: 'assistant', text: 'a1', ts: 110, assignee: 'claude:opus', costUsd: 0.001 },
    { role: 'user',      text: 'q2', ts: 200, assignee: 'claude:opus' },
    { role: 'assistant', text: 'a2', ts: 210, assignee: 'claude:opus', costUsd: 0.002 },
  ]);
  _lcChatRender();
  _lcRenderSessions();
  return { id, sessionsLen: _lcGetSessions().length };
});
check('parent session created', seeded.sessionsLen === 1);

// Branch from message index 1 (the first assistant reply).
const branched = await page.evaluate(async () => {
  _lcBranchFrom(_lcCurrentId(), 1);
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const sessions = _lcGetSessions();
  const cur = _lcCurrentId();
  const branch = sessions.find(s => s.id === cur);
  return {
    sessionsCount: sessions.length,
    parentId: branch && branch.parentId,
    branchedAt: branch && branch.branchedAt,
    historyLen: _lcGetHistory(cur).length,
    label: branch && branch.label,
  };
});

check('new branch session created (count = 2)', branched.sessionsCount === 2);
check('branch.parentId points at the original',  !!branched.parentId);
check('branch.branchedAt records source idx',     branched.branchedAt === 1);
check('branch history truncated at idx + 1 (2 msgs)', branched.historyLen === 2);
check('branch label includes "분기" or "branch"',
  /분기|branch/i.test(branched.label || ''));

// Verify QQ24 lineage chip in the sidebar.
const lineage = await page.evaluate(() => {
  const list = document.getElementById('lcSessionList');
  if (!list) return { found: false };
  // Active row is the new branch.
  const active = list.querySelector('[data-active="1"]');
  if (!active) return { found: false };
  const text = active.textContent || '';
  return {
    found: text.includes('↳') && text.includes('parent-session'),
    text,
  };
});
check('QQ24 ↳ lineage chip shows parent label', lineage.found);

// Click parent session → verify QQ65 assignee restore + history.
const switched = await page.evaluate(async () => {
  const sessions = _lcGetSessions();
  const parent = sessions.find(s => !s.parentId);
  _lcSwitchSession(parent.id);
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  return {
    cur: _lcCurrentId(),
    parentId: parent.id,
    historyLen: _lcGetHistory(parent.id).length,
  };
});
check('switch back to parent', switched.cur === switched.parentId);
check('parent history still 4 messages', switched.historyLen === 4);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
