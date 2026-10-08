"""
Visual baselines for Phase 3 — Quick-Swap grid and shortcuts overlay.

The two GRID captures are hermetic against dev data (2026-09-13 sweep triage,
item 2). They used to render XL-1's LIVE grid: a real PM-DB-1 binding borrowed
for the test, plus whatever dev happened to hold. When XL-1's Printer Pool slots
(LR-MDB-1 slot 4, TST-MDB-1 slot 1) gained spools, those short "empty staging
slot" buttons became full spool cards and the section grew from 680 to 762 px,
with no layout change at all. Recapturing would only have re-baked that day's
dev data. Now the page answers every request the grid's content depends on from
a fixed loadout (`grid_stub_response`), and every non-GET is answered
synthetically, so the captures neither read dev's loadout nor write anything
(no borrowed binding, no buffer clear).
"""
from __future__ import annotations

import json
import os
import re
import typing
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, expect

QUICKSWAP_JS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "static", "js", "modules", "inv_quickswap.js")

# ---------------------------------------------------------------------------
# The fixed loadout behind the hermetic grid captures
# ---------------------------------------------------------------------------

GRID_TOOLHEAD = "XL-1"          # the real toolhead row the Location Manager opens
GRID_PRINTER = "FCC Test XL"
_MDB, _PDB, _POOL = "FCC-TEST-MDB", "FCC-TEST-PDB", "FCC-TEST-POOL"


def _spool(sid: int, box: str, slot: str, color_name: str, material: str, color: str, grams: int) -> dict:
    return {
        "id": sid, "type": "spool",
        "display": f"#{sid} FCC Test {material} {color_name}",
        "color": color, "remaining_weight": grams,
        "location": box, "slot": slot,
        "details": {"brand": "FCC Test", "material": material, "color_name": color_name},
    }


GRID_PRINTER_MAP = {"printers": {GRID_PRINTER: [{"location_id": GRID_TOOLHEAD, "position": 0}]}}
# One loaded and one empty slot among the toolhead feeds AND in the Printer Pool,
# so every render branch of an empty-buffer grid is pinned.
GRID_TOOLHEAD_SLOTS = {
    "printer_name": GRID_PRINTER,
    "toolheads": {GRID_TOOLHEAD: [{"box": _MDB, "slot": "1"}, {"box": _PDB, "slot": "1"}]},
    "printer_pool": [{"box": _MDB, "slot": "4"}, {"box": _POOL, "slot": "1"}],
}
GRID_CONTENTS = {
    _MDB: [_spool(990601, _MDB, "1", "Galaxy Black", "PLA", "2b2d42", 812)],
    _PDB: [],
    _POOL: [_spool(990602, _POOL, "1", "Signal Orange", "PETG", "ff7f11", 455)],
}
GRID_SLOT_COUNT = 4    # two feeds + two pool slots
GRID_CARD_COUNT = 2    # the loaded ones render as spool cards
OK = {"success": True}


def grid_stub_response(method: str, url: str) -> typing.Optional[typing.Tuple[int, typing.Any]]:
    """(status, json body) for a request the hermetic grid answers itself, or
    None to let it through. What passes through is read-only and renders outside
    #manage-quickswap-section: the page, JS/CSS, /api/locations (for the XL-1
    row) and the XL-1 modal's own reads."""
    if method != "GET":
        return 200, OK                      # nothing the page sends may reach dev
    parts = urlsplit(url)
    path = parts.path
    if path == "/api/printer_map":
        return 200, GRID_PRINTER_MAP
    if re.fullmatch(r"/api/machine/.+/toolhead_slots", path):
        return 200, GRID_TOOLHEAD_SLOTS     # whatever printer name XL-1 resolved to
    if path == "/api/get_contents":
        box = (parse_qs(parts.query).get("id") or [""])[0]
        if box in GRID_CONTENTS:
            return 200, GRID_CONTENTS[box]
    if path == "/api/state/buffer":
        return 200, []                      # empty buffer: empty slots stay inert, no Deposit buttons
    return None


@pytest.fixture
def hermetic_grid(page: Page):
    """Route the page through `grid_stub_response`. Must be set up before the
    Location Manager opens (open_manage_modal navigates)."""
    def _handle(route):
        try:
            answer = grid_stub_response(route.request.method, route.request.url)
            if answer is None:
                route.continue_()
                return
            status, payload = answer
            route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))
        except PlaywrightError as e:
            # A heartbeat request still in flight when the context closes.
            if "closed" not in str(e).lower():
                raise

    page.route("**/*", _handle)
    yield
    try:
        page.unroute_all(behavior="ignoreErrors")
    except PlaywrightError:
        pass


