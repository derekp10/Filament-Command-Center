"""Group 58, Derek's second look (2026-11-03, section H): the audit panel's page half, on
a real DOM and the REAL routes, hermetic.

The real overlay_mount.js, inv_core.js, inv_cmd.js, inv_queue.js, inv_audit_find.js, the
real scan accumulator and global.css, in `isolated_page` (no route to any network), so it
runs under --offline; every call the panel makes goes to the REAL Flask routes on the real
session, over tests/spoolman_extra_fake.SpoolmanHTTPFake (test_audit_find_and_tiles_58_js's
`live`).

Pinned here, each RED on the commit before its own:
- P4, not scanned first (sample 5a(i)): "Expected here" shows "Not scanned (N)", those
  tiles with their QRs, then "Found (M)", each in the order the server sends (shelf
  order); the Extras and Loaded from here after; the headings and counts follow every
  redraw; the arrows move in the order drawn.
- P2, the dock (sample 1b): the Last found box, Needs a label, Done… and Cancel Audit
  under the scrolling list, never scrolling with it, the three QRs in one row, drawn once
  per panel; the panel as tall as the window less 16 px; a narrow dock puts the box on
  its own row and drops the captions; with nothing found the box says so, and with
  nothing selected says that; on a window too short for the dock and a tile row the dock
  goes in the flow after the tiles, and comes back when the window grows.
- P5, the 🏷️ on Needs a label sits on a small dark round backing (sample 4(ii)).
- P6, a found tile's own 🏷️ (Derek's (a)): on an Expected tile found and on an Extra, its
  own button beside the tile's; a tap marks the spool and leaves the last found alone, a
  tap apart takes the mark back, a double tap is one; a flag up before the audit shows so
  and a tap says so; a refusal says why; Tab reaches it, a person's Enter presses it, a
  scan's presses nothing, the arrows go on from it; a double click reaches nothing else.
- P7, "↩ Put back" in the Last found box: what a press on its tile does, for an Expected
  spool and an Extra, never for one loaded from here, with no QR; a second press under a
  double press puts nothing else back, even when a scan put another spool in the box.

The real dashboard's geometry (the dock at five window sizes, a phone at every Text
size, the 🏷️ centred on its backing) is test_audit_panel_look_58_e2e.py's; the real
double click on every control, test_audit_double_click_58_e2e.py's.
"""
from __future__ import annotations

import app as app_module
from test_audit_find_and_tiles_58_js import audit_id, begin, live, posts, scanned  # noqa: F401  (live: the fixture)
from test_audit_no_label_58_js import BODY, LABEL, PAST_A_DOUBLE_PRESS, tile, tile_says, toasts, wire
from test_audit_panel_58_js import NOTICE, audit  # noqa: F401  (the fixture `live` stands on)
from test_audit_session_58 import add_spool, env, scan, session  # noqa: F401  (env: the fixture)
from test_scanner_safe_dialogs_61_js import page61  # noqa: F401  (the fixture `audit` stands on)
from test_slow_scan_slash_js import _type

SUBHEAD = ".fcc-audit-subhead"


def four(env):
    """Four spools filed in one box, a slot each."""
    for sid, slot in ((57, "1"), (99, "2"), (134, "3"), (150, "4")):
        add_spool(env, sid, "LR-MDB-1", container_slot=slot)


def shelf_order():
    """The order the server sends the expected rows in: the panel keeps it in each group."""
    rows = app_module.app.test_client().get("/api/audit_session").get_json()["expected"]
    return [r["id"] for r in rows]


def headings(page):
    return page.evaluate("(s) => Array.from(document.querySelectorAll(s)).map((h) => h.textContent.trim())", SUBHEAD)


def drawn(page):
    """Every Expected tile, in the order drawn (the two groups' grids)."""
    return page.evaluate("""() => Array.from(document.querySelectorAll(
        '[data-audit-group="missing"] [data-audit-tile], [data-audit-group="found"] [data-audit-tile]'))
        .map((t) => Number(t.dataset.auditTile))""")


def headings_are(page, want):
    page.wait_for_function("([s, want]) => JSON.stringify(Array.from(document.querySelectorAll(s))"
                           ".map((h) => h.textContent.trim())) === JSON.stringify(want)", arg=[SUBHEAD, want])


# --- P4: not scanned first -------------------------------------------------------------

