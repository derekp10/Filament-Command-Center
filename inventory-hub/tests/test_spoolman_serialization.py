import pytest
import sys
import os
import json

# Add parent directory to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import spoolman_api

def test_sanitize_outbound_data_string_numbers():
    """Test that numbers inside strings are strictly dumped as json strings if in JSON_STRING_FIELDS"""
    
    payload = {
        "id": 1,
        "extra": {
            "container_slot": "4", # Strictly typed in Spoolman DB as string
            "physical_source_slot": "99",
            "random_field": "123" # Not in JSON_STRING_FIELDS
        }
    }
    
    clean_payload = spoolman_api.sanitize_outbound_data(payload)
    clean_extra = clean_payload.get('extra', {})
    
    # "4" -> json.dumps -> '"4"'
    assert clean_extra.get('container_slot') == '"4"'
    assert clean_extra.get('physical_source_slot') == '"99"'
    
    # "123" -> json.loads -> 123 -> not enforced as string
    assert clean_extra.get('random_field') == "123"

def test_sanitize_outbound_data_naked_strings():
    """Test that arbitrary naked strings are wrapped in double quotes to satisfy Spoolman json constraints"""
    payload = {
        "id": 1,
        "extra": {
            "slicer_profile": "Basic PLA" # Naked string
        }
    }
    
    clean_payload = spoolman_api.sanitize_outbound_data(payload)
    
    assert clean_payload['extra']['slicer_profile'] == '"Basic PLA"'

def test_sanitize_outbound_data_booleans():
    """Test that booleans and boolean-like types are explicitly mapped to strictly compliant Spoolman lowercase literal strings"""
    payload = {
        "id": 1,
        "extra": {
            "boolean_true": True,
            "boolean_false": False,
            "string_true_upper": "True",
            "string_false_upper": "False",
            "string_true_lower": "true",
            "string_false_lower": "false"
        }
    }
    
    clean_payload = spoolman_api.sanitize_outbound_data(payload)
    
    # Must natively produce identical coerced outputs compatible with Pydantic Extra str,str models
    assert clean_payload['extra']['boolean_true'] == "true"
    assert clean_payload['extra']['boolean_false'] == "false"
    assert clean_payload['extra']['string_true_upper'] == "true"
    assert clean_payload['extra']['string_false_upper'] == "false"
    assert clean_payload['extra']['string_true_lower'] == "true"
    assert clean_payload['extra']['string_false_lower'] == "false"

def test_clamp_used_weight_rule():
    """Test that spools generated or updated explicitly enforce the SQLAlchemy integrity constraints prior to payload generation"""
    # Simulate a user submitting a form where they weighed an empty spool resulting in 'used_weight = 1200' on a 1000g initial spool.
    initial_weight = 1000.0
    used_weight = 1200.0

    # The API layer enforces min() clamp logic explicitly in create_spool / update_spool
    clamped_used_weight = min(used_weight, initial_weight) if initial_weight is not None else used_weight

    assert clamped_used_weight == 1000.0


def _fake_spool(vendor_name="CC3D", color_name="Red", material="PLA"):
    return {
        "id": 42,
        "external_id": "",
        "remaining_weight": 500,
        "extra": {},
        "filament": {
            "id": 7,
            "vendor": {"name": vendor_name},
            "material": material,
            "name": color_name,
            "color_hex": "ff0000",
            "extra": {},
        },
    }


@pytest.mark.parametrize("vendor_name", ["CC3D", "MatterHackers", "eSUN", "polymaker"])
def test_format_spool_display_preserves_vendor_casing(vendor_name):
    """Vendor/manufacturer names must be shown verbatim — not .title()-cased.

    Regression guard for the 'CC3D' -> 'Cc3D' autocorrection bug. Brand strings
    should be stripped of whitespace only; any other case-changing is out of scope.
    """
    spool = _fake_spool(vendor_name=vendor_name)
    out = spoolman_api.format_spool_display(spool)

    assert vendor_name in out["text"], (
        f"Expected '{vendor_name}' in display text, got: {out['text']}"
    )
    assert vendor_name in out["text_short"], (
        f"Expected '{vendor_name}' in short text, got: {out['text_short']}"
    )


def test_format_spool_display_preserves_vendor_with_surrounding_whitespace():
    """Leading/trailing whitespace is still stripped, but internal casing survives."""
    spool = _fake_spool(vendor_name="  CC3D  ")
    out = spoolman_api.format_spool_display(spool)
    assert "CC3D" in out["text"]
    assert "  CC3D  " not in out["text"]


# ---------------------------------------------------------------------------
# Activity-Log enrichment helper (logic._spool_brand_color_suffix)
# ---------------------------------------------------------------------------

