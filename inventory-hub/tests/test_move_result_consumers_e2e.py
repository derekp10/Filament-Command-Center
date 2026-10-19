"""Browser coverage for the move-result consumers changed by fix G (2026-09-12,
review R3-08: "Frontend fix G has no offline test coverage at all").

The backend now reports what really happened to a move, and every frontend
consumer must read it rather than key on status === 'success':
  - a Quick-Swap deposit tells identify_scan whether the user confirmed an
    active-print banner (confirm_active_print), through click, Enter AND the QR
    (R2-01: Enter used to send nothing);
  - a deposit the backend answers assignment_requires_confirm re-opens the
    confirm with the PRINTING banner instead of dead-ending in "Deposit failed";
  - assignment_failed keeps the spool in the buffer and raises a >= 7 s error;
    not_deployed / auto_deploy_skipped raise a >= 7 s warning;
  - performContextAssign, _doAssignFinalize and the Force Location override read
    res.failures (R2-05);
  - the Return overlay counts only non-ghost residents and previews the spool's
    recorded physical_source box (R2-03).

HERMETIC AGAINST DEV DATA: one context route answers every non-GET synthetically
and records it, including POST /api/state/buffer (renderBuffer persists the
buffer on every change). GET /api/state/buffer serves the buffer the page last
persisted to that fake, so dev's real buffer never enters the page and the 2 s
loadBuffer heartbeat cannot rewrite a seeded buffer mid-test. The printer-state
probe, get_contents for FCC-TEST-*, /api/spools/<fake id> and
/api/dryer_boxes/slots are stubbed; GET /api/locations passes through read-only
with fake FCC-TEST-* rows appended. Spool ids are fake (999xxx).

Toast durations are recorded by an init script: showToast appends the toast and
then, synchronously, arms setTimeout(dismiss, duration), so the first setTimeout
after a toast is appended carries its duration.

HEAD proof (each docstring says what HEAD did): the scratch plugin
serve_head_js_g.py serves `git show HEAD:` inv_quickswap.js / inv_cmd.js /
inv_loc_mgr.js / inv_details.js to the test browser only.
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
BOX, SLOT, TH = "FCC-TEST-BOX", "2", "FCC-TEST-TH"
SPOOL = {"id": 999101, "display": "FCC Test PLA #999101", "color": "ff0000", "remaining_weight": 800}
REJECT = "400: rejected by test"
PRINTER = "FCC Test XL"
BOX_ROW = {"LocationID": BOX, "Name": "FCC Test Box", "Type": "Dryer Box", "Max Spools": "4"}
# Group 40.4: Force Location into a multi-slot box opens the slot picker, so the
# tests of the DIRECT path's answers force onto a plain shelf.
SHELF = "FCC-TEST-SHELF"
SHELF_ROW = {"LocationID": SHELF, "Name": "FCC Test Shelf", "Type": "Shelf", "Max Spools": "12"}
BINDINGS = {"slots": [{"box": "FCC-TEST-BIND", "slot": "1", "target": TH}]}


def _assignment(action: str, **extra) -> dict:
    return {"type": "assignment", "action": action, "location": BOX, "slot": SLOT, **extra}


DONE = _assignment("assignment_done", moved=SPOOL["id"], auto_deployed_to=TH)
FAILED = _assignment("assignment_failed", spool=SPOOL["id"], msg=REJECT)
NEEDS_CONFIRM = _assignment(
    "assignment_requires_confirm", msg=f"{PRINTER} is PRINTING — confirm to load",
    active_print={"printer_name": PRINTER, "state": "PRINTING", "toolhead": TH})
NOT_DEPLOYED = _assignment(
    "assignment_done", moved=SPOOL["id"], not_deployed_target=TH,
    not_deployed="Smart Load refused: FCC-TEST-TH still holds #999900")

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
  held: (state.heldSpools || []).map(s => s.id),
  toasts: window.__toastLog.slice(-6),
  overlayTitle: (document.getElementById('fcc-quickswap-confirm-title') || {}).textContent || null,
  overlayBody: (document.getElementById('fcc-quickswap-confirm-body') || {}).textContent || null,
})"""

OVERLAY_JS = """() => {
  const row = document.querySelector('#fcc-quickswap-confirm-overlay .fcc-confirm-qr-row');
  return {
    title: document.getElementById('fcc-quickswap-confirm-title').textContent,
    body: document.getElementById('fcc-quickswap-confirm-body').textContent,
    banner: !!document.querySelector('#fcc-quickswap-confirm-body .alert-warning'),
    qrSid: row ? row.id.replace(/-row$/, '') : null,
  };
}"""

# The same data attributes the Quick-Swap grid's "Deposit from buffer" button carries.
OPEN_DEPOSIT_JS = """([box, slot, th]) => {
    let btn = document.getElementById('fcc-test-deposit-btn');
    if (!btn) {
        btn = document.createElement('button');
        btn.id = 'fcc-test-deposit-btn';
        btn.className = 'fcc-qs-slot';
        btn.dataset.box = box; btn.dataset.slot = slot; btn.dataset.toolhead = th;
        btn.hidden = true;
        document.body.appendChild(btn);
    }
    window.quickSwapDeposit(btn);
}"""

# returnToolheadToSlot acts on the Quick-Swap section's current location, which
# renderQuickSwapSection sets synchronously before any fetch.
OPEN_RETURN_JS = """(th) => {
    if (!document.getElementById('manage-quickswap-section')) throw new Error('no #manage-quickswap-section');
    window.renderQuickSwapSection({ LocationID: th, Type: 'Tool Head' });
    window.returnToolheadToSlot();
}"""


