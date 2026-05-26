"""Tests for the Edit Filament Modal "Import from External" panel (Group 6.1).

Reuses the wizard's GET /api/external/search backend and
window.computeFilamentBackfillDiff to render a per-field checkbox preview.
Apply Selected writes form values only — user must click the modal Save to persist.

Covers:
  - Panel DOM is always present in the Edit Filament modal (Advanced tab).
  - editfilExternalSearch hits /api/external/search with the right source+q.
  - URL auto-detect switches the source dropdown.
  - Single-result auto-previews; multi-result populates the picker.
  - Preview renders silent fills (default-checked) and mismatches (default-unchecked).
  - Apply Selected writes form values for checked rows only.
  - Apply does NOT POST to /api/update_filament (user clicks Save for that).
"""
from __future__ import annotations

from playwright.sync_api import Page, expect


def _stub_external_search(page: Page) -> None:
    """Install a window.fetch stub returning a controlled parser template.

    Captures the URL of the last /api/external/search call so tests can
    assert the source+q parameters were passed correctly.
    """
    page.evaluate(
        """
        window.__lastExternalSearchUrl = null;
        window.__updateFilamentCalls = 0;
        const origFetch = window.fetch;
        window.fetch = async (url, opts) => {
            if (typeof url !== 'string') return origFetch(url, opts);
            const method = (opts && opts.method) || 'GET';
            if (url.startsWith('/api/external/search')) {
                window.__lastExternalSearchUrl = url;
                return new Response(JSON.stringify({
                    success: true,
                    source: 'spoolman',
                    results: [{
                        id: 'demo-001',
                        name: 'Galaxy Black',
                        material: 'PLA',
                        vendor: {name: 'Acme Filament Co'},
                        weight: 1000,
                        spool_weight: 200,
                        diameter: 1.75,
                        density: 1.24,
                        color_hex: '112233',
                        color_name: 'Galaxy Black',
                        external_link: 'https://example.com/galaxy',
                        settings_extruder_temp: 215,
                        settings_bed_temp: 60,
                        extra: {
                            nozzle_temp_max: '"235"',
                            bed_temp_max: '"65"',
                        },
                    }]
                }), {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/vendors' && method === 'GET') {
                return new Response(JSON.stringify({success: true, vendors: []}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/external/fields') {
                return new Response(JSON.stringify({success: true, fields: {filament: [
                    {key: 'filament_attributes', field_type: 'choice', multi_choice: true, choices: ['Silk']},
                    {key: 'slicer_profile', field_type: 'choice', multi_choice: false, choices: []},
                ], spool: []}}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/materials') {
                return new Response(JSON.stringify({success: true, materials: ['PLA']}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/update_filament' && method === 'POST') {
                window.__updateFilamentCalls++;
                return new Response(JSON.stringify({success: true, filament: {id: 999}}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            return origFetch(url, opts);
        };
        """
    )


def _open_edit_filament(page: Page, fil: dict) -> None:
    """Open the Edit Filament modal with a stubbed filament, switch to the
    Advanced tab, and expand the Import-from-External collapsible so its
    input fields are visible to Playwright fill operations."""
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    expect(page.locator("#editFilamentModal.show")).to_have_count(1)
    # The import panel lives inside the Advanced tab inside a Bootstrap
    # collapse — both must be expanded before its inputs are visible.
    page.locator("#editfil-tab-advanced-btn").click()
    page.evaluate(
        "() => { const c = document.getElementById('editfil-import-panel');"
        "  c.classList.add('show'); c.style.height = 'auto'; }"
    )
    expect(page.locator("#editfil-external-query")).to_be_visible()


