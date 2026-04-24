#!/usr/bin/env node
/**
 * 사이드바 UX 실측 — v2.33.x
 *
 * 재현할 이슈:
 *  1) sb-collapsed 토글 후 복구 가능 여부
 *  2) 카테고리 hover → flyout 으로 마우스 이동 시 flyout 이 살아있는지
 *  3) collapsed 상태에서 아이콘이 어떤 기능인지 알 수 있는지 (title/aria-label)
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE || 'http://127.0.0.1:8080';
const HEADLESS = process.env.HEADLESS !== '0';

const browser = await chromium.launch({ headless: HEADLESS });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('pageerror', e => console.log('[pageerror]', e.message));

await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForTimeout(800);

// 로그인 게이트 건너뛰기
const gateBtn = await page.$('#gateContinueBtn');
if (gateBtn) {
  console.log('↪︎ 로그인 게이트 통과');
  await gateBtn.click();
  await page.waitForTimeout(600);
}
await page.waitForSelector('#sidebar', { state: 'visible', timeout: 5000 });

// ============== ISSUE 1: 사이드바 축소 → 복구 가능? ==============
console.log('\n=== ISSUE 1: 접기 → 펼치기 ===');
const sbToggleBefore = await page.evaluate(() => {
  const el = document.getElementById('sbToggle');
  if (!el) return 'missing';
  const cs = getComputedStyle(el);
  return `display=${cs.display}, visible=${el.offsetParent !== null}`;
});
console.log('[before] #sbToggle:', sbToggleBefore);

await page.click('#sbToggle');
await page.waitForTimeout(300);

const afterCollapse = await page.evaluate(() => {
  const isCollapsed = document.body.classList.contains('sb-collapsed');
  const sbToggle = document.getElementById('sbToggle');
  const navToggle = document.getElementById('navToggle');
  return {
    isCollapsed,
    sbToggleDisplay: sbToggle ? getComputedStyle(sbToggle).display : 'missing',
    sbToggleVisible: sbToggle ? sbToggle.offsetParent !== null : false,
    navToggleDisplay: navToggle ? navToggle.style.display : 'missing',
    navToggleVisible: navToggle ? navToggle.offsetParent !== null : false,
    navToggleRect: navToggle ? navToggle.getBoundingClientRect() : null,
  };
});
console.log('[after collapse]', afterCollapse);

// ============== ISSUE 2: hover → flyout 이동 간격 ==============
console.log('\n=== ISSUE 2: flyout hover 이동 ===');
// 원래 상태로 복구
await page.evaluate(() => { document.body.classList.remove('sb-collapsed'); });
await page.waitForTimeout(200);

const firstCat = await page.evaluate(() => {
  const cat = document.querySelector('.nav-category');
  if (!cat) return null;
  const r = cat.getBoundingClientRect();
  return { x: r.x + r.width/2, y: r.y + r.height/2, catId: cat.dataset.cat };
});
console.log('[첫 카테고리]', firstCat);

if (firstCat) {
  await page.mouse.move(firstCat.x, firstCat.y);
  await page.waitForTimeout(250);
  const flyoutBox = await page.evaluate(() => {
    const fl = document.querySelector('.nav-category:hover > .nav-flyout') ||
               document.querySelector('.nav-flyout');
    if (!fl) return null;
    const visible = getComputedStyle(fl).display !== 'none';
    const r = fl.getBoundingClientRect();
    const cat = fl.closest('.nav-category').getBoundingClientRect();
    return { visible, flRect: r, catRight: cat.right, gap: r.left - cat.right };
  });
  console.log('[flyout 첫 hover]', flyoutBox);

  if (flyoutBox && flyoutBox.visible) {
    // 카테고리 우측 → flyout 왼쪽으로 이동하며 중간 지점에서 flyout 살아있는지 체크
    const midX = flyoutBox.catRight + flyoutBox.gap / 2;
    const midY = firstCat.y;
    await page.mouse.move(midX, midY);
    await page.waitForTimeout(150);
    const midStatus = await page.evaluate(() => {
      const hoveredFlyout = document.querySelectorAll('.nav-category:hover > .nav-flyout');
      const anyOpen = document.querySelectorAll('.nav-flyout');
      let visibleCount = 0;
      anyOpen.forEach(f => { if (getComputedStyle(f).display !== 'none') visibleCount++; });
      return { hoveredFlyoutCount: hoveredFlyout.length, visibleFlyouts: visibleCount };
    });
    console.log('[mouse at gap 중간]', midStatus);

    // flyout 안으로 이동
    const flyoutInsideX = flyoutBox.flRect.left + 40;
    const flyoutInsideY = flyoutBox.flRect.top + 40;
    await page.mouse.move(flyoutInsideX, flyoutInsideY);
    await page.waitForTimeout(150);
    const insideStatus = await page.evaluate(() => {
      let visibleCount = 0;
      document.querySelectorAll('.nav-flyout').forEach(f => { if (getComputedStyle(f).display !== 'none') visibleCount++; });
      return { visibleFlyouts: visibleCount };
    });
    console.log('[mouse inside flyout]', insideStatus);
  }
}

// ============== ISSUE 3: collapsed 상태에서 아이콘 의미 ==============
console.log('\n=== ISSUE 3: collapsed 아이콘 접근성 ===');
await page.evaluate(() => { document.body.classList.add('sb-collapsed'); });
await page.waitForTimeout(200);
const accessInfo = await page.evaluate(() => {
  const cats = Array.from(document.querySelectorAll('.nav-category'));
  return cats.map(c => ({
    id: c.dataset.cat,
    title: c.getAttribute('title'),
    ariaLabel: c.getAttribute('aria-label'),
    hasIcon: !!c.querySelector('.nav-cat-icon'),
    iconChar: c.querySelector('.nav-cat-icon')?.textContent.trim(),
  }));
});
console.log('[nav-category 접근성]', JSON.stringify(accessInfo, null, 2));

// ============== REGRESSION: flyout 이 마우스 나가면 정상 종료 ==============
console.log('\n=== REGRESSION: flyout 닫힘 ===');
await page.evaluate(() => { document.body.classList.remove('sb-collapsed'); });
await page.waitForTimeout(200);
// 카테고리 → flyout 진입 → 바깥으로 나가기
const cat0 = await page.evaluate(() => {
  const c = document.querySelector('.nav-category');
  const r = c.getBoundingClientRect();
  return { x: r.x + r.width/2, y: r.y + r.height/2 };
});
await page.mouse.move(cat0.x, cat0.y);
await page.waitForTimeout(200);
// 바깥 (화면 중앙)
await page.mouse.move(900, 500);
await page.waitForTimeout(250);
const flyoutAfterLeave = await page.evaluate(() => {
  let vis = 0;
  document.querySelectorAll('.nav-flyout').forEach(f => { if (getComputedStyle(f).display !== 'none') vis++; });
  return { visibleFlyouts: vis };
});
console.log('[mouse 바깥]', flyoutAfterLeave);

// DEBUG: label states
const dbg = await page.evaluate(() => {
  document.body.classList.add('sb-collapsed');
  return Array.from(document.querySelectorAll('.nav-category')).map(c => {
    const full = c.querySelector('.nav-cat-label-full');
    const short = c.querySelector('.nav-cat-label-short');
    return {
      id: c.dataset.cat,
      fullText: full?.textContent,
      fullDisplay: full ? getComputedStyle(full).display : 'missing',
      shortText: short?.textContent,
      shortDisplay: short ? getComputedStyle(short).display : 'missing',
    };
  });
});
console.log('\n=== DEBUG: label display ===');
console.log(JSON.stringify(dbg, null, 2));

// ============== ISSUE 4: 복구 동작 확인 ==============
console.log('\n=== ISSUE 4: navToggle 로 복구 ===');
await page.click('#navToggle');
await page.waitForTimeout(250);
const restored = await page.evaluate(() => ({
  isCollapsed: document.body.classList.contains('sb-collapsed'),
  sidebarWidth: document.getElementById('sidebar').getBoundingClientRect().width,
}));
console.log('[after navToggle click]', restored);

// screenshot
await page.evaluate(() => { document.body.classList.add('sb-collapsed'); });
await page.waitForTimeout(200);
await page.screenshot({ path: '/tmp/sidebar-collapsed.png', fullPage: false, clip: { x: 0, y: 0, width: 120, height: 800 } });
console.log('\n→ /tmp/sidebar-collapsed.png 저장');
// expanded 스크린샷
await page.evaluate(() => { document.body.classList.remove('sb-collapsed'); });
await page.waitForTimeout(200);
await page.screenshot({ path: '/tmp/sidebar-expanded.png', fullPage: false, clip: { x: 0, y: 0, width: 280, height: 800 } });
console.log('→ /tmp/sidebar-expanded.png 저장');

await browser.close();
