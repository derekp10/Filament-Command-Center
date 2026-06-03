"""Printer Status widget — box-bounding regression guards (2026-06-01).

Root cause: `_pulse_section_printer_status` gated a toolhead's `item`
(loaded-spool contents) behind a dryer-box-derived `is_bound` flag, so a
directly-fed toolhead with no dryer box — Core One's prod setup — showed
empty even with a spool physically loaded. The symptom Derek reported:
"status seems to key off attached dryerboxes, and not actual print heads."

Fix: occupancy now keys off the toolhead LOCATION via
`spoolman_api.bucket_spools_by_location` (ONE Spoolman fetch for every
toolhead at once); `unbound` stays a pure dryer-box-binding hint used only
for the widget's "🔗 no bound slot" affordance — it never gates contents.

These deterministic unit tests (no live Spoolman) pin:
  - bucket_spools_by_location matches per-location semantics (direct
    location + physical_source ghost) via the shared _build_location_match;
  - a LOADED but UNBOUND toolhead surfaces its spool (the masked path);
  - `unbound` is independent of occupancy;
  - exactly ONE spool-list fetch regardless of toolhead count.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import app          # noqa: E402
import spoolman_api  # noqa: E402


def _fake_display(s):
    """Offline stand-in for format_spool_display so the bucket logic never
    touches Spoolman during the unit test."""
    return {
        'text': f"#{s['id']}",
        'color': 'ff0000',
        'slot': '',
        'color_direction': 'longitudinal',
        'details': {},
    }


# --------------------------------------------------------------------------
# bucket_spools_by_location
# --------------------------------------------------------------------------

def test_bucket_matches_per_location_including_ghost():
    spools = [
        {'id': 150, 'location': 'CORE1-M0', 'extra': {}, 'remaining_weight': 700, 'archived': False},
        {'id': 225, 'location': 'XL-1', 'extra': {}, 'remaining_weight': 0, 'archived': False},
        # Ghost: physically sits in a dryer box but physical_source feeds XL-4.
        {'id': 999, 'location': 'LR-MDB-1',
         'extra': {'physical_source': 'XL-4', 'physical_source_slot': '2'},
         'remaining_weight': 500, 'archived': False},
        {'id': 333, 'location': 'SHELF-A', 'extra': {}, 'remaining_weight': 100, 'archived': False},
    ]
    with patch.object(spoolman_api, 'format_spool_display', side_effect=_fake_display):
        buckets = spoolman_api.bucket_spools_by_location(
            ['CORE1-M0', 'CORE1-M1', 'XL-1', 'XL-4'], spools=spools
        )
    assert [i['id'] for i in buckets['CORE1-M0']] == [150]   # direct location match
    assert [i['id'] for i in buckets['XL-1']] == [225]
    assert buckets['CORE1-M1'] == []                          # empty toolhead still keyed
    assert [i['id'] for i in buckets['XL-4']] == [999]        # physical_source ghost match
    assert buckets['XL-4'][0]['is_ghost'] is True
    # A spool parked elsewhere never leaks into a toolhead bucket.
    all_ids = {i['id'] for v in buckets.values() for i in v}
    assert 333 not in all_ids


def test_bucket_equivalent_to_per_location_calls():
    """Drop-in fidelity: bucketing N locations in one pass yields the same
    per-location result as N separate get_spools_at_location_detailed calls."""
    spools = [
        {'id': 150, 'location': 'CORE1-M0', 'extra': {}, 'remaining_weight': 700, 'archived': False},
        {'id': 225, 'location': 'XL-1', 'extra': {}, 'remaining_weight': 0, 'archived': False},
        {'id': 999, 'location': 'LR-MDB-1',
         'extra': {'physical_source': 'XL-4', 'physical_source_slot': '2'},
         'remaining_weight': 500, 'archived': False},
    ]
    loc_ids = ['CORE1-M0', 'XL-1', 'XL-2', 'XL-4']
    with patch.object(spoolman_api, 'format_spool_display', side_effect=_fake_display), \
         patch.object(spoolman_api, 'get_all_spools', return_value=spools):
        bucket = spoolman_api.bucket_spools_by_location(loc_ids)
        for lid in loc_ids:
            per = spoolman_api.get_spools_at_location_detailed(lid)
            assert [i['id'] for i in bucket[lid]] == [i['id'] for i in per], lid


def test_bucket_empty_loc_ids_returns_empty():
    assert spoolman_api.bucket_spools_by_location([]) == {}
    assert spoolman_api.bucket_spools_by_location(None) == {}


def test_bucket_dedupes_and_uppercases_targets():
    spools = [{'id': 1, 'location': 'core1-m0', 'extra': {}, 'remaining_weight': 1, 'archived': False}]
    with patch.object(spoolman_api, 'format_spool_display', side_effect=_fake_display):
        buckets = spoolman_api.bucket_spools_by_location(['CORE1-M0', 'core1-m0', ' CORE1-M0 '], spools=spools)
    assert list(buckets.keys()) == ['CORE1-M0']        # deduped + uppercased
    assert [i['id'] for i in buckets['CORE1-M0']] == [1]  # case-insensitive location match


# --------------------------------------------------------------------------
# _pulse_section_printer_status — the ungate
# --------------------------------------------------------------------------

def _patch_pulse(printer_map, bindings_toolheads, spools, get_all=None):
    return [
        patch.object(app.config_loader, 'load_config', return_value={'printer_map': printer_map}),
        patch.object(app.config_loader, 'get_api_urls', return_value=('http://sm', 'http://fb')),
        patch.object(app.prusalink_api, 'get_printer_state', return_value=None),
        patch.object(app.locations_db, 'get_bindings_for_machine',
                     return_value={'printer_name': 'x', 'toolheads': bindings_toolheads, 'printer_pool': []}),
        patch.object(app.spoolman_api, 'get_all_spools', get_all or (lambda *a, **k: spools)),
        patch.object(app.spoolman_api, 'format_spool_display', side_effect=_fake_display),
    ]


def _run_pulse(ctx):
    for m in ctx:
        m.start()
    try:
        return app._pulse_section_printer_status()
    finally:
        for m in reversed(ctx):
            m.stop()


def test_unbound_toolhead_with_loaded_spool_surfaces_item():
    """Core regression guard: Core One direct-fed (NO dryer-box binding)
    with a spool physically on CORE1-M0 must surface the spool with
    unbound=True. Against the pre-fix gate this returned item=None."""
    printer_map = {'CORE1-M0': {'printer_name': 'Core One', 'position': 0}}
    spools = [{'id': 150, 'location': 'CORE1-M0', 'extra': {}, 'remaining_weight': 712, 'archived': False}]
    ps = _run_pulse(_patch_pulse(printer_map, bindings_toolheads={}, spools=spools))
    th = ps['Core One']['toolheads'][0]
    assert th['id'] == 'CORE1-M0'
    assert th['unbound'] is True, "no dryer box feeds it → unbound stays True"
    assert th['item'] is not None, "loaded spool must NOT be masked by missing binding"
    assert th['item']['id'] == 150


def test_unbound_flag_independent_of_occupancy():
    """unbound reflects ONLY dryer-box bindings — never occupancy."""
    printer_map = {
        'XL-1': {'printer_name': 'XL', 'position': 0},  # bound + loaded
        'XL-2': {'printer_name': 'XL', 'position': 1},  # bound + empty
        'XL-3': {'printer_name': 'XL', 'position': 2},  # unbound + loaded
        'XL-4': {'printer_name': 'XL', 'position': 3},  # unbound + empty
    }
    spools = [
        {'id': 11, 'location': 'XL-1', 'extra': {}, 'remaining_weight': 500, 'archived': False},
        {'id': 33, 'location': 'XL-3', 'extra': {}, 'remaining_weight': 400, 'archived': False},
    ]
    bindings = {'XL-1': [{'box': 'B', 'slot': '1'}], 'XL-2': [{'box': 'B', 'slot': '2'}], 'XL-3': [], 'XL-4': []}
    ps = _run_pulse(_patch_pulse(printer_map, bindings_toolheads=bindings, spools=spools))
    ths = {t['id']: t for t in ps['XL']['toolheads']}
    assert ths['XL-1']['unbound'] is False and ths['XL-1']['item']['id'] == 11
    assert ths['XL-2']['unbound'] is False and ths['XL-2']['item'] is None
    assert ths['XL-3']['unbound'] is True and ths['XL-3']['item']['id'] == 33   # loaded+unbound surfaces
    assert ths['XL-4']['unbound'] is True and ths['XL-4']['item'] is None


def test_ghost_sourced_spool_surfaces_at_unbound_toolhead():
    """A spool ghosted to a dryer-box-less toolhead via physical_source must
    also surface (the box is the feed origin, the toolhead is where it prints)."""
    printer_map = {'CORE1-M0': {'printer_name': 'Core One', 'position': 0}}
    spools = [{'id': 150, 'location': 'PM-DB-5',
               'extra': {'physical_source': 'CORE1-M0', 'physical_source_slot': '3'},
               'remaining_weight': 712, 'archived': False}]
    ps = _run_pulse(_patch_pulse(printer_map, bindings_toolheads={}, spools=spools))
    th = ps['Core One']['toolheads'][0]
    assert th['unbound'] is True
    assert th['item'] is not None and th['item']['id'] == 150
    assert th['item']['is_ghost'] is True


def test_single_spoolman_fetch_regardless_of_toolhead_count():
    """Perf guard: occupancy for ALL toolheads resolves in ONE Spoolman
    spool-list fetch (not one per toolhead). Locks in the bulk-fetch so a
    future refactor can't silently reintroduce the N-fetch fan-out that the
    pre-fix per-bound-toolhead loop had."""
    printer_map = {f'CORE1-M{i}': {'printer_name': 'Core One', 'position': i} for i in range(6)}
    printer_map.update({f'XL-{i}': {'printer_name': 'XL', 'position': i} for i in range(1, 6)})
    spools = [{'id': 1, 'location': 'CORE1-M0', 'extra': {}, 'remaining_weight': 100, 'archived': False}]
    get_all = MagicMock(return_value=spools)
    ps = _run_pulse(_patch_pulse(printer_map, bindings_toolheads={}, spools=spools, get_all=get_all))
    assert get_all.call_count == 1, f"expected ONE spool-list fetch, got {get_all.call_count}"
    total_ths = sum(len(p['toolheads']) for p in ps.values())
    assert total_ths == 11  # 6 Core One + 5 XL all rendered
