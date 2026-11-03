"""Derek's answers of 2026-11-03 on Group 58, the page half: a tile's QR (A1), 🔎 Find a
spool (A2), an Extra taken back (A3) and the strip's 🖨️ Add to print queue (B), on a real
DOM, hermetic.

The real overlay_mount.js, inv_core.js, inv_cmd.js, inv_audit_find.js and inv_queue.js,
the real scan accumulator and global.css, in `isolated_page` (no route to any network),
so it runs under --offline. Every request the page makes to FCC goes through an exposed
binding to the REAL Flask routes (identify_scan, the audit's, /api/search), on the real
session, with the real reads over tests/spoolman_extra_fake.SpoolmanHTTPFake: a search
row, a session row and a scan's answer are the routes' own. A stub stands in only where
the server can't be made to fail that way (no answer from FCC, an error page), and the
QR library's drawing, which needs a CDN.

Keys go on a fake clock (test_slow_scan_slash_js / test_scanner_safe_dialogs_61_js) where a
scanner's speed is the point; the real keyboard and mouse where a browser's own press is
what is tested (a synthetic Enter clicks nothing).

test_audit_no_label_58.py has the server's CMD:FOUND and the Extra's take-back; the
_e2e twin of this file the real dashboard with real QR codes.

RED on 2fd8a2d (builder 1's last commit) unless a test says it pins what was already right.
"""
from __future__ import annotations

import json

import pytest

import app as app_module
from test_audit_no_label_58_js import BODY, BUTTON, UNDO, tile, strip_says, tile_says, toasts
from test_audit_panel_58_js import DONE, PANEL, audit  # noqa: F401  (audit: the fixture)
from test_audit_session_58 import ROWS, add_spool, env, scan, session, start  # noqa: F401  (env: the fixture)
from test_scanner_safe_dialogs_61_js import MODULES, TYPE_BOX_JS, page61  # noqa: F401  (page61: the fixture)
from test_slow_scan_slash_js import _later, _type

FIND = "#fcc-audit-find"
FIND_BTN = "#fcc-audit-panel-find"
FIND_BOX = FIND + " [data-find-box]"
FIND_BODY = FIND + " [data-find-body]"
FIND_ROW = FIND + " .fcc-find-row"
FIND_NOTICE = FIND + " [data-find-notice]"
QUEUE = "#fcc-audit-label-queue"
PAST_A_DOUBLE_PRESS = 720                       # DOUBLE_PRESS_MS (inv_cmd.js) and a little
PAST_THE_DEBOUNCE = 320                         # DEBOUNCE_MS (inv_audit_find.js) and a little

# The real routes for every request to FCC this file is about, and the hooks a test
# holds them with. `__held`: a scan's answer waits for `__release()`. `__holdSearch`: each
# search waits for its own `release`, in `__searches`. `__searchFails`: 'down' (FCC never
# answers) or 'html' (an error page) for the search, which no real route can be made to do.
ROUTES = r"""() => {
    window.closeAuditPanel();
    window.__sent = [];
    window.__qrs = [];
    // The QR library from the CDN draws a canvas, and sets the box's tooltip to its text.
    window.QRCode = function (el, o) { window.__qrs.push(o.text); el.textContent = 'QR'; el.title = o.text; };
    window.QRCode.CorrectLevel = { L: 1 };
    window.__searches = [];
    window.__holdSearch = false;
    window.__searchFails = null;
    state.allLocations = window.__rows;
    const plain = window.fetch;
    window.fetch = async (url, opts) => {
        const u = String(url);
        if (!/\/api\/(identify_scan|audit|search)/.test(u)) return plain(url, opts);
        const body = opts && opts.body ? opts.body : null;
        if (body) window.__sent.push({ url: u, body: JSON.parse(body) });
        if (u.indexOf('/api/search') !== -1) {
            const entry = { url: u, q: new URL(u, 'http://fcc.test').searchParams.get('q'), answered: false };
            window.__searches.push(entry);
            if (window.__holdSearch) await new Promise((resolve) => { entry.release = resolve; });
            entry.answered = true;
            if (window.__searchFails === 'down') throw new TypeError('Failed to fetch');
            if (window.__searchFails === 'html') {
                return { ok: false, status: 500, json: async () => { throw new SyntaxError('Unexpected token <'); },
                         text: async () => '<html>Internal Server Error</html>' };
            }
        }
        if (window.__held && u.indexOf('/api/identify_scan') !== -1) {
            await new Promise((resolve) => { window.__release = resolve; });
        }
        const got = JSON.parse(await window.__fcc(u, (opts && opts.method) || 'GET', body));
        return { ok: got.status < 400, status: got.status, json: async () => JSON.parse(got.text), text: async () => got.text };
    };
}"""


