"""Group 41's adversarial review (2026-10-14), frontend half: hermetic checks of
the real modules under node's `vm` (the harness of test_core1_return_ejectall_js.py).

  - The Locations table hid ✏️ / 🗑️ by Type, which real rows share: a "Virtual
    Room / Zone" row, prod's blank-id "Unknown Location" row (whose 🗑️ is the
    only way to remove it, Group 46.5) and a blank-Type parent shown as
    "(Room)". It now hides them only on rows /api/locations marks Synthesized.
  - The delete prompt read the contents fail-open, so a Spoolman blip read as
    "It holds no spools." just before a delete that unassigned them. It now
    reads strictly and says when it couldn't read.
  - Every delete counts only the spools filed on the row itself, as the server
    now does for every type.

Each fails on the modules as of a1b2db7.
"""
from __future__ import annotations

import json
import re

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

RENDER = """
window.fetchT = (url, opts) => window.fetch(url, opts);
state.locSortBy = 'LocationID';
window._renderLocationsPayload(__ROWS__);
return { html: document.getElementById('location-table').innerHTML };
"""


def _buttons(tmp_path, rows) -> dict:
    """{LocationID: set of row buttons}, read from the rendered table."""
    res = run_js(tmp_path, ["inv_core.js"], RENDER.replace("__ROWS__", json.dumps(rows)))
    assert res["unhandled"] == [], res
    html = res["html"]
    out = {}
    for m in re.finditer(r'<tr data-locid="([^"]*)"(.*?)</tr>', html, re.S):
        out[m.group(1)] = {b for b in ("btn-edit", "btn-delete", "btn-manage") if b in m.group(2)}
    return out


def test_row_buttons_follow_the_synthesized_flag_not_the_type(tmp_path):
    rows = [
        {"LocationID": "Unassigned", "Name": "Workbench", "Type": "Virtual", "Synthesized": True},
        {"LocationID": "ZZ", "Name": "ZZ (Room)", "Type": "Virtual Room", "Synthesized": True},
        {"LocationID": "Shelf 9", "Name": "Shelf 9", "Type": "Spoolman Native", "Synthesized": True},
        {"LocationID": "UNKNOWN", "Name": "Unknown", "Type": "Unknown", "Synthesized": True},
        # Real rows that share those Types:
        {"LocationID": "GAR", "Name": "Garage", "Type": "Virtual Room"},
        {"LocationID": "", "Name": "Unknown Location", "Type": "Virtual Room"},
        {"LocationID": "LR-MDB-1", "Name": "Box", "Type": "Dryer Box"},
    ]
    b = _buttons(tmp_path, rows)
    assert b["UNASSIGNED"] == {"btn-manage"} and b["ZZ"] == {"btn-manage"}, b
    assert b["UNKNOWN"] == {"btn-manage"}, b
    # A Spoolman-native row keeps ✏️: saving it there makes it an FCC location.
    assert b["SHELF 9"] == {"btn-edit", "btn-manage"}, b
    assert b["GAR"] == {"btn-edit", "btn-delete", "btn-manage"}, b
    assert b[""] == {"btn-edit", "btn-delete", "btn-manage"}, b
    assert b["LR-MDB-1"] == {"btn-edit", "btn-delete", "btn-manage"}, b


PROMPT = """
state.allLocations = __ROWS__;
const answer = __ANSWER__;
window.__respond = (url, method) => {
    if (url.startsWith('/api/get_contents')) return answer;
    if (method === 'DELETE') return { body: { success: true, msg: 'Deleted.' } };
    return { body: [] };
};
globalThis.fetchLocations = () => {};
const confirms = [];
globalThis.requestConfirmation = (msg, cb) => { confirms.push(String(msg)); };
window.deleteLoc(__LOC__);
await __settle(60);
return { confirms, reads: __rec.fetches.filter(f => f.url.startsWith('/api/get_contents')).map(f => f.url) };
"""


def _prompt(tmp_path, loc, rows, answer) -> dict:
    res = run_js(tmp_path, ["inv_loc_mgr.js"], (PROMPT.replace("__ROWS__", json.dumps(rows))
                                                .replace("__ANSWER__", json.dumps(answer))
                                                .replace("__LOC__", json.dumps(loc))))
    assert res["unhandled"] == [], res
    return res


def test_the_delete_prompt_reads_strictly_and_says_when_it_couldnt(tmp_path):
    rows = [{"LocationID": "CR-CT-2-R1", "Type": "Cart Row"}]
    failed = {"status": 502, "body": {"error": "Couldn't read CR-CT-2-R1 from Spoolman."}}
    res = _prompt(tmp_path, "CR-CT-2-R1", rows, failed)
    assert res["reads"] == ["/api/get_contents?id=CR-CT-2-R1&strict=1"], res
    assert res["confirms"] == ["Delete CR-CT-2-R1? FCC couldn't read its spools from Spoolman just now, "
                               "so it can't say how many go to Unassigned."], res


def test_a_zones_prompt_counts_only_its_own_spools(tmp_path):
    """A "Virtual Room / Zone" counted every prefix hit, like any non-Room did."""
    rows = [{"LocationID": "GAR", "Type": "Virtual Room"}]
    contents = {"body": [{"id": 1, "location": "GAR"}, {"id": 2, "location": "GAR-X-9"}]}
    res = _prompt(tmp_path, "GAR", rows, contents)
    assert res["confirms"] == ["Delete GAR? Its spool #1 goes to Unassigned."], res
