"""E2E coverage for the per-spool Prusament scan flow added in Step 3 of
the Add-Inventory wizard. Exercises the route-mocked happy path, the
duplicate-filament auto-switch, and the parser-failure submit gate.

All tests intercept `/api/external/search` and `/api/create_inventory_wizard`
so no Spoolman state is mutated and no live Prusament HTTP is required."""

import json
import re

from playwright.sync_api import Page, expect


# --- canned Prusament parser responses ------------------------------------

def _prusament_result(initial_weight=998, spool_weight=215, mfg_date="2026-03-12",
                      length_m=330, color="Galaxy Black", external_link="https://prusament.com/spool/1/aaa/"):
    """Shape matches what PrusamentParser.search returns inside data.results[0]."""
    return {
        "id": "fake-prusa-id",
        "name": f"Prusament PLA {color}",
        "material": "PLA",
        "vendor": {"name": "Prusament"},
        "weight": initial_weight,
        "spool_weight": spool_weight,
        "diameter": 1.75,
        "density": 1.24,
        "color_hex": "111111",
        "color_name": color,
        "external_link": external_link,
        "settings_extruder_temp": 215,
        "settings_bed_temp": 60,
        "extra": {
            "prusament_manufacturing_date": mfg_date,
            "prusament_length_m": length_m,
        },
    }


def _route_external_search(page, response_factory):
    """Wire `/api/external/search?source=prusament` to a per-call factory.
    `response_factory(query_url)` returns the dict to return as `results[0]`,
    or None to simulate a failed scan (returns success:false)."""
    def _handler(route, request):
        url = request.url
        m = re.search(r"q=([^&]+)", url)
        q = m.group(1) if m else ""
        result = response_factory(q)
        if result is None:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"success": True, "results": []}),
            )
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"success": True, "results": [result]}),
        )
    page.route("**/api/external/search**", _handler)


def _capture_create_wizard(page):
    """Intercept the wizard-save POST and capture the outgoing payload.
    Returns a list that the test can read after submit."""
    captured: list[dict] = []

    def _handler(route, request):
        try:
            body = request.post_data_json or {}
        except Exception:
            body = {}
        captured.append(body)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"success": True, "filament_id": 999, "created_spools": [1, 2]}),
        )

    page.route("**/api/create_inventory_wizard", _handler)
    return captured


# --- tests -----------------------------------------------------------------

def test_per_spool_scan_sends_overrides_and_fills_step2(page: Page):
    """Golden path (manual mode, no existing match): two scans → wizard
    submits with spool_overrides AND the first scan filled Step 2."""
    # Mock /api/filaments to ensure no duplicate match (empty filament list).
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": []}),
    ))

    # First URL → "Galaxy Black" 998g, second URL → 1003g.
    def factory(q):
        if "aaa" in q:
            return _prusament_result(initial_weight=998, mfg_date="2026-03-12",
                                     external_link="https://prusament.com/spool/1/aaa/")
        if "bbb" in q:
            return _prusament_result(initial_weight=1003, mfg_date="2026-03-13",
                                     external_link="https://prusament.com/spool/2/bbb/")
        return None
    _route_external_search(page, factory)
    captured = _capture_create_wizard(page)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    modal = page.locator("#wizardModal")
    expect(modal).to_be_visible()
    page.locator("#btn-type-manual").click()

    # Bump quantity to 2 and trigger the row sync.
    qty = page.locator("#wiz-spool-qty")
    qty.fill("2")
    qty.dispatch_event("input")

    # Two rows should now exist.
    rows = page.locator("[data-spool-row-idx]")
    expect(rows).to_have_count(2)

    # Scan into row 0.
    rows.nth(0).locator("input[type='url']").fill("https://prusament.com/spool/1/aaa/")
    rows.nth(0).locator("input[type='url']").blur()
    expect(rows.nth(0).locator(".badge.bg-success")).to_be_visible(timeout=5000)

    # Step 2 should now reflect the Prusament template (material + color + weight).
    expect(page.locator("#wiz-fil-material")).to_have_value("PLA")
    expect(page.locator("#wiz-fil-color_name")).to_have_value("Galaxy Black")
    expect(page.locator("#wiz-fil-weight")).to_have_value("998")

    # Scan into row 1.
    rows.nth(1).locator("input[type='url']").fill("https://prusament.com/spool/2/bbb/")
    rows.nth(1).locator("input[type='url']").blur()
    expect(rows.nth(1).locator(".badge.bg-success")).to_be_visible(timeout=5000)

    # Submit.
    page.locator("#btn-wiz-submit").click()
    expect(page.locator("#wiz-status-msg")).to_contain_text("Success!", timeout=5000)

    assert len(captured) == 1, captured
    body = captured[0]
    overrides = body.get("spool_overrides")
    assert overrides is not None and len(overrides) == 2, body
    assert overrides[0]["initial_weight"] == 998
    assert overrides[0]["product_url"] == "https://prusament.com/spool/1/aaa/"
    # Spoolman text-type extras must arrive as JSON-quoted strings — the
    # value is wrapped in literal quote chars before sending so it survives
    # sanitize_outbound_data's json.loads round-trip without becoming an int.
    assert overrides[0]["extra"]["prusament_manufacturing_date"] == '"2026-03-12"'
    assert overrides[0]["extra"]["prusament_length_m"] == '"330"'
    assert overrides[1]["initial_weight"] == 1003
    assert overrides[1]["extra"]["prusament_manufacturing_date"] == '"2026-03-13"'
    # Manual mode → filament_data still in the payload (not filament_id).
    assert body.get("filament_data") is not None
    assert not body.get("filament_id")


