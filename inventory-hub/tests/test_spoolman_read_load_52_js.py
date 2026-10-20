"""Group 52 (Spoolman read load & honest empties), the frontend half: the REAL
modules under node's `vm` (the harness of test_core1_return_ejectall_js.py, plus
a recorder for document listeners so a scenario can fire one). No browser, no
container: runs under --offline.

  52.1a  the heartbeat asks for label_backlog unless the backlog window is open;
         the backlog button takes its count from it (and keeps it when the
         section couldn't read Spoolman); the window's own poll runs only while
         it is open, and a failed refresh keeps its rows;
  52.1b  the Location Manager's open / refresh read strictly: a read that fails
         keeps the cards (a fresh open draws none) and says Spoolman didn't
         answer; an empty box still draws EMPTY; the heartbeat's manage section
         routes the same way;
  52.1c  the Quick-Swap grid makes ONE contents request for every feeding box;
         when it fails, nothing is drawn empty, and a heartbeat refresh keeps
         the tiles it drew.

Each test was run against the base modules (52741e6) and failed there.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from test_core1_return_ejectall_js import (  # noqa: F401  (pytestmark: skip without node)
    DRIVER_JS, MODULES, NODE, RESULT_MARK, pytestmark)

# Record document listeners (the shared stub drops them) so a scenario can fire
# one with __fire(type, detail). Nothing fires unless a scenario asks.
EVENTS_JS = r"""
  globalThis.__docListeners = {};
  globalThis.document.addEventListener = (type, fn) => {
    (globalThis.__docListeners[type] = globalThis.__docListeners[type] || []).push(fn);
  };
  globalThis.__fire = (type, detail) => {
    for (const fn of (globalThis.__docListeners[type] || [])) fn({ type, detail });
  };
"""
_HOOK = "  globalThis.__settle = async"
assert _HOOK in DRIVER_JS, "the shared node driver changed; re-anchor EVENTS_JS"
EVENT_DRIVER_JS = DRIVER_JS.replace(_HOOK, EVENTS_JS + _HOOK, 1)


def run(tmp_path: Path, modules: list, scenario: str) -> dict:
    driver = (EVENT_DRIVER_JS
              .replace("__MODULE_PATHS__", json.dumps([str(MODULES / m) for m in modules]))
              .replace("__SCENARIO__", scenario))
    script = tmp_path / "driver.js"
    script.write_text(driver, encoding="utf-8")
    proc = subprocess.run([NODE, str(script)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(RESULT_MARK)]
    assert proc.returncode == 0 and lines, (
        f"node driver failed (rc={proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    out = json.loads(lines[-1][len(RESULT_MARK):])
    res = {**out["result"], "unhandled": out["unhandled"]}
    assert res["unhandled"] == [], res
    return res


# ---------------------------------------------------------------------------
# 52.1a: the heartbeat
# ---------------------------------------------------------------------------

def test_the_heartbeat_asks_for_the_backlog_count_unless_the_window_is_open(tmp_path):
    """The count rides the heartbeat; while the backlog window is open its own
    list fetch sets the button (filtered by the window), so the tick leaves it."""
    res = run(tmp_path, ["inv_core.js"], """
