"""Group 10.9 — Unit tests for choice_validation.js.

Pure-JS module loaded in the browser via mountOverlay-style globals
(`window.normalizeChoice`, `window.levenshtein`, `window.validateNewChoice`).
We exercise it through Playwright's `page.evaluate` so we test the actual
shipped code, not a Python port. The fixture loads the dashboard so the
script tags are evaluated.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page


@pytest.fixture
def loaded_page(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_function("typeof window.validateNewChoice === 'function'", timeout=5_000)
    return page


def _validate(page, raw, existing=None):
    return page.evaluate(
        "([raw, existing]) => window.validateNewChoice(raw, existing)",
        [raw, existing or []],
    )


def _normalize(page, raw):
    return page.evaluate("(r) => window.normalizeChoice(r)", raw)


def _lev(page, a, b):
    return page.evaluate("([a, b]) => window.levenshtein(a, b)", [a, b])


# --- normalize ---------------------------------------------------------------

def test_normalize_trims_outer_whitespace(loaded_page):
    assert _normalize(loaded_page, "  PETG  ") == "PETG"


def test_normalize_collapses_internal_whitespace(loaded_page):
    assert _normalize(loaded_page, "Carbon   Fiber") == "Carbon Fiber"


def test_normalize_handles_empty(loaded_page):
    assert _normalize(loaded_page, "") == ""
    assert _normalize(loaded_page, None) == ""


# --- levenshtein -------------------------------------------------------------

def test_lev_identical(loaded_page):
    assert _lev(loaded_page, "abc", "abc") == 0


def test_lev_one_edit(loaded_page):
    assert _lev(loaded_page, "abc", "abd") == 1


def test_lev_two_edits(loaded_page):
    assert _lev(loaded_page, "kitten", "sitting") == 3


def test_lev_empty(loaded_page):
    assert _lev(loaded_page, "", "abc") == 3
    assert _lev(loaded_page, "abc", "") == 3


# --- validateNewChoice: rejection paths --------------------------------------

def test_rejects_empty(loaded_page):
    r = _validate(loaded_page, "", [])
    assert r["ok"] is False
    assert "empty" in r["error"].lower()


def test_rejects_below_min_length(loaded_page):
    r = _validate(loaded_page, "F", [])
    assert r["ok"] is False
    assert "3 characters" in r["error"]


def test_rejects_leading_punctuation(loaded_page):
    r = _validate(loaded_page, ";Transparent", [])
    assert r["ok"] is False
    assert "punctuation" in r["error"].lower()


def test_rejects_trailing_punctuation(loaded_page):
    r = _validate(loaded_page, "Carbon Fiber,", [])
    assert r["ok"] is False
    assert "punctuation" in r["error"].lower()


def test_rejects_separator_confusion(loaded_page):
    """A value starting or ending with a separator likely indicates the user
    typed multiple values into one input. Reject and let them re-enter."""
    r = _validate(loaded_page, "/Transparent", [])
    assert r["ok"] is False


# --- validateNewChoice: suggestion paths -------------------------------------

def test_suggests_exact_case_insensitive_match(loaded_page):
    r = _validate(loaded_page, "transparent", ["Transparent", "Carbon Fiber"])
    assert r["ok"] is True
    assert r["suggestion"] == "Transparent"


def test_suggests_normalized_key_match(loaded_page):
    """Carbon-Fiber should collapse to the same normalized key as Carbon Fiber."""
    r = _validate(loaded_page, "Carbon-Fiber", ["Carbon Fiber", "PETG"])
    assert r["ok"] is True
    assert r["suggestion"] == "Carbon Fiber"


def test_suggests_prefix_match(loaded_page):
    """Tran is a prefix of Transparent → suggest Transparent."""
    r = _validate(loaded_page, "Tran", ["Transparent", "PETG"])
    assert r["ok"] is True
    assert r["suggestion"] == "Transparent"


def test_suggests_within_two_edits(loaded_page):
    """One-letter typo should suggest the original."""
    r = _validate(loaded_page, "Glower", ["Glow", "PETG"])
    assert r["ok"] is True
    assert r["suggestion"] == "Glow"


def test_clean_value_with_no_match_passes(loaded_page):
    r = _validate(loaded_page, "Multi-Color", ["PETG", "Carbon Fiber"])
    assert r["ok"] is True
    assert "suggestion" not in r or r.get("suggestion") is None
    assert r["canonical"] == "Multi-Color"


def test_canonical_strips_whitespace(loaded_page):
    r = _validate(loaded_page, "  Multi   Color  ", [])
    assert r["ok"] is True
    assert r["canonical"] == "Multi Color"


def test_exact_match_returns_existing_as_canonical_form(loaded_page):
    """When the user types something already in the list (any case), the
    suggestion field points back to the existing canonical form so the caller
    knows to defer to it rather than committing a new variant."""
    r = _validate(loaded_page, "PETG", ["PETG", "PLA"])
    assert r["ok"] is True
    assert r["suggestion"] == "PETG"


def test_suggestion_priority_exact_beats_prefix(loaded_page):
    """Exact case-insensitive match should win over prefix match if both apply."""
    r = _validate(loaded_page, "PETG", ["PETG-CF", "PETG"])
    assert r["ok"] is True
    assert r["suggestion"] == "PETG"
