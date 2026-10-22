"""Text size guard: the readability rule on the screens the 2026-10-21 audit
measured (Derek's decisions, DESIGN.md "Typography").

Text you read is never under 13.6 px; a label inside a pill or box (a badge, a
tag, a chip, IDLE / PRINTING, a count, a "📷 Scan to …" caption, a short
ALL-CAPS label) never under 12.8 px. The walker is `assert_text_size` in
conftest.py: an element is a label when it, or an ancestor, is sized with
--fcc-fs-label. Like test_contrast_guard.py, each test opens real screens on
the dev container; if a change brings small text back, the failure names every
element under its floor.

READ-ONLY. Every request the page makes that isn't a read is answered inside
the browser with 200 "{}" and never reaches the server (only GETs, the
heartbeat POST and the spool-refresh POST, both reads, go through). Pickers and
questions are opened with no door behind them and closed with Escape; nothing
is picked, saved, moved or deducted. The ids come from dev's own data (a
multi-slot box with a stored spool, a toolhead it feeds), so a test that can't
find them skips with the reason instead of failing.

HEAD proof (dev 6e6bdd4 / c7dafaa code: the CSS / JS / template edits stashed
for one run against the live container, restored after): all 10 RED. The
finding lists named 32 elements on the dashboard (10.4 px IDLE and ▲▼, 11.5 px
toolhead ids and "🔗 no bound slot", 11.2 px material lines), 83 in the
Locations window and search (12 px badges), 14 in the slot picker (10.6 px
"📷 CANCEL", 11.5 px ⭐ Recommended), 4 in the questions (11.5 px "📷 Scan to …"
captions), 140 in Settings (12 px tags, 12.25 px small-in-small help lines,
11.2 px printer ids); no named sizes; and 10 QR codes whose colour wasn't their
button's (the idle Load QR blue, the printing one orange, under an amber button).

The readability review (2026-10-21) widened it: the walker now judges every
visible input, select and textarea by its own size (hermetic proof:
test_text_size_guard_walker.py); the search check waits for its own new
results and skips, saying why, when they hold no card (an error line or "No
matching…" used to pass for a measured search); and it opens the screens the
build changed that no check opened: "Record it as coming from…", a Room and a
Printer row in the Location Manager, and the review window, the audit panel
and the bulk-move panel, each drawn from a sample this browser alone is
served. Nothing there is under its floor today.
"""
from __future__ import annotations

from urllib.parse import urlparse

import pytest
import requests
from playwright.sync_api import Page

from conftest import LABEL_FLOOR_PX, TEXT_FLOOR_PX

# POSTs that only read (the heartbeat; the spool refresh). Everything else
# that isn't a GET is answered in the page.
READ_POSTS = {"/api/dashboard_pulse", "/api/spools/refresh"}

pytestmark = pytest.mark.usefixtures("require_server")


def _read_only(page: Page, extra_get=None):
    """Answer every write in the browser. `extra_get`: {path: json} GET answers
    served to this page only (a printer that says PRINTING)."""
    import json as _json
    served = dict(extra_get or {})

    def handle(route, request):
        u = urlparse(request.url)
        method = request.method.upper()
        if method == "GET":
            if u.path in served:
                route.fulfill(status=200, content_type="application/json", body=_json.dumps(served[u.path]))
                return
            route.continue_()
            return
        if method == "POST" and u.path in READ_POSTS:
            route.continue_()
            return
        route.fulfill(status=200, content_type="application/json", body="{}")

    page.route("**/*", handle)


def _ready(page: Page, base_url: str):
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_function(
        "() => typeof openSpoolDetails === 'function' && typeof state !== 'undefined' && state.locationsLoaded",
        timeout=45_000)
    page.wait_for_function(
        "() => { const w = document.getElementById('printer-status-widget');"
        " return w && !w.classList.contains('fcc-ps-loading') && w.querySelectorAll('.fcc-ps-th').length > 0; }",
        timeout=45_000)
    page.wait_for_timeout(1500)
    # The floors are the Standard text size: the browser's default 16 px root.
    assert page.evaluate("() => parseFloat(getComputedStyle(document.documentElement).fontSize)") == 16


def _shown(page: Page, modal_id: str, opener_js: str, arg=None, timeout=15_000):
    """Run `opener_js` and wait for Bootstrap's shown.bs.modal on `modal_id`."""
    page.evaluate("""(id) => { window.__fccShown = window.__fccShown || {};
        const el = document.getElementById(id);
        el.addEventListener('shown.bs.modal', () => { window.__fccShown[id] = true; }, { once: true });
        window.__fccShown[id] = false; }""", modal_id)
    page.evaluate(opener_js, arg)
    page.wait_for_function("(id) => window.__fccShown[id] === true", arg=modal_id, timeout=timeout)
    page.wait_for_timeout(400)


