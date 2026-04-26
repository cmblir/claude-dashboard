// Reproduce the small-screen flyout bug shown in the user's screenshot.
import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const BASE = process.env.BASE || 'http://127.0.0.1:19503';
const OUT = process.env.OUT || './scripts/_flyout-debug';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 670, height: 720 } });
  const page = await ctx.newPage();
  const consoleLines = [];
  page.on('console', m => consoleLines.push(`[${m.type()}] ${m.text()}`));

  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 25000 });
  await page.waitForTimeout(900);

  // Dismiss first-visit login gate if present
  await page.evaluate(() => {
    const cont = Array.from(document.querySelectorAll('button, a, [role="button"]'))
      .find(b => /Continue|시작|계속/i.test(b.textContent.trim()));
    if (cont) cont.click();
  });
  await page.waitForTimeout(700);

  // Diagnostic: pre-state
  const pre = await page.evaluate(() => ({
    isMobile: window.matchMedia('(max-width: 900px)').matches,
    navToggleDisplay: getComputedStyle(document.getElementById('navToggle')).display,
    sbToggleDisplay: getComputedStyle(document.getElementById('sbToggle')).display,
  }));
  console.log('PRE:', JSON.stringify(pre));

  // Click hamburger via JS (the button may be display:none-ed by sync logic)
  await page.evaluate(() => {
    if (typeof _toggleSidebar === 'function') _toggleSidebar();
    else document.getElementById('navToggle').click();
  });
  await page.waitForTimeout(350);
  await page.screenshot({ path: `${OUT}-1-sidebar-open.png` });

  // Click 학습 category (group=learn)
  await page.evaluate(() => {
    const cats = Array.from(document.querySelectorAll('.nav-category'));
    const learn = cats.find(c => /학습|learn/i.test(c.textContent));
    if (learn) learn.click();
  });
  await page.waitForTimeout(450);
  await page.screenshot({ path: `${OUT}-2-learn-open.png` });
  await page.screenshot({ path: `${OUT}-2-learn-open-fp.png`, fullPage: true });

  // Diagnostic dump
  const diag = await page.evaluate(() => {
    function dump(el) {
      if (!el) return null;
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return {
        tag: el.tagName, id: el.id || '', cls: (el.className+'').slice(0,140),
        rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
        position: cs.position, zIndex: cs.zIndex, display: cs.display,
        bg: cs.backgroundColor, overflow: cs.overflow,
      };
    }
    const sb = document.getElementById('sidebar');
    const isMobile = window.matchMedia('(max-width: 900px)').matches;
    const sidebarOpen = document.body.classList.contains('sidebar-open');
    const learnCat = Array.from(document.querySelectorAll('.nav-category')).find(c => /학습|learn/i.test(c.textContent));
    const flyout = learnCat?.querySelector('.nav-flyout');
    const beforeStyle = getComputedStyle(document.body, '::after');

    // Tab content visible behind?
    const view = document.getElementById('view');
    const viewRect = view ? view.getBoundingClientRect() : null;

    // Walk all elements and find any in the right half (>300px) with non-zero opacity
    const visibleRight = [];
    document.querySelectorAll('*').forEach(el => {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      if (r.width < 30 || r.height < 30) return;
      if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return;
      if (r.x > 320 && r.x < 600 && el.children.length === 0 && el.textContent.trim()) {
        visibleRight.push({ tag: el.tagName, txt: el.textContent.trim().slice(0,40), x: Math.round(r.x), y: Math.round(r.y) });
      }
    });

    return {
      isMobile,
      sidebarOpen,
      sidebar: dump(sb),
      learnCat: dump(learnCat),
      flyout: dump(flyout),
      bodyAfterContent: beforeStyle.content,
      bodyAfterDisplay: beforeStyle.display,
      bodyAfterZ: beforeStyle.zIndex,
      bodyAfterBg: beforeStyle.backgroundColor,
      bodyAfterPos: beforeStyle.position,
      view: dump(view),
      visibleRightSample: visibleRight.slice(0, 12),
      vw: innerWidth, vh: innerHeight,
    };
  });

  writeFileSync(`${OUT}-diag.json`, JSON.stringify({ diag, console: consoleLines.slice(-20) }, null, 2));
  console.log(JSON.stringify(diag, null, 2));

  await browser.close();
})();