@pytest.fixture
def live(env, audit):
    """`audit`'s page with Find and the print queue loaded, answered by the real routes."""
    client = app_module.app.test_client()

    def answer(url, method, body):
        res = client.open(url, method=method, data=body, content_type="application/json")
        return json.dumps({"status": res.status_code, "text": res.get_data(as_text=True)})
    audit.expose_function("__fcc", answer)
    for name in ("inv_queue.js", "inv_audit_find.js"):
        audit.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    audit.evaluate("(rows) => { window.__rows = rows; }", ROWS)
    audit.evaluate(ROUTES)
    return audit


def search_row(sid, name, location, slot="", is_ghost=False, lost_from=None, archived=False):
    """A row of /api/search's answer (type=spool), as the real route builds it: pinned by
    test_the_search_sample_is_the_routes_shape below, for the e2e and the guards."""
    display = f"#{sid} Some Brand PLA ({name})"
    return {"id": sid, "display": display, "display_short": display[len(f"#{sid} "):], "color": "72071C",
            "color_direction": "longitudinal", "slot": slot, "location": location, "is_ghost": is_ghost,
            "remaining": 500, "color_dist": 0, "type": "spool", "archived": archived, "spools_count": None,
            "details": {"id": sid, "brand": "Some Brand", "material": "PLA", "color_name": name, "weight": 500,
                        "temp": "", "needs_label_print": None, "lost_from": lost_from}}


SEARCH_ROWS = [search_row(99, "Glow Blue", "LR-MDB-1", "2"), search_row(200, "Glow Teal", "LR-MDB-2", "3"),
               search_row(242, "Glow Lime", "LR-MDB-2", "4", is_ghost=True),
               search_row(260, "Glow Gold", "UNKNOWN", lost_from={"place": "CR-CT-1", "slot": "2", "on": "2026-11-01"}),
               search_row(270, "Glow Grey", "")]


def begin(page, env, place="LR-MDB-1"):
    """The audit started on the real session, and its panel up on the page."""
    start(env, place)
    page.evaluate("() => { state.auditActive = true; window.openAuditPanel(); }")
    page.wait_for_selector(DONE)


def two(env):
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    add_spool(env, 99, "LR-MDB-1", container_slot="2")


def scanned(page, text, source="keyboard"):
    """A scan through the page's own path, answered and drawn."""
    page.evaluate("([t, s]) => { window.processScan(t, s); }", [text, source])
    page.wait_for_function("() => !state.processing")


def scans(page):
    return [p["body"].get("text") for p in page.evaluate("window.__sent") if p["url"] == "/api/identify_scan"]


def scans_with_source(page):
    return [(p["body"].get("text"), p["body"].get("source"))
            for p in page.evaluate("window.__sent") if p["url"] == "/api/identify_scan"]


def posts(page, url):
    return [p["body"] for p in page.evaluate("window.__sent") if p["url"] == url]


def audit_id():
    return session()["audit_id"]


def qr_text(sid):
    return f"CMD:FOUND:{audit_id()}:{sid}"


def open_find(page):
    page.click(FIND_BTN)
    page.wait_for_selector(FIND_BOX)
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=FIND_BOX)


def search(page, words):
    """Words typed into Find's box as a person does, and the newest answer drawn."""
    n = page.evaluate("window.__searches.length")
    page.fill(FIND_BOX, words)
    page.wait_for_function("([n]) => window.__searches.length > n && window.__searches.every((s) => s.answered)", arg=[n])
    page.wait_for_function("(s) => ['ready', 'empty', 'error'].includes(document.querySelector(s).dataset.findState)",
                           arg=FIND_BODY)


def rows(page):
    return page.evaluate("(s) => Array.from(document.querySelectorAll(s)).map((r) => Number(r.dataset.findId))", FIND_ROW)


def row(sid):
    return f"{FIND} .fcc-find-row[data-find-id='{sid}']"


