"""Edit Spool's pre-edit read, when it gives no spool (Group 53 review, r3-3).

api_edit_spool_wizard reads the spool before it diffs the form against it, and
fails closed when it can't (27.1: without the record it can't run the dirty
diff or the SYSTEM_MANAGED strip). Two faults, one root:

  - Its answer read spoolman_api.LAST_SPOOLMAN_ERROR, which get_spool never
    sets, so it showed whatever an earlier write had left there. Since Group 53.2
    a refused filament create sets it too, and "Failed to update Spool 57: HTTP
    400: {"message": "Unknown extra field 'colour_family'"}" blamed an extra
    field for an edit that never reached Spoolman.
  - get_spool hands back Spoolman's body whatever the status, so a 404's or a
    5xx's JSON body was read as the spool: the form was diffed against it, every
    field came out dirty and was written, and a Location in the form wrote the
    spool Unassigned ('', where the bogus record said it was) before its move.

Now only the spool's own record (a dict whose id is the spool's) is the spool.
Anything else writes nothing, and the answer says in words which it was: "There
is no Spool 57 in Spoolman." (asked again through get_spool_answer, only when
Spoolman answered something that isn't the spool) or "Couldn't read Spool 57
from Spoolman before the edit, so nothing was saved. Try again in a moment."
Another spool's record is no spool either (Group 53 review, rd-2: nothing pinned
the id half of the rule).

The real routes and the real read and write helpers; only Spoolman's HTTP
answers are faked (spoolman_extra_fake.SpoolmanHTTPFake).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock
from urllib.parse import urlsplit

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app  # noqa: E402
import routes_inventory  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake, _Resp  # noqa: E402

SM = "http://spoolman.test:7913"
SPOOL_PATH = "/api/v1/spool/57"
COULDNT_READ = ("Couldn't read Spool 57 from Spoolman before the edit, so nothing was saved. "
                "Try again in a moment.")
NO_SUCH = "There is no Spool 57 in Spoolman."
STALE = 'HTTP 400: {"message": "an earlier, unrelated write\'s refusal"}'
TIMEOUT = requests.exceptions.ReadTimeout(
    "HTTPConnectionPool(host='spoolman.test', port=7913): Read timed out. (read timeout=3)")


class _Spoolman(SpoolmanHTTPFake):
    """SpoolmanHTTPFake with canned GET answers for a path (`canned[path]`, a list
    of _Resp answers or errors to raise, taken in turn; then the fake answers),
    and a POST that answers `post_answer`."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.canned = {}
        self.posts = []
        self.post_answer = None

    def get(self, url, timeout=None, **kw):
        path = urlsplit(str(url)).path.rstrip("/")
        queue = self.canned.get(path)
        if queue:
            answer = queue.pop(0)
            self.gets.append(path)
            if isinstance(answer, BaseException):
                raise answer
            return answer
        return super().get(url, timeout=timeout, **kw)

    def post(self, url, json=None, timeout=None, **kw):  # noqa: A002 (requests' kwarg)
        self.posts.append((urlsplit(str(url)).path, json))
        if self.post_answer is None:
            raise AssertionError(f"unexpected POST {url}")
        return self.post_answer


def _stocked():
    fake = _Spoolman()
    fake.add("spool", 57, {}, location="CR-SHELF", comment="", filament={"id": 3},
             initial_weight=1000.0, used_weight=100.0, archived=False)
    return fake


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def wire(monkeypatch):
    def _wire(fake):
        monkeypatch.setattr(spoolman_api.config_loader, "get_api_urls", lambda: (SM, "http://fb.test"))
        monkeypatch.setattr(spoolman_api.requests, "get", fake.get)
        monkeypatch.setattr(spoolman_api.requests, "patch", fake.patch)
        monkeypatch.setattr(spoolman_api.requests, "post", fake.post)
        monkeypatch.setattr(spoolman_api, "_RAW_EXTRAS_RETRY_DELAY_S", 0)
        for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
            getattr(spoolman_api, name, {}).clear()
        return fake
    return _wire


@pytest.fixture(autouse=True)
def stale_error(monkeypatch):
    """An earlier write's refusal is still in the global, as in the running app;
    monkeypatch puts back whatever the global held before the test."""
    monkeypatch.setattr(spoolman_api, "LAST_SPOOLMAN_ERROR", STALE)


@pytest.fixture
def hub_warnings(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(state.logger, "warning", mock)
    return lambda: [str(c.args[0]) for c in mock.call_args_list if c.args]


@pytest.fixture(autouse=True)
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a[0] if a else None)))
    return calls


def _edit(client, spool_data, sid=57):
    r = client.post("/api/edit_spool_wizard", json={"spool_id": sid, "spool_data": spool_data})
    assert r.status_code == 200
    return r.get_json()


