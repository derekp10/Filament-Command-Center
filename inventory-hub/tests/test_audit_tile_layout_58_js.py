"""Group 58, Derek's look of 2026-11-04 (T1): the audit panel's tiles laid out again.

"Yes that seems fine. I'm ok with them being a bit longer, if we want to try and move some
of the stuff on the sides to the top and bottom, like the label buttons, and the scanned
notifications. That would give us a little more room for the full name. Id also say let it
wrap too. but we'd have to try and keep the box size consistant among all of them though.
otherwise the grid will just look odd."

So every tile (Not scanned, Found, Extra, Loaded from here):
- its name takes the tile's width and wraps, two lines at most (the rest cut, the whole name
  in its title);
- its words ("✅ scanned", "found, no label read", "⚠️ extra", "🔗 loaded") and a found tile's
  🏷️ sit in a row under the name, the 🏷️ at that row's end; a tile not yet found keeps its QR
  at its side;
- every tile in a group's grid is one height, and a found tile is as tall as one not yet
  found;
- the row under the name is no part of a found tile's press button, so a tap a little off
  the 🏷️ presses nothing (a press took the find back, and its label read with it); the 🏷️ is
  a 44 px target at least on a touch screen.

On a real DOM and the REAL routes, hermetic (test_audit_find_and_tiles_58_js's `live`):
the real overlay_mount.js, inv_core.js, inv_cmd.js, the real scan accumulator and
global.css, over tests/spoolman_extra_fake.SpoolmanHTTPFake, so it runs under --offline.
The page has no Bootstrap: BOOTSTRAP_BASE is Bootstrap 5.3's own reboot (box-sizing, the
body's font and line height) and its .text-truncate, which the tile's name used to wear, so
the tiles measure here as on the dashboard. The real dashboard's look is in the round's
pictures; the arrows, Tab, Enter and Space, a scan's Enter and a double click on a tile or
its 🏷️ stay pinned by test_audit_panel_look_58_js.py, test_audit_no_label_58_js.py and
test_audit_double_click_58_e2e.py.

RED on 826992a unless a test says it pins what was already right.
"""
from __future__ import annotations

from test_audit_find_and_tiles_58_js import begin, live, posts, scanned  # noqa: F401  (live: the fixture)
from test_audit_no_label_58_js import BODY, PAST_A_DOUBLE_PRESS, cell, tile, tile_says
from test_audit_panel_58_js import audit  # noqa: F401  (the fixture `live` stands on)
from test_audit_session_58 import add_spool, env, session  # noqa: F401  (env: the fixture)
from test_scanner_safe_dialogs_61_js import page61  # noqa: F401  (the fixture `audit` stands on)

# Bootstrap 5.3.0's reboot (dist/css/bootstrap.css: `*, ::after, ::before`, `body`) and its
# .text-truncate utility, as the dashboard loads them.
BOOTSTRAP_BASE = """*, ::after, ::before { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", "Noto Sans",
       "Liberation Sans", Arial, sans-serif; font-size: 1rem; font-weight: 400; line-height: 1.5; }
.text-truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }"""

LONG = "Glow in the Dark Green (Luminous) with Extra Sparkle Flakes"
NAMES = {57: "Galaxy Black", 99: "Space Grey", 134: LONG, 150: "Jade White",
         160: "Rainbow Gradient (Red / Orange / Yellow / Green / Blue / Indigo / Violet) Silk Dual Colour Special"}
TAG_URL = "/api/audit/needs_label"
UNTAG_URL = "/api/audit/needs_label_undo"
FOUND_URL = "/api/audit/found"


def tag(sid):
    return f"[data-audit-tag='{sid}']"


def shelf(env):
    """Five spools in a box, names short and long; #160's is longer than two lines."""
    for slot, (sid, name) in enumerate(NAMES.items(), start=1):
        add_spool(env, sid, "LR-MDB-1", container_slot=str(slot), name=name)


def setup(live, env, width=1600, height=1300):
    live.set_viewport_size({"width": width, "height": height})
    live.add_style_tag(content=BOOTSTRAP_BASE)
    shelf(env)
    begin(live, env)
    scanned(live, "ID:57", "barcode")                   # found by its label: "✅ scanned"
    for sid in (134, 160):                              # found by hand: long, longer than two lines
        scanned(live, f"ID:{sid}")
    live.wait_for_selector(tag(160))


