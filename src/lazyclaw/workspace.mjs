// Workspace — OpenClaw-parity convention for project-rooted system
// prompts. A workspace is a directory at
//
//   ~/.lazyclaw/workspaces/<name>/
//     ├─ AGENTS.md   — what the assistant should DO
//     ├─ SOUL.md     — how the assistant should THINK / behave
//     ├─ TOOLS.md    — what tools / commands it can reach for
//
// `lazyclaw chat --workspace foo` (or `agent --workspace foo`) reads
// the three files and synthesises a single system prompt. Skill
// composition still works alongside — workspace lives at the head,
// then any --skill content. Missing files are skipped silently so
// a half-set-up workspace still works.
//
// Why three files instead of one giant SYSTEM.md: the OpenClaw
// convention separates concerns so reviewers / teammates can edit
// the "what" (AGENTS) without churning the "how" (SOUL) — and the
// TOOLS file commonly comes from a generator (read from
// `lazyclaw providers list` etc).

import fs from 'node:fs';
import path from 'node:path';

const FILES = [
  { name: 'AGENTS.md', heading: 'AGENTS — what to do' },
  { name: 'SOUL.md',   heading: 'SOUL — how to behave' },
  { name: 'TOOLS.md',  heading: 'TOOLS — what is available' },
];

export function workspaceRoot(cfgDir) {
  return path.join(cfgDir, 'workspaces');
}

export function workspaceDir(cfgDir, name) {
  if (!name || !/^[A-Za-z0-9_.-]+$/.test(name)) {
    throw new Error('workspace name must match [A-Za-z0-9_.-]+');
  }
  return path.join(workspaceRoot(cfgDir), name);
}

// List every workspace under ~/.lazyclaw/workspaces/. Returns
// metadata (which of the three files are present, total size) so
// `lazyclaw workspace list` can show the user at a glance which
// workspaces are populated vs scaffolded-but-empty.
export function listWorkspaces(cfgDir) {
  const root = workspaceRoot(cfgDir);
  if (!fs.existsSync(root)) return [];
  const out = [];
  for (const name of fs.readdirSync(root)) {
    const dir = path.join(root, name);
    let st;
    try { st = fs.statSync(dir); } catch { continue; }
    if (!st.isDirectory()) continue;
    const files = {};
    let totalBytes = 0;
    for (const f of FILES) {
      const p = path.join(dir, f.name);
      try {
        const fst = fs.statSync(p);
        files[f.name] = { bytes: fst.size, mtimeMs: fst.mtimeMs };
        totalBytes += fst.size;
      } catch { /* missing — leave undefined */ }
    }
    out.push({ name, dir, files, totalBytes });
  }
  // Newest-modified first.
  out.sort((a, b) => {
    const ma = Math.max(0, ...Object.values(a.files).map((f) => f.mtimeMs));
    const mb = Math.max(0, ...Object.values(b.files).map((f) => f.mtimeMs));
    return mb - ma;
  });
  return out;
}

// Scaffold a fresh workspace. Each file gets a tiny stub the user
// can replace. We deliberately don't pre-populate from a template
// repo — the OpenClaw stubs are intentionally short so the user
// reads them before editing.
export function initWorkspace(cfgDir, name) {
  const dir = workspaceDir(cfgDir, name);
  if (fs.existsSync(dir)) throw new Error(`workspace "${name}" already exists`);
  fs.mkdirSync(dir, { recursive: true });
  const stubs = {
    'AGENTS.md':
`# Agents

What this assistant is asked to DO. Plain English.

- Primary goal: ...
- Daily routines: ...
- When stuck, escalate to: ...
`,
    'SOUL.md':
`# Soul

How the assistant should BEHAVE — voice, defaults, hard rules.

- Tone: ...
- Defaults: prefer concise answers; ask before destructive actions.
- Never: hand-wave, fabricate citations, or skip running tests.
`,
    'TOOLS.md':
`# Tools

What the assistant can reach for, and how to invoke each one.

- \`lazyclaw browse <url>\` — fetch + markdown-ify a page
- \`lazyclaw message send <name> <text>\` — Slack / Discord webhook
- \`lazyclaw agent ...\` — one-shot LLM call

Add project-specific tools below.
`,
  };
  for (const [name, body] of Object.entries(stubs)) {
    fs.writeFileSync(path.join(dir, name), body, 'utf8');
  }
  return dir;
}

// Compose the three files into a single system prompt. Returns ''
// when the workspace is empty (caller falls back to whatever it had
// before). Skip-on-missing keeps the contract forgiving.
export function composeWorkspacePrompt(cfgDir, name) {
  if (!name) return '';
  const dir = workspaceDir(cfgDir, name);
  if (!fs.existsSync(dir)) {
    throw new Error(`workspace "${name}" not found at ${dir}`);
  }
  const blocks = [];
  for (const f of FILES) {
    const p = path.join(dir, f.name);
    let body;
    try { body = fs.readFileSync(p, 'utf8').trim(); } catch { continue; }
    if (!body) continue;
    blocks.push(`# ${f.heading}\n\n${body}`);
  }
  return blocks.join('\n\n---\n\n');
}

// Read just one file's content so the CLI can `workspace show`
// without printing all three.
export function readWorkspaceFile(cfgDir, name, fileName) {
  const dir = workspaceDir(cfgDir, name);
  const allowed = FILES.map((f) => f.name);
  if (!allowed.includes(fileName)) {
    throw new Error(`unknown file "${fileName}" — must be one of ${allowed.join(', ')}`);
  }
  const p = path.join(dir, fileName);
  return fs.readFileSync(p, 'utf8');
}

export function removeWorkspace(cfgDir, name) {
  const dir = workspaceDir(cfgDir, name);
  if (!fs.existsSync(dir)) throw new Error(`workspace "${name}" not found`);
  fs.rmSync(dir, { recursive: true, force: true });
}

export const WORKSPACE_FILES = FILES.map((f) => f.name);
