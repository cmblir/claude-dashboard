#!/usr/bin/env node
/**
 * QQ208 — terminal parity for chat /workflows (QQ206) and /run (QQ207).
 *   lazyclaude workflows [filter]   list flows + status
 *   lazyclaude run <id|name>        start a run
 */
import { chromium } from 'playwright';

const PORT = process.env.PORT || '19500';
const URL  = `http://127.0.0.1:${PORT}/`;

function check(label, ok, detail) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) process.exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
page.on('pageerror', e => console.error('[pageerror]', e.message));

const runPosts = [];
page.on('request', req => {
  if (req.method() === 'POST' && req.url().endsWith('/api/workflows/run')) {
    runPosts.push(req.postData() || '');
  }
});

await page.goto(URL, { waitUntil: 'networkidle' });

// Seed a workflow with a name unique to this test run (date+random) so
// repeated test invocations don't accumulate ambiguous matches.
const uniqTag = 'termrun-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
const seed = await page.evaluate(async (tag) => {
  const r = await fetch('/api/workflows/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id: 'wf-term-runtest-' + Date.now(),
      name: 'qq208-' + tag,
      nodes: [
        { id: 'start',  type: 'start',  x: 100, y: 100, data: {} },
        { id: 'output', type: 'output', x: 300, y: 100, data: {} },
      ],
      edges: [{ from: 'start', fromPort: 'out', to: 'output', toPort: 'in' }],
    }),
  });
  return await r.json();
}, uniqTag);
check('test prereq: seeded workflow saved', seed && seed.ok);
const seedId = seed && seed.id;

await page.evaluate(() => window.go('lazyclawTerm'));
await page.waitForSelector('#lcTermInput', { timeout: 8000 });
await page.waitForFunction(() => window.CC_PREFS && window.CC_PREFS.ui, { timeout: 8000 });
await page.waitForFunction(() =>
  /헬스체크 완료/.test((document.getElementById('lcTermLog') || {}).textContent || ''),
  { timeout: 12000 }).catch(() => {});

async function run(cmd) {
  await page.evaluate((c) => {
    const inp = document.getElementById('lcTermInput');
    inp.value = c;
    return window._lcTermRun();
  }, cmd);
  await page.waitForTimeout(350);
}
const fullLog = async () => await page.evaluate(() => (document.getElementById('lcTermLog') || {}).textContent || '');

// 1. lazyclaude workflows lists workflows
await run('lazyclaude workflows');
const wfsOut = await fullLog();
check('lazyclaude workflows lists the seeded workflow id',
  wfsOut.includes(seedId), `seedId=${seedId}`);
check('lazyclaude workflows shows node count',
  /\d+n/.test(wfsOut));

// 2. lazyclaude workflows <filter> narrows
await run(`lazyclaude workflows qq208-${uniqTag}`);
const filteredOut = await fullLog();
check('lazyclaude workflows <filter> narrows to seeded',
  new RegExp(`qq208-${uniqTag}`).test(filteredOut));

// 3. lazyclaude run with no arg → ⚠ usage
await run('lazyclaude run');
const usageOut = await fullLog();
check('lazyclaude run (no arg) emits ⚠ usage',
  /⚠.*사용법.*lazyclaude run/.test(usageOut));

// 4. lazyclaude run <unique name> POSTs and prints runId
const before = runPosts.length;
await run(`lazyclaude run qq208-${uniqTag}`);
await page.waitForTimeout(500);
check('lazyclaude run <unique name> fires POST',
  runPosts.length === before + 1, `posts=${runPosts.length - before}`);
const runOut = await fullLog();
check('lazyclaude run prints "Started:" + run id',
  new RegExp(`Started:.*qq208-${uniqTag}`).test(runOut) && /run:\s+run-/.test(runOut));

// 5. ambiguous prefix → list bubble, no POST
const before2 = runPosts.length;
await run('lazyclaude run wf-');
await page.waitForTimeout(300);
check('ambiguous run does NOT POST',
  runPosts.length === before2, `posts=${runPosts.length - before2}`);
const ambigOut = await fullLog();
check('ambiguous run prints "Multiple matches"',
  /Multiple matches/.test(ambigOut));

// 6. no-match → ⚠ warn
await run('lazyclaude run no-such-zzz');
const noMatchOut = await fullLog();
check('no-match run prints ⚠',
  /⚠.*일치하는 워크플로우 없음/.test(noMatchOut));

// 7. lazyclaude help lists workflows + run
await run('lazyclaude help');
const helpOut = await fullLog();
check('help lists workflows', /lazyclaude workflows/.test(helpOut));
check('help lists run', /lazyclaude run/.test(helpOut));

// 8. typo did-you-mean for workflows
await run('lazyclaude wrkflows');
const typoOut = await fullLog();
check('lazyclaude wrkflows → suggests workflows',
  /lazyclaude workflows/.test(typoOut));

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
