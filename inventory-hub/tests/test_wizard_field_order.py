"""Group 10.6 — Wizard field-order stability.

Spoolman's /api/v1/field/{entity} response has no `order` key, so the wizard's
existing sort (`.sort((a,b) => (a.order||0) - (b.order||0))`) was a no-op and
fields shifted around whenever Spoolman re-emitted its array. The fix lives in
`app.py`: `_enrich_field_order` stamps each field dict with a canonical order
index from `FIELD_ORDER` before the wizard ever sees it. Unknown keys go to
`FIELD_ORDER_UNKNOWN` (end of the list).
"""
from __future__ import annotations

import app as fcc_app


def test_enrich_filament_fields_uses_canonical_order():
    spoolman_response = [
        {"key": "slicer_profile", "name": "Slicer Profile", "field_type": "choice"},
        {"key": "filament_attributes", "name": "Filament Attributes", "field_type": "choice"},
        {"key": "purchase_url", "name": "Purchase Link", "field_type": "text"},
    ]

    enriched = fcc_app._enrich_field_order("filament", spoolman_response)

    by_key = {f["key"]: f["order"] for f in enriched}
    assert by_key["filament_attributes"] < by_key["slicer_profile"]
    assert by_key["slicer_profile"] < by_key["purchase_url"]


def test_enrich_handles_unknown_keys_by_pinning_to_end():
    enriched = fcc_app._enrich_field_order(
        "filament",
        [
            {"key": "filament_attributes"},
            {"key": "totally_made_up_field"},
        ],
    )

    by_key = {f["key"]: f["order"] for f in enriched}
    assert by_key["filament_attributes"] == 0
    assert by_key["totally_made_up_field"] == fcc_app.FIELD_ORDER_UNKNOWN
    assert by_key["filament_attributes"] < by_key["totally_made_up_field"]


def test_enrich_spool_fields_order_is_independent_of_filament():
    enriched = fcc_app._enrich_field_order(
        "spool",
        [
            {"key": "purchase_url"},
            {"key": "spool_type"},
            {"key": "container_slot"},
        ],
    )

    by_key = {f["key"]: f["order"] for f in enriched}
    # spool ordering: spool_type → container_slot → purchase_url
    assert by_key["spool_type"] < by_key["container_slot"] < by_key["purchase_url"]


def test_enrich_is_idempotent():
    """Re-enriching an already-enriched list should produce identical ordering."""
    fields = [
        {"key": "purchase_url"},
        {"key": "filament_attributes"},
    ]
    once = fcc_app._enrich_field_order("filament", fields)
    twice = fcc_app._enrich_field_order("filament", once)
    assert [f["order"] for f in once] == [f["order"] for f in twice]


def test_enrich_unknown_entity_type_is_safe():
    """An entity type not in FIELD_ORDER should not raise — every field gets UNKNOWN."""
    enriched = fcc_app._enrich_field_order(
        "vendor",
        [{"key": "website"}, {"key": "something_else"}],
    )
    for f in enriched:
        assert f["order"] == fcc_app.FIELD_ORDER_UNKNOWN


def test_field_order_covers_all_setup_fields_py_definitions():
    """Guard against drift: every field declared in setup_fields.py should
    have a slot in FIELD_ORDER, otherwise it sorts to the end as a stranger.
    Hardcoded from `setup-and-rebuild/setup_fields.py` — keep in sync when
    new extras are added."""
    expected_filament = {
        "filament_attributes", "shore_hardness", "slicer_profile",
        "needs_label_print", "sample_printed", "product_url", "purchase_url",
        "sheet_link", "price_total", "original_color", "drying_temp",
        "drying_time", "flush_multiplier", "nozzle_temp_max", "bed_temp_max",
        "multi_color_direction",
    }
    expected_spool = {
        "physical_source", "physical_source_slot", "fcc_pre_archive_location",
        "needs_label_print", "is_refill", "spool_temp", "product_url",
        "purchase_url", "container_slot", "spool_type",
        # Prusament-import per-spool extras (not in setup_fields.py but
        # surfaced live by Spoolman once a Prusament scan populates them).
        "original_color", "nozzle_temp_max", "bed_temp_max",
        "prusament_manufacturing_date", "prusament_length_m",
    }

    assert expected_filament <= set(fcc_app.FIELD_ORDER["filament"]), (
        f"Missing filament keys in FIELD_ORDER: "
        f"{expected_filament - set(fcc_app.FIELD_ORDER['filament'])}"
    )
    assert expected_spool <= set(fcc_app.FIELD_ORDER["spool"]), (
        f"Missing spool keys in FIELD_ORDER: "
        f"{expected_spool - set(fcc_app.FIELD_ORDER['spool'])}"
    )