def find_state(page):
    return page.evaluate("(s) => document.querySelector(s).dataset.findState", FIND_BODY)


def focus_is(page, sel):
    return page.evaluate("(s) => document.activeElement === document.querySelector(s)", sel)


# --- A1: a tile's QR ---------------------------------------------------------------------

def test_a_tile_not_yet_found_shows_its_qr_and_no_other_tile_does(live, env):
    two(env)
    add_spool(env, 200, "LR-MDB-2", container_slot="3")
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-1", physical_source_slot="4")
    begin(live, env)
    scanned(live, "ID:57")
    scanned(live, "ID:200")
    scanned(live, "ID:242")
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('Loaded from here')", arg=BODY)
    qrs = live.evaluate("""() => Array.from(document.querySelectorAll('[data-audit-qr]')).map((q) => ({
        tile: q.closest('[data-audit-tile]') && q.closest('[data-audit-tile]').dataset.auditTile,
        text: q.dataset.auditQr, hidden: q.getAttribute('aria-hidden'),
        title: q.querySelector('.fcc-audit-tile-qr-code').getAttribute('title') }))""")
    assert qrs == [{"tile": "99", "text": qr_text(99), "hidden": "true", "title": None}]
    assert live.evaluate("window.__qrs").count(qr_text(99)) == 1
    assert "or scan its QR" in live.get_attribute(tile(99), "title")
    assert "Press its tile, or scan its QR." in live.text_content(BODY)


def test_no_qr_until_the_page_knows_the_audit(audit):
    """A QR with no audit id would name no audit. The stub session has none here. A guard
    of the new code (no QR at all on 2fd8a2d): proved on a copy whose _tileQrText draws
    one whatever the page knows."""
    audit.evaluate("""() => { window.closeAuditPanel(); window.__qrs = [];
        window.QRCode = function (el, o) { window.__qrs.push(o.text); }; window.QRCode.CorrectLevel = { L: 1 };
        state.auditId = null; window.__session = Object.assign({}, window.__session, { audit_id: null });
        window.openAuditPanel(); }""")
    audit.wait_for_selector("[data-audit-tile='99']")
    assert audit.evaluate("() => document.querySelectorAll('[data-audit-qr]').length") == 0
    assert "Press its tile." in audit.text_content(BODY)
    assert not [t for t in audit.evaluate("window.__qrs") if t.startswith("CMD:FOUND")]


def test_a_tiles_qr_is_drawn_once_and_kept_through_every_redraw(live, env):
    two(env)
    add_spool(env, 134, "LR-MDB-1", container_slot="3")
    begin(live, env)
    live.wait_for_selector("[data-audit-qr]")
    live.evaluate("() => { document.querySelector(\"[data-audit-tile='99'] .fcc-audit-tile-qr-code\").__mine = 1; }")
    scanned(live, "ID:57")                  # each scan changes the panel's hash: the body is drawn again
    strip_says(live, "#57")
    scanned(live, "ID:134")
    strip_says(live, "#134")
    assert live.evaluate("window.__qrs").count(qr_text(99)) == 1
    assert live.evaluate("() => document.querySelector(\"[data-audit-tile='99'] .fcc-audit-tile-qr-code\").__mine") == 1


@pytest.mark.parametrize("upper", [False, True], ids=["as-drawn", "upper-case"])
def test_a_tiles_qr_scanned_as_keys_finds_the_spool_as_a_press_does(live, env, upper):
    """The real accumulator at a scanner's speed, the real route: found, no label read,
    the last found; its QR goes with the find. A scanner set to upper case reads the same."""
    two(env)
    begin(live, env)
    live.wait_for_selector("[data-audit-qr]")
    text = qr_text(99).upper() if upper else qr_text(99)
    _type(live, text, 1)
    tile_says(live, 99, "found, no label read")
    strip_says(live, "No label was read for #99")
    assert scans(live) == [text]
    assert live.evaluate("() => Array.from(document.querySelectorAll('[data-audit-qr]')).map((q) => q.dataset.auditQr)") \
        == [qr_text(57)]                     # #99's went with its find; #57 is still to find
    assert 99 in session()["scanned_items"]


