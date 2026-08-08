"""End-to-end test for spool auto-archive (0g) and the symmetric
auto-unarchive (refill) lifecycle.

Drives `inventory-hub`'s `/api/update_filament` and `/api/spool/update`
flow against a running container + Spoolman so the real `update_spool`
path is exercised — including:
  - `_auto_archive_on_empty` planting `extra.fcc_pre_archive_location`
  - `_auto_unarchive_on_refill` consuming it on weight refill
  - the `_merge_extras_with_existing` round-trip preserving siblings

Skips when no spool with a non-empty location is available.
"""
from __future__ import annotations

import warnings

import pytest
import requests

# Group 38 — this suite PATCHes the real dev Spoolman on the NAS directly
# (`{spoolman_url}/api/v1/spool/{sid}`), archiving a real spool and restoring it
# afterwards. It carried NO marker, and `require_spoolman` only checks
# REACHABILITY — it is not gated by RUN_INTEGRATION — so a plain `pytest` run
# with the NAS up mutated Derek's live inventory. CLAUDE.md's contract is
# explicit that `@pytest.mark.integration` is what gates "tests that hit the
# real dev Spoolman", so this belongs here. Full sweeps run with
# RUN_INTEGRATION=1, so sweep coverage is unchanged; what changes is that a
# plain run no longer touches dev.
pytestmark = pytest.mark.integration


def _get_spool(spoolman_url: str, sid: int) -> dict:
    return requests.get(f"{spoolman_url}/api/v1/spool/{sid}", timeout=5).json()


def _patch_spool(spoolman_url: str, sid: int, body: dict) -> requests.Response:
    return requests.patch(f"{spoolman_url}/api/v1/spool/{sid}", json=body, timeout=10)


@pytest.fixture
def spool_with_location(require_spoolman: str):
    """Locate a usable spool (non-archived, has a real location, has weight
    headroom) and yield its initial snapshot. Restores the spool's
    used_weight, archived state, location, and breadcrumb extra in
    teardown so the test never leaves the dev DB in a weird state.
    """
    spoolman_url = require_spoolman
    r = requests.get(f"{spoolman_url}/api/v1/spool", timeout=5)
    if not r.ok:
        pytest.skip(f"Spoolman returned {r.status_code} for spool list")

    candidate = None
    for s in r.json() or []:
        if s.get("archived"):
            continue
        loc = (s.get("location") or "").strip()
        if not loc:
            continue
        try:
            initial = float(s.get("filament", {}).get("weight") or s.get("initial_weight") or 0)
        except (TypeError, ValueError):
            continue
        if initial <= 0:
            continue
        candidate = s
        break

    if candidate is None:
        pytest.skip("no non-archived spool with a real location available")

    snapshot = {
        "id": candidate["id"],
        "used_weight": candidate.get("used_weight") or 0,
        "initial_weight": (
            candidate.get("initial_weight")
            or (candidate.get("filament") or {}).get("weight")
        ),
        "location": candidate.get("location") or "",
        "archived": bool(candidate.get("archived", False)),
        "extra_breadcrumb": (candidate.get("extra") or {}).get("fcc_pre_archive_location"),
    }

    yield snapshot

    # Restore original state. Order matters: unarchive first, then move back,
    # then weight last (so auto-archive doesn't fire mid-restore).
    try:
        _patch_spool(spoolman_url, snapshot["id"], {
            "archived": snapshot["archived"],
            "location": snapshot["location"],
            "used_weight": float(snapshot["used_weight"]),
        })
        # If the test didn't leave a breadcrumb originally, clean it. Spoolman
        # text-extras need JSON-encoded values; empty string is the closest
        # we can get to "delete".
        breadcrumb = snapshot["extra_breadcrumb"]
        if breadcrumb is None:
            _patch_spool(spoolman_url, snapshot["id"], {"extra": {"fcc_pre_archive_location": '""'}})
    except Exception as exc:  # noqa: BLE001
        # Group 38 — still best-effort (teardown must not mask a test failure),
        # but no longer SILENT. This test archives a REAL dev spool, so a
        # swallowed restore leaves Derek's inventory wrong with no trace of
        # which record or why.
        warnings.warn(
            f"archive/unarchive teardown FAILED to restore spool "
            f"{snapshot['id']}: {exc!r} — it may still be archived, at the "
            f"wrong location, or at the wrong weight.",
            stacklevel=2,
        )
    else:
        # Verify the restore actually landed. A PATCH returning 200 is not
        # proof the value stuck — the same verify-by-re-read discipline Group 36
        # adopted after silent restore failures drained real filaments.
        try:
            after = _get_spool(spoolman_url, snapshot["id"])
            drift = []
            if bool(after.get("archived", False)) != snapshot["archived"]:
                drift.append(f"archived={after.get('archived')} (want {snapshot['archived']})")
            if (after.get("location") or "").strip() != snapshot["location"].strip():
                drift.append(f"location={after.get('location')!r} (want {snapshot['location']!r})")
            if drift:
                warnings.warn(
                    f"archive/unarchive teardown did NOT fully restore spool "
                    f"{snapshot['id']}: " + "; ".join(drift),
                    stacklevel=2,
                )
        except Exception:  # noqa: BLE001
            pass  # the verification itself must never break teardown