const closed = window._computePulseInclude();
document.getElementById('backlogModal').classList.add('show');
const open = window._computePulseInclude();
document.getElementById('backlogModal').classList.remove('show');
document.getElementById('manageModal').classList.add('show');
document.getElementById('manage-loc-id').value = 'LR-MDB-1';
const manage = window._computePulseInclude();
return { closed, open, manage };
""")
    assert "label_backlog" in res["closed"]["sections"], res
    assert "label_backlog" not in res["open"]["sections"], res
    assert "manage" in res["manage"]["sections"] and res["manage"]["manageId"] == "LR-MDB-1", res


PULSE = """
const calls = { render: [], fail: [], count: [] };
window._renderManagePayload = (id, d) => { calls.render.push([id, d]); return true; };
window._showManageReadFailure = (id, why) => { calls.fail.push([id, why]); return true; };
window._renderBacklogCount = (sec) => { calls.count.push(sec); return true; };
const payloads = __PAYLOADS__;
let n = 0;
window.__respond = (url) => url.startsWith('/api/dashboard_pulse') ? { body: payloads[n++] } : { body: {} };
for (let i = 0; i < payloads.length; i++) { window._dashboardPulseTickOnce(); await __settle(40); }
return { calls, urls: __rec.fetches.map(f => f.url).filter(u => u.startsWith('/api/dashboard_pulse')) };
"""


def test_the_heartbeat_keeps_the_cards_when_its_manage_section_couldnt_read(tmp_path):
    """A manage section that couldn't read Spoolman (read_ok: false, no
    contents) shows the notice instead of rendering; a real answer, an empty
    one too, renders; the backlog section reaches the button."""
    payloads = [
        {"manage": {"id": "LR-MDB-1", "read_ok": False, "read_error": "couldn't read Spoolman (timeout)"},
         "label_backlog": {"read_ok": True, "count": 4, "spools": 3, "filaments": 1}},
        {"manage": {"id": "LR-MDB-1", "contents": [], "read_ok": True}},
        {"manage": {"id": "LR-MDB-1", "error": "boom"}},
    ]
    res = run(tmp_path, ["inv_core.js"], PULSE.replace("__PAYLOADS__", json.dumps(payloads)))
    calls = res["calls"]
    assert calls["render"] == [["LR-MDB-1", []]], calls
    assert calls["fail"] == [["LR-MDB-1", "couldn't read Spoolman (timeout)"], ["LR-MDB-1", "boom"]], calls
    assert calls["count"] == [payloads[0]["label_backlog"]], calls
    assert all("label_backlog" in u for u in res["urls"]) and len(res["urls"]) == 3, res["urls"]


# ---------------------------------------------------------------------------
# 52.1a: the backlog button and window
# ---------------------------------------------------------------------------

BACKLOG = """
window.getFilamentStyle = () => ({ frame: '#333', inner: '#222', border: false });
const ITEMS = [{ id: 901, type: 'spool', registered: '2026-02-01',
                 filament: { material: 'PLA', name: 'Red', color_hex: 'ff0000', vendor: { name: 'FCC Test' } } }];
const pending = (body) => (url) => url.startsWith('/api/print_queue/pending') ? { body } : { body: {} };
const btn = document.getElementById('btn-backlog-count');
btn.innerHTML = '🏷️ Backlog (0)';
const counts = [];
counts.push([window._renderBacklogCount({ read_ok: true, count: 3, spools: 2, filaments: 1 }), btn.innerHTML]);
counts.push([window._renderBacklogCount({ read_ok: false, read_error: "couldn't read Spoolman" }), btn.innerHTML]);
counts.push([window._renderBacklogCount({ read_ok: true }), btn.innerHTML]);

// Window closed: a heartbeat (or any other) pulse fetches nothing.
window.__respond = pending({ success: true, items: ITEMS });
__fire('inventory:sync-pulse', { source: 'dashboard_pulse' });
__fire('inventory:sync-pulse', { source: 'eject' });
await __settle(40);
const closedFetches = __rec.fetches.length;

// Window open: each pulse refreshes its list.
document.getElementById('backlogModal').classList.add('show');
__fire('inventory:sync-pulse', { source: 'dashboard_pulse' });
await __settle(40);
const list = document.getElementById('backlog-list');
const notice = document.getElementById('backlog-read-notice');
const rowsOk = list.innerHTML;
window.__respond = pending({ success: false, msg: "Spoolman didn't answer the spool list (HTTP 503)" });
__fire('inventory:sync-pulse', { source: 'dashboard_pulse' });
await __settle(40);
const rowsAfterFail = list.innerHTML;
const noticeAfterFail = [notice.style.display, notice.textContent];
window.__respond = pending({ success: true, items: ITEMS });
__fire('inventory:sync-pulse', { source: 'dashboard_pulse' });
await __settle(40);
const noticeAfterOk = [notice.style.display, notice.textContent];
return { counts, closedFetches, rowsOk, rowsAfterFail, noticeAfterFail, noticeAfterOk,
         pendingGets: __rec.fetches.filter(f => f.url.startsWith('/api/print_queue/pending')).length };
