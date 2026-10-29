"""Group 52 review, finding reads-1, the page half: when the heartbeat's spool
read fails, the Printer Status widget and the Locations table keep what they
drew and say Spoolman didn't answer, instead of drawing every head empty and
every box 0/N for one tick.

Runs the REAL overlay_mount.js, inv_core.js and inv_printer_status.js with the
real static/css/global.css in `isolated_page` (a chromium with no route to any
network), so it RUNS under --offline. `fetch` is stubbed in the page; every
answer below is made up, nothing reaches the container or Spoolman.

Pinned:
  - a failed tick keeps a loaded head's tile (and a head that was empty stays
    "empty"), still updates the printer's state badge, and shows
    #printer-status-read-notice above the tiles; the next good tick redraws
    and hides it;
  - a failed FIRST tick (nothing drawn yet) draws every head "? not read",
    never "empty", and says it couldn't read;
  - the widget's own fan-out reads each head strictly (&strict=1), so a head
    whose read fails keeps its tile and the notice shows;
  - a failed tick keeps the table's counts without redrawing it (a row it never
    counted shows "?", never a confident 0/N) and shows #loc-read-notice; a good
    tick redraws the counts and clears it; a first failed tick draws only "?";
  - the page's own /api/locations fetch reads the X-FCC-Spool-Read header the
    same way;
  - the heartbeat hands `spool_read` to both renderers;
  - a payload without `spool_read` draws exactly as before (empty heads, 0/4);
  - both notices and the "? not read" tiles pass the contrast guard, the
    widget's in its collapsed view too (the notice sits outside the body the
    collapsed view hides).

Proven RED on the bundle tip a5d8cb8, except the two "as before" controls.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import conftest

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
GLOBAL_CSS = HUB / "static" / "css" / "global.css"

# Set up before the modules load: the registerShortcut queue (scripts.html's
# shim) and a fetch that answers from window.__answers, keyed by URL prefix (the
# longest matching prefix wins; each key's list is used in turn and its last
# answer repeats; {pending: true} never settles). Answers are real Responses, so
# a header reads as it would from the server.
PRELUDE = r"""
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__fetches = [];
window.__answers = {};
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.fetch = function (url) {
    const u = String(url);
    window.__fetches.push(u);
    const key = Object.keys(window.__answers).filter((p) => u.startsWith(p))
        .sort((a, b) => b.length - a.length)[0];
    const list = key ? window.__answers[key] : null;
    const a = list ? (list.length > 1 ? list.shift() : list[0]) : { status: 404, body: {} };
    if (a && a.pending) return new Promise(() => {});
    const headers = Object.assign({ 'Content-Type': 'application/json' }, (a && a.headers) || {});
    return Promise.resolve(new Response(JSON.stringify(a && a.body !== undefined ? a.body : {}),
                                        { status: (a && a.status) || 200, headers }));
};
"""

# The dashboard's widget markup (templates/dashboard.html) and the Location
# List's table (templates/components/modals_loc_mgr.html), trimmed.
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<div id="printer-status-widget" class="fcc-ps-widget fcc-ps-loading">
    <div class="fcc-ps-header">
        <div class="fcc-ps-header-bar">
            <span class="fcc-ps-toggle">▾</span>
            <span class="fcc-ps-title">🖨️ Printer Status</span>
            <span class="fcc-ps-hint">click to collapse</span>
        </div>
        <div class="fcc-ps-header-chips"></div>
    </div>
    <div class="fcc-ps-body">
        <div class="fcc-ps-skeleton text-secondary fw-bold" style="padding: 0.5rem 0;">Loading printer status…</div>
    </div>
</div>
<div id="loc-mgr-body" class="modal-body p-0" style="background:#212529;">
    <div class="d-flex justify-content-between align-items-center p-3 border-bottom bg-dark">
        <span id="loc-count" class="text-info fw-bold fcc-loc-count">Loading...</span>
        <button id="loc-pin-printers-btn" class="btn btn-outline-warning">📌 Pin Printers</button>
    </div>
    <div class="table-responsive max-h-70vh">
        <table class="table table-dark table-hover mb-0">
            <thead class="sticky-th"><tr><th>ID</th><th>Name</th><th>Type</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody id="location-table"></tbody>
        </table>
    </div>
</div>
</body></html>"""


