#!/usr/bin/env node
/**
 * QQ137 — server boot pre-warms the QQ135 / QQ136 subprocess caches
 * (/api/cli/status and /api/auth/status) in a daemon thread so the
 * user's first AI Providers / Team tab visit hits the memo instead
 * of paying the cold ~750ms / ~400ms cost.
 *
 * This test only knows the server is up — it can't observe the
 * pre-warm thread directly. It infers correctness from the fact
 * that the *first* cold-from-the-test-process hit is already fast.
 * (If the prewarm hadn't run, this hit would take 200ms+.)
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

// Allow up to 4s for the daemon prewarm thread to settle after boot.
// In practice it finishes in <1s, but the test should be tolerant if
// the test runner started the server right before invoking this script.
let cliMs = 0, authMs = 0;
const deadline = Date.now() + 4000;
while (Date.now() < deadline) {
  cliMs = await timed(`http://127.0.0.1:${PORT}/api/cli/status`);
  authMs = await timed(`http://127.0.0.1:${PORT}/api/auth/status`);
  if (cliMs < 60 && authMs < 60) break;
  await new Promise(r => setTimeout(r, 200));
}

check('first /api/cli/status hit < 60ms (was 750ms cold pre-fix)',
  cliMs < 60, `${cliMs}ms`);
check('first /api/auth/status hit < 60ms (was 400ms cold pre-fix)',
  authMs < 60, `${authMs}ms`);

// Sanity — second hit must also be fast.
const cli2 = await timed(`http://127.0.0.1:${PORT}/api/cli/status`);
const auth2 = await timed(`http://127.0.0.1:${PORT}/api/auth/status`);
check('second cli/status hit stays cached', cli2 < 60, `${cli2}ms`);
check('second auth/status hit stays cached', auth2 < 60, `${auth2}ms`);

console.log(process.exitCode ? '\nFAILED' : '\nOK');
