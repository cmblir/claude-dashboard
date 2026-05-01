"""Per-host HTTPS keep-alive connection pool.

Slack / Telegram clients call ``api.slack.com`` / ``api.telegram.org`` over and
over. ``urllib.request.urlopen`` opens a fresh TCP+TLS handshake for every
request. For a chat-heavy orchestrator that adds 50–200 ms of pure latency per
message — which compounds when several sub-agent results all reply to the
same channel.

This module trades that for a tiny per-host pool of
``http.client.HTTPSConnection`` objects, with three guarantees:

- **Hostname is pinned per pool** — callers ask for ``borrow("api.slack.com")``,
  not a free-form URL. Eliminates the SSRF / redirect-pivot class of bug.
- **One in-flight connection per slot.** A connection is checked out, used,
  then returned. If the response surfaces a connection-fatal error
  (``BadStatusLine``, ``ConnectionResetError``, etc.) it is discarded rather
  than returned.
- **Bounded.** Pool size is per-host, default 4, env-tunable. We never grow
  unboundedly on burst.

No new dependencies. The pool is thread-safe via a single ``RLock`` per host.

If anything below the wire goes sideways, ``request()`` falls back to the
classic ``urllib.request.urlopen`` path so feature behaviour does not regress
under network weirdness — just the latency win is lost.
"""
from __future__ import annotations

import http.client
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from typing import Optional

from .logger import log


_POOL_PER_HOST = max(1, int(os.environ.get("HTTP_POOL_PER_HOST", "4")))
_IDLE_TIMEOUT_S = float(os.environ.get("HTTP_POOL_IDLE_S", "60"))
_DEFAULT_TIMEOUT = float(os.environ.get("HTTP_POOL_TIMEOUT_S", "12"))


class _HostPool:
    __slots__ = ("host", "lock", "free", "_ssl_ctx")

    def __init__(self, host: str) -> None:
        self.host = host
        self.lock = threading.Lock()
        self.free: deque[tuple[float, http.client.HTTPSConnection]] = deque()
        self._ssl_ctx = ssl.create_default_context()

    def _make_conn(self, timeout: float) -> http.client.HTTPSConnection:
        # ``check_hostname`` and ``verify_mode`` come from the default context.
        return http.client.HTTPSConnection(self.host, timeout=timeout,
                                           context=self._ssl_ctx)

    def borrow(self, timeout: float) -> http.client.HTTPSConnection:
        cutoff = time.time() - _IDLE_TIMEOUT_S
        with self.lock:
            while self.free:
                ts, conn = self.free.popleft()
                if ts < cutoff:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    continue
                return conn
        return self._make_conn(timeout)

    def release(self, conn: http.client.HTTPSConnection, *, healthy: bool) -> None:
        if not healthy:
            try:
                conn.close()
            except Exception:
                pass
            return
        with self.lock:
            if len(self.free) < _POOL_PER_HOST:
                self.free.append((time.time(), conn))
                return
        # Pool full — close.
        try:
            conn.close()
        except Exception:
            pass

    def close_all(self) -> None:
        with self.lock:
            while self.free:
                _, conn = self.free.popleft()
                try:
                    conn.close()
                except Exception:
                    pass


_POOLS: dict[str, _HostPool] = {}
_POOLS_LOCK = threading.Lock()


def _pool_for(host: str) -> _HostPool:
    p = _POOLS.get(host)
    if p is not None:
        return p
    with _POOLS_LOCK:
        p = _POOLS.get(host)
        if p is None:
            p = _HostPool(host)
            _POOLS[host] = p
    return p


# ───────── Public surface ─────────

class HttpResponse:
    __slots__ = ("status", "body", "headers")

    def __init__(self, status: int, body: bytes, headers: dict) -> None:
        self.status = status
        self.body = body
        self.headers = headers


def request(host: str, method: str, path: str, *, body: Optional[bytes] = None,
            headers: Optional[dict] = None, timeout: float = _DEFAULT_TIMEOUT,
            allow_fallback: bool = True) -> HttpResponse:
    """Send one HTTPS request via the pool. Path is everything after the host
    (including query string). On any pool-fatal error we transparently fall
    back to ``urllib.request.urlopen`` so callers keep working when the
    keep-alive optimization can't be applied.
    """
    if not host:
        raise ValueError("host required")
    headers = dict(headers or {})
    headers.setdefault("Host", host)
    headers.setdefault("Connection", "keep-alive")
    if body is not None and "Content-Length" not in headers:
        headers["Content-Length"] = str(len(body))

    pool = _pool_for(host)
    conn = pool.borrow(timeout)
    healthy = False
    try:
        conn.request(method.upper(), path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        status = resp.status
        out_headers = {k.lower(): v for k, v in resp.getheaders()}
        # Connection: close from server → don't keep
        healthy = (out_headers.get("connection", "").lower() != "close")
        return HttpResponse(status, raw, out_headers)
    except (http.client.HTTPException, ConnectionError, OSError, ssl.SSLError) as e:
        try:
            conn.close()
        except Exception:
            pass
        if not allow_fallback:
            raise
        log.debug("http_pool fallback to urllib for %s: %s", host, e)
        return _urllib_fallback(host, method, path, body, headers, timeout)
    finally:
        pool.release(conn, healthy=healthy)


def _urllib_fallback(host: str, method: str, path: str, body: Optional[bytes],
                     headers: dict, timeout: float) -> HttpResponse:
    url = f"https://{host}{path}"
    req = urllib.request.Request(url, data=body, headers=headers,
                                 method=method.upper())
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return HttpResponse(r.status,
                                r.read(),
                                {k.lower(): v for k, v in r.getheaders()})
    except urllib.error.HTTPError as e:
        # Surface non-2xx the same way as the pooled path: caller decides.
        return HttpResponse(e.code, e.read() if hasattr(e, "read") else b"",
                            {k.lower(): v for k, v in (e.headers.items() if e.headers else [])})


def post_json(host: str, path: str, payload: dict, *,
              extra_headers: Optional[dict] = None,
              timeout: float = _DEFAULT_TIMEOUT) -> dict:
    """Convenience wrapper used by Slack/Telegram clients. Returns the parsed
    JSON dict on 2xx; raises ``RuntimeError`` with body excerpt otherwise.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    h = {"Content-Type": "application/json; charset=utf-8"}
    if extra_headers:
        h.update(extra_headers)
    resp = request(host, "POST", path, body=body, headers=h, timeout=timeout)
    if resp.status // 100 != 2:
        snippet = resp.body[:200].decode("utf-8", errors="replace")
        raise RuntimeError(f"http {resp.status}: {snippet}")
    try:
        return json.loads(resp.body.decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"non-json response: {e}") from e


def stats() -> dict:
    """For perf tests / dashboards."""
    out: dict[str, dict] = {}
    for host, pool in _POOLS.items():
        with pool.lock:
            out[host] = {"idle": len(pool.free), "max": _POOL_PER_HOST}
    return out


def close_all() -> None:
    for p in list(_POOLS.values()):
        p.close_all()
