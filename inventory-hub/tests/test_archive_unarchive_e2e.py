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

import pytest
import requests


SPOOLMAN = "http://192.168.1.29:7913"


def _get_spool(sid: int) -> dict:
    return requests.get(f"{SPOOLMAN}/api/v1/spool/{sid}", timeout=5).json()


def _patch_spool(sid: int, body: dict) -> requests.Response:
    return requests.patch(f"{SPOOLMAN}/api/v1/spool/{sid}", json=body, timeout=10)


@pytest.fixture
def spool_with_location():
    """Locate a usable spool (non-archived, has a real location, has weight
    headroom) and yield its initial snapshot. Restores the spool's
    used_weight, archived state, location, and breadcrumb extra in
    teardown so the test never leaves the dev DB in a weird state.
    """
    try:
        r = requests.get(f"{SPOOLMAN}/api/v1/spool", timeout=5)
    except requests.exceptions.RequestException:
        pytest.skip("Spoolman dev instance unreachable")
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
        _patch_spool(snapshot["id"], {
            "archived": snapshot["archived"],
            "location": snapshot["location"],
            "used_weight": float(snapshot["used_weight"]),
        })
        # If the test didn't leave a breadcrumb originally, clean it. Spoolman
        # text-extras need JSON-encoded values; empty string is the closest
        # we can get to "delete".
        breadcrumb = snapshot["extra_breadcrumb"]
        if breadcrumb is None:
            _patch_spool(snapshot["id"], {"extra": {"fcc_pre_archive_location": '""'}})
    except Exception:
        # Best-effort teardown; failures here shouldn't mask test failures.
        pass


def test_archive_then_unarchive_restores_location(api_base_url: str, spool_with_location):
    """Drain → auto-archive (with breadcrumb) → refill → auto-unarchive
    (location restored from breadcrumb) round-trip via the inventory-hub
    API, exercising the real `update_spool` path."""
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

    after_drain = _get_spool(sid)
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

    after_refill = _get_spool(sid)
    assert after_refill.get("archived") is False, (
        f"expected auto-unarchive after refilling spool #{sid}, "
        f"got archived={after_refill.get('archived')!r}"
    )
    restored_loc = after_refill.get("location") or ""
    assert restored_loc == starting_loc, (
        f"expected location restored to {starting_loc!r}, got {restored_loc!r}"
    )


def test_unarchive_without_breadcrumb_stays_unassigned(api_base_url: str):
    """If a spool was archived (e.g. via Spoolman directly) without a
    breadcrumb planted, refilling should still un-archive but leave the
    spool at UNASSIGNED for the user to relocate manually."""
    try:
        r = requests.get(f"{SPOOLMAN}/api/v1/spool", timeout=5)
    except requests.exceptions.RequestException:
        pytest.skip("Spoolman dev instance unreachable")
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
        _patch_spool(sid, {"location": ""})
        # Clear any stale breadcrumb left by a prior FCC archive on this spool
        # (text-typed extras: JSON-empty-string is closest to "absent").
        _patch_spool(sid, {"extra": {"fcc_pre_archive_location": '""'}})
        _patch_spool(sid, {"archived": True})

        # Refill via FCC update — should auto-unarchive but leave at UNASSIGNED.
        refill_resp = requests.post(
            f"{api_base_url}/api/spool/update",
            json={"id": sid, "updates": {"used_weight": 0}},
            timeout=10,
        )
        assert refill_resp.ok, refill_resp.text

        after = _get_spool(sid)
        assert after.get("archived") is False, (
            f"expected auto-unarchive to fire on breadcrumb-less spool #{sid}"
        )
        assert (after.get("location") or "") == "", (
            f"expected spool to stay at UNASSIGNED without breadcrumb, "
            f"got {after.get('location')!r}"
        )
    finally:
        # Restore: unarchive first, then weight + location + archived state.
        _patch_spool(sid, {"archived": False})
        _patch_spool(sid, {
            "used_weight": float(original_used),
            "location": original_loc,
            "archived": original_archived,
        })
