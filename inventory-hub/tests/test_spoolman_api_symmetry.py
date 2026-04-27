"""Unit tests for the Phase B symmetry + helper API on `spoolman_api`.

These tests use mocked HTTP (no real Spoolman) and pin the contract:
  - update_spool AND update_filament both populate LAST_SPOOLMAN_ERROR
    on rejection (the pre-fix asymmetry was the root of the multi-hour
    2026-04-27 outage diagnosis lag — only update_filament populated it).
  - Both clear LAST_SPOOLMAN_ERROR to None on success.
  - The _or_raise variants raise SpoolmanRejection on None and pass
    through on success.
  - compute_dirty_extras strips system-managed keys regardless of value
    and only diffs the rest.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

import spoolman_api


def _mock_response(ok: bool, status_code: int = 400, text: str = "validation error",
                   json_body: dict | None = None) -> MagicMock:
    """Build a minimal requests.Response stand-in for unit tests."""
    m = MagicMock()
    m.ok = ok
    m.status_code = status_code if not ok else 200
    m.text = text
    m.json = MagicMock(return_value=json_body or {})
    return m


# ---------------------------------------------------------------------------
# update_spool / update_filament symmetry — Phase B.1
# ---------------------------------------------------------------------------

class TestUpdateSpoolErrorSymmetry:
    """update_spool must populate LAST_SPOOLMAN_ERROR on every failure
    code path so callers can surface the rejection reason. Pre-fix only
    update_filament did this."""

    def setup_method(self):
        spoolman_api.LAST_SPOOLMAN_ERROR = None

    def test_http_400_populates_error_with_status_and_body(self):
        with patch.object(spoolman_api, "get_spool", return_value={"id": 1}), \
             patch.object(spoolman_api, "_get_raw_extras", return_value={}), \
             patch.object(spoolman_api.requests, "patch",
                          return_value=_mock_response(ok=False, status_code=400, text="Unknown extra field")):
            result = spoolman_api.update_spool(1, {"extra": {"x": "y"}})
        assert result is None
        assert spoolman_api.LAST_SPOOLMAN_ERROR is not None
        assert "HTTP 400" in spoolman_api.LAST_SPOOLMAN_ERROR
        assert "Unknown extra field" in spoolman_api.LAST_SPOOLMAN_ERROR

    def test_transport_exception_populates_error_with_message(self):
        import requests as _r
        with patch.object(spoolman_api, "get_spool", return_value={"id": 1}), \
             patch.object(spoolman_api.requests, "patch",
                          side_effect=_r.RequestException("boom — connection refused")):
            result = spoolman_api.update_spool(1, {"used_weight": 5})
        assert result is None
        assert spoolman_api.LAST_SPOOLMAN_ERROR is not None
        assert "boom" in spoolman_api.LAST_SPOOLMAN_ERROR

    def test_success_clears_error_to_none(self):
        spoolman_api.LAST_SPOOLMAN_ERROR = "stale prior failure"
        with patch.object(spoolman_api, "get_spool", return_value={"id": 1}), \
             patch.object(spoolman_api.requests, "patch",
                          return_value=_mock_response(ok=True, json_body={"id": 1})):
            result = spoolman_api.update_spool(1, {"used_weight": 5})
        assert result == {"id": 1}
        assert spoolman_api.LAST_SPOOLMAN_ERROR is None


class TestUpdateFilamentErrorSymmetry:
    """update_filament has always populated LAST_SPOOLMAN_ERROR — pin it
    so a future refactor doesn't accidentally regress."""

    def setup_method(self):
        spoolman_api.LAST_SPOOLMAN_ERROR = None

    def test_http_400_populates_error(self):
        with patch.object(spoolman_api.requests, "patch",
                          return_value=_mock_response(ok=False, status_code=422, text="Some Spoolman complaint")):
            result = spoolman_api.update_filament(99, {"name": "Test"})
        assert result is None
        assert spoolman_api.LAST_SPOOLMAN_ERROR is not None
        assert "HTTP 422" in spoolman_api.LAST_SPOOLMAN_ERROR
        assert "Some Spoolman complaint" in spoolman_api.LAST_SPOOLMAN_ERROR

    def test_success_clears_error_to_none(self):
        spoolman_api.LAST_SPOOLMAN_ERROR = "stale prior failure"
        with patch.object(spoolman_api.requests, "patch",
                          return_value=_mock_response(ok=True, json_body={"id": 99})):
            result = spoolman_api.update_filament(99, {"name": "Test"})
        assert result == {"id": 99}
        assert spoolman_api.LAST_SPOOLMAN_ERROR is None


# ---------------------------------------------------------------------------
# _or_raise variants — Phase B.2
# ---------------------------------------------------------------------------

