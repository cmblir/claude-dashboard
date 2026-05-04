import { test, expect } from '@playwright/test';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { spawnSync } from 'node:child_process';

const REPO_ROOT = process.cwd();
const CLI = path.join(REPO_ROOT, 'src/lazyclaw/cli.mjs');

function tmp(prefix: string) {
  return fs.mkdtempSync(path.join(os.tmpdir(), `lc-${prefix}-`));
}

test('phase 5 — full integration: configure → run with AI node → kill → resume → complete', () => {
  const cfgDir = tmp('p5-cfg');
  const stateDir = tmp('p5-state');
  const sentinel = path.join(stateDir, 'rec.txt');

  // Configure provider via CLI.
  const setProv = spawnSync(process.execPath, [CLI, 'config', 'set', 'provider', 'mock'], {
    encoding: 'utf8',
    env: { ...process.env, LAZYCLAW_CONFIG_DIR: cfgDir },
  });
  expect(setProv.status).toBe(0);

  // Workflow with an AI node that consumes the mock provider.
  const wf = path.join(stateDir, 'wf-ai.mjs');
  const registryUrl = 'file://' + path.join(REPO_ROOT, 'src/lazyclaw/providers/registry.mjs');
  fs.writeFileSync(wf, `
    import fs from 'node:fs';
    import { PROVIDERS } from ${JSON.stringify(registryUrl)};
    const SENT = ${JSON.stringify(sentinel)};
    const FAIL = process.env.LC_FAIL_AT;
    function append(s){ fs.appendFileSync(SENT, s + '\\n'); }
    async function ai(prompt){
      let acc = '';
      for await (const c of PROVIDERS.mock.sendMessage([{role:'user', content: prompt}], {})) acc += c;
      return acc;
    }
    export const nodes = [
      { id: 'n1', type: 'cmd', async execute(){ append('n1'); return 'init'; } },
      { id: 'n2', type: 'ai',  async execute(input){ append('n2'); return await ai(input); } },
      { id: 'n3', type: 'cmd', async execute(input){ append('n3'); if(FAIL==='3') throw new Error('forced'); return input + '|n3'; } },
      { id: 'n4', type: 'ai',  async execute(input){ append('n4'); return await ai(input); } },
      { id: 'n5', type: 'cmd', async execute(input){ append('n5'); return input + '|done'; } },
    ];
  `);

  const sid = 'p5-session';

  // First run: simulate "kill" by injecting failure at node 3.
  const r1 = spawnSync(process.execPath, [CLI, 'run', sid, wf, '--dir', stateDir], {
    encoding: 'utf8',
    env: { ...process.env, LC_FAIL_AT: '3' },
  });
  expect(r1.status).toBe(1);
  const after1 = fs.readFileSync(sentinel, 'utf8').trim().split('\n');
  expect(after1).toEqual(['n1', 'n2', 'n3']);
  const stateAfter1 = JSON.parse(fs.readFileSync(path.join(stateDir, `${sid}.json`), 'utf8'));
  expect(stateAfter1.nodes.n1.status).toBe('success');
  expect(stateAfter1.nodes.n2.status).toBe('success');
  expect(stateAfter1.nodes.n3.status).toBe('failed');
  expect(stateAfter1.nodes.n4.status).toBe('pending');
  expect(stateAfter1.nodes.n5.status).toBe('pending');

  // Resume — no failure, should pick up at n3 and complete.
  const r2 = spawnSync(process.execPath, [CLI, 'resume', sid, wf, '--dir', stateDir], {
    encoding: 'utf8',
    env: { ...process.env },
  });
  expect(r2.status).toBe(0);
  const after2 = fs.readFileSync(sentinel, 'utf8').trim().split('\n');
  // n1+n2 must NOT have re-executed.
  expect(after2).toEqual(['n1', 'n2', 'n3', 'n3', 'n4', 'n5']);
  const stateAfter2 = JSON.parse(fs.readFileSync(path.join(stateDir, `${sid}.json`), 'utf8'));
  for (const id of ['n1', 'n2', 'n3', 'n4', 'n5']) {
    expect(stateAfter2.nodes[id].status).toBe('success');
  }
});
