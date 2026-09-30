"""Hotfix 2026-09-29 — Core One → Core One+ INDX printer setup (Derek's report).

Derek rebuilt his Core One into an 8-head INDX and set it up on prod. Prod's
locations.json afterwards: Printer row RCOI ("🦝 Core One INDX") with toolheads
RCOI-1..RCOI-8 and a hand-made Tool Head row for each — but NO printer_creds,
although he had entered the PrusaLink IP + API key more than once. The
config.json:printer_map seed still names the deleted CORE1.

Pinned here, each against the code path that caused it:

1. Boot must not resurrect a deleted printer from the vestigial
   config.json:printer_map seed once the Printer rows are authoritative
   (startup_migrations re-created a creds-less "Core One Upgraded" CORE1 row
   on every restart). A fresh install still bootstraps from the seed.
2. A Location-Manager edit must not drop row fields the edit modal doesn't
   own. The modal posts only LocationID/Name/Type/Max Spools, and the POST
   replaced the whole row — so renaming a Printer silently dropped its
   toolheads[] and renaming a Dryer Box silently dropped extra.slot_targets.
3. Toolheads saved in the Settings editor get Location rows (so spools can be
   assigned to them), and a toolhead created in the Location Manager under a
   Printer is registered in that Printer's toolheads[].
4. Printer connections are addressed by the Printer row's LocationID, not by
   its display Name, and printer Names stay unique — a shared Name made the
   Settings grid display one row while the save wrote another.
"""
import copy
from contextlib import ExitStack
from unittest.mock import patch

import pytest

import config_schema
import locations_db


XL_CREDS = {"ip_address": "192.168.1.121", "api_key": "XLKEY"}
INDX_CREDS = {"ip_address": "192.168.1.120", "api_key": "INDXKEY"}
INDX_NAME = "🦝 Core One INDX"


def _heads(prefix, count):
    return [{"location_id": f"{prefix}-{n}", "position": n - 1} for n in range(1, count + 1)]


def _prod_like_rows():
    """Prod's shape on 2026-09-29 (keys masked), trimmed to what these paths read."""
    rows = [
        {"LocationID": "CR", "Name": "Computer Room", "Type": "Room", "parent_id": None},
        {"LocationID": "LR", "Name": "Living Room", "Type": "Room", "parent_id": None},
        {"LocationID": "RCOI", "Name": INDX_NAME, "Type": "Printer", "Max Spools": "0",
         "parent_id": None, "toolheads": _heads("RCOI", 8)},
        {"LocationID": "XL", "Name": "🦝 XL", "Type": "Printer", "Max Spools": "0",
         "parent_id": "LR", "toolheads": _heads("XL", 5), "printer_creds": dict(XL_CREDS)},
        {"LocationID": "PM-DB-1", "Name": "PolyDryer 1", "Type": "Dryer Box", "Max Spools": "4",
         "parent_id": "PM", "extra": {"slot_targets": {"1": "XL-1", "2": "RCOI-2"}}},
    ]
    for n in range(1, 9):
        rows.append({"LocationID": f"RCOI-{n}", "Name": f"{INDX_NAME} Tool Head {n}",
                     "Type": "Tool Head", "Max Spools": "1", "parent_id": "RCOI"})
    for n in range(1, 6):
        rows.append({"LocationID": f"XL-{n}", "Name": f"🦝 XL Tool Head {n}",
                     "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"})
    return rows


# The stale seed prod still carries: CORE1 was deleted from the rows, not from here.
VESTIGIAL_CONFIG = {"printer_map": {
    "CORE1": {"printer_name": "🦝 Core One Upgraded", "position": 0},
    **{f"XL-{n}": {"printer_name": "🦝 XL", "position": n - 1} for n in range(1, 6)},
}}


class _Store:
    """In-memory locations.json: every load sees the latest save."""

    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)
        self.saves = 0

    def load(self):
        return copy.deepcopy(self.rows)

    def save(self, lst):
        self.rows = copy.deepcopy(lst)
        self.saves += 1
        return True

    def row(self, loc_id):
        return next((r for r in self.rows if r.get("LocationID") == loc_id), None)


