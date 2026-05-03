#!/usr/bin/env node
/**
 * Light theme contrast audit.
 *
 * Iterates every tab in light theme, measures foreground/background for all
 * visible text elements, computes WCAG contrast ratio. Anything < 4.5 (AA)
 * is flagged with its selector path for batch CSS override.
 *
 * Usage:
 *   node scripts/e2e-light-contrast.mjs
 *   HEADLESS=0 node scripts/e2e-light-contrast.mjs
 *   TAB_ID=overview node scripts/e2e-light-contrast.mjs   # single tab
 */
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';

const BASE = process.env.BASE || `http://127.0.0.1:${process.env.PORT || 8080}`;
const HEADLESS = process.env.HEADLESS !== '0';
const ONLY = process.env.TAB_ID || null;
// WCAG 1.4.3 AA: 4.5 for body text, 3.0 for "large" text
// (≥24px regular OR ≥18.66px bold). The CONTRAST_MIN env still
// works as a hard floor override for both.
const HARD_FLOOR = parseFloat(process.env.CONTRAST_MIN || '0');

function readTabIds() {
  const src = readFileSync(new URL('../server/nav_catalog.py', import.meta.url), 'utf8');
  const idx = src.indexOf('TAB_CATALOG: list[tuple[');
  return [...src.slice(idx).matchAll(/^\s*\("([a-zA-Z][a-zA-Z0-9_]*)"\s*,/gm)].map(m => m[1]);
}

const browser = await chromium.launch({ headless: HEADLESS });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

await page.goto(BASE, { waitUntil: 'networkidle' });
try { await page.waitForSelector('#gateContinueBtn', { timeout: 5000 }); } catch {}
const gb = await page.$('#gateContinueBtn');
if (gb) await gb.click();
await page.waitForFunction(() => document.querySelectorAll('.nav-category').length >= 6, { timeout: 8000 });

// Light theme on
await page.evaluate(() => { if (typeof setTheme === 'function') setTheme('light'); });
await page.waitForTimeout(400);

const tabs = readTabIds();
const targets = ONLY ? tabs.filter(t => t === ONLY) : tabs;
console.log(`🎨 light-theme contrast audit: ${targets.length} tabs`);

function inject() {
  window.__contrastCheck = function(hardFloor) {
    function parseRGB(str) {
      const m = str.match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s]+([\d.]+))?/);
      if (!m) return null;
      return [parseInt(m[1]), parseInt(m[2]), parseInt(m[3]), m[4] ? parseFloat(m[4]) : 1];
    }
    function compositeOnWhite(fg, bg) {
      // Simple alpha composite — approximate effective color when bg is semi-transparent.
      if (!bg || bg[3] === 1) return bg || [255,255,255,1];
      const a = bg[3];
      return [
        Math.round(bg[0]*a + 255*(1-a)),
        Math.round(bg[1]*a + 255*(1-a)),
        Math.round(bg[2]*a + 255*(1-a)),
        1,
      ];
    }
    function luminance([r,g,b]) {
      const [R,G,B] = [r,g,b].map(v => {
        v /= 255;
        return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4);
      });
      return 0.2126*R + 0.7152*G + 0.0722*B;
    }
    function ratio(fg, bg) {
      const L1 = luminance(fg), L2 = luminance(bg);
      const [hi, lo] = L1 > L2 ? [L1, L2] : [L2, L1];
      return (hi + 0.05) / (lo + 0.05);
    }
    function effectiveBg(el) {
      // Walk up to find a non-transparent parent for effective bg color.
      let cur = el;
      while (cur && cur !== document.documentElement) {
        const cs = getComputedStyle(cur);
        const bg = parseRGB(cs.backgroundColor);
        if (bg && bg[3] > 0.01) return compositeOnWhite(null, bg);
        cur = cur.parentElement;
      }
      // Default light body fallback
      const bodyBg = parseRGB(getComputedStyle(document.body).backgroundColor);
      return bodyBg && bodyBg[3] > 0 ? compositeOnWhite(null, bodyBg) : [232,232,226,1];
    }
    const hits = [];
    const visited = new Set();
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT, null, false);
    let n;
    while ((n = walker.nextNode())) {
      if (!n.textContent || !n.textContent.trim()) continue;
      if (n.offsetParent === null) continue; // hidden
      // Only leaf-ish text-carrying elements
      const hasDirectText = Array.from(n.childNodes).some(c => c.nodeType === 3 && c.textContent.trim());
      if (!hasDirectText) continue;
      if (n.closest('script,style,svg')) continue;
      const cs = getComputedStyle(n);
      const fg = parseRGB(cs.color);
      if (!fg) continue;
      const bg = effectiveBg(n);
      const r = ratio([fg[0],fg[1],fg[2]], [bg[0],bg[1],bg[2]]);
      // WCAG 1.4.3 AA: 4.5 for body text, 3.0 for "large" text
      // (≥24px regular OR ≥18.66px bold).
      const px = parseFloat(cs.fontSize) || 16;
      const w = parseInt(cs.fontWeight, 10) || 400;
      const isLarge = px >= 24 || (px >= 18.66 && w >= 700);
      const wcagThreshold = isLarge ? 3.0 : 4.5;
      const threshold = Math.max(wcagThreshold, hardFloor);
      if (r < threshold) {
        const sample = n.textContent.trim().slice(0, 50);
        const path = (function(el){ const p=[]; while(el && el.id!=='content' && p.length<4){ p.unshift(el.tagName+(el.className?'.'+String(el.className).split(' ')[0]:'')); el=el.parentElement; } return p.join('>'); })(n);
        // Dedupe by path + fg/bg
        const key = path + '|' + fg.slice(0,3).join(',') + '|' + bg.slice(0,3).join(',');
        if (!visited.has(key)) {
          visited.add(key);
          hits.push({
            ratio: r.toFixed(2),
            fg: `rgb(${fg[0]},${fg[1]},${fg[2]})`,
            bg: `rgb(${bg[0]},${bg[1]},${bg[2]})`,
            text: sample,
            path,
            fontSize: cs.fontSize,
            fontWeight: cs.fontWeight,
          });
        }
      }
    }
    return hits;
  };
}

