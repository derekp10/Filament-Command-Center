"""Group 17.1 — the Filament Details modal shows swatch + label-confirmed
status badges so the user can see at a glance whether a swatch has been
printed and whether the printed label has been physically confirmed.

Reads from existing extras:
  - `sample_printed` (true / false / missing)
  - `needs_label_print` (false=confirmed, true=needs print, missing=unknown)
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


def _find_any_filament(api_base_url: str):
    r = requests.get(f"{api_base_url}/api/filaments", timeout=10)
    if not r.ok:
        return None
    payload = r.json()
    fils = payload.get('filaments') if isinstance(payload, dict) else payload
    return (fils or [None])[0]


@pytest.mark.usefixtures("require_server")
def test_filament_details_renders_sample_and_label_status_rows(page: Page, base_url: str, api_base_url: str, reset_dom_state_js: str):
    fil = _find_any_filament(api_base_url)
    if not fil:
        pytest.skip("No filaments in dev environment.")
    fid = fil.get('id')

    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function("typeof openFilamentDetails === 'function' && modals && modals.filamentModal", timeout=10000)
    page.evaluate(f"openFilamentDetails({fid})")
    expect(page.locator("#filamentModal")).to_be_visible(timeout=5000)

    sample_el = page.locator("#fil-detail-sample-status")
    label_el = page.locator("#fil-detail-label-status")
    expect(sample_el).to_be_visible(timeout=3000)
    expect(label_el).to_be_visible(timeout=3000)

    sample_txt = sample_el.inner_text().strip()
    label_txt = label_el.inner_text().strip()
    # Either confirmed-status, needs-print, or unknown — all are valid for an
    # arbitrary dev filament. Just assert the badge populated with a known
    # state and isn't empty / placeholder.
    assert sample_txt in {"✅ Yes", "No", "unknown"}, f"unexpected sample status: {sample_txt!r}"
    assert label_txt in {"✅ Confirmed", "🖨️ Needs print", "unknown"}, f"unexpected label status: {label_txt!r}"


# ---------------------------------------------------------------------------
# Inline editor (scan-match-pipeline branch): the Filament Details modal now
# exposes a ✏️ button next to the Swatch-Printed badge → promptEditSampleStatus
# → a Swal radio → a sibling-preserving /api/update_filament write. Previously
# sample_printed could only be SET true as a side-effect of a FIL: label-confirm
# scan; this is the first surface that can set it false or clear it on demand.
# ---------------------------------------------------------------------------

def _norm_sample(v):
    """Mirror the frontend's tri-state read of a stored sample_printed extra."""
    if v is None:
        return None
    s = str(v).strip().strip('"').lower()
    if s in ("true", "1"):
        return "true"
    if s in ("false", "0"):
        return "false"
    return None


def _get_sample(api_base_url: str, fid):
    r = requests.get(f"{api_base_url}/api/filaments/{fid}", timeout=10)
    data = (r.json() or {}).get("data") or {}
    return _norm_sample((data.get("extra") or {}).get("sample_printed"))


def _set_sample(api_base_url: str, fid, value):
    """Set (True/False) or clear (None) sample_printed via the same endpoint the
    UI uses, merging against the live extra so siblings survive."""
    r = requests.get(f"{api_base_url}/api/filaments/{fid}", timeout=10)
    data = (r.json() or {}).get("data") or {}
    extra = dict(data.get("extra") or {})
    if value is None:
        extra.pop("sample_printed", None)
    else:
        extra["sample_printed"] = bool(value)
    requests.post(
        f"{api_base_url}/api/update_filament",
        json={"id": fid, "data": {"extra": extra}},
        timeout=10,
    )


@pytest.mark.usefixtures("require_server")
def test_filament_sample_status_inline_toggle_round_trip(page: Page, base_url: str, api_base_url: str, reset_dom_state_js: str):
    fil = _find_any_filament(api_base_url)
    if not fil:
        pytest.skip("No filaments in dev environment.")
    fid = fil.get("id")

    original = _get_sample(api_base_url, fid)
    # Pick a target guaranteed to differ from the current value so the handler's
    # unchanged-value no-op guard doesn't short-circuit the save.
    target = "true" if original != "true" else "false"
    expected_badge = "✅ Yes" if target == "true" else "No"

    try:
        page.goto(base_url)
        page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
        page.evaluate(reset_dom_state_js)
        page.wait_for_function(
            "typeof openFilamentDetails === 'function' && typeof promptEditSampleStatus === 'function' && modals && modals.filamentModal",
            timeout=10000,
        )
        page.evaluate(f"openFilamentDetails({fid})")
        expect(page.locator("#filamentModal")).to_be_visible(timeout=5000)

        # Baseline QR-deck position with the filament modal already open, so we
        # can prove the dialog itself doesn't reflow the page.
        qr = page.locator("#qr-locs")
        qr_before = qr.bounding_box() if qr.count() else None

        # The ✏️ edit affordance sits right after the read-only badge.
        edit_btn = page.locator('button[title="Edit Swatch Printed status"]')
        expect(edit_btn).to_be_visible(timeout=3000)
        edit_btn.click()

        # Dark custom-list dialog (NOT Swal's white radio widget) → pick state → Save.
        expect(page.locator(".swal2-popup")).to_be_visible(timeout=4000)
        # white-on-white regression: three dark option rows, not the white .swal2-radio pill.
        assert page.locator(".swal2-popup .swal-sample-item").count() == 3
        # QR-shift regression: heightAuto:false means the dashboard QR deck stays put.
        if qr_before is not None:
            qr_after = page.locator("#qr-locs").bounding_box()
            assert qr_after is not None and abs(qr_after["y"] - qr_before["y"]) <= 3, \
                f"dashboard QR deck shifted when the dialog opened: {qr_before['y']} -> {qr_after and qr_after['y']}"
        # Drive the pick entirely by keyboard — Derek's report: the dialog must
        # accept keyboard input. ↑/↓ move the highlight, Enter saves.
        order = ["true", "false", ""]
        cur_idx = order.index(original) if original in order else 2
        for _ in range((order.index(target) - cur_idx) % len(order)):
            page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")

        # The save chains into openFilamentDetails(fid, true), re-rendering the
        # badge — expect() auto-retries until the refresh lands.
        expect(page.locator("#fil-detail-sample-status")).to_have_text(expected_badge, timeout=6000)

        # And the write actually persisted to Spoolman.
        assert _get_sample(api_base_url, fid) == target, "sample_printed did not persist via the API"
    finally:
        _set_sample(api_base_url, fid, {"true": True, "false": False}.get(original))
