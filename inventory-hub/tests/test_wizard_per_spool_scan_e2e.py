"""E2E coverage for the per-spool Prusament scan flow added in Step 3 of
the Add-Inventory wizard. Exercises the route-mocked happy path, the
duplicate-filament auto-switch, and the parser-failure submit gate.

All tests intercept `/api/external/search` and `/api/create_inventory_wizard`
so no Spoolman state is mutated and no live Prusament HTTP is required."""

import json
import re

import pytest
from playwright.sync_api import Page, expect


# --- safety net: NEVER let a test PATCH a real Spoolman record -----------
# An earlier round of these tests mocked /api/filaments to return fake
# filaments with IDs 42, 157, 192 — but didn't mock /api/update_filament.
# When the auto-switch fired the silent backfill, the PATCH leaked through
# to the real Spoolman and overwrote real filament records with the test
# fixture's defaults (color_hex=FAFAFA, weight=998, "Galaxy Black", etc.).
# This autouse fixture makes that impossible: every test in this file gets
# /api/update_filament intercepted by default. Tests that want to inspect
# the captured PATCHes can re-route over it; the fulfillment shape stays
# consistent so they keep working.
@pytest.fixture(autouse=True)
def _block_real_update_filament(page):
    page.route("**/api/update_filament", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body='{"success": true, "filament": {}}',
    ))
    yield


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
        # Visually-obvious fake hex — if this ever leaks into a real
        # Spoolman record, it's instantly recognizable in the activity log.
        "color_hex": "FAFAFA",
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
    # product_url + purchase_url live in extras (no native product_url on
    # Spool). Sent UNWRAPPED — sanitize_outbound_data wraps both since
    # they're in JSON_STRING_FIELDS. Pre-wrapping would double-wrap.
    assert "product_url" not in overrides[0]
    assert overrides[0]["extra"]["product_url"] == 'https://prusament.com/spool/1/aaa/'
    assert overrides[0]["extra"]["purchase_url"] == 'https://prusament.com/spool/1/aaa/'
    # Date and length are NOT in JSON_STRING_FIELDS, so they DO need
    # literal-quote wrapping to survive the json.loads round-trip.
    assert overrides[0]["extra"]["prusament_manufacturing_date"] == '"2026-03-12"'
    assert overrides[0]["extra"]["prusament_length_m"] == '"330"'
    assert overrides[1]["initial_weight"] == 1003
    assert overrides[1]["extra"]["prusament_manufacturing_date"] == '"2026-03-13"'
    assert overrides[1]["extra"]["product_url"] == 'https://prusament.com/spool/2/bbb/'
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
            {"id": 99042, "name": "Galaxy Black", "material": "PLA",
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
    # The "Recognized existing" status text can be immediately overwritten
    # by the silent backfill's "Updated existing" banner — wait for the
    # selectedFilamentId state to flip instead of polling text.
    page.wait_for_function(
        "() => wizardState.selectedFilamentId !== null && wizardState.selectedFilamentId !== undefined",
        timeout=5000,
    )

    # Wizard should be in `existing` mode now — selectedFilamentId set.
    selected_id = page.evaluate("() => wizardState.selectedFilamentId")
    assert str(selected_id) == "99042"

    page.locator("#btn-wiz-submit").click()
    # Backfill banner can overwrite "Success!" mid-frame, so wait for the
    # post-success lock instead — that flag is only set after the create
    # POST returns success on the wizard's side.
    page.wait_for_function("() => wizardState.lockedAfterSuccess === true", timeout=5000)

    assert len(captured) == 1
    body = captured[0]
    assert str(body.get("filament_id")) == "99042"
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
            {"id": 99157, "name": "Silver (Pearl Mouse)", "material": "PLA",
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
    # The "Recognized existing" status text can be immediately overwritten
    # by the silent backfill's "Updated existing" banner — wait for the
    # selectedFilamentId state to flip instead of polling text.
    page.wait_for_function(
        "() => wizardState.selectedFilamentId !== null && wizardState.selectedFilamentId !== undefined",
        timeout=5000,
    )

    selected_id = page.evaluate("() => wizardState.selectedFilamentId")
    assert str(selected_id) == "99157"

    page.locator("#btn-wiz-submit").click()
    # Backfill banner can overwrite "Success!" mid-frame, so wait for the
    # post-success lock instead — that flag is only set after the create
    # POST returns success on the wizard's side.
    page.wait_for_function("() => wizardState.lockedAfterSuccess === true", timeout=5000)

    assert len(captured) == 1
    assert str(captured[0].get("filament_id")) == "99157"
    assert captured[0].get("filament_data") is None


def test_per_spool_scan_tier1_picks_tagged_over_lowest_id(page: Page):
    """Replaces the previous "lowest id wins silently" test. With the
    matcher's Tier-1 product-ID rule, when one of the candidates has its
    extra.product_url tagged with the same Prusament product (from a
    prior scan), THAT candidate wins — even when it's the higher id.
    Definitive match → silent auto-switch, no picker."""
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": [
            # Lower id, no product_url → previously would have won.
            {"id": 99192, "name": "Pearl Mouse", "material": "PLA",
             "vendor": {"name": "Prusament"}},
            # Higher id, tagged with /spool/1/ matching the scan → Tier-1 wins.
            {"id": 99257, "name": "Silver (Pearl Mouse)", "material": "PLA",
             "vendor": {"name": "Prusament"},
             "extra": {"product_url": '"https://prusament.com/spool/1/d1aa0032a0"'}},
        ]}),
    ))
    _route_external_search(page, lambda q: _prusament_result(
        color="Pearl Mouse", external_link="https://prusament.com/spool/1/aaa/"
    ))
    captured = _capture_create_wizard(page)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.locator("#btn-type-manual").click()

    rows = page.locator("[data-spool-row-idx]")
    rows.nth(0).locator("input[type='url']").fill("https://prusament.com/spool/1/aaa/")
    rows.nth(0).locator("input[type='url']").blur()
    expect(rows.nth(0).locator(".badge.bg-success")).to_be_visible(timeout=5000)

    # Tier-1 winner (99257) — silent auto-switch, picker never shown.
    page.wait_for_function(
        "() => String(wizardState.selectedFilamentId) === '99257'", timeout=5000
    )
    expect(page.locator("#wiz-duplicate-picker")).not_to_be_visible()

    page.locator("#btn-wiz-submit").click()
    page.wait_for_function("() => wizardState.lockedAfterSuccess === true", timeout=5000)
    assert str(captured[0].get("filament_id")) == "99257"


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


