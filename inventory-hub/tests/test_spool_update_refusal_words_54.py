"""Group 54 review R4-2 (2026-11-09): a refused weight says why in words, never Spoolman's address.

/api/spool/update answered a write Spoolman refused, or never answered, with
`msg` "Failed to update spool: <LAST_SPOOLMAN_ERROR>", and review R1-3 made that
`msg` the weigh screens' 7 s error toast. LAST_SPOOLMAN_ERROR is requests' own
text, Spoolman's host and port in it ("HTTPConnectionPool(host='192.168.1.29',
port=7913): Read timed out. (read timeout=15)"), or Spoolman's raw JSON body, so
the toast showed a Spoolman address and ran past its own edge (off the screen on
a phone; the fixer's measurements, 1366x768 and 390x844). CLAUDE.md: where a
person reads a refusal, spoolman_api.refusal_words puts it in words "so no
Spoolman address reaches a person", and the log line keeps the full text.

Now `msg` is "Couldn't save Spool #57: " and refusal_words' words, and `error`
keeps the raw text (the page's Activity Log line appends it when `msg` doesn't
hold it, test_weigh_save_failure_toast_js).

The REAL route and update_spool run over tests/spoolman_extra_fake.SpoolmanHTTPFake,
its PATCH made to fail the way requests and Spoolman fail.

Base proof (7218c2d): every test marked RED fails there; the control passes.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import spoolman_api as sm_api  # noqa: E402
import state  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake, _Resp  # noqa: E402

SPOOL_FIELDS = [{"key": k, "field_type": "text", "name": k}
                for k in ("container_slot", "physical_source", "physical_source_slot")]

HOST = "HTTPConnectionPool(host='192.168.1.29', port=7913)"
TIMEOUT = f"{HOST}: Read timed out. (read timeout=15)"
REFUSED = (f"{HOST}: Max retries exceeded with url: /api/v1/spool/57 (Caused by NewConnectionError("
           "'<urllib3.connection.HTTPConnection object at 0x0000021D>: Failed to establish a new connection: "
           "[WinError 10061] No connection could be made because the target machine actively refused it'))")
# Spoolman's bodies (FastAPI's {"detail"} for a request it can't take, its own
# {"message"}), as dicts: _Resp sends them as JSON text.
BODY_422 = {"detail": [{"type": "float_parsing", "loc": ["body", "used_weight"],
                        "msg": "Input should be a valid number, unable to parse string as a number", "input": "x"}]}
BODY_500 = {"message": "database is locked"}


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def spoolman(monkeypatch):
    """#57 in stock at CR-SHELF, 1000 g with 700 g used, on a Spoolman 0.27 whose
    PATCH does what `fail` says: raise requests' exception with its own words, or
    answer an HTTP refusal with a body."""
    fake = SpoolmanHTTPFake(version="0.27.0", fields={"spool": copy.deepcopy(SPOOL_FIELDS)})
    fake.add("spool", 57, {}, location="CR-SHELF", initial_weight=1000.0, used_weight=700.0, archived=False)
    fake.fail = None

    def patch_(url, json=None, timeout=None, **kw):  # noqa: A002 — requests' kwarg
        fail = fake.fail
        if isinstance(fail, Exception):
            raise fail
        if isinstance(fail, tuple):
            status, body = fail
            return _Resp(status, body)
        return fake.patch(url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(sm_api.config_loader, "get_api_urls", lambda: ("http://sm.test", "http://fb"))
    monkeypatch.setattr(sm_api.requests, "get", fake.get)
    monkeypatch.setattr(sm_api.requests, "patch", patch_)
    monkeypatch.setattr(sm_api.locations_db, "get_active_printer_map", lambda *a, **k: {})
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(sm_api, name, {}).clear()
    yield fake
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(sm_api, name, {}).clear()


def _save(client, body=None):
    return client.post("/api/spool/update", json=body or {"id": 57, "updates": {"used_weight": 960}}).get_json()


@pytest.mark.parametrize("fail, words, raw", [
    (requests.exceptions.ReadTimeout(TIMEOUT), "Spoolman didn't answer in time.", "Read timed out"),
    (requests.exceptions.ConnectionError(REFUSED), "FCC couldn't reach Spoolman.", "Max retries exceeded"),
    ((422, BODY_422), "Spoolman refused it: Input should be a valid number, unable to parse string as a number",
     "float_parsing"),
    ((500, BODY_500), "Spoolman refused it: database is locked", '"message"'),
], ids=["timeout", "refused-connection", "422-body", "500-body"])
def test_a_refused_save_says_why_in_words_and_keeps_the_raw_text_in_error(client, spoolman, fail, words, raw):
    """RED: `msg` is "Couldn't save Spool #57: " and refusal_words' words, with no
    Spoolman address, no requests text and no JSON in it; `error` keeps the raw
    text, for the page's Activity Log line. On the base `msg` was "Failed to update
    spool: " and the raw text (the host and port, or the body's braces)."""
    spoolman.fail = fail
    body = _save(client)
    assert body["status"] == "error", body
    assert body["msg"] == f"Couldn't save Spool #57: {words}", body
    for leak in ("7913", "192.168", "host=", "HTTPConnectionPool", "{", "Failed to update spool"):
        assert leak not in body["msg"], (leak, body)
    assert raw in body["error"], body
    assert body["error"] == sm_api.LAST_SPOOLMAN_ERROR, body


def test_fccs_own_refusal_before_the_write_is_said_in_words(client, spoolman, monkeypatch):
    """RED: a write carrying an extra whose pre-merge read fails is refused by FCC
    itself (PREMERGE_READ_REFUSAL, a developer's sentence): the person reads
    refusal_words' sentence for it. On the base: "Failed to update spool: could
    not read the record's existing extras before a partial update; …"."""
    monkeypatch.setattr(sm_api, "_get_raw_extras", lambda entity, sid: None)
    body = _save(client, {"id": 57, "updates": {"used_weight": 960, "extra": {"container_slot": "1"}}})
    assert body["status"] == "error", body
    assert body["msg"] == ("Couldn't save Spool #57: FCC couldn't read it from Spoolman just before writing, "
                           "so nothing was written."), body
    assert body["error"] == sm_api.PREMERGE_READ_REFUSAL, body


def test_control_a_save_that_lands_answers_success(client, spoolman):
    """Control (green on the base too): the same save with Spoolman answering."""
    body = _save(client)
    assert body["status"] == "success", body
    assert spoolman.records["spool"][57]["used_weight"] == 960.0
