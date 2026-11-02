"""Group 58, build spec sections 7 and 8 on the real dashboard, with Bootstrap and the
page's own polls. Every test but the last answers FCC's routes in this browser, on
their real shapes, so nothing reaches a real session; the last runs one real audit
from the tile through a real park and its Undo, on throwaway dev spools it makes and
deletes, with nothing stubbed.

The logic is proved on the real routes' answers in test_audit_done_question_58_js.py
and test_audit_lost_badges_58_js.py, and on a real DOM in
test_audit_question_dialog_58_js.py; this is the same flows where the real panel, a
hidden Bootstrap dialog and a real heartbeat can get in the way.
"""
from __future__ import annotations

import json

import pytest
import requests
from playwright.sync_api import Page, expect

import conftest
from test_audit_page_58_e2e import DONE, PANEL, PILL, TILE, Server, _dashboard, _start, _toasts
from test_audit_page_58_js import SESSION
from test_audit_question_dialog_58_js import _question

pytestmark = pytest.mark.usefixtures("require_server")

QUESTION = "#fcc-audit-done-question"
SHEET = QUESTION + " .fcc-apc-panel"
YES = QUESTION + " .fcc-apc-yes"
BACK = QUESTION + " .fcc-apc-no"
STATUS = QUESTION + " .fcc-apc-status"
QRS = QUESTION + " .fcc-confirm-qr-row"
AUDIT_ID = SESSION["audit_id"]
PARKED_MSG = "Parked 3 spools at Unknown. Undo Last Move puts them back."


class Asked(Server):
    """Server, with Done answering the question and /api/audit/park an answer of the
    route's shape. `parks` records every Yes."""

    def __init__(self, page, question=None):
        super().__init__(page)
        self.answers["CMD:DONE"] = question or _question()
        self.parks = []
        page.route("**/api/audit/park", self._park)

    def _park(self, route):
        self.parks.append(route.request.post_data_json)
        end = {"id": AUDIT_ID, "why": "done", "location": "LR-MDB-1"}
        self.session = {"active": False, "audit_end": end}
        self.beat.update(audit_active=False, audit_location="", audit_end=end)
        self._json(route, {"success": True, "parked": [100, 101, 102], "stayed": [], "failed": [],
                           "msg": PARKED_MSG, "audit_ended": {"id": AUDIT_ID, "why": "done"}})


def _ask(page: Page):
    page.click(DONE)
    page.wait_for_function("(sel) => document.activeElement === document.querySelector(sel)", arg=BACK)


def _on_top(page: Page, selector: str) -> bool:
    return page.evaluate("""(sel) => { const el = document.querySelector(sel);
        const r = el.getBoundingClientRect();
        return el.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)); }""", selector)


def _scan_keys(page: Page, text: str):
    """Through the real accumulator, as a scanner types."""
    page.keyboard.type(text, delay=0)
    page.keyboard.press("Enter")


def test_the_question_draws_above_the_real_panel_and_opens_on_back(page: Page, base_url: str):
    server = Asked(page)
    _dashboard(page, base_url)
    _start(page)
    _ask(page)
    assert _on_top(page, YES) and _on_top(page, BACK)
    assert page.evaluate("""(sel) => { const r = document.querySelector(sel).getBoundingClientRect();
        return !!document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2).closest('#fcc-audit-done-question'); }""",
                         DONE)
    assert page.text_content(BACK) == "Back to the audit" and page.text_content(YES) == "Park them"
    assert "Park 3 spools at Unknown?" in page.text_content(SHEET)
    assert page.evaluate("state.activeModal") is None
    assert server.parks == []