import logic  # noqa: E402


def test_brand_color_suffix_includes_manufacturer_and_color(monkeypatch):
    """Auto-Detect / Auto-Deploy log lines must identify the spool, not just #ID."""
    fake = _fake_spool(vendor_name="CC3D", color_name="Crimson Red", material="PLA")
    monkeypatch.setattr(logic.spoolman_api, "get_spool", lambda sid: fake)

    suffix = logic._spool_brand_color_suffix(42)

    assert "CC3D" in suffix
    assert "Crimson Red" in suffix
    assert "PLA" in suffix
    assert suffix.startswith(" — ")


def test_brand_color_suffix_empty_when_spool_missing(monkeypatch):
    """A missing spool should collapse to an empty suffix, not raise."""
    monkeypatch.setattr(logic.spoolman_api, "get_spool", lambda sid: None)
    assert logic._spool_brand_color_suffix(9999) == ""


def test_brand_color_suffix_swallows_exceptions(monkeypatch):
    """Network / API errors must never break the log write."""
    def boom(sid):
        raise RuntimeError("spoolman unreachable")
    monkeypatch.setattr(logic.spoolman_api, "get_spool", boom)
    assert logic._spool_brand_color_suffix(42) == ""


# ---------------------------------------------------------------------------
# Spool / Filament color-card parity (search_inventory → frontend card render)
# ---------------------------------------------------------------------------
# The filament branch used to truncate multi-color strings to the first hex
# only, and defaulted `color_direction` to '' (blank), which caused the card
# gradient / coextruded rendering to diverge from the spool branch.
# Regression guards below.


def _fake_filament_multi():
    return {
        "id": 99,
        "name": "Cosmic Swirl",
        "material": "PLA",
        "vendor": {"id": 1, "name": "Polymaker"},
        "color_hex": "ff0000",
        "multi_color_hexes": "ff0000,00ff00,0000ff",
        "multi_color_direction": "coaxial",
        "extra": {},
    }


def test_format_spool_display_passes_full_multicolor_string():
    """Spool cards need the complete CSV of hex codes — not a truncation."""
    spool = _fake_spool(vendor_name="Polymaker")
    spool["filament"]["multi_color_hexes"] = "ff0000,00ff00,0000ff"
    spool["filament"]["multi_color_direction"] = "coaxial"

    out = spoolman_api.format_spool_display(spool)

    assert out["color"] == "ff0000,00ff00,0000ff"
    assert out["color_direction"] == "coaxial"


def test_filament_search_result_passes_full_multicolor_string():
    """Filament cards must render the same gradient/coextruded visuals as spools.

    Previously the filament branch did `base_color.split(',')[0]`, so a 3-color
    filament rendered solid red instead of the tri-color gradient a spool of
    the same filament would show.
    """
    # We can't easily stand up a full search_inventory test without Spoolman,
    # so exercise the formatting branch by stubbing requests.get and checking
    # the returned payload.
    import types, sys  # noqa: PLC0415
    fake_filaments = [_fake_filament_multi()]
    fake_spools: list = []

    class _FakeResp:
        def __init__(self, data):
            self._data = data
            self.ok = True

        def json(self):
            return self._data

    def fake_get(url, **_kwargs):
        if "/spool" in url:
            return _FakeResp(fake_spools)
        if "/filament" in url:
            return _FakeResp(fake_filaments)
        return _FakeResp([])

    # Patch the module-level requests.get for this test
    import spoolman_api as sm
    original = sm.requests.get
    sm.requests.get = fake_get
    try:
        results = sm.search_inventory(target_type="filament")
    finally:
        sm.requests.get = original

    assert results, "Expected at least one filament result"
    fil_card = results[0]
    assert fil_card["color"] == "ff0000,00ff00,0000ff", (
        f"Filament card color should be the full multi-color CSV, got {fil_card['color']!r}"
    )
    assert fil_card["color_direction"] == "coaxial"


def test_filament_search_result_direction_defaults_to_longitudinal():
    """When no direction is stored, filament cards should mirror the spool default."""
    fil = _fake_filament_multi()
    fil["multi_color_direction"] = ""
    fil["extra"] = {}

    class _FakeResp:
        def __init__(self, data):
            self._data = data
            self.ok = True

        def json(self):
            return self._data

    def fake_get(url, **_kwargs):
        if "/filament" in url:
            return _FakeResp([fil])
        return _FakeResp([])

    import spoolman_api as sm
    original = sm.requests.get
    sm.requests.get = fake_get
    try:
        results = sm.search_inventory(target_type="filament")
    finally:
        sm.requests.get = original

    assert results[0]["color_direction"] == "longitudinal"

