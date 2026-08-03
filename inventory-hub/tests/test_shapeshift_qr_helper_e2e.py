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


def test_bulkmove_slot_shapeshifts_between_states(page: Page):
    """L298 Phase 3 — the 4-state BULK MOVE slot had no coverage, so nothing
    pinned the label / btnClass / ENCODED COMMAND per state.

    That matters because the block comment above the slot once claimed the two
    "scan a location label" states encode no cmd, while the shipped table sets
    CMD:CANCEL for both. Acting on the comment would have made st.cmd falsy —
    and (pre-fix) a falsy cmd left the PREVIOUS state's QR on screen, which from
    `preview` strands a scannable CMD:DONE over a half-armed session.
    """
    _goto(page)
    page.evaluate(_STUB_QRCODE)
    # Keep the panel out of the way — this test is about the deck tile. (Its
    # own behaviour is covered by tests/test_bulk_move_panel.py.) Arrow-function
    # form: page.evaluate CALLS a script whose value is a function, so a trailing
    # `window.x = () => …` would invoke the stub immediately.
    page.evaluate("""() => {
        window.openBulkMovePanel = () => {};
        window.closeBulkMovePanel = () => {};
    }""")

    expected = {
        "awaiting_source": ("SCAN SRC", "CMD:CANCEL", "btn-bulkmove-active"),
        "awaiting_dest": ("SCAN DEST", "CMD:CANCEL", "btn-bulkmove-active"),
        "preview": ("COMMIT", "CMD:DONE", "btn-bulkmove-ready"),
    }
    for stage, (label, cmd, btn_class) in expected.items():
        # Count BEFORE, and require the count to grow. Matching only the tail
        # text is satisfied by the PREVIOUS state's call when two states encode
        # the same command (awaiting_source and awaiting_dest both use
        # CMD:CANCEL) — so a regression that stopped re-rendering the QR
        # entirely would still pass.
        before = page.evaluate(
            "() => (window.__qrCalls || []).filter(x => x.id === 'qr-bulkmove').length")
        page.evaluate(
            "(s) => { state.bulkMoveActive = true; state.bulkMoveStage = s; "
            "window.updateBulkMoveVisuals(); }", stage)
        expect(page.locator("#lbl-bulkmove")).to_have_text(label)
        assert page.evaluate(
            "(c) => document.getElementById('btn-deck-bulkmove').classList.contains(c)",
            btn_class) is True
        assert page.evaluate(
            "document.getElementById('lbl-bulkmove').classList.contains('label-active-bulkmove')") is True
        page.wait_for_function(
            "([t, n]) => { const c = (window.__qrCalls || []).filter(x => x.id === 'qr-bulkmove'); "
            "return c.length > n && c[c.length-1].text === t; }",
            arg=[cmd, before], timeout=3_000)

    # --- IDLE: label + cmd revert and the active classes are union-cleared ---
    page.evaluate("state.bulkMoveActive = false; state.bulkMoveStage = 'idle'; "
                  "window.updateBulkMoveVisuals();")
    expect(page.locator("#lbl-bulkmove")).to_have_text("BULK MOVE")
    assert page.evaluate(
        "document.getElementById('btn-deck-bulkmove').classList.contains('btn-bulkmove-ready')") is False
    assert page.evaluate(
        "document.getElementById('btn-deck-bulkmove').classList.contains('btn-bulkmove-active')") is False
    page.wait_for_function(
        "() => { const c = (window.__qrCalls || []).filter(x => x.id === 'qr-bulkmove'); "
        "return c.length && c[c.length-1].text === 'CMD:BULKMOVE'; }",
        timeout=3_000)


def test_shapeshift_state_without_a_cmd_clears_the_stale_qr(page: Page):
    """A cmd-less state must CLEAR the QR div, not inherit the previous state's.

    Pre-fix, `if (qrDiv && st.cmd)` skipped the whole block, leaving a scannable
    command under a label that no longer matches it — a live footgun for any
    future deck state that legitimately has nothing to encode.
    """
    _goto(page)
    page.evaluate(_STUB_QRCODE)
    page.evaluate(
        """() => {
            const wrap = document.createElement('div');
            wrap.id = 'btn-deck-ytest';
            wrap.innerHTML = '<div id="qr-ytest"></div><div id="lbl-ytest">A</div>';
            document.body.appendChild(wrap);
            window.__yt = window.registerShapeshiftQR({
                slot: 'ytest', size: 64, default: 'withcmd',
                states: {
                    withcmd: { cmd: 'CMD:YGO', label: 'GO' },
                    nocmd:   { label: 'WAIT' },
                },
            });
        }"""
    )
    page.evaluate("window.__yt.set('withcmd')")
    page.wait_for_function(
        "() => (window.__qrCalls || []).some(c => c.id === 'qr-ytest' && c.text === 'CMD:YGO')",
        timeout=3_000)
    # Prove something is actually rendered before we assert it goes away.
    page.evaluate("document.getElementById('qr-ytest').innerHTML = '<canvas></canvas>';")

    page.evaluate("window.__yt.set('nocmd')")
    expect(page.locator("#lbl-ytest")).to_have_text("WAIT")
    assert page.evaluate("document.getElementById('qr-ytest').innerHTML.trim()") == ""
