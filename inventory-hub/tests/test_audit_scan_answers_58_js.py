"""Group 58 on the page: what the audit's scans answer, under the real scan path.

Node's `vm` (test_head_load_confirm_js's harness): the route's own answers go to
the real processScan. Every audit scan used to answer cmd 'clear', and with a spool
in the buffer that raised "Clear entire Buffer?" (#confirmModal, z 1100) behind the
panel (z 20000): state.activeModal then stopped every later scan, a scanned Done
included, with no toast and no log line. The server answers `audit_scan` now, on
which the page does nothing, so the moments after a reload (no heartbeat yet, so
state.auditActive still false) are covered too, which a page guard would not be.

An isolated browser page (the real overlay_mount.js, inv_cmd.js and
duplicate_picker.js, no network, so it runs under --offline): a legacy label several
spools share, scanned in an audit, opens its picker OVER the real panel, and its
pick comes back as ID:<n>. The spec's "try it in a browser" was also run on dev's
real audit and real LEG:6 label (2026-11-02): same result.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import state  # noqa: E402
from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: E402,F401  (pytestmark: skip without node)
from test_head_load_confirm_js import PRELUDE, SCAN  # noqa: E402
from test_scanner_safe_dialogs_61_js import _open_picker, page61  # noqa: E402,F401  (page61: the fixture)

SCANS = ["LOC:LR-MDB-1", "ID:57", "CMD:DONE"]


def _route_answers(monkeypatch):
    """What the real route answers an audit's scans, not a copy of it."""
    monkeypatch.setattr(state, "AUDIT_LAST_END", None)
    monkeypatch.setattr(state, "add_log_entry", lambda *a, **k: None)
    client = app_module.app.test_client()
    state.reset_audit()
    try:
        return [client.post("/api/identify_scan", json={"text": text, "source": "barcode"}).get_json()
                for text in ("CMD:AUDIT", "CMD:AUDIT", "CMD:CANCEL")]
    finally:
        state.reset_audit()