def test_per_spool_scan_auto_switches_to_existing_filament(page: Page):
    """When /api/filaments contains a Prusament match for the scanned
    template, the wizard auto-switches into existing-filament mode and
    submits with filament_id (no filament_data)."""
    # One existing matching filament.
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": [
            {"id": 42, "name": "Galaxy Black", "material": "PLA",
             "color_name": "Galaxy Black", "vendor": {"name": "Prusament"}}
        ]}),
    ))
    _route_external_search(page, lambda q: _prusament_result())
    captured = _capture_create_wizard(page)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.locator("#btn-type-manual").click()

    rows = page.locator("[data-spool-row-idx]")
    rows.nth(0).locator("input[type='url']").fill("https://prusament.com/spool/1/aaa/")
    rows.nth(0).locator("input[type='url']").blur()
    expect(rows.nth(0).locator(".badge.bg-success")).to_be_visible(timeout=5000)

    # Status message should announce the auto-switch.
    expect(page.locator("#wiz-status-msg")).to_contain_text("Recognized existing", timeout=5000)

    # Wizard should be in `existing` mode now — selectedFilamentId set.
    selected_id = page.evaluate("() => wizardState.selectedFilamentId")
    assert str(selected_id) == "42"

    page.locator("#btn-wiz-submit").click()
    expect(page.locator("#wiz-status-msg")).to_contain_text("Success!", timeout=5000)

    assert len(captured) == 1
    body = captured[0]
    assert str(body.get("filament_id")) == "42"
    assert body.get("filament_data") is None
    overrides = body.get("spool_overrides")
    assert overrides is not None and len(overrides) == 1


def test_per_spool_scan_fuzzy_color_match_existing_filament(page: Page):
    """Real-world repro: a Prusament filament stored as `name="Silver (Pearl Mouse)"`
    with no `color_name` field must still match a scan whose `color_name=Pearl Mouse`.
    Without fuzzy matching, the wizard creates a duplicate filament instead
    of switching to the existing one (the bug the user hit on 2026-04-25)."""
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": [
            # Note: no color_name field. Just the parenthesized name.
            {"id": 157, "name": "Silver (Pearl Mouse)", "material": "PLA",
             "vendor": {"name": "Prusament"}}
        ]}),
    ))
    _route_external_search(page, lambda q: _prusament_result(color="Pearl Mouse"))
    captured = _capture_create_wizard(page)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.locator("#btn-type-manual").click()

    rows = page.locator("[data-spool-row-idx]")
    rows.nth(0).locator("input[type='url']").fill("https://prusament.com/spool/1/aaa/")
    rows.nth(0).locator("input[type='url']").blur()
    expect(rows.nth(0).locator(".badge.bg-success")).to_be_visible(timeout=5000)
    expect(page.locator("#wiz-status-msg")).to_contain_text("Recognized existing", timeout=5000)

    selected_id = page.evaluate("() => wizardState.selectedFilamentId")
    assert str(selected_id) == "157"

    page.locator("#btn-wiz-submit").click()
    expect(page.locator("#wiz-status-msg")).to_contain_text("Success!", timeout=5000)

    assert len(captured) == 1
    assert str(captured[0].get("filament_id")) == "157"
    assert captured[0].get("filament_data") is None


