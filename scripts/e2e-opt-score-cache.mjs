#!/usr/bin/env node
/**
 * QQ155 — server-side cache for /api/optimization/score. The endpoint
 * aggregates settings + 30-day quality metrics + agents/plugins/
 * permissions counts; ~50ms per hit. Overview tab calls it on every
 * load. The metrics window is 30 days, so a 10s TTL coalesces
 * tab-switch redundancy without making the dashboard feel stale.
 */
const PORT = process.env.PORT || '19500';

function check(label, ok, detail) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) process.exitCode = 1;
}

async function timed(url) {
  const t0 = Date.now();
  await fetch(url);
  return Date.now() - t0;
}

const t1 = await timed(`http://127.0.0.1:${PORT}/api/optimization/score`);
const t2 = await timed(`http://127.0.0.1:${PORT}/api/optimization/score`);

check('cached call < 30ms (got ' + t2 + 'ms)', t2 < 30, `t1=${t1} t2=${t2}`);

// 5 back-to-back hits should all be served from cache.
let total = 0;
for (let i = 0; i < 5; i++) total += await timed(`http://127.0.0.1:${PORT}/api/optimization/score`);
check('5 back-to-back hits avg < 10ms', total / 5 < 10, `${(total/5).toFixed(1)}ms`);

console.log(process.exitCode ? '\nFAILED' : '\nOK');
