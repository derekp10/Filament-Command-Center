"""Group 39 review fixes, frontend half: hermetic JS checks under node's `vm`.

Runs the REAL frontend modules (inv_core.js, inv_quickswap.js, inv_cmd.js,
inv_loc_mgr.js) with the stub DOM + network of test_core1_return_ejectall_js.py,
so the confirm-replay contracts are proven without a browser or the container:

  - every replay sends the UNION of the heads confirmed so far (a regression to
    "only the newest heads" ping-pongs the user between two printing heads);
  - a Quick-Swap deposit the server asks about again shows the SERVER's message
    (it re-opened with its own text, so its Yes covered heads it never named);
  - a slot-scan replay that is asked again re-asks instead of toasting the
    question as a green success;
  - a Location Manager move off a printer head asks once, not twice;
  - the "Checking XL…" label names the printer before printerMap has loaded;
  - two taps during the Quick-Swap probe can't leak a page-wide keydown handler.

HEAD proof (the modules as of 8833329): the five fix pins fail there. The two
union tests pass there too: the review found that behaviour untested, not
broken, and they keep it from regressing.
"""
from __future__ import annotations

import json

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

XL = """
state.allLocations = [
  { LocationID: 'XL', Name: 'XL Test', Type: 'Printer',
    toolheads: [{ location_id: 'XL-1', position: 0 }, { location_id: 'XL-2', position: 1 },
                { location_id: 'XL-3', position: 2 }] },
  { LocationID: 'XL-1', Name: 'XL-1', Type: 'Tool Head', 'Max Spools': '1' },
  { LocationID: 'XL-2', Name: 'XL-2', Type: 'Tool Head', 'Max Spools': '1' },
  { LocationID: 'XL-3', Name: 'XL-3', Type: 'Tool Head', 'Max Spools': '1' },
  { LocationID: 'LR-MDB-1', Name: 'LR box', Type: 'Dryer Box', 'Max Spools': '4',
    extra: { slot_targets: { '3': 'XL-2' } } },
];
window.attachConfirmQRs = null;
// inv_core.js's fetchT needs AbortSignal; the stub fetch is enough here.
window.fetchT = (url, opts) => window.fetch(url, opts);
const printing = (name) => ({ body: { known: true, is_active: true, state: 'PRINTING', printer_name: name } });
const idle = (name) => ({ body: { known: true, is_active: false, state: 'IDLE', printer_name: name } });
const clickYes = async (sel) => {
  const el = __overlayEls[__overlayEls.length - 1];
  const yes = el ? el.querySelector(sel) : null;
  if (yes && typeof yes.onclick === 'function') yes.onclick();
  await __settle(120);
};
const posts = (url) => __rec.fetches.filter(f => f.method === 'POST' && f.url === url).map(f => f.body);
"""


def _run(tmp_path, modules, body):
    return run_js(tmp_path, modules, XL + body)


def test_printer_name_for_head_falls_back_to_the_printer_rows(tmp_path):
    """Review frontend-13: state.printerMap is null on a fresh dashboard."""
    res = _run(tmp_path, ["inv_core.js"], """
state.printerMap = null;
state.allLocations.push({ LocationID: 'CORE1', Name: 'Core One', Type: 'Printer',
                          toolheads: [{ location_id: 'CORE1', position: 0 }] });
return { xl2: window.printerNameForHead('XL-2'), core: window.printerNameForHead('CORE1'),
         none: window.printerNameForHead('ZZ-9'), slotLabel: window.printerLabelForTarget('LR-MDB-1', '3') };
""")
    assert res["xl2"] == "XL Test" and res["core"] == "Core One", res
    assert res["none"] is None
    assert res["slotLabel"] == "⏳ Checking XL Test…", res


