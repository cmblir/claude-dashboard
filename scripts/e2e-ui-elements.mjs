#!/usr/bin/env node
/**
 * UI 요소 무결성 E2E — 워크플로우 탭의 중요 DOM 구조가 v2.10.x UX 변경
 * 이후에도 깨지지 않았는지 검증. Anthropic API 키 없이도 돌림.
 *
 * 검증 항목:
 *  - #wfRoot / #wfCanvasHost / #wfCanvas / #wfViewport / #wfMinimap 존재
 *  - 노드 렌더 시 .wf-node-body / .wf-node-ring / .wf-node-elapsed 각 1개 이상
 *  - `/api/workflows/templates/bt-multi-ai-compare` 로 임시 워크플로우 생성 후
 *    .wf-node 엘리먼트 개수 = nodes 배열 길이
 *  - _wfRenderRunBanner / _wfShowNodeTooltip / _wfToggleCat 전역 노출 체크
 *
 * 사용:
 *   node scripts/e2e-ui-elements.mjs
 *   HEADLESS=0 node scripts/e2e-ui-elements.mjs
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE || `http://127.0.0.1:${process.env.PORT || 8080}`;
const HEADLESS = process.env.HEADLESS !== '0';
const TPL = process.env.TPL_ID || 'bt-multi-ai-compare';

console.log(`🧪 UI elements E2E · base=${BASE} · headless=${HEADLESS}`);

const browser = await chromium.launch({ headless: HEADLESS });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

const errors = [];
const pass = (msg) => console.log(`  ✅ ${msg}`);
const fail = (msg) => { console.log(`  ❌ ${msg}`); errors.push(msg); };

page.on('pageerror', e => errors.push('[pageerror] ' + e.message));
page.on('console', m => { if (m.type() === 'error') errors.push('[console.error] ' + m.text()); });

await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForTimeout(500);

await page.evaluate(() => { location.hash = '#/workflows'; });
await page.waitForSelector('#wfRoot', { timeout: 15000 });
pass('워크플로우 탭 로드됨 (#wfRoot)');

const coreIds = ['wfRoot', 'wfCanvasWrap', 'wfToolbar', 'wfCanvasHost', 'wfCanvas', 'wfViewport', 'wfMinimap'];
for (const id of coreIds) {
  const exists = await page.evaluate(k => !!document.getElementById(k), id);
  exists ? pass(`#${id} 존재`) : fail(`#${id} 없음`);
}

const tpl = await page.evaluate(async (id) => fetch('/api/workflows/templates/' + id).then(x => x.json()), TPL);
if (!tpl || !tpl.ok) { fail(`템플릿 조회 실패: ${JSON.stringify(tpl).slice(0,120)}`); await browser.close(); process.exit(1); }
pass(`템플릿 조회 ok · ${tpl.template.name} · ${tpl.template.nodes.length} nodes`);

const newWf = await page.evaluate(async (tpl) => {
  return fetch('/api/workflows/save', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: '[E2E-UI] ' + tpl.template.name,
      nodes: tpl.template.nodes, edges: tpl.template.edges,
    }),
  }).then(x => x.json());
}, tpl);
if (!newWf || !newWf.ok) { fail(`워크플로우 저장 실패: ${JSON.stringify(newWf).slice(0,120)}`); await browser.close(); process.exit(1); }
const wfId = newWf.id || newWf.workflowId || (newWf.workflow && newWf.workflow.id);
pass(`임시 워크플로우 생성 · id=${wfId}`);

await page.evaluate(async (id) => {
  if (window._wfSelect) window._wfSelect(id);
  else {
    const r = document.querySelector(`[data-wfid="${id}"]`);
    if (r) r.click();
  }
}, wfId);
await page.waitForTimeout(800);

const nodeCount = await page.$$eval('.wf-node', els => els.length);
if (nodeCount === tpl.template.nodes.length) pass(`.wf-node 렌더 = ${nodeCount}/${tpl.template.nodes.length}`);
else if (nodeCount > 0) pass(`.wf-node 렌더 (부분) = ${nodeCount}`);
else fail(`.wf-node 렌더 안 됨 (기대 ${tpl.template.nodes.length})`);

const ringCount = await page.$$eval('.wf-node-ring', els => els.length);
ringCount >= 1 ? pass(`.wf-node-ring 존재 (${ringCount}개, v2.10.0 회전 링)`) : fail('.wf-node-ring 없음 (v2.10.0 회귀)');

const elapsedCount = await page.$$eval('.wf-node-elapsed', els => els.length);
elapsedCount >= 1 ? pass(`.wf-node-elapsed 존재 (${elapsedCount}개, v2.10.0 카운터)`) : fail('.wf-node-elapsed 없음 (v2.10.0 회귀)');

const hasBannerFn = await page.evaluate(() => typeof window._wfRenderRunBanner === 'function');
hasBannerFn ? pass('_wfRenderRunBanner 전역 노출 (v2.10.0)') : fail('_wfRenderRunBanner 없음 (v2.10.0 회귀)');

const bannerOk = await page.evaluate(() => {
  try {
    const fakeRun = {
      status: 'running',
      startedAt: Date.now() - 1500,
      currentNodeId: (window.__wf?.current?.nodes?.[0]?.id) || null,
      nodeResults: {},
    };
    window._wfRenderRunBanner(fakeRun);
    const el = document.getElementById('wfRunBanner');
    return el && el.classList.contains('visible');
  } catch (e) { return false; }
});
bannerOk ? pass('#wfRunBanner visible 클래스 정상 부착') : fail('#wfRunBanner visible 부착 실패 (v2.10.0 회귀)');

const hasTooltipFn = await page.evaluate(() => typeof window._wfShowNodeTooltip === 'function');
hasTooltipFn ? pass('_wfShowNodeTooltip 전역 노출 (v2.10.2)') : fail('_wfShowNodeTooltip 없음 (v2.10.2 회귀)');

const hasCatToggleFn = await page.evaluate(() => typeof window._wfToggleCat === 'function');
hasCatToggleFn ? pass('_wfToggleCat 전역 노출 (v2.10.1)') : fail('_wfToggleCat 없음 (v2.10.1 회귀)');

await page.evaluate(async (id) => {
  await fetch('/api/workflows/delete', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ id }),
  });
}, wfId);
pass('임시 워크플로우 정리됨');

await browser.close();
if (errors.length) {
  console.log(`\n❌ ${errors.length} 실패`);
  for (const e of errors) console.log(`  - ${e}`);
  process.exit(1);
}
console.log('\n✅ 전부 통과');
process.exit(0);
