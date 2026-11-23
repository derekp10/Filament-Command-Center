"""Group 65.2 (Derek, 2026-11-03: "Is there any way to have FCC find and flag any bgcode
that uses something new ... I'd like to try to prevent changes in how the systems
perform from sneaking up on us like this in the future"): a finished print's file that
reads differently from the slicer, and a slicer tag FCC doesn't know, each raise one
warning, and no charge changes. Offline.

  (a) The completion check: a finished print's file is walked as a cancel's is, and the
      heads past the 2% / 0.1 g rule share one WARNING (the Group 56 pin that a
      completion says nothing about the walk is turned round in
      test_deduct_accuracy_56.py). The charge stays the footer's.
  (b) The tag scan (print_file_watch.py): tags FCC doesn't know, and tag words written
      without their ';', one WARNING per printer and word per FCC run. A tag joins
      KNOWN_TAGS only with a case here of what the walk does with it.

Red on 1be96d6e (no print_file_watch module, no completion line).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

import app as app_module  # noqa: F401  (registers the routes the deduct imports)
import cancel_fetch_store
import cancel_review_store
import print_deduct
import print_deduct_ledger
import print_file_watch
import prusalink_api
import state
from test_deduct_accuracy_56 import (  # noqa: F401  (logs: a fixture)
    NASTY, NASTY_ESC, _XL_PM, _cancel_usage, _footer, _gap_file, _gap_lines, logs)


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    print_file_watch.forget()
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    yield
    print_file_watch.forget()


# --------------------------------------------------------------------------- #
# (b) The tag shape, from the 2026-11-03 scoping's real lines                  #
# --------------------------------------------------------------------------- #

TAG_LINES = {
    "  ;EXCLUDE_E_START": "EXCLUDE_E_START",
    ";TYPE:External perimeter": "TYPE",
    ";WIDTH:0.45": "WIDTH",
    ";Z:0.2": "Z",
    ";_TOOLCHANGE_TIME12.500000": "_TOOLCHANGE_TIME",
    ";FLUSH_START": "FLUSH_START",
    ";LAYER_CHANGE\r": "LAYER_CHANGE",          # a CR LF file
    ";PURGE_START": "PURGE_START",
}
NOT_TAGS = [
    ";G29 P1 X150 Y0 W100 H20 C ; probe near purge place",
    ";PET-family (PET/PETG/*-CF...)…",
    ";low-temp materials…",
    ";0.2",
    "; Change Tool0 -> Tool1 (layer 19)",
    ";-------Purge Station specific Gcode Start-----",
    "; RETRACT AFTER TOOLCHANGE START",
    ";M73 P10 R5",
    ";T1",
    "G1 X10 E1 ;TYPE:Infill",                   # a comment after a move: no tag, as the walk reads it
]
BARE_LINES = {
    "EXCLUDE_E_START": "EXCLUDE_E_START",
    "  EXCLUDE_E_END  \r": "EXCLUDE_E_END",
    "PURGE_START": "PURGE_START",
}
NOT_BARE = ["G1 X10 Y10", "M83", "T0", "PRINT_START EXTRUDER=200", "G92 E0"]


@pytest.mark.parametrize("line,name", list(TAG_LINES.items()))
def test_a_tag_shaped_line_reads_as_its_tag(line, name, monkeypatch):
    monkeypatch.setattr(print_file_watch, "KNOWN_TAGS", {})
    assert print_file_watch.find_tags("M83\n" + line + "\nG1 E1\n") == {"unknown": [name], "bare": []}


@pytest.mark.parametrize("line", NOT_TAGS)
def test_a_comment_a_person_wrote_is_no_tag(line, monkeypatch):
    monkeypatch.setattr(print_file_watch, "KNOWN_TAGS", {})
    assert print_file_watch.find_tags("M83\n" + line + "\nG1 E1\n") == {"unknown": [], "bare": []}


@pytest.mark.parametrize("line,word", list(BARE_LINES.items()))
def test_a_tag_word_alone_on_its_line_is_a_bare_word(line, word):
    assert print_file_watch.find_tags("M83\n" + line + "\nG1 E1\n")["bare"] == [word]


@pytest.mark.parametrize("line", NOT_BARE)
def test_a_gcode_line_is_no_bare_word(line):
    assert print_file_watch.find_tags(line + "\n")["bare"] == []


# --------------------------------------------------------------------------- #
# (b) Every known tag, with what the walk does with it                         #
# --------------------------------------------------------------------------- #

# tag: (the lines between two 5 mm moves, the walk's total in mm). Only the FLUSH and
# EXCLUDE_E pairs change the count, so only their cases count differently without the
# tag lines (FLUSH: a pull-back inside a flush owes nothing, 12 mm without the tags;
# EXCLUDE_E: the 3 mm between them are no filament used, 13 mm without).
EFFECTS = {
    "TYPE": ([";TYPE:External perimeter"], 10.0),
    "WIPE_START": ([";WIPE_START", "G1 E-1", "G1 E1"], 10.0),
    "WIPE_END": ([";WIPE_END"], 10.0),
    "HEIGHT": ([";HEIGHT:0.2"], 10.0),
    "WIDTH": ([";WIDTH:0.45"], 10.0),
    "LAYER_CHANGE": ([";LAYER_CHANGE"], 10.0),
    "COLOR_CHANGE": ([";COLOR_CHANGE"], 10.0),
    "PAUSE_PRINT": ([";PAUSE_PRINT"], 10.0),
    "CUSTOM_GCODE": ([";CUSTOM_GCODE"], 10.0),
    "_GP_FIRST_LINE_M73_PLACEHOLDER": ([";_GP_FIRST_LINE_M73_PLACEHOLDER"], 10.0),
    "_GP_LAST_LINE_M73_PLACEHOLDER": ([";_GP_LAST_LINE_M73_PLACEHOLDER"], 10.0),
    "_GP_ESTIMATED_PRINTING_TIME_PLACEHOLDER": ([";_GP_ESTIMATED_PRINTING_TIME_PLACEHOLDER"], 10.0),
    "FLUSH_START": ([";FLUSH_START", "G1 E-2", "G1 E4", ";FLUSH_END"], 14.0),
    "FLUSH_END": ([";FLUSH_START", "G1 E-2", "G1 E4", ";FLUSH_END"], 14.0),
    "EXCLUDE_E_START": ([";EXCLUDE_E_START", "G1 E3", ";EXCLUDE_E_END"], 10.0),
    "EXCLUDE_E_END": ([";EXCLUDE_E_START", "G1 E3", ";EXCLUDE_E_END"], 10.0),
    "BEFORE_LAYER_CHANGE": ([";BEFORE_LAYER_CHANGE"], 10.0),
    "AFTER_LAYER_CHANGE": ([";AFTER_LAYER_CHANGE"], 10.0),
    "Z": ([";Z:0.2"], 10.0),
    "_TOOLCHANGE_TIME": ([";_TOOLCHANGE_TIME12.500000"], 10.0),
    "_TOOLCHANGE_END": ([";_TOOLCHANGE_END"], 10.0),
}
COUNTING = {"FLUSH_START", "FLUSH_END", "EXCLUDE_E_START", "EXCLUDE_E_END"}


def _walk(lines):
    text = "M83\nT0\nG1 E5\n" + "".join(line + "\n" for line in lines) + "G1 E5\n" + _footer([100], [100])
    return prusalink_api.measure_filament_usage(text, [])["whole"][0]


def test_every_known_tag_has_a_case_of_what_the_walk_does_with_it():
    """A tag joins KNOWN_TAGS only with a case here: copying the slicer's list
    wholesale would have marked EXCLUDE_E known while the walk still counted it."""
    assert set(EFFECTS) == set(print_file_watch.KNOWN_TAGS)


@pytest.mark.parametrize("tag", sorted(EFFECTS))
def test_the_walk_counts_around_a_known_tag_as_the_slicer_does(tag, monkeypatch):
    lines, want = EFFECTS[tag]
    # The case holds its tag, in the tag's own shape.
    monkeypatch.setattr(print_file_watch, "KNOWN_TAGS", {})
    assert tag in print_file_watch.find_tags("\n".join(lines) + "\n")["unknown"], lines
    assert _walk(lines) == want
    untagged = [line for line in lines if not line.startswith(";")]
    assert (_walk(untagged) != want) == (tag in COUNTING), (tag, _walk(untagged))


def test_a_file_of_known_tags_says_nothing(logs):
    text = "M83\nT0\n" + "".join(lines[0] + "\nG1 E1\n" for lines, _ in EFFECTS.values()) + _footer([100], [100])
    assert print_file_watch.scan_tags("XL", "f.gcode", text) == {"unknown": [], "bare": []}
    assert logs == []


# --------------------------------------------------------------------------- #
# (b) What it says, once per printer and word                                  #
# --------------------------------------------------------------------------- #

UNKNOWN_WORDS = "FCC may count this printer's filament differently from the slicer."


def test_an_unknown_tag_is_said_once_per_printer_and_word(logs):
    text = "M83\nT0\n;PURGE_START\nG1 E5\n" + _footer([10], [10])
    print_file_watch.scan_tags("INDX", NASTY, text)
    print_file_watch.scan_tags("INDX", "/usb/OTHER.BGC", text)   # the same printer and word: nothing
    print_file_watch.scan_tags("XL", "/usb/X.BGC", text)         # another printer: once
    assert [(m, a[0]) for m, a, k in logs] == [
        (f"⚠️ INDX: '{NASTY_ESC}' uses a slicer tag FCC doesn't know: ;PURGE_START. {UNKNOWN_WORDS}", "WARNING"),
        (f"⚠️ XL: '/usb/X.BGC' uses a slicer tag FCC doesn't know: ;PURGE_START. {UNKNOWN_WORDS}", "WARNING")]


def test_a_later_file_names_only_its_new_words(logs):
    print_file_watch.scan_tags("INDX", "a.bgcode", ";PURGE_START\n")
    print_file_watch.scan_tags("INDX", "b.bgcode", ";PURGE_START\n;PARK_TOOL\n;PURGE_START\n")
    assert [m for m, a, k in logs][1] == (
        f"⚠️ INDX: 'b.bgcode' uses a slicer tag FCC doesn't know: ;PARK_TOOL. {UNKNOWN_WORDS}")
    print_file_watch.scan_tags("INDX", "c.bgcode", ";PURGE_START\n;PARK_TOOL\n")
    assert len(logs) == 2, logs


def test_two_unknown_tags_in_one_file_share_one_line(logs):
    print_file_watch.scan_tags("INDX", "a.bgcode", ";PURGE_START\nG1 E1\n;PURGE_END\n")
    assert [m for m, a, k in logs] == [
        f"⚠️ INDX: 'a.bgcode' uses slicer tags FCC doesn't know: ;PURGE_START, ;PURGE_END. {UNKNOWN_WORDS}"]


def test_bare_exclude_e_words_say_the_slicer_counts_the_moves_between_them(logs):
    """The old INDX profile (2026-10-01 to 10-20): its tool-change wrote the two words
    as bare lines, and the slicer counted the moves between them (job 1095's file)."""
    text = "M83\nT0\nG1 E5\nEXCLUDE_E_START\nG1 E3\nEXCLUDE_E_END\nG1 E5\nEXCLUDE_E_START\n"
    print_file_watch.scan_tags("INDX", "/usb/RACOON~1.BGC", text)
    assert [(m, a[0]) for m, a, k in logs] == [(
        "⚠️ INDX: '/usb/RACOON~1.BGC' has EXCLUDE_E_START and EXCLUDE_E_END on lines of their own, "
        "without the ';' that makes them slicer tags, so the slicer counts the moves between them as "
        "filament used (and so does FCC). Check the printer profile's tool-change G-code.", "WARNING")]


def test_another_bare_word_says_neither_reads_it(logs):
    print_file_watch.scan_tags("XL", "x.bgcode", "M83\nPURGE_START\nG1 E1\n")
    assert [m for m, a, k in logs] == [
        "⚠️ XL: 'x.bgcode' has PURGE_START on a line of its own, without the ';' that would make it a "
        "slicer tag, so neither the slicer nor FCC reads it as one. Check the printer profile's G-code."]


def test_a_bare_word_and_an_unknown_tag_in_one_file_are_two_lines(logs):
    print_file_watch.scan_tags("XL", "x.bgcode", "EXCLUDE_E_START\n;PURGE_START\nEXCLUDE_E_END\n")
    msgs = [m for m, a, k in logs]
    assert len(msgs) == 2 and "has EXCLUDE_E_START and EXCLUDE_E_END" in msgs[0] and ";PURGE_START" in msgs[1], msgs


def test_a_scan_that_fails_never_raises(monkeypatch, logs):
    def boom(content):
        raise RuntimeError("bad file")
    monkeypatch.setattr(print_file_watch, "find_tags", boom)
    said = []
    monkeypatch.setattr(state.logger, "warning", lambda msg, *a, **k: said.append(msg))
    assert print_file_watch.scan_tags("XL", "f.gcode", ";PURGE_START\n") is None
    assert logs == [] and len(said) == 1 and "bad file" in said[0], said


# --------------------------------------------------------------------------- #
# (a) + (b) through the real _compute_cancel_usage                             #
# --------------------------------------------------------------------------- #

def test_every_file_fcc_reads_is_scanned_and_the_cause_comes_first(logs):
    g = ";PURGE_START\n" + _gap_file()
    for use_footer in (False, True):          # a cancel, then a finished print
        print_file_watch.forget()
        logs.clear()
        usage, terminal = _cancel_usage(g, 1.0, _XL_PM, use_footer=use_footer)
        assert terminal is None and usage == {0: 10.0, 1: 10.0}
        msgs = [m for m, a, k in logs]
        assert len(msgs) == 2 and ";PURGE_START" in msgs[0] and "G-code walk" in msgs[1], (use_footer, msgs)


def test_a_tag_scan_that_raises_never_stops_a_charge(logs, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("scan")
    monkeypatch.setattr(print_file_watch, "scan_tags", boom)
    usage, terminal = _cancel_usage(_gap_file(), 1.0, _XL_PM, use_footer=True)
    assert terminal is None and usage == {0: 10.0, 1: 10.0}


_FOUR = {f"H-{n}": {"printer_name": "INDX", "position": n - 1} for n in (1, 2, 3, 4)}
_TWO = {"XL-1": {"printer_name": "INDX", "position": 0}, "XL-2": {"printer_name": "INDX", "position": 1}}


def _completion(gcode, pm):
    with patch.object(print_deduct.locations_db, "get_active_printer_map", return_value=pm), \
         patch.object(prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, f: {"gcode": gcode, "fraction": f}):
        return print_deduct._compute_cancel_usage("INDX", "/usb/FLEXI-~2.BGC", "J-1", 1.0, "1.2.3.4", "k",
                                                  use_footer=True)


def test_a_finished_print_names_every_head_over_the_rule_in_one_line(logs):
    """Job 1135's shape (2026-11-03): four heads over, read with a walker that counted
    the ;EXCLUDE_E moves. Here H-3 walks to its footer, so it isn't named."""
    g = "M83\nT0\nG1 E20\nT1\nG1 E12\nT2\nG1 E10\nT3\nG1 E30\n" + _footer([10, 10, 10, 10], [10, 10, 10, 10])
    usage, terminal = _completion(g, _FOUR)
    assert terminal is None and usage == {0: 10.0, 1: 10.0, 2: 10.0, 3: 10.0}    # the footer's
    assert [(m, a[0]) for m, a in _gap_lines(logs)] == [(
        "⚠️ INDX: FCC's G-code walk of '/usb/FLEXI-~2.BGC' came to 20.00g against the slicer's 10.00g "
        "for H-1 (+100.0%), 12.00g against 10.00g for H-2 (+20.0%) and 30.00g against 10.00g for H-4 "
        "(+200.0%). This finished print was charged the slicer's figures, so its charge stands, but FCC "
        "reads this file differently from the slicer: a cancelled print like it would be charged wrong.",
        "WARNING")]


def test_a_footer_head_the_walk_cant_see_is_named_and_still_charged(logs):
    g = ("M83\nT0\nG1 E12\nT1\nG5 E10\n"
         "; filament used [mm] = 10, 10\n; filament used [g] = 10, 10\n")
    usage, terminal = _completion(g, _TWO)
    assert terminal is None and usage == {0: 10.0, 1: 10.0}
    lines = [m for m, a in _gap_lines(logs)]
    assert len(lines) == 1, lines
    assert ("12.00g against the slicer's 10.00g for XL-1 (+20.0%) and 0.00g against 10.00g for XL-2 "
            "(-100.0%)") in lines[0], lines
    assert lines[0].endswith("a cancelled print like it would be charged wrong and would charge XL-2 "
                             "nothing."), lines


def test_heads_within_the_rule_say_nothing_and_the_floor_is_what_keeps_one_quiet(logs, monkeypatch):
    # +1.5%: quiet.
    _completion("M83\nT0\nG1 E10.15\n" + _footer([10], [10]), {"XL-1": {"printer_name": "INDX", "position": 0}})
    # The XL's 20 mm on a 2.31 g head: +2.6%, but 0.06 g, under the 0.1 g floor.
    small = "M83\nT0\nG1 E790\n" + _footer([770], [2.31])
    _completion(small, {"XL-1": {"printer_name": "INDX", "position": 0}})
    assert _gap_lines(logs) == []
    # Without the floor the same file speaks: the floor, not the 2%, kept it quiet.
    monkeypatch.setattr(print_deduct, "_PARSE_GAP_MIN_G", 0.0)
    _completion(small, {"XL-1": {"printer_name": "INDX", "position": 0}})
    assert len(_gap_lines(logs)) == 1, logs


def test_a_completion_walk_that_raises_never_stops_the_charge(logs, monkeypatch):
    said = []
    monkeypatch.setattr(state.logger, "warning", lambda msg, *a, **k: said.append(msg))
    monkeypatch.setattr(prusalink_api, "measure_filament_usage",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("walk")))
    usage, terminal = _completion(_gap_file(), _TWO)
    assert terminal is None and usage == {0: 10.0, 1: 10.0}
    assert _gap_lines(logs) == [] and any("completion walk" in s and "walk" in s for s in said), said


def test_a_print_with_swaps_reuses_the_swap_walk(logs):
    """A finished print with recorded swaps walks once: the split's walk gives the
    whole-file figures too."""
    g = _gap_file()
    with patch.object(prusalink_api, "_walk_extrusion", wraps=prusalink_api._walk_extrusion) as walk, \
         patch.object(print_deduct.locations_db, "get_active_printer_map", return_value=_XL_PM), \
         patch.object(prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, f, extra_fractions=None: {
                          "gcode": g, "fraction": f, "fractions": list(extra_fractions or [])}):
        usage, terminal = print_deduct._compute_cancel_usage(
            "XL", "f.gcode", "J-1", 1.0, "1.2.3.4", "k", use_footer=True, swap_points=[0.5], cums_out={})
    assert terminal is None and usage == {0: 10.0, 1: 10.0}
    assert walk.call_count == 1
    assert len(_gap_lines(logs)) == 1


def test_the_real_completion_deduct_charges_the_footer_of_a_file_that_walks_far_over_it(logs, monkeypatch):
    """A file walking 2.5x its footer: the finished print is charged the footer, no
    review is opened, and one line says FCC reads the file differently."""
    captured = {}

    def _apply(printer, usage_map, fb_url, strategy_label="", active_locs=None, failed_out=None):
        captured["usage_map"] = dict(usage_map)
        return (1, [{"sid": 100, "grams": 10.0, "remaining": 900.0}], {0})

    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    monkeypatch.setattr(print_deduct, "_heads_snapshot", lambda *a, **k: [])
    pm = {"XL-1": {"printer_name": "XL", "position": 0}}
    gcode = "M83\nT0\nG1 E25\n" + _footer([10], [10])
    with patch.object(print_deduct.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(print_deduct.locations_db, "get_active_printer_map", return_value=pm), \
         patch.object(prusalink_api, "fetch_printer_credentials",
                      return_value={"ip_address": "1.2.3.4", "api_key": "k"}), \
         patch.object(prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}), \
         patch.object(print_deduct, "_apply_usage_to_printer", side_effect=_apply):
        res = print_deduct.deduct_completed_print("XL", "done.gcode", "J-9")
    assert res["status"] == "deducted", res
    assert captured["usage_map"] == {0: 10.0}
    assert cancel_review_store.list_pending() == []
    lines = [m for m, a in _gap_lines(logs)]
    assert len(lines) == 1 and "25.00g against the slicer's 10.00g for XL-1 (+150.0%)" in lines[0], lines
