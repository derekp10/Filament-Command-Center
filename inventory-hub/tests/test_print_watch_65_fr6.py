"""Group 65 fix review, round 6: a cancel or reset at a park whose read landed only on a retry.
Offline, over the fetch-off-watcher rig (the real edges, review and card; only the download
is stubbed).

  - WU1 (red): the card such an end opens says where its heads were read ("when FCC first read
    its heads at the park, a while after the printer paused"), each row it names says it may
    not be the spool that printed this, and the Activity Log warns, as a resume does. It said
    "when the printer paused" with the spool loaded at the prompt pre-picked, and nothing
    warned.

Red on 04ce498f (fix review 5's fixes).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

import cancel_review_store
import print_deduct
from test_fetch_off_watcher_hotfix import _isolated, logs, Rig, _tick, _job, XL  # noqa: F401
from test_print_watch_65_fr4 import _rigged


@pytest.mark.parametrize("end", ["STOPPED", "IDLE"])
def test_an_end_at_a_park_whose_read_came_late_says_so(logs, end):
    rig = Rig()
    snap, dl = _rigged(rig)
    reads = {"n": 0}

    def _flaky(*a, **k):
        reads["n"] += 1
        return None if reads["n"] == 1 else rig._capture(*a, **k)
    with rig, snap, dl, patch.object(print_deduct, "_capture_print_heads", side_effect=_flaky):
        _tick(XL, "IDLE", None)
        _tick(XL, "ATTENTION", _job(0.45, job_id=8, filename="y.gcode"))    # the park read hits a blip
        rig.on["XL-1"] = 200                                              # a Quick-Swap at the prompt
        _tick(XL, "ATTENTION", _job(0.45, job_id=8, filename="y.gcode"))    # the retry reads #200
        _tick(XL, end, None)                                              # cancelled, or reset
    card = cancel_review_store.get_pending(XL, "8") or {}
    assert card.get("heads_source") == "park_late", card
    assert (card.get("heads_words") or {}).get("end", "").startswith("when FCC first read its heads at the park"), card
    assert "isn't the one that printed this" in (card.get("row_notes") or {}).get("200", ""), card
    said = [m for m in logs if "only after it first saw the print parked" in m and "🛑 card" in m]
    assert len(said) == 1 and "T0 #200" in said[0], logs
