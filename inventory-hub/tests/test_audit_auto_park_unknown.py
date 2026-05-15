"""Group 18.2 Part A — at audit end (CMD:DONE), any spool that was
expected at the audited location but wasn't scan-confirmed gets moved
to the virtual UNKNOWN bucket with a breadcrumb on
`extra.fcc_pre_audit_location` pointing at where it was expected.

Why not on `cmd:cancel`: cancel is the user explicitly bailing
(e.g. they realized they were auditing the wrong location). Only
`done` triggers the auto-park.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_audit_session():
    """Reset AUDIT_SESSION before / after each test so cross-test bleed
    can't mask a regression."""
    state.reset_audit()
    yield
    state.reset_audit()


def _seed_audit(loc_id: str, expected: list[int], scanned: list[int]):
    """Helper: configure the audit session as if the user opened it
    against `loc_id` and scanned the given subset of expected items."""
    state.AUDIT_SESSION.update({
        'active': True,
        'location_id': loc_id,
        'expected_items': list(expected),
        'scanned_items': list(scanned),
        'rogue_items': [],
    })


def test_audit_done_parks_missing_spools_at_unknown():
    _seed_audit("LR-MDB-1", expected=[101, 102, 103], scanned=[101])

    captured_updates = []
    def _fake_update(sid, payload):
        captured_updates.append((sid, payload))
        return {"id": sid, **payload}

    def _fake_get_spool(sid):
        # Existing extras the audit code should preserve / merge against.
        return {"id": sid, "location": "LR-MDB-1", "extra": {
            "container_slot": str(sid % 10),
            "spool_type": '"Plastic"',
        }}

    with patch.object(logic.spoolman_api, "update_spool", side_effect=_fake_update), \
         patch.object(logic.spoolman_api, "get_spool", side_effect=_fake_get_spool):
        result = logic.process_audit_scan({'type': 'command', 'cmd': 'done'})

    assert result['status'] == 'success'
    moved_ids = sorted(sid for sid, _ in captured_updates)
    assert moved_ids == [102, 103], (
        f"Should park exactly the unscanned IDs at UNKNOWN; got {moved_ids}"
    )
    for sid, payload in captured_updates:
        assert payload['location'] == 'UNKNOWN'
        extras = payload['extra']
        assert extras['fcc_pre_audit_location'] == 'LR-MDB-1', (
            f"Breadcrumb missing/wrong for #{sid}: {extras.get('fcc_pre_audit_location')!r}"
        )
        # Pre-existing extras are preserved alongside the new key.
        assert 'container_slot' in extras
        assert 'spool_type' in extras


def test_audit_cancel_does_not_park_missing_spools():
    """Cancel = user bailing out. Shouldn't apply the auto-park."""
    _seed_audit("LR-MDB-1", expected=[101, 102], scanned=[101])

    called = []
    def _fake_update(sid, payload):
        called.append((sid, payload))
        return {"id": sid, **payload}

    with patch.object(logic.spoolman_api, "update_spool", side_effect=_fake_update), \
         patch.object(logic.spoolman_api, "get_spool", return_value={"id": 102, "extra": {}}):
        result = logic.process_audit_scan({'type': 'command', 'cmd': 'cancel'})

    assert result['status'] == 'success'
    assert called == [], (
        f"cancel should NOT trigger auto-park; got updates {called}"
    )


def test_audit_done_perfect_match_does_not_call_update():
    """Sanity: no missing spools → no auto-park; the existing 'Perfect Match'
    log message path still runs unchanged."""
    _seed_audit("LR-MDB-1", expected=[101], scanned=[101])

    called = []
    def _fake_update(sid, payload):
        called.append((sid, payload))
        return {"id": sid, **payload}

    with patch.object(logic.spoolman_api, "update_spool", side_effect=_fake_update):
        result = logic.process_audit_scan({'type': 'command', 'cmd': 'done'})

    assert result['status'] == 'success'
    assert called == []


def test_audit_done_with_no_location_no_auto_park():
    """Defensive: if the session somehow ended without a location set,
    don't try to park anything (we'd have no breadcrumb anchor)."""
    state.AUDIT_SESSION.update({
        'active': True,
        'location_id': '',
        'expected_items': [101, 102],
        'scanned_items': [],
        'rogue_items': [],
    })
    called = []
    with patch.object(logic.spoolman_api, "update_spool",
                      side_effect=lambda *a, **k: called.append(a) or {}):
        logic.process_audit_scan({'type': 'command', 'cmd': 'done'})
    assert called == []


def test_fcc_pre_audit_location_is_system_managed():
    """The breadcrumb key must be in SYSTEM_MANAGED_EXTRAS so user-driven
    edit surfaces (wizard, vendor edit, manufacturer edit) can't clobber
    it during a routine save."""
    from spoolman_api import SYSTEM_MANAGED_EXTRAS
    assert 'fcc_pre_audit_location' in SYSTEM_MANAGED_EXTRAS
