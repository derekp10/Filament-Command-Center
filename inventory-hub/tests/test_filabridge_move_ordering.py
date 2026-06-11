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
        # L271 Phase 4: printer_map is read via locations_db.get_active_printer_map()
        # (Printer-row toolheads[]); the config fallback was removed at the cutover,
        # so inject through the accessor too.
        patch.object(logic.locations_db, "get_active_printer_map",
                     return_value=printer_map),
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
        patch.object(logic.requests, "get", return_value=MagicMock(ok=False, status_code=404)),
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
        # L271 Phase 4: printer_map is read via locations_db.get_active_printer_map()
        # (Printer-row toolheads[]); the config fallback was removed at the cutover,
        # so inject through the accessor too.
        patch.object(logic.locations_db, "get_active_printer_map",
                     return_value=printer_map),
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
        patch.object(logic.requests, "get", return_value=MagicMock(ok=False, status_code=404)),
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
        # L271 Phase 4: printer_map is read via locations_db.get_active_printer_map()
        # (Printer-row toolheads[]); the config fallback was removed at the cutover,
        # so inject through the accessor too.
        patch.object(logic.locations_db, "get_active_printer_map",
                     return_value=printer_map),
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
        patch.object(logic.requests, "get", return_value=MagicMock(ok=False, status_code=404)),
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


