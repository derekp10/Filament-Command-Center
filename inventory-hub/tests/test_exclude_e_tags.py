"""Hotfix 2026-11-02: the slicer's ;EXCLUDE_E tags are no filament used.

PrusaSlicer 2.9.6 added two custom G-code tags, `;EXCLUDE_E_START` and
`;EXCLUDE_E_END`, "allowing to define sections that aren't incorporated into
filament consumption" (its 2.9.6-rc1 release notes). The Core One INDX profile
(2.5.12 and later) wraps the park in them and, each time a tool already used is
picked up again, two moves:

      ;EXCLUDE_E_START
    G1 E1.6 F1200 ; Final lock tool
      ;EXCLUDE_E_END
    ...
      ;EXCLUDE_E_START
    G1 E8 F2400 ; Restore filament retracted by G27 R on park
      ;EXCLUDE_E_END

because the firmware's `G27 ... R8` pulls the filament back 8 mm when it parks a
tool, and no E move in the file says so (with a wipe tower the wrapped moves are
`G1 E2.0` and the rest of the restore). The slicer's footer leaves those moves
out; FCC's walk counted them, 9.6 mm at 228 of the print's 231 pick-ups, so a
small four-colour print (flexi-fox, job 1134, cancelled at 2%) walked to about
2.5x its footer on every head: three "FCC may be misreading this file" WARNINGs,
and a charge of 0.05 g where FCC now charges 0.13 g (the slicer's own count at
that cut is 0.136 g): the excluded millimetres, spread over every pick-up,
swelled each tool's whole-file walk more than its early partial.

The tag is read as PrusaSlicer reads it (GCodeProcessor::process_gcode_line and
process_tags, version_2.9.6): a whole-line comment, any blanks before the ';'
trimmed, the tag right after the ';' as a prefix, case as written. An excluded
move still moves the E position (only its filament isn't counted), so in
absolute E the high-water mark moves by its delta. An older INDX profile wrote
the same words as bare lines, no ';' (the raccoon capture, 2026-10-08): the
slicer of the day counted the moves between them, its footer says so (the walk
lands on it to 0.01%), so a bare line is no tag and those moves still count.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import bgcode_decode  # noqa: E402
import print_deduct  # noqa: E402
import prusalink_api  # noqa: E402
import state  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_HUB = os.path.abspath(os.path.join(_HERE, ".."))
_FLEXI = os.path.join(_HUB, "..", ".captures", "indx-flexi-2026-11-02", "flexi_resliced.bgcode")
# The copy the printer ran for job 1134 ('/usb/FLEXI-~1.BGC'), pulled read-only off
# its USB stick on 2026-11-03: prod's code walked it to the three logged WARNINGs
# (+150.5% / +160.2% / +150.1%) and the 0.05 g card.
_FLEXI_PRINTED = os.path.join(_HUB, "..", ".captures", "indx-flexi-2026-11-02", "flexi_printed.bgcode")


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a, k)))
    return calls


def _footer(mms, grams):
    return ("; filament used [mm] = " + ", ".join(str(m) for m in mms) + "\n"
            "; filament used [g] = " + ", ".join(str(g) for g in grams) + "\n")


# One INDX re-pick-up as the 2.5.14 profile writes it (decoded .bgcode: no-space
# moves, the tags indented): T0 prints 5 mm, the park, then T1 is locked (1.6,
# excluded), gets back the 8 mm the park pulled (excluded), primes 0.7, flushes
# 2.0 (counted, as the slicer counts a flush), retracts and de-retracts 0.7, and
# prints 3 mm: T0 5 mm, T1 5.7 mm, the slicer's own count. (The park's 0.8 mm
# retract on T0 is left out: a retract the file never recovers is the one place
# the walk's net sum and the slicer's count differ, by that retract, before and
# after this fix, so it would only blur what these tests check.)
_PICKUP = (
    "M83\nT0 S1 L0 D0\n"
    "G1X10Y10E5\n"
    "  ; Change Tool0 -> Tool1 (layer 19)\n"
    "  ;EXCLUDE_E_START\n"
    "G27 W3 Z0.6 P2 R8 V30 A1\n"
    "  ;EXCLUDE_E_END\n"
    "P0 S1 L0 D0\n"
    "T1 S1 L0 D0\n"
    "  ;-------Purge Station specific Gcode Start-----\n"
    "      ;EXCLUDE_E_START\n"
    "G1E1.6F1200\n"
    "      ;EXCLUDE_E_END\n"
    "G12 S30\n"
    "      ;EXCLUDE_E_START\n"
    "G1E8F1200\n"
    "      ;EXCLUDE_E_END\n"
    "G1E0.7F1200\n"
    "G91\nM83\n"
    "    ;FLUSH_START\n"
    "G1X0.40E0.6F57.6975\n"
    "G1Y-1.20E1.4F74.1825\n"
    "    ;FLUSH_END\n"
    "    ; RETRACT AFTER TOOLCHANGE START\n"
    "G1Y0E-0.7F2400\n"
    "    ; RETRACT AFTER TOOLCHANGE END\n"
    "  ;-------Purge Station specific Gcode End-----\n"
    "G90\nM83\n"
    "G1E.7F1800\n"
    "G1X20Y20E3\n"
)


def test_e_between_the_slicers_tags_is_not_filament_used():
    g = _PICKUP + _footer([5.0, 5.7], [5.0, 5.7])
    measured = prusalink_api.measure_filament_usage(g, [1.0])
    assert measured["whole"] == {0: pytest.approx(5.0), 1: pytest.approx(5.7)}, measured
    # Counted, the lock and the restore made T1 walk 15.3 mm (+168%), the shape
    # of job 1134's three WARNINGs.


def test_the_wipe_tower_form_of_the_restore_is_left_out_too():
    """The profile's wipe-tower branch wraps `G1 E2.0` and `G1 E{retract_toolchange-2.0}`
    (6 mm here) instead, and counts the de-retract after them."""
    g = ("M83\nT1\n"
         "  ;-------Wipe Tower specific Gcode Start-----\n"
         "    ;EXCLUDE_E_START\n    G1 E2.0 F2100\n    ;EXCLUDE_E_END\n"
         "    G750 Y85 F21000 A\n"
         "    ;EXCLUDE_E_START\n    G1 E6 F1200 ; Restore filament retracted by G27 R on park\n"
         "    ;EXCLUDE_E_END\n"
         "    G1 E0.4 F1200\n"
         "G1X1Y1E3\n"
         + _footer([0, 3.4], [0, 3.4]))
    measured = prusalink_api.measure_filament_usage(g, [1.0])
    assert measured["whole"] == {1: pytest.approx(3.4)}, measured


def test_a_cut_inside_the_tags_counts_nothing_from_them():
    g = _PICKUP + _footer([5.0, 5.7], [5.0, 5.7])
    at = g.index("G1E8F1200\n") + len("G1E8F1200\n")
    cuts, whole = prusalink_api._walk_extrusion(g, [at], 0)
    assert cuts[0][0] == {0: pytest.approx(5.0)}, cuts      # T1 has extruded nothing yet
    assert whole[0][1] == pytest.approx(5.7), whole


def test_unbalanced_tags_do_what_the_slicer_does():
    """A START with no END leaves out the rest of the file; an END with no START
    does nothing (the slicer's flag is set and cleared the same way)."""
    no_end = "M83\nT0\nG1X1E1\n;EXCLUDE_E_START\nG1X2E5\nG1X3E5\n" + _footer([1], [1])
    assert prusalink_api.measure_filament_usage(no_end, [1.0])["whole"] == {0: pytest.approx(1.0)}
    no_start = "M83\nT0\nG1X1E1\n;EXCLUDE_E_END\nG1X2E2\n" + _footer([3], [3])
    assert prusalink_api.measure_filament_usage(no_start, [1.0])["whole"] == {0: pytest.approx(3.0)}


def test_the_tag_is_read_as_the_slicer_reads_it():
    """A whole-line comment, blanks before the ';' trimmed, the tag a prefix right
    after the ';' (PrusaSlicer 2.9.6, GCodeProcessor::process_tags). Anything else
    is no tag: the slicer counts the move, so the walk must too."""
    counted = {
        "bare line, no ';' (the 2026-10-08 INDX profile)": "EXCLUDE_E_START\nG1E1.6F1200\nEXCLUDE_E_END\n",
        "a blank after the ';'": "; EXCLUDE_E_START\nG1E1.6F1200\n; EXCLUDE_E_END\n",
        "lower case": ";exclude_e_start\nG1E1.6F1200\n;exclude_e_end\n",
        "after a move on its line": "G1E0 ;EXCLUDE_E_START\nG1E1.6F1200\nG1E0 ;EXCLUDE_E_END\n",
    }
    for why, body in counted.items():
        g = "M83\nT0\nG1X1E1\n" + body + _footer([2.6], [2.6])
        whole = prusalink_api.measure_filament_usage(g, [1.0])["whole"]
        assert whole[0] == pytest.approx(2.6), (why, whole)
    excluded = {
        "a tab before the ';'": "\t;EXCLUDE_E_START\nG1E1.6F1200\n\t;EXCLUDE_E_END\n",
        "words after the tag": ";EXCLUDE_E_START lock\nG1E1.6F1200\n;EXCLUDE_E_END lock\n",
        "a CRLF file": ";EXCLUDE_E_START\r\nG1E1.6F1200\r\n;EXCLUDE_E_END\r\n",
    }
    for why, body in excluded.items():
        g = "M83\nT0\nG1X1E1\n" + body + _footer([1], [1])
        whole = prusalink_api.measure_filament_usage(g, [1.0])["whole"]
        assert whole[0] == pytest.approx(1.0), (why, whole)


@pytest.mark.parametrize("body, slicer_mm", [
    # From the mark: the restore to 13 adds nothing, the 1 mm after it adds 1.
    ("G1 X10 E5\n;EXCLUDE_E_START\nG1 E13\n;EXCLUDE_E_END\nG1 X20 E14\n", 6.0),
    # A retract before it is still owed: 5, back to 4.2, +8 left out, on to 15 = 7.
    ("G1 X1 E5\nG1 E4.2\n;EXCLUDE_E_START\nG1 E12.2\n;EXCLUDE_E_END\nG1 X2 E15\n", 7.0),
    ("G1 X1 E5\nG1 E4\n;EXCLUDE_E_START\nG1 E5\n;EXCLUDE_E_END\nG1 X2 E8\n", 7.0),
    # An excluded retract: the 1 mm back after it is new filament (5 + 1 + 3 = 9).
    ("G1 X1 E5\n;EXCLUDE_E_START\nG1 E4\n;EXCLUDE_E_END\nG1 E5\nG1 X2 E8\n", 9.0),
])
def test_an_excluded_move_in_absolute_e_moves_the_mark_by_its_own_delta(body, slicer_mm):
    """The slicer moves E for an excluded move and counts none of it; its count is
    the high-water mark of the moves it does count. In absolute E the walk's mark
    therefore moves by the excluded move's own delta (raising it to the move's E
    is that only when the move starts at the mark). Each case is the slicer's count
    (the review of this hotfix checked 4000 random files against it)."""
    g = "M82\nT0\nG92 E0\n" + body + _footer([slicer_mm], [slicer_mm])
    measured = prusalink_api.measure_filament_usage(g, [1.0])
    assert measured["whole"][0] == pytest.approx(slicer_mm), measured


def test_a_tool_change_or_g92_inside_the_tags_still_happens():
    """T and G92 don't read the tag (the slicer's process_T / process_G92 don't):
    the tool still changes and the origin is still reset."""
    g = ("M82\nT0\nG92 E0\nG1 X1 E2\n"
         ";EXCLUDE_E_START\nT1\nG92 E0\nG1 E8\n;EXCLUDE_E_END\n"
         "G1 X2 E9\n"
         + _footer([2, 1], [2, 1]))
    measured = prusalink_api.measure_filament_usage(g, [1.0])
    assert measured["whole"] == {0: pytest.approx(2.0), 1: pytest.approx(1.0)}, measured


def test_a_pick_up_walk_lands_on_its_footer_so_no_warning_is_logged(logs):
    """Through the cancel path: the footer is the slicer's count of the pick-up, so
    the 2% check has nothing to say, and the charge at the end is the footer."""
    g = _PICKUP + _footer([5.0, 5.7], [5.0, 5.7])
    pm = {"RCOI-1": {"printer_name": "INDX", "position": 0},
          "RCOI-2": {"printer_name": "INDX", "position": 1}}
    with patch.object(print_deduct.locations_db, "get_active_printer_map", return_value=pm), \
         patch.object(prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, f: {"gcode": g, "fraction": f}):
        usage, terminal = print_deduct._compute_cancel_usage("INDX", "flexi.bgcode", "J-1", 1.0,
                                                             "1.2.3.4", "k")
    assert terminal is None and usage == {0: 5.0, 1: 5.7}, (usage, terminal)
    assert [m for m, a, k in logs if "G-code walk" in m] == []


@pytest.mark.parametrize("path, footer, early_want", [
    # a local re-slice of job 1134's project (2.5.14 profile, PrusaSlicer 2.9.7)
    pytest.param(_FLEXI, {0: 2.18, 1: 1.35, 2: 0.34, 3: 0.22},
                 {0: 0.030, 1: 0.033, 3: 0.068}, id="resliced"),
    # the file the printer ran: the card Derek re-applied by hand was 0.03 / 0.03 / 0.07
    pytest.param(_FLEXI_PRINTED, {0: 2.17, 1: 1.34, 2: 0.34, 3: 0.22},
                 {0: 0.0297, 1: 0.0328, 3: 0.0680}, id="printed"),
])
def test_the_flexi_fox_capture_walks_to_its_footer_and_its_2pct_cancel_charges_the_share(
        logs, path, footer, early_want):
    """The real 2.5.14-profile file (its footer is the slicer's): every tool walks
    to its footer within 1% (it was 2.5x to 3.1x; what is left is each tool's last
    retract, which the file never recovers), and a cancel at the printer's 2%
    charges 0.13 g, not 0.05 g."""
    if not os.path.isfile(path):
        pytest.skip("the flexi-fox captures are git-ignored (only on Derek's PC)")
    with open(path, "rb") as fh:
        dec = bgcode_decode.decode_bgcode(fh.read())
    g = dec["gcode"]
    at_2pct = bgcode_decode.progress_to_decoded_fraction(dec, 0.02)
    measured = prusalink_api.measure_filament_usage(g, [at_2pct, 1.0])
    assert measured["footer"] == footer
    for t, want in measured["footer"].items():
        assert abs(measured["whole"][t] - want) <= 0.01 * want, (t, measured["whole"])
    assert measured["partials"][1] == measured["footer"]
    early = measured["partials"][0]
    assert set(early) == set(early_want), early              # T2 hadn't printed yet
    for t, want in early_want.items():
        assert early[t] == pytest.approx(want, abs=0.002), early
    assert round(sum(early.values()), 2) == 0.13, early
    pm = {f"RCOI-{n + 1}": {"printer_name": "INDX", "position": n} for n in range(8)}
    with patch.object(print_deduct.locations_db, "get_active_printer_map", return_value=pm):
        print_deduct._warn_parse_gap("INDX", "FLEXI-~1.BGC", measured)
    assert [m for m, a, k in logs if "G-code walk" in m] == []
