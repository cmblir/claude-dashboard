// Render docs/logo/mascot.svg into PNG icons for the PWA manifest.
// Outputs: dist/icons/{icon-192.png, icon-512.png, icon-maskable-512.png, apple-touch-180.png}
//
// We use Playwright (already a devDependency) to keep zero extra deps.
// "maskable" wraps the mascot in a solid background so iOS / Android safe-zone
// cropping doesn't lose the ears.
import { chromium } from 'playwright';
import { mkdirSync, readFileSync, writeFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(here, '..');
const SVG = readFileSync(resolve(ROOT, 'docs/logo/mascot.svg'), 'utf-8');
const OUT = resolve(ROOT, 'dist/icons');
mkdirSync(OUT, { recursive: true });

// Build an HTML page with the SVG embedded centred on a coloured background.
function htmlFor({ size, padding = 0, bg = '#0a0a0a' }) {
  // The SVG ships with width/height attrs — strip and let CSS size it.
  const cleanSvg = SVG.replace(/width="\d+"/, '').replace(/height="\d+"/, '');
  const inner = size - padding * 2;
  return `<!doctype html><html><head><meta charset="utf-8"><style>
    html,body { margin:0; padding:0; width:${size}px; height:${size}px; background:${bg}; }
    .wrap { width:${size}px; height:${size}px; display:flex; align-items:center; justify-content:center; }
    .wrap > svg { width:${inner}px; height:${inner}px; }
  </style></head><body><div class="wrap">${cleanSvg}</div></body></html>`;
}

const VARIANTS = [
  { name: 'icon-192.png',          size: 192, padding: 12, bg: '#0a0a0a' },
  { name: 'icon-512.png',          size: 512, padding: 32, bg: '#0a0a0a' },
  // Maskable: the safe area is the inner 80%. Pad more so the mascot's ears
  // and arms don't get cropped off by Android's adaptive icon mask.
  // Dark background so the orange mascot stands out; padding 80 px ⇒ ~70%
  // safe-zone usage which Maskable Hub flags as "good".
  { name: 'icon-maskable-512.png', size: 512, padding: 80, bg: '#1a1a1a' },
  // iOS apple-touch-icon — Apple insists on no transparency and no rounding
  // (iOS rounds it itself).
  { name: 'apple-touch-180.png',   size: 180, padding: 14, bg: '#0a0a0a' },
];

const browser = await chromium.launch({ headless: true });
for (const v of VARIANTS) {
  const ctx = await browser.newContext({ viewport: { width: v.size, height: v.size }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.setContent(htmlFor(v), { waitUntil: 'load' });
  const buf = await page.screenshot({ type: 'png', omitBackground: false });
  writeFileSync(resolve(OUT, v.name), buf);
  console.log(`wrote ${v.name} (${v.size}x${v.size})`);
  await ctx.close();
}
await browser.close();

// favicon.ico is referenced from existing notification code — generate a 32px PNG and
// also keep the .svg as a modern alternative.
{
  const ctx = await (await chromium.launch({ headless: true })).newContext({
    viewport: { width: 32, height: 32 }, deviceScaleFactor: 1,
  });
  // Wait — re-using the closed browser. Re-open quickly.
}
// Simpler: redo with a fresh browser for the favicon.
const b2 = await chromium.launch({ headless: true });
{
  const ctx = await b2.newContext({ viewport: { width: 32, height: 32 } });
  const page = await ctx.newPage();
  await page.setContent(htmlFor({ size: 32, padding: 1, bg: '#0a0a0a' }), { waitUntil: 'load' });
  writeFileSync(resolve(ROOT, 'dist/favicon-32.png'), await page.screenshot({ type: 'png' }));
  console.log('wrote favicon-32.png');
}
// Also drop the original SVG into dist for browsers that prefer a vector favicon.
writeFileSync(resolve(ROOT, 'dist/favicon.svg'), SVG);
console.log('wrote favicon.svg');
await b2.close();
console.log('done');
