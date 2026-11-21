"""Group 64.6: the G-code walk counts an MMU print as the slicer counts one.

PrusaSlicer's GCodeProcessor (version_2.9.4 and 2.9.7, read for this): when a
print is single extruder multi material with more than one extruder (its
`nozzle_diameter` list) and a wipe tower, apply_config keeps the parking position
and the extra loading move, and UsedFilaments::increase_caches starts each extruder
owing the parking distance (its filament waits parked in the MMU, so its first load
is no filament used) and counts the first counted move after each tool change the
extra loading move less: the wipe tower unloads the parking distance before a tool
change (toolchange_Unload) and loads parking + extra back after it
(toolchange_Load), and the two balance. The processor starts on extruder 0, so a T0
first is no tool change. An excluded move or a flush doesn't go through
increase_caches, so it never takes the tool change's turn.

Without the rule FCC's walk counted each first load as filament (+32 mm per tool on
a Core One MMU3 profile) and came up 52 mm short after every reload, so a
multi-colour MMU print's walk drifted far from its footer: its 2% WARNING on every
head, and a cancel's shares skewed. The rule is read from the file's own settings:
a plain .gcode's config block, or the copy bgcode_decode appends from a .bgcode's
Slicer-Metadata block (only for an MMU print). The repo's own Core One fixture is
an MMU3 print: it lands on its footer (test_deduct_accuracy_56).

Each figure below is the slicer's count of its file (worked from increase_caches,
and checked against a simulation of it).
"""
from __future__ import annotations

import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import bgcode_decode  # noqa: E402
import prusalink_api  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE1 = os.path.join(_HERE, "fixtures", "sample.bgcode")
# A real multi-colour MMU3 slice (2026-11-20): three 15 mm cubes on filaments 1-3,
# sliced with PrusaSlicer 2.9.7 from the Core One MMU3 settings in sample.bgcode's
# Slicer-Metadata block, in a throwaway --datadir (how to rebuild it: the README in
# the git-ignored .captures/mmu3-three-cubes-2026-11-20/, beside its inputs).
_THREE_CUBES = os.path.join(_HERE, "fixtures", "mmu3_three_cubes.bgcode")


def _config(semm="1", wipe_tower="1", park="84", extra="-52", nozzles="0.4,0.4,0.4"):
    """A config block as PrusaSlicer ends a plain .gcode with it."""
    return ("; prusaslicer_config = begin\n"
            f"; extra_loading_move = {extra}\n"
            "; filament_minimal_purge_on_wipe_tower = 15,15,15\n"
            f"; nozzle_diameter = {nozzles}\n"
            f"; parking_pos_retraction = {park}\n"
            f"; single_extruder_multi_material = {semm}\n"
            f"; wipe_tower = {wipe_tower}\n"
            "; wipe_tower_x = 170\n"
            "; prusaslicer_config = end\n")


def _footer(mms):
    """A footer whose grams equal its millimetres, so `whole` reads in mm."""
    vals = ", ".join(str(m) for m in mms)
    return f"; filament used [mm] = {vals}\n; filament used [g] = {vals}\n"


# The wipe tower's tool change on a Core One MMU3 profile (parking 84, extra -52):
# the unload pulls the parking distance back in four moves, the load pushes
# parking + extra (32 mm) back in three (0.2 / 0.7 / 0.1 of it).
_UNLOAD = "G1 E-15\nG1 E-48.3\nG1 E-13.8\nG1 E-6.9\n"
_LOAD = "G1 E6.4 F1000\nG1 X10 E22.4\nG1 X20 E3.2\n"
# T1 loads and prints 100, T2 loads and prints 50, T1 is loaded again and prints 30.
_THREE_CHANGES = ("M83\nT1\n" + _LOAD + "G1 X30 E100\n" + _UNLOAD
                  + "T2\n" + _LOAD + "G1 X40 E50\n" + _UNLOAD
                  + "T1\n" + _LOAD + "G1 X50 E30\n")


def _walk(text, cut=None):
    mmu = prusalink_api._mmu_rule(text)
    cuts, (whole, _saw) = prusalink_api._walk_extrusion(text, [cut] if cut is not None else [], 0, mmu=mmu)
    rounded = {t: round(mm, 6) for t, mm in whole.items()}
    if cut is None:
        return rounded
    return {t: round(mm, 6) for t, mm in cuts[0][0].items()}, rounded


def test_an_mmu_print_counts_each_filament_as_the_slicer_does():
    """T1 130 (100 + 30), T2 50: every load pays the parking distance back and is
    no filament used. Without the rule the walk counted T1's first load and lost 52 mm
    at its reload (132), and counted T2's load (82)."""
    text = _THREE_CHANGES + _footer([0, 130, 50]) + _config()
    assert _walk(text) == {1: 130.0, 2: 50.0}
    plain = _THREE_CHANGES + _footer([0, 130, 50])
    assert _walk(plain) == {1: 132.0, 2: 82.0}


