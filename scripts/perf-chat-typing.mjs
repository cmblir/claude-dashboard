#!/usr/bin/env node
/**
 * Chat composer typing latency profile.
 *
 * Seeds a session with 120 messages (mixed user/assistant, varied length),
 * navigates to lazyclawChat, then types 80 characters into the input
 * one at a time and counts long tasks. Establishes a baseline for the
 * "typing feels laggy when chat history is huge" complaint.
 */
import { chromium } from 'playwright';

const URL = process.env.URL || `http://127.0.0.1:${process.env.PORT || 8080}/`;

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
await page.addInitScript(() => {
  window.__perfTasks = [];
  try { new PerformanceObserver(l => l.getEntries().forEach(e => window.__perfTasks.push(e.duration))).observe({type:'longtask',buffered:true}); } catch(_){}
});
await page.goto(URL, { waitUntil: 'networkidle' });
// Seed history.
await page.evaluate(() => {
  const sid = 'perf-typing';
  _lcSaveSessions([{ id: sid, label: 'perf', ts: Date.now(), preview: '' }]);
  const hist = [];
  for (let i = 0; i < 120; i++) {
    hist.push({
      role: i % 2 === 0 ? 'user' : 'assistant',
      text: `Message ${i}: ` + 'lorem ipsum dolor sit amet '.repeat(8 + (i % 5)),
      assignee: 'claude:opus',
      ts: Date.now() - (120 - i) * 60_000,
    });
  }
  _lcSaveHistory(sid, hist);
  _lcSetCurrentId(sid);
});
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });
await page.waitForTimeout(800);
const histLen = await page.evaluate(() => (_lcGetHistory(_lcCurrentId()) || []).length);
console.log('seeded history length:', histLen);

// Reset task buffer.
await page.evaluate(() => { window.__perfTasks = []; });

// Type 80 characters one-at-a-time with a small delay so input handlers
// fire individually.
await page.click('#lcChatInput');
const sample = 'Hello world this is a sample message to profile typing latency in a long chat session';
for (const ch of sample.slice(0, 80)) {
  await page.keyboard.type(ch, { delay: 12 });
}
await page.waitForTimeout(400);

const r = await page.evaluate(() => ({
  tasks: window.__perfTasks.slice(),
  inputLen: (document.getElementById('lcChatInput') || {}).value?.length || 0,
}));
const total = r.tasks.reduce((s, x) => s + x, 0);
const longest = r.tasks.length ? Math.max(...r.tasks).toFixed(0) : '0';
console.log(`input length: ${r.inputLen} chars`);
console.log(`longtasks during typing: ${r.tasks.length} · total: ${total.toFixed(0)}ms · longest: ${longest}ms`);

await browser.close();
