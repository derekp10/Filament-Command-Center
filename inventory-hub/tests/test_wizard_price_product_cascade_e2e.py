"""L349 (filament→spool price cascade) + L351 (per-spool product_url input).

L349: a new/cloned/edited spool with no price of its own inherits the filament's
price (mirrors the empty-weight cascade), BLANK-GATED so it never overwrites an
explicit spool price (Derek's constraint: "as long as we aren't overwriting
filaments/spools that have data for that field").

L351: the spool section of the wizard now has its own editable Product Link
input (#wiz-spool-product_url), populated on a Prusament/import scan in parity
with the existing Purchase Link input.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect


def _goto(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.wizardPrefillSpoolPrice === 'function'", timeout=5_000)


def _set_price(page: Page, val: str) -> None:
    page.evaluate("(v) => { document.getElementById('wiz-spool-price').value = v; }", val)


def _get_price(page: Page) -> str:
    return page.evaluate("document.getElementById('wiz-spool-price').value")


# ---------------- L349: price cascade (blank-gated) ----------------

def test_price_inherits_filament_when_spool_blank(page: Page):
    _goto(page)
    _set_price(page, "")
    page.evaluate("window.wizardPrefillSpoolPrice(null, 25.5)")
    assert _get_price(page) == "25.5"


def test_price_prefers_spools_own_value(page: Page):
    _goto(page)
    _set_price(page, "")
    page.evaluate("window.wizardPrefillSpoolPrice(10, 25.5)")
    assert _get_price(page) == "10"


def test_price_never_overwrites_existing_typed_value(page: Page):
    """The blank-gate: an already-populated price field is left untouched."""
    _goto(page)
    _set_price(page, "99")
    page.evaluate("window.wizardPrefillSpoolPrice(null, 25.5)")
    assert _get_price(page) == "99"


def test_price_noop_when_no_source(page: Page):
    _goto(page)
    _set_price(page, "")
    page.evaluate("window.wizardPrefillSpoolPrice(null, null)")
    assert _get_price(page) == ""


# ---------------- L351: per-spool product_url input ----------------

def test_spool_product_url_input_exists(page: Page):
    _goto(page)
    expect(page.locator("#wiz-spool-product_url")).to_have_count(1)


def test_scan_populates_both_url_inputs(page: Page):
    """A scanned/imported template fills BOTH the spool's product_url (from the
    product/external link) and purchase_url (from the buy link) inputs."""
    _goto(page)
    page.evaluate("window.openWizardModal && window.openWizardModal()")
    expect(page.locator("#wizardModal")).to_be_visible()
    page.evaluate(
        "window.applyFilamentFieldsFromTemplate("
        "{external_link:'https://prod.example/x', purchase_link:'https://buy.example/y'})"
    )
    expect(page.locator("#wiz-spool-product_url")).to_have_value("https://prod.example/x")
    expect(page.locator("#wiz-spool-purchase_url")).to_have_value("https://buy.example/y")

    # Clean close so we don't pollute later tests.
    page.evaluate("""
        const m = bootstrap.Modal.getInstance(document.getElementById('wizardModal'));
        if (m) { try { wizardState.forceClose = true; wizardState.isDirty = false; } catch (_) {} m.hide(); }
    """)
