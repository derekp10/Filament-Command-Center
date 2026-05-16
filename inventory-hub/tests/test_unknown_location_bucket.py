"""Group 18.1 — virtual UNKNOWN location bucket for physically-lost spools.

Asserts:
  - `/api/locations` injects an UNKNOWN row with Type="Unknown".
  - The row sits at the BOTTOM of the list (Derek's UX pick — finding
    lost spools is the goal, so they shouldn't crowd top placement).
  - It's a sibling-virtual to Unassigned (which is pinned at the top
    as "deliberately on the workbench").
  - `logic.resolve_scan` accepts "UNKNOWN" as a valid bare-string scan
    target (same allow-list as UNASSIGNED).
  - The locations endpoint reports the occupancy count.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402


@pytest.mark.usefixtures("require_server")
def test_locations_api_includes_unknown_row_at_bottom(api_base_url: str):
    r = requests.get(f"{api_base_url}/api/locations", timeout=10)
    assert r.ok, r.text
    locs = r.json()
    assert isinstance(locs, list) and locs, "locations payload is empty"

    # First row is the Unassigned virtual bucket.
    assert locs[0].get('LocationID') == 'Unassigned'
    assert locs[0].get('Type') == 'Virtual'

    # Last row is the Unknown virtual bucket.
    last = locs[-1]
    assert last.get('LocationID') == 'UNKNOWN', (
        f"UNKNOWN row should be pinned at the bottom; last row was {last.get('LocationID')!r}"
    )
    assert last.get('Type') == 'Unknown'
    assert '?' in (last.get('Name') or '') or '❓' in (last.get('Name') or ''), (
        f"Unknown row Name should carry a question-mark cue: {last.get('Name')!r}"
    )
    # Occupancy is a "<n> items" string just like Unassigned's.
    occ = last.get('Occupancy', '')
    assert 'item' in occ, f"Occupancy field missing or malformed: {occ!r}"

    # No duplicates — if a stale on-disk UNKNOWN row exists (Derek
    # experimented with one before this feature landed), the iteration
    # SKIP in app.py keeps only the virtual injection.
    unknown_rows = [l for l in locs if str(l.get('LocationID', '')).upper() == 'UNKNOWN']
    assert len(unknown_rows) == 1, (
        f"Expected exactly one UNKNOWN row (virtual only); got {len(unknown_rows)}: {unknown_rows}"
    )


def test_resolve_scan_accepts_bare_unknown():
    """Mirror of the UNASSIGNED carve-out: typing UNKNOWN as a bare
    location string should resolve as a location move target."""
    with patch.object(logic.locations_db, "load_locations_list", return_value=[]):
        result = logic.resolve_scan("UNKNOWN")
    assert result == {'type': 'location', 'id': 'UNKNOWN'}, result


def test_resolve_scan_rejects_unrelated_bare_string():
    """Negative regression: only UNASSIGNED + UNKNOWN are the bare-string
    virtual buckets. Random text still errors out."""
    with patch.object(logic.locations_db, "load_locations_list", return_value=[]):
        result = logic.resolve_scan("NOT-A-REAL-PLACE")
    assert result.get('type') == 'error'


def test_smart_move_to_unknown_clears_ghost_trail():
    """perform_smart_move's GENERIC branch (which already clears
    physical_source for non-toolhead targets, see L130) handles UNKNOWN
    as just another non-toolhead destination. Spool's `location` gets
    set to UNKNOWN; physical_source / physical_source_slot are popped
    so the "deployed" computation doesn't false-flag the spool."""
    from unittest.mock import MagicMock
    printer_map = {}
    loc_list = []  # UNKNOWN isn't an on-disk row; goes through generic branch.
    spool_data = {
        "id": 555, "location": "LR-MDB-1",
        "extra": {
            "physical_source": "LR-MDB-1",
            "physical_source_slot": "2",
            "container_slot": "2",
        }
    }
    captured = {}

    def _fake_update(sid, data):
        captured['update'] = (sid, data)
        return {"id": sid, **data}

    mocks = [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        patch.object(logic.config_loader, "get_api_urls",
                     return_value=("http://spoolman", "http://filabridge")),
        patch.object(logic.locations_db, "load_locations_list", return_value=loc_list),
        patch.object(logic.spoolman_api, "get_spool", return_value=spool_data),
        patch.object(logic.spoolman_api, "get_spools_at_location", return_value=[]),
        patch.object(logic.spoolman_api, "format_spool_display",
                     return_value={"text": "Test Spool", "color": "ff0000"}),
        patch.object(logic.spoolman_api, "update_spool", side_effect=_fake_update),
        patch.object(logic.requests, "post", return_value=MagicMock(ok=True)),
    ]
    for m in mocks: m.start()
    try:
        logic.perform_smart_move("UNKNOWN", [555], target_slot=None, origin="manual_override")
    finally:
        for m in reversed(mocks): m.stop()

    _, patch_data = captured['update']
    assert patch_data['location'] == 'UNKNOWN'
    extras = patch_data['extra']
    # L130 lineage — ghost trail cleared on non-toolhead destination.
    assert extras.get('physical_source') in (None, ''), (
        f"physical_source should be cleared on move to UNKNOWN, got {extras.get('physical_source')!r}"
    )
    assert extras.get('physical_source_slot') in (None, ''), (
        f"physical_source_slot should be cleared, got {extras.get('physical_source_slot')!r}"
    )
