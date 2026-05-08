// Config-driven CLI surfaces — auth-profile rotation, pairing
// (sender allowlist), nodes (device registration), and outbound
// messaging webhooks. Each one is a thin record-keeper layered on
// top of the existing readConfig / writeConfig pair: the CLI never
// stores a separate file.
//
// All four were called out as OpenClaw parity gaps; we implement
// them as plain config keys here so the SAME `lazyclaw config get`
// flow keeps working and `lazyclaw export | jq` already covers
// backups without us writing a second exporter.

// Auth profiles ────────────────────────────────────────────────
//
// cfg.authProfiles[provider] = [{ key, label, addedAt }]
//
// Picked over a single `api-key` field so a user can keep multiple
// keys for the same provider (work / personal / spare) and rotate
// when one hits a rate limit. The rotation cursor lives in
// cfg.authActiveProfile[provider] = label so the choice persists
// across invocations.

export function authList(cfg, provider) {
  const profiles = (cfg.authProfiles || {})[provider] || [];
  return profiles.map((p) => ({
    label: p.label,
    addedAt: p.addedAt,
    keyMasked: maskKey(p.key),
  }));
}

export function authAdd(cfg, provider, key, label) {
  if (!provider) throw new Error('provider is required');
  if (!key) throw new Error('key is required');
  cfg.authProfiles = cfg.authProfiles || {};
  cfg.authProfiles[provider] = cfg.authProfiles[provider] || [];
  const lbl = (label || `profile-${cfg.authProfiles[provider].length + 1}`).trim();
  if (cfg.authProfiles[provider].some((p) => p.label === lbl)) {
    throw new Error(`profile "${lbl}" already exists for ${provider}`);
  }
  cfg.authProfiles[provider].push({ key, label: lbl, addedAt: new Date().toISOString() });
  // First-added profile becomes active so the user gets working
  // auth rotation without a separate `auth use` step.
  cfg.authActiveProfile = cfg.authActiveProfile || {};
  if (!cfg.authActiveProfile[provider]) cfg.authActiveProfile[provider] = lbl;
  return lbl;
}

export function authRemove(cfg, provider, label) {
  const arr = (cfg.authProfiles || {})[provider] || [];
  const idx = arr.findIndex((p) => p.label === label);
  if (idx < 0) throw new Error(`no profile "${label}" for ${provider}`);
  arr.splice(idx, 1);
  if ((cfg.authActiveProfile || {})[provider] === label) {
    cfg.authActiveProfile[provider] = arr[0]?.label || '';
  }
}

export function authUse(cfg, provider, label) {
  const arr = (cfg.authProfiles || {})[provider] || [];
  if (!arr.some((p) => p.label === label)) {
    throw new Error(`no profile "${label}" for ${provider}`);
  }
  cfg.authActiveProfile = cfg.authActiveProfile || {};
  cfg.authActiveProfile[provider] = label;
}

export function authRotate(cfg, provider) {
  const arr = (cfg.authProfiles || {})[provider] || [];
  if (arr.length < 2) return null;
  cfg.authActiveProfile = cfg.authActiveProfile || {};
  const cur = cfg.authActiveProfile[provider];
  const idx = arr.findIndex((p) => p.label === cur);
  const next = arr[(idx + 1) % arr.length];
  cfg.authActiveProfile[provider] = next.label;
  return next.label;
}

// Resolves the api-key the chat / agent flow should send. Falls
// back to the legacy single `api-key` field so existing configs
// keep working without a migration.
export function resolveApiKey(cfg, provider) {
  const arr = (cfg.authProfiles || {})[provider] || [];
  const active = (cfg.authActiveProfile || {})[provider];
  const hit = arr.find((p) => p.label === active) || arr[0];
  if (hit?.key) return hit.key;
  return cfg['api-key'] || '';
}

function maskKey(key) {
  if (!key) return '';
  const s = String(key);
  if (s.length <= 8) return '****' + s.slice(-2);
  return s.slice(0, 4) + '…' + s.slice(-4);
}

// Pairing (sender allowlist) ───────────────────────────────────
//
// cfg.pairing = [{ id, label, addedAt }]
//
// Sender ids are the opaque strings the messaging layer hands us
// (e.g. Slack member id, Discord user id, phone number for SMS
// bridges). Anything that isn't on the allowlist gets rejected by
// the inbound handler — same shape as openclaw `pairing approve`.

export function pairingList(cfg) {
  return (cfg.pairing || []).slice();
}

export function pairingAdd(cfg, id, label) {
  if (!id) throw new Error('id is required');
  cfg.pairing = cfg.pairing || [];
  if (cfg.pairing.some((p) => p.id === id)) {
    throw new Error(`id "${id}" already paired`);
  }
  cfg.pairing.push({ id, label: label || '', addedAt: new Date().toISOString() });
}

