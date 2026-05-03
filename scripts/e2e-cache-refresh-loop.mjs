#!/usr/bin/env node
/**
 * QQ140 — periodic background refresh keeps the QQ135/QQ136 memos hot
 * past the 30s TTL. Without this, leaving the dashboard idle for >30s
 * meant the next AI Providers / Team tab open paid the cold subprocess
 * fan-out cost (~750ms / ~400ms) again.
 *
 * The refresh thread fires every 25s, so a hit at t=35s should still be
 * served from cache (the entry was rewritten at t=25s).
 *
 * Test budget: ~32s (we have to actually wait past the original TTL).
 * Use `SKIP_CACHE_REFRESH_LOOP=1` to skip in fast iteration runs.
 */
const PORT = process.env.PORT || '19500';

if (process.env.SKIP_CACHE_REFRESH_LOOP === '1') {
  console.log('skipped (SKIP_CACHE_REFRESH_LOOP=1)');
  process.exit(0);
}

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

const cliFresh = await timed(`http://127.0.0.1:${PORT}/api/cli/status`);
const authFresh = await timed(`http://127.0.0.1:${PORT}/api/auth/status`);

check('cli/status hot at boot+', cliFresh < 60, `${cliFresh}ms`);
check('auth/status hot at boot+', authFresh < 60, `${authFresh}ms`);

// Sleep past the 30s TTL — the refresh loop runs every 25s so the cache
// should have been re-populated at ~t=25s.
console.log('  ⏱  waiting 32s to cross the original 30s TTL …');
await new Promise(r => setTimeout(r, 32_000));

const cliLate = await timed(`http://127.0.0.1:${PORT}/api/cli/status`);
const authLate = await timed(`http://127.0.0.1:${PORT}/api/auth/status`);

check(`cli/status still hot after 32s idle (was 750ms cold without refresh)`,
  cliLate < 60, `${cliLate}ms`);
check(`auth/status still hot after 32s idle (was 400ms cold without refresh)`,
  authLate < 60, `${authLate}ms`);

console.log(process.exitCode ? '\nFAILED' : '\nOK');
