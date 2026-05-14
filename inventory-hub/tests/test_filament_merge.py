"""Tests for the filament merge endpoint (Group 11.2).

Covers POST /api/filament/<src>/merge_into/<dst>:
  - Source == target is rejected.
  - Source / target not found are rejected.
  - Happy path re-parents every child spool, then deletes source.
  - Partial re-parent failure aborts before deleting source (atomic-ish).
  - Source-delete failure after successful re-parents is reported.

Mocked Spoolman — no real HTTP. The endpoint enumerates children via direct
`requests.get` (not `get_spools_for_filament`, so it can include archived),
then calls `update_spool_or_raise` per spool, then `delete_filament`.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app
import spoolman_api


@pytest.fixture()
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def _ok_json(payload):
    m = MagicMock()
    m.ok = True
    m.status_code = 200
    m.json = MagicMock(return_value=payload)
    return m


class TestMergeFilament:
    def test_rejects_same_source_and_target(self, client):
        r = client.post('/api/filament/7/merge_into/7')
        assert r.status_code == 400
        body = r.get_json()
        assert body['success'] is False
        assert 'differ' in body['error'].lower()

    def test_rejects_missing_source(self, client):
        with patch('spoolman_api.get_filament', side_effect=[None]):
            r = client.post('/api/filament/7/merge_into/9')
        assert r.status_code == 404
        body = r.get_json()
        assert body['success'] is False
        assert '#7' in body['error']

    def test_rejects_missing_target(self, client):
        # Source resolves, target returns None.
        with patch('spoolman_api.get_filament', side_effect=[{'id': 7, 'name': 'src'}, None]):
            r = client.post('/api/filament/7/merge_into/9')
        assert r.status_code == 404
        body = r.get_json()
        assert body['success'] is False
        assert '#9' in body['error']

    def test_happy_path_reparents_and_deletes_source(self, client):
        src = {'id': 7, 'name': 'PLA Old'}
        dst = {'id': 9, 'name': 'PLA New'}
        children = [{'id': 101}, {'id': 102}, {'id': 103}]

        with patch('spoolman_api.get_filament', side_effect=[src, dst]), \
             patch('app.requests.get', return_value=_ok_json(children)), \
             patch('spoolman_api.update_spool_or_raise', return_value={'id': 'ok'}) as mock_upd, \
             patch('spoolman_api.delete_filament', return_value=True) as mock_del:
            r = client.post('/api/filament/7/merge_into/9')

        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True
        assert body['source_filament_id'] == 7
        assert body['target_filament_id'] == 9
        assert body['reparented_spool_ids'] == [101, 102, 103]
        # Each child should have been re-parented onto filament 9.
        assert mock_upd.call_count == 3
        for call in mock_upd.call_args_list:
            args, _kwargs = call
            assert args[1] == {'filament_id': 9}
        mock_del.assert_called_once_with(7)

    def test_partial_reparent_failure_aborts_without_deleting_source(self, client):
        src = {'id': 7, 'name': 'src'}
        dst = {'id': 9, 'name': 'dst'}
        children = [{'id': 101}, {'id': 102}]

        def upd_side_effect(sid, data):
            if sid == 102:
                raise spoolman_api.SpoolmanRejection("HTTP 409: cannot reassign")
            return {'id': sid}

        with patch('spoolman_api.get_filament', side_effect=[src, dst]), \
             patch('app.requests.get', return_value=_ok_json(children)), \
             patch('spoolman_api.update_spool_or_raise', side_effect=upd_side_effect), \
             patch('spoolman_api.delete_filament') as mock_del:
            r = client.post('/api/filament/7/merge_into/9')

        assert r.status_code == 502
        body = r.get_json()
        assert body['success'] is False
        assert 'left in place' in body['error']
        assert body['reparented_spool_ids'] == [101]
        assert len(body['spool_errors']) == 1
        assert body['spool_errors'][0]['spool_id'] == 102
        # Critically: source filament must NOT be deleted when any spool fails.
        mock_del.assert_not_called()

    def test_source_delete_failure_after_full_reparent_is_reported(self, client):
        src = {'id': 7, 'name': 'src'}
        dst = {'id': 9, 'name': 'dst'}
        children = [{'id': 101}]

        spoolman_api.LAST_SPOOLMAN_ERROR = "HTTP 500: db locked"
        with patch('spoolman_api.get_filament', side_effect=[src, dst]), \
             patch('app.requests.get', return_value=_ok_json(children)), \
             patch('spoolman_api.update_spool_or_raise', return_value={'id': 101}), \
             patch('spoolman_api.delete_filament', return_value=False):
            r = client.post('/api/filament/7/merge_into/9')

        assert r.status_code == 502
        body = r.get_json()
        assert body['success'] is False
        assert 'db locked' in body['error']
        assert body['reparented_spool_ids'] == [101]

    def test_zero_children_still_deletes_source(self, client):
        # Edge: orphan filament with no spools at all — merge is essentially
        # a rename + delete, but the endpoint should still succeed cleanly.
        src = {'id': 7, 'name': 'src'}
        dst = {'id': 9, 'name': 'dst'}
        with patch('spoolman_api.get_filament', side_effect=[src, dst]), \
             patch('app.requests.get', return_value=_ok_json([])), \
             patch('spoolman_api.update_spool_or_raise') as mock_upd, \
             patch('spoolman_api.delete_filament', return_value=True) as mock_del:
            r = client.post('/api/filament/7/merge_into/9')

        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True
        assert body['reparented_spool_ids'] == []
        mock_upd.assert_not_called()
        mock_del.assert_called_once_with(7)
