"""Playwright tests for the buried delete-action UI on the spool and
filament details modals.

These tests cover the UX flow only — open the gear-icon dropdown, render
the inline overlay, walk through the two-step confirmation, exercise
cancel / wrong-input / Escape paths. They do NOT actually trigger the
DELETE endpoint (no destruction of dev data).

The actual server-side delete is covered by `test_delete_helpers.py`
(unit tests with mocked HTTP) and a manual QA pass once the user is
comfortable that the UX is right.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect

import conftest


def _open_first_spool_modal(page: Page, reset_js: str) -> None:
    page.goto("http://localhost:8000")

    # Defensive cross-test pollution teardown — Group 14.1. See
    # conftest.RESET_DOM_STATE_JS for the patterns it handles.
    page.evaluate(reset_js)
    page.wait_for_timeout(200)

    page.locator('nav button:has-text("SEARCH")').click()
    page.wait_for_selector("#offcanvasSearch", timeout=5000)
    page.locator('#global-search-query').fill("a")
    # Scope to inside the offcanvas — see Group 14.3 / 14.6 note in
    # test_ui_details_modal_e2e.py. .fcc-card-action-btn also matches
    # dashboard buffer cards, which sit behind the offcanvas-backdrop.
    page.wait_for_selector("#offcanvasSearch .fcc-card-action-btn[title='View Details']", timeout=10000)
    page.click("#offcanvasSearch .fcc-card-action-btn[title='View Details']")
    expect(page.locator("#spoolModal")).to_be_visible()


def _pick_filament_with_spools(api_base_url: str):
    """Find a filament that has at least one child spool (for cascade prompt
    coverage)."""
    try:
        r = requests.get(f"{api_base_url}/api/filaments", timeout=5)
    except requests.exceptions.RequestException:
        pytest.skip("filaments API unreachable")
    if not r.ok:
        pytest.skip(f"/api/filaments returned {r.status_code}")
    payload = r.json() or {}
    filaments = payload.get("filaments") or payload if isinstance(payload, list) else payload.get("filaments", [])
    if not filaments:
        pytest.skip("no filaments to test against")
    for f in filaments:
        fid = f.get("id")
        if not fid:
            continue
        c = requests.get(f"{api_base_url}/api/spools_by_filament?id={fid}&allow_archived=true", timeout=5)
        if not c.ok:
            continue
        spools = c.json() or []
        if spools:
            return fid, len(spools)
    pytest.skip("no filament with child spools available")


# ---------------------------------------------------------------------------
# Spool delete flow
# ---------------------------------------------------------------------------

def test_spool_gear_dropdown_exposes_delete(page: Page, reset_dom_state_js: str):
    _open_first_spool_modal(page, reset_dom_state_js)
    # Gear button + dropdown item are present and the item is text-danger styled.
    gear = page.locator("#btn-spool-gear")
    expect(gear).to_be_visible()
    gear.click()
    delete_item = page.locator("#btn-spool-delete")
    expect(delete_item).to_be_visible()
    # Confirm it's styled as a destructive action (text-danger class).
    classes = delete_item.get_attribute("class") or ""
    assert "text-danger" in classes, f"Expected text-danger styling, got: {classes}"


def test_spool_delete_step1_renders_warning(page: Page, reset_dom_state_js: str):
    _open_first_spool_modal(page, reset_dom_state_js)
    page.locator("#btn-spool-gear").click()
    page.locator("#btn-spool-delete").click()
    overlay = page.locator("#fcc-spool-delete-overlay")
    expect(overlay).to_be_visible()
    # Step 1 wording.
    expect(overlay).to_contain_text("Delete this spool")
    expect(overlay).to_contain_text("cannot be undone")
    # No type-to-confirm input on Step 1.
    assert overlay.locator("input").count() == 0
    # Cancel returns to the modal cleanly.
    overlay.locator("[data-fcc-delete-cancel]").click()
    expect(overlay).not_to_be_visible()
    expect(page.locator("#spoolModal")).to_be_visible()


def test_spool_delete_step2_requires_id_match(page: Page, reset_dom_state_js: str):
    _open_first_spool_modal(page, reset_dom_state_js)
    sid = (page.locator("#detail-id").inner_text() or "").strip()
    assert sid, "spool details modal didn't render an ID"
    page.locator("#btn-spool-gear").click()
    page.locator("#btn-spool-delete").click()
    # Walk to Step 2.
    page.locator("#fcc-spool-delete-overlay [data-fcc-delete-confirm]").click()
    overlay = page.locator("#fcc-spool-delete-overlay")
    expect(overlay).to_contain_text("Final confirmation")
    expect(overlay).to_contain_text(sid)
    # Type something WRONG and try to confirm — should show inline error.
    inp = overlay.locator("input").first
    inp.fill("not-the-id")
    overlay.locator("[data-fcc-delete-confirm]").click()
    err = overlay.locator(f"#fcc-spool-delete-overlay-err")
    expect(err).to_contain_text("Doesn't match")
    # Cancel out — overlay closes, modal stays.
    overlay.locator("[data-fcc-delete-cancel]").click()
    expect(overlay).not_to_be_visible()
    expect(page.locator("#spoolModal")).to_be_visible()


def test_spool_delete_escape_closes_overlay(page: Page, reset_dom_state_js: str):
    _open_first_spool_modal(page, reset_dom_state_js)
    page.locator("#btn-spool-gear").click()
    page.locator("#btn-spool-delete").click()
    overlay = page.locator("#fcc-spool-delete-overlay")
    expect(overlay).to_be_visible()
    # NB: page.keyboard.press("Escape") AND locator.press("Escape") both
    # silently fail to reach DOM keydown handlers in this Bootstrap-modal +
    # Playwright + Chromium combo (verified via capture-phase probe — count
    # stays at 0). Synthetic dispatchEvent works correctly and exercises
    # the same code path the real Escape would hit.
    page.locator("#fcc-spool-delete-overlay [data-fcc-delete-cancel]").focus()
    page.evaluate("""
        document.activeElement.dispatchEvent(
            new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true})
        );
    """)
    expect(overlay).not_to_be_visible()
    # Modal must still be open — Escape on the delete overlay only dismisses
    # the overlay, not the underlying modal.
    expect(page.locator("#spoolModal")).to_be_visible()


def test_spool_delete_overlay_clears_when_modal_closes(page: Page, reset_dom_state_js: str):
    _open_first_spool_modal(page, reset_dom_state_js)
    page.locator("#btn-spool-gear").click()
    page.locator("#btn-spool-delete").click()
    overlay = page.locator("#fcc-spool-delete-overlay")
    expect(overlay).to_be_visible()
    # Close the modal mid-flow.
    page.evaluate("modals.spoolModal && modals.spoolModal.hide()")
    expect(page.locator("#spoolModal")).to_be_hidden()
    # Re-open — overlay should NOT be re-rendered with stale state.
    _open_first_spool_modal(page, reset_dom_state_js)
    expect(page.locator("#fcc-spool-delete-overlay")).not_to_be_visible()


# ---------------------------------------------------------------------------
# Filament delete flow (cascade messaging)
# ---------------------------------------------------------------------------

def test_filament_delete_shows_cascade_count(page: Page, api_base_url: str):
    fid, child_count = _pick_filament_with_spools(api_base_url)
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone", timeout=10000)
    # `openFilamentDetails` is a top-level const in inv_details.js (not on
    # window), so call it directly via a lexical reference.
    page.evaluate(f"openFilamentDetails({fid})")
    expect(page.locator("#filamentModal")).to_be_visible(timeout=10000)
    # Wait for the spool count to populate from /api/spools_by_filament.
    page.wait_for_function(
        "() => { const el = document.getElementById('fil-spool-count');"
        " return el && /\\d+/.test(el.innerText); }",
        timeout=10000,
    )
    # Wait for the spool count fetch to populate. The handler does its own
    # /api/spools_by_filament call, but that's after the click — we just
    # need the gear button mounted.
    page.locator("#btn-fil-gear").click()
    page.locator("#btn-fil-delete").click()
    overlay = page.locator("#fcc-filament-delete-overlay")
    expect(overlay).to_be_visible()
    # Step 1 should mention the cascade count and the filament ID.
    expect(overlay).to_contain_text(f"#{fid}")
    expect(overlay).to_contain_text(str(child_count))
    expect(overlay).to_contain_text("spool")  # singular or plural
    # Continue to Step 2 — should require typing CONFIRM (cascade case).
    overlay.locator("[data-fcc-delete-confirm]").click()
    expect(overlay).to_contain_text("Final confirmation")
    expect(overlay).to_contain_text("CONFIRM")
    inp = overlay.locator("input").first
    expect(inp).to_be_visible()
    # Cancel — no destruction.
    overlay.locator("[data-fcc-delete-cancel]").click()
    expect(overlay).not_to_be_visible()
    expect(page.locator("#filamentModal")).to_be_visible()


# ---------------------------------------------------------------------------
# Group 62.8: the delete question is a mountOverlay
# ---------------------------------------------------------------------------

def test_spool_delete_question_is_on_top_keeps_tab_and_escape_closes_only_it(page: Page, reset_dom_state_js: str):
    """It was a div inside the spool window; it is a mountOverlay now. Tab stays inside
    it, a real Escape closes only it (the window stays), and the window's own buttons
    can't be pressed under it."""
    _open_first_spool_modal(page, reset_dom_state_js)
    page.locator("#btn-spool-gear").click()
    page.locator("#btn-spool-delete").click()
    overlay = page.locator("#fcc-spool-delete-overlay")
    expect(overlay).to_be_visible()
    assert overlay.get_attribute("data-overlay-mount") == "1"
    page.wait_for_function("() => document.activeElement && document.activeElement.matches('[data-fcc-delete-cancel]')")
    for _ in range(4):
        page.keyboard.press("Tab")
        assert page.evaluate("() => !!document.activeElement.closest('#fcc-spool-delete-overlay')")
    page.keyboard.press("Escape")
    expect(overlay).to_have_count(0)
    expect(page.locator("#spoolModal")).to_be_visible()


