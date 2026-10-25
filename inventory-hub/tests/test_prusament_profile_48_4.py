"""Group 48.4 — the Prusament spool page names the slicer profile.

Derek, 2026-10-19: "It be perfered if we could just source that from the site …
being able to determin this, would help later on if they decide to add more
variants." PrusaSlicer names Prusa's profiles after the product line, and the
spool page's product name is that line + the colour + the size. The page shapes
below are real (dev's own Prusament spool URLs, read 2026-10-19).

Base proof (52741e6): prusament_profile doesn't exist there and the parser
returns no slicer_profile, so every test fails.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import external_parsers  # noqa: E402

REAL = [
    ({"name": "Prusament PETG Prusa Orange 1kg - v1", "color_name": "Prusa Orange", "material": "PETG"},
     "Prusament PETG"),
    ({"name": "Prusament PLA Blend Oh My Gold 1kg", "color_name": "Oh My Gold", "material": "PLA Blend"},
     "Prusament PLA Blend"),
    ({"name": "Prusament PLA Pearl Mouse 1kg - v1", "color_name": "Pearl Mouse", "material": "PLA"},
     "Prusament PLA"),
]


@pytest.mark.parametrize("fil, profile", REAL, ids=["petg", "pla-blend", "pla"])
def test_the_product_line_up_to_the_colour_is_the_profile(fil, profile):
    assert external_parsers.prusament_profile(fil) == profile


@pytest.mark.parametrize("fil, profile", [
    ({"name": "Prusament PC Blend Carbon Fiber Black 800g", "color_name": "Black", "material": "PC CF"},
     "Prusament PC Blend Carbon Fiber"),                       # the name wins over a terse material
    ({"name": "P PLA Black", "color_name": "Galaxy Black", "material": "PLA"}, "Prusament PLA"),
    ({"name": "Prusament Galaxy Black", "color_name": "Galaxy Black", "material": "PLA"}, "Prusament PLA"),
    ({"name": "  Prusament  PETG   Jet Black 1kg ", "color_name": "jet black", "material": "PETG"}, "Prusament PETG"),
    ({}, ""), (None, ""),
], ids=["cf-variant", "colour-not-in-name", "no-line-before-colour", "spacing-and-case", "empty", "none"])
def test_odd_pages_fall_back_to_the_material(fil, profile):
    assert external_parsers.prusament_profile(fil) == profile


def test_the_parser_returns_the_profile_and_where_it_came_from():
    blob = {"ff_goods_id": 17644, "weight": 970, "spool_weight": 193,
            "filament": {"color_name": "Oh My Gold", "color_rgb": "#daa900", "material": "PLA Blend",
                         "name": "Prusament PLA Blend Oh My Gold 1kg", "he_min": 205, "he_max": 225,
                         "hb_min": 40, "hb_max": 60}}
    page = Mock(ok=True, text="<script>var spoolData = '" + json.dumps(blob) + "';</script>")
    with patch.object(external_parsers.requests, "get", return_value=page):
        [res] = external_parsers.PrusamentParser.search("https://prusament.com/spool/17644/3a4e6aaccb")
    assert res["slicer_profile"] == "Prusament PLA Blend", res
    assert res["slicer_profile_source"] == "prusament.com", res
