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
                if sid == OTHER_SPOOL["id"]:
                    self._json(route, {"success": True, "data": OTHER_SPOOL})
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
