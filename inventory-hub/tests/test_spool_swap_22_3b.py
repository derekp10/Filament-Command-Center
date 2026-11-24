"""Group 22.3(b) — mid-print swap-event capture (swap_log) + the Color-Change
segmentation primitive.

22.3(c) (already shipped) routes a completion to a manual-split review when a USED
toolhead's spool changed start→completion, detected by a coarse 2-point START-vs-END
snapshot diff. 22.3(b) builds the FOUNDATION for full per-segment apportionment:

  - CAPTURE: on each resume INTO printing from a pause/ATTENTION (M600 / Color-Change /
    runout) on the SAME already-snapshotted job, diff a fresh snapshot against the
    mapping the just-printed segment fed from and append an ordered swap_log event.
    This catches an A→B→A swap (ran out, replaced, original re-loaded → start==end) the
    2-point diff misses, and records the per-segment history.
  - THREADING: swap_log rides the fire dict (live edge), the persisted entry (restart),
    and the deferred-fetch record (finish-screen lock) into deduct_completed_print, with
    the same snapshot_job guard as start_spools.
  - ROUTING (safe degrade): a non-empty swap_log at a used position routes the completion
    to the SAME spool_changed review, never auto-applied. (Its grams are split at the
    swaps since the print-end hotfix, 2026-11-11, scope B: _compute_swap_split, from the
    print's one download; a head FCC can't split is held as a set. This file pins the
    capture and the route.)
  - SEGMENTATION primitive: parse_color_change_segments scans decoded gcode for
    ;COLOR_CHANGE markers → ordered cut boundaries. Pure; NOT wired to any weight write.
"""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
import print_deduct  # L316: patch targets / live seams for moved symbols
import print_monitor  # L316: patch targets for moved symbols  # noqa: E402
import prusalink_api  # noqa: E402
import cancel_review_store  # noqa: E402
import cancel_fetch_store  # noqa: E402
import functools  # noqa: E402

# Group 64.3 (9): the isolation fixture (autouse), the latch driver, the
# completion's mocks and the made-up XL, shared with test_spool_swap_22_3.py.
from spool_swap_harness import ACTIVE, PM, completion_ctx, reset  # noqa: E402,F401  (reset: autouse)
from spool_swap_harness import creds as _creds  # noqa: E402,F401
from spool_swap_harness import latch as _latch  # noqa: E402

# This file's completion row is #100, the spool its swaps start from.
_completion_ctx = functools.partial(completion_ctx, default_sid=100)


# =========================================================================== #
# _record_swap_events — the diff-and-append helper                            #
# =========================================================================== #


def test_is_sid_swap_predicate():
    """Shared predicate: confident 1→1 only; None either side = no swap; string-compared
    so a JSON int↔str round-trip of the SAME sid never reads as a change, and a
    non-numeric sid can't raise (the old bare int() could ValueError → silent auto-apply)."""
    assert app_module._is_sid_swap(100, 200) is True
    assert app_module._is_sid_swap(100, 100) is False
    assert app_module._is_sid_swap("100", 100) is False   # int↔str same sid = NOT a swap
    assert app_module._is_sid_swap(None, 200) is False
    assert app_module._is_sid_swap(100, None) is False
    assert app_module._is_sid_swap("A", "B") is True      # non-numeric never raises


def test_record_clean_change_appends_event():
    import time as _t
    entry = {"start_spools": {"0": 100}}
    before = _t.time()
    n = app_module._record_swap_events(entry, {0: 200}, 0.5)
    assert n == 1
    # Group 64 fix review 2 (CS1): each event keeps when the print resumed (it is
    # recorded at the resume), which ends the time the spool it took off was off a head.
    back_at = entry["swap_log"][0].pop("back_at")
    assert before <= back_at <= _t.time(), back_at
    # runout defaults False (feature/runout-auto-split 2026-07-03: a manual/PAUSED swap,
    # not an ATTENTION runout, so no sensor→nozzle path remnant is charged).
    assert entry["swap_log"] == [
        {"seq": 0, "position": 0, "progress": 0.5, "from_sid": 100, "to_sid": 200,
         "runout": False}]


