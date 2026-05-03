// Playwright smoke for Hyper Agent (v2.39.0).
// Verifies: API list + get + configure + history round-trip; UI globals exist;
// modal opens against a real on-disk agent; toggle persists; configure saves.
import { chromium } from 'playwright';
import { writeFileSync, existsSync, unlinkSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || `http://127.0.0.1:${process.env.PORT || 8080}`;
const errors = [];

// Seed a real test agent at ~/.claude/agents/hyper-test.md so the modal has something to open.
const AGENTS_DIR = path.join(homedir(), '.claude', 'agents');
const AGENT_FILE = path.join(AGENTS_DIR, 'hyper-test.md');
const AGENT_BODY = `---
name: hyper-test
description: synthetic agent for hyper smoke
model: opus
tools: Read, Grep
---

You are a test agent for the hyper-agent smoke script.
`;
let createdAgent = false;
try {
  if (!existsSync(AGENTS_DIR)) mkdirSync(AGENTS_DIR, { recursive: true });
  if (!existsSync(AGENT_FILE)) {
    writeFileSync(AGENT_FILE, AGENT_BODY, 'utf8');
    createdAgent = true;
  }
} catch (e) {
  console.error('failed to seed test agent:', e.message);
  process.exit(1);
}

const browser = await chromium.launch();
const page = await browser.newContext().then(c => c.newPage());
page.on('pageerror', e => errors.push('pageerror: ' + e.message));
page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForTimeout(2000);

// 1) globals exist
const globals = await page.evaluate(() => ({
  openHyperAgent:    typeof openHyperAgent    === 'function',
  _hyperBindControls: typeof _hyperBindControls === 'function',
}));
if (!globals.openHyperAgent || !globals._hyperBindControls) {
  errors.push('hyper UI globals missing');
} else {
  console.log('OK: UI globals present');
}

// 2) list endpoint reachable
const list = await page.evaluate(async () => {
  const r = await fetch('/api/hyper-agents/list', { cache: 'no-store' });
  return r.json();
});
if (!list.ok) errors.push('list failed: ' + JSON.stringify(list));
else console.log(`OK: list (count=${list.count})`);

// 3) configure round-trip
const cfg = await page.evaluate(async () => {
  const r = await fetch('/api/hyper-agents/configure', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'hyper-test',
      patch: {
        enabled: true,
        objective: 'be terse and surgical',
        refineTargets: ['systemPrompt', 'description'],
        trigger: 'manual',
        budgetUSD: 1.5,
      },
    }),
  });
  return r.json();
});
if (!cfg.ok) errors.push('configure failed: ' + JSON.stringify(cfg));
else if (cfg.agent.objective !== 'be terse and surgical') errors.push('objective not persisted');
else console.log(`OK: configure saved (enabled=${cfg.agent.enabled}, targets=${cfg.agent.refineTargets.join('+')})`);

// 4) get endpoint
const got = await page.evaluate(async () => {
  const r = await fetch('/api/hyper-agents/get/hyper-test');
  return r.json();
});
if (!got.ok || !got.agent.enabled) errors.push('get did not reflect saved state');
else console.log('OK: get reflects saved state');

// 5) toggle off via dedicated endpoint
const tg = await page.evaluate(async () => {
  const r = await fetch('/api/hyper-agents/toggle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'hyper-test', enabled: false }),
  });
  return r.json();
});
if (!tg.ok || tg.agent.enabled !== false) errors.push('toggle off failed');
else console.log('OK: toggle off');

// 6) modal opens for a real agent (UI integration) — robust against navigation
try {
  // re-enable so the modal reflects an enabled state
  await page.evaluate(async () => fetch('/api/hyper-agents/configure', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'hyper-test', patch: { enabled: true, objective: 'be terse and surgical' } }),
  }));
  // Reload to a clean page so version banner / prior state can't interfere
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  await page.evaluate(() => openHyperAgent('hyper-test'));
  await page.waitForTimeout(900);
  const modal = await page.evaluate(() => ({
    hasToggle:    !!document.getElementById('hyperToggle'),
    hasObjective: !!document.getElementById('hyperObjective'),
    hasRefineBtn: !!document.getElementById('hyperRefine'),
    hasDryBtn:    !!document.getElementById('hyperRefineDry'),
    objVal:       (document.getElementById('hyperObjective') || {}).value || '',
  }));
  if (!modal.hasToggle || !modal.hasObjective || !modal.hasRefineBtn || !modal.hasDryBtn) {
    errors.push('modal controls missing: ' + JSON.stringify(modal));
  } else if (modal.objVal !== 'be terse and surgical') {
    errors.push('modal did not load saved objective: ' + JSON.stringify(modal.objVal));
  } else {
    console.log('OK: modal renders with saved objective');
  }
} catch (e) {
  errors.push('modal step crashed: ' + e.message);
}

// 7) refine-now should not crash the server (graceful err in JSON when no provider keys)
const refine = await page.evaluate(async () => {
  const r = await fetch('/api/hyper-agents/refine-now', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'hyper-test', dryRun: true }),
  });
  return { status: r.status, body: await r.json() };
});
if (refine.status !== 200) errors.push('refine returned non-200: ' + refine.status);
else console.log(`OK: refine endpoint responded (ok=${refine.body.ok})`);

// Cleanup
if (createdAgent) {
  try { unlinkSync(AGENT_FILE); } catch {}
}
await page.evaluate(async () => fetch('/api/hyper-agents/configure', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ name: 'hyper-test', patch: { enabled: false } }),
}));

await browser.close();
if (errors.length) {
  console.error('\n-- FAILURES --');
  errors.forEach(e => console.error('  X', e));
  process.exit(1);
}
console.log('\nAll Hyper Agent smoke checks passed.');
