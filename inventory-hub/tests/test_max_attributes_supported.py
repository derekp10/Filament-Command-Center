"""A filament carrying EVERY attribute must be SUPPORTED, not merely tolerated.

Derek's ask (2026-08-03):
    "Highly unlikely in reality, but we should make sure that having that many
     attributes doesn't break things like it might be doing right now, so we
     should probably put in some tests for this kind of thing, so that it's
     supported, even though it might not currently be possible."

It became possible by accident: a leaking test drove filament #55 to all 28
choices while every other record had <= 2. The only thing known to break was
that test — but nothing anywhere PINNED that the app tolerates the state, so
"it happens to work" was luck rather than a guarantee.

These are deliberately OFFLINE and mock-driven. The endpoints that would
exercise this end-to-end (`remove_choice` / `sweep_unused`) run a destructive
schema force_reset that can permanently destroy real filaments' extras — see
the data-loss item in Feature-Buglist.md — so pinning this against live data
would risk the very thing we are protecting.
"""
from __future__ import annotations

import json

import pytest

import app as app_module
import labels_csv

from test_l316_charact_filament_attributes_unit import (  # noqa: E402
    _attr_field,
    _capture_logs,
    _install_wire,
    client,  # noqa: F401  (pytest fixture, imported for use)
)


# A realistically-sized worst case: the live dev schema carried 28 choices when
# this was found, including ones with spaces and punctuation.
ALL_CHOICES = [
    "+", "Anniversary LE", "Basic", "Blend", "Carbon Fiber", "Duel Matte",
    "Easy", "Elite", "Fluorescent", "For Infill", "Galaxy", "Glass Fiber",
    "Glitter", "Glow", "Gradient", "High Speed", "Marble", "Matte", "Metal",
    "Neon", "Professional", "Rainbow", "Satin", "Silk", "Sparkle",
    "Transparent", "Wood Filled", "Recycled",
]


class TestLabelCsvTypeColumn:
    """`get_smart_type` joins EVERY attribute + the material into one string,
    which is what prints in the label CSV's Type column. Derek flagged the
    P-touch column as the thing most likely to suffer."""

    def test_all_attributes_render_without_error(self):
        out = labels_csv.get_smart_type(
            "PLA", {"filament_attributes": json.dumps(ALL_CHOICES)})
        assert isinstance(out, str) and out
        # Every attribute survives into the column, and the material lands last.
        for choice in ALL_CHOICES:
            assert choice in out, f"{choice!r} was dropped from the Type column"
        assert out.endswith("PLA")

    def test_no_leading_or_double_spaces(self):
        """28.A2 pinned that an empty material must not leave a trailing space.
        The same join must stay clean at the other extreme."""
        out = labels_csv.get_smart_type(
            "PLA", {"filament_attributes": json.dumps(ALL_CHOICES)})
        assert "  " not in out
        assert out == out.strip()

    def test_empty_material_still_clean_with_max_attributes(self):
        out = labels_csv.get_smart_type(
            "", {"filament_attributes": json.dumps(ALL_CHOICES)})
        assert not out.endswith(" ")
        assert "  " not in out

    def test_the_column_is_very_long_and_that_is_recorded(self):
        """Not an assertion of correctness — a tripwire.

        This documents how wide the Type column gets in the worst case, so if a
        future label template has to bound it, the number is already measured
        rather than discovered on a misprinted label.
        """
        out = labels_csv.get_smart_type(
            "PLA", {"filament_attributes": json.dumps(ALL_CHOICES)})
        assert len(out) > 200, (
            "expected a very long Type column for the max-attribute case; if "
            "this got short, the join changed and the label may be truncating"
        )

    @pytest.mark.parametrize("raw", [
        json.dumps(ALL_CHOICES),          # canonical wire form
        ALL_CHOICES,                       # already-parsed list
    ])
    def test_accepts_both_wire_and_parsed_forms(self, raw):
        out = labels_csv.get_smart_type("PLA", {"filament_attributes": raw})
        assert "Carbon Fiber" in out and out.endswith("PLA")


class TestReportWithAMaxAttributeFilament:
    def test_counts_every_choice_exactly_once(self, client, monkeypatch):
        """The report's per-choice usage counts must handle one record holding
        the entire schema."""
        fields = [_attr_field(ALL_CHOICES)]
        filaments = [{"id": 1, "name": "MaxAttrs",
                      "extra": {"filament_attributes": json.dumps(ALL_CHOICES)}}]
        _install_wire(monkeypatch, fields=fields, filaments=filaments)

        body = client.get("/api/filament_attributes/report").get_json()
        assert body["success"] is True
        assert set(body["counts"]) == set(ALL_CHOICES), (
            "counts must cover the whole schema"
        )
        assert all(v == 1 for v in body["counts"].values()), body["counts"]
        # 29.A1 — nothing should land in rogue_counts: every attribute IS a
        # schema choice here.
        assert not body.get("rogue_counts"), body.get("rogue_counts")

    def test_the_filament_row_lists_all_of_them(self, client, monkeypatch):
        fields = [_attr_field(ALL_CHOICES)]
        filaments = [{"id": 1, "name": "MaxAttrs",
                      "extra": {"filament_attributes": json.dumps(ALL_CHOICES)}}]
        _install_wire(monkeypatch, fields=fields, filaments=filaments)

        body = client.get("/api/filament_attributes/report").get_json()
        row = next(f for f in body["filaments"] if f["id"] == 1)
        assert sorted(row["attributes"]) == sorted(ALL_CHOICES)


class TestSweepUnusedWithAMaxAttributeFilament:
    """Derek's specific worry: 'nothing is unused when one record holds
    everything'. The sweep must then find NOTHING to do — and crucially must
    NOT run its destructive force_reset for an empty work list."""

    def test_nothing_is_unused(self, client, monkeypatch):
        fields = [_attr_field(ALL_CHOICES)]
        filaments = [{"id": 1, "name": "MaxAttrs",
                      "extra": {"filament_attributes": json.dumps(ALL_CHOICES)}}]
        calls = _install_wire(monkeypatch, fields=fields, filaments=filaments)
        _capture_logs(monkeypatch)

        body = client.post("/api/filament_attributes/sweep_unused",
                           json={"force": True}).get_json()
        assert body["success"] is True
        assert body.get("removed") == [], body
        assert body.get("restored", 0) == 0

        # THE IMPORTANT PART: no schema DELETE may happen when there is nothing
        # to sweep. That force_reset is the data-loss path — running it for a
        # no-op would put every filament's extras at risk for no reason.
        assert not [m for (m, _u, _j) in calls if m == "DELETE"], (
            "sweep_unused ran its destructive schema reset with nothing to remove"
        )

    def test_preview_mode_reports_nothing_unused(self, client, monkeypatch):
        fields = [_attr_field(ALL_CHOICES)]
        filaments = [{"id": 1, "name": "MaxAttrs",
                      "extra": {"filament_attributes": json.dumps(ALL_CHOICES)}}]
        calls = _install_wire(monkeypatch, fields=fields, filaments=filaments)

        body = client.post("/api/filament_attributes/sweep_unused",
                           json={}).get_json()
        assert body["success"] is True
        assert body.get("unused") == [], body
        assert not [m for (m, _u, _j) in calls if m == "DELETE"]
