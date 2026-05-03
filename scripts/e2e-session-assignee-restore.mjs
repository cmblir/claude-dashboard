#!/usr/bin/env node
/**
 * QQ65 + QQ67 + QQ91 — switching sessions restores the session's
 * stored assignee onto the model dropdown, backfills it for legacy
 * sessions, and the per-session model badge in the sidebar shows
 * the model name (with full tag like "llama3.1:8b" via QQ104).
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

// Seed 3 sessions with distinct assignees + a legacy one with no
// assignee field at all.
const ids = await page.evaluate(() => {
  _lcSaveSessions([]);
  // session A: claude:opus
  _lcNewSession('claude:opus');
  const idA = _lcCurrentId();
  let ss = _lcGetSessions(); ss.find(s => s.id === idA).label = 'sess-A';
  _lcSaveSessions(ss);
  // session B: ollama:llama3.1:8b (multi-colon — exercises QQ104 fix)
  _lcNewSession('ollama:llama3.1:8b');
  const idB = _lcCurrentId();
  ss = _lcGetSessions(); ss.find(s => s.id === idB).label = 'sess-B';
  _lcSaveSessions(ss);
  // legacy session: no assignee field at all.
  const idL = _lcMakeSessionId();
  ss = _lcGetSessions();
  ss.unshift({ id: idL, label: 'sess-legacy', ts: Date.now(), preview: '' }); // no assignee
  _lcSaveSessions(ss);
  // Add the option for sess-A / sess-B values to the dropdown so
  // _lcSwitchSession's dropdown.value=… succeeds without our adding logic.
  _lcRenderSessions();
  return { idA, idB, idL };
});

// Switch to A → dropdown should be claude:opus.
await page.evaluate((id) => _lcSwitchSession(id), ids.idA);
await page.waitForTimeout(120);
const valA = await page.$eval('#lcChatAssignee', el => el.value);
check('switch A: dropdown value = claude:opus', valA === 'claude:opus');

// Switch to B → dropdown should be ollama:llama3.1:8b (the QQ65
// option-injection path adds it if missing).
await page.evaluate((id) => _lcSwitchSession(id), ids.idB);
await page.waitForTimeout(120);
const valB = await page.$eval('#lcChatAssignee', el => el.value);
check('switch B: dropdown value = ollama:llama3.1:8b',
  valB === 'ollama:llama3.1:8b');

// QQ91 sidebar model badge: B's label retains "llama3.1:8b" (full
// model spec after the first colon).
const badgeText = await page.evaluate((id) => {
  const list = document.getElementById('lcSessionList');
  const items = Array.from(list.querySelectorAll('div'));
  // Find the row for sess-B by label.
  const row = items.find(d => d.textContent && d.textContent.includes('sess-B'));
  if (!row) return null;
  return row.textContent;
}, ids.idB);
check('QQ91 badge for B contains "llama3.1:8b"',
  /llama3\.1:8b/.test(badgeText || ''));

// QQ67 backfill: switch to legacy. The dropdown's current value
// should get written onto the session as its new assignee.
await page.evaluate((id) => _lcSwitchSession(id), ids.idL);
await page.waitForTimeout(120);
const legacyAssignee = await page.evaluate((id) => {
  const s = _lcGetSessions().find(x => x.id === id);
  return s && s.assignee;
}, ids.idL);
check('QQ67 backfill: legacy session got the dropdown value as assignee',
  typeof legacyAssignee === 'string' && legacyAssignee.length > 0);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
