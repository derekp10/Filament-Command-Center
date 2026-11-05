"""Review 3, R3S-1 (Derek, 2026-11-04, option (a)): the QR FCC draws on a spool's card on
the screen is never a label read.

Derek, 2026-11-03: "We should make sure that scanning the QR code in the UI doesn't count as a
confirmed label in the backlog and in the tagging of an unconfirmed label field." The audit's
own doors (a tile's QR, a press, 🔎 Find, a search card) already read no label
(test_audit_no_label_58.py); but every scan-buffer card (inv_cmd.js renderBuffer) and every
Location Manager spool card (inv_loc_mgr.js, its ✋ PICK) drew a QR of ID:<id>, the printed
label's own text, and a scanner reading it off the screen sends exactly what a printed label
sends, which FCC takes as a label read (routes_scan._is_label_read): in an audit it confirmed a
spool's missing label status ("✅ Found #57 (1 left)", "✔️ Spool #57 Label Verified"), and
outside one it cleared a "needs a label" flag, so the spool left the 🏷️ Backlog with no label
printed. Those cards now draw SPL:<id> (inv_core.js window.fccSpoolCardQr), a spool form the
scan path reads as that spool everywhere and never as a label read; a label FCC prints keeps
ID: (labels_csv.py).

On a real DOM, hermetic: the REAL overlay_mount.js, inv_core.js, ui_builder.js, inv_cmd.js,
inv_loc_mgr.js, duplicate_picker.js and the real scan accumulator
(test_scanner_safe_dialogs_61_js's `page61`), the Location Manager's real markup, in
`isolated_page`, so it runs under --offline. What each card draws is read from the QR library's
own call (its drawing needs a CDN), then typed as a scanner's burst through the accumulator, and
every request to FCC goes through an exposed binding to the REAL Flask routes over
tests/spoolman_extra_fake.SpoolmanHTTPFake (test_audit_session_58's `env`), so the label's status
is Spoolman's own after the scan. RED on 3e26878 unless a test says it pins what was right.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import app as app_module
import logic
import routes_print_queue
from test_audit_session_58 import add_spool, env, session, start  # noqa: F401  (env: the fixture)
from test_scanner_safe_dialogs_61_js import LEGACY, page61  # noqa: F401  (page61: the fixture)

HUB = Path(__file__).resolve().parent.parent
LABEL = "needs_label_print"

# The QR library from the CDN draws a canvas; here each box keeps the text it was asked to
# draw. Every request to FCC's scan and audit routes goes to the real routes (`__fcc`), the
# rest to page61's stubs.
BRIDGE = r"""() => {
    window.QRCode = function (el, o) { el.dataset.qrText = o.text; el.textContent = 'QR'; };
    window.QRCode.CorrectLevel = { L: 1 };
    window.__sent = [];
    const plain = window.fetch;
    window.fetch = async (url, opts) => {
        const u = String(url);
        if (!/\/api\/(identify_scan|audit)/.test(u)) return plain(url, opts);
        const body = opts && opts.body ? opts.body : null;
        if (body) window.__sent.push(JSON.parse(body));
        const got = JSON.parse(await window.__fcc(u, (opts && opts.method) || 'GET', body));
        return { ok: got.status < 400, status: got.status, json: async () => JSON.parse(got.text), text: async () => got.text };
    };
}"""


@pytest.fixture
def cards(env, page61):
    """page61 with the dashboard's buffer box and the Location Manager's markup, answered by the
    real routes."""
    page = page61
    client = app_module.app.test_client()

    def answer(url, method, body):
        res = client.open(url, method=method, data=body, content_type="application/json")
        return json.dumps({"status": res.status_code, "text": res.get_data(as_text=True)})
    page.expose_function("__fcc", answer)
    markup = (HUB / "templates" / "components" / "modals_loc_mgr.html").read_text(encoding="utf-8")
    page.evaluate("""(markup) => {
        document.body.insertAdjacentHTML('beforeend',
            '<div id="buffer-zone"></div><div id="buffer-nav-deck"></div>' + markup);
    }""", markup)
    page.evaluate(BRIDGE)
    return page


def _held(sid):
    return {"id": sid, "display": f"#{sid} Some Brand PLA (Red)", "color": "72071C", "remaining_weight": 500}


def buffer_card_qr(page, sid):
    """What #sid's scan-buffer card draws, as the dashboard draws it."""
    page.evaluate("(s) => { state.heldSpools = [s]; window.renderBuffer(); }", _held(sid))
    page.wait_for_function("() => { const q = document.getElementById('qr-buf-0'); return !!(q && q.dataset.qrText); }")
    return page.evaluate("() => document.getElementById('qr-buf-0').dataset.qrText")


