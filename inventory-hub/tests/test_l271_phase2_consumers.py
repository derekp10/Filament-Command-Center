"""L271 Phase 2 — backend consumer-migration regression pins.

Phase 2 of the locations schema refactor (see
`docs/agent_docs/tasks/L271-location-manager-phase-plan.md`) replaces every
backend `loc.split('-')[0]` / `startswith(parent + '-')` hierarchy probe with
`locations_db.resolve_parent(...)`. resolve_parent still falls back to prefix
parsing in this phase, so the migration is meant to be *byte-for-byte
behavior-preserving* — these tests pin the observable output of each migrated
consumer so any drift (now or when the fallback is retired in Phase 5) is loud.

The expected values were captured from the live dev container BEFORE the
migration (238-spool seeded tree: rooms CR/DR/LR, printers CORE1/XL, carts,
rows, slots, dryer boxes) and are asserted against the migrated code here.

These are pure-function pins — no running server required.
"""
import types

import pytest

import logic
import spoolman_api


# ---------------------------------------------------------------------------
# Consumer 1 — logic.get_room_from_location  (the central room deriver)
# ---------------------------------------------------------------------------
# Was: prefix = loc_id.split("-")[0]
# Now: prefix = locations_db.resolve_parent(loc_id) or ""

GET_ROOM_CASES = [
    # (input, expected_room)  — representative room -> box -> slot tree
    ("LR-DB1", "LR"),            # box in a room -> room prefix
    ("LR-MDB-1", "LR"),         # multi-drawer box -> room
    ("LR-DB-1-S2", "LR"),       # deep slot -> still the top room prefix
    ("CR-CT-1-R1", "CR"),       # cart row -> room
    ("DR-CT-1-R2-L", "DR"),     # split-side row -> room
    ("XL-1", "XL"),             # printer toolhead -> printer prefix
    ("CORE1-M0", "CORE1"),      # MMU toolhead -> printer prefix
    ("BR-CART-2", "BR"),        # generic room prefix
    ("lr-db1", "LR"),           # case-insensitive
    # Excluded non-room prefixes (no virtual room spawned):
    ("PM-DB-XL-L", ""),         # Polymaker portable box
    ("PM-DB-1", ""),
    ("PJ-1", ""),               # project cart
    ("PJ-CT-1", ""),
    ("TST-1", ""),              # system test
    ("TST-MDB-1", ""),
    ("TEST-9", ""),
    # No-dash / top-level rows have no room:
    ("CORE1", ""),
    ("XL", ""),
    ("UNASSIGNED", ""),
    # Empty / whitespace / falsy guards:
    ("", ""),
    ("   ", ""),
]


@pytest.mark.parametrize("loc_id,expected", GET_ROOM_CASES)
def test_get_room_from_location_pins_baseline(loc_id, expected):
    """resolve_parent-routed room deriver matches the pre-migration split."""
    assert logic.get_room_from_location(loc_id) == expected


def test_get_room_from_location_none_is_empty():
    """Falsy input short-circuits before any prefix logic."""
    assert logic.get_room_from_location(None) == ""


# ---------------------------------------------------------------------------
# Consumer 2 — logic.perform_smart_eject room-hierarchy bypass
# ---------------------------------------------------------------------------
# Was: saved_source.strip('"').upper().startswith(current_location + "-")
# Now: locations_db.resolve_parent(saved_source.strip('"')) == current_location
#
# Driven end-to-end through perform_smart_eject with the Spoolman / filabridge
# boundary monkeypatched, so the assertion lands on the real migrated branch
# (not a re-implementation of the predicate).

