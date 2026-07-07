"""
Tests for the Archive-Empty-Weight prompt flow.

Covers:
  - /api/spool/update response surfaces auto_archived + needs_empty_weight_prompt
    flags with the right semantics (filament vs vendor fallback).
  - window.showArchiveEmptyWeightPrompt exists and renders the expected
    copy (#ID, filament ID, weight input).
  - Save path POSTs spool_weight to /api/update_filament.
  - 2026-07-06 "combine + propagate": the prompt was migrated Swal -> mountOverlay,
    takes a pre-fill (so a Gross-weigh tare isn't re-asked), and offers an opt-in
    vendor/brand-default propagate that PATCHes /api/vendors/<id>.
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import Page, expect

# Unit import for the backend-side shape check
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app as app_module  # noqa: E402


# --- Backend API shape ------------------------------------------------------


def test_spool_update_response_includes_archive_flags(monkeypatch):
    """The endpoint must report auto_archived + needs_empty_weight_prompt."""
    client = app_module.app.test_client()

    # Fake spool before update: not archived.
    pre = {"id": 99, "archived": False, "initial_weight": 1000, "used_weight": 500}
    # Fake spool after update: archived (weight hit 0), filament with no spool_weight.
    post = {
        "id": 99,
        "archived": True,
        "initial_weight": 1000,
        "used_weight": 1000,
        "filament": {
            "id": 7,
            "spool_weight": None,
            "vendor": {"name": "Overture"},  # no empty_spool_weight
        },
    }

    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: post)

    r = client.post("/api/spool/update", json={"id": 99, "updates": {"used_weight": 1000}})
    payload = r.get_json()
    assert payload["status"] == "success"
    assert payload["auto_archived"] is True
    assert payload["needs_empty_weight_prompt"] is True
    assert payload["filament_id"] == 7


def test_spool_update_no_prompt_when_filament_has_weight(monkeypatch):
    """If the filament already has spool_weight, don't prompt."""
    client = app_module.app.test_client()
    pre = {"id": 99, "archived": False, "initial_weight": 1000, "used_weight": 500}
    post = {
        "id": 99,
        "archived": True,
        "initial_weight": 1000,
        "used_weight": 1000,
        "filament": {"id": 7, "spool_weight": 220, "vendor": {}},
    }
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: post)

    r = client.post("/api/spool/update", json={"id": 99, "updates": {"used_weight": 1000}})
    payload = r.get_json()
    assert payload["auto_archived"] is True
    assert payload["needs_empty_weight_prompt"] is False


def test_spool_update_no_prompt_when_vendor_has_weight(monkeypatch):
    """If the vendor has empty_spool_weight, the inheritance chain wins — no prompt."""
    client = app_module.app.test_client()
    pre = {"id": 99, "archived": False, "initial_weight": 1000, "used_weight": 500}
    post = {
        "id": 99,
        "archived": True,
        "initial_weight": 1000,
        "used_weight": 1000,
        "filament": {
            "id": 7,
            "spool_weight": None,
            "vendor": {"name": "Sunlu", "empty_spool_weight": 167},
        },
    }
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: post)

    r = client.post("/api/spool/update", json={"id": 99, "updates": {"used_weight": 1000}})
    payload = r.get_json()
    assert payload["auto_archived"] is True
    assert payload["needs_empty_weight_prompt"] is False


def test_spool_update_no_auto_archive_when_already_archived(monkeypatch):
    """A spool that was already archived shouldn't re-fire the auto_archived flag."""
    client = app_module.app.test_client()
    pre = {"id": 99, "archived": True, "initial_weight": 1000, "used_weight": 1000}
    post = {"id": 99, "archived": True, "initial_weight": 1000, "used_weight": 1000}
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: post)

    r = client.post("/api/spool/update", json={"id": 99, "updates": {"comment": "x"}})
    payload = r.get_json()
    assert payload["auto_archived"] is False
    assert payload["needs_empty_weight_prompt"] is False


# --- Frontend wiring --------------------------------------------------------
#
# The prompt was migrated from Swal -> window.mountOverlay (2026-07-06, the
# "combine + propagate" empty-weight work), so these assert the overlay DOM
# (#fcc-archive-empty-*), the pre-fill, and the vendor-propagate opt-in.


def _stub_filament_and_writes(page, vendor=None):
    """Stub /api/filament_details, /api/update_filament, and PATCH /api/vendors
    so the prompt renders + saves without a live Spoolman. Records the last
    filament + vendor payloads (and the vendor path) on window."""
    if vendor is None:
        vendor = {"id": 1, "name": "CC3D"}
    page.evaluate(
        """
        (vendor) => {
            window.__updateFilamentPayload = null;
            window.__vendorPayload = null;
            window.__vendorPath = null;
            const origFetch = window.fetch;
            window.fetch = async (url, opts) => {
                const u = typeof url === 'string' ? url : (url && url.url) || '';
                if (u.startsWith('/api/filament_details')) {
                    return new Response(JSON.stringify({
                        id: 7, name: 'Crimson Red', material: 'PLA',
                        spool_weight: null, vendor: vendor
                    }), { status: 200, headers: {'Content-Type': 'application/json'} });
                }
                if (u === '/api/update_filament') {
                    window.__updateFilamentPayload = JSON.parse(opts.body);
                    return new Response(JSON.stringify({ success: true, filament: { id: 7 } }),
                        { status: 200, headers: {'Content-Type': 'application/json'} });
                }
                if (u.indexOf('/api/vendors/') === 0 && opts && opts.method === 'PATCH') {
                    window.__vendorPath = u;
                    window.__vendorPayload = JSON.parse(opts.body);
                    return new Response(JSON.stringify({ success: true, vendor: { id: 1 } }),
                        { status: 200, headers: {'Content-Type': 'application/json'} });
                }
                return origFetch(url, opts);
            };
        }
        """,
        vendor,
    )


