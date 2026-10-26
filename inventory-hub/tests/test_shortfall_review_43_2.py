"""Group 43.2: a shortfall becomes a recoverable review.

Job 1104 on the Core One INDX needed 61.32 g. Spool #99 on RCOI-1 held 34.2 g,
so the completion deduct charged it 34.2 g, #99 hit 0 g and was auto-archived,
and the other 27.12 g went to no spool: one Activity Log WARNING, and nothing on
the ledger entry. (Derek had RCOI-1 joined to RCOI-2, so the printer finished
from RCOI-2's spool; PrusaLink can't tell FCC that.)

Now a deduct that leaves at least `shortfall_review_min_g` (default 1 g)
uncharged stashes a review card under the derived key "<job>#shortfall" BEFORE it
writes the ledger, and the ledger entry records the shortfall. The card lists
each head's uncharged grams with the spool picker: the spool that was on that head
when FCC logged the print (the run-out spool, archived by then), the spools on the
heads now, or any #id. Every Apply of a card quotes its revision, so a stale view
can't charge grams that were already placed.

Derek's 2026-10-13 answer: a picked archived spool is charged what it still has
on record and stays archived (and doesn't move). Whatever a pick can't take stays
on the card, so he can pick again or discard; on any other review card it opens
an uncharged-grams card. Review cards stop refusing archived picks.

The adversarial review of the first build (wf_6284177c-d05) found the rest pinned
here: a write that reported failure but landed is never charged twice (it rides
on the card as a 43.6-stamped row), a stale or retried Apply is refused, a failed
write in a card's Apply keeps the other picks' leftover, a crash between the card
and the ledger doesn't re-run the deduct, a hand-archived spool charged to 0 g
stays in its slot, id-less jobs get no shared card, the card's ledger entry adds
up every Apply, and a head holding two spools offers both.

HEAD proof: on the pre-43.2 code no card is stashed, the ledger entry has no
`shortfall`, an archived pick is refused, and a "#shortfall" record stashed by
hand is used up by an Apply that picked nothing.

The engine runs for real against tests/deduct_wire_harness.py, with a head
locator that reads the fake Spoolman's live state (an auto-archived spool leaves
its head, as in production).
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
import config_schema  # noqa: E402
import print_deduct  # noqa: E402
import print_deduct_ledger  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from deduct_wire_harness import WeightWireSpoolman, _start, _stop  # noqa: E402

INDX = "🦝 Core One INDX"
HEADS = (("RCOI-1", 0), ("RCOI-2", 1))
FILE = "/usb/MAIN-B~1.BGC"
CARD = "1104#shortfall"


@pytest.fixture(autouse=True)
def _isolated_stores(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a, k)))
    return calls


def _spool(used, loc, archived=False, initial=1000.0, extra=None):
    return {"used_weight": used, "initial_weight": initial, "archived": archived,
            "location": loc, "filament": {"weight": 1000.0}, "extra": dict(extra or {})}


def _sm(over=None):
    spools = {
        99: _spool(965.8, "RCOI-1"),                 # 34.2 g left: job 1104's run-out spool
        300: _spool(100.0, "RCOI-2"),                # the joined spool, 900 g left
        301: _spool(990.0, "SHELF-A"),               # 10 g left
        226: _spool(900.0, "", archived=True),       # archived by hand, 100 g on record
    }
    spools.update(over or {})
    return WeightWireSpoolman(spools)


def _ctx(sm, cfg=None):
    """The wire harness's context, with a head locator that reads the fake's LIVE
    state: a spool that gets auto-archived leaves its head, as it does in
    production (update_spool clears its location)."""
    active = [(loc, {"position": pos, "printer_name": INDX}) for loc, pos in HEADS]

    def located(loc):
        return [sid for sid, rec in sm.spools.items()
                if str(rec.get("location") or "").upper() == str(loc).upper() and not rec.get("archived")]

    return [
        patch.object(print_deduct.locations_db, "get_active_printer_map", return_value={}),
        patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=active),
        patch.object(spoolman_api, "get_spools_at_location", side_effect=located),
        patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(print_deduct.config_loader, "load_config", return_value=dict(cfg or {})),
        patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "ff0000"}),
        patch.object(spoolman_api.requests, "get", side_effect=sm._get),
        patch.object(spoolman_api.requests, "patch", side_effect=sm._patch),
    ]


def _complete(sm, usage, job=1104, cfg=None):
    """The real completion deduct, with the footer parse stubbed to `usage`."""
    ctx = _ctx(sm, cfg)
    _start(ctx)
    try:
        with patch.object(print_deduct, "_compute_cancel_usage", return_value=(dict(usage), None)):
            return print_deduct.deduct_completed_print(INDX, FILE, job, fb_url="http://fb",
                                                       ip_address="10.0.0.9", api_key="k")
    finally:
        _stop(ctx)


def _confirm(sm, body, cfg=None):
    ctx = _ctx(sm, cfg)
    _start(ctx)
    try:
        return app_module.app.test_client().post("/api/cancel_deduct/confirm", json=body).get_json()
    finally:
        _stop(ctx)


def _apply_card(sm, charges=None, rev=None, **extra):
    """An Apply of job 1104's card, quoting its current revision unless told otherwise."""
    if rev is None:
        rev = (_pending(CARD) or {}).get("rev", 0)
    body = {"printer_name": INDX, "job_id": CARD, "rev": rev, **extra}
    if charges is not None:
        body["charges"] = charges
    return _confirm(sm, body)


