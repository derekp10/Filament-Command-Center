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


# --------------------------------------------------------------------------- #
# Decision 1: a spool weighed between a print's end and its charge             #
# --------------------------------------------------------------------------- #

import app as app_module  # noqa: E402
import weigh_stamps  # noqa: E402


@pytest.fixture
def stamps(tmp_path, monkeypatch):
    monkeypatch.setattr(weigh_stamps, "_STORE_PATH", str(tmp_path / "weigh_stamps.json"))
    return weigh_stamps


class TwoHeadsOverHTTP:
    """The XL's two heads over Spoolman's HTTP (list and per-spool reads, PATCHes):
    #200 on XL-1 (100 g used), #300 on XL-2 (50 g used)."""

    def __init__(self):
        self.sm = SpoolmanHTTPFake()
        for sid, loc, used in ((200, "XL-1", 100.0), (300, "XL-2", 50.0)):
            self.sm.add("spool", sid, location=loc, used_weight=used, initial_weight=1000.0,
                        archived=False, filament={"weight": 1000.0})

    def used(self, sid):
        return self.sm.records["spool"][sid]["used_weight"]

    def __enter__(self):
        active = [("XL-1", {"position": 0, "printer_name": XL}), ("XL-2", {"position": 1, "printer_name": XL})]
        self._ctx = [
            patch.object(print_deduct.locations_db, "get_active_printer_map",
                         return_value={"XL-1": {"printer_name": XL, "position": 0},
                                       "XL-2": {"printer_name": XL, "position": 1}}),
            patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=active),
            patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
            patch.object(spoolman_api, "format_spool_display",
                         return_value={"text": "#s", "color": "ff0000", "slot": "", "details": {}}),
            patch.object(spoolman_api.requests, "get", side_effect=self.sm.get),
            patch.object(spoolman_api.requests, "patch", side_effect=self.sm.patch),
            patch.object(print_deduct.prusalink_api, "fetch_printer_credentials",
                         return_value={"ip_address": "1.2.3.4", "api_key": "k"}),
        ]
        _start(self._ctx)
        return self

    def __exit__(self, *exc):
        _stop(self._ctx)


def _two_tool_gcode():
    return ("M83\nT0\n" + "G1 X1 E1\n" * 10 + "T1\n" + "G1 X1 E1\n" * 10
            + "; filament used [mm] = 10, 10\n; filament used [g] = 12.4, 3.6\n")


def _end_read(rig):
    with rig:
        end = print_monitor._capture_end_heads(XL, JOB, "http://fb")
    assert end["heads"][0]["used"] == {"200": 100.0}, end
    return end


def _complete(rig, end):
    with rig, _download(_two_tool_gcode()):
        return print_deduct.deduct_completed_print(XL, "x.gcode", JOB, fb_url="http://fb", end_heads=end)


@pytest.fixture
def warn_lines(monkeypatch):
    lines = []
    monkeypatch.setattr(state, "add_log_entry",
                        lambda msg, level="INFO", *a, **k: lines.append((msg, level)))
    return lines


def test_a_spool_weighed_on_fcc_after_the_print_ended_is_held_at_0g(stamps, warn_lines):
    """Red on 7edb245 (charged on top). The print ends; #200 is weighed on the
    Quick-Weigh; the charge then holds its 12.4 g on the card, filled in with 0 g,
    and charges XL-2's #300 as usual."""
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    rig.sm.records["spool"][200]["used_weight"] = 130.0            # the scale's reading
    stamps.note(200, "the Quick-Weigh", at=end["at_s"] + 60)
    out = _complete(rig, end)
    assert out["status"] == "deducted", out
    assert rig.used(200) == 130.0, "the weighed spool was charged on top"
    assert rig.used(300) == pytest.approx(53.6)
    card = cancel_review_store.get_pending(XL, f"{JOB}#shortfall")
    cause = card["shortfall_causes"]["0"]
    assert cause["why"] == "weighed" and cause["known_order"] is True and cause["sid"] == 200, card
    assert card["unresolved_usage"] == {"0": 12.4} and card["shortfall_prefill"] == {"0": 0.0}, card
    assert "was weighed on the Quick-Weigh at" in cause["words"], cause
    said = [m for m, lvl in warn_lines if lvl == "WARNING" and "#200 on XL-1" in m]
    assert len(said) == 1 and "put 0 g on its \U0001f6d1 Review card" in said[0], warn_lines
    assert print_deduct_ledger.was_deducted(XL, str(JOB))


def test_a_change_fcc_cant_place_in_time_is_held_with_the_prints_grams(stamps, warn_lines):
    """Red on 7edb245. #200's weight changed after the end with no FCC weighing after
    it (an edit in Spoolman's own page; FCC's last weighing was before the print):
    held, filled in with the print's 12.4 g, said loudly."""
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    stamps.note(200, "the weigh-out list", at=end["at_s"] - 3600)
    rig.sm.records["spool"][200]["used_weight"] = 104.0
    _complete(rig, end)
    assert rig.used(200) == 104.0
    card = cancel_review_store.get_pending(XL, f"{JOB}#shortfall")
    assert card["shortfall_causes"]["0"]["known_order"] is False, card
    assert card["shortfall_prefill"] == {"0": 12.4}, card
    said = [m for m, lvl in warn_lines if lvl == "WARNING" and "#200 on XL-1" in m]
    assert len(said) == 1 and "can't tell" in said[0] and "may be counted twice" in said[0], warn_lines


def test_a_print_whose_spools_didnt_change_is_charged_as_before(stamps, warn_lines):
    """Passes on 7edb245 by design."""
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    out = _complete(rig, end)
    assert out["status"] == "deducted"
    assert rig.used(200) == pytest.approx(112.4) and rig.used(300) == pytest.approx(53.6)
    assert cancel_review_store.get_pending(XL, f"{JOB}#shortfall") is None


def test_an_end_read_from_before_this_release_checks_nothing(stamps):
    """A queued record's end read with no `used` (written before the release) is
    charged as before. Passes on 7edb245 by design."""
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    for h in end["heads"]:
        h.pop("used", None)
    rig.sm.records["spool"][200]["used_weight"] = 130.0
    _complete(rig, end)
    assert rig.used(200) == pytest.approx(142.4)


def _held_card(rig, stamps):
    end = _end_read(rig)
    rig.sm.records["spool"][200]["used_weight"] = 130.0
    stamps.note(200, "the Quick-Weigh", at=end["at_s"] + 60)
    _complete(rig, end)
    return cancel_review_store.get_pending(XL, f"{JOB}#shortfall")


def test_a_card_of_held_lines_left_at_0g_settles_with_nothing_charged(stamps, warn_lines):
    """Red on 7edb245. Its Apply sends `settle_held`: the card closes as a Discard
    would, nothing charged, one line saying why."""
    rig = TwoHeadsOverHTTP()
    card = _held_card(rig, stamps)
    with rig:
        r = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": XL, "job_id": card["job_id"], "rev": card["rev"],
            "charges": [], "settle_held": True})
    body = r.get_json()
    assert body["status"] == "confirmed" and body["settled_held"] is True, body
    assert rig.used(200) == 130.0
    assert cancel_review_store.get_pending(XL, card["job_id"]) is None
    assert any("left 12.40g" in m and "uncharged on #200" in m for m, lvl in warn_lines), warn_lines


def test_settle_held_on_a_card_with_another_line_is_refused(stamps):
    """Red on 7edb245. A line that isn't a weighed spool's still needs its pick."""
    rig = TwoHeadsOverHTTP()
    card = _held_card(rig, stamps)
    rec = cancel_review_store.pop_pending(XL, card["job_id"])
    rec["unresolved_usage"]["1"] = 3.0
    rec["shortfall_causes"]["1"] = {"why": "no_spool", "toolhead": "XL-2"}
    cancel_review_store.add_pending(rec)
    with rig:
        body = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": XL, "job_id": card["job_id"], "rev": card["rev"],
            "charges": [], "settle_held": True}).get_json()
    assert body["status"] == "error" and "Pick the spool" in body["msg"], body
    assert cancel_review_store.get_pending(XL, card["job_id"]) is not None


def test_a_held_line_can_still_be_charged_by_its_pick(stamps):
    """The weighing was a mistake: the person types the grams on the pre-picked
    spool, an ordinary Apply."""
    rig = TwoHeadsOverHTTP()
    card = _held_card(rig, stamps)
    with rig:
        body = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": XL, "job_id": card["job_id"], "rev": card["rev"],
            "charges": [{"position": 0, "sid": 200, "grams": 12.4}]}).get_json()
    assert body["status"] == "confirmed", body
    assert rig.used(200) == pytest.approx(142.4)


def test_a_cancels_card_row_whose_spool_was_weighed_after_the_end_says_so(stamps):
    """Red on 7edb245. The cancel's review rows come from the print-end read; a row
    whose spool was weighed after the end is filled in with 0 g and marked."""
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    rig.sm.records["spool"][200]["used_weight"] = 120.0
    stamps.note(200, "the weigh-out list", at=end["at_s"] + 30)
    with rig, _download(_two_tool_gcode()):
        print_deduct._create_pending_cancel_review(XL, "x.gcode", JOB, 0.5, fb_url="http://fb",
                                                   end_heads=end)
    rec = cancel_review_store.get_pending(XL, str(JOB))
    row = next(r for r in rec["spools"] if r["sid"] == 200)
    assert row["prefill"] == 0.0 and row["weighed"]["known_order"] is True, row
    assert "weigh-out list" in row["weighed"]["words"], row
    other = next(r for r in rec["spools"] if r["sid"] == 300)
    assert "weighed" not in other and "prefill" not in other, other


def test_the_weigh_screens_stamp_their_weighings(stamps):
    """Red on 7edb245. /api/spool/update stamps a weight save with its screen."""
    rig = TwoHeadsOverHTTP()
    with rig:
        app_module.app.test_client().post("/api/spool/update", json={
            "id": 200, "updates": {"used_weight": 130.0},
            "based_on": {"mode": "set_used", "screen": "quick"}})
        app_module.app.test_client().post("/api/spool/update", json={
            "id": 300, "updates": {"used_weight": 60.0}})
    assert stamps.last(200)["how"] == "the Quick-Weigh"
    assert stamps.last(300)["how"] == "a weight save"


