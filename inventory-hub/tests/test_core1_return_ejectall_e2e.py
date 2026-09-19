"""Browser coverage for the CORE1 Return + Eject All guard fixes (2026-09-13).

BUG 1: Quick-Swap Return on a Printer row whose single toolhead shares the
printer's id (the Core One: row CORE1, head CORE1) showed "Nothing to return on
CORE1" and never called /api/quickswap/return: the frontend only looked for
"CORE1-*" heads. The Bind-a-Slot picker threw on the same row. The fake printer
here (FCC-TEST-P1 owning head FCC-TEST-P1) has exactly that shape.

BUG 2: a CMD:EJECTALL scan with the Location Manager closed prompted "Nuke all
unslotted in ?" and, on FORCE EXECUTE, cleared location "" (the backend matcher
reads that as every Unassigned spool). triggerEjectAll also toasted "Cleared!"
over a backend refusal.

The same decisions are pinned hermetically (node vm, runs --offline) in
test_core1_return_ejectall_js.py; this file checks the flows in a real browser.

HERMETIC AGAINST DEV DATA: one context route answers every non-GET synthetically
and records it, including POST /api/state/buffer. Fake FCC-TEST-* rows are
appended to GET /api/locations and the pulse's locations; GET /api/printer_map
gains the fake printer's group; the printer-state probe, toolhead_slots,
get_contents for FCC-TEST-*, /api/spools/<fake id> and /api/dryer_boxes/slots
are stubbed. Spool ids are fake (999xxx).
"""
from __future__ import annotations

import json
import re
import time
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

OK = {"success": True}
PRINTER_ID = "FCC-TEST-P1"
PRINTER_NAME = "FCC Test Core"
P1_ROW = {"LocationID": PRINTER_ID, "Name": PRINTER_NAME, "Type": "Printer", "Max Spools": "1",
          "toolheads": [{"location_id": PRINTER_ID, "position": 0}]}
BOX = "FCC-TEST-BOX"
BOX_ROW = {"LocationID": BOX, "Name": "FCC Test Box", "Type": "Dryer Box", "Max Spools": "4"}
SPOOL_ID = 999601
RESIDENT = {"id": SPOOL_ID, "display": "FCC Test PLA #999601", "location": PRINTER_ID, "slot": ""}
SPOOL_RECORD = {"success": True, "data": {"id": SPOOL_ID, "location": PRINTER_ID, "extra": {
    "physical_source": json.dumps(BOX), "physical_source_slot": json.dumps("2")}}}
REFUSAL = "No location given. Open a location in the Location Manager, then use Eject All."

TOAST_RECORDER_JS = """
(() => {
  window.__toastLog = [];
  let pending = null;
  const append = Node.prototype.appendChild;
  Node.prototype.appendChild = function (child) {
    const out = append.call(this, child);
    if (child && child.nodeType === 1 && child.classList && child.classList.contains('toast-msg')) {
      const cls = Array.from(child.classList).find(c => c.startsWith('toast-') && c !== 'toast-msg');
      pending = { text: child.textContent, type: cls ? cls.slice(6) : null, duration: null };
      window.__toastLog.push(pending);
    }
    return out;
  };
  const st = window.setTimeout;
  window.setTimeout = function (fn, ms, ...rest) {
    if (pending) { pending.duration = ms; pending = null; }
    return st.call(window, fn, ms, ...rest);
  };
})();
"""

SNAPSHOT_JS = """() => ({
  toasts: (window.__toastLog || []).slice(-6),
  overlayTitle: (document.getElementById('fcc-quickswap-confirm-title') || {}).textContent || null,
  safetyShown: document.getElementById('safetyModal').classList.contains('show'),
  safetyMsg: document.getElementById('safety-msg').textContent,
  manageShown: document.getElementById('manageModal').classList.contains('show'),
  manageLocId: document.getElementById('manage-loc-id').value,
})"""

