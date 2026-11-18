"""Group 63.6: a weigh save sends what its preview was worked out from.

The weigh-out list caches each spool's details (its capacity, used weight, tare)
when it reads them, and the Quick-Weigh reads them once as it opens. When the
spool's total changed in between (a print charged it, its total was corrected), a
reading was saved against the old figures: a Net 0 g reading went out as the old
capacity's used weight, the archive edge read grams left on the new capacity, and
the page's own `archived: true` archived a spool with grams on its record (Group 54
review R5-4).

Now each save sends `based_on` {mode, capacity, used}. /api/spool/update reads the
spool's own record first and, when what the mode depends on changed (Net and
Gross: the capacity; Additive: the used weight; Set Used: nothing), writes nothing
and answers `details_changed` with the fresh figures, and logs one WARNING line. A
request without `based_on` (an older page), or a read that isn't the spool's own
record, is handled as before. The page half is test_weigh_based_on_page_63_6_js.

The REAL route and update_spool over tests/spoolman_extra_fake.SpoolmanHTTPFake.
Tests marked RED fail on e1b22f4 (the branch's base).
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import spoolman_api as sm_api  # noqa: E402
import state  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake  # noqa: E402

SPOOL_FIELDS = [
    {"key": k, "field_type": "text", "name": k} for k in (
        "container_slot", "physical_source", "physical_source_slot",
        "fcc_pre_archive_location", "fcc_pre_box_location", "fcc_pre_audit_location")
]


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


@pytest.fixture
def spoolman(monkeypatch):
    """#57 at CR-SHELF: its total corrected to 1200 g since the page read 1000 g,
    700 g used."""
    fake = SpoolmanHTTPFake(version="0.27.0", fields={"spool": copy.deepcopy(SPOOL_FIELDS)})
    fake.add("spool", 57, {}, location="CR-SHELF", initial_weight=1200.0, used_weight=700.0, archived=False)
    monkeypatch.setattr(sm_api.config_loader, "get_api_urls", lambda: ("http://sm.test", "http://fb"))
    monkeypatch.setattr(sm_api.requests, "get", fake.get)
    monkeypatch.setattr(sm_api.requests, "patch", fake.patch)
    monkeypatch.setattr(sm_api.locations_db, "get_active_printer_map", lambda *a, **k: {})
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(sm_api, name, {}).clear()
    yield fake
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(sm_api, name, {}).clear()


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _save(client, updates, based_on=None, **extra):
    body = {"id": 57, "updates": updates, "auto_archive": True, **extra}
    if based_on is not None:
        body["based_on"] = based_on
    return client.post("/api/spool/update", json=body).get_json()


@pytest.mark.parametrize("mode", ["net", "gross"])
def test_a_reading_against_an_old_total_is_refused_with_nothing_written(spoolman, client, mode):
    """RED on e1b22f4: a Net (or Gross) reading of what is left, 0 g, worked out
    against the old 1000 g total, went out as used 1000 g with `archived: true`, and
    the spool was archived with 200 g on its record."""
    body = _save(client, {"used_weight": 1000.0, "archived": True},
                 based_on={"mode": mode, "capacity": 1000, "used": 700})
    assert body["status"] == "details_changed" and body["changed"] == "capacity", body
    assert body["fresh"] == {"initial": 1200.0, "used": 700.0, "archived": False}, body
    assert body["msg"] == "#57's weight changed since this was read: check its preview and press Enter again", body
    assert spoolman.patches == [], spoolman.patches
    rec = spoolman.records["spool"][57]
    assert rec["archived"] is False and rec["used_weight"] == 700.0, rec
    (line,) = [e for e in state.RECENT_LOGS if "reading wasn't saved" in e["msg"]]
    assert line["type"] == "WARNING" and "its total changed since it was read (1000 g, now 1200 g)" in line["msg"], line


def test_an_additive_reading_against_an_old_used_weight_is_refused(spoolman, client):
    """RED on e1b22f4: +25 g on the used weight the page read (650 g) went out as
    675 g, dropping the 50 g a print charged meanwhile."""
    body = _save(client, {"used_weight": 675.0}, based_on={"mode": "additive", "capacity": 1200, "used": 650})
    assert body["status"] == "details_changed" and body["changed"] == "used", body
    assert spoolman.patches == []


def test_control_set_used_depends_on_nothing(spoolman, client):
    """Control: Set Used is the used weight itself, so a changed total asks nothing."""
    body = _save(client, {"used_weight": 900.0}, based_on={"mode": "set_used", "capacity": 1000, "used": 0})
    assert body["status"] == "success", body
    assert spoolman.records["spool"][57]["used_weight"] == 900.0


@pytest.mark.parametrize("based_on", [
    {"mode": "net", "capacity": 1200, "used": 700},
    {"mode": "net", "capacity": 1200.03, "used": 0},
    {"mode": "additive", "capacity": 0, "used": 700},
], ids=["unchanged", "within-a-rounding", "additive-unchanged"])
def test_control_figures_that_didnt_change_save_as_before(spoolman, client, based_on):
    body = _save(client, {"used_weight": 800.0}, based_on=based_on)
    assert body["status"] == "success", body
    assert spoolman.records["spool"][57]["used_weight"] == 800.0


@pytest.mark.parametrize("based_on", [None, {}, {"mode": "net"}, {"mode": "net", "capacity": "x"},
                                      {"mode": "net", "capacity": True}, "net"],
                         ids=["absent", "empty", "no-capacity", "text", "bool", "not-a-dict"])
def test_control_a_basis_it_cant_compare_is_no_check(spoolman, client, based_on):
    """Control (an older page sends none): saved as before."""
    body = _save(client, {"used_weight": 800.0}, based_on=based_on)
    assert body["status"] == "success", body


def test_control_a_read_that_isnt_the_spools_record_is_no_check(spoolman, client, monkeypatch):
    """Control: with no record of the spool to compare (a 5xx body, no answer), the
    save goes on as before; update_spool's own rules decide."""
    monkeypatch.setattr(sm_api, "get_spool", lambda sid: {"message": "database is locked"})
    body = _save(client, {"used_weight": 800.0}, based_on={"mode": "net", "capacity": 1000, "used": 700})
    assert body["status"] == "success", body
