// Playwright smoke for Quick Settings drawer.
// Verifies: prefs API boot · drawer renders · toggle persists · keyboard ⌘,
import { chromium } from 'playwright';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8080';
const errors = [];

const browser = await chromium.launch();
const ctx = await browser.newContext();
const page = await ctx.newPage();

page.on('pageerror', (err) => errors.push('pageerror: ' + err.message));
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push('console: ' + msg.text());
});

await page.goto(BASE, { waitUntil: 'networkidle' });

// Wait for the prefs boot fetch to complete
await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS.ui, { timeout: 8000 });

// 1) Open via keyboard ⌘,
await page.keyboard.press('Meta+Comma');
await page.waitForSelector('#qsDrawer.open', { timeout: 3000 });
console.log('OK: meta+comma opens drawer');

// 2) All five sections render (ui, ai, behavior, workflow, current)
const tabCount = await page.$$eval('.qs-tab', els => els.length);
if (tabCount !== 5) errors.push(`expected 5 tabs, got ${tabCount}`);
else console.log('OK: 5 section tabs');

// 3) Toggle a bool (autoResume — flip)
const before = await page.evaluate(() => window.CC_PREFS.behavior.autoResume);
await page.click('.qs-tab[data-section="behavior"]');
await page.waitForTimeout(150);
const toggle = await page.$('.qs-toggle[data-section="behavior"][data-key="autoResume"]');
if (!toggle) { errors.push('autoResume toggle not found'); }
else {
  await toggle.click();
  await page.waitForTimeout(450); // debounced flush
  const after = await page.evaluate(() => window.CC_PREFS.behavior.autoResume);
  if (after === before) errors.push(`autoResume did not flip: ${before} -> ${after}`);
  else console.log(`OK: autoResume flipped: ${before} -> ${after}`);
}

// 4) Server-side persistence
const persisted = await page.evaluate(async () => {
  const r = await fetch('/api/prefs/get', { cache: 'no-store' });
  const j = await r.json();
  return j.prefs.behavior.autoResume;
});
const expected = await page.evaluate(() => window.CC_PREFS.behavior.autoResume);
if (persisted !== expected) errors.push(`server mismatch: ${persisted} vs ${expected}`);
else console.log(`OK: server persisted: ${persisted}`);

// 5) Esc closes drawer
await page.keyboard.press('Escape');
await page.waitForTimeout(300);
const stillOpen = await page.$('#qsDrawer.open');
if (stillOpen) errors.push('drawer did not close on Esc');
else console.log('OK: Esc closes drawer');

// 6) AI section: range slider value updates
await page.keyboard.press('Meta+Comma');
await page.waitForSelector('#qsDrawer.open');
await page.click('.qs-tab[data-section="ai"]');
await page.waitForTimeout(150);
const tempSlider = await page.$('input[type="range"][data-section="ai"][data-key="temperature"]');
if (!tempSlider) errors.push('temperature slider not found');
else {
  await page.evaluate(() => {
    const el = document.querySelector('input[type="range"][data-section="ai"][data-key="temperature"]');
    el.value = '1.5'; el.dispatchEvent(new Event('input')); el.dispatchEvent(new Event('change'));
  });
  await page.waitForTimeout(400);
  const t2 = await page.evaluate(() => window.CC_PREFS.ai.temperature);
  if (Math.abs(t2 - 1.5) > 0.01) errors.push(`temperature mismatch: ${t2}`);
  else console.log(`OK: temperature -> ${t2}`);
}

// 7) Reset back to defaults
await page.evaluate(() => fetch('/api/prefs/reset', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' }));

await browser.close();

if (errors.length) {
  console.error('\n-- FAILURES --');
  errors.forEach(e => console.error('  X', e));
  process.exit(1);
}
console.log('\nAll Quick Settings smoke checks passed.');
