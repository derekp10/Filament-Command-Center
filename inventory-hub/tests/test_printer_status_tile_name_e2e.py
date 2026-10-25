"""Printer Status tiles on the real page: no dot beside the spool's name
(Derek, 2026-10-24: "the color swatch next to the name is pretty close if not
sometimes entering the border for the toolhead. Also, Names are a bit tight
in there"). The dev container's dashboard (Bootstrap, the heartbeat, the
Settings path for the Text size) with a made-up fleet in every source the
widget reads (conftest.stub_printer_fleet): an INDX-like printer with 8 heads
and an XL-like one with 5, whose XL-4 and XL-5 hold dev's two Transition
spools. Pinned, at every Text size on Derek's 1600 x 1300 window:
  - no dot inside any expanded tile (one colour, several colours, a spool
    Spoolman told nothing about, an archived 59-character name, an unbound
    head with a spool);
  - the name is the first thing on its line and starts where the head's
    label does (6 px in from the border, the band's inset), the material line
    under it; a long name ends in "…" right before the weight, with all the
    room the weight leaves; the weight is whole and inside the tile;
  - nothing else moves: every tile keeps d554dc2's size, the 8 heads one row
    at Small and Standard and 4 + 4 at Large and Extra Large, the 5 one row,
    the empty and unbound tiles say so, and minimized, every head's chip in
    the strip keeps its dot.
The fleet's every tile kind at every size, the hover text and the 2 px that
cut "Transition Spool" are test_printer_status_tile_name.py (hermetic, under
--offline).

READ-ONLY: every request that isn't a read is answered in the browser, and
the widget's sources answer the made-up fleet in this page only.

RED on d554dc2: with d554dc2's global.css and ui_builder.js on disk for one
run (the container serves the checkout live; this checkout's files restored
afterwards, their checksums checked), 4 of 8: a dot in every loaded tile at
every size. The 4 that hold there are the "nothing else moves" guards, so
the sizes above are d554dc2's.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from test_printer_status_even_rows_e2e import _layout, _open
from test_printer_status_tile_name import LONG, SIZES_JS, STRIP_DOTS_JS, TILE_JS

pytestmark = pytest.mark.usefixtures("require_server")

SIZES = ("Small", "Standard", "Large", "Extra Large")
INDX = "ZZ Tile INDX"
XL = "ZZ Tile XL"


def _item(sid, colour, name, grams, material=None, direction="longitudinal", **extra):
    item = {"id": sid, "display": f"#{sid} {name}".strip(), "color": colour, "color_direction": direction,
            "remaining_weight": grams, "initial_weight": 1000}
    if material is not None:
        item["details"] = {"material": material}
    item.update(extra)
    return item


# Each head: (id, bound to a box slot, the spool on it).
FLEET = {
    INDX: {"state": {"state": "IDLE", "is_active": False}, "heads": [
        ("ZE-1", True, _item(9701, "2a6f97", "Galaxy Black", 703, "PETG")),
        ("ZE-2", True, {"id": 9702, "color": "", "display": "", "remaining_weight": None, "initial_weight": None}),
        ("ZE-3", True, _item(9703, "e0e0e0", LONG, 0, "PLA Silk", archived=True)),
        ("ZE-4", False, _item(9704, "3a3a3a", "Fiberlogy Easy PETG Graphite", 999, "PETG")),
        ("ZE-5", True, None), ("ZE-6", True, None), ("ZE-7", False, None), ("ZE-8", True, None)]},
    XL: {"state": {"state": "IDLE", "is_active": False}, "heads": [
        ("ZX-1", True, None), ("ZX-2", True, None), ("ZX-3", True, None),
        ("ZX-4", True, _item(9714, "6a0dad,ff0000,ff8c00,ffff00,00ff00,0000ff", "Transition Spool", 703,
                             "For Infill PETG", direction="coaxial")),
        ("ZX-5", True, _item(9715, "6a0dad,ff0000,ff8c00,ffff00,00ff00,0000ff", "Transition (Color Change)", 423,
                             "PLA", direction="coaxial"))]},
}
LOADED = {"ZE-1", "ZE-2", "ZE-3", "ZE-4", "ZX-4", "ZX-5"}

# d554dc2's tiles on this page, before the dot went: each printer's lines of
# tiles (the count on each) and each line's height in px (a line is as tall
# as its tallest tile: the INDX's holds ZE-4's 🔗 line).
D554DC2 = {
    "Small": {INDX: ("8", [103.66]), XL: ("5", [85.66])},
    "Standard": {INDX: ("8", [105.81]), XL: ("5", [86.63])},
    "Large": {INDX: ("4+4", [112.3, 74.61]), XL: ("5", [90.69])},
    "Extra Large": {INDX: ("4+4", [120.28, 78.5]), XL: ("5", [96.28])},
}


def _page(page: Page, base_url: str, size: str):
    _open(page, base_url, size, fleet=FLEET, reviews={})
    tiles = {t["th"]: t for t in page.evaluate(TILE_JS)}
    assert {k for k, t in tiles.items() if t["loaded"]} == LOADED, tiles
    return tiles


@pytest.mark.parametrize("size", SIZES)
def test_no_dot_and_the_name_starts_under_the_head_s_label(page: Page, base_url: str, size):
    tiles = _page(page, base_url, size)
    dotted = {k: t["dots"] for k, t in tiles.items() if t["dots"]}
    assert not dotted, f"a dot inside an expanded tile at {size}: {dotted}"
    for k in sorted(LOADED):
        t = tiles[k]
        where = (size, k, t)
        assert t["kids"] == 2 and t["first"], f"the name should be the first thing on its line: {where}"
        assert t["name"]["left"] == pytest.approx(t["label"]["left"], abs=0.5), f"the name should start under the head's label: {where}"
        assert t["name"]["left"] - t["inner"]["left"] == pytest.approx(t["bandInset"], abs=0.5), where
        if t["mat"]:
            assert t["mat"]["textLeft"] == pytest.approx(t["name"]["left"], abs=0.5), f"the material line should start under the name: {where}"
        assert t["weight"]["whole"] and t["weight"]["right"] <= t["inner"]["right"] + 0.5, f"the weight is cut or outside the tile: {where}"
        room = t["line"]["right"] - t["name"]["left"] - t["weight"]["width"] - t["gap"]
        if t["name"]["cut"]:
            assert t["name"]["width"] == pytest.approx(room, abs=0.5), f"a cut name should have all the room the weight leaves: {where}"
        assert t["line"]["height"] == pytest.approx(t["nameLH"], abs=0.5), where
    assert tiles["ZE-3"]["name"]["cut"] and tiles["ZX-5"]["name"]["cut"], size


@pytest.mark.parametrize("size", SIZES)
def test_nothing_else_moves(page: Page, base_url: str, size):
    """Every tile keeps its size and every printer its rows; the empty and
    the unbound tiles still say so; minimized, every head's chip keeps its
    dot, first."""
    tiles = _page(page, base_url, size)
    got = page.evaluate(SIZES_JS)
    for name, (rows, heights) in D554DC2[size].items():
        p = got["printers"][name]
        assert p["rows"] == rows, (size, name, p)
        assert p["widths"] == [pytest.approx(10.5 * got["root"], abs=0.01)], (size, name, p)
        assert p["heights"] == [pytest.approx(h, abs=0.5) for h in heights], (size, name, p)
    layout = _layout(page)
    assert (layout[INDX]["rows"], layout[XL]["rows"]) == (D554DC2[size][INDX][0], D554DC2[size][XL][0]), layout
    assert [tiles[k]["chips"] for k in ("ZE-5", "ZE-7", "ZE-4")] == [["empty"], ["🔗 no bound slot"], ["🔗 no bound slot"]]
    page.locator("#printer-status-widget .fcc-ps-header-bar").click()
    page.wait_for_function("() => document.getElementById('printer-status-widget').classList.contains('collapsed')")
    chips = {c["th"]: c for c in page.evaluate(STRIP_DOTS_JS)}
    assert sorted(chips) == sorted(h for p in FLEET.values() for (h, _b, _i) in p["heads"]), chips
    for k, c in chips.items():
        assert c["dots"] == 1 and c["first"] and c["w"] >= 11.5, f"{k}'s chip lost its dot at {size}: {c}"
    assert "gradient" in chips["ZX-4"]["fill"] and "repeating-linear-gradient" in chips["ZX-1"]["fill"], chips