def test_a_tiles_qr_read_twice_finds_once_and_takes_nothing_back(live, env):
    two(env)
    begin(live, env)
    live.wait_for_selector("[data-audit-qr]")
    text = qr_text(99)
    _type(live, text, 1)
    tile_says(live, 99, "found, no label read")
    _type(live, text, 1)
    live.wait_for_function("() => !state.processing")
    tile_says(live, 99, "found, no label read")
    assert 99 in session()["scanned_items"]


# --- A3: an Extra taken back -------------------------------------------------------------

def test_an_extra_tile_is_a_button_and_a_press_takes_it_back(live, env):
    two(env)
    add_spool(env, 200, "LR-MDB-2", container_slot="3")
    begin(live, env)
    scanned(live, "ID:200")
    live.wait_for_selector(tile(200))
    assert live.evaluate("(s) => document.querySelector(s).tagName", tile(200)) == "BUTTON"
    assert live.get_attribute(tile(200), "data-audit-found") == "1"
    assert "isn't here after all" in live.get_attribute(tile(200), "title")
    assert "Not here after all? Press its tile." in live.text_content(BODY)
    live.click(tile(200))
    live.wait_for_selector(tile(200), state="detached")
    assert posts(live, "/api/audit/found") == [{"audit_id": audit_id(), "id": 200, "found": False}]
    assert 200 not in session()["rogue_items"] and session().get("last_found") != 200
    assert "Extra (found here" not in live.text_content(BODY)


def test_a_double_click_on_an_extra_takes_it_back_once_and_reaches_nothing_under_it(live, env):
    two(env)
    add_spool(env, 200, "LR-MDB-2", container_slot="3")
    begin(live, env)
    scanned(live, "ID:200")
    live.wait_for_selector(tile(200))
    live.dblclick(tile(200))
    live.wait_for_selector(tile(200), state="detached")
    live.wait_for_timeout(300)
    assert posts(live, "/api/audit/found") == [{"audit_id": audit_id(), "id": 200, "found": False}]
    assert session()["scanned_items"] == []          # nothing under it was found


def test_the_arrows_reach_an_extra_and_enter_takes_it_back(live, env):
    two(env)
    add_spool(env, 200, "LR-MDB-2", container_slot="3")
    begin(live, env)
    scanned(live, "ID:200")
    live.wait_for_selector(tile(200))
    live.keyboard.press("ArrowLeft")                 # from nowhere, back: the last tile
    assert live.evaluate("document.activeElement.dataset.auditTile") == "200"
    live.keyboard.press("Enter")
    live.wait_for_selector(tile(200), state="detached")
    assert posts(live, "/api/audit/found")[-1]["found"] is False


def test_a_loaded_from_here_tile_stays_a_plain_tile(live, env):
    """Pins the server's rule on the page: it was right before."""
    two(env)
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-1", physical_source_slot="4")
    begin(live, env)
    scanned(live, "ID:242")
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('Loaded from here')", arg=BODY)
    assert live.evaluate("() => document.querySelectorAll(\"button[data-audit-tile='242']\").length") == 0


# --- B: the strip's 🖨️ Add to print queue ------------------------------------------------

def marked(page, env, sid=99):
    """A spool found, then marked "Needs a label" on the strip."""
    scanned(page, f"ID:{sid}")
    strip_says(page, f"#{sid}")
    page.click(BUTTON)
    page.wait_for_selector(UNDO)


