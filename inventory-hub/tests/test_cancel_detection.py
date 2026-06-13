"""Simulation tests for the live-pulse cancelled-print DETECTION wiring
(FilaBridge absorption §9.3 / build slice 2a).

The detection layer rides the dashboard-pulse printer-state probe: it latches
the running job (filename / job_id / monotonic byte-progress) while a print is
in progress, and fires the partial deduct on the →STOPPED/ERROR edge. These
tests drive the edge logic + `get_printer_job` parsing + the full
pulse→detect→deduct path with a MOCKED PrusaLink + Spoolman, so no physical
cancelled print is needed to validate it (Derek's "active test pattern": catch
issues in CI, burn filament only for a final sign-off).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import prusalink_api  # noqa: E402
import print_deduct_ledger  # noqa: E402
import cancel_review_store  # noqa: E402
import cancel_fetch_store  # noqa: E402
import print_tracker_store  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_tracker():
    """Each test starts with an empty PRINT_TRACKER and synchronous dispatch
    (so the cancel-edge action runs inline, not on a daemon thread)."""
    app_module._PRINT_TRACKER.clear()
    prev_async = app_module._CANCEL_DEDUCT_RUN_ASYNC
    app_module._CANCEL_DEDUCT_RUN_ASYNC = False
    try:
        yield
    finally:
        app_module._CANCEL_DEDUCT_RUN_ASYNC = prev_async
        app_module._PRINT_TRACKER.clear()


@pytest.fixture
def capture_edge():
    """Replace the cancel-edge ACTION with a capturing mock, so the detection
    tests assert WHAT fires (and with which latched values) independently of the
    deduct itself. This seam (`_on_cancel_edge`) is stable across slice 2a/5."""
    m = MagicMock()
    with patch.object(app_module, "_on_cancel_edge", m):
        yield m


@pytest.fixture
def capture_ambiguous():
    """Capture the AMBIGUOUS-edge action (in-progress → IDLE/READY WITHOUT an
    observed terminal state — a fast cancel→restart that slipped the poll, or a
    printer power-cycle). Separate seam from _on_cancel_edge so the cancel tests
    stay clean. _on_ambiguous_edge(printer, filename, job_id, progress, fb_url)."""
    m = MagicMock()
    with patch.object(app_module, "_on_ambiguous_edge", m):
        yield m


def _state(s):
    return {"state": s, "is_active": s in ("PRINTING", "PAUSING", "RESUMING")}


def _job(filename="/usb/print.gcode", job_id=7, progress=0.5, meta=None):
    return {"filename": filename, "job_id": job_id, "progress": progress,
            "file_meta": meta or {}}


class _Resp:
    """Faithful-enough stand-in for requests.Response: exposes status_code, ok,
    content, .text (real Response decodes the body to a string), and .json()."""
    def __init__(self, status_code=200, body=None, content=b"x"):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.content = content if status_code != 204 else b""
        self._body = body or {}

    @property
    def text(self):
        import json as _json
        if isinstance(self._body, str):
            return self._body
        return _json.dumps(self._body)

    def json(self):
        return self._body


# ---------------------------------------------------------------------------
# get_printer_job — /api/v1/job parsing
# ---------------------------------------------------------------------------

def _creds(*a, **k):
    return {"ip_address": "1.2.3.4", "api_key": "k"}


def test_get_printer_job_parses_v1():
    body = {
        "id": 42, "state": "PRINTING", "progress": 37.5,
        "file": {
            "refs": {"download": "/usb/MyPrint.bgcode"},
            "name": "MyPrint.bgcode", "path": "/usb/MyPrint.bgcode",
            "meta": {"filament used [g]": "40, 32", "filament used [mm]": "20, 16"},
        },
    }
    with patch.object(prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(prusalink_api.requests, "get", return_value=_Resp(200, body)):
        out = prusalink_api.get_printer_job("http://fb", "XL")
    assert out["job_id"] == 42
    assert out["filename"] == "/usb/MyPrint.bgcode"   # refs.download preferred
    assert abs(out["progress"] - 0.375) < 1e-9        # percent / 100
    assert out["file_meta"]["filament used [g]"] == "40, 32"


def test_get_printer_job_prefers_refs_download_over_name():
    body = {"id": 1, "progress": 10,
            "file": {"refs": {"download": "/usb/A.gcode"}, "name": "A.gcode"}}
    with patch.object(prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(prusalink_api.requests, "get", return_value=_Resp(200, body)):
        out = prusalink_api.get_printer_job("http://fb", "XL")
    assert out["filename"] == "/usb/A.gcode"


def test_get_printer_job_idle_204_returns_none():
    with patch.object(prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(prusalink_api.requests, "get", return_value=_Resp(204)):
        assert prusalink_api.get_printer_job("http://fb", "XL") is None


def test_get_printer_job_legacy_fallback():
    """v1 404 (firmware lacks it) → legacy /api/job parsed."""
    legacy = {"job": {"file": {"name": "old.gcode", "path": "/usb/old.gcode"}},
              "progress": {"completion": 0.42}}

    def _get(url, **k):
        if "/api/v1/job" in url:
            return _Resp(404, {})
        return _Resp(200, legacy)

    with patch.object(prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(prusalink_api.requests, "get", side_effect=_get):
        out = prusalink_api.get_printer_job("http://fb", "XL")
    assert out["filename"] == "/usb/old.gcode"
    assert abs(out["progress"] - 0.42) < 1e-9
    assert out["job_id"] is None   # legacy has no numeric id → blank job


def test_get_printer_job_no_creds_returns_none():
    with patch.object(prusalink_api, "fetch_printer_credentials", return_value=None):
        assert prusalink_api.get_printer_job("http://fb", "XL") is None


# ---------------------------------------------------------------------------
# _track_print_edge — latch + edge detection (action seam mocked)
# ---------------------------------------------------------------------------

def _drive(states, jobs=None):
    """Feed a sequence of (state, job) through _track_print_edge for one
    printer. `jobs` maps a state-index to the get_printer_job return."""
    jobs = jobs or {}
    for i, st in enumerate(states):
        job_ret = jobs.get(i, _job())
        with patch.object(app_module.prusalink_api, "get_printer_job",
                          return_value=job_ret):
            app_module._track_print_edge("XL", _state(st) if st else None, "http://fb")


def test_printing_then_stopped_fires_once(capture_edge):
    _drive(["PRINTING", "STOPPED"],
           jobs={0: _job(filename="/usb/p.gcode", job_id=9, progress=0.4)})
    assert capture_edge.call_count == 1
    args = capture_edge.call_args.args
    # _on_cancel_edge(printer, filename, job_id, progress, fb_url)
    assert args[0] == "XL"
    assert args[1] == "/usb/p.gcode"
    assert args[2] == 9
    assert abs(args[3] - 0.4) < 1e-9


def test_error_state_fires(capture_edge):
    _drive(["PRINTING", "ERROR"], jobs={0: _job(progress=0.6)})
    assert capture_edge.call_count == 1
    assert abs(capture_edge.call_args.args[3] - 0.6) < 1e-9


def test_monotonic_progress_latched(capture_edge):
    # 0.2 then 0.6 then a regressed 0.4 — the edge must use the MAX (0.6).
    _drive(["PRINTING", "PRINTING", "PRINTING", "STOPPED"],
           jobs={0: _job(progress=0.2), 1: _job(progress=0.6), 2: _job(progress=0.4)})
    assert capture_edge.call_count == 1
    assert abs(capture_edge.call_args.args[3] - 0.6) < 1e-9


def test_job_id_change_resets_progress_high_water(capture_edge):
    """PRINTING job A @0.7, then a DIFFERENT job B @0.1 starts while still
    in-progress (cancel→reslice→restart faster than a sampled STOPPED). The new
    job must NOT inherit A's 0.7 high-water — B's own cancel deducts B's progress
    (0.1), else a quick restart over-deducts the new spool."""
    _drive(["PRINTING", "PRINTING", "STOPPED"],
           jobs={0: _job(filename="/usb/a.gcode", job_id=100, progress=0.7),
                 1: _job(filename="/usb/b.gcode", job_id=200, progress=0.1)})
    assert capture_edge.call_count == 1
    args = capture_edge.call_args.args
    assert args[1] == "/usb/b.gcode" and args[2] == 200
    assert abs(args[3] - 0.1) < 1e-9   # 0.1, NOT max(0.7, 0.1)


def test_finished_does_not_fire_cancel(capture_edge):
    """A completed print (FINISHED) must NOT fire the CANCEL edge. Whether it
    fires a COMPLETION is flag-dependent (Phase-C) and covered in
    test_completion_deduct — mock that seam so this stays a pure cancel-detection
    assertion with NO real deduct side-effects regardless of the live config flag
    (which is ON in dev, so an unmocked FINISHED would hit the real printer)."""
    with patch.object(app_module, "_on_completion_edge"):
        _drive(["PRINTING", "FINISHED"])
    assert capture_edge.call_count == 0


def test_idle_after_printing_fires_ambiguous_review(capture_ambiguous, capture_edge):
    """PRINTING → IDLE without an observed STOPPED/FINISHED is the AMBIGUOUS edge
    (2026-06-13): a fast cancel→restart that slipped the poll, or a power-cycle.
    It must NOT be silently dropped — it routes to the review pipeline flagged
    'couldn't confirm', and NEVER to the auto-deduct cancel edge. The retained
    progress (0.26 — the proven prod signature) rides along as the hint."""
    _drive(["PRINTING", "IDLE"],
           jobs={0: _job(filename="/usb/p.gcode", job_id=9, progress=0.26)})
    assert capture_ambiguous.call_count == 1
    assert capture_edge.call_count == 0
    args = capture_ambiguous.call_args.args
    # _on_ambiguous_edge(printer, filename, job_id, progress, fb_url)
    assert args[0] == "XL" and args[1] == "/usb/p.gcode" and args[2] == 9
    assert abs(args[3] - 0.26) < 1e-9


def test_ready_after_printing_fires_ambiguous(capture_ambiguous):
    """READY (newer-firmware idle) is in the idle allow-list, same as IDLE."""
    _drive(["PRINTING", "READY"], jobs={0: _job(progress=0.5)})
    assert capture_ambiguous.call_count == 1


def test_offline_then_idle_fires_ambiguous(capture_ambiguous):
    """PRINTING → offline(None) → IDLE (the printer power-cycle live case): the
    offline tick bridges (leaving prev=PRINTING), then the IDLE tick fires the
    ambiguous review from the pre-blip latch."""
    with patch.object(app_module.prusalink_api, "get_printer_job",
                      return_value=_job(filename="/usb/b.gcode", job_id=3, progress=0.7)):
        app_module._track_print_edge("XL", _state("PRINTING"), "http://fb")
    app_module._track_print_edge("XL", None, "http://fb")        # offline
    app_module._track_print_edge("XL", _state("IDLE"), "http://fb")
    assert capture_ambiguous.call_count == 1
    args = capture_ambiguous.call_args.args
    assert args[1] == "/usb/b.gcode" and abs(args[3] - 0.7) < 1e-9


def test_ambiguous_does_not_fire_without_latched_job(capture_ambiguous):
    """PRINTING with no latch-able job (get_printer_job None) → IDLE: there's no
    filename to review, so the ambiguous edge must NOT fire."""
    with patch.object(app_module.prusalink_api, "get_printer_job", return_value=None):
        app_module._track_print_edge("XL", _state("PRINTING"), "http://fb")
    app_module._track_print_edge("XL", _state("IDLE"), "http://fb")
    assert capture_ambiguous.call_count == 0


def test_printing_to_attention_does_not_fire(capture_ambiguous, capture_edge):
    """PRINTING → ATTENTION (a filament runout / M600 prompt) is NOT an end edge —
    the print is stalled, not over. cur=ATTENTION isn't idle/terminal, so nothing
    fires here; the latch is held so the eventual END is still caught."""
    _drive(["PRINTING", "ATTENTION"], jobs={0: _job(progress=0.3)})
    assert capture_ambiguous.call_count == 0
    assert capture_edge.call_count == 0


def test_attention_to_idle_fires_ambiguous(capture_ambiguous):
    """PRINTING → ATTENTION → IDLE: a hard reset out of the filament-prompt screen
    (Derek's live Core One case — you can't reach Cancel without a filament reload,
    so you power-cycle). The print ENDED from ATTENTION without an observed
    terminal → fire the ambiguous review from the held latch (prev=ATTENTION is
    'active', not idle/terminal)."""
    _drive(["PRINTING", "ATTENTION", "IDLE"],
           jobs={0: _job(filename="/usb/r.bgcode", job_id=42, progress=0.91)})
    assert capture_ambiguous.call_count == 1
    args = capture_ambiguous.call_args.args
    assert args[1] == "/usb/r.bgcode" and args[2] == 42
    assert abs(args[3] - 0.91) < 1e-9


def test_attention_offline_idle_fires_ambiguous(capture_ambiguous):
    """The full hard-reset sequence: PRINTING → ATTENTION → offline(None) → IDLE.
    The offline tick bridges (latch held at ATTENTION), then the rebooted IDLE
    fires the ambiguous review. Exactly the live Core One @91% flow."""
    with patch.object(app_module.prusalink_api, "get_printer_job",
                      return_value=_job(filename="/usb/r.bgcode", job_id=42, progress=0.91)):
        app_module._track_print_edge("XL", _state("PRINTING"), "http://fb")
    app_module._track_print_edge("XL", _state("ATTENTION"), "http://fb")
    app_module._track_print_edge("XL", None, "http://fb")            # power-off
    app_module._track_print_edge("XL", _state("IDLE"), "http://fb")  # rebooted
    assert capture_ambiguous.call_count == 1
    assert abs(capture_ambiguous.call_args.args[3] - 0.91) < 1e-9


def test_attention_to_stopped_fires_cancel(capture_edge):
    """PRINTING → ATTENTION → STOPPED: cancelling FROM the filament-prompt screen
    is still a real cancel edge (prev=ATTENTION is 'active'), not a silent drop."""
    _drive(["PRINTING", "ATTENTION", "STOPPED"], jobs={0: _job(progress=0.3)})
    assert capture_edge.call_count == 1


def test_attention_resume_does_not_fire(capture_ambiguous, capture_edge):
    """PRINTING → ATTENTION → PRINTING (loaded filament, resumed) → no edge — the
    print continues; the resume re-latches."""
    _drive(["PRINTING", "ATTENTION", "PRINTING"], jobs={0: _job(progress=0.3)})
    assert capture_ambiguous.call_count == 0
    assert capture_edge.call_count == 0


def test_ambiguous_resets_latch_no_double_fire(capture_ambiguous):
    """The ambiguous edge resets the latch (like cancel/complete), so a second
    IDLE tick can't re-fire."""
    _drive(["PRINTING", "IDLE", "IDLE"], jobs={0: _job(progress=0.4)})
    assert capture_ambiguous.call_count == 1


