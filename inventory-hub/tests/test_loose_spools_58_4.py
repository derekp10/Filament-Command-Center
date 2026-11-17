"""Group 58.4, the server half: which places are loose, and GET /api/loose_spools.

Derek's once-over: one list of the spools filed at a cart or room itself. The rule
is "has child rows", not Type Cart (a cart's rows are Type Cart too: on dev 54
spools, not 130). A spool counts by its own `location`, exactly. The answer never
reads as empty when Spoolman didn't answer (Group 52's rule).

Hermetic. The route runs on the real read_spool_list and parse_inbound_data over a
stand-in `requests.get`, the wire records in Spoolman's own shape (extras as JSON
text). Every other requests verb raises, which is what pins "read-only".
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import app as app_module
import locations_db
import spoolman_api

ROWS = [
    {"LocationID": "LR", "Name": "Living Room", "Type": "Room", "parent_id": None},
    {"LocationID": "ZONE", "Name": "A Zone", "Type": "Virtual Room", "parent_id": None},
    {"LocationID": "GARAGE", "Name": "Garage", "Type": "", "parent_id": None},
    {"LocationID": "CR", "Name": "Craft Room", "Type": "Room", "parent_id": None},
    {"LocationID": "CR-CT-1", "Name": "Big Cart", "Type": "Cart", "parent_id": "CR"},
    {"LocationID": "CR-CT-1-R1", "Name": "Big Cart Row 1", "Type": "Cart", "parent_id": "CR-CT-1"},
    {"LocationID": "CR-CT-2", "Name": "Flat Cart", "Type": "Cart", "parent_id": "CR"},
    {"LocationID": "LR-DB-1", "Name": "Dry Box", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR"},
    {"LocationID": "LR-DB-1-A", "Name": "Odd child of a box", "Type": "Cart", "parent_id": "LR-DB-1"},
    {"LocationID": "XL", "Name": "Big Printer", "Type": "Printer", "parent_id": "LR",
     "toolheads": [{"location_id": "XL-1", "position": 0}, {"location_id": "XL-2", "position": 1}]},
    {"LocationID": "XL-1", "Name": "Head 1", "Type": "Tool Head", "parent_id": "XL"},
    {"LocationID": "XL-2", "Name": "Head 2", "Type": "Tool Head", "parent_id": "XL"},
    {"LocationID": "XL-2-X", "Name": "Odd child of a head", "Type": "Cart", "parent_id": "XL-2"},
    {"LocationID": "ONE", "Name": "One Head Printer", "Type": "Printer", "parent_id": None,
     "toolheads": [{"location_id": "ONE", "position": 0}]},
    {"LocationID": "ONE-X", "Name": "Odd child of a head printer", "Type": "Cart", "parent_id": "ONE"},
    {"LocationID": "PJ", "Name": "Projects", "Type": "Cart", "parent_id": None},
    {"LocationID": "PJ-CT-1", "Name": "Project Cart", "Type": "Cart"},          # parent by prefix: PJ, a pseudo
]


def _loose(rows=None):
    rows = ROWS if rows is None else rows
    return locations_db.loose_place_ids(rows, locations_db.get_active_printer_map(rows))


# --- the classifier ------------------------------------------------------------


def test_the_loose_places():
    assert _loose() == {"LR", "ZONE", "GARAGE", "CR", "CR-CT-1", "XL"}


@pytest.mark.parametrize("lid,why", [
    ("LR", "a Room"),
    ("ZONE", "a Virtual Room"),
    ("GARAGE", "a dash-less row with no Type: /api/locations shows it as a room"),
    ("CR-CT-1", "a cart with rows"),
    ("XL", "a Printer row that isn't a head, with child rows"),
])
def test_loose(lid, why):
    assert lid in _loose(), why


@pytest.mark.parametrize("lid,why", [
    ("CR-CT-1-R1", "a cart's row is Type Cart too: Type can't be the rule"),
    ("CR-CT-2", "a cart with no rows is as exact as that place gets"),
    ("LR-DB-1", "a Dryer Box, even with a child row"),
    ("XL-1", "a toolhead"),
    ("XL-2", "a toolhead, even with a child row"),
    ("ONE", "a Printer row that is its own head, even with a child row"),
    ("PJ", "a pseudo-prefix parent doesn't count as having children"),
    ("PJ-CT-1", "a cart with no rows"),
])
def test_not_loose(lid, why):
    assert lid not in _loose(), why


@pytest.mark.parametrize("rtype", ["Tool Head", "MMU Slot", "No MMU Direct Load"])
def test_a_toolhead_type_is_never_loose_even_with_no_printer_listing_it(rtype):
    """Its Type says so on its own: a head no Printer row's toolheads[] lists is in
    no printer_map, and child rows don't make it a place to file spools at."""
    rows = [{"LocationID": "HEAD-1", "Type": rtype}, {"LocationID": "HEAD-1-X", "Type": "Cart", "parent_id": "HEAD-1"}]
    assert locations_db.get_active_printer_map(rows) == {}
    assert _loose(rows) == set()


