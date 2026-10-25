"""Printer Status tiles: no dot beside the spool's name (Derek, 2026-10-24).

Seeing the name-first layout: "the color swatch next to the name is pretty
close if not sometimes entering the border for the toolhead. Also, Names are
a bit tight in there". He chose to drop the small swatch dot beside the name
in the EXPANDED tiles only: the band across the tile's top already shows the
filament's colour; the collapsed strip keeps its dots; no tile changes size
(the INDX keeps one row of 8 at Small and Standard on 1600 px); the tile's
hover text still names the spool, in full, and its weight.

The dot (makeSwatchHtml's span, 12 px and its border) sat against the tile's
left border with a 0.5rem gap before the name. Now the name starts where the
head's label in the band above it starts (the band's own 6 px inset), the
material line under it, so the head, the filament and its material read down
one edge, clear of the border; the name takes the rest of the line up to the
weight, which stays where it was.

Hermetic, and it RUNS under --offline: the widget page of
test_printer_status_even_rows.py (the real global.css, inv_core.js,
ui_builder.js, inv_printer_status.js, text_size.js and cancel_review.js in a
chromium with no route to any network), fed made-up printers as the heartbeat
feeds them. Pinned, at every Text size on 1600 x 1300:
  - no dot inside any expanded tile, whatever it holds: one colour, three
    colours, no colour at all (a spool Spoolman told nothing about), an
    archived spool, a 59-character name, 0, 12, 85, 703, 999 and 1000 g, no
    weight, an unbound head, a doubled one;
  - the name is the first thing on its line and starts where the head's
    label does, 6 px in from the tile's border, and the material line starts
    there too; a name too long for its line ends in "…" right before the
    weight, taking all the room the weight leaves; the weight is whole and
    inside the tile; "Transition Spool" (dev's XL-4) is whole at Small and
    Standard (it ended "Transition Sp…" beside the dot);
  - the collapsed strip keeps one dot, first, on every head's chip: the
    filament's colours on a loaded head (a gradient for several), the striped
    one on an empty head;
  - every tile keeps d554dc2's size, and each printer's lines of tiles their
    heights; the 8 heads are one row at Small and Standard and 4 + 4 at Large
    and Extra Large, the 5 one row; the empty, "? not read" and unbound tiles
    still say so;
  - the hover text still names the head, the spool in full and its weight.
The same on the real page (Bootstrap, the dev container) is
test_printer_status_tile_name_e2e.py.

RED on d554dc2 (this file in a throwaway worktree of it): 10 of 19, no dot
at every size (a dot in every loaded tile), the name's place at every size
(the dot came first on its line, the name 18 to 20 px further in than the
head's label) and "Transition Spool" at Small and Standard. The 9 that hold
there are guards for what this must not change: the collapsed strip's dots
(4), the tiles' sizes and rows (4) and the hover text. Mutations of the
finished code, one at a time: the dot put back fails the same 10; the name
flush against the border (no 6 px inset), the material line padded 20 px
again and a dot shrunk to nothing but kept with its gap each fail the name's
place at every size (4); the dot hidden by CSS instead of left out fails
nothing (the checks read what is drawn), nor does the name capped at
8.75rem again (the room the weight leaves is under that at every size).
"""
from __future__ import annotations

import pytest

from test_printer_status_even_rows import SIZES, _build, _feed, _size

TEST = "ZZ Tile Test"
XL = "ZZ Tile XL"
LONG = "A Filament Whose Name Goes On And On Past Any Sensible End!"
assert len(LONG) == 59  # longer than a tile's line at every size


def _item(sid, colour, name, grams, material=None, direction="longitudinal", **extra):
    item = {"id": sid, "display": f"#{sid} {name}".strip(), "color": colour, "color_direction": direction,
            "remaining_weight": grams, "initial_weight": 1000}
    if material is not None:
        item["details"] = {"material": material}
    item.update(extra)
    return item


