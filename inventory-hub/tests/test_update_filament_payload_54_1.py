"""Group 54.1 — /api/update_filament answers a malformed request loudly.

The route read `data = payload.get('data') or {}`, so a request with no `data`, a
`null` one, a string, a list or an empty object all answered the same 200 "No
fields to update.", and a request without an id 200 "Missing filament id." That
generic answer is what hid the attribute purge's `_restore` no-op for months: it
sent the old {id, field, value} shape and every restore "succeeded" with nothing
written (Group 36). Its two sibling doors, /api/create_filament and
PATCH /api/vendors/<id>, already answer 400.

Now, before anything is read: a body that isn't a JSON object, a missing id, a
missing `data` (naming the old shape when the body carries `field` or `value`,
and one WARNING in hub.log naming the keys that came) and a `data` that isn't an
object each answer 400 with their own words. `{id, data: {}}` keeps its 200 "No
fields to update." (Claude's call: no caller sends it today, and keeping it costs
nothing). Every caller sends {id, data} and reads the JSON whatever the status.

Base proof (cac365d): every test marked RED fails there; the controls pass.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402

URL = "/api/update_filament"


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def spoolman(monkeypatch):
    """Records every read and write the route makes. A malformed request must
    make neither."""
    calls = {"get": [], "update": [], "warnings": []}

    def _get(fid):
        calls["get"].append(fid)
        return {"id": int(fid), "name": "Old"}

    def _update(fid, data):
        calls["update"].append((fid, data))
        return {"id": int(fid), **data}

    monkeypatch.setattr(spoolman_api, "get_filament", _get)
    monkeypatch.setattr(spoolman_api, "update_filament", _update)
    monkeypatch.setattr(state, "add_log_entry", lambda *a, **k: None)
    real_warning = state.logger.warning
    monkeypatch.setattr(state.logger, "warning",
                        lambda msg, *a, **k: (calls["warnings"].append(str(msg)), real_warning(msg, *a, **k)))
    return calls


def _nothing_touched(calls):
    assert calls["get"] == [] and calls["update"] == [], calls


def test_the_old_id_field_value_shape_is_refused_and_named(client, spoolman):
    """RED on the base: 200 "No fields to update." and nothing else."""
    r = client.post(URL, json={"id": 5, "field": "name", "value": "X"})
    assert r.status_code == 400, (r.status_code, r.get_json())
    body = r.get_json()
    assert body["success"] is False, body
    assert '"data"' in body["msg"] and "{id, field, value}" in body["msg"], body
    assert body["msg"].startswith("Nothing was updated"), body
    _nothing_touched(spoolman)
    named = [w for w in spoolman["warnings"] if "update_filament" in w and "data" in w]
    assert len(named) == 1 and "field, id, value" in named[0], spoolman["warnings"]


def test_a_request_with_no_data_at_all_is_refused_without_the_old_shape_words(client, spoolman):
    """RED on the base (200)."""
    r = client.post(URL, json={"id": 5})
    assert r.status_code == 400, (r.status_code, r.get_json())
    msg = r.get_json()["msg"]
    assert '"data"' in msg and "Send {id, data: {field: value}}" in msg, msg
    assert "old" not in msg, msg
    _nothing_touched(spoolman)


@pytest.mark.parametrize("data", ["x", ["a"], None, 7], ids=["text", "list", "null", "number"])
def test_a_data_that_isnt_an_object_is_refused(client, spoolman, data):
    """RED on the base: 200 "No fields to update." """
    r = client.post(URL, json={"id": 5, "data": data})
    assert r.status_code == 400, (r.status_code, r.get_json())
    body = r.get_json()
    assert body["success"] is False and body["msg"].startswith('"data" must be an object'), body
    assert "nothing was updated" in body["msg"], body
    _nothing_touched(spoolman)


@pytest.mark.parametrize("payload", [{"data": {"name": "X"}}, {"id": None, "data": {"name": "X"}},
                                     {"id": "", "data": {"name": "X"}}], ids=["absent", "null", "blank"])
def test_a_request_with_no_id_is_refused(client, spoolman, payload):
    """RED on the base: 200, same words."""
    r = client.post(URL, json=payload)
    assert r.status_code == 400, (r.status_code, r.get_json())
    assert r.get_json() == {"success": False, "msg": "Missing filament id."}
    _nothing_touched(spoolman)


@pytest.mark.parametrize("raw", ["[1]", "null", '"text"', "nope"], ids=["list", "null", "string", "not-json"])
def test_a_body_that_isnt_a_json_object_is_refused_in_json(client, spoolman, raw):
    """RED on the base: a list raised on `.get` (500), `null` and a string read
    as no id (200), and a body that isn't JSON got Flask's own HTML 400, which
    the page can't read."""
    r = client.post(URL, data=raw, content_type="application/json")
    assert r.status_code == 400, (r.status_code, r.data[:200])
    assert r.get_json() == {"success": False,
                            "msg": "The request isn't a JSON object, so nothing was updated."}
    _nothing_touched(spoolman)


def test_control_an_empty_data_keeps_its_answer(client, spoolman):
    """Control (green on the base too): {id, data: {}} answers 200 "No fields to
    update." as before."""
    r = client.post(URL, json={"id": 5, "data": {}})
    assert r.status_code == 200
    assert r.get_json() == {"success": False, "msg": "No fields to update."}
    _nothing_touched(spoolman)


def test_control_a_well_formed_request_still_writes(client, spoolman):
    """Control (green on the base too)."""
    r = client.post(URL, json={"id": 5, "data": {"name": "X"}})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["success"] is True, r.get_json()
    assert spoolman["get"] == [5] and spoolman["update"] == [(5, {"name": "X"})], spoolman