def test_a_quickswap_replay_sends_every_head_confirmed_so_far(tmp_path):
    """Review deduct-and-tests-21. The overlay's probe showed XL-2 PRINTING and
    the user confirmed it; the server then asks about XL-1. The replay must
    carry both, or the next answer asks about XL-2 again, forever."""
    res = _run(tmp_path, ["inv_core.js", "inv_quickswap.js"], """
let swaps = 0;
window.__respond = (url, method) => {
  if (url.startsWith('/api/printer_state/')) return printing('XL Test');
  if (url === '/api/quickswap') {
    swaps += 1;
    return swaps === 1
      ? { body: { action: 'quickswap_requires_confirm', msg: '#42 is loaded on XL-1. Continue?',
                  active_print: { toolhead: 'XL-1', printer_name: 'XL Test', state: 'PRINTING' },
                  active_prints: [{ toolhead: 'XL-1', printer_name: 'XL Test', state: 'PRINTING', role: 'source' }] } }
      : { body: { action: 'quickswap_done', moved: 42 } };
  }
  return { body: [] };
};
const btn = { dataset: { box: 'LR-MDB-1', slot: '3', toolhead: 'XL-2' }, hasAttribute: () => false,
              querySelector: () => null };
window.quickSwapTap(btn);
await __settle(150);
await clickYes('#fcc-quickswap-yes');
await clickYes('#fcc-quickswap-yes');
return { posts: posts('/api/quickswap'), overlays: __rec.overlays.map(o => o.content) };
""")
    sent = [p["confirmed_toolheads"] for p in res["posts"]]
    assert sent == [["XL-2"], ["XL-2", "XL-1"]], sent
    assert "#42 is loaded on XL-1" in res["overlays"][-1]


def test_a_return_replay_sends_every_head_confirmed_so_far(tmp_path):
    res = _run(tmp_path, ["inv_core.js", "inv_quickswap.js"], """
let returns = 0;
window.__respond = (url, method) => {
  if (url.startsWith('/api/printer_state/')) return printing('XL Test');
  if (url.startsWith('/api/machine/')) return { status: 404, body: { toolheads: {} } };
  if (url.startsWith('/api/get_contents?id=XL-1')) return { body: [] };
  if (url.startsWith('/api/get_contents?id=XL-2'))
    return { body: [{ id: 42, display: 'Test spool #42', location: 'XL-2', slot: '' }] };
  if (url === '/api/spools/42') return { body: { success: true, data: { id: 42, location: 'XL-2',
      extra: { physical_source: '"LR-MDB-1"', physical_source_slot: '"3"' } } } };
  if (url === '/api/dryer_boxes/slots') return { body: { slots: [{ box: 'LR-MDB-1', slot: '3', target: 'XL-2' }] } };
  if (url === '/api/quickswap/return') {
    returns += 1;
    return returns === 1
      ? { body: { action: 'return_requires_confirm', msg: 'XL-9 needs a confirm too. Continue?',
                  active_print: { toolhead: 'XL-9', printer_name: 'XL Test', state: 'PRINTING' },
                  active_prints: [{ toolhead: 'XL-9', printer_name: 'XL Test', state: 'PRINTING', role: 'source' }] } }
      : { body: { action: 'return_done', moved: 42, box: 'LR-MDB-1', slot: '3' } };
  }
  return { body: [] };
};
window.renderQuickSwapSection(state.allLocations[0]);
await __settle();
window.returnToolheadToSlot();
await __settle(200);
await clickYes('#fcc-quickswap-yes');
await clickYes('#fcc-quickswap-yes');
return { posts: posts('/api/quickswap/return') };
""")
    sent = [p["confirmed_toolheads"] for p in res["posts"]]
    assert sent == [["XL-2"], ["XL-2", "XL-9"]], sent


