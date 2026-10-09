"""A confirm raised from inside a confirm's own callback must actually SHOW, and
a CMD:CONFIRM scan must never fire a callback whose dialog is not on screen.

Derek, 2026-09-12 (bulk-move active-print testing report): ejecting a spool off a
printing toolhead "did nothing". Proven root cause: confirmAction() starts
Bootstrap's hide fade on #confirmModal and runs the eject callback in the same
tick. When /api/manage_contents answers require_confirm (the active-print
re-prompt, or the plain "true unassign" prompt with no print running) before
that fade ends, doEject calls requestConfirmation -> show() on the SAME
still-transitioning instance, and Bootstrap 5.3 ignores it by design. No dialog,
no toast, no request — and a still-armed state.pendingConfirm that a later
CMD:CONFIRM scan fired with nothing on screen. Two more routes orphan that
callback with no race at all: a backdrop/Escape dismissal (pendingConfirm is
deliberately kept, de390a0) and a stale CMD:CONFIRM:<sid> QR.

The 2026-09-12 frontend review (FE-1..FE-6) added: a fading gating dialog takes
no clicks (global.css), the "Confirm scan ignored" toast says WHY and stays
silent when nothing was armed, "on screen" hit-tests the dialog (so a confirm
covered by a mountOverlay panel refuses a scan), CMD:CLEAR does nothing but
inform during a bulk move, a stale CMD:CONFIRM:<sid> is refused client-side,
and the safety/action dialogs are pinned on the same queue as the confirm.

HERMETIC AGAINST DEV DATA: every non-GET request is fulfilled synthetically by a
context route and recorded; GETs are read-only and pass through (GET
/api/locations can be given extra fake rows). Spool and location ids are fake.
The fade of all three gating dialogs is widened to 1 s so the race is
deterministic regardless of host load (the real window is ~150 ms).

Eject is driven with a non-'Scan' loc on purpose: ejectSpool(id, 'Scan') skips
the first confirm, so nothing is mid-hide and it would pass on unfixed code.

Playwright trap (see test_scan_path_integrity.py): a JS function serializes to
Python None, identical to null. Check callbacks with `typeof`, never the value.
"""
from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

ACTIVE = {
    "success": False, "require_confirm": True, "confirm_type": "active_print",
    "active_print": {"printer_name": "XL", "state": "PRINTING", "toolhead": "FCC-TEST-TH"},
    "msg": "XL is PRINTING - ejecting from this toolhead will disrupt the print.",
}
UNASSIGN = {"success": False, "require_confirm": True,
            "msg": "True Unassign spool #990001? It is currently floating in a room."}
OK = {"success": True}

SID = 990001            # fake: every manage_contents POST is answered synthetically
LOC = "FCC-TEST-TH"     # fake, and deliberately not 'Scan'
YES = "#confirmModal .btn-success"

IGNORED = "Confirm scan ignored"
NOT_YET = "the dialog isn't on screen yet"
DISMISSED = "that confirmation was dismissed"
STALE_QR = "That confirm QR belongs to a dialog that has closed"

# Bootstrap reads the computed duration for its transition fallback timer, so
# the hide genuinely lasts ~1 s (shown.bs.modal is keyed to the dialog's own
# .3s transform, so the fade-IN timing is unchanged).
WIDE_FADE_CSS = ("#confirmModal.fade, #safetyModal.fade, #actionModal.fade"
                 " { transition: opacity 1s linear !important; }")

# The three gating dialogs share one lifecycle (_showGatingModal / closeModal).
# `yes` is each dialog's primary click target (templates/components/modals_core.html
# and promptAction's generated cards).
DIALOGS = {
    "confirm": {"modal": "confirmModal", "yes": "#confirmModal .btn-success"},
    "safety": {"modal": "safetyModal", "yes": "#safetyModal .btn-danger"},
    "action": {"modal": "actionModal", "yes": "#action-buttons .modal-action-card"},
}

# Installed before any page script, so its capture listeners record every
# gating-modal event in dispatch order, and every toast as it is added.
RECORDER_JS = """
(() => {
  window.__ev = [];
  window.__toasts = [];
  const GATING = ['confirmModal', 'safetyModal', 'actionModal'];
  ['show', 'shown', 'hide', 'hidden'].forEach(k => document.addEventListener(k + '.bs.modal', ev => {
    const id = ev.target && ev.target.id;
    if (!GATING.includes(id)) return;
    const m = document.getElementById('confirm-msg');
    window.__ev.push({ k, id, t: performance.now(), msg: m ? m.textContent : null });
  }, true));
  new MutationObserver(muts => muts.forEach(mu => mu.addedNodes.forEach(n => {
    if (n.nodeType === 1 && n.classList.contains('toast-msg')) window.__toasts.push(n.textContent);
  }))).observe(document, { childList: true, subtree: true });
})();
"""

# Drive any of the three dialogs the way FCC does. __yes runs exactly the code
# the dialog's primary button runs.
DIALOG_HELPERS_JS = """() => {
    window.__ran = [];
    window.__open = (kind, text, tag, cb) => {
        const run = cb || (() => window.__ran.push(tag));
        if (kind === 'confirm') return requestConfirmation(text, run);
        if (kind === 'safety') return promptSafety(text, run);
        return promptAction(text, 'probe body', [{ label: 'Go', action: run }]);
    };
    window.__yes = (kind) => {
        if (kind === 'confirm') return confirmAction(true);
        if (kind === 'safety') return confirmSafety(true);
        closeModal('actionModal'); state.modalCallbacks[0]();
    };
    window.__text = (kind) => document.getElementById(
        kind === 'confirm' ? 'confirm-msg' : kind === 'safety' ? 'safety-msg' : 'action-title').textContent;
    window.__armed = (kind) => kind === 'confirm' ? typeof state.pendingConfirm
        : kind === 'safety' ? typeof state.pendingSafety
        : typeof (state.modalCallbacks || [])[0];
}"""