def test_no_button_for_a_spool_whose_label_isnt_flagged(live, env):
    """A guard of the new code (no button at all on 2fd8a2d): proved on a copy whose
    _queueButton draws it for every spool."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    strip_says(live, "#57")
    assert live.locator(QUEUE).count() == 0


def test_a_flagged_spools_label_goes_to_the_print_queue_once(live, env):
    two(env)
    begin(live, env)
    marked(live, env)
    assert live.text_content(QUEUE).strip() == "🖨️ Add to print queue"
    live.evaluate("() => { const plain = window.addToQueue; window.__adds = 0;"
                  " window.addToQueue = (item) => { window.__adds += 1; return plain(item); }; }")
    live.click(QUEUE)
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('In the print queue')", arg=QUEUE)
    assert live.evaluate("window.labelQueue.map((q) => [q.id, q.type])") == [[99, "spool"]]
    assert live.get_attribute(QUEUE, "aria-disabled") == "true"
    assert {"msg": "Added #99's label to the print queue.", "kind": "success"} in toasts(live)
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    box = live.locator(QUEUE).bounding_box()         # queued: a real press does nothing
    live.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    live.wait_for_timeout(100)
    assert live.evaluate("window.__adds") == 1 and len(live.evaluate("window.labelQueue")) == 1
    assert focus_is(live, QUEUE)                     # it kept the keyboard through the redraw


def test_a_double_press_of_the_queue_button_is_one_press(live, env):
    two(env)
    begin(live, env)
    marked(live, env)
    live.evaluate("() => { const plain = window.addToQueue; window.__adds = 0;"
                  " window.addToQueue = (item) => { window.__adds += 1; return plain(item); }; }")
    live.dblclick(QUEUE)
    live.wait_for_timeout(200)
    assert live.evaluate("window.__adds") == 1


def test_the_queue_button_is_pressed_by_a_persons_enter_and_not_by_a_scans(live, env):
    two(env)
    begin(live, env)
    marked(live, env)
    live.focus(QUEUE)
    _type(live, "LOC:LR-MDB-2", 1)                   # a scan's Enter with the focus on it
    live.wait_for_function("() => !state.processing")
    assert live.evaluate("window.labelQueue.length") == 0
    _later(live, 200)                                # past a scanner's second Enter (CR LF)
    live.focus(QUEUE)
    live.keyboard.press("Enter")
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('In the print queue')", arg=QUEUE)


def test_undo_that_leaves_the_queue_alone_and_says_the_label_is_still_there(live, env):
    two(env)
    begin(live, env)
    marked(live, env)
    live.click(QUEUE)
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('In the print queue')", arg=QUEUE)
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    live.click(UNDO)
    live.wait_for_selector(UNDO, state="detached")
    live.wait_for_function("() => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                           ".some((e) => e.innerText.includes('#99 is still in the print queue.'))")
    assert live.evaluate("window.labelQueue.length") == 1
    assert "In the print queue" in live.text_content(QUEUE)


def test_a_label_queued_from_another_tab_turns_the_button(live, env):
    """inv_queue.js's 2 s read of the shared queue changes window.labelQueue in place,
    with no event: the panel's own poll reads it."""
    two(env)
    begin(live, env)
    marked(live, env)
    live.evaluate("() => { window.labelQueue.push({ id: 99, type: 'spool', display: '#99' }); }")
    live.evaluate("() => window.refreshAuditSession()")
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('In the print queue')", arg=QUEUE)


# --- A2: Find a spool ----------------------------------------------------------------------

def glow(env):
    """Spools a search for "glow" finds: on the list (found and not), elsewhere, loaded
    from a box, on a head, lost by an audit, unassigned, and archived."""
    add_spool(env, 57, "LR-MDB-1", name="Glow Red", container_slot="1")
    add_spool(env, 99, "LR-MDB-1", name="Glow Blue", container_slot="2")
    add_spool(env, 200, "LR-MDB-2", name="Glow Teal", container_slot="3")
    add_spool(env, 242, "XL-1", name="Glow Lime", physical_source="LR-MDB-2", physical_source_slot="4")
    add_spool(env, 250, "XL-2", name="Glow Pink")
    add_spool(env, 260, "UNKNOWN", name="Glow Gold", fcc_pre_audit_location="CR-CT-1:2@2026-11-01")
    add_spool(env, 270, "", name="Glow Grey")
    add_spool(env, 280, "LR-MDB-2", name="Glow Black")
    env["fake"].records["spool"][280]["archived"] = True


def test_the_search_sample_is_the_routes_shape(env):
    """The e2e and the guards draw SEARCH_ROWS: the real route's rows, key for key, and
    the same words where they hold the same spool. Pins the sample, not new code."""
    glow(env)
    got = {r["id"]: r for r in env["client"].get("/api/search?q=glow&type=spool&strict=1").get_json()["results"]}
    for want in SEARCH_ROWS:
        real = got[want["id"]]
        assert set(want) == set(real) and set(want["details"]) == set(real["details"]), want["id"]
        for key in ("display", "location", "slot", "is_ghost", "type", "archived"):
            assert want[key] == real[key], (want["id"], key, real[key])
        assert want["details"]["lost_from"] == real["details"]["lost_from"]


