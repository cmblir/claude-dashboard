#!/usr/bin/env node
/**
 * QQ143 — server-side cache for /api/memory/snapshot. The endpoint
 * fans out _top_processes(30) (ps) and api_cli_sessions_list (full
 * Claude sessions scan), totalling ~150-360ms per hit. With a 1.5s
 * TTL, the live ticker stays real-time but back-to-back tab-switches
 * and concurrent panel refreshes hit the memo. ?nocache=1 forces a
 * re-probe.
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

const t1 = await timed(`http://127.0.0.1:${PORT}/api/memory/snapshot`);
const t2 = await timed(`http://127.0.0.1:${PORT}/api/memory/snapshot`);
const t3 = await timed(`http://127.0.0.1:${PORT}/api/memory/snapshot?nocache=1`);

check(`cached call < 30ms (got ${t2}ms; cold was ${t1}ms)`,
  t2 < 30, `t2=${t2}`);
check(`nocache=1 forces re-probe (>= ${Math.max(40, t1 - 100)}ms)`,
  t3 >= Math.max(40, t1 - 100), `t1=${t1} t3=${t3}`);

// Wait > 1.5s TTL so the next hit is cold again.
await new Promise(r => setTimeout(r, 1700));
const t4 = await timed(`http://127.0.0.1:${PORT}/api/memory/snapshot`);
check(`TTL expires after 1.5s — new hit is uncached again`,
  t4 >= Math.max(40, t1 - 100), `t1=${t1} t4=${t4}`);

console.log(process.exitCode ? '\nFAILED' : '\nOK');