SNAPSHOT_JS = """() => ({
  confirmShown: document.getElementById('confirmModal').classList.contains('show'),
  msg: document.getElementById('confirm-msg').textContent,
  activeModal: state.activeModal,
  pendingConfirm: typeof state.pendingConfirm,
  events: window.__ev.map(e => e.id + ':' + e.k),
  toasts: window.__toasts.slice(-4),
})"""

DIALOG_SNAPSHOT_JS = """([kind, modalId]) => ({
  shown: document.getElementById(modalId).classList.contains('show'),
  text: window.__text(kind),
  activeModal: state.activeModal,
  armed: window.__armed(kind),
  events: window.__ev.filter(e => e.id === modalId).map(e => e.k),
  ran: window.__ran.slice(),
})"""

# Rows the manage-view refresh test needs in state.allLocations.
FAKE_MANAGE_ROWS = [
    {"LocationID": "FCC-TEST-TH", "Name": "FCC Test Toolhead", "Type": "Tool Head", "Max Spools": "1"},
    {"LocationID": "FCC-TEST-BOX", "Name": "FCC Test Box", "Type": "Dryer Box", "Max Spools": "4"},
]


class FakeBackend:
    """Fulfils every non-GET request synthetically and records it."""

    def __init__(self, page: Page, manage_contents=lambda body: OK, extra_locations=()):
        self.posts: list[tuple[str, dict]] = []
        self.get_contents_ids: list[str] = []
        self._manage_contents = manage_contents
        self.extra_locations = list(extra_locations)
        page.context.route("**/*", self._handle)

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
        if req.method in ("GET", "HEAD", "OPTIONS"):
            if parts.path == "/api/get_contents":
                loc_id = (parse_qs(parts.query).get("id") or [""])[0]
                self.get_contents_ids.append(loc_id)
                if loc_id.startswith("FCC-TEST-"):
                    route.fulfill(status=200, content_type="application/json", body="[]")
                    return
            if req.method == "GET" and self.extra_locations and parts.path in (
                    "/api/locations", "/api/dashboard_pulse"):
                self._fulfil_with_extra_rows(route, None if parts.path == "/api/locations" else "locations")
                return
            route.continue_()
            return
        try:
            body = json.loads(req.post_data or "{}")
        except (TypeError, ValueError):
            body = {}
        if not isinstance(body, dict):
            body = {"_raw": body}
        self.posts.append((parts.path, body))
        if parts.path == "/api/manage_contents":
            payload = self._manage_contents(body)
        elif parts.path == "/api/identify_scan":
            # What logic.resolve_scan returns for ANY text containing CMD:CONFIRM.
            payload = {"type": "command", "cmd": "confirm"}
        else:
            payload = OK
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

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
        route.fulfill(status=resp.status, content_type="application/json", body=json.dumps(data))

    def bodies(self, path: str) -> list[dict]:
        return [b for p, b in self.posts if p == path]

    def ejects(self) -> list[dict]:
        return self.bodies("/api/manage_contents")


@pytest.fixture(autouse=True)
def _drop_routes_in_flight(page: Page):
    """A route callback still running at context close otherwise surfaces its
    TargetClosedError in the NEXT test's setup."""
    yield
    try:
        page.context.unroute_all(behavior="ignoreErrors")
    except PlaywrightError:
        pass


def _boot(page: Page, base_url: str, reset_dom_state_js: str) -> None:
    page.add_init_script(RECORDER_JS)
    page.goto(base_url.rstrip("/") + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "typeof state !== 'undefined' && typeof modals !== 'undefined' && !!modals.confirmModal"
        " && !!modals.safetyModal && !!modals.actionModal"
        " && typeof window.ejectSpool === 'function' && typeof window.processScan === 'function'",
        timeout=20_000,
    )
    page.evaluate(reset_dom_state_js)
    page.add_style_tag(content=WIDE_FADE_CSS)
    page.evaluate(DIALOG_HELPERS_JS)


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


def _count(page: Page, kind: str, modal: str = "confirmModal") -> int:
    return page.evaluate(
        "([m, k]) => window.__ev.filter(e => e.id === m && e.k === k).length", [modal, kind])


def _wait_shown(page: Page, n: int, what: str, timeout_ms: int = 5_000, modal: str = "confirmModal") -> None:
    _js_until(page, f"window.__ev.filter(e => e.id === {json.dumps(modal)} && e.k === 'shown').length"
              f" >= {n}", timeout_ms, what)


def _dialog_snapshot(page: Page, kind: str) -> dict:
    return page.evaluate(DIALOG_SNAPSHOT_JS, [kind, DIALOGS[kind]["modal"]])


def _toast_until(page: Page, text: str, what: str, timeout_ms: int = 3_000) -> None:
    _js_until(page, f"window.__toasts.some(t => t.includes({json.dumps(text)}))", timeout_ms, what)


def _toasts_with(page: Page, text: str) -> list[str]:
    return [t for t in page.evaluate("window.__toasts") if text in t]


def _confirm_visible_with(page: Page, text: str, what: str) -> None:
    _js_until(page, "document.getElementById('confirmModal').classList.contains('show')"
              f" && document.getElementById('confirm-msg').textContent.includes({json.dumps(text)})",
              5_000, what)


def _start_eject(page: Page, sid: int = SID, loc: str = LOC) -> None:
    page.evaluate(f"ejectSpool({sid}, {json.dumps(loc)}, false)")
    _wait_shown(page, 1, "the first 'Eject spool?' confirm never showed")
    assert f"#{sid}" in page.text_content("#confirm-msg")


