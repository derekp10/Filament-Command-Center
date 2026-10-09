"""Group 38.5 — wait-budget canary for the Quick-Swap confirm overlay.

`showConfirmOverlay` awaits an active-print probe BEFORE it mounts the overlay:
`_probeWithTimeout(toolheadId, timeoutMs = 3000)` (inv_quickswap.js:340) is
awaited at :368, and `window.mountOverlay(...)` — the only thing that creates
`#fcc-quickswap-confirm-overlay` — is not reached until :468. Against offline
dev printers that probe reliably burns its full 3s, so any Playwright wait on
that overlay has a hard ~3000ms floor underneath it before network time.

Group 14.2 raised several of those waits to 8000ms for exactly this reason
(see the comment at test_quickswap_ui_e2e.py:77-79). It missed four sites,
which sat at 4000ms — ~1s of headroom over a 3s floor. Two of them were the
Group 38.5 flake (`test_return_text_and_overlay_close.py`); the other two
(`test_return_overlay_and_refresh.py`) were latent siblings with identical
exposure that simply had not gone red yet.

This canary is hermetic — it only reads test sources, so it runs in `--offline`
and needs no container. It exists so the next person to add a wait on this
overlay cannot silently reintroduce a sub-floor budget.
"""
from __future__ import annotations

import pathlib
import re

TESTS_DIR = pathlib.Path(__file__).parent

OVERLAY_ID = "#fcc-quickswap-confirm-overlay"

# 3000ms probe floor + headroom for the mount and the network round trip.
# The established precedent in the suite is 8000ms; 6000 is the floor we
# refuse to go below, so a deliberate 6000/8000 choice both pass.
MIN_BUDGET_MS = 6000

_LOCATOR_ASSIGN = re.compile(
    r"(\w+)\s*=\s*page\.locator\(\s*[\"']" + re.escape(OVERLAY_ID) + r"[\"']"
)
_EXPECT_VISIBLE = re.compile(
    r"expect\(\s*(.+?)\s*\)\.to_be_visible\(\s*timeout\s*=\s*(\d+)"
)
_DEF_LINE = re.compile(r"^\s*(?:async\s+)?def\s+")


def _offenders() -> list[str]:
    """Every wait on the confirm overlay whose budget is under the floor.

    Handles both spellings used in the suite: the inline
    `expect(page.locator("#fcc-...")).to_be_visible(timeout=N)` and the
    two-step `overlay = page.locator("#fcc-...")` / `expect(overlay)...`.
    Tracked names reset at each `def` so a variable called `overlay` in an
    unrelated test can't leak across function boundaries.
    """
    found: list[str] = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        if path.name == pathlib.Path(__file__).name:
            continue
        tracked: set[str] = set()
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            if _DEF_LINE.match(line):
                tracked = set()
            assign = _LOCATOR_ASSIGN.search(line)
            if assign:
                tracked.add(assign.group(1))
            visible = _EXPECT_VISIBLE.search(line)
            if not visible:
                continue
            target, budget = visible.group(1), int(visible.group(2))
            if OVERLAY_ID in target or target.strip() in tracked:
                if budget < MIN_BUDGET_MS:
                    found.append(f"{path.name}:{lineno} waits {budget}ms")
    return found


def test_confirm_overlay_waits_clear_the_probe_floor():
    """No wait on the Quick-Swap confirm overlay may sit under the 3s probe."""
    offenders = _offenders()
    assert not offenders, (
        "These waits on "
        + OVERLAY_ID
        + " are below the "
        + str(MIN_BUDGET_MS)
        + "ms floor:\n  "
        + "\n  ".join(offenders)
        + "\n\nshowConfirmOverlay awaits a ~3s active-print probe "
        "(inv_quickswap.js:340/368) before mountOverlay (:468), so a budget "
        "this tight is a flake waiting to happen — this is exactly what made "
        "Group 38.5 fail only under sweep load."
    )


def test_canary_actually_matches_the_real_call_sites():
    """Guard the guard: prove the matcher sees the sites it is meant to police.

    A canary whose regex silently stops matching is worse than no canary —
    it reports green forever. Group 38.9 hit precisely that failure mode when
    a call moved behind a helper and dropped out of a sibling canary's scope.
    """
    seen = 0
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if OVERLAY_ID not in text:
            continue
        tracked: set[str] = set()
        for line in text.splitlines():
            if _DEF_LINE.match(line):
                tracked = set()
            assign = _LOCATOR_ASSIGN.search(line)
            if assign:
                tracked.add(assign.group(1))
            visible = _EXPECT_VISIBLE.search(line)
            if visible and (
                OVERLAY_ID in visible.group(1) or visible.group(1).strip() in tracked
            ):
                seen += 1
    assert seen >= 5, (
        f"The wait-budget matcher only recognised {seen} call site(s) on "
        f"{OVERLAY_ID}. It matched 5 when written (2 in "
        "test_return_text_and_overlay_close.py, 2 in "
        "test_return_overlay_and_refresh.py, 1 in test_quickswap_ui_e2e.py). "
        "If the spelling of those assertions changed, update this matcher — "
        "do not delete the check."
    )