def test_measure_uses_the_rule_so_an_mmu_print_walks_to_its_footer():
    text = _THREE_CHANGES + _footer([0, 130, 50]) + _config()
    measured = prusalink_api.measure_filament_usage(text, [1.0])
    assert measured["whole"] == {1: pytest.approx(130.0), 2: pytest.approx(50.0)}
    assert measured["partials"][0] == measured["footer"] == {1: 130.0, 2: 50.0}


def test_a_cut_after_an_unload_charges_what_the_tool_printed():
    """Right after T1's unload (before T2): T1 printed 100. The unload's 84 mm is a
    debt that was never counted (the load that brought it forward paid the slicer's
    parking debt), so it comes off nothing: off a cut it would have charged 16."""
    before = "M83\nT1\n" + _LOAD + "G1 X30 E100\n" + _UNLOAD
    text = _THREE_CHANGES + _footer([0, 130, 50]) + _config()
    assert text.startswith(before)
    cut, whole = _walk(text, cut=len(before.encode("utf-8")))
    assert cut == {1: 100.0} and whole == {1: 130.0, 2: 50.0}


def test_a_first_filament_of_t0_is_no_tool_change():
    """The processor starts on extruder 0, so a T0 first changes nothing and its
    first load counts no extra loading move: the whole parking distance (84 mm) is
    left out, not 32, and the slicer's footer says 48 for 132 pushed out. FCC counts
    the same, because a cancel is charged its share of that footer."""
    text = "M83\nT0\n" + _LOAD + "G1 X30 E100\n" + _footer([48]) + _config()
    assert _walk(text) == {0: 48.0}


def test_an_mmu_file_with_no_t_at_all_folds_onto_its_footers_tool():
    """No T: the walk counts on the slicer's extruder 0 (owing the parking distance,
    no tool change), and measure folds it onto the footer's sole tool, as before."""
    text = "M83\n" + _LOAD + "G1 X30 E100\n" + _footer([0, 48]) + _config()
    measured = prusalink_api.measure_filament_usage(text, [1.0])
    assert measured["whole"] == {1: pytest.approx(48.0)}


def test_excluded_moves_flushes_and_still_moves_never_take_the_tool_changes_turn():
    """A move the slicer doesn't send through increase_caches (an excluded move, a
    flush) or one that doesn't move E leaves the tool change for the next counted
    move. The slicer's flag is one for every extruder, so when another T comes
    first, the turn is that tool's: T1 here only flushes 1 before T2 is loaded, and
    its own load later still gets the extra loading move (T1 51, T2 100). Taken by
    T1's excluded move, T1's reload would have counted 52 mm too many (102)."""
    tail = "T2\n" + _LOAD + "G1 X30 E100\nT1\n" + _LOAD + "G1 X40 E50\n"
    body = "M83\nT1\n;EXCLUDE_E_START\nG1 E8\n;EXCLUDE_E_END\n;FLUSH_START\nG1 X1 E1\n;FLUSH_END\n" + tail
    assert _walk(body + _footer([0, 51, 100]) + _config()) == {1: 51.0, 2: 100.0}
    still = "M83\nT1\nG1 X1 E0\n" + tail
    assert _walk(still + _footer([0, 50, 100]) + _config()) == {1: 50.0, 2: 100.0}
    # One tool: the turn taken early or late gives the same count (the debt rides
    # through an excluded move or a flush unchanged): the flush's 1 and 100 printed.
    one = ("M83\nT1\n;EXCLUDE_E_START\nG1 E8\n;EXCLUDE_E_END\n"
           ";FLUSH_START\nG1 X1 E1\n;FLUSH_END\n" + _LOAD + "G1 X30 E100\n")
    assert _walk(one + _footer([0, 101]) + _config()) == {1: 101.0}


_RULE_OFF = [
    ("not single extruder multi material", _config(semm="0")),
    ("no wipe tower", _config(wipe_tower="0")),
    ("one extruder", _config(nozzles="0.4")),
    ("a parking distance that isn't a number", _config(park="nil")),
    ("no config block", ""),
    ("the settings outside the config block",
     "; single_extruder_multi_material = 1\n; wipe_tower = 1\n; parking_pos_retraction = 84\n"
     "; extra_loading_move = -52\n; nozzle_diameter = 0.4,0.4,0.4\n"),
]


@pytest.mark.parametrize("why, config", _RULE_OFF, ids=[why for why, _cfg in _RULE_OFF])
def test_the_rule_is_off_unless_the_slicer_would_apply_it(why, config):
    """apply_config sets the parking position only for single extruder multi material
    with more than one extruder and a wipe tower; FCC reads the settings only from
    the config block. (Red on the old walk only for want of _mmu_rule: the plain
    count is what it always gave.)"""
    text = _THREE_CHANGES + _footer([0, 132, 82]) + config
    assert prusalink_api._mmu_rule(text) is None, why
    assert _walk(text) == {1: 132.0, 2: 82.0}, why


