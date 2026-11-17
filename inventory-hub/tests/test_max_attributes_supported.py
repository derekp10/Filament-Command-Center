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
from unittest.mock import patch

import pytest

import app as app_module
import labels_csv
import spoolman_api

from test_l316_charact_filament_attributes_unit import (  # noqa: E402
    _attr_field,
    _capture_logs,
    _install_wire,
    client,  # noqa: F401  (pytest fixture, imported for use)
)
from test_search_api import _attr_filament, _attr_get  # noqa: E402


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


# --- Group 54.2: search, the fifth surface ------------------------------------
#
# Group 49.1 made the attributes searchable text, and a card's line puts every one
# in front of the material (format_spool_display for a spool card, search_inventory's
# own builder for a filament card), so a filament holding the whole schema has a
# card that says 28 tags before "PLA". The four windows that draw them as chips are
# checked on the real page: test_max_attribute_chips_e2e.py.

MAX_FIL = _attr_filament(801, "Ocean Blue", "PLA", json.dumps(ALL_CHOICES), color="Ocean Blue")
# A filament with no attributes whose own words hold none of the 28's, so a query
# that found it would find anything (the control below shows it can be found).
PLAIN_FIL = _attr_filament(802, "Plain Jane", "ABS", "[]")
MAX_SPOOLS = [
    {"id": 901, "remaining_weight": 750, "location": "Shelf A", "filament": MAX_FIL},
    {"id": 902, "remaining_weight": 300, "location": "Shelf B", "filament": PLAIN_FIL},
]
CARD_LINE = " ".join(ALL_CHOICES) + " PLA"


class TestSearchWithAMaxAttributeFilament:
    """The attribute search with one filament holding all 28 (Group 54.2, the
    planning pass's search case, due since Group 49.1 shipped). Spoolman's two
    lists are test_search_api's _attr_get fake; nothing else is stubbed."""

    @pytest.fixture(autouse=True)
    def _spoolman(self):
        with patch("spoolman_api.requests.get") as get:
            get.side_effect = _attr_get(spools=MAX_SPOOLS, filaments=[MAX_FIL, PLAIN_FIL])
            yield

    @pytest.mark.parametrize("choice", ALL_CHOICES)
    def test_each_attribute_finds_the_filament(self, choice):
        found = spoolman_api.search_inventory(query=choice, target_type="filament")
        assert [r["id"] for r in found] == [801]

    @pytest.mark.parametrize("choice", ALL_CHOICES)
    def test_each_attribute_finds_its_spool(self, choice):
        assert [r["id"] for r in spoolman_api.search_inventory(query=choice)] == [901]

    def test_all_28_in_one_query_find_it(self):
        """The every-token rule over all of them at once (33 words: some tags are two)."""
        query = " ".join(ALL_CHOICES)
        assert [r["id"] for r in spoolman_api.search_inventory(query=query, target_type="filament")] == [801]
        assert [r["id"] for r in spoolman_api.search_inventory(query=query)] == [901]

    def test_control_the_plain_filament_is_found_by_its_own_words(self):
        assert [r["id"] for r in spoolman_api.search_inventory(query="plain", target_type="filament")] == [802]
        assert [r["id"] for r in spoolman_api.search_inventory(query="plain")] == [902]

    @pytest.mark.parametrize("raw", [json.dumps(ALL_CHOICES), list(ALL_CHOICES)], ids=["wire", "parsed"])
    def test_filament_attribute_list_gives_all_28_in_order(self, raw):
        assert spoolman_api.filament_attribute_list({"extra": {"filament_attributes": raw}}) == ALL_CHOICES

    def test_the_cards_line_names_every_attribute_before_the_material(self):
        [spool] = spoolman_api.search_inventory(query="ocean")
        [fil] = spoolman_api.search_inventory(query="ocean", target_type="filament")
        assert spool["details"]["material"] == CARD_LINE
        assert fil["details"]["material"] == CARD_LINE