def test_record_same_sid_no_event():
    entry = {"start_spools": {"0": 100}}
    assert app_module._record_swap_events(entry, {0: 100}, 0.5) == 0
    assert "swap_log" not in entry


@pytest.mark.parametrize("end_snap", [{0: None}, {}])
def test_record_none_after_no_event(end_snap):
    """A position that's EMPTY/ambiguous at resume (None, or absent from the snap) is
    NOT a confident swap — mirrors the completion-time guard."""
    entry = {"start_spools": {"0": 100}}
    assert app_module._record_swap_events(entry, end_snap, 0.5) == 0
    assert "swap_log" not in entry


def test_record_none_before_no_event():
    """A position EMPTY at the start of the segment (None) → not a confident swap."""
    entry = {"start_spools": {"0": None}}
    assert app_module._record_swap_events(entry, {0: 200}, 0.5) == 0


def test_record_sequential_swaps_diff_running_mapping():
    """A→B then B→C: the second resume diffs against the RUNNING mapping (B), not the
    original start (A), so it records B→C with the next seq."""
    entry = {"start_spools": {"0": 100}}
    app_module._record_swap_events(entry, {0: 200}, 0.3)   # A→B
    app_module._record_swap_events(entry, {0: 300}, 0.6)   # B→C
    assert [(e["from_sid"], e["to_sid"], e["seq"]) for e in entry["swap_log"]] == [
        (100, 200, 0), (200, 300, 1)]


def test_record_a_b_a_records_two_events():
    """A→B→A: end mapping == start, but TWO swaps happened — both recorded (this is the
    case the coarse start-vs-end diff misses)."""
    entry = {"start_spools": {"0": 100}}
    app_module._record_swap_events(entry, {0: 200}, 0.3)   # A→B
    app_module._record_swap_events(entry, {0: 100}, 0.6)   # B→A
    assert len(entry["swap_log"]) == 2
    assert (entry["swap_log"][1]["from_sid"], entry["swap_log"][1]["to_sid"]) == (200, 100)


def test_record_multi_position_one_resume():
    """Two toolheads swapped at the same pause → two events from one diff."""
    entry = {"start_spools": {"0": 100, "1": 200}}
    n = app_module._record_swap_events(entry, {0: 101, 1: 201}, 0.5)
    assert n == 2
    assert {(e["position"], e["from_sid"], e["to_sid"]) for e in entry["swap_log"]} == {
        (0, 100, 101), (1, 200, 201)}


# =========================================================================== #
# Resume capture in _track_print_edge                                         #
# =========================================================================== #

JOB = {"filename": "m600.gcode", "job_id": 9, "progress": 0.5}


@pytest.mark.parametrize("pause_state", ["PAUSED", "ATTENTION"])
def test_resume_from_pause_captures_swap(pause_state):
    """PRINTING(start) → pause(PAUSED/ATTENTION) → PRINTING(resume) with a changed
    mapping appends a swap_log event. ATTENTION (the M600/runout park, not a latch
    state) must trigger as well as PAUSED."""
    snap = MagicMock(side_effect=[{0: 100}, {0: 200}])
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(print_deduct, "_snapshot_active_spools", snap):
        _latch("PRINTING", dict(JOB))         # start snapshot {0:100}
        _latch(pause_state, dict(JOB))        # pause — no snapshot
        _latch("PRINTING", dict(JOB))         # resume snapshot {0:200} → swap
    assert snap.call_count == 2
    e = app_module._PRINT_TRACKER["XL"]
    assert [(x["from_sid"], x["to_sid"]) for x in e["swap_log"]] == [(100, 200)]
    assert e["swap_log"][0]["progress"] == 0.5


def test_first_printing_tick_does_not_capture_swap():
    """The job's FIRST printing tick is the START snapshot (snapshot_job not yet set),
    NOT a resume — no swap_log."""
    snap = MagicMock(return_value={0: 100})
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(print_deduct, "_snapshot_active_spools", snap):
        _latch("PRINTING", dict(JOB))
    assert snap.call_count == 1
    assert "swap_log" not in app_module._PRINT_TRACKER["XL"]