def test_a_stamp_store_fcc_cant_read_is_read_as_no_stamps(stamps):
    with open(stamps._STORE_PATH, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    assert stamps.last(200) is None and stamps.weighed_after(200, 0) is None
    stamps.note(200, "the Quick-Weigh", at=1000.0)
    assert stamps.weighed_after(200, 999.0)["how"] == "the Quick-Weigh"
    assert stamps.weighed_after(200, 1000.0) is None


def test_a_held_line_opens_the_card_under_the_uncharged_grams_threshold(stamps, monkeypatch):
    """A held head is a question, not a rounding: its card opens whatever
    shortfall_review_min_g says (here 50 g, over the print's 12.4 g). Red on 7edb245."""
    monkeypatch.setattr(print_deduct, "_shortfall_review_min_g", lambda: 50.0)
    rig = TwoHeadsOverHTTP()
    card = _held_card(rig, stamps)
    assert card is not None and card["shortfall_causes"]["0"]["why"] == "weighed", card


# --------------------------------------------------------------------------- #
# 64.2 (1): a weigh save never lands between a charge's read and its write     #
# --------------------------------------------------------------------------- #

import routes_inventory  # noqa: E402


def _charge_and_weigh(monkeypatch, save_body, route="/api/spool/update"):
    """A print's charge of #200 is held right after its read of the spool; a save of
    #200 starts meanwhile. Returns (the PATCHed used weights in order, whether the
    save wrote while the charge was held, the spool's final used weight)."""
    monkeypatch.setattr(routes_inventory, "_log_manual_weight_change", lambda *a, **k: None)
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    gate, in_read = threading.Event(), threading.Event()
    held = {"first": True}
    real_get = rig.sm.get

    def _get(url, *a, **k):
        answer = real_get(url, *a, **k)
        if str(url).split("?")[0].rstrip("/").endswith("/api/v1/spool/200") and held["first"]:
            held["first"] = False
            in_read.set()            # the charge has read #200, under its lock
            gate.wait(5)
        return answer
    heads = [{"toolhead": "XL-1", "position": 0, "sid": 200, "sids": [200]}]
    with rig, patch.object(spoolman_api.requests, "get", side_effect=_get):
        charge = threading.Thread(target=print_deduct._apply_usage_to_printer,
                                  args=(XL, {0: 12.4}, "http://fb"), kwargs={"heads": heads})
        charge.start()
        assert in_read.wait(5)
        client = app_module.app.test_client()
        save = threading.Thread(target=lambda: client.post(route, json=save_body))
        save.start()
        save.join(0.5)                                   # the save, if it doesn't wait, lands now
        wrote_meanwhile = [p for p in rig.sm.patches if p[0] == "spool"]
        gate.set()
        charge.join(5)
        save.join(5)
    used = [p[2].get("used_weight") for p in rig.sm.patches if p[0] == "spool" and "used_weight" in p[2]]
    return used, wrote_meanwhile, rig.used(200)


def test_a_weigh_save_waits_for_a_charge_of_the_same_spool(monkeypatch, stamps):
    """Red on 7edb245: the save wrote the scale's 130 g while the charge was between
    its read and its write, and the charge then wrote 100 + 12.4 over it: the
    reading was lost."""
    used, meanwhile, final = _charge_and_weigh(
        monkeypatch, {"id": 200, "updates": {"used_weight": 130.0}})
    assert meanwhile == [], "the save wrote while the charge held the spool"
    assert used == [pytest.approx(112.4), 130.0], used
    assert final == 130.0


def test_prusaments_apply_weights_waits_for_a_charge_too(monkeypatch, stamps):
    """Red on 7edb245. Its total is the charge's clamp."""
    used, meanwhile, final = _charge_and_weigh(
        monkeypatch, {"spool_id": 200, "updates": {"initial_weight": 1100.0}},
        route="/api/spool/prusament_apply_weights")
    assert meanwhile == [], "the apply-weights wrote while the charge held the spool"
    assert final == pytest.approx(112.4)


def test_the_deducts_lock_is_the_one_the_saves_take():
    assert print_deduct._spool_lock(200) is spoolman_api.spool_lock(200)
    assert spoolman_api.spool_lock(200) is not spoolman_api.spool_lock(201)


# --------------------------------------------------------------------------- #
# 64.6: an MMU printer (Derek, 2026-11-20: each slot its own number)           #
# --------------------------------------------------------------------------- #

MMU = "MMU TEST"


class MmuPrinter:
    """A made-up printer with an MMU of five slots (MMU-1..MMU-5, Type "MMU Slot"),
    each holding spool #401..#405 unless `loaded` says otherwise. `shared` puts every
    slot on toolhead number 1 (position 0), the setup FCC can't tell apart; else
    each slot has its own number (position = slot - 1), as Derek's model says."""

    def __init__(self, shared=False, loaded=None):
        self.slots = [f"MMU-{i + 1}" for i in range(5)]
        self.pos = {slot: (0 if shared else i) for i, slot in enumerate(self.slots)}
        loaded = loaded if loaded is not None else {slot: 401 + i for i, slot in enumerate(self.slots)}
        self.sm = SpoolmanHTTPFake()
        for i, slot in enumerate(self.slots):
            sid = loaded.get(slot)
            if sid is not None:
                self.sm.add("spool", sid, location=slot, used_weight=10.0, initial_weight=1000.0,
                            archived=False, filament={"weight": 1000.0})

    def used(self, sid):
        return self.sm.records["spool"][sid]["used_weight"]

    def __enter__(self):
        active = [(slot, {"position": self.pos[slot], "printer_name": MMU}) for slot in self.slots]
        rows = [{"LocationID": slot, "Type": "MMU Slot"} for slot in self.slots]
        self._ctx = [
            patch.object(print_deduct.locations_db, "get_active_printer_map",
                         return_value={slot: {"printer_name": MMU, "position": self.pos[slot]}
                                       for slot in self.slots}),
            patch.object(print_deduct.locations_db, "load_locations_list", return_value=rows),
            patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=active),
            patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
            patch.object(spoolman_api, "format_spool_display",
                         return_value={"text": "#s", "color": "ff0000", "slot": "", "details": {}}),
            patch.object(spoolman_api.requests, "get", side_effect=self.sm.get),
            patch.object(spoolman_api.requests, "patch", side_effect=self.sm.patch),
            patch.object(print_deduct.prusalink_api, "fetch_printer_credentials",
                         return_value={"ip_address": "1.2.3.4", "api_key": "k"}),
        ]
        _start(self._ctx)
        return self

    def __exit__(self, *exc):
        _stop(self._ctx)


def _mmu_gcode(grams):
    """A plain-text multi-material MMU print: each tool in `grams` prints in turn;
    the footer lists every tool up to the last, 0 g for one that printed none."""
    tools = max(grams) + 1
    body = ["M83"]
    for t in sorted(grams):
        body += [f"T{t}"] + ["G1 X1 E1"] * 10
    mm = ", ".join("10" if t in grams else "0" for t in range(tools))
    g = ", ".join(str(grams.get(t, 0)) for t in range(tools))
    return "\n".join(body) + f"\n; filament used [mm] = {mm}\n; filament used [g] = {g}\n"


def _mmu_complete(rig, grams, end=True):
    with rig:
        end_heads = print_monitor._capture_end_heads(MMU, JOB, "http://fb") if end else None
    with rig, _download(_mmu_gcode(grams)):
        return print_deduct.deduct_completed_print(MMU, "m.gcode", JOB, fb_url="http://fb",
                                                   **({"end_heads": end_heads} if end_heads else {}))


def test_an_mmu_whose_slots_have_their_own_numbers_is_charged_slot_by_slot():
    """Derek's model: a multi-color print charges each slot's spool its own tool's
    grams, as a toolchanger's heads are charged. Passes on 6b76460 by design (FCC
    already charges per toolhead number); pinned for MMU setups."""
    rig = MmuPrinter()
    out = _mmu_complete(rig, {0: 10.0, 2: 5.0})
    assert out["status"] == "deducted", out
    assert rig.used(401) == pytest.approx(20.0) and rig.used(403) == pytest.approx(15.0)
    assert rig.used(402) == 10.0 and rig.used(404) == 10.0


def test_a_one_color_print_on_slot_3_of_an_mmu_with_own_numbers_charges_slot_3():
    """An MMU-profile file printing from slot 3 lists only T2. Passes on 6b76460 by
    design (several numbers: no fold onto slot 1)."""
    rig = MmuPrinter()
    _mmu_complete(rig, {2: 5.0})
    assert rig.used(403) == pytest.approx(15.0) and rig.used(401) == 10.0


def test_mmu_slots_sharing_one_number_each_holding_a_spool_are_asked_about(warn_lines):
    """Red on 6b76460: the print-end read stopped at the first slot holding a spool,
    and slot 1's #401 was charged the print that slot 3 made."""
    rig = MmuPrinter(shared=True)
    out = _mmu_complete(rig, {2: 5.0})
    assert [rig.used(s) for s in (401, 402, 403, 404, 405)] == [10.0] * 5, "a slot's spool was charged"
    # Its only head held: the card to pick on, as for any head FCC can't vouch for.
    assert out["status"] == "pending_unresolved" and out["kind"] == "no_spool", out
    card = cancel_review_store.get_pending(MMU, str(JOB))
    note = card["unresolved_notes"]["0"]
    assert note.startswith("MMU slots MMU-1, MMU-2, MMU-3, MMU-4 and MMU-5 share one Position"), note
    assert "(#401, #402, #403, #404 and #405)" in note and "in Settings" in note, note
    offered = {s for h in card["heads_at_end"] for s in (h.get("sids") or [h.get("sid")])}
    assert {401, 402, 403, 404, 405} <= offered, card   # the card's picker offers every slot's spool


def test_mmu_slots_sharing_one_number_with_no_print_end_read_charge_none(warn_lines):
    """Red on 6b76460: with no print-end read the apply charged the first slot's
    spool. It charges none now, and says how to set the MMU up."""
    rig = MmuPrinter(shared=True)
    _mmu_complete(rig, {2: 5.0}, end=False)
    assert [rig.used(s) for s in (401, 402, 403)] == [10.0] * 3
    # Group 64 review (O2): in the editor's own terms, its 0-based Position.
    said = [m for m, lvl in warn_lines if "share Position 0 (T0)" in m]
    assert len(said) == 1 and "own Position in Settings (slot 1 = Position 0)" in said[0], warn_lines


def test_mmu_slots_sharing_one_number_with_one_spool_loaded_charge_it():
    """Only one slot holds a spool: there's nothing to tell apart. Passes on
    6b76460 by design."""
    rig = MmuPrinter(shared=True, loaded={"MMU-3": 403})
    _mmu_complete(rig, {2: 5.0})
    assert rig.used(403) == pytest.approx(15.0)


def test_a_cancel_on_mmu_slots_sharing_one_number_says_why_it_asks():
    """Red on 6b76460 (its card blamed one slot for holding two spools)."""
    rig = MmuPrinter(shared=True, loaded={"MMU-1": 401, "MMU-2": 402})
    with rig:
        end_heads = print_monitor._capture_end_heads(MMU, JOB, "http://fb")
    with rig, _download(_mmu_gcode({1: 5.0})):
        print_deduct._create_pending_cancel_review(MMU, "m.gcode", JOB, 0.5, fb_url="http://fb",
                                                   end_heads=end_heads)
    rec = cancel_review_store.get_pending(MMU, str(JOB))
    note = (rec.get("unresolved_notes") or {}).get("0", "")
    assert "MMU slots MMU-1 and MMU-2 share one Position" in note, rec
    assert "own Position in Settings (slot 1 = Position 0, slot 2 = Position 1, …)" in note, rec
    assert rig.used(401) == 10.0 and rig.used(402) == 10.0


