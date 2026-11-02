"""Group 58.4, the page half: window.openLooseList, the 🧺 Loose spools list.

Hermetic: the REAL overlay_mount.js, inv_core.js and inv_loose.js, the real
global.css and the real Locations window template in `isolated_page` (no network),
so it runs under --offline. `fetch` answers /api/loose_spools in the route's real
shape (one test feeds it the route's own answer); window.openManage is a recorder.

Pinned: one list of every place and its spools, rows at the named size, arrows move
.kb-active and wrap, Enter or a click opens the place outside an audit and nothing
during one, Escape closes only the list, a read that failed shows the yellow notice
with Try again and never "no loose spools", the tiers (standard, and confirm over
another overlay), a scan's Enter left to the scan path, a window opened meanwhile,
stale answers, escaping, and contrast in every state.

The same list over the real dashboard: test_loose_spools_58_4_e2e.py,
test_contrast_guard.py and test_text_size_guard.py (they need the container).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import contrast_offenders
from test_loose_spools_58_4 import _ask, _Spoolman, _wire

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
GLOBAL_CSS = HUB / "static" / "css" / "global.css"
LOC_TEMPLATE = HUB / "templates" / "components" / "modals_loc_mgr.html"
SCRIPTS = HUB / "templates" / "components" / "scripts.html"
OVERLAY = "#fcc-loose-list"
PANEL = OVERLAY + " .fcc-loose-panel"
BODY = OVERLAY + " [data-loose-body]"
ROW = OVERLAY + " .fcc-loose-row"
ACTIVE = ROW + ".kb-active"
NOTICE = OVERLAY + " [data-loose-notice]"
RETRY = OVERLAY + " [data-loose-retry]"

PRELUDE = r"""
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__fetches = [];
window.__answers = [];
window.__opened = [];
window.__toasts = [];
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.addEventListener('unhandledrejection', (e) => window.__errors.push(String(e.reason)));
window.fetch = function (url, opts) {
    window.__fetches.push([String(url), (opts && opts.method) || 'GET']);
    const a = window.__answers.length > 1 ? window.__answers.shift() : window.__answers[0];
    const go = () => {
        if (!a || a.network) return Promise.reject(new TypeError('Failed to fetch'));
        return Promise.resolve({
            ok: a.status >= 200 && a.status < 300, status: a.status,
            json: () => (a.badJson ? Promise.reject(new SyntaxError('Unexpected token <'))
                                   : Promise.resolve(JSON.parse(JSON.stringify(a.body)))),
        });
    };
    if (a && a.hold) return new Promise((r) => { window.__release = () => r(go()); });
    return go();
};
window.openManage = function (id) { window.__opened.push(id); };
"""


def _spool(sid, display, grams=500.0, color="72071C", direction="longitudinal"):
    return {"id": sid, "display": display, "color": color, "color_direction": direction,
            "remaining_weight": grams}


LOOSE = {"read_ok": True, "read_error": None, "count": 3, "places": [
    {"id": "CR", "name": "Computer Room", "type": "Room", "spools": [_spool(86, "#86 Elegoo PLA (Gray)", 921.43)]},
    {"id": "CR-CT-1", "name": "Computer Room Cart 1", "type": "Cart", "spools": [
        _spool(15, "#15 Elegoo PETG (Orange)", 969.0),
        _spool(16, "#16 Sunlu PLA (Two Tone)", None, color="BA0C2F,0047BB", direction="coaxial")]},
]}
EMPTY = {"read_ok": True, "read_error": None, "count": 0, "places": []}
DOWN = {"read_ok": False, "read_error": "couldn't read Spoolman (Spoolman didn't answer (test))",
        "count": 0, "places": []}


def _answer(body, status=200, **kw):
    a = {"status": status, "body": body}
    a.update(kw)
    return a


@pytest.fixture
def loose(isolated_page):
    """The page with the real modules; returns (page, open(answers..., by the
    Locations window's real button unless click=False))."""
    page = isolated_page
    page.set_content('<!doctype html><html><head><meta charset="utf-8"><style>'
                     + GLOBAL_CSS.read_text(encoding="utf-8") + '</style></head><body>'
                     + LOC_TEMPLATE.read_text(encoding="utf-8")
                     + '<div id="manageModal" class="modal"></div><div id="elsewhere" tabindex="0">x</div></body></html>')
    page.add_script_tag(content=PRELUDE)
    for name in ("overlay_mount.js", "inv_core.js", "inv_loose.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("""() => {
        window.showToast = (msg, type, ms) => window.__toasts.push({ msg, type, ms });
        document.getElementById('locMgrModal').classList.add('show');
        state.locationsLoaded = true;
        state.allLocations = [{ LocationID: 'CR' }, { LocationID: 'CR-CT-1' }];
    }""")

    def _open(*answers, click=True, opts=None):
        page.evaluate("(a) => { window.__answers = a; }", list(answers))
        if click:
            page.locator("#loc-loose-list-btn").click()
        else:
            page.evaluate("(o) => { window.openLooseList(o); }", opts)
        page.wait_for_selector(PANEL)

    return page, _open


def _state(page):
    return page.locator(BODY).get_attribute("data-loose-state")


def _wait_state(page, name):
    page.wait_for_function(
        "(n) => { const b = document.querySelector(" + json.dumps(BODY) + "); return b && b.dataset.looseState === n; }",
        arg=name, timeout=5000)


def _active(page):
    return page.locator(ACTIVE).get_attribute("data-spool")


def _no_errors(page):
    assert page.evaluate("window.__errors") == []


# --- the list -----------------------------------------------------------------------


def test_every_place_and_its_spools(loose):
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    drawn = page.evaluate("""(sel) => Array.from(document.querySelector(sel).children).map((el) =>
        el.classList.contains('fcc-loose-place')
            ? ['place', el.dataset.loosePlace, el.querySelector('.fcc-loose-place-name').textContent,
               el.querySelector('.fcc-loose-tag').textContent, el.querySelector('.fcc-loose-count').textContent]
            : ['spool', el.dataset.spool, el.dataset.place, el.querySelector('.fcc-loose-name').textContent,
               el.querySelector('.fcc-loose-grams').textContent])""", BODY)
    assert drawn == [
        ["place", "CR", "Computer Room", "Room", "1"],
        ["spool", "86", "CR", "#86 Elegoo PLA (Gray)", "921 g"],
        ["place", "CR-CT-1", "Computer Room Cart 1", "Cart", "2"],
        ["spool", "15", "CR-CT-1", "#15 Elegoo PETG (Orange)", "969 g"],
        ["spool", "16", "CR-CT-1", "#16 Sunlu PLA (Two Tone)", "? g"],
    ]
    assert page.locator(OVERLAY + " [data-loose-sub]").inner_text().startswith("3 spools in 2 places, filed at")
    assert "Enter opens the place" in page.locator(OVERLAY + " [data-loose-foot]").inner_text()
    _no_errors(page)


def test_the_routes_own_answer_draws(loose):
    """The contract: the REAL route's JSON, not a hand-made sample."""
    res = _ask(_Spoolman([_wire(57, "LR", name="Gold"), _wire(58, "Old Shelf"), _wire(59, "CR-CT-1-R1")]))
    page, open_list = loose
    open_list(_answer(res.get_json()))
    _wait_state(page, "ready")
    assert page.locator(ROW).count() == 2
    assert page.locator(ROW).first.inner_text().split("\n")[0] == "#57 Some Brand PLA (Gold)"
    tags = page.locator(OVERLAY + " .fcc-loose-tag").all_inner_texts()
    assert tags == ["Room", "not in Locations"]              # a place with no row says so
    # A place with no name of its own shows its id once.
    assert page.locator(OVERLAY + " [data-loose-place='Old Shelf'] .fcc-loose-place-name").count() == 0
    _no_errors(page)


def test_it_reads_once_and_writes_nothing(loose):
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    assert page.evaluate("window.__fetches") == [["/api/loose_spools", "GET"]]


def test_rows_use_the_named_size(loose):
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    sizes = page.evaluate("""(row) => {
        const px = (el) => parseFloat(getComputedStyle(el).fontSize);
        const probe = document.createElement('div');
        probe.style.fontSize = 'var(--fcc-fs-row)';
        document.body.appendChild(probe);
        const named = px(probe);
        probe.remove();
        return { named, row: px(document.querySelector(row)) };
    }""", ROW)
    assert sizes["row"] == sizes["named"] == pytest.approx(14.4)


def test_a_bad_colour_keeps_its_row(loose):
    page, open_list = loose
    open_list(_answer({**EMPTY, "count": 1, "places": [
        {"id": "CR", "name": "CR", "type": "Room", "spools": [_spool(1, "#1 Odd", color="not a colour")]}]}))
    _wait_state(page, "ready")
    assert page.locator(ROW).count() == 1


# --- keys ---------------------------------------------------------------------------


def test_arrows_move_the_highlight_and_wrap(loose):
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    assert _active(page) == "86"
    assert page.evaluate("document.activeElement.dataset.spool") == "86"       # the list opens on its first row
    page.keyboard.press("ArrowDown")
    assert _active(page) == "15"
    page.keyboard.press("ArrowDown")
    assert _active(page) == "16"
    page.keyboard.press("ArrowDown")
    assert _active(page) == "86"                                               # wraps past the end
    page.keyboard.press("ArrowUp")
    assert _active(page) == "16"                                               # and before the start
    assert page.locator(ACTIVE).count() == 1
    assert page.evaluate("document.activeElement.dataset.spool") == "16"


def test_enter_opens_the_rows_place_and_the_list_gives_way(loose):
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == ["CR-CT-1"]
    assert page.locator(OVERLAY).count() == 0
    _no_errors(page)


def test_a_click_opens_the_place(loose):
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    page.locator(ROW).nth(2).click()
    assert page.evaluate("window.__opened") == ["CR-CT-1"]
    assert page.locator(OVERLAY).count() == 0


def test_a_place_opens_by_the_rows_own_spelling(loose):
    """openManage finds its row by LocationID, exactly."""
    page, open_list = loose
    page.evaluate("() => { state.allLocations = [{ LocationID: 'Old Shelf' }]; }")
    open_list(_answer({**EMPTY, "count": 1, "places": [
        {"id": "OLD SHELF", "name": "OLD SHELF", "type": "", "spools": [_spool(1, "#1 x")]}]}))
    _wait_state(page, "ready")
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == ["Old Shelf"]


def test_a_place_the_location_list_lacks_says_so_and_keeps_the_list(loose):
    """openManage bails with no word for an id it can't find."""
    page, open_list = loose
    page.evaluate("() => { state.allLocations = []; }")
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == []
    assert page.locator(OVERLAY).count() == 1
    toast = page.evaluate("window.__toasts")
    assert len(toast) == 1 and toast[0]["type"] == "warning" and toast[0]["ms"] == 7000
    assert "CR" in toast[0]["msg"]


def test_a_place_still_loading_is_left_to_openManage(loose):
    """Its first /api/locations load still on the way: openManage parks the open."""
    page, open_list = loose
    page.evaluate("() => { state.locationsLoaded = false; state.allLocations = []; }")
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == ["CR"]


def test_during_an_audit_a_row_opens_nothing(loose):
    """The place would open behind the audit panel."""
    page, open_list = loose
    page.evaluate("() => { state.auditActive = true; }")
    open_list(_answer(LOOSE), click=False, opts={"tier": "confirm"})
    _wait_state(page, "ready")
    page.keyboard.press("ArrowDown")
    assert _active(page) == "15"                                               # the arrows still read the list
    page.keyboard.press("Enter")
    page.locator(ROW).nth(2).click()
    assert page.evaluate("window.__opened") == []
    assert page.locator(OVERLAY).count() == 1
    assert "Enter" not in page.locator(OVERLAY + " [data-loose-foot]").inner_text()
    assert page.locator(ROW).first.get_attribute("aria-disabled") == "true"
    assert page.locator(ROW).first.get_attribute("role") is None
    _no_errors(page)


def test_an_audit_started_with_the_list_open_stops_enter_too(loose):
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    page.evaluate("() => { state.auditActive = true; }")
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == []


def test_escape_closes_only_the_list(loose):
    page, open_list = loose
    page.evaluate("""() => {
        window.__hostKeys = [];
        document.getElementById('locMgrModal').addEventListener('keydown', (e) => window.__hostKeys.push(e.key));
        document.addEventListener('keydown', (e) => window.__hostKeys.push('doc:' + e.key));
    }""")
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    page.keyboard.press("Escape")
    assert page.locator(OVERLAY).count() == 0
    assert page.evaluate("document.getElementById('locMgrModal').classList.contains('show')") is True
    assert page.evaluate("window.__hostKeys") == []                            # Bootstrap never sees it
    assert page.evaluate("document.activeElement.id") == "loc-loose-list-btn"  # the focus comes back
    assert page.evaluate("window.__opened") == []


def test_the_close_button_and_the_backdrop_close_it(loose):
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    page.locator(OVERLAY + " [data-loose-close]").click()
    assert page.locator(OVERLAY).count() == 0
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    page.wait_for_timeout(450)                                                 # past a double click's second click
    page.mouse.click(5, 5)
    assert page.locator(OVERLAY).count() == 0


def test_the_second_click_of_a_double_click_does_not_close_it(loose):
    page, open_list = loose
    page.evaluate("(a) => { window.__answers = a; }", [_answer(LOOSE)])
    box = page.locator("#loc-loose-list-btn").bounding_box()
    page.mouse.dblclick(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_selector(PANEL)
    _wait_state(page, "ready")
    assert page.locator(OVERLAY).count() == 1


def test_a_scans_enter_is_the_scan_paths(loose):
    """Keys in the scan buffer: the Enter ends that scan, it opens nothing."""
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    page.evaluate("() => { state.scanBuffer = 'LOC:CR'; state.scanStartTime = Date.now(); }")
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == []
    assert page.locator(OVERLAY).count() == 1


def test_a_person_may_not_press_under_the_press_rule(loose):
    """window.personMayPress says no (a scan still queued, say): nothing opens."""
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    page.evaluate("() => { window.personMayPress = () => false; }")
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == []
    assert page.locator(OVERLAY).count() == 1


def test_something_over_the_list_owns_the_keys(loose):
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    page.evaluate("""() => { window.mountOverlay({ id: 'over-it', tier: 'confirm', content: '<div>over</div>' }); }""")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert _active(page) == "86" and page.evaluate("window.__opened") == []
    page.keyboard.press("Escape")                                              # the one on top
    assert page.locator("#over-it").count() == 0 and page.locator(OVERLAY).count() == 1


def test_a_window_opened_meanwhile_closes_the_list(loose):
    """A scan's window opens under this panel, where nobody could see it."""
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    page.evaluate("() => document.getElementById('manageModal').dispatchEvent(new Event('show.bs.modal', { bubbles: true }))")
    assert page.locator(OVERLAY).count() == 0
    page.keyboard.press("ArrowDown")                                           # its keys went with it
    _no_errors(page)


def test_it_closes_with_its_host(loose):
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    page.evaluate("() => document.getElementById('locMgrModal').dispatchEvent(new Event('hidden.bs.modal'))")
    assert page.locator(OVERLAY).count() == 0


# --- reads --------------------------------------------------------------------------


def _assert_notice(page):
    notice = page.locator(NOTICE)
    assert notice.get_attribute("role") == "alert"
    colours = notice.evaluate("""(el) => { const s = getComputedStyle(el);
        return [s.color, s.backgroundColor, s.borderTopColor]; }""")
    assert colours == ["rgb(255, 213, 74)", "rgb(43, 34, 0)", "rgb(255, 213, 74)"]    # the approved yellow notice
    assert page.locator(RETRY).is_visible()
    assert page.evaluate("document.activeElement.hasAttribute('data-loose-retry')")
    text = page.locator(BODY).inner_text().lower()
    assert "not an empty list" in text
    assert "no loose" not in text and page.locator(ROW).count() == 0
    assert page.locator(OVERLAY + " [data-loose-foot]").inner_text() == "Esc closes"   # no row to promise


def test_a_failed_read_shows_the_notice_with_try_again(loose):
    page, open_list = loose
    open_list(_answer(DOWN), _answer(LOOSE))
    _wait_state(page, "error")
    _assert_notice(page)
    assert "Spoolman didn't answer" in page.locator(NOTICE).inner_text()
    assert "(test)" in page.locator(NOTICE).get_attribute("title")             # the why, for a hover
    page.locator(RETRY).click()
    _wait_state(page, "ready")
    assert page.locator(ROW).count() == 3 and page.locator(NOTICE).count() == 0
    assert _active(page) == "86"
    assert len(page.evaluate("window.__fetches")) == 2


@pytest.mark.parametrize("failed", [{"network": True}, _answer(None, status=500, badJson=True),
                                    _answer({"unexpected": 1})],
                         ids=["no connection", "an error page", "an unknown shape"])
def test_no_answer_from_fcc_is_never_an_empty_list(loose, failed):
    page, open_list = loose
    open_list(failed)
    _wait_state(page, "error")
    _assert_notice(page)
    assert "FCC didn't answer" in page.locator(NOTICE).inner_text()


def test_enter_presses_try_again(loose):
    page, open_list = loose
    open_list(_answer(DOWN), _answer(LOOSE))
    _wait_state(page, "error")
    page.keyboard.press("Enter")
    _wait_state(page, "ready")


def test_a_good_empty_read_says_so(loose):
    page, open_list = loose
    open_list(_answer(EMPTY))
    _wait_state(page, "empty")
    assert "No loose spools" in page.locator(BODY).inner_text()
    assert page.locator(NOTICE).count() == 0 and page.locator(ROW).count() == 0
    page.keyboard.press("ArrowDown")                                           # nothing to move through
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    assert page.locator(OVERLAY).count() == 0
    _no_errors(page)


def test_it_says_it_is_reading(loose):
    page, open_list = loose
    open_list(_answer(LOOSE, hold=True))
    assert _state(page) == "loading"
    assert "Reading" in page.locator(BODY).inner_text()
    page.evaluate("window.__release()")
    _wait_state(page, "ready")


def test_a_closed_list_ignores_its_answer(loose):
    page, open_list = loose
    open_list(_answer(LOOSE, hold=True))
    page.keyboard.press("Escape")
    assert page.locator(OVERLAY).count() == 0
    page.evaluate("window.__release()")
    page.wait_for_timeout(100)
    assert page.locator(OVERLAY).count() == 0
    _no_errors(page)


def test_an_older_answer_never_paints_over_a_newer_one(loose):
    page, open_list = loose
    open_list(_answer(DOWN, hold=True))
    page.evaluate("() => { window.__heldFirst = window.__release; }")
    open_list(_answer(LOOSE), click=False)                     # reopened with the first read still out
    _wait_state(page, "ready")
    page.evaluate("() => window.__heldFirst()")
    page.wait_for_timeout(100)
    assert _state(page) == "ready" and page.locator(NOTICE).count() == 0


# --- the tiers ----------------------------------------------------------------------


def test_the_standard_tier_is_the_default(loose):
    page, open_list = loose
    open_list(_answer(LOOSE))
    assert page.locator(OVERLAY).get_attribute("data-overlay-tier") == "standard"
    assert page.evaluate("getComputedStyle(document.querySelector('#fcc-loose-list')).zIndex") == "20000"


def test_the_confirm_tier_sits_over_a_standard_overlay(loose):
    """The audit panel's way in (slice s5): over its panel, closing only itself."""
    page, open_list = loose
    page.evaluate("""() => { window.mountOverlay({ id: 'stand-in-audit-panel', content: '<div>panel</div>' }); }""")
    open_list(_answer(LOOSE), click=False, opts={"tier": "confirm"})
    _wait_state(page, "ready")
    assert page.locator(OVERLAY).get_attribute("data-overlay-tier") == "confirm"
    assert page.evaluate("getComputedStyle(document.querySelector('#fcc-loose-list')).zIndex") == "20100"
    assert page.evaluate("window.isTopOverlay(document.querySelector('#fcc-loose-list'))") is True
    page.keyboard.press("ArrowDown")
    assert _active(page) == "15"
    page.keyboard.press("Escape")
    assert page.locator(OVERLAY).count() == 0 and page.locator("#stand-in-audit-panel").count() == 1


def test_opening_it_again_replaces_it(loose):
    page, open_list = loose
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    open_list(_answer(EMPTY), click=False)
    _wait_state(page, "empty")
    assert page.locator(OVERLAY).count() == 1
    page.keyboard.press("Escape")
    assert page.locator(OVERLAY).count() == 0
    _no_errors(page)


# --- text ---------------------------------------------------------------------------


def test_every_piece_of_text_is_escaped(loose):
    page, open_list = loose
    evil = '<img src=x onerror="window.__xss=1">'
    open_list(_answer({**EMPTY, "count": 1, "places": [
        {"id": evil, "name": evil + "n", "type": evil + "t", "spools": [_spool(1, evil + "s", color='"><b>')]}]}))
    _wait_state(page, "ready")
    assert page.locator(OVERLAY + " img").count() == 0
    assert page.evaluate("window.__xss === undefined") is True
    assert evil + "s" in page.locator(ROW).inner_text()


def test_contrast_in_every_state(loose):
    page, open_list = loose
    open_list(_answer(LOOSE, hold=True))
    assert contrast_offenders(page.locator(PANEL)) == []                       # reading
    page.evaluate("window.__release()")
    _wait_state(page, "ready")
    assert contrast_offenders(page.locator(PANEL)) == []                       # the rows, one highlighted
    scored = [o["text"] for o in contrast_offenders(page.locator(PANEL), min_ratio=100)]
    assert any("#86" in t for t in scored), scored                             # and the rows were scored
    open_list(_answer(DOWN), click=False)
    _wait_state(page, "error")
    assert contrast_offenders(page.locator(PANEL)) == []                       # the notice
    page.locator(RETRY).hover()
    assert contrast_offenders(page.locator(PANEL)) == []
    open_list(_answer(EMPTY), click=False)
    _wait_state(page, "empty")
    assert contrast_offenders(page.locator(PANEL)) == []


def test_the_short_window_keeps_its_rows(loose):
    page, open_list = loose
    page.set_viewport_size({"width": 800, "height": 420})
    open_list(_answer(LOOSE))
    _wait_state(page, "ready")
    assert page.locator(OVERLAY + " [data-loose-sub]").is_hidden()
    assert page.locator(ACTIVE).is_visible()


def test_one_size_whatever_it_shows(loose):
    """Derek on the Low stock list (Group 57.1): "It jumps in size"."""
    page, open_list = loose
    sizes = []
    for body, state_name in ((LOOSE, "ready"), (EMPTY, "empty"), (DOWN, "error")):
        open_list(_answer(body), click=False)
        _wait_state(page, state_name)
        box = page.locator(PANEL).bounding_box()
        sizes.append((box["width"], box["height"]))
    assert len(set(sizes)) == 1, sizes


# --- the wiring ---------------------------------------------------------------------


def test_the_page_loads_the_module():
    html = SCRIPTS.read_text(encoding="utf-8")
    assert "js/modules/inv_loose.js" in html
    assert html.index("js/modules/inv_core.js") < html.index("js/modules/inv_loose.js")


def test_the_locations_window_has_its_way_in():
    html = LOC_TEMPLATE.read_text(encoding="utf-8")
    assert 'id="loc-loose-list-btn"' in html
    assert "window.openLooseList({ host: document.getElementById('locMgrModal') })" in html


def test_its_keys_are_in_the_shortcut_list(loose):
    page, _ = loose
    keys = page.evaluate("window.__pendingShortcuts.filter((s) => s.scope === 'Loose Spools List').map((s) => s.keys[0])")
    assert keys == ["↑", "Enter", "Esc"]
