"""Group 43 adversarial review (2026-10-13): the confirmed findings, pinned.

Each test names its finding. The engine runs for real against
tests/deduct_wire_harness.py, whose missing spool now answers the way Spoolman
does: a 404 with a TRUTHY {"message": ...} body, which get_spool returns as-is.

HEAD proof: on the pre-fix branch (aa59e14) every test here fails except
test_a_stamped_row_whose_write_did_not_land_can_be_redirected, which guards that
the new refusal stays narrow.
"""
from __future__ import annotations

import os
import sys

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


def _msgs(logs):
    return [m for m, _ in logs]


def _spool(used, loc, archived=False, initial=1000.0):
    return {"used_weight": used, "initial_weight": initial, "archived": archived,
            "location": loc, "filament": {"weight": 1000.0}, "extra": {}}


def _sm(extra=None):
    spools = {96: _spool(900.0, "RCOI-2"), 97: _spool(100.0, "RCOI-3"),
              98: _spool(50.0, "SHELF-A")}
    spools.update(extra or {})
    return WeightWireSpoolman(spools)


def _ctx(sm):
    return _wire_ctx(sm, at={"RCOI-2": [96], "RCOI-3": [97]}, toolheads=HEADS, printer=INDX)


def _confirm(sm, body):
    ctx = _ctx(sm)
    _start(ctx)
    try:
        r = app_module.app.test_client().post("/api/cancel_deduct/confirm", json=body)
        return r.get_json()
    finally:
        _stop(ctx)


def _no_spool_review(sm, usage, job="J-1105"):
    ctx = _ctx(sm)
    _start(ctx)
    try:
        return print_deduct._stash_unresolved_review(
            INDX, "/usb/MAIN-B~1.BGC", job, 1.0, usage_map=usage, no_spool=True)
    finally:
        _stop(ctx)


def _cancel_review(job, rows):
    cancel_review_store.add_pending({
        "printer_name": INDX, "job_id": job, "filename": "f.bgcode", "progress": 0.5,
        "total_grams": sum(r["grams"] for r in rows), "ambiguous": False,
        "created": "2026-10-13 00:00:00", "spools": rows})


def _pending(job):
    return next((r for r in cancel_review_store.list_pending() if r["job_id"] == job), None)


# --- picker-backend-7: a redirect onto a near-empty spool --------------------

def test_a_redirect_onto_a_near_empty_spool_reports_what_it_could_not_take(logs):
    """#98 has 950 g left in the fixture; make it 20 g. A 50 g row redirected
    there charged 20 g and said nothing about the other 30 g."""
    sm = _sm({98: _spool(980.0, "SHELF-A")})
    _cancel_review("J-1300", [{"sid": 97, "toolhead": "RCOI-3", "position": 2, "grams": 50.0}])
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1300",
                         "charges": [{"row": 97, "sid": 98, "grams": 50.0}]})
    assert body["status"] == "confirmed", body
    assert sm.used(98) == pytest.approx(1000.0)
    assert body.get("shortfall_g") == pytest.approx(30.0), body
    assert any("Spool #98 had only 20.0g left" in m for m in _msgs(logs)), _msgs(logs)
    assert any("30.00g of 'f.bgcode' wasn't charged" in m for m in _msgs(logs)), _msgs(logs)


# --- deduct-math-2: a row with a 43.6 attempt baseline ----------------------

def _stamped_review(job, sid=97, before=100.0, grams=2.5):
    _cancel_review(job, [{"sid": sid, "toolhead": "RCOI-3", "position": 2, "grams": grams,
                          "attempt_used_before": before, "attempt_used_after": before + grams}])


def test_a_stamped_row_whose_write_may_have_landed_cannot_be_redirected(logs):
    """#97's earlier write landed (it is at the attempted weight). Moving the
    row to #96 would charge the print twice, once on each spool."""
    sm = _sm()
    sm.spools[97]["used_weight"] = 102.5
    _stamped_review("J-1301")
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1301",
                         "charges": [{"row": 97, "sid": 96, "grams": 2.5}]})
    assert body["status"] == "error" and "earlier write" in body["msg"], body
    assert not sm.patches and _pending("J-1301") is not None


def test_a_stamped_row_whose_write_did_not_land_can_be_redirected(logs):
    """#97 is still at the weight before the attempt: the write never landed,
    so the grams may move, once."""
    sm = _sm()
    _stamped_review("J-1302")
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1302",
                         "charges": [{"row": 97, "sid": 96, "grams": 2.5}]})
    assert body["status"] == "confirmed", body
    assert sm.used(96) == pytest.approx(902.5) and sm.used(97) == 100.0