@pytest.fixture
def pg(isolated_page):
    page = isolated_page
    page.set_content(PAGE.format(css=GLOBAL_CSS.read_text(encoding="utf-8")))
    page.add_script_tag(content=PRELUDE)
    for name in ("overlay_mount.js", "inv_core.js", "inv_printer_status.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    yield page
    assert page.evaluate("window.__errors") == []


# --- the server's answers ------------------------------------------------------

PRINTER = "ZZ Read Printer"
UP = {"ok": True, "error": None}
DOWN = {"ok": False, "error": "Spoolman didn't answer (Read timed out. (read timeout=5))"}


def _item(sid):
    return {"id": sid, "display": f"#{sid} Read Test", "color": "1f3a5f", "color_direction": "longitudinal",
            "remaining_weight": 600, "initial_weight": 1000, "details": {"material": "PLA"}}


def _status(heads, state="IDLE"):
    """printer_status as the server builds it: one printer, heads ZR-1 / ZR-2."""
    return {PRINTER: {
        "state": {"state": state, "is_active": state == "PRINTING"},
        "toolheads": [{"id": tid, "position": pos, "item": it, "unbound": False,
                       "loaded_count": 1 if it else 0}
                      for pos, (tid, it) in enumerate(heads)],
    }}


GOOD = _status([("ZR-1", _item(57)), ("ZR-2", None)], "PRINTING")
GOOD_58 = _status([("ZR-1", _item(58)), ("ZR-2", None)], "PRINTING")
# What the server answers when its spool read failed: every head empty.
FAILED = _status([("ZR-1", None), ("ZR-2", None)], "IDLE")


def _rows(counts, extra=()):
    """The /api/locations rows: {LocationID: (Occupancy, OccupancyRaw)}."""
    occ = dict(counts)
    rows = [{"LocationID": "Unassigned", "Name": "Workbench / Unsorted", "Type": "Virtual",
             "Occupancy": occ["Unassigned"][0], "Max Spools": 0, "parent_id": None, "Synthesized": True},
            {"LocationID": "ZZ-RD", "Name": "Read Room", "Type": "Room", "Max Spools": "0",
             "Occupancy": occ["ZZ-RD"][0], "OccupancyRaw": occ["ZZ-RD"][1], "parent_id": None},
            {"LocationID": "ZZ-RD-1", "Name": "Read Box", "Type": "Dryer Box", "Max Spools": "4",
             "Occupancy": occ["ZZ-RD-1"][0], "OccupancyRaw": occ["ZZ-RD-1"][1], "parent_id": "ZZ-RD"}]
    for lid in extra:
        rows.append({"LocationID": lid, "Name": "New Box", "Type": "Dryer Box", "Max Spools": "4",
                     "Occupancy": occ[lid][0], "OccupancyRaw": occ[lid][1], "parent_id": "ZZ-RD"})
    rows.append({"LocationID": "UNKNOWN", "Name": "Unknown (Physically Lost)", "Type": "Unknown",
                 "Occupancy": occ["UNKNOWN"][0], "Max Spools": 0, "parent_id": None, "Synthesized": True})
    return rows


ROWS_GOOD = _rows({"Unassigned": ("3 items", None), "ZZ-RD": ("2 Total", 2), "ZZ-RD-1": ("2/4", 2),
                   "UNKNOWN": ("1 items", None)})
ROWS_GOOD_1 = _rows({"Unassigned": ("4 items", None), "ZZ-RD": ("1 Total", 1), "ZZ-RD-1": ("1/4", 1),
                     "UNKNOWN": ("1 items", None)})
_ZEROS = {"Unassigned": ("0 items", None), "ZZ-RD": ("0 Total", 0), "ZZ-RD-1": ("0/4", 0),
          "UNKNOWN": ("0 items", None), "ZZ-RD-2": ("0/4", 0)}
# What the server answers when its spool read failed: every count 0.
ROWS_FAILED = _rows(_ZEROS)
# ...and with a box added since the last good answer (no count of its own).
ROWS_FAILED_NEW = _rows(_ZEROS, extra=("ZZ-RD-2",))


# --- reading the page ----------------------------------------------------------

WIDGET_JS = r"""() => {
    const w = document.getElementById('printer-status-widget');
    const squash = (s) => String(s || '').replace(/\s+/g, ' ').trim();
    const tiles = [...w.querySelectorAll('.fcc-ps-body .fcc-ps-th')].map((t) => ({
        head: t.dataset.toolhead, spool: t.dataset.spoolId || null, text: squash(t.textContent) }));
    const minis = [...w.querySelectorAll('.fcc-ps-header-chips .fcc-ps-mini')].map((m) => ({
        text: squash(m.textContent), title: m.title }));
    const badge = squash((w.querySelector('.fcc-ps-body .fcc-ps-state') || {}).textContent);
    const n = document.getElementById('printer-status-read-notice');
    const notice = n ? { shown: getComputedStyle(n).display !== 'none', text: n.textContent, title: n.title,
                         role: n.getAttribute('role'), parent: n.parentElement === w,
                         beforeBody: n.nextElementSibling === w.querySelector('.fcc-ps-body') } : null;
    return { tiles, minis, badge, notice };
}"""

TABLE_JS = r"""() => {
    const squash = (s) => String(s || '').replace(/\s+/g, ' ').trim();
    const cells = {};
    document.querySelectorAll('#location-table tr[data-locid]').forEach((tr) => {
        cells[tr.dataset.locid] = squash(tr.querySelector('.col-status').textContent);
    });
    const n = document.getElementById('loc-read-notice');
    const notice = n ? { shown: getComputedStyle(n).display !== 'none', text: n.textContent, title: n.title,
                         role: n.getAttribute('role'),
                         beforeTable: n.nextElementSibling === document.querySelector('.table-responsive') } : null;
    const rows = {};
    (state.allLocations || []).forEach((r) => { rows[String(r.LocationID).toUpperCase()] = r.Occupancy; });
    return { cells, notice, rows, unread: document.querySelectorAll('#location-table .loc-count-unread').length,
             html: document.getElementById('location-table').innerHTML };
}"""


def _widget(page):
    return page.evaluate(WIDGET_JS)


def _table(page):
    return page.evaluate(TABLE_JS)


def _shown(notice):
    return bool(notice and notice["shown"])


def _aggregate(page, rows, read=None):
    page.evaluate("([r, s]) => window.refreshPrinterStatusWidgetFromAggregate(r, s || undefined)", [rows, read])


def _locations(page, rows, read=None):
    page.evaluate("([d, s]) => window._renderLocationsPayload(d, s || undefined)", [rows, read])


# --- the Printer Status widget -------------------------------------------------

def test_a_failed_tick_keeps_the_tiles_and_says_so(pg):
    """The heart of reads-1 for the widget: Spoolman times out on one tick.
    The loaded head keeps its spool, the empty head stays empty (its last
    answer), the printer's state badge (read from the printer, not Spoolman)
    still updates, and the notice says why. The next good tick redraws."""
    _aggregate(pg, GOOD, UP)
    good = _widget(pg)
    _aggregate(pg, FAILED, DOWN)
    failed = _widget(pg)
    _aggregate(pg, GOOD_58, UP)
    after = _widget(pg)

    assert [(t["head"], t["spool"]) for t in good["tiles"]] == [("ZR-1", "57"), ("ZR-2", None)], good
    assert not _shown(good["notice"]), good
    assert failed["tiles"] == good["tiles"], "a failed read redrew the tiles"
    assert "empty" in failed["tiles"][1]["text"], failed
    assert failed["minis"] == good["minis"], failed
    assert good["badge"] == "PRINTING" and failed["badge"] == "IDLE", (good, failed)
    n = failed["notice"]
    assert _shown(n) and n["role"] == "status", n
    assert "Spoolman didn't answer" in n["text"] and "These tiles are from its last answer" in n["text"], n
    assert "timed out" in n["title"], n
    assert n["parent"] and n["beforeBody"], "the notice sits above the tiles, outside the body"
    assert after["tiles"][0]["spool"] == "58", after
    assert not _shown(after["notice"]) and after["notice"]["text"] == "", after


def test_failed_ticks_in_a_row_keep_the_last_good_tiles(pg):
    _aggregate(pg, GOOD, UP)
    for _ in range(3):
        _aggregate(pg, FAILED, DOWN)
    w = _widget(pg)
    assert w["tiles"][0]["spool"] == "57" and _shown(w["notice"]), w


def test_a_failed_first_tick_draws_no_head_empty(pg):
    """Nothing drawn yet and Spoolman down: every head says "? not read"
    (expanded and collapsed), none says "empty", and the notice says it
    couldn't read (no "last answer" to speak of)."""
    _aggregate(pg, FAILED, DOWN)
    w = _widget(pg)
    assert [t["head"] for t in w["tiles"]] == ["ZR-1", "ZR-2"], w
    for t in w["tiles"]:
        assert "not read" in t["text"] and "empty" not in t["text"] and t["spool"] is None, t
    # Folded (Group 50.1), an unread head is its label and a "?", and its
    # tooltip says Spoolman didn't answer; never "empty".
    assert len(w["minis"]) == 2 and all(
        m["text"].endswith("?") and "didn't answer" in m["title"] and "empty" not in m["text"] + m["title"]
        for m in w["minis"]), w
    assert _shown(w["notice"]) and "Spoolman didn't answer" in w["notice"]["text"], w
    assert "last answer" not in w["notice"]["text"], w
    # The next good tick draws the real tiles.
    _aggregate(pg, GOOD, UP)
    w2 = _widget(pg)
    assert w2["tiles"][0]["spool"] == "57" and "empty" in w2["tiles"][1]["text"], w2
    assert not _shown(w2["notice"]), w2


def test_a_payload_without_spool_read_draws_as_before(pg):
    """An older server, or a direct call: no `spool_read`, no change. The
    failed-looking answer is drawn empty and no notice shows. A control
    (passes on the base too)."""
    _aggregate(pg, GOOD)
    _aggregate(pg, FAILED)
    w = _widget(pg)
    assert [t["spool"] for t in w["tiles"]] == [None, None], w
    assert all("empty" in t["text"] for t in w["tiles"]), w
    assert not _shown(w["notice"]), w


FANOUT = {
    "/api/printer_map": [{"body": {"printers": {PRINTER: [{"location_id": "ZR-1", "position": 0},
                                                          {"location_id": "ZR-2", "position": 1}]}}}],
    "/api/machine/": [{"body": {"toolheads": {"ZR-1": [{"box": "ZZ-BOX"}], "ZR-2": [{"box": "ZZ-BOX"}]},
                                "printer_pool": []}}],
    # The plain read answers [] on a blip (what the base asked for, and drew).
    "/api/get_contents?id=ZR-1": [{"body": [_item(57)]}, {"body": []}],
    "/api/get_contents?id=ZR-2": [{"body": []}],
    # The strict read answers the route's 502 on a blip.
    "/api/get_contents?id=ZR-1&strict=1": [
        {"body": [_item(57)]},
        {"status": 502, "body": {"error": "Couldn't read ZR-1 from Spoolman (Read timed out.)."}}],
    "/api/get_contents?id=ZR-2&strict=1": [{"body": []}],
}

_REFRESH = "() => Promise.race([window.refreshPrinterStatusWidget(), new Promise((r) => setTimeout(r, 5000))])"


def test_the_fan_out_reads_strictly_and_keeps_a_head_it_couldnt_read(pg):
    """The widget's own refresh (after a local change, and within 15 s of one
    on every tick) read each head with the plain /api/get_contents, which
    answers [] on a blip and drew the head empty. It reads strictly now: a 502
    keeps the head's tile and shows the notice."""
    pg.evaluate("(a) => { window.__answers = a; }", FANOUT)
    pg.evaluate(_REFRESH)
    first = _widget(pg)
    pg.evaluate(_REFRESH)
    second = _widget(pg)
    reads = [u for u in pg.evaluate("window.__fetches") if u.startswith("/api/get_contents")]

    assert [(t["head"], t["spool"]) for t in first["tiles"]] == [("ZR-1", "57"), ("ZR-2", None)], first
    assert not _shown(first["notice"]), first
    assert reads and all(u.endswith("&strict=1") for u in reads), reads
    assert second["tiles"] == first["tiles"], "a failed read redrew the head"
    assert _shown(second["notice"]) and "These tiles are from its last answer" in second["notice"]["text"], second


# --- the Locations table -------------------------------------------------------

def test_a_failed_tick_keeps_the_counts_without_a_redraw_and_says_so(pg):
    """The heart of reads-1 for the table: one failed read keeps every count
    (no flip to 0/4, not even a redraw), and the notice says why; the next
    good read redraws the counts and clears it."""
    _locations(pg, ROWS_GOOD, UP)
    good = _table(pg)
    pg.evaluate("document.querySelector('#location-table tr').setAttribute('data-probe', 'kept')")
    _locations(pg, ROWS_FAILED, DOWN)
    failed = _table(pg)
    probe = pg.evaluate("!!document.querySelector('#location-table tr[data-probe]')")
    _locations(pg, ROWS_GOOD_1, UP)
    after = _table(pg)

    assert good["cells"] == {"UNASSIGNED": "3 items", "ZZ-RD": "2 Total", "ZZ-RD-1": "2/4",
                             "UNKNOWN": "1 items"}, good
    assert failed["cells"] == good["cells"], failed
    assert probe, "a failed read redrew the table"
    n = failed["notice"]
    assert _shown(n) and n["role"] == "status" and n["beforeTable"], n
    assert "Spoolman didn't answer" in n["text"] and "These counts are from its last answer" in n["text"], n
    assert "A ?" not in n["text"] and "timed out" in n["title"], n
    assert failed["rows"]["ZZ-RD-1"] == "2/4", failed["rows"]     # state.allLocations too
    assert after["cells"]["ZZ-RD-1"] == "1/4" and after["cells"]["UNASSIGNED"] == "4 items", after
    assert not _shown(after["notice"]) and after["notice"]["text"] == "", after


def test_a_row_with_no_earlier_count_shows_a_question_mark(pg):
    """A box added since the last good read has no count to keep: "?", never a
    confident "0/4" with its ⚠️ Empty Capacity mark. Every other reader of
    state.allLocations sees '--' (the Location Manager's title then shows no
    count)."""
    _locations(pg, ROWS_GOOD, UP)
    _locations(pg, ROWS_FAILED_NEW, DOWN)
    t = _table(pg)
    assert t["cells"]["ZZ-RD-2"] == "?" and t["unread"] == 1, t
    assert t["cells"]["ZZ-RD-1"] == "2/4", t
    assert "0/4" not in t["html"] and "Empty Capacity" not in t["html"], t["html"]
    assert t["rows"]["ZZ-RD-2"] == "--", t["rows"]
    assert "These counts are from its last answer" in t["notice"]["text"], t
    assert "A ? is a count it couldn't read" in t["notice"]["text"], t


def test_a_failed_first_read_draws_no_count_at_all(pg):
    """Nothing counted yet and Spoolman down: every count is "?", none is 0."""
    _locations(pg, ROWS_FAILED, DOWN)
    t = _table(pg)
    assert set(t["cells"].values()) == {"?"}, t
    assert "0/4" not in t["html"] and "0 items" not in t["html"] and "Empty Capacity" not in t["html"], t
    assert _shown(t["notice"]) and "last answer" not in t["notice"]["text"], t
    _locations(pg, ROWS_GOOD, UP)
    t2 = _table(pg)
    assert t2["cells"]["ZZ-RD-1"] == "2/4" and not _shown(t2["notice"]) and t2["unread"] == 0, t2


def test_a_locations_payload_without_spool_read_draws_as_before(pg):
    """A control (passes on the base too): no outcome, today's zeros."""
    _locations(pg, ROWS_GOOD)
    _locations(pg, ROWS_FAILED)
    t = _table(pg)
    assert t["cells"]["ZZ-RD-1"].startswith("0/4") and "Empty Capacity" in t["html"], t
    assert not _shown(t["notice"]), t


def _settled_locations(page, count):
    """Wait until `count` /api/locations answers have been drawn (or the
    notice shows), whichever the page does."""
    page.wait_for_function(
        """(n) => window.__fetches.filter((u) => u === '/api/locations').length >= n
                  && !!document.querySelector('#location-table tr[data-locid]')""", arg=count, timeout=5000)
    page.wait_for_timeout(150)


def test_the_pages_own_locations_fetch_reads_the_header(pg):
    """fetchLocations (every Location List open, sort and pin) reads the
    X-FCC-Spool-Read header: 'failed' keeps the counts like a failed tick."""
    pg.evaluate("(a) => { window.__answers = a; }", {"/api/locations": [
        {"body": ROWS_GOOD, "headers": {"X-FCC-Spool-Read": "ok"}},
        {"body": ROWS_FAILED, "headers": {"X-FCC-Spool-Read": "failed"}},
    ]})
    pg.evaluate("window.fetchLocations()")
    _settled_locations(pg, 1)
    good = _table(pg)
    pg.evaluate("window.fetchLocations()")
    _settled_locations(pg, 2)
    failed = _table(pg)
    assert good["cells"]["ZZ-RD-1"] == "2/4", good
    assert failed["cells"] == good["cells"], failed
    assert _shown(failed["notice"]), failed


# --- the heartbeat -------------------------------------------------------------

def test_the_heartbeat_hands_spool_read_to_both_renderers(pg):
    """One good tick, then one whose read failed: the tiles and the counts
    stay, and both notices show. Later ticks never settle."""
    pg.evaluate("(a) => { window.__answers = a; }", {"/api/dashboard_pulse": [
        {"body": {"locations": ROWS_GOOD, "printer_status": GOOD, "spool_read": UP}},
        {"body": {"locations": ROWS_FAILED, "printer_status": FAILED, "spool_read": DOWN}},
        {"pending": True},
    ]})
    pg.evaluate("window._dashboardPulseTickOnce()")
    pg.wait_for_function("!!document.querySelector('#printer-status-widget .fcc-ps-th[data-spool-id=\"57\"]')",
                         timeout=5000)
    pg.evaluate("window._dashboardPulseTickOnce()")
    pg.wait_for_function("window.__fetches.filter((u) => u.startsWith('/api/dashboard_pulse')).length >= 2",
                         timeout=5000)
    pg.wait_for_function("document.querySelector('#printer-status-widget .fcc-ps-state').textContent.trim() === 'IDLE'",
                         timeout=5000)
    w, t = _widget(pg), _table(pg)
    assert w["tiles"][0]["spool"] == "57" and _shown(w["notice"]), w
    assert t["cells"]["ZZ-RD-1"] == "2/4" and _shown(t["notice"]), t
    # The widget took the tick's section: no per-head fan-out on its event.
    assert not [u for u in pg.evaluate("window.__fetches") if u.startswith("/api/get_contents")]


# --- contrast (standing order) ---------------------------------------------------

def _scored(root, element_id):
    """Prove `element_id` is scored at all: the guard walks the root's
    DESCENDANTS (never the root itself), so a notice passed as its own root
    would be checked vacuously. At an impossible ratio it must be reported."""
    return any(o["id"] == element_id for o in conftest.contrast_offenders(root, min_ratio=100))


def test_the_widget_notice_and_unread_tiles_are_readable(pg, assert_contrast):
    _aggregate(pg, FAILED, DOWN)
    widget = pg.locator("#printer-status-widget")
    assert _scored(widget, "printer-status-read-notice")
    assert_contrast(widget)
    # Collapsed: the body is hidden, the notice and the "? not read" chips show.
    pg.evaluate("document.getElementById('printer-status-widget').classList.add('collapsed')")
    assert pg.locator("#printer-status-read-notice").is_visible()
    assert not pg.locator("#printer-status-widget .fcc-ps-body").is_visible()
    assert pg.locator("#printer-status-widget .fcc-ps-ring-unread").first.is_visible()
    assert_contrast(widget)


def test_the_table_notice_and_question_marks_are_readable(pg, assert_contrast):
    _locations(pg, ROWS_FAILED, DOWN)
    body = pg.locator("#loc-mgr-body")
    assert _scored(body, "loc-read-notice")
    offenders = [o for o in conftest.contrast_offenders(body)
                 if o["id"] == "loc-read-notice" or "loc-count-unread" in str(o["className"] or "")]
    assert offenders == [], offenders
    for cell in pg.locator("#location-table td.col-status").all():
        assert_contrast(cell)
