#!/usr/bin/env node
/**
 * QQ156 — /api/auto_resume/status memo (QQ154) used to outlive
 * writes — a cancel/set followed by an immediate /status read
 * served stale data for up to 1.5s. This regression locks in the
 * fix: /status reflects the post-write state immediately.
 *
 * Flow:
 *   1. Pick a session, force-bind via allowUnboundSession
 *   2. /status sees the entry as enabled
 *   3. Cancel the binding
 *   4. /status (NEXT call, no wait) — entry must be enabled=false
 */
const PORT = process.env.PORT || '19500';

function check(label, ok, detail) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) process.exitCode = 1;
}

async function jget(path) {
  const r = await fetch(`http://127.0.0.1:${PORT}${path}`);
  return r.json();
}
async function jpost(path, body) {
  const r = await fetch(`http://127.0.0.1:${PORT}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}

// Pick any session
const sessList = await jget('/api/sessions/list?limit=10&sort=recent');
const sid = (sessList.sessions || []).filter(s => s.cwd || s.projectPath)[0]?.session_id;
if (!sid) { console.error('no sessions to test against'); process.exit(1); }

// Cleanup any prior binding
await jpost('/api/auto_resume/cancel', { sessionId: sid }).catch(() => {});

// Bind
const setRes = await jpost('/api/auto_resume/set', {
  sessionId: sid, prompt: 'cache-invalidation-test',
  pollInterval: 60, idleSeconds: 30, maxAttempts: 3,
  allowUnboundSession: true,
});
check('set succeeded', setRes.ok === true, JSON.stringify(setRes));

// Read /status — should see the binding as enabled.
const s1 = await jget('/api/auto_resume/status');
const e1 = (s1.entries || []).find(e => e.sessionId === sid);
check('status returns the new binding as enabled',
  e1 && e1.enabled === true,
  JSON.stringify(e1 ? { enabled: e1.enabled, state: e1.state } : null));

// Cancel — must invalidate the cache so the next /status reflects this.
const cancelRes = await jpost('/api/auto_resume/cancel', { sessionId: sid });
check('cancel succeeded', cancelRes.ok === true, JSON.stringify(cancelRes));

// IMMEDIATELY read /status — without QQ156 this returned stale enabled=true
// for up to 1.5s.
const s2 = await jget('/api/auto_resume/status');
const e2 = (s2.entries || []).find(e => e.sessionId === sid);
check('status reflects cancel without 1.5s delay',
  e2 && e2.enabled === false,
  JSON.stringify(e2 ? { enabled: e2.enabled, state: e2.state } : null));

console.log(process.exitCode ? '\nFAILED' : '\nOK');