def test_per_spool_scan_prefers_oldest_when_multiple_match(page: Page):
    """If the user already has duplicate Prusament filaments from earlier
    broken runs, the matcher must auto-switch to the OLDEST (lowest id) —
    not surface a picker. The picker added complexity and the user kept
    accidentally creating yet another duplicate. Lowest id wins silently."""
    # Two filaments both fuzzy-match the scan. 157 is the canonical original;
    # 192 is the junk duplicate. Wizard must pick 157.
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": [
            {"id": 192, "name": "Pearl Mouse", "material": "PLA",
             "vendor": {"name": "Prusament"}},
            {"id": 157, "name": "Silver (Pearl Mouse)", "material": "PLA",
             "vendor": {"name": "Prusament"}},
        ]}),
    ))
    _route_external_search(page, lambda q: _prusament_result(color="Pearl Mouse"))
    captured = _capture_create_wizard(page)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.locator("#btn-type-manual").click()

    rows = page.locator("[data-spool-row-idx]")
    rows.nth(0).locator("input[type='url']").fill("https://prusament.com/spool/1/aaa/")
    rows.nth(0).locator("input[type='url']").blur()
    expect(rows.nth(0).locator(".badge.bg-success")).to_be_visible(timeout=5000)
    # Lowest id (157) wins — the duplicate (192) is ignored.
    expect(page.locator("#wiz-status-msg")).to_contain_text("Filament #157", timeout=5000)
    selected_id = page.evaluate("() => wizardState.selectedFilamentId")
    assert str(selected_id) == "157"

    page.locator("#btn-wiz-submit").click()
    expect(page.locator("#wiz-status-msg")).to_contain_text("Success!", timeout=5000)
    assert str(captured[0].get("filament_id")) == "157"


def test_post_success_lock_blocks_repeat_submit_until_edit(page: Page):
    """After a successful create, clicking Create again without editing must
    NOT fire a second POST. The user kept double-clicking and getting
    duplicate spools/filaments. Lock stays until any input/change event."""
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": []}),
    ))
    _route_external_search(page, lambda q: _prusament_result())
    captured = _capture_create_wizard(page)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.locator("#btn-type-manual").click()

    rows = page.locator("[data-spool-row-idx]")
    rows.nth(0).locator("input[type='url']").fill("https://prusament.com/spool/1/aaa/")
    rows.nth(0).locator("input[type='url']").blur()
    expect(rows.nth(0).locator(".badge.bg-success")).to_be_visible(timeout=5000)

    submit = page.locator("#btn-wiz-submit")
    submit.click()
    expect(page.locator("#wiz-status-msg")).to_contain_text("Success!", timeout=5000)
    assert len(captured) == 1

    # Wait for the post-success status flip + verify the button is locked.
    expect(submit).to_be_disabled()

    # Second click should do nothing — button is disabled, no new POST.
    submit.click(force=True)  # force past the disabled state to prove it doesn't fire
    page.wait_for_timeout(500)
    assert len(captured) == 1, f"Expected single POST, got {len(captured)}"

    # An input change re-arms the button.
    page.locator("#wiz-spool-qty").fill("3")
    page.locator("#wiz-spool-qty").dispatch_event("input")
    expect(submit).not_to_be_disabled(timeout=2000)


def test_per_spool_scan_failure_blocks_submit(page: Page):
    """A failed scan must mark the row red and block submit until the URL
    is cleared. Never silently fall back to defaults."""
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": []}),
    ))
    # Always-fail factory.
    _route_external_search(page, lambda q: None)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.locator("#btn-type-manual").click()

    # Fill bare-minimum filament fields so submit isn't otherwise blocked.
    page.locator("#wiz-fil-material").fill("PLA")
    page.locator("#wiz-fil-color_name").fill("Test")

    rows = page.locator("[data-spool-row-idx]")
    rows.nth(0).locator("input[type='url']").fill("https://prusament.com/spool/9/zzz/")
    rows.nth(0).locator("input[type='url']").blur()
    expect(rows.nth(0).locator(".badge.bg-danger")).to_be_visible(timeout=5000)
    expect(page.locator("#btn-wiz-submit")).to_be_disabled()

    # Clear the URL → row goes empty, submit re-enables.
    rows.nth(0).locator("input[type='url']").fill("")
    rows.nth(0).locator("input[type='url']").blur()
    expect(page.locator("#btn-wiz-submit")).not_to_be_disabled(timeout=3000)
