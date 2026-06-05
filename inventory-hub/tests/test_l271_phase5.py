"""L271 Phase 5 — Edit-UI explicit parent + shelf grouping (Wall/Row) tests.

Three slices:
  (a) explicit Parent selector + write-time validation in api_save_location
      (LIVE integration — must reject a non-existent / self / descendant parent);
  (b) "Printer" + "No MMU Direct Load" in the Type dropdown, Wall/Row badges,
      wizard exclusion (source canaries);
  (c) migrate_shelf_grouping_rows_if_needed — synthesize REAL Wall + Row rows so
      shelf sections nest Room → Wall → Row → Shelf (pure-function).

Pure-function tests run in-memory (no disk/server); the integration ones skip
when the dev server is down.
"""
import copy
import json
import os

import pytest

import locations_db as L

try:  # live integration helper (kept optional so the unit tests run anywhere)
    import requests
except Exception:  # pragma: no cover
    requests = None

_HUB = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*parts):
    path = os.path.join(_HUB, *parts)
    assert os.path.exists(path), f"missing: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _by_id(rows):
    return {r["LocationID"]: r for r in rows if isinstance(r, dict)}


# ---------------------------------------------------------------------------
# (c) migrate_shelf_grouping_rows_if_needed — pure function
# ---------------------------------------------------------------------------

def _dev_tree():
    """Dev shape: Computer Room + 4 flat R1 shelf sections (no Wall/Row rows)."""
    rows = [{"LocationID": "CR", "Name": "Computer Room", "Type": "Room", "parent_id": None}]
    for n in (1, 2, 3, 4):
        rows.append({
            "LocationID": f"CR-WLN-R1-SC{n}",
            "Name": f"Computer Room Wall North Row 1 Section {n}",
            "Type": "Shelf", "Max Spools": "0", "parent_id": "CR",
        })
    return rows


def _prod_tree():
    """Prod shape: R1 + R2 (8 sections), still flat under CR."""
    rows = _dev_tree()
    for n in (1, 2, 3, 4):
        rows.append({
            "LocationID": f"CR-WLN-R2-SC{n}",
            "Name": f"Computer Room Wall North Row 2 Section {n}",
            "Type": "Shelf", "Max Spools": "0", "parent_id": "CR",
        })
    return rows


def test_creates_wall_and_row_and_nests_sections():
    out, changed = L.migrate_shelf_grouping_rows_if_needed(_dev_tree())
    assert changed is True
    by = _by_id(out)
    assert by["CR-WLN"]["Type"] == "Wall" and by["CR-WLN"]["parent_id"] == "CR"
    assert by["CR-WLN-R1"]["Type"] == "Row" and by["CR-WLN-R1"]["parent_id"] == "CR-WLN"
    # grouping nodes hold no spools
    assert by["CR-WLN"]["Max Spools"] == "0" and by["CR-WLN-R1"]["Max Spools"] == "0"
    for n in (1, 2, 3, 4):
        assert by[f"CR-WLN-R1-SC{n}"]["parent_id"] == "CR-WLN-R1"


def test_names_derived_from_child_names():
    by = _by_id(L.migrate_shelf_grouping_rows_if_needed(_dev_tree())[0])
    assert by["CR-WLN"]["Name"] == "Computer Room Wall North"
    assert by["CR-WLN-R1"]["Name"] == "Computer Room Wall North Row 1"


def test_prod_shape_single_wall_two_rows():
    out, changed = L.migrate_shelf_grouping_rows_if_needed(_prod_tree())
    assert changed is True
    by = _by_id(out)
    # ONE wall shared by both rows
    assert len([r for r in out if r.get("Type") == "Wall"]) == 1
    assert by["CR-WLN-R1"]["parent_id"] == "CR-WLN"
    assert by["CR-WLN-R2"]["parent_id"] == "CR-WLN"
    assert by["CR-WLN-R2"]["Name"] == "Computer Room Wall North Row 2"
    for r in ("R1", "R2"):
        for n in (1, 2, 3, 4):
            assert by[f"CR-WLN-{r}-SC{n}"]["parent_id"] == f"CR-WLN-{r}"


