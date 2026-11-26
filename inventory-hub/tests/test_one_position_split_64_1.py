"""Group 64.1: a one-position printer's swap split charges each gram once.

On a printer whose heads share one position (an MMU's slots), an MMU-profile file
can mark tool 1 although the printer has one head: its usage is {1: g}, and the
figures at its recorded swaps, measured in the same walk, are keyed by tool 1 too.
`_route_completion_to_review` split the head at position 0 (the old fold read any
sole entry as position 0's), and `_uncharged_usage` left the same grams on a T1
line: an Apply as shown recorded a false shortfall, and a spool picked on the T1
line was charged them twice (found 2026-11-12 by the print-end hotfix's review).
A cousin: a multi-material footer {0: 30, 1: 50} whose swap came before T0 first
printed (figures {1: 12}) split T0's 30 g as 12 + 18, T1's figure read as T0's.

Pinned here, on the real functions (the wire harness answers Spoolman; only the
download is stood in for):
  - the usage and the swaps' figures are folded onto the one position together
    (`_fold_sole_tool`), the figure read by the one tool the usage names;
  - the item's shape gives one row per spool and no uncharged line;
  - several tools on one position, or swaps at several positions, aren't split:
    the head asks;
  - a whole completion on a one-position printer: a plain one-tool print is
    charged as before, a one-tool swap is split with no line, and a two-tool
    print's swapped head is held, every gram of the footer on the card once.

HEAD proof: the tests marked "red on eb94846" fail on `dev` before Group 64; the
plain print and the one-tool split through the whole path pass there by design
(the whole path folded the usage, and the old fold read the figure by luck).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import cancel_fetch_store  # noqa: E402
import cancel_review_store  # noqa: E402
import print_deduct  # noqa: E402
import print_deduct_ledger  # noqa: E402
import print_monitor  # noqa: E402
import prusalink_api  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from deduct_wire_harness import WeightWireSpoolman, _start, _stop  # noqa: E402

P = "MMU PRINTER"
HEAD = "MMU-1"
JOB = "J-64"
SWAP = [{"seq": 0, "position": 0, "progress": 0.4, "from_sid": 100, "to_sid": 200, "runout": False}]
PT = print_deduct._swap_point(SWAP[0])
END = {"heads": [{"toolhead": HEAD, "position": 0, "sid": 200, "sids": [200]}],
       "source": "print_end", "at": "2026-11-20 01:00:00"}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(spoolman_api, "LAST_SPOOLMAN_ERROR", None)
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", False)
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    monkeypatch.setattr(print_deduct.config_loader, "load_config", lambda: {})
    monkeypatch.setattr(state, "add_log_entry", lambda *a, **k: None)


def _spool(used, loc):
    return {"used_weight": used, "initial_weight": 1000.0, "archived": False,
            "location": loc, "filament": {"weight": 1000.0}, "extra": {}}


class OnePosition:
    """A printer with one head (position 0): #100 started on it, #200 is on it now."""

    def __init__(self, on_head=(200,)):
        self.sm = WeightWireSpoolman({100: _spool(100.0, "SHELF-1"), 200: _spool(10.0, HEAD)})
        self.at = {HEAD: list(on_head)}

    def __enter__(self):
        active = [(HEAD, {"position": 0, "printer_name": P})]
        self._ctx = [
            patch.object(print_deduct.locations_db, "get_active_printer_map",
                         return_value={HEAD: {"printer_name": P, "position": 0}}),
            patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=active),
            patch.object(spoolman_api, "get_spools_at_location",
                         side_effect=lambda loc: list(self.at.get(str(loc).upper(), []))),
            patch.object(spoolman_api, "select_deduct_targets",
                         side_effect=lambda loc: (list(self.at.get(str(loc).upper(), [])),
                                                  len(self.at.get(str(loc).upper(), [])) > 1)),
            patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
            patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "ff0000"}),
            patch.object(spoolman_api.requests, "get", side_effect=self.sm._get),
            patch.object(spoolman_api.requests, "patch", side_effect=self.sm._patch),
            patch.object(print_deduct.prusalink_api, "fetch_printer_credentials",
                         return_value={"ip_address": "1.2.3.4", "api_key": "k"}),
        ]
        _start(self._ctx)
        return self

    def __exit__(self, *exc):
        _stop(self._ctx)


def _gcode(grams, mm_each=10):
    """A plain-text print: each tool in `grams` prints 10 moves of 1 mm in turn, and
    the footer lists every tool up to the last (0 g for a tool that printed none)."""
    tools = max(grams) + 1
    body = ["M83"]
    for t in sorted(grams):
        body.append(f"T{t}")
        body += ["G1 X1 E1"] * mm_each
    mm = ", ".join(str(mm_each if t in grams else 0) for t in range(tools))
    g = ", ".join(str(grams.get(t, 0)) for t in range(tools))
    return "\n".join(body) + f"\n; filament used [mm] = {mm}\n; filament used [g] = {g}\n"