def _pending(job):
    return next((r for r in cancel_review_store.list_pending() if r["job_id"] == job), None)


def _entry(job):
    return print_deduct_ledger._load().get(print_deduct_ledger._key(INDX, job))


def _card(**over):
    """A shortfall card shaped like the one the completion deduct stashes."""
    rec = {
        "printer_name": INDX, "job_id": CARD, "shortfall_of": "1104", "filename": FILE,
        "progress": 1.0, "total_grams": 27.12, "spools": [], "ambiguous": False, "kind": "shortfall",
        "rev": 0, "unresolved_usage": {"0": 27.12},
        "heads_at_end": [{"toolhead": "RCOI-1", "position": 0, "sid": 99, "archived": True},
                         {"toolhead": "RCOI-2", "position": 1, "sid": 300}],
        "shortfall_causes": {"0": {"why": "ran_out", "sid": 99, "toolhead": "RCOI-1", "archived": True}},
        "created": "2026-10-13 00:00:00",
    }
    rec.update(over)
    cancel_review_store.add_pending(rec)
    return rec


# --------------------------------------------------------------------------- #
# The card is stashed by a deduct                                             #
# --------------------------------------------------------------------------- #

def test_job_1104_shortfall_becomes_a_review_card(logs):
    sm = _sm()
    res = _complete(sm, {0: 61.32})
    assert res["status"] == "deducted", res
    assert sm.used(99) == pytest.approx(1000.0) and sm.spools[99]["archived"] is True
    rec = _pending(CARD)
    assert rec is not None, "the 27.12 g that went to no spool must leave a review card"
    assert rec["kind"] == "shortfall" and rec["shortfall_of"] == "1104" and rec["rev"] == 0, rec
    assert rec["unresolved_usage"] == {"0": pytest.approx(27.12)}, rec
    assert rec["total_grams"] == pytest.approx(27.12)
    heads = {h["position"]: h for h in rec["heads_at_end"]}
    # The run-out spool is named even though the auto-archive already took it off
    # RCOI-1: the card's default comes from the deduct's own details.
    assert heads[0]["sid"] == 99 and heads[0]["toolhead"] == "RCOI-1", rec["heads_at_end"]
    assert heads[1]["sid"] == 300, "the joined spool on RCOI-2 is offered as a head at print end"
    cause = rec["shortfall_causes"]["0"]
    assert cause["why"] == "ran_out" and cause["sid"] == 99 and cause["archived"] is True, cause
    entry = _entry("1104")
    assert entry["grams"] == pytest.approx(34.2)
    assert entry["shortfall"] == pytest.approx(27.12), "the ledger entry must explain the gap on its own"
    line = next((m for m, a, k in logs if "27.12" in m and "Review" in m), None)
    assert line and "#99's record hit 0 g on RCOI-1" in line, logs
    meta = next(k.get("meta") for m, a, k in logs if m == line)
    assert meta == {"type": "cancel_deduct_pending", "printer_name": INDX, "job_id": CARD}, meta