def _patch_store(stack, store):
    stack.enter_context(patch.object(locations_db, "load_locations_list", side_effect=store.load))
    stack.enter_context(patch.object(locations_db, "save_locations_list", side_effect=store.save))


@pytest.fixture
def client():
    import app
    app.app.config["TESTING"] = True
    return app.app.test_client()


def _run_boot(store, cfg, tmp_path):
    import config_loader
    import startup_migrations
    with ExitStack() as stack:
        _patch_store(stack, store)
        stack.enter_context(patch.object(config_loader, "load_config", return_value=copy.deepcopy(cfg)))
        # Keep the migrations' backup side effects off the real data dir.
        stack.enter_context(patch.object(locations_db, "JSON_FILE", str(tmp_path / "locations.json")))
        stack.enter_context(patch("shutil.copy2"))
        stack.enter_context(patch.object(startup_migrations, "_prune_locations_backups", return_value=[]))
        startup_migrations.run_startup_migrations()


# --------------------------------------------------------------------------- #
# 1. Boot never resurrects a deleted printer from the vestigial seed           #
# --------------------------------------------------------------------------- #

def test_boot_does_not_resurrect_deleted_printer_from_vestigial_config(tmp_path):
    store = _Store(_prod_like_rows())
    _run_boot(store, VESTIGIAL_CONFIG, tmp_path)
    assert store.row("CORE1") is None, (
        "a restart re-created the deleted CORE1 printer from config.json:printer_map")
    assert store.row("RCOI")["toolheads"] == _heads("RCOI", 8)


def test_boot_does_not_prime_toolheads_onto_a_hand_made_printer_row(tmp_path):
    # A Printer row made in the Location Manager has no toolheads key yet. Once
    # the rows are authoritative, the stale seed must not hand it the old CORE1
    # head.
    rows = _prod_like_rows() + [{"LocationID": "CORE1", "Name": "Spare", "Type": "Printer",
                                 "Max Spools": "0", "parent_id": None}]
    store = _Store(rows)
    _run_boot(store, VESTIGIAL_CONFIG, tmp_path)
    assert "toolheads" not in store.row("CORE1")


def test_boot_still_bootstraps_printer_rows_on_a_fresh_install(tmp_path):
    # No Printer rows yet (a pre-L271 install): the seed must still build them.
    rows = [r for r in _prod_like_rows()
            if r.get("Type") != "Printer" and not str(r.get("LocationID")).startswith("RCOI")]
    rows.append({"LocationID": "CORE1", "Name": "Core One", "Type": "Tool Head", "Max Spools": "1"})
    store = _Store(rows)
    _run_boot(store, VESTIGIAL_CONFIG, tmp_path)
    core1, xl = store.row("CORE1"), store.row("XL")
    assert core1["Type"] == "Printer" and core1["toolheads"] == [{"location_id": "CORE1", "position": 0}]
    assert xl["Type"] == "Printer" and xl["toolheads"] == _heads("XL", 5)


# --------------------------------------------------------------------------- #
# 2. A Location-Manager edit keeps the fields its modal doesn't own             #
# --------------------------------------------------------------------------- #

def _post_edit(client, store, old_id, new_data):
    with ExitStack() as stack:
        _patch_store(stack, store)
        return client.post("/api/locations", json={"old_id": old_id, "new_data": new_data})


def test_location_manager_printer_rename_keeps_toolheads_and_creds(client):
    rows = _prod_like_rows()
    next(r for r in rows if r["LocationID"] == "RCOI")["printer_creds"] = dict(INDX_CREDS)
    store = _Store(rows)
    res = _post_edit(client, store, "RCOI", {
        "LocationID": "RCOI", "Name": "🦝 Core One+ INDX", "Type": "Printer", "Max Spools": "0"})
    assert res.status_code == 200, res.get_json()
    rcoi = store.row("RCOI")
    assert rcoi["Name"] == "🦝 Core One+ INDX"
    assert rcoi.get("toolheads") == _heads("RCOI", 8), "the edit dropped the printer's toolheads"
    assert rcoi.get("printer_creds") == INDX_CREDS


