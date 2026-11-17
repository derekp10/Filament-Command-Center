"""create_filament and create_spool say why Spoolman refused them (Group 53.2).

/api/create_filament answers a refused create with spoolman_api.LAST_SPOOLMAN_ERROR
(28.B4), but create_filament never set it, and neither did create_spool: a
refusal answered whatever an earlier, unrelated write had left there, or the
generic "Spoolman rejected the filament create." The 28.B4 test stubbed
create_filament out and set the error by hand, so it never saw that. Both
helpers now set it on a refusal and clear it on success, as create_vendor,
update_* and delete_* do. Found by the Group 53.2 write-site review.

The real helpers and the real route, with only Spoolman's HTTP answer faked.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app  # noqa: E402
import spoolman_api  # noqa: E402

STALE = "HTTP 500: an earlier, unrelated write's refusal"
REFUSAL_BODY = '{"message": "Unknown extra field \'colour_code\'"}'


@pytest.fixture()
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def stale_error(monkeypatch):
    """An earlier write's refusal is still in the global, as in the running app."""
    monkeypatch.setattr(spoolman_api, 'LAST_SPOOLMAN_ERROR', STALE)


def _answer(status, body_text, body=None):
    m = MagicMock()
    m.ok = 200 <= status < 400
    m.status_code = status
    m.text = body_text
    m.json = MagicMock(return_value=body)
    return m


def test_a_refused_filament_create_answers_its_own_refusal(client):
    with patch('spoolman_api.requests.post', return_value=_answer(400, REFUSAL_BODY)):
        r = client.post('/api/create_filament', json={'data': {'material': 'PLA', 'name': 'X'}})
    assert r.status_code == 500
    body = r.get_json()
    assert body['success'] is False
    assert body['msg'] == f'HTTP 400: {REFUSAL_BODY}'


@pytest.mark.parametrize('create, data', [
    (spoolman_api.create_filament, {'material': 'PLA', 'name': 'X'}),
    (spoolman_api.create_spool, {'filament_id': 1}),
])
def test_a_refused_create_sets_the_error(create, data):
    with patch('spoolman_api.requests.post', return_value=_answer(400, REFUSAL_BODY)):
        assert create(dict(data)) is None
    assert spoolman_api.LAST_SPOOLMAN_ERROR == f'HTTP 400: {REFUSAL_BODY}'


@pytest.mark.parametrize('create, data', [
    (spoolman_api.create_filament, {'material': 'PLA', 'name': 'X'}),
    (spoolman_api.create_spool, {'filament_id': 1}),
])
def test_a_create_that_fails_to_send_sets_the_error(create, data):
    with patch('spoolman_api.requests.post', side_effect=OSError('connection refused')):
        assert create(dict(data)) is None
    assert spoolman_api.LAST_SPOOLMAN_ERROR == 'connection refused'


@pytest.mark.parametrize('create, data', [
    (spoolman_api.create_filament, {'material': 'PLA', 'name': 'X'}),
    (spoolman_api.create_spool, {'filament_id': 1}),
])
def test_a_create_that_lands_clears_the_error(create, data):
    with patch('spoolman_api.requests.post', return_value=_answer(200, '{"id": 5}', {'id': 5})):
        assert create(dict(data)) == {'id': 5}
    assert spoolman_api.LAST_SPOOLMAN_ERROR is None