# ---------------------------------------------------------------------------
# The chained re-prompt must become visible
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_active_print_reprompt_after_a_button_eject_is_shown(
        page: Page, base_url: str, reset_dom_state_js: str):
    be = FakeBackend(page, lambda b: OK if b.get("confirm_active_print") else ACTIVE)
    _boot(page, base_url, reset_dom_state_js)

    _start_eject(page)
    page.click(YES)
    # The synthetic backend answers active_print at once, i.e. while the first
    # confirm is still fading out: exactly the window that dropped the dialog.
    _confirm_visible_with(page, "PRINTING",
                          "the active-print re-confirm was silently dropped (show() mid-hide)")
    _wait_shown(page, 2, "the active-print re-confirm never finished showing")
    assert page.evaluate("state.activeModal") == "confirm"
    assert [b["confirm_active_print"] for b in be.ejects()] == [False]

    page.click(YES)
    _until(page, lambda: len(be.ejects()) >= 2, 5_000, "YES on the re-confirm sent no retry")
    retry = be.ejects()[1]
    assert retry["spool_id"] == SID and retry["confirm_active_print"] is True, retry
    _js_until(page, "window.__toasts.includes('Ejected')", 5_000, "no 'Ejected' toast")


@pytest.mark.usefixtures("require_server")
def test_true_unassign_reprompt_with_no_print_running_is_shown(
        page: Page, base_url: str, reset_dom_state_js: str):
    """The drop never needed a print: a spool floating in a room (or a PM/PJ/TST
    box with no saved home) gets the plain REQUIRE_CONFIRM answer, with no
    PrusaLink probe in the way, so it lands inside the fade even faster."""
    be = FakeBackend(page, lambda b: OK if b.get("confirmed") else UNASSIGN)
    _boot(page, base_url, reset_dom_state_js)

    _start_eject(page)
    page.click(YES)
    _confirm_visible_with(page, "True Unassign",
                          "the true-unassign re-confirm was silently dropped (show() mid-hide)")
    _wait_shown(page, 2, "the true-unassign re-confirm never finished showing")

    page.click(YES)
    _until(page, lambda: len(be.ejects()) >= 2, 5_000, "YES on the re-confirm sent no retry")
    retry = be.ejects()[1]
    assert retry["confirmed"] is True and retry["confirm_active_print"] is False, retry
    _js_until(page, "window.__toasts.includes('Ejected')", 5_000, "no 'Ejected' toast")


@pytest.mark.usefixtures("require_server")
def test_three_hop_active_print_then_true_unassign_chain(
        page: Page, base_url: str, reset_dom_state_js: str):
    """A homeless resident of a printing toolhead: the active-print prompt, then
    (with the print override set, so no probe) the true-unassign prompt."""
    def backend(b):
        if b.get("confirmed"):
            return OK
        return UNASSIGN if b.get("confirm_active_print") else ACTIVE

    be = FakeBackend(page, backend)
    _boot(page, base_url, reset_dom_state_js)

    _start_eject(page)
    page.click(YES)
    _confirm_visible_with(page, "PRINTING", "hop 2 (active print) was dropped")
    _wait_shown(page, 2, "hop 2 never finished showing")
    page.click(YES)
    _confirm_visible_with(page, "True Unassign", "hop 3 (true unassign) was dropped")
    _wait_shown(page, 3, "hop 3 never finished showing")
    page.click(YES)

    _until(page, lambda: len(be.ejects()) >= 3, 5_000, "YES on hop 3 sent no retry")
    flags = [(b["confirmed"], b["confirm_active_print"]) for b in be.ejects()]
    assert flags == [(False, False), (False, True), (True, True)], flags
    _js_until(page, "window.__toasts.includes('Ejected')", 5_000, "no 'Ejected' toast")


@pytest.mark.usefixtures("require_server")
def test_double_click_on_yes_never_confirms_the_reprompt_unseen(
        page: Page, base_url: str, reset_dom_state_js: str):
    """FE-1: the second click of a double-click lands on the dialog that is still
    fading out, which by then carries the NEXT prompt's text and callback. It
    used to confirm the active-print override before anyone could read it
    (12/12 runs, HEAD and the first cut of the fix). global.css now makes a
    fading gating dialog's .modal-content inert, so the click falls through to
    the .modal, the re-prompt shows, and only a deliberate click confirms it.
    Real CDP mouse input throughout, so browser hit-testing is what decides."""
    be = FakeBackend(page, lambda b: OK if b.get("confirm_active_print") else ACTIVE)
    _boot(page, base_url, reset_dom_state_js)
    _start_eject(page)

    page.click(YES)
    _js_until(page, "document.getElementById('confirm-msg').textContent.includes('PRINTING')", 3_000,
              "the backend's active-print answer never re-armed the dialog")
    # Where YES is painted NOW: the longer re-prompt text reflows the fading dialog.
    at_second = page.evaluate("""() => {
        const m = document.getElementById('confirmModal');
        const r = m.querySelector('.btn-success').getBoundingClientRect();
        const x = r.left + r.width / 2, y = r.top + r.height / 2;
        const hit = document.elementFromPoint(x, y);
        return { x, y, shown: m.classList.contains('show'), display: getComputedStyle(m).display,
                 opacity: getComputedStyle(m).opacity,
                 hitInContent: !!(hit && hit.closest('#confirmModal .modal-content')) };
    }""")
    assert not at_second["shown"] and at_second["display"] == "block" and float(at_second["opacity"]) > 0, (
        f"precondition: the second click must land on the still-painted, fading-out dialog: {at_second}")
    page.mouse.click(at_second["x"], at_second["y"])

    _wait_shown(page, 2, "the active-print re-prompt never reached shown after a double-click")
    page.wait_for_timeout(300)
    assert len(be.ejects()) == 1, (
        "the second click of a double-click confirmed the active-print override unseen "
        f"(hit test at that click: {at_second}): {be.ejects()}")
    snap = page.evaluate(SNAPSHOT_JS)
    assert snap["confirmShown"] and "PRINTING" in snap["msg"] and snap["activeModal"] == "confirm", snap

    page.click(YES)   # a deliberate click on the fully shown re-prompt
    _until(page, lambda: len(be.ejects()) >= 2, 5_000, "a deliberate click on the shown re-prompt sent nothing")
    assert be.ejects()[1]["confirm_active_print"] is True, be.ejects()
    _js_until(page, "window.__toasts.includes('Ejected')", 5_000, "no 'Ejected' toast")