def test_idempotent_second_run_is_noop():
    out1, c1 = L.migrate_shelf_grouping_rows_if_needed(_prod_tree())
    assert c1 is True
    reloaded = json.loads(json.dumps(out1))  # survive a JSON round-trip
    snapshot = copy.deepcopy(reloaded)
    out2, c2 = L.migrate_shelf_grouping_rows_if_needed(reloaded)
    assert c2 is False
    assert out2 == snapshot


def test_respects_operator_override():
    rows = _dev_tree()
    for r in rows:
        if r["LocationID"] == "CR-WLN-R1-SC1":
            r["parent_id"] = "CR-CUSTOM"  # operator hand-placed it elsewhere
    by = _by_id(L.migrate_shelf_grouping_rows_if_needed(rows)[0])
    assert by["CR-WLN-R1-SC1"]["parent_id"] == "CR-CUSTOM"   # untouched
    assert by["CR-WLN-R1-SC2"]["parent_id"] == "CR-WLN-R1"   # flat-default sibling nests
    # the grouping rows are still synthesized (SC2..4 want them)
    assert "CR-WLN" in by and "CR-WLN-R1" in by


def test_non_matching_shelves_left_flat():
    rows = [
        {"LocationID": "CR", "Name": "Computer Room", "Type": "Room", "parent_id": None},
        {"LocationID": "CR-SHELF-A", "Name": "shallow", "Type": "Shelf", "Max Spools": "0", "parent_id": "CR"},
        {"LocationID": "CR-XX-YY-ZZ", "Name": "wrong scheme", "Type": "Shelf", "Max Spools": "0", "parent_id": "CR"},
    ]
    out, changed = L.migrate_shelf_grouping_rows_if_needed(rows)
    assert changed is False
    assert not any(r.get("Type") in ("Wall", "Row") for r in out)
    by = _by_id(out)
    assert by["CR-SHELF-A"]["parent_id"] == "CR"
    assert by["CR-XX-YY-ZZ"]["parent_id"] == "CR"


def test_name_robust_to_section_number_typo():
    rows = _prod_tree()
    for r in rows:  # the real prod typo: R2-SC3 Name says "Section 1"
        if r["LocationID"] == "CR-WLN-R2-SC3":
            r["Name"] = "Computer Room Wall North Row 2 Section 1"
    by = _by_id(L.migrate_shelf_grouping_rows_if_needed(rows)[0])
    assert by["CR-WLN-R2"]["Name"] == "Computer Room Wall North Row 2"
    assert by["CR-WLN"]["Name"] == "Computer Room Wall North"


def test_result_is_immediate_parent_fixpoint():
    """The migrated state must be a fixpoint for the Phase-3.5 immediate-parent
    pass too (no conflict / no re-parent), regardless of run order."""
    out, _ = L.migrate_shelf_grouping_rows_if_needed(_prod_tree())
    _, changed = L.migrate_immediate_parent_ids_if_needed(copy.deepcopy(out))
    assert changed is False


def test_resolve_room_walks_through_wall_and_row():
    out, _ = L.migrate_shelf_grouping_rows_if_needed(_dev_tree())
    pmap = L.build_parent_map(out)
    # section → row → wall → room
    assert L.resolve_room("CR-WLN-R1-SC1", parent_map=pmap) == "CR"
    assert L.resolve_room("CR-WLN-R1", parent_map=pmap) == "CR"
    assert L.is_descendant("CR-WLN-R1-SC1", "CR", parent_map=pmap)
    assert L.is_descendant("CR-WLN-R1-SC1", "CR-WLN", parent_map=pmap)


def test_non_list_input_is_safe():
    out, changed = L.migrate_shelf_grouping_rows_if_needed("not a list")
    assert out == "not a list" and changed is False


def test_segment_and_name_helpers():
    assert L._is_wall_segment("WLN") and L._is_wall_segment("wls")
    assert not L._is_wall_segment("WL") and not L._is_wall_segment("R1")
    assert L._is_row_segment("R1") and L._is_row_segment("R12")
    assert not L._is_row_segment("RX") and not L._is_row_segment("WLN")
    assert L._decode_wall_segment("WLN") == "Wall North"
    assert L._decode_wall_segment("WLS") == "Wall South"
    assert L._decode_wall_segment("R1") is None
    assert L._name_before_token("Computer Room Wall North Row 1 Section 1", "Row") == "Computer Room Wall North"
    assert L._name_before_token("Computer Room Wall North Row 1 Section 1", "Section") == "Computer Room Wall North Row 1"
    assert L._name_before_token("no marker here", "Row") == ""


