"""Group 42, frontend half: hermetic checks of the real modules under node's
`vm` (the harness of test_core1_return_ejectall_js.py).

42.5a: the eject toast says where the spool went and which single-slot box let
go of the head, in Derek's short arrow form (2026-10-13: "short arrows for
toast. And a full sentence in the activity log"). It used to say "Ejected".
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

EJECT = """
state.allLocations = [
  { LocationID: 'PM-DB-2', Type: 'Dryer Box' },
  { LocationID: 'LR-MDB-1', Type: 'Dryer Box' },
  { LocationID: 'CR-CT-2-R1', Type: 'Cart Row' },
];
const answer = __ANSWER__;
window.__respond = (url) => (url === '/api/manage_contents' ? { body: answer } : { body: [] });
globalThis.fetchLocations = () => {};
window.doEject(__SID__, 'Scan');
await __settle(60);
return { toasts: __rec.toasts };
"""


def _ok(**kw):
    return {"success": True, "slot": "", "released_boxes": [], **kw}


@pytest.mark.parametrize("sid, answer, text", [
    (50, _ok(spool_id=50, **{"from": "XL-2"}, to="PM-DB-2", home=True, released_boxes=["PM-DB-2"]),
     "⏏️ #50 → back in PM-DB-2 (PM-DB-2 detached from XL-2)"),
    (134, _ok(spool_id=134, **{"from": "XL-3"}, to="LR-MDB-1", slot="3", home=True),
     "⏏️ #134 → back in LR-MDB-1 slot 3"),
    (50, _ok(spool_id=50, **{"from": "PM-DB-2"}, to="CR-CT-2-R1", home=True),
     "⏏️ #50 → back on CR-CT-2-R1"),
    (88, _ok(spool_id=88, **{"from": "CR-CT-2-R1"}, to="", home=False),
     "⏏️ #88 → Unassigned"),
    (60, _ok(spool_id=60, **{"from": "RCOI-1"}, to="CR", home=False),
     "⏏️ #60 → Room CR"),
    (7, {"success": True}, "Ejected"),   # an answer with no report (an older server)
], ids=["own-box-released", "box-slot", "cart-row", "unassigned", "room", "no-report"])
def test_the_eject_toast_says_where_it_went(tmp_path, sid, answer, text):
    res = run_js(tmp_path, ["inv_loc_mgr.js"],
                 EJECT.replace("__ANSWER__", json.dumps(answer)).replace("__SID__", str(sid)))
    assert res["unhandled"] == [], res
    assert [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]] == [(text, "success", 4000)], res


WEIGH = """
const answer = __ANSWER__;
window.__respond = (url) => (url === '/api/spool/update' ? { body: answer } : { body: {} });
window.saveSpoolWeight(77, null, { used_weight: 960 }, false);
await __settle(80);
return { toasts: __rec.toasts };
"""


@pytest.mark.parametrize("warning", [
    "#77 is back in stock (40 g), but XL-1 now holds #42, so it is Unassigned — scan it to where you put it.",
    None,
], ids=["redirected", "plain"])
def test_the_weigh_screen_toasts_an_unarchive_redirect_for_7_seconds(tmp_path, warning):
    """Group 42.3c: a used-up spool weighed back above 0 g whose old toolhead
    holds another spool now goes to Unassigned; the weigh screen says so."""
    answer = {"status": "success", "auto_archived": False, "needs_empty_weight_prompt": False}
    if warning:
        answer["warning"] = warning
    res = run_js(tmp_path, ["inv_weigh_out.js"], WEIGH.replace("__ANSWER__", json.dumps(answer)))
    assert res["unhandled"] == [], res
    toasts = [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]]
    assert toasts[0][0] == "Updated Spool #77", toasts
    assert toasts[1:] == ([(warning, "warning", 7000)] if warning else []), toasts


# --- 42.5b: a location label in eject mode -------------------------------------

SCAN = """
state.allLocations = [
  { LocationID: 'XL', Type: 'Printer', toolheads: [{ location_id: 'XL-1' }, { location_id: 'XL-2' }] },
  { LocationID: 'XL-2', Type: 'Tool Head', 'Max Spools': '1' },
  { LocationID: 'RCOI-1', Type: 'Tool Head', 'Max Spools': '1' },
  { LocationID: 'CORE1', Type: 'Printer', 'Max Spools': '1', toolheads: [{ location_id: 'CORE1' }] },
  { LocationID: 'PM-DB-4', Type: 'Dryer Box', 'Max Spools': '1', extra: { slot_targets: { '1': 'RCOI-1' } } },
  { LocationID: 'LR-MDB-1', Type: 'Dryer Box', 'Max Spools': '4' },
];
state.ejectMode = __EJECT__;
state.bulkMoveActive = __BULK__;
state.heldSpools = __BUFFER__;
const contents = __CONTENTS__;
const ejects = [];
window.doEject = (sid, loc) => { ejects.push([sid, loc]); };
window.closeManage = () => {};
globalThis.openManage = () => {};
window.__respond = (url) => (url === '/api/identify_scan'
  ? { body: { type: 'location', id: __ID__, contents } } : { body: { status: 'success' } });
