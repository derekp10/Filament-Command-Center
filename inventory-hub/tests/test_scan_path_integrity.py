"""Scan-path integrity guards (axis-(a) audit, 2026-08-03).

FCC's primary input is a barcode scanner whose keystrokes are accumulated by a
global `document` keydown listener in templates/components/scripts.html. That
listener begins `if (e.target.tagName === 'INPUT') return;`, so ANY focused
text-entry element silently disarms the scanner, and any competing keydown
handler can steal the Enter that terminates a scan or leave junk in the buffer.

The audit found 11 distinct instances of that class. These tests pin the guards
that fix them. Most are SOURCE-TEXT pins rather than behavioural tests: the
defects live in event-ordering between listeners that only exists in a real
browser, and a source pin at least fails loudly when someone deletes the guard
while refactoring — which is precisely how several of these regressed into
existence (the same defect recurred in four separate modules).

The one exception is the `state.activeModal` leak, which IS behaviourally
testable and gets a real E2E below, because it is the highest-severity finding:
it silently swallows every scan until a page reload.
"""
from __future__ import annotations

from pathlib import Path

import pytest

INV_HUB = Path(__file__).resolve().parent.parent
JS = INV_HUB / "static" / "js" / "modules"
TPL = INV_HUB / "templates" / "components"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# The Enter-ownership rule: a scan in flight owns the Enter key
# ---------------------------------------------------------------------------

# Every overlay/grid that binds its own Enter handler AND can be on screen while
# the user is expected to scan. The confirm overlays are the dangerous ones: they
# render a "Scan to Cancel" QR while focusing the YES button, so before the fix
# the CANCEL scan's terminating Enter performed the CONFIRM instead.
ENTER_OWNERSHIP_SITES = [
    # (file, label, minimum expected guard count)
    # The count matters: a bare "is the string present" check is VACUOUS for a
    # file that uses isScanInFlight for something ELSE. inv_cmd.js has two
    # independent uses — the Shift+B bulk-move closure AND the confirm-overlay
    # Enter guard — so deleting the safety-critical one would still leave the
    # string present and the test green.
    (JS / "inv_quickswap.js", "Quick-Swap confirm overlay + slot grid", 2),
    (JS / "inv_cmd.js", "Shift+B closure + active-print scan confirm overlay", 2),
    (JS / "inv_loc_mgr.js", "active-print assign confirm overlay", 1),
]


@pytest.mark.parametrize("path,label,minimum", ENTER_OWNERSHIP_SITES,
                         ids=[p.name for p, _, _ in ENTER_OWNERSHIP_SITES])
def test_enter_handlers_yield_to_an_in_flight_scan(path: Path, label: str, minimum: int):
    """Each Enter handler must bail while a scan is in flight.

    Without it, the Enter that terminates a scan is treated as a press of the
    focused button — and mountOverlay focuses YES — so scanning the overlay's
    own '📷 Scan to Cancel' QR CONFIRMED instead, yanking a spool off a live
    toolhead.
    """
    src = _read(path)
    found = src.count("isScanInFlight")
    assert found >= minimum, (
        f"{path.name} ({label}) has {found} isScanInFlight guard(s), expected "
        f">= {minimum}. One of its scan-in-flight guards was removed — if that "
        "is the confirm-overlay one, scanning 'Scan to Cancel' performs the "
        "CONFIRM and yanks a spool off a live toolhead."
    )


def test_quickswap_guards_both_its_enter_handlers():
    """inv_quickswap.js has TWO: the confirm overlay and the slot grid.

    The grid one fires on the Enter terminating an unrelated scan, opening an
    unrequested swap confirm — which then inherits the overlay bug above.
    """
    src = _read(JS / "inv_quickswap.js")
    assert src.count("isScanInFlight") >= 2, (
        "expected a scan-in-flight guard on BOTH the confirm overlay and the "
        f"Quick-Swap slot grid; found {src.count('isScanInFlight')}"
    )


