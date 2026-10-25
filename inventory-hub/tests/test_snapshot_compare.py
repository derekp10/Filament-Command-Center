"""The visual comparator sees colour (readability review, 2026-10-21).

`conftest.compare_screenshot` is what the `snapshot` fixture uses to diff a
screenshot against its baseline in tests/__screenshots__/. It compared the two
images as RGBA, and Pillow's getbbox() on an RGBA image looks at the alpha band
only: two opaque screenshots of the same size never differ in alpha, so every
pair "matched" and only a size change could fail a visual test. A solid green
image matched confirm-qr-row.png, and stale baselines (the old orange Continue
QR) kept passing. Offline: Pillow and temporary files only.

HEAD proof (feat/readability-2026-10-21 4729579, the RGBA comparator copied
in): the colour tests below are RED (each "matched"); the tolerance and size
tests pass there too.
"""
from __future__ import annotations

import io
import os

import pytest
from PIL import Image

from conftest import BASELINE_DIR, compare_screenshot


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def baseline(tmp_path):
    """A 100 x 50 opaque baseline: dark grey with a cyan bar, saved as RGBA
    like a Playwright screenshot."""
    img = Image.new("RGBA", (100, 50), (30, 30, 30, 255))
    for x in range(10, 90):
        for y in range(20, 30):
            img.putpixel((x, y), (13, 202, 240, 255))
    path = tmp_path / "base.png"
    img.save(path)
    return str(path), img


def test_the_same_image_matches(baseline):
    path, img = baseline
    assert compare_screenshot(path, _png(img)) is None


def test_a_different_colour_of_the_same_size_does_not_match(baseline):
    path, _ = baseline
    green = Image.new("RGBA", (100, 50), (0, 200, 0, 255))
    msg = compare_screenshot(path, _png(green))
    assert msg and "pixels differ" in msg, msg
    # The debugging pair is written next to the baseline.
    assert os.path.isfile(path.replace(".png", ".actual.png"))
    assert os.path.isfile(path.replace(".png", ".diff.png"))


def test_a_recoloured_bar_does_not_match(baseline):
    """The QR card's change of colour: same shapes, another colour (amber
    instead of cyan) over 16 % of the image."""
    path, img = baseline
    amber = img.copy()
    for x in range(10, 90):
        for y in range(20, 30):
            amber.putpixel((x, y), (255, 193, 7, 255))
    assert compare_screenshot(path, _png(amber)) is not None


def test_drift_under_the_tolerance_still_matches(baseline):
    """Anti-aliasing noise: every pixel off by under the per-channel threshold,
    and a few pixels (under 1 %) off by more."""
    path, img = baseline
    noisy = img.copy()
    for x in range(100):
        for y in range(50):
            r, g, b, a = noisy.getpixel((x, y))
            noisy.putpixel((x, y), (min(255, r + 10), g, max(0, b - 10), a))
    for x in range(40):          # 40 of 5000 pixels = 0.8 %
        noisy.putpixel((x, 0), (255, 0, 0, 255))
    assert compare_screenshot(path, _png(noisy)) is None


def test_a_size_change_beyond_a_pixel_does_not_match(baseline):
    path, _ = baseline
    msg = compare_screenshot(path, _png(Image.new("RGBA", (103, 50), (30, 30, 30, 255))))
    assert msg and msg.startswith("size mismatch"), msg


def test_a_real_baseline_does_not_match_a_solid_image(tmp_path):
    """The reviewer's proof on a committed baseline (copied, so nothing is
    written next to the real one)."""
    src = os.path.join(BASELINE_DIR, "confirm-qr-row.png")
    if not os.path.isfile(src):
        pytest.skip("confirm-qr-row.png baseline is missing")
    real = Image.open(src)
    copy = tmp_path / "confirm-qr-row.png"
    real.save(copy)
    solid = Image.new("RGB", real.size, (0, 200, 0))
    assert compare_screenshot(str(copy), _png(solid)) is not None
