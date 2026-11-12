"""Hotfix round 2, R2 (Derek's picture check, 2026-11-12): the line a 🛑 Review's
Apply logs for the grams it leaves uncharged names each head and the spools FCC
saw there.

Derek: "My guess is ... it's lost, except for probably a note about xx grams not
being deducted from Spool X or spool Y that were on the same toolhead during the
print."

Once a review is applied its card is closed, and grams nobody placed are gone
unless the spools are weighed. The Apply's last Activity Log line used to say only
"84.28g of 'x' wasn't charged to any spool — weigh the spools to true up", naming
no head and no spool. Pinned here, on the real edge, review and Apply code over
the wire harness (tests/deduct_wire_harness.py; only the G-code compute is
stubbed):

  - one WARNING line says, per head, the grams left on it and every spool FCC's
    own record names there (a set's spools; else the start snapshot's and the
    recorded swaps' spools, then what the print-end read found), with no Spoolman
    read: a set left empty, a set part placed (only what its boxes didn't place),
    a plain held line nobody picked (two spools at the end; a head emptied before
    the end), two heads, a set of three spools, a no_spool card's set;
  - grams a picked spool couldn't take (its clamp) are logged per spool already:
    the line counts them in its total and names no spool for them again; a clamp
    big enough for a card of its own goes on that card, and the line still says
    which heads were left (it used to say nothing about them at all);
  - a retry after a failed write still names them when it commits;
  - free text is escaped; the ledger's shortfall is unchanged.

HEAD proof: run on 732841b (R1, before R2), every test here fails except
test_a_clamp_alone_keeps_the_old_line, which passes by design: it pins that a
shortfall with no head to name reads as before. The failure lines are in each
test's comment.
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
import print_monitor  # noqa: E402
import print_tracker_store  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from deduct_wire_harness import WeightWireSpoolman, _start, _stop  # noqa: E402
from test_print_end_heads_hotfix import FILE, INDX, JOB, USAGE, Indx, _job, _rec, _spool, _tick  # noqa: E402
from test_swap_split_sets_hotfix import _measured  # noqa: E402

LEAD = f"⚠️ {INDX}: "


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))
    monkeypatch.setattr(spoolman_api, "LAST_SPOOLMAN_ERROR", None)
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", False)
    monkeypatch.setattr(print_monitor, "_FETCH_CLAIMS", set(), raising=False)
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    monkeypatch.setattr(print_deduct.config_loader, "load_config", lambda: {})
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER.clear()
    yield
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER.clear()


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a[0] if a else k.get("category"))))
    return calls


def _put(p, head, sid):
    """`sid` onto `head`; the spool that was there goes to a cart (Spoolman's record)."""
    for old in p.at.get(head) or []:
        if old in p.sm.spools:
            p.sm.spools[old]["location"] = "CR-CT-2-R1"
    if sid not in p.sm.spools:
        p.sm.spools[sid] = _spool(10.0, head)
    p.sm.spools[sid]["location"] = head
    p.at[head] = [sid]


def _swap(p, head, sid, at):
    """A run-out on `head` at `at`: the printer parks, `sid` goes on, it resumes and
    FCC records the swap."""
    _tick("ATTENTION", _job(at))
    _put(p, head, sid)
    _tick("PRINTING", _job(at))


def _confirm(body, printer=INDX, job=JOB):
    return app_module.app.test_client().post(
        "/api/cancel_deduct/confirm", json=dict({"printer_name": printer, "job_id": str(job)}, **body)).get_json()


def _uncharged(logs):
    """The one line that says what no spool took."""
    lines = [(m, lvl) for m, lvl in logs if "wasn't charged to any spool" in m]
    assert len(lines) == 1, logs
    msg, lvl = lines[0]
    assert lvl == "WARNING", lines
    return msg


def _changed_at_end(p, end_state="STOPPED"):
    """Job 1141's poll-window case: #229 went on RCOI-5 before FCC saw the end, no
    pause, so the card shows RCOI-5 as a set of #42 and #229."""
    _tick("PRINTING", _job(0.42))
    p.load_229()
    _tick(end_state)


def _shortfall_entry():
    return print_deduct_ledger._load()[print_deduct_ledger._key(INDX, str(JOB))].get("shortfall")


# --------------------------------------------------------------------------- #

def test_a_set_left_empty_is_named_with_both_spools(logs):
    # On 732841b: AssertionError: ... wasn't charged to any spool — weigh the spools to true up.' == ...
    # (no head and no spool named).
    with Indx() as p, _measured(USAGE, {}):
        _changed_at_end(p)
        body = _confirm({"updates": {"243": 75.32, "231": 21.9}})
    assert body["status"] == "confirmed" and body["shortfall_g"] == pytest.approx(84.28), body
    assert _uncharged(logs) == (
        f"{LEAD}84.28g of '{FILE}' wasn't charged to any spool: 84.28 g on T4 · RCOI-5, "
        f"which had #42 and #229 — weigh them to true up.")
    assert _shortfall_entry() == pytest.approx(84.28)


def test_a_set_part_placed_names_only_what_its_boxes_left(logs):
    # On 732841b: AssertionError: (the line named no head: "...54.28g of '...' wasn't charged to
    # any spool — weigh the spools to true up.")
    with Indx() as p, _measured(USAGE, {}):
        _changed_at_end(p)
        body = _confirm({"charges": [{"row": 243, "sid": 243, "grams": 75.32},
                                     {"row": 231, "sid": 231, "grams": 21.9},
                                     {"position": 4, "sid": 42, "grams": 30.0}]})
        assert p.sm.used(42) == pytest.approx(730.0)
    assert body["status"] == "confirmed" and body["shortfall_g"] == pytest.approx(54.28), body
    assert _uncharged(logs) == (
        f"{LEAD}54.28g of '{FILE}' wasn't charged to any spool: 54.28 g on T4 · RCOI-5, "
        f"which had #42 and #229 — weigh them to true up.")
    assert _shortfall_entry() == pytest.approx(54.28)


def test_a_plain_held_line_nobody_picked_names_the_spools_at_the_end(logs):
    """RCOI-5 held two spools when the print ended: one held line (not a set), left
    unpicked."""
    # On 732841b: AssertionError: (no head and no spool named)
    with Indx() as p, _measured(USAGE, {}):
        _tick("PRINTING", _job(0.42))
        p.at["RCOI-5"] = [42, 229]
        p.sm.spools[229]["location"] = "RCOI-5"
        _tick("STOPPED")
        rec = _rec()
        assert rec["unresolved_usage"] == {"4": 84.28} and not rec.get("unresolved_sets"), rec
        body = _confirm({"updates": {"243": 75.32, "231": 21.9}})
    assert body["status"] == "confirmed", body
    assert _uncharged(logs) == (
        f"{LEAD}84.28g of '{FILE}' wasn't charged to any spool: 84.28 g on T4 · RCOI-5, "
        f"which had #42 and #229 — weigh them to true up.")


def test_a_head_emptied_before_the_end_names_its_start_spool(logs):
    # On 732841b: AssertionError: (no head and no spool named)
    with Indx() as p, _measured(USAGE, {}):
        _tick("PRINTING", _job(0.42))
        p.at["RCOI-5"] = []
        p.sm.spools[42]["location"] = "CR-CT-2-R1"
        _tick("STOPPED")
        body = _confirm({"updates": {"243": 75.32, "231": 21.9}})
    assert body["status"] == "confirmed", body
    # One spool named: "weigh it".
    assert _uncharged(logs) == (
        f"{LEAD}84.28g of '{FILE}' wasn't charged to any spool: 84.28 g on T4 · RCOI-5, "
        f"which had #42 — weigh it to true up.")


def test_two_heads_left_are_each_named(logs):
    # On 732841b: AssertionError: (no head and no spool named: "...159.60g of ... wasn't charged
    # to any spool — weigh the spools to true up.")
    with Indx() as p, _measured(USAGE, {}):
        _tick("PRINTING", _job(0.42))
        p.load_229()
        _put(p, "RCOI-7", 302)
        _tick("STOPPED")
        assert set((_rec().get("unresolved_sets") or {})) == {"4", "6"}
        body = _confirm({"updates": {"231": 21.9}})
    assert body["status"] == "confirmed" and body["shortfall_g"] == pytest.approx(159.6), body
    assert _uncharged(logs) == (
        f"{LEAD}159.60g of '{FILE}' wasn't charged to any spool: 84.28 g on T4 · RCOI-5, which had "
        f"#42 and #229; 75.32 g on T6 · RCOI-7, which had #243 and #302 — weigh them to true up.")
    assert _shortfall_entry() == pytest.approx(159.6)


def test_a_set_of_three_spools_names_all_three(logs):
    """Two run-outs on RCOI-5 (#42 to #229 at 10%, #229 to #300 at 25%) that the
    walk couldn't measure: a set of the three spools, left empty."""
    # On 732841b: AssertionError: (no head and no spool named)
    with Indx() as p, _measured(USAGE, {}):
        _tick("PRINTING", _job(0.05))
        _swap(p, "RCOI-5", 229, 0.10)
        _tick("PRINTING", _job(0.20))
        _swap(p, "RCOI-5", 300, 0.25)
        _tick("PRINTING", _job(0.42))
        _tick("STOPPED")
        assert [e["sid"] for e in _rec()["unresolved_sets"]["4"]] == [42, 229, 300]
        body = _confirm({"updates": {"243": 75.32, "231": 21.9}})
    assert body["status"] == "confirmed", body
    assert _uncharged(logs) == (
        f"{LEAD}84.28g of '{FILE}' wasn't charged to any spool: 84.28 g on T4 · RCOI-5, "
        f"which had #42, #229 and #300 — weigh them to true up.")


def test_a_no_spool_cards_set_part_placed_is_named(logs):
    """A completion whose only used head changed with no swap recorded: a no_spool
    card whose line is a set; 20 g of its 50 g placed."""
    # On 732841b: AssertionError: (no head and no spool named: "...30.00g of ... wasn't charged
    # to any spool — weigh the spools to true up.")
    with Indx() as p, _measured({4: 50.0}, {}):
        _tick("PRINTING", _job(0.5))
        p.load_229()
        _tick("FINISHED")
        assert _rec()["kind"] == "no_spool"
        body = _confirm({"charges": [{"position": 4, "sid": 42, "grams": 20.0}]})
    assert body["status"] == "confirmed" and body["shortfall_g"] == pytest.approx(30.0), body
    assert _uncharged(logs) == (
        f"{LEAD}30.00g of '{FILE}' wasn't charged to any spool: 30 g on T4 · RCOI-5, "
        f"which had #42 and #229 — weigh them to true up.")


def test_a_clamp_is_counted_but_its_spool_is_not_named_again(logs):
    """#231 has 21.5 g left for its 21.9 g: its 0.4 g are logged on its own line, too
    few for a card (under 1 g), and counted in this line's total, unnamed."""
    # On 732841b: AssertionError: (no head named: "...84.68g of ... wasn't charged to any spool —
    # weigh the spools to true up.")
    with Indx() as p, _measured(USAGE, {}):
        p.sm.spools[231]["used_weight"] = 978.5
        _changed_at_end(p)
        body = _confirm({"updates": {"243": 75.32, "231": 21.9}})
    assert body["status"] == "confirmed" and body["shortfall_g"] == pytest.approx(84.68), body
    assert "shortfall_card" not in body
    assert any("Spool #231 had only 21.5g left" in m for m, _ in logs), logs
    line = _uncharged(logs)
    assert line == (
        f"{LEAD}84.68g of '{FILE}' wasn't charged to any spool: 84.28 g on T4 · RCOI-5, which had "
        f"#42 and #229; and 0.4 g the picked spools couldn't take (said above) — weigh them to true up.")
    assert "#231" not in line


def test_a_clamp_alone_keeps_the_old_line(logs):
    """Every head placed; only a clamp under a card's worth is left: no head to
    name, so the line reads as before. Passes by design on 732841b."""
    with Indx() as p, _measured(USAGE, {}):
        p.sm.spools[231]["used_weight"] = 978.5
        _tick("PRINTING", _job(0.42))
        _tick("STOPPED")
        body = _confirm({"updates": {"42": 84.28, "243": 75.32, "231": 21.9}})
    assert body["status"] == "confirmed" and body["shortfall_g"] == pytest.approx(0.4), body
    assert _uncharged(logs) == f"{LEAD}0.40g of '{FILE}' wasn't charged to any spool — weigh the spools to true up."


def test_a_clamp_on_its_own_card_leaves_the_heads_nobody_placed_named(logs):
    """#231 has 10 g left for its 21.9 g: its 11.9 g go on a card of their own (the
    line about that card says so). RCOI-5's set was left empty: those grams are on
    no card, and the line says so. On 732841b nothing said them at all."""
    # On 732841b: AssertionError: assert 0 == 1 (no "wasn't charged to any spool" line: only the
    # new card's line, about #231's 11.9 g).
    with Indx() as p, _measured(USAGE, {}):
        p.sm.spools[231]["used_weight"] = 990.0
        _changed_at_end(p)
        body = _confirm({"updates": {"243": 75.32, "231": 21.9}})
    assert body["status"] == "confirmed" and body["shortfall_card"] == f"{JOB}#shortfall", body
    assert body["shortfall_g"] == pytest.approx(96.18), body
    assert any("11.90g of" in m and "couldn't be charged to the spool(s) picked" in m for m, _ in logs), logs
    assert _uncharged(logs) == (
        f"{LEAD}84.28g of '{FILE}' wasn't charged to any spool: 84.28 g on T4 · RCOI-5, "
        f"which had #42 and #229 — weigh them to true up.")
    assert _shortfall_entry() == pytest.approx(96.18)


def test_a_retry_after_a_failed_write_still_names_the_head(logs):
    """The Apply placed 30 g of RCOI-5's set and #243's write was lost; the retry
    commits, and the line still names the set's 54.28 g."""
    # On 732841b: AssertionError: (no head and no spool named)
    with Indx() as p, _measured(USAGE, {}):
        _changed_at_end(p)
        p.sm.patch_lost.add(243)
        first = _confirm({"charges": [{"row": 243, "sid": 243, "grams": 75.32},
                                      {"row": 231, "sid": 231, "grams": 21.9},
                                      {"position": 4, "sid": 42, "grams": 30.0}]})
        assert first["status"] == "confirmed" and first["errors"], first
        assert not [m for m, _ in logs if "wasn't charged to any spool" in m]
        p.sm.patch_lost.clear()
        second = _confirm({"updates": {"243": 75.32}})
        assert p.sm.used(243) == pytest.approx(775.32)
    assert second["status"] == "confirmed" and second["shortfall_g"] == pytest.approx(54.28), second
    assert _uncharged(logs) == (
        f"{LEAD}54.28g of '{FILE}' wasn't charged to any spool: 54.28 g on T4 · RCOI-5, "
        f"which had #42 and #229 — weigh them to true up.")


def test_the_line_escapes_its_free_text(logs):
    # On 732841b: AssertionError: (the head wasn't named, so its name never reached the line)
    sm = WeightWireSpoolman({42: _spool(700.0, "H<2>&"), 7: _spool(700.0, "SHELF")})
    rec = {"printer_name": "P<1>", "job_id": "9", "filename": "f<3>.gcode", "progress": 0.5,
           "total_grams": 15.0, "spools": [{"sid": 7, "toolhead": "H-1", "position": 1, "grams": 10.0,
                                            "display": "#7", "color": "ff0000", "ambiguous": False}],
           "ambiguous": False, "unresolved_usage": {"0": 5.0},
           "heads_at_end": [{"toolhead": "H<2>&", "position": 0, "sid": 42, "sids": [42]}],
           "heads_source": "print_end", "created": "2026-11-12 00:00:00"}
    ctx = [patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
           patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "ff0000"}),
           patch.object(spoolman_api.requests, "get", side_effect=sm._get),
           patch.object(spoolman_api.requests, "patch", side_effect=sm._patch)]
    _start(ctx)
    try:
        cancel_review_store.add_pending(rec)
        body = _confirm({"updates": {"7": 10.0}}, printer="P<1>", job="9")
    finally:
        _stop(ctx)
    assert body["status"] == "confirmed", body
    assert _uncharged(logs) == ("⚠️ P&lt;1&gt;: 5.00g of 'f&lt;3&gt;.gcode' wasn't charged to any spool: "
                                "5 g on T0 · H&lt;2&gt;&amp;, which had #42 — weigh it to true up.")