def test_location_manager_dryer_box_rename_keeps_slot_bindings(client):
    store = _Store(_prod_like_rows())
    res = _post_edit(client, store, "PM-DB-1", {
        "LocationID": "PM-DB-1", "Name": "PolyDryer One", "Type": "Dryer Box", "Max Spools": "4"})
    assert res.status_code == 200, res.get_json()
    box = store.row("PM-DB-1")
    assert box["Name"] == "PolyDryer One"
    assert box.get("extra") == {"slot_targets": {"1": "XL-1", "2": "RCOI-2"}}, (
        "the edit dropped the box's slot → toolhead bindings")


def test_location_manager_refuses_renaming_a_printer_id_with_toolheads(client):
    # Toolheads are grouped under a printer by id prefix: RCOI → INDX would leave
    # RCOI-1..8 under a printer that no longer matches them.
    store = _Store(_prod_like_rows())
    res = _post_edit(client, store, "RCOI", {
        "LocationID": "INDX", "Name": INDX_NAME, "Type": "Printer", "Max Spools": "0"})
    assert res.status_code == 400
    assert "Name instead" in res.get_json()["error"]
    assert store.saves == 0


def test_location_manager_refuses_renaming_a_dual_role_printer_id(client):
    rows = [r for r in _prod_like_rows() if not str(r["LocationID"]).startswith("RCOI")]
    rows.append({"LocationID": "CORE1", "Name": "🦝 Core One Upgraded", "Type": "Printer",
                 "Max Spools": "1", "parent_id": "CR", "toolheads": [{"location_id": "CORE1", "position": 0}]})
    store = _Store(rows)
    res = _post_edit(client, store, "CORE1", {
        "LocationID": "C1", "Name": "🦝 Core One Upgraded", "Type": "Printer", "Max Spools": "1"})
    assert res.status_code == 400
    assert store.saves == 0


def test_location_manager_allows_renaming_a_toolhead_less_printer_id(client):
    rows = _prod_like_rows() + [{"LocationID": "SPARE", "Name": "🦝 Spare", "Type": "Printer",
                                 "Max Spools": "0", "parent_id": None}]
    store = _Store(rows)
    res = _post_edit(client, store, "SPARE", {
        "LocationID": "SPARE2", "Name": "🦝 Spare", "Type": "Printer", "Max Spools": "0"})
    assert res.status_code == 200, res.get_json()
    assert store.row("SPARE") is None and store.row("SPARE2") is not None


def test_location_manager_refuses_renaming_a_registered_toolhead_id(client):
    store = _Store(_prod_like_rows())
    res = _post_edit(client, store, "RCOI-1", {
        "LocationID": "RCOI-A", "Name": f"{INDX_NAME} Tool Head 1", "Type": "Tool Head", "Max Spools": "1"})
    assert res.status_code == 400
    assert "RCOI" in res.get_json()["error"]
    assert store.saves == 0


def test_location_manager_toolhead_name_edit_is_allowed_and_not_double_registered(client):
    store = _Store(_prod_like_rows())
    res = _post_edit(client, store, "RCOI-1", {
        "LocationID": "RCOI-1", "Name": "T1 — PLA Basic", "Type": "Tool Head", "Max Spools": "1"})
    assert res.status_code == 200, res.get_json()
    assert store.row("RCOI-1")["Name"] == "T1 — PLA Basic"
    assert store.row("RCOI-1")["parent_id"] == "RCOI"
    assert store.row("RCOI")["toolheads"] == _heads("RCOI", 8)


def test_location_manager_edit_still_applies_the_fields_it_sends(client):
    store = _Store(_prod_like_rows())
    res = _post_edit(client, store, "PM-DB-1", {
        "LocationID": "PM-DB-1", "Name": "PolyDryer 1", "Type": "Dryer Box", "Max Spools": "2",
        "parent_id": None})
    assert res.status_code == 200, res.get_json()
    box = store.row("PM-DB-1")
    assert box["Max Spools"] == "2"
    assert box["parent_id"] is None


# --------------------------------------------------------------------------- #
# 3. Settings toolheads ↔ Location Manager rows stay in step                    #
# --------------------------------------------------------------------------- #