def test_not_scanned_comes_first_then_found_each_in_the_servers_order(live, env):
    four(env)
    begin(live, env)
    order = shelf_order()
    assert sorted(order) == [57, 99, 134, 150]
    headings_are(live, ["Not scanned (4)"])             # nothing found: one group, no empty one
    assert drawn(live) == order
    live.click(tile(order[1]))                          # a press finds the second on the shelf
    headings_are(live, ["Not scanned (3)", "Found (1)"])
    assert drawn(live) == [order[0], order[2], order[3], order[1]]
    scanned(live, f"ID:{order[0]}")                     # a scan the first: Found keeps shelf order
    headings_are(live, ["Not scanned (2)", "Found (2)"])
    assert drawn(live) == [order[2], order[3], order[0], order[1]]
    # A not-scanned tile shows its QR, a found one none.
    qrs = live.evaluate("""() => Array.from(document.querySelectorAll('[data-audit-qr]'))
        .map((q) => Number(q.closest('[data-audit-tile]').dataset.auditTile))""")
    assert qrs == [order[2], order[3]]
    for sid in order[2:]:
        scanned(live, f"ID:{sid}")
    headings_are(live, ["Found (4)"])                   # all found: one group
    assert drawn(live) == order


def test_the_groups_sit_under_expected_here_and_the_extras_come_after(live, env):
    four(env)
    add_spool(env, 200, "LR-MDB-2", container_slot="3")
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-1", physical_source_slot="4")
    begin(live, env)
    scanned(live, "ID:99")
    scanned(live, "ID:200")
    scanned(live, "ID:242")
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('Loaded from here')", arg=BODY)
    text = " ".join(live.inner_text(BODY).split())
    at = [text.index(w) for w in ("Expected here", "Not scanned (3)", "Found (1)", "Extra (found here", "Loaded from here")]
    assert at == sorted(at), text


def test_the_arrows_move_in_the_order_drawn(live, env):
    four(env)
    begin(live, env)
    order = shelf_order()
    scanned(live, f"ID:{order[0]}")
    headings_are(live, ["Not scanned (3)", "Found (1)"])
    walked = []
    for _ in range(5):
        live.keyboard.press("ArrowRight")
        walked.append(int(live.evaluate("document.activeElement.dataset.auditTile")))
    assert walked == [order[1], order[2], order[3], order[0], order[1]]      # wraps to the first drawn


def test_a_pressed_tile_keeps_the_keyboard_as_it_moves_to_found(live, env):
    """The keyboard goes with the tile it pressed, never to the next one, whose next
    Enter would find a spool nobody pressed (the double-press rule)."""
    four(env)
    begin(live, env)
    order = shelf_order()
    live.keyboard.press("ArrowRight")
    live.keyboard.press("Enter")
    tile_says(live, order[0], "found, no label read")
    headings_are(live, ["Not scanned (3)", "Found (1)"])
    assert int(live.evaluate("document.activeElement.dataset.auditTile")) == order[0]


# --- P2: the dock ----------------------------------------------------------------------

DOCK = "#fcc-audit-panel-dock"
SCROLL = "#fcc-audit-panel-scroll"
STRIP = "#fcc-audit-last-found"
NONE = "#fcc-audit-last-none"
NEED = "#fcc-audit-panel-needlabel"
DONE_BTN = "#fcc-audit-panel-done"
CANCEL_BTN = "#fcc-audit-panel-cancel"
QRS = ["#fcc-audit-panel-qr-needlabel", "#fcc-audit-panel-qr-done", "#fcc-audit-panel-qr-cancel"]
CONTROLS = [NEED, DONE_BTN, CANCEL_BTN] + QRS

# Wholly seen: its four corners (2 px in) and its middle hit-test to it.
SEEN = r"""(sel) => { const e = document.querySelector(sel); if (!e) return false;
    const r = e.getBoundingClientRect(); if (r.width < 4 || r.height < 4) return false;
    return [[r.left + 2, r.top + 2], [r.right - 2, r.top + 2], [r.left + 2, r.bottom - 2], [r.right - 2, r.bottom - 2],
            [r.left + r.width / 2, r.top + r.height / 2]].every(([x, y]) => {
        const h = document.elementFromPoint(x, y); return !!h && e.contains(h); }); }"""