# ---------------------------------------------------------------------------
# A CONFIRM scan must not fire a callback whose dialog is not on screen
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("when", ["before_release", "after_release"])
def test_confirm_scan_after_a_backdrop_dismissal_fires_nothing(
        page: Page, base_url: str, reset_dom_state_js: str, when: str):
    """before_release: the scan lands inside the 400 ms before the hidden.bs.modal
    release clears activeModal, so it takes the activeModal === 'confirm' route.
    after_release: it goes through /api/identify_scan to the generic
    `res.cmd === 'confirm'` route, with pendingConfirm still armed (de390a0).
    FE-2: the warning says the confirmation was DISMISSED (not merely "no
    dialog") and is written to the Activity Log."""
    be = FakeBackend(page, lambda b: ACTIVE)
    _boot(page, base_url, reset_dom_state_js)
    _start_eject(page)

    if when == "before_release":
        page.evaluate("""() => {
            window.__scanState = null;
            document.getElementById('confirmModal').addEventListener('hidden.bs.modal', () => setTimeout(() => {
                window.__scanState = { activeModal: state.activeModal, pendingConfirm: typeof state.pendingConfirm };
                processScan('CMD:CONFIRM', 'barcode');
            }, 0), { once: true });
        }""")

    page.mouse.click(15, 650)   # on #confirmModal, outside .modal-dialog -> backdrop dismiss
    _js_until(page, "window.__ev.some(e => e.id === 'confirmModal' && e.k === 'hidden')", 5_000,
              "the backdrop click did not dismiss the confirm")

    if when == "before_release":
        _js_until(page, "window.__scanState !== null", 3_000, "the scan hook never ran")
        assert page.evaluate("window.__scanState") == {
            "activeModal": "confirm", "pendingConfirm": "function"}, "precondition"
    else:
        _js_until(page, "state.activeModal === null", 3_000, "the scan gate was never released")
        assert page.evaluate("typeof state.pendingConfirm") == "function", (
            "precondition: a dismissal deliberately leaves the callback armed")
        page.evaluate("processScan('CMD:CONFIRM', 'barcode')")
        _until(page, lambda: be.bodies("/api/identify_scan"), 3_000,
               "the scan never reached identify_scan, so this test would be vacuous")

    page.wait_for_timeout(1_500)
    assert be.ejects() == [], (
        f"a CMD:CONFIRM scan fired the DISMISSED eject with no dialog on screen: {be.ejects()}")
    assert not page.evaluate("document.getElementById('confirmModal').classList.contains('show')")
    _toast_until(page, DISMISSED, "a blocked CONFIRM scan on a dismissed dialog must say it was dismissed")
    assert not _toasts_with(page, NOT_YET), page.evaluate("window.__toasts")
    _until(page, lambda: [b for b in be.bodies("/api/log_event")
                          if b.get("level") == "WARNING" and IGNORED in (b.get("msg") or "")],
           3_000, "the ignored CONFIRM scan wrote no Activity Log WARNING")


@pytest.mark.usefixtures("require_server")
def test_stale_session_scoped_confirm_qr_fires_nothing(
        page: Page, base_url: str, reset_dom_state_js: str):
    """A CMD:CONFIRM:<sid> that routeConfirmScan does not claim belongs to a
    dialog that has closed. Dismissed here the way the inv_loc_mgr Escape ladder
    does: inst.hide(), which leaves pendingConfirm armed.

    CHANGED 2026-09-12 (FE-5): this used to require the stale QR to reach
    /api/identify_scan (where the backend's substring match answers
    cmd:'confirm' and the on-screen guard refused it). inv_cmd.js now refuses
    it client-side, right after routeConfirmScan, so it must NOT reach the
    backend at all, and it says why."""
    be = FakeBackend(page, lambda b: ACTIVE)
    _boot(page, base_url, reset_dom_state_js)
    _start_eject(page)

    page.evaluate("bootstrap.Modal.getInstance(document.getElementById('confirmModal')).hide()")
    _js_until(page, "window.__ev.some(e => e.id === 'confirmModal' && e.k === 'hidden')", 5_000,
              "inst.hide() did not dismiss the confirm")
    _js_until(page, "state.activeModal === null", 3_000, "the scan gate was never released")
    assert page.evaluate("typeof state.pendingConfirm") == "function", "precondition"

    stale = "CMD:CONFIRM:zzstale123"
    assert page.evaluate("(t) => window.routeConfirmScan(t)", stale) is False, "precondition"
    page.evaluate("(t) => processScan(t, 'barcode')", stale)
    _toast_until(page, STALE_QR, "a stale CMD:CONFIRM:<sid> was not refused with the closed-dialog toast")

    page.wait_for_timeout(1_500)
    assert be.ejects() == [], (
        f"a stale CMD:CONFIRM:<sid> fired the dismissed eject: {be.ejects()}")
    assert not [b for b in be.bodies("/api/identify_scan") if b.get("text") == stale], (
        "a stale CMD:CONFIRM:<sid> must be refused before it reaches the backend's substring match")


