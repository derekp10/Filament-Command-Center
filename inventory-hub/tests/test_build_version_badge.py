"""L42 regression — the build-version badge auto-derives from source mtime
+ git commit info and renders in the user's local timezone (not the
container's UTC).

History:
- Original badge: hardcoded `VERSION = "v154.26 (...)"` that drifted.
- Round 1: derive from source-file mtime, format locally on the frontend.
- Round 2: also load commit SHA + timestamp via `_gen_build_info` (no
  git binary required); fall back to mtime when .git isn't reachable.

This test accepts EITHER format (`build YYYY-MM-DD HH:MM` or
`commit <sha> • YYYY-MM-DD HH:MM`) so it passes regardless of whether
.git was reachable when the server started.
"""
from __future__ import annotations

import pytest
import re
import requests
from playwright.sync_api import Page, expect


_BADGE_PATTERN = re.compile(
    r"^(build \d{4}-\d{2}-\d{2} \d{2}:\d{2}|commit [0-9a-f]{7,}( • \d{4}-\d{2}-\d{2} \d{2}:\d{2})?)$"
)


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

    badge.wait_for(state="visible")

    # Give the DOMContentLoaded handler a beat to run, then check the
    # rendered text matches one of the two accepted local-time formats.
    page.wait_for_function(
        "() => /^(build \\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}|commit [0-9a-f]{7,}( • \\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2})?)$/.test(document.getElementById('fcc-build-version').textContent.trim())",
        timeout=3000,
    )

    text = badge.inner_text().strip()
    assert _BADGE_PATTERN.match(text), f"badge text not in expected format: {text!r}"


@pytest.mark.usefixtures("require_server")
def test_build_version_no_longer_pinned_to_v154(base_url: str):
    """Hardcoded `v154.x` string should be gone — formats are
    `build ...` (mtime fallback) or `commit ...` (with git resolution)."""
    body = requests.get(base_url + "/", timeout=10).text
    assert "v154." not in body, "legacy hardcoded VERSION string still present"
    assert ("build " in body) or ("commit " in body), (
        "Neither build-mtime nor commit-SHA format present in dashboard HTML"
    )


@pytest.mark.usefixtures("require_server")
def test_build_version_commit_data_attrs_present_when_git_reachable(page: Page, base_url: str):
    """When .git is reachable from the running server, the badge carries
    data-build-commit-sha + data-build-commit-ts and the rendered label
    leads with `commit `. If .git is NOT reachable (e.g. prod container
    without the .build_info file pre-baked), the data attrs are empty
    and the badge falls back to mtime — that's a valid pass too."""
    page.goto(base_url)
    badge = page.locator("#fcc-build-version")
    sha = badge.get_attribute("data-build-commit-sha") or ""
    if not sha:
        pytest.skip("Server couldn't resolve .git — mtime fallback in use; skipping commit-attr assertion.")
    # Some git output formats can fall through to a short hash that's
    # 7-12 chars of hex; our helper trims to 8 but allow ≥7 to be safe.
    assert re.match(r"^[0-9a-f]{7,12}$", sha), f"sha looks malformed: {sha!r}"
    page.wait_for_function(
        "() => /^commit [0-9a-f]{7,}/.test(document.getElementById('fcc-build-version').textContent.trim())",
        timeout=3000,
    )