def test_a_dashed_row_with_no_type_is_not_a_room():
    rows = [{"LocationID": "CR-X", "Type": "", "parent_id": "CR"}, {"LocationID": "CR", "Type": "Room"}]
    assert _loose(rows) == {"CR"}


@pytest.mark.parametrize("rtype", ["room", "ROOM", " Room ", "virtual room"])
def test_a_room_in_any_spelling(rtype):
    assert _loose([{"LocationID": "LR", "Type": rtype}]) == {"LR"}


def test_malformed_rows_are_skipped():
    assert _loose(["not a row", None, {"Type": "Room"}, {"LocationID": "  ", "Type": "Room"},
                   {"LocationID": "LR", "Type": "Room"}]) == {"LR"}
    assert locations_db.loose_place_ids([], {}) == set()
    assert locations_db.loose_place_ids(None, None) == set()


def test_ids_are_compared_upper_cased():
    rows = [{"LocationID": "lr", "Type": "Room"},
            {"LocationID": "One", "Type": "Printer", "toolheads": [{"location_id": "one", "position": 0}]},
            {"LocationID": "One-x", "Type": "Cart", "parent_id": "One"}]
    assert _loose(rows) == {"LR"}


# --- one count of child rows ----------------------------------------------------


def test_child_row_counts_leaves_out_the_pseudo_prefixes():
    assert locations_db.child_row_counts({"A-1": "A", "A-2": "A", "B": None, "PM-1": "PM", "PJ-1": "PJ",
                                          "TST-1": "TST", "TEST-1": "TEST"}) == {"A": 2}


def _occupancy(rows):
    """/api/locations' own answer for `rows`, with no spool anywhere."""
    with patch.object(locations_db, "load_locations_list", return_value=[dict(r) for r in rows]), \
            patch.object(spoolman_api, "get_all_locations", return_value=[]), \
            patch.object(spoolman_api, "read_spool_list", return_value=([], None)):
        with app_module.app.test_request_context("/api/locations"):
            return {r["LocationID"]: r["Occupancy"] for r in app_module.api_get_locations().get_json()}


def test_the_list_and_api_locations_agree_on_who_has_child_rows():
    """Every row /api/locations calls a parent ("N Total") is loose, unless it is a
    head or a box, and no other row with a Type is. One count, shared."""
    shown = _occupancy(ROWS)
    parents = {lid.upper() for lid, occ in shown.items() if "Total" in occ}
    assert parents == {"LR", "CR", "CR-CT-1", "LR-DB-1", "XL", "XL-2", "ONE", "ZONE"}, shown
    assert _loose() - {"GARAGE"} == parents - {"LR-DB-1", "XL-2", "ONE"}


def test_both_readers_use_the_one_count():
    with patch.object(locations_db, "child_row_counts", wraps=locations_db.child_row_counts) as spy:
        _loose()
        assert spy.call_count == 1
        _occupancy(ROWS)
        assert spy.call_count == 2


# --- GET /api/loose_spools ------------------------------------------------------


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self.ok = status < 400
        self._body = body

    def json(self):
        return json.loads(json.dumps(self._body))


