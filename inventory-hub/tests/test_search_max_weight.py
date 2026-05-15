"""L209 — search by remaining weight: max_weight filter (the symmetric
complement to the existing min_weight). Verifies both backend filter and
the frontend offcanvas input is wired up.
"""
from __future__ import annotations

import json

import pytest
import requests
from playwright.sync_api import Page, expect


@pytest.mark.usefixtures("require_server")
def test_search_api_max_weight_filters_results(api_base_url: str):
    """Backend: pass max_weight=500 + min_weight=100, every returned
    remaining_weight should fall inside the closed interval."""
    r = requests.get(
        f"{api_base_url}/api/search",
        params={"type": "spool", "min_weight": 100, "max_weight": 500, "in_stock": "true"},
        timeout=15,
    )
    assert r.ok, r.text
    body = r.json()
    assert body.get("success") is True
    results = body.get("results", [])
    if not results:
        pytest.skip("dev inventory empty for the 100–500g band; nothing to assert")
    for spool in results:
        w = (spool.get("details") or {}).get("weight")
        assert w is not None, f"spool {spool.get('id')} missing weight in details"
        assert 100 <= w <= 500, f"spool {spool.get('id')} weight {w}g outside 100–500"


@pytest.mark.usefixtures("require_server")
def test_search_api_max_weight_alone_is_an_upper_bound(api_base_url: str):
    """Backend: max_weight without min_weight still caps the upper edge."""
    r = requests.get(
        f"{api_base_url}/api/search",
        params={"type": "spool", "max_weight": 250, "in_stock": "true"},
        timeout=15,
    )
    assert r.ok
    body = r.json()
    results = body.get("results", [])
    for spool in results:
        w = (spool.get("details") or {}).get("weight")
        if w is None:
            continue
        assert w <= 250, f"spool {spool.get('id')} weight {w}g exceeds max_weight=250"


@pytest.mark.usefixtures("require_server")
def test_offcanvas_max_weight_input_present_and_wired(page: Page, base_url: str):
    """Frontend: the offcanvas search panel exposes a Max-g input next to
    Min-g, and typing into it re-triggers the search."""
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    # Open the offcanvas search.
    page.evaluate(
        """() => {
            if (window.SearchEngine && typeof window.SearchEngine.open === 'function') {
                window.SearchEngine.open();
            } else {
                const t = document.querySelector('[data-bs-target="#offcanvasSearch"]');
                if (t) t.click();
            }
        }"""
    )

    max_input = page.locator("#global-search-max-weight")
    expect(max_input).to_be_visible(timeout=5000)
    # Sanity: the placeholder advertises Max g.
    assert "Max" in (max_input.get_attribute("placeholder") or "")

    # Capture the search call to confirm max_weight is wired into the URL.
    captured = {}
    def handle(route):
        req = route.request
        if req.method == 'GET' and '/api/search' in req.url:
            from urllib.parse import urlparse, parse_qs
            captured['qs'] = parse_qs(urlparse(req.url).query)
            route.fulfill(
                status=200, content_type='application/json',
                body=json.dumps({"success": True, "results": []}),
            )
        else:
            route.continue_()
    page.route("**/api/search**", handle)

    max_input.fill("250")
    # Debounced ~300ms — give it a moment.
    page.wait_for_function(
        "() => window.__searchProbeRan === true || true",
        timeout=1000,
    )
    page.wait_for_timeout(600)

    assert captured.get('qs'), "search endpoint was not hit after typing in max_weight"
    assert captured['qs'].get('max_weight') == ['250'], (
        f"max_weight should be propagated to /api/search; got query string: {captured['qs']}"
    )
