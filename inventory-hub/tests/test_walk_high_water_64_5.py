"""Group 64.5: the walk keeps what the slicer keeps.

PrusaSlicer counts the filament a print uses in UsedFilaments::increase_caches
(GCodeProcessor.cpp, version_2.9.4): each extruder keeps the volume it has pulled
back and not yet pushed out again, a move that pushes out pays that off first, and
only what is left over is filament used. That is a high-water mark of each tool's
E position, in either E mode. FCC's walk used to add every signed move in relative
E, so a retract the file never takes back (each tool's last, and the park's at a
cancel) came off its walk, about 0.8 mm per tool under the footer. In absolute E a
G92 forgot a retract still owed (the slicer's G92 E<v> sets the position and
leaves what is owed alone), and G90 / G91 were never read: E is relative under G91
or M83 (extract_absolute_position_on_axis), and G90 sets only the positioning of
every axis, never M83's E mode (process_G90, process_M83).

Each figure below is the slicer's own count of its file. A cut (a cancel's point)
counts what each tool pushed out less a retract still pending there (pulled back
into the tool, not used: the next prime gives it back), except for a tool with
nothing more to push out after it, which keeps its whole count, as the footer
counts it. The real captures are pinned in test_exclude_e_tags.py (flexi-fox, to
0.05 mm per tool) and test_deduct_accuracy_56.py (the raccoon, whole and trimmed).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import prusalink_api  # noqa: E402


def _footer(mms):
    """A footer whose grams equal its millimetres, so `whole` reads in mm."""
    vals = ", ".join(str(m) for m in mms)
    return f"; filament used [mm] = {vals}\n; filament used [g] = {vals}\n"


def _whole(body, mms, default_tool=0):
    _cuts, (walked, _saw) = prusalink_api._walk_extrusion(body + _footer(mms), [], default_tool)
    return {t: round(mm, 6) for t, mm in walked.items()}


def _at(body_before, body_after, mms, default_tool=0):
    """Each tool's mm at a cut right after `body_before`, and over the whole file."""
    g = body_before + body_after + _footer(mms)
    cut = len(body_before.encode("utf-8"))
    cuts, (whole, _saw) = prusalink_api._walk_extrusion(g, [cut], default_tool)
    return ({t: round(mm, 6) for t, mm in cuts[0][0].items()},
            {t: round(mm, 6) for t, mm in whole.items()})


# --------------------------------------------------------------------------- #
# The whole file                                                               #
# --------------------------------------------------------------------------- #

def test_a_last_retract_the_file_never_takes_back_stays_counted():
    """On 7edb245's walk: 4.2 and 2.2 (the retracts netted out)."""
    assert _whole("M83\nT0\nG1 X1 E5\nG1 E-0.8\nT1\nG1 X2 E3\nG1 E-0.8\n", [5, 3]) == {0: 5.0, 1: 3.0}


def test_a_retract_the_file_takes_back_adds_nothing_in_either_mode():
    """Passes by design on the old walk too: the high-water rule never counts an
    un-retract as new filament."""
    assert _whole("M83\nT0\nG1 X1 E5\nG1 E-0.8\nG1 E0.8\nG1 X2 E2\n", [7]) == {0: 7.0}
    assert _whole("M82\nT0\nG92 E0\nG1 X1 E5\nG1 E4.2\nG1 E5\nG1 X2 E7\n", [7]) == {0: 7.0}


def test_g92_keeps_a_retract_still_owed():
    """15 mm out, 0.8 back, G92 E0, then the 0.8 back out (no new filament) and 3
    more: 18. On the old walk the G92 forgot the 0.8, so the un-retract counted: 18.8."""
    assert _whole("M82\nT0\nG92 E0\nG1 X1 E15\nG1 E14.2\nG92 E0\nG1 E0.8\nG1 X2 E3.8\n", [18]) == {0: 18.0}


def test_a_g92_to_another_value_keeps_it_too():
    """G92 E100 after a 0.8 retract: back out to 100.8 is the debt, past it is new."""
    assert _whole("M82\nT0\nG92 E0\nG1 X1 E10\nG1 E9.2\nG92 E100\nG1 E100.8\nG1 X2 E102.8\n",
                  [12]) == {0: 12.0}


def test_a_bare_g92_is_g92_e0_and_keeps_what_is_owed():
    """The slicer's bare G92 moves every origin to where it is, E included: as G92 E0.
    On the old walk the debt went with it: 8."""
    assert _whole("M82\nT0\nG92 E0\nG1 X1 E5\nG1 E4\nG92\nG1 E1\nG1 X2 E3\n", [7]) == {0: 7.0}


