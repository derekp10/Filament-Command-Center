"""Tests for the 23.4 extras delete-sentinel.

Every write surface read-merges via `_merge_extras_with_existing`. An OMITTED
key means "keep" (protects siblings: the 252/253/157 prod-wipe incident, when a
filament's PATCH replaced its whole `extra`). A key whose value is
DELETE_EXTRA_SENTINEL is the ONLY way to clear an extra. The merge must NEVER
forward the sentinel to Spoolman or store it literally.

2026-10-21: the merge used to POP the key, so the PATCH left it out. Spoolman
0.26+ merges a PATCH's `extra` key by key (dev and prod run 0.27.0), so a key
left out is KEPT and the clear never landed (a spool's extra has merged since
0.22, so a spool clear never landed at all). The sentinel now becomes a WRITE of
the value that clears the field: the plan's value (JSON null on Spoolman 0.26+,
else the type's own empty value, '""' for text), or '""' from a merge given no
plan. These are pure-function tests of the merge's invariants; the plan, and
every field type through the REAL update_spool / update_filament /
update_vendor on a faithful Spoolman fake, are in test_extras_clear_027.py.

The last tests drive the three write functions through tests/spoolman_extra_fake
both ways: merging like 0.27 and replacing like 0.23 (a filament's and a
vendor's PATCH up to 0.25).
"""
from __future__ import annotations

import sys
import os
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import spoolman_api
from spoolman_extra_fake import MERGE, REPLACE, SpoolmanHTTPFake

SENTINEL = spoolman_api.DELETE_EXTRA_SENTINEL


# --- _is_delete_sentinel ----------------------------------------------------

def test_is_delete_sentinel_raw_form():
    assert spoolman_api._is_delete_sentinel(SENTINEL) is True


def test_is_delete_sentinel_json_wrapped_form():
    # sanitize_outbound_data json.dumps a JSON_STRING_FIELDS value, so a future
    # surface (or the current edit-filament {...fil.extra} spread) may present
    # the sentinel quote-wrapped. It must still match.
    assert spoolman_api._is_delete_sentinel('"' + SENTINEL + '"') is True


def test_is_delete_sentinel_rejects_non_sentinels():
    for v in (None, '', 'sheet_link', 'https://example.com', '0', 0,
              ['__FCC_DELETE_EXTRA__'], {'k': SENTINEL}, '__FCC_DELETE_EXTRA__ ish'):
        assert spoolman_api._is_delete_sentinel(v) is False, v


# --- _merge_extras_with_existing -------------------------------------------

def test_merge_clears_a_present_text_key_and_preserves_siblings():
    # With no plan, written as a JSON empty string: every Spoolman stores it
    # (merging or replacing), and FCC reads it back as '' (blank). Left out,
    # 0.27 kept it.
    existing = {'product_url': '"https://x"', 'purchase_url': '"https://y"'}
    merged = spoolman_api._merge_extras_with_existing(existing, {'product_url': SENTINEL})
    assert merged['product_url'] == '""'
    assert merged.get('purchase_url') == '"https://y"'


def test_merge_writes_the_plans_value_for_each_key():
    existing = {'sample_printed': 'true', 'slicer_profile': '"Basic PLA"', 'old': '"x"', 'keep': '"k"'}
    clears = {'sample_printed': None, 'slicer_profile': None, 'old': spoolman_api._LEAVE_OUT}
    merged = spoolman_api._merge_extras_with_existing(
        existing, {'sample_printed': SENTINEL, 'slicer_profile': SENTINEL, 'old': SENTINEL}, clears)
    assert merged == {'sample_printed': None, 'slicer_profile': None, 'keep': '"k"'}


def test_merge_never_emits_the_literal_sentinel():
    existing = {'product_url': '"https://x"'}
    merged = spoolman_api._merge_extras_with_existing(existing, {'product_url': SENTINEL})
    for val in merged.values():
        assert not spoolman_api._is_delete_sentinel(val)
        assert SENTINEL not in str(val)


def test_merge_sentinel_for_absent_key_is_noop():
    existing = {'purchase_url': '"https://y"'}
    merged = spoolman_api._merge_extras_with_existing(existing, {'product_url': SENTINEL})
    assert 'product_url' not in merged
    assert merged == {'purchase_url': '"https://y"'}


def test_merge_sentinel_for_an_already_blank_key_leaves_it():
    existing = {'product_url': '""', 'filament_attributes': '[]'}
    merged = spoolman_api._merge_extras_with_existing(
        existing, {'product_url': SENTINEL, 'filament_attributes': SENTINEL}, {})
    assert merged == existing


def test_merge_refuses_to_delete_system_managed_key():
    # Defense-in-depth: the clear-sentinel must NEVER unseat a slotted spool,
    # regardless of which caller forwards it, even with a plan that names it.
    for key in spoolman_api.SYSTEM_MANAGED_EXTRAS:
        existing = {key: 'XL-1', 'product_url': '"https://x"'}
        for clears in (None, {key: '""'}):
            merged = spoolman_api._merge_extras_with_existing(existing, {key: SENTINEL}, clears)
            assert merged.get(key) == 'XL-1', key
            assert merged.get('product_url') == '"https://x"'


def test_the_plan_never_clears_a_system_managed_key():
    with patch.object(spoolman_api, '_extra_field_schema', return_value=None):
        plan = spoolman_api._plan_extra_clears('spool', {'container_slot': '"2"'}, {'container_slot': SENTINEL})
    assert plan == {}