def _hide(page: Page, modal_id: str):
    page.evaluate("""(id) => { const el = document.getElementById(id);
        const m = el && bootstrap.Modal.getInstance(el); if (m) m.hide(); }""", modal_id)
    page.wait_for_function("(id) => !document.getElementById(id).classList.contains('show')", arg=modal_id,
                           timeout=10_000)
    page.wait_for_timeout(400)


@pytest.fixture(scope="module")
def dev_ids(api_base_url):
    """Ids from dev's own data: a multi-slot Dryer Box holding a STORED spool in
    a slot bound to a toolhead (its tile opens the Swap / Overwrite panel; its
    head has a Quick-Swap card), that head's printer, the spool's filament, and
    a spool from elsewhere to place."""
    def get(path):
        r = requests.get(api_base_url + path, timeout=20)
        r.raise_for_status()
        return r.json()

    rows = get("/api/locations")
    heads = {str(r.get("LocationID")) for r in rows if r.get("Type") == "Tool Head"}
    found = None
    for row in rows:
        if row.get("Type") != "Dryer Box":
            continue
        try:
            n = int(str(row.get("Max Spools") or "0"))
        except ValueError:
            n = 0
        targets = (row.get("extra") or {}).get("slot_targets") or {}
        if n < 2 or not isinstance(targets, dict):
            continue
        box = str(row["LocationID"])
        for s in get("/api/get_contents?id=" + box):
            slot = str(s.get("slot") or "")
            head = str(targets.get(slot) or "")
            if slot and head in heads and not s.get("is_ghost"):
                found = {"box": box, "slot": slot, "head": head, "spool": int(s["id"])}
                break
        if found:
            break
    if not found:
        pytest.skip("dev has no multi-slot Dryer Box with a stored spool in a slot bound to a toolhead")
    printer = next((str(r["LocationID"]) for r in rows if r.get("Type") == "Printer"
                    and any(str(t.get("location_id")) == found["head"] for t in (r.get("toolheads") or []))), None)
    # The Room the box stands in (its DEPLOYED cards), else any Room.
    rooms = [str(r["LocationID"]) for r in rows if r.get("Type") == "Room"]
    box_row = next((r for r in rows if str(r.get("LocationID")) == found["box"]), {})
    parent = str(box_row.get("parent_id") or "")
    found["room"] = parent if parent in rooms else (rooms[0] if rooms else None)
    details = get("/api/spool_details?id=%d" % found["spool"])
    found["filament"] = int((details.get("filament") or {}).get("id") or 0) or None
    others = [s for s in get("/api/get_contents?id=Unassigned") if s.get("id") is not None]
    found["incoming"] = int(others[0]["id"]) if others else found["spool"]
    found["printer"] = printer
    return found


# ---------------------------------------------------------------------------
# The dashboard: title bar, Printer Status (open and collapsed), the log,
# the buffer and the command deck
# ---------------------------------------------------------------------------

def test_dashboard_text_is_readable(page: Page, base_url: str, assert_text_size):
    """Everything on screen at load (hidden windows don't count): the title
    bar, Printer Status, the log, the buffer, the command deck, the pills."""
    _read_only(page)
    _ready(page, base_url)
    assert_text_size(page.locator("body"))
    # Collapsed: this browser's own localStorage, a fresh context per test.
    page.evaluate("() => window.togglePrinterStatusWidget()")
    page.wait_for_function("() => document.getElementById('printer-status-widget').classList.contains('collapsed')")
    page.wait_for_timeout(400)
    assert_text_size(page.locator("#printer-status-widget"))


def test_locations_and_search_text_is_readable(page: Page, base_url: str, assert_text_size):
    _read_only(page)
    _ready(page, base_url)
    _shown(page, "locMgrModal", "() => window.openLocationsModal()")
    page.wait_for_function("() => document.querySelectorAll('#location-table tr').length > 0", timeout=20_000)
    assert_text_size(page.locator("#locMgrModal .modal-content"))
    _hide(page, "locMgrModal")
    page.evaluate("() => SearchEngine.open()")
    page.wait_for_function("() => document.getElementById('offcanvasSearch').classList.contains('show')")
    page.wait_for_timeout(500)
    assert_text_size(page.locator("#offcanvasSearch"))
    _search_cards(page, "spool", lambda: page.fill("#global-search-query", "PLA"))
    assert_text_size(page.locator("#offcanvasSearch"))
    _search_cards(page, "filament", lambda: page.click("label[for=searchTypeFilaments]"))
    assert_text_size(page.locator("#offcanvasSearch"))


# The search shows cards, or a line saying why not ("No matching…", an error).
SEARCH_DONE_JS = ("() => { const r = document.getElementById('global-search-results');"
                  " return !!r && !r.querySelector('[data-tsg-stale]') && !r.querySelector('.spinner-border')"
                  " && (!!r.querySelector('.fcc-spool-card') || /No matching|error/i.test(r.textContent)); }")