def test_scan_in_flight_has_exactly_one_definition():
    """The 500ms scan-in-flight test must exist ONCE.

    It was copy-pasted verbatim into three modules (fab_drag, inv_cmd,
    shortcuts_registry) and the 2026-08-03 audit was about to add several more
    variants — some using a bare `scanBuffer` truthiness check, which is subtly
    WRONG: an abandoned keystroke lingers in the buffer until the 2s accumulator
    timeout, and during that window a truthiness check blocks real button
    presses. Divergent copies of a safety check are how this class of bug keeps
    coming back, so pin the single definition.
    """
    canonical = _read(JS / "inv_core.js")
    assert "const isScanInFlight" in canonical, (
        "the canonical isScanInFlight definition has left inv_core.js"
    )
    assert "window.isScanInFlight = isScanInFlight" in canonical, (
        "isScanInFlight is no longer exported for the other modules"
    )

    # The distinctive body of the check — nobody else may re-implement it.
    fingerprint = "Date.now() - st.scanStartTime"
    offenders = []
    for path in sorted(JS.glob("*.js")):
        if path.name == "inv_core.js":
            continue
        if fingerprint in _read(path):
            offenders.append(path.name)
    assert not offenders, (
        "scan-in-flight logic was re-implemented instead of calling "
        f"window.isScanInFlight(): {offenders}"
    )


# ---------------------------------------------------------------------------
# The accumulator's own guards
# ---------------------------------------------------------------------------

def test_accumulator_ignores_modifier_combos():
    """Ctrl/Alt/Meta combos are app shortcuts, never scanner output.

    Without this, Ctrl+C to copy a location id leaves 'c' in scanBuffer and the
    next scan dispatches 'cLOC:PM-DB-A' -> "Unknown Code" on a valid label.
    """
    src = _read(TPL / "scripts.html")
    assert "e.ctrlKey || e.altKey || e.metaKey" in src, (
        "the scan accumulator lost its modifier-key guard"
    )


def test_accumulator_modifier_guard_does_not_include_shift():
    """Load-bearing omission: scanners send Shift for EVERY uppercase char.

    Guarding on shiftKey would break every scan containing a capital letter,
    i.e. essentially all of them.
    """
    src = _read(TPL / "scripts.html")
    idx = src.find("e.ctrlKey || e.altKey || e.metaKey")
    assert idx != -1
    # Inspect just the guard expression, not the whole file.
    guard_line = src[idx:src.find("\n", idx)]
    assert "shiftKey" not in guard_line, (
        "shiftKey must NOT be in the accumulator's modifier guard — barcode "
        "scanners send Shift for uppercase, so this would break every scan"
    )


# ---------------------------------------------------------------------------
# Focus-holding controls that look like buttons
# ---------------------------------------------------------------------------

# `id` -> the file it lives in. Each is a checkbox/radio that RENDERS as a
# button or switch, so nothing on screen hints that a focus-holding <input> is
# active and the scanner has gone deaf.
BLUR_ON_CHANGE_CONTROLS = [
    ("weigh-auto-archive", TPL / "modals_weigh_out.html"),
    ("feeds-slot-order-ltr", TPL / "modals_loc_mgr.html"),
    ("feeds-slot-order-rtl", TPL / "modals_loc_mgr.html"),
]


@pytest.mark.parametrize("ctrl_id,path", BLUR_ON_CHANGE_CONTROLS,
                         ids=[c for c, _ in BLUR_ON_CHANGE_CONTROLS])
def test_focus_holding_control_blurs_on_change(ctrl_id: str, path: Path):
    src = _read(path)
    idx = src.find(f'id="{ctrl_id}"')
    assert idx != -1, f"control #{ctrl_id} not found in {path.name}"
    # The element's own tag text — from the preceding '<' to the closing '>'.
    start = src.rfind("<", 0, idx)
    end = src.find(">", idx)
    tag = src[start:end]
    assert "blur()" in tag, (
        f"#{ctrl_id} in {path.name} must blur on change — while it holds focus "
        "the global scan handler bails on tagName === 'INPUT' and the scanner "
        "is silently dead. This is the L298 bulk-move ack-box defect."
    )


