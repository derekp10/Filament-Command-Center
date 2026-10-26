"""Group 56: Deduct Accuracy.

56.1 — The cancel parser skipped G2 / G3 arcs. PrusaSlicer's arc fitting puts a
real share of every tool's filament on arcs (the raccoon INDX print: 48.43 g
counted against a 52.27 g footer without them, 52.26 g with them), so every
cancelled print was charged short: a raccoon print cancelled at 50% by 1.96 g.

56.2 — One pass over the file gives each tool's partial and its whole-file walk;
the charge is the share of the tool's walk reached, times its footer grams, never
more than the footer (the Core One fixture walks ~1.4% over its footer even with
arcs counted). A head whose walk drifts more than 2% from its footer gets ONE
Activity Log WARNING; it never changes the charge.

56.3 — A completed print whose footer can't be read (or lists nothing) opens the
recoverable "couldn't measure" review instead of a 0 g ledger entry, and so does
a completion whose file couldn't be downloaded for the 72 h retry window.

56.4 — The deduct and monitor log lines escape a print's filename (the Activity
Log is HTML).

56.5 — The boot creds seed no longer GETs the retired FilaBridge (pinned in
test_l316_charact_monitor_boot.py), and the shortfall card reads the printer's
heads on an explicit `read_heads` flag, not on `fb_url` being passed.

Each pin was proven red on the base (dev 4d99c61) before the change.
"""
from __future__ import annotations

import ast
import os
import re
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import bgcode_decode  # noqa: E402
import cancel_fetch_store  # noqa: E402
import cancel_review_store  # noqa: E402
import print_deduct  # noqa: E402
import print_deduct_ledger  # noqa: E402
import print_monitor  # noqa: E402
import prusalink_api  # noqa: E402
import state  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_HUB = os.path.abspath(os.path.join(_HERE, ".."))
_TRIMMED = os.path.join(_HERE, "fixtures", "indx_raccoon_trimmed.gcode")
_CORE1 = os.path.join(_HERE, "fixtures", "sample.bgcode")
_RACCOON = os.path.join(_HUB, "..", ".captures", "indx-raccoon-2026-10-08", "racoon_decoded.gcode")
NASTY = "<b>&x.gcode"
NASTY_ESC = "&lt;b&gt;&amp;x.gcode"


@pytest.fixture(autouse=True)
def _isolated_stores(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a, k)))
    return calls