def _route_writes(page: Page, deletes: list):
    """The DELETE answered in the browser (refused, so the flow keeps its question up),
    and any scan answered empty: nothing reaches dev."""
    def handle(route, request):
        if request.method == "DELETE":
            deletes.append(request.url)
            route.fulfill(status=200, content_type="application/json",
                          body='{"success": false, "error": "test: not deleted"}')
        elif request.method == "POST" and "/api/identify_scan" in request.url:
            route.fulfill(status=200, content_type="application/json", body="{}")
        else:
            route.continue_()
    page.route("**/api/**", handle)


def test_enter_in_the_typed_box_never_deletes_and_a_refusal_is_said_on_the_question(page: Page, reset_dom_state_js: str):
    """A scanner's digits-only label for the spool, read into the typed box at scanner
    speed, goes to the scan path (the box keeps what it held). Enter in the box never
    presses Delete forever (the review of Group 62): a scanner slower than the box's digit
    rule (a key every 40 ms), or a two-digit id, left the label's digits in the box, which
    can't tell their Enter from a person's, and the id matched. The id typed at a person's
    pace (as a slower scanner sends it) and Enter say to press Delete forever; its click
    sends one DELETE, answered here as refused: the question says why on itself (its toast
    is drawn under it), its buttons answer again, and the keyboard is on Cancel. RED before
    the review's fix: that Enter deleted, and a refusal left both buttons dead."""
    deletes: list = []
    _route_writes(page, deletes)
    _open_first_spool_modal(page, reset_dom_state_js)
    sid = (page.locator("#detail-id").inner_text() or "").strip()
    assert sid.isdigit(), sid
    page.locator("#btn-spool-gear").click()
    page.locator("#btn-spool-delete").click()
    question = page.locator("#fcc-spool-delete-overlay")
    question.locator("[data-fcc-delete-confirm]").click()
    box = page.locator("#fcc-spool-delete-overlay-input")
    expect(box).to_be_focused()
    page.keyboard.type(sid, delay=5)                    # a scanner's pace
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    assert deletes == [], "a scanned label pressed Delete forever"
    assert box.input_value() == ""
    page.wait_for_timeout(2100)                          # past the accumulator's reset
    box.focus()
    page.keyboard.type(sid, delay=120)                   # a person, or a slower scanner
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    assert deletes == [], "Enter in the typed box pressed Delete forever"
    err = page.locator("#fcc-spool-delete-overlay-err")
    expect(err).to_contain_text("Delete forever")
    confirm = question.locator("[data-fcc-delete-confirm]")
    cancel = question.locator("[data-fcc-delete-cancel]")
    confirm.click()
    page.wait_for_timeout(500)
    assert len(deletes) == 1 and deletes[0].rstrip("/").endswith(f"/api/spool/{sid}"), deletes
    expect(err).to_contain_text("test: not deleted")
    expect(confirm).to_be_enabled()
    expect(cancel).to_be_enabled()
    expect(cancel).to_be_focused()


