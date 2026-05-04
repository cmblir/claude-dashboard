#!/usr/bin/env node
/**
 * QQ221 — verifies the live-CLI-sessions tab exposes a one-click
 * Auto-Resume inject button per row, the click POSTs to
 * /api/auto_resume/set, the row flips to the "AR 중단" state, and
 * cancelling reverts it.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE || `http://127.0.0.1:${process.env.PORT || 8080}`;
const HEADLESS = process.env.HEADLESS !== '0';

async function fetchJson(url, init) {
  const r = await fetch(url, init);
  const txt = await r.text();
  try { return { status: r.status, body: JSON.parse(txt) }; }
  catch { return { status: r.status, body: txt }; }
}

(async () => {
  // 1. preflight: at least one live CLI session
  const live = await fetchJson(BASE + '/api/sessions-monitor/list');
  if (!live.body || !live.body.ok || !Array.isArray(live.body.sessions) || live.body.sessions.length === 0) {
    console.error('skip: no live CLI sessions to drive the test');
    process.exit(0);
  }
  const target = live.body.sessions[0];
  console.log(`[boot] target sid=${target.sessionId.slice(0,8)} cwd=${target.cwd}`);

  // clean any pre-existing binding
  await fetchJson(BASE + '/api/auto_resume/cancel', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ sessionId: target.sessionId }),
  });

  const browser = await chromium.launch({ headless: HEADLESS });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push('[pageerror] ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });

  await page.addInitScript(() => { window._scheduleAutoReload = () => {}; });

  // accept the cancel confirm() dialog
  page.on('dialog', d => d.accept());

  await page.goto(BASE + '/#/cliSessions', { waitUntil: 'networkidle', timeout: 30000 });
  // Dismiss onboarding gate if present.
  try {
    await page.waitForSelector('#gateContinueBtn', { timeout: 2000 });
    await page.click('#gateContinueBtn');
  } catch {}
  await page.waitForFunction(() => typeof state !== 'undefined' && state.view === 'cliSessions', { timeout: 15000 });
  await page.waitForTimeout(1500);

  // Verify the inject button for our target row exists
  const sidShort = target.sessionId.slice(0, 8);
  const rowSel = `tr:has(td:has-text("${sidShort}"))`;
  await page.waitForSelector(rowSel, { timeout: 8000 });

  const injectBtn = page.locator(rowSel).locator('button', { hasText: /Auto-Resume 주입|Auto-Resume Inject|注入/i });
  const cnt = await injectBtn.count();
  if (cnt === 0) throw new Error('inject button not found in row');
  console.log('[step] ✓ inject button visible');

  // Click and wait for the row to re-render with "AR 중단"
  await injectBtn.first().click();
  await page.waitForFunction((sid) => {
    const rows = document.querySelectorAll('table.data tbody tr');
    for (const r of rows) {
      if (r.textContent.includes(sid.slice(0, 8))) {
        return /AR 중단|AR Stop|AR 停止/.test(r.textContent);
      }
    }
    return false;
  }, target.sessionId, { timeout: 8000 });
  console.log('[step] ✓ row flipped to AR 중단 (binding active)');

  // Confirm via API
  const status = await fetchJson(BASE + '/api/auto_resume/status');
  const found = (status.body.active || []).find(e => e.sessionId === target.sessionId);
  if (!found || !found.enabled) throw new Error('binding not enabled server-side');
  console.log(`[step] ✓ server-side binding state=${found.state} enabled=${found.enabled}`);

  // Cancel via the same row's button
  const cancelBtn = page.locator(rowSel).locator('button', { hasText: /AR 중단|AR Stop|AR 停止/i }).first();
  await cancelBtn.click();
  await page.waitForFunction((sid) => {
    const rows = document.querySelectorAll('table.data tbody tr');
    for (const r of rows) {
      if (r.textContent.includes(sid.slice(0, 8))) {
        return /Auto-Resume 주입|Auto-Resume Inject|注入/.test(r.textContent);
      }
    }
    return false;
  }, target.sessionId, { timeout: 8000 });
  console.log('[step] ✓ row reverted to inject state');

  if (errs.length) {
    const ours = errs.filter(e => /auto_resume|cliSessions|_pmInjectAR|_pmCancelAR/i.test(e));
    if (ours.length) throw new Error('console errors:\n  ' + ours.join('\n  '));
  }

  await ctx.close();
  await browser.close();
  console.log('✅ e2e-cli-sessions-ar PASS');
})().catch(e => { console.error('❌', e.message); process.exit(1); });
