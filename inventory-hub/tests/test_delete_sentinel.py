"""Tests for the 23.4 extras delete-sentinel.

Spoolman PATCH REPLACES the whole `extra` dict, so every write surface
read-merges via `_merge_extras_with_existing`. An OMITTED key means "keep"
(protects siblings — the 252/253/157 prod-wipe incident). A key whose value is
DELETE_EXTRA_SENTINEL is the ONLY way to clear an extra: the merge pops it and
must NEVER forward it to Spoolman or store it literally.

These are pure-function tests of the invariants the three write surfaces
(update_filament / update_spool / update_vendor) and compute_dirty_extras rely
on — no server / Playwright needed.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import spoolman_api

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

def test_merge_pops_present_key_preserves_siblings():
    existing = {'product_url': '"https://x"', 'purchase_url': '"https://y"'}
    merged = spoolman_api._merge_extras_with_existing(existing, {'product_url': SENTINEL})
    assert 'product_url' not in merged
    assert merged.get('purchase_url') == '"https://y"'


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


def test_merge_refuses_to_delete_system_managed_key():
    # Defense-in-depth: the clear-sentinel must NEVER unseat a slotted spool,
    # regardless of which caller forwards it.
    for key in spoolman_api.SYSTEM_MANAGED_EXTRAS:
        existing = {key: 'XL-1', 'product_url': '"https://x"'}
        merged = spoolman_api._merge_extras_with_existing(existing, {key: SENTINEL})
        assert merged.get(key) == 'XL-1', key
        assert merged.get('product_url') == '"https://x"'


def test_sanitize_then_merge_never_stores_the_sentinel():
    # Mirror the real update_filament/update_spool/update_vendor path: sanitize
    # the caller's extras FIRST (which json.dumps-wraps the sentinel), then merge
    # against the raw existing dict.
    existing = {'product_url': '"https://x"', 'sheet_link': '"https://s"'}
    caller = {'product_url': SENTINEL}
    sanitized = spoolman_api.sanitize_outbound_data({'extra': caller}).get('extra', {})
    merged = spoolman_api._merge_extras_with_existing(existing, sanitized)
    assert 'product_url' not in merged
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


def test_compute_dirty_strips_system_managed_sentinel():
    existing = {'container_slot': 'XL-1'}
    dirty, stripped = spoolman_api.compute_dirty_extras(
        existing, {'container_slot': SENTINEL},
        system_managed=spoolman_api.SYSTEM_MANAGED_EXTRAS,
    )
    assert 'container_slot' not in dirty
    assert 'container_slot' in stripped