# ---------------------------------------------------------------------------
# The second review of Group 62 (2026-11-17): after a refusal Delete forever takes no
# pointer press for 700 ms, a retry clears the last refusal's words, and the keyboard
# goes to Cancel only while the question is on top. The Merge question, the same file's
# other permanent question, says why on itself too.
# ---------------------------------------------------------------------------

# The DELETE answered in the page itself, refused, or held until window.__release():
# nothing reaches dev. A plain object, not a Response, so the refusal is read in the
# press's own task and a double click's second press comes after it.
REFUSE_DELETES = r"""() => {
    window.__deletes = 0; window.__release = null; window.__holdDeletes = false;
    const real = window.fetch;
    window.fetch = (u, o) => {
        if (!(o && String(o.method || '').toUpperCase() === 'DELETE')) return real(u, o);
        window.__deletes += 1;
        const n = window.__deletes;
        const answer = { ok: true, status: 200, json: () => Promise.resolve({ success: false, error: 'test: refused ' + n }) };
        if (!window.__holdDeletes) return Promise.resolve(answer);
        return new Promise((r) => { window.__release = () => r(answer); });
    };
    delete window.fccQuestionArmMs;          // these tests are about the 700 ms
}"""


def _typed_step(page: Page, reset_js: str):
    _open_first_spool_modal(page, reset_js)
    page.evaluate(REFUSE_DELETES)
    sid = (page.locator("#detail-id").inner_text() or "").strip()
    assert sid.isdigit(), sid
    page.locator("#btn-spool-gear").click()
    page.locator("#btn-spool-delete").click()
    question = page.locator("#fcc-spool-delete-overlay")
    question.locator("[data-fcc-delete-confirm]").click()
    box = page.locator("#fcc-spool-delete-overlay-input")
    expect(box).to_be_focused()
    box.fill(sid)                                        # no keys: nothing reads as a scan
    return question