def test_a_g92_naming_only_other_axes_leaves_e_alone():
    """G92 X0 Y0 sets X and Y; E goes on from 5 to 7 (2 more). The old walk read it as
    a bare G92 and counted the whole 7 again: 12. A G92 of axes the slicer doesn't
    know (A, B: PrusaSlicer's GH #3510) changes nothing either."""
    assert _whole("M82\nT0\nG92 E0\nG1 X1 E5\nG92 X0 Y0\nG1 X2 E7\n", [7]) == {0: 7.0}
    assert _whole("M82\nT0\nG92 E0\nG1 X1 E5\nG92 A0 B0\nG1 X2 E7\n", [7]) == {0: 7.0}


def test_g91_makes_e_relative_under_m82():
    """A G91 block in an absolute-E file: its E moves add to the position (5, then 2
    and 1 more), and after G90 and G92 E0, 1 more: 9. The old walk read the block's E
    as absolute positions under the mark: 6."""
    body = "M82\nT0\nG92 E0\nG1 X1 E5\nG91\nG1 X1 E2\nG1 X1 E1\nG90\nG92 E0\nG1 X2 E1\n"
    assert _whole(body, [9]) == {0: 9.0}


def test_g90_never_clears_m83():
    """PrusaSlicer's process_G90 sets only the positioning of every axis; M83's E mode
    stays. Read as clearing it, the last two moves would be absolute E2, adding
    nothing: 2. (The INDX profile writes M83 after every G90, so its files can't
    tell; the slicer's own source does. Passes by design on the old walk, which
    never read G90.)"""
    assert _whole("M83\nT0\nG1 X1 E2\nG90\nG1 X2 E2\nG1 X3 E2\n", [6]) == {0: 6.0}
    assert _whole("M83\nT0\nG91\nG1 X1 E2\nG90\nG1 X1 E2\n", [4]) == {0: 4.0}


def test_only_g90_and_g91_switch_the_mode():
    """Zero-padded, as the firmware reads G01 (Group 56.1): G091 is G91. G90.1 / G91.1
    (the arc-centre modes) and G900 are no such line."""
    assert _whole("M82\nT0\nG92 E0\nG091\nG1 X1 E2\nG1 X1 E2\n", [4]) == {0: 4.0}
    assert _whole("M82\nT0\nG92 E0\nG91\nG1 X1 E2\nG90.1\nG1 X1 E2\nG900\nG1 X1 E2\n",
                  [6]) == {0: 6.0}
    assert _whole("M82\nT0\nG92 E0\nG1 X1 E2\nG91.1\nG1 X1 E3\n", [3]) == {0: 3.0}


def test_each_tool_keeps_its_own_position_and_debt():
    """T0 retracts 1 and hands over; T1's moves never pay T0's debt, and T0 pays its
    own when it comes back. (Passes by design on the old walk: relative E netted
    each tool's own moves the same.)"""
    body = ("M83\nT0\nG1 X1 E4\nG1 E-1\nT1\nG1 X2 E1\nG1 E2\nT0\nG1 E1\nG1 X3 E2\n")
    assert _whole(body, [6, 3]) == {0: 6.0, 1: 3.0}


# --------------------------------------------------------------------------- #
# A cut                                                                        #
# --------------------------------------------------------------------------- #

def test_a_retract_pending_at_a_cut_is_not_charged():
    """10 out, 1 back into the tool, then the print stops: 9 used. Relative E always
    said so (it netted); absolute E's mark said 10 on the old walk."""
    assert _at("M83\nT0\nG1 X1 E10\nG1 E-1\n", "G1 E1\nG1 X2 E10\n", [20]) == ({0: 9.0}, {0: 20.0})
    assert _at("M82\nT0\nG92 E0\nG1 X1 E10\nG1 E9\n", "G1 E10\nG1 X2 E20\n", [20]) == ({0: 9.0}, {0: 20.0})


def test_a_retract_pending_across_a_g92_at_a_cut_is_not_charged():
    """The debt G92 keeps is still pending at a cut before it is paid: 15 - 0.8."""
    before = "M82\nT0\nG92 E0\nG1 X1 E15\nG1 E14.2\nG92 E0\n"
    assert _at(before, "G1 E0.8\nG1 X2 E3.8\n", [18]) == ({0: 14.2}, {0: 18.0})