BOX = "(s) => { const r = document.querySelector(s).getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; }"
# The box of the innermost element under `root` whose own text holds `text`: found by its
# words, so the measure reads a tile drawn either way (before this round, and now).
TEXT_BOX = r"""([root, text]) => { const r = document.querySelector(root);
    const walker = document.createTreeWalker(r, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
        if (!node.data.includes(text)) continue;
        const b = node.parentElement.getBoundingClientRect();
        return [b.left, b.top, b.right, b.bottom];
    }
    return null; }"""


def name_of(sid):
    """The tile's name: the one element in its press button with a title of its own."""
    return f"{tile(sid)} span[title]"


def lines(page, sel):
    """How many lines the element's text takes on screen, and whether any of it is hidden."""
    return page.evaluate("""(s) => { const e = document.querySelector(s);
        const lh = parseFloat(getComputedStyle(e).lineHeight);
        return { lines: Math.round(e.clientHeight / lh), hidden: e.scrollHeight > e.clientHeight + 1
                                                                   || e.scrollWidth > e.clientWidth + 1 }; }""", sel)


def test_a_long_name_wraps_instead_of_being_cut(live, env):
    """At 1600 x 1300 a found tile's name that needs two lines takes two, all of it shown, on
    a tile with a 🏷️ and on one not yet found with its QR. RED on 826992a: one line, cut
    (.text-truncate), the 🏷️ taking the room."""
    setup(live, env)
    for sid in (134, 99):
        live.wait_for_selector(name_of(sid))
    long_name = live.text_content(name_of(134))
    assert LONG.lower() in long_name.lower()             # the display title-cases a colour
    assert lines(live, name_of(134)) == {"lines": 2, "hidden": False}
    assert lines(live, name_of(57)) == {"lines": 1, "hidden": False}
    # A tile not yet found: the same rule, beside its QR.
    assert lines(live, name_of(99))["hidden"] is False


def test_a_name_longer_than_two_lines_is_cut_at_two_with_its_whole_name_in_its_title(live, env):
    """What keeps the tiles one height: two lines at most."""
    setup(live, env)
    got = lines(live, name_of(160))
    assert got == {"lines": 2, "hidden": True}, got
    assert live.get_attribute(name_of(160), "title").lower().endswith(NAMES[160].lower() + ")")


def test_the_words_and_the_tag_sit_in_a_row_under_the_name(live, env):
    """A found tile: its words and its 🏷️ below its name and grams, the 🏷️ at the row's right
    end, neither inside the press button. A tile not yet found: its words under its name, its
    QR at its side, both inside its press button (it has no 🏷️ to miss). RED on 826992a: the
    words and the 🏷️ sat at the tile's right side."""
    setup(live, env)
    c = cell(57)
    name, grams = live.evaluate(BOX, name_of(57)), live.evaluate(TEXT_BOX, [tile(57), "500g"])
    words = live.evaluate(TEXT_BOX, [c, "✅ scanned"])
    mark, box = live.evaluate(BOX, tag(57)), live.evaluate(BOX, c)
    assert words[1] >= grams[3] - 0.5 and mark[1] >= grams[3] - 0.5, (grams, words, mark)
    assert abs(mark[2] - (box[2] - 9)) <= 1.5, (mark, box)            # 8 px in from the tile's edge
    assert words[0] < name[0], (words, name)                         # the row starts under the swatch
    inside = live.evaluate("""([t, g]) => { const b = document.querySelector(t);
        const w = Array.from(document.querySelectorAll('*')).find((e) => e.children.length === 0
            && e.textContent.includes('✅ scanned') && e.closest('.fcc-audit-tile-cell') === b.closest('.fcc-audit-tile-cell'));
        return [b.contains(w), b.contains(document.querySelector(g))]; }""", [tile(57), tag(57)])
    assert inside == [False, False]
    # Not yet found: the QR at its side, beside the name, and the words under the name.
    qr, name99 = live.evaluate(BOX, f"{tile(99)} .fcc-audit-tile-qr"), live.evaluate(BOX, name_of(99))
    words99 = live.evaluate(TEXT_BOX, [tile(99), "not scanned"])
    assert qr[0] >= name99[2] and qr[1] <= name99[3] and words99[1] >= name99[3] - 0.5, (qr, name99, words99)