def test_resume_unchanged_mapping_no_swap():
    snap = MagicMock(side_effect=[{0: 100}, {0: 100}])
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(print_deduct, "_snapshot_active_spools", snap):
        _latch("PRINTING", dict(JOB))
        _latch("PAUSED", dict(JOB))
        _latch("PRINTING", dict(JOB))
    assert snap.call_count == 2  # start + resume both snapshot...
    assert "swap_log" not in app_module._PRINT_TRACKER["XL"]  # ...but the diff is empty


def test_resume_blip_snapshot_skips_and_retries():
    """An empty resume snapshot (Spoolman blip) records nothing; the NEXT resume retries
    and captures the swap."""
    snap = MagicMock(side_effect=[{0: 100}, {}, {0: 200}])
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(print_deduct, "_snapshot_active_spools", snap):
        _latch("PRINTING", dict(JOB))   # start {0:100}
        _latch("PAUSED", dict(JOB))
        _latch("PRINTING", dict(JOB))   # resume blip {} → nothing
        assert "swap_log" not in app_module._PRINT_TRACKER["XL"]
        _latch("PAUSED", dict(JOB))
        _latch("PRINTING", dict(JOB))   # resume {0:200} → swap
    assert [(x["from_sid"], x["to_sid"]) for x in
            app_module._PRINT_TRACKER["XL"]["swap_log"]] == [(100, 200)]


def test_resume_capture_runs_with_the_flag_off():
    """Group 64.3 (2): with the completion-ownership flag off, the start AND the
    resume snapshot still run: the cancel and ambiguous reviews read them too (since
    the print-end hotfix of 2026-11-11), not only deduct_completed_print. A swap at
    the pause is recorded."""
    snap = MagicMock(side_effect=[{0: 100}, {0: 200}])
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=False), \
         patch.object(print_deduct, "_snapshot_active_spools", snap), \
         patch.object(app_module.state, "add_log_entry"):
        _latch("PRINTING", dict(JOB))
        _latch("PAUSED", dict(JOB))
        _latch("PRINTING", dict(JOB))
    assert snap.call_count == 2
    entry = app_module._PRINT_TRACKER["XL"]
    assert entry["start_spools"] == {"0": 100}
    assert [(ev["from_sid"], ev["to_sid"]) for ev in entry["swap_log"]] == [(100, 200)]


def test_job_change_pops_swap_log():
    """A new job must not inherit the previous job's swap history."""
    with app_module._PRINT_TRACKER_LOCK:
        app_module._PRINT_TRACKER["XL"] = {
            "state": "PRINTING", "job_id": 9, "filename": "a.gcode", "progress": 0.5,
            "start_spools": {"0": 100}, "snapshot_job": "9",
            "swap_log": [{"seq": 0, "position": 0, "from_sid": 100, "to_sid": 200,
                          "progress": 0.4}]}
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(print_deduct, "_snapshot_active_spools", return_value={0: 300}), \
         patch.object(app_module.state, "add_log_entry"):
        _latch("PRINTING", {"filename": "b.gcode", "job_id": 10, "progress": 0.1})
    assert "swap_log" not in app_module._PRINT_TRACKER["XL"]


def test_capture_a_b_a_end_to_end():
    """Full sequence: start A → swap to B → swap back to A. swap_log has 2 events even
    though the final mapping equals the start."""
    snap = MagicMock(side_effect=[{0: 100}, {0: 200}, {0: 100}])
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(print_deduct, "_snapshot_active_spools", snap):
        _latch("PRINTING", dict(JOB))   # start A
        _latch("PAUSED", dict(JOB))
        _latch("PRINTING", dict(JOB))   # → B
        _latch("PAUSED", dict(JOB))
        _latch("PRINTING", dict(JOB))   # → A
    log = app_module._PRINT_TRACKER["XL"]["swap_log"]
    assert [(x["from_sid"], x["to_sid"]) for x in log] == [(100, 200), (200, 100)]


# =========================================================================== #
# Threading swap_log → completion                                             #
# =========================================================================== #