OVERLAY_JS = """() => ({
  title: document.getElementById('fcc-quickswap-confirm-title').textContent,
  body: document.getElementById('fcc-quickswap-confirm-body').textContent,
})"""

# The fake printer's printer_map group, merged the way fetchPrinterMap caches it.
USE_P1_JS = """(row) => {
    state.printerMap = Object.assign({}, state.printerMap || {}, { [row.Name]: row.toolheads });
    window.renderQuickSwapSection(row);
}"""


class FakeBackend:
    """Answers every non-GET synthetically (and records it); stubs the GETs whose
    real dev data would make these tests nondeterministic."""

    def __init__(self, page: Page, *, contents=None, extra_locations=(), identify=None, manage_contents=None):
        self.posts: list[tuple[str, dict]] = []
        self.buffer: list = []
        self.contents = contents or {}
        self.extra_locations = list(extra_locations)
        self._identify = identify or (lambda body: {"type": "command", "cmd": "ejectall"})
        self._manage_contents = manage_contents or (lambda body: OK)
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
        parts = urlsplit(req.url)
        path = parts.path
        if req.method in ("GET", "HEAD", "OPTIONS"):
            if path == "/api/state/buffer":
                self._json(route, self.buffer)
                return
            if path.startswith("/api/printer_state/"):
                self._json(route, {"known": True, "is_active": False, "state": "IDLE",
                                   "printer_name": PRINTER_NAME})
                return
            if path.startswith("/api/machine/") and PRINTER_NAME in unquote(path):
                self._json(route, {"printer_name": PRINTER_NAME, "toolheads": {PRINTER_ID: []},
                                   "printer_pool": []})
                return
            if path == "/api/get_contents":
                loc = (parse_qs(parts.query).get("id") or [""])[0].upper()
                if loc.startswith("FCC-TEST-"):
                    self._json(route, self.contents.get(loc, []))
                    return
            m = re.fullmatch(r"/api/spools/(\d+)", path)
            if m and int(m.group(1)) == SPOOL_ID:
                self._json(route, SPOOL_RECORD)
                return
            if path == "/api/dryer_boxes/slots":
                self._json(route, {"slots": [{"box": BOX, "box_name": "FCC Test Box", "slot": "1",
                                              "target": None}]})
                return
            if path == "/api/printer_map" and req.method == "GET":
                self._fulfil_printer_map(route)
                return
            if req.method == "GET" and self.extra_locations and path in ("/api/locations", "/api/dashboard_pulse"):
                self._fulfil_with_extra_rows(route, None if path == "/api/locations" else "locations")
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
        if path == "/api/state/buffer":
            buf = body.get("buffer")
            self.buffer = buf if isinstance(buf, list) else []
            payload = OK
        elif path == "/api/identify_scan":
            payload = self._identify(body)
        elif path == "/api/manage_contents":
            payload = self._manage_contents(body)
        elif path == "/api/quickswap/return":
            payload = {"action": "return_done", "moved": SPOOL_ID, "box": BOX, "slot": "2"}
        else:
            payload = OK
        self._json(route, payload)

    def _fulfil_printer_map(self, route):
        resp = route.fetch()
        try:
            data = resp.json()
        except ValueError:
            data = {}
        printers = data.get("printers") if isinstance(data, dict) else None
        if isinstance(printers, dict):
            printers[PRINTER_NAME] = P1_ROW["toolheads"]
        self._json(route, data, status=resp.status)

    def _fulfil_with_extra_rows(self, route, key):
        """The real (read-only) response with the fake rows appended, so a
        heartbeat fetchLocations can never wipe them mid-test."""
        resp = route.fetch()
        try:
            data = resp.json()
        except ValueError:
            route.fulfill(status=resp.status, body=resp.body())
            return
        rows = data if key is None else (data.get(key) if isinstance(data, dict) else None)
        if isinstance(rows, list):
            have = {r.get("LocationID") for r in rows if isinstance(r, dict)}
            rows.extend(r for r in self.extra_locations if r["LocationID"] not in have)
        self._json(route, data, status=resp.status)

    def bodies(self, path: str) -> list[dict]:
        return [b for p, b in self.posts if p == path]


