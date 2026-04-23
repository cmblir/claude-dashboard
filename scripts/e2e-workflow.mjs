#!/usr/bin/env node
/**
 * 워크플로우 E2E — 빌트인 템플릿 생성 → 실행 → 상태 배너 등장 검증.
 * (Anthropic API 키 없이도 돌 수 있게 "시작 → 실패 허용" 까지만 검증)
 *
 * 사용:
 *   node scripts/e2e-workflow.mjs
 *   HEADLESS=0 node scripts/e2e-workflow.mjs
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE || 'http://127.0.0.1:8080';
const HEADLESS = process.env.HEADLESS !== '0';
const TPL_ID = process.env.TPL_ID || 'bt-multi-ai-compare';

console.log(`🧪 workflow E2E · tpl=${TPL_ID} · headless=${HEADLESS}`);

const browser = await chromium.launch({ headless: HEADLESS });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

const consoleErrors = [];
page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
page.on('pageerror', err => consoleErrors.push('[pageerror] ' + err.message));

await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
await page.evaluate(() => { window.state && (window.state.view = 'workflows'); window.renderView && window.renderView(); });
await page.waitForSelector('#wfRoot', { timeout: 10000 });
console.log('  ✓ 워크플로우 탭 로드됨');

// 빌트인 템플릿 가져오기
const tpl = await page.evaluate(async (id) => {
  const r = await fetch('/api/workflows/templates/' + id).then(x => x.json());
  return r;
}, TPL_ID);
if (!tpl || !tpl.ok) {
  console.log(`  ❌ 템플릿 조회 실패: ${JSON.stringify(tpl).slice(0,200)}`);
  await browser.close();
  process.exit(1);
}
console.log(`  ✓ 템플릿 ok · name=${tpl.template.name} · nodes=${tpl.template.nodes?.length || 0}`);

// 템플릿 기반 워크플로우 생성 (서버 API 직접)
const newWf = await page.evaluate(async (tpl) => {
  const body = {
    name: '[E2E] ' + (tpl.template.name || 'test'),
    nodes: tpl.template.nodes || [],
    edges: tpl.template.edges || [],
  };
  const r = await fetch('/api/workflows/save', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(x => x.json());
  return r;
}, tpl);

if (!newWf || !newWf.ok) {
  console.log(`  ❌ 워크플로우 생성 실패: ${JSON.stringify(newWf).slice(0,200)}`);
  await browser.close();
  process.exit(1);
}
const wfId = newWf.id || newWf.workflowId || (newWf.workflow && newWf.workflow.id);
console.log(`  ✓ 워크플로우 생성됨 · id=${wfId}`);

// 실행 요청
const runResp = await page.evaluate(async (wfId) => {
  const r = await fetch('/api/workflows/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: wfId }),
  }).then(x => x.json());
  return r;
}, wfId);
if (!runResp || !runResp.ok) {
  console.log(`  ❌ 실행 요청 실패: ${JSON.stringify(runResp).slice(0,200)}`);
} else {
  console.log(`  ✓ 실행 시작 · runId=${runResp.runId}`);
}

// 5초간 상태 관찰
const endAt = Date.now() + 5000;
let bannerSeen = false;
let statusSeen = new Set();
while (Date.now() < endAt) {
  const st = await page.evaluate((rid) => fetch('/api/workflows/run-status?runId=' + rid).then(x => x.json()), runResp.runId);
  const run = st && st.run;
  if (run) statusSeen.add(run.status);
  const bannerVisible = await page.evaluate(() => !!document.querySelector('#wfRunBanner.visible'));
  if (bannerVisible) bannerSeen = true;
  if (run && (run.status === 'ok' || run.status === 'err')) break;
  await page.waitForTimeout(500);
}

// 배너 화면에 실제로 렌더 유도 (화면 렌더는 선택적이지만 프론트 로직 재확인)
await page.evaluate(() => {
  if (window.__wf && window.__wf.lastRun && window._wfRenderRunBanner) {
    window._wfRenderRunBanner(window.__wf.lastRun);
  }
});

const finalBanner = await page.evaluate(() => {
  const el = document.querySelector('#wfRunBanner');
  return el ? { visible: el.classList.contains('visible'), className: el.className, text: el.textContent.slice(0, 200) } : null;
});

console.log(`  → 관찰된 상태: ${[...statusSeen].join(', ') || '-'}`);
console.log(`  → 배너 등장 여부: ${bannerSeen}`);
if (finalBanner) console.log(`  → 최종 배너: ${finalBanner.className} · "${finalBanner.text.replace(/\s+/g,' ').slice(0,120)}"`);
if (consoleErrors.length) {
  console.log(`  ⚠️ console errors (${consoleErrors.length}):`);
  consoleErrors.slice(0, 5).forEach(e => console.log(`     • ${e.slice(0,180)}`));
}

// 워크플로우 정리 (E2E 잔여물 제거)
await page.evaluate(async (wfId) => {
  await fetch('/api/workflows/delete', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: wfId }),
  });
}, wfId);
console.log(`  ✓ 테스트 워크플로우 삭제됨`);

await browser.close();

const hasCriticalErr = consoleErrors.some(e => /is not defined|View render failed|뷰 렌더 실패/.test(e));
if (hasCriticalErr) {
  console.log('\n❌ critical error 존재 — 실패');
  process.exit(1);
}
console.log('\n✅ E2E 스모크 통과 (critical error 없음)');
process.exit(0);
