"""Group 48's card buttons, two fixes from the bundle review (2026-10-19), under
node's `vm` (no browser, no container): the REAL inv_core.js, ui_builder.js and
inv_details.js.

  - browser-4: a card's ✏️ reads where the spool IS before Force Location opens.
    A loaded spool's search or buffer card is a ghost filed at its box, so the
    card passed '' and the dialog opened on "-- Unassigned --": a Force Move
    with no pick took the spool off its head. Now the dialog opens on the
    spool's own location (its head), as the spool window's ✏️ does, and a read
    that fails opens nothing.
  - integration-2: every card's 🖨️ handler compiles for a name with an
    apostrophe. The display went into the inline handler HTML-escaped only, and
    the browser decodes the attribute before it compiles the handler, so
    "Robin's Egg Blue" ended the JS string: the click did nothing (48.1 removed
    the Location Manager listener that used to hide it there).

Base proof (a5d8cb8): every test fails there.
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

MODULES = ["inv_core.js", "ui_builder.js", "inv_details.js"]
LOCS = [{"LocationID": "LR-MDB-1", "Name": "LR box", "Type": "Dryer Box", "Max Spools": "4"},
        {"LocationID": "XL-1", "Name": "XL-1", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "CR-CT-2-R1", "Name": "Cart row", "Type": "Cart Row", "Max Spools": "0"}]
# What /api/spools/refresh and /api/search answer for #57, loaded on XL-1 from
# LR-MDB-1 slot 2: a ghost filed at its box.
GHOST = {"id": 57, "display": "#57 Brand PLA (Red)", "color": "ff0000", "location": "LR-MDB-1",
         "is_ghost": True, "slot": "2", "deployed_to": "XL-1", "details": {}}


def _js(value):
    return json.dumps(value)


PENCIL = """
window.fetchT = (u, o) => window.fetch(u, o);
window.__respond = (url) => {
  if (url === '/api/locations') return { body: __LOCS__ };
  if (url.startsWith('/api/spool_details')) return __DETAILS__;
  return { body: { success: true } };
};
const html = window.SpoolCardBuilder.buildCard(__ITEM__, 'buffer', { isFirst: true, index: 0 });
const call = (html.match(/moveSpoolFromCard\\(([^)]*)\\)/) || [''])[0];
let swalHtml = null;
globalThis.Swal = {
  fire: (opts) => {
    swalHtml = opts.html;
    const hidden = (/id="swal-override-loc" value="([^"]*)"/.exec(opts.html) || [])[1];
    return Promise.resolve({ isConfirmed: true, value: hidden });   // Force Move with nothing picked
  },
  getPopup: () => null, close: () => {}, clickConfirm: () => {},
};
eval('window.' + call);              // the pencil's own onclick call
await __settle(300);
const unassignedRow = (/<div class="swal-loc-item[^"]*" data-id="" style="[^"]*"/.exec(swalHtml || '') || [''])[0];
return { call, opened: swalHtml !== null,
         hidden: (/id="swal-override-loc" value="([^"]*)"/.exec(swalHtml || '') || [])[1],
         unassignedHighlighted: unassignedRow.includes('background:#444'),
         reads: __rec.fetches.filter(f => f.url.startsWith('/api/spool_details')).map(f => f.url),
         posts: __rec.fetches.filter(f => f.method === 'POST' && f.url !== '/api/log_event').map(f => f.body),
         toasts: __rec.toasts, logs: __rec.logs };
"""


def _pencil(tmp_path, details, item=GHOST, modules=MODULES):
    scenario = (PENCIL.replace("__LOCS__", _js(LOCS)).replace("__DETAILS__", _js(details))
                .replace("__ITEM__", _js(item)))
    res = run_js(tmp_path, modules, scenario)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def test_a_loaded_spools_pencil_opens_on_its_head_not_unassigned(tmp_path):
    res = _pencil(tmp_path, {"body": {"id": 57, "location": "XL-1", "extra": {}}})
    assert res["reads"] == ["/api/spool_details?id=57"], res["reads"]
    assert res["opened"] and res["hidden"] == "XL-1", res
    assert not res["unassignedHighlighted"], res
    assert not any((p or {}).get("action") == "force_unassign" for p in res["posts"]), res["posts"]


@pytest.mark.parametrize("details", [
    {"status": 502, "body": {"error": "Spoolman timed out"}},
    {"body": None},
    {"body": {"message": "Item not found"}},      # get_spool answers Spoolman's 404 body
], ids=["spoolman-down", "no-record", "spoolman-404"])
def test_a_pencil_whose_spool_cant_be_read_opens_nothing(tmp_path, details):
    # Without inv_core.js, so the driver's own showToast / logClientEvent record
    # each call (the real ones draw into the DOM and POST to /api/log_event).
    res = _pencil(tmp_path, details, modules=["ui_builder.js", "inv_details.js"])
    assert not res["opened"] and res["posts"] == [], res
    warn = [t for t in res["toasts"] if "Couldn't read #57 from Spoolman" in t["msg"]]
    assert warn and warn[0]["type"] == "warning" and warn[0]["duration"] >= 7000, res["toasts"]
    assert any(lg["level"] == "WARNING" and "✏️ on #57" in lg["msg"] for lg in res["logs"]), res["logs"]


DISPLAY = "#57 FCC Test PLA (Robin's Egg Blue) \"Big\" <b>&amp;"
QUEUE = """
const got = [];
window.addToQueue = (o) => { got.push(o); return true; };
globalThis.addToQueue = window.addToQueue;
window.processScan = () => {};
const item = __ITEM__;
const decode = (s) => s.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<')
  .replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const out = {};
for (const mode of ['search', 'loc_list', 'loc_grid', 'quickswap', 'buffer']) {
  const html = window.SpoolCardBuilder.buildCard(Object.assign({}, item), mode,
    { index: 0, locId: 'LR-MDB-1', slotNum: 2, isFirst: true });
  const handlers = [...html.matchAll(/onclick="([^"]*)"/g)].map(m => decode(m[1]))
    .filter(code => code.includes('addToQueue('));
  out[mode] = handlers.map(code => {
    const before = got.length;
    try { new Function('event', code)({ stopPropagation() {} }); }
    catch (e) { return 'ERR ' + e.name + ': ' + e.message; }
    return got.length > before ? got[got.length - 1].display : 'NOT CALLED';
  });
}
return out;
"""


def test_every_cards_print_button_compiles_for_a_name_with_an_apostrophe(tmp_path):
    item = {"id": 57, "display": DISPLAY, "color": "ff0000", "location": "LR-MDB-1", "slot": "2",
            "details": {}}
    res = run_js(tmp_path, MODULES, QUEUE.replace("__ITEM__", _js(item)))
    assert res["unhandled"] == [], res["unhandled"]
    for mode in ("search", "loc_list", "loc_grid", "quickswap", "buffer"):
        assert res[mode], (mode, res)
        assert all(d == DISPLAY for d in res[mode]), (mode, res[mode])
