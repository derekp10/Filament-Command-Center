"""Group 41.4 — Undo Last Move asks first and says what it really did.

Derek, 2026-10-13: "the issue here boils down to Undo on the UI not being
specific on what it does in the first place … I'm thinking we change it to
'Undo Last Move'". So Undo always asks first, naming the move it will reverse
("Undo: put #57 back in LR-MDB-1 slot 2 and #196 back on XL-2?"), printing or
not; a printing head is called out (D6); the Yes must quote the record's number
(the stack is shared by every tab); it is off while a bulk move is armed; it
reports only what went back; and a move whose writes never landed records
nothing to undo.

The real move engine and the real /api/undo route run against
tests/move_engine_harness.py's FakeSpoolman.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, _probe_for, run_move  # noqa: E402

PRINTER = "🦝 XL"
PRINTER_MAP = {"XL-2": {"printer_name": PRINTER, "position": 1}}
LOCATIONS = [
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4"},
    {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1"},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0"},
]
QUESTION = "Undo: put #57 back in LR-MDB-1 slot 2 and #196 back on XL-2?"


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def fresh_stack(monkeypatch):
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(state, "BULK_MOVE_SESSION", {"active": False})


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a)))
    return calls


def _sm(**kw):
    return FakeSpoolman({
        57: {"location": "LR-MDB-1", "extra": {"container_slot": "2"}},
        196: {"location": "XL-2", "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "3"}},
    }, **kw)


def _swap(sm, probe=IDLE):
    """#57 onto XL-2; Smart Load sends its resident #196 home to LR-MDB-1 slot 3."""
    res = run_move(sm, probe=probe, locations=LOCATIONS, printer_map=PRINTER_MAP,
                   target="XL-2", raw_spools=[57])
    assert logic.smart_move_failure(res, 57) == "", res
    assert sm.spools[57]["location"] == "XL-2" and sm.spools[196]["location"] == "LR-MDB-1"
    return state.UNDO_STACK[-1]


def _undo(sm, client, body=None, probe=IDLE):
    return run_move(sm, probe=probe, locations=LOCATIONS, printer_map=PRINTER_MAP,
                    call=lambda: client.post("/api/undo", json=body or {})).get_json()


def test_a_press_asks_first_naming_the_move_and_writes_nothing(client, logs):
    """FAILS on the old route: /api/undo reverted at once, unasked."""
    sm = _sm()
    record = _swap(sm)
    writes = len(sm.writes)
    ask = _undo(sm, client)
    assert ask["requires_confirm"] is True and ask["msg"] == QUESTION, ask
    assert ask["undo_id"] == record["id"] and ask["active_prints"] == []
    assert len(sm.writes) == writes, "the question wrote"
    assert state.UNDO_STACK == [record]


def test_the_yes_puts_both_spools_back_and_says_so(client, logs):
    sm = _sm()
    record = _swap(sm)
    done = _undo(sm, client, {"confirm": True, "undo_id": record["id"]})
    assert done["success"] is True, done
    assert sm.spools[57]["location"] == "LR-MDB-1" and sm.spools[57]["extra"]["container_slot"] == "2"
    assert sm.spools[196]["location"] == "XL-2"
    assert done["msg"] == ("↩️ Undo: #57 is back in LR-MDB-1 slot 2 (it had been moved to XL-2); "
                           "#196 is back on XL-2"), done
    assert (done["msg"], ("WARNING",)) in logs
    assert state.UNDO_STACK == []


def test_a_yes_for_a_move_that_is_no_longer_on_top_is_refused(client, logs):
    """FAILS on the old route (it took no id): another tab's move landed on top
    after the question, and the Yes undid that move instead."""
    sm = _sm()
    record = _swap(sm)
    newer = {"target": "CR-CT-2-R1", "moves": {}, "ejections": {}, "summary": "Moved 1 -> CR-CT-2-R1"}
    logic._push_undo(newer)
    writes = len(sm.writes)
    done = _undo(sm, client, {"confirm": True, "undo_id": record["id"]})
    assert done["success"] is False and done["stale"] is True, done
    assert len(sm.writes) == writes and state.UNDO_STACK == [record, newer]


