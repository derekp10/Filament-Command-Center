"""FilaBridge status dot was constantly RED even though FilaBridge was up
(Derek 2026-06-02). Root cause: the /api/logs liveness probe hit FilaBridge's
/status endpoint, which polls every printer's live PrusaLink state and takes
~5-6s on a prod-sized fleet — past the old timeout=3 — so it timed out on EVERY
heartbeat. /print-errors (already fetched right after) returns instantly, so the
probe now uses it for liveness too.

These host-level tests mock the requests layer and drive /api/logs through the
Flask test client to assert: (1) FilaBridge reads as UP when /print-errors is
reachable, (2) the slow /status endpoint is NOT probed for the dot, (3) the dot
goes red when /print-errors itself is unreachable.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import config_loader  # noqa: E402


def _resp(ok=True, status=200, payload=None):
    m = MagicMock()
    m.ok = ok
    m.status_code = status
    m.json.return_value = payload if payload is not None else {}
    return m


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def fake_urls(monkeypatch):
    monkeypatch.setattr(
        config_loader, "get_api_urls",
        lambda: ("http://spoolman:7912", "http://filabridge:5001/api"),
    )


def test_filabridge_up_via_print_errors_and_status_not_probed(client, fake_urls, monkeypatch):
    seen = []

    def fake_get(url, **_kw):
        seen.append(url)
        if "/api/v1/health" in url:
            return _resp(ok=True)
        if "/print-errors" in url:
            return _resp(ok=True, payload={"errors": None})  # null errors → []
        if url.endswith("/status") or "/status" in url:
            # If the liveness probe regresses to /status, fail loudly — the
            # whole point of the fix is to NOT call this slow endpoint.
            raise AssertionError(f"liveness must not probe /status: {url}")
        return _resp(ok=True, payload={})

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    r = client.get("/api/logs")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"]["filabridge"] is True
    assert body["status"]["spoolman"] is True
    # Liveness probed /print-errors, never /status.
    assert any("/print-errors" in u for u in seen)
    assert not any(u.rstrip("/").endswith("/status") for u in seen)


def test_filabridge_down_when_print_errors_unreachable(client, fake_urls, monkeypatch):
    def fake_get(url, **_kw):
        if "/api/v1/health" in url:
            return _resp(ok=True)
        if "/print-errors" in url:
            raise app_module.requests.RequestException("filabridge unreachable")
        return _resp(ok=True, payload={})

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    r = client.get("/api/logs")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"]["filabridge"] is False
    assert body["status"]["spoolman"] is True


def test_null_errors_payload_does_not_crash(client, fake_urls, monkeypatch):
    """`{"errors": null}` must coerce to [] — a bare .get('errors', []) would
    return None and the error-processing loop would TypeError on `for err in
    None` (caught, but masking the bug). Assert the endpoint stays 200 + up."""
    def fake_get(url, **_kw):
        if "/api/v1/health" in url:
            return _resp(ok=True)
        if "/print-errors" in url:
            return _resp(ok=True, payload={"errors": None})
        return _resp(ok=True, payload={})

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    r = client.get("/api/logs")
    assert r.status_code == 200
    assert r.get_json()["status"]["filabridge"] is True
