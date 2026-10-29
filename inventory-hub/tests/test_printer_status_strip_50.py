"""Group 50.1 (Derek, 2026-10-19 / 25 / 29): the folded Printer Status strip.

Each printer reads as it does open: its name (or its ID), its state, its 🛑
count, then its heads. A head is its label (the toolhead-label setting) on its
spool's colours, ringed in its weight colour, with its grams beside it (the
default: "it's kind of the point for me at least"), under it ("I really like C
too"), or only in its tooltip. Three per-browser settings (Settings → This
Browser), each applied as soon as it is picked: the toolhead labels (By ID / By
number / By Tool + number; a browser's old pick, "XL-3" / "3" / "Tool 3", one
of Derek's own heads, moves to its new name at load: no setup's own names in
Settings), the printers (By name / By ID; hovering shows both) and the weights
(Beside each toolhead / Under each toolhead / Off). The strip sits beside the
title while every printer's heads fit there, else under it, and a printer whose
heads don't fit even then scrolls them sideways.

Runs in an isolated page with the real global.css and modules (the harness of
test_printer_status_even_rows.py), and the heartbeat's `id` through the
section builder with its collaborators patched. Offline.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

import app as app_module  # noqa: E402,F401  (route registration)
import locations_db  # noqa: E402
import routes_state_pulse  # noqa: E402
from test_printer_status_even_rows import (  # noqa: E402
    ACCUMULATOR, BOOTSTRAP_STANDIN, GLOBAL_CSS, MODULES, PAGE, PRELUDE, _size)

XL = "🦝 XL"
INDX = "🦝 Core One INDX"
RAINBOW = "000000,FF0000,000000,FF7F00,000000,FFFF00,000000,00FF00,000000,0000FF"


def _spool(sid, colour, grams):
    return {"id": sid, "display": f"#{sid} Sample PLA", "color": colour, "color_direction": "longitudinal",
            "remaining_weight": grams, "initial_weight": 1000}


def _heads(prefix, spools, unbound=False):
    return [{"id": f"{prefix}-{i + 1}", "position": i, "unbound": unbound, "item": s,
             "loaded_count": 1 if s else 0} for i, s in enumerate(spools)]


# Decision 1's made-up fleet on dev's real layout and names: the XL's five heads
# (812 g, 64 g amber, empty, a rainbow, 0 g red) and the INDX's eight (no box
# slot feeds them).
FLEET = {
    XL: {"id": "XL", "state": {"state": "PRINTING", "is_active": True}, "toolheads": _heads("XL", [
        _spool(57, "1a1a1a", 812), _spool(88, "008b8b", 64), None, _spool(242, RAINBOW, 703),
        _spool(61, "f5f5f5", 0)])},
    INDX: {"id": "RCOI", "state": {"state": "IDLE", "is_active": False}, "toolheads": _heads("RCOI", [
        _spool(101, "fa6831", 905), _spool(102, "0e0e0e", 455), _spool(103, "d4af37", 88), None,
        _spool(105, "1f5fbf", 610), _spool(106, "c8102e", 300), _spool(107, "2e8b57", 740), None], unbound=True)},
}
LABELS = {"By ID": ["XL-1", "XL-2", "XL-3", "XL-4", "XL-5"],
          "By number": ["1", "2", "3", "4", "5"],
          "By Tool + number": ["Tool 1", "Tool 2", "Tool 3", "Tool 4", "Tool 5"]}

STRIP_JS = r"""() => {
    const w = document.getElementById('printer-status-widget');
    const strip = w.querySelector('.fcc-ps-header-chips');
    const bar = w.querySelector('.fcc-ps-header-bar').getBoundingClientRect();
    const box = (el) => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right }; };
    return {
        under: strip.classList.contains('fcc-ps-strip-under'),
        beside: strip.getBoundingClientRect().left >= bar.right - 1,
        widgetH: Math.round(w.getBoundingClientRect().height),
        printers: Array.from(strip.querySelectorAll('.fcc-ps-printer-group')).map((g) => {
            const name = g.querySelector('.fcc-ps-strip-name');
            const heads = g.querySelector('.fcc-ps-strip-heads');
            return { printer: g.dataset.printer, name: name.textContent, title: name.title, box: box(g),
                     scrolls: heads.scrollWidth > heads.clientWidth + 1,
                     heads: Array.from(heads.querySelectorAll('.fcc-ps-strip-head')).map((h) => {
                         const ring = h.querySelector('.fcc-ps-ring');
                         const grams = h.querySelector('.fcc-ps-mini-weight:not(.fcc-ps-strip-w-none)');
                         return { id: h.dataset.toolhead, label: ring.textContent, title: h.title,
                                  ring: box(ring), grams: grams ? grams.textContent : null,
                                  gramsBox: grams ? box(grams) : null, gramsColour: grams ? getComputedStyle(grams).color : null,
                                  border: getComputedStyle(ring).borderTopColor,
                                  borderStyle: getComputedStyle(ring).borderTopStyle }; }) }; }) };
}"""


def _build(page, stored=None):
    """The widget's page, with `stored` in its localStorage before the modules load."""
    page.set_content(PAGE.format(standin=BOOTSTRAP_STANDIN, css=GLOBAL_CSS.read_text(encoding="utf-8")))
    page.add_script_tag(content=PRELUDE)
    # The XL first, as Derek orders them (unordered, the widget sorts by name).
    page.evaluate("(s) => { for (const k in s) localStorage.setItem(k, s[k]); }",
                  {"fcc.printerStatus.order": json.dumps([XL, INDX]), **(stored or {})})
    for name in ("inv_core.js", "ui_builder.js", "inv_printer_status.js", "text_size.js", "cancel_review.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content=ACCUMULATOR)


@pytest.fixture
def strip_page(isolated_page):
    page = isolated_page
    yield page
    assert page.evaluate("window.__errors") == []


def _open(page, width=1600, size="Standard", stored=None, fleet=None):
    page.set_viewport_size({"width": width, "height": 900})
    _build(page, stored)
    _size(page, size)
    page.evaluate("(rows) => window.refreshPrinterStatusWidgetFromAggregate(rows)", fleet or FLEET)
    page.evaluate("() => window.togglePrinterStatusWidget()")   # fold it, as the user does
    page.wait_for_function("() => document.getElementById('printer-status-widget').classList.contains('collapsed')")
    return page.evaluate(STRIP_JS)


def _printer(got, name):
    return next(p for p in got["printers"] if p["printer"] == name)


def _one_line(heads):
    return max(h["ring"]["top"] for h in heads) - min(h["ring"]["top"] for h in heads) < 2


# --- each printer: its name, state, count, heads; labels follow the setting ---

@pytest.mark.parametrize("mode", list(LABELS))
def test_the_strip_reads_per_printer_and_follows_the_label_setting(strip_page, mode):
    got = _open(strip_page, stored={"fcc.printerStatus.toolheadLabel": mode})
    assert [p["printer"] for p in got["printers"]] == [XL, INDX], got
    xl = _printer(got, XL)
    assert [h["label"] for h in xl["heads"]] == LABELS[mode], xl
    # Clicks and every test that selects by it still see the full ID.
    assert [h["id"] for h in xl["heads"]] == LABELS["By ID"], xl
    assert xl["name"] == XL and xl["title"] == f"{XL} · ID XL", xl
    assert strip_page.evaluate("""() => Array.from(document.querySelector('.fcc-ps-printer-group').children)
        .map((c) => c.className)""") == ["fcc-ps-strip-name", "fcc-ps-strip-state", "fcc-ps-strip-count",
                                         "fcc-ps-strip-heads"]


def test_no_divider_between_printers(strip_page):
    _open(strip_page)
    assert strip_page.evaluate("""() => Array.from(document.querySelectorAll('.fcc-ps-printer-group'))
        .map((g) => getComputedStyle(g).borderLeftStyle)""") == ["none", "none"]


def test_printers_by_id_and_hovering_shows_both(strip_page):
    fleet = {**FLEET, "No Row Printer": {"id": "", "state": None, "toolheads": _heads("NR", [None])}}
    got = _open(strip_page, stored={"fcc.printerStatus.printerName": "By ID"}, fleet=fleet)
    assert {p["printer"]: p["name"] for p in got["printers"]} == {
        XL: "XL", INDX: "RCOI", "No Row Printer": "No Row Printer"}, got
    assert _printer(got, INDX)["title"] == f"{INDX} · ID RCOI", got
    # A printer FCC has no ID for keeps its name (and its title is the name).
    assert _printer(got, "No Row Printer")["title"] == "No Row Printer", got


# --- the rings and the grams ---------------------------------------------------

def test_rings_wear_the_weight_colours_and_say_what_feeds_them(strip_page):
    got = _open(strip_page)
    xl, indx = _printer(got, XL), _printer(got, INDX)
    border = {h["id"]: h["border"] for h in xl["heads"] + indx["heads"]}
    assert border["XL-1"] == "rgb(13, 202, 240)" and border["XL-2"] == "rgb(255, 193, 7)", border
    assert border["XL-5"] == "rgb(255, 107, 107)", border
    styles = {h["id"]: h["borderStyle"] for h in xl["heads"] + indx["heads"]}
    assert styles["XL-1"] == "solid" and styles["RCOI-1"] == "dashed" and styles["RCOI-4"] == "dashed", styles
    # The tooltip carries what the ring leaves out.
    assert xl["heads"][0]["title"] == "XL-1: #57 Sample PLA, 812 g left. Click to open XL-1.", xl
    assert indx["heads"][3]["title"] == "RCOI-4: empty. No box slot feeds it. Click to open RCOI-4.", indx


def test_weights_beside_each_toolhead_is_the_default(strip_page):
    got = _open(strip_page)
    xl = _printer(got, XL)
    assert [h["grams"] for h in xl["heads"]] == ["812g", "64g", None, "703g", "0g"], xl
    for h in xl["heads"]:
        if h["grams"]:
            # Beside: on the ring's line, after it, in the ring's colour.
            assert h["gramsBox"]["left"] >= h["ring"]["right"] - 0.5, h
            assert abs((h["gramsBox"]["top"] + h["gramsBox"]["bottom"]) / 2
                       - (h["ring"]["top"] + h["ring"]["bottom"]) / 2) < 3, h
            assert h["gramsColour"] == h["border"], h


def test_weights_under_each_toolhead(strip_page):
    got = _open(strip_page, stored={"fcc.printerStatus.stripWeight": "Under each toolhead"})
    xl = _printer(got, XL)
    assert [h["grams"] for h in xl["heads"]] == ["812g", "64g", None, "703g", "0g"], xl
    for h in xl["heads"]:
        if h["grams"]:
            assert h["gramsBox"]["top"] >= h["ring"]["bottom"] - 1, h
    # The rings stay in one line, the empty head's included.
    assert _one_line(xl["heads"]), xl


def test_weights_off_keeps_them_in_the_tooltip(strip_page):
    got = _open(strip_page, stored={"fcc.printerStatus.stripWeight": "Off"})
    xl = _printer(got, XL)
    assert all(h["grams"] is None for h in xl["heads"]), xl
    assert "812 g left" in xl["heads"][0]["title"], xl


# --- the settings: an old pick moves, a pick applies at once, a scan never picks ---

@pytest.mark.parametrize("old, new", [("XL-3", "By ID"), ("3", "By number"), ("Tool 3", "By Tool + number")])
def test_an_old_label_pick_moves_to_its_new_name(strip_page, old, new):
    got = _open(strip_page, stored={"fcc.printerStatus.toolheadLabel": old})
    assert strip_page.evaluate("() => localStorage.getItem('fcc.printerStatus.toolheadLabel')") == new
    assert [h["label"] for h in _printer(got, XL)["heads"]] == LABELS[new], got


@pytest.mark.parametrize("stored", ["", "Tool three", "By id"])
def test_an_unknown_pick_reads_as_the_default(strip_page, stored):
    got = _open(strip_page, stored={"fcc.printerStatus.toolheadLabel": stored,
                                    "fcc.printerStatus.stripWeight": stored,
                                    "fcc.printerStatus.printerName": stored})
    xl = _printer(got, XL)
    assert [h["label"] for h in xl["heads"]] == LABELS["By ID"] and xl["name"] == XL, got
    assert xl["heads"][0]["grams"] == "812g", got


SELECT_JS = r"""(a) => {
    const sel = document.createElement('select');
    sel.className = 'form-select form-select-sm cfgset-input';
    sel.dataset.key = a.key; sel.dataset.initial = a.from;
    a.choices.forEach((c) => { const o = document.createElement('option'); o.value = c; o.textContent = c; sel.appendChild(o); });
    sel.value = a.from;
    document.body.appendChild(sel);
    return true;
}"""


@pytest.mark.parametrize("key, choices, pick, check", [
    ("fcc.printerStatus.stripWeight", ["Beside each toolhead", "Under each toolhead", "Off"], "Off",
     "() => document.querySelectorAll('.fcc-ps-header-chips .fcc-ps-mini-weight').length === 0"),
    ("fcc.printerStatus.printerName", ["By name", "By ID"], "By ID",
     "() => document.querySelector('.fcc-ps-strip-name').textContent === 'XL'"),
    ("fcc.printerStatus.toolheadLabel", ["By ID", "By number", "By Tool + number"], "By number",
     "() => document.querySelector('.fcc-ps-header-chips .fcc-ps-ring').textContent === '1'"
     " && document.querySelector('.fcc-ps-body .fcc-ps-th-id').textContent === '1'"),
])
def test_a_settings_pick_applies_at_once_with_no_save(strip_page, key, choices, pick, check):
    _open(strip_page)
    strip_page.evaluate(SELECT_JS, {"key": key, "choices": choices, "from": choices[0]})
    strip_page.evaluate("(a) => { const s = document.querySelector('.cfgset-input'); s.value = a;"
                        " s.dispatchEvent(new Event('change', { bubbles: true })); }", pick)
    assert strip_page.evaluate(check), strip_page.evaluate(STRIP_JS)
    assert strip_page.evaluate("(k) => localStorage.getItem(k)", key) == pick
    # Kept already, so Save settings has nothing left to do for it.
    assert strip_page.evaluate("() => document.querySelector('.cfgset-input').dataset.initial") == pick


def test_a_scan_never_picks_a_choice(strip_page):
    _open(strip_page)
    strip_page.evaluate(SELECT_JS, {"key": "fcc.printerStatus.stripWeight",
                                    "choices": ["Beside each toolhead", "Under each toolhead", "Off"],
                                    "from": "Beside each toolhead"})
    prevented = strip_page.evaluate("""() => { const s = document.querySelector('.cfgset-input'); s.focus();
        const press = (key) => { const e = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
            s.dispatchEvent(e); return e.defaultPrevented; };
        return { letter: press('U'), digit: press('7'), arrow: press('ArrowDown'), ctrl: (() => {
            const e = new KeyboardEvent('keydown', { key: 'c', ctrlKey: true, bubbles: true, cancelable: true });
            s.dispatchEvent(e); return e.defaultPrevented; })() }; }""")
    assert prevented == {"letter": True, "digit": True, "arrow": False, "ctrl": False}, prevented


# --- the fit (measured; Derek's 1600 px window, then narrower) -----------------

def test_number_labels_keep_one_line_beside_the_title_at_1600(strip_page):
    got = _open(strip_page, stored={"fcc.printerStatus.toolheadLabel": "By number"})
    heads = [h for p in got["printers"] for h in p["heads"]]
    assert got["beside"] and not got["under"] and _one_line(heads), got
    assert not any(p["scrolls"] for p in got["printers"]), got


def test_id_labels_take_a_line_per_printer_beside_the_title_at_1600(strip_page):
    got = _open(strip_page)
    xl, indx = _printer(got, XL), _printer(got, INDX)
    assert got["beside"] and not got["under"], got
    assert _one_line(xl["heads"]) and _one_line(indx["heads"]), got
    assert indx["box"]["top"] >= xl["box"]["bottom"] - 1, "each printer on its own line"
    # Both lines start at the same edge.
    assert abs(indx["box"]["left"] - xl["box"]["left"]) < 1, got


def test_weights_under_keep_one_line_with_id_labels_at_1600(strip_page):
    got = _open(strip_page, stored={"fcc.printerStatus.stripWeight": "Under each toolhead"})
    heads = [h for p in got["printers"] for h in p["heads"]]
    assert got["beside"] and _one_line(heads), got


def test_a_narrow_window_puts_the_strip_under_the_title_and_scrolls_what_still_does_not_fit(strip_page):
    got = _open(strip_page, width=1024, size="Extra Large")
    assert got["under"] and not got["beside"], got
    assert _printer(got, INDX)["scrolls"] and not _printer(got, XL)["scrolls"], got
    assert strip_page.evaluate("() => document.documentElement.scrollWidth <= innerWidth"), "the page scrolls sideways"


def test_widening_the_window_brings_the_strip_back_beside_the_title(strip_page):
    got = _open(strip_page, width=1024, size="Extra Large")
    assert got["under"], got
    strip_page.set_viewport_size({"width": 1600, "height": 900})
    _size(strip_page, "Standard")
    strip_page.wait_for_function("() => !document.querySelector('.fcc-ps-header-chips').classList.contains('fcc-ps-strip-under')",
                                 timeout=3000)
    assert strip_page.evaluate(STRIP_JS)["beside"]


def test_folding_measures_the_strip_again(strip_page):
    # Open, the strip has no width; folded at a narrow width it goes under the title.
    _open(strip_page, width=1024, size="Extra Large")
    strip_page.evaluate("() => window.togglePrinterStatusWidget()")   # open
    strip_page.evaluate("() => document.querySelector('.fcc-ps-header-chips').classList.remove('fcc-ps-strip-under')")
    strip_page.evaluate("() => window.togglePrinterStatusWidget()")   # fold
    assert strip_page.evaluate(STRIP_JS)["under"]


# --- the heartbeat gives each printer its ID -----------------------------------

ROWS = [
    {"LocationID": "XL", "Type": "Printer", "Name": XL,
     "toolheads": [{"location_id": "XL-1", "position": 0}, {"location_id": "XL-2", "position": 1}]},
    # Two rows sharing one Name: the row listing the printer's first head decides.
    {"LocationID": "TWIN-B", "Type": "Printer", "Name": "Twin", "toolheads": [{"location_id": "TW-2", "position": 1}]},
    {"LocationID": "TWIN-A", "Type": "Printer", "Name": "Twin", "toolheads": [{"location_id": "TW-1", "position": 0}]},
]


def _section(rows, extra_map=None):
    pm = locations_db.build_printer_map_from_rows(rows)
    pm.update(extra_map or {})
    with patch.object(routes_state_pulse.locations_db, "load_locations_list", return_value=rows), \
         patch.object(routes_state_pulse.locations_db, "get_active_printer_map", return_value=pm), \
         patch.object(routes_state_pulse.config_loader, "load_config", return_value={}), \
         patch.object(routes_state_pulse.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(routes_state_pulse.spoolman_api, "bucket_spools_by_location", return_value={}), \
         patch.object(routes_state_pulse.locations_db, "get_bindings_for_machine", return_value={"toolheads": {}}), \
         patch.object(routes_state_pulse.prusalink_api, "get_printer_state", return_value=None):
        return routes_state_pulse._pulse_section_printer_status()


def test_the_heartbeat_gives_each_printer_its_own_id():
    out = _section(ROWS, {"GH-1": {"printer_name": "Ghost", "position": 0}})
    assert out[XL]["id"] == "XL", out
    assert out["Twin"]["id"] == "TWIN-A", out
    # A printer no Printer row lists: no id, and the strip keeps its name.
    assert out["Ghost"]["id"] == "", out
    assert set(out[XL]) == {"toolheads", "state", "id"}, out


# --- Group 50.3: every head by keyboard (the keyboard standing order) ----------

OPEN_STUB = "() => { window.__opened = []; window.openManage = (id) => window.__opened.push(id); }"
HEAD = '#printer-status-widget .fcc-ps-strip-head[data-toolhead="{}"]'
TILE = '#printer-status-widget .fcc-ps-th[data-toolhead="{}"]'


def test_every_head_is_a_tab_stop_and_a_button(strip_page):
    _open(strip_page)
    got = strip_page.evaluate("""() => Array.from(document.querySelectorAll(
        '#printer-status-widget .fcc-ps-th, #printer-status-widget .fcc-ps-strip-head'))
        .map((el) => [el.dataset.toolhead, el.getAttribute('tabindex'), el.getAttribute('role')])""")
    assert len(got) == 26 and all(t == "0" and r == "button" for _, t, r in got), got


@pytest.mark.parametrize("key", ["Enter", "Space"])
def test_enter_or_space_on_a_focused_head_opens_it(strip_page, key):
    _open(strip_page)
    strip_page.evaluate(OPEN_STUB)
    strip_page.focus(HEAD.format("RCOI-3"))
    strip_page.keyboard.press(key)
    assert strip_page.evaluate("window.__opened") == ["RCOI-3"]
    strip_page.evaluate("() => window.togglePrinterStatusWidget()")   # open: the tiles
    strip_page.focus(TILE.format("XL-2"))
    strip_page.keyboard.press(key)
    assert strip_page.evaluate("window.__opened") == ["RCOI-3", "XL-2"]
    # A person's press, not a scan.
    assert strip_page.evaluate("window.__scans") == []


def test_a_scan_typed_on_a_focused_head_is_still_a_scan(strip_page):
    _open(strip_page)
    strip_page.evaluate(OPEN_STUB)
    strip_page.focus(HEAD.format("XL-1"))
    # A label with a Space in it, at a scanner's pace, then its Enter.
    strip_page.keyboard.type("LOC:Bin 2", delay=5)
    strip_page.keyboard.press("Enter")
    assert strip_page.evaluate("window.__opened") == []
    assert strip_page.evaluate("window.__scans") == ["LOC:Bin 2"]


def test_a_focused_head_keeps_the_focus_through_a_heartbeat(strip_page):
    import copy
    _open(strip_page)
    strip_page.focus(HEAD.format("RCOI-5"))
    fleet = copy.deepcopy(FLEET)
    fleet[INDX]["toolheads"][4]["item"]["remaining_weight"] = 600
    strip_page.evaluate("(rows) => window.refreshPrinterStatusWidgetFromAggregate(rows)", fleet)
    assert strip_page.evaluate("() => document.activeElement.dataset.toolhead") == "RCOI-5"
    assert strip_page.evaluate("() => document.activeElement.textContent") == "RCOI-5600g"


def test_the_keyboard_reach_is_in_the_shortcut_list(strip_page):
    _open(strip_page)
    ids = strip_page.evaluate("() => window.__pendingShortcuts.map((s) => s.id)")
    assert "printer-status-open-head" in ids, ids