# --------------------------------------------------------------------------- #
# 64.2 (7) / (8): the uncharged-grams card's spool entries                     #
# --------------------------------------------------------------------------- #

def _card_heads_of(**kw):
    kw.setdefault("filename", "f.gcode")
    kw.setdefault("scale", 1.0)
    rec = print_deduct._stash_shortfall_review(XL, f"J-{len(kw)}", **kw)
    return rec["heads_at_end"]


def test_an_older_cards_run_out_spool_never_takes_the_heads_own_entry():
    """64.2 (7). Red on 9fc269b: #200 (charged, then archived off the head) wrote
    over #100's entry, so the spool on the head went from the picker."""
    heads = _card_heads_of(uncharged={"0": 2.0},
                           heads=[{"toolhead": "XL-1", "position": 0, "sid": 100}],
                           details=[{"sid": 200, "position": 0, "toolhead": "XL-1", "remaining": 0.0,
                                     "grams": 3.0}])
    assert {"toolhead": "XL-1", "position": 0, "sid": 100} in heads, heads
    assert {"toolhead": "XL-1", "position": 0, "sid": 200, "archived": True, "when": "end"} in heads, heads


def test_a_spool_picked_on_a_card_that_ran_short_is_offered_as_picked():
    """64.2 (7), the card Apply's path. Red on 9fc269b: the spool picked by its # was
    left off the next card's picker (the print-end entry returned early)."""
    heads = _card_heads_of(uncharged={"0": 2.0}, picked=True,
                           heads=[{"toolhead": "XL-1", "position": 0, "sid": 100, "sids": [100]}],
                           details=[{"sid": 300, "position": 0, "toolhead": "XL-1", "remaining": 0.0,
                                     "grams": 0.0}])
    own = next(h for h in heads if h.get("sid") == 100)
    assert own.get("archived") is not True and "when" not in own, heads
    assert {"toolhead": "XL-1", "position": 0, "sid": 300, "archived": True, "when": "picked"} in heads, heads


def test_a_run_out_spool_among_a_heads_several_gets_its_own_mark():
    """64.2 (8). Red on 9fc269b: the entry naming #100 and #101 got no mark, so #100
    was offered as if it had filament left."""
    heads = _card_heads_of(uncharged={"0": 2.0},
                           heads=[{"toolhead": "XL-1", "position": 0, "sid": None, "sids": [100, 101]}],
                           details=[{"sid": 100, "position": 0, "toolhead": "XL-1", "remaining": 0.0,
                                     "grams": 3.0}])
    entry = next(h for h in heads if h.get("sids") == [100, 101])
    assert entry.get("archived_sids") == [100] and not entry.get("archived"), heads
    assert len([h for h in heads if h.get("sid") == 100]) == 0, heads


# --------------------------------------------------------------------------- #
# 64.2 (2): the server checks a set's grams itself                             #
# --------------------------------------------------------------------------- #

def _set_card():
    """A cancel's card: XL-2's #300 a row (3.6 g); XL-1's 12.4 g a set of #200 and
    #100 (its spool changed during the print), nothing pre-filled."""
    words = {"end": "when the print ended", "start": "when the print started", "during": "during the print"}
    rec = {"printer_name": XL, "job_id": str(JOB), "filename": "x.gcode", "progress": 0.5,
           "total_grams": 16.0, "ambiguous": False, "kind": "partial", "created": "2026-11-20 00:00:00",
           "heads_source": "print_end", "heads_words": words,
           "spools": [{"sid": 300, "toolhead": "XL-2", "position": 1, "grams": 3.6, "display": "#300",
                       "color": "ff0000", "ambiguous": False}],
           "unresolved_usage": {"0": 12.4},
           "unresolved_sets": {"0": [{"sid": 100, "when": "start"}, {"sid": 200, "when": "end"}]},
           "heads_at_end": [{"toolhead": "XL-1", "position": 0, "sid": 200, "sids": [200]},
                            {"toolhead": "XL-2", "position": 1, "sid": 300, "sids": [300]}]}
    cancel_review_store.add_pending(rec)
    return rec


def _post_set(rig, grams, **extra):
    with rig:
        return app_module.app.test_client().post("/api/cancel_deduct/confirm", json=dict({
            "printer_name": XL, "job_id": str(JOB),
            "charges": [{"row": 300, "sid": 300, "grams": 3.6},
                        {"position": 0, "sid": 200, "grams": grams}]}, **extra)).get_json()


def test_a_set_short_from_a_page_with_no_set_check_is_told_to_reload():
    """Red on 0576b5a: the server took it (only the page asked)."""
    rig = TwoHeadsOverHTTP()
    _set_card()
    body = _post_set(rig, 5.0)
    assert body["status"] == "error" and body.get("stale_page") is True and "reload" in body["msg"], body
    assert cancel_review_store.get_pending(XL, str(JOB)) is not None, "the card was lost"
    assert rig.used(200) == 100.0 and rig.used(300) == 50.0


def test_a_set_short_that_the_person_saw_goes_ahead():
    """Passes on 0576b5a by design (the server took it then too): today's page's
    second press says what the person saw."""
    rig = TwoHeadsOverHTTP()
    _set_card()
    body = _post_set(rig, 5.0, set_ack={"0": 5.0})
    assert body["status"] == "confirmed", body
    assert rig.used(200) == pytest.approx(105.0) and rig.used(300) == pytest.approx(53.6)


def test_a_set_whose_grams_changed_after_the_question_is_asked_again():
    """Red on 0576b5a. The person saw 5 g placed, then the post placed 9 g (another
    tab, or a box changed after the question)."""
    rig = TwoHeadsOverHTTP()
    _set_card()
    body = _post_set(rig, 9.0, set_ack={"0": 5.0})
    assert body["status"] == "error" and "changed since FCC asked" in body["msg"], body
    assert "XL-1" in body["msg"] and not body.get("stale_page"), body
    assert cancel_review_store.get_pending(XL, str(JOB)) is not None
    assert rig.used(200) == 100.0


def test_a_set_that_adds_up_needs_no_question():
    """Passes on 0576b5a by design."""
    rig = TwoHeadsOverHTTP()
    _set_card()
    body = _post_set(rig, 12.4)
    assert body["status"] == "confirmed", body
    assert rig.used(200) == pytest.approx(112.4)


def test_a_plain_row_still_takes_more_than_its_grams():
    """A row isn't a set: an over-allocation goes ahead, as before. Passes on
    0576b5a by design."""
    rig = TwoHeadsOverHTTP()
    rec = _set_card()
    rec = cancel_review_store.pop_pending(XL, str(JOB))
    rec.pop("unresolved_sets")
    rec["unresolved_usage"] = {}
    cancel_review_store.add_pending(rec)
    with rig:
        body = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": XL, "job_id": str(JOB),
            "charges": [{"row": 300, "sid": 300, "grams": 9.0}]}).get_json()
    assert body["status"] == "confirmed", body
    assert rig.used(300) == pytest.approx(59.0)


# --------------------------------------------------------------------------- #
# Group 64 review, the server half (S1, S2, S4, S5, Y1, Y2 / O3 / O4)          #
# --------------------------------------------------------------------------- #

def _two_end_reads(rig):
    """Print A's end read, then print B's, as the morning goes: A ended two minutes
    before B's end read was taken a minute ago."""
    with rig:
        end_a = print_monitor._capture_end_heads(XL, 77, "http://fb")
        end_b = print_monitor._capture_end_heads(XL, 78, "http://fb")
    end_a["at_s"] -= 120
    end_b["at_s"] -= 60
    return end_a, end_b


def _charge(rig, job, end, name):
    with rig, _download(_two_tool_gcode()):
        return print_deduct.deduct_completed_print(XL, name, job, fb_url="http://fb", end_heads=end)


def test_fcc_charging_an_earlier_print_after_a_later_ones_end_read_is_no_weighing(stamps, warn_lines):
    """S1, red on 82dbb38 (B held whole: #200 left at 112.4, a card saying FCC can't
    tell). Print B's end read was taken before print A's charge landed (A's file
    waited behind the printer's screen); A's charge is FCC's own, so B is charged as
    a plain print."""
    rig = TwoHeadsOverHTTP()
    end_a, end_b = _two_end_reads(rig)
    _charge(rig, 77, end_a, "a.gcode")
    assert rig.used(200) == pytest.approx(112.4) and rig.used(300) == pytest.approx(53.6)
    assert stamps.charged_after(200, end_b["at_s"]) == pytest.approx(12.4)
    out = _charge(rig, 78, end_b, "b.gcode")
    assert out["status"] == "deducted", out
    assert rig.used(200) == pytest.approx(124.8) and rig.used(300) == pytest.approx(57.2)
    assert cancel_review_store.get_pending(XL, "78#shortfall") is None
    assert not [m for m, lvl in warn_lines if "can't tell" in m or "was weighed" in m], warn_lines


def test_a_weighing_in_the_same_window_is_still_held_and_its_words_name_fccs_charge(stamps, warn_lines):
    """S1's other side: A's charge and a change FCC can't place (an edit in
    Spoolman's own page) both land after B's end read. B's #200 is still held, its
    words saying how much of the change was FCC's own; #300, which only A's charge
    moved, is charged."""
    rig = TwoHeadsOverHTTP()
    end_a, end_b = _two_end_reads(rig)
    _charge(rig, 77, end_a, "a.gcode")
    rig.sm.records["spool"][200]["used_weight"] = 120.0
    _charge(rig, 78, end_b, "b.gcode")
    assert rig.used(200) == 120.0 and rig.used(300) == pytest.approx(57.2)
    cause = cancel_review_store.get_pending(XL, "78#shortfall")["shortfall_causes"]["0"]
    assert cause["known_order"] is False, cause
    assert "(100.00 g used then, 120.00 g now, 12.40 g of it charged by FCC since)" in cause["words"], cause


def test_a_weighing_after_fccs_own_charge_is_held_at_0g(stamps, warn_lines):
    """And a weighing on FCC after both: held at 0 g, the scale having counted B."""
    rig = TwoHeadsOverHTTP()
    end_a, end_b = _two_end_reads(rig)
    _charge(rig, 77, end_a, "a.gcode")
    rig.sm.records["spool"][200]["used_weight"] = 137.2
    stamps.note(200, "the Quick-Weigh")
    _charge(rig, 78, end_b, "b.gcode")
    assert rig.used(200) == 137.2
    card = cancel_review_store.get_pending(XL, "78#shortfall")
    assert card["shortfall_causes"]["0"]["known_order"] is True and card["shortfall_prefill"] == {"0": 0.0}


def test_a_cards_apply_notes_its_charges_too(stamps):
    """S1: a 🛑 card's Apply is FCC's own charge, so a print ended before it isn't
    held over it."""
    rig = TwoHeadsOverHTTP()
    card = _held_card(rig, stamps)
    with rig:
        app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": XL, "job_id": card["job_id"], "rev": card["rev"],
            "charges": [{"position": 0, "sid": 200, "grams": 12.4}]})
    assert stamps.charged_after(200, 0) == pytest.approx(12.4)