# ---------------------------------------------------------------------------
# Shortcut handlers must not poison the buffer
# ---------------------------------------------------------------------------

def test_slash_search_shortcut_stops_the_accumulator():
    """preventDefault alone does NOT stop the accumulator — it's a separate
    document-level listener. '/' survived into scanBuffer and corrupted the
    next scan into '/LOC:...'."""
    src = _read(JS / "fab_drag.js")
    assert "stopImmediatePropagation" in src, (
        "fab_drag.js lost the stopImmediatePropagation that keeps '/' out of "
        "state.scanBuffer"
    )


def test_wizard_shortcuts_yield_to_an_in_flight_scan():
    """Shift+E / Shift+C are indistinguishable from a scanner sending the
    uppercase letters 'E' and 'C', which appear in ordinary labels."""
    src = _read(JS / "inv_wizard.js")
    assert "isScanInFlight" in src, (
        "inv_wizard.js lost its scan-in-flight guard; a scanned label "
        "containing E or C would fire expand/collapse and corrupt the scan"
    )


# ---------------------------------------------------------------------------
# The HIGH finding, tested for real
# ---------------------------------------------------------------------------

def test_hidden_bs_modal_releases_the_scan_gate_source():
    src = _read(JS / "inv_core.js")
    assert "SCAN_GATING_MODALS" in src, (
        "inv_core.js lost the hidden.bs.modal scan-gate release; dismissing a "
        "confirm with Escape would again leave state.activeModal latched and "
        "silently swallow every scan until reload"
    )


@pytest.mark.usefixtures("require_server")
def test_weigh_out_captures_a_scan_from_a_focused_weight_field_e2e(page):
    """The Weigh-Out modal advertises live scanning twice, but auto-focuses a
    weight input — and the global accumulator bails on a focused INPUT, so the
    feature was dead and the barcode was typed into the weight box instead.

    Derek's call was to KEEP the auto-focus (typing weights is the primary
    action there) and capture the scan from inside the field.

    Driven against a synthetic .weigh-input rather than a real weigh-out
    session: the capture listener is bound to `document` and keys only off the
    element's class, so this exercises the real code path without needing spools
    in the buffer — and without mutating dev inventory. processScan is stubbed
    for the same reason.
    """
    page.goto("http://localhost:8000/", wait_until="domcontentloaded")
    page.wait_for_function("typeof state !== 'undefined'", timeout=15000)

    page.evaluate("""
        window.__scanned = [];
        window.processScan = (text, source) => window.__scanned.push([text, source]);
        const inp = document.createElement('input');
        inp.type = 'text';
        inp.className = 'weigh-input';
        inp.id = '__probe_weigh_input';
        document.body.appendChild(inp);
        inp.focus();
    """)

    # 1. SCANNER: a prefixed payload delivered at scanner speed.
    #    dispatch directly so the timing is genuinely sub-150ms.
    page.evaluate("""
        const inp = document.getElementById('__probe_weigh_input');
        for (const ch of 'ID:9') {
            inp.dispatchEvent(new KeyboardEvent('keydown', {key: ch, bubbles: true}));
            inp.value += ch;
        }
        inp.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
    """)
    assert page.evaluate("window.__scanned.length") == 1, (
        "a scanner payload typed into a focused weight field was not routed to "
        "processScan — the modal's advertised 'scan them now while this window "
        "is open' is dead"
    )
    assert page.evaluate("window.__scanned[0][0]") == "ID:9"
    assert page.evaluate("document.getElementById('__probe_weigh_input').value") == "", (
        "the scanned barcode was left sitting in the weight field — in "
        "'additive' mode that field is type=text, so Enter would save the "
        "barcode AS A WEIGHT"
    )

    # 2. HUMAN: a plain numeric weight must NOT be hijacked, even if typed fast.
    page.evaluate("""
        window.__scanned = [];
        const inp = document.getElementById('__probe_weigh_input');
        inp.value = '';
        for (const ch of '1234') {
            inp.dispatchEvent(new KeyboardEvent('keydown', {key: ch, bubbles: true}));
            inp.value += ch;
        }
        inp.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
    """)
    assert page.evaluate("window.__scanned.length") == 0, (
        "a numeric weight was misrouted to processScan — weights must never be "
        "treated as scans, however fast they are typed"
    )
    assert page.evaluate("document.getElementById('__probe_weigh_input').value") == "1234", (
        "a typed weight was cleared out of the field"
    )

    page.evaluate("document.getElementById('__probe_weigh_input').remove()")


