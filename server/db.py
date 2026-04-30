"""SQLite session index — connection factory + schema initialization.

`~/.claude-dashboard.db` (path overridable via `CLAUDE_DASHBOARD_DB`).
Manages `sessions`, `tool_uses`, `agent_edges`, `scores_history` tables.
"""
from __future__ import annotations

import sqlite3
import threading

from .config import DB_PATH


# Module-level init guard — _db_init() is called from every API handler,
# but only the first call needs to do work.
_INITIALIZED: bool = False
_INIT_LOCK = threading.Lock()


def _db() -> sqlite3.Connection:
    """sqlite3.Row factory connection. Caller closes via with-block.

    Note: WAL pragma is set once in _db_init(); journal_mode is a database-level
    setting and persists across connections.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _db_init() -> None:
    """Create tables + run schema migrations. Idempotent — first call only."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    with _INIT_LOCK:
        if _INITIALIZED:
            return
        with _db() as c:
            # Set WAL once at the database level (persists across connections).
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
              session_id TEXT PRIMARY KEY,
              project TEXT,
              project_dir TEXT,
              cwd TEXT,
              jsonl_path TEXT,
              started_at INTEGER,
              ended_at INTEGER,
              duration_ms INTEGER,
              message_count INTEGER DEFAULT 0,
              user_msg_count INTEGER DEFAULT 0,
              assistant_msg_count INTEGER DEFAULT 0,
              tool_use_count INTEGER DEFAULT 0,
              error_count INTEGER DEFAULT 0,
              agent_call_count INTEGER DEFAULT 0,
              subagent_types TEXT,
              model TEXT,
              first_user_prompt TEXT,
              last_summary TEXT,
              score INTEGER DEFAULT 0,
              score_breakdown TEXT,
              indexed_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS tool_uses (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT,
              ts INTEGER,
              tool TEXT,
              subagent_type TEXT,
              input_summary TEXT,
              had_error INTEGER DEFAULT 0,
              turn_tokens INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_tool_session ON tool_uses(session_id);
            CREATE INDEX IF NOT EXISTS idx_tool_name ON tool_uses(tool);
            CREATE TABLE IF NOT EXISTS agent_edges (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT,
              src TEXT,
              dst TEXT,
              ts INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_edge_session ON agent_edges(session_id);
            CREATE TABLE IF NOT EXISTS scores_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT,
              ts INTEGER,
              score INTEGER,
              breakdown TEXT
            );
            """)
            # Migration: add missing columns (existing-DB compatibility)
            try:
                cols = {r["name"] for r in c.execute("PRAGMA table_info(sessions)").fetchall()}
                for col, typ in [
                    ("cwd", "TEXT"),
                    ("input_tokens", "INTEGER DEFAULT 0"),
                    ("output_tokens", "INTEGER DEFAULT 0"),
                    ("cache_read_tokens", "INTEGER DEFAULT 0"),
                    ("cache_creation_tokens", "INTEGER DEFAULT 0"),
                    ("total_tokens", "INTEGER DEFAULT 0"),
                    ("mtime", "INTEGER DEFAULT 0"),
                ]:
                    if col not in cols:
                        c.execute(f"ALTER TABLE sessions ADD COLUMN {col} {typ}")
                tcols = {r["name"] for r in c.execute("PRAGMA table_info(tool_uses)").fetchall()}
                if "turn_tokens" not in tcols:
                    c.execute("ALTER TABLE tool_uses ADD COLUMN turn_tokens INTEGER DEFAULT 0")

                # Sessions table query indexes (added in v2.46 perf pass).
                c.executescript("""
                CREATE INDEX IF NOT EXISTS idx_sess_started ON sessions(started_at);
                CREATE INDEX IF NOT EXISTS idx_sess_score ON sessions(score, tool_use_count);
                CREATE INDEX IF NOT EXISTS idx_sess_cwd_started ON sessions(cwd, started_at);
                -- v2.48 perf pass: kill TEMP B-TREE sorts on alternate
                -- "sessions list" sort orders. Each is a covering index for
                -- ORDER BY <col> DESC LIMIT N.
                CREATE INDEX IF NOT EXISTS idx_sess_tool_use_count ON sessions(tool_use_count DESC);
                CREATE INDEX IF NOT EXISTS idx_sess_total_tokens ON sessions(total_tokens DESC);
                CREATE INDEX IF NOT EXISTS idx_sess_duration_ms ON sessions(duration_ms DESC);
                """)

                # tool_uses indexes — existing idx_tool_session covers
                # per-session lookups, idx_tool_name covers tool-distribution
                # aggregation. Add a subagent-aware index for stats/agent_graph
                # which filter by subagent_type and time window.
                c.executescript("""
                CREATE INDEX IF NOT EXISTS idx_tool_subagent_ts ON tool_uses(subagent_type, ts);
                """)

                # agent_edges — ts-window queries (agent_graph edges) full-scan
                # currently; add a ts index so growth stays bounded.
                c.executescript("""
                CREATE INDEX IF NOT EXISTS idx_edge_ts ON agent_edges(ts);
                """)

                # Workflow cost tracking table
                c.executescript("""
                CREATE TABLE IF NOT EXISTS workflow_costs (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  run_id TEXT,
                  workflow_id TEXT,
                  node_id TEXT,
                  provider TEXT,
                  model TEXT,
                  tokens_in INTEGER DEFAULT 0,
                  tokens_out INTEGER DEFAULT 0,
                  tokens_total INTEGER DEFAULT 0,
                  cost_usd REAL DEFAULT 0.0,
                  duration_ms INTEGER DEFAULT 0,
                  ts INTEGER,
                  status TEXT DEFAULT 'ok'
                );
                CREATE INDEX IF NOT EXISTS idx_wfcost_run ON workflow_costs(run_id);
                CREATE INDEX IF NOT EXISTS idx_wfcost_provider ON workflow_costs(provider);
                """)

                # v2.47.0 — workflow runs migrated out of the JSON store.
                # Per-iteration node status updates previously rewrote the
                # whole ~/.claude-dashboard-workflows.json under a single
                # global lock; runs now live in their own table so save and
                # run paths no longer serialize on the same lock.
                # Indexed columns are hoisted from the run payload; the rest
                # stays as a single TEXT json blob for read-as-a-unit access.
                c.executescript("""
                CREATE TABLE IF NOT EXISTS workflow_runs (
                  run_id TEXT PRIMARY KEY,
                  workflow_id TEXT NOT NULL,
                  status TEXT NOT NULL,
                  started_at REAL NOT NULL,
                  ended_at REAL,
                  iteration INTEGER DEFAULT 0,
                  total_iterations INTEGER DEFAULT 1,
                  cost_total REAL DEFAULT 0.0,
                  tokens_in INTEGER DEFAULT 0,
                  tokens_out INTEGER DEFAULT 0,
                  payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_workflow ON workflow_runs(workflow_id, started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_status ON workflow_runs(status, started_at DESC);
                -- v2.48 perf pass: global "runs list" path
                -- (`SELECT … FROM workflow_runs ORDER BY started_at DESC LIMIT ?`)
                -- previously SCAN + TEMP B-TREE; this kills the sort.
                CREATE INDEX IF NOT EXISTS idx_runs_started ON workflow_runs(started_at DESC);
                """)

                # run_history — filtered list path
                # (`WHERE source=? AND item_id=? ORDER BY ts DESC LIMIT ?`)
                # used the existing 2-col idx_runhist_item but still incurred
                # a TEMP B-TREE sort. Composite (source, item_id, ts DESC) is
                # a covering ordering for the LIMIT.
                c.executescript("""
                CREATE INDEX IF NOT EXISTS idx_runhist_item_ts ON run_history(source, item_id, ts DESC);
                """)

                # Refresh planner statistics so the new indexes are actually
                # picked. ANALYZE on a small DB is ~milliseconds; gating it
                # behind init means we only pay the cost once per process.
                try:
                    c.execute("ANALYZE")
                except Exception:
                    pass
            except Exception:
                pass
        _INITIALIZED = True
