"""
Shared pytest fixtures for the Filament Command Center test suite.

Usage:
- `page` (from pytest-playwright) is enhanced with a 1600x1300 viewport.
- `api_base_url` / `page_base_url` resolve from INVENTORY_HUB_URL env
  (default: http://localhost:8000) so tests can run against any environment.
- `clean_buffer`, `with_held_spool`, `seed_dryer_box`, `snapshot`, `scan`
  cover the common setup/teardown patterns used across the E2E suite.

Fixtures keep existing tests working unchanged — they only take effect when
imported or requested explicitly.
"""
from __future__ import annotations

import os
import sys
import typing

import pytest
import requests

# Make the inventory-hub app modules importable from tests.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


DEFAULT_BASE_URL = os.environ.get("INVENTORY_HUB_URL", "http://localhost:8000")
BASELINE_VIEWPORT = {"width": 1600, "height": 1300}


# ---------------------------------------------------------------------------
# Base URL / context overrides
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def base_url() -> str:
    return DEFAULT_BASE_URL


@pytest.fixture(scope="session")
def api_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


@pytest.fixture
def browser_context_args(browser_context_args):
    """Override pytest-playwright's default context args to use our baseline viewport."""
    return {
        **browser_context_args,
        "viewport": BASELINE_VIEWPORT,
    }


# ---------------------------------------------------------------------------
# Buffer helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_buffer(api_base_url: str):
    """Ensure the buffer is empty before the test. Yields the base URL."""
    try:
        requests.post(f"{api_base_url}/api/buffer/clear", timeout=5)
    except requests.RequestException:
        pass
    yield api_base_url


@pytest.fixture
def with_held_spool(api_base_url: str, clean_buffer):
    """Factory: push a spool into the buffer and return its id."""
    def _push(spool_id: int) -> int:
        r = requests.post(
            f"{api_base_url}/api/identify_scan",
            json={"text": f"ID:{spool_id}", "source": "test"},
            timeout=5,
        )
        r.raise_for_status()
        return spool_id

    return _push


# ---------------------------------------------------------------------------
# Dryer box seeders (API + UI flavors)
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_dryer_box(api_base_url: str):
    """API-path seeder: PUT bindings onto a Dryer Box via the new API.

    Signature: seed_dryer_box(box_id, slot_targets={'1': 'XL-1', '2': None, ...})

    Gracefully skips when the bindings endpoint isn't deployed yet (Phase 2
    hasn't shipped) — lets M0 baseline tests run without the new API.
    """
    def _seed(box_id: str, slot_targets: typing.Optional[dict] = None) -> dict:
        if slot_targets is None:
            slot_targets = {}
        try:
            r = requests.put(
                f"{api_base_url}/api/dryer_box/{box_id}/bindings",
                json={"slot_targets": slot_targets},
                timeout=5,
            )
        except requests.RequestException as exc:
            pytest.skip(f"Bindings endpoint unreachable: {exc}")
        if r.status_code == 404:
            pytest.skip("Bindings endpoint not deployed yet (expected before M3)")
        r.raise_for_status()
        return r.json()

    return _seed


@pytest.fixture
def seed_via_ui(api_base_url: str):
    """UI-path seeder: click through Location Manager to set per-slot bindings.

    Exists so every API-seeded test has a UI-path twin. Returns a callable that
    receives a Playwright Page plus the same args as `seed_dryer_box`.

    Phase 2 UI ships with M4 — until then this fixture skips.
    """
    def _seed(page, box_id: str, slot_targets: typing.Optional[dict] = None) -> None:
        pytest.skip("UI bindings path ships with M4; use seed_dryer_box until then.")

    return _seed


# ---------------------------------------------------------------------------
# Snapshot / scan helpers
# ---------------------------------------------------------------------------

