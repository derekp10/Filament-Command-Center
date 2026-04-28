"""
Tests for the Archive-Empty-Weight prompt flow.

Covers:
  - /api/spool/update response surfaces auto_archived + needs_empty_weight_prompt
    flags with the right semantics (filament vs vendor fallback).
  - window.showArchiveEmptyWeightPrompt exists and renders the expected
    copy (#ID, filament ID, weight input).
  - Save path POSTs spool_weight to /api/update_filament.
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


def test_show_archive_empty_weight_prompt_exists(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function(
        "typeof window.showArchiveEmptyWeightPrompt === 'function'", timeout=5_000
    )


def test_archive_empty_weight_prompt_renders_and_saves(page: Page):
    """Open the modal with stubbed backends, enter a weight, save, verify POST."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.showArchiveEmptyWeightPrompt === 'function'")

    # Stub both /api/filament_details (form open) and /api/update_filament (save).
    page.evaluate(
        """
        window.__updateFilamentPayload = null;
        const origFetch = window.fetch;
        window.fetch = async (url, opts) => {
            const u = typeof url === 'string' ? url : (url && url.url) || '';
            if (u.startsWith('/api/filament_details')) {
                return new Response(JSON.stringify({
                    id: 7,
                    name: 'Crimson Red',
                    material: 'PLA',
                    spool_weight: null,
                    vendor: { id: 1, name: 'CC3D' }
                }), { status: 200, headers: {'Content-Type': 'application/json'} });
            }
            if (u === '/api/update_filament') {
                window.__updateFilamentPayload = JSON.parse(opts.body);
                return new Response(JSON.stringify({ success: true, filament: { id: 7 } }),
                    { status: 200, headers: {'Content-Type': 'application/json'} });
            }
            return origFetch(url, opts);
        };
        """
    )

    # Open the prompt
    # Fire-and-forget: the function returns a Promise that only resolves when
    # the Swal is dismissed, so page.evaluate would hang if we returned it.
    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=3_000)

    # Copy check — the modal should identify the spool and filament.
    popup_text = page.locator(".swal2-popup").inner_text()
    assert "#99" in popup_text, popup_text
    assert "#7" in popup_text, popup_text
    assert "CC3D" in popup_text, popup_text  # vendor name shown

    # Enter a weight and save
    page.locator("#fcc-archive-empty-wt").fill("168")
    page.locator(".swal2-confirm").click()

    page.wait_for_function("window.__updateFilamentPayload !== null", timeout=3_000)
    payload = page.evaluate("() => window.__updateFilamentPayload")
    assert payload == {"id": 7, "data": {"spool_weight": 168}}


def test_archive_empty_weight_prompt_later_is_noop(page: Page):
    """Tapping 'Later' should close the modal without POSTing."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.showArchiveEmptyWeightPrompt === 'function'")

    page.evaluate(
        """
        window.__updateFilamentPayload = null;
        const origFetch = window.fetch;
        window.fetch = async (url, opts) => {
            const u = typeof url === 'string' ? url : (url && url.url) || '';
            if (u.startsWith('/api/filament_details')) {
                return new Response(JSON.stringify({ id: 7, name: 'X', material: 'PLA', vendor: {} }),
                    { status: 200, headers: {'Content-Type': 'application/json'} });
            }
            if (u === '/api/update_filament') {
                window.__updateFilamentPayload = JSON.parse(opts.body);
                return new Response(JSON.stringify({ success: true }), { status: 200 });
            }
            return origFetch(url, opts);
        };
        """
    )

    # Fire-and-forget: the function returns a Promise that only resolves when
    # the Swal is dismissed, so page.evaluate would hang if we returned it.
    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=3_000)

    # Click the Deny (Later) button
    page.locator(".swal2-deny").click()
    # Modal closes; no POST fired
    page.wait_for_selector("#fcc-archive-empty-wt", state="detached", timeout=3_000)
    payload = page.evaluate("() => window.__updateFilamentPayload")
    assert payload is None


def test_archive_empty_weight_prompt_validates_weight(page: Page):
    """Empty / negative input should surface a Swal validation message, not save."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.showArchiveEmptyWeightPrompt === 'function'")

    page.evaluate(
        """
        const origFetch = window.fetch;
        window.fetch = async (url, opts) => {
            const u = typeof url === 'string' ? url : (url && url.url) || '';
            if (u.startsWith('/api/filament_details')) {
                return new Response(JSON.stringify({ id: 7, name: 'X', material: 'PLA', vendor: {} }),
                    { status: 200, headers: {'Content-Type': 'application/json'} });
            }
            return origFetch(url, opts);
        };
        """
    )

    # Fire-and-forget: the function returns a Promise that only resolves when
    # the Swal is dismissed, so page.evaluate would hang if we returned it.
    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=3_000)

    # Leave weight blank, confirm
    page.locator(".swal2-confirm").click()
    validation = page.locator(".swal2-validation-message")
    expect(validation).to_be_visible()


def test_archive_empty_weight_prompt_enter_key_submits(page: Page):
    """L46: Enter key from the input should submit the prompt (no mouse needed)."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.showArchiveEmptyWeightPrompt === 'function'")

    page.evaluate(
        """
        window.__updateFilamentPayload = null;
        const origFetch = window.fetch;
        window.fetch = async (url, opts) => {
            const u = typeof url === 'string' ? url : (url && url.url) || '';
            if (u.startsWith('/api/filament_details')) {
                return new Response(JSON.stringify({
                    id: 7, name: 'Crimson Red', material: 'PLA',
                    spool_weight: null, vendor: { id: 1, name: 'CC3D' }
                }), { status: 200, headers: {'Content-Type': 'application/json'} });
            }
            if (u === '/api/update_filament') {
                window.__updateFilamentPayload = JSON.parse(opts.body);
                return new Response(JSON.stringify({ success: true, filament: { id: 7 } }),
                    { status: 200, headers: {'Content-Type': 'application/json'} });
            }
            return origFetch(url, opts);
        };
        """
    )

    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=3_000)

    # Type a weight then submit via Enter — no mouse click on the confirm button.
    field = page.locator("#fcc-archive-empty-wt")
    field.fill("168")
    field.press("Enter")

    page.wait_for_function("window.__updateFilamentPayload !== null", timeout=3_000)
    payload = page.evaluate("() => window.__updateFilamentPayload")
    assert payload == {"id": 7, "data": {"spool_weight": 168}}


def test_archive_empty_weight_prompt_enter_with_blank_input_validates(page: Page):
    """L46 corollary: Enter on a blank input must trigger validation, not save."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.showArchiveEmptyWeightPrompt === 'function'")

    page.evaluate(
        """
        window.__updateFilamentPayload = null;
        const origFetch = window.fetch;
        window.fetch = async (url, opts) => {
            const u = typeof url === 'string' ? url : (url && url.url) || '';
            if (u.startsWith('/api/filament_details')) {
                return new Response(JSON.stringify({ id: 7, name: 'X', material: 'PLA', vendor: {} }),
                    { status: 200, headers: {'Content-Type': 'application/json'} });
            }
            if (u === '/api/update_filament') {
                window.__updateFilamentPayload = JSON.parse(opts.body);
                return new Response(JSON.stringify({ success: true }), { status: 200 });
            }
            return origFetch(url, opts);
        };
        """
    )

    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=3_000)

    # Press Enter without filling — validation should fire and no POST should run.
    page.locator("#fcc-archive-empty-wt").press("Enter")
    validation = page.locator(".swal2-validation-message")
    expect(validation).to_be_visible()
    payload = page.evaluate("() => window.__updateFilamentPayload")
    assert payload is None
