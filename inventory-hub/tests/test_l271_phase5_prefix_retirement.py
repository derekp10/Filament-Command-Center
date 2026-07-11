"""Group-34 / L271 Phase-5 prefix-retirement — Phase 0 spine pins.

Phase 0 is deliberately behavior-preserving except for ONE net-new guard:

  1. `derive_parent_id_from_prefix` was renamed to `location_prefix()` and the
     old name is now RETIRED (Phase-5). The first-segment behavior — incl. the
     load-bearing None-on-no-dash contract the /api/locations synthesizer stamp
     depends on — is preserved byte-for-byte; the retirement + no-inline-prefix
     grep-gate are pinned by test_prefix_derivation_is_retired.
  2. `save_locations_list` now REFUSES to persist a NEWLY-INTRODUCED orphan
     (a row given an explicit parent_id pointing at no real row / pseudo-room /
     the row's own first segment). Diffed against the prior on-disk file so
     pre-existing orphans + every boot-migration mid-state are grandfathered —
     the "own first segment is always OK" clause is the migration-safety
     keystone (Phase-1A's `XL-1 → XL` must persist before the XL row exists).
  3. The frontend `window.buildLocationTree` helper was extracted and the LM
     render + the two loc_mgr tree helpers re-wired onto it (source canary).

Pure-function + source-canary tests only — no live server needed.
"""
import json
import os
import types

import pytest

import locations_db as L
import spoolman_api
import config_loader

_HUB = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*parts):
    path = os.path.join(_HUB, *parts)
    assert os.path.exists(path), f"missing: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# 1. location_prefix() rename + preserved behavior + back-compat alias
# ---------------------------------------------------------------------------

def test_location_prefix_basic():
    assert L.location_prefix("LR-MDB-1") == "LR"
    assert L.location_prefix("CORE1-M0") == "CORE1"
    assert L.location_prefix("PM-DB-XL-L") == "PM"


def test_location_prefix_uppercases_and_strips():
    assert L.location_prefix("lr-mdb-1") == "LR"
    assert L.location_prefix("core1-m0") == "CORE1"
    assert L.location_prefix("  LR-X  ") == "LR"


def test_location_prefix_returns_none_on_no_dash():
    """Correction #6 — MUST return None for a dash-free id. The /api/locations
    synthesizer stamps parent_id from this directly (unmasked by an equality
    check), so a dash-free Spoolman-native location must NOT self-parent."""
    assert L.location_prefix("LR") is None
    assert L.location_prefix("CORE1") is None
    assert L.location_prefix("") is None


def test_location_prefix_non_string_is_none():
    assert L.location_prefix(None) is None
    assert L.location_prefix(123) is None
    assert L.location_prefix(["LR-1"]) is None


def test_prefix_derivation_is_retired():
    """Group-34 Phase-5 grep-gate: the retired name `derive_parent_id_from_prefix`
    is GONE from every backend module, and no inline BARE `split('-')[0]`
    hierarchy-prefix shortcut survives. The sanctioned first-segment helper is
    location_prefix() (which uses the two-arg `split('-', 1)[0]`); the B2 printer-
    prefix family also uses the two-arg form and is deliberately out of scope, so
    banning only the bare one-arg form never false-fails on it. Scans every *.py
    at the inventory-hub root non-recursively (tests/ excluded), mirroring
    test_no_direct_extra_patch."""
    import glob
    offenders_name, offenders_split = [], []
    for path in glob.glob(os.path.join(_HUB, "*.py")):
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        base = os.path.basename(path)
        if "derive_parent_id_from_prefix" in src:
            offenders_name.append(base)
        if "split('-')[0]" in src or 'split("-")[0]' in src:
            offenders_split.append(base)
    assert not offenders_name, (
        f"the retired name derive_parent_id_from_prefix still appears in: "
        f"{offenders_name} — every caller must read location_prefix()"
    )
    assert not offenders_split, (
        f"an inline bare split('-')[0] hierarchy-prefix shortcut appears in: "
        f"{offenders_split} — derive a first segment via location_prefix() instead"
    )


