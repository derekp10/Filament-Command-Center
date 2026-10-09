"""A failed attribute-restore must NAME its casualty and log the recovery data.

Background (2026-08-05 — real data loss, found on Derek's dev container):
  `remove_choice` and `sweep_unused` cannot delete a single choice from a
  Spoolman `choice` field, so they run a force_reset: snapshot every
  attribute-bearing filament's FULL `extra`, DELETE the field, recreate it, then
  PATCH all ~150 records back. If one restore PATCH fails, that filament's
  extras are gone — the field was already wiped and nothing retries.

  The only trace was a COUNT: "restored 151/152 … 1 restore failure(s)". The
  filament id appeared nowhere, in the Activity Log or hub.log. So the loss was
  both silent and unattributable, and 26 filaments in dev drained over months
  before anyone noticed. Recovering them required diffing against prod.

This pins the mitigation: every casualty is logged at ERROR with the snapshot
payload we failed to write back (that payload IS the recovery data), and the
Activity-Log line names the ids instead of just counting them.

Pure unit tests on the helper — driving a genuine mid-migration failure against
a live Spoolman would mean deliberately destroying real records.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import routes_config_attrs as rca


SNAPSHOT = {
    55: {"filament_attributes": '["Basic"]', "product_url": '"http://x/55"'},
    63: {"filament_attributes": '["Blend"]', "original_color": '"Azure"'},
    99: {"filament_attributes": '["Glow"]'},
}


def test_no_failures_logs_nothing_and_returns_no_ids():
    with patch.object(rca.state, "logger") as log:
        ids = rca._report_restore_failures("op", [], SNAPSHOT)
    assert ids == []
    log.error.assert_not_called()


def test_each_casualty_is_named():
    failures = [
        {"id": 63, "msg": "HTTP 500: boom"},
        {"id": 99, "msg": "ConnectionError"},
    ]
    with patch.object(rca.state, "logger") as log:
        ids = rca._report_restore_failures("remove_choice('Blend')", failures, SNAPSHOT)

    assert ids == [63, 99], "the caller needs the ids for its Activity-Log line"
    assert log.error.call_count == 2, "every casualty must be logged, not just the first"


def test_the_log_carries_the_recovery_payload():
    """Without the snapshot payload the log says what was lost but not what it
    WAS — which is the difference between recoverable and gone."""
    failures = [{"id": 63, "msg": "HTTP 500: boom"}]
    with patch.object(rca.state, "logger") as log:
        rca._report_restore_failures("sweep_unused(['X'])", failures, SNAPSHOT)

    msg = log.error.call_args[0][0]
    assert "#63" in msg
    assert "Blend" in msg, "the lost filament_attributes value is missing"
    assert "Azure" in msg, "sibling extras are lost too and must be recoverable"
    assert "HTTP 500: boom" in msg, "the underlying failure reason is missing"
    assert "sweep_unused" in msg, "the operation that caused it is missing"


def test_a_missing_snapshot_entry_still_logs():
    """Never swallow a casualty just because its snapshot is absent —
    an unattributable loss is exactly the failure mode being fixed."""
    failures = [{"id": 4242, "msg": "gone"}]
    with patch.object(rca.state, "logger") as log:
        ids = rca._report_restore_failures("op", failures, SNAPSHOT)
    assert ids == [4242]
    assert log.error.call_count == 1
    assert "#4242" in log.error.call_args[0][0]


def test_an_unserialisable_snapshot_does_not_suppress_the_log():
    """The recovery payload is best-effort; losing it must not lose the ALERT."""
    class _Weird:
        def __repr__(self):
            return "<weird-extras>"

    failures = [{"id": 7, "msg": "boom"}]
    with patch.object(rca.state, "logger") as log:
        ids = rca._report_restore_failures("op", failures, {7: _Weird()})
    assert ids == [7]
    msg = log.error.call_args[0][0]
    assert "#7" in msg and "weird-extras" in msg


def test_payload_is_bounded():
    """A 150-record migration must not write an unbounded blob per casualty."""
    huge = {"filament_attributes": json.dumps(["x" * 50] * 500)}
    failures = [{"id": 1, "msg": "boom"}]
    with patch.object(rca.state, "logger") as log:
        rca._report_restore_failures("op", failures, {1: huge})
    assert len(log.error.call_args[0][0]) < 6000


def test_both_destructive_endpoints_use_the_helper():
    """Source pin: neither endpoint may report a bare count again."""
    src = (rca.__file__ or "")
    from pathlib import Path
    text = Path(src).read_text(encoding="utf-8", errors="replace")
    assert text.count("_report_restore_failures(") >= 3, (
        "expected the helper definition plus a call in BOTH remove_choice and "
        "sweep_unused — a destructive path is reporting failures without naming them"
    )
    assert "restore failure(s)" not in text, (
        "an endpoint is still emitting the old count-only wording, which is what "
        "made this loss unattributable"
    )
