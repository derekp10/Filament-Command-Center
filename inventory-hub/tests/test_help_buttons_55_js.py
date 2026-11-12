"""In-app help (Group 55.3): the ? buttons the page's scripts draw, on the real modules
under node's `vm` (the stub DOM of test_core1_return_ejectall_js.py), with no browser and
no container.

  - window.confirmActivePrint draws its ? where the ? key gives help: by default it asks
    the help registry (shortcuts_registry.js + help_texts.js) for its overlay's help, so
    the move doors' questions get the move question's, the Printer picker's toolhead
    question the picker's, and Done's question none. A question with no help is drawn
    byte for byte as it was (test_audit_done_question_58_js.py pins those bytes without
    the registry; here, with it loaded).
  - Enter on the question's ? opens the help and never answers the question (the
    three-way's Enter elsewhere stores it).
  - window.WeightEntry draws a ? only for a caller that names a help key: the
    Quick-Weigh, never the wizard's Weigh from Scale.
  - Drawn by the real openers (Group 55 review, R3-4: test_help_texts_55.py's SCRIPT_DRAWN
    only finds their text): openQuickWeigh's window has its ?, and so does each picker's
    header, the box picker's (Return's too) and the Printer picker's, each its own help.
  - window.fccCornerHelpHtml (the Quick-Swap question's ? and "Record it as coming
    from…"'s) draws the help its overlay id has, or nothing.

The browser half (where each ? sits, a click leaving the keyboard where it was) is
test_in_app_help_55_e2e.py.
"""
from __future__ import annotations

import json
import re

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import PRELUDE

HELP = ["inv_core.js", "shortcuts_registry.js", "help_texts.js"]
CORE = ["inv_core.js"]

# The calls the doors make, and the help each one's ? opens (None: no ?).
CALLS = [
    ("{ title: 'Load #42 onto HEAD-1?', msg: 'B.', onConfirm() {}, onCancel() {}, onStore() {},"
     " storeLabel: 'Just store it in DRYBOX-1 slot 2' }", "move-question"),
    ("{ activePrint: { printer_name: 'PRINTER-1', state: 'PRINTING' }, msg: 'M',"
     " ids: { overlay: 'fcc-active-print-scan-overlay', yes: 'fcc-aps-yes', no: 'fcc-aps-no' } }", "move-question"),
    ("{ activePrints: [{ printer_name: 'PRINTER-1', state: 'PRINTING' }], msg: 'Undo?', onConfirm() {} }", "move-question"),
    ("{ title: 'Load #42 onto HEAD-3?', msg: 'HEAD-3 holds #7.', printing: false, loadLabel: 'Load it instead',"
     " ids: { overlay: 'fcc-head-pick-confirm' }, onConfirm() {}, onCancel() {} }", "printer-picker"),
    ("{ title: 'Park 2 at Unknown?', msg: 'B', printing: true, ids: { overlay: 'fcc-audit-done-question' },"
     " onConfirm() {}, onCancel() {}, cancelLabel: 'Back to the audit', keepWhole: true }", None),
    ("{ title: 'T', msg: 'B', noLoad: true, onConfirm() {}, onStore() {},"
     " ids: { overlay: 'q', yes: 'y', no: 'n', store: 's' } }", None),
]