export function pairingRemove(cfg, id) {
  const arr = cfg.pairing || [];
  const idx = arr.findIndex((p) => p.id === id);
  if (idx < 0) throw new Error(`id "${id}" not found`);
  arr.splice(idx, 1);
}

export function pairingHas(cfg, id) {
  return (cfg.pairing || []).some((p) => p.id === id);
}

// Nodes (device registration) ──────────────────────────────────
//
// cfg.nodes = [{ id, platform, label, registeredAt }]
//
// CLI side of `openclaw nodes` — the actual mobile companion apps
// aren't in scope here, but the registration table lets a future
// app (or just `curl`) authenticate against `lazyclaw daemon`.
// Platform is free-form ('macos' / 'ios' / 'android' / 'web' /
// 'cli') so we don't constrain future surfaces.

export function nodesList(cfg) {
  return (cfg.nodes || []).slice();
}

export function nodesRegister(cfg, id, platform = 'cli', label = '') {
  if (!id) throw new Error('id is required');
  cfg.nodes = cfg.nodes || [];
  if (cfg.nodes.some((n) => n.id === id)) {
    throw new Error(`node "${id}" already registered`);
  }
  cfg.nodes.push({
    id,
    platform: String(platform || 'cli').toLowerCase(),
    label: label || '',
    registeredAt: new Date().toISOString(),
  });
}

export function nodesRemove(cfg, id) {
  const arr = cfg.nodes || [];
  const idx = arr.findIndex((n) => n.id === id);
  if (idx < 0) throw new Error(`node "${id}" not found`);
  arr.splice(idx, 1);
}

// Messaging — outbound webhooks ────────────────────────────────
//
// cfg.messaging.webhooks[name] = { kind: 'slack'|'discord', url }
//
// We deliberately store webhook URLs (not bot tokens) because that
// keeps the install footprint small — any user can paste a Slack
// "Incoming Webhook" URL and start sending without registering an
// app. Bot tokens can be added later as a separate `messaging.tokens`
// shape when we wire the bidirectional inbox.

const WEBHOOK_PATTERNS = {
  slack:   /^https?:\/\/hooks\.slack\.com\//i,
  discord: /^https?:\/\/(?:discord(?:app)?\.com|canary\.discord\.com)\/api\/webhooks\//i,
};

function detectKind(url) {
  for (const [kind, re] of Object.entries(WEBHOOK_PATTERNS)) {
    if (re.test(url)) return kind;
  }
  return 'generic';
}

export function messageList(cfg) {
  const map = (cfg.messaging || {}).webhooks || {};
  return Object.entries(map).map(([name, v]) => ({
    name,
    kind: v.kind,
    urlMasked: v.url ? v.url.slice(0, 32) + '…' + v.url.slice(-6) : '',
  }));
}

export function messageAdd(cfg, name, url, kindOverride) {
  if (!name) throw new Error('name is required');
  if (!url) throw new Error('url is required');
  cfg.messaging = cfg.messaging || {};
  cfg.messaging.webhooks = cfg.messaging.webhooks || {};
  if (cfg.messaging.webhooks[name]) {
    throw new Error(`webhook "${name}" already exists`);
  }
  cfg.messaging.webhooks[name] = {
    kind: kindOverride || detectKind(url),
    url,
    addedAt: new Date().toISOString(),
  };
}

export function messageRemove(cfg, name) {
  const map = (cfg.messaging || {}).webhooks || {};
  if (!map[name]) throw new Error(`webhook "${name}" not found`);
  delete map[name];
}

export async function messageSend(cfg, name, text, opts = {}) {
  const map = (cfg.messaging || {}).webhooks || {};
  const hook = map[name];
  if (!hook) throw new Error(`webhook "${name}" not configured — add via \`lazyclaw message add\``);
  const fetchFn = opts.fetch || globalThis.fetch;
  if (!fetchFn) throw new Error('no fetch implementation');

  // Slack and Discord both accept a JSON body but with different key
  // shapes — Slack uses { text }, Discord uses { content }. The
  // generic kind sends a plain JSON envelope so user-supplied
  // endpoints can ingest whatever shape they like via { text }.
  let body;
  if (hook.kind === 'discord') body = JSON.stringify({ content: text });
  else                          body = JSON.stringify({ text });

  const res = await fetchFn(hook.url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body,
  });
  if (!res.ok) {
    const errText = (await (res.text?.() || Promise.resolve(''))).slice(0, 300);
    throw new Error(`webhook ${hook.kind} send failed: ${res.status} ${errText}`);
  }
  return { ok: true, kind: hook.kind, status: res.status };
}
