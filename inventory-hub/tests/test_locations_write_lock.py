"""Group 38 follow-up — locations.json write serialization.

Every mutator of locations.json is a whole-file READ-MODIFY-WRITE:

    loc_list = load_locations_list()   →   mutate   →   save_locations_list(loc_list)

There was no lock anywhere in `locations_db.py`, and Flask runs threaded. Two
overlapping writers therefore LOSE UPDATES — the second one's save carries a
snapshot taken before the first one's write, silently reverting it, while both
callers get a success response.

That is not hypothetical: it was the Group 38.6a flake. One "Save Feeds" click
fired the slot_order PUT and the bindings PUT in the same tick, and
`set_dryer_box_slot_order` copies the ENTIRE `extra` dict (slot_targets
included), so whichever landed second reverted the other — while the UI showed
"✅ Saved". Captured traceback: `assert 'XL-1' == 'XL-2'`.

These tests are hermetic (they patch the module's IO, touch no container and no
NAS) so they run under `--offline`.

⚠️ MUTATION CHECK — these are worthless if they pass without the fix. To verify,
remove the `with locations_write_lock():` from `set_dryer_box_slot_order` and
`attach_single_slot_box_to_toolhead`; `test_concurrent_writers_do_not_lose_updates`
must go RED. The `_load` delay below exists precisely to make that failure
deterministic rather than a coin flip.
"""
from __future__ import annotations

import copy
import os
import sys
import threading
import time
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import locations_db  # noqa: E402


# Two DIFFERENT rows, mutated by two different writers. Deliberately avoids
# `set_dryer_box_bindings` so the test doesn't depend on validate_slot_targets'
# printer_map rules — the race is a property of the whole-file read-modify-write,
# not of any particular validator.
FAKE_ROWS = [
    {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "4", "extra": {}},
    {"LocationID": "PM-DB-9", "Type": "Dryer Box", "Max Spools": "1", "extra": {}},
]


def _install_slow_store(store, read_delay=0.05):
    """Patch locations_db IO with an in-memory store whose READ is slow.

    The delay widens the read→write window so that, without serialization, the
    two writers are guaranteed to overlap. With the lock held across the whole
    cycle the second writer simply waits, so the delay costs the test ~0.1s and
    changes nothing about what it asserts.
    """
    def _load():
        rows = copy.deepcopy(store["rows"])
        time.sleep(read_delay)
        return rows

    def _save(rows):
        store["rows"] = copy.deepcopy(rows)
        return True  # mirror the real contract (True on a verified write)

    return patch.object(locations_db, "load_locations_list", side_effect=_load), \
        patch.object(locations_db, "save_locations_list", side_effect=_save)


def _extra_for(store, loc_id):
    for row in store["rows"]:
        if row.get("LocationID") == loc_id:
            return row.get("extra") or {}
    return {}


def test_concurrent_writers_do_not_lose_updates():
    """Two mutators racing on locations.json must BOTH survive.

    Without the write lock this fails deterministically: both threads read the
    same snapshot, each mutates its own row, and whichever saves last writes
    back a copy that never contained the other's change.
    """
    store = {"rows": copy.deepcopy(FAKE_ROWS)}
    start = threading.Barrier(2)
    errors = []

    def _order():
        try:
            start.wait(timeout=5)
            locations_db.set_dryer_box_slot_order("PM-DB-1", "rtl")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def _attach():
        try:
            start.wait(timeout=5)
            locations_db.attach_single_slot_box_to_toolhead("PM-DB-9", "XL-1")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    p_load, p_save = _install_slow_store(store)
    with p_load, p_save:
        threads = [threading.Thread(target=_order), threading.Thread(target=_attach)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        assert not any(t.is_alive() for t in threads), (
            "a writer thread did not finish — a deadlock would look exactly like this"
        )

    assert not errors, f"writer raised: {errors}"

    # BOTH mutations must be on disk. Exactly one surviving is the lost update.
    assert _extra_for(store, "PM-DB-1").get("slot_order") == "rtl", (
        "the slot_order write was lost — the other writer's stale snapshot "
        "reverted it (this is the Group 38.6a mechanism)"
    )
    assert _extra_for(store, "PM-DB-9").get("slot_targets") == {"1": "XL-1"}, (
        "the single-slot attach was lost — the other writer's stale snapshot "
        "reverted it (this is the Group 38.6a mechanism)"
    )


def test_write_lock_is_reentrant():
    """A locked mutator must be able to call another one without deadlocking.

    `logic.perform_smart_move` already calls `attach_single_slot_box_to_toolhead`,
    so nesting is reachable in production. A plain `threading.Lock` here would
    self-deadlock; the module uses an RLock.
    """
    store = {"rows": copy.deepcopy(FAKE_ROWS)}
    p_load, p_save = _install_slow_store(store, read_delay=0)
    with p_load, p_save:
        with locations_db.locations_write_lock():
            with locations_db.locations_write_lock():
                ok, _ = locations_db.set_dryer_box_slot_order("PM-DB-1", "rtl")
    assert ok is True
    assert _extra_for(store, "PM-DB-1").get("slot_order") == "rtl"


def test_slot_order_reports_failure_when_the_save_is_refused():
    """A refused write must surface as a failure, not a cheerful success.

    `save_locations_list` returns False on the orphan guard, an atomic-write
    exception, or an unrecovered verify-after-write. `set_dryer_box_slot_order`
    used to discard that boolean and `return True, None` regardless — which is
    how "✅ Saved" came to be displayed over an unchanged file.
    """
    store = {"rows": copy.deepcopy(FAKE_ROWS)}

    with patch.object(locations_db, "load_locations_list",
                      side_effect=lambda: copy.deepcopy(store["rows"])), \
         patch.object(locations_db, "save_locations_list", return_value=False):
        ok, msg = locations_db.set_dryer_box_slot_order("PM-DB-1", "rtl")

    assert ok is False, "a refused save must not be reported as success"
    assert msg and "save failed" in msg.lower()
