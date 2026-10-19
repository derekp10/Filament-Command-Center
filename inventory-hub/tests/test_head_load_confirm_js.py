"""Group 40.3 — the three-way "Load it instead / Just store it / Cancel"
question, its replays, and every door that shows it, as hermetic JS checks
under node's `vm` (the stub DOM of test_core1_return_ejectall_js.py).

The three-way is a mode of the one shared confirm (window.confirmActivePrint,
CLAUDE.md: never a new copy): Load it instead keeps the yes button's ids
(`.fcc-apc-yes` / a door's own), Cancel the no's, and Just store it adds
`.fcc-apc-store`. Pinned here:
  - an idle head_fed answer (active_print null, active_prints []) never shows
    "is PRINTING", "Continue Anyway" or "Continue?": the server's title / body;
  - the store button names the slot; each button answers once; with no store
    option only Load and Cancel remain, and Enter cancels;
  - Enter stores (Derek, 2026-10-14) unless a scan owns the Enter (in flight,
    or a slower scanner's buffered payload);
  - the scan QRs (CMD:CONFIRM loads, CMD:STORE stores, CMD:CANCEL cancels);
    a stale STORE QR posts nothing; a question on screen holds off every other
    scan, and CMD:CANCEL cancels it;
  - moveConfirmKind, and buildMoveReplay's bodies: the union of heads and
    confirm keys across rounds (active_print -> head_fed -> active_print), a
    sticky store, picked_slot only for a slot the engine picked, expected_feed,
    and the spools the question named;
  - each door's first request carries confirmed_fed_heads, and its replays the
    spec's fields: the slot scan, performContextAssign, the Location Manager
    (doAssign), the Quick-Swap deposit (ONE dialog when the head is fed), the
    DEPLOYED card's ↩️ (auto_deploy false) and the Location Manager ID field.

HEAD proof (run on 14c5bc5): window.confirmHeadLoad, buildMoveReplay,
askMoveConfirm, moveConfirmKind, unionConfirmFedHeads and the STORE QR don't
exist there, and its doors send no confirmed_fed_heads: 23 of these 24 fail.
The one that passes is the control
test_a_slot_scan_that_loads_with_no_question_shows_no_dialog (Derek's S1 / S2:
the browser adds no prompt when the server asks nothing).
"""
from __future__ import annotations

import json

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

FED_BODY = ("LR-MDB-1 slot 1 feeds XL-1, and XL-1 is running #99 (from PM-DB-2). "
            "Loading #57 sends #99 back to PM-DB-2.")
FED = {
    "status": "requires_confirm", "confirm_type": "head_fed",
    "fed_heads": [{"toolhead": "XL-1", "printer_name": "XL", "box": "LR-MDB-1", "slot": "1",
                   "resident": {"id": 99, "from": "PM-DB-2", "goes": "back to PM-DB-2"},
                   "residents": [{"id": 99, "from": "PM-DB-2", "goes": "back to PM-DB-2"}],
                   "confirm_key": "XL-1#99"}],
    "active_prints": [], "active_print": None, "can_store": True, "target_slot": "1", "spools": [57],
    "title": "Load #57 onto XL-1?", "body": FED_BODY, "msg": FED_BODY,
}
PRINTING_FEEDS = {
    "status": "requires_confirm", "confirm_type": "active_print", "can_store": True,
    "fed_heads": [], "target_slot": "1", "spools": [57],
    "active_print": {"toolhead": "XL-1", "printer_name": "XL", "state": "PRINTING"},
    "active_prints": [{"toolhead": "XL-1", "printer_name": "XL", "state": "PRINTING", "role": "feeds", "spools": [57]}],
    "title": "Load #57 onto XL-1?",
    "body": "XL is PRINTING. LR-MDB-1 slot 1 feeds XL-1, so this also loads #57 onto XL-1.",
    "msg": "XL is PRINTING. LR-MDB-1 slot 1 feeds XL-1, so this also loads #57 onto XL-1. Continue?",
}
LEAVING = dict(PRINTING_FEEDS, can_store=False, title=None, body=None,
               msg="#57 is loaded on XL-3. Moving it to LR-MDB-1 means FCC stops charging this print to it. Continue?",
               active_print={"toolhead": "XL-3", "printer_name": "XL", "state": "PRINTING"},
               active_prints=[{"toolhead": "XL-3", "printer_name": "XL", "state": "PRINTING",
                               "role": "source", "spools": [57]}])


