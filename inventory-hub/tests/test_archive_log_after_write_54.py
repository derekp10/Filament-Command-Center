"""Group 54 review R1-2 (2026-11-09): the archive and un-archive lines say what a write did.

update_spool wrote "📦 Auto-archived Spool #N (remaining weight hit 0) — moved to
UNASSIGNED" BEFORE its PATCH, and for ANY write carrying `archived: true`:
  - a write Spoolman refused was logged as archived (on dev, a refused
    {remaining_weight: -5, archived: true} got the line while the spool stayed in
    stock on its shelf), and so was one FCC refused itself when its pre-merge read
    of the extras failed;
  - a caller's own archive with weight left (the wizard's Archived box:
    update_spool(57, {archived: True}) with 700 g left at CR-SHELF) was logged as
    having hit 0 and moved to UNASSIGNED, though it stayed at CR-SHELF.
The "📤 Auto-unarchived / Un-archived" line was written before the PATCH too.

Now both lines are written only once the write has landed: after Spoolman's OK,
or, for a write whose answer timed out (a READ timeout, so it may have landed),
once a re-read shows the spool archived (or back in stock) where the write put
it. The archive line says what the write did:
  - the archive edge's archive at 0 g keeps its words, "📦 Auto-archived Spool #N
    (remaining weight hit 0)"; any other archive reads "📦 Archived Spool #N";
  - then "moved to UNASSIGNED" only when the write blanked the location of a
    spool that had one, "moved to <place>" for a place the write named, and
    otherwise where the spool is ("still at CR-SHELF", "still Unassigned"), the
    place escaped (the Activity Log is HTML, and a Spoolman location is free text).

The REAL update_spool runs over tests/spoolman_extra_fake.SpoolmanHTTPFake (its
PATCH made to refuse) and over tests/deduct_wire_harness.WeightWireSpoolman (a
PATCH that lands and then times out, or times out and never lands).

Base proof (9c40996, R1-1 in): every test marked RED fails there; the controls pass.

Review R4-3 (2026-11-09): when FCC's own read of the spool before the write
fails, it can't know whether the spool was archived already, or already where
the write puts it (a charge on a spool archived by hand sends `archived: true`
and its own place), so the line says only the state: "📦 Spool #57 is archived —
at CR-SHELF (FCC couldn't read it before this write)". The tests marked RED under
that heading fail on 01ef59e.
"""
from __future__ import annotations

import copy
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import spoolman_api as sm_api  # noqa: E402
import state  # noqa: E402
from deduct_wire_harness import WeightWireSpoolman  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake, _Resp  # noqa: E402

SPOOL_FIELDS = [
    *[{"key": k, "field_type": "text", "name": k} for k in (
        "container_slot", "physical_source", "physical_source_slot",
        "fcc_pre_archive_location", "fcc_pre_box_location", "fcc_pre_audit_location")],
    {"key": "needs_label_print", "field_type": "boolean", "name": "Needs Label Print"},
]

# The message inside the swatch markup add_log_entry wraps a coloured line in.
_MSG = re.compile(r'<span style="vertical-align:middle;">(.*)</span>$', re.S)


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


@pytest.fixture(autouse=True)
def _no_destination_reads(monkeypatch):
    """Where an un-archived spool goes (Group 42.3c) is its note's place, with no
    read of locations.json or Spoolman. 42.3c has its own tests."""
    monkeypatch.setattr(sm_api, "_unarchive_destination", lambda existing, prev, remaining: (str(prev), None))


def _msgs(icon):
    """The Activity Log's lines starting with `icon`, oldest first, as text."""
    out = []
    for entry in reversed(state.RECENT_LOGS):
        m = _MSG.search(str(entry.get("msg", "")))
        text = m.group(1) if m else str(entry.get("msg", ""))
        if text.startswith(icon):
            out.append(text)
    return out


def _clear_caches():
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(sm_api, name, {}).clear()


