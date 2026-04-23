"""Filabridge call-ordering tests (2026-04-22 desync regression).

These tests assert the sequence of filabridge writes during a spool move.
The bug they guard against: a move from Core1-M0 directly into a dryer
slot bound to a different toolhead (XL-3) would silently corrupt
filabridge state because the code mapped the destination BEFORE
unmapping the origin, and filabridge enforces one-spool-one-toolhead.

Key assertions:
  - Origin toolhead is unmapped before destination is mapped.
  - When filabridge rejects the unmap, the destination map does NOT fire
    (no layering bad state on bad state).
  - Response includes filabridge_ok / filabridge_detail so the endpoint
    layer can raise a warning toast.
"""

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import logic  # noqa: E402


def _call_spool_id(call):
    """Extract the spool_id field from a recorded requests.post call."""
    # Calls look like: requests.post(url, json={...}, timeout=3)
    return call.kwargs.get('json', {}).get('spool_id')


def _call_toolhead(call):
    j = call.kwargs.get('json', {})
    return (j.get('printer_name'), j.get('toolhead_id'))


def test_cross_toolhead_move_unmaps_origin_before_mapping_destination():
    """Move Spool #240 from Core1-M0 directly to XL-3. Assert filabridge
    sees unmap(Core1-M0) BEFORE map(XL-3, 240). This is the core fix."""
    printer_map = {
        "CORE1-M0": {"printer_name": "Core1", "position": 0},
        "XL-3": {"printer_name": "XL", "position": 3},
    }
    loc_list = [
        {"LocationID": "CORE1-M0", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"},
    ]
    spool_240 = {"id": 240, "location": "CORE1-M0", "extra": {}}

    def fake_update(sid, data):
        return {"id": sid, **data}

    ctx = [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        patch.object(logic.config_loader, "get_api_urls",
                     return_value=("http://spoolman", "http://filabridge")),
        patch.object(logic.locations_db, "load_locations_list", return_value=loc_list),
        patch.object(logic.spoolman_api, "get_spool", return_value=spool_240),
        patch.object(logic.spoolman_api, "get_spools_at_location", return_value=[]),
        patch.object(logic.spoolman_api, "get_spools_at_location_detailed", return_value=[]),
        patch.object(logic.spoolman_api, "format_spool_display",
                     return_value={"text": "#240", "color": "ff0000"}),
        patch.object(logic.spoolman_api, "update_spool", side_effect=fake_update),
        patch.object(logic.requests, "post", return_value=MagicMock(ok=True)),
    ]
    for m in ctx:
        m.start()
    try:
        result = logic.perform_smart_move("XL-3", [240], target_slot=None, origin="test")
        post = logic.requests.post
    finally:
        for m in reversed(ctx):
            m.stop()

    # Two filabridge POSTs: unmap(Core1-M0) then map(XL-3, 240).
    posts = [c for c in post.call_args_list]
    assert len(posts) == 2, f"expected 2 fb POSTs, got {len(posts)}: {posts!r}"

    first, second = posts
    assert _call_toolhead(first) == ("Core1", 0), f"first call should unmap Core1-M0, got {_call_toolhead(first)!r}"
    assert _call_spool_id(first) == 0, "first call should be unmap (spool_id=0)"

    assert _call_toolhead(second) == ("XL", 3), f"second call should map XL-3, got {_call_toolhead(second)!r}"
    assert _call_spool_id(second) == 240, "second call should map spool 240"

    assert result["filabridge_ok"] is True
    assert result["filabridge_detail"] == ""


def test_bound_slot_move_preserves_two_step_semantics_and_orders_fb():
    """Move Spool #240 from Core1-M0 into a dryer slot bound to XL-3.

    The two user-visible writes (dryer placement + toolhead deploy) stay
    intact. What changes: between them, filabridge sees unmap(Core1-M0)
    before map(XL-3, 240) — previously unmap(Core1-M0) never fired at
    all, and the map was rejected."""
    printer_map = {
        "CORE1-M0": {"printer_name": "Core1", "position": 0},
        "XL-3": {"printer_name": "XL", "position": 3},
    }
    loc_list = [
        {"LocationID": "CORE1-M0", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4",
         "extra": {"slot_targets": {"3": "XL-3"}}},
    ]

    # Phase 1 looks up the spool at Core1-M0. Phase 2 (the recursive
    # auto-deploy call) then looks up the same id again — by that point
    # Spoolman has been written to the dryer. The test fakes that with a
    # counter so the second get returns the dryer-placed spool.
    lookups = {"calls": 0}

    def fake_get_spool(sid):
        lookups["calls"] += 1
        if lookups["calls"] == 1:
            return {"id": 240, "location": "CORE1-M0", "extra": {}}
        return {"id": 240, "location": "LR-MDB-1", "extra": {"container_slot": "3"}}

    update_calls = []

    def fake_update(sid, data):
        update_calls.append((sid, dict(data)))
        return {"id": sid, **data}

    ctx = [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        patch.object(logic.config_loader, "get_api_urls",
                     return_value=("http://spoolman", "http://filabridge")),
        patch.object(logic.locations_db, "load_locations_list", return_value=loc_list),
        patch.object(logic.spoolman_api, "get_spool", side_effect=fake_get_spool),
        patch.object(logic.spoolman_api, "get_spools_at_location", return_value=[]),
        patch.object(logic.spoolman_api, "get_spools_at_location_detailed", return_value=[]),
        patch.object(logic.spoolman_api, "format_spool_display",
                     return_value={"text": "#240", "color": "ff0000"}),
        patch.object(logic.spoolman_api, "update_spool", side_effect=fake_update),
        patch.object(logic.requests, "post", return_value=MagicMock(ok=True)),
    ]
    for m in ctx:
        m.start()
    try:
        result = logic.perform_smart_move("LR-MDB-1", [240], target_slot="3", origin="test")
        post_calls = list(logic.requests.post.call_args_list)
    finally:
        for m in reversed(ctx):
            m.stop()

    # Two Spoolman updates (user-visible two-step flow preserved)
    locations = [data.get("location") for sid, data in update_calls]
    assert "LR-MDB-1" in locations, f"phase 1 (dryer placement) missing: {update_calls!r}"
    assert "XL-3" in locations, f"phase 2 (toolhead deploy) missing: {update_calls!r}"

    # Filabridge sequence: unmap(Core1-M0) then map(XL-3, 240)
    assert len(post_calls) == 2, f"expected 2 fb POSTs, got {len(post_calls)}: {post_calls!r}"
    unmap_call, map_call = post_calls
    assert _call_toolhead(unmap_call) == ("Core1", 0)
    assert _call_spool_id(unmap_call) == 0
    assert _call_toolhead(map_call) == ("XL", 3)
    assert _call_spool_id(map_call) == 240

    assert result["filabridge_ok"] is True
    assert result.get("auto_deployed_to") == "XL-3"


def test_filabridge_reject_on_unmap_aborts_destination_map():
    """If filabridge rejects the origin unmap (e.g. HTTP 409), the
    destination map must NOT fire. The response reports the failure so
    the endpoint layer can raise a warning toast."""
    printer_map = {
        "CORE1-M0": {"printer_name": "Core1", "position": 0},
        "XL-3": {"printer_name": "XL", "position": 3},
    }
    loc_list = [
        {"LocationID": "CORE1-M0", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"},
    ]
    spool_240 = {"id": 240, "location": "CORE1-M0", "extra": {}}

    def fake_update(sid, data):
        return {"id": sid, **data}

    # First call (the origin unmap) fails; anything after is unreached.
    rejected = MagicMock(ok=False, status_code=409, text="already mapped elsewhere")
    accepted = MagicMock(ok=True, status_code=200, text="")

    ctx = [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        patch.object(logic.config_loader, "get_api_urls",
                     return_value=("http://spoolman", "http://filabridge")),
        patch.object(logic.locations_db, "load_locations_list", return_value=loc_list),
        patch.object(logic.spoolman_api, "get_spool", return_value=spool_240),
        patch.object(logic.spoolman_api, "get_spools_at_location", return_value=[]),
        patch.object(logic.spoolman_api, "get_spools_at_location_detailed", return_value=[]),
        patch.object(logic.spoolman_api, "format_spool_display",
                     return_value={"text": "#240", "color": "ff0000"}),
        patch.object(logic.spoolman_api, "update_spool", side_effect=fake_update),
        patch.object(logic.requests, "post", side_effect=[rejected, accepted]),
    ]
    for m in ctx:
        m.start()
    try:
        result = logic.perform_smart_move("XL-3", [240], target_slot=None, origin="test")
        post_calls = list(logic.requests.post.call_args_list)
    finally:
        for m in reversed(ctx):
            m.stop()

    # Exactly ONE filabridge POST — the rejected unmap. The destination
    # map was aborted because we won't layer bad state on bad state.
    assert len(post_calls) == 1, f"destination map should not fire after unmap reject: {post_calls!r}"
    assert _call_spool_id(post_calls[0]) == 0, "only call should be the unmap"

    assert result["filabridge_ok"] is False
    assert "409" in result["filabridge_detail"], f"detail should include HTTP code: {result!r}"


def test_move_to_same_toolhead_does_not_double_unmap():
    """Re-scanning a spool that's already on the target toolhead should
    not issue an unmap(self) — that would clear the toolhead we're about
    to map back to. Asserts only the destination map fires."""
    printer_map = {"XL-3": {"printer_name": "XL", "position": 3}}
    loc_list = [{"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"}]
    spool_240 = {
        "id": 240, "location": "XL-3",
        "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "3"},
    }

    def fake_update(sid, data):
        return {"id": sid, **data}

    # get_spools_at_location returns [240] so the Smart-Load branch knows
    # the spool is already home (and skips ejecting itself).
    ctx = [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        patch.object(logic.config_loader, "get_api_urls",
                     return_value=("http://spoolman", "http://filabridge")),
        patch.object(logic.locations_db, "load_locations_list", return_value=loc_list),
        patch.object(logic.spoolman_api, "get_spool", return_value=spool_240),
        patch.object(logic.spoolman_api, "get_spools_at_location", return_value=[240]),
        patch.object(logic.spoolman_api, "get_spools_at_location_detailed", return_value=[]),
        patch.object(logic.spoolman_api, "format_spool_display",
                     return_value={"text": "#240", "color": "ff0000"}),
        patch.object(logic.spoolman_api, "update_spool", side_effect=fake_update),
        patch.object(logic.requests, "post", return_value=MagicMock(ok=True)),
    ]
    for m in ctx:
        m.start()
    try:
        result = logic.perform_smart_move("XL-3", [240], target_slot=None, origin="test")
        post_calls = list(logic.requests.post.call_args_list)
    finally:
        for m in reversed(ctx):
            m.stop()

    # Exactly one POST: the destination map. No origin unmap because
    # origin == destination.
    assert len(post_calls) == 1, f"re-map of same toolhead should not include unmap: {post_calls!r}"
    assert _call_toolhead(post_calls[0]) == ("XL", 3)
    assert _call_spool_id(post_calls[0]) == 240

    assert result["filabridge_ok"] is True
