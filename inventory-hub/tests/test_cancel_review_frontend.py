"""Frontend test for the cancelled-print review overlay (FilaBridge §9.7 /
slice 5). Route-mocks the backend so the overlay's render + nudge + confirm-POST
logic is exercised without seeding a real pending record server-side.
"""
from __future__ import annotations

import json


def test_cancel_review_overlay_renders_nudges_and_confirms(page, require_server, base_url):
    page.goto(base_url, wait_until='domcontentloaded')

    pending = {"pending": [{
        "printer_name": "XL", "job_id": "FE-1", "filename": "t.gcode",
        "progress": 0.4, "total_grams": 20.0,
        "spools": [{
            "sid": 100, "toolhead": "XL-1", "position": 0, "grams": 20.0,
            "current_used": 100.0, "initial_weight": 1000.0,
            "remaining_before": 900.0, "remaining_after": 880.0,
            "display": "#100 PLA Red", "color": "ff0000",
        }],
    }]}
    captured = {"confirm_body": None}

    page.route("**/api/cancel_deduct/pending",
               lambda route: route.fulfill(status=200, content_type="application/json",
                                           body=json.dumps(pending)))

    def _confirm(route):
        captured["confirm_body"] = route.request.post_data
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"status": "confirmed",
                                       "applied": [{"sid": 100, "grams": 25, "remaining": 875}],
                                       "errors": []}))
    page.route("**/api/cancel_deduct/confirm", _confirm)

    # Open the overlay (the activity-log "🛑 Review" button calls this).
    page.evaluate("() => window.openCancelReview()")
    page.wait_for_selector("#fcc-cancel-review-overlay .fcc-cr-card", timeout=5000)

    # The spool row + computed grams render.
    grams = page.query_selector('#fcc-cancel-review-overlay .fcc-cr-grams[data-sid="100"]')
    assert grams is not None, "grams input for spool 100 should render"
    assert grams.input_value() in ("20", "20.0"), grams.input_value()

    # The M486 over-estimate reminder is always shown (Derek 2026-06-12): per-
    # object cancels can't be auto-detected, so the review nudges the user to
    # trim the grams down when objects were cancelled mid-print.
    card = page.query_selector("#fcc-cancel-review-overlay .fcc-cr-card")
    assert "M486" in card.inner_text(), "M486 over-estimate reminder must show in the review"

    # Nudge 20 → 25 and confirm.
    grams.fill("25")
    page.click("#fcc-cancel-review-overlay .fcc-cr-confirm")

    # Confirm POST carried the nudged grams; overlay closes after success.
    page.wait_for_function("() => !document.getElementById('fcc-cancel-review-overlay')", timeout=5000)
    assert captured["confirm_body"] is not None, "confirm endpoint was never called"
    body = json.loads(captured["confirm_body"])
    assert body["printer_name"] == "XL" and body["job_id"] == "FE-1"
    assert body["updates"] == {"100": 25}, body["updates"]


def test_cancel_review_dismiss_drops_card(page, require_server, base_url):
    page.goto(base_url, wait_until='domcontentloaded')
    pending = {"pending": [{
        "printer_name": "XL", "job_id": "FE-2", "filename": "t.gcode",
        "progress": 0.3, "total_grams": 12.0,
        "spools": [{"sid": 101, "toolhead": "XL-1", "position": 0, "grams": 12.0,
                    "current_used": 0.0, "initial_weight": 1000.0,
                    "remaining_before": 1000.0, "remaining_after": 988.0,
                    "display": "#101", "color": "00ff00"}],
    }]}
    dismissed = {"hit": False}
    page.route("**/api/cancel_deduct/pending",
               lambda route: route.fulfill(status=200, content_type="application/json",
                                           body=json.dumps(pending)))

    def _dismiss(route):
        dismissed["hit"] = True
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"status": "dismissed"}))
    page.route("**/api/cancel_deduct/dismiss", _dismiss)

    page.evaluate("() => window.openCancelReview()")
    page.wait_for_selector("#fcc-cancel-review-overlay .fcc-cr-card", timeout=5000)
    # Discard is a two-click confirm (arm → "⚠️ Confirm discard") so an
    # accidental click can't drop a review (slice 5.1).
    page.click("#fcc-cancel-review-overlay .fcc-cr-discard")   # arm
    page.click("#fcc-cancel-review-overlay .fcc-cr-discard")   # confirm → fires dismiss
    page.wait_for_function("() => !document.getElementById('fcc-cancel-review-overlay')", timeout=5000)
    assert dismissed["hit"] is True


def _one_pending(job_id="FE-X"):
    return {"pending": [{
        "printer_name": "XL", "job_id": job_id, "filename": "t.gcode",
        "progress": 0.4, "total_grams": 20.0,
        "spools": [{"sid": 100, "toolhead": "XL-1", "position": 0, "grams": 20.0,
                    "current_used": 100.0, "initial_weight": 1000.0,
                    "remaining_before": 900.0, "remaining_after": 880.0,
                    "display": "#100", "color": "ff0000"}],
    }]}


def test_cancel_review_escape_closes_overlay(page, require_server, base_url):
    page.goto(base_url, wait_until='domcontentloaded')
    page.route("**/api/cancel_deduct/pending",
               lambda route: route.fulfill(status=200, content_type="application/json",
                                           body=json.dumps(_one_pending("FE-ESC"))))
    page.evaluate("() => window.openCancelReview()")
    page.wait_for_selector("#fcc-cancel-review-overlay .fcc-cr-card", timeout=5000)
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('fcc-cancel-review-overlay')", timeout=5000)


def test_cancel_review_dismiss_already_handled_closes_cleanly(page, require_server, base_url):
    """A concurrently-handled dismiss (backend returns already_handled) must
    still close the card cleanly, not leave a stuck disabled button."""
    page.goto(base_url, wait_until='domcontentloaded')
    page.route("**/api/cancel_deduct/pending",
               lambda route: route.fulfill(status=200, content_type="application/json",
                                           body=json.dumps(_one_pending("FE-AH"))))
    page.route("**/api/cancel_deduct/dismiss",
               lambda route: route.fulfill(status=200, content_type="application/json",
                                           body=json.dumps({"status": "already_handled"})))
    page.evaluate("() => window.openCancelReview()")
    page.wait_for_selector("#fcc-cancel-review-overlay .fcc-cr-card", timeout=5000)
    page.click("#fcc-cancel-review-overlay .fcc-cr-discard")   # arm
    page.click("#fcc-cancel-review-overlay .fcc-cr-discard")   # confirm → fires dismiss
    page.wait_for_function("() => !document.getElementById('fcc-cancel-review-overlay')", timeout=5000)


def test_cancel_review_no_pending_shows_no_overlay(page, require_server, base_url):
    page.goto(base_url, wait_until='domcontentloaded')
    page.route("**/api/cancel_deduct/pending",
               lambda route: route.fulfill(status=200, content_type="application/json",
                                           body=json.dumps({"pending": []})))
    page.evaluate("() => window.openCancelReview()")
    # No overlay mounts when there's nothing to review.
    page.wait_for_timeout(500)
    assert page.query_selector("#fcc-cancel-review-overlay") is None