BASELINE_DIR = os.path.join(os.path.dirname(__file__), "__screenshots__", "chromium-1600x1300")
_UPDATE_BASELINES = os.environ.get("UPDATE_VISUAL_BASELINES", "").lower() in ("1", "true", "yes")


@pytest.fixture
def snapshot(pytestconfig, request):
    """Visual regression snapshot helper.

    Usage:
        def test_something(page, snapshot):
            page.goto("/")
            snapshot(page, "dashboard-default")

    Behavior:
    - If the baseline file does not exist, it is created from the current
      screenshot and the test passes (with a captured note on `request.node`).
    - If the baseline exists, the current screenshot is diffed against it.
      Mismatches raise AssertionError with a diff image written next to the
      baseline as `<name>.actual.png` and `<name>.diff.png`.
    - Set env UPDATE_VISUAL_BASELINES=1 to force re-capture (overwrite).

    Tolerance defaults to 1% of pixels allowed to differ. The per-pixel
    threshold accepts tiny RGB drift (sub-pixel AA, hint diffs) without
    marking them as a mismatch.
    """
    from playwright.sync_api import Page, Locator

    def _save(screenshot_bytes: bytes, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(screenshot_bytes)

    def _compare(baseline_path: str, actual_bytes: bytes, *, max_diff_pixel_ratio: float) -> typing.Optional[str]:
        """Return None if images match, else a human-readable diff summary."""
        from PIL import Image, ImageChops
        import io

        baseline_img = Image.open(baseline_path).convert("RGBA")
        actual_img = Image.open(io.BytesIO(actual_bytes)).convert("RGBA")

        if baseline_img.size != actual_img.size:
            return (
                f"size mismatch: baseline={baseline_img.size} actual={actual_img.size}"
            )

        diff = ImageChops.difference(baseline_img, actual_img)
        bbox = diff.getbbox()
        if bbox is None:
            return None

        # Count pixels that differ beyond a small per-channel threshold to
        # tolerate font/hinting noise.
        threshold = 15  # per-channel RGB delta
        diff_pixels = 0
        total_pixels = baseline_img.size[0] * baseline_img.size[1]
        for px in diff.getdata():
            if max(px[:3]) > threshold:
                diff_pixels += 1
        ratio = diff_pixels / total_pixels
        if ratio <= max_diff_pixel_ratio:
            return None

        # Write diff artifacts for debugging.
        actual_path = baseline_path.replace(".png", ".actual.png")
        diff_path = baseline_path.replace(".png", ".diff.png")
        actual_img.save(actual_path)
        # Amplify diff so it's visible.
        amplified = diff.point(lambda p: min(255, p * 10))
        amplified.save(diff_path)
        return (
            f"{diff_pixels}/{total_pixels} pixels differ "
            f"(ratio={ratio:.4f}, max allowed={max_diff_pixel_ratio}). "
            f"See {actual_path} and {diff_path}"
        )

    def _capture_locator(locator) -> bytes:
        """Screenshot a locator, expanding the viewport first if the
        element is taller/wider than the current window so content
        that would normally require scrolling inside the modal actually
        lands in the image.
        """
        page = locator.page
        # Measure the full scrollable dimensions of the locator (not just
        # the visible portion).
        size = locator.evaluate(
            "el => ({w: Math.max(el.scrollWidth, el.getBoundingClientRect().width),"
            "       h: Math.max(el.scrollHeight, el.getBoundingClientRect().height)})"
        )
        w, h = int(size.get("w", 0)) or BASELINE_VIEWPORT["width"], \
               int(size.get("h", 0)) or BASELINE_VIEWPORT["height"]
        # Pad a little so borders/shadows survive the crop.
        desired = {"width": max(w + 40, BASELINE_VIEWPORT["width"]),
                   "height": max(h + 80, BASELINE_VIEWPORT["height"])}
        try:
            page.set_viewport_size(desired)
            # Scroll the element into view so fixed-position overlays render
            # with their full body visible.
            locator.scroll_into_view_if_needed()
            return locator.screenshot()
        finally:
            page.set_viewport_size(BASELINE_VIEWPORT)

    def _capture_page(page) -> bytes:
        """Full-page screenshot with the viewport expanded to the document
        height so Bootstrap fixed-position elements (navbar, modals) and
        tall scrollable content both end up captured.
        """
        doc_h = page.evaluate(
            "() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)"
        )
        desired = {"width": BASELINE_VIEWPORT["width"],
                   "height": max(int(doc_h or 0), BASELINE_VIEWPORT["height"])}
        try:
            page.set_viewport_size(desired)
            return page.screenshot(full_page=True)
        finally:
            page.set_viewport_size(BASELINE_VIEWPORT)

    def _snap(page_or_locator, name: str, *, max_diff_pixel_ratio: float = 0.01, full_page: bool = True, **kwargs) -> None:
        filename = name if name.endswith(".png") else f"{name}.png"
        baseline_path = os.path.join(BASELINE_DIR, filename)

        # Capture current screenshot as bytes (don't write yet).
        if isinstance(page_or_locator, Locator):
            try:
                actual = _capture_locator(page_or_locator)
            except Exception:
                # Fallback: plain locator screenshot if viewport resize
                # isn't supported (e.g. headless context quirk).
                actual = page_or_locator.screenshot(**kwargs)
        else:
            try:
                actual = _capture_page(page_or_locator)
            except Exception:
                actual = page_or_locator.screenshot(full_page=full_page, **kwargs)

        baseline_exists = os.path.isfile(baseline_path)
        if _UPDATE_BASELINES or not baseline_exists:
            _save(actual, baseline_path)
            # Tag for reporter; not a failure.
            if not hasattr(request.node, "_visual_baselines_created"):
                request.node._visual_baselines_created = []
            request.node._visual_baselines_created.append(filename)
            return

        diff_msg = _compare(baseline_path, actual, max_diff_pixel_ratio=max_diff_pixel_ratio)
        if diff_msg is not None:
            raise AssertionError(f"Visual regression for {filename}: {diff_msg}")

    return _snap


@pytest.fixture
def scan(api_base_url: str):
    """Synthetic scan helper — posts directly to /api/identify_scan.

    This is the fast API-path variant. UI-path tests should type into the
    scan input on the dashboard instead of using this fixture.
    """
    def _scan(text: str, source: str = "test") -> dict:
        r = requests.post(
            f"{api_base_url}/api/identify_scan",
            json={"text": text, "source": source},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    return _scan


# ---------------------------------------------------------------------------
# Utility: skip everything if the dev server isn't reachable
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=False)
def require_server(api_base_url: str):
    """Opt-in fixture for tests that need the live server.

    Kept autouse=False so unit tests don't hit the network. Request it
    explicitly from E2E tests if you want a friendly skip instead of a
    connection error.
    """
    try:
        r = requests.get(api_base_url, timeout=3)
        if r.status_code >= 500:
            pytest.skip(f"Dev server at {api_base_url} returned {r.status_code}")
    except requests.RequestException as exc:
        pytest.skip(f"Dev server unreachable at {api_base_url}: {exc}")
    return api_base_url


# ---------------------------------------------------------------------------
# Contrast guard
# ---------------------------------------------------------------------------
#
# Gray-on-gray text has been a recurring whack-a-mole: every round of UI
# work has at some point dropped a Bootstrap `text-muted` onto a dark
# surface and produced an unreadable element. A visual snapshot only
# catches the specific placements it happens to capture; this fixture
# catches ANY low-contrast text inside a given root element.
#
# Usage:
#     def test_something(page, assert_contrast):
#         page.goto(...)
#         assert_contrast(page.locator("#fcc-bind-picker-overlay"))

@pytest.fixture
def assert_contrast():
    """Playwright-driven contrast check against WCAG AA thresholds.

    Walks every text-bearing element under `root_locator`, reads its
    resolved foreground color, finds the first non-transparent
    background color by climbing ancestors, computes the WCAG relative-
    luminance contrast ratio, and asserts every visible piece of text
    meets `min_ratio` (default 4.5:1, AA for normal text).

    Returns the list of offenders when pytest fails so the error message
    names exactly which selectors violated and by how much.
    """
    _JS_CONTRAST = """
        (root, opts) => {
            const { minRatio, skipEmpty } = opts;
            if (!root) return { error: 'root_not_found' };

            const relLum = (r, g, b) => {
                const srgb = [r, g, b].map(v => {
                    v = v / 255;
                    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
                });
                return 0.2126 * srgb[0] + 0.7152 * srgb[1] + 0.0722 * srgb[2];
            };
            const ratio = (l1, l2) => {
                const a = Math.max(l1, l2), b = Math.min(l1, l2);
                return (a + 0.05) / (b + 0.05);
            };
            const parseColor = (str) => {
                const m = String(str).match(/rgba?\\(([^)]+)\\)/);
                if (!m) return null;
                const parts = m[1].split(',').map(s => parseFloat(s.trim()));
                return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
            };
            const firstOpaqueBg = (el) => {
                let cur = el;
                while (cur && cur !== document.documentElement) {
                    const bg = parseColor(getComputedStyle(cur).backgroundColor);
                    if (bg && bg.a > 0.01) return bg;
                    cur = cur.parentElement;
                }
                const bodyBg = parseColor(getComputedStyle(document.body).backgroundColor);
                return bodyBg || { r: 18, g: 18, b: 18, a: 1 };
            };

            const offenders = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
            let el;
            while ((el = walker.nextNode())) {
                const cs = getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                const opacity = parseFloat(cs.opacity || '1');
                if (opacity < 0.05) continue;
                const hasDirectText = Array.from(el.childNodes).some(n =>
                    n.nodeType === Node.TEXT_NODE && n.textContent.trim().length > 0
                );
                if (!hasDirectText) continue;
                if (skipEmpty && !el.innerText.trim()) continue;

                const fg = parseColor(cs.color);
                if (!fg) continue;
                const bg = firstOpaqueBg(el);
                const r = ratio(relLum(fg.r, fg.g, fg.b), relLum(bg.r, bg.g, bg.b));
                if (r < minRatio) {
                    offenders.push({
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        className: el.className || null,
                        text: (el.innerText || '').trim().slice(0, 80),
                        fg: `rgb(${Math.round(fg.r)}, ${Math.round(fg.g)}, ${Math.round(fg.b)})`,
                        bg: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,
                        ratio: Number(r.toFixed(2)),
                    });
                }
            }
            return { offenders };
        }
        """

    def _check(root_locator, min_ratio: float = 4.5, skip_empty: bool = True):
        # Use locator.evaluate so Playwright hands the real element to the
        # JS — no fragile selector-string extraction needed.
        result = root_locator.evaluate(
            _JS_CONTRAST,
            {"minRatio": min_ratio, "skipEmpty": skip_empty},
        )
        if not isinstance(result, dict) or result.get('error') == 'root_not_found':
            raise AssertionError(f"assert_contrast: could not evaluate on locator {root_locator!r}")
        offenders = result.get('offenders') or []
        if offenders:
            msg_lines = [f"Contrast < {min_ratio}:1 for {len(offenders)} element(s):"]
            for o in offenders:
                label = f"<{o['tag']}"
                if o.get('id'):
                    label += f" id={o['id']!r}"
                if o.get('className'):
                    label += f" class={o['className']!r}"
                label += ">"
                msg_lines.append(
                    f"  {label} ratio={o['ratio']}:1  fg={o['fg']}  bg={o['bg']}  text={o['text']!r}"
                )
            raise AssertionError("\n".join(msg_lines))

    return _check