# --- review fixes ----------------------------------------------------------

def test_collision_with_non_grouping_row_at_row_id_leaves_sections_flat():
    """review #1: a pre-existing NON-grouping row at the computed Row id must
    NOT be treated as a Row, and the sections must stay flat (not nested under
    a Dryer Box etc.)."""
    rows = _dev_tree()
    rows.append({"LocationID": "CR-WLN-R1", "Name": "squatter", "Type": "Dryer Box",
                 "Max Spools": "4", "parent_id": "CR"})
    out, _ = L.migrate_shelf_grouping_rows_if_needed(rows)
    by = _by_id(out)
    assert by["CR-WLN-R1"]["Type"] == "Dryer Box"          # untouched
    assert not any(r.get("Type") == "Row" for r in out)    # no Row synthesized
    for n in (1, 2, 3, 4):
        assert by[f"CR-WLN-R1-SC{n}"]["parent_id"] == "CR"  # left flat


def test_collision_with_non_grouping_row_at_wall_id_leaves_sections_flat():
    rows = _dev_tree()
    rows.append({"LocationID": "CR-WLN", "Name": "squatter", "Type": "Storage",
                 "Max Spools": "1", "parent_id": "CR"})
    out, _ = L.migrate_shelf_grouping_rows_if_needed(rows)
    by = _by_id(out)
    assert by["CR-WLN"]["Type"] == "Storage"
    assert not any(r.get("Type") in ("Wall", "Row") for r in out)
    for n in (1, 2, 3, 4):
        assert by[f"CR-WLN-R1-SC{n}"]["parent_id"] == "CR"


def test_row_name_fallback_uses_wall_name_not_raw_id():
    """review #3: when a shelf Name lacks the 'Section' token, the Row name must
    fall back to the WALL's friendly name, not the raw 'CR-WLN' id."""
    rows = [{"LocationID": "CR", "Name": "Computer Room", "Type": "Room", "parent_id": None}]
    for n in (1, 2):
        rows.append({"LocationID": f"CR-WLN-R1-SC{n}", "Name": "unlabeled",
                     "Type": "Shelf", "Max Spools": "0", "parent_id": "CR"})
    by = _by_id(L.migrate_shelf_grouping_rows_if_needed(rows)[0])
    assert by["CR-WLN"]["Name"] == "Computer Room Wall North"      # decoded from segment
    assert by["CR-WLN-R1"]["Name"] == "Computer Room Wall North Row 1"  # NOT "CR-WLN Row 1"


def test_is_descendant_strict_ignores_dangling_dashed_fk():
    """review #5: a dangling dashed parent_id (row points at a deleted toolhead)
    must not fabricate a phantom ancestor via prefix-derivation under strict."""
    rows = [
        {"LocationID": "LR", "Type": "Room", "parent_id": None},
        {"LocationID": "XL", "Type": "Printer", "parent_id": "LR"},
        {"LocationID": "BAR", "Type": "Cart", "parent_id": "XL-2"},  # XL-2 no longer a row
    ]
    pmap = L.build_parent_map(rows)
    assert L.is_descendant("BAR", "XL", parent_map=pmap) is True          # phantom (non-strict)
    assert L.is_descendant("BAR", "XL", parent_map=pmap, strict=True) is False  # fixed


# ---------------------------------------------------------------------------
# (a) explicit-parent write-time validation — LIVE integration
# ---------------------------------------------------------------------------

def _post(api, lid, typ, **extra):
    data = {"LocationID": lid, "Name": f"t {lid}", "Type": typ, "Max Spools": "0"}
    data.update(extra)
    return requests.post(f"{api}/api/locations", json={"old_id": extra.get("_old", ""), "new_data": data}, timeout=10)


def _all(api):
    return {str(x.get("LocationID")): x for x in requests.get(f"{api}/api/locations", timeout=10).json()}