def test_the_core_one_mmu3_capture_walks_to_its_footers_millimetres():
    """The real file (a Core One MMU3 profile print, its first filament T1): 2130.152
    mm against its footer's 2130.15. It walked 30 mm over without the rule."""
    if not os.path.isfile(_CORE1):
        pytest.skip("sample.bgcode fixture not present")
    with open(_CORE1, "rb") as fh:
        g = bgcode_decode.decode_bgcode(fh.read())["gcode"]
    assert prusalink_api._mmu_rule(g) == (84.0, -52.0)
    foot = prusalink_api._parse_weights_from_match(prusalink_api._GCODE_MM_RE.search(g))
    assert foot == {1: 2130.15}
    measured_mm = _walk(g)
    assert set(measured_mm) <= {0, 1} and measured_mm[1] == pytest.approx(2130.15, abs=0.01), measured_mm


def test_a_real_multi_colour_mmu3_slice_walks_to_its_footer(monkeypatch):
    """The slicer's own multi-colour MMU3 output: T0, T1, T2, 54 tool changes, each
    an unload of the parking distance and a load of 32 mm. Every tool walks to its
    footer's millimetres within 0.01 mm (0.005 today), so the 2% check has nothing to
    say; the walk before the rule came 1216 / 644 / 592 mm short (52 mm a reload), a
    WARNING on every head. Its first filament is T0: no tool change for its first
    load (test_a_first_filament_of_t0_is_no_tool_change)."""
    with open(_THREE_CUBES, "rb") as fh:
        g = bgcode_decode.decode_bgcode(fh.read())["gcode"]
    assert prusalink_api._mmu_rule(g) == (84.0, -52.0)
    foot = prusalink_api._parse_weights_from_match(prusalink_api._GCODE_MM_RE.search(g))
    assert foot == {0: 1475.82, 1: 1040.46, 2: 924.98}
    walked = _walk(g)
    assert set(walked) == {0, 1, 2}
    for t, want in foot.items():
        assert walked[t] == pytest.approx(want, abs=0.01), (t, walked, foot)
    _cuts, (plain, _saw) = prusalink_api._walk_extrusion(g, [], 0)
    assert all(plain[t] < foot[t] - 500 for t in foot), plain
    measured = prusalink_api.measure_filament_usage(g, [1.0])
    assert measured["footer"] == {0: 4.4, 1: 3.1, 2: 2.76}
    assert measured["whole"] == {t: pytest.approx(v, abs=1e-3) for t, v in measured["footer"].items()}
    import print_deduct  # noqa: E402  (the 2% check, as a cancel runs it)
    import state  # noqa: E402
    lines = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: lines.append(msg))
    pm = {f"MMU-{n + 1}": {"printer_name": "MMU", "position": n} for n in range(5)}
    monkeypatch.setattr(print_deduct.locations_db, "get_active_printer_map", lambda: pm)
    print_deduct._warn_parse_gap("MMU", "cubes.bgcode", measured)
    assert [m for m in lines if "G-code walk" in m] == []


# --------------------------------------------------------------------------- #
# bgcode_decode carries the settings over from the Slicer-Metadata block        #
# --------------------------------------------------------------------------- #

def _block(btype, payload, enc=0):
    return struct.pack("<HHI", btype, 0, len(payload)) + struct.pack("<H", enc) + payload


def _bgcode(slicer_meta):
    header = b"GCDE" + struct.pack("<I", 1) + struct.pack("<H", 0)
    body = (_THREE_CHANGES).encode()
    print_meta = b"filament used [mm] = 0, 130, 50\nfilament used [g] = 0, 130, 50\n"
    return header + _block(2, slicer_meta) + _block(4, print_meta) + _block(1, body)


_SLICER_META = (b"extra_loading_move=-52\nfilament_minimal_purge_on_wipe_tower=15,15,15\n"
                b"nozzle_diameter=0.4,0.4,0.4\nparking_pos_retraction=84\n"
                b"single_extruder_multi_material=1\nwipe_tower=1\nwipe_tower_x=170\n")


def test_decode_appends_an_mmu_prints_settings_past_the_footer():
    g = bgcode_decode.decode_bgcode(_bgcode(_SLICER_META))["gcode"]
    assert g.endswith(
        "; filament used [g] = 0, 130, 50\n"
        "; prusaslicer_config = begin\n"
        "; single_extruder_multi_material = 1\n; wipe_tower = 1\n; parking_pos_retraction = 84\n"
        "; extra_loading_move = -52\n; nozzle_diameter = 0.4,0.4,0.4\n"
        "; prusaslicer_config = end\n"), g[-400:]
    assert prusalink_api._mmu_rule(g) == (84.0, -52.0)
    assert prusalink_api.measure_filament_usage(g, [1.0])["whole"] == {1: pytest.approx(130.0),
                                                                       2: pytest.approx(50.0)}


def test_decode_leaves_every_other_file_as_it_was():
    """Not an MMU print: nothing is appended, so its text (and every progress
    fraction mapped on it) is exactly what it was."""
    other = _SLICER_META.replace(b"single_extruder_multi_material=1", b"single_extruder_multi_material=0")
    g = bgcode_decode.decode_bgcode(_bgcode(other))["gcode"]
    assert g == _THREE_CHANGES + "\n; filament used [mm] = 0, 130, 50\n; filament used [g] = 0, 130, 50\n"
