#!/usr/bin/env node
/**
 * QQ139 — the SessionEnd "dashboard reindex" hook preset hardcoded
 * http://127.0.0.1:8080 in its command. Anyone running the dashboard
 * on a non-default port who installed the preset would silently lose
 * the reindex on session end. The command now uses `location.origin`
 * captured when app.js loads.
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

const probe = await page.evaluate(() => {
  const p = (_HOOK_PRESETS || []).find(x => x.id === 'session-end-save');
  return p ? { command: p.command, origin: location.origin } : null;
});

check('session-end-save preset exists', !!probe);
check('preset command no longer hardcodes 127.0.0.1:8080',
  probe && !probe.command.includes('127.0.0.1:8080'),
  `cmd=${(probe && probe.command || '').slice(0, 100)}`);
check(`preset command uses current origin (${probe && probe.origin})`,
  probe && probe.command.includes(probe.origin),
  `cmd=${(probe && probe.command || '').slice(0, 100)}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