def test_the_stamp_store_reads_its_first_form_and_keeps_charges_apart(stamps):
    """The file as the module first wrote it ({sid: stamp}) is read as weighings, and
    a charge is never read as a weighing."""
    import json
    with open(stamps._STORE_PATH, "w", encoding="utf-8") as fh:
        json.dump({"200": {"at": 1000.0, "how": "the Quick-Weigh"}}, fh)
    assert stamps.weighed_after(200, 999.0)["how"] == "the Quick-Weigh"
    stamps.note_charge(300, 5.0, at=1001.0)
    stamps.note_charge(300, 0.0, at=1002.0)                # a charge of nothing notes nothing
    assert stamps.last(300) is None and stamps.weighed_after(200, 999.0)["how"] == "the Quick-Weigh"
    assert stamps.charged_after(300, 1000.0) == 5.0 and stamps.charged_after(300, 1001.0) == 0.0
    stamps.note(300, "Edit Spool", at=1003.0)
    assert stamps.charged_after(300, 1000.0) == 5.0, "a weighing dropped the charges"


def test_a_save_between_the_check_and_the_charge_is_held_not_charged_on_top(stamps, warn_lines, monkeypatch):
    """S4, red on 82dbb38 (#200 charged to 142.4, no card). The Quick-Weigh's save of
    #200 lands right after deduct_completed_print's Decision 1 check: the apply's own
    check, under the spool's lock, holds it."""
    monkeypatch.setattr(routes_inventory, "_log_manual_weight_change", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    end["at_s"] -= 60
    real = print_deduct._weighed_since_end

    def _check_then_weigh(heads, end_at):
        out = real(heads, end_at)
        app_module.app.test_client().post("/api/spool/update", json={
            "id": 200, "updates": {"used_weight": 130.0},
            "based_on": {"mode": "set_used", "screen": "quick"}})
        return out

    with patch.object(print_deduct, "_weighed_since_end", side_effect=_check_then_weigh):
        out = _complete(rig, end)
    assert out["status"] == "deducted", out
    assert rig.used(200) == pytest.approx(130.0), "the weighing was charged on top"
    assert rig.used(300) == pytest.approx(53.6)
    card = cancel_review_store.get_pending(XL, f"{JOB}#shortfall")
    cause = card["shortfall_causes"]["0"]
    assert cause["why"] == "weighed" and cause["known_order"] is True and cause["sid"] == 200, card
    assert card["shortfall_prefill"] == {"0": 0.0}
    said = [m for m, lvl in warn_lines if lvl == "WARNING" and "#200 on XL-1" in m]
    assert len(said) == 1 and "was weighed on the Quick-Weigh" in said[0], warn_lines


def test_a_comment_only_edit_spool_save_writes_no_used_weight_and_stamps_nothing(stamps, warn_lines, monkeypatch):
    """S2, red on 82dbb38 (a 100.4 PATCH, a stamp, and the print held at 0 g). A page
    that sends Total Used as it drew it (to 0.1 g) over a stored 100.37 changed
    nothing there: nothing is written or stamped, and the print is charged."""
    monkeypatch.setattr(routes_inventory, "_log_manual_weight_change", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    rig.sm.records["spool"][200]["used_weight"] = 100.37
    rig.sm.records["spool"][200]["comment"] = "old"
    with rig:
        end = print_monitor._capture_end_heads(XL, JOB, "http://fb")
    end["at_s"] -= 60
    with rig:
        body = app_module.app.test_client().post("/api/edit_spool_wizard", json={
            "spool_id": 200,
            "spool_data": {"used_weight": 100.4, "comment": "new note", "initial_weight": 1000.0,
                           "archived": False, "extra": {}}}).get_json()
    assert body["success"] is True, body
    sent = [b for e, i, b in rig.sm.patches if e == "spool" and i == 200]
    assert sent and all("used_weight" not in b for b in sent) and sent[-1].get("comment") == "new note", sent
    assert stamps.last(200) is None
    _complete(rig, end)
    assert rig.used(200) == pytest.approx(112.77)
    assert cancel_review_store.get_pending(XL, f"{JOB}#shortfall") is None


def test_an_edit_spool_used_weight_past_the_boxs_rounding_is_still_written(stamps, monkeypatch):
    """A real change in Total Used is written and stamped, as before."""
    monkeypatch.setattr(routes_inventory, "_log_manual_weight_change", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    rig.sm.records["spool"][200]["used_weight"] = 100.37
    with rig:
        app_module.app.test_client().post("/api/edit_spool_wizard", json={
            "spool_id": 200, "spool_data": {"used_weight": 100.5, "extra": {}}})
    assert rig.used(200) == 100.5 and stamps.last(200)["how"] == "Edit Spool"


def test_a_live_edges_raise_offers_try_again_now_once(warn_lines):
    """S5, red on 82dbb38 (no line ever carried the button). A compute that always
    raises, first at the live edge: the edge's own line says how the queue keeps
    trying and carries the button; the queue's raises after it say nothing more."""
    with patch.object(print_deduct, "deduct_completed_print", side_effect=RuntimeError("bad file")), \
            patch.object(print_monitor, "_capture_end_heads", return_value=None):
        print_monitor._on_completion_edge(XL, "x.gcode", JOB, "http://fb")
        for _ in range(5):
            rec = cancel_fetch_store.get_pending(XL, JOB)
            print_monitor._run_fetch_retry(rec, "http://fb", print_monitor._claim_fetch(XL, JOB))
    offered = [m for m, lvl in warn_lines if "Try again now" in m]
    assert len(offered) == 1, warn_lines
    assert "FCC tries again when the printer is idle, twice more right away" in offered[0], offered
    assert 'data-fetch-job="77"' in offered[0], offered


def test_a_set_placed_five_hundredths_off_the_card_goes_ahead():
    """Y1, red on 82dbb38 (9.95 against 10 was 0.0500000000000007 here: refused as
    a page out of date). Whole cents, as the page rounds them."""
    rig = TwoHeadsOverHTTP()
    _set_card()
    body = _post_set(rig, 12.35)
    assert body["status"] == "confirmed", body
    assert rig.used(200) == pytest.approx(112.35)


def test_a_set_placed_six_hundredths_off_is_still_asked_about():
    rig = TwoHeadsOverHTTP()
    _set_card()
    body = _post_set(rig, 12.34)
    assert body["status"] == "error" and body.get("stale_page") is True, body


def test_a_no_spool_sets_unrounded_figure_is_compared_as_the_card_shows_it():
    """Y1's twin: a no_spool card's ask is the walk's figure (12.3549, shown 12.35);
    picks of 6.2 + 6.1 are within 0.05 g of what the card shows."""
    rig = TwoHeadsOverHTTP()
    rig.sm.add("spool", 100, location="", used_weight=10.0, initial_weight=1000.0, archived=False,
               filament={"weight": 1000.0})
    rec = {"printer_name": XL, "job_id": str(JOB), "filename": "x.gcode", "progress": 1.0,
           "total_grams": 12.3549, "ambiguous": False, "kind": "no_spool", "created": "2026-11-20 00:00:00",
           "spools": [], "usage_map": {"0": 12.3549},
           "unresolved_sets": {"0": [{"sid": 100, "when": "start"}, {"sid": 200, "when": "end"}]},
           "heads_at_end": [{"toolhead": "XL-1", "position": 0, "sid": 200, "sids": [200]}]}
    cancel_review_store.add_pending(rec)
    with rig:
        body = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": XL, "job_id": str(JOB),
            "charges": [{"position": 0, "sid": 200, "grams": 6.2},
                        {"position": 0, "sid": 100, "grams": 6.1}]}).get_json()
    assert body["status"] == "confirmed", body
    assert rig.used(200) == pytest.approx(106.2) and rig.used(100) == pytest.approx(16.1)


def _unsure_card(rig, stamps):
    end = _end_read(rig)
    stamps.note(200, "the weigh-out list", at=end["at_s"] - 3600)
    rig.sm.records["spool"][200]["used_weight"] = 104.0       # an edit in Spoolman's own page
    _complete(rig, end)
    return cancel_review_store.get_pending(XL, f"{JOB}#shortfall")


def test_settling_a_change_fcc_cant_place_says_it_was_left_as_set(stamps, warn_lines):
    """Y2's server half, red on 82dbb38 (it said "weighed after the print ended, the
    scale counted it", FCC's knowledge, for the person's choice)."""
    rig = TwoHeadsOverHTTP()
    card = _unsure_card(rig, stamps)
    with rig:
        body = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": XL, "job_id": card["job_id"], "rev": card["rev"],
            "charges": [], "settle_held": True}).get_json()
    assert body["settled_held"] is True and body["settled_unsure"] is True, body
    assert body["left_weighed"] == [{"line": "0", "sid": 200, "grams": 12.4, "known_order": False}], body
    said = [m for m, lvl in warn_lines if "left 12.40g" in m]
    assert len(said) == 1 and "couldn't tell whether the scale counted it: left as set on the card" in said[0]
    assert "the scale counted it." not in said[0], said


def _mixed_card():
    """An uncharged-grams card: line 0, #200 weighed on the Quick-Weigh after the print
    ended (0 g filled in); line 1, XL-2 had no spool (3 g)."""
    words = ("#200 on XL-1 was weighed on the Quick-Weigh at 14:05, after this print ended (at 13:50), "
             "so the scale already counted its 12.40 g")
    rec = {"printer_name": XL, "job_id": f"{JOB}#shortfall", "shortfall_of": str(JOB), "kind": "shortfall",
           "rev": 0, "filename": "x.gcode", "progress": 1.0, "total_grams": 15.4, "spools": [],
           "ambiguous": False, "unresolved_usage": {"0": 12.4, "1": 3.0}, "shortfall_prefill": {"0": 0.0},
           "shortfall_causes": {"0": {"why": "weighed", "sid": 200, "toolhead": "XL-1", "archived": False,
                                      "known_order": True, "words": words},
                                "1": {"why": "no_spool", "toolhead": "XL-2"}},
           "heads_at_end": [{"toolhead": "XL-1", "position": 0, "sid": 200, "sids": [200]},
                            {"toolhead": "XL-2", "position": 1, "sid": None}]}
    cancel_review_store.add_pending(rec)
    return rec


def _post_mixed(rig, **extra):
    with rig:
        return app_module.app.test_client().post("/api/cancel_deduct/confirm", json=dict({
            "printer_name": XL, "job_id": f"{JOB}#shortfall", "rev": 0,
            "charges": [{"position": 1, "sid": 300, "grams": 3.0}]}, **extra)).get_json()