def test_the_card_is_stashed_before_the_ledger_entry(logs):
    """A crash between the two must leave the recoverable card, not a terminal
    ledger key with nothing behind it."""
    sm = _sm()
    seen = []
    real = print_deduct_ledger.record_deduct

    def spy(printer, job, **meta):
        if str(job) == "1104":
            seen.append(cancel_review_store.has_pending(INDX, CARD))
        return real(printer, job, **meta)

    with patch.object(print_deduct_ledger, "record_deduct", side_effect=spy):
        _complete(sm, {0: 61.32})
    assert seen == [True], seen


def test_a_crash_between_the_card_and_the_ledger_does_not_charge_again(logs):
    """Review finding deduct-5. The card exists and the job has no ledger entry,
    so a deferred-fetch retry or a restart's recovery must not run the deduct a
    second time: it records the missing entry and stops."""
    sm = _sm()
    real = print_deduct_ledger.record_deduct

    def boom(printer, job, **meta):
        if str(job) == "1104":
            raise RuntimeError("power cut")
        return real(printer, job, **meta)

    with patch.object(print_deduct_ledger, "record_deduct", side_effect=boom):
        # Group 56 (review round 3): a raise after the spool writes comes out as
        # CompletionMayHaveCharged, from the original error, so the deferred-fetch
        # loop never retries it blind.
        with pytest.raises(print_deduct.CompletionMayHaveCharged) as raised:
            _complete(sm, {0: 61.32})
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert _pending(CARD) is not None and not print_deduct_ledger.was_deducted(INDX, "1104")
    patches = len(sm.patches)
    res = _complete(sm, {0: 61.32})
    assert res["status"] == "skipped", res
    assert len(sm.patches) == patches, "no spool may be charged a second time"
    assert _entry("1104").get("recovered") is True
    assert _pending("1104") is None, "no second (no_spool) review for the same print"


def test_a_shortfall_under_the_threshold_is_recorded_but_opens_no_card(logs):
    sm = _sm()
    _complete(sm, {0: 34.7})                     # 0.5 g more than #99 had
    assert _pending(CARD) is None
    assert _entry("1104")["shortfall"] == pytest.approx(0.5)


def test_the_threshold_is_a_setting(logs):
    sm = _sm()
    _complete(sm, {0: 61.32}, cfg={"shortfall_review_min_g": 30})
    assert _pending(CARD) is None, "27.12 g is under a 30 g threshold"
    assert _entry("1104")["shortfall"] == pytest.approx(27.12)
    field = config_schema.get_field("shortfall_review_min_g")
    assert field is not None and field.default == 1.0 and field.section == "behavior"


def test_every_head_with_uncharged_grams_gets_a_line(logs):
    """RCOI-1's spool runs out and RCOI-2 had no spool loaded at all."""
    sm = _sm({300: _spool(100.0, "SHELF-B")})
    _complete(sm, {0: 61.32, 1: 5.0})
    rec = _pending(CARD)
    assert rec["unresolved_usage"] == {"0": pytest.approx(27.12), "1": pytest.approx(5.0)}, rec
    assert rec["shortfall_causes"]["1"]["why"] == "no_spool", rec["shortfall_causes"]
    assert rec["total_grams"] == pytest.approx(32.12)
    assert _entry("1104")["shortfall"] == pytest.approx(32.12)


def test_a_head_with_two_spools_offers_both(logs):
    """Review finding spec-5: the apply loop skips a head holding two spools; the
    card's line names both and offers both, instead of neither."""
    sm = _sm({302: _spool(100.0, "RCOI-2")})
    two = lambda loc: ([300, 302], True) if str(loc).upper() == "RCOI-2" else ([], False)  # noqa: E731
    with patch.object(spoolman_api, "select_deduct_targets", side_effect=two):
        _complete(sm, {0: 10.0, 1: 5.0})
    rec = _pending(CARD)
    assert rec["unresolved_usage"] == {"1": pytest.approx(5.0)}, rec
    cause = rec["shortfall_causes"]["1"]
    assert cause["why"] == "two_spools" and cause["sids"] == [300, 302], cause
    assert {h["sid"] for h in rec["heads_at_end"] if h["position"] == 1} >= {300, 302}, rec["heads_at_end"]