def test_observed_finished_then_idle_not_ambiguous(capture_ambiguous):
    """A completion FCC actually OBSERVED (PRINTING → FINISHED → IDLE) is NOT
    ambiguous: prev=FINISHED on the IDLE tick is not in-progress. This is the key
    no-spam guard — normal completions must never raise an ambiguous review.
    (Flag forced off so FINISHED takes the non-firing branch.)"""
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=False):
        _drive(["PRINTING", "FINISHED", "IDLE"], jobs={0: _job(progress=0.99)})
    assert capture_ambiguous.call_count == 0


def test_pause_resume_then_stopped_fires(capture_edge):
    """A pause is still in-progress, so a print paused then cancelled still
    deducts (with the latest latch)."""
    _drive(["PRINTING", "PAUSED", "PRINTING", "STOPPED"],
           jobs={0: _job(progress=0.3), 2: _job(progress=0.55, job_id=12)})
    assert capture_edge.call_count == 1
    assert capture_edge.call_args.args[2] == 12
    assert abs(capture_edge.call_args.args[3] - 0.55) < 1e-9


def test_offline_blip_is_bridged(capture_edge):
    """PRINTING → offline(None) → STOPPED: the offline blip is not an edge, and
    the pre-blip latch still drives the deduct on the real STOPPED."""
    with patch.object(app_module.prusalink_api, "get_printer_job",
                      return_value=_job(filename="/usb/b.gcode", job_id=3, progress=0.7)):
        app_module._track_print_edge("XL", _state("PRINTING"), "http://fb")
    app_module._track_print_edge("XL", None, "http://fb")        # offline
    app_module._track_print_edge("XL", _state("STOPPED"), "http://fb")
    assert capture_edge.call_count == 1
    assert capture_edge.call_args.args[1] == "/usb/b.gcode"
    assert abs(capture_edge.call_args.args[3] - 0.7) < 1e-9