def _scans(tmp_path, answers):
    """Three scans with a spool in the buffer (the prelude's #57), and
    state.auditActive false: a page before its first heartbeat."""
    body = """
window.closeManage = () => {};     // inv_loc_mgr.js's, which this module set doesn't load
answerWith('/api/identify_scan', %s);
for (const text of %s) { window.processScan(text, 'barcode'); await __settle(120); }
return { modal: state.activeModal, pending: !!state.pendingConfirm,
         scans: posts('/api/identify_scan').map((p) => p.text),
         held: state.heldSpools.map((s) => s.id), toasts: toasts().map((t) => t.msg) };
""" % (json.dumps(answers), json.dumps(SCANS))
    res = run_js(tmp_path, SCAN, PRELUDE + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def test_the_routes_audit_answers_raise_nothing_and_stop_nothing(tmp_path, monkeypatch):
    """RED on f6d8c90: the route answered 'clear', the prompt armed on the first
    scan, and the other two never reached the server."""
    res = _scans(tmp_path, _route_answers(monkeypatch))
    assert res["modal"] is None and res["pending"] is False, res
    assert res["scans"] == SCANS, res
    assert res["held"] == [57], res                  # the buffer is kept
    assert res["toasts"] == [], res


def test_the_old_answer_really_did_swallow_the_scans(tmp_path):
    """The control: this harness does see the trap the test above closes."""
    res = _scans(tmp_path, [{"type": "command", "cmd": "clear"}])
    assert res["modal"] == "confirm", res
    assert res["scans"] == SCANS[:1], res


def test_an_answer_that_ended_the_audit_asks_nothing_of_the_page_either(tmp_path):
    res = _scans(tmp_path, [{"type": "command", "cmd": "audit_scan",
                             "audit_ended": {"id": "boot-1", "why": "done"}}])
    assert res["modal"] is None and res["scans"] == SCANS, res


# --- the legacy picker, over the real panel ---------------------------------------

SESSION = {
    "active": True, "audit_id": "boot-1", "location_id": "LR-MDB-1", "note": "", "idle_timeout_min": 30,
    "stats": {"total_expected": 2, "found": 0, "missing": 2, "rogue": 0, "trail": 0},
    "expected": [{"id": 134, "display": "#134 Brand PLA (Black)", "color": "111111",
                  "color_direction": "longitudinal", "remaining_weight": 800, "slot": "1",
                  "location": "LR-MDB-1", "where": "LR-MDB-1 slot 1", "found": False},
                 {"id": 135, "display": "#135 Brand PLA (Black)", "color": "111111",
                  "color_direction": "longitudinal", "remaining_weight": 10, "slot": "2",
                  "location": "LR-MDB-1", "where": "LR-MDB-1 slot 2", "found": False}],
    "rogue": [], "trail": [],
}


@pytest.fixture
def audit_page(page61):
    """The real panel up, on the session's real shape, with an audit running."""
    page61.evaluate("""(session) => {
        const fetchAnswers = window.fetch;
        window.fetch = (url, opts) => String(url).indexOf('/api/audit_session') !== -1
            ? Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(session) })
            : fetchAnswers(url, opts);
        window.__answers['ID:134'] = { type: 'command', cmd: 'audit_scan' };
        window.__answers['ID:135'] = { type: 'command', cmd: 'audit_scan' };
        window.__answers['LOC:LR-MDB-1'] = { type: 'error', msg: 'Already auditing LR-MDB-1. Finish first!' };
        state.auditActive = true;
        window.openAuditPanel();
    }""", SESSION)
    page61.wait_for_function("() => (document.querySelector('#fcc-audit-panel-body') || {}).innerText"
                             " && document.querySelector('#fcc-audit-panel-body').innerText.includes('#134')")
    return page61


def _on_top(page, selector):
    return page.evaluate("""(sel) => { const el = document.querySelector(sel);
        const r = el.getBoundingClientRect();
        return el.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)); }""", selector)


def test_the_legacy_picker_opens_on_top_of_the_audit_panel(audit_page):
    _open_picker(audit_page, choose=134)
    assert _on_top(audit_page, "#fcc-legacy-picker-use")
    assert audit_page.evaluate("window.isTopOverlay(document.getElementById('fcc-legacy-picker-overlay'))")
    assert audit_page.is_visible("#fcc-audit-panel-overlay")       # still there behind it


def test_the_picks_id_comes_back_through_the_scan_path_as_no_label_read(audit_page):
    _open_picker(audit_page, choose=135)
    audit_page.click("#fcc-legacy-picker-use")
    audit_page.wait_for_function("() => window.__ids.some((p) => p.text === 'ID:135')")
    assert audit_page.evaluate("window.__ids[window.__ids.length - 1]") == {"text": "ID:135", "source": "keyboard"}
    assert audit_page.is_visible("#fcc-audit-panel-overlay")
    assert not audit_page.locator("#fcc-legacy-picker-overlay").count()
    # The audit took it: nothing joined the buffer.
    assert audit_page.evaluate("state.heldSpools.length") == 0


def test_escape_closes_only_the_picker_and_the_audit_goes_on(audit_page):
    _open_picker(audit_page, choose=134)
    audit_page.keyboard.press("Escape")
    audit_page.wait_for_selector("#fcc-legacy-picker-overlay", state="detached")
    assert audit_page.is_visible("#fcc-audit-panel-overlay")
    assert audit_page.evaluate("state.auditActive") is True


def test_another_scan_waits_for_the_picker(audit_page):
    _open_picker(audit_page, choose=134)
    sent = audit_page.evaluate("window.__ids.length")
    audit_page.evaluate("window.processScan('LOC:LR-MDB-1', 'barcode')")
    assert audit_page.is_visible("#fcc-legacy-picker-overlay")
    assert audit_page.evaluate("window.__ids.length") == sent


def test_add_new_spool_hides_the_panel_so_the_wizard_can_be_seen(audit_page):
    """The wizard is a Bootstrap window, under the panel: it opened behind it, with
    nothing to show for the click. The panel hides, as Hide does; the audit runs on."""
    audit_page.evaluate("""() => { window.__wizard = [];
        window.openNewSpoolFromFilamentWizard = (fid) => { window.__wizard.push({
            fid, panel: !!document.getElementById('fcc-audit-panel-overlay') }); }; }""")
    _open_picker(audit_page, choose=134)
    audit_page.click("#fcc-legacy-picker-addnew")
    assert audit_page.evaluate("window.__wizard") == [{"fid": 7, "panel": False}]
    assert audit_page.evaluate("state.auditActive") is True


def test_outside_an_audit_add_new_spool_behaves_as_it_did(page61):
    page61.evaluate("""() => { window.__wizard = [];
        window.openNewSpoolFromFilamentWizard = (fid) => { window.__wizard.push(fid); }; }""")
    _open_picker(page61, choose=134)
    page61.click("#fcc-legacy-picker-addnew")
    assert page61.evaluate("window.__wizard") == [7]