"""


def test_the_backlog_button_takes_the_heartbeats_count_and_polls_only_while_open(tmp_path):
    """The button used to re-read Spoolman's whole spool and filament lists on
    every pulse. Its count now comes from the heartbeat (kept when that couldn't
    read Spoolman); the window polls only while it is open, and a refresh that
    fails keeps its rows and says so (it used to replace them with the error,
    and the next good answer, matching the last hash, never redrew them)."""
    res = run(tmp_path, ["inv_backlog.js"], BACKLOG)
    assert res["counts"] == [[True, "🏷️ Backlog (3)"], [False, "🏷️ Backlog (3)"], [False, "🏷️ Backlog (3)"]], res
    assert res["closedFetches"] == 0, res
    assert "backlog-row" in res["rowsOk"] and "#901" in res["rowsOk"], res
    assert res["rowsAfterFail"] == res["rowsOk"], "a failed refresh wiped the rows"
    assert res["noticeAfterFail"][0] == "block" and "HTTP 503" in res["noticeAfterFail"][1], res
    assert "Showing the last list" in res["noticeAfterFail"][1], res
    assert res["noticeAfterOk"] == ["none", ""], res
    assert res["pendingGets"] == 3, res


LOAD = """
window.getFilamentStyle = () => ({ frame: '#333', inner: '#222', border: false });
window.__respond = (url) => url.startsWith('/api/print_queue/pending')
    ? { body: { success: true, items: [] } } : { body: {} };
if (__FED__) window._renderBacklogCount({ read_ok: true, count: 2 });
const delays = [];
const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms) => { delays.push(ms); fn(); return 0; };
__fire('DOMContentLoaded');
globalThis.setTimeout = realSetTimeout;
await __settle(30);
return { delays, pendingGets: __rec.fetches.filter(f => f.url.startsWith('/api/print_queue/pending')).length };
"""


def test_the_page_load_fetches_the_backlog_only_if_no_heartbeat_counted_it(tmp_path):
    """Every load used to fetch the whole backlog 1.5 s in; the first heartbeat
    (100 ms in) carries the count now, and the load fetches it only as a
    fallback."""
    fed = run(tmp_path, ["inv_backlog.js"], LOAD.replace("__FED__", "true"))
    assert fed["pendingGets"] == 0, fed
    starved = run(tmp_path, ["inv_backlog.js"], LOAD.replace("__FED__", "false"))
    assert starved["pendingGets"] == 1, starved
    assert fed["delays"] == starved["delays"] == [10000], (fed, starved)


# ---------------------------------------------------------------------------
# 52.1b: the Location Manager's open and refresh
# ---------------------------------------------------------------------------

# Each answer serves one open or refresh. {"down": true} is Spoolman timing out:
# the strict read answers 502, the plain one [] (what the base read, and drew).
LM = """
window.SpoolCardBuilder = { buildCard: (it) => `CARD#${it.id}` };
state.allLocations = [{ LocationID: 'LR-MDB-1', Type: 'Dryer Box', 'Max Spools': '4' }];
state.locationsLoaded = true;
window.renderFeedsSection = () => {};
window.renderQuickSwapSection = () => {};
const answers = __ANSWERS__;
window.__respond = (url) => {
  if (!url.startsWith('/api/get_contents?id=LR-MDB-1')) return { body: {} };
  const a = answers.shift() || { down: true };
  if (a.down) return url.includes('strict=1')
      ? { status: 502, body: { error: "Couldn't read LR-MDB-1 from Spoolman (Read timed out.)." } }
      : { body: [] };
  return { body: a.body };
};
const snap = () => {
  const n = document.getElementById('manage-read-notice');
  return { grid: document.getElementById('slot-grid-container').innerHTML,
           view: document.getElementById('manage-grid-view').style.display,
           notice: n.style.display || '', text: n.textContent || '' };
};
window.openManage('LR-MDB-1');
await __settle(60);
const opened = snap();
window.refreshManageView('LR-MDB-1');
await __settle(60);
const refreshed = snap();
const elsewhere = window._showManageReadFailure ? window._showManageReadFailure('XL-1', 'x') : null;
return { opened, refreshed, elsewhere, toasts: __rec.toasts,
         reads: __rec.fetches.filter(f => f.url.startsWith('/api/get_contents')).map(f => f.url) };
