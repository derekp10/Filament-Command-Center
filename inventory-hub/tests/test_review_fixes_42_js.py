"""Group 42 adversarial review (2026-10-14), frontend half: hermetic pins of the
real modules under node's `vm` (the harness of test_core1_return_ejectall_js.py),
each proven red on the branch before its fix.

  frontend-2      a failed read of a single-slot box showed its attachment as
                  stale and offered Unbind;
  frontend-3      an eject-mode toolhead label answered an unreadable head as empty;
  frontend-5      the doubled-head banner skipped a dual-role printer head (CORE1);
  frontend-6      Unbind sent no head, so the server couldn't refuse a moved box;
  data-safety-1   the deposit tile on a single-slot box promised an auto-deploy
                  that 42.2 removed;
  data-safety-3   Return's preview offered a PolyDryer's lifecycle binding;
  engine-guards-1 two spools claiming one slot showed one card while the server
                  moved the other.
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

# --- the Quick-Swap grid ------------------------------------------------------------

GRID = """
state.printerMap = { 'XL': [{ location_id: 'XL-2', position: 1 }] };
state.heldSpools = __BUFFER__;
window.SpoolCardBuilder = { buildCard: (it) => `CARD#${it.id}` };
window.makeSwatchHtml = () => '';
const answers = __ANSWERS__;
let machineReads = 0;
window.__respond = (url, method, body) => {
  if (url.startsWith('/api/machine/')) {
    machineReads += 1;
    return { body: { toolheads: { 'XL-2': __ENTRIES__ }, printer_pool: [] } };
  }
  for (const [prefix, a] of Object.entries(answers)) if (url.startsWith(prefix)) return a;
  return { body: [] };
};
window.renderQuickSwapSection({ LocationID: 'XL-2', Type: 'Tool Head' });
await __settle(80);
const html = document.getElementById('quickswap-grid').innerHTML;
let put = null;
if (__CLICK__) {
  const btn = { getAttribute: (k) => ({ 'data-box': 'PM-DB-2', 'data-toolhead': 'XL-2' })[k] };
  window.quickSwapUnbindAttached(btn);
  await __settle(80);
  put = __rec.fetches.find(f => f.method === 'PUT') || null;
}
if (__DEPOSIT__) {
  window.quickSwapDeposit({ dataset: { box: 'PM-DB-2', slot: '1', toolhead: 'XL-2', singleSlot: '1' } });
  await __settle(80);
}
return { html, put, machineReads, toasts: __rec.toasts, overlays: __rec.overlays.map(o => o.content),
         gets: __rec.fetches.filter(f => f.method === 'GET').map(f => f.url) };
