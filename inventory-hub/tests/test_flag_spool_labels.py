"""Tests for the 23.3 follow-up POST /api/filament/<id>/flag_spool_labels.

A filament edit that changes a SPOOL-label-visible field (Brand/Type/Color-name)
flags the filament's UNARCHIVED spools' needs_label_print so the now-stale spool
labels surface in spool details + the print queue. Hex/RGB-only changes never
reach this endpoint (the frontend excludes them — hex isn't on the spool label).
"""
from __future__ import annotations

import sys
import os
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app
import spoolman_api


@pytest.fixture()
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def test_flags_unarchived_skips_archived(client):
    spools = [
        {'id': 1, 'archived': False},
        {'id': 2, 'archived': True},
        {'id': 3, 'archived': False},
    ]
    calls = []

    def _upd(sid, data):
        calls.append((sid, data))
        return {'id': sid}

    with patch.object(spoolman_api, 'get_spools_for_filament', return_value=spools), \
         patch.object(spoolman_api, 'update_spool', side_effect=_upd), \
         patch('app.state.add_log_entry'):
        r = client.post('/api/filament/42/flag_spool_labels')

    body = r.get_json()
    assert body['success'] is True
    assert sorted(body['flagged']) == [1, 3]
    assert body['errors'] == []
    # archived spool #2 not touched; unarchived flagged with a PARTIAL extra
    # (merge preserves siblings).
    assert {sid for sid, _ in calls} == {1, 3}
    for _sid, data in calls:
        assert data == {'extra': {'needs_label_print': True}}


def test_reports_per_spool_failure(client):
    spools = [{'id': 1, 'archived': False}, {'id': 2, 'archived': False}]

    def _upd(sid, data):
        return None if sid == 2 else {'id': sid}

    with patch.object(spoolman_api, 'get_spools_for_filament', return_value=spools), \
         patch.object(spoolman_api, 'update_spool', side_effect=_upd), \
         patch.object(spoolman_api, 'LAST_SPOOLMAN_ERROR', 'boom'), \
         patch('app.state.add_log_entry'):
        r = client.post('/api/filament/42/flag_spool_labels')

    body = r.get_json()
    assert body['success'] is True
    assert body['flagged'] == [1]
    assert len(body['errors']) == 1 and body['errors'][0]['id'] == 2


def test_passes_int_filament_id_to_lookup(client):
    captured = {}

    def _get(fid):
        captured['fid'] = fid
        return []

    with patch.object(spoolman_api, 'get_spools_for_filament', side_effect=_get), \
         patch('app.state.add_log_entry'):
        r = client.post('/api/filament/42/flag_spool_labels')

    assert r.get_json()['success'] is True
    assert captured['fid'] == 42  # int — matches Spoolman's filament.id type


def test_invalid_filament_id_rejected(client):
    r = client.post('/api/filament/not-a-number/flag_spool_labels')
    assert r.get_json()['success'] is False