BOX = "(s) => { const r = document.querySelector(s).getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }"
TILES_PRESSABLE = r"""() => Array.from(document.querySelectorAll('#fcc-audit-panel-body .fcc-audit-tile')).map((t) => {
    t.scrollIntoView({ block: 'center' });
    const r = t.getBoundingClientRect();
    const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!e && t.contains(e); })"""


def shelf(env, n=40):
    for sid in range(1000, 1000 + n):
        add_spool(env, sid, "LR-MDB-1")


def seen(page, sel):
    return page.evaluate(SEEN, sel)


def box_says(page, sel, words):
    page.wait_for_function("([s, w]) => { const e = document.querySelector(s); return !!e && e.textContent.includes(w); }",
                           arg=[sel, words])


def test_the_dock_sits_under_the_list_and_never_scrolls_with_it(live, env):
    """Derek, 2026-11-03 (sample 1b): "the placement of useful buttons and last found on
    the panel". RED on 517abe1: Done, Cancel and their QRs ended the scrolling body, out of
    view until it was scrolled to its end, and Needs a label rode on a sticky strip."""
    live.set_viewport_size({"width": 1366, "height": 768})
    shelf(env)
    begin(live, env)
    scanned(live, "ID:1000")
    live.wait_for_selector(STRIP)
    live.wait_for_timeout(100)                          # the QRs draw two frames later
    assert live.evaluate("(s) => { const b = document.querySelector(s); return b.scrollHeight > b.clientHeight * 2; }", BODY)
    assert live.evaluate("([b, d]) => !document.querySelector(b).contains(document.querySelector(d))", [BODY, DOCK])
    boxes = []
    for at in ("0", "b.scrollHeight / 2", "b.scrollHeight"):
        live.evaluate(f"(s) => {{ const b = document.querySelector(s); b.scrollTop = {at}; }}", BODY)
        boxes.append(live.evaluate(BOX, DOCK))
        assert [c for c in CONTROLS + [STRIP] if not seen(live, c)] == [], at
    assert boxes[0] == boxes[1] == boxes[2]             # it never moved
    # The three QRs in one row, under their buttons; the box beside them.
    tops = [live.evaluate(BOX, q)[1] for q in QRS]
    assert max(tops) - min(tops) <= 1, tops
    for btn, qr in zip([NEED, DONE_BTN, CANCEL_BTN], QRS):
        b, q = live.evaluate(BOX, btn), live.evaluate(BOX, qr)
        assert q[1] >= b[1] + b[3] - 0.5 and b[0] < q[0] + q[2] and q[0] < b[0] + b[2], (btn, b, q)
    strip = live.evaluate(BOX, STRIP)
    assert strip[0] + strip[2] <= live.evaluate(BOX, NEED)[0]
    # As tall as the window less 8 px above and below.
    panel = live.evaluate(BOX, "#fcc-audit-panel-overlay .fcc-audit-panel")
    assert abs(panel[1] - 8) <= 1 and abs(panel[3] - (768 - 16)) <= 1, panel


def test_the_docks_columns_are_drawn_once_and_only_the_box_again(live, env):
    """Its QRs never flicker at a redraw, and the keyboard on one of its buttons stays
    there. RED on 517abe1: every scan drew Done's and Cancel's QRs again."""
    four(env)
    begin(live, env)
    live.wait_for_function("() => window.__qrs.includes('CMD:DONE')")
    live.focus(NEED)
    for sid in (57, 99, 134):
        scanned(live, f"ID:{sid}")
        box_says(live, STRIP, f"#{sid}")
    qrs = live.evaluate("window.__qrs")
    assert [qrs.count(c) for c in ("CMD:DONE", "CMD:CANCEL", "CMD:NEEDLABEL")] == [1, 1, 1], qrs
    assert live.evaluate("document.activeElement.id") == NEED[1:]


def test_with_nothing_found_the_box_says_so_then_nothing_selected(live, env):
    """Its words stay true: nothing found yet, then, once a find is taken back that was the
    last found while others stay found, nothing selected. RED on 517abe1: no box."""
    four(env)
    begin(live, env)
    live.wait_for_selector(NONE)
    assert "Nothing found yet" in live.text_content(NONE) and "Last found" in live.text_content(NONE)
    assert seen(live, NEED) and seen(live, DONE_BTN)    # the columns are there from the start
    scanned(live, "ID:57")
    live.click(tile(99))
    box_says(live, STRIP, "#99")
    live.wait_for_timeout(720)                          # past a double press
    live.click(tile(99))                                # taken back: it was the last found
    box_says(live, NONE, "Nothing is selected")