def test_no_row_merges_into_a_stamped_row(logs):
    """Card [96 stamped, 97]: #97's row redirected onto #96. The retry's landed
    check covers only the 2.5 g the attempt wrote, so a merge either loses #97's
    grams (landed) or charges the stamped grams twice (the other order)."""
    sm = _sm()
    sm.spools[96]["used_weight"] = 902.5          # the stamped write landed
    _cancel_review("J-1303", [
        {"sid": 96, "toolhead": "RCOI-2", "position": 1, "grams": 2.5,
         "attempt_used_before": 900.0, "attempt_used_after": 902.5},
        {"sid": 97, "toolhead": "RCOI-3", "position": 2, "grams": 5.0}])
    for order in ([{"row": 96, "sid": 96, "grams": 2.5}, {"row": 97, "sid": 96, "grams": 5.0}],
                  [{"row": 97, "sid": 96, "grams": 5.0}, {"row": 96, "sid": 96, "grams": 2.5}]):
        body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1303", "charges": order})
        assert body["status"] == "error" and "earlier write" in body["msg"], (order, body)
    assert not sm.patches and sm.used(96) == 902.5


# --- deduct-math-3: the auto-apply's timeout-after-commit hole ---------------

def test_the_auto_apply_counts_a_write_that_landed_but_timed_out(logs):
    sm = WeightWireSpoolman({96: _spool(900.0, "RCOI-2")}, patch_fails={96})
    ctx = _ctx(sm)
    _start(ctx)
    try:
        updated, details, _known = print_deduct._apply_usage_to_printer(INDX, {1: 7.4}, "http://fb")
    finally:
        _stop(ctx)
    assert updated == 1 and details[0]["grams"] == pytest.approx(7.4), details
    assert sm.used(96) == pytest.approx(907.4) and len(sm.patches) == 1
    assert any("write landed" in m for m in _msgs(logs)), _msgs(logs)


# --- deduct-math-4: the shortfall survives a retry ---------------------------

def test_a_retry_still_reports_the_tools_nobody_picked(logs):
    """no_spool usage {T0: 7, T2: 20}; only T0 is picked (-> #96) and its write
    is lost. The retry commits: the 20 g nobody took is still reported, and the
    ledger records what every Apply charged."""
    sm = _sm()
    _no_spool_review(sm, {0: 7.0, 2: 20.0})
    sm.patch_lost.add(96)
    first = _confirm(sm, {"printer_name": INDX, "job_id": "J-1105",
                          "charges": [{"position": 0, "sid": 96, "grams": 7.0}]})
    assert first["status"] == "error", first
    sm.patch_lost.clear()
    second = _confirm(sm, {"printer_name": INDX, "job_id": "J-1105",
                           "updates": {"96": 7.0}})
    assert second["status"] == "confirmed", second
    assert second.get("shortfall_g") == pytest.approx(20.0), second
    assert any("20.00g of" in m and "wasn't charged" in m for m in _msgs(logs)), _msgs(logs)
    entry = print_deduct_ledger._load()[print_deduct_ledger._key(INDX, "J-1105")]
    assert entry["grams"] == pytest.approx(7.0)


# --- deduct-math-5: the auto-split preview's capacity ------------------------

def test_split_rows_use_the_effective_capacity_and_name_the_head(logs):
    """#100 inherits its weight (own initial_weight null, filament 1000 g)."""
    sm = WeightWireSpoolman({100: {"used_weight": 100.0, "initial_weight": None, "archived": False,
                                   "location": "RCOI-2", "filament": {"weight": 1000.0}, "extra": {}}})
    ctx = _ctx(sm)
    _start(ctx)
    try:
        rows = print_deduct._split_to_review_rows(
            {1: [{"sid": 100, "grams": 12.0, "segment": 0, "runout": False}]},
            active_locs=[("RCOI-2", {"position": 1})])
    finally:
        _stop(ctx)
    assert rows[0]["remaining_before"] == 900.0 and rows[0]["remaining_after"] == 888.0, rows
    assert rows[0]["toolhead"] == "RCOI-2", rows


# --- picker-backend-14 / deduct-math-6: archived kept rows -------------------

def test_an_archived_kept_row_does_not_block_a_redirect_and_stays_archived(logs):
    """spool_changed rows: #99 ran out (archived, 0 g left) and #96. Redirecting
    #96's row was refused because #99 is archived; #99's row just clamps."""
    sm = _sm({99: _spool(1000.0, "", archived=True)})
    _cancel_review("J-1304", [
        {"sid": 99, "toolhead": "RCOI-2", "position": 1, "grams": 30.0},
        {"sid": 96, "toolhead": "RCOI-2", "position": 1, "grams": 20.0}])
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1304", "charges": [
        {"row": 99, "sid": 99, "grams": 30.0}, {"row": 96, "sid": 97, "grams": 20.0}]})
    assert body["status"] == "confirmed", body
    assert sm.used(97) == pytest.approx(120.0) and sm.used(99) == 1000.0
    assert sm.spools[99]["archived"] is True


