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
    G27 / G21 stay out even with an E-like parameter: `^G[0-3](?![0-9])`."""
    g = ("M83\nT0\n"
         "G10 E5\nG11 E5\nG12 S90 E5\nG28 E5\nG29 E5\nG27 E5\nG21 E5\n"
         "G1 E1\n"
         + _footer([1], [1]))
    measured = prusalink_api.measure_filament_usage(g, [1.0])
    assert abs(measured["whole"][0] - 1.0) < 1e-9, measured


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
    regex before 56.1) falls short on every tool by more than 10%."""
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
    assert sum(measured["partials"][0].values()) == pytest.approx(23.80, abs=0.05)


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
    than the whole file: the charge stops at the footer."""
    head = "M83\nT0\nG1 E10\n"
    g = head + "G1 E-2\n" + _footer([10], [1.0])
    measured = prusalink_api.measure_filament_usage(g, [(len(head) + 1) / len(g)])
    assert measured["partials"][0][0] == pytest.approx(1.0)


def test_absolute_e_wipe_tail_keeps_a_late_cancel_under_the_footer():
    head = "M82\nT0\nG92 E0\nG1 E9.9\n"
    g = head + "G1 E9.0\nG1 E10\n" + _footer([10], [1.0])   # a wipe, then the last 0.1mm
    late = prusalink_api.parse_partial_filament_usage(g, (len(head) + 1) / len(g))
    assert late[0] == pytest.approx(0.99)
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
    assert "couldn't download its file" in logs[-1][0]


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


def _unescaped_filenames(source, name):
    """(offenders, checked): every f-string field naming a filename inside an
    add_log_entry message (directly, or through a variable the same function
    assigns and then logs) must go through an escape."""
    tree = ast.parse(source)
    offenders, checked = set(), set()
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        assigns = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigns.setdefault(target.id, []).append(node.value)
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_log_entry" and node.args):
                continue
            msg = node.args[0]
            exprs = assigns.get(msg.id, []) if isinstance(msg, ast.Name) else [msg]
            for expr in exprs:
                for field in ast.walk(expr):
                    if not isinstance(field, ast.FormattedValue):
                        continue
                    text = ast.unparse(field.value)
                    if "filename" not in text:
                        continue
                    checked.add((name, field.lineno, text))
                    v = field.value
                    if not (isinstance(v, ast.Call) and ast.unparse(v.func) in _ESCAPES):
                        offenders.add(f"{name}:{field.lineno}: {{{text}}}")
    return sorted(offenders), checked


def test_the_escape_canary_catches_a_raw_filename():
    src = ("def f(filename, rec):\n"
           "    state.add_log_entry(f\"ok '{_esc(filename)}'\", 'INFO')\n"
           "    msg = f\"bad '{rec.get('filename')}'\"\n"
           "    state.add_log_entry(msg, 'INFO')\n"
           "    state.add_log_entry(f\"bad '{filename}'\", 'INFO')\n")
    offenders, checked = _unescaped_filenames(src, "x.py")
    assert len(checked) == 3 and len(offenders) == 2, (offenders, checked)


def test_every_deduct_and_monitor_log_line_escapes_its_filename():
    offenders, checked = [], set()
    for name in ("print_deduct.py", "print_monitor.py"):
        with open(os.path.join(_HUB, name), encoding="utf-8") as fh:
            bad, seen = _unescaped_filenames(fh.read(), name)
        offenders += bad
        checked |= seen
    assert not offenders, "log a filename through _esc(...):\n" + "\n".join(offenders)
    assert len(checked) >= 31, len(checked)   # 21 in print_deduct, 10 in print_monitor


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
