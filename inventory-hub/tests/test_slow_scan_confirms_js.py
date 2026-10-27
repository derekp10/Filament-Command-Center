"""A slower scanner's Enter never answers a confirm (Group 57 review, round 4),
hermetic.

Runs the REAL scan accumulator (scripts.html's keydown block, lifted as
test_slow_scan_slash_js.py lifts it) with the REAL overlay_mount.js, inv_core.js
and inv_quickswap.js, and the REAL Shift+B block of inv_cmd.js and Shift+E /
Shift+C block of inv_wizard.js (each lifted as it is), in `isolated_page` (a
chromium with no route to any network), so it RUNS under --offline. The keys are
typed on a fake clock, one every `ms`, so a scanner's speed is exact whatever the
machine's load.

The defect (found in round 3, reproduced on dev in round 4): the Quick-Swap
confirm overlay's Enter (showConfirmOverlay: the swap, the deposit, the Return
and the server's re-ask) and the slot grid's Enter asked only isScanInFlight,
which counts 500 ms from a scan's FIRST key. The overlay's "Scan to Cancel" is
about 30 characters, so a scanner slower than about 17 ms a key was still typing
it, and its Enter pressed the focused YES: during a print, scanning the cancel
loaded a spool onto the printing head (POST /api/quickswap with the head in
confirmed_toolheads). After Q, a slow scan's Enter opened a swap nobody asked
for, and the next slow scan answered it. The shared move question
(window.confirmActivePrint) caught a slow payload only by its ':', so a slower
scanner's bare-number label ("57") answered its focused button: "Just store it".
Shift+B (Bulk Moves) fired on a slow label's 'B' and cut the scan, and the
wizard's Shift+E / Shift+C on its 'E' or 'C'. The grid's Q kept its 'q' in the
scan buffer (a label scanned within 2 s of it arrived as "qLOC:…") and took any
'q' inside a label for a person's.

Pinned, from 1 to 150 ms a key: the CANCEL scan cancels and the CONFIRM scan
confirms (through routeConfirmScan), nothing else; a person's Enter on YES
confirms and on NO cancels; after Q no slow scan opens or answers a swap, Q
leaves no 'q' behind, and a 'q' inside a label moves nothing; the
shared question's Enter never answers a slow scan, a bare number's included;
Shift+B and Shift+E / Shift+C never fire inside a slow label, and still do for a
person. RED on dd81587 (each test says from what speed).

Round 5 (RED on 91e79e8, each test says how): the person's side. Two Spaces a
button press left made a person's Enter on YES, on the grid or in the three-way
a scan of "  "; two keys a person left (the shortcut list's "??", a stray "12",
the wizard's own E and C) held off Q, Shift+B and the wizard's next toggle for
2 s; a key left in front of the confirm's own "Scan to Cancel" stopped it; Q,
then a digit, then Enter opened the swap and also put that spool in the scan
buffer. Pinned too: a one-key label never answers a confirm, and a label's 'E'
right after its first key never toggles the wizard (both were unpinned).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from test_slow_scan_slash_js import TYPE_JS, _accumulator

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
SPEEDS = [1, 8, 13, 18, 26, 40, 60, 150]

STUBS = r"""
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__posts = [];
window.__scans = [];
window.showToast = function () {};
window.fetch = function (url, opts) {
    url = String(url);
    if (opts && opts.method && opts.method !== 'GET') window.__posts.push({ url, body: opts.body ? JSON.parse(opts.body) : null });
    return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve('{}'),
                             json: () => Promise.resolve({ status: 'success', success: true }) });
};
// The scan path, as inv_cmd.js's processScan starts: a CMD:CONFIRM / CMD:CANCEL
// / CMD:STORE for an open dialog goes to it.
window.processScan = function (t) { window.__scans.push(t); if (window.routeConfirmScan) window.routeConfirmScan(t); };
"""

PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<div id="manageModal" class="modal show"><div id="quickswap-grid">
  <button class="fcc-qs-slot" data-toolhead="XL-1" data-box="LR-MDB-1" data-slot="1" data-spool-id="57">slot 1</button>
  <button class="fcc-qs-slot" data-toolhead="XL-1" data-box="LR-MDB-1" data-slot="2" data-spool-id="58">slot 2</button>
</div></div>
<div id="wizardModal" class="modal"><button id="wiz-btn">wizard</button></div>
<div id="fcc-shortcuts-overlay" style="display:none"><div id="fcc-shortcuts-list"></div></div>
</body></html>"""