@pytest.mark.usefixtures("require_server")
def test_stale_session_scoped_confirm_qr_never_answers_a_different_shown_dialog(
        page: Page, base_url: str, reset_dom_state_js: str):
    """FE-5: with 'Eject spool #N?' fully shown, a late scan of some closed
    overlay's CMD:CONFIRM:<sid> used to fall through to the activeModal route,
    where upper.includes('CONFIRM') ran the unrelated eject. A stale
    CMD:CANCEL:<sid> still falls through (cancelling is always safe)."""
    be = FakeBackend(page, lambda b: OK)
    _boot(page, base_url, reset_dom_state_js)
    _start_eject(page)

    stale = "CMD:CONFIRM:zzStale999"
    assert page.evaluate("(t) => window.routeConfirmScan(t)", stale) is False, "precondition"
    # Version-independent on purpose (no isGatingModalOnScreen), so HEAD fails at the eject assertion.
    assert page.evaluate("document.getElementById('confirmModal').classList.contains('show')"
                         " && state.activeModal === 'confirm'"), "precondition: the eject confirm must be fully shown"
    page.evaluate("(t) => processScan(t, 'barcode')", stale)
    _toast_until(page, STALE_QR, "a stale CMD:CONFIRM:<sid> raised no closed-dialog toast")

    page.wait_for_timeout(800)
    assert be.ejects() == [], f"a stale CMD:CONFIRM:<sid> confirmed a DIFFERENT shown dialog: {be.ejects()}"
    snap = page.evaluate(SNAPSHOT_JS)
    assert snap["confirmShown"] and snap["activeModal"] == "confirm" and snap["pendingConfirm"] == "function", snap
    assert not be.bodies("/api/identify_scan"), be.posts
    _until(page, lambda: [b for b in be.bodies("/api/log_event")
                          if b.get("level") == "WARNING" and "Stale confirm QR" in (b.get("msg") or "")],
           3_000, "the refused stale QR wrote no Activity Log WARNING")

    page.evaluate("(t) => processScan(t, 'barcode')", "CMD:CANCEL:zzStale999")
    _js_until(page, "window.__ev.some(e => e.id === 'confirmModal' && e.k === 'hidden')", 5_000,
              "a stale CMD:CANCEL:<sid> no longer cancels the shown dialog")
    assert be.ejects() == []


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("dialog", ["safety", "action"])
def test_scan_into_a_dismissed_safety_or_action_dialog_fires_nothing(
        page: Page, base_url: str, reset_dom_state_js: str, dialog: str):
    """The analogous routes: activeModal === 'safety' (CONFIRM -> confirmSafety)
    and === 'action' (CMD:MODAL:<i> -> modalCallbacks[i]). The scan lands after a
    non-button dismissal but inside the 400 ms before the gate release."""
    FakeBackend(page)
    _boot(page, base_url, reset_dom_state_js)
    modal_id = f"{dialog}Modal"
    scan = "CMD:CONFIRM" if dialog == "safety" else "CMD:MODAL:0"
    opener = ("promptSafety('Nuke probe?', () => window.__ran.push('safety'))" if dialog == "safety"
              else "promptAction('Probe', 'Pick one', [{ label: 'Go', action: () => window.__ran.push('action') }])")
    page.evaluate(f"() => {{ window.__ran = []; {opener}; }}")
    _js_until(page, f"window.__ev.some(e => e.id === '{modal_id}' && e.k === 'shown')", 5_000,
              f"#{modal_id} never showed")

    page.evaluate("""([modalId, scanText]) => {
        window.__scanState = null;
        const el = document.getElementById(modalId);
        el.addEventListener('hidden.bs.modal', () => setTimeout(() => {
            window.__scanState = { activeModal: state.activeModal };
            processScan(scanText, 'barcode');
        }, 0), { once: true });
        bootstrap.Modal.getInstance(el).hide();   // the Escape-ladder / backdrop path
    }""", [modal_id, scan])
    _js_until(page, "window.__scanState !== null", 5_000, f"#{modal_id} never finished hiding")
    assert page.evaluate("window.__scanState") == {"activeModal": dialog}, (
        "precondition: the scan must land before the gate release")

    page.wait_for_timeout(500)
    assert page.evaluate("window.__ran") == [], (
        f"a {scan} scan fired the callback of a DISMISSED {dialog} dialog")
    _toast_until(page, DISMISSED, "a blocked scan into a dismissed dialog must say it was dismissed")


@pytest.mark.usefixtures("require_server")
def test_confirm_scan_while_a_reprompt_is_still_queued_is_ignored(
        page: Page, base_url: str, reset_dom_state_js: str):
    """The routing decision: 'on screen' means shown, not merely armed. A
    re-prompt queued behind a fade-out is armed before anyone can read it, so a
    scanner double-read of the first dialog's YES QR must not confirm the
    active-print override. Once the dialog is up, a deliberate scan works.
    FE-2: the warning must say the dialog is not on screen YET (the old text,
    'no confirmation dialog is on screen', was contradicted half a second later)."""
    be = FakeBackend(page, lambda b: OK if b.get("confirm_active_print") else ACTIVE)
    _boot(page, base_url, reset_dom_state_js)
    _start_eject(page)
    page.click(YES)
    _until(page, lambda: len(be.ejects()) == 1, 3_000, "the first eject POST never went out")
    page.wait_for_timeout(100)

    pre = page.evaluate(SNAPSHOT_JS)
    assert pre["activeModal"] == "confirm" and not pre["confirmShown"] and "PRINTING" in pre["msg"], (
        f"precondition: the re-prompt should be armed but still queued behind the fade: {pre}")
    page.evaluate("processScan('CMD:CONFIRM', 'barcode')")
    page.wait_for_timeout(300)
    assert len(be.ejects()) == 1, (
        f"a CONFIRM scan confirmed the active-print override before its dialog was on screen: {be.ejects()}")
    _toast_until(page, NOT_YET, "the scan ignored while the re-prompt was queued must say it isn't on screen yet")
    assert not _toasts_with(page, DISMISSED), page.evaluate("window.__toasts")

    _wait_shown(page, 2, "the queued re-prompt never showed")
    page.evaluate("processScan('CMD:CONFIRM', 'barcode')")
    _until(page, lambda: len(be.ejects()) == 2, 3_000, "a CONFIRM scan on the visible re-prompt did nothing")
    assert be.ejects()[1]["confirm_active_print"] is True


