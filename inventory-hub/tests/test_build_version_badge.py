"""L42 regression — the build-version badge auto-derives from source mtime
and renders in the user's local timezone (not the container's UTC).

The badge used to be hardcoded `VERSION = "v154.26 (...)"` in app.py and went
stale by ~25 commits before anyone noticed. The fix walks `app.py`/`static/`/
`templates/` for the newest mtime and emits a UNIX timestamp the frontend
formats locally.
"""
from __future__ import annotations

import pytest
import re
import requests
from playwright.sync_api import Page, expect


@pytest.mark.usefixtures("require_server")
def test_build_version_badge_is_present_and_local(page: Page, base_url: str):
    page.goto(base_url)
    badge = page.locator("#fcc-build-version")
    expect(badge).to_be_visible()

    # data-build-mtime is a positive unix timestamp written by the backend.
    mtime_attr = badge.get_attribute("data-build-mtime")
    assert mtime_attr, "data-build-mtime missing"
    mtime = float(mtime_attr)
    assert mtime > 1_700_000_000, f"build mtime looks bogus: {mtime}"

    # After DOMContentLoaded the JS hook should have replaced the UTC server
    # render with a local-time string. Match the local format the JS emits.
    local_pattern = re.compile(r"^build \d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
    badge.wait_for(state="visible")

    # Give the DOMContentLoaded handler a beat to run.
    page.wait_for_function(
        "() => /^build \\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}$/.test(document.getElementById('fcc-build-version').textContent.trim())",
        timeout=3000,
    )

    text = badge.inner_text().strip()
    assert local_pattern.match(text), f"badge text not in local format: {text!r}"


@pytest.mark.usefixtures("require_server")
def test_build_version_no_longer_pinned_to_v154(base_url: str):
    """Hardcoded `v154.x` string should be gone — the new format is `build ...`."""
    body = requests.get(base_url + "/", timeout=10).text
    assert "v154." not in body, "legacy hardcoded VERSION string still present"
    # The server-rendered badge prints the UTC timestamp before JS runs.
    assert "build " in body
