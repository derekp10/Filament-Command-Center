"""L316 characterization tests — pins pre-carve behavior of the deduct-seam
read/aggregate endpoints (app.py:4093-4232). Generated from the 2026-07-01
coverage audit. Do not weaken these to make a refactor pass.

Covers, with NO live server and NO live Spoolman (everything mocked):

  1. GET /api/get_multi_spool_filaments — archived-spool skip, filament-id
     grouping (first-spool-wins metadata), count>1 filter, the
     {id, display, count, spool_ids} response shape, the "Vendor - Name"
     display fallbacks, and the swallow-everything-to-[] error contract.
  2. POST /api/backfill_spool_weights/<fid> — filament-over-vendor weight
     inheritance, the exact per-spool PATCH payload ({'spool_weight': target}
     only), archived spools included, per-spool failure collected into
     errors[] while the loop continues, the 400/404/502/500 taxonomy, and the
     empty-filament (no spools) case.

These complement tests/test_backfill_spool_weights.py, which exercises the
same endpoint against LIVE dev FCC + Spoolman (and silently skips offline);
this file is the offline tripwire for the app.py modularization carve.

House style: module-level `import app as app_module`, Flask test_client,
pytest monkeypatch against app_module.spoolman_api / app_module.requests.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app as app_module  # noqa: E402


def _client():
    app_module.app.config['TESTING'] = True
    return app_module.app.test_client()


def _mock_urls(monkeypatch):
    """Pin the Spoolman base URL so the outbound-request URL is assertable."""
    monkeypatch.setattr(
        app_module.config_loader, 'get_api_urls',
        lambda: ('http://mock', 'http://mock'),
    )


def _fake_requests_get(monkeypatch, payload, ok=True):
    """Replace app-module requests.get with a recorder returning one canned
    response. Returns the recorder list of (args, kwargs) tuples."""
    calls = []
    resp = MagicMock()
    resp.ok = ok
    resp.json.return_value = payload

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return resp

    monkeypatch.setattr(app_module.requests, 'get', fake_get)
    return calls


def _capture_logger(monkeypatch):
    mock_logger = MagicMock()
    monkeypatch.setattr(app_module.state, 'logger', mock_logger)
    return mock_logger


def _spool(sid, fid, name='Blue', vendor='Acme', archived=False):
    """Spoolman /api/v1/spool list entry, trimmed to the fields the
    multi-spool aggregation reads."""
    return {
        'id': sid,
        'archived': archived,
        'filament': {'id': fid, 'name': name, 'vendor': {'name': vendor}},
    }


# ---------------------------------------------------------------------------
# GET /api/get_multi_spool_filaments
# ---------------------------------------------------------------------------

def test_multi_spool_grouping_count_filter_and_shape(monkeypatch):
    """Pins the core aggregation: archived spools skipped (even when they are
    the FIRST spool of a filament — metadata must come from the first
    UNARCHIVED spool), spools without a filament id skipped, non-dict list
    entries skipped, single-spool filaments filtered out (count>1 only), and
    the exact {id, display, count, spool_ids} candidate shape. Also pins the
    outbound Spoolman URL + timeout so a moved module can't silently point at
    the wrong base URL."""
    _mock_urls(monkeypatch)
    calls = _fake_requests_get(monkeypatch, [
        # Archived spool FIRST for fid 7 — must not seed name/vendor metadata.
        _spool(999, 7, name='Zombie', vendor='Dead', archived=True),
        _spool(101, 7, name='Galaxy Black', vendor='Prusament'),
        # Same filament id, different (stale) metadata — first-unarchived wins.
        _spool(102, 7, name='DIFFERENT', vendor='Other'),
        # No filament id → skipped entirely.
        {'id': 104, 'archived': False, 'filament': {}},
        # Only one spool for fid 5 → filtered out by the count>1 rule.
        _spool(105, 5, name='Lonely', vendor='Solo'),
        # Non-dict entry → skipped.
        'junk-string-entry',
    ])

    res = _client().get('/api/get_multi_spool_filaments')
    assert res.status_code == 200
    body = res.get_json()

    assert body == [{
        'id': 7,
        'display': 'Prusament - Galaxy Black',
        'count': 2,
        'spool_ids': [101, 102],
    }]

    # Outbound fetch: full unfiltered spool list, 10s timeout.
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ('http://mock/api/v1/spool',)
    assert kwargs.get('timeout') == 10


def test_multi_spool_display_fallbacks(monkeypatch):
    """Pins the 'Vendor - Name'.strip(' -') display fallbacks: vendor-less
    filament shows just the name, name-less shows just the vendor, and a
    filament with neither shows the empty string (not ' - ')."""
    _mock_urls(monkeypatch)
    _fake_requests_get(monkeypatch, [
        # fid 5: no vendor key at all.
        {'id': 1, 'archived': False, 'filament': {'id': 5, 'name': 'Blue'}},
        {'id': 2, 'archived': False, 'filament': {'id': 5, 'name': 'Blue'}},
        # fid 6: neither name nor vendor.
        {'id': 3, 'archived': False, 'filament': {'id': 6}},
        {'id': 4, 'archived': False, 'filament': {'id': 6}},
        # fid 8: vendor but empty name.
        _spool(5, 8, name='', vendor='Acme'),
        _spool(6, 8, name='', vendor='Acme'),
    ])

    body = _client().get('/api/get_multi_spool_filaments').get_json()
    by_id = {c['id']: c for c in body}
    assert set(by_id) == {5, 6, 8}
    assert by_id[5]['display'] == 'Blue'
    assert by_id[6]['display'] == ''
    assert by_id[8]['display'] == 'Acme'


def test_multi_spool_display_preserves_content_hyphens(monkeypatch):
    """29.C3 FIX — the display is now built conditionally instead of
    f"{v} - {n}".strip(" -"), so legitimate leading/trailing hyphens in a
    vendor or name survive: 'Acme' + '-EOL-' -> 'Acme - -EOL-' (was 'Acme -
    -EOL'), and a name-less vendor '-X-' shows '-X-' intact (was 'X')."""
    _mock_urls(monkeypatch)
    _fake_requests_get(monkeypatch, [
        # fid 10: vendor + hyphen-wrapped name (count>1 to become a candidate).
        {'id': 1, 'archived': False,
         'filament': {'id': 10, 'name': '-EOL-', 'vendor': {'name': 'Acme'}}},
        {'id': 2, 'archived': False,
         'filament': {'id': 10, 'name': '-EOL-', 'vendor': {'name': 'Acme'}}},
        # fid 11: name-less, hyphen-wrapped vendor.
        {'id': 3, 'archived': False, 'filament': {'id': 11, 'vendor': {'name': '-X-'}}},
        {'id': 4, 'archived': False, 'filament': {'id': 11, 'vendor': {'name': '-X-'}}},
    ])

    body = _client().get('/api/get_multi_spool_filaments').get_json()
    by_id = {c['id']: c for c in body}
    assert by_id[10]['display'] == 'Acme - -EOL-'
    assert by_id[11]['display'] == '-X-'


def test_multi_spool_spoolman_not_ok_returns_empty_list(monkeypatch):
    """A non-ok Spoolman response degrades to HTTP 200 + [] (no error status,
    no error body) — the frontend picker just shows nothing."""
    _mock_urls(monkeypatch)
    _fake_requests_get(monkeypatch, None, ok=False)

    res = _client().get('/api/get_multi_spool_filaments')
    assert res.status_code == 200
    assert res.get_json() == []


def test_multi_spool_non_list_payload_returns_empty_list(monkeypatch):
    """A non-list JSON payload (e.g. a Spoolman error object) is guarded by
    the isinstance check → 200 + [] with no exception."""
    _mock_urls(monkeypatch)
    _fake_requests_get(monkeypatch, {'detail': 'boom'})

    res = _client().get('/api/get_multi_spool_filaments')
    assert res.status_code == 200
    assert res.get_json() == []


def test_multi_spool_exception_swallowed_to_empty_list(monkeypatch):
    """A raising requests.get is swallowed by the blanket except: the endpoint
    still returns 200 + [] and logs 'Multi-Spool Error' via state.logger.error
    (NOT the Activity Log)."""
    _mock_urls(monkeypatch)
    mock_logger = _capture_logger(monkeypatch)

    def raising_get(*args, **kwargs):
        raise RuntimeError('connection exploded')

    monkeypatch.setattr(app_module.requests, 'get', raising_get)

    res = _client().get('/api/get_multi_spool_filaments')
    assert res.status_code == 200
    assert res.get_json() == []
    mock_logger.error.assert_called_once()
    assert 'Multi-Spool Error' in mock_logger.error.call_args[0][0]


def test_multi_spool_malformed_spool_is_skipped_valid_candidates_survive(monkeypatch):
    """27.7 FIX — a single malformed spool (missing 'id' key) is now skipped by
    the per-spool guard (logged) and the VALID fid-7 group STILL returns,
    instead of the blanket except poisoning the entire response to [] and
    hiding every other valid candidate.
    """
    _mock_urls(monkeypatch)
    mock_logger = _capture_logger(monkeypatch)
    _fake_requests_get(monkeypatch, [
        _spool(101, 7),
        _spool(102, 7),
        # Malformed: no 'id' key → s['id'] KeyError, caught per-spool.
        {'archived': False, 'filament': {'id': 9, 'name': 'X'}},
    ])

    res = _client().get('/api/get_multi_spool_filaments')
    assert res.status_code == 200
    assert res.get_json() == [{
        'id': 7,
        'display': 'Acme - Blue',
        'count': 2,
        'spool_ids': [101, 102],
    }]
    # The one bad entry was logged (skipped), not swallowed to nothing.
    mock_logger.error.assert_called_once()
    assert 'skipping malformed spool' in mock_logger.error.call_args[0][0]


# ---------------------------------------------------------------------------
# POST /api/backfill_spool_weights/<int:fid>
# ---------------------------------------------------------------------------

def _record_update_spool(monkeypatch, result_for=lambda sid: {'id': sid}):
    """Patch spoolman_api.update_spool with a recorder; returns the call list
    of (sid, payload) tuples."""
    calls = []

    def fake_update(sid, payload):
        calls.append((sid, payload))
        return result_for(sid)

    monkeypatch.setattr(app_module.spoolman_api, 'update_spool', fake_update)
    return calls


def test_backfill_filament_weight_wins_updates_payload_and_url(monkeypatch):
    """Filament spool_weight takes precedence over the vendor's
    empty_spool_weight (source=='filament'); only null/<=0 spools are PATCHed
    with EXACTLY {'spool_weight': target} (partial payload — sibling
    preservation is update_spool's job); positive-weight spools count as
    skipped; archived spools are included (the fetch URL carries
    allow_archived=true and the loop never checks the archived flag)."""
    _mock_urls(monkeypatch)
    monkeypatch.setattr(
        app_module.spoolman_api, 'get_filament',
        lambda fid: {'id': 7, 'spool_weight': 250,
                     'vendor': {'empty_spool_weight': 180}},
    )
    fetch_calls = _fake_requests_get(monkeypatch, [
        {'id': 1, 'spool_weight': 0},
        {'id': 2, 'spool_weight': 200},               # positive → skipped
        {'id': 3, 'spool_weight': None},
        {'id': 4, 'spool_weight': -5, 'archived': True},  # archived still fixed
    ])
    update_calls = _record_update_spool(monkeypatch)

    res = _client().post('/api/backfill_spool_weights/7')
    assert res.status_code == 200
    body = res.get_json()
    assert body == {
        'success': True,
        'filament_id': 7,
        'target_weight': 250.0,
        'source': 'filament',
        'updated': 3,
        'updated_ids': [1, 3, 4],
        'skipped': 1,
        'errors': [],
    }

    assert update_calls == [
        (1, {'spool_weight': 250.0}),
        (3, {'spool_weight': 250.0}),
        (4, {'spool_weight': 250.0}),
    ]

    # Spool fetch includes archived spools, 5s timeout.
    assert len(fetch_calls) == 1
    args, kwargs = fetch_calls[0]
    assert args == ('http://mock/api/v1/spool?filament_id=7&allow_archived=true',)
    assert kwargs.get('timeout') == 5


@pytest.mark.parametrize('fil_weight', [0, None, 'not-a-number'])
def test_backfill_vendor_fallback_when_filament_weight_not_positive(monkeypatch, fil_weight):
    """When the filament's own spool_weight is 0 / None / non-numeric, the
    vendor's empty_spool_weight is inherited and the response reports
    source=='vendor' with the float-coerced target."""
    _mock_urls(monkeypatch)
    monkeypatch.setattr(
        app_module.spoolman_api, 'get_filament',
        lambda fid: {'id': 7, 'spool_weight': fil_weight,
                     'vendor': {'empty_spool_weight': 180}},
    )
    _fake_requests_get(monkeypatch, [{'id': 1, 'spool_weight': 0}])
    update_calls = _record_update_spool(monkeypatch)

    body = _client().post('/api/backfill_spool_weights/7').get_json()
    assert body['success'] is True
    assert body['source'] == 'vendor'
    assert body['target_weight'] == 180.0
    assert update_calls == [(1, {'spool_weight': 180.0})]


@pytest.mark.parametrize('vendor', [None, {}, {'empty_spool_weight': 0}])
def test_backfill_no_inheritable_weight_400(monkeypatch, vendor):
    """Neither filament nor vendor has a positive weight → 400 with the
    'No inheritable empty-spool weight' message, and the spool fetch is never
    attempted (guard returns before any Spoolman list call)."""
    _mock_urls(monkeypatch)
    monkeypatch.setattr(
        app_module.spoolman_api, 'get_filament',
        lambda fid: {'id': 7, 'spool_weight': 0, 'vendor': vendor},
    )
    fetch = MagicMock()
    monkeypatch.setattr(app_module.requests, 'get', fetch)

    res = _client().post('/api/backfill_spool_weights/7')
    assert res.status_code == 400
    body = res.get_json()
    assert body['success'] is False
    assert 'No inheritable empty-spool weight' in body['msg']
    fetch.assert_not_called()


def test_backfill_unknown_filament_404(monkeypatch):
    """get_filament → None maps to 404 with the exact 'Filament #<id> not
    found.' message."""
    _mock_urls(monkeypatch)
    monkeypatch.setattr(app_module.spoolman_api, 'get_filament', lambda fid: None)

    res = _client().post('/api/backfill_spool_weights/99')
    assert res.status_code == 404
    body = res.get_json()
    assert body['success'] is False
    assert body['msg'] == 'Filament #99 not found.'


def test_backfill_spool_fetch_failure_502(monkeypatch):
    """A non-ok spool-list response from Spoolman maps to 502 with the fixed
    'Failed to fetch spools from Spoolman.' message and no writes."""
    _mock_urls(monkeypatch)
    monkeypatch.setattr(
        app_module.spoolman_api, 'get_filament',
        lambda fid: {'id': 7, 'spool_weight': 250, 'vendor': None},
    )
    _fake_requests_get(monkeypatch, None, ok=False)
    update_calls = _record_update_spool(monkeypatch)

    res = _client().post('/api/backfill_spool_weights/7')
    assert res.status_code == 502
    body = res.get_json()
    assert body['success'] is False
    assert body['msg'] == 'Failed to fetch spools from Spoolman.'
    assert update_calls == []


def test_backfill_per_spool_failure_collected_loop_continues(monkeypatch):
    """update_spool returning None (Spoolman rejection) lands that spool id in
    errors[] but does NOT abort: the loop continues to the remaining spools
    and the overall response stays success:True with the partial results —
    the documented per-spool best-effort contract for this write surface."""
    _mock_urls(monkeypatch)
    monkeypatch.setattr(
        app_module.spoolman_api, 'get_filament',
        lambda fid: {'id': 7, 'spool_weight': 250, 'vendor': None},
    )
    _fake_requests_get(monkeypatch, [
        {'id': 1, 'spool_weight': 0},
        {'id': 2, 'spool_weight': 0},   # this one gets rejected
        {'id': 3, 'spool_weight': None},
    ])
    update_calls = _record_update_spool(
        monkeypatch, result_for=lambda sid: None if sid == 2 else {'id': sid})

    res = _client().post('/api/backfill_spool_weights/7')
    assert res.status_code == 200
    body = res.get_json()
    assert body['success'] is True          # partial failure is still success
    assert body['updated'] == 2
    assert body['updated_ids'] == [1, 3]
    assert body['errors'] == [2]
    assert body['skipped'] == 0
    # Loop continued past the failure — all three spools were attempted.
    assert [c[0] for c in update_calls] == [1, 2, 3]


def test_backfill_malformed_spool_no_id_skipped(monkeypatch):
    """29.N2 FIX — a spool list entry with no 'id' (only reachable with
    malformed Spoolman data) is now SKIPPED (logged) instead of issuing a
    PATCH aimed at /spool/None. Valid spools in the same batch are still
    updated and update_spool is never called with a None id."""
    _mock_urls(monkeypatch)
    mock_logger = _capture_logger(monkeypatch)
    monkeypatch.setattr(
        app_module.spoolman_api, 'get_filament',
        lambda fid: {'id': 7, 'spool_weight': 250, 'vendor': None},
    )
    _fake_requests_get(monkeypatch, [
        {'id': 1, 'spool_weight': 0},
        {'spool_weight': 0},            # malformed: no 'id' → skipped
        {'id': 3, 'spool_weight': None},
    ])
    update_calls = _record_update_spool(monkeypatch)

    res = _client().post('/api/backfill_spool_weights/7')
    assert res.status_code == 200
    body = res.get_json()
    assert body['success'] is True
    assert body['updated'] == 2
    assert body['updated_ids'] == [1, 3]
    assert body['errors'] == []
    # update_spool was NEVER called with a None id.
    assert [c[0] for c in update_calls] == [1, 3]
    # The malformed entry was logged as a warning naming the missing id.
    mock_logger.warning.assert_called_once()
    assert 'no id' in mock_logger.warning.call_args[0][0]


@pytest.mark.parametrize('spool_payload', [[], None])
def test_backfill_empty_filament_no_spools(monkeypatch, spool_payload):
    """A filament with zero spools (empty list, or a null JSON body which the
    `or []` guard normalizes) succeeds with all-zero counters and no writes."""
    _mock_urls(monkeypatch)
    monkeypatch.setattr(
        app_module.spoolman_api, 'get_filament',
        lambda fid: {'id': 7, 'spool_weight': 250, 'vendor': None},
    )
    _fake_requests_get(monkeypatch, spool_payload)
    update_calls = _record_update_spool(monkeypatch)

    res = _client().post('/api/backfill_spool_weights/7')
    assert res.status_code == 200
    body = res.get_json()
    assert body == {
        'success': True,
        'filament_id': 7,
        'target_weight': 250.0,
        'source': 'filament',
        'updated': 0,
        'updated_ids': [],
        'skipped': 0,
        'errors': [],
    }
    assert update_calls == []


def test_backfill_unexpected_exception_500(monkeypatch):
    """An unexpected exception inside the handler (here: update_spool raising)
    maps to 500 with msg == str(exc), and state.logger.error names the
    endpoint + filament id for diagnosis."""
    _mock_urls(monkeypatch)
    mock_logger = _capture_logger(monkeypatch)
    monkeypatch.setattr(
        app_module.spoolman_api, 'get_filament',
        lambda fid: {'id': 7, 'spool_weight': 250, 'vendor': None},
    )
    _fake_requests_get(monkeypatch, [{'id': 1, 'spool_weight': 0}])

    def raising_update(sid, payload):
        raise RuntimeError('kaboom')

    monkeypatch.setattr(app_module.spoolman_api, 'update_spool', raising_update)

    res = _client().post('/api/backfill_spool_weights/7')
    assert res.status_code == 500
    body = res.get_json()
    assert body['success'] is False
    assert body['msg'] == 'kaboom'
    mock_logger.error.assert_called_once()
    assert 'api_backfill_spool_weights(7) failed' in mock_logger.error.call_args[0][0]


def test_backfill_non_integer_fid_routing_404(monkeypatch):
    """The route uses the <int:fid> converter, so a non-integer filament id
    404s at routing before the handler runs (no handler-level validation)."""
    monkeypatch.setattr(
        app_module.spoolman_api, 'get_filament',
        MagicMock(side_effect=AssertionError('handler must not run')),
    )
    res = _client().post('/api/backfill_spool_weights/not-a-number')
    assert res.status_code == 404
