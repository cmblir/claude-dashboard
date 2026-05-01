"""Tests for server.http_pool.

We don't make real network calls here — that would couple the suite to
external uptime. Instead we drive the pool's internals (borrow/release,
pruning, capacity) which are the actual optimization.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def pool():
    from server import http_pool
    importlib.reload(http_pool)
    yield http_pool
    http_pool.close_all()


def test_pool_starts_empty(pool):
    p = pool._pool_for("api.example.com")
    assert len(p.free) == 0


def test_release_keeps_when_healthy(pool):
    p = pool._pool_for("api.example.com")
    # Synthetic stand-in — the pool only inspects the object's .close attr.
    class DummyConn:
        closed = False
        def close(self): self.closed = True

    c = DummyConn()
    p.release(c, healthy=True)
    assert len(p.free) == 1
    assert c.closed is False


def test_release_drops_when_unhealthy(pool):
    p = pool._pool_for("api.example.com")
    class DummyConn:
        closed = False
        def close(self): self.closed = True

    c = DummyConn()
    p.release(c, healthy=False)
    assert len(p.free) == 0
    assert c.closed is True


def test_release_caps_at_pool_size(pool, monkeypatch):
    monkeypatch.setattr(pool, "_POOL_PER_HOST", 2)
    p = pool._pool_for("api.example.com")
    closed = [0]
    class DummyConn:
        def close(self): closed[0] += 1

    for _ in range(5):
        p.release(DummyConn(), healthy=True)
    assert len(p.free) == 2
    # Three over-capacity dummies should have been closed.
    assert closed[0] == 3


def test_borrow_reuses_recent(pool):
    p = pool._pool_for("api.example.com")
    class DummyConn:
        ident = 0
    c = DummyConn(); c.ident = 7
    p.release(c, healthy=True)
    again = p.borrow(timeout=1.0)
    assert getattr(again, "ident", None) == 7


def test_borrow_skips_idle_too_old(pool, monkeypatch):
    """Anything past idle-timeout should be discarded, not handed back."""
    monkeypatch.setattr(pool, "_IDLE_TIMEOUT_S", 0.01)
    p = pool._pool_for("api.example.com")
    class DummyConn:
        closed = False
        def close(self): self.closed = True
    c = DummyConn()
    p.release(c, healthy=True)
    import time as _t; _t.sleep(0.05)
    new = p.borrow(timeout=1.0)
    assert new is not c     # got a fresh connection
    assert c.closed is True