def _cleanup(api, *ids):
    for lid in ids:
        try:
            requests.delete(f"{api}/api/locations", params={"id": lid}, timeout=10)
        except Exception:
            pass


@pytest.mark.integration
def test_explicit_parent_id_is_honored(api_base_url, require_server):
    room, shelf = "ZZP5HR", "ZZP5HR-S1"
    try:
        requests.post(f"{api_base_url}/api/locations", json={"old_id": "", "new_data": {
            "LocationID": room, "Name": "t room", "Type": "Room", "Max Spools": "0"}}, timeout=10).raise_for_status()
        r = requests.post(f"{api_base_url}/api/locations", json={"old_id": "", "new_data": {
            "LocationID": shelf, "Name": "t shelf", "Type": "Shelf", "Max Spools": "0",
            "parent_id": room}}, timeout=10)
        r.raise_for_status()
        assert _all(api_base_url)[shelf]["parent_id"] == room
    finally:
        _cleanup(api_base_url, shelf, room)


@pytest.mark.integration
def test_reject_nonexistent_parent(api_base_url, require_server):
    bad = "ZZP5BAD"
    try:
        r = requests.post(f"{api_base_url}/api/locations", json={"old_id": "", "new_data": {
            "LocationID": bad, "Name": "t", "Type": "Shelf", "Max Spools": "0",
            "parent_id": "NOPE-NOT-REAL"}}, timeout=10)
        assert r.status_code == 400
        assert r.json().get("success") is False
        assert bad not in _all(api_base_url)  # not persisted
    finally:
        _cleanup(api_base_url, bad)


@pytest.mark.integration
def test_reject_self_parent(api_base_url, require_server):
    sid = "ZZP5SELF"
    try:
        r = requests.post(f"{api_base_url}/api/locations", json={"old_id": "", "new_data": {
            "LocationID": sid, "Name": "t", "Type": "Shelf", "Max Spools": "0",
            "parent_id": sid}}, timeout=10)
        assert r.status_code == 400
        assert sid not in _all(api_base_url)
    finally:
        _cleanup(api_base_url, sid)


@pytest.mark.integration
def test_reject_descendant_cycle(api_base_url, require_server):
    room, parent, child = "ZZP5C", "ZZP5C-CT", "ZZP5C-CT-R1"
    try:
        for lid, typ in ((room, "Room"), (parent, "Cart"), (child, "Cart")):
            requests.post(f"{api_base_url}/api/locations", json={"old_id": "", "new_data": {
                "LocationID": lid, "Name": f"t {lid}", "Type": typ, "Max Spools": "0"}},
                timeout=10).raise_for_status()
        got = _all(api_base_url)
        assert got[parent]["parent_id"] == room and got[child]["parent_id"] == parent
        # try to parent `parent` under its own descendant `child` → cycle → reject
        r = requests.post(f"{api_base_url}/api/locations", json={"old_id": parent, "new_data": {
            "LocationID": parent, "Name": "t", "Type": "Cart", "Max Spools": "0",
            "parent_id": child}}, timeout=10)
        assert r.status_code == 400
        assert "cycle" in str(r.json().get("error", "")).lower()
        # unchanged
        assert _all(api_base_url)[parent]["parent_id"] == room
    finally:
        _cleanup(api_base_url, child, parent, room)


@pytest.mark.integration
def test_explicit_top_level_null(api_base_url, require_server):
    room, shelf = "ZZP5T", "ZZP5T-S1"
    try:
        requests.post(f"{api_base_url}/api/locations", json={"old_id": "", "new_data": {
            "LocationID": room, "Name": "t room", "Type": "Room", "Max Spools": "0"}}, timeout=10).raise_for_status()
        # explicit null = top-level even though the ID prefix would derive ZZP5T
        r = requests.post(f"{api_base_url}/api/locations", json={"old_id": "", "new_data": {
            "LocationID": shelf, "Name": "t", "Type": "Shelf", "Max Spools": "0",
            "parent_id": None}}, timeout=10)
        r.raise_for_status()
        assert _all(api_base_url)[shelf]["parent_id"] is None
    finally:
        _cleanup(api_base_url, shelf, room)


