"""Group 64.2: the print-end hotfix's smaller known limits, server side.

(10) A cancel's progress is at least where its print got. The latch's progress is
the high-water of the job samples, which can lag a park by a poll (an ATTENTION park
freezes the job past the last PRINTING sample) and the swap a resume records there
(cut at the frozen progress). So a cancel during the park was computed short of it,
and a cancel right after a resume that recorded a swap past the latched progress had
its split refused (the swap's figure ran past the cancel's partial): the head was
held as a set to split by hand. Now the live edge, the job-change review, restart
recovery and the review itself take at least the park's frozen progress and the last
recorded swap's point (`print_deduct._reached_at_least`).

HEAD proof: every test here is red on 6ad359f (before this change) unless it says
it passes there by design.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import cancel_fetch_store  # noqa: E402
import cancel_review_store  # noqa: E402
import print_deduct  # noqa: E402
import print_deduct_ledger  # noqa: E402
import print_monitor  # noqa: E402
import print_tracker_store  # noqa: E402
import prusalink_api  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from deduct_wire_harness import WeightWireSpoolman, _start, _stop  # noqa: E402

XL = "XL"
JOB = 77
SWAP = [{"seq": 0, "position": 0, "progress": 0.45, "from_sid": 100, "to_sid": 200, "runout": True}]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))
    monkeypatch.setattr(spoolman_api, "LAST_SPOOLMAN_ERROR", None)
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", False)
    monkeypatch.setattr(print_monitor, "_FETCH_CLAIMS", set(), raising=False)
    monkeypatch.setattr(print_monitor, "_fcc_owns_completion_deduct", lambda: True)
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    monkeypatch.setattr(print_deduct.config_loader, "load_config", lambda: {})
    monkeypatch.setattr(state, "add_log_entry", lambda *a, **k: None)
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER.clear()
    yield
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER.clear()


def _job(progress):
    return {"filename": "x.gcode", "job_id": JOB, "progress": progress}


def _tick(st, job=None, on_head=None):
    """One monitor tick of the XL; `on_head` is what Spoolman says is on XL-1 now."""
    snap = {0: on_head} if on_head is not None else {}
    with patch.object(print_monitor.prusalink_api, "get_printer_job", return_value=job), \
            patch.object(print_deduct, "_snapshot_active_spools", return_value=snap):
        print_monitor._track_print_edge(XL, {"state": st}, "http://fb")


def _spool(used, loc):
    return {"used_weight": used, "initial_weight": 1000.0, "archived": False,
            "location": loc, "filament": {"weight": 1000.0}, "extra": {}}


class TwoHeads:
    """The XL's two heads: #200 on XL-1 (#100 ran out on it), #300 on XL-2."""

    def __init__(self):
        self.sm = WeightWireSpoolman({100: _spool(100.0, "SHELF-1"), 200: _spool(10.0, "XL-1"),
                                      300: _spool(10.0, "XL-2")})
        self.at = {"XL-1": [200], "XL-2": [300]}

    def __enter__(self):
        active = [("XL-1", {"position": 0, "printer_name": XL}), ("XL-2", {"position": 1, "printer_name": XL})]
        self._ctx = [
            patch.object(print_deduct.locations_db, "get_active_printer_map",
                         return_value={"XL-1": {"printer_name": XL, "position": 0},
                                       "XL-2": {"printer_name": XL, "position": 1}}),
            patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=active),
            patch.object(spoolman_api, "get_spools_at_location",
                         side_effect=lambda loc: list(self.at.get(str(loc).upper(), []))),
            patch.object(spoolman_api, "select_deduct_targets",
                         side_effect=lambda loc: (list(self.at.get(str(loc).upper(), [])), False)),
            patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
            patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "ff0000"}),
            patch.object(spoolman_api.requests, "get", side_effect=self.sm._get),
            patch.object(spoolman_api.requests, "patch", side_effect=self.sm._patch),
            patch.object(print_deduct.prusalink_api, "fetch_printer_credentials",
                         return_value={"ip_address": "1.2.3.4", "api_key": "k"}),
        ]
        _start(self._ctx)
        return self

    def __exit__(self, *exc):
        _stop(self._ctx)


def _gcode(lines=40):
    """T0 prints `lines` moves of 1 mm, one per line, so a byte fraction is about
    the same fraction of its filament."""
    return ("M83\nT0\n" + "G1 X1 E1\n" * lines
            + f"; filament used [mm] = {lines}\n; filament used [g] = 10\n")


def _download(text):
    def _fetch(ip, key, filename, fraction, extra_fractions=None):
        out = {"gcode": text, "fraction": fraction}
        if extra_fractions:
            out["fractions"] = list(extra_fractions)
        return out
    return patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=_fetch)


END = {"heads": [{"toolhead": "XL-1", "position": 0, "sid": 200, "sids": [200]},
                 {"toolhead": "XL-2", "position": 1, "sid": 300, "sids": [300]}],
       "source": "print_end", "at": "2026-11-20 02:00:00"}


# --------------------------------------------------------------------------- #
# 64.2 (10): how far the print got                                             #
# --------------------------------------------------------------------------- #

