#!/usr/bin/env node
/**
 * 45 tabs smoke — 모든 탭을 순회하며:
 *  - 뷰 렌더 실패 메시지("뷰 렌더 실패:") 미노출
 *  - console error 카운트 0
 *  - "_escapeHTML is not defined" / "is not defined" 류 즉시 실패
 *
 * 서버가 127.0.0.1:8080 에 기동돼 있어야 한다.
 *
 * 사용:
 *   node scripts/e2e-tabs-smoke.mjs
 *   HEADLESS=0 node scripts/e2e-tabs-smoke.mjs        # 창 띄워서 실행
 *   TAB_ID=workflows node scripts/e2e-tabs-smoke.mjs  # 단일 탭만
 */
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';

const BASE = process.env.BASE || `http://127.0.0.1:${process.env.PORT || 8080}`;
const HEADLESS = process.env.HEADLESS !== '0';
const ONLY = process.env.TAB_ID || null;

// server/nav_catalog.py 를 정적 파싱해 탭 id 목록 추출 (빌드 의존 없이)
function readTabIds() {
  const src = readFileSync(new URL('../server/nav_catalog.py', import.meta.url), 'utf8');
  const startMarker = 'TAB_CATALOG: list[tuple[';
  const idx = src.indexOf(startMarker);
  if (idx < 0) throw new Error('TAB_CATALOG 을 찾지 못함');
  const tail = src.slice(idx);
  const ids = [...tail.matchAll(/^\s*\("([a-zA-Z][a-zA-Z0-9_]*)"\s*,/gm)].map(m => m[1]);
  return ids;
}

const tabIds = ONLY ? [ONLY] : readTabIds();
console.log(`🧪 smoke: ${tabIds.length} tabs · base=${BASE} · headless=${HEADLESS}`);

const browser = await chromium.launch({ headless: HEADLESS });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await context.newPage();

const failures = [];
const consoleErrors = [];
page.on('console', msg => {
  if (msg.type() === 'error') consoleErrors.push(msg.text());
});
page.on('pageerror', err => consoleErrors.push('[pageerror] ' + err.message));

await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
// nav 렌더 대기 (요소 id)
await page.waitForSelector('#nav', { timeout: 10000 }).catch(() => {});
// 앱 초기화 안정화 대기
await page.waitForTimeout(500);

for (const id of tabIds) {
  const errsBefore = consoleErrors.length;
  try {
    // hashchange 이벤트로 네비게이션 — go() 와 동일 경로 (state.view + renderNav + renderView)
    await page.evaluate((tid) => { location.hash = '#/' + tid; }, id);
    await page.waitForTimeout(450);
    // 실제 뷰 전환 확인
    const confirmed = await page.evaluate((tid) =>
      typeof state !== 'undefined' && state.view === tid
    , id);
    if (!confirmed) {
      failures.push({ id, reason: 'view-not-switched', detail: 'state.view mismatch' });
      console.log(`  ⚠️  ${id} — view did not switch`);
      continue;
    }
    // 뷰 렌더 실패는 renderView() catch 블록이 생성하는 `<div class="card p-8 empty">` 로만 판정.
    // 일반 본문 텍스트에 "뷰 렌더 실패" 라는 문자열이 포함돼 있어도 실제 에러가 아니면 무시 (ex. memory 탭의 메모리 노트 본문).
    const renderFailed = await page.evaluate(() => {
      const v = document.querySelector('#view');
      if (!v) return false;
      return !!v.querySelector('.card.p-8.empty');
    });
    const newErrs = consoleErrors.slice(errsBefore);
    if (renderFailed) {
      failures.push({ id, reason: 'view-render-failed', detail: bodyText.split('\n').find(l => l.includes('실패') || l.includes('failed')) || '' });
      console.log(`  ❌ ${id} — view render failed`);
    } else if (newErrs.length) {
      failures.push({ id, reason: 'console-error', detail: newErrs.join(' | ').slice(0, 240) });
      console.log(`  ⚠️  ${id} — ${newErrs.length} console error(s)`);
    } else {
      console.log(`  ✅ ${id}`);
    }
  } catch (e) {
    failures.push({ id, reason: 'exception', detail: e.message });
    console.log(`  💥 ${id} — ${e.message}`);
  }
}

console.log('');
if (failures.length) {
  console.log(`❌ ${failures.length}/${tabIds.length} 실패`);
  for (const f of failures) console.log(`  - ${f.id}: [${f.reason}] ${f.detail}`);
} else {
  console.log(`✅ ${tabIds.length}/${tabIds.length} 탭 모두 통과`);
}

await browser.close();
process.exit(failures.length ? 1 : 0);
