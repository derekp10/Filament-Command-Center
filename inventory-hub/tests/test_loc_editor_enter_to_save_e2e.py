"""Group 46.2: Enter in the location editor saves it — it is never a scan of "t".

Root cause (2026-09-29): the editor had no Enter-to-save, and the global scan
accumulator (templates/components/scripts.html) skips only INPUT/TEXTAREA
targets. A letter typed on the Type <select> (native typeahead) therefore landed
in state.scanBuffer, and Enter submitted it to /api/identify_scan as the code
"t" — Derek's "Type dropdown + 't' + Enter → error instead of saving".

The fix is a keydown handler on #locModal, NOT a global "ignore SELECT" in the
scanner (a focused dropdown would then swallow a blind barcode scan), so a
scanner burst on the dropdown still reaches the scan path.

HERMETIC AGAINST DEV DATA: one context route answers every non-GET
synthetically and records it (POST /api/locations, /api/identify_scan and
/api/state/buffer included), so no location is ever saved and no scan reaches
the backend. GETs pass through read-only, except /api/state/buffer, which is
served from the fake so dev's real buffer never enters the page.

HEAD proof: on the pre-fix inv_loc_mgr.js, the first test POSTs identify_scan
with text "t" and never saves, and the second never saves at all (Enter in a
text field did nothing).
"""
from __future__ import annotations

import json
import time

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

NEW_ID = "FCC-TEST-ENTER-SAVE"
OK = {"success": True}

pytestmark = pytest.mark.usefixtures("require_server")


