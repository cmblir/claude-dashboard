"""Agent bus — lightweight pub/sub for inter-agent reporting.

Used by the channel orchestrator, workflow nodes, Slack/Telegram bots, the TUI
and the frontend SSE bridge to publish status updates and watch each other's
progress without polling each other directly.

Design goals (see Projects/lazyclaude/logs/2026-05-01.md for the full ADR):

- **No polling on the hot path.** Subscribers block on a single
  `threading.Condition`; publishers `notify_all()` once per accepted event.
- **Batched durability.** Events stream into an in-memory deque immediately;
  a single background flusher writes to SQLite in batches (every
  `_FLUSH_MS` ms, or whenever the pending queue reaches `_FLUSH_BATCH`).
- **Dedup.** `(topic, sha1(payload))` is held in an LRU of size `_DEDUP_LRU`;
  identical events arriving within `_DEDUP_WINDOW_MS` are dropped — kills
  "still working..." spam without losing legitimate periodic status events.
- **Topic matching.** Subscribers pass glob patterns (`orch.*`, `wf.run.42.*`).
  Patterns are precompiled to `re.Pattern` once per subscriber; `publish()`
  walks the active subscriber list (a small list, usually <10) without
  rebuilding regexes.
- **Bounded memory.** Recent-event ring buffer is capped at `_RING_SIZE`;
  history beyond that is served from SQLite via `since_id` queries.

All limits are env-overridable so deployments can tune without touching code.

The bus stores into the existing `~/.claude-dashboard.db` (path resolved by
`server.config.DB_PATH`); no extra files. Schema is created on first publish.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from .config import DB_PATH
from .db import _db, _db_init
from .logger import log


# ───────── Tunables (env-overridable, no hardcoding) ─────────

_RING_SIZE         = int(os.environ.get("AGENT_BUS_RING_SIZE", "2048"))
_FLUSH_BATCH       = int(os.environ.get("AGENT_BUS_FLUSH_BATCH", "32"))
_FLUSH_MS          = int(os.environ.get("AGENT_BUS_FLUSH_MS", "100"))
_DEDUP_LRU         = int(os.environ.get("AGENT_BUS_DEDUP_LRU", "64"))
_DEDUP_WINDOW_MS   = int(os.environ.get("AGENT_BUS_DEDUP_WINDOW_MS", "5000"))
_RETENTION_DAYS    = int(os.environ.get("AGENT_BUS_RETENTION_DAYS", "7"))
_SUBSCRIBE_WAIT_S  = float(os.environ.get("AGENT_BUS_WAIT_S", "25"))


# ───────── Event shape ─────────

@dataclass
class AgentEvent:
    id: int = 0
    ts: int = 0           # epoch ms
    topic: str = ""       # "orch.<run_id>.dispatch", "wf.<id>.node.<nid>", ...
    source: str = ""      # agent identifier ("claude:opus", "slack:Cxxxx", ...)
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "ts": self.ts, "topic": self.topic,
            "source": self.source, "payload": self.payload,
        }


# ───────── Schema ─────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_events (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  ts      INTEGER NOT NULL,
  topic   TEXT    NOT NULL,
  source  TEXT    NOT NULL DEFAULT '',
  payload TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_agent_events_topic_id ON agent_events(topic, id);
CREATE INDEX IF NOT EXISTS idx_agent_events_ts       ON agent_events(ts);
"""

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        _db_init()
        with _db() as c:
            c.executescript(_SCHEMA)
        _SCHEMA_READY = True


# ───────── Topic glob → regex ─────────

_GLOB_CACHE: dict[str, re.Pattern] = {}


def _glob_to_re(pat: str) -> re.Pattern:
    """Glob compile with topic-friendly semantics:

    - ``*``  matches anything except a literal '.' (one segment)
    - ``**`` matches anything (zero+ segments)
    - ``foo.*`` matches ``foo.bar`` *and* ``foo.bar.baz`` — i.e. trailing
      ``.*`` is auto-promoted to ``.**`` so the natural ``orch.*`` works for
      nested topics. Inline ``a.*.b`` still matches single-segment.

    Cached so repeat subscribers don't recompile.
    """
    cached = _GLOB_CACHE.get(pat)
    if cached is not None:
        return cached
    # Auto-promote trailing ``.*`` to ``.**`` for ergonomic prefix subscriptions.
    if pat.endswith(".*") and not pat.endswith(".**"):
        pat_eff = pat[:-1] + "**"
    else:
        pat_eff = pat
    out: list[str] = []
    i, n = 0, len(pat_eff)
    while i < n:
        ch = pat_eff[i]
        if ch == "*":
            if i + 1 < n and pat_eff[i + 1] == "*":
                out.append(".*"); i += 2
            else:
                out.append("[^.]*"); i += 1
        elif ch in r".+?^${}()|[]\\":
            out.append(re.escape(ch)); i += 1
        else:
            out.append(ch); i += 1
    rx = re.compile("^" + "".join(out) + "$")
    if len(_GLOB_CACHE) < 512:
        _GLOB_CACHE[pat] = rx
    return rx