class TestOrRaiseVariants:
    """update_spool_or_raise / update_filament_or_raise must raise
    SpoolmanRejection (carrying LAST_SPOOLMAN_ERROR) when the inner call
    returns None, and pass through the result otherwise."""

    def setup_method(self):
        spoolman_api.LAST_SPOOLMAN_ERROR = None

    def test_update_spool_or_raise_raises_on_failure(self):
        with patch.object(spoolman_api, "update_spool", return_value=None):
            spoolman_api.LAST_SPOOLMAN_ERROR = "HTTP 400: invalid field"
            with pytest.raises(spoolman_api.SpoolmanRejection) as excinfo:
                spoolman_api.update_spool_or_raise(1, {"used_weight": 5})
        assert "HTTP 400" in str(excinfo.value)

    def test_update_spool_or_raise_passes_through_on_success(self):
        with patch.object(spoolman_api, "update_spool", return_value={"id": 1}):
            result = spoolman_api.update_spool_or_raise(1, {"used_weight": 5})
        assert result == {"id": 1}

    def test_update_filament_or_raise_raises_on_failure(self):
        with patch.object(spoolman_api, "update_filament", return_value=None):
            spoolman_api.LAST_SPOOLMAN_ERROR = "HTTP 422: rejected"
            with pytest.raises(spoolman_api.SpoolmanRejection) as excinfo:
                spoolman_api.update_filament_or_raise(99, {"name": "T"})
        assert "HTTP 422" in str(excinfo.value)

    def test_update_filament_or_raise_passes_through_on_success(self):
        with patch.object(spoolman_api, "update_filament", return_value={"id": 99}):
            result = spoolman_api.update_filament_or_raise(99, {"name": "T"})
        assert result == {"id": 99}

    def test_spoolman_rejection_falls_back_to_default_message(self):
        spoolman_api.LAST_SPOOLMAN_ERROR = None
        exc = spoolman_api.SpoolmanRejection()
        assert "Spoolman rejected" in str(exc)


# ---------------------------------------------------------------------------
# compute_dirty_extras helper — Phase F.1 / D.3
# ---------------------------------------------------------------------------

class TestComputeDirtyExtras:
    def test_returns_only_changed_keys(self):
        existing = {"a": "1", "b": "2", "c": "3"}
        requested = {"a": "1", "b": "BBB", "c": "3"}
        dirty, stripped = spoolman_api.compute_dirty_extras(existing, requested)
        assert dirty == {"b": "BBB"}
        assert stripped == []

    def test_string_comparison_matches_parsed_and_wire_form(self):
        # parse_inbound_data unwraps `"1"` → 1 (int); the string
        # comparison in compute_dirty_extras must treat them as equal so
        # a no-op wizard save doesn't trigger a spurious PATCH.
        existing = {"used_weight": 1}      # parsed form (int)
        requested = {"used_weight": "1"}    # wire form (str)
        dirty, _ = spoolman_api.compute_dirty_extras(existing, requested)
        assert dirty == {}

    def test_strips_system_managed_keys_unconditionally(self):
        existing = {"container_slot": "XL-1", "purchase_url": "before"}
        # The wizard tries to write container_slot="" (clobbering the slot
        # assignment) plus a legitimate purchase_url change. The guard
        # must drop container_slot regardless of value, AND must strip
        # it BEFORE comparing — even if requested matches existing.
        requested = {"container_slot": "", "purchase_url": "after"}
        dirty, stripped = spoolman_api.compute_dirty_extras(
            existing, requested,
            system_managed=spoolman_api.SYSTEM_MANAGED_EXTRAS,
        )
        assert dirty == {"purchase_url": "after"}
        assert "container_slot" in stripped

    def test_strips_all_three_system_managed_keys(self):
        existing = {}
        requested = {
            "container_slot": "X",
            "physical_source": "Y",
            "physical_source_slot": "Z",
            "purchase_url": "W",
        }
        dirty, stripped = spoolman_api.compute_dirty_extras(
            existing, requested,
            system_managed=spoolman_api.SYSTEM_MANAGED_EXTRAS,
        )
        assert set(stripped) == {"container_slot", "physical_source", "physical_source_slot"}
        assert dirty == {"purchase_url": "W"}

    def test_handles_none_inputs_gracefully(self):
        dirty, stripped = spoolman_api.compute_dirty_extras(None, None)
        assert dirty == {}
        assert stripped == []

    def test_default_system_managed_is_empty(self):
        # When no system_managed set is passed, no keys are stripped.
        existing = {"a": "1"}
        requested = {"a": "2", "container_slot": "XL-1"}
        dirty, stripped = spoolman_api.compute_dirty_extras(existing, requested)
        assert dirty == {"a": "2", "container_slot": "XL-1"}
        assert stripped == []


# ---------------------------------------------------------------------------
# SYSTEM_MANAGED_EXTRAS constant — Phase D
# ---------------------------------------------------------------------------

class TestSystemManagedExtrasConstant:
    """Pin the exact membership so a future commit doesn't accidentally
    add / remove a key without a deliberate review. The bug behind Item 4
    in Feature-Buglist was the wizard writing one of these directly."""

    def test_contains_all_three_canonical_keys(self):
        assert "container_slot" in spoolman_api.SYSTEM_MANAGED_EXTRAS
        assert "physical_source" in spoolman_api.SYSTEM_MANAGED_EXTRAS
        assert "physical_source_slot" in spoolman_api.SYSTEM_MANAGED_EXTRAS

    def test_is_a_frozenset(self):
        # frozenset prevents accidental mutation at runtime.
        assert isinstance(spoolman_api.SYSTEM_MANAGED_EXTRAS, frozenset)