def test_the_one_shot_cancel_deduct_stashes_a_card_too(logs):
    sm = _sm()
    ctx = _ctx(sm)
    _start(ctx)
    try:
        with patch.object(print_deduct, "_compute_cancel_usage", return_value=({0: 61.32}, None)):
            res = print_deduct.deduct_cancelled_print(INDX, FILE, 1104, 0.9, fb_url="http://fb",
                                                      ip_address="10.0.0.9", api_key="k")
    finally:
        _stop(ctx)
    assert res["status"] == "deducted", res
    assert _pending(CARD)["unresolved_usage"] == {"0": pytest.approx(27.12)}


def test_a_confirmed_deduct_opens_a_card_too(logs):
    """Changed by review finding deduct-2: grams a spool couldn't take open a card
    on every path, a deduct someone just confirmed included."""
    details = [{"sid": 99, "grams": 34.2, "remaining": 0.0, "toolhead": "RCOI-1", "position": 0}]
    print_deduct._record_applied_deduct(INDX, "J-9", filename=FILE, scale=1.0, details=details,
                                        usage_map={0: 61.32}, known_positions={0, 1}, confirmed=True)
    assert _pending("J-9#shortfall")["unresolved_usage"] == {"0": pytest.approx(27.12)}
    entry = _entry("J-9")
    assert entry["shortfall"] == pytest.approx(27.12) and entry["confirmed"] is True


def test_a_job_without_an_id_gets_no_card(logs):
    """Review finding deduct-7: an id-less job's card key would be "#shortfall" for
    every such print, so the first settled one would silence the rest."""
    details = [{"sid": 99, "grams": 34.2, "remaining": 0.0, "toolhead": "RCOI-1", "position": 0}]
    print_deduct._record_applied_deduct(INDX, "", filename=FILE, scale=1.0, details=details,
                                        usage_map={0: 61.32}, known_positions={0, 1})
    assert _pending("#shortfall") is None
    assert any("wasn't deducted" in m and "weigh" in m for m, a, k in logs), logs


# --------------------------------------------------------------------------- #
# A write that reported failure but landed is never charged twice             #
# --------------------------------------------------------------------------- #

def test_an_unconfirmed_write_that_landed_is_not_charged_twice(logs):
    """Review finding deduct-1. #300's write landed, then Spoolman timed out and
    couldn't be re-read, so the deduct counted it as failed. The card carries it
    as a 43.6-stamped row; its Apply sees the write already landed and charges
    nothing more. HEAD of the first build pre-picked #300 and charged it again."""
    sm = _sm()
    sm.patch_fails.add(300)
    sm.blind_after_patch.add(300)
    _complete(sm, {0: 20.0, 1: 5.0})
    assert sm.used(300) == pytest.approx(105.0), "the write landed"
    rec = _pending(CARD)
    assert rec is not None and rec["unresolved_usage"] == {}, rec
    row = rec["spools"][0]
    assert row["sid"] == 300 and row["unconfirmed_write"] is True
    assert (row["attempt_used_before"], row["attempt_used_after"]) == (100.0, 105.0), row
    sm.blind.discard(300)
    body = _apply_card(sm, updates={"300": 5.0})
    assert body["status"] == "confirmed", body
    assert sm.used(300) == pytest.approx(105.0), "charged once, not twice"
    assert _pending(CARD) is None and _entry(CARD)["grams"] == pytest.approx(5.0)


def test_an_unconfirmed_write_that_never_landed_is_charged_once(logs):
    sm = _sm()
    sm.patch_lost.add(300)
    _complete(sm, {0: 20.0, 1: 5.0})
    assert sm.used(300) == pytest.approx(100.0), "the write never landed"
    sm.patch_lost.discard(300)
    body = _apply_card(sm, updates={"300": 5.0})
    assert body["status"] == "confirmed", body
    assert sm.used(300) == pytest.approx(105.0)