def test_validated_swap_log_job_guard():
    log = [{"seq": 0, "position": 0, "from_sid": 100, "to_sid": 200}]
    src = {"swap_log": log, "snapshot_job": "9"}
    assert app_module._validated_swap_log(src, 9) == log     # int 9 vs str '9'
    assert app_module._validated_swap_log(src, 10) is None    # stale job
    assert app_module._validated_swap_log(None, 9) is None


def test_fire_dict_threads_swap_log_to_completion():
    log = [{"seq": 0, "position": 0, "from_sid": 100, "to_sid": 200, "progress": 0.5}]
    with app_module._PRINT_TRACKER_LOCK:
        app_module._PRINT_TRACKER["XL"] = {
            "state": "PRINTING", "job_id": 9, "filename": "m600.gcode", "progress": 0.9,
            "start_spools": {"0": 100}, "snapshot_job": "9", "swap_log": log}
    disp = MagicMock()
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(print_monitor, "_dispatch_completion_edge", disp), \
         patch.object(app_module.state, "add_log_entry"):
        _latch("FINISHED", None)
    disp.assert_called_once()
    assert disp.call_args.kwargs.get("swap_log") == log


def test_restart_recovery_threads_persisted_swap_log():
    log = [{"seq": 0, "position": 0, "from_sid": 100, "to_sid": 200, "progress": 0.5}]
    entry = {"state": "PRINTING", "job_id": 9, "filename": "m600.gcode", "progress": 0.9,
             "start_spools": {"0": 100}, "snapshot_job": "9", "swap_log": log}
    disp = MagicMock()
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module.prusalink_api, "get_printer_state", return_value={"state": "FINISHED"}), \
         patch.object(print_monitor, "_dispatch_completion_edge", disp), \
         patch.object(app_module.state, "add_log_entry"):
        app_module._recover_one_print_latch("XL", entry, "http://fb")
    disp.assert_called_once()
    assert disp.call_args.kwargs.get("swap_log") == log


def test_enqueue_persists_swap_log():
    log = [{"seq": 0, "position": 0, "from_sid": 100, "to_sid": 200}]
    with patch.object(app_module.state, "add_log_entry"):
        app_module._enqueue_cancel_fetch("XL", "m600.gcode", "J-Q", 1.0, kind="complete",
                                         start_spools={"0": 100}, swap_log=log)
    rec = cancel_fetch_store.get_pending("XL", "J-Q")
    assert rec["swap_log"] == log


def test_deferred_retry_threads_swap_log():
    """The deferred-fetch retry reads swap_log off the record and passes it into the
    completion deduct (so an A→B→A swap survives the finish-screen lock)."""
    log = [{"seq": 0, "position": 0, "from_sid": 100, "to_sid": 200}]
    cancel_fetch_store.add_pending({
        "printer_name": "XL", "job_id": "J-D", "filename": "m600.gcode",
        "progress": 1.0, "first_seen": time.time(), "kind": "complete",
        "start_spools": {"0": 100}, "swap_log": log,
        "attempts": 1, "last_status": "awaiting_fetch"})
    comp = MagicMock(return_value={"status": "deducted", "job_id": "J-D"})
    states = {"XL": {"state": "IDLE"}}
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(print_deduct, "deduct_completed_print", comp):
        app_module._process_pending_cancel_fetches(states, "http://fb")
    comp.assert_called_once()
    assert comp.call_args.kwargs.get("swap_log") == log


# =========================================================================== #
# Routing in deduct_completed_print (the A→B→A safe degrade)                   #
# =========================================================================== #

def test_swap_log_routes_when_start_equals_end():
    """A→B→A: start_spools == end_snap (so the 2-point diff finds NO change), but the
    swap_log at a USED position routes to review (the 22.3(b) gap-closer)."""
    log = [{"seq": 0, "position": 0, "from_sid": 100, "to_sid": 200, "progress": 0.4},
           {"seq": 1, "position": 0, "from_sid": 200, "to_sid": 100, "progress": 0.7}]
    ctx, apply_mock = _completion_ctx(usage_map={0: 25.0}, end_snap={0: 100})
    for m in ctx:
        m.start()
    try:
        res = app_module.deduct_completed_print("XL", "m600.gcode", "J-1",
                                                start_spools={"0": 100}, swap_log=log)
    finally:
        for m in reversed(ctx):
            m.stop()
    assert res["status"] == "pending_spool_changed", res
    apply_mock.assert_not_called()
    rec = cancel_review_store.get_pending("XL", "J-1")
    assert rec and rec["kind"] == "spool_changed"
    assert rec["swap_log"] == log               # carried for future apportionment
    assert rec["changed_positions"] == [0]