def test_per_spool_scan_splits_material_into_base_plus_attribute_chips(page: Page):
    """When the parser returns 'PC Blend Carbon Fiber' for a brand-new
    filament, Step 2's material field must show 'PC' and the
    filament_attributes chip container must hold 'Blend' + 'Carbon Fiber'.
    Without this split, Spoolman's flat material filter can't group all
    PC variants together — the whole reason the user introduced the
    base/attrs convention."""
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": []}),
    ))
    _route_external_search(page, lambda q: {
        "id": "fake",
        "name": "Prusament PC Blend Carbon Fiber Black",
        "material": "PC Blend Carbon Fiber",
        "vendor": {"name": "Prusament"},
        "weight": 800,
        "spool_weight": 215,
        "diameter": 1.75,
        "density": 1.18,
        "color_hex": "111111",
        "color_name": "Black",
        "external_link": "https://prusament.com/spool/9/zzz/",
        "extra": {},
    })
    captured = _capture_create_wizard(page)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.locator("#btn-type-manual").click()

    rows = page.locator("[data-spool-row-idx]")
    rows.nth(0).locator("input[type='url']").fill("https://prusament.com/spool/9/zzz/")
    rows.nth(0).locator("input[type='url']").blur()
    expect(rows.nth(0).locator(".badge.bg-success")).to_be_visible(timeout=5000)

    # Step 2's native material field must hold the BASE only.
    expect(page.locator("#wiz-fil-material")).to_have_value("PC")

    # Both attributes must be rendered as chips with data-selected="true"
    # so the existing wizardSubmit collector at line ~1610 picks them up.
    chip_values = page.locator(
        '#chip-container-fil-filament_attributes .dynamic-chip[data-selected="true"]'
    ).evaluate_all("els => els.map(e => e.getAttribute('data-value')).sort()")
    assert chip_values == ["Blend", "Carbon Fiber"]

    page.locator("#btn-wiz-submit").click()
    expect(page.locator("#wiz-status-msg")).to_contain_text("Success!", timeout=5000)
    fil_data = captured[0].get("filament_data") or {}
    assert fil_data.get("material") == "PC"
    # Attributes flow into the filament's extras as a list (the wizard's
    # existing chip collector at inv_wizard.js:1610).
    assert sorted(fil_data.get("extra", {}).get("filament_attributes", [])) == ["Blend", "Carbon Fiber"]