class FakeBackend:
    """Answers every non-GET synthetically (and records it); stubs the GETs whose
    real dev data would make these tests nondeterministic."""

    def __init__(self, page: Page, *, printer_active=False, identify=None, manage_contents=None,
                 smart_move=None, contents=None, spools=None, dryer_slots=None, extra_locations=(),
                 responders=None, printer_state=None, placement=None, gets=None):
        # responders: {path: body -> (status, payload)}, payload a dict (JSON) or
        # a str (served as text/html, like a proxy's error page). Group 39.8.
        self.responders = dict(responders or {})
        # gets: {path: query dict -> (status, payload)} for GETs a test answers
        # itself (Group 40.6: the slot picker's /api/placement_options).
        self.gets = dict(gets or {})
        # printer_state: toolhead -> the /api/printer_state answer (Group 39.3),
        # overriding the printer_active default.
        self._printer_state = printer_state
        self.posts: list[tuple[str, dict]] = []
        self.buffer: list = []
        self.probes: list[str] = []
        self.printer_active = printer_active
        self._identify = identify or (lambda body: OK)
        self._manage_contents = manage_contents or (lambda body: {"status": "success"})
        self._smart_move = smart_move or (lambda body: {"status": "success"})
        self.contents = contents or {}
        self.spools = spools or {}
        self.dryer_slots = dryer_slots
        self.extra_locations = list(extra_locations)
        # placement: {location: the /api/placement_options model} (Group 40.4).
        self.placement = dict(placement or {})
        page.context.route("**/*", self._handle)

    @staticmethod
    def _json(route, payload, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    def _handle(self, route):
        try:
            self._route(route)
        except PlaywrightError as e:
            # A heartbeat request still in flight when the test's context
            # closes (route.fetch is a real round-trip). Nothing to answer.
            if "closed" not in str(e).lower():
                raise

    def _route(self, route):
        req = route.request
        parts = urlsplit(req.url)
        path = parts.path
        if req.method in ("GET", "HEAD", "OPTIONS"):
            if path in self.gets:
                status, payload = self.gets[path](parse_qs(parts.query))
                self._json(route, payload, status=status)
                return
            if path == "/api/state/buffer":
                self._json(route, self.buffer)
                return
            if path.startswith("/api/printer_state/"):
                self.probes.append(unquote(path[len("/api/printer_state/"):]))
                if self._printer_state is not None:
                    self._json(route, self._printer_state(self.probes[-1]))
                    return
                state = "PRINTING" if self.printer_active else "IDLE"
                self._json(route, {"known": True, "is_active": self.printer_active,
                                   "state": state, "printer_name": PRINTER})
                return
            if path == "/api/get_contents":
                loc = (parse_qs(parts.query).get("id") or [""])[0].upper()
                if loc.startswith("FCC-TEST-"):
                    self._json(route, self.contents.get(loc, []))
                    return
            m = re.fullmatch(r"/api/spools/(\d+)", path)
            if m and int(m.group(1)) >= 990000:
                sid = int(m.group(1))
                if sid in self.spools:
                    self._json(route, self.spools[sid])
                else:
                    self._json(route, {"success": False, "msg": "Spool not found"}, status=404)
                return
            if path == "/api/placement_options" and self.placement:
                loc = (parse_qs(parts.query).get("location") or [""])[0].upper()
                if loc in self.placement:
                    self._json(route, self.placement[loc])
                    return
            if path == "/api/dryer_boxes/slots" and self.dryer_slots is not None:
                self._json(route, self.dryer_slots)
                return
            if path == "/api/locations" and req.method == "GET" and self.extra_locations:
                resp = route.fetch()
                rows = resp.json()
                if isinstance(rows, list):
                    have = {r.get("LocationID") for r in rows if isinstance(r, dict)}
                    rows.extend(r for r in self.extra_locations if r["LocationID"] not in have)
                self._json(route, rows, status=resp.status)
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
        if path in self.responders:
            status, payload = self.responders[path](body)
            if isinstance(payload, str):
                route.fulfill(status=status, content_type="text/html", body=payload)
            else:
                self._json(route, payload, status=status)
            return
        if path == "/api/state/buffer":
            buf = body.get("buffer")
            self.buffer = buf if isinstance(buf, list) else []
            payload = OK
        elif path == "/api/identify_scan":
            payload = self._identify(body)
        elif path == "/api/manage_contents":
            payload = self._manage_contents(body)
        elif path == "/api/smart_move":
            payload = self._smart_move(body)
        else:
            payload = OK
        self._json(route, payload)

    def bodies(self, path: str) -> list[dict]:
        return [b for p, b in self.posts if p == path]


@pytest.fixture(autouse=True)
def _drop_routes_in_flight(page: Page):
    """A route callback still running at context close otherwise surfaces its
    TargetClosedError in the NEXT test's setup. Close the page FIRST: un-routing a
    live page lets its next buffer poll or persist reach the real dev server."""
    yield
    try:
        page.close()
    except PlaywrightError:
        pass
    try:
        page.context.unroute_all(behavior="ignoreErrors")
    except PlaywrightError:
        pass


def _boot(page: Page, base_url: str, reset_dom_state_js: str) -> None:
    page.add_init_script(TOAST_RECORDER_JS)
    page.goto(base_url.rstrip("/") + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "typeof state !== 'undefined' && typeof modals !== 'undefined' && !!modals.confirmModal"
        " && typeof window.processScan === 'function' && typeof window.quickSwapDeposit === 'function'"
        " && typeof window.returnToolheadToSlot === 'function' && typeof window.renderQuickSwapSection === 'function'"
        " && typeof window.doAssign === 'function' && typeof window.promptEditLocation === 'function'"
        " && typeof window.mountOverlay === 'function' && typeof window.SpoolCardBuilder !== 'undefined'",
        timeout=20_000,
    )
    page.evaluate(reset_dom_state_js)


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


def _held(page: Page) -> list:
    return page.evaluate("(state.heldSpools || []).map(s => s.id)")


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


def _seed_buffer(page: Page, be: FakeBackend, spools: list[dict]) -> None:
    page.evaluate("(spools) => { state.heldSpools = spools; renderBuffer(); }", spools)
    ids = [s["id"] for s in spools]
    _until(page, lambda: [s.get("id") for s in be.buffer if isinstance(s, dict)] == ids, 5_000,
           "the seeded buffer was never persisted (to the fake)")


def _wait_overlay(page: Page, what: str, banner: bool | None = None, title_contains: str | None = None,
                  timeout_ms: int = 6_000) -> dict:
    conds = ["!!document.getElementById('fcc-quickswap-confirm-title')"]
    if banner is True:
        conds.append("!!document.querySelector('#fcc-quickswap-confirm-body .alert-warning')")
    elif banner is False:
        conds.append("!document.querySelector('#fcc-quickswap-confirm-body .alert-warning')")
    if title_contains:
        conds.append("document.getElementById('fcc-quickswap-confirm-title').textContent"
                     f".includes({json.dumps(title_contains)})")
    _js_until(page, " && ".join(conds), timeout_ms, what)
    return page.evaluate(OVERLAY_JS)


def _confirm_overlay(page: Page, how: str, ov: dict) -> None:
    if how == "click":
        page.click("#fcc-quickswap-yes")
    elif how == "enter":
        _js_until(page, "document.activeElement && document.activeElement.id === 'fcc-quickswap-yes'",
                  3_000, "Yes never took focus, so Enter would not reach it")
        page.keyboard.press("Enter")
    else:
        assert ov["qrSid"], f"precondition: the PRINTING banner mounts confirm QRs: {ov}"
        page.evaluate("(t) => processScan(t, 'barcode')", f"CMD:CONFIRM:{ov['qrSid']}")


def _deposit(page: Page) -> None:
    page.evaluate(OPEN_DEPOSIT_JS, [BOX, SLOT, TH])


# ---------------------------------------------------------------------------
# (a) The deposit tells the backend whether an active-print banner was confirmed
# ---------------------------------------------------------------------------

PRINTING_STORE_Q = _assignment(
    "assignment_requires_confirm", confirm_type="active_print", can_store=True, target_slot=None,
    active_print={"printer_name": PRINTER, "state": "PRINTING", "toolhead": TH},
    active_prints=[{"toolhead": TH, "printer_name": PRINTER, "state": "PRINTING", "role": "feeds",
                    "spools": [SPOOL["id"]]}],
    fed_heads=[], spools=[SPOOL["id"]], moved=SPOOL["id"],
    title=f"Load #{SPOOL['id']} onto {TH}?",
    body=f"{PRINTER} is PRINTING. {BOX} slot {SLOT} feeds {TH}, so this also loads #{SPOOL['id']} onto {TH}.",
    msg=f"{PRINTER} is PRINTING. {BOX} slot {SLOT} feeds {TH}, so this also loads #{SPOOL['id']} onto {TH}. Continue?")


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("how", ["click_load", "enter_stores", "qr_load"])
def test_a_deposit_while_printing_is_one_question_the_three_way(
        page: Page, base_url: str, reset_dom_state_js: str, how: str):
    """Group 40.3, Derek (2026-10-14): one dialog. While the slot's head's
    printer prints, FCC asks anyway, so the deposit's own confirm is skipped and
    the server's three-way is the question. Load it instead (click, or its
    CMD:CONFIRM QR) confirms the head the question named; Enter stores (Derek: a
    toolhead isn't loaded mid-print) and confirms no head it doesn't load.
    Replaces the Group 39 test of the deposit's own PRINTING banner, which the
    deposit no longer shows (the server's question carries the print).
    FAILS on HEAD: HEAD opened the deposit's own banner confirm first, and its
    re-ask had no store."""
    be = FakeBackend(page, printer_active=True, identify=lambda b: (
        DONE if (b.get("confirmed_toolheads") or b.get("auto_deploy") is False) else PRINTING_STORE_Q))
    _boot(page, base_url, reset_dom_state_js)
    _seed_buffer(page, be, [SPOOL])
    _deposit(page)
    page.wait_for_selector("#fcc-active-print-confirm-overlay .fcc-apc-store", state="visible", timeout=8_000)
    assert page.locator("#fcc-quickswap-confirm-overlay").count() == 0, "two dialogs for one deposit"
    assert page.text_content("#fcc-active-print-confirm-overlay .fcc-apc-store").strip() \
        == f"Just store it in {BOX} slot {SLOT}"
    first = be.bodies("/api/identify_scan")[0]
    assert (first["confirmed_toolheads"], first["confirmed_fed_heads"], first["spool_id"], first["expected_feed"]) \
        == ([], [], SPOOL["id"], TH), first

    if how == "click_load":
        page.click("#fcc-active-print-confirm-overlay .fcc-apc-yes")
    elif how == "enter_stores":
        page.wait_for_function("() => document.activeElement && document.activeElement.classList.contains('fcc-apc-store')",
                               timeout=3_000)
        page.keyboard.press("Enter")
    else:
        sid = page.evaluate("() => document.querySelector('#fcc-active-print-confirm-overlay .fcc-confirm-qr-row')"
                            ".id.replace(/-row$/, '')")
        page.evaluate("(t) => processScan(t, 'barcode')", f"CMD:CONFIRM:{sid}")
    _until(page, lambda: len(be.bodies("/api/identify_scan")) >= 2, 5_000, f"{how} sent no replay")
    replay = be.bodies("/api/identify_scan")[1]
    if how == "enter_stores":
        assert replay["auto_deploy"] is False and replay["confirmed_toolheads"] == [], replay
    else:
        assert replay["confirmed_toolheads"] == [TH] and "auto_deploy" not in replay, replay
    assert replay["spool_id"] == SPOOL["id"] and replay["expected_feed"] == TH, replay
    assert be.probes == [TH], f"one probe decides the dialog: {be.probes}"
    _until(page, lambda: _held(page) == [], 5_000, "the answered deposit did not leave the buffer")


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("how", ["click", "enter"])
def test_deposit_with_the_printer_idle_never_claims_a_confirm(
        page: Page, base_url: str, reset_dom_state_js: str, how: str):
    """No banner, no QR, so nothing was confirmed. PASSES on HEAD too (HEAD sent
    no flag at all, which the backend reads as false); pinned so a later edit
    cannot start sending true without a warning the user actually saw."""
    be = FakeBackend(page, printer_active=False, identify=lambda b: DONE)
    _boot(page, base_url, reset_dom_state_js)
    _seed_buffer(page, be, [SPOOL])
    _deposit(page)
    ov = _wait_overlay(page, "the deposit confirm never opened", banner=False)
    assert not ov["qrSid"], ov

    _confirm_overlay(page, how, ov)
    _until(page, lambda: be.bodies("/api/identify_scan"), 5_000, f"confirming the deposit via {how} sent nothing")
    body = be.bodies("/api/identify_scan")[0]
    assert body.get("confirm_active_print", False) is False, body
    assert body.get("confirmed_toolheads") == [], body
    assert be.probes == [TH], be.probes


# ---------------------------------------------------------------------------
# (b) assignment_requires_confirm re-opens the confirm with the banner
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_deposit_answered_requires_confirm_reopens_with_the_banner_then_confirms(
        page: Page, base_url: str, reset_dom_state_js: str):
    """The overlay's probe missed the print (slow/unreachable printer), so no
    banner was shown and the backend answered assignment_requires_confirm. The
    handler must log a WARNING and re-open the confirm with the backend's own
    active_print as the banner (no second probe); confirming that posts the
    head it named (confirmed_toolheads). FAILS on HEAD: no branch for the action, so it
    toasted "Deposit failed: assignment_requires_confirm" and stopped."""
    be = FakeBackend(page, printer_active=False,
                     identify=lambda b: DONE if b.get("confirmed_toolheads") else NEEDS_CONFIRM)
    _boot(page, base_url, reset_dom_state_js)
    _seed_buffer(page, be, [SPOOL])
    _deposit(page)
    _wait_overlay(page, "the deposit confirm never opened", banner=False)
    page.click("#fcc-quickswap-yes")
    _until(page, lambda: be.bodies("/api/identify_scan"), 5_000, "the first deposit POST never went out")
    assert be.bodies("/api/identify_scan")[0].get("confirmed_toolheads") == []

    ov = _wait_overlay(page, "a deposit answered assignment_requires_confirm did not re-open the confirm "
                             "with the PRINTING banner", banner=True)
    assert f"{PRINTER} is PRINTING" in ov["body"], ov
    assert _held(page) == [SPOOL["id"]], "the spool must stay in the buffer while the confirm is pending"
    assert be.probes == [TH], f"the re-opened confirm must use the backend's answer, not re-probe: {be.probes}"
    assert not [t for t in _toasts(page) if t["type"] == "error"], _toasts(page)
    _until(page, lambda: [b for b in be.bodies("/api/log_event")
                          if b.get("level") == "WARNING" and "active-print confirm" in (b.get("msg") or "")],
           3_000, "the requires-confirm outcome wrote no Activity Log WARNING")

    page.click("#fcc-quickswap-yes")
    _until(page, lambda: len(be.bodies("/api/identify_scan")) >= 2, 5_000,
           "confirming the re-opened deposit sent nothing")
    # The head the backend's answer named (Group 39.1).
    assert be.bodies("/api/identify_scan")[1].get("confirmed_toolheads") == [TH], be.bodies("/api/identify_scan")
    _until(page, lambda: _held(page) == [], 5_000, "the confirmed deposit did not leave the buffer")


# ---------------------------------------------------------------------------
# (c) assignment_failed keeps the spool and says so; (d) not_deployed warns
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("path", ["scan", "scan_confirmed_replay", "deposit"])
def test_rejected_assignment_keeps_the_spool_in_the_buffer_with_a_7s_error(
        page: Page, base_url: str, reset_dom_state_js: str, path: str):
    """A rejected write used to come back as assignment_done; it is now
    assignment_failed and the spool is still in the buffer.
    FAILS on HEAD for all three: scan -> "Unknown assignment result" (4 s
    warning); the confirmed replay -> the msg as a 3 s SUCCESS toast; deposit ->
    "Deposit failed: assignment_failed" (5 s, without the reason)."""
    if path == "scan_confirmed_replay":
        identify = lambda b: FAILED if b.get("confirmed_toolheads") else NEEDS_CONFIRM  # noqa: E731
    else:
        identify = lambda b: FAILED  # noqa: E731
    be = FakeBackend(page, identify=identify)
    _boot(page, base_url, reset_dom_state_js)
    _seed_buffer(page, be, [SPOOL])

    if path == "deposit":
        _deposit(page)
        _wait_overlay(page, "the deposit confirm never opened", banner=False)
        page.click("#fcc-quickswap-yes")
    else:
        page.evaluate("(t) => processScan(t, 'barcode')", f"LOC:{BOX}:SLOT:{SLOT}")
        if path == "scan_confirmed_replay":
            page.wait_for_selector("#fcc-aps-yes", timeout=5_000)
            page.click("#fcc-aps-yes")
            _until(page, lambda: [b for b in be.bodies("/api/identify_scan") if b.get("confirmed_toolheads")],
                   5_000, "the confirmed replay never went out")

    toast = _toast(page, f"a rejected assignment ({path}) raised no error toast naming the reason",
                   type_="error", contains=(REJECT,))
    assert toast["duration"] and toast["duration"] >= 7000, toast
    page.wait_for_timeout(500)
    assert _held(page) == [SPOOL["id"]], f"a rejected assignment ({path}) dropped the spool from the buffer"
    assert not [t for t in _toasts(page) if t["type"] == "success"], _toasts(page)


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("path", ["scan", "deposit"])
def test_placed_but_not_deployed_raises_a_7s_warning(
        page: Page, base_url: str, reset_dom_state_js: str, path: str):
    """The spool landed in the box but the bound toolhead did not get it.
    FAILS on HEAD for both: only the success toast, nothing about the deploy."""
    be = FakeBackend(page, identify=lambda b: NOT_DEPLOYED)
    _boot(page, base_url, reset_dom_state_js)
    _seed_buffer(page, be, [SPOOL])
    if path == "deposit":
        _deposit(page)
        _wait_overlay(page, "the deposit confirm never opened", banner=False)
        page.click("#fcc-quickswap-yes")
    else:
        page.evaluate("(t) => processScan(t, 'barcode')", f"LOC:{BOX}:SLOT:{SLOT}")

    toast = _toast(page, f"a not-deployed result ({path}) raised no warning naming the reason",
                   type_="warning", contains=("NOT deployed", "Smart Load refused"))
    assert toast["duration"] and toast["duration"] >= 7000, toast
    _until(page, lambda: _held(page) == [], 5_000, "the placed spool did not leave the buffer")


# ---------------------------------------------------------------------------
# (e) performContextAssign, (f) _doAssignFinalize, (g) Force Location override
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_context_assign_with_failures_drops_only_the_moved_spools(
        page: Page, base_url: str, reset_dom_state_js: str):
    """/api/smart_move answers status 'success' even when a write was rejected;
    the rejected id is in res.failures. FAILS on HEAD: every id left the buffer
    under "Assigned 3 items!", with no error and no deploy warning."""
    ids = [999201, 999202, 999203]
    be = FakeBackend(page, smart_move=lambda b: {
        "status": "success", "failures": {"999202": REJECT},
        "auto_deploy_skipped": {"999203": "FCC-TEST-TH is printing"}, "auto_deploy_target": TH})
    _boot(page, base_url, reset_dom_state_js)
    _seed_buffer(page, be, [{"id": i, "display": f"FCC Test #{i}", "color": "00ff00"} for i in ids])

    page.evaluate("(tid) => performContextAssign(tid, null, false, null)", BOX)
    _until(page, lambda: be.bodies("/api/smart_move"), 5_000, "performContextAssign sent nothing")
    body = be.bodies("/api/smart_move")[0]
    assert body["location"] == BOX and body["spools"] == ids, body

    err = _toast(page, "the failed id raised no error toast", type_="error", contains=("#999202", REJECT))
    assert err["duration"] and err["duration"] >= 7000, err
    warn = _toast(page, "the skipped deploy raised no warning", type_="warning", contains=("#999203", "NOT deployed"))
    assert warn["duration"] and warn["duration"] >= 7000, warn
    _toast(page, "no success toast for the two spools that moved", type_="success", contains=("Assigned 2 items",))
    _until(page, lambda: _held(page) == [999202], 5_000, "the buffer should keep exactly the failed spool")
    page.wait_for_timeout(500)
    assert _held(page) == [999202]


@pytest.mark.usefixtures("require_server")
def test_context_assign_yes_names_the_slot_and_the_spool_it_asked_about(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Group 40.0e: a slotless move into a multi-slot box is given its slot before
    the question, and the answer carries it (`target_slot`). The Yes sends that
    slot back as `picked_slot` (the server keeps it only while it is still free,
    so it never unseats anyone), and names the spool the question was about: a
    spool scanned into the buffer while the dialog is open stays in the buffer.
    FAILS on HEAD: the replay sent no slot and re-read the live buffer (both
    spools).
    Group 40.3: a printing answer that can store is the three-way (the engine
    sends its title and body for a slot that loads a head); Load it instead
    keeps the Yes button's id, and the replay also says what it confirmed and
    which feed it was about."""
    ask = {"status": "requires_confirm", "confirm_type": "active_print",
           "active_print": {"toolhead": TH, "printer_name": PRINTER, "state": "PRINTING"},
           "active_prints": [{"toolhead": TH, "printer_name": PRINTER, "state": "PRINTING",
                              "role": "feeds", "spools": [999211]}],
           "fed_heads": [], "can_store": True, "target_slot": SLOT,
           "title": f"Load #999211 onto {TH}?",
           "body": f"{PRINTER} is PRINTING. {BOX} slot {SLOT} feeds {TH}, so this also loads #999211 "
                   f"onto {TH} and unloads what {TH} holds.",
           "msg": f"{PRINTER} is PRINTING. {BOX} slot {SLOT} feeds {TH}, so this also loads #999211 "
                  f"onto {TH} and unloads what {TH} holds. Continue?"}
    be = FakeBackend(page, smart_move=lambda b: (
        {"status": "success", "failures": {}} if b.get("confirmed_toolheads") else ask))
    _boot(page, base_url, reset_dom_state_js)
    _seed_buffer(page, be, [{"id": 999211, "display": "FCC Test #999211", "color": "00ff00"}])

    page.evaluate("(tid) => performContextAssign(tid, null, [], null)", BOX)
    page.wait_for_selector("#fcc-active-print-scan-overlay #fcc-aps-yes", state="visible", timeout=5_000)
    assert be.bodies("/api/smart_move")[0]["slot"] is None, be.bodies("/api/smart_move")
    page.evaluate("() => { state.heldSpools.push({id: 999212, display: 'FCC Test #999212', color: '0000ff'});"
                  " renderBuffer(); }")
    page.click("#fcc-active-print-scan-overlay #fcc-aps-yes")
    _until(page, lambda: len(be.bodies("/api/smart_move")) >= 2, 5_000, "Yes sent no retry")
    replay = be.bodies("/api/smart_move")[1]
    assert replay["picked_slot"] == SLOT and replay["slot"] is None, replay
    assert replay["spools"] == [999211], replay
    assert replay["confirmed_toolheads"] == [TH], replay
    assert replay["confirmed_fed_heads"] == [] and replay["expected_feed"] == TH, replay
    assert "auto_deploy" not in replay, replay
    _until(page, lambda: _held(page) == [999212], 5_000, "the late spool should stay in the buffer")


@pytest.mark.usefixtures("require_server")
def test_slot_assign_with_a_failure_leaves_the_buffer_untouched(
        page: Page, base_url: str, reset_dom_state_js: str):
    """doAssign -> _doAssignFinalize (a non-toolhead target, so no probe) with
    manage_contents answering status 'success' + failures[spool]: no splice, no
    swapDisplaced push, a 7 s error. FAILS on HEAD: "Assigned", the spool
    spliced out and the displaced spool pushed in."""
    be = FakeBackend(page, manage_contents=lambda b: {"status": "success", "failures": {"999301": REJECT}})
    _boot(page, base_url, reset_dom_state_js)
    _seed_buffer(page, be, [{"id": 999301, "display": "FCC Test #999301", "color": "0000ff"},
                            {"id": 999302, "display": "FCC Test #999302", "color": "0000ff"}])

    page.evaluate("""([loc, sid]) => window.doAssign(loc, sid, 1, true,
        { swapDisplaced: { id: 999399, display: 'FCC Test displaced', color: 'ffff00' } })""", [BOX, 999301])
    _until(page, lambda: be.bodies("/api/manage_contents"), 5_000, "doAssign sent nothing")
    body = be.bodies("/api/manage_contents")[0]
    assert (body["action"], body["location"], body["spool_id"], body["origin"]) == ("add", BOX, "ID:999301", "buffer"), body

    err = _toast(page, "a failed slot assign raised no error toast", type_="error", contains=("#999301", REJECT))
    assert err["duration"] and err["duration"] >= 7000, err
    page.wait_for_timeout(500)
    assert _held(page) == [999301, 999302], "a failed slot assign mutated the buffer"
    assert not [t for t in _toasts(page) if t["text"] == "Assigned"], _toasts(page)


@pytest.mark.usefixtures("require_server")
def test_force_location_override_with_a_failure_shows_the_error(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Spool details -> Force Location -> double-click a shelf row (21.5 commits
    in one gesture). manage_contents answers status 'success' + failures[spool].
    FAILS on HEAD: "Location updated via override" (R2-05). (A shelf since Group
    40.4: a multi-slot box opens the slot picker first.)"""
    be = FakeBackend(page, manage_contents=lambda b: {"status": "success", "failures": {"999401": REJECT}},
                     extra_locations=[BOX_ROW, SHELF_ROW])
    _boot(page, base_url, reset_dom_state_js)

    _force_to(page, SHELF)
    _until(page, lambda: be.bodies("/api/manage_contents"), 5_000, "the override sent nothing")
    # Group 40.3: every door request carries confirmed_fed_heads (one without it
    # gets the stale-page refusal instead of the head_fed question).
    assert be.bodies("/api/manage_contents")[0] == {
        "action": "add", "location": SHELF, "spool_id": 999401, "origin": "manual_override",
        "confirmed_toolheads": [], "confirmed_fed_heads": []}

    err = _toast(page, "a failed override raised no error toast", type_="error", contains=("#999401", REJECT))
    assert err["duration"] and err["duration"] >= 7000, err
    page.wait_for_timeout(500)
    assert not [t for t in _toasts(page) if "Location updated via override" in (t["text"] or "")], _toasts(page)


_FORCE_ASK = {"status": "requires_confirm", "confirm_type": "active_print",
              "active_print": {"toolhead": TH, "printer_name": PRINTER, "state": "PRINTING"},
              "active_prints": [{"toolhead": TH, "printer_name": PRINTER, "state": "PRINTING",
                                 "role": "source", "spools": [999401]}],
              "msg": f"#999401 is loaded on {TH}. Moving it to {SHELF} means FCC stops charging this print to it. Continue?"}


def _force_to(page: Page, loc: str) -> None:
    page.evaluate("(sid) => window.promptEditLocation(sid, 'Unassigned')", 999401)
    item = f".swal-loc-item[data-id='{loc}']"
    page.wait_for_selector(item, state="attached", timeout=10_000)
    page.dispatch_event(item, "dblclick")


@pytest.mark.usefixtures("require_server")
def test_force_location_asks_on_an_active_print_then_moves_with_the_head(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Group 39.5: a requires_confirm answer used to be a dead-end 7 s error. Now
    the shared confirm shows the server's message, and Yes retries confirming the
    head it named. HEAD proof: no confirm, an error toast."""
    be = FakeBackend(page, manage_contents=lambda b: (
        {"status": "success"} if b.get("confirmed_toolheads") else _FORCE_ASK), extra_locations=[SHELF_ROW])
    _boot(page, base_url, reset_dom_state_js)
    _force_to(page, SHELF)
    page.wait_for_selector("#fcc-active-print-confirm-overlay .fcc-apc-yes", state="visible", timeout=5_000)
    assert "stops charging this print" in page.text_content("#fcc-active-print-confirm-overlay .fcc-apc-msg")
    page.click("#fcc-active-print-confirm-overlay .fcc-apc-yes")
    _until(page, lambda: len(be.bodies("/api/manage_contents")) >= 2, 5_000, "Yes sent no retry")
    assert be.bodies("/api/manage_contents")[1]["confirmed_toolheads"] == [TH], be.bodies("/api/manage_contents")
    _toast(page, "the confirmed override raised no success toast", type_="success",
           contains=("Location updated via override",))


@pytest.mark.usefixtures("require_server")
def test_force_location_into_a_box_opens_the_slot_picker_and_the_yes_keeps_its_slot(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Group 40.4 (Derek's D2.4: "Force Location into a box behaves exactly like
    a box-label scan"): Force Location into a multi-slot box opens the slot
    picker; the free slot picked is sent as `picked_slot` with the feed its tile
    showed (`expected_feed`), and the Yes to the server's printing question sends
    it back (Group 40.0e), so it lands where the question said. It used to post
    the box with no slot, a slot chosen unseen."""
    from test_slot_picker_e2e import ROWS as PICKER_ROWS, build_model
    model = build_model(BOX, spool=999401)
    assert model["recommended"]["slot"] == "3", model["recommended"]      # FCCX-3: free, empty
    ask = {"status": "requires_confirm", "confirm_type": "active_print",
           "active_print": {"toolhead": "FCCX-3", "printer_name": PRINTER, "state": "PRINTING"},
           "active_prints": [{"toolhead": "FCCX-3", "printer_name": PRINTER, "state": "PRINTING",
                              "role": "feeds", "spools": [999401]}],
           "fed_heads": [], "can_store": False, "target_slot": "3", "slot_picked": True, "feed": "FCCX-3",
           "msg": f"{PRINTER} is PRINTING. {BOX} slot 3 feeds FCCX-3, so this also loads #999401 "
                  f"onto FCCX-3. Continue?"}
    be = FakeBackend(page, manage_contents=lambda b: (
        {"status": "success", "failures": {}} if b.get("confirmed_toolheads") else ask),
        extra_locations=[r for r in PICKER_ROWS], placement={BOX: model})
    _boot(page, base_url, reset_dom_state_js)
    _force_to(page, BOX)
    page.wait_for_selector("#fcc-slot-picker [data-sp-state='ready']", timeout=10_000)
    page.keyboard.press("Enter")                       # the ⭐: slot 3
    page.wait_for_selector("#fcc-active-print-confirm-overlay .fcc-apc-yes", state="visible", timeout=5_000)
    page.click("#fcc-active-print-confirm-overlay .fcc-apc-yes")
    _until(page, lambda: len(be.bodies("/api/manage_contents")) >= 2, 5_000, "Yes sent no retry")
    first, retry = be.bodies("/api/manage_contents")[:2]
    assert first["picked_slot"] == "3" and first["expected_feed"] == "FCCX-3" and "slot" not in first, first
    assert first["location"] == BOX and first["origin"] == "manual_override", first
    assert retry["picked_slot"] == "3" and "slot" not in retry, retry
    assert retry["confirmed_toolheads"] == ["FCCX-3"], retry
    _toast(page, "the confirmed override raised no success toast", type_="success",
           contains=(f"#999401 → {BOX} slot 3",))


@pytest.mark.usefixtures("require_server")
def test_force_location_into_a_printer_opens_the_printer_picker(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Group 40.5 (Derek's D3): Force Location onto a Printer row that isn't its
    own toolhead (the XL, the INDX) opens the Printer picker: a head, then (for a
    spool from no box) which box slot it came from, the one free slot
    pre-selected. It used to file the spool on the printer row itself (refused
    since 40.0a)."""
    from test_slot_picker_e2e import ROWS as PICKER_ROWS, build_model
    model = build_model("FCCX", spool=999401)
    be = FakeBackend(page, manage_contents=lambda b: {"status": "success", "failures": {},
                                                      "recorded_source": "FCC-TEST-BOX:3"},
                     extra_locations=[r for r in PICKER_ROWS], placement={"FCCX": model})
    _boot(page, base_url, reset_dom_state_js)
    _force_to(page, "FCCX")
    page.wait_for_selector("#fcc-slot-picker [data-sp-state='ready']", timeout=10_000)
    page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-head='FCCX-3']").click()
    page.wait_for_selector("#fcc-record-source .fcc-rs-panel", timeout=5_000)
    assert "Record #999401 as coming from" in page.text_content("#fcc-record-source .fcc-rs-panel")
    page.keyboard.press("Enter")                       # the one free feed slot is pre-selected
    _until(page, lambda: be.bodies("/api/manage_contents"), 5_000, "the head pick sent nothing")
    body = be.bodies("/api/manage_contents")[0]
    assert body["location"] == "FCCX-3" and body["record_source"] == {"box": "FCC-TEST-BOX", "slot": "3"}, body
    _toast(page, "the head pick raised no success toast", type_="success",
           contains=("#999401 → FCCX-3", "recorded as from FCC-TEST-BOX slot 3"))


@pytest.mark.usefixtures("require_server")
def test_force_location_cancelled_sends_nothing_more(
        page: Page, base_url: str, reset_dom_state_js: str):
    be = FakeBackend(page, manage_contents=lambda b: _FORCE_ASK, extra_locations=[SHELF_ROW])
    _boot(page, base_url, reset_dom_state_js)
    _force_to(page, SHELF)
    page.wait_for_selector("#fcc-active-print-confirm-overlay .fcc-apc-no", state="visible", timeout=5_000)
    page.click("#fcc-active-print-confirm-overlay .fcc-apc-no")
    page.wait_for_timeout(600)
    assert len(be.bodies("/api/manage_contents")) == 1, be.bodies("/api/manage_contents")
    assert page.evaluate("() => !document.getElementById('fcc-active-print-confirm-overlay')")


@pytest.mark.usefixtures("require_server")
def test_force_unassign_asks_on_an_active_print_then_retries_with_the_flag(
        page: Page, base_url: str, reset_dom_state_js: str):
    """The force_unassign answer has its own shape (require_confirm +
    confirm_type) and its route keeps the boolean."""
    ask = {"success": False, "require_confirm": True, "confirm_type": "active_print",
           "active_print": {"toolhead": TH, "printer_name": PRINTER, "state": "PRINTING"},
           "msg": f"{PRINTER} is PRINTING — force-unassigning from this toolhead will disrupt the print."}
    be = FakeBackend(page, manage_contents=lambda b: {"success": True} if b.get("confirm_active_print") else ask,
                     extra_locations=[BOX_ROW])
    _boot(page, base_url, reset_dom_state_js)
    page.evaluate("(sid) => window.promptEditLocation(sid, 'Unassigned')", 999401)
    item = ".swal-loc-item[data-id='']"
    page.wait_for_selector(item, state="attached", timeout=10_000)
    page.dispatch_event(item, "dblclick")
    page.wait_for_selector("#fcc-active-print-confirm-overlay .fcc-apc-yes", state="visible", timeout=5_000)
    page.click("#fcc-active-print-confirm-overlay .fcc-apc-yes")
    _until(page, lambda: len(be.bodies("/api/manage_contents")) >= 2, 5_000, "Yes sent no retry")
    first, second = be.bodies("/api/manage_contents")[:2]
    assert first["action"] == "force_unassign" and first["confirm_active_print"] is False, first
    assert second["confirm_active_print"] is True, second


# ---------------------------------------------------------------------------
# (h) The Return overlay never offers what the backend would refuse
# ---------------------------------------------------------------------------

_GHOST = {"id": 999501, "display": "FCC ghost #999501", "is_ghost": True,
          "location": BOX, "slot": "3", "deployed_to": "FCC-TEST-TH2"}
_DIRECT_A = {"id": 999511, "display": "FCC Test #999511", "location": TH, "slot": ""}
_DIRECT_B = {"id": 999512, "display": "FCC Test #999512", "location": TH, "slot": ""}
# Group 40.6: the server's dry run decides what a Return would do; these are
# its answers for each head (the route's own tests pin them).
_NO_SPOOL = (404, {"action": "return_no_spool", "toolhead": TH, "candidates": [TH]})
RETURN_REFUSED = {
    "empty": ([], _NO_SPOOL, f"Nothing to return on {TH}"),
    "ghost_only": ([_GHOST], _NO_SPOOL, f"Nothing to return on {TH}"),
    "two_direct": ([_DIRECT_A, _DIRECT_B],
                   (409, {"action": "return_ambiguous", "toolhead": TH, "active_toolhead": TH, "requested": TH,
                          "spools": [_DIRECT_A["id"], _DIRECT_B["id"]],
                          "error": f"{TH} holds 2 spools — eject the wrong one first"}),
                   f"{TH} holds 2 spools"),
}


def _returns(be: FakeBackend) -> list[dict]:
    """The Return requests themselves: every POST but the dry run (Group 40.6)."""
    return [b for b in be.bodies("/api/quickswap/return") if not b.get("dry_run")]


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("case", list(RETURN_REFUSED))
def test_return_overlay_offers_nothing_the_backend_would_refuse(
        page: Page, base_url: str, reset_dom_state_js: str, case: str):
    """Return acts only on DIRECT residents and refuses 0 or 2+ (R2-03): the
    overlay must be the no-op one, and its Yes must send nothing.
    FAILS on HEAD for all three: empty -> previewed the first bound slot;
    ghost_only -> previewed the ghost's box; two_direct -> previewed one spool.
    Each offered a real "Return the spool on FCC-TEST-TH?" confirm.
    Group 40.6 (deliberate): the server's dry run now says so (its answer is
    stubbed per case), and the Yes sends no Return after it."""
    items, answer, title = RETURN_REFUSED[case]
    be = FakeBackend(page, contents={TH: items}, dryer_slots=BINDINGS,
                     responders={"/api/quickswap/return": lambda b: answer})
    _boot(page, base_url, reset_dom_state_js)

    page.evaluate(OPEN_RETURN_JS, TH)
    ov = _wait_overlay(page, "the Return overlay never opened")
    assert ov["title"] == title, ov
    if case == "two_direct":
        assert "eject the wrong one first" in ov["body"], ov

    page.click("#fcc-quickswap-yes")
    page.wait_for_timeout(500)
    assert be.bodies("/api/quickswap/return") == [{"toolhead": TH, "dry_run": True}], be.posts
    assert page.evaluate("!document.getElementById('fcc-quickswap-confirm-overlay')"), "the no-op overlay did not close"


_RETURN_RESIDENT = {"id": 999531, "display": "FCC Test #999531", "location": TH, "slot": ""}


def _ret_plan(**kw) -> dict:
    """The server's dry-run answer (Group 40.6): a one-tap plan into BOX slot 3,
    the spool's recorded source, unless `kw` says otherwise."""
    plan = {"action": "return_plan", "toolhead": TH, "active_toolhead": TH, "requested": TH,
            "spool": 999521, "display": "FCC Test PLA #999521", "box": BOX, "slot": "3",
            "source": "physical_source", "needs_choice": False, "note": "",
            "occupancy": {"after": 1, "max": 4}, "options": None, "recommended": None}
    plan.update(kw)
    return plan


def _ret_responder(plan: dict, done):
    """POST /api/quickswap/return: the dry run answers `plan`; every Return
    answers `done` ((status, payload), or a callable of the body)."""
    def respond(body):
        if body.get("dry_run"):
            return 200, plan
        return done(body) if callable(done) else done
    return respond


OPEN_TAP_JS = """([box, slot, th]) => {
    const btn = document.createElement('button');
    btn.dataset.box = box; btn.dataset.slot = slot; btn.dataset.toolhead = th;
    btn.dataset.spoolLabel = 'FCC Test spool';
    window.quickSwapTap(btn);
}"""


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("status,payload,expect", [
    (409, {"action": "return_failed", "error": REJECT}, f"Return failed: {REJECT}"),
    (409, {"action": "return_ambiguous", "error": f"{TH} holds 2 spools — eject the wrong one first"},
     "eject the wrong one first"),
    (502, "<html><body>502 Bad Gateway</body></html>", "server answered 502"),
], ids=["return_failed", "return_ambiguous", "non_json_502"])
def test_return_failures_raise_a_7s_error_toast(
        page: Page, base_url: str, reset_dom_state_js: str, status, payload, expect):
    """Move-pipeline follow-ups item 6 / Group 39.8: no test drove these toasts.
    The non-JSON case FAILS on HEAD: r.json() threw and the catch toasted
    "Return — network error" for a server that did answer. (Group 40.6: the
    dry run answers a plan first; the Return itself fails.)"""
    plan = _ret_plan(spool=_RETURN_RESIDENT["id"], display=_RETURN_RESIDENT["display"])
    be = FakeBackend(page, contents={TH: [_RETURN_RESIDENT]}, dryer_slots=BINDINGS,
                     responders={"/api/quickswap/return": _ret_responder(plan, (status, payload))})
    _boot(page, base_url, reset_dom_state_js)
    page.evaluate(OPEN_RETURN_JS, TH)
    _wait_overlay(page, "the Return overlay never opened", title_contains="Return the spool on")
    page.click("#fcc-quickswap-yes")
    _until(page, lambda: _returns(be), 5_000, "Yes sent no Return")
    err = _toast(page, f"no error toast for {payload!r}", type_="error", contains=(expect,))
    assert err["duration"] and err["duration"] >= 7000, err


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("status,payload,expect", [
    (409, {"action": "quickswap_failed", "error": REJECT}, f"Quick-swap failed: {REJECT}"),
    (502, "<html><body>502 Bad Gateway</body></html>", "server answered 502"),
], ids=["quickswap_failed", "non_json_502"])
def test_quickswap_failures_raise_a_7s_error_toast(
        page: Page, base_url: str, reset_dom_state_js: str, status, payload, expect):
    be = FakeBackend(page, responders={"/api/quickswap": lambda b: (status, payload)})
    _boot(page, base_url, reset_dom_state_js)
    page.evaluate(OPEN_TAP_JS, [BOX, SLOT, TH])
    _wait_overlay(page, "the Quick-Swap overlay never opened", title_contains="Load ")
    page.click("#fcc-quickswap-yes")
    _until(page, lambda: be.bodies("/api/quickswap"), 5_000, "Yes sent no Quick-Swap")
    err = _toast(page, f"no error toast for {payload!r}", type_="error", contains=(expect,))
    assert err["duration"] and err["duration"] >= 7000, err


# Group 40.6 (deliberate): test_return_overlay_previews_the_spools_recorded_source_box
# is replaced by the tests below. The preview no longer reads the spool and the
# bindings itself (_resolveReturnDestination is gone): the server's dry run says
# where the spool goes, and the overlay names exactly that.

_PICK_SPOOL = {"id": 999599, "display": "FCC Test PLA #999599", "color": "00ff00", "remaining_weight": 700,
               "details": {}, "archived": False, "is_ghost": False, "deployed_to": None}


def _picker_slot(n, spool=None):
    return {"slot": str(n), "spool": spool, "claimants": [spool["id"]] if spool else [], "current": False,
            "free": spool is None, "feeds": None, "would_prompt": False,
            "occupant_state": "stored" if spool else None, "stores_only": False,
            "blocked": f"Holds #{spool['id']}: Return takes a free slot, or No slot" if spool else None}


# What /api/placement_options answers for BOX in return mode: slot 3 holds
# #999599 (greyed out), the others are free, ⭐ slot 2.
PICKER_MODEL = {
    "mode": "return", "location": BOX, "name": "FCC Test Box", "type": "Dryer Box", "spool": 999521,
    "spool_display": "FCC Test PLA #999521", "spool_location": TH, "toolhead": TH, "read_ok": True,
    "read_error": None, "max_slots": 4, "slot_order": "ltr",
    "slots": [_picker_slot(1), _picker_slot(2), _picker_slot(3, _PICK_SPOOL), _picker_slot(4)],
    "unslotted": [], "printers": [], "allow_none": True,
    "recommended": {"kind": "slot", "box": BOX, "slot": "2"}, "recommend_reason": "spare_slot",
    "recommend_text": "a free slot that feeds no toolhead",
}
CHOOSE_PLAN = _ret_plan(slot=None, needs_choice=True, note=f"{BOX} slot 3, where it came from, holds #999599",
                        occupancy={"after": 2, "max": 4}, options=PICKER_MODEL,
                        recommended=PICKER_MODEL["recommended"])


def _ret_done(slot):
    return 200, {"action": "return_done", "moved": 999521, "toolhead": TH, "active_toolhead": TH,
                 "requested": TH, "box": BOX, "slot": slot, "source": "chosen"}


def _wait_picker(page: Page) -> None:
    _js_until(page, "!!document.querySelector('#fcc-slot-picker [data-sp-state=\"ready\"]')", 8_000,
              "the slot picker never opened")


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("source, tag", [
    ("physical_source", "(original source)"),
    ("feed_slot", f"(the only free slot that feeds {TH})"),
], ids=["recorded_slot", "only_free_feed_slot"])
def test_return_preview_names_the_slot_the_server_will_use(
        page: Page, base_url: str, reset_dom_state_js: str, source: str, tag: str):
    """Item D: the confirm names the exact slot from the server's dry run (the
    recorded slot, or the only free slot feeding the head: Derek's answer 6),
    and No sends no Return."""
    plan = _ret_plan(source=source, slot="3")
    be = FakeBackend(page, contents={TH: [_RETURN_RESIDENT]},
                     responders={"/api/quickswap/return": _ret_responder(plan, _ret_done("3"))})
    _boot(page, base_url, reset_dom_state_js)

    page.evaluate(OPEN_RETURN_JS, TH)
    ov = _wait_overlay(page, "the Return overlay never opened", title_contains="Return the spool on")
    assert ov["title"] == f"Return the spool on {TH}?", ov
    assert "FCC Test PLA #999521" in ov["body"], ov
    assert f"Sending back to: {BOX} slot 3 {tag}" in ov["body"], ov
    page.click("#fcc-quickswap-no")
    page.wait_for_timeout(300)
    assert be.bodies("/api/quickswap/return") == [{"toolhead": TH, "dry_run": True}], be.posts


@pytest.mark.usefixtures("require_server")
def test_return_with_no_usable_slot_opens_the_picker_then_names_the_choice(
        page: Page, base_url: str, reset_dom_state_js: str):
    """D5: the recorded slot is taken, so the slot picker (return mode) opens
    BEFORE any confirm; the pick is named on the confirm, and the Return sends
    it with the spool the page showed."""
    be = FakeBackend(page, contents={TH: [_RETURN_RESIDENT]},
                     responders={"/api/quickswap/return": _ret_responder(CHOOSE_PLAN, _ret_done("2"))},
                     gets={"/api/placement_options": lambda q: (200, PICKER_MODEL)})
    _boot(page, base_url, reset_dom_state_js)

    page.evaluate(OPEN_RETURN_JS, TH)
    _wait_picker(page)
    assert page.evaluate("!document.getElementById('fcc-quickswap-confirm-overlay')"), "a confirm opened before the pick"
    assert page.evaluate("document.querySelector('#fcc-slot-picker .fcc-sp-tile[data-sp-slot=\"3\"]')"
                         ".getAttribute('aria-disabled')") == "true"
    page.click('#fcc-slot-picker .fcc-sp-tile[data-sp-slot="2"]')
    ov = _wait_overlay(page, "no confirm after the pick", title_contains="Return the spool on")
    assert f"Sending back to: {BOX} slot 2 (your choice)" in ov["body"], ov
    page.click("#fcc-quickswap-yes")
    _until(page, lambda: _returns(be), 5_000, "Yes sent no Return")
    assert _returns(be) == [{"toolhead": TH, "box": BOX, "slot": "2", "expected_spool": 999521,
                             "confirmed_toolheads": []}], be.posts
    _toast(page, "no success toast", type_="success", contains=(f"↩️ #999521 → {BOX} slot 2",))


@pytest.mark.usefixtures("require_server")
def test_return_with_no_slot_names_the_count_and_never_toasts_null(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Item D: "No slot" in the picker is confirmed as "no slot — FCC-TEST-BOX
    will show 2/4", sends slot "none", and the toast says "(no slot)", never
    "SLOT:null"."""
    be = FakeBackend(page, contents={TH: [_RETURN_RESIDENT]},
                     responders={"/api/quickswap/return": _ret_responder(CHOOSE_PLAN, _ret_done(None))},
                     gets={"/api/placement_options": lambda q: (200, PICKER_MODEL)})
    _boot(page, base_url, reset_dom_state_js)

    page.evaluate(OPEN_RETURN_JS, TH)
    _wait_picker(page)
    page.click('#fcc-slot-picker .fcc-sp-tile[data-sp-kind="none"]')
    ov = _wait_overlay(page, "no confirm after No slot", title_contains="Return the spool on")
    assert f"Sending back to: {BOX} — no slot ({BOX} will show 2/4)" in ov["body"], ov
    page.click("#fcc-quickswap-yes")
    _until(page, lambda: _returns(be), 5_000, "Yes sent no Return")
    assert _returns(be)[0]["slot"] == "none", be.posts
    _toast(page, "no success toast", type_="success", contains=(f"↩️ #999521 → {BOX} (no slot)",))
    assert not [t for t in _toasts(page) if "null" in (t.get("text") or "")], _toasts(page)


PR_ROW = {"LocationID": "FCC-TEST-PR", "Name": PRINTER, "Type": "Printer", "Max Spools": "0",
          "toolheads": [{"location_id": TH, "position": 0}]}
TH_ROW = {"LocationID": TH, "Name": "FCC Test Toolhead", "Type": "Tool Head", "Max Spools": "1"}
_DEPLOYED_CARD = {"id": 999521, "display": "FCC Test PLA #999521", "color": "ff0000", "remaining_weight": 800,
                  "is_ghost": True, "deployed_to": TH, "location": BOX, "slot": "3"}
RENDER_CARD_JS = """([item, box]) => {
    let host = document.getElementById('fcc-test-card');
    if (!host) { host = document.createElement('div'); host.id = 'fcc-test-card'; document.body.appendChild(host); }
    host.innerHTML = window.SpoolCardBuilder.buildCard(item, 'loc_grid', { slotNum: 3, locId: box });
}"""


@pytest.mark.usefixtures("require_server")
def test_the_deployed_cards_return_posts_the_canonical_return_with_its_spool(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Item E: the ↩️ on a DEPLOYED card is the canonical Return for the head
    its spool is on (FCC-TEST-TH, a head of a fake printer): the dry run and the
    Return both name the card's spool (expected_spool), and no manage_contents
    add is posted (it used to post the slot straight back)."""
    plan = _ret_plan()
    be = FakeBackend(page, extra_locations=[PR_ROW, TH_ROW, BOX_ROW],
                     responders={"/api/quickswap/return": _ret_responder(plan, _ret_done("3"))})
    _boot(page, base_url, reset_dom_state_js)
    page.wait_for_function(
        "['FCC-TEST-PR', 'FCC-TEST-BOX'].every(id => state.allLocations.some(l => l.LocationID === id))",
        timeout=15_000)

    page.evaluate(RENDER_CARD_JS, [_DEPLOYED_CARD, BOX])
    page.click("#fcc-test-card .js-btn-pick")
    ov = _wait_overlay(page, "the Return overlay never opened", title_contains="Return the spool on")
    assert f"Sending back to: {BOX} slot 3 (original source)" in ov["body"], ov
    page.click("#fcc-quickswap-yes")
    _until(page, lambda: _returns(be), 5_000, "Yes sent no Return")
    assert be.bodies("/api/quickswap/return") == [
        {"toolhead": TH, "dry_run": True, "expected_spool": 999521},
        {"toolhead": TH, "box": BOX, "slot": "3", "expected_spool": 999521, "confirmed_toolheads": []}], be.posts
    assert not be.bodies("/api/manage_contents"), be.posts
    _toast(page, "no success toast", type_="success", contains=(f"↩️ #999521 → {BOX} slot 3",))


# ---------------------------------------------------------------------------
# (i) Group 39.3: "Checking XL…" whenever FCC waits on a printer
# ---------------------------------------------------------------------------
# Group 38's lever: delay the request in-page, never by sleeping in a route
# handler (that stalls Playwright's sync dispatcher).
DELAY_FETCH_JS = """([prefix, ms]) => {
    const orig = window.fetch;
    window.fetch = (url, opts) => {
        const u = typeof url === 'string' ? url : (url && url.url) || '';
        if (u.startsWith(prefix)) {
            return new Promise(resolve => setTimeout(() => resolve(orig(url, opts)), ms));
        }
        return orig(url, opts);
    };
}"""
PILL = "#fcc-printer-check-pill"


@pytest.mark.usefixtures("require_server")
def test_a_slow_printer_check_shows_the_pill_then_clears_it(
        page: Page, base_url: str, reset_dom_state_js: str):
    """A ~2 s probe used to show nothing new until the overlay mounted. Now a
    pinned pill says so after 300 ms and goes when the answer lands. HEAD
    proof: there is no pill."""
    FakeBackend(page, printer_active=False)
    _boot(page, base_url, reset_dom_state_js)
    page.evaluate(DELAY_FETCH_JS, ["/api/printer_state/", 2_000])
    page.evaluate(OPEN_TAP_JS, [BOX, SLOT, TH])
    page.wait_for_selector(PILL, state="visible", timeout=1_500)
    assert "Checking" in page.text_content(PILL)
    assert page.evaluate(f"() => !document.querySelector('{PILL}').classList.contains('toast-msg')"), (
        "the pill must not be a .toast-msg: Escape dismisses the newest toast")
    _wait_overlay(page, "the Quick-Swap overlay never opened", banner=False)
    _js_until(page, f"!document.querySelector('{PILL}')", 2_000, "the pill outlived the answer")


@pytest.mark.usefixtures("require_server")
def test_a_printer_that_never_answers_is_named_in_the_overlay(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Past the client's 3 s cap the probe gives up: the pill says the printer
    didn't answer, a WARNING is logged, and the overlay says FCC couldn't tell,
    rather than looking like an idle printer. HEAD proof: no note, no WARNING."""
    be = FakeBackend(page, printer_active=False)
    _boot(page, base_url, reset_dom_state_js)
    page.evaluate(DELAY_FETCH_JS, ["/api/printer_state/", 4_500])
    page.evaluate(OPEN_TAP_JS, [BOX, SLOT, TH])
    ov = _wait_overlay(page, "the Quick-Swap overlay never opened", banner=False, timeout_ms=8_000)
    assert "Couldn't reach" in ov["body"], ov
    assert "didn't answer" in (page.text_content(PILL) or ""), "the pill did not say the printer didn't answer"
    _until(page, lambda: [b for b in be.bodies("/api/log_event")
                          if b.get("level") == "WARNING" and "didn't answer" in (b.get("msg") or "")],
           3_000, "the timeout wrote no Activity Log WARNING")


@pytest.mark.usefixtures("require_server")
def test_a_printer_with_no_login_says_so_not_unreachable(
        page: Page, base_url: str, reset_dom_state_js: str):
    """The fix for "no credentials" is entering them, so the overlay says that
    (the route's new reason, Group 39.3)."""
    FakeBackend(page, printer_state=lambda th: {"known": False, "reason": "no_credentials",
                                                "printer_name": PRINTER})
    _boot(page, base_url, reset_dom_state_js)
    page.evaluate(OPEN_TAP_JS, [BOX, SLOT, TH])
    ov = _wait_overlay(page, "the Quick-Swap overlay never opened", banner=False)
    assert f"FCC has no login for {PRINTER}" in ov["body"], ov
    assert "Couldn't reach" not in ov["body"], ov


@pytest.mark.usefixtures("require_server")
def test_a_slot_scan_labels_the_dim_with_the_printer_it_waits_on(
        page: Page, base_url: str, reset_dom_state_js: str):
    """A scan has no button to spin. A slot scan whose slot feeds a head waits
    on that printer server-side, so the dim says which. HEAD proof: a bare dim."""
    FakeBackend(page, identify=lambda b: DONE)
    _boot(page, base_url, reset_dom_state_js)
    page.evaluate(DELAY_FETCH_JS, ["/api/identify_scan", 2_000])
    # One task: inject the map/binding and scan, so no heartbeat refresh lands between.
    page.evaluate("""([box, slot, th, printer]) => {
        state.printerMap = { [printer]: [{ location_id: th, position: 0 }] };
        state.allLocations = (state.allLocations || []).filter(l => l.LocationID !== box)
            .concat([{ LocationID: box, Type: 'Dryer Box', 'Max Spools': '4',
                       extra: { slot_targets: { [slot]: th } } }]);
        processScan(`LOC:${box}:SLOT:${slot}`, 'barcode');
    }""", [BOX, SLOT, TH, PRINTER])
    page.wait_for_selector("#processing-overlay .fcc-processing-label", state="visible", timeout=1_500)
    assert f"Checking {PRINTER}" in page.text_content("#processing-overlay .fcc-processing-label")
    _js_until(page, "!document.querySelector('#processing-overlay .fcc-processing-label')"
                    " || document.getElementById('processing-overlay').style.display === 'none'",
              5_000, "the dim's label outlived the answer")