def test_archive_then_unarchive_restores_location(
    require_server: str, dev_spoolman_url: str, spool_with_location
):
    """Drain → auto-archive (with breadcrumb) → refill → auto-unarchive
    (location restored from breadcrumb) round-trip via the inventory-hub
    API, exercising the real `update_spool` path."""
    api_base_url = require_server
    snap = spool_with_location
    sid = snap["id"]
    initial = float(snap["initial_weight"])
    starting_loc = snap["location"]

    # --- Drain to 0g via the FCC update endpoint --------------------------
    drain_resp = requests.post(
        f"{api_base_url}/api/spool/update",
        json={"id": sid, "updates": {"used_weight": initial}},
        timeout=10,
    )
    assert drain_resp.ok, drain_resp.text

    after_drain = _get_spool(dev_spoolman_url, sid)
    assert after_drain.get("archived") is True, (
        f"expected auto-archive after draining spool #{sid} to 0g, "
        f"got archived={after_drain.get('archived')!r}"
    )
    # Spoolman represents UNASSIGNED as empty string.
    assert (after_drain.get("location") or "") == "", (
        f"expected location cleared after auto-archive, got {after_drain.get('location')!r}"
    )
    breadcrumb = (after_drain.get("extra") or {}).get("fcc_pre_archive_location")
    # Spoolman wraps text-typed extras as JSON strings — strip the wrapping
    # quotes for comparison.
    assert breadcrumb, f"breadcrumb missing after auto-archive of spool #{sid}"
    breadcrumb_unwrapped = breadcrumb.strip('"')
    assert breadcrumb_unwrapped == starting_loc, (
        f"breadcrumb expected {starting_loc!r}, got {breadcrumb_unwrapped!r}"
    )

    # --- Refill via the FCC update endpoint -------------------------------
    refill_resp = requests.post(
        f"{api_base_url}/api/spool/update",
        json={"id": sid, "updates": {"used_weight": 0}},
        timeout=10,
    )
    assert refill_resp.ok, refill_resp.text

    after_refill = _get_spool(dev_spoolman_url, sid)
    assert after_refill.get("archived") is False, (
        f"expected auto-unarchive after refilling spool #{sid}, "
        f"got archived={after_refill.get('archived')!r}"
    )
    restored_loc = after_refill.get("location") or ""
    assert restored_loc == starting_loc, (
        f"expected location restored to {starting_loc!r}, got {restored_loc!r}"
    )


def test_unarchive_without_breadcrumb_stays_unassigned(
    require_server: str, require_spoolman: str
):
    """If a spool was archived (e.g. via Spoolman directly) without a
    breadcrumb planted, refilling should still un-archive but leave the
    spool at UNASSIGNED for the user to relocate manually."""
    api_base_url = require_server
    spoolman_url = require_spoolman
    r = requests.get(f"{spoolman_url}/api/v1/spool", timeout=5)
    if not r.ok:
        pytest.skip(f"Spoolman returned {r.status_code} for spool list")

    candidate = None
    for s in r.json() or []:
        if s.get("archived"):
            continue
        try:
            initial = float(s.get("filament", {}).get("weight") or s.get("initial_weight") or 0)
        except (TypeError, ValueError):
            continue
        if initial <= 0:
            continue
        candidate = s
        break
    if candidate is None:
        pytest.skip("no non-archived spool with weight available for breadcrumb-less test")

    sid = candidate["id"]
    original_used = candidate.get("used_weight") or 0
    original_loc = candidate.get("location") or ""
    original_archived = bool(candidate.get("archived", False))

    try:
        # Move to UNASSIGNED first, THEN archive it directly via Spoolman so no
        # breadcrumb is planted (FCC's auto-archive helper would normally plant one).
        _patch_spool(spoolman_url, sid, {"location": ""})
        # Clear any stale breadcrumb left by a prior FCC archive on this spool
        # (text-typed extras: JSON-empty-string is closest to "absent").
        _patch_spool(spoolman_url, sid, {"extra": {"fcc_pre_archive_location": '""'}})
        _patch_spool(spoolman_url, sid, {"archived": True})

        # Refill via FCC update — should auto-unarchive but leave at UNASSIGNED.
        refill_resp = requests.post(
            f"{api_base_url}/api/spool/update",
            json={"id": sid, "updates": {"used_weight": 0}},
            timeout=10,
        )
        assert refill_resp.ok, refill_resp.text

        after = _get_spool(spoolman_url, sid)
        assert after.get("archived") is False, (
            f"expected auto-unarchive to fire on breadcrumb-less spool #{sid}"
        )
        assert (after.get("location") or "") == "", (
            f"expected spool to stay at UNASSIGNED without breadcrumb, "
            f"got {after.get('location')!r}"
        )
    finally:
        # Restore: unarchive first, then weight + location + archived state.
        _patch_spool(spoolman_url, sid, {"archived": False})
        _patch_spool(spoolman_url, sid, {
            "used_weight": float(original_used),
            "location": original_loc,
            "archived": original_archived,
        })
