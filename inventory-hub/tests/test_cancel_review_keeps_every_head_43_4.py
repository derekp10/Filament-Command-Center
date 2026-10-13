"""Group 43.4 (was 22.5): a cancel review keeps every head.

A cancelled print's review listed only the heads where FCC found a spool, and
its total left the rest out, so a head emptied mid-print lost its grams with no
warning at all. Group 39.4 makes that an everyday case: a confirmed move off a
printing head leaves it empty, and nothing records a swap until a resume. The
review now carries those heads as `unresolved_usage`; the card offers 43.3's
picker for them (a `{position, sid, grams}` pick), and confirm reports whatever
nobody picks as the job's shortfall instead of dropping it.

The engine runs for real against tests/deduct_wire_harness.py; only the gcode
compute is stubbed to a fixed usage map.
HEAD proof: on the pre-43.4 code every test here fails.
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
JOB = "J-4301"


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


def _spool(used, loc):
    return {"used_weight": used, "initial_weight": 1000.0, "archived": False,
            "location": loc, "filament": {"weight": 1000.0}, "extra": {}}


def _sm():
    # RCOI-3 (T2) is EMPTY: its spool left it mid-print. #97 sits on a shelf.
    return WeightWireSpoolman({96: _spool(900.0, "RCOI-2"), 97: _spool(100.0, "SHELF-A")})


def _ctx(sm):
    return _wire_ctx(sm, at={"RCOI-2": [96]}, toolheads=HEADS, printer=INDX)


def _stash(sm, usage):
    ctx = _ctx(sm) + [
        patch.object(print_deduct.prusalink_api, "fetch_printer_credentials",
                     return_value={"ip_address": "1.2.3.4", "api_key": "k"}),
        patch.object(print_deduct, "_compute_cancel_usage", return_value=(usage, None)),
    ]
    _start(ctx)
    try:
        return print_deduct._create_pending_cancel_review(INDX, "f.bgcode", JOB, 0.5, fb_url="http://fb")
    finally:
        _stop(ctx)


def _confirm(sm, body):
    ctx = _ctx(sm)
    _start(ctx)
    try:
        return app_module.app.test_client().post("/api/cancel_deduct/confirm",
                                                 json={"printer_name": INDX, "job_id": JOB, **body}).get_json()
    finally:
        _stop(ctx)


def _rec():
    return cancel_review_store.get_pending(INDX, JOB)


def test_a_head_with_no_spool_stays_on_the_review(logs):
    out = _stash(_sm(), {1: 10.0, 2: 5.0})
    assert out["status"] == "pending", out
    rec = _rec()
    assert [r["sid"] for r in rec["spools"]] == [96]
    assert rec.get("unresolved_usage") == {"2": 5.0}, rec
    assert rec["total_grams"] == pytest.approx(15.0)
    assert any(h["toolhead"] == "RCOI-3" for h in rec.get("heads_at_end") or []), rec
    assert any("5.00g on T2" in m and "no spool loaded" in m for m, _ in logs), logs


def test_confirming_without_a_pick_reports_the_uncharged_grams(logs):
    sm = _sm()
    _stash(sm, {1: 10.0, 2: 5.0})
    body = _confirm(sm, {"updates": {"96": 10.0}})
    assert body["status"] == "confirmed", body
    assert sm.used(96) == pytest.approx(910.0)
    assert body.get("shortfall_g") == pytest.approx(5.0), body
    assert any("5.00g of 'f.bgcode' wasn't charged" in m for m, _ in logs), logs
    assert print_deduct_ledger.was_deducted(INDX, JOB)


def test_picking_a_spool_for_the_emptied_head_charges_it(logs):
    sm = _sm()
    _stash(sm, {1: 10.0, 2: 5.0})
    body = _confirm(sm, {"charges": [{"row": 96, "sid": 96, "grams": 10.0},
                                     {"position": 2, "sid": 97, "grams": 5.0}]})
    assert body["status"] == "confirmed", body
    assert sm.used(96) == pytest.approx(910.0) and sm.used(97) == pytest.approx(105.0)
    assert body.get("shortfall_g") == pytest.approx(0.0), body
    line = next(m for m, _ in logs if "Spool #97" in m and "cancel-deduct" in m)
    assert line.startswith(f"✔️ {INDX} RCOI-3: "), line


def test_a_retry_does_not_offer_a_picked_head_again(logs):
    """#97's write is lost: the retry keeps #97 as a ROW (with its 43.6 baseline)
    and no longer lists T2 as uncharged, so it can't be picked a second time."""
    sm = _sm()
    _stash(sm, {1: 10.0, 2: 5.0})
    sm.patch_lost.add(97)
    first = _confirm(sm, {"charges": [{"row": 96, "sid": 96, "grams": 10.0},
                                      {"position": 2, "sid": 97, "grams": 5.0}]})
    assert first["status"] == "confirmed" and first["errors"], first
    rec = _rec()
    assert [r["sid"] for r in rec["spools"]] == [97], rec
    assert not rec.get("unresolved_usage"), rec
    assert rec.get("requested_total") == pytest.approx(15.0), rec