def _wire(sid, location, archived=False, remaining=500.0, extra=None, **fil):
    """A spool as Spoolman sends it: extras as JSON text, a missing key left out."""
    return {
        "id": sid, "location": location, "archived": archived, "remaining_weight": remaining,
        "extra": extra or {}, "used_weight": 100.0, "registered": "2026-02-11T04:07:24Z",
        "filament": {"id": sid + 1000, "name": fil.get("name", "Red"), "material": "PLA",
                     "color_hex": fil.get("color", "72071C"), "extra": {},
                     "vendor": {"id": 2, "name": "Some Brand", "extra": {}}},
    }


def _no_write(*a, **k):
    raise AssertionError(f"the loose list wrote: {a!r}")


class _Spoolman:
    def __init__(self, records=None, status=200, raises=None):
        self.records = records
        self.status = status
        self.raises = raises
        self.gets = []

    def get(self, url, timeout=None, **kw):
        self.gets.append(str(url))
        if self.raises:
            raise self.raises
        return _Resp(self.status, self.records if self.status < 400 else {"message": "unavailable (test)"})


def _ask(spoolman, rows=None):
    with patch.object(locations_db, "load_locations_list", return_value=list(ROWS if rows is None else rows)), \
            patch.object(spoolman_api.requests, "get", side_effect=spoolman.get), \
            patch.object(spoolman_api.requests, "post", side_effect=_no_write), \
            patch.object(spoolman_api.requests, "patch", side_effect=_no_write), \
            patch.object(spoolman_api.requests, "put", side_effect=_no_write), \
            patch.object(spoolman_api.requests, "delete", side_effect=_no_write):
        res = app_module.app.test_client().get("/api/loose_spools")
    return res


def _places(body):
    return {p["id"]: [s["id"] for s in p["spools"]] for p in body["places"]}


def test_a_spool_counts_only_by_its_own_exact_location():
    res = _ask(_Spoolman([
        _wire(1, "LR"),
        _wire(2, "CR-CT-1"),
        _wire(3, "CR-CT-1-R1"),                # a row: an exact place
        _wire(4, "CR-CT-2"),                   # a cart with no rows
        _wire(5, "LR-DB-1", extra={"container_slot": '"2"'}),
        _wire(6, "XL-1", extra={"physical_source": '"CR-CT-1"', "physical_source_slot": '"1"'}),   # runs on a head
        _wire(7, "XL-1", extra={"physical_source": '"LR"'}),                  # a trail never counts
    ]))
    assert res.status_code == 200
    body = res.get_json()
    assert body["read_ok"] is True and body["read_error"] is None
    assert _places(body) == {"LR": [1], "CR-CT-1": [2]}
    assert body["count"] == 2


def test_a_rooms_rows_do_not_count_as_the_room():
    """The matcher's prefix hit would list CR-CT-1-R1's spool under CR. Exact only."""
    body = _ask(_Spoolman([_wire(1, "CR-CT-1-R1"), _wire(2, "CR-CT-2"), _wire(3, "CR")])).get_json()
    assert _places(body) == {"CR": [3]}


def test_unassigned_unknown_and_archived_stay_out():
    body = _ask(_Spoolman([
        _wire(1, ""), _wire(2, None), _wire(3, "Unassigned"), _wire(4, "UNKNOWN"),
        _wire(5, "LR", archived=True), _wire(6, "LR"),
    ])).get_json()
    assert _places(body) == {"LR": [6]} and body["count"] == 1


def test_a_stray_unknown_row_on_disk_does_not_list_the_bucket():
    """The virtual bucket stays out even with a hand-made, typeless row of that name,
    which the classifier alone would call loose."""
    rows = ROWS + [{"LocationID": "UNKNOWN", "Type": ""}]
    assert _places(_ask(_Spoolman([_wire(1, "UNKNOWN")]), rows=rows).get_json()) == {}


def test_a_location_with_no_row_is_included():
    """FCC can't say what that is, so it is shown, as Spoolman spells it."""
    body = _ask(_Spoolman([_wire(1, "Old Shelf"), _wire(2, "OLD SHELF")])).get_json()
    assert body["places"] == [{
        "id": "Old Shelf", "name": "Old Shelf", "type": "",
        "spools": body["places"][0]["spools"],
    }]
    assert [s["id"] for s in body["places"][0]["spools"]] == [1, 2]