def _put_map(client, store, printer_map):
    with ExitStack() as stack:
        _patch_store(stack, store)
        return client.put("/api/printer_map", json={"printer_map": printer_map})


def _map_from_rows(rows):
    return {k: dict(v) for k, v in locations_db.build_printer_map_from_rows(rows).items()}


def test_settings_new_toolhead_gets_a_location_row(client):
    rows = _prod_like_rows()
    store = _Store(rows)
    pm = _map_from_rows(rows)
    pm["RCOI-9"] = {"printer_name": INDX_NAME, "position": 8}
    res = _put_map(client, store, pm)
    assert res.status_code == 200 and res.get_json()["ok"], res.get_json()
    head = store.row("RCOI-9")
    assert head is not None, "a toolhead saved in Settings got no Location row"
    assert head["Type"] == "Tool Head"
    assert head["Name"] == f"{INDX_NAME} Tool Head 9"
    assert head["Max Spools"] == "1"
    assert head["parent_id"] == "RCOI"


def test_settings_new_printer_gets_printer_and_toolhead_rows(client):
    rows = _prod_like_rows()
    store = _Store(rows)
    pm = _map_from_rows(rows)
    pm.update({"MK4-1": {"printer_name": "🦝 MK4", "position": 0},
               "MK4-2": {"printer_name": "🦝 MK4", "position": 1}})
    res = _put_map(client, store, pm)
    assert res.status_code == 200 and res.get_json()["ok"], res.get_json()
    assert store.row("MK4")["Type"] == "Printer"
    for n in (1, 2):
        head = store.row(f"MK4-{n}")
        assert head is not None and head["Type"] == "Tool Head" and head["parent_id"] == "MK4"
        assert head["Name"] == f"🦝 MK4 Tool Head {n}"


def test_settings_save_never_clobbers_an_existing_location_row(client):
    rows = _prod_like_rows()
    next(r for r in rows if r["LocationID"] == "XL-1")["Name"] = "Left nozzle (custom)"
    store = _Store(rows)
    res = _put_map(client, store, _map_from_rows(rows))
    assert res.status_code == 200, res.get_json()
    assert store.row("XL-1")["Name"] == "Left nozzle (custom)"
    assert sum(1 for r in store.rows if r.get("LocationID") == "XL-1") == 1


def test_settings_dual_role_printer_gets_no_extra_toolhead_row(client):
    # CORE1-style printer that is its own single toolhead: the Printer row IS the
    # deploy location, so no separate Tool Head row may appear.
    rows = [r for r in _prod_like_rows() if not str(r["LocationID"]).startswith("RCOI")]
    store = _Store(rows)
    pm = _map_from_rows(rows)
    pm["SOLO"] = {"printer_name": "🦝 Solo", "position": 0}
    res = _put_map(client, store, pm)
    assert res.status_code == 200 and res.get_json()["ok"], res.get_json()
    solo = [r for r in store.rows if r.get("LocationID") == "SOLO"]
    assert len(solo) == 1 and solo[0]["Type"] == "Printer"


def test_location_manager_new_toolhead_is_registered_on_its_printer(client):
    store = _Store(_prod_like_rows())
    with ExitStack() as stack:
        _patch_store(stack, store)
        res = client.post("/api/locations", json={"old_id": "", "new_data": {
            "LocationID": "RCOI-9", "Name": f"{INDX_NAME} Tool Head 9",
            "Type": "Tool Head", "Max Spools": "1"}})
    assert res.status_code == 200, res.get_json()
    assert store.row("RCOI-9")["parent_id"] == "RCOI"
    assert {"location_id": "RCOI-9", "position": 8} in store.row("RCOI")["toolheads"], (
        "a toolhead made in the Location Manager never reached the printer's toolheads[]")