# Answers the printer check as the page's own module would, after inv_core.js.
PRINTING_JS = """(printing) => { window.checkPrinterForHead = () => Promise.resolve(printing
    ? { active: true, known: true, state: 'PRINTING', printer_name: 'XL' }
    : { active: false, known: true, state: 'IDLE', printer_name: 'XL' }); }"""


def _block(path, start, end):
    """The source from `start` up to (not including) `end`, as it is."""
    src = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    a = src.index(start)
    return src[a:src.index(end, a)]


SHIFT_B = _block(MODULES / "inv_cmd.js", "(function () {\n    // Delegates to the canonical definition",
                 "// --- L298 Phase 3")
WIZARD_KEYS = _block(MODULES / "inv_wizard.js", "(function() {\n    if (window._wizExpandShortcutWired) return;",
                     "    // Register with the shortcuts registry") + "})();\n"


@pytest.fixture
def scan_page(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "inv_quickswap.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content=SHIFT_B)
    page.add_script_tag(content=WIZARD_KEYS)
    page.add_script_tag(content=_accumulator())          # last, as on the page
    page.evaluate("""() => { window.__bulk = 0; window.toggleBulkMove = () => { window.__bulk += 1; };
        window.__wiz = []; window.wizardExpandAllSections = () => window.__wiz.push('expand');
        window.wizardCollapseAllSections = () => window.__wiz.push('collapse'); }""")
    page.evaluate(PRINTING_JS, True)
    page.evaluate(TYPE_JS, ["", 0, False, {}])            # the fake clock, before anything is typed
    return page


def _type(page, text, ms, enter=True):
    page.evaluate(TYPE_JS, [text, ms, enter, {}])


def _fresh(page):
    """Nothing pending: no dialog, an empty buffer, no record, the clock moved on."""
    page.evaluate("""() => { if (window.closeQuickswapConfirm) window.closeQuickswapConfirm();
        document.querySelectorAll('[data-overlay-mount="1"]').forEach((n) => n.remove());
        window.__posts = []; window.__scans = []; window.__T += 5000;
        state.scanBuffer = ''; state.scanStartTime = 0; }""")


def _open_swap(page, slot=0):
    """The real tap on a slot, with XL-1 printing: the confirm with its QRs."""
    page.evaluate("(i) => window.quickSwapTap(document.querySelectorAll('.fcc-qs-slot')[i])", slot)
    page.wait_for_selector("#fcc-quickswap-confirm-overlay .fcc-confirm-qr-row", timeout=5000)
    return page.evaluate("() => Object.keys(window._fccActiveConfirms).slice(-1)[0]")


def _seen(page):
    return page.evaluate("""() => ({ posts: window.__posts.map((p) => p.url), scans: window.__scans.slice(),
        open: !!document.getElementById('fcc-quickswap-confirm-overlay'), buffer: state.scanBuffer,
        bodies: window.__posts.map((p) => p.body) })""")


@pytest.mark.parametrize("ms", SPEEDS)
def test_a_slow_scanners_cancel_never_confirms_a_swap(scan_page, ms):
    """XL-1 printing, the swap's confirm up with YES focused, and its own "Scan
    to Cancel" scanned: the swap is cancelled, and nothing is sent. RED on
    dd81587 from 18 ms a key: POST /api/quickswap with confirmed_toolheads
    ["XL-1"], and routeConfirmScan never saw the cancel."""
    page = scan_page
    _fresh(page)
    sid = _open_swap(page)
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "fcc-quickswap-yes"
    _type(page, f"CMD:CANCEL:{sid}", ms)
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["posts"] == [] and s["scans"] == [f"CMD:CANCEL:{sid}"] and not s["open"], (ms, s)


@pytest.mark.parametrize("ms", [1, 26, 150])
def test_a_slow_scanners_confirm_still_confirms_once(scan_page, ms):
    """The CONFIRM QR is the scan's own answer: it confirms through the scan
    path, once, with the printing head confirmed."""
    page = scan_page
    _fresh(page)
    sid = _open_swap(page)
    _type(page, f"CMD:CONFIRM:{sid}", ms)
    page.wait_for_function("() => window.__posts.length >= 1")
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["posts"] == ["/api/quickswap"] and s["scans"] == [f"CMD:CONFIRM:{sid}"], (ms, s)
    assert s["bodies"][0]["confirmed_toolheads"] == ["XL-1"], s


def test_a_persons_enter_still_answers_the_focused_button(scan_page):
    """Keyboard use is unaffected: Enter by hand finds the buffer empty. On YES
    it swaps; on NO (Tab) it cancels and sends nothing."""
    page = scan_page
    _fresh(page)
    _open_swap(page)
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__posts.length === 1")
    assert _seen(page)["posts"] == ["/api/quickswap"]
    _fresh(page)
    _open_swap(page)
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.id") == "fcc-quickswap-no"
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    s = _seen(page)
    assert s["posts"] == [] and not s["open"], s


@pytest.mark.parametrize("ms", [13, 26, 60])
def test_slow_scans_after_q_never_open_or_answer_a_swap(scan_page, ms):
    """Q puts the focus on the grid's first slot; then two spool QRs scanned
    slowly. Neither opens "Load LR-MDB-1 slot 1 into XL-1?", and both reach the
    scan path whole. RED on dd81587 at 26 ms a key: the first scan opened the
    confirm and the second, never reaching the scan path, performed it (POST
    /api/quickswap, nobody having pressed anything)."""
    page = scan_page
    _fresh(page)
    page.evaluate(PRINTING_JS, False)
    page.locator(".fcc-qs-slot").first.focus()
    page.keyboard.press("q")                         # its 'q' stays out of the scan buffer
    page.wait_for_timeout(50)
    url = "https://prusament.com/spool/17705/5b1a183b26/"
    for _ in range(2):
        _type(page, url, ms)
        page.wait_for_timeout(100)
    s = _seen(page)
    assert s["posts"] == [] and not s["open"] and s["scans"] == [url, url], (ms, s)
    # A person's Enter on the highlighted slot still opens it.
    page.evaluate("() => { window.__T += 3000; }")
    page.keyboard.press("Enter")
    page.wait_for_selector("#fcc-quickswap-confirm-overlay", timeout=5000)


def test_q_leaves_no_q_for_the_next_scan(scan_page):
    """Q jumps to the grid and keeps its 'q' out of the scan buffer: a label
    scanned straight after it arrives as it is. RED on dd81587: "qLOC:LR-MDB-1"
    (an unknown code) for 2 s after Q."""
    page = scan_page
    _fresh(page)
    page.locator(".fcc-qs-slot").nth(1).focus()
    page.keyboard.press("q")
    assert page.evaluate("() => document.activeElement.dataset.slot") == "1"     # the grid's first slot
    _type(page, "LOC:LR-MDB-1", 13)
    assert _seen(page)["scans"] == ["LOC:LR-MDB-1"]


@pytest.mark.parametrize("ms", [13, 60])
def test_a_q_inside_a_slow_label_moves_nothing(scan_page, ms):
    """A label with a 'q' in it (a confirm's session id has one), scanned with
    the grid up and no dialog: the focus stays where it was and the scan is
    whole. RED on dd81587 at every speed: Q had no scan check at all, and the
    'q' jumped the focus to the first slot."""
    page = scan_page
    _fresh(page)
    page.locator(".fcc-qs-slot").nth(1).focus()
    _type(page, "CMD:CANCEL:fcc-cqr-1-abc", ms)
    assert page.evaluate("() => document.activeElement.dataset.slot") == "2", ms
    assert _seen(page)["scans"] == ["CMD:CANCEL:fcc-cqr-1-abc"], ms


# The shared move question (window.confirmActivePrint), in its three-way:
# Load it instead / Just store it / Cancel, Enter storing. Records the answer.
THREE_WAY_JS = """() => { window.__answer = null;
    window.confirmActivePrint({ title: 'XL-1 is running #99', msg: 'Load #57 onto XL-1?',
        ids: { overlay: 'fcc-three-way-probe' },
        onConfirm: () => { window.__answer = 'load'; }, onStore: () => { window.__answer = 'store'; },
        onCancel: () => { window.__answer = 'cancel'; } }); }"""


@pytest.mark.parametrize("label", ["57", "1024", "LOC:LR-MDB-1"])
@pytest.mark.parametrize("ms", [1, 26, 60, 150, 250])
def test_the_shared_question_never_answers_a_slow_scan(scan_page, label, ms):
    """The three-way up (Enter would store), and a label scanned at every
    speed: the question stays unanswered and the label reaches the scan path.
    RED on dd81587 for a bare number whose Enter came 500 ms or more after its
    first key ("1024" at 150 ms a key, "57" at 250): "Just store it". (A label
    with a ':' was caught there already.)"""
    page = scan_page
    _fresh(page)
    page.evaluate(THREE_WAY_JS)
    page.wait_for_selector("#fcc-three-way-probe")
    _type(page, label, ms)
    page.wait_for_timeout(50)
    got = page.evaluate("() => ({ answer: window.__answer, scans: window.__scans.slice(),"
                        " open: !!document.getElementById('fcc-three-way-probe') })")
    assert got == {"answer": None, "scans": [label], "open": True}, (label, ms, got)
    page.evaluate("() => { window.__T += 3000; }")
    page.keyboard.press("Enter")                       # a person's Enter: the focused store
    assert page.evaluate("() => window.__answer") == "store"


@pytest.mark.parametrize("ms", [13, 26, 75, 150])
def test_shift_b_never_fires_inside_a_slow_label(scan_page, ms):
    """Nothing open, "LOC:LR-MDB-1" scanned: its 'B' is a Shift+B, and past the
    first 500 ms it armed a bulk move and cut the scan to "-1" (RED on
    dd81587 at 75 ms a key). A person's Shift+B still arms one."""
    page = scan_page
    _fresh(page)
    page.evaluate("() => { document.getElementById('manageModal').classList.remove('show'); document.activeElement.blur(); }")
    _type(page, "LOC:LR-MDB-1", ms)
    s = _seen(page)
    assert page.evaluate("() => window.__bulk") == 0 and s["scans"] == ["LOC:LR-MDB-1"], (ms, s)
    page.evaluate("() => { window.__T += 3000; }")
    page.keyboard.press("Shift+B")
    assert page.evaluate("() => window.__bulk") == 1


@pytest.mark.parametrize("ms", [13, 80, 150])
def test_the_wizards_shift_e_and_c_never_fire_inside_a_slow_label(scan_page, ms):
    """The wizard up with the focus on a button, "LOC:CR-CT-2-R1" scanned: its
    capital C's are Shift+C. Past the first 500 ms each collapsed the wizard's
    sections (RED on dd81587 at 80 ms a key). A person's Shift+E still
    expands them."""
    page = scan_page
    _fresh(page)
    page.evaluate("() => { document.getElementById('manageModal').classList.remove('show');"
                  " document.getElementById('wizardModal').classList.add('show'); document.getElementById('wiz-btn').focus(); }")
    _type(page, "LOC:CR-CT-2-R1", ms)
    assert page.evaluate("() => window.__wiz") == [] and _seen(page)["scans"] == ["LOC:CR-CT-2-R1"], ms
    page.evaluate("() => { window.__T += 3000; }")
    page.keyboard.press("Shift+E")
    assert page.evaluate("() => window.__wiz") == ["expand"]


# ---- Round 5: the person's side, and two unpinned scan rules -------------------------------------

def _wizard(page):
    """The wizard up with the focus on its button, nothing else open."""
    page.evaluate("() => { document.getElementById('manageModal').classList.remove('show');"
                  " document.getElementById('wizardModal').classList.add('show'); document.getElementById('wiz-btn').focus(); }")


def _q(page):
    """Q on the grid (the focus on slot 2): the focus goes to slot 1. A beat
    after, so Q's deferred buffer clear has run, as it has by the time a
    person's next key comes."""
    page.locator(".fcc-qs-slot").nth(1).focus()
    _type(page, "q", 10, enter=False)
    page.wait_for_timeout(20)


@pytest.mark.parametrize("ms", [1, 26, 150])
def test_a_one_key_label_never_answers_a_confirm(scan_page, ms):
    """A one-key label ("7", an old bare spool id) scanned at the Quick-Swap
    confirm (YES focused), onto the grid after Q, and at the three-way: its
    Enter is the scan's (it is in flight), so nothing is answered and "7"
    reaches the scan path. Unpinned until round 5: without enterIsAScan's
    in-flight rule every test stayed green, and "7" confirmed the swap."""
    page = scan_page
    _fresh(page)
    _open_swap(page)
    _type(page, "7", ms)
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["posts"] == [] and s["open"] and s["scans"] == ["7"], (ms, s)
    _fresh(page)
    page.evaluate(PRINTING_JS, False)
    _q(page)
    _type(page, "7", ms)
    page.wait_for_timeout(50)
    s = _seen(page)
    assert not s["open"] and s["scans"] == ["7"], (ms, s)
    _fresh(page)
    page.evaluate(THREE_WAY_JS)
    page.wait_for_selector("#fcc-three-way-probe")
    _type(page, "7", ms)
    page.wait_for_timeout(50)
    assert page.evaluate("() => window.__answer") is None and _seen(page)["scans"] == ["7"], ms


@pytest.mark.parametrize("left", ["x", " ", "x "])
def test_a_key_left_in_front_of_the_qrs_never_stops_them(scan_page, left):
    """A key a person pressed on the confirm (a stray letter, a Space, or
    both), then its own QR scanned a second later: "Scan to Cancel" cancels
    the swap and sends nothing, and the three-way's "Scan to Store" stores.
    RED on 91e79e8: the key sat in front of the payload, the anchored match
    missed it, and the dialog stayed up with nothing said."""
    page = scan_page
    _fresh(page)
    sid = _open_swap(page)
    _type(page, left, 100, enter=False)
    page.evaluate("() => { window.__T += 1000; }")
    _type(page, f"CMD:CANCEL:{sid}", 8)
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["posts"] == [] and not s["open"], (left, s)
    _fresh(page)
    page.evaluate(THREE_WAY_JS)
    page.wait_for_selector("#fcc-three-way-probe")
    sid = page.evaluate("() => Object.keys(window._fccActiveConfirms).slice(-1)[0]")
    _type(page, left, 100, enter=False)
    page.evaluate("() => { window.__T += 1000; }")
    _type(page, f"CMD:STORE:{sid}", 8)
    page.wait_for_timeout(50)
    assert page.evaluate("() => window.__answer") == "store", left


@pytest.mark.parametrize("left", ["  ", "x ", "x"])
def test_a_persons_enter_after_stray_keys_answers_the_dialog(scan_page, left):
    """Two Spaces pressed on a button (they press nothing here; a tile that
    takes no Space is the real case), a stray letter and a Space, or a stray
    letter, then a person's Enter 0.7 s later: YES swaps, the grid's
    highlighted slot opens its confirm, and the three-way stores, each on the
    first Enter, and the keys go with it (they would start the next scan). RED
    on 91e79e8: the blanks stayed in the scan buffer and counted, so the Enter
    was taken for a scan of "  " or "x " and lost; and the letter stayed."""
    page = scan_page
    _fresh(page)
    _open_swap(page)
    _type(page, left, 300, enter=False)
    _type(page, "", 700)
    page.wait_for_function("() => window.__posts.length === 1", timeout=3000)
    assert _seen(page)["buffer"] == "", left
    _fresh(page)
    page.evaluate(PRINTING_JS, False)
    _q(page)
    _type(page, left, 300, enter=False)
    _type(page, "", 700)
    page.wait_for_selector("#fcc-quickswap-confirm-overlay", timeout=3000)
    page.wait_for_timeout(20)
    assert (_seen(page)["buffer"], _seen(page)["scans"]) == ("", []), left
    _fresh(page)
    page.evaluate(THREE_WAY_JS)
    page.wait_for_selector("#fcc-three-way-probe")
    _type(page, left, 300, enter=False)
    _type(page, "", 700)
    page.wait_for_timeout(20)
    assert page.evaluate("() => window.__answer") == "store", left
    assert (_seen(page)["buffer"], _seen(page)["scans"]) == ("", []), left


def test_a_legacy_labels_question_mark_never_opens_the_shortcut_list(scan_page):
    """A legacy Google Sheets label is a URL with a '?' after its "https:".
    Scanned slowly, with the scanner pausing 200 ms (real time: the list waits
    120 ms for a next key) right after the '?': the list stays shut and the
    scan arrives whole. RED on 91e79e8: the '?' asked only whether a scan was
    in flight (500 ms from its first key), so the list opened over the scan."""
    page = scan_page
    page.add_script_tag(content=(MODULES / "shortcuts_registry.js").read_text(encoding="utf-8"))
    _fresh(page)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    url = "https://docs.google.com/spreadsheets/d/1AbC/edit?gid=304905527#gid=304905527&range=98:98"
    at = url.index("?") + 1
    _type(page, url[:at], 26, enter=False)
    page.wait_for_timeout(200)
    _type(page, url[at:], 26)
    assert page.evaluate("() => document.getElementById('fcc-shortcuts-overlay').style.display") != "block"
    assert _seen(page)["scans"] == [url]


def test_keys_a_person_left_never_stop_q_shift_b_or_the_wizard(scan_page):
    """Two keys a person pressed and left ("??", "12"), then Q 0.6 s later:
    the focus goes to the grid; then Shift+B 0.6 s after "12" with nothing
    open: a bulk move arms; the wizard's Shift+E, Shift+C, Shift+E, Shift+C
    0.6 s apart: all four act (the wizard keeps its own keys in the buffer, so
    a label's first key is never cut). RED on 91e79e8: any two characters in
    the buffer held these keys off for 2 s, and each blocked press restarted
    it."""
    page = scan_page
    _fresh(page)
    page.locator(".fcc-qs-slot").nth(1).focus()
    _type(page, "??", 600, enter=False)
    _type(page, "q", 600, enter=False)
    assert page.evaluate("() => document.activeElement.dataset.slot") == "1"
    assert _seen(page)["buffer"] == ""
    _fresh(page)
    page.evaluate("() => { document.getElementById('manageModal').classList.remove('show'); document.activeElement.blur(); }")
    _type(page, "12", 600, enter=False)
    _type(page, "B", 600, enter=False)
    assert page.evaluate("() => window.__bulk") == 1
    _fresh(page)
    _wizard(page)
    _type(page, "ECEC", 600, enter=False)
    assert page.evaluate("() => window.__wiz") == ["expand", "collapse", "expand", "collapse"]


def test_the_help_key_takes_its_question_marks_back(scan_page):
    """'?' opens the shortcut list and '?' closes it (nothing followed either
    within 120 ms, so both were a person's): neither stays in the scan buffer,
    and Q 0.6 s later moves the focus to the grid. RED on 91e79e8: "??" stayed
    for 2 s, held Q off, and a person's next Enter scanned it."""
    page = scan_page
    page.add_script_tag(content=(MODULES / "shortcuts_registry.js").read_text(encoding="utf-8"))
    _fresh(page)
    shown = "document.getElementById('fcc-shortcuts-overlay').style.display"
    page.locator(".fcc-qs-slot").nth(1).focus()
    _type(page, "?", 10, enter=False)
    page.wait_for_function(f"() => {shown} === 'block'", timeout=3000)
    assert _seen(page)["buffer"] == ""
    _type(page, "?", 600, enter=False)
    page.wait_for_function(f"() => {shown} === 'none'", timeout=3000)
    assert _seen(page)["buffer"] == ""
    _type(page, "q", 600, enter=False)
    assert page.evaluate("() => document.activeElement.dataset.slot") == "1"


def test_q_then_a_digit_then_enter_opens_the_swap_and_nothing_else(scan_page):
    """Q, then 2 (a person expecting slot 2), then Enter 0.7 s later: the
    highlighted slot's confirm opens, and the "2" goes nowhere. RED on 91e79e8:
    the grid's Enter left the event to the accumulator too, which submitted
    "2" (on dev, spool #2 into the scan buffer, unseen behind the dialog)."""
    page = scan_page
    _fresh(page)
    page.evaluate(PRINTING_JS, False)
    _q(page)
    _type(page, "2", 300, enter=False)
    _type(page, "", 700)
    page.wait_for_selector("#fcc-quickswap-confirm-overlay", timeout=3000)
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["scans"] == [] and s["buffer"] == "", s


@pytest.mark.parametrize("ms", [13, 80])
def test_a_labels_e_right_after_its_first_key_never_toggles_the_wizard(scan_page, ms):
    """"LEG:120" with the wizard up: its 'E' is a Shift+E one key in, with
    nothing in the buffer that looks like a scan yet, so only the in-flight
    rule keeps it the scan's. Unpinned until round 5 (scanIsArriving without it
    kept every test green, and the 'E' expanded the wizard)."""
    page = scan_page
    _fresh(page)
    _wizard(page)
    _type(page, "LEG:120", ms)
    assert page.evaluate("() => window.__wiz") == [] and _seen(page)["scans"] == ["LEG:120"], ms