def test_enter_goes_back_and_a_held_enter_does_nothing(page: Page, base_url: str):
    server = Asked(page)
    _dashboard(page, base_url)
    _start(page)
    page.focus(DONE)
    page.keyboard.down("Enter")                 # presses Done
    page.wait_for_function("(sel) => document.activeElement === document.querySelector(sel)", arg=BACK)
    page.keyboard.down("Enter")                 # its repeats reach the question
    page.keyboard.down("Enter")
    page.wait_for_timeout(120)
    expect(page.locator(QUESTION)).to_be_visible()
    page.keyboard.up("Enter")
    page.wait_for_timeout(120)
    page.keyboard.press("Enter")
    expect(page.locator(QUESTION)).to_have_count(0)
    expect(page.locator(DONE)).to_be_focused()
    assert server.parks == [] and page.evaluate("state.auditActive") is True


def test_a_scans_enter_presses_nothing_and_a_second_done_is_refused(page: Page, base_url: str):
    server = Asked(page)
    _dashboard(page, base_url)
    _start(page)
    _ask(page)
    _scan_keys(page, "CMD:DONE")
    expect(page.locator(STATUS)).to_contain_text("Answer the question on screen first: Park them or Back to the audit")
    expect(page.locator(STATUS)).to_contain_text("(Ignored: CMD:DONE)")
    assert _on_top(page, STATUS)
    assert server.scans == ["CMD:AUDIT", "CMD:DONE"] and server.parks == []
    expect(page.locator(QUESTION)).to_have_count(1)


def test_a_bare_cmd_cancel_closes_only_the_question(page: Page, base_url: str):
    server = Asked(page)
    _dashboard(page, base_url)
    _start(page)
    _ask(page)
    _scan_keys(page, "CMD:CANCEL")
    expect(page.locator(QUESTION)).to_have_count(0)
    expect(page.locator(PANEL)).to_be_visible()
    assert server.scans == ["CMD:AUDIT", "CMD:DONE"] and page.evaluate("state.auditActive") is True


def test_the_qrs_answer_it(page: Page, base_url: str):
    server = Asked(page)
    _dashboard(page, base_url)
    _start(page)
    _ask(page)
    sid = page.evaluate("Object.keys(window._fccActiveConfirms).pop()")
    _scan_keys(page, f"CMD:CANCEL:{sid}")
    expect(page.locator(QUESTION)).to_have_count(0)
    assert server.parks == []
    page.wait_for_timeout(120)                  # past a scanner's CR LF window
    _ask(page)
    sid = page.evaluate("Object.keys(window._fccActiveConfirms).pop()")
    _scan_keys(page, f"CMD:CONFIRM:{sid}")
    expect(page.locator(PANEL)).to_have_count(0)
    assert [p["ids"] for p in server.parks] == [[100, 101, 102]]
    assert server.parks[0]["audit_id"] == AUDIT_ID