def _read_text(path):
    """Universal newlines: a CRLF checkout (core.autocrlf) reads back as the LF
    text the decoder hands FCC."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _cut_before(gcode, marker):
    """The fraction that reaches every line before the first line starting with
    `marker`, and nothing of that line."""
    at = re.search(r"(?m)^" + re.escape(marker), gcode).start()
    return (len(gcode[:at].encode("utf-8")) + 1) / len(gcode.encode("utf-8"))


def _footer(mms, grams):
    return ("; filament used [mm] = " + ", ".join(str(m) for m in mms) + "\n"
            "; filament used [g] = " + ", ".join(str(g) for g in grams) + "\n")


# --------------------------------------------------------------------------- #
# 56.1 — arcs count                                                            #
# --------------------------------------------------------------------------- #

def test_arcs_count_in_relative_e_with_and_without_spaces():
    g = ("M83\nT0\n"
         "G1 X10 Y0 E1\n"
         "G2 X10 Y10 I5 J5 E2\n"                 # spaced arc
         "G3X0Y10I-5J0E3\n"                      # Prusa no-spaces arc
         "g2 x0 y0 i0 j-5 e4\n"                  # lower case is still an arc
         + _footer([10], [10]))
    measured = prusalink_api.measure_filament_usage(g, [1.0])
    assert abs(measured["whole"][0] - 10.0) < 1e-9, measured   # 1 + 2 + 3 + 4 mm


def test_arcs_count_in_absolute_e():
    g = ("M82\nT0\nG92 E0\n"
         "G1 X10 E2\n"                           # to 2
         "G2 X10 Y10 I5 J5 E5\n"                 # to 5 (+3)
         "G3X0Y10I-5J0E4.5\n"                    # a retract on an arc adds nothing
         "G3X0Y0I0J-5E8\n"                       # to 8 (+3 past the high-water 5)
         + _footer([8], [8]))
    measured = prusalink_api.measure_filament_usage(g, [1.0])
    assert abs(measured["whole"][0] - 8.0) < 1e-9, measured


def test_g_codes_that_are_not_moves_never_count():
    """G10 / G11 (firmware retract), G12 (the INDX nozzle clean), G28 / G29 /
    G27 / G21 stay out even with an E-like parameter, zero-padded too (G010 is
    G10). The old G0/G1 regex kept them out as well: this pins that widening it
    to arcs (and padding) let none of them in."""
    g = ("M83\nT0\n"
         "G10 E5\nG11 E5\nG12 S90 E5\nG28 E5\nG29 E5\nG27 E5\nG21 E5\n"
         "G010 E5\nG028 E5\nG0012 E5\n"
         "G1 E1\n"
         + _footer([1], [1]))
    measured = prusalink_api.measure_filament_usage(g, [1.0])
    assert abs(measured["whole"][0] - 1.0) < 1e-9, measured


def test_zero_padded_moves_count_like_the_firmware_reads_them():
    """`G01` / `G02` / `G03` / `G00` are G1 / G2 / G3 / G0 to the firmware (a
    CNC-style slicer writes them); the walk before Group 56 dropped all of them."""
    g = ("M83\nT0\n"
         "G01 X10 E1\n"
         "G02 X10 Y10 I5 J5 E2\n"
         "G003X0Y10I-5J0E3\n"
         "G00 E4\n"
         + _footer([10], [10]))
    measured = prusalink_api.measure_filament_usage(g, [1.0])
    assert abs(measured["whole"][0] - 10.0) < 1e-9, measured


def test_trimmed_indx_fixture_carries_arcs_on_every_tool():
    """The fixture is only a test of arc counting if arcs carry a real share of
    every tool's filament (an independent count, not FCC's parser)."""
    g = _read_text(_TRIMMED)
    foot_mm = [float(x) for x in re.search(r"filament used \[mm\] = ([0-9., ]+)", g).group(1).split(",")]
    arc_mm, tool = {}, 0
    for line in g.splitlines():
        code = line.split(";", 1)[0].strip().upper()
        t = re.match(r"T(\d+)(?!\d)", code)
        if t:
            tool = int(t.group(1))
        elif re.match(r"G[23](?!\d)", code):
            e = re.search(r"E(-?\d*\.?\d+)", code)
            if e:
                arc_mm[tool] = arc_mm.get(tool, 0.0) + float(e.group(1))
    for t in (0, 1, 2):
        assert arc_mm.get(t, 0.0) >= 0.10 * foot_mm[t], (t, arc_mm, foot_mm)
    assert g.count("Purge Station specific Gcode Start") >= 2
    assert len(re.findall(r"(?m)^T[012]\b", g)) >= 3


def test_trimmed_indx_fixture_whole_walk_lands_on_its_footer():
    """The real INDX G-code (no-space arcs, tool changes, Purge Station blocks,
    the G91 prime flush) walks to its footer on every tool; skipping arcs (the
    regex before 56.1) falls short on every tool by more than 10%.

    The excerpt's footer was computed for it by an independent signed-E count
    over G0-G3 (make_trimmed_fixture.py beside the capture), so its first half
    only proves the walker reads the real syntax the way that count does; the
    second half (arcs carry >10% of every tool) is what tells the old walk from
    the new. The check against the SLICER's own footer is the full-capture test
    below, which runs where the git-ignored capture exists (Derek's PC)."""
    g = _read_text(_TRIMMED)
    measured = prusalink_api.measure_filament_usage(g, [1.0])
    assert set(measured["footer"]) == {0, 1, 2}
    for t, want in measured["footer"].items():
        assert abs(measured["whole"][t] - want) <= 0.001 * want, (t, measured)
    with patch.object(prusalink_api, "_EXTRUDING_MOVE_RE", re.compile(r"^G[01](?![0-9])")):
        old = prusalink_api.measure_filament_usage(g, [1.0])
    for t, want in measured["footer"].items():
        assert old["whole"].get(t, 0.0) < 0.9 * want, (t, old)


def test_trimmed_indx_fixture_partials_keep_the_untouched_head_at_zero():
    g = _read_text(_TRIMMED)
    footer = prusalink_api.parse_footer_usage(g)
    before_t2 = prusalink_api.parse_partial_filament_usage(g, _cut_before(g, "T2"))
    assert 2 not in before_t2, before_t2                      # T2 hadn't printed yet
    assert before_t2[0] == pytest.approx(footer[0])           # T0 was done
    assert before_t2[1] == pytest.approx(footer[1])           # and so was T1
    t1_at = _cut_before(g, "T1")
    t2_at = _cut_before(g, "T2")
    mid_t1 = prusalink_api.parse_partial_filament_usage(g, (t1_at + t2_at) / 2)
    assert 0 < mid_t1[1] < footer[1], mid_t1
    assert 2 not in mid_t1


@pytest.mark.skipif(not os.path.isfile(_RACCOON),
                    reason="the full raccoon capture is git-ignored (only on Derek's PC)")
def test_full_raccoon_capture_walks_to_its_footer():
    """The whole real file: 52.26 g against the footer's 52.27 g (it was 48.43 g),
    and a cancel at the end charges exactly the footer."""
    g = _read_text(_RACCOON)
    measured = prusalink_api.measure_filament_usage(g, [0.5, 1.0])
    assert measured["footer"] == {0: 18.83, 1: 24.44, 2: 9.0}
    for t, want in measured["footer"].items():
        assert abs(measured["whole"][t] - want) < 0.1, (t, measured["whole"])
    assert measured["partials"][1] == measured["footer"]
    half = measured["partials"][0]
    assert sum(half.values()) == pytest.approx(23.80, abs=0.05)
    # Per tool too: without arcs, scaling alone would move the TOTAL only ~0.08 g
    # (T0 -0.19, T1 +0.22, T2 -0.11), so the sum can't pin arc counting by itself.
    assert half[0] == pytest.approx(7.58, abs=0.02), half
    assert half[1] == pytest.approx(11.615, abs=0.02), half
    assert half[2] == pytest.approx(4.607, abs=0.02), half


# --------------------------------------------------------------------------- #
# 56.2 — one pass, scaled to the footer, clamped, and the 2% warning           #
# --------------------------------------------------------------------------- #

def test_partial_is_the_share_reached_times_the_footer():
    """A file that walks 10% over its footer: the cancel is charged the footer's
    share, never the walk's own grams."""
    head = "M83\nT0\nG1 E5.5\n"
    g = head + "G1 E5.5\n" + _footer([10], [1.0])      # walks 11mm, footer 10mm / 1g
    half = (len(head) + 1) / len(g)
    measured = prusalink_api.measure_filament_usage(g, [half, 1.0])
    assert measured["whole"][0] == pytest.approx(1.1)
    assert measured["partials"][0][0] == pytest.approx(0.5)    # not 0.55
    assert measured["partials"][1][0] == pytest.approx(1.0)    # not 1.1


def test_a_net_negative_tail_never_charges_past_the_footer():
    """Relative E nets a final retract, so a cancel just before it reaches more
    than the whole file: the charge stops at the footer. (Before 56.2 this
    cancel was charged 12mm at the footer's g/mm: 1.2g against a 1g footer.)"""
    head = "M83\nT0\nG1 E12\n"
    g = head + "G1 E-2\n" + _footer([10], [1.0])
    measured = prusalink_api.measure_filament_usage(g, [(len(head) + 1) / len(g)])
    assert measured["whole"][0] == pytest.approx(1.0)
    assert measured["partials"][0][0] == pytest.approx(1.0)


def test_absolute_e_wipe_tail_keeps_a_late_cancel_under_the_footer():
    """Absolute E: a file that walks over its footer (10.5mm, a wipe, then 0.5mm
    more past it: 11mm against 10mm). A late cancel before the wipe is charged
    its share of the footer, not 10.5mm at the footer's g/mm (1.05g, past the
    footer, before 56.2)."""
    head = "M82\nT0\nG92 E0\nG1 E10.5\n"
    g = head + "G1 E9.5\nG1 E11\n" + _footer([10], [1.0])
    late = prusalink_api.parse_partial_filament_usage(g, (len(head) + 1) / len(g))
    assert late[0] == pytest.approx(1.0 * 10.5 / 11, abs=1e-4)   # rounded to 4 dp
    assert prusalink_api.parse_partial_filament_usage(g, 1.0)[0] == pytest.approx(1.0)


def test_core_one_fixture_still_scales_and_clamps():
    """The Core One fixture walks ~1.4% over its footer with arcs counted; every
    partial stays within the footer and the end of the file charges exactly it."""
    if not os.path.isfile(_CORE1):
        pytest.skip("sample.bgcode fixture not present")
    g = bgcode_decode.decode_bgcode(open(_CORE1, "rb").read())["gcode"]
    measured = prusalink_api.measure_filament_usage(g, [0.25, 0.5, 0.75, 0.99, 1.0])
    assert measured["footer"] == {1: 6.35}
    assert 1.01 < measured["whole"][1] / 6.35 < 1.02, measured["whole"]
    vals = [p[1] for p in measured["partials"]]
    assert vals == sorted(vals) and all(v <= 6.35 for v in vals), vals
    assert vals[-1] == pytest.approx(6.35)
    # The mid-file charge IS the footer's share (~1.4% under the walk's own grams):
    # this tells scaling from no scaling, which the clamp alone can't.
    total = len(g.encode("utf-8"))
    cuts, whole = prusalink_api._walk_extrusion(g, [int(0.5 * total)], 1)
    expected = round(6.35 * cuts[0][0][1] / whole[0][1], 4)
    assert vals[1] == expected, (vals[1], expected)
    assert vals[1] < cuts[0][0][1] * 6.35 / 2130.15 - 0.03, "the unscaled walk would charge more"


def test_several_cuts_are_measured_in_one_pass_in_the_order_asked():
    g = "M83\nT0\n" + "G1 E1\n" * 10 + _footer([10], [10])
    with patch.object(prusalink_api, "_walk_extrusion", wraps=prusalink_api._walk_extrusion) as walk:
        measured = prusalink_api.measure_filament_usage(g, [0.9, 0.1, 0.5])
    assert walk.call_count == 1
    late, early, mid = (p.get(0, 0.0) for p in measured["partials"])
    assert early < mid < late, measured["partials"]


def test_the_run_out_split_walks_the_file_once_and_needs_the_mm_footer():
    body = "M83\nT0\n" + "G1 E1\n" * 11
    text = body + _footer([10], [5.0])                 # walks 11mm against 10mm / 5g
    with patch.object(prusalink_api, "_download_file_bytes", return_value=text.encode()), \
         patch.object(prusalink_api, "_walk_extrusion", wraps=prusalink_api._walk_extrusion) as walk:
        seg = prusalink_api.compute_segment_usage("ip", "k", "f.gcode", [0.3, 0.6])
    assert walk.call_count == 1
    assert seg["footer"] == {0: 5.0}
    assert all(c[0] <= 5.0 for c in seg["cums"]) and seg["cums"][0][0] < seg["cums"][1][0], seg
    no_mm = body + "; filament used [g] = 5.0\n"
    with patch.object(prusalink_api, "_download_file_bytes", return_value=no_mm.encode()):
        assert prusalink_api.compute_segment_usage("ip", "k", "f.gcode", [0.5]) is None


def _gap_file():
    # T0 walks 10mm against 10mm (0%); T1 walks 11mm against 10mm (+10%).
    return ("M83\nT0\nG1 E10\nT1\nG1 E11\n"
            "; filament used [mm] = 10, 10\n; filament used [g] = 10, 10\n")


def _cancel_usage(gcode, frac, pm, use_footer=False, filename=NASTY):
    with patch.object(print_deduct.locations_db, "get_active_printer_map", return_value=pm), \
         patch.object(prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, f: {"gcode": gcode, "fraction": f}):
        return print_deduct._compute_cancel_usage("XL", filename, "J-1", frac, "1.2.3.4", "k",
                                                  use_footer=use_footer)


_XL_PM = {"XL-1": {"printer_name": "XL", "position": 0},
          "XL-2": {"printer_name": "XL", "position": 1}}


def _gap_lines(logs):
    return [(m, a) for m, a, k in logs if "G-code walk" in m]


def test_a_head_over_two_percent_logs_exactly_one_warning(logs):
    usage, terminal = _cancel_usage(_gap_file(), 1.0, _XL_PM)
    assert terminal is None and usage == {0: 10.0, 1: 10.0}   # the charge is the footer's
    lines = _gap_lines(logs)
    assert len(lines) == 1, logs
    msg, args = lines[0]
    assert args[0] == "WARNING"
    assert msg.startswith("⚠️ XL XL-2:"), msg
    assert "11.00g" in msg and "10.00g" in msg and "+10.0%" in msg, msg
    assert NASTY_ESC in msg and "<b>" not in msg, msg


def test_heads_within_two_percent_log_nothing(logs):
    g = "M83\nT0\nG1 E10.15\n" + _footer([10], [10])        # +1.5%
    _cancel_usage(g, 1.0, _XL_PM)
    assert _gap_lines(logs) == []


def test_an_untouched_head_is_not_checked(logs):
    """T1 is over 2% but hadn't printed when the print was cancelled: nothing
    was charged to it, so nothing is said about it."""
    g = _gap_file()
    _cancel_usage(g, _cut_before(g, "T1"), _XL_PM)
    assert _gap_lines(logs) == []


def test_a_single_head_printer_names_its_head_not_the_tool_index(logs):
    """An MMU-profile file marks tool 1 on a one-head Core One: the warning names
    the head the charge was folded onto."""
    g = "M83\nT1\nG1 E11\n" + _footer([0, 10], [0, 10])
    usage, _ = _cancel_usage(g, 1.0, {"CORE1": {"printer_name": "XL", "position": 0}})
    assert usage == {0: 10.0}
    lines = _gap_lines(logs)
    assert len(lines) == 1 and lines[0][0].startswith("⚠️ XL CORE1:"), lines


def test_a_footer_tool_the_walk_never_sees_is_named_even_before_it_prints(logs):
    """T1's moves are something the walk doesn't read, so T1 would never be
    charged, whatever the cut: one WARNING names it even though this cancel came
    before T1's turn (an untouched head that the walk DOES see stays quiet,
    test_an_untouched_head_is_not_checked)."""
    g = ("M83\nT0\nG1 E10\nT1\nG5 E10\n"
         "; filament used [mm] = 10, 10\n; filament used [g] = 10, 10\n")
    _cancel_usage(g, _cut_before(g, "T1"), _XL_PM)
    lines = _gap_lines(logs)
    assert len(lines) == 1 and lines[0][0].startswith("⚠️ XL XL-2:"), lines
    assert "0.00g" in lines[0][0] and "-100.0%" in lines[0][0], lines


def test_a_completion_reads_the_footer_and_says_nothing_about_the_walk(logs):
    usage, terminal = _cancel_usage(_gap_file(), 1.0, _XL_PM, use_footer=True)
    assert terminal is None and usage == {0: 10.0, 1: 10.0}
    assert _gap_lines(logs) == []


# --------------------------------------------------------------------------- #
# 56.3 — a completion FCC can't read asks instead of recording 0 g             #
# --------------------------------------------------------------------------- #

def _complete_with(gcode, filename=NASTY):
    with patch.object(print_deduct.locations_db, "get_active_printer_map",
                      return_value={"XL-1": {"printer_name": "XL", "position": 0}}), \
         patch.object(prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, f: {"gcode": gcode, "fraction": f}):
        return print_deduct.deduct_completed_print("XL", filename, "J-7", fb_url="http://fb",
                                                   ip_address="1.2.3.4", api_key="k")


@pytest.mark.parametrize("gcode, reason, words", [
    ("M83\nT0\nG1 E5\n; another slicer's file\n", "no_footer",
     "its file's filament footer couldn't be read"),
    ("M83\nT0\nG1 X10\n; filament used [mm] = 0.00, 0.00\n; filament used [g] = 0.00, 0.00\n",
     "empty_footer", "its file's filament footer lists no filament"),
])
def test_a_completion_without_a_readable_footer_opens_a_review(logs, gcode, reason, words):
    out = _complete_with(gcode)
    assert out["status"] == "pending_unresolved" and out["kind"] == "progress_unknown", out
    assert print_deduct_ledger.was_deducted("XL", "J-7") is False      # no 0 g entry
    rec = cancel_review_store.get_pending("XL", "J-7")
    assert rec["kind"] == "progress_unknown" and rec["unmeasured_reason"] == reason
    assert rec["filename"] == NASTY                                      # stored raw
    msg = logs[-1][0]
    assert words in msg and NASTY_ESC in msg and "<b>" not in msg, msg


def test_a_completion_without_a_job_id_warns_instead_of_sharing_one_review(logs):
    """An id-less job has no key to hold a review on (every one would land on
    the same "<printer>::" record and the second would vanish), so it warns every
    time instead, as 43.2 does for id-less shortfalls."""
    for _ in range(2):
        with patch.object(print_deduct.locations_db, "get_active_printer_map", return_value={}), \
             patch.object(prusalink_api, "fetch_cancel_gcode",
                          side_effect=lambda ip, key, fn, f: {"gcode": "G1 E5\n", "fraction": f}):
            out = print_deduct.deduct_completed_print("XL", NASTY, "", fb_url="http://fb",
                                                      ip_address="1.2.3.4", api_key="k")
        assert out["status"] == "no_usage" and out["reason"] == "no_footer", out
    assert cancel_review_store.list_pending() == []
    warned = [m for m, a, k in logs if "no job id" in m]
    assert len(warned) == 2 and NASTY_ESC in warned[0] and "<b>" not in warned[0], logs


def test_the_unmeasured_review_offers_only_discard_and_discard_settles_it(logs):
    _complete_with("M83\nT0\nG1 E5\n")
    client = app_module.app.test_client()
    r = client.post("/api/cancel_deduct/confirm", json={"printer_name": "XL", "job_id": "J-7"})
    assert r.get_json()["status"] == "manual_only"
    assert cancel_review_store.has_pending("XL", "J-7")
    r = client.post("/api/cancel_deduct/dismiss", json={"printer_name": "XL", "job_id": "J-7"})
    assert r.status_code == 200
    assert print_deduct_ledger.was_deducted("XL", "J-7") is True
    assert not cancel_review_store.has_pending("XL", "J-7")


def _aged_fetch(kind):
    cancel_fetch_store.add_pending({
        "printer_name": "XL", "job_id": "J-9", "filename": NASTY, "progress": 1.0,
        "first_seen": time.time() - print_monitor._CANCEL_FETCH_MAX_AGE_S - 10,
        "kind": kind, "attempts": 30, "last_status": "awaiting_fetch"})


def test_a_completion_given_up_after_the_retry_window_opens_a_review(logs):
    _aged_fetch("complete")
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True):
        print_monitor._process_pending_cancel_fetches({"XL": {"state": "IDLE"}}, "http://fb")
    assert not cancel_fetch_store.has_pending("XL", "J-9")
    assert print_deduct_ledger.was_deducted("XL", "J-9") is False
    rec = cancel_review_store.get_pending("XL", "J-9")
    assert rec["kind"] == "progress_unknown" and rec["unmeasured_reason"] == "no_download"
    assert "couldn't download or read its file" in logs[-1][0]