def _head(hid, pos, item=None, **extra):
    head = {"id": hid, "position": pos, "unbound": False, "item": item, "loaded_count": 1 if item else 0}
    head.update(extra)
    return head


# The heads a tile can show. Spools: one colour (703 g), three colours across
# the spool (1000 g, dev's XL-4 name), nothing known (no colour, no name, no
# weight), archived with a 59-character name at 0 g, 85 g (amber) with a
# descender in its material; then an empty head, one Spoolman didn't answer
# for and an unbound empty one. The XL: an unbound head with a spool (its 🔗
# line), a doubled head (its ⚠️ line), two colours along the spool with no
# material, and two empty heads.
FLEET = {
    TEST: {"state": {"state": "IDLE", "is_active": False}, "toolheads": [
        _head("ZT-1", 0, _item(9601, "2a6f97", "Galaxy Black", 703, "PETG")),
        _head("ZT-2", 1, _item(9602, "ff0000,ffff00,0000ff", "Transition Spool", 1000, "PLA", direction="coaxial")),
        _head("ZT-3", 2, {"id": 9603, "color": "", "display": "", "remaining_weight": None, "initial_weight": None}),
        _head("ZT-4", 3, _item(9604, "e0e0e0", LONG, 0, "PLA Silk", archived=True)),
        _head("ZT-5", 4, _item(9605, "f77f00", "Sunset Orange", 85, "Polycarbonate")),
        _head("ZT-6", 5),
        _head("ZT-7", 6, unread=True),
        _head("ZT-8", 7, unbound=True),
    ]},
    XL: {"state": {"state": "PRINTING", "is_active": True}, "toolheads": [
        _head("ZU-1", 0, _item(9611, "3a3a3a", "Fiberlogy Easy PETG Graphite", 999, "PETG"), unbound=True),
        _head("ZU-2", 1, _item(9612, "f5c211", "Signal Yellow", 12, "ASA"), loaded_count=2, loaded_ids=[9612, 9613]),
        _head("ZU-3", 2, _item(9613, "ff00ff,00ffff", "Two Tone", 450)),
        _head("ZU-4", 3),
        _head("ZU-5", 4),
    ]},
}
LOADED = {"ZT-1", "ZT-2", "ZT-3", "ZT-4", "ZT-5", "ZU-1", "ZU-2", "ZU-3"}
# The name each loaded tile shows (the colour name, else the display without
# its #id).
NAMES = {"ZT-1": "Galaxy Black", "ZT-2": "Transition Spool", "ZT-3": "", "ZT-4": LONG, "ZT-5": "Sunset Orange",
         "ZU-1": "Fiberlogy Easy PETG Graphite", "ZU-2": "Signal Yellow", "ZU-3": "Two Tone"}
WEIGHTS = {"ZT-1": "703g", "ZT-2": "1000g", "ZT-3": "---", "ZT-4": "0g", "ZT-5": "85g", "ZU-1": "999g",
           "ZU-2": "12g", "ZU-3": "450g"}

# d554dc2's tiles here, before the dot went (the same at every size: a tile is
# 10.5rem wide): each printer's lines of tiles, the tiles on each and each
# line's height in px. The dot (14 px) was never taller than the name's line
# (1.2 lines of 0.85rem: 16.32 px at Standard), so taking it out moves
# nothing up or down. (The tiles of a line are as tall as its tallest: the
# XL's line holds the 🔗 and ⚠️ tiles, a line taller.)
D554DC2 = {
    "Small": {TEST: ("8", [85.66]), XL: ("5", [103.66])},
    "Standard": {TEST: ("8", [86.63]), XL: ("5", [105.81])},
    "Large": {TEST: ("4+4", [90.69, 90.69]), XL: ("5", [112.3])},
    "Extra Large": {TEST: ("4+4", [96.28, 96.28]), XL: ("5", [120.28])},
}

