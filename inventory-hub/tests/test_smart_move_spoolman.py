"""Spool-move pipeline tests — Spoolman is the single source of truth.

Replaces the retired `test_filabridge_move_ordering.py` (FilaBridge Phase-2
cutover, Phase F). That file asserted the ordering of FilaBridge `/map_toolhead`
POSTs during a move (unmap-origin-before-map-destination, abort-on-reject, the
`filabridge_ok`/`filabridge_detail` response fields). FCC is now the sole owner
of the toolhead↔spool map and of deducts, so `_fb_write`/`_fb_spool_location`
and that whole response surface are gone.

What survives — and what these tests now guard:
  - A move writes the spool's Spoolman `location` to the destination.
  - A bound-slot move still does the two-step auto-deploy (dryer placement →
    toolhead deploy) and reports `auto_deployed_to`.
  - A move makes ZERO FilaBridge writes (no `requests.post`) — the regression
    guard that `_fb_write` and its ~12 call sites stay removed.
  - The move result no longer carries `filabridge_ok`/`filabridge_detail`/
    `filabridge_outcomes`.
"""

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import logic  # noqa: E402


def _move_ctx(printer_map, loc_list, get_spool, update_spool,
              spools_at_location=None):
    """Build the standard mock context for a perform_smart_move call.

    `requests.post` is mocked so we can assert it is NEVER called (FilaBridge is
    gone); `requests.get` returns a 404 so the active-print preflight fails open
    (no printer reachable → no active-print block)."""
    return [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        # L271 Phase 4: printer_map is read via locations_db.get_active_printer_map().
        patch.object(logic.locations_db, "get_active_printer_map",
                     return_value=printer_map),
        patch.object(logic.config_loader, "get_api_urls",
                     return_value=("http://spoolman", "http://filabridge")),
        patch.object(logic.locations_db, "load_locations_list", return_value=loc_list),
        patch.object(logic.spoolman_api, "get_spool", **get_spool),
        patch.object(logic.spoolman_api, "get_spools_at_location",
                     return_value=spools_at_location if spools_at_location is not None else []),
        patch.object(logic.spoolman_api, "get_spools_at_location_detailed", return_value=[]),
        patch.object(logic.spoolman_api, "format_spool_display",
                     return_value={"text": "#240", "color": "ff0000"}),
        patch.object(logic.spoolman_api, "update_spool", **update_spool),
        patch.object(logic.requests, "post", return_value=MagicMock(ok=True)),
        patch.object(logic.requests, "get", return_value=MagicMock(ok=False, status_code=404)),
    ]


def test_move_to_toolhead_writes_spoolman_location():
    """Move Spool #240 to XL-3 → Spoolman `location` is written to XL-3, the
    move succeeds, and NO FilaBridge POST fires."""
    printer_map = {"XL-3": {"printer_name": "XL", "position": 3}}
    loc_list = [{"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"}]
    spool_240 = {"id": 240, "location": "PM-DB-1", "extra": {}}

    update_calls = []

    def fake_update(sid, data):
        update_calls.append((sid, dict(data)))
        return {"id": sid, **data}

    ctx = _move_ctx(
        printer_map, loc_list,
        get_spool={"return_value": spool_240},
        update_spool={"side_effect": fake_update},
    )
    for m in ctx:
        m.start()
    try:
        result = logic.perform_smart_move("XL-3", [240], target_slot=None, origin="test")
        post = logic.requests.post
    finally:
        for m in reversed(ctx):
            m.stop()

    # Spoolman written to the destination toolhead.
    locations = [data.get("location") for sid, data in update_calls]
    assert "XL-3" in locations, f"move should write Spoolman location XL-3: {update_calls!r}"
    assert result["status"] == "success"
    # No FilaBridge writes anymore.
    assert post.call_count == 0, f"a move must make no FilaBridge POSTs: {post.call_args_list!r}"
    # The retired response surface is gone.
    for k in ("filabridge_ok", "filabridge_detail", "filabridge_outcomes"):
        assert k not in result, f"result must not carry '{k}' post-cutover: {result!r}"


def test_bound_slot_move_two_step_autodeploy():
    """Move Spool #240 into a dryer slot bound to XL-3 → the two-step flow
    (dryer placement + toolhead deploy) still happens and the result reports
    auto_deployed_to. No FilaBridge POSTs."""
    printer_map = {"XL-3": {"printer_name": "XL", "position": 3}}
    loc_list = [
        {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4",
         "extra": {"slot_targets": {"3": "XL-3"}}},
    ]

    # Phase 1 looks up the spool at its origin; phase 2 (the recursive
    # auto-deploy) looks it up again, by which point Spoolman shows the dryer.
    lookups = {"calls": 0}

    def fake_get_spool(sid):
        lookups["calls"] += 1
        if lookups["calls"] == 1:
            return {"id": 240, "location": "PM-DB-1", "extra": {}}
        return {"id": 240, "location": "LR-MDB-1", "extra": {"container_slot": "3"}}

    update_calls = []

    def fake_update(sid, data):
        update_calls.append((sid, dict(data)))
        return {"id": sid, **data}

    ctx = _move_ctx(
        printer_map, loc_list,
        get_spool={"side_effect": fake_get_spool},
        update_spool={"side_effect": fake_update},
    )
    for m in ctx:
        m.start()
    try:
        result = logic.perform_smart_move("LR-MDB-1", [240], target_slot="3", origin="test")
        post = logic.requests.post
    finally:
        for m in reversed(ctx):
            m.stop()

    # Both Spoolman writes happened (dryer placement + toolhead deploy).
    locations = [data.get("location") for sid, data in update_calls]
    assert "LR-MDB-1" in locations, f"phase 1 (dryer placement) missing: {update_calls!r}"
    assert "XL-3" in locations, f"phase 2 (toolhead deploy) missing: {update_calls!r}"
    assert result.get("auto_deployed_to") == "XL-3"
    assert post.call_count == 0, f"a move must make no FilaBridge POSTs: {post.call_args_list!r}"