class FakeBackend:
    def __init__(self, page: Page, locations=None):
        self.locations = locations   # None = GET /api/locations passes through read-only
        self.posts: list[tuple[str, dict]] = []
        self.urls: list[tuple[str, str]] = []   # (method, full url) of every non-GET
        self.buffer: list = []
        page.context.route("**/*", self._handle)

    @staticmethod
    def _json(route, payload, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    def _handle(self, route):
        try:
            self._route(route)
        except PlaywrightError as e:
            if "closed" not in str(e).lower():
                raise

    def _route(self, route):
        req = route.request
        path = req.url.split("://", 1)[-1].split("/", 1)[-1]
        path = "/" + path.split("?", 1)[0]
        if req.method in ("GET", "HEAD", "OPTIONS"):
            if path == "/api/state/buffer":
                self._json(route, self.buffer)
                return
            if path == "/api/locations" and self.locations is not None:
                self._json(route, self.locations)
                return
            route.continue_()
            return
        try:
            body = json.loads(req.post_data or "{}")
        except (TypeError, ValueError):
            body = {}
        if not isinstance(body, dict):
            body = {"_raw": body}
        self.posts.append((path, body))
        self.urls.append((req.method, req.url))
        if path == "/api/state/buffer":
            buf = body.get("buffer")
            self.buffer = buf if isinstance(buf, list) else []
        self._json(route, OK)

    def bodies(self, path: str) -> list[dict]:
        return [b for p, b in self.posts if p == path]


@pytest.fixture(autouse=True)
def _drop_routes_in_flight(page: Page):
    """Close the page BEFORE un-routing: a live page's next buffer poll or persist
    would otherwise reach the real dev server."""
    yield
    try:
        page.close()
    except PlaywrightError:
        pass
    try:
        page.context.unroute_all(behavior="ignoreErrors")
    except PlaywrightError:
        pass


def _until(page: Page, predicate, timeout_ms: int, what: str) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if predicate():
            return
        page.wait_for_timeout(50)
    assert predicate(), what


def _open_editor(page: Page, base_url: str, reset_dom_state_js: str, locations=None) -> FakeBackend:
    be = FakeBackend(page, locations=locations)
    page.goto(base_url.rstrip("/") + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "typeof state !== 'undefined' && typeof modals !== 'undefined' && !!modals.locModal"
        " && typeof window.openAddModal === 'function' && typeof window.saveLocation === 'function'",
        timeout=20_000,
    )
    page.evaluate(reset_dom_state_js)
    page.evaluate("() => window.openAddModal()")
    page.wait_for_function("document.getElementById('locModal').classList.contains('show')",
                           timeout=10_000)
    # `.show` lands at the START of the fade; the shown handler later focuses
    # #edit-id and selects its text. Wait for it, or a key meant for another
    # field can land in the ID under load.
    page.wait_for_function("document.activeElement && document.activeElement.id === 'edit-id'",
                           timeout=10_000)
    page.fill("#edit-id", NEW_ID)
    page.fill("#edit-name", "FCC Test Enter Save")
    return be


def _scan_texts(be: FakeBackend) -> list:
    return [b.get("text") for b in be.bodies("/api/identify_scan")]


def test_letter_then_enter_on_the_type_dropdown_saves(page: Page, base_url, reset_dom_state_js):
    be = _open_editor(page, base_url, reset_dom_state_js)
    page.focus("#edit-type")
    page.keyboard.press("t")
    page.keyboard.press("Enter")

    _until(page, lambda: be.bodies("/api/locations"), 5_000,
           f"Enter on the Type dropdown never saved; scans sent: {_scan_texts(be)}")
    saved = be.bodies("/api/locations")[0]
    assert saved["new_data"]["LocationID"] == NEW_ID, saved
    page.wait_for_timeout(300)
    assert not be.bodies("/api/identify_scan"), (
        f"Enter on the Type dropdown was ALSO submitted as a scan: {_scan_texts(be)}")
    assert page.evaluate("() => state.scanBuffer") == "", \
        "the typeahead letter was left in the scan accumulator"


def test_enter_in_a_text_field_saves(page: Page, base_url, reset_dom_state_js):
    be = _open_editor(page, base_url, reset_dom_state_js)
    page.focus("#edit-name")
    page.keyboard.press("Enter")
    _until(page, lambda: be.bodies("/api/locations"), 5_000, "Enter in Friendly Name never saved")
    assert be.bodies("/api/locations")[0]["new_data"]["Name"] == "FCC Test Enter Save"


def test_a_scanner_burst_on_the_dropdown_is_still_a_scan(page: Page, base_url, reset_dom_state_js):
    """Not a global 'ignore SELECT': a barcode scanned while the dropdown has
    focus still reaches the scan path, and doesn't save the half-edited row. A
    purely numeric barcode has no scan-shaped character, so only the scanner-
    speed rule can tell it from typing. The burst and its Enter are dispatched
    in ONE evaluate, so the timing can't depend on this machine's load."""
    be = _open_editor(page, base_url, reset_dom_state_js)
    page.focus("#edit-type")
    page.evaluate("""() => {
        state.scanBuffer = '12345678'; state.scanStartTime = Date.now();
        document.getElementById('edit-type').dispatchEvent(
            new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true}));
    }""")

    _until(page, lambda: "12345678" in _scan_texts(be), 5_000,
           "a scanner burst on the focused Type dropdown never reached /api/identify_scan")
    page.wait_for_timeout(300)
    assert not be.bodies("/api/locations"), (
        f"a scanner burst on the dropdown saved the location: {be.bodies('/api/locations')}")


def test_a_slow_scanner_on_the_dropdown_is_still_a_scan(page: Page, base_url, reset_dom_state_js):
    """A scanner slower than the 150 ms burst window still types a scan-shaped
    payload (a ':' no typeahead produces): it stays a scan, never a save."""
    be = _open_editor(page, base_url, reset_dom_state_js)
    page.focus("#edit-type")
    page.evaluate("""() => {
        state.scanBuffer = 'LOC:FCC-TEST-SLOW'; state.scanStartTime = Date.now() - 1000;
        document.getElementById('edit-type').dispatchEvent(
            new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true}));
    }""")
    _until(page, lambda: "LOC:FCC-TEST-SLOW" in _scan_texts(be), 5_000,
           "a slow scan on the Type dropdown never reached /api/identify_scan")
    page.wait_for_timeout(300)
    assert not be.bodies("/api/locations")


def test_a_scan_typed_into_a_text_field_is_a_scan_not_a_save(page: Page, base_url, reset_dom_state_js):
    """The accumulator ignores INPUT targets, so a barcode scanned while Friendly
    Name has focus types into the field. Enter-to-save then SAVED it as the name
    (Group 46 review). The shared field-scan capture now sends it to the scan path
    and leaves the field as it was. Keydowns dispatched in one evaluate = scanner
    speed, on any machine."""
    be = _open_editor(page, base_url, reset_dom_state_js)
    page.focus("#edit-name")
    page.evaluate("""() => {
        const el = document.getElementById('edit-name');
        for (const c of 'LOC:FCC-TEST-SCAN') {
            el.dispatchEvent(new KeyboardEvent('keydown', {key: c, bubbles: true, cancelable: true}));
        }
        el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true}));
    }""")
    _until(page, lambda: "LOC:FCC-TEST-SCAN" in _scan_texts(be), 5_000,
           "a scan typed into Friendly Name never reached /api/identify_scan")
    page.wait_for_timeout(300)
    assert not be.bodies("/api/locations"), (
        f"a scan typed into a text field was saved into the location: {be.bodies('/api/locations')}")
    assert page.input_value("#edit-name") == "FCC Test Enter Save"


def test_a_held_or_doubled_enter_saves_once(page: Page, base_url, reset_dom_state_js):
    be = _open_editor(page, base_url, reset_dom_state_js)
    page.focus("#edit-name")
    page.evaluate("""() => {
        const el = document.getElementById('edit-name');
        const enter = (repeat) => el.dispatchEvent(
            new KeyboardEvent('keydown', {key: 'Enter', repeat, bubbles: true, cancelable: true}));
        enter(false); enter(true); enter(false);
    }""")
    _until(page, lambda: be.bodies("/api/locations"), 5_000, "Enter never saved")
    page.wait_for_timeout(500)
    assert len(be.bodies("/api/locations")) == 1, (
        f"one Enter press posted {len(be.bodies('/api/locations'))} saves")


def test_enter_on_a_focused_button_presses_it(page: Page, base_url, reset_dom_state_js):
    """The accumulator cancelled every Enter outside INPUT/TEXTAREA (until Group
    50.6), which killed Enter on the editor's buttons, and it submitted leftover typeahead letters as
    a scan. Enter on 💾 Save now saves; the stray 't' goes nowhere."""
    be = _open_editor(page, base_url, reset_dom_state_js)
    page.focus("#locModal .modal-footer .btn-primary")
    page.evaluate("() => { state.scanBuffer = 't'; state.scanStartTime = Date.now() - 1000; }")
    page.keyboard.press("Enter")
    _until(page, lambda: be.bodies("/api/locations"), 5_000, "Enter on the focused Save button didn't save")
    page.wait_for_timeout(300)
    assert not be.bodies("/api/identify_scan"), f"leftover letters were scanned: {_scan_texts(be)}"


def test_editing_a_blank_id_row_is_refused_with_a_way_out(page: Page, base_url, reset_dom_state_js):
    """Group 46.5: the editor can't repair a row with no Location ID (saving it
    appends a SECOND row, and the next save says "already exists"), so it doesn't
    open; it says to delete the row and add it again."""
    FakeBackend(page)
    page.goto(base_url.rstrip("/") + "/", wait_until="domcontentloaded")
    page.wait_for_function("typeof window.openEdit === 'function' && typeof modals !== 'undefined'",
                           timeout=20_000)
    page.evaluate(reset_dom_state_js)
    page.evaluate("() => window.openEdit('')")
    page.wait_for_timeout(600)
    assert not page.evaluate("() => document.getElementById('locModal').classList.contains('show')")
    toast = page.evaluate(
        "() => Array.from(document.querySelectorAll('.toast-msg')).map(t => t.textContent).join(' | ')")
    assert "no Location ID" in toast, toast


def test_enter_in_the_parent_tree_picker_is_not_scanned(page: Page, base_url, reset_dom_state_js):
    """Same class as 46.2, in the 🌳 Browse… picker: its Enter reached the scan
    accumulator, which submitted letters typed in the picker as a scan."""
    # The picker fetches /api/locations itself; a fixed list keeps it fast and off
    # dev's Spoolman-backed synthesizer.
    rows = [{"LocationID": "FCC-TEST-ROOM", "Name": "FCC Test Room", "Type": "Room",
             "Max Spools": "0", "parent_id": None}]
    be = _open_editor(page, base_url, reset_dom_state_js, locations=rows)
    page.evaluate("() => window.openParentTreePicker()")   # what 🌳 Browse… calls
    page.wait_for_selector("#fcc-parent-tree-picker .fcc-tp-node", state="attached", timeout=8_000)
    page.evaluate("""() => {
        state.scanBuffer = 'r'; state.scanStartTime = Date.now() - 1000;
        const node = document.querySelector('#fcc-parent-tree-picker .fcc-tp-node');
        node.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true}));
    }""")
    page.wait_for_timeout(500)
    assert not be.bodies("/api/identify_scan"), f"the picker's Enter was scanned: {_scan_texts(be)}"
    assert page.evaluate("() => state.scanBuffer") == ""


def test_save_with_a_blank_location_id_is_refused_client_side(page: Page, base_url, reset_dom_state_js):
    """Group 46.5: a blank id never reaches the server (which also 400s it), the
    user is told why, and the cursor goes back to the ID field."""
    be = _open_editor(page, base_url, reset_dom_state_js)
    page.fill("#edit-id", "   ")
    page.click("#locModal .modal-footer .btn-primary")   # 💾 Save Changes
    page.wait_for_timeout(400)
    assert not be.bodies("/api/locations"), (
        f"a blank LocationID was POSTed: {be.bodies('/api/locations')}")
    toast = page.evaluate(
        "() => Array.from(document.querySelectorAll('.toast-msg')).map(t => t.textContent).join(' | ')")
    assert "Enter a Location ID" in toast, toast
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "edit-id"
    assert page.evaluate("() => document.getElementById('edit-id').required") is True


def test_deleting_the_blank_id_row_uses_the_explicit_path(page: Page, base_url, reset_dom_state_js):
    """Group 46.5: the 🗑️ on a row saved with a blank id used to send ?id=, which
    the server refuses. It now sends ?blank_id=1 (the fake answers it; dev's own
    blank TestCart row is never touched)."""
    be = FakeBackend(page)
    page.goto(base_url.rstrip("/") + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "typeof state !== 'undefined' && typeof modals !== 'undefined' && !!modals.confirmModal"
        " && typeof window.deleteLoc === 'function'", timeout=20_000)
    page.evaluate(reset_dom_state_js)
    page.evaluate("() => window.deleteLoc('')")
    page.wait_for_function("document.getElementById('confirmModal').classList.contains('show')",
                           timeout=5_000)
    prompt = page.evaluate("() => document.getElementById('confirmModal').textContent")
    assert "blank Location ID" in prompt, prompt
    page.click("#confirmModal .btn-success")
    deletes = lambda: [u for m, u in be.urls if m == "DELETE" and "/api/locations" in u]  # noqa: E731
    _until(page, deletes, 5_000, "confirming the delete sent no DELETE /api/locations")
    assert len(deletes()) == 1 and deletes()[0].endswith("/api/locations?blank_id=1"), deletes()


def test_enter_save_is_in_the_shortcut_reference(page: Page, base_url, reset_dom_state_js):
    """CLAUDE.md: a new shortcut registers with shortcuts_registry.js. This file
    loads before the registry, so registering at eval time would silently skip."""
    _open_editor(page, base_url, reset_dom_state_js)
    listed = page.evaluate(
        "() => (document.getElementById('fcc-shortcuts-list') || {}).textContent || ''")
    assert "Location Editor" in listed and "Save the location" in listed, (
        f"Enter-to-save isn't in the ? reference: {listed[:400]!r}")