def test_no_double_fire_when_stopped_persists(capture_edge):
    _drive(["PRINTING", "STOPPED", "STOPPED"])
    assert capture_edge.call_count == 1   # second STOPPED tick: prev not in-progress


def test_stopped_without_prior_print_does_not_fire(capture_edge):
    """A STOPPED seen with no preceding in-progress state is not a cancel edge
    (printer was already idle/stopped when the dashboard loaded)."""
    _drive(["STOPPED"])
    assert capture_edge.call_count == 0


def test_cancel_without_latched_job_logs_and_skips(capture_edge):
    """PRINTING with no job latch-able (get_printer_job returns None) then
    STOPPED — too-short-to-sample: no deduct, but an INFO log so it's visible."""
    with patch.object(app_module.prusalink_api, "get_printer_job", return_value=None):
        app_module._track_print_edge("XL", _state("PRINTING"), "http://fb")
    with patch.object(app_module.state, "add_log_entry") as log:
        app_module._track_print_edge("XL", _state("STOPPED"), "http://fb")
    assert capture_edge.call_count == 0
    assert log.call_count == 1
    assert "no active job was latched" in log.call_args.args[0]


def test_second_print_after_cancel_fires_again(capture_edge):
    """After a cancel resets the latch, a NEW print that is itself cancelled
    must fire again (the reset doesn't wedge the tracker)."""
    _drive(["PRINTING", "STOPPED"], jobs={0: _job(job_id=1)})
    _drive(["PRINTING", "STOPPED"], jobs={0: _job(job_id=2)})
    assert capture_edge.call_count == 2
    assert capture_edge.call_args_list[1].args[2] == 2


