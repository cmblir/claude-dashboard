#!/usr/bin/env node
/**
 * Auto-Resume E2E — exercises every panel control end-to-end across the
 * three mandatory viewports (375x667 / 768x800 / 1280x800) per CLAUDE.md §8.
 *
 * Preconditions
 *   - server running at BASE (default http://127.0.0.1:8080)
 *   - at least one indexed session jsonl exists under ~/.claude/projects
 *
 * Verifies
 *   1. Session detail modal renders the Auto-Resume panel
 *   2. Inject button issues POST /api/auto_resume/set and the panel
 *      flips to the live state (state chip + progress bar present)
 *   3. Cancel reverts the panel to inactive
 *   4. Install Hooks / Remove Hooks calls succeed
 *   5. Session list shows the 🔄 AR badge while a binding is active
 *   6. All of the above on each viewport
 */
import { chromium } from 'playwright';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const BASE = process.env.BASE || `http://127.0.0.1:${process.env.PORT || 8080}`;
const HEADLESS = process.env.HEADLESS !== '0';

const VIEWPORTS = [
  { name: 'mobile',  width: 375,  height: 667 },
  { name: 'narrow',  width: 768,  height: 800 },
  { name: 'desktop', width: 1280, height: 800 },
];

function log(prefix, msg) {
  console.log(`[${prefix}] ${msg}`);
}

// Some app navigations (locale fetch, reload heuristics) destroy the
// execution context mid-evaluate. Retry transparently — each attempt
// runs in the fresh context.
async function safeEvaluate(page, fn, arg, attempts = 5) {
  let lastErr;
  for (let i = 0; i < attempts; i++) {
    try {
      return arg === undefined ? await page.evaluate(fn) : await page.evaluate(fn, arg);
    } catch (e) {
      lastErr = e;
      if (!/Execution context was destroyed|Target closed/i.test(e.message)) throw e;
      await page.waitForTimeout(300);
    }
  }
  throw lastErr;
}

async function safeWaitForFunction(page, fn, options) {
  let lastErr;
  for (let i = 0; i < 5; i++) {
    try {
      return await page.waitForFunction(fn, options);
    } catch (e) {
      lastErr = e;
      if (!/Execution context was destroyed/i.test(e.message)) throw e;
      await page.waitForTimeout(300);
    }
  }
  throw lastErr;
}

async function fetchJson(url, init) {
  const r = await fetch(url, init);
  const txt = await r.text();
  try { return { status: r.status, body: JSON.parse(txt) }; }
  catch { return { status: r.status, body: txt }; }
}

async function waitForServerReady(timeoutMs = 30000) {
  const start = Date.now();
  let lastErr;
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(BASE + '/api/auto_resume/status', { signal: AbortSignal.timeout(2000) });
      if (r.ok) return;
      lastErr = new Error('status ' + r.status);
    } catch (e) { lastErr = e; }
    await new Promise(res => setTimeout(res, 500));
  }
  throw new Error(`server at ${BASE} not ready after ${timeoutMs}ms — last err: ${lastErr ? lastErr.message : 'n/a'}`);
}

async function pickSessionId() {
  const r = await fetchJson(BASE + '/api/sessions/list?limit=20&sort=recent');
  if (r.status !== 200 || !r.body || !Array.isArray(r.body.sessions) || r.body.sessions.length === 0) {
    throw new Error('no sessions available — index a Claude Code session first');
  }
  const withCwd = r.body.sessions.filter(s => s.cwd || s.projectPath);
  if (!withCwd.length) throw new Error('no sessions with resolvable cwd');
  return withCwd[0].session_id;
}

async function cleanupBinding(sessionId) {
  await fetchJson(BASE + '/api/auto_resume/cancel', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ sessionId }),
  });
}