def test_a_pick_beside_a_weighed_line_left_at_0g_settles_the_card(warn_lines, monkeypatch):
    """O3, red on 82dbb38 (the card was kept, and told the person to pick a spool for
    the 12.40 g the scale already counted). The page sends settle_held beside its
    pick; the weighed line settles in the same Apply."""
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    rig.sm.records["spool"][200]["used_weight"] = 130.0
    _mixed_card()
    body = _post_mixed(rig, settle_held=True)
    assert body["status"] == "confirmed" and body.get("settled_held") is True and not body.get("kept"), body
    assert body["left_weighed"] == [{"line": "0", "sid": 200, "grams": 12.4, "known_order": True}], body
    assert rig.used(300) == pytest.approx(53.0) and rig.used(200) == 130.0
    assert cancel_review_store.get_pending(XL, f"{JOB}#shortfall") is None
    msgs = [m for m, lvl in warn_lines]
    assert any("left 12.40g" in m and "uncharged on #200" in m and "the scale counted it" in m for m in msgs), msgs
    assert not any("still have no spool" in m or "wasn't charged to any spool" in m for m in msgs), msgs
    assert print_deduct_ledger.was_deducted(XL, f"{JOB}#shortfall")


def test_a_pick_beside_a_weighed_line_from_an_older_page_keeps_the_card(warn_lines, monkeypatch):
    """No settle_held (a page from before the review): kept as before. Passes on
    82dbb38 by design."""
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    _mixed_card()
    body = _post_mixed(rig)
    assert body.get("kept") is True and not body.get("settled_held"), body
    assert cancel_review_store.get_pending(XL, f"{JOB}#shortfall")["unresolved_usage"] == {"0": 12.4}


def test_settle_held_beside_a_pick_with_another_line_left_keeps_the_card(warn_lines, monkeypatch):
    """A line that isn't a weighed spool's, left without a pick, still keeps the card."""
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    rec = cancel_review_store.pop_pending(XL, _mixed_card()["job_id"])
    rec["unresolved_usage"]["2"] = 2.0
    rec["shortfall_causes"]["2"] = {"why": "no_spool", "toolhead": "XL-3"}
    rec["total_grams"] = 17.4
    cancel_review_store.add_pending(rec)
    body = _post_mixed(rig, settle_held=True)
    assert body.get("kept") is True and not body.get("settled_held"), body
    assert set(cancel_review_store.get_pending(XL, f"{JOB}#shortfall")["unresolved_usage"]) == {"0", "2"}


def test_a_cancels_weighed_row_left_at_0g_is_said_and_handed_to_the_page(stamps, warn_lines):
    """O4, red on 82dbb38 (no line said it, and the page could only say "the spool
    picked has 0 g left on record"). The cancel's card marks #200's row (weighed
    on FCC after the end, 0 g filled in); its Apply charges #300's row only."""
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    rig.sm.records["spool"][200]["used_weight"] = 120.0
    stamps.note(200, "the weigh-out list", at=end["at_s"] + 30)
    with rig, _download(_two_tool_gcode()):
        print_deduct._create_pending_cancel_review(XL, "x.gcode", JOB, 0.5, fb_url="http://fb",
                                                   end_heads=end)
    rec = cancel_review_store.get_pending(XL, str(JOB))
    rows = {r["sid"]: r for r in rec["spools"]}
    with rig:
        body = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": XL, "job_id": str(JOB), "updates": {"300": rows[300]["grams"]}}).get_json()
    assert body["status"] == "confirmed", body
    assert body["left_weighed"] == [{"line": "0", "sid": 200, "grams": rows[200]["grams"],
                                     "known_order": True}], body
    assert rig.used(200) == 120.0
    said = [m for m, lvl in warn_lines if "uncharged on #200" in m]
    assert len(said) == 1 and "weighed after the print ended, the scale counted it" in said[0], warn_lines


# --------------------------------------------------------------------------- #
# Group 64 fix review (the second round): FS1-FS4, FP2 / FP3 server           #
# --------------------------------------------------------------------------- #

_SET_POST = {"printer_name": XL, "job_id": str(JOB)}


@pytest.mark.parametrize("raw", [
    '{"charges": [{"row": 300, "sid": 300, "grams": 3.6}, {"position": 0, "sid": 200, "grams": 5.0}],'
    ' "set_ack": {"0": 1e308}}',
    '{"charges": [{"row": 300, "sid": 300, "grams": 3.6}, {"position": 0, "sid": 200, "grams": 1e307}],'
    ' "set_ack": {"0": 1e307}}',
    '{"charges": [{"row": 300, "sid": 300, "grams": 3.6}, {"position": 0, "sid": 200, "grams": 5.0}],'
    ' "set_ack": {"0": NaN}}',
    '{"charges": [{"row": 300, "sid": 300, "grams": 3.6}, {"position": 0, "sid": 200, "grams": 5.0}],'
    ' "set_ack": {"0": 1' + "0" * 400 + '}}',
], ids=["a huge set_ack", "typed 1e307 with its ack", "NaN", "a 401-digit integer"])
def test_a_set_figure_fcc_cant_use_keeps_the_card(raw):
    """FS1, red on abb67aa (a 500, and the card was lost: the whole-cents compare
    raised after the Apply had taken the card off the store). Nothing is charged and
    the card stays, with words a person can act on."""
    rig = TwoHeadsOverHTTP()
    _set_card()
    body = raw[:1] + '"printer_name": "XL", "job_id": "77", ' + raw[1:]
    with rig:
        r = app_module.app.test_client().post("/api/cancel_deduct/confirm", data=body,
                                              content_type="application/json")
    answer = r.get_json()
    # The set check refuses it itself (a 200 in its own words), never the net's 500.
    assert r.status_code == 200 and answer["status"] == "error", (r.status_code, answer)
    assert ("aren't a figure FCC can use" in answer["msg"]
            or "changed since FCC asked" in answer["msg"]), answer
    assert cancel_review_store.get_pending(XL, str(JOB)) is not None, "the card was lost"
    assert rig.used(200) == 100.0 and rig.used(300) == 50.0
    assert not print_deduct_ledger.was_deducted(XL, str(JOB))


def test_a_raise_in_the_set_check_keeps_the_card(monkeypatch):
    """FS1's net: whatever the check raises, the card goes back, as a raise in
    _rows_from_charges does."""
    monkeypatch.setattr(print_deduct, "_set_check_refusal", MagicMock(side_effect=RuntimeError("boom")))
    rig = TwoHeadsOverHTTP()
    _set_card()
    body = _post_set(rig, 12.4)
    assert body["status"] == "error" and "check them" in body["msg"], body
    assert cancel_review_store.get_pending(XL, str(JOB)) is not None


def _post_mixed_clamp(rig, **extra):
    with rig:
        return app_module.app.test_client().post("/api/cancel_deduct/confirm", json=dict({
            "printer_name": XL, "job_id": f"{JOB}#shortfall", "rev": 0,
            "charges": [{"position": 1, "sid": 300, "grams": 3.0}]}, **extra)).get_json()


def test_a_kept_card_counts_its_weighed_line_apart_after_a_clamp(warn_lines, monkeypatch):
    """FS2 (a), red on abb67aa ("14.40g still have no spool": the weighed line's 12.40
    g, which the scale counted, among them). The pick of #300 could take only 1 g of
    its 3, so the card is kept with that 2 g, and its weighed line waits apart."""
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    # Emptied, #300 is archived, and the archive writes FCC's notes: the fake knows them.
    monkeypatch.setattr(spoolman_api, "_FIELD_SCHEMA_CACHE", {})
    monkeypatch.setattr(spoolman_api, "_SPOOLMAN_VERSION_CACHE", {})
    monkeypatch.setattr(spoolman_api, "_RAW_EXTRAS_RETRY_DELAY_S", 0)
    rig = TwoHeadsOverHTTP()
    rig.sm.fields["spool"] = [{"key": k, "field_type": "text", "name": k} for k in (
        "container_slot", "physical_source", "physical_source_slot", "fcc_pre_archive_location",
        "fcc_pre_audit_location", "fcc_pre_box_location")]
    rig.sm.records["spool"][300]["used_weight"] = 999.0          # 1 g left
    rig.sm.records["spool"][200]["used_weight"] = 130.0
    _mixed_card()
    body = _post_mixed_clamp(rig, settle_held=True)
    assert body.get("kept") is True, body
    assert body["kept_weighed"] == [{"line": "0", "sid": 200, "grams": 12.4, "known_order": True}], body
    said = [m for m, lvl in warn_lines if "uncharged grams" in m]
    assert len(said) == 1, warn_lines
    assert "2.00g still have no spool" in said[0], said
    assert "12.40g on #200, weighed after the print ended, stay on the card" in said[0], said
    assert "14.40g" not in said[0], said


def test_a_kept_card_counts_its_weighed_line_apart_beside_another_unpicked_line(warn_lines, monkeypatch):
    """FS2 (b), red on abb67aa. Line 2 (no spool) is left without a pick, so the page
    sends no settle_held and the card is kept with both lines."""
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    rig.sm.records["spool"][200]["used_weight"] = 130.0
    rec = cancel_review_store.pop_pending(XL, _mixed_card()["job_id"])
    rec["unresolved_usage"]["2"] = 2.0
    rec["shortfall_causes"]["2"] = {"why": "no_spool", "toolhead": "XL-3"}
    rec["total_grams"] = 17.4
    cancel_review_store.add_pending(rec)
    body = _post_mixed_clamp(rig)
    assert body.get("kept") is True and len(body["kept_weighed"]) == 1, body
    said = [m for m, lvl in warn_lines if "uncharged grams" in m]
    assert "2.00g still have no spool" in said[0] and "12.40g on #200" in said[0], said
    assert "14.40g" not in said[0], said


def test_a_kept_card_of_only_unweighed_lines_keeps_its_words(warn_lines, monkeypatch):
    """No weighed line: the words as before (red on abb67aa only for the answer's
    new `kept_weighed` key, which was missing)."""
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    rec = cancel_review_store.pop_pending(XL, _mixed_card()["job_id"])
    rec["unresolved_usage"] = {"1": 3.0, "2": 2.0}
    rec["shortfall_causes"] = {"1": {"why": "no_spool", "toolhead": "XL-2"},
                               "2": {"why": "no_spool", "toolhead": "XL-3"}}
    rec["total_grams"] = 5.0
    cancel_review_store.add_pending(rec)
    body = _post_mixed_clamp(rig)
    assert body.get("kept") is True and body["kept_weighed"] == [], body
    said = [m for m, lvl in warn_lines if "uncharged grams" in m]
    assert "2.00g still have no spool — pick another in" in said[0], said