# Inside each expanded tile: its size, its content edges (inside the border),
# the band's own inset, anything round in it (a dot: makeSwatchHtml's span is
# border-radius 50%), and where the head's label, the name's line, the name,
# the weight and the material line sit.
TILE_JS = r"""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-body .fcc-ps-th')).map((t) => {
    const R = (el) => { if (!el) return null; const r = el.getBoundingClientRect();
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height }; };
    const cs = getComputedStyle(t);
    const tile = t.getBoundingClientRect();
    const dots = Array.from(t.querySelectorAll('*')).filter((el) => {
        const s = getComputedStyle(el); const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden'
            && (s.borderTopLeftRadius === '50%' || /swatch/.test(String(el.className))); }).length;
    const band = t.querySelector('.fcc-ps-th-body');
    const chip = t.querySelector('.fcc-ps-chip');
    const line = chip ? chip.firstElementChild : null;
    const kids = line ? Array.from(line.children).filter((k) => getComputedStyle(k).display !== 'none') : [];
    const name = kids.find((k) => k.classList.contains('text-truncate')) || null;
    const weight = kids.find((k) => k.classList.contains('ms-auto')) || null;
    const mat = t.querySelector('.fcc-ps-chip-mat');
    return {
        th: t.dataset.toolhead, loaded: !!t.dataset.spoolId, title: t.getAttribute('title') || '',
        w: tile.width, h: tile.height, dots,
        inner: { left: tile.left + parseFloat(cs.borderLeftWidth) + parseFloat(cs.paddingLeft),
                 right: tile.right - parseFloat(cs.borderRightWidth) - parseFloat(cs.paddingRight) },
        bandInset: band ? parseFloat(getComputedStyle(band).paddingLeft) : null,
        label: R(t.querySelector('.fcc-ps-th-id')), line: R(line), kids: kids.length, first: !!name && kids[0] === name,
        gap: line ? parseFloat(getComputedStyle(line).columnGap) : null,
        nameLH: name ? parseFloat(getComputedStyle(name).lineHeight) : null,
        name: name ? Object.assign(R(name), { text: name.textContent, cut: name.scrollWidth > name.clientWidth + 0.5,
                                              ellipsis: getComputedStyle(name).textOverflow === 'ellipsis' }) : null,
        weight: weight ? Object.assign(R(weight), { text: weight.textContent.trim(),
                                                    whole: weight.scrollWidth <= weight.clientWidth + 0.5 }) : null,
        // The material line's text starts at its content edge (it was padded 20 px in, past the dot).
        mat: mat ? Object.assign(R(mat), { text: mat.textContent.trim(), textLeft: mat.getBoundingClientRect().left
            + parseFloat(getComputedStyle(mat).borderLeftWidth) + parseFloat(getComputedStyle(mat).paddingLeft) }) : null,
        chips: Array.from(t.querySelectorAll('.fcc-ps-th-chip')).map((c) => c.textContent.trim()),
    };
})"""

# Each printer's lines of tiles (the count on each and its height), the
# tiles' widths and the root font size.
SIZES_JS = r"""() => {
    const out = { root: parseFloat(getComputedStyle(document.documentElement).fontSize), printers: {} };
    document.querySelectorAll('#printer-status-widget .fcc-ps-row').forEach((row) => {
        const tiles = Array.from(row.querySelectorAll('.fcc-ps-th')).map((t) => t.getBoundingClientRect());
        const lines = [];
        tiles.forEach((r) => { const l = lines.find((x) => Math.abs(x.top - r.top) < 2);
            if (l) { l.n++; l.h = Math.max(l.h, r.height); } else lines.push({ top: r.top, n: 1, h: r.height }); });
        lines.sort((a, b) => a.top - b.top);
        out.printers[row.dataset.printer] = { rows: lines.map((l) => l.n).join('+'),
            heights: lines.map((l) => Math.round(l.h * 100) / 100),
            widths: Array.from(new Set(tiles.map((r) => Math.round(r.width * 100) / 100))) };
    });
    return out;
}"""