async function runViewport(browser, vp, sessionId, sandboxCwd) {
  log(vp.name, `── viewport ${vp.width}x${vp.height} ──`);
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', err => consoleErrors.push('[pageerror] ' + err.message));

  // Disable the dashboard's auto-reload BEFORE navigation so it can't
  // interrupt our test mid-evaluate. (Other API responses can trigger
  // _scheduleAutoReload and the page navigates out from under us.)
  await page.addInitScript(() => {
    window._scheduleAutoReload = () => {};
    window.__noReloadAlways = true;
  });

  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
  await safeWaitForFunction(page,
    () => typeof state !== 'undefined' && !!document.getElementById('view'),
    { timeout: 15000 }
  );
  await safeEvaluate(page, () => { window._scheduleAutoReload = () => {}; });
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(800);

  await safeEvaluate(page, () => { location.hash = '#/sessions'; });
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
  await safeWaitForFunction(page, () => state && state.view === 'sessions', { timeout: 8000 });
  await page.waitForTimeout(800);

  await safeEvaluate(page, (sid) => window.openSessionDetail(sid), sessionId);
  await page.waitForSelector('#autoResumePanel', { timeout: 8000 });

  const initialPanel = await safeEvaluate(page, () => {
    const p = document.getElementById('autoResumePanel');
    return p ? p.dataset.sessionId : null;
  });
  if (initialPanel !== sessionId) {
    throw new Error(`viewport=${vp.name}: panel shows wrong sessionId (got ${initialPanel})`);
  }
  log(vp.name, '✓ Auto-Resume panel rendered');

  // QQ112 — page.waitForFunction polled an arInjectBtn predicate that
  // never returned truthy in the loop's test rig (works in isolated
  // probes; suspected interaction with the AR ticker swapping the
  // panel innerHTML mid-poll under headless Chromium). waitForSelector
  // with state:'visible' uses a dedicated DOM observer instead of
  // page-side eval and is reliable here.
  await page.waitForSelector('#arInjectBtn', { state: 'visible', timeout: 8000 });

  await safeEvaluate(page, () => {
    const det = document.querySelector('#autoResumePanel details');
    if (det) det.open = true;
  });
  await page.waitForTimeout(150);

  await safeEvaluate(page, () => {
    const max = document.getElementById('arMax');
    const poll = document.getElementById('arPoll');
    if (max) max.value = '8';
    if (poll) poll.value = '60';
    // QQ112 — sessions picked from /api/sessions/list are typically not
    // currently running, so the API rejects bind requests without
    // allowUnboundSession=true. Tick the new force-bind checkbox.
    const allow = document.getElementById('arAllowUnbound');
    if (allow) allow.checked = true;
  });

  await page.click('#arInjectBtn');
  await safeWaitForFunction(page, () => {
    const chip = document.getElementById('arStateChip');
    return chip && chip.textContent && chip.textContent.trim().length > 0;
  }, { timeout: 8000 });
  log(vp.name, '✓ Inject -> active state chip visible');

  const hasBar = await safeEvaluate(page, () => {
    const card = document.querySelector('#autoResumePanel .card');
    return card && card.querySelector('div[style*="background:#86efac"], div[style*="background:#fcd34d"], div[style*="background:#fca5a5"]') !== null;
  });
  if (!hasBar) throw new Error(`viewport=${vp.name}: progress bar not rendered`);
  log(vp.name, '✓ Progress bar rendered');

  const cancelExists = await safeEvaluate(page, () => !!document.getElementById('arCancelBtn'));
  if (!cancelExists) throw new Error(`viewport=${vp.name}: cancel button missing`);
  log(vp.name, '✓ Cancel button rendered');

  const cancelResp = await safeEvaluate(page, async (sid) => {
    const r = await fetch('/api/auto_resume/cancel', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ sessionId: sid }),
    });
    return r.ok;
  }, sessionId);
  if (!cancelResp) throw new Error(`viewport=${vp.name}: cancel API failed`);

  await safeEvaluate(page, (sid) => window._arLoad(sid), sessionId);
  await safeWaitForFunction(page, () => !!document.getElementById('arInjectBtn'), { timeout: 5000 });
  log(vp.name, '✓ Cancel reverted panel to inactive');

  const inst = await safeEvaluate(page, async (cwd) => {
    const r = await fetch('/api/auto_resume/install_hooks', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ cwd }),
    });
    return r.json();
  }, sandboxCwd);
  if (!inst.ok || !inst.addedStop || !inst.addedSessionStart) {
    throw new Error(`viewport=${vp.name}: install_hooks failed: ${JSON.stringify(inst)}`);
  }
  const uninst = await safeEvaluate(page, async (cwd) => {
    const r = await fetch('/api/auto_resume/uninstall_hooks', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ cwd }),
    });
    return r.json();
  }, sandboxCwd);
  if (!uninst.ok || uninst.removedStop !== 1 || uninst.removedSessionStart !== 1) {
    throw new Error(`viewport=${vp.name}: uninstall_hooks failed: ${JSON.stringify(uninst)}`);
  }
  log(vp.name, '✓ Hook install/uninstall round-trip OK');

  await safeEvaluate(page, async (sid) => {
    await fetch('/api/auto_resume/set', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ sessionId: sid, prompt: 'badge test', pollInterval: 60, idleSeconds: 30, maxAttempts: 3, allowUnboundSession: true }),
    });
  }, sessionId);

  await safeEvaluate(page, () => closeModal && closeModal());
  await safeEvaluate(page, () => renderView && renderView());
  await page.waitForTimeout(700);
  const badgePresent = await safeEvaluate(page, (sid) => {
    const rows = document.querySelectorAll('tr.link-row');
    for (const r of rows) {
      if (r.getAttribute('onclick') && r.getAttribute('onclick').includes(sid)) {
        return r.innerHTML.includes('AR');
      }
    }
    return false;
  }, sessionId);
  if (!badgePresent) throw new Error(`viewport=${vp.name}: AR badge missing in sessions list`);
  log(vp.name, '✓ Session list shows 🔄 AR badge');

  await cleanupBinding(sessionId);

  if (consoleErrors.length) {
    const ours = consoleErrors.filter(e =>
      /auto_resume|auto-resume|_arSubmit|_arCancel|_arLoad|autoResumePanel/i.test(e)
    );
    if (ours.length) {
      throw new Error(`viewport=${vp.name}: console errors related to auto-resume:\n  ${ours.join('\n  ')}`);
    }
  }

  await context.close();
  log(vp.name, `✅ viewport ${vp.name} PASS`);
}