def test_a_cancel_given_up_after_the_retry_window_still_records_and_warns(logs):
    """Unchanged: only a completion's give-up became a review."""
    _aged_fetch("cancel")
    print_monitor._process_pending_cancel_fetches({"XL": {"state": "IDLE"}}, "http://fb")
    assert print_deduct_ledger.was_deducted("XL", "J-9") is True
    assert not cancel_review_store.has_pending("XL", "J-9")
    assert NASTY_ESC in logs[-1][0]


# --------------------------------------------------------------------------- #
# 56.4 — filenames are escaped in every deduct / monitor log line              #
# --------------------------------------------------------------------------- #

_ESCAPES = {"_esc", "print_deduct._esc", "html.escape"}
# Outside text besides a filename: an exception, Spoolman's error body and the
# review's refusal reasons built from them (56.4 and its reviews).
_FREE_TEXT_NAMES = {"e", "err", "exc", "why"}


def _is_escape(node):
    return isinstance(node, ast.Call) and ast.unparse(node.func) in _ESCAPES


def _free_text(node):
    """Whether `node` is outside text: a filename, an exception or error name, or
    Spoolman's last error body."""
    if isinstance(node, ast.Name) and (node.id in _FREE_TEXT_NAMES or "filename" in node.id):
        return True
    if isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
        text = ast.unparse(node)
        return "filename" in text or "LAST_SPOOLMAN_ERROR" in text
    return False


