"""Group 43.3: pick the spool on a print review.

Derek, on two `no_spool` reviews for job 1104's file: "This should have an option
to select a different loaded spool, or any spool. Currently the bgcode directs to
toolhead 1, but I've been printing from toolhead 2, which was done on the printer
when selecting an existing file to print... give an option to easily re-direct
the deducts to the correct toolhead." Also 22.5(b): "A `no_spool` Review card
never names a spool. Its Apply charges whatever is on the head at that moment,
which can be a spool loaded after the print."

PrusaLink exposes nothing per slot, so FCC can't detect a printer-side tool remap.
The vehicle is a picker:
  - a `no_spool` review records the printer's heads AT PRINT END (`heads_at_end`);
  - GET /api/cancel_deduct/candidates lists the printer's heads with the spool on
    each NOW, for the card's picker (plus "any spool by #id");
  - Apply sends explicit `charges` — [{position, sid, grams}] for a no_spool
    review, [{row, sid, grams}] to redirect a row of a cancel/spool-changed
    review — and the server charges exactly those spools, through the same
    clamped, idempotent per-spool loop as every other review (43.1, 43.6).
  - An archived pick is refused for now: where a top-up onto an auto-archived
    spool should go is Group 43.2's open question for Derek.
  - Apply WITHOUT `charges` keeps the old re-check (a cached page, the tests that
    pin it).

The engine runs for real against tests/deduct_wire_harness.py.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import cancel_fetch_store  # noqa: E402
import cancel_review_store  # noqa: E402
import print_deduct  # noqa: E402
import print_deduct_ledger  # noqa: E402
import state  # noqa: E402
from deduct_wire_harness import WeightWireSpoolman, _start, _stop, _wire_ctx  # noqa: E402

INDX = "🦝 Core One INDX"
HEADS = (("RCOI-1", 0), ("RCOI-2", 1), ("RCOI-3", 2))


@pytest.fixture(autouse=True)
def _isolated_stores(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a)))
    return calls


def _spool(used, loc, archived=False, initial=1000.0):
    return {"used_weight": used, "initial_weight": initial, "archived": archived,
            "location": loc, "filament": {"weight": 1000.0}, "extra": {}}


def _sm():
    # T0's head (RCOI-1) is EMPTY: the print was sliced for T0 but ran on RCOI-2.
    return WeightWireSpoolman({
        96: _spool(900.0, "RCOI-2"),
        97: _spool(100.0, "RCOI-3"),
        98: _spool(50.0, "SHELF-A"),               # not on any head ("any spool")
        99: _spool(1000.0, "", archived=True),     # auto-archived at 0 g (job 1104's #99)
    })


def _ctx(sm):
    return _wire_ctx(sm, at={"RCOI-2": [96], "RCOI-3": [97]}, toolheads=HEADS, printer=INDX)


def _no_spool_review(sm, usage, job="J-1105"):
    ctx = _ctx(sm)
    _start(ctx)
    try:
        return print_deduct._stash_unresolved_review(
            INDX, "/usb/MAIN-B~1.BGC", job, 1.0, usage_map=usage, no_spool=True)
    finally:
        _stop(ctx)


def _confirm(sm, body):
    ctx = _ctx(sm)
    _start(ctx)
    try:
        return app_module.app.test_client().post("/api/cancel_deduct/confirm", json=body).get_json()
    finally:
        _stop(ctx)


def _pending(job):
    return next((r for r in cancel_review_store.list_pending() if r["job_id"] == job), None)


def test_a_no_spool_review_records_the_heads_at_print_end(logs):
    sm = _sm()
    res = _no_spool_review(sm, {0: 61.32})
    assert res["status"] == "pending_unresolved", res
    rec = _pending("J-1105")
    assert rec["heads_at_end"] == [
        {"toolhead": "RCOI-1", "position": 0, "sid": None},
        {"toolhead": "RCOI-2", "position": 1, "sid": 96},
        {"toolhead": "RCOI-3", "position": 2, "sid": 97},
    ], rec


def test_candidates_list_each_head_with_its_spool_now(logs):
    sm = _sm()
    ctx = _ctx(sm)
    _start(ctx)
    try:
        r = app_module.app.test_client().get("/api/cancel_deduct/candidates",
                                             query_string={"printer_name": INDX})
    finally:
        _stop(ctx)
    assert r.status_code == 200
    heads = {h["toolhead"]: h for h in r.get_json()["heads"]}
    assert heads["RCOI-1"]["sid"] is None
    assert heads["RCOI-2"]["sid"] == 96 and heads["RCOI-2"]["remaining"] == 100.0
    assert heads["RCOI-3"]["sid"] == 97 and heads["RCOI-3"]["archived"] is False
    assert "display" in heads["RCOI-2"]


def test_candidates_need_a_printer(logs):
    r = app_module.app.test_client().get("/api/cancel_deduct/candidates")
    assert r.status_code == 400


def test_apply_charges_the_picked_spool_not_the_sliced_head(logs):
    """Derek's case: the gcode says T0 (RCOI-1, empty), the print ran on RCOI-2.
    Pick RCOI-2's spool and the grams land there."""
    sm = _sm()
    _no_spool_review(sm, {0: 61.32})
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1105",
                         "charges": [{"position": 0, "sid": 96, "grams": 61.32}]})
    assert body["status"] == "confirmed", body
    assert sm.used(96) == pytest.approx(961.32)
    assert sm.used(97) == 100.0, "an unpicked spool was charged"
    entry = print_deduct_ledger._load()[print_deduct_ledger._key(INDX, "J-1105")]
    assert entry["grams"] == pytest.approx(61.32)
    assert _pending("J-1105") is None