await page.addInitScript(inject);
await page.reload({ waitUntil: 'networkidle' });
try { await page.waitForSelector('#gateContinueBtn', { timeout: 5000 }); } catch {}
const gb2 = await page.$('#gateContinueBtn');
if (gb2) await gb2.click();
await page.waitForFunction(() => document.querySelectorAll('.nav-category').length >= 6, { timeout: 8000 });
await page.evaluate(() => { if (typeof setTheme === 'function') setTheme('light'); });
await page.waitForTimeout(500);

const totalHits = {};
for (const id of targets) {
  await page.evaluate((t) => { location.hash = '#/' + t; }, id);
  await page.waitForTimeout(700);
  try {
    const hits = await page.evaluate((th) => window.__contrastCheck(th), HARD_FLOOR);
    if (hits.length) totalHits[id] = hits;
  } catch (e) {
    console.log(`[${id}] eval failed: ${e.message}`);
  }
}

// Summarize
console.log(`\n==== Contrast audit (light theme, WCAG AA — 4.5 body / 3.0 large${HARD_FLOOR ? `, hard floor=${HARD_FLOOR}` : ''}) ====\n`);
const tabEntries = Object.entries(totalHits);
console.log(`Tabs with violations: ${tabEntries.length} / ${targets.length}`);
let total = 0;
for (const [tab, hits] of tabEntries) {
  total += hits.length;
  console.log(`\n[${tab}] ${hits.length} issues`);
  for (const h of hits.slice(0, 8)) {
    console.log(`  ratio=${h.ratio} fg=${h.fg} bg=${h.bg} ${h.fontSize}/${h.fontWeight}  "${h.text}"  ${h.path}`);
  }
  if (hits.length > 8) console.log(`  ... +${hits.length - 8} more`);
}
console.log(`\nTotal violations: ${total}`);

// aggregate by (fg, bg) — find top colors to batch-fix
const byColor = {};
for (const hits of Object.values(totalHits)) {
  for (const h of hits) {
    const k = h.fg + ' on ' + h.bg;
    (byColor[k] = byColor[k] || []).push(h);
  }
}
const topColors = Object.entries(byColor).sort((a,b) => b[1].length - a[1].length).slice(0, 10);
console.log(`\n==== Top color pairs (for batch fix) ====`);
for (const [pair, arr] of topColors) {
  console.log(`  ${arr.length}x  ${pair}  (ratio=${arr[0].ratio})`);
}

await browser.close();