"""
SPOOL = {"id": 57, "display": "#57 PLA Red", "color": "ff0000", "slot": "2", "location": "LR-MDB-1"}


def _lm(tmp_path, answers):
    return run(tmp_path, ["inv_loc_mgr.js"], LM.replace("__ANSWERS__", json.dumps(answers)))


def test_a_refresh_that_cant_read_keeps_the_cards_and_says_so(tmp_path):
    """The heart of 52.1b: Spoolman times out while a box is open. Its cards
    stay, and the notice says Spoolman didn't answer. RED on 52741e6: the plain
    read answered [] and the box was redrawn EMPTY."""
    res = _lm(tmp_path, [{"body": [SPOOL]}, {"down": True}])
    assert "CARD#57" in res["opened"]["grid"] and res["opened"]["notice"] in ("", "none"), res
    assert res["refreshed"]["grid"] == res["opened"]["grid"], "the cards were redrawn"
    assert res["refreshed"]["notice"] == "block", res
    assert "Spoolman didn't answer" in res["refreshed"]["text"], res
    assert "These cards are from its last answer" in res["refreshed"]["text"], res
    assert res["reads"] == ["/api/get_contents?id=LR-MDB-1&strict=1"] * 2, res["reads"]
    assert res["elsewhere"] is False, "a failure about another location is ignored"


def test_an_open_that_cant_read_draws_no_empty_box(tmp_path):
    """A fresh open with Spoolman down draws no slots (no EMPTY tiles) and says
    why; the next answer draws the box and clears the notice. RED on 52741e6."""
    res = _lm(tmp_path, [{"down": True}, {"body": [SPOOL]}])
    assert res["opened"]["grid"] == "" and res["opened"]["view"] == "none", res
    assert res["opened"]["notice"] == "block" and "Spoolman didn't answer" in res["opened"]["text"], res
    assert "These cards" not in res["opened"]["text"], res
    assert "CARD#57" in res["refreshed"]["grid"] and res["refreshed"]["view"] == "block", res
    assert res["refreshed"]["notice"] == "none" and res["refreshed"]["text"] == "", res
    assert res["toasts"] == [], res


def test_a_genuinely_empty_box_still_draws_empty(tmp_path):
    """Control: an answer of [] is an empty box (passes on the base too)."""
    res = _lm(tmp_path, [{"body": []}, {"body": []}])
    assert res["opened"]["grid"].count("EMPTY") == 4 and res["opened"]["view"] == "block", res
    assert res["opened"]["notice"] in ("", "none"), res
    assert res["refreshed"]["grid"].count("EMPTY") == 4, res


# ---------------------------------------------------------------------------
# 52.1c: the Quick-Swap grid's one batched read
# ---------------------------------------------------------------------------

GRID = """
state.printerMap = { 'XL': [{ location_id: 'XL-2', position: 1 }] };
state.heldSpools = __BUFFER__;
window.SpoolCardBuilder = { buildCard: (it) => `CARD#${it.id}` };
window.makeSwatchHtml = () => '';
const batches = __BATCHES__;
window.__respond = (url) => {
  if (url.startsWith('/api/machine/')) return { body: { toolheads: { 'XL-2': [
      { box: 'PM-DB-2', slot: '1', single_slot: true }, { box: 'LR-MDB-1', slot: '2' } ] },
      printer_pool: [{ box: 'LR-MDB-1', slot: '4' }] } };
  if (url.startsWith('/api/get_contents')) {
    // The base asked once per box (?id=), each a whole spool-list read.
    if (!url.startsWith('/api/get_contents?ids=')) return { body: [] };
    return batches.shift() || { status: 500, body: {} };
  }
  return { body: [] };
};
const loc = { LocationID: 'XL-2', Type: 'Tool Head' };
window.renderQuickSwapSection(loc);
await __settle(80);
const first = document.getElementById('quickswap-grid').innerHTML;
window.renderQuickSwapSection(loc, { silent: true });
await __settle(80);
const second = document.getElementById('quickswap-grid').innerHTML;
return { first, second, reads: __rec.fetches.filter(f => f.url.startsWith('/api/get_contents')).map(f => f.url) };
"""
FOLLOWER = {"id": 50, "is_ghost": True, "deployed_to": "XL-2", "location": "PM-DB-2", "slot": ""}
STORED = {"id": 77, "is_ghost": False, "location": "LR-MDB-1", "slot": "2"}
OK = {"body": {"read_ok": True, "read_error": None,
               "contents": {"PM-DB-2": [FOLLOWER], "LR-MDB-1": [STORED]}}}
DOWN = {"body": {"read_ok": False, "read_error": "couldn't read Spoolman (timeout)", "contents": {}}}


def _grid(tmp_path, batches, buffer=()):
    return run(tmp_path, ["inv_quickswap.js"], (GRID
               .replace("__BATCHES__", json.dumps(batches))
               .replace("__BUFFER__", json.dumps([{"id": b, "display": f"#{b}"} for b in buffer]))))


def test_the_grid_reads_every_feeding_box_in_one_request(tmp_path):
    """Two boxes and a Printer Pool slot: one contents request (it was one per
    box, each a whole spool-list read, again on every heartbeat). RED on
    52741e6: two ?id= reads."""
    res = _grid(tmp_path, [OK, OK])
    assert res["reads"] == ["/api/get_contents?ids=PM-DB-2&ids=LR-MDB-1"] * 2, res["reads"]
    assert "CARD#50" in res["first"] and "CARD#77" in res["first"], res["first"]
    assert "attached — follows #50" in res["first"], res["first"]
    assert "empty staging slot" in res["first"], "the pool slot read empty"


def test_a_grid_that_cant_read_draws_no_box_empty(tmp_path):
    """One read serves every box, so when it fails none of them is drawn empty:
    the PolyDryer keeps its strict "couldn't read" header (no Unbind), and the
    multi-slot box's slot and the pool slot say so too, with no deposit tile.
    RED on 52741e6."""
    res = _grid(tmp_path, [DOWN, DOWN], buffer=[88])
    html = res["first"]
    assert "couldn't read PM-DB-2 from Spoolman" in html, html
    assert "fcc-qs-unbind" not in html and "isn't on XL-2" not in html, html
    assert html.count("⚠️ couldn't read LR-MDB-1") == 2, html     # feed slot 2 + pool slot 4
    assert "quickSwapDeposit" not in html and "empty" not in html.replace("text-decoration", ""), html


def test_a_heartbeat_refresh_that_cant_read_keeps_the_tiles(tmp_path):
    """A silent (heartbeat) refresh whose read fails keeps the tiles it drew
    rather than flipping them all to "couldn't read" for one tick."""
    res = _grid(tmp_path, [OK, DOWN])
    assert "CARD#50" in res["first"], res
    assert res["second"] == res["first"], "a failed heartbeat read redrew the grid"