@pytest.mark.usefixtures("require_server")
def test_a_double_read_after_a_successful_confirm_raises_no_ignored_warning(
        page: Page, base_url: str, reset_dom_state_js: str):
    """FE-2: a scanner double-read of the YES QR. The first read confirms; the
    second finds nothing armed and must stay quiet, as HEAD was. A 7 s 'Confirm
    scan ignored' right after a successful eject invites a blind rescan."""
    be = FakeBackend(page, lambda b: OK)
    _boot(page, base_url, reset_dom_state_js)
    _start_eject(page)

    page.evaluate("() => { processScan('CMD:CONFIRM', 'barcode'); processScan('CMD:CONFIRM', 'barcode'); }")
    _until(page, lambda: be.bodies("/api/identify_scan"), 3_000,
           "the second read never reached identify_scan, so this test would be vacuous")
    _js_until(page, "window.__toasts.includes('Ejected')", 5_000, "the first read did not confirm the eject")
    page.wait_for_timeout(1_500)
    assert len(be.ejects()) == 1, be.ejects()
    assert not _toasts_with(page, IGNORED), (
        f"a double-read after a successful confirm raised a false 'ignored' warning: {page.evaluate('window.__toasts')}")


@pytest.mark.usefixtures("require_server")
def test_confirm_scan_into_a_shown_confirm_covered_by_an_overlay_fires_nothing(
        page: Page, base_url: str, reset_dom_state_js: str):
    """FE-3: a fully shown #confirmModal (z 1100) under a mountOverlay panel
    (z 20000, backdrop) is shown but not visible. isGatingModalOnScreen now
    hit-tests the dialog centre, so a CONFIRM scan refuses it; once the panel
    is gone the same scan works (the guard is not latched)."""
    FakeBackend(page)
    _boot(page, base_url, reset_dom_state_js)
    page.evaluate("() => requestConfirmation('Covered probe?', () => window.__ran.push('covered'))")
    _wait_shown(page, 1, "the confirm never showed")
    # Version-independent on purpose (no isGatingModalOnScreen), so HEAD fails at the scan assertion.
    assert page.evaluate("""() => {
        const r = document.querySelector('#confirmModal .modal-content').getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return !!(hit && hit.closest('#confirmModal'));
    }""") is True, "precondition: uncovered, the shown confirm is hit-testable"

    page.evaluate("""() => { window.__cover = window.mountOverlay({
        id: 'fcc-test-cover-overlay', tier: 'standard', backdrop: true, backdropDismiss: false,
        content: '<div style="background:#222;color:#fff;padding:40px;">FCC TEST PANEL</div>',
    }); }""")
    probe = page.evaluate("""() => {
        const r = document.querySelector('#confirmModal .modal-content').getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return { hitInOverlay: !!(hit && hit.closest('#fcc-test-cover-overlay')),
                 confirmShown: document.getElementById('confirmModal').classList.contains('show'),
                 activeModal: state.activeModal };
    }""")
    assert probe == {"hitInOverlay": True, "confirmShown": True, "activeModal": "confirm"}, (
        f"precondition: the shown confirm must be covered by the overlay: {probe}")

    page.evaluate("processScan('CMD:CONFIRM', 'barcode')")
    page.wait_for_timeout(500)
    assert page.evaluate("window.__ran") == [], "a CONFIRM scan fired a confirm hidden behind a mountOverlay panel"
    assert page.evaluate("document.getElementById('confirmModal').classList.contains('show')"
                         " && state.activeModal === 'confirm'"), page.evaluate(SNAPSHOT_JS)
    _toast_until(page, IGNORED, "the refused scan into a covered confirm raised no toast")

    page.evaluate("() => window.__cover.cleanup()")
    page.evaluate("processScan('CMD:CONFIRM', 'barcode')")
    _js_until(page, "window.__ran.length > 0", 3_000, "once uncovered, a CONFIRM scan did nothing")
    assert page.evaluate("window.__ran") == ["covered"]


@pytest.mark.usefixtures("require_server")
def test_clear_scan_during_a_bulk_move_opens_no_confirm(
        page: Page, base_url: str, reset_dom_state_js: str):
    """FE-3: the client-side CMD:CLEAR route runs before identify_scan. During a
    bulk move with a non-empty buffer it opened 'Clear entire Buffer?' BEHIND the
    bulk panel, where activeModal='confirm' swallowed every later scan. The
    buffer and the flag are set in the same task as the scan, so no heartbeat
    can change them in between."""
    be = FakeBackend(page)
    _boot(page, base_url, reset_dom_state_js)
    page.evaluate("""() => {
        state.heldSpools = [{ id: 990071, display: 'FCC-TEST spool', color: '#fff' }];
        state.bulkMoveActive = true;
        processScan('CMD:CLEAR', 'barcode');
        window.__afterClear = { activeModal: state.activeModal, held: state.heldSpools.length };
    }""")
    page.wait_for_timeout(700)
    assert page.evaluate("window.__afterClear") == {"activeModal": None, "held": 1}
    snap = page.evaluate(SNAPSHOT_JS)
    assert not snap["confirmShown"] and snap["activeModal"] is None and _count(page, "show") == 0, (
        f"CMD:CLEAR during a bulk move opened a confirm: {snap}")
    assert not be.bodies("/api/identify_scan"), be.posts
    _toast_until(page, "kept during a bulk move", "CMD:CLEAR during a bulk move gave no explanation")

    # Control: outside a bulk move the same scan does prompt, so the above is not vacuous.
    page.evaluate("""() => {
        state.bulkMoveActive = false;
        state.heldSpools = [{ id: 990071, display: 'FCC-TEST spool', color: '#fff' }];
        processScan('CMD:CLEAR', 'barcode');
    }""")
    _confirm_visible_with(page, "Clear entire Buffer?", "control: CMD:CLEAR outside a bulk move should prompt")
    page.evaluate("confirmAction(false)")   # cancel: never clear anything


