"""feature/scan-match-pipeline — Prusament-QR scan pipeline.

A physical Prusament spool label encodes a https://prusament.com/spool/<id>/<hash>/
URL. resolve_scan must recognize it as a dedicated `prusament_url` type (matched by
the numeric spool <id>) so /api/identify_scan can either backfill nozzle/bed temps
onto the matching existing filament or onboard a brand-new spool.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logic import resolve_scan  # noqa: E402


def test_resolve_scan_recognizes_prusament_url():
    res = resolve_scan("https://prusament.com/spool/17705/5b1a183b26/")
    assert res == {
        "type": "prusament_url",
        "url": "https://prusament.com/spool/17705/5b1a183b26/",
        "spool_id": "17705",
    }


def test_resolve_scan_prusament_url_without_scheme():
    # Some scanners strip the scheme; the substring match should still catch it.
    res = resolve_scan("prusament.com/spool/42/abc/")
    assert res["type"] == "prusament_url"
    assert res["spool_id"] == "42"


def test_resolve_scan_prusament_url_is_case_insensitive():
    res = resolve_scan("HTTPS://PRUSAMENT.COM/SPOOL/999/DEADBEEF/")
    assert res["type"] == "prusament_url"
    assert res["spool_id"] == "999"


def test_resolve_scan_generic_url_is_not_mistaken_for_prusament():
    res = resolve_scan("https://example.com/whatever/")
    assert res["type"] != "prusament_url"
