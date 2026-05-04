// Tiny structured logger — JSON-line output, level-gated, no transitive deps.
//
// Why not pino/winston: a single dep would dwarf the entire CLI. JSON-line
// is the de-facto observability format (jq-friendly, ingestible by every
// log shipper) and an 80-line module covers our needs.
//
// Levels: debug < info < warn < error. Setting LAZYCLAW_LOG_LEVEL=warn
// silences info+debug. The default (info) keeps user-meaningful events
// without per-request noise; the daemon's access log lives at info so
// it's on by default once the logger is wired.

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };

function levelToNum(name) {
  const n = LEVELS[String(name || '').toLowerCase()];
  return Number.isFinite(n) ? n : LEVELS.info;
}

/**
 * Build a logger. The `sink` callback receives the JSON string per
 * record so tests can capture without monkey-patching process.stderr.
 *
 * @param {{ level?: string, sink?: (line: string) => void, base?: object, now?: () => number }} [opts]
 */
export function createLogger(opts = {}) {
  const minLevel = levelToNum(opts.level);
  const sink = opts.sink || ((line) => { process.stderr.write(line + '\n'); });
  const now = opts.now || (() => Date.now());
  const base = opts.base || {};

  const log = (level, msg, fields) => {
    if (LEVELS[level] < minLevel) return;
    const record = {
      ts: new Date(now()).toISOString(),
      level,
      msg,
      ...base,
      ...(fields || {}),
    };
    sink(JSON.stringify(record));
  };

  return {
    minLevel,
    debug: (msg, fields) => log('debug', msg, fields),
    info:  (msg, fields) => log('info',  msg, fields),
    warn:  (msg, fields) => log('warn',  msg, fields),
    error: (msg, fields) => log('error', msg, fields),
    child(extraBase) {
      return createLogger({ ...opts, base: { ...base, ...extraBase } });
    },
  };
}

export { LEVELS, levelToNum };