def _route_update_filament(page):
    """Capture every PATCH the backfill flow sends, return the success
    response Spoolman would normally return so the wizard can continue."""
    captured: list[dict] = []

    def _handler(route, request):
        try:
            body = request.post_data_json or {}
        except Exception:
            body = {}
        captured.append(body)
        # Echo the data back as the "filament" so the cache-refresh path
        # has something to merge.
        merged = {'id': body.get('id'), **(body.get('data') or {})}
        route.fulfill(
            status=200, content_type='application/json',
            body=json.dumps({'success': True, 'filament': merged}),
        )
    page.route('**/api/update_filament', _handler)
    return captured


def test_backfill_silent_patch_fires_on_autoswitch(page: Page):
    """Real-world filament 122 case: stored as material='PC' with missing
    temps, missing bed_temp_max/nozzle_temp_max, attrs=['Carbon Fiber'].
    Scan returns 'PC Blend Carbon Fiber' with full temps. Auto-switch
    must fire AND a single PATCH must carry the silent backfill diff."""
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": [
            {
                "id": 99122, "name": "Black (Carbon Fiber)", "material": "PC",
                "color_hex": "2B2B2B", "density": 1.20, "diameter": None,
                "weight": 0, "spool_weight": 0,
                "settings_extruder_temp": None, "settings_bed_temp": None,
                "vendor": {"name": "Prusament"},
                "extra": {"filament_attributes": ["Carbon Fiber"]},
            }
        ]}),
    ))
    _route_external_search(page, lambda q: {
        "id": "fake", "name": "Prusament PC Blend Carbon Fiber Black",
        "material": "PC Blend Carbon Fiber",
        "vendor": {"name": "Prusament"}, "weight": 800, "spool_weight": 215,
        "diameter": 1.75, "density": 1.18,
        "color_hex": "2B2B2B", "color_name": "Black",
        "external_link": "https://prusament.com/spool/9/zzz/",
        "settings_extruder_temp": 215, "settings_bed_temp": 60,
        "extra": {"nozzle_temp_max": '"225"', "bed_temp_max": '"60"'},
    })
    patches = _route_update_filament(page)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.locator("#btn-type-manual").click()

    rows = page.locator("[data-spool-row-idx]")
    rows.nth(0).locator("input[type='url']").fill("https://prusament.com/spool/9/zzz/")
    rows.nth(0).locator("input[type='url']").blur()
    expect(rows.nth(0).locator(".badge.bg-success")).to_be_visible(timeout=5000)

    # Auto-switch fired — selected fake fixture id 99122 (NOT a real
    # Spoolman id; the autouse _block_real_update_filament fixture also
    # intercepts the PATCH so it can never leak even by accident).
    selected_id = page.evaluate("() => wizardState.selectedFilamentId")
    assert str(selected_id) == "99122"

    # Status banner should have flipped from "Recognized existing" to the
    # backfill confirmation. Either is acceptable; we only need to confirm
    # the PATCH was sent.
    assert len(patches) == 1, f"expected 1 backfill PATCH, got {len(patches)}: {patches}"
    body = patches[0]
    assert str(body.get("id")) == "99122"
    data = body.get("data") or {}
    # Silent fills the parser had and the existing record was missing.
    assert data.get("spool_weight") == 215
    assert data.get("settings_extruder_temp") == 215
    assert data.get("settings_bed_temp") == 60
    extra = data.get("extra") or {}
    assert extra.get("nozzle_temp_max") == '"225"'
    assert extra.get("bed_temp_max") == '"60"'
    # filament_attributes set-union: existing kept, parser-implied added.
    assert sorted(extra.get("filament_attributes", [])) == ["Blend", "Carbon Fiber"]
    # original_color flows in from the parser's color_name. Sent raw —
    # sanitize_outbound_data wraps it because the field is in JSON_STRING_FIELDS.
    assert extra.get("original_color") == 'Black'

    # weight, spool_weight, diameter, density all transitioned from
    # null/0 to silent fills. Existing density=1.20 vs parser=1.18 is
    # under the 0.05 threshold so no mismatch row. Same with color_hex
    # (equal in this fixture). Panel should be hidden.
    assert data.get("diameter") == 1.75
    assert data.get("weight") == 800
    panel = page.locator("#wiz-fil-mismatch-panel")
    expect(panel).not_to_be_visible(timeout=2000)