def test_nothing_to_undo_is_said_and_logged(client, logs):
    """FAILS on the old route: "Nothing to undo" wrote no Activity Log line."""
    done = _undo(_sm(), client)
    assert done["success"] is False and done["nothing"] is True, done
    assert "moves only" in done["msg"]
    assert any(m.startswith("↩️ Nothing to undo") and a[0] == "INFO" for m, a in logs), logs


def test_undo_is_off_while_a_bulk_move_is_armed(client, logs, monkeypatch):
    """Claude's call 9: the bulk-move panel would hide the prompt."""
    sm = _sm()
    _swap(sm)
    monkeypatch.setattr(state, "BULK_MOVE_SESSION", {"active": True})
    writes = len(sm.writes)
    done = _undo(sm, client)
    assert done["success"] is False and "bulk move is armed" in done["msg"], done
    assert "requires_confirm" not in done and len(sm.writes) == writes


def test_a_printing_head_is_called_out_and_its_yes_must_name_it(client, logs):
    """D6 for Undo: XL starts printing after the swap. The question calls out
    XL-2; a Yes that doesn't carry XL-2 is asked again, writing nothing."""
    sm = _sm()
    record = _swap(sm)
    printing = _probe_for({PRINTER})
    ask = _undo(sm, client, probe=printing)
    assert [a["toolhead"] for a in ask["active_prints"]] == ["XL-2"], ask
    assert "is PRINTING" in ask["msg"] and ask["msg"].endswith(QUESTION), ask
    writes = len(sm.writes)
    again = _undo(sm, client, {"confirm": True, "undo_id": record["id"]}, probe=printing)
    assert again.get("requires_confirm") is True and len(sm.writes) == writes, again
    done = _undo(sm, client, {"confirm": True, "undo_id": record["id"],
                              "confirmed_toolheads": ["XL-2"]}, probe=printing)
    assert done["success"] is True and sm.spools[196]["location"] == "XL-2", done


def test_a_paused_printer_gets_the_plain_question(client, logs):
    sm = _sm()
    _swap(sm)

    def paused(_url, printer_name):
        return {"state": "PAUSED", "is_active": False}

    ask = _undo(sm, client, probe=paused)
    assert ask["msg"] == QUESTION and ask["active_prints"] == [], ask


def test_a_move_that_never_landed_records_nothing_to_undo(logs):
    """FAILS on the old engine: the record was pushed even when every write of
    the move had been rejected, so Undo "restored" a spool that never moved."""
    sm = FakeSpoolman({57: {"location": "LR-MDB-1", "extra": {}}}, reject_ids=[57])
    res = run_move(sm, probe=IDLE, locations=LOCATIONS, printer_map=PRINTER_MAP,
                   target="CR-CT-2-R1", raw_spools=[57])
    assert logic.smart_move_failure(res, 57), res
    assert state.UNDO_STACK == []


def test_a_rejected_restore_is_reported_not_logged_as_undone(client, logs):
    """FAILS on the old engine: "↩️ Undid: …" was logged and success answered
    even when Spoolman rejected every restore write."""
    sm = _sm()
    record = _swap(sm)
    sm.reject_ids = {57, 196}
    done = _undo(sm, client, {"confirm": True, "undo_id": record["id"]})
    assert done["success"] is False and "#57" in done["msg"] and "#196" in done["msg"], done
    assert not [m for m, _ in logs if m.startswith("↩️ Undo:")], logs
    assert any(m.startswith("⚠️ Undo partly failed") and a[0] == "ERROR" for m, a in logs), logs


def test_the_ui_calls_it_undo_last_move():
    """Claude's call 8: the deck tile reads UNDO MOVE, and the shortcut list and
    tooltip say Undo Last Move (the scan code CMD:UNDO is unchanged, so printed
    labels keep working). Pinned as text: the visual harness's 1% tolerance
    would let the old label through."""
    hub = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    with open(os.path.join(hub, "templates", "dashboard.html"), encoding="utf-8") as fh:
        dashboard = fh.read()
    with open(os.path.join(hub, "static", "js", "modules", "shortcuts_registry.js"), encoding="utf-8") as fh:
        shortcuts = fh.read()
    assert '<div class="deck-label text-warning">UNDO MOVE</div>' in dashboard
    assert 'title="Undo Last Move' in dashboard
    assert "description: 'Undo Last Move" in shortcuts and "keys: ['CMD:UNDO']" in shortcuts
