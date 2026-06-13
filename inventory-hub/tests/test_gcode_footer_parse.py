"""Tests for the surviving G-code footer-parse chain used by FCC's own
FINISHED-completion deduct: `prusalink_api.download_gcode_content` (download +
transparent `.bgcode` decode) feeding `prusalink_api.parse_footer_usage` (the
slicer's full per-tool `filament used [g]` footer → `{tool_index: grams}`).

The footer is exactly what FilaBridge billed (same array, no M486 handling), so
this is the COMPLETE-print deduct source post-cutover. These two functions
outlived the FilaBridge error-recovery surface (`download_gcode_and_parse_usage`
/ the `/api/fb_*` endpoints) retired in Phase E Slice 3; this file preserves the
regression coverage that previously rode on the now-deleted recovery parser —
most importantly that the footer must be lifted out of a binary `.bgcode`
container (the OLD text parser read ZERO on the real binary fleet).
"""
from unittest.mock import patch

import prusalink_api as pa


def test_footer_parse_ascii():
    """Plain-ASCII gcode: the footer parses straight through the decode chain
    (download_gcode_content passes ASCII through; parse_footer_usage reads the
    per-tool array)."""
    ascii_bytes = b"; metadata block\n; filament used [g] = 3.14, 5.22\n; end"
    with patch("prusalink_api._download_file_bytes", return_value=ascii_bytes):
        content = pa.download_gcode_content("1.2.3.4", "key", "test.gcode")
    assert pa.parse_footer_usage(content) == {0: 3.14, 1: 5.22}


def test_footer_parse_bgcode_roundtrip():
    """The real fleet slices to binary .bgcode — the footer lives in the
    PrintMeta block, so a naive text read returns ZERO. download_gcode_content
    must decode the container so parse_footer_usage can lift the footer. This is
    the regression the old ASCII-only parser structurally couldn't catch."""
    import struct

    def _block(btype, payload, enc=0):  # uncompressed block (comp=0, checksum=0)
        return struct.pack("<HHI", btype, 0, len(payload)) + struct.pack("<H", enc) + payload

    body = b"M83\nT0\nG1 X10 E5\nG1 X20 E5\n"
    meta = b"filament used [mm] = 10\nfilament used [g] = 25\n"
    raw = (b"GCDE" + struct.pack("<I", 1) + struct.pack("<H", 0)
           + _block(4, meta) + _block(1, body))  # PrintMeta, GCode

    with patch("prusalink_api._download_file_bytes", return_value=raw):
        content = pa.download_gcode_content("1.2.3.4", "key", "real.bgcode")
    assert pa.parse_footer_usage(content) == {0: 25.0}  # footer lifted from the binary container


def test_download_gcode_content_download_failure_returns_none():
    """A failed download surfaces as None (the completion deduct then defers /
    retries rather than billing a phantom)."""
    with patch("prusalink_api._download_file_bytes", return_value=None):
        assert pa.download_gcode_content("1.2.3.4", "key", "x.bgcode") is None