def test_swap_log_at_unused_position_auto_applies():
    """A swap recorded at a position with NO footer usage (grams 0 / untouched head)
    must not block the deduct — auto-apply the used positions."""
    log = [{"seq": 0, "position": 1, "from_sid": 200, "to_sid": 201, "progress": 0.4}]
    ctx, apply_mock = _completion_ctx(usage_map={0: 25.0}, end_snap={0: 100})
    apply_mock.return_value = (1, [{"sid": 100, "grams": 25.0, "remaining": 900.0}], {0})
    for m in ctx:
        m.start()
    try:
        res = app_module.deduct_completed_print("XL", "m600.gcode", "J-2",
                                                start_spools={"0": 100}, swap_log=log)
    finally:
        for m in reversed(ctx):
            m.stop()
    assert res["status"] == "deducted"
    apply_mock.assert_called_once()
    assert cancel_review_store.get_pending("XL", "J-2") is None


def test_empty_swap_log_no_start_spools_auto_applies():
    """swap_log=[] and start_spools=None → detection is skipped entirely → auto-apply."""
    apply_mock = MagicMock(return_value=(1, [{"sid": 100, "grams": 25.0, "remaining": 900.0}], {0}))
    snap = MagicMock(return_value={0: 100})
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(print_deduct, "_compute_cancel_usage", return_value=({0: 25.0}, None)), \
         patch.object(app_module.locations_db, "get_active_printer_map", return_value=PM), \
         patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=ACTIVE), \
         patch.object(print_deduct, "_snapshot_active_spools", snap), \
         patch.object(print_deduct, "_apply_usage_to_printer", apply_mock), \
         patch.object(app_module.state, "add_log_entry"):
        res = app_module.deduct_completed_print("XL", "m600.gcode", "J-3",
                                                start_spools=None, swap_log=[])
    assert res["status"] == "deducted"
    apply_mock.assert_called_once()
    snap.assert_not_called()   # no detection work at all


# =========================================================================== #
# parse_color_change_segments — the segmentation primitive (scaffold)         #
# =========================================================================== #

def test_color_change_segments_basic():
    gcode = (
        "; filament used [g] = 12.0\n"
        "G1 X0 Y0 E1\n"
        ";COLOR_CHANGE,T0,#FF8800\n"
        "G1 X1 Y1 E2\n"
        ";COLOR_CHANGE,T0,#00AA55\n"
        "G1 X2 Y2 E3\n")
    segs = prusalink_api.parse_color_change_segments(gcode)
    assert len(segs) == 2
    assert [s["seq"] for s in segs] == [0, 1]
    assert [s["tool"] for s in segs] == [0, 0]
    assert [s["color"] for s in segs] == ["#FF8800", "#00AA55"]
    # boundaries are in file order, strictly increasing, inside (0, 1)
    assert 0 < segs[0]["fraction"] < segs[1]["fraction"] < 1
    assert segs[0]["byte_offset"] < segs[1]["byte_offset"]


def test_color_change_segments_none_when_absent():
    assert prusalink_api.parse_color_change_segments("G1 X0 E1\nG1 X1 E2\n") == []
    assert prusalink_api.parse_color_change_segments("") == []


def test_color_change_segments_rejects_lookalike_tokens():
    """The \\b after COLOR_CHANGE rejects lookalike comments that merely START with the
    token — only the real marker (followed by ',', whitespace, or EOL) boundaries."""
    gcode = (";COLOR_CHANGE_DATA bla\n"
             ";COLOR_CHANGEDFOO\n"
             ";COLOR_CHANGES_REMAINING=3\n"
             ";COLOR_CHANGE,T0,#FF0000\n")   # only THIS one is a real boundary
    segs = prusalink_api.parse_color_change_segments(gcode)
    assert len(segs) == 1
    assert segs[0]["tool"] == 0 and segs[0]["color"] == "#FF0000"