def test_location_manager_new_toolhead_takes_its_tool_number_as_position(client):
    # RCOI-10 is tool T9 — its position comes from the number, not "last + 1"
    # (the deduct bills spools by position).
    store = _Store(_prod_like_rows())
    with ExitStack() as stack:
        _patch_store(stack, store)
        res = client.post("/api/locations", json={"old_id": "", "new_data": {
            "LocationID": "RCOI-10", "Name": "Tool 10", "Type": "Tool Head", "Max Spools": "1"}})
    assert res.status_code == 200 and "warning" not in res.get_json(), res.get_json()
    assert {"location_id": "RCOI-10", "position": 9} in store.row("RCOI")["toolheads"]


@pytest.mark.parametrize("new_id, parent", [
    ("INDX-T9", "RCOI"),     # doesn't share the printer's prefix — Settings would split it off
    ("RCOI-LEFT", None),     # no tool number to take a position from
])
def test_location_manager_ambiguous_toolhead_is_saved_but_not_registered(client, new_id, parent):
    store = _Store(_prod_like_rows())
    new_data = {"LocationID": new_id, "Name": "Tool ?", "Type": "Tool Head", "Max Spools": "1"}
    if parent:
        new_data["parent_id"] = parent
    with ExitStack() as stack:
        _patch_store(stack, store)
        res = client.post("/api/locations", json={"old_id": "", "new_data": new_data})
    assert res.status_code == 200, res.get_json()
    assert store.row(new_id) is not None
    assert "Settings" in res.get_json()["warning"]
    assert store.row("RCOI")["toolheads"] == _heads("RCOI", 8)


def test_location_manager_toolhead_whose_position_is_taken_is_not_registered(client):
    rows = _prod_like_rows()
    printer = next(r for r in rows if r["LocationID"] == "RCOI")
    printer["toolheads"] = printer["toolheads"][:7] + [{"location_id": "RCOI-X", "position": 8}]
    store = _Store(rows)
    with ExitStack() as stack:
        _patch_store(stack, store)
        res = client.post("/api/locations", json={"old_id": "", "new_data": {
            "LocationID": "RCOI-9", "Name": "Tool 9", "Type": "Tool Head", "Max Spools": "1"}})
    assert res.status_code == 200
    assert "warning" in res.get_json()
    assert not any(h["location_id"] == "RCOI-9" for h in store.row("RCOI")["toolheads"])


def test_location_manager_failed_save_reports_an_error(client):
    store = _Store(_prod_like_rows())
    with patch.object(locations_db, "load_locations_list", side_effect=store.load), \
         patch.object(locations_db, "save_locations_list", return_value=False):
        res = client.post("/api/locations", json={"old_id": "PM-DB-1", "new_data": {
            "LocationID": "PM-DB-1", "Name": "PolyDryer One", "Type": "Dryer Box", "Max Spools": "4"}})
    assert res.status_code == 500
    assert res.get_json()["success"] is False


def test_settings_toolhead_row_carries_the_legacy_columns(client):
    rows = _prod_like_rows()
    store = _Store(rows)
    pm = _map_from_rows(rows)
    pm["XL-6"] = {"printer_name": "🦝 XL", "position": 5}
    res = _put_map(client, store, pm)
    assert res.status_code == 200 and res.get_json()["ok"], res.get_json()
    head = store.row("XL-6")
    assert head == {"LocationID": "XL-6", "Location": "Living Room", "Device Identifier": "",
                    "Device Type": "", "Type": "Tool Head", "Order": "6", "Row": "",
                    "Max Spools": "1", "Name": "🦝 XL Tool Head 6", "Label Printed": "No",
                    "parent_id": "XL"}


# --------------------------------------------------------------------------- #
# Deleting a printer, and loading a spool onto one                              #
# --------------------------------------------------------------------------- #

def test_deleting_a_printer_that_still_has_toolheads_is_refused(client):
    import spoolman_api
    store = _Store(_prod_like_rows())
    with ExitStack() as stack:
        _patch_store(stack, store)
        unassign = stack.enter_context(patch.object(spoolman_api, "update_spool", return_value=True))
        at_loc = stack.enter_context(patch.object(spoolman_api, "get_spools_at_location", return_value=[101, 102]))
        res = client.delete("/api/locations?id=RCOI")
    assert res.status_code == 409
    assert "Settings" in res.get_json()["error"]
    assert store.row("RCOI") is not None and store.saves == 0
    unassign.assert_not_called()
    at_loc.assert_not_called()


