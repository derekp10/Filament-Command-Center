"""Group 40.6 — the browser half of Return's slot choice (Derek's D5 and his
2026-10-13 answer 6), its display (item D) and the DEPLOYED card's ↩️ (item E),
as hermetic JS checks under node's `vm` (the stub DOM of
test_core1_return_ejectall_js.py). inv_quickswap.js runs for real; the server's
answers, the printer check (window.checkPrinterForHead) and the slot picker
(window.openSlotPicker) are stubs answering what the server or the user would.
The server half is pinned in test_return_slot_choice.py.

Pinned here:
  - the confirm comes from the server's dry run and names the exact slot
    ("LR-MDB-1 slot 3 (original source)", "(the only free slot that feeds
    XL-2)", "no slot (LR-MDB-1 will show 3/4)"), and its Yes sends {toolhead,
    box, slot, expected_spool};
  - a plan that needs a choice opens the slot picker in return mode BEFORE the
    confirm; the printer is checked once, beside the dry run, and its banner is
    on the confirm; a pick is "(your choice)", No slot sends slot "none", and
    Escape sends nothing;
  - return_slot_taken (a slot taken meanwhile) reopens the picker with a 7 s
    warning, and the replay keeps the heads confirmed so far;
  - the toast is "↩️ #77 → LR-MDB-1 slot 3" or "↩️ #77 → LR-MDB-1 (no slot)",
    never "null";
  - a dry run the server refuses shows the no-op overlay (nothing to return,
    two spools, no binding) or a 7 s toast (another spool on the head);
  - item E: the DEPLOYED card's ↩️ runs the canonical Return for the head its
    spool is on, naming the spool; a stale trail falls back to doAssign on the
    spool's own box with autoDeploy off and its slot as a picked slot, never an
    Overwrite (Group 40.6 review, R1, which also pins a Room view's card);
  - the review's R2 (a no-binding answer's reason) and R3 (the reload answer
    meant for a page older than 40.6 is never toasted here);
  - the Printer view's head lookup skips a ghost (move-pipeline follow-ups
    item 6, test debt).

HEAD proof (0b0eeb7): see the commit message.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from pathlib import Path

import pytest

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

MODULES = Path(__file__).resolve().parent.parent / "static" / "js" / "modules"
QS = ["ui_builder.js", "inv_quickswap.js"]

PRELUDE = r"""
const LOCS = [
  { LocationID: 'XL', Name: 'XL', Type: 'Printer',
    toolheads: [{ location_id: 'XL-1', position: 0 }, { location_id: 'XL-2', position: 1 },
                { location_id: 'XL-3', position: 2 }] },
  { LocationID: 'XL-1', Name: 'XL-1', Type: 'Tool Head', 'Max Spools': '1' },
  { LocationID: 'XL-2', Name: 'XL-2', Type: 'Tool Head', 'Max Spools': '1' },
  { LocationID: 'XL-3', Name: 'XL-3', Type: 'Tool Head', 'Max Spools': '1' },
  { LocationID: 'LR-MDB-1', Name: 'LR box', Type: 'Dryer Box', 'Max Spools': '4',
    extra: { slot_targets: { '1': 'XL-1', '2': 'XL-2', '3': 'XL-3', '4': 'PRINTER:XL' } } },
  { LocationID: 'CR-CT-2-R1', Name: 'Cart row', Type: 'Cart Row', 'Max Spools': '0' },
];
state.allLocations = LOCS;
state.printerMap = { 'XL': [{ location_id: 'XL-1', position: 0 }, { location_id: 'XL-2', position: 1 },
                            { location_id: 'XL-3', position: 2 }] };
