"""window.registerShapeshiftQR — reusable in-place "shapeshift" deck QR helper
(generalizes the Audit slot, Derek 2026-06-07).

Two guarantees:
  1. The Audit slot, now migrated onto the helper, still shapeshifts EXACTLY as
     before: idle = CMD:AUDIT / "AUDIT" / no active class / panel closed;
     active = CMD:DONE / "FINISH" / active classes / panel open.
  2. The generic factory works on any slot: it re-encodes the QR command,
     rewrites the label, and swaps active classes (union-clearing so switching
     states removes the previous state's class).

We stub window.QRCode (qrcodejs) to capture the exact text each generateSafeQR
re-render encodes, since the encoded command isn't otherwise visible in the DOM.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect


def _goto(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function(
        "typeof window.registerShapeshiftQR === 'function' "
        "&& typeof window.updateAuditVisuals === 'function'",
        timeout=5_000,
    )


_STUB_QRCODE = """() => {
    window.__qrCalls = [];
    const Orig = window.QRCode;
    function FakeQR(el, opts) {
        window.__qrCalls.push({ id: el && el.id, text: opts && opts.text });
    }
    FakeQR.CorrectLevel = (Orig && Orig.CorrectLevel) || { L: 0, M: 1, Q: 2, H: 3 };
    window.QRCode = FakeQR;
}"""


def _last_qr_for(page: Page, slot_id: str):
    return page.evaluate(
        """(slotId) => {
            const calls = (window.__qrCalls || []).filter(c => c.id === slotId);
            return calls.length ? calls[calls.length - 1].text : null;
        }""",
        slot_id,
    )


def test_audit_slot_shapeshifts_between_states(page: Page):
    _goto(page)
    page.evaluate(_STUB_QRCODE)

    # --- ACTIVE state ---
    page.evaluate("state.auditActive = true; window.updateAuditVisuals();")
    expect(page.locator("#lbl-audit")).to_have_text("FINISH")
    assert page.evaluate("document.getElementById('btn-deck-audit').classList.contains('btn-audit-active')") is True
    assert page.evaluate("document.getElementById('lbl-audit').classList.contains('label-active-audit')") is True
    # onEnter opened the visual audit panel.
    expect(page.locator("#fcc-audit-panel-overlay")).to_be_visible(timeout=3_000)
    # QR re-encoded to CMD:DONE (wait for the double-rAF generateSafeQR to flush).
    page.wait_for_function(
        "() => (window.__qrCalls || []).some(c => c.id === 'qr-audit' && c.text === 'CMD:DONE')",
        timeout=3_000,
    )
    assert _last_qr_for(page, "qr-audit") == "CMD:DONE"

    # --- IDLE state ---
    page.evaluate("state.auditActive = false; window.updateAuditVisuals();")
    expect(page.locator("#lbl-audit")).to_have_text("AUDIT")
    assert page.evaluate("document.getElementById('btn-deck-audit').classList.contains('btn-audit-active')") is False
    assert page.evaluate("document.getElementById('lbl-audit').classList.contains('label-active-audit')") is False
    # onEnter closed the panel.
    expect(page.locator("#fcc-audit-panel-overlay")).to_have_count(0, timeout=3_000)
    page.wait_for_function(
        "() => { const c = (window.__qrCalls || []).filter(x => x.id === 'qr-audit'); "
        "return c.length && c[c.length-1].text === 'CMD:AUDIT'; }",
        timeout=3_000,
    )
    assert _last_qr_for(page, "qr-audit") == "CMD:AUDIT"


def test_registershapeshiftqr_generic_slot(page: Page):
    _goto(page)
    page.evaluate(_STUB_QRCODE)

    # Inject a throwaway deck slot following the qr-/lbl-/btn-deck- convention.
    page.evaluate(
        """() => {
            const wrap = document.createElement('div');
            wrap.id = 'btn-deck-xtest';
            wrap.innerHTML = '<div id="qr-xtest"></div><div id="lbl-xtest">START</div>';
            document.body.appendChild(wrap);
            window.__xt = window.registerShapeshiftQR({
                slot: 'xtest', size: 64, default: 'armed',
                states: {
                    armed:    { cmd: 'CMD:XARM',    label: 'ARMED',    btnClass: 'x-on',  labelClass: 'lbl-on' },
                    disarmed: { cmd: 'CMD:XDISARM', label: 'DISARMED' },
                },
            });
        }"""
    )

    # set('armed') → label/classes/cmd applied.
    page.evaluate("window.__xt.set('armed')")
    expect(page.locator("#lbl-xtest")).to_have_text("ARMED")
    assert page.evaluate("document.getElementById('btn-deck-xtest').classList.contains('x-on')") is True
    assert page.evaluate("document.getElementById('lbl-xtest').classList.contains('lbl-on')") is True
    page.wait_for_function(
        "() => (window.__qrCalls || []).some(c => c.id === 'qr-xtest' && c.text === 'CMD:XARM')",
        timeout=3_000,
    )
    assert page.evaluate("window.__xt.current()") == "armed"

    # set('disarmed') → label changes AND the previous state's classes are
    # union-cleared (disarmed declares none).
    page.evaluate("window.__xt.set('disarmed')")
    expect(page.locator("#lbl-xtest")).to_have_text("DISARMED")
    assert page.evaluate("document.getElementById('btn-deck-xtest').classList.contains('x-on')") is False
    assert page.evaluate("document.getElementById('lbl-xtest').classList.contains('lbl-on')") is False
    page.wait_for_function(
        "() => { const c = (window.__qrCalls || []).filter(x => x.id === 'qr-xtest'); "
        "return c.length && c[c.length-1].text === 'CMD:XDISARM'; }",
        timeout=3_000,
    )

    # reset() returns to the default state.
    page.evaluate("window.__xt.reset()")
    expect(page.locator("#lbl-xtest")).to_have_text("ARMED")
    assert page.evaluate("window.__xt.current()") == "armed"

    # Unknown state is a no-op (no throw, state unchanged).
    page.evaluate("window.__xt.set('nope')")
    assert page.evaluate("window.__xt.current()") == "armed"
