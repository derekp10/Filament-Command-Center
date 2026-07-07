"""L18 Config System Phase 1 — Settings card E2E.

Closes the acceptance criteria the unit suite can't reach:
  #1  a setting persists across a full page reload,
  #5  the client weigh-mode writes the SAME localStorage key weight_entry.js reads,
  #6  dark-theme contrast (no white-on-white / dark-on-dark).

NON-DESTRUCTIVE: exercises only the CLIENT-scope pref (localStorage in the test
browser context), asserts the SERVER inputs merely render (never saves a server
change, so dev config.json is untouched), and restores the one pref it touches.
The server write path is covered by test_config_save.py.
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

WEIGH_KEY = "fcc.weighEntry.defaultMode"
MODE_SEL = '.cfgset-input[data-key="fcc.weighEntry.defaultMode"]'


def _open_settings(page: Page, base_url: str, reset_dom_state_js: str):
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function("typeof window.openConfigModal === 'function'", timeout=10000)
    page.evaluate("window.openConfigModal()")
    expect(page.locator("#configModal")).to_be_visible(timeout=5000)
    # the schema-driven card finishes rendering (placeholder replaced by inputs)
    page.wait_for_function(
        """() => {
            const el = document.getElementById('config-generated-settings');
            return el && el.querySelector('.cfgset-input') !== null;
        }""",
        timeout=10000,
    )


@pytest.mark.usefixtures("require_server")
def test_settings_card_renders_all_fields(page: Page, base_url: str, reset_dom_state_js: str):
    _open_settings(page, base_url, reset_dom_state_js)
    sync = page.locator('.cfgset-input[data-key="sync_delay"]')
    # fcc_owns_completion_deduct is the surviving server bool field
    # (auto_recover_filabridge_errors was removed in the FilaBridge cleanup).
    deduct = page.locator('.cfgset-input[data-key="fcc_owns_completion_deduct"]')
    mode = page.locator(MODE_SEL)
    expect(sync).to_be_visible()
    expect(deduct).to_be_visible()
    expect(mode).to_be_visible()
    assert sync.evaluate("el => el.type") == "number"
    assert deduct.evaluate("el => el.type") == "checkbox"
    assert mode.evaluate("el => el.tagName.toLowerCase()") == "select"
    expect(page.locator("#cfgset-save")).to_be_visible()


@pytest.mark.usefixtures("require_server")
def test_settings_card_contrast(page: Page, base_url: str, reset_dom_state_js: str):
    # criterion #6: light-on-dark, not white-on-white / dark-on-dark
    _open_settings(page, base_url, reset_dom_state_js)
    colors = page.locator(MODE_SEL).evaluate(
        "el => { const s = getComputedStyle(el); return { color: s.color, bg: s.backgroundColor }; }"
    )

    def lum(rgb):
        nums = re.findall(r"[\d.]+", rgb or "")
        if len(nums) < 3:
            return None
        r, g, b = float(nums[0]), float(nums[1]), float(nums[2])
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    tl, bl = lum(colors["color"]), lum(colors["bg"])
    assert tl is not None and bl is not None
    assert abs(tl - bl) > 80, f"insufficient contrast: text={colors['color']} bg={colors['bg']}"


@pytest.mark.usefixtures("require_server")
def test_client_weigh_mode_persists_across_reload(page: Page, base_url: str, reset_dom_state_js: str):
    _open_settings(page, base_url, reset_dom_state_js)
    original = page.evaluate("(k) => window.localStorage.getItem(k)", WEIGH_KEY)
    try:
        current = page.locator(MODE_SEL).input_value()
        target = "net" if current != "net" else "gross"
        page.locator(MODE_SEL).select_option(target)
        page.locator("#cfgset-save").click()
        # #5: the SAME localStorage key weight_entry.js reads is written
        page.wait_for_function(
            "([k, v]) => window.localStorage.getItem(k) === v",
            arg=[WEIGH_KEY, target],
            timeout=5000,
        )
        # #1: survives a full reload and the reopened select reflects it
        _open_settings(page, base_url, reset_dom_state_js)
        assert page.evaluate("(k) => window.localStorage.getItem(k)", WEIGH_KEY) == target
        assert page.locator(MODE_SEL).input_value() == target
    finally:
        page.evaluate(
            "([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }",
            [WEIGH_KEY, original],
        )


@pytest.mark.usefixtures("require_server")
def test_phase2_secret_and_connection_fields_render(page: Page, base_url: str, reset_dom_state_js: str):
    # Non-destructive: never clicks Save with a typed secret, so the real key
    # on disk is never touched.
    _open_settings(page, base_url, reset_dom_state_js)
    sec = page.locator('.cfgset-input[data-key="SCRAPER_API_KEY"]')
    expect(sec).to_be_visible()
    # NOT type=password (so Chrome's password manager never engages); masked via CSS
    assert sec.evaluate("el => el.type") == "text"
    assert sec.evaluate("el => el.style.webkitTextSecurity") == "disc"
    assert sec.input_value() == ""  # plaintext is NEVER populated into the field
    # the eye toggles the CSS mask, not the input type
    eye = page.locator(".cfgset-eye").first
    eye.click()
    assert sec.evaluate("el => el.style.webkitTextSecurity") == "none"
    eye.click()
    assert sec.evaluate("el => el.style.webkitTextSecurity") == "disc"
    # no type=password anywhere in the card -> Chrome's credential heuristic can't fire
    assert page.locator('#config-generated-settings input[type="password"]').count() == 0
    # ip field renders as text, port as number
    assert page.locator('.cfgset-input[data-key="server_ip"]').evaluate("el => el.type") == "text"
    assert page.locator('.cfgset-input[data-key="spoolman_port"]').evaluate("el => el.type") == "number"


@pytest.mark.usefixtures("require_server")
def test_phase4_import_export_card(page: Page, base_url: str, reset_dom_state_js: str, tmp_path):
    # Non-destructive: drives Import to the dry-run confirm overlay, then CANCELS
    # (never clicks Apply), so the real config.json is untouched.
    _open_settings(page, base_url, reset_dom_state_js)
    expect(page.locator('a[href="/api/config/export"]')).to_be_visible()
    expect(page.locator("#cfgio-import-btn")).to_be_visible()
    # upload a config file -> dry-run -> the confirm overlay mounts
    f = tmp_path / "cfg-import.json"
    f.write_text('{"sync_delay": 0.7}', encoding="utf-8")
    page.locator("#cfgio-file").set_input_files(str(f))
    page.wait_for_selector("#cfgio-apply", timeout=8000)
    expect(page.locator("#cfgio-apply")).to_be_visible()
    # cancel — do NOT apply (keep the live config untouched)
    page.locator("#cfgio-cancel").click()
    page.wait_for_selector("#cfgio-apply", state="detached", timeout=5000)


@pytest.mark.usefixtures("require_server")
def test_phase3_printer_map_editor_renders(page: Page, base_url: str, reset_dom_state_js: str):
    # Non-destructive: never clicks Save, so the real printer_map is untouched.
    _open_settings(page, base_url, reset_dom_state_js)
    page.wait_for_function(
        "() => { const h = document.getElementById('config-printer-map'); return h && h.querySelector('.pm-row'); }",
        timeout=10000,
    )
    rows_before = page.locator("#config-printer-map .pm-row").count()
    assert rows_before >= 1
    # existing LocationID inputs are read-only (no rename of an existing toolhead)
    assert page.locator("#config-printer-map .pm-row .pm-loc").first.evaluate("el => el.readOnly") is True
    # "+ Add toolhead" appends a row whose LocationID IS editable
    page.locator("#pm-add").click()
    assert page.locator("#config-printer-map .pm-row").count() == rows_before + 1
    assert page.locator("#config-printer-map .pm-row .pm-loc").last.evaluate("el => el.readOnly") is False
    # removing the just-added row restores the count (client-side only; no save)
    page.locator("#config-printer-map .pm-row").last.locator(".pm-remove").click()
    assert page.locator("#config-printer-map .pm-row").count() == rows_before