def _search_cards(page: Page, kind: str, start):
    """Run `start` (what sets the search off), wait for the search to finish
    drawing its new results, and skip unless it drew cards: a check that
    measured only "No matching spools found" or a connection error proves
    nothing about the cards (readability review, 2026-10-21). The results on
    screen are marked first, so the old spool cards can't pass for the
    filament search's answer."""
    page.evaluate("() => { const r = document.getElementById('global-search-results');"
                  " Array.from((r && r.children) || []).forEach((c) => { c.dataset.tsgStale = '1'; }); }")
    start()
    page.wait_for_function(SEARCH_DONE_JS, timeout=30_000)
    page.wait_for_timeout(600)
    cards = page.evaluate("(kind) => Array.from(document.querySelectorAll('#global-search-results .fcc-spool-card'))"
                          ".filter((c) => kind !== 'filament' || /openFilamentDetails/.test(c.getAttribute('onclick') || '')).length",
                          kind)
    if not cards:
        text = page.evaluate("() => document.getElementById('global-search-results').innerText.trim()")
        pytest.skip(f"the {kind} search drew no cards to measure: {text[:120]!r}")


def test_spool_and_filament_windows_text_is_readable(page: Page, base_url: str, dev_ids, assert_text_size):
    _read_only(page)
    _ready(page, base_url)
    _shown(page, "spoolModal", "(id) => openSpoolDetails(id)", dev_ids["spool"])
    page.wait_for_function("(id) => document.getElementById('detail-id').innerText.trim() === String(id)",
                           arg=dev_ids["spool"])
    page.wait_for_timeout(600)
    assert_text_size(page.locator("#spoolModal .modal-content"))
    _hide(page, "spoolModal")
    if not dev_ids["filament"]:
        pytest.skip("the spool's filament id wasn't readable")
    _shown(page, "filamentModal", "(id) => openFilamentDetails(id)", dev_ids["filament"])
    page.wait_for_function("() => { const l = document.getElementById('fil-spools-list');"
                           " return l && l.children.length > 0 && !/Loading/i.test(l.innerText); }", timeout=15_000)
    page.wait_for_timeout(500)
    assert_text_size(page.locator("#filamentModal .modal-content"))
    _shown(page, "editFilamentModal", "() => document.getElementById('btn-fil-edit').click()")
    for tab in ("basic", "colors", "specs", "advanced"):
        page.evaluate("(t) => { const b = document.querySelector('[data-bs-target=\"#editfil-tab-' + t + '\"]');"
                      " if (b) bootstrap.Tab.getOrCreateInstance(b).show(); }", tab)
        page.wait_for_timeout(500)
        assert_text_size(page.locator("#editFilamentModal .modal-content"))
    _hide(page, "editFilamentModal")
    _hide(page, "filamentModal")


def _close_wizard(page: Page):
    page.evaluate("() => { try { wizardState.isDirty = false; wizardState.forceClose = true;"
                  " wizardState.returnToSpoolId = null; wizardState.returnToFilamentId = null; } catch (e) {} }")
    _hide(page, "wizardModal")


def _open_every_panel(page: Page):
    page.evaluate("() => { document.querySelectorAll('#wizardModal .collapse').forEach((el) => {"
                  " try { bootstrap.Collapse.getOrCreateInstance(el, { toggle: false }).show(); } catch (e) {} }); }")
    page.wait_for_timeout(800)


def test_wizard_text_is_readable(page: Page, base_url: str, dev_ids, assert_text_size):
    _read_only(page)
    _ready(page, base_url)
    _shown(page, "wizardModal", "() => window.openWizardModal()")
    assert_text_size(page.locator("#wizardModal .modal-content"))
    for mode in ("existing", "external", "manual"):
        page.evaluate("(m) => wizardSelectType(m)", mode)
        page.wait_for_timeout(1000)
        if mode == "manual":
            _open_every_panel(page)
        assert_text_size(page.locator("#wizardModal .modal-content"))
    _close_wizard(page)
    _shown(page, "wizardModal", "(id) => window.openEditWizard(id)", dev_ids["spool"])
    page.wait_for_timeout(2000)
    _open_every_panel(page)
    assert_text_size(page.locator("#wizardModal .modal-content"))
    _close_wizard(page)


def _open_manage(page: Page, loc: str):
    _shown(page, "manageModal", "(id) => window.openManage(id)", loc)


