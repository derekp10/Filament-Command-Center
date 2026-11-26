"""Group 66.1, the server: one manufacturer per name, and a vendor list read that says so
when it couldn't read.

Spoolman takes a second vendor of a name already in use, and FCC never checked. Derek's
data (prod, read 2026-11-24) holds three such pairs: Sunlu #4 / #35, Prusament #9 / #34,
Jessie Premium #38 / #39. And `/api/vendors` answered `success: true` with [] when
Spoolman didn't answer, so after a blip Edit Filament read the filament's own vendor as
unknown ("+ NEW") and its Save created a second vendor of that name.

Now a create (POST /api/vendors, either body shape) and a rename (PATCH /api/vendors/<id>
with a new name) are refused with 409 and `existing: {id, name}` when another vendor has
the name (spoolman_api.vendor_name_key: trimmed, inner spaces made one, any case), and
with 502 when FCC couldn't read the list; nothing is written either way, and one escaped
WARNING Activity Log line says so. An edit that leaves the name alone (or changes only
its own case) reads no list. Both vendor GETs answer 502 with words for a list FCC
couldn't read, never an empty list. The created line and the edit log escape their text.

Hermetic: the Flask test client; Spoolman's vendor list from
tests/spoolman_extra_fake.SpoolmanHTTPFake (its 503 and its silence), the writes patched.
"""
from __future__ import annotations

import pytest

import app as app_module
import spoolman_api
from spoolman_extra_fake import SpoolmanHTTPFake

VENDORS = [(4, "Sunlu", 167.0), (9, "Prusament", None), (35, "Sunlu", None),
           (38, "Jessie Premium", 179.0), (40, "Öko Filament", None)]


@pytest.fixture
def env(monkeypatch):
    fake = SpoolmanHTTPFake(version="0.27.0")
    for vid, name, w in VENDORS:
        fake.add("vendor", vid, {}, name=name, empty_spool_weight=w, external_id="")
    monkeypatch.setattr(spoolman_api.config_loader, "get_api_urls", lambda: ("http://sm.test", "http://fb"))
    monkeypatch.setattr(spoolman_api.requests, "get", fake.get)
    created, updated, logs = [], [], []
    monkeypatch.setattr(spoolman_api, "create_vendor",
                        lambda data: created.append(data) or dict(data, id=99))
    monkeypatch.setattr(spoolman_api, "update_vendor_or_raise",
                        lambda vid, data: updated.append((vid, data)) or dict(data, id=vid))
    monkeypatch.setattr(spoolman_api, "get_vendor",
                        lambda vid: next(({"id": v, "name": n, "empty_spool_weight": w, "extra": {}}
                                          for v, n, w in VENDORS if v == int(vid)), None))
    monkeypatch.setattr(app_module.state, "add_log_entry", lambda msg, *a, **k: logs.append((msg, a)))
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client, fake, created, updated, logs


def _create(client, name, shape="data"):
    body = {"data": {"name": name, "comment": ""}} if shape == "data" else {"name": name}
    r = client.post("/api/vendors", json=body)
    return r.status_code, r.get_json()


@pytest.mark.parametrize("name", ["sunlu", " SUNLU ", "Sunlu", "jessie  premium", "ÖKO FILAMENT"])
@pytest.mark.parametrize("shape", ["data", "name"])
def test_a_name_in_use_is_never_created_again(env, name, shape):
    """RED on the base: Spoolman created a second vendor of the name."""
    client, _fake, created, _updated, logs = env
    code, body = _create(client, name, shape)
    assert code == 409, body
    assert body["success"] is False and created == []
    assert "already exists" in body["msg"] and "nothing was created" in body["msg"]
    want = {"sunlu": (4, "Sunlu"), "jessie premium": (38, "Jessie Premium"), "öko filament": (40, "Öko Filament")}
    assert (body["existing"]["id"], body["existing"]["name"]) == want[spoolman_api.vendor_name_key(name)]
    assert len(logs) == 1 and logs[0][1] == ("WARNING", "ffaa00"), logs


def test_a_free_name_is_created_and_its_line_escaped(env):
    """A free name is created once, as before; the created line is HTML text. RED on the
    base: the name went into the line as markup."""
    client, _fake, created, _updated, logs = env
    code, body = _create(client, "<b>Odd</b> & Co")
    assert code == 200 and body["success"] is True
    assert [c["name"] for c in created] == ["<b>Odd</b> & Co"]
    assert logs == [("➕ Vendor '&lt;b&gt;Odd&lt;/b&gt; &amp; Co' created", ("SUCCESS", "00ff00"))]