@pytest.mark.usefixtures("require_server")
def test_cancel_scan_while_a_reprompt_is_queued_cancels_it(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Guards the queue's cancellation: CANCEL stays unguarded, and closing a
    prompt that is still queued must stop it from appearing later. (Unfixed
    code also passes: there the prompt was dropped outright.)"""
    be = FakeBackend(page, lambda b: ACTIVE)
    _boot(page, base_url, reset_dom_state_js)
    _start_eject(page)
    page.click(YES)
    _until(page, lambda: len(be.ejects()) == 1, 3_000, "the first eject POST never went out")
    page.wait_for_timeout(100)

    page.evaluate("processScan('CMD:CANCEL', 'barcode')")
    _js_until(page, "window.__ev.some(e => e.id === 'confirmModal' && e.k === 'hidden')", 5_000,
              "the first confirm never finished hiding")
    page.wait_for_timeout(1_200)
    snap = page.evaluate(SNAPSHOT_JS)
    assert not snap["confirmShown"] and _count(page, "show") == 1, (
        f"a cancelled queued prompt came back: {snap}")
    assert snap["activeModal"] is None and snap["pendingConfirm"] == "object", snap
    assert len(be.ejects()) == 1


# ---------------------------------------------------------------------------
# Queue mechanics, pinned in-page (no network involved)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_queued_show_runs_before_document_hidden_listeners_and_keeps_the_scan_gate(
        page: Page, base_url: str, reset_dom_state_js: str):
    """The queued show is an ELEMENT-level hidden.bs.modal listener, so it must
    dispatch before any DOCUMENT-level one, including inv_core's scan-gate
    release. Pinned rather than assumed, and the gate must survive the
    release's 400 ms timer."""
    FakeBackend(page)
    _boot(page, base_url, reset_dom_state_js)
    page.evaluate("""() => {
        window.__atDocHidden = [];
        // Added after inv_core's own document-level hidden.bs.modal listener.
        document.addEventListener('hidden.bs.modal', (ev) => {
            if (ev.target.id !== 'confirmModal') return;
            window.__atDocHidden.push({
                showsSoFar: window.__ev.filter(e => e.id === 'confirmModal' && e.k === 'show').length,
                activeModal: state.activeModal,
            });
        });
        requestConfirmation('first', () => setTimeout(() => requestConfirmation('second', () => {}), 30));
    }""")
    _wait_shown(page, 1, "the first confirm never showed")
    page.click(YES)

    _js_until(page, "window.__atDocHidden.length >= 1", 5_000, "the first confirm never hid")
    at = page.evaluate("window.__atDocHidden[0]")
    assert at == {"showsSoFar": 2, "activeModal": "confirm"}, (
        f"the queued show must dispatch BEFORE document-level hidden.bs.modal listeners: {at}")
    page.wait_for_timeout(900)
    snap = page.evaluate(SNAPSHOT_JS)
    assert snap["activeModal"] == "confirm" and snap["confirmShown"] and snap["msg"] == "second", (
        f"the scan-gate release tore down the re-armed prompt: {snap}")


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("kind", list(DIALOGS))
def test_prompts_queued_behind_a_fade_out_show_once_with_the_newest_text(
        page: Page, base_url: str, reset_dom_state_js: str, kind: str):
    """FE-4: parametrized over confirm / safety / action. All three go through
    _showGatingModal, and HEAD dropped the safety and action chains outright."""
    FakeBackend(page)
    _boot(page, base_url, reset_dom_state_js)
    d = DIALOGS[kind]
    page.evaluate("""(kind) => __open(kind, 'first', 'first', () => {
        // Both arrive while 'first' is still fading out.
        setTimeout(() => __open(kind, 'second', 'second'), 30);
        setTimeout(() => __open(kind, 'third', 'third'), 60);
    })""", kind)
    _wait_shown(page, 1, f"the first {kind} dialog never showed", modal=d["modal"])
    page.click(d["yes"])
    _wait_shown(page, 2, f"the queued {kind} prompt never showed", modal=d["modal"])
    page.wait_for_timeout(600)   # past the 400 ms hidden.bs.modal scan-gate release
    snap = _dialog_snapshot(page, kind)
    assert snap["shown"] and snap["activeModal"] == kind and snap["text"] == "third", (
        f"the queued {kind} prompt lost its gate or its newest text: {snap}")
    page.wait_for_timeout(600)   # room for a duplicate queued show to sneak in
    assert _count(page, "show", d["modal"]) == 2, _dialog_snapshot(page, kind)

    page.click(d["yes"])
    _js_until(page, "window.__ran.length > 0", 3_000, f"the queued {kind} prompt's button ran nothing")
    page.wait_for_timeout(300)
    assert page.evaluate("window.__ran") == ["third"]


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("kind", list(DIALOGS))
def test_a_callback_that_reprompts_synchronously_keeps_its_new_callback(
        page: Page, base_url: str, reset_dom_state_js: str, kind: str):
    """confirmAction/confirmSafety used to null the pending callback AFTER running
    it, wiping a callback that the callback itself had just armed. FE-4:
    parametrized over confirm / safety / action (promptAction's generation bump
    is what keeps activeModal='action' past the release)."""
    FakeBackend(page)
    _boot(page, base_url, reset_dom_state_js)
    d = DIALOGS[kind]
    page.evaluate("(kind) => __open(kind, 'first', 'first', () => __open(kind, 'second', 'second'))", kind)
    _wait_shown(page, 1, f"the first {kind} dialog never showed", modal=d["modal"])
    page.click(d["yes"])
    _js_until(page, f"document.getElementById({json.dumps(d['modal'])}).classList.contains('show')"
              f" && window.__text({json.dumps(kind)}) === 'second'", 5_000,
              f"a synchronous {kind} re-prompt was dropped")
    _wait_shown(page, 2, f"the synchronous {kind} re-prompt never finished showing", modal=d["modal"])
    page.wait_for_timeout(600)
    snap = _dialog_snapshot(page, kind)
    assert snap["shown"] and snap["activeModal"] == kind and snap["armed"] == "function", snap

    page.click(d["yes"])
    _js_until(page, "window.__ran.length > 0", 3_000, f"the {kind} re-prompt's button ran nothing")
    assert page.evaluate("window.__ran") == ["second"]


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("kind", list(DIALOGS))
def test_closing_a_confirm_during_its_fade_in_really_closes_it(
        page: Page, base_url: str, reset_dom_state_js: str, kind: str):
    """The symmetric quirk: Bootstrap ignores hide() during the ~450 ms fade-in,
    which left a dialog on screen whose callback had already run. FE-4:
    parametrized over confirm / safety / action."""
    FakeBackend(page)
    _boot(page, base_url, reset_dom_state_js)
    modal = DIALOGS[kind]["modal"]
    page.evaluate("""([kind, modalId]) => new Promise(res => {
        __open(kind, 'probe', 'probe');
        setTimeout(() => {
            window.__eventsAtClose = window.__ev.filter(e => e.id === modalId).map(e => e.k);
            __yes(kind);
            res();
        }, 50);
    })""", [kind, modal])
    assert page.evaluate("window.__eventsAtClose") == ["show"], "precondition: still fading in"
    assert page.evaluate("window.__ran") == ["probe"]
    _js_until(page, f"window.__ev.some(e => e.id === {json.dumps(modal)} && e.k === 'hidden')", 6_000,
              f"a {kind} dialog closed during its fade-in stayed on screen (hide() was ignored)")
    _js_until(page, "state.activeModal === null"
              f" && !document.getElementById({json.dumps(modal)}).classList.contains('show')", 3_000,
              f"the {kind} dialog did not end closed")


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("kind", list(DIALOGS))
def test_a_reprompt_raised_during_a_fade_in_close_stays_on_screen(
        page: Page, base_url: str, reset_dom_state_js: str, kind: str):
    """Guards the queued HIDE's cancellation: a prompt re-armed before shown.bs.modal
    must not be hidden by the close that preceded it. (Unfixed code also passes,
    for all three dialogs: there the close was ignored outright.) FE-4:
    parametrized over confirm / safety / action."""
    FakeBackend(page)
    _boot(page, base_url, reset_dom_state_js)
    d = DIALOGS[kind]
    page.evaluate("""(kind) => {
        __open(kind, 'first', 'first', () => setTimeout(() => __open(kind, 'second', 'second'), 20));
        setTimeout(() => __yes(kind), 50);
    }""", kind)
    _wait_shown(page, 1, f"the {kind} dialog never showed", modal=d["modal"])
    page.wait_for_timeout(1_500)
    snap = _dialog_snapshot(page, kind)
    assert snap["shown"] and snap["text"] == "second" and snap["activeModal"] == kind, snap

    page.click(d["yes"])
    _js_until(page, "window.__ran.length > 0", 3_000, f"the {kind} re-prompt's button ran nothing")
    assert page.evaluate("window.__ran") == ["second"]


# ---------------------------------------------------------------------------
# doEject's success path refreshes the view that is actually open
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_successful_eject_refreshes_the_open_manage_view_not_the_cards_box(
        page: Page, base_url: str, reset_dom_state_js: str):
    """A Quick-Swap card passes its SOURCE BOX as loc (ui_builder.js), so
    refreshManageView(loc) rendered the box's grid into the toolhead's view.

    FE-6 hardening: refreshManageView silently does nothing if the open view's
    row is missing from state.allLocations, which a heartbeat fetchLocations
    could cause between a row push and the click. GET /api/locations (and the
    pulse's locations section) now always carry the fake rows, the rows are
    re-asserted in the same task as the confirm, and the wait is for the
    specific id rather than for any get_contents."""
    be = FakeBackend(page, lambda b: OK, extra_locations=FAKE_MANAGE_ROWS)
    _boot(page, base_url, reset_dom_state_js)
    page.wait_for_function("state.allLocations.some(l => l.LocationID === 'FCC-TEST-TH')", timeout=15_000)
    page.evaluate("""() => {
        window.__pulses = [];
        document.addEventListener('inventory:sync-pulse', e => window.__pulses.push(e.detail && e.detail.source));
        document.getElementById('manage-loc-id').value = 'FCC-TEST-TH';
    }""")

    page.evaluate("ejectSpool(990002, 'FCC-TEST-BOX', false)")
    _wait_shown(page, 1, "the eject confirm never showed")
    be.get_contents_ids.clear()
    page.evaluate("""(rows) => {
        rows.forEach(r => { if (!state.allLocations.some(l => l.LocationID === r.LocationID)) state.allLocations.push(r); });
        document.querySelector('#confirmModal .btn-success').click();
    }""", FAKE_MANAGE_ROWS)

    _until(page, lambda: be.ejects(), 3_000, "the eject POST never went out")
    assert be.ejects()[0]["location"] == "FCC-TEST-BOX"
    _until(page, lambda: "FCC-TEST-TH" in be.get_contents_ids, 5_000,
           "no refresh of the open FCC-TEST-TH view after a successful eject")
    page.wait_for_timeout(300)
    assert "FCC-TEST-BOX" not in be.get_contents_ids, (
        f"refreshed the card's box instead of the open toolhead view: {be.get_contents_ids}")
    _js_until(page, "window.__pulses.includes('eject')", 3_000,
              "no inventory:sync-pulse, so the Quick-Swap grid waits for the next heartbeat")
