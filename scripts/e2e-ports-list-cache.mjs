#!/usr/bin/env node
/**
 * QQ144 — server-side cache for /api/ports/list. The endpoint runs
 * `lsof -iTCP -sTCP:LISTEN` and `lsof -iUDP` (~50-150ms on a busy
 * system). The Open Ports tab calls it via a live ticker, so
 * coalescing back-to-back hits matters. 3s TTL feels live; bypass
 * via ?nocache=1.
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

const t1 = await timed(`http://127.0.0.1:${PORT}/api/ports/list`);
const t2 = await timed(`http://127.0.0.1:${PORT}/api/ports/list`);
const t3 = await timed(`http://127.0.0.1:${PORT}/api/ports/list?nocache=1`);

check(`cached call < 30ms (got ${t2}ms; cold was ${t1}ms)`,
  t2 < 30, `t2=${t2}`);
// QQ196 — nocache and post-TTL hits do a real lsof, but the OS file-table
// page cache makes subsequent lsof runs ~30% faster than the cold one.
// Assert "much slower than the cached path" rather than "≥ cold − 80ms".
check(`nocache=1 forces re-probe (>> cached)`,
  t3 >= 60 && t3 > t2 * 4, `t1=${t1} t2=${t2} t3=${t3}`);

await new Promise(r => setTimeout(r, 3500));
const t4 = await timed(`http://127.0.0.1:${PORT}/api/ports/list`);
check(`TTL expires after 3s — new hit is uncached again`,
  t4 >= 60 && t4 > t2 * 4, `t1=${t1} t2=${t2} t4=${t4}`);

console.log(process.exitCode ? '\nFAILED' : '\nOK');
