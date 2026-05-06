#!/usr/bin/env node
/**
 * Crew wizard — verify the QQ233 realistic-default seed runs and
 * replaces any hardcoded model that isn't backed by a real available
 * provider with one that is.
 */
import { chromium } from 'playwright';

const URL = process.env.URL || `http://127.0.0.1:${process.env.PORT || 8080}/`;
let exitCode = 0;
function check(label, ok, detail) {
  const tag = ok ? '\x1b[32m✅\x1b[0m' : '\x1b[31m❌\x1b[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
await page.goto(URL, { waitUntil: 'networkidle' });

// Snapshot the available providers so we know what the wizard should pick.
const provs = await page.evaluate(async () => {
  const r = await fetch('/api/ai-providers/list');
  const j = await r.json();
  const realistic = [];
  for (const p of (j.providers || [])) {
    if (!p.available) continue;
    for (const m of (p.models || []).slice(0, 2)) {
      realistic.push(`${p.id}:${m.id || m.name}`);
      if (realistic.length >= 6) break;
    }
    if (realistic.length >= 6) break;
  }
  return realistic;
});
check('we have at least one available provider:model', provs.length > 0, `count=${provs.length}`);

// Open crew wizard so the QQ233 seed runs.
await page.evaluate(() => window.go && window.go('crewWizard'));
await page.waitForFunction(() => state.view === 'crewWizard', { timeout: 8000 });
await page.waitForTimeout(700);

// Read the form state.
const form = await page.evaluate(() => ({
  plannerModel: __cw.form.plannerModel,
  personas: __cw.form.personas.map(p => p.model),
}));
check('planner model swapped to a real available assignee',
  provs.includes(form.plannerModel),
  `plannerModel=${form.plannerModel}`);
const realPersonas = form.personas.every(m => provs.includes(m));
check('every persona model is available',
  realPersonas,
  `personas=${JSON.stringify(form.personas)}`);

// Add a new persona — it should also pick a real model.
await page.evaluate(() => {
  // Skip to step 2 (personas) and trigger _cwRenderBody so the form mounts.
  __cw.step = 2;
  if (typeof _cwRenderBody === 'function') _cwRenderBody();
  if (typeof _cwBindFooter === 'function') _cwBindFooter();
});
await page.waitForTimeout(400);
const before = await page.evaluate(() => __cw.form.personas.length);
await page.evaluate(() => {
  const btn = document.getElementById('cw_addPersona');
  if (btn) btn.click();
});
await page.waitForTimeout(300);
const after = await page.evaluate(() => ({
  count: __cw.form.personas.length,
  lastModel: __cw.form.personas[__cw.form.personas.length - 1].model,
}));
check('add-persona picked a real available model',
  after.count === before + 1 && provs.includes(after.lastModel),
  `count ${before}→${after.count}, lastModel=${after.lastModel}`);

await browser.close();
console.log(exitCode === 0 ? '\nOK' : '\nFAIL');
process.exit(exitCode);
