#!/usr/bin/env node
/**
 * README 용 스크린샷 자동 생성 (언어별, v2.23.2~).
 *
 * 대시보드 주요 탭을 3 언어(ko/en/zh) × 12 탭 = 36장 캡처해
 * `docs/screenshots/{ko,en,zh}/<tab>.png` 로 저장.
 *
 * 개선점:
 * - 언어 분리: `?lang=en|zh` 쿼리로 UI 언어 전환 후 캡처
 * - 콘텐츠 대기: 탭별 selector 대기 + toast 소멸 대기 (기본 최소 1400ms)
 * - Costs Timeline 은 Playwright route 로 모의 데이터 주입 (실 API 호출 없이 차트 채움)
 * - 시드 워크플로우 선택/뷰맞춤 실패 시 재시도
 * - 캡처 후 [Demo] 워크플로우 정리
 *
 * 사용:
 *   python3 server.py &                     # 먼저 서버 기동
 *   node scripts/capture-screenshots.mjs    # 캡처
 *   LANGS=en node scripts/capture-screenshots.mjs   # 특정 언어만
 *   HEADLESS=0 node scripts/capture-screenshots.mjs # 창 띄워서
 */
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const BASE = process.env.BASE || 'http://127.0.0.1:8080';
const HEADLESS = process.env.HEADLESS !== '0';
const LANGS = (process.env.LANGS || 'ko,en,zh').split(',').map(s => s.trim()).filter(Boolean);
const OUT_BASE = new URL('../docs/screenshots/', import.meta.url).pathname;

const TABS = [
  { id: 'overview',      waitFor: '.card',          extraWait: 900 },
  { id: 'workflows',     waitFor: '#wfCanvas, #wf-canvas, .wf-node, [data-nid]', extraWait: 1600, kind: 'workflows' },
  { id: 'aiProviders',   waitFor: '.chip-ok, .chip-err, .card h3', extraWait: 1200 },
  { id: 'costsTimeline', waitFor: 'svg, .card',     extraWait: 900, kind: 'costs' },
  { id: 'promptCache',   waitFor: '.card',          extraWait: 900, kind: 'promptCache' },
  { id: 'thinkingLab',   waitFor: '.card',          extraWait: 900 },
  { id: 'toolUseLab',    waitFor: '.card',          extraWait: 900 },
  { id: 'modelBench',    waitFor: '.card',          extraWait: 900 },
  { id: 'claudeDocs',    waitFor: '.card',          extraWait: 900 },
  { id: 'promptLibrary', waitFor: '.card',          extraWait: 900 },
  { id: 'projectAgents', waitFor: '.card',          extraWait: 900 },
  { id: 'mcp',           waitFor: '.card',          extraWait: 900 },
];

// Costs Timeline 모의 응답 — 실 API 호출 없이 의미있는 차트가 그려지도록
const MOCK_COST_SUMMARY = {
  ok: true,
  totalUsd: 12.3847,
  totalCount: 147,
  days: Array.from({ length: 14 }, (_, i) => {
    const d = new Date(); d.setDate(d.getDate() - (13 - i));
    const day = d.toISOString().slice(0, 10);
    const seedA = ((i * 73) % 100) / 100;
    const seedB = ((i * 137 + 23) % 100) / 100;
    const seedC = ((i * 211 + 47) % 100) / 100;
    const sources = {
      promptCache: +(0.05 + seedA * 0.42).toFixed(4),
      thinkingLab: +(0.08 + seedB * 0.31).toFixed(4),
      toolUseLab: +(0.02 + seedC * 0.18).toFixed(4),
      workflows: +(0.10 + ((seedA + seedB) / 2) * 0.55).toFixed(4),
      modelBench: +(0.03 + seedC * 0.22).toFixed(4),
    };
    const usd = +Object.values(sources).reduce((a, b) => a + b, 0).toFixed(4);
    return { day, count: 3 + ((i * 5) % 9), usd, sources };
  }),
  bySource: [
    { source: 'workflows',  count: 42, usd: 4.182, tokensIn: 418000, tokensOut: 71000 },
    { source: 'promptCache',count: 31, usd: 2.914, tokensIn: 651000, tokensOut: 44000 },
    { source: 'thinkingLab',count: 28, usd: 2.401, tokensIn: 245000, tokensOut: 88000 },
    { source: 'toolUseLab', count: 18, usd: 1.332, tokensIn: 132000, tokensOut: 24000 },
    { source: 'modelBench', count: 16, usd: 0.907, tokensIn: 91000,  tokensOut: 19000 },
    { source: 'visionLab',  count: 8,  usd: 0.429, tokensIn: 42000,  tokensOut: 9000  },
    { source: 'serverTools',count: 4,  usd: 0.219, tokensIn: 21000,  tokensOut: 5000  },
  ],
  byModel: [
    { model: 'claude-opus-4-7',   count: 31, usd: 5.821 },
    { model: 'claude-sonnet-4-6', count: 74, usd: 4.519 },
    { model: 'claude-haiku-4-5',  count: 42, usd: 2.044 },
  ],
};