def test_backfill_mismatch_panel_renders_and_opt_in_patches(page: Page):
    """When the existing record has values that DIFFER from the parser
    (not just empty), the mismatch panel renders and each [Use Scanned]
    button fires a one-key PATCH for that field only."""
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": [
            {
                "id": 99122, "name": "Black (Carbon Fiber)", "material": "PC",
                "color_hex": "2B2B2B", "density": 1.20, "diameter": 1.75,
                "weight": 865, "spool_weight": 215,
                "settings_extruder_temp": 240, "settings_bed_temp": 90,
                "vendor": {"name": "Prusament"},
                "extra": {"filament_attributes": ["Carbon Fiber", "Blend"],
                          "nozzle_temp_max": '"260"', "bed_temp_max": '"100"',
                          "original_color": '"Black"'},
            }
        ]}),
    ))
    _route_external_search(page, lambda q: {
        "id": "fake", "name": "Prusament PC Blend Carbon Fiber Black",
        "material": "PC Blend Carbon Fiber",
        "vendor": {"name": "Prusament"}, "weight": 800, "spool_weight": 215,
        "diameter": 1.75, "density": 1.18,
        "color_hex": "868463", "color_name": "Black",
        "external_link": "https://prusament.com/spool/9/zzz/",
        "settings_extruder_temp": 215, "settings_bed_temp": 60,
        "extra": {"nozzle_temp_max": '"225"', "bed_temp_max": '"60"'},
    })
    patches = _route_update_filament(page)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.locator("#btn-type-manual").click()

    rows = page.locator("[data-spool-row-idx]")
    rows.nth(0).locator("input[type='url']").fill("https://prusament.com/spool/9/zzz/")
    rows.nth(0).locator("input[type='url']").blur()
    expect(rows.nth(0).locator(".badge.bg-success")).to_be_visible(timeout=5000)

    panel = page.locator("#wiz-fil-mismatch-panel")
    expect(panel).to_be_visible(timeout=5000)
    # Expected mismatches: weight, color_hex, settings_extruder_temp,
    # settings_bed_temp, nozzle_temp_max, bed_temp_max. (density gap is
    # under threshold; diameter equals; spool_weight equals.)
    rows_in_panel = page.locator("#wiz-fil-mismatch-rows tr[data-mismatch-row]")
    keys = rows_in_panel.evaluate_all("els => els.map(e => e.getAttribute('data-mismatch-key'))")
    assert "weight" in keys
    assert "color_hex" in keys
    assert "settings_extruder_temp" in keys
    assert "extra.nozzle_temp_max" in keys

    # No silent backfill should have happened (everything was set already
    # and either equal or in mismatch panel). So patches list is empty
    # so far. (filament_attributes set-union didn't fire because parser
    # implied no NEW attrs beyond what was already there.)
    assert patches == []

    # Click [Use Scanned] on the weight row.
    weight_row = page.locator('#wiz-fil-mismatch-rows tr[data-mismatch-key="weight"]')
    weight_row.locator("button").click()
    page.wait_for_timeout(300)
    assert len(patches) == 1, patches
    assert patches[0]["data"] == {"weight": 800}
    # Row should have collapsed to a confirmation message.
    expect(weight_row).to_contain_text("Updated", timeout=2000)


