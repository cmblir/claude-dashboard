import { test, expect } from '@playwright/test';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { spawnSync } from 'node:child_process';

import {
  runPersistent,
  loadState,
  statePath,
} from '../src/lazyclaw/workflow/persistent.mjs';

const REPO_ROOT = process.cwd();

interface PNode {
  id: string;
  type: string;
  execute(input: unknown): Promise<unknown>;
}

function tmpDir(prefix: string): string {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), `lc-${prefix}-`));
  return d;
}

function makeChain(count: number, opts: { failAt?: number; rec?: string[] } = {}): PNode[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `n${i + 1}`,
    type: 'test',
    async execute(input: unknown) {
      opts.rec?.push(`n${i + 1}`);
      if (opts.failAt && i + 1 === opts.failAt) throw new Error(`fail@n${opts.failAt}`);
      return ((typeof input === 'number' ? input : 0) + 1);
    },
  }));
}

test.describe('Phase 2 — Auto-resume', () => {
  test('state persists to disk before and after each node', async () => {
    const dir = tmpDir('p2a');
    const sid = 'sess-persist-1';
    const seenAfterEach: string[][] = [];
    const nodes: PNode[] = Array.from({ length: 3 }, (_, i) => ({
      id: `n${i + 1}`,
      type: 'test',
      async execute() {
        // While running this node, file must exist with status=running for it.
        const s = loadState(sid, dir);
        seenAfterEach.push(Object.entries(s!.nodes).map(([id, v]) => `${id}:${v.status}`));
        return i;
      },
    }));
    const r = await runPersistent(nodes, { sessionId: sid, dir });
    expect(r.success).toBe(true);
    expect(fs.existsSync(statePath(sid, dir))).toBe(true);
    // While n1 was running, n1 status was 'running'.
    expect(seenAfterEach[0]).toContain('n1:running');
    // After full run, all success.
    const finalState = loadState(sid, dir)!;
    for (const id of ['n1', 'n2', 'n3']) {
      expect(finalState.nodes[id].status).toBe('success');
    }
  });

  test('resume after simulated kill skips completed nodes and re-runs interrupted', async () => {
    const dir = tmpDir('p2b');
    const sid = 'sess-resume-1';

    // First run: nodes 1..5 succeed, then we throw to simulate kill before 6.
    const rec1: string[] = [];
    const nodesRun1: PNode[] = makeChain(10, { failAt: 6, rec: rec1 });
    const r1 = await runPersistent(nodesRun1, { sessionId: sid, dir });
    expect(r1.success).toBe(false);
    expect(rec1).toEqual(['n1', 'n2', 'n3', 'n4', 'n5', 'n6']);

    // Simulate "kill mid-flight" by hand-editing n5 back to running, n6 absent.
    const mid = loadState(sid, dir)!;
    mid.nodes['n5'] = { status: 'running', attempts: 1 };
    mid.nodes['n6'] = { status: 'pending' };
    fs.writeFileSync(statePath(sid, dir), JSON.stringify(mid, null, 2));

    // Second run: a fresh node set with no failure injection. Resume must
    // re-run the interrupted n5 cleanly and continue 6..10. Nodes 1..4 must
    // be skipped (status='success').
    const rec2: string[] = [];
    const nodesRun2: PNode[] = makeChain(10, { rec: rec2 });
    const r2 = await runPersistent(nodesRun2, { sessionId: sid, dir });
    expect(r2.success).toBe(true);
    // Completed nodes do not re-execute.
    for (const skipped of ['n1', 'n2', 'n3', 'n4']) {
      expect(rec2).not.toContain(skipped);
    }
    // Interrupted node + remainder did execute.
    expect(rec2).toEqual(['n5', 'n6', 'n7', 'n8', 'n9', 'n10']);
    expect(r2.executedNodes).toEqual(['n5', 'n6', 'n7', 'n8', 'n9', 'n10']);
  });

  test('timeout retries with exponential backoff (max 3) and gives up', async () => {
    const dir = tmpDir('p2c');
    const sid = 'sess-timeout-1';
    let calls = 0;
    const slept: number[] = [];
    const nodes: PNode[] = [
      {
        id: 'slow',
        type: 'test',
        async execute() {
          calls++;
          // Always exceed timeout window.
          await new Promise(r => setTimeout(r, 50));
          return 'never';
        },
      },
    ];
    const r = await runPersistent(nodes, {
      sessionId: sid,
      dir,
      timeoutMs: 5,
      baseDelayMs: 10,
      maxRetries: 3,
      sleep: async (ms: number) => { slept.push(ms); /* skip real sleep */ },
    });
    expect(r.success).toBe(false);
    expect(calls).toBe(3); // 3 attempts
    // Backoff: 10, 20 (between attempts 1→2 and 2→3). No sleep after final fail.
    expect(slept).toEqual([10, 20]);
    expect(r.state.nodes.slow.status).toBe('failed');
    expect(r.state.nodes.slow.attempts).toBe(3);
  });

  test('CLI resume command continues from checkpoint', async () => {
    const dir = tmpDir('p2d');
    const sid = 'sess-cli-1';
    const sentinel = path.join(dir, 'cli-rec.txt');

    // Workflow fixture: writes its node id to sentinel. node 4 throws on
    // first invocation only (controlled by env var), then on resume succeeds.
    const wfFile = path.join(dir, 'wf.mjs');
    fs.writeFileSync(wfFile, `
      import fs from 'node:fs';
      const SENT = ${JSON.stringify(sentinel)};
      const FAIL = process.env.LC_FAIL_AT;
      function append(line){ fs.appendFileSync(SENT, line + '\\n'); }
      export const nodes = Array.from({length:8}, (_,i) => ({
        id: 'n' + (i+1),
        type: 'test',
        async execute(input){
          append('n'+(i+1));
          if (FAIL && String(i+1) === FAIL) throw new Error('forced');
          return (typeof input === 'number' ? input : 0) + 1;
        },
      }));
    `);

    const cli = path.join(REPO_ROOT, 'src/lazyclaw/cli.mjs');

    // First run: fail at node 4.
    const r1 = spawnSync(process.execPath, [cli, 'run', sid, wfFile, '--dir', dir], {
      encoding: 'utf8',
      env: { ...process.env, LC_FAIL_AT: '4' },
    });
    expect(r1.status).toBe(1);
    const recAfter1 = fs.readFileSync(sentinel, 'utf8').trim().split('\n');
    expect(recAfter1).toEqual(['n1', 'n2', 'n3', 'n4']);
    const s1 = loadState(sid, dir)!;
    expect(s1.nodes.n4.status).toBe('failed');
    expect(s1.nodes.n3.status).toBe('success');

    // Resume: no failure injection now.
    const r2 = spawnSync(process.execPath, [cli, 'resume', sid, wfFile, '--dir', dir], {
      encoding: 'utf8',
      env: { ...process.env },
    });
    expect(r2.status).toBe(0);
    const recAfter2 = fs.readFileSync(sentinel, 'utf8').trim().split('\n');
    // n1..n3 must NOT have re-executed; n4..n8 must have.
    expect(recAfter2).toEqual(['n1', 'n2', 'n3', 'n4', 'n4', 'n5', 'n6', 'n7', 'n8']);
    const s2 = loadState(sid, dir)!;
    for (const id of ['n1', 'n2', 'n3', 'n4', 'n5', 'n6', 'n7', 'n8']) {
      expect(s2.nodes[id].status).toBe('success');
    }
  });
});