@pytest.fixture(autouse=True)
def _drop_routes_in_flight(page: Page):
    """A route callback still running at context close otherwise surfaces its
    TargetClosedError in the NEXT test's setup."""
    yield
    try:
        page.context.unroute_all(behavior="ignoreErrors")
    except PlaywrightError:
        pass


# Headless chromium denies the Wake Lock permission, and FCC's wake-lock helper
# surfaces that denial as an unhandled rejection. It is environment noise with a
# documented fallback (test_frontend_source_presence::test_request_wakelock_fallback),
# not anything these tests are about.
_IGNORED_PAGE_ERRORS = ("Wake Lock",)


def _boot(page: Page, base_url: str, reset_dom_state_js: str) -> list[str]:
    errors: list[str] = []
    page.on(
        "pageerror",
        lambda e: None if any(s in str(e) for s in _IGNORED_PAGE_ERRORS) else errors.append(str(e)),
    )
    page.add_init_script(TOAST_RECORDER_JS)
    page.goto(base_url.rstrip("/") + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "typeof state !== 'undefined' && typeof modals !== 'undefined' && !!modals.safetyModal"
        " && typeof window.processScan === 'function' && typeof window.returnToolheadToSlot === 'function'"
        " && typeof window.renderQuickSwapSection === 'function' && typeof window.openBindSlotPicker === 'function'"
        " && typeof window.triggerEjectAll === 'function' && typeof window.openManage === 'function'"
        " && typeof window.mountOverlay === 'function'",
        timeout=20_000,
    )
    page.evaluate(reset_dom_state_js)
    return errors


def _js_until(page: Page, expr: str, timeout_ms: int, what: str) -> None:
    try:
        page.wait_for_function(expr, timeout=timeout_ms)
    except PlaywrightTimeout:
        raise AssertionError(f"{what}\n  page: {page.evaluate(SNAPSHOT_JS)}") from None


def _until(page: Page, predicate, timeout_ms: int, what: str) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if predicate():
            return
        page.wait_for_timeout(50)   # pumps the event loop so route handlers run
    assert predicate(), f"{what}\n  page: {page.evaluate(SNAPSHOT_JS)}"


def _toasts(page: Page) -> list[dict]:
    return page.evaluate("window.__toastLog")


def _toast(page: Page, what: str, type_: str | None = None, contains=(), timeout_ms: int = 5_000) -> dict:
    conds = ["true"]
    if type_:
        conds.append(f"t.type === {json.dumps(type_)}")
    conds += [f"(t.text || '').includes({json.dumps(c)})" for c in contains]
    pred = "t => " + " && ".join(conds)
    _js_until(page, f"window.__toastLog.some({pred})", timeout_ms, what)
    return page.evaluate(f"window.__toastLog.find({pred})")


def _wait_rows(page: Page, ids: list[str]) -> None:
    page.wait_for_function(
        f"{json.dumps(ids)}.every(id => state.allLocations.some(l => l.LocationID === id))", timeout=15_000)


def _safety_on_screen(page: Page, text: str, what: str) -> None:
    _js_until(page, "window.isGatingModalOnScreen && window.isGatingModalOnScreen('safetyModal')"
              f" && document.getElementById('safety-msg').textContent.includes({json.dumps(text)})",
              5_000, what)


def _assert_no_safety_prompt(page: Page) -> None:
    page.wait_for_timeout(700)
    snap = page.evaluate(SNAPSHOT_JS)
    assert not snap["safetyShown"], f"an Eject All safety prompt opened: {snap}"
    assert "Nuke all" not in (snap["safetyMsg"] or ""), snap


