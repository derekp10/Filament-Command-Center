"""Tests for the binary-gcode (.bgcode) decoder.

Derek's whole fleet slices to binary G-code, so the cancelled-print prefix-parse
depends on decoding it back to ASCII. The strongest test is a real-data
round-trip: `tests/fixtures/sample.bgcode` is a real file pulled from the live
Core One (a single-material MMU calibration print); its slicer footer says tool
index 1 used 6.35 g / 2130.15 mm. A correct decode → prefix-parse at 100% must
reproduce that within slicer-estimate tolerance. Focused unit vectors cover the
heatshrink + MeatPack + block-walk paths in isolation.
"""
from __future__ import annotations

import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import bgcode_decode  # noqa: E402
import prusalink_api  # noqa: E402

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample.bgcode")
_have_fixture = os.path.exists(_FIXTURE)


# --------------------------------------------------------------------------
# magic detection
# --------------------------------------------------------------------------

def test_is_bgcode():
    assert bgcode_decode.is_bgcode(b"GCDE\x01\x00\x00\x00") is True
    assert bgcode_decode.is_bgcode(b"; normal ascii gcode\nG1 X1 E1\n") is False
    assert bgcode_decode.is_bgcode("GCDE....") is True   # str form
    assert bgcode_decode.is_bgcode(b"") is False


def test_decode_non_bgcode_raises():
    with pytest.raises(ValueError):
        bgcode_decode.decode_bgcode(b"not a bgcode file")


# --------------------------------------------------------------------------
# heatshrink
# --------------------------------------------------------------------------

def test_heatshrink_literals():
    # "Hi" as two heatshrink literals: [tag=1][0x48][tag=1][0x69] packed MSB-first
    # → 0xA4 0x5A 0x40 (trailing zero pad ends the stream cleanly).
    assert bgcode_decode.heatshrink_decode(b"\xA4\x5A\x40", 11, 4) == b"Hi"


# --------------------------------------------------------------------------
# MeatPack
# --------------------------------------------------------------------------

def test_meatpack_command_and_pack():
    # FF FF FB = enable packing; then packed bytes with literal escapes decode
    # to "M73 P0" (verified against the real stream).
    data = bytes([0xFF, 0xFF, 0xFB, 0x7F, 0x4D, 0xF3, 0x20, 0x0F, 0x50])
    out, packing, no_spaces = bgcode_decode.meatpack_decode(data)
    assert out == b"M73 P0"
    assert packing is True


def test_meatpack_nospaces_maps_space_slot_to_E():
    # Enable packing + no-spaces, then a packed byte whose low nibble is the
    # space slot (0x0B) must decode to 'E' (the no-spaces repurpose), high nibble
    # 'X' (0x0E). Byte = (0x0E << 4) | 0x0B = 0xEB → "EX".
    data = bytes([0xFF, 0xFF, 0xFB, 0xFF, 0xFF, 0xF7, 0xEB])
    out, _, no_spaces = bgcode_decode.meatpack_decode(data)
    assert no_spaces is True
    assert out == b"EX"


def test_meatpack_passthrough_when_disabled():
    out, _, _ = bgcode_decode.meatpack_decode(b"; hi\n", packing=False)
    assert out == b"; hi\n"


# --------------------------------------------------------------------------
# synthetic bgcode (compression=none, encoding=none) — block walk + footer
# --------------------------------------------------------------------------

def _block(btype, payload, enc=0):
    # uncompressed block: type, comp=0, uncompressed_size, encoding param, data
    return struct.pack("<HHI", btype, 0, len(payload)) + struct.pack("<H", enc) + payload


def _synth_bgcode(gcode_body: bytes, print_meta: bytes) -> bytes:
    # checksum_type=0 → no CRC trailer on blocks
    header = b"GCDE" + struct.pack("<I", 1) + struct.pack("<H", 0)
    return header + _block(4, print_meta) + _block(1, gcode_body)  # PrintMeta, GCode


def test_synthetic_decode_block_walk_and_footer():
    body = b"M83\nT0\nG1 X10 E5\nG1 X20 E5\n"
    meta = b"estimated printing time=1h\nfilament used [mm] = 10\nfilament used [g] = 25\n"
    raw = _synth_bgcode(body, meta)
    dec = bgcode_decode.decode_bgcode(raw)
    # G-code body recovered (comp/enc none → verbatim).
    assert "G1 X10 E5" in dec["gcode"]
    # Footers lifted out of the PrintMeta block and appended for the parser.
    assert "filament used [g] = 25" in dec["gcode"]
    assert dec["filament_g"] == "25" and dec["filament_mm"] == "10"
    # The whole thing parses: tool 0 extruded 10mm * (25g/10mm) = 25g.
    usage = prusalink_api.parse_partial_filament_usage(dec["gcode"], 1.0)
    assert abs(usage.get(0, 0) - 25.0) < 1e-6


