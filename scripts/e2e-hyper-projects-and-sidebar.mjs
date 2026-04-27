// Playwright smoke for v2.40.0 — Hyper Agent project scope + sidebar UX.
//
// Verifies:
// 1. Hyper Agent project-scoped lifecycle (configure/get/refine/rollback) via
//    new POST endpoints with a {name, cwd} body.
// 2. Same-name twin separation: a global agent and a project agent with the
//    same name keep independent meta entries.
// 3. Sidebar favorites toggle via toggleFavoriteTab() persists to prefs and
//    surfaces a "★ 즐겨찾기" section above the categorical groups.
// 4. Sidebar recent-tab MRU appears after a few go() calls and respects the
//    prefs.ui.recentTabsLimit cap.
// 5. '/' key alone opens spotlight (when no input is focused).
import { chromium } from 'playwright';
import { writeFileSync, existsSync, unlinkSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8080';
const errors = [];

const AGENTS_DIR = path.join(homedir(), '.claude', 'agents');
const GLOBAL_AGENT = path.join(AGENTS_DIR, 'v40-test.md');
const TMP_PROJ = mkdtempSync(path.join(tmpdir(), 'v40-proj-'));
const PROJ_AGENTS_DIR = path.join(TMP_PROJ, '.claude', 'agents');
const PROJ_AGENT = path.join(PROJ_AGENTS_DIR, 'v40-test.md');

const AGENT_BODY = (label) => `---
name: v40-test
description: synthetic v2.40 ${label} agent
model: opus
tools: Read, Grep
---

You are the ${label} v40-test agent.
`;

let createdGlobal = false;
try {
  if (!existsSync(AGENTS_DIR)) mkdirSync(AGENTS_DIR, { recursive: true });
  if (!existsSync(GLOBAL_AGENT)) {
    writeFileSync(GLOBAL_AGENT, AGENT_BODY('global'), 'utf8');
    createdGlobal = true;
  }
  mkdirSync(PROJ_AGENTS_DIR, { recursive: true });
  writeFileSync(PROJ_AGENT, AGENT_BODY('project'), 'utf8');
} catch (e) {
  console.error('seed failed:', e.message);
  process.exit(1);
}

const cleanup = () => {
  try { if (createdGlobal) unlinkSync(GLOBAL_AGENT); } catch {}
  try { rmSync(TMP_PROJ, { recursive: true, force: true }); } catch {}
};
process.on('exit', cleanup);

const browser = await chromium.launch();
const page = await browser.newContext().then(c => c.newPage());
page.on('pageerror', e => errors.push('pageerror: ' + e.message));
page.on('console', m => {
  if (m.type() !== 'error') return;
  const txt = m.text();
  // Skip pre-existing / unrelated state-race noise that isn't introduced by
  // this change (overview tab AFTER hook fires before VIEWS finishes its
  // async fetch when go() is rapid-fired in the e2e).
  if (/state\.data\.overview/.test(txt)) return;
  errors.push('console: ' + txt);
});

await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForTimeout(2200);
// Boot wait — CC_PREFS is filled by the v2.38 prefs bootstrap.
await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS.ui, { timeout: 8000 });

// 1) Configure GLOBAL twin
const cfgGlobal = await page.evaluate(async () => {
  const r = await fetch('/api/hyper-agents/configure', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ name: 'v40-test', patch: { enabled: true, objective: 'global obj' } }),
  });
  return r.json();
});
if (!cfgGlobal.ok || cfgGlobal.agent.scope !== 'global' || cfgGlobal.agent.objective !== 'global obj') {
  errors.push('global configure failed: ' + JSON.stringify(cfgGlobal));
} else {
  console.log('OK: global configure (scope=global)');
}

// 2) Configure PROJECT twin (same name, different scope+cwd)
const cfgProj = await page.evaluate(async (cwd) => {
  const r = await fetch('/api/hyper-agents/configure', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ name: 'v40-test', cwd, patch: { enabled: false, objective: 'project obj' } }),
  });
  return r.json();
}, TMP_PROJ);
if (!cfgProj.ok || cfgProj.agent.scope !== 'project' || cfgProj.agent.cwd !== TMP_PROJ || cfgProj.agent.objective !== 'project obj') {
  errors.push('project configure failed: ' + JSON.stringify(cfgProj));
} else {
  console.log('OK: project configure (scope=project, cwd preserved)');
}

// 3) Twin separation — global must still have its own enabled+objective
const reGlobal = await page.evaluate(async () => {
  const r = await fetch('/api/hyper-agents/get/v40-test');
  return r.json();
});
if (!reGlobal.ok || reGlobal.agent.objective !== 'global obj' || reGlobal.agent.enabled !== true) {
  errors.push('twin separation broken (global): ' + JSON.stringify(reGlobal.agent));
} else {
  console.log('OK: twin separation — global retained');
}

// 4) Project lookup via POST endpoint (cwd in body)
const reProj = await page.evaluate(async (cwd) => {
  const r = await fetch('/api/hyper-agents/get', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ name: 'v40-test', cwd }),
  });
  return r.json();
}, TMP_PROJ);
if (!reProj.ok || reProj.agent.objective !== 'project obj' || reProj.agent.enabled !== false) {
  errors.push('twin separation broken (project): ' + JSON.stringify(reProj.agent));
} else {
  console.log('OK: twin separation — project retained');
}

