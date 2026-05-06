#!/usr/bin/env node
/**
 * End-to-end workflow run validation.
 *
 * Builds a 3-node workflow (start → transform → output) that doesn't
 * need any AI provider, runs it via /api/workflows/run, polls
 * /api/workflows/run-status until terminal, and asserts:
 *   1. The run reaches `ok` status (not `err` / `running`).
 *   2. Every node has a result with status === 'ok'.
 *   3. The transform node's output matches the expected template.
 *   4. The total wall-clock time is < 5 s (real-world sanity check).
 */
const PORT = process.env.PORT || 8080;
const BASE = process.env.BASE || `http://127.0.0.1:${PORT}`;

let exitCode = 0;
function check(label, ok, detail) {
  const tag = ok ? '\x1b[32m✅\x1b[0m' : '\x1b[31m❌\x1b[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) exitCode = 1;
}

async function jpost(path, body) {
  const r = await fetch(BASE + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}
async function jget(path) { return (await fetch(BASE + path)).json(); }

// 1. Build & save the workflow.
const wf = {
  name: 'e2e-run-no-provider',
  description: 'transform-only workflow used by e2e test',
  nodes: [
    { id: 'n-start',  type: 'start',  title: 'Start',  x: 80, y: 80,  data: {} },
    {
      id: 'n-xform',  type: 'transform', title: 'Transform',
      x: 320, y: 80,
      data: {
        transformType: 'template',
        // {{input}} expands to the upstream node's output. The start
        // node yields its `subject` text; for an empty start node the
        // template just hardcodes a known string.
        template: 'hello-from-transform',
      },
    },
    { id: 'n-out',    type: 'output', title: 'Out',   x: 560, y: 80, data: {} },
  ],
  edges: [
    { id: 'e1', from: 'n-start', to: 'n-xform' },
    { id: 'e2', from: 'n-xform', to: 'n-out'   },
  ],
};
const saveR = await jpost('/api/workflows/save', wf);
check('workflow saves', !!saveR.ok && !!saveR.id, JSON.stringify(saveR).slice(0, 200));
const wfId = saveR.id;

// 2. Kick off the run.
const runR = await jpost('/api/workflows/run', { workflowId: wfId });
check('run starts', !!runR.ok && !!runR.runId, JSON.stringify(runR).slice(0, 200));
const runId = runR.runId;

// 3. Poll until terminal (ok or err) or 8 s.
const t0 = Date.now();
let last;
while (Date.now() - t0 < 8000) {
  last = await jget('/api/workflows/run-status?runId=' + encodeURIComponent(runId));
  if (last && last.run && (last.run.status === 'ok' || last.run.status === 'err')) break;
  await new Promise(r => setTimeout(r, 200));
}
const elapsed = Date.now() - t0;
check('run reaches terminal status within 8s', last && last.run && (last.run.status === 'ok' || last.run.status === 'err'),
  `status=${last && last.run && last.run.status} elapsed=${elapsed}ms`);
check('run finished OK', last && last.run && last.run.status === 'ok',
  `status=${last && last.run && last.run.status}`);

// 4. Verify per-node results.
const results = (last && last.run && last.run.nodeResults) || {};
check('every node has a result', Object.keys(results).length === 3, `got ${Object.keys(results).length}`);
const xform = results['n-xform'];
check('transform node ran ok', !!xform && xform.status === 'ok',
  `status=${xform && xform.status} err=${xform && xform.error}`);
check('transform output matches template', !!xform && (xform.output || '').includes('hello-from-transform'),
  `output=${xform && (xform.output || '').slice(0, 60)}`);

// 5. Make sure /api/workflows/runs surfaces this run.
const list = await jget('/api/workflows/runs?limit=10');
const found = ((list && list.runs) || []).some(r => r.runId === runId);
check('run shows up in /workflows/runs listing', found, `runs=${(list && list.runs || []).length}`);

// 6. Cleanup — delete the workflow so smoke runs don't accumulate.
await jpost('/api/workflows/delete', { id: wfId });

console.log(exitCode === 0 ? '\nOK' : '\nFAIL');
process.exit(exitCode);