def test_a_weigh_save_is_stamped_before_a_waiting_charge_reads_it(stamps, warn_lines, monkeypatch):
    """FS3, red on abb67aa (known_order False, the print's 12.40 g filled in). The
    print's charge waits on #200's lock while a Quick-Weigh save holds it; the save
    stamped its weighing only after it let go (after its read-back, release, take-off
    and log line), so the charge read the new weight with no stamp. The stamp is now
    written inside the lock."""
    import time as _time
    import spoolman_api as _sm
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    end["at_s"] -= 60
    checked, save_has_lock, rechecked = threading.Event(), threading.Event(), threading.Event()
    real_check, real_update = print_deduct._weighed_since_end, _sm.update_spool
    real_changed = print_deduct._changed_since_check

    def _check(heads, end_at):
        out = real_check(heads, end_at)      # nothing changed yet: passes
        checked.set()
        save_has_lock.wait(5)                # the save now holds #200's lock
        return out

    def _update(sid, data, *a, **k):
        if str(sid) == "200" and data.get("used_weight") == 130.0:
            save_has_lock.set()
            _time.sleep(0.3)                 # the charge reaches the lock and waits
        return real_update(sid, data, *a, **k)

    def _changed(watch, sid, used):
        out = real_changed(watch, sid, used)
        if str(sid) == "200":
            rechecked.set()
        return out

    # The save's own steps after its write wait until the charge has re-checked.
    monkeypatch.setattr(routes_inventory, "_log_manual_weight_change", lambda *a, **k: rechecked.wait(5))
    done = {}

    def _save():
        checked.wait(5)
        done["status"] = app_module.app.test_client().post("/api/spool/update", json={
            "id": 200, "updates": {"used_weight": 130.0},
            "based_on": {"mode": "set_used", "screen": "quick"}}).status_code

    with rig, _download(_two_tool_gcode()), pytest.MonkeyPatch.context() as mp:
        mp.setattr(print_deduct, "_weighed_since_end", _check)
        mp.setattr(_sm, "update_spool", _update)
        mp.setattr(print_deduct, "_changed_since_check", _changed)
        t = threading.Thread(target=_save)
        t.start()
        out = print_deduct.deduct_completed_print(XL, "x.gcode", JOB, fb_url="http://fb", end_heads=end)
        t.join(10)
    assert out["status"] == "deducted" and done["status"] == 200, (out, done)
    assert rig.used(200) == 130.0, "charged on top"
    card = cancel_review_store.get_pending(XL, f"{JOB}#shortfall")
    cause = card["shortfall_causes"]["0"]
    assert cause["known_order"] is True and card["shortfall_prefill"] == {"0": 0.0}, card


def test_edit_spools_weight_save_is_stamped_while_it_holds_the_lock(stamps, monkeypatch):
    """FS3, Edit Spool's twin: its stamp is written while the spool's lock is held
    (another thread can't take it then). Red on abb67aa: stamped after the lock."""
    import spoolman_api as _sm
    monkeypatch.setattr(routes_inventory, "_log_manual_weight_change", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    held = {}
    real_note = stamps.note

    def _note(sid, how, at=None):
        got = {}

        def _probe():
            # The thread that takes an RLock is the one that must let it go: released
            # from another thread it stays held by a dead one, and every later test
            # that takes this spool's lock waits forever (it hung a run on abb67aa).
            lock = _sm.spool_lock(sid)
            got["free"] = lock.acquire(blocking=False)
            if got["free"]:
                lock.release()
        t = threading.Thread(target=_probe)
        t.start()
        t.join(5)
        held[str(sid)] = not got.get("free")
        return real_note(sid, how, at=at)

    monkeypatch.setattr(stamps, "note", _note)
    with rig:
        body = app_module.app.test_client().post("/api/edit_spool_wizard", json={
            "spool_id": 200, "spool_data": {"used_weight": 130.0, "extra": {}}}).get_json()
    assert body["success"] is True, body
    assert held == {"200": True}, held


def test_a_charge_found_landed_later_is_noted_from_when_it_was_sent(stamps, warn_lines, monkeypatch):
    """FS4, red on abb67aa (B held as a change FCC can't place). Print A's charge of
    #200 landed, but its answer was lost and the read-back failed: a failed write, on
    A's uncharged-grams card as a 43.6 row. That card's Apply finds it landed, and now
    notes it as FCC's own charge from when it was sent, so print B, whose end read
    came before A's charge, is charged as a plain print."""
    import requests
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    end_a, end_b = _two_end_reads(rig)
    lost = {"done": False, "fail_get": 0}
    real_patch, real_get = rig.sm.patch, rig.sm.get

    def _patch(url, json=None, **kw):
        r = real_patch(url, json=json, **kw)
        if url.rstrip("/").endswith("/spool/200") and not lost["done"] and (json or {}).get("used_weight"):
            lost["done"], lost["fail_get"] = True, 1
            raise requests.exceptions.ReadTimeout("read timed out (test)")
        return r

    def _get(url, **kw):
        if lost["fail_get"] and url.rstrip("/").endswith("/spool/200"):
            lost["fail_get"] -= 1
            raise requests.exceptions.ConnectionError("refused (test)")
        return real_get(url, **kw)

    rig.sm.patch, rig.sm.get = _patch, _get
    _charge(rig, 77, end_a, "a.gcode")
    assert rig.used(200) == pytest.approx(112.4)          # it landed
    assert stamps.charged_after(200, end_b["at_s"]) == 0.0
    card = cancel_review_store.get_pending(XL, "77#shortfall")
    row = card["spools"][0]
    assert row["sid"] == 200 and row["attempt_sent_at"] > end_b["at_s"], row
    with rig:
        body = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": XL, "job_id": "77#shortfall", "rev": card["rev"],
            "updates": {"200": row["grams"]}}).get_json()
    assert body["status"] == "confirmed", body
    assert rig.used(200) == pytest.approx(112.4), "charged twice"
    assert stamps.charged_after(200, end_b["at_s"]) == pytest.approx(12.4)
    out = _charge(rig, 78, end_b, "b.gcode")
    assert out["status"] == "deducted", out
    assert rig.used(200) == pytest.approx(124.8)
    assert cancel_review_store.get_pending(XL, "78#shortfall") is None


def _edit_add(rig, base, used=150.0):
    with rig:
        return app_module.app.test_client().post("/api/edit_spool_wizard", json={
            "spool_id": 200, "spool_data": {"used_weight": used, "extra": {}},
            "used_based_on": {"mode": "additive", "used": base}}).get_json()


def test_an_edit_spool_addition_on_a_weight_that_moved_is_refused(stamps, warn_lines, monkeypatch):
    """FP2, red on abb67aa (150 written over the charge's 112.4: the 12.4 g erased).
    Edit Spool opened at 100 g used; a print's charge took it to 112.4 behind the
    open form; "+ Add Printed Wt" 50 then posts 150 on top of 100. Nothing is saved,
    and the person is told to look again."""
    monkeypatch.setattr(routes_inventory, "_log_manual_weight_change", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    rig.sm.records["spool"][200]["used_weight"] = 112.4      # the charge, behind the form
    body = _edit_add(rig, base=100.0)
    assert body["success"] is False and body.get("details_changed") is True, body
    assert "changed since Edit Spool opened (100 g then, 112.4 g now" in body["msg"], body
    assert rig.used(200) == 112.4 and not [b for e, i, b in rig.sm.patches if e == "spool"]
    assert stamps.last(200) is None
    assert any("changed since Edit Spool opened" in m for m, lvl in warn_lines if lvl == "WARNING"), warn_lines


def test_an_edit_spool_addition_is_saved_and_never_stamped_as_a_weighing(stamps, monkeypatch):
    """FP3, red on abb67aa (stamped "Edit Spool", so a print charged after it was
    held at 0 g as if the scale had counted it). The base matches: written, no stamp."""
    monkeypatch.setattr(routes_inventory, "_log_manual_weight_change", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    body = _edit_add(rig, base=100.0)
    assert body["success"] is True, body
    assert rig.used(200) == 150.0 and stamps.last(200) is None


def test_after_an_addition_a_print_is_held_with_its_own_grams(stamps, warn_lines, monkeypatch):
    """FP3's effect on Decision 1, red on abb67aa (a 0 g card saying the scale counted
    the print). Grams typed for some print tell FCC nothing about this one, so the
    print is held as a change FCC can't place, its own 12.40 g filled in."""
    monkeypatch.setattr(routes_inventory, "_log_manual_weight_change", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    end["at_s"] -= 60
    _edit_add(rig, base=100.0)
    _complete(rig, end)
    card = cancel_review_store.get_pending(XL, f"{JOB}#shortfall")
    assert card["shortfall_causes"]["0"]["known_order"] is False and card["shortfall_prefill"] == {"0": 12.4}, card


def test_a_quick_weigh_additive_save_is_no_weighing_but_its_other_modes_are(stamps, monkeypatch):
    """FP3's rule on the weigh screens: the Quick-Weigh's Additive mode types grams
    used, no reading of the scale. Red on abb67aa for the first spool."""
    monkeypatch.setattr(routes_inventory, "_log_manual_weight_change", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    with rig:
        app_module.app.test_client().post("/api/spool/update", json={
            "id": 200, "updates": {"used_weight": 110.0},
            "based_on": {"mode": "additive", "screen": "quick", "used": 100.0}})
        app_module.app.test_client().post("/api/spool/update", json={
            "id": 300, "updates": {"used_weight": 60.0},
            "based_on": {"mode": "gross", "screen": "quick", "capacity": 1000.0}})
    assert rig.used(200) == 110.0 and stamps.last(200) is None
    assert stamps.last(300)["how"] == "the Quick-Weigh"


def test_a_cards_own_write_found_landed_later_is_noted_from_when_it_was_sent(stamps, monkeypatch):
    """FS4's other path, red on abb67aa (nothing noted). A card's Apply charges #200;
    its PATCH lands but the answer is lost and the read-back fails, so the card keeps
    a 43.6 retry row, which now carries when the write was sent. The next Apply finds
    the write landed and notes it as FCC's own charge from then."""
    import requests
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    rig = TwoHeadsOverHTTP()
    before = rig.sm.records["spool"][200]["used_weight"]
    rec = {"printer_name": XL, "job_id": f"{JOB}#shortfall", "shortfall_of": str(JOB), "kind": "shortfall",
           "rev": 0, "filename": "x.gcode", "progress": 1.0, "total_grams": 12.4, "spools": [],
           "ambiguous": False, "unresolved_usage": {"0": 12.4},
           "shortfall_causes": {"0": {"why": "no_spool", "toolhead": "XL-1"}},
           "heads_at_end": [{"toolhead": "XL-1", "position": 0, "sid": None}]}
    cancel_review_store.add_pending(rec)
    lost = {"done": False, "fail_get": 0}
    real_patch, real_get = rig.sm.patch, rig.sm.get

    def _patch(url, json=None, **kw):
        r = real_patch(url, json=json, **kw)
        if url.rstrip("/").endswith("/spool/200") and not lost["done"] and (json or {}).get("used_weight"):
            lost["done"], lost["fail_get"] = True, 1
            raise requests.exceptions.ReadTimeout("read timed out (test)")
        return r

    def _get(url, **kw):
        if lost["fail_get"] and url.rstrip("/").endswith("/spool/200"):
            lost["fail_get"] -= 1
            raise requests.exceptions.ConnectionError("refused (test)")
        return real_get(url, **kw)

    rig.sm.patch, rig.sm.get = _patch, _get
    with rig:
        first = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": XL, "job_id": f"{JOB}#shortfall", "rev": 0,
            "charges": [{"position": 0, "sid": 200, "grams": 12.4}]}).get_json()
    assert first["errors"], first
    assert rig.used(200) == pytest.approx(before + 12.4)              # it landed
    card = cancel_review_store.get_pending(XL, f"{JOB}#shortfall")
    row = card["spools"][0]
    assert row["sid"] == 200 and row.get("attempt_sent_at") is not None, row
    assert stamps.charged_after(200, 0) == 0.0
    with rig:
        second = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": XL, "job_id": f"{JOB}#shortfall", "rev": card["rev"],
            "updates": {"200": row["grams"]}}).get_json()
    assert second["status"] == "confirmed", second
    assert rig.used(200) == pytest.approx(before + 12.4), "charged twice"
    assert stamps.charged_after(200, row["attempt_sent_at"] - 1) == pytest.approx(12.4)


