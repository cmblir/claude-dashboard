#!/usr/bin/env node
/** MM regression: workflow fail-fast.
 *
 *  Build a 2-node parallel workflow: one node deliberately fails fast
 *  (invalid model), the other tries claude-cli with a long prompt.
 *  Without MM1+MM2 this run takes 60-300s (sibling timeout). With the
 *  fix, the run terminates within ~3s of the err.
 *
 *  Pure server-side check (no browser) — directly call the Python API.
 */
import { spawn } from 'child_process';

function run(cmd, args) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '', err = '';
    p.stdout.on('data', d => out += d.toString());
    p.stderr.on('data', d => err += d.toString());
    p.on('close', code => resolve({ code, out, err }));
    p.on('error', reject);
  });
}

const py = `
import json, time, importlib
from server import workflows, ai_providers
importlib.reload(ai_providers); importlib.reload(workflows)

# Replace registry execute with one that errs instantly when prompt
# contains MARKER, otherwise long-runs claude-cli with a real prompt.
reg = ai_providers.get_registry()
orig = reg.execute
def fake(provider_id, model, prompt, **kw):
    if 'MARKER_FAIL' in (prompt or ''):
        return ai_providers.AIResponse(status='err', error='simulated', provider=provider_id, duration_ms=10)
    return orig(provider_id, model, prompt, **kw)
reg.execute = fake

W = workflows
wf = {
  'id': 'wf-mm-test', 'name': 'mm-test',
  'nodes': [
    {'id': 'n-s', 'type': 'start', 'x': 0, 'y': 0, 'title': 'S', 'data': {}},
    {'id': 'n-fail', 'type': 'subagent', 'x': 200, 'y': 0, 'title': 'fail',
     'data': {'assignee': 'sonnet-4.6', 'subject': 'MARKER_FAIL', 'description': 'MARKER_FAIL'}},
    {'id': 'n-hang', 'type': 'subagent', 'x': 200, 'y': 200, 'title': 'hang',
     'data': {'assignee': 'sonnet-4.6',
              'subject': '한국어로 매우 긴 답변을 5000자 이상 작성해주세요.',
              'description': '디테일하게 답해주세요. ' * 50}},
    {'id': 'n-o', 'type': 'output', 'x': 400, 'y': 100, 'title': 'out', 'data': {}},
  ],
  'edges': [
    {'id': 'e1', 'from': 'n-s', 'to': 'n-fail', 'fromPort': 'out', 'toPort': 'in'},
    {'id': 'e2', 'from': 'n-s', 'to': 'n-hang', 'fromPort': 'out', 'toPort': 'in'},
    {'id': 'e3', 'from': 'n-fail', 'to': 'n-o', 'fromPort': 'out', 'toPort': 'in'},
    {'id': 'e4', 'from': 'n-hang', 'to': 'n-o', 'fromPort': 'out', 'toPort': 'in'},
  ],
}
runId = W._new_run_id()
W._runs_cache_set(runId, {'id': runId, 'wfId': wf['id'], 'status': 'running',
                          'startedAt': int(time.time()*1000), 'nodeResults': {}})
t0 = time.time()
ok, results, _ = W._run_one_iteration(wf, runId, 0)
elapsed = time.time() - t0
out = {
    'elapsed_s': round(elapsed, 2),
    'ok': ok,
    'fail_status': (results.get('n-fail') or {}).get('status'),
    'hang_present': 'n-hang' in results,
}
print(json.dumps(out))
`;

const r = await run('python3', ['-c', py]);
if (r.code !== 0) {
  console.error('python failed:', r.err);
  process.exit(2);
}
const last = r.out.trim().split('\n').pop();
const stats = JSON.parse(last);
console.log('--- fail-fast regression ---');
console.log('  elapsed:', stats.elapsed_s + 's');
console.log('  ok:', stats.ok);
console.log('  n-fail status:', stats.fail_status);
console.log('  n-hang in results:', stats.hang_present);

const PASS = stats.elapsed_s < 5 && stats.fail_status === 'err' && !stats.ok;
console.log(PASS ? 'PASS' : 'FAIL: regression introduced');
process.exit(PASS ? 0 : 1);