def test_a_print_whose_every_write_failed_gets_a_card_not_a_no_spool_review(logs):
    """A no_spool review's Apply re-resolves to whatever is on the head, which
    would charge a landed write again; the card's stamped row checks first."""
    sm = _sm()
    sm.patch_fails.add(99)
    sm.blind_after_patch.add(99)
    _complete(sm, {0: 20.0})
    assert _pending("1104") is None, "no no_spool review"
    rec = _pending(CARD)
    assert [r["sid"] for r in rec["spools"]] == [99], rec


# --------------------------------------------------------------------------- #
# Applying the card                                                           #
# --------------------------------------------------------------------------- #

def test_picking_the_joined_spool_charges_it_and_closes_the_card(logs):
    """Derek's case: the printer finished from RCOI-2's spool. The real job is
    already in the ledger when the card is applied: the derived key keeps the
    confirm from answering "already handled" and losing the grams again."""
    sm = _sm()
    _complete(sm, {0: 61.32})
    assert print_deduct_ledger.was_deducted(INDX, "1104")
    body = _apply_card(sm, [{"position": 0, "sid": 300, "grams": 27.12}])
    assert body["status"] == "confirmed" and not body.get("kept"), body
    assert sm.used(300) == pytest.approx(127.12)
    assert _pending(CARD) is None
    assert _entry(CARD)["grams"] == pytest.approx(27.12)
    assert _entry("1104")["grams"] == pytest.approx(34.2), "the print's own entry is untouched"


def test_picking_the_archived_run_out_spool_keeps_the_card(logs):
    """#99 has 0 g on record: it is charged nothing, stays archived and doesn't
    move, and the 27.12 g stay on the card to pick again or discard."""
    sm = _sm()
    _complete(sm, {0: 61.32})
    patches_before = len([p for p in sm.patches if p[0] == 99])
    body = _apply_card(sm, [{"position": 0, "sid": 99, "grams": 27.12}])
    assert body["status"] == "confirmed" and body.get("kept") is True, body
    assert body["shortfall_g"] == pytest.approx(27.12) and body["rev"] == 1
    assert len([p for p in sm.patches if p[0] == 99]) == patches_before, "an empty spool takes no write"
    assert sm.spools[99]["archived"] is True and sm.spools[99]["location"] == ""
    rec = _pending(CARD)
    assert rec is not None and rec["unresolved_usage"] == {"0": pytest.approx(27.12)}, rec
    assert rec["kind"] == "shortfall" and rec["spools"] == [] and rec["rev"] == 1, rec
    assert not print_deduct_ledger.was_deducted(INDX, CARD)


def test_a_pick_that_can_take_only_part_leaves_the_rest_on_the_card(logs):
    sm = _sm()
    _complete(sm, {0: 61.32})
    body = _apply_card(sm, [{"position": 0, "sid": 301, "grams": 27.12}])
    assert body.get("kept") is True, body
    assert sm.used(301) == pytest.approx(1000.0), "#301 takes its last 10 g"
    assert sm.spools[301]["archived"] is True, "a charge that empties a spool archives it, as today"
    rec = _pending(CARD)
    assert rec["unresolved_usage"] == {"0": pytest.approx(17.12)}
    # Review finding contracts-4: the line now says #301 ran dry, so the card
    # doesn't pre-pick it again.
    assert rec["shortfall_causes"]["0"] == {"why": "ran_out", "sid": 301, "archived": True,
                                            "toolhead": "RCOI-1"}, rec["shortfall_causes"]