async function capture(browser, lang) {
  const langOut = OUT_BASE + lang + '/';
  mkdirSync(langOut, { recursive: true });
  console.log(`\n🌐 lang=${lang} → ${langOut}`);

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    colorScheme: 'dark',
  });
  // Costs Timeline 모킹 (모든 탭 공통으로 붙여도 다른 탭엔 영향 없음)
  await context.route('**/api/cost-timeline/summary', route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_COST_SUMMARY) }));

  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(`${BASE}/?lang=${lang}`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForSelector('#nav', { state: 'attached', timeout: 10000 });
  // 초기 i18n 로드 + NAV 렌더 완료까지 넉넉히 대기
  await page.waitForFunction(() => {
    const nav = document.getElementById('nav');
    return nav && nav.children.length > 5;
  }, { timeout: 10000 });
  await page.waitForTimeout(800);

  // 시드 워크플로우 1건 (빌트인 템플릿 기반)
  try {
    const tpl = await page.evaluate(() =>
      fetch('/api/workflows/templates/bt-multi-ai-compare').then(r => r.json()));
    if (tpl?.ok) {
      await page.evaluate(async (tpl) => {
        await fetch('/api/workflows/save', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: '[Demo] Multi-AI Compare',
            nodes: tpl.template.nodes, edges: tpl.template.edges,
          }),
        });
      }, tpl);
    }
  } catch {}

  let shot = 0;
  for (const tab of TABS) {
    const path = `${langOut}${tab.id}.png`;
    try {
      // aiProviders 는 fetch 응답을 먼저 예약해두고 탭 전환
      const aiResp = (tab.id === 'aiProviders')
        ? page.waitForResponse(r => r.url().includes('/api/ai-providers/list') && r.status() === 200, { timeout: 8000 }).catch(() => null)
        : null;

      await page.evaluate((id) => { location.hash = '#/' + id; }, tab.id);
      // fetch 완료 대기 → 콘텐츠 셀렉터 → 여유 시간
      await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
      if (aiResp) await aiResp;
      try {
        await page.waitForSelector(tab.waitFor, { state: 'visible', timeout: 4000 });
      } catch {}
      if (tab.id === 'aiProviders') {
        await page.waitForFunction(() => {
          const n = document.querySelectorAll('[data-i18n="available"], [data-i18n="unavailable"]').length;
          return n >= 5;
        }, { timeout: 5000 }).catch(() => {});
      }
      await page.waitForTimeout(tab.extraWait);

      if (tab.kind === 'workflows') {
        // 데모 워크플로우 선택 → fitView → 토스트 사라질 때까지 대기
        const ok = await page.evaluate(() => {
          const list = (window.__wf?.workflows || []);
          const demo = list.find(w => (w.name || '').startsWith('[Demo]'));
          if (!demo) return false;
          if (typeof window._wfOpen === 'function') { window._wfOpen(demo.id); return true; }
          if (typeof window._wfSelect === 'function') { window._wfSelect(demo.id); return true; }
          if (window.__wf) { window.__wf.current = demo; if (window.renderView) window.renderView(); return true; }
          return false;
        });
        await page.waitForTimeout(900);
        await page.evaluate(() => { try { window._wfFitView && window._wfFitView(); } catch {} });
        // toast 사라질 때까지 대기 (2.5s 가량)
        await page.waitForTimeout(2600);
        if (!ok) console.log(`     ⚠ workflow seed not loaded`);
      }

      if (tab.id === 'overview') {
        // 연결된 계정 온보딩 모달 자동 Continue
        const clicked = await page.evaluate(() => {
          const buttons = Array.from(document.querySelectorAll('button'));
          const cont = buttons.find(b => /Continue|계속|继续/.test(b.textContent || ''));
          if (cont) { cont.click(); return true; }
          return false;
        });
        if (clicked) await page.waitForTimeout(800);
      }

      if (tab.kind === 'promptCache') {
        await page.evaluate(() => {
          if (typeof window.pcLoadExample === 'function') window.pcLoadExample('system-prompt');
        });
        await page.waitForTimeout(500);
      }

      // 기타 탭에서 잔여 toast 가 있으면 사라질 때까지 짧게 대기
      await page.waitForTimeout(200);
      await page.screenshot({ path, fullPage: false });
      console.log(`  ✅ ${tab.id.padEnd(16)} → ${lang}/${tab.id}.png`);
      shot++;
    } catch (e) {
      console.log(`  ❌ ${tab.id}: ${e.message}`);
    }
  }

  // 데모 워크플로우 정리
  try {
    await page.evaluate(async () => {
      const list = await fetch('/api/workflows/list').then(r => r.json());
      for (const w of (list.workflows || [])) {
        if ((w.name || '').startsWith('[Demo]')) {
          await fetch('/api/workflows/delete', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: w.id }),
          });
        }
      }
    });
  } catch {}

  await context.close();
  return { shot, errors };
}

console.log(`📸 capturing ${TABS.length} tabs × ${LANGS.length} langs → docs/screenshots/<lang>/`);
const browser = await chromium.launch({ headless: HEADLESS });
let totalShot = 0;
const allErrors = [];
for (const lang of LANGS) {
  const { shot, errors } = await capture(browser, lang);
  totalShot += shot;
  allErrors.push(...errors);
}
await browser.close();

if (allErrors.length) {
  console.log(`\n⚠️  ${allErrors.length} console errors observed:`);
  allErrors.slice(0, 5).forEach(e => console.log('   ' + e.slice(0, 200)));
}
const target = TABS.length * LANGS.length;
console.log(`\n${totalShot === target ? '✅' : '⚠️'} captured ${totalShot}/${target} screenshots`);
process.exit(totalShot === target ? 0 : 1);