# --------------------------------------------------------------------------- #
# Group 64 full review: Decision 1 at a card's Apply (RW1 / OR1 / SP3 / PR1),  #
# and a spool that left its head at a swap (OR2 / SP2)                         #
# --------------------------------------------------------------------------- #

def _cancel_card(rig, end):
    with rig, _download(_two_tool_gcode()):
        print_deduct._create_pending_cancel_review(XL, "x.gcode", JOB, 0.5, fb_url="http://fb", end_heads=end)
    rec = cancel_review_store.get_pending(XL, str(JOB))
    return rec, {r["sid"]: r for r in rec["spools"]}


def _quick_weigh(rig, sid, used):
    with rig:
        return app_module.app.test_client().post("/api/spool/update", json={
            "id": sid, "updates": {"used_weight": used},
            "based_on": {"mode": "set_used", "screen": "quick"}}).get_json()


def _apply_card(rig, updates, rev=None, charges=None):
    body = {"printer_name": XL, "job_id": str(JOB)}
    if charges is not None:
        body["charges"] = charges
    else:
        body["updates"] = updates
    if rev is not None:
        body["rev"] = rev           # what today's page sends (Group 64 full review, FX7)
    with rig:
        return app_module.app.test_client().post("/api/cancel_deduct/confirm", json=body).get_json()


@pytest.fixture
def quiet_saves(monkeypatch):
    monkeypatch.setattr(routes_inventory, "_log_manual_weight_change", lambda *a, **k: None)
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)


def test_a_spool_weighed_after_its_card_was_made_is_held_at_the_apply(stamps, warn_lines, quiet_saves):
    """RW1 / OR1 / SP3 / PR1, red on c7073d8 (#200 charged the card's grams on top of
    the scale's 130 g). The cancel's card is made, then #200 is weighed on the
    Quick-Weigh; the card, unchanged, is applied as filled in. #200 is charged nothing
    and the card stays, its line marked and filled in with 0 g; #300 is charged."""
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    end["at_s"] -= 60
    rec, rows = _cancel_card(rig, end)
    assert "weighed" not in rows[200], rows[200]
    _quick_weigh(rig, 200, 130.0)
    body = _apply_card(rig, {"200": rows[200]["grams"], "300": rows[300]["grams"]})
    assert body["status"] == "confirmed", body
    assert rig.used(200) == 130.0, "charged on top of the scale"
    assert rig.used(300) == pytest.approx(50.0 + rows[300]["grams"])
    assert [h["sid"] for h in body["held"]] == [200] and body["held"][0]["known_order"] is True, body
    kept = cancel_review_store.get_pending(XL, str(JOB))
    row = next(r for r in kept["spools"] if r["sid"] == 200)
    assert row["weighed"]["known_order"] is True and row["prefill"] == 0.0, row
    assert "was weighed on the Quick-Weigh" in row["weighed"]["words"], row
    said = [m for m, lvl in warn_lines if lvl == "WARNING" and "#200" in m and "Nothing was charged" in m]
    assert len(said) == 1, warn_lines


def test_a_held_line_is_charged_as_typed_once_the_card_has_shown_it(stamps, quiet_saves):
    """The person sees the mark and types grams anyway (the weighing came before the
    print): the next Apply charges them, the card having shown that change."""
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    end["at_s"] -= 60
    rec, rows = _cancel_card(rig, end)
    _quick_weigh(rig, 200, 130.0)
    _apply_card(rig, {"200": rows[200]["grams"], "300": rows[300]["grams"]})
    body = _apply_card(rig, {"200": 5.0}, rev=1)
    assert body["status"] == "confirmed" and not body.get("held"), body
    assert rig.used(200) == pytest.approx(135.0)
    assert cancel_review_store.get_pending(XL, str(JOB)) is None


def test_a_change_fcc_cant_place_after_the_card_is_held_with_its_grams(stamps, quiet_saves):
    """An edit in Spoolman's own page after the card was made: held, its line filled
    in with the print's grams and marked as a change FCC can't place."""
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    end["at_s"] -= 60
    rec, rows = _cancel_card(rig, end)
    rig.sm.records["spool"][200]["used_weight"] = 104.0
    body = _apply_card(rig, {"200": rows[200]["grams"], "300": rows[300]["grams"]})
    assert rig.used(200) == 104.0 and body["held"][0]["known_order"] is False, body
    row = next(r for r in cancel_review_store.get_pending(XL, str(JOB))["spools"] if r["sid"] == 200)
    assert row["prefill"] == rows[200]["grams"] and "can't tell" in row["weighed"]["words"], row


def test_a_card_whose_spools_didnt_change_applies_in_one_go(stamps, quiet_saves):
    """Passes on c7073d8 by design."""
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    end["at_s"] -= 60
    rec, rows = _cancel_card(rig, end)
    body = _apply_card(rig, {"200": rows[200]["grams"], "300": rows[300]["grams"]})
    assert body["status"] == "confirmed" and not body.get("held"), body
    assert cancel_review_store.get_pending(XL, str(JOB)) is None


def test_a_line_the_card_already_showed_as_weighed_is_charged_as_typed(stamps, quiet_saves):
    """The weighing came before the card: its line was marked when the card was made,
    so the Apply charges what the person typed (passes on c7073d8 by design)."""
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    end["at_s"] -= 60
    _quick_weigh(rig, 200, 120.0)
    rec, rows = _cancel_card(rig, end)
    assert rows[200]["prefill"] == 0.0, rows[200]
    body = _apply_card(rig, {"200": 5.0, "300": rows[300]["grams"]})
    assert body["status"] == "confirmed" and not body.get("held"), body
    assert rig.used(200) == pytest.approx(125.0)


def test_a_set_spool_weighed_after_the_card_holds_its_box(stamps, quiet_saves):
    """SP3 (b), red on c7073d8 (the set's share for #200 charged on top). A set's spool
    on its head at the end, weighed after the card was made: its box is held."""
    import time as _t
    rig = TwoHeadsOverHTTP()
    _set_card()
    rec = cancel_review_store.pop_pending(XL, str(JOB))
    rec["heads_at_end"][0]["used"] = {"200": 100.0}
    rec["heads_at_end"][1]["used"] = {"300": 50.0}
    rec["end_at_s"] = _t.time() - 60
    cancel_review_store.add_pending(rec)
    _quick_weigh(rig, 200, 130.0)
    body = _post_set(rig, 12.4)
    assert rig.used(200) == 130.0 and [h["sid"] for h in body["held"]] == [200], body
    assert rig.used(300) == pytest.approx(53.6)


def test_the_spools_that_left_their_head_at_a_swap_and_when():
    """OR2 / SP2: each spool that left its head at a swap and didn't come back, with
    the moment the printer stopped for that swap."""
    log = [{"seq": 0, "position": 0, "from_sid": 100, "to_sid": 200, "at": 10.0},
           {"seq": 1, "position": 0, "from_sid": 200, "to_sid": 300, "at": 20.0}]
    assert print_deduct._swap_left_at(log) == {"100": 10.0, "200": 20.0}
    log.append({"seq": 2, "position": 0, "from_sid": 300, "to_sid": 100, "at": 30.0})
    assert print_deduct._swap_left_at(log) == {"200": 20.0, "300": 30.0}       # #100 came back
    assert print_deduct._swap_left_at([{"seq": 0, "position": 0, "from_sid": 1, "to_sid": 2}]) == {}
    entry = {"start_spools": {"0": 100}, "swap_log": []}
    print_deduct._record_swap_events(entry, {0: 200}, 0.5, at=123.5)
    assert entry["swap_log"][0]["at"] == 123.5 and entry["swap_log"][0]["from_sid"] == 100


def test_a_spool_that_left_at_a_swap_and_was_weighed_after_is_marked_on_its_card(stamps):
    """OR2 / SP2, red on c7073d8 (no mark: the swapped-out spool's share pre-filled and
    charged on top of the scale). A weighing before the swap is no weighing of it."""
    import time as _t
    t_swap = _t.time() - 120
    stamps.note(100, "the Quick-Weigh", at=t_swap + 30)
    stamps.note(400, "the Quick-Weigh", at=t_swap - 30)
    rows = [{"sid": 100, "toolhead": "XL-1", "position": 0, "grams": 12.4},
            {"sid": 400, "toolhead": "XL-1", "position": 0, "grams": 2.0},
            {"sid": 200, "toolhead": "XL-1", "position": 0, "grams": 3.0}]
    print_deduct._mark_weighed_rows(rows, [], _t.time() - 60, {"100": t_swap, "400": t_swap})
    assert rows[0]["prefill"] == 0.0 and rows[0]["weighed"]["known_order"] is True, rows[0]
    assert "left XL-1 at a swap" in rows[0]["weighed"]["words"], rows[0]
    assert "weighed" not in rows[1] and "weighed" not in rows[2], rows


def test_a_spool_that_left_at_a_swap_weighed_after_its_card_is_held_at_the_apply(stamps, quiet_saves):
    """OR2 / SP2 at the Apply, red on c7073d8: the swapped-out spool, weighed after the
    card was made, is charged nothing and its line marked."""
    import time as _t
    rig = TwoHeadsOverHTTP()
    rig.sm.add("spool", 100, location="SHELF-1", used_weight=300.0, initial_weight=1000.0,
               archived=False, filament={"weight": 1000.0})
    rec = {"printer_name": XL, "job_id": str(JOB), "filename": "x.gcode", "progress": 1.0, "total_grams": 12.4,
           "ambiguous": False, "kind": "partial", "created": "2026-11-22 00:00:00",
           "swap_left_at": {"100": _t.time() - 120},
           "spools": [{"sid": 100, "toolhead": "XL-1", "position": 0, "grams": 12.4, "display": "#100",
                       "color": "ff0000", "ambiguous": False}],
           "heads_at_end": [{"toolhead": "XL-1", "position": 0, "sid": 200, "sids": [200], "used": {"200": 100.0}}],
           "end_at_s": _t.time() - 60}
    cancel_review_store.add_pending(rec)
    _quick_weigh(rig, 100, 312.4)
    body = _apply_card(rig, {"100": 12.4})
    assert rig.used(100) == 312.4 and [h["sid"] for h in body["held"]] == [100], body
    row = cancel_review_store.get_pending(XL, str(JOB))["spools"][0]
    assert row["prefill"] == 0.0 and "left XL-1 at a swap" in row["weighed"]["words"], row