def test_show_archive_empty_weight_prompt_exists(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function(
        "typeof window.showArchiveEmptyWeightPrompt === 'function'", timeout=5_000
    )


def test_archive_empty_weight_prompt_renders_and_saves(page: Page):
    """Open the overlay with stubbed backends, enter a weight, save, verify POST."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.showArchiveEmptyWeightPrompt === 'function'")
    _stub_filament_and_writes(page)

    # Fire-and-forget: the function only resolves when the overlay is dismissed.
    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=3_000)

    # Copy check — the overlay should identify the spool, filament, and vendor.
    popup_text = page.locator("#fcc-archive-empty-overlay").inner_text()
    assert "#99" in popup_text, popup_text
    assert "#7" in popup_text, popup_text
    assert "CC3D" in popup_text, popup_text  # vendor name shown

    page.locator("#fcc-archive-empty-wt").fill("168")
    page.locator("#fcc-archive-save").click()

    page.wait_for_function("window.__updateFilamentPayload !== null", timeout=3_000)
    assert page.evaluate("() => window.__updateFilamentPayload") == {
        "id": 7, "data": {"spool_weight": 168}}
    # Propagate NOT ticked -> no vendor PATCH.
    assert page.evaluate("() => window.__vendorPayload") is None


def test_archive_empty_weight_prompt_prefill_is_a_confirm(page: Page):
    """The 3rd arg pre-fills the input so a Gross-weigh tare isn't re-asked
    (Derek's 'one pre-filled confirm'); confirming persists the pre-filled value."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.showArchiveEmptyWeightPrompt === 'function'")
    _stub_filament_and_writes(page)

    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7, 210); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=3_000)
    assert page.locator("#fcc-archive-empty-wt").input_value() == "210"

    page.locator("#fcc-archive-save").click()
    page.wait_for_function("window.__updateFilamentPayload !== null", timeout=3_000)
    assert page.evaluate("() => window.__updateFilamentPayload") == {
        "id": 7, "data": {"spool_weight": 210}}


def test_archive_empty_weight_prompt_propagates_to_vendor(page: Page):
    """Ticking the vendor checkbox also PATCHes the vendor's empty_spool_weight."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.showArchiveEmptyWeightPrompt === 'function'")
    _stub_filament_and_writes(page, {"id": 1, "name": "CC3D"})

    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=3_000)
    page.locator("#fcc-archive-empty-wt").fill("168")
    page.locator("#fcc-archive-propagate").check()
    page.locator("#fcc-archive-save").click()

    page.wait_for_function("window.__vendorPayload !== null", timeout=3_000)
    assert page.evaluate("() => window.__updateFilamentPayload") == {
        "id": 7, "data": {"spool_weight": 168}}
    assert page.evaluate("() => window.__vendorPath") == "/api/vendors/1"
    assert page.evaluate("() => window.__vendorPayload") == {
        "data": {"empty_spool_weight": 168}}


def test_archive_empty_weight_prompt_no_vendor_checkbox_when_vendor_set(page: Page):
    """When the vendor ALREADY has an empty_spool_weight there is nothing to fill,
    so the propagate checkbox is not offered (avoids a silent brand-wide overwrite)."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.showArchiveEmptyWeightPrompt === 'function'")
    _stub_filament_and_writes(page, {"id": 1, "name": "CC3D", "empty_spool_weight": 167})

    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=3_000)
    assert page.locator("#fcc-archive-propagate").count() == 0


def test_archive_empty_weight_prompt_later_is_noop(page: Page):
    """Tapping 'Later' should close the overlay without POSTing."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.showArchiveEmptyWeightPrompt === 'function'")
    _stub_filament_and_writes(page, {})  # no vendor id -> no propagate checkbox

    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=3_000)

    page.locator("#fcc-archive-later").click()
    page.wait_for_selector("#fcc-archive-empty-wt", state="detached", timeout=3_000)
    assert page.evaluate("() => window.__updateFilamentPayload") is None


def test_archive_empty_weight_prompt_validates_weight(page: Page):
    """Empty / non-positive input surfaces an inline error, and does not save."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.showArchiveEmptyWeightPrompt === 'function'")
    _stub_filament_and_writes(page, {})

    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=3_000)

    # Leave weight blank, click save -> inline validation, no POST.
    page.locator("#fcc-archive-save").click()
    err = page.locator("#fcc-archive-empty-err")
    expect(err).to_be_visible()
    expect(err).to_contain_text("positive")
    assert page.evaluate("() => window.__updateFilamentPayload") is None


def test_archive_empty_weight_prompt_enter_key_submits(page: Page):
    """L46: Enter from the input submits the prompt (no mouse needed)."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.showArchiveEmptyWeightPrompt === 'function'")
    _stub_filament_and_writes(page)

    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=3_000)

    field = page.locator("#fcc-archive-empty-wt")
    field.fill("168")
    field.press("Enter")

    page.wait_for_function("window.__updateFilamentPayload !== null", timeout=3_000)
    assert page.evaluate("() => window.__updateFilamentPayload") == {
        "id": 7, "data": {"spool_weight": 168}}


def test_archive_empty_weight_prompt_enter_with_blank_input_validates(page: Page):
    """L46 corollary: Enter on a blank input triggers validation, not a save."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.showArchiveEmptyWeightPrompt === 'function'")
    _stub_filament_and_writes(page, {})

    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=3_000)

    page.locator("#fcc-archive-empty-wt").press("Enter")
    err = page.locator("#fcc-archive-empty-err")
    expect(err).to_be_visible()
    assert page.evaluate("() => window.__updateFilamentPayload") is None