def test_a_read_spoolman_didnt_answer_after_a_refused_create_never_blames_the_create(client, wire, hub_warnings):
    """The review's sequence: the Edit Filament modal's Add is refused, then an
    Edit Spool save whose pre-edit read times out. It answered the create's
    refusal: "Failed to update Spool 57: HTTP 400: {"message": "Unknown extra
    field 'colour_family'"}"."""
    fake = wire(_stocked())
    fake.post_answer = _Resp(400, {"message": "Unknown extra field 'colour_family'"})
    created = client.post("/api/create_filament", json={"data": {"material": "PLA", "name": "x"}})
    assert created.status_code == 500 and "Unknown extra field" in created.get_json()["msg"]
    assert "Unknown extra field" in spoolman_api.LAST_SPOOLMAN_ERROR      # left there, as in the app

    fake.canned[SPOOL_PATH] = [TIMEOUT]
    body = _edit(client, {"comment": "hi"})

    assert body == {"success": False, "msg": f"Failed to update Spool 57: {COULDNT_READ}", "error": COULDNT_READ}
    assert fake.patches == []
    assert fake.gets.count(SPOOL_PATH) == 1        # no answer: not asked again
    assert any("57" in w and "refusing" in w for w in hub_warnings()), hub_warnings()


def test_a_spool_spoolman_has_no_record_of_says_so_and_writes_nothing(client, wire, hub_warnings):
    fake = wire(_Spoolman())        # no Spool 57: its read answers 404 {"message": "No spool with ID 57 found."}
    body = _edit(client, {"comment": "hi"})

    assert body == {"success": False, "msg": f"Failed to update Spool 57: {NO_SUCH}", "error": NO_SUCH}
    assert fake.patches == [], fake.patches
    assert any("57" in w for w in hub_warnings()), hub_warnings()


@pytest.mark.parametrize("status", [500, 503])
def test_a_5xx_body_is_not_the_spool_and_nothing_is_written(client, wire, status):
    """Spoolman answers the read with a JSON error body, then recovers: the body
    was diffed as the spool and the form written."""
    fake = wire(_stocked())
    fake.canned[SPOOL_PATH] = [_Resp(status, {"message": "database is locked"})]
    body = _edit(client, {"comment": "hi"})

    assert body == {"success": False, "msg": f"Failed to update Spool 57: {COULDNT_READ}", "error": COULDNT_READ}
    assert fake.patches == [], fake.patches
    assert fake.records["spool"][57]["comment"] == ""


def test_a_5xx_body_never_writes_the_spool_unassigned_before_its_move(client, wire, monkeypatch):
    """The form's Location (where the spool is) differed from the error body's
    none, so the edit was a move, and its first write named where the body said
    the spool was: '' (Unassigned)."""
    fake = wire(_stocked())
    fake.canned[SPOOL_PATH] = [_Resp(500, {"message": "database is locked"})]
    moves = []
    monkeypatch.setattr(routes_inventory, "_wizard_move",
                        lambda *a, **k: moves.append(a) or (True, {"status": "success"}, None))
    body = _edit(client, {"comment": "hi", "location": "CR-SHELF"})

    assert body["success"] is False and body["error"] == COULDNT_READ, body
    assert fake.patches == [], fake.patches
    assert moves == []
    assert fake.records["spool"][57]["location"] == "CR-SHELF"


@pytest.mark.parametrize("form", [{"comment": "hi"}, {"comment": "hi", "location": "CR-SHELF"}],
                         ids=["a comment", "a comment and the Location"])
def test_a_record_of_another_spool_is_not_the_spool_and_nothing_is_written(client, wire, monkeypatch, form):
    """rd-2: the record is the spool only when its id is the one asked for.
    Spoolman (or a proxy or cache before it) answering 200 with Spool 58's record:
    diffed against #58 (the id check dropped), the form's comment would be written
    to #57, and the form's Location (where #57 is) would differ from #58's, so the
    edit would be a move whose first write files #57 where #58 is."""
    fake = wire(_stocked())
    other = {"id": 58, "location": "BIN-9", "comment": "", "filament": {"id": 4}, "extra": {},
             "initial_weight": 1000.0, "used_weight": 900.0, "archived": False}
    fake.canned[SPOOL_PATH] = [_Resp(200, other), _Resp(200, other)]
    moves = []
    monkeypatch.setattr(routes_inventory, "_wizard_move",
                        lambda *a, **k: moves.append(a) or (True, {"status": "success"}, None))
    body = _edit(client, form)

    assert body == {"success": False, "msg": f"Failed to update Spool 57: {COULDNT_READ}", "error": COULDNT_READ}
    assert fake.patches == [], fake.patches
    assert moves == []
    assert {k: fake.records["spool"][57][k] for k in ("comment", "location")} == {
        "comment": "", "location": "CR-SHELF"}


@pytest.mark.parametrize("sid", [57, "57"], ids=["number", "text"])
def test_a_spool_spoolman_sends_is_edited_as_before(client, wire, sid):
    """The control: the spool's own record, its id sent as a number or as text."""
    fake = wire(_stocked())
    body = _edit(client, {"comment": "hi"}, sid=sid)

    assert body["success"] is True, body
    assert [(entity, eid) for entity, eid, _body in fake.patches] == [("spool", 57)]
    assert fake.records["spool"][57]["comment"] == "hi"