@pytest.fixture
def http(monkeypatch):
    """spoolman_api's HTTP seam on a Spoolman 0.27 (SpoolmanHTTPFake). `refuse`
    makes every PATCH answer 400 with nothing stored. No printer map, so the
    archive edge's box release reads no file."""
    fake = SpoolmanHTTPFake(version="0.27.0", fields={"spool": copy.deepcopy(SPOOL_FIELDS)})
    fake.refuse = False

    def patch_(url, json=None, timeout=None, **kw):  # noqa: A002 — requests' kwarg
        if fake.refuse:
            fake.patches.append(("spool", int(str(url).rstrip("/").rsplit("/", 1)[-1]), copy.deepcopy(json)))
            return _Resp(400, {"message": "refused (test)"})
        return fake.patch(url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(sm_api.config_loader, "get_api_urls", lambda: ("http://sm.test", "http://fb"))
    monkeypatch.setattr(sm_api.requests, "get", fake.get)
    monkeypatch.setattr(sm_api.requests, "patch", patch_)
    monkeypatch.setattr(sm_api.locations_db, "get_active_printer_map", lambda *a, **k: {})
    _clear_caches()
    yield fake
    _clear_caches()


def _in_stock(fake, location="CR-SHELF"):
    """#57 in stock at `location`: 1000 g spool, 300 g used, so 700 g left."""
    fake.add("spool", 57, {"needs_label_print": "false"},
             location=location, initial_weight=1000.0, used_weight=300.0, archived=False)


def _archived_empty_with_a_note(fake):
    """#57 archived empty off CR-SHELF by the edge: Unassigned, its note saying where."""
    fake.add("spool", 57, {"fcc_pre_archive_location": '"CR-SHELF"'},
             location="", initial_weight=1000.0, used_weight=1000.0, archived=True)


# ---- a write that doesn't land logs nothing ------------------------------------------------------------

@pytest.mark.parametrize("write", [
    {"used_weight": 1000},
    {"remaining_weight": 0},
    {"remaining_weight": 0, "archived": True},
    {"remaining_weight": -5, "archived": True},
    {"archived": True},
], ids=["used-to-empty", "weight-left-0", "fallback-switch-on", "dev-refusal", "archived-box"])
def test_a_write_spoolman_refuses_logs_no_archive_line(http, write):
    """RED on 9c40996: the line was written before the PATCH, so a refused write
    read in the Activity Log as archived (and moved to UNASSIGNED) while the spool
    stayed in stock on its shelf."""
    _in_stock(http)
    http.refuse = True
    assert sm_api.update_spool(57, dict(write)) is None
    assert sm_api.LAST_SPOOLMAN_ERROR.startswith("HTTP 400"), sm_api.LAST_SPOOLMAN_ERROR
    rec = http.records["spool"][57]
    assert rec["archived"] is False and rec["location"] == "CR-SHELF", rec
    assert _msgs("📦") == [], state.RECENT_LOGS


@pytest.mark.parametrize("write", [{"used_weight": 600}, {"archived": False}], ids=["refill", "untick"])
def test_a_refill_spoolman_refuses_logs_no_unarchive_line(http, write):
    """RED on 9c40996: "📤 Auto-unarchived …" / "📤 Un-archived …" came before the
    PATCH, so a refused refill read as back in stock."""
    _archived_empty_with_a_note(http)
    http.refuse = True
    assert sm_api.update_spool(57, dict(write)) is None
    assert http.records["spool"][57]["archived"] is True
    assert _msgs("📤") == [], state.RECENT_LOGS


@pytest.mark.parametrize("make, write, icon", [
    (_in_stock, {"used_weight": 1000}, "📦"),
    (_archived_empty_with_a_note, {"used_weight": 600}, "📤"),
], ids=["archive", "refill"])
def test_a_write_fcc_refuses_before_sending_logs_nothing(http, monkeypatch, make, write, icon):
    """FCC refuses the write itself when its read of the spool's extras fails (a
    partial `extra` could wipe the siblings): nothing is sent, and nothing is
    logged as archived or back in stock. RED on 9c40996."""
    make(http)
    monkeypatch.setattr(sm_api, "_get_raw_extras", lambda entity, eid: None)
    assert sm_api.update_spool(57, dict(write)) is None
    assert sm_api.LAST_SPOOLMAN_ERROR == sm_api.PREMERGE_READ_REFUSAL
    assert http.patches == []
    assert _msgs(icon) == [], state.RECENT_LOGS


# ---- a write that lands: the line says what it did -----------------------------------------------------

def test_control_the_edges_archive_keeps_its_words(http):
    """Control (green on 9c40996 too): weighed to empty, the edge archives the spool
    and takes it off its shelf."""
    _in_stock(http)
    assert sm_api.update_spool(57, {"used_weight": 1000}) is not None, sm_api.LAST_SPOOLMAN_ERROR
    assert http.records["spool"][57]["location"] == ""
    assert _msgs("📦") == ["📦 Auto-archived Spool #57 (remaining weight hit 0) — moved to UNASSIGNED"]


def test_control_the_fallback_row_with_auto_archive_on_keeps_its_words(http):
    """Control (green on 9c40996 too): the weigh-out row's fallback, switch on,
    sends its own `archived: true` with the weight left; the weight did hit 0 and
    the edge took the spool off its shelf, so today's words are true."""
    _in_stock(http)
    assert sm_api.update_spool(57, {"remaining_weight": 0, "archived": True}) is not None
    assert _msgs("📦") == ["📦 Auto-archived Spool #57 (remaining weight hit 0) — moved to UNASSIGNED"]


def test_a_callers_own_archive_with_weight_left_says_where_the_spool_is(http):
    """The wizard's Archived box on a spool with 700 g left at CR-SHELF: archived
    in place. RED on 9c40996: "📦 Auto-archived Spool #57 (remaining weight hit 0)
    — moved to UNASSIGNED"."""
    _in_stock(http)
    assert sm_api.update_spool(57, {"archived": True}) is not None, sm_api.LAST_SPOOLMAN_ERROR
    rec = http.records["spool"][57]
    assert rec["archived"] is True and rec["location"] == "CR-SHELF", rec
    assert _msgs("📦") == ["📦 Archived Spool #57 — still at CR-SHELF"], state.RECENT_LOGS


def test_a_callers_own_archive_that_takes_it_off_its_place_says_so(http):
    """An archive with weight left that also blanks the location (as the wizard's
    take-off before a move writes it). RED on 9c40996: it said the weight hit 0."""
    _in_stock(http)
    assert sm_api.update_spool(57, {"archived": True, "location": ""}) is not None
    assert _msgs("📦") == ["📦 Archived Spool #57 — moved to UNASSIGNED"], state.RECENT_LOGS


def test_the_edges_archive_into_a_place_the_caller_names_says_that_place(http):
    """Weighed to empty by a write that names a new place: the edge archives it but
    leaves the caller's location. RED on 9c40996: "— moved to UNASSIGNED"."""
    _in_stock(http)
    assert sm_api.update_spool(57, {"used_weight": 1000, "location": "CR-CT-2-R1"}) is not None
    assert http.records["spool"][57]["location"] == "CR-CT-2-R1"
    assert _msgs("📦") == ["📦 Auto-archived Spool #57 (remaining weight hit 0) — moved to CR-CT-2-R1"]


def test_the_edges_archive_of_a_spool_already_unassigned_moves_nothing(http):
    """A spool in stock with no location weighed to empty: the write blanks a
    location that was already blank. RED on 9c40996: "— moved to UNASSIGNED"."""
    _in_stock(http, location="")
    assert sm_api.update_spool(57, {"used_weight": 1000}) is not None
    assert _msgs("📦") == ["📦 Auto-archived Spool #57 (remaining weight hit 0) — still Unassigned"]


UNREAD = " (FCC couldn't read it before this write)"


def test_an_archive_of_a_spool_fcc_couldnt_read_says_where_spoolman_has_it(http, monkeypatch):
    """Review R1-1's case: FCC's read failed, so the edge didn't run and the page's
    own `archived: true` went out alone. The line says where Spoolman's answer has
    the spool. RED on 9c40996: it said the weight hit 0 and the spool moved to
    UNASSIGNED, neither of which FCC knew or did.

    PIN UPDATED DELIBERATELY (review R4-3): with no read before the write FCC can't
    say this write archived the spool (it may have been archived already), so the
    line is a state, "is archived — at XL-1", and says why it is only that."""
    _in_stock(http, location="XL-1")
    monkeypatch.setattr(sm_api, "get_spool", lambda sid: None)
    assert sm_api.update_spool(57, {"remaining_weight": 0, "archived": True}) is not None
    assert _msgs("📦") == [f"📦 Spool #57 is archived — at XL-1{UNREAD}"], state.RECENT_LOGS


# ---- a spool FCC couldn't read before the write: where it is, never an archive or a move (review R4-3) --

def _archived_by_hand(fake, location="CR-SHELF"):
    """#57 archived by hand at `location` with 700 g left."""
    fake.add("spool", 57, {}, location=location, initial_weight=1000.0, used_weight=300.0, archived=True)


def test_an_unread_spool_charged_in_its_own_place_claims_no_archive_or_move(http, monkeypatch):
    """RED: a print charge on a spool archived by hand sends its weight with
    `archived: true` and its own place (print_deduct._deduct_payload), and FCC's own
    read before the write failed. The spool was archived, and at CR-SHELF, before
    and after: the line says that state and nothing else. On 7c831c6..01ef59e:
    "📦 Archived Spool #57 — moved to CR-SHELF", an archive and a move that never
    happened."""
    _archived_by_hand(http)
    monkeypatch.setattr(sm_api, "get_spool", lambda sid: None)
    assert sm_api.update_spool(57, {"used_weight": 310.0, "archived": True, "location": "CR-SHELF"}) is not None
    rec = http.records["spool"][57]
    assert rec["archived"] is True and rec["location"] == "CR-SHELF", rec
    assert _msgs("📦") == [f"📦 Spool #57 is archived — at CR-SHELF{UNREAD}"], state.RECENT_LOGS


def test_an_unread_archived_spool_weighed_empty_where_it_is_claims_no_archive(http, monkeypatch):
    """RED: the weigh-out fallback (switch on) weighs a spool already archived at
    XL-1 to 0 g, and FCC's read failed: "📦 Archived Spool #57 — still at XL-1" on
    the base, though nothing archived it."""
    _archived_by_hand(http, location="XL-1")
    monkeypatch.setattr(sm_api, "get_spool", lambda sid: None)
    assert sm_api.update_spool(57, {"remaining_weight": 0, "archived": True}) is not None
    assert _msgs("📦") == [f"📦 Spool #57 is archived — at XL-1{UNREAD}"], state.RECENT_LOGS


@pytest.mark.parametrize("data, after, line", [
    ({"archived": True}, None, f"📦 Spool #57 is archived{UNREAD}"),
    ({"archived": True, "location": ""}, None, f"📦 Spool #57 is archived — Unassigned{UNREAD}"),
    ({"archived": True}, {"id": 57, "location": ""}, f"📦 Spool #57 is archived — Unassigned{UNREAD}"),
    ({"archived": True, "location": "Bin <2>"}, {"id": 57, "location": "Bin <2>"},
     f"📦 Spool #57 is archived — at Bin &lt;2&gt;{UNREAD}"),
    ({"archived": True}, {"message": "database is locked"}, f"📦 Spool #57 is archived{UNREAD}"),
], ids=["nothing-said", "write-blanks-it", "answer-unassigned", "escaped", "answer-not-a-record"])
def test_the_unread_line_says_only_where_the_spool_is(data, after, line):
    """RED (the words are new): with no record read before the write (`existing`
    {}), the line is a state: where Spoolman's answer has the spool, else the place
    the write named, else no place, and never "moved to" or "Archived Spool"."""
    assert sm_api._archive_line(57, data, {}, after, False) == line


def test_control_a_read_spools_line_is_unchanged(http):
    """Control (green on the base too): with FCC's read the line says what the
    write did, as before."""
    _in_stock(http)
    assert sm_api.update_spool(57, {"archived": True, "location": ""}) is not None
    assert _msgs("📦") == ["📦 Archived Spool #57 — moved to UNASSIGNED"], state.RECENT_LOGS


def test_a_place_in_the_line_is_escaped(http):
    """The Activity Log is HTML, and a Spoolman location is free text. (Guards the
    new words: on 9c40996 the line named no place at all.)"""
    _in_stock(http, location="Shelf <2> & Co")
    assert sm_api.update_spool(57, {"archived": True}) is not None
    assert _msgs("📦") == ["📦 Archived Spool #57 — still at Shelf &lt;2&gt; &amp; Co"], state.RECENT_LOGS


def test_control_a_landed_refill_logs_its_line(http):
    """Control (green on 9c40996 too): the refill lands and says so."""
    _archived_empty_with_a_note(http)
    assert sm_api.update_spool(57, {"used_weight": 600}) is not None, sm_api.LAST_SPOOLMAN_ERROR
    assert _msgs("📤") == ["📤 Auto-unarchived Spool #57 (weight refilled) — restored to CR-SHELF"]


def test_control_a_landed_untick_logs_its_line(http):
    """Control (green on 9c40996 too): an untick with weight left names where the
    spool is."""
    http.add("spool", 57, {}, location="CR-SHELF", initial_weight=1000.0, used_weight=300.0, archived=True)
    assert sm_api.update_spool(57, {"archived": False}) is not None, sm_api.LAST_SPOOLMAN_ERROR
    assert _msgs("📤") == ["📤 Un-archived Spool #57 (back in stock) — now at CR-SHELF"]


# ---- a write whose answer timed out: logged once a re-read shows it landed -----------------------------

@pytest.fixture
def wire(monkeypatch):
    """The REAL get_spool / update_spool over WeightWireSpoolman's wire:
    `patch_fails` lands the PATCH and then times out, `patch_lost` times out with
    nothing stored."""
    def make(spools, **kw):
        sm = WeightWireSpoolman(spools, **kw)
        monkeypatch.setattr(sm_api.config_loader, "get_api_urls", lambda: ("http://sm", "http://fb"))
        monkeypatch.setattr(sm_api.requests, "get", sm._get)
        monkeypatch.setattr(sm_api.requests, "patch", sm._patch)
        monkeypatch.setattr(sm_api.locations_db, "get_active_printer_map", lambda *a, **k: {})
        return sm
    return make


def _shelf_spool(archived=False, used=300.0, location="CR-SHELF", **extra):
    return {50: {"location": location, "initial_weight": 1000.0, "used_weight": used,
                 "archived": archived, "extra": dict(extra)}}


def test_control_an_archive_that_lands_and_times_out_is_logged_from_the_re_read(wire):
    """Control (green on 9c40996 too, which logged it before the PATCH): the write
    landed, so the line is written once the re-read shows it archived."""
    sm = wire(_shelf_spool(), patch_fails={50})
    assert sm_api.update_spool(50, {"used_weight": 1000}) is None
    assert sm.spools[50]["archived"] is True and sm.spools[50]["location"] == ""
    assert _msgs("📦") == ["📦 Auto-archived Spool #50 (remaining weight hit 0) — moved to UNASSIGNED"]


def test_an_archive_that_times_out_and_never_lands_logs_nothing(wire):
    """RED on 9c40996: the line was written before a PATCH that never landed."""
    sm = wire(_shelf_spool(), patch_lost={50})
    assert sm_api.update_spool(50, {"used_weight": 1000}) is None
    assert sm.spools[50]["archived"] is False and sm.spools[50]["location"] == "CR-SHELF"
    assert _msgs("📦") == [], state.RECENT_LOGS


def test_a_callers_own_archive_that_lands_and_times_out_says_where_the_spool_is(wire):
    """The Archived box's write landed in place and its answer timed out: the
    re-read shows it archived at CR-SHELF. RED on 9c40996 (the false words)."""
    sm = wire(_shelf_spool(), patch_fails={50})
    assert sm_api.update_spool(50, {"archived": True}) is None
    assert sm.spools[50]["archived"] is True and sm.spools[50]["location"] == "CR-SHELF"
    assert _msgs("📦") == ["📦 Archived Spool #50 — still at CR-SHELF"], state.RECENT_LOGS


def test_an_unread_spools_archive_that_lands_and_times_out_says_where_it_is(wire, monkeypatch):
    """RED: FCC's read before the write failed, the charge's PATCH landed and its
    answer timed out, and the re-read shows the spool archived at CR-SHELF: the line
    is the state, from the re-read. On the base: "📦 Archived Spool #50 — moved to
    CR-SHELF"."""
    sm = wire(_shelf_spool(archived=True), patch_fails={50})
    real = sm_api.get_spool
    reads = []

    def first_read_fails(sid):
        reads.append(sid)
        return None if len(reads) == 1 else real(sid)

    monkeypatch.setattr(sm_api, "get_spool", first_read_fails)
    assert sm_api.update_spool(50, {"used_weight": 310.0, "archived": True, "location": "CR-SHELF"}) is None
    assert len(reads) == 2, reads
    assert sm.spools[50]["archived"] is True and sm.spools[50]["location"] == "CR-SHELF"
    assert _msgs("📦") == [f"📦 Spool #50 is archived — at CR-SHELF{UNREAD}"], state.RECENT_LOGS


def test_control_a_refill_that_lands_and_times_out_is_logged_from_the_re_read(wire):
    """Control (green on 9c40996 too, which logged it before the PATCH)."""
    sm = wire(_shelf_spool(archived=True, used=1000.0, location="", fcc_pre_archive_location="CR-SHELF"),
              patch_fails={50})
    assert sm_api.update_spool(50, {"used_weight": 600}) is None
    assert sm.spools[50]["archived"] is False and sm.spools[50]["location"] == "CR-SHELF"
    assert _msgs("📤") == ["📤 Auto-unarchived Spool #50 (weight refilled) — restored to CR-SHELF"]


def test_a_refill_that_times_out_and_never_lands_logs_nothing(wire):
    """RED on 9c40996: the line was written before a PATCH that never landed."""
    sm = wire(_shelf_spool(archived=True, used=1000.0, location="", fcc_pre_archive_location="CR-SHELF"),
              patch_lost={50})
    assert sm_api.update_spool(50, {"used_weight": 600}) is None
    assert sm.spools[50]["archived"] is True
    assert _msgs("📤") == [], state.RECENT_LOGS