def test_a_deposit_asked_again_shows_the_servers_message_and_replays_the_same_spool(tmp_path):
    """Review routes-wire-7. The overlay's probe saw XL-2 idle; the server's
    source check asks about XL-1, which #42 is leaving (D6). The re-ask must
    show that message, not repeat the deposit's own text, and its Yes must
    replay #42 with XL-1 confirmed."""
    res = _run(tmp_path, ["inv_core.js", "inv_quickswap.js"], """
state.heldSpools = [{ id: 42, display: '#42' }, { id: 57, display: '#57' }];
let deposits = 0;
const D6 = '#42 is loaded on XL-1. Moving it to LR-MDB-1 means FCC stops charging this print to it. Continue?';
window.__respond = (url, method) => {
  if (url.startsWith('/api/printer_state/')) return idle('XL Test');
  if (url === '/api/identify_scan') {
    deposits += 1;
    return deposits === 1
      ? { body: { type: 'assignment', action: 'assignment_requires_confirm', location: 'LR-MDB-1', slot: '3',
                  msg: D6, moved: 42,
                  active_print: { toolhead: 'XL-1', printer_name: 'XL Test', state: 'PRINTING' },
                  active_prints: [{ toolhead: 'XL-1', printer_name: 'XL Test', state: 'PRINTING', role: 'source' }] } }
      : { body: { type: 'assignment', action: 'assignment_done', location: 'LR-MDB-1', slot: '3', moved: 42 } };
  }
  return { body: [] };
};
const btn = { dataset: { box: 'LR-MDB-1', slot: '3', toolhead: 'XL-2' } };
window.quickSwapDeposit(btn);
await __settle(150);
await clickYes('#fcc-quickswap-yes');
// The carousel rotates while the re-ask is open: the replay still names #42.
state.heldSpools = [{ id: 57, display: '#57' }, { id: 42, display: '#42' }];
await clickYes('#fcc-quickswap-yes');
return { posts: posts('/api/identify_scan'), overlays: __rec.overlays.map(o => o.content),
         logs: __rec.logs.concat(posts('/api/log_event')) };
""")
    assert len(res["overlays"]) == 2, res["overlays"]
    assert "stops charging this print to it" in res["overlays"][1], res["overlays"][1]
    bodies = res["posts"]
    assert [b["confirmed_toolheads"] for b in bodies] == [[], ["XL-1"]], bodies
    assert [b["spool_id"] for b in bodies] == [42, 42], bodies
    assert any(lg["level"] == "WARNING" and "active-print confirm" in lg["msg"] for lg in res["logs"]), res["logs"]


def test_a_slot_scan_replay_asked_again_re_asks_with_the_union(tmp_path):
    """Review engine-5. The first replay is asked again (a printer that failed
    open on the first probe answers PRINTING now). It used to show the
    question as a 3 s green toast while nothing moved."""
    res = _run(tmp_path, ["inv_core.js", "inv_cmd.js"], """
state.heldSpools = [{ id: 42, display: '#42' }];
let scans = 0;
const ask = (head) => ({ body: { type: 'assignment', action: 'assignment_requires_confirm',
    location: 'LR-MDB-1', slot: '3', moved: 42, msg: head + ' is printing. Continue?',
    active_print: { toolhead: head, printer_name: 'XL Test', state: 'PRINTING' },
    active_prints: [{ toolhead: head, printer_name: 'XL Test', state: 'PRINTING', role: 'feeds' }] } });
window.__respond = (url, method) => {
  if (url.startsWith('/api/printer_state/')) return idle('XL Test');
  if (url === '/api/identify_scan') {
    scans += 1;
    if (scans === 1) return ask('XL-2');
    if (scans === 2) return ask('XL-1');
    return { body: { type: 'assignment', action: 'assignment_done', location: 'LR-MDB-1', slot: '3', moved: 42 } };
  }
  return { body: [] };
};
window.processScan('LOC:LR-MDB-1:SLOT:3', 'barcode');
await __settle(200);
await clickYes('.fcc-apc-yes');
await clickYes('.fcc-apc-yes');
await __settle(100);
return { posts: posts('/api/identify_scan'), toasts: __rec.toasts };
""")
    bodies = res["posts"]
    assert len(bodies) == 3, bodies
    assert bodies[1]["confirmed_toolheads"] == ["XL-2"] and bodies[1].get("spool_id") == 42, bodies
    assert bodies[2]["confirmed_toolheads"] == ["XL-2", "XL-1"] and bodies[2].get("spool_id") == 42, bodies
    assert not [t for t in res["toasts"] if t["type"] == "success" and "Continue?" in t["msg"]], res["toasts"]