@pytest.mark.usefixtures("require_server")
def test_manage_id_field_captures_a_scan_e2e(page):
    """Manage Contents re-focuses #manual-spool-id after every add, so the
    modal's OWN CMD:DONE QR came back as "Invalid Code".

    Derek's call was to KEEP the re-focus (it's there so several legacy ids can
    be typed in a row) and capture scanner input from the field instead — the
    same resolution as Weigh-Out, through the shared helper.
    """
    page.goto("http://localhost:8000/", wait_until="domcontentloaded")
    page.wait_for_function("typeof window.installFieldScanCapture === 'function'",
                           timeout=15000)

    page.evaluate("""
        window.__scanned = [];
        window.processScan = (t, s) => window.__scanned.push([t, s]);
        const inp = document.createElement('input');
        inp.type = 'text';
        inp.id = 'manual-spool-id';
        inp.setAttribute('data-probe', '1');
        document.body.appendChild(inp);
        inp.focus();
    """)

    def _type(text):
        page.evaluate("""(txt) => {
            const inp = document.querySelector('#manual-spool-id[data-probe]');
            inp.value = '';
            for (const ch of txt) {
                inp.dispatchEvent(new KeyboardEvent('keydown', {key: ch, bubbles: true}));
                inp.value += ch;
            }
            inp.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
        }""", text)

    # A scanned command QR — the exact case that reported "Invalid Code".
    _type("CMD:DONE")
    assert page.evaluate("window.__scanned.length") == 1, (
        "the modal's own CMD:DONE QR was not routed to the scan path"
    )
    assert page.evaluate("window.__scanned[0][0]") == "CMD:DONE"
    assert page.evaluate("document.querySelector('#manual-spool-id[data-probe]').value") == ""

    # A hand-typed legacy id must still reach the field's own handler.
    page.evaluate("window.__scanned = []")
    _type("12345")
    assert page.evaluate("window.__scanned.length") == 0, (
        "a typed legacy spool id was hijacked as a scan — that field exists to "
        "accept exactly this"
    )
    assert page.evaluate("document.querySelector('#manual-spool-id[data-probe]').value") == "12345"

    page.evaluate("document.querySelector('#manual-spool-id[data-probe]').remove()")


@pytest.mark.usefixtures("require_server")
def test_slot_scan_during_an_active_print_offers_the_confirm_e2e(page):
    """Scanning a slot QR while that printer is printing used to dead-end.

    The backend has always answered `assignment_requires_confirm` with the
    printer state attached, but the scan path had no branch for it — so it fell
    through to a yellow "Unknown assignment result" toast with no dialog and no
    way to proceed, however many times you rescanned. Every other surface
    already prompts; this one couldn't.

    The response is stubbed rather than driven off a real print: making this
    happen for real means starting a print and yanking a spool off a live
    toolhead.
    """
    page.goto("http://localhost:8000/", wait_until="domcontentloaded")
    page.wait_for_function("typeof window.processScan === 'function'", timeout=15000)

    page.evaluate("""
        window.__toasts = [];
        const realToast = window.showToast;
        window.showToast = (m, t, d) => { window.__toasts.push(String(m)); };
        // Stub the scan POST with exactly what routes_scan.py returns when
        // perform_smart_move bails on the active-print guard.
        window.fetchT = () => Promise.resolve({ json: () => Promise.resolve({
            type: 'assignment',
            action: 'assignment_requires_confirm',
            location: 'XL-1',
            slot: '1',
            confirm_type: 'active_print',
            active_print: {printer_name: 'XL', state: 'PRINTING'},
            msg: 'XL is PRINTING',
            moved: 42,
        })});
        window.processScan('LOC:XL-1:SLOT:1', 'barcode');
    """)

    # The confirm overlay must appear...
    page.wait_for_selector("#fcc-aps-yes", timeout=8000)
    body = page.inner_text("body")
    assert "PRINTING" in body, "the confirm should name the printer state"

    # ...and the dead-end toast must NOT.
    toasts = page.evaluate("window.__toasts")
    assert not any("Unknown assignment result" in t for t in toasts), (
        f"the slot scan still dead-ends instead of prompting: {toasts}"
    )

    # Cancel out so the page is left clean for other tests.
    page.click("#fcc-aps-no")


