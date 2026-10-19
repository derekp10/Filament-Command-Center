"""Group 42.4 — a toolhead shows its one LOADED spool, and says so when FCC's
records put two on it.

Derek's principle (2026-09-13): "If looking at the toolhead, I should only ever
see one in there." The heartbeat's printer-status section picked the first item
per head, ghosts (a trail naming the head) included, so a stale trail could
stand in for the loaded spool, and a second loaded spool was invisible except in
the Location Manager list. Now the section prefers a loaded spool and reports
`loaded_count` (+ `loaded_ids` when above 1), and the tile and the head's view
say "⚠️ 2 spools" (tests/test_single_slot_lifecycle_js.py renders those).

Hermetic: the section's collaborators are patched on their defining modules.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402,F401  (route registration)
import routes_state_pulse  # noqa: E402

PRINTER_MAP = {"XL-1": {"printer_name": "XL", "position": 0},
               "XL-2": {"printer_name": "XL", "position": 1}}


def _section(by_tid):
    with patch.object(routes_state_pulse.locations_db, "get_active_printer_map", return_value=PRINTER_MAP), \
         patch.object(routes_state_pulse.config_loader, "load_config", return_value={}), \
         patch.object(routes_state_pulse.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(routes_state_pulse.spoolman_api, "bucket_spools_by_location", return_value=by_tid), \
         patch.object(routes_state_pulse.locations_db, "get_bindings_for_machine", return_value={"toolheads": {}}), \
         patch.object(routes_state_pulse.prusalink_api, "get_printer_state", return_value=None):
        out = routes_state_pulse._pulse_section_printer_status()
    return {th["id"]: th for th in out["XL"]["toolheads"]}


def test_the_loaded_spool_wins_over_a_ghost_listed_first():
    ghost = {"id": 7, "location": "XL-1", "is_ghost": True}
    loaded = {"id": 42, "location": "XL-1", "is_ghost": False}
    th = _section({"XL-1": [ghost, loaded]})["XL-1"]
    assert th["item"]["id"] == 42 and th["loaded_count"] == 1
    assert "loaded_ids" not in th


def test_a_doubled_head_reports_both_spools():
    th = _section({"XL-2": [{"id": 42, "location": "XL-2", "is_ghost": False},
                            {"id": 50, "location": "XL-2", "is_ghost": False}]})["XL-2"]
    assert th["item"]["id"] == 42 and th["loaded_count"] == 2 and th["loaded_ids"] == [42, 50]


def test_a_ghost_alone_still_shows_and_an_empty_head_is_empty():
    heads = _section({"XL-1": [{"id": 7, "location": "XL-1", "is_ghost": True}]})
    assert heads["XL-1"]["item"]["id"] == 7 and heads["XL-1"]["loaded_count"] == 0
    assert heads["XL-2"]["item"] is None and heads["XL-2"]["loaded_count"] == 0
