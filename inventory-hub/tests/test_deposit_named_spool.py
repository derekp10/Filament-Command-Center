"""Group 46 review: the Quick-Swap deposit writes the spool its confirm NAMED.

quickSwapDeposit names the buffered spool in its confirm overlay and toast, but
the LOC:<box>:SLOT:<n> scan path it posts used to deposit the FIRST spool of
state.GLOBAL_BUFFER, the replica the client persists asynchronously. The overlay
waits up to 3 s on the printer probe with the carousel still clickable, so a
rotate during that wait made it deposit a different spool from the one it named
(the 46.1 symptom on the Quick-Swap grid). The deposit now sends `spool_id` and
the route deposits exactly that spool. A plain scan names no spool and keeps the
buffer's first.

The engine is spied, not run: these pin WHICH spool the route hands it.
HEAD proof: without the fix the route ignores `spool_id` and moves #1.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import locations_db  # noqa: E402
import logic  # noqa: E402
import state  # noqa: E402

ROWS = [{"LocationID": "FCC-BOX", "Type": "Dryer Box", "Max Spools": "4", "Name": "FCC Box"}]


@pytest.fixture
def moves(monkeypatch):
    calls = []
    monkeypatch.setattr(locations_db, "load_locations_list", lambda: [dict(r) for r in ROWS])
    monkeypatch.setattr(logic, "perform_smart_move",
                        lambda target, spools, **kw: calls.append((target, list(spools), kw)) or {"status": "success"})
    monkeypatch.setattr(state, "add_log_entry", lambda *a, **k: None)
    prior = state.GLOBAL_BUFFER
    state.GLOBAL_BUFFER = [{"id": 1, "display": "#1"}, {"id": 2, "display": "#2"}]
    yield calls
    state.GLOBAL_BUFFER = prior


def _scan(**extra):
    body = {"text": "LOC:FCC-BOX:SLOT:2", "source": "quickswap_deposit", **extra}
    return app_module.app.test_client().post("/api/identify_scan", json=body)


def test_a_named_spool_is_the_one_deposited(moves):
    r = _scan(spool_id=2)
    body = r.get_json()
    assert r.status_code == 200 and body["action"] == "assignment_partial", body
    assert moves[0][1] == [2], f"deposited {moves[0][1]}, the confirm named #2"
    assert body["moved"] == 2
    assert [s["id"] for s in state.GLOBAL_BUFFER] == [1]


def test_a_named_spool_missing_from_the_replica_is_still_the_one_deposited(moves):
    """The replica can lag the client (a persist in flight); the user confirmed #7."""
    r = _scan(spool_id=7)
    assert r.get_json()["moved"] == 7 and moves[0][1] == [7]
    assert [s["id"] for s in state.GLOBAL_BUFFER] == [1, 2]


def test_a_scan_that_names_no_spool_keeps_the_buffers_first(moves):
    r = _scan()
    assert r.get_json()["moved"] == 1 and moves[0][1] == [1]


@pytest.mark.parametrize("bad", ["abc", -3, 0, "ID:"])
def test_a_bad_spool_id_is_refused_not_guessed(moves, bad):
    r = _scan(spool_id=bad)
    assert r.status_code == 400 and r.get_json()["action"] == "assignment_failed"
    assert not moves, "a bad spool id must not fall back to the buffer's first spool"
