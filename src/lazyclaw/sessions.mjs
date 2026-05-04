// Persistent chat sessions for LazyClaw.
//
// Storage layout under <configDir>/sessions/:
//   <id>.jsonl — append-only log of {role, content, ts} turns
//
// Why JSONL not a single JSON file:
//   - Atomic append per turn — no read-modify-write race when two
//     terminals talk to the same session.
//   - O(1) write per turn regardless of conversation length.
//   - The last-turn timestamp is the file mtime, so listSessions does
//     not have to read every file to sort.
//
// `loadTurns` is the only operation that reads the whole log; it splits
// on '\n' and JSON.parses each non-empty line, ignoring malformed lines
// rather than failing the chat.

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const SESSIONS_DIRNAME = 'sessions';

export function defaultConfigDir() {
  return process.env.LAZYCLAW_CONFIG_DIR || path.join(os.homedir(), '.lazyclaw');
}

export function sessionsDir(configDir = defaultConfigDir()) {
  return path.join(configDir, SESSIONS_DIRNAME);
}

export function sessionPath(id, configDir = defaultConfigDir()) {
  if (!id || /[/\\]/.test(id) || id === '.' || id === '..') {
    throw new Error(`invalid session id: ${id}`);
  }
  return path.join(sessionsDir(configDir), `${id}.jsonl`);
}

export function listSessions(configDir = defaultConfigDir()) {
  const dir = sessionsDir(configDir);
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter(name => name.endsWith('.jsonl'))
    .map(name => {
      const fullPath = path.join(dir, name);
      const stat = fs.statSync(fullPath);
      return {
        id: name.slice(0, -'.jsonl'.length),
        path: fullPath,
        bytes: stat.size,
        mtimeMs: stat.mtimeMs,
      };
    })
    .sort((a, b) => b.mtimeMs - a.mtimeMs);
}

export function loadTurns(id, configDir = defaultConfigDir()) {
  const p = sessionPath(id, configDir);
  if (!fs.existsSync(p)) return [];
  const raw = fs.readFileSync(p, 'utf8');
  const out = [];
  for (const line of raw.split('\n')) {
    if (!line) continue;
    try { out.push(JSON.parse(line)); }
    catch { /* skip malformed line */ }
  }
  return out;
}

export function appendTurn(id, role, content, configDir = defaultConfigDir()) {
  if (role !== 'user' && role !== 'assistant' && role !== 'system') {
    throw new Error(`invalid role: ${role}`);
  }
  const p = sessionPath(id, configDir);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  const line = JSON.stringify({ role, content: String(content ?? ''), ts: Date.now() }) + '\n';
  fs.appendFileSync(p, line);
}

export function clearSession(id, configDir = defaultConfigDir()) {
  const p = sessionPath(id, configDir);
  if (fs.existsSync(p)) fs.unlinkSync(p);
}

export function resetSession(id, configDir = defaultConfigDir()) {
  // Truncate without removing — mtime advances so the session stays at
  // the top of `listSessions` order (it was just touched).
  const p = sessionPath(id, configDir);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, '');
}