def test_a_head_with_no_row_of_its_own_is_no_loose_place():
    """Settings can give a printer a head with no location row, and FCC still loads
    spools on it. A loaded spool is as exact as a spool gets: it isn't "not in
    Locations", however its row is missing."""
    rows = ROWS + [{"LocationID": "CORE", "Name": "Core", "Type": "Printer", "parent_id": "LR",
                    "toolheads": [{"location_id": "CORE-1", "position": 0}]}]
    body = _ask(_Spoolman([_wire(1, "CORE-1"), _wire(2, "LR")]), rows=rows).get_json()
    assert _places(body) == {"LR": [2]} and body["count"] == 1


def test_a_place_reads_as_its_row_says():
    body = _ask(_Spoolman([_wire(1, "cr-ct-1")])).get_json()
    place = body["places"][0]
    assert (place["id"], place["name"], place["type"]) == ("CR-CT-1", "Big Cart", "Cart")


def test_a_row_with_no_name_reads_as_its_id():
    body = _ask(_Spoolman([_wire(1, "LR")]), rows=[{"LocationID": "LR", "Type": "Room"}]).get_json()
    assert body["places"][0]["name"] == "LR"


def test_the_spool_rows_carry_the_cards_data():
    body = _ask(_Spoolman([_wire(57, "LR", remaining=312.5, name="Gold", color="F9E352")])).get_json()
    assert body["places"][0]["spools"] == [{
        "id": 57, "display": "#57 Some Brand PLA (Gold)", "color": "F9E352",
        "color_direction": "longitudinal", "remaining_weight": 312.5}]


def test_places_and_spools_come_sorted():
    body = _ask(_Spoolman([_wire(10, "LR"), _wire(9, "LR"), _wire(100, "LR"), _wire(2, "CR"), _wire(3, "CR-CT-1")])).get_json()
    assert [p["id"] for p in body["places"]] == ["CR", "CR-CT-1", "LR"]
    assert _places(body)["LR"] == [9, 10, 100]


def test_nothing_loose_is_a_good_read():
    body = _ask(_Spoolman([_wire(1, "CR-CT-1-R1")])).get_json()
    assert body == {"read_ok": True, "read_error": None, "count": 0, "places": []}


def test_it_reads_the_list_once():
    spoolman = _Spoolman([_wire(1, "LR"), _wire(2, "CR")])
    _ask(spoolman)
    assert len(spoolman.gets) == 1 and spoolman.gets[0].endswith("/api/v1/spool")


@pytest.mark.parametrize("spoolman", [
    _Spoolman(raises=ConnectionError("no route (test)")),
    _Spoolman(status=503),
    _Spoolman(records={"not": "a list"}),
], ids=["no answer", "an error page", "not a list"])
def test_a_failed_read_is_never_an_empty_list(spoolman):
    res = _ask(spoolman)
    assert res.status_code == 200
    body = res.get_json()
    assert body["read_ok"] is False and body["places"] == [] and body["count"] == 0
    assert "couldn't read Spoolman" in body["read_error"]


def test_a_corrupt_locations_file_says_so_and_reads_nothing_else():
    err = locations_db.LocationsCorruptError("data/locations.json", json.JSONDecodeError("bad", "{", 0))
    spoolman = _Spoolman([_wire(1, "LR")])
    with patch.object(locations_db, "load_locations_list", side_effect=err), \
            patch.object(spoolman_api.requests, "get", side_effect=spoolman.get):
        res = app_module.app.test_client().get("/api/loose_spools")
    body = res.get_json()
    assert res.status_code == 200 and body["read_ok"] is False and body["places"] == []
    assert "locations.json" in body["read_error"]
    assert spoolman.gets == []


def test_the_route_is_get_only():
    client = app_module.app.test_client()
    for method in (client.post, client.put, client.patch, client.delete):
        assert method("/api/loose_spools").status_code == 405
