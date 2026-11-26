"""The review of Group 62 (2026-11-17), the fixes with no other home, hermetic.

- Return's "nothing to return" notices hold off no scan. 62.2 made the Quick-Swap
  confirm a question that holds off every other scan until it is answered, and its
  notices ("Nothing to return on XL", a head whose spool has no box to go back to) are
  drawn by the same overlay: every scan was refused with "Answer the question on screen
  first: Yes, swap or No, cancel" under words that ask nothing, as before 62.2 none was.
  inv_quickswap.js's showConfirmOverlay takes `notice: true` for them now.
- A scan a text box's capture sends on stamps its Enter (inv_core.js's
  installFieldScanCapture): it never set `state.lastScanEnterAt`, which only the scan
  accumulator set, and the accumulator skips keys typed into a box. So a scanner set to
  end with CR LF had its second Enter read as a person's, which in the delete question's
  typed box pressed Delete forever.

The real modules: inv_quickswap.js under node (test_core1_return_ejectall_js.py's
driver), and inv_core.js in `isolated_page` with real keys. RED before the review's
fixes unless a test says it pins what was right.
"""
from __future__ import annotations

import pytest

from test_core1_return_ejectall_js import _return_scenario, pytestmark, run_js  # noqa: F401
from test_slow_scan_confirms_js import MODULES


def _held_after_return(tmp_path, row, loaded, spools=None):
    base = _return_scenario(row, loaded, spools)
    cut = base.index("const overlays = __rec.overlays")
    res = run_js(tmp_path, ["inv_quickswap.js"], base[:cut] + """
const q = window._fccOpenMoveQuestions || [];
return { overlays: __rec.overlays.map(o => o.content), held: q.length, top: !!window._fccOpenMoveQuestion };
""")
    assert res["unhandled"] == [], res["unhandled"]
    return res


@pytest.mark.parametrize("row, loaded, words", [
    ("XL", {}, "Nothing to return on XL"),
    ("XL", {"XL-2": 913}, "Return the spool on XL-2?"),
], ids=["printer-with-nothing-loaded", "head-with-no-box-to-go-back-to"])
def test_returns_notices_hold_off_no_scan(tmp_path, row, loaded, words):
    """RED before the review's fix: each held scans off (held 1)."""
    res = _held_after_return(tmp_path, row, loaded)
    assert any(words in c for c in res["overlays"]), res["overlays"]
    assert res["held"] == 0 and res["top"] is False, res


def test_a_returns_real_question_still_holds_scans_off(tmp_path):
    """A pin (62.2): "Return the spool on CORE1?", with a box to go back to, asks."""
    res = _held_after_return(tmp_path, "CORE1", {"CORE1": 912},
                             {"912": {"physical_source": '"CR-DB-1"', "physical_source_slot": '"2"'}})
    assert any("Return the spool on CORE1?" in c for c in res["overlays"]), res["overlays"]
    assert res["held"] == 1 and res["top"] is True, res


# --- the field capture stamps a scan's Enter -------------------------------------------

PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<input id="labelled" type="text"><input id="plain" type="text">
</body></html>"""

STUBS = r"""
window.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}), text: () => Promise.resolve('{}') });
window.__si = window.setInterval; window.setInterval = () => 0;
"""


@pytest.fixture
def boxes(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("""() => {
        window.setInterval = window.__si;
        window.__scans = [];
        window.processScan = (t, src) => { window.__scans.push([t, src]); };
        // When each Enter was pressed, on the window, before any document listener.
        window.addEventListener('keydown', (e) => { if (e.key === 'Enter') window.__enterAt = Date.now(); }, true);
        window.installFieldScanCapture({ match: (el) => el.id === 'labelled', isScanPayload: () => true, labels: true });
        window.installFieldScanCapture({ match: (el) => el.id === 'plain', isScanPayload: () => true });
    }""")
    return page


def _stamp(page):
    return page.evaluate("""() => { const st = (typeof state !== 'undefined') ? state : window.state;
        return { at: st.lastScanEnterAt || null, enter: window.__enterAt || null, scans: window.__scans.slice() }; }""")


@pytest.mark.parametrize("box, text", [("#labelled", "ID:57"), ("#labelled", "8812"), ("#plain", "ID:57")],
                         ids=["a-label", "digits-alone", "a-burst-in-a-plain-box"])
def test_a_scan_the_capture_sends_on_stamps_its_enter(boxes, box, text):
    """RED before the review's fix: no stamp, so enterIsAScan() read the CR LF scanner's
    second Enter, 100 ms later at most, as a person's."""
    page = boxes
    page.focus(box)
    page.keyboard.type(text, delay=5)
    page.keyboard.press("Enter")
    got = _stamp(page)
    assert got["scans"] and got["scans"][-1][0] == text, got
    assert got["at"] is not None and abs(got["at"] - got["enter"]) < 50, got


