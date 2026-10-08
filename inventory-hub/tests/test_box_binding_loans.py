"""`borrow_box_bindings` puts a borrowed dev Dryer Box back to a FIXED baseline.

2026-09-13 sweep triage, item 3. Ten E2E files borrowed a real dev box (mostly
PM-DB-1 slot 1 -> XL-1) by snapshotting its slot_targets at setup and PUTting
that snapshot back at teardown. That restores whatever was OBSERVED, so a run
interrupted before teardown left its temporary binding behind, and every later
run "restored" the leftover as if it were real: dev carried a stale PM-DB-1
slot 1 -> XL-1 until Derek spotted it on 2026-09-13.

These tests drive `conftest.BoxBindingLoans` (the logic behind the fixture)
against an in-memory fake of the two bindings endpoints, so they run under
--offline and never contact the container.
"""
from __future__ import annotations

import glob
import json
import os
import re

import pytest
import requests

import conftest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(TESTS_DIR, "..", "..", "setup-and-rebuild", "seeds", "locations-seed.json")
API = "http://fcc.invalid"   # never contacted: FakeBindingsApi answers every call
Failed = pytest.fail.Exception


class _Resp:
    def __init__(self, status: int, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeBindingsApi:
    """GET / PUT /api/dryer_box/<box>/bindings over an in-memory store, with the
    real endpoint's storage rule (a null target is dropped)."""

    def __init__(self, store, reject=None, unreachable=()):
        self.store = {box: dict(t) for box, t in store.items()}
        self.calls = []
        self.reject = reject or (lambda box, targets: False)
        self.unreachable = set(unreachable)

    def _box(self, url):
        m = re.fullmatch(r"http://fcc\.invalid/api/dryer_box/([^/]+)/bindings", url)
        assert m, f"unexpected URL {url!r}"
        return m.group(1)

    def get(self, url, timeout=None):
        box = self._box(url)
        self.calls.append(("GET", box, None))
        if box in self.unreachable:
            raise requests.ConnectionError("container went away")
        if box not in self.store:
            return _Resp(404, {"error": "not_a_dryer_box", "location": box})
        return _Resp(200, {"location": box, "slot_targets": dict(self.store[box])})

    def put(self, url, json=None, timeout=None):
        box = self._box(url)
        targets = (json or {}).get("slot_targets") or {}
        self.calls.append(("PUT", box, dict(targets)))
        if box in self.unreachable:
            raise requests.ConnectionError("container went away")
        if self.reject(box, targets):
            return _Resp(400, {"error": "validation_failed", "location": box})
        self.store[box] = {str(k): v for k, v in targets.items() if v}
        return _Resp(200, {"location": box, "slot_targets": dict(self.store[box]), "warnings": []})

    def puts(self):
        return [(box, body) for method, box, body in self.calls if method == "PUT"]


def _loans(api: FakeBindingsApi, baselines=None) -> conftest.BoxBindingLoans:
    return conftest.BoxBindingLoans(API, http=api, baselines=baselines)


# ---------------------------------------------------------------------------
# The rule that was missing: a leftover is refused, never restored
# ---------------------------------------------------------------------------

def test_an_interrupted_run_cannot_make_its_binding_permanent():
    """Run 1 borrows PM-DB-1 and is killed before teardown. Run 2 must refuse
    to borrow the box (and write nothing) instead of adopting the leftover as
    the state to restore. The old fixtures snapshotted it and PUT it back."""
    api = FakeBindingsApi({"PM-DB-1": {}})
    run1 = _loans(api)
    run1.borrow("PM-DB-1", {"1": "XL-1"})
    # ...interrupted: run1.restore_all() never runs.
    assert api.store["PM-DB-1"] == {"1": "XL-1"}

    run2 = _loans(api)
    writes_before = len(api.puts())
    with pytest.raises(Failed) as exc:
        run2.borrow("PM-DB-1", {"1": "XL-1"})
    msg = str(exc.value)
    assert "PM-DB-1 is not at its test baseline" in msg, msg
    assert "{'1': 'XL-1'}" in msg and "expected slot_targets: {}" in msg, msg
    assert "Slot -> Toolhead Feeds" in msg, "the message must say how to put the box back"
    assert len(api.puts()) == writes_before, "a refused borrow must not write anything"

    run2.restore_all()
    assert len(api.puts()) == writes_before, "a box that was never borrowed must not be 'restored'"
    assert api.store["PM-DB-1"] == {"1": "XL-1"}, "the leftover is left for a human to judge"


def test_borrow_checks_the_baseline_writes_and_teardown_restores_the_baseline():
    api = FakeBindingsApi({"PM-DB-1": {}})
    loans = _loans(api)
    assert loans.borrow("PM-DB-1", {"1": "XL-1"}) == {}
    assert api.calls[0] == ("GET", "PM-DB-1", None), "the baseline check must come first"
    assert api.store["PM-DB-1"] == {"1": "XL-1"}

    loans.restore_all()
    assert api.puts()[-1] == ("PM-DB-1", {})
    assert api.store["PM-DB-1"] == {}
    assert loans.borrowed == []


def test_teardown_restores_the_baseline_even_after_the_test_changed_more():
    """A UI test that saves extra bindings (e.g. slot 2 via the Feeds editor)
    still ends with the baseline, not with any snapshot of the box."""
    api = FakeBindingsApi({"PM-DB-1": {}})
    loans = _loans(api)
    loans.borrow("PM-DB-1", {"1": "XL-1"})
    api.store["PM-DB-1"] = {"1": "XL-1", "2": "XL-2"}   # what the test did through the UI
    loans.restore_all()
    assert api.store["PM-DB-1"] == {}


def test_check_only_borrow_writes_nothing_until_teardown():
    api = FakeBindingsApi({"PM-DB-5": {}})
    loans = _loans(api)
    loans.borrow("PM-DB-5")
    assert api.puts() == []
    loans.restore_all()
    assert api.puts() == [("PM-DB-5", {})]


def test_borrowing_the_same_box_twice_checks_once_and_restores_once():
    api = FakeBindingsApi({"PM-DB-1": {}})
    loans = _loans(api)
    loans.borrow("PM-DB-1", {"1": "XL-1"})
    loans.borrow("PM-DB-1", {"1": "XL-2"})    # no refusal: this test already owns it
    assert [c for c in api.calls if c[0] == "GET"] == [("GET", "PM-DB-1", None)]
    assert api.store["PM-DB-1"] == {"1": "XL-2"}
    loans.restore_all()
    assert api.puts().count(("PM-DB-1", {})) == 1


def test_unbound_slots_compare_equal_to_absent_ones():
    """Storage drops a null target, but a reply carrying one must not read as a
    leftover binding."""
    assert conftest._normalized_slot_targets({"1": None, "2": "", 3: "XL-3"}) == {"3": "XL-3"}
    assert conftest._normalized_slot_targets(None) == {}

    class _NullSlotApi(FakeBindingsApi):
        def get(self, url, timeout=None):
            self.calls.append(("GET", self._box(url), None))
            return _Resp(200, {"slot_targets": {"1": None}})

    loans = _loans(_NullSlotApi({"PM-DB-1": {}}))
    assert loans.borrow("PM-DB-1") == {}


# ---------------------------------------------------------------------------
# Loud failures
# ---------------------------------------------------------------------------

def test_a_box_without_a_baseline_cannot_be_borrowed():
    api = FakeBindingsApi({"LR-MDB-1": {"1": "XL-1"}})
    with pytest.raises(Failed) as exc:
        _loans(api).borrow("LR-MDB-1", {"2": "XL-2"})
    assert "DEV_BOX_BINDING_BASELINES" in str(exc.value)
    assert api.calls == [], "no request may go out for a box with no baseline"


def test_a_box_missing_from_dev_fails_loudly():
    api = FakeBindingsApi({})
    with pytest.raises(Failed) as exc:
        _loans(api, baselines={"PM-DB-2": {}}).borrow("PM-DB-2")
    assert "404" in str(exc.value) and "PM-DB-2" in str(exc.value)


def test_an_unreachable_container_fails_the_borrow_loudly():
    api = FakeBindingsApi({"PM-DB-4": {}}, unreachable={"PM-DB-4"})
    with pytest.raises(Failed) as exc:
        _loans(api).borrow("PM-DB-4", {"1": "XL-1"})
    assert "could not read PM-DB-4" in str(exc.value)


def test_a_rejected_setup_write_fails_and_the_box_is_still_restored():
    api = FakeBindingsApi({"PM-DB-4": {}}, reject=lambda box, targets: targets.get("1") == "XL-999")
    loans = _loans(api)
    with pytest.raises(Failed) as exc:
        loans.borrow("PM-DB-4", {"1": "XL-999"})
    assert "could not set PM-DB-4" in str(exc.value) and "HTTP 400" in str(exc.value)
    assert loans.borrowed == ["PM-DB-4"], "registered before the write, so teardown still restores it"
    loans.restore_all()
    assert api.puts()[-1] == ("PM-DB-4", {})


def test_restore_tries_every_box_then_names_the_ones_it_could_not_restore():
    api = FakeBindingsApi({"PM-DB-1": {}, "PM-DB-5": {}})
    loans = _loans(api)
    loans.borrow("PM-DB-1", {"1": "XL-1"})
    loans.borrow("PM-DB-5", {"1": "XL-2"})
    api.reject = lambda box, targets: box == "PM-DB-1"
    with pytest.raises(Failed) as exc:
        loans.restore_all()
    msg = str(exc.value)
    assert "PM-DB-1" in msg and "HTTP 400" in msg, msg
    assert "PM-DB-5" not in msg, msg
    assert api.store["PM-DB-5"] == {}, "a failure on one box must not stop the others"
    assert loans.borrowed == []


# ---------------------------------------------------------------------------
# The baselines and the E2E suite stay in step
# ---------------------------------------------------------------------------

def test_baselines_match_the_reset_dev_seed():
    """`pytest --reset-dev` restores the committed seed; it must restore exactly
    the state the fixture demands, or a freshly reset dev would refuse to run."""
    with open(SEED, encoding="utf-8") as fh:
        rows = json.load(fh)
    by_id = {str(r.get("LocationID", "")).upper(): r for r in rows if isinstance(r, dict)}
    assert conftest.DEV_BOX_BINDING_BASELINES, "no baselines registered"
    for box, baseline in conftest.DEV_BOX_BINDING_BASELINES.items():
        row = by_id.get(box.upper())
        assert row is not None, f"{box} is not in the reset-dev seed"
        assert row.get("Type") == "Dryer Box", f"{box} is not a Dryer Box in the seed: {row}"
        seeded = conftest._normalized_slot_targets((row.get("extra") or {}).get("slot_targets"))
        assert seeded == conftest._normalized_slot_targets(baseline), (
            f"{box}: seed slot_targets {seeded!r} != fixture baseline {baseline!r}")


def test_borrow_box_bindings_is_gated_offline():
    assert "borrow_box_bindings" in conftest.CONTAINER_FIXTURES


# The snapshot-and-restore idiom all ten converted files used, in its two halves:
#     original = snap.get("slot_targets", {})                  # read what is there
#     requests.put(..., json={"slot_targets": original})       # put it back later
# The write half does the damage, and it does not care what the snapshot
# variable is called, so it matches ANY value that is not a dict literal.
_OBSERVED_SNAPSHOT_READ = re.compile(r"""snap\.get\(\s*["']slot_targets["']""")
_NON_LITERAL_BINDINGS_PUT = re.compile(r"""json\s*=\s*\{\s*["']slot_targets["']\s*:\s*(?![\s{])""")

# Test files that still restore an observed binding on a baseline box, each with
# why it has not been converted. An entry that stops matching fails the canary,
# so converting a file forces its entry out of this list.
_OBSERVED_RESTORE_ALLOWED = {
    "test_printer_status_widget.py": (
        "test_widget_shows_unbound_printers_with_placeholder clears EVERY dryer box "
        "in dev, real multi-slot setups included, and PUTs what it observed back. A "
        "fixed baseline for the whole fleet needs Derek's decision; standalone follow-up."
    ),
}


def _observed_restore_idioms(src):
    """The halves of the snapshot-and-restore idiom present in `src` ([] if none)."""
    found = []
    if _OBSERVED_SNAPSHOT_READ.search(src):
        found.append('reads snap.get("slot_targets")')
    if _NON_LITERAL_BINDINGS_PUT.search(src):
        found.append('PUTs json={"slot_targets": <non-literal>}')
    return found


@pytest.mark.parametrize("src", [
    'original = snap.get("slot_targets", {})',
    'requests.put(url, json={"slot_targets": original}, timeout=5)',
    "requests.put(url, json={'slot_targets': box_originals[b]}, timeout=5)",
    'requests.put(\n    url,\n    json={\n        "slot_targets": saved_before_test,\n    },\n)',
])
def test_the_canary_recognises_the_observed_restore_idiom_in_its_variants(src):
    """Review 2026-09-13: the canary matched only the literal `snap.get(...)` read,
    so test_printer_status_widget.py's `box_originals[b]` restore walked past it."""
    assert _observed_restore_idioms(src), src


@pytest.mark.parametrize("src", [
    'requests.put(url, json={"slot_targets": {}}, timeout=5)',
    'requests.put(url, json={"slot_targets": {"1": "XL-1"}})',
    'requests.put(url, json={ "slot_targets" :\n    {"1": TEST_TOOLHEAD}})',
    'last = requests.get(url, timeout=5).json().get("slot_targets", {})',
    'rows = [{"LocationID": "PM-DB-1", "extra": {"slot_targets": slot_targets}}]',
])
def test_the_canary_leaves_literal_payloads_and_plain_reads_alone(src):
    """A literal payload writes a known state, a poll only reads, and a fake
    locations row is not a PUT; none of them restores an observed binding."""
    assert _observed_restore_idioms(src) == [], src


def test_no_test_file_restores_an_observed_snapshot_of_a_baseline_box():
    """Source canary: a test module that names a baseline box must not put an
    observed binding back on it; borrow the box through `borrow_box_bindings`.

    What is actually enforced is the idiom above, in either half: a
    `snap.get("slot_targets", ...)` read, or a `json={"slot_targets": ...}` PUT
    payload whose value is not a dict literal. A restore spelled another way
    (say, a payload dict built in a variable first) is not caught.
    """
    offenders, allowed_matches = [], set()
    this_file = os.path.basename(__file__)
    for path in sorted(glob.glob(os.path.join(TESTS_DIR, "test_*.py"))):
        name = os.path.basename(path)
        if name == this_file:  # the detector's own samples above spell the idiom out
            continue
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        if not any(f'"{box}"' in src for box in conftest.DEV_BOX_BINDING_BASELINES):
            continue
        idioms = _observed_restore_idioms(src)
        if not idioms:
            continue
        if name in _OBSERVED_RESTORE_ALLOWED:
            allowed_matches.add(name)
        else:
            offenders.append(f"{name} ({'; '.join(idioms)})")
    assert offenders == [], (
        f"these files snapshot a baseline box's slot_targets and put the snapshot back; "
        f"use the borrow_box_bindings fixture instead: {offenders}")
    stale = sorted(set(_OBSERVED_RESTORE_ALLOWED) - allowed_matches)
    assert stale == [], (
        f"_OBSERVED_RESTORE_ALLOWED lists files that no longer restore an observed "
        f"binding on a baseline box; drop them from the list: {stale}")
