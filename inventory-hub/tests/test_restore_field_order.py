"""L318 — Spoolman field-order restore endpoint.

`POST /api/spoolman/restore_field_order` writes FIELD_ORDER's canonical
index back into each Spoolman field's `order` property so the Spoolman
UI renders extras in the same sequence FCC's wizard / details modal do.

Spoolman's `POST /api/v1/field/{entity}/{key}` is an upsert — sending
only `order` would clobber name / field_type / choices to defaults, so
the endpoint GETs each field first, splices in the new order, and POSTs
the full payload back. These tests pin that contract.
"""
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _make_app():
    """Fresh Flask test client with the real app module wired up."""
    from app import app as flask_app
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


def _fake_field_response(fields):
    r = MagicMock()
    r.ok = True
    r.json.return_value = fields
    return r


def test_restore_field_order_skips_fields_already_in_position():
    """If a Spoolman field's order already matches its canonical index,
    the endpoint must skip the POST round-trip entirely (idempotent
    re-run is a no-op)."""
    fil_fields = [
        # filament_attributes is at index 0 in FIELD_ORDER["filament"];
        # the field reports order=0, so no write needed.
        {"key": "filament_attributes", "name": "Attributes",
         "field_type": "choice", "choices": ["Matte"], "order": 0},
    ]
    spool_fields = []  # nothing to do for spool side

    def fake_get(url, timeout=10):
        if "/field/filament" in url:
            return _fake_field_response(fil_fields)
        if "/field/spool" in url:
            return _fake_field_response(spool_fields)
        return MagicMock(ok=False, status_code=404)

    with patch("app.config_loader.get_api_urls",
               return_value=("http://spoolman", "http://fb")), \
         patch("app.requests.get", side_effect=fake_get), \
         patch("app.requests.post") as mock_post:
        client = _make_app()
        res = client.post('/api/spoolman/restore_field_order')

    data = res.get_json()
    assert data['success'] is True
    assert data['summary']['filament']['updated'] == 0
    assert data['summary']['filament']['skipped'] == 1
    # No POSTs because nothing needed updating.
    mock_post.assert_not_called()


def test_restore_field_order_writes_canonical_index_when_drift_present():
    """When a field's order doesn't match its canonical index, the
    endpoint POSTs an upsert with the new order AND echoes every other
    property the GET returned (name, field_type, choices, etc.) so the
    upsert doesn't clobber them to defaults."""
    fil_fields = [
        {"key": "slicer_profile", "name": "Slicer Profile",
         "field_type": "choice", "choices": ["A", "B"],
         "multi_choice": False, "order": 0},  # canonical is index 2
    ]

    def fake_get(url, timeout=10):
        if "/field/filament" in url:
            return _fake_field_response(fil_fields)
        if "/field/spool" in url:
            return _fake_field_response([])
        return MagicMock(ok=False, status_code=404)

    post_calls = []

    def fake_post(url, json=None, timeout=10):
        post_calls.append((url, json))
        m = MagicMock()
        m.ok = True
        return m

    with patch("app.config_loader.get_api_urls",
               return_value=("http://spoolman", "http://fb")), \
         patch("app.requests.get", side_effect=fake_get), \
         patch("app.requests.post", side_effect=fake_post):
        client = _make_app()
        res = client.post('/api/spoolman/restore_field_order')

    data = res.get_json()
    assert data['success'] is True
    assert data['summary']['filament']['updated'] == 1
    assert len(post_calls) == 1
    url, body = post_calls[0]
    assert "/field/filament/slicer_profile" in url
    # FIELD_ORDER["filament"] indexes slicer_profile at 2.
    assert body['order'] == 2
    # Critical: all the other ExtraFieldParameters props get echoed
    # back so the upsert doesn't clobber them.
    assert body['name'] == "Slicer Profile"
    assert body['field_type'] == "choice"
    assert body['choices'] == ["A", "B"]
    assert body['multi_choice'] is False


def test_restore_field_order_skips_unknown_keys():
    """Fields not in FIELD_ORDER must pass through untouched — no POST,
    no order written. Otherwise an unknown field would be permanently
    relocated to position 0."""
    fil_fields = [
        {"key": "some_external_field_we_dont_own", "name": "External",
         "field_type": "text", "order": 5},
    ]

    def fake_get(url, timeout=10):
        if "/field/filament" in url:
            return _fake_field_response(fil_fields)
        if "/field/spool" in url:
            return _fake_field_response([])
        return MagicMock(ok=False, status_code=404)

    with patch("app.config_loader.get_api_urls",
               return_value=("http://spoolman", "http://fb")), \
         patch("app.requests.get", side_effect=fake_get), \
         patch("app.requests.post") as mock_post:
        client = _make_app()
        res = client.post('/api/spoolman/restore_field_order')

    data = res.get_json()
    assert data['success'] is True
    assert data['summary']['filament']['updated'] == 0
    assert data['summary']['filament']['skipped'] == 1
    mock_post.assert_not_called()


def test_restore_field_order_surfaces_spoolman_errors():
    """When Spoolman returns 4xx on a write, the endpoint must surface
    the error body in the summary so the caller can see what failed
    (and not silently report success=true)."""
    fil_fields = [
        {"key": "slicer_profile", "name": "Slicer Profile",
         "field_type": "choice", "choices": ["A"], "order": 0},
    ]

    def fake_get(url, timeout=10):
        if "/field/filament" in url:
            return _fake_field_response(fil_fields)
        if "/field/spool" in url:
            return _fake_field_response([])
        return MagicMock(ok=False, status_code=404)

    def fake_post(url, json=None, timeout=10):
        m = MagicMock()
        m.ok = False
        m.status_code = 400
        m.text = "Bad Request: invalid order"
        return m

    with patch("app.config_loader.get_api_urls",
               return_value=("http://spoolman", "http://fb")), \
         patch("app.requests.get", side_effect=fake_get), \
         patch("app.requests.post", side_effect=fake_post):
        client = _make_app()
        res = client.post('/api/spoolman/restore_field_order')

    data = res.get_json()
    # Errors → success=false so callers can branch on it.
    assert data['success'] is False
    assert data['summary']['filament']['updated'] == 0
    errs = data['summary']['filament']['errors']
    assert len(errs) == 1
    assert "slicer_profile" in errs[0]
    assert "400" in errs[0]
