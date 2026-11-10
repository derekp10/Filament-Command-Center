"""A refused field-list read in update_extra_field_choices (Group 53.2).

update_extra_field_choices reads the field list (GET /api/v1/field/<entity>),
then POSTs the field back with the new choice added. When Spoolman refused that
read, the function fell off the end of its `if r.ok:` block and returned None,
which neither caller can read: /api/filament_attributes/add_choice called
`.get` on it (a 500), and /api/external/fields/add_choice answered `null`, which
the wizard read as "HTTP 200" or as a TypeError. It now answers
{"success": False, "msg": ...} and writes nothing, as its other failures do.
Found by the Group 53.2 write-site review.

The real helper and the real routes, with only Spoolman's HTTP answers faked.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app  # noqa: E402
import spoolman_api  # noqa: E402

REFUSED_MSG = "Spoolman's field list answered HTTP 503, so no choice was added."


@pytest.fixture()
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def _refused_field_list():
    m = MagicMock()
    m.ok = False
    m.status_code = 503
    m.text = '{"message": "Service Unavailable"}'
    m.json = MagicMock(return_value={"message": "Service Unavailable"})
    return m


def test_a_refused_field_list_read_answers_a_failure_and_writes_nothing():
    with patch('spoolman_api.requests.get', return_value=_refused_field_list()), \
         patch('spoolman_api.requests.post') as post:
        res = spoolman_api.update_extra_field_choices('filament', 'filament_attributes', ['Silk'])
    assert res == {"success": False, "msg": REFUSED_MSG}
    post.assert_not_called()


def test_the_attributes_manager_says_why_instead_of_a_500(client):
    with patch('spoolman_api.requests.get', return_value=_refused_field_list()), \
         patch('spoolman_api.requests.post') as post:
        r = client.post('/api/filament_attributes/add_choice', json={'choice': 'Silk'})
    assert r.status_code == 200
    assert r.get_json() == {"success": False, "msg": REFUSED_MSG}
    post.assert_not_called()


def test_the_wizard_add_choice_says_why_instead_of_null(client):
    with patch('spoolman_api.requests.get', return_value=_refused_field_list()), \
         patch('spoolman_api.requests.post') as post:
        r = client.post('/api/external/fields/add_choice', json={
            'entity_type': 'filament', 'key': 'filament_attributes', 'new_choice': 'Silk',
        })
    assert r.status_code == 200
    assert r.get_json() == {"success": False, "msg": REFUSED_MSG}
    post.assert_not_called()