def test_reached_at_least_takes_the_park_and_the_last_swap():
    assert print_deduct._reached_at_least(0.40) == 0.40
    assert print_deduct._reached_at_least(0.40, None, 0.45) == 0.45
    assert print_deduct._reached_at_least(0.40, SWAP) == 0.45
    assert print_deduct._reached_at_least(0.60, SWAP, 0.45) == 0.60
    assert print_deduct._reached_at_least(None, "not a list", "x") == 0.0


def test_a_cancel_during_the_park_is_computed_at_the_parks_progress():
    """The last PRINTING sample said 40%; the ATTENTION park froze the job at 45%;
    the print was cancelled from the park. Red on 6ad359f: the review got 40%."""
    edge = MagicMock()
    with patch.object(print_monitor, "_dispatch_cancel_edge", edge):
        _tick("PRINTING", _job(0.40), on_head=100)
        _tick("ATTENTION", _job(0.45))
        _tick("STOPPED", None)
    edge.assert_called_once()
    assert edge.call_args.args[3] == pytest.approx(0.45)


def test_a_cancel_right_after_a_resume_that_recorded_a_swap_is_computed_at_the_swap():
    """#100 ran out at the 45% park and #200 was loaded; the resume's sample lagged
    (44%), and the print was cancelled before another. Red on 6ad359f: 44%, short of
    the swap FCC recorded at 45%, whose split was then refused."""
    edge = MagicMock()
    with patch.object(print_monitor, "_dispatch_cancel_edge", edge), \
            patch.object(state, "add_log_entry"):
        _tick("PRINTING", _job(0.40), on_head=100)
        _tick("ATTENTION", _job(0.45))
        _tick("PRINTING", _job(0.44), on_head=200)       # the resume records #100 -> #200
        _tick("STOPPED", None)
    edge.assert_called_once()
    assert [ev["progress"] for ev in edge.call_args.kwargs["swap_log"]] == [0.45]
    assert edge.call_args.args[3] == pytest.approx(0.45)


def test_a_plain_cancel_keeps_its_latched_progress():
    """Passes on 6ad359f by design: no park, no swap, the latch's 40% as before."""
    edge = MagicMock()
    with patch.object(print_monitor, "_dispatch_cancel_edge", edge):
        _tick("PRINTING", _job(0.40), on_head=100)
        _tick("STOPPED", None)
    assert edge.call_args.args[3] == pytest.approx(0.40)


def test_restart_recovery_of_a_cancel_from_the_park_uses_the_parks_progress():
    """FCC restarted during the park and the print was cancelled meanwhile. Red on
    6ad359f: the recovered review got the latch's 40%."""
    edge = MagicMock()
    entry = {"state": "ATTENTION", "job_id": JOB, "filename": "x.gcode", "progress": 0.40,
             "pause_progress": 0.45, "saw_attention": True}
    with patch.object(print_monitor, "_dispatch_cancel_edge", edge), \
            patch.object(print_monitor.prusalink_api, "get_printer_state",
                         return_value={"state": "STOPPED"}), \
            patch.object(print_monitor.prusalink_api, "get_printer_job", return_value=None):
        print_monitor._recover_one_print_latch(XL, entry, "http://fb")
    edge.assert_called_once()
    assert edge.call_args.args[3] == pytest.approx(0.45)


def test_the_review_splits_a_swap_recorded_past_the_cancels_latched_progress():
    """A queued fetch (or any caller) with the latch's lagging 40% and a swap recorded
    at 45%: the review computes at the swap and splits there. Red on 6ad359f: the swap's
    figure ran past the 40% partial, the split was refused, and XL-1 was a set with
    nothing pre-filled."""
    text = _gcode()
    with TwoHeads(), _download(text):
        print_deduct._create_pending_cancel_review(
            XL, "x.gcode", JOB, 0.40, fb_url="http://fb", end_heads=END,
            start_spools={"0": 100, "1": 300}, swap_log=SWAP)
    rec = cancel_review_store.get_pending(XL, str(JOB))
    assert rec["progress"] == pytest.approx(0.45), rec
    assert not (rec.get("unresolved_sets") or {}).get("0"), rec
    grams = {r["sid"]: r["grams"] for r in rec["spools"] if str(r.get("position")) == "0"}
    assert set(grams) == {100, 200} or set(grams) == {100}, rec
    assert grams[100] == pytest.approx(
        prusalink_api.measure_filament_usage(text, [0.45])["partials"][0][0], abs=0.01)


def test_a_job_that_replaces_a_parked_one_reviews_it_at_the_parks_progress():
    """The print was cancelled at the 45% park and the next one started before FCC
    saw it end. Red on 6ad359f: the outgoing job's review got the latch's 40%."""
    edge = MagicMock()
    with patch.object(print_monitor, "_dispatch_ambiguous_edge", edge), \
            patch.object(state, "add_log_entry"):
        _tick("PRINTING", _job(0.40), on_head=100)
        _tick("ATTENTION", _job(0.45))
        _tick("PRINTING", {"filename": "next.gcode", "job_id": JOB + 1, "progress": 0.05}, on_head=100)
    edge.assert_called_once()
    assert edge.call_args.args[2] == JOB
    assert edge.call_args.args[3] == pytest.approx(0.45)
