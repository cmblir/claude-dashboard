#!/usr/bin/env node
/**
 * README 용 스크린샷 자동 생성.
 *
 * 대시보드 주요 탭을 순회하며 `docs/screenshots/<tab>.png` 로 저장.
 * 캡처 전 각 탭에 시드 데이터(워크플로우 템플릿, 프롬프트 라이브러리 등)를
 * 넣어 빈 화면이 아니라 실제 UI 구조가 보이게 한다.
 *
 * 사용:
 *   node scripts/capture-screenshots.mjs
 *   HEADLESS=0 node scripts/capture-screenshots.mjs   # 창 띄워서
 */
import { chromium } from 'playwright';
import { writeFileSync } from 'node:fs';

const BASE = process.env.BASE || 'http://127.0.0.1:8080';
const HEADLESS = process.env.HEADLESS !== '0';
const OUT = new URL('../docs/screenshots/', import.meta.url).pathname;

const TABS = [
  { id: 'overview',      label: '개요 · 최적화 점수 · 시스템 요약' },
  { id: 'workflows',     label: 'n8n 스타일 DAG 에디터' },
  { id: 'aiProviders',   label: '멀티 AI 프로바이더' },
  { id: 'costsTimeline', label: '비용 타임라인 통합' },
  { id: 'promptCache',   label: 'Prompt Cache Lab' },
  { id: 'thinkingLab',   label: 'Extended Thinking Lab' },
  { id: 'toolUseLab',    label: 'Tool Use 플레이그라운드' },
  { id: 'modelBench',    label: 'Model Benchmark' },
  { id: 'claudeDocs',    label: 'Claude Docs Hub' },
  { id: 'promptLibrary', label: 'Prompt Library' },
  { id: 'projectAgents', label: '프로젝트 서브에이전트' },
  { id: 'mcp',           label: 'MCP 커넥터' },
];

console.log(`📸 capturing ${TABS.length} tab screenshots → ${OUT}`);

const browser = await chromium.launch({ headless: HEADLESS });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2, // 레티나 렌더
  colorScheme: 'dark',
});
const page = await context.newPage();

// 콘솔 에러는 수집만 (캡처 실패 판단용)
const errors = [];
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForSelector('#nav', { state: 'attached', timeout: 10000 });
await page.waitForTimeout(900); // 초기 NAV 렌더 + 최적화 점수 fetch 완료 대기

// --- seed: workflows 탭에 빌트인 템플릿 1개 미리 올려둠 (빈 캔버스 방지) ---
try {
  const tpl = await page.evaluate(() =>
    fetch('/api/workflows/templates/bt-multi-ai-compare').then(r => r.json()));
  if (tpl?.ok) {
    const saved = await page.evaluate(async (tpl) => {
      return fetch('/api/workflows/save', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          name: '[Demo] 멀티 AI 비교',
          nodes: tpl.template.nodes, edges: tpl.template.edges,
        }),
      }).then(r => r.json());
    }, tpl);
    console.log(`  ✓ seed workflow: ${saved?.id || saved?.workflowId || 'ok'}`);
  }
} catch (e) { console.log('  ⚠ seed workflow skipped:', e.message); }

let shot = 0;
for (const tab of TABS) {
  try {
    await page.evaluate((id) => { location.hash = '#/' + id; }, tab.id);
    await page.waitForTimeout(tab.id === 'workflows' ? 1500 : 700);

    // workflows 는 생성해둔 데모 선택 + 뷰 맞춤
    if (tab.id === 'workflows') {
      await page.evaluate(() => {
        const list = (window.__wf?.workflows || []);
        const demo = list.find(w => (w.name||'').includes('멀티 AI'));
        if (demo && window._wfSelect) window._wfSelect(demo.id);
        else if (demo) { window.__wf.current = demo; window.renderView && window.renderView(); }
      });
      await page.waitForTimeout(800);
      await page.evaluate(() => window._wfFitView && window._wfFitView()).catch(()=>{});
      await page.waitForTimeout(400);
    }

    // promptCache 는 예시 첫 번째 로드
    if (tab.id === 'promptCache') {
      await page.evaluate(() => window.pcLoadExample && window.pcLoadExample('system-prompt')).catch(()=>{});
      await page.waitForTimeout(400);
    }

    const out = OUT + tab.id + '.png';
    await page.screenshot({ path: out, fullPage: false });
    console.log(`  ✅ ${tab.id.padEnd(16)} → docs/screenshots/${tab.id}.png`);
    shot++;
  } catch (e) {
    console.log(`  ❌ ${tab.id}: ${e.message}`);
  }
}

// 정리: 데모 워크플로우 삭제
try {
  await page.evaluate(async () => {
    const list = await fetch('/api/workflows/list').then(r => r.json());
    for (const w of (list.workflows || [])) {
      if ((w.name||'').startsWith('[Demo]')) {
        await fetch('/api/workflows/delete', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ id: w.id }),
        });
      }
    }
  });
  console.log('  ✓ demo workflow cleanup');
} catch (e) {}

await browser.close();

if (errors.length) {
  console.log(`\n⚠️ ${errors.length} console errors observed:`);
  errors.slice(0, 5).forEach(e => console.log('   ' + e.slice(0, 200)));
}
console.log(`\n✅ captured ${shot}/${TABS.length} tabs`);
process.exit(shot === TABS.length ? 0 : 1);