@pytest.mark.parametrize("how", ["503", "down"])
def test_a_list_fcc_couldnt_read_creates_nothing(env, how):
    """Never a create on a guess. RED on the base: created anyway."""
    client, fake, created, _updated, logs = env
    if how == "503":
        fake.list_reads_fail = True
    else:
        fake.down = True
    code, body = _create(client, "Brand New")
    assert code == 502, body
    assert created == [] and "Couldn't check whether that name is free" in body["msg"]
    assert len(logs) == 1 and "FCC couldn't read the manufacturer list" in logs[0][0]


def test_a_rename_to_a_name_in_use_is_refused(env):
    """RED on the base: renamed, two vendors of one name."""
    client, _fake, _created, updated, logs = env
    r = client.patch("/api/vendors/35", json={"data": {"name": "Prusament"}})
    assert r.status_code == 409
    body = r.get_json()
    assert body["existing"] == {"id": 9, "name": "Prusament"} and "nothing was saved" in body["msg"]
    assert updated == []
    assert len(logs) == 1 and "Didn't rename manufacturer #35" in logs[0][0]


def test_a_rename_of_its_own_case_or_an_edit_without_a_name_change_reads_no_list(env):
    """A pin: the duplicate pair's own weight edit, and a case-only rename, go through
    with no read (Sunlu #35 shares its name with #4 and can still be edited)."""
    client, fake, _created, updated, _logs = env
    fake.list_reads_fail = True        # a read would refuse: none is made
    r = client.patch("/api/vendors/35", json={"data": {"empty_spool_weight": 167}})
    assert r.status_code == 200, r.get_json()
    r = client.patch("/api/vendors/4", json={"data": {"name": "SUNLU", "comment": ""}})
    assert r.status_code == 200, r.get_json()
    assert [v for v, _ in updated] == [35, 4]


def test_a_rename_with_a_list_fcc_couldnt_read_writes_nothing(env):
    client, fake, _created, updated, _logs = env
    fake.down = True
    r = client.patch("/api/vendors/35", json={"data": {"name": "Sunlu Two"}})
    assert r.status_code == 502 and updated == []


def test_a_free_rename_is_saved_and_its_log_line_escaped(env):
    """RED on the base: the edit log put the names in as markup."""
    client, _fake, _created, updated, logs = env
    r = client.patch("/api/vendors/40", json={"data": {"name": "<i>Eco</i> & Co"}})
    assert r.status_code == 200, r.get_json()
    assert updated == [(40, {"name": "<i>Eco</i> & Co"})]
    assert "name: Öko Filament → &lt;i&gt;Eco&lt;/i&gt; &amp; Co" in logs[0][0], logs


@pytest.mark.parametrize("route", ["/api/vendors", "/api/external/vendors"])
def test_a_vendor_list_fcc_couldnt_read_is_said_never_empty(env, route):
    """RED on the base: success with [] (and Edit Filament then marked a filament's own
    vendor "+ NEW", and its Save made a second vendor)."""
    client, fake, *_ = env
    r = client.get(route)
    assert r.status_code == 200 and [v["id"] for v in r.get_json()["vendors"]] == [4, 9, 35, 38, 40]
    fake.list_reads_fail = True
    r = client.get(route)
    assert r.status_code == 502, r.get_json()
    assert r.get_json() == {"success": False,
                            "msg": "Couldn't read the manufacturer list from Spoolman. Try again in a moment."}


def test_a_list_holding_something_that_isnt_a_vendor_counts_as_unread(env, monkeypatch):
    client, fake, *_ = env
    fake.add("vendor", 41, {}, name="Fine")
    fake.records["vendor"][41]["id"] = True       # a bool is no vendor id
    r = client.get("/api/vendors")
    assert r.status_code == 502


def test_the_name_key_and_the_lowest_id():
    """One rule: trimmed, inner spaces made one, any case (a non-ASCII name too); several
    holders of a name answer the lowest id."""
    k = spoolman_api.vendor_name_key
    assert k("  Jessie   Premium ") == k("jessie premium") == "jessie premium"
    assert k("Öko") == k("öko") and k("Sun-lu") != k("Sunlu") and k(None) == ""
    vendors = [{"id": 35, "name": "Sunlu"}, {"id": 4, "name": "sunlu"}, {"id": 9, "name": "Prusament"}]
    assert spoolman_api.vendor_named("SUNLU", vendors)["id"] == 4
    assert spoolman_api.vendor_named("Sunlu", vendors, but_not=4)["id"] == 35
    assert spoolman_api.vendor_named("Polymaker", vendors) is None
    assert spoolman_api.vendor_named("", vendors) is None
