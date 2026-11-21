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