# Each head's chip in the collapsed strip: its round dots, whether the first
# is the chip's first child, its width and what it is filled with.
STRIP_DOTS_JS = r"""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-header-chips .fcc-ps-mini')).map((m) => {
    const dots = Array.from(m.querySelectorAll('span')).filter((el) => { const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && getComputedStyle(el).borderTopLeftRadius === '50%'; });
    const d = dots[0]; const s = d ? getComputedStyle(d) : null;
    return { th: m.dataset.toolhead, dots: dots.length, first: !!d && m.firstElementChild === d,
             w: d ? d.getBoundingClientRect().width : 0,
             fill: s ? (s.backgroundImage !== 'none' ? s.backgroundImage : s.backgroundColor) : null };
})"""


@pytest.fixture
def widget(isolated_page):
    page = isolated_page
    _build(page)
    yield page
    assert page.evaluate("window.__errors") == []


def _tiles(page, size):
    page.set_viewport_size({"width": 1600, "height": 1300})
    _size(page, size)
    _feed(page, FLEET)
    tiles = {t["th"]: t for t in page.evaluate(TILE_JS)}
    assert {k for k, t in tiles.items() if t["loaded"]} == LOADED, tiles
    return tiles


@pytest.mark.parametrize("size", SIZES)
def test_no_dot_inside_an_expanded_tile(widget, size):
    """Whatever the head holds, its tile has no dot: the band across its top
    shows the filament's colour (Derek: the dot came close to, "if not
    sometimes entering", the tile's border)."""
    tiles = _tiles(widget, size)
    dotted = {k: t["dots"] for k, t in tiles.items() if t["dots"]}
    assert not dotted, f"a dot inside an expanded tile at {size}: {dotted}"


@pytest.mark.parametrize("size", SIZES)
def test_the_name_starts_under_the_head_s_label_and_takes_the_dot_s_room(widget, size):
    """The name is the first thing on its line and starts where the head's
    label does (the band's 6 px inset from the border), with the material
    line; a name too long for its line ends in "…" right before the weight,
    so it has every px the weight leaves; the weight is whole, inside the
    tile, and the line no taller than the name's own text."""
    tiles = _tiles(widget, size)
    for k in sorted(LOADED):
        t = tiles[k]
        where = (size, k, t)
        assert t["kids"] == 2 and t["first"], f"the name should be the first thing on its line: {where}"
        assert t["name"]["text"] == NAMES[k] and t["weight"]["text"] == WEIGHTS[k], where
        assert t["name"]["left"] == pytest.approx(t["label"]["left"], abs=0.5), f"the name should start under the head's label: {where}"
        assert t["name"]["left"] - t["inner"]["left"] == pytest.approx(t["bandInset"], abs=0.5), where
        assert t["bandInset"] >= 4, f"the name should be clear of the border: {where}"
        if t["mat"]:
            assert t["mat"]["textLeft"] == pytest.approx(t["name"]["left"], abs=0.5), f"the material line should start under the name: {where}"
        assert t["weight"]["whole"] and t["weight"]["right"] <= t["inner"]["right"] + 0.5, f"the weight is cut or outside the tile: {where}"
        assert t["name"]["right"] + t["gap"] <= t["weight"]["left"] + 0.5, f"the name runs into the weight: {where}"
        room = t["line"]["right"] - t["name"]["left"] - t["weight"]["width"] - t["gap"]
        if t["name"]["cut"]:
            assert t["name"]["ellipsis"], where
            assert t["name"]["width"] == pytest.approx(room, abs=0.5), f"a cut name should have all the room the weight leaves: {where}"
        assert t["line"]["height"] == pytest.approx(t["nameLH"], abs=0.5), f"the name's line should be as tall as its text: {where}"
    # The long ones are cut, the short ones whole.
    assert tiles["ZT-4"]["name"]["cut"] and tiles["ZU-1"]["name"]["cut"], (size, tiles["ZT-4"], tiles["ZU-1"])
    assert not any(tiles[k]["name"]["cut"] for k in ("ZT-1", "ZT-3", "ZT-5", "ZU-2", "ZU-3")), size