def manager_card_qr(page, sid, place="LR-MDB-2"):
    """What #sid's card in the Location Manager draws (a list view: the place has no slots),
    with the buffer empty, as the heartbeat draws it."""
    page.evaluate("""([sid, place]) => {
        state.heldSpools = [];
        state.allLocations = [{ LocationID: place, Name: 'A cart', Type: 'Cart' }];
        document.getElementById('manage-loc-id').value = place;
        state.lastLocRenderHash = null;
        window._renderManagePayload(place, [{ id: sid, display: '#' + sid + ' Some Brand PLA (Red)', color: '72071C',
            remaining_weight: 500, location: place, slot: '', details: {} }]);
    }""", [sid, place])
    page.wait_for_function("() => { const q = document.getElementById('qr-pick-0'); return !!(q && q.dataset.qrText); }")
    return page.evaluate("() => document.getElementById('qr-pick-0').dataset.qrText")


def scanned_off_the_screen(page, text):
    """A scanner reading `text` off the screen: a burst of keys and its Enter, through the real
    accumulator (source 'barcode'), and its answer drawn."""
    n = len(page.evaluate("window.__sent"))
    page.evaluate("() => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); }")
    page.keyboard.type(text, delay=0)
    page.keyboard.press("Enter")
    page.wait_for_function("(n) => window.__sent.length > n", arg=n)
    page.wait_for_function("() => !state.processing")
    sent = page.evaluate("window.__sent")[n]
    assert sent["text"] == text and sent["source"] == "barcode", sent
    return sent


def status(env, sid):
    """The label status as Spoolman holds it, on the wire ('true', 'false' or None)."""
    return env["fake"].extra("spool", sid).get(LABEL)


def test_a_buffer_cards_qr_never_clears_a_needs_a_label_flag(cards, env):
    """Outside an audit: #58 is flagged for a new label (it is on the 🏷️ Backlog), and its
    buffer card's QR is scanned off the screen. RED on 3e26878: the card drew ID:58, FCC logged
    "✔️ Spool #58 Label Verified", the flag went to false, and #58 left the Backlog with no label
    printed. Now nothing is written, and the scan still finds #58 (already in the buffer)."""
    add_spool(env, 58, "LR-MDB-1", container_slot="1", **{LABEL: True})
    records = env["fake"].records["spool"]
    assert routes_print_queue._needs_label(records[58]) is True
    qr = buffer_card_qr(cards, 58)
    scanned_off_the_screen(cards, qr)
    assert status(env, 58) == "true"
    assert routes_print_queue._needs_label(records[58]) is True
    assert not [m for m, _c, _k in env["logs"] if "Label Verified" in m], env["logs"]
    assert cards.evaluate("state.heldSpools.map((s) => s.id)") == [58]
    assert ["warning", "Already in Buffer"] in cards.evaluate(
        """() => Array.from(document.querySelectorAll('#toast-container .toast-msg'))
            .map((e) => [e.className.replace('toast-msg toast-', ''), e.innerText])""")


def test_a_location_manager_cards_qr_never_confirms_a_label_and_still_picks_the_spool(cards, env):
    """Outside an audit: #60, with no label status, is on a cart; its Location Manager card's
    QR (the ✋ PICK) is scanned off the screen. It still picks #60 into the buffer, as it did,
    and writes nothing on its label. RED on 3e26878: the status went from none to confirmed."""
    add_spool(env, 60, "LR-MDB-2")
    qr = manager_card_qr(cards, 60)
    scanned_off_the_screen(cards, qr)
    assert status(env, 60) is None
    assert not [m for m, _c, _k in env["logs"] if "Label Verified" in m], env["logs"]
    assert cards.evaluate("state.heldSpools.map((s) => s.id)") == [60]