def test_a_cards_apply_judges_the_order_by_the_end_reads_own_moment(stamps, quiet_saves):
    """The card keeps the end read's moment (`end_at_s`), not only its words to the
    second (`heads_read_at`), so the Apply tells a weighing after the end from one
    before as the charge does. Here the end read is a minute old (its words say now),
    and the weighing 30 s after it: known order, 0 g."""
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    end["at_s"] -= 60
    rec, rows = _cancel_card(rig, end)
    assert rec["end_at_s"] == pytest.approx(end["at_s"]), rec.get("end_at_s")
    rig.sm.records["spool"][200]["used_weight"] = 130.0
    stamps.note(200, "the Quick-Weigh", at=end["at_s"] + 30)
    body = _apply_card(rig, {"200": rows[200]["grams"], "300": rows[300]["grams"]})
    assert body["held"][0]["known_order"] is True, body


# --------------------------------------------------------------------------- #
# Group 64 full review, chunk 2: a view drawn before a hold (FX7), a no_spool   #
# card's swapped-out spool (FX2), a mark the picks dropped (FX1), a mark from   #
# before the full review (FX4). Each is red on 89faa0b unless it says otherwise. #
# --------------------------------------------------------------------------- #

def _view_a_holds(rig):
    """A cancel's card applied once in view A: #300 charged, #200 (weighed on the
    Quick-Weigh after the card was made) held. Returns the rows view B still shows."""
    end = _end_read(rig)
    end["at_s"] -= 60
    rec, rows = _cancel_card(rig, end)
    _quick_weigh(rig, 200, 130.0)
    body = _apply_card(rig, {"200": rows[200]["grams"], "300": rows[300]["grams"]}, rev=0)
    assert [h["sid"] for h in body["held"]] == [200], body
    return rows


def test_a_view_drawn_before_a_hold_is_refused_and_charges_nothing(stamps, quiet_saves):
    """FX7. On 89faa0b view B's Apply charged #200 its 12.40 g on top of the scale's
    130 g and closed the card. Now the hold bumped the card's revision; B quotes the
    old one and is refused, nothing charged, the card kept."""
    rig = TwoHeadsOverHTTP()
    rows = _view_a_holds(rig)
    assert cancel_review_store.get_pending(XL, str(JOB))["rev"] == 1
    body = _apply_card(rig, {"200": rows[200]["grams"], "300": rows[300]["grams"]}, rev=0)
    assert body["status"] == "error" and body.get("stale") is True, body
    assert "drawn again" in body["msg"], body
    assert rig.used(200) == 130.0, "charged on top of the scale"
    kept = cancel_review_store.get_pending(XL, str(JOB))
    assert kept is not None and kept["rev"] == 1 and [r["sid"] for r in kept["spools"]] == [200], kept


def test_a_page_from_before_the_revision_is_told_to_reload(stamps, quiet_saves):
    """FX7: an older page sends no revision for this card; it is told to reload (its
    own redraw would never send one), nothing charged, the card kept."""
    rig = TwoHeadsOverHTTP()
    rows = _view_a_holds(rig)
    body = _apply_card(rig, {"200": rows[200]["grams"]})
    assert body["status"] == "error" and body.get("stale_page") is True and "Reload" in body["msg"], body
    assert rig.used(200) == 130.0
    assert cancel_review_store.get_pending(XL, str(JOB)) is not None


def test_a_card_never_held_needs_no_revision():
    """Passes on 89faa0b by design: a card no Apply kept with a hold has no revision,
    so a page that sends none (or 0) applies it as before."""
    rig = TwoHeadsOverHTTP()
    _set_card()
    body = _post_set(rig, 12.4)
    assert body["status"] == "confirmed", body


def _swapped_set_heads():
    return [{"toolhead": "XL-1", "position": 0, "sid": 200, "sids": [200], "used": {"200": 100.0}},
            {"toolhead": "XL-2", "position": 1, "sid": 300, "sids": [300], "used": {"300": 50.0}}]


@pytest.mark.parametrize("how", ["cancel", "completion"])
def test_a_no_spool_cards_set_spool_that_left_at_a_swap_and_was_weighed_after_is_held(stamps, quiet_saves, how):
    """FX2. A one-tool print on XL-1 starts on #100; at a pause #100 is swapped for
    #400 (recorded, with when the printer stopped); the print-end read names #200, so
    the head is a set {#100, #400, #200} and, no other head having printed, the card a
    no_spool card. #100 is weighed on the Quick-Weigh after its swap. On 89faa0b the
    card kept no swap_left_at, and #100 was charged its share on top of the scale."""
    import time as _t
    rig = TwoHeadsOverHTTP()
    for sid in (100, 400):
        rig.sm.add("spool", sid, location="SHELF-1", used_weight=300.0, initial_weight=1000.0,
                   archived=False, filament={"weight": 1000.0})
    t_swap = _t.time() - 300
    swap = [{"seq": 0, "position": 0, "progress": 0.4, "from_sid": 100, "to_sid": 400, "runout": True,
             "at": t_swap}]
    end_at = _t.time() - 120
    with rig:
        if how == "cancel":
            print_deduct._stash_cancel_review_from_heads(
                XL, "x.gcode", JOB, 0.5, "http://fb", False, {0: 12.4},
                (_swapped_set_heads(), "print_end", "2026-11-22 20:00:00"), {"0": 100}, swap, end_at=end_at)
        else:
            print_deduct._route_completion_to_review(
                XL, "x.gcode", JOB, {0: 12.4}, "http://fb", {0}, swap_log=swap, start_spools={"0": 100},
                heads=_swapped_set_heads(), heads_source="print_end", heads_read_at="2026-11-22 20:00:00",
                end_at=end_at)
    rec = cancel_review_store.get_pending(XL, str(JOB))
    assert rec["kind"] == "no_spool", rec["kind"]
    assert [e["sid"] for e in rec["unresolved_sets"]["0"]] == [100, 400, 200], rec["unresolved_sets"]
    assert rec["swap_left_at"] == {"100": t_swap} and rec["end_at_s"] == end_at, rec
    stamps.note(100, "the Quick-Weigh", at=t_swap + 30)
    rig.sm.records["spool"][100]["used_weight"] = 306.2           # the scale's reading
    body = _apply_card(rig, None, charges=[{"position": 0, "sid": 100, "grams": 4.34},
                                           {"position": 0, "sid": 400, "grams": 5.0},
                                           {"position": 0, "sid": 200, "grams": 3.06}])
    assert rig.used(100) == 306.2, "charged on top of the scale"
    assert [h["sid"] for h in body["held"]] == [100], body
    assert rig.used(400) == pytest.approx(305.0) and rig.used(200) == pytest.approx(103.06)
    row = next(r for r in cancel_review_store.get_pending(XL, str(JOB))["spools"] if r["sid"] == 100)
    assert row["prefill"] == 0.0 and "left XL-1 at a swap" in row["weighed"]["words"], row


def test_a_change_the_card_showed_isnt_held_again_when_the_apply_goes_out_as_picks(stamps, quiet_saves):
    """FX1. #200 was edited in Spoolman's own page after the print ended: the card
    marks it (FCC can't tell the order) and fills in its 12.40 g. The person keeps
    that and redirects XL-2's row to #400, so the Apply goes out as picks, which carry
    no mark. On 89faa0b #200 was held again ('check its line'); the card showed the
    change, so it is charged as typed."""
    rig = TwoHeadsOverHTTP()
    rig.sm.add("spool", 400, location="SHELF-1", used_weight=10.0, initial_weight=1000.0,
               archived=False, filament={"weight": 1000.0})
    end = _end_read(rig)
    end["at_s"] -= 60
    rig.sm.records["spool"][200]["used_weight"] = 104.0
    rec, rows = _cancel_card(rig, end)
    assert rows[200]["weighed"]["known_order"] is False and rows[200]["prefill"] == rows[200]["grams"], rows[200]
    body = _apply_card(rig, None, charges=[{"row": 200, "sid": 200, "grams": rows[200]["grams"]},
                                           {"row": 300, "sid": 400, "grams": rows[300]["grams"]}])
    assert body["status"] == "confirmed" and not body.get("held"), body
    assert rig.used(200) == pytest.approx(104.0 + rows[200]["grams"])
    assert rig.used(400) == pytest.approx(10.0 + rows[300]["grams"])
    assert cancel_review_store.get_pending(XL, str(JOB)) is None


def test_a_mark_from_before_the_full_review_isnt_held_again_after_fccs_own_charge(stamps, quiet_saves):
    """FX4. A card made before 89faa0b marked #200 with no `ours`: after the print
    ended FCC charged it another print's 5 g and it was edited in Spoolman's page, the
    mark showing the whole 9 g. Nothing changes after that. On 89faa0b the Apply took
    FCC's 5 g off its own side only and held #200; the card showed exactly this."""
    import time as _t
    rig = TwoHeadsOverHTTP()
    end_at = _t.time() - 300
    stamps.note_charge(200, 5.0, at=end_at + 30)
    rig.sm.records["spool"][200]["used_weight"] = 109.0
    rec = {"printer_name": XL, "job_id": str(JOB), "filename": "x.gcode", "progress": 0.5, "total_grams": 12.4,
           "ambiguous": False, "kind": "partial", "created": "2026-11-22 00:00:00", "end_at_s": end_at,
           "spools": [{"sid": 200, "toolhead": "XL-1", "position": 0, "grams": 12.4, "display": "#200",
                       "color": "ff0000", "ambiguous": False, "prefill": 12.4,
                       "weighed": {"words": "#200 on XL-1 changed weight after this print ended", "known_order": False,
                                   "then": 100.0, "now": 109.0}}],
           "heads_at_end": [{"toolhead": "XL-1", "position": 0, "sid": 200, "sids": [200], "used": {"200": 100.0}}]}
    cancel_review_store.add_pending(rec)
    body = _apply_card(rig, {"200": 12.4})
    assert body["status"] == "confirmed" and not body.get("held"), body
    assert rig.used(200) == pytest.approx(121.4)


def test_a_mark_from_before_the_full_review_still_holds_a_later_change(stamps, quiet_saves):
    """FX4's other side, red on no commit (89faa0b holds it too): the spool changed
    again after that card was made, so the Apply holds it."""
    import time as _t
    rig = TwoHeadsOverHTTP()
    end_at = _t.time() - 300
    rig.sm.records["spool"][200]["used_weight"] = 130.0
    rec = {"printer_name": XL, "job_id": str(JOB), "filename": "x.gcode", "progress": 0.5, "total_grams": 12.4,
           "ambiguous": False, "kind": "partial", "created": "2026-11-22 00:00:00", "end_at_s": end_at,
           "spools": [{"sid": 200, "toolhead": "XL-1", "position": 0, "grams": 12.4, "display": "#200",
                       "color": "ff0000", "ambiguous": False, "prefill": 12.4,
                       "weighed": {"words": "#200 on XL-1 changed weight after this print ended", "known_order": False,
                                   "then": 100.0, "now": 104.0}}],
           "heads_at_end": [{"toolhead": "XL-1", "position": 0, "sid": 200, "sids": [200], "used": {"200": 100.0}}]}
    cancel_review_store.add_pending(rec)
    body = _apply_card(rig, {"200": 12.4})
    assert [h["sid"] for h in body["held"]] == [200], body
    assert rig.used(200) == 130.0