def test_find_opens_from_its_button_and_from_slash_with_the_box_focused(live, env):
    two(env)
    begin(live, env)
    open_find(live)
    assert "Type a name, colour, brand or number." in live.text_content(FIND_BODY)
    assert live.evaluate("(s) => document.querySelector(s).closest('[data-overlay-mount]').dataset.overlayTier",
                         FIND_BOX) == "confirm"
    live.keyboard.press("Escape")                    # closes only Find
    live.wait_for_selector(FIND, state="detached")
    assert live.locator(PANEL).count() == 1
    live.keyboard.press("/")
    live.wait_for_selector(FIND_BOX)
    assert focus_is(live, FIND_BOX)
    assert live.evaluate("state.scanBuffer") == ""   # the '/' joins no scan


def test_a_slash_inside_a_scan_opens_nothing_and_the_scan_arrives_whole(audit):
    """A guard of the new code (no Find on 2fd8a2d): proved on a copy whose _keyFind
    doesn't ask window.scanIsArriving."""
    audit.add_script_tag(content=(MODULES / "inv_audit_find.js").read_text(encoding="utf-8"))
    audit.wait_for_selector(DONE)
    _type(audit, "ID:5/7", 1)
    audit.wait_for_function("() => window.__ids.length > 0")
    assert audit.locator(FIND).count() == 0
    assert [i["text"] for i in audit.evaluate("window.__ids")] == ["ID:5/7"]