# ---------------------------------------------------------------------------
# End-to-end: pulse → detect → real deduct_cancelled_print → Spoolman
# ---------------------------------------------------------------------------

_DEAD = "; " + ("pad " * 40) + "\n"


def _cancelled_gcode():
    """T0 extrudes 10mm before the cancel, 10mm after; T1 only after. footer
    mm=[20,16] g=[40,32] → 2.0 g/mm. Returns (gcode, reached_fraction)."""
    prefix = "M83\nT0\nG1 X10 E5\nG1 X20 E5\n"
    suffix = ("G1 X30 E5\nG1 X40 E5\nT1\nG1 E16\n"
              "; filament used [mm] = 20, 16\n; filament used [g] = 40, 32\n")
    gcode = prefix + _DEAD + suffix
    cut = len(prefix.encode("utf-8")) + len(_DEAD.encode("utf-8")) // 2
    return gcode, cut / len(gcode.encode("utf-8"))


@pytest.fixture
def ledger_tmp(tmp_path, monkeypatch):
    # Isolate EVERY persistent store the monitor touches so an e2e tick can never
    # write the live container's bind-mounted data/ (the XL::7 / XL::J9 leak,
    # 2026-06-13): ledger + review + deferred-fetch + the latch snapshot.
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetch.json"))
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))


