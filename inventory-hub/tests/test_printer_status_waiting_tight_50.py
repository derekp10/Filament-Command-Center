"""Group 50.4 and 50.7 (Derek's picks from the samples, 2026-10-30), hermetic.

50.4, "stored, not loaded": a spool stored in a box slot that feeds a head but
isn't loaded on it (the heartbeat's `waiting`: every such spool, a slot prepped
on purpose included, Derek's answer; tests/test_printer_status_waiting_50_4.py
pins the server's half) shows quietly. On the open tile a line, "📦 #93 waits
in slot 2", and "I loaded it", which runs the Quick-Swap tap's load
(window.quickSwapTap: its confirm, a printing head's question, Group 51.5's
spool check, Undo) and never also opens the head; several spools, their count,
and the tile opens the head. In the folded strip an amber dot on the head's
ring (Derek's pick of three), the words in the head's tooltip and its
accessible name, so a screen reader hears them, and a tap, a click or Enter
opens the head, whose Quick-Swap slots show and load it (Derek: "as long as it
also takes into account non mouse inputs"). Nothing when nothing waits; a
spool's free text is escaped.

50.7, option (b) (Derek: "I like B, but we lose the material type in the
cards. We could try putting it into the color section, where the toolhead name
is listed"): on a window too short for the open widget (it would scroll inside
itself), each printer's state and 🛑 count go beside its name and each tile's
material moves from its own line up into its colour band, so every head shows
whole; a tall window never changes; a window made shorter or taller takes or
drops the step, measured.

Runs the REAL global.css, inv_core.js, ui_builder.js, inv_printer_status.js,
text_size.js and cancel_review.js, and the dashboard's own scan accumulator
(lifted from scripts.html), in `isolated_page`, so it RUNS under --offline.
"""
from __future__ import annotations

import json

import pytest

import conftest
from test_printer_status_even_rows import (ACCUMULATOR, BOOTSTRAP_STANDIN, GLOBAL_CSS, MODULES, PAGE, PRELUDE,
                                           _item, _size)

XL = "ZZ Wait XL"
INDX = "ZZ Wait INDX"

W93 = {"id": 93, "display": "#93 Galaxy Black PLA", "box": "ZZ-BOX-1", "slot": "2"}
W95 = {"id": 95, "display": "#95 Teal PETG", "box": "ZZ-BOX-1", "slot": "3"}
W96 = {"id": 96, "display": "#96 Orange PLA", "box": "ZZ-BOX-2", "slot": "1"}


def _heads(prefix, items, waiting=None, unbound=False):
    waiting = waiting or {}
    out = []
    for i, it in enumerate(items):
        th = {"id": f"{prefix}-{i + 1}", "position": i, "unbound": unbound, "item": it, "loaded_count": 1 if it else 0}
        if i in waiting:
            th["waiting"] = waiting[i]
        out.append(th)
    return out


def _fleet(waiting_xl=None, waiting_indx=None, indx_unbound=False):
    """Dev's shape: an XL of five heads (one empty) and an INDX of eight (two
    empty), every loaded spool with a material. `indx_unbound`: no box slot
    feeds the INDX's heads (Derek's today: each tile says "🔗 no bound slot")."""
    mats = ["PLA", "PETG", "ASA", "PLA Silk", "TPU"]
    xl = [_item(500 + i, c, mats[i % 5]) if c else None
          for i, c in enumerate(["1a1a1a", "008b8b", None, "d4af37", "f5f5f5"])]
    indx = [_item(600 + i, c, mats[(i + 1) % 5]) if c else None
            for i, c in enumerate(["fa6831", "0e0e0e", "d4af37", None, "1f5fbf", "c8102e", "2e8b57", None])]
    return {XL: {"id": "ZXL", "state": {"state": "PRINTING", "is_active": True},
                 "toolheads": _heads("ZX", xl, waiting_xl)},
            INDX: {"id": "ZIN", "state": {"state": "IDLE", "is_active": False},
                   "toolheads": _heads("ZI", indx, waiting_indx, indx_unbound)}}


