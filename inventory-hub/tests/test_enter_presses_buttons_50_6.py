"""Group 50.6: Enter presses the focused button, as a click or Space does, and a
held Enter presses once.

Runs the REAL overlay_mount.js and inv_core.js and the REAL scan accumulator
(scripts.html's keydown block, lifted as test_slow_scan_slash_js.py lifts it),
plus inv_quickswap.js, inv_config.js and inv_settings.js where a test needs
them, in `isolated_page` (a chromium with no route to any network), so it RUNS
under --offline. Typed with Playwright's real keyboard: only a trusted Enter
makes the browser press a focused button, and a second `keyboard.down` of a
held key is an auto-repeat (`repeat: true`).

The defect: the accumulator cancelled every Enter outside a text field, so
Enter on a focused button did nothing (Space worked) and every dialog that
wanted it answered Enter itself. And a held Enter repeats: Chrome presses a
focused button on every repeat, and a dialog's own Enter handler answered each
one, so a key held a moment too long answered the NEXT dialog under it, the
printing yes / no's "Continue Anyway" among them.

Pinned: a person's Enter on a button or a link presses it once; a scan's Enter
(enterIsAScan) presses nothing and the scan reaches processScan whole; a key a
person left goes with their press; a held Enter presses once, answers no dialog
opened under it, and does nothing more in a text box, while a text area still
types its new lines; Enter presses nothing behind the overlay on top, while a
scan read earlier still waits to go out, in a window fading out, under its own
inline overlay (data-fcc-cover) or in a gating dialog not yet on screen. Derek's
answers (2026-10-29): the printing yes / no opens on Cancel; the settings
import opens on Cancel and backing out says nothing was imported. With them:
the tag remove and purge ask in an overlay that opens on Cancel (the browser's
confirm() opened on OK), Sweep Unused Tags opens on Cancel, and the Quick-Swap
grid's Enter presses the tile that has the focus, never a stale highlight.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
SCRIPTS = HUB / "templates" / "components" / "scripts.html"


def _accumulator():
    """The scan accumulator, exactly as the page has it."""
    src = SCRIPTS.read_text(encoding="utf-8")
    a = src.index("state.scanStartTime = 0;")
    b = src.index("// L206", a)
    block = src[a:b]
    assert "processScan(state.scanBuffer" in block and "function personMayPress" in block, block[:300]
    return block


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
body { margin: 0; font-family: sans-serif; }
.modal { display: none; } .modal.show { display: block; }
</style></head><body>
<button id="plain" onclick="window.__hit('plain')">Plain</button>
<a id="link" href="#nowhere" onclick="window.__hit('link'); return false;">A link</a>
<button id="opener">Open a question</button>
<input id="box" type="text"><textarea id="area"></textarea>
<div id="someModal" class="modal show" style="display:block"><div class="modal-content">
  <button id="in-modal" onclick="window.__hit('inModal')">In the window</button>
  <div id="cover" data-fcc-cover="1" style="display:none"><button id="in-cover" onclick="window.__hit('inCover')">In the cover</button></div>
</div></div>
<div id="confirmModal" class="modal show" style="display:block"><div class="modal-content">
  <button id="confirm-yes" onclick="window.__hit('confirmYes')">YES</button>
</div></div>
<div id="manageModal" class="modal show" style="display:block" tabindex="-1">
  <div id="manage-quickswap-section"><div id="quickswap-grid">
    <button class="fcc-qs-slot" id="tile-a" data-toolhead="XL-1" data-box="BOX-1" data-slot="1" onclick="window.__hit('tileA')">slot 1</button>
    <button class="fcc-qs-slot" id="tile-b" data-toolhead="XL-1" data-box="BOX-1" data-slot="2" onclick="window.__hit('tileB')">slot 2</button>
  </div></div>
  <button id="mm-other" onclick="window.__hit('mmOther')">Return to Slot</button>
</div>
<div id="configModal" class="modal show" style="display:block">
  <div id="config-attrs-results"></div>
  <button id="cfgio-import-btn">Import</button><input type="file" id="cfgio-file" style="display:none">
</div>
</body></html>"""

