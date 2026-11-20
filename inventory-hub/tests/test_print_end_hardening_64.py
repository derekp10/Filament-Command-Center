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
import threading
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


# --------------------------------------------------------------------------- #
# 64.3 (8): the one-shot cancel deduct takes the print-end read                #
# --------------------------------------------------------------------------- #

def _one_shot(rig, text, downloads=None, reached=0.5, **kw):
    calls = downloads if downloads is not None else []

    def _fetch(ip, key, filename, fraction, extra_fractions=None):
        calls.append(filename)
        out = {"gcode": text, "fraction": fraction}
        if extra_fractions:
            out["fractions"] = list(extra_fractions)
        return out
    with patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=_fetch):
        return print_deduct.deduct_cancelled_print(
            XL, "x.gcode", JOB, reached, fb_url="http://fb", ip_address="1.2.3.4", api_key="k", **kw)


def test_the_one_shot_charges_the_print_end_spool_never_one_loaded_after_it():
    """#200 was on XL-1 when the print ended; #100 was loaded during the download.
    Red on e4c0ae0 (no end_heads: the read after the download charged #100, the
    job-1141 bug)."""
    text = _gcode()
    with TwoHeads() as rig:
        rig.at["XL-1"] = [100]
        out = _one_shot(rig, text, end_heads=END)
    assert out["status"] == "deducted", out
    want = prusalink_api.measure_filament_usage(text, [0.5])["partials"][0][0]
    assert rig.sm.used(200) == pytest.approx(10.0 + want, abs=0.01)
    assert rig.sm.used(100) == pytest.approx(100.0)
    assert print_deduct_ledger.was_deducted(XL, str(JOB))


def test_the_one_shot_sends_a_head_it_cant_vouch_for_to_the_review_from_one_download():
    """A swap recorded on XL-1 during the print: a one-shot can't ask, so the whole
    print goes to the review, split at the swap from the same download, and nothing
    is charged. Red on e4c0ae0."""
    text = _gcode()
    downloads = []
    with TwoHeads() as rig:
        out = _one_shot(rig, text, downloads, reached=0.40, end_heads=END,
                        start_spools={"0": 100, "1": 300}, swap_log=SWAP)
    assert str(out["status"]).startswith("pending"), out
    assert downloads == ["x.gcode"], "the review downloaded the file again"
    rec = cancel_review_store.get_pending(XL, str(JOB))
    assert rec["progress"] == pytest.approx(0.45), rec      # at least its last swap (64.2 (10))
    assert {r["sid"] for r in rec["spools"] if str(r.get("position")) == "0"} == {100, 200}, rec
    assert rig.sm.patches == []
    assert not print_deduct_ledger.was_deducted(XL, str(JOB))


def test_the_one_shot_sends_a_head_with_two_spools_at_the_end_to_the_review():
    """Red on e4c0ae0: both spools on the head were charged its whole grams' share."""
    two = {"heads": [dict(END["heads"][0], sid=None, sids=[200, 300])], "source": "print_end",
           "at": END["at"]}
    with TwoHeads() as rig:
        out = _one_shot(rig, _gcode(), end_heads=two)
    assert str(out["status"]).startswith("pending"), out
    assert rig.sm.patches == []


def test_the_one_shot_with_no_print_end_read_reads_the_heads_as_before():
    """Passes on e4c0ae0 by design: no usable read, the heads are read after the
    download, as the function always did."""
    with TwoHeads() as rig:
        out = _one_shot(rig, _gcode())
    assert out["status"] == "deducted", out
    assert rig.sm.used(200) > 10.0


def test_the_one_shot_whose_print_end_spool_is_gone_asks_with_the_print_end_heads():
    """The print-end read names #999, which Spoolman no longer has: nothing is
    charged, and the card says what the read saw. Red on e4c0ae0."""
    gone = {"heads": [dict(END["heads"][0], sid=999, sids=[999])], "source": "print_end",
            "at": END["at"]}
    with TwoHeads() as rig:
        out = _one_shot(rig, _gcode(), end_heads=gone)
    assert str(out["status"]).startswith("pending"), out
    rec = cancel_review_store.get_pending(XL, str(JOB))
    assert rec.get("heads_source") == "print_end", rec
    assert rig.sm.patches == []


# --------------------------------------------------------------------------- #
# 64.3 (1): one spool-list read per step                                       #
# --------------------------------------------------------------------------- #

from spoolman_extra_fake import SpoolmanHTTPFake  # noqa: E402

EIGHT = [(f"RCOI-{i + 1}", i) for i in range(8)]
INDX = "INDX TEST"