# What the page's other modules would do: the Quick-Swap tap (inv_quickswap.js)
# and opening a head (inv_loc_mgr.js), recorded.
STUBS = r"""
window.__taps = []; window.__opened = [];
window.quickSwapTap = (btn) => window.__taps.push({ toolhead: btn.dataset.toolhead, box: btn.dataset.box,
    slot: btn.dataset.slot, spool: btn.dataset.spoolId, label: btn.dataset.spoolLabel });
window.openManage = (id) => window.__opened.push(id);
"""


def _build(page, width=1600, height=1300, size="Standard", stored=None):
    page.set_viewport_size({"width": width, "height": height})
    page.set_content(PAGE.format(standin=BOOTSTRAP_STANDIN, css=GLOBAL_CSS.read_text(encoding="utf-8")))
    page.add_script_tag(content=PRELUDE)
    page.evaluate("(s) => { for (const k in s) localStorage.setItem(k, s[k]); }",
                  {"fcc.printerStatus.order": json.dumps([XL, INDX]), **(stored or {})})
    for name in ("inv_core.js", "ui_builder.js", "inv_printer_status.js", "text_size.js", "cancel_review.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content=ACCUMULATOR)
    page.add_script_tag(content=STUBS)
    _size(page, size)


def _feed(page, rows):
    page.evaluate("(rows) => window.refreshPrinterStatusWidgetFromAggregate(rows)", rows)


@pytest.fixture
def wpage(isolated_page):
    yield isolated_page
    assert isolated_page.evaluate("window.__errors") == []


TILE_JS = r"""(id) => { const t = document.querySelector('#printer-status-widget .fcc-ps-body .fcc-ps-th[data-toolhead="' + id + '"]');
    const w = t.querySelector('.fcc-ps-th-waiting'); const b = t.querySelector('.fcc-ps-loaded-it');
    return { line: w ? w.querySelector('.fcc-ps-th-waiting-text').textContent : null, title: w ? w.title : null,
             button: b ? { text: b.textContent, toolhead: b.dataset.toolhead, box: b.dataset.box, slot: b.dataset.slot,
                           spool: b.dataset.spoolId, label: b.dataset.spoolLabel } : null,
             bold: !!t.querySelector('.fcc-ps-th-waiting b, .fcc-ps-chip b') }; }"""

HEAD_JS = r"""(id) => { const h = document.querySelector('#printer-status-widget .fcc-ps-header-chips .fcc-ps-strip-head[data-toolhead="' + id + '"]');
    const ring = h.querySelector('.fcc-ps-ring'); const dot = getComputedStyle(ring, '::after');
    return { dot: ring.classList.contains('fcc-ps-ring-waiting'), dotColour: dot.backgroundColor, dotContent: dot.content,
             title: h.title, aria: h.getAttribute('aria-label'), width: h.getBoundingClientRect().width }; }"""


# --- 50.4: the open tile ---------------------------------------------------------------

def test_a_stored_spool_shows_on_its_heads_tile_with_i_loaded_it(wpage):
    page = wpage
    _build(page)
    _feed(page, _fleet(waiting_xl={1: [W93], 2: [W95]}))
    got = page.evaluate(TILE_JS, "ZX-2")      # runs #501 while #93 waits
    assert got["line"] == "📦 #93 waits in slot 2", got
    assert got["title"].startswith("Stored for ZX-2, not loaded: #93 Galaxy Black PLA in ZZ-BOX-1 slot 2."), got
    assert got["button"] == {"text": "✓ I loaded it", "toolhead": "ZX-2", "box": "ZZ-BOX-1", "slot": "2",
                             "spool": "93", "label": "#93 Galaxy Black PLA"}, got
    empty = page.evaluate(TILE_JS, "ZX-3")    # empty while #95 waits
    assert empty["line"] == "📦 #95 waits in slot 3" and empty["button"]["spool"] == "95", empty
    for quiet in ("ZX-1", "ZI-1", "ZI-4"):
        assert page.evaluate(TILE_JS, quiet)["line"] is None, quiet


def test_i_loaded_it_runs_the_quick_swap_tap_and_never_opens_the_head(wpage):
    page = wpage
    _build(page)
    _feed(page, _fleet(waiting_xl={1: [W93]}))
    btn = page.locator('#printer-status-widget .fcc-ps-th[data-toolhead="ZX-2"] .fcc-ps-loaded-it')
    btn.click()
    assert page.evaluate("window.__taps") == [{"toolhead": "ZX-2", "box": "ZZ-BOX-1", "slot": "2", "spool": "93",
                                                "label": "#93 Galaxy Black PLA"}]
    assert page.evaluate("window.__opened") == []
    # The tile itself still opens the head.
    page.locator('#printer-status-widget .fcc-ps-th[data-toolhead="ZX-2"] .fcc-ps-th-body').click()
    assert page.evaluate("window.__opened") == ["ZX-2"]


def test_i_loaded_it_by_keyboard_presses_once_and_a_scan_onto_it_stays_a_scan(wpage):
    """Tab reaches the button (after its tile); Enter presses it once, through
    the dashboard's own accumulator (Group 50.6); a scan typed while it has the
    focus presses nothing and reaches the scan path whole."""
    page = wpage
    _build(page)
    _feed(page, _fleet(waiting_xl={1: [W93]}))
    page.locator('#printer-status-widget .fcc-ps-th[data-toolhead="ZX-2"]').focus()
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.classList.contains('fcc-ps-loaded-it')")
    page.keyboard.press("Enter")
    assert len(page.evaluate("window.__taps")) == 1 and page.evaluate("window.__opened") == []
    page.keyboard.type("LOC:ZZ-BIN-2")
    page.keyboard.press("Enter")
    assert len(page.evaluate("window.__taps")) == 1
    assert page.evaluate("window.__scans") == ["LOC:ZZ-BIN-2"]


def test_several_stored_spools_show_their_count_and_the_tile_opens_the_head(wpage):
    page = wpage
    _build(page)
    _feed(page, _fleet(waiting_xl={0: [W93, W96]}))
    got = page.evaluate(TILE_JS, "ZX-1")
    assert got["line"] == "📦 2 spools wait" and got["button"] is None, got
    assert ("#93 Galaxy Black PLA in ZZ-BOX-1 slot 2 and #96 Orange PLA in ZZ-BOX-2 slot 1." in got["title"]
            and "Open ZX-1 to load one from its Quick-Swap slots." in got["title"]), got


def test_a_spools_free_text_is_escaped(wpage):
    page = wpage
    _build(page)
    odd = dict(W93, display='#93 <b>Bold</b> "PLA"')
    rows = _fleet(waiting_xl={1: [odd]})
    rows[XL]["toolheads"][0]["item"]["details"]["material"] = "<b>PLA</b>"
    rows[XL]["toolheads"][0]["item"]["display"] = "#500 <b>Black</b>"
    _feed(page, rows)
    got = page.evaluate(TILE_JS, "ZX-2")
    assert got["button"]["label"] == '#93 <b>Bold</b> "PLA"' and not got["bold"], got
    assert '#93 <b>Bold</b> "PLA" in ZZ-BOX-1 slot 2' in got["title"]
    first = page.evaluate(TILE_JS, "ZX-1")
    assert not first["bold"], first
    assert page.evaluate("""() => document.querySelector('#printer-status-widget .fcc-ps-th[data-toolhead="ZX-1"] .fcc-ps-chip-mat').textContent""") == "<b>PLA</b>"


def test_the_mark_comes_and_goes_with_the_heartbeat(wpage):
    page = wpage
    _build(page)
    _feed(page, _fleet())
    assert page.evaluate(TILE_JS, "ZX-2")["line"] is None
    _feed(page, _fleet(waiting_xl={1: [W93]}))
    assert page.evaluate(TILE_JS, "ZX-2")["line"] == "📦 #93 waits in slot 2"
    _feed(page, _fleet())
    assert page.evaluate(TILE_JS, "ZX-2")["line"] is None


def test_the_waiting_line_is_readable(wpage):
    """Standing order: readable contrast (WCAG AA) for the line and its button
    on the dark tile, a loaded one and an empty one. Both are scored (the
    guard scores a root's descendants: min_ratio=100 lists them)."""
    page = wpage
    _build(page)
    _feed(page, _fleet(waiting_xl={1: [W93], 2: [W95]}))
    for hid in ("ZX-2", "ZX-3"):
        block = page.locator(f'#printer-status-widget .fcc-ps-th[data-toolhead="{hid}"] .fcc-ps-th-waiting')
        scored = [o.get("text", "").strip() for o in conftest.contrast_offenders(block, min_ratio=100)]
        assert any(t.startswith("📦") for t in scored) and "✓ I loaded it" in scored, (hid, scored)
        assert conftest.contrast_offenders(block) == [], hid


# --- 50.4: the folded strip --------------------------------------------------------------

def test_the_folded_strip_marks_the_head_with_an_amber_dot_and_says_why(wpage):
    page = wpage
    _build(page)
    _feed(page, _fleet(waiting_xl={1: [W93], 2: [W95]}))
    page.evaluate("() => window.togglePrinterStatusWidget()")
    page.wait_for_function("() => document.getElementById('printer-status-widget').classList.contains('collapsed')")
    loaded = page.evaluate(HEAD_JS, "ZX-2")
    assert loaded["dot"] and loaded["dotColour"] == "rgb(255, 183, 77)" and loaded["dotContent"] == '""', loaded
    want = "Stored for ZX-2, not loaded: #93 Galaxy Black PLA in ZZ-BOX-1 slot 2."
    assert want in loaded["title"] and loaded["aria"] == loaded["title"], loaded
    assert loaded["title"].startswith("ZX-2: #501 Even Test PETG, 640 g left.") and loaded["title"].endswith("Click to open ZX-2.")
    empty = page.evaluate(HEAD_JS, "ZX-3")
    assert empty["dot"] and "Stored for ZX-3, not loaded: #95 Teal PETG in ZZ-BOX-1 slot 3." in empty["aria"], empty
    quiet = page.evaluate(HEAD_JS, "ZX-1")
    assert not quiet["dot"] and "Stored for" not in quiet["title"] and quiet["aria"] == quiet["title"], quiet
    # The dot sits on the ring: the head is as wide as it was without it.
    _feed(page, _fleet())
    assert abs(page.evaluate(HEAD_JS, "ZX-2")["width"] - loaded["width"]) < 0.5
    # A tap, a click or Enter opens the head, whose Quick-Swap slots show the spool.
    _feed(page, _fleet(waiting_xl={1: [W93]}))
    page.locator('#printer-status-widget .fcc-ps-header-chips .fcc-ps-strip-head[data-toolhead="ZX-2"]').click()
    page.locator('#printer-status-widget .fcc-ps-header-chips .fcc-ps-strip-head[data-toolhead="ZX-2"]').focus()
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == ["ZX-2", "ZX-2"]


# --- 50.7: a short window --------------------------------------------------------------

TIGHT_JS = r"""() => {
  const w = document.getElementById('printer-status-widget'); const body = w.querySelector('.fcc-ps-body');
  const box = body.getBoundingClientRect();
  const tiles = Array.from(body.querySelectorAll('.fcc-ps-th'));
  const shown = (el) => !!el && getComputedStyle(el).display !== 'none';
  return {
    tight: w.classList.contains('fcc-ps-tight'),
    scrolls: body.scrollHeight > body.clientHeight + 1,
    whole: tiles.filter((t) => { const r = t.getBoundingClientRect(); return r.top >= box.top - 1 && r.bottom <= box.bottom + 1; }).length,
    tiles: tiles.length,
    rows: Array.from(body.querySelectorAll('.fcc-ps-row')).map((row) => {
      const n = row.querySelector('.fcc-ps-name').getBoundingClientRect(); const i = row.querySelector('.fcc-ps-info').getBoundingClientRect();
      const heads = row.querySelector('.fcc-ps-toolheads').getBoundingClientRect();
      return { beside: Math.abs((n.top + n.bottom) / 2 - (i.top + i.bottom) / 2) < 4 && i.left >= n.right,
               tilesUnder: heads.top >= Math.max(n.bottom, i.bottom) - 0.5, tilesFrom: Math.round(heads.left - n.left) }; }),
    bandMat: tiles.filter((t) => shown(t.querySelector('.fcc-ps-th-mat'))).map((t) => t.querySelector('.fcc-ps-th-mat').textContent),
    lineMat: tiles.filter((t) => shown(t.querySelector('.fcc-ps-chip-mat'))).length,
    bandInside: tiles.every((t) => { const m = t.querySelector('.fcc-ps-th-mat'); if (!shown(m)) return true;
      const b = t.querySelector('.fcc-ps-th-body').getBoundingClientRect(); const r = m.getBoundingClientRect();
      return r.left >= b.left - 0.5 && r.right <= b.right + 0.5 && r.top >= b.top - 0.5 && r.bottom <= b.bottom + 0.5; }),
  };
}"""


WAITING_JS = r"""(id) => { const w = document.querySelector('#printer-status-widget .fcc-ps-body .fcc-ps-th[data-toolhead="' + id + '"] .fcc-ps-th-waiting');
    const a = w.querySelector('.fcc-ps-th-waiting-id').getBoundingClientRect(); const b = w.querySelector('.fcc-ps-loaded-it').getBoundingClientRect();
    return { oneLine: Math.abs((a.top + a.bottom) / 2 - (b.top + b.bottom) / 2) < 3 && b.left >= a.right,
             where: getComputedStyle(w.querySelector('.fcc-ps-th-waiting-where')).display !== 'none' }; }"""


@pytest.mark.parametrize("width, height, size", [(1280, 800, "Large"), (1366, 768, "Standard")])
@pytest.mark.parametrize("worst", [False, True], ids=["plain", "waiting-and-unbound"])
def test_a_short_window_takes_the_tight_step_and_shows_every_head(wpage, width, height, size, worst):
    """The two short laptop windows of the samples: 9 of the 13 heads showed
    whole before (the rest a scroll away); now all 13, each printer's state and
    🛑 count beside its name, each material in its tile's colour band. The
    worst case Derek's own fleet makes: a spool waiting for two of the XL's
    heads and every INDX tile saying "🔗 no bound slot": a waiting spool takes
    one line there, its number beside "I loaded it" (the laptop at the printer
    is a short window, and it is where a spool is loaded)."""
    page = wpage
    _build(page, width, height, size)
    _feed(page, _fleet(waiting_xl={1: [W93], 2: [W95]}, indx_unbound=True) if worst else _fleet())
    page.wait_for_timeout(100)
    got = page.evaluate(TIGHT_JS)
    assert got["tight"] and not got["scrolls"] and got["whole"] == got["tiles"] == 13, got
    assert all(r["beside"] and r["tilesUnder"] for r in got["rows"]), got
    want = [th["item"]["details"]["material"] for p in _fleet().values() for th in p["toolheads"] if th["item"]]
    assert sorted(got["bandMat"]) == sorted(want) and len(want) == 10, got
    assert got["lineMat"] == 0 and got["bandInside"], got
    if worst:
        for hid in ("ZX-2", "ZX-3"):
            assert page.evaluate(WAITING_JS, hid) == {"oneLine": True, "where": False}, hid


def test_a_tall_window_never_changes(wpage):
    page = wpage
    _build(page, 1600, 1300, "Standard")
    _feed(page, _fleet(waiting_xl={1: [W93]}, indx_unbound=True))
    page.wait_for_timeout(100)
    got = page.evaluate(TIGHT_JS)
    assert not got["tight"] and not got["scrolls"] and got["whole"] == 13, got
    assert not any(r["beside"] for r in got["rows"]) and got["bandMat"] == [] and got["lineMat"] == 10, got
    # The waiting spool's two lines, as Derek saw them in the sample.
    assert page.evaluate(WAITING_JS, "ZX-2") == {"oneLine": False, "where": True}


def test_a_window_made_shorter_or_taller_takes_or_drops_the_step(wpage):
    page = wpage
    _build(page, 1366, 1100, "Standard")
    _feed(page, _fleet())
    page.wait_for_timeout(100)
    assert not page.evaluate(TIGHT_JS)["tight"]
    page.set_viewport_size({"width": 1366, "height": 768})      # only the height changes
    page.wait_for_function("() => document.getElementById('printer-status-widget').classList.contains('fcc-ps-tight')",
                           timeout=3000)
    got = page.evaluate(TIGHT_JS)
    assert got["whole"] == 13 and not got["scrolls"], got
    page.set_viewport_size({"width": 1366, "height": 1100})
    page.wait_for_function("() => !document.getElementById('printer-status-widget').classList.contains('fcc-ps-tight')",
                           timeout=3000)
    # Large text on the same tall window: still no step; Extra Large on a short one: the step.
    _size(page, "Large")
    page.wait_for_timeout(100)
    assert not page.evaluate(TIGHT_JS)["tight"]
    page.set_viewport_size({"width": 1366, "height": 768})
    _size(page, "Extra Large")
    page.wait_for_timeout(150)
    assert page.evaluate(TIGHT_JS)["tight"]


def test_the_tight_step_keeps_a_phones_tiles_at_the_edge(wpage):
    """A phone held sideways is short and narrow: its tiles start at the row's
    edge (.fcc-ps-edge) in the tight step too, never under the name only."""
    page = wpage
    _build(page, 412, 400, "Standard")
    _feed(page, _fleet())
    page.wait_for_timeout(150)
    got = page.evaluate(TIGHT_JS)
    assert got["tight"], got
    edges = page.evaluate("""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-row')).map((row) => {
        const heads = row.querySelector('.fcc-ps-toolheads').getBoundingClientRect(); const r = row.getBoundingClientRect();
        return { edge: row.classList.contains('fcc-ps-edge'), fromEdge: Math.round(heads.left - r.left) }; })""")
    assert all(e["edge"] and e["fromEdge"] <= 1 for e in edges), edges
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")


NAMES_JS = r"""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-row')).map((row) => {
    const n = row.querySelector('.fcc-ps-name'); const i = row.querySelector('.fcc-ps-info');
    const nb = n.getBoundingClientRect(); const ib = i.getBoundingClientRect(); const rb = row.getBoundingClientRect();
    const hb = row.querySelector('.fcc-ps-toolheads').getBoundingClientRect();
    return { printer: row.dataset.printer, whole: n.scrollWidth <= n.clientWidth + 1, nameW: Math.round(nb.width),
             infoAfter: ib.left >= nb.right - 0.5, infoInside: ib.right <= rb.right + 0.5,
             tilesFromName: Math.abs(hb.left - nb.left) < 1, edge: row.classList.contains('fcc-ps-edge'),
             tilesLeft: hb.left }; })"""


@pytest.mark.parametrize("width, height, size", [(1280, 800, "Large"), (1366, 768, "Standard"), (1600, 700, "Extra Large"),
                                                 (1024, 600, "Large"), (412, 800, "Standard"), (390, 700, "Extra Large")])
def test_in_the_tight_step_every_name_shows_whole_and_its_info_follows_it(wpage, width, height, size):
    """Found measuring the build (2026-10-30): with three columns the tiles'
    width went to the info line's column and a printer's name shrank to a
    few px. In the step every name here shows whole, its info line follows it
    inside the row, and the tiles start under the name (at the row's edge on a
    phone)."""
    page = wpage
    _build(page, width, height, size)
    _feed(page, _fleet(indx_unbound=True))
    assert page.evaluate("() => document.getElementById('printer-status-widget').classList.contains('fcc-ps-tight')")
    rows = page.evaluate(NAMES_JS)
    assert len(rows) == 2, rows
    for r in rows:
        assert r["whole"] and r["infoAfter"] and r["infoInside"], (width, size, rows)
        assert r["tilesFromName"] or r["edge"], (width, size, rows)


@pytest.mark.parametrize("width, size", [(700, "Large"), (412, "Standard")])
def test_in_the_tight_step_a_60_character_name_ends_in_an_ellipsis_and_moves_nothing(wpage, width, size):
    """A name too long for its line ends in "…" (its full text is its title),
    as it does on two lines: the info line stays inside the row, and the tiles
    start where they do under a short name."""
    page = wpage
    long_name = "ZZ A Printer Whose Name Goes On And On Past Any Sensible End"
    assert len(long_name) == 60
    _build(page, width, 600, size, stored={"fcc.printerStatus.order": json.dumps([long_name, INDX])})
    rows = _fleet(indx_unbound=True)
    _feed(page, rows)
    short = {r["printer"]: r["tilesLeft"] for r in page.evaluate(NAMES_JS)}
    rows[long_name] = rows.pop(XL)
    _feed(page, rows)
    assert page.evaluate("() => document.getElementById('printer-status-widget').classList.contains('fcc-ps-tight')")
    got = {r["printer"]: r for r in page.evaluate(NAMES_JS)}
    assert not got[long_name]["whole"] and got[long_name]["infoInside"] and got[long_name]["infoAfter"], got
    assert abs(got[long_name]["tilesLeft"] - short[XL]) < 0.5, (got, short)
    assert got[INDX]["whole"], got