def test_progress_mapping_bounds():
    raw = _synth_bgcode(b"G1 X1 E1\n" * 50, b"filament used [mm] = 1\nfilament used [g] = 1\n")
    dec = bgcode_decode.decode_bgcode(raw)
    assert bgcode_decode.progress_to_decoded_fraction(dec, 0.0) == 0.0
    assert bgcode_decode.progress_to_decoded_fraction(dec, 1.0) == 1.0
    mid = bgcode_decode.progress_to_decoded_fraction(dec, 0.5)
    assert 0.0 <= mid <= 1.0


def test_progress_spans_gcode_not_whole_file():
    """Regression (2026-06-12): when a big (incompressible PNG) thumbnail sits
    BEFORE the G-code, a mid-print cancel must NOT map to decoded 0. `progress`
    is progress through the G-code, not a whole-compressed-file byte offset.

    Here the single G-code block spans compressed bytes [8000, 10000] of a
    10000-byte file — the thumbnail occupies the first 80%. The OLD code scaled
    `progress * filesize`, so progress 0.5 → byte 5000 ≤ gmap[0][0]=8000 → 0.0
    (a silent 0 g under-deduction — exactly the real Core One ~51% cancel). The
    fix spans `progress` across the G-code's compressed range, so 0.5 → ~0.5."""
    dec = {"gcode": "x" * 1000, "filesize": 10000, "gmap": [(8000, 10000, 0, 1000)]}
    assert bgcode_decode.progress_to_decoded_fraction(dec, 0.0) == 0.0
    assert bgcode_decode.progress_to_decoded_fraction(dec, 1.0) == 1.0
    # progress 0.5 → ~0.5 of the decoded G-code (the old code returned 0.0 here).
    # (No M73 markers in this hand-built dict → exercises the gmap FALLBACK.)
    assert abs(bgcode_decode.progress_to_decoded_fraction(dec, 0.5) - 0.5) < 0.02
    assert abs(bgcode_decode.progress_to_decoded_fraction(dec, 0.25) - 0.25) < 0.02


def test_progress_uses_m73_markers_when_present():
    """The printer's `progress` is the slicer's M73 TIME-based value, so it
    inverts through the file's `M73 P{percent}` markers (exact to the slicer's
    time model) — NOT the byte/gmap mapping. Validated 2026-06-12 against scale
    weights (51%→1.08g, 76%→1.49g = weighed part + a constant skirt/prime)."""
    # Markers 0%@b0, 50%@b200, 100%@b400 over a 500-byte decoded G-code. A gmap is
    # ALSO present (to a different answer) to prove M73 takes precedence.
    dec = {"gcode": "x" * 500, "m73": [(0, 0), (50, 200), (100, 400)],
           "gmap": [(0, 999, 0, 500)]}
    assert bgcode_decode.progress_to_decoded_fraction(dec, 0.0) == 0.0
    assert bgcode_decode.progress_to_decoded_fraction(dec, 1.0) == 1.0
    # 50% → M73 P50 → byte 200 → 0.40 (NOT the gmap's 0.50).
    assert abs(bgcode_decode.progress_to_decoded_fraction(dec, 0.5) - 0.40) < 1e-6
    # 25% interpolates P0@0..P50@200 → byte 100 → 0.20.
    assert abs(bgcode_decode.progress_to_decoded_fraction(dec, 0.25) - 0.20) < 1e-6


# --------------------------------------------------------------------------
# real-data round-trip (the gold test)
# --------------------------------------------------------------------------

def _header():
    return b"GCDE" + struct.pack("<I", 1) + struct.pack("<H", 0)


# --------------------------------------------------------------------------
# robustness: malformed / truncated / adversarial input must NOT crash
# --------------------------------------------------------------------------

def test_decode_corrupt_gcode_block_is_skipped_footer_survives():
    # A GCode block claiming deflate but holding garbage → _decompress raises →
    # the block is skipped, but the (separate, valid) PrintMeta footer survives.
    meta = b"filament used [mm] = 7\nfilament used [g] = 21\n"
    bad_gcode = struct.pack("<HHI", 1, 1, 999) + struct.pack("<I", 5) + struct.pack("<H", 0) + b"\xde\xad\xbe\xef\x00"
    raw = _header() + _block(4, meta) + bad_gcode
    dec = bgcode_decode.decode_bgcode(raw)   # must not raise
    assert dec["filament_g"] == "21"          # footer recovered despite bad block
    assert dec["gmap"] == []                   # the corrupt gcode block contributed nothing