(async () => {
  await waitForServerReady();
  log('boot', `server ready at ${BASE}`);
  const sessionId = await pickSessionId();
  log('boot', `using sessionId=${sessionId}`);

  const sandboxCwd = mkdtempSync(join(tmpdir(), 'lz-ar-e2e-'));
  log('boot', `sandbox cwd=${sandboxCwd}`);

  const browser = await chromium.launch({ headless: HEADLESS });
  const failures = [];
  try {
    for (const vp of VIEWPORTS) {
      try {
        await runViewport(browser, vp, sessionId, sandboxCwd);
      } catch (e) {
        failures.push({ viewport: vp.name, error: e.message });
        log(vp.name, `❌ ${e.message}`);
      }
    }
  } finally {
    await browser.close();
    try {
      if (existsSync(sandboxCwd)) rmSync(sandboxCwd, { recursive: true, force: true });
    } catch {}
    await cleanupBinding(sessionId);
  }

  console.log('');
  if (failures.length) {
    console.log(`❌ ${failures.length}/${VIEWPORTS.length} viewports failed`);
    for (const f of failures) console.log(`  - ${f.viewport}: ${f.error}`);
    process.exit(1);
  } else {
    console.log(`✅ ${VIEWPORTS.length}/${VIEWPORTS.length} viewports PASS — Auto-Resume E2E green`);
  }
})();
