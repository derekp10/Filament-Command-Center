"""Group 62.7: four small ones from Group 55's word check, hermetic.

(a) The location window's Done / Sync QR was CMD:DONE, the text that finishes an audit
    (Done's question) and commits a bulk move: scanned while either ran, it did that
    instead of closing the window, which can be open under a hidden audit or bulk panel.
    It is CMD:CLOSE now, a code only the page reads, which closes the window whatever else
    runs. CMD:DONE belongs to the audit and the bulk move.
(b) EJECT ALL's button and a spool card's 🗑️ weren't stopped during an audit, though their
    scans are: they are refused now with the scan's words, and send nothing. Both wait
    during a bulk move too, as CMD:TRASH: does, and so does the CMD:EJECTALL scan, whose
    "Nuke all?" opened behind the bulk panel and then swallowed the session's scans.
(c) The slot picker drew no 📷 CANCEL QR while it loaded or on its "couldn't read"
    message; it does in both now.
(d) The 📡 pill compared 'HH:MM:SS' clock times as text, so after midnight a line earlier
    than the last-seen time never raised it. Each entry carries `ts` now
    (test_log_entry_ts_62_7.py), and the pill counts by it, stored under
    `fcc.logPill.lastSeenTs`.

(a) and (b) run the real inv_core.js, ui_builder.js, inv_cmd.js and inv_loc_mgr.js under
node (test_audit_page_58_js.py's harness: a real audit session on the stub DOM); (c) and
(d) the real modules in `isolated_page`. RED on the commit before 62.7 unless a test says
it pins what was right.
"""
from __future__ import annotations

import json

import pytest

from test_audit_page_58_js import LM, SESSION, _run
from test_core1_return_ejectall_js import pytestmark  # noqa: F401  (skip without node)
from test_slow_scan_confirms_js import MODULES

# --- (a) the location window's own QR ---------------------------------------------------

def test_the_location_windows_qr_is_close_not_done():
    src = (MODULES / "inv_loc_mgr.js").read_text(encoding="utf-8")
    assert "generateSafeQR('qr-modal-done', 'CMD:CLOSE'" in src
    assert "'qr-modal-done', 'CMD:DONE'" not in src


RUNNING = {
    "an-audit": "await running(SESSION);",
    "a-hidden-audit": "await running(SESSION); panel().querySelector('#fcc-audit-panel-close').onclick();",
    "a-bulk-move": "window.FCC_BULK_MOVE_ENABLED = true; state.bulkMoveActive = true;",
    "nothing": "",
}


@pytest.mark.parametrize("what", list(RUNNING))
def test_its_close_qr_closes_the_window_whatever_runs_and_sends_nothing(tmp_path, what):
    """RED on the commit before 62.7: CMD:CLOSE was no code, and went to the server."""
    res = _run(tmp_path, """
document.getElementById('manageModal').classList.add('show');
document.getElementById('manage-loc-id').value = 'LR-MDB-1';
window.closeManage = () => { __rec.opened = (__rec.opened || []).concat('closed'); };
%s
window.processScan('CMD:CLOSE', 'barcode');
await __settle(40);
return { opened: __rec.opened || [], scans: scans(), audit: !!state.auditActive, bulk: !!state.bulkMoveActive };
""" % RUNNING[what])
    assert res["opened"] == ["closed"] and res["scans"] == [], res
    assert res["audit"] is what.endswith("audit") and res["bulk"] is (what == "a-bulk-move")


def test_cmd_done_still_asks_the_audits_done(tmp_path):
    """A pin: CMD:DONE is the audit's and the bulk move's, and goes to the server."""
    res = _run(tmp_path, """
await running(SESSION);
window.closeManage = () => { __rec.opened = (__rec.opened || []).concat('closed'); };
window.processScan('CMD:DONE', 'barcode');
await __settle(40);
return { opened: __rec.opened || [], scans: scans() };
""")
    assert res["scans"] == ["CMD:DONE"] and res["opened"] == []


# --- (b) EJECT ALL's button and a card's 🗑️ -------------------------------------------