@pytest.mark.parametrize("size", ["Small", "Standard"])
def test_transition_spool_is_whole_beside_four_digits(widget, size):
    """Dev's XL-4 holds a spool named "Transition Spool": beside the dot it
    read "Transition Sp…" (2 px short at Standard). With the dot's room it is
    whole, even beside a four-digit weight."""
    t = _tiles(widget, size)["ZT-2"]
    assert t["weight"]["text"] == "1000g" and not t["name"]["cut"], (size, t)


@pytest.mark.parametrize("size", SIZES)
def test_the_collapsed_strip_keeps_its_dots(widget, size):
    """Minimized, a head is a chip in the strip: its dot first, then its id
    and its weight. Every chip keeps its dot: the filament's colours on a
    loaded head (a gradient where it has several), the striped one on an
    empty head."""
    page = widget
    _tiles(page, size)
    page.evaluate("() => window.togglePrinterStatusWidget()")
    page.wait_for_function("() => document.getElementById('printer-status-widget').classList.contains('collapsed')")
    chips = {c["th"]: c for c in page.evaluate(STRIP_DOTS_JS)}
    heads = [h["id"] for p in FLEET.values() for h in p["toolheads"]]
    assert sorted(chips) == sorted(heads), chips
    for k, c in chips.items():
        assert c["dots"] == 1 and c["first"] and c["w"] >= 11.5, f"{k}'s chip lost its dot at {size}: {c}"
    for k in ("ZT-2", "ZU-3"):
        assert "gradient" in chips[k]["fill"], f"{k} has several colours: {chips[k]}"
    for k in ("ZT-6", "ZT-7", "ZT-8", "ZU-4", "ZU-5"):
        assert "repeating-linear-gradient" in chips[k]["fill"], f"{k} is empty: {chips[k]}"


@pytest.mark.parametrize("size", SIZES)
def test_every_tile_keeps_its_size_and_rows(widget, size):
    """No tile changes size (Derek: the INDX keeps one row of 8 at Small and
    Standard on 1600 px): every tile is 10.5rem wide, each printer's lines of
    tiles are as tall as on d554dc2 and hold as many tiles; the tiles with no
    spool still say why."""
    page = widget
    tiles = _tiles(page, size)
    got = page.evaluate(SIZES_JS)
    for name, (rows, heights) in D554DC2[size].items():
        p = got["printers"][name]
        assert p["rows"] == rows, (size, name, p)
        assert p["widths"] == [pytest.approx(10.5 * got["root"], abs=0.01)], (size, name, p)
        assert p["heights"] == [pytest.approx(h, abs=0.5) for h in heights], (size, name, p)
    assert tiles["ZT-6"]["chips"] == ["empty"] and tiles["ZT-7"]["chips"] == ["? not read"], (tiles["ZT-6"], tiles["ZT-7"])
    assert tiles["ZT-8"]["chips"] == ["🔗 no bound slot"] and tiles["ZU-1"]["chips"] == ["🔗 no bound slot"]
    assert tiles["ZU-2"]["chips"] == ["⚠️ 2 spools"], tiles["ZU-2"]


def test_the_hover_text_still_names_the_spool_in_full(widget):
    """Hovering a tile says which head, the spool in full (the long name
    whole, not cut) and its weight."""
    tiles = _tiles(widget, "Standard")
    assert tiles["ZT-4"]["title"] == f"ZT-4 — #9604 {LONG} — 0g remaining (click to Quick-Swap)", tiles["ZT-4"]
    assert tiles["ZT-2"]["title"] == "ZT-2 — #9602 Transition Spool — 1000g remaining (click to Quick-Swap)"
    assert tiles["ZT-3"]["title"] == "ZT-3 — #9603 — 0g remaining (click to Quick-Swap)", tiles["ZT-3"]