# ---------------------------------------------------------------------------
# BUG 1 — Return and Bind picker on a CORE1-shaped printer
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_return_on_a_core1_shaped_printer_reaches_the_backend(
        page: Page, base_url: str, reset_dom_state_js: str):
    """FAILS on the pre-fix inv_quickswap.js: "Nothing to return on FCC-TEST-P1",
    whose Yes sent nothing."""
    be = FakeBackend(page, contents={PRINTER_ID: [RESIDENT]}, extra_locations=[P1_ROW, BOX_ROW])
    errors = _boot(page, base_url, reset_dom_state_js)
    _wait_rows(page, [PRINTER_ID, BOX])

    page.evaluate(USE_P1_JS, P1_ROW)
    page.evaluate("window.returnToolheadToSlot()")
    _js_until(page, "!!document.getElementById('fcc-quickswap-confirm-title')", 6_000,
              "the Return overlay never opened")
    ov = page.evaluate(OVERLAY_JS)
    assert ov["title"] == f"Return the spool on {PRINTER_ID}?", ov
    assert f"Sending back to: {BOX} slot 2 (original source)" in ov["body"], ov

    page.click("#fcc-quickswap-yes")
    _until(page, lambda: be.bodies("/api/quickswap/return"), 5_000, "confirming the Return sent nothing")
    assert be.bodies("/api/quickswap/return") == [{"toolhead": PRINTER_ID}]
    _toast(page, "no success toast after return_done", type_="success", contains=(str(SPOOL_ID),))
    assert errors == [], errors


@pytest.mark.usefixtures("require_server")
def test_bind_picker_opens_on_a_core1_shaped_printer(
        page: Page, base_url: str, reset_dom_state_js: str):
    """FAILS on the pre-fix inv_quickswap.js: openBindSlotPicker threw reading
    toolheadOptions[0].value and the picker never opened."""
    be = FakeBackend(page, extra_locations=[P1_ROW])
    errors = _boot(page, base_url, reset_dom_state_js)
    _wait_rows(page, [PRINTER_ID])

    page.evaluate(USE_P1_JS, P1_ROW)
    try:
        page.evaluate("window.openBindSlotPicker()")
    except PlaywrightError as e:
        raise AssertionError(f"openBindSlotPicker threw on a CORE1-shaped printer: {e}") from None
    _js_until(page, "getComputedStyle(document.getElementById('fcc-bind-picker-overlay')).display !== 'none'",
              5_000, "the Bind picker never opened on a CORE1-shaped printer")
    assert page.text_content("#fcc-bind-picker-toolhead") == PRINTER_ID
    assert page.evaluate("document.getElementById('fcc-bind-picker-toolhead-row').style.display") == "none"
    page.evaluate("window.closeBindSlotPicker()")
    assert not [p for p, _ in be.posts if p.startswith("/api/dryer_box/")], be.posts
    assert errors == [], errors


# ---------------------------------------------------------------------------
# BUG 2 — CMD:EJECTALL with no location open, and triggerEjectAll's honesty
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("text", [pytest.param("CMD:EJECTALL", id="client-match"),
                                  pytest.param("FCC-TEST CMD:EJECTALL", id="backend-answered")])
def test_ejectall_scan_with_no_location_open_prompts_nothing(
        page: Page, base_url: str, reset_dom_state_js: str, text: str):
    """FAILS on the pre-fix inv_cmd.js for both routes: "Nuke all unslotted in ?"
    opened, one click away from clearing every Unassigned spool."""
    be = FakeBackend(page)
    _boot(page, base_url, reset_dom_state_js)
    _js_until(page, "!document.getElementById('manageModal').classList.contains('show')", 3_000,
              "precondition: the Location Manager must be closed")
    page.evaluate("document.getElementById('manage-loc-id').value = ''")

    page.evaluate("(t) => processScan(t, 'barcode')", text)
    toast = _toast(page, "no warning explained the ignored Eject All scan", type_="warning",
                   contains=("Eject All ignored",))
    assert toast["duration"] and toast["duration"] >= 7000, toast
    _until(page, lambda: [b for b in be.bodies("/api/log_event")
                          if b.get("level") == "WARNING" and "CMD:EJECTALL" in (b.get("msg") or "")],
           3_000, "the ignored scan wrote no Activity Log WARNING")
    _assert_no_safety_prompt(page)
    assert be.bodies("/api/manage_contents") == [], be.posts
    if text != "CMD:EJECTALL":
        assert be.bodies("/api/identify_scan"), "precondition: the backend-answered route was not exercised"