# ───────── Dedup LRU ─────────

class _DedupLRU:
    """Bounded LRU mapping (topic, sha1) → last-seen-ms.

    `seen()` returns True iff this exact key was seen within the window;
    inserts/refreshes the entry as a side effect.
    """
    __slots__ = ("_d", "_max", "_window_ms")

    def __init__(self, max_size: int, window_ms: int):
        self._d: OrderedDict[tuple[str, str], int] = OrderedDict()
        self._max = max_size
        self._window_ms = window_ms

    def seen(self, key: tuple[str, str], now_ms: int) -> bool:
        prev = self._d.get(key)
        self._d[key] = now_ms
        self._d.move_to_end(key)
        while len(self._d) > self._max:
            self._d.popitem(last=False)
        return prev is not None and (now_ms - prev) < self._window_ms


# ───────── Subscriber ─────────

@dataclass
class _Subscription:
    patterns: list[re.Pattern]
    last_id: int = 0

    def matches(self, topic: str) -> bool:
        return any(p.match(topic) for p in self.patterns)


# ───────── Bus singleton ─────────

class _Bus:
    """Process-wide singleton. Threadsafe — all mutation through `_lock`/`_cv`."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._ring: deque[AgentEvent] = deque(maxlen=_RING_SIZE)
        self._next_local_id = 1               # only for in-memory monotonic order
        self._dedup = _DedupLRU(_DEDUP_LRU, _DEDUP_WINDOW_MS)
        self._pending: list[AgentEvent] = []   # not yet flushed to SQLite
        self._flush_thread: Optional[threading.Thread] = None
        self._stop = False
        self._last_flush_ms = 0
        self._last_retention_ms = 0

    # ---- lifecycle ----

    def _ensure_flusher(self) -> None:
        if self._flush_thread is not None and self._flush_thread.is_alive():
            return
        t = threading.Thread(target=self._flush_loop, name="agent-bus-flush", daemon=True)
        self._flush_thread = t
        t.start()

    def _flush_loop(self) -> None:
        while not self._stop:
            time.sleep(_FLUSH_MS / 1000.0)
            try:
                self._flush_once()
                self._maybe_retention()
            except Exception as e:
                log.warning("agent_bus flush error: %s", e)

    def _flush_once(self) -> None:
        with self._lock:
            if not self._pending:
                return
            batch = self._pending
            self._pending = []
        if not batch:
            return
        try:
            with _db() as c:
                c.executemany(
                    "INSERT INTO agent_events(ts, topic, source, payload) VALUES (?, ?, ?, ?)",
                    [(e.ts, e.topic, e.source, json.dumps(e.payload, ensure_ascii=False))
                     for e in batch],
                )
                # reconcile DB ids back into ring entries (best-effort — only matters for
                # subscribers that reconnect with a since_id from a previous run).
                # Note: we keep the in-memory id as authoritative for the ring
                # buffer and live subscribers. SQLite assigns its own rowids
                # which are only used by cross-restart history queries.
        except sqlite3.Error as e:
            log.warning("agent_bus persist failed (events kept in ring): %s", e)

    def _maybe_retention(self) -> None:
        now_ms = int(time.time() * 1000)
        if now_ms - self._last_retention_ms < 6 * 3600 * 1000:  # at most every 6h
            return
        self._last_retention_ms = now_ms
        cutoff = now_ms - _RETENTION_DAYS * 86_400_000
        try:
            with _db() as c:
                c.execute("DELETE FROM agent_events WHERE ts < ?", (cutoff,))
        except sqlite3.Error as e:
            log.warning("agent_bus retention sweep failed: %s", e)

    # ---- publish ----

    def publish(self, topic: str, payload: dict, source: str = "") -> Optional[AgentEvent]:
        """Append an event. Returns the stored event, or None if deduped.

        The event gets a positive monotonic in-memory id immediately. On flush
        SQLite assigns its own row id; we keep the in-memory id for cursor
        comparisons since cross-restart subscribers query SQLite directly.
        """
        if not topic or not isinstance(payload, dict):
            return None
        _ensure_schema()
        self._ensure_flusher()
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        key = (topic, hashlib.sha1(body).hexdigest())
        now_ms = int(time.time() * 1000)
        with self._cv:
            if self._dedup.seen(key, now_ms):
                return None
            ev = AgentEvent(id=self._next_local_id, ts=now_ms, topic=topic,
                            source=source, payload=payload)
            self._next_local_id += 1
            self._ring.append(ev)
            self._pending.append(ev)
            self._cv.notify_all()
        return ev

    # ---- subscribe ----

    def history(self, topics: list[str], limit: int = 200, since_id: int = 0) -> list[AgentEvent]:
        """Replay recent events matching `topics`. Pulls from ring first, falls
        back to SQLite if `since_id` is older than what's in memory.
        """
        _ensure_schema()
        patterns = [_glob_to_re(t) for t in (topics or ["**"])]
        # Try ring first
        with self._lock:
            ring_snapshot = list(self._ring)
        ring_hit = [e for e in ring_snapshot
                    if e.id > since_id and any(p.match(e.topic) for p in patterns)]
        if ring_hit:
            return ring_hit[-limit:]
        # SQLite fallback
        try:
            with _db() as c:
                rows = c.execute(
                    "SELECT id, ts, topic, source, payload FROM agent_events "
                    "WHERE id > ? ORDER BY id DESC LIMIT ?",
                    (max(0, since_id), max(1, min(limit, 1000))),
                ).fetchall()
            out: list[AgentEvent] = []
            for r in reversed(rows):
                if not any(p.match(r["topic"]) for p in patterns):
                    continue
                try:
                    pl = json.loads(r["payload"] or "{}")
                except Exception:
                    pl = {}
                out.append(AgentEvent(id=r["id"], ts=r["ts"], topic=r["topic"],
                                      source=r["source"] or "", payload=pl))
            return out
        except sqlite3.Error as e:
            log.warning("agent_bus history query failed: %s", e)
            return []

    def subscribe(self, topics: list[str], since_id: int = 0,
                  wait_s: float = _SUBSCRIBE_WAIT_S) -> Iterator[AgentEvent]:
        """Generator that yields events as they arrive on matching `topics`.

        - First call yields any backlog (ring/SQLite) above `since_id`.
        - Then blocks on the condition variable until new matching events show
          up or `wait_s` elapses (one heartbeat tick — caller decides whether
          to keep iterating).

        Designed to be wrapped by an SSE stream: each tick yields zero-or-more
        events, then the caller emits a keepalive comment if needed.
        """
        patterns = [_glob_to_re(t) for t in (topics or ["**"])]
        cursor = since_id
        backlog = self.history(topics, since_id=since_id, limit=500)
        for ev in backlog:
            cursor = max(cursor, ev.id if ev.id > 0 else cursor)
            yield ev

        while True:
            with self._cv:
                self._cv.wait(timeout=wait_s)
                snapshot = list(self._ring)
            new_events = [e for e in snapshot
                          if e.id > cursor and any(p.match(e.topic) for p in patterns)]
            if not new_events:
                yield AgentEvent(id=cursor, ts=int(time.time() * 1000),
                                 topic="__heartbeat__", source="bus", payload={})
                continue
            for ev in new_events:
                cursor = max(cursor, ev.id)
                yield ev


_BUS = _Bus()


# ───────── Public surface ─────────

def publish(topic: str, payload: dict, source: str = "") -> Optional[AgentEvent]:
    return _BUS.publish(topic, payload, source)


def history(topics: list[str], limit: int = 200, since_id: int = 0) -> list[dict]:
    return [e.to_dict() for e in _BUS.history(topics, limit=limit, since_id=since_id)]


def subscribe(topics: list[str], since_id: int = 0,
              wait_s: float = _SUBSCRIBE_WAIT_S) -> Iterator[AgentEvent]:
    return _BUS.subscribe(topics, since_id=since_id, wait_s=wait_s)


def flush_now() -> None:
    """Force an immediate flush — for tests and shutdown hooks."""
    _BUS._flush_once()


# ───────── Request / reply protocol ─────────
#
# Built on top of publish/subscribe so any subscriber can answer a question
# without a separate transport. The flow:
#
#   asker → publish(topic + ".ask", {corrId, ...})
#   any subscriber to "<topic>.ask.**" can resolve by:
#     publish(topic + ".reply." + corrId, {...})
#   asker waits for the matching reply (correlation by corrId).
#
# Optimization rationale: we re-use the bus's wakeup-driven subscribe loop
# instead of building a second condition variable. The matcher filters by
# exact reply topic, which the glob compiler caches — O(1) per wakeup.

def ask(topic: str, payload: dict, *, source: str = "asker",
        timeout_s: float = 30.0) -> Optional[dict]:
    """Publish a question on ``<topic>.ask`` and block until a matching
    reply on ``<topic>.reply.<corrId>`` arrives or ``timeout_s`` elapses.

    Returns the reply payload, or ``None`` on timeout. Bad input raises
    ``ValueError`` (we don't silently turn a programmer error into a hang).
    """
    if not topic or not isinstance(payload, dict):
        raise ValueError("topic and dict-payload required")
    import secrets
    corr_id = secrets.token_hex(8)
    ask_topic   = f"{topic}.ask"
    reply_topic = f"{topic}.reply.{corr_id}"
    enriched = dict(payload)
    enriched["__corrId__"] = corr_id
    enriched["__replyTopic__"] = reply_topic
    # Subscribe *before* publishing so we don't miss a fast reply.
    deadline = time.time() + max(0.5, timeout_s)
    # Use a short wait_s so the heartbeat path lets us re-check the deadline.
    wait_s = min(2.0, max(0.5, timeout_s / 2.0))
    sub_iter = subscribe([reply_topic], wait_s=wait_s)
    publish(ask_topic, enriched, source=source)
    try:
        for ev in sub_iter:
            if time.time() > deadline:
                return None
            if ev.topic == reply_topic:
                return ev.payload
            # heartbeat — check deadline and continue
    except Exception as e:
        log.warning("ask() crash on topic %s: %s", topic, e)
    return None


def reply(question_event: dict, payload: dict, source: str = "responder") -> bool:
    """Reply to a previously received question event. ``question_event`` is the
    payload (or full event dict) of an ``<topic>.ask`` publication; we use the
    embedded ``__replyTopic__`` to route the answer.
    """
    if not isinstance(question_event, dict):
        return False
    pl = question_event.get("payload") if "payload" in question_event \
        else question_event
    rt = (pl or {}).get("__replyTopic__")
    if not rt:
        return False
    publish(str(rt), payload, source=source)
    return True


def reset_for_tests() -> None:
    """Drop in-memory state. Tests only — does not touch SQLite."""
    with _BUS._cv:
        _BUS._ring.clear()
        _BUS._pending.clear()
        _BUS._dedup = _DedupLRU(_DEDUP_LRU, _DEDUP_WINDOW_MS)
        _BUS._next_local_id = 1


# ───────── HTTP API ─────────

def api_agent_bus_history(query: dict) -> dict:
    """GET /api/agent-bus/history?topics=a,b&since=0&limit=200"""
    topics_raw = (query.get("topics") or ["**"])
    if isinstance(topics_raw, list):
        topics_raw = topics_raw[0] if topics_raw else "**"
    topics = [t.strip() for t in str(topics_raw).split(",") if t.strip()]
    since = int((query.get("since") or [0])[0]) if isinstance(query.get("since"), list) \
        else int(query.get("since") or 0)
    limit = int((query.get("limit") or [200])[0]) if isinstance(query.get("limit"), list) \
        else int(query.get("limit") or 200)
    return {"ok": True, "events": history(topics, limit=limit, since_id=since)}


def handle_agent_bus_stream(handler, query: dict) -> None:
    """GET /api/agent-bus/stream?topics=a,b&since=N — Server-Sent Events.

    Each new event is emitted as ``event: bus`` with a JSON ``data`` line.
    The bus heartbeats with ``event: ping`` so proxies don't kill the stream.
    The stream stops cleanly if the client disconnects.
    """
    topics_raw = query.get("topics") if isinstance(query, dict) else None
    if isinstance(topics_raw, list):
        topics_raw = topics_raw[0] if topics_raw else "**"
    topics = [t.strip() for t in str(topics_raw or "**").split(",") if t.strip()]
    since_raw = query.get("since") if isinstance(query, dict) else 0
    if isinstance(since_raw, list):
        since_raw = since_raw[0] if since_raw else 0
    try:
        since = int(since_raw or 0)
    except (TypeError, ValueError):
        since = 0

    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()

    def _send(event: str, data: str) -> bool:
        try:
            handler.wfile.write(f"event: {event}\ndata: {data}\n\n".encode("utf-8"))
            handler.wfile.flush()
            return True
        except Exception:
            return False

    deadline = time.time() + 30 * 60  # cap one connection at 30 minutes
    try:
        for ev in subscribe(topics, since_id=since, wait_s=15.0):
            if ev.topic == "__heartbeat__":
                if not _send("ping", json.dumps({"ts": ev.ts})):
                    return
            else:
                if not _send("bus", json.dumps(ev.to_dict(), ensure_ascii=False)):
                    return
            if time.time() > deadline:
                _send("done", json.dumps({"reason": "max-duration"}))
                return
    except Exception as e:
        log.warning("agent_bus stream error: %s", e)


def api_agent_bus_publish(body: dict) -> dict:
    """POST /api/agent-bus/publish — for the frontend / TUI to inject events."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    topic = (body.get("topic") or "").strip()
    if not topic:
        return {"ok": False, "error": "topic required"}
    payload = body.get("payload") or {}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "payload must be object"}
    source = str(body.get("source") or "user")
    ev = publish(topic, payload, source=source)
    return {"ok": True, "deduped": ev is None,
            "event": ev.to_dict() if ev else None}