def _download(text):
    def _fetch(ip, key, filename, fraction, extra_fractions=None):
        out = {"gcode": text, "fraction": fraction}
        if extra_fractions:
            out["fractions"] = list(extra_fractions)
        return out
    return patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=_fetch)


def _card():
    return cancel_review_store.get_pending(P, JOB)


def _on_card(rec):
    """Every gram a card puts anywhere: its rows and its uncharged lines."""
    rows = sum(float(r.get("grams") or 0) for r in rec.get("spools") or [])
    held = rec.get("usage_map") if rec.get("kind") == "no_spool" else rec.get("unresolved_usage")
    lines = sum(float(g or 0) for g in (held or {}).values())
    return round(rows + lines, 2)


# --------------------------------------------------------------------------- #
# The real functions                                                           #
# --------------------------------------------------------------------------- #

def test_the_fold_puts_the_usage_and_its_figures_on_the_one_position():
    """Red on eb94846 (no _fold_sole_tool)."""
    with OnePosition():
        usage, cums, sole = print_deduct._fold_sole_tool(P, {1: 50.0}, {PT: {1: 20.0}})
        assert (usage, cums, sole) == ({0: 50.0}, {PT: {0: 20.0}}, 0)
        # A figure the tool lacks is 0 g, never another tool's.
        _, cums, _ = print_deduct._fold_sole_tool(P, {1: 50.0}, {PT: {0: 7.0}})
        assert cums == {PT: {0: 0.0}}
        # Several tools on one position, or several positions: nothing folds.
        assert print_deduct._fold_sole_tool(P, {0: 30.0, 1: 50.0}, {PT: {1: 12.0}})[2] is None
    with patch.object(print_deduct.locations_db, "get_active_printer_map",
                      return_value={"XL-1": {"printer_name": P, "position": 0},
                                    "XL-2": {"printer_name": P, "position": 1}}):
        assert print_deduct._fold_sole_tool(P, {1: 50.0}, {PT: {1: 20.0}}) == ({1: 50.0}, {PT: {1: 20.0}}, None)
    with patch.object(print_deduct.locations_db, "get_active_printer_map", side_effect=OSError("disk")):
        assert print_deduct._fold_sole_tool(P, {1: 50.0})[2] is None


def test_the_items_shape_is_one_row_per_spool_and_no_uncharged_line():
    """The item: a completion whose file charges tool 1, its swap recorded at
    position 0. Red on eb94846: rows 20 + 30 g AND an uncharged T1 line of 50 g."""
    with OnePosition():
        out = print_deduct._route_completion_to_review(
            P, "f.gcode", JOB, {1: 50.0}, "http://fb", [0],
            active_locs=[(HEAD, {"position": 0, "printer_name": P})], swap_log=SWAP,
            start_spools={"0": 100}, swap_cums={PT: {1: 20.0}})
    assert str(out["status"]).startswith("pending"), out
    rec = _card()
    assert sorted((r["sid"], r["grams"]) for r in rec["spools"]) == [(100, 20.0), (200, 30.0)], rec
    assert not rec.get("unresolved_usage"), rec
    assert _on_card(rec) == 50.0


def test_the_items_shape_with_the_print_end_read_is_split_once_too():
    """Red on eb94846: the T1 line was left beside the split."""
    with OnePosition():
        print_deduct._route_completion_to_review(
            P, "f.gcode", JOB, {1: 50.0}, "http://fb", [0],
            active_locs=[(HEAD, {"position": 0, "printer_name": P})], swap_log=SWAP,
            start_spools={"0": 100}, swap_cums={PT: {1: 20.0}},
            heads=END["heads"], heads_source="print_end", heads_read_at=END["at"])
    rec = _card()
    assert sorted((r["sid"], r["grams"]) for r in rec["spools"]) == [(100, 20.0), (200, 30.0)], rec
    assert not rec.get("unresolved_usage"), rec


def test_a_cancels_review_of_the_items_shape_is_split_once_too():
    """The cancel's twin (its review from the print-end read). Red on eb94846: the
    T1 line was left beside the split."""
    with OnePosition():
        heads = print_deduct._usable_heads(END)
        print_deduct._stash_cancel_review_from_heads(
            P, "f.gcode", JOB, 0.9, "http://fb", False, {1: 50.0}, heads, {"0": 100}, SWAP,
            swap_cums={PT: {1: 20.0}})
    rec = _card()
    assert sorted((r["sid"], r["grams"]) for r in rec["spools"]) == [(100, 20.0), (200, 30.0)], rec
    assert not rec.get("unresolved_usage"), rec
    assert _on_card(rec) == 50.0