def test_color_change_segments_tolerates_missing_tool_and_color():
    segs = prusalink_api.parse_color_change_segments(";COLOR_CHANGE\nG1 E1\n")
    assert len(segs) == 1
    assert segs[0]["tool"] is None and segs[0]["color"] is None


def test_color_change_segments_normalizes_hex_without_hash():
    segs = prusalink_api.parse_color_change_segments(";COLOR_CHANGE,T2,AABBCC\n")
    assert segs[0]["tool"] == 2
    assert segs[0]["color"] == "#AABBCC"


def test_color_change_byte_offset_matches_partial_parse_space():
    """The boundary fraction is the SAME file-byte space parse_partial_filament_usage
    slices on, so a future apportionment can prefix-parse straight to a boundary."""
    head = "; filament used [g] = 9.0\n" + "G1 E1\n" * 5
    gcode = head + ";COLOR_CHANGE,T0,#112233\nG1 E2\n"
    segs = prusalink_api.parse_color_change_segments(gcode)
    expected_byte = len(head.encode("utf-8"))
    assert segs[0]["byte_offset"] == expected_byte
    total = len(gcode.encode("utf-8"))
    assert abs(segs[0]["fraction"] - expected_byte / total) < 1e-6


# =========================================================================== #
# Group 64.3 (4): the resume's words, and no file_meta on the latch            #
# =========================================================================== #

def _resume_lines(first, second, pause_state="ATTENTION", runout_job=None):
    """A start snapshot, a pause, a resume: the Activity Log lines the resume wrote."""
    with app_module._PRINT_TRACKER_LOCK:
        app_module._PRINT_TRACKER.clear()      # each call is its own print
    snap = MagicMock(side_effect=[dict(first), dict(second)])
    job = dict(runout_job or JOB)
    with patch.object(print_deduct, "_snapshot_active_spools", snap), \
            patch.object(app_module.state, "add_log_entry") as log:
        _latch("PRINTING", job)
        _latch(pause_state, dict(job, progress=0.6))
        _latch("PRINTING", dict(job, progress=0.6))
    return [c.args[0] for c in log.call_args_list if "resumed job" in c.args[0]]


def test_a_resume_with_no_change_says_so_in_words():
    """The resume line names each head's spool in words and says no change was
    recorded: never "the full footer will be billed" (a print then cancelled is
    charged only its printed part, on a card) and never raw dicts."""
    # On 2742bb7: the line read "... no spool mapping change at any toolhead (before={'0': 100,
    # '1': 7}, after={0: 100, 1: 7}), so no swap was recorded and the full footer will be billed as-is."
    lines = _resume_lines({0: 100, 1: 7}, {0: 100, 1: 7})
    assert lines == ["🔁 XL: resumed job 9 at ~60.0% with the same spool on every head (T0 #100, T1 #7), "
                     "so no change was recorded."], lines


def test_a_resume_with_a_change_names_it_in_words():
    lines = _resume_lines({0: 100}, {0: 200})
    assert lines == ["🔁 XL: resumed job 9 at ~60.0%, after a run-out, with a spool changed "
                     "(T0: #100 → #200): FCC splits its grams at the change."], lines
    lines = _resume_lines({0: 100}, {0: 200}, pause_state="PAUSED")
    assert lines == ["🔁 XL: resumed job 9 at ~60.0% with a spool changed (T0: #100 → #200): FCC "
                     "splits its grams at the change."], lines


def test_the_latch_keeps_no_file_meta():
    """Nothing read the slicer's estimate the latch kept ("for slice 5's preview UX"):
    it is no longer kept."""
    with patch.object(print_deduct, "_snapshot_active_spools", MagicMock(return_value={0: 100})):
        _latch("PRINTING", dict(JOB, file_meta={"filament used [g]": "40, 32"}))
    assert "file_meta" not in app_module._PRINT_TRACKER["XL"], app_module._PRINT_TRACKER["XL"]
