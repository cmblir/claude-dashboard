"""H5 — boot timing API."""
from __future__ import annotations


def test_boot_timing_endpoint_shape():
    from server import routes
    r = routes._api_boot_timing()
    assert r["ok"] is True
    # In a non-server-script process the values are zero — that's expected.
    assert "startedAtMs" in r
    assert "listeningAtMs" in r
    assert "bootDurationMs" in r


def test_route_registered():
    from server import routes
    assert "/api/system/boot-timing" in routes.ROUTES_GET