"""

SINGLE = [{"box": "PM-DB-2", "slot": "1", "single_slot": True}]


def _grid(tmp_path, answers, entries=SINGLE, buffer=(), click=False, deposit=False):
    res = run_js(tmp_path, ["inv_quickswap.js"], (GRID
                 .replace("__ANSWERS__", json.dumps(answers))
                 .replace("__ENTRIES__", json.dumps(entries))
                 .replace("__BUFFER__", json.dumps([{"id": b, "display": f"#{b}"} for b in buffer]))
                 .replace("__CLICK__", json.dumps(click))
                 .replace("__DEPOSIT__", json.dumps(deposit))))
    assert res["unhandled"] == [], res
    return res


def test_an_unreadable_polydryer_is_not_offered_an_unbind(tmp_path):
    """frontend-2: a Spoolman blip read as "its spool isn't on XL-2", and Unbind
    then detached the box while its spool ran on the head."""
    res = _grid(tmp_path, {"/api/get_contents?id=PM-DB-2": {"status": 502, "body": {"error": "unreachable"}}},
                buffer=[88])
    assert "/api/get_contents?id=PM-DB-2&strict=1" in res["gets"], res["gets"]
    assert "couldn't read PM-DB-2 from Spoolman" in res["html"], res["html"]
    assert "fcc-qs-unbind" not in res["html"] and "isn't on XL-2" not in res["html"], res["html"]
    assert "quickSwapDeposit" not in res["html"], "a deposit tile on a box FCC couldn't read"


def test_unbind_names_the_head_it_showed(tmp_path):
    """frontend-6: the server refuses when the box is attached elsewhere by now."""
    res = _grid(tmp_path, {"/api/get_contents?id=PM-DB-2": {"body": []},
                           "/api/dryer_box/": {"body": {"slot_targets": {}}}}, click=True)
    assert res["put"]["body"] == {"target": None, "expected_target": "XL-2"}, res["put"]


def test_an_unbind_the_server_refuses_says_why_and_repaints(tmp_path):
    msg = "PM-DB-2 is attached to XL-4 now, not XL-2, so nothing was changed. Reopen XL-2 to see where it is."
    res = _grid(tmp_path, {"/api/get_contents?id=PM-DB-2": {"body": []},
                           "/api/dryer_box/": {"status": 409, "body": {"error": "binding_moved", "msg": msg}}},
                click=True)
    assert [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]] == [(f"❌ {msg}", "error", 7000)], res
    assert res["machineReads"] == 2, "the grid kept showing the stale Unbind"


def test_a_deposit_into_a_polydryer_promises_no_load(tmp_path):
    """data-safety-1: 42.2 stopped a single-slot box from auto-deploying, but its
    tile and confirm still said the spool would be loaded onto the head."""
    res = _grid(tmp_path, {"/api/get_contents?id=PM-DB-2": {"body": []}}, buffer=[88], deposit=True)
    assert 'data-single-slot="1"' in res["html"], res["html"]
    assert "auto-deploy" not in res["html"], res["html"]
    assert "Put the buffered spool in PM-DB-2 (it is not loaded onto XL-2)" in res["html"], res["html"]
    assert len(res["overlays"]) == 1, res
    body = res["overlays"][0]
    assert "auto-deploy" not in body and "goes back to its recorded source box" not in body, body
    assert "It is not loaded onto <b>XL-2</b>: PM-DB-2 is attached to XL-2" in body, body


def test_a_bound_slot_of_a_multi_slot_box_still_promises_its_deploy(tmp_path):
    """Control (passes before the fix too)."""
    res = _grid(tmp_path, {"/api/get_contents?id=LR-MDB-1": {"body": []}},
                entries=[{"box": "LR-MDB-1", "slot": "2"}], buffer=[88])
    assert "(auto-deploys to XL-2)" in res["html"] and "data-single-slot" not in res["html"], res["html"]


@pytest.mark.parametrize("entries, box", [(SINGLE, "PM-DB-2"), ([{"box": "LR-MDB-1", "slot": "1"}], "LR-MDB-1")],
                         ids=["single-slot", "multi-slot"])
def test_a_slot_two_spools_claim_shows_both_and_no_card(tmp_path, entries, box):
    """engine-guards-1: the grid kept the LAST item for a slot while the server
    moved the FIRST, so the user loaded one spool and FCC recorded the other."""
    contents = [{"id": 50, "is_ghost": True, "deployed_to": "XL-2", "location": box, "slot": "1"},
                {"id": 77, "is_ghost": False, "location": box, "slot": "1"}]
    res = _grid(tmp_path, {f"/api/get_contents?id={box}": {"body": contents}}, entries=entries)
    assert "CARD#" not in res["html"], res["html"]
    assert f"⚠️ #50 and #77 both claim slot 1 — open {box} to sort them" in res["html"], res["html"]


# --- the doubled-head banner -----------------------------------------------------------

def test_a_dual_role_printer_heads_view_shows_the_doubled_banner(tmp_path):
    """frontend-5: CORE1 is a Printer row whose only head is itself; its tile said
    "⚠️ 2 spools" while its view showed no banner."""
    scenario = """
    state.allLocations = [{ LocationID: 'CORE1', Type: 'Printer', 'Max Spools': '1',
                            toolheads: [{ location_id: 'CORE1' }] },
                          { LocationID: 'XL', Type: 'Printer', 'Max Spools': '0',
                            toolheads: [{ location_id: 'XL-1' }, { location_id: 'XL-2' }] }];
    const two = (loc) => [{ id: 42, location: loc, is_ghost: false }, { id: 50, location: loc, is_ghost: false }];
    const core = window._doubledHeadBanner(two('CORE1'), 'CORE1');
    const xl = window._doubledHeadBanner(two('XL'), 'XL');
    return { core: core ? core.textContent : null, xl: xl ? xl.textContent : null };
    """
    res = run_js(tmp_path, ["inv_loc_mgr.js"], scenario)
    assert res["unhandled"] == [], res
    assert res["core"] == ("⚠️ CORE1 holds #42 and #50 — a toolhead holds one spool. "
                           "Open CORE1 and eject the one that isn't loaded."), res
    assert res["xl"] is None, "XL holds any number of spools"


# --- a location scan that couldn't read the location ----------------------------------

SCAN = """
state.allLocations = [
  { LocationID: 'RCOI-1', Type: 'Tool Head', 'Max Spools': '1' },
  { LocationID: 'PM-DB-4', Type: 'Dryer Box', 'Max Spools': '1', extra: { slot_targets: { '1': 'RCOI-1' } } },
];
state.ejectMode = __EJECT__;
state.heldSpools = [];
const ejects = [];
const opened = [];
window.doEject = (sid, loc) => { ejects.push([sid, loc]); };
globalThis.openManage = (id) => { opened.push(id); };
window.__respond = (url) => (url === '/api/identify_scan'
  ? { body: { type: 'location', id: 'RCOI-1', contents: [],
              contents_error: "couldn't read RCOI-1 from Spoolman (unreachable)" } }
  : { body: { status: 'success' } });
