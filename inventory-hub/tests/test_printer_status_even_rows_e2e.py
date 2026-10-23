"""Printer Status: even rows of tiles beside each printer's name, on the real
page (Derek, 2026-10-22).

Derek's call after the 2026-10-22 picture walk: when a printer's heads don't
fit on one row beside its name, split them into the fewest rows with EQUAL
counts (8 -> 4 + 4, 7 -> 4 + 3, 10 -> 5 + 5; never a lone tile), the tiles
staying beside the name column like the XL row; at every Text size and window
width, re-balanced on a resize and on a Text size change. The material line
under a tile's filament goes from line-height 1.1 to 1.2, so a "g" or "y"
never clips at Large.

The dev container's real page (Bootstrap, the heartbeat, the Settings path
for the size) with a made-up fleet in every source the widget reads
(conftest.stub_printer_fleet): an INDX-like printer with 8 heads and an
XL-like one with 5, as dev has. Pinned:
  - on Derek's 1600 x 1300 window, at each Text size: the 8 heads are 4 + 4
    and the 5 one row, all beside the name, inside the row;
  - 1024 px: 4 + 4 and 3 + 2 at Standard; 3 + 3 + 2 and 3 + 2 at Extra Large;
  - a Text size picked in Settings lays the rows out again at once, and a
    resize does too (to 1600 px: 4 + 4 and 5; to 800 px at Extra Large: under
    the name, 3 + 3 + 2 and 3 + 2);
  - collapsing and opening the widget, the ▲▼ reorder and a heartbeat that
    repaints keep the rows even;
  - the material line is 1.2 high at Large (the box text-truncate clips its
    "g" and "y" to), inside its tile;
  - every check holds the lines drawn to the ones the layout recorded
    (data-rows, data-place), and 7 and 10 heads at 1024 px Extra Large are
    3 + 2 + 2 and 3 + 3 + 2 + 2, each row starting in the first column (review,
    2026-10-22: with that line of the layout deleted, the 8 and 5 heads came
    out the same and every check passed; now that test is RED there, drawn
    3 + 3 + 1 and 3 + 3 + 3 + 1).
The rule itself and the narrow widths are test_printer_status_even_rows.py
(hermetic, under --offline).

READ-ONLY: every request that isn't a read is answered in the browser, and
the widget's sources answer the made-up fleet in this page only.

HEAD proof (0c965c7: the product edits stashed for one run against the live
container, restored after): all 8 RED. The 8 heads sat under the name: one
line of 8 at Small and Standard, 7 + 1 at Large and Extra Large, 5 + 3 at
1024 px (and the 5 heads 4 + 1 at 1024 px Extra Large, both under the name);
nothing was laid out again on a size change (the wait for 3 + 3 + 2 timed
out), and the material line was 1.1 high.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from conftest import stub_printer_fleet
from test_text_size_guard import _read_only

pytestmark = pytest.mark.usefixtures("require_server")

KEY = "fcc.textSize"
INDX = "ZZ Even INDX"
XL = "ZZ Even XL"


def _item(sid, material, grams=640):
    return {"id": sid, "color": "2A6F97", "color_direction": "longitudinal", "remaining_weight": grams,
            "initial_weight": 1000, "display": f"#{sid} Even Test {material}", "details": {"material": material}}


FLEET = {
    INDX: {"state": {"state": "IDLE", "is_active": False},
           "heads": [(f"ZE-{i}", i in (1, 4), _item(9300 + i, "Polycarbonate" if i == 1 else "PETG") if i in (1, 4) else None)
                     for i in range(1, 9)]},
    XL: {"state": {"state": "PRINTING", "is_active": True},
         "heads": [(f"ZX-{i}", True, _item(9310 + i, "PETG") if i == 2 else None) for i in range(1, 6)]},
}

# Per printer: the counts of each row of tiles, where they sit, and how many
# stick out of the printer's row.
LAYOUT_JS = r"""() => {
    const out = {};
    document.querySelectorAll('#printer-status-widget .fcc-ps-row').forEach((row) => {
        const nameR = row.querySelector('.fcc-ps-name-col').getBoundingClientRect();
        const rowR = row.getBoundingClientRect();
        const tiles = Array.from(row.querySelectorAll('.fcc-ps-th')).map((t) => t.getBoundingClientRect());
        const lines = [];
        tiles.forEach((r) => {
            const line = lines.find((l) => Math.abs(l.top - r.top) < 2);
            if (line) line.n++; else lines.push({ top: r.top, n: 1 });
        });
        lines.sort((a, b) => a.top - b.top);
        const beside = tiles.every((r) => r.left >= nameR.right - 0.5);
        const below = tiles.every((r) => r.top >= nameR.bottom - 0.5);
        const heads = row.querySelector('.fcc-ps-toolheads');
        out[row.dataset.printer] = { rows: lines.map((l) => l.n).join('+'),
            place: beside ? 'beside' : (below ? 'below' : 'mixed'),
            out: tiles.filter((r) => r.right > rowR.right + 0.5 || r.left < rowR.left - 0.5).length,
            data: heads.dataset.rows || null, dataPlace: heads.dataset.place || null };
    });
    return out;
}"""


def _drawn_as_recorded(got: dict) -> dict:
    """Every printer's tiles as the layout recorded them (review, 2026-10-22):
    the lines drawn are data-rows, where data-place says. Checks of fixed
    strings alone passed a layout whose CSS drew 3 + 3 + 1 for a planned
    3 + 2 + 2, or tiles that wrapped under the name while it said beside."""
    wrong = {k: v for k, v in got.items() if (v["rows"], v["place"]) != (v["data"], v["dataPlace"])}
    assert not wrong, f"drawn differently from what the layout recorded: {wrong}"
    return {k: {"rows": v["rows"], "place": v["place"], "out": v["out"]} for k, v in got.items()}


def _store(page: Page, name: str):
    page.add_init_script("(() => { try { localStorage.setItem(%r, %r); } catch (e) {} })();" % (KEY, name))


def _open(page: Page, base_url: str, size: str = "Standard", width: int = 1600, height: int = 1300, fleet=None):
    fleet = fleet or FLEET
    _read_only(page)
    stub_printer_fleet(page, fleet)
    _store(page, size)
    page.set_viewport_size({"width": width, "height": height})
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_function("(n) => typeof state !== 'undefined' && state.locationsLoaded"
                           " && document.querySelectorAll('#printer-status-widget .fcc-ps-row').length === n",
                           arg=len(fleet), timeout=45_000)
    page.wait_for_timeout(800)


def _layout(page: Page):
    return _drawn_as_recorded(page.evaluate(LAYOUT_JS))


def _settled(page: Page, want: dict):
    """Wait for {printer: rows}: a resize lays the rows out on the next frame."""
    page.wait_for_function("""([js, want]) => { const got = (eval(js))();
        return Object.entries(want).every(([k, v]) => got[k] && got[k].rows === v); }""",
                           arg=[LAYOUT_JS, want], timeout=5000)


@pytest.mark.parametrize("size", ["Small", "Standard", "Large", "Extra Large"])
def test_on_derek_s_window_8_heads_are_4_and_4_beside_the_name(page: Page, base_url: str, size):
    _open(page, base_url, size)
    got = _layout(page)
    assert got[INDX] == {"rows": "4+4", "place": "beside", "out": 0}, (size, got)
    assert got[XL] == {"rows": "5", "place": "beside", "out": 0}, (size, got)


def test_a_1024_px_window_splits_evenly_at_both_ends_of_the_sizes(page: Page, base_url: str):
    _open(page, base_url, "Standard", 1024, 900)
    got = _layout(page)
    assert (got[INDX]["rows"], got[INDX]["place"], got[XL]["rows"], got[XL]["place"]) == \
        ("4+4", "beside", "3+2", "beside"), got
    page.evaluate("() => window.fccTextSize.set('Extra Large')")
    got = _layout(page)
    assert (got[INDX]["rows"], got[INDX]["place"], got[XL]["rows"], got[XL]["place"]) == \
        ("3+3+2", "beside", "3+2", "beside"), got
    assert got[INDX]["out"] == 0 and got[XL]["out"] == 0, got


def test_a_size_picked_in_settings_and_a_resize_lay_the_rows_out_again(page: Page, base_url: str):
    _open(page, base_url, "Standard", 1024, 900)
    assert _layout(page)[INDX]["rows"] == "4+4"
    page.evaluate("() => window.openConfigModal()")
    sel = page.locator('.cfgset-input[data-key="fcc.textSize"]')
    sel.wait_for(state="visible", timeout=15_000)
    sel.select_option("Extra Large")
    page.wait_for_function("() => document.documentElement.getAttribute('data-fcc-text-size') === 'xlarge'",
                           timeout=3000)
    _settled(page, {INDX: "3+3+2", XL: "3+2"})
    page.keyboard.press("Escape")
    page.set_viewport_size({"width": 1600, "height": 1300})
    _settled(page, {INDX: "4+4", XL: "5"})
    page.set_viewport_size({"width": 800, "height": 1100})
    _settled(page, {INDX: "3+3+2", XL: "3+2"})
    got = _layout(page)
    assert got[INDX]["place"] == "below" and got[XL]["place"] == "below", got


def test_collapse_reorder_and_a_repaint_keep_the_rows_even(page: Page, base_url: str):
    _open(page, base_url)
    page.evaluate("() => window.togglePrinterStatusWidget()")
    page.wait_for_function("() => document.getElementById('printer-status-widget').classList.contains('collapsed')")
    page.set_viewport_size({"width": 1024, "height": 900})
    page.evaluate("() => window.togglePrinterStatusWidget()")
    _settled(page, {INDX: "4+4", XL: "3+2"})
    first = page.locator("#printer-status-widget .fcc-ps-row").first.get_attribute("data-printer")
    page.evaluate("(n) => window.movePrinterStatusRow(n, 1)", first)
    assert page.locator("#printer-status-widget .fcc-ps-row").first.get_attribute("data-printer") != first
    assert (_layout(page)[INDX]["rows"], _layout(page)[XL]["rows"]) == ("4+4", "3+2")
    # A heartbeat with a change (another spool on the INDX) repaints the rows.
    # The repaint and the read in one turn of the page's JS: the next real
    # tick answers the stub fleet again and would repaint it back.
    got = page.evaluate("""([indx, xl, js]) => {
        const heads = (prefix, n, loaded) => Array.from({ length: n }, (_, i) => ({ id: prefix + '-' + (i + 1),
            position: i, unbound: false, loaded_count: loaded.includes(i) ? 1 : 0,
            item: loaded.includes(i) ? { id: 9400 + i, color: '7B2CBF', remaining_weight: 300, initial_weight: 1000,
                                          display: '#' + (9400 + i), details: { material: 'PLA' } } : null }));
        const rows = {}; rows[indx] = { state: { state: 'IDLE', is_active: false }, toolheads: heads('ZE', 8, [0, 1, 2]) };
        rows[xl] = { state: { state: 'IDLE', is_active: false }, toolheads: heads('ZX', 5, [4]) };
        window.refreshPrinterStatusWidgetFromAggregate(rows);
        return { repainted: !!document.querySelector("#printer-status-widget .fcc-ps-th[data-spool-id='9402']"),
                 layout: (eval(js))() }; }""", [INDX, XL, LAYOUT_JS])
    assert got["repainted"], got
    _drawn_as_recorded(got["layout"])
    assert (got["layout"][INDX]["rows"], got["layout"][XL]["rows"]) == ("4+4", "3+2"), got


# Counts a plain grid fill draws unevenly (3 + 3 + 1, 3 + 3 + 3 + 1) where three
# tiles fit beside the name: only each row's first tile starting in column 1
# draws the rule's 3 + 2 + 2 (review, 2026-10-22: the 8 and 5 heads above come
# out the same either way).
UNEVEN = {
    "ZZ Seven": {"state": {"state": "IDLE", "is_active": False},
                 "heads": [(f"ZS-{i}", True, _item(9320 + i, "PETG") if i == 1 else None) for i in range(1, 8)]},
    "ZZ Ten": {"state": {"state": "IDLE", "is_active": False},
               "heads": [(f"ZT-{i}", True, None) for i in range(1, 11)]},
}


def test_seven_and_ten_heads_start_each_row_in_the_first_column(page: Page, base_url: str):
    _open(page, base_url, "Extra Large", 1024, 900, fleet=UNEVEN)
    got = _layout(page)
    assert got == {"ZZ Seven": {"rows": "3+2+2", "place": "beside", "out": 0},
                   "ZZ Ten": {"rows": "3+3+2+2", "place": "beside", "out": 0}}, got


def test_the_material_line_is_1_2_high_at_large(page: Page, base_url: str):
    """Its own box (text-truncate clips to it) is 1.2 lines high, and the
    whole box is inside its tile."""
    _open(page, base_url, "Large")
    lines = page.evaluate("""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-chip-mat'))
        .map((el) => { const cs = getComputedStyle(el); const tile = el.closest('.fcc-ps-th').getBoundingClientRect();
            const r = el.getBoundingClientRect();
            return { text: el.textContent.trim(), ratio: parseFloat(cs.lineHeight) / parseFloat(cs.fontSize),
                     high: el.clientHeight >= parseFloat(cs.lineHeight) - 0.5,
                     inTile: r.bottom <= tile.bottom + 0.5 && r.top >= tile.top - 0.5 }; })""")
    assert {ln["text"] for ln in lines} >= {"PETG", "Polycarbonate"}, lines
    for ln in lines:
        assert ln["ratio"] == pytest.approx(1.2, abs=0.01), ln
        assert ln["high"] and ln["inTile"], ln