def _wait_ready(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    page.wait_for_function("typeof window.editfilExternalSearch === 'function'")


def test_import_panel_dom_present(page: Page):
    _wait_ready(page)
    expect(page.locator("#editfil-import-panel")).to_have_count(1)
    expect(page.locator("#editfil-external-source")).to_have_count(1)
    expect(page.locator("#editfil-external-query")).to_have_count(1)
    expect(page.locator("#editfil-external-preview")).to_have_count(1)


def test_search_calls_backend_with_source_and_query(page: Page):
    _wait_ready(page)
    _stub_external_search(page)
    _open_edit_filament(page, {
        "id": 501, "name": "Existing Black", "material": "PLA",
        "vendor": {"id": 1, "name": "Old Vendor"},
    })
    page.locator("#editfil-external-source").select_option("spoolman")
    page.locator("#editfil-external-query").fill("galaxy black")
    page.evaluate("() => window.editfilExternalSearch()")
    page.wait_for_function("window.__lastExternalSearchUrl !== null")
    url = page.evaluate("() => window.__lastExternalSearchUrl")
    assert "source=spoolman" in url
    assert "q=galaxy" in url


def test_url_autodetect_switches_source_to_prusament(page: Page):
    _wait_ready(page)
    _stub_external_search(page)
    _open_edit_filament(page, {"id": 502, "name": "X", "material": "PLA"})
    page.locator("#editfil-external-query").fill("https://prusament.com/spool/12345/whatever")
    page.evaluate("() => window.editfilExternalSearch()")
    page.wait_for_function("window.__lastExternalSearchUrl !== null")
    assert page.locator("#editfil-external-source").input_value() == "prusament"
    url = page.evaluate("() => window.__lastExternalSearchUrl")
    assert "source=prusament" in url


def test_single_result_auto_previews_with_per_field_checkboxes(page: Page):
    _wait_ready(page)
    _stub_external_search(page)
    # Existing filament has nothing set beyond name/material → all parser
    # fields should render as silent_fill with default-checked checkboxes.
    _open_edit_filament(page, {
        "id": 503, "name": "Existing", "material": "PLA",
        "vendor": {"id": 1, "name": "Old Vendor"},
    })
    page.locator("#editfil-external-query").fill("galaxy")
    page.evaluate("() => window.editfilExternalSearch()")
    expect(page.locator("#editfil-external-preview:not(.d-none)")).to_have_count(1)
    rows = page.locator(".editfil-import-row")
    expect(rows.first).to_be_visible()
    # All silent_fill rows should be checked by default (per spec).
    checkbox_states = page.evaluate(
        "() => Array.from(document.querySelectorAll('.editfil-import-row'))"
        "  .map(cb => ({key: cb.dataset.key, checked: cb.checked, disabled: cb.disabled}))"
    )
    assert any(s["key"] == "diameter" and s["checked"] for s in checkbox_states), checkbox_states
    assert any(s["key"] == "density" and s["checked"] for s in checkbox_states), checkbox_states


def test_apply_selected_writes_form_values_without_posting(page: Page):
    _wait_ready(page)
    _stub_external_search(page)
    _open_edit_filament(page, {
        "id": 504, "name": "Existing", "material": "PLA",
        "vendor": {"id": 1, "name": "Old Vendor"},
    })
    page.locator("#editfil-external-query").fill("galaxy")
    page.evaluate("() => window.editfilExternalSearch()")
    expect(page.locator("#editfil-external-preview:not(.d-none)")).to_have_count(1)
    page.evaluate("() => window.editfilExternalApplySelected()")

    # Specs tab inputs should now hold the parser's values.
    page.locator("#editfil-tab-specs-btn").click()
    assert page.locator("#editfil-diameter").input_value() == "1.75"
    assert page.locator("#editfil-density").input_value() == "1.24"
    assert page.locator("#editfil-spool-weight").input_value() == "200"
    assert page.locator("#editfil-weight").input_value() == "1000"
    assert page.locator("#editfil-nozzle").input_value() == "215"
    assert page.locator("#editfil-bed").input_value() == "60"
    # Max temps live as text-typed extras — written without JSON wrapping.
    assert page.locator("#editfil-nozzle-max").input_value() == "235"
    assert page.locator("#editfil-bed-max").input_value() == "65"

    # Apply must NOT trigger a save — that's the modal Save button's job.
    update_calls = page.evaluate("() => window.__updateFilamentCalls")
    assert update_calls == 0, f"Apply Selected unexpectedly POSTed {update_calls} times"


def test_l202_collapse_leaves_no_sliver(page: Page):
    """L202 — after toggling the Import-from-External panel closed, no child
    should remain visible. Bootstrap's 350ms height transition was leaving
    the top child (Source <select>) briefly rendered inside the animating
    height window; the snap-collapse CSS in global.css suppresses that.
    Asserts the panel is fully hidden immediately after the toggle click."""
    _wait_ready(page)
    _open_edit_filament(page, {
        "id": 1, "name": "Probe", "material": "PLA",
        "vendor": {"id": 1, "name": "V"},
    })
    # _open_edit_filament already opened the panel via .add('show'); close it
    # through the real Bootstrap toggle so we exercise the .collapsing path.
    page.locator("[data-bs-target='#editfil-import-panel']").click()
    panel = page.locator("#editfil-import-panel")
    expect(panel).not_to_have_class("collapse show")
    info = panel.evaluate("""
        el => {
            const cs = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return { display: cs.display, rectH: r.height };
        }
    """)
    assert info["display"] == "none", f"panel not hidden, got display={info['display']}"
    assert info["rectH"] == 0, f"panel still has height, got {info['rectH']}"
    src_h = page.locator("#editfil-external-source").evaluate(
        "el => el.getBoundingClientRect().height"
    )
    assert src_h == 0, f"source select still visible, height={src_h}"


def test_apply_skips_unchecked_rows(page: Page):
    _wait_ready(page)
    _stub_external_search(page)
    _open_edit_filament(page, {
        "id": 505, "name": "Existing", "material": "PLA",
        "vendor": {"id": 1, "name": "Old Vendor"},
    })
    page.locator("#editfil-external-query").fill("galaxy")
    page.evaluate("() => window.editfilExternalSearch()")
    # Uncheck the diameter row → it should NOT propagate to the form.
    page.evaluate(
        "() => { const cb = document.querySelector('.editfil-import-row[data-key=\"diameter\"]');"
        "  if (cb) cb.checked = false; }"
    )
    page.evaluate("() => window.editfilExternalApplySelected()")
    page.locator("#editfil-tab-specs-btn").click()
    # Diameter stays as the original (empty) since the row was unchecked.
    assert page.locator("#editfil-diameter").input_value() == ""
    # Density was checked → applied.
    assert page.locator("#editfil-density").input_value() == "1.24"