PRELUDE = r"""
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__hits = {};
window.__hit = (k) => { window.__hits[k] = (window.__hits[k] || 0) + 1; };
window.__fetches = [];
window.__answer = () => ({});
window.fetch = (url, opts) => {
    url = String(url);
    window.__fetches.push({ url, body: opts && opts.body ? JSON.parse(opts.body) : null });
    const ans = window.__answer(url, opts && opts.body ? JSON.parse(opts.body) : null);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(ans), text: () => Promise.resolve(JSON.stringify(ans)) });
};
(() => {
    const data = new Map();
    const store = { getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => data.set(k, String(v)),
                    removeItem: (k) => data.delete(k), clear: () => data.clear() };
    Object.defineProperty(window, 'localStorage', { value: store, configurable: true });
})();
"""

# After the modules (inv_core.js has its own showToast): what reached the scan
# path and every toast.
STUBS = r"""
window.__scans = [];
window.processScan = function (buf) { window.__scans.push(buf); };
window.__toasts = [];
window.showToast = (m, t, ms) => window.__toasts.push({ m, t, ms });
window.logClientEvent = function () {};
"""


@pytest.fixture
def page50(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=PRELUDE)
    for name in ("overlay_mount.js", "inv_core.js", "inv_quickswap.js", "inv_config.js", "inv_settings.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content=STUBS)
    page.add_script_tag(content=_accumulator())        # last, as on the page
    assert page.evaluate("window.__errors") == []
    return page


def _hits(page):
    return page.evaluate("() => window.__hits")


def _focus(page, sel):
    page.evaluate("(s) => document.querySelector(s).focus()", sel)
    assert page.evaluate("(s) => document.activeElement === document.querySelector(s)", sel), sel


def _hold_enter(page, repeats=2):
    """A held Enter: one press, then `repeats` auto-repeats, then the release."""
    page.keyboard.down("Enter")
    page.wait_for_timeout(30)
    for _ in range(repeats):
        page.keyboard.down("Enter")
        page.wait_for_timeout(30)
    page.keyboard.up("Enter")


# --- a person's Enter presses; a scan's doesn't -------------------------------------

def test_a_persons_enter_presses_the_focused_button_or_link_once(page50):
    page = page50
    _focus(page, "#plain")
    page.keyboard.press("Enter")
    _focus(page, "#link")
    page.keyboard.press("Enter")
    assert _hits(page) == {"plain": 1, "link": 1}
    assert page.evaluate("window.__scans") == []


def test_a_scan_typed_onto_a_button_presses_nothing_and_reaches_the_scan_path_whole(page50):
    page = page50
    _focus(page, "#plain")
    page.keyboard.type("LOC:BIN-2")          # Playwright's keys come at scanner speed
    page.keyboard.press("Enter")
    assert _hits(page) == {}
    assert page.evaluate("window.__scans") == ["LOC:BIN-2"]
    # A person's Enter afterwards is a press again.
    page.keyboard.press("Enter")
    assert _hits(page) == {"plain": 1}


def test_a_key_a_person_left_goes_with_their_press(page50):
    page = page50
    _focus(page, "#plain")
    page.keyboard.type("x")
    page.wait_for_timeout(600)               # past isScanInFlight's 500 ms: a person's key
    page.keyboard.press("Enter")
    assert _hits(page) == {"plain": 1}
    assert page.evaluate("window.__scans") == []
    assert page.evaluate("() => state.scanBuffer") == ""


# --- a held Enter presses once --------------------------------------------------------

def test_a_held_enter_presses_once_and_answers_no_dialog_opened_under_it(page50):
    page = page50
    page.evaluate("""() => { document.getElementById('opener').onclick = () => {
        window.__hit('opener');
        window.mountOverlay({ id: 'fcc-test-q', initialFocus: '#q-yes',
            content: '<div><button id="q-yes" onclick="window.__hit(\\'qYes\\')">Yes</button></div>' });
    }; }""")
    _focus(page, "#opener")
    page.keyboard.down("Enter")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'q-yes'")
    page.keyboard.down("Enter")              # the held key's auto-repeats, now on the dialog's Yes
    page.keyboard.down("Enter")
    page.keyboard.up("Enter")
    assert _hits(page) == {"opener": 1}
    # A fresh press answers it.
    page.keyboard.press("Enter")
    assert _hits(page) == {"opener": 1, "qYes": 1}


def test_a_held_enter_never_answers_the_printing_question_and_it_opens_on_cancel(page50):
    """The printing yes / no answers Enter itself (its own key handler), so the
    repeat reached it whatever the accumulator did: it answered Continue Anyway
    while it opened on it. It opens on Cancel now (Derek, 2026-10-29), and the
    repeats of the Enter that opened it answer nothing."""
    page = page50
    page.evaluate("""() => { window.__said = null; document.getElementById('opener').onclick = () => {
        window.__hit('opener');
        window.confirmActivePrint({ activePrint: { printer_name: 'Printer A', state: 'PRINTING' },
            msg: 'Load #57 onto T-1?', onConfirm: () => { window.__said = 'yes'; },
            onCancel: () => { window.__said = 'no'; } });
    }; }""")
    _focus(page, "#opener")
    page.keyboard.down("Enter")
    page.wait_for_function("() => document.activeElement && document.activeElement.classList.contains('fcc-apc-no')")
    page.keyboard.down("Enter")
    page.keyboard.down("Enter")
    page.keyboard.up("Enter")
    assert page.evaluate("window.__said") is None
    assert page.locator("#fcc-active-print-confirm-overlay").count() == 1
    assert "Enter cancels" in page.locator("#fcc-active-print-confirm-overlay .fcc-apc-hint").inner_text()
    page.keyboard.press("Enter")             # a fresh press: the default, Cancel
    assert page.evaluate("window.__said") == "no"
    # Continue Anyway takes a deliberate Tab.
    page.evaluate("""() => { window.__said = null; window.confirmActivePrint({
        activePrint: { printer_name: 'Printer A', state: 'PRINTING' }, msg: 'Load #57 onto T-1?',
        onConfirm: () => { window.__said = 'yes'; }, onCancel: () => { window.__said = 'no'; } }); }""")
    page.wait_for_function("() => document.activeElement && document.activeElement.classList.contains('fcc-apc-no')")
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.classList.contains('fcc-apc-yes')")
    page.keyboard.press("Enter")
    assert page.evaluate("window.__said") == "yes"


def test_a_held_enter_in_a_text_box_answers_once_and_a_text_area_still_types_lines(page50):
    page = page50
    page.evaluate("""() => { window.__boxEnters = 0; document.getElementById('box').addEventListener('keydown',
        (e) => { if (e.key === 'Enter') window.__boxEnters += 1; }); }""")
    _focus(page, "#box")
    _hold_enter(page)
    assert page.evaluate("window.__boxEnters") == 1
    _focus(page, "#area")
    _hold_enter(page)
    assert page.evaluate("() => document.getElementById('area').value") == "\n\n\n"


# --- only where a mouse could click it now ---------------------------------------------

def test_enter_presses_nothing_behind_the_overlay_on_top(page50):
    page = page50
    _focus(page, "#plain")
    page.evaluate("() => { window.__ov = window.mountOverlay({ id: 'fcc-test-cover', content: '<div>Over it</div>' }); }")
    _focus(page, "#plain")                   # the focus left behind it
    page.keyboard.press("Enter")
    assert _hits(page) == {}
    page.evaluate("() => window.__ov.cleanup()")
    _focus(page, "#plain")
    page.keyboard.press("Enter")
    assert _hits(page) == {"plain": 1}


def test_enter_presses_nothing_while_a_scan_read_earlier_waits_to_go_out(page50):
    page = page50
    page.evaluate("() => { state.scanQueue.push({ text: 'ID:57', source: 'barcode', capturedAt: Date.now() }); }")
    _focus(page, "#plain")
    page.keyboard.press("Enter")
    assert _hits(page) == {}
    page.evaluate("() => { state.scanQueue.length = 0; }")
    page.keyboard.press("Enter")
    assert _hits(page) == {"plain": 1}


def test_enter_presses_nothing_in_a_window_fading_out(page50):
    page = page50
    _focus(page, "#in-modal")
    page.keyboard.press("Enter")
    assert _hits(page) == {"inModal": 1}
    page.evaluate("() => document.getElementById('someModal').classList.remove('show')")   # its fade-out
    page.keyboard.press("Enter")
    assert _hits(page) == {"inModal": 1}


def test_enter_presses_nothing_under_a_windows_own_inline_overlay(page50):
    """The delete flow's overlay covers its window but traps no Tab: while it
    shows, only its own buttons answer Enter; once it is hidden (its window's
    close hides it without its close()), the window's buttons do again."""
    page = page50
    page.evaluate("() => { document.getElementById('cover').style.display = 'block'; }")
    _focus(page, "#in-modal")
    page.keyboard.press("Enter")
    _focus(page, "#in-cover")
    page.keyboard.press("Enter")
    assert _hits(page) == {"inCover": 1}
    page.evaluate("() => { document.getElementById('cover').style.display = 'none'; }")
    _focus(page, "#in-modal")
    page.keyboard.press("Enter")
    assert _hits(page) == {"inCover": 1, "inModal": 1}


def test_enter_presses_nothing_in_a_gating_dialog_until_it_is_on_screen(page50):
    page = page50
    _focus(page, "#confirm-yes")
    page.keyboard.press("Enter")             # never "shown": a dialog still fading in
    assert _hits(page) == {}
    page.evaluate("() => document.getElementById('confirmModal').dispatchEvent(new Event('shown.bs.modal', { bubbles: true }))")
    page.keyboard.press("Enter")
    assert _hits(page) == {"confirmYes": 1}


# --- the Quick-Swap grid --------------------------------------------------------------

def test_the_grid_presses_the_focused_tile_never_a_stale_highlight(page50):
    page = page50
    page.evaluate("() => document.getElementById('tile-a').classList.add('kb-active')")
    # The focus on another button of the window: that one's Enter.
    _focus(page, "#mm-other")
    page.keyboard.press("Enter")
    assert _hits(page) == {"mmOther": 1}
    # The focus on another tile: that tile, not the highlighted one.
    _focus(page, "#tile-b")
    page.keyboard.press("Enter")
    assert _hits(page) == {"mmOther": 1, "tileB": 1}
    # The focus on the window itself: the highlighted tile, as before.
    page.evaluate("() => { document.querySelectorAll('.fcc-qs-slot').forEach((t) => t.classList.remove('kb-active'));"
                  " document.getElementById('tile-a').classList.add('kb-active'); }")
    _focus(page, "#manageModal")
    page.keyboard.press("Enter")
    assert _hits(page) == {"mmOther": 1, "tileB": 1, "tileA": 1}
    # The grid's section hidden (another location's view): nothing.
    page.evaluate("() => { document.getElementById('manage-quickswap-section').style.display = 'none'; }")
    _focus(page, "#manageModal")
    page.keyboard.press("Enter")
    assert _hits(page) == {"mmOther": 1, "tileB": 1, "tileA": 1}


# --- the settings window: tags and the import (Derek's answers) ---------------------------

REPORT = {"success": True, "choices": ["Matte"], "counts": {"Matte": 2}, "filaments": [],
          "hidden_choices": ["Silk"], "affected_records": 5}


def _attrs_page(page):
    page.evaluate("""(report) => { window.__answer = (url) => (url.indexOf('/api/filament_attributes/report') !== -1 ? report : {});
        window.__removed = []; window.__purged = [];
        window.configAttrsRemoveChoice = (c) => window.__removed.push(c);
        window.configAttrsPurgeChoice = (c) => window.__purged.push(c); }""", REPORT)
    page.evaluate("() => window.configAttrsScan()")
    page.wait_for_selector("#config-attrs-results .config-attrs-rm-choice")


def test_removing_a_tag_asks_in_an_overlay_that_opens_on_cancel(page50):
    page = page50
    _attrs_page(page)
    page.click("#config-attrs-results .config-attrs-rm-choice")
    page.wait_for_selector("#fcc-attr-remove-confirm")
    page.wait_for_function("() => document.activeElement && document.activeElement.dataset.dc === 'no'")
    assert "stripped from 2 filament(s)" in page.locator("#fcc-attr-remove-confirm").inner_text()
    page.keyboard.press("Enter")             # the default: Cancel
    page.wait_for_timeout(50)
    assert page.locator("#fcc-attr-remove-confirm").count() == 0
    assert page.evaluate("window.__removed") == []
    page.click("#config-attrs-results .config-attrs-rm-choice")
    page.wait_for_function("() => document.activeElement && document.activeElement.dataset.dc === 'no'")
    page.keyboard.press("Escape")
    page.wait_for_timeout(50)
    assert page.evaluate("window.__removed") == []
    page.click("#config-attrs-results .config-attrs-rm-choice")
    page.wait_for_function("() => document.activeElement && document.activeElement.dataset.dc === 'no'")
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.dataset.dc") == "yes"
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__removed.length === 1")
    assert page.evaluate("window.__removed") == ["Matte"]
    assert page.locator("#fcc-attr-remove-confirm").count() == 0


def test_a_held_enter_on_purge_purges_nothing(page50):
    """The browser's confirm() opened on OK, and the page can't stop a repeat
    that reaches it: a held Enter on 🗑 purge pressed the button, then OK."""
    page = page50
    _attrs_page(page)
    _focus(page, "#config-attrs-results .config-attrs-purge-choice")
    page.keyboard.down("Enter")
    page.wait_for_selector("#fcc-attr-purge-confirm")
    page.wait_for_function("() => document.activeElement && document.activeElement.dataset.dc === 'no'")
    page.keyboard.down("Enter")
    page.keyboard.down("Enter")
    page.keyboard.up("Enter")
    assert page.evaluate("window.__purged") == []
    assert page.locator("#fcc-attr-purge-confirm").count() == 1
    page.keyboard.press("Enter")             # a fresh press: Cancel
    page.wait_for_timeout(50)
    assert page.evaluate("window.__purged") == [] and page.locator("#fcc-attr-purge-confirm").count() == 0


def test_sweep_unused_tags_opens_on_cancel(page50):
    page = page50
    page.evaluate("() => { window.__answer = () => ({ success: true, unused: ['Old'], affected_records: 3 }); }")
    page.evaluate("() => window.configAttrsSweepUnused()")
    page.wait_for_selector("#fcc-sweep-unused-overlay")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'sweep-overlay-cancel'")
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    assert page.locator("#fcc-sweep-unused-overlay").count() == 0
    assert [f for f in page.evaluate("window.__fetches") if f["body"] and f["body"].get("force")] == []


DIFF = {"ok": True, "diff": [{"key": "fcc.x", "label": "A setting", "from": "1", "to": "2"}], "ignored": []}


def _choose_settings_file(page, dry):
    page.evaluate("""(dry) => { window.__answer = (url, body) => (body && body.dry_run ? dry : { ok: true, saved: ['fcc.x'] });
        window.wireImportExport(); }""", dry)
    page.set_input_files("#cfgio-file", files=[{"name": "settings.json", "mimeType": "application/json",
                                                 "buffer": json.dumps({"fcc.x": "2"}).encode()}])
    page.wait_for_selector("#fcc-config-import-overlay")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'cfgio-cancel'")


def _imports(page):
    return [f for f in page.evaluate("window.__fetches") if f["body"] and not f["body"].get("dry_run")]


@pytest.mark.parametrize("how", ["Enter", "Escape"])
def test_the_settings_import_opens_on_cancel_and_backing_out_says_nothing_was_imported(page50, how):
    page = page50
    _choose_settings_file(page, DIFF)
    page.keyboard.press(how)
    page.wait_for_timeout(50)
    assert page.locator("#fcc-config-import-overlay").count() == 0
    assert _imports(page) == []
    toasts = page.evaluate("window.__toasts")
    assert [t["t"] for t in toasts] == ["warning"] and toasts[0]["m"].startswith("Settings not imported"), toasts
    assert toasts[0]["ms"] >= 7000


def test_the_settings_import_applies_only_by_a_deliberate_press(page50):
    page = page50
    _choose_settings_file(page, DIFF)
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.id") == "cfgio-apply"
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__toasts.length === 1")
    assert len(_imports(page)) == 1
    assert page.evaluate("window.__toasts")[0]["m"] == "Imported 1 setting(s)"


def test_backing_out_of_an_import_with_nothing_to_change_says_nothing(page50):
    page = page50
    _choose_settings_file(page, {"ok": True, "diff": [], "ignored": []})
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    assert page.locator("#fcc-config-import-overlay").count() == 0
    assert page.evaluate("window.__toasts") == []