def _draw(tmp_path, modules, calls):
    body = "".join(f"window.confirmActivePrint({c});\n" for c in calls) + "return { html: html() };"
    res = run_js(tmp_path, modules, PRELUDE + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res["html"]


def test_each_question_draws_the_help_its_overlay_has(tmp_path):
    drawn = _draw(tmp_path, HELP, [c for c, _ in CALLS])
    for (call, key), html in zip(CALLS, drawn):
        keys = re.findall(r'data-fcc-help="([^"]+)"', html)
        if key is None:
            assert keys == [], (call, keys)
            continue
        assert keys == [key], (call, keys)
        btn = re.search(r"<button[^>]*data-fcc-help=[^>]*>", html).group(0)
        assert 'type="button"' in btn and "fcc-help-btn fcc-apc-help" in btn and "aria-label=" in btn, btn
        # In the panel, before its title (top right, positioned by global.css), never in it:
        # the title's words are as they were.
        assert re.search(r'class="fcc-apc-panel[^"]*" style="[^"]*position:relative;">\s*<button', html), html
        title = re.search(r'<div class="fcc-apc-title" style="([^"]*)">(.*?)</div>', html, re.S)
        assert "padding:0 2.5rem;" in title.group(1) and "data-fcc-help" not in title.group(2), title.group(0)


def test_a_question_with_no_help_is_drawn_as_it_was(tmp_path):
    """Pins what was right: with the registry loaded, a question whose overlay has no help
    (Done's) and one whose caller passes `help: ''` are the bytes inv_core.js alone draws."""
    plain = [c for c, key in CALLS if key is None]
    assert _draw(tmp_path, HELP, plain) == _draw(tmp_path, CORE, plain)
    first = CALLS[0][0]
    silenced = first[:-1] + ", help: '' }"
    assert _draw(tmp_path, HELP, [silenced]) == _draw(tmp_path, CORE, [first])


def test_a_caller_can_name_its_questions_help(tmp_path):
    html = _draw(tmp_path, HELP, ["{ title: 'T', msg: 'B', ids: { overlay: 'q' }, help: 'wizard',"
                                  " onConfirm() {}, onCancel() {} }"])[0]
    assert re.findall(r'data-fcc-help="([^"]+)"', html) == ["wizard"]


ENTER_ON_HELP = r"""
let answered = [];
let clicks = 0;
window.confirmActivePrint(__CALL__);
const helpBtn = btn('.fcc-apc-help');
helpBtn.click = () => { clicks += 1; };
document.activeElement = helpBtn;
await key('Enter');
const onHelp = { answered: answered.slice(), clicks };
document.activeElement = btn(__OTHER__);
await key('Enter');
return { onHelp, answered, clicks };
"""


def test_enter_on_the_questions_help_button_opens_the_help_and_answers_nothing(tmp_path):
    """The three-way's Enter stores the spool wherever the keyboard is but on Load or
    Cancel, so without its own case an Enter on the ? stored it. It presses the ? instead,
    and the question waits; Enter on Just store it (or the yes / no's Cancel) still answers."""
    for call, other, then in (
            ("{ title: 'Load #42 onto HEAD-1?', msg: 'B.', onConfirm() { answered.push('load'); },"
             " onCancel() { answered.push('cancel'); }, onStore() { answered.push('store'); } }",
             ".fcc-apc-store", "store"),
            ("{ activePrint: { printer_name: 'PRINTER-1', state: 'PRINTING' }, msg: 'M',"
             " onConfirm() { answered.push('load'); }, onCancel() { answered.push('cancel'); } }",
             ".fcc-apc-no", "cancel")):
        body = ENTER_ON_HELP.replace("__CALL__", call).replace("__OTHER__", json.dumps(other))
        res = run_js(tmp_path, HELP, PRELUDE + body)
        assert res["unhandled"] == [], res["unhandled"]
        assert res["onHelp"] == {"answered": [], "clicks": 1}, (call, res)
        assert res["answered"] == [then] and res["clicks"] == 1, (call, res)


WEIGH = r"""
await window.WeightEntry.openModal({ title: 'Quick Weigh', helpKey: 'quick-weigh',
    spool: { id: 42, initial_weight: 1000, used_weight: 0, display: 'Example - PLA - Blue' } });
await window.WeightEntry.openModal({ title: 'Weigh from Scale',
    spool: { id: null, initial_weight: 1000, used_weight: 0, display: 'New spool' } });
return { html: __rec.overlays.map(o => o.content) };
"""


def test_the_weigh_window_draws_a_help_button_only_for_a_caller_that_names_one(tmp_path):
    res = run_js(tmp_path, ["inv_core.js", "weight_utils.js", "weight_entry.js"], WEIGH)
    assert res["unhandled"] == [], res["unhandled"]
    quick, scale = res["html"]
    assert re.findall(r'data-fcc-help="([^"]+)"', quick) == ["quick-weigh"]
    assert "data-fcc-help" not in scale and "fcc-help-btn" not in scale
    # Beside the ×, before it, in the header.
    assert quick.index('data-fcc-help="quick-weigh"') < quick.index('id="fcc-we-close"') < quick.index('id="fcc-we-input"')


# Group 55 review, R3-4: the ?s a script draws with its key in a variable, drawn by the
# real code that opens them (test_help_texts_55.py's SCRIPT_DRAWN only finds the text).
QUICK_WEIGH = r"""
window.__respond = (url) => (url.startsWith('/api/spool_details')
    ? { body: { id: 42, initial_weight: 1000, used_weight: 200, spool_weight: 200, archived: false,
                filament: { id: 7, name: 'Blue', material: 'PLA', weight: 1000, spool_weight: 200,
                            vendor: { id: 3, name: 'Example' } } } }
    : { body: {} });
window.openQuickWeigh(42);
await __settle(120);
return { html: __rec.overlays.map(o => o.content) };
"""


def test_the_quick_weigh_opens_with_its_help_button(tmp_path):
    """openQuickWeigh names the Quick-Weigh's help key: its window has the ?."""
    res = run_js(tmp_path, ["inv_core.js", "weight_utils.js", "weight_entry.js", "inv_weigh_out.js"], QUICK_WEIGH)
    assert res["unhandled"] == [], res["unhandled"]
    assert len(res["html"]) == 1, res["html"]
    assert re.findall(r'data-fcc-help="([^"]+)"', res["html"][0]) == ["quick-weigh"]


PICKER = r"""
// The node sandbox has no URLSearchParams: the picker builds its read's address with one.
window.URLSearchParams = class {
  constructor(o) { this.o = Object.assign({}, o || {}); }
  set(k, v) { this.o[k] = String(v); }
  append(k, v) { this.o[k] = String(v); }
  toString() { return Object.keys(this.o).map((k) => encodeURIComponent(k) + '=' + encodeURIComponent(this.o[k])).join('&'); }
};
// inv_core.js's fetchT times out with AbortSignal, which the sandbox lacks too.
window.fetchT = (u, o) => window.fetch(u, o);
// The stub overlay has no setContent: the picker draws through it.
const __stubMount = window.mountOverlay;
window.mountOverlay = (opts) => {
  const h = __stubMount(opts);
  h.panel = h.element;
  h.setContent = (html) => { h.element.innerHTML = html; __rec.overlays.push({ id: opts.id, content: html, closed: false }); };
  return h;
};
state.allLocations = [
  { LocationID: 'DRYBOX-1', Name: 'Box', Type: 'Dryer Box', 'Max Spools': '4' },
  { LocationID: 'PRINTER-1', Name: 'Printer 1', Type: 'Printer',
    toolheads: [{ location_id: 'HEAD-1', position: 0 }, { location_id: 'HEAD-2', position: 1 }] },
  { LocationID: 'HEAD-1', Name: 'Head 1', Type: 'Tool Head', 'Max Spools': '1' },
  { LocationID: 'HEAD-2', Name: 'Head 2', Type: 'Tool Head', 'Max Spools': '1' },
];
window.__respond = () => ({ status: 503, body: {} });   // the loading view is enough
window.openSlotPicker(__OPTS__);
await __settle(120);
// The views it drew (the mount's empty shell left out).
return { html: __rec.overlays.filter(o => o.id === 'fcc-slot-picker' && o.content.includes('card-header')).map(o => o.content) };
"""


def test_each_picker_draws_its_own_help_button(tmp_path):
    """The box picker's header has the slot picker's ?, Return's too, and the Printer
    picker's has its own, from the loading view on (the mode _mount marks on its root)."""
    for opts, key in (({"location": "DRYBOX-1", "spool": 42}, "slot-picker"),
                      ({"location": "DRYBOX-1", "spool": 42, "mode": "return"}, "slot-picker"),
                      ({"location": "PRINTER-1", "spool": 42}, "printer-picker")):
        res = run_js(tmp_path, ["inv_core.js", "slot_picker.js"], PICKER.replace("__OPTS__", json.dumps(opts)))
        assert res["unhandled"] == [], res["unhandled"]
        assert res["html"], f"the picker drew nothing for {opts}"
        for html in res["html"]:
            assert re.findall(r'data-fcc-help="([^"]+)"', html) == [key], (opts, html[:400])
            # In the header, just before its ✕ (the header ends where the status line starts).
            at = [html.find(s) for s in ('class="card-header', 'data-fcc-help=', 'data-sp-act="cancel"',
                                         'class="fcc-sp-status"')]
            assert -1 not in at and at == sorted(at), (opts, at)


CORNER = r"""
return {
  swap: window.fccCornerHelpHtml('fcc-quickswap-confirm-overlay'),
  source: window.fccCornerHelpHtml('fcc-record-source'),
  done: window.fccCornerHelpHtml('fcc-audit-done-question'),
  none: window.fccCornerHelpHtml(''),
};
"""


def test_a_corner_help_button_is_the_help_its_overlay_has(tmp_path):
    """window.fccCornerHelpHtml (the Quick-Swap question's ? and "Record it as coming
    from…"'s): the help help_texts.js gives the overlay id, or nothing."""
    res = run_js(tmp_path, HELP, CORNER)
    assert res["unhandled"] == [], res["unhandled"]
    assert re.findall(r'data-fcc-help="([^"]+)"', res["swap"]) == ["swap-question"]
    assert re.findall(r'data-fcc-help="([^"]+)"', res["source"]) == ["printer-picker"]
    for html in (res["swap"], res["source"]):
        assert html.startswith('<button type="button" class="fcc-help-btn fcc-help-corner"') and "aria-label=" in html, html
    assert res["done"] == "" and res["none"] == ""