def test_backfill_dismiss_closes_panel_without_writes(page: Page):
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": [
            {"id": 99122, "name": "Black", "material": "PC",
             "color_hex": "111111", "weight": 865, "spool_weight": 215,
             "diameter": 1.75, "density": 1.20,
             "settings_extruder_temp": 215, "settings_bed_temp": 60,
             "vendor": {"name": "Prusament"},
             "extra": {"filament_attributes": ["Carbon Fiber", "Blend"],
                       "nozzle_temp_max": '"225"', "bed_temp_max": '"60"',
                       "original_color": '"Black"'}}
        ]}),
    ))
    _route_external_search(page, lambda q: {
        "id": "fake", "name": "x", "material": "PC Blend Carbon Fiber",
        "vendor": {"name": "Prusament"}, "weight": 800, "spool_weight": 215,
        "diameter": 1.75, "density": 1.18, "color_hex": "222222",
        "color_name": "Black", "external_link": "https://prusament.com/spool/9/zzz/",
        "extra": {"nozzle_temp_max": '"225"', "bed_temp_max": '"60"'},
    })
    patches = _route_update_filament(page)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    page.locator("#btn-type-manual").click()
    rows = page.locator("[data-spool-row-idx]")
    rows.nth(0).locator("input[type='url']").fill("https://prusament.com/spool/9/zzz/")
    rows.nth(0).locator("input[type='url']").blur()

    panel = page.locator("#wiz-fil-mismatch-panel")
    expect(panel).to_be_visible(timeout=5000)
    panel.get_by_role("button", name="Dismiss").click()
    expect(panel).not_to_be_visible(timeout=2000)
    # Nothing patched (no silent fields, no opt-ins).
    assert patches == []


def test_import_from_external_panel_runs_matcher_and_autoswitches(page: Page):
    """Real-world bug the user hit: clicking 'Import from External Database'
    in Step 1 (which sets wizardState.mode='external') and selecting a
    pre-searched filament used to skip the duplicate-detect matcher
    entirely — the gate only fired in 'manual' mode. Result: a duplicate
    filament got crammed in even though a perfect match existed. Gate
    must accept both 'manual' AND 'external' modes."""
    # One existing Pearl Mouse filament that should match the scan.
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": [
            {"id": 99157, "name": "Silver (Pearl Mouse)", "color_name": None,
             "material": "PLA", "vendor": {"name": "Prusament"},
             "color_hex": "868463", "weight": 1000, "spool_weight": 215,
             "diameter": 1.75, "density": 1.18,
             "settings_extruder_temp": 215, "settings_bed_temp": 60,
             "extra": {"original_color": '"Pearl Mouse"',
                       "filament_attributes": '["Carbon Fiber", "Blend"]'}}
        ]}),
    ))
    # External search returns the canonical Prusament template — same as
    # a per-spool scan would.
    page.route(
        "**/api/external/search**",
        lambda route, req: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"success": True, "results": [
                _prusament_result(color="Pearl Mouse")
            ]}),
        ),
    )
    captured = _capture_create_wizard(page)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    expect(page.locator("#wizardModal")).to_be_visible()

    # Switch to "Import from External Database" mode (sets mode='external').
    page.locator("#btn-type-external").click()

    # Drive the search panel — paste a Prusament URL into the search box,
    # set source to prusament, click Search → results dropdown populates.
    page.evaluate("""() => {
        document.getElementById('wiz-external-source').value = 'prusament';
        document.getElementById('wiz-search-external').value = 'https://prusament.com/spool/1/aaa/';
        window.wizardSearchExternal();
    }""")
    # Wait for the results dropdown to populate, then pick the first result.
    page.wait_for_function(
        "() => document.getElementById('wiz-external-results').options.length > 0 "
        "&& document.getElementById('wiz-external-results').options[0].value !== ''",
        timeout=5000,
    )
    page.evaluate("""() => {
        const sel = document.getElementById('wiz-external-results');
        sel.selectedIndex = 0;
        window.wizardExternalSelected();
    }""")

    # The matcher MUST have fired and auto-switched into existing mode.
    page.wait_for_function(
        "() => String(wizardState.selectedFilamentId) === '99157'", timeout=5000
    )
    assert str(page.evaluate("() => wizardState.selectedFilamentId")) == "99157"

    page.locator("#btn-wiz-submit").click()
    page.wait_for_function("() => wizardState.lockedAfterSuccess === true", timeout=5000)

    assert len(captured) == 1
    body = captured[0]
    # CRITICAL: filament_id is 99157 (the existing match), NOT a fresh
    # filament_data payload. Without the fix, this would be filament_data.
    assert str(body.get("filament_id")) == "99157"
    assert body.get("filament_data") is None