def _unescaped_free_text(source, name):
    """(offenders, checked): every piece of outside text put into an add_log_entry
    message must go through an escape. A message may be an f-string, a +, % or
    .format() build, written in the call or held in a variable the same function
    assigns (=, +=, annotated) and then logs. `checked` counts every escape and
    every offender seen, so a canary that sees nothing can't pass."""
    tree = ast.parse(source)
    offenders, checked = set(), set()

    def visit(node):
        if _is_escape(node):
            checked.add((name, node.lineno, ast.unparse(node)))
            return
        if isinstance(node, ast.FormattedValue):
            visit(node.value)
            return
        if _free_text(node):
            text = ast.unparse(node)
            checked.add((name, node.lineno, text))
            offenders.add(f"{name}:{node.lineno}: {text}")
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        assigns = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and node.value is not None:
                targets, value = [node.target], node.value
            else:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    assigns.setdefault(target.id, []).append(value)
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_log_entry" and node.args):
                continue
            msg = node.args[0]
            for expr in (assigns.get(msg.id, []) if isinstance(msg, ast.Name) else [msg]):
                visit(expr)
    return sorted(offenders), checked


def test_the_escape_canary_catches_raw_outside_text():
    src = ("def f(filename, rec, e, err, why):\n"
           "    state.add_log_entry(f\"ok '{_esc(filename)}' {_esc(e)}\", 'INFO')\n"
           "    msg = f\"bad '{rec.get('filename')}'\"\n"
           "    state.add_log_entry(msg, 'INFO')\n"
           "    state.add_log_entry(f\"bad '{filename}' {e}\", 'INFO')\n"
           "    m2 = 'x'\n"
           "    m2 += f\"bad {err}\"\n"
           "    state.add_log_entry(m2, 'INFO')\n"
           "    state.add_log_entry('bad %s' % filename, 'INFO')\n"
           "    state.add_log_entry('bad {}'.format(why), 'INFO')\n"
           "    state.add_log_entry(f\"bad {spoolman_api.LAST_SPOOLMAN_ERROR}\", 'INFO')\n"
           "    state.add_log_entry(f\"fine {len(rec)} {printer}\", 'INFO')\n")
    offenders, checked = _unescaped_free_text(src, "x.py")
    assert len(offenders) == 7, offenders
    assert len(checked) == 9, checked


