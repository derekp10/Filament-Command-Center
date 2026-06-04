"""L271 Phase 3.5 — hierarchy-walk helper unit tests.

Phase 3.5 flips `parent_id` from the flat first-segment to each row's
IMMEDIATE parent, so the room/child resolvers can no longer assume a single
hop reaches the room. These tests pin `resolve_room` / `is_descendant` /
`build_parent_map` against BOTH the pre-3.5 flat tree (where they must reduce
to the old single-hop behavior — the A/B identity that lets the consumer
migrations land before the data flip) AND the post-3.5 nested tree (where they
must walk the full chain).

Pure-function pins — no running server, no disk (every case passes an explicit
fixture tree / parent_map).
"""
import pytest

import locations_db as L


# --- representative trees -------------------------------------------------

def _row(lid, parent):
    return {"LocationID": lid, "parent_id": parent, "Type": "x"}


# Pre-3.5: parent_id is the flat first-segment; printers are top-level roots.
FLAT_TREE = [
    _row("CR", None), _row("LR", None),
    _row("CR-CT-1", "CR"), _row("CR-CT-1-R1", "CR"), _row("CR-CT-1-R2", "CR"),
    _row("LR-MDB-1", "LR"),
    _row("XL", None), _row("XL-1", "XL"), _row("XL-2", "XL"),
    _row("CORE1", None),
    _row("PM-DB-1", "PM"),  # PM has no on-disk row (virtual room)
]

# Post-3.5: parent_id is the immediate parent; printers nest under their room.
NESTED_TREE = [
    _row("CR", None), _row("LR", None),
    _row("CR-CT-1", "CR"), _row("CR-CT-1-R1", "CR-CT-1"), _row("CR-CT-1-R2", "CR-CT-1"),
    _row("LR-MDB-1", "LR"),
    _row("XL", "LR"), _row("XL-1", "XL"), _row("XL-2", "XL"),
    _row("CORE1", "CR"),
    _row("PM-DB-1", "PM"),
]


# --- build_parent_map -----------------------------------------------------

def test_build_parent_map_shape():
    pmap = L.build_parent_map(FLAT_TREE)
    assert pmap["CR-CT-1-R1"] == "CR"
    assert pmap["XL"] is None
    assert pmap["XL-1"] == "XL"
    # every row present, upper-cased keys
    assert set(pmap) == {r["LocationID"].upper() for r in FLAT_TREE}


def test_build_parent_map_skips_blank_and_nondict():
    pmap = L.build_parent_map([{"LocationID": "  "}, "junk", {"LocationID": "A", "parent_id": None}])
    assert pmap == {"A": None}


# --- is_descendant: A/B identity on the flat tree -------------------------

@pytest.mark.parametrize("child,anc,expected", [
    ("CR-CT-1-R1", "CR", True),    # flat: direct child of room
    ("CR-CT-1", "CR", True),
    ("XL-1", "XL", True),
    ("XL-1", "LR", False),         # flat: printer is a top-level root, NOT under LR
    ("CR-CT-1-R1", "CR-CT-1", False),  # flat: row's only ancestor is CR, not the cart
    ("CR-CT-1", "DR", False),
])
def test_is_descendant_flat(child, anc, expected):
    pmap = L.build_parent_map(FLAT_TREE)
    assert L.is_descendant(child, anc, pmap) is expected


@pytest.mark.parametrize("child,anc,expected", [
    ("CR-CT-1-R1", "CR-CT-1", True),   # nested: cart-row IS under its cart
    ("CR-CT-1-R1", "CR", True),         # ...and transitively under the room
    ("XL-1", "XL", True),
    ("XL-1", "LR", True),               # nested: toolhead under printer under room
    ("CORE1", "CR", True),
    ("LR-MDB-1", "CR", False),
])
def test_is_descendant_nested(child, anc, expected):
    pmap = L.build_parent_map(NESTED_TREE)
    assert L.is_descendant(child, anc, pmap) is expected