def test_a_double_click_across_a_fast_refusal_sends_one_delete(page: Page, reset_dom_state_js: str):
    """A refusal re-enabled Delete forever at once, so the second press of a double click,
    landing after a fast refusal, sent a second DELETE nobody asked for, its reason
    unread. A later click still tries again. RED before the fix: two DELETEs."""
    question = _typed_step(page, reset_dom_state_js)
    confirm = question.locator("[data-fcc-delete-confirm]")
    confirm.dblclick()
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__deletes") == 1
    expect(page.locator("#fcc-spool-delete-overlay-err")).to_have_text("Delete failed: test: refused 1")
    page.wait_for_timeout(700)
    confirm.click()
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__deletes") == 2


def test_a_retry_clears_the_last_refusal_and_cancel_takes_the_keyboard_only_on_top(page: Page, reset_dom_state_js: str):
    """While Delete forever tried again, the last refusal's words stayed up; and a refusal
    moved the keyboard to Cancel even with another window over the question (a scan can
    open one there), where its keys reached nothing on screen. RED before the fix."""
    question = _typed_step(page, reset_dom_state_js)
    confirm = question.locator("[data-fcc-delete-confirm]")
    err = page.locator("#fcc-spool-delete-overlay-err")
    confirm.click()
    expect(err).to_have_text("Delete failed: test: refused 1")
    page.wait_for_timeout(800)
    page.evaluate("() => { window.__holdDeletes = true; }")
    confirm.click()
    page.wait_for_function("() => typeof window.__release === 'function'")
    expect(err).to_have_text("")
    page.evaluate("""() => { window.__top = window.mountOverlay({ id: 'fcc-test-top', tier: 'confirm',
        content: '<div><button id="t-top">top</button></div>', initialFocus: '#t-top' }); }""")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 't-top'")
    page.evaluate("() => window.__release()")
    expect(err).to_have_text("Delete failed: test: refused 2")
    page.wait_for_timeout(200)
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "t-top"
    page.evaluate("() => window.__top.cleanup()")