processScan('LOC:RCOI-1', 'barcode');
await __settle(80);
return { ejects, opened, toasts: __rec.toasts, logs: __rec.logs };
"""


def test_eject_mode_says_it_could_not_read_the_head(tmp_path):
    """frontend-3: a Spoolman blip read as "RCOI-1 is empty — PM-DB-4 is still
    attached; open RCOI-1 to unbind it" about a loaded head."""
    res = run_js(tmp_path, ["inv_cmd.js"], SCAN.replace("__EJECT__", "true"))
    assert res["unhandled"] == [] and res["ejects"] == [], res
    assert [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]] == [
        ("Couldn't read RCOI-1 from Spoolman, so nothing was ejected. Scan it again in a moment.",
         "warning", 7000)], res


def test_a_location_scan_says_it_could_not_read_the_location(tmp_path):
    """Out of eject mode, the same answer said "📭 RCOI-1 is empty — no spools here"."""
    res = run_js(tmp_path, ["inv_cmd.js"], SCAN.replace("__EJECT__", "false"))
    assert res["unhandled"] == [] and res["opened"] == ["RCOI-1"], res
    assert [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]] == [
        ("Couldn't read RCOI-1 from Spoolman — opening it so you can check.", "warning", 7000)], res


# --- Return's preview skips a PolyDryer's lifecycle binding -------------------------

RETURN = """
const row = { LocationID: 'RCOI-1', Type: 'Tool Head', 'Max Spools': '1' };
state.allLocations = [row, { LocationID: 'PM-DB-4', Type: 'Dryer Box', 'Max Spools': '1' },
                      { LocationID: 'CR-CT-2-R1', Type: 'Cart Row', 'Max Spools': '0' }];
state.printerMap = { 'INDX': [{ location_id: 'RCOI-1', position: 0 }] };
window.__respond = (url) => {
  if (url.startsWith('/api/machine/')) return { status: 404, body: { toolheads: {} } };
  if (url === '/api/get_contents?id=RCOI-1') return { body: [{ id: 61, display: '#61', location: 'RCOI-1', slot: '' }] };
  if (url === '/api/spools/61') return { body: { success: true, data: { id: 61, location: 'RCOI-1',
      extra: { physical_source: '"CR-CT-2-R1"' } } } };
  if (url === '/api/dryer_boxes/slots') return { body: { slots: [
      { box: 'PM-DB-4', box_name: 'PM-DB-4', slot: '1', target: 'RCOI-1', single_slot: true }] } };
  if (url === '/api/quickswap/return') return { body: { action: 'return_done', moved: 61, box: 'PM-DB-4', slot: '1' } };
  return { body: [] };
};
window.renderQuickSwapSection(row);
await __settle();
window.returnToolheadToSlot();
await __settle(200);
const overlays = __rec.overlays.map(o => o.content);
const last = __overlayEls[__overlayEls.length - 1];
const yes = last ? last.querySelector('#fcc-quickswap-yes') : null;
if (yes && typeof yes.onclick === 'function') yes.onclick();
await __settle(100);
return { overlays, posts: __rec.fetches.filter(f => f.method === 'POST').map(f => f.url) };
"""


def test_returns_preview_never_offers_a_polydryer_binding(tmp_path):
    """data-safety-3: the server no longer falls back to a single-slot box's
    lifecycle binding, so the preview mustn't promise it either."""
    res = run_js(tmp_path, ["inv_quickswap.js"], RETURN)
    assert res["unhandled"] == [], res
    assert len(res["overlays"]) == 1, res
    assert "has no recorded source and no bound dryer box slot" in res["overlays"][0], res["overlays"]
    assert "PM-DB-4" not in res["overlays"][0]
    assert "/api/quickswap/return" not in res["posts"], res
