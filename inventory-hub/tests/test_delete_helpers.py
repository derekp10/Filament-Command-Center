"""Unit tests for `delete_spool`, `delete_filament`, and
`get_spools_for_filament` in `spoolman_api`.

Mocked HTTP — no real Spoolman. Verifies the contract:
  - Both delete helpers return True on success / False on failure.
  - LAST_SPOOLMAN_ERROR is populated on every failure path with the
    Spoolman rejection body, and cleared to None on success.
  - get_spools_for_filament filters by nested filament.id correctly
    and tolerates malformed entries.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import spoolman_api as sm


def _resp(ok: bool, status: int = 200, text: str = "ok") -> MagicMock:
    m = MagicMock()
    m.ok = ok
    m.status_code = status if not ok else 200
    m.text = text
    return m


class TestDeleteSpool:
    def test_success_returns_true_clears_error(self):
        sm.LAST_SPOOLMAN_ERROR = "stale"
        with patch("spoolman_api.requests.delete", return_value=_resp(True)):
            result = sm.delete_spool(42)
        assert result is True
        assert sm.LAST_SPOOLMAN_ERROR is None

    def test_http_failure_returns_false_populates_error(self):
        with patch("spoolman_api.requests.delete",
                   return_value=_resp(False, status=409, text="spool has dependencies")):
            result = sm.delete_spool(42)
        assert result is False
        assert "409" in sm.LAST_SPOOLMAN_ERROR
        assert "dependencies" in sm.LAST_SPOOLMAN_ERROR

    def test_transport_exception_returns_false_with_message(self):
        with patch("spoolman_api.requests.delete",
                   side_effect=Exception("connection refused")):
            result = sm.delete_spool(42)
        assert result is False
        assert "connection refused" in sm.LAST_SPOOLMAN_ERROR


class TestDeleteFilament:
    def test_success_returns_true_clears_error(self):
        sm.LAST_SPOOLMAN_ERROR = "stale"
        with patch("spoolman_api.requests.delete", return_value=_resp(True)):
            result = sm.delete_filament(7)
        assert result is True
        assert sm.LAST_SPOOLMAN_ERROR is None

    def test_http_failure_populates_error_body(self):
        with patch("spoolman_api.requests.delete",
                   return_value=_resp(False, status=409, text="filament has child spools")):
            result = sm.delete_filament(7)
        assert result is False
        assert "child spools" in sm.LAST_SPOOLMAN_ERROR

    def test_transport_exception(self):
        with patch("spoolman_api.requests.delete",
                   side_effect=Exception("timeout")):
            result = sm.delete_filament(7)
        assert result is False
        assert "timeout" in sm.LAST_SPOOLMAN_ERROR


class TestGetSpoolsForFilament:
    def test_filters_by_nested_filament_id(self):
        api_spools = [
            {"id": 1, "filament": {"id": 7, "name": "PLA"}},
            {"id": 2, "filament": {"id": 8, "name": "PETG"}},
            {"id": 3, "filament": {"id": 7, "name": "PLA"}},
        ]
        resp = MagicMock()
        resp.ok = True
        resp.json = MagicMock(return_value=api_spools)
        with patch("spoolman_api.requests.get", return_value=resp):
            result = sm.get_spools_for_filament(7)
        assert [s["id"] for s in result] == [1, 3]

    def test_returns_empty_for_no_matches(self):
        resp = MagicMock()
        resp.ok = True
        resp.json = MagicMock(return_value=[
            {"id": 1, "filament": {"id": 99}},
        ])
        with patch("spoolman_api.requests.get", return_value=resp):
            result = sm.get_spools_for_filament(7)
        assert result == []

    def test_tolerates_missing_filament_block(self):
        resp = MagicMock()
        resp.ok = True
        resp.json = MagicMock(return_value=[
            {"id": 1},  # malformed entry, no filament block at all
            {"id": 2, "filament": {"id": 7}},
        ])
        with patch("spoolman_api.requests.get", return_value=resp):
            result = sm.get_spools_for_filament(7)
        assert [s["id"] for s in result] == [2]

    def test_returns_empty_on_http_failure(self):
        resp = MagicMock()
        resp.ok = False
        with patch("spoolman_api.requests.get", return_value=resp):
            result = sm.get_spools_for_filament(7)
        assert result == []

    def test_returns_empty_on_transport_exception(self):
        with patch("spoolman_api.requests.get",
                   side_effect=Exception("network down")):
            result = sm.get_spools_for_filament(7)
        assert result == []