def test_every_deduct_and_monitor_log_line_escapes_its_outside_text():
    offenders, checked = [], set()
    for name in ("print_deduct.py", "print_monitor.py", "startup_migrations.py",
                 "cancel_review_store.py"):
        with open(os.path.join(_HUB, name), encoding="utf-8") as fh:
            bad, seen = _unescaped_free_text(fh.read(), name)
        offenders += bad
        checked |= seen
    assert not offenders, "log outside text through _esc(...):\n" + "\n".join(offenders)
    # Every escape the four modules' log lines carry (filenames, exceptions,
    # Spoolman errors, refusal reasons): a floor, so a canary that stops seeing
    # them fails instead of passing on nothing.
    assert len(checked) >= 52, len(checked)


def test_the_boot_re_surface_escapes_and_names_an_unmeasured_print(logs):
    import startup_migrations
    cancel_review_store.add_pending({"printer_name": "XL", "job_id": "R-1", "filename": NASTY,
                                     "kind": "progress_unknown", "spools": [], "total_grams": 0.0})
    cancel_review_store.add_pending({"printer_name": "XL", "job_id": "R-2#shortfall", "filename": NASTY,
                                     "kind": "shortfall", "spools": [], "total_grams": 3.0})
    startup_migrations.resurface_pending_cancel_reviews()
    msgs = [m for m, a, k in logs]
    assert len(msgs) == 2, msgs
    assert all(NASTY_ESC in m and "<b>" not in m for m in msgs), msgs
    unmeasured = next(m for m in msgs if "Unmeasured print" in m)
    assert "couldn't measure how much" in unmeasured and "0.0g" not in unmeasured, unmeasured


def test_spoolmans_error_text_is_escaped_in_the_deduct_lines(logs):
    """A Spoolman (or proxy) error body is outside text too: a connect timeout's
    `<HTTPConnection ...>` vanished from the line as a bogus tag."""
    import spoolman_api
    spool = {"id": 5, "used_weight": 100.0, "initial_weight": 1000.0, "filament": {"weight": 1000.0}}
    err = "HTTPConnectionPool: Caused by ConnectTimeoutError(<HTTPConnection(host='x') at 0x1>)"

    def _fail(*a, **k):
        spoolman_api.LAST_SPOOLMAN_ERROR = err
        return None
    with patch.object(spoolman_api, "get_spools_at_location", return_value=[5]), \
         patch.object(spoolman_api, "get_spool", return_value=dict(spool)), \
         patch.object(spoolman_api, "update_spool", side_effect=_fail), \
         patch.object(spoolman_api, "format_spool_display", return_value={"text": "#5", "color": "ff0000"}):
        updated, details, known = print_deduct._apply_usage_to_printer(
            "XL", {0: 2.0}, "http://fb", active_locs=[("XL-1", {"position": 0, "printer_name": "XL"})])
    assert updated == 0
    line = next(m for m, a, k in logs if "failed to auto-deduct" in m)
    assert "&lt;HTTPConnection(host='x') at 0x1&gt;" in line and "<HTTP" not in line, line


def test_a_refusal_reason_built_from_the_request_is_escaped(logs):
    """`_rows_from_charges` echoes the request's `position` back in its reason;
    the review's refusal line puts it in the Activity Log for every dashboard."""
    cancel_review_store.add_pending({"printer_name": "XL", "job_id": "N-1", "filename": "f.gcode",
                                     "kind": "no_spool", "spools": [], "total_grams": 2.0,
                                     "usage_map": {"0": 2.0}, "progress": 1.0})
    client = app_module.app.test_client()
    r = client.post("/api/cancel_deduct/confirm", json={
        "printer_name": "XL", "job_id": "N-1",
        "charges": [{"position": "<img src=x onerror=alert(1)>", "sid": 1, "grams": 1}]})
    assert r.get_json()["status"] == "error"
    assert cancel_review_store.has_pending("XL", "N-1")
    line = next(m for m, a, k in logs if "review Apply refused" in m)
    assert "&lt;img src=x onerror=alert(1)&gt;" in line and "<img" not in line, line


def test_the_converted_lines_render_a_filename_as_text(logs, monkeypatch):
    monkeypatch.setattr(print_deduct, "_heads_snapshot", lambda *a, **k: [])
    monkeypatch.setattr(print_deduct.config_loader, "get_api_urls", lambda: ("http://sm", "http://fb"))
    print_deduct._log_cancel_uncomputable("XL", NASTY, 0.5, None)
    print_deduct._log_cancel_uncomputable("XL", NASTY, 0.5, "; filament used [g] = 1\n; filament used [mm] = 1\n")
    print_deduct._log_cancel_uncomputable("XL", NASTY, 0.5, "G1 E1\n")
    print_deduct._enqueue_cancel_fetch("XL", NASTY, "E-1", 0.5)
    print_deduct._enqueue_cancel_fetch("XL", NASTY, "E-2", 1.0, kind="complete")
    print_deduct._enqueue_cancel_fetch("XL", NASTY, "E-3", 0.5, ambiguous=True)
    print_deduct._stash_unresolved_review("XL", NASTY, "E-4", 1.0, usage_map={0: 2.0}, no_spool=True)
    print_deduct._stash_unresolved_review("XL", NASTY, "E-5", 1.0, progress_unknown=True)
    print_deduct._record_applied_deduct("XL", "", filename=NASTY, scale=1.0, details=[],
                                        usage_map={0: 3.0})
    with patch.object(print_deduct, "_create_pending_cancel_review",
                      side_effect=RuntimeError("<urllib3 object at 0x1>")):
        print_monitor._on_cancel_edge("XL", NASTY, "E-6", 0.5, "http://fb")
    assert not [m for m, a, k in logs if "<b>" in m], logs
    msgs = [m for m, a, k in logs if "x.gcode" in m]   # ("Cancel detected" names no file)
    assert len(msgs) == 10, msgs
    for m in msgs:
        assert NASTY_ESC in m, m
    assert "&lt;urllib3 object at 0x1&gt;" in msgs[-1], msgs[-1]