def test_a_location_manager_move_off_a_printing_head_asks_once(tmp_path):
    """Review engine-6. #42 sits on XL-1; the Location Manager assigns it to
    XL-3 while the XL prints. The server's one answer names both heads (D6).
    doAssign's own probe-and-confirm of XL-3 made it two prompts."""
    res = _run(tmp_path, ["inv_core.js", "inv_loc_mgr.js"], """
state.heldSpools = [{ id: 42, display: '#42', location: 'XL-1' }];
window.refreshManageView = () => {}; window.fetchLocations = () => {}; window.renderBuffer = () => {};
let assigns = 0;
window.__respond = (url, method) => {
  if (url.startsWith('/api/printer_state/')) return printing('XL Test');
  if (url === '/api/manage_contents') {
    assigns += 1;
    return assigns === 1
      ? { body: { status: 'requires_confirm', confirm_type: 'active_print',
                  msg: '#42 is loaded on XL-1. Moving it to XL-3 means FCC stops charging this print to it. Continue?',
                  active_print: { toolhead: 'XL-1', printer_name: 'XL Test', state: 'PRINTING' },
                  active_prints: [{ toolhead: 'XL-1', printer_name: 'XL Test', state: 'PRINTING', role: 'source' },
                                  { toolhead: 'XL-3', printer_name: 'XL Test', state: 'PRINTING', role: 'destination' }] } }
      : { body: { status: 'success' } };
  }
  return { body: [] };
};
window.doAssign('XL-3', 42, null, true);
await __settle(150);
for (let i = 0; i < 3 && __overlayEls.length > i; i++) await clickYes('.fcc-apc-yes');
return { posts: posts('/api/manage_contents'), overlays: __rec.overlays.length,
         probes: __rec.fetches.filter(f => f.url.startsWith('/api/printer_state/')).length };
""")
    assert res["overlays"] == 1, f"{res['overlays']} prompts for one move"
    sent = [p["confirmed_toolheads"] for p in res["posts"]]
    assert sent == [[], ["XL-1", "XL-3"]], sent


def test_two_taps_during_the_probe_leave_no_keydown_handler_behind(tmp_path):
    """Review frontend-14. Both taps passed the overlay check before either
    probe answered; the remount dropped the first overlay's DOM but not its
    document keydown handler, which then ate every Tab on the page."""
    res = _run(tmp_path, ["inv_core.js", "inv_quickswap.js"], """
const live = [];
const realAdd = document.addEventListener, realRemove = document.removeEventListener;
document.addEventListener = (type, fn) => { if (type === 'keydown') live.push(fn); };
document.removeEventListener = (type, fn) => {
  if (type === 'keydown') { const i = live.indexOf(fn); if (i !== -1) live.splice(i, 1); }
};
window.fetchPrinterStateDetailed = () => new Promise(r => setTimeout(
  () => r({ active: false, known: true, reason: null, state: 'IDLE', printer_name: 'XL Test' }), 80));
const btn = { dataset: { box: 'LR-MDB-1', slot: '3', toolhead: 'XL-2' }, hasAttribute: () => false,
              querySelector: () => null };
window.quickSwapTap(btn);
window.quickSwapTap(btn);
await __settle(400);
const mounted = __rec.overlays.length;
const el = __overlayEls[__overlayEls.length - 1];
const no = el.querySelector('#fcc-quickswap-no');
if (no && typeof no.onclick === 'function') no.onclick();
await __settle(50);
return { mounted, liveAfterClose: live.length };
""")
    assert res["mounted"] == 1, res
    assert res["liveAfterClose"] == 0, res