def test_location_manager_text_is_readable(page: Page, base_url: str, dev_ids, assert_text_size):
    _read_only(page)
    _ready(page, base_url)
    _open_manage(page, dev_ids["box"])
    page.wait_for_function("() => document.getElementById('slot-grid-container').children.length > 0", timeout=15_000)
    page.evaluate("() => { const b = document.getElementById('feeds-body');"
                  " if (b && (b.style.display === 'none' || !b.style.display)) window.toggleFeedsSection(); }")
    page.wait_for_timeout(1200)
    assert_text_size(page.locator("#manageModal .modal-content"))
    page.evaluate("() => { window.manageNavStack = []; closeManage(); }")
    page.wait_for_function("() => !document.getElementById('manageModal').classList.contains('show')", timeout=10_000)
    page.wait_for_timeout(400)
    _open_manage(page, dev_ids["head"])
    page.wait_for_function("() => document.querySelectorAll('#quickswap-grid .fcc-qs-card').length > 0", timeout=15_000)
    page.wait_for_timeout(2500)   # the printer probes settle
    assert_text_size(page.locator("#manageModal .modal-content"))
    # Its Quick-Swap card opens the confirm (nothing is written until Yes).
    page.locator("#quickswap-grid .fcc-qs-card").first.click()
    page.wait_for_function("() => !!document.getElementById('fcc-quickswap-confirm-overlay')", timeout=10_000)
    page.wait_for_timeout(800)
    assert_text_size(page.locator("#fcc-quickswap-confirm-overlay"))
    page.keyboard.press("Escape")


def test_location_manager_room_and_printer_views_text_is_readable(page: Page, base_url: str, dev_ids,
                                                                  assert_text_size):
    """A Room (the cards of its boxes' spools, DEPLOYED badges included) and
    a Printer row, the views the build changed and no guard opened
    (readability review, 2026-10-21)."""
    _read_only(page)
    _ready(page, base_url)
    views = [v for v in (dev_ids["room"], dev_ids["printer"]) if v]
    if not views:
        pytest.skip("dev has no Room and no Printer row")
    for loc in views:
        _open_manage(page, loc)
        page.wait_for_timeout(2500)   # the contents and the printer probes settle
        assert_text_size(page.locator("#manageModal .modal-content"))
        page.evaluate("() => { window.manageNavStack = []; closeManage(); }")
        page.wait_for_function("() => !document.getElementById('manageModal').classList.contains('show')",
                               timeout=10_000)
        page.wait_for_timeout(400)


# Samples served to one test browser only (GET answers), so the review window,
# the audit panel and the bulk-move panel draw real rows; builder 1's measure
# harness used the same. Their writes are answered in the page.
SAMPLE_REVIEW = {"pending": [{
    "kind": "partial", "printer_name": "\U0001F99D XL", "job_id": "tsg-sample-1", "progress": 0.42,
    "filename": "/usb/SAMPLE~1.BGC",
    "spools": [{"sid": 57, "display": "#57 Prusament PLA (Purple (Galaxy Purple))", "toolhead": "XL-1", "grams": 12.3,
                "remaining_before": 900, "ambiguous": True, "unconfirmed_write": True, "runout": True, "color": "453A72"},
               {"sid": 99, "display": "#99 Tecbears PETG (Clear)", "toolhead": "XL-2", "grams": 4.1,
                "remaining_before": 19, "color": "C4C2C8"}]}]}
SAMPLE_AUDIT = {"active": True, "location_id": "LR-MDB-1", "idle_timeout_min": 30,
                "stats": {"total_expected": 2, "found": 1, "missing": 1, "rogue": 1},
                "expected": [{"id": 57, "display": "Prusament PLA (Purple (Galaxy Purple))", "color": "453A72",
                              "remaining_weight": 922, "slot": "", "found": True},
                             {"id": 99, "display": "Tecbears PETG (Clear)", "color": "C4C2C8",
                              "remaining_weight": 19, "slot": "4", "found": False}],
                "rogue": [{"id": 134, "display": "Prusament PLA (Pearl White)", "color": "F0F0F0",
                           "remaining_weight": 924, "slot": "3"}]}
SAMPLE_BULK = {"active": True, "stage": "preview", "source_id": "LR-MDB-1", "dest_id": "CR-CT-1-R1",
               "preview": {"ok": True, "msg": "", "stats": {"movable": 2, "skipped": 1}, "source_feeds": ["XL-1"],
                           "movable": [{"id": 57, "display": "#57 Prusament PLA (Purple (Galaxy Purple))",
                                        "color": "453A72", "remaining_weight": 922, "slot": ""},
                                       {"id": 134, "display": "#134 Prusament PLA (Pearl White)", "color": "F0F0F0",
                                        "remaining_weight": 924, "slot": "3"}],
                           "skipped": [{"id": 99, "display": "#99 Tecbears PETG (Clear)", "color": "C4C2C8",
                                        "remaining_weight": 19, "slot": "4", "reason": "loaded on a toolhead"}]}}