# --------------------------------------------------------------------------- #
# 56.5 — the shortfall card reads the heads on an explicit flag                #
# --------------------------------------------------------------------------- #

_HEADS = [{"toolhead": "XL-1", "position": 0, "sid": 5}]


def test_the_shortfall_card_reads_heads_only_when_asked():
    with patch.object(print_deduct, "_heads_snapshot", return_value=list(_HEADS)) as heads:
        quiet = print_deduct._stash_shortfall_review(
            "XL", "S-1", filename="f", scale=1.0, uncharged={"0": 3.0}, fb_url="http://fb")
        assert heads.call_count == 0      # passing fb_url no longer reads them
        asked = print_deduct._stash_shortfall_review(
            "XL", "S-2", filename="f", scale=1.0, uncharged={"0": 3.0}, read_heads=True)
        assert heads.call_count == 1
    assert quiet["heads_at_end"] == []
    assert asked["heads_at_end"][0]["sid"] == 5
    assert asked["shortfall_causes"]["0"]["sid"] == 5


def test_every_deduct_path_asks_the_card_to_read_the_heads():
    tree = ast.parse(open(os.path.join(_HUB, "print_deduct.py"), encoding="utf-8").read())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and ast.unparse(n.func) == "_record_applied_deduct"]
    assert len(calls) == 3, len(calls)    # the cancel, completion and no_spool-confirm deducts
    for call in calls:
        flag = {kw.arg: kw.value for kw in call.keywords}.get("read_heads")
        assert isinstance(flag, ast.Constant) and flag.value is True, call.lineno
    src = ast.unparse(tree)
    assert "if fb_url is not None" not in src


def test_a_completion_deduct_card_still_names_the_heads_at_print_end(logs):
    """The live path keeps its behaviour: a completion that leaves grams uncharged
    opens a card naming the heads FCC read at print end."""
    details = [{"sid": 5, "grams": 1.0, "remaining": 0.0, "toolhead": "XL-1", "position": 0}]
    with patch.object(prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, f: {"gcode": "x", "fraction": f}), \
         patch.object(prusalink_api, "parse_footer_usage", return_value={0: 5.0}), \
         patch.object(print_deduct.locations_db, "get_active_printer_map", return_value={}), \
         patch.object(print_deduct, "_resolve_active_locs_for_printer",
                      return_value=[("XL-1", {"position": 0, "printer_name": "XL"})]), \
         patch.object(print_deduct, "_apply_usage_to_printer", return_value=(1, details, {0})), \
         patch.object(print_deduct.config_loader, "load_config", return_value={}), \
         patch.object(print_deduct.stock_report, "check_after_deduct"), \
         patch.object(print_deduct, "_heads_snapshot", return_value=list(_HEADS)) as heads:
        out = print_deduct.deduct_completed_print("XL", "f.bgcode", "J-3", fb_url="http://fb",
                                                  ip_address="1.2.3.4", api_key="k")
    assert out["status"] == "deducted"
    assert heads.call_count == 1
    card = cancel_review_store.get_pending("XL", "J-3#shortfall")
    assert card["heads_at_end"][0]["toolhead"] == "XL-1"


# --------------------------------------------------------------------------- #
# The second review (wf_80c46b1e-f8e): the warning's edges, the run-out split  #
# on real and synthetic files, and the flows it found                          #
# --------------------------------------------------------------------------- #

def test_the_two_percent_line_is_drawn_where_it_says(logs):
    """2.5% warns, 2.0% doesn't (the threshold is "more than 2%")."""
    _cancel_usage("M83\nT0\nG1 E10.25\n" + _footer([10], [10]), 1.0, _XL_PM)
    assert len(_gap_lines(logs)) == 1
    del logs[:]
    _cancel_usage("M83\nT0\nG1 E10.2\n" + _footer([10], [10]), 1.0, _XL_PM)
    assert _gap_lines(logs) == []


def test_every_head_over_the_line_gets_its_own_warning(logs):
    g = "M83\nT0\nG1 E11\nT1\nG1 E11\n" + _footer([10, 10], [10, 10])
    _cancel_usage(g, 1.0, _XL_PM)
    lines = [m for m, a in _gap_lines(logs)]
    assert len(lines) == 2, lines
    assert lines[0].startswith("⚠️ XL XL-1:") and lines[1].startswith("⚠️ XL XL-2:"), lines


def test_a_gap_under_a_tenth_of_a_gram_says_nothing(logs):
    """A Core One MMU3-profile file walks a fixed ~29 mm (~0.09 g) of start G-code
    the slicer doesn't count: +4.4% of a 2 g print, and nothing misread."""
    _cancel_usage("M83\nT0\nG1 E2.088\n" + _footer([2], [2]), 1.0, _XL_PM)
    assert _gap_lines(logs) == []


def test_the_warning_never_raises_into_the_deduct(logs):
    usage, terminal = _cancel_usage("M83\nT0\nG1 E11\n" + _footer([10], [10]), 1.0,
                                    {"XL-1": "not a dict"})
    assert terminal is None and usage == {0: 10.0}
    assert _gap_lines(logs) == []


def test_a_tool_whose_walk_nets_nothing_falls_back_to_the_footer_ratio():
    """Relative E whose tail nets the tool below zero: there is no share to scale
    by, so the partial is mm x the footer's g/mm (still clamped)."""
    head = "M83\nT0\nG1 E2\n"
    g = head + "G1 E-3\n" + _footer([5], [1.0])          # whole walk -1 mm
    measured = prusalink_api.measure_filament_usage(g, [(len(head) + 1) / len(g)])
    assert "0" not in {str(k) for k in measured["whole"]}
    assert measured["partials"][0][0] == pytest.approx(0.4)   # 2 mm * 0.2 g/mm


