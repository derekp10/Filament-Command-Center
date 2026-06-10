"""L3 slot-assign latency fixes A + B (prusalink_api).

A — per-operation probe cache: a single perform_smart_move probes the same
    printer in both its phase-1 and phase-2 auto-deploy passes; with a cache
    active it must hit the network only once.
B — skip the legacy /api/printer fallback when the v1 probe fails at the
    connection level (timeout / refused), since the legacy endpoint is on the
    same ip:port and would only burn a second timeout.
"""
from __future__ import annotations

import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import prusalink_api  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_cache():
    prusalink_api.clear_probe_cache()
    yield
    prusalink_api.clear_probe_cache()


# --- Fix A: per-operation probe cache ---------------------------------------

def test_probe_cache_dedupes_same_printer(monkeypatch):
    calls = []
    monkeypatch.setattr(prusalink_api, "_probe_printer_state",
                        lambda fb, name: (calls.append(name) or {"state": "IDLE", "is_active": False}))
    prusalink_api.begin_probe_cache()
    a = prusalink_api.get_printer_state("http://fb", "CORE1")
    b = prusalink_api.get_printer_state("http://fb", "CORE1")
    assert a == b == {"state": "IDLE", "is_active": False}
    assert calls == ["CORE1"]  # second call was a cache hit — no network


def test_probe_cache_caches_none(monkeypatch):
    # An offline printer returns None; that None MUST be cached too (it's the
    # expensive-to-recompute case — the whole point of fix A).
    calls = []
    monkeypatch.setattr(prusalink_api, "_probe_printer_state",
                        lambda fb, name: (calls.append(name) or None))
    prusalink_api.begin_probe_cache()
    assert prusalink_api.get_printer_state("http://fb", "CORE1") is None
    assert prusalink_api.get_printer_state("http://fb", "CORE1") is None
    assert calls == ["CORE1"]


def test_no_cache_calls_through_each_time(monkeypatch):
    calls = []
    monkeypatch.setattr(prusalink_api, "_probe_printer_state",
                        lambda fb, name: (calls.append(name) or None))
    # no begin_probe_cache() → unrelated callers are unaffected by fix A
    prusalink_api.get_printer_state("http://fb", "CORE1")
    prusalink_api.get_printer_state("http://fb", "CORE1")
    assert calls == ["CORE1", "CORE1"]


def test_cache_distinguishes_printers(monkeypatch):
    calls = []
    monkeypatch.setattr(prusalink_api, "_probe_printer_state",
                        lambda fb, name: (calls.append(name) or {"state": "X", "is_active": False}))
    prusalink_api.begin_probe_cache()
    prusalink_api.get_printer_state("http://fb", "CORE1")
    prusalink_api.get_printer_state("http://fb", "XL")
    prusalink_api.get_printer_state("http://fb", "CORE1")  # cached
    assert calls == ["CORE1", "XL"]


# --- Fix B: skip legacy fallback on a connection-level failure --------------

def test_v1_timeout_skips_legacy_fallback(monkeypatch):
    monkeypatch.setattr(prusalink_api, "fetch_printer_credentials",
                        lambda fb, name: {"ip_address": "1.2.3.4", "api_key": "k"})
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        raise requests.exceptions.ReadTimeout("timeout")

    monkeypatch.setattr(prusalink_api.requests, "get", fake_get)
    assert prusalink_api._probe_printer_state("http://fb", "CORE1") is None
    # Only the v1 endpoint was hit; the legacy /api/printer call was skipped.
    assert len(calls) == 1 and "/api/v1/status" in calls[0]


def test_v1_connection_error_skips_legacy_fallback(monkeypatch):
    monkeypatch.setattr(prusalink_api, "fetch_printer_credentials",
                        lambda fb, name: {"ip_address": "1.2.3.4", "api_key": "k"})
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(prusalink_api.requests, "get", fake_get)
    assert prusalink_api._probe_printer_state("http://fb", "CORE1") is None
    assert len(calls) == 1


def test_v1_unusable_response_still_tries_legacy(monkeypatch):
    # A non-timeout "answered but unusable" v1 response (old firmware) must
    # STILL fall through to the legacy endpoint — fix B only skips on a
    # connection-level failure, not on a parseable-but-empty answer.
    monkeypatch.setattr(prusalink_api, "fetch_printer_credentials",
                        lambda fb, name: {"ip_address": "1.2.3.4", "api_key": None})
    calls = []

    class _Resp:
        ok = True

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    def fake_get(url, **kw):
        calls.append(url)
        if "/api/v1/status" in url:
            return _Resp({})  # unusable — no printer.state
        return _Resp({"state": {"text": "Operational", "flags": {"printing": False}}})

    monkeypatch.setattr(prusalink_api.requests, "get", fake_get)
    result = prusalink_api._probe_printer_state("http://fb", "CORE1")
    assert result == {"state": "OPERATIONAL", "is_active": False}
    assert len(calls) == 2  # v1 unusable → legacy tried