def _patch_eject_io(monkeypatch, *, location, physical_source, physical_source_slot=""):
    """Stub every external boundary perform_smart_eject touches and capture
    the resulting update_spool payload. Returns the capture dict."""
    import config_loader
    import spoolman_api as smapi

    extra = {
        "physical_source": physical_source,
        "physical_source_slot": physical_source_slot,
        "container_slot": "S1",
    }
    captured = {"update": []}

    monkeypatch.setattr(
        smapi, "get_spool",
        lambda sid: {"id": 7, "location": location, "extra": dict(extra)},
    )
    monkeypatch.setattr(config_loader, "load_config", lambda: {"printer_map": {}})
    monkeypatch.setattr(config_loader, "get_api_urls", lambda: ("http://sm", "http://fb"))
    monkeypatch.setattr(logic, "_fb_spool_location", lambda sid, url: None)
    monkeypatch.setattr(smapi, "get_spools_at_location_detailed", lambda loc: [])

    def fake_update(sid, payload):
        captured["update"].append((sid, payload))
        return True

    monkeypatch.setattr(smapi, "update_spool", fake_update)
    return captured


def test_smart_eject_bypass_fires_for_child_source(monkeypatch):
    """Floating in room LR with physical_source LR-DB1 (an immediate child):
    the bypass nulls the source so the spool ejects to Unassigned and never
    bounces back down into the child box."""
    captured = _patch_eject_io(monkeypatch, location="LR", physical_source="LR-DB1")
    result = logic.perform_smart_eject(7, confirmed_unassign=True, confirm_active_print=True)
    assert result is True
    assert len(captured["update"]) == 1
    _sid, payload = captured["update"][0]
    assert payload["location"] == ""            # Unassigned — bypass fired


def test_smart_eject_bypass_skips_non_child_source(monkeypatch):
    """Floating in room LR with physical_source CR-CT-1 (NOT a child of LR):
    the bypass must NOT fire — the spool returns home to its real source."""
    captured = _patch_eject_io(monkeypatch, location="LR", physical_source="CR-CT-1")
    result = logic.perform_smart_eject(7, confirmed_unassign=True, confirm_active_print=True)
    assert result is True
    assert len(captured["update"]) == 1
    _sid, payload = captured["update"][0]
    assert payload["location"] == "CR-CT-1"     # returned home — bypass did not fire


# ---------------------------------------------------------------------------
# Consumer 3 — spoolman_api.get_spools_at_location_strict
# ---------------------------------------------------------------------------
# Was: bare = "-" not in target; (... bare and sloc.startswith(target+"-") ...)
# Now: resolve_parent(sloc) == target or resolve_parent(p_source) == target
#
# A/B against the OLD predicate as oracle over a representative tree, with the
# Spoolman HTTP fetch stubbed. Covers direct / room-child / ghost (physical_
# source) / ghost-child / dashed-exact / prefix-near-miss matches.

_STRICT_SPOOLS = [
    {"id": 1, "location": "LR-DB1",       "extra": {}},                          # direct + child of LR
    {"id": 2, "location": "LR",           "extra": {}},                          # direct room
    {"id": 3, "location": "XL-1",         "extra": {}},                          # child of XL
    {"id": 4, "location": "CORE1-M0",     "extra": {"physical_source": "LR-DB1"}},  # ghost -> LR-DB1 / LR
    {"id": 5, "location": "",             "extra": {}},                          # unassigned
    {"id": 6, "location": "CR-CT-1-R1",   "extra": {}},                          # deep child of CR
    {"id": 7, "location": "DR-CT-1-R2-L", "extra": {}},                          # split-side child of DR
    {"id": 8, "location": "LRX-1",        "extra": {}},                          # prefix near-miss (NOT under LR)
    {"id": 9, "location": "",             "extra": {"physical_source": "XL-2"}},    # ghost -> XL-2 / XL
]

STRICT_TARGETS = ["LR", "LR-DB1", "XL", "XL-2", "CORE1-M0", "CR", "DR", "CR-CT-1-R1", "LRX"]


def _old_strict_match(s, target):
    """Pre-migration matching predicate — the A/B oracle."""
    target = str(target).strip().upper()
    bare = "-" not in target
    sloc = (s.get('location') or '').strip().upper()
    extra = s.get('extra', {}) or {}
    p_source = str(extra.get('physical_source', '')).strip().replace('"', '').upper()
    return (sloc == target or p_source == target
            or (bare and (sloc.startswith(target + "-") or p_source.startswith(target + "-"))))