def _split_file():
    # Walks 11 mm against a 10 mm / 5 g footer (10% over), one tool.
    return "M83\nT0\n" + "G1 E1\n" * 11 + _footer([10], [5.0])


def _split(progress):
    text = _split_file()
    swap = [{"position": 0, "progress": progress, "from_sid": 1, "to_sid": 2, "runout": False}]
    with patch.object(prusalink_api, "_download_file_bytes", return_value=text.encode()):
        return print_deduct._compute_swap_split("ip", "k", "f.gcode", {0: 5.0}, swap, {"0": 1},
                                                path_filament_g=0.0, single_position=True)


def test_the_run_out_split_charges_each_spool_its_share_of_the_footer():
    """Driven through the real compute_segment_usage (only the download stubbed):
    the swap's cumulative is the footer's share of the walk, not the walk's own
    grams, and the two spools add up to the footer."""
    text = _split_file()
    cut = int(0.5 * len(text.encode()))
    cuts, whole = prusalink_api._walk_extrusion(text, [cut], 0)
    share = round(5.0 * cuts[0][0][0] / whole[0][0], 2)
    rows = _split(0.5)[0]
    assert rows[0] == {"sid": 1, "grams": share, "segment": 0, "runout": False}, rows
    assert rows[1]["sid"] == 2 and rows[1]["grams"] == pytest.approx(5.0 - share, abs=0.01), rows


def test_a_swap_captured_late_is_split_not_sent_to_the_manual_review():
    """Deliberate (56.2): past the last move the cumulative is the whole footer,
    so the run-out spool takes it all; the raw walk (5.5 g against 5 g) used to
    trip the over-footer guard and drop the split."""
    split = _split(0.999)
    assert split is not None
    assert split[0][0]["grams"] == pytest.approx(5.0) and split[0][1]["grams"] == pytest.approx(0.0)


_JOB_1078 = os.path.join(_HUB, "data", "val_1078.gcode")


@pytest.mark.skipif(not os.path.isfile(_JOB_1078),
                    reason="job 1078's decoded G-code is git-ignored dev data (Derek's PC)")
def test_job_1078s_run_out_split_still_matches_the_scale():
    """The 2026-07-02 validation: Core One job 1078 ran out, and the scale said
    the replacement spool used 83.2 g. Fed the true cut (21.7%), the split gave
    83.28 g before 56.2; with arcs counted and the cumulative scaled to the
    footer it gives 83.19 g."""
    g = _read_text(_JOB_1078)
    measured = prusalink_api.measure_filament_usage(g, [0.217])
    assert measured["footer"] == {0: 109.76}
    assert abs(measured["whole"][0] - 109.76) < 0.01, measured["whole"]
    replacement = 109.76 - measured["partials"][0][0]
    assert abs(replacement - 83.2) < 0.1, replacement


def _isolated_tracker(monkeypatch, tmp_path):
    import print_tracker_store
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", False)
    monkeypatch.setattr(print_monitor, "_fcc_owns_completion_deduct", lambda: False)
    monkeypatch.setattr(print_deduct, "_snapshot_active_spools", lambda *a, **k: {})
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER.clear()


def _tick(state_name, job):
    with patch.object(prusalink_api, "get_printer_job", return_value=job):
        print_monitor._track_print_edge("XL", {"state": state_name}, "http://fb")


def test_an_unsampled_end_is_stored_as_unsampled_not_replaced(logs, monkeypatch, tmp_path):
    """A job latched with no progress that reaches IDLE, and a restart's recovery
    of one, ended before FCC read its progress; only the job change "replaced"
    it (the reason rides on the record for the card)."""
    _isolated_tracker(monkeypatch, tmp_path)
    try:
        _tick("PRINTING", {"filename": "f.gcode", "job_id": 7, "progress": None})
        with patch.object(print_monitor, "_dispatch_ambiguous_edge") as disp:
            _tick("IDLE", {})
        assert disp.call_args.kwargs.get("unmeasured_reason") == "unsampled"
        print_monitor._PRINT_TRACKER.clear()
        _tick("PRINTING", {"filename": "f.gcode", "job_id": 7, "progress": None})
        with patch.object(print_monitor, "_dispatch_ambiguous_edge") as disp:
            _tick("PRINTING", {"filename": "g.gcode", "job_id": 8, "progress": 0.1})
        assert disp.call_args.kwargs.get("unmeasured_reason", "replaced") == "replaced"
        entry = {"state": "PRINTING", "job_id": 9, "filename": "f.gcode"}
        with patch.object(prusalink_api, "get_printer_state", return_value={"state": "IDLE"}), \
             patch.object(print_monitor, "_dispatch_ambiguous_edge") as disp:
            print_monitor._recover_one_print_latch("XL", entry, "http://fb")
        assert disp.call_args.kwargs.get("unmeasured_reason") == "unsampled"
    finally:
        print_monitor._PRINT_TRACKER.clear()
    print_monitor._on_ambiguous_edge("XL", NASTY, "U-1", 0.0, "http://fb", progress_unknown=True,
                                     unmeasured_reason="unsampled")
    rec = cancel_review_store.get_pending("XL", "U-1")
    assert rec["unmeasured_reason"] == "unsampled" and rec["ambiguous"] is True
    assert any("ended before its progress" in m for m, a, k in logs), logs


def _ambiguous_review(gcode, frac=0.99, ambiguous=True, job="A-1"):
    with patch.object(prusalink_api, "fetch_printer_credentials",
                      return_value={"ip_address": "1.2.3.4", "api_key": "k"}), \
         patch.object(print_deduct.locations_db, "get_active_printer_map", return_value=_XL_PM), \
         patch.object(prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, f: {"gcode": gcode, "fraction": f}):
        return print_deduct._create_pending_cancel_review("XL", NASTY, job, frac,
                                                          fb_url="http://fb", ambiguous=ambiguous)