def test_review_audit_and_bulk_move_panels_text_is_readable(page: Page, base_url: str, assert_text_size):
    """The print-review window (and its badge), the audit panel and the
    bulk-move panel, each drawn from a sample this browser alone is served.
    Nothing is applied, audited or moved (readability review, 2026-10-21:
    the build changed all three and no guard opened them)."""
    _read_only(page, extra_get={"/api/cancel_deduct/pending": SAMPLE_REVIEW, "/api/audit_session": SAMPLE_AUDIT,
                                "/api/bulk_move_session": SAMPLE_BULK})
    _ready(page, base_url)
    page.evaluate("() => { if (window.refreshCancelReviewBadge) window.refreshCancelReviewBadge(); }")
    page.wait_for_timeout(1200)
    page.evaluate("() => window.openCancelReview()")
    page.wait_for_function("() => !!document.getElementById('fcc-cr-title')", timeout=10_000)
    page.wait_for_timeout(1000)
    assert_text_size(page.locator("[aria-labelledby='fcc-cr-title']"))
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('fcc-cr-title')", timeout=5000)
    page.evaluate("() => window.openAuditPanel()")
    page.wait_for_function("() => { const b = document.getElementById('fcc-audit-panel-body');"
                           " return !!b && /Auditing/.test(b.innerText); }", timeout=10_000)
    page.wait_for_timeout(800)
    assert_text_size(page.locator("#fcc-audit-panel-body"))
    page.evaluate("() => window.closeAuditPanel()")
    page.wait_for_timeout(400)
    if not page.evaluate("() => window.FCC_BULK_MOVE_ENABLED === true && typeof window.openBulkMovePanel === 'function'"):
        pytest.skip("Bulk Moves is off in this install: the review window and the audit panel were checked")
    page.evaluate("() => window.openBulkMovePanel({ user: true })")
    page.wait_for_function("() => document.querySelectorAll('#fcc-bulkmove-body .fcc-bulk-tile').length > 0",
                           timeout=10_000)
    page.wait_for_timeout(800)
    assert_text_size(page.locator("#fcc-bulkmove-body"))


def _open_picker(page: Page, loc: str, spool: int):
    page.evaluate("([loc, sid]) => { window.openSlotPicker({ location: loc, spool: sid }); }", [loc, spool])
    page.wait_for_function("() => document.querySelectorAll('#fcc-slot-picker .fcc-sp-tile').length > 0", timeout=20_000)
    page.wait_for_timeout(2500)   # the printer chips leave "checking…"


def _click_slot_tile(page: Page, slot: str):
    """Click the picker tile whose number reads SLOT <slot>."""
    page.evaluate("""(slot) => { const t = Array.from(document.querySelectorAll('#fcc-slot-picker .fcc-sp-tile'))
        .find((el) => { const n = el.querySelector('.fcc-sp-num'); return n && n.textContent.trim() === 'SLOT ' + slot; });
        if (t) t.click(); }""", str(slot))


def _close_picker(page: Page):
    for _ in range(3):
        if not page.evaluate("() => !!document.getElementById('fcc-slot-picker')"):
            return
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)


def test_slot_picker_text_is_readable(page: Page, base_url: str, dev_ids, assert_text_size):
    """Box mode, its Swap / Overwrite panel (a stored spool's tile), and
    printer mode. Nothing is picked: Escape closes each."""
    _read_only(page)
    _ready(page, base_url)
    _open_picker(page, dev_ids["box"], dev_ids["incoming"])
    assert_text_size(page.locator("#fcc-slot-picker"))
    # "SLOT 1" stays on one line beside the ⭐ Recommended tag (Derek: trim the
    # tag's side padding so it fits).
    lines = page.evaluate("""() => { const n = document.querySelector('#fcc-slot-picker .fcc-sp-tile.is-star .fcc-sp-num');
        if (!n) return null; const r = document.createRange(); r.selectNodeContents(n);
        return new Set(Array.from(r.getClientRects()).map((x) => Math.round(x.top))).size; }""")
    assert lines in (None, 1), "the starred tile's slot number wraps beside ⭐ Recommended"
    _click_slot_tile(page, dev_ids["slot"])
    page.wait_for_function("() => !!document.querySelector('#fcc-slot-picker [data-sp-state=\"choice\"]')", timeout=8000)
    page.wait_for_timeout(600)
    assert_text_size(page.locator("#fcc-slot-picker"))
    _close_picker(page)
    if dev_ids["printer"]:
        _open_picker(page, dev_ids["printer"], dev_ids["incoming"])
        assert_text_size(page.locator("#fcc-slot-picker"))
        _close_picker(page)