def test_decode_truncated_file_no_crash():
    body = b"M83\nT0\nG1 X10 E5\n"
    meta = b"filament used [mm] = 10\nfilament used [g] = 25\n"
    raw = _synth_bgcode(body, meta)
    for cut in (5, 11, 20, len(raw) // 2, len(raw) - 1):
        dec = bgcode_decode.decode_bgcode(raw[:cut])   # must not raise for any prefix
        assert isinstance(dec, dict) and "gcode" in dec


def test_decode_no_gcode_blocks():
    # Metadata-only file: gmap empty, progress maps to 0 (no extrusion reached).
    raw = _header() + _block(4, b"filament used [mm] = 1\nfilament used [g] = 1\n")
    dec = bgcode_decode.decode_bgcode(raw)
    assert dec["gmap"] == []
    assert bgcode_decode.progress_to_decoded_fraction(dec, 0.5) == 0.0
    assert bgcode_decode.progress_to_decoded_fraction(dec, 1.0) == 0.0


def test_meatpack_state_threads_across_gcode_blocks():
    # Block 1 enables packing (FF FF FB); block 2 is a single packed byte 0x1D
    # (low nibble 0xD='G', high nibble 0x1='1'). Only decodes to "G1" if the
    # packing state carried across the block boundary.
    raw = (_header()
           + _block(1, bytes([0xFF, 0xFF, 0xFB]), enc=2)
           + _block(1, bytes([0x1D]), enc=2))
    dec = bgcode_decode.decode_bgcode(raw)
    assert "G1" in dec["gcode"], repr(dec["gcode"])


# --------------------------------------------------------------------------
# parser: bare G92 + multi-tool attribution
# --------------------------------------------------------------------------

def test_bare_g92_resets_high_water_mark():
    # absolute mode: extrude to E10 (10mm), bare G92 resets E origin to 0,
    # then extrude to E5 (another 5mm). High-water must reset → total 15mm.
    g = ("M82\nG1 E10\nG92\nG1 E5\n"
         "; filament used [mm] = 15\n; filament used [g] = 30\n")
    out = prusalink_api.parse_partial_filament_usage(g, 1.0)
    assert abs(out.get(0, 0) - 30.0) < 1e-6   # 15mm * (30g/15mm)


def test_multi_block_multi_tool_attribution():
    # Two G-code blocks: T0 in block 1, T1 in block 2. Untouched-head invariant:
    # at a fraction reaching only block 1, T1 must be absent (0).
    b1 = b"M83\nT0\nG1 E10\n"
    b2 = b"T1\nG1 E10\n"
    meta = b"filament used [mm] = 10, 10\nfilament used [g] = 20, 20\n"
    raw = _header() + _block(4, meta) + _block(1, b1) + _block(1, b2)
    g = bgcode_decode.decode_bgcode(raw)["gcode"]
    full = prusalink_api.parse_partial_filament_usage(g, 1.0)
    assert abs(full.get(0, 0) - 20.0) < 1e-6 and abs(full.get(1, 0) - 20.0) < 1e-6
    # Reaching only block 1 (T0): T1 untouched → absent.
    block1_frac = len(b1) / len(g.encode("utf-8")) * 0.9
    early = prusalink_api.parse_partial_filament_usage(g, block1_frac)
    assert 1 not in early, early


@pytest.mark.skipif(not _have_fixture, reason="sample.bgcode fixture not present")
def test_real_bgcode_round_trip_matches_footer():
    raw = open(_FIXTURE, "rb").read()
    assert bgcode_decode.is_bgcode(raw)
    dec = bgcode_decode.decode_bgcode(raw)
    g = dec["gcode"]
    # Footer extracted from the (deflate) PrintMeta block.
    assert dec["filament_g"].startswith("0.00, 6.35")
    assert "filament used [g]" in g and "filament used [mm]" in g
    # Real G-code moves recovered (space-less, Prusa no-spaces MeatPack).
    assert "G1X" in g and g.count("\nG1") > 1000
    # Decode → prefix-parse at 100% reproduces the footer (tool 1 = 6.35 g)
    # within slicer-estimate tolerance (~1.3% high; high-water E accounting).
    full = prusalink_api.parse_partial_filament_usage(g, 1.0)
    assert set(full.keys()) == {1}, full
    assert 6.1 < full[1] < 6.7, full
    # Partials are monotonic non-decreasing across the print.
    vals = [prusalink_api.parse_partial_filament_usage(g, f).get(1, 0.0)
            for f in (0.25, 0.5, 0.75, 1.0)]
    assert vals == sorted(vals) and vals[0] > 0 and vals[-1] > vals[0]


@pytest.mark.skipif(not _have_fixture, reason="sample.bgcode fixture not present")
def test_real_bgcode_fetch_fraction_mapping():
    raw = open(_FIXTURE, "rb").read()
    dec = bgcode_decode.decode_bgcode(raw)
    # The big thumbnail/metadata header sits before the G-code, so a low
    # file-progress maps to ~0 decoded (no extrusion reached yet), and full
    # progress maps to the end.
    assert bgcode_decode.progress_to_decoded_fraction(dec, 1.0) == 1.0
    near_end = bgcode_decode.progress_to_decoded_fraction(dec, 0.95)
    assert 0.0 < near_end <= 1.0