def test_sanitize_then_merge_never_stores_the_sentinel():
    # Mirror the real update_filament/update_spool/update_vendor path: sanitize
    # the caller's extras FIRST (which json.dumps-wraps the sentinel), then merge
    # against the raw existing dict.
    existing = {'product_url': '"https://x"', 'sheet_link': '"https://s"'}
    caller = {'product_url': SENTINEL}
    sanitized = spoolman_api.sanitize_outbound_data({'extra': caller}).get('extra', {})
    merged = spoolman_api._merge_extras_with_existing(existing, sanitized)
    assert merged['product_url'] == '""'
    assert merged.get('sheet_link') == '"https://s"'
    for val in merged.values():
        assert SENTINEL not in str(val)


# --- compute_dirty_extras ---------------------------------------------------

def test_compute_dirty_keeps_real_delete():
    # Existing has a value → a sentinel clear is a REAL change → stays dirty.
    existing = {'product_url': 'https://x'}
    dirty, _stripped = spoolman_api.compute_dirty_extras(existing, {'product_url': SENTINEL})
    assert dirty.get('product_url') == SENTINEL


def test_compute_dirty_suppresses_noop_delete_on_absent_key():
    # Existing lacks the key → deleting it is a no-op → must NOT manufacture a
    # dirty set (would cause a spurious PATCH on an unchanged wizard edit-save).
    existing = {'purchase_url': 'https://y'}
    dirty, _stripped = spoolman_api.compute_dirty_extras(existing, {'product_url': SENTINEL})
    assert 'product_url' not in dirty
    assert dirty == {}


def test_compute_dirty_suppresses_noop_delete_on_blank_key():
    existing = {'product_url': ''}
    dirty, _stripped = spoolman_api.compute_dirty_extras(existing, {'product_url': SENTINEL})
    assert dirty == {}


def test_compute_dirty_suppresses_noop_delete_on_a_cleared_text_key_read_raw():
    # A text extra blanked on a Spoolman older than 0.26 (or by FCC's own ''
    # writes) is stored as '""'; read without parse_inbound_data it is the
    # 2-character string, which is still blank.
    dirty, _stripped = spoolman_api.compute_dirty_extras({'product_url': '""'}, {'product_url': SENTINEL})
    assert dirty == {}


def test_compute_dirty_strips_system_managed_sentinel():
    existing = {'container_slot': 'XL-1'}
    dirty, stripped = spoolman_api.compute_dirty_extras(
        existing, {'container_slot': SENTINEL},
        system_managed=spoolman_api.SYSTEM_MANAGED_EXTRAS,
    )
    assert 'container_slot' not in dirty
    assert 'container_slot' in stripped


# --- through the write functions, on a Spoolman that merges and one that replaces --

FIELDS = {
    'spool': [{'key': 'product_url', 'field_type': 'text', 'name': 'p'},
              {'key': 'purchase_url', 'field_type': 'text', 'name': 'b'}],
    'filament': [{'key': 'product_url', 'field_type': 'text', 'name': 'p'},
                 {'key': 'sheet_link', 'field_type': 'text', 'name': 's'}],
    'vendor': [{'key': 'website', 'field_type': 'text', 'name': 'w'}],
}


def _clear_caches():
    for name in ('_FIELD_SCHEMA_CACHE', '_SPOOLMAN_VERSION_CACHE'):
        getattr(spoolman_api, name, {}).clear()


@pytest.fixture(autouse=True)
def _fresh_caches():
    _clear_caches()
    yield
    _clear_caches()


@pytest.mark.parametrize('mode', [MERGE, REPLACE])
@pytest.mark.parametrize('entity,eid,extra,key', [
    ('spool', 5, {'product_url': '"https://x"', 'purchase_url': '"https://y"'}, 'product_url'),
    ('filament', 12, {'product_url': '"https://x"', 'sheet_link': '"https://s"'}, 'product_url'),
    ('vendor', 3, {'website': '"https://v"'}, 'website'),
])
def test_a_clear_lands_whether_spoolman_merges_or_replaces(mode, entity, eid, extra, key):
    """RED on the base in merge mode (0.27): the popped key was kept."""
    fake = SpoolmanHTTPFake(version='0.27.0' if mode == MERGE else '0.23.1', mode=mode, fields=FIELDS)
    fake.add(entity, eid, dict(extra))
    write = {'spool': spoolman_api.update_spool, 'filament': spoolman_api.update_filament,
             'vendor': spoolman_api.update_vendor}[entity]
    with patch.object(spoolman_api.config_loader, 'get_api_urls', return_value=('http://sm.test', 'http://fb')), \
         patch.object(spoolman_api.requests, 'get', side_effect=fake.get), \
         patch.object(spoolman_api.requests, 'patch', side_effect=fake.patch), \
         patch.object(spoolman_api.state, 'add_log_entry'):
        res = write(eid, {'extra': {key: SENTINEL}})
    assert res is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    stored = fake.extra(entity, eid)
    if mode == MERGE:
        assert key not in stored, stored       # 0.27: sent as null, so the row is dropped
    else:
        assert stored[key] == '""', stored     # 0.23.1 takes no null: a JSON empty string
    for other, raw in extra.items():
        if other != key:
            assert stored[other] == raw, stored