def test_a_yes_ends_the_audit_with_no_warning_from_the_heartbeat(page: Page, base_url: str):
    """The panel's poll and the real heartbeat path both see the audit gone."""
    server = Asked(page)
    _dashboard(page, base_url)
    _start(page)
    _ask(page)
    page.click(YES)
    expect(page.locator(PANEL)).to_have_count(0)
    page.wait_for_function("(m) => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                           ".some((e) => e.innerText === m)", arg=PARKED_MSG)
    page.evaluate("() => window._dashboardPulseTickOnce()")
    page.wait_for_timeout(300)
    assert server.logged == [] and not any("ended (" in t for t in _toasts(page))
    expect(page.locator(PILL)).to_be_hidden()
    expect(page.locator(TILE)).to_contain_text("AUDIT")
    assert page.evaluate("getComputedStyle(document.getElementById('processing-overlay')).display") == "none"


def test_close_audit_panel_closes_an_open_question_and_the_heartbeats_end_too(page: Page, base_url: str):
    server = Asked(page)
    _dashboard(page, base_url)
    _start(page)
    _ask(page)
    page.evaluate("window.closeAuditPanel()")
    expect(page.locator(QUESTION)).to_have_count(0)
    assert server.parks == []
    page.click(PILL)
    page.wait_for_selector(DONE)
    _ask(page)
    end = {"id": AUDIT_ID, "why": "idle", "location": "LR-MDB-1"}
    server.session = {"active": False, "audit_end": end}
    server.beat.update(audit_active=False, audit_location="", audit_end=end)
    expect(page.locator(QUESTION)).to_have_count(0, timeout=10_000)
    expect(page.locator(PANEL)).to_have_count(0)
    assert server.parks == []


@pytest.mark.parametrize("size", ["Standard", "Large"])
@pytest.mark.parametrize("park, stays", [(20, 0), (10, 10), (20, 12)])
def test_twenty_spools_fit_with_the_qrs_in_view_on_a_1366_by_768_window(page: Page, base_url: str, park, stays, size):
    """With the real Bootstrap's buttons and line heights, at the Text sizes a laptop
    is likely to run."""
    page.set_viewport_size({"width": 1366, "height": 768})
    page.add_init_script("(() => { try { localStorage.setItem('fcc.textSize', %r); } catch (e) {} })();" % size)
    Asked(page, _question(park, stays))
    _dashboard(page, base_url)
    _start(page)
    _ask(page)
    expect(page.locator(QRS)).to_be_visible()
    page.wait_for_timeout(200)                  # the QR codes draw two frames later
    box = page.evaluate("""([sheet, qrs]) => { const p = document.querySelector(sheet);
        const s = p.getBoundingClientRect(), q = document.querySelector(qrs).getBoundingClientRect();
        return { top: s.top, bottom: s.bottom, qrBottom: q.bottom, vh: innerHeight,
                 scrolls: p.classList.contains('fcc-question-scroll') }; }""", [SHEET, QRS])
    assert not box["scrolls"] and box["top"] >= 0 and box["bottom"] <= box["vh"] and box["qrBottom"] <= box["vh"], box
    assert _on_top(page, QRS + " .fcc-confirm-qr-cell[data-qr='confirm']")
    assert _on_top(page, QRS + " .fcc-confirm-qr-cell[data-qr='cancel']")


def test_the_panels_loose_button_opens_the_list_on_top(page: Page, base_url: str):
    Asked(page)
    page.route("**/api/loose_spools", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"read_ok": True, "read_error": None, "count": 1, "places": [
            {"id": "A-ROOM", "name": "A Room", "type": "Room", "spools": [
                {"id": 8001, "display": "#8001 Some Brand PLA (Gold)", "color": "F9E352",
                 "color_direction": "longitudinal", "remaining_weight": 912}]}]})))
    _dashboard(page, base_url)
    _start(page)
    page.click("#fcc-audit-panel-loose")
    expect(page.locator("#fcc-loose-list .fcc-loose-row.kb-active")).to_have_count(1)
    assert _on_top(page, "#fcc-loose-list .fcc-loose-panel")
    page.keyboard.press("Enter")                # a row opens nothing during an audit
    page.wait_for_timeout(120)
    assert page.evaluate("document.getElementById('manageModal').classList.contains('show')") is False
    page.keyboard.press("Escape")
    expect(page.locator("#fcc-loose-list")).to_have_count(0)
    expect(page.locator(PANEL)).to_be_visible()


def test_the_panels_header_keeps_both_its_buttons_on_a_phone(page: Page, base_url: str):
    page.set_viewport_size({"width": 360, "height": 640})
    Asked(page)
    _dashboard(page, base_url)
    _start(page)
    boxes = page.evaluate("""() => ['#fcc-audit-panel-loose', '#fcc-audit-panel-close'].map((s) => {
        const r = document.querySelector(s).getBoundingClientRect(); return { left: r.left, right: r.right }; })""")
    assert all(b["left"] >= 0 and b["right"] <= 360 for b in boxes), boxes


# --- no stubs ------------------------------------------------------------------------