# Each tile's height, by its group: a group's grid holds its tiles.
HEIGHTS = """() => Object.fromEntries(Array.from(document.querySelectorAll('#fcc-audit-panel-body [data-audit-group]'))
    .map((g) => [g.dataset.auditGroup, Array.from(g.children)
        .map((c) => Math.round(c.getBoundingClientRect().height * 2) / 2)]))"""


def test_every_tile_in_a_group_is_one_height_and_the_groups_match(live, env):
    """Names of one line and of two, in the tiles not yet found and the found: every tile in
    a group's grid one height, and a found tile as tall as one not yet found. RED on 826992a:
    a found tile whose label was read was a line shorter than one with no label read, and
    both were shorter than a tile with its QR."""
    setup(live, env)
    scanned(live, "ID:150")                            # no label read: words under its badge's place
    tile_says(live, 150, "found, no label read")
    got = live.evaluate(HEIGHTS)
    assert set(got) == {"missing", "found"}, got
    for group, heights in got.items():
        assert max(heights) - min(heights) <= 0.5, (group, got)
    assert abs(got["missing"][0] - got["found"][0]) <= 1, got


def test_a_tap_a_little_off_the_tag_presses_nothing(live, env):
    """Beside a found tile's 🏷️, left of it on the row, right of it to the tile's edge, under it
    and just over it: no press, no mark, the spool still found. RED on 826992a: a tap left of
    the 🏷️ pressed the tile, which took the find back."""
    setup(live, env)
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    l, t, r, b = live.evaluate(BOX, tag(57))
    mid_x, mid_y = (l + r) / 2, (t + b) / 2
    for x, y in ((l - 6, mid_y), (r + 4, mid_y), (mid_x, b + 4), (mid_x, t - 3)):
        hit = live.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y);"
                            " return e ? [!!e.closest('[data-audit-tile]'), !!e.closest('[data-audit-tag]')] : null; }", [x, y])
        assert hit == [False, False], (x, y, hit)
        live.mouse.click(x, y)
        live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    assert posts(live, FOUND_URL) == [] and posts(live, TAG_URL) == [] and posts(live, UNTAG_URL) == []
    assert 57 in session()["scanned_items"]
    tile_says(live, 57, "scanned")


def test_on_a_touch_screen_the_tag_is_a_44px_target_and_the_tiles_stay_one_height(live, env):
    """WCAG's 44 px for a finger (pointer: coarse, as a phone's), the row under the name as
    tall on every tile. RED on 826992a: 32 px."""
    cdp = live.context.new_cdp_session(live)
    cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 1})
    assert live.evaluate("matchMedia('(pointer: coarse)').matches")
    setup(live, env, 390, 844)
    l, t, r, b = live.evaluate(BOX, tag(57))
    assert r - l >= 44 and b - t >= 44, (l, t, r, b)
    got = live.evaluate(HEIGHTS)
    for group, heights in got.items():
        assert max(heights) - min(heights) <= 0.5, (group, got)
    assert abs(got["missing"][0] - got["found"][0]) <= 1, got


def test_the_ring_goes_round_the_whole_tile(live, env):
    """The keyboard's tile wears its ring round the row under its name too, so the 🏷️ it is
    pressed after reads as the tile's. RED on 826992a: the ring was the press button's."""
    setup(live, env)
    live.focus(tile(57))
    live.keyboard.press("ArrowRight")
    live.keyboard.press("ArrowLeft")                    # the keyboard's focus, so :focus-visible
    sid = live.evaluate("document.activeElement.dataset.auditTile")
    ring = live.evaluate("""(s) => { const t = document.querySelector(s); const c = t.closest('.fcc-audit-tile-cell');
        return [getComputedStyle(c).outlineStyle, getComputedStyle(t).outlineStyle]; }""", tile(sid))
    assert ring == ["solid", "none"], ring