processScan(__TEXT__, 'barcode');
await __settle(80);
return { ejects, buffer: state.heldSpools.map(s => s.id), toasts: __rec.toasts, logs: __rec.logs,
         posts: __rec.fetches.filter(f => f.method === 'POST').map(f => f.url) };
"""


def _scan(tmp_path, text, loc_id=None, contents=(), eject=True, bulk=False, buffer=()):
    res = run_js(tmp_path, ["inv_cmd.js"], (SCAN
                 .replace("__EJECT__", json.dumps(eject)).replace("__BULK__", json.dumps(bulk))
                 .replace("__BUFFER__", json.dumps([{"id": b, "display": f"#{b}"} for b in buffer]))
                 .replace("__CONTENTS__", json.dumps(list(contents)))
                 .replace("__ID__", json.dumps(loc_id or text.split(":")[1]))
                 .replace("__TEXT__", json.dumps(text))))
    assert res["unhandled"] == [], res
    return res


def _warnings(res):
    return [t["msg"] for t in res["toasts"] if t["type"] == "warning" and t["duration"] >= 7000]


def _loaded(sid, loc):
    return {"id": sid, "location": loc, "is_ghost": False, "slot": ""}


@pytest.mark.parametrize("head", ["RCOI-1", "CORE1"])
def test_eject_mode_toolhead_label_ejects_its_one_loaded_spool(tmp_path, head):
    """Derek's Q-B answer; the buffer is left alone (it used to be assigned to
    the head while eject mode stayed on)."""
    res = _scan(tmp_path, f"LOC:{head}", contents=[_loaded(60, head)], buffer=[88])
    assert res["ejects"] == [[60, head]], res
    assert res["buffer"] == [88] and "/api/smart_move" not in res["posts"], res
    assert _warnings(res) == [], res


def test_eject_mode_ignores_a_stale_trail_on_the_head(tmp_path):
    res = _scan(tmp_path, "LOC:XL-2", contents=[{"id": 7, "location": "XL-2", "is_ghost": True, "slot": ""}])
    assert res["ejects"] == [] and _warnings(res) == ["XL-2 is empty — nothing to eject."], res


def test_eject_mode_names_both_spools_on_a_doubled_head(tmp_path):
    res = _scan(tmp_path, "LOC:XL-2", contents=[_loaded(42, "XL-2"), _loaded(50, "XL-2")])
    assert res["ejects"] == [], res
    assert _warnings(res) == ["XL-2 holds #42 and #50 — scan the label of the one to eject."], res


def test_eject_mode_on_an_empty_head_says_its_polydryer_is_still_attached(tmp_path):
    res = _scan(tmp_path, "LOC:RCOI-1")
    assert _warnings(res) == ["RCOI-1 is empty — PM-DB-4 is still attached; open RCOI-1 to unbind it."], res


@pytest.mark.parametrize("label", ["LOC:LR-MDB-1", "LOC:XL"])
def test_eject_mode_on_a_box_or_printer_label_warns_and_does_nothing(tmp_path, label):
    res = _scan(tmp_path, label, contents=[_loaded(42, "XL-1")], buffer=[88])
    loc = label.split(":")[1]
    assert res["ejects"] == [] and res["buffer"] == [88], res
    assert _warnings(res) == [f"Eject mode: {loc} isn't a toolhead, so nothing was ejected. "
                              f"Scan a spool or a toolhead label, or turn eject mode off."], res
    assert [lg["level"] for lg in res["logs"]] == ["WARNING"], res


def test_eject_mode_stops_a_slot_label_before_the_server_loads_the_buffer(tmp_path):
    res = _scan(tmp_path, "LOC:LR-MDB-1:SLOT:2", loc_id="LR-MDB-1", buffer=[88])
    assert "/api/identify_scan" not in res["posts"], "the slot scan reached the server"
    assert res["buffer"] == [88]
    assert _warnings(res) == ["Eject mode: a slot label loads your buffer into LR-MDB-1 slot 2, so nothing "
                              "was loaded. Scan a spool or a toolhead label, or turn eject mode off."], res


def test_without_eject_mode_a_toolhead_label_still_assigns_the_buffer(tmp_path):
    """Control (passes on the old module too)."""
    res = _scan(tmp_path, "LOC:RCOI-1", contents=[], eject=False, buffer=[88])
    assert res["ejects"] == [] and "/api/smart_move" in res["posts"], res


def test_a_bulk_move_keeps_its_own_location_scans(tmp_path):
    res = _scan(tmp_path, "LOC:RCOI-1", contents=[_loaded(60, "RCOI-1")], bulk=True)
    assert res["ejects"] == [], res


# --- 42.4: "⚠️ 2 spools" on a doubled head --------------------------------------

DOUBLED_TEXT = "XL-2 holds #42 and #50 — a toolhead holds one spool. Open XL-2 and eject the one that isn't loaded."

WIDGET = """
window.makeSwatchHtml = () => '';
window.getFilamentStyle = () => ({ frame: '#333' });
const rows = { XL: { state: null, toolheads: [
  { id: 'XL-1', position: 0, unbound: false, loaded_count: 0, item: null },
  { id: 'XL-2', position: 1, unbound: false, loaded_count: __COUNT__, loaded_ids: __IDS__,
    item: { id: 42, color: 'ff0000', remaining_weight: 500, initial_weight: 1000, display: '#42' } },
] } };
window.refreshPrinterStatusWidgetFromAggregate(rows);
const w = document.getElementById('printer-status-widget');
return { body: w.querySelector('.fcc-ps-body').innerHTML, strip: w.querySelector('.fcc-ps-header-chips').innerHTML };
"""


def test_the_tile_and_the_strip_say_a_head_holds_two_spools(tmp_path):
    res = run_js(tmp_path, ["inv_printer_status.js"],
                 WIDGET.replace("__COUNT__", "2").replace("__IDS__", "[42, 50]"))
    assert res["unhandled"] == [], res
    assert "⚠️ 2 spools" in res["body"] and f'title="{DOUBLED_TEXT}"' in res["body"], res["body"]
    assert "background:#2b2200" in res["body"], "the chip needs an opaque background (contrast guard)"
    assert "⚠️2" in res["strip"] and DOUBLED_TEXT in res["strip"], res["strip"]


def test_one_loaded_spool_shows_no_warning(tmp_path):
    res = run_js(tmp_path, ["inv_printer_status.js"],
                 WIDGET.replace("__COUNT__", "1").replace("__IDS__", "undefined"))
    assert "spools" not in res["body"] and "⚠️" not in res["strip"], res


MANAGE = """
state.allLocations = [{ LocationID: 'XL-2', Type: 'Tool Head', 'Max Spools': '1' },
                      { LocationID: 'LR-MDB-1', Type: 'Dryer Box', 'Max Spools': '4' }];
