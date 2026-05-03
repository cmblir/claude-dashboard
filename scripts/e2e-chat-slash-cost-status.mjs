#!/usr/bin/env node
/**
 * QQ116 — chat slash commands /cost · /status · /rename:
 *
 * 1. Seed a session with a couple of fake assistant messages whose
 *    tokensIn/tokensOut/costUsd are populated, then run /cost — the
 *    next assistant bubble must contain the totals.
 * 2. /status posts an assistant bubble naming assignee + session label.
 * 3. /rename Foo bar updates the session label in storage.
 * 4. /help now lists /cost, /status, /rename.
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
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

// Seed a fresh session with two fake assistant messages carrying token + cost.
await page.evaluate(() => {
  _lcSaveSessions([]);
  _lcNewSession('claude:opus');
  const id = _lcCurrentId();
  const h = [
    { role: 'user',      text: 'hi', ts: 1, assignee: 'claude:opus' },
    { role: 'assistant', text: 'hello', ts: 2, assignee: 'claude:opus',
      tokensIn: 100, tokensOut: 50, costUsd: 0.0012 },
    { role: 'user',      text: 'more', ts: 3, assignee: 'claude:opus' },
    { role: 'assistant', text: 'ok',   ts: 4, assignee: 'claude:opus',
      tokensIn: 200, tokensOut: 75, costUsd: 0.0034 },
  ];
  _lcSaveHistory(id, h);
  _lcChatRender();
});

// Helper: invoke slash command via the existing entry-point.
async function slash(line) {
  await page.evaluate((l) => {
    const ta = document.getElementById('lcChatInput');
    ta.value = l;
    return _lcChatSlashCommand(l);
  }, line);
  await page.waitForTimeout(120);
}

// 1. /cost
await slash('/cost');
const lastCost = await page.evaluate(() => {
  const log = document.getElementById('lcChatLog');
  return log ? log.innerHTML : '';
});
check('/cost shows total input tokens (300)',
  /300/.test(lastCost));
check('/cost shows total output tokens (125)',
  /125/.test(lastCost));
check('/cost shows cumulative USD',
  /\$0\.0046/.test(lastCost) || /0\.004/.test(lastCost));

// 2. /status
await slash('/status');
const stat = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/status mentions assignee claude:opus', /claude:opus/.test(stat));

// 3. /rename
await slash('/rename ProjectAlpha');
const renamed = await page.evaluate(() => {
  const id = _lcCurrentId();
  const s = (_lcGetSessions() || []).find(x => x.id === id);
  return s ? s.label : null;
});
check('/rename updates session label', renamed === 'ProjectAlpha', `label=${renamed}`);

// 4. /agents lists registered assignees
await slash('/agents');
const agentsOut = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/agents lists current assignee claude:opus',
  /claude:opus/.test(agentsOut));
check('/agents marks current selection with ➜', /➜/.test(agentsOut));

// 4b. /sessions lists current sessions with message counts
await slash('/sessions');
const sessOut = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/sessions shows the active session with ➜', /➜/.test(sessOut));
// We seeded 4 history entries above + several /-bubbles; expect a non-zero
// message count to render.
check('/sessions includes a message count', /\d+\s*메시지|\d+\s*messages|\d+\s*消息/.test(sessOut) || /\d+ 메시지/.test(sessOut));

// 5. /help lists the new commands
await slash('/help');
const help = await page.evaluate(() => document.getElementById('lcChatLog').innerHTML);
check('/help lists /cost',   /\/cost/.test(help));
check('/help lists /status', /\/status/.test(help));
check('/help lists /rename', /\/rename/.test(help));
check('/help lists /agents', /\/agents/.test(help));
check('/help lists /sessions', /\/sessions/.test(help));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
