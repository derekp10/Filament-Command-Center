"""Group 43.3: the review card's spool picker, in the browser.

Derek's case (job 1104's file, the 1105/1106 `no_spool` reviews): the gcode was
sliced for T0, but he started it on the printer from another head, so FCC found
no spool on T0 and the review could only "re-check" T0. Now each line picks the
spool it charges: one that was on a head when the print ended, one on a head
now, or any spool by #id. A cancel review's row can be redirected the same way.

HERMETIC AGAINST DEV DATA: one context route answers /api/cancel_deduct/pending,
/candidates, /confirm and /api/spools/<id> from fixtures and records the POSTs;
every other non-GET is answered synthetically; the remaining GETs pass through
read-only. Nothing is charged, and no review is created or cleared on dev.
"""
from __future__ import annotations

import copy
import json
import re
import time
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

pytestmark = pytest.mark.usefixtures("require_server")

INDX = "🦝 Core One INDX"
NO_SPOOL = {
    "printer_name": INDX, "job_id": "J-1105", "filename": "/usb/MAIN-B~1.BGC", "progress": 1.0,
    "total_grams": 61.32, "spools": [], "ambiguous": False, "kind": "no_spool",
    "usage_map": {"0": 61.32},
    "heads_at_end": [{"toolhead": "RCOI-1", "position": 0, "sid": None},
                     {"toolhead": "RCOI-2", "position": 1, "sid": 96}],
    "created": "2026-10-13 00:00:00",
}
ROW = {"sid": 97, "toolhead": "RCOI-3", "position": 2, "grams": 2.5, "current_used": 100.0,
       "initial_weight": 1000.0, "remaining_before": 900.0, "remaining_after": 897.5,
       "display": "#97 PLA Red", "color": "ff0000"}
PARTIAL = {"printer_name": INDX, "job_id": "J-1200", "filename": "f.bgcode", "progress": 0.5,
           "total_grams": 2.5, "ambiguous": False, "spools": [ROW], "created": "2026-10-13 00:00:00"}
HEADS = {"heads": [
    {"toolhead": "RCOI-1", "position": 0, "sid": None},
    {"toolhead": "RCOI-2", "position": 1, "sid": 96, "display": "#96 Galaxy Black", "color": "000000",
     "remaining": 100.0, "archived": False},
    {"toolhead": "RCOI-3", "position": 2, "sid": 97, "display": "#97 PLA Red", "color": "ff0000",
     "remaining": 900.0, "archived": False},
]}
OTHER_SPOOL = {"id": 98, "filament": {"name": "PLA Blue"}, "location": "SHELF-A", "archived": False,
               "remaining_weight": 40.0}
# Group 43.2: job 1104's run-out spool, auto-archived at 0 g.
ARCHIVED_SPOOL = {"id": 99, "filament": {"name": "PETG Clear"}, "location": "", "archived": True,
                  "remaining_weight": 0.0}
SPOOLS = {OTHER_SPOOL["id"]: OTHER_SPOOL, ARCHIVED_SPOOL["id"]: ARCHIVED_SPOOL}


