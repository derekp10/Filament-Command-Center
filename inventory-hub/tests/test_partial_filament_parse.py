"""Unit tests for prusalink_api.parse_partial_filament_usage — the cancelled-
print per-toolhead partial-deduction core (FilaBridge absorption design §9.2).

The load-bearing case is multi-tool: a toolhead never selected before the
cancel must deduct ZERO (Derek's XL untouched-head=0 invariant). These are pure
parser tests — no server / network.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import prusalink_api  # noqa: E402


# A long single-line comment used as a byte "dead zone" at the cancel point, so
# the reached-byte boundary is robust to float rounding: the cut lands inside
# this comment (no extrusion), many bytes away from any G1 E move on either side.
_DEAD = "; " + ("pad " * 30) + "\n"   # ~120 bytes, no extrusion


def _split_gcode(prefix_body, suffix_body, footer):
    """Assemble gcode = prefix_body + dead-zone + suffix_body + footer, and
    return (gcode, reached_fraction) where the fraction targets the MIDDLE of
    the dead zone — i.e. everything in prefix_body is "reached", nothing in
    suffix_body is."""
    gcode = prefix_body + _DEAD + suffix_body + footer
    cut_byte = len(prefix_body.encode("utf-8")) + len(_DEAD.encode("utf-8")) // 2
    frac = cut_byte / len(gcode.encode("utf-8"))
    return gcode, frac


def test_multitool_untouched_head_deducts_zero():
    """THE invariant: T1 only extrudes after the cancel point, so it must be
    absent (0) from the result; T0 reports its real partial grams."""
    prefix = (
        "M83\n"            # relative extrusion
        "T0\n"
        "G1 X10 E5\n"      # T0 +5mm
        "G1 X20 E5\n"      # T0 +5mm  -> 10mm
    )
    suffix = (
        "T1\n"
        "G1 X0 E8\n"       # T1 +8mm  (never reached)
        "G1 X10 E8\n"      # T1 +8mm  -> 16mm
    )
    footer = (
        "; filament used [mm] = 10, 16\n"
        "; filament used [g] = 0.02, 0.048\n"
    )
    gcode, frac = _split_gcode(prefix, suffix, footer)
    usage = prusalink_api.parse_partial_filament_usage(gcode, frac)

    assert 1 not in usage, f"untouched tool 1 must be absent (0); got {usage}"
    # T0: 10mm * (0.02g / 10mm) = 0.02g
    assert abs(usage.get(0, 0.0) - 0.02) < 1e-6, usage


def test_relative_e_single_tool_partial():
    prefix = "M83\nT0\nG1 X10 E100\n"        # 100mm reached
    suffix = "G1 X20 E100\n"                  # another 100mm (not reached)
    footer = "; filament used [mm] = 200\n; filament used [g] = 0.4\n"
    gcode, frac = _split_gcode(prefix, suffix, footer)
    usage = prusalink_api.parse_partial_filament_usage(gcode, frac)
    # g/mm = 0.4/200 = 0.002; reached 100mm -> 0.2g
    assert abs(usage.get(0, 0.0) - 0.2) < 1e-6, usage


def test_absolute_e_deltas():
    prefix = (
        "M82\n"             # absolute extrusion (the default)
        "T0\n"
        "G92 E0\n"
        "G1 X10 E5\n"       # delta 5 -> 5mm
        "G1 X20 E12\n"      # delta 7 -> 12mm
    )
    suffix = "G1 X30 E20\n"                    # delta 8 (not reached)
    footer = "; filament used [mm] = 20\n; filament used [g] = 0.04\n"
    gcode, frac = _split_gcode(prefix, suffix, footer)
    usage = prusalink_api.parse_partial_filament_usage(gcode, frac)
    # g/mm = 0.04/20 = 0.002; reached 12mm -> 0.024g
    assert abs(usage.get(0, 0.0) - 0.024) < 1e-6, usage


def test_g92_reset_accumulates_across_origin_reset():
    prefix = (
        "M82\nT0\n"
        "G1 X10 E5\n"       # 5mm
        "G92 E0\n"          # reset extruder origin
        "G1 X20 E3\n"       # 3mm from reset -> physical total 8mm
    )
    suffix = "G1 X30 E9\n"
    footer = "; filament used [mm] = 8\n; filament used [g] = 0.016\n"
    gcode, frac = _split_gcode(prefix, suffix, footer)
    usage = prusalink_api.parse_partial_filament_usage(gcode, frac)
    # 8mm * (0.016/8) = 0.016g
    assert abs(usage.get(0, 0.0) - 0.016) < 1e-6, usage


def test_cancel_before_first_extrusion_is_empty():
    # reached_fraction ~0 -> nothing extruded yet.
    gcode = (
        "M83\nT0\nG1 X10 E5\n"
        "; filament used [mm] = 5\n; filament used [g] = 0.01\n"
    )
    assert prusalink_api.parse_partial_filament_usage(gcode, 0.0) == {}
    assert prusalink_api.parse_partial_filament_usage(gcode, 0.001) == {}


def test_full_file_matches_footer_totals():
    prefix = "M83\nT0\nG1 X10 E5\nG1 X20 E5\n"
    suffix = "T1\nG1 X0 E8\nG1 X10 E8\n"
    footer = "; filament used [mm] = 10, 16\n; filament used [g] = 0.02, 0.048\n"
    gcode = prefix + suffix + footer
    usage = prusalink_api.parse_partial_filament_usage(gcode, 1.0)
    assert abs(usage.get(0, 0.0) - 0.02) < 1e-6, usage
    assert abs(usage.get(1, 0.0) - 0.048) < 1e-6, usage


def test_no_footer_metadata_returns_empty():
    gcode = "M83\nT0\nG1 X10 E5\nG1 X20 E5\n"   # extrusion but no footer
    assert prusalink_api.parse_partial_filament_usage(gcode, 0.5) == {}


def test_mm_to_g_uses_slicer_ratio_not_assumed_density():
    # Two different filaments (different g/mm) prove the ratio is per-tool and
    # taken from the footer, not a hard-coded density.
    prefix = "M83\nT0\nG1 E500\n"              # tool0 500mm reached
    suffix = "T1\nG1 E500\n"                   # tool1 not reached
    footer = (
        "; filament used [mm] = 1000, 1000\n"
        "; filament used [g] = 2.0, 3.0\n"     # tool0 0.002 g/mm, tool1 0.003 g/mm
    )
    gcode, frac = _split_gcode(prefix, suffix, footer)
    usage = prusalink_api.parse_partial_filament_usage(gcode, frac)
    assert abs(usage.get(0, 0.0) - 1.0) < 1e-6, usage   # 500 * 0.002
    assert 1 not in usage, usage


def test_empty_input_is_empty():
    assert prusalink_api.parse_partial_filament_usage("", 0.5) == {}
