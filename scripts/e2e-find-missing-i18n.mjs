#!/usr/bin/env node
/**
 * 미번역 탐지 — zh/en 로 언어 전환 후 화면에 남아있는 한국어/번역누락 텍스트 수집.
 * - zh 모드에서 한국어 텍스트가 보이면 = zh 번역 누락
 * - en 모드에서 한국어 텍스트가 보이면 = en 번역 누락
 * - zh 모드에서 사이드바 카테고리 라벨이 영어면 = short/label 키 누락
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE || `http://127.0.0.1:${process.env.PORT || 8080}`;
const HEADLESS = process.env.HEADLESS !== '0';

const browser = await chromium.launch({ headless: HEADLESS });

const KO_RE = /[가-힣]/;

async function scan(lang) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${BASE}/?lang=${lang}`, { waitUntil: 'networkidle' });
  // gate 가 뜰 때까지 최대 5초 대기 (auth.status 비동기 응답 후 렌더)
  try { await page.waitForSelector('#gateContinueBtn', { timeout: 5000 }); } catch {}
  const gateBtn = await page.$('#gateContinueBtn');
  if (gateBtn) { await gateBtn.click(); }
  // sidebar 가 display:'' 으로 복원될 때까지 + nav 렌더 완료 대기
  await page.waitForFunction(() => {
    const sb = document.getElementById('sidebar');
    return sb && getComputedStyle(sb).display !== 'none' && document.querySelectorAll('.nav-category').length >= 6;
  }, { timeout: 8000 });
  await page.waitForTimeout(700);  // i18n 치환 완료

  // 스크린샷 (expanded)
  await page.screenshot({ path: `/tmp/sidebar-${lang}.png`, clip: { x: 0, y: 0, width: 280, height: 800 } });
  // 스크린샷 (collapsed)
  await page.evaluate(() => document.body.classList.add('sb-collapsed'));
  await page.waitForTimeout(300);
  await page.screenshot({ path: `/tmp/sidebar-${lang}-collapsed.png`, clip: { x: 0, y: 0, width: 110, height: 500 } });
  await page.evaluate(() => document.body.classList.remove('sb-collapsed'));
  await page.waitForTimeout(200);

  // 사이드바 카테고리 라벨 수집
  const navLabels = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('.nav-category')).map(c => ({
      id: c.dataset.cat,
      full: c.querySelector('.nav-cat-label-full')?.textContent,
      short: c.querySelector('.nav-cat-label-short')?.textContent,
      desc: c.querySelector('.nav-cat-desc')?.textContent,
      title: c.getAttribute('title'),
    }));
  });

  // flyout 까지 열어서 sub-tab 라벨 수집
  const subLabels = await page.evaluate(() => {
    document.querySelectorAll('.nav-category').forEach(c => c.classList.add('open'));
    const items = [];
    document.querySelectorAll('.nav-flyout .nav-item').forEach(el => {
      items.push({
        label: el.querySelector('.nav-label > div')?.textContent,
        desc: el.querySelector('.nav-desc')?.textContent,
      });
    });
    document.querySelectorAll('.nav-category').forEach(c => c.classList.remove('open'));
    return items;
  });

  // 전체 body 에서 한국어 텍스트 노드 스캔 (ko 모드 외에서는 번역 누락)
  const koLeaks = lang !== 'ko' ? await page.evaluate(() => {
    const out = [];
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
    let n;
    while ((n = w.nextNode())) {
      const t = (n.textContent||'').trim();
      if (!t) continue;
      if (/[가-힣]/.test(t)) {
        out.push({ text: t.slice(0, 80), parent: n.parentElement?.tagName + '.' + (n.parentElement?.className||'').slice(0,40) });
      }
    }
    return out.slice(0, 50);  // 과다 방지
  }) : [];

  // placeholder/title/aria-label 속성에서 한국어 누수
  const attrLeaks = lang !== 'ko' ? await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('[placeholder],[title],[aria-label]').forEach(el => {
      ['placeholder','title','aria-label'].forEach(attr => {
        const v = el.getAttribute(attr);
        if (v && /[가-힣]/.test(v)) {
          out.push({ tag: el.tagName, attr, v: v.slice(0,80) });
        }
      });
    });
    return out.slice(0, 30);
  }) : [];

  console.log(`\n========== ${lang.toUpperCase()} ==========`);
  console.log('\n[nav category labels]');
  navLabels.forEach(l => console.log(`  ${l.id}: full="${l.full}" short="${l.short}" desc="${l.desc}"`));
  console.log(`\n[sub-tabs in flyouts] — ${subLabels.length} items`);
  const badSub = subLabels.filter(s => {
    const text = (s.label||'') + ' ' + (s.desc||'');
    if (lang === 'ko') return !KO_RE.test(s.label || '');
    return KO_RE.test(text);
  });
  badSub.slice(0,20).forEach(s => console.log(`  ⚠️ label="${s.label}" desc="${(s.desc||'').slice(0,60)}"`));
  if (lang !== 'ko') {
    console.log(`\n[텍스트 노드 한국어 누수] ${koLeaks.length} 건`);
    koLeaks.forEach(l => console.log(`  ⚠️ "${l.text}" (${l.parent})`));
    console.log(`\n[속성 한국어 누수] ${attrLeaks.length} 건`);
    attrLeaks.forEach(l => console.log(`  ⚠️ ${l.tag}[${l.attr}]: "${l.v}"`));
  }

  await page.close();
  return { navLabels, subLabels, koLeaks, attrLeaks };
}

const ko = await scan('ko');
const en = await scan('en');
const zh = await scan('zh');

await browser.close();