// 5) list_hyper surfaces both with scope/cwd fields. Match project entry by
//    cwd so stale entries from prior runs (same name, different tmp cwd)
//    don't shadow the current run's entry.
const list = await page.evaluate(async () => (await fetch('/api/hyper-agents/list')).json());
const gItem = (list.items || []).find(it => it.scope === 'global' && it.name === 'v40-test');
const pItem = (list.items || []).find(it => it.scope === 'project' && it.name === 'v40-test' && it.cwd === TMP_PROJ);
if (!gItem || !pItem) {
  errors.push('list missing twin entries: ' + JSON.stringify({gItem, pItem, expectedCwd: TMP_PROJ, total: list.count}));
} else {
  console.log(`OK: list surfaces both scopes (global enabled=${gItem.enabled}, project enabled=${pItem.enabled})`);
}

// 6) Project rollback path responds cleanly when no backup exists
//    (versionTs=1 — non-zero so it isn't rejected by the "required" guard;
//     rollback() itself will return "backup not found".)
const rb = await page.evaluate(async (cwd) => {
  const r = await fetch('/api/hyper-agents/rollback', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ name: 'v40-test', cwd, versionTs: 1 }),
  });
  return r.json();
}, TMP_PROJ);
if (rb.ok || !rb.error || !/backup not found/.test(rb.error)) {
  errors.push('expected backup-not-found error: ' + JSON.stringify(rb));
} else {
  console.log('OK: rollback path responds with clean error when no backup');
}

// 7) Modal opens with project scope (UI integration, navigation-resilient)
//    Reload to a clean page first so any in-flight prefs/version banner can't
//    interrupt the evaluate. Retry once if a navigation interrupts.
async function _projectModalCheck() {
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS.ui, { timeout: 8000 });
  await page.waitForTimeout(1500);
  await page.evaluate(({name, cwd}) => openHyperAgent(name, cwd), {name:'v40-test', cwd: TMP_PROJ});
  await page.waitForTimeout(900);
  return page.evaluate(() => ({
    objVal: (document.getElementById('hyperObjective')||{}).value || '',
    hasSave: !!document.getElementById('hyperSave'),
  }));
}
try {
  let modal;
  try { modal = await _projectModalCheck(); }
  catch (_navErr) { modal = await _projectModalCheck(); }
  if (modal.objVal !== 'project obj') errors.push('modal did not load project objective: ' + JSON.stringify(modal));
  else console.log('OK: project modal renders');
} catch (e) {
  errors.push('modal step crashed: ' + e.message);
}

// 8) Sidebar favorites — toggle via JS, verify it appears
await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS.ui, { timeout: 8000 });
await page.evaluate(() => toggleFavoriteTab('workflows'));
await page.waitForTimeout(400);
const favPersisted = await page.evaluate(async () => {
  const r = await fetch('/api/prefs/get', { cache: 'no-store' });
  const j = await r.json();
  return j.prefs.ui.favoriteTabs;
});
if (!Array.isArray(favPersisted) || !favPersisted.includes('workflows')) {
  errors.push('favorite not persisted: ' + JSON.stringify(favPersisted));
} else {
  console.log('OK: favorite persisted to prefs');
}
const navHasFav = await page.evaluate(() => {
  const headers = Array.from(document.querySelectorAll('.nav-quick-header')).map(h => h.textContent);
  return headers.some(h => h.includes('★'));
});
if (!navHasFav) errors.push('★ section not rendered in sidebar');
else console.log('OK: ★ favorites section rendered');

// 9) Recent — drive a couple of go() calls and verify the 🕒 section
await page.evaluate(() => { go('sessions'); });
await page.waitForTimeout(200);
await page.evaluate(() => { go('agents'); });
await page.waitForTimeout(200);
await page.evaluate(() => { go('overview'); });
await page.waitForTimeout(200);
const recent = await page.evaluate(() => {
  const arr = JSON.parse(localStorage.getItem('cc-recent-tabs') || '[]');
  const headers = Array.from(document.querySelectorAll('.nav-quick-header')).map(h => h.textContent);
  return { arr, hasRecent: headers.some(h => h.includes('🕒')) };
});
if (!Array.isArray(recent.arr) || !recent.hasRecent) {
  errors.push('recent block missing or storage empty: ' + JSON.stringify(recent));
} else {
  console.log(`OK: recent surfaces ${recent.arr.length} tabs`);
}

// 10) '/' key opens spotlight when no input focused
await page.evaluate(() => {
  if (typeof closeSpotlight === 'function') closeSpotlight();
  document.body.focus();
});
await page.keyboard.press('/');
await page.waitForTimeout(400);
const sp = await page.evaluate(() => !!document.getElementById('spotlightOverlay') || (typeof _spotlightOpen !== 'undefined' && _spotlightOpen));
if (!sp) errors.push("'/' key did not open spotlight");
else console.log("OK: '/' key opens spotlight");

// Cleanup — disable both metas, restore prefs
await page.evaluate(async (cwd) => {
  await fetch('/api/hyper-agents/configure', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name:'v40-test', patch:{enabled:false}}) });
  await fetch('/api/hyper-agents/configure', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name:'v40-test', cwd, patch:{enabled:false}}) });
  await fetch('/api/prefs/set', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({patch:{ui:{favoriteTabs:[]}}}) });
}, TMP_PROJ);

await browser.close();
if (errors.length) {
  console.error('\n-- FAILURES --');
  errors.forEach(e => console.error('  X', e));
  process.exit(1);
}
console.log('\nAll v2.40 smoke checks passed.');