def _slot(answer):
    """The identify_scan slot door's shape of an engine question."""
    if answer.get("status") != "requires_confirm":
        return answer
    out = {k: v for k, v in answer.items() if k != "status"}
    out.update(type="assignment", action="assignment_requires_confirm", location="LR-MDB-1", slot="1", moved=57)
    return out


SLOT_DONE = {"type": "assignment", "action": "assignment_done", "location": "LR-MDB-1", "slot": "1",
             "moved": 57, "remaining_buffer": 0}

PRELUDE = r"""
window.fetchT = (u, o) => window.fetch(u, o);
// The stub overlay has no panel and drops element listeners: keep both, so the
// real attachConfirmQRs registers its session and keydown handlers can be fired.
const __mounts = [];
const __stubMount = window.mountOverlay;
window.mountOverlay = (opts) => {
  const h = __stubMount(opts);
  h.panel = h.element;
  const ls = [];
  h.element.addEventListener = (t, fn) => ls.push([t, fn]);
  __mounts.push({ opts, el: h.element, ls });
  return h;
};
const lastMount = () => __mounts[__mounts.length - 1];
const btn = (sel) => lastMount().el.querySelector(sel);
const click = async (sel) => { const b = btn(sel); if (b && typeof b.onclick === 'function') b.onclick(); await __settle(120); };
const key = async (k, extra) => {
  const m = lastMount();
  m.ls.filter(([t]) => t === 'keydown').forEach(([, fn]) => fn(Object.assign(
    { key: k, shiftKey: false, preventDefault() {}, stopPropagation() {} }, extra || {})));
  await __settle(60);
};
const toasts = () => (document.getElementById('toast-container').children || [])
  .map(c => ({ msg: c.innerText, type: String(c.className).replace('toast-msg toast-', '') }));
const posts = (url) => __rec.fetches.filter(f => f.method === 'POST' && f.url === url).map(f => f.body);
const html = () => __rec.overlays.map(o => o.content);
const sidOf = () => Object.keys(window._fccActiveConfirms || {}).pop();
state.heldSpools = [{ id: 57, display: '#57' }];
state.allLocations = [
  { LocationID: 'XL', Name: 'XL', Type: 'Printer', toolheads: [{ location_id: 'XL-1', position: 0 }] },
  { LocationID: 'XL-1', Name: 'XL-1', Type: 'Tool Head', 'Max Spools': '1' },
  { LocationID: 'LR-MDB-1', Name: 'LR box', Type: 'Dryer Box', 'Max Spools': '4',
    extra: { slot_targets: { '1': 'XL-1' } } },
];
window.refreshManageView = () => {}; window.fetchLocations = () => {}; window.openSpoolDetails = () => {};
let __answers = [];
let __n = 0;
const answerWith = (url, list) => { __answers = list; __n = 0; window.__door = url; };
window.__respond = (url) => {
  if (url.startsWith('/api/printer_state/')) return { body: { known: true, is_active: false, state: 'IDLE', printer_name: 'XL' } };
  if (url === window.__door) return { body: __answers[Math.min(__n++, __answers.length - 1)] };
  if (window.__extra) { const r = window.__extra(url); if (r) return r; }
  return { body: [] };
};
"""

CORE = ["inv_core.js"]
SCAN = ["inv_core.js", "ui_builder.js", "inv_cmd.js"]
LM = ["inv_core.js", "ui_builder.js", "inv_loc_mgr.js"]
QS = ["inv_core.js", "ui_builder.js", "inv_quickswap.js"]


