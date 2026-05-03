#!/usr/bin/env node
/**
 * QQ150 — `lazyclaude diag` re-runs the CLI health check on demand.
 * The same code path that auto-fires once per hour on first terminal
 * tab visit, but reachable from the keyboard so users can re-probe
 * after installing/updating a CLI without waiting for the 1-hour gate.
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
await page.evaluate(() => window.go && window.go('lazyclawTerm'));
await page.waitForSelector('#lcTermInput', { timeout: 8000 });
// Wait for the auto-fire healthcheck (if any) to settle.
await page.waitForTimeout(2200);

// Clear log so we can see the diag run cleanly.
await page.evaluate(() => {
  try { localStorage.removeItem('cc.lazyclawTerm.log'); } catch (_) {}
  document.getElementById('lcTermLog').innerHTML = '';
});

// Run diag
await page.evaluate(() => {
  const inp = document.getElementById('lcTermInput');
  inp.value = 'lazyclaude diag';
  return window._lcTermRun();
});

// Healthcheck takes a couple seconds to settle (subprocess fan-out).
// Wait for the closing "헬스체크 완료" line.
await page.waitForFunction(() => {
  const log = document.getElementById('lcTermLog');
  return log && /헬스체크 완료|health.?check.*complete/i.test(log.textContent || '');
}, { timeout: 15000 });

const summary = await page.evaluate(() => {
  const log = document.getElementById('lcTermLog');
  const txt = log ? log.textContent : '';
  return {
    hasStart:   /헬스체크 시작|health.?check/i.test(txt),
    hasEnd:     /헬스체크 완료|health.?check.*complete/i.test(txt),
    hasClaude:  /claude --version/.test(txt),
    hasOllama:  /ollama list/.test(txt),
    hasGit:     /git status/.test(txt),
  };
});

check('diag prints health-check START line', summary.hasStart);
check('diag prints health-check END line',   summary.hasEnd);
check('diag probed claude --version',        summary.hasClaude);
check('diag probed ollama list',             summary.hasOllama);
check('diag probed git status -sb',          summary.hasGit);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
