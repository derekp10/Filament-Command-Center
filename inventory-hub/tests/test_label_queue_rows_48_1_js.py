"""Group 48.1 — the label queue draws every row like the backlog, under node's
`vm` (no browser): the REAL inv_queue.js with canned answers.

Derek, 2026-10-08: "Just listing a spool id doesn't tell me what color it is."
Each spool / filament row is a swatch + "Brand - Material - Color" + its #id,
read live when the queue window opens (ONE /api/spools/refresh for the spools,
one /api/filament_details per filament); a location row is "LOC — Name"; a
failed read keeps the stored text with its leading "#id" stripped; every piece
of text is escaped; a redraw (a removal, the 2 s server poll) reads only labels
it doesn't know yet.

Base proof (52741e6): every test fails there (rows were "#57 - Spool #57").
"""
from __future__ import annotations

import json
from pathlib import Path

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

MODULES = ["inv_core.js", "inv_queue.js"]
JS = Path(__file__).resolve().parent.parent / "static" / "js" / "modules"

QUEUE = [
    {"id": 57, "type": "spool", "display": "Spool #57"},
    {"id": 12, "type": "filament", "display": "Filament #12"},
    {"id": "CR-CT-2-R1", "type": "location", "display": "Location: CR-CT-2-R1"},
    {"id": 58, "type": "spool", "display": "#58 Prusament PLA (Galaxy Black)"},
]
SPOOLS = {"57": {"color": "ff0000", "color_direction": "longitudinal",
                 "details": {"brand": "Prusament", "material": "Matte PLA", "color_name": "Lipstick Red"}}}
FILAMENT = {"id": 12, "name": "Jet Black", "material": "PETG", "vendor": {"name": "Prusament"}, "color_hex": "111111"}


def _run(tmp_path, body, spools=None, filament=None, queue=None):
    res = run_js(tmp_path, MODULES, f"""
window.labelQueue.length = 0;
{json.dumps(queue or QUEUE)}.forEach(i => window.labelQueue.push(i));
state.allLocations = [{{ LocationID: 'CR-CT-2-R1', Name: 'Cart row 1' }}];
const SPOOLS = {json.dumps(SPOOLS if spools is None else spools)};
const FILAMENT = {json.dumps(FILAMENT if filament is None else filament)};
window.__respond = (url) => {{
  if (url === '/api/spools/refresh') return SPOOLS === 'fail' ? {{ status: 502, body: {{}} }} : {{ body: SPOOLS }};
  if (url.startsWith('/api/filament_details')) return FILAMENT === 'fail' ? {{ status: 502, body: {{}} }} : {{ body: FILAMENT }};
  return null;
}};
const list = () => document.getElementById('queue-list-items').innerHTML;
const refreshes = () => __rec.fetches.filter(f => f.url === '/api/spools/refresh');
const filamentReads = () => __rec.fetches.filter(f => f.url.startsWith('/api/filament_details'));
{body}
""")
    assert res["unhandled"] == [], res["unhandled"]
    return res


def test_rows_read_like_the_backlog_once_the_live_data_lands(tmp_path):
    res = _run(tmp_path, """
window.openQueueModal();
const first = list();
await __settle(150);
return { first, after: list(), refreshes: refreshes().map(f => f.body), filamentReads: filamentReads().map(f => f.url),
         red: window.getFilamentStyle('ff0000', 'longitudinal').frame };
""")
    after = res["after"]
    assert "Prusament - Matte PLA - Lipstick Red" in after, after
    assert "#57" in after and "fcc-queue-swatch" in after and res["red"] in after, (res["red"], after)
    assert "Prusament - PETG - Jet Black" in after and "#12" in after, after
    assert "CR-CT-2-R1 — Cart row 1" in after, after
    # #58 was not in the live answer: its stored text, the leading "#58" stripped.
    assert "Prusament PLA (Galaxy Black)" in after and "#58 Prusament" not in after, after
    assert res["refreshes"] == [{"spools": [57, 58]}], res["refreshes"]
    assert res["filamentReads"] == ["/api/filament_details?id=12"], res["filamentReads"]
    # Drawn at once from what was stored, before any answer.
    assert "Spool #57" in res["first"] and "CR-CT-2-R1" in res["first"], res["first"]


def test_a_failed_read_keeps_the_stored_text(tmp_path):
    res = _run(tmp_path, """
window.openQueueModal();
await __settle(150);
return { after: list() };
""", spools="fail", filament="fail")
    after = res["after"]
    assert "Spool #57" in after and "Filament #12" in after, after
    assert "Prusament PLA (Galaxy Black)" in after and "fcc-queue-swatch" not in after, after


def test_every_piece_of_text_is_escaped(tmp_path):
    evil = '<img src=x onerror=alert(1)>'
    res = _run(tmp_path, """
window.openQueueModal();
await __settle(150);
return { after: list() };
""", spools={"57": {"color": "ff0000", "details": {"brand": "B", "material": "PLA", "color_name": evil}}},
        queue=[{"id": 57, "type": "spool", "display": evil}, {"id": 59, "type": "spool", "display": evil}])
    assert "<img" not in res["after"] and "&lt;img src=x onerror=alert(1)&gt;" in res["after"], res["after"]


def test_a_redraw_reads_only_what_it_does_not_know(tmp_path):
    res = _run(tmp_path, """
window.openQueueModal();
await __settle(150);
window.removeFromQueue(0);
await __settle(100);
const afterRemove = refreshes().length + filamentReads().length;
window.openQueueModal();
await __settle(150);
return { afterRemove, afterReopen: refreshes().length + filamentReads().length, rows: list() };
""")
    assert res["afterRemove"] == 2, res        # the open's one spool read + one filament read, nothing more
    assert res["afterReopen"] == 4, res        # opening again reads afresh
    assert "Lipstick Red" not in res["rows"], res  # #57 was removed


def test_the_location_managers_label_button_queues_once_per_click():
    """The card's 🖨️ LABEL carries its own onclick (ui_builder.js); the Location
    Manager also attached a click listener to it, queuing every click twice
    (hidden only by addToQueue's de-dup). One handler now."""
    loc_mgr = (JS / "inv_loc_mgr.js").read_text(encoding="utf-8")
    assert ".js-btn-label')" not in loc_mgr and '.js-btn-label")' not in loc_mgr
    builder = (JS / "ui_builder.js").read_text(encoding="utf-8")
    assert 'js-btn-label" onclick="${printHoverClick}"' in builder


def test_the_uncalled_quick_queue_helper_is_gone():
    assert "const quickQueue" not in (JS / "inv_details.js").read_text(encoding="utf-8")
