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


def test_audit_summary_includes_display_labels_not_bare_ids():
    """18.2 follow-up — the Activity Log Missing/Extra summary lines must
    include the spool's display label (brand + material + color), not
    just bare IDs. Bare IDs aren't enough information to actually go
    find the spool. Falls back to "#N" silently if Spoolman can't
    resolve the record."""
    _seed_audit("LR-MDB-1", expected=[101, 102], scanned=[101])
    state.AUDIT_SESSION['rogue_items'] = [999]

    log_calls = []

    def _fake_get_spool(sid):
        if sid == 102:
            return {"id": 102, "filament": {"name": "Galaxy Black", "material": "PLA"}}
        if sid == 999:
            return {"id": 999, "filament": {"name": "Mystery", "material": "PETG"}}
        return None

    def _fake_format(spool):
        # Mimic spoolman_api.format_spool_display shape.
        fil = (spool or {}).get('filament') or {}
        text = f"{fil.get('material','?')} ({fil.get('name','?')})"
        return {"text": text, "color": "#fff"}

    with patch.object(logic.spoolman_api, "get_spool", side_effect=_fake_get_spool), \
         patch.object(logic.spoolman_api, "format_spool_display", side_effect=_fake_format), \
         patch.object(logic.spoolman_api, "update_spool", return_value={"id": 102}), \
         patch.object(state, "add_log_entry", side_effect=lambda *a, **k: log_calls.append(a)):
        logic.process_audit_scan({'type': 'command', 'cmd': 'done'})

    # Find the summary line (the one containing "Audit Report").
    summary = next((c[0] for c in log_calls if 'Audit Report' in c[0]), None)
    assert summary, f"No 'Audit Report' line emitted; got {[c[0] for c in log_calls]}"
    # Missing-list entry references the resolved display text.
    assert "#102" in summary and "PLA" in summary and "Galaxy Black" in summary, (
        f"Missing line should carry display label, not bare ID. Got: {summary!r}"
    )
    # Extra-list entry too.
    assert "#999" in summary and "PETG" in summary, (
        f"Extra line should carry display label. Got: {summary!r}"
    )


def test_audit_summary_falls_back_to_bare_id_on_lookup_miss():
    """If get_spool returns None / blows up, the summary still renders
    with `#N` for that entry instead of erroring out."""
    _seed_audit("LR-MDB-1", expected=[101, 102], scanned=[101])

    log_calls = []
    with patch.object(logic.spoolman_api, "get_spool", return_value=None), \
         patch.object(logic.spoolman_api, "update_spool", return_value={"id": 102}), \
         patch.object(state, "add_log_entry", side_effect=lambda *a, **k: log_calls.append(a)):
        logic.process_audit_scan({'type': 'command', 'cmd': 'done'})

    summary = next((c[0] for c in log_calls if 'Audit Report' in c[0]), None)
    assert summary, "No Audit Report emitted"
    assert "#102" in summary, f"Bare-id fallback missing: {summary!r}"