def test_is_descendant_strict_self_is_false():
    pmap = L.build_parent_map(NESTED_TREE)
    assert L.is_descendant("CR", "CR", pmap) is False
    assert L.is_descendant("XL-1", "XL-1", pmap) is False


def test_is_descendant_empty_args():
    pmap = L.build_parent_map(NESTED_TREE)
    assert L.is_descendant("", "CR", pmap) is False
    assert L.is_descendant("CR", "", pmap) is False


def test_is_descendant_prefix_fallback_for_unknown_id():
    # A spool sitting at a LocationID with no row still resolves via prefix.
    pmap = L.build_parent_map(NESTED_TREE)
    assert L.is_descendant("CR-CT-9-R9", "CR", pmap) is True   # CR-CT-9-R9 -> ... -> CR
    assert L.is_descendant("GAR-SHELF-1", "CR", pmap) is False


def test_is_descendant_cycle_guard():
    cyclic = [_row("A", "B"), _row("B", "A")]
    pmap = L.build_parent_map(cyclic)
    # must terminate, not hang or raise
    assert L.is_descendant("A", "Z", pmap) is False


# --- resolve_room: A/B identity on the flat tree --------------------------

@pytest.mark.parametrize("loc,expected", [
    ("CR-CT-1-R1", "CR"),   # flat: one hop already at room
    ("LR-MDB-1", "LR"),
    ("XL-1", "XL"),          # flat: printer is the top-level root
    ("PM-DB-1", "PM"),       # pseudo-prefix kept (caller excludes it)
])
def test_resolve_room_flat(loc, expected):
    pmap = L.build_parent_map(FLAT_TREE)
    assert L.resolve_room(loc, pmap) == expected


@pytest.mark.parametrize("loc,expected", [
    ("CR-CT-1-R1", "CR"),   # nested: walk CR-CT-1-R1 -> CR-CT-1 -> CR
    ("CR-CT-1", "CR"),
    ("XL-1", "LR"),          # nested: toolhead -> printer -> room
    ("XL", "LR"),
    ("CORE1", "CR"),
    ("LR-MDB-1", "LR"),
])
def test_resolve_room_nested(loc, expected):
    pmap = L.build_parent_map(NESTED_TREE)
    assert L.resolve_room(loc, pmap) == expected


def test_resolve_room_top_level_returns_self():
    pmap = L.build_parent_map(NESTED_TREE)
    assert L.resolve_room("CR", pmap) == "CR"


def test_resolve_room_empty():
    assert L.resolve_room("", {}) == ""
    assert L.resolve_room(None, {}) == ""


def test_resolve_room_accepts_row_dict():
    pmap = L.build_parent_map(NESTED_TREE)
    assert L.resolve_room({"LocationID": "XL-1"}, pmap) == "LR"


def test_resolve_room_cycle_guard():
    cyclic = [_row("A", "B"), _row("B", "A")]
    pmap = L.build_parent_map(cyclic)
    # terminates; returns one of the cycle members, never hangs
    assert L.resolve_room("A", pmap) in ("A", "B")


# --- logic.get_room_from_location through the nested chain -----------------
# The eject room-deriver consumer: on the nested tree it must walk to the
# top-level room, NOT stop at the immediate parent. Pinned against an explicit
# nested fixture so it's independent of live data.

import logic  # noqa: E402


@pytest.mark.parametrize("loc,expected", [
    ("CR-CT-1-R1", "CR"),   # cart-row -> cart -> room
    ("CR-CT-1", "CR"),
    ("XL-1", "LR"),          # toolhead -> printer -> room (the Phase 3.5 change)
    ("LR-MDB-1", "LR"),
    ("XL", ""),              # dash-free root -> no room above (guard)
    ("CORE1", ""),
    ("PM-DB-1", ""),         # pseudo-prefix excluded
    ("", ""),
])
def test_get_room_from_location_nested(monkeypatch, loc, expected):
    monkeypatch.setattr(L, "load_locations_list", lambda: list(NESTED_TREE))
    assert logic.get_room_from_location(loc) == expected