def test_location_prefix_wired_at_load_bearing_sites():
    """The 4 flat spool-matchers + the synthesizer stamp read location_prefix()
    (not the retired name) — a source canary so a future edit can't silently
    reintroduce the old hierarchy-conflating name at a safety-critical matcher."""
    sm = _read("spoolman_api.py")
    assert sm.count("locations_db.location_prefix(") >= 4, (
        "the 4 flat location-string matchers must read location_prefix()"
    )
    assert "locations_db.derive_parent_id_from_prefix(" not in sm, (
        "no matcher may still call the retired name"
    )
    routes = _read("routes_locations.py")
    assert "locations_db.location_prefix(loc_name)" in routes, (
        "the /api/locations synthesizer stamp must read location_prefix()"
    )


# ---------------------------------------------------------------------------
# 2. _find_new_orphans — the write-time guard's core predicate
# ---------------------------------------------------------------------------

def test_orphan_new_row_with_bogus_parent_is_flagged():
    prior = [{"LocationID": "CR", "parent_id": None}]
    new = [
        {"LocationID": "CR", "parent_id": None},
        {"LocationID": "SHELF-A-3", "parent_id": "WAREHOUSE-9"},
    ]
    orphans = L._find_new_orphans(new, prior)
    assert [lid for lid, _ in orphans] == ["SHELF-A-3"]


def test_orphan_own_first_segment_is_permitted_even_without_the_prefix_row():
    """Migration-safety keystone: Phase-1A stamps XL-1 → parent 'XL' before the
    XL row exists. That own-first-segment orphan must NOT be flagged."""
    new = [{"LocationID": "XL-1", "Type": "Tool Head", "parent_id": "XL"}]
    assert L._find_new_orphans(new, []) == []


def test_orphan_pseudo_room_prefix_is_permitted():
    new = [{"LocationID": "PM-DB-9", "Type": "Dryer Box", "parent_id": "PM"}]
    assert L._find_new_orphans(new, []) == []


def test_orphan_real_row_parent_is_permitted():
    new = [
        {"LocationID": "CR", "parent_id": None},
        {"LocationID": "CR-CT", "parent_id": "CR"},
    ]
    assert L._find_new_orphans(new, []) == []


def test_orphan_explicit_none_parent_is_permitted():
    new = [{"LocationID": "ROOM", "parent_id": None}]
    assert L._find_new_orphans(new, []) == []


def test_orphan_auto_derive_path_no_parent_key_is_permitted():
    """A row with NO parent_id key is the Auto-derive path — always safe."""
    new = [{"LocationID": "FOO-BAR", "Type": "Shelf"}]
    assert L._find_new_orphans(new, []) == []


def test_orphan_preexisting_orphan_is_grandfathered():
    """An orphan already on disk with that exact parent isn't newly introduced."""
    prior = [{"LocationID": "CT-9", "parent_id": "GHOST"}]
    new = [{"LocationID": "CT-9", "parent_id": "GHOST"}]
    assert L._find_new_orphans(new, prior) == []


def test_orphan_changing_a_parent_to_a_bogus_value_is_flagged():
    prior = [{"LocationID": "CT-9", "parent_id": None}]
    new = [{"LocationID": "CT-9", "parent_id": "GHOST"}]
    orphans = L._find_new_orphans(new, prior)
    assert [lid for lid, _ in orphans] == ["CT-9"]


def test_orphan_check_is_case_insensitive_on_parent():
    """A lowercase real-row reference is still recognized as real (canonicalized
    upper) and must not be flagged."""
    new = [
        {"LocationID": "CR", "parent_id": None},
        {"LocationID": "CR-CT", "parent_id": "cr"},
    ]
    assert L._find_new_orphans(new, []) == []


def test_orphan_whitespace_parent_is_treated_as_top_level():
    """A hand-edited whitespace-only parent_id must canonicalize to None (top
    level) via the SAME helper the prior map uses — not to '' (which would
    false-reject an otherwise-unchanged row). Regression pin for the inline-vs-
    _canonical_parent_id divergence the Phase-0 review caught."""
    assert L._find_new_orphans([{"LocationID": "CT-9", "parent_id": "   "}], []) == []
    # And an unchanged whitespace-parent row on disk is not spuriously flagged.
    prior = [{"LocationID": "CT-9", "parent_id": "   "}]
    assert L._find_new_orphans([{"LocationID": "CT-9", "parent_id": "   "}], prior) == []


