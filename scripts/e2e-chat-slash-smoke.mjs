#!/usr/bin/env node
/**
 * QQ178 — comprehensive smoke for every chat slash command. Runs each
 * verb once with sensible args and verifies _lcChatSlashCommand returns
 * `true` (handled) and the chat tab is still alive after every call.
 *
 * Catches:
 *   - a regression where a verb throws and breaks subsequent commands
 *   - a verb that silently returns false (forgot to add to switch)
 *   - a verb that mangles the chat DOM beyond recovery
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

await page.addInitScript(() => { window.confirm = () => true; });
await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

// Seed with one session containing a fake assistant message that has
// a code block + token meta — so /cost, /code, /copy all have inputs.
await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  _lcSaveHistory(_lcCurrentId(), [
    { role: 'user', text: 'do thing', ts: 1, assignee: 'claude:opus' },
    { role: 'assistant',
      text: 'Sure!\n\n```js\nconst x = 42;\n```\n\nThat\'s it.',
      ts: 2, assignee: 'claude:opus',
      tokensIn: 10, tokensOut: 5, costUsd: 0.001 },
  ]);
  _lcChatRender();
});

// Verbs to smoke. Pick args that are safe (non-destructive) where possible.
const cases = [
  ['/help', 'help'],
  ['/cost', 'cost'],
  ['/status', 'status'],
  ['/agents', 'agents'],
  ['/sessions', 'sessions'],
  ['/system', 'system show'],
  ['/system Be helpful.', 'system set'],
  ['/code', 'code'],
  ['/copy', 'copy'],
  ['/copy 1', 'copy N'],
  ['/version', 'version'],
  ['/tabs', 'tabs'],
  ['/code 1', 'code N'],
  // Note: /clear, /clear all, /go, /lang, /theme, /retry have side effects
  //       that would break subsequent runs in this single-tab smoke; they
  //       have dedicated regressions instead.
];

for (const [line, label] of cases) {
  const r = await page.evaluate((l) => _lcChatSlashCommand(l), line);
  const stillAlive = await page.evaluate(() => !!document.getElementById('lcChatLog'));
  check(`${label.padEnd(12)} returns true + DOM intact`,
    r === true && stillAlive, `r=${r} alive=${stillAlive}`);
}

// /rename to a known marker; verify it took.
await page.evaluate(() => _lcChatSlashCommand('/rename SmokeMarker-XYZ'));
await page.waitForTimeout(120);
const lbl = await page.evaluate(() => {
  const id = _lcCurrentId();
  return _lcGetSessions().find(s => s.id === id)?.label;
});
check('/rename took effect', lbl === 'SmokeMarker-XYZ', `label=${lbl}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
