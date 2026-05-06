#!/usr/bin/env node
/**
 * Chat with 1000 messages stress test.
 *
 * Seeds a session with 1000 mixed user/assistant messages of realistic
 * length, navigates to lazyclawChat, measures:
 *   - first render time of the chat log (ms)
 *   - scroll latency (mousewheel for 2 seconds)
 *   - typing latency (50 chars typed)
 *   - re-render time (delete first message → triggers full _lcChatRender)
 */
import { chromium } from 'playwright';

const URL = process.env.URL || `http://127.0.0.1:${process.env.PORT || 8080}/`;
const N = parseInt(process.env.N || '1000', 10);

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
await page.addInitScript(() => {
  window.__perfTasks = [];
  try { new PerformanceObserver(l => l.getEntries().forEach(e => window.__perfTasks.push(e.duration))).observe({type:'longtask',buffered:true}); } catch(_){}
  let last = performance.now();
  window.__frames = 0;
  function tick() { window.__frames++; last = performance.now(); requestAnimationFrame(tick); }
  requestAnimationFrame(tick);
});
await page.goto(URL, { waitUntil: 'networkidle' });

// Seed history.
await page.evaluate((n) => {
  const sid = 'perf-1k';
  _lcSaveSessions([{ id: sid, label: 'perf-1k', ts: Date.now(), preview: '' }]);
  const hist = [];
  for (let i = 0; i < n; i++) {
    // Defeat the v3.68 LRU body-cache by sprinkling unique tokens
    // into every message — otherwise modulo-N text repeats produce
    // unrealistic cache hit rates for a stress baseline.
    const rnd = Math.random().toString(36).slice(2, 8);
    hist.push({
      role: i % 2 === 0 ? 'user' : 'assistant',
      text: `Message #${i} [${rnd}]: ` + 'lorem ipsum dolor '.repeat(8 + (i % 5)) + '\n```js\nfn(' + rnd + ')\n```',
      assignee: 'claude:opus',
      ts: Date.now() - (n - i) * 60_000,
    });
  }
  _lcSaveHistory(sid, hist);
  _lcSetCurrentId(sid);
}, N);

// Measure first render time.
await page.evaluate(() => { window.__perfTasks = []; });
const navT0 = Date.now();
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 10000 });
await page.waitForFunction(() => {
  const log = document.getElementById('lcChatLog');
  return log && log.children.length > 100;  // bubbles rendered
}, { timeout: 10000 });
const firstRender = Date.now() - navT0;
const firstRenderTasks = await page.evaluate(() => window.__perfTasks.slice());
const firstRenderTotal = firstRenderTasks.reduce((s, x) => s + x, 0);
const firstRenderLongest = firstRenderTasks.length ? Math.max(...firstRenderTasks) : 0;
console.log(`first render: ${firstRender}ms wall · ${firstRenderTotal.toFixed(0)}ms scripting · longest task ${firstRenderLongest.toFixed(0)}ms`);

// Scroll perf.
await page.evaluate(() => { window.__perfTasks = []; window.__frames = 0; });
const scrollT0 = Date.now();
const log = await page.$('#lcChatLog');
for (let i = 0; i < 8; i++) {
  await log.evaluate(el => el.scrollBy(0, 200));
  await page.waitForTimeout(200);
}
const scrollDur = Date.now() - scrollT0;
const scrollData = await page.evaluate(() => ({ frames: window.__frames, tasks: window.__perfTasks.slice() }));
const scrollTotal = scrollData.tasks.reduce((s, x) => s + x, 0);
const scrollFps = (scrollData.frames / (scrollDur / 1000)).toFixed(1);
console.log(`scroll 8x200px in ${scrollDur}ms · fps=${scrollFps} · scripting ${scrollTotal.toFixed(0)}ms across ${scrollData.tasks.length} longtasks`);

// Typing perf.
await page.click('#lcChatInput');
await page.evaluate(() => { window.__perfTasks = []; });
for (const ch of 'Hello world this is a stress-test typing latency probe.') {
  await page.keyboard.type(ch, { delay: 8 });
}
await page.waitForTimeout(200);
const typingTasks = await page.evaluate(() => window.__perfTasks.slice());
const typingTotal = typingTasks.reduce((s, x) => s + x, 0);
console.log(`typing 56 chars: scripting ${typingTotal.toFixed(0)}ms across ${typingTasks.length} longtasks`);

// Re-render via delete first message.
await page.evaluate(() => { window.__perfTasks = []; });
const reRenderT0 = await page.evaluate(() => performance.now());
await page.evaluate(() => {
  _lcDeleteMsg(_lcCurrentId(), 0);
});
const reRenderEnd = await page.evaluate(() => performance.now());
const reRenderTasks = await page.evaluate(() => window.__perfTasks.slice());
const reRenderTotal = reRenderTasks.reduce((s, x) => s + x, 0);
console.log(`delete-msg re-render: ${(reRenderEnd - reRenderT0).toFixed(0)}ms · scripting ${reRenderTotal.toFixed(0)}ms across ${reRenderTasks.length} longtasks`);

// Heap.
const heap = await page.evaluate(() => ((performance.memory && performance.memory.usedJSHeapSize) || 0) / 1048576);
console.log(`heap after 1000-msg session: ${heap.toFixed(1)} MB`);

await browser.close();