def test_scope1_spoolman_is_authoritative_origin():
    """[Scope 1 / FilaBridge absorption] FCC is now the single source of truth
    for the toolhead<->spool map — _fb_spool_location reads the spool's Spoolman
    `location`, NOT FilaBridge `/status`. So the pre-map origin unmap targets
    wherever SPOOLMAN says the spool is, even if a (now-ignored) FilaBridge view
    would disagree.

    Pre-Scope-1 this asserted the INVERSE — FilaBridge winning over a Spoolman
    lag — which was the dual-writer desync this change eliminates: with FCC the
    only map writer and Spoolman written first, the two can no longer diverge.

    Setup: Spoolman says #213 is on XL-2; we move it to CORE1-M0. The origin
    unmap must clear XL-2 before mapping CORE1-M0. A contradictory FilaBridge
    /status (which would claim CORE1-M0 == destination → skip the unmap) is
    provided to prove it's never consulted."""
    printer_map = {
        "CORE1-M0": {"printer_name": "Core1", "position": 0},
        "XL-2": {"printer_name": "XL", "position": 2},
    }
    loc_list = [
        {"LocationID": "CORE1-M0", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1"},
    ]
    # Spoolman — the authoritative origin under Scope 1 — says #213 is on XL-2.
    spool_213 = {"id": 213, "location": "XL-2", "extra": {}}

    def fake_update(sid, data):
        return {"id": sid, **data}

    # A contradictory FilaBridge /status that (pre-Scope-1) would have claimed
    # #213 on CORE1-M0 — origin == destination → skip unmap. Scope 1 never reads
    # /status, so this is ignored and Spoolman's XL-2 origin wins.
    fb_status_resp = MagicMock(ok=True, status_code=200, text='')
    fb_status_resp.json.return_value = {
        "toolhead_mappings": {
            "printer_core1": {
                "0": {"printer_name": "Core1", "toolhead_id": 0, "spool_id": 213},
            },
        },
    }

    ok_resp = MagicMock(ok=True, status_code=200, text="")

    ctx = [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        # L271 Phase 4: printer_map is read via locations_db.get_active_printer_map()
        # (Printer-row toolheads[]); the config fallback was removed at the cutover,
        # so inject through the accessor too.
        patch.object(logic.locations_db, "get_active_printer_map",
                     return_value=printer_map),
        patch.object(logic.config_loader, "get_api_urls",
                     return_value=("http://spoolman", "http://filabridge")),
        patch.object(logic.locations_db, "load_locations_list", return_value=loc_list),
        patch.object(logic.spoolman_api, "get_spool", return_value=spool_213),
        patch.object(logic.spoolman_api, "get_spools_at_location", return_value=[]),
        patch.object(logic.spoolman_api, "get_spools_at_location_detailed", return_value=[]),
        patch.object(logic.spoolman_api, "format_spool_display",
                     return_value={"text": "#213", "color": "ff0000"}),
        patch.object(logic.spoolman_api, "update_spool", side_effect=fake_update),
        patch.object(logic.requests, "post", return_value=ok_resp),
        patch.object(logic.requests, "get", return_value=fb_status_resp),
    ]
    for m in ctx:
        m.start()
    try:
        result = logic.perform_smart_move("CORE1-M0", [213], target_slot=None, origin="test")
        post_calls = list(logic.requests.post.call_args_list)
    finally:
        for m in reversed(ctx):
            m.stop()

    # Two POSTs: unmap XL-2 (Spoolman's authoritative origin), then map
    # CORE1-M0 <- 213. The contradictory FilaBridge /status (origin ==
    # destination) is never consulted, so the unmap fires off Spoolman.
    assert len(post_calls) == 2, f"expected unmap+map, got {post_calls!r}"
    unmap_call, map_call = post_calls
    assert _call_toolhead(unmap_call) == ("XL", 2), \
        f"unmap should target Spoolman's origin (XL-2), got {_call_toolhead(unmap_call)!r}"
    assert _call_spool_id(unmap_call) == 0
    assert _call_toolhead(map_call) == ("Core1", 0)
    assert _call_spool_id(map_call) == 213
    assert result["filabridge_ok"] is True


def test_scope1_fb_spool_location_reads_spoolman_not_filabridge():
    """[Scope 1] _fb_spool_location resolves the spool's toolhead from its
    Spoolman `location` (through the printer_map), and does NOT probe FilaBridge
    `/status` — proving the READ side moved off FilaBridge (this is what kills
    the residual L3 latency tail and the dual-writer desync class)."""
    printer_map = {"XL-2": {"printer_name": "XL", "position": 2}}

    # On a toolhead -> (printer_name, position); FilaBridge /status untouched.
    with patch.object(logic.locations_db, "get_active_printer_map",
                      return_value=printer_map), \
         patch.object(logic.spoolman_api, "get_spool",
                      return_value={"id": 213, "location": "XL-2"}) as get_spool, \
         patch.object(logic.requests, "get") as fb_get:
        assert logic._fb_spool_location(213) == ("XL", 2)
        assert fb_get.call_count == 0, \
            "Scope 1: _fb_spool_location must not read FilaBridge /status"
        get_spool.assert_called_with(213)

    # Not on a toolhead (Spoolman says a dryer box) -> None; still no /status.
    with patch.object(logic.locations_db, "get_active_printer_map",
                      return_value=printer_map), \
         patch.object(logic.spoolman_api, "get_spool",
                      return_value={"id": 213, "location": "PM-DB-1"}), \
         patch.object(logic.requests, "get") as fb_get2:
        assert logic._fb_spool_location(213) is None
        assert fb_get2.call_count == 0


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
        # L271 Phase 4: printer_map is read via locations_db.get_active_printer_map()
        # (Printer-row toolheads[]); the config fallback was removed at the cutover,
        # so inject through the accessor too.
        patch.object(logic.locations_db, "get_active_printer_map",
                     return_value=printer_map),
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
        patch.object(logic.requests, "get", return_value=MagicMock(ok=False, status_code=404)),
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


def _fb_status_with_mapping(printer_name, toolhead_id, spool_id):
    """Build a fake filabridge `/status` response payload that reports
    `spool_id` mapped to (printer_name, toolhead_id). Used by L204
    tests where _fb_spool_location needs to find the spool's toolhead
    via the filabridge status endpoint."""
    return {
        "toolhead_mappings": {
            printer_name: {
                str(toolhead_id): {
                    "printer_name": printer_name,
                    "spool_id": spool_id,
                }
            }
        }
    }


def test_l204_dryer_move_unmaps_filabridge_when_spool_was_on_toolhead():
    """L204 — moving a ghost-deployed spool back to its dryerbox must
    also unmap filabridge for the toolhead that was holding it.
    Pre-fix the DRYER MOVE branch wrote Spoolman cleanly but never
    touched filabridge, leaving the toolhead pinned to a spool that
    Spoolman had already moved away. Repro: filabridge reports the
    spool on XL-3; perform_smart_move to PM-DB-1 must POST an unmap
    for XL-3 before / during the move."""
    printer_map = {
        "XL-3": {"printer_name": "XL", "position": 3},
    }
    loc_list = [
        {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "4",
         "extra": {"slot_targets": {"1": "XL-3"}}},
    ]
    spool_240 = {"id": 240, "location": "XL-3",
                 "extra": {"physical_source": "PM-DB-1", "physical_source_slot": "1"}}

    def fake_update(sid, data):
        return {"id": sid, **data}

    fb_status_resp = MagicMock(ok=True)
    fb_status_resp.json.return_value = _fb_status_with_mapping("XL", 3, 240)

    ctx = [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        # L271 Phase 4: printer_map is read via locations_db.get_active_printer_map()
        # (Printer-row toolheads[]); the config fallback was removed at the cutover,
        # so inject through the accessor too.
        patch.object(logic.locations_db, "get_active_printer_map",
                     return_value=printer_map),
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
        patch.object(logic.requests, "get", return_value=fb_status_resp),
    ]
    for m in ctx:
        m.start()
    try:
        logic.perform_smart_move("PM-DB-1", [240], target_slot="1", origin="test")
        post_calls = list(logic.requests.post.call_args_list)
    finally:
        for m in reversed(ctx):
            m.stop()

    # The dryer-move branch must unmap XL-3 (where filabridge reports
    # the spool) before / during the move. Auto-deploy chains to XL-3
    # again, so we also expect a final map(XL-3, 240) — but the critical
    # assertion is that the unmap is present at all.
    unmap_calls = [c for c in post_calls if _call_spool_id(c) == 0]
    unmapped_targets = [_call_toolhead(c) for c in unmap_calls]
    assert ("XL", 3) in unmapped_targets, (
        f"expected unmap(XL-3) in fb POSTs, got: "
        f"{[(_call_toolhead(c), _call_spool_id(c)) for c in post_calls]!r}"
    )


def test_scope1_eject_trusts_spoolman_no_toolhead_rescue():
    """[Scope 1 / FilaBridge absorption] When Spoolman says the spool is NOT on
    a toolhead (here: in dryer box PM-DB-1), ejecting it issues no toolhead
    unmap — FCC trusts Spoolman as the single source of truth. Pre-Scope-1 the
    eject probed FilaBridge `/status` and rescue-unmapped a toolhead the spool
    was still pinned to (a Spoolman-lag desync); that whole class is gone now
    (FCC is the only map writer + writes Spoolman first; out-of-band drift is
    healed by the L324 reconcile, not opportunistically here). A contradictory
    FilaBridge /status claiming XL-3 is provided to prove it's ignored."""
    printer_map = {
        "XL-3": {"printer_name": "XL", "position": 3},
    }
    spool_240 = {"id": 240, "location": "PM-DB-1",
                 "extra": {"container_slot": "1"}}

    def fake_update(sid, data):
        return True

    fb_status_resp = MagicMock(ok=True)
    fb_status_resp.json.return_value = _fb_status_with_mapping("XL", 3, 240)

    ctx = [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        # L271 Phase 4: printer_map is read via locations_db.get_active_printer_map()
        # (Printer-row toolheads[]); the config fallback was removed at the cutover,
        # so inject through the accessor too.
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
        patch.object(logic.requests, "get", return_value=fb_status_resp),
    ]
    for m in ctx:
        m.start()
    try:
        logic.perform_smart_eject(240, confirmed_unassign=True)
        post_calls = list(logic.requests.post.call_args_list)
    finally:
        for m in reversed(ctx):
            m.stop()

    # No toolhead unmap: Spoolman says PM-DB-1 (a dryer box), so the spool
    # isn't on a toolhead and there's nothing to clear. The old rescue-unmap
    # of XL-3 (driven by FilaBridge's view) is gone by design under Scope 1.
    unmaps = [c for c in post_calls
              if _call_spool_id(c) == 0 and _call_toolhead(c) == ("XL", 3)]
    assert not unmaps, (
        f"Scope 1: a spool Spoolman places in a dryer box must NOT trigger a "
        f"FilaBridge toolhead rescue-unmap; got fb POSTs: "
        f"{[(_call_toolhead(c), _call_spool_id(c)) for c in post_calls]!r}"
    )