def _open_hermetic_grid(page: Page, open_manage_modal) -> None:
    open_manage_modal(GRID_TOOLHEAD)
    page.wait_for_function(
        """([slots, cards]) => {
            const grid = document.getElementById('quickswap-grid');
            return !!grid && (state.heldSpools || []).length === 0
                && grid.querySelectorAll('.fcc-qs-slot').length === slots
                && grid.querySelectorAll('.fcc-qs-card').length === cards;
        }""",
        arg=[GRID_SLOT_COUNT, GRID_CARD_COUNT],
        timeout=10000,
    )
    boxes = page.evaluate(
        "() => [...new Set([...document.querySelectorAll('#quickswap-grid .fcc-qs-slot')]"
        ".map(e => e.dataset.box))].sort()")
    assert boxes == sorted(GRID_CONTENTS), f"the grid rendered something other than the fixed loadout: {boxes}"
    expect(page.locator(f".fcc-qs-slot[data-box='{_PDB}'][data-slot='1']")).to_be_disabled()


@pytest.mark.usefixtures("require_server", "hermetic_grid")
def test_visual_quickswap_grid(page: Page, open_manage_modal, snapshot):
    _open_hermetic_grid(page, open_manage_modal)
    snapshot(page.locator("#manage-quickswap-section"), "quickswap-grid-default")


@pytest.mark.usefixtures("require_server", "hermetic_grid")
def test_visual_quickswap_kb_active(page: Page, open_manage_modal, snapshot):
    _open_hermetic_grid(page, open_manage_modal)
    page.keyboard.press("q")
    expect(page.locator(f".fcc-qs-slot.kb-active[data-box='{_MDB}'][data-slot='1']")).to_have_count(1)
    page.wait_for_timeout(200)
    snapshot(page.locator("#manage-quickswap-section"), "quickswap-grid-kb-active")


# ---------------------------------------------------------------------------
# Hermetic guards for the stub itself (run under --offline)
# ---------------------------------------------------------------------------

def _render_quickswap_fetch_urls() -> typing.List[str]:
    with open(QUICKSWAP_JS, encoding="utf-8") as fh:
        src = fh.read()
    start = src.index("const renderQuickSwapSection = ")
    end = src.index("\n    };\n", start)
    body = src[start:end]
    assert "printer_pool" in body and "grid.innerHTML = html" in body, (
        "could not isolate renderQuickSwapSection in inv_quickswap.js; update this canary")
    return [m.group(2) for m in re.finditer(r"fetch\(\s*([`'\"])(.*?)\1", body)]


def test_grid_stub_answers_every_request_renderQuickSwapSection_makes():
    """If the grid starts fetching something new, the captures silently depend
    on dev data again. Every fetch in renderQuickSwapSection must be stubbed."""
    urls = _render_quickswap_fetch_urls()
    assert len(urls) >= 3, f"expected the printer_map, toolhead_slots and get_contents fetches: {urls}"
    for template in urls:
        sample = re.sub(r"\$\{[^}]*\}", _MDB, template)
        assert grid_stub_response("GET", "http://fcc.invalid" + sample) is not None, (
            f"renderQuickSwapSection fetches {template!r}, which the hermetic grid does not stub")


def test_grid_stub_pins_the_buffer_and_swallows_every_write():
    base = "http://fcc.invalid"
    assert grid_stub_response("GET", f"{base}/api/state/buffer") == (200, []), (
        "a non-empty buffer turns empty slots into Deposit buttons")
    for method, path in [("POST", "/api/state/buffer"), ("PUT", "/api/dryer_box/PM-DB-1/bindings"),
                         ("POST", "/api/quickswap"), ("POST", "/api/identify_scan")]:
        assert grid_stub_response(method, base + path) == (200, OK), (method, path)
    assert grid_stub_response("GET", f"{base}/api/machine/%F0%9F%A6%9D%20XL/toolhead_slots") == (
        200, GRID_TOOLHEAD_SLOTS)
    # Real boxes pass through (the XL-1 modal's own reads render outside the section).
    assert grid_stub_response("GET", f"{base}/api/get_contents?id=XL-1") is None
    assert grid_stub_response("GET", f"{base}/api/locations") is None


def test_grid_loadout_covers_loaded_and_empty_slots_in_both_sections():
    feeds = GRID_TOOLHEAD_SLOTS["toolheads"][GRID_TOOLHEAD]
    pool = GRID_TOOLHEAD_SLOTS["printer_pool"]

    def loaded(entry):
        return any(str(it["slot"]) == entry["slot"] for it in GRID_CONTENTS[entry["box"]])

    assert sorted(map(loaded, feeds)) == [False, True]
    assert sorted(map(loaded, pool)) == [False, True]
    assert len(feeds) + len(pool) == GRID_SLOT_COUNT
    assert sum(map(loaded, feeds + pool)) == GRID_CARD_COUNT