const out = {};
for (const [key, loc, data] of __CASES__) {
    const el = window._doubledHeadBanner(data, loc);
    out[key] = el ? el.textContent : null;
}
return out;
"""


def test_a_doubled_heads_view_says_so_above_its_cards(tmp_path):
    """renderList puts this banner first (the full sweep renders it in a browser)."""
    two = [{"id": 42, "location": "XL-2", "is_ghost": False}, {"id": 50, "location": "XL-2", "is_ghost": False}]
    one = [two[0], {"id": 7, "location": "XL-2", "is_ghost": True}]
    cases = [["two", "XL-2", two], ["one", "XL-2", one], ["box", "LR-MDB-1",
             [{"id": 1, "location": "LR-MDB-1"}, {"id": 2, "location": "LR-MDB-1"}]]]
    res = run_js(tmp_path, ["inv_loc_mgr.js"], MANAGE.replace("__CASES__", json.dumps(cases)))
    assert res["unhandled"] == [], res
    assert res["two"] == f"⚠️ {DOUBLED_TEXT}", res
    assert res["one"] is None and res["box"] is None, res


# --- 42.5c: "attached — follows #50" on the toolhead's grid ------------------------

GRID = """
state.printerMap = { 'XL': [{ location_id: 'XL-2', position: 1 }] };
state.heldSpools = [];
window.SpoolCardBuilder = { buildCard: (it) => `CARD#${it.id}` };
window.makeSwatchHtml = () => '';
const pm = __CONTENTS__;
window.__respond = (url, method, body) => {
  if (url.startsWith('/api/machine/')) return { body: { toolheads: { 'XL-2': [
      { box: 'PM-DB-2', slot: '1', single_slot: true }, { box: 'LR-MDB-1', slot: '2' } ] }, printer_pool: [] } };
  if (url.startsWith('/api/get_contents?id=PM-DB-2')) return { body: pm };
  if (method === 'PUT') return { body: { success: true } };
  return { body: [] };
};
window.renderQuickSwapSection({ LocationID: 'XL-2', Type: 'Tool Head' });
await __settle(80);
const html = document.getElementById('quickswap-grid').innerHTML;
let put = null;
if (__CLICK__) {
  const btn = { getAttribute: (k) => ({ 'data-box': 'PM-DB-2', 'data-toolhead': 'XL-2' })[k] };
  window.quickSwapUnbindAttached(btn);
  await __settle(60);
  put = __rec.fetches.find(f => f.method === 'PUT') || null;
}
return { html, put, toasts: __rec.toasts };
"""


def _grid(tmp_path, contents, click=False):
    res = run_js(tmp_path, ["inv_quickswap.js"], GRID.replace("__CONTENTS__", json.dumps(contents))
                 .replace("__CLICK__", json.dumps(click)))
    assert res["unhandled"] == [], res
    return res


def test_an_attached_polydryer_says_which_spool_it_follows(tmp_path):
    """Its loaded spool, stored with a blank slot (a legacy row), still fills
    the box's tile (42.2) instead of the tile reading empty."""
    follower = {"id": 50, "is_ghost": True, "deployed_to": "XL-2", "location": "PM-DB-2", "slot": ""}
    html = _grid(tmp_path, [follower])["html"]
    assert "🔗 attached — follows #50" in html and "CARD#50" in html, html
    assert "fcc-qs-unbind" not in html


def test_a_stale_attachment_says_so_and_unbinds(tmp_path):
    res = _grid(tmp_path, [], click=True)
    assert "🔗 attached, but its spool isn't on XL-2" in res["html"] and "fcc-qs-unbind" in res["html"], res
    # It names the head it showed, so a box that moved meanwhile is refused (Group 42 review).
    assert res["put"]["url"] == "/api/dryer_box/PM-DB-2/bindings/1", res
    assert res["put"]["body"] == {"target": None, "expected_target": "XL-2"}, res
    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [("🔗✖ PM-DB-2 detached from XL-2", "success")]