def test_apply_can_charge_any_spool_by_id(logs):
    sm = _sm()
    _no_spool_review(sm, {0: 20.0})
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1105",
                         "charges": [{"position": 0, "sid": 98, "grams": 20.0}]})
    assert body["status"] == "confirmed", body
    assert sm.used(98) == pytest.approx(70.0)


def test_an_archived_pick_is_refused_and_the_review_kept(logs):
    """Where a top-up onto an auto-archived spool should go is 43.2's open
    question, so for now the card says so and charges nothing."""
    sm = _sm()
    _no_spool_review(sm, {0: 27.12})
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1105",
                         "charges": [{"position": 0, "sid": 99, "grams": 27.12}]})
    assert body["status"] == "error" and "archived" in body["msg"].lower(), body
    assert sm.used(99) == 1000.0 and not sm.patches
    assert _pending("J-1105") is not None, "a refused Apply must keep the review"
    assert not print_deduct_ledger.was_deducted(INDX, "J-1105")


@pytest.mark.parametrize("charges", [
    [{"position": 5, "sid": 96, "grams": 1.0}],    # a tool the print never used
    [{"position": 0, "sid": 96, "grams": 0}],      # nothing to charge
    [{"position": 0, "grams": 1.0}],               # no spool
    "not-a-list",
])
def test_a_malformed_pick_is_refused_and_the_review_kept(logs, charges):
    sm = _sm()
    _no_spool_review(sm, {0: 10.0})
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1105", "charges": charges})
    assert body["status"] == "error", body
    assert not sm.patches and _pending("J-1105") is not None


def test_a_partial_pick_warns_about_what_stayed_uncharged(logs):
    sm = _sm()
    _no_spool_review(sm, {0: 10.0, 2: 5.0})
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1105",
                         "charges": [{"position": 0, "sid": 96, "grams": 10.0}]})
    assert body["status"] == "confirmed" and body.get("shortfall_g") == pytest.approx(5.0), body
    assert any("wasn't charged" in m for m, _ in logs), logs


def test_apply_without_charges_keeps_the_old_recheck(logs):
    """A cached page (or a caller) that sends no `charges` gets the old behaviour:
    re-resolve against the head now. RCOI-1 is still empty, so: still no spool."""
    sm = _sm()
    _no_spool_review(sm, {0: 10.0})
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1105", "updates": {}})
    assert body["status"] == "still_no_spool", body
    assert _pending("J-1105") is not None


def test_a_cancel_review_row_can_be_redirected_to_another_spool(logs):
    """A cancel review names the spool on the head at print end (the expected
    spool). If the print really ran on another head, redirect that row."""
    sm = _sm()
    cancel_review_store.add_pending({
        "printer_name": INDX, "job_id": "J-1200", "filename": "f.bgcode", "progress": 0.5,
        "total_grams": 2.5, "ambiguous": False, "created": "2026-10-13 00:00:00",
        "spools": [{"sid": 97, "toolhead": "RCOI-3", "position": 2, "grams": 2.5}]})
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1200",
                         "charges": [{"row": 97, "sid": 96, "grams": 2.5}]})
    assert body["status"] == "confirmed", body
    assert sm.used(96) == pytest.approx(902.5) and sm.used(97) == 100.0


def test_a_redirect_must_name_a_row_of_this_review(logs):
    sm = _sm()
    cancel_review_store.add_pending({
        "printer_name": INDX, "job_id": "J-1201", "filename": "f.bgcode", "progress": 0.5,
        "total_grams": 2.5, "ambiguous": False, "created": "2026-10-13 00:00:00",
        "spools": [{"sid": 97, "toolhead": "RCOI-3", "position": 2, "grams": 2.5}]})
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1201",
                         "charges": [{"row": 12345, "sid": 96, "grams": 2.5}]})
    assert body["status"] == "error" and not sm.patches, body
    assert _pending("J-1201") is not None