# The confirm overlay has TWO layouts, and which one renders depends on the
# live active-print probe (`window.fetchPrinterStateForToolhead`), NOT on any
# markup change:
#   - probe → null  (printer idle/offline/unknown): the plain confirm card.
#   - probe → active state: the card ALSO grows an "⚠️ … is PRINTING" warning
#     banner + a scan-to-confirm QR pair (the 2026-04-23 active-print safety
#     feature), ~218px taller.
# Because `bound_loaded_slot` yields whatever loaded slot exists — sometimes a
# toolhead on a live printer, sometimes not — a single baseline that lets the
# real probe run is inherently nondeterministic (it flip-flops 284px⇄502px on
# the same code). So each variant is pinned in its own test with the probe
# STUBBED to a fixed answer, making both captures deterministic. (Group 33.4.)
def _open_confirm_overlay(page: Page, open_manage_modal, bound_loaded_slot, probe_stub_js: str):
    box, slot, toolhead = (
        bound_loaded_slot["box"], bound_loaded_slot["slot"], bound_loaded_slot["toolhead"]
    )
    open_manage_modal(toolhead)
    # Pin the active-print probe BEFORE the slot click (showConfirmOverlay reads
    # window.fetchPrinterStateForToolhead at click time) so the overlay renders
    # a deterministic variant regardless of what the real fleet is doing.
    page.evaluate(f"window.fetchPrinterStateForToolhead = {probe_stub_js};")
    page.locator(f".fcc-qs-slot[data-box='{box}'][data-slot='{slot}']").first.click()
    expect(page.locator("#fcc-quickswap-confirm-overlay")).to_be_visible(timeout=8000)
    # Snapshot the bounded confirm CARD, not the full-viewport backdrop: the
    # backdrop is semi-transparent, so capturing it bakes the live dashboard
    # (activity-log timestamps, backlog count) into the baseline and guarantees
    # a >1% drift on every run. The card (`.border-info`, min-width 420px) is
    # the only bordered panel inside the overlay and pins the layout/styling.
    card = page.locator("#fcc-quickswap-confirm-overlay .border-info").first
    expect(card).to_be_visible()
    return card


@pytest.mark.usefixtures("require_server")
def test_visual_quickswap_confirm_overlay(page: Page, open_manage_modal, snapshot, bound_loaded_slot):
    # Base variant: probe fails open (null) → plain confirm card, no banner/QRs.
    # Matches the long-standing baseline captured when dev printers were idle.
    card = _open_confirm_overlay(
        page, open_manage_modal, bound_loaded_slot,
        "() => Promise.resolve(null)",
    )
    snapshot(card, "quickswap-confirm-overlay")


@pytest.mark.usefixtures("require_server")
def test_visual_quickswap_confirm_overlay_active_print(page: Page, open_manage_modal, snapshot, bound_loaded_slot):
    # Active-print variant: probe reports a printing printer → the card grows
    # the "⚠️ … is PRINTING" warning banner + scan-to-confirm QR pair. Pinned
    # separately so a regression in the SAFETY banner (not just the base card)
    # is caught, and so this layout is captured deterministically.
    card = _open_confirm_overlay(
        page, open_manage_modal, bound_loaded_slot,
        "() => Promise.resolve({ state: 'PRINTING', printer_name: 'DEV-PRINTER' })",
    )
    # The QR pair renders async into the banner; wait for both codes to paint so
    # the card reaches its final height before capture (attachConfirmQRs draws a
    # canvas/img per code, giving each QR container its 70px size).
    page.wait_for_function(
        "() => { const c = document.querySelector('#fcc-quickswap-confirm-overlay .border-info');"
        " return c && c.querySelectorAll('canvas, img, svg').length >= 2; }",
        timeout=8000,
    )
    # MASK the QR row out of the pixel diff: each QR encodes a per-render session
    # id (fcc-cqr-<seq>-<Date.now>), so its pixels change every run and would
    # otherwise drift the baseline — the exact flake class this group removes.
    # Masking blanks only the QR row (Playwright paints it a solid color); the
    # warning banner, spool text, and buttons stay pixel-pinned so a real layout
    # regression is still caught. The wait above still guarantees the row is at
    # full height so the mask covers the right area. (Group 33.4 review fix.)
    snapshot(
        card, "quickswap-confirm-overlay-active",
        mask=[page.locator("#fcc-quickswap-confirm-overlay .fcc-confirm-qr-row")],
    )


@pytest.mark.usefixtures("require_server")
def test_visual_shortcuts_overlay(page: Page, base_url: str, snapshot):
    page.goto(base_url)
    page.wait_for_selector("#btn-shortcuts-help", timeout=10000)
    page.locator("#btn-shortcuts-help").click()
    expect(page.locator("#fcc-shortcuts-overlay")).to_be_visible()
    page.wait_for_timeout(300)
    snapshot(page.locator("#fcc-shortcuts-overlay"), "shortcuts-overlay-default")