def test_a_tool_with_nothing_more_to_push_out_keeps_its_whole_count():
    """T0 is done before the cut (its last retract never comes back): it is charged its
    whole, as the footer counts it, and T1, which goes on, what it has pushed out."""
    cut, whole = _at("M83\nT0\nG1 X1 E5\nG1 E-0.8\nT1\nG1 X2 E3\n", "G1 X3 E3\n", [5, 6])
    assert cut == {0: 5.0, 1: 3.0} and whole == {0: 5.0, 1: 6.0}


def test_a_cut_after_a_tools_last_filament_charges_its_whole_footer():
    """Through measure_filament_usage: the done tool's share is all of its footer.
    (Passes by design on the old walk: its whole netted the same retract out.)"""
    before = "M83\nT0\nG1 X1 E5\nG1 E-0.8\nT1\nG1 X2 E3\n"
    g = before + "G1 X3 E3\n" + "; filament used [mm] = 5, 6\n; filament used [g] = 2.5, 3.0\n"
    at = (len(before.encode("utf-8")) + 1) / len(g.encode("utf-8"))
    measured = prusalink_api.measure_filament_usage(g, [at])
    assert measured["partials"][0] == {0: 2.5, 1: 1.5}, measured


def test_an_excluded_move_under_relative_e_moves_the_mark_too():
    """The ;EXCLUDE_E rule holds in relative E: an excluded move moves the position
    and the mark alike, so a debt from before it stays a debt. 2 out, 1 back (owed),
    the excluded 8 restore (the INDX re-pick-up's, test_exclude_e_tags._PICKUP),
    then 0.7 and 1 more: 1 of them pays the debt, 0.7 is new: 2.7. (Passes by design
    on the old walk too: relative E netted the same.)"""
    body = "M83\nT1\nG1 X1 E2\nG1 E-1\n;EXCLUDE_E_START\nG1 E8\n;EXCLUDE_E_END\nG1 E0.7\nG1 X2 E1\n"
    assert _whole(body, [0, 2.7], default_tool=1) == {1: 2.7}


# --------------------------------------------------------------------------- #
# The slicer's ;FLUSH tags (PrusaSlicer 2.9.6+)                                #
# --------------------------------------------------------------------------- #

def test_a_pull_back_inside_a_flush_owes_nothing():
    """update_flush_per_extruder adds a flush's push in full and skips a pull-back:
    5, then the flush's 2 and 1 (the 0.5 back counts nothing and owes nothing), then
    1 more: 9. On fb03133's walk the 0.5 was a debt the next moves paid: 8.5. This is
    the re-sliced flexi-fox's T1 (-0.046 mm before this rule, -0.004 after)."""
    body = "M83\nT0\nG1 X1 E5\n;FLUSH_START\nG1 X2 E2\nG1 E-0.5\nG1 X3 E1\n;FLUSH_END\nG1 X4 E1\n"
    assert _whole(body, [9]) == {0: 9.0}


def test_a_flush_pays_no_debt_but_the_debt_still_gets_paid():
    """A retract owed before a flush stays owed through it and is paid after: the
    total is the same either way (8), and so is a cut after the flush (5 + 2 - 0.8).
    Passes by design on the old walk."""
    before = "M83\nT0\nG1 X1 E5\nG1 E-0.8\n;FLUSH_START\nG1 X2 E2\n;FLUSH_END\n"
    assert _at(before, "G1 E0.8\nG1 X3 E1\n", [8]) == ({0: 6.2}, {0: 8.0})


def test_flush_tags_are_read_as_the_exclude_tags_are_and_exclude_wins():
    """Indented, or with words after them, they are tags (process_tags reads a
    custom tag right after the ';' as a prefix); an excluded move inside a flush
    counts nothing (the slicer's !m_exclude_e comes first)."""
    body = ("M83\nT0\n  ;FLUSH_START purge\nG1 X1 E2\nG1 E-1\nG1 X2 E1\n  ;FLUSH_END\n"
            ";FLUSH_START\n;EXCLUDE_E_START\nG1 E8\n;EXCLUDE_E_END\nG1 X3 E2\n;FLUSH_END\n")
    assert _whole(body, [5]) == {0: 5.0}
    # A bare line is no tag: the pull-back is a debt the next push pays.
    bare = "M83\nT0\nFLUSH_START\nG1 X1 E2\nG1 E-1\nG1 X2 E1\nFLUSH_END\n"
    assert _whole(bare, [2]) == {0: 2.0}