def test_deleting_a_dual_role_printer_keeps_the_existing_path(client):
    import spoolman_api
    rows = [r for r in _prod_like_rows() if not str(r["LocationID"]).startswith("RCOI")]
    rows.append({"LocationID": "CORE1", "Name": "🦝 Core One Upgraded", "Type": "Printer",
                 "Max Spools": "1", "toolheads": [{"location_id": "CORE1", "position": 0}]})
    store = _Store(rows)
    with ExitStack() as stack:
        _patch_store(stack, store)
        stack.enter_context(patch.object(spoolman_api, "get_spools_at_location", return_value=[]))
        res = client.delete("/api/locations?id=CORE1")
    assert res.status_code == 200, res.get_json()
    assert store.row("CORE1") is None


def test_loading_onto_a_multi_head_printer_row_does_not_eject_its_heads():
    # The resident lookup prefix-matches child ids, so treating the INDX's
    # Printer row as a single-occupancy slot ejected the spool on every head.
    import logic
    import prusalink_api
    import spoolman_api
    rows = _prod_like_rows()
    incoming = {"id": 8, "location": "", "extra": {}}
    with patch.object(locations_db, "load_locations_list", return_value=copy.deepcopy(rows)), \
         patch.object(spoolman_api, "get_spools_at_location", return_value=[101, 102]), \
         patch.object(spoolman_api, "get_spool", return_value=incoming), \
         patch.object(spoolman_api, "update_spool", return_value=True), \
         patch.object(spoolman_api, "format_spool_display", return_value={"text": "", "color": "000"}), \
         patch.object(prusalink_api, "get_printer_state", return_value=None), \
         patch.object(logic, "perform_smart_eject") as eject:
        logic.perform_smart_move("RCOI", [8])
    eject.assert_not_called()


# --------------------------------------------------------------------------- #
# Stale Spoolman-native locations                                               #
# --------------------------------------------------------------------------- #

class _SpoolResp:
    ok = True

    def __init__(self, spools):
        self._spools = spools

    def json(self):
        return self._spools


def _get_locations(client, native_names, live_spools):
    import app
    with patch.object(app.locations_db, "load_locations_list", return_value=copy.deepcopy(_prod_like_rows())), \
         patch.object(app.spoolman_api, "get_all_locations", return_value=native_names), \
         patch.object(app.config_loader, "get_api_urls", return_value=("http://spool", "http://fb/api")), \
         patch.object(app.requests, "get", return_value=_SpoolResp(live_spools)):
        res = client.get("/api/locations")
    assert res.status_code == 200
    return {r["LocationID"]: r for r in res.get_json()}


def test_native_location_only_archived_spools_reference_is_hidden(client):
    # Spoolman's /location still lists "Old Shelf" (an archived spool sits
    # there); /spool lists only live spools and none are at it.
    rows = _get_locations(client, ["Old Shelf", "Garage"], [{"id": 1, "location": "Garage", "extra": {}}])
    assert "Old Shelf" not in rows
    assert rows["Garage"]["Type"] == "Spoolman Native"
    assert all("_synth_native" not in r for r in rows.values())


def test_native_location_with_only_a_deployed_ghost_stays_listed(client):
    rows = _get_locations(client, ["Shelf Box"], [{"id": 2, "location": "XL-1",
                                                   "extra": {"physical_source": "Shelf Box"}}])
    assert "Shelf Box" in rows


def test_location_manager_non_toolhead_under_printer_is_not_registered(client):
    store = _Store(_prod_like_rows())
    with ExitStack() as stack:
        _patch_store(stack, store)
        res = client.post("/api/locations", json={"old_id": "", "new_data": {
            "LocationID": "RCOI-SHELF", "Name": "Top shelf", "Type": "Storage",
            "Max Spools": "2", "parent_id": "RCOI"}})
    assert res.status_code == 200, res.get_json()
    assert store.row("RCOI")["toolheads"] == _heads("RCOI", 8)