def test_a_stale_view_cannot_apply_the_cards_old_grams(logs):
    """Review finding deduct-3: another tab, or a retried request, still shows
    27.12 g after an Apply placed 10 g; its Apply is refused, and the card's ledger
    entry adds up both real Applies (deduct-8)."""
    sm = _sm()
    _complete(sm, {0: 61.32})
    first = _apply_card(sm, [{"position": 0, "sid": 301, "grams": 27.12}], rev=0)
    assert first.get("kept") is True and first["rev"] == 1, first
    stale = _apply_card(sm, [{"position": 0, "sid": 300, "grams": 27.12}], rev=0)
    assert stale["status"] == "error" and stale.get("stale") is True, stale
    assert sm.used(300) == pytest.approx(100.0), "nothing charged from the stale view"
    assert _pending(CARD)["unresolved_usage"] == {"0": pytest.approx(17.12)}
    fresh = _apply_card(sm, [{"position": 0, "sid": 300, "grams": 17.12}], rev=1)
    assert fresh["status"] == "confirmed" and not fresh.get("kept"), fresh
    assert sm.used(300) == pytest.approx(117.12)
    assert _entry(CARD)["grams"] == pytest.approx(27.12), "the card's entry counts every Apply"


def test_an_apply_without_the_cards_revision_is_refused(logs):
    """A page from before 43.2 sends no revision."""
    sm = _sm()
    _card()
    body = _confirm(sm, {"printer_name": INDX, "job_id": CARD,
                         "charges": [{"position": 0, "sid": 300, "grams": 27.12}]})
    assert body["status"] == "error" and body.get("stale") is True, body
    assert not sm.patches and _pending(CARD) is not None


def test_an_archived_spool_with_filament_on_record_is_charged_and_stays_archived(logs):
    sm = _sm()
    _card()
    body = _apply_card(sm, [{"position": 0, "sid": 226, "grams": 27.12}])
    assert body["status"] == "confirmed" and not body.get("kept"), body
    assert sm.used(226) == pytest.approx(927.12)
    sent = [b for sid, b in sm.patches if sid == 226]
    assert sent and sent[-1].get("archived") is True, sent
    assert sm.spools[226]["archived"] is True and sm.spools[226]["location"] == ""


def test_charging_a_hand_archived_spool_to_zero_keeps_it_in_its_slot(logs):
    """Review finding deduct-6: a spool archived by hand, still in LR-MDB-1 slot 2,
    charged its last 20 g. The auto-archive used to move it to UNASSIGNED and
    clear its slot; Derek's answer is that it doesn't move."""
    sm = _sm({226: _spool(980.0, "LR-MDB-1", archived=True, extra={"container_slot": "2"})})
    _card()
    body = _apply_card(sm, [{"position": 0, "sid": 226, "grams": 27.12}])
    assert body["status"] == "confirmed" and body.get("kept") is True, body
    assert sm.used(226) == pytest.approx(1000.0)
    assert sm.spools[226]["archived"] is True and sm.spools[226]["location"] == "LR-MDB-1"
    assert sm.spools[226]["extra"].get("container_slot") == "2", sm.spools[226]["extra"]


def test_an_apply_with_no_pick_is_refused_and_the_card_kept(logs):
    sm = _sm()
    _card()
    body = _apply_card(sm, updates={})
    assert body["status"] == "error" and "pick" in body["msg"].lower(), body
    assert _pending(CARD) is not None
    assert not print_deduct_ledger.was_deducted(INDX, CARD)
    assert not sm.patches


def test_a_failed_write_keeps_the_card_a_shortfall_card(logs):
    sm = _sm()
    sm.patch_lost.add(300)
    _card()
    first = _apply_card(sm, [{"position": 0, "sid": 300, "grams": 27.12}])
    assert first["status"] == "error", first
    rec = _pending(CARD)
    assert rec["kind"] == "shortfall" and rec["shortfall_of"] == "1104" and rec["rev"] == 1, rec
    assert [r["sid"] for r in rec["spools"]] == [300]
    sm.patch_lost.discard(300)
    # The retry card's row keeps its own spool, so the card posts the plain shape.
    second = _apply_card(sm, updates={"300": 27.12})
    assert second["status"] == "confirmed", second
    assert sm.used(300) == pytest.approx(127.12)
    assert _pending(CARD) is None and print_deduct_ledger.was_deducted(INDX, CARD)


