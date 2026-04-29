"""Regression guard for buglist L24 / L40 — buffer cards staleness.

The bug: backend-driven location moves (Location Manager, Quick-Swap,
force-unassign, auto-archive-on-empty) update Spoolman correctly, but the
buffer cards on the main dashboard kept showing stale location badges
until the user navigated away and back.

Root cause: `liveRefreshBuffer` in `inv_cmd.js` polled
/api/spools/refresh every sync-pulse but its diff check + in-place
mutation only covered display, color, color_direction, remaining_weight,
details, and archived. The backend response ALSO carries `location`,
`is_ghost`, `slot`, and `deployed_to` — those weren't being picked up,
so the renderBuffer call (which uses `item.location`, `item.is_ghost`,
`item.slot`, `item.deployed_to` to build the location badge) used stale
in-memory state.

Fix landed 2026-04-28 — these guards make sure a future refactor doesn't
silently drop the propagation again.
"""
from __future__ import annotations

import re
from pathlib import Path

JS_DIR = Path(__file__).resolve().parents[1] / "static" / "js" / "modules"


def _read(name: str) -> str:
    return (JS_DIR / name).read_text(encoding="utf-8")


def _find_live_refresh_buffer(src: str) -> str:
    """Return just the body of the `liveRefreshBuffer` function so the
    asserts below don't false-positive on similar code elsewhere in the
    file (e.g., loadBuffer or renderBuffer)."""
    m = re.search(
        r"const\s+liveRefreshBuffer\s*=\s*\(\s*\)\s*=>\s*\{(.+?)^};",
        src,
        re.DOTALL | re.MULTILINE,
    )
    assert m, "liveRefreshBuffer function not found in inv_cmd.js"
    return m.group(1)


# ---------------------------------------------------------------------------
# Diff check — every renderable field must be in the change-detection clause
# ---------------------------------------------------------------------------

class TestLiveRefreshBufferDiffCheck:
    def test_diff_check_includes_location(self):
        body = _find_live_refresh_buffer(_read("inv_cmd.js"))
        assert re.search(r"fresh\.location\s*!==\s*s\.location", body), \
            "liveRefreshBuffer must compare fresh.location vs s.location " \
            "or backend-driven moves won't trigger a re-render (buglist L40)"

    def test_diff_check_includes_is_ghost(self):
        body = _find_live_refresh_buffer(_read("inv_cmd.js"))
        assert re.search(r"fresh\.is_ghost\s*!==\s*s\.is_ghost", body), \
            "liveRefreshBuffer must compare fresh.is_ghost vs s.is_ghost " \
            "(deployed-vs-buffered transitions need this)"

    def test_diff_check_includes_slot(self):
        body = _find_live_refresh_buffer(_read("inv_cmd.js"))
        assert re.search(r"fresh\.slot\s*!==\s*s\.slot", body), \
            "liveRefreshBuffer must compare fresh.slot vs s.slot"

    def test_diff_check_includes_deployed_to(self):
        body = _find_live_refresh_buffer(_read("inv_cmd.js"))
        assert re.search(r"fresh\.deployed_to\s*!==\s*s\.deployed_to", body), \
            "liveRefreshBuffer must compare fresh.deployed_to vs s.deployed_to"


# ---------------------------------------------------------------------------
# Mutation — every diffed field must actually be copied onto the live state
# ---------------------------------------------------------------------------

class TestLiveRefreshBufferMutation:
    def test_mutation_copies_location(self):
        body = _find_live_refresh_buffer(_read("inv_cmd.js"))
        assert re.search(r"s\.location\s*=\s*fresh\.location", body), \
            "liveRefreshBuffer detects a location change but doesn't copy it " \
            "onto state.heldSpools — renderBuffer will use the stale value"

    def test_mutation_copies_is_ghost(self):
        body = _find_live_refresh_buffer(_read("inv_cmd.js"))
        assert re.search(r"s\.is_ghost\s*=\s*fresh\.is_ghost", body)

    def test_mutation_copies_slot(self):
        body = _find_live_refresh_buffer(_read("inv_cmd.js"))
        assert re.search(r"s\.slot\s*=\s*fresh\.slot", body)

    def test_mutation_copies_deployed_to(self):
        body = _find_live_refresh_buffer(_read("inv_cmd.js"))
        assert re.search(r"s\.deployed_to\s*=\s*fresh\.deployed_to", body)


# ---------------------------------------------------------------------------
# Backend contract — /api/spools/refresh response shape
# ---------------------------------------------------------------------------

class TestLiveSpoolsDataContract:
    """Pin the backend response shape so the frontend guards above can
    rely on the keys being present. If get_live_spools_data drops one of
    these keys in a future refactor, this test fails loudly instead of
    silently turning the buffer cards stale again."""

    def test_get_live_spools_data_returns_location_fields(self):
        logic_src = (JS_DIR.parents[2] / "logic.py").read_text(encoding="utf-8")
        # Find the result-dict construction — it should include all four keys.
        m = re.search(
            r"def get_live_spools_data\(.+?return results",
            logic_src,
            re.DOTALL,
        )
        assert m, "get_live_spools_data not found in logic.py"
        fn_body = m.group(0)
        for key in ("location", "is_ghost", "slot", "deployed_to"):
            assert f'"{key}":' in fn_body, \
                f"get_live_spools_data must include {key!r} in its result " \
                f"dict — frontend depends on it for buffer card rendering"
