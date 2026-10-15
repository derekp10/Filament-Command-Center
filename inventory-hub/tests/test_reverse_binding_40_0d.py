"""Group 40.0d — the 13.6 reverse-binding records a "came from" slot only when
exactly one free bound slot feeds the head, and says which one.

When a spool lands on a toolhead with no meaningful source (a toolhead-QR scan of
a spare), the engine records a box slot that feeds that head as its home, so the
box card lists it and Return knows where it goes. It used to take the FIRST
unclaimed bound slot in locations.json order. Derek's D3 rule, "one is
pre-selected only when exactly one free option exists", applied to this silent
choice: with two free slots feeding the head it records nothing (INFO "not
guessing"), and a recorded slot comes back as `recorded_source` for the scan
toast. Claimed slots are read strictly, through the one slot rule (42.2's
effective_slot): a Spoolman blip read every slot as free. Single-slot boxes are
never candidates (42.1 step 5, pinned in test_single_slot_box_lifecycle.py).

The real engine runs over move_engine_harness's fakes and a live locations store.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, LocationsStore, run_move  # noqa: E402

XL = "🦝 XL"
PRINTER_MAP = {f"XL-{n}": {"printer_name": XL, "position": n - 1} for n in (1, 2)}
BASE = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2)]},
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "LR"},
]


def _box(box, targets, max_spools="4"):
    return {"LocationID": box, "Type": "Dryer Box", "Max Spools": max_spools, "parent_id": "LR",
            "extra": {"slot_targets": targets}}


ONE_FEED = BASE + [_box("LR-MDB-1", {"1": "XL-1", "2": "XL-2"}), _box("TST-MDB-1", {})]
TWO_FEEDS = BASE + [_box("LR-MDB-1", {"1": "XL-1"}), _box("TST-MDB-1", {"2": "XL-1"})]


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(state, "GLOBAL_BUFFER", [])


class _BoxBlip(FakeSpoolman):
    """Spoolman can't list one box: the strict reader raises, and the fail-open
    reader answers [] (it swallows the error)."""
    blind_box = ""

    def at_location_detailed_strict(self, loc):
        if str(loc).upper() == self.blind_box:
            raise logic.spoolman_api.requests.ConnectionError("Spoolman unreachable (test)")
        return super().at_location_detailed_strict(loc)

    def at_location_detailed(self, loc):
        if str(loc).upper() == self.blind_box:
            return []
        return super().at_location_detailed(loc)


def _scan_spare(rows, sm=None):
    """#42, Unassigned (no meaningful "came from"), is scanned onto XL-1. A spool
    coming from a cart or box keeps that as its trail and never reaches 13.6."""
    sm = sm or FakeSpoolman({})
    sm.spools.setdefault(42, {"location": "", "extra": {}})
    res = run_move(sm, probe=IDLE, store=LocationsStore(rows), printer_map=PRINTER_MAP,
                   target="XL-1", raw_spools=[42])
    assert logic.smart_move_failure(res, 42) == "", res
    assert sm.direct_at("XL-1") == [42]
    return res, sm.spools[42]["extra"]


def _trail(extra):
    return (str(extra.get("physical_source") or ""), str(extra.get("physical_source_slot") or ""))


def test_one_free_feed_is_recorded_and_named():
    res, extra = _scan_spare(ONE_FEED)
    assert _trail(extra) == ("LR-MDB-1", "1")
    assert res.get("recorded_source") == "LR-MDB-1:1", res


def test_two_free_feeds_record_nothing():
    """It used to take LR-MDB-1 slot 1 because that row comes first in the file."""
    res, extra = _scan_spare(TWO_FEEDS)
    assert _trail(extra) == ("", ""), extra
    assert "recorded_source" not in res, res


def test_a_feed_another_spool_holds_is_not_free():
    sm = FakeSpoolman({9: {"location": "TST-MDB-1", "extra": {"container_slot": "2"}}})
    res, extra = _scan_spare(TWO_FEEDS, sm)
    assert _trail(extra) == ("LR-MDB-1", "1") and res.get("recorded_source") == "LR-MDB-1:1", res


def test_a_feed_whose_own_spool_is_deployed_elsewhere_is_not_free():
    """#5 left LR-MDB-1 slot 1 for XL-2 and still claims it (its trail)."""
    sm = FakeSpoolman({5: {"location": "XL-2", "extra": {"physical_source": "LR-MDB-1",
                                                         "physical_source_slot": "1"}}})
    res, extra = _scan_spare(TWO_FEEDS, sm)
    assert _trail(extra) == ("TST-MDB-1", "2") and res.get("recorded_source") == "TST-MDB-1:2", res


def test_a_box_fcc_cant_read_is_never_guessed_free():
    """The fail-open read answered [] on a blip, so a slot another spool holds
    looked free and the spare took it: two spools claiming one slot."""
    sm = _BoxBlip({7: {"location": "LR-MDB-1", "extra": {"container_slot": "1"}}})
    sm.blind_box = "LR-MDB-1"
    res, extra = _scan_spare(ONE_FEED, sm)
    assert _trail(extra) == ("", ""), extra
    assert "recorded_source" not in res, res


def test_a_spool_arriving_from_a_box_keeps_its_own_trail():
    """Control: 13.6 runs only when the spool brings no meaningful source."""
    sm = FakeSpoolman({42: {"location": "TST-MDB-1", "extra": {"container_slot": "3"}}})
    res, extra = _scan_spare(ONE_FEED, sm)
    assert _trail(extra) == ("TST-MDB-1", "3")
    assert "recorded_source" not in res, res
