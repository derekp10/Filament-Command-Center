"""
Tests for the Phase-2 weight-entry math helper (`window.computeUsedWeight`)
and the `+/-` parser (`window.parseAdditiveInput`) in weight_utils.js.

Both helpers are pure functions exposed on `window` so we exercise the real
JS inside Chromium — no shimming.

The math helper backs all four modes of the unified <WeightEntry> component:
- gross    : user enters scale reading WITH spool       -> used = initial - (gross - empty)
- net      : user enters filament-only weight remaining -> used = initial - net
- additive : user enters signed delta (e.g. +50 / -20)  -> used = current_used + delta
- set_used : user enters target used_weight directly    -> used = value
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page


def _open_dashboard(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function(
        "typeof window.computeUsedWeight === 'function'", timeout=5_000
    )
    page.wait_for_function(
        "typeof window.parseAdditiveInput === 'function'", timeout=5_000
    )


# --- computeUsedWeight ------------------------------------------------------


@pytest.mark.parametrize(
    "args,expected",
    [
        # GROSS — used = initial - (gross - empty)
        # Spool 1000g initial, empty=220, gross reading 645 -> 1000 - (645-220) = 575
        (
            {"mode": "gross", "value": 645, "initial_weight": 1000,
             "current_used": 200, "empty_spool_weight": 220},
            {"used_weight": 575, "remaining": 425, "capped": None,
             "requires_empty": False, "error": None},
        ),
        # GROSS — gross equals empty -> filament fully consumed (used = initial)
        (
            {"mode": "gross", "value": 220, "initial_weight": 1000,
             "current_used": 0, "empty_spool_weight": 220},
            {"used_weight": 1000, "remaining": 0, "capped": None,
             "requires_empty": False, "error": None},
        ),
        # GROSS — gross > spool+filament (impossible reading) clamps low at 0 used? No,
        # gross > initial+empty means raw_used < 0 -> clamps to 0 (capped='low').
        (
            {"mode": "gross", "value": 1300, "initial_weight": 1000,
             "current_used": 0, "empty_spool_weight": 220},
            {"used_weight": 0, "remaining": 1000, "capped": "low",
             "requires_empty": False, "error": None},
        ),
        # GROSS — missing empty_spool_weight -> requires_empty
        (
            {"mode": "gross", "value": 645, "initial_weight": 1000,
             "current_used": 0, "empty_spool_weight": None},
            {"used_weight": None, "remaining": None, "capped": None,
             "requires_empty": True, "error": None},
        ),
        # GROSS — empty_spool_weight = 0 also triggers requires_empty (0 is "unset")
        (
            {"mode": "gross", "value": 645, "initial_weight": 1000,
             "current_used": 0, "empty_spool_weight": 0},
            {"used_weight": None, "remaining": None, "capped": None,
             "requires_empty": True, "error": None},
        ),
        # NET — used = initial - net
        (
            {"mode": "net", "value": 425, "initial_weight": 1000,
             "current_used": 200, "empty_spool_weight": None},
            {"used_weight": 575, "remaining": 425, "capped": None,
             "requires_empty": False, "error": None},
        ),
        # NET — net > initial -> raw_used < 0 -> clamps low to 0
        (
            {"mode": "net", "value": 1100, "initial_weight": 1000,
             "current_used": 0, "empty_spool_weight": None},
            {"used_weight": 0, "remaining": 1000, "capped": "low",
             "requires_empty": False, "error": None},
        ),
        # ADDITIVE — used = current_used + delta
        (
            {"mode": "additive", "value": 50, "initial_weight": 1000,
             "current_used": 575, "empty_spool_weight": None},
            {"used_weight": 625, "remaining": 375, "capped": None,
             "requires_empty": False, "error": None},
        ),
        # ADDITIVE — negative delta past 0 clamps low
        (
            {"mode": "additive", "value": -100, "initial_weight": 1000,
             "current_used": 50, "empty_spool_weight": None},
            {"used_weight": 0, "remaining": 1000, "capped": "low",
             "requires_empty": False, "error": None},
        ),
        # ADDITIVE — delta past initial clamps high (ALEX FIX preview)
        (
            {"mode": "additive", "value": 500, "initial_weight": 1000,
             "current_used": 800, "empty_spool_weight": None},
            {"used_weight": 1000, "remaining": 0, "capped": "high",
             "requires_empty": False, "error": None},
        ),
        # SET_USED — used = value
        (
            {"mode": "set_used", "value": 575, "initial_weight": 1000,
             "current_used": 200, "empty_spool_weight": None},
            {"used_weight": 575, "remaining": 425, "capped": None,
             "requires_empty": False, "error": None},
        ),
        # SET_USED — value > initial clamps high
        (
            {"mode": "set_used", "value": 1500, "initial_weight": 1000,
             "current_used": 0, "empty_spool_weight": None},
            {"used_weight": 1000, "remaining": 0, "capped": "high",
             "requires_empty": False, "error": None},
        ),
        # SET_USED — negative value clamps low to 0
        (
            {"mode": "set_used", "value": -10, "initial_weight": 1000,
             "current_used": 0, "empty_spool_weight": None},
            {"used_weight": 0, "remaining": 1000, "capped": "low",
             "requires_empty": False, "error": None},
        ),
    ],
    ids=[
        "gross-basic",
        "gross-empty-equals-tare",
        "gross-over-clamps-low",
        "gross-missing-empty-requires-prompt",
        "gross-zero-empty-requires-prompt",
        "net-basic",
        "net-over-initial-clamps-low",
        "additive-positive-delta",
        "additive-negative-past-zero-clamps-low",
        "additive-past-initial-clamps-high",
        "set-used-basic",
        "set-used-over-initial-clamps-high",
        "set-used-negative-clamps-low",
    ],
)
def test_compute_used_weight(page: Page, args, expected):
    _open_dashboard(page)
    result = page.evaluate("(a) => window.computeUsedWeight(a)", args)
    for key, val in expected.items():
        assert result[key] == val, (
            f"computeUsedWeight({args}).{key} = {result[key]!r}, expected {val!r}"
        )


def test_compute_used_weight_invalid_initial(page: Page):
    """initial_weight <= 0 (or missing) is a hard error."""
    _open_dashboard(page)
    for bad in [0, -100, None]:
        r = page.evaluate(
            "(a) => window.computeUsedWeight(a)",
            {"mode": "net", "value": 100, "initial_weight": bad},
        )
        assert r["error"] == "invalid_initial"
        assert r["used_weight"] is None


def test_compute_used_weight_invalid_value(page: Page):
    """Empty / NaN / non-numeric value returns error: 'invalid_value'."""
    _open_dashboard(page)
    for bad in ["", None, "abc"]:
        r = page.evaluate(
            "(a) => window.computeUsedWeight(a)",
            {"mode": "net", "value": bad, "initial_weight": 1000},
        )
        assert r["error"] == "invalid_value"
        assert r["used_weight"] is None


def test_compute_used_weight_invalid_mode(page: Page):
    _open_dashboard(page)
    r = page.evaluate(
        "(a) => window.computeUsedWeight(a)",
        {"mode": "wat", "value": 100, "initial_weight": 1000},
    )
    assert r["error"] == "invalid_mode"


# --- parseAdditiveInput ----------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+50", {"value": 50, "sign": "+"}),
        ("-20", {"value": -20, "sign": "-"}),
        ("50",  {"value": 50, "sign": None}),
        ("",    {"value": None, "sign": None}),
        (None,  {"value": None, "sign": None}),
        (" +12.5 ", {"value": 12.5, "sign": "+"}),
        ("+",   {"value": None, "sign": None}),  # bare sign is "no input"
    ],
    ids=[
        "plus-prefix",
        "minus-prefix",
        "bare-number",
        "empty-string",
        "null",
        "whitespace-and-decimal",
        "bare-sign-is-no-input",
    ],
)
def test_parse_additive_input(page: Page, raw, expected):
    _open_dashboard(page)
    result = page.evaluate("(r) => window.parseAdditiveInput(r)", raw)
    assert result == expected, f"parseAdditiveInput({raw!r}) -> {result!r}"
