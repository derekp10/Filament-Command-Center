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

The real dashboard's geometry (the dock at five window sizes, a phone at every Text
size, the 🏷️ centred on its backing) is test_audit_panel_look_58_e2e.py's; the real
double click on every control, test_audit_double_click_58_e2e.py's.
"""
from __future__ import annotations

import pytest

import app as app_module
from test_audit_find_and_tiles_58_js import begin, live, scanned  # noqa: F401  (live: the fixture)
from test_audit_no_label_58_js import BODY, tile, tile_says
from test_audit_panel_58_js import audit  # noqa: F401  (the fixture `live` stands on)
from test_audit_session_58 import add_spool, env  # noqa: F401  (env: the fixture)
from test_scanner_safe_dialogs_61_js import page61  # noqa: F401  (the fixture `audit` stands on)

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