class EightHeads:
    """An INDX-like printer over Spoolman's HTTP: a spool on each of eight heads
    (#101-#108, its used weight 10 g times its head number), and #200 on a shelf."""

    def __init__(self):
        self.sm = SpoolmanHTTPFake()
        for loc, pos in EIGHT:
            self.sm.add("spool", 101 + pos, location=loc, used_weight=10.0 * (pos + 1),
                        initial_weight=1000.0, archived=False, filament={"weight": 1000.0})
        self.sm.add("spool", 200, location="SHELF-1", used_weight=5.0, initial_weight=1000.0,
                    archived=False, filament={"weight": 1000.0})

    def list_gets(self):
        return [p for p in self.sm.gets if p.split("?")[0].rstrip("/") == "/api/v1/spool"]

    def __enter__(self):
        active = [(loc, {"position": pos, "printer_name": INDX}) for loc, pos in EIGHT]
        self._ctx = [
            patch.object(print_deduct.locations_db, "get_active_printer_map",
                         return_value={loc: {"printer_name": INDX, "position": pos} for loc, pos in EIGHT}),
            patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=active),
            patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
            patch.object(spoolman_api, "format_spool_display",
                         return_value={"text": "#s", "color": "ff0000", "slot": "", "details": {}}),
            patch.object(spoolman_api.requests, "get", side_effect=self.sm.get),
            patch.object(spoolman_api.requests, "patch", side_effect=self.sm.patch),
        ]
        _start(self._ctx)
        return self

    def __exit__(self, *exc):
        _stop(self._ctx)


def test_the_heads_read_is_one_list_read_and_keeps_each_spools_used_weight():
    """Red on e5fcac2: eight whole-list GETs, one per head, and no used weights."""
    with EightHeads() as rig:
        heads = print_deduct._capture_print_heads(INDX, "http://fb")
    assert len(rig.list_gets()) == 1, rig.sm.gets
    assert [(h["toolhead"], h["sid"]) for h in heads] == [(loc, 101 + pos) for loc, pos in EIGHT]
    assert heads[2]["used"] == {"103": 30.0}, heads[2]


def test_a_spool_list_fcc_couldnt_read_is_no_read_never_every_head_empty(caplog):
    """Red on e5fcac2: every head came back empty (the blip rule caught only an
    all-empty answer, and a read that failed part-way named empty heads)."""
    with EightHeads() as rig:
        rig.sm.list_reads_fail = True
        with caplog.at_level("WARNING"):
            heads = print_deduct._capture_print_heads(INDX, "http://fb")
    assert heads is None
    assert len(rig.list_gets()) == 1
    assert any("couldn't read the spool list for its heads" in r.getMessage() for r in caplog.records)


def test_the_print_end_read_carries_the_used_weights_onto_the_print():
    """Red on e5fcac2. The read the edge keeps (_capture_end_heads) carries each
    spool's used weight, and _usable_heads keeps it."""
    with EightHeads():
        end = print_monitor._capture_end_heads(INDX, 1141, "http://fb")
    heads, source, _at = print_deduct._usable_heads(end)
    assert source == "print_end"
    assert heads[7]["used"] == {"108": 80.0}, heads[7]


def test_the_start_snapshot_and_an_apply_read_the_list_once_each():
    """Red on e5fcac2: one whole-list GET per head for each."""
    with EightHeads() as rig:
        snap = print_deduct._snapshot_active_spools(INDX, "http://fb")
        assert len(rig.list_gets()) == 1
        assert snap == {pos: 101 + pos for _loc, pos in EIGHT}, snap
        before = len(rig.list_gets())
        updated, details, _known = print_deduct._apply_usage_to_printer(
            INDX, {0: 1.0, 3: 2.0, 7: 3.0}, "http://fb", strategy_label="Complete")
    assert updated == 3, details
    assert len(rig.list_gets()) - before == 1, rig.sm.gets


def test_blocks_share_inside_one_thread_and_never_across_threads():
    """A block inside another shares its read; another thread's block reads its
    own; outside any block every location read is its own, as before."""
    with EightHeads() as rig:
        with spoolman_api.one_spool_list_read() as outer:
            spoolman_api.get_spools_at_location("RCOI-1")
            with spoolman_api.one_spool_list_read() as inner:
                spoolman_api.get_spools_at_location("RCOI-2")
            assert inner is outer
            seen = []

            def _other():
                with spoolman_api.one_spool_list_read():
                    seen.append(spoolman_api.get_spools_at_location("RCOI-3"))
            t = threading.Thread(target=_other)
            t.start()
            t.join(5)
        assert len(rig.list_gets()) == 2, rig.sm.gets     # this thread's one, the other's one
        assert seen == [[103]]
        spoolman_api.get_spools_at_location("RCOI-1")
        spoolman_api.get_spools_at_location("RCOI-2")
    assert len(rig.list_gets()) == 4


@pytest.mark.parametrize("reader", ["heads_snapshot", "resolve_usage", "changed_since_end"])
def test_every_other_heads_reader_reads_the_list_once(reader):
    """Red on e5fcac2: one whole-list GET per head."""
    with EightHeads() as rig:
        if reader == "heads_snapshot":
            out = print_deduct._heads_snapshot(INDX, "http://fb")
            assert [h["sid"] for h in out] == [101 + pos for _loc, pos in EIGHT], out
        elif reader == "resolve_usage":
            rows = print_deduct._resolve_usage_to_spools(INDX, {0: 1.0, 5: 2.0, 7: 3.0}, "http://fb")
            assert sorted(r["sid"] for r in rows) == [101, 106, 108], rows
        else:
            heads = [{"toolhead": loc, "position": pos, "sid": 101 + pos, "sids": [101 + pos]}
                     for loc, pos in EIGHT]
            assert print_deduct._changed_since_end(INDX, "http://fb", heads) == []
    assert len(rig.list_gets()) == 1, rig.sm.gets