def test_an_ambiguous_end_fcc_cant_measure_asks_instead_of_recording_zero(logs):
    """FINISHED was missed (the next poll saw IDLE): it may have been a completion,
    so a file without a footer opens the "couldn't measure" review, as 56.3 does
    for completions; a true cancel keeps the 0 g entry and its WARNING."""
    out = _ambiguous_review("M83\nT0\nG1 E5\n; another slicer's file\n")
    assert out["status"] == "pending_unresolved", out
    rec = cancel_review_store.get_pending("XL", "A-1")
    assert rec["unmeasured_reason"] == "no_footer" and rec["ambiguous"] is True
    assert print_deduct_ledger.was_deducted("XL", "A-1") is False
    assert not any("non-Prusa slicer" in m for m, a, k in logs), logs   # one line, the review's
    out = _ambiguous_review("M83\nT0\nG1 E5\n; another slicer's file\n", ambiguous=False, job="C-1")
    assert out["status"] == "no_usage"
    assert print_deduct_ledger.was_deducted("XL", "C-1") is True
    assert any("non-Prusa slicer" in m and NASTY_ESC in m for m, a, k in logs), logs


def test_an_ambiguous_end_before_any_extrusion_still_records_zero(logs):
    head = "M83\nT0\n"
    g = head + "G1 E5\n" + _footer([5], [1.0])
    out = _ambiguous_review(g, frac=(len(head) - 1) / len(g))
    assert out["status"] == "no_usage" and out.get("reason") == "nothing_reached", out
    assert print_deduct_ledger.was_deducted("XL", "A-1") is True


def test_moves_the_walk_cant_read_are_named_not_called_an_early_cancel(logs):
    """Line-numbered moves the walk doesn't read: the footer lists filament but
    the walk finds none. A cancel says FCC couldn't read the moves (and warns per
    head), never "cancelled before any extrusion"; an ambiguous end asks."""
    g = "N1 M83\nN2 T0\nN3 G1 X10 E5\n" + _footer([5], [1.0])
    out = _ambiguous_review(g, frac=0.6, ambiguous=False, job="M-1")
    assert out["status"] == "no_usage" and out.get("reason") == "unreadable_moves", out
    msgs = [m for m, a, k in logs]
    assert any("couldn't read this file's moves" in m for m in msgs), msgs
    assert not any("before any extrusion" in m for m in msgs), msgs
    assert len(_gap_lines(logs)) == 1
    out = _ambiguous_review(g, frac=0.6, job="M-2")
    assert out["status"] == "pending_unresolved"
    assert cancel_review_store.get_pending("XL", "M-2")["unmeasured_reason"] == "unreadable_moves"


def test_the_give_up_honours_the_crash_guard(logs):
    """A queued completion whose retry charged the spools and stashed an
    uncharged-grams card, then died before its ledger write, is a deducted job:
    past the 72 h window it gets its ledger entry, not a card saying nothing was
    deducted."""
    cancel_review_store.add_pending({"printer_name": "XL", "job_id": "J-9#shortfall",
                                     "shortfall_of": "J-9", "kind": "shortfall", "filename": NASTY,
                                     "spools": [], "total_grams": 15.0})
    _aged_fetch("complete")
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True):
        print_monitor._process_pending_cancel_fetches({"XL": {"state": "IDLE"}}, "http://fb")
    assert not cancel_fetch_store.has_pending("XL", "J-9")
    assert not cancel_review_store.has_pending("XL", "J-9")
    assert print_deduct_ledger.was_deducted("XL", "J-9") is True
    assert any("was already deducted" in m for m, a, k in logs), logs


def test_a_give_up_while_fcc_doesnt_own_completions_keeps_the_old_record(logs):
    _aged_fetch("complete")
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=False):
        print_monitor._process_pending_cancel_fetches({"XL": {"state": "IDLE"}}, "http://fb")
    assert print_deduct_ledger.was_deducted("XL", "J-9") is True
    assert not cancel_review_store.has_pending("XL", "J-9")
    assert any("Gave up fetching the completed print's gcode" in m for m, a, k in logs), logs


def test_a_queued_completion_that_raises_is_dropped_not_charged_again(logs):
    """The deduct writes the spools before its ledger entry; a raise in between
    (a full disk) used to leave the entry queued, and every IDLE tick charged the
    footer again."""
    cancel_fetch_store.add_pending({
        "printer_name": "XL", "job_id": "Q-1", "filename": NASTY, "progress": 1.0,
        "first_seen": time.time(), "kind": "complete", "attempts": 1})
    calls = []

    def _boom(*a, **k):
        calls.append(1)
        raise OSError("[Errno 28] No space left <on device>")
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(print_deduct, "deduct_completed_print", side_effect=_boom):
        print_monitor._process_pending_cancel_fetches({"XL": {"state": "IDLE"}}, "http://fb")
        print_monitor._process_pending_cancel_fetches({"XL": {"state": "IDLE"}}, "http://fb")
    assert len(calls) == 1
    assert not cancel_fetch_store.has_pending("XL", "Q-1")
    line = next(m for m, a, k in logs if "Completed-print deduct failed" in m)
    assert NASTY_ESC in line and "&lt;on device&gt;" in line and "not retried" in line, line


def test_a_queued_job_without_an_id_is_dropped_with_a_word(logs):
    cancel_fetch_store.add_pending({
        "printer_name": "XL", "job_id": "", "filename": NASTY, "progress": 1.0,
        "first_seen": time.time(), "kind": "complete", "attempts": 1})
    print_monitor._process_pending_cancel_fetches({"XL": {"state": "IDLE"}}, "http://fb")
    assert cancel_fetch_store.list_pending() == []
    assert any("no job id" in m and NASTY_ESC in m for m, a, k in logs), logs


def test_a_completion_held_by_a_review_is_not_charged_behind_it(logs):
    """A restart's recovery can fire a completion again; while a review holds the
    job, nothing is charged (its Discard would otherwise overwrite the entry)."""
    _complete_with("M83\nT0\nG1 E5\n")                    # a no_footer review for J-7
    with patch.object(print_deduct, "_apply_usage_to_printer",
                      side_effect=AssertionError("charged behind a pending review")):
        out = _complete_with("M83\nT0\nG1 E5\n" + _footer([5], [5]))
    assert out == {"status": "skipped", "reason": "already pending", "job_id": "J-7"}
    assert print_deduct_ledger.was_deducted("XL", "J-7") is False


def test_a_review_the_store_pushes_out_is_reported(logs, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_MAX_ENTRIES", 3)
    for i in range(4):
        cancel_review_store.add_pending({"printer_name": "XL", "job_id": f"E-{i}", "filename": NASTY,
                                         "kind": "no_spool", "total_grams": 2.5, "spools": []})
    assert len(cancel_review_store.list_pending()) == 3
    assert not cancel_review_store.has_pending("XL", "E-0")
    line = next(m for m, a, k in logs if "Review list is full" in m)
    assert "job E-0" in line and "2.50g" in line and NASTY_ESC in line, line