@pytest.mark.usefixtures("require_server")
def test_ejectall_scan_with_a_location_open_still_prompts_and_clears(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Control, PASSES on the pre-fix modules too: with the manager open on
    FCC-TEST-BOX the scan prompts for that box and FORCE EXECUTE clears it."""
    be = FakeBackend(page, contents={BOX: []}, extra_locations=[BOX_ROW])
    _boot(page, base_url, reset_dom_state_js)
    _wait_rows(page, [BOX])

    page.evaluate("(id) => window.openManage(id)", BOX)
    _js_until(page, "document.getElementById('manageModal').classList.contains('show')"
              f" && document.getElementById('manage-loc-id').value === {json.dumps(BOX)}",
              8_000, "the Location Manager never opened on the fake box")
    page.evaluate("processScan('CMD:EJECTALL', 'barcode')")
    _safety_on_screen(page, f"Nuke all unslotted in {BOX}?", "the Eject All prompt never showed for the open box")
    page.click("#safetyModal .btn-danger")

    _until(page, lambda: be.bodies("/api/manage_contents"), 5_000, "FORCE EXECUTE sent nothing")
    assert be.bodies("/api/manage_contents") == [{"action": "clear_location", "location": BOX}]
    _toast(page, "no Cleared! toast after a successful Eject All", contains=("Cleared!",))


@pytest.mark.usefixtures("require_server")
def test_eject_all_backend_refusal_is_not_reported_as_cleared(
        page: Page, base_url: str, reset_dom_state_js: str):
    """FAILS on the pre-fix inv_loc_mgr.js: a {success: false} answer toasted
    "Cleared!"."""
    be = FakeBackend(page, manage_contents=lambda b: {"success": False, "msg": REFUSAL})
    _boot(page, base_url, reset_dom_state_js)

    page.evaluate("(id) => window.triggerEjectAll(id)", BOX)
    _safety_on_screen(page, f"Nuke all unslotted in {BOX}?", "the Eject All prompt never showed")
    page.click("#safetyModal .btn-danger")

    _until(page, lambda: be.bodies("/api/manage_contents"), 5_000, "FORCE EXECUTE sent nothing")
    toast = _toast(page, "the refusal was not shown", type_="warning", contains=(REFUSAL,))
    assert toast["duration"] and toast["duration"] >= 7000, toast
    page.wait_for_timeout(500)
    assert not [t for t in _toasts(page) if (t["text"] or "") == "Cleared!"], _toasts(page)


@pytest.mark.usefixtures("require_server")
def test_trigger_eject_all_with_a_blank_location_prompts_nothing(
        page: Page, base_url: str, reset_dom_state_js: str):
    """FAILS on the pre-fix inv_loc_mgr.js: it prompted "Nuke all unslotted in ?"."""
    be = FakeBackend(page)
    _boot(page, base_url, reset_dom_state_js)

    page.evaluate("window.triggerEjectAll('')")
    toast = _toast(page, "no warning for a blank Eject All", type_="warning", contains=("Eject All needs a location",))
    assert toast["duration"] and toast["duration"] >= 7000, toast
    _assert_no_safety_prompt(page)
    assert be.bodies("/api/manage_contents") == [], be.posts
