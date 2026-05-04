// Skills are markdown files in <configDir>/skills/<name>.md whose contents
// are prepended to the system prompt when chat or agent runs with --skill.
//
// This is the OpenClaw "skill" concept reduced to its load-bearing core:
// reusable instruction bundles, named, locally stored, no remote registry.
//
// Why .md and not JSON-with-content: skills are written by humans for
// humans, and markdown keeps headers / lists / code blocks readable both
// in the file system and inside the model prompt.

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const SKILLS_DIRNAME = 'skills';
const SKILL_EXT = '.md';

export function defaultConfigDir() {
  return process.env.LAZYCLAW_CONFIG_DIR || path.join(os.homedir(), '.lazyclaw');
}

export function skillsDir(configDir = defaultConfigDir()) {
  return path.join(configDir, SKILLS_DIRNAME);
}

export function skillPath(name, configDir = defaultConfigDir()) {
  if (!name || /[/\\]/.test(name) || name === '.' || name === '..' || name.startsWith('.')) {
    throw new Error(`invalid skill name: ${name}`);
  }
  return path.join(skillsDir(configDir), `${name}${SKILL_EXT}`);
}

export function listSkills(configDir = defaultConfigDir()) {
  const dir = skillsDir(configDir);
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter(name => name.endsWith(SKILL_EXT))
    .map(name => {
      const full = path.join(dir, name);
      const stat = fs.statSync(full);
      const head = readFirstLine(full);
      return {
        name: name.slice(0, -SKILL_EXT.length),
        path: full,
        bytes: stat.size,
        mtimeMs: stat.mtimeMs,
        summary: head.replace(/^#+\s*/, '').slice(0, 120),
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

function readFirstLine(p) {
  try {
    const buf = fs.readFileSync(p, 'utf8');
    const nl = buf.indexOf('\n');
    return nl < 0 ? buf : buf.slice(0, nl);
  } catch { return ''; }
}

export function loadSkill(name, configDir = defaultConfigDir()) {
  const p = skillPath(name, configDir);
  if (!fs.existsSync(p)) throw new Error(`skill not found: ${name}`);
  return fs.readFileSync(p, 'utf8');
}

export function installSkill(name, content, configDir = defaultConfigDir()) {
  const p = skillPath(name, configDir);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, content);
  return p;
}

export function removeSkill(name, configDir = defaultConfigDir()) {
  const p = skillPath(name, configDir);
  if (fs.existsSync(p)) fs.unlinkSync(p);
}

/**
 * Compose the system prompt for a chat/agent invocation. Concatenates each
 * named skill's contents with a separator, in the order given. Returns null
 * when no skills are requested so the caller can pass through unchanged.
 *
 * @param {string[]} names
 * @param {string} [configDir]
 */
export function composeSystemPrompt(names, configDir = defaultConfigDir()) {
  if (!names || names.length === 0) return null;
  const blocks = [];
  for (const n of names) {
    const trimmed = String(n || '').trim();
    if (!trimmed) continue;
    const body = loadSkill(trimmed, configDir);
    blocks.push(`<!-- skill: ${trimmed} -->\n${body.trim()}`);
  }
  return blocks.length ? blocks.join('\n\n---\n\n') : null;
}