def test_move_to_same_toolhead_rescan_succeeds():
    """Re-scanning a spool already on the target toolhead writes Spoolman and
    succeeds (no FilaBridge plumbing to trip over)."""
    printer_map = {"XL-3": {"printer_name": "XL", "position": 3}}
    loc_list = [{"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"}]
    spool_240 = {
        "id": 240, "location": "XL-3",
        "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "3"},
    }

    def fake_update(sid, data):
        return {"id": sid, **data}

    ctx = _move_ctx(
        printer_map, loc_list,
        get_spool={"return_value": spool_240},
        update_spool={"side_effect": fake_update},
        spools_at_location=[240],  # already home → Smart-Load skips self-eject
    )
    for m in ctx:
        m.start()
    try:
        result = logic.perform_smart_move("XL-3", [240], target_slot=None, origin="test")
        post = logic.requests.post
    finally:
        for m in reversed(ctx):
            m.stop()

    assert result["status"] == "success"
    assert post.call_count == 0, f"a move must make no FilaBridge POSTs: {post.call_args_list!r}"


def test_dryer_move_writes_spoolman_and_clears_ghost_trail():
    """Moving a toolhead-loaded spool back to a dryer box writes Spoolman
    `location` to the box and clears the ghost trail. No FilaBridge POSTs."""
    printer_map = {"XL-3": {"printer_name": "XL", "position": 3}}
    loc_list = [
        {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "4"},
    ]
    spool_240 = {"id": 240, "location": "XL-3",
                 "extra": {"physical_source": "PM-DB-1", "physical_source_slot": "1"}}

    update_calls = []

    def fake_update(sid, data):
        update_calls.append((sid, dict(data)))
        return {"id": sid, **data}

    ctx = _move_ctx(
        printer_map, loc_list,
        get_spool={"return_value": spool_240},
        update_spool={"side_effect": fake_update},
    )
    for m in ctx:
        m.start()
    try:
        result = logic.perform_smart_move("PM-DB-1", [240], target_slot=None, origin="test")
        post = logic.requests.post
    finally:
        for m in reversed(ctx):
            m.stop()

    assert result["status"] == "success"
    # Spoolman moved to the box; ghost trail (physical_source) cleared.
    box_writes = [data for sid, data in update_calls if data.get("location") == "PM-DB-1"]
    assert box_writes, f"expected a Spoolman write to PM-DB-1: {update_calls!r}"
    assert box_writes[-1].get("extra", {}).get("physical_source", "") == ""
    assert post.call_count == 0, f"a move must make no FilaBridge POSTs: {post.call_args_list!r}"


def test_eject_writes_spoolman_no_filabridge_post():
    """Ejecting a spool off a toolhead writes Spoolman (location cleared) and
    makes no FilaBridge POST — the toolhead-unmap call is gone."""
    printer_map = {"XL-3": {"printer_name": "XL", "position": 3}}
    spool_240 = {"id": 240, "location": "XL-3", "extra": {"container_slot": "1"}}

    update_calls = []

    def fake_update(sid, data):
        update_calls.append((sid, dict(data)))
        return True

    ctx = [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        patch.object(logic.locations_db, "get_active_printer_map",
                     return_value=printer_map),
        patch.object(logic.config_loader, "get_api_urls",
                     return_value=("http://spoolman", "http://filabridge")),
        patch.object(logic.spoolman_api, "get_spool", return_value=spool_240),
        patch.object(logic.spoolman_api, "get_spools_at_location_detailed", return_value=[]),
        patch.object(logic.spoolman_api, "format_spool_display",
                     return_value={"text": "#240", "color": "ff0000"}),
        patch.object(logic.spoolman_api, "update_spool", side_effect=fake_update),
        patch.object(logic.requests, "post", return_value=MagicMock(ok=True)),
        patch.object(logic.requests, "get", return_value=MagicMock(ok=False, status_code=404)),
    ]
    for m in ctx:
        m.start()
    try:
        logic.perform_smart_eject(240, confirmed_unassign=True)
        post = logic.requests.post
    finally:
        for m in reversed(ctx):
            m.stop()

    assert update_calls, "eject should write Spoolman"
    assert post.call_count == 0, f"eject must make no FilaBridge POSTs: {post.call_args_list!r}"