def test_a_narrow_dock_puts_the_box_on_its_own_row_and_drops_the_captions(live, env):
    """On a phone the Last found words take the dock's first row and the three columns the
    second, the captions under the QRs dropped. RED on 517abe1: no dock."""
    live.set_viewport_size({"width": 390, "height": 844})
    four(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(STRIP)
    dock, strip = live.evaluate(BOX, DOCK), live.evaluate(BOX, STRIP)
    assert abs(strip[2] - dock[2]) <= 1, (strip, dock)  # the whole width
    cols = [live.evaluate(BOX, f"#fcc-audit-panel-dock .fcc-audit-dock-{c}") for c in ("need", "done", "cancel")]
    assert all(c[1] >= strip[1] + strip[3] for c in cols)    # under it, side by side
    assert max(c[1] for c in cols) - min(c[1] for c in cols) <= 1
    assert cols[0][0] + cols[0][2] <= cols[1][0] and cols[1][0] + cols[1][2] <= cols[2][0]
    tops = [live.evaluate(BOX, q)[1] for q in QRS]      # the QRs in one row
    assert max(tops) - min(tops) <= 1, tops
    caps = live.evaluate("""() => Array.from(document.querySelectorAll(
        '#fcc-audit-panel-dock .fcc-audit-dock-cap, #fcc-audit-panel-dock .fcc-audit-strip-cap')).map((c) => getComputedStyle(c).display)""")
    assert caps == ["none", "none", "none"]
    assert [c for c in CONTROLS if not seen(live, c)] == []


def test_a_window_too_short_for_the_dock_puts_it_in_the_flow_and_back(live, env):
    """On a window that would leave the list less than a tile row, the dock follows the
    tiles and the two scroll as one: every tile, and the dock's buttons and QRs, can be
    brought into view. A taller window puts it back under the list. RED on 517abe1."""
    shelf(env, 12)
    live.set_viewport_size({"width": 1366, "height": 400})
    begin(live, env)
    scanned(live, "ID:1000")
    live.wait_for_selector(STRIP)
    live.wait_for_function("(s) => document.querySelector(s).classList.contains('fcc-audit-scroll-flow')", arg=SCROLL)
    assert all(live.evaluate(TILES_PRESSABLE))
    for c in CONTROLS:
        live.evaluate("(s) => document.querySelector(s).scrollIntoView({ block: 'nearest' })", c)
        assert seen(live, c), c
    live.set_viewport_size({"width": 1366, "height": 900})
    live.wait_for_function("(s) => !document.querySelector(s).classList.contains('fcc-audit-scroll-flow')", arg=SCROLL)
    live.evaluate("(s) => { document.querySelector(s).scrollTop = 0; }", BODY)
    assert [c for c in CONTROLS if not seen(live, c)] == []


# --- P5: the 🏷️ on a dark round backing -------------------------------------------------

def test_needs_a_label_wears_its_tag_on_a_dark_round_backing(live, env):
    """Derek, 2026-11-03 (sample 4(ii)): the 🏷️ blended into the yellow. The emoji sits in
    its own round dark span, hidden from a screen reader (the button's name is "Needs a
    label"), then a real space, so the button's text still reads "🏷️ Needs a label". Its
    centring is measured from its pixels on the real dashboard
    (test_audit_panel_look_58_e2e.py). RED on fed9646: the emoji was bare text."""
    four(env)
    begin(live, env)
    got = live.evaluate("""(s) => { const b = document.querySelector(s); const ico = b.querySelector('.fcc-ico-on-light');
        return { ico: ico ? ico.textContent : null, hidden: ico ? ico.getAttribute('aria-hidden') : null,
                 text: b.textContent.replace(/\\s+/g, ' ').trim(),
                 round: ico ? getComputedStyle(ico).borderRadius : null, bg: ico ? getComputedStyle(ico).backgroundColor : null,
                 square: ico ? Math.abs(ico.getBoundingClientRect().width - ico.getBoundingClientRect().height) < 0.5 : null }; }""",
                        NEED)
    assert got == {"ico": "🏷️", "hidden": "true", "text": "🏷️ Needs a label", "round": "50%", "bg": "rgb(30, 30, 30)",
                   "square": True}


# --- P6: a 🏷️ on each found tile ----------------------------------------------------------

TAG_URL = "/api/audit/needs_label"
UNTAG_URL = "/api/audit/needs_label_undo"


def tag(sid):
    return f"[data-audit-tag='{sid}']"


def tag_state(page, sid):
    return page.evaluate("(s) => { const t = document.querySelector(s); return t ? t.dataset.auditTagState : null; }", tag(sid))


def tag_is(page, sid, state):
    page.wait_for_function("([s, w]) => { const t = document.querySelector(s); return !!t && t.dataset.auditTagState === w; }",
                           arg=[tag(sid), state])


def test_a_found_tile_has_its_own_tag_beside_it_and_no_other_tile_does(live, env):
    """Derek, 2026-11-03, (a): "A sounds good". On an Expected tile found and on an Extra,
    its own button, a sibling of the tile's press button in one cell, never inside it;
    none on a tile not yet found, nor on a loaded-from-here one. RED on e64ab36."""
    four(env)
    add_spool(env, 200, "LR-MDB-2", container_slot="3")
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-1", physical_source_slot="4")
    begin(live, env)
    scanned(live, "ID:57")
    scanned(live, "ID:200")
    scanned(live, "ID:242")
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('Loaded from here')", arg=BODY)
    got = live.evaluate("""() => Array.from(document.querySelectorAll('[data-audit-tag]')).map((b) => {
        const t = document.querySelector(`[data-audit-tile='${b.dataset.auditTag}']`);
        return { id: Number(b.dataset.auditTag), tag: b.tagName, sibling: !!t && t.parentElement === b.parentElement && !t.contains(b),
                 state: b.dataset.auditTagState, pressed: b.getAttribute('aria-pressed') }; })""")
    assert got == [{"id": 57, "tag": "BUTTON", "sibling": True, "state": "none", "pressed": "false"},
                   {"id": 200, "tag": "BUTTON", "sibling": True, "state": "none", "pressed": "false"}]
    assert "Needs a label: mark #57" in live.get_attribute(tag(57), "aria-label")
    # The tile's own press area stays whole: its middle is the tile, the 🏷️ its own.
    hit = live.evaluate("""([t, g]) => { const r = document.querySelector(t).getBoundingClientRect();
        const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        const q = document.querySelector(g).getBoundingClientRect();
        const f = document.elementFromPoint(q.left + q.width / 2, q.top + q.height / 2);
        return [!!e.closest(t) && !e.closest(g), !!f.closest(g)]; }""", [tile(57), tag(57)])
    assert hit == [True, True]


def test_a_tap_marks_the_spool_and_leaves_the_last_found_alone(live, env):
    four(env)
    begin(live, env)
    scanned(live, "ID:57")
    scanned(live, "ID:99")                             # the last found
    box_says(live, STRIP, "#99")
    live.click(tag(57))
    tag_is(live, 57, "marked")
    tile_says(live, 57, "needs a label")
    assert live.get_attribute(tag(57), "aria-pressed") == "true"
    assert wire(env, 57) == "true"
    assert posts(live, TAG_URL) == [{"audit_id": audit_id(), "id": 57}]
    assert session()["last_found"] == 99 and "#99" in live.text_content(STRIP)
    assert {"msg": "#57 is marked: it needs a label.", "kind": "success"} in toasts(live)


def test_a_second_tap_apart_takes_the_mark_back_and_a_double_tap_is_one(live, env):
    four(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.click(tag(57))
    live.click(tag(57))                                # under 700 ms: the same tap
    tag_is(live, 57, "marked")
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    assert posts(live, TAG_URL) == [{"audit_id": audit_id(), "id": 57}] and posts(live, UNTAG_URL) == []
    live.click(tag(57))                                # apart: the mark comes off
    tag_is(live, 57, "none")
    assert posts(live, UNTAG_URL) == [{"audit_id": audit_id(), "id": 57}]
    assert LABEL not in env["fake"].extra("spool", 57)
    assert "needs a label" not in live.text_content(tile(57))


def test_a_spool_flagged_before_the_audit_shows_so_and_a_tap_says_so(live, env):
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    add_spool(env, 99, "LR-MDB-1", container_slot="2", needs_label_print=True)
    begin(live, env)
    scanned(live, "ID:99")
    tag_is(live, 99, "flagged")
    tile_says(live, 99, "needs a label")
    assert live.get_attribute(tag(99), "aria-pressed") is None
    assert "already flagged" in live.get_attribute(tag(99), "aria-label")
    env["fake"].patches.clear()
    live.click(tag(99))
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('already flagged')", arg=NOTICE)
    assert env["fake"].patches == [] and tag_state(live, 99) == "flagged"
    assert {"msg": "#99 is already flagged for a new label.", "kind": "info"} in toasts(live)


def test_a_refused_tap_says_why(live, env):
    """The audit ended elsewhere before the panel heard: nothing is marked, and the
    answer's words are toasted at 7 s and said on the panel, as the strip's buttons'."""
    four(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(tag(57))
    live.evaluate("""() => { const plain = window.fetch;     // the panel's poll hasn't heard
        window.fetch = (u, o) => (String(u).indexOf('/api/audit_session') !== -1 ? new Promise(() => {}) : plain(u, o)); }""")
    scan(env, "CMD:CANCEL")
    live.click(tag(57))
    live.wait_for_function("() => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                           ".some((e) => e.innerText.includes('already ended'))")
    assert {"msg": "That audit has already ended.", "kind": "error"} in toasts(live)
    assert wire(env, 57) is None


def test_tab_reaches_a_tag_a_persons_enter_presses_it_and_the_arrows_go_on(live, env):
    four(env)
    begin(live, env)
    order = shelf_order()
    scanned(live, f"ID:{order[0]}")                     # found: drawn last, its 🏷️ after it
    headings_are(live, ["Not scanned (3)", "Found (1)"])
    live.focus(tile(order[0]))
    live.keyboard.press("Tab")
    assert live.evaluate("document.activeElement.dataset.auditTag") == str(order[0])
    live.keyboard.press("Enter")                        # a person's Enter, through the accumulator
    tag_is(live, order[0], "marked")
    assert live.evaluate("document.activeElement.dataset.auditTag") == str(order[0])   # kept through the redraw
    live.keyboard.press("ArrowLeft")                    # back to its own tile
    assert int(live.evaluate("document.activeElement.dataset.auditTile")) == order[0]
    live.focus(tag(order[0]))
    live.keyboard.press("ArrowRight")                   # on to the next tile: past the last, the first
    assert int(live.evaluate("document.activeElement.dataset.auditTile")) == order[1]
    assert posts(live, UNTAG_URL) == []


def test_a_scans_enter_on_a_tag_presses_nothing(live, env):
    four(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.focus(tag(57))
    _type(live, "ID:99", 1)                             # a scanner's keys, with the keyboard on the 🏷️
    live.wait_for_function("() => window.__sent.some((p) => p.body && p.body.text === 'ID:99')")
    live.wait_for_timeout(150)
    assert posts(live, TAG_URL) == [] and wire(env, 57) is None


def test_a_double_click_on_a_tag_marks_once_and_reaches_nothing_under_it(live, env):
    """The mark grows the tile, and the tiles under it move: the second press reaches
    nothing on the panel."""
    four(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(tag(57))
    live.dblclick(tag(57))
    tag_is(live, 57, "marked")
    live.wait_for_timeout(300)
    assert posts(live, TAG_URL) == [{"audit_id": audit_id(), "id": 57}] and posts(live, UNTAG_URL) == []
    assert posts(live, "/api/audit/found") == []


# --- P7: "↩ Put back" ----------------------------------------------------------------------

PUT_BACK = "#fcc-audit-put-back"
FOUND_URL = "/api/audit/found"


def test_put_back_takes_the_last_find_back_onto_the_not_scanned_list(live, env):
    """Derek, 2026-11-03: "put back into the unscanned queue, so the user doesn't have to
    scroll to find that one, if they realize it was a mistaken scan". What a press on its
    tile does, from the box; then the box says nothing is selected. RED on 1bcaeb4."""
    four(env)
    begin(live, env)
    scanned(live, "ID:134")
    scanned(live, "ID:57")
    box_says(live, STRIP, "#57")
    assert live.text_content(PUT_BACK).strip() == "↩ Put back"
    assert "not-scanned list" in live.get_attribute(PUT_BACK, "title")
    live.click(PUT_BACK)
    box_says(live, NONE, "Nothing is selected")
    assert posts(live, FOUND_URL) == [{"audit_id": audit_id(), "id": 57, "found": False}]
    assert 57 not in session()["scanned_items"] and 134 in session()["scanned_items"]
    tile_says(live, 57, "not scanned")
    headings_are(live, ["Not scanned (3)", "Found (1)"])
    assert {"msg": "#57 is back on the not-scanned list.", "kind": "success"} in toasts(live)
    assert live.evaluate("document.activeElement === document.body")   # it went, with its box's spool


def test_put_back_takes_an_extra_off_the_extras(live, env):
    four(env)
    add_spool(env, 200, "LR-MDB-2", container_slot="3")
    begin(live, env)
    scanned(live, "ID:200")
    box_says(live, STRIP, "#200")
    assert "off the Extras" in live.get_attribute(PUT_BACK, "title")
    live.click(PUT_BACK)
    live.wait_for_selector(tile(200), state="detached")
    assert 200 not in session()["rogue_items"]
    assert {"msg": "#200 is off the Extras: it isn't here after all.", "kind": "success"} in toasts(live)


def test_no_put_back_for_a_spool_loaded_from_here_and_no_qr_in_the_box(live, env):
    """A loaded-from-here tile is no button, and the route refuses to take it back."""
    four(env)
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-1", physical_source_slot="4")
    begin(live, env)
    scanned(live, "ID:242")
    box_says(live, STRIP, "#242")
    assert live.locator(PUT_BACK).count() == 0
    scanned(live, "ID:57")
    box_says(live, STRIP, "#57")
    assert live.locator(PUT_BACK).count() == 1
    assert live.evaluate("(s) => document.querySelector(s).querySelectorAll('[id*=qr], canvas, img').length", STRIP) == 0


def test_a_second_press_under_a_double_press_puts_nothing_else_back(live, env):
    """A double click must not put back one spool and then act on what takes its place: a
    scan answered between the two presses puts another spool in the box."""
    four(env)
    begin(live, env)
    scanned(live, "ID:57")
    box_says(live, STRIP, "#57")
    live.click(PUT_BACK)
    box_says(live, NONE, "Nothing is selected")
    scanned(live, "ID:99")                             # read between the two presses
    box_says(live, STRIP, "#99")
    live.click(PUT_BACK)                               # under 700 ms after the first
    live.wait_for_timeout(200)
    assert posts(live, FOUND_URL) == [{"audit_id": audit_id(), "id": 57, "found": False}]
    assert 99 in session()["scanned_items"]


def test_a_real_double_click_on_put_back_puts_back_once_and_reaches_nothing_under_it(live, env):
    four(env)
    begin(live, env)
    scanned(live, "ID:134")
    scanned(live, "ID:57")
    box_says(live, STRIP, "#57")
    live.dblclick(PUT_BACK)
    box_says(live, NONE, "Nothing is selected")
    live.wait_for_timeout(300)
    assert posts(live, FOUND_URL) == [{"audit_id": audit_id(), "id": 57, "found": False}]
    assert 134 in session()["scanned_items"] and "CMD:NEEDLABEL" not in [p.get("text") for p in posts(live, "/api/identify_scan")]


def test_a_persons_enter_on_put_back_presses_it_once(live, env):
    four(env)
    begin(live, env)
    scanned(live, "ID:57")
    box_says(live, STRIP, "#57")
    live.focus(PUT_BACK)
    live.keyboard.press("Enter")
    box_says(live, NONE, "Nothing is selected")
    live.keyboard.press("Enter")                       # the keyboard went with it: nothing more
    live.wait_for_timeout(200)
    assert posts(live, FOUND_URL) == [{"audit_id": audit_id(), "id": 57, "found": False}]


def test_a_put_back_that_is_refused_keeps_the_spool_and_says_why(live, env):
    """The audit ended elsewhere: nothing is taken back, and the answer's words are toasted
    at 7 s, as the strip's buttons'."""
    four(env)
    begin(live, env)
    scanned(live, "ID:57")
    box_says(live, STRIP, "#57")
    live.evaluate("""() => { const plain = window.fetch;     // the panel's poll hasn't heard
        window.fetch = (u, o) => (String(u).indexOf('/api/audit_session') !== -1 ? new Promise(() => {}) : plain(u, o)); }""")
    scan(env, "CMD:CANCEL")
    live.click(PUT_BACK)
    live.wait_for_function("() => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                           ".some((e) => e.innerText.includes('already ended'))")
    assert {"msg": "That audit has already ended.", "kind": "error"} in toasts(live)
    assert live.locator(STRIP).count() == 1