QUESTIONS = {
    "three-way, idle": """{ title: 'Load #57 onto XL-1?', msg: 'LR-MDB-1 slot 1 feeds XL-1. (A test question: nothing happens.)',
        printing: false, onConfirm() {}, onCancel() {}, onStore() {}, ids: { overlay: 'fcc-tsg-question' } }""",
    "three-way, printing": """{ title: 'Load #57 onto XL-1?', msg: 'XL is PRINTING. (A test question: nothing happens.)',
        printing: true, onConfirm() {}, onCancel() {}, onStore() {}, ids: { overlay: 'fcc-tsg-question' } }""",
    "store only": """{ title: 'Store #57 in LR-MDB-1 slot 1?', msg: 'The slot feeds nothing now. (A test question.)',
        noLoad: true, printing: false, onConfirm() {}, onCancel() {}, onStore() {}, ids: { overlay: 'fcc-tsg-question' } }""",
    "two-way active print": """{ activePrint: { printer_name: 'XL', state: 'PRINTING', toolhead: 'XL-1' },
        msg: 'Moving a spool now will disrupt the print. (A test question.)', onConfirm() {}, onCancel() {},
        ids: { overlay: 'fcc-tsg-question' } }""",
}


def test_questions_text_is_readable(page: Page, base_url: str, dev_ids, assert_text_size):
    """Every shape of the shared move question (one shared QR row: the
    "📷 Scan to …" captions), the gating confirm and Quick Weigh."""
    _read_only(page)
    _ready(page, base_url)
    for opts in QUESTIONS.values():
        page.evaluate("() => window.confirmActivePrint(" + opts + ")")
        page.wait_for_function("() => !!document.querySelector('#fcc-tsg-question .fcc-confirm-qr-row')", timeout=5000)
        page.wait_for_timeout(300)
        assert_text_size(page.locator("#fcc-tsg-question"))
        page.keyboard.press("Escape")
        page.wait_for_function("() => !document.getElementById('fcc-tsg-question')", timeout=5000)
    # "Record it as coming from…", the Printer picker's question (sample feeds;
    # Escape answers it, nothing is sent). The build changed its text too.
    page.evaluate("""() => { window.__tsgRs = _askRecordSource({ head: 'XL-1', spool_location: '', feeds: [
        { box: 'LR-MDB-1', slot: '1', free: true }, { box: 'LR-MDB-1', slot: '2', free: false, claimed_by: 99 }] }, 57, null); }""")
    page.wait_for_function("() => !!document.querySelector('#fcc-record-source .fcc-confirm-qr-row')", timeout=5000)
    page.wait_for_timeout(300)
    assert_text_size(page.locator("#fcc-record-source"))
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('fcc-record-source')", timeout=5000)
    _shown(page, "confirmModal", "() => requestConfirmation('A test question: nothing happens either way.', () => {})")
    assert_text_size(page.locator("#confirmModal .modal-content"))
    page.evaluate("() => confirmAction(false)")
    page.wait_for_timeout(600)
    page.evaluate("(id) => window.openQuickWeigh(id)", dev_ids["spool"])
    page.wait_for_function("() => !!document.getElementById('fcc-weight-entry-overlay')", timeout=10_000)
    page.wait_for_timeout(500)
    assert_text_size(page.locator("#fcc-weight-entry-overlay"))
    page.keyboard.press("Escape")