def test_charging_an_archived_spool_does_not_unarchive_it(logs):
    """An archived spool with filament left is charged through the plain Apply:
    update_spool's auto-unarchive read any write leaving remaining > 0 as a
    refill, unarchiving it and putting it back on its old head."""
    sm = WeightWireSpoolman({96: dict(_spool(500.0, "", archived=True),
                                      extra={"fcc_pre_archive_location": "RCOI-2"})})
    _cancel_review("J-1305", [{"sid": 96, "toolhead": "RCOI-2", "position": 1, "grams": 2.5}])
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1305", "updates": {"96": 2.5}})
    assert body["status"] == "confirmed", body
    assert sm.used(96) == pytest.approx(502.5)
    assert sm.spools[96]["archived"] is True and sm.spools[96]["location"] == "", sm.spools[96]


# --- picker-backend-12: the charges path's guards ----------------------------

def test_a_non_finite_pick_is_refused_and_the_review_kept(logs):
    sm = _sm()
    _no_spool_review(sm, {0: 10.0})
    ctx = _ctx(sm)
    _start(ctx)
    try:
        r = app_module.app.test_client().post(
            "/api/cancel_deduct/confirm", content_type="application/json",
            data='{"printer_name": "%s", "job_id": "J-1105", '
                 '"charges": [{"position": 0, "sid": 96, "grams": Infinity}]}' % INDX)
    finally:
        _stop(ctx)
    assert r.status_code == 200 and r.get_json()["status"] == "error", r.get_data(as_text=True)
    assert not sm.patches and _pending("J-1105") is not None


def test_charges_for_a_job_the_ledger_already_settled_are_already_handled(logs):
    sm = _sm()
    _no_spool_review(sm, {0: 10.0})
    print_deduct_ledger.record_deduct(INDX, "J-1105", filename="x", scale=1.0, grams=10.0)
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1105",
                         "charges": [{"position": 0, "sid": 96, "grams": 10.0}]})
    assert body["status"] == "already_handled", body
    assert not sm.patches


# --- picker-backend-15: a typo'd #id -----------------------------------------

def test_a_typod_spool_id_is_refused_and_the_review_kept_as_it_was(logs):
    sm = _sm()
    _no_spool_review(sm, {0: 61.32})
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1105",
                         "charges": [{"position": 0, "sid": 9996, "grams": 61.32}]})
    assert body["status"] == "error" and "wasn't found" in body["msg"], body
    assert not sm.patches
    rec = _pending("J-1105")
    assert rec["kind"] == "no_spool" and rec.get("usage_map"), rec


# --- picker-frontend-18 (backend half): a stale card ------------------------

def test_an_apply_naming_only_spools_outside_the_review_keeps_it(logs):
    """After a failed redirect the review's rows are the picked spools; a stale
    card that sends the old row's sid used to drop the review with no log."""
    sm = _sm()
    _cancel_review("J-1306", [{"sid": 96, "toolhead": "RCOI-3", "position": 2, "grams": 2.5}])
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1306", "updates": {"97": 2.5}})
    assert body["status"] == "error", body
    assert _pending("J-1306") is not None, "the review was dropped"
    assert any("Review kept" in m for m in _msgs(logs)), _msgs(logs)
    assert not sm.patches


# --- logs-and-tests-30: the head in a picked spool's log line ----------------

def test_a_no_spool_picks_log_line_names_the_head_not_the_spools_shelf(logs):
    sm = _sm()
    _no_spool_review(sm, {1: 20.0})           # T1 = RCOI-2 at print end
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1105",
                         "charges": [{"position": 1, "sid": 98, "grams": 20.0}]})
    assert body["status"] == "confirmed", body
    line = next(m for m in _msgs(logs) if "Spool #98" in m and "cancel-deduct" in m)
    assert line.startswith(f"✔️ {INDX} RCOI-2: "), line
    assert "SHELF-A" not in line


def test_a_redirected_rows_log_line_names_the_head_the_print_used(logs):
    sm = _sm()
    _cancel_review("J-1307", [{"sid": 97, "toolhead": "RCOI-3", "position": 2, "grams": 2.5}])
    _confirm(sm, {"printer_name": INDX, "job_id": "J-1307",
                  "charges": [{"row": 97, "sid": 98, "grams": 2.5}]})
    line = next(m for m in _msgs(logs) if "Spool #98" in m and "cancel-deduct" in m)
    assert line.startswith(f"✔️ {INDX} RCOI-3: "), line