def test_orphan_non_list_input_is_safe():
    assert L._find_new_orphans("not a list", []) == []


# ---------------------------------------------------------------------------
# 3. save_locations_list write-time refusal (disk integration, temp file)
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_locations(monkeypatch, tmp_path):
    """Point locations_db at a fresh temp locations.json (mirrors the fixture in
    test_save_locations_atomicity.py so this file stays independently runnable)."""
    target = tmp_path / "locations.json"
    initial = [{"LocationID": "CR", "Name": "Computer Room", "Type": "Room", "parent_id": None}]
    target.write_text(json.dumps(initial, indent=4), encoding="utf-8")
    monkeypatch.setattr(L, "JSON_FILE", str(target))
    monkeypatch.setattr(L, "_DATA_DIR", str(tmp_path))
    return target, initial


def test_save_refuses_new_orphan_and_leaves_file_unchanged(temp_locations):
    target, initial = temp_locations
    bad = [
        {"LocationID": "CR", "Name": "Computer Room", "Type": "Room", "parent_id": None},
        {"LocationID": "CR-CT-Z", "Type": "Cart", "parent_id": "NOPE-NOT-REAL"},
    ]
    assert L.save_locations_list(bad) is False
    # File must be untouched — the refusal happens BEFORE the atomic write.
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk == initial


def test_save_accepts_valid_new_child(temp_locations):
    target, _ = temp_locations
    good = [
        {"LocationID": "CR", "Name": "Computer Room", "Type": "Room", "parent_id": None},
        {"LocationID": "CR-CT", "Type": "Cart", "parent_id": "CR"},
    ]
    assert L.save_locations_list(good) is True
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert {r["LocationID"] for r in on_disk} == {"CR", "CR-CT"}


def test_save_accepts_own_prefix_backfill_before_the_prefix_row_exists(temp_locations):
    """The migration-safety keystone at the STORE boundary: a backfill that
    parents XL-1 under 'XL' before an XL row exists must still persist (else the
    boot-migration convergence chain silently bricks)."""
    target, _ = temp_locations
    migrating = [
        {"LocationID": "CR", "Name": "Computer Room", "Type": "Room", "parent_id": None},
        {"LocationID": "XL-1", "Type": "Tool Head", "parent_id": "XL"},
    ]
    assert L.save_locations_list(migrating) is True
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert {r["LocationID"] for r in on_disk} == {"CR", "XL-1"}


def test_save_rows_without_parent_key_are_unaffected(temp_locations):
    """The existing atomicity tests write parent_id-less rows; the new guard
    must never touch that path."""
    target, _ = temp_locations
    payload = [{"LocationID": "TEST-A", "Type": "Buffer"}]
    assert L.save_locations_list(payload) is True
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_save_is_fail_open_when_validation_raises(temp_locations, monkeypatch):
    """The orphan guard is documented FAIL-OPEN: a bug inside the validation
    must NEVER block a legitimate save (only a positively-detected new orphan
    returns False). A regression that let the exception propagate, or flipped
    to fail-CLOSED, would silently brick every save incl. boot-migration
    mid-states — so pin the fail-open path explicitly."""
    target, _ = temp_locations

    def _boom(*a, **k):
        raise RuntimeError("validation bug")

    monkeypatch.setattr(L, "_find_new_orphans", _boom)
    good = [{"LocationID": "CR", "Name": "Computer Room", "Type": "Room", "parent_id": None}]
    assert L.save_locations_list(good) is True  # did not block
    assert json.loads(target.read_text(encoding="utf-8")) == good  # and wrote


# ---------------------------------------------------------------------------
# 4. buildLocationTree extraction — frontend source canaries
# ---------------------------------------------------------------------------

def test_build_location_tree_defined_and_consumed_in_core():
    core = _read("static", "js", "modules", "inv_core.js")
    assert "window.buildLocationTree = function buildLocationTree(" in core, (
        "the shared tree helper must be defined on window in inv_core.js"
    )
    assert "window.buildLocationTree(bodyRows" in core, (
        "the LM render must consume the shared helper (with the pin shouldFloat)"
    )
    assert "shouldFloat" in core, "the render must pass the pin-float predicate"


