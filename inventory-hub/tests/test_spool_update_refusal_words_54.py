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

Review R5-2 / R5-3 (2026-11-09): update_spool's timeout is a READ timeout, so a
write whose answer never came, or came broken (the connection dropped, a chunked
answer cut short, a 200 whose body isn't JSON), may have landed. The route called
it "Couldn't save", ran nothing after it (the weigh page's unassign after an
archive), and a person who saved again added the grams twice (the Quick-Weigh's
Additive mode). Now such a failure is read back once (spoolman_api.get_spool_answer):
landed as sent, it is answered as saved, the normal way; not landed, "Couldn't
save" stands; unreadable, the answer says FCC can't tell and to check the weight
first (`may_have_saved`). A refusal Spoolman answered, or FCC's own before
sending, wrote nothing and is never read back. refusal_words also puts a cut-off
or unreadable answer in words. The tests marked "RED on 2c4b6f6" fail there.
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

# Every FCC extra the archive edge can write (Spoolman refuses a PATCH carrying one
# it doesn't know).
SPOOL_FIELDS = [{"key": k, "field_type": "text", "name": k}
                for k in ("container_slot", "physical_source", "physical_source_slot",
                          "fcc_pre_archive_location", "fcc_pre_box_location", "fcc_pre_audit_location")]

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
ABORTED = "('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"
CHUNKED = ("('Connection broken: IncompleteRead(0 bytes read, 512 more expected)', "
           "IncompleteRead(0 bytes read, 512 more expected))")


class _HTMLResp:
    """A 200 whose body isn't JSON (a proxy's page): the PATCH was taken."""
    status_code = 200
    ok = True
    text = "<html><body>OK</body></html>"

    def json(self):
        raise requests.exceptions.JSONDecodeError("Expecting value", self.text, 0)


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
    fake.apply_then = None   # the PATCH lands, then its answer is lost (an exception) or isn't JSON ('html')

    def patch_(url, json=None, timeout=None, **kw):  # noqa: A002 — requests' kwarg
        fail = fake.fail
        if isinstance(fail, Exception):
            raise fail
        if isinstance(fail, tuple):
            status, body = fail
            return _Resp(status, body)
        out = fake.patch(url, json=json, timeout=timeout, **kw)
        lost = fake.apply_then
        if isinstance(lost, Exception):
            raise lost
        if lost == "html":
            return _HTMLResp()
        return out

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


# ---- a write whose answer was lost is read back before it is called failed (review R5-2) ----------------

LOST = [
    requests.exceptions.ReadTimeout(TIMEOUT),
    requests.exceptions.ConnectionError(ABORTED),
    requests.exceptions.ChunkedEncodingError(CHUNKED),
    "html",
]
LOST_IDS = ["timeout", "aborted", "chunked", "html-200"]


def _msgs(fragment):
    return [str(e.get("msg", "")) for e in reversed(state.RECENT_LOGS) if fragment in str(e.get("msg", ""))]


@pytest.mark.parametrize("lost", LOST, ids=LOST_IDS)
def test_a_save_that_landed_though_its_answer_was_lost_is_answered_saved(client, spoolman, lost):
    """RED on 2c4b6f6: the PATCH landed (the record holds 960 g used) but its
    answer was lost; a read-back shows it, so the save is answered as saved, its
    weight line is written and `location_now` says where the spool is. On the base:
    "Couldn't save Spool #57: …", and a person saved it again."""
    spoolman.apply_then = lost
    body = _save(client)
    assert spoolman.records["spool"][57]["used_weight"] == 960.0
    assert body["status"] == "success", body
    assert body.get("location_now") == "CR-SHELF" and body.get("auto_archived") is False, body
    assert _msgs("Weight updated — Spool #57"), state.RECENT_LOGS


def test_a_weigh_to_empty_that_landed_is_answered_archived(client, spoolman):
    """RED on 2c4b6f6: a weigh to 0 g FCC read first: the archive edge's write
    landed (archived, Unassigned) and its answer timed out. Answered as saved and
    archived, with `location_now` '' (the page then needs no unassign)."""
    spoolman.apply_then = requests.exceptions.ReadTimeout(TIMEOUT)
    body = _save(client, {"id": 57, "updates": {"used_weight": 1000}})
    rec = spoolman.records["spool"][57]
    assert rec["archived"] is True and rec["location"] == "", rec
    assert body["status"] == "success" and body["auto_archived"] is True, body
    assert body.get("location_now") == "", body


def test_an_unread_spools_weigh_to_empty_that_landed_names_its_place(client, spoolman, monkeypatch):
    """RED on 2c4b6f6: FCC couldn't read #57 first (review R1-1: archived where it
    is by the page's own `archived: true`), the write landed at CR-SHELF and its
    answer timed out; the read-back works. Answered as saved, archived, at
    CR-SHELF, so the weigh page's unassign takes it off (review R4-1)."""
    monkeypatch.setattr(sm_api, "get_spool", lambda sid: None)
    spoolman.apply_then = requests.exceptions.ReadTimeout(TIMEOUT)
    body = _save(client, {"id": 57, "updates": {"remaining_weight": 0, "archived": True}})
    rec = spoolman.records["spool"][57]
    assert rec["archived"] is True and rec["location"] == "CR-SHELF", rec
    assert body["status"] == "success" and body["auto_archived"] is True, body
    assert body.get("location_now") == "CR-SHELF", body


@pytest.mark.parametrize("lost", LOST[:3], ids=LOST_IDS[:3])
def test_a_save_whose_answer_and_read_back_both_failed_says_it_cant_tell(client, spoolman, monkeypatch, lost):
    """RED on 2c4b6f6: the answer was lost and so was the read-back, so FCC can't
    tell whether the write landed: it says so, and to check the weight before saving
    again (the Quick-Weigh's Additive mode would add the grams twice), never
    "Couldn't save". `error` keeps the raw text."""
    spoolman.apply_then = lost
    monkeypatch.setattr(sm_api, "get_spool_answer", lambda sid: (None, False))
    body = _save(client)
    assert body["status"] == "error" and body.get("may_have_saved") is True, body
    assert body["msg"].startswith("Couldn't tell whether Spool #57 saved: "), body
    assert body["msg"].endswith(" Check its weight before saving again."), body
    for leak in ("7913", "host=", "HTTPConnectionPool", "IncompleteRead", "RemoteDisconnected"):
        assert leak not in body["msg"], (leak, body)
    assert body["error"] == sm_api.LAST_SPOOLMAN_ERROR, body


def test_control_a_save_that_timed_out_and_never_landed_still_says_it_couldnt_save(client, spoolman):
    """Control (green on 2c4b6f6 too): the PATCH timed out and never landed; the
    read-back shows the old weight, so "Couldn't save" is true."""
    spoolman.fail = requests.exceptions.ReadTimeout(TIMEOUT)
    body = _save(client)
    assert spoolman.records["spool"][57]["used_weight"] == 700.0
    assert body["status"] == "error" and not body.get("may_have_saved"), body
    assert body["msg"] == "Couldn't save Spool #57: Spoolman didn't answer in time.", body


@pytest.mark.parametrize("fail", [(500, BODY_500), (422, BODY_422)], ids=["500", "422"])
def test_control_a_refusal_spoolman_answered_is_never_read_back(client, spoolman, monkeypatch, fail):
    """Control (green on 2c4b6f6 too): Spoolman answered "no", so nothing landed and
    nothing is read back."""
    reads = []
    real = sm_api.get_spool_answer
    monkeypatch.setattr(sm_api, "get_spool_answer", lambda sid: reads.append(sid) or real(sid))
    spoolman.fail = fail
    body = _save(client)
    assert body["status"] == "error" and body["msg"].startswith("Couldn't save Spool #57: Spoolman refused it"), body
    assert reads == [], reads


# ---- refusal_words: an answer cut off or unreadable (review R5-3) ----------------------------------------

@pytest.mark.parametrize("raw, words", [
    (CHUNKED, "Spoolman's answer was cut off."),
    ("Expecting value: line 1 column 1 (char 0)", "Spoolman's answer couldn't be read."),
    ("Extra data: line 1 column 5 (char 4)", "Spoolman's answer couldn't be read."),
], ids=["chunked", "json-empty", "json-extra"])
def test_refusal_words_says_an_answer_was_cut_off_or_unreadable(raw, words):
    """RED on 2c4b6f6: these came back as they were, requests' and json's own words."""
    assert sm_api.refusal_words(raw) == words


def test_control_refusal_words_keeps_fccs_own_sentences():
    """Control: FCC's own sentence comes back as it is (the audit report's reasons)."""
    said = "FCC couldn't read PM-DB-9 from Spoolman, so nothing was moved."
    assert sm_api.refusal_words(said) == said