def test_in_an_audit_a_cards_qr_finds_the_spool_with_no_label_read(cards, env):
    """In an audit of LR-MDB-1, with the panel hidden: #57, with no label status, is found by
    its buffer card's QR, and #59, flagged, by its Location Manager card's. Each is found as a
    find with no label read is ("Found #57, no label read (1 left)"), and neither label status
    moves. RED on 3e26878: "Found #57 (1 left)", the words of a label read, and #57's status
    went to confirmed, the false green tick 58.5 took out."""
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    add_spool(env, 59, "LR-MDB-1", container_slot="2", **{LABEL: True})
    add_spool(env, 61, "LR-MDB-1", container_slot="3")
    start(env, "LR-MDB-1")
    cards.evaluate("(id) => { state.auditActive = true; state.auditId = id; }", session()["audit_id"])
    qr57 = buffer_card_qr(cards, 57)
    scanned_off_the_screen(cards, qr57)
    assert 57 in session()["scanned_items"]
    lines = [m for m, _c, _k in env["logs"] if "#57" in m]
    assert lines == ["✅ Found #57, no label read (2 left)"], lines
    assert status(env, 57) is None
    assert session()["found_by"]["57"] == logic.AUDIT_FOUND_NO_LABEL
    qr59 = manager_card_qr(cards, 59, "LR-MDB-1")
    scanned_off_the_screen(cards, qr59)
    assert 59 in session()["scanned_items"]
    assert status(env, 59) == "true"
    assert not [m for m, _c, _k in env["logs"] if "Label Verified" in m], env["logs"]


def test_a_cards_qr_is_the_spool_form_the_scan_path_reads_and_no_label(cards):
    """What the two cards draw: the spool form the scan path reads as the spool and never as a
    label read (SPL:<id>, logic.resolve_scan's step 5, routes_scan._is_label_read), the same
    text whichever way the Location Manager draws it (its self-heal redraw too). RED on
    3e26878: ID:<id>, the printed label's own text."""
    assert buffer_card_qr(cards, 57) == "SPL:57"
    assert manager_card_qr(cards, 60) == "SPL:60"
    # The self-heal pass (21.2): a QR box left empty by a dropped render is drawn again.
    cards.evaluate("() => { const q = document.getElementById('qr-pick-0'); q.innerHTML = ''; delete q.dataset.qrText; }")
    cards.evaluate("() => window._ensureManageQRsFilled()")
    cards.wait_for_function("() => !!document.getElementById('qr-pick-0').dataset.qrText")
    assert cards.evaluate("() => document.getElementById('qr-pick-0').dataset.qrText") == "SPL:60"


def test_the_legacy_picker_still_takes_a_cards_qr_as_that_spools_own_label(page61):
    """The legacy-ID picker (Group 61): a listed spool's own label picks it. A card's QR read
    off the screen is one, and the pick goes out as no label read ('keyboard'), as an SPL: label
    already did. A pin: SPL: was always read so (duplicate_picker.js)."""
    page = page61
    page.evaluate("(a) => { window.__answers['LEG:120'] = a; window.processScan('LEG:120', 'barcode'); }", LEGACY)
    page.wait_for_selector("#fcc-legacy-picker-overlay", timeout=5000)
    page.wait_for_timeout(150)
    page.keyboard.type("SPL:134", delay=0)          # what #134's card draws (pinned above)
    page.keyboard.press("Enter")
    page.wait_for_selector("#fcc-legacy-picker-overlay", state="detached")
    page.wait_for_function("() => window.__ids.length >= 2")
    assert page.evaluate("() => window.__ids.map((r) => [r.text, r.source])")[-1] == ["ID:134", "keyboard"]