def test_the_split_reads_the_one_tool_its_usage_names():
    """The split's own rule, on a usage nobody folded. Red on eb94846 (its second
    half): a figure of another tool was read as this one's (7 g up to the swap)."""
    split = print_deduct._compute_swap_split({1: 50.0}, SWAP, {"0": 100}, {PT: {1: 20.0}},
                                             single_position=True)
    assert [(r["sid"], r["grams"]) for r in split[0]] == [(100, 20.0), (200, 30.0)]
    split = print_deduct._compute_swap_split({1: 50.0}, SWAP, {"0": 100}, {PT: {0: 7.0}},
                                             single_position=True)
    assert [(r["sid"], r["grams"]) for r in split[0]] == [(100, 0.0), (200, 50.0)]


def test_several_tools_on_one_position_are_not_split():
    """The cousin. Red on eb94846: T0's 30 g split as 12 + 18, T1's figure read as T0's."""
    split = print_deduct._compute_swap_split({0: 30.0, 1: 50.0}, SWAP, {"0": 100}, {PT: {1: 12.0}},
                                             single_position=True)
    assert split is None
    two_positions = SWAP + [dict(SWAP[0], position=1, seq=1)]
    assert print_deduct._compute_swap_split({0: 50.0}, two_positions, {"0": 100, "1": 300},
                                            {PT: {0: 20.0}}, single_position=True) is None


def test_a_multi_head_split_reads_its_own_position_as_before():
    """Passes before the change by design: an XL-style split is unchanged."""
    swap = [dict(SWAP[0], position=1)]
    split = print_deduct._compute_swap_split({0: 30.0, 1: 50.0}, swap, {"1": 100},
                                             {PT: {0: 9.0, 1: 20.0}}, single_position=False)
    assert [(r["sid"], r["grams"]) for r in split[1]] == [(100, 20.0), (200, 30.0)]


# --------------------------------------------------------------------------- #
# A whole completion through deduct_completed_print                            #
# --------------------------------------------------------------------------- #

def test_a_plain_one_tool_print_on_a_one_position_printer_is_charged_as_before():
    """Passes before the change by design: tool 1's 50 g go on the head's spool."""
    with OnePosition() as rig, _download(_gcode({1: 50.0})):
        out = print_deduct.deduct_completed_print(P, "f.gcode", JOB, fb_url="http://fb",
                                                  end_heads=END)
    assert out["status"] == "deducted", out
    assert rig.sm.used(200) == pytest.approx(60.0)
    assert rig.sm.used(100) == pytest.approx(100.0)


def test_a_one_tool_swap_on_a_one_position_printer_is_split_with_no_line():
    """Passes before the change by design (the whole path folded the usage, and the
    old fold read tool 1's figure as position 0's); pinned so it stays so."""
    text = _gcode({1: 50.0})
    with OnePosition(), _download(text):
        out = print_deduct.deduct_completed_print(
            P, "f.gcode", JOB, fb_url="http://fb", start_spools={"0": 100}, swap_log=SWAP,
            end_heads=END)
    assert out["status"] == "pending_spool_changed" and out.get("auto_split") is True, out
    rec = _card()
    # #100 printed up to the swap: tool 1's own figure there, from the same walk.
    want = round(prusalink_api.measure_filament_usage(text, [0.4])["partials"][0][1], 2)
    assert 0 < want < 50
    grams = {r["sid"]: r["grams"] for r in rec["spools"]}
    assert grams == {100: want, 200: round(50.0 - want, 2)}, rec
    assert not rec.get("unresolved_usage"), rec
    assert _on_card(rec) == 50.0


def test_a_two_tool_print_whose_head_was_swapped_asks_and_puts_each_gram_on_the_card_once():
    """Red on eb94846: position 0 was split by T0's figures as if the swap were
    T0's slot's; on one head it could be either slot's, so the head asks. Every gram
    of the footer is on the card once either way."""
    text = _gcode({0: 30.0, 1: 50.0})
    with OnePosition(), _download(text):
        print_deduct.deduct_completed_print(
            P, "f.gcode", JOB, fb_url="http://fb", start_spools={"0": 100}, swap_log=SWAP,
            end_heads=END)
    rec = _card()
    assert rec["kind"] == "no_spool" and rec["spools"] == [], rec
    assert rec["usage_map"] == {"0": 30.0, "1": 50.0}, rec
    assert [o["sid"] for o in rec["unresolved_sets"]["0"]] == [100, 200], rec
    assert "couldn't split" in rec["unresolved_notes"]["0"], rec
    assert _on_card(rec) == 80.0