def test_typing_searches_spools_strictly_and_only_the_newest_answer_paints(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    live.evaluate("() => { window.__holdSearch = true; }")
    live.fill(FIND_BOX, "glow red")
    live.wait_for_function("() => window.__searches.length === 1")
    live.fill(FIND_BOX, "glow teal")
    live.wait_for_function("() => window.__searches.length === 2")
    assert live.evaluate("window.__searches.map((s) => s.url)") == [
        "/api/search?q=glow+red&type=spool&strict=1", "/api/search?q=glow+teal&type=spool&strict=1"]
    live.evaluate("() => window.__searches[1].release()")       # the newer answer first
    live.wait_for_function("(s) => document.querySelector(s).dataset.findState === 'ready'", arg=FIND_BODY)
    assert rows(live) == [200]
    live.evaluate("() => window.__searches[0].release()")       # the older one, late
    live.wait_for_function("() => window.__searches.every((s) => s.answered)")
    live.wait_for_timeout(100)
    assert rows(live) == [200]


def test_one_search_for_a_burst_of_typing(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    live.type(FIND_BOX, "glow", delay=30)
    live.wait_for_timeout(PAST_THE_DEBOUNCE)
    live.wait_for_function("(s) => document.querySelector(s).dataset.findState === 'ready'", arg=FIND_BODY)
    assert live.evaluate("window.__searches.map((s) => s.q)") == ["glow"]


@pytest.mark.parametrize("how, why", [
    ("spoolman-down", "Couldn't search: Spoolman didn't answer"),
    ("spoolman-503", "Couldn't search: Spoolman answered HTTP 503."),
    ("fcc-down", "Couldn't search: FCC didn't answer."),
    ("error-page", "Couldn't search: FCC answered with an error (HTTP 500)."),
])
def test_a_search_that_fails_says_so_and_never_no_matches(live, env, how, why):
    glow(env)
    begin(live, env)
    open_find(live)
    if how == "spoolman-down":
        env["fake"].down = True
    elif how == "spoolman-503":
        env["fake"].list_reads_fail = True
    else:
        live.evaluate("(h) => { window.__searchFails = h === 'fcc-down' ? 'down' : 'html'; }", how)
    search(live, "glow")
    assert find_state(live) == "error"
    text = live.text_content(FIND_BODY)
    assert why in text and "No spool matches" not in text and rows(live) == []
    # Try again, with Spoolman and FCC answering.
    env["fake"].down = env["fake"].list_reads_fail = False
    live.evaluate("() => { window.__searchFails = null; }")
    live.click(FIND + " [data-find-retry]")
    live.wait_for_function("(s) => document.querySelector(s).dataset.findState === 'ready'", arg=FIND_BODY)
    assert 99 in rows(live)


def test_a_search_that_matches_nothing_says_so_and_an_empty_box_shows_the_hint(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    search(live, "nothing like this")
    assert find_state(live) == "empty" and "No spool matches" in live.text_content(FIND_BODY)
    live.fill(FIND_BOX, "")
    live.wait_for_function("(s) => document.querySelector(s).dataset.findState === 'hint'", arg=FIND_BODY)
    assert "Type a name, colour, brand or number." in live.text_content(FIND_BODY)


def test_each_row_says_where_fcc_has_it_and_what_the_audit_says_of_it(live, env):
    glow(env)
    begin(live, env)
    scanned(live, "ID:57")
    open_find(live)
    search(live, "glow")
    assert 280 not in rows(live)                     # archived
    got = live.evaluate("""(sel) => Object.fromEntries(Array.from(document.querySelectorAll(sel)).map((r) => [r.dataset.findId, {
        name: r.querySelector('.fcc-find-name').textContent, where: r.querySelector('.fcc-find-where').textContent,
        tag: r.querySelector('[data-find-tag]').textContent.trim(), swatch: !!r.querySelector('.fcc-find-swatch') }]))""", FIND_ROW)
    assert got["57"] == {"name": "#57 Some Brand PLA (Glow Red)", "where": "📍 LR-MDB-1 slot 1", "tag": "✅ found", "swatch": True}
    assert got["99"]["where"] == "📍 LR-MDB-1 slot 2" and got["99"]["tag"] == "on the list"
    assert got["200"]["where"] == "📍 LR-MDB-2 slot 3" and got["200"]["tag"] == ""
    assert got["242"]["where"] == "🔗 loaded from LR-MDB-2 slot 4"
    assert got["250"]["where"] == "🔗 loaded on XL-2"
    assert got["260"]["where"] == "❓ Lost: CR-CT-1 slot 2"
    assert got["270"]["where"] == "Unassigned"


def test_the_number_typed_comes_first(live, env):
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    add_spool(env, 157, "LR-MDB-2", container_slot="1")
    add_spool(env, 570, "LR-MDB-2", container_slot="2")
    begin(live, env)
    open_find(live)
    search(live, "#57")
    assert rows(live)[0] == 57 and set(rows(live)) == {57, 157, 570}
    assert live.evaluate("window.__searches.map((s) => s.q)")[-1] == "57"


def test_the_arrows_wrap_and_tab_moves_between_the_box_and_the_list(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    search(live, "glow")
    first, *_rest, last = rows(live)
    live.keyboard.press("ArrowDown")
    assert focus_is(live, row(first))
    live.keyboard.press("ArrowUp")                   # wraps
    assert focus_is(live, row(last))
    live.keyboard.press("ArrowDown")
    assert focus_is(live, row(first))
    assert live.evaluate("(s) => Array.from(document.querySelectorAll(s)).filter((r) => r.tabIndex === 0).length", FIND_ROW) == 1
    live.keyboard.press("Shift+Tab")
    assert focus_is(live, FIND_BOX)
    live.keyboard.press("Tab")
    assert focus_is(live, row(first))
    live.keyboard.press("/")                         # back to the box
    assert focus_is(live, FIND_BOX)


def test_enter_on_a_row_picks_it_with_no_label_read(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    search(live, "glow blue")
    live.keyboard.press("ArrowDown")
    live.keyboard.press("Enter")
    live.wait_for_selector(FIND, state="detached")
    tile_says(live, 99, "found, no label read")
    strip_says(live, "No label was read for #99")
    assert scans_with_source(live) == [("ID:99", "search")]
    assert focus_is(live, FIND_BTN)


def test_enter_in_the_box_searches_now_and_picks_nothing(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    live.evaluate("(s) => { const b = document.querySelector(s); b.value = 'glow blue'; }", FIND_BOX)  # no input event
    live.keyboard.press("Enter")
    live.wait_for_function("(s) => document.querySelector(s).dataset.findState === 'ready'", arg=FIND_BODY)
    assert rows(live) == [99] and scans(live) == []
    assert live.locator(FIND).count() == 1


def test_a_double_enter_on_a_row_picks_once_and_opens_nothing(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    search(live, "glow blue")
    live.keyboard.press("ArrowDown")
    live.keyboard.press("Enter")
    live.keyboard.press("Enter")                     # lands on 🔎, where the keyboard went
    live.wait_for_timeout(200)
    assert live.locator(FIND).count() == 0
    assert scans(live) == ["ID:99"]


def test_a_click_on_a_row_picks_it_in_its_turn_behind_a_scan_read_before_it(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    search(live, "glow blue")
    live.evaluate("() => { window.__held = true; window.processScan('ID:57', 'keyboard'); }")
    live.wait_for_function("() => state.processing")
    live.click(row(99))
    live.wait_for_selector(FIND, state="detached")
    assert scans(live) == ["ID:57"]                  # the pick waits its turn
    live.evaluate("() => { window.__held = false; window.__release(); }")
    live.wait_for_function("() => window.__sent.filter((p) => p.url === '/api/identify_scan').length === 2")
    assert scans_with_source(live) == [("ID:57", "keyboard"), ("ID:99", "search")]


def test_a_spool_off_the_list_picked_is_an_extra(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    search(live, "glow teal")
    live.click(row(200))
    live.wait_for_selector(tile(200))
    strip_says(live, "Extra: FCC has #200 at LR-MDB-2 slot 3")
    assert 200 in session()["rogue_items"]


def test_a_label_scanned_into_the_box_is_a_scan_and_never_a_search(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    live.evaluate(TYPE_BOX_JS, ["gl", 200, False, {}])          # a person's two keys
    live.evaluate(TYPE_BOX_JS, ["ID:200", 1, True, {"0": 900}])  # then a scanner, after a pause
    live.wait_for_selector(FIND, state="detached")             # the audit took it
    assert scans_with_source(live) == [("ID:200", "barcode")]
    assert not [s for s in live.evaluate("window.__searches.map((s) => s.q)") if "ID" in s.upper()]
    live.wait_for_selector(tile(200))


def test_a_scans_enter_on_a_row_picks_nothing_and_the_scan_arrives_whole(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    search(live, "glow blue")
    live.keyboard.press("ArrowDown")
    _type(live, "LOC:LR-MDB-2", 1)                   # refused: an audit is running
    live.wait_for_function("(s) => !document.querySelector(s).hidden", arg=FIND_NOTICE)
    assert scans(live) == ["LOC:LR-MDB-2"]
    assert live.locator(FIND).count() == 1           # refused, so it stays, and says why on top
    assert "Already auditing" in live.text_content(FIND_NOTICE)


def test_a_space_inside_a_scan_presses_no_row(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    search(live, "glow blue")
    live.keyboard.press("ArrowDown")
    live.keyboard.type("LOC:Bin 2")                  # real keys: the Space would press the row
    live.keyboard.press("Enter")
    live.wait_for_function("() => window.__sent.some((p) => p.url === '/api/identify_scan')")
    live.wait_for_function("() => !state.processing")
    assert scans(live) == ["LOC:Bin 2"]


def test_find_closes_on_a_scan_the_audit_takes_and_with_the_panel(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    scanned(live, "ID:57")
    live.wait_for_selector(FIND, state="detached")
    open_find(live)
    live.evaluate("() => window.closeAuditPanel()")
    live.wait_for_selector(FIND, state="detached")


def test_a_double_click_on_a_row_picks_once_and_reaches_nothing_under_it(live, env):
    """The hermetic twin of the double-click sweep's: the row lies over the panel, and
    its second click lands there once Find is gone."""
    glow(env)
    begin(live, env)
    open_find(live)
    search(live, "glow blue")
    box = live.locator(row(99)).bounding_box()
    under = live.evaluate("""([x, y]) => { const f = document.getElementById('fcc-audit-find');
        f.style.visibility = 'hidden'; const e = document.elementFromPoint(x, y); f.style.visibility = '';
        return e && document.getElementById('fcc-audit-panel-overlay').contains(e); }""",
                          [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2])
    assert under is True
    live.mouse.dblclick(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, delay=0)
    live.wait_for_selector(FIND, state="detached")
    tile_says(live, 99, "found, no label read")
    live.wait_for_timeout(300)
    assert scans(live) == ["ID:99"] and posts(live, "/api/audit/found") == []
    assert session()["scanned_items"] == [99]


def test_the_tags_follow_the_audit_while_find_is_open(live, env):
    glow(env)
    begin(live, env)
    open_find(live)
    search(live, "glow blue")
    assert live.text_content(row(99) + " [data-find-tag]").strip() == "on the list"
    scan(env, "ID:99")                               # found from another window
    live.evaluate("() => window.refreshAuditSession()")
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('found')", arg=row(99) + " [data-find-tag]")