def test_picker_fires_when_matcher_cant_disambiguate(page: Page):
    """User explicitly asked: when the matcher can't disambiguate after
    all tiers, fall back to letting the user decide. This pins the picker
    behavior — two basic-gate matches with no tagged product_url for
    Tier-1 disambiguation should surface the duplicate picker, not
    silently pick lowest-id."""
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": [
            # Material must match _prusament_result()'s "PLA" default for
            # the basic-gate matcher to pass — otherwise the matcher
            # returns zero candidates and the picker never fires.
            {"id": 99121, "name": "Black (Jet Black)", "color_name": None,
             "material": "PLA", "vendor": {"name": "Prusament"}},
            {"id": 99122, "name": "Black (Carbon Fiber)", "color_name": None,
             "material": "PLA", "vendor": {"name": "Prusament"}},
        ]}),
    ))
    _route_external_search(page, lambda q: _prusament_result(color="Black"))
    captured = _capture_create_wizard(page)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.locator("#btn-type-manual").click()

    rows = page.locator("[data-spool-row-idx]")
    rows.nth(0).locator("input[type='url']").fill("https://prusament.com/spool/9/zzz/")
    rows.nth(0).locator("input[type='url']").blur()
    expect(rows.nth(0).locator(".badge.bg-success")).to_be_visible(timeout=5000)

    # Picker MUST be visible — no Tier-1 winner, multiple basic-gate matches.
    picker = page.locator("#wiz-duplicate-picker")
    expect(picker).to_be_visible(timeout=5000)
    expect(picker).to_contain_text("Multiple existing filaments match")

    # Both candidates listed; user can pick either, or "Create new filament".
    select_opts = page.locator("#wiz-duplicate-picker-sel option").evaluate_all(
        "els => els.map(e => e.value)"
    )
    assert sorted(select_opts) == ["99121", "99122"]
    expect(picker.get_by_role("button", name=re.compile("Use selected"))).to_be_visible()
    expect(picker.get_by_role("button", name=re.compile("Create new filament"))).to_be_visible()

    # Pick 99122 (the canonical-by-the-user's-intent match).
    page.evaluate("""() => {
        document.getElementById('wiz-duplicate-picker-sel').value = '99122';
        window.wizardDuplicatePickerConfirm();
    }""")
    expect(picker).not_to_be_visible(timeout=2000)

    # Wizard should have auto-switched to 99122.
    page.wait_for_function(
        "() => String(wizardState.selectedFilamentId) === '99122'", timeout=5000
    )

    page.locator("#btn-wiz-submit").click()
    page.wait_for_function("() => wizardState.lockedAfterSuccess === true", timeout=5000)
    assert str(captured[0].get("filament_id")) == "99122"


def test_picker_create_new_falls_through_to_fresh_filament(page: Page):
    """The "Create new filament" button must fully escape the matcher —
    fill Step 2 from the parser template and let the wizard create a
    fresh filament record at submit time. Rare but real case: user has
    fuzzy duplicates and intentionally wants a third record."""
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "filaments": [
            # Material must match _prusament_result()'s "PLA" default for
            # the basic-gate matcher to fire (otherwise picker never shows).
            {"id": 99121, "name": "Black (Jet Black)", "material": "PLA",
             "vendor": {"name": "Prusament"}},
            {"id": 99122, "name": "Black (Carbon Fiber)", "material": "PLA",
             "vendor": {"name": "Prusament"}},
        ]}),
    ))
    _route_external_search(page, lambda q: _prusament_result(color="Black"))
    captured = _capture_create_wizard(page)

    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    page.locator("#btn-type-manual").click()

    rows = page.locator("[data-spool-row-idx]")
    rows.nth(0).locator("input[type='url']").fill("https://prusament.com/spool/9/zzz/")
    rows.nth(0).locator("input[type='url']").blur()
    expect(page.locator("#wiz-duplicate-picker")).to_be_visible(timeout=5000)

    page.evaluate("() => window.wizardDuplicatePickerDismiss()")
    expect(page.locator("#wiz-duplicate-picker")).not_to_be_visible(timeout=2000)

    # Step 2 should now be filled from the parser template — wizard back
    # in normal create-new mode. Parser returns material="PLA".
    expect(page.locator("#wiz-fil-material")).to_have_value("PLA")
    selected = page.evaluate("() => wizardState.selectedFilamentId")
    assert not selected, "Create new must NOT bind to either existing match"

    page.locator("#btn-wiz-submit").click()
    page.wait_for_function("() => wizardState.lockedAfterSuccess === true", timeout=5000)
    body = captured[0]
    assert body.get("filament_id") is None, "Create new must not bind filament_id"
    assert body.get("filament_data") is not None, "Create new must send filament_data"


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