def test_build_location_tree_consumed_by_loc_mgr_helpers():
    mgr = _read("static", "js", "modules", "inv_loc_mgr.js")
    assert mgr.count("window.buildLocationTree(state.allLocations") >= 2, (
        "_locDescendants and _locBreadcrumbChain must both read the shared helper"
    )


# ---------------------------------------------------------------------------
# 5. Safety-critical matcher FLATNESS — must not become a transitive tree walk
# ---------------------------------------------------------------------------
# The 4 spoolman_api flat matchers are a locked contract (2026-06-04 review): a
# room-level query reaches its cart-ROWS (first segment == room) but NOT a
# nested printer's toolhead (first segment == printer). Phase 0 re-pointed them
# onto location_prefix() but MUST keep them flat. The A/B pins in
# test_l271_phase2_consumers.py use an EMPTY parent_map, so a regression that
# built a tree internally slips past them; these pins seed a genuinely NESTED
# tree and assert the room query stays flat regardless.

_NESTED_TREE = [
    {"LocationID": "LR", "Type": "Room", "parent_id": None},
    {"LocationID": "XL", "Type": "Printer", "parent_id": "LR"},      # printer nested UNDER the room
    {"LocationID": "XL-1", "Type": "Tool Head", "parent_id": "XL"},  # toolhead under the printer
    {"LocationID": "LR-CT-1", "Type": "Cart", "parent_id": "LR"},    # cart-row directly under the room
]


def test_build_location_match_stays_flat():
    """_build_location_match matches by FLAT first segment only: a room-LR query
    must NOT reach a spool at toolhead XL-1 (the actively-printing toolhead the
    contract protects) even though XL nests under LR — while a cart-row LR-CT-1
    IS reached, and the printer's own XL query DOES reach its toolhead."""
    at_toolhead = {"id": 1, "location": "XL-1", "extra": {}}
    at_cartrow = {"id": 2, "location": "LR-CT-1", "extra": {}}
    assert spoolman_api._build_location_match(dict(at_cartrow), "LR") is not None
    assert spoolman_api._build_location_match(dict(at_toolhead), "LR") is None
    assert spoolman_api._build_location_match(dict(at_toolhead), "XL") is not None


def test_get_spools_at_location_strict_stays_flat_under_a_nested_tree(monkeypatch):
    """End-to-end: a fail-closed room query over a NESTED tree must EXCLUDE the
    nested printer's toolhead spool and include the room's own cart-row/box.
    The tree is seeded so a regression that swaps the flat matcher for a
    transitive is_descendant walk WOULD wrongly sweep XL-1 — and fail here."""
    spools = [
        {"id": 1, "location": "XL-1", "extra": {}},      # nested toolhead — must be EXCLUDED for room LR
        {"id": 2, "location": "LR-CT-1", "extra": {}},   # room's cart-row — INCLUDED
        {"id": 3, "location": "LR-DB1", "extra": {}},    # box directly in room — INCLUDED
    ]

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return spools

    monkeypatch.setattr(spoolman_api, "requests",
                        types.SimpleNamespace(get=lambda url, timeout=5: _Resp()))
    monkeypatch.setattr(config_loader, "get_api_urls", lambda: ("http://sm", "http://fb"))
    monkeypatch.setattr(L, "load_locations_list", lambda: list(_NESTED_TREE))

    got = set(spoolman_api.get_spools_at_location_strict("LR"))
    assert 1 not in got, "room LR must NOT reach a nested printer's toolhead spool (flat-match contract)"
    assert got == {2, 3}


def test_matchers_never_call_is_descendant_or_build_parent_map():
    """Source tripwire: a regression adding `or locations_db.is_descendant(...)`
    alongside the flat clause keeps the location_prefix() count >= 4 (so the
    wiring canary passes) but silently broadens the destructive blast radius.
    Assert the transitive-walk primitives are ABSENT from the flat-matcher
    module entirely."""
    sm = _read("spoolman_api.py")
    assert "is_descendant(" not in sm, (
        "the flat matchers must never call is_descendant — that would turn a "
        "room-level clear into a transitive subtree sweep (2026-06-04 contract)"
    )
    assert "build_parent_map(" not in sm, (
        "the flat matchers must not build a parent_map — flatness must not consult the tree"
    )