@pytest.mark.integration
def test_explicit_parent_id_is_canonicalized(api_base_url, require_server):
    """review #6: a non-canonical (lowercase) parent_id passes validation but is
    stored upper-cased."""
    room, shelf = "ZZP5CAN", "ZZP5CAN-S1"
    try:
        requests.post(f"{api_base_url}/api/locations", json={"old_id": "", "new_data": {
            "LocationID": room, "Name": "t room", "Type": "Room", "Max Spools": "0"}}, timeout=10).raise_for_status()
        r = requests.post(f"{api_base_url}/api/locations", json={"old_id": "", "new_data": {
            "LocationID": shelf, "Name": "t", "Type": "Shelf", "Max Spools": "0",
            "parent_id": room.lower()}}, timeout=10)
        r.raise_for_status()
        assert _all(api_base_url)[shelf]["parent_id"] == room  # stored upper-cased
    finally:
        _cleanup(api_base_url, shelf, room)


@pytest.mark.integration
def test_reject_duplicate_locationid(api_base_url, require_server):
    """review #7: creating/renaming onto an existing LocationID is rejected (no
    duplicate row on disk)."""
    a = "ZZP5DUP"
    try:
        requests.post(f"{api_base_url}/api/locations", json={"old_id": "", "new_data": {
            "LocationID": a, "Name": "first", "Type": "Shelf", "Max Spools": "0"}}, timeout=10).raise_for_status()
        r = requests.post(f"{api_base_url}/api/locations", json={"old_id": "", "new_data": {
            "LocationID": a, "Name": "dup", "Type": "Shelf", "Max Spools": "0"}}, timeout=10)
        assert r.status_code == 400
        rows = requests.get(f"{api_base_url}/api/locations", timeout=10).json()
        assert sum(1 for x in rows if str(x.get("LocationID")) == a) == 1
    finally:
        _cleanup(api_base_url, a)


# ---------------------------------------------------------------------------
# (a)+(b)+(c) source canaries — guard the wiring without a server
# ---------------------------------------------------------------------------

def test_migration_wired_at_startup():
    app = _read("app.py")
    assert "migrate_shelf_grouping_rows_if_needed" in app, "Phase 5 migration must run at startup"
    assert "pre-wall-row-synthesis-migration" in app, "must take a timestamped backup"


def test_parent_validation_present_in_save():
    app = _read("app.py")
    assert "A location can't be its own parent" in app
    assert "is not an existing location" in app
    assert "is_descendant(" in app, "must reject descendant-cycle parents"


def test_type_dropdown_has_new_options():
    html = _read("templates", "components", "modals_loc_mgr.html")
    for v in ('value="Printer"', 'value="No MMU Direct Load"', 'value="Wall"', 'value="Row"'):
        assert v in html, f"edit-type dropdown missing {v}"


def test_parent_selector_markup_present():
    html = _read("templates", "components", "modals_loc_mgr.html")
    assert 'id="edit-parent"' in html and 'id="edit-parent-breadcrumb"' in html


def test_savelocation_sends_parent_contract():
    js = _read("static", "js", "modules", "inv_loc_mgr.js")
    assert "_populateParentSelect" in js and "_LOC_PARENT_NONE" in js
    assert "new_data.parent_id = null" in js, "Top level must send explicit null"
    # openAddModal must reset the Type select (the old non-reset bug)
    assert "document.getElementById('edit-type').value = \"Storage\"" in js


def test_wall_row_badges_and_wizard_exclusion():
    core = _read("static", "js", "modules", "inv_core.js")
    assert "t === 'Wall'" in core and "t === 'Row'" in core, "Wall/Row need distinct badges"
    wiz = _read("static", "js", "modules", "inv_wizard.js")
    assert "type === 'wall' || type === 'row'" in wiz, "grouping nodes excluded from wizard picker"


def test_grouping_excluded_from_all_spool_pickers():
    """review #8: Wall/Row are excluded from EVERY spool-assignment surface, not
    just the wizard (force-location picker + scan-assign)."""
    det = _read("static", "js", "modules", "inv_details.js")
    cmd = _read("static", "js", "modules", "inv_cmd.js")
    assert "type === 'wall' || type === 'row'" in det, "force-location picker must exclude grouping nodes"
    assert "locType === 'wall' || locType === 'row'" in cmd, "scan-assign must reject grouping nodes"
