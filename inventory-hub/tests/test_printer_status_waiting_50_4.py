"""Group 50.4 ("stored, not loaded"; Derek, 2026-10-14 and 30), the server's half.

The heartbeat's printer_status gives a head `waiting`: the spools stored in a
box slot that feeds it and not loaded on it, as a mid-print "Just store it"
leaves one (every such spool, a slot prepped on purpose included: Derek's
answer). From the tick's one spool list: no Spoolman read of its own. Only a
multi-slot box's own slot counts (a single-slot box's slot-1 binding follows
its spool onto the head, Group 42; a Printer Pool slot feeds no one head), and
only a spool whose own record files it in that very slot (a deployed spool's
trail there is a ghost; an archived one waits for no load; a spool at a place
inside the box's id is not in the box). Slots compare in one form ("04" is 4).
The widget's half: tests/test_printer_status_waiting_tight_50.py.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app  # noqa: E402


def _display(s):
    """format_spool_display, offline: the slot from the spool's own record."""
    extra = s.get('extra') or {}
    return {'text': f"#{s['id']} Test", 'color': '336699', 'color_direction': 'longitudinal',
            'slot': str(extra.get('container_slot', '')).strip('"'), 'details': {}}


PRINTER_MAP = {
    'ZX-1': {'printer_name': 'ZZ XL', 'position': 0},
    'ZX-2': {'printer_name': 'ZZ XL', 'position': 1},
    'ZX-3': {'printer_name': 'ZZ XL', 'position': 2},
    'ZX-4': {'printer_name': 'ZZ XL', 'position': 3},
}
BINDINGS = {
    'ZX-1': [{'box': 'ZZ-BOX-A', 'slot': '1'}, {'box': 'ZZ-BOX-B', 'slot': '4'}, {'box': 'ZZ-BOX-A', 'slot': '3'}],
    'ZX-2': [{'box': 'ZZ-BOX-A', 'slot': '2'}],
    'ZX-3': [{'box': 'ZZ-PD-1', 'slot': '1', 'single_slot': True}],
    'ZX-4': [],
}


def _spool(sid, location, slot='', archived=False, **extra):
    e = dict(extra)
    if slot != '':
        e['container_slot'] = f'"{slot}"'
    return {'id': sid, 'location': location, 'extra': e, 'remaining_weight': 500, 'archived': archived}


SPOOLS = [
    _spool(57, 'ZX-1', physical_source='ZZ-BOX-A', physical_source_slot='1'),   # loaded from slot 1: a ghost there
    _spool(88, 'ZX-2'),                                                         # loaded on ZX-2
    _spool(93, 'ZZ-BOX-A', '2'),                                                # stored for ZX-2: waits
    _spool(74, 'ZZ-BOX-B', '04'),                                               # stored for ZX-1 ("04" is slot 4): waits
    _spool(71, 'ZZ-BOX-A', '3', archived=True),                                 # archived: waits for no load
    _spool(70, 'ZZ-PD-1', '1'),                                                 # a single-slot box's own spool
    _spool(75, 'ZZ-BOX-A-SUB', '2'),                                            # inside the box's id, not in the box
    _spool(76, 'ZZ-BOX-A'),                                                     # in the box, no slot
    _spool(77, 'ZZ-BOX-A', '5'),                                                # a slot that feeds no head here
]


class _TickList:
    """The pulse's SpoolListRead: the tick's one list."""
    def __init__(self, spools):
        self._spools = spools

    def get(self):
        return self._spools


def _run(spools=None, get_all=None):
    reads = []

    def _get_all(*a, **k):
        reads.append((a, k))
        return SPOOLS if get_all is None else get_all

    ctx = [
        patch.object(app.config_loader, 'load_config', return_value={'printer_map': PRINTER_MAP}),
        patch.object(app.locations_db, 'load_locations_list', return_value=[]),
        patch.object(app.locations_db, 'get_active_printer_map', return_value=PRINTER_MAP),
        patch.object(app.locations_db, 'printer_owning_toolhead', return_value='ZZXL'),
        patch.object(app.config_loader, 'get_api_urls', return_value=('http://sm', 'http://fb')),
        patch.object(app.prusalink_api, 'get_printer_state', return_value=None),
        patch.object(app.locations_db, 'get_bindings_for_machine',
                     return_value={'printer_name': 'ZZ XL', 'toolheads': BINDINGS, 'printer_pool': []}),
        patch.object(app.spoolman_api, 'get_all_spools', _get_all),
        patch.object(app.spoolman_api, 'format_spool_display', side_effect=_display),
    ]
    for m in ctx:
        m.start()
    try:
        out = app._pulse_section_printer_status(spools=spools)
    finally:
        for m in reversed(ctx):
            m.stop()
    return {t['id']: t for t in out['ZZ XL']['toolheads']}, reads


def test_a_spool_stored_for_a_head_and_not_loaded_waits():
    heads, _reads = _run(spools=_TickList(SPOOLS))
    assert heads['ZX-2']['waiting'] == [{'id': 93, 'display': '#93 Test', 'box': 'ZZ-BOX-A', 'slot': '2'}]
    assert heads['ZX-2']['item']['id'] == 88              # what it runs is unchanged
    assert heads['ZX-1']['waiting'] == [{'id': 74, 'display': '#74 Test', 'box': 'ZZ-BOX-B', 'slot': '4'}]


def test_nothing_else_waits():
    """The deployed spool's trail (a ghost), an archived spool, a single-slot
    box's own spool, a place inside the box's id, a spool with no slot, a slot
    that feeds no head here, a head with no feed: no `waiting` key at all."""
    heads, _reads = _run(spools=_TickList(SPOOLS))
    assert 'waiting' not in heads['ZX-3'] and 'waiting' not in heads['ZX-4']
    ids = {w['id'] for th in heads.values() for w in th.get('waiting', [])}
    assert ids == {93, 74}, ids


def test_it_reads_nothing_of_its_own():
    """With the tick's shared list, no Spoolman read at all; without one (an
    older caller), the one read the heads already made."""
    heads, reads = _run(spools=_TickList(SPOOLS))
    assert reads == [] and heads['ZX-2']['waiting'][0]['id'] == 93
    heads, reads = _run(spools=None)
    assert len(reads) == 1 and heads['ZX-2']['waiting'][0]['id'] == 93


def test_a_failed_read_waits_for_nothing():
    """The tick's read failed (its get() answers None): every head empty, as
    before (the widget keeps its tiles, reads-1), and nothing waits."""
    heads, reads = _run(spools=_TickList(None))
    assert reads == [] and all('waiting' not in th and th['item'] is None for th in heads.values())