def _empty_box(api_base_url: str, spoolman: str):
    """A multi-slot dryer box of dev's with nothing filed in it and no spool's trail
    on it, else any cart or drawer with nothing filed: places, not locations.json,
    are what this reads. None when dev has neither."""
    rows = requests.get(f"{api_base_url}/api/locations", timeout=30).json()
    spools = requests.get(f"{spoolman}/api/v1/spool", timeout=30).json()
    taken = set()
    for s in spools:
        taken.add(str(s.get("location") or "").upper())
        taken.add(str((s.get("extra") or {}).get("physical_source") or "").strip('"').upper())
    free = [r for r in rows if str(r.get("LocationID")).upper() not in taken]
    boxes = [r for r in free if r.get("Type") == "Dryer Box" and int(r.get("Max Spools") or 0) >= 2]
    others = [r for r in free if r.get("Type") in ("Cart", "Sliding Drawer")]
    best = (boxes or others or [None])[0]
    return (best["LocationID"], bool(boxes)) if best else (None, False)


def _extra(spoolman: str, sid: int) -> dict:
    rec = requests.get(f"{spoolman}/api/v1/spool/{sid}", timeout=10).json()
    return {"location": rec.get("location"), **{k: json.loads(v) for k, v in (rec.get("extra") or {}).items()}}