@pytest.mark.parametrize("hidden", [False, True], ids=["panel-up", "panel-hidden"])
def test_eject_all_and_a_cards_trash_wait_for_an_audit_and_send_nothing(tmp_path, hidden):
    """RED on the commit before 62.7: EJECT ALL asked the server and the card's 🗑️ asked
    its question, the audit running."""
    res = _run(tmp_path, """
await running(SESSION);
if (%s) panel().querySelector('#fcc-audit-panel-close').onclick();
__realTriggerEjectAll('LR-MDB-1');
await __settle(40);
__realEjectSpool(99, 'LR-MDB-1', false);
await __settle(40);
return { sent: __rec.fetches.filter(f => f.method !== 'GET' && f.url !== '/api/log_event').map(f => f.url),
         toasts: timed(), safety: __rec.safety, modal: state.activeModal };
""" % json.dumps(hidden), modules=LM)
    assert res["sent"] == [] and res["safety"] == [] and res["modal"] is None, res
    assert [t["msg"] for t in res["toasts"]] == ["Eject All waits until the audit is finished or cancelled.",
                                                 "Eject waits until the audit is finished or cancelled."], res["toasts"]
    assert all(t["type"] == "warning" and t["ms"] == 7000 for t in res["toasts"])


def test_eject_all_its_scan_and_a_cards_trash_wait_for_a_bulk_move(tmp_path):
    """RED on the commit before 62.7: EJECT ALL asked the server, then "Nuke all?" opened
    behind the bulk panel (its scan too), and the card's 🗑️ asked its question."""
    res = _run(tmp_path, """
window.FCC_BULK_MOVE_ENABLED = true; state.bulkMoveActive = true;
document.getElementById('manageModal').classList.add('show');
document.getElementById('manage-loc-id').value = 'LR-MDB-1';
window.triggerEjectAll = __realTriggerEjectAll;
window.ejectSpool = __realEjectSpool;
__realTriggerEjectAll('LR-MDB-1');
await __settle(40);
__realEjectSpool(99, 'LR-MDB-1', false);
await __settle(40);
window.processScan('CMD:EJECTALL', 'barcode');
await __settle(40);
return { sent: __rec.fetches.filter(f => f.method !== 'GET' && f.url !== '/api/log_event').map(f => f.url),
         safety: __rec.safety, modal: state.activeModal, toasts: toasts().map(t => t.msg) };
""", modules=LM)
    assert res["sent"] == [] and res["safety"] == [] and res["modal"] is None, res
    assert sum("waits until the bulk move is finished" in t for t in res["toasts"]) == 3, res["toasts"]


def test_with_nothing_running_eject_all_still_asks_the_server_first(tmp_path):
    """A pin: the control."""
    res = _run(tmp_path, """
window.__extra = ((prev) => (url) => url === '/api/manage_contents' ? { body: { success: true } } : prev(url))(window.__extra);
__realTriggerEjectAll('LR-MDB-1');
await __settle(60);
return { checks: __rec.fetches.filter(f => f.url === '/api/manage_contents').map(f => f.body) };
""", modules=LM)
    assert res["checks"] and res["checks"][0].get("check_only") is True, res


# --- (c) the slot picker's CANCEL QR from the start --------------------------------------

PICKER_STUBS = r"""
window.__qrs = [];
// inv_core.js's generateSafeQR (a top-level const) draws through the QR library's
// QRCode, which this page stands in for: each code drawn is recorded.
window.QRCode = function (el, opts) { window.__qrs.push([el.id, opts.text]); };
window.QRCode.CorrectLevel = { L: 1 };
window.__held = [];
window.fetch = () => new Promise((r) => window.__held.push(() => r({ ok: true, status: 200,
    json: () => Promise.resolve({ read_ok: false, read_error: 'Spoolman did not answer' }) })));
"""