def test_pulse_printing_then_stopped_creates_pending_review(ledger_tmp):
    """Drive the WHOLE path: a PRINTING pulse latches the job via the live
    probe, a STOPPED pulse computes the per-tool partial and STASHES a pending
    review (slice 5 = preview-and-confirm, NOT auto-write). Spoolman is NOT
    touched; the untouched head is skipped in the resolved rows."""
    gcode, frac = _cancelled_gcode()
    printer_map = {
        "XL-1": {"printer_name": "XL", "position": 0},
        "XL-2": {"printer_name": "XL", "position": 1},
    }
    spools = {
        100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0},
        200: {"id": 200, "used_weight": 50.0, "initial_weight": 1000.0},
    }
    spools_at = {"XL-1": [100], "XL-2": [200]}
    captured = {"updates": []}

    def _update(sid, data):
        captured["updates"].append((sid, dict(data)))
        return {"id": sid, **data}

    # get_printer_state: PRINTING on pulse 1, STOPPED on pulse 2.
    state_seq = iter([_state("PRINTING"), _state("STOPPED")])
    job_ret = _job(filename="job.gcode", job_id="J-1", progress=frac)

    ctx = [
        patch.object(app_module.config_loader, "load_config", return_value={}),
        patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map),
        patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(app_module.locations_db, "get_bindings_for_machine",
                     return_value={"printer_name": "XL", "toolheads": {}, "printer_pool": []}),
        patch.object(app_module.spoolman_api, "bucket_spools_by_location", return_value={}),
        patch.object(app_module.prusalink_api, "get_printer_state",
                     side_effect=lambda *a, **k: next(state_seq)),
        patch.object(app_module.prusalink_api, "get_printer_job", return_value=job_ret),
        patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds),
        patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                     side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}),
        patch.object(app_module.spoolman_api, "get_spools_at_location",
                     side_effect=lambda loc: spools_at.get(str(loc).upper(), [])),
        patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))),
        patch.object(app_module.spoolman_api, "update_spool", side_effect=_update),
        patch.object(app_module.spoolman_api, "format_spool_display",
                     return_value={"text": "#s", "color": "ff0000"}),
    ]
    for m in ctx:
        m.start()
    try:
        app_module._cancel_monitor_tick()   # PRINTING → latch
        app_module._cancel_monitor_tick()   # STOPPED → stash pending
    finally:
        for m in reversed(ctx):
            m.stop()

    assert captured["updates"] == [], "preview path must NOT write to Spoolman"
    pending = cancel_review_store.list_pending()
    assert len(pending) == 1, pending
    rec = pending[0]
    assert rec["printer_name"] == "XL" and rec["job_id"] == "J-1"
    sids = {r["sid"]: r for r in rec["spools"]}
    assert 100 in sids and abs(sids[100]["grams"] - 20.0) < 1e-6   # T0: 10mm*2.0
    assert 200 not in sids, "untouched toolhead's spool must not be in the preview"
    # Not yet committed to the ledger — that happens on confirm/dismiss.
    assert print_deduct_ledger.was_deducted("XL", "J-1") is False


# ---------------------------------------------------------------------------
# Hardening coverage (from the slice-2a adversarial review)
# ---------------------------------------------------------------------------

def test_continuous_get_printer_job_failure_skips_cancel(capture_edge):
    """If get_printer_job RAISES on every printing poll (timeout/500), nothing
    latches; the cancel can't be computed and is skipped with a visible log —
    not a crash, not a silent fire with stale data."""
    import requests
    with patch.object(app_module.prusalink_api, "get_printer_job",
                      side_effect=requests.exceptions.Timeout("boom")):
        app_module._track_print_edge("XL", _state("PRINTING"), "http://fb")
        app_module._track_print_edge("XL", _state("PRINTING"), "http://fb")
    with patch.object(app_module.state, "add_log_entry") as log:
        app_module._track_print_edge("XL", _state("STOPPED"), "http://fb")
    assert capture_edge.call_count == 0
    assert log.call_count == 1
    assert "no active job was latched" in log.call_args.args[0]


def test_legacy_blank_job_id_cancel_still_fires(capture_edge):
    """A legacy-firmware job (no numeric id → job_id None) must still fire the
    cancel; the latch keeps the filename even though the id is blank (the
    ledger then deducts once from the edge, accepting the §9.4 restart window)."""
    _drive(["PRINTING", "STOPPED"],
           jobs={0: _job(filename="/usb/legacy.gcode", job_id=None, progress=0.5)})
    assert capture_edge.call_count == 1
    args = capture_edge.call_args.args
    assert args[1] == "/usb/legacy.gcode"
    assert args[2] == ""          # blank id defaulted at fire time
    assert abs(args[3] - 0.5) < 1e-9


def test_zero_job_id_not_latched(capture_edge):
    """A spurious job_id of 0 / '0' is treated as blank (matches the ledger's
    _is_blank_job set) — it must not be latched as a real id."""
    _drive(["PRINTING", "STOPPED"],
           jobs={0: _job(filename="/usb/z.gcode", job_id=0, progress=0.3)})
    assert capture_edge.call_count == 1
    assert capture_edge.call_args.args[2] == ""   # 0 rejected → blank default


# ---------------------------------------------------------------------------
# fetch_cancel_gcode failure + deduct messaging
# ---------------------------------------------------------------------------

def test_deduct_gcode_fetch_fail_logs_visible_warning_not_silent(ledger_tmp):
    """A cancel whose gcode can't be fetched/decoded must surface a VISIBLE
    warning so it isn't silently un-deducted, and must NOT be ledger-recorded
    (a later fetch could succeed)."""
    with patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(app_module.prusalink_api, "fetch_cancel_gcode", return_value=None), \
         patch.object(app_module.state, "add_log_entry") as log:
        out = app_module.deduct_cancelled_print(
            "XL", "/usb/Print.bgcode", "J-9", 0.4, fb_url="http://fb",
            ip_address="1.2.3.4", api_key="k")
    assert out["status"] == "error"
    assert log.call_count == 1
    msg, level = log.call_args.args[0], log.call_args.args[1]
    assert level == "WARNING"
    assert "Weigh the spool" in msg
    assert print_deduct_ledger.was_deducted("XL", "J-9") is False