# --------------------------------------------------------------------------- #
# 4. Connections addressed by LocationID; printer Names unique                  #
# --------------------------------------------------------------------------- #

def test_printer_map_get_lists_every_printer_row_by_location_id(client):
    rows = _prod_like_rows()
    rows.append({"LocationID": "SPARE", "Name": "🦝 Spare", "Type": "Printer", "Max Spools": "0"})
    store = _Store(rows)
    with ExitStack() as stack:
        _patch_store(stack, store)
        res = client.get("/api/printer_map")
    assert res.status_code == 200
    by_id = {p["location_id"]: p for p in res.get_json()["printer_rows"]}
    assert set(by_id) == {"RCOI", "XL", "SPARE"}, "toolhead-less printers must still get a connection row"
    assert by_id["RCOI"] == {"location_id": "RCOI", "name": INDX_NAME, "ip_address": "",
                             "api_key": "", "toolhead_count": 8}
    assert by_id["XL"]["ip_address"] == XL_CREDS["ip_address"]
    assert by_id["XL"]["api_key"] == config_schema.SECRET_SENTINEL
    assert "XLKEY" not in res.get_data(as_text=True)


def _put_creds(client, store, body):
    with ExitStack() as stack:
        _patch_store(stack, store)
        return client.put("/api/printer_creds", json=body)


def test_put_printer_creds_by_location_id(client):
    store = _Store(_prod_like_rows())
    res = _put_creds(client, store, {"location_id": "RCOI", **INDX_CREDS})
    assert res.status_code == 200 and res.get_json()["ok"], res.get_json()
    assert store.row("RCOI")["printer_creds"] == INDX_CREDS


def test_put_printer_creds_by_location_id_ignores_a_shared_name(client):
    # Two Printer rows that share a Name (the state the rename left behind):
    # the Settings grid addresses the row by id, so the save lands on it.
    rows = _prod_like_rows()
    rows.insert(0, {"LocationID": "CORE1", "Name": INDX_NAME, "Type": "Printer",
                    "Max Spools": "0", "toolheads": [], "printer_creds": {"ip_address": "10.0.0.1",
                                                                         "api_key": "OLD"}})
    store = _Store(rows)
    res = _put_creds(client, store, {"location_id": "RCOI", "printer_name": INDX_NAME, **INDX_CREDS})
    assert res.status_code == 200 and res.get_json()["ok"], res.get_json()
    assert store.row("RCOI")["printer_creds"] == INDX_CREDS
    assert store.row("CORE1")["printer_creds"] == {"ip_address": "10.0.0.1", "api_key": "OLD"}


def test_put_printer_creds_unknown_location_id_is_404(client):
    store = _Store(_prod_like_rows())
    res = _put_creds(client, store, {"location_id": "NOPE", **INDX_CREDS})
    assert res.status_code == 404
    assert store.saves == 0


def test_put_printer_creds_location_id_must_be_a_printer(client):
    store = _Store(_prod_like_rows())
    res = _put_creds(client, store, {"location_id": "RCOI-1", **INDX_CREDS})
    assert res.status_code == 404
    assert store.saves == 0


@pytest.mark.parametrize("address", [{"location_id": "XL"}, {"printer_name": "🦝 XL"}])
def test_put_printer_creds_refuses_a_new_key_without_an_ip(client, address):
    # A blank IP clears the whole connection, so a typed key sent with it used to
    # delete the saved connection while the editor reported success.
    store = _Store(_prod_like_rows())
    res = _put_creds(client, store, {**address, "ip_address": "", "api_key": "NEWKEY"})
    assert res.status_code == 400
    assert store.saves == 0
    assert store.row("XL")["printer_creds"] == XL_CREDS


def test_put_printer_creds_blank_ip_and_kept_key_still_clears_by_id(client):
    store = _Store(_prod_like_rows())
    res = _put_creds(client, store, {"location_id": "XL", "ip_address": "",
                                     "api_key": config_schema.SECRET_SENTINEL})
    assert res.status_code == 200 and res.get_json()["ok"]
    assert "printer_creds" not in store.row("XL")


