"""Unit tests for `_auto_archive_on_empty` and `_auto_unarchive_on_refill`
in `spoolman_api`.

These are the pure-Python helpers that mutate a spool update payload to
archive on 0g (and plant a pre-archive location breadcrumb) and to
auto-unarchive when weight comes back above 0 (restoring the breadcrumb's
location when present).

No real Spoolman HTTP — the helpers are pure functions that mutate `data`
in place. The bottom of the file also covers the `update_spool` wiring
with mocked HTTP so we can verify the helpers fire from the real entry
point without needing a Docker restart.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

import spoolman_api as sm


def _mock_response(ok: bool, json_body: dict | None = None) -> MagicMock:
    m = MagicMock()
    m.ok = ok
    m.status_code = 200 if ok else 400
    m.text = "ok" if ok else "validation error"
    m.json = MagicMock(return_value=json_body or {})
    return m


# ---------------------------------------------------------------------------
# _auto_archive_on_empty
# ---------------------------------------------------------------------------

class TestAutoArchiveOnEmpty:
    def test_archives_and_unassigns_when_remaining_zero(self):
        data = {"used_weight": 1000, "initial_weight": 1000}
        sm._auto_archive_on_empty(data, 1000, 0, existing_location="PM-XL-Buffer-1")
        assert data["archived"] is True
        assert data["location"] == ""

    def test_plants_breadcrumb_in_extras_with_location(self):
        data = {"used_weight": 1000, "initial_weight": 1000}
        sm._auto_archive_on_empty(data, 1000, 0, existing_location="PM-XL-Buffer-1")
        assert data["extra"]["fcc_pre_archive_location"] == "PM-XL-Buffer-1"

    def test_skips_breadcrumb_when_already_unassigned(self):
        data = {"used_weight": 1000, "initial_weight": 1000}
        sm._auto_archive_on_empty(data, 1000, 0, existing_location="")
        # Archive still happens, but no breadcrumb is planted (nothing to remember).
        assert data["archived"] is True
        assert data["location"] == ""
        # 13.6 Part B — slot binding cleanup fires regardless; defensive
        # against a stale container_slot on a spool that landed at
        # UNASSIGNED with leftover bindings from a manual edit.
        assert "fcc_pre_archive_location" not in data["extra"]
        assert data["extra"]["container_slot"] == ""

    def test_skips_breadcrumb_when_existing_location_none(self):
        data = {"used_weight": 1000, "initial_weight": 1000}
        sm._auto_archive_on_empty(data, 1000, 0, existing_location=None)
        assert data["archived"] is True
        assert "fcc_pre_archive_location" not in data["extra"]
        assert data["extra"]["container_slot"] == ""

    def test_does_not_archive_when_remaining_above_zero(self):
        data = {"used_weight": 500, "initial_weight": 1000}
        sm._auto_archive_on_empty(data, 1000, 0, existing_location="PM-XL-Buffer-1")
        assert "archived" not in data
        assert "location" not in data
        assert "extra" not in data

    def test_caller_archived_intent_wins(self):
        data = {"used_weight": 1000, "initial_weight": 1000, "archived": False}
        sm._auto_archive_on_empty(data, 1000, 0, existing_location="PM-XL-Buffer-1")
        assert data["archived"] is False  # caller said no — respected

    def test_caller_location_intent_wins(self):
        data = {"used_weight": 1000, "initial_weight": 1000, "location": "PM-XL-Slot-2"}
        sm._auto_archive_on_empty(data, 1000, 0, existing_location="PM-XL-Buffer-1")
        # When caller specifies location, we don't plant the breadcrumb either —
        # the caller is in charge of where this spool ends up.
        assert data["location"] == "PM-XL-Slot-2"
        assert "extra" not in data

    def test_no_op_when_no_weight_in_payload(self):
        data = {"location": "PM-XL-Slot-1"}
        sm._auto_archive_on_empty(data, 1000, 500, existing_location="PM-XL-Slot-1")
        assert "archived" not in data

    def test_preserves_caller_extras(self):
        data = {
            "used_weight": 1000,
            "initial_weight": 1000,
            "extra": {"some_key": "some_value"},
        }
        sm._auto_archive_on_empty(data, 1000, 0, existing_location="PM-XL-Buffer-1")
        assert data["extra"]["some_key"] == "some_value"
        assert data["extra"]["fcc_pre_archive_location"] == "PM-XL-Buffer-1"


# ---------------------------------------------------------------------------
# 31.2 — inherit-weight spools (no own initial_weight) fall back to the
# parent filament's net weight for the archive/unarchive remaining math.
# ---------------------------------------------------------------------------

class TestInheritWeightFallback:
    """A spool with initial_weight=None inherits its net capacity from its
    filament (same as Spoolman's remaining_weight). Before 31.2 the auto-
    archive/unarchive helpers bailed early on the None initial, so emptying an
    inherit-weight spool via the wizard/quick-weigh never archived it."""

    def test_archive_uses_filament_weight_when_initial_none(self):
        # used == filament net weight → remaining 0 → archive.
        data = {"used_weight": 1000}
        sm._auto_archive_on_empty(
            data, None, 0, existing_location="PM-XL-Buffer-1",
            existing_filament_weight=1000,
        )
        assert data["archived"] is True
        assert data["location"] == ""

    def test_archive_respects_filament_weight_not_yet_empty(self):
        # remaining still > 0 against the inherited net → no archive.
        data = {"used_weight": 600}
        sm._auto_archive_on_empty(
            data, None, 0, existing_location="PM-XL-Buffer-1",
            existing_filament_weight=1000,
        )
        assert "archived" not in data

    def test_no_archive_when_neither_initial_nor_filament_known(self):
        # No effective initial anywhere → quiet no-op (can't judge remaining).
        data = {"used_weight": 1000}
        sm._auto_archive_on_empty(
            data, None, 0, existing_location="PM-XL-Buffer-1",
            existing_filament_weight=None,
        )
        assert "archived" not in data

    def test_own_initial_still_wins_over_filament_weight(self):
        # Spool has its own initial → filament weight is ignored.
        data = {"used_weight": 500}
        sm._auto_archive_on_empty(
            data, 800, 0, existing_location="PM-XL-Buffer-1",
            existing_filament_weight=1000,
        )
        # remaining = 800 - 500 = 300 > 0 → no archive (uses 800, not 1000).
        assert "archived" not in data

    def test_unarchive_uses_filament_weight_when_initial_none(self):
        existing = {
            "archived": True,
            "initial_weight": None,
            "used_weight": 1000,
            "location": "",
            "filament": {"weight": 1000},
            "extra": {"fcc_pre_archive_location": "PM-XL-Buffer-1"},
        }
        data = {"used_weight": 200}  # remaining 800 against inherited net
        sm._auto_unarchive_on_refill(data, existing)
        assert data["archived"] is False
        assert data["location"] == "PM-XL-Buffer-1"

    def test_unarchive_noop_when_no_effective_initial(self):
        existing = {
            "archived": True,
            "initial_weight": None,
            "used_weight": 1000,
            "location": "",
            "filament": {},  # no weight to inherit
            "extra": {},
        }
        data = {"used_weight": 200}
        sm._auto_unarchive_on_refill(data, existing)
        assert "archived" not in data


class TestUpdateSpoolInheritWeightArchive:
    """update_spool wiring: an inherit-weight spool (get_spool returns
    initial_weight=None + a nested filament.weight) auto-archives on empty."""

    def test_inherit_weight_spool_archives_via_update_spool(self):
        existing = {
            "id": 42,
            "initial_weight": None,
            "used_weight": 400,
            "archived": False,
            "location": "PM-XL-Buffer-1",
            "filament": {"id": 7, "weight": 1000},
            "extra": {},
        }
        captured = {}

        def fake_patch(url, json, **kw):
            captured["json"] = json
            return _mock_response(True, {**existing, **json})

        with patch.object(sm, "get_spool", return_value=existing), \
             patch.object(sm, "_get_raw_extras", return_value={}), \
             patch("spoolman_api.requests.patch", side_effect=fake_patch):
            res = sm.update_spool(42, {"used_weight": 1000})

        assert res is not None
        assert captured["json"]["archived"] is True
        assert captured["json"]["location"] == ""

    def test_inherit_weight_spool_unarchives_via_update_spool(self):
        existing = {
            "id": 42,
            "initial_weight": None,
            "used_weight": 1000,
            "archived": True,
            "location": "",
            "filament": {"id": 7, "weight": 1000},
            "extra": {"fcc_pre_archive_location": "PM-XL-Buffer-1"},
        }
        captured = {}

        def fake_patch(url, json, **kw):
            captured["json"] = json
            return _mock_response(True, {**existing, **json})

        with patch.object(sm, "get_spool", return_value=existing), \
             patch.object(sm, "_get_raw_extras", return_value={"fcc_pre_archive_location": '"PM-XL-Buffer-1"'}), \
             patch("spoolman_api.requests.patch", side_effect=fake_patch):
            res = sm.update_spool(42, {"used_weight": 200})

        assert res is not None
        assert captured["json"]["archived"] is False
        assert captured["json"]["location"] == "PM-XL-Buffer-1"


# ---------------------------------------------------------------------------
# 13.6 Part B — auto-archive slot binding cleanup
# ---------------------------------------------------------------------------

class TestAutoArchiveClearsSlotBindings:
    """13.6 Part B — auto-archive must clear container_slot and the ghost
    source fields so the dryer-box card drops the spool symmetrically with
    the FilaBridge unmap. Previously these lingered, leaving the box's slot
    view showing a spool that FilaBridge had already released."""

    def test_clears_container_slot_on_archive(self):
        data = {"used_weight": 1000, "initial_weight": 1000}
        sm._auto_archive_on_empty(
            data, 1000, 0, existing_location="PM-DB-XL-L"
        )
        assert data["extra"]["container_slot"] == ""

    def test_clears_physical_source_on_archive(self):
        data = {"used_weight": 1000, "initial_weight": 1000}
        sm._auto_archive_on_empty(
            data, 1000, 0, existing_location="XL-1"
        )
        # Ghost source fields cleared so a stale ghost binding doesn't make
        # the dryer box think the archived spool is still feeding a toolhead.
        assert data["extra"]["physical_source"] == ""
        assert data["extra"]["physical_source_slot"] == ""

    def test_preserves_breadcrumb_alongside_slot_clear(self):
        """fcc_pre_archive_location is still planted; only the slot+ghost
        keys get the new cleanup."""
        data = {"used_weight": 1000, "initial_weight": 1000}
        sm._auto_archive_on_empty(
            data, 1000, 0, existing_location="PM-DB-XL-L"
        )
        assert data["extra"]["fcc_pre_archive_location"] == "PM-DB-XL-L"
        assert data["extra"]["container_slot"] == ""

    def test_merges_with_caller_extras(self):
        """Caller extras (e.g. user-set sheet_link from a wizard edit) must
        survive the auto-archive slot cleanup."""
        data = {
            "used_weight": 1000,
            "initial_weight": 1000,
            "extra": {"sheet_link": "https://example.com/sheet"},
        }
        sm._auto_archive_on_empty(
            data, 1000, 0, existing_location="PM-DB-XL-L"
        )
        assert data["extra"]["sheet_link"] == "https://example.com/sheet"
        assert data["extra"]["container_slot"] == ""

    def test_no_slot_clear_when_remaining_above_zero(self):
        """The cleanup only fires when auto-archive actually triggers."""
        data = {"used_weight": 500, "initial_weight": 1000}
        sm._auto_archive_on_empty(
            data, 1000, 500, existing_location="PM-DB-XL-L"
        )
        # No archive → no slot cleanup; data is left untouched.
        assert data.get("archived") is None
        assert "extra" not in data

    def test_no_slot_clear_when_caller_overrides_location(self):
        """If the caller has its own `location` plan, we don't plant
        breadcrumb OR clear slot — the caller is taking over the move."""
        data = {
            "used_weight": 1000,
            "initial_weight": 1000,
            "location": "PM-XL-Buffer-2",
        }
        sm._auto_archive_on_empty(
            data, 1000, 0, existing_location="PM-DB-XL-L"
        )
        # archived still added (caller didn't override that), but the
        # extras-touching branch is short-circuited by the caller's location.
        assert data["archived"] is True
        assert data["location"] == "PM-XL-Buffer-2"
        assert "extra" not in data


# ---------------------------------------------------------------------------
# _auto_unarchive_on_refill
# ---------------------------------------------------------------------------

class TestAutoUnarchiveOnRefill:
    def test_unarchives_when_archived_spool_gets_weight_back(self):
        existing = {
            "archived": True,
            "initial_weight": 1000,
            "used_weight": 1000,
            "location": "",
            "extra": {"fcc_pre_archive_location": "PM-XL-Buffer-1"},
        }
        data = {"used_weight": 200}  # remaining 800
        sm._auto_unarchive_on_refill(data, existing)
        assert data["archived"] is False
        assert data["location"] == "PM-XL-Buffer-1"

    def test_unarchives_without_breadcrumb_leaves_unassigned(self):
        existing = {
            "archived": True,
            "initial_weight": 1000,
            "used_weight": 1000,
            "location": "",
            "extra": {},
        }
        data = {"used_weight": 200}
        sm._auto_unarchive_on_refill(data, existing)
        assert data["archived"] is False
        # Caller didn't specify, breadcrumb absent — leave location untouched
        # so Spoolman's existing UNASSIGNED stays in place.
        assert "location" not in data

    def test_skip_when_existing_not_archived(self):
        existing = {
            "archived": False,
            "initial_weight": 1000,
            "used_weight": 1000,
            "extra": {"fcc_pre_archive_location": "PM-XL-Buffer-1"},
        }
        data = {"used_weight": 200}
        sm._auto_unarchive_on_refill(data, existing)
        # Already not archived, helper does nothing.
        assert "archived" not in data
        assert "location" not in data

    def test_skip_when_remaining_still_zero(self):
        existing = {
            "archived": True,
            "initial_weight": 1000,
            "used_weight": 1000,
            "extra": {"fcc_pre_archive_location": "PM-XL-Buffer-1"},
        }
        data = {"used_weight": 1000}  # still empty
        sm._auto_unarchive_on_refill(data, existing)
        assert "archived" not in data

    def test_caller_archived_intent_wins(self):
        existing = {
            "archived": True,
            "initial_weight": 1000,
            "used_weight": 1000,
            "extra": {"fcc_pre_archive_location": "PM-XL-Buffer-1"},
        }
        data = {"used_weight": 200, "archived": True}  # caller wants to keep archived
        sm._auto_unarchive_on_refill(data, existing)
        assert data["archived"] is True

    def test_caller_location_intent_wins(self):
        existing = {
            "archived": True,
            "initial_weight": 1000,
            "used_weight": 1000,
            "extra": {"fcc_pre_archive_location": "PM-XL-Buffer-1"},
        }
        data = {"used_weight": 200, "location": "PM-XL-Slot-2"}
        sm._auto_unarchive_on_refill(data, existing)
        # Both unarchive AND honor caller's location
        assert data["archived"] is False
        assert data["location"] == "PM-XL-Slot-2"

    def test_uses_existing_initial_when_only_used_in_payload(self):
        existing = {
            "archived": True,
            "initial_weight": 1000,
            "used_weight": 1000,
            "extra": {"fcc_pre_archive_location": "PM-XL-Buffer-1"},
        }
        data = {"used_weight": 0}  # full spool back from 0
        sm._auto_unarchive_on_refill(data, existing)
        assert data["archived"] is False
        assert data["location"] == "PM-XL-Buffer-1"

    def test_handles_missing_existing_extras(self):
        existing = {
            "archived": True,
            "initial_weight": 1000,
            "used_weight": 1000,
        }
        data = {"used_weight": 200}
        # Should not crash on missing extra — just no breadcrumb to consult.
        sm._auto_unarchive_on_refill(data, existing)
        assert data["archived"] is False
        assert "location" not in data

    def test_handles_empty_existing(self):
        # Defensive: pass an empty dict (e.g. spool not found upstream).
        sm._auto_unarchive_on_refill({"used_weight": 200}, {})
        # Nothing to do — should be a quiet no-op.

    def test_invalid_weight_data_is_quiet_noop(self):
        existing = {
            "archived": True,
            "initial_weight": "not-a-number",
            "used_weight": "also-not",
            "extra": {"fcc_pre_archive_location": "PM-XL-Buffer-1"},
        }
        data = {"used_weight": 200}
        sm._auto_unarchive_on_refill(data, existing)
        assert "archived" not in data


# ---------------------------------------------------------------------------
# SYSTEM_MANAGED_EXTRAS guard
# ---------------------------------------------------------------------------

class TestSystemManagedGuardOnBreadcrumb:
    def test_breadcrumb_key_is_system_managed(self):
        """User surfaces (wizard, vendor edit, etc.) must funnel through
        compute_dirty_extras with SYSTEM_MANAGED_EXTRAS so they cannot
        clobber the auto-archive breadcrumb."""
        assert "fcc_pre_archive_location" in sm.SYSTEM_MANAGED_EXTRAS

    def test_compute_dirty_extras_strips_breadcrumb_from_user_payload(self):
        existing = {"fcc_pre_archive_location": "PM-XL-Buffer-1"}
        # User surface tries to clobber the breadcrumb with garbage.
        requested = {"fcc_pre_archive_location": "evil-value", "color_hex": "FF0000"}
        dirty, stripped = sm.compute_dirty_extras(
            existing, requested, system_managed=sm.SYSTEM_MANAGED_EXTRAS
        )
        assert "fcc_pre_archive_location" not in dirty
        assert "fcc_pre_archive_location" in stripped
        assert dirty["color_hex"] == "FF0000"


# ---------------------------------------------------------------------------
# update_spool wiring — confirms helpers fire from the real entry point
# ---------------------------------------------------------------------------

class TestUpdateSpoolArchiveLifecycle:
    """Mock Spoolman HTTP and assert that `update_spool` plants the
    breadcrumb on auto-archive and consumes it on auto-unarchive.
    No real Spoolman or Docker container required."""

    def test_archive_on_empty_plants_breadcrumb_via_update_spool(self):
        existing = {
            "id": 99,
            "initial_weight": 1000,
            "used_weight": 500,
            "archived": False,
            "location": "PM-XL-Buffer-1",
            "extra": {},
        }
        captured = {}

        def fake_patch(url, json, **kw):
            captured["url"] = url
            captured["json"] = json
            return _mock_response(True, {**existing, **json})

        with patch.object(sm, "get_spool", return_value=existing), \
             patch.object(sm, "_get_raw_extras", return_value={}), \
             patch("spoolman_api.requests.patch", side_effect=fake_patch):
            res = sm.update_spool(99, {"used_weight": 1000})

        assert res is not None
        # Helper fired through update_spool.
        assert captured["json"]["archived"] is True
        assert captured["json"]["location"] == ""
        # Breadcrumb planted in extras.
        extras = captured["json"].get("extra") or {}
        # Spoolman text-typed extras get JSON-string-wrapped by sanitize_outbound_data.
        breadcrumb = extras.get("fcc_pre_archive_location")
        assert breadcrumb, "expected breadcrumb in patched extras"
        assert "PM-XL-Buffer-1" in str(breadcrumb)

    def test_unarchive_on_refill_restores_location_via_update_spool(self):
        existing = {
            "id": 99,
            "initial_weight": 1000,
            "used_weight": 1000,
            "archived": True,
            "location": "",
            "extra": {"fcc_pre_archive_location": "PM-XL-Buffer-1"},
        }
        captured = {}

        def fake_patch(url, json, **kw):
            captured["url"] = url
            captured["json"] = json
            return _mock_response(True, {**existing, **json})

        with patch.object(sm, "get_spool", return_value=existing), \
             patch.object(sm, "_get_raw_extras", return_value={"fcc_pre_archive_location": '"PM-XL-Buffer-1"'}), \
             patch("spoolman_api.requests.patch", side_effect=fake_patch):
            res = sm.update_spool(99, {"used_weight": 200})

        assert res is not None
        assert captured["json"]["archived"] is False
        assert captured["json"]["location"] == "PM-XL-Buffer-1"

    def test_refill_without_breadcrumb_unarchives_but_no_location_change(self):
        existing = {
            "id": 99,
            "initial_weight": 1000,
            "used_weight": 1000,
            "archived": True,
            "location": "",
            "extra": {},
        }
        captured = {}

        def fake_patch(url, json, **kw):
            captured["url"] = url
            captured["json"] = json
            return _mock_response(True, {**existing, **json})

        with patch.object(sm, "get_spool", return_value=existing), \
             patch.object(sm, "_get_raw_extras", return_value={}), \
             patch("spoolman_api.requests.patch", side_effect=fake_patch):
            res = sm.update_spool(99, {"used_weight": 200})

        assert res is not None
        assert captured["json"]["archived"] is False
        # Caller didn't specify, breadcrumb absent — location key omitted from PATCH.
        assert "location" not in captured["json"]

    def test_already_archived_zero_weight_update_is_idempotent(self):
        """Already-archived spool with a still-zero weight: the auto-archive
        helper fires idempotently (archived=True, location='') and the
        unarchive helper correctly sits out (remaining is still ≤ 0). Net
        effect is a no-op equivalent payload — neither activity-log line
        should fire because pre_archived already matches data['archived']."""
        existing = {
            "id": 99,
            "initial_weight": 1000,
            "used_weight": 1000,
            "archived": True,
            "location": "",
            "extra": {"fcc_pre_archive_location": "PM-XL-Buffer-1"},
        }
        captured = {}

        def fake_patch(url, json, **kw):
            captured["url"] = url
            captured["json"] = json
            return _mock_response(True, {**existing, **json})

        with patch.object(sm, "get_spool", return_value=existing), \
             patch.object(sm, "_get_raw_extras", return_value={"fcc_pre_archive_location": '"PM-XL-Buffer-1"'}), \
             patch("spoolman_api.requests.patch", side_effect=fake_patch):
            res = sm.update_spool(99, {"used_weight": 1000})

        assert res is not None
        # Auto-archive helper writes the idempotent values.
        assert captured["json"]["archived"] is True
        assert captured["json"]["location"] == ""
        # No NEW state transition: neither auto-archive nor auto-unarchive log fires.
        # (Activity log inspection isn't easy here — we rely on the pre/post-archived
        # gates in update_spool. The wiring test covers the happy paths above.)