def test_deduct_unrecognized_footer_warns_distinctly(ledger_tmp):
    """Gcode present but with no Prusa 'filament used' footer → WARNING (the
    tool extruded but we can't measure it), distinct from a true no-extrusion
    cancel (INFO)."""
    no_footer = "M83\nT0\nG1 X10 E5\n; some non-prusa slicer\n"
    with patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, frac: {"gcode": no_footer, "fraction": frac}), \
         patch.object(app_module.state, "add_log_entry") as log:
        out = app_module.deduct_cancelled_print(
            "XL", "x.gcode", "J-10", 0.9, fb_url="http://fb",
            ip_address="1.2.3.4", api_key="k")
    assert out["status"] == "no_usage"
    assert log.call_args.args[1] == "WARNING"
    assert "no recognized per-tool 'filament used' footer" in log.call_args.args[0]


# ---------------------------------------------------------------------------
# Real daemon-thread dispatch (production path, not the sync test shortcut)
# ---------------------------------------------------------------------------

def test_cancel_creates_pending_once_on_real_daemon_thread(ledger_tmp):
    """Exercise the ACTUAL async dispatch (_CANCEL_DEDUCT_RUN_ASYNC=True): a
    PRINTING→STOPPED edge spawns the daemon thread, which stashes a pending
    review exactly once. Proves the thread path (not just the sync shortcut)."""
    import time
    gcode, frac = _cancelled_gcode()
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    spools = {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0}}
    captured = {"updates": []}

    def _update(sid, data):
        captured["updates"].append((sid, dict(data)))
        return {"id": sid, **data}

    app_module._CANCEL_DEDUCT_RUN_ASYNC = True   # fixture restores it
    ctx = [
        patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map),
        patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds),
        patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                     side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}),
        patch.object(app_module.spoolman_api, "get_spools_at_location",
                     side_effect=lambda loc: [100] if str(loc).upper() == "XL-1" else []),
        patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))),
        patch.object(app_module.spoolman_api, "update_spool", side_effect=_update),
        patch.object(app_module.spoolman_api, "format_spool_display",
                     return_value={"text": "#s", "color": "ff0000"}),
    ]
    for m in ctx:
        m.start()
    try:
        with patch.object(app_module.prusalink_api, "get_printer_job",
                          return_value=_job(filename="job.gcode", job_id="T-1", progress=frac)):
            app_module._track_print_edge("XL", _state("PRINTING"), "http://fb")
        app_module._track_print_edge("XL", _state("STOPPED"), "http://fb")  # dispatches a thread
        # Wait for the daemon thread to stash the pending review.
        deadline = time.time() + 3.0
        while time.time() < deadline and not cancel_review_store.has_pending("XL", "T-1"):
            time.sleep(0.02)
    finally:
        for m in reversed(ctx):
            m.stop()

    assert cancel_review_store.has_pending("XL", "T-1") is True, "daemon review never stashed"
    assert captured["updates"] == [], "preview path must NOT write to Spoolman"
    rec = cancel_review_store.get_pending("XL", "T-1")
    assert len(rec["spools"]) == 1 and rec["spools"][0]["sid"] == 100
    assert abs(rec["spools"][0]["grams"] - 20.0) < 1e-6


# ---------------------------------------------------------------------------
# Cancel-monitor daemon — dashboard-independent detection (Derek's correction)
# ---------------------------------------------------------------------------

def test_single_head_printer_folds_usage_to_sole_position():
    """A one-toolhead printer (Derek's Core One — one head, one spool) folds all
    footer tools onto its sole position, so an MMU-profile file (footer marks
    slot 1) still deducts from the one physical spool instead of orphaning to a
    non-existent position 1."""
    gcode = ("M83\nT1\nG1 E10\n"
             "; filament used [mm] = 0, 10\n; filament used [g] = 0, 25\n")
    pm = {"CORE1-M0": {"printer_name": "Core One", "position": 0}}
    with patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}), \
         patch.object(app_module.locations_db, "get_active_printer_map", return_value=pm):
        usage_map, terminal = app_module._compute_cancel_usage(
            "Core One", "f.gcode", "J-1", 1.0, "1.2.3.4", "k")
    assert terminal is None
    assert set(usage_map.keys()) == {0}, usage_map      # slot-1 folded → position 0
    assert abs(usage_map[0] - 25.0) < 1e-6


def test_single_position_multi_material_not_folded():
    """MMU SAFETY: a real multi-material print (several spools swapped through one
    head → multi-tool footer) on a single-position printer must NOT be summed
    onto one spool (that would over-deduct). It keeps its per-tool map and falls
    through to the orphan-warning path instead."""
    gcode = ("M83\nT0\nG1 E10\nT1\nG1 E4\n"
             "; filament used [mm] = 10, 4\n; filament used [g] = 20, 8\n")
    pm = {"CORE1-M0": {"printer_name": "Core One", "position": 0}}
    with patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}), \
         patch.object(app_module.locations_db, "get_active_printer_map", return_value=pm):
        usage_map, terminal = app_module._compute_cancel_usage(
            "Core One", "f.gcode", "J-3", 1.0, "1.2.3.4", "k")
    assert terminal is None
    assert set(usage_map.keys()) == {0, 1}, usage_map   # NOT folded (multi-tool)