@pytest.mark.usefixtures("require_server")
def test_escape_on_a_confirm_releases_the_scan_gate_e2e(page):
    """THE regression that matters: cancel a confirm with Escape, and the
    scanner must still work.

    Pre-fix, `state.activeModal` was cleared only by closeModal() — i.e. only by
    the dialog's own buttons — so an Escape (or backdrop click) left it latched
    at 'confirm'. From then on inv_cmd's router answered only CONFIRM/CANCEL and
    dropped every spool and location scan with no toast, no log line and no
    request: the scanner looked dead until a page reload.
    """
    page.goto("http://localhost:8000/", wait_until="domcontentloaded")
    page.wait_for_function("typeof state !== 'undefined'", timeout=15000)

    # Raise a confirm dialog through the app's own helper.
    page.evaluate("requestConfirmation('scan-gate regression probe', () => {})")
    page.wait_for_function(
        "document.getElementById('confirmModal')?.classList.contains('show')",
        timeout=5000,
    )
    assert page.evaluate("state.activeModal") == "confirm", (
        "precondition failed: the confirm did not arm the scan gate"
    )

    # Let the fade-IN finish. Bootstrap 5 silently IGNORES .hide() called while a
    # modal is still transitioning in — the same quirk inv_details.js's
    # _hideSiblingDetailsModal works around with a 400ms retry. Without this the
    # dismissal below is a no-op and the test fails for a reason that has nothing
    # to do with the scan gate.
    page.wait_for_timeout(600)

    # Dismiss WITHOUT going through closeModal() — that is the whole defect.
    # `inst.hide()` is exactly what inv_loc_mgr.js's document-capture Escape
    # ladder calls, and what a Bootstrap backdrop click does internally.
    #
    # We drive hide() directly rather than sending a keyboard Escape because
    # Bootstrap binds its Escape handler to the modal element: in a headless
    # page where focus never entered the dialog, Escape is simply not delivered
    # (verified — the modal stays open, so such a test would assert nothing).
    # Driving the bypass path directly tests the actual regression and is
    # deterministic.
    page.evaluate(
        "bootstrap.Modal.getInstance(document.getElementById('confirmModal')).hide()"
    )
    page.wait_for_function(
        "!document.getElementById('confirmModal')?.classList.contains('show')",
        timeout=5000,
    )
    # hidden.bs.modal fires after the fade transition.
    page.wait_for_function("state.activeModal === null", timeout=5000)

    assert page.evaluate("state.activeModal") is None, (
        "state.activeModal survived a non-closeModal dismissal — every "
        "subsequent spool/location scan will be silently swallowed"
    )
    # NOTE: `pendingConfirm` is deliberately NOT cleared here. An earlier
    # version of this fix did clear it, which broke the chained re-prompt
    # (eject -> "true unassign"): the first dialog's `hidden` event fired AFTER
    # the second had re-armed, wiping the new callback and leaving a dead YES
    # button. A generation counter guards the stale-callback case instead.
    #
    # Also worth recording: asserting on `pendingConfirm` from Playwright is a
    # TRAP. Its serializer has no branch for functions, so a live callback comes
    # back as Python None — identical to a real null. Any such assertion passes
    # unconditionally. Use `typeof` if this ever needs checking again.
    assert page.evaluate("typeof state.pendingConfirm") in ("function", "object"), (
        "sanity: pendingConfirm should still be inspectable via typeof"
    )
