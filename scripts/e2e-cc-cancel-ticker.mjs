#!/usr/bin/env node
/** CC verify: workflow Execute/Cancel toggle + elapsed ticker.
 *
 *  Stubs SSE so the page sees a synthetic in-flight run; checks that
 *  (1) the run button flips to `중단` (Stop), (2) `.wfrb-meta-text`
 *  increments past its initial value within 2s.
 */
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.addInitScript(() => { localStorage.setItem('dashboard-entered', '1'); });
await page.goto('http://127.0.0.1:8080/#/workflows', { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);

// Inject a synthetic running run snapshot through _wfApplyRunStatus
const before = await page.evaluate(() => {
  if (typeof __wf === 'undefined') return { err: '__wf undef' };
  __wf.current = __wf.current || { id: 'cc-test', name: 'cc', nodes: [], edges: [],
                                    viewport: { panX:0, panY:0, zoom:1 } };
  __wf.runId = 'cc-fake';
  if (typeof _wfSetRunButtonState === 'function') _wfSetRunButtonState(true);
  const startedAt = Date.now() - 5000; // 5s ago
  const fakeRun = {
    runId: 'cc-fake', status: 'running',
    startedAt, nodeResults: {},
    currentNodeId: null,
  };
  if (typeof _wfApplyRunStatus !== 'function') return { err: 'no apply fn' };
  _wfApplyRunStatus(fakeRun);
  const btn = document.getElementById('wfRunBtn');
  const meta = document.querySelector('.wfrb-meta-text');
  return {
    btnText: btn ? btn.textContent.trim() : null,
    metaText: meta ? meta.textContent : null,
  };
});
console.log('initial:', before);

await page.waitForTimeout(2200);

const after = await page.evaluate(() => {
  const btn = document.getElementById('wfRunBtn');
  const meta = document.querySelector('.wfrb-meta-text');
  return {
    btnText: btn ? btn.textContent.trim() : null,
    metaText: meta ? meta.textContent : null,
  };
});
console.log('after 2.2s:', after);

const numBefore = before.metaText ? parseFloat((before.metaText.match(/(\d+(?:\.\d+)?)s/)||[])[1] || '0') : 0;
const numAfter  = after.metaText  ? parseFloat((after.metaText.match(/(\d+(?:\.\d+)?)s/)||[])[1]  || '0') : 0;

const btnOk = (after.btnText || '').includes('중단') || (after.btnText || '').toLowerCase().includes('stop');
const tickOk = numAfter > numBefore + 0.5; // ticker fires ~1Hz; allow jitter

if (!btnOk)  { console.log('FAIL: run button did not flip to stop label'); process.exit(2); }
if (!tickOk) { console.log(`FAIL: ticker did not increment (${numBefore}s → ${numAfter}s)`); process.exit(3); }

console.log('OK: btn flipped + ticker advanced', { numBefore, numAfter });
await browser.close();