def _run(tmp_path, modules, body):
    res = run_js(tmp_path, modules, PRELUDE + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def _js(value):
    return json.dumps(value)


# ---- the dialog ----------------------------------------------------------------------------------

def test_an_idle_fed_answer_shows_the_servers_words_and_no_printing_banner(tmp_path):
    res = _run(tmp_path, CORE, f"""
window.confirmHeadLoad({{ answer: {_js(FED)}, onLoad() {{}}, onStore() {{}}, onCancel() {{}} }});
return {{ html: html().pop(), opts: lastMount().opts }};
""")
    h = res["html"]
    assert "Load #57 onto XL-1?" in h and FED_BODY in h
    for banned in ("is PRINTING", "Continue Anyway", "Continue?"):
        assert banned not in h, banned
    assert "Load it instead" in h and "Just store it in LR-MDB-1 slot 1" in h and ">Cancel<" in h
    assert "fcc-apc-yes" in h and "fcc-apc-store" in h and "fcc-apc-no" in h
    assert "Enter stores it" in h
    assert res["opts"]["tier"] == "confirm" and res["opts"]["initialFocus"] == ".fcc-apc-store"


def test_each_button_answers_once(tmp_path):
    res = _run(tmp_path, CORE, f"""
const out = {{}};
const open = () => {{ const calls = [];
  window.confirmHeadLoad({{ answer: {_js(FED)}, onLoad: () => calls.push('load'),
                            onStore: () => calls.push('store'), onCancel: () => calls.push('cancel') }});
  return calls; }};
let calls = open(); await click('.fcc-apc-store'); await click('.fcc-apc-store'); await click('.fcc-apc-yes');
out.store = calls.slice();
calls = open(); await click('.fcc-apc-yes'); await click('.fcc-apc-no'); out.load = calls.slice();
calls = open(); await click('.fcc-apc-no'); await click('.fcc-apc-yes'); out.cancel = calls.slice();
return out;
""")
    assert res["store"] == ["store"] and res["load"] == ["load"] and res["cancel"] == ["cancel"], res


def test_without_a_store_option_only_load_and_cancel_remain_and_enter_cancels(tmp_path):
    res = _run(tmp_path, CORE, f"""
const calls = [];
window.confirmHeadLoad({{ answer: {_js(dict(FED, can_store=False))}, onLoad: () => calls.push('load'),
                          onStore: () => calls.push('store'), onCancel: () => calls.push('cancel') }});
const h = html().pop();
document.activeElement = null;
await key('Enter');
return {{ html: h, calls, initialFocus: lastMount().opts.initialFocus }};
""")
    assert "Just store it" not in res["html"] and "Load it instead" in res["html"]
    assert "Enter cancels" in res["html"] and res["initialFocus"] == ".fcc-apc-no"
    assert res["calls"] == ["cancel"]


def test_a_printing_store_answer_uses_the_same_dialog_and_names_the_target_slot(tmp_path):
    answer = dict(PRINTING_FEEDS, target_slot="2", title="Load #57 onto XL-2?")
    res = _run(tmp_path, CORE, f"""
window.confirmHeadLoad({{ answer: {_js(answer)}, box: 'LR-MDB-1', onLoad() {{}}, onStore() {{}} }});
return {{ html: html().pop() }};
""")
    h = res["html"]
    assert "Load #57 onto XL-2?" in h and "Just store it in LR-MDB-1 slot 2" in h
    assert "XL is PRINTING. LR-MDB-1 slot 1 feeds XL-1" in h      # the server's body
    assert "Continue?" not in h and "Continue Anyway" not in h


def test_enter_stores_unless_a_scan_owns_the_enter(tmp_path):
    """Derek's answer 5: Enter = Just store it. A scan's terminating Enter (the
    'Scan to cancel' QR read at scanner speed, or by a slower scanner whose
    buffer holds a payload) must never store."""
    res = _run(tmp_path, CORE, f"""
const calls = [];
window.confirmHeadLoad({{ answer: {_js(FED)}, onLoad: () => calls.push('load'),
                          onStore: () => calls.push('store'), onCancel: () => calls.push('cancel') }});
document.activeElement = btn('.fcc-apc-store');
state.scanBuffer = 'CMD:CANCEL:x'; state.scanStartTime = Date.now();
await key('Enter');                           // a scan in flight: nothing
const inFlight = calls.slice();
state.scanBuffer = 'LOC:LR-MDB-1'; state.scanStartTime = Date.now() - 5000;
await key('Enter');                           // a slow scanner's payload: nothing
const slow = calls.slice();
state.scanBuffer = ''; state.scanStartTime = 0;
await key('Enter');                           // a human Enter: store
return {{ inFlight, slow, calls }};
""")
    assert res["inFlight"] == [] and res["slow"] == [], res
    assert res["calls"] == ["store"], res


def test_tab_and_arrows_cycle_the_three_buttons(tmp_path):
    res = _run(tmp_path, CORE, f"""
window.confirmHeadLoad({{ answer: {_js(FED)}, onLoad() {{}}, onStore() {{}}, onCancel() {{}} }});
const seen = [];
const focusOf = (sel) => {{ const b = btn(sel); b.focus = () => {{ document.activeElement = b; seen.push(sel); }}; }};
['.fcc-apc-yes', '.fcc-apc-store', '.fcc-apc-no'].forEach(focusOf);
document.activeElement = btn('.fcc-apc-store');
await key('Tab'); await key('Tab'); await key('ArrowRight'); await key('ArrowLeft', {{}}); await key('Tab', {{ shiftKey: true }});
return {{ seen }};
""")
    assert res["seen"] == [".fcc-apc-no", ".fcc-apc-yes", ".fcc-apc-store", ".fcc-apc-yes", ".fcc-apc-no"], res


def test_the_scan_qrs_load_store_and_cancel(tmp_path):
    res = _run(tmp_path, CORE, f"""
const out = {{}};
const open = (answer) => {{ const calls = [];
  window.confirmHeadLoad({{ answer, onLoad: () => calls.push('load'), onStore: () => calls.push('store'),
                            onCancel: () => calls.push('cancel') }});
  return calls; }};
let calls = open({_js(FED)}); out.storeRouted = window.routeConfirmScan('CMD:STORE:' + sidOf()); out.store = calls.slice();
calls = open({_js(FED)}); out.loadRouted = window.routeConfirmScan('CMD:CONFIRM:' + sidOf()); out.load = calls.slice();
calls = open({_js(FED)}); out.cancelRouted = window.routeConfirmScan('CMD:CANCEL:' + sidOf()); out.cancel = calls.slice();
calls = open({_js(dict(FED, can_store=False))});
out.noStoreRouted = window.routeConfirmScan('CMD:STORE:' + sidOf()); out.noStore = calls.slice();
out.staleRouted = window.routeConfirmScan('CMD:STORE:fcc-cqr-999-zz');
const row = (lastMount().el.children || []).map(c => c.innerHTML || '').join('');
return Object.assign(out, {{ rowWithoutStore: row }});
""")
    assert res["storeRouted"] is True and res["store"] == ["store"], res
    assert res["loadRouted"] is True and res["load"] == ["load"], res
    assert res["cancelRouted"] is True and res["cancel"] == ["cancel"], res
    assert res["noStoreRouted"] is True and res["noStore"] == [], res
    assert res["staleRouted"] is False
    assert "-store-qr" not in res["rowWithoutStore"] and "Scan to Load" in res["rowWithoutStore"]


def test_union_confirm_fed_heads_keeps_every_key(tmp_path):
    res = _run(tmp_path, CORE, """
const a1 = { fed_heads: [{ toolhead: 'XL-1', confirm_key: 'XL-1#1' }] };
const a2 = { fed_heads: [{ toolhead: 'XL-2', confirm_key: 'xl-2#7,9' }] };
const first = window.unionConfirmFedHeads([], a1);
const both = window.unionConfirmFedHeads(first, a2);
return { first, both, again: window.unionConfirmFedHeads(both, a1),
         none: window.unionConfirmFedHeads(both, { active_prints: [{ toolhead: 'XL-3' }] }),
         bad: window.unionConfirmFedHeads(null, null) };
""")
    assert res["first"] == ["XL-1#1"] and sorted(res["both"]) == ["XL-1#1", "XL-2#7,9"]
    assert sorted(res["again"]) == sorted(res["both"]) == sorted(res["none"]) and res["bad"] == []


# ---- what kind of question, and what a door sends back ---------------------------------------------

def test_move_confirm_kind(tmp_path):
    res = _run(tmp_path, CORE, f"""
const k = window.moveConfirmKind;
return {{
  fed: k({_js(FED)}), slotFed: k({_js(_slot(FED))}), printingStore: k({_js(PRINTING_FEEDS)}),
  printing: k({_js(LEAVING)}), legacy: k({{ status: 'requires_confirm', msg: 'x' }}),
  quickswap: k({{ action: 'quickswap_requires_confirm', msg: 'x' }}),
  feedChanged: k({{ status: 'requires_confirm', confirm_type: 'feed_changed' }}),
  odd: k({{ status: 'requires_confirm', confirm_type: 'something_new' }}),
  done: k({{ status: 'success' }}), nothing: k(null),
}};
""")
    assert res == {"fed": "head_load", "slotFed": "head_load", "printingStore": "head_load",
                   "printing": "active_print", "legacy": "active_print", "quickswap": "active_print",
                   "feedChanged": "head_load", "odd": "unknown", "done": None, "nothing": None,
                   "unhandled": []}, res


def test_replays_accumulate_both_lists_across_print_fed_print(tmp_path):
    """Spec 40.3 #4: an idle head_fed question then a print starting must not
    ping-pong between two dialogs: each Load sends the union of every answer's
    heads AND confirm keys, and keeps the feed the questions named."""
    res = _run(tmp_path, CORE, f"""
const original = {{ text: 'LOC:LR-MDB-1:SLOT:1', source: 'barcode', confirmed_toolheads: [], confirmed_fed_heads: [] }};
let prior = {{}};
const bodies = [];
for (const a of [{_js(_slot(PRINTING_FEEDS))}, {_js(_slot(FED))}, {_js(_slot(LEAVING))}]) {{
  const r = window.buildMoveReplay('slot_scan', original, a, 'load', prior);
  bodies.push(r.body); prior = r.prior;
}}
return {{ bodies }};
""")
    got = [(b["confirmed_toolheads"], b["confirmed_fed_heads"], b.get("expected_feed")) for b in res["bodies"]]
    assert got == [(["XL-1"], [], "XL-1"), (["XL-1"], ["XL-1#99"], "XL-1"),
                   (["XL-1", "XL-3"], ["XL-1#99"], "XL-1")], got
    for b in res["bodies"]:
        assert b["text"] == "LOC:LR-MDB-1:SLOT:1" and b["spool_id"] == 57 and "picked_slot" not in b
        assert "auto_deploy" not in b


def test_just_store_it_confirms_only_the_heads_it_does_not_load_and_stays_a_store(tmp_path):
    both = dict(PRINTING_FEEDS, active_prints=LEAVING["active_prints"] + PRINTING_FEEDS["active_prints"])
    res = _run(tmp_path, CORE, f"""
const original = {{ location: 'LR-MDB-1', spools: [57], slot: null, origin: 'buffer',
                   confirmed_toolheads: [], confirmed_fed_heads: [] }};
const first = window.buildMoveReplay('smart_move', original, {_js(both)}, 'store', {{}});
// A later yes / no about another printing head keeps the store.
const later = window.buildMoveReplay('smart_move', original, {_js(LEAVING)}, 'load', first.prior);
return {{ first: first.body, later: later.body, prior: first.prior }};
""")
    s = res["first"]
    assert s["auto_deploy"] is False and s["picked_slot"] == "1" and s["spools"] == [57]
    assert s["confirmed_toolheads"] == ["XL-3"], s          # XL-1 is the head it does NOT load
    assert s["confirmed_fed_heads"] == [] and s["expected_feed"] == "XL-1"
    assert res["later"]["auto_deploy"] is False and res["later"]["picked_slot"] == "1"
    assert res["prior"]["store"] is True


def test_the_replay_names_the_picked_slot_only_for_a_slot_the_engine_picked(tmp_path):
    res = _run(tmp_path, CORE, f"""
const b = window.buildMoveReplay;
const slotless = {{ action: 'add', location: 'LR-MDB-1', spool_id: 57, slot: null, confirmed_toolheads: [], confirmed_fed_heads: [] }};
const named = Object.assign({{}}, slotless, {{ slot: '3' }});
const fed = {_js(FED)};
return {{
  slotless: b('manage_add', slotless, fed, 'load', {{}}).body,
  named: b('manage_add', named, fed, 'load', {{}}).body,
  scan: b('slot_scan', {{ text: 'LOC:LR-MDB-1:SLOT:1' }}, fed, 'load', {{}}).body,
  pickedFlag: b('manage_add', named, Object.assign({{}}, fed, {{ slot_picked: true, target_slot: '2' }}), 'load', {{}}).body,
  notPicked: b('manage_add', slotless, Object.assign({{}}, fed, {{ slot_picked: false }}), 'load', {{}}).body,
  feedToken: b('manage_add', slotless, Object.assign({{}}, fed, {{ feed: '' }}), 'load', {{}}).body,
}};
""")
    assert res["slotless"]["picked_slot"] == "1" and res["slotless"]["spool_id"] == 57
    assert "picked_slot" not in res["named"] and res["named"]["slot"] == "3"
    assert "picked_slot" not in res["scan"] and res["scan"]["spool_id"] == 57
    assert res["pickedFlag"]["picked_slot"] == "2"
    assert "picked_slot" not in res["notPicked"]
    # A server that states the feed is believed, "" (no toolhead) included.
    assert res["feedToken"]["expected_feed"] == "" and res["slotless"]["expected_feed"] == "XL-1"


# ---- the doors ----------------------------------------------------------------------------------------

def test_a_slot_scan_onto_a_fed_head_asks_the_three_way_and_load_replays_the_spec_fields(tmp_path):
    res = _run(tmp_path, SCAN, f"""
answerWith('/api/identify_scan', [{_js(_slot(FED))}, {_js(SLOT_DONE)}]);
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(150);
const shown = html().pop();
await click('.fcc-apc-yes');   // the stub DOM fakes one element per selector
return {{ posts: posts('/api/identify_scan'), shown, toasts: toasts(), ids: lastMount().opts.id }};
""")
    first, load = res["posts"]
    assert first == {"text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "confirmed_fed_heads": []}, first
    assert "expected_feed" not in first     # a blind scan names no feed: S1 stays prompt-free
    assert "is PRINTING" not in res["shown"] and "Continue Anyway" not in res["shown"]
    assert "Just store it in LR-MDB-1 slot 1" in res["shown"] and 'id="fcc-aps-store"' in res["shown"]
    assert res["ids"] == "fcc-active-print-scan-overlay"
    assert load == {"text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "confirmed_toolheads": [],
                    "confirmed_fed_heads": ["XL-1#99"], "expected_feed": "XL-1", "spool_id": 57}, load
    assert any("Loaded #57 into LR-MDB-1:1" in t["msg"] for t in res["toasts"]), res["toasts"]


def test_just_store_it_on_a_slot_scan_stores_and_says_so(tmp_path):
    res = _run(tmp_path, SCAN, f"""
answerWith('/api/identify_scan', [{_js(_slot(FED))}, {_js(SLOT_DONE)}]);
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(150);
await click('.fcc-apc-store');
return {{ posts: posts('/api/identify_scan'), toasts: toasts() }};
""")
    store = res["posts"][1]
    assert store["auto_deploy"] is False and store["confirmed_fed_heads"] == [] and store["spool_id"] == 57
    assert store["expected_feed"] == "XL-1" and store["confirmed_toolheads"] == []
    assert any(t["msg"] == "📦 #57 stored in LR-MDB-1 slot 1 — XL-1 left as it was" for t in res["toasts"]), res["toasts"]


def test_a_slot_scan_that_loads_with_no_question_shows_no_dialog(tmp_path):
    """Control (passes on HEAD too): Derek's S1 / S2 paths. The server decides
    the same-slot swap and the empty idle head; the browser adds no prompt."""
    res = _run(tmp_path, SCAN, f"""
answerWith('/api/identify_scan', [{_js(SLOT_DONE)}]);
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(150);
return {{ overlays: __rec.overlays.length, posts: posts('/api/identify_scan') }};
""")
    assert res["overlays"] == 0 and len(res["posts"]) == 1


def test_a_question_on_screen_holds_off_other_scans_and_cmd_cancel_cancels_it(tmp_path):
    res = _run(tmp_path, SCAN, f"""
answerWith('/api/identify_scan', [{_js(_slot(FED))}]);
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(150);
window.processScan('ID:99', 'barcode');
window.processScan('LOC:LR-MDB-1:SLOT:2', 'barcode');
await __settle(80);
const held = posts('/api/identify_scan').length;
const open = !!window._fccOpenMoveQuestion;
window.processScan('CMD:CANCEL', 'barcode');
await __settle(80);
return {{ held, open, after: !!window._fccOpenMoveQuestion, posts: posts('/api/identify_scan').length,
         toasts: toasts(), logs: posts('/api/log_event') }};
""")
    assert res["open"] is True and res["held"] == 1 and res["posts"] == 1, res
    assert res["after"] is False
    warn = [t for t in res["toasts"] if "Answer the question on screen first" in t["msg"]]
    assert len(warn) == 2 and all(t["type"] == "warning" for t in warn), res["toasts"]
    assert any(t["msg"] == "Cancelled — nothing moved" for t in res["toasts"]), res["toasts"]
    assert sum("ignored" in (lg.get("msg") or "") for lg in res["logs"]) == 2, res["logs"]


def test_a_stale_store_qr_posts_nothing(tmp_path):
    res = _run(tmp_path, SCAN, """
window.processScan('CMD:STORE:fcc-cqr-9-x', 'barcode');
await __settle(80);
return { posts: posts('/api/identify_scan'), toasts: toasts() };
""")
    assert res["posts"] == []
    assert any("belongs to a dialog that has closed" in t["msg"] and t["type"] == "warning" for t in res["toasts"])


def test_a_buffer_assign_into_a_box_replays_the_picked_slot_and_the_spools(tmp_path):
    res = _run(tmp_path, SCAN, f"""
answerWith('/api/smart_move', [{_js(FED)}, {{ status: 'success', failures: {{}} }}]);
performContextAssign('LR-MDB-1', null, [], [57]);
await __settle(150);
await click('.fcc-apc-yes');   // the stub DOM fakes one element per selector
return {{ posts: posts('/api/smart_move'), shown: html().pop() }};
""")
    first, load = res["posts"]
    assert first == {"location": "LR-MDB-1", "spools": [57], "slot": None, "origin": "buffer",
                     "confirmed_toolheads": [], "confirmed_fed_heads": []}, first
    assert load == {"location": "LR-MDB-1", "spools": [57], "slot": None, "origin": "buffer",
                    "confirmed_toolheads": [], "confirmed_fed_heads": ["XL-1#99"],
                    "picked_slot": "1", "expected_feed": "XL-1"}, load
    assert "Just store it in LR-MDB-1 slot 1" in res["shown"]


def test_a_location_manager_tap_onto_a_fed_head_asks_over_the_manager(tmp_path):
    res = _run(tmp_path, LM, f"""
answerWith('/api/manage_contents', [{_js(FED)}, {{ status: 'success', failures: {{}} }}]);
window.doAssign('LR-MDB-1', 57, 1, true);
await __settle(150);
const host = lastMount().opts.host === document.getElementById('manageModal');
await click('.fcc-apc-store');
return {{ posts: posts('/api/manage_contents'), host, toasts: toasts() }};
""")
    first, store = res["posts"]
    assert first == {"action": "add", "location": "LR-MDB-1", "spool_id": "ID:57", "slot": 1, "origin": "buffer",
                     "confirmed_toolheads": [], "confirmed_fed_heads": []}, first
    assert store["auto_deploy"] is False and store["slot"] == 1 and "picked_slot" not in store
    assert store["expected_feed"] == "XL-1" and store["confirmed_fed_heads"] == []
    assert res["host"] is True
    assert any(t["msg"] == "📦 #57 stored in LR-MDB-1 slot 1 — XL-1 left as it was" for t in res["toasts"])


def test_a_location_manager_head_assign_names_the_recorded_feed_slot(tmp_path):
    """Deferred note tests:lm-toolhead-recorded-source-toast: the toast mirrors
    the buffer scan's "#42 → XL-1 (recorded as from LR-MDB-1 slot 1)"."""
    res = _run(tmp_path, LM, """
answerWith('/api/manage_contents', [{ status: 'success', failures: {}, recorded_source: 'LR-MDB-1:1' }]);
window.doAssign('XL-1', 57, null, true);
await __settle(200);
return { toasts: toasts() };
""")
    assert any(t["msg"] == "#57 → XL-1 (recorded as from LR-MDB-1 slot 1)" for t in res["toasts"]), res["toasts"]


def test_the_deployed_cards_return_puts_the_spool_back_and_leaves_the_head(tmp_path):
    """Group 40.6, item E (deliberate): the card's ↩️ calls returnDeployedSpool
    (inv_quickswap.js) with the head the spool is loaded on, which runs the
    canonical Return for a toolhead (pinned in test_return_slot_choice_js.py).
    Its fallback for a stale trail is still this doAssign with autoDeploy off."""
    res = _run(tmp_path, LM, """
const ghost = { id: 57, display: '#57', color: 'ff0000', is_ghost: true, deployed_to: 'XL-1', slot: '1' };
const grid = window.SpoolCardBuilder.buildCard(ghost, 'loc_grid', { slotNum: 1, locId: 'LR-MDB-1' });
const list = window.SpoolCardBuilder.buildCard(ghost, 'loc_list', { locId: 'LR-MDB-1' });
answerWith('/api/manage_contents', [{ status: 'success', failures: {} }]);
window.doAssign('LR-MDB-1', 57, 1, null, { autoDeploy: false });
await __settle(150);
return { grid, list, posts: posts('/api/manage_contents'), toasts: toasts() };
""")
    assert "returnDeployedSpool('LR-MDB-1', 57, 1, 'XL-1')" in res["grid"], res["grid"]
    assert "returnDeployedSpool('LR-MDB-1', 57, '1', 'XL-1')" in res["list"], res["list"]
    assert "doAssign(" not in res["grid"] and "doAssign(" not in res["list"]
    assert res["posts"][0]["auto_deploy"] is False
    assert any(t["msg"] == "↩️ #57 → LR-MDB-1 slot 1" for t in res["toasts"]), res["toasts"]


def test_a_deposit_onto_a_fed_head_is_one_dialog_the_three_way(tmp_path):
    """Derek, 2026-10-14: one dialog. XL-1 runs #99, so FCC asks anyway: the
    deposit's own overlay is skipped and the server's three-way is the question."""
    res = _run(tmp_path, QS, f"""
window.__extra = (url) => url.startsWith('/api/get_contents?id=XL-1&strict=1')
  ? {{ body: [{{ id: 99, location: 'XL-1', is_ghost: false }}] }} : null;
answerWith('/api/identify_scan', [{_js(_slot(FED))}, {_js(SLOT_DONE)}]);
window.quickSwapDeposit({{ dataset: {{ box: 'LR-MDB-1', slot: '1', toolhead: 'XL-1' }} }});
await __settle(200);
const shown = html().slice();
await click('.fcc-apc-yes');
return {{ shown, posts: posts('/api/identify_scan') }};
""")
    assert len(res["shown"]) == 1 and "Load #57 onto XL-1?" in res["shown"][0], res["shown"]
    assert "fcc-quickswap-confirm" not in res["shown"][0]
    first, load = res["posts"]
    assert first == {"text": "LOC:LR-MDB-1:SLOT:1", "source": "quickswap_deposit", "confirmed_toolheads": [],
                     "confirmed_fed_heads": [], "spool_id": 57, "expected_feed": "XL-1"}, first
    assert load["confirmed_fed_heads"] == ["XL-1#99"] and load["spool_id"] == 57 and load["expected_feed"] == "XL-1"


def test_a_deposit_onto_an_empty_idle_head_keeps_its_own_confirm(tmp_path):
    """Control for the one-dialog rule: an idle, empty head asks nothing on the
    server, so the deposit's own confirm stays, and its Yes carries the keys."""
    res = _run(tmp_path, QS, f"""
answerWith('/api/identify_scan', [{_js(SLOT_DONE)}]);
window.quickSwapDeposit({{ dataset: {{ box: 'LR-MDB-1', slot: '1', toolhead: 'XL-1' }} }});
await __settle(200);
const shown = html().slice();
await click('#fcc-quickswap-yes');
return {{ shown, posts: posts('/api/identify_scan') }};
""")
    assert len(res["shown"]) == 1 and "fcc-quickswap-confirm-title" in res["shown"][0]
    assert res["posts"] == [{"text": "LOC:LR-MDB-1:SLOT:1", "source": "quickswap_deposit", "confirmed_toolheads": [],
                             "confirmed_fed_heads": [], "spool_id": 57, "expected_feed": "XL-1"}], res["posts"]


def test_a_typed_slot_label_in_the_manager_goes_through_the_scan_path(tmp_path):
    res = _run(tmp_path, ["inv_core.js", "ui_builder.js", "inv_cmd.js", "inv_loc_mgr.js"], f"""
answerWith('/api/identify_scan', [{_js(SLOT_DONE)}]);
document.getElementById('manual-spool-id').value = 'LOC:LR-MDB-1:SLOT:1';
window.manualAddSpool();
await __settle(150);
return {{ posts: posts('/api/identify_scan'), toasts: toasts() }};
""")
    assert res["posts"] == [{"text": "LOC:LR-MDB-1:SLOT:1", "source": "keyboard", "confirmed_fed_heads": []}]
    assert not any("Invalid Code" in t["msg"] for t in res["toasts"]), res["toasts"]
    assert any("Loaded #57 into LR-MDB-1:1" in t["msg"] for t in res["toasts"]), res["toasts"]