def test_settings_and_list_windows_text_is_readable(page: Page, base_url: str, assert_text_size):
    """Settings (every section, the attribute report loaded: a GET), the
    keyboard shortcuts, Weigh-Out, the label queue and the label backlog."""
    _read_only(page)
    _ready(page, base_url)
    _shown(page, "configModal", "() => window.openConfigModal()")
    page.wait_for_function("() => !!document.getElementById('cfgset-save')"
                           " && !/Loading/.test(document.getElementById('config-printer-map').innerText)", timeout=15_000)
    page.click("#btn-config-attrs-scan")
    page.wait_for_function("() => document.querySelectorAll('#config-attrs-results tr').length > 0", timeout=20_000)
    page.wait_for_timeout(600)
    assert_text_size(page.locator("#configModal .modal-content"))
    _hide(page, "configModal")
    page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
    page.keyboard.press("?")
    page.wait_for_function("() => { const o = document.getElementById('fcc-shortcuts-overlay');"
                           " return o && o.style.display === 'block'; }", timeout=5000)
    assert_text_size(page.locator("#fcc-shortcuts-overlay"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    for modal, opener in (("weighOutModal", "() => window.openWeighOutModal()"),
                          ("queueModal", "() => window.openQueueModal()"),
                          ("backlogModal", "() => window.openBacklogModal()")):
        _shown(page, modal, opener)
        page.wait_for_timeout(1200)
        assert_text_size(page.locator("#%s .modal-content" % modal))
        _hide(page, modal)


# ---------------------------------------------------------------------------
# QR codes take their button's colour (Derek, 2026-10-21): "so it's clear at a
# glance what QR code matches the button". The hermetic proof of the shared
# helper is test_qr_button_tones_js.py; this checks every QR question on the
# real page, by computed colour.
# ---------------------------------------------------------------------------

# The colour each QR wears, by the Bootstrap variant of the button it stands
# for: (card border, caption), as rgb. Amber is btn-warning's own #ffc107 (the
# Load it instead / Continue Anyway button); Derek approved Store's cyan pair
# and Cancel's grey pair as they were (2026-10-21).
QR_TONE_RGB = {
    "warning": ("255,193,7", "255,193,7"),
    "info": ("79,162,201", "143,211,240"),
    "secondary": ("108,117,125", "173,181,189"),
    "light": ("222,226,230", "222,226,230"),
    "dark": ("73,80,87", "248,249,250"),
}

# The QR row's cells in order (confirm, [store], cancel), read by structure so
# the check runs on any version of the row: the card is a cell's first child,
# the caption its last.
QR_CELLS_JS = r"""(root) => {
    const rgb = (c) => { const m = String(c).match(/\d+(\.\d+)?/g); return m ? m.slice(0, 3).map(Number).join(',') : String(c); };
    const row = root.querySelector('.fcc-confirm-qr-row');
    if (!row) return [];
    const cells = Array.from(row.children).filter((c) => c.tagName === 'DIV');
    const roles = cells.length === 3 ? ['confirm', 'store', 'cancel'] : ['confirm', 'cancel'];
    return cells.map((cell, i) => {
        const kids = Array.from(cell.children);
        const card = kids[0];
        const cap = kids[kids.length - 1];
        return { qr: roles[i], caption: (cap && cap.innerText) || '',
                 border: card ? rgb(getComputedStyle(card).borderTopColor) : null,
                 captionColor: cap ? rgb(getComputedStyle(cap).color) : null };
    });
}"""

BUTTON_VARIANTS_JS = r"""(root, sels) => sels.map((sel) => {
    const b = root.querySelector(sel);
    if (!b) return null;
    const m = String(b.className).match(/\bbtn-(?:outline-)?(warning|info|secondary|light|dark|danger|success|primary)\b/);
    return m ? m[1] : null;
})"""


def _qr_mismatches(page: Page, root_sel: str, buttons: dict, where: str) -> list:
    """Each QR's border and caption must be the colour of the button it stands
    for (`buttons`: QR role -> that button's selector). Returns what doesn't
    match, as sentences."""
    root = page.locator(root_sel)
    cells = root.evaluate(QR_CELLS_JS)
    if not cells:
        return [f"{where}: no QR codes on screen"]
    variants = root.evaluate(BUTTON_VARIANTS_JS, [buttons[c["qr"]] for c in cells])
    wrong = []
    for cell, variant in zip(cells, variants):
        want = QR_TONE_RGB.get(variant)
        if not want or (cell["border"], cell["captionColor"]) != want:
            wrong.append(f"{where}: the {cell['qr']} QR ({cell['caption']!r}) is border {cell['border']} / caption "
                         f"{cell['captionColor']}, its button is btn-{variant} {want}")
    return wrong


def test_the_named_sizes_are_the_standard_sizes(page: Page, base_url: str):
    """--fcc-fs-label / -small / -row are 12.8 / 13.6 / 14.4 px at the Standard
    size, and Bootstrap's own sizes are held to the rule: a badge never under
    12.8 px (inside small text too), a badge in a heading keeps its bigger size,
    and small text inside small text is 13.6 px."""
    _read_only(page)
    _ready(page, base_url)
    sizes = page.evaluate("""() => {
        const host = document.createElement('div');
        host.innerHTML = '<span id="t-l" style="font-size:var(--fcc-fs-label)">a</span>'
            + '<span id="t-s" style="font-size:var(--fcc-fs-small)">a</span>'
            + '<span id="t-r" style="font-size:var(--fcc-fs-row)">a</span>'
            + '<span class="badge" id="t-b">a</span>'
            + '<span class="small"><span class="badge" id="t-bs">a</span><span class="small" id="t-ss">a</span>'
            + '<code id="t-cs">a</code></span>'
            + '<h5><span class="badge" id="t-bh">a</span></h5>';
        document.body.appendChild(host);
        const px = (id) => parseFloat(getComputedStyle(document.getElementById(id)).fontSize);
        const out = { label: px('t-l'), small: px('t-s'), row: px('t-r'), badge: px('t-b'),
                      badge_in_small: px('t-bs'), small_in_small: px('t-ss'), code_in_small: px('t-cs'),
                      badge_in_h5: px('t-bh') };
        host.remove();
        return out; }""")
    assert sizes == {"label": LABEL_FLOOR_PX, "small": TEXT_FLOOR_PX, "row": 14.4, "badge": LABEL_FLOOR_PX,
                     "badge_in_small": LABEL_FLOOR_PX, "small_in_small": TEXT_FLOOR_PX,
                     "code_in_small": TEXT_FLOOR_PX, "badge_in_h5": 15}, sizes


def test_qr_codes_take_their_buttons_colour(page: Page, base_url: str, dev_ids):
    """Derek, 2026-10-21: the Load QR's border and caption must match its amber
    "Load it instead" button, as Store's (cyan) and Cancel's (grey) match
    theirs, "so it's clear at a glance what QR code matches the button"; and
    every other QR question the same way. Every mismatch is collected, so one
    run names them all. The hermetic proof of the shared helper is
    test_qr_button_tones_js.py; this reads the computed colours on the page."""
    _read_only(page)
    _ready(page, base_url)
    wrong = []
    move = {"confirm": ".fcc-apc-yes", "store": ".fcc-apc-store", "cancel": ".fcc-apc-no"}
    for name in ("three-way, idle", "three-way, printing", "two-way active print"):
        page.evaluate("() => window.confirmActivePrint(" + QUESTIONS[name] + ")")
        page.wait_for_function("() => !!document.querySelector('#fcc-tsg-question .fcc-confirm-qr-row')", timeout=5000)
        wrong += _qr_mismatches(page, "#fcc-tsg-question", move, name)
        page.keyboard.press("Escape")
        page.wait_for_function("() => !document.getElementById('fcc-tsg-question')", timeout=5000)
    page.evaluate("() => window.confirmActivePrint(" + QUESTIONS["store only"] + ")")
    page.wait_for_function("() => !!document.querySelector('#fcc-tsg-question .fcc-confirm-qr-row')", timeout=5000)
    wrong += _qr_mismatches(page, "#fcc-tsg-question", {"confirm": ".fcc-apc-store", "cancel": ".fcc-apc-no"},
                            "store only")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('fcc-tsg-question')", timeout=5000)
    # The slot picker's Swap / Overwrite panel.
    _open_picker(page, dev_ids["box"], dev_ids["incoming"])
    _click_slot_tile(page, dev_ids["slot"])
    page.wait_for_function("() => !!document.querySelector('#fcc-slot-picker .fcc-confirm-qr-row')", timeout=8000)
    wrong += _qr_mismatches(page, "#fcc-slot-picker",
                            {"confirm": ".fcc-sp-choice-btns > .fcc-sp-choice-btn:first-child",
                             "store": "[data-sp-choice=overwrite]", "cancel": "[data-sp-choice=back]"},
                            "slot picker choice")
    _close_picker(page)
    # "Record it as coming from…" (one free slot: slot / No box / Cancel).
    page.evaluate("""() => { window.__tsgRs = _askRecordSource({ head: 'XL-1', spool_location: '', feeds: [
        { box: 'LR-MDB-1', slot: '1', free: true }, { box: 'LR-MDB-1', slot: '2', free: false, claimed_by: 99 }] }, 57, null); }""")
    page.wait_for_function("() => !!document.querySelector('#fcc-record-source .fcc-confirm-qr-row')", timeout=5000)
    wrong += _qr_mismatches(page, "#fcc-record-source",
                            {"confirm": ".fcc-rs-opt:not([disabled])", "store": ".fcc-rs-none", "cancel": ".fcc-rs-cancel"},
                            "record source")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('fcc-record-source')", timeout=5000)
    # The Quick-Swap confirm while the head's printer answers PRINTING (this
    # page only, from here on): Yes, swap is cyan, No, cancel a light outline,
    # and each button sits under its QR.
    page.route("**/api/printer_state/" + dev_ids["head"], lambda route: route.fulfill(
        status=200, content_type="application/json",
        body='{"is_active": true, "known": true, "printer_name": "XL", "state": "PRINTING"}'))
    _open_manage(page, dev_ids["head"])
    page.wait_for_function("() => document.querySelectorAll('#quickswap-grid .fcc-qs-card').length > 0", timeout=15_000)
    page.wait_for_timeout(1000)
    page.locator("#quickswap-grid .fcc-qs-card").first.click()
    page.wait_for_function("() => !!document.querySelector('#fcc-quickswap-confirm-overlay .fcc-confirm-qr-row')",
                           timeout=10_000)
    page.wait_for_timeout(300)
    wrong += _qr_mismatches(page, "#fcc-quickswap-confirm-overlay",
                            {"confirm": "#fcc-quickswap-yes", "cancel": "#fcc-quickswap-no"}, "Quick-Swap")
    centres = page.evaluate("""() => {
        const c = (el) => { const r = el.getBoundingClientRect(); return Math.round(r.left + r.width / 2); };
        const cards = Array.from(document.querySelectorAll('#fcc-quickswap-confirm-overlay .fcc-confirm-qr-row > div'))
            .map((cell) => cell.firstElementChild);
        return [[c(cards[0]), c(document.getElementById('fcc-quickswap-yes'))],
                [c(cards[1]), c(document.getElementById('fcc-quickswap-no'))]]; }""")
    for (qr_x, btn_x), name in zip(centres, ("Yes, swap", "No, cancel")):
        if abs(qr_x - btn_x) > 3:
            wrong.append(f"Quick-Swap: {name} is centred at x={btn_x}, its QR at x={qr_x}")
    page.keyboard.press("Escape")
    assert not wrong, "QR codes that don't match their buttons:\n  " + "\n  ".join(wrong)