def test_a_persons_typing_and_enter_stamps_nothing(boxes):
    """A pin: a person's Enter in a box is theirs."""
    page = boxes
    page.focus("#labelled")
    page.keyboard.type("Shelf 2", delay=120)
    page.keyboard.press("Enter")
    got = _stamp(page)
    assert got["scans"] == [] and got["at"] is None, got


# The page's clock moves only when a test says (Date.now), so a scanner's pace is exact.
FAKE_CLOCK = r"""() => { const base = Date.now(); window.__T = 0; Date.now = () => base + window.__T; }"""


@pytest.mark.parametrize("box, text", [("#labelled", "ID:57"), ("#labelled", "8812"), ("#plain", "ID:57")],
                         ids=["a-label", "digits-alone", "a-burst-in-a-plain-box"])
def test_a_scanners_second_enter_never_reaches_the_box(boxes, box, text):
    """The second review round (2026-11-17): a scanner set to end with CR LF sends two
    Enters. The capture took the scan and its first; the second reached the box's own
    Enter handler, which saved, searched or pressed there unless it asked enterIsAScan.
    The capture takes it too now. A person's Enter a moment later is theirs (a pin). RED
    before the fix: the box heard the second Enter."""
    page = boxes
    page.evaluate(FAKE_CLOCK)
    page.evaluate("""(sel) => { window.__boxEnters = 0;
        document.querySelector(sel).addEventListener('keydown', (e) => { if (e.key === 'Enter') window.__boxEnters += 1; }); }""", box)
    page.focus(box)
    for ch in text:
        page.evaluate("() => { window.__T += 5; }")
        page.keyboard.type(ch)
    page.evaluate("() => { window.__T += 5; }")
    page.keyboard.press("Enter")                    # its CR
    page.evaluate("() => { window.__T += 3; }")
    page.keyboard.press("Enter")                    # its LF
    got = page.evaluate("() => ({ enters: window.__boxEnters, scans: window.__scans.map((s) => s[0]) })")
    assert got["scans"] == [text] and got["enters"] == 0, got
    page.evaluate("() => { window.__T += 400; }")
    page.keyboard.press("Enter")
    assert page.evaluate("() => window.__boxEnters") == 1


# --- the ⌨️ list names the two new codes -------------------------------------------------

def test_the_shortcut_list_names_the_two_new_codes_and_says_what_done_does_now():
    """The list's Scan Commands are the codes' own reference: 62.6's CMD:DEPOSIT:<place>
    and 62.7's CMD:CLOSE weren't in it, and CMD:DONE read as the location window's own
    Done (whose QR is CMD:CLOSE now) and left out the bulk move it commits. With no audit
    or bulk move running it still closes that window (the server answers `done`, and the
    page runs closeManage). RED before the review's fix."""
    import re
    src = (MODULES / "shortcuts_registry.js").read_text(encoding="utf-8")
    assert "keys: ['CMD:CLOSE']" in src
    assert "keys: ['CMD:DEPOSIT:<place>']" in src
    done = re.search(r"id: 'scan-cmd-done',.*?description: '((?:[^'\\]|\\.)*)'", src, re.S).group(1)
    assert "bulk move" in done and "audit" in done, done