def test_multi_head_printer_keeps_per_tool_map():
    """A multi-toolhead printer (XL/INDX) keeps the per-tool map — tool index IS
    the toolhead position there, no fold."""
    gcode = ("M83\nT0\nG1 E10\nT1\nG1 E4\n"
             "; filament used [mm] = 10, 4\n; filament used [g] = 20, 8\n")
    pm = {"XL-1": {"printer_name": "XL", "position": 0},
          "XL-2": {"printer_name": "XL", "position": 1}}
    with patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}), \
         patch.object(app_module.locations_db, "get_active_printer_map", return_value=pm):
        usage_map, terminal = app_module._compute_cancel_usage(
            "XL", "f.gcode", "J-2", 1.0, "1.2.3.4", "k")
    assert terminal is None
    assert set(usage_map.keys()) == {0, 1}, usage_map   # per-tool preserved
    assert abs(usage_map[0] - 20.0) < 1e-6 and abs(usage_map[1] - 8.0) < 1e-6


def test_cancel_monitor_tick_drives_edge(capture_edge):
    """The 30s daemon tick probes each printer and runs the latch/edge detector
    independent of the dashboard: PRINTING then STOPPED across two ticks fires
    the cancel edge."""
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    state_seq = iter([_state("PRINTING"), _state("STOPPED")])
    with patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map), \
         patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "get_printer_state",
                      side_effect=lambda *a, **k: next(state_seq)), \
         patch.object(app_module.prusalink_api, "get_printer_job",
                      return_value=_job(filename="j.gcode", job_id="M-1", progress=0.5)):
        app_module._cancel_monitor_tick()   # PRINTING → latch
        app_module._cancel_monitor_tick()   # STOPPED → edge
    assert capture_edge.call_count == 1
    assert capture_edge.call_args.args[2] == "M-1"


def test_cancel_monitor_tick_no_printers_noop(capture_edge):
    with patch.object(app_module.locations_db, "get_active_printer_map", return_value={}), \
         patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")):
        busy = app_module._cancel_monitor_tick()
    assert capture_edge.call_count == 0
    assert busy is False   # nothing to poll → loop backs off to the idle cadence


# ---------------------------------------------------------------------------
# Adaptive poll cadence — the tick reports BUSY so the loop can speed up
# ---------------------------------------------------------------------------

def _tick_busy_for(state_str, job=None):
    """Run one tick with every printer reporting `state_str`; return the busy
    flag. Latch persistence + the fetch-retry pass are isolated from disk."""
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    with patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map), \
         patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "get_printer_state", return_value=_state(state_str)), \
         patch.object(app_module.prusalink_api, "get_printer_job", return_value=job), \
         patch.object(app_module, "print_tracker_store"), \
         patch.object(app_module, "_process_pending_cancel_fetches"):
        return app_module._cancel_monitor_tick()


def test_tick_busy_while_printing():
    """A printer in-progress → tick returns True → loop polls fast (so a fast
    cancel→restart is sampled before the screen clears)."""
    assert _tick_busy_for("PRINTING", job=_job(job_id="B-1")) is True


def test_tick_busy_on_terminal_screen():
    """A printer sitting on a terminal screen (STOPPED) also keeps the loop fast,
    so the screen-clear unlock + deferred fetch drain promptly."""
    assert _tick_busy_for("STOPPED") is True


def test_tick_busy_on_finished_screen():
    assert _tick_busy_for("FINISHED") is True


def test_tick_busy_on_attention():
    """ATTENTION (filament prompt) keeps the loop fast so a hard reset / cancel
    out of it is sampled promptly."""
    assert _tick_busy_for("ATTENTION", job=_job(job_id="A-1")) is True


def test_tick_idle_backs_off():
    """All idle → tick returns False → loop backs off to the slow cadence."""
    assert _tick_busy_for("IDLE") is False


def test_tick_offline_backs_off():
    """Offline/unreachable (state None) isn't 'busy' — don't burn the fast
    cadence probing a printer that's powered off."""
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    with patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map), \
         patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "get_printer_state", return_value=None), \
         patch.object(app_module.prusalink_api, "get_printer_job", return_value=None), \
         patch.object(app_module, "print_tracker_store"), \
         patch.object(app_module, "_process_pending_cancel_fetches"):
        assert app_module._cancel_monitor_tick() is False


# ---------------------------------------------------------------------------
# Instant-ack — log the moment the STOPPED edge fires, before the slow download
# ---------------------------------------------------------------------------

def test_cancel_edge_logs_instant_ack():
    """_on_cancel_edge logs the immediate '🛑 Cancel detected … computing the
    partial…' line BEFORE the (slow, async) gcode download — so the user isn't
    met with 30-60s of silence on a slow .bgcode pull."""
    logs = []
    with patch.object(app_module, "_create_pending_cancel_review") as review, \
         patch.object(app_module.state, "add_log_entry",
                      side_effect=lambda *a, **k: logs.append(a)):
        app_module._on_cancel_edge("XL", "/usb/p.bgcode", "J-1", 0.62, "http://fb")
    assert any("Cancel detected on XL" in str(a[0]) and "computing the partial" in str(a[0])
               for a in logs), logs
    review.assert_called_once()