@pytest.mark.parametrize("target", STRICT_TARGETS)
def test_strict_location_match_matches_legacy_predicate(monkeypatch, target):
    """The migrated resolve_parent predicate returns the exact same id set as
    the legacy bare/startswith probe for every target shape."""
    import config_loader

    payload = [dict(s, extra=dict(s["extra"])) for s in _STRICT_SPOOLS]

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    monkeypatch.setattr(spoolman_api, "requests",
                        types.SimpleNamespace(get=lambda url, timeout=5: _Resp()))
    monkeypatch.setattr(config_loader, "get_api_urls", lambda: ("http://sm", "http://fb"))

    expected = sorted(s["id"] for s in _STRICT_SPOOLS if _old_strict_match(s, target))
    assert sorted(spoolman_api.get_spools_at_location_strict(target)) == expected


# ---------------------------------------------------------------------------
# Consumer 4 — spoolman_api._build_location_match (the canonical matcher
# behind get_spools_at_location_detailed + the Printer Status widget)
# ---------------------------------------------------------------------------
# Was: "-" not in target_loc_upper and sloc.upper().startswith(target+"-")
#      (same for the ghost physical_source clause)
# Now: resolve_parent(sloc) == target_loc_upper / resolve_parent(p_source) == ...

_BUILD_SPOOLS = [
    {"id": 1, "location": "LR-DB1",     "extra": {"container_slot": "1"}},                                  # direct + child of LR
    {"id": 2, "location": "XL-1",       "extra": {}},                                                       # child of XL
    {"id": 3, "location": "CORE1-M0",   "extra": {"physical_source": "LR-DB1", "physical_source_slot": "2"}},  # ghost -> LR-DB1 / LR
    {"id": 4, "location": "",           "extra": {}},                                                       # unassigned
    {"id": 5, "location": "LRX-1",      "extra": {}},                                                       # prefix near-miss
    {"id": 6, "location": "CR-CT-1-R1", "extra": {}},                                                       # deep child of CR
]

BUILD_TARGETS = ["LR", "LR-DB1", "XL", "CORE1-M0", "CR", "LRX", "UNASSIGNED"]


def _old_build_match_decision(s, target_upper, check_unassigned=False):
    """Pre-migration match + ghost decision — the A/B oracle."""
    sloc = (s.get('location') or '').strip()
    extra = s.get('extra', {}) or {}
    match = False
    is_ghost = False
    if check_unassigned:
        if not sloc:
            match = True
    elif sloc.upper() == target_upper:
        match = True
    elif "-" not in target_upper and sloc.upper().startswith(target_upper + "-"):
        match = True
    p_source = str(extra.get('physical_source', '')).strip().replace('"', '').upper()
    if not match and not check_unassigned:
        if p_source == target_upper or ("-" not in target_upper and p_source.startswith(target_upper + "-")):
            match = True
            is_ghost = True
    return match, is_ghost


@pytest.mark.parametrize("target", BUILD_TARGETS)
def test_build_location_match_matches_legacy_predicate(target):
    """The migrated matcher agrees with the legacy predicate on match / no-match
    and the ghost flag for every spool, and a ghost hit still surfaces the
    physical_source_slot as its slot."""
    check_unassigned = (target == "UNASSIGNED")
    target_upper = target.upper()
    for s in _BUILD_SPOOLS:
        exp_match, exp_ghost = _old_build_match_decision(s, target_upper, check_unassigned)
        res = spoolman_api._build_location_match(
            dict(s, extra=dict(s["extra"])), target_upper, check_unassigned)
        assert (res is not None) == exp_match, f"target={target} spool={s['id']}"
        if res is not None:
            assert res["id"] == s["id"]
            assert bool(res["is_ghost"]) == exp_ghost
            if exp_ghost:
                assert res["slot"] == str(s["extra"].get("physical_source_slot", "")).strip('"')
