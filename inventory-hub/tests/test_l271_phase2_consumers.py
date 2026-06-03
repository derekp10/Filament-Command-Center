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
import pytest

import logic


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