def test_put_printer_creds_by_id_sentinel_keeps_the_stored_key(client):
    store = _Store(_prod_like_rows())
    res = _put_creds(client, store, {"location_id": "XL", "ip_address": "192.168.1.99",
                                     "api_key": config_schema.SECRET_SENTINEL})
    assert res.status_code == 200 and res.get_json()["ok"]
    assert store.row("XL")["printer_creds"] == {"ip_address": "192.168.1.99", "api_key": "XLKEY"}


def test_settings_removed_toolhead_loses_its_now_empty_row(client):
    rows = _prod_like_rows()
    store = _Store(rows)
    pm = _map_from_rows(rows)
    del pm["RCOI-8"]
    with patch("routes_bindings._printer_map_blocked_removals", return_value=[]):
        res = _put_map(client, store, pm)
    assert res.status_code == 200 and res.get_json()["ok"], res.get_json()
    assert store.row("RCOI-8") is None
    assert res.get_json()["removed_toolhead_rows"] == ["RCOI-8"]
    assert store.row("RCOI")["toolheads"] == _heads("RCOI", 7)


def test_settings_removed_toolhead_keeps_a_row_something_is_parented_under(client):
    rows = _prod_like_rows() + [{"LocationID": "PM-DB-11", "Name": "PolyDryer 11", "Type": "Dryer Box",
                                 "Max Spools": "1", "parent_id": "RCOI-8"}]
    store = _Store(rows)
    pm = _map_from_rows(rows)
    del pm["RCOI-8"]
    with patch("routes_bindings._printer_map_blocked_removals", return_value=[]):
        res = _put_map(client, store, pm)
    assert res.status_code == 200 and res.get_json()["ok"], res.get_json()
    assert store.row("RCOI-8") is not None


def test_get_creds_prefers_the_same_named_row_that_has_an_ip():
    rows = [
        {"LocationID": "CORE1", "Type": "Printer", "Name": INDX_NAME},
        {"LocationID": "RCOI", "Type": "Printer", "Name": INDX_NAME,
         "printer_creds": dict(INDX_CREDS)},
    ]
    assert locations_db.get_printer_credentials(INDX_NAME, rows) == INDX_CREDS


def test_settings_rejects_two_printers_sharing_a_name(client):
    rows = _prod_like_rows()
    store = _Store(rows)
    pm = _map_from_rows(rows)
    pm["MK4-1"] = {"printer_name": INDX_NAME, "position": 0}   # different prefix, same Name
    res = _put_map(client, store, pm)
    assert res.status_code == 400
    assert "MK4" in res.get_json()["error"] and "RCOI" in res.get_json()["error"]
    assert store.saves == 0


def test_settings_rejects_a_name_held_by_a_toolhead_less_printer(client):
    rows = _prod_like_rows()
    rows.append({"LocationID": "CORE1", "Name": "🦝 Core One Upgraded", "Type": "Printer",
                 "Max Spools": "0", "toolheads": []})
    store = _Store(rows)
    pm = _map_from_rows(rows)
    for k in list(pm):
        if k.startswith("RCOI-"):
            pm[k]["printer_name"] = "🦝 Core One Upgraded"
    res = _put_map(client, store, pm)
    assert res.status_code == 400
    assert "CORE1" in res.get_json()["error"]
    assert store.saves == 0


def test_location_manager_rejects_a_duplicate_printer_name(client):
    store = _Store(_prod_like_rows())
    with ExitStack() as stack:
        _patch_store(stack, store)
        res = client.post("/api/locations", json={"old_id": "", "new_data": {
            "LocationID": "SPARE", "Name": INDX_NAME, "Type": "Printer", "Max Spools": "0"}})
    assert res.status_code == 400
    assert "RCOI" in res.get_json()["error"]
    assert store.saves == 0


def test_location_manager_printer_name_is_trimmed(client):
    store = _Store(_prod_like_rows())
    res = _post_edit(client, store, "RCOI", {
        "LocationID": "RCOI", "Name": f"  {INDX_NAME}  ", "Type": "Printer", "Max Spools": "0"})
    assert res.status_code == 200, res.get_json()
    assert store.row("RCOI")["Name"] == INDX_NAME