def test_ambiguous_edge_logs_instant_ack():
    """_on_ambiguous_edge logs its own instant-ack ('… couldn't confirm …') and
    routes to the review pipeline with ambiguous=True."""
    logs = []
    with patch.object(app_module, "_create_pending_cancel_review") as review, \
         patch.object(app_module.state, "add_log_entry",
                      side_effect=lambda *a, **k: logs.append(a)):
        app_module._on_ambiguous_edge("XL", "/usb/p.bgcode", "J-2", 0.26, "http://fb")
    assert any("couldn't confirm" in str(a[0]) for a in logs), logs
    review.assert_called_once()
    assert review.call_args.kwargs.get("ambiguous") is True


def test_cancel_monitor_start_idempotent():
    """The daemon starts at most once per process (no real thread spawned in the
    test — threading.Thread is mocked)."""
    app_module._cancel_monitor_started = False
    try:
        with patch.object(app_module.threading, "Thread") as T:
            app_module._start_cancel_monitor()
            app_module._start_cancel_monitor()
        assert T.call_count == 1
    finally:
        app_module._cancel_monitor_started = False


def test_pulse_no_longer_drives_detection():
    """Regression guard for the decoupling: the dashboard pulse must NOT run
    cancel detection (that's the daemon's job now), so an unfocused/closed
    dashboard can't cause missed cancels."""
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    with patch.object(app_module, "_track_print_edge") as tpe, \
         patch.object(app_module.config_loader, "load_config", return_value={}), \
         patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map), \
         patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.locations_db, "get_bindings_for_machine",
                      return_value={"printer_name": "XL", "toolheads": {}, "printer_pool": []}), \
         patch.object(app_module.spoolman_api, "bucket_spools_by_location", return_value={}), \
         patch.object(app_module.prusalink_api, "get_printer_state", return_value=_state("PRINTING")):
        app_module._pulse_section_printer_status()
    assert tpe.call_count == 0, "dashboard pulse must not drive cancel detection (daemon-only)"


# ---------------------------------------------------------------------------
# End-to-end: pulse → AMBIGUOUS idle edge → review (flagged, no auto-deduct)
# ---------------------------------------------------------------------------

def test_pulse_printing_then_idle_creates_ambiguous_review(ledger_tmp):
    """Drive the WHOLE ambiguous path through the daemon tick: a PRINTING tick
    latches the job, then an IDLE tick (NO observed STOPPED/FINISHED) computes the
    per-tool partial at the retained progress and STASHES a review FLAGGED
    ambiguous. Spoolman is NOT touched (review, not auto-deduct), and the ledger
    is untouched until confirm/dismiss."""
    gcode, frac = _cancelled_gcode()
    printer_map = {
        "XL-1": {"printer_name": "XL", "position": 0},
        "XL-2": {"printer_name": "XL", "position": 1},
    }
    spools = {
        100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0},
        200: {"id": 200, "used_weight": 50.0, "initial_weight": 1000.0},
    }
    spools_at = {"XL-1": [100], "XL-2": [200]}
    captured = {"updates": []}

    def _update(sid, data):
        captured["updates"].append((sid, dict(data)))
        return {"id": sid, **data}

    # get_printer_state: PRINTING on tick 1, IDLE on tick 2 (no terminal sampled).
    state_seq = iter([_state("PRINTING"), _state("IDLE")])
    job_ret = _job(filename="amb.gcode", job_id="A-1", progress=frac)

    ctx = [
        patch.object(app_module.config_loader, "load_config", return_value={}),
        patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map),
        patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(app_module.prusalink_api, "get_printer_state",
                     side_effect=lambda *a, **k: next(state_seq)),
        patch.object(app_module.prusalink_api, "get_printer_job", return_value=job_ret),
        patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds),
        patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                     side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}),
        patch.object(app_module.spoolman_api, "get_spools_at_location",
                     side_effect=lambda loc: spools_at.get(str(loc).upper(), [])),
        patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))),
        patch.object(app_module.spoolman_api, "update_spool", side_effect=_update),
        patch.object(app_module.spoolman_api, "format_spool_display",
                     return_value={"text": "#s", "color": "ff0000"}),
        patch.object(app_module, "print_tracker_store"),          # isolate latch persistence
        patch.object(app_module, "_process_pending_cancel_fetches"),  # not under test here
    ]
    for m in ctx:
        m.start()
    try:
        app_module._cancel_monitor_tick()   # PRINTING → latch
        app_module._cancel_monitor_tick()   # IDLE → ambiguous review
    finally:
        for m in reversed(ctx):
            m.stop()

    assert captured["updates"] == [], "ambiguous review must NOT write to Spoolman"
    pending = cancel_review_store.list_pending()
    assert len(pending) == 1, pending
    rec = pending[0]
    assert rec["printer_name"] == "XL" and rec["job_id"] == "A-1"
    assert rec.get("ambiguous") is True, "review must be flagged ambiguous"
    sids = {r["sid"]: r for r in rec["spools"]}
    assert 100 in sids and abs(sids[100]["grams"] - 20.0) < 1e-6   # T0: 10mm*2.0
    assert 200 not in sids, "untouched toolhead's spool must not be in the preview"
    assert print_deduct_ledger.was_deducted("XL", "A-1") is False