def test_a_real_audit_through_the_question_a_real_park_and_its_undo(
        page: Page, base_url: str, api_base_url: str, require_spoolman: str, throwaway_filament,
        throwaway_spool_with_extras):
    """Nothing stubbed but the page's buffer, which is dev's shared one. Three throwaway
    spools in an empty place: one scanned, two parked by the real Yes through the real
    route into dev's real Spoolman, each then saying who lost it, and one real Undo."""
    spoolman = require_spoolman
    if requests.get(f"{api_base_url}/api/audit_session", timeout=10).json().get("active"):
        pytest.skip("an audit is already running on dev")
    if requests.get(f"{api_base_url}/api/bulk_move_session", timeout=10).json().get("active"):
        pytest.skip("a bulk move is armed on dev")
    place, slotted = _empty_box(api_base_url, spoolman)
    if not place:
        pytest.skip("dev has no empty box or cart to audit")
    slots = ("1", "2") if slotted else ("", "")
    found = throwaway_spool_with_extras({}, location=place)["id"]
    first = throwaway_spool_with_extras({"container_slot": slots[0]}, location=place)["id"]
    second = throwaway_spool_with_extras({"container_slot": slots[1]}, location=place)["id"]
    conftest.own_the_buffer(page, [])
    _dashboard(page, base_url)
    page.wait_for_function("() => state.lastAuditState === false", timeout=30_000)
    today = page.evaluate("window.fccLocalDay()")
    try:
        page.click(TILE)
        page.wait_for_selector(DONE)
        page.evaluate("(p) => { window.processScan('LOC:' + p, 'keyboard'); }", place)
        expect(page.locator("#fcc-audit-panel-body")).to_contain_text(f"Auditing {place}")
        page.evaluate("(sid) => { window.processScan('ID:' + sid, 'keyboard'); }", found)
        expect(page.locator("#fcc-audit-panel-body")).to_contain_text("1/3")

        _ask(page)
        sheet = page.locator(SHEET)
        expect(sheet).to_contain_text("Park 2 spools at Unknown?")
        expect(sheet).to_contain_text(f"1 of 3 found at {place}.")
        expect(sheet).to_contain_text(f"#{first} ")
        expect(sheet).to_contain_text(f"#{second} ")
        assert f"#{found} " not in sheet.inner_text()
        page.keyboard.press("Enter")            # Back: nothing moved
        expect(page.locator(QUESTION)).to_have_count(0)
        assert _extra(spoolman, first)["location"] == place

        _ask(page)
        page.click(YES)
        expect(page.locator(PANEL)).to_have_count(0, timeout=30_000)
        expect(page.locator(PILL)).to_be_hidden()
        assert requests.get(f"{api_base_url}/api/audit_session", timeout=10).json()["active"] is False
        page.wait_for_function("() => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                               ".some((e) => e.innerText.includes('Parked 2 spools at Unknown.'))")

        for sid, slot in ((first, slots[0]), (second, slots[1])):
            rec = _extra(spoolman, sid)
            note = f"{place}:{slot}@{today}" if slot else f"{place}@{today}"
            assert rec["location"] == "UNKNOWN" and rec["fcc_pre_audit_location"] == note, rec
            assert rec.get("container_slot", "") == "", rec
        assert _extra(spoolman, found)["location"] == place

        # A lost spool says so: a scan's 7 s toast, its card, the spool window.
        where = f"{place} slot {slots[0]}" if slots[0] else place
        page.evaluate("(sid) => { window.processScan('ID:' + sid, 'keyboard'); }", first)
        turned_up = f"#{first} turned up. It was marked lost by the audit of {where} on {today}. Scan where it goes."
        page.wait_for_function("(m) => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                               ".some((e) => e.innerText === m)", arg=turned_up)
        badge = page.locator(f".buffer-item[data-spool-id='{first}'] .badge.bg-warning").first
        expect(badge).to_have_text(f"❓ Lost: {where}")
        assert badge.get_attribute("title") == f"Marked lost by the audit of {where} on {today}"
        page.evaluate("(sid) => { openSpoolDetails(sid); }", first)
        window_badge = page.locator("#detail-location-badge")
        expect(window_badge).to_have_text(f"❓ Marked lost by the audit of {where} on {today}")
        page.evaluate("() => { document.querySelector('#spoolModal button[title=\"Force/Override Location\"]').click(); }")
        expect(page.locator("#swal-override-loc")).to_have_count(1)
        assert page.locator("#swal-override-loc").get_attribute("value") == "UNKNOWN"
        page.evaluate("() => Swal.close()")
        expect(page.locator("#swal-override-loc")).to_have_count(0)
        page.evaluate("() => { const m = bootstrap.Modal.getInstance(document.getElementById('spoolModal')); if (m) m.hide(); }")
        page.wait_for_function("() => !document.getElementById('spoolModal').classList.contains('show')")
        conftest.wait_modal_settled(page, "spoolModal")

        # The search card, from the real search; each spool in the Unknown list.
        rows = requests.get(f"{api_base_url}/api/search", timeout=30,
                            params={"q": throwaway_filament["name"], "type": "spool"}).json()["results"]
        page.evaluate("(rows) => window.SearchEngine.renderResults(rows)", [r for r in rows if r["id"] == first])
        searched = page.locator(f"#global-search-results [data-spool-id='{first}'] .badge.bg-warning").first
        expect(searched).to_have_text(f"❓ Lost: {where}")
        page.evaluate("() => window.openManage('UNKNOWN')")
        listed = page.locator(f"#manageModal .manage-list-item[data-spool-id='{second}'] .badge.bg-warning").first
        expect(listed).to_contain_text("❓ Lost:", timeout=15_000)
        page.evaluate("() => { window.manageNavStack = []; closeManage(); }")
        page.wait_for_function("() => !document.getElementById('manageModal').classList.contains('show')")
        conftest.wait_modal_settled(page, "manageModal")

        # One Undo puts the batch back, slots and all.
        page.evaluate("() => { window.processScan('CMD:UNDO', 'keyboard'); }")
        expect(page.locator("#confirm-msg")).to_contain_text("Undo")
        page.wait_for_function("() => window.isGatingModalOnScreen && window.isGatingModalOnScreen('confirmModal')")
        with page.expect_response(lambda r: r.url.endswith("/api/undo"), timeout=30_000) as undone:
            page.locator("#confirmModal .btn-success").click()
        assert undone.value.json()["success"] is True, undone.value.json()
        for sid, slot in ((first, slots[0]), (second, slots[1])):
            rec = _extra(spoolman, sid)
            assert rec["location"] == place and rec.get("container_slot", "") == slot, rec
            assert rec.get("fcc_pre_audit_location", "") == "", rec
    finally:
        if requests.get(f"{api_base_url}/api/audit_session", timeout=10).json().get("active"):
            requests.post(f"{api_base_url}/api/identify_scan", json={"text": "CMD:CANCEL"}, timeout=10)