class FakeBackend:
    """`confirm_answer` is what /confirm answers; `pending_after_confirm`, when
    set, is what /pending lists once a confirm has posted (the server's
    reshaped review)."""

    def __init__(self, page: Page, pending, confirm_answer=None, pending_after_confirm=None):
        self.pending = copy.deepcopy(pending)
        self.confirms: list[dict] = []
        self.confirm_answer = confirm_answer or {"status": "confirmed", "applied": [], "errors": []}
        self.pending_after_confirm = pending_after_confirm
        page.context.route("**/*", self._handle)

    @staticmethod
    def _json(route, payload, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    def _handle(self, route):
        try:
            self._route(route)
        except PlaywrightError as e:
            if "closed" not in str(e).lower():
                raise

    def _route(self, route):
        req = route.request
        path = urlsplit(req.url).path
        if req.method in ("GET", "HEAD", "OPTIONS"):
            if path == "/api/cancel_deduct/pending":
                self._json(route, {"pending": self.pending})
            elif path == "/api/cancel_deduct/candidates":
                self._json(route, HEADS)
            elif path == "/api/state/buffer":
                self._json(route, [])
            elif re.fullmatch(r"/api/spools/\d+", path):
                # routes_inventory.api_get_spool's real envelope.
                sid = int(path.rsplit("/", 1)[-1])
                if sid in SPOOLS:
                    self._json(route, {"success": True, "data": SPOOLS[sid]})
                else:
                    self._json(route, {"success": False, "msg": "Spool not found"}, status=404)
            else:
                route.continue_()
            return
        try:
            body = json.loads(req.post_data or "{}")
        except (TypeError, ValueError):
            body = {}
        if path == "/api/cancel_deduct/confirm":
            self.confirms.append(body)
            if self.pending_after_confirm is not None:
                self.pending = copy.deepcopy(self.pending_after_confirm)
            self._json(route, self.confirm_answer)
            return
        self._json(route, {"success": True})


@pytest.fixture(autouse=True)
def _drop_routes_in_flight(page: Page):
    """Close the page BEFORE un-routing, so its polls can't reach the dev server."""
    yield
    try:
        page.close()
    except PlaywrightError:
        pass
    try:
        page.context.unroute_all(behavior="ignoreErrors")
    except PlaywrightError:
        pass


def _until(page: Page, predicate, timeout_ms: int, what: str) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if predicate():
            return
        page.wait_for_timeout(50)
    assert predicate(), what


def _open(page: Page, base_url: str, reset_dom_state_js: str, pending, **backend) -> FakeBackend:
    be = FakeBackend(page, pending, **backend)
    page.goto(base_url.rstrip("/") + "/", wait_until="domcontentloaded")
    page.wait_for_function("typeof window.openCancelReview === 'function' && typeof window.mountOverlay === 'function'",
                           timeout=20_000)
    page.evaluate(reset_dom_state_js)
    page.evaluate("() => window.openCancelReview()")
    page.wait_for_selector("#fcc-cancel-review-overlay .fcc-cr-card", state="attached", timeout=10_000)
    return be


def _wait_heads(page: Page, line: str) -> None:
    page.wait_for_function(
        f"!!document.querySelector('.fcc-cr-pick[data-line=\"{line}\"] .fcc-cr-now option[value=\"96\"]')",
        timeout=8_000)


def test_a_no_spool_review_charges_the_head_the_print_really_ran_on(page: Page, base_url, reset_dom_state_js):
    be = _open(page, base_url, reset_dom_state_js, [NO_SPOOL])
    _wait_heads(page, "0")
    ended = page.evaluate(
        "() => Array.from(document.querySelectorAll('.fcc-cr-pick[data-line=\"0\"] .fcc-cr-ended option'))"
        ".map(o => o.value)")
    assert ended == ["96"], f"RCOI-2's spool at print end should be offered: {ended}"
    page.select_option('.fcc-cr-pick[data-line="0"]', "96")
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    _until(page, lambda: be.confirms, 5_000, "Apply never posted")
    assert be.confirms[0].get("charges") == [{"position": 0, "sid": 96, "grams": 61.32}], be.confirms[0]
    assert "updates" not in be.confirms[0]


def test_apply_without_a_pick_says_so_and_posts_nothing(page: Page, base_url, reset_dom_state_js):
    be = _open(page, base_url, reset_dom_state_js, [NO_SPOOL])
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    page.wait_for_timeout(400)
    assert not be.confirms
    toast = page.evaluate("() => Array.from(document.querySelectorAll('.toast-msg')).map(t => t.textContent).join(' | ')")
    assert "Pick the spool" in toast, toast


def test_any_spool_can_be_charged_by_id(page: Page, base_url, reset_dom_state_js):
    be = _open(page, base_url, reset_dom_state_js, [NO_SPOOL])
    page.select_option('.fcc-cr-pick[data-line="0"]', "other")
    page.fill('.fcc-cr-other[data-line="0"]', "98")
    page.dispatch_event('.fcc-cr-other[data-line="0"]', "change")
    page.wait_for_function(
        "(document.querySelector('.fcc-cr-other-info[data-line=\"0\"]') || {}).textContent.includes('PLA Blue')",
        timeout=5_000)
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    _until(page, lambda: be.confirms, 5_000, "Apply never posted")
    assert be.confirms[0]["charges"] == [{"position": 0, "sid": 98, "grams": 61.32}]


def test_a_cancel_review_row_can_be_redirected(page: Page, base_url, reset_dom_state_js):
    be = _open(page, base_url, reset_dom_state_js, [PARTIAL])
    _wait_heads(page, "97")
    page.select_option('.fcc-cr-pick[data-line="97"]', "96")
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    _until(page, lambda: be.confirms, 5_000, "Confirm never posted")
    assert be.confirms[0].get("charges") == [{"row": 97, "sid": 96, "grams": 2.5}], be.confirms[0]


def test_an_unchanged_row_still_sends_updates(page: Page, base_url, reset_dom_state_js):
    """Back-compat: a card whose rows keep their own spool posts the old shape."""
    be = _open(page, base_url, reset_dom_state_js, [PARTIAL])
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    _until(page, lambda: be.confirms, 5_000, "Confirm never posted")
    assert be.confirms[0].get("updates") == {"97": 2.5}, be.confirms[0]
    assert "charges" not in be.confirms[0]


def test_an_empty_id_pick_blocks_the_apply(page: Page, base_url, reset_dom_state_js):
    """Review finding picker-frontend-20: "Another spool by #ID…" with no #id was
    skipped, and the Apply used up the whole review without that tool."""
    usage = {"0": 61.32, "1": 5.0}
    be = _open(page, base_url, reset_dom_state_js, [dict(NO_SPOOL, usage_map=usage, total_grams=66.32)])
    page.select_option('.fcc-cr-pick[data-line="0"]', "96")
    page.select_option('.fcc-cr-pick[data-line="1"]', "other")
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    page.wait_for_timeout(400)
    assert not be.confirms, be.confirms
    toast = page.evaluate("() => Array.from(document.querySelectorAll('.toast-msg')).map(t => t.textContent).join(' | ')")
    assert "#id" in toast and "T1" in toast, toast


def test_a_redirect_previews_the_picked_spools_remaining(page: Page, base_url, reset_dom_state_js):
    """Review finding picker-backend-7: the row kept its own spool's 900 g left,
    so a redirect onto a near-empty spool previewed green and then clamped."""
    _open(page, base_url, reset_dom_state_js, [PARTIAL])
    _wait_heads(page, "97")
    page.select_option('.fcc-cr-pick[data-line="97"]', "96")        # 100 g left
    assert page.evaluate("() => document.querySelector('.fcc-cr-grams').dataset.remaining") == "100"
    page.fill(".fcc-cr-grams", "150")
    page.wait_for_function("document.querySelector('.fcc-cr-preview').textContent.includes('⚠️')", timeout=3_000)
    page.select_option('.fcc-cr-pick[data-line="97"]', "97")        # back to its own spool
    assert page.evaluate("() => document.querySelector('.fcc-cr-grams').dataset.remaining") == "900"


def test_a_failed_apply_shows_the_review_as_the_server_kept_it(page: Page, base_url, reset_dom_state_js):
    """Review finding picker-frontend-18: the redirect's write failed, so the
    server kept a review whose row is the PICKED spool. The stale card still
    showed #97, and flipping it back posted a row the review no longer has."""
    kept = dict(PARTIAL, spools=[dict(ROW, sid=96, display="#96 Galaxy Black",
                                      attempt_used_before=900.0, attempt_used_after=902.5)])
    be = _open(page, base_url, reset_dom_state_js, [PARTIAL],
               confirm_answer={"status": "error", "applied": [],
                               "errors": [{"sid": 96, "error": "read timed out"}]},
               pending_after_confirm=[kept])
    _wait_heads(page, "97")
    page.select_option('.fcc-cr-pick[data-line="97"]', "96")
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    _until(page, lambda: be.confirms, 5_000, "Confirm never posted")
    page.wait_for_selector('.fcc-cr-row[data-sid="96"]', state="attached", timeout=5_000)
    assert page.evaluate("() => !document.querySelector('.fcc-cr-row[data-sid=\"97\"]')"), "the stale #97 row is still shown"


def test_a_row_with_no_known_capacity_says_so(page: Page, base_url, reset_dom_state_js):
    """43.1: neither the spool nor its filament has a weight, so there is no
    remaining to show (it used to read "0g left" with max=0)."""
    row = dict(ROW, remaining_before=None, remaining_after=None, initial_weight=None)
    _open(page, base_url, reset_dom_state_js, [dict(PARTIAL, spools=[row])])
    text = page.evaluate("() => document.querySelector('.fcc-cr-row').textContent")
    assert "capacity unknown" in text, text
    assert page.evaluate("() => document.querySelector('.fcc-cr-grams').hasAttribute('max')") is False
    page.fill(".fcc-cr-grams", "3")
    page.wait_for_function("document.querySelector('.fcc-cr-preview').textContent.includes('?')", timeout=3_000)


# Group 43.4: a partial review keeps the heads that had no spool when it ended.
PARTIAL_WITH_EMPTY_HEAD = dict(
    PARTIAL, total_grams=7.5, unresolved_usage={"1": 5.0},
    heads_at_end=[{"toolhead": "RCOI-1", "position": 0, "sid": None},
                  {"toolhead": "RCOI-2", "position": 1, "sid": None},
                  {"toolhead": "RCOI-3", "position": 2, "sid": 97}])


def test_an_emptied_head_is_offered_and_its_pick_is_sent_by_position(page: Page, base_url, reset_dom_state_js):
    """HEAD proof: the card had no line for the emptied head at all."""
    be = _open(page, base_url, reset_dom_state_js, [PARTIAL_WITH_EMPTY_HEAD])
    _wait_heads(page, "pos:1")
    text = page.evaluate("() => document.querySelector('.fcc-cr-card').textContent")
    assert "T1 · RCOI-2" in text and "No spool was loaded" in text, text
    page.select_option('.fcc-cr-pick[data-line="pos:1"]', "96")
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    _until(page, lambda: be.confirms, 5_000, "Confirm never posted")
    assert be.confirms[0].get("charges") == [
        {"row": 97, "sid": 97, "grams": 2.5}, {"position": 1, "sid": 96, "grams": 5.0}], be.confirms[0]


def test_an_emptied_head_left_unpicked_keeps_the_updates_shape(page: Page, base_url, reset_dom_state_js):
    """Unpicked, its grams stay on the server's record, which reports them as
    uncharged at Apply; the card sends the old shape for the kept row."""
    be = _open(page, base_url, reset_dom_state_js, [PARTIAL_WITH_EMPTY_HEAD])
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    _until(page, lambda: be.confirms, 5_000, "Confirm never posted")
    assert be.confirms[0].get("updates") == {"97": 2.5} and "charges" not in be.confirms[0], be.confirms[0]


# Group 43.2: grams an automatic deduct couldn't charge become a card. Job 1104:
# #99 on RCOI-1 ran out after 34.2 g of 61.32 g, and the printer carried on from
# the spool joined to it on RCOI-2.
SHORTFALL = {
    "printer_name": INDX, "job_id": "1104#shortfall", "shortfall_of": "1104", "filename": "/usb/MAIN-B~1.BGC",
    "progress": 1.0, "total_grams": 27.12, "spools": [], "ambiguous": False, "kind": "shortfall",
    "unresolved_usage": {"0": 27.12},
    "heads_at_end": [{"toolhead": "RCOI-1", "position": 0, "sid": 99, "archived": True},
                     {"toolhead": "RCOI-2", "position": 1, "sid": 96}],
    "shortfall_causes": {"0": {"why": "ran_out", "sid": 99, "toolhead": "RCOI-1", "archived": True}},
    "created": "2026-10-13 00:00:00",
}


def _toasts(page: Page) -> str:
    return page.evaluate("() => Array.from(document.querySelectorAll('.toast-msg')).map(t => t.textContent).join(' | ')")


def test_a_shortfall_card_says_why_and_charges_the_picked_spool(page: Page, base_url, reset_dom_state_js):
    """HEAD proof: the card rendered as "cancelled at ~100%" with a "no spool was
    loaded" line, and never said which spool ran out."""
    be = _open(page, base_url, reset_dom_state_js, [SHORTFALL])
    _wait_heads(page, "pos:0")
    text = page.evaluate("() => document.querySelector('.fcc-cr-card').textContent")
    assert "27.12g went to no spool" in text and "#99's record hit 0 g on RCOI-1 (archived)" in text, text
    # The archived run-out spool is offered, and says so, but isn't pre-picked.
    assert page.evaluate("() => document.querySelector('.fcc-cr-pick[data-line=\"pos:0\"]').value") == ""
    ended = page.evaluate(
        "() => Array.from(document.querySelectorAll('.fcc-cr-pick[data-line=\"pos:0\"] .fcc-cr-ended option'))"
        ".map(o => o.textContent)")
    assert any("#99" in t and "ran out, archived" in t for t in ended), ended
    page.select_option('.fcc-cr-pick[data-line="pos:0"]', "96")
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    _until(page, lambda: be.confirms, 5_000, "Apply never posted")
    assert be.confirms[0] == {"printer_name": INDX, "job_id": "1104#shortfall", "rev": 0,
                              "charges": [{"position": 0, "sid": 96, "grams": 27.12}]}, be.confirms[0]


def test_a_shortfall_card_without_a_pick_says_so_and_posts_nothing(page: Page, base_url, reset_dom_state_js):
    be = _open(page, base_url, reset_dom_state_js, [SHORTFALL])
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    page.wait_for_timeout(400)
    assert not be.confirms, be.confirms
    assert "Pick the spool that took these grams" in _toasts(page)


def test_what_a_pick_cannot_take_stays_on_the_card(page: Page, base_url, reset_dom_state_js):
    """#96 had only 10 g: the server charges what fits and keeps the card with the rest."""
    kept = dict(SHORTFALL, total_grams=17.12, unresolved_usage={"0": 17.12})
    be = _open(page, base_url, reset_dom_state_js, [SHORTFALL],
               confirm_answer={"status": "confirmed", "applied": [{"sid": 96, "grams": 10.0, "remaining": 0.0}],
                               "errors": [], "shortfall_g": 17.12, "kept": True},
               pending_after_confirm=[kept])
    _wait_heads(page, "pos:0")
    page.select_option('.fcc-cr-pick[data-line="pos:0"]', "96")
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    _until(page, lambda: be.confirms, 5_000, "Apply never posted")
    page.wait_for_function(
        "(() => { const c = document.querySelector('.fcc-cr-card'); return !!c && c.textContent.includes('17.12g went to no spool'); })()",
        timeout=5_000)
    assert "17.12g still have no spool" in _toasts(page)


def test_a_spool_that_was_not_charged_is_pre_picked(page: Page, base_url, reset_dom_state_js):
    """A head whose spool wasn't charged (a failed write) keeps that spool as the
    default: it's still loaded and not archived, so one tap applies it."""
    rec = dict(SHORTFALL,
               shortfall_causes={"0": {"why": "not_charged", "sid": 97, "toolhead": "RCOI-1", "archived": False}},
               heads_at_end=[{"toolhead": "RCOI-1", "position": 0, "sid": 97}])
    be = _open(page, base_url, reset_dom_state_js, [rec])
    assert page.evaluate("() => document.querySelector('.fcc-cr-pick[data-line=\"pos:0\"]').value") == "97"
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    _until(page, lambda: be.confirms, 5_000, "Apply never posted")
    assert be.confirms[0]["charges"] == [{"position": 0, "sid": 97, "grams": 27.12}], be.confirms[0]


def test_typing_an_archived_spool_says_it_is_charged_and_stays_archived(page: Page, base_url, reset_dom_state_js):
    """HEAD said "is archived — pick another spool" (Derek answered 2026-10-13:
    charge it, leave it archived). It also says how much it has left (0 g), so an
    empty pick isn't a surprise."""
    _open(page, base_url, reset_dom_state_js, [NO_SPOOL])
    page.select_option('.fcc-cr-pick[data-line="0"]', "other")
    page.fill('.fcc-cr-other[data-line="0"]', "99")
    page.dispatch_event('.fcc-cr-other[data-line="0"]', "change")
    page.wait_for_function(
        "(document.querySelector('.fcc-cr-other-info[data-line=\"0\"]') || {}).textContent.includes('stays archived')",
        timeout=5_000)
    info = page.evaluate("() => document.querySelector('.fcc-cr-other-info[data-line=\"0\"]').textContent")
    assert "0g left" in info, info


def test_a_stale_card_is_redrawn_instead_of_charged(page: Page, base_url, reset_dom_state_js):
    """43.2 review fix (deduct-3): another tab's Apply moved the card to rev 1 and
    17.12 g; this view's Apply is refused as stale, and the card redraws."""
    newer = dict(SHORTFALL, rev=1, total_grams=17.12, unresolved_usage={"0": 17.12})
    be = _open(page, base_url, reset_dom_state_js, [SHORTFALL],
               confirm_answer={"status": "error", "stale": True,
                               "msg": "This card changed since you opened it — reopen the review."},
               pending_after_confirm=[newer])
    _wait_heads(page, "pos:0")
    page.select_option('.fcc-cr-pick[data-line="pos:0"]', "96")
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    _until(page, lambda: be.confirms, 5_000, "Apply never posted")
    page.wait_for_function(
        "(() => { const c = document.querySelector('.fcc-cr-card'); return !!c && c.dataset.rev === '1'"
        " && c.textContent.includes('17.12g went to no spool'); })()", timeout=5_000)
    assert "This card changed" in _toasts(page)


def test_grams_a_pick_could_not_take_show_up_as_a_new_card(page: Page, base_url, reset_dom_state_js):
    """43.2 review fix (deduct-2): an empty pick on a no_spool review closes it,
    and its grams arrive as an uncharged-grams card in the same overlay."""
    card = dict(SHORTFALL, job_id="J-1105#shortfall", shortfall_of="J-1105")
    be = _open(page, base_url, reset_dom_state_js, [NO_SPOOL],
               confirm_answer={"status": "confirmed", "applied": [{"sid": 99, "grams": 0.0, "remaining": 0.0}],
                               "errors": [], "shortfall_g": 61.32, "shortfall_card": "J-1105#shortfall"},
               pending_after_confirm=[card])
    page.select_option('.fcc-cr-pick[data-line="0"]', "other")
    page.fill('.fcc-cr-other[data-line="0"]', "99")
    page.dispatch_event('.fcc-cr-other[data-line="0"]', "change")
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    _until(page, lambda: be.confirms, 5_000, "Apply never posted")
    page.wait_for_selector('.fcc-cr-card[data-job="J-1105#shortfall"]', state="attached", timeout=5_000)
    assert page.evaluate("() => !document.querySelector('.fcc-cr-card[data-job=\"J-1105\"]')"), "the review closed"
    toasts = _toasts(page)
    assert "Nothing was charged" in toasts and "on a new card" in toasts, toasts
    assert "Deducted from" not in toasts, toasts


def test_an_unconfirmed_write_row_says_so(page: Page, base_url, reset_dom_state_js):
    """43.2 review fix (deduct-1): a write Spoolman reported as failed rides on the
    card as a row whose Apply checks first; the row says it's unconfirmed."""
    row = dict(ROW, sid=97, grams=5.0, position=1, toolhead="RCOI-2", unconfirmed_write=True,
               attempt_used_before=100.0, attempt_used_after=105.0)
    rec = dict(SHORTFALL, total_grams=5.0, spools=[row], unresolved_usage={}, shortfall_causes={})
    be = _open(page, base_url, reset_dom_state_js, [rec])
    text = page.evaluate("() => document.querySelector('.fcc-cr-card').textContent")
    assert "unconfirmed write" in text, text
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")
    _until(page, lambda: be.confirms, 5_000, "Apply never posted")
    assert be.confirms[0].get("updates") == {"97": 5.0} and be.confirms[0].get("rev") == 0, be.confirms[0]


def test_a_two_spool_head_names_both(page: Page, base_url, reset_dom_state_js):
    """43.2 review fix (spec-5): the card names both spools on a head that held two."""
    rec = dict(SHORTFALL, unresolved_usage={"1": 5.0}, total_grams=5.0,
               heads_at_end=[{"toolhead": "RCOI-2", "position": 1, "sid": 96},
                             {"toolhead": "RCOI-2", "position": 1, "sid": 97}],
               shortfall_causes={"1": {"why": "two_spools", "sid": None, "sids": [96, 97],
                                       "toolhead": "RCOI-2", "archived": False}})
    _open(page, base_url, reset_dom_state_js, [rec])
    text = page.evaluate("() => document.querySelector('.fcc-cr-card').textContent")
    assert "RCOI-2 had two spools (#96 and #97)" in text, text
    ended = page.evaluate(
        "() => Array.from(document.querySelectorAll('.fcc-cr-pick[data-line=\"pos:1\"] .fcc-cr-ended option'))"
        ".map(o => o.value)")
    assert ended == ["96", "97"], ended