def test_the_slot_picker_draws_its_cancel_qr_while_it_loads_and_on_its_message(isolated_page):
    """RED on the commit before 62.7: neither view drew it, though a cancel scan works there."""
    page = isolated_page
    page.set_content("<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>")
    page.add_script_tag(content=PICKER_STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "slot_picker.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("() => { window.openSlotPicker({ location: 'CR-MDB-1', spool: 6 }); }")
    page.wait_for_selector("#fcc-slot-picker [data-sp-state='loading']")
    cancel_qr = "#fcc-slot-picker [id^='fcc-sp-qr-'][id$='-cancel']"
    assert page.locator(cancel_qr).count() == 1
    page.wait_for_function("() => window.__qrs.filter(([, t]) => t === 'CMD:CANCEL').length === 1")
    page.evaluate("() => window.__held.forEach((f) => f())")
    page.wait_for_selector("#fcc-slot-picker [data-sp-state='message']")
    assert page.locator(cancel_qr).count() == 1
    page.wait_for_function("() => window.__qrs.filter(([, t]) => t === 'CMD:CANCEL').length === 2")


# --- (d) the 📡 pill across midnight ----------------------------------------------------

PILL_PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<button id="fcc-log-pill" style="display:none"><span id="fcc-log-pill-count"></span></button>
</body></html>"""


@pytest.fixture
def pill(isolated_page):
    page = isolated_page
    page.set_content(PILL_PAGE)
    # set_content's page has no origin, so no localStorage of its own: one in memory.
    page.add_script_tag(content="""(() => { const m = new Map();
        Object.defineProperty(window, 'localStorage', { configurable: true, value: {
            getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => { m.set(k, String(v)); },
            removeItem: (k) => { m.delete(k); }, clear: () => { m.clear(); } } }); })();""")
    page.add_script_tag(content="window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({ logs: window.__logs || [] }) });")
    for name in ("overlay_mount.js", "inv_core.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("() => { try { localStorage.clear(); } catch (e) {} }")
    return page


AFTER_MIDNIGHT = [{"time": "00:00:01", "ts": 1_700_000_004_000, "msg": "after", "type": "INFO"},
                  {"time": "23:59:58", "ts": 1_700_000_001_000, "msg": "before", "type": "INFO"}]


def _shown(page):
    return page.evaluate("""() => { const p = document.getElementById('fcc-log-pill');
        return p.style.display === 'none' ? null : document.getElementById('fcc-log-pill-count').innerText; }""")


def test_a_line_after_midnight_raises_the_pill(pill):
    """Seen up to the 23:59:58 line: the 00:00:01 line is new. RED on the commit before
    62.7: '00:00:01' sorted before '23:59:58', and the pill stayed hidden."""
    pill.evaluate("""() => { localStorage.setItem('fcc.logPill.lastSeenTime', '23:59:58');
        localStorage.setItem('fcc.logPill.lastSeenTs', '1700000001000'); }""")
    pill.evaluate("(logs) => _updateLogPill(logs)", AFTER_MIDNIGHT)
    assert _shown(pill) == "1"


def test_an_old_stored_time_hides_no_new_line_once(pill):
    """Only the old key stored (an FCC before 62.7): it reads as nothing seen. RED on the
    commit before 62.7: '23:59:59' hid both."""
    pill.evaluate("() => localStorage.setItem('fcc.logPill.lastSeenTime', '23:59:59')")
    pill.evaluate("(logs) => _updateLogPill(logs)", AFTER_MIDNIGHT)
    assert _shown(pill) == "2"


def test_opening_the_list_marks_every_line_seen_by_its_ts(pill):
    pill.evaluate("(logs) => { window.__logs = logs; window.openLogPillOverlay(); }", AFTER_MIDNIGHT)
    pill.wait_for_function("() => localStorage.getItem('fcc.logPill.lastSeenTs') === '1700000004000'")
    pill.evaluate("(logs) => _updateLogPill(logs)", AFTER_MIDNIGHT)
    assert _shown(pill) is None


def test_an_entry_from_an_older_fcc_is_compared_as_before(pill):
    """A pin: an entry with no `ts` keeps the text compare."""
    pill.evaluate("() => localStorage.setItem('fcc.logPill.lastSeenTime', '12:00:00')")
    pill.evaluate("(logs) => _updateLogPill(logs)", [{"time": "13:00:00", "msg": "a"}, {"time": "11:00:00", "msg": "b"}])
    assert _shown(pill) == "1"


def test_opening_the_list_marks_seen_up_to_its_newest_line_wherever_it_sits(pill):
    """The review of Group 62: two lines logged at once by two threads could reach the
    list out of their stamps' order, and opening the list saved its first line's stamp,
    not the newest, so the newer line read as new right after the list was read. The page
    keeps the newest stamp now (and state.py stamps a line and puts it in the list under
    one lock: test_log_entry_ts_62_7.py). RED before the review's fix: '1700000004000'."""
    out_of_order = [{"time": "10:00:04", "ts": 1_700_000_004_000, "msg": "a", "type": "INFO"},
                    {"time": "10:00:04", "ts": 1_700_000_004_001, "msg": "b", "type": "INFO"}]
    pill.evaluate("(logs) => { window.__logs = logs; window.openLogPillOverlay(); }", out_of_order)
    pill.wait_for_function("() => localStorage.getItem('fcc.logPill.lastSeenTs') !== null")
    assert pill.evaluate("() => localStorage.getItem('fcc.logPill.lastSeenTs')") == "1700000004001"
    pill.evaluate("(logs) => _updateLogPill(logs)", out_of_order)
    assert _shown(pill) is None