def test_a_failed_write_keeps_the_other_picks_leftover_on_the_card(logs):
    """Review finding deduct-4: #301 takes its last 10 g of line 0 while #300's
    write for line 1 fails. The 17.12 g #301 couldn't take used to drop off the
    card; they stay as a line, next to the row still to retry."""
    sm = _sm({300: _spool(100.0, "SHELF-B")})
    _complete(sm, {0: 61.32, 1: 5.0})
    sm.patch_lost.add(300)
    body = _apply_card(sm, [{"position": 0, "sid": 301, "grams": 27.12},
                            {"position": 1, "sid": 300, "grams": 5.0}])
    assert body["status"] == "confirmed" and body["errors"], body
    rec = _pending(CARD)
    assert rec["unresolved_usage"] == {"0": pytest.approx(17.12)}, rec
    assert [r["sid"] for r in rec["spools"]] == [300]
    assert rec["total_grams"] == pytest.approx(22.12) and rec["rev"] == 1, rec
    assert rec["shortfall_causes"]["0"]["sid"] == 301 and rec["shortfall_causes"]["0"]["archived"] is True


def test_dismissing_the_card_says_what_was_left_uncharged(logs):
    _card()
    r = app_module.app.test_client().post("/api/cancel_deduct/dismiss",
                                          json={"printer_name": INDX, "job_id": CARD}).get_json()
    assert r["status"] == "dismissed", r
    assert _entry(CARD)["dismissed"] is True and _entry(CARD)["grams"] == 0
    line = next((m for m, a, k in logs if "Dismissed" in m), "")
    assert "uncharged" in line and "27.12" in line and "1104" in line, line


def test_discarding_a_partly_applied_card_records_what_it_charged(logs):
    """Review finding deduct-8: a Discard after an Apply placed 10 g recorded 0 g."""
    sm = _sm()
    _complete(sm, {0: 61.32})
    _apply_card(sm, [{"position": 0, "sid": 301, "grams": 27.12}])
    r = app_module.app.test_client().post("/api/cancel_deduct/dismiss",
                                          json={"printer_name": INDX, "job_id": CARD}).get_json()
    assert r["status"] == "dismissed", r
    assert _entry(CARD)["grams"] == pytest.approx(10.0)


# --------------------------------------------------------------------------- #
# Derek's answer applies to every review card                                 #
# --------------------------------------------------------------------------- #

def test_a_no_spool_review_charges_a_picked_archived_spool(logs):
    sm = _sm()
    ctx = _ctx(sm)
    _start(ctx)
    try:
        print_deduct._stash_unresolved_review(INDX, FILE, "J-1105", 1.0, usage_map={0: 27.12}, no_spool=True)
    finally:
        _stop(ctx)
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1105",
                         "charges": [{"position": 0, "sid": 226, "grams": 27.12}]})
    assert body["status"] == "confirmed" and "shortfall_card" not in body, body
    assert sm.used(226) == pytest.approx(927.12) and sm.spools[226]["archived"] is True


def test_an_empty_pick_on_another_review_opens_a_card_with_its_grams(logs):
    """Review finding deduct-2: picking #99 (0 g on record) on job 1105's no_spool
    review charged nothing and closed the review for good. The review still
    closes, but its 27.12 g open an uncharged-grams card to pick again."""
    sm = _sm({99: _spool(1000.0, "", archived=True)})
    ctx = _ctx(sm)
    _start(ctx)
    try:
        print_deduct._stash_unresolved_review(INDX, FILE, "J-1105", 1.0, usage_map={0: 27.12}, no_spool=True)
    finally:
        _stop(ctx)
    body = _confirm(sm, {"printer_name": INDX, "job_id": "J-1105",
                         "charges": [{"position": 0, "sid": 99, "grams": 27.12}]})
    assert body["status"] == "confirmed" and body["shortfall_card"] == "J-1105#shortfall", body
    card = _pending("J-1105#shortfall")
    assert card["unresolved_usage"] == {"0": pytest.approx(27.12)}, card
    assert card["shortfall_causes"]["0"] == {"why": "ran_out", "sid": 99, "toolhead": "RCOI-1",
                                             "archived": True}, card["shortfall_causes"]
    assert _entry("J-1105")["shortfall"] == pytest.approx(27.12)