__rec.probes = [];
window.__printing = false;
window.checkPrinterForHead = (head) => {
  __rec.probes.push(head);
  return Promise.resolve(window.__printing
    ? { active: true, known: true, state: 'PRINTING', printer_name: 'XL' }
    : { active: false, known: true, state: 'IDLE', printer_name: 'XL' });
};
window.unionConfirmHeads = (prior, ans) => {
  const out = new Set((prior || []).map(h => String(h).toUpperCase()));
  (ans.active_prints || []).forEach(a => out.add(String(a.toolhead).toUpperCase()));
  return [...out];
};
window.__picks = [];
window.__pickerCalls = [];
window.openSlotPicker = (opts) => {
  window.__pickerCalls.push(Object.assign({}, opts, { host: !!opts.host, overlaysBefore: __rec.overlays.length }));
  const p = window.__picks.shift();
  return Promise.resolve(p === undefined ? null : p);
};
window.__refreshed = [];
window.refreshManageView = (id) => window.__refreshed.push(id);
window.__assigns = [];
window.doAssign = (...args) => window.__assigns.push(args);
window.__contents = {};
window.__plan = { body: {} };
window.__writes = [{ body: {} }];
let __w = 0;
window.__respond = (url, method, body) => {
  if (url.startsWith('/api/machine/')) return { status: 404, body: { toolheads: {} } };
  const gc = url.match(/^\/api\/get_contents\?id=(.+)$/);
  if (gc) return { body: window.__contents[decodeURIComponent(gc[1])] || [] };
  if (url === '/api/quickswap/return') {
    if (body && body.dry_run) return window.__plan;
    return window.__writes[Math.min(__w++, window.__writes.length - 1)];
  }
  return { body: [] };
};
const yes = async () => {
  const el = __overlayEls[__overlayEls.length - 1];
  const y = el ? el.querySelector('#fcc-quickswap-yes') : null;
  if (y && typeof y.onclick === 'function') y.onclick();
  await __settle(150);
};
const openHead = async (id) => {
  window.renderQuickSwapSection(LOCS.find(l => l.LocationID === id));
  await __settle();
  window.returnToolheadToSlot();
  await __settle(200);
};
const out = () => ({
  posts: __rec.fetches.filter(f => f.method === 'POST' && f.url === '/api/quickswap/return').map(f => f.body),
  overlays: __rec.overlays.map(o => o.content), toasts: __rec.toasts, logs: __rec.logs,
  picker: window.__pickerCalls, probes: __rec.probes, refreshed: window.__refreshed, assigns: window.__assigns,
});
"""


def _plan(**kw):
    base = {"action": "return_plan", "toolhead": "XL-3", "active_toolhead": "XL-3", "requested": "XL-3",
            "spool": 77, "display": "#77 Galaxy Black", "box": "LR-MDB-1", "slot": "3",
            "source": "physical_source", "needs_choice": False, "note": "",
            "occupancy": {"after": 1, "max": 4}, "options": None, "recommended": None}
    base.update(kw)
    return base


CHOOSE = _plan(slot=None, needs_choice=True, note="LR-MDB-1 slot 3, where it came from, holds #57",
               occupancy={"after": 3, "max": 4}, recommended={"kind": "slot", "box": "LR-MDB-1", "slot": "2"},
               options={"mode": "return", "location": "LR-MDB-1", "max_slots": 4, "slots": [], "unslotted": []})


def _done(slot, sid=77, source="physical_source"):
    return {"action": "return_done", "moved": sid, "toolhead": "XL-3", "box": "LR-MDB-1", "slot": slot,
            "source": source}


def _pick(slot):
    return {"kind": "slot", "box": "LR-MDB-1", "slot": slot, "free": True, "send": {"picked_slot": slot},
            "expected_feed": "", "choice": None, "swap": False, "displaced": None}


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def _run(tmp_path, body, plan=None, writes=(), picks=(), printing=False, contents=None):
    setup = (f"window.__plan = {json.dumps(plan or {'body': {}})};\n"
             f"window.__writes = {json.dumps(list(writes) or [{'body': {}}])};\n"
             f"window.__picks = {json.dumps(list(picks))};\n"
             f"window.__printing = {json.dumps(printing)};\n"
             f"window.__contents = {json.dumps(contents or {})};\n")
    res = run_js(tmp_path, QS, PRELUDE + setup + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


RUN_HEAD = """
await openHead(__HEAD__);
const shown = __rec.overlays.map(o => o.content);
await yes();
return Object.assign(out(), { shown });
"""


def _head(tmp_path, head="XL-3", **kw):
    return _run(tmp_path, RUN_HEAD.replace("__HEAD__", json.dumps(head)), **kw)


# ---- the confirm names the slot the server will use ---------------------------------------------

def test_the_confirm_names_the_free_recorded_slot_and_the_yes_sends_it(tmp_path):
    res = _head(tmp_path, plan={"body": _plan()}, writes=[{"body": _done("3")}])
    assert res["posts"] == [{"toolhead": "XL-3", "dry_run": True},
                            {"toolhead": "XL-3", "box": "LR-MDB-1", "slot": "3", "expected_spool": 77,
                             "confirmed_toolheads": []}], res["posts"]
    shown = _text(res["shown"][0])
    assert "Return the spool on XL-3?" in shown and "Spool: #77 Galaxy Black" in shown, shown
    assert "Sending back to: LR-MDB-1 slot 3 (original source)" in shown, shown
    assert res["picker"] == [] and res["probes"] == ["XL-3"], res
    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [("↩️ #77 → LR-MDB-1 slot 3", "success")], res["toasts"]


def test_the_only_free_slot_feeding_the_head_is_named_with_why(tmp_path):
    """Derek's answer 6: one tap when the answer is obvious, and the confirm
    still names it."""
    plan = _plan(toolhead="XL-2", active_toolhead="XL-2", requested="XL-2", spool=42, display="#42", slot="2",
                 source="feed_slot", note="#42 has no recorded slot; LR-MDB-1 slot 2 is the only free slot that feeds XL-2")
    res = _head(tmp_path, "XL-2", plan={"body": plan}, writes=[{"body": _done("2", 42, "feed_slot")}])
    shown = _text(res["shown"][0])
    assert "Sending back to: LR-MDB-1 slot 2 (the only free slot that feeds XL-2)" in shown, shown
    assert "LR-MDB-1 slot 2 is the only free slot that feeds XL-2." in shown, shown
    assert res["posts"][1] == {"toolhead": "XL-2", "box": "LR-MDB-1", "slot": "2", "expected_spool": 42,
                               "confirmed_toolheads": []}, res["posts"]


def test_a_printing_head_is_checked_once_and_the_banners_yes_confirms_it(tmp_path):
    res = _head(tmp_path, plan={"body": _plan()}, writes=[{"body": _done("3")}], printing=True)
    assert "XL is PRINTING" in _text(res["shown"][0]), res["shown"]
    assert res["probes"] == ["XL-3"], res["probes"]
    assert res["posts"][1]["confirmed_toolheads"] == ["XL-3"], res["posts"]


# ---- no usable slot: the picker, then the confirm -------------------------------------------------

def test_a_plan_that_needs_a_choice_opens_the_picker_before_the_confirm(tmp_path):
    res = _head(tmp_path, plan={"body": CHOOSE}, writes=[{"body": _done("2", source="chosen")}],
                picks=[_pick("2")], printing=True)
    assert res["picker"] == [{"location": "LR-MDB-1", "spool": 77, "mode": "return", "toolhead": "XL-3",
                              "host": True, "overlaysBefore": 0}], res["picker"]
    shown = _text(res["shown"][0])
    assert "Sending back to: LR-MDB-1 slot 2 (your choice)" in shown and "XL is PRINTING" in shown, shown
    assert "where it came from, holds #57" not in shown   # the why was the picker's to show
    assert res["probes"] == ["XL-3"], res["probes"]
    assert res["posts"][1] == {"toolhead": "XL-3", "box": "LR-MDB-1", "slot": "2", "expected_spool": 77,
                               "confirmed_toolheads": ["XL-3"]}, res["posts"]
    assert [t["msg"] for t in res["toasts"]] == ["↩️ #77 → LR-MDB-1 slot 2"], res["toasts"]


def test_a_slow_printer_check_never_delays_the_picker_but_the_confirm_waits_for_it(tmp_path):
    """The printer check (up to 3 s for a printer that's off) starts beside the
    dry run: the picker opens as soon as the plan is in, and the confirm after
    the pick still shows the check's banner."""
    res = _run(tmp_path, """
let settled = false;
window.checkPrinterForHead = (head) => {
  __rec.probes.push(head);
  return new Promise(r => setTimeout(() => { settled = true;
    r({ active: true, known: true, state: 'PRINTING', printer_name: 'XL' }); }, 400));
};
const openPicker = window.openSlotPicker;
let settledAtPick = null;
window.openSlotPicker = (opts) => { settledAtPick = settled; return openPicker(opts); };
await openHead('XL-3');
const beforeCheck = __rec.overlays.length;
await __settle(500);
const shown = __rec.overlays.map(o => o.content);
await yes();
return Object.assign(out(), { settledAtPick, beforeCheck, shown });
""", plan={"body": CHOOSE}, writes=[{"body": _done("2", source="chosen")}], picks=[_pick("2")])
    assert res["settledAtPick"] is False, res
    assert res["beforeCheck"] == 0, "the confirm opened before the printer check answered"
    assert "XL is PRINTING" in _text(res["shown"][0]), res["shown"]
    assert res["probes"] == ["XL-3"] and res["posts"][1]["confirmed_toolheads"] == ["XL-3"], res


def test_no_slot_says_the_count_sends_none_and_never_toasts_null(tmp_path):
    res = _head(tmp_path, plan={"body": CHOOSE}, writes=[{"body": _done(None, source="chosen")}],
                picks=[{"kind": "none", "box": "LR-MDB-1"}])
    shown = _text(res["shown"][0])
    assert "Sending back to: LR-MDB-1 — no slot (LR-MDB-1 will show 3/4)" in shown, shown
    assert res["posts"][1]["slot"] == "none" and res["posts"][1]["box"] == "LR-MDB-1", res["posts"]
    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [("↩️ #77 → LR-MDB-1 (no slot)", "success")]
    assert not any("null" in t["msg"] for t in res["toasts"]), res["toasts"]


def test_escape_in_the_picker_moves_nothing(tmp_path):
    res = _head(tmp_path, plan={"body": CHOOSE}, writes=[{"body": _done("2")}], picks=[])
    assert res["posts"] == [{"toolhead": "XL-3", "dry_run": True}], res["posts"]
    assert res["overlays"] == [] and res["toasts"] == [], res
    assert any("no slot chosen — nothing moved" in lg["msg"] for lg in res["logs"]), res["logs"]


def test_a_slot_taken_meanwhile_reopens_the_picker_and_keeps_the_confirmed_heads(tmp_path):
    taken = {"action": "return_slot_taken", "toolhead": "XL-3", "active_toolhead": "XL-3", "requested": "XL-3",
             "spool": 77, "display": "#77", "box": "LR-MDB-1", "slot": "2", "taken_by": [58],
             "error": "LR-MDB-1 slot 2 holds #58 now, so nothing was moved",
             "options": CHOOSE["options"], "recommended": {"kind": "slot", "box": "LR-MDB-1", "slot": "4"}}
    res = _run(tmp_path, """
await openHead('XL-3');
await yes();
await yes();
return out();
""", plan={"body": CHOOSE}, writes=[{"status": 409, "body": taken}, {"body": _done("4", source="chosen")}],
        picks=[_pick("2"), _pick("4")], printing=True)
    assert len(res["picker"]) == 2, res["picker"]
    assert [p["slot"] for p in res["posts"][1:]] == ["2", "4"], res["posts"]
    assert [p["confirmed_toolheads"] for p in res["posts"][1:]] == [["XL-3"], ["XL-3"]], res["posts"]
    warn = [t for t in res["toasts"] if t["type"] == "warning"]
    assert warn and warn[0]["msg"] == "⚠️ LR-MDB-1 slot 2 holds #58 now, so nothing was moved — pick another slot"
    assert warn[0]["duration"] >= 7000, warn
    assert res["toasts"][-1]["msg"] == "↩️ #77 → LR-MDB-1 slot 4", res["toasts"]


# ---- the server refused the dry run ---------------------------------------------------------------

@pytest.mark.parametrize("answer, title, says", [
    ({"status": 404, "body": {"action": "return_no_spool", "toolhead": "XL-3", "candidates": ["XL-3"]}},
     "Nothing to return on XL-3", "No spool is loaded on XL-3"),
    ({"status": 409, "body": {"action": "return_ambiguous", "toolhead": "XL-3", "active_toolhead": "XL-3",
                              "requested": "XL-3", "spools": [42, 43], "error": "XL-3 holds 2 spools"}},
     "XL-3 holds 2 spools", "eject the wrong one first"),
    ({"status": 404, "body": {"action": "return_no_binding", "toolhead": "XL-3", "active_toolhead": "XL-3",
                              "requested": "XL-3"}},
     "Return the spool on XL-3?", "has no recorded source and no bound dryer box slot"),
], ids=["no_spool", "ambiguous", "no_binding"])
def test_a_refused_dry_run_shows_a_no_op_overlay(tmp_path, answer, title, says):
    res = _head(tmp_path, plan=answer)
    assert len(res["shown"]) == 1, res["shown"]
    shown = _text(res["shown"][0])
    assert shown.startswith(title) and says in shown, shown
    assert res["posts"] == [{"toolhead": "XL-3", "dry_run": True}], res["posts"]


def test_another_spool_on_the_head_is_a_7s_warning(tmp_path):
    msg = "XL-1 holds #43 now, not #42, so nothing was moved. Reopen XL-1 to see what is on it."
    res = _run(tmp_path, """
window.returnDeployedSpool('LR-MDB-1', 42, '1', 'XL-1');
await __settle(200);
return out();
""", plan={"status": 409, "body": {"action": "return_spool_mismatch", "toolhead": "XL-1", "active_toolhead": "XL-1",
                                    "requested": "XL-1", "spool": 43, "expected_spool": 42, "error": msg}})
    assert res["posts"] == [{"toolhead": "XL-1", "dry_run": True, "expected_spool": 42}], res["posts"]
    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [(f"⚠️ {msg}", "warning")], res["toasts"]
    assert res["toasts"][0]["duration"] >= 7000 and res["overlays"] == [], res
    assert res["refreshed"] == ["LR-MDB-1"], res["refreshed"]


# ---- item E: the DEPLOYED card's ↩️ ---------------------------------------------------------------

CARD = """
const ghost = { id: 42, display: '#42', color: 'ff0000', is_ghost: true, deployed_to: __DEPLOYED__, slot: '1' };
const html = window.SpoolCardBuilder.buildCard(ghost, __MODE__, { slotNum: 1, locId: 'LR-MDB-1' });
const call = (html.match(/returnDeployedSpool\\([^)]*\\)/) || [''])[0];
eval('window.' + call);
await __settle(200);
const shown = __rec.overlays.map(o => o.content);
await yes();
return Object.assign(out(), { call, shown });
"""

# A stale-trail ghost as /api/get_contents lists it (spoolman_api._build_location_match):
# `location` is its trail's box, `slot` its trail's slot, `deployed_to` where it really is
# (Group 40.6 review, R1: the card's ↩️ names that box, not the view).
STALE_GHOST = {"id": 60, "display": "#60", "color": "ff0000", "is_ghost": True, "location": "LR-MDB-1",
               "deployed_to": "CR-CT-2-R1", "slot": "1"}

GHOST_CARD = """
const html = window.SpoolCardBuilder.buildCard(__ITEM__, __MODE__, { slotNum: 1, locId: __VIEW__ });
const call = (html.match(/returnDeployedSpool\\([^)]*\\)/) || [''])[0];
eval('window.' + call);
await __settle(200);
const shown = __rec.overlays.map(o => o.content);
await yes();
return Object.assign(out(), { call, shown });
"""


def _card(tmp_path, item, mode, view, **kw):
    """Build `item`'s card in `mode` as the Location Manager does for the view
    `view`, and tap its ↩️."""
    return _run(tmp_path, GHOST_CARD.replace("__ITEM__", json.dumps(item)).replace("__MODE__", json.dumps(mode))
                .replace("__VIEW__", json.dumps(view)), **kw)


@pytest.mark.parametrize("mode", ["loc_grid", "loc_list"])
def test_the_deployed_cards_return_is_the_canonical_return_for_its_head(tmp_path, mode):
    plan = _plan(toolhead="XL-1", active_toolhead="XL-1", requested="XL-1", spool=42, display="#42", slot="1")
    res = _run(tmp_path, CARD.replace("__DEPLOYED__", json.dumps("XL-1")).replace("__MODE__", json.dumps(mode)),
               plan={"body": plan}, writes=[{"body": dict(_done("1", 42), toolhead="XL-1")}])
    assert res["call"].startswith("returnDeployedSpool('LR-MDB-1', 42, "), res["call"]
    assert res["posts"] == [{"toolhead": "XL-1", "dry_run": True, "expected_spool": 42},
                            {"toolhead": "XL-1", "box": "LR-MDB-1", "slot": "1", "expected_spool": 42,
                             "confirmed_toolheads": []}], res["posts"]
    assert "Sending back to: LR-MDB-1 slot 1 (original source)" in _text(res["shown"][0])
    assert res["assigns"] == [], res["assigns"]
    assert res["refreshed"] and set(res["refreshed"]) == {"LR-MDB-1"}, res["refreshed"]
    assert [t["msg"] for t in res["toasts"]] == ["↩️ #42 → LR-MDB-1 slot 1"], res["toasts"]


@pytest.mark.parametrize("mode", ["loc_grid", "loc_list"])
def test_a_stale_trails_return_puts_it_back_in_its_slot_without_a_load(tmp_path, mode):
    """The card's spool sits on a cart (a stale trail), not a head: the 40.3
    fallback, doAssign with autoDeploy off, and no Return request.

    Changed on purpose (Group 40.6 review, R1): it pinned
    ['LR-MDB-1', 42, 1, None, {autoDeploy: False}], an explicit slot, which
    the engine treats as an Overwrite (it unseated the slot's stored spool,
    unasked). The slot now goes as a picked slot, kept only while it is free
    (`pickedSlot`, slot null: the doAssign contract inv_loc_mgr.js gains), and
    the box is the spool's own, from the item the server lists (`location`, its
    trail), on both card types."""
    item = dict(STALE_GHOST, id=42)
    res = _card(tmp_path, item, mode, "LR-MDB-1")
    assert res["assigns"] == [["LR-MDB-1", 42, None, None, {"autoDeploy": False, "pickedSlot": "1"}]], \
        res["assigns"]
    assert res["posts"] == [], res["posts"]


# ---- Group 40.6 review (R1-R3): the browser half --------------------------------------------------
# Each test fails on 7976b72 (the review's base) unless its docstring calls it a guard.

def test_a_room_views_stale_trail_return_names_the_spools_own_box(tmp_path):
    """R1 (the review's card probe): the Room view (openManage('LR')) lists, by
    the flat prefix matcher, every spool deployed from an LR-* box. #60's
    record names LR-MDB-1 slot 1, but it sits on a cart. Its ↩️ now names
    LR-MDB-1, its own box, with the slot as a picked slot. 7976b72 named the
    VIEW: doAssign('LR', 60, '1', null, {autoDeploy: false}), an Overwrite of
    slot 1 across every LR-* box (test_return_round_trip pins the outcome)."""
    res = _card(tmp_path, STALE_GHOST, "loc_list", "LR")
    assert res["call"] == "returnDeployedSpool('LR-MDB-1', 60, '1', 'CR-CT-2-R1', 'LR')", res["call"]
    assert res["assigns"] == [["LR-MDB-1", 60, None, None, {"autoDeploy": False, "pickedSlot": "1"}]], \
        res["assigns"]
    assert res["posts"] == [], res["posts"]


def test_a_stale_trail_with_no_slot_lets_the_engine_pick_one(tmp_path):
    """R1: a trail with no slot recorded sends no slot at all (the engine's own
    pick, which never unseats anyone), never a blank slot."""
    res = _card(tmp_path, dict(STALE_GHOST, slot=""), "loc_list", "LR")
    assert res["assigns"] == [["LR-MDB-1", 60, None, None, {"autoDeploy": False}]], res["assigns"]


def test_a_room_views_deployed_card_returns_off_its_head_and_refreshes_the_room(tmp_path):
    """R1: the canonical Return from a Room view's card. The server decides
    where the spool goes; the card names its own box, and the view refreshed
    afterwards is the Room on screen (the trail box's refresh would be dropped
    while the Room is open). A guard for the refresh, which 7976b72 got right by
    naming the view as the box; red there on the call it pins."""
    plan = _plan(toolhead="XL-1", active_toolhead="XL-1", requested="XL-1", spool=42, display="#42", slot="1")
    item = dict(STALE_GHOST, id=42, display="#42", deployed_to="XL-1")
    res = _card(tmp_path, item, "loc_list", "LR", plan={"body": plan},
                writes=[{"body": dict(_done("1", 42), toolhead="XL-1")}])
    assert res["call"] == "returnDeployedSpool('LR-MDB-1', 42, '1', 'XL-1', 'LR')", res["call"]
    assert res["posts"] == [{"toolhead": "XL-1", "dry_run": True, "expected_spool": 42},
                            {"toolhead": "XL-1", "box": "LR-MDB-1", "slot": "1", "expected_spool": 42,
                             "confirmed_toolheads": []}], res["posts"]
    assert res["assigns"] == [] and set(res["refreshed"]) == {"LR"}, res


def test_a_no_binding_answer_with_a_reason_shows_the_reason(tmp_path):
    """R2: a box that feeds the head but has no slot count isn't offered; the
    server's answer says so (`msg`) and the no-op overlay shows it, instead of
    "no bound dryer box slot" while the box's Feeds show one."""
    msg = ("#42 has no recorded slot; LR-BOX-9 feeds XL-3 but has no slot count (Max Spools is blank), "
           "so Return can't pick a slot there: set its Max Spools to return spools there")
    res = _head(tmp_path, plan={"status": 404, "body": {"action": "return_no_binding", "toolhead": "XL-3",
                                                         "active_toolhead": "XL-3", "requested": "XL-3", "msg": msg}})
    assert len(res["shown"]) == 1, res["shown"]
    shown = html_lib.unescape(_text(res["shown"][0]))   # the overlay escapes it; a browser shows the text
    assert shown.startswith("Return the spool on XL-3?") and f"{msg} — nothing was moved." in shown, shown
    assert "no bound dryer box slot" not in shown, shown
    assert res["posts"] == [{"toolhead": "XL-3", "dry_run": True}], res["posts"]


def test_a_reload_answer_meant_for_an_old_page_is_never_toasted_here(tmp_path):
    """R3, a guard (passes on 7976b72): return_choose_slot now carries `error` /
    `msg` / `stale_page` for a page older than 40.6. This page dispatches on the
    action: it opens the picker again and toasts none of it."""
    reload_msg = ("LR-MDB-1 slot 3, where it came from, holds #57; no free slot feeds XL-3, so nothing was "
                  "moved: reload the page (Ctrl+F5) to choose a slot")
    choose = dict(CHOOSE, action="return_choose_slot", error=reload_msg, msg=reload_msg, stale_page=True)
    res = _run(tmp_path, """
await openHead('XL-3');
await yes();
await yes();
return out();
""", plan={"body": _plan()}, writes=[{"body": choose}, {"body": _done("2", source="chosen")}], picks=[_pick("2")])
    assert [p["slot"] for p in res["posts"][1:]] == ["3", "2"], res["posts"]
    assert len(res["picker"]) == 1, res["picker"]
    assert [t["msg"] for t in res["toasts"]] == ["↩️ #77 → LR-MDB-1 slot 2"], res["toasts"]


# ---- the Printer view's head lookup (move-pipeline follow-ups item 6) ----------------------------

def test_a_printer_view_return_skips_a_ghost_and_acts_on_the_loaded_head(tmp_path):
    """XL-1 lists only a ghost (a spool deployed elsewhere whose trail names
    XL-1): the Return acts on XL-2, which really holds a spool."""
    contents = {"XL-1": [{"id": 9, "display": "#9", "is_ghost": True, "location": "XL-1", "deployed_to": "XL-3"}],
                "XL-2": [{"id": 42, "display": "#42", "location": "XL-2", "slot": ""}]}
    plan = _plan(toolhead="XL-2", active_toolhead="XL-2", requested="XL-2", spool=42, display="#42", slot="2")
    res = _head(tmp_path, "XL", plan={"body": plan}, writes=[{"body": _done("2", 42)}], contents=contents)
    assert res["posts"][0] == {"toolhead": "XL-2", "dry_run": True}, res["posts"]
    shown = _text(res["shown"][0])
    assert "Return the spool on XL-2?" in shown and "virtual printer" in shown, shown


# ---- source canaries -----------------------------------------------------------------------------

def test_the_old_preview_and_the_null_toast_are_gone():
    src = (MODULES / "inv_quickswap.js").read_text(encoding="utf-8")
    assert "_resolveReturnDestination" not in src
    assert "SLOT:${body.slot}" not in src
    assert "window.returnDeployedSpool = " in src