# The merge's POST answered in the page itself, refused: nothing reaches dev.
REFUSE_MERGES = r"""() => {
    window.__merges = 0;
    const real = window.fetch;
    window.fetch = (u, o) => {
        if (!(String(u).includes('/merge_into/') && o && String(o.method || '').toUpperCase() === 'POST')) return real(u, o);
        window.__merges += 1;
        const n = window.__merges;
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: false, error: 'test: not merged ' + n }) });
    };
    delete window.fccQuestionArmMs;
}"""


def test_a_refused_merge_says_why_on_its_question_and_a_double_click_sends_one(page: Page):
    """Older than Group 62: the Merge question's refusal was only a toast, drawn under the
    question (a confirm-tier overlay), and Merge forever answered again at once, so a
    double click across a fast refusal sent a second merge. It says why on itself now, as
    the delete question does, the keyboard on Cancel, and takes no pointer press for
    700 ms after a refusal. RED before the fix."""
    page.goto("http://localhost:8000")
    page.wait_for_function("() => typeof openFilamentDetails === 'function' && typeof state !== 'undefined'",
                           timeout=45_000)
    ids = page.evaluate("""async () => { const j = await fetch('/api/filaments').then((r) => r.json());
        return ((j && j.filaments) || []).slice(0, 2).map((f) => f.id); }""")
    if len(ids) < 2:
        pytest.skip("dev holds fewer than two filaments")
    src, dst = ids
    page.evaluate("(id) => openFilamentDetails(id)", src)
    page.wait_for_function("""(id) => document.getElementById('filamentModal').classList.contains('show')
        && (document.getElementById('fil-detail-id').innerText || '').trim() === String(id)""", arg=src, timeout=15_000)
    # The window has its show class some 330 ms before Bootstrap ends its show, and the end
    # focuses the window itself (its focus trap's autofocus). This flow reaches the refusal
    # well inside that, so the window took the keyboard back from Cancel whenever the two
    # landed in the wrong order (the full sweep of 2026-11-23: red on every run, the click
    # within 30 ms of the show's end). No person gets this far in 330 ms.
    conftest.wait_modal_settled(page, "filamentModal")
    page.evaluate(REFUSE_MERGES)
    page.evaluate("() => document.getElementById('btn-fil-merge').click()")
    page.wait_for_selector("#fcc-merge-target-input")
    page.locator("#fcc-merge-target-input").fill(f"#{dst}")
    page.locator("#fcc-merge-continue").click()
    page.wait_for_selector("#fcc-merge-confirm-input")
    page.locator("#fcc-merge-confirm-input").fill("MERGE")
    go = page.locator("#fcc-merge-confirm-go")
    go.click()
    err = page.locator("#fcc-merge-confirm-err")
    expect(err).to_have_text("Merge failed: test: not merged 1")
    assert err.get_attribute("role") == "alert"
    expect(page.locator("#fcc-merge-confirm-cancel")).to_be_focused()
    page.wait_for_timeout(800)
    go.dblclick()
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__merges") == 2
