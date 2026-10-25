"""Group 49.2b at the merge: a 🛑 Review Apply warns like an automatic deduct.

A cancelled print (or a finished one with a mid-print swap) is charged through
Review -> Apply (print_deduct.api_cancel_deduct_confirm), which writes its own
ledger entry, so the builder's hook in _record_applied_deduct never saw it: a
reviewed charge that took a filament under the line logged nothing. Each Apply
charge now also says whether its spool was archived (Derek's 43.2: an archived
pick is charged what it has and stays archived), so a spool archived by hand is
never read as the filament running out.

Real route and deduct code against the 49 builder's fake Spoolman (the `env`
fixture of test_low_stock_warning.py). Before the hook: the first test fails
(no warning); with the hook but no `was_archived`, the second does ("out").
"""
from __future__ import annotations

import app as app_module
import cancel_review_store
import print_deduct
import spoolman_api
from test_low_stock_warning import _galaxy, _stock_warnings, env  # noqa: F401  (env: the fixture)


def _review(job, rows):
    cancel_review_store.add_pending({
        "printer_name": "XL", "job_id": job, "filename": "part.gcode", "progress": 0.5,
        "total_grams": sum(g for _sid, _th, g in rows), "ambiguous": False, "created": "2026-10-19 00:00:00",
        "spools": [{"sid": sid, "toolhead": th, "position": i, "grams": g} for i, (sid, th, g) in enumerate(rows)]})


def _apply(job, charges):
    return app_module.app.test_client().post(
        "/api/cancel_deduct/confirm", json={"printer_name": "XL", "job_id": job, "charges": charges}).get_json()


def test_a_review_apply_that_takes_a_filament_under_the_line_warns_once(env):
    fake = _galaxy(env, (1, 160, "XL-1"), (2, 140, "SHELF-A"))
    _review("J-R1", [(1, "XL-1", 80)])
    body = _apply("J-R1", [{"row": 1, "sid": 1, "grams": 80}])
    assert body["status"] == "confirmed", body
    assert fake.remaining(1) == 80
    assert [m for m, _ in _stock_warnings(env["logs"])] == [
        "⚠️ Prusament PLA Galaxy Black is running low: 220 g left in 2 spools"], env["logs"]


def test_an_archived_pick_never_reads_as_the_filament_running_out(env):
    """#1 was archived by hand with 50 g left (no stock); Review charges it its
    50 g and it stays archived. The filament had nothing in stock before or
    after, so nothing ran out: no warning."""
    fake = _galaxy(env, (1, 50, "", True))
    _review("J-R2", [(1, "XL-1", 50)])
    body = _apply("J-R2", [{"row": 1, "sid": 1, "grams": 50}])
    assert body["status"] == "confirmed", body
    assert fake.spools[1]["archived"] is True and fake.remaining(1) == 0
    assert [a.get("was_archived") for a in body["applied"]] == [True], body["applied"]
    assert _stock_warnings(env["logs"]) == [], env["logs"]


def test_a_retry_of_a_charge_that_landed_still_says_the_filament_is_out(env):
    """Review engine-4: the first Apply's PATCH landed (archiving #1, the
    filament's last spool, at 0 g) but its answer timed out and the re-read
    failed, so the row was queued again with the attempt (43.6). The retry
    finds the write landed and counts it once, but read `was_archived` from the
    record the attempt itself had archived: "is out" was never said. RED on
    a5d8cb8."""
    fake = _galaxy(env, (1, 30, "XL-1"))
    _review("J-R3", [(1, "XL-1", 30)])
    mp = env["monkeypatch"]
    real_update, real_read = spoolman_api.update_spool, print_deduct._spool_read
    wrote = []

    def timed_out(sid, data, *a, **k):
        real_update(sid, data, *a, **k)            # Spoolman applies it...
        wrote.append(sid)
        return None                                # ...but the answer never comes

    def read(sid):
        return None if wrote else real_read(sid)   # and the re-read after it fails too

    mp.setattr(spoolman_api, "update_spool", timed_out)
    mp.setattr(print_deduct, "_spool_read", read)
    first = _apply("J-R3", [{"row": 1, "sid": 1, "grams": 30}])
    assert first["status"] != "confirmed" and not first.get("applied"), first
    assert fake.spools[1]["archived"] is True and fake.remaining(1) == 0
    [row] = cancel_review_store.get_pending("XL", "J-R3")["spools"]
    assert row["attempt_used_after"] == 1000.0 and row["attempt_was_archived"] is False, row
    assert _stock_warnings(env["logs"]) == [], env["logs"]

    mp.setattr(spoolman_api, "update_spool", real_update)
    mp.setattr(print_deduct, "_spool_read", real_read)
    again = _apply("J-R3", [{"row": 1, "sid": 1, "grams": 30}])
    assert again["status"] == "confirmed", again
    assert [(a["grams"], a["was_archived"]) for a in again["applied"]] == [(30.0, False)], again["applied"]
    assert [m for m, _ in _stock_warnings(env["logs"])] == [
        "⚠️ Prusament PLA Galaxy Black is out: #1 was its last spool in stock"], env["logs"]
